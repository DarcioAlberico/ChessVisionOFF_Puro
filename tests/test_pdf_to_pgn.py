from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, build_pgn_text, save_pdf_positions_to_pgn, scan_pdf_positions


class PdfToPgnTests(unittest.TestCase):
    def test_build_pgn_text_creates_one_game_per_position(self) -> None:
        positions = [
            DiagramPosition(page_index=0, diagram_index=1, fen="8/8/8/8/8/8/8/8", confidence=0.91),
            DiagramPosition(page_index=2, diagram_index=2, fen="4k3/8/8/8/8/8/8/4K3", confidence=0.83),
        ]

        payload = build_pgn_text(positions, source_name="book.pdf")

        self.assertIn('[SourcePDF "book.pdf"]', payload)
        self.assertIn('[Page "1"]', payload)
        self.assertIn('[Diagram "1"]', payload)
        self.assertIn('[OCRConfidence "0.910"]', payload)
        self.assertIn('[Round "3.2"]', payload)
        self.assertEqual(payload.count("[SetUp \"1\"]"), 2)
        self.assertEqual(payload.count("[Result \"*\"]"), 2)

    @patch("chess_diagram_ocr.pdf_to_pgn.predict_fen_from_board")
    @patch("chess_diagram_ocr.pdf_to_pgn.detect_boards")
    @patch("chess_diagram_ocr.pdf_to_pgn._render_pdf_page")
    @patch("chess_diagram_ocr.pdf_to_pgn.load_model")
    @patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count")
    def test_scan_pdf_positions_walks_all_pages(
        self,
        mock_get_pdf_page_count,
        mock_load_model,
        mock_render_pdf_page,
        mock_detect_boards,
        mock_predict_fen_from_board,
    ) -> None:
        mock_get_pdf_page_count.return_value = 3
        mock_load_model.return_value = ("model", "cpu")
        mock_render_pdf_page.side_effect = [
            np.zeros((10, 10, 3), dtype=np.uint8),
            np.zeros((10, 10, 3), dtype=np.uint8),
            np.zeros((10, 10, 3), dtype=np.uint8),
        ]
        board_rgb = np.zeros((800, 800, 3), dtype=np.uint8)
        mock_detect_boards.side_effect = [
            [(board_rgb, None), (board_rgb, None)],
            [],
            [(board_rgb, None)],
        ]
        mock_predict_fen_from_board.side_effect = [
            ("8/8/8/8/8/8/8/8", 0.90),
            ("4k3/8/8/8/8/8/8/4K3", 0.80),
            ("8/8/8/8/8/3k4/8/3K4", 0.70),
        ]

        positions = scan_pdf_positions(Path("sample.pdf"))

        self.assertEqual(
            positions,
            [
                DiagramPosition(page_index=0, diagram_index=1, fen="8/8/8/8/8/8/8/8", confidence=0.90),
                DiagramPosition(page_index=0, diagram_index=2, fen="4k3/8/8/8/8/8/8/4K3", confidence=0.80),
                DiagramPosition(page_index=2, diagram_index=1, fen="8/8/8/8/8/3k4/8/3K4", confidence=0.70),
            ],
        )
        self.assertEqual(mock_render_pdf_page.call_count, 3)
        self.assertEqual(mock_detect_boards.call_count, 3)
        self.assertTrue(all(call.kwargs.get("reading_order") == "column" for call in mock_detect_boards.call_args_list))
        self.assertEqual(mock_predict_fen_from_board.call_count, 3)

    @patch("chess_diagram_ocr.pdf_to_pgn.predict_fen_from_board")
    @patch("chess_diagram_ocr.pdf_to_pgn.detect_boards")
    @patch("chess_diagram_ocr.pdf_to_pgn._render_pdf_page")
    @patch("chess_diagram_ocr.pdf_to_pgn.load_model")
    @patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count")
    def test_scan_pdf_positions_reports_progress(
        self,
        mock_get_pdf_page_count,
        mock_load_model,
        mock_render_pdf_page,
        mock_detect_boards,
        mock_predict_fen_from_board,
    ) -> None:
        mock_get_pdf_page_count.return_value = 2
        mock_load_model.return_value = ("model", "cpu")
        mock_render_pdf_page.side_effect = [
            np.zeros((10, 10, 3), dtype=np.uint8),
            np.zeros((10, 10, 3), dtype=np.uint8),
        ]
        board_rgb = np.zeros((800, 800, 3), dtype=np.uint8)
        mock_detect_boards.side_effect = [
            [(board_rgb, None)],
            [],
        ]
        mock_predict_fen_from_board.return_value = ("8/8/8/8/8/8/8/8", 0.9)
        progress_calls: list[tuple[int, int, int, int]] = []

        scan_pdf_positions(
            Path("sample.pdf"),
            progress_callback=lambda page_index, total_pages, page_boards, total_positions: progress_calls.append(
                (page_index, total_pages, page_boards, total_positions)
            ),
        )

        self.assertEqual(progress_calls, [(0, 2, 1, 1), (1, 2, 0, 1)])

    @patch("chess_diagram_ocr.pdf_to_pgn.scan_pdf_positions")
    def test_save_pdf_positions_to_pgn_writes_output_file(self, mock_scan_pdf_positions) -> None:
        mock_scan_pdf_positions.return_value = [
            DiagramPosition(page_index=0, diagram_index=1, fen="8/8/8/8/8/8/8/8", confidence=0.95)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.pgn"
            positions = save_pdf_positions_to_pgn(
                pdf_source=Path("PDF") / "book.pdf",
                output_path=output_path,
            )

            self.assertEqual(len(positions), 1)
            self.assertTrue(output_path.exists())
            payload = output_path.read_text(encoding="utf-8")
            self.assertIn('[SourcePDF "book.pdf"]', payload)
            self.assertIn('[FEN "8/8/8/8/8/8/8/8 w - - 0 1"]', payload)


if __name__ == "__main__":
    unittest.main()
