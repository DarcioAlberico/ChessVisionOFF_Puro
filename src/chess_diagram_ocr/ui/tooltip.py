"""Tooltip simples para explicar um controle desabilitado (S-32).

Um botão cinza sem explicação é pior que um botão ausente: quem o vê não sabe se está
quebrado, se falta configuração ou se falta seleção. O critério de aceite da S-32 pede
literalmente "desabilitado com tooltip explicativo", e o Tk não traz um.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

TOOLTIP_DELAY_MS = 450
"""Tempo parado sobre o widget antes de a dica aparecer. Curto o bastante para quem
está procurando explicação, longo o bastante para não piscar ao atravessar a barra."""


class Tooltip:
    """Dica de texto ao pousar o ponteiro sobre um widget.

    O texto é trocável (`set_text`) porque o motivo de um botão estar desabilitado muda --
    "não configurado" e "configurado e desligado" são situações diferentes -- e recriar o
    tooltip a cada mudança perderia os bindings.
    """

    def __init__(self, widget: tk.Misc, text: str = "", *, wraplength: int = 360) -> None:
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self._window: tk.Toplevel | None = None
        self._after: str | None = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        # Um clique também esconde: com o botao desabilitado o clique não faz nada, e deixar
        # a dica na tela pareceria que fez.
        widget.bind("<ButtonPress>", self._hide, add="+")

    def set_text(self, text: str) -> None:
        self.text = text
        if not text:
            self._hide()

    def _schedule(self, _event: tk.Event | None = None) -> None:
        if not self.text:
            return
        self._cancel()
        self._after = self.widget.after(TOOLTIP_DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self) -> None:
        if self._window is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        janela = tk.Toplevel(self.widget)
        janela.wm_overrideredirect(True)
        janela.wm_geometry(f"+{x}+{y}")
        ttk.Label(
            janela,
            text=self.text,
            justify=tk.LEFT,
            wraplength=self.wraplength,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            padding=6,
        ).pack()
        self._window = janela

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None
