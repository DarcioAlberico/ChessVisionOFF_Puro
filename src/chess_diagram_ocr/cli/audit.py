from __future__ import annotations

import argparse
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from ..audit import (
    DUPLICATE_SHARE_CEILING,
    AuditReport,
    apply_side_to_move_fixes,
    audit_dataset,
    backup_csv,
    dedupe_summary,
    drop_missing_labels,
    filenames_without_split,
    orphans_dir_for,
    prune_orphan_images,
    quarantine_fatal_labels,
    remove_duplicate_labels,
    write_dedupe_summary,
)
from ..config import DEFAULT_DATASET_CSV, DEFAULT_SAMPLES_DIR, PIECE_CLASSES, PROJECT_ROOT
from ..labels import label_origins
from ..logging_setup import configure_logging, default_log_file
from ..splits import load_splits, split_leaks

logger = logging.getLogger(__name__)

DEFAULT_QUARANTINE = DEFAULT_DATASET_CSV.parent / "quarantine.csv"
DEFAULT_SPLITS = DEFAULT_DATASET_CSV.parent / "splits.csv"
DEFAULT_METRICS_DIR = PROJECT_ROOT / "docs" / "metrics"


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
        "--prune-orphans",
        action="store_true",
        help="Aposenta os PNGs sem linha no CSV, movendo-os para data/orphans/<data>/ (S-63).",
    )
    parser.add_argument(
        "--drop-missing",
        action="store_true",
        help="Move para a quarentena as linhas cujo PNG sumiu do disco (S-63).",
    )
    parser.add_argument(
        "--skip-duplicates",
        action="store_true",
        help="Não calcula hashes perceptuais (relatório muito mais rápido).",
    )
    parser.add_argument("--limit-examples", type=int, default=5, help="Exemplos mostrados por categoria.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _print_report(
    report: AuditReport,
    limit: int,
    *,
    sem_split: list[str] | None = None,
    vazamentos: Sequence[tuple[tuple[str, str, str], Mapping[str, str]]] = (),
) -> None:
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
    if report.deliberate_illegal:
        print(f"    Ilegais confirmadas à mão .... {len(report.deliberate_illegal)}  (não são problema)")
    print(f"    Lado a jogar invertido ....... {len(turn)}")
    print(f"    FEN não interpretável ........ {len(syntax)}")
    print(f"    Imagem ausente ............... {len(missing)}")
    print(
        f"    Amostras redundantes ......... {report.duplicate_count} em {len(report.duplicate_groups)} grupos"
        f"  ({report.duplicate_share:.1%} dos utilizáveis)"
    )
    print(f"    Imagens órfãs ................ {len(report.orphan_images)}")
    if sem_split is not None:
        print(f"    Sem split registrado ......... {len(sem_split)}")
    if vazamentos:
        print(f"    Mesmo diagrama em 2+ splits .. {len(vazamentos)}  (S-98)")

    if report.duplicates_above_ceiling:
        # O teto da S-63 existe porque a redundancia cresceu de 234 para 248 sem nada notar.
        # E um alerta, nao uma falha: recorte diferente da mesma pagina e aumento de dados
        # legitimo, e o comando nao tem autoridade para decidir que 11% e demais.
        print()
        print(
            f"  !! Redundância acima do teto: {report.duplicate_share:.1%} > {DUPLICATE_SHARE_CEILING:.0%} (S-63)."
        )
        # A frase anterior aqui era "membros de um grupo continuam no mesmo split, entao a
        # validacao segue honesta". Ela e verdadeira pela definicao de grupo e vazia na
        # pratica (S-98): o grupo e `placement` igual + dHash <= 3, e o mesmo diagrama
        # reextraido com recorte deslocado nao cai nele. Quem responde de verdade por
        # vazamento e a secao abaixo, que compara procedencia.
        print("     Membros de um mesmo grupo caem no mesmo split; o que o grupo não vê está abaixo.")
        print("     O que isto vigia é o crescimento: confira de onde vêm os grupos novos antes de treinar.")

    if vazamentos:
        print()
        print(f"  Mesmo diagrama impresso em splits diferentes ({len(vazamentos)}) -- vazamento de treino:")
        print("    A tripla (livro, página, diagrama) é exata: são a mesma posição impressa,")
        print("    salva mais de uma vez com recorte diferente. O guarda de imagem não os vê.")
        print("    Isto **lista e não move**: mover linha de `test` é irreversível na prática,")
        print("    e a direção que não contamina é sempre em direção ao `train`.")
        for (pdf, pagina, diagrama), membros in vazamentos[:limit]:
            print(f"      {pdf} p{pagina} d{diagrama}")
            for nome, split in membros.items():
                print(f"        {nome}  [{split}]")
        if len(vazamentos) > limit:
            print(f"      ... e outros {len(vazamentos) - limit}")

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

    if report.deliberate_illegal:
        print()
        print("  Ilegais confirmadas -- o livro desenha assim (estrutura de peões, final parcial):")
        print("    Treinam normalmente e o --fix não as toca. Para desfazer uma, esvazie a")
        print("    coluna `illegal_ok` da linha, ou corrija a FEN pela aba Dataset.")
        for issue in report.deliberate_illegal[:limit]:
            print(f"      {issue.filename}  [{', '.join(issue.problems)}]")
        if len(report.deliberate_illegal) > limit:
            print(f"      ... e outras {len(report.deliberate_illegal) - limit}")

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

    if missing:
        print()
        print(f"  Rótulos cujo PNG sumiu ({len(missing)}) -- descartados em silêncio no treino:")
        for issue in missing[:limit]:
            print(f"      {issue.filename}")
        if len(missing) > limit:
            print(f"      ... e outros {len(missing) - limit}")

    if report.orphan_images:
        bytes_orfaos = sum(
            (report.samples_dir / name).stat().st_size
            for name in report.orphan_images
            if (report.samples_dir / name).exists()
        )
        print()
        print(f"  Imagens sem linha no CSV ({len(report.orphan_images)}, {bytes_orfaos / 1024 / 1024:.1f} MiB):")
        for name in report.orphan_images[:limit]:
            print(f"      {name}")
        if len(report.orphan_images) > limit:
            print(f"      ... e outras {len(report.orphan_images) - limit}")

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
    vazamentos = (
        split_leaks(label_origins(args.csv), load_splits(args.splits)) if Path(args.splits).exists() else []
    )
    _print_report(report, limit=args.limit_examples, sem_split=sem_split, vazamentos=vazamentos)

    mutating = args.fix_side_to_move or args.quarantine or args.dedupe or args.prune_orphans or args.drop_missing
    if not mutating:
        suggestions = []
        if report.of_kind("lado-a-jogar"):
            suggestions.append("--fix-side-to-move")
        if report.of_kind("fatal"):
            suggestions.append("--quarantine")
        if report.duplicate_groups:
            suggestions.append("--dedupe")
        if report.of_kind("imagem-ausente"):
            suggestions.append("--drop-missing")
        if report.orphan_images:
            suggestions.append("--prune-orphans")
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

    if args.dedupe:
        # **Antes** de remover, porque depois nao ha como saber de que split cada linha saiu:
        # o resumo e o denominador de toda medicao anterior a esta limpeza (S-101).
        caminho = write_dedupe_summary(
            dedupe_summary(report, args.splits),
            DEFAULT_METRICS_DIR,
            stamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        print(f"Resumo do dedupe em {caminho}")

    if args.fix_side_to_move:
        applied = apply_side_to_move_fixes(args.csv, report)
        print(f"Lado a jogar corrigido em {applied} rótulos.")

    if args.quarantine:
        moved = quarantine_fatal_labels(args.csv, report, args.quarantine_path)
        print(f"{moved} rótulos ilegais movidos para {args.quarantine_path}.")

    if args.dedupe:
        removed = remove_duplicate_labels(args.csv, report)
        print(f"{removed} linhas duplicadas removidas.")

    if args.drop_missing:
        dropped = drop_missing_labels(args.csv, report, args.quarantine_path)
        print(f"{dropped} rótulo(s) sem imagem movido(s) para {args.quarantine_path}.")

    if args.prune_orphans:
        # Depois do `--drop-missing` de proposito: apagar uma linha cria um orfao, e rodar as
        # duas na mesma chamada tem de aposentar tambem o que a primeira acabou de orfanar.
        alvo = report if not args.drop_missing else audit_dataset(args.csv, args.samples, check_duplicates=False)
        aposentados = prune_orphan_images(alvo)
        if aposentados:
            print(f"{len(aposentados)} imagem(ns) órfã(s) movida(s) para {aposentados[0].parent}.")
        else:
            print("Nenhuma imagem órfã a mover.")

    print()
    print("Reauditando para confirmar...")
    after = audit_dataset(args.csv, args.samples, check_duplicates=not args.skip_duplicates)
    print(f"  Rótulos utilizáveis: {report.valid_rows} -> {after.valid_rows}")
    print(f"  Posições ilegais   : {len(report.of_kind('fatal'))} -> {len(after.of_kind('fatal'))}")
    print(f"  Lado a jogar errado: {len(report.of_kind('lado-a-jogar'))} -> {len(after.of_kind('lado-a-jogar'))}")
    print(f"  Imagem ausente     : {len(report.of_kind('imagem-ausente'))} -> {len(after.of_kind('imagem-ausente'))}")
    print(f"  Imagens órfãs      : {len(report.orphan_images)} -> {len(after.orphan_images)}")
    print(f"  Duplicatas         : {report.duplicate_count} -> {after.duplicate_count}")
    if args.prune_orphans and not after.orphan_images and not after.of_kind("imagem-ausente"):
        # O criterio de aceite da S-63, verificado no proprio comando em vez de prometido.
        print("  → data/samples/ e labels.csv têm o mesmo conjunto de nomes.")
    if args.prune_orphans:
        print()
        print(f"Nada foi apagado do disco: os órfãos estão em {orphans_dir_for(args.samples)}.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
