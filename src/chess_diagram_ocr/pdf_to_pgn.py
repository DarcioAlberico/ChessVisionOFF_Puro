from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import chess.pgn
import numpy as np

from .board_detection import detect_boards
from .config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_MODEL_PATH,
    DEFAULT_READING_ORDER,
    PROJECT_ROOT,
    ReadingOrder,
)
from .inference import load_model, predict_board

PdfSource = str | Path | bytes
ProgressCallback = Callable[[int, int, int, int], None]


@dataclass(frozen=True)
class DiagramPosition:
    page_index: int
    diagram_index: int
    fen: str
    confidence: float
    """Confiança média das 64 casas. Mantida por compatibilidade; ver `min_confidence`."""

    min_confidence: float | None = None
    """Confiança da casa mais insegura (S-10). `None` em posições montadas à mão."""

    is_legal: bool | None = None
    """Legal exatamente como está escrita, lado a jogar incluído (S-05).

    `None` quando não foi avaliada."""

    is_fatal: bool | None = None
    """Viola uma regra que não depende do lado a jogar: erro real de reconhecimento.

    A distinção importa e não é sutil. Um diagrama de livro não diz de quem é a vez, e o
    export assume brancas; se as pretas estiverem em xeque, a posição sai como "ilegal"
    sendo que o tabuleiro está perfeito -- errado é o palpite do lado a jogar. Descartar
    esse caso jogaria fora leitura boa. Só `is_fatal` significa "o modelo leu errado".
    """

    problems: tuple[str, ...] = ()
    """Descrições dos problemas de legalidade, quando houver."""

    @property
    def needs_side_to_move_flip(self) -> bool:
        """A posição só não fecha por causa do lado a jogar assumido (S-17)."""
        return self.is_legal is False and self.is_fatal is False

    @property
    def legality_label(self) -> str:
        """Como a legalidade aparece no PGN: três estados, não dois."""
        if self.is_legal is None:
            return "nao-avaliada"
        if self.is_legal:
            return "legal"
        return "lado-a-jogar" if self.is_fatal is False else "ilegal"

    @property
    def page_number(self) -> int:
        return self.page_index + 1


Verdict = Literal["accepted", "needs_review", "rejected"]


@dataclass(frozen=True)
class ExportReport:
    """Resultado de uma exportação, com cada posição em um dos três destinos (S-15).

    Antes disso o export escrevia tudo no mesmo arquivo, inclusive posições ilegais: o
    usuário só descobria ao abrir o PGN num visualizador que reclamava -- e não tinha como
    saber quais dos 300 diagramas eram os ruins.
    """

    accepted: list[DiagramPosition]
    """Legais e confiantes. Vão para o PGN principal."""

    needs_review: list[tuple[DiagramPosition, str]]
    """Legais, mas com alguma casa insegura. Vão para o `.review.pgn` com o motivo."""

    rejected: list[tuple[DiagramPosition, str]]
    """Ilegais mesmo depois da decodificação restrita (S-11), ou tabuleiro vazio.

    Também vão para o `.review.pgn`, e não para o lixo: uma posição ilegal costuma estar a
    uma casa da correta, e é justamente o que vale a pena corrigir à mão. O que a S-15
    exige é que o PGN **principal** saia limpo, não que o diagrama desapareça.
    """

    pages_scanned: int
    output_path: Path
    review_path: Path | None
    """`None` quando nada precisou de revisão -- nesse caso o arquivo não é criado."""

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.needs_review) + len(self.rejected)

    @property
    def review_items(self) -> list[tuple[DiagramPosition, str]]:
        """Tudo que precisa de olho humano, na ordem em que foi encontrado no PDF."""
        items = self.needs_review + self.rejected
        return sorted(items, key=lambda item: (item[0].page_index, item[0].diagram_index))

    def summary(self) -> str:
        return (
            f"{len(self.accepted)} aceitos, {len(self.needs_review)} para revisão, "
            f"{len(self.rejected)} rejeitados em {self.pages_scanned} páginas"
        )


def classify_position(
    position: DiagramPosition,
    *,
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
) -> tuple[Verdict, str]:
    """Destino de uma posição na exportação, com o motivo em texto.

    Campos não medidos (`None`) não condenam a posição: `DiagramPosition` também é usada
    para posições montadas à mão, e afirmar "ilegal" sem ter verificado seria pior que não
    afirmar nada.
    """
    if position.is_fatal:
        problems = "; ".join(position.problems) or "posição ilegal"
        return "rejected", f"ilegal: {problems}"

    if position.needs_side_to_move_flip:
        # Leitura provavelmente boa, palpite de lado a jogar ruim. Vai para revisão porque
        # ninguém verificou de quem é a vez; a inferência automática é a S-17.
        return "needs_review", "lado a jogar assumido errado: " + ("; ".join(position.problems) or "xeque invertido")

    if position.min_confidence is not None and position.min_confidence < accept_threshold:
        return "needs_review", f"confiança mínima {position.min_confidence:.3f} < {accept_threshold:.2f}"

    return "accepted", ""


def partition_positions(
    positions: Iterable[DiagramPosition],
    *,
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
) -> tuple[list[DiagramPosition], list[tuple[DiagramPosition, str]], list[tuple[DiagramPosition, str]]]:
    accepted: list[DiagramPosition] = []
    needs_review: list[tuple[DiagramPosition, str]] = []
    rejected: list[tuple[DiagramPosition, str]] = []

    for position in positions:
        verdict, reason = classify_position(position, accept_threshold=accept_threshold)
        if verdict == "accepted":
            accepted.append(position)
        elif verdict == "needs_review":
            needs_review.append((position, reason))
        else:
            rejected.append((position, reason))

    return accepted, needs_review, rejected


def review_output_path(output_path: Path) -> Path:
    """`PGN/livro.pgn` -> `PGN/livro.review.pgn`."""
    output_path = Path(output_path)
    return output_path.with_suffix(f".review{output_path.suffix}")


def _normalize_fen_for_pgn(fen: str) -> str:
    normalized = fen.strip()
    if " " not in normalized:
        return f"{normalized} w - - 0 1"
    return normalized


def _get_pdf_page_count(pdf_source: PdfSource) -> int:
    from .pdf_io import get_pdf_page_count

    return get_pdf_page_count(pdf_source)


def _render_pdf_page(pdf_source: PdfSource, page_index: int, dpi: int) -> np.ndarray:
    # Indirecao mantida para permitir mock nos testes sem tocar em pdf_io.
    from .pdf_io import render_pdf_page

    return render_pdf_page(pdf_source, page_index, dpi=dpi)


def scan_pdf_positions(
    pdf_source: PdfSource,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = 220,
    max_boards_per_page: int = 8,
    rotate_180: bool = False,
    device: str | None = None,
    start_page: int = 0,
    end_page: int | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    progress_callback: ProgressCallback | None = None,
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
            prediction = predict_board(
                board_rgb,
                model,
                resolved_device,
                rotate_180=rotate_180,
            )
            positions.append(
                DiagramPosition(
                    page_index=page_index,
                    diagram_index=diagram_index,
                    fen=prediction.fen_board,
                    confidence=prediction.mean_confidence,
                    min_confidence=prediction.min_confidence,
                    is_legal=prediction.position.is_legal,
                    is_fatal=prediction.position.is_fatal,
                    problems=prediction.position.problems,
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
    review_reasons: Mapping[tuple[int, int], str] | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
) -> list[chess.pgn.Game]:
    """Um jogo por posição, só com headers -- o diagrama é a posição inicial.

    `review_reasons`, indexado por (página, diagrama), adiciona o header `[Review]` com o
    motivo pelo qual a posição foi separada. É o que faz o arquivo de revisão dizer *por
    que* cada item está lá em vez de deixar o usuário adivinhar.

    `reading_order` vai para o header porque `[Diagram "2"]` só significa algo junto com a
    ordem em que a página foi numerada (S-14): sem isso, um PGN gerado com outro padrão
    fica impossível de conferir depois.
    """
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
        game.headers["ReadingOrder"] = reading_order
        game.headers["OCRConfidence"] = f"{position.confidence:.3f}"
        if position.min_confidence is not None:
            game.headers["OCRMinConfidence"] = f"{position.min_confidence:.3f}"
        if position.is_legal is not None:
            game.headers["OCRLegality"] = position.legality_label
            if not position.is_legal and position.problems:
                game.headers["OCRProblems"] = "; ".join(position.problems)

        reason = (review_reasons or {}).get((position.page_index, position.diagram_index))
        if reason:
            game.headers["Review"] = reason

        games.append(game)

    return games


def build_pgn_text(
    positions: Iterable[DiagramPosition],
    *,
    source_name: str,
    event_name: str = "ChessVisionOFF PDF OCR",
    review_reasons: Mapping[tuple[int, int], str] | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
) -> str:
    payloads = [
        game.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True)).strip()
        for game in build_pgn_games(
            positions,
            source_name=source_name,
            event_name=event_name,
            review_reasons=review_reasons,
            reading_order=reading_order,
        )
    ]
    return "\n\n".join(payload for payload in payloads if payload).strip()


def write_gated_pgn(
    positions: Iterable[DiagramPosition],
    output_path: Path,
    *,
    source_name: str,
    event_name: str = "ChessVisionOFF PDF OCR",
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    pages_scanned: int = 0,
) -> ExportReport:
    """Escreve o PGN principal só com o que passou no gate, e o resto no `.review.pgn`."""
    accepted, needs_review, rejected = partition_positions(positions, accept_threshold=accept_threshold)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_pgn_text(accepted, source_name=source_name, event_name=event_name, reading_order=reading_order)
    output_path.write_text(payload + "\n" if payload else "", encoding="utf-8")

    review_items = sorted(
        needs_review + rejected,
        key=lambda item: (item[0].page_index, item[0].diagram_index),
    )
    review_path: Path | None = None
    if review_items:
        review_path = review_output_path(output_path)
        review_payload = build_pgn_text(
            [position for position, _ in review_items],
            source_name=source_name,
            event_name=event_name,
            review_reasons={(position.page_index, position.diagram_index): reason for position, reason in review_items},
            reading_order=reading_order,
        )
        review_path.write_text(review_payload + "\n" if review_payload else "", encoding="utf-8")

    return ExportReport(
        accepted=accepted,
        needs_review=needs_review,
        rejected=rejected,
        pages_scanned=pages_scanned,
        output_path=output_path,
        review_path=review_path,
    )


def save_pdf_positions_to_pgn(
    pdf_source: PdfSource,
    output_path: Path,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = 220,
    max_boards_per_page: int = 8,
    rotate_180: bool = False,
    device: str | None = None,
    start_page: int = 0,
    end_page: int | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    event_name: str = "ChessVisionOFF PDF OCR",
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    progress_callback: ProgressCallback | None = None,
) -> ExportReport:
    """Varre o PDF e exporta com o gate de qualidade da S-15.

    Devolve o `ExportReport` -- antes devolvia a lista de posições. O relatório é o que
    permite ao chamador dizer quantas foram para revisão e por quê; a lista continua
    acessível em `report.accepted` e companhia.
    """
    source_name = Path(pdf_source).name if isinstance(pdf_source, (str, Path)) else "pdf-bytes"
    pages_seen = 0

    def _count_pages(page_index: int, total_pages: int, page_boards: int, total_positions: int) -> None:
        nonlocal pages_seen
        pages_seen += 1
        if progress_callback is not None:
            progress_callback(page_index, total_pages, page_boards, total_positions)

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
        progress_callback=_count_pages,
    )

    return write_gated_pgn(
        positions,
        output_path,
        source_name=source_name,
        event_name=event_name,
        accept_threshold=accept_threshold,
        reading_order=reading_order,
        pages_scanned=pages_seen,
    )


def default_pgn_output_path(pdf_path: Path) -> Path:
    return PROJECT_ROOT / "PGN" / f"{pdf_path.stem}.pgn"
