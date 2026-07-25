from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.audit import (
    DUPLICATE_HASH_SIZE,
    apply_side_to_move_fixes,
    audit_dataset,
    backup_csv,
    dhash,
    find_duplicate_groups,
    hamming_distance,
    quarantine_fatal_labels,
    remove_duplicate_labels,
)

LEGAL = "4k3/8/8/8/8/8/8/4K3"
LEGAL_OTHER = "4k3/8/8/8/8/8/4P3/4K3"
FATAL_NO_KINGS = "4n3/8/8/4B2n/8/8/8/8"
FATAL_TWO_WHITE_KINGS = "4k3/8/8/8/8/8/8/3KK3"
TURN_FLIP = "R3k3/8/8/8/8/8/8/4K3"  # pretas em xeque: legal apenas com "b"


def _board_image(seed: int, size: int = 128) -> np.ndarray:
    """Imagem sintetica deterministica, com estrutura suficiente para o dHash."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


class Fixture:
    def __init__(self, tmp: str) -> None:
        self.root = Path(tmp)
        self.samples = self.root / "samples"
        self.samples.mkdir()
        self.csv = self.root / "labels.csv"
        self.rows: list[tuple[str, str]] = []

    def add(self, name: str, fen: str, *, image: np.ndarray | None = None, write_image: bool = True) -> None:
        if write_image:
            img = image if image is not None else _board_image(len(self.rows) + 1)
            cv2.imwrite(str(self.samples / name), img)
        self.rows.append((name, fen))

    def write(self) -> None:
        lines = ["filename,fen"] + [f"{name},{fen}" for name, fen in self.rows]
        self.csv.write_text("\n".join(lines) + "\n", encoding="utf-8")


class HashTests(unittest.TestCase):
    def test_default_hash_size_is_not_eight(self) -> None:
        # Um dHash 8x8 alinha com a grade 8x8 do tabuleiro e captura o padrao xadrezado
        # em vez das pecas. Regressao explicita: ver comentario em audit.DUPLICATE_HASH_SIZE.
        self.assertNotEqual(DUPLICATE_HASH_SIZE, 8)
        self.assertEqual(DUPLICATE_HASH_SIZE, 16)

    def test_identical_images_hash_equal(self) -> None:
        image = _board_image(7)
        self.assertEqual(dhash(image), dhash(image.copy()))

    def test_different_images_hash_far_apart(self) -> None:
        self.assertGreater(hamming_distance(dhash(_board_image(1)), dhash(_board_image(2))), 10)

    def test_hamming_distance_basics(self) -> None:
        self.assertEqual(hamming_distance(0b1011, 0b1011), 0)
        self.assertEqual(hamming_distance(0b1011, 0b1000), 2)


class AuditReportTests(unittest.TestCase):
    def test_classifies_each_kind_of_problem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.add("sem_reis.png", FATAL_NO_KINGS)
            fx.add("dois_reis.png", FATAL_TWO_WHITE_KINGS)
            fx.add("turno.png", TURN_FLIP)
            fx.add("ausente.png", LEGAL, write_image=False)
            fx.add("vazia.png", "")
            fx.write()

            report = audit_dataset(fx.csv, fx.samples)

            self.assertEqual(report.total_rows, 6)
            self.assertEqual(len(report.of_kind("fatal")), 2)
            self.assertEqual(len(report.of_kind("lado-a-jogar")), 1)
            self.assertEqual(len(report.of_kind("imagem-ausente")), 1)
            self.assertEqual(len(report.of_kind("sintaxe")), 1)

    def test_suggests_side_to_move_correction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("turno.png", TURN_FLIP)
            fx.write()

            issue = audit_dataset(fx.csv, fx.samples).of_kind("lado-a-jogar")[0]

            self.assertIsNotNone(issue.suggested_fen)
            self.assertIn(" b ", str(issue.suggested_fen))

    def test_counts_orphan_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.write()
            cv2.imwrite(str(fx.samples / "orfa.png"), _board_image(99))

            report = audit_dataset(fx.csv, fx.samples)

            self.assertEqual(report.orphan_images, ["orfa.png"])

    def test_class_distribution_counts_squares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.write()

            report = audit_dataset(fx.csv, fx.samples)

            self.assertEqual(report.class_counts["K"], 1)
            self.assertEqual(report.class_counts["k"], 1)
            self.assertEqual(report.class_counts["empty"], 62)

    def test_missing_csv_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                audit_dataset(Path(tmp) / "nao_existe.csv", Path(tmp))


class DuplicateDetectionTests(unittest.TestCase):
    def test_same_image_same_label_is_a_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            shared = _board_image(11)
            fx.add("a.png", LEGAL, image=shared)
            fx.add("b.png", LEGAL, image=shared)
            fx.write()

            groups = find_duplicate_groups(fx.samples, fx.rows)

            self.assertEqual(groups, [["a.png", "b.png"]])

    def test_same_image_different_label_is_not_a_group(self) -> None:
        # Conflito de anotacao: remover as cegas descartaria a etiqueta correta.
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            shared = _board_image(12)
            fx.add("a.png", LEGAL, image=shared)
            fx.add("b.png", LEGAL_OTHER, image=shared)
            fx.write()

            self.assertEqual(find_duplicate_groups(fx.samples, fx.rows), [])

    def test_different_images_same_label_is_not_a_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("a.png", LEGAL, image=_board_image(21))
            fx.add("b.png", LEGAL, image=_board_image(22))
            fx.write()

            self.assertEqual(find_duplicate_groups(fx.samples, fx.rows), [])


class MutationTests(unittest.TestCase):
    def test_backup_preserves_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.write()
            original = fx.csv.read_bytes()

            backup = backup_csv(fx.csv)

            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_bytes(), original)

    def test_apply_side_to_move_fixes_rewrites_only_the_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("turno.png", TURN_FLIP)
            fx.add("ok.png", LEGAL)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)

            applied = apply_side_to_move_fixes(fx.csv, report)

            self.assertEqual(applied, 1)
            after = audit_dataset(fx.csv, fx.samples)
            self.assertEqual(after.of_kind("lado-a-jogar"), [])
            # A colocacao das pecas nao mudou.
            content = fx.csv.read_text(encoding="utf-8")
            self.assertIn(TURN_FLIP, content)

    def test_quarantine_moves_fatal_rows_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ok.png", LEGAL)
            fx.add("ruim.png", FATAL_NO_KINGS)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)
            quarantine = Path(tmp) / "quarantine.csv"

            moved = quarantine_fatal_labels(fx.csv, report, quarantine)

            self.assertEqual(moved, 1)
            self.assertTrue(quarantine.exists())
            self.assertIn("ruim.png", quarantine.read_text(encoding="utf-8"))
            self.assertNotIn("ruim.png", fx.csv.read_text(encoding="utf-8"))
            self.assertIn("ok.png", fx.csv.read_text(encoding="utf-8"))

    def test_quarantine_records_the_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.add("ruim.png", FATAL_TWO_WHITE_KINGS)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)
            quarantine = Path(tmp) / "quarantine.csv"

            quarantine_fatal_labels(fx.csv, report, quarantine)

            self.assertIn("mais de um rei", quarantine.read_text(encoding="utf-8"))

    def test_dedupe_keeps_first_of_each_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            shared = _board_image(31)
            fx.add("a.png", LEGAL, image=shared)
            fx.add("b.png", LEGAL, image=shared)
            fx.write()
            report = audit_dataset(fx.csv, fx.samples)

            removed = remove_duplicate_labels(fx.csv, report)

            self.assertEqual(removed, 1)
            content = fx.csv.read_text(encoding="utf-8")
            self.assertIn("a.png", content)
            self.assertNotIn("b.png", content)


if __name__ == "__main__":
    unittest.main()
