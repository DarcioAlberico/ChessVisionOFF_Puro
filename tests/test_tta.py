"""TTA leve com voto (S-29) e a temperatura da S-28 aplicada na inferencia."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from chess_diagram_ocr.config import BOARD_SIZE, PIECE_CLASSES
from chess_diagram_ocr.inference import board_probabilities, describe_device, predict_board, tta_views
from chess_diagram_ocr.model import ArchConfig


class _ConstantModel(nn.Module):
    """Sempre a mesma resposta: isola o efeito do TTA do efeito do modelo."""

    def __init__(self, class_index: int = 0, logit: float = 4.0, arch: ArchConfig | None = None) -> None:
        super().__init__()
        self.arch = arch or ArchConfig()
        self.temperature = 1.0
        self.class_index = class_index
        self.logit = logit
        self.calls = 0

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        self.calls += x.shape[0]
        logits = torch.zeros(x.shape[0], len(PIECE_CLASSES))
        logits[:, self.class_index] = self.logit
        return logits


def _board() -> np.ndarray:
    return np.random.default_rng(0).integers(0, 256, (BOARD_SIZE, BOARD_SIZE, 3), dtype=np.uint8)


class ViewsTests(unittest.TestCase):
    def test_seven_views_and_the_first_is_the_original(self) -> None:
        board = _board()
        views = tta_views(board)
        self.assertEqual(len(views), 7)
        self.assertIs(views[0], board)

    def test_every_view_keeps_the_board_geometry(self) -> None:
        for view in tta_views(_board()):
            self.assertEqual(view.shape, (BOARD_SIZE, BOARD_SIZE, 3))

    def test_the_shifted_views_actually_differ_from_the_original(self) -> None:
        views = tta_views(_board())
        for index, view in enumerate(views[1:], start=1):
            with self.subTest(view=index):
                self.assertFalse(np.array_equal(view, views[0]))

    def test_shifts_replicate_the_border_instead_of_padding_black(self) -> None:
        """Preencher com preto inventaria uma peca escura na borda do tabuleiro."""
        board = np.full((BOARD_SIZE, BOARD_SIZE, 3), 255, dtype=np.uint8)
        for view in tta_views(board):
            self.assertGreater(int(view.min()), 200)


class ProbabilityTests(unittest.TestCase):
    def test_tta_costs_seven_forwards_worth_of_cells(self) -> None:
        model = _ConstantModel()
        board_probabilities(_board(), model, "cpu", tta=True)
        self.assertEqual(model.calls, 7 * 64)

    def test_without_tta_it_is_one_forward(self) -> None:
        model = _ConstantModel()
        board_probabilities(_board(), model, "cpu", tta=False)
        self.assertEqual(model.calls, 64)

    def test_output_is_a_probability_matrix(self) -> None:
        for tta in (False, True):
            with self.subTest(tta=tta):
                probs = board_probabilities(_board(), _ConstantModel(), "cpu", tta=tta)
                self.assertEqual(probs.shape, (64, len(PIECE_CLASSES)))
                # 1e-6, nao 1e-9: o softmax roda em float32 no modelo e so depois vira
                # float64. Exigir precisao de float64 aqui testaria o torch, nao o TTA.
                np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-6)

    def test_averaging_identical_views_changes_nothing(self) -> None:
        """Com modelo constante o voto tem de ser o proprio valor: sinal de que e media."""
        board = _board()
        single = board_probabilities(board, _ConstantModel(), "cpu", tta=False)
        voted = board_probabilities(board, _ConstantModel(), "cpu", tta=True)
        np.testing.assert_allclose(single, voted, atol=1e-12)


class TemperatureTests(unittest.TestCase):
    def test_higher_temperature_flattens_the_distribution(self) -> None:
        cold = _ConstantModel(logit=8.0)
        hot = _ConstantModel(logit=8.0)
        hot.temperature = 4.0

        confident = board_probabilities(_board(), cold, "cpu").max(axis=1)
        flattened = board_probabilities(_board(), hot, "cpu").max(axis=1)
        self.assertTrue((flattened < confident).all())

    def test_temperature_does_not_change_the_reading(self) -> None:
        """Um escalar positivo nao reordena classes: a FEN sai igual, so a confianca muda."""
        board = _board()
        neutral = _ConstantModel(class_index=3)
        scaled = _ConstantModel(class_index=3)
        scaled.temperature = 3.5

        self.assertEqual(
            predict_board(board, neutral, "cpu", constrained=False).fen_board,
            predict_board(board, scaled, "cpu", constrained=False).fen_board,
        )

    def test_default_temperature_is_neutral(self) -> None:
        model = _ConstantModel(logit=8.0)
        probs = board_probabilities(_board(), model, "cpu")
        expected = torch.softmax(torch.tensor([8.0] + [0.0] * 12), dim=0).numpy()
        np.testing.assert_allclose(probs[0], expected, atol=1e-9)


class StoredTemperatureIsNotAppliedByDefaultTests(unittest.TestCase):
    """Decisao medida da S-28: o `T` e gravado no checkpoint mas nao aplicado.

    Medido no mesmo modelo, so a temperatura mudando: o ECE no teste piora ~3x e a fila de
    revisao dobra (6 para 12 rejeitados em 320), sem mudar uma casa. Ver
    `config.APPLY_CALIBRATED_TEMPERATURE` e docs/EXPERIMENTS.md.
    """

    def _checkpoint(self, path: Path, temperature: float) -> None:
        from chess_diagram_ocr.checkpoint import save_checkpoint
        from chess_diagram_ocr.model import ArchConfig, build_model

        arch = ArchConfig()
        save_checkpoint(
            path,
            build_model(arch, pretrained=False).state_dict(),
            metadata={"arch_version": arch.version, "class_names": list(PIECE_CLASSES)},
            temperature=temperature,
        )

    def test_a_stored_temperature_is_reported_but_left_neutral(self) -> None:
        from chess_diagram_ocr.inference import load_model

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "m.pt"
            self._checkpoint(caminho, 1.85)

            model, _ = load_model(caminho)
            self.assertEqual(model.temperature, 1.0)

    def test_asking_for_it_applies_it(self) -> None:
        from chess_diagram_ocr.inference import load_model

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "m.pt"
            self._checkpoint(caminho, 1.85)

            model, _ = load_model(caminho, apply_temperature=True)
            self.assertAlmostEqual(float(model.temperature), 1.85, places=5)

    def test_the_checkpoint_still_carries_the_fitted_value(self) -> None:
        """O numero e diagnostico: T=1,85 diz que o modelo e confiante demais."""
        from chess_diagram_ocr.checkpoint import load_checkpoint

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "m.pt"
            self._checkpoint(caminho, 1.85)
            self.assertAlmostEqual(load_checkpoint(caminho).temperature, 1.85, places=5)


class DeviceDescriptionTests(unittest.TestCase):
    def test_cpu_is_named_explicitly(self) -> None:
        self.assertIn("cpu", describe_device("cpu"))

    def test_unavailable_cuda_is_flagged_not_silently_accepted(self) -> None:
        if torch.cuda.is_available():
            self.skipTest("esta maquina tem CUDA; o caso a cobrir e a ausencia dela")
        self.assertIn("indispon", describe_device("cuda"))


class ArchAwarePredictionTests(unittest.TestCase):
    def test_prediction_follows_the_model_arch(self) -> None:
        """O preprocessamento tem de seguir o modelo, senao o RGB recebe 1 canal."""
        arch = ArchConfig(channels="rgb", image_size=32)
        model = _ConstantModel(arch=arch)

        captured: list[tuple[int, ...]] = []
        original = model.forward

        def spy(x: torch.Tensor) -> torch.Tensor:
            captured.append(tuple(x.shape))
            return original(x)

        model.forward = spy  # type: ignore[method-assign]
        board_probabilities(_board(), model, "cpu")
        self.assertEqual(captured[0], (64, 3, 32, 32))


if __name__ == "__main__":
    unittest.main()
