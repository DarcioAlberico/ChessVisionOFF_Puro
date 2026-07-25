from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import DEFAULT_DATASET_CSV, DEFAULT_MODEL_PATH, DEFAULT_SAMPLES_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging, default_log_file
from ..training import train_model

logger = logging.getLogger(__name__)

DEFAULT_SPLITS_PATH = PROJECT_ROOT / "data" / "splits.csv"


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
    parser.add_argument(
        "--splits",
        type=Path,
        default=DEFAULT_SPLITS_PATH,
        help="Arquivo de splits persistido. O split 'test' nunca e usado no treino.",
    )
    parser.add_argument(
        "--no-splits",
        action="store_true",
        help="Ignora o arquivo de splits e sorteia a validacao (comportamento antigo, nao recomendado).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Treina do zero, ignorando o checkpoint existente.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nivel DEBUG.")
    return parser.parse_args(argv)


def _log_epoch(row: dict[str, object]) -> None:
    parts = [f"época {row.get('epoch')}/{row.get('total_epochs', '?')}"]
    for key, label in (
        ("train_loss", "train_loss"),
        ("train_acc", "train_acc"),
        ("val_loss", "val_loss"),
        ("val_acc", "val_acc"),
    ):
        if key in row:
            parts.append(f"{label}={float(row[key]):.4f}")  # type: ignore[arg-type]
    logger.info("%s", " | ".join(parts))


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
        progress_cb=_log_epoch,
        fresh=args.fresh,
        splits_path=None if args.no_splits else args.splits,
    )

    logger.info("Treino concluído em %d épocas. Melhor modelo em %s", len(history), args.model)
    if history:
        best = min(history, key=lambda row: row.get("val_loss", row.get("train_loss", float("inf"))))
        logger.info("Melhor época: %s", best)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
