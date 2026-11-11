from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
from ..relogio import agora
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


@dataclass(frozen=True)
class _Achados:
    """O que o relatório imprime: a auditoria, e o que o `splits.csv` acrescenta a ela."""

    report: AuditReport
    limit: int
    sem_split: list[str] | None
    vazamentos: Sequence[tuple[tuple[str, str, str], Mapping[str, str]]]


def _e_outros(itens: Sequence[object], limit: int, palavra: str) -> list[str]:
    """A linha `... e outros N` de toda lista cortada em `limit`, ou nada quando coube."""
    return [f"      ... e {palavra} {len(itens) - limit}"] if len(itens) > limit else []


def _lista(cabecalho: Sequence[str], linhas: Sequence[str], limit: int, palavra: str) -> list[str]:
    """Uma seção que é uma lista: o cabeçalho, as `limit` primeiras linhas, e quantas sobraram."""
    return ["", *cabecalho, *linhas[:limit], *_e_outros(linhas, limit, palavra)]


def _cabecalho(a: _Achados) -> list[str]:
    report = a.report
    linhas = [
        "",
        "=" * 78,
        f"Auditoria de {report.csv_path}",
        "=" * 78,
        f"  Linhas no CSV .................. {report.total_rows}",
        f"  Rótulos utilizáveis ............ {report.valid_rows}",
        "",
        "  Problemas",
        f"    Posição ilegal (fatal) ....... {len(report.of_kind('fatal'))}",
    ]
    if report.deliberate_illegal:
        linhas.append(f"    Ilegais confirmadas à mão .... {len(report.deliberate_illegal)}  (não são problema)")
    linhas += [
        f"    Lado a jogar invertido ....... {len(report.of_kind('lado-a-jogar'))}",
        f"    FEN não interpretável ........ {len(report.of_kind('sintaxe'))}",
        f"    Imagem ausente ............... {len(report.of_kind('imagem-ausente'))}",
        f"    Amostras redundantes ......... {report.duplicate_count} em {len(report.duplicate_groups)} grupos"
        f"  ({report.duplicate_share:.1%} dos utilizáveis)",
        f"    Imagens órfãs ................ {len(report.orphan_images)}",
    ]
    if a.sem_split is not None:
        linhas.append(f"    Sem split registrado ......... {len(a.sem_split)}")
    if a.vazamentos:
        linhas.append(f"    Mesmo diagrama em 2+ splits .. {len(a.vazamentos)}  (S-98)")
    return linhas


def _teto_de_redundancia(a: _Achados) -> list[str]:
    if not a.report.duplicates_above_ceiling:
        return []
    # O teto da S-63 existe porque a redundancia cresceu de 234 para 248 sem nada notar.
    # E um alerta, nao uma falha: recorte diferente da mesma pagina e aumento de dados
    # legitimo, e o comando nao tem autoridade para decidir que 11% e demais.
    #
    # A frase anterior aqui era "membros de um grupo continuam no mesmo split, entao a
    # validacao segue honesta". Ela e verdadeira pela definicao de grupo e vazia na
    # pratica (S-98): o grupo e `placement` igual + dHash <= 3, e o mesmo diagrama
    # reextraido com recorte deslocado nao cai nele. Quem responde de verdade por
    # vazamento e a secao abaixo, que compara procedencia.
    return [
        "",
        f"  !! Redundância acima do teto: {a.report.duplicate_share:.1%} > {DUPLICATE_SHARE_CEILING:.0%} (S-63).",
        "     Membros de um mesmo grupo caem no mesmo split; o que o grupo não vê está abaixo.",
        "     O que isto vigia é o crescimento: confira de onde vêm os grupos novos antes de treinar.",
    ]


def _vazamentos(a: _Achados) -> list[str]:
    if not a.vazamentos:
        return []
    linhas = [
        "",
        f"  Mesmo diagrama impresso em splits diferentes ({len(a.vazamentos)}) -- vazamento de treino:",
        "    A tripla (livro, página, diagrama) é exata: são a mesma posição impressa,",
        "    salva mais de uma vez com recorte diferente. O guarda de imagem não os vê.",
        "    Isto **lista e não move**: mover linha de `test` é irreversível na prática,",
        "    e a direção que não contamina é sempre em direção ao `train`.",
    ]
    for (pdf, pagina, diagrama), membros in a.vazamentos[: a.limit]:
        linhas.append(f"      {pdf} p{pagina} d{diagrama}")
        linhas += [f"        {nome}  [{split}]" for nome, split in membros.items()]
    return linhas + _e_outros(a.vazamentos, a.limit, "outros")


def _sem_split(a: _Achados) -> list[str]:
    if not a.sem_split:
        return []
    cabecalho = (
        "  Sem split registrado -- invisíveis a qualquer treino que filtre por split:",
        "    `cvoff-train` atribui o split que falta antes de montar o dataset (S-56).",
    )
    return _lista(cabecalho, [f"      {filename}" for filename in a.sem_split], a.limit, "outras")


def _fatais(a: _Achados) -> list[str]:
    fatal = a.report.of_kind("fatal")
    if not fatal:
        return []
    linhas = ["", "  Posições ilegais -- erro real de anotação, não devem ser treinadas:"]
    by_problem: dict[str, int] = {}
    for issue in fatal:
        for problem in issue.problems:
            by_problem[problem] = by_problem.get(problem, 0) + 1
    linhas += [f"    {count:4d}  {problem}" for problem, count in sorted(by_problem.items(), key=lambda kv: -kv[1])]
    linhas.append("")
    for issue in fatal[: a.limit]:
        linhas += [f"      {issue.filename}  [{', '.join(issue.problems)}]", f"        {issue.fen}"]
    return linhas


def _ilegais_confirmadas(a: _Achados) -> list[str]:
    confirmadas = a.report.deliberate_illegal
    if not confirmadas:
        return []
    cabecalho = (
        "  Ilegais confirmadas -- o livro desenha assim (estrutura de peões, final parcial):",
        "    Treinam normalmente e o --fix não as toca. Para desfazer uma, esvazie a",
        "    coluna `illegal_ok` da linha, ou corrija a FEN pela aba Dataset.",
    )
    linhas = [f"      {issue.filename}  [{', '.join(issue.problems)}]" for issue in confirmadas]
    return _lista(cabecalho, linhas, a.limit, "outras")


def _lado_a_jogar(a: _Achados) -> list[str]:
    turn = a.report.of_kind("lado-a-jogar")
    if not turn:
        return []
    linhas = [
        "",
        "  Lado a jogar invertido -- as peças estão certas, só o turno está errado:",
        f"    Corrigível automaticamente: {sum(1 for i in turn if i.suggested_fen)} de {len(turn)}",
    ]
    for issue in turn[: a.limit]:
        linhas += [f"      {issue.filename}", f"        de : {issue.fen}", f"        para: {issue.suggested_fen}"]
    return linhas


def _redundantes(a: _Achados) -> list[str]:
    if not a.report.duplicate_groups:
        return []
    return [
        "",
        "  Grupos redundantes -- mesmo diagrama, mesma anotação:",
        "    São a mesma amostra salva duas vezes ou a mesma página reextraída com",
        "    recorte diferente. Mesmo sem remover, membros de um grupo precisam ficar",
        "    no mesmo split, senão a validação mede o que o treino já viu.",
        "    À esquerda a linha que o --dedupe mantém: a que declara livro e página, e",
        "    não a mais antiga -- as anteriores à S-19 não declaram nenhum dos dois (S-452).",
        *(f"      {fica}  <-  {', '.join(saem)}" for fica, saem in a.report.dedupe_plan()[: a.limit]),
    ]


def _ausentes(a: _Achados) -> list[str]:
    missing = a.report.of_kind("imagem-ausente")
    if not missing:
        return []
    cabecalho = (f"  Rótulos cujo PNG sumiu ({len(missing)}) -- descartados em silêncio no treino:",)
    return _lista(cabecalho, [f"      {issue.filename}" for issue in missing], a.limit, "outros")


def _orfas(a: _Achados) -> list[str]:
    report = a.report
    if not report.orphan_images:
        return []
    bytes_orfaos = sum(
        (report.samples_dir / name).stat().st_size
        for name in report.orphan_images
        if (report.samples_dir / name).exists()
    )
    cabecalho = (f"  Imagens sem linha no CSV ({len(report.orphan_images)}, {bytes_orfaos / 1024 / 1024:.1f} MiB):",)
    return _lista(cabecalho, [f"      {name}" for name in report.orphan_images], a.limit, "outras")


def _classes(a: _Achados) -> list[str]:
    contagem = a.report.class_counts
    if not contagem:
        return []
    linhas = ["", "  Distribuição de classes nas casas rotuladas:"]
    total = sum(contagem.values())
    for cls in PIECE_CLASSES:
        count = contagem.get(cls, 0)
        if count:
            share = count / total * 100
            linhas.append(f"    {cls:>5}  {count:7d}  {share:5.2f}%  {'#' * max(1, int(share / 2))}")
    return linhas


def _rotas(a: _Achados) -> list[str]:
    # Os 625 valores de `corrected_by` que nenhuma tela e nenhum comando liam (S-137). A
    # pergunta que a coluna existe para responder -- "as amostras corrigidas a mao treinam
    # melhor?" -- comeca por saber quantas sao de cada caminho.
    rotas = a.report.route_counts
    if not rotas:
        return []
    total_rotas = sum(rotas.values())
    return [
        "",
        "  Por onde o rótulo chegou (coluna `corrected_by`, S-52):",
        *(f"    {rota[:38]:40} {quantos:6d}  {quantos / total_rotas:6.1%}" for rota, quantos in rotas.most_common()),
    ]


_SECOES = (
    _cabecalho,
    _teto_de_redundancia,
    _vazamentos,
    _sem_split,
    _fatais,
    _ilegais_confirmadas,
    _lado_a_jogar,
    _redundantes,
    _ausentes,
    _orfas,
    _classes,
    _rotas,
)
"""O relatório, na ordem em que sai. Cada seção devolve as linhas dela, vazia quando não há o que dizer."""


def _print_report(
    report: AuditReport,
    limit: int,
    *,
    sem_split: list[str] | None = None,
    vazamentos: Sequence[tuple[tuple[str, str, str], Mapping[str, str]]] = (),
) -> None:
    achados = _Achados(report, limit, sem_split, vazamentos)
    for secao in _SECOES:
        for linha in secao(achados):
            print(linha)
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


def _corrige_algo(args: argparse.Namespace) -> bool:
    """Se alguma flag que escreve foi pedida. Sem nenhuma o comando só relata, que é o contrato dele."""
    return args.fix_side_to_move or args.quarantine or args.dedupe or args.prune_orphans or args.drop_missing


def _sugestoes(report: AuditReport) -> list[str]:
    """As flags que consertariam o que a auditoria achou, na ordem em que o comando as sugere. Pura."""
    pares = (
        ("--fix-side-to-move", bool(report.of_kind("lado-a-jogar"))),
        ("--quarantine", bool(report.of_kind("fatal"))),
        ("--dedupe", bool(report.duplicate_groups)),
        ("--drop-missing", bool(report.of_kind("imagem-ausente"))),
        ("--prune-orphans", bool(report.orphan_images)),
    )
    return [flag for flag, vale in pares if vale]


def _so_relatar(report: AuditReport, sem_split: list[str] | None) -> None:
    flags = _sugestoes(report)
    if flags:
        print(f"Nada foi alterado. Para aplicar as correções: cvoff-audit {' '.join(flags)}")
        print()
    if sem_split:
        # Nao entra na lista de sugestoes acima porque quem atribui split e o treino, nao
        # a auditoria: atribuir e irreversivel na pratica (S-07), e nao e decisao de um
        # comando cujo contrato e "sem flag, so relata".
        print(f"{len(sem_split)} amostra(s) sem split. O próximo `cvoff-train` as inclui.")
        print()


def _corrigir(args: argparse.Namespace, report: AuditReport) -> None:
    """Aplica as correções pedidas, na ordem que importa, com backup do CSV antes."""
    backup_csv(args.csv)

    if args.dedupe:
        # **Antes** de remover, porque depois nao ha como saber de que split cada linha saiu:
        # o resumo e o denominador de toda medicao anterior a esta limpeza (S-101).
        caminho = write_dedupe_summary(
            dedupe_summary(report, args.splits),
            DEFAULT_METRICS_DIR,
            stamp=agora().strftime("%Y%m%d_%H%M%S"),
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
        _aposentar_orfaos(args, report)


def _aposentar_orfaos(args: argparse.Namespace, report: AuditReport) -> None:
    # Depois do `--drop-missing` de proposito: apagar uma linha cria um orfao, e rodar as
    # duas na mesma chamada tem de aposentar tambem o que a primeira acabou de orfanar.
    alvo = report if not args.drop_missing else audit_dataset(args.csv, args.samples, check_duplicates=False)
    aposentados = prune_orphan_images(alvo)
    if aposentados:
        print(f"{len(aposentados)} imagem(ns) órfã(s) movida(s) para {aposentados[0].parent}.")
    else:
        print("Nenhuma imagem órfã a mover.")


def _reauditar(args: argparse.Namespace, report: AuditReport) -> AuditReport:
    """Audita de novo e mostra o antes e o depois das correções, contagem por contagem."""
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
    return after


def _imprimir_texto(violacoes: Sequence[str]) -> None:
    if violacoes:
        print("Base de caractere (S-201/S-203):")
        for violacao in violacoes:
            print(f"  - {violacao}")
        print()


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    report = audit_dataset(args.csv, args.samples, check_duplicates=not args.skip_duplicates)
    tem_splits = Path(args.splits).exists()
    sem_split = filenames_without_split(args.csv, args.splits) if tem_splits else None
    vazamentos = split_leaks(label_origins(args.csv), load_splits(args.splits)) if tem_splits else []
    _print_report(report, limit=args.limit_examples, sem_split=sem_split, vazamentos=vazamentos)

    # A metade da S-201/S-203 que mora aqui: o split da base de caractere não é do `labels.csv`,
    # mas quem responde "esta base pode publicar um número?" é este comando.
    do_texto = violacoes_do_texto(args.vazamento_de_texto)
    _imprimir_texto(do_texto)

    if not _corrige_algo(args):
        _so_relatar(report, sem_split)
        return _codigo_de_saida(report, strict=args.strict, extras=do_texto)

    _corrigir(args, report)
    after = _reauditar(args, report)
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
