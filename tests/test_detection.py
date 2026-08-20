from __future__ import annotations

import unittest
from unittest import mock

import cv2
import fitz
import numpy as np

from chess_diagram_ocr.board_detection import _bbox_iou, _checker_score, _grid_score, _small_gray
from chess_diagram_ocr.detection import (
    DiagramCandidate,
    candidates_from_embedded_images,
    detect_diagrams,
    trim_to_frame,
    trim_to_grid,
)
from chess_diagram_ocr.detection.hybrid import (
    EMBEDDED_SIZE_TOLERANCE,
    OVERLAP_IOU,
    REFINE_TOLERANCE,
    _contour_wins_over_merged,
    _same_region,
    _typical_side,
    board_checker_contrast,
    board_texture_score,
    refine_candidate_with_contour,
    texture_scores_side_by_side,
)

# Uma pagina A4 em pontos.
PAGE_WIDTH, PAGE_HEIGHT = 595.0, 842.0


def board_image(side: int = 320, *, border: int = 0, frame: bool = False) -> np.ndarray:
    """Imagem de tabuleiro 8x8 com casas alternadas e, opcionalmente, margem branca.

    `frame` desenha a linha preta em volta do tabuleiro, como um diagrama impresso tem -- e
    como `tests/fixtures/gerar.py` sempre desenhou. Sem ela as casas claras (245) encostam na
    margem branca (255) e o contorno nao tem borda onde fechar o retangulo: o detector so acha
    as casas de dentro. Fica em `False` por padrao porque quase todo teste deste arquivo
    substitui o detector; quem precisa dele de verdade e o refino (S-160).
    """
    cell = side // 8
    board = np.full((side, side, 3), 245, dtype=np.uint8)
    for row in range(8):
        for column in range(8):
            if (row + column) % 2:
                board[row * cell : (row + 1) * cell, column * cell : (column + 1) * cell] = 45
    if frame:
        cv2.rectangle(board, (0, 0), (side - 1, side - 1), (0, 0, 0), 3)
    if border:
        framed = np.full((side + 2 * border, side + 2 * border, 3), 255, dtype=np.uint8)
        framed[border : border + side, border : border + side] = board
        return framed
    return board


def board_with_caption(side: int = 320, caption_height: int = 60) -> np.ndarray:
    """Tabuleiro com faixa de legenda embaixo -- o caso 620x704 medido no Aagaard."""
    board = board_image(side)
    caption = np.full((caption_height, side, 3), 255, dtype=np.uint8)
    cv2.putText(caption, "Diagrama 12", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    return np.vstack([board, caption])


def hatched_board(side: int = 320) -> np.ndarray:
    """Tabuleiro de casa **hachurada** -- o estilo do `Karpov 1`.

    A diferença que importa não é estética: a fronteira entre casa clara e casa escura vira
    uma mudança de textura em vez de um traço, e `trim_to_grid` procura exatamente o traço.
    Medido no livro real, o passo mediano entre picos de gradiente sai 9 px onde a casa tem
    82 -- o que ela acha é a moldura e as bordas das peças, nunca a grade.
    """
    cell = side // 8
    board = np.full((side, side, 3), 245, dtype=np.uint8)
    for row in range(8):
        for column in range(8):
            if (row + column) % 2 == 0:
                continue
            y0, x0 = row * cell, column * cell
            for offset in range(-cell, cell, 5):
                cv2.line(
                    board,
                    (x0 + offset, y0 + cell),
                    (x0 + offset + cell, y0),
                    (30, 30, 30),
                    1,
                )
    return board


def framed_board_with_footer(
    side: int = 320, *, footer: int = 40, frame: int = 4, margin: int = 6, hatched: bool = True
) -> np.ndarray:
    """Tabuleiro com **moldura impressa** e faixa de avaliação embaixo.

    É a forma exata da imagem embutida do `Karpov 1`: moldura preta em volta do tabuleiro e,
    fora dela, o `△`/`+−` da avaliação. Recortar pelo bbox cru divide oito filas sobre
    tabuleiro **mais rodapé**, e o desvio acumula até passar de uma casa na fila 1.
    """
    board = hatched_board(side) if hatched else board_image(side)
    largura = side + 2 * (frame + margin)
    altura = side + 2 * (frame + margin) + footer
    imagem = np.full((altura, largura, 3), 255, dtype=np.uint8)

    topo = margin
    esquerda = margin
    lado_moldurado = side + 2 * frame
    imagem[topo : topo + lado_moldurado, esquerda : esquerda + lado_moldurado] = 20
    imagem[topo + frame : topo + frame + side, esquerda + frame : esquerda + frame + side] = board

    # A faixa de avaliacao: dois glifos pequenos, longe de encher 80% de uma linha.
    base = topo + lado_moldurado + margin + 24
    cv2.putText(imagem, "+-", (esquerda + side - 40, base), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return imagem


def png_bytes(image_rgb: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
    if not ok:
        raise RuntimeError("Falha ao codificar PNG do fixture.")
    return buffer.tobytes()


def pdf_with_images(placements: list[tuple[np.ndarray, fitz.Rect]]) -> fitz.Document:
    """PDF de uma pagina com as imagens dadas inseridas nos retangulos dados.

    Fixture gerado em memoria em vez de arquivo versionado: o repositorio nao versiona PDF
    (sao material protegido, ver ROADMAP) e um tabuleiro sintetico basta para exercitar o
    filtro de tamanho, de aspecto e de cobertura.
    """
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    for image, rect in placements:
        page.insert_image(rect, stream=png_bytes(image))
    return doc


def render(page: fitz.Page, dpi: int = 220) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    buffer = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return buffer[:, :, :3].copy() if pix.n == 4 else buffer.copy()


class TrimToGridTests(unittest.TestCase):
    def test_crops_the_caption_strip_and_returns_a_square(self) -> None:
        """O caso que motivou a funcao: imagem embutida que inclui a legenda (S-12)."""
        trimmed, trusted = trim_to_grid(board_with_caption(side=320, caption_height=60))

        self.assertTrue(trusted)
        self.assertEqual(trimmed.shape[0], trimmed.shape[1])
        # A legenda ficou de fora: a altura cai de 380 para ~320.
        self.assertLess(trimmed.shape[0], 380)
        self.assertGreater(trimmed.shape[0], 250)

    def test_removes_a_white_border(self) -> None:
        trimmed, trusted = trim_to_grid(board_image(side=320, border=40))

        self.assertTrue(trusted)
        self.assertLess(trimmed.shape[0], 400)

    def test_leaves_a_clean_board_alone(self) -> None:
        """Tabuleiro que já está recortado sai praticamente igual.

        "Praticamente" e não "igual": o lado sai de arredondar o passo medido da grade, então
        1 px de diferença é esperado -- e irrelevante, porque a imagem é redimensionada para
        800×800 antes de virar casas.
        """
        board = board_image(side=320)
        trimmed, trusted = trim_to_grid(board)

        self.assertTrue(trusted)
        self.assertAlmostEqual(trimmed.shape[0], board.shape[0], delta=2)
        self.assertAlmostEqual(trimmed.shape[1], board.shape[1], delta=2)

    def test_cala_diante_de_casa_hachurada(self) -> None:
        """A premissa da `trim_to_frame`, escrita como teste.

        Sem isto, alguém "conserta" a segunda tentativa mexendo no limiar da primeira -- e o
        limiar não é o problema: a função nem chega a avaliá-lo, porque `_board_span` desiste
        antes. A hachura não desenha linha de grade nenhuma.
        """
        _trimmed, trusted = trim_to_grid(framed_board_with_footer())
        self.assertFalse(trusted, "se a grade passar a ser detectável aqui, revise trim_to_frame")

    def test_refuses_to_crop_what_is_not_a_grid(self) -> None:
        """Recorte errado desloca a grade e estraga as 64 casas de uma vez.

        Diante de imagem sem periodicidade, devolver intacta e a resposta certa -- quem chama
        decide se ainda quer tentar ler.
        """
        noise = np.full((300, 300, 3), 200, dtype=np.uint8)
        cv2.circle(noise, (150, 150), 90, (20, 20, 20), -1)

        trimmed, trusted = trim_to_grid(noise)

        self.assertFalse(trusted)
        np.testing.assert_array_equal(trimmed, noise)

    def test_rejects_non_rgb_input(self) -> None:
        with self.assertRaises(ValueError):
            trim_to_grid(np.zeros((100, 100), dtype=np.uint8))


class TrimToFrameTests(unittest.TestCase):
    """A segunda tentativa, para quando a grade não é um traço (S-64).

    O defeito que ela corrige custou 8 posições erradas em 173 diagramas do `Karpov 1`, e uma
    delas passava pelo gate de exportação com confiança 0,9385 -- ia para o PGN principal como
    se estivesse certa. Ver `trim_to_frame` para os números.
    """

    def test_recorta_a_moldura_e_o_rodape_de_avaliacao(self) -> None:
        imagem = framed_board_with_footer(side=320, footer=40)
        aparado, confiou = trim_to_frame(imagem)

        self.assertTrue(confiou)
        self.assertLess(aparado.shape[0], imagem.shape[0], "o rodapé continuou na imagem")
        # O que sobra e o tabuleiro: quase quadrado, e a maior parte do original.
        self.assertAlmostEqual(aparado.shape[1] / aparado.shape[0], 1.0, delta=0.05)
        self.assertGreater(aparado.shape[0], 280)

    def test_o_que_sobra_e_o_tabuleiro_e_nao_a_moldura(self) -> None:
        """Se o traço preto entrar no recorte, ele vira parte da fila 8 e da fila 1."""
        aparado, _ = trim_to_frame(framed_board_with_footer(side=320, frame=4))
        borda = aparado[:2, :, :]
        self.assertGreater(float(borda.mean()), 100.0, "sobrou traço de moldura na borda")

    def test_sem_moldura_devolve_intacta(self) -> None:
        """Diagrama sem moldura impressa é a maioria do acervo; aqui ela tem de calar."""
        board = board_image(side=320)
        aparado, confiou = trim_to_frame(board)

        self.assertFalse(confiou)
        np.testing.assert_array_equal(aparado, board)

    def test_moldura_que_e_a_propria_borda_da_imagem_nao_conta(self) -> None:
        """Não há o que aparar, e dizer que aparou inflaria o `detector_score` à toa."""
        board = board_image(side=320)
        emoldurado = cv2.copyMakeBorder(board, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=(20, 20, 20))
        _aparado, confiou = trim_to_frame(emoldurado, inset=0)
        self.assertFalse(confiou)

    def test_recusa_quando_o_que_sobra_nao_e_quadrado(self) -> None:
        """A guarda que impede um sublinhado ou uma tarja de virar "moldura de tabuleiro"."""
        imagem = np.full((400, 400, 3), 255, dtype=np.uint8)
        imagem[40:60, :] = 20  # tarja horizontal larga
        imagem[360:380, :] = 20
        _aparado, confiou = trim_to_frame(imagem)
        self.assertFalse(confiou)

    def test_recusa_quando_a_moldura_cobre_quase_nada(self) -> None:
        imagem = np.full((400, 400, 3), 255, dtype=np.uint8)
        imagem[10:14, :] = 20
        imagem[30:34, :] = 20
        imagem[:, 10:14] = 20
        imagem[:, 30:34] = 20
        _aparado, confiou = trim_to_frame(imagem)
        self.assertFalse(confiou)

    def test_uma_fila_cheia_de_pecas_pretas_nao_e_moldura(self) -> None:
        """O vale entre os dois é largo: peças chegam a ~0,45 de preenchimento, moldura a 0,95."""
        board = board_image(side=320)
        cell = 320 // 8
        for coluna in range(8):
            centro = (coluna * cell + cell // 2, cell // 2)
            cv2.circle(board, centro, cell // 3, (20, 20, 20), -1)
        _aparado, confiou = trim_to_frame(board)
        self.assertFalse(confiou)

    def test_rejects_non_rgb_input(self) -> None:
        with self.assertRaises(ValueError):
            trim_to_frame(np.zeros((100, 100), dtype=np.uint8))


class TrimFallbackTests(unittest.TestCase):
    """A ordem das duas tentativas, e o fato de a segunda só existir para o que a 1ª perde."""

    def test_a_moldura_entra_quando_a_grade_cala(self) -> None:
        imagem = framed_board_with_footer(side=320, footer=40)
        doc = pdf_with_images([(imagem, fitz.Rect(80, 100, 380, 420))])
        try:
            candidatos = candidates_from_embedded_images(doc[0])
            self.assertEqual(len(candidatos), 1)
            candidato = candidatos[0]

            self.assertFalse(trim_to_grid(imagem)[1], "premissa: a grade tem de calar aqui")
            self.assertTrue(candidato.trimmed, "a segunda tentativa não entrou")
            altura, largura = candidato.board_rgb.shape[:2]
            self.assertAlmostEqual(largura / altura, 1.0, delta=0.05)
        finally:
            doc.close()

    def test_quando_a_grade_responde_a_moldura_nao_e_consultada(self) -> None:
        """A primeira tentativa continua sendo a primeira: ela usa o sinal mais específico."""
        with mock.patch("chess_diagram_ocr.detection.embedded.trim_to_frame") as espiao:
            doc = pdf_with_images([(board_with_caption(side=320, caption_height=60), fitz.Rect(80, 100, 380, 420))])
            try:
                candidatos = candidates_from_embedded_images(doc[0])
            finally:
                doc.close()

        self.assertEqual(len(candidatos), 1)
        self.assertTrue(candidatos[0].trimmed)
        espiao.assert_not_called()


class EmbeddedCandidateTests(unittest.TestCase):
    def test_finds_the_embedded_diagram(self) -> None:
        doc = pdf_with_images([(board_image(400), fitz.Rect(80, 100, 380, 400))])
        try:
            candidates = candidates_from_embedded_images(doc[0])

            self.assertEqual(len(candidates), 1)
            candidate = candidates[0]
            self.assertEqual(candidate.source, "embedded")
            self.assertEqual(candidate.native_size, (400, 400))
            # bbox em pontos do PDF, e nao em pixels: e o que a S-16 vai usar para associar
            # o texto vizinho sem depender do DPI do render.
            x0, y0, x1, y1 = candidate.bbox_pdf
            self.assertAlmostEqual(x0, 80, delta=2)
            self.assertAlmostEqual(y1, 400, delta=2)
        finally:
            doc.close()

    def test_ignores_the_full_page_background_scan(self) -> None:
        """A armadilha medida no Kemeri: cada pagina tem um scan de 1633x2468 cobrindo tudo."""
        scan = board_image(800)
        doc = pdf_with_images([(scan, fitz.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT))])
        try:
            self.assertEqual(candidates_from_embedded_images(doc[0]), [])
        finally:
            doc.close()

    def test_ignores_images_that_are_too_small(self) -> None:
        doc = pdf_with_images([(board_image(64), fitz.Rect(100, 100, 160, 160))])
        try:
            self.assertEqual(candidates_from_embedded_images(doc[0]), [])
        finally:
            doc.close()


class NotaDoMesmoLadoTests(unittest.TestCase):
    """A comparação de textura mede a imagem, e não a resolução em que ela chegou (S-130).

    `board_texture_score` leva qualquer recorte a 320 px, mas ampliar não cria detalhe: um
    recorte de 200 px ampliado a 320 continua borrado ao lado de um de 800 px reduzido a 320.
    A nota media a nitidez junto com a "tabuleiridade", e a decisão dependia de qual dos dois
    chegou maior.
    """

    def test_a_mesma_imagem_em_duas_resolucoes_recebe_a_mesma_nota(self) -> None:
        """A tolerância declarada é **zero**: os dois lados viram literalmente o mesmo array."""
        base = hatched_board(800)
        pequena = cv2.resize(base, (240, 240), interpolation=cv2.INTER_AREA)

        grande_nota, pequena_nota = board_detection_pair(base, pequena)

        self.assertEqual(grande_nota, pequena_nota)

    def test_a_ordem_dos_argumentos_nao_muda_o_par(self) -> None:
        a, b = hatched_board(800), cv2.resize(hatched_board(800), (300, 300), interpolation=cv2.INTER_AREA)

        primeira, segunda = board_detection_pair(a, b)
        invertida_b, invertida_a = board_detection_pair(b, a)

        self.assertAlmostEqual(primeira, invertida_a, places=12)
        self.assertAlmostEqual(segunda, invertida_b, places=12)

    def test_sem_a_correcao_a_nota_varia_com_a_resolucao(self) -> None:
        """O defeito, medido: amplitude 0,343 contra uma margem de decisão de 0,02.

        Num tabuleiro **limpo** a nota é estável nas oito resoluções -- é por isso que ninguém
        tinha visto. O acervo de verdade é hachurado.
        """
        base = hatched_board(800)
        notas = [
            board_texture_score(cv2.resize(base, (lado, lado), interpolation=cv2.INTER_AREA))
            for lado in (800, 640, 480, 320, 240, 200, 160, 128)
        ]
        self.assertGreater(max(notas) - min(notas), REFINE_TOLERANCE * 5)

        limpo = board_image(800)
        limpas = [
            board_texture_score(cv2.resize(limpo, (lado, lado), interpolation=cv2.INTER_AREA))
            for lado in (800, 640, 480, 320, 240, 200, 160, 128)
        ]
        self.assertLess(max(limpas) - min(limpas), 1e-9, "o caso limpo esconde o defeito")

    def test_a_parcela_de_xadrez_e_estavel_e_a_de_grade_nao(self) -> None:
        """Onde mora o ruído, e por que a S-143 tem uma segunda razão para desconfiar da grade.

        Medido: xadrez varia 0,0335--0,0340 nas oito resoluções; grade vai de 0,1429 a 1,0000,
        porque a hachura *aliasa* para o período de 20 px que o detector de picos procura.
        """
        base = hatched_board(800)
        xadrez, grade = [], []
        for lado in (800, 640, 480, 320, 240, 200, 160, 128):
            pequeno = _small_gray(cv2.resize(base, (lado, lado), interpolation=cv2.INTER_AREA))
            xadrez.append(_checker_score(pequeno))
            grade.append(_grid_score(pequeno))

        self.assertLess(max(xadrez) - min(xadrez), 0.01)
        self.assertGreater(max(grade) - min(grade), 0.5)


def board_detection_pair(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Atalho de leitura para o par de notas do mesmo lado."""
    return texture_scores_side_by_side(a, b)


class PaginaGiradaTests(unittest.TestCase):
    """A página com `/Rotate` não gera candidato fantasma (S-129).

    `get_image_info` devolve o bbox no sistema **não girado**; `get_pixmap` desenha a página
    **girada**. Quem consome a caixa -- o recorte, o retângulo na tela, a linha do conjunto de
    campo -- trabalha no sistema girado. Sem a correção, a caixa aponta para outro lugar da
    folha, e o resultado não é erro: é um candidato que parece diagrama e ocupa uma vaga do
    teto por página.

    **Medido no acervo em 2026-08-17: 1 página girada em 18.767** (`Yusupov`, p. 1413,
    `/Rotate 180`). O defeito é latente, e é por isso que ele precisa de teste: nada no acervo
    o denunciaria, e o dia em que entrar um livro digitalizado em paisagem já é tarde.
    """

    ALVO = fitz.Rect(80, 100, 380, 400)

    def _documento(self, rotacao: int) -> fitz.Document:
        doc = pdf_with_images([(board_image(400), self.ALVO)])
        doc[0].set_rotation(rotacao)
        return doc

    def _onde_o_tabuleiro_esta(self, page: fitz.Page) -> tuple[float, float, float, float]:
        """A caixa do tabuleiro medida no **pixel** da página desenhada, a 72 DPI.

        É a única referência que não depende da API sob teste: um ponto do PDF vira um pixel,
        então o retângulo em pixels é o retângulo em pontos.
        """
        imagem = render(page, dpi=72)
        escuro = np.argwhere(imagem[:, :, 0] < 200)
        ys, xs = escuro[:, 0], escuro[:, 1]
        return float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)

    def test_a_caixa_do_candidato_cai_onde_o_tabuleiro_esta_desenhado(self) -> None:
        for rotacao in (0, 90, 180, 270):
            with self.subTest(rotacao=rotacao):
                doc = self._documento(rotacao)
                try:
                    page = doc[0]
                    candidatos = candidates_from_embedded_images(page)
                    self.assertEqual(len(candidatos), 1)
                    esperado = self._onde_o_tabuleiro_esta(page)
                    for citado, real in zip(candidatos[0].bbox_pdf, esperado, strict=True):
                        self.assertAlmostEqual(citado, real, delta=3)
                finally:
                    doc.close()

    def test_sem_rotacao_nada_muda(self) -> None:
        """A correção é a identidade em 18.766 das 18.767 páginas do acervo. Vale travar."""
        doc = self._documento(0)
        try:
            (candidato,) = candidates_from_embedded_images(doc[0])
            for citado, real in zip(candidato.bbox_pdf, tuple(self.ALVO), strict=True):
                self.assertAlmostEqual(citado, real, delta=3)
        finally:
            doc.close()

    @staticmethod
    def _para_xywh(caixa: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return int(caixa[0]), int(caixa[1]), int(caixa[2] - caixa[0]), int(caixa[3] - caixa[1])

    def test_a_caixa_crua_nao_encosta_no_tabuleiro_girado(self) -> None:
        """O tamanho do estrago, medido: a caixa crua contra onde o tabuleiro está desenhado.

        | `/Rotate` | IoU da caixa crua |
        |---|---|
        | 0 | 1,000 |
        | 90 | **0,000** |
        | 180 | **0,000** |
        | 270 | **0,404** |

        Não é um erro de alguns pontos que o refino do contorno consertaria depois. E o 270 é o
        pior dos três justamente por não ser zero: um recorte que pega 40% do diagrama e 60% de
        outra coisa ainda passa nas guardas de tamanho e aspecto, e vira um candidato que
        *parece* um diagrama mal recortado em vez de um erro.
        """
        for rotacao, teto in ((90, 0.01), (180, 0.01), (270, 0.5)):
            with self.subTest(rotacao=rotacao):
                doc = self._documento(rotacao)
                try:
                    page = doc[0]
                    desenhado = self._onde_o_tabuleiro_esta(page)
                    crua = _bbox_iou(self._para_xywh(tuple(self.ALVO)), self._para_xywh(desenhado))
                    self.assertLess(crua, teto)

                    (candidato,) = candidates_from_embedded_images(page)
                    corrigida = _bbox_iou(self._para_xywh(candidato.bbox_pdf), self._para_xywh(desenhado))
                    self.assertGreater(corrigida, 0.95)
                finally:
                    doc.close()

    def test_a_legenda_girada_continua_ao_lado_do_diagrama(self) -> None:
        """A legenda é casada ao diagrama **por proximidade** (S-16), e proximidade é relativa.

        **Este é o teste que diz por que as duas correções são uma só.** Antes da S-129, as
        caixas do texto e da imagem estavam *ambas* no sistema não girado: erradas, e erradas
        do mesmo jeito, então a distância entre elas saía certa e a associação funcionava por
        acidente. Corrigir só `detection/embedded.py` põe as duas em sistemas diferentes e
        **quebra o que estava funcionando** -- medido aqui: a legenda passa de ≤ 60 pt para
        243 pt do diagrama, a 90°, e nenhum diagrama herda legenda nenhuma.

        Por isso o que se afirma é a distância, e não que a caixa caiba na página: ela cabe
        mesmo errada, e um teste sobre isso passaria nos três estados.
        """
        from chess_diagram_ocr.pdf_text import DEFAULT_RADIUS_PT, page_text_lines

        for rotacao in (0, 90, 180, 270):
            with self.subTest(rotacao=rotacao):
                doc = pdf_with_images([(board_image(400), self.ALVO)])
                try:
                    doc[0].insert_text(fitz.Point(90, 430), "31: Jogada das pretas", fontsize=11)
                    doc[0].set_rotation(rotacao)
                    page = doc[0]
                    (linha,) = [item for item in page_text_lines(page) if "pretas" in item.text]
                    (candidato,) = candidates_from_embedded_images(page)

                    dx = max(candidato.bbox_pdf[0] - linha.bbox[2], linha.bbox[0] - candidato.bbox_pdf[2], 0.0)
                    dy = max(candidato.bbox_pdf[1] - linha.bbox[3], linha.bbox[1] - candidato.bbox_pdf[3], 0.0)
                    self.assertLess(max(dx, dy), DEFAULT_RADIUS_PT)
                finally:
                    doc.close()


class MinimumSideInPointsTests(unittest.TestCase):
    """A guarda da S-78: tamanho **na página**, que é a unidade da pergunta.

    A fixture destes testes é o defeito. Todas as outras deste arquivo desenham em retângulos
    grandes, e é por isso que 509 testes verdes nunca distinguiram "128 px nativos" de "128 px
    nativos espremidos em 15 pt de página".
    """

    def test_o_glifo_do_cabecalho_nao_e_diagrama(self) -> None:
        """O cavalo do `Secrets`: 128 px nativos em 15,4 pt. Passava nas quatro guardas."""
        doc = pdf_with_images([(board_image(128), fitz.Rect(375.4, 16.3, 390.7, 31.7))])
        try:
            self.assertEqual(candidates_from_embedded_images(doc[0]), [])
        finally:
            doc.close()

    def test_a_mesma_imagem_em_tamanho_de_diagrama_e_diagrama(self) -> None:
        """O par do teste acima: o que muda é o retângulo, não a imagem.

        É esta dupla que separa a guarda nova da velha -- `MIN_EMBEDDED_SIDE` vê 128 px nos
        dois casos e não tem como distingui-los.
        """
        doc = pdf_with_images([(board_image(128), fitz.Rect(240, 320, 394, 474))])
        try:
            candidatos = candidates_from_embedded_images(doc[0])

            self.assertEqual(len(candidatos), 1)
            self.assertEqual(candidatos[0].native_size, (128, 128))
        finally:
            doc.close()

    def test_o_menor_diagrama_real_do_acervo_passa(self) -> None:
        """105,6 pt, medido no `Euwe Band 1-2`. O piso de 72 pt tem de deixá-lo entrar."""
        doc = pdf_with_images([(board_image(440), fitz.Rect(100, 100, 205.6, 205.6))])
        try:
            self.assertEqual(len(candidates_from_embedded_images(doc[0])), 1)
        finally:
            doc.close()

    def test_o_piso_e_parametro_e_nao_numero_solto_no_codigo(self) -> None:
        doc = pdf_with_images([(board_image(128), fitz.Rect(375.4, 16.3, 390.7, 31.7))])
        try:
            self.assertEqual(len(candidates_from_embedded_images(doc[0], min_side_pt=10.0)), 1)
        finally:
            doc.close()

    def test_o_glifo_nao_chega_ao_detector_hibrido(self) -> None:
        """A guarda vale onde o dano acontecia: na lista que numera os diagramas da página."""
        doc = pdf_with_images(
            [
                (board_image(128), fitz.Rect(375.4, 16.3, 390.7, 31.7)),
                (board_image(400), fitz.Rect(80, 100, 380, 400)),
            ]
        )
        try:
            page = doc[0]
            candidatos = detect_diagrams(page, render(page))

            self.assertEqual(len(candidatos), 1, "o glifo continuava consumindo um número")
            self.assertGreater(candidatos[0].bbox_pdf[3] - candidatos[0].bbox_pdf[1], 100)
        finally:
            doc.close()

    def test_ignores_images_that_are_not_roughly_square(self) -> None:
        wide = np.repeat(board_image(200), 3, axis=1)
        doc = pdf_with_images([(wide, fitz.Rect(50, 100, 500, 250))])
        try:
            self.assertEqual(candidates_from_embedded_images(doc[0]), [])
        finally:
            doc.close()

    def test_finds_several_diagrams_on_one_page(self) -> None:
        doc = pdf_with_images(
            [
                (board_image(320), fitz.Rect(60, 80, 280, 300)),
                (board_image(320), fitz.Rect(310, 80, 530, 300)),
                (board_image(320), fitz.Rect(60, 400, 280, 620)),
            ]
        )
        try:
            self.assertEqual(len(candidates_from_embedded_images(doc[0])), 3)
        finally:
            doc.close()


class HybridDetectorTests(unittest.TestCase):
    def test_uses_the_embedded_source_when_available(self) -> None:
        doc = pdf_with_images([(board_image(400), fitz.Rect(80, 100, 380, 400))])
        try:
            page = doc[0]
            candidates = detect_diagrams(page, render(page))

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].source, "embedded")
        finally:
            doc.close()

    def test_falls_back_to_contour_when_there_is_no_embedded_image(self) -> None:
        """12 dos 27 PDFs do acervo sao scan de pagina inteira: este caminho e a maioria."""
        doc = fitz.open()
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        # Diagrama desenhado com vetores, sem imagem embutida nenhuma.
        cell = 30.0
        origin_x, origin_y = 100.0, 150.0
        for row in range(8):
            for column in range(8):
                if (row + column) % 2:
                    rect = fitz.Rect(
                        origin_x + column * cell,
                        origin_y + row * cell,
                        origin_x + (column + 1) * cell,
                        origin_y + (row + 1) * cell,
                    )
                    page.draw_rect(rect, color=None, fill=(0.18, 0.18, 0.18))
        page.draw_rect(fitz.Rect(origin_x, origin_y, origin_x + 8 * cell, origin_y + 8 * cell), color=(0, 0, 0), width=1)

        try:
            self.assertEqual(candidates_from_embedded_images(page), [])

            candidates = detect_diagrams(page, render(page))

            self.assertTrue(candidates, "o contorno tem de achar o diagrama vetorial")
            self.assertEqual(candidates[0].source, "contour")
        finally:
            doc.close()

    def test_does_not_report_the_same_diagram_twice(self) -> None:
        """As duas fontes veem o mesmo tabuleiro; ele tem de sair uma vez so."""
        doc = pdf_with_images([(board_image(400), fitz.Rect(80, 100, 380, 400))])
        try:
            page = doc[0]
            candidates = detect_diagrams(page, render(page))

            self.assertEqual(len(candidates), 1)
        finally:
            doc.close()

    def test_orders_diagrams_by_reading_order(self) -> None:
        """Mesma regra da S-14, com candidatos das duas fontes na mesma lista."""
        doc = pdf_with_images(
            [
                (board_image(320), fitz.Rect(310, 80, 530, 300)),  # coluna direita, topo
                (board_image(320), fitz.Rect(60, 400, 280, 620)),  # coluna esquerda, baixo
                (board_image(320), fitz.Rect(60, 80, 280, 300)),  # coluna esquerda, topo
            ]
        )
        try:
            page = doc[0]
            candidates = detect_diagrams(page, render(page), reading_order="column")

            self.assertEqual(len(candidates), 3)
            centers = [((c.bbox_pdf[0] + c.bbox_pdf[2]) / 2, (c.bbox_pdf[1] + c.bbox_pdf[3]) / 2) for c in candidates]
            # Coluna da esquerda inteira antes da direita, e de cima para baixo dentro dela.
            self.assertLess(centers[0][0], centers[2][0])
            self.assertLess(centers[0][1], centers[1][1])
        finally:
            doc.close()

    def test_respects_max_boards(self) -> None:
        doc = pdf_with_images(
            [
                (board_image(320), fitz.Rect(60, 80, 280, 300)),
                (board_image(320), fitz.Rect(310, 80, 530, 300)),
                (board_image(320), fitz.Rect(60, 400, 280, 620)),
            ]
        )
        try:
            page = doc[0]
            self.assertEqual(len(detect_diagrams(page, render(page), max_boards=2)), 2)
        finally:
            doc.close()

    def test_empty_page_yields_nothing(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        try:
            self.assertEqual(detect_diagrams(page, render(page)), [])
        finally:
            doc.close()


def tiled_board(side: int = 320, *, rows: int = 2, cols: int = 2) -> list[tuple[np.ndarray, tuple[int, int]]]:
    """Um tabuleiro partido em ladrilhos, com a posição de cada pedaço.

    É a forma do `GALLAGHER`: o PDF traz a página digitalizada mais um punhado de remendos
    pequenos sobrepostos, e cada remendo é um XObject de imagem próprio.
    """
    board = board_image(side)
    alturas = [side // rows] * rows
    larguras = [side // cols] * cols
    alturas[-1] += side - sum(alturas)
    larguras[-1] += side - sum(larguras)

    pedacos: list[tuple[np.ndarray, tuple[int, int]]] = []
    y = 0
    for altura in alturas:
        x = 0
        for largura in larguras:
            pedacos.append((board[y : y + altura, x : x + largura].copy(), (x, y)))
            x += largura
        y += altura
    return pedacos


class MergeTilesTests(unittest.TestCase):
    """S-81: a imagem embutida que é **pedaço** de diagrama, e não diagrama.

    No `GALLAGHER` o caminho embutido entregava 33 fragmentos contra 7 imagens de verdade em
    192 páginas. Nenhum piso de tamanho os separa: eles vão a 106,5 pt e o menor diagrama real
    do acervo tem 105,6 pt. O que os distingue é adjacência.
    """

    def _pdf_com_ladrilhos(self, origem: fitz.Rect, *, rows: int = 2, cols: int = 2) -> fitz.Document:
        lado = int(origem.width)
        colocacoes = []
        for pedaco, (x, y) in tiled_board(lado, rows=rows, cols=cols):
            altura, largura = pedaco.shape[:2]
            destino = fitz.Rect(origem.x0 + x, origem.y0 + y, origem.x0 + x + largura, origem.y0 + y + altura)
            colocacoes.append((pedaco, destino))
        return pdf_with_images(colocacoes)

    def test_quatro_ladrilhos_encostados_viram_um_candidato(self) -> None:
        doc = self._pdf_com_ladrilhos(fitz.Rect(80, 100, 380, 400))
        try:
            candidatos = candidates_from_embedded_images(doc[0])

            self.assertEqual(len(candidatos), 1, "cada pedaco entrou como diagrama proprio")
            self.assertEqual(candidatos[0].merged_tiles, 4)
            x0, y0, x1, y1 = candidatos[0].bbox_pdf
            self.assertAlmostEqual(x1 - x0, 300, delta=4)
            self.assertAlmostEqual(y1 - y0, 300, delta=4)
        finally:
            doc.close()

    def test_diagramas_separados_na_mesma_pagina_nao_se_unem(self) -> None:
        """A guarda que protege o caso comum: os vãos do acervo são de 30 e 100 pt."""
        doc = pdf_with_images(
            [
                (board_image(320), fitz.Rect(60, 80, 280, 300)),
                (board_image(320), fitz.Rect(310, 80, 530, 300)),
                (board_image(320), fitz.Rect(60, 400, 280, 620)),
            ]
        )
        try:
            candidatos = candidates_from_embedded_images(doc[0])

            self.assertEqual(len(candidatos), 3)
            self.assertEqual([c.merged_tiles for c in candidatos], [0, 0, 0])
        finally:
            doc.close()

    def test_o_scan_de_fundo_nao_engole_a_pagina(self) -> None:
        """O `1937 Kemeri` tem scan de fundo **e** diagramas embutidos de verdade.

        O scan toca todas as outras imagens por definição. Se entrasse no agrupamento, a
        página inteira viraria um grupo só e os diagramas morreriam na cobertura.
        """
        doc = pdf_with_images(
            [
                (board_image(800), fitz.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT)),
                (board_image(400), fitz.Rect(80, 100, 380, 400)),
            ]
        )
        try:
            candidatos = candidates_from_embedded_images(doc[0])

            self.assertEqual(len(candidatos), 1)
            self.assertEqual(candidatos[0].merged_tiles, 0)
            self.assertAlmostEqual(candidatos[0].bbox_pdf[0], 80, delta=2)
        finally:
            doc.close()

    def test_moldura_feita_de_linhas_esticadas_nao_vira_diagrama(self) -> None:
        """O caso do `Polgar`: as bordas dos diagramas são imagens de **1×1 px** esticadas.

        Dezenove delas cercam cada diagrama e se encostam, então a união reproduz a moldura com
        precisão -- e seria tentador aceitá-la. Mas o retângulo carrega 19 pixels de imagem no
        total: não há o que ler ali, e o conteúdo está no scan da página, que é o que o
        contorno já lia. Aceitá-la trocava um recorte de 737 px por um render de 241 px nos
        114 diagramas do livro, com a nota de textura **subindo** -- o censo não mede resolução.
        """
        linha = np.full((1, 1, 3), 20, dtype=np.uint8)
        moldura = fitz.Rect(80, 100, 380, 400)
        colocacoes = [
            (linha, fitz.Rect(moldura.x0, moldura.y0, moldura.x1, moldura.y0 + 1)),
            (linha, fitz.Rect(moldura.x0, moldura.y1 - 1, moldura.x1, moldura.y1)),
            (linha, fitz.Rect(moldura.x0, moldura.y0, moldura.x0 + 1, moldura.y1)),
            (linha, fitz.Rect(moldura.x1 - 1, moldura.y0, moldura.x1, moldura.y1)),
        ]
        doc = pdf_with_images(colocacoes)
        try:
            self.assertEqual(candidates_from_embedded_images(doc[0]), [])
        finally:
            doc.close()

    def test_a_uniao_pode_ser_desligada(self) -> None:
        doc = self._pdf_com_ladrilhos(fitz.Rect(80, 100, 380, 400))
        try:
            self.assertEqual(len(candidates_from_embedded_images(doc[0], merge_tiles=False)), 4)
        finally:
            doc.close()

    def test_a_uniao_sobrevive_ao_refino(self) -> None:
        """O `merged_tiles` some no refino e as duas regras que dependem dele calam.

        Foi o que aconteceu, e o sintoma foi confuso: as regras estavam escritas, os testes
        de unidade passavam, e no livro real nada mudava.
        """
        doc = self._pdf_com_ladrilhos(fitz.Rect(80, 100, 380, 400))
        try:
            page = doc[0]
            candidato = candidates_from_embedded_images(page)[0]
            self.assertEqual(refine_candidate_with_contour(page, candidato).merged_tiles, 4)
        finally:
            doc.close()


class MergedVersusContourTests(unittest.TestCase):
    """A união é inferência nossa, não declaração do PDF -- então ela não tem precedência.

    Medido no `GALLAGHER`: nas páginas 168 e 169 a união produzia caixas de 91 pt com textura
    0,34 e 0,11 que suprimiam achados de contorno de 120 pt com textura 0,74 e 0,69. Na 169
    uma união engolia **dois** diagramas bons.
    """

    def _uniao(self, board: np.ndarray, bbox: tuple[float, float, float, float]) -> DiagramCandidate:
        return DiagramCandidate(
            board_rgb=board,
            bbox_pdf=bbox,
            source="embedded",
            detector_score=0.7,
            native_size=(board.shape[1], board.shape[0]),
            merged_tiles=3,
        )

    def test_imagem_declarada_nunca_perde_para_o_contorno(self) -> None:
        """A regra da S-12 continua: declaração ganha de inferência sobre pixels."""
        declarada = DiagramCandidate(
            board_rgb=np.full((320, 320, 3), 255, dtype=np.uint8),
            bbox_pdf=(80.0, 100.0, 380.0, 400.0),
            source="embedded",
            detector_score=0.7,
            native_size=(320, 320),
        )
        self.assertFalse(_contour_wins_over_merged(declarada, board_image(320)))

    def test_a_uniao_perde_quando_o_contorno_e_claramente_melhor(self) -> None:
        ruim = np.full((320, 320, 3), 250, dtype=np.uint8)
        cv2.putText(ruim, "texto", (10, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

        self.assertTrue(_contour_wins_over_merged(self._uniao(ruim, (80.0, 100.0, 380.0, 400.0)), board_image(320)))

    def test_a_uniao_boa_nao_e_derrubada_por_ruido(self) -> None:
        """A margem existe para o empate: `board_texture_score` tem ruído de reamostragem."""
        board = board_image(320)

        self.assertFalse(_contour_wins_over_merged(self._uniao(board, (80.0, 100.0, 380.0, 400.0)), board.copy()))

    def test_contencao_conta_como_mesma_regiao_so_para_uniao(self) -> None:
        """Na p168 do `GALLAGHER` a união está 97% dentro do contorno e o IoU dá 0,41.

        IoU pergunta "as duas caixas são a mesma?"; aqui a pergunta é "uma está dentro da
        outra?", que é razão sobre a menor.
        """
        contorno = (181, 555, 368, 368)
        uniao = (324, 642, 232, 281)

        self.assertLess(_bbox_iou(contorno, uniao), OVERLAP_IOU, "premissa: o IoU nao ve isto")
        self.assertTrue(_same_region(contorno, uniao, merged=True))
        self.assertFalse(_same_region(contorno, uniao, merged=False), "declarada nao usa contencao")


class TypicalSideTests(unittest.TestCase):
    """S-79: o gabarito de tamanho da página, que era `np.median` e não podia ser.

    Mediana é robusta a *outlier* e não a **bimodalidade**. Com duas populações de tamanho ela
    devolve um número que não é o tamanho de nada que exista na página, e o prior passa a
    recusar exatamente o diagrama que ele existe para recuperar.
    """

    def test_a_lista_vazia_nao_tem_gabarito(self) -> None:
        self.assertIsNone(_typical_side([], EMBEDDED_SIZE_TOLERANCE))

    def test_um_candidato_so_e_o_proprio_gabarito(self) -> None:
        self.assertEqual(_typical_side([150.0], EMBEDDED_SIZE_TOLERANCE), 150.0)

    def test_tamanhos_parecidos_seguem_dando_o_de_sempre(self) -> None:
        """O caso comum não pode mudar: é a página de diagramas todos iguais."""
        self.assertAlmostEqual(_typical_side([148.0, 150.0, 152.0], EMBEDDED_SIZE_TOLERANCE), 150.0)

    def test_o_glifo_nao_arrasta_o_gabarito_para_o_vazio(self) -> None:
        """O defeito medido: glifo de 15 pt com diagrama de 154 pt dava mediana ~85 pt.

        85 pt não é o tamanho de nada naquela página, e com tolerância de 30% a janela aceita
        vira 59--110 pt -- todo achado de contorno do tamanho real seria recusado.
        """
        gabarito = _typical_side([15.4, 153.6], EMBEDDED_SIZE_TOLERANCE)

        self.assertIsNotNone(gabarito)
        assert gabarito is not None
        self.assertAlmostEqual(gabarito, 153.6, delta=1.0)
        self.assertNotAlmostEqual(gabarito, 84.5, delta=10.0, msg="voltou a ser a mediana")

    def test_o_maior_grupo_ganha_e_nao_o_maior_valor(self) -> None:
        """Três diagramas de 150 e uma capa de capítulo de 400: o gabarito é 150."""
        gabarito = _typical_side([150.0, 151.0, 149.0, 400.0], EMBEDDED_SIZE_TOLERANCE)

        self.assertIsNotNone(gabarito)
        assert gabarito is not None
        self.assertAlmostEqual(gabarito, 150.0, delta=2.0)

    def test_empate_de_tamanho_de_grupo_resolve_pelo_maior(self) -> None:
        """Na dúvida o maior: diagrama pequeno demais é o que as outras guardas já barram."""
        gabarito = _typical_side([40.0, 41.0, 300.0, 305.0], EMBEDDED_SIZE_TOLERANCE)

        self.assertIsNotNone(gabarito)
        assert gabarito is not None
        self.assertGreater(gabarito, 200.0)

    def test_o_contorno_do_tamanho_certo_sobrevive_ao_glifo_na_pagina(self) -> None:
        """O dano de ponta a ponta: um diagrama achado só pelo contorno, numa página com glifo.

        Antes da S-79 o gabarito envenenado o recusava por tamanho. É o efeito silencioso --
        o diagrama simplesmente não aparecia, sem erro e sem log.
        """
        pixels_por_pt = 220 / 72
        lados = [200.0, 15.0]
        gabarito = _typical_side([lado * pixels_por_pt for lado in lados], EMBEDDED_SIZE_TOLERANCE)

        self.assertIsNotNone(gabarito)
        assert gabarito is not None
        achado = 200.0 * pixels_por_pt
        self.assertLessEqual(
            abs(achado - gabarito),
            gabarito * EMBEDDED_SIZE_TOLERANCE,
            "o achado de contorno do tamanho do diagrama caiu fora da janela",
        )


class RefineGuardTests(unittest.TestCase):
    """S-38: o refino do contorno não pode entregar um recorte pior que o cru.

    Até aqui `refine_candidate_with_contour` conferia se o contorno tinha achado *alguma
    coisa*, nunca se o que achou era *melhor*. Medido na página 80 do `Karpov 1`: o bbox
    embutido do candidato #4 contém um diagrama impecável e o refino o trocava por um
    trapézio de texto, que o modelo lia como oito reis brancos com confiança 0,0004.
    """

    def _candidato(self, doc: fitz.Document, rect: fitz.Rect, board: np.ndarray) -> DiagramCandidate:
        return DiagramCandidate(
            board_rgb=board,
            bbox_pdf=(rect.x0, rect.y0, rect.x1, rect.y1),
            source="embedded",
            detector_score=0.7,
            native_size=(board.shape[1], board.shape[0]),
        )

    def test_um_recorte_pior_e_recusado_e_o_cru_fica(self) -> None:
        rect = fitz.Rect(80, 100, 380, 400)
        doc = pdf_with_images([(board_image(400), rect)])
        try:
            page = doc[0]
            cru = self._candidato(doc, rect, board_image(400))
            pior = np.full((320, 320, 3), 255, dtype=np.uint8)  # sem grade, sem xadrez

            with mock.patch(
                "chess_diagram_ocr.detection.hybrid.detect_boards", return_value=[(pior, None)]
            ):
                resultado = refine_candidate_with_contour(page, cru)

            self.assertIs(resultado, cru, "o refino piorou o recorte e mesmo assim foi aceito")
            self.assertFalse(resultado.trimmed)
        finally:
            doc.close()

    def test_um_recorte_melhor_e_aceito(self) -> None:
        """A guarda não pode virar "nunca refina": alinhar a grade é o ganho da S-12.

        **A página precisa de moldura e de margem (S-160), e nenhuma das duas é enfeite.** Com
        `board_image(400)` o tabuleiro ocupava a região inteira e não tinha linha em volta:
        o contorno não achava retângulo nenhum e sobravam os contornos das casas *internas*.
        O "refino" que este teste dava por aceito era **uma casa de 49×49 px substituindo um
        tabuleiro de 400** -- ele nunca verificou o que o nome dele diz. Uma casa sozinha não
        tem paridade, logo tem contraste de casa zero, e foi o piso da S-143 que expôs isso ao
        recusá-la: o refino passou a devolver o recorte cru, que é a resposta certa e é a
        mesma regra que a S-38 já aplicava ao caso "não achou nada".

        Com moldura e margem o contorno acha o tabuleiro inteiro -- 311×312 px de um lado de
        320, contraste 1,00 --, e o refino sobe a textura de 0,0000 para 1,0000. Medido no
        acervo: dos 284 candidatos embutidos de quatro livros, 283 refinam igual com e sem o
        piso, e o único que muda melhora (0,089 para 0,137 de contraste).
        """
        rect = fitz.Rect(80, 100, 380, 400)
        doc = pdf_with_images([(board_image(320, border=40, frame=True), rect)])
        try:
            page = doc[0]
            # Cru desalinhado (com moldura larga), refinado alinhado: e o caso que a S-12 mede.
            cru = self._candidato(doc, rect, board_image(240, border=80))
            melhor = board_image(320)

            resultado = refine_candidate_with_contour(page, cru)
            self.assertTrue(resultado.trimmed, "o refino que melhora tem de ser aceito")
            self.assertGreater(
                board_texture_score(resultado.board_rgb),
                board_texture_score(cru.board_rgb) - REFINE_TOLERANCE,
            )
            self.assertGreater(board_texture_score(melhor), 0.0)
        finally:
            doc.close()

    def test_uma_piora_dentro_da_tolerancia_passa(self) -> None:
        """Ruído de reamostragem entre dois recortes igualmente bons não é motivo de recusa."""
        rect = fitz.Rect(80, 100, 380, 400)
        doc = pdf_with_images([(board_image(400), rect)])
        try:
            page = doc[0]
            cru = self._candidato(doc, rect, board_image(400))
            quase_igual = board_image(400)

            with mock.patch(
                "chess_diagram_ocr.detection.hybrid.detect_boards", return_value=[(quase_igual, None)]
            ):
                resultado = refine_candidate_with_contour(page, cru)

            self.assertTrue(resultado.trimmed)
        finally:
            doc.close()

    def test_sem_achado_continua_devolvendo_o_cru(self) -> None:
        """O comportamento que já existia não pode ter mudado."""
        rect = fitz.Rect(80, 100, 380, 400)
        doc = pdf_with_images([(board_image(400), rect)])
        try:
            page = doc[0]
            cru = self._candidato(doc, rect, board_image(400))
            with mock.patch("chess_diagram_ocr.detection.hybrid.detect_boards", return_value=[]):
                self.assertIs(refine_candidate_with_contour(page, cru), cru)
        finally:
            doc.close()

    def test_a_textura_e_medida_na_resolucao_em_que_foi_calibrada(self) -> None:
        """Comparar recortes de tamanhos diferentes compararia números incomparáveis."""
        grande = board_texture_score(board_image(800))
        pequeno = board_texture_score(board_image(160))
        self.assertAlmostEqual(grande, pequeno, delta=0.15)


def photo_like(side: int = 320, *, seed: int = 7) -> np.ndarray:
    """Um quadrado de tom contínuo: o retrato, a foto, a moldura -- nada de reticulado 8×8.

    Feito de manchas suaves e não de ruído branco porque é assim que a foto impressa se
    comporta: bordas longas e periódicas (a moldura), gradiente no meio, e **nenhuma**
    diferença sistemática entre as 32 casas de uma paridade e as 32 da outra.
    """
    rng = np.random.default_rng(seed)
    campo = rng.random((side // 8, side // 8)).astype(np.float32)
    campo = cv2.resize(campo, (side, side), interpolation=cv2.INTER_CUBIC)
    campo = cv2.GaussianBlur(campo, (0, 0), side / 24.0)
    campo -= campo.min()
    campo /= max(float(campo.max()), 1e-6)
    cinza = (40 + campo * 180).astype(np.uint8)
    imagem = cv2.cvtColor(cinza, cv2.COLOR_GRAY2RGB)
    cv2.rectangle(imagem, (2, 2), (side - 3, side - 3), (20, 20, 20), 3)
    return imagem


def crowded_board(side: int = 320) -> np.ndarray:
    """Tabuleiro com peça em quase toda casa -- o caso `Polgar` que reprovou a S-80.

    A S-80 morreu porque `board_texture_score` mistura "isto é um tabuleiro" com "quantas
    peças há": uma posição de abertura de 28 peças tira 0,158 e um final de dois reis tira
    0,8, **no mesmo livro e na mesma página**. Esta fixture é o lado ruim dessa faixa.
    """
    board = board_image(side)
    cell = side // 8
    for row in range(8):
        for column in range(8):
            if row in (2, 3, 4, 5) and (row + column) % 3:
                continue
            centro = (int((column + 0.5) * cell), int((row + 0.5) * cell))
            cv2.circle(board, centro, int(cell * 0.34), (25, 25, 25), -1)
    return board


class CheckerContrastGuardTests(unittest.TestCase):
    """O achado de contorno sem contraste de casa não é diagrama (S-143).

    Capa e prancha de retrato do `Karpov 1` rendiam 10 caixas onde não há diagrama: o título,
    a grade de fotos, cada retrato, e três casas do tabuleiro **pintado ao fundo do quadro**.
    """

    def _pagina_com(self, imagem: np.ndarray, rect: fitz.Rect) -> fitz.Document:
        return pdf_with_images([(imagem, rect)])

    def test_a_foto_quadrada_nao_e_diagrama(self) -> None:
        doc = self._pagina_com(photo_like(400), fitz.Rect(120, 160, 420, 460))
        try:
            page = doc[0]
            contorno = [c for c in detect_diagrams(page, render(page)) if c.source == "contour"]
            self.assertEqual(contorno, [], "retrato de tom contínuo não pode virar diagrama")
        finally:
            doc.close()

    def test_o_tabuleiro_de_verdade_continua_passando(self) -> None:
        """A guarda não pode custar o caminho que é a maioria do acervo."""
        doc = fitz.open()
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        cell, ox, oy = 30.0, 100.0, 150.0
        for row in range(8):
            for column in range(8):
                if (row + column) % 2:
                    page.draw_rect(
                        fitz.Rect(ox + column * cell, oy + row * cell, ox + (column + 1) * cell, oy + (row + 1) * cell),
                        color=None,
                        fill=(0.18, 0.18, 0.18),
                    )
        page.draw_rect(fitz.Rect(ox, oy, ox + 8 * cell, oy + 8 * cell), color=(0, 0, 0), width=1)
        try:
            contorno = [c for c in detect_diagrams(page, render(page)) if c.source == "contour"]
            self.assertTrue(contorno, "o diagrama vetorial tem de sobreviver à guarda")
        finally:
            doc.close()

    def test_tabuleiro_cheio_de_pecas_sobrevive(self) -> None:
        """O caso que reprovou a S-80: peça cobrindo casa derruba a nota, mas não a zera.

        É a razão de a guarda olhar **só** a parcela de xadrez e cortar em zero, e não a
        textura combinada num piso qualquer -- ali o `Polgar` tira 0,158 e uma foto tira 0,29.
        """
        self.assertGreater(board_checker_contrast(crowded_board()), 0.0)

    def test_a_parcela_de_grade_sozinha_nao_separaria(self) -> None:
        """Por que a guarda não usa a textura combinada, encravado em teste.

        Moldura e faixa de fotos produzem borda periódica, que é o que a parcela de **grade**
        mede -- medido nas páginas do relato, as fotos tiram 0,04 a 0,80 nela. É essa parcela
        que, misturada 0,4 na textura, deixou a S-80 medir uma foto acima de um diagrama bom.
        """
        foto = cv2.resize(photo_like(320), (320, 320), interpolation=cv2.INTER_AREA)
        self.assertEqual(board_checker_contrast(foto), 0.0, "a foto não tem contraste de casa")
        self.assertGreater(
            _grid_score(_small_gray(foto)),
            0.0,
            "a foto TEM borda periódica -- é por isso que a grade não serve de guarda",
        )

    def test_a_declaracao_do_pdf_nao_e_alcancada(self) -> None:
        """Imagem embutida continua ganhando (S-12): ela tem as guardas dela."""
        rect = fitz.Rect(120, 160, 420, 460)
        doc = self._pagina_com(photo_like(400), rect)
        try:
            page = doc[0]
            embutidos = [c for c in detect_diagrams(page, render(page)) if c.source == "embedded"]
            self.assertTrue(embutidos, "a guarda da S-143 é só do caminho de contorno")
        finally:
            doc.close()

    def test_a_guarda_pode_ser_desligada(self) -> None:
        # 100 px nativos reprovam em `MIN_EMBEDDED_SIDE`, entao a fonte embutida nao declara
        # nada e o contorno fica sendo a unica -- que e o caso das paginas do relato.
        doc = self._pagina_com(photo_like(100), fitz.Rect(120, 160, 420, 460))
        try:
            page = doc[0]
            pagina = render(page)
            self.assertEqual(candidates_from_embedded_images(page), [])
            com = detect_diagrams(page, pagina)
            sem = detect_diagrams(page, pagina, checker_contrast_floor=None)
            self.assertEqual(com, [])
            self.assertTrue(sem, "None tem de reproduzir o comportamento anterior à S-143")
        finally:
            doc.close()

    def test_o_contraste_e_medido_na_resolucao_calibrada(self) -> None:
        """Mesmo motivo de `board_texture_score`: dois tamanhos, um número comparável."""
        grande = board_checker_contrast(board_image(800))
        pequeno = board_checker_contrast(board_image(160))
        self.assertAlmostEqual(grande, pequeno, delta=0.15)


if __name__ == "__main__":
    unittest.main()
