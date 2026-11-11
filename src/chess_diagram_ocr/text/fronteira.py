"""O espaço que o vão entre as caixas não mostra, e o léxico como árbitro dele (S-732).

`linhas.texto_da_linha` põe espaço pelo vão **entre os bboxes**, e o bbox do `f` inclui o gancho, que
avança sobre a letra seguinte. `of the` tem o vão de um `ft` colado: 7 px, contra um limite de 7,6.
Nas 27 folhas dos 5 livros aprovados, faltaram 37 espaços, e 12 dos 14 do Dvoretsky são depois de `f`.

## O vão de baixo separa, mas não sozinho

Medindo só a faixa de baixo da altura-de-x, onde o `f` é uma haste (em alturas-de-x):

                               p5     mediana    p95
    com espaço, já detectado   0,48    0,72      1,24
    espaço que faltou          0,20    0,54      1,01
    sem espaço                 0,05    0,16      0,33

**A faixa não basta**: `r|a`, `r|e`, `q|u` e `v|e` também têm o braço no alto e o vão embaixo, e são 1.381
pares acima de 0,30 num total de 19.555. O vão só propõe, e quem dispõe é o léxico.

## O léxico sozinho já foi medido, e perdeu

`lexico.PARTIR_COLADAS` registra: 0 partições certas contra 5 erradas em 40 páginas, porque `carrying` vira
`carr ying` quando `Carr` e `Ying` são sobrenomes. Aqui são três as diferenças, e cada uma é por isso:

1. só o corte que tem o vão de baixo é candidato, e fora do `f`, cujo gancho come o vão de cima, ele
   também tem de ter vão de cima (`VAO_DE_CIMA_MINIMO`): `carrying` tem `r|y` com o braço encostado;
2. os pedaços curtos saem de uma lista fechada (`palavras_curtas`) e os longos, do léxico **sem nomes**;
3. um nome só vale de pedaço a partir de `NOME_MINIMO` letras: `Reshevsky joga` passa, e `Carr` não.

**E o pedaço da direita tem ao menos 3 letras, salvo depois do `f`.** O português conjuga: `romperam` e
`transferem` não estão no léxico, e `romper` + `am` e `transfer` + `em` estão, nas duas línguas de um
acervo que mistura as duas. Foi o que a primeira rodada partiu errado.

Ambiguidade não corrige, como em toda decisão do dicionário.

## A outra direção

`ganhando` saía `ga n ha ndo` em *Minhas 60*: o vão de quem é estreito passa do limite. `juntar` cola os
tokens quando a junção é uma palavra longa do léxico sem nomes e algum dos tokens não existe.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np

from .boxes import Caixa
from .lexico import PONTUACAO_DE_BORDA
from .palavras_curtas import CURTAS, conhecida_ou_curta

LIGADO = True
"""A reversão da S-732: partir."""

JUNTAR_PARTIDAS = True
"""A reversão da outra direção da S-732: juntar."""

VAO_BAIXO_MINIMO = 0.30
"""Em alturas-de-x. Acima de 95% dos pares sem espaço, e abaixo de 90% dos espaços que faltaram."""

VAO_DE_CIMA_MINIMO = 0.15
"""Em alturas-de-x, entre os bboxes, quando a esquerda não é `f`. Mediana sem espaço: 0,11."""

DIREITA_CURTA_MINIMA = 3
"""Letras do pedaço da direita, quando a esquerda não termina em `f`."""

ESQUERDA_MINIMA = 2
"""`a posição` existe, mas `aposição` também: a de uma letra só fica para o Tesseract."""

FAIXA_DO_VAO = 0.6
"""Quanto da altura-de-x, a partir da linha de base, entra na medida do vão de baixo."""

NOME_MINIMO = 6
"""Abaixo disto, pedaço que só existe na lista de nomes não conta: `Carr`, `Ying`."""

JUNCAO_MINIMA = 5
"""A junção de tokens tem de ser uma palavra de pelo menos tantas letras."""

MAX_TOKENS_DA_JUNCAO = 4
"""`ga n ha ndo` tem quatro."""

ANTES_DE_LANCE = frozenset({"of", "if", "in", "on", "at", "by", "to", "and", "or", "de", "em", "ou", "com"})
"""As palavras que ficam coladas num número de lance: `of2.exf6`, `if2...`. Fechada de propósito:
`Be2.` também é palavra curta seguida de número, e é lance. **`e` não entra**: `e7.` é a casa, no fim da frase."""

_NUMERO_DE_LANCE = re.compile(r"^\d+\.")
_SO_LETRAS = re.compile(r"^[^\W\d_]+$")


def vao_de_baixo(binaria: np.ndarray, a: Caixa, b: Caixa, base: float, xh: float) -> float | None:
    """O vão entre as duas caixas, olhando só a faixa de baixo. `None` se alguma não tem tinta lá."""
    y0 = max(0, int(base - FAIXA_DO_VAO * xh))
    y1 = max(y0 + 1, int(base))

    def extremos(c: Caixa) -> tuple[int, int] | None:
        x0 = max(0, c.x1)
        colunas = np.nonzero((binaria[y0:y1, x0 : c.x2] > 0).any(axis=0))[0]
        return None if colunas.size == 0 else (x0 + int(colunas[0]), x0 + int(colunas[-1]) + 1)

    ea, eb = extremos(a), extremos(b)
    return None if ea is None or eb is None else float(eb[0] - ea[1])


def _pedaco_vale(pedaco: str, lexico_sem_nomes: frozenset[str], lexico: frozenset[str]) -> bool:
    limpo = pedaco.strip(PONTUACAO_DE_BORDA).casefold()
    if not limpo or not _SO_LETRAS.match(limpo):
        return False
    if conhecida_ou_curta(limpo, lexico_sem_nomes):
        return True
    return len(limpo) >= NOME_MINIMO and limpo in lexico


def cortes(
    chars: Sequence[str],
    candidatos: Sequence[int],
    lexico_sem_nomes: frozenset[str],
    lexico: frozenset[str],
) -> list[int] | None:
    """Os cortes (entre `k-1` e `k`) que deixam só palavras conhecidas, ou `None` se não há um único jeito.

    `candidatos` são os índices com o vão de baixo. Procura com um corte e depois com dois, e a primeira
    quantidade que resolve decide: quem parte em dois não precisa ser comparado com quem parte em três.
    """
    palavra = "".join(chars)
    if conhecida_ou_curta(palavra, lexico):
        return None
    if not _SO_LETRAS.match(palavra.strip(PONTUACAO_DE_BORDA)):
        return None

    def vale(de: int, ate: int) -> bool:
        return _pedaco_vale("".join(chars[de:ate]), lexico_sem_nomes, lexico)

    def direita_ok(k: int, ate: int) -> bool:
        tamanho = len("".join(chars[k:ate]).strip(PONTUACAO_DE_BORDA))
        return tamanho >= DIREITA_CURTA_MINIMA or chars[k - 1] == "f"

    def esquerda_ok(k: int) -> bool:
        return len("".join(chars[:k]).strip(PONTUACAO_DE_BORDA)) >= ESQUERDA_MINIMA

    candidatos = [k for k in candidatos if esquerda_ok(k) and direita_ok(k, len(chars))]
    um = [k for k in candidatos if vale(0, k) and vale(k, len(chars))]
    if um:
        return um if len(um) == 1 else None
    dois = [
        [k, j]
        for i, k in enumerate(candidatos)
        for j in candidatos[i + 1 :]
        if vale(0, k) and vale(k, j) and vale(j, len(chars))
    ]
    return dois[0] if len(dois) == 1 else None


def corrigir(
    lidos: Sequence[tuple[str, float]],
    caixas: Sequence[Caixa],
    binaria: np.ndarray,
    lexico: frozenset[str],
    lexico_sem_nomes: frozenset[str],
    *,
    xh: float,
) -> list[tuple[str, float]]:
    """Parte as palavras coladas, pondo o espaço na frente do caractere: `texto_da_linha` só concatena."""
    saida = list(lidos)
    if not LIGADO or not lidos or not lexico or xh <= 0 or len(lidos) != len(caixas):
        return saida

    from .dicionario import palavras
    from .notacao import peso_de_notacao

    base = float(np.median([c.y2 for c in caixas]))
    for inicio, fim in palavras(caixas, lidos):
        chars = [c for c, _ in lidos[inicio:fim]]
        if fim - inicio < 3:
            continue
        candidatos = []
        for k in range(1, fim - inicio):
            vao = vao_de_baixo(binaria, caixas[inicio + k - 1], caixas[inicio + k], base, xh)
            acima = (caixas[inicio + k].x1 - caixas[inicio + k - 1].x2) / xh
            de_f = chars[k - 1] == "f"
            if vao is not None and vao / xh >= VAO_BAIXO_MINIMO and (de_f or acima >= VAO_DE_CIMA_MINIMO):
                candidatos.append(k)
        if not candidatos:
            continue

        lance = _corte_antes_de_lance(chars, candidatos)
        if lance is not None:
            saida[inicio + lance] = (" " + saida[inicio + lance][0], saida[inicio + lance][1])
            continue
        if peso_de_notacao("".join(chars)) > 0:
            continue
        achados = cortes(chars, candidatos, lexico_sem_nomes, lexico)
        for k in achados or ():
            saida[inicio + k] = (" " + saida[inicio + k][0], saida[inicio + k][1])
    return saida


def _corte_antes_de_lance(chars: Sequence[str], candidatos: Sequence[int]) -> int | None:
    """O corte em `of2.exf6`: palavra de `ANTES_DE_LANCE` em minúscula, e o resto começa num número."""
    for k in candidatos:
        esquerda = "".join(chars[:k]).lstrip(PONTUACAO_DE_BORDA)
        if esquerda in ANTES_DE_LANCE and _NUMERO_DE_LANCE.match("".join(chars[k:])):
            return k
    return None


def juntar(texto: str, lexico_sem_nomes: frozenset[str]) -> str:
    """Cola os tokens que o vão separou sem motivo: `ga n ha ndo` -> `ganhando`, `estava m` -> `estavam`.

    Só quando a junção é conhecida, tem ao menos `JUNCAO_MINIMA` letras e **algum token dela não existe**:
    `a partida` não vira `apartida`, ainda que a junção estivesse na lista.
    """
    if not JUNTAR_PARTIDAS or not lexico_sem_nomes or " " not in texto:
        return texto

    tokens = texto.split(" ")
    saida: list[str] = []
    i = 0
    while i < len(tokens):
        junta = None
        for n in range(min(MAX_TOKENS_DA_JUNCAO, len(tokens) - i), 1, -1):
            pedacos = tokens[i : i + n]
            cauda = pedacos[-1].rstrip(PONTUACAO_DE_BORDA)
            nucleos = [*pedacos[:-1], cauda]
            if not all(_SO_LETRAS.match(p) for p in nucleos):
                continue
            unida = "".join(nucleos)
            if len(unida) < JUNCAO_MINIMA or unida.casefold() not in lexico_sem_nomes:
                continue
            if all(_existe(p, lexico_sem_nomes) for p in nucleos):
                continue
            junta = (n, unida + pedacos[-1][len(cauda) :])
            break
        if junta is None:
            saida.append(tokens[i])
            i += 1
        else:
            saida.append(junta[1])
            i += junta[0]
    return " ".join(saida)


def _existe(token: str, lexico: frozenset[str]) -> bool:
    """O token existe por si? Três letras contam como sim: o léxico não as tem, e `cut off` não é `cutoff`."""
    return len(token) == 3 or token.casefold() in lexico or token.casefold() in CURTAS


__all__ = [
    "ANTES_DE_LANCE",
    "FAIXA_DO_VAO",
    "JUNCAO_MINIMA",
    "JUNTAR_PARTIDAS",
    "LIGADO",
    "NOME_MINIMO",
    "VAO_BAIXO_MINIMO",
    "VAO_DE_CIMA_MINIMO",
    "corrigir",
    "cortes",
    "juntar",
    "vao_de_baixo",
]
