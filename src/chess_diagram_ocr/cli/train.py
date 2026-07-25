from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import DEFAULT_DATASET_CSV, DEFAULT_MODEL_PATH, DEFAULT_SAMPLES_DIR
from ..logging_setup import configure_logging, default_log_file
from ..training import train_model

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Treina o classificador de pecas do Chess Diagram OCR.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV, help="CSV de rotulos (filename,fen).")
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES_DIR, help="Pasta com as imagens dos tabuleiros.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Caminho do checkpoint .pt.")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument(
        "--patience",
        type=int,
        default=15,
        help="Epocas sem melhora antes de parar antecipadamente. 0 desativa.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nivel DEBUG.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

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
        logger.info("%s", row)
    logger.info("Treino concluido em %d epocas. Melhor modelo em %s", len(history), args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
