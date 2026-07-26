from __future__ import annotations

import logging
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import chess
import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.detection import DiagramCandidate
from chess_diagram_ocr.export_checkpoint import (
    CheckpointWriter,
    ScanParams,
    load_partial,
    partial_path_for,
    position_from_dict,
    position_to_dict,
)
from chess_diagram_ocr.inference import OrientedPrediction, prediction_from_probs
from chess_diagram_ocr.pdf_text import DiagramContext
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, save_pdf_positions_to_pgn, scan_pdf_positions
from chess_diagram_ocr.semantics import SideToMove

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"


def params(**overrides) -> ScanParams:
    base = {
        "source_name": "livro.pdf",
        "model_path": "models/piece_classifier.pt",
        "dpi": 220,
        "max_boards_per_page": 8,
        "orientation": "auto",
        "reading_order": "column",
        "read_text": True,
        "start_page": 0,
        "end_page": None,
    }
    base.update(overrides)
    return ScanParams(**base)


def position(page: int = 0, diagram: int = 1) -> DiagramPosition:
    return DiagramPosition(
        page_index=page,
        diagram_index=diagram,
        fen=KINGS_ONLY,
        confidence=0.97,
        min_confidence=0.91,
        is_legal=True,
        is_fatal=False,
        problems=("nenhum",),
        rotation=180,
        orientation_ambiguous=True,
        orientation_reason="margem apertada",
        side_to_move=SideToMove(color=chess.BLACK, source="text", reason="legenda", conflicting=True),
        context=DiagramContext(
            caption="5\nMorphy-De Riviere",
            side_to_move=chess.BLACK,
            side_to_move_evidence="pretas jogam",
            exercise_number=5,
            players=("Morphy", "De Riviere"),
            event="Paris",
            year=1858,
        ),
        detection_source="embedded",
        duplicate_of=(3, 2),
    )


class SerializationTests(unittest.TestCase):
    """Se a serialização perder um campo, retomar produz um PGN diferente do inteiro."""

    def test_round_trip_preserves_every_field(self) -> None:
        original = position()
        restored = position_from_dict(position_to_dict(original))
        self.assertEqual(restored, original)

    def test_round_trip_of_a_bare_position(self) -> None:
        bare = DiagramPosition(page_index=2, diagram_index=1, fen=KINGS_ONLY, confidence=0.5)
        self.assertEqual(position_from_dict(position_to_dict(bare)), bare)

    def test_side_to_move_color_survives(self) -> None:
        restored = position_from_dict(position_to_dict(position()))
        assert restored.side_to_move is not None
        self.assertEqual(restored.side_to_move.color, chess.BLACK)
        self.assertTrue(restored.side_to_move.conflicting)


class PartialFileTests(unittest.TestCase):
    def test_writer_and_loader_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(), every=1)
            writer.record_page(0, [position(0, 1)])
            writer.record_page(1, [position(1, 1), position(1, 2)])

            partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual(len(partial.positions), 3)
            self.assertEqual(partial.last_page_done, 1)
            self.assertEqual(partial.resume_from, 2)

    def test_pages_are_buffered_until_the_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(), every=5)
            for page in range(3):
                writer.record_page(page, [position(page, 1)])
            self.assertFalse(path.exists())

            writer.flush()
            partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual(partial.last_page_done, 2)

    def test_different_parameters_invalidate_the_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(dpi=220), every=1)
            writer.record_page(0, [position()])

            with self.assertLogs("chess_diagram_ocr.export_checkpoint", level=logging.WARNING) as captured:
                self.assertIsNone(load_partial(path, params(dpi=300)))
            self.assertTrue(any("outros parâmetros" in line for line in captured.output))

    def test_torn_last_line_keeps_the_pages_before_it(self) -> None:
        """Queda de energia no meio da escrita: a última linha não parseia, o resto vale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            writer = CheckpointWriter(path, params(), every=1)
            writer.record_page(0, [position(0, 1)])
            writer.record_page(1, [position(1, 1)])
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"kind": "page", "page_index": 2, "positi')

            with self.assertLogs("chess_diagram_ocr.export_checkpoint", level=logging.WARNING):
                partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual(partial.last_page_done, 1)
            self.assertEqual(len(partial.positions), 2)

    def test_missing_file_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(load_partial(Path(tmpdir) / "nao-existe.jsonl", params()))

    def test_resumed_writer_appends_instead_of_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "livro.partial.jsonl"
            CheckpointWriter(path, params(), every=1).record_page(0, [position(0, 1)])

            continuacao = CheckpointWriter(path, params(), every=1, resumed=True)
            continuacao.record_page(1, [position(1, 1)])

            partial = load_partial(path, params())
            assert partial is not None
            self.assertEqual([p.page_index for p in partial.positions], [0, 1])

    def test_partial_path_sits_next_to_the_pgn(self) -> None:
        self.assertEqual(partial_path_for(Path("PGN/livro.pgn")), Path("PGN/livro.partial.jsonl"))


def oriented(fen: str, confidence: float = 0.99) -> OrientedPrediction:
    return OrientedPrediction(
        prediction=prediction_from_probs(probs_for_fen(fen, confidence)),
        rotation=0,
        margin=0.5,
        ambiguous=False,
        reason="teste",
    )


def candidate() -> DiagramCandidate:
    return DiagramCandidate(
        board_rgb=np.zeros((800, 800, 3), dtype=np.uint8),
        bbox_pdf=(10.0, 10.0, 90.0, 90.0),
        source="embedded",
        detector_score=0.9,
        native_size=(320, 320),
    )


class CancelAndResumeTests(unittest.TestCase):
    """S-24: cancelar preserva o parcial, e retomar produz o mesmo PGN da execução inteira."""

    def setUp(self) -> None:
        self.page_count = 6
        self.patches = [
            patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count", return_value=self.page_count),
            patch("chess_diagram_ocr.pdf_to_pgn.load_model", return_value=("model", "cpu")),
            patch(
                "chess_diagram_ocr.pdf_to_pgn._render_pdf_page",
                side_effect=lambda *a, **k: np.zeros((10, 10, 3), dtype=np.uint8),
            ),
            patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams", side_effect=lambda *a, **k: [candidate()]),
            patch("chess_diagram_ocr.pdf_to_pgn._page_contexts", side_effect=lambda *a, **k: [DiagramContext()]),
            patch("chess_diagram_ocr.pdf_to_pgn.predict_with_orientation", side_effect=lambda *a, **k: oriented(KINGS_ONLY)),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in self.patches])

    def test_cancel_stops_between_pages(self) -> None:
        cancel = threading.Event()
        visited: list[int] = []

        def _progress(page_index: int, total: int, boards: int, positions: int) -> None:
            visited.append(page_index)
            if len(visited) == 2:
                cancel.set()

        positions = scan_pdf_positions(
            Path("livro.pdf"),
            cancel_event=cancel,
            progress_callback=_progress,
        )

        # Parou logo apos a segunda pagina, e nao no fim das seis.
        self.assertEqual(visited, [0, 1])
        self.assertEqual(len(positions), 2)

    def test_cancel_already_set_reads_nothing(self) -> None:
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(scan_pdf_positions(Path("livro.pdf"), cancel_event=cancel), [])

    def test_resume_produces_the_same_pgn_as_an_uninterrupted_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            inteiro = Path(tmpdir) / "inteiro.pgn"
            report_inteiro = save_pdf_positions_to_pgn(pdf_source=Path("livro.pdf"), output_path=inteiro)
            self.assertFalse(report_inteiro.cancelled)
            self.assertIsNone(report_inteiro.resumed_from_page)
            # Terminar apaga o parcial: ele existe para atravessar a interrupcao, nao para
            # virar um segundo formato de saida.
            self.assertFalse(partial_path_for(inteiro).exists())

            interrompido = Path(tmpdir) / "retomado.pgn"
            cancel = threading.Event()
            paginas: list[int] = []

            def _progress(page_index: int, total: int, boards: int, positions: int) -> None:
                paginas.append(page_index)
                if len(paginas) == 3:
                    cancel.set()

            parcial = save_pdf_positions_to_pgn(
                pdf_source=Path("livro.pdf"),
                output_path=interrompido,
                cancel_event=cancel,
                checkpoint_every=1,
                progress_callback=_progress,
            )
            self.assertTrue(parcial.cancelled)
            self.assertEqual(parcial.partial_path, partial_path_for(interrompido))
            self.assertTrue(parcial.partial_path.exists())
            self.assertEqual(len(parcial.accepted), 3)

            retomado = save_pdf_positions_to_pgn(pdf_source=Path("livro.pdf"), output_path=interrompido)
            self.assertFalse(retomado.cancelled)
            self.assertEqual(retomado.resumed_from_page, 3)
            self.assertEqual(len(retomado.accepted), len(report_inteiro.accepted))
            self.assertEqual(
                interrompido.read_text(encoding="utf-8"),
                inteiro.read_text(encoding="utf-8"),
            )
            self.assertFalse(partial_path_for(interrompido).exists())

    def test_resume_disabled_starts_over(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            saida = Path(tmpdir) / "livro.pgn"
            cancel = threading.Event()
            cancel.set()
            save_pdf_positions_to_pgn(pdf_source=Path("livro.pdf"), output_path=saida, cancel_event=cancel)

            report = save_pdf_positions_to_pgn(pdf_source=Path("livro.pdf"), output_path=saida, resume=False)
            self.assertIsNone(report.resumed_from_page)
            self.assertEqual(len(report.accepted), self.page_count)


if __name__ == "__main__":
    unittest.main()
