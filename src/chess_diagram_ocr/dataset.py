from __future__ import annotations

import logging
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from .config import BOARD_SIZE
from .fen_utils import check_position, is_syntactically_valid_fen, labels_from_fen
from .model import preprocess_cell_to_tensor
from .splits import Split

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasetEntry:
    filename: str
    fen: str


class BoardFenDataset(Dataset):
    def __init__(
        self,
        csv_path: Path,
        samples_dir: Path,
        transform: Callable | None = None,
        *,
        skip_illegal: bool = True,
        split: Split | None = None,
        splits: Mapping[str, Split] | None = None,
    ) -> None:
        """Dataset de casas de tabuleiro a partir de rótulos FEN.

        `skip_illegal` descarta rótulos que violam regras independentes do lado a jogar
        (rei faltando, peças demais, peão na primeira fila). Esses rótulos são erros de
        anotação e, se treinados, ensinam o modelo a reproduzi-los. Rótulos apenas com
        o lado a jogar invertido são mantidos: a informação de peças neles está correta.

        `split` restringe o dataset a uma partição, usando o mapa `splits` (normalmente
        vindo de `splits.ensure_splits`). Amostras sem split registrado são ignoradas,
        para que uma amostra nova nunca entre por acidente no conjunto de teste.
        """
        self.csv_path = Path(csv_path)
        self.samples_dir = Path(samples_dir)
        self.transform = transform
        self.skip_illegal = skip_illegal
        self.split = split
        self.splits = splits
        self.entries: list[DatasetEntry] = []
        self.index_map: list[tuple[int, int]] = []
        self.skipped_illegal: list[tuple[str, tuple[str, ...]]] = []
        self._board_cache: dict[int, np.ndarray] = {}
        self._labels_cache: dict[int, list[int]] = {}
        self._load_entries()

    def _load_entries(self) -> None:
        if not self.csv_path.exists():
            return

        df = pd.read_csv(self.csv_path)
        required_cols = {"filename", "fen"}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"Dataset CSV must have columns {required_cols}")

        missing_files: list[str] = []
        for row in df.itertuples(index=False):
            # Celula vazia no CSV chega como NaN (float): coagir antes de validar.
            fen = str(row.fen).strip()
            if not fen or fen.lower() == "nan" or not is_syntactically_valid_fen(fen):
                continue

            filename = str(row.filename).strip()

            if self.split is not None:
                if self.splits is None:
                    raise ValueError("Para filtrar por split é necessário informar o mapa `splits`.")
                if self.splits.get(filename) != self.split:
                    continue

            if self.skip_illegal:
                position = check_position(fen)
                if position.is_fatal:
                    self.skipped_illegal.append((filename, position.problems))
                    continue

            img_path = self.samples_dir / filename
            if not img_path.exists():
                missing_files.append(filename)
                continue
            self.entries.append(DatasetEntry(filename=filename, fen=fen))

        if missing_files:
            preview = ", ".join(sorted(set(missing_files))[:3])
            suffix = "..." if len(set(missing_files)) > 3 else ""
            warnings.warn(
                f"{len(missing_files)} linhas ignoradas por imagem ausente: {preview}{suffix}",
                RuntimeWarning,
                stacklevel=2,
            )

        if self.skipped_illegal:
            logger.warning(
                "%d rótulos ignorados por posição ilegal. Rode `cvoff-audit` para revisá-los. "
                "Primeiros casos: %s",
                len(self.skipped_illegal),
                "; ".join(f"{name} ({', '.join(problems)})" for name, problems in self.skipped_illegal[:3]),
            )

        self.index_map = [(entry_idx, sq) for entry_idx in range(len(self.entries)) for sq in range(64)]

    def __len__(self) -> int:
        return len(self.index_map)

    def _load_board(self, entry_idx: int) -> np.ndarray:
        cached = self._board_cache.get(entry_idx)
        if cached is not None:
            return cached

        entry = self.entries[entry_idx]
        img_path = self.samples_dir / entry.filename
        board = cv2.imread(str(img_path))
        if board is None:
            raise FileNotFoundError(f"Could not read board image: {img_path}")
        board = cv2.cvtColor(board, cv2.COLOR_BGR2RGB)
        if board.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
            board = cv2.resize(board, (BOARD_SIZE, BOARD_SIZE))
        self._board_cache[entry_idx] = board
        return board

    def _labels(self, entry_idx: int) -> list[int]:
        cached = self._labels_cache.get(entry_idx)
        if cached is not None:
            return cached
        labels = labels_from_fen(self.entries[entry_idx].fen)
        self._labels_cache[entry_idx] = labels
        return labels

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        entry_idx, square_idx = self.index_map[idx]
        board = self._load_board(entry_idx)
        labels = self._labels(entry_idx)

        row = square_idx // 8
        col = square_idx % 8
        step = BOARD_SIZE // 8
        y0, y1 = row * step, (row + 1) * step
        x0, x1 = col * step, (col + 1) * step

        cell = board[y0:y1, x0:x1]
        x = preprocess_cell_to_tensor(cell)
        if self.transform is not None:
            x = self.transform(x)
        y = labels[square_idx]
        return x, y


def append_training_sample(
    board_rgb: np.ndarray,
    fen: str,
    csv_path: Path,
    samples_dir: Path,
    *,
    allow_illegal: bool = False,
) -> Path:
    """Grava uma amostra rotulada (imagem + linha no CSV).

    Rejeita posições fatalmente ilegais: gravá-las como verdade ensina o modelo a
    reproduzir o erro. Posições apenas com o lado a jogar invertido são aceitas.
    `allow_illegal=True` contorna a checagem, para casos deliberados.
    """
    if not is_syntactically_valid_fen(fen):
        raise ValueError("FEN inválida: não foi possível interpretar a notação.")

    if not allow_illegal:
        position = check_position(fen)
        if position.is_fatal:
            raise ValueError("Posição ilegal, não pode ser salva como rótulo: " + "; ".join(position.problems))

    csv_path = Path(csv_path)
    samples_dir = Path(samples_dir)
    samples_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    sample_id = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"board_{sample_id}.png"
    image_path = samples_dir / filename

    board = board_rgb
    if board.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
        board = cv2.resize(board, (BOARD_SIZE, BOARD_SIZE))
    board_bgr = cv2.cvtColor(board, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(image_path), board_bgr)

    new_row = pd.DataFrame([{"filename": filename, "fen": fen.strip()}])
    if csv_path.exists():
        existing = pd.read_csv(csv_path)
        combined = pd.concat([existing, new_row], ignore_index=True)
    else:
        combined = new_row
    combined.to_csv(csv_path, index=False)
    return image_path
