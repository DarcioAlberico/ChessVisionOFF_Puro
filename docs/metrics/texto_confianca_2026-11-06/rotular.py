"""O rótulo de cada palavra lida: certa ou errada contra a referência, sem rodar motor (S-760, S-761).

A palavra da saída é comparada à referência **depois da normalização `tip`, token a token**, e só a prosa da régua conta como erro: é a
definição da G5 provisória da S-718, com o `difflib` trocado por uma programação dinâmica, que não se perde em tokens repetidos.
O rótulo é da folha **final**, e volta aos tokens da fusão pela igualdade do texto da linha.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from chess_diagram_ocr.text import regua_prosa as regua

PROSA = regua.PROSA


def ler(*caminhos: str | Path) -> list[dict[str, Any]]:
    registros: list[dict[str, Any]] = []
    for caminho in caminhos:
        with open(caminho, encoding="utf-8") as arquivo:
            registros.extend(json.loads(linha) for linha in arquivo)
    return registros


def _norm(token: str, lingua: str) -> str:
    return regua.normalizar(token, regua.TIP, lingua).strip()


def alinhar_tokens(a: Sequence[str], b: Sequence[str]) -> list[tuple[int, int]]:
    """Os pares `(i, j)` iguais de uma LCS. O tamanho é o de uma folha, e o `numpy` deixa isto em milissegundos."""
    import numpy as np

    n, m = len(a), len(b)
    if not n or not m:
        return []
    ids: dict[str, int] = {}
    av = np.array([ids.setdefault(t, len(ids)) for t in a])
    bv = np.array([ids.setdefault(t, len(ids)) for t in b])
    tabela = np.zeros((n + 1, m + 1), dtype=np.int32)
    for i in range(1, n + 1):
        iguais = av[i - 1] == bv
        linha = tabela[i - 1, :-1] + iguais
        linha = np.maximum(linha, tabela[i - 1, 1:])
        tabela[i, 1:] = np.maximum.accumulate(linha)
    pares = []
    i, j = n, m
    while i and j:
        if a[i - 1] == b[j - 1] and tabela[i, j] == tabela[i - 1, j - 1] + 1:
            pares.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif tabela[i - 1, j] >= tabela[i, j - 1]:
            i -= 1
        else:
            j -= 1
    pares.reverse()
    return pares


def rotular_linhas(ref: str, linhas: Iterable[str], lingua: str) -> dict[str, Any]:
    """Por linha, por token: `True` é palavra de prosa errada. E as palavras de prosa da referência que nenhum token cobriu."""
    tokens_ref = [_norm(t, lingua) for t in ref.split()]
    por_linha = [ln.split() for ln in linhas]
    planos = [(n, k, t) for n, tokens in enumerate(por_linha) for k, t in enumerate(tokens)]
    hip = [_norm(t, lingua) for _, _, t in planos]
    pares = alinhar_tokens(tokens_ref, hip)
    certos = {j for _, j in pares}
    cobertos = {i for i, _ in pares}
    errada: list[list[bool]] = [[False] * len(t) for t in por_linha]
    prosa: list[list[bool]] = [[False] * len(t) for t in por_linha]
    for indice, (n, k, token) in enumerate(planos):
        e_prosa = regua.classe_do_token(token, lingua) == PROSA
        prosa[n][k] = e_prosa
        errada[n][k] = e_prosa and indice not in certos
    perdidas = sum(1 for i, t in enumerate(ref.split()) if i not in cobertos and regua.classe_do_token(t, lingua) == PROSA)
    return {"errada": errada, "prosa": prosa, "perdidas": perdidas, "n_ref_prosa": sum(regua.classe_do_token(t, lingua) == PROSA for t in ref.split())}


def tokens_rotulados(r: dict[str, Any]) -> tuple[list[tuple[dict[str, Any], bool, bool, int, int]], int]:
    """Os tokens da fusão com `(token, errada, prosa, n da linha, k)`, pela igualdade do texto da linha final, e quantos não voltaram."""
    finais = [ln["texto"] for ln in r["linhas"]]
    rotulo = rotular_linhas(r["ref"], finais, r["lingua"])
    onde: dict[str, list[int]] = {}
    for n, texto in enumerate(finais):
        onde.setdefault(" ".join(texto.split()), []).append(n)
    saida = []
    sem_rotulo = 0
    for n, linha in enumerate(r["tokens"]):
        texto = " ".join(t["texto"] for t in linha)
        fila = onde.get(" ".join(texto.split()))
        if not fila:
            sem_rotulo += len(linha)
            continue
        final = fila.pop(0)
        for k, token in enumerate(linha):
            if k < len(rotulo["errada"][final]):
                saida.append((token, rotulo["errada"][final][k], rotulo["prosa"][final][k], n, k))
    return saida, sem_rotulo
