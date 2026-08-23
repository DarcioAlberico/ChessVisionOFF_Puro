"""Onde um parágrafo termina e outro começa (S-192).

Ordem não é parágrafo. Saber que a linha 12 vem antes da 13 não diz onde um parágrafo acaba, e
sem isso o texto exportado é uma parede.

**Três regras juntas, porque nenhuma sozinha cobre este material.** A prosa usa recuo; a notação
em negrito entre parágrafos usa espaço em branco; e nenhuma das duas vê o fim da coluna -- lá o
salto vertical é **negativo**, porque a leitura volta ao topo da página.

    recuo    a linha começa mais à direita que a margem da coluna
    salto    o vão até a linha anterior passa de uma altura de linha e meia
    troca    a coluna mudou

## A margem é por coluna, e a mediana da página não serve

É a lição da F61 no projeto de origem: a mediana das esquerdas de uma página de duas colunas não
é margem nenhuma. Metade das linhas começa em 122 e metade em 893, e a mediana cai num dos dois
-- com ela, ou a coluna da direita inteira parece recuada (cada linha vira um parágrafo) ou a da
esquerda perde todos os recuos que tem.

**E a métrica é da página, não do trecho.** São medianas, e a mediana de cinco linhas entre dois
diagramas não diz onde fica a margem da coluna.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

RECUO_DE_PARAGRAFO = 0.8
"""Recuo que abre parágrafo, em alturas de linha."""

SALTO_DE_PARAGRAFO = 0.6
"""Salto vertical extra que abre parágrafo, em alturas de linha. O corte é `1 + este valor`."""


@dataclass(frozen=True)
class Linha:
    """Uma linha já lida, do ponto de vista da diagramação."""

    topo: int
    esquerda: int
    altura: int
    texto: str
    coluna: int = 0
    """Em qual faixa de `colunas.detectar_colunas` esta linha está. Zero na página de coluna
    única, que é o caso em que tudo isto some."""


@dataclass(frozen=True)
class Paragrafo:
    texto: str
    linhas: tuple[Linha, ...] = field(default_factory=tuple)

    @property
    def coluna(self) -> int:
        return self.linhas[0].coluna if self.linhas else 0


def metricas_por_coluna(linhas: Sequence[Linha]) -> dict[int, tuple[int, int]]:
    """`{coluna: (margem esquerda, altura de linha)}`, medidas na **página inteira**.

    Ver "A margem é por coluna" no cabeçalho.
    """
    metricas: dict[int, tuple[int, int]] = {}
    for coluna in {linha.coluna for linha in linhas}:
        desta = [linha for linha in linhas if linha.coluna == coluna]
        esquerdas = sorted(linha.esquerda for linha in desta)
        alturas = sorted(linha.altura for linha in desta)
        metricas[coluna] = (esquerdas[len(esquerdas) // 2], alturas[len(alturas) // 2] or 1)
    return metricas


def cortar(linhas: Sequence[Linha], metricas: dict[int, tuple[int, int]] | None = None) -> list[Paragrafo]:
    """Linhas -> parágrafos, pelas três regras do cabeçalho.

    `metricas=None` as tira destas mesmas linhas, que é o que serve a quem chama com a página
    toda. Quem chama com um trecho passa as da página -- ver o cabeçalho.
    """
    if not linhas:
        return []
    if metricas is None:
        metricas = metricas_por_coluna(linhas)

    paragrafos: list[Paragrafo] = []
    atual: list[Linha] = []
    anterior: Linha | None = None
    for linha in linhas:
        margem, altura = metricas.get(linha.coluna, (linha.esquerda, linha.altura or 1))
        trocou = anterior is not None and linha.coluna != anterior.coluna
        recuou = linha.esquerda > margem + altura * RECUO_DE_PARAGRAFO
        saltou = (
            anterior is not None
            and not trocou
            and linha.topo - anterior.topo > altura * (1 + SALTO_DE_PARAGRAFO)
        )
        if atual and (recuou or saltou or trocou):
            paragrafos.append(_fechar(atual))
            atual = []
        atual.append(linha)
        anterior = linha
    if atual:
        paragrafos.append(_fechar(atual))
    return paragrafos


def _fechar(linhas: list[Linha]) -> Paragrafo:
    return Paragrafo(texto=" ".join(linha.texto for linha in linhas), linhas=tuple(linhas))


__all__ = [
    "RECUO_DE_PARAGRAFO",
    "SALTO_DE_PARAGRAFO",
    "Linha",
    "Paragrafo",
    "cortar",
    "metricas_por_coluna",
]
