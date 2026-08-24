"""A temperatura, e a curva que diz se ela serviu (S-205).

**O defeito que este item existe para impedir é de processo, não de fórmula.** Medido na F25 do
projeto de origem: **o retreino apaga a calibração e ninguém nota**, porque o metadado continua
trazendo o número antigo -- que passa a descrever outro modelo. Aqui a temperatura é ajustada
dentro de `treinar`, com os pesos da **melhor** época, e `gravar_checkpoint` grava as duas coisas
de uma vez. Não existe caminho que produza pesos sem temperatura.

## Por que a confiança deste classificador importa mais que o normal

Ela decide quatro coisas, e um modelo mal calibrado desregula as quatro de uma vez:

- o corte de legenda adivinhada (S-181, `MIN_CONFIDENCE`);
- o árbitro do glifo colado e do box de duas linhas (S-186, S-198);
- o ângulo da pilha de texto girado (S-197);
- a ordem da fila de revisão de caractere (S-212).

Um modelo a 0,99 de confiança crua sobre um `'` que ele acerta 57% das vezes não erra só o `'`:
ele erra os quatro julgamentos que perguntam "quanto isto vale?".

## O número que faltava, e por que a temperatura sozinha não bastava

A temperatura é **um** parâmetro, e ela diz a direção -- acima de 1 o modelo era otimista. O que
ela não diz é **quanto sobrou**: um modelo pode ficar bem calibrado na média e continuar péssimo
na faixa alta, que é justamente a faixa que os quatro julgamentos acima consultam. Quem responde
isso é a curva de confiabilidade e o erro esperado de calibração (ECE), medidos **antes e
depois** -- e é isso que a S-205 devia.

## A régua: como o ECE é somado aqui

As amostras vão para faixas de confiança de largura igual. Em cada faixa comparam-se duas coisas
que deveriam ser iguais num modelo calibrado: a **confiança média** que ele reportou e o
**acerto** que ele teve. O ECE é a média dessas diferenças, ponderada pelo tamanho da faixa:

    ECE = Σ (n_faixa / n) × | acerto_faixa − confiança_faixa |

**Faixa vazia não entra na conta**, e faixas de largura igual (e não de população igual) são a
escolha deliberada: a leitura que interessa é "quando ele diz 0,9, ele acerta 0,9?", e para
responder isso a faixa tem de ser definida pela confiança, não pela contagem.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

FAIXAS_PADRAO = 15
"""Faixas da curva de confiabilidade.

Quinze e não dez: a massa deste classificador fica toda acima de 0,9, e com dez faixas metade das
amostras cai numa só -- a faixa que decide vira uma média sobre tudo que interessa. Mais que
quinze começa a produzir faixa vazia no meio, que não soma no ECE mas polui a curva."""


@dataclass(frozen=True)
class Faixa:
    """Uma faixa da curva. `acerto` acima de `confianca` é modelo pessimista, e vice-versa."""

    de: float
    ate: float
    amostras: int
    confianca: float
    acerto: float

    @property
    def desvio(self) -> float:
        """O que o ECE soma nesta faixa, antes de ponderar pelo tamanho dela."""
        return abs(self.acerto - self.confianca)

    def como_dicionario(self) -> dict[str, Any]:
        return {
            "de": round(self.de, 4),
            "ate": round(self.ate, 4),
            "amostras": self.amostras,
            "confianca": self.confianca,
            "acerto": self.acerto,
        }


def probabilidades(logits: np.ndarray, temperatura: float = 1.0) -> np.ndarray:
    """`softmax(logits / T)`, estável. `T <= 0` é recusado em vez de virar `nan` em silêncio."""
    if temperatura <= 0.0:
        raise ValueError(f"temperatura tem de ser positiva, e veio {temperatura!r}")
    if logits.size == 0:
        return np.empty((0, 0), dtype=np.float64)
    z = np.asarray(logits, dtype=np.float64) / temperatura
    z -= z.max(axis=1, keepdims=True)
    exp = np.exp(z)
    return exp / exp.sum(axis=1, keepdims=True)


def calibrar(logits: np.ndarray, verdade: np.ndarray) -> float:
    """A temperatura que minimiza a NLL na validação.

    Busca em grade log-espaçada e depois refina -- e não LBFGS -- porque o problema é escalar,
    convexo e barato, e uma grade não tem estado escondido que possa divergir em silêncio.

    **Conjunto vazio devolve 1,0 em vez de levantar.** Calibrar sem dado não é erro de quem
    chama: é o caso de um split que não deixou validação, e quem trata isso é o treino, com uma
    mensagem que diz o que fazer.
    """
    if logits.size == 0:
        return 1.0

    def nll(temperatura: float) -> float:
        z = np.asarray(logits, dtype=np.float64) / temperatura
        z = z - z.max(axis=1, keepdims=True)
        log_soma = np.log(np.exp(z).sum(axis=1))
        return float((log_soma - z[np.arange(z.shape[0]), verdade]).mean())

    melhor, melhor_perda = 1.0, nll(1.0)
    for temperatura in np.geomspace(0.05, 20.0, 120):
        perda = nll(float(temperatura))
        if perda < melhor_perda:
            melhor, melhor_perda = float(temperatura), perda
    passo = melhor * 0.05
    for _ in range(40):
        for candidato in (melhor - passo, melhor + passo):
            if candidato <= 0.01:
                continue
            perda = nll(candidato)
            if perda < melhor_perda:
                melhor, melhor_perda = candidato, perda
        passo *= 0.7
    return float(melhor)


def curva(
    logits: np.ndarray,
    verdade: np.ndarray,
    *,
    temperatura: float = 1.0,
    faixas: int = FAIXAS_PADRAO,
) -> list[Faixa]:
    """A curva de confiabilidade: por faixa de confiança, o que ele disse e o que ele acertou.

    Só a classe **vencedora** entra, que é a confiança que o programa de fato consulta -- as
    outras 313 não são reportadas a ninguém.
    """
    if logits.size == 0:
        return []

    probs = probabilidades(logits, temperatura)
    confianca = probs.max(axis=1)
    acertou = probs.argmax(axis=1) == verdade

    bordas = np.linspace(0.0, 1.0, faixas + 1)
    saida: list[Faixa] = []
    for i in range(faixas):
        # A última faixa é fechada dos dois lados: a confiança 1,0 exata acontece, e deixá-la
        # fora tiraria da conta justamente as amostras de que o programa mais depende.
        dentro = (confianca >= bordas[i]) & (
            confianca <= bordas[i + 1] if i == faixas - 1 else confianca < bordas[i + 1]
        )
        n = int(dentro.sum())
        if n == 0:
            continue
        saida.append(
            Faixa(
                de=float(bordas[i]),
                ate=float(bordas[i + 1]),
                amostras=n,
                confianca=float(confianca[dentro].mean()),
                acerto=float(acertou[dentro].mean()),
            )
        )
    return saida


def curva_de_confianca(
    confiancas: Sequence[float], acertos: Sequence[bool], *, faixas: int = FAIXAS_PADRAO
) -> list[Faixa]:
    """A mesma curva, para quem já tem `(confiança, acertou?)` e não logits.

    **É o que a S-189 precisa.** A confiança de lá não sai de um softmax: ela sai da concordância
    entre duas leituras -- a maior quando concordam, a menor quando divergem --, e a pergunta
    continua sendo a mesma: quando ele diz 0,9, ele acerta 0,9?
    """
    if not confiancas:
        return []
    conf = np.asarray(confiancas, dtype=np.float64)
    certo = np.asarray(acertos, dtype=bool)
    bordas = np.linspace(0.0, 1.0, faixas + 1)
    saida: list[Faixa] = []
    for i in range(faixas):
        dentro = (conf >= bordas[i]) & (
            conf <= bordas[i + 1] if i == faixas - 1 else conf < bordas[i + 1]
        )
        n = int(dentro.sum())
        if n == 0:
            continue
        saida.append(
            Faixa(
                de=float(bordas[i]),
                ate=float(bordas[i + 1]),
                amostras=n,
                confianca=float(conf[dentro].mean()),
                acerto=float(certo[dentro].mean()),
            )
        )
    return saida


def ece_da_curva(linhas: Sequence[Faixa]) -> tuple[float, float]:
    """`(ECE ponderado, ECE por faixa)` de uma curva já montada. Ver os dois no cabeçalho."""
    total = sum(f.amostras for f in linhas)
    if not linhas or total == 0:
        return 0.0, 0.0
    ponderado = sum(f.amostras * f.desvio for f in linhas) / total
    por_faixa = sum(f.desvio for f in linhas) / len(linhas)
    return float(ponderado), float(por_faixa)


def ece(
    logits: np.ndarray,
    verdade: np.ndarray,
    *,
    temperatura: float = 1.0,
    faixas: int = FAIXAS_PADRAO,
) -> float:
    """O erro esperado de calibração. `0,0` é o modelo que diz 0,9 e acerta 0,9.

    Ver a régua no cabeçalho. Sem amostra devolve `0,0`, que é o único valor que não inventa.
    """
    linhas = curva(logits, verdade, temperatura=temperatura, faixas=faixas)
    total = sum(faixa.amostras for faixa in linhas)
    if total == 0:
        return 0.0
    return float(sum(faixa.amostras * faixa.desvio for faixa in linhas) / total)


def ece_por_faixa(
    logits: np.ndarray,
    verdade: np.ndarray,
    *,
    temperatura: float = 1.0,
    faixas: int = FAIXAS_PADRAO,
) -> float:
    """O ECE com **toda faixa valendo o mesmo**, e é ele que decide.

    **É a mesma lição que a `metrica_que_decide` aplica ao acerto, aqui aplicada à calibração.**
    O ECE ponderado é a média das faixas pelo tamanho delas, e nesta base 96% das amostras caem
    numa faixa só -- a de 0,93 a 1,00, onde o modelo é quase perfeito. O número ponderado
    portanto **mede aquela faixa e mais nada**, e sai lisonjeiro por construção.

    E a faixa que ele esconde é justamente a que o programa consulta: o corte de legenda
    adivinhada da S-42 está em 0,30, e os árbitros da S-186 e da S-197 comparam confianças no
    meio da escala. Publicar só o ponderado diria "calibrado" sobre a região onde nenhuma decisão
    acontece.
    """
    linhas = curva(logits, verdade, temperatura=temperatura, faixas=faixas)
    if not linhas:
        return 0.0
    return float(sum(faixa.desvio for faixa in linhas) / len(linhas))


def esperanca_de_confianca(temperatura: float) -> str:
    """Uma frase sobre o que a temperatura achada diz. Para o relatório, não para decidir."""
    if math.isclose(temperatura, 1.0, rel_tol=0.02):
        return "o modelo já saiu calibrado: a temperatura ficou em 1,0"
    if temperatura > 1.0:
        return f"o modelo era otimista: a temperatura {temperatura:.4f} **reduz** a confiança que ele reporta"
    return f"o modelo era pessimista: a temperatura {temperatura:.4f} **aumenta** a confiança que ele reporta"


def leitura(
    temperatura: float,
    antes: float,
    depois: float,
    *,
    ponderado: tuple[float, float] | None = None,
) -> str:
    """A frase acima, mais o que a curva mostrou. Para o relatório, não para decidir.

    `antes` e `depois` são o ECE **por faixa**, que é o que decide; o ponderado entra ao lado,
    nomeado como o que ele é. Publicar só o ponderado nesta base diria "calibrado" sobre a única
    faixa em que nada é decidido.
    """
    frase = "o modelo já saiu calibrado: a temperatura ficou em 1,0 e a curva não se mexeu"
    if not math.isclose(temperatura, 1.0, rel_tol=0.02):
        verbo = "caiu" if depois <= antes else "**subiu**"
        frase = (
            f"{esperanca_de_confianca(temperatura)}, e o ECE por faixa {verbo} de "
            f"{antes:.4f} para {depois:.4f}"
        )
        if depois > antes:
            # **Piorar é um resultado, e ele tem de aparecer.** A temperatura minimiza a NLL, e
            # não o ECE: as duas quase sempre andam juntas, e quando não andam quem lê precisa
            # saber que a régua otimizada não foi esta.
            frase += " -- ela minimiza a NLL, não o ECE"
    if ponderado is not None:
        frase += (
            f". O ECE ponderado, que a faixa mais cheia domina, foi de {ponderado[0]:.4f} para "
            f"{ponderado[1]:.4f}"
        )
    return frase


def relatorio(
    logits: np.ndarray,
    verdade: np.ndarray,
    temperatura: float,
    *,
    faixas: int = FAIXAS_PADRAO,
) -> dict[str, Any]:
    """A curva e o ECE **antes e depois**, que é o que a S-205 devia.

    Antes é a temperatura 1,0 -- o modelo cru, como ele sairia se ninguém calibrasse. Depois é a
    temperatura achada. Publicar só a segunda diria que o modelo é bom sem dizer o que a
    calibração fez por ele.
    """
    antes = ece(logits, verdade, temperatura=1.0, faixas=faixas)
    depois = ece(logits, verdade, temperatura=temperatura, faixas=faixas)
    antes_por_faixa = ece_por_faixa(logits, verdade, temperatura=1.0, faixas=faixas)
    depois_por_faixa = ece_por_faixa(logits, verdade, temperatura=temperatura, faixas=faixas)
    probs = probabilidades(logits, temperatura) if logits.size else np.empty((0, 0))
    return {
        "faixas": faixas,
        "amostras": int(verdade.size),
        "temperatura": float(temperatura),
        "leitura": leitura(
            temperatura, antes_por_faixa, depois_por_faixa, ponderado=(antes, depois)
        ),
        "antes": {
            "temperatura": 1.0,
            "ece": antes,
            "ece_por_faixa": antes_por_faixa,
            "curva": [f.como_dicionario() for f in curva(logits, verdade, faixas=faixas)],
        },
        "depois": {
            "temperatura": float(temperatura),
            "ece": depois,
            "ece_por_faixa": depois_por_faixa,
            "confianca_media": float(probs.max(axis=1).mean()) if probs.size else 0.0,
            "acerto": float((probs.argmax(axis=1) == verdade).mean()) if probs.size else 0.0,
            "curva": [
                f.como_dicionario()
                for f in curva(logits, verdade, temperatura=temperatura, faixas=faixas)
            ],
        },
    }


__all__ = [
    "FAIXAS_PADRAO",
    "Faixa",
    "calibrar",
    "curva",
    "curva_de_confianca",
    "ece",
    "ece_da_curva",
    "ece_por_faixa",
    "esperanca_de_confianca",
    "leitura",
    "probabilidades",
    "relatorio",
]
