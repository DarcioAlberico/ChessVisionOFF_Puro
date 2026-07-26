from __future__ import annotations

import argparse
import logging
import random
from pathlib import Path

from ..config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_DATASET_CSV,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
)
from ..logging_setup import configure_logging, default_log_file
from ..review_queue import (
    DEFAULT_CACHE_DIR,
    DEFAULT_QUEUE_PATH,
    ReviewQueue,
    build_review_queue,
    error_rate,
    merge_queues,
    rare_classes_from_labels,
)

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Varre um PDF e monta a fila de revisao ordenada por valor de informacao (S-22).",
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH, help=f"Padrao: {DEFAULT_QUEUE_PATH}")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--labels", type=Path, default=DEFAULT_DATASET_CSV, help="CSV usado para achar classes raras.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--max-boards-per-page", type=int, default=8)
    parser.add_argument("--orientation", choices=("auto", "0", "180"), default=DEFAULT_ORIENTATION_MODE)
    parser.add_argument("--start-page", type=int, default=0)
    parser.add_argument("--end-page", type=int, default=None, help="Exclusivo. Padrao: ate o fim do PDF.")
    parser.add_argument("--reading-order", choices=("column", "row"), default=DEFAULT_READING_ORDER)
    parser.add_argument("--accept-threshold", type=float, default=ACCEPT_MIN_CONFIDENCE)
    parser.add_argument("--limit", type=int, default=None, help="Corta a fila apos ordenar.")
    parser.add_argument("--show", type=int, default=20, help="Itens listados no fim.")
    parser.add_argument(
        "--no-merge",
        dest="merge",
        action="store_false",
        help="Descarta o que ja foi marcado como revisado na fila existente.",
    )
    parser.add_argument(
        "--compare-random",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Criterio de aceite da S-22: compara a taxa de erro dos N primeiros da fila com "
            "a de N itens sorteados entre todos os diagramas varridos."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    def _progress(page_index: int, total_pages: int, page_boards: int, total_positions: int) -> None:
        logger.info(
            "pagina %d/%d | diagramas na pagina: %d | total acumulado: %d",
            page_index + 1,
            total_pages,
            page_boards,
            total_positions,
        )

    rare = rare_classes_from_labels(args.labels)
    if rare:
        logger.info("Classes raras no dataset: %s", ", ".join(sorted(rare)))

    queue = build_review_queue(
        args.pdf,
        args.model,
        dpi=args.dpi,
        max_boards_per_page=args.max_boards_per_page,
        orientation=args.orientation,
        start_page=args.start_page,
        end_page=args.end_page,
        reading_order=args.reading_order,
        accept_threshold=args.accept_threshold,
        rare_classes=rare,
        cache_dir=args.cache_dir,
        limit=args.limit,
        progress_callback=_progress,
    )

    if args.merge:
        existing = ReviewQueue.load(args.queue)
        if existing.items and existing.source_pdf == queue.source_pdf:
            revisados = sum(1 for item in existing.items if item.status != "pending")
            queue = merge_queues(existing, queue)
            print(f"Fila anterior reaproveitada: {revisados} itens ja marcados foram preservados.")

    path = queue.save(args.queue)

    print(f"PDF: {args.pdf}")
    print(f"Fila: {path}")
    print(queue.summary())

    if queue.items and args.show:
        print()
        print("Prioridade mais alta primeiro:")
        for item in queue.items[: args.show]:
            print(f"  {item.describe()}")
        if len(queue.items) > args.show:
            print(f"  ... e outros {len(queue.items) - args.show}")

    if args.compare_random and queue.items:
        _print_acceptance_check(queue, args.compare_random, args.accept_threshold)
    return 0


def _print_acceptance_check(queue: ReviewQueue, sample: int, accept_threshold: float) -> None:
    """Mede o que a S-22 pede: o topo da fila erra mais que uma amostra qualquer?

    A amostra aleatoria sai da propria fila embaralhada, e o denominador honesto e dito
    junto: itens que nao entraram na fila nao tem sinal de erro nenhum, entao a comparacao
    correta e "topo da fila" contra "fila inteira", e nao contra o livro inteiro -- que
    inflaria a diferenca de graca.
    """
    top = queue.items[:sample]
    pool = list(queue.items)
    random.shuffle(pool)
    aleatorio = pool[:sample]

    taxa_topo = error_rate(top, accept_threshold=accept_threshold)
    taxa_aleatoria = error_rate(aleatorio, accept_threshold=accept_threshold)
    print()
    print(f"Criterio de aceite da S-22 (amostras de {min(sample, len(queue.items))}):")
    print(f"  topo da fila:      {taxa_topo:.1%} com sinal objetivo de erro")
    print(f"  sorteio da fila:   {taxa_aleatoria:.1%}")
    print(f"  fila inteira:      {error_rate(queue.items, accept_threshold=accept_threshold):.1%}")
    print(f"  varridos:          {queue.scanned_diagrams} diagramas, {len(queue.items)} entraram na fila")


if __name__ == "__main__":
    raise SystemExit(main())
