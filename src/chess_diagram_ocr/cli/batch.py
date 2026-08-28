"""`cvoff-batch`: exporta uma biblioteca inteira de PDFs para PGN (S-34)."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from pathlib import Path
from types import FrameType

from ..batch import BatchOptions, BatchReport, BookResult, find_pdfs, run_batch
from ..config import (
    DEFAULT_MAX_BOARDS,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
)
from ..logging_setup import configure_logging, default_log_file
from . import (
    EXIT_BAD_INPUT,
    EXIT_FAILURE,
    EXIT_OK,
    add_accept_threshold_argument,
    add_dpi_argument,
    add_model_argument,
    add_verbose,
    cli_errors,
)

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("PGN")
DEFAULT_REPORT = Path("PGN/batch_report.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Varre todos os PDFs de uma pasta e exporta cada um para PGN, com relatório "
            "consolidado. Substitui o acompanhamento manual em PDF/Andamento.txt."
        )
    )
    parser.add_argument("source", type=Path, help="Pasta com os PDFs, ou um PDF só.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="Pasta de saída dos PGN.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="JSON do relatório consolidado.")
    add_model_argument(parser)
    add_dpi_argument(parser)
    parser.add_argument(
        "--max-boards-per-page", type=int, default=DEFAULT_MAX_BOARDS, help="Teto de diagramas aceitos por página."
    )
    parser.add_argument(
        "--orientation",
        choices=("auto", "0", "180"),
        default=DEFAULT_ORIENTATION_MODE,
        help="Rotação do tabuleiro. `auto` decide pela confiança das duas leituras.",
    )
    parser.add_argument(
        "--reading-order",
        choices=("row", "column"),
        default=DEFAULT_READING_ORDER,
        help="Ordem em que os diagramas da página entram no PGN.",
    )
    add_accept_threshold_argument(parser)
    parser.add_argument("--dedupe", action="store_true", help="Omite diagramas repetidos (S-18).")
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help=(
            "Reexporta livros cujo PGN já existe. Por padrão eles são pulados, e é isso que "
            "torna a varredura retomável sem estado próprio."
        ),
    )
    parser.set_defaults(skip_existing=True)
    parser.add_argument("--limit", "--limite", type=int, default=None, help="Processa apenas os N primeiros livros.")
    add_verbose(parser)
    return parser.parse_args(argv)


def _install_cancel_handler(cancel: threading.Event) -> None:
    """Ctrl+C pede parada entre livros em vez de matar a varredura no meio.

    Sem isto, interromper uma varredura de 27 livros deixaria o PGN do livro em curso pela
    metade e nenhum relatório -- que é o oposto do que a S-34 pede.
    """

    def _handler(_sig: int, _frame: FrameType | None) -> None:
        if cancel.is_set():
            raise KeyboardInterrupt
        cancel.set()
        print("\nCancelamento pedido: terminando o livro atual. Ctrl+C de novo aborta.")

    try:
        signal.signal(signal.SIGINT, _handler)
    except ValueError:  # pragma: no cover - fora da thread principal
        logger.debug("Nao foi possivel instalar o handler de SIGINT.")


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    livros = find_pdfs(args.source)
    if args.limit is not None:
        livros = livros[: args.limit]
    if not livros:
        print(f"Nenhum PDF encontrado em {args.source}.")
        return EXIT_BAD_INPUT

    print(f"{len(livros)} PDF(s) a processar. Saída em {args.output}, relatório em {args.report}.")

    cancel = threading.Event()
    _install_cancel_handler(cancel)

    def _inicio(pdf: Path, indice: int, total: int) -> None:
        print(f"[{indice}/{total}] {pdf.name}...", flush=True)

    def _fim(resultado: BookResult) -> None:
        print(resultado.line(), flush=True)

    relatorio: BatchReport = run_batch(
        livros,
        args.output,
        options=BatchOptions(
            model_path=args.model,
            dpi=args.dpi,
            max_boards_per_page=args.max_boards_per_page,
            orientation=args.orientation,
            reading_order=args.reading_order,
            accept_threshold=args.accept_threshold,
            dedupe=args.dedupe,
            skip_existing=args.skip_existing,
        ),
        report_path=args.report,
        on_book_start=_inicio,
        on_book_done=_fim,
        cancel_event=cancel,
    )

    print()
    print(relatorio.summary())
    # Falha em qualquer livro vira codigo de saida diferente de zero: quem roda isto num
    # script precisa saber que a varredura nao saiu limpa sem ter de ler o JSON.
    return EXIT_FAILURE if relatorio.failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
