"""`cvoff-experiment`: roda a grade da S-29 e imprime a tabela para docs/EXPERIMENTS.md."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..audit import filenames_without_split
from ..config import DEFAULT_DATASET_CSV, DEFAULT_SAMPLES_DIR, PROJECT_ROOT
from ..experiments import default_grid, markdown_table, run_variant, save_results
from ..logging_setup import configure_logging, default_log_file
from ..splits import load_splits

logger = logging.getLogger(__name__)

DEFAULT_SPLITS_PATH = PROJECT_ROOT / "data" / "splits.csv"
DEFAULT_WORKDIR = PROJECT_ROOT / "models" / "experiments"
DEFAULT_JSON = PROJECT_ROOT / "docs" / "metrics" / "experiments.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade de experimentos de arquitetura (S-29).")
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES_DIR)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS_PATH)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR, help="Onde ficam os checkpoints da grade.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--epochs", type=int, default=4, help="Epocas por variante. Iguais para todas, por justica.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument("--only", nargs="*", default=None, help="Roda so estas variantes, pelo nome.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    splits = load_splits(args.splits)
    if not splits:
        print(f"Arquivo de splits vazio ou ausente: {args.splits}")
        return 1

    # A grade le a particao uma vez e nao a escreve (S-106). Amostra sem split ficaria
    # invisivel as variantes **e** a avaliacao, entao a recusa e antes de comecar: descobrir
    # isso depois de sete treinos custa horas.
    sem_split = filenames_without_split(args.csv, args.splits)
    if sem_split:
        print(f"{len(sem_split)} amostra(s) sem split registrado, e a grade não atribui split.")
        print("Elas ficariam invisíveis a todas as variantes, e a comparação sairia sobre um")
        print("dataset menor do que o que existe.")
        print()
        print("Atribua o split rodando um treino comum uma vez, antes da grade:")
        print("    cvoff-train --epochs 1")
        return 1

    grid = default_grid()
    if args.only:
        wanted = set(args.only)
        desconhecidas = wanted - {variant.name for variant in grid}
        if desconhecidas:
            print(f"Variantes desconhecidas: {', '.join(sorted(desconhecidas))}")
            print(f"Disponiveis: {', '.join(variant.name for variant in grid)}")
            return 1
        grid = [variant for variant in grid if variant.name in wanted]

    logger.info(
        "Grade da S-29: %d variantes x %d epocas, semente %d, comparadas no split 'val'.",
        len(grid),
        args.epochs,
        args.seed,
    )

    results = []
    for position, variant in enumerate(grid, start=1):
        logger.info("[%d/%d] %s (%s)", position, len(grid), variant.name, variant.arch.version)
        results.append(
            run_variant(
                variant,
                csv_path=args.csv,
                samples_dir=args.samples,
                splits_path=args.splits,
                splits=splits,
                workdir=args.workdir,
                epochs=args.epochs,
                seed=args.seed,
                batch_size=args.batch_size,
                num_workers=args.num_workers,
            )
        )
        save_results(results, args.json)  # grava a cada variante: a grade e longa e pode ser interrompida

    print()
    print(markdown_table(results))
    print()
    print(f"JSON em {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
