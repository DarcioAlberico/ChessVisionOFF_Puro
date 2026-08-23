"""O treino do classificador de caracteres, e a calibração que tem de vir junto (S-204/S-205).

**A rede não é escolha deste módulo.** Ela é construída por `modelo._construir_rede`, que é a
mesma `SimpleCNN` que o carregador espera -- 1→32→64→128, densa 2048→256, `Dropout(0.5)`,
256→n. Treinar com outra forma produziria pesos que `carregar_classificador` recusa, e recusar é
o comportamento certo. Uma variante de arquitetura é trabalho de grade, e a grade muda os dois
lados de uma vez ou não muda nenhum.

**A métrica que salva a época está declarada, e não é a acurácia.** Nesta base, `lower_a` tem
63.055 recortes e 61 classes têm um só: um modelo que acerte todo `a` e erre todo `♗` mostra 97%
de acurácia e lê a notação errada. A época é salva pela **recall macro** sobre as classes com
pelo menos `MINIMO_PARA_MACRO` amostras em validação -- o corte existe porque a recall de uma
classe com duas amostras é 0%, 50% ou 100%, e média sobre isso é ruído. A acurácia micro é
calculada e registrada ao lado, explicitamente como a que lisonjeia.

**A calibração entra no fim do treino, ou não sobrevive a ele.** É a S-205, e o defeito que ela
existe para impedir é de processo, não de fórmula: o retreino apaga a calibração e ninguém nota,
porque o metadado continua trazendo o número antigo -- que passa a descrever outro modelo. Aqui
a temperatura é ajustada na validação **dentro** de `treinar`, e `gravar_checkpoint` grava as
duas coisas de uma vez. Não há caminho que produza pesos sem temperatura.

**A procedência de toda amostra desta base é `desconhecida`.** Os recortes não têm registro de
quem rotulou nem de que livro vieram (`dataset.py` explica), e a S-201 manda marcar em vez de
recusar. O checkpoint grava a contagem por procedência como ela é -- 100% desconhecida --, que é
o que permite a alguém, daqui a seis meses, ler o número final sabendo o que ele mede.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from ..atomic_io import atomic_write_text
from .classes import char_to_folder
from .dataset import Classe
from .modelo import LADO, _construir_rede, impressao_das_classes, impressao_do_arquivo

if TYPE_CHECKING:  # pragma: no cover
    import torch

logger = logging.getLogger(__name__)

MINIMO_PARA_MACRO = 5
"""Amostras em validação para uma classe entrar na métrica que decide.

Abaixo disso a recall só assume dois ou três valores, e a média sobre 115 classes assim mede o
sorteio do split e não o modelo. As classes de fora **continuam sendo treinadas** e continuam
aparecendo no relatório por classe -- elas só não votam em qual época é a melhor."""

EPOCAS_PADRAO = 20
LOTE_PADRAO = 256
TAXA_PADRAO = 1e-3
PACIENCIA_PADRAO = 10
"""O desenho do `cvoff-train` que já existe: semente fixa, parada antecipada pela métrica que
decide. O lote é 256 e não os 64 do projeto de origem porque aqui a base está em RAM e o gargalo
é a passada de CPU, não o disco.

**A paciência era 4, e 4 estava errado.** O `cvoff-train` deste projeto usa 15, e o motivo ficou
visível na terceira corrida de 2026-08-23: a recall macro oscila entre épocas consecutivas com
desvio de **0,0068**, e uma paciência de 4 dispara nesse ruído. A corrida parou na época 13 com a
macro **ainda subindo** (0,9632 na melhor, contra 0,9793 que a corrida anterior do mesmo recipe
alcançou na época 23). Uma parada antecipada tem de esperar mais que o ruído da métrica que a
governa, senão ela mede a sorte do sorteio e não a convergência."""


@dataclass
class Epoca:
    """Uma linha do histórico. `macro` é a que decide; `acuracia` é a que lisonjeia."""

    numero: int
    perda: float
    acuracia: float
    macro: float
    segundos: float


@dataclass
class Resultado:
    """O que o treino produziu, antes de virar arquivo."""

    estado: dict[str, Any]
    temperatura: float
    historico: list[Epoca] = field(default_factory=list)
    melhor: int = 0
    metricas: dict[str, Any] = field(default_factory=dict)


def _lotes(n: int, tamanho: int, aleatorio: np.random.Generator | None) -> list[np.ndarray]:
    ordem = aleatorio.permutation(n) if aleatorio is not None else np.arange(n)
    return [ordem[i : i + tamanho] for i in range(0, n, tamanho)]


def _para_tensor(X: np.ndarray, indices: np.ndarray, device: str) -> torch.Tensor:
    """`uint8 (n, 1024)` -> `float32 (n, 1, 32, 32)` em [0, 1].

    **É o mesmo pré-processamento de `ClassificadorDeGlifo._entrada`, e tem de continuar sendo.**
    Lá é `resize` + `/255`; o `resize` já aconteceu na varredura, e o que sobra é a divisão.
    """
    import torch

    bloco = X[indices].astype(np.float32) / 255.0
    return torch.from_numpy(bloco.reshape(-1, 1, LADO, LADO)).to(device)


def _avaliar(
    rede: Any, X: np.ndarray, y: np.ndarray, indices: np.ndarray, device: str, lote: int
) -> tuple[np.ndarray, np.ndarray]:
    """`(logits, verdade)` para o subconjunto. Sem gradiente."""
    import torch

    rede.eval()
    saidas: list[np.ndarray] = []
    with torch.no_grad():
        for pedaco in _lotes(indices.size, lote, None):
            entrada = _para_tensor(X, indices[pedaco], device)
            saidas.append(rede(entrada).cpu().numpy())
    return np.concatenate(saidas) if saidas else np.empty((0, 0), np.float32), y[indices]


def recall_por_classe(previsto: np.ndarray, verdade: np.ndarray, n_classes: int) -> np.ndarray:
    """`(n_classes,)` com a recall de cada classe, ou `nan` onde ela não aparece na verdade."""
    recalls = np.full(n_classes, np.nan, dtype=np.float64)
    for classe in np.unique(verdade):
        da_classe = verdade == classe
        recalls[classe] = float((previsto[da_classe] == classe).mean())
    return recalls


def metrica_que_decide(
    logits: np.ndarray, verdade: np.ndarray, n_classes: int, minimo: int = MINIMO_PARA_MACRO
) -> tuple[float, float]:
    """`(macro, acurácia)`. A macro ignora classe com menos de `minimo` amostras aqui.

    Devolve as duas juntas de propósito: quem registra uma sem a outra perde exatamente a
    comparação que o item pede para ficar visível.
    """
    if logits.size == 0:
        return 0.0, 0.0
    previsto = logits.argmax(axis=1)
    acuracia = float((previsto == verdade).mean())
    contagens = np.bincount(verdade, minlength=n_classes)
    recalls = recall_por_classe(previsto, verdade, n_classes)
    elegiveis = (contagens >= minimo) & ~np.isnan(recalls)
    macro = float(recalls[elegiveis].mean()) if elegiveis.any() else 0.0
    return macro, acuracia


def calibrar_temperatura(logits: np.ndarray, verdade: np.ndarray) -> float:
    """A temperatura que minimiza a NLL na validação (S-205).

    Busca em grade log-espaçada e depois refina -- e não LBFGS -- porque o problema é escalar,
    convexo e barato, e uma grade não tem estado escondido que possa divergir em silêncio.
    """
    if logits.size == 0:
        return 1.0

    def nll(temperatura: float) -> float:
        z = logits / temperatura
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


def treinar(
    X: np.ndarray,
    y: np.ndarray,
    treino: np.ndarray,
    validacao: np.ndarray,
    n_classes: int,
    *,
    epocas: int = EPOCAS_PADRAO,
    lote: int = LOTE_PADRAO,
    taxa: float = TAXA_PADRAO,
    paciencia: int = PACIENCIA_PADRAO,
    semente: int = 0,
    device: str = "cpu",
    pesos_de_classe: bool = False,
    callback: Callable[[Epoca], None] | None = None,
) -> Resultado:
    """Treina, escolhe a época pela métrica que decide, e calibra na validação antes de devolver.

    `treino` e `validacao` são **índices**, e não um vetor de lado, porque quem chama decide se
    val mede um recorte por grupo ou todos: nesta base 70,7% são cópia exata, e medir todos faz a
    métrica pesar pela contagem de cópias em vez do acerto. Ver `dataset.representantes`.

    `pesos_de_classe` é hipótese aberta e por isso é opção: a Fase 5 deste projeto mediu que
    pesos **não** ajudaram para peças, e ninguém mediu para caractere. O padrão é sem, que é o
    controle; ligá-lo produz o outro braço da comparação.
    """
    import torch
    import torch.nn as nn

    torch.manual_seed(semente)
    aleatorio = np.random.default_rng(semente)

    treino = np.asarray(treino)
    validacao = np.asarray(validacao)
    if treino.size == 0:
        raise ValueError("O split não deixou nada no treino.")
    if validacao.size == 0:
        raise ValueError(
            "O split não deixou nada em validação, e sem validação não há época que decida nem "
            "temperatura que calibre. Ver `dataset.split_por_grupo`."
        )

    rede = _construir_rede(n_classes).to(device)
    otimizador = torch.optim.Adam(rede.parameters(), lr=taxa)

    peso = None
    if pesos_de_classe:
        contagens = np.bincount(y[treino], minlength=n_classes).astype(np.float64)
        # Raiz e não inverso puro: com 63.055 contra 1, o inverso dá peso 63 mil a uma amostra e
        # o gradiente passa a ser essa amostra.
        bruto = np.where(contagens > 0, 1.0 / np.sqrt(np.maximum(contagens, 1.0)), 0.0)
        peso = torch.tensor(bruto / bruto[bruto > 0].mean(), dtype=torch.float32, device=device)
    criterio = nn.CrossEntropyLoss(weight=peso)

    resultado = Resultado(estado={}, temperatura=1.0)
    melhor_macro = -1.0
    sem_melhora = 0

    for numero in range(1, epocas + 1):
        import time

        comeco = time.perf_counter()
        rede.train()
        soma, vistos = 0.0, 0
        for pedaco in _lotes(treino.size, lote, aleatorio):
            indices = treino[pedaco]
            entrada = _para_tensor(X, indices, device)
            alvo = torch.from_numpy(y[indices].astype(np.int64)).to(device)
            otimizador.zero_grad(set_to_none=True)
            perda = criterio(rede(entrada), alvo)
            perda.backward()
            otimizador.step()
            soma += float(perda.item()) * indices.size
            vistos += indices.size

        logits, verdade = _avaliar(rede, X, y, validacao, device, lote)
        macro, acuracia = metrica_que_decide(logits, verdade, n_classes)
        epoca = Epoca(numero, soma / max(1, vistos), acuracia, macro, time.perf_counter() - comeco)
        resultado.historico.append(epoca)
        if callback is not None:
            callback(epoca)

        if macro > melhor_macro:
            melhor_macro = macro
            resultado.melhor = numero
            resultado.estado = {k: v.detach().cpu().clone() for k, v in rede.state_dict().items()}
            sem_melhora = 0
        else:
            sem_melhora += 1
            if paciencia and sem_melhora >= paciencia:
                logger.info("Parada antecipada: %d épocas sem melhorar a macro.", sem_melhora)
                break

    if not resultado.estado:  # pragma: no cover - só se `epocas` for 0
        resultado.estado = {k: v.detach().cpu().clone() for k, v in rede.state_dict().items()}

    # A calibração usa os pesos da **melhor** época, não os da última: é o par que vai para o
    # disco, e calibrar o outro é gravar a temperatura de um modelo que não existe.
    rede.load_state_dict(resultado.estado)
    logits, verdade = _avaliar(rede, X, y, validacao, device, lote)
    resultado.temperatura = calibrar_temperatura(logits, verdade)
    macro, acuracia = metrica_que_decide(logits, verdade, n_classes)
    resultado.metricas = {
        "val_macro": macro,
        "val_acuracia": acuracia,
        "val_amostras": int(validacao.size),
        "treino_amostras": int(treino.size),
        "epoca_escolhida": resultado.melhor,
    }
    return resultado


def avaliar_split(
    estado: dict[str, Any],
    X: np.ndarray,
    y: np.ndarray,
    indices: np.ndarray,
    n_classes: int,
    *,
    device: str = "cpu",
    lote: int = LOTE_PADRAO,
) -> tuple[dict[str, float], np.ndarray]:
    """`(métricas, recall por classe)` sobre os índices pedidos. O teste só é tocado no fim."""
    indices = np.asarray(indices)
    if indices.size == 0:
        return {"macro": 0.0, "acuracia": 0.0, "amostras": 0}, np.full(n_classes, np.nan)
    rede = _construir_rede(n_classes).to(device)
    rede.load_state_dict(estado)
    logits, verdade = _avaliar(rede, X, y, indices, device, lote)
    macro, acuracia = metrica_que_decide(logits, verdade, n_classes)
    recalls = recall_por_classe(logits.argmax(axis=1), verdade, n_classes)
    return {"macro": macro, "acuracia": acuracia, "amostras": int(indices.size)}, recalls


def gravar_checkpoint(
    resultado: Resultado,
    classes: list[Classe],
    caminho_pesos: Path,
    caminho_meta: Path,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grava `.pt` e `char_meta.json` **juntos**, e devolve o metadado.

    A ordem importa: os pesos primeiro, o hash deles depois, o metadado por último. Gravar o
    metadado antes deixaria, numa falha de disco no meio, um `char_meta.json` descrevendo um
    modelo que não existe -- e é exatamente o par descasado que `modelo.py` existe para impedir.
    """
    import torch

    caminho_pesos = Path(caminho_pesos)
    caminho_meta = Path(caminho_meta)
    caminho_pesos.parent.mkdir(parents=True, exist_ok=True)
    torch.save(resultado.estado, caminho_pesos)

    idx_to_char = {i: c.caractere for i, c in enumerate(classes)}
    for i, c in enumerate(classes):
        if char_to_folder(c.caractere) != c.pasta:  # pragma: no cover - `varrer` já barrou
            raise ValueError(f"classe {i} não fecha a ida-e-volta: {c.pasta} -> {c.caractere}")

    meta: dict[str, Any] = {
        "schema_version": 2,
        "label_map": {c.pasta: i for i, c in enumerate(classes)},
        "idx_to_char": {str(i): c for i, c in idx_to_char.items()},
        "num_classes": len(classes),
        "temperatura": resultado.temperatura,
        "modelo_sha256": impressao_do_arquivo(caminho_pesos),
        "classes_sha256": impressao_das_classes(idx_to_char),
        "treinado_em": datetime.now().replace(microsecond=0).isoformat(),
    }
    if extra:
        meta.update(extra)
    caminho_meta.parent.mkdir(parents=True, exist_ok=True)
    # `atomic_write_text` e nao `write_text`: um `char_meta.json` gravado pela metade e um par
    # descasado -- o metadado descrevendo um modelo que nao e o do lado --, que e o defeito que
    # `modelo.py` inteiro existe para impedir. Refazer custa uma corrida de treino.
    atomic_write_text(caminho_meta, json.dumps(meta, ensure_ascii=False))
    return meta


def esperanca_de_confianca(temperatura: float) -> str:
    """Uma frase sobre o que a temperatura achada diz. Para o relatório, não para decidir."""
    if math.isclose(temperatura, 1.0, rel_tol=0.02):
        return "o modelo já saiu calibrado: a temperatura ficou em 1,0"
    if temperatura > 1.0:
        return f"o modelo era otimista: a temperatura {temperatura:.4f} **reduz** a confiança que ele reporta"
    return f"o modelo era pessimista: a temperatura {temperatura:.4f} **aumenta** a confiança que ele reporta"


__all__ = [
    "EPOCAS_PADRAO",
    "LOTE_PADRAO",
    "MINIMO_PARA_MACRO",
    "PACIENCIA_PADRAO",
    "TAXA_PADRAO",
    "Epoca",
    "Resultado",
    "avaliar_split",
    "calibrar_temperatura",
    "esperanca_de_confianca",
    "gravar_checkpoint",
    "metrica_que_decide",
    "recall_por_classe",
    "treinar",
]
