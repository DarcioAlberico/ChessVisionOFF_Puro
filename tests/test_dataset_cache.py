"""Cache limitado do dataset (S-26).

O que estes testes travam nao e uma otimizacao, e uma regressao de memoria: o cache sem
teto carregava os 3.208 tabuleiros de uma epoca e chegava a 5,99 GiB de RSS medidos.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from chess_diagram_ocr.config import BOARD_SIZE
from chess_diagram_ocr.dataset import BoardFenDataset, BoardGroupedSampler, board_groups

LEGAL = "4k3/8/8/8/8/8/8/4K3"


def _fixture(root: Path, boards: int) -> tuple[Path, Path]:
    samples = root / "samples"
    samples.mkdir()
    linhas = ["filename,fen"]
    for index in range(boards):
        name = f"b{index:03d}.png"
        # Tabuleiro pequeno: o dataset redimensiona, e gravar 800x800 aqui custaria
        # 1,83 MiB por arquivo so para provar uma propriedade de contagem.
        cv2.imwrite(str(samples / name), np.full((64, 64, 3), 200, dtype=np.uint8))
        linhas.append(f"{name},{LEGAL}")
    csv_path = root / "labels.csv"
    csv_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return csv_path, samples


class CacheBoundTests(unittest.TestCase):
    def test_cache_never_exceeds_its_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), 20)
            dataset = BoardFenDataset(csv_path, samples, cache_size=4)

            for board in range(20):
                dataset[board * 64]
                self.assertLessEqual(len(dataset._board_cache), 4)

    def test_zero_disables_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), 3)
            dataset = BoardFenDataset(csv_path, samples, cache_size=0)

            for square in range(128):
                dataset[square]
            self.assertEqual(len(dataset._board_cache), 0)
            self.assertEqual(dataset.cache_hits, 0)

    def test_least_recently_used_is_the_one_evicted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), 5)
            dataset = BoardFenDataset(csv_path, samples, cache_size=2)

            dataset[0 * 64]
            dataset[1 * 64]
            dataset[0 * 64]  # renova o tabuleiro 0
            dataset[2 * 64]  # deve expulsar o 1, nao o 0
            self.assertEqual(set(dataset._board_cache), {0, 2})

    def test_cache_returns_the_same_image_not_a_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), 2)
            dataset = BoardFenDataset(csv_path, samples, cache_size=2)

            first = dataset._load_board(0)
            self.assertIs(dataset._load_board(0), first)
            self.assertEqual(dataset.cache_hits, 1)


class HitRateTests(unittest.TestCase):
    """O cache com teto so e barato porque o amostrador agrupa -- os dois itens sao um so."""

    def _hit_rate(self, order: list[int], cache_size: int, boards: int = 40) -> float:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), boards)
            dataset = BoardFenDataset(csv_path, samples, cache_size=cache_size)
            for index in order:
                dataset[index]
            return dataset.cache_hit_rate

    def test_grouped_order_has_a_high_hit_rate_with_a_small_cache(self) -> None:
        sampler = BoardGroupedSampler(
            board_groups([(b, s) for b in range(40) for s in range(64)]),
            seed=5,
            boards_per_chunk=8,
        )
        self.assertGreater(self._hit_rate(list(sampler), cache_size=8), 0.95)

    def test_unstructured_shuffle_defeats_a_small_cache(self) -> None:
        rng = np.random.default_rng(0)
        order = rng.permutation(40 * 64).tolist()
        self.assertLess(self._hit_rate(order, cache_size=8), 0.5)

    def test_sequential_access_needs_a_cache_of_one(self) -> None:
        """E por isso que o loader de validacao nao precisa de cache grande."""
        self.assertGreater(self._hit_rate(list(range(40 * 64)), cache_size=1), 0.98)


class DefaultsTests(unittest.TestCase):
    def test_default_cache_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), 2)
            self.assertGreater(BoardFenDataset(csv_path, samples).cache_size, 0)

    def test_negative_cache_size_is_clamped_to_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), 2)
            self.assertEqual(BoardFenDataset(csv_path, samples, cache_size=-5).cache_size, 0)

    def test_hit_rate_is_zero_before_any_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), 2)
            self.assertEqual(BoardFenDataset(csv_path, samples).cache_hit_rate, 0.0)

    def test_boards_are_still_resized_to_the_canonical_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, samples = _fixture(Path(tmp), 1)
            dataset = BoardFenDataset(csv_path, samples)
            self.assertEqual(dataset._load_board(0).shape, (BOARD_SIZE, BOARD_SIZE, 3))


if __name__ == "__main__":
    unittest.main()
