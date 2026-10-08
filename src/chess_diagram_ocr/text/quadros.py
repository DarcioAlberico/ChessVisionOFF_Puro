"""O quadro de largura inteira que cruza a calha com muitas bandas (S-525).

O «Scoring» do fim de capítulo do `Yusupov - Build Up Your Chess` é um quadro emoldurado, de
margem a margem, com cinco linhas dentro. Ele cruza a calha em todas elas, a folha inteira é
recusada, e as soluções em cima dele -- de linha curta -- são reprovadas no preenchimento da busca
por região (S-507) ou picadas em tiras. A borda da S-523 não o alcança: ela cede duas bandas, e o
quadro tem cinco.

**O que o quadro tem, e a lista de lances não tem, é a moldura.** Tratar qualquer bloco isolado da
borda como título foi medido e recusado: a lista de lances do `Melhores Finais de Capablanca`
(p. 172) também é um bloco separado do texto por espaço, e virava duas colunas. A moldura é o que
só o quadro tem, e ela aparece nos dois caminhos:

- **no glifo**, `boxes.caixas_de_caractere` deixa passar a moldura como **uma** caixa -- não há
  teto de área ali --, larga como o texto e alta como várias linhas, e **oca**: na p. 1201 do
  Yusupov, 252 x 87 pt com 9 % de tinta no retângulo, contra ~45 % de um tabuleiro e ~50 % de uma
  foto. É a tinta que separa a moldura do diagrama que o detector não achou;
- **na camada**, o quadro é um bloco de imagem (`get_text("dict")`, `type == 1`) largo, com linhas
  de texto dentro dele que **cruzam o meio** da imagem, são a maioria das linhas dentro e têm
  palavras. A imagem decorativa do cabeçalho corrente também é larga, mas tem uma linha só cruzando
  (o título), e a S-523 cuida dela; a tira de dois diagramas tem linhas (as coordenadas) que não
  cruzam o meio; a imagem de fundo de uma lição tem as linhas das duas colunas dentro, e a maioria
  não cruza; o lixo de OCR de um tabuleiro cruza, mas não tem palavra.

O quadro vira **região de uma coluna**, e a folha é cortada em volta dele: cada trecho que sobra
passa pela régua de sempre (`regioes.detectar_regioes`). As linhas dentro dele continuam lidas --
é o oposto de `boxes.excluir_diagramas`, que tira o diagrama da leitura.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import numpy as np

from .boxes import Caixa
from .linhas import bandas

LARGURA_DE_QUADRO = 0.4
"""Fração da largura do texto a partir da qual uma caixa (ou imagem) é larga como um quadro.

O «Scoring» tem 0,60; um diagrama de coluna, 0,35 a 0,45 -- e é por isso que a largura não decide
sozinha: ver `TINTA_DE_MOLDURA` e `LINHAS_DENTRO`."""

ALTURA_DE_QUADRO = 3.0
"""Em escalas de texto (glifo) ou em pontos vezes dez (camada): o quadro é alto como várias linhas."""

ALTURA_MINIMA_PT = 30.0
"""Na camada, a altura mínima da imagem para ser quadro: três linhas de corpo 10."""

TINTA_DE_MOLDURA = 0.25
"""Fração máxima de tinta no retângulo da caixa para ela ser moldura (oca), e não tabuleiro."""

LINHAS_DENTRO = 2
"""Quantas bandas (ou linhas da camada) o quadro precisa ter dentro para ser quadro de texto."""

AREA_MAXIMA = 0.8
"""Fração da página acima da qual a imagem é o fundo da página inteira, e não um quadro."""

FRACAO_CRUZANDO = 0.5
"""Na camada, a fração mínima das linhas dentro da imagem que cruzam o meio dela. Ver
`quadros_da_camada`: a imagem de fundo de uma lição de duas colunas fica em 0,25."""

_PALAVRA = re.compile(r"[^\W\d_]{2,}")
"""Duas letras ou mais: o que separa «20 points and above» do lixo de OCR de um tabuleiro."""


def molduras_nas_caixas(
    caixas: Sequence[Caixa], binaria: np.ndarray, *, escala: int
) -> list[tuple[int, int]]:
    """Os intervalos de `y` (pixels) dos quadros emoldurados entre as caixas de caractere.

    Uma caixa larga como `LARGURA_DE_QUADRO` do texto e alta como `ALTURA_DE_QUADRO` escalas,
    com menos de `TINTA_DE_MOLDURA` de tinta no retângulo e pelo menos `LINHAS_DENTRO` bandas de
    outras caixas dentro dela.
    """
    if not caixas or escala <= 0:
        return []
    largura_do_texto = max(c.x2 for c in caixas) - min(c.x1 for c in caixas)
    if largura_do_texto <= 0:
        return []
    candidatas = [
        c
        for c in caixas
        if c.largura >= LARGURA_DE_QUADRO * largura_do_texto and c.altura >= ALTURA_DE_QUADRO * escala
    ]
    if not candidatas:
        return []
    grupos = bandas(caixas)
    topos = [min(c.y1 for c in g) for g in grupos]
    saida: list[tuple[int, int]] = []
    for c in candidatas:
        recorte = binaria[max(0, c.y1) : c.y2 + 1, max(0, c.x1) : c.x2 + 1]
        if recorte.size == 0 or float(np.count_nonzero(recorte)) / recorte.size > TINTA_DE_MOLDURA:
            continue
        dentro = sum(1 for t in topos if c.y1 < t <= c.y2)
        if dentro >= LINHAS_DENTRO:
            saida.append((c.y1, c.y2))
    return _fundidos(saida)


def quadros_da_camada(page: Any) -> list[tuple[float, float]]:
    """Os intervalos de `y` (pontos) dos quadros da camada de texto: imagens largas com linhas dentro."""
    largura = float(page.rect.width)
    area = float(page.rect.width * page.rect.height)
    blocos = page.get_text("dict")["blocks"]
    linhas = [
        (linha["bbox"], texto)
        for bloco in blocos
        if bloco.get("type") == 0
        for linha in bloco.get("lines", [])
        if (texto := "".join(span["text"] for span in linha["spans"]).strip())
    ]
    saida: list[tuple[float, float]] = []
    for bloco in blocos:
        if bloco.get("type") != 1:
            continue
        x0, y0, x1, y1 = (float(v) for v in bloco["bbox"])
        if x1 - x0 < LARGURA_DE_QUADRO * largura or y1 - y0 < ALTURA_MINIMA_PT:
            continue
        if (x1 - x0) * (y1 - y0) > AREA_MAXIMA * area:
            continue
        # **As linhas dentro têm de cruzar o meio da imagem, ser a maioria e ter palavras.** Três
        # réguas, e cada uma barra uma imagem larga que não é quadro (medido em 2026-10-08, na
        # régua da S-194): a tira de dois diagramas lado a lado do Nunn tem linhas dentro (as
        # coordenadas sob cada tabuleiro), e nenhuma cruza o meio; a imagem de fundo de uma lição
        # do Yusupov (p. 1872) tem 16 linhas de duas colunas dentro, e só 4 cruzam o meio (0,25);
        # o diagrama do `Pawnless Endings` (p. 269) tem lixo de OCR cruzando o meio, e nenhuma
        # linha com duas palavras. O «Scoring»: 4 de 4 a 4 de 7 cruzam, todas com palavras.
        meio = (x0 + x1) / 2
        dentro = [
            (lx0, lx1, texto) for (lx0, ly0, lx1, ly1), texto in linhas
            if y0 <= (ly0 + ly1) / 2 <= y1 and x0 <= (lx0 + lx1) / 2 <= x1
        ]
        cruzam = [texto for lx0, lx1, texto in dentro if lx0 < meio < lx1]
        com_palavras = sum(1 for texto in cruzam if len(_PALAVRA.findall(texto)) >= 2)
        if (
            len(cruzam) >= LINHAS_DENTRO
            and len(cruzam) >= FRACAO_CRUZANDO * len(dentro)
            and com_palavras >= LINHAS_DENTRO
        ):
            saida.append((y0, y1))
    return _fundidos(saida)


def _fundidos(intervalos: list[tuple[Any, Any]]) -> list[Any]:
    """Intervalos ordenados e sem sobreposição: dois quadros que se tocam são um."""
    saida: list[Any] = []
    for y1, y2 in sorted(intervalos):
        if saida and y1 <= saida[-1][1]:
            saida[-1] = (saida[-1][0], max(saida[-1][1], y2))
        else:
            saida.append((y1, y2))
    return saida


__all__ = [
    "ALTURA_DE_QUADRO",
    "ALTURA_MINIMA_PT",
    "AREA_MAXIMA",
    "FRACAO_CRUZANDO",
    "LARGURA_DE_QUADRO",
    "LINHAS_DENTRO",
    "TINTA_DE_MOLDURA",
    "molduras_nas_caixas",
    "quadros_da_camada",
]
