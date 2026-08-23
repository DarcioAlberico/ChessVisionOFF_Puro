"""A tabela sai como tabela (S-199).

A tabela de finais da página 236 do Nunn mede 1342x1099 e tem moldura fechada. Com
`RETR_EXTERNAL`, as 276 caixas de caractere de dentro dela **não saíam fora de ordem: não
saíam.** É a mesma classe de falha da tarja e da trama, e é a que menos se percebe -- uma tabela
ausente parece uma página sem tabela.

## Duas partes, e a ordem importa

**1. Abrir o bloco** é a S-196, com a tolerância de proporção corrigida: a razão 1,22 desta tabela
é o caso que obrigou a correção, porque a régua anterior a tinha exatamente no vão entre "é
diagrama" e "vale abrir".

**2. Ler a grade da imagem**, e não por folga arbitrária: as linhas da moldura dão as fronteiras
de célula. E **dentro da célula não se lê como se lê a página** -- a célula tem a própria escala,
a própria margem, e a ordem de leitura é por célula, não por banda horizontal da página inteira.

## A saída é uma estrutura, e não um bloco de texto com espaços

Quem exporta decide como desenhá-la. Um bloco de texto com espaços obrigaria cada consumidor a
readivinhar onde estava a coluna -- e é exatamente o que a página já fazia antes.

## O limite conhecido, declarado em vez de heurística frágil

**A tabela sem moldura -- só com alinhamento -- não é reconhecida.** Achá-la exigiria inferir
colunas de espaços em branco, que é o que a S-190 já faz para a página e não para dentro de um
bloco; e o falso positivo dessa inferência é uma lista de duas colunas virando tabela. Fica como
limite registrado.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from .boxes import Caixa

FRACAO_DA_LINHA = 0.6
"""Que fração do lado do bloco uma linha da moldura precisa cobrir para ser fronteira de célula.

Abaixo disto é sublinhado de célula, traço de conteúdo ou quebra do scan -- e aceitá-los produz
uma tabela com dezenas de colunas de um caractere."""

ESPESSURA_MAXIMA = 0.06
"""Espessura máxima de uma linha de moldura, em frações do lado do bloco. Mais grossa é barra de
preenchimento, não fronteira."""

MIN_CELULAS = 2
"""Menos que isto num eixo não é tabela: é um bloco com uma borda."""


@dataclass(frozen=True)
class Celula:
    """Uma célula da grade, com as caixas de caractere que caem dentro dela."""

    linha: int
    coluna: int
    bbox: tuple[int, int, int, int]
    caixas: tuple[Caixa, ...] = ()


@dataclass(frozen=True)
class Tabela:
    """A grade lida de um bloco. `linhas x colunas`, com as células em ordem de leitura."""

    bbox: tuple[int, int, int, int]
    linhas: int
    colunas: int
    celulas: tuple[Celula, ...]

    @property
    def forma(self) -> tuple[int, int]:
        return (self.linhas, self.colunas)

    def celula(self, linha: int, coluna: int) -> Celula | None:
        for c in self.celulas:
            if c.linha == linha and c.coluna == coluna:
                return c
        return None


def _fronteiras(projecao: np.ndarray, extensao: int) -> list[int]:
    """Onde a moldura corta o eixo: faixas contínuas de tinta que cobrem quase todo o outro eixo.

    Devolve o **centro** de cada faixa. Uma moldura de 3 px produz um corte, e não três.
    """
    if projecao.size == 0:
        return []
    cheia = projecao >= FRACAO_DA_LINHA * extensao
    espessura_max = max(1, int(len(projecao) * ESPESSURA_MAXIMA))

    cortes: list[int] = []
    inicio: int | None = None
    for i, marcado in enumerate([*cheia, False]):
        if marcado:
            if inicio is None:
                inicio = i
        elif inicio is not None:
            if i - inicio <= espessura_max:
                cortes.append((inicio + i) // 2)
            inicio = None
    return cortes


def grade(binaria: np.ndarray, bloco: Caixa) -> tuple[list[int], list[int]]:
    """`(cortes horizontais, cortes verticais)` da moldura, em coordenadas da página.

    **A grade vem da imagem**, e não de folga arbitrária -- ver o cabeçalho.
    """
    recorte = bloco.recortar(binaria)
    if recorte.size == 0:
        return [], []

    tinta = (recorte > 0).astype(np.int32)
    horizontais = [bloco.y1 + y for y in _fronteiras(tinta.sum(axis=1), recorte.shape[1])]
    verticais = [bloco.x1 + x for x in _fronteiras(tinta.sum(axis=0), recorte.shape[0])]
    return horizontais, verticais


def ler(binaria: np.ndarray, bloco: Caixa, caixas: Sequence[Caixa] = ()) -> Tabela | None:
    """A tabela do bloco, ou `None` quando ele não tem grade.

    `caixas` são as de caractere já segmentadas; cada uma vai para a célula que contém o centro
    dela. Sem elas a tabela sai com a forma e as células vazias, que é o que serve a quem só quer
    saber se há grade.
    """
    horizontais, verticais = grade(binaria, bloco)
    if len(horizontais) < MIN_CELULAS + 1 or len(verticais) < MIN_CELULAS + 1:
        return None

    celulas: list[Celula] = []
    for i, (y0, y1) in enumerate(zip(horizontais, horizontais[1:], strict=False)):
        for j, (x0, x1) in enumerate(zip(verticais, verticais[1:], strict=False)):
            dentro = tuple(
                c for c in caixas if x0 <= (c.x1 + c.x2) / 2 <= x1 and y0 <= (c.y1 + c.y2) / 2 <= y1
            )
            celulas.append(Celula(linha=i, coluna=j, bbox=(x0, y0, x1, y1), caixas=dentro))

    return Tabela(
        bbox=(bloco.x1, bloco.y1, bloco.x2, bloco.y2),
        linhas=len(horizontais) - 1,
        colunas=len(verticais) - 1,
        celulas=tuple(celulas),
    )


def ordem_na_celula(celula: Celula) -> list[Caixa]:
    """A ordem de leitura **dentro** da célula.

    Ela tem a própria escala e a própria margem: usar a banda da página inteira juntaria a célula
    da esquerda com a da direita, que é o mesmo defeito da coluna um nível acima.
    """
    from .linhas import ordem_em_faixa

    return ordem_em_faixa(celula.caixas)


def moldura_fechada(binaria: np.ndarray, bloco: Caixa) -> bool:
    """O bloco tem moldura nos quatro lados? É o que a S-196 precisa saber para reabri-lo."""
    horizontais, verticais = grade(binaria, bloco)
    if not horizontais or not verticais:
        return False
    folga = max(2, int(min(bloco.altura, bloco.largura) * ESPESSURA_MAXIMA) * 2)
    return (
        min(horizontais) - bloco.y1 <= folga
        and bloco.y2 - max(horizontais) <= folga
        and min(verticais) - bloco.x1 <= folga
        and bloco.x2 - max(verticais) <= folga
    )


def desenhar_grade(forma: tuple[int, int], *, lado: int = 60, espessura: int = 3) -> np.ndarray:
    """Uma grade sintética binarizada, para os testes. Tinta em branco, como o resto do subpacote."""
    linhas, colunas = forma
    altura, largura = linhas * lado, colunas * lado
    imagem = np.zeros((altura + espessura, largura + espessura), dtype=np.uint8)
    for i in range(linhas + 1):
        cv2.line(imagem, (0, i * lado), (largura, i * lado), 255, espessura)
    for j in range(colunas + 1):
        cv2.line(imagem, (j * lado, 0), (j * lado, altura), 255, espessura)
    return imagem


__all__ = [
    "ESPESSURA_MAXIMA",
    "FRACAO_DA_LINHA",
    "MIN_CELULAS",
    "Celula",
    "Tabela",
    "desenhar_grade",
    "grade",
    "ler",
    "moldura_fechada",
    "ordem_na_celula",
]
