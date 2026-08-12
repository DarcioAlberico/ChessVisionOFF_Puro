from __future__ import annotations

import unittest

import numpy as np
import torch

from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.model import (
    COORDINATE_CHANNELS,
    DEFAULT_ARCH,
    ArchConfig,
    PieceClassifier,
    build_model,
    coordinate_channels,
    count_parameters,
    preprocess_cell_to_tensor,
    with_coordinate_channels,
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


class CoordinateChannelTests(unittest.TestCase):
    """S-62a: os três planos constantes, e a garantia de que eles não entram por acidente."""

    def test_default_arch_has_no_coordinate_channels(self) -> None:
        self.assertFalse(DEFAULT_ARCH.coords)
        self.assertEqual(DEFAULT_ARCH.version, "cnn-gray-64-linear")
        self.assertEqual(DEFAULT_ARCH.in_channels, DEFAULT_ARCH.image_channels)

    def test_version_says_coords_and_round_trips(self) -> None:
        arch = ArchConfig(coords=True)
        self.assertEqual(arch.version, "cnn-gray-64-linear-coords")
        self.assertEqual(ArchConfig.from_version(arch.version), arch)
        # E a versao antiga continua interpretavel, sem virar um modelo com coordenadas.
        self.assertFalse(ArchConfig.from_version("cnn-gray-64-linear").coords)

    def test_input_gains_exactly_three_channels(self) -> None:
        for base in (ArchConfig(), ArchConfig(channels="rgb")):
            arch = ArchConfig(backbone=base.backbone, channels=base.channels, head=base.head, coords=True)
            with self.subTest(arch=arch.version):
                self.assertEqual(arch.in_channels, base.in_channels + COORDINATE_CHANNELS)

    def test_planes_are_constant_and_encode_parity_row_and_column(self) -> None:
        planos = coordinate_channels(square_index=9, size=8)  # fila 1, coluna 1
        self.assertEqual(tuple(planos.shape), (COORDINATE_CHANNELS, 8, 8))
        for canal, esperado in enumerate((0.0, 1 / 7, 1 / 7)):
            with self.subTest(canal=canal):
                self.assertAlmostEqual(float(planos[canal].min()), esperado, places=6)
                self.assertAlmostEqual(float(planos[canal].max()), esperado, places=6)

    def test_parity_alternates_between_neighbouring_squares(self) -> None:
        paridade = [float(coordinate_channels(i, 8)[0, 0, 0]) for i in range(8)]
        self.assertEqual(paridade, [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0])
        # E a fila seguinte comeca invertida, como no tabuleiro.
        self.assertEqual(float(coordinate_channels(8, 8)[0, 0, 0]), 1.0)

    def test_helper_is_a_no_op_without_coords(self) -> None:
        cell = torch.rand(1, 64, 64)
        self.assertIs(with_coordinate_channels(cell, 0, ArchConfig()), cell)

    def test_helper_appends_after_the_image_channels(self) -> None:
        cell = torch.rand(1, 64, 64)
        saida = with_coordinate_channels(cell, 17, ArchConfig(coords=True))
        self.assertEqual(tuple(saida.shape), (4, 64, 64))
        self.assertTrue(torch.equal(saida[:1], cell), "o canal da imagem tem de ficar em primeiro")

    def test_zeroed_extra_channels_reproduce_the_model_of_today(self) -> None:
        """O teste de paridade numérica que a S-62 pede, antes de qualquer retreino.

        Os pesos das entradas novas zerados, o resto copiado: a saída tem de ser bit a bit a
        do modelo sem coordenadas. Se não for, o canal extra não está sendo *acrescentado* --
        está deslocando a imagem para dentro de outro filtro.
        """
        torch.manual_seed(0)
        antigo = build_model(ArchConfig(), pretrained=False).eval()
        novo = build_model(ArchConfig(coords=True), pretrained=False).eval()

        estado = dict(antigo.state_dict())
        peso_antigo = estado.pop("features.0.weight")
        faltando = novo.load_state_dict(estado, strict=False)
        self.assertEqual(list(faltando.unexpected_keys), [])
        with torch.no_grad():
            novo.features[0].weight.zero_()
            novo.features[0].weight[:, :1].copy_(peso_antigo)

        cell = torch.rand(4, 1, 64, 64)
        com_coords = torch.cat(
            [with_coordinate_channels(cell[i], i, ArchConfig(coords=True)).unsqueeze(0) for i in range(4)]
        )
        with torch.no_grad():
            self.assertTrue(torch.equal(antigo(cell), novo(com_coords)))

    def test_the_extra_channels_cost_about_one_percent_of_the_parameters(self) -> None:
        base = count_parameters(build_model(ArchConfig(), pretrained=False))
        com = count_parameters(build_model(ArchConfig(coords=True), pretrained=False))
        self.assertLess((com - base) / base, 0.01)

    def test_every_coords_variant_still_outputs_one_logit_per_class(self) -> None:
        for arch in (
            ArchConfig(coords=True),
            ArchConfig(channels="rgb", coords=True),
            ArchConfig(head="gap", coords=True),
            ArchConfig(image_size=32, coords=True),
        ):
            with self.subTest(arch=arch.version):
                model = build_model(arch, pretrained=False)
                batch = torch.zeros(4, arch.in_channels, arch.image_size, arch.image_size)
                self.assertEqual(tuple(model(batch).shape), (4, len(PIECE_CLASSES)))


if __name__ == "__main__":
    unittest.main()
