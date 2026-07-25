from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.config import BOARD_SIZE
from chess_diagram_ocr.dataset import BoardFenDataset, append_training_sample

LEGAL = "4k3/8/8/8/8/8/8/4K3"
FATAL = "4n3/8/8/4B2n/8/8/8/8"  # sem reis
TURN_FLIP = "R3k3/8/8/8/8/8/8/4K3"  # legal apenas com pretas a jogar


def _write_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["filename,fen"] + [f"{name},{fen}" for name, fen in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_board(directory: Path, name: str, size: int = BOARD_SIZE) -> None:
    cv2.imwrite(str(directory / name), np.full((size, size, 3), 200, dtype=np.uint8))


class MalformedCsvTests(unittest.TestCase):
    """Regressao: uma celula FEN vazia derrubava todo o carregamento do dataset."""

    def test_empty_fen_cell_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_board(samples, "b.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL), ("b.png", "")])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 1)
            self.assertEqual(dataset.entries[0].filename, "a.png")

    def test_missing_columns_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "labels.csv").write_text("arquivo,posicao\na.png,x\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                BoardFenDataset(root / "labels.csv", root)

    def test_absent_csv_yields_empty_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = BoardFenDataset(Path(tmp) / "ausente.csv", Path(tmp))
            self.assertEqual(len(dataset), 0)

    def test_missing_image_warns_and_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_csv(root / "labels.csv", [("ausente.png", LEGAL)])

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 0)
            self.assertTrue(any("imagem ausente" in str(w.message) for w in caught))


class LegalityFilterTests(unittest.TestCase):
    def test_fatal_labels_are_skipped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            for name in ("ok.png", "ruim.png"):
                _write_board(samples, name)
            _write_csv(root / "labels.csv", [("ok.png", LEGAL), ("ruim.png", FATAL)])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 1)
            self.assertEqual(len(dataset.skipped_illegal), 1)
            self.assertEqual(dataset.skipped_illegal[0][0], "ruim.png")

    def test_skip_illegal_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "ruim.png")
            _write_csv(root / "labels.csv", [("ruim.png", FATAL)])

            dataset = BoardFenDataset(root / "labels.csv", samples, skip_illegal=False)

            self.assertEqual(len(dataset.entries), 1)

    def test_turn_flip_labels_are_kept(self) -> None:
        # As pecas estao certas; so o turno assumido esta errado. Descartar perderia
        # uma amostra perfeitamente boa para o treino.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "turno.png")
            _write_csv(root / "labels.csv", [("turno.png", TURN_FLIP)])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset.entries), 1)
            self.assertEqual(dataset.skipped_illegal, [])


class SplitFilterTests(unittest.TestCase):
    def test_only_requested_split_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            for name in ("a.png", "b.png", "c.png"):
                _write_board(samples, name)
            _write_csv(root / "labels.csv", [("a.png", LEGAL), ("b.png", LEGAL), ("c.png", LEGAL)])
            splits = {"a.png": "train", "b.png": "val", "c.png": "test"}

            train = BoardFenDataset(root / "labels.csv", samples, split="train", splits=splits)  # type: ignore[arg-type]
            test = BoardFenDataset(root / "labels.csv", samples, split="test", splits=splits)  # type: ignore[arg-type]

            self.assertEqual([e.filename for e in train.entries], ["a.png"])
            self.assertEqual([e.filename for e in test.entries], ["c.png"])

    def test_sample_without_recorded_split_is_excluded(self) -> None:
        # Amostra nova nao pode entrar no conjunto de teste por acidente.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            for name in ("a.png", "nova.png"):
                _write_board(samples, name)
            _write_csv(root / "labels.csv", [("a.png", LEGAL), ("nova.png", LEGAL)])

            test = BoardFenDataset(
                root / "labels.csv", samples, split="test", splits={"a.png": "test"}  # type: ignore[arg-type]
            )

            self.assertEqual([e.filename for e in test.entries], ["a.png"])

    def test_split_without_map_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])

            with self.assertRaises(ValueError):
                BoardFenDataset(root / "labels.csv", samples, split="train")


class ItemShapeTests(unittest.TestCase):
    def test_each_board_yields_64_squares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])

            dataset = BoardFenDataset(root / "labels.csv", samples)

            self.assertEqual(len(dataset), 64)
            tensor, label = dataset[0]
            self.assertEqual(tuple(tensor.shape), (1, 64, 64))
            self.assertIsInstance(label, int)

    def test_king_squares_carry_the_right_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = root / "samples"
            samples.mkdir()
            _write_board(samples, "a.png")
            _write_csv(root / "labels.csv", [("a.png", LEGAL)])
            dataset = BoardFenDataset(root / "labels.csv", samples)

            # LEGAL = "4k3/8/.../4K3": indice 4 e o rei preto (e8), 60 o branco (e1).
            self.assertEqual(dataset[4][1], 12)  # 'k'
            self.assertEqual(dataset[60][1], 6)  # 'K'


class AppendSampleTests(unittest.TestCase):
    def test_appending_writes_image_and_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            path = append_training_sample(board, LEGAL, root / "labels.csv", root / "samples")

            self.assertTrue(path.exists())
            self.assertIn(path.name, (root / "labels.csv").read_text(encoding="utf-8"))

    def test_fatal_position_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            with self.assertRaises(ValueError) as ctx:
                append_training_sample(board, FATAL, root / "labels.csv", root / "samples")

            self.assertIn("ilegal", str(ctx.exception).lower())
            self.assertFalse((root / "labels.csv").exists())

    def test_fatal_position_can_be_forced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            path = append_training_sample(
                board, FATAL, root / "labels.csv", root / "samples", allow_illegal=True
            )

            self.assertTrue(path.exists())

    def test_unparseable_fen_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 128, dtype=np.uint8)

            with self.assertRaises(ValueError):
                append_training_sample(board, "isto nao e uma fen", root / "labels.csv", root / "samples")

    def test_board_is_resized_to_canonical_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = np.full((200, 200, 3), 128, dtype=np.uint8)

            path = append_training_sample(board, LEGAL, root / "labels.csv", root / "samples")

            written = cv2.imread(str(path))
            self.assertEqual(written.shape[:2], (BOARD_SIZE, BOARD_SIZE))


if __name__ == "__main__":
    unittest.main()
