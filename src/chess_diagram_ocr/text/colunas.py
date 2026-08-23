"""Onde a coluna acaba, medido na imagem (S-190 e S-191).

Este projeto já ordena por coluna **dentro de um bloco da camada de texto** -- é o
`pdf_text._split_into_columns` da S-16, e ele resolve o caso do `Karpov`, que põe as legendas das
duas colunas num bloco só. Isso não é a mesma coisa que saber onde a coluna acaba na **imagem**,
e a diferença é o que separa os 20 livros com camada de texto dos 7 sem.

## A calha se acha projetando linhas, e não boxes

**Contar boxes é um `OR`, e um `OR` morre com uma letra.** Era assim no projeto de origem até a
F70, e o sintoma era errático porque a variável é onde a letra do cabeçalho calha de cair: o
cabeçalho corrente centralizado pousa em cima da calha, e um único box de 25x27 px em y≈105
derruba a calha de 31 px para 7 no Nunn. A página sai com as duas colunas intercaladas.

Contando **linhas**, o cabeçalho é uma só e passa pela tolerância, enquanto o miolo de uma página
de coluna única é coberto por todas as quarenta -- o espaço entre palavras do texto justificado
cai num x diferente a cada linha, e nenhum x central sobrevive à conta.

Tolerar **uma** linha, medido lá nas 456 páginas de prosa de 4 livros:

    Nunn (2 colunas)           298 -> 316 de 352 páginas
    Aagaard (2 colunas)          3 ->  28 de 30
    Yusupov Complete (2 col)    23 ->  26 de 35
    Darcy Lima (1 coluna)        0 ->   0 de 39   <- o controle

Duas linhas não acrescentam nada no Nunn e começam a partir o Yusupov (32 de 35): o ponto é uma.

## Achar o vão não basta: a faixa que ele deixa tem de ser uma coluna

O vão entre o título e o número da página de um sumário é largo, e tratá-lo como calha faz o
livro sair com os títulos todos juntos e os números todos juntos. Medido lá, a "coluna" de número
de capítulo tem 2% da largura do texto e a de número de página 4%, contra 48% de cada coluna de
verdade no Kasparov. O piso fica no vão: 2,5x acima do maior falso e 4,5x abaixo da menor coluna
de verdade.

**A faixa estreita é fundida, e não descartada.** A faixa é o critério de quem entra em qual
coluna, e uma faixa a menos seria um punhado de boxes lidos no fim da página, fora de ordem.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .boxes import Caixa
from .linhas import bandas

CALHA_EM_CARACTERES = 0.8
"""Largura mínima de uma calha, em larguras medianas de caractere.

**Eram 3,0 no projeto de origem até a F61, e é por isso que o livro de duas colunas saía
embaralhado.** Medido em 33 páginas de 6 livros:

    calha de verdade   Nunn        1,00 - 1,18   (17-20 px, e é o resto que o cabeçalho deixou)
                       Kasparov    2,58 - 3,31   (49-58 px)
                       Yusupov     2,59 - 2,94   (44-46 px)
    vão que não é      Yusupov     0,17 - 0,75

A 3,0 o Nunn nunca é detectado e o Kasparov é detectado em algumas páginas e não em outras -- que
é exatamente a queixa. 0,8 fica 1,25x abaixo da menor calha medida e 6,7x acima do maior vão que
não é calha. O espaço entre palavras não chega perto porque a projeção é da **página inteira**:
para sobreviver a ela, toda linha teria de ter espaço no mesmo x."""

CALHA_DA_PAGINA = 0.01
"""O piso da calha em frações da largura do texto, para a página cuja largura mediana de
caractere não vale nada.

Mesmo motivo do `escala_de_texto`: numa página com trama a mediana simples desaba para 2 px, e
`0,8 x 2` deixaria qualquer respiro virar coluna. Medido lá na página 66 do *Chess Evolution 1*
-- trama de scan na margem, mediana 2 px, calha de verdade com 34 px --, 1% da largura do texto
dá 18 px: barra o respingo e deixa passar a calha. A 2% barrava também a do Nunn."""

COLUNA_MINIMA = 0.10
"""Largura mínima de uma coluna, em frações da largura do texto. Ver o cabeçalho."""

LINHAS_NA_CALHA = 1
"""Quantas linhas de texto podem cruzar a calha sem que ela deixe de existir. Ver o cabeçalho."""

LINHAS_PARA_TOLERAR = 12
"""A partir de quantas linhas a página pode desprezar uma delas na calha.

**Uma linha de cinco é 20% da página, e aí a tolerância inventa calha.** Medido lá num recorte de
cinco linhas em duas colunas, tolerar uma abre uma terceira faixa onde a contagem mínima é 1: o
vão entre duas palavras que calham de se alinhar em cinco linhas seguidas. Na página inteira isso
não acontece.

O limiar fica no vão: 2,4x acima do recorte de 5 linhas e 1,25x abaixo da **menor** página de
prosa medida (15 linhas no Nunn, contra 23 no Aagaard e 30 no Darcy Lima). Abaixo dele vale a
régua de antes -- nenhuma linha tolerada --, que é o lado seguro do erro."""

CALHA_MINIMA_ABSOLUTA = 4
"""Piso em pixels. Abaixo disto nada é calha, em nenhuma escala."""


def linhas_por_x(grupos: Sequence[Sequence[Caixa]], x_min: int, largura: int) -> np.ndarray:
    """Quantas **linhas** cobrem cada x. É a projeção que a F70 pôs no lugar do `OR`.

    **O que marca é a união dos boxes da linha, e não a caixa que a envolve.** Numa página de
    duas colunas a banda recolhe a linha da esquerda e a da direita juntas, porque estão na mesma
    altura; envolvê-las numa caixa só encheria a calha, que é exatamente o vão que se quer
    enxergar vazio.
    """
    conta = np.zeros(largura + 2, dtype=np.int32)
    for grupo in grupos:
        desta = np.zeros(largura + 2, dtype=bool)
        for caixa in grupo:
            desta[max(0, caixa.x1 - x_min) : max(0, caixa.x2 - x_min) + 1] = True
        conta += desta
    return conta


def calha(caixas: Sequence[Caixa], *, calha_minima: int | None = None) -> list[tuple[int, int]]:
    """As faixas verticais de `x` que separam colunas, em pixels da imagem. Vazio se não houver.

    `calha_minima=None` deriva o piso da largura mediana de caractere e da largura do texto --
    ver `CALHA_EM_CARACTERES` e `CALHA_DA_PAGINA`.
    """
    if not caixas:
        return []

    x_min = min(c.x1 for c in caixas)
    x_max = max(c.x2 for c in caixas)
    largura = x_max - x_min
    if largura <= 1:
        return []

    grupos = bandas(caixas)
    tolerado = LINHAS_NA_CALHA if len(grupos) >= LINHAS_PARA_TOLERAR else 0
    livre = linhas_por_x(grupos, x_min, largura) <= tolerado

    if calha_minima is None:
        larguras = sorted(c.largura for c in caixas)
        mediana = larguras[len(larguras) // 2] or 1
        calha_minima = max(
            int(mediana * CALHA_EM_CARACTERES),
            int(largura * CALHA_DA_PAGINA),
            CALHA_MINIMA_ABSOLUTA,
        )

    achadas: list[tuple[int, int]] = []
    inicio: int | None = None
    for i, vago in enumerate(livre):
        if vago:
            if inicio is None:
                inicio = i
        else:
            # **O vão que encosta na margem esquerda não é calha.** Com o `OR` ele não tinha como
            # existir -- algum box começa em `x_min` por definição --, mas a tolerância o cria na
            # página em que só o cabeçalho alcança a margem. Abrir faixa ali deixaria os boxes
            # dele fora de toda coluna.
            if inicio is not None and inicio > 0 and i - inicio >= calha_minima:
                achadas.append((x_min + inicio, x_min + i))
            inicio = None
    return achadas


def detectar_colunas(caixas: Sequence[Caixa], *, calha_minima: int | None = None) -> list[tuple[int, int]]:
    """As faixas de coluna, em ordem de leitura. Uma faixa só quando a página é de coluna única."""
    if not caixas:
        return []

    x_min = min(c.x1 for c in caixas)
    x_max = max(c.x2 for c in caixas)
    if x_max - x_min <= 1:
        return [(x_min, x_max)]

    cortes = calha(caixas, calha_minima=calha_minima)
    if not cortes:
        return [(x_min, x_max)]

    faixas: list[tuple[int, int]] = []
    anterior = x_min
    for inicio, fim in cortes:
        if inicio > anterior:
            faixas.append((anterior, inicio - 1))
        anterior = fim
    if anterior <= x_max:
        faixas.append((anterior, x_max))

    faixas = [f for f in faixas if f[1] > f[0]] or [(x_min, x_max)]
    return _fundir_faixas_estreitas(faixas, x_max - x_min)


def _fundir_faixas_estreitas(faixas: list[tuple[int, int]], largura: int) -> list[tuple[int, int]]:
    """Funde na vizinha toda faixa estreita demais para ser coluna. Ver o cabeçalho.

    Some pela calha **mais estreita** das duas ao redor, que é a que menos afirma separação.
    """
    minima = largura * COLUNA_MINIMA
    faixas = list(faixas)
    while len(faixas) > 1:
        i = min(range(len(faixas)), key=lambda j: faixas[j][1] - faixas[j][0])
        if faixas[i][1] - faixas[i][0] >= minima:
            break
        esquerda = faixas[i][0] - faixas[i - 1][1] if i else None
        direita = faixas[i + 1][0] - faixas[i][1] if i + 1 < len(faixas) else None
        if direita is None or (esquerda is not None and esquerda <= direita):
            faixas[i - 1 : i + 1] = [(faixas[i - 1][0], faixas[i][1])]
        else:
            faixas[i : i + 2] = [(faixas[i][0], faixas[i + 1][1])]
    return faixas


def atribuir_coluna(caixa: Caixa, colunas: Sequence[tuple[int, int]]) -> int:
    """Em qual coluna esta caixa está. **Quem cai na calha fica com a faixa mais próxima** (F70).

    Antes sobrava: a caixa que não coubesse em faixa nenhuma era despejada depois de tudo, e isso
    era inofensivo enquanto a calha tinha 20 px e nada cabia lá dentro. Com a calha de verdade --
    56 px no Nunn -- quem mora ali é o caractere central do cabeçalho corrente, o mesmo que
    apagava a calha, e ele passava a sair **depois da página inteira**.
    """
    if not colunas:
        return 0
    centro = (caixa.x1 + caixa.x2) / 2.0
    for i, (x1, x2) in enumerate(colunas):
        if x1 <= centro <= x2:
            return i
    return min(range(len(colunas)), key=lambda i: min(abs(centro - colunas[i][0]), abs(centro - colunas[i][1])))


def atravessa(caixa: Caixa, colunas: Sequence[tuple[int, int]]) -> bool:
    """A caixa cobre mais de uma coluna? Título e diagrama largo cobrem, e não pertencem a uma."""
    return sum(1 for x1, x2 in colunas if caixa.x1 <= x2 and caixa.x2 >= x1) > 1


__all__ = [
    "CALHA_DA_PAGINA",
    "CALHA_EM_CARACTERES",
    "CALHA_MINIMA_ABSOLUTA",
    "COLUNA_MINIMA",
    "LINHAS_NA_CALHA",
    "LINHAS_PARA_TOLERAR",
    "atravessa",
    "atribuir_coluna",
    "calha",
    "detectar_colunas",
    "linhas_por_x",
]
