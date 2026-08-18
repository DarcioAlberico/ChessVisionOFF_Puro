from __future__ import annotations

import inspect
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.board_detection import (
    NoBoardDetectedError,
    _sort_selected_candidates,
    detect_board,
    detect_boards,
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
        image_bgr = cv2.imread(str(fixture))
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


if __name__ == "__main__":
    unittest.main()
