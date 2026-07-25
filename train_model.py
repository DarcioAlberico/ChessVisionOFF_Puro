from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chess_diagram_ocr.config import DEFAULT_DATASET_CSV, DEFAULT_MODEL_PATH, DEFAULT_SAMPLES_DIR
from chess_diagram_ocr.training import train_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Chess Diagram OCR model")
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES_DIR)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=15, help="Number of epochs with no improvement before stopping early")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    history = train_model(
        csv_path=args.csv,
        samples_dir=args.samples,
        model_path=args.model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        patience=args.patience,
    )
    for row in history:
        print(row)


if __name__ == "__main__":
    main()
