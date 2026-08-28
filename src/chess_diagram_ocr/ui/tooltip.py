"""Tooltip simples para explicar um controle desabilitado (S-32).

Um botão cinza sem explicação é pior que um botão ausente: quem o vê não sabe se está
quebrado, se falta configuração ou se falta seleção. O critério de aceite da S-32 pede
literalmente "desabilitado com tooltip explicativo", e o Tk não traz um.

**E é a única dica da janela** (S-403). `ui/board_widget.py` tinha a segunda: mesma `Toplevel`
retirada, mesmo token de superfície, mesma borda -- e **350 ms** contra os 450 daqui. Duas dicas
com tempos diferentes na mesma tela não são duas decisões, são uma decisão tomada duas vezes: quem
passa o ponteiro da barra para o tabuleiro vê a segunda aparecer mais cedo sem que nada explique
por quê. O que ficou lá é o que só o tabuleiro sabe -- qual casa está sob o ponteiro e o que
escrever sobre ela --, e o resto passou a ser `atraso_de_dica` e `janela_de_dica`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme, tokens

TOOLTIP_DELAY_MS = 450
"""Tempo parado sobre o widget antes de a dica aparecer. Curto o bastante para quem
está procurando explicação, longo o bastante para não piscar ao atravessar a barra.

**Uma constante, e não uma por dica** (S-403): o número não é uma propriedade do widget que a
mostra, é uma propriedade da janela -- e o tabuleiro tinha o dele, 100 ms mais curto."""


def janela_de_dica(
    pai: tk.Misc,
    texto: str,
    *,
    x: int,
    y: int,
    wraplength: int = 0,
    fonte: tuple[str, int] | tuple[str, int, str] | None = None,
) -> tk.Toplevel:
    """A caixinha da dica: `Toplevel` sem moldura, na posição pedida, com a cor do tema (S-403).

    Quem chama decide **onde** e **o quê** -- a barra a põe abaixo do botão, o tabuleiro a põe ao
    lado do ponteiro. O que não se decide duas vezes é o resto: a superfície vem de
    `tokens.SUPERFICIE_DICA` e a letra de `tokens.sobre_superficie`, que é o par que a S-147
    fechou para a dica não virar letra clara sobre fundo claro sob tema escuro.

    Zero é o que o Tk entende por "não quebre linha": serve ao tabuleiro, cujas linhas já vêm
    quebradas e curtas. O padrão é zero e não 360 porque quem sabe a largura é quem escreve o
    texto -- ver a isenção que `test_ui_texto.SemLiteralTests` já registrava para este módulo.
    """
    janela = tk.Toplevel(pai)
    janela.wm_overrideredirect(True)
    janela.wm_geometry(f"+{x}+{y}")
    fundo = theme.cor_atual(tokens.SUPERFICIE_DICA)
    rotulo = ttk.Label(
        janela,
        text=texto,
        justify=tk.LEFT,
        wraplength=wraplength,
        background=fundo,
        foreground=tokens.sobre_superficie(fundo),
        relief=tk.SOLID,
        borderwidth=1,
        padding=6,
    )
    if fonte is not None:
        rotulo.configure(font=fonte)
    rotulo.pack()
    return janela


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
        # **E a morte do widget cancela o que estava agendado** (S-402). Sem isto, sair de uma
        # barra que a troca de pele destrói no mesmo gesto deixava um `after` de 450 ms marcado
        # para um widget que não existe mais: `_show` acordava, pedia `winfo_rootx` e o `TclError`
        # subia pelo `report_callback_exception` do Tk -- um traceback na saída padrão do
        # programa, por passar o ponteiro no lugar errado na hora errada.
        widget.bind("<Destroy>", self._ao_morrer, add="+")

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

    def _ao_morrer(self, event: tk.Event) -> None:
        """O widget morreu: esquece o agendamento e a janelinha, sem destruir nada (S-402).

        **Só o próprio widget conta.** `<Destroy>` sobe dos filhos, e a dica é filha do widget --
        tratar o `<Destroy>` dela como se fosse o dele apagaria a dica que acabou de aparecer.

        Não destrói a `Toplevel` porque ela é filha de quem está morrendo, e o Tk já a leva junto;
        chamar `destroy` no meio disso é que levantaria.
        """
        if event.widget is not self.widget:
            return
        self._cancel()
        self._window = None

    def _show(self) -> None:
        if self._window is not None or not self.text:
            return
        # A dica segue o tema (S-147), e o cromo dela é o de `janela_de_dica` (S-403). O fundo
        # era um amarelo-pálido cravado e a letra vinha do `Style`: sob tema escuro isso dava
        # letra clara sobre `#ffffe0` -- a única explicação que um botão desabilitado oferece,
        # ilegível.
        self._window = janela_de_dica(
            self.widget,
            self.text,
            x=self.widget.winfo_rootx() + 12,
            y=self.widget.winfo_rooty() + self.widget.winfo_height() + 6,
            wraplength=self.wraplength,
        )

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None
