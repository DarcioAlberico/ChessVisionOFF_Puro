"""Onde a tela estava quando um pedido assíncrono saiu: `AncoraDaTela` (S-823).

"O resultado ainda é da tela?" estava decidido de três jeitos. A detecção de fundo levava
`(documento, página)` em texto cru, a rasterização do visualizador comparava `(folha.source,
folha.indice)` com `Path ==`, e a leitura da janela levava **só a página**. Ler a página 1 do
livro A, abrir o livro B (que abre na página 1) e deixar a leitura terminar punha os diagramas de
A na tela de B -- e o `Ctrl+S` seguinte gravava amostras de A com o nome e a página de B, no
dataset de treino. Era a premissa 2 da revisão de solidez: "um resultado que chega depois é
marcado só pela página, sem o livro".

A regra, num lugar só: o pedido captura a âncora **quando sai**, o resultado a leva de volta, e
quem o recebe pergunta `ainda_vale(ancora, tela)` contra a âncora da tela de agora. O livro é a
`ChaveDoLivro` da S-827, e não o caminho em texto, para que `PDF\\sub\\..\\Livro.pdf` e
`pdf/livro.pdf` sejam a mesma tela. Sem livro a chave é `None`, e duas âncoras sem livro na mesma
página são a mesma tela: "continua sem livro" (ver `ui/livros.py`).

Não é a `Ancora(documento, pagina, diagrama)` do estudo: aquela diz qual diagrama a sala está
estudando; esta diz em que tela um pedido foi feito.
"""

from __future__ import annotations

from dataclasses import dataclass

from chess_diagram_ocr.ui.livros import Caminho, ChaveDoLivro, chave_do_livro

__all__ = ["AncoraDaTela", "ainda_vale", "frase_do_descarte"]


@dataclass(frozen=True)
class AncoraDaTela:
    """O par (livro, página) em que um pedido foi feito. `pagina` começa em zero."""

    documento: ChaveDoLivro | None
    pagina: int

    @classmethod
    def de(cls, caminho: Caminho | None, pagina: int) -> AncoraDaTela:
        """A âncora da página `pagina` do livro em `caminho` (`None` ou `""` sem livro)."""
        return cls(chave_do_livro(caminho), pagina)


def ainda_vale(ancora: AncoraDaTela, tela: AncoraDaTela) -> bool:
    """O resultado pedido em `ancora` ainda é da `tela`? Só se o livro e a página forem os mesmos.

    A página igual não basta, e é o defeito da S-823: o livro B abre na mesma página em que a
    leitura do livro A foi pedida.
    """
    return ancora == tela


def frase_do_descarte(ancora: AncoraDaTela, tela: AncoraDaTela) -> str:
    """O que o rodapé diz quando a leitura pedida em `ancora` chega e a tela já é outra."""
    onde = "em outro livro" if ancora.documento != tela.documento else "em outra página"
    return f"A leitura da página {ancora.pagina + 1} terminou, mas a tela já está {onde}."
