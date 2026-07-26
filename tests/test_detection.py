from __future__ import annotations

import unittest

import cv2
import fitz
import numpy as np

from chess_diagram_ocr.detection import (
    candidates_from_embedded_images,
    detect_diagrams,
    trim_to_grid,
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


if __name__ == "__main__":
    unittest.main()
