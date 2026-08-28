"""A janela de achar e substituir do editor de texto (S-245).

**O que ela tem que uma busca genérica não teria**, e as três coisas são medidas:

1. **A lista antes da troca em massa.** `substituir todos` sobre uma página de OCR é a operação
   que apaga trabalho. A S-76 é o registro do que custa um botão destrutivo que não parece um --
   1.405 diagramas sobrescritos por um clique --, e a resposta aqui é a mesma da S-170: mostrar
   **o quê**, e deixar tirar da lista o que não deve ser trocado.

2. **O casamento de figurina.** Procurar `N` acha `♘` quando o interruptor está ligado, porque o
   acervo mistura as duas codificações -- 360 figurinas contra 212 notações ASCII em 16 páginas
   (S-211). É oferta e não tradução: nasce **desligado**.

3. **A busca é do documento, não do widget.** Quem acha é `text/busca.py`, que responde com a
   janela fechada; esta classe é a caixa em volta. É o que permite a contagem de ocorrências e a
   contagem de trocas serem comparadas num teste sem abrir janela nenhuma.

## A lista é seleção, e começa toda marcada

`tk.Listbox` com `selectmode=MULTIPLE` e tudo selecionado: quem quer trocar tudo aperta o botão, e
quem não quer **desmarca** o que ficar de fora. O contrário -- começar vazia -- faria o gesto comum
custar um clique por ocorrência, e a S-245 é explícita sobre o público desta aba: alguém corrigindo
a mesma troca dezenas de vezes na mesma página.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from ..text import busca as _busca
from ..text.rico import DocumentoRico
from . import comandos
from . import texto as texto_ui

__all__ = ["JanelaDeBusca", "TITULO"]

TITULO = "Achar e substituir"

ROTULO_DE_FIGURINA = "Casar figurina com letra (N acha ♘)"
"""O interruptor da S-245, com o exemplo no próprio rótulo.

O exemplo está ali porque "casar figurina com letra" é ambíguo nas duas direções, e a pergunta que
quem lê faz -- *"então procurar ♘ acha N?"* -- se responde com quatro caracteres."""


class JanelaDeBusca(tk.Toplevel):
    """A caixa de achar e substituir. Uma por aba: reabrir traz a que já está aberta."""

    def __init__(
        self,
        pai: tk.Misc,
        *,
        documento: Callable[[], DocumentoRico],
        ao_substituir: Callable[[Sequence[_busca.Ocorrencia], str], int],
        ao_mostrar: Callable[[int, int], None],
        substituindo: bool = False,
    ) -> None:
        super().__init__(pai)
        self._documento = documento
        self._ao_substituir = ao_substituir
        self._ao_mostrar = ao_mostrar
        self._achadas: tuple[_busca.Ocorrencia, ...] = ()

        self.title(TITULO)
        self.transient(pai.winfo_toplevel())
        self.resizable(True, False)

        self.agulha_var = tk.StringVar()
        self.novo_var = tk.StringVar()
        self.figurina_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="")

        moldura = ttk.Frame(self, padding=12)
        moldura.pack(fill=tk.BOTH, expand=True)
        moldura.columnconfigure(1, weight=1)

        ttk.Label(moldura, text="Achar").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        self.campo = ttk.Entry(moldura, textvariable=self.agulha_var, width=32)
        self.campo.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(moldura, text="Substituir por").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(moldura, textvariable=self.novo_var, width=32).grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Checkbutton(moldura, text=ROTULO_DE_FIGURINA, variable=self.figurina_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 2)
        )

        botoes = ttk.Frame(moldura)
        botoes.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        ttk.Button(botoes, text=comandos.rotulo_de_botao("achar"), command=self.listar).pack(side=tk.LEFT)
        ttk.Button(
            botoes, text=comandos.rotulo_de_botao("substituir_todos"), command=self.trocar_marcadas
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.lista = tk.Listbox(moldura, selectmode=tk.MULTIPLE, height=8, exportselection=False)
        self.lista.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(4, 4))
        self.lista.bind("<Double-Button-1>", self._mostrar_escolhida)

        # **Enter acha e Esc fecha (S-342).** A janela tinha os dois botões e nenhuma tecla: quem
        # digita o que procurar e aperta `Enter` -- que é o gesto de toda caixa de busca -- não
        # recebia nada, e para fechá-la era preciso ir ao X do título. As duas ligações são no
        # `Toplevel` inteiro, e não só no campo, porque a lista e a caixa de substituir também
        # recebem foco: uma tecla que funciona em um widget e não no vizinho é pior que nenhuma.
        self.bind("<Return>", self._ao_teclar_enter)
        self.bind("<KP_Enter>", self._ao_teclar_enter)
        self.bind("<Escape>", self._ao_teclar_esc)

        texto_ui.acompanhar(ttk.Label(moldura, textvariable=self.status_var)).grid(
            row=5, column=0, columnspan=2, sticky="w"
        )

        self.mostrar(substituindo=substituindo)
        self.campo.focus_set()

    # ------------------------------------------------------------------------------- comandos

    def mostrar(self, *, substituindo: bool = False) -> None:
        """Traz a janela para a frente. `substituindo` só decide onde o cursor entra."""
        self.deiconify()
        self.lift()
        self.campo.focus_set()
        if substituindo:
            self.status_var.set("Digite o que achar e o que pôr no lugar, e confira a lista.")

    def _ao_teclar_enter(self, _evento: object = None) -> str:
        """`Enter` acha. **Não substitui**, e a diferença é a regra 2 desta revisão (S-342).

        Trocar cento e vinte ocorrências é a ação destrutiva desta janela, e ela continua exigindo
        o botão: uma tecla que a dispare pelo caminho de "achar" é exatamente o gesto que ninguém
        pediu. Com a lista já na tela, `Enter` a refaz -- que é o que se quer depois de mudar o
        que procurar.
        """
        self.listar()
        return "break"

    def _ao_teclar_esc(self, _evento: object = None) -> str:
        """`Esc` fecha, como na paleta e nos dois diálogos que já a tinham."""
        self.destroy()
        return "break"

    def listar(self) -> tuple[_busca.Ocorrencia, ...]:
        """Acha e enche a lista, **toda marcada**. Devolve o que achou, para o teste comparar."""
        agulha = self.agulha_var.get()
        self._achadas = _busca.achar(self._documento(), agulha, casar_figurina=bool(self.figurina_var.get()))
        self.lista.delete(0, tk.END)
        for ocorrencia in self._achadas:
            self.lista.insert(tk.END, ocorrencia.contexto)
        self.lista.selection_set(0, tk.END)
        if not agulha.strip():
            self.status_var.set("Digite o que procurar.")
        else:
            self.status_var.set(f"{len(self._achadas)} ocorrência(s). Desmarque o que não deve ser trocado.")
        if self._achadas:
            self._mostrar(0)
        return self._achadas

    def marcadas(self) -> tuple[_busca.Ocorrencia, ...]:
        """As ocorrências que continuam marcadas na lista -- as que serão trocadas."""
        escolhidas = set(self.lista.curselection())
        return tuple(o for i, o in enumerate(self._achadas) if i in escolhidas)

    def trocar_marcadas(self) -> int:
        """Troca as marcadas e devolve quantas trocou. **Sem lista, não troca nada.**

        Achar antes de trocar não é passo a mais: é a confirmação. Um botão que trocasse direto
        seria o gesto destrutivo sem pergunta que a S-76 mediu, sobre um texto que alguém passou a
        tarde corrigindo.
        """
        if not self._achadas:
            self.listar()
            self.status_var.set("Confira a lista e clique de novo para trocar.")
            return 0
        escolhidas = self.marcadas()
        if not escolhidas:
            self.status_var.set("Nada marcado: nenhuma troca foi feita.")
            return 0
        feitas = self._ao_substituir(escolhidas, self.novo_var.get())
        self.status_var.set(f"{feitas} troca(s) feita(s).")
        self._achadas = ()
        self.lista.delete(0, tk.END)
        return feitas

    def _mostrar_escolhida(self, _evento: object = None) -> None:
        indices = self.lista.curselection()
        if indices:
            self._mostrar(indices[0])

    def _mostrar(self, indice: int) -> None:
        if 0 <= indice < len(self._achadas):
            ocorrencia = self._achadas[indice]
            self._ao_mostrar(ocorrencia.inicio, ocorrencia.fim)
