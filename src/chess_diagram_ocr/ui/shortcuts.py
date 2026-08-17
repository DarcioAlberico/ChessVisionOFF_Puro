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


def owns_key(widget: object, sequence: str) -> bool:
    """Se aquele widget já declarou um `bind` próprio para aquela sequência (S-117).

    **O defeito que isto conserta.** `ui/study_panel.py` liga `<Left>`/`<Right>` no canvas do
    tabuleiro de estudo a `undo_move`/`redo_move`, e esses handlers devolvem `None`. O
    `bind_all` daqui liga as mesmas teclas ao editor. Sem esta pergunta, os **dois** disparam:
    analisar uma posição com as setas na aba Análise movia, invisivelmente, o cursor do editor
    em outra aba -- e o que o `Ctrl+S` seguinte gravava deixava de ser o diagrama que a pessoa
    achava que estava selecionado.

    A alternativa mais barata era `undo_move`/`redo_move` devolverem `"break"`. Ela resolve
    este caso e não o próximo: a regra "quem declarou a tecla fica com ela" vale para todo
    atalho que vier depois, e é por isso que ela mora aqui e não lá.

    `widget.bind(seq)` sem callback **consulta** em vez de ligar, e devolve string vazia quando
    não há binding. Um widget destruído ou de outra biblioteca levanta, e aí a resposta é não:
    não ceder é o comportamento anterior, que é o certo diante de dúvida.
    """
    consulta = getattr(widget, "bind", None)
    if consulta is None:
        return False
    try:
        return bool(str(consulta(sequence)).strip())
    except Exception:  # noqa: BLE001 - widget destruido, ou que nao implementa `bind`
        return False


def guard(handler: Callable[[], None], sequence: str = "") -> Callable[[tk.Event], str | None]:
    """Envolve o handler com a guarda de foco.

    Devolve `"break"` quando trata a tecla, para o Tk não a repassar adiante, e `None`
    quando cede -- que é o que faz o `Entry` continuar recebendo a seta normalmente.

    Cede em **dois** casos: o widget é de texto (`ignores_widget`), ou ele já declarou binding
    próprio para aquela sequência (`owns_key`, S-117). `sequence=""` desliga a segunda
    pergunta, e existe para quem chama `guard` sem saber qual tecla ligou.
    """

    def _wrapped(event: tk.Event) -> str | None:
        alvo = getattr(event, "widget", None)
        if ignores_widget(alvo):
            return None
        if sequence and owns_key(alvo, sequence):
            return None
        handler()
        return "break"

    return _wrapped


def bind_shortcuts(root: tk.Misc, bindings: Mapping[str, Callable[[], None]]) -> None:
    """Liga os atalhos na janela inteira, cada um sob a guarda de foco."""
    for sequence, handler in bindings.items():
        root.bind_all(sequence, guard(handler, sequence))
