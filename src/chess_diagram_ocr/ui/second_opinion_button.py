"""O botão "2ª opinião": um segundo leitor **local** e a thread dele (S-66).

Irmão do `net_button` e deliberadamente mais simples, porque lhe falta a única coisa que
tornava aquele complicado: **nada sai da máquina**. Sem envio não há aviso a mostrar, host a
nomear nem consentimento a gravar -- sobram o botão, a thread e o ciclo de vida.

Não foi feito como um modo do `NetCorrectionButton` justamente por isso. Aquele botão carrega
três portas de autorização que existem para provar que nenhum byte parte sem permissão
(S-32), e passar por elas um caminho que não usa a rede transformaria a prova num `if`.

O que fica aqui é o mecanismo; o que o resultado significa é do editor: quem recebe a leitura
é `on_read`, e é o `DiagramEditorModel.mark_second_opinion` que adota a posição, guarda as
casas em disputa e registra a procedência `segunda-opiniao`.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from functools import partial
from tkinter import messagebox, ttk

import numpy as np

from chess_diagram_ocr.settings import LocalReaderSettings
from chess_diagram_ocr.tsoj_reader import TsojUnavailableError, build_local_provider

from .tooltip import Tooltip

logger = logging.getLogger(__name__)

__all__ = ["SecondOpinionButton"]


class SecondOpinionButton:
    """Encapsula o botão, o tooltip e a leitura. Não conhece o editor -- só callbacks."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        settings: Callable[[], LocalReaderSettings],
        board_image: Callable[[], tuple[int, np.ndarray] | None],
        on_status: Callable[[str], None],
        on_read: Callable[[int, str], None],
        schedule: Callable[[int, Callable[[], None]], object],
    ) -> None:
        self._settings = settings
        self._board_image = board_image
        self._on_status = on_status
        self._on_read = on_read
        self._schedule = schedule
        """`widget.after`: a thread não pode tocar em Tk, então tudo volta pela fila."""

        self._running = False

        self.button = ttk.Button(parent, text="2ª opinião", command=self.read)
        self.tooltip = Tooltip(self.button)
        self.refresh()

    def pack(self, **kwargs: object) -> None:
        self.button.pack(**kwargs)  # type: ignore[arg-type]

    def refresh(self) -> None:
        """Habilita ou desabilita conforme a configuração, e explica o porquê no tooltip."""
        configuracao = self._settings()
        disponivel = configuracao.is_usable and not self._running
        self.button.configure(state=tk.NORMAL if disponivel else tk.DISABLED)
        self.tooltip.set_text(configuracao.disabled_reason())

    def read(self) -> None:
        """Lê o diagrama selecionado com o segundo modelo. Roda inteiramente local."""
        if self._running:
            return

        selecionado = self._board_image()
        if selecionado is None:
            # Pré-condição no rodapé (S-164).
            self._on_status("Não há diagrama para ler.")
            return

        leitor = build_local_provider(self._settings())
        if leitor is None:
            # O botao esta desabilitado, mas o atalho de teclado e o roteiro headless chegam
            # aqui: "desabilitado na tela" nunca foi garantia.
            messagebox.showinfo("2ª opinião", self._settings().disabled_reason())
            return

        idx, board_rgb = selecionado
        self._running = True
        self.button.configure(state=tk.DISABLED)
        # O primeiro uso carrega 232,8 MiB de peso e leva ~7 s; os seguintes, ~0,3 s. Dizer
        # isso na barra evita que a primeira espera pareca travamento.
        self._on_status("Lendo com o segundo modelo (o primeiro uso carrega os pesos)...")
        threading.Thread(target=self._worker, args=(leitor, idx, board_rgb), daemon=True).start()

    def _worker(self, leitor: object, idx: int, board_rgb: np.ndarray) -> None:
        try:
            placement = leitor.predict(board_rgb)  # type: ignore[attr-defined]
            self._schedule(0, partial(self._on_read, idx, placement))
        except Exception as exc:
            self._schedule(0, partial(self._error, exc))
        finally:
            self._schedule(0, self._finish)

    def _finish(self) -> None:
        self._running = False
        self.refresh()

    def _error(self, exc: Exception) -> None:
        self._on_status("Falha na segunda leitura.")
        if isinstance(exc, TsojUnavailableError):
            # Erro de instalacao, nao de leitura: a mensagem ja diz o que fazer, e um
            # traceback no log so esconderia isso.
            messagebox.showerror("2ª opinião", str(exc))
            return
        logger.exception("Segunda leitura falhou.")
        messagebox.showerror("2ª opinião", f"Não foi possível ler o diagrama:\n{exc}")
