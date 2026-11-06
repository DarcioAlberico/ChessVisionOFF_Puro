"""A caixa alta demais para ser letra, e por que ela intercalava a coluna inteira (S-712).

**O sintoma parecia ser duas linhas encostadas, e não era.** As folhas 278 e 577 do *Chess Evolution 2013* saíam
`k15n.ig..♘ht/da4.!th1o6u`, e o roadmap supunha que a caixa de uma linha tinha engolido a vizinha. Medido em
2026-11-06, a linha é `(0, 0, 466, 595)` em pontos, a folha de alto a baixo: a faixa azul lateral, de
`(0, 0, 377, 1819)` em pixels, chega até aqui como **uma caixa de caractere**. É a mesma faixa da S-711; ali o filete
a ligava à borda e ela saía como moldura, e aqui ela está solta.

`linhas.bandas` ordena por `y1`, e ela é a primeira a entrar: abre a banda com o fundo no pé da folha, e as letras
das primeiras linhas da coluna entram todas na mesma banda, ordenadas por `x`. É o `k15n`: duas linhas lidas de
través. E o recorte que o leitor de linha recebe é o retângulo disso, a coluna inteira.

**Sai da lista de caixas, e não da binária.** Da binária, o que estava dentro dela apareceria: a faixa tem letra
branca, e o miolo dos `o` e dos `e` é tinta solta, que viraria sinal. Fora da lista, o contorno externo continua
escondendo tudo aquilo. E sai **depois** de `quadros.molduras_nas_caixas`, que precisa da moldura de quadro para
medi-la.

**O que sai perde no máximo um caractere por caixa**, porque a caixa era lida como um caractere só. Em 808 folhas de
58 livros saíram 837 caixas, contando o miolo da faixa de `text/moldura.py`, de 177 folhas: 44 tocam texto da camada,
e 24 destas são os dígitos do código de barras de uma contracapa. Ver `docs/metrics/texto_prosa_s712.json`.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .boxes import Caixa

TIRAR_GIGANTES = True
"""A reversão da S-712: desligada, a caixa fica na lista, e a coluna se intercala como antes."""

ALTURA_DE_GIGANTE = 8.0
"""Em escalas de caractere: acima disto a caixa é faixa, fio, foto ou diagrama que o detector não viu.

Medido no censo: de 8 a 12 escalas a largura mediana é de 0,6 escala, que é fio. **Abaixo disto a régua não foi
examinada caixa a caixa**: de 3 a 8 há título, capitular e também foto, e por isso a foto tem a regra da tinta."""

LADO_DE_MANCHA = 3.0
"""Em escalas: a foto pequena fica abaixo de `ALTURA_DE_GIGANTE`, e quem a separa da letra é a tinta."""

TINTA_DE_MANCHA = 0.8
"""Fração de tinta no retângulo. A foto do *Chess Evolution 2014* dá 0,94; a letra deixa o retângulo com vão."""


def _e_mancha(caixa: Caixa, binaria: np.ndarray, *, escala: int) -> bool:
    """Larga e alta como várias letras, e quase toda tinta: é foto, e letra nenhuma é assim."""
    if caixa.altura < LADO_DE_MANCHA * escala or caixa.largura < LADO_DE_MANCHA * escala:
        return False
    recorte = caixa.recortar(binaria)
    return recorte.size > 0 and float(np.count_nonzero(recorte)) / recorte.size >= TINTA_DE_MANCHA


def sem_gigantes(caixas: Sequence[Caixa], binaria: np.ndarray, *, escala: int) -> Sequence[Caixa]:
    """As caixas sem as que não são letra. **A mesma lista se não há nenhuma.**"""
    if not TIRAR_GIGANTES or escala <= 0:
        return caixas
    teto = ALTURA_DE_GIGANTE * escala
    fora = {id(c) for c in caixas if c.altura > teto or _e_mancha(c, binaria, escala=escala)}
    if not fora:
        return caixas
    return [caixa for caixa in caixas if id(caixa) not in fora]


__all__ = ["ALTURA_DE_GIGANTE", "LADO_DE_MANCHA", "TINTA_DE_MANCHA", "TIRAR_GIGANTES", "sem_gigantes"]
