"""Calibração de confiança por temperature scaling (S-28).

**O problema em uma frase:** o modelo acerta com confiança 0,9998 e erra com confiança
0,8855 (medido no split de teste). A separação existe -- é o que faz a fila de revisão da
S-22 funcionar --, mas a escala não é uma probabilidade: "confiança 0,88" não quer dizer
88% de chance de acerto. E os dois limiares do produto (`ACCEPT_MIN_CONFIDENCE` da S-15 e
`UNCERTAIN_SQUARE_THRESHOLD` da S-10) foram escolhidos olhando a distribuição, não a
curva. São palpites informados, e estão documentados como tal desde a Fase 2.

**A solução é um número só.** Aprender um escalar `T` no conjunto de **validação**
minimizando a NLL de `softmax(logits / T)`. `T > 1` achata a distribuição (o modelo era
confiante demais), `T < 1` a agudiza. Um único parâmetro não consegue reordenar nada: o
argmax por casa é rigorosamente o mesmo antes e depois, e portanto a acurácia também.
O que muda é só a escala -- que é exatamente o que se quer mudar.

**Por que no `val` e não no `test`.** Ajustar `T` no teste e reportar o ECE do teste
mediria o ajuste, não a calibração. O `val` é o conjunto que o treino já usa para
decidir, então usá-lo aqui não gasta nada de novo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)


def fit_temperature(
    logits: torch.Tensor,
    targets: torch.Tensor,
    *,
    max_iter: int = 100,
    initial: float = 1.0,
) -> float:
    """Ajusta a temperatura por LBFGS sobre a NLL. Devolve `T > 0`.

    Otimiza `log T` em vez de `T` para dispensar restrição de positividade: um passo do
    LBFGS que levasse `T` a zero produziria `inf` na divisão, e um `T` negativo inverteria
    a ordem das classes -- os dois são estados dos quais a otimização não volta.
    """
    if logits.ndim != 2:
        raise ValueError(f"Esperados logits (N, C); recebido {tuple(logits.shape)}.")
    if logits.shape[0] != targets.shape[0]:
        raise ValueError(f"{logits.shape[0]} logits para {targets.shape[0]} rótulos.")
    if logits.shape[0] == 0:
        raise ValueError("Sem amostras para calibrar. Verifique se o split de validação não está vazio.")

    logits = logits.detach().to(torch.float32)
    targets = targets.detach().to(torch.long)

    log_temperature = torch.tensor([float(np.log(initial))], requires_grad=True)
    optimizer = torch.optim.LBFGS([log_temperature], lr=0.1, max_iter=max_iter)

    def closure() -> torch.Tensor:
        optimizer.zero_grad()
        loss = F.cross_entropy(logits / log_temperature.exp(), targets)
        loss.backward()
        return loss

    optimizer.step(closure)  # type: ignore[arg-type]

    temperature = float(log_temperature.exp().item())
    if not np.isfinite(temperature) or temperature <= 0:
        logger.warning("Calibração divergiu (T=%r); mantendo T=1,0 (sem calibração).", temperature)
        return 1.0
    return temperature


def negative_log_likelihood(logits: torch.Tensor, targets: torch.Tensor, temperature: float = 1.0) -> float:
    with torch.no_grad():
        return float(F.cross_entropy(logits.to(torch.float32) / temperature, targets.to(torch.long)).item())


@dataclass(frozen=True)
class ReliabilityBin:
    low: float
    high: float
    count: int
    mean_confidence: float
    accuracy: float

    @property
    def gap(self) -> float:
        """Confiança declarada menos acerto observado. Positivo = confiante demais."""
        return self.mean_confidence - self.accuracy


def reliability_table(confidences: np.ndarray, correct: np.ndarray, *, bins: int = 10) -> list[ReliabilityBin]:
    """Curva de calibração: por faixa de confiança, quanto o modelo de fato acerta."""
    confidences = np.asarray(confidences, dtype=np.float64)
    correct = np.asarray(correct, dtype=np.float64)
    if confidences.shape != correct.shape:
        raise ValueError(f"{confidences.shape} confianças para {correct.shape} acertos.")

    edges = np.linspace(0.0, 1.0, bins + 1)
    table: list[ReliabilityBin] = []
    for low, high in zip(edges[:-1], edges[1:], strict=True):
        # Intervalo (low, high], com a primeira faixa fechada a esquerda para nao perder
        # a confianca exatamente 0 -- que existe quando o softmax satura.
        mask = (confidences > low) & (confidences <= high) if low > 0 else (confidences >= low) & (confidences <= high)
        if not mask.any():
            continue
        table.append(
            ReliabilityBin(
                low=float(low),
                high=float(high),
                count=int(mask.sum()),
                mean_confidence=float(confidences[mask].mean()),
                accuracy=float(correct[mask].mean()),
            )
        )
    return table


def expected_calibration_error(confidences: np.ndarray, correct: np.ndarray, *, bins: int = 10) -> float:
    """ECE: diferença média (ponderada pela contagem) entre confiança e acerto.

    0 significa que "confiança 0,9" corresponde de fato a 90% de acerto.
    """
    confidences = np.asarray(confidences, dtype=np.float64)
    if confidences.size == 0:
        return 0.0
    total = float(confidences.size)
    return float(
        sum(faixa.count / total * abs(faixa.gap) for faixa in reliability_table(confidences, correct, bins=bins))
    )


def confidence_for_accuracy(
    confidences: np.ndarray,
    correct: np.ndarray,
    target_accuracy: float,
    *,
    bins: int = 20,
) -> float | None:
    """Menor limiar de confiança cuja precisão observada acima dele atinge `target_accuracy`.

    É isto que a S-28 quer dizer com "limiares derivados da curva de calibração": em vez
    de escolher 0,80 porque a distribuição parecia sugerir, perguntar a que confiança
    aceitar produz de fato a taxa de acerto que se está disposto a aceitar.

    Devolve `None` quando nenhum limiar atinge o alvo -- resposta honesta e diferente de
    devolver 1,0, que faria o chamador achar que existe um ponto de corte.
    """
    confidences = np.asarray(confidences, dtype=np.float64)
    correct = np.asarray(correct, dtype=np.float64)
    if confidences.size == 0:
        return None

    for threshold in np.linspace(0.0, 1.0, bins + 1):
        mask = confidences >= threshold
        if not mask.any():
            break
        if correct[mask].mean() >= target_accuracy:
            return float(threshold)
    return None
