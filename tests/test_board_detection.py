from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
