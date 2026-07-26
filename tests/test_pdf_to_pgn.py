from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.inference import prediction_from_probs
from chess_diagram_ocr.pdf_to_pgn import (
    DiagramPosition,
    build_pgn_text,
    classify_position,
    partition_positions,
    save_pdf_positions_to_pgn,
    scan_pdf_positions,
    write_gated_pgn,
)

EMPTY_BOARD = "8/8/8/8/8/8/8/8"
KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"
KINGS_D1_D3 = "8/8/8/8/8/3k4/8/3K4"

# Pretas em xeque. O export assume "brancas jogam", então a FEN completa fica ilegal --
# mas o tabuleiro está perfeito: é o palpite de lado a jogar que está errado (S-17).
BLACK_IN_CHECK = "4k3/8/8/8/8/8/8/4KR2"


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
        self.assertEqual(payload.count("[SetUp \"1\"]"), 2)
        self.assertEqual(payload.count("[Result \"*\"]"), 2)

    def test_headers_record_the_reading_order(self) -> None:
        """S-14: `[Diagram "2"]` só é conferível se o PGN disser como a página foi numerada."""
        positions = [DiagramPosition(page_index=0, diagram_index=2, fen=KINGS_ONLY, confidence=0.9)]

        self.assertIn('[ReadingOrder "column"]', build_pgn_text(positions, source_name="book.pdf"))
        self.assertIn(
            '[ReadingOrder "row"]',
            build_pgn_text(positions, source_name="book.pdf", reading_order="row"),
        )

    def test_headers_omit_unmeasured_fields(self) -> None:
        """Posição montada à mão não afirma legalidade nem confiança mínima."""
        payload = build_pgn_text(
            [DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.91)],
            source_name="book.pdf",
        )

        self.assertNotIn("OCRMinConfidence", payload)
        self.assertNotIn("OCRLegality", payload)

    def test_headers_carry_min_confidence_and_legality(self) -> None:
        positions = [
            DiagramPosition(
                page_index=0,
                diagram_index=1,
                fen=EMPTY_BOARD,
                confidence=0.97,
                min_confidence=0.42,
                is_legal=False,
                is_fatal=True,
                problems=("tabuleiro vazio",),
            ),
            DiagramPosition(
                page_index=0,
                diagram_index=2,
                fen=KINGS_ONLY,
                confidence=0.99,
                min_confidence=0.95,
                is_legal=True,
                is_fatal=False,
            ),
        ]

        payload = build_pgn_text(positions, source_name="book.pdf")

        self.assertIn('[OCRMinConfidence "0.420"]', payload)
        self.assertIn('[OCRLegality "ilegal"]', payload)
        self.assertIn('[OCRProblems "tabuleiro vazio"]', payload)
        self.assertIn('[OCRMinConfidence "0.950"]', payload)
        self.assertIn('[OCRLegality "legal"]', payload)
        # Posicao legal nao carrega lista de problemas vazia.
        self.assertEqual(payload.count("OCRProblems"), 1)

    def test_side_to_move_case_is_not_labelled_illegal(self) -> None:
        """Tabuleiro bom, palpite de lado a jogar ruim: o PGN precisa dizer qual dos dois."""
        payload = build_pgn_text(
            [
                DiagramPosition(
                    page_index=0,
                    diagram_index=1,
                    fen=BLACK_IN_CHECK,
                    confidence=0.99,
                    min_confidence=0.98,
                    is_legal=False,
                    is_fatal=False,
                    problems=("o lado que não joga está em xeque",),
                )
            ],
            source_name="book.pdf",
        )

        self.assertIn('[OCRLegality "lado-a-jogar"]', payload)
        self.assertNotIn('"ilegal"', payload)

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
        # E `is_fatal` chega junto: sem ele o gate nao distingue erro de leitura de palpite
        # errado de lado a jogar.
        self.assertEqual([p.is_fatal for p in positions], [True, False, False])
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
            DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.95)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.pgn"
            report = save_pdf_positions_to_pgn(
                pdf_source=Path("PDF") / "book.pdf",
                output_path=output_path,
            )

            self.assertEqual(len(report.accepted), 1)
            self.assertTrue(output_path.exists())
            payload = output_path.read_text(encoding="utf-8")
            self.assertIn('[SourcePDF "book.pdf"]', payload)
            self.assertIn(f'[FEN "{KINGS_ONLY} w - - 0 1"]', payload)


class ExportGateTests(unittest.TestCase):
    """S-15: o PGN principal sai limpo e nada desaparece em silencio."""

    def positions(self) -> list[DiagramPosition]:
        return [
            # Legal e confiante -> PGN principal.
            DiagramPosition(
                page_index=0,
                diagram_index=1,
                fen=KINGS_ONLY,
                confidence=0.99,
                min_confidence=0.97,
                is_legal=True,
                is_fatal=False,
            ),
            # Legal, mas com uma casa insegura -> revisao.
            DiagramPosition(
                page_index=1,
                diagram_index=1,
                fen=KINGS_D1_D3,
                confidence=0.98,
                min_confidence=0.42,
                is_legal=True,
                is_fatal=False,
            ),
            # Ilegal -> rejeitada, fora do PGN principal.
            DiagramPosition(
                page_index=2,
                diagram_index=1,
                fen=EMPTY_BOARD,
                confidence=0.99,
                min_confidence=0.99,
                is_legal=False,
                is_fatal=True,
                problems=("tabuleiro vazio",),
            ),
        ]

    def test_classification_of_each_bucket(self) -> None:
        accepted, needs_review, rejected = partition_positions(self.positions())

        self.assertEqual([p.page_index for p in accepted], [0])
        self.assertEqual([p.page_index for p, _ in needs_review], [1])
        self.assertEqual([p.page_index for p, _ in rejected], [2])
        self.assertIn("0.420", needs_review[0][1])
        self.assertIn("tabuleiro vazio", rejected[0][1])

    def test_side_to_move_goes_to_review_and_not_to_the_bin(self) -> None:
        """O caso medido no 1937 Kemeri: 3 de 12 diagramas caem aqui.

        Rejeitar seria perder leitura boa; aceitar em silencio afirmaria um lado a jogar
        que ninguem verificou. Revisao com o motivo escrito e a unica resposta honesta.
        """
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=BLACK_IN_CHECK,
            confidence=0.99,
            min_confidence=0.98,
            is_legal=False,
            is_fatal=False,
            problems=("o lado que não joga está em xeque",),
        )

        verdict, reason = classify_position(position)

        self.assertEqual(verdict, "needs_review")
        self.assertIn("lado a jogar", reason)

    def test_unmeasured_position_is_not_condemned(self) -> None:
        """Sem `is_legal`/`min_confidence` medidos, nao ha o que alegar contra a posicao."""
        verdict, reason = classify_position(
            DiagramPosition(page_index=0, diagram_index=1, fen=KINGS_ONLY, confidence=0.5)
        )

        self.assertEqual(verdict, "accepted")
        self.assertEqual(reason, "")

    def test_threshold_zero_accepts_every_legal_position(self) -> None:
        accepted, needs_review, rejected = partition_positions(self.positions(), accept_threshold=0.0)

        self.assertEqual(len(accepted), 2)
        self.assertEqual(needs_review, [])
        # Ilegal continua ilegal: o limiar de confianca nao tem nada a dizer sobre regras.
        self.assertEqual(len(rejected), 1)

    def test_main_pgn_excludes_everything_that_needs_a_human(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "book.pgn"
            report = write_gated_pgn(self.positions(), output_path, source_name="book.pdf", pages_scanned=3)

            main_payload = output_path.read_text(encoding="utf-8")
            self.assertEqual(main_payload.count("[FEN "), 1)
            self.assertIn(KINGS_ONLY, main_payload)
            self.assertNotIn(EMPTY_BOARD, main_payload)
            self.assertNotIn("Review", main_payload)

            self.assertEqual(report.review_path, Path(tmpdir) / "book.review.pgn")
            review_payload = report.review_path.read_text(encoding="utf-8")
            self.assertEqual(review_payload.count("[FEN "), 2)
            # O motivo acompanha cada posicao separada -- sem ele o usuario adivinha.
            self.assertIn('[Review "confiança mínima 0.420 < 0.80"]', review_payload)
            self.assertIn('[Review "ilegal: tabuleiro vazio"]', review_payload)
            self.assertEqual(report.summary(), "1 aceitos, 1 para revisão, 1 rejeitados em 3 páginas")

    def test_review_file_is_not_created_when_nothing_needs_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "book.pgn"
            report = write_gated_pgn(self.positions()[:1], output_path, source_name="book.pdf", pages_scanned=1)

            self.assertIsNone(report.review_path)
            self.assertFalse((Path(tmpdir) / "book.review.pgn").exists())

    def test_review_items_keep_pdf_order(self) -> None:
        positions = list(reversed(self.positions()))
        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_gated_pgn(positions, Path(tmpdir) / "book.pgn", source_name="book.pdf")

            self.assertEqual([p.page_index for p, _ in report.review_items], [1, 2])

    def test_every_position_lands_in_exactly_one_bucket(self) -> None:
        positions = self.positions()
        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_gated_pgn(positions, Path(tmpdir) / "book.pgn", source_name="book.pdf")

            self.assertEqual(report.total, len(positions))

    def test_gate_runs_on_real_predictions_end_to_end(self) -> None:
        """Ponte com a S-10: a confianca que o gate le e a que `predict_board` produz."""
        prediction = prediction_for(KINGS_ONLY, 0.55)
        position = DiagramPosition(
            page_index=0,
            diagram_index=1,
            fen=prediction.fen_board,
            confidence=prediction.mean_confidence,
            min_confidence=prediction.min_confidence,
            is_legal=prediction.position.is_legal,
            problems=prediction.position.problems,
        )

        verdict, reason = classify_position(position)

        self.assertEqual(verdict, "needs_review")
        self.assertIn("0.550", reason)


if __name__ == "__main__":
    unittest.main()
