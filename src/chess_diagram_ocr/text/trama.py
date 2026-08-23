"""Texto sobre trama de meio-tom, e o bloco que engoliu a tabela (S-196 e S-199).

O quadro de pontuação que fecha cada capítulo é um painel chapado, e o escaneamento o devolve
como uma nuvem de pontos. O estrago é em dois tempos, e o segundo é o que apaga o texto:

1. **A trama envenena toda régua relativa.** Medido no projeto de origem, na página 18 do *Chess
   Evolution 1*: 6.765 contornos, 95,8% deles de 6x6 px ou menos, e a mediana das alturas em
   **2 px**. Quem conserta isso é a `escala_de_texto` da S-185, que pesa por tinta.
2. **A trama solda o texto ao fundo.** Os pontos encostam nas letras e as letras umas nas outras:
   o painel inteiro sai como **um** contorno de 1049x390, e o que estava escrito dentro dele não
   chega a existir como caixa.

Este módulo trata o segundo.

## Rebinarizar o recorte é o que desfaz a solda

Na página inteira o papel branco domina e o Otsu global corta em ~50, **abaixo** da trama -- que
vira tinta e gruda em tudo. Dentro do painel o papel some da conta e sobram duas populações,
trama (tom ~99) e texto (tom ~5); ali o Otsu corta em **143**, acima da trama. Medido no painel da
página 18: **71 componentes com tamanho de caractere onde antes havia zero.**

## A peneira é do domínio, e tem margem larga: tabuleiro é quadrado

Um tabuleiro também é bloco grande de tinta esparsa, e ler dentro dele daria uma caixa por peça.
Medido, os diagramas medem 578x579, 579x579, 580x584 -- proporção 1,00 a 1,01; o painel de
pontuação mede 1049x390, proporção 2,69. A cobertura por células diria o mesmo com margem estreita
(99,9% contra 82%-91%) e por isso não é usada.

**A tolerância não é "mais largo que alto", e isso custou uma fase.** Uma tabela pode ser mais
alta que larga -- a tabela de finais da página 236 do Nunn mede 1342x1099, razão **1,22** --, e a
primeira régua, posta "no meio do vão" a 1,5 porque nada caía entre 1,3 e 2,6, tinha essa tabela
justamente no vão. Moldura fechada, `RETR_EXTERNAL`, e as 276 caixas de dentro dela **sumiam do
livro sem aviso nenhum**: não saíam fora de ordem, não saíam.

## A moldura reaparece dentro do próprio recorte

Recortar o bloco pelo retângulo dele traz a borda junto, e ali dentro ela é de novo o contorno
externo: o `RETR_EXTERNAL` devolve a moldura e o conteúdo continua sendo filho de alguém. Numa
tabela escaneada o defeito não aparece porque o scan quebra a borda em pedaços; numa moldura que
fecha de verdade, como a de um PDF vetorial, ele sobreviveria à própria correção. Medido:
**0 glifos com a borda dentro, 12 sem ela.**
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from .boxes import Caixa

TAMANHO_MINIMO = 4.0
"""Quantas escalas de caractere o bloco precisa ter, nos dois eixos, para valer a pena olhar
dentro. Abaixo disso é palavra grande, não painel."""

TOLERANCIA_QUADRADO = 1.15
"""Quanto o bloco tem de fugir do quadrado para valer uma olhada dentro.

**É o complemento exato da peneira do diagrama**, e prendê-las ao mesmo número é o que impede o
caso do meio: um bloco que não é quadrado o bastante para virar diagrama e é quadrado demais para
ser lido. Era exatamente a tabela do Nunn a 1,22 -- ver o cabeçalho."""

ALTURA_GLIFO = (0.35, 2.5)
"""Faixa de altura, em escalas de texto da página, para um componente de dentro do bloco ser
caractere. Larga porque o painel mistura corpo grande com corpo pequeno."""

MIN_GLIFOS = 3
"""Quantos caracteres fazem o bloco valer a substituição. Para **decidir**, um punhado basta."""

MAX_GLIFOS = 2000
"""E quantos são caracteres demais para serem caractere.

**A página que é uma fotografia tem escala de texto degenerada**, e é isso que fabrica o número.
Medida a capa do *Chess Evolution 1*, a escala devolve **2 px** -- não há texto na página para
pesar --, e com ela `ALTURA_GLIFO` aceita como caractere qualquer grão de 0,7 a 5 px: o bloco
rende dezenas de milhares de "glifos" e a página sai de 1 caixa para 40 mil."""

MARGEM_DA_MOLDURA = 0.25
"""Quanto se tira de cada lado do recorte antes de olhar dentro, em escalas de texto.
Ver "A moldura reaparece dentro do próprio recorte" no cabeçalho."""


def _margem(escala: int) -> int:
    return max(2, int(escala * MARGEM_DA_MOLDURA))


def e_quadrado(caixa: Caixa, *, tolerancia: float = TOLERANCIA_QUADRADO) -> bool:
    """O bloco é quadrado o bastante para ser tabuleiro? **Nos dois eixos** -- ver o cabeçalho."""
    largura, altura = max(1, caixa.largura), max(1, caixa.altura)
    return max(largura / altura, altura / largura) <= tolerancia


def candidatos(caixas: Sequence[Caixa], *, escala: int) -> list[Caixa]:
    """Blocos grandes que **não** são quadrados -- os que valem uma segunda olhada.

    Nada aqui afirma que o bloco tem texto: quem afirma é `ler_bloco`, depois de reler o recorte.
    """
    if escala <= 0:
        return []
    piso = escala * TAMANHO_MINIMO
    return [c for c in caixas if c.altura >= piso and c.largura >= piso and not e_quadrado(c)]


def binarizar_bloco(cinza: np.ndarray, bloco: Caixa, *, escala: int = 0) -> np.ndarray:
    """O recorte binarizado **com o limiar dele**, não com o da página. Tinta em branco.

    Vem sem a própria borda -- ver `MARGEM_DA_MOLDURA`. Quem chama tem de passar a mesma `escala`
    a `glifos_do_bloco`, que é quem devolve a margem às coordenadas.
    """
    m = _margem(escala)
    # **Bloco menor que duas margens não sobra nada, e dizer isso importa**: com `y2 - m`
    # negativo o `numpy` fatia a partir do fim da imagem e devolve um recorte de **outro lugar
    # da página**, não vazio. O sintoma seria glifos com coordenadas plausíveis vindos de onde
    # ninguém olhou. `candidatos` já barra o bloco pequeno; isto é a rede de segurança de quem
    # chamar direto.
    if bloco.altura <= 2 * m or bloco.largura <= 2 * m:
        return np.zeros((0, 0), dtype=np.uint8)

    recorte = cinza[bloco.y1 + m : bloco.y2 - m, bloco.x1 + m : bloco.x2 - m]
    if recorte.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    _, binaria = cv2.threshold(recorte, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binaria


def glifos_do_bloco(cinza: np.ndarray, bloco: Caixa, *, escala: int) -> list[Caixa]:
    """As caixas de dentro do bloco, em coordenadas da página."""
    binaria = binarizar_bloco(cinza, bloco, escala=escala)
    if binaria.size == 0:
        return []

    m = _margem(escala)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    saida = []
    for contorno in contornos:
        x, y, largura, altura = cv2.boundingRect(contorno)
        if largura <= 0 or altura <= 0:
            continue
        x0, y0 = bloco.x1 + m + x, bloco.y1 + m + y
        saida.append(Caixa(x0, y0, x0 + largura, y0 + altura))
    return saida


def parece_texto(glifos: Sequence[Caixa], *, escala: int) -> bool:
    """O bloco reaberto tem cara de texto? Ver `MIN_GLIFOS` e `MAX_GLIFOS`."""
    piso, teto = (f * escala for f in ALTURA_GLIFO)
    plausiveis = sum(1 for g in glifos if piso <= g.altura <= teto)
    return MIN_GLIFOS <= plausiveis <= MAX_GLIFOS


def ler_bloco(cinza: np.ndarray, bloco: Caixa, *, escala: int) -> list[Caixa] | None:
    """Os caracteres de dentro do bloco, ou `None` quando ele não é texto.

    `None` é caminho normal: o tabuleiro é recusado antes, por `candidatos`; a fotografia é
    recusada aqui, por `MAX_GLIFOS`.
    """
    glifos = glifos_do_bloco(cinza, bloco, escala=escala)
    return glifos if parece_texto(glifos, escala=escala) else None


def abrir_blocos(cinza: np.ndarray, caixas: Sequence[Caixa], *, escala: int) -> tuple[list[Caixa], list[Caixa]]:
    """`(caixas com os blocos de texto reabertos, os blocos aceitos)`."""
    abertos: dict[int, list[Caixa]] = {}
    blocos: list[Caixa] = []

    for bloco in candidatos(caixas, escala=escala):
        glifos = ler_bloco(cinza, bloco, escala=escala)
        if glifos is None:
            continue
        blocos.append(bloco)
        abertos[id(bloco)] = glifos

    saida: list[Caixa] = []
    for caixa in caixas:
        saida.extend(abertos.get(id(caixa), [caixa]))
    saida.sort(key=lambda c: (c.y1, c.x1))
    return saida, blocos


__all__ = [
    "ALTURA_GLIFO",
    "MARGEM_DA_MOLDURA",
    "MAX_GLIFOS",
    "MIN_GLIFOS",
    "TAMANHO_MINIMO",
    "TOLERANCIA_QUADRADO",
    "abrir_blocos",
    "binarizar_bloco",
    "candidatos",
    "e_quadrado",
    "glifos_do_bloco",
    "ler_bloco",
    "parece_texto",
]
