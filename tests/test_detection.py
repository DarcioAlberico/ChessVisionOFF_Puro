from __future__ import annotations

import unittest
from unittest import mock

import cv2
import fitz
import numpy as np

from chess_diagram_ocr.detection import (
    DiagramCandidate,
    candidates_from_embedded_images,
    detect_diagrams,
    trim_to_frame,
    trim_to_grid,
)
from chess_diagram_ocr.detection.hybrid import (
    REFINE_TOLERANCE,
    board_texture_score,
    refine_candidate_with_contour,
)

# Uma pagina A4 em pontos.
PAGE_WIDTH, PAGE_HEIGHT = 595.0, 842.0


def board_image(side: int = 320, *, border: int = 0) -> np.ndarray:
    """Imagem de tabuleiro 8x8 com casas alternadas e, opcionalmente, moldura branca."""
    cell = side // 8
    board = np.full((side, side, 3), 245, dtype=np.uint8)
    for row in range(8):
        for column in range(8):
            if (row + column) % 2:
                board[row * cell : (row + 1) * cell, column * cell : (column + 1) * cell] = 45
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
        """A guarda não pode virar "nunca refina": alinhar a grade é o ganho da S-12."""
        rect = fitz.Rect(80, 100, 380, 400)
        doc = pdf_with_images([(board_image(400), rect)])
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


if __name__ == "__main__":
    unittest.main()
