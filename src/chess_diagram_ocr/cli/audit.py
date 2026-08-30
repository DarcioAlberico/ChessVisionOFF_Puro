from __future__ import annotations

import argparse
import json
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
from ..config import DEFAULT_DATASET_CSV, PIECE_CLASSES, PROJECT_ROOT
from ..labels import label_origins
from ..logging_setup import configure_logging, default_log_file
from ..splits import load_splits, split_leaks
from . import EXIT_FAILURE, add_dataset_arguments, add_splits_argument, add_verbose, cli_errors

logger = logging.getLogger(__name__)

DEFAULT_QUARANTINE = DEFAULT_DATASET_CSV.parent / "quarantine.csv"
DEFAULT_METRICS_DIR = PROJECT_ROOT / "docs" / "metrics"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita o dataset de rótulos: posições ilegais, duplicatas e arquivos órfãos.",
        epilog="Sem nenhuma flag de correção, apenas relata. Toda escrita cria backup do CSV.",
    )
    add_dataset_arguments(parser, splits=False)
    parser.add_argument(
        "--quarantine-path", type=Path, default=DEFAULT_QUARANTINE, help="CSV de quarentena: para onde vão os rótulos recusados."
    )
    add_splits_argument(parser, help="Arquivo de splits, para relatar amostras que nenhum treino enxerga (S-56).")
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
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Sai com código 1 quando um limite declarado é violado (S-102). Sem ele o comando "
            "relata e sai 0, que é o contrato de quem usa a auditoria para olhar."
        ),
    )
    parser.add_argument(
        "--vazamento-de-texto",
        type=Path,
        help="Relatorio de vazamento da base de caractere. Padrao: docs/metrics/texto_vazamento.json.",
    )
    add_verbose(parser)
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
        print("    À esquerda a linha que o --dedupe mantém: a que declara livro e página, e")
        print("    não a mais antiga -- as anteriores à S-19 não declaram nenhum dos dois (S-452).")
        for fica, saem in report.dedupe_plan()[:limit]:
            print(f"      {fica}  <-  {', '.join(saem)}")

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

    if report.route_counts:
        # Os 625 valores de `corrected_by` que nenhuma tela e nenhum comando liam (S-137). A
        # pergunta que a coluna existe para responder -- "as amostras corrigidas a mao treinam
        # melhor?" -- comeca por saber quantas sao de cada caminho.
        print()
        print("  Por onde o rótulo chegou (coluna `corrected_by`, S-52):")
        total_rotas = sum(report.route_counts.values())
        for rota, quantos in report.route_counts.most_common():
            print(f"    {rota[:38]:40} {quantos:6d}  {quantos / total_rotas:6.1%}")

    print()


def violacoes_do_texto(caminho: Path | None = None) -> list[str]:
    """As violações do último split da base de caractere, ou `[]` quando não há relatório.

    **Não medir não é violação.** Um clone limpo não tem `docs/metrics/texto_vazamento.json`, e
    tratar a ausência como falha faria a auditoria do dataset de diagramas depender de alguém ter
    rodado o treino de texto. Quem produz o arquivo é `cvoff-texto-train`, inclusive no modo
    `--so-split`, que custa um minuto.
    """
    from ..text import procedencia as pr

    alvo = Path(caminho) if caminho is not None else pr.CAMINHO_DO_VAZAMENTO
    if not alvo.exists():
        return []
    try:
        relatorio = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # pragma: no cover - arquivo truncado
        return [f"o relatório de vazamento de caractere não pôde ser lido ({exc})"]
    return pr.violacoes_do_split(relatorio)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    report = audit_dataset(args.csv, args.samples, check_duplicates=not args.skip_duplicates)
    sem_split = filenames_without_split(args.csv, args.splits) if Path(args.splits).exists() else None
    vazamentos = (
        split_leaks(label_origins(args.csv), load_splits(args.splits)) if Path(args.splits).exists() else []
    )
    _print_report(report, limit=args.limit_examples, sem_split=sem_split, vazamentos=vazamentos)

    # A metade da S-201/S-203 que mora aqui: o split da base de caractere não é do `labels.csv`,
    # mas quem responde "esta base pode publicar um número?" é este comando.
    do_texto = violacoes_do_texto(args.vazamento_de_texto)
    if do_texto:
        print("Base de caractere (S-201/S-203):")
        for violacao in do_texto:
            print(f"  - {violacao}")
        print()

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
        return _codigo_de_saida(report, strict=args.strict, extras=do_texto)

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
    # O relatorio **depois** das correcoes: com `--strict`, o que importa e o estado em que o
    # comando deixou o dataset, e nao aquele em que o encontrou.
    return _codigo_de_saida(after, strict=args.strict)


def _codigo_de_saida(report: AuditReport, *, strict: bool, extras: Sequence[str] = ()) -> int:
    """`1` quando `--strict` e há violação; `0` sempre que não (S-102).

    **Sem `--strict` continua saindo 0 mesmo reprovado**, e isso é decisão: o comando é usado
    para *olhar*, e quebrar o código de saída de quem olha trocaria um problema por outro. Quem
    quer o portão pede o portão -- é a CI e o `cvoff-train` que pedem.
    """
    violacoes = [*report.violations(), *extras]
    if not violacoes:
        if strict:
            print("Auditoria estrita: nenhum limite declarado violado.")
            print()
        return 0

    print("Limites declarados violados:")
    for violacao in violacoes:
        print(f"  - {violacao}")
    print()
    if not strict:
        print("Saindo com 0 porque `--strict` não foi pedido. Para transformar isto em portão:")
        print("  cvoff-audit --strict")
        print()
        return 0
    return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
