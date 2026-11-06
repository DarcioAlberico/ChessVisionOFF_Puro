"""A poeira que estica a linha (S-714).

**A perda de leiaute sob ruído não vem de binarização nem de linha que toca: vem de mancha solta.** Na folha 58 do Seirawan
degradada, o Tesseract lia `Apesar das pretas` como nada, com o oráculo a 0,47%. A linha tinha uma caixa que ia da margem à
margem e subia até a linha de cima: um ponto de poeira na margem é uma caixa de caractere como outra qualquer, a régua de
área deixa passar (ele tem o tamanho de um ponto final), `quebrar_em_linhas` o põe na linha, e `envolve` faz o resto.

**O que separa a poeira do ponto final é a vizinhança, e não o tamanho.** Pontuação, pingo e reticências moram junto de letra
ou de outra marca. Contando as caixas pequenas a mais de uma altura mediana de qualquer letra e de qualquer outra caixa pequena:

    210 folhas limpas dos 7 livros do ouro-dev    0 a 3, e 184 delas com 0
    28 folhas no perfil médio sintético           18 a 136, fora a folha do Capablanca que a escala errada já peneira

Daí a segunda regra: **uma ou duas caixas soltas não são poeira**. Numa folha limpa, a caixa solta é um `-` numa célula de
tabela. É o `POEIRA_MINIMA_NA_FOLHA`, e é ele que deixa a folha limpa como estava.

**A mancha entre duas linhas não está solta, e é a que mais custa.** Ela sobe ou desce a caixa da linha, e o leitor de linha lê
a folga como nada. `aparar` é a régua dela, na linha já formada, e `sem_excesso` corta a que `unir_pingos` colou numa letra.

A poeira entre as palavras de uma linha não sai daqui, e é de propósito: ela não muda a caixa da linha, e confundi-la com
ponto final custaria o ponto final.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .boxes import Caixa

TIRAR_POEIRA = True
"""A reversão da S-714: desligada, toda caixa pequena segue para a linha, como antes."""

POEIRA_MAIOR_LADO = 0.5
"""Maior lado da caixa pequena, em alturas medianas: abaixo disto não é letra, e pode ser ponto, pingo ou poeira."""

ALTURA_DE_LETRA = 0.65
"""A partir desta fração da altura mediana a caixa é letra. A mesma régua de `boxes.CAIXA_CURTA` e `linhas.CAIXA_CURTA`."""

POEIRA_DISTANCIA = 1.0
"""Distância a qualquer letra e a qualquer caixa pequena, em alturas medianas, acima da qual a caixa pequena está solta."""

POEIRA_MINIMA_NA_FOLHA = 6
"""Abaixo de quantas caixas soltas a folha não tem poeira. Ver a tabela do cabeçalho: entre 3 e 18 não houve folha."""


FOLGA_DO_MIOLO = 0.35
"""Até onde o centro de uma caixa pequena pode passar do miolo da linha, em alturas medianas: a altura de um ascendente."""

VAO_DA_PONTA = 1.5
"""Vão, em `POEIRA_DISTANCIA`, a partir do qual a caixa pequena na ponta da linha não é pontuação dela."""

LETRA_ACIMA_DO_MIOLO = 0.9
"""Até onde uma letra sobe acima do topo mediano da linha, em alturas medianas: a maiúscula acentuada."""

LETRA_ABAIXO_DO_MIOLO = 0.5
"""Até onde uma letra desce abaixo do fundo mediano da linha, em alturas medianas: o descendente."""

LINHA_INTEIRA = 3.0
"""Acima de quantas alturas medianas a linha não é uma linha só, e não tem miolo. Não é o caso desta régua: é o da S-712."""

MIN_LETRAS_NA_LINHA = 3
"""Com menos letras do que isto a linha não tem miolo que se meça."""


def soltas(caixas: Sequence[Caixa]) -> list[int]:
    """Os índices das caixas pequenas sem letra nem outra caixa pequena por perto.

    **A outra caixa pequena conta**: as reticências de `9 . . . Cxe4` são três pontos sem letra ao lado, numa fonte miúda, e
    são os únicos pontos que uma folha limpa tinha a perder. A mancha quase nunca tem companhia.

    As máscaras são da folha inteira, em vez de comparar par a par, porque a folha com meio-tom tem dezenas de milhares de
    caixas pequenas, e pequena contra letra seria um produto delas.
    """
    if not caixas:
        return []
    alturas = sorted(c.altura for c in caixas)
    mediana = alturas[len(alturas) // 2] or 1
    pequena = POEIRA_MAIOR_LADO * mediana
    letra = ALTURA_DE_LETRA * mediana
    folga = int(round(POEIRA_DISTANCIA * mediana))

    largura = max(c.x2 for c in caixas) + 1
    altura = max(c.y2 for c in caixas) + 1
    perto = np.zeros((altura, largura), dtype=bool)
    miudas = np.zeros((altura, largura), dtype=np.uint16)
    candidatas: list[int] = []
    for i, c in enumerate(caixas):
        area = (slice(max(0, c.y1 - folga), c.y2 + folga), slice(max(0, c.x1 - folga), c.x2 + folga))
        if c.altura >= letra:
            perto[area] = True
        elif max(c.largura, c.altura) < pequena:
            miudas[area] += 1
            candidatas.append(i)
    # Cada candidata cobre a si mesma uma vez: mais do que isso é vizinha.
    return [
        i
        for i in candidatas
        if not perto[caixas[i].y1 : caixas[i].y2, caixas[i].x1 : caixas[i].x2].any()
        and int(miudas[caixas[i].y1 : caixas[i].y2, caixas[i].x1 : caixas[i].x2].max(initial=0)) <= 1
    ]


def sem_poeira(caixas: Sequence[Caixa]) -> list[Caixa]:
    """As caixas sem a poeira da folha, quando há poeira. **Antes de `unir_pingos`**, que a poria sobre uma letra."""
    if not TIRAR_POEIRA:
        return list(caixas)
    fora = soltas(caixas)
    if len(fora) < POEIRA_MINIMA_NA_FOLHA:
        return list(caixas)
    tirar = set(fora)
    return [c for i, c in enumerate(caixas) if i not in tirar]


def _aparar_uma(linha: list[Caixa], *, mediana: int) -> list[Caixa]:
    letra = ALTURA_DE_LETRA * mediana
    pequena = POEIRA_MAIOR_LADO * mediana
    letras = [c for c in linha if c.altura >= letra]
    if len(letras) < MIN_LETRAS_NA_LINHA or max(c.y2 for c in letras) - min(c.y1 for c in letras) > LINHA_INTEIRA * mediana:
        return linha
    topo = sorted(c.y1 for c in letras)[len(letras) // 2]
    fundo = sorted(c.y2 for c in letras)[len(letras) // 2]

    def miudo(c: Caixa) -> bool:
        return c.altura < letra and max(c.largura, c.altura) < pequena

    miolo = [
        c
        for c in linha
        if not miudo(c) or topo - FOLGA_DO_MIOLO * mediana <= (c.y1 + c.y2) / 2 <= fundo + FOLGA_DO_MIOLO * mediana
    ]
    # **As pontas, uma a uma**: a mancha depois do ponto final está na altura certa, e só o vão a denuncia.
    vao = POEIRA_DISTANCIA * mediana * VAO_DA_PONTA
    while len(miolo) >= 2 and miudo(miolo[-1]) and miolo[-1].x1 - miolo[-2].x2 > vao:
        miolo.pop()
    while len(miolo) >= 2 and miudo(miolo[0]) and miolo[1].x1 - miolo[0].x2 > vao:
        miolo.pop(0)

    # **A mancha que `unir_pingos` já colou numa letra só sai cortando a letra**, e o corte é só o que nenhuma letra alcança.
    teto = int(topo - LETRA_ACIMA_DO_MIOLO * mediana)
    piso = int(fundo + LETRA_ABAIXO_DO_MIOLO * mediana)

    def sem_excesso(c: Caixa) -> Caixa:
        if c.altura < letra or (c.y1 >= teto and c.y2 <= piso) or c.y1 < teto - mediana or c.y2 > piso + mediana:
            return c
        return Caixa(c.x1, max(c.y1, teto), c.x2, min(c.y2, piso), c.angulo)

    return [sem_excesso(c) for c in miolo]


def aparar(linhas: Sequence[Sequence[Caixa]]) -> list[list[Caixa]]:
    """As linhas de uma tira sem a caixa pequena que está fora do miolo delas, ou solta numa ponta.

    **`sem_poeira` não vê esta**: entre duas linhas a mancha está a menos de uma altura de letra, e não está solta. Na linha,
    ela desce ou sobe a caixa inteira, e o leitor de linha lê a folga como nada: medido na folha 58 do Seirawan, `Apesar das
    pretas` sai vazia com a caixa em 62 px, e inteira com 8 px a menos. O miolo é a mediana dos topos e dos fundos das letras,
    e a folga deixa o apóstrofo e a vírgula dentro.
    """
    grupos = [list(linha) for linha in linhas]
    if not TIRAR_POEIRA or not grupos:
        return grupos
    alturas = sorted(c.altura for g in grupos for c in g)
    if not alturas:
        return grupos
    mediana = alturas[len(alturas) // 2] or 1
    return [_aparar_uma(g, mediana=mediana) for g in grupos]


__all__ = [
    "ALTURA_DE_LETRA",
    "FOLGA_DO_MIOLO",
    "LETRA_ABAIXO_DO_MIOLO",
    "LETRA_ACIMA_DO_MIOLO",
    "LINHA_INTEIRA",
    "MIN_LETRAS_NA_LINHA",
    "POEIRA_DISTANCIA",
    "POEIRA_MAIOR_LADO",
    "POEIRA_MINIMA_NA_FOLHA",
    "TIRAR_POEIRA",
    "VAO_DA_PONTA",
    "aparar",
    "sem_poeira",
    "soltas",
]
