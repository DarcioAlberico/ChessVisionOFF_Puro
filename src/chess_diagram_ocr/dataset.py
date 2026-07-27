from __future__ import annotations

import logging
import os
import warnings
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, Sampler

from .atomic_io import atomic_write_bytes
from .config import BOARD_SIZE, BOARDS_PER_CHUNK, DEFAULT_BOARD_CACHE_SIZE
from .fen_utils import check_position, is_syntactically_valid_fen, labels_from_fen
from .model import DEFAULT_ARCH, ArchConfig, preprocess_cell_to_tensor
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
        cache_size: int = DEFAULT_BOARD_CACHE_SIZE,
        arch: ArchConfig = DEFAULT_ARCH,
    ) -> None:
        """Dataset de casas de tabuleiro a partir de rótulos FEN.

        `skip_illegal` descarta rótulos que violam regras independentes do lado a jogar
        (rei faltando, peças demais, peão na primeira fila). Esses rótulos são erros de
        anotação e, se treinados, ensinam o modelo a reproduzi-los. Rótulos apenas com
        o lado a jogar invertido são mantidos: a informação de peças neles está correta.

        `split` restringe o dataset a uma partição, usando o mapa `splits` (normalmente
        vindo de `splits.ensure_splits`). Amostras sem split registrado são ignoradas,
        para que uma amostra nova nunca entre por acidente no conjunto de teste.

        `cache_size` limita quantos tabuleiros 800×800×3 ficam residentes (S-26). Antes
        o cache era um dict sem teto: como `index_map` percorre as 64 casas de cada
        tabuleiro, uma época carregava **todos** -- 5,99 GiB de RSS medidos com os 3.208
        rótulos de hoje, e crescendo com o dataset. `0` desliga o cache (relê a cada
        casa: correto, mas 64× mais leitura de disco).

        O teto só é barato porque o acesso deixou de ser aleatório: com
        `BoardGroupedSampler` as casas do mesmo tabuleiro saem na mesma janela, então um
        cache pequeno tem taxa de acerto alta. Com `shuffle=True` puro no `DataLoader`,
        um cache limitado vira quase só falta -- os dois itens da S-26 são um só.
        """
        self.csv_path = Path(csv_path)
        self.samples_dir = Path(samples_dir)
        self.transform = transform
        self.skip_illegal = skip_illegal
        self.split = split
        self.splits = splits
        self.cache_size = max(0, int(cache_size))
        self.arch = arch
        self.entries: list[DatasetEntry] = []
        self.index_map: list[tuple[int, int]] = []
        self.skipped_illegal: list[tuple[str, tuple[str, ...]]] = []
        self._board_cache: OrderedDict[int, np.ndarray] = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0
        # Os rótulos ficam sem teto de propósito: são 64 inteiros por tabuleiro (~6 MB no
        # dataset inteiro) contra 1,83 MiB por tabuleiro de imagem. Limitá-los pagaria
        # complexidade para economizar 0,1% do que a S-26 mede.
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
            self.cache_hits += 1
            self._board_cache.move_to_end(entry_idx)
            return cached

        self.cache_misses += 1
        entry = self.entries[entry_idx]
        img_path = self.samples_dir / entry.filename
        board = cv2.imread(str(img_path))
        if board is None:
            raise FileNotFoundError(f"Could not read board image: {img_path}")
        board = cv2.cvtColor(board, cv2.COLOR_BGR2RGB)
        if board.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
            board = cv2.resize(board, (BOARD_SIZE, BOARD_SIZE))

        if self.cache_size:
            self._board_cache[entry_idx] = board
            while len(self._board_cache) > self.cache_size:
                self._board_cache.popitem(last=False)
        return board

    @property
    def cache_hit_rate(self) -> float:
        """Fração de acessos servidos pelo cache. Mede se o amostrador está fazendo efeito."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0

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
        x = preprocess_cell_to_tensor(cell, self.arch)
        if self.transform is not None:
            x = self.transform(x)
        y = labels[square_idx]
        return x, y


def board_groups(
    index_map: Sequence[tuple[int, int]],
    dataset_indices: Sequence[int] | None = None,
) -> list[list[int]]:
    """Agrupa posições do amostrador pelas casas do mesmo tabuleiro.

    `dataset_indices` é a lista de índices do dataset que o wrapper (`Subset`) expõe, na
    ordem em que ele os expõe; o retorno vem em coordenadas do **wrapper**. Sem ela, o
    dataset é usado direto. Essa indireção existe porque o treino nem sempre entrega o
    dataset cru ao `DataLoader`: com validação sorteada ele entrega um `Subset`, e um
    amostrador que devolvesse índices do dataset apontaria para as casas erradas.

    Os grupos saem em ordem de tabuleiro (dict preserva inserção), então duas execuções
    com a mesma semente produzem a mesma sequência.
    """
    indices = range(len(index_map)) if dataset_indices is None else dataset_indices
    groups: dict[int, list[int]] = {}
    for position, dataset_index in enumerate(indices):
        groups.setdefault(index_map[dataset_index][0], []).append(position)
    return list(groups.values())


class BoardGroupedSampler(Sampler[int]):
    """Embaralha por tabuleiro, não por casa (item 2 da S-26).

    O `shuffle=True` do `DataLoader` sorteia as 205.312 casas independentemente, então
    duas casas do mesmo tabuleiro caem em pontos arbitrários da época e qualquer cache
    com teto vira quase só falta -- é por isso que o cache de antes não tinha teto. Aqui
    a época é percorrida em janelas de `boards_per_chunk` tabuleiros: dentro da janela as
    casas são embaralhadas normalmente, mas o conjunto de trabalho do cache passa a ser a
    janela e não o dataset.

    **Por que a janela e não um tabuleiro por vez.** A leitura literal da S-26 ("as 64
    casas do mesmo tabuleiro no mesmo lote") daria, com `batch_size=128`, lotes de 2
    tabuleiros. Isso resolve o cache e cria outro problema: um lote com a estatística de
    2 posições deixa o BatchNorm ruidoso e muda a dinâmica do treino por um motivo que
    não tem nada a ver com memória. A janela de 64 tabuleiros mantém a localidade (117
    MiB residentes) e devolve a mistura.

    **Com `num_workers > 0` cada processo tem o próprio cache** e recebe um lote a cada
    `num_workers`, então todos tocam todos os tabuleiros da janela: a leitura de disco é
    multiplicada pelo número de workers. Medido, o disco é ~7% da época, então essa
    amplificação é aceitável; alinhar janela e worker exigiria acoplar o amostrador ao
    `num_workers` e degradaria em silêncio se o `DataLoader` mudasse a distribuição.
    """

    def __init__(
        self,
        groups: Iterable[Iterable[int]],
        *,
        shuffle: bool = True,
        seed: int = 42,
        boards_per_chunk: int = BOARDS_PER_CHUNK,
    ) -> None:
        self.groups = [list(group) for group in groups]
        self.shuffle = shuffle
        self.seed = seed
        self.boards_per_chunk = max(1, int(boards_per_chunk))
        self.epoch = 0

    def set_epoch(self, epoch: int) -> None:
        """Fixa a época usada na semente. O padrão é incrementar a cada iteração."""
        self.epoch = epoch

    def __len__(self) -> int:
        return sum(len(group) for group in self.groups)

    def __iter__(self) -> Iterator[int]:
        if not self.shuffle:
            for group in self.groups:
                yield from group
            return

        generator = torch.Generator().manual_seed(self.seed + self.epoch)
        board_order = torch.randperm(len(self.groups), generator=generator).tolist()
        self.epoch += 1

        for start in range(0, len(board_order), self.boards_per_chunk):
            window = [position for board in board_order[start : start + self.boards_per_chunk] for position in self.groups[board]]
            inner = torch.randperm(len(window), generator=generator).tolist()
            for offset in inner:
                yield window[offset]


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
