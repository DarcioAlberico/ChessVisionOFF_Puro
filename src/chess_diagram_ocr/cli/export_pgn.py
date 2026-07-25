from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import DEFAULT_MODEL_PATH
from ..logging_setup import configure_logging, default_log_file
from ..pdf_to_pgn import default_pgn_output_path, save_pdf_positions_to_pgn

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Varre um PDF inteiro e salva todas as posicoes encontradas em PGN.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=None, help="Padrao: PGN/<nome-do-pdf>.pgn")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--max-boards-per-page", type=int, default=8)
    parser.add_argument("--rotate-180", action="store_true")
    parser.add_argument("--start-page", type=int, default=0)
    parser.add_argument("--end-page", type=int, default=None, help="Exclusivo. Padrao: ate o fim do PDF.")
    parser.add_argument("--reading-order", choices=("column", "row"), default="column")
    parser.add_argument("--event", type=str, default="ChessVisionOFF PDF OCR")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nivel DEBUG.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    output_path = args.output or default_pgn_output_path(args.pdf)

    def _progress(page_index: int, total_pages: int, page_boards: int, total_positions: int) -> None:
        logger.info(
            "pagina %d/%d | diagramas na pagina: %d | total acumulado: %d",
            page_index + 1,
            total_pages,
            page_boards,
            total_positions,
        )

    positions = save_pdf_positions_to_pgn(
        pdf_source=args.pdf,
        output_path=output_path,
        model_path=args.model,
        dpi=args.dpi,
        max_boards_per_page=args.max_boards_per_page,
        rotate_180=args.rotate_180,
        start_page=args.start_page,
        end_page=args.end_page,
        reading_order=args.reading_order,
        event_name=args.event,
        progress_callback=_progress,
    )

    print(f"PDF: {args.pdf}")
    print(f"PGN: {output_path}")
    print(f"Posicoes salvas: {len(positions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
