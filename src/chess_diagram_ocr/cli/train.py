from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..augment import AugmentConfig
from ..config import (
    DEFAULT_BOARD_CACHE_SIZE,
    DEFAULT_DATASET_CSV,
    DEFAULT_MODEL_PATH,
    DEFAULT_SAMPLES_DIR,
    PROJECT_ROOT,
)
from ..logging_setup import configure_logging, default_log_file
from ..model import ArchConfig
from ..training import DEFAULT_CLASS_WEIGHTS, train_model

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
    parser.add_argument("--seed", type=int, default=42, help="Semente. Gravada no checkpoint (S-27).")
    parser.add_argument(
        "--augment",
        default="aug0",
        help=(
            "Aumento dirigido ao acervo (S-40), como as letras de `AugmentConfig.version`: "
            "m=espelhar, h=hachura, s=granulacao, p=papel, i=inversao. Ex.: --augment mhsp. "
            "'aug0' (padrao) e o conjunto generico de antes da S-40. NAO MEDIDO ainda: ligar "
            "muda o modelo, e a comparacao honesta e treinar as duas variantes com a mesma "
            "semente e medir com `cvoff-field`."
        ),
    )
    parser.add_argument(
        "--class-weights",
        choices=["none", "balanced"],
        default=DEFAULT_CLASS_WEIGHTS,
        help="Pesos inversos a frequencia na loss. Medido: 'balanced' nao muda a acuracia por "
        "tabuleiro e triplica as casas erradas (docs/EXPERIMENTS.md).",
    )
    parser.add_argument(
        "--cache-size",
        type=int,
        default=DEFAULT_BOARD_CACHE_SIZE,
        help="Tabuleiros residentes no cache do dataset (S-26). 0 desliga.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="Processos de carregamento. Padrao: min(4, cpus//2). 0 carrega no processo principal.",
    )
    parser.add_argument("--no-calibrate", action="store_true", help="Pula a calibracao de temperatura (S-28).")

    grupo_arch = parser.add_argument_group("arquitetura (S-29)")
    grupo_arch.add_argument("--backbone", choices=["cnn", "mobilenet_v3_small"], default="cnn")
    grupo_arch.add_argument("--channels", choices=["gray", "rgb"], default="gray")
    grupo_arch.add_argument("--image-size", type=int, default=64)
    grupo_arch.add_argument("--head", choices=["linear", "gap"], default="linear")

    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nivel DEBUG.")
    return parser.parse_args(argv)


def _log_epoch(row: dict[str, object]) -> None:
    parts = [f"época {row.get('epoch')}/{row.get('total_epochs', '?')}"]
    for key in ("train_loss", "train_square_acc", "val_loss", "val_square_acc", "val_board_exact_acc"):
        if key in row:
            parts.append(f"{key}={float(row[key]):.6f}")  # type: ignore[arg-type]
    if row.get("is_best"):
        parts.append("★ melhor")
    logger.info("%s", " | ".join(parts))

    recall = row.get("val_per_class_recall")
    if isinstance(recall, dict):
        # Recall por classe importa porque a acuracia por casa e dominada pelas vazias:
        # uma dama que o modelo nunca acerta some dentro de 0,9988.
        piores = sorted((value, name) for name, value in recall.items() if value == value)[:4]
        logger.info("    piores classes: %s", ", ".join(f"{name}={value:.4f}" for value, name in piores))


def _augment_from_letters(texto: str) -> AugmentConfig:
    """`"mhsp"` ou `"augmhsp"` -> `AugmentConfig`. Probabilidades fixas, ligado ou desligado.

    Uma letra liga a transformacao na probabilidade que a S-40 propos; afinar valor por
    valor pela linha de comando seria oferecer um espaco de busca que ninguem mediu.
    """
    letras = texto[3:] if texto.startswith("aug") else texto
    if letras in ("", "0"):
        return AugmentConfig()
    desconhecidas = set(letras) - set("mhspi")
    if desconhecidas:
        raise ValueError(f"Letras desconhecidas em --augment: {''.join(sorted(desconhecidas))} (validas: mhspi)")
    return AugmentConfig(
        hflip=0.5 if "m" in letras else 0.0,
        hatch=0.30 if "h" in letras else 0.0,
        speckle=0.25 if "s" in letras else 0.0,
        paper=0.30 if "p" in letras else 0.0,
        invert=0.03 if "i" in letras else 0.0,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    try:
        augment = _augment_from_letters(args.augment)
    except ValueError as exc:
        print(f"Erro: {exc}")
        return 2
    if not augment.version.endswith("0"):
        logger.info("Aumento dirigido ligado: %s. Isto muda o modelo (S-40).", augment.version)

    run = train_model(
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
        arch=ArchConfig(
            backbone=args.backbone,
            channels=args.channels,
            image_size=args.image_size,
            head=args.head,
        ),
        class_weights=args.class_weights,
        seed=args.seed,
        cache_size=args.cache_size,
        # Diferente do padrao da biblioteca (0): este e um entrypoint com guarda
        # `if __name__ == "__main__"`, entao `spawn` no Windows e seguro aqui.
        num_workers=args.num_workers,
        calibrate=not args.no_calibrate,
        augment=augment,
    )

    logger.info(
        "Melhor época: %d de %d (%s = %.6f).",
        run.best_epoch,
        len(run.history),
        run.best_metric_name,
        run.best_metric,
    )
    if run.ece_after is not None:
        logger.info("Temperatura calibrada: %.4f (ECE no val %.5f → %.5f).", run.temperature, run.ece_before, run.ece_after)
    logger.info("Confira o resultado no conjunto de teste com: cvoff-eval --split test --model %s", args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
