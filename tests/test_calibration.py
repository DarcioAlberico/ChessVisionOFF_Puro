from __future__ import annotations

import unittest

import numpy as np
import torch

from chess_diagram_ocr.calibration import (
    confidence_for_accuracy,
    expected_calibration_error,
    fit_temperature,
    negative_log_likelihood,
    reliability_table,
)


def _ambiguous(count: int = 4000, classes: int = 13, scale: float = 1.0, seed: int = 0) -> tuple[torch.Tensor, torch.Tensor]:
    """Logits informativos mas ambiguos, escalados por `scale`.

    O sinal (`one_hot * 2,2`) acerta ~70% das vezes; o ruido gaussiano produz a
    ambiguidade. `scale > 1` agudiza a distribuicao sem mexer no argmax -- que e
    exatamente a deformacao "confiante demais" que o temperature scaling desfaz.

    A tentacao e gerar rotulos por `argmax` e embaralhar uma fracao deles. Nao serve:
    rotulo uniformemente aleatorio e ruido irredutivel, e nenhuma temperatura o corrige,
    entao o ECE fica alto depois da calibracao e o teste acusaria a implementacao por um
    defeito do fixture.
    """
    generator = torch.Generator().manual_seed(seed)
    targets = torch.randint(0, classes, (count,), generator=generator)
    logits = torch.nn.functional.one_hot(targets, classes).float() * 2.2
    logits = logits + torch.randn(count, classes, generator=generator)
    return logits * scale, targets


def _ece(logits: torch.Tensor, targets: torch.Tensor, temperature: float = 1.0) -> float:
    correct = (logits.argmax(dim=1) == targets).numpy().astype(np.float64)
    confidences = torch.softmax(logits / temperature, dim=1).max(dim=1).values.numpy()
    return expected_calibration_error(confidences, correct)


class FitTemperatureTests(unittest.TestCase):
    def test_temperature_scales_with_the_logits(self) -> None:
        """`T` e homogeneo de grau 1: multiplicar os logits por k multiplica `T` por k.

        E a propriedade exata que define o metodo, e o teste mais forte disponivel sem
        depender de um alvo numerico arbitrario.
        """
        logits, targets = _ambiguous()
        base = fit_temperature(logits, targets)
        for factor in (2.0, 3.0, 5.0):
            with self.subTest(factor=factor):
                self.assertAlmostEqual(fit_temperature(logits * factor, targets) / base, factor, delta=0.05)

    def test_overconfident_logits_get_flattened(self) -> None:
        logits, targets = _ambiguous(scale=3.0)
        self.assertGreater(fit_temperature(logits, targets), 1.0)

    def test_underconfident_logits_get_sharpened(self) -> None:
        logits, targets = _ambiguous(scale=0.4)
        self.assertLess(fit_temperature(logits, targets), 1.0)

    def test_reduces_negative_log_likelihood(self) -> None:
        for scale in (0.4, 1.0, 3.0):
            with self.subTest(scale=scale):
                logits, targets = _ambiguous(scale=scale)
                temperature = fit_temperature(logits, targets)
                self.assertLessEqual(
                    negative_log_likelihood(logits, targets, temperature),
                    negative_log_likelihood(logits, targets, 1.0),
                )

    def test_reduces_calibration_error(self) -> None:
        for scale in (1.0, 3.0):
            with self.subTest(scale=scale):
                logits, targets = _ambiguous(scale=scale)
                temperature = fit_temperature(logits, targets)
                self.assertLess(_ece(logits, targets, temperature), _ece(logits, targets))

    def test_calibrated_error_is_small_in_absolute_terms(self) -> None:
        """O criterio da S-28 e ECE < 0,05; um teste de "melhorou" sozinho passaria com 0,3."""
        logits, targets = _ambiguous(scale=3.0)
        self.assertLess(_ece(logits, targets, fit_temperature(logits, targets)), 0.05)

    def test_argmax_is_untouched(self) -> None:
        """Um escalar positivo nao reordena classe nenhuma -- entao a acuracia nao muda.

        E a garantia que permite calibrar sem revalidar a acuracia do modelo.
        """
        logits, targets = _ambiguous(scale=3.0)
        temperature = fit_temperature(logits, targets)
        self.assertTrue(torch.equal((logits / temperature).argmax(dim=1), logits.argmax(dim=1)))

    def test_rejects_empty_validation_set(self) -> None:
        with self.assertRaises(ValueError):
            fit_temperature(torch.zeros(0, 13), torch.zeros(0, dtype=torch.long))

    def test_rejects_mismatched_lengths(self) -> None:
        with self.assertRaises(ValueError):
            fit_temperature(torch.zeros(10, 13), torch.zeros(9, dtype=torch.long))


class ReliabilityTests(unittest.TestCase):
    def test_perfect_calibration_has_zero_error(self) -> None:
        # Confianca 0,5 acertando metade das vezes e calibracao perfeita naquela faixa.
        confidences = np.array([0.5] * 100)
        correct = np.array([1.0] * 50 + [0.0] * 50)
        self.assertAlmostEqual(expected_calibration_error(confidences, correct), 0.0, places=6)

    def test_overconfidence_shows_as_positive_gap(self) -> None:
        confidences = np.full(100, 0.95)
        correct = np.array([1.0] * 60 + [0.0] * 40)
        table = reliability_table(confidences, correct)
        self.assertEqual(len(table), 1)
        self.assertAlmostEqual(table[0].gap, 0.35, places=6)

    def test_confidence_zero_is_not_dropped(self) -> None:
        """A primeira faixa e fechada a esquerda: softmax saturado produz 0,0 exato."""
        table = reliability_table(np.zeros(10), np.zeros(10))
        self.assertEqual(sum(faixa.count for faixa in table), 10)

    def test_empty_input_is_zero_not_an_error(self) -> None:
        self.assertEqual(expected_calibration_error(np.array([]), np.array([])), 0.0)


class ThresholdDerivationTests(unittest.TestCase):
    def test_finds_the_threshold_where_accuracy_reaches_the_target(self) -> None:
        # Erros so abaixo de 0,5; acima disso tudo acerta.
        confidences = np.concatenate([np.linspace(0.0, 0.49, 50), np.linspace(0.5, 1.0, 50)])
        correct = np.concatenate([np.zeros(50), np.ones(50)])
        threshold = confidence_for_accuracy(confidences, correct, 1.0)
        self.assertIsNotNone(threshold)
        assert threshold is not None
        self.assertGreaterEqual(threshold, 0.5)

    def test_returns_none_when_no_threshold_reaches_the_target(self) -> None:
        """Erro que acontece com confianca alta nao tem limiar que o pegue.

        E o caso do bispo lido como peao com confianca 1,000 no BASELINE.md: devolver
        1,0 aqui faria o chamador acreditar que existe um ponto de corte.
        """
        confidences = np.full(100, 0.99)
        correct = np.array([1.0] * 50 + [0.0] * 50)
        self.assertIsNone(confidence_for_accuracy(confidences, correct, 0.95))

    def test_empty_input_returns_none(self) -> None:
        self.assertIsNone(confidence_for_accuracy(np.array([]), np.array([]), 0.9))


if __name__ == "__main__":
    unittest.main()
