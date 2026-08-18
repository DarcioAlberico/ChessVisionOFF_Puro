"""A barra de ferramentas que quebra em vez de cortar (S-151).

**O defeito.** `ui/pdf_panel.py` empilhava **cinco** barras antes de a página aparecer: ~200 px,
20% da altura da janela gastos em controle permanente, sobre o painel cuja única razão de
existir é mostrar a página grande.

E nenhuma delas refluía. Todas usavam `pack(side=LEFT)` numa linha de altura fixa, e quando
falta largura o Tk simplesmente **não desenha** o que passou da borda: em 1100 de largura somem
"Exportar PDF → PGN", "Cancelar exportação", "Tirar o selecionado" e a contagem de diagramas da
página. Sem aviso, sem reticências, sem `>>`.

**O que o `pack` não sabe, e esta barra sabe.** Que a linha pode ser duas. Dado o que cada item
pede e quanto há disponível, `arranjo` distribui os itens em linhas — e a propriedade que o
teste afirma é a que hoje falha: **nenhum item é descartado**, em nenhuma largura.

**Por que não um botão de transbordo.** Ele foi a primeira ideia e não sobrevive ao Tk: um
widget não muda de pai depois de criado, então "mover o que sobrou para dentro de um menu"
exigiria recriar cada controle — com os `Tooltip`, os `state=DISABLED` e as variáveis atados a
ele. Quebrar em mais uma linha custa ~28 px e não custa nenhuma dessas amarras, e a linha extra
só aparece na largura em que o transbordo apareceria.

**A decisão é pura; o widget só executa.** `arranjo` não toca `tkinter` e é afirmada nos três
regimes — cabe em uma linha, cabe em duas, não cabe em nenhuma.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk
from typing import TypeVar

logger = logging.getLogger(__name__)

__all__ = ["ESPACO_ENTRE_ITENS", "BarraFluida", "arranjo", "linhas_necessarias"]

W = TypeVar("W", bound=tk.Widget)
"""O tipo do widget registrado. Devolver o **mesmo** tipo é o que preserva `lbl.config(text=...)`
nos pontos de chamada -- sem ele, tudo que passa pela barra vira `tk.Widget` para o verificador."""

ESPACO_ENTRE_ITENS = 6
"""O `padx` entre dois controles da mesma linha. Entra na conta porque ele é largura também."""

# **Por que uma moldura por linha, e não um `grid` só.** Foram duas tentativas erradas antes,
# e as duas vieram de o `grid` do Tk ser uma tabela:
#
# 1. `grid(row=n, column=i)` dá a **mesma** largura à coluna `i` de todas as linhas. Com
#    "Próxima página" (92 px) na coluna 1 da primeira e "Ajustar à página" (95) na coluna 1 da
#    segunda, a coluna passa a medir 95 nas duas, cada linha engorda pelo item mais largo da
#    outra, e o `grid` **desmapeia** o que não coube -- o defeito original de volta.
# 2. Dar a cada linha uma faixa de colunas própria (0..99, 100..199) não isola nada: as colunas
#    do `grid` são dispostas da esquerda para a direita para a grade **inteira**, então a linha
#    2 nasce depois da largura somada da linha 1. Medido: os dois últimos botões começavam em
#    x=490 numa barra de 500 px.
#
# Uma `ttk.Frame` por linha, com os itens empacotados `in_=` ela, torna as linhas independentes
# de verdade. Os itens continuam sendo filhos da **barra** -- `pack(in_=...)` aceita qualquer
# descendente do pai --, então nada precisa ser recriado quando o arranjo muda.


def arranjo(
    larguras: Sequence[int],
    disponivel: int,
    *,
    espaco: int = ESPACO_ENTRE_ITENS,
) -> list[list[int]]:
    """Distribui os itens em linhas, na ordem em que vieram. Devolve índices por linha.

    **Nenhum item é descartado, em nenhuma largura** — é essa a propriedade que hoje falha, e é
    ela que o teste afirma nos três regimes. Um item mais largo que a barra inteira ocupa uma
    linha sozinho e é cortado na borda; cortar um é melhor que esconder três, e é o único caso
    em que a barra não tem saída.

    A ordem é preservada de propósito: reordenar controles entre larguras faria o mesmo botão
    mudar de lugar ao arrastar o divisor, e a memória motora de quem usa o programa todo dia
    vale mais que a linha economizada.
    """
    linhas: list[list[int]] = []
    atual: list[int] = []
    usado = 0
    for indice, largura in enumerate(larguras):
        pedido = int(largura) + (espaco if atual else 0)
        if atual and usado + pedido > int(disponivel):
            linhas.append(atual)
            atual, usado = [], 0
            pedido = int(largura)
        atual.append(indice)
        usado += pedido
    if atual:
        linhas.append(atual)
    return linhas


def linhas_necessarias(larguras: Sequence[int], disponivel: int, *, espaco: int = ESPACO_ENTRE_ITENS) -> int:
    """Quantas linhas a barra vai ocupar. É o que o critério de aceite mede."""
    return len(arranjo(larguras, disponivel, espaco=espaco))


class BarraFluida(ttk.Frame):
    """Uma barra cujos controles quebram para a linha de baixo quando não cabem.

    Monte os controles com `self` como pai e registre-os com `adicionar` — sem `pack` nem
    `grid` próprios, que é quem esta classe substitui.
    """

    def __init__(self, parent: tk.Misc, *, espaco: int = ESPACO_ENTRE_ITENS) -> None:
        super().__init__(parent)
        self._itens: list[tk.Widget] = []
        self._molduras: list[ttk.Frame] = []
        self._espaco = espaco
        self._arranjo_aplicado: list[list[int]] = []
        self._largura = 0
        """A última largura conhecida da barra.

        Vem do **evento** e não de `winfo_width()`: durante um redimensionamento o widget ainda
        reporta a largura anterior quando o `<Configure>` chega, e arranjar contra ela deixava
        dois controles fora da área do `grid` -- que o Tk **desmapeia** em vez de recortar. O
        sintoma era o defeito original de volta, com outra causa."""

        self.bind("<Configure>", lambda evento: self._rearranjar(int(evento.width)))

    def adicionar(self, widget: W) -> W:
        """Registra um controle na barra, na ordem em que ele deve aparecer. Devolve-o.

        Devolver o widget é o que faz o ponto de chamada caber numa linha --
        `barra.adicionar(ttk.Button(barra, ...))` -- em vez de precisar de uma variável só para
        registrar em seguida.
        """
        self._itens.append(widget)
        self._rearranjar(self._largura or self.winfo_width())
        return widget

    # ------------------------------------------------------------------------ geometria

    def _larguras(self) -> list[int]:
        return [max(1, item.winfo_reqwidth()) for item in self._itens]

    def _rearranjar(self, largura: int) -> None:
        """Recalcula e reaplica o arranjo. Idempotente: repor o mesmo arranjo não pisca."""
        if not self._itens:
            return
        self._largura = max(self._largura, 1) if largura <= 1 else largura
        try:
            novo = arranjo(self._larguras(), self._largura, espaco=self._espaco)
        except tk.TclError:  # pragma: no cover - widget destruído durante o evento
            return
        if novo == self._arranjo_aplicado:
            return
        self._arranjo_aplicado = novo
        while len(self._molduras) < len(novo):
            self._molduras.append(ttk.Frame(self))
        for numero, moldura in enumerate(self._molduras):
            if numero < len(novo):
                moldura.pack(fill=tk.X, pady=(0 if numero == 0 else 2, 0))
            else:
                # Desempacotada e não destruída: uma janela que oscila de largura recriaria a
                # moldura a cada pixel, e o `pack_forget` custa nada.
                moldura.pack_forget()
        for numero, linha in enumerate(novo):
            for coluna, indice in enumerate(linha):
                self._itens[indice].pack(
                    in_=self._molduras[numero],
                    side=tk.LEFT,
                    padx=(0 if coluna == 0 else self._espaco, 0),
                )

    @property
    def linhas(self) -> int:
        """Quantas linhas a barra está ocupando agora. É o que o teste de aceite lê."""
        return len(self._arranjo_aplicado)
