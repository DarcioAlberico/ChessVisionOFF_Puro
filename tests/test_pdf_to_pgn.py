from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.inference import prediction_from_probs
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, build_pgn_text, save_pdf_positions_to_pgn, scan_pdf_positions

EMPTY_BOARD = "8/8/8/8/8/8/8/8"
KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"
KINGS_D1_D3 = "8/8/8/8/8/3k4/8/3K4"


def prediction_for(fen: str, confidence: float):
    """`BoardPrediction` real para uma FEN, com todas as casas na mesma confiança.

    Usar o objeto de verdade em vez de um duplo garante que a S-10 continue conectada
    ponta a ponta: se `predict_board` mudar de forma, estes testes quebram.
    """
    return prediction_from_probs(probs_for_fen(fen, confidence))


class PdfToPgnTests(unittest.TestCase):
    def test_build_pgn_text_creates_one_game_per_position(self) -> None:
        positions = [
            DiagramPosition(page_index=0, diagram_index=1, fen=EMPTY_BOARD, confidence=0.91),
            DiagramPosition(page_index=2, diagram_index=2, fen=KINGS_ONLY, confidence=0.83),
        ]

        payload = build_pgn_text(positions, source_name="book.pdf")

        self.assertIn('[SourcePDF "book.pdf"]', payload)
        self.assertIn('[Page "1"]', payload)
        self.assertIn('[Diagram "1"]', payload)
        self.assertIn('[OCRConfidence "0.910"]', payload)
        self.assertIn('[Round "3.2"]', payload)
        self.assertEqual(payload.count('[SetUp "1"]'), 2)
        self.assertEqual(payload.count('[Result "*"]'), 2)

    def test_headers_omit_unmeasured_fields(self) -> None:
        """Posição montada à mão não afirma legalidade nem confiança mínima."""
        payload = build_pgn_text(
            [DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.91)],
            source_name="book.pdf",
        )

        self.assertNotIn("OCRMinConfidence", payload)
        self.assertNotIn("OCRLegal", payload)

    def test_headers_carry_min_confidence_and_legality(self) -> None:
        positions = [
            DiagramPosition(
                page_index=0,
                diagram_index=1,
                fen=EMPTY_BOARD,
                confidence=0.97,
                min_confidence=0.42,
                is_legal=False,
                problems=("tabuleiro vazio",),
            ),
            DiagramPosition(
                page_index=0,
                diagram_index=2,
                fen=KINGS_ONLY,
                confidence=0.99,
                min_confidence=0.95,
                is_legal=True,
            ),
        ]

        payload = build_pgn_text(positions, source_name="book.pdf")

        self.assertIn('[OCRMinConfidence "0.420"]', payload)
        self.assertIn('[OCRLegal "0"]', payload)
        self.assertIn('[OCRProblems "tabuleiro vazio"]', payload)
        self.assertIn('[OCRMinConfidence "0.950"]', payload)
        self.assertIn('[OCRLegal "1"]', payload)
        # Posicao legal nao carrega lista de problemas vazia.
        self.assertEqual(payload.count("OCRProblems"), 1)

    @patch("chess_diagram_ocr.pdf_to_pgn.predict_board")
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
        mock_predict_board,
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
        mock_predict_board.side_effect = [
            prediction_for(EMPTY_BOARD, 0.90),
            prediction_for(KINGS_ONLY, 0.80),
            prediction_for(KINGS_D1_D3, 0.70),
        ]

        positions = scan_pdf_positions(Path("sample.pdf"))

        self.assertEqual(
            [(p.page_index, p.diagram_index, p.fen) for p in positions],
            [(0, 1, EMPTY_BOARD), (0, 2, KINGS_ONLY), (2, 1, KINGS_D1_D3)],
        )
        for position, expected_confidence in zip(positions, (0.90, 0.80, 0.70), strict=True):
            self.assertAlmostEqual(position.confidence, expected_confidence, places=6)
            # Todas as casas com a mesma confianca: minimo e media coincidem.
            self.assertAlmostEqual(position.min_confidence, expected_confidence, places=6)

        # A legalidade acompanha a posicao, e nao um valor fixo: tabuleiro vazio e ilegal.
        self.assertEqual([p.is_legal for p in positions], [False, True, True])
        self.assertIn("tabuleiro vazio", positions[0].problems)
        self.assertEqual(positions[1].problems, ())

        self.assertEqual(mock_render_pdf_page.call_count, 3)
        self.assertEqual(mock_detect_boards.call_count, 3)
        self.assertTrue(all(call.kwargs.get("reading_order") == "column" for call in mock_detect_boards.call_args_list))
        self.assertEqual(mock_predict_board.call_count, 3)

    @patch("chess_diagram_ocr.pdf_to_pgn.predict_board")
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
        mock_predict_board,
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
        mock_predict_board.return_value = prediction_for(EMPTY_BOARD, 0.9)
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
