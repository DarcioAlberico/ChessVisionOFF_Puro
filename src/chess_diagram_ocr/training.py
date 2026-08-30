"""Treino do classificador de peças.

O que a Fase 5 mudou aqui, e por quê:

- **A métrica de decisão deixou de ser `val_loss`.** O que interessa ao produto é
  `val_board_exact_acc` -- a fração de diagramas que sai sem nenhuma correção manual. A
  acurácia por casa, que era a única medida, é dominada pelos 77% de casas vazias: um
  modelo que só respondesse "vazio" marcaria 0,77 e pareceria razoável. Pior, `val_loss` e
  acurácia exata não sobem juntas no fim do treino, então a época salva não era a melhor.
- **Retomar deixou de zerar o controle de melhor época** (pendência aberta desde a Fase 1):
  a métrica da melhor época vai no checkpoint e é lida de volta.
- **`strict=False` virou `strict=True`.** Ver `checkpoint.check_compatible`.
- **O split vem do arquivo e a semente é registrada**, então "reproduza este número" passou
  a ser uma instrução executável.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import threading
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision.transforms import v2

from .audit import duplicate_groups_touching, read_label_rows
from .augment import DEFAULT_AUGMENT, AugmentConfig, build_augmentations
from .calibration import expected_calibration_error, fit_temperature, negative_log_likelihood
from .checkpoint import Checkpoint, check_compatible, git_commit, load_checkpoint, save_checkpoint
from .config import DEFAULT_BOARD_CACHE_SIZE, PIECE_CLASSES, VAL_BOARD_CACHE_SIZE
from .dataset import BoardFenDataset, BoardGroupedSampler, BoardUnitDataset, board_groups
from .fen_utils import labels_from_fen
from .labels import DatasetEntry, filenames_with_provenance, label_origins
from .model import DEFAULT_ARCH, ArchConfig, build_model, count_parameters
from .splits import Split, ensure_splits, groups_by_origin, load_splits, splits_hash

logger = logging.getLogger(__name__)

NUM_CLASSES = len(PIECE_CLASSES)
ClassWeighting = Literal["none", "balanced"]

DEFAULT_CLASS_WEIGHTS: ClassWeighting = "none"
"""Medido, não herdado da spec -- e o motivo não é o que se esperaria.

A S-27 propõe `"balanced"` por padrão, para o desbalanceamento de 77% de casas vazias
contra ~1% de dama. Medido no split de validação, 3 épocas, mesma semente
(docs/EXPERIMENTS.md):

| | `"none"` | `"balanced"` |
|---|---|---|
| exata por tabuleiro | 0,9673 | 0,9706 |
| **acurácia por casa** | **0,999183** | **0,997549** |
| **posições ilegais** | **0** | **1** |

A acurácia exata por tabuleiro fica **praticamente igual** (+0,0033 é um tabuleiro em 306,
dentro do ruído que o BASELINE.md descreve). O que muda de forma clara é o resto: as casas
erradas vão de ~16 para ~48 em 19.584, e é a única configuração da grade que produziu uma
posição ilegal.

O padrão de erro é o interessante: **três vezes mais casas erradas espalhadas por um número
igual de tabuleiros**, ou seja, o erro se concentrou em vez de aparecer em diagramas novos.
Isso é o que se espera de peso inverso à frequência -- ele compra recall de classe rara
vendendo precisão nas vazias, e uma dama inventada numa casa vazia é exatamente o tipo de
erro que viola contagem de peças e derruba a legalidade.

`"none"` continua o padrão porque paga menos por tabuleiro exato igual. O parâmetro fica
porque num dataset com classe genuinamente ausente do treino a conta pode virar.
"""


class TransformSubset(torch.utils.data.Dataset):
    def __init__(self, subset: Subset, transform: Callable | None = None):
        self.subset = subset
        self.transform = transform

    def __getitem__(self, idx: int):
        x, y = self.subset[idx]
        if self.transform is not None:
            x = self.transform(x)
        return x, y

    def __len__(self) -> int:
        return len(self.subset)


class ImageChannelsOnly(nn.Module):
    """Aplica o aumento só nos canais de imagem e recoloca os da S-62a intactos.

    O docstring de `with_coordinate_channels` diz que a coordenada roda **depois** do aumento
    porque `RandomAffine` translada e preenche a borda com zero: sobre um plano constante de
    0,71 isso produziria uma coordenada que varia dentro da casa e mente na margem. No
    caminho por tabuleiro a ordem sai de graça, porque quem chama `BoardFenDataset.square`
    entrega o aumento junto. No caminho por casa **não sai**: o `TransformSubset` roda depois
    do `__getitem__`, que já concatenou.

    O primeiro sintoma disso não foi uma coordenada errada -- foi o `ColorJitter` recusando
    `4` canais, o que é sorte: um aumento que aceitasse quatro teria treinado, e o defeito
    apareceria como um modelo pior sem nenhuma mensagem.

    `nn.Module` e não `lambda` pelo motivo de sempre: com `num_workers > 0` no Windows a
    pipeline inteira é pickleada para cada worker (ver `_clamp01`).
    """

    def __init__(self, inner: Callable, image_channels: int) -> None:
        super().__init__()
        self.inner = inner
        self.image_channels = image_channels

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[-3] <= self.image_channels:
            return self.inner(x)
        imagem = x[..., : self.image_channels, :, :]
        coordenadas = x[..., self.image_channels :, :, :]
        return torch.cat((self.inner(imagem), coordenadas), dim=-3)


def _clamp01(x: torch.Tensor) -> torch.Tensor:
    """Era uma `lambda` dentro do `v2.Compose`.

    Uma lambda não é picklável, e no Windows o `DataLoader` com `num_workers > 0` usa
    `spawn`: a pipeline de aumento inteira é pickleada para cada worker. Com a lambda,
    ligar o carregamento paralelo da S-26 falharia com `PicklingError` -- num ponto do
    código que não tem nada a ver com paralelismo.
    """
    return torch.clamp(x, 0.0, 1.0)


def _com_probabilidade(etapa: Any, p: float) -> Any | None:
    """A etapa envolvida em `RandomApply(p)` -- ou ela mesma, ou nada (S-376).

    **`p >= 1` devolve a etapa crua, e isso não é otimização.** `RandomApply.forward` sorteia
    um número antes de decidir, mesmo com `p=1,0`: envolver as duas etapas que hoje são
    incondicionais consumiria dois sorteios por casa e mudaria toda a sequência do RNG. O
    treino do padrão tem de sair **idêntico** ao de antes deste item, e sai: com
    `jitter=1,0` e `affine=1,0` a lista montada é a mesma, objeto por objeto.

    `p <= 0` devolve `None` pelo mesmo motivo, do outro lado: `RandomApply(p=0)` sortearia
    para descartar sempre.
    """
    if p >= 1.0:
        return etapa
    if p <= 0.0:
        return None
    return v2.RandomApply([etapa], p=p)


def build_train_transform(augment: AugmentConfig = DEFAULT_AUGMENT) -> Callable:
    """A pipeline de aumento. O padrão reproduz o treino anterior à S-40.

    As três primeiras etapas são o conjunto genérico de sempre. As dirigidas ao acervo
    (hachura, granulação, papel, inversão, espelhamento) entram depois delas e **desligadas
    por padrão**: ligar muda o modelo, e é a grade da S-40 que decide quais valem.

    A ordem coloca as dirigidas **depois** do afim de propósito. O afim reamostra, e
    reamostrar uma hachura sintética de período 6 px a borraria até sumir -- justamente a
    frequência que se quer ensinar.

    **As três genéricas são probabilidades, e duas delas não eram lidas (S-376).**
    `augment.jitter` e `augment.affine` existiam como campo, com valor documentado como
    probabilidade, e não chegavam a lugar nenhum: `ColorJitter` e `RandomAffine` estavam
    sempre na lista. `AugmentConfig(jitter=0.0)` -- que é como a grade de experimentos e
    qualquer chamada de `train_model` desligariam o jitter -- treinava com ele ligado, e o
    `augment_version` do checkpoint dizia a mesma coisa nos dois casos.
    """
    etapas: list[Any] = [
        _com_probabilidade(v2.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0)), augment.blur),
        _com_probabilidade(v2.ColorJitter(brightness=0.3, contrast=0.3), augment.jitter),
        _com_probabilidade(v2.RandomAffine(degrees=2, translate=(0.05, 0.05), scale=(0.95, 1.05)), augment.affine),
    ]
    etapas = [etapa for etapa in etapas if etapa is not None]
    etapas.extend(build_augmentations(augment))
    etapas.append(v2.Lambda(_clamp01))
    return v2.Compose(etapas)


@dataclass
class TrainingRun:
    """Resultado de um treino: o histórico mais o que é preciso para reproduzi-lo."""

    cancelled: bool = False
    """O treino parou por pedido, entre épocas (S-60).

    Não é falha: o checkpoint da melhor época gravada continua no disco e continua sendo o
    melhor conhecido. O que muda é o que a interface diz ao terminar."""

    history: list[dict[str, Any]] = field(default_factory=list)
    best_epoch: int = 0
    best_metric: float = 0.0
    best_metric_name: str = "val_board_exact_acc"
    metadata: dict[str, Any] = field(default_factory=dict)
    model_path: Path = Path()
    temperature: float = 1.0
    ece_before: float | None = None
    ece_after: float | None = None

    def __len__(self) -> int:
        """Compatibilidade com os chamadores que tratavam o retorno como a lista de épocas."""
        return len(self.history)

    def __iter__(self):
        return iter(self.history)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.history[index]


def set_seed(seed: int) -> None:
    """Semeia os três geradores que o treino usa.

    `numpy` entra porque o `ColorJitter` do torchvision v2 não é o único caminho
    aleatório: `random` é usado pelo próprio `v2.RandomApply`.
    """
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)


def resolve_num_workers(requested: int | None) -> int:
    """`None` → `min(4, cpu//2)`, que é o padrão que a S-26 pede.

    Atenção a quem chama: no Windows o start method é `spawn`, e cada worker **reimporta o
    módulo `__main__`**. `cvoff-train` e o `app_tkinter.py` têm guarda `if __name__ ==
    "__main__"`, então são seguros. O `examples/streamlit_demo.py` não tem -- não pode
    ter, é um script de topo executado pelo Streamlit --, e workers ali reexecutariam a
    página inteira dentro de cada processo. Por isso o padrão de `train_model` é 0 e quem sobe
    para 4 é o CLI, não a biblioteca.
    """
    if requested is not None:
        return max(0, int(requested))
    return min(4, (os.cpu_count() or 2) // 2)


def class_weights_for(entries: list, weighting: ClassWeighting) -> torch.Tensor | None:
    """Peso inverso à frequência observada, ou `None` para loss não ponderada.

    Classe ausente do treino recebe peso 0 em vez de infinito: ela não pode contribuir
    para a loss porque não aparece, e `total / 0` propagaria `inf` para o gradiente.
    """
    if weighting == "none":
        return None

    counts = np.zeros(NUM_CLASSES, dtype=np.float64)
    for entry in entries:
        try:
            for class_idx in labels_from_fen(entry.fen):
                counts[class_idx] += 1
        except ValueError:
            continue

    total = counts.sum()
    if total == 0:
        return None
    weights = np.where(counts > 0, total / (NUM_CLASSES * np.maximum(counts, 1.0)), 0.0)
    return torch.tensor(weights, dtype=torch.float32)


def resolve_splits(
    csv_path: Path,
    samples_dir: Path,
    splits_path: Path,
    *,
    assign_new: bool = True,
) -> dict[str, Split]:
    """Mapa de splits do `labels.csv`, atribuindo split às amostras novas (S-56).

    **O defeito que isto corrige.** `splits.ensure_splits` existia, estava correta e tinha
    teste, e nenhum código de produção a chamava: todos os consumidores usavam `load_splits`,
    que só lê. Então uma amostra recém-salva não recebia split, e
    `BoardFenDataset._load_entries` a descartava -- porque o que o mapa não conhece fica de
    fora, para que amostra nova não caia por acidente no conjunto de teste. Sem ninguém
    atribuindo, "não cai por acidente" virou "não entra nunca": 45 amostras, justamente as
    únicas com procedência preenchida, estavam fora do treino em silêncio. O ciclo do README
    -- corrigir, salvar, treinar -- não fechava.

    **Por que a deduplicação é restrita.** Membros de um mesmo diagrama precisam cair no
    mesmo split (S-07), e descobrir isso exige comparar imagens. `find_duplicate_groups` lê
    as 3.289 amostras, ~6 GB, o que seria absurdo a cada treino. `duplicate_groups_touching`
    lê só as linhas cujo rótulo alguma amostra nova também tem -- e o resultado é o mesmo,
    porque um grupo formado só por amostras antigas não muda atribuição nenhuma.

    `assign_new=False` volta ao comportamento anterior: lê e não escreve. Existe para quem
    quer avaliar um checkpoint contra a partição exata em que ele foi treinado, sem que a
    leitura mexa no arquivo.
    """
    splits_path = Path(splits_path)
    if not assign_new:
        return load_splits(splits_path)

    linhas = read_label_rows(Path(csv_path))
    nomes = [nome for nome, _fen in linhas if nome]
    registrados = load_splits(splits_path)
    novos = [nome for nome in nomes if nome not in registrados]

    # S-98: dois agrupamentos, e a união deles é o grupo. O de imagem não vê a mesma página
    # reextraída com recorte deslocado -- é como o `Niemeijer p10 d1` foi parar nas três
    # partições. O de origem vê, e é exato, mas só alcança as amostras com procedência.
    origens = label_origins(Path(csv_path))
    grupos = list(duplicate_groups_touching(Path(samples_dir), linhas, novos)) if novos else []
    grupos += groups_by_origin(origens)
    # A procedência que escolhe quem o `--dedupe` mantém é a mesma que dá a chave de split ao
    # grupo (S-452). Sem passá-la aqui, os dois lados voltariam a escolher representantes
    # diferentes -- e "quem representa este grupo" tem de ter uma resposta só.
    mapa = ensure_splits(
        nomes, splits_path, groups=grupos, with_provenance=filenames_with_provenance(origens)
    )

    if novos:
        distribuicao = Counter(mapa[nome] for nome in novos if nome in mapa)
        logger.info(
            "%d amostra(s) sem split receberam um agora: %s. Antes da S-56 elas ficavam "
            "invisíveis ao treino.",
            len(novos),
            ", ".join(f"{quantas} para {split}" for split, quantas in sorted(distribuicao.items())) or "nenhuma",
        )
    return mapa


def _split_square_indices_by_board(dataset: BoardFenDataset, val_ratio: float, seed: int) -> tuple[list[int], list[int]]:
    num_boards = len(dataset.entries)
    if num_boards <= 1:
        return list(range(len(dataset))), []

    val_boards = int(num_boards * val_ratio)
    val_boards = min(max(val_boards, 1), num_boards - 1)

    generator = torch.Generator().manual_seed(seed)
    board_perm = torch.randperm(num_boards, generator=generator).tolist()
    val_board_ids = set(board_perm[:val_boards])

    train_indices: list[int] = []
    val_indices: list[int] = []
    for square_dataset_idx, (entry_idx, _) in enumerate(dataset.index_map):
        (val_indices if entry_idx in val_board_ids else train_indices).append(square_dataset_idx)

    return train_indices, val_indices


@dataclass
class ValidationMetrics:
    loss: float
    square_accuracy: float
    board_exact_accuracy: float
    per_class_recall: dict[str, float]
    logits: torch.Tensor
    targets: torch.Tensor


def evaluate_validation(
    model: nn.Module,
    loader: DataLoader,
    device: str,
    criterion: nn.Module,
) -> ValidationMetrics:
    """Uma passada pela validação que produz todas as métricas de uma vez.

    Guarda os logits porque três consumidores precisam deles e uma passada custa o mesmo
    que três: a loss, a acurácia exata por tabuleiro (que exige reagrupar as casas) e a
    calibração da S-28 no fim do treino.

    **O reagrupamento depende da ordem.** As casas chegam em ordem de tabuleiro porque o
    loader de validação roda com `shuffle=False` e o `index_map` é organizado por
    tabuleiro. Se alguém ligar `shuffle` aqui, `board_exact_accuracy` passa a comparar
    casas de tabuleiros diferentes e o número fica errado sem dar erro -- daí a checagem
    de divisibilidade por 64 abaixo, que é o sintoma detectável.
    """
    model.eval()
    all_logits: list[torch.Tensor] = []
    all_targets: list[torch.Tensor] = []

    with torch.inference_mode():
        for xb, yb in loader:
            logits = model(xb.to(device))
            all_logits.append(logits.cpu())
            # Com a cabeca da S-62b o lote e (B, 64) de rotulos e (B*64, 13) de logits: a
            # cabeca devolve achatado justamente para que tudo daqui para baixo -- loss,
            # acuracia por casa, exata por tabuleiro, calibracao -- continue sendo o mesmo
            # codigo. So os alvos precisam acompanhar.
            all_targets.append(yb.reshape(-1).cpu())

    logits = torch.cat(all_logits).to(torch.float32)
    targets = torch.cat(all_targets).to(torch.long)
    predictions = logits.argmax(dim=1)
    hits = predictions == targets

    if logits.shape[0] % 64 != 0:
        raise ValueError(
            f"A validação tem {logits.shape[0]} casas, que não é múltiplo de 64. "
            f"A acurácia exata por tabuleiro depende de as 64 casas de cada tabuleiro "
            f"chegarem juntas e em ordem."
        )

    board_exact = hits.reshape(-1, 64).all(dim=1)

    recall: dict[str, float] = {}
    for class_idx, name in enumerate(PIECE_CLASSES):
        mask = targets == class_idx
        support = int(mask.sum())
        recall[name] = float(hits[mask].float().mean().item()) if support else float("nan")

    with torch.no_grad():
        loss = float(criterion(logits, targets).item())

    return ValidationMetrics(
        loss=loss,
        square_accuracy=float(hits.float().mean().item()),
        board_exact_accuracy=float(board_exact.float().mean().item()),
        per_class_recall=recall,
        logits=logits,
        targets=targets,
    )


def _load_for_resume(model: nn.Module, model_path: Path, arch: ArchConfig, device: str) -> Checkpoint:
    """Carrega os pesos para retomar, transformando a recusa do torch em pt-BR.

    `strict=True` é a garantia: se os pesos não correspondem exatamente à arquitetura, o
    torch levanta e o treino para. O que esta função acrescenta é não deixar o usuário
    diante de uma lista de `size mismatch for classifier.1.weight` sem saber o que fazer.
    """
    checkpoint = load_checkpoint(model_path, map_location=device)
    check_compatible(checkpoint, arch.version)

    try:
        model.load_state_dict(checkpoint.state, strict=True)
    except RuntimeError as exc:
        raise ValueError(
            f"Os pesos de {model_path.name} não correspondem à arquitetura '{arch.version}'. "
            f"Ele foi treinado com outra e retomá-lo não faria sentido. Treine do zero "
            f"(--fresh, ou a caixa 'Treinar do zero' na interface) ou aponte outro "
            f"checkpoint.\n\nDetalhe do torch: {exc}"
        ) from exc

    logger.info(
        "Retomando treino a partir de %s%s.",
        model_path.name,
        " (checkpoint anterior à Fase 5: arquitetura conferida pelos próprios pesos)" if checkpoint.is_legacy else "",
    )
    return checkpoint


def _motivo_para_medir(
    gravado: float | None,
    *,
    mesmo_split: bool,
    mesma_metrica: bool,
    nome_gravado: str,
    metric_name: str,
) -> str:
    """Por que o número gravado não serve -- na frase que vai para o log.

    São três causas independentes e elas se acumulam; dizer só a primeira faria o log mentir
    por omissão justamente na retomada em que mais de uma vale.
    """
    if gravado is None:
        return "não registra a métrica com que foi salvo"
    motivos = []
    if not mesmo_split:
        motivos.append("foi medido em outro split")
    if not mesma_metrica:
        qual = f"registra {nome_gravado!r}" if nome_gravado else "não registra qual métrica gravou"
        motivos.append(f"{qual} e este treino decide por {metric_name!r}")
    return " e ".join(motivos)


def _resolve_best_metric(
    resumed: Checkpoint | None,
    *,
    model: nn.Module,
    val_loader: DataLoader | None,
    device: str,
    criterion: nn.Module,
    split_hash: str,
    metric_name: str,
) -> tuple[float, int]:
    """Qual métrica a primeira época precisa superar para sobrescrever o checkpoint.

    Esta função é a correção definitiva da pendência que a Fase 1 registrou. Antes,
    retomar recomeçava o controle em infinito e a primeira época gravava por cima mesmo
    sendo pior -- foi assim que o treino do baseline quase se perdeu.

    Gravar `best_metric` no checkpoint (S-27) resolve o caso fácil. Sobram quatro em que o
    valor gravado não serve:

    - **checkpoint anterior à Fase 5**, que não registra métrica nenhuma;
    - **split diferente** do que produziu a métrica: 0,98 medido em outros 306 tabuleiros
      não é comparável com 0,98 medido nestes, e o dataset cresce;
    - **split que nenhum dos dois lados sabe qual é** (S-371): sem arquivo de splits o
      `split_hash` é `""` aqui e `""` no checkpoint, e a igualdade dizia "mesmo split" sobre
      duas partições que o `val_ratio` sorteia a cada execução, em datasets que cresceram
      entre uma e outra. Vazio não é identidade: é a ausência dela;
    - **outra métrica** (S-370): um checkpoint salvo sem validação registra `-train_loss`, e
      o `best_metric_name` que diz isso estava gravado e não era lido. Comparar `-0,42` com
      uma acurácia por tabuleiro, que vive em `[0, 1]`, não decide nada -- na retomada com
      validação a primeira época grava por cima sempre, e no sentido contrário nunca grava.

    Nos quatro, a resposta certa não é supor 0 nem confiar no número: é **medir** o modelo
    recém-carregado na validação atual, o que custa uma passada (~20 s) e dá o incumbente
    de verdade.
    """
    if resumed is None:
        # Treino do zero: nao ha incumbente, entao qualquer epoca grava. `-inf` diz isso
        # sem precisar de um caso especial na comparacao do laco.
        return float("-inf"), 0

    gravado = resumed.best_metric
    nome_gravado = str(resumed.metadata.get("best_metric_name", "") or "")
    split_gravado = str(resumed.metadata.get("split_hash", "") or "")
    # Vazio de qualquer um dos lados nao e "mesmo split": e "nao se sabe" (S-371).
    mesmo_split = bool(split_gravado) and split_gravado == split_hash
    mesma_metrica = bool(nome_gravado) and nome_gravado == metric_name
    if gravado is not None and mesmo_split and mesma_metrica:
        epoca = int(resumed.metadata.get("best_epoch", 0))
        logger.info("Melhor métrica registrada no checkpoint: %.6f (época %d).", gravado, epoca)
        return gravado, epoca

    motivo = _motivo_para_medir(
        gravado, mesmo_split=mesmo_split, mesma_metrica=mesma_metrica,
        nome_gravado=nome_gravado, metric_name=metric_name,
    )
    if val_loader is None:
        logger.warning(
            "Este treino não tem validação e %s %s: a primeira época vai sobrescrever o "
            "checkpoint. Faça uma cópia antes se ele importa.",
            resumed.path.name,
            motivo,
        )
        return float("-inf"), 0

    logger.info("%s %s: medindo-o na validação atual para saber o que a primeira época precisa superar...",
                resumed.path.name, motivo)
    incumbente = evaluate_validation(model, val_loader, device, criterion).board_exact_accuracy
    logger.info("Incumbente: val_board_exact_acc = %.6f. Só uma época melhor que isso grava por cima.", incumbente)
    return incumbente, 0


class _Unprepared(nn.Module):
    """Sentinela para os atributos do `Trainer` que só existem depois de `prepare()`.

    A alternativa seria tipá-los `nn.Module | None` e espalhar `assert` por sete métodos --
    o que troca uma mensagem útil por um `AssertionError` sem texto, e some com `-O`.
    """

    def forward(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Chame Trainer.prepare() antes de treinar: não há modelo nem critério montados.")


_UNPREPARED = _Unprepared()


@dataclass(frozen=True)
class DataPlan:
    """De onde vêm os tabuleiros e como eles chegam à memória."""

    csv_path: Path
    samples_dir: Path
    splits_path: Path | None = None
    assign_splits: bool = True
    val_ratio: float = 0.1
    cache_size: int = DEFAULT_BOARD_CACHE_SIZE
    num_workers: int | None = 0

    def __post_init__(self) -> None:
        if not 0.0 < self.val_ratio < 1.0:
            raise ValueError(f"val_ratio tem de ficar entre 0 e 1 (exclusivos); veio {self.val_ratio}.")
        if self.cache_size < 0:
            raise ValueError(f"cache_size não pode ser negativo; veio {self.cache_size}.")


@dataclass(frozen=True)
class OptimPlan:
    """Como o laço aprende, e quando ele desiste."""

    epochs: int = 5
    batch_size: int = 128
    lr: float = 1e-3
    patience: int = 15
    class_weights: ClassWeighting = DEFAULT_CLASS_WEIGHTS
    seed: int = 42
    augment: AugmentConfig = DEFAULT_AUGMENT

    boards_per_batch: int = 4
    """Tabuleiros por lote quando a cabeça é a da S-62b. Ignorado pelas outras.

    Quatro, e o número precisa de justificativa porque a S-26 já mediu o vizinho dele. Com o
    tabuleiro como unidade, `batch_size=128` deixaria de significar 128 casas e passaria a
    significar 128 tabuleiros -- 8.192 casas por passo, memória de sobra e uma época de 21
    passos. Na outra ponta, a leitura literal ("as 64 casas juntas") daria lotes de 1 ou 2
    tabuleiros, que é exatamente o regime de BatchNorm ruidoso que fez a S-26 escolher a
    janela em vez do tabuleiro.

    Quatro tabuleiros são 256 casas por lote: o dobro das 128 de hoje para as estatísticas do
    BatchNorm, vindas de 4 posições diferentes em vez de 2. É um regime **novo**, não herdado,
    e a S-62 manda remedi-lo em vez de supô-lo."""

    def __post_init__(self) -> None:
        if self.epochs < 0:
            raise ValueError(f"epochs não pode ser negativo; veio {self.epochs}.")
        if self.batch_size <= 0:
            raise ValueError(f"batch_size tem de ser positivo; veio {self.batch_size}.")
        if self.boards_per_batch <= 0:
            raise ValueError(f"boards_per_batch tem de ser positivo; veio {self.boards_per_batch}.")
        if self.lr <= 0:
            raise ValueError(f"lr tem de ser positivo; veio {self.lr}.")


@dataclass(frozen=True)
class OutputPlan:
    """O que o treino deixa no disco."""

    model_path: Path
    fresh: bool = False
    calibrate: bool = True
    pretrained: bool = True

    keep_ties: bool = False
    """Grava também a época que **empatou** com a melhor, ao lado (S-104).

    **Existe para um experimento, e não para o uso normal.** A métrica que decide tem
    granularidade de um tabuleiro -- 1/306 = 0,00327 no `val` da Fase 5 --, então empate é
    comum: em `docs/metrics/phase5_training.json` o máximo é atingido por duas épocas em 3 de
    3 execuções, e em 2 delas a época gravada tem `val_loss` **maior** que a da outra empatada.

    A pergunta que isto permite medir é se a de menor `val_loss` exporta mais em página real.
    Enquanto ela não tiver resposta, o `>` estrito do `accepts` fica -- e a razão dele está
    escrita lá: regravar sem ganho é reescrever 8,7 MB e correr o risco da S-57 de graça."""


@dataclass(frozen=True)
class TrainingPlan:
    """Os 18 parâmetros de `train_model`, agrupados por assunto e validados uma vez (S-47).

    Dezoito parâmetros posicionais não são um problema de estética: são quatro assuntos
    distintos -- de onde vêm os dados, qual é a arquitetura, como o laço aprende, o que fica
    no disco -- passados como uma lista plana em que nada valida nada. Agrupá-los é o que
    permite ao `Trainer` receber **um** objeto imutável e conferido, em vez de repassar
    dezoito por sete métodos.

    `train_model` continua com a assinatura antiga porque tem trinta chamadores entre CLI,
    `ui/training_dialog.py`, `experiments.py` e testes; ela monta este plano e delega.
    """

    data: DataPlan
    output: OutputPlan
    model: ArchConfig = DEFAULT_ARCH
    optim: OptimPlan = OptimPlan()


def labels_hash(entries: Iterable[DatasetEntry]) -> str:
    """Identidade do **conteúdo** dos rótulos de treino: SHA-256 dos pares `(arquivo, FEN)` (S-105).

    `split_hash` responde *qual partição*; este responde *qual verdade*. São perguntas
    diferentes, e até aqui só a primeira tinha resposta gravada -- as 468 amostras de correção
    humana que a S-107 mediu entraram no `train` **sem** que o `split_hash` mudasse, porque a
    partição delas era nova e não uma remontagem da antiga.

    **Ordenado, e por isso estável sob reordenação do CSV.** A pergunta é "estes rótulos são os
    mesmos?", e a ordem das linhas no arquivo não é parte da resposta -- ela muda por qualquer
    reescrita do `LabelStore`. Corrigir **uma** FEN, essa sim, muda o hash.

    Só o split de treino: `val` e `test` mudarem não altera o que o modelo aprendeu, e incluí-los
    faria o hash mudar por motivo que não é sobre este checkpoint. Quem vigia os reservados é o
    `split_hash`.
    """
    payload = "\n".join(sorted(f"{entry.filename}={entry.fen}" for entry in entries))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _optim_metadata(optim: OptimPlan, arch: ArchConfig) -> dict[str, Any]:
    """Os hiperparâmetros que reproduzem o número, prefixados para não colidir (S-105).

    `asdict(optim)` traria `augment` como dicionário aninhado e `class_weights`/`seed`
    duplicados -- os três já estão nos metadados com nome próprio desde a S-27 e a S-40.
    O que faltava são estes quatro, e é neles que `--lr 1e-4` e `--lr 1e-3` diferem.

    **E o lote tem duas unidades desde a S-62b (S-372).** A cabeça por tabuleiro monta o
    `DataLoader` com `boards_per_batch` e ignora `batch_size`; a cabeça por janela faz o
    contrário. Gravar só o `batch_size` deixava o checkpoint da cabeça nova declarando um
    número que não governou nada e omitindo o que governou -- dois treinos com
    `--boards-per-batch 4` e `8` saíam com metadados idênticos, que é exatamente o que a
    S-105 existiu para acabar. Os dois vão gravados, e `batch_unit` diz qual valeu.
    """
    return {
        "lr": optim.lr,
        "batch_size": optim.batch_size,
        "boards_per_batch": optim.boards_per_batch,
        "batch_unit": "board" if arch.head == "board" else "square",
        "epochs_requested": optim.epochs,
        "patience": optim.patience,
        # Fixo hoje, e gravado mesmo assim: um metadado ausente e um metadado que diz "Adam"
        # sao a mesma coisa **ate** o dia em que o otimizador mudar, e ai o segundo continua
        # verdadeiro sobre os checkpoints antigos e o primeiro nao diz nada sobre nenhum.
        "optimizer": "adam",
    }


class BestEpochPolicy:
    """Quando gravar por cima, e quando parar. Testável **sem treinar** -- era o que faltava.

    Esta política já teve um defeito real e caro, e o ROADMAP registra que "a primeira versão
    da 5.3 estava errada, e foi o uso que mostrou": retomar zerava o controle de melhor época
    em infinito, e a primeira época da retomada sobrescrevia o checkpoint mesmo sendo pior.
    O defeito sobreviveu porque **não havia como perguntar à política sem rodar um treino** --
    a decisão morava no meio de um laço de 259 linhas que precisa de dataset, modelo e GPU
    para ser exercitado.

    Aqui ela é um objeto de três métodos e nenhuma dependência: `accepts` responde à pergunta
    "esta métrica grava por cima?", `observe` registra a resposta, e `should_stop` responde
    à parada antecipada. Um teste que cobre a retomada custa três linhas e nenhum tensor.

    Convenção: **maior é melhor, sempre.** Sem validação a métrica é `-train_loss`, para que
    a comparação valha nos dois regimes sem um caso especial. E o incumbente de um treino do
    zero é `-inf`, para que a primeira época grave sem cláusula especial -- era justamente a
    cláusula especial que produzia o defeito acima.
    """

    def __init__(self, metric_name: str, incumbent: float, *, patience: int = 15, best_epoch: int = 0) -> None:
        self.metric_name = metric_name
        self.best_metric = incumbent
        self.best_epoch = best_epoch
        self.patience = patience
        self.epochs_without_improvement = 0

    def accepts(self, metric: float) -> bool:
        """Estritamente maior: empatar não regrava, porque regravar sem ganho é risco de graça."""
        return metric > self.best_metric

    def observe(self, metric: float, epoch: int) -> bool:
        """Aplica `accepts` e atualiza o estado. Devolve se a época é a nova melhor."""
        aceita = self.accepts(metric)
        if aceita:
            self.best_metric = metric
            self.best_epoch = epoch
            self.epochs_without_improvement = 0
        else:
            self.epochs_without_improvement += 1
        return aceita

    def should_stop(self, epochs_without_improvement: int | None = None) -> bool:
        """Parada antecipada. `patience <= 0` desliga."""
        contador = self.epochs_without_improvement if epochs_without_improvement is None else epochs_without_improvement
        return self.patience > 0 and contador >= self.patience

    @property
    def settled_metric(self) -> float:
        """O valor que vai para os metadados.

        `-inf` só sobrevive se nenhuma época rodou (`epochs=0`, ou cancelamento antes da
        primeira); gravá-lo seria um número falso.
        """
        return 0.0 if self.best_metric == float("-inf") else self.best_metric


class Trainer:
    """O treino em etapas nomeadas, cada uma chamável sozinha (S-47).

    `train_model` fazia sete coisas em 259 linhas: montar dataset e loaders, resolver split,
    retomar checkpoint, rodar o laço de época, decidir a melhor época, parar antecipadamente,
    calibrar e gravar. O tamanho era o sintoma; o custo era que nada disso podia ser
    perguntado isoladamente -- ver `BestEpochPolicy` para o defeito concreto que isso
    escondeu por duas fases.

    O ciclo de vida é `prepare() → resume() → run_epoch()* → finish()`, e `fit()` é
    exatamente essa sequência. Cada etapa pode ser chamada por um teste:

    - `prepare()` monta datasets, loaders, amostrador, pesos, critério e otimizador;
    - `resume()` carrega o checkpoint e resolve o incumbente que a primeira época precisa
      superar -- devolve o `Checkpoint` para inspeção, em vez de o esconder num local;
    - `run_epoch(n)` é uma época completa, chamável com dois lotes sintéticos;
    - `finish()` fecha metadados e calibração.

    **A ordem das operações aleatórias é a de antes, de propósito.** `set_seed` primeiro, o
    modelo construído antes de qualquer loader, e todo sorteio posterior com gerador
    explícito. Este item não pode mudar resultado, e a comparação do critério de aceite é
    sobre o histórico bit a bit sob a mesma semente.
    """

    def __init__(
        self,
        plan: TrainingPlan,
        *,
        progress: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.plan = plan
        self.progress = progress
        self.cancel_event = cancel_event

        self.device: str = "cpu"
        self.model: nn.Module = _UNPREPARED
        self.dataset: BoardFenDataset | None = None
        self.val_dataset: BoardFenDataset | None = None
        self.train_loader: DataLoader | None = None
        self.val_loader: DataLoader | None = None
        self.criterion: nn.Module = _UNPREPARED
        self.cpu_criterion: nn.Module = _UNPREPARED
        self.optimizer: torch.optim.Optimizer | None = None
        self.metadata_base: dict[str, Any] = {}
        self.resumed: Checkpoint | None = None
        self.best_validation: ValidationMetrics | None = None
        self.run = TrainingRun(model_path=Path(plan.output.model_path))
        self.policy = BestEpochPolicy("val_board_exact_acc", float("-inf"), patience=plan.optim.patience)

    # ------------------------------------------------------------------ prepare

    def prepare(self) -> None:
        """Datasets, loaders, amostrador, pesos, critério e otimizador."""
        data, optim, output = self.plan.data, self.plan.optim, self.plan.output
        arch = self.plan.model

        set_seed(optim.seed)
        workers = resolve_num_workers(data.num_workers)
        splits_map = (
            resolve_splits(data.csv_path, data.samples_dir, data.splits_path, assign_new=data.assign_splits)
            if data.splits_path is not None
            else None
        )

        # Com num_workers > 0 o cache e por processo: o teto vale W+1 vezes, e o criterio de
        # aceite da S-26 (< 2 GiB por epoca) e sobre o treino inteiro, nao sobre o pai.
        per_process_cache = max(1, data.cache_size // (workers + 1)) if workers else data.cache_size

        common = {"cache_size": per_process_cache, "arch": arch}
        if splits_map:
            dataset = BoardFenDataset(data.csv_path, data.samples_dir, split="train", splits=splits_map, **common)  # type: ignore[arg-type]
            val_dataset: BoardFenDataset | None = BoardFenDataset(
                data.csv_path,
                data.samples_dir,
                split="val",
                splits=splits_map,
                arch=arch,
                # Validacao e sequencial: um cache do tamanho do treino dobraria a memoria
                # residente para uma taxa de acerto que 4 tabuleiros ja entregam.
                cache_size=VAL_BOARD_CACHE_SIZE,
            )
            logger.info(
                "Split persistido em uso: %d tabuleiros de treino, %d de validação. Teste reservado.",
                len(dataset.entries),
                len(val_dataset.entries) if val_dataset else 0,
            )
        else:
            dataset = BoardFenDataset(data.csv_path, data.samples_dir, **common)  # type: ignore[arg-type]
            val_dataset = None
            logger.warning(
                "Sem arquivo de splits: a validação será sorteada e mudará quando o dataset crescer. "
                "Passe splits_path para uma métrica estável (S-07)."
            )

        if len(dataset) == 0:
            raise ValueError("Dataset vazio. Salve exemplos corrigidos antes de treinar.")

        if val_dataset is not None:
            train_indices = list(range(len(dataset)))
            val_indices = list(range(len(val_dataset)))
        else:
            train_indices, val_indices = _split_square_indices_by_board(
                dataset, val_ratio=data.val_ratio, seed=optim.seed
            )

        self.dataset, self.val_dataset = dataset, val_dataset
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = build_model(arch, pretrained=output.pretrained).to(self.device)

        logger.info(
            "Treinando em %s | arquitetura %s (%s parâmetros) | %d tabuleiros, %d casas | "
            "semente %d | workers %d | cache %d tabuleiros/processo | pesos de classe: %s",
            self.device,
            arch.version,
            f"{count_parameters(self.model):,}".replace(",", "."),
            len(dataset.entries),
            len(dataset),
            optim.seed,
            workers,
            per_process_cache,
            optim.class_weights,
        )

        loader_extra: dict[str, Any] = {"num_workers": workers}
        if workers:
            loader_extra["persistent_workers"] = True
            loader_extra["prefetch_factor"] = 2

        val_source = val_dataset if val_dataset is not None else dataset
        train_board_ids = {dataset.index_map[index][0] for index in train_indices}
        # Um so aumento para os dois caminhos: o guarda de `ImageChannelsOnly` o torna
        # transparente quando nao ha canal de coordenada para proteger.
        aumento = ImageChannelsOnly(build_train_transform(optim.augment), arch.image_channels)

        if arch.head == "board":
            # A cabeca da S-62b decide as 64 casas juntas, entao a unidade de amostragem passa
            # a ser o tabuleiro -- e com ela cai o `BoardGroupedSampler`, que existia para
            # aproximar isso sem pagar o preco. Um lote e N tabuleiros por construcao.
            val_board_ids = sorted({val_source.index_map[index][0] for index in val_indices})
            self.train_loader = DataLoader(
                BoardUnitDataset(dataset, sorted(train_board_ids), transform=aumento),
                batch_size=optim.boards_per_batch,
                shuffle=True,
                generator=torch.Generator().manual_seed(optim.seed),
                **loader_extra,
            )
            self.val_loader = (
                DataLoader(
                    BoardUnitDataset(val_source, val_board_ids),
                    batch_size=optim.boards_per_batch,
                    shuffle=False,
                    **loader_extra,
                )
                if val_board_ids
                else None
            )
            logger.info(
                "Cabeça por tabuleiro (S-62b): %d tabuleiro(s) por lote, %d casas por passo. "
                "O amostrador por janela da S-26 não é usado neste regime.",
                optim.boards_per_batch,
                optim.boards_per_batch * 64,
            )
        else:
            train_ds = TransformSubset(Subset(dataset, train_indices), transform=aumento)
            sampler = BoardGroupedSampler(board_groups(dataset.index_map, train_indices), shuffle=True, seed=optim.seed)
            self.train_loader = DataLoader(
                train_ds,
                batch_size=optim.batch_size,
                sampler=sampler,
                generator=torch.Generator().manual_seed(optim.seed),
                **loader_extra,
            )

            # Sem shuffle e sem amostrador: a ordem sequencial ja e por tabuleiro, e a acuracia
            # exata por tabuleiro depende disso (ver `evaluate_validation`).
            val_ds: Subset | None = Subset(val_source, val_indices) if val_indices else None
            self.val_loader = (
                DataLoader(val_ds, batch_size=optim.batch_size, shuffle=False, **loader_extra)
                if val_ds is not None
                else None
            )

        weights = class_weights_for([dataset.entries[i] for i in sorted(train_board_ids)], optim.class_weights)
        if weights is not None:
            logger.info(
                "Pesos de classe: %s",
                ", ".join(f"{name}={value:.2f}" for name, value in zip(PIECE_CLASSES, weights.tolist(), strict=True)),
            )
        self.criterion = nn.CrossEntropyLoss(weight=weights.to(self.device) if weights is not None else None)
        self.cpu_criterion = nn.CrossEntropyLoss(weight=weights if weights is not None else None)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=optim.lr)

        self.metadata_base = {
            "arch_version": arch.version,
            "class_names": list(PIECE_CLASSES),
            "seed": optim.seed,
            "class_weights": optim.class_weights,
            # Sem isto, "o modelo A e melhor que o B" pode estar comparando dois regimes de
            # aumento -- a mesma armadilha que a S-27 fechou para arquitetura e semente (S-40).
            "augment_version": optim.augment.version,
            # Os hiperparametros de otimizacao, inteiros (S-105). Sem eles, `--lr 1e-4` e
            # `--lr 1e-3` produziam dois arquivos indistinguiveis pelos metadados -- e ha 17
            # checkpoints em `models/` e nove treinos comparados no EXPERIMENTS_FASE7.
            **_optim_metadata(optim, arch),
            "split_hash": splits_hash(splits_map) if splits_map else "",
            # **Qual particao** e **qual verdade** sao perguntas diferentes, e ate aqui so a
            # primeira tinha resposta: as 468 amostras de correcao humana da S-107 entraram
            # sem que o `split_hash` mudasse.
            "labels_hash": labels_hash([dataset.entries[i] for i in sorted(train_board_ids)]),
            "splits_path": str(data.splits_path) if data.splits_path else "",
            "dataset_size": len(dataset.entries),
            "val_size": len(val_dataset.entries) if val_dataset is not None else len(val_indices) // 64,
            "git_commit": git_commit(),
            "best_metric_name": "val_board_exact_acc" if self.val_loader is not None else "train_loss",
        }
        self.run.best_metric_name = str(self.metadata_base["best_metric_name"])
        self.policy = BestEpochPolicy(
            self.run.best_metric_name, float("-inf"), patience=optim.patience
        )

    # ------------------------------------------------------------------- resume

    def resume(self) -> Checkpoint | None:
        """Carrega o checkpoint existente e resolve o incumbente da primeira época.

        Devolve o `Checkpoint` em vez de o guardar em silêncio: "de onde vieram estes pesos"
        é a pergunta que uma retomada sempre levanta, e agora ela tem resposta sem log.
        """
        model_path = Path(self.plan.output.model_path)
        if self.plan.output.fresh:
            logger.info("Treinando do zero (--fresh): checkpoint existente será ignorado.")
        elif model_path.exists():
            self.resumed = _load_for_resume(self.model, model_path, self.plan.model, self.device)

        best_metric, best_epoch = _resolve_best_metric(
            self.resumed,
            model=self.model,
            val_loader=self.val_loader,
            device=self.device,
            criterion=self.cpu_criterion,
            split_hash=str(self.metadata_base.get("split_hash", "")),
            metric_name=self.run.best_metric_name,
        )
        self.policy = BestEpochPolicy(
            self.run.best_metric_name, best_metric, patience=self.plan.optim.patience, best_epoch=best_epoch
        )
        self.run.best_metric, self.run.best_epoch = best_metric, best_epoch
        return self.resumed

    # --------------------------------------------------------------------- laço

    def validate(self) -> ValidationMetrics:
        """Uma passada pela validação. Levanta se o plano não tem conjunto de validação."""
        if self.val_loader is None:
            raise ValueError("Este treino não tem conjunto de validação: não há o que medir.")
        return evaluate_validation(self.model, self.val_loader, self.device, self.cpu_criterion)

    def run_epoch(self, epoch: int) -> dict[str, Any]:
        """Uma época completa: treinar, validar, decidir se grava, avisar quem observa."""
        if self.train_loader is None or self.optimizer is None:
            raise RuntimeError("Chame prepare() antes de run_epoch().")

        self.model.train()
        train_loss = 0.0
        train_hits = 0
        seen = 0

        for xb, yb in self.train_loader:
            # `reshape(-1)` para a cabeca por tabuleiro (S-62b), que entrega (B, 64) de
            # rotulos; para as outras cabecas yb ja e 1-D e isto e uma vista, nao uma copia.
            xb, yb = xb.to(self.device), yb.to(self.device).reshape(-1)
            self.optimizer.zero_grad()
            logits = self.model(xb)
            loss = self.criterion(logits, yb)
            loss.backward()
            self.optimizer.step()

            # Contado em **casas**, e nao em itens do lote: a loss por casa e o unico numero
            # comparavel entre os dois regimes, e `xb.size(0)` significaria tabuleiros num e
            # casas no outro.
            casas = yb.numel()
            train_loss += float(loss.item()) * casas
            train_hits += int((logits.argmax(dim=1) == yb).sum().item())
            seen += casas

        row: dict[str, Any] = {
            "epoch": epoch,
            "total_epochs": self.plan.optim.epochs,
            "train_loss": train_loss / max(seen, 1),
            "train_square_acc": train_hits / max(seen, 1),
        }

        validation: ValidationMetrics | None = None
        if self.val_loader is not None:
            validation = self.validate()
            row["val_loss"] = validation.loss
            row["val_square_acc"] = validation.square_accuracy
            row["val_board_exact_acc"] = validation.board_exact_accuracy
            row["val_per_class_recall"] = validation.per_class_recall
            # Maior e melhor, ao contrario da loss.
            metric_for_best = validation.board_exact_accuracy
        else:
            # Sem validacao a unica coisa disponivel e a loss de treino, e ai menor e melhor:
            # negar deixa a comparacao "maior e melhor" valendo nos dois regimes.
            metric_for_best = -row["train_loss"]

        # Sem clausula especial para a primeira epoca: num treino do zero o incumbente e
        # `-inf`, e numa retomada e a metrica real do checkpoint que esta no disco. Era a
        # clausula especial que fazia a primeira epoca de uma retomada gravar por cima.
        # **Antes** do `observe`, porque ele move o incumbente: depois da chamada não há mais
        # como saber que esta época empatou com a melhor em vez de perder para ela (S-104).
        empatou = not self.policy.accepts(metric_for_best) and metric_for_best == self.policy.best_metric

        improved = self.policy.observe(metric_for_best, epoch)
        if empatou and self.plan.output.keep_ties:
            self._save_tie(epoch, metric_for_best, row)
        if improved:
            self.run.best_metric = self.policy.best_metric
            self.run.best_epoch = self.policy.best_epoch
            self.best_validation = validation
            save_checkpoint(
                Path(self.plan.output.model_path),
                self.model.state_dict(),
                metadata={
                    **self.metadata_base,
                    "best_metric": metric_for_best,
                    "best_epoch": epoch,
                    "metrics": _plain(row),
                },
            )

        row["is_best"] = improved
        self.run.history.append(row)
        if self.progress is not None:
            self.progress(row)
        return row

    def _save_tie(self, epoch: int, metric: float, row: dict[str, Any]) -> Path:
        """Grava a época empatada num arquivo próprio, `<modelo>.tie-e<N>.pt` (S-104).

        **Ao lado e não por cima**: o checkpoint principal continua sendo o que o `>` estrito
        do `accepts` decidiu, e a comparação entre os dois é justamente o que se quer medir.
        Um nome por época porque um treino pode empatar mais de uma vez, e sobrescrever
        deixaria o experimento com um lado só.
        """
        destino = Path(self.plan.output.model_path)
        destino = destino.with_name(f"{destino.stem}.tie-e{epoch}{destino.suffix}")
        save_checkpoint(
            destino,
            self.model.state_dict(),
            metadata={
                **self.metadata_base,
                "best_metric": metric,
                "best_epoch": epoch,
                "metrics": _plain(row),
                # Marcado no proprio arquivo: sem isto, um `.tie-*.pt` copiado para outro nome
                # seria indistinguivel de um checkpoint que a politica escolheu.
                "tie_with_best_epoch": self.policy.best_epoch,
            },
        )
        logger.info(
            "Época %d empatou com a %d em %s=%.6f; gravada em %s para comparação (S-104).",
            epoch,
            self.policy.best_epoch,
            self.run.best_metric_name,
            metric,
            destino.name,
        )
        return destino

    def _cancelled(self, epoch: int) -> bool:
        """Conferido **entre** épocas, e não dentro do laço de lotes.

        Pelo mesmo motivo da varredura (S-24): o pior caso de resposta é uma unidade de
        trabalho, e aqui a unidade é a época porque é ela que decide se o checkpoint muda.
        Interromper no meio de uma época devolveria pesos que nenhuma métrica avaliou (S-60).
        """
        if self.cancel_event is None or not self.cancel_event.is_set():
            return False
        logger.info("Treino cancelado antes da época %d. O melhor checkpoint gravado continua valendo.", epoch)
        self.run.cancelled = True
        return True

    # ------------------------------------------------------------------- finish

    def finish(self) -> TrainingRun:
        """Metadados, calibração da S-28 e o log de fecho."""
        model_path = Path(self.plan.output.model_path)
        self.run.best_metric = self.policy.settled_metric
        self.run.best_epoch = self.policy.best_epoch
        self.run.metadata = {
            **self.metadata_base,
            "best_metric": self.run.best_metric,
            "best_epoch": self.run.best_epoch,
        }

        calibrate = self.plan.output.calibrate
        if calibrate and self.best_validation is not None:
            _calibrate_and_store(self.run, self.best_validation, model_path, self.device)
        elif calibrate and self.val_loader is None:
            logger.info("Sem conjunto de validação: calibração (S-28) pulada, temperatura fica em 1,0.")
        elif calibrate and not model_path.exists():
            # Cancelado antes da primeira época (S-60), ou `epochs=0`: não há checkpoint no disco
            # para ler a temperatura de, e nem deveria haver. Ler daqui era o único caminho que
            # supunha que sempre existe um arquivo -- suposição que valia enquanto o treino não
            # podia ser interrompido antes de gravar o primeiro.
            logger.info("Nenhuma época rodou e não há checkpoint em %s: calibração pulada.", model_path)
        elif calibrate:
            # Retomada em que nenhuma epoca superou o melhor registrado: o checkpoint no disco
            # e de outra execucao e ja tem a temperatura dela. Recalibra-lo com os logits
            # destes pesos -- que sao piores e nao serao gravados -- daria um T que nao
            # corresponde ao modelo que esta no arquivo.
            self.run.temperature = load_checkpoint(model_path, map_location=self.device).temperature
            logger.info(
                "Nenhuma época superou o melhor registrado (%s = %.6f): o checkpoint no disco não "
                "foi tocado, e a temperatura dele (%.4f) continua valendo.",
                self.run.best_metric_name,
                self.run.best_metric,
                self.run.temperature,
            )

        logger.info(
            "Treino %s em %d épocas. Melhor época: %d (%s = %.6f). Checkpoint em %s.",
            "cancelado" if self.run.cancelled else "concluído",
            len(self.run.history),
            self.run.best_epoch,
            self.run.best_metric_name,
            self.run.best_metric,
            model_path,
        )
        return self.run

    def fit(self) -> TrainingRun:
        """`prepare → resume → laço → finish`, que é o que `train_model` sempre fez."""
        self.prepare()
        self.resume()

        for epoch in range(1, self.plan.optim.epochs + 1):
            if self._cancelled(epoch):
                break
            self.run_epoch(epoch)
            if self.policy.should_stop():
                logger.info(
                    "Parada antecipada: sem melhora de %s por %d épocas. Interrompendo na época %d.",
                    self.run.best_metric_name,
                    self.plan.optim.patience,
                    epoch,
                )
                break

        return self.finish()


def train_model(
    csv_path: Path,
    samples_dir: Path,
    model_path: Path,
    epochs: int = 5,
    batch_size: int = 128,
    lr: float = 1e-3,
    val_ratio: float = 0.1,
    patience: int = 15,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    *,
    fresh: bool = False,
    splits_path: Path | None = None,
    arch: ArchConfig = DEFAULT_ARCH,
    class_weights: ClassWeighting = DEFAULT_CLASS_WEIGHTS,
    seed: int = 42,
    cache_size: int = DEFAULT_BOARD_CACHE_SIZE,
    num_workers: int | None = 0,
    calibrate: bool = True,
    pretrained: bool = True,
    assign_splits: bool = True,
    cancel_event: threading.Event | None = None,
    augment: AugmentConfig = DEFAULT_AUGMENT,
    boards_per_batch: int = OptimPlan.boards_per_batch,
    keep_ties: bool = False,
) -> TrainingRun:
    """Treina o classificador de peças. Monta o `TrainingPlan` e chama `Trainer.fit()` (S-47).

    A assinatura é a de sempre porque tem trinta chamadores; o corpo são vinte e cinco linhas.
    Quem precisa de uma etapa isolada -- rodar uma época com dois lotes, perguntar à política
    de melhor época sem treinar, inspecionar o checkpoint retomado -- usa o `Trainer` direto.

    `splits_path` aponta para o arquivo de splits persistido (`data/splits.csv`). Quando
    informado, o treino usa **apenas** o split `train` e valida no `val`; o `test` fica
    reservado e nunca é visto. Sem ele, cai no comportamento antigo de sortear a validação
    a cada execução -- que contamina a métrica ao longo do tempo (S-07).

    `assign_splits=True` (o padrão) dá split às amostras que ainda não têm, antes de montar
    o dataset. É o que faz o ciclo do README fechar: sem isso, uma amostra recém-salva nunca
    entra no treino, porque `BoardFenDataset` descarta o que o mapa de splits não conhece
    (S-56). `False` lê e não escreve -- útil para reproduzir um treino sobre a partição
    exata de antes.

    `fresh=True` ignora o checkpoint existente e treina do zero. `num_workers=None` resolve
    para `min(4, cpu//2)`; ver a ressalva de `resolve_num_workers` sobre o Streamlit.

    `cancel_event` interrompe **entre épocas** (S-60). Até aqui o treino não tinha
    cancelamento nenhum, então parar exigia fechar a janela -- e fechar a janela matava a
    thread no meio de um `torch.save`, que era a outra metade do defeito da S-57. O melhor
    checkpoint gravado até o cancelamento continua valendo, porque ele é gravado por época e
    não no fim.
    """
    plan = TrainingPlan(
        data=DataPlan(
            csv_path=Path(csv_path),
            samples_dir=Path(samples_dir),
            splits_path=Path(splits_path) if splits_path is not None else None,
            assign_splits=assign_splits,
            val_ratio=val_ratio,
            cache_size=cache_size,
            num_workers=num_workers,
        ),
        output=OutputPlan(
            model_path=Path(model_path),
            fresh=fresh,
            calibrate=calibrate,
            pretrained=pretrained,
            keep_ties=keep_ties,
        ),
        model=arch,
        optim=OptimPlan(
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            patience=patience,
            class_weights=class_weights,
            seed=seed,
            augment=augment,
            boards_per_batch=boards_per_batch,
        ),
    )
    return Trainer(plan, progress=progress_cb, cancel_event=cancel_event).fit()


def _plain(row: dict[str, Any]) -> dict[str, Any]:
    """Só o que serializa bem no checkpoint (`weights_only=True` recusa objetos)."""
    return {key: value for key, value in row.items() if isinstance(value, (int, float, str, bool))}


def _calibrate_and_store(run: TrainingRun, validation: ValidationMetrics, model_path: Path, device: str) -> None:
    """Ajusta a temperatura no `val` da melhor época e regrava o checkpoint (S-28).

    Usa os logits da **melhor** época, não da última: o checkpoint no disco é o da melhor,
    e calibrar com os logits de outro conjunto de pesos daria um `T` que não corresponde ao
    modelo que vai ser usado.
    """
    confidences = torch.softmax(validation.logits, dim=1).max(dim=1).values.numpy()
    correct = (validation.logits.argmax(dim=1) == validation.targets).numpy().astype(np.float64)
    run.ece_before = expected_calibration_error(confidences, correct)

    temperature = fit_temperature(validation.logits, validation.targets)
    scaled = torch.softmax(validation.logits / temperature, dim=1).max(dim=1).values.numpy()
    run.ece_after = expected_calibration_error(scaled, correct)
    run.temperature = temperature

    logger.info(
        "Calibração (S-28): T = %.4f | ECE no val %.5f → %.5f | NLL %.5f → %.5f",
        temperature,
        run.ece_before,
        run.ece_after,
        negative_log_likelihood(validation.logits, validation.targets, 1.0),
        negative_log_likelihood(validation.logits, validation.targets, temperature),
    )

    checkpoint = load_checkpoint(model_path, map_location=device)
    save_checkpoint(
        model_path,
        checkpoint.state,
        metadata={**checkpoint.metadata, "ece_val_before": run.ece_before, "ece_val_after": run.ece_after},
        temperature=temperature,
    )
