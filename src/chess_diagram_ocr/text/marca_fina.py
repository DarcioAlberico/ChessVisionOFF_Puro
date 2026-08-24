"""Apóstrofo ou vírgula, decidido pela **posição na linha** (S-211).

Irmão de `text/caixa_alta.py`, e pelo mesmo motivo de fundo: o recorte que o classificador recebe
é o **bbox apertado** do contorno, então tudo que distingue dois glifos por *onde eles moram na
linha* é apagado antes de o modelo ver a imagem. Lá era o tamanho; aqui é a altura em que a marca
assenta.

    '  apóstrofo, aspa      no alto da linha
    ,  vírgula              na base, descendo abaixo dela
    .  ponto                na base

Isolados e redimensionados para 32x32, os três são a mesma mancha. `Black's` saía `Black,s`.

## Medido em 2026-08-24

Em 13 páginas de 4 livros de camada editorada, sobre 355 marcas finas casadas com a camada:

    marca             n     topo do box, em alturas de linha
    alta (' ’ ” )    13     p10 0,00   mediana 0,03   p90 0,03
    baixa (, . ; :) 342     p10 0,79   mediana 0,85   p90 0,87

**Não há sobreposição**, e um corte em 0,30 separa 99,2%.

## O teto deste conserto é baixo, e é honesto dizer por quê

**O modelo não tem as aspas curvas.** `’`, `‘`, `“` e `”` não são classes -- só existem o
apóstrofo reto `'` e as aspas retas `"`. Dos 28 erros de marca fina medidos, **13 são de classe
ausente**: não há resposta que o decodificador pudesse dar. Este módulo escreve `'`, que é o certo
para se **ler**, e continua contando como erro contra uma camada que escreveu `’`.

Por isso o ganho de CER é da ordem de **0,001 -- dentro do ruído**, e quem quiser julgar este item
pelo CER vai concluir que ele não fez nada. Ele existe pela legibilidade: `Black,s` está errado de
um jeito que salta aos olhos, e `Black's` não. O número que importa aqui é 12 palavras consertadas
em 13 páginas, e não o quarto decimal do CER.

## Só a direção que foi medida

Marca baixa lida no alto vira apóstrofo. O inverso -- apóstrofo lido na base -- **não** entra: são
2 casos na medição, e escolher entre `,` e `.` para eles seria uma regra inventada sobre dado que
não existe.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

ALTA = "'"
"""O que o modelo tem para marca alta. Ver "O teto deste conserto" no cabeçalho."""

BAIXAS = ",.;:"
"""As marcas que assentam na base, e que este módulo pode promover a apóstrofo."""

ALTURA_MAXIMA = 0.50
"""Acima desta fração da altura da linha, o box não é marca de pontuação: é letra.

**Esta guarda nasceu de dois falsos positivos, e eles ensinam mais que o acerto.** Sem ela,
`Qualquer` saía `Qua'quer` e `Lviv` saía `Lvl'v`: um `l` e um `i` que o classificador **já** estava
lendo como vírgula, e que a regra de posição então promovia a apóstrofo -- letra alta começa no
topo da linha, como o apóstrofo. A promoção não criava o erro, ela só trocava qual caractere
errado aparecia; mas trocar um erro por outro erro é trabalho sem ganho, e um `'` no meio de uma
palavra é mais desconcertante que uma vírgula.

Medido nas mesmas 13 páginas: a marca de verdade vai até **0,35** da altura da linha, e a letra
lida como marca mede **0,97**. O teto fica em 0,50, no meio do vão. **O lado da exclusão está
medido em poucos casos** -- é raro o classificador ler uma letra alta como vírgula --, e é aí que
este número pode precisar de revisão."""

CORTE_NA_LINHA = 0.30
"""Abaixo desta fração da altura da linha, a marca é alta. Medido: separa 99,2% de 355 casos.

O corte fica no meio do vão -- as altas terminam em 0,03 e as baixas começam em 0,79 --, e não
colado numa das pontas. O vão é largo porque a diferença é de **posição**, e posição na linha é a
coisa mais estável que uma marca de pontuação tem."""


def referencia_da_linha(caixas: Sequence[object]) -> tuple[float, float]:
    """`(topo, base)` da linha, em pixels da página. `(0, 0)` sem caixas.

    O **topo** é o menor `y1`, dominado por maiúscula e ascendente. A **base** é a mediana dos
    `y2`, e mediana e não máximo é o item: um `g` ou um `p` descem abaixo da linha de base, e o
    máximo os tomaria por ela -- toda marca pareceria mais alta do que é.
    """
    if not caixas:
        return (0.0, 0.0)
    topo = float(min(c.y1 for c in caixas))  # type: ignore[attr-defined]
    base = float(np.median([c.y2 for c in caixas]))  # type: ignore[attr-defined]
    return (topo, base)


def posicao_na_linha(y1: float, topo: float, base: float) -> float:
    """Onde o topo do box cai, em alturas de linha: `0.0` colado no topo, `1.0` na base.

    `-1.0` quando a linha não tem altura -- e o valor negativo é deliberado, para que nenhuma
    comparação com o corte dispare por acidente numa linha degenerada.
    """
    altura = base - topo
    if altura <= 0:
        return -1.0
    return (y1 - topo) / altura


def e_marca_alta(
    y1: float,
    topo: float,
    base: float,
    *,
    altura: float | None = None,
    corte: float | None = None,
    teto: float | None = None,
) -> bool:
    """Esta é uma marca de pontuação que mora no alto da linha?

    **Duas condições, e as duas foram medidas**: o topo do box no alto (`corte`) e o box *pequeno*
    (`teto`). A segunda existe porque letra alta também começa no topo -- ver `ALTURA_MAXIMA`.
    `altura=None` dispensa a segunda, e é o caminho de quem já sabe que o box é marca.

    `corte=None` e `teto=None` leem as constantes **na hora da chamada**, e não na definição -- a
    mesma lição que `caixa_alta.caixa_pela_altura` registra: um limiar amarrado na assinatura faz
    varredura nenhuma variar.
    """
    p = posicao_na_linha(y1, topo, base)
    if p < 0 or p >= (CORTE_NA_LINHA if corte is None else corte):
        return False
    if altura is None:
        return True
    linha = base - topo
    return linha > 0 and altura / linha <= (ALTURA_MAXIMA if teto is None else teto)


def corrigir(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[object],
    idx_to_char: dict[int, str],
    *,
    corte: float | None = None,
) -> list[tuple[str, float]]:
    """Promove a apóstrofo a marca baixa que está no alto da linha. Devolve `(char, confiança)`.

    Roda **depois** de `caixa_alta.decidir`, sobre o que ele já escolheu: as duas correções olham
    geometrias diferentes -- tamanho e posição -- e nenhum box é das duas famílias ao mesmo tempo.

    A confiança devolvida é a da classe do apóstrofo, e não a da vírgula recusada. É a mesma regra
    do módulo irmão: trocar o caractere e manter a confiança do palpite descartado diria que o
    programa tem certeza de algo sobre o que acabou de mudar de ideia.

    Sem a classe `'` no modelo, devolve a entrada intacta -- não há para onde promover.
    """
    if not lidos:
        return []
    indice = next((i for i, c in idx_to_char.items() if c == ALTA), None)
    if indice is None:
        return list(lidos)

    topo, base = referencia_da_linha(caixas)
    saida: list[tuple[str, float]] = []
    for k, (char, confianca) in enumerate(lidos):
        if char in BAIXAS and k < len(caixas):
            caixa = caixas[k]
            y1 = float(caixa.y1)  # type: ignore[attr-defined]
            altura = float(caixa.altura)  # type: ignore[attr-defined]
            if e_marca_alta(y1, topo, base, altura=altura, corte=corte):
                nova = float(probs[k, indice]) if k < probs.shape[0] else confianca
                saida.append((ALTA, nova))
                continue
        saida.append((char, confianca))
    return saida


__all__ = [
    "ALTA",
    "ALTURA_MAXIMA",
    "BAIXAS",
    "CORTE_NA_LINHA",
    "corrigir",
    "e_marca_alta",
    "posicao_na_linha",
    "referencia_da_linha",
]
