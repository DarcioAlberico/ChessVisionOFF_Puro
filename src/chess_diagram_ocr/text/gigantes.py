"""A caixa alta demais para ser letra, e por que ela intercalava a coluna inteira (S-712).

**O sintoma parecia ser duas linhas encostadas, e não era.** As folhas 278 e 577 do *Chess Evolution 2013* saíam
`k15n.ig..♘ht/da4.!th1o6u`, e o roadmap supunha que a caixa de uma linha tinha engolido a vizinha. Medido em
2026-11-06, a linha é `(0, 0, 466, 595)` em pontos, a folha de alto a baixo: a faixa azul lateral, de
`(0, 0, 377, 1819)` em pixels, chega até aqui como **uma caixa de caractere**. É a mesma faixa da S-711; ali o filete
a ligava à borda e ela saía como moldura, e aqui ela está solta.

`linhas.bandas` ordena por `y1`, e ela é a primeira a entrar: abre a banda com o fundo no pé da folha, e as letras
das primeiras linhas da coluna entram todas na mesma banda, ordenadas por `x`. É o `k15n`: duas linhas lidas de
través. E o recorte que o leitor de linha recebe é o retângulo disso, a coluna inteira.

**Duas perguntas diferentes, e a primeira versão as confundia.** Tirar da lista tudo o que passa de 8 escalas consertava
a coluna, e apagava `PRACTICAL MATTERS`, `OPENING` e o quadro `CHAPTER SIX`: letra de título de verdade, que o glifo lê
mal e o Tesseract lê certo. Então:

- `sem_gigantes` tira **o que não é letra**: a faixa, o fio, a foto, e a moldura aberta, cujas letras de dentro já são
  caixas. Sai da lista, e não da binária: da binária, o miolo das letras brancas da faixa viraria sinal.
- `separar_grandes` isola **o que é letra grande demais**: ela continua sendo lida, numa linha só dela, sem abrir banda
  na coluna. Ver `leitor._tiras`.

Sai **depois** de `quadros.molduras_nas_caixas`, que precisa da moldura de quadro para medi-la. O que sai e de onde está em
`docs/metrics/texto_prosa_s712.json`, `auditoria_das_caixas`.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .boxes import Caixa

TIRAR_GIGANTES = True
"""A reversão da S-712: desligada, a lista não muda, e a coluna se intercala como antes."""

ALTURA_DE_GRANDE = 8.0
"""Em escalas de caractere: acima disto a caixa não entra na banda de ninguém, seja letra de título ou não."""

FRACAO_DA_FOLHA = 0.3
"""Da altura da folha: acima disto é faixa ou foto. O título do *Silman* mede 0,09 da folha, e a faixa, 1,0."""

LARGURA_DE_FIO = 0.5
"""Em escalas: grande e mais estreita que isto é fio. Um `I` de título, nessa altura, é mais largo."""

LETRAS_DENTRO = 3
"""Quantas caixas com o centro dentro dela fazem da caixa grande uma moldura aberta, e não uma letra."""

LADO_DE_MANCHA = 3.0
"""Em escalas: a foto pequena fica abaixo de `ALTURA_DE_GRANDE`, e quem a separa da letra é a tinta."""

TINTA_DE_MANCHA = 0.8
"""Fração de tinta no retângulo. A foto do *Chess Evolution 2014* dá 0,94; a letra deixa o retângulo com vão."""


def _e_mancha(caixa: Caixa, binaria: np.ndarray, *, escala: int) -> bool:
    """Larga e alta como várias letras, e quase toda tinta: é foto, e letra nenhuma é assim."""
    if caixa.altura < LADO_DE_MANCHA * escala or caixa.largura < LADO_DE_MANCHA * escala:
        return False
    recorte = caixa.recortar(binaria)
    return recorte.size > 0 and float(np.count_nonzero(recorte)) / recorte.size >= TINTA_DE_MANCHA


def _contem(caixa: Caixa, outras: Sequence[Caixa]) -> bool:
    """Tem `LETRAS_DENTRO` caixas com o centro dentro dela? Parar na terceira é o que mantém isto barato."""
    achadas = 0
    for outra in outras:
        centro_x, centro_y = (outra.x1 + outra.x2) / 2, (outra.y1 + outra.y2) / 2
        if outra is not caixa and caixa.x1 <= centro_x <= caixa.x2 and caixa.y1 <= centro_y <= caixa.y2:
            achadas += 1
            if achadas >= LETRAS_DENTRO:
                return True
    return False


def _nao_e_letra(caixa: Caixa, caixas: Sequence[Caixa], binaria: np.ndarray, *, escala: int) -> bool:
    if _e_mancha(caixa, binaria, escala=escala):
        return True
    if caixa.altura <= ALTURA_DE_GRANDE * escala:
        return False
    return (
        caixa.altura >= FRACAO_DA_FOLHA * binaria.shape[0]
        or caixa.largura < LARGURA_DE_FIO * escala
        or _contem(caixa, caixas)
    )


def sem_gigantes(caixas: Sequence[Caixa], binaria: np.ndarray, *, escala: int) -> Sequence[Caixa]:
    """As caixas sem as que não são letra. **A mesma lista se não há nenhuma.**"""
    if not TIRAR_GIGANTES or escala <= 0:
        return caixas
    fora = {id(c) for c in caixas if _nao_e_letra(c, caixas, binaria, escala=escala)}
    if not fora:
        return caixas
    return [caixa for caixa in caixas if id(caixa) not in fora]


def separar_grandes(caixas: Sequence[Caixa], *, escala: int) -> tuple[list[Caixa], list[Caixa]]:
    """`(as de altura de texto, as grandes)`. A grande é letra de título, e sai numa linha só dela."""
    if not TIRAR_GIGANTES or escala <= 0:
        return list(caixas), []
    teto = ALTURA_DE_GRANDE * escala
    return [c for c in caixas if c.altura <= teto], [c for c in caixas if c.altura > teto]


__all__ = [
    "ALTURA_DE_GRANDE",
    "FRACAO_DA_FOLHA",
    "LADO_DE_MANCHA",
    "LARGURA_DE_FIO",
    "LETRAS_DENTRO",
    "TINTA_DE_MANCHA",
    "TIRAR_GIGANTES",
    "separar_grandes",
    "sem_gigantes",
]
