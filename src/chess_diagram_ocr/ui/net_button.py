"""O botão "Corrigir pela rede": consentimento, thread e ciclo de vida do envio (S-32/S-49).

Saiu do `ResultPanel` porque não é edição de diagrama: é o único caminho do projeto em que
**bytes saem da máquina**, e ele carrega três portas de autorização, uma thread, um botão
que se desabilita sozinho e um tooltip que explica por quê. Nada disso tem a ver com as três
listas paralelas que o editor guarda, e misturado ali fazia a regra de gravação dividir
arquivo com a regra de rede.

O que fica aqui é o **mecanismo**; o que o resultado significa continua no editor: quem
recebe a FEN corrigida é `on_corrected`, e é o `DiagramEditorModel` que registra a
procedência (`net-remoto`) para que a coluna `corrected_by` não conte leitura de terceiro
como trabalho humano (S-52).
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from functools import partial
from tkinter import messagebox, ttk

import numpy as np

from chess_diagram_ocr.fen_utils import is_valid_fen
from chess_diagram_ocr.net_correction import RemoteFenProvider, build_provider
from chess_diagram_ocr.settings import RemoteFenSettings

from . import estilos, strings
from .tooltip import Tooltip

__all__ = ["NetCorrectionButton"]


class NetCorrectionButton:
    """Encapsula o botão, o tooltip e o envio. Não conhece o editor -- só recebe callbacks."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        settings: Callable[[], RemoteFenSettings],
        board_image: Callable[[], tuple[int, np.ndarray] | None],
        on_status: Callable[[str], None],
        on_consent: Callable[[RemoteFenSettings], bool],
        on_corrected: Callable[[int, str], None],
        schedule: Callable[[int, Callable[[], None]], object],
    ) -> None:
        self._settings = settings
        self._board_image = board_image
        """Devolve `(índice, imagem)` do diagrama selecionado, ou `None` se não há nenhum."""

        self._on_status = on_status
        self._on_consent = on_consent
        """Pergunta ao usuário se a imagem pode sair da máquina, e devolve a resposta.

        Mora fora daqui porque a resposta afirmativa com "não perguntar novamente" tem de ser
        **gravada** nas preferências, e persistência não é assunto de widget."""

        self._on_corrected = on_corrected
        self._schedule = schedule
        """`widget.after`: a thread não pode tocar em Tk, então tudo volta pela fila de eventos."""

        self._running = False

        self.button = ttk.Button(
            parent,
            text=strings.CORRIGIR_PELA_REDE,
            command=self.correct,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        )
        # Desabilitado até haver configuração, e com o motivo a um pouso de ponteiro: um
        # botao cinza sem explicacao e pior que um botao ausente (S-32).
        self.tooltip = Tooltip(self.button)
        self.refresh()

    def pack(self, **kwargs: object) -> None:
        self.button.pack(**kwargs)  # type: ignore[arg-type]

    def refresh(self) -> None:
        """Habilita ou desabilita conforme a configuração, e explica o porquê.

        Chamado na construção e sempre que as preferências mudam. O tooltip carrega a razão
        exata -- "não configurado" e "configurado e desligado" pedem ações diferentes.
        """
        configuracao = self._settings()
        disponivel = configuracao.is_usable and not self._running
        self.button.configure(state=tk.NORMAL if disponivel else tk.DISABLED)
        self.tooltip.set_text(configuracao.disabled_reason())

    def correct(self) -> None:
        """Segunda opinião de um serviço externo. **Envia a imagem para fora da máquina.**

        Três portas antes de qualquer byte sair: haver diagrama, haver configuração que
        autorize (S-32) e o usuário ter consentido com aquele host.
        """
        if self._running:
            return

        selecionado = self._board_image()
        if selecionado is None:
            # Pré-condição no rodapé (S-164).
            self._on_status("Não há diagrama lido para corrigir.")
            return

        configuracao = self._settings()
        provedor = build_provider(configuracao)
        if provedor is None:
            # Não deveria acontecer -- o botao esta desabilitado --, mas o atalho de teclado
            # e o código de teste chegam aqui, e "desabilitado na tela" não e uma garantia.
            messagebox.showinfo(strings.CORRIGIR_PELA_REDE, configuracao.disabled_reason())
            return

        if not configuracao.acknowledged and not self._on_consent(configuracao):
            self._on_status("Envio para o servico externo cancelado.")
            return

        idx, board_rgb = selecionado
        self._running = True
        self.button.configure(state=tk.DISABLED)
        self._on_status(f"Corrigindo FEN via {provedor.name}...")
        threading.Thread(target=self._worker, args=(provedor, idx, board_rgb), daemon=True).start()

    def _worker(self, provider: RemoteFenProvider, idx: int, board_rgb: np.ndarray) -> None:
        try:
            fen = provider.predict(board_rgb)
            if not is_valid_fen(fen):
                raise ValueError("API retornou FEN inválida.")
            self._schedule(0, partial(self._on_corrected, idx, fen))
        except Exception as exc:
            self._schedule(0, partial(self._error, exc))
        finally:
            self._schedule(0, self._finish)

    def _finish(self) -> None:
        self._running = False
        self.refresh()

    def _error(self, exc: Exception) -> None:
        self._on_status("Falha ao corrigir com Net.")
        messagebox.showerror(strings.CORRIGIR_PELA_REDE, f"Não foi possível corrigir o FEN:\n{exc}")
