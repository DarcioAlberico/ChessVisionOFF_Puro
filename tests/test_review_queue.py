from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import chess
import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.detection import DiagramCandidate
from chess_diagram_ocr.inference import OrientedPrediction, prediction_from_probs
from chess_diagram_ocr.pdf_text import DiagramContext
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, ScannedDiagram
from chess_diagram_ocr.review_queue import (
    WEIGHT_ILLEGAL,
    WEIGHT_ORIENTATION_AMBIGUOUS,
    ReviewItem,
    ReviewQueue,
    build_review_queue,
    error_rate,
    item_from_scanned,
    merge_queues,
    priority_for,
    rare_classes_from_labels,
)
from chess_diagram_ocr.semantics import SideToMove

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"
EMPTY_BOARD = "8/8/8/8/8/8/8/8"


def position(**overrides) -> DiagramPosition:
    base = {
        "page_index": 0,
        "diagram_index": 1,
        "fen": KINGS_ONLY,
        "confidence": 0.99,
        "min_confidence": 0.99,
        "is_legal": True,
        "is_fatal": False,
    }
    base.update(overrides)
    return DiagramPosition(**base)


class PriorityTests(unittest.TestCase):
    """A ordem da S-22 tem de valer como precedência, não como soma de sinais."""

    def test_clean_diagram_gets_no_reason_to_be_reviewed(self) -> None:
        score, reasons = priority_for(position(), min_confidence=0.99, mean_entropy=0.001)
        self.assertEqual(reasons, ())
        self.assertLess(score, 1.0)

    def test_illegal_dominates_low_confidence(self) -> None:
        ilegal, _ = priority_for(
            position(is_legal=False, is_fatal=True, problems=("tabuleiro vazio",), fen=EMPTY_BOARD),
            min_confidence=0.99,
            mean_entropy=0.0,
        )
        inseguro, _ = priority_for(position(), min_confidence=0.01, mean_entropy=2.0)
        self.assertGreater(ilegal, inseguro)
        self.assertGreaterEqual(ilegal, WEIGHT_ILLEGAL)

    def test_ambiguous_orientation_outranks_low_confidence(self) -> None:
        """Uma casa insegura custa uma correção; um diagrama girado custa o diagrama."""
        girado, reasons = priority_for(
            position(orientation_ambiguous=True, orientation_reason="margem apertada"),
            min_confidence=0.99,
            mean_entropy=0.0,
        )
        inseguro, _ = priority_for(position(), min_confidence=0.01, mean_entropy=1.0)
        self.assertGreater(girado, inseguro)
        self.assertGreaterEqual(girado, WEIGHT_ORIENTATION_AMBIGUOUS)
        self.assertTrue(any("orientação incerta" in reason for reason in reasons))

    def test_conflicting_sources_are_a_reason(self) -> None:
        _score, reasons = priority_for(
            position(side_to_move=SideToMove(color=chess.WHITE, source="legality", conflicting=True)),
            min_confidence=0.99,
            mean_entropy=0.0,
        )
        self.assertTrue(any("discordam" in reason for reason in reasons))

    def test_low_confidence_scales_with_the_gap(self) -> None:
        pior, _ = priority_for(position(), min_confidence=0.10, mean_entropy=0.0)
        melhor, _ = priority_for(position(), min_confidence=0.70, mean_entropy=0.0)
        self.assertGreater(pior, melhor)

    def test_low_confidence_names_the_squares(self) -> None:
        _score, reasons = priority_for(
            position(),
            min_confidence=0.10,
            mean_entropy=0.0,
            uncertain_squares=[0, 63],
        )
        self.assertTrue(any("a8" in reason and "h1" in reason for reason in reasons))

    def test_rare_class_adds_weight_only_when_present(self) -> None:
        com_rara, reasons = priority_for(
            position(fen="4k3/8/8/8/8/8/8/3QK3"),
            min_confidence=0.99,
            mean_entropy=0.0,
            rare_classes={"Q"},
        )
        sem_rara, _ = priority_for(position(), min_confidence=0.99, mean_entropy=0.0, rare_classes={"Q"})
        self.assertGreater(com_rara, sem_rara)
        self.assertTrue(any("classe rara" in reason for reason in reasons))

    def test_decode_repair_is_reported(self) -> None:
        _score, reasons = priority_for(position(), min_confidence=0.99, mean_entropy=0.0, repaired_squares=2)
        self.assertTrue(any("decodificação restrita" in reason for reason in reasons))


class QueueOrderingTests(unittest.TestCase):
    def item(self, priority: float, page: int = 0, diagram: int = 1, status: str = "pending") -> ReviewItem:
        return ReviewItem(
            pdf_path="livro.pdf",
            page_index=page,
            diagram_index=diagram,
            board_image="cache/p1_d1.png",
            fen=f"{KINGS_ONLY} w - - 0 1",
            side_to_move="w",
            min_confidence=0.5,
            mean_entropy=0.1,
            priority=priority,
            reasons=("teste",),
            status=status,  # type: ignore[arg-type]
        )

    def test_sorts_by_priority_then_book_order(self) -> None:
        queue = ReviewQueue(items=[self.item(10, page=5), self.item(90, page=9), self.item(90, page=2)])
        queue.sort()
        self.assertEqual([item.page_index for item in queue.items], [2, 9, 5])

    def test_pending_filters_out_resolved(self) -> None:
        queue = ReviewQueue(items=[self.item(10), self.item(20, page=1, status="done")])
        self.assertEqual(len(queue.pending()), 1)

    def test_mark_and_update(self) -> None:
        queue = ReviewQueue(items=[self.item(10)])
        queue.mark(0, "done")
        self.assertEqual(queue.items[0].status, "done")
        queue.update_fen(0, "8/8/8/8/8/8/8/K6k w - - 0 1", "b")
        self.assertEqual(queue.items[0].side_to_move, "b")
        self.assertEqual(queue.items[0].status, "done")

    def test_index_of_finds_the_diagram(self) -> None:
        queue = ReviewQueue(items=[self.item(10, page=3, diagram=2)])
        self.assertEqual(queue.index_of(3, 2), 0)
        self.assertIsNone(queue.index_of(3, 1))

    def test_persistence_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "review_queue.json"
            queue = ReviewQueue(source_pdf="livro.pdf", created_at="2026-07-26T10:00:00", items=[self.item(42)])
            queue.save(path)
            restored = ReviewQueue.load(path)
            self.assertEqual(restored.source_pdf, "livro.pdf")
            self.assertEqual(len(restored.items), 1)
            self.assertAlmostEqual(restored.items[0].priority, 42.0)

    def test_load_of_a_broken_file_starts_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "review_queue.json"
            path.write_text("{quebrado", encoding="utf-8")
            self.assertEqual(len(ReviewQueue.load(path).items), 0)

    def test_merge_keeps_what_was_already_reviewed(self) -> None:
        """Revarrer o livro não pode ressuscitar item já resolvido."""
        antiga = ReviewQueue(items=[self.item(10, page=1, status="done"), self.item(10, page=2, status="skipped")])
        nova = ReviewQueue(items=[self.item(80, page=1), self.item(70, page=2), self.item(60, page=3)])
        merged = merge_queues(antiga, nova)
        estados = {item.page_index: item.status for item in merged.items}
        self.assertEqual(estados, {1: "done", 2: "skipped", 3: "pending"})
        # A prioridade nova manda: o que mudou no livro tem de aparecer.
        self.assertAlmostEqual(next(i.priority for i in merged.items if i.page_index == 1), 80.0)

    def test_error_rate_counts_objective_signals(self) -> None:
        limpo = self.item(1)
        suspeito = ReviewItem(**{**limpo.__dict__, "reasons": ("ilegal: tabuleiro vazio",)})
        self.assertAlmostEqual(error_rate([limpo, suspeito]), 1.0)  # os dois tem min_conf 0,5 < 0,80
        confiante = ReviewItem(**{**limpo.__dict__, "min_confidence": 0.99, "reasons": ("classe rara: Q",)})
        self.assertAlmostEqual(error_rate([confiante, suspeito]), 0.5)


def oriented(fen: str, confidence: float = 0.99, *, ambiguous: bool = False) -> OrientedPrediction:
    return OrientedPrediction(
        prediction=prediction_from_probs(probs_for_fen(fen, confidence)),
        rotation=0,
        margin=0.0 if ambiguous else 0.5,
        ambiguous=ambiguous,
        reason="teste",
    )


def candidate() -> DiagramCandidate:
    return DiagramCandidate(
        board_rgb=np.zeros((80, 80, 3), dtype=np.uint8),
        bbox_pdf=(10.0, 10.0, 90.0, 90.0),
        source="embedded",
        detector_score=0.9,
        native_size=(320, 320),
    )


class ItemFromScannedTests(unittest.TestCase):
    def test_clean_diagram_does_not_enter_the_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            scanned = ScannedDiagram(
                position=position(),
                prediction=prediction_from_probs(probs_for_fen(KINGS_ONLY, 0.999)),
                board_rgb=np.zeros((80, 80, 3), dtype=np.uint8),
                detector_score=0.9,
            )
            self.assertIsNone(item_from_scanned(scanned, pdf_path=Path("livro.pdf"), cache_dir=Path(tmpdir)))

    def test_suspect_diagram_gets_a_cached_thumbnail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prediction = prediction_from_probs(probs_for_fen(KINGS_ONLY, 0.30))
            scanned = ScannedDiagram(
                position=position(page_index=6, min_confidence=0.30),
                prediction=prediction,
                board_rgb=np.zeros((80, 80, 3), dtype=np.uint8),
                detector_score=0.9,
            )
            item = item_from_scanned(scanned, pdf_path=Path("livro.pdf"), cache_dir=Path(tmpdir))
            assert item is not None
            self.assertTrue(Path(item.board_image).exists())
            self.assertIn("p00007_d1.png", item.board_image)
            # As 64 confiancas viajam com o item: o heatmap abre sem reprocessar a pagina.
            self.assertEqual(len(item.square_confidences), 64)
            self.assertEqual(item.first_uncertain_square, item.uncertain_squares[0])


class BuildQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patches = [
            patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count", return_value=3),
            patch("chess_diagram_ocr.pdf_to_pgn.load_model", return_value=("model", "cpu")),
            patch(
                "chess_diagram_ocr.pdf_to_pgn._render_pdf_page",
                side_effect=lambda *a, **k: np.zeros((10, 10, 3), dtype=np.uint8),
            ),
            patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams", side_effect=lambda *a, **k: [candidate()]),
            patch("chess_diagram_ocr.pdf_to_pgn._page_contexts", side_effect=lambda *a, **k: [DiagramContext()]),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in self.patches])

    def test_only_diagrams_with_a_reason_enter_the_queue(self) -> None:
        leituras = [oriented(KINGS_ONLY, 0.999), oriented(KINGS_ONLY, 0.20), oriented(EMPTY_BOARD, 0.95)]
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "chess_diagram_ocr.pdf_to_pgn.predict_with_orientation",
            side_effect=leituras,
        ):
            queue = build_review_queue(Path("livro.pdf"), cache_dir=Path(tmpdir))

        self.assertEqual(queue.scanned_diagrams, 3)
        self.assertEqual(queue.pages_scanned, 3)
        # O tabuleiro vazio (ilegal) vem antes do de baixa confianca; o limpo nem entra.
        self.assertEqual(len(queue.items), 2)
        self.assertTrue(queue.items[0].reasons[0].startswith("ilegal"))
        self.assertGreater(queue.items[0].priority, queue.items[1].priority)

    def test_limit_cuts_after_sorting(self) -> None:
        leituras = [oriented(EMPTY_BOARD, 0.95), oriented(KINGS_ONLY, 0.20), oriented(KINGS_ONLY, 0.50)]
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "chess_diagram_ocr.pdf_to_pgn.predict_with_orientation",
            side_effect=leituras,
        ):
            queue = build_review_queue(Path("livro.pdf"), cache_dir=Path(tmpdir), limit=1)
        self.assertEqual(len(queue.items), 1)
        self.assertTrue(queue.items[0].reasons[0].startswith("ilegal"))


class RareClassTests(unittest.TestCase):
    def test_reads_class_shares_from_the_labels_csv(self) -> None:
        import pandas as pd

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "labels.csv"
            # Um tabuleiro com uma dama branca e muitos peoes: a dama e a classe rara.
            pd.DataFrame(
                {"filename": ["a.png"] * 4, "fen": ["4k3/pppppppp/8/8/8/8/PPPPPPPP/3QK3"] * 4}
            ).to_csv(csv_path, index=False)
            raras = rare_classes_from_labels(csv_path, share=0.10)
            self.assertIn("Q", raras)
            self.assertNotIn("P", raras)

    def test_missing_csv_is_not_an_error(self) -> None:
        self.assertEqual(rare_classes_from_labels(Path("nao-existe.csv")), set())


if __name__ == "__main__":
    unittest.main()
