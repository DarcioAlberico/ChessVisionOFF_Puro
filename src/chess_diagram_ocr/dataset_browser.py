"""Listar, filtrar, recorrigir e remover amostras do dataset (S-23).

`labels.csv` é append-only desde o primeiro commit: a única forma de consertar um rótulo
era editar o CSV à mão -- e foi assim que os 100 rótulos ilegais que a Fase 1 encontrou
tiveram de ser tratados. Este módulo é a camada de dados por trás da aba "Dataset": ele não
sabe o que é Tkinter, e por isso dá para testá-lo.

Duas decisões que valem registro:

- **Remover apaga a linha; a imagem é opcional.** Uma amostra removida do CSV com a imagem
  preservada continua recuperável; o contrário, não. O padrão é manter o PNG e reportá-lo
  como órfão em `cvoff-audit`, que é onde ele já aparecia.
- **Quarentena em vez de exclusão para o que está ilegal.** É o mesmo caminho que
  `audit.quarantine_fatal_labels` já abriu, agora acessível por amostra: a linha sai do
  treino sem sair da existência, e volta pela UI quando alguém a corrigir.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from .atomic_io import atomic_write_bytes
from .config import PIECE_CLASSES
from .dataset import LABEL_COLUMNS, _write_labels
from .fen_utils import check_position, is_syntactically_valid_fen, labels_from_fen
from .splits import Split, load_splits

logger = logging.getLogger(__name__)

Legality = Literal["legal", "lado-a-jogar", "ilegal", "sintaxe"]

IMBALANCE_RATIO = 20.0
"""Quantas vezes a classe mais comum pode superar a mais rara antes de virar alerta."""


@dataclass(frozen=True)
class DatasetRow:
    """Uma amostra do dataset com tudo que a tabela precisa mostrar."""

    filename: str
    fen: str
    side_to_move: str
    source_pdf: str
    source_page: str
    source_diagram: str
    detection_source: str
    created_at: str
    corrected_by: str
    legality: Legality
    problems: tuple[str, ...]
    split: Split | None
    image_exists: bool
    duplicate_group: str = ""
    """Nome do representante do grupo de duplicatas, ou vazio se a amostra é única."""

    @property
    def placement(self) -> str:
        return self.fen.split(" ")[0]

    @property
    def is_duplicate(self) -> bool:
        return bool(self.duplicate_group) and self.duplicate_group != self.filename

    def image_path(self, samples_dir: Path) -> Path:
        return Path(samples_dir) / self.filename

    def classes_present(self) -> set[str]:
        return {char for char in self.placement if char.isalpha()}


def _legality_of(fen: str) -> tuple[Legality, tuple[str, ...]]:
    if not fen or fen.lower() == "nan" or not is_syntactically_valid_fen(fen):
        return "sintaxe", ("FEN vazia ou não interpretável",)
    check = check_position(fen)
    if check.is_fatal:
        return "ilegal", check.problems
    if not check.is_legal:
        return "lado-a-jogar", check.problems
    return "legal", ()


def load_rows(
    csv_path: Path,
    samples_dir: Path,
    *,
    splits_path: Path | None = None,
    duplicate_groups: Iterable[Sequence[str]] = (),
) -> list[DatasetRow]:
    """Lê o `labels.csv` inteiro para a tabela, sem carregar imagem nenhuma.

    A checagem de imagem é `exists()`, não leitura: 3.195 PNGs de 800×800 são 2,7 GB, e a
    tabela precisa abrir em menos de um segundo.
    """
    csv_path = Path(csv_path)
    samples_dir = Path(samples_dir)
    if not csv_path.exists():
        return []

    frame = pd.read_csv(csv_path).fillna("")
    if not {"filename", "fen"}.issubset(frame.columns):
        raise ValueError("O CSV precisa das colunas `filename` e `fen`.")

    splits = load_splits(splits_path) if splits_path is not None and Path(splits_path).exists() else {}

    group_of: dict[str, str] = {}
    for group in duplicate_groups:
        members = sorted(group)
        for member in members:
            group_of[member] = members[0]

    rows: list[DatasetRow] = []
    for record in frame.to_dict("records"):
        filename = str(record.get("filename", "")).strip()
        fen = str(record.get("fen", "")).strip()
        legality, problems = _legality_of(fen)
        rows.append(
            DatasetRow(
                filename=filename,
                fen=fen,
                side_to_move=str(record.get("side_to_move", "")).strip(),
                source_pdf=str(record.get("source_pdf", "")).strip(),
                source_page=str(record.get("source_page", "")).strip(),
                source_diagram=str(record.get("source_diagram", "")).strip(),
                detection_source=str(record.get("detection_source", "")).strip(),
                created_at=str(record.get("created_at", "")).strip(),
                corrected_by=str(record.get("corrected_by", "")).strip(),
                legality=legality,
                problems=problems,
                split=splits.get(filename),
                image_exists=(samples_dir / filename).exists() if filename else False,
                duplicate_group=group_of.get(filename, ""),
            )
        )
    return rows


def filter_rows(
    rows: Iterable[DatasetRow],
    *,
    query: str = "",
    legality: Legality | None = None,
    split: Split | None = None,
    source_pdf: str | None = None,
    has_classes: Collection[str] = (),
    only_duplicates: bool = False,
    only_missing_image: bool = False,
) -> list[DatasetRow]:
    """Aplica os filtros da S-23. Filtros vazios não filtram nada.

    `query` casa por substring, sem distinguir maiúsculas, contra nome do arquivo, FEN e
    livro de origem -- é o campo de busca único, que cobre "achar aquela amostra do Kemeri"
    sem obrigar o usuário a escolher em qual coluna procurar.
    """
    needle = query.strip().lower()
    wanted_classes = set(has_classes)

    result: list[DatasetRow] = []
    for row in rows:
        if legality is not None and row.legality != legality:
            continue
        if split is not None and row.split != split:
            continue
        if source_pdf and row.source_pdf != source_pdf:
            continue
        if only_duplicates and not row.is_duplicate:
            continue
        if only_missing_image and row.image_exists:
            continue
        if wanted_classes and not wanted_classes.issubset(row.classes_present()):
            continue
        if needle and needle not in f"{row.filename} {row.fen} {row.source_pdf}".lower():
            continue
        result.append(row)
    return result


def class_distribution(rows: Iterable[DatasetRow]) -> Counter[str]:
    """Contagem por classe **em casas**, que é a unidade em que o modelo aprende."""
    counts: Counter[str] = Counter()
    for row in rows:
        try:
            indices = labels_from_fen(row.fen)
        except (ValueError, IndexError):
            continue
        for index in indices:
            counts[PIECE_CLASSES[index]] += 1
    return counts


def split_distribution(rows: Iterable[DatasetRow]) -> Counter[str]:
    return Counter(row.split or "sem split" for row in rows)


def source_distribution(rows: Iterable[DatasetRow]) -> Counter[str]:
    return Counter(row.source_pdf or "origem não registrada" for row in rows)


def imbalance_alerts(counts: Counter[str], *, ratio: float = IMBALANCE_RATIO) -> list[str]:
    """Alertas de desbalanceamento entre as classes de peça.

    `empty` fica de fora da comparação: 77% das casas são vazias por construção do problema,
    e incluí-la faria o alerta disparar sempre, dizendo apenas o óbvio.
    """
    pieces = {name: value for name, value in counts.items() if name != "empty" and value > 0}
    if len(pieces) < 2:
        return ["Classes de peça insuficientes para avaliar desbalanceamento."]

    ausentes = [name for name in PIECE_CLASSES if name != "empty" and counts.get(name, 0) == 0]
    alerts: list[str] = []
    if ausentes:
        alerts.append(f"Classes sem nenhuma amostra: {', '.join(ausentes)}.")

    mais_comum = max(pieces.items(), key=lambda item: item[1])
    mais_rara = min(pieces.items(), key=lambda item: item[1])
    proporcao = mais_comum[1] / mais_rara[1]
    if proporcao > ratio:
        alerts.append(
            f"Desbalanceamento de {proporcao:.0f}x entre `{mais_comum[0]}` ({mais_comum[1]}) "
            f"e `{mais_rara[0]}` ({mais_rara[1]})."
        )
    return alerts


# ------------------------------------------------------------------------ escrita


def update_row(
    csv_path: Path,
    filename: str,
    *,
    fen: str,
    side_to_move: str | None = None,
    corrected_by: str = "ui",
    allow_illegal: bool = False,
) -> bool:
    """Regrava o rótulo de uma amostra. Devolve `False` se a amostra não existe no CSV.

    Recusa posição fatalmente ilegal pelo mesmo motivo de `append_training_sample`: gravá-la
    como verdade ensina o modelo a reproduzir o erro. `allow_illegal` existe para o caso
    deliberado -- e é o que a quarentena usa.
    """
    csv_path = Path(csv_path)
    if not is_syntactically_valid_fen(fen):
        raise ValueError("FEN inválida: não foi possível interpretar a notação.")

    placement = fen.split(" ")[0]
    side = side_to_move if side_to_move in ("w", "b") else None
    parts = fen.split()
    if side is not None:
        full_fen = f"{placement} {side} " + " ".join(parts[2:]) if len(parts) > 2 else f"{placement} {side} - - 0 1"
    else:
        full_fen = fen.strip()
        side = parts[1] if len(parts) > 1 and parts[1] in ("w", "b") else ""

    if not allow_illegal:
        check = check_position(full_fen)
        if check.is_fatal:
            raise ValueError("Posição ilegal, não pode ser salva como rótulo: " + "; ".join(check.problems))

    frame = pd.read_csv(csv_path).fillna("")
    mask = frame["filename"].astype(str).str.strip() == filename
    if not mask.any():
        return False

    frame.loc[mask, "fen"] = full_fen
    if "side_to_move" not in frame.columns:
        frame["side_to_move"] = ""
    frame.loc[mask, "side_to_move"] = side or ""
    if "corrected_by" not in frame.columns:
        frame["corrected_by"] = ""
    frame.loc[mask, "corrected_by"] = corrected_by

    _write_labels(frame, csv_path)
    logger.info("Rótulo de %s regravado como %s.", filename, full_fen)
    return True


def delete_rows(
    csv_path: Path,
    filenames: Collection[str],
    *,
    samples_dir: Path | None = None,
    delete_images: bool = False,
) -> int:
    """Remove linhas do CSV. Só apaga o PNG quando pedido explicitamente."""
    csv_path = Path(csv_path)
    wanted = {name.strip() for name in filenames if name.strip()}
    if not wanted:
        return 0

    frame = pd.read_csv(csv_path).fillna("")
    mask = frame["filename"].astype(str).str.strip().isin(wanted)
    removed = int(mask.sum())
    if not removed:
        return 0

    _write_labels(frame[~mask].copy(), csv_path)

    if delete_images and samples_dir is not None:
        for name in wanted:
            path = Path(samples_dir) / name
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Não foi possível apagar a imagem %s: %s", path, exc)

    logger.info("%d amostra(s) removidas do dataset.", removed)
    return removed


def quarantine_rows(
    csv_path: Path,
    filenames: Collection[str],
    quarantine_path: Path,
    *,
    reason: str = "quarentena pela UI",
) -> int:
    """Move linhas para o CSV de quarentena, preservando o motivo."""
    csv_path = Path(csv_path)
    quarantine_path = Path(quarantine_path)
    wanted = {name.strip() for name in filenames if name.strip()}
    if not wanted:
        return 0

    frame = pd.read_csv(csv_path).fillna("")
    mask = frame["filename"].astype(str).str.strip().isin(wanted)
    if not mask.any():
        return 0

    removed = frame[mask].copy()
    removed["motivo"] = reason
    if quarantine_path.exists():
        existing = pd.read_csv(quarantine_path).fillna("")
        removed = pd.concat([existing, removed], ignore_index=True)
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(quarantine_path, removed.to_csv(index=False, lineterminator=os.linesep).encode("utf-8"))

    _write_labels(frame[~mask].copy(), csv_path)
    logger.info("%d amostra(s) movidas para quarentena em %s.", int(mask.sum()), quarantine_path)
    return int(mask.sum())


def restore_from_quarantine(csv_path: Path, quarantine_path: Path, filenames: Collection[str]) -> int:
    """Devolve amostras da quarentena para o `labels.csv`, sem a coluna `motivo`."""
    csv_path = Path(csv_path)
    quarantine_path = Path(quarantine_path)
    wanted = {name.strip() for name in filenames if name.strip()}
    if not wanted or not quarantine_path.exists():
        return 0

    quarantined = pd.read_csv(quarantine_path).fillna("")
    mask = quarantined["filename"].astype(str).str.strip().isin(wanted)
    if not mask.any():
        return 0

    restored = quarantined[mask].drop(columns=[c for c in ("motivo",) if c in quarantined.columns]).copy()
    existing = pd.read_csv(csv_path).fillna("") if csv_path.exists() else pd.DataFrame(columns=list(LABEL_COLUMNS))
    _write_labels(pd.concat([existing, restored], ignore_index=True), csv_path)

    atomic_write_bytes(
        quarantine_path,
        quarantined[~mask].to_csv(index=False, lineterminator=os.linesep).encode("utf-8"),
    )
    logger.info("%d amostra(s) restauradas da quarentena.", int(mask.sum()))
    return int(mask.sum())
