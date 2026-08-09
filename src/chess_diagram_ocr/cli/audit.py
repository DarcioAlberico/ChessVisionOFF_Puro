from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..audit import (
    AuditReport,
    apply_side_to_move_fixes,
    audit_dataset,
    backup_csv,
    filenames_without_split,
    quarantine_fatal_labels,
    remove_duplicate_labels,
)
from ..config import DEFAULT_DATASET_CSV, DEFAULT_SAMPLES_DIR, PIECE_CLASSES
from ..logging_setup import configure_logging, default_log_file

logger = logging.getLogger(__name__)

DEFAULT_QUARANTINE = DEFAULT_DATASET_CSV.parent / "quarantine.csv"
DEFAULT_SPLITS = DEFAULT_DATASET_CSV.parent / "splits.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita o dataset de rótulos: posições ilegais, duplicatas e arquivos órfãos.",
        epilog="Sem nenhuma flag de correção, apenas relata. Toda escrita cria backup do CSV.",
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES_DIR)
    parser.add_argument("--quarantine-path", type=Path, default=DEFAULT_QUARANTINE)
    parser.add_argument(
        "--splits",
        type=Path,
        default=DEFAULT_SPLITS,
        help="Arquivo de splits, para relatar amostras que nenhum treino enxerga (S-56).",
    )
    parser.add_argument(
        "--fix-side-to-move",
        action="store_true",
        help="Corrige as FENs cujo único problema é o lado a jogar assumido errado.",
    )
    parser.add_argument(
        "--quarantine",
        action="store_true",
        help="Move rótulos fatalmente ilegais para o CSV de quarentena.",
    )
    parser.add_argument("--dedupe", action="store_true", help="Remove duplicatas, mantendo a primeira ocorrência.")
    parser.add_argument(
        "--skip-duplicates",
        action="store_true",
        help="Não calcula hashes perceptuais (relatório muito mais rápido).",
    )
    parser.add_argument("--limit-examples", type=int, default=5, help="Exemplos mostrados por categoria.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _print_report(report: AuditReport, limit: int, *, sem_split: list[str] | None = None) -> None:
    fatal = report.of_kind("fatal")
    turn = report.of_kind("lado-a-jogar")
    syntax = report.of_kind("sintaxe")
    missing = report.of_kind("imagem-ausente")

    print()
    print("=" * 78)
    print(f"Auditoria de {report.csv_path}")
    print("=" * 78)
    print(f"  Linhas no CSV .................. {report.total_rows}")
    print(f"  Rótulos utilizáveis ............ {report.valid_rows}")
    print()
    print("  Problemas")
    print(f"    Posição ilegal (fatal) ....... {len(fatal)}")
    print(f"    Lado a jogar invertido ....... {len(turn)}")
    print(f"    FEN não interpretável ........ {len(syntax)}")
    print(f"    Imagem ausente ............... {len(missing)}")
    print(f"    Amostras redundantes ......... {report.duplicate_count} em {len(report.duplicate_groups)} grupos")
    print(f"    Imagens órfãs ................ {len(report.orphan_images)}")
    if sem_split is not None:
        print(f"    Sem split registrado ......... {len(sem_split)}")

    if sem_split:
        print()
        print("  Sem split registrado -- invisíveis a qualquer treino que filtre por split:")
        print("    `cvoff-train` atribui o split que falta antes de montar o dataset (S-56).")
        for filename in sem_split[:limit]:
            print(f"      {filename}")
        if len(sem_split) > limit:
            print(f"      ... e outras {len(sem_split) - limit}")

    if fatal:
        print()
        print("  Posições ilegais -- erro real de anotação, não devem ser treinadas:")
        by_problem: dict[str, int] = {}
        for issue in fatal:
            for problem in issue.problems:
                by_problem[problem] = by_problem.get(problem, 0) + 1
        for problem, count in sorted(by_problem.items(), key=lambda kv: -kv[1]):
            print(f"    {count:4d}  {problem}")
        print()
        for issue in fatal[:limit]:
            print(f"      {issue.filename}  [{', '.join(issue.problems)}]")
            print(f"        {issue.fen}")

    if turn:
        print()
        print("  Lado a jogar invertido -- as peças estão certas, só o turno está errado:")
        print(f"    Corrigível automaticamente: {sum(1 for i in turn if i.suggested_fen)} de {len(turn)}")
        for issue in turn[:limit]:
            print(f"      {issue.filename}")
            print(f"        de : {issue.fen}")
            print(f"        para: {issue.suggested_fen}")

    if report.duplicate_groups:
        print()
        print("  Grupos redundantes -- mesmo diagrama, mesma anotação:")
        print("    São a mesma amostra salva duas vezes ou a mesma página reextraída com")
        print("    recorte diferente. Mesmo sem remover, membros de um grupo precisam ficar")
        print("    no mesmo split, senão a validação mede o que o treino já viu.")
        for group in report.duplicate_groups[:limit]:
            print(f"      {group[0]}  <-  {', '.join(group[1:])}")

    if report.orphan_images:
        print()
        print(f"  Imagens sem linha no CSV ({len(report.orphan_images)}):")
        for name in report.orphan_images[:limit]:
            print(f"      {name}")

    if report.class_counts:
        print()
        print("  Distribuição de classes nas casas rotuladas:")
        total = sum(report.class_counts.values())
        for cls in PIECE_CLASSES:
            count = report.class_counts.get(cls, 0)
            if not count:
                continue
            share = count / total * 100
            bar = "#" * max(1, int(share / 2))
            print(f"    {cls:>5}  {count:7d}  {share:5.2f}%  {bar}")

    print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    report = audit_dataset(args.csv, args.samples, check_duplicates=not args.skip_duplicates)
    sem_split = filenames_without_split(args.csv, args.splits) if Path(args.splits).exists() else None
    _print_report(report, limit=args.limit_examples, sem_split=sem_split)

    mutating = args.fix_side_to_move or args.quarantine or args.dedupe
    if not mutating:
        suggestions = []
        if report.of_kind("lado-a-jogar"):
            suggestions.append("--fix-side-to-move")
        if report.of_kind("fatal"):
            suggestions.append("--quarantine")
        if report.duplicate_groups:
            suggestions.append("--dedupe")
        if suggestions:
            print(f"Nada foi alterado. Para aplicar as correções: cvoff-audit {' '.join(suggestions)}")
            print()
        if sem_split:
            # Nao entra na lista de sugestoes acima porque quem atribui split e o treino, nao
            # a auditoria: atribuir e irreversivel na pratica (S-07), e nao e decisao de um
            # comando cujo contrato e "sem flag, so relata".
            print(f"{len(sem_split)} amostra(s) sem split. O próximo `cvoff-train` as inclui.")
            print()
        return 0

    backup_csv(args.csv)

    if args.fix_side_to_move:
        applied = apply_side_to_move_fixes(args.csv, report)
        print(f"Lado a jogar corrigido em {applied} rótulos.")

    if args.quarantine:
        moved = quarantine_fatal_labels(args.csv, report, args.quarantine_path)
        print(f"{moved} rótulos ilegais movidos para {args.quarantine_path}.")

    if args.dedupe:
        removed = remove_duplicate_labels(args.csv, report)
        print(f"{removed} linhas duplicadas removidas.")

    print()
    print("Reauditando para confirmar...")
    after = audit_dataset(args.csv, args.samples, check_duplicates=not args.skip_duplicates)
    print(f"  Rótulos utilizáveis: {report.valid_rows} -> {after.valid_rows}")
    print(f"  Posições ilegais   : {len(report.of_kind('fatal'))} -> {len(after.of_kind('fatal'))}")
    print(f"  Lado a jogar errado: {len(report.of_kind('lado-a-jogar'))} -> {len(after.of_kind('lado-a-jogar'))}")
    print(f"  Duplicatas         : {report.duplicate_count} -> {after.duplicate_count}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
