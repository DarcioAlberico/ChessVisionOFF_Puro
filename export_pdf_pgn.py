from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chess_diagram_ocr.config import DEFAULT_MODEL_PATH
from chess_diagram_ocr.pdf_to_pgn import default_pgn_output_path, save_pdf_positions_to_pgn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Varre um PDF inteiro e salva todas as posicoes em PGN.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--max-boards-per-page", type=int, default=8)
    parser.add_argument("--rotate-180", action="store_true")
    parser.add_argument("--start-page", type=int, default=0)
    parser.add_argument("--end-page", type=int, default=None)
    parser.add_argument("--reading-order", choices=("column", "row"), default="column")
    parser.add_argument("--event", type=str, default="ChessVisionOFF PDF OCR")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output or default_pgn_output_path(args.pdf)

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
    )

    print(f"PDF: {args.pdf}")
    print(f"PGN: {output_path}")
    print(f"Posicoes salvas: {len(positions)}")


if __name__ == "__main__":
    main()
