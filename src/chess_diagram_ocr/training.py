from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision.transforms import v2

from .checkpoint import load_state_dict
from .dataset import BoardFenDataset
from .model import PieceClassifier
from .splits import load_splits

logger = logging.getLogger(__name__)


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


def _accuracy(logits: torch.Tensor, target: torch.Tensor) -> float:
    preds = logits.argmax(dim=1)
    return float((preds == target).float().mean().item())


def _split_square_indices_by_board(dataset: BoardFenDataset, val_ratio: float) -> tuple[list[int], list[int]]:
    num_boards = len(dataset.entries)
    if num_boards <= 1:
        return list(range(len(dataset))), []

    val_boards = int(num_boards * val_ratio)
    if val_boards == 0:
        val_boards = 1
    if val_boards >= num_boards:
        val_boards = num_boards - 1

    generator = torch.Generator().manual_seed(42)
    board_perm = torch.randperm(num_boards, generator=generator).tolist()
    val_board_ids = set(board_perm[:val_boards])

    train_indices: list[int] = []
    val_indices: list[int] = []
    for square_dataset_idx, (entry_idx, _) in enumerate(dataset.index_map):
        if entry_idx in val_board_ids:
            val_indices.append(square_dataset_idx)
        else:
            train_indices.append(square_dataset_idx)

    return train_indices, val_indices


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
) -> list[dict[str, Any]]:
    """Treina o classificador de peças.

    `splits_path` aponta para o arquivo de splits persistido (`data/splits.csv`). Quando
    informado, o treino usa **apenas** o split `train` e valida no split `val`; o split
    `test` fica reservado e nunca é visto. Sem ele, cai no comportamento antigo de
    sortear a validação a cada execução -- que contamina a métrica ao longo do tempo
    (ver ANALISE.md §3.4 e S-07).

    `fresh=True` ignora o checkpoint existente e treina do zero. Necessário para
    produzir uma medição de generalização confiável: retomar um checkpoint que já viu o
    split de teste invalida a avaliação.
    """
    splits_map = load_splits(Path(splits_path)) if splits_path is not None else None

    if splits_map:
        dataset = BoardFenDataset(Path(csv_path), Path(samples_dir), split="train", splits=splits_map)
        val_dataset: BoardFenDataset | None = BoardFenDataset(
            Path(csv_path), Path(samples_dir), split="val", splits=splits_map
        )
        logger.info(
            "Split persistido em uso: %d tabuleiros de treino, %d de validação. Teste reservado.",
            len(dataset.entries),
            len(val_dataset.entries) if val_dataset else 0,
        )
    else:
        dataset = BoardFenDataset(Path(csv_path), Path(samples_dir))
        val_dataset = None
        logger.warning(
            "Sem arquivo de splits: a validação será sorteada e mudará quando o dataset crescer. "
            "Passe splits_path para uma métrica estável (S-07)."
        )

    if len(dataset) == 0:
        raise ValueError("Dataset vazio. Salve exemplos corrigidos antes de treinar.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = PieceClassifier().to(device)
    if fresh:
        logger.info("Treinando do zero (--fresh): checkpoint existente será ignorado.")
    elif Path(model_path).exists():
        model.load_state_dict(load_state_dict(Path(model_path), map_location=device), strict=False)
        logger.info("Retomando treino a partir de %s.", model_path)
        # O checkpoint nao guarda a val_loss com que foi salvo (pendencia da S-27), entao
        # `best_val_loss` recomeca em infinito: a primeira epoca sempre grava, mesmo se for
        # pior que o que estava no disco. Avisar e o minimo enquanto isso nao muda.
        logger.warning(
            "Retomar zera o controle de melhor época: a primeira época vai sobrescrever %s "
            "mesmo se tiver val_loss pior. Faça uma cópia antes se o checkpoint atual importa.",
            Path(model_path).name,
        )

    logger.info("Treinando em %s com %d tabuleiros (%d casas).", device, len(dataset.entries), len(dataset))
    if val_dataset is not None:
        train_indices = list(range(len(dataset)))
        val_indices = list(range(len(val_dataset)))
    else:
        train_indices, val_indices = _split_square_indices_by_board(dataset, val_ratio=val_ratio)

    train_transform = v2.Compose([
        v2.RandomApply([v2.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0))], p=0.3),
        v2.ColorJitter(brightness=0.3, contrast=0.3),
        v2.RandomAffine(degrees=2, translate=(0.05, 0.05), scale=(0.95, 1.05)),
        v2.Lambda(lambda x: torch.clamp(x, 0.0, 1.0))
    ])

    train_ds = TransformSubset(Subset(dataset, train_indices), transform=train_transform)

    # Com split persistido, a validacao vem de um dataset separado; sem ele, e um
    # subconjunto do mesmo dataset. Indexar o dataset errado aqui inverteria a metrica.
    val_source = val_dataset if val_dataset is not None else dataset
    val_ds: Subset | None = Subset(val_source, val_indices) if val_indices else None
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False) if val_ds is not None else None

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    history: list[dict[str, Any]] = []
    best_val_loss = float("inf")
    epochs_no_improve = 0

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        train_acc = 0.0

        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()

            train_loss += float(loss.item()) * xb.size(0)
            train_acc += _accuracy(logits, yb) * xb.size(0)

        train_loss /= len(train_ds)
        train_acc /= len(train_ds)

        row: dict[str, Any] = {
            "epoch": epoch,
            "total_epochs": epochs,
            "train_loss": train_loss,
            "train_acc": train_acc,
        }

        model.eval()
        if val_loader is not None and val_ds is not None:
            val_loss = 0.0
            val_acc = 0.0
            with torch.no_grad():
                for xb, yb in val_loader:
                    xb, yb = xb.to(device), yb.to(device)
                    logits = model(xb)
                    loss = criterion(logits, yb)
                    val_loss += float(loss.item()) * xb.size(0)
                    val_acc += _accuracy(logits, yb) * xb.size(0)

            val_loss /= len(val_ds)
            val_acc /= len(val_ds)
            row["val_loss"] = val_loss
            row["val_acc"] = val_acc

            metric_for_best = val_loss
        else:
            metric_for_best = train_loss

        if metric_for_best < best_val_loss:
            best_val_loss = metric_for_best
            epochs_no_improve = 0
            Path(model_path).parent.mkdir(parents=True, exist_ok=True)
            torch.save({"model_state": model.state_dict()}, model_path)
        else:
            epochs_no_improve += 1

        history.append(row)
        if progress_cb is not None:
            progress_cb(row)

        if patience > 0 and epochs_no_improve >= patience:
            logger.info(
                "Parada antecipada: sem melhora por %d epocas. Interrompendo na epoca %d.",
                patience,
                epoch,
            )
            break

    return history
