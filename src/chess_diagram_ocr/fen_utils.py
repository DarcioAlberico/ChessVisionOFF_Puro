from __future__ import annotations

from collections.abc import Iterable

import chess

from .config import IDX_TO_CLASS, PIECE_TO_IDX


def _normalize_fen(fen: str) -> str:
    fen = fen.strip()
    if " " not in fen:
        return f"{fen} w - - 0 1"
    return fen


def is_valid_fen(fen: str) -> bool:
    """A FEN e parseavel. ATENCAO: nao garante posicao legal.

    Aceita, por exemplo, posicoes sem rei ou com dois reis da mesma cor.
    A checagem de legalidade sera introduzida em S-05 (ver docs/SPEC.md).
    """
    try:
        chess.Board(_normalize_fen(fen))
        return True
    except (ValueError, AttributeError, TypeError):
        # AttributeError/TypeError cobrem entrada nao textual vinda da UI ou do CSV.
        return False


def board_from_fen(fen: str) -> chess.Board:
    return chess.Board(_normalize_fen(fen))


def labels_from_fen(fen: str) -> list[int]:
    board_part = fen.split()[0] if " " in fen else fen
    rows = board_part.split("/")
    if len(rows) != 8:
        raise ValueError("FEN must have 8 ranks.")

    labels: list[int] = []
    for row in rows:
        expanded: list[str] = []
        for ch in row:
            if ch.isdigit():
                expanded.extend(["empty"] * int(ch))
            else:
                expanded.append(ch)
        if len(expanded) != 8:
            raise ValueError("Each FEN rank must resolve to 8 squares.")
        labels.extend(PIECE_TO_IDX.get(piece, PIECE_TO_IDX["empty"]) for piece in expanded)
    return labels


def fen_from_class_indices(class_indices: Iterable[int]) -> str:
    classes = [IDX_TO_CLASS[int(idx)] for idx in class_indices]
    if len(classes) != 64:
        raise ValueError("Expected exactly 64 squares.")

    rows: list[str] = []
    for row_start in range(0, 64, 8):
        row = classes[row_start : row_start + 8]
        chunks: list[str] = []
        empty_count = 0
        for item in row:
            if item == "empty":
                empty_count += 1
                continue
            if empty_count > 0:
                chunks.append(str(empty_count))
                empty_count = 0
            chunks.append(item)
        if empty_count > 0:
            chunks.append(str(empty_count))
        rows.append("".join(chunks))
    return "/".join(rows)
