from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from chess_diagram_ocr.dataset_browser import (
    class_distribution,
    delete_rows,
    filter_rows,
    imbalance_alerts,
    load_rows,
    quarantine_rows,
    restore_from_quarantine,
    source_distribution,
    split_distribution,
    update_row,
)
from chess_diagram_ocr.labels import LabelStore

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"
BLACK_IN_CHECK = "R3k3/8/8/8/8/8/8/4K3"
TWO_WHITE_KINGS = "4k3/8/8/8/8/8/8/K3K3"


class DatasetFixture:
    """Um `labels.csv` de mentira com um caso de cada estado que a tabela precisa mostrar."""

    def __init__(self, tmpdir: Path) -> None:
        self.root = tmpdir
        self.csv_path = tmpdir / "labels.csv"
        self.samples_dir = tmpdir / "samples"
        self.splits_path = tmpdir / "splits.csv"
        self.samples_dir.mkdir()

        rows = [
            ("legal.png", f"{KINGS_ONLY} w - - 0 1", "w", "Kemeri.pdf", "10"),
            ("lado.png", f"{BLACK_IN_CHECK} w - - 0 1", "w", "Kemeri.pdf", "11"),
            ("ilegal.png", f"{TWO_WHITE_KINGS} w - - 0 1", "w", "Schiller.pdf", "12"),
            ("sem_imagem.png", f"{KINGS_ONLY} b - - 0 1", "b", "Schiller.pdf", "13"),
        ]
        pd.DataFrame(
            [
                {
                    "filename": filename,
                    "fen": fen,
                    "side_to_move": side,
                    "source_pdf": pdf,
                    "source_page": page,
                    "source_diagram": "1",
                    "detection_source": "embedded",
                    "created_at": "2026-07-26T10:00:00Z",
                    "corrected_by": "",
                }
                for filename, fen, side, pdf, page in rows
            ]
        ).to_csv(self.csv_path, index=False)

        for filename, *_ in rows:
            if filename != "sem_imagem.png":
                cv2.imwrite(str(self.samples_dir / filename), np.zeros((16, 16, 3), dtype=np.uint8))

        pd.DataFrame(
            {"filename": ["legal.png", "lado.png", "ilegal.png"], "split": ["train", "val", "test"]}
        ).to_csv(self.splits_path, index=False)

    def rows(self, duplicate_groups=()):
        return load_rows(
            self.csv_path,
            self.samples_dir,
            splits_path=self.splits_path,
            duplicate_groups=duplicate_groups,
        )


class LoadRowsTests(unittest.TestCase):
    def test_classifies_legality_in_three_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = DatasetFixture(Path(tmpdir)).rows()
            por_nome = {row.filename: row for row in rows}
            self.assertEqual(por_nome["legal.png"].legality, "legal")
            self.assertEqual(por_nome["lado.png"].legality, "lado-a-jogar")
            self.assertEqual(por_nome["ilegal.png"].legality, "ilegal")
            self.assertIn("mais de um rei", "; ".join(por_nome["ilegal.png"].problems))

    def test_reports_missing_images_without_dropping_the_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = DatasetFixture(Path(tmpdir)).rows()
            ausente = next(row for row in rows if row.filename == "sem_imagem.png")
            self.assertFalse(ausente.image_exists)
            self.assertEqual(len(rows), 4)

    def test_attaches_the_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = DatasetFixture(Path(tmpdir)).rows()
            self.assertEqual({row.filename: row.split for row in rows}["ilegal.png"], "test")
            self.assertIsNone({row.filename: row.split for row in rows}["sem_imagem.png"])

    def test_marks_duplicates_from_the_group_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = DatasetFixture(Path(tmpdir)).rows(duplicate_groups=[["legal.png", "lado.png"]])
            por_nome = {row.filename: row for row in rows}
            # O representante e o primeiro em ordem alfabetica -- a mesma convencao de
            # `audit.find_duplicate_groups`, que devolve os grupos ordenados.
            self.assertFalse(por_nome["lado.png"].is_duplicate)
            self.assertTrue(por_nome["legal.png"].is_duplicate)

    def test_missing_csv_yields_no_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(load_rows(Path(tmpdir) / "nada.csv", Path(tmpdir)), [])


class FilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fixture = DatasetFixture(Path(self._tmp.name))
        self.all_rows = self.fixture.rows(duplicate_groups=[["legal.png", "lado.png"]])

    def test_no_filter_returns_everything(self) -> None:
        self.assertEqual(len(filter_rows(self.all_rows)), 4)

    def test_by_legality(self) -> None:
        self.assertEqual([row.filename for row in filter_rows(self.all_rows, legality="ilegal")], ["ilegal.png"])

    def test_by_split(self) -> None:
        self.assertEqual([row.filename for row in filter_rows(self.all_rows, split="val")], ["lado.png"])

    def test_by_source_book(self) -> None:
        nomes = [row.filename for row in filter_rows(self.all_rows, source_pdf="Schiller.pdf")]
        self.assertEqual(sorted(nomes), ["ilegal.png", "sem_imagem.png"])

    def test_by_query_across_columns(self) -> None:
        self.assertEqual(len(filter_rows(self.all_rows, query="kemeri")), 2)
        self.assertEqual(len(filter_rows(self.all_rows, query="ilegal")), 1)

    def test_only_duplicates(self) -> None:
        self.assertEqual([row.filename for row in filter_rows(self.all_rows, only_duplicates=True)], ["legal.png"])

    def test_only_missing_image(self) -> None:
        self.assertEqual(
            [row.filename for row in filter_rows(self.all_rows, only_missing_image=True)], ["sem_imagem.png"]
        )

    def test_by_class_present(self) -> None:
        # Torre branca so existe no rotulo de `lado.png`.
        self.assertEqual([row.filename for row in filter_rows(self.all_rows, has_classes={"R"})], ["lado.png"])

    def test_filters_combine(self) -> None:
        resultado = filter_rows(self.all_rows, source_pdf="Kemeri.pdf", legality="legal")
        self.assertEqual([row.filename for row in resultado], ["legal.png"])


class StatisticsTests(unittest.TestCase):
    def test_counts_squares_not_boards(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = DatasetFixture(Path(tmpdir)).rows()
            counts = class_distribution(rows)
            # 4 tabuleiros x 64 casas.
            self.assertEqual(sum(counts.values()), 4 * 64)
            self.assertEqual(counts["K"], 5)  # 1+1+2+1

    def test_split_and_source_distributions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = DatasetFixture(Path(tmpdir)).rows()
            self.assertEqual(split_distribution(rows)["sem split"], 1)
            self.assertEqual(source_distribution(rows)["Kemeri.pdf"], 2)

    def test_imbalance_alert_ignores_empty_squares(self) -> None:
        counts = Counter({"empty": 100000, "K": 10, "k": 10})
        alertas = imbalance_alerts(counts)
        self.assertTrue(any("sem nenhuma amostra" in texto for texto in alertas))
        self.assertFalse(any("empty" in texto for texto in alertas))

    def test_imbalance_alert_fires_on_ratio(self) -> None:
        counts = Counter(dict.fromkeys("PNBRQKpnbrqk", 100))
        counts["q"] = 1
        self.assertTrue(any("Desbalanceamento" in texto for texto in imbalance_alerts(counts)))

    def test_balanced_dataset_has_no_alert(self) -> None:
        counts = Counter(dict.fromkeys("PNBRQKpnbrqk", 100))
        self.assertEqual(imbalance_alerts(counts), [])


class EditingTests(unittest.TestCase):
    """O critério de aceite da S-23: corrigir sem tocar no CSV à mão."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fixture = DatasetFixture(Path(self._tmp.name))

    def test_update_row_rewrites_fen_and_side(self) -> None:
        atualizado = update_row(self.fixture.csv_path, "lado.png", fen=KINGS_ONLY, side_to_move="b")
        self.assertTrue(atualizado)

        row = next(row for row in self.fixture.rows() if row.filename == "lado.png")
        self.assertEqual(row.placement, KINGS_ONLY)
        self.assertEqual(row.side_to_move, "b")
        self.assertEqual(row.legality, "legal")
        self.assertEqual(row.corrected_by, "ui")

    def test_update_row_fixes_an_illegal_label(self) -> None:
        update_row(self.fixture.csv_path, "ilegal.png", fen=KINGS_ONLY, side_to_move="w")
        row = next(row for row in self.fixture.rows() if row.filename == "ilegal.png")
        self.assertEqual(row.legality, "legal")

    def test_update_row_refuses_an_illegal_position(self) -> None:
        with self.assertRaises(ValueError):
            update_row(self.fixture.csv_path, "legal.png", fen=TWO_WHITE_KINGS)
        # E o CSV nao mudou.
        row = next(row for row in self.fixture.rows() if row.filename == "legal.png")
        self.assertEqual(row.placement, KINGS_ONLY)

    def test_update_row_allows_illegal_when_asked(self) -> None:
        self.assertTrue(
            update_row(self.fixture.csv_path, "legal.png", fen=TWO_WHITE_KINGS, allow_illegal=True)
        )

    def test_update_row_marks_the_illegal_position_it_accepted(self) -> None:
        update_row(self.fixture.csv_path, "legal.png", fen=TWO_WHITE_KINGS, allow_illegal=True)

        entry = next(e for e in LabelStore(self.fixture.csv_path).read() if e.filename == "legal.png")
        self.assertTrue(entry.illegal_accepted)

    def test_correcting_a_marked_row_back_to_legal_clears_the_mark(self) -> None:
        """A marca descreve a FEN da linha, não perdoa o arquivo para sempre."""
        update_row(self.fixture.csv_path, "legal.png", fen=TWO_WHITE_KINGS, allow_illegal=True)

        update_row(self.fixture.csv_path, "legal.png", fen=KINGS_ONLY)

        entry = next(e for e in LabelStore(self.fixture.csv_path).read() if e.filename == "legal.png")
        self.assertEqual(entry.illegal_ok, "")

    def test_update_row_reports_unknown_sample(self) -> None:
        self.assertFalse(update_row(self.fixture.csv_path, "nao-existe.png", fen=KINGS_ONLY))

    def test_update_row_preserves_the_other_columns(self) -> None:
        update_row(self.fixture.csv_path, "legal.png", fen=KINGS_ONLY, side_to_move="b")
        row = next(row for row in self.fixture.rows() if row.filename == "legal.png")
        self.assertEqual(row.source_pdf, "Kemeri.pdf")
        self.assertEqual(row.detection_source, "embedded")

    def test_delete_keeps_the_image_by_default(self) -> None:
        removed = delete_rows(self.fixture.csv_path, ["legal.png"], samples_dir=self.fixture.samples_dir)
        self.assertEqual(removed, 1)
        self.assertEqual(len(self.fixture.rows()), 3)
        self.assertTrue((self.fixture.samples_dir / "legal.png").exists())

    def test_delete_can_remove_the_image(self) -> None:
        delete_rows(
            self.fixture.csv_path,
            ["legal.png"],
            samples_dir=self.fixture.samples_dir,
            delete_images=True,
        )
        self.assertFalse((self.fixture.samples_dir / "legal.png").exists())

    def test_delete_of_unknown_sample_changes_nothing(self) -> None:
        self.assertEqual(delete_rows(self.fixture.csv_path, ["nao-existe.png"]), 0)
        self.assertEqual(len(self.fixture.rows()), 4)

    def test_quarantine_moves_the_row_and_keeps_the_reason(self) -> None:
        quarantine_path = self.fixture.root / "quarantine.csv"
        moved = quarantine_rows(self.fixture.csv_path, ["ilegal.png"], quarantine_path, reason="dois reis brancos")
        self.assertEqual(moved, 1)
        self.assertEqual(len(self.fixture.rows()), 3)

        quarantined = pd.read_csv(quarantine_path)
        self.assertEqual(list(quarantined["filename"]), ["ilegal.png"])
        self.assertEqual(list(quarantined["motivo"]), ["dois reis brancos"])

    def test_restore_from_quarantine_round_trip(self) -> None:
        quarantine_path = self.fixture.root / "quarantine.csv"
        quarantine_rows(self.fixture.csv_path, ["ilegal.png"], quarantine_path)
        restored = restore_from_quarantine(self.fixture.csv_path, quarantine_path, ["ilegal.png"])

        self.assertEqual(restored, 1)
        self.assertEqual(len(self.fixture.rows()), 4)
        self.assertTrue(pd.read_csv(quarantine_path).empty)
        # A coluna `motivo` nao volta para o labels.csv.
        self.assertNotIn("motivo", pd.read_csv(self.fixture.csv_path).columns)


if __name__ == "__main__":
    unittest.main()
