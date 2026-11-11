"""Que fonte desenha tabuleiro, que fonte desenha figurina, e o que é rótulo de eixo (S-836).

**Uma regra só, importada pelos dois lados.** Havia duas: `pdf_text` tirava da legenda a linha que é
o próprio tabuleiro desenhado em fonte (o `Polgar 5334`), e `text/admissao` recusava a folha com
uma fileira de tabuleiro fora do diagrama. As duas expressões discordavam em oito nomes --
`Leipzig`, `Kingdom`, `Linares` e `Alpha` eram diagrama para a admissão e texto para a legenda;
`Echecs`, `Ajedrez`, `Schachfiguren` e `XadrezFont`, o contrário -- e a admissão chamava
`ChessMerida` de diagrama e de figurina ao mesmo tempo.

A regra aqui é a união das duas listas de diagrama, menos o que é de figurina. **No acervo isso não
muda nada**: medido em 2026-11-09 sobre os 1.928 nomes de fonte dos PDFs de `PDF/`, sete são de
xadrez (`Chess Merida Regular`, `Chess-Merida`, `SkakNew-Diagram`, de diagrama; `SkakNew-Figurine`,
`SkakNew-Figurine-Bold` e os dois `FigurineSymbol`, de figurina), e as duas regras antigas já
concordavam neles. A diferença é para o livro que ainda não foi medido, e o que ela garante é que
a legenda e a admissão respondam igual a ele.

**Diagrama, figurina e "de xadrez" são três perguntas.** A figurina desenha a peça no meio do
lance (`♘f3`), e o nome dela casa com o de diagrama (`SkakNew-Diagram` e `SkakNew-Figurine` são a
mesma família): por isso o de figurina sai do de diagrama. "De xadrez" é qualquer das duas, e é o
que a admissão e a camada de prosa precisam para não chamar de lixo o caractere de uso privado com
que essas fontes desenham as peças.
"""

from __future__ import annotations

import re

PREFIXO_DE_SUBCONJUNTO = re.compile(r"^[A-Z]{6}\+")
"""`ABCDEF+ChessMerida`: o prefixo de subconjunto do PDF, que não faz parte do nome."""

NOME_DE_DIAGRAMA = re.compile(
    r"chess|skak|merida|diagram|schach|echecs|scacchi|ajedrez|xadrez|alpha|leipzig|kingdom|linares",
    re.IGNORECASE,
)
"""Palavras de nome de fonte que desenha tabuleiro, nas línguas em que os livros do acervo saem.

`chess` já cobre `ChessBerlin`, `UsualChess` e `ChessAlpha`, que o protótipo da admissão listava à parte."""

NOME_DE_FIGURINA = re.compile(r"figurine|semfig|segoe ui symbol|ms gothic", re.IGNORECASE)
"""Fonte de **figurina**, que desenha a peça no meio do lance e não o tabuleiro.

Medido no acervo (S-16), as duas de figurina do `Polgar` desenham 1.892 linhas que também têm prosa:
são as listas de lances, e tratá-las como tabuleiro apagaria o texto. `Segoe UI Symbol` e `MS Gothic`
são de sistema, mas trazem os símbolos de peça, e entram pelo mesmo motivo que fez a admissão listá-las."""

ROTULO_DE_EIXO = re.compile(r"^[a-h1-8]$")
"""Uma linha que é só um rótulo de eixo do tabuleiro: uma coluna (`a`..`h`) ou uma fila (`1`..`8`)."""

MIN_ROTULOS_DE_EIXO = 6
"""Quantos rótulos distintos, alinhados, fazem a borda de um tabuleiro (S-217).

Seis, e não oito: o scan perde rótulo de canto, e exigir os oito faria a régua falhar justamente nas
páginas piores."""


def _sem_prefixo(nome: str) -> str:
    return PREFIXO_DE_SUBCONJUNTO.sub("", nome or "")


def e_fonte_de_figurina(nome: str) -> bool:
    """A fonte desenha a peça no meio do lance (`SkakNew-Figurine`)?"""
    return bool(NOME_DE_FIGURINA.search(_sem_prefixo(nome)))


def e_fonte_de_diagrama(nome: str) -> bool:
    """A fonte desenha tabuleiro? Figurina não conta, mesmo quando a família é a mesma."""
    limpo = _sem_prefixo(nome)
    return bool(NOME_DE_DIAGRAMA.search(limpo)) and not NOME_DE_FIGURINA.search(limpo)


def e_fonte_de_xadrez(nome: str) -> bool:
    """A fonte desenha peça ou tabuleiro -- qualquer das duas."""
    limpo = _sem_prefixo(nome)
    return bool(NOME_DE_DIAGRAMA.search(limpo) or NOME_DE_FIGURINA.search(limpo))
