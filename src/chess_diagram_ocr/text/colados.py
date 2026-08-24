"""Dois caracteres num contorno só, e o árbitro que confirma o corte (S-186).

**Este item chega com uma suspeita contra si mesmo, e ela é do projeto de origem.** Lá foram
medidos 231 caracteres colados na horizontal em 10 páginas rotuladas — e, depois que as classes
de **ligadura** entraram no modelo, a vantagem do separador caiu de +0,3 para +0,1 de F1, e os
cortes bons de 23 para 13. O modelo tem `ligature_fi`, `ligature_e4`, `ligature_xf6`: pares que
ele lê inteiros, e que o separador não precisa cortar.

Ou seja: **o separador é candidato legítimo a ficar desligado**, e o item existe para medir isso
aqui antes de decidir — não para portar e ligar.

## A regra que sustenta o desenho, e ela é a mais cara do projeto de origem

**Separar glifo colado sem classificador que confirme custou lá 2,3 pontos de F1.** A geometria
propõe o corte; o classificador dispõe, comparando a confiança média dos dois pedaços contra a do
inteiro. É a mesma regra da S-197 (o ângulo) e da S-198 (o box de duas linhas), e é a mesma
frase: **sem árbitro, não mexer.**

## O corte é vertical, e o vale é de coluna

O gêmeo deste módulo, `duas_linhas`, procura o vale no perfil **horizontal** de tinta: duas linhas
de texto empilhadas. Aqui é o perfil **vertical**: dois caracteres lado a lado, e o vale é a
coluna de menos tinta entre eles. As pontas ficam de fora pela mesma razão — o mínimo colado na
borda é o fim do próprio glifo, e cortar ali produz um pedaço vazio.

## Três modos, e o padrão sai da medição

`auto` pergunta ao árbitro, `sempre` corta onde houver vale, `nunca` não toca em nada. O padrão é
`nunca` **até a tabela dizer o contrário** — que é o oposto de herdar o padrão de lá.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

import numpy as np

from .boxes import Caixa

logger = logging.getLogger(__name__)

AUTO, SEMPRE, NUNCA = "auto", "sempre", "nunca"
MODOS = (AUTO, SEMPRE, NUNCA)

PADRAO = NUNCA
"""**O padrão sai da medição desta entrega, e não de herança.** Ver a tabela na spec da S-186."""

LARGURA_SUSPEITA = 1.35
"""Acima de quantas escalas de caractere a caixa é candidata a ter dois glifos.

Menos exigente que o `ALTURA_SUSPEITA` de 1,6 da S-198, e por um motivo de forma: caractere é
mais alto que largo, então duas letras lado a lado passam de 1,35 escalas de largura antes de
uma letra sozinha chegar lá. `m` e `w` são a exceção que o árbitro recusa."""

MARGEM_DO_VALE = 0.25
"""Fração de cada ponta que fica fora da busca. O mínimo colado na borda é o fim do glifo."""

GANHO_MINIMO = 0.05
"""Quanto a confiança média dos dois pedaços tem de superar a do inteiro.

**É uma probabilidade, e por isso não atravessa uma calibração** — a mesma regra da S-198. Se a
temperatura do modelo mudar, este limiar precisa ser remedido."""


def _perfil_vertical(binaria: np.ndarray, caixa: Caixa) -> np.ndarray:
    """Tinta por coluna do recorte. É onde o vale entre dois caracteres colados aparece."""
    recorte = caixa.recortar(binaria)
    if recorte.size == 0:
        return np.zeros(0, dtype=np.float64)
    return (recorte > 0).mean(axis=0)


def vale(binaria: np.ndarray, caixa: Caixa) -> int | None:
    """A coluna com menos tinta, em coordenadas da página. `None` quando não há vale.

    Ignora as pontas (`MARGEM_DO_VALE`) e exige que o mínimo esteja **abaixo da média** do
    perfil: sem isso, uma letra sozinha de traço uniforme produziria um "vale" em qualquer lugar.
    """
    perfil = _perfil_vertical(binaria, caixa)
    if perfil.size < 3:
        return None

    margem = max(1, int(len(perfil) * MARGEM_DO_VALE))
    miolo = perfil[margem : len(perfil) - margem]
    if miolo.size == 0:
        return None
    if float(miolo.min()) >= float(perfil.mean()):
        return None
    return caixa.x1 + margem + int(miolo.argmin())


def partir(
    caixa: Caixa,
    corte: int,
    *,
    arbitro: Callable[[Sequence[Caixa]], float] | None = None,
    modo: str = AUTO,
) -> list[Caixa]:
    """A caixa partida em duas no `corte`, ou intacta quando o árbitro não confirma.

    **Sem árbitro não corta**, e no modo `auto` isso não é cautela: separar sem confirmação custou
    2,3 pontos de F1 no projeto de origem. O modo `sempre` existe para a tabela ter a linha que
    mostra o preço de ignorar o árbitro — não para ser usado.
    """
    if modo == NUNCA:
        return [caixa]
    if corte <= caixa.x1 or corte >= caixa.x2:
        return [caixa]

    esquerda = Caixa(caixa.x1, caixa.y1, corte, caixa.y2, caixa.angulo)
    direita = Caixa(corte, caixa.y1, caixa.x2, caixa.y2, caixa.angulo)
    if modo == SEMPRE:
        return [esquerda, direita]
    if arbitro is None:
        return [caixa]

    inteiro = arbitro([caixa])
    partido = arbitro([esquerda, direita])
    return [esquerda, direita] if partido > inteiro + GANHO_MINIMO else [caixa]


def separar(
    binaria: np.ndarray,
    caixas: Sequence[Caixa],
    *,
    escala: int,
    arbitro: Callable[[Sequence[Caixa]], float] | None = None,
    modo: str = PADRAO,
) -> list[Caixa]:
    """As caixas com as coladas partidas, na ordem de leitura da esquerda para a direita.

    **A ligadura conhecida sobrevive por si**, e é o mecanismo que torna este item pequeno: se o
    modelo lê `fi` inteiro com confiança alta, os dois pedaços não superam o inteiro por
    `GANHO_MINIMO`, e o árbitro recusa o corte sem que ninguém precise listar ligaduras.
    """
    if modo not in MODOS:
        raise ValueError(f"modo desconhecido: {modo!r}. Use {', '.join(MODOS)}.")
    if modo == NUNCA or escala <= 0:
        return list(caixas)

    piso = LARGURA_SUSPEITA * escala
    saida: list[Caixa] = []
    for caixa in caixas:
        if caixa.largura < piso:
            saida.append(caixa)
            continue
        corte = vale(binaria, caixa)
        if corte is None:
            saida.append(caixa)
            continue
        saida.extend(partir(caixa, corte, arbitro=arbitro, modo=modo))
    return saida


__all__ = [
    "AUTO",
    "GANHO_MINIMO",
    "LARGURA_SUSPEITA",
    "MODOS",
    "NUNCA",
    "PADRAO",
    "SEMPRE",
    "partir",
    "separar",
    "vale",
]
