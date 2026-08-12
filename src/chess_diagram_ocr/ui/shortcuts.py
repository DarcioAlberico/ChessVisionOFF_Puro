"""Atalhos de teclado do ciclo corrigir → salvar → próximo (S-20/S-31).

**A guarda é o item, não o `bind`.** Os atalhos ficam ligados na janela inteira
(`bind_all`), porque o usuário pode estar com o foco em qualquer widget quando aperta
`←`. Mas `←` dentro do campo de FEN pertence ao campo -- move o cursor --, e `Del` dentro
dele apaga um caractere. Sem a guarda, digitar uma FEN à mão trocaria de diagrama a cada
seta e apagaria a peça selecionada a cada `Delete`.

Que a regra viva num módulo próprio é o que a torna verificável: `ignores_widget` responde
sim ou não sobre uma classe de widget, sem abrir janela nenhuma.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from tkinter import ttk

TEXT_ENTRY_WIDGETS: tuple[type, ...] = (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox)
"""Widgets em que as teclas de navegação são do widget, não do app.

`ttk.Spinbox` está aqui por causa do seletor "Selecionado": as setas dentro dele já
incrementam o número, e deixar o atalho passar mudaria o diagrama duas vezes por tecla."""


def ignores_widget(widget: object) -> bool:
    """Se o atalho deve ceder a vez para o widget que tem o foco."""
    return isinstance(widget, TEXT_ENTRY_WIDGETS)


def guard(handler: Callable[[], None]) -> Callable[[tk.Event], str | None]:
    """Envolve o handler com a guarda de foco.

    Devolve `"break"` quando trata a tecla, para o Tk não a repassar adiante, e `None`
    quando cede -- que é o que faz o `Entry` continuar recebendo a seta normalmente.
    """

    def _wrapped(event: tk.Event) -> str | None:
        if ignores_widget(getattr(event, "widget", None)):
            return None
        handler()
        return "break"

    return _wrapped


def bind_shortcuts(root: tk.Misc, bindings: Mapping[str, Callable[[], None]]) -> None:
    """Liga os atalhos na janela inteira, cada um sob a guarda de foco."""
    for sequence, handler in bindings.items():
        root.bind_all(sequence, guard(handler))
