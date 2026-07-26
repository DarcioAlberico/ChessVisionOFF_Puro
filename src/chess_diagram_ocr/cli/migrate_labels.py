"""Migra o `labels.csv` para o esquema com lado a jogar e origem (S-19).

Mora no pacote, e não em `tools/`, pela mesma razão que `cvoff-audit`: a lógica é testável
e reutilizável, e um script solto não entraria no `mypy` nem nos testes.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import DEFAULT_DATASET_CSV
from ..dataset import migrate_labels_csv
from ..logging_setup import configure_logging, default_log_file

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Adiciona as colunas da S-19 ao labels.csv, com backup.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV)
    parser.add_argument(
        "--no-backup",
        dest="backup",
        action="store_false",
        help="Nao grava a copia .bak antes de reescrever. O padrao e gravar.",
    )
    parser.add_argument(
        "--no-infer",
        dest="infer_side",
        action="store_false",
        help=(
            "So adiciona as colunas, sem deduzir lado a jogar pela legalidade (S-17). "
            "O padrao e deduzir onde a posicao impoe a resposta."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nivel DEBUG.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    counters = migrate_labels_csv(args.csv, backup=args.backup, infer_side=args.infer_side)

    print(f"CSV: {args.csv}")
    print(f"  rotulos ................ {counters['total']}")
    print(f"  ja tinham lado a jogar . {counters['ja_tinha']}")
    print(f"  deduzidos da legalidade  {counters['inferido']}")
    print(f"  sem resposta ........... {counters['sem_resposta']} (coluna vazia, e nao 'w')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
