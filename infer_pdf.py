from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chess_diagram_ocr.board_detection import NoBoardDetectedError, detect_board
from chess_diagram_ocr.config import DEFAULT_MODEL_PATH
from chess_diagram_ocr.inference import load_model, predict_fen_from_board
from chess_diagram_ocr.pdf_io import render_pdf_page


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer board FEN from a PDF page")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=0)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--rotate-180", action="store_true")
    parser.add_argument("--dpi", type=int, default=220)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        page_rgb = render_pdf_page(args.pdf, args.page, dpi=args.dpi)
        board_rgb, _ = detect_board(page_rgb)
    except NoBoardDetectedError as exc:
        raise SystemExit(str(exc))

    model, device = load_model(args.model)
    fen, confidence = predict_fen_from_board(
        board_rgb=board_rgb,
        model=model,
        device=device,
        rotate_180=args.rotate_180,
    )
    print(f"FEN: {fen}")
    print(f"Confidence: {confidence:.3f}")


if __name__ == "__main__":
    main()
