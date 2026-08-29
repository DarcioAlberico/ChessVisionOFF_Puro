from __future__ import annotations

import inspect
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.atomic_io import read_image
from chess_diagram_ocr.board_detection import (
    SQUARE_KERNEL,
    NoBoardDetectedError,
    _repaired_pass,
    _sort_selected_candidates,
    _threshold_passes,
    detect_board,
    detect_boards,
    order_quad_points,
)
from chess_diagram_ocr.config import DEFAULT_MAX_BOARDS, DEFAULT_READING_ORDER
from chess_diagram_ocr.pdf_to_pgn import save_pdf_positions_to_pgn, scan_pdf_positions

ROOT = Path(__file__).resolve().parents[1]


class BoardDetectionTests(unittest.TestCase):
    def test_detect_boards_returns_empty_for_blank_page(self) -> None:
        blank_page = np.full((1400, 1000, 3), 255, dtype=np.uint8)

        boards = detect_boards(blank_page, max_boards=1)

        self.assertEqual(boards, [])

    def test_detect_board_raises_when_no_board_is_found(self) -> None:
        blank_page = np.full((1400, 1000, 3), 255, dtype=np.uint8)

        with self.assertRaises(NoBoardDetectedError):
            detect_board(blank_page)

    def test_detect_boards_still_finds_real_sample(self) -> None:
        """Uma página com um diagrama devolve um diagrama, 800×800 e com quad.

        **Ele lia `data/samples/` e pulava na CI** -- e como era a única cobertura executável do
        detector sobre imagem, a CI não tinha nenhuma: uma regressão que fizesse `detect_boards`
        devolver vazio entrava verde. O caminho agora é o fixture versionado da S-09
        (`tests/fixtures/`), que roda em qualquer checkout. As páginas e a receita delas estão
        em `tests/test_fixtures.py`, com o que elas cobrem e o que não cobrem.
        """
        fixture = ROOT / "tests" / "fixtures" / "um_diagrama.png"
        image_bgr = read_image(fixture)
        self.assertIsNotNone(image_bgr, f"Falha ao abrir o fixture: {fixture}")
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

        boards = detect_boards(image_rgb, max_boards=1)

        self.assertEqual(len(boards), 1)
        board_rgb, quad = boards[0]
        self.assertEqual(board_rgb.shape[:2], (800, 800))
        self.assertIsNotNone(quad)

    def test_column_reading_order_groups_by_left_to_right_columns(self) -> None:
        def candidate(identifier: int, bbox: tuple[int, int, int, int]) -> tuple[np.ndarray, float, tuple[int, int, int, int]]:
            return np.full((4, 2), identifier, dtype=np.float32), 1.0, bbox

        selected = [
            candidate(2, (500, 20, 80, 80)),
            candidate(4, (510, 410, 80, 80)),
            candidate(3, (105, 400, 80, 80)),
            candidate(1, (100, 10, 80, 80)),
        ]

        _sort_selected_candidates(selected, "column")

        self.assertEqual([int(item[0][0, 0]) for item in selected], [1, 3, 2, 4])


def _synthetic_grid(rows: int, columns: int, *, cell: int = 24, margin: int = 40) -> np.ndarray:
    """Pagina branca com `rows x columns` tabuleiros 8x8 desenhados em xadrez.

    Serve para exercitar o teto de `max_boards` sem depender de PDF: o detector so
    precisa de quadrados com textura periodica, que e o que ele pontua.
    """
    board = cell * 8
    espaco = cell
    page = np.full(
        (margin * 2 + rows * board + (rows - 1) * espaco, margin * 2 + columns * board + (columns - 1) * espaco, 3),
        255,
        dtype=np.uint8,
    )
    for row in range(rows):
        for column in range(columns):
            y0 = margin + row * (board + espaco)
            x0 = margin + column * (board + espaco)
            for i in range(8):
                for j in range(8):
                    if (i + j) % 2:
                        page[y0 + i * cell : y0 + (i + 1) * cell, x0 + j * cell : x0 + (j + 1) * cell] = 90
            cv2.rectangle(page, (x0, y0), (x0 + board - 1, y0 + board - 1), (0, 0, 0), 2)
    return page


class MaxBoardsCapTests(unittest.TestCase):
    """Regressao: numa grade 3x3 o teto de 8 cortava um diagrama, e em silencio.

    Medido no "A Matter of Endgame Technique", pagina 17: os nove diagramas pontuam entre
    0,2667 e 0,3054 -- um bloco praticamente empatado --, e o corte por score derrubava o
    do canto superior direito. Nada na tela dizia que faltava um.
    """

    def test_a_three_by_three_page_is_not_truncated_by_the_default(self) -> None:
        page = _synthetic_grid(3, 3)
        self.assertGreaterEqual(len(detect_boards(page)), 9)

    def test_the_cap_still_limits_when_asked_to(self) -> None:
        page = _synthetic_grid(3, 3)
        self.assertEqual(len(detect_boards(page, max_boards=4)), 4)

    def test_hitting_the_cap_is_logged_instead_of_silent(self) -> None:
        page = _synthetic_grid(3, 3)
        with self.assertLogs("chess_diagram_ocr.board_detection", level="WARNING") as captured:
            detect_boards(page, max_boards=4)
        self.assertIn("max_boards", "\n".join(captured.output))

    def test_no_warning_when_the_cap_does_not_bind(self) -> None:
        page = _synthetic_grid(2, 2)
        with self.assertNoLogs("chess_diagram_ocr.board_detection", level="WARNING"):
            detect_boards(page)

    def test_a_deliberate_single_board_request_does_not_warn(self) -> None:
        """O aviso é para o teto do usuário, e refinar um recorte não usa esse teto.

        `refine_candidate_with_contour` pede **um** tabuleiro dentro da região de um
        candidato já localizado -- ali `max_boards=1` é o pedido, não um limite. O aviso
        aparecia mesmo assim, num OCR de página normal, mandando "aumente 'Max diagramas'"
        numa configuração que não tem efeito nenhum sobre aquela chamada.
        """
        page = _synthetic_grid(3, 3)
        with self.assertNoLogs("chess_diagram_ocr.board_detection", level="WARNING"):
            detect_boards(page, max_boards=1, warn_on_cap=False)

    def test_the_internal_single_board_callers_all_silence_the_warning(self) -> None:
        """Silenciar num lugar só deixaria o aviso vazando pelos outros dois."""
        from chess_diagram_ocr import board_detection, service
        from chess_diagram_ocr.detection import hybrid

        for modulo in (board_detection, hybrid, service):
            fonte = inspect.getsource(modulo)
            for chamada in fonte.split("detect_boards(")[1:]:
                trecho = chamada[: chamada.find(")")]
                if "max_boards=1" in trecho:
                    with self.subTest(modulo=modulo.__name__):
                        self.assertIn("warn_on_cap=False", trecho)

    def test_the_default_cap_is_the_shared_constant(self) -> None:
        """O teto morava em seis arquivos como literal 8; divergir de novo seria facil."""
        self.assertEqual(inspect.signature(detect_boards).parameters["max_boards"].default, DEFAULT_MAX_BOARDS)
        self.assertGreaterEqual(DEFAULT_MAX_BOARDS, 9)

    def test_every_pipeline_entry_point_shares_the_cap(self) -> None:
        """Trocar a constante nao basta: o default de cada rota tem de vir dela.

        Foi assim que a correcao vazou na primeira tentativa -- `config` e as funcoes ja
        diziam 12, e `cvoff-export` continuava exportando 8 diagramas porque o
        `add_argument` tinha o literal antigo.
        """
        from chess_diagram_ocr.detection.hybrid import detect_diagrams, detect_diagrams_in_pdf_page
        from chess_diagram_ocr.pdf_to_pgn import save_pdf_positions_to_pgn, scan_pdf_positions
        from chess_diagram_ocr.review_queue import build_review_queue

        rotas = [
            (detect_boards, "max_boards"),
            (detect_diagrams, "max_boards"),
            (detect_diagrams_in_pdf_page, "max_boards"),
            (scan_pdf_positions, "max_boards_per_page"),
            (save_pdf_positions_to_pgn, "max_boards_per_page"),
            (build_review_queue, "max_boards_per_page"),
        ]
        for função, parâmetro in rotas:
            with self.subTest(rota=função.__name__):
                self.assertEqual(inspect.signature(função).parameters[parâmetro].default, DEFAULT_MAX_BOARDS)

    def test_command_line_defaults_share_the_cap(self) -> None:
        from chess_diagram_ocr.cli.export_pgn import parse_args as export_args
        from chess_diagram_ocr.cli.review import parse_args as review_args

        for parse, argv in ((export_args, ["livro.pdf"]), (review_args, ["livro.pdf"])):
            with self.subTest(cli=parse.__module__):
                self.assertEqual(parse(argv).max_boards_per_page, DEFAULT_MAX_BOARDS)


class ReadingOrderIsUnifiedTests(unittest.TestCase):
    """S-14: a numeracao de diagramas tem de ser a mesma na GUI e na exportacao.

    O bug era de configuracao, nao de algoritmo: `detect_boards` tinha `"row"` por padrao,
    a exportacao passava `"column"`, e os frontends chamavam sem o parametro. Numa pagina
    de duas colunas o `[Diagram "2"]` do PGN apontava para outra posicao que a da tela.
    Estes testes travam justamente os defaults.
    """

    def test_detect_boards_default_is_the_shared_default(self) -> None:
        default = inspect.signature(detect_boards).parameters["reading_order"].default
        self.assertEqual(default, DEFAULT_READING_ORDER)

    def test_export_path_default_is_the_shared_default(self) -> None:
        for function in (scan_pdf_positions, save_pdf_positions_to_pgn):
            with self.subTest(function=function.__name__):
                default = inspect.signature(function).parameters["reading_order"].default
                self.assertEqual(default, DEFAULT_READING_ORDER)

    def test_gui_and_export_routes_number_the_page_the_same_way(self) -> None:
        """Compara as duas rotas de verdade: a GUI chama `detect_boards` sem o parametro,
        a exportacao chama com o valor que propaga desde o CLI."""
        page = _page_with_boards_in_two_columns()

        gui_boards = detect_boards(page, max_boards=4)
        export_boards = detect_boards(page, max_boards=4, reading_order=DEFAULT_READING_ORDER)

        self.assertEqual(len(gui_boards), 4)
        for index, (gui_item, export_item) in enumerate(zip(gui_boards, export_boards, strict=True)):
            with self.subTest(diagram=index + 1):
                np.testing.assert_array_equal(gui_item[1], export_item[1])

    def test_column_order_is_what_a_two_column_book_needs(self) -> None:
        """Ancora o valor do padrao: ler em coluna significa descer a coluna da esquerda
        toda antes de passar para a direita."""
        page = _page_with_boards_in_two_columns()

        boards = detect_boards(page, max_boards=4)
        centers = [(quad[:, 0].mean(), quad[:, 1].mean()) for _, quad in boards if quad is not None]

        self.assertEqual(len(centers), 4)
        left_x = [x for x, _ in centers[:2]]
        right_x = [x for x, _ in centers[2:]]
        self.assertLess(max(left_x), min(right_x))
        # E dentro de cada coluna, de cima para baixo.
        self.assertLess(centers[0][1], centers[1][1])
        self.assertLess(centers[2][1], centers[3][1])


def _page_with_boards_in_two_columns() -> np.ndarray:
    """Pagina sintetica com 4 tabuleiros: duas colunas de dois.

    Desenhar o padrao xadrez importa: `_extract_candidate_quads` pontua candidatos pela
    aparencia de tabuleiro, e um quadrado solido nao passa.
    """
    page = np.full((1200, 900, 3), 255, dtype=np.uint8)
    size = 320
    cell = size // 8
    for origin_x in (60, 500):
        for origin_y in (60, 620):
            for row in range(8):
                for column in range(8):
                    if (row + column) % 2 == 0:
                        continue
                    y = origin_y + row * cell
                    x = origin_x + column * cell
                    page[y : y + cell, x : x + cell] = 40
            cv2.rectangle(page, (origin_x, origin_y), (origin_x + size, origin_y + size), (0, 0, 0), 2)
    return page


def _severed_corner_pair(gap: int = 1) -> np.ndarray:
    """Duas casas que se encostariam pela quina, afastadas por `gap` px -- só o binário.

    É a unidade do defeito da S-175: é por este ponto, e só por ele, que duas casas da mesma
    paridade são 8-conexas.
    """
    binario = np.zeros((60, 60), np.uint8)
    binario[10 : 30 - gap, 10 : 30 - gap] = 255
    binario[30 + gap : 50, 30 + gap : 50] = 255
    return binario


def _board_with_severed_corner_contacts(gap: int = 1, *, cell: int = 24, margin: int = 40) -> np.ndarray:
    """Tabuleiro 8x8 em que **nenhuma** quina encosta: cada casa escura encolheu `gap` px.

    É o que a rasterização faz com a coluna esquerda do `Reinfeld` a 220 DPI, levado ao
    extremo -- lá a fase sub-pixel derruba os 7 contatos de uma linha da grade, aqui derruba
    todos. Sem o reparo o passe base vê 32 manchas soltas de 22 px, e não um tabuleiro.
    """
    lado = cell * 8
    page = np.full((margin * 2 + lado, margin * 2 + lado, 3), 255, np.uint8)
    for row in range(8):
        for column in range(8):
            if (row + column) % 2 == 0:
                continue
            y0 = margin + row * cell + gap
            x0 = margin + column * cell + gap
            page[y0 : margin + (row + 1) * cell - gap, x0 : margin + (column + 1) * cell - gap] = 90
    return page


def _components(binario: np.ndarray) -> int:
    total, _ = cv2.connectedComponents(binario, connectivity=8)
    return total - 1


class DiagonalContactRepairTests(unittest.TestCase):
    """S-175: o contorno fechava 7/8 do tabuleiro quando a quina não sobrevivia ao limiar.

    Medido no `Reinfeld_1001_Sacrificios_y_Combinaciones_Brillantes_1977.pdf`, página 141
    (0-based) a 220 DPI: a coluna esquerda saía 101×116 pt contra 116×116 na direita, e a
    leitura ia de 0,993 para 0,026. Ver `DIAGONAL_KERNELS` para o mecanismo.
    """

    def test_fechamento_reto_nao_liga_a_quina_e_o_reparo_liga(self) -> None:
        """A unidade do defeito, e o motivo de o passe existir.

        `MORPH_CLOSE` é dilatação seguida de erosão: com o elemento quadrado a dilatação
        atravessa a quina e a erosão corta o pescoço de volta. Ao longo da diagonal a erosão
        corre na direção da ponte, e ela sobrevive.
        """
        binario = _severed_corner_pair()

        reto = cv2.morphologyEx(binario, cv2.MORPH_CLOSE, SQUARE_KERNEL, iterations=1)

        self.assertEqual(_components(binario), 2)
        self.assertEqual(_components(reto), 2, "o fechamento reto não repara a quina -- é a razão da S-175")
        self.assertEqual(_components(_repaired_pass(binario)), 1)

    def test_o_reparo_contem_o_que_o_fechamento_reto_ja_ligava(self) -> None:
        """União, e não substituição: nada que estava conexo deixa de estar."""
        binario = np.zeros((60, 60), np.uint8)
        # Duas manchas separadas por 1 px na horizontal: o caso que o fechamento reto liga.
        binario[10:50, 10:29] = 255
        binario[10:50, 30:50] = 255

        self.assertEqual(_components(binario), 2)
        self.assertEqual(_components(cv2.morphologyEx(binario, cv2.MORPH_CLOSE, SQUARE_KERNEL, iterations=1)), 1)
        self.assertEqual(_components(_repaired_pass(binario)), 1)

    def test_tabuleiro_com_todas_as_quinas_partidas_sai_inteiro(self) -> None:
        page = _board_with_severed_corner_contacts()

        boards = detect_boards(page, max_boards=1)

        self.assertEqual(len(boards), 1)
        _board_rgb, quad = boards[0]
        self.assertIsNotNone(quad)
        assert quad is not None
        largura = float(quad[:, 0].max() - quad[:, 0].min())
        altura = float(quad[:, 1].max() - quad[:, 1].min())
        # 8 casas de 24 px. Uma fileira a menos daria ~168, que era o sintoma.
        self.assertGreater(largura, 24 * 7.5)
        self.assertGreater(altura, 24 * 7.5)

    def test_sem_o_reparo_a_pagina_e_so_manchas_soltas(self) -> None:
        """Prende no lugar o que o passe base sozinho enxerga -- para o teste acima ter valor."""
        page = _board_with_severed_corner_contacts()
        gray = cv2.cvtColor(page, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        base = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 41, 8)

        contours, _ = cv2.findContours(base, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        maior = max(cv2.boundingRect(contour)[2] for contour in contours)

        self.assertEqual(_components(base), 32, "as 32 casas de uma paridade, cada uma por si")
        self.assertLess(maior, 24 * 2, "o maior contorno do passe base é uma casa, não o tabuleiro")
        self.assertEqual(_components(_repaired_pass(base)), 1)

    def test_o_fechamento_reto_continua_sendo_um_passe_proprio(self) -> None:
        """A lição que custou 8 diagramas do `Gaprindashvili`, encravada.

        Unir o reparo ao fechamento reto numa imagem só economiza um `findContours` e **tira
        candidato**: fundir duas componentes remove as duas da lista de contornos e põe a
        fundida no lugar. Onde o contorno justo era o bom, ele deixava de existir -- e aquele
        livro tem um justo de 112 pt que lê 1,0000 e um largo de 116 pt que lê 0,29 a 0,87.
        """
        binario = _severed_corner_pair()

        passes = _threshold_passes(binario)
        reto = cv2.morphologyEx(binario, cv2.MORPH_CLOSE, SQUARE_KERNEL, iterations=1)

        self.assertEqual(len(passes), 3, "cru, fechamento reto e reparo de quina")
        np.testing.assert_array_equal(passes[0], binario, "o passe cru vai intocado")
        np.testing.assert_array_equal(passes[1], reto, "o fechamento reto vai sozinho, não fundido no reparo")
        self.assertEqual(_components(passes[1]), 2)
        self.assertEqual(_components(passes[2]), 1, "e o reparo entra como um terceiro, não no lugar dele")

    def test_o_reparo_nao_engorda_a_caixa(self) -> None:
        """Dilatar repararia a quina igual e deslocaria toda caixa do acervo em ~1 px.

        O fechamento devolve a forma ao tamanho original, então o diff do censo continua
        mostrando só o que de fato mudou.
        """
        binario = _severed_corner_pair()

        reparado = _repaired_pass(binario)
        dilatado = cv2.dilate(binario, SQUARE_KERNEL, iterations=1)

        self.assertEqual(cv2.boundingRect(reparado), cv2.boundingRect(binario))
        self.assertNotEqual(cv2.boundingRect(dilatado), cv2.boundingRect(binario))


if __name__ == "__main__":
    unittest.main()


class QuadA45GrausTests(unittest.TestCase):
    """Os quatro cantos saem distintos, inclusive no losango (S-363).

    A regra das somas e diferenças funciona para quadrilátero de pé e quebra a 45°: o mesmo ponto
    ganhava `argmin(soma)` e `argmin(diferença)`, a saída tinha um canto repetido e um perdido, e
    `getPerspectiveTransform` sobre isso é uma matriz sem sentido. É justamente o candidato torto
    que a geometria mais precisa julgar.
    """

    def _ordenado(self, quad: list[list[float]]) -> list[tuple[float, float]]:
        saida = order_quad_points(np.array(quad, dtype=np.float32))
        return [(float(x), float(y)) for x, y in saida]

    def test_o_losango_tem_quatro_cantos(self) -> None:
        cantos = self._ordenado([[100, 0], [200, 100], [100, 200], [0, 100]])
        self.assertEqual(len(set(cantos)), 4)

    def test_o_retangulo_sai_na_ordem_de_sempre(self) -> None:
        """TL, TR, BR, BL -- a convenção que `warp_from_quad` espera, e ela não mudou."""
        esperado = [(10.0, 20.0), (110.0, 20.0), (110.0, 120.0), (10.0, 120.0)]
        self.assertEqual(self._ordenado([[10, 20], [110, 20], [110, 120], [10, 120]]), esperado)
        self.assertEqual(self._ordenado([[110, 120], [10, 20], [110, 20], [10, 120]]), esperado)

    def test_o_quad_torto_da_a_volta_na_figura(self) -> None:
        cantos = self._ordenado([[12, 25], [108, 18], [115, 121], [16, 128]])
        self.assertEqual(len(set(cantos)), 4)
        self.assertEqual(cantos[0], (12.0, 25.0), "começa pelo canto de menor soma")
