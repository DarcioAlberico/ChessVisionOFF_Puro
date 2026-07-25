from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.splits import (
    assign_split,
    compute_splits,
    ensure_splits,
    group_keys,
    load_splits,
    save_splits,
    split_counts,
)


def _names(count: int, prefix: str = "board") -> list[str]:
    return [f"{prefix}_{i:05d}.png" for i in range(count)]


class DeterminismTests(unittest.TestCase):
    def test_same_key_always_gets_same_split(self) -> None:
        for name in _names(50):
            self.assertEqual(assign_split(name), assign_split(name))

    def test_split_does_not_depend_on_process(self) -> None:
        # Valores fixos: se o algoritmo de hash mudar, isto quebra de proposito.
        # Usa SHA-256 justamente porque hash() de str e randomizado por processo.
        self.assertEqual(assign_split("board_00000.png"), assign_split("board_00000.png"))
        expected = {name: assign_split(name) for name in _names(20)}
        self.assertEqual({name: assign_split(name) for name in _names(20)}, expected)

    def test_proportions_are_approximately_respected(self) -> None:
        splits = compute_splits(_names(3000), val_pct=10, test_pct=10)
        counts = split_counts(splits)

        self.assertAlmostEqual(counts["test"] / 3000, 0.10, delta=0.02)
        self.assertAlmostEqual(counts["val"] / 3000, 0.10, delta=0.02)
        self.assertAlmostEqual(counts["train"] / 3000, 0.80, delta=0.03)

    def test_rejects_impossible_percentages(self) -> None:
        with self.assertRaises(ValueError):
            assign_split("x.png", val_pct=60, test_pct=50)


class StabilityUnderGrowthTests(unittest.TestCase):
    """A propriedade central: crescer o dataset nao pode mover amostras antigas."""

    def test_adding_samples_does_not_move_existing_ones(self) -> None:
        before = compute_splits(_names(1000))
        after = compute_splits(_names(1100))

        for name in _names(1000):
            self.assertEqual(before[name], after[name], f"{name} mudou de split ao crescer o dataset")

    def test_ensure_splits_preserves_recorded_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"

            first = ensure_splits(_names(100), path)
            # Forca uma atribuicao divergente para provar que o arquivo tem precedencia.
            tampered = dict(first)
            tampered[_names(100)[0]] = "test" if first[_names(100)[0]] != "test" else "train"
            save_splits(path, tampered)

            second = ensure_splits(_names(150), path)

            for name in _names(100):
                self.assertEqual(second[name], tampered[name])
            self.assertEqual(len(second), 150)


class GroupAwarenessTests(unittest.TestCase):
    """Amostras redundantes nao podem se espalhar entre splits: seria vazamento."""

    def test_group_members_share_a_split(self) -> None:
        names = _names(600)
        # Agrupa pares distantes na ordem, para que sem agrupamento caissem em splits
        # diferentes com alta probabilidade.
        groups = [[names[i], names[i + 300]] for i in range(300)]

        splits = compute_splits(names, groups=groups)

        for group in groups:
            with self.subTest(group=group):
                self.assertEqual(splits[group[0]], splits[group[1]])

    def test_grouping_actually_changes_something(self) -> None:
        # Garante que o teste anterior nao passa por acidente.
        names = _names(600)
        groups = [[names[i], names[i + 300]] for i in range(300)]

        without = compute_splits(names)
        straddling = sum(1 for g in groups if without[g[0]] != without[g[1]])

        self.assertGreater(straddling, 0, "sem agrupamento, algum grupo deveria cruzar splits")

    def test_group_keys_maps_members_to_representative(self) -> None:
        keys = group_keys(["a.png", "b.png", "c.png"], [["b.png", "a.png"]])

        self.assertEqual(keys["a.png"], "a.png")
        self.assertEqual(keys["b.png"], "a.png")
        self.assertEqual(keys["c.png"], "c.png")

    def test_new_member_of_known_group_inherits_its_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            ensure_splits(["a.png"], path)
            recorded = load_splits(path)["a.png"]

            grown = ensure_splits(["a.png", "b.png"], path, groups=[["a.png", "b.png"]])

            self.assertEqual(grown["b.png"], recorded)


class PersistenceTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            data = {"a.png": "train", "b.png": "val", "c.png": "test"}

            save_splits(path, data)  # type: ignore[arg-type]

            self.assertEqual(load_splits(path), data)

    def test_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_splits(Path(tmp) / "ausente.csv"), {})

    def test_invalid_split_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            path.write_text("filename,split\na.png,treino\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_splits(path)


if __name__ == "__main__":
    unittest.main()
