"""Formatação das métricas de treino mostradas na interface (S-27/S-31).

Não abre janela: o que vale a pena travar aqui é a **ordem** das métricas e qual época o
resumo descreve, e as duas são decisões de projeto que um refatoramento desfaz sem querer.
"""

from __future__ import annotations

import threading
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.training import TrainingRun
from chess_diagram_ocr.ui import training_dialog
from chess_diagram_ocr.ui.training_dialog import (
    TrainingController,
    TrainingRequest,
    format_metrics,
    summarize_run,
)

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
                {"epoch": 1, "val_board_exact_acc": 0.90, "is_best": True},
                {"epoch": 2, "val_board_exact_acc": 0.99, "is_best": True},
                {"epoch": 3, "val_board_exact_acc": 0.80, "is_best": False},
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

    def test_o_best_epoch_do_checkpoint_nao_indexa_o_historico_desta_execucao(self) -> None:
        """S-310: numa retomada, `best_epoch` é do **checkpoint**, e o histórico é desta rodada.

        Um treino retomado de um checkpoint com `best_epoch=7`, cancelado na segunda época,
        chegava aqui com `history` de duas linhas e `best_epoch=7`. `history[6]` estourava
        `IndexError`, o `except` do `_worker` o apanhava, e a interface anunciava "Falha no
        treino" ao fim de um treino que gravou o que devia gravar. Quando não estourava --
        histórico maior que `best_epoch` -- era pior: mostrava calado a métrica da época errada.

        Quem sabe qual época ficou no disco é `is_best`, que `run_epoch` carimba em toda linha.
        """
        run = TrainingRun(
            history=[
                {"epoch": 1, "val_board_exact_acc": 0.91, "is_best": True},
                {"epoch": 2, "val_board_exact_acc": 0.88, "is_best": False},
            ],
            best_epoch=7,
        )

        resumo = summarize_run(run)

        self.assertIn("0.9100", resumo)
        self.assertNotIn("0.8800", resumo)

    def test_nenhuma_epoca_melhor_que_o_incumbente_nao_e_falha(self) -> None:
        """Resultado legítimo de uma retomada: o resumo fica vazio, e quem fala é o status."""
        run = TrainingRun(
            history=[{"epoch": 1, "val_board_exact_acc": 0.70, "is_best": False}],
            best_epoch=3,
        )

        self.assertEqual(summarize_run(run), "")


class CancelarDeVerdadeTests(unittest.TestCase):
    """O botão "Cancelar" do treino chega ao treino (S-309).

    **O defeito era uma linha ausente, com três presenças que a faziam parecer existir.**
    `start` registrava a operação no `BusyRegistry` como `cancellable=True` e passava o `Event`;
    o rodapé habilitava o botão por causa disso; e o `Trainer` sabe parar entre épocas desde a
    S-60. Só que `_worker` recebia `cancel` e não o repassava a `train_model`: o botão respondia
    ao clique, o rodapé dizia "cancelando", e as oito épocas rodavam até o fim -- ~9 min cada
    em CPU.

    O par com a S-310 não é acidente. Ligar o cancelamento torna comum o caso
    `len(history) < best_epoch`, que era o `IndexError` da S-310: cancelar na segunda época de
    uma retomada faria a interface anunciar "Falha no treino" sobre um cancelamento correto.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def _controlador(self) -> TrainingController:
        return TrainingController(
            self.root,
            request=lambda: TrainingRequest(
                csv_path=Path("data/labels.csv"),
                samples_dir=Path("data/samples"),
                model_path=Path("models/x.pt"),
                epochs=2,
                batch_size=8,
                lr=1e-3,
                splits_path=Path("data/splits.csv"),
                fresh=False,
            ),
            on_status=lambda _t: None,
            on_controls_enabled=lambda _v: None,
            on_finished=lambda: None,
        )

    def test_o_evento_de_cancelamento_chega_ao_treino(self) -> None:
        controlador = self._controlador()
        evento = threading.Event()

        with mock.patch.object(training_dialog, "train_model") as treino:
            treino.return_value = TrainingRun(history=[], best_epoch=0)
            controlador._worker(controlador._request(), evento)

        self.assertIs(treino.call_args.kwargs.get("cancel_event"), evento)

    def test_cancelado_nao_e_anunciado_como_concluido(self) -> None:
        """"Treino concluído" sobre uma parada na época 2 de 8 é a interface mentindo."""
        controlador = self._controlador()
        frases: list[str] = []
        controlador._on_status = frases.append  # type: ignore[method-assign]

        with mock.patch.object(training_dialog, "train_model") as treino:
            treino.return_value = TrainingRun(
                cancelled=True,
                history=[{"epoch": 1, "val_board_exact_acc": 0.9, "is_best": True}],
                best_epoch=1,
            )
            controlador._worker(controlador._request(), threading.Event())

        self.assertTrue(any("cancelado" in frase.lower() for frase in frases), frases)
        self.assertFalse(any("concluído" in frase.lower() for frase in frases), frases)


if __name__ == "__main__":
    unittest.main()
