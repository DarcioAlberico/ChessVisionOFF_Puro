from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import chess.pgn

from .board_detection import ReadingOrder, detect_boards
from .config import DEFAULT_MODEL_PATH, PROJECT_ROOT
from .inference import load_model, predict_fen_from_board

PdfSource = str | Path | bytes
ProgressCallback = Callable[[int, int, int, int], None]


@dataclass(frozen=True)
class DiagramPosition:
    page_index: int
    diagram_index: int
    fen: str
    confidence: float

    @property
    def page_number(self) -> int:
        return self.page_index + 1


def _normalize_fen_for_pgn(fen: str) -> str:
    normalized = fen.strip()
    if " " not in normalized:
        return f"{normalized} w - - 0 1"
    return normalized


def _get_pdf_page_count(pdf_source: PdfSource) -> int:
    from .pdf_io import get_pdf_page_count

    return get_pdf_page_count(pdf_source)


def _render_pdf_page(pdf_source: PdfSource, page_index: int, dpi: int) -> object:
    from .pdf_io import render_pdf_page

    return render_pdf_page(pdf_source, page_index, dpi=dpi)


def scan_pdf_positions(
    pdf_source: PdfSource,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = 220,
    max_boards_per_page: int = 8,
    rotate_180: bool = False,
    device: Optional[str] = None,
    start_page: int = 0,
    end_page: Optional[int] = None,
    reading_order: ReadingOrder = "column",
    progress_callback: Optional[ProgressCallback] = None,
) -> list[DiagramPosition]:
    page_count = _get_pdf_page_count(pdf_source)
    if page_count <= 0:
        return []

    if start_page < 0 or start_page >= page_count:
        raise ValueError(f"start_page {start_page} fora do intervalo 0..{page_count - 1}")

    last_page_exclusive = page_count if end_page is None else min(end_page, page_count)
    if last_page_exclusive <= start_page:
        raise ValueError("end_page deve ser maior que start_page.")
    total_pages = last_page_exclusive - start_page

    model, resolved_device = load_model(Path(model_path), device=device)
    positions: list[DiagramPosition] = []

    for page_index in range(start_page, last_page_exclusive):
        page_rgb = _render_pdf_page(pdf_source, page_index, dpi=dpi)
        boards = detect_boards(page_rgb, max_boards=max_boards_per_page, reading_order=reading_order)
        for diagram_index, (board_rgb, _quad) in enumerate(boards, start=1):
            fen, confidence = predict_fen_from_board(
                board_rgb=board_rgb,
                model=model,
                device=resolved_device,
                rotate_180=rotate_180,
            )
            positions.append(
                DiagramPosition(
                    page_index=page_index,
                    diagram_index=diagram_index,
                    fen=fen,
                    confidence=confidence,
                )
            )
        if progress_callback is not None:
            progress_callback(page_index, total_pages, len(boards), len(positions))

    return positions


def build_pgn_games(
    positions: Iterable[DiagramPosition],
    *,
    source_name: str,
    event_name: str = "ChessVisionOFF PDF OCR",
) -> list[chess.pgn.Game]:
    games: list[chess.pgn.Game] = []

    for position in positions:
        game = chess.pgn.Game()
        game.headers["Event"] = event_name
        game.headers["Site"] = "Local"
        game.headers["Round"] = f"{position.page_number}.{position.diagram_index}"
        game.headers["White"] = "?"
        game.headers["Black"] = "?"
        game.headers["Result"] = "*"
        game.headers["Annotator"] = "ChessVisionOFF"
        game.headers["SetUp"] = "1"
        game.headers["FEN"] = _normalize_fen_for_pgn(position.fen)
        game.headers["SourcePDF"] = source_name
        game.headers["Page"] = str(position.page_number)
        game.headers["Diagram"] = str(position.diagram_index)
        game.headers["OCRConfidence"] = f"{position.confidence:.3f}"
        games.append(game)

    return games


def build_pgn_text(
    positions: Iterable[DiagramPosition],
    *,
    source_name: str,
    event_name: str = "ChessVisionOFF PDF OCR",
) -> str:
    payloads = [
        game.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True)).strip()
        for game in build_pgn_games(positions, source_name=source_name, event_name=event_name)
    ]
    return "\n\n".join(payload for payload in payloads if payload).strip()


def save_pdf_positions_to_pgn(
    pdf_source: PdfSource,
    output_path: Path,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = 220,
    max_boards_per_page: int = 8,
    rotate_180: bool = False,
    device: Optional[str] = None,
    start_page: int = 0,
    end_page: Optional[int] = None,
    reading_order: ReadingOrder = "column",
    event_name: str = "ChessVisionOFF PDF OCR",
    progress_callback: Optional[ProgressCallback] = None,
) -> list[DiagramPosition]:
    source_name = Path(pdf_source).name if isinstance(pdf_source, (str, Path)) else "pdf-bytes"
    positions = scan_pdf_positions(
        pdf_source=pdf_source,
        model_path=model_path,
        dpi=dpi,
        max_boards_per_page=max_boards_per_page,
        rotate_180=rotate_180,
        device=device,
        start_page=start_page,
        end_page=end_page,
        reading_order=reading_order,
        progress_callback=progress_callback,
    )
    payload = build_pgn_text(positions, source_name=source_name, event_name=event_name)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if payload:
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        output_path.write_text("", encoding="utf-8")
    return positions


def default_pgn_output_path(pdf_path: Path) -> Path:
    return PROJECT_ROOT / "PGN" / f"{pdf_path.stem}.pgn"
