"""Til contra trema, circunflexo contra agudo: a letra certa com o acento errado (S-735).

`não` saía `näo`, `três` saía `trés`. O modelo põe os dois acentos no topo (`ä` 0,59 e `ã` 0,30), e
**a classe que vence é a que ele quase não viu**: `ä` tem 15 amostras em `training_data/`, contra 3.797
de `ã`. Nas 27 folhas dos 5 livros aprovados, os 23 `ã`->`ä` têm a classe certa em rank 2, os 4
`ê`->`é`, em rank 3 (`ê` tem 347 amostras, `é` 1.751).

## Por que o dicionário não resolvia

Duas guardas de `dicionario.py` a barram, e as duas estão certas no que dizem: `sem_troca_de_caixa` tira
a mesma letra com outro acento (`façanha` virava `facanha`, e a cedilha é tinta), e `MIN_TAMANHO` tira
`não` e `são`. Aqui a troca é só **de um acento por outro**, e nunca tira nem põe tinta: `facanha` e
`importancia` ficam fora. E a resposta tem de existir: em livro alemão, `Spätes` não vira `Spãtes`.

**A única troca sem léxico é `äo` no fim da palavra, ou antes do hífen**: nenhuma língua do acervo escreve
isso, e `-ção` é o sufixo mais comum do português, em que o léxico falha (`moderação`). `ã` tem de estar no topo.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from itertools import combinations, product

import numpy as np

from .boxes import Caixa
from .palavras_curtas import conhecida_ou_curta

LIGADO = True
"""A reversão da S-735 para o acento."""

TOPO = 3
"""Quantos candidatos do modelo entram, por caixa. O `ê` lido `é` está em rank 3."""

PISO = 0.001
"""Probabilidade mínima da alternativa, a mesma de `dicionario.PISO_DE_CANDIDATO`."""

MAX_TROCAS = 2
"""Quantas letras de uma palavra podem trocar de acento. `câmeräs` não existe, e o custo é por caixa."""


def _base(char: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", char) if not unicodedata.combining(c))


def _tem_acento(char: str) -> bool:
    return len(char) == 1 and _base(char) != char


def alternativas(char: str, candidatos: Sequence[str]) -> list[str]:
    """Os candidatos que são a mesma letra, na mesma caixa, com **outro** acento."""
    if not _tem_acento(char):
        return []
    return [c for c in candidatos if c != char and _tem_acento(c) and _base(c) == _base(char)]


def escolher(palavra: str, opcoes: dict[int, list[str]], lexico: frozenset[str]) -> str | None:
    """A única palavra conhecida trocando só acentos, ou `None`.

    Como em `dicionario.escolher`: palavra já conhecida não se mexe, e ambiguidade não corrige.
    """
    if not opcoes or conhecida_ou_curta(palavra, lexico):
        return None
    achadas: set[str] = set()
    posicoes = sorted(opcoes)
    for n in range(1, MAX_TROCAS + 1):
        for escolha in combinations(posicoes, n):
            for trocas in product(*(opcoes[p] for p in escolha)):
                nova = list(palavra)
                for p, c in zip(escolha, trocas, strict=True):
                    nova[p] = c
                texto = "".join(nova)
                if conhecida_ou_curta(texto, lexico):
                    achadas.add(texto)
    return achadas.pop() if len(achadas) == 1 else None


def _sem_o_trema_final(palavra: str, opcoes: dict[int, list[str]]) -> str | None:
    """`moderaçäo` -> `moderação`, `näo-soviéticos` -> `não-soviéticos`, com o til entre as opções do modelo."""
    nova = list(palavra)
    for marca in re.finditer(r"(?<=\w)äo(?![^\W\d_])", palavra):
        if "ã" in opcoes.get(marca.start(), []):
            nova[marca.start()] = "ã"
    texto = "".join(nova)
    return texto if texto != palavra else None


def corrigir(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[Caixa],
    idx_to_char: dict[int, str],
    lexico: frozenset[str],
) -> list[tuple[str, float]]:
    """Troca o acento das palavras que o léxico decide. Confiança: a da classe escolhida."""
    saida = list(lidos)
    if not LIGADO or not lexico or not lidos or len(lidos) != len(caixas):
        return saida

    from .dicionario import palavras

    de_char = {c: i for i, c in idx_to_char.items() if len(c) == 1}
    for inicio, fim in palavras(caixas, lidos):
        pedaco = [c for c, _ in lidos[inicio:fim]]
        if any(len(c) != 1 for c in pedaco) or not any(_tem_acento(c) for c in pedaco):
            continue
        opcoes: dict[int, list[str]] = {}
        for i, char in enumerate(pedaco):
            k = inicio + i
            if k >= probs.shape[0]:
                continue
            ordem = np.argsort(-probs[k])[:TOPO]
            candidatos = [idx_to_char[int(j)] for j in ordem if probs[k, j] >= PISO]
            achadas = alternativas(char, candidatos)
            if achadas:
                opcoes[i] = achadas
        palavra = "".join(pedaco)
        escolhida = escolher(palavra, opcoes, lexico) or _sem_o_trema_final(palavra, opcoes)
        if escolhida is None:
            continue
        for i, novo in enumerate(escolhida):
            if novo != palavra[i]:
                saida[inicio + i] = (novo, float(probs[inicio + i, de_char[novo]]))
    return saida


__all__ = ["LIGADO", "MAX_TROCAS", "PISO", "TOPO", "alternativas", "corrigir", "escolher"]
