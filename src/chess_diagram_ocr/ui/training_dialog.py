"""Treino disparado pela interface: o diálogo modal e a thread (S-31).

**O que sai daqui do `app_tkinter.py`.** Nove métodos e seis atributos de instância que
serviam a uma coisa só. O que importa não é o tamanho: é que a formatação das métricas --
qual delas aparece primeiro para o usuário -- é uma decisão da S-27, e ela estava enterrada
numa classe de 2.300 linhas onde ninguém a acharia para conferir.

**A ordem das métricas é a decisão, não a apresentação.** `val_board_exact_acc` vem
primeiro porque é ela que decide qual época é salva. A acurácia por casa fica em ~0,999
mesmo quando um em cada vinte tabuleiros sai com erro -- mostrá-la primeiro faria o usuário
ler um número ótimo sobre um treino medíocre.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from chess_diagram_ocr.training import TrainingRun, train_model

from . import texto
from .busy import BusyRegistry, BusyToken

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingRequest:
    """Os parâmetros do treino lidos da tela, para não viajarem soltos entre threads.

    Congelados no momento do clique de propósito: mexer nos spinboxes com o treino em
    andamento não pode mudar o que já está rodando.
    """

    csv_path: Path
    samples_dir: Path
    model_path: Path
    epochs: int
    batch_size: int
    lr: float
    fresh: bool = False
    splits_path: Path | None = None


def format_metrics(row: dict[str, Any]) -> str:
    """Uma linha de métricas de época, na ordem que a S-27 decidiu.

    Testável sem Tk, e é o que de fato vale a pena travar: a ordem é uma decisão de projeto,
    e trocá-la sem perceber é fácil.
    """
    partes: list[str] = []
    epoca = row.get("epoch")
    if epoca is not None:
        partes.append(f"época={epoca}")
    for chave, rotulo in (
        ("val_board_exact_acc", "exata/tabuleiro"),
        ("train_loss", "train_loss"),
        ("train_square_acc", "train_acc"),
        ("val_loss", "val_loss"),
        ("val_square_acc", "val_acc/casa"),
    ):
        if chave in row:
            partes.append(f"{rotulo}={float(row[chave]):.4f}")
    if row.get("is_best"):
        partes.append("(melhor até agora)")
    return " | ".join(partes)


def summarize_run(run: TrainingRun) -> str:
    """Resumo do checkpoint que ficou no disco -- a **melhor** época, não a última.

    Mostrar a última faria o usuário ler uma métrica que não corresponde ao arquivo salvo:
    desde a S-27 o treino só grava por cima quando melhora.

    **A melhor época é a que `is_best` marca, e não `history[best_epoch - 1]` (S-310).** Os dois
    coincidem num treino do zero e divergem em toda retomada: `best_epoch` é do **checkpoint**,
    e pode valer 7 sobre um histórico de duas épocas -- o `IndexError` daí subia como "Falha no
    treino" ao fim de um treino bem-sucedido. E quando não estoura, mente: indexa a época errada
    desta execução e mostra a métrica dela.

    Nenhuma época melhor que o incumbente é um resultado, e não uma falha: aí o resumo fica
    vazio de propósito, e quem diz o que aconteceu é a frase de status.
    """
    melhores = [linha for linha in run.history if linha.get("is_best")]
    melhor = melhores[-1] if melhores else {}
    resumo = format_metrics(melhor)
    if run.ece_after is not None:
        resumo += f" | T={run.temperature:.3f}"
    return resumo


class TrainingController:
    """Roda o treino numa thread e mantém o diálogo modal em dia."""

    def __init__(
        self,
        root: tk.Misc,
        *,
        request: Callable[[], TrainingRequest],
        on_status: Callable[[str], None],
        on_controls_enabled: Callable[[bool], None],
        on_finished: Callable[[], None],
        busy: BusyRegistry | None = None,
    ) -> None:
        """`busy` registra o treino como operação longa, para a janela saber o que se perde
        ao ser fechada (S-60). `None` mantém o comportamento antigo, para os testes."""
        self.root = root
        self._busy = busy
        self._busy_token: BusyToken | None = None
        self._cancel: threading.Event | None = None
        self._request = request
        self._on_status = on_status
        self._on_controls_enabled = on_controls_enabled
        self._on_finished = on_finished
        """Chamado ao fim do treino, com ou sem sucesso. É onde o modelo é invalidado --
        o `.pt` que estava em memória pode não ser mais o que está no disco (S-31)."""

        self.status_var = tk.StringVar(value="")
        self.metrics_var = tk.StringVar(value="")
        self._dialog: tk.Toplevel | None = None
        self._progress: ttk.Progressbar | None = None
        self._running = False
        self._total_epochs = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            # Rodapé (S-164): a zona de operação ao lado já mostra "treino do modelo (época 3 de
            # 8)", e uma caixa modal dizendo o mesmo é um clique para saber o que está na tela.
            self._on_status("Já existe um treino em execução.")
            return

        pedido = self._request()
        self._running = True
        self._total_epochs = pedido.epochs
        self._cancel = threading.Event()
        if self._busy is not None:
            self._busy_token = self._busy.register(
                "treino do modelo",
                # O checkpoint da melhor epoca ja esta no disco; o que se perde e o progresso
                # desde ela -- que em CPU e ~9 min por epoca, e por isso vale perguntar.
                loses_work=True,
                cancellable=True,
                detail=f"época 1 de {pedido.epochs}",
                cancel=self.cancel,
            )
        self._on_controls_enabled(False)
        self.set_text("Preparando treino...", "")
        self.open_dialog()

        threading.Thread(target=self._worker, args=(pedido, self._cancel), daemon=True).start()

    def cancel(self) -> None:
        """Pede o cancelamento. A resposta vem entre épocas, não no meio de uma (S-60)."""
        if self._cancel is None:
            return
        self._cancel.set()
        self._on_status("Cancelando treino... termina a época atual e para.")

    # ------------------------------------------------------------------------------ modal

    def open_dialog(self) -> None:
        if self._dialog is not None and self._dialog.winfo_exists():
            self._dialog.deiconify()
            self._dialog.lift()
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Treinando modelo")
        dlg.geometry("520x170")
        dlg.resizable(False, False)
        dlg.transient(self.root.winfo_toplevel())
        # Fechar esconde em vez de destruir: o treino continua rodando, e destruir a janela
        # deixaria a thread escrevendo em widgets que já não existem.
        dlg.protocol("WM_DELETE_WINDOW", dlg.withdraw)

        wrap = ttk.Frame(dlg, padding=12)
        wrap.pack(fill=tk.BOTH, expand=True)
        ttk.Label(wrap, text="Status do treino").pack(anchor="w")
        texto.acompanhar(ttk.Label(wrap, textvariable=self.status_var)).pack(anchor="w", pady=(6, 0))
        texto.acompanhar(ttk.Label(wrap, textvariable=self.metrics_var)).pack(anchor="w", pady=(4, 0))

        self._progress = ttk.Progressbar(wrap, mode="indeterminate")
        self._progress.pack(fill=tk.X, pady=(10, 0))
        self._progress.start(10)
        self._dialog = dlg

    def close_dialog(self) -> None:
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
        if self._dialog is not None and self._dialog.winfo_exists():
            self._dialog.destroy()
        self._dialog = None

    def set_text(self, status_text: str, metrics_text: str = "") -> None:
        """Atualiza o modal de qualquer thread; o worker chama isto a cada época."""
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(status_text)
            self.metrics_var.set(metrics_text)
        else:
            self.root.after(0, partial(self._set_text_now, status_text, metrics_text))

    def _set_text_now(self, status_text: str, metrics_text: str) -> None:
        self.status_var.set(status_text)
        self.metrics_var.set(metrics_text)

    # ----------------------------------------------------------------------------- worker

    def _on_progress(self, row: dict[str, Any]) -> None:
        epoca = int(row.get("epoch", 0))
        status = f"Treinando... época {epoca}/{self._total_epochs}"
        self._on_status(status)
        self.set_text(status, format_metrics(row))
        token = self._busy_token
        if token is not None:
            # Com o número, e não só com a frase: é o que faz a barra do rodapé ser determinada
            # (S-164). Época é a unidade em que o treino de verdade progride -- ~9 min cada em CPU.
            token.update(f"época {epoca} de {self._total_epochs}", feito=epoca, total=self._total_epochs)

    def _worker(self, pedido: TrainingRequest, cancel: threading.Event) -> None:
        try:
            self._on_status("Treinando modelo...")
            self.set_text("Treinando modelo...", "")
            run = train_model(
                csv_path=pedido.csv_path,
                samples_dir=pedido.samples_dir,
                model_path=pedido.model_path,
                epochs=pedido.epochs,
                batch_size=pedido.batch_size,
                lr=pedido.lr,
                progress_cb=self._on_progress,
                splits_path=pedido.splits_path,
                fresh=pedido.fresh,
                # **O `Event` que o botão "Cancelar" do rodapé aciona (S-309).** Ele existia em
                # três lugares -- `start` registra a operação como `cancellable=True`, o rodapé
                # habilita o botão, e `Trainer` sabe parar entre épocas -- e faltava nesta linha.
                # O botão respondia ao clique e o treino seguia até o fim.
                cancel_event=cancel,
            )
            resumo = summarize_run(run)
            # Sem caixa modal ao fim (S-164): o modal do treino **já está aberto** e mostra o
            # resumo em `metrics_var` -- a caixa era uma segunda cópia do que está a 20 px dela,
            # e um treino de uma hora terminava exigindo um clique para liberar a janela.
            #
            # Cancelado não é concluído nem falhou (S-309): o checkpoint da melhor época gravada
            # continua no disco e continua sendo o melhor conhecido. Dizer "Treino concluído"
            # sobre uma parada na época 2 de 8 seria a interface mentindo sobre o que ela fez.
            if run.cancelled:
                epocas = len(run.history)
                feito = f"Treino cancelado na época {epocas} de {self._total_epochs}."
                sobrou = resumo or "nenhuma época superou o checkpoint que já existia."
                self._on_status(f"{feito} {sobrou}")
                self.set_text(feito, sobrou)
            else:
                self._on_status(
                    f"Treino concluído. Melhor época: {run.best_epoch} de {len(run.history)}. {resumo}"
                )
                self.set_text("Treino concluído.", resumo)
        except Exception as exc:
            logger.exception("Falha no treino disparado pela interface.")
            self._on_status("Falha no treino.")
            self.set_text("Falha no treino.", str(exc))
            self.root.after(0, partial(messagebox.showerror, "Erro no treino", str(exc)))
        finally:
            self.root.after(0, self._finish)

    def _finish(self) -> None:
        self._running = False
        self._cancel = None
        if self._busy_token is not None:
            self._busy_token.release()
            self._busy_token = None
        self._on_controls_enabled(True)
        self.close_dialog()
        self._on_finished()
