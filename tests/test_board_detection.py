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
from chess_diagram_ocr.config import DEFAULT_READING_ORDER
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
        # Depende de data/samples/, que nao e versionado (ver .gitignore). Enquanto nao
        # houver fixtures proprios no repositorio (S-09), o teste pula fora do ambiente local.
        # sorted() torna a escolha deterministica, em vez de depender da ordem do sistema de arquivos.
        sample_path = next(iter(sorted((ROOT / "data" / "samples").glob("*.png"))), None)
        if sample_path is None:
            self.skipTest("Nenhuma amostra em data/samples/. Fixtures versionados: ver S-09 em docs/SPEC.md.")

        image_bgr = cv2.imread(str(sample_path))
        self.assertIsNotNone(image_bgr, f"Falha ao abrir sample: {sample_path}")
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
