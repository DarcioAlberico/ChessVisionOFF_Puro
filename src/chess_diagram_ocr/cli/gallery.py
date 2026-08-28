"""`cvoff-gallery` — o extrato do trabalho humano da galeria, e a volta dele (S-115).

    cvoff-gallery --export-human            # data/gallery/ -> data/gallery_human.jsonl
    cvoff-gallery --import-human            # o caminho de volta, depois de um desastre
    cvoff-gallery --census                  # quanto há, e quanto disso é irrecuperável

**Por que só metade da galeria é versionada.** `data/gallery/` são 13 MB em que o
`*.index.json` é derivado do PDF e o `<livro>.json` descreve o conteúdo de um livro protegido
-- os dois motivos pelos quais a pasta está no `.gitignore`, e os dois continuam válidos. Mas
dentro dela existe trabalho que **varredura nenhuma reconstrói**: a vez a jogar que alguém
conferiu na legenda impressa, e as partidas escolhidas a mão entre as candidatas (S-86).

O que a base preencheu volta com `cvoff-games --apply` a partir do cache de posições. O que
uma pessoa decidiu não volta -- e é exatamente o que este comando separa.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..gallery import (
    DEFAULT_GALLERY_DIR,
    DEFAULT_HUMAN_EXTRACT,
    HumanExtract,
    export_human,
    read_human_extract,
    restore_human,
    write_human_extract,
)
from ..logging_setup import configure_logging, default_log_file
from . import EXIT_BAD_INPUT, add_verbose, cli_errors

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai e restaura o trabalho humano das anotações da Galeria (S-115).",
        epilog=(
            "O extrato é o que se versiona: o resto da galeria é derivado do PDF ou volta "
            "com `cvoff-games --apply`."
        ),
    )
    parser.add_argument(
        "--gallery-dir", type=Path, default=DEFAULT_GALLERY_DIR, help="Pasta dos índices da Galeria."
    )
    parser.add_argument("--extract", type=Path, default=DEFAULT_HUMAN_EXTRACT, help="O .jsonl do extrato.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--export-human", action="store_true", help="Galeria -> extrato.")
    grupo.add_argument(
        "--import-human",
        action="store_true",
        help="Extrato -> galeria. O que veio da pessoa vence o que a base preencheu.",
    )
    grupo.add_argument("--census", action="store_true", help="Conta sem gravar nada.")
    add_verbose(parser)
    return parser.parse_args(argv)


def _census(extrato: HumanExtract) -> None:
    registros = extrato.records
    escolhas = sum(1 for registro in registros if registro.get("chosen_game"))
    vezes = sum(1 for registro in registros if registro.get("side_to_move"))
    lances = sum(1 for registro in registros if registro.get("move_number"))
    headers = sum(len(registro.get("headers") or {}) for registro in registros)  # type: ignore[arg-type]

    print(f"  Diagramas com algo humano ...... {len(registros)} em {extrato.books} livro(s)")
    print(f"    partida escolhida a mão ...... {escolhas}")
    print(f"    vez a jogar declarada ........ {vezes}")
    print(f"    número do lance .............. {lances}")
    print(f"    campos de header ............. {headers}")
    if extrato.unresolved:
        # Sem esta linha, um extrato pequeno pareceria "ha pouco trabalho humano" quando o
        # que ha e trabalho que nao da para separar do que a base preencheu.
        print()
        print(f"  !! {extrato.unresolved} anotação(ões) sem procedência por campo, fora do extrato.")
        print("     São anteriores à correção da S-72: têm a partida que preencheu, mas não")
        print("     **quais campos** ela preencheu, e ali o que a base escreveu é indistinguível")
        print("     do que alguém digitou. Chamá-las de humanas inventaria procedência.")
        print("     Conserto: `cvoff-games --apply` devolve o `filled_fields` a elas; depois")
        print("     disso, `--export-human` de novo separa o que sobrar.")


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    if args.import_human:
        registros = read_human_extract(args.extract)
        if not registros:
            print(f"Extrato vazio ou inexistente: {args.extract}")
            return EXIT_BAD_INPUT
        por_livro = restore_human(registros, directory=args.gallery_dir)
        print(f"{sum(por_livro.values())} diagrama(s) restaurados em {len(por_livro)} livro(s):")
        for livro, quantos in sorted(por_livro.items()):
            print(f"  {livro[:60]:62} {quantos}")
        return 0

    extrato = export_human(directory=args.gallery_dir)
    if args.census:
        print(f"Galeria em {args.gallery_dir}")
        _census(extrato)
        return 0

    caminho = write_human_extract(extrato.records, args.extract)
    print(f"Extrato em {caminho}")
    _census(extrato)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
