from __future__ import annotations

import logging
import os
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from .atomic_io import atomic_write_bytes
from .config import BOARD_SIZE
from .fen_utils import check_position, is_syntactically_valid_fen, labels_from_fen
from .model import preprocess_cell_to_tensor
from .semantics import infer_side_to_move
from .splits import Split

logger = logging.getLogger(__name__)


def _cell(row: object, column: str) -> str:
    """Valor textual de uma coluna opcional. Coluna ausente ou `NaN` viram string vazia.

    O `NaN` não é hipótese acadêmica: é o que o pandas entrega para célula vazia, e foi ele
    que derrubou o carregamento inteiro do dataset antes da Fase 0.
    """
    value = getattr(row, column, "")
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


LABEL_COLUMNS: tuple[str, ...] = (
    "filename",
    "fen",
    "side_to_move",
    "source_pdf",
    "source_page",
    "source_diagram",
    "detection_source",
    "created_at",
    "corrected_by",
)
"""Esquema do `labels.csv` a partir da S-19. Só `filename` e `fen` são obrigatórios.

O esquema antigo (`filename,fen`) continua carregando: coluna ausente vira valor vazio. São
3.195 rótulos existentes, e quebrá-los para ganhar colunas seria o pior negócio possível.

`side_to_move` é o campo que motivou o resto. Sem ele o dataset perde a única informação
que o PDF dava de graça e que a imagem do tabuleiro não contém -- e foi essa perda que fez
`_normalize_fen` completar 3.244 rótulos com `w` fixo. As colunas de origem (`source_*`)
existem para o que a Fase 1 já pediu e não pôde fazer: agrupar o split por livro (S-07),
auditar por fonte e voltar ao PDF para recortar de novo.
"""


@dataclass(frozen=True)
class DatasetEntry:
    filename: str
    fen: str
    side_to_move: str = ""
    """`w`, `b` ou vazio. Redundante com a FEN de propósito -- ver `resolved_side_to_move`."""

    source_pdf: str = ""
    source_page: str = ""
    source_diagram: str = ""
    detection_source: str = ""
    created_at: str = ""
    corrected_by: str = ""

    @property
    def resolved_side_to_move(self) -> str:
        """A coluna manda; a FEN é o reserva.

        As duas são escritas juntas e não deviam divergir, mas a coluna carrega o que a
        legenda do PDF disse -- que numa posição legal dos dois jeitos é informação que a
        FEN sozinha não tem como recuperar. Se um dia divergirem, a mais informativa vence.
        """
        if self.side_to_move in ("w", "b"):
            return self.side_to_move
        parts = self.fen.split()
        return parts[1] if len(parts) > 1 and parts[1] in ("w", "b") else ""


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
            self.entries.append(
                DatasetEntry(
                    filename=filename,
                    fen=fen,
                    **{column: _cell(row, column) for column in LABEL_COLUMNS[2:]},
                )
            )

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


def _fen_with_side(fen: str, side_to_move: str | None) -> tuple[str, str]:
    """Casa a FEN e a coluna de lado a jogar, para que não haja duas verdades no arquivo."""
    fen = str(fen).strip()
    parts = fen.split()
    declared = side_to_move if side_to_move in ("w", "b") else None
    if declared is None:
        return fen, parts[1] if len(parts) > 1 and parts[1] in ("w", "b") else ""

    if len(parts) > 1:
        parts[1] = declared
        return " ".join(parts), declared
    return f"{parts[0]} {declared} - - 0 1", declared


def append_training_sample(
    board_rgb: np.ndarray,
    fen: str,
    csv_path: Path,
    samples_dir: Path,
    *,
    allow_illegal: bool = False,
    side_to_move: str | None = None,
    source_pdf: str = "",
    source_page: int | str = "",
    source_diagram: int | str = "",
    detection_source: str = "",
    corrected_by: str = "",
) -> Path:
    """Grava uma amostra rotulada (imagem + linha no CSV), no esquema da S-19.

    Rejeita posições fatalmente ilegais: gravá-las como verdade ensina o modelo a
    reproduzir o erro. Posições apenas com o lado a jogar invertido são aceitas.
    `allow_illegal=True` contorna a checagem, para casos deliberados.

    Os campos de origem são todos opcionais e default vazio: quem grava um tabuleiro
    montado à mão não tem PDF nem página para informar, e exigir isso quebraria o fluxo
    que existe hoje.
    """
    if not is_syntactically_valid_fen(fen):
        raise ValueError("FEN inválida: não foi possível interpretar a notação.")

    fen, resolved_side = _fen_with_side(fen, side_to_move)

    if not allow_illegal:
        position = check_position(fen)
        if position.is_fatal:
            raise ValueError("Posição ilegal, não pode ser salva como rótulo: " + "; ".join(position.problems))

    csv_path = Path(csv_path)
    samples_dir = Path(samples_dir)
    samples_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = pd.Timestamp.utcnow()
    filename = f"board_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.png"
    image_path = samples_dir / filename

    board = board_rgb
    if board.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
        board = cv2.resize(board, (BOARD_SIZE, BOARD_SIZE))
    board_bgr = cv2.cvtColor(board, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(image_path), board_bgr)

    new_row = pd.DataFrame(
        [
            {
                "filename": filename,
                "fen": fen,
                "side_to_move": resolved_side,
                "source_pdf": source_pdf,
                "source_page": str(source_page),
                "source_diagram": str(source_diagram),
                "detection_source": detection_source,
                "created_at": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "corrected_by": corrected_by,
            }
        ]
    )
    if csv_path.exists():
        existing = pd.read_csv(csv_path)
        combined = pd.concat([existing, new_row], ignore_index=True)
    else:
        combined = new_row
    _write_labels(combined, csv_path)
    return image_path


def _write_labels(frame: pd.DataFrame, csv_path: Path) -> None:
    """Grava o CSV com as colunas da S-19 na ordem, sem `NaN` e sem perder coluna extra.

    Escrita atômica (S-25): este arquivo é o dataset inteiro, 3.195 rótulos de trabalho
    humano acumulado. `to_csv` direto no destino trunca antes de escrever -- e a UI de
    dataset da S-23 passa a regravá-lo a cada correção, o que multiplica as chances de
    apanhar a janela ruim.
    """
    for column in LABEL_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    extra = [column for column in frame.columns if column not in LABEL_COLUMNS]
    frame = frame[[*LABEL_COLUMNS, *extra]].fillna("")
    payload = frame.to_csv(index=False, lineterminator=os.linesep)
    atomic_write_bytes(Path(csv_path), payload.encode("utf-8"))


def migrate_labels_csv(csv_path: Path, *, backup: bool = True, infer_side: bool = True) -> dict[str, int]:
    """Leva um `labels.csv` antigo para o esquema da S-19, preenchendo o que é dedutível.

    O único campo que dá para recuperar de um rótulo já gravado é o lado a jogar, e só nos
    casos em que a posição o impõe (S-17): a origem -- de que PDF e de que página a amostra
    veio -- foi perdida na gravação e nenhuma migração a inventa. Fica vazia, que é o que
    ela é.

    Devolve a contagem do que mudou, para o CLI poder dizer o que fez em vez de só "ok".
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV de rótulos não encontrado: {csv_path}")

    frame = pd.read_csv(csv_path)
    if "fen" not in frame.columns or "filename" not in frame.columns:
        raise ValueError("CSV de rótulos precisa ter ao menos as colunas `filename` e `fen`.")

    if backup:
        stamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = csv_path.with_suffix(f"{csv_path.suffix}.bak-{stamp}")
        backup_path.write_bytes(csv_path.read_bytes())
        logger.info("Backup do CSV de rótulos em %s", backup_path)

    counters = {"total": len(frame), "ja_tinha": 0, "inferido": 0, "sem_resposta": 0}
    sides: list[str] = []
    for raw in frame["fen"].astype(str):
        parts = raw.strip().split()
        if len(parts) > 1 and parts[1] in ("w", "b"):
            counters["ja_tinha"] += 1
            sides.append(parts[1])
            continue
        if not infer_side:
            counters["sem_resposta"] += 1
            sides.append("")
            continue

        decision = infer_side_to_move(parts[0])
        if decision.source == "legality":
            counters["inferido"] += 1
            sides.append("w" if decision.color else "b")
        else:
            # Padrao nao e resposta: gravar "w" aqui seria repetir exatamente o erro que a
            # S-19 existe para corrigir, so que agora com aparencia de dado conferido.
            counters["sem_resposta"] += 1
            sides.append("")

    if "side_to_move" in frame.columns:
        existing_side = frame["side_to_move"].fillna("").astype(str)
        sides = [current or previous for current, previous in zip(sides, existing_side, strict=True)]
    frame["side_to_move"] = sides

    _write_labels(frame, csv_path)
    return counters
