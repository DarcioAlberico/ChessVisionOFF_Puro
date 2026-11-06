"""O desenho comum dos testes de decisão da Fase 103: caixas e probabilidades sintéticas, sem modelo e sem livro."""

from __future__ import annotations

import numpy as np

from chess_diagram_ocr.text.boxes import Caixa

CLASSES = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,'\"()-—/")
CLASSES += ["ç", "ã", "ä", "é", "ê", "õ", "Õ", "ó", "Ó", "fi", "f1"]
I2C = dict(enumerate(CLASSES))
C2I = {c: i for i, c in I2C.items()}


def _matriz(lidos: list[str], segundos: dict[int, str] | None = None) -> np.ndarray:
    """Probabilidades em que `lidos[k]` vence, e `segundos[k]`, quando há, vem logo atrás."""
    m = np.full((len(lidos), len(CLASSES)), 1e-5, dtype=np.float32)
    for k, c in enumerate(lidos):
        m[k, C2I[c]] = 0.6
        if segundos and k in segundos:
            m[k, C2I[segundos[k]]] = 0.3
    return m


def _linha(desenho: list[tuple[str, int, int]], *, x: int = 10, vao: int = 3, base: int = 100) -> tuple[list[str], list[Caixa]]:
    """`(caractere, largura, altura)`, assentados na mesma base e separados pelo mesmo vão.

    O terceiro campo negativo é a altura de quem desce: a parte negativa fica abaixo da base.
    """
    chars, caixas = [], []
    for char, largura, altura in desenho:
        if altura < 0:
            caixas.append(Caixa(x, base - 20, x + largura, base - altura))
        else:
            caixas.append(Caixa(x, base - altura, x + largura, base))
        chars.append(char)
        x += largura + vao
    return (chars, caixas)


def _lidos(chars: list[str]) -> list[tuple[str, float]]:
    return [(c, 0.6) for c in chars]


def _texto(lidos: list[tuple[str, float]]) -> str:
    return "".join(c for c, _ in lidos)


# Prosa em corpo de 20 px de altura-de-x: as letras de x dão a régua da linha.
DE_X = [("a", 12, 20), ("e", 12, 20), ("n", 12, 20)]
