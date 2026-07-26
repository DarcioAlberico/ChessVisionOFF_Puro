"""Checkpoint incremental da exportação, para cancelar e retomar (S-24).

O `1001 Winning Chess Sacrifices` tem 1.121 páginas. A 0,18 s por página são ~3,5 minutos
de varredura, e até aqui a única forma de interromper era fechar o app -- perdendo tudo.

O formato é JSONL de uma linha por página, e não um JSON único reescrito a cada página, por
duas razões que se somam:

- **Acrescentar não reescreve.** Um JSON único custaria O(páginas²) de escrita ao longo de
  um livro e, pior, teria uma janela de truncamento a cada página.
- **Linha rasgada é detectável.** Se a energia cair no meio da última linha, ela não parseia
  e é descartada; as anteriores continuam válidas. Um JSON único cortado ao meio não tem
  nada aproveitável.

A primeira linha é o cabeçalho com os parâmetros da varredura. Retomar com parâmetro
diferente (outro DPI, outra ordem de leitura, outro modelo) **não** é retomar: seria juntar
metade de um PGN com metade de outro. Nesse caso o parcial é descartado e a varredura
recomeça, com aviso no log.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chess

if TYPE_CHECKING:
    from .pdf_to_pgn import DiagramPosition

logger = logging.getLogger(__name__)

CHECKPOINT_VERSION = 1

DEFAULT_CHECKPOINT_EVERY = 5
"""Páginas entre gravações. 5 a 220 DPI é ~1 s de trabalho arriscado por vez."""


def partial_path_for(output_path: Path) -> Path:
    """`PGN/livro.pgn` -> `PGN/livro.partial.jsonl`."""
    output_path = Path(output_path)
    return output_path.with_suffix(".partial.jsonl")


@dataclass(frozen=True)
class ScanParams:
    """O que precisa bater para um parcial poder ser continuado."""

    source_name: str
    model_path: str
    dpi: int
    max_boards_per_page: int
    orientation: str
    reading_order: str
    read_text: bool
    start_page: int
    end_page: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "model_path": self.model_path,
            "dpi": self.dpi,
            "max_boards_per_page": self.max_boards_per_page,
            "orientation": self.orientation,
            "reading_order": self.reading_order,
            "read_text": self.read_text,
            "start_page": self.start_page,
            "end_page": self.end_page,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ScanParams:
        return cls(
            source_name=str(raw.get("source_name", "")),
            model_path=str(raw.get("model_path", "")),
            dpi=int(raw.get("dpi", 0)),
            max_boards_per_page=int(raw.get("max_boards_per_page", 0)),
            orientation=str(raw.get("orientation", "")),
            reading_order=str(raw.get("reading_order", "")),
            read_text=bool(raw.get("read_text", True)),
            start_page=int(raw.get("start_page", 0)),
            end_page=None if raw.get("end_page") is None else int(raw["end_page"]),
        )


@dataclass
class PartialExport:
    """O que um `.partial.jsonl` guarda: os parâmetros e as páginas já concluídas."""

    params: ScanParams
    positions: list[DiagramPosition] = field(default_factory=list)
    last_page_done: int = -1
    """Índice da última página **inteira** gravada. -1 quando nenhuma."""

    @property
    def resume_from(self) -> int:
        return self.last_page_done + 1

    @property
    def pages_done(self) -> int:
        return max(0, self.last_page_done + 1 - self.params.start_page)


# ---------------------------------------------------------------------- serialização


def _context_to_dict(context: Any) -> dict[str, Any] | None:
    if context is None:
        return None
    return {
        "caption": context.caption,
        "side_to_move": None if context.side_to_move is None else bool(context.side_to_move),
        "side_to_move_evidence": context.side_to_move_evidence,
        "exercise_number": context.exercise_number,
        "players": list(context.players) if context.players else None,
        "event": context.event,
        "year": context.year,
    }


def _context_from_dict(raw: dict[str, Any] | None) -> Any:
    if raw is None:
        return None
    from .pdf_text import DiagramContext

    players = raw.get("players")
    return DiagramContext(
        caption=str(raw.get("caption", "")),
        side_to_move=None if raw.get("side_to_move") is None else chess.Color(bool(raw["side_to_move"])),
        side_to_move_evidence=str(raw.get("side_to_move_evidence", "")),
        exercise_number=raw.get("exercise_number"),
        players=(str(players[0]), str(players[1])) if players and len(players) == 2 else None,
        event=raw.get("event"),
        year=raw.get("year"),
    )


def _side_to_dict(side: Any) -> dict[str, Any] | None:
    if side is None:
        return None
    return {
        "color": bool(side.color),
        "source": side.source,
        "reason": side.reason,
        "conflicting": side.conflicting,
    }


def _side_from_dict(raw: dict[str, Any] | None) -> Any:
    if raw is None:
        return None
    from .semantics import SideToMove

    return SideToMove(
        color=chess.Color(bool(raw.get("color", True))),
        source=raw.get("source", "default"),
        reason=str(raw.get("reason", "")),
        conflicting=bool(raw.get("conflicting", False)),
    )


def position_to_dict(position: DiagramPosition) -> dict[str, Any]:
    return {
        "page_index": position.page_index,
        "diagram_index": position.diagram_index,
        "fen": position.fen,
        "confidence": position.confidence,
        "min_confidence": position.min_confidence,
        "is_legal": position.is_legal,
        "is_fatal": position.is_fatal,
        "problems": list(position.problems),
        "rotation": position.rotation,
        "orientation_ambiguous": position.orientation_ambiguous,
        "orientation_reason": position.orientation_reason,
        "side_to_move": _side_to_dict(position.side_to_move),
        "context": _context_to_dict(position.context),
        "detection_source": position.detection_source,
        "duplicate_of": list(position.duplicate_of) if position.duplicate_of else None,
    }


def position_from_dict(raw: dict[str, Any]) -> DiagramPosition:
    from .pdf_to_pgn import DiagramPosition

    duplicate = raw.get("duplicate_of")
    return DiagramPosition(
        page_index=int(raw["page_index"]),
        diagram_index=int(raw["diagram_index"]),
        fen=str(raw["fen"]),
        confidence=float(raw.get("confidence", 0.0)),
        min_confidence=None if raw.get("min_confidence") is None else float(raw["min_confidence"]),
        is_legal=raw.get("is_legal"),
        is_fatal=raw.get("is_fatal"),
        problems=tuple(str(item) for item in raw.get("problems", ())),
        rotation=None if raw.get("rotation") is None else int(raw["rotation"]),
        orientation_ambiguous=bool(raw.get("orientation_ambiguous", False)),
        orientation_reason=str(raw.get("orientation_reason", "")),
        side_to_move=_side_from_dict(raw.get("side_to_move")),
        context=_context_from_dict(raw.get("context")),
        detection_source=raw.get("detection_source"),
        duplicate_of=(int(duplicate[0]), int(duplicate[1])) if duplicate and len(duplicate) == 2 else None,
    )


# ------------------------------------------------------------------------ escrita


class CheckpointWriter:
    """Acumula páginas e grava o parcial de tempos em tempos.

    O acúmulo existe porque gravar uma linha por página em livro de 1.121 páginas custaria
    1.121 `flush` -- e o que se ganha com isso é irrelevante: perder 5 páginas de trabalho
    numa queda é ~1 s de reprocessamento.
    """

    def __init__(
        self,
        path: Path,
        params: ScanParams,
        *,
        every: int = DEFAULT_CHECKPOINT_EVERY,
        resumed: bool = False,
    ) -> None:
        self.path = Path(path)
        self.params = params
        self.every = max(1, every)
        self._pending: list[tuple[int, list[DiagramPosition]]] = []
        self._started = resumed
        """`True` já de saída quando retomamos: as páginas novas vão ao fim do arquivo que
        existe, e reescrever o cabeçalho perderia tudo que ele guardava."""

    def record_page(self, page_index: int, positions: list[DiagramPosition]) -> None:
        self._pending.append((page_index, list(positions)))
        if len(self._pending) >= self.every:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        lines: list[str] = []
        if not self._started:
            header = {"kind": "header", "version": CHECKPOINT_VERSION, "params": self.params.to_dict()}
            lines.append(json.dumps(header, ensure_ascii=False))
        for page_index, positions in self._pending:
            lines.append(
                json.dumps(
                    {
                        "kind": "page",
                        "page_index": page_index,
                        "positions": [position_to_dict(position) for position in positions],
                    },
                    ensure_ascii=False,
                )
            )
        self._pending.clear()

        mode = "a" if self._started else "w"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open(mode, encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        self._started = True

    def discard(self) -> None:
        """Apaga o parcial. Chamado quando a exportação chega ao fim com sucesso."""
        self._pending.clear()
        self.path.unlink(missing_ok=True)


def load_partial(path: Path, params: ScanParams) -> PartialExport | None:
    """Lê um parcial compatível com `params`. `None` se não houver ou não servir."""
    path = Path(path)
    if not path.exists():
        return None

    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Parcial de exportação ilegível, será ignorado (%s): %s", path, exc)
        return None

    lines = [line for line in raw_lines if line.strip()]
    if not lines:
        return None

    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        logger.warning("Parcial de exportação sem cabeçalho válido, será ignorado (%s): %s", path, exc)
        return None

    if header.get("kind") != "header" or header.get("version") != CHECKPOINT_VERSION:
        logger.warning("Parcial de exportação de formato desconhecido, será ignorado: %s", path)
        return None

    stored = ScanParams.from_dict(header.get("params", {}))
    if stored != params:
        logger.warning(
            "Parcial de exportação foi gerado com outros parâmetros e será ignorado: %s",
            _params_diff(stored, params),
        )
        return None

    partial = PartialExport(params=stored)
    for line_number, line in enumerate(lines[1:], start=2):
        try:
            entry = json.loads(line)
            if entry.get("kind") != "page":
                continue
            page_index = int(entry["page_index"])
            positions = [position_from_dict(item) for item in entry.get("positions", [])]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            # Linha rasgada por interrupcao: acontece na ultima e so nela. Descartar o resto
            # e a leitura correta -- as paginas seguintes nao chegaram a ser gravadas.
            logger.warning("Parcial truncado na linha %d, retomando do que veio antes: %s", line_number, exc)
            break
        partial.positions.extend(positions)
        partial.last_page_done = max(partial.last_page_done, page_index)

    if partial.last_page_done < 0:
        return None
    return partial


def _params_diff(stored: ScanParams, wanted: ScanParams) -> str:
    changes = [
        f"{field_name}: {getattr(stored, field_name)!r} -> {getattr(wanted, field_name)!r}"
        for field_name in stored.to_dict()
        if getattr(stored, field_name) != getattr(wanted, field_name)
    ]
    return "; ".join(changes) or "sem diferença aparente"
