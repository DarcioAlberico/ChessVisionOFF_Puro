from __future__ import annotations

import logging
import warnings
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset, Sampler

from .config import BOARD_SIZE, BOARDS_PER_CHUNK, DEFAULT_BOARD_CACHE_SIZE
from .fen_utils import check_position, is_syntactically_valid_fen, labels_from_fen
from .labels import LABEL_COLUMNS, DatasetEntry, LabelStore
from .model import DEFAULT_ARCH, ArchConfig, preprocess_cell_to_tensor, with_coordinate_channels
from .semantics import infer_side_to_move
from .splits import Split

logger = logging.getLogger(__name__)

__all__ = [
    "LABEL_COLUMNS",
    "BoardFenDataset",
    "BoardGroupedSampler",
    "BoardUnitDataset",
    "DatasetEntry",
    "append_training_sample",
    "board_groups",
    "migrate_labels_csv",
]
"""`LABEL_COLUMNS` e `DatasetEntry` moraram aqui até a S-51 e agora moram em `labels.py`.
Reexportados porque o nome deste módulo continua sendo o lugar onde se procura por eles, e
porque quebrar o import de quem já os usava não compraria nada."""


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
        self.skipped_without_split: list[str] = []
        """Rótulos descartados por não terem split registrado (S-56).

        Não é o mesmo que "de outro split": é "de split nenhum", e significa que a amostra
        está invisível a **todos** os três datasets. Separá-los é o que permite avisar."""
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

        missing_files: list[str] = []
        for entry in LabelStore(self.csv_path).read():
            fen = entry.fen
            if not fen or not is_syntactically_valid_fen(fen):
                continue

            filename = entry.filename

            if self.split is not None:
                if self.splits is None:
                    raise ValueError("Para filtrar por split é necessário informar o mapa `splits`.")
                registrado = self.splits.get(filename)
                if registrado is None:
                    self.skipped_without_split.append(filename)
                    continue
                if registrado != self.split:
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
            self.entries.append(entry)

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

        if self.skipped_without_split:
            # Este aviso é a metade barata da S-56. O descarte em si está certo -- amostra sem
            # split não pode entrar por acidente no conjunto de teste --, mas ele era mudo, e
            # foi assim que 45 amostras ficaram fora do treino sem que nada dissesse. Quem
            # atribui o split é `training.resolve_splits`; quem grita quando ninguém atribuiu
            # é isto.
            logger.warning(
                "%d rótulo(s) ignorados por não terem split registrado em data/splits.csv, e "
                "portanto invisíveis a este treino. Rode `cvoff-train` (que atribui) ou "
                "`cvoff-audit` para vê-los. Primeiros casos: %s",
                len(self.skipped_without_split),
                ", ".join(self.skipped_without_split[:3]),
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

    def square(self, entry_idx: int, square_idx: int, transform: Callable | None) -> tuple[torch.Tensor, int]:
        """Uma casa preprocessada e o seu rótulo, com o aumento que quem chama pedir.

        Separado de `__getitem__` porque o `BoardUnitDataset` da S-62b precisa exatamente
        disto -- o mesmo corte, o mesmo cache e a mesma ordem de canais -- mas com o aumento
        vindo dele, e não do atributo deste objeto. Sem a separação ele teria de reimplementar
        o corte, e o dia em que os dois divergissem o treino por tabuleiro passaria a ver uma
        imagem diferente da que a inferência monta, em silêncio.
        """
        board = self._load_board(entry_idx)
        labels = self._labels(entry_idx)

        row = square_idx // 8
        col = square_idx % 8
        step = BOARD_SIZE // 8
        y0, y1 = row * step, (row + 1) * step
        x0, x1 = col * step, (col + 1) * step

        x = preprocess_cell_to_tensor(board[y0:y1, x0:x1], self.arch)
        if transform is not None:
            x = transform(x)
        # Depois do aumento, de proposito: ver `with_coordinate_channels` (S-62a).
        return with_coordinate_channels(x, square_idx, self.arch), labels[square_idx]

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        entry_idx, square_idx = self.index_map[idx]
        return self.square(entry_idx, square_idx, self.transform)


class BoardUnitDataset(Dataset):
    """O tabuleiro como unidade de amostragem, para a cabeça da S-62b.

    Devolve `(64, C, S, S)` e `(64,)` -- as 64 casas de um tabuleiro, em ordem de leitura.
    Não substitui o `BoardFenDataset`: **envolve** o mesmo objeto, com o mesmo cache de
    imagem, os mesmos rótulos e os mesmos descartes. O que muda é só o que conta como um item.

    **O aumento roda por casa, e não sobre o bloco.** Aplicar o `Compose` ao tensor
    `(64, C, S, S)` inteiro é uma linha mais curto e sorteia **um** conjunto de parâmetros
    para as 64 casas -- o mesmo desfoque, o mesmo brilho, a mesma hachura em todas. Isso é
    outro regime de aumento, e compará-lo com o da cabeça de hoje mediria duas mudanças de
    uma vez. O laço custa o que a honestidade da comparação vale.

    `board_indices` restringe a quais tabuleiros do dataset base este expõe -- é como o treino
    e a validação se separam quando não há arquivo de splits.
    """

    def __init__(
        self,
        base: BoardFenDataset,
        board_indices: Sequence[int] | None = None,
        transform: Callable | None = None,
    ) -> None:
        self.base = base
        self.transform = transform
        self.board_indices = list(range(len(base.entries)) if board_indices is None else board_indices)

    def __len__(self) -> int:
        return len(self.board_indices)

    @property
    def entries(self) -> list[DatasetEntry]:
        """Os tabuleiros que este dataset expõe, na ordem em que os expõe."""
        return [self.base.entries[i] for i in self.board_indices]

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        board_idx = self.board_indices[idx]
        # Por `base.square` de proposito: o cache, o corte e a ordem dos canais da S-62a tem
        # de ser exatamente os mesmos que a cabeca de hoje recebe.
        pares = [self.base.square(board_idx, square_idx, self.transform) for square_idx in range(64)]
        return torch.stack([x for x, _ in pares]), torch.tensor([y for _, y in pares], dtype=torch.long)


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

    timestamp = datetime.now(timezone.utc)
    filename = f"board_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.png"
    image_path = samples_dir / filename

    board = board_rgb
    if board.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
        board = cv2.resize(board, (BOARD_SIZE, BOARD_SIZE))
    board_bgr = cv2.cvtColor(board, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(image_path), board_bgr)

    LabelStore(csv_path).append(
        DatasetEntry(
            filename=filename,
            fen=fen,
            side_to_move=resolved_side,
            source_pdf=source_pdf,
            source_page=str(source_page),
            source_diagram=str(source_diagram),
            detection_source=detection_source,
            created_at=timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            corrected_by=corrected_by,
        )
    )
    return image_path


def migrate_labels_csv(csv_path: Path, *, backup: bool = True, infer_side: bool = True) -> dict[str, int]:
    """Leva um `labels.csv` antigo para o esquema da S-19, preenchendo o que é dedutível.

    O único campo que dá para recuperar de um rótulo já gravado é o lado a jogar, e só nos
    casos em que a posição o impõe (S-17): a origem -- de que PDF e de que página a amostra
    veio -- foi perdida na gravação e nenhuma migração a inventa. Fica vazia, que é o que
    ela é.

    Devolve a contagem do que mudou, para o CLI poder dizer o que fez em vez de só "ok".
    """
    store = LabelStore(csv_path)
    if not store.exists():
        raise FileNotFoundError(f"CSV de rótulos não encontrado: {csv_path}")

    rows = store.read_rows()
    if backup:
        store.backup()

    counters = {"total": len(rows), "ja_tinha": 0, "inferido": 0, "sem_resposta": 0}
    for row in rows:
        parts = row.get("fen", "").split()
        if len(parts) > 1 and parts[1] in ("w", "b"):
            counters["ja_tinha"] += 1
            lado = parts[1]
        elif not infer_side:
            counters["sem_resposta"] += 1
            lado = ""
        else:
            decision = infer_side_to_move(parts[0] if parts else "")
            if decision.source == "legality":
                counters["inferido"] += 1
                lado = "w" if decision.color else "b"
            else:
                # Padrao nao e resposta: gravar "w" aqui seria repetir exatamente o erro que
                # a S-19 existe para corrigir, so que agora com aparencia de dado conferido.
                counters["sem_resposta"] += 1
                lado = ""

        # O que ja estava na coluna vence o vazio, e nunca o contrario: a migracao preenche
        # o que falta e nao reinterpreta o que alguem ja respondeu.
        row["side_to_move"] = lado or row.get("side_to_move", "")

    store.rewrite(rows)
    return counters
