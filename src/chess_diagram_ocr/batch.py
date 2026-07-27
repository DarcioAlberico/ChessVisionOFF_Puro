"""Varredura de uma biblioteca inteira de PDFs, com relatório consolidado (S-34).

**O que ele substitui.** `PDF/Andamento.txt` — um arquivo de controle mantido à mão, onde o
progresso por livro era anotado a dedo. Um txt manual não sabe quantos diagramas foram
rejeitados, nem com que confiança, nem quanto tempo levou; e ninguém consegue dizer, olhando
para ele, se está atualizado.

**A regra que organiza tudo aqui: um livro que falha não derruba a varredura.** Com 27 PDFs
e minutos por livro, uma exceção no décimo que abortasse o processo custaria tudo que veio
antes. Cada livro é isolado, a falha vira uma linha do relatório com o motivo, e a varredura
segue. É literalmente o critério de aceite da S-34.

**E o relatório é gravado a cada livro, não no fim.** Pelo mesmo motivo: se o processo
morrer por algo que o `try` não pega — falta de memória, o usuário fechando o terminal —, o
que já foi medido continua no disco. Um relatório escrito só no fim é um relatório que não
existe exatamente quando ele seria mais útil.

**`--skip-existing` é o que torna a varredura retomável** sem nenhum estado próprio: o PGN
que já está no disco é o registro de que aquele livro foi feito. Não inventa um segundo
lugar para a verdade morar.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
    OrientationMode,
    ReadingOrder,
)
from .pdf_to_pgn import ExportReport, default_pgn_output_path, save_pdf_positions_to_pgn

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_SKIPPED = "pulado"
STATUS_FAILED = "falhou"
STATUS_CANCELLED = "cancelado"


@dataclass(frozen=True)
class BatchOptions:
    """Os parâmetros de leitura, iguais para todos os livros da varredura."""

    model_path: Path = DEFAULT_MODEL_PATH
    dpi: int = 220
    max_boards_per_page: int = DEFAULT_MAX_BOARDS
    orientation: OrientationMode = DEFAULT_ORIENTATION_MODE
    reading_order: ReadingOrder = DEFAULT_READING_ORDER
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE
    dedupe: bool = False
    skip_existing: bool = True
    """Livro cujo PGN já existe é pulado. O arquivo no disco **é** o registro de progresso;
    um segundo lugar para essa verdade morar só teria como divergir do primeiro."""


@dataclass(frozen=True)
class BookResult:
    """O que aconteceu com um livro. Sempre existe, mesmo quando ele falhou."""

    pdf: Path
    status: str
    output: Path | None = None
    review_path: Path | None = None
    pages: int = 0
    accepted: int = 0
    needs_review: int = 0
    rejected: int = 0
    duplicates: int = 0
    mean_min_confidence: float = 0.0
    elapsed_s: float = 0.0
    error: str = ""

    @property
    def total_diagrams(self) -> int:
        return self.accepted + self.needs_review + self.rejected

    @property
    def acceptance_rate(self) -> float:
        """Fração aceita no PGN principal. `0.0` quando não houve diagrama nenhum."""
        return self.accepted / self.total_diagrams if self.total_diagrams else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf": str(self.pdf),
            "status": self.status,
            "output": str(self.output) if self.output else None,
            "review_path": str(self.review_path) if self.review_path else None,
            "pages": self.pages,
            "accepted": self.accepted,
            "needs_review": self.needs_review,
            "rejected": self.rejected,
            "duplicates": self.duplicates,
            "mean_min_confidence": round(self.mean_min_confidence, 4),
            "acceptance_rate": round(self.acceptance_rate, 4),
            "elapsed_s": round(self.elapsed_s, 2),
            "error": self.error,
        }

    def line(self) -> str:
        """Uma linha para o terminal. Os rejeitados aparecem sempre que existem (S-15)."""
        if self.status == STATUS_SKIPPED:
            return f"  {self.pdf.name}: já exportado, pulado"
        if self.status == STATUS_FAILED:
            return f"  {self.pdf.name}: FALHOU — {self.error}"

        partes = [
            f"{self.pages} págs",
            f"{self.accepted} aceitos",
        ]
        if self.needs_review:
            partes.append(f"{self.needs_review} p/ revisão")
        if self.rejected:
            partes.append(f"{self.rejected} ilegais")
        if self.duplicates:
            partes.append(f"{self.duplicates} repetidos")
        partes.append(f"conf mín média {self.mean_min_confidence:.3f}")
        partes.append(f"{self.elapsed_s:.1f}s")
        marca = " (cancelado)" if self.status == STATUS_CANCELLED else ""
        return f"  {self.pdf.name}{marca}: " + ", ".join(partes)


@dataclass
class BatchReport:
    """A varredura inteira. Mutável porque é gravada a cada livro, não só no fim."""

    books: list[BookResult] = field(default_factory=list)
    started_at: str = ""

    @property
    def processed(self) -> list[BookResult]:
        return [livro for livro in self.books if livro.status in (STATUS_OK, STATUS_CANCELLED)]

    @property
    def failed(self) -> list[BookResult]:
        return [livro for livro in self.books if livro.status == STATUS_FAILED]

    @property
    def total_accepted(self) -> int:
        return sum(livro.accepted for livro in self.books)

    @property
    def total_needs_review(self) -> int:
        return sum(livro.needs_review for livro in self.books)

    @property
    def total_rejected(self) -> int:
        return sum(livro.rejected for livro in self.books)

    @property
    def elapsed_s(self) -> float:
        return sum(livro.elapsed_s for livro in self.books)

    def summary(self) -> str:
        """O resumo final. Falhas aparecem por nome, não como um contador.

        "3 livros falharam" não permite agir; os nomes permitem.
        """
        pulados = sum(1 for livro in self.books if livro.status == STATUS_SKIPPED)
        linhas = [
            f"{len(self.processed)} livro(s) processado(s), {pulados} pulado(s), "
            f"{len(self.failed)} com falha em {self.elapsed_s / 60:.1f} min.",
            f"Diagramas: {self.total_accepted} aceitos, {self.total_needs_review} para revisão, "
            f"{self.total_rejected} ilegais.",
        ]
        for livro in self.failed:
            linhas.append(f"  falhou: {livro.pdf.name} — {livro.error}")
        return "\n".join(linhas)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "books": [livro.to_dict() for livro in self.books],
            "totals": {
                "processed": len(self.processed),
                "failed": len(self.failed),
                "accepted": self.total_accepted,
                "needs_review": self.total_needs_review,
                "rejected": self.total_rejected,
                "elapsed_s": round(self.elapsed_s, 2),
            },
        }


def find_pdfs(source: Path) -> list[Path]:
    """Os PDFs a varrer, em ordem de nome. Aceita um arquivo ou um diretório."""
    if source.is_file():
        return [source]
    return sorted(p for p in source.rglob("*.pdf") if p.is_file())


def _mean_min_confidence(report: ExportReport) -> float:
    """Confiança mínima média entre **todos** os diagramas lidos, e não só os aceitos.

    Média só dos aceitos subiria conforme o gate rejeitasse mais — o número melhoraria
    justamente nos livros em que a leitura piorou.
    """
    posicoes = (
        list(report.accepted)
        + [p for p, _motivo in report.needs_review]
        + [p for p, _motivo in report.rejected]
    )
    if not posicoes:
        return 0.0
    valores = [float(getattr(p, "min_confidence", 0.0) or 0.0) for p in posicoes]
    return sum(valores) / len(valores)


def run_batch(
    sources: Sequence[Path] | Iterable[Path],
    output_dir: Path,
    *,
    options: BatchOptions | None = None,
    report_path: Path | None = None,
    on_book_start: Callable[[Path, int, int], None] | None = None,
    on_book_done: Callable[[BookResult], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> BatchReport:
    """Exporta cada PDF para PGN e devolve o relatório consolidado.

    Sequencial de propósito. A S-34 sugere `--workers 2`, mas a inferência do torch já usa
    as CPUs disponíveis: dois processos disputariam os mesmos núcleos e ainda carregariam
    dois modelos na memória. A decisão é a mesma que a S-24 tomou para páginas, pelo mesmo
    motivo, e está registrada no ROADMAP.
    """
    options = options or BatchOptions()
    output_dir.mkdir(parents=True, exist_ok=True)
    relatorio = BatchReport(started_at=time.strftime("%Y-%m-%d %H:%M:%S"))

    livros = list(sources)
    for indice, pdf in enumerate(livros, start=1):
        if cancel_event is not None and cancel_event.is_set():
            logger.info("Varredura cancelada antes de %s.", pdf.name)
            break

        if on_book_start is not None:
            on_book_start(pdf, indice, len(livros))

        resultado = _run_one(pdf, output_dir, options, cancel_event)
        relatorio.books.append(resultado)

        if on_book_done is not None:
            on_book_done(resultado)
        if report_path is not None:
            # A cada livro, e nao no fim: se o processo morrer por algo que o `try` nao
            # pega, o que ja foi medido continua no disco.
            atomic_write_json(report_path, relatorio.to_dict())

    return relatorio


def _run_one(
    pdf: Path,
    output_dir: Path,
    options: BatchOptions,
    cancel_event: threading.Event | None,
) -> BookResult:
    saida = output_dir / default_pgn_output_path(pdf).name
    if options.skip_existing and saida.exists():
        logger.info("Pulando %s: %s ja existe.", pdf.name, saida.name)
        return BookResult(pdf=pdf, status=STATUS_SKIPPED, output=saida)

    inicio = time.monotonic()
    try:
        report = save_pdf_positions_to_pgn(
            pdf_source=pdf,
            output_path=saida,
            model_path=options.model_path,
            dpi=options.dpi,
            max_boards_per_page=options.max_boards_per_page,
            orientation=options.orientation,
            reading_order=options.reading_order,
            accept_threshold=options.accept_threshold,
            dedupe=options.dedupe,
            cancel_event=cancel_event,
        )
    except Exception as exc:
        # Um livro que falha nao derruba a varredura: com 27 PDFs e minutos por livro, uma
        # excecao no decimo custaria tudo que veio antes (criterio da S-34).
        logger.exception("Falha ao exportar %s.", pdf.name)
        return BookResult(
            pdf=pdf,
            status=STATUS_FAILED,
            output=saida,
            elapsed_s=time.monotonic() - inicio,
            error=f"{type(exc).__name__}: {exc}",
        )

    return BookResult(
        pdf=pdf,
        status=STATUS_CANCELLED if report.cancelled else STATUS_OK,
        output=report.output_path,
        review_path=report.review_path,
        pages=report.pages_scanned,
        accepted=len(report.accepted),
        needs_review=len(report.needs_review),
        rejected=len(report.rejected),
        duplicates=len(report.duplicates),
        mean_min_confidence=_mean_min_confidence(report),
        elapsed_s=time.monotonic() - inicio,
    )
