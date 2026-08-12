"""Formatação das métricas de treino mostradas na interface (S-27/S-31).

Não abre janela: o que vale a pena travar aqui é a **ordem** das métricas e qual época o
resumo descreve, e as duas são decisões de projeto que um refatoramento desfaz sem querer.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.training import TrainingRun
from chess_diagram_ocr.ui.training_dialog import format_metrics, summarize_run

EPOCA = {
    "epoch": 3,
    "train_loss": 0.1234,
    "train_square_acc": 0.99123,
    "val_loss": 0.2345,
    "val_square_acc": 0.99876,
    "val_board_exact_acc": 0.98765,
}


class FormatTests(unittest.TestCase):
    def test_the_deciding_metric_comes_before_the_flattering_one(self) -> None:
        """`val_board_exact_acc` decide qual época é salva; `val_acc/casa` fica ~0,999 sempre.

        Mostrar a acurácia por casa primeiro faria o usuário ler um número ótimo sobre um
        treino em que um em cada vinte tabuleiros sai com erro.
        """
        linha = format_metrics(EPOCA)
        self.assertLess(linha.index("exata/tabuleiro"), linha.index("val_acc/casa"))

    def test_the_epoch_number_opens_the_line(self) -> None:
        self.assertTrue(format_metrics(EPOCA).startswith("época=3"))

    def test_metrics_are_shown_with_four_decimals(self) -> None:
        self.assertIn("exata/tabuleiro=0.9877", format_metrics(EPOCA))

    def test_a_missing_metric_is_omitted_instead_of_shown_as_zero(self) -> None:
        """Zero é um valor; ausente não é. Confundi-los inventaria um treino péssimo."""
        linha = format_metrics({"epoch": 1, "train_loss": 0.5})
        self.assertNotIn("val_acc", linha)
        self.assertNotIn("exata/tabuleiro", linha)

    def test_the_best_epoch_so_far_is_flagged(self) -> None:
        self.assertIn("melhor até agora", format_metrics({**EPOCA, "is_best": True}))

    def test_an_empty_row_yields_an_empty_line_without_raising(self) -> None:
        self.assertEqual(format_metrics({}), "")


class SummaryTests(unittest.TestCase):
    def _run(self, **extra: object) -> TrainingRun:
        return TrainingRun(
            history=[
                {"epoch": 1, "val_board_exact_acc": 0.90},
                {"epoch": 2, "val_board_exact_acc": 0.99},
                {"epoch": 3, "val_board_exact_acc": 0.80},
            ],
            best_epoch=2,
            **extra,  # type: ignore[arg-type]
        )

    def test_the_summary_describes_the_saved_epoch_not_the_last_one(self) -> None:
        """Desde a S-27 o treino só grava por cima quando melhora.

        Resumir a última época mostraria 0,80 enquanto o arquivo no disco é o de 0,99 --
        uma métrica que não corresponde a nada que exista.
        """
        resumo = summarize_run(self._run())
        self.assertIn("época=2", resumo)
        self.assertIn("0.9900", resumo)

    def test_the_calibration_temperature_appears_only_when_it_was_measured(self) -> None:
        self.assertNotIn("T=", summarize_run(self._run()))
        self.assertIn("T=1.234", summarize_run(self._run(ece_after=0.01, temperature=1.234)))

    def test_a_run_with_no_history_does_not_raise(self) -> None:
        self.assertEqual(summarize_run(TrainingRun()), "")


if __name__ == "__main__":
    unittest.main()
