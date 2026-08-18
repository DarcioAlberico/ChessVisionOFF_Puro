"""A legenda de atalhos do menu Ajuda (S-165).

**O defeito.** Dez atalhos ligados, e **nenhum** aparecia na interface: nem menu, nem legenda, nem
tooltip. Depois da S-150 isso deixou de ser conveniência -- num notebook de 1366×768 o `Ctrl+S` era
o único caminho para salvar, porque o botão não cabia na tela, e a tecla não estava escrita em
lugar nenhum do programa.

**Gerada da mesma tabela que liga as teclas** (`ui/atalhos.py`). Uma segunda lista escrita à mão
diverge da primeira -- é o que aconteceu com os rótulos de procedência antes da S-04, e o que a
S-134 documenta sobre índice que ninguém verifica. Aqui a divergência é impossível por construção:
esta janela **percorre** `ATALHOS`, e quem acrescentar uma tecla ganha a linha de graça.

O módulo é só a janela; a decisão do que cada tecla faz é da tabela.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import atalhos, theme, tipografia, tokens

__all__ = ["JanelaDeAtalhos", "abrir"]

TITULO = "Atalhos de teclado"


class JanelaDeAtalhos(tk.Toplevel):
    """Uma linha por atalho: a tecla à esquerda, o que ela faz à direita.

    `Toplevel` e não `messagebox`: a tecla precisa de destaque tipográfico próprio (é dado, e vai
    em monoespaçada pela S-149) e a caixa do sistema só sabe mostrar um bloco de texto -- onde
    `Ctrl+S` e a frase ao lado teriam a mesma aparência, que é justamente o que não ajuda a achar
    a linha certa.
    """

    def __init__(self, pai: tk.Misc) -> None:
        super().__init__(pai)
        self.title(TITULO)
        self.transient(pai if isinstance(pai, (tk.Tk, tk.Toplevel)) else None)
        self.resizable(False, False)

        moldura = ttk.Frame(self, padding=14)
        moldura.pack(fill=tk.BOTH, expand=True)
        ttk.Label(moldura, text=TITULO, font=theme.fonte_atual(tipografia.TITULO)).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        for linha, atalho in enumerate(atalhos.ATALHOS, start=1):
            ttk.Label(moldura, text=atalho.rotulo, font=theme.fonte_atual(tipografia.DADO)).grid(
                row=linha, column=0, sticky="w", padx=(0, 18), pady=2
            )
            ttk.Label(moldura, text=atalho.descricao).grid(row=linha, column=1, sticky="w", pady=2)

        ttk.Label(
            moldura,
            text="A tecla é do editor quando o foco está num campo de texto: ali "
            "← e Delete pertencem ao campo.",
            foreground=theme.cor_atual(tokens.TEXTO_SECUNDARIO),
            font=theme.fonte_atual(tipografia.AUXILIAR),
        ).grid(row=len(atalhos.ATALHOS) + 1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        """A guarda de foco da S-20, dita onde ela é procurada: a legenda é o único lugar em que
        alguém pergunta "por que a seta não trocou de diagrama agora?"."""

        ttk.Button(moldura, text="Fechar", command=self.destroy).grid(
            row=len(atalhos.ATALHOS) + 2, column=1, sticky="e", pady=(14, 0)
        )

    def linhas(self) -> list[tuple[str, str]]:
        """(tecla, descrição) de cada linha desenhada. É o que o teste percorre."""
        celulas = [filho for filho in self.winfo_children()[0].winfo_children() if isinstance(filho, ttk.Label)]
        # A primeira é o título e a última é a nota de rodapé; o meio são os pares em duas colunas.
        pares = celulas[1:-1]
        return [(str(pares[i].cget("text")), str(pares[i + 1].cget("text"))) for i in range(0, len(pares) - 1, 2)]


def abrir(pai: tk.Misc) -> JanelaDeAtalhos:
    """Abre a legenda. Uma por vez: reabrir traz a que já está aberta para a frente."""
    for filho in pai.winfo_children():
        if isinstance(filho, JanelaDeAtalhos) and filho.winfo_exists():
            filho.lift()
            filho.focus_set()
            return filho
    return JanelaDeAtalhos(pai)
