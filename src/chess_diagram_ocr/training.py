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

import logging
import os
import random
import threading
from collections import Counter
from collections.abc import Callable
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
from .dataset import BoardFenDataset, BoardGroupedSampler, board_groups
from .fen_utils import labels_from_fen
from .model import DEFAULT_ARCH, ArchConfig, build_model, count_parameters
from .splits import Split, ensure_splits, load_splits, splits_hash

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


def _clamp01(x: torch.Tensor) -> torch.Tensor:
    """Era uma `lambda` dentro do `v2.Compose`.

    Uma lambda não é picklável, e no Windows o `DataLoader` com `num_workers > 0` usa
    `spawn`: a pipeline de aumento inteira é pickleada para cada worker. Com a lambda,
    ligar o carregamento paralelo da S-26 falharia com `PicklingError` -- num ponto do
    código que não tem nada a ver com paralelismo.
    """
    return torch.clamp(x, 0.0, 1.0)


def build_train_transform(augment: AugmentConfig = DEFAULT_AUGMENT) -> Callable:
    """A pipeline de aumento. O padrão reproduz o treino anterior à S-40.

    As três primeiras etapas são o conjunto genérico de sempre. As dirigidas ao acervo
    (hachura, granulação, papel, inversão, espelhamento) entram depois delas e **desligadas
    por padrão**: ligar muda o modelo, e é a grade da S-40 que decide quais valem.

    A ordem coloca as dirigidas **depois** do afim de propósito. O afim reamostra, e
    reamostrar uma hachura sintética de período 6 px a borraria até sumir -- justamente a
    frequência que se quer ensinar.
    """
    etapas: list[Any] = [
        v2.RandomApply([v2.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0))], p=augment.blur),
        v2.ColorJitter(brightness=0.3, contrast=0.3),
        v2.RandomAffine(degrees=2, translate=(0.05, 0.05), scale=(0.95, 1.05)),
    ]
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
    "__main__"`, então são seguros. O `app_streamlit.py` não tem -- não pode ter, é um
    script de topo executado pelo Streamlit --, e workers ali reexecutariam a página
    inteira dentro de cada processo. Por isso o padrão de `train_model` é 0 e quem sobe
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

    grupos = duplicate_groups_touching(Path(samples_dir), linhas, novos) if novos else []
    mapa = ensure_splits(nomes, splits_path, groups=grupos)

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
            all_targets.append(yb.cpu())

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


def _resolve_best_metric(
    resumed: Checkpoint | None,
    *,
    model: nn.Module,
    val_loader: DataLoader | None,
    device: str,
    criterion: nn.Module,
    split_hash: str,
) -> tuple[float, int]:
    """Qual métrica a primeira época precisa superar para sobrescrever o checkpoint.

    Esta função é a correção definitiva da pendência que a Fase 1 registrou. Antes,
    retomar recomeçava o controle em infinito e a primeira época gravava por cima mesmo
    sendo pior -- foi assim que o treino do baseline quase se perdeu.

    Gravar `best_metric` no checkpoint (S-27) resolve o caso fácil. Sobram dois em que o
    valor gravado não serve:

    - **checkpoint anterior à Fase 5**, que não registra métrica nenhuma;
    - **split diferente** do que produziu a métrica: 0,98 medido em outros 306 tabuleiros
      não é comparável com 0,98 medido nestes, e o dataset cresce.

    Nos dois, a resposta certa não é supor 0 nem confiar no número: é **medir** o modelo
    recém-carregado na validação atual, o que custa uma passada (~20 s) e dá o incumbente
    de verdade.
    """
    if resumed is None:
        # Treino do zero: nao ha incumbente, entao qualquer epoca grava. `-inf` diz isso
        # sem precisar de um caso especial na comparacao do laco.
        return float("-inf"), 0

    gravado = resumed.best_metric
    mesmo_split = str(resumed.metadata.get("split_hash", "")) == split_hash
    if gravado is not None and mesmo_split:
        epoca = int(resumed.metadata.get("best_epoch", 0))
        logger.info("Melhor métrica registrada no checkpoint: %.6f (época %d).", gravado, epoca)
        return gravado, epoca

    if val_loader is None:
        logger.warning(
            "Sem validação e sem métrica registrada em %s: a primeira época vai sobrescrever "
            "o checkpoint. Faça uma cópia antes se ele importa.",
            resumed.path.name,
        )
        return float("-inf"), 0

    motivo = "não registra a métrica com que foi salvo" if gravado is None else "foi medido em outro split"
    logger.info("%s %s: medindo-o na validação atual para saber o que a primeira época precisa superar...",
                resumed.path.name, motivo)
    incumbente = evaluate_validation(model, val_loader, device, criterion).board_exact_accuracy
    logger.info("Incumbente: val_board_exact_acc = %.6f. Só uma época melhor que isso grava por cima.", incumbente)
    return incumbente, 0


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
) -> TrainingRun:
    """Treina o classificador de peças.

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
    set_seed(seed)
    workers = resolve_num_workers(num_workers)
    splits_map = (
        resolve_splits(Path(csv_path), Path(samples_dir), Path(splits_path), assign_new=assign_splits)
        if splits_path is not None
        else None
    )

    # Com num_workers > 0 o cache e por processo: o teto vale W+1 vezes, e o criterio de
    # aceite da S-26 (< 2 GiB por epoca) e sobre o treino inteiro, nao sobre o pai.
    per_process_cache = max(1, cache_size // (workers + 1)) if workers else cache_size

    common = {"cache_size": per_process_cache, "arch": arch}
    if splits_map:
        dataset = BoardFenDataset(Path(csv_path), Path(samples_dir), split="train", splits=splits_map, **common)  # type: ignore[arg-type]
        val_dataset: BoardFenDataset | None = BoardFenDataset(
            Path(csv_path),
            Path(samples_dir),
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
        dataset = BoardFenDataset(Path(csv_path), Path(samples_dir), **common)  # type: ignore[arg-type]
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
        train_indices, val_indices = _split_square_indices_by_board(dataset, val_ratio=val_ratio, seed=seed)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model(arch, pretrained=pretrained).to(device)

    resumed: Checkpoint | None = None
    if fresh:
        logger.info("Treinando do zero (--fresh): checkpoint existente será ignorado.")
    elif Path(model_path).exists():
        resumed = _load_for_resume(model, Path(model_path), arch, device)

    logger.info(
        "Treinando em %s | arquitetura %s (%s parâmetros) | %d tabuleiros, %d casas | "
        "semente %d | workers %d | cache %d tabuleiros/processo | pesos de classe: %s",
        device,
        arch.version,
        f"{count_parameters(model):,}".replace(",", "."),
        len(dataset.entries),
        len(dataset),
        seed,
        workers,
        per_process_cache,
        class_weights,
    )

    train_ds = TransformSubset(Subset(dataset, train_indices), transform=build_train_transform(augment))
    sampler = BoardGroupedSampler(board_groups(dataset.index_map, train_indices), shuffle=True, seed=seed)

    loader_extra: dict[str, Any] = {"num_workers": workers}
    if workers:
        loader_extra["persistent_workers"] = True
        loader_extra["prefetch_factor"] = 2
    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        sampler=sampler,
        generator=torch.Generator().manual_seed(seed),
        **loader_extra,
    )

    # Sem shuffle e sem amostrador: a ordem sequencial ja e por tabuleiro, e a acuracia
    # exata por tabuleiro depende disso (ver `evaluate_validation`).
    val_source = val_dataset if val_dataset is not None else dataset
    val_ds: Subset | None = Subset(val_source, val_indices) if val_indices else None
    val_loader = (
        DataLoader(val_ds, batch_size=batch_size, shuffle=False, **loader_extra) if val_ds is not None else None
    )

    train_board_ids = {dataset.index_map[index][0] for index in train_indices}
    weights = class_weights_for([dataset.entries[i] for i in sorted(train_board_ids)], class_weights)
    if weights is not None:
        logger.info(
            "Pesos de classe: %s",
            ", ".join(f"{name}={value:.2f}" for name, value in zip(PIECE_CLASSES, weights.tolist(), strict=True)),
        )
    criterion = nn.CrossEntropyLoss(weight=weights.to(device) if weights is not None else None)
    cpu_criterion = nn.CrossEntropyLoss(weight=weights if weights is not None else None)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    metadata_base: dict[str, Any] = {
        "arch_version": arch.version,
        "class_names": list(PIECE_CLASSES),
        "seed": seed,
        "class_weights": class_weights,
        # Sem isto, "o modelo A e melhor que o B" pode estar comparando dois regimes de
        # aumento -- a mesma armadilha que a S-27 fechou para arquitetura e semente (S-40).
        "augment_version": augment.version,
        "split_hash": splits_hash(splits_map) if splits_map else "",
        "splits_path": str(splits_path) if splits_path else "",
        "dataset_size": len(dataset.entries),
        "val_size": len(val_dataset.entries) if val_dataset is not None else len(val_indices) // 64,
        "git_commit": git_commit(),
        "best_metric_name": "val_board_exact_acc" if val_loader is not None else "train_loss",
    }

    best_metric, best_epoch = _resolve_best_metric(
        resumed,
        model=model,
        val_loader=val_loader,
        device=device,
        criterion=cpu_criterion,
        split_hash=str(metadata_base["split_hash"]),
    )

    run = TrainingRun(model_path=Path(model_path), best_metric=best_metric, best_epoch=best_epoch)
    run.best_metric_name = str(metadata_base["best_metric_name"])
    epochs_no_improve = 0
    best_validation: ValidationMetrics | None = None

    for epoch in range(1, epochs + 1):
        if cancel_event is not None and cancel_event.is_set():
            # Conferido **entre** épocas, e não dentro do laço de lotes, pelo mesmo motivo da
            # varredura (S-24): o pior caso de resposta é uma unidade de trabalho, e aqui a
            # unidade é a época porque é ela que decide se o checkpoint muda. Interromper no
            # meio de uma época devolveria pesos que nenhuma métrica avaliou (S-60).
            logger.info("Treino cancelado antes da época %d. O melhor checkpoint gravado continua valendo.", epoch)
            run.cancelled = True
            break

        model.train()
        train_loss = 0.0
        train_hits = 0
        seen = 0

        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()

            train_loss += float(loss.item()) * xb.size(0)
            train_hits += int((logits.argmax(dim=1) == yb).sum().item())
            seen += xb.size(0)

        row: dict[str, Any] = {
            "epoch": epoch,
            "total_epochs": epochs,
            "train_loss": train_loss / max(seen, 1),
            "train_square_acc": train_hits / max(seen, 1),
        }

        if val_loader is not None:
            validation = evaluate_validation(model, val_loader, device, cpu_criterion)
            row["val_loss"] = validation.loss
            row["val_square_acc"] = validation.square_accuracy
            row["val_board_exact_acc"] = validation.board_exact_accuracy
            row["val_per_class_recall"] = validation.per_class_recall
            # Maior e melhor, ao contrario da loss.
            metric_for_best = validation.board_exact_accuracy
        else:
            validation = None  # type: ignore[assignment]
            # Sem validacao a unica coisa disponivel e a loss de treino, e ai menor e melhor:
            # negar deixa a comparacao "maior e melhor" valendo nos dois regimes.
            metric_for_best = -row["train_loss"]

        # Sem clausula especial para a primeira epoca: num treino do zero o incumbente e
        # `-inf`, e numa retomada e a metrica real do checkpoint que esta no disco. Era a
        # clausula especial que fazia a primeira epoca de uma retomada gravar por cima.
        improved = metric_for_best > run.best_metric
        if improved:
            run.best_metric = metric_for_best
            run.best_epoch = epoch
            epochs_no_improve = 0
            best_validation = validation
            save_checkpoint(
                Path(model_path),
                model.state_dict(),
                metadata={**metadata_base, "best_metric": metric_for_best, "best_epoch": epoch, "metrics": _plain(row)},
            )
        else:
            epochs_no_improve += 1

        row["is_best"] = improved
        run.history.append(row)
        if progress_cb is not None:
            progress_cb(row)

        if patience > 0 and epochs_no_improve >= patience:
            logger.info(
                "Parada antecipada: sem melhora de %s por %d épocas. Interrompendo na época %d.",
                run.best_metric_name,
                patience,
                epoch,
            )
            break

    # `-inf` so sobrevive se nenhuma epoca rodou (epochs=0); grava-lo seria um numero falso.
    if run.best_metric == float("-inf"):
        run.best_metric = 0.0
    run.metadata = {**metadata_base, "best_metric": run.best_metric, "best_epoch": run.best_epoch}

    if calibrate and best_validation is not None:
        _calibrate_and_store(run, best_validation, Path(model_path), device)
    elif calibrate and val_loader is None:
        logger.info("Sem conjunto de validação: calibração (S-28) pulada, temperatura fica em 1,0.")
    elif calibrate and not Path(model_path).exists():
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
        run.temperature = load_checkpoint(Path(model_path), map_location=device).temperature
        logger.info(
            "Nenhuma época superou o melhor registrado (%s = %.6f): o checkpoint no disco não "
            "foi tocado, e a temperatura dele (%.4f) continua valendo.",
            run.best_metric_name,
            run.best_metric,
            run.temperature,
        )

    logger.info(
        "Treino %s em %d épocas. Melhor época: %d (%s = %.6f). Checkpoint em %s.",
        "cancelado" if run.cancelled else "concluído",
        len(run.history),
        run.best_epoch,
        run.best_metric_name,
        run.best_metric,
        model_path,
    )
    return run


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
