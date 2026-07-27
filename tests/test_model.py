from __future__ import annotations

import unittest

import numpy as np
import torch

from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.model import (
    DEFAULT_ARCH,
    ArchConfig,
    PieceClassifier,
    build_model,
    count_parameters,
    preprocess_cell_to_tensor,
)


class ArchConfigTests(unittest.TestCase):
    def test_default_is_the_architecture_that_produced_the_baseline(self) -> None:
        self.assertEqual(DEFAULT_ARCH.version, "cnn-gray-64-linear")
        self.assertEqual(DEFAULT_ARCH.in_channels, 1)

    def test_version_round_trips(self) -> None:
        for arch in (
            ArchConfig(),
            ArchConfig(channels="rgb"),
            ArchConfig(image_size=32),
            ArchConfig(head="gap"),
            ArchConfig(backbone="mobilenet_v3_small", channels="rgb", image_size=48, head="gap"),
        ):
            self.assertEqual(ArchConfig.from_version(arch.version), arch)

    def test_image_size_must_survive_three_max_pools(self) -> None:
        with self.assertRaises(ValueError):
            ArchConfig(image_size=50)
        with self.assertRaises(ValueError):
            ArchConfig(image_size=0)


class ForwardShapeTests(unittest.TestCase):
    def test_every_cnn_variant_outputs_one_logit_per_class(self) -> None:
        for arch in (
            ArchConfig(),
            ArchConfig(channels="rgb"),
            ArchConfig(image_size=32),
            ArchConfig(image_size=48),
            ArchConfig(head="gap"),
            ArchConfig(channels="rgb", image_size=32, head="gap"),
        ):
            with self.subTest(arch=arch.version):
                model = build_model(arch, pretrained=False)
                batch = torch.zeros(4, arch.in_channels, arch.image_size, arch.image_size)
                self.assertEqual(tuple(model(batch).shape), (4, len(PIECE_CLASSES)))

    def test_gap_head_is_an_order_of_magnitude_smaller(self) -> None:
        """A `Linear(8192, 256)` concentra 96% dos parametros -- e a premissa da S-29."""
        linear = count_parameters(build_model(ArchConfig(head="linear"), pretrained=False))
        gap = count_parameters(build_model(ArchConfig(head="gap"), pretrained=False))
        self.assertGreater(linear, 2_000_000)
        self.assertLess(gap, linear / 10)

    def test_temperature_starts_neutral_and_is_not_in_the_state_dict(self) -> None:
        """Se fosse buffer, todo checkpoint anterior a S-28 falharia sob strict=True."""
        model = PieceClassifier()
        self.assertEqual(model.temperature, 1.0)
        self.assertNotIn("temperature", model.state_dict())

    def test_forward_returns_raw_logits(self) -> None:
        """Aplicar a temperatura no forward mudaria o gradiente da loss no treino."""
        model = PieceClassifier().eval()
        batch = torch.randn(2, 1, 64, 64)
        with torch.no_grad():
            before = model(batch)
            model.temperature = 5.0
            after = model(batch)
        self.assertTrue(torch.equal(before, after))


class PreprocessTests(unittest.TestCase):
    def _cell(self) -> np.ndarray:
        return np.random.default_rng(0).integers(0, 256, (100, 100, 3), dtype=np.uint8)

    def test_gray_produces_one_channel(self) -> None:
        tensor = preprocess_cell_to_tensor(self._cell(), ArchConfig())
        self.assertEqual(tuple(tensor.shape), (1, 64, 64))

    def test_rgb_produces_three_channels_in_chw_order(self) -> None:
        tensor = preprocess_cell_to_tensor(self._cell(), ArchConfig(channels="rgb"))
        self.assertEqual(tuple(tensor.shape), (3, 64, 64))

    def test_resolution_follows_the_arch(self) -> None:
        for size in (32, 48, 64):
            with self.subTest(size=size):
                tensor = preprocess_cell_to_tensor(self._cell(), ArchConfig(image_size=size))
                self.assertEqual(tuple(tensor.shape), (1, size, size))

    def test_output_is_normalised_to_unit_range(self) -> None:
        tensor = preprocess_cell_to_tensor(self._cell())
        self.assertGreaterEqual(float(tensor.min()), 0.0)
        self.assertLessEqual(float(tensor.max()), 1.0)
        self.assertEqual(tensor.dtype, torch.float32)

    def test_output_feeds_the_matching_model(self) -> None:
        for arch in (ArchConfig(), ArchConfig(channels="rgb", image_size=32)):
            with self.subTest(arch=arch.version):
                tensor = preprocess_cell_to_tensor(self._cell(), arch).unsqueeze(0)
                model = build_model(arch, pretrained=False).eval()
                with torch.no_grad():
                    self.assertEqual(tuple(model(tensor).shape), (1, len(PIECE_CLASSES)))

    def test_default_argument_matches_the_baseline_arch(self) -> None:
        cell = self._cell()
        self.assertTrue(torch.equal(preprocess_cell_to_tensor(cell), preprocess_cell_to_tensor(cell, DEFAULT_ARCH)))


if __name__ == "__main__":
    unittest.main()
