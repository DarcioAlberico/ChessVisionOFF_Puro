"""`cvoff-provenance` — recupera a procedência dos rótulos órfãos (S-52).

Três passos, e a separação entre eles é o item:

    cvoff-provenance --build                 # indexa os 27 PDFs. Caro: horas de CPU.
    cvoff-provenance --match                 # relata a taxa de casamento, sem escrever nada
    cvoff-provenance --match --apply         # grava a procedência recuperada no labels.csv

O `--match` sem `--apply` é o padrão de propósito. Isto escreve em até 3.195 linhas de
trabalho humano de uma vez -- a operação mais ampla que o projeto faz sobre esse arquivo --,
e a taxa de casamento é justamente o número que o item promete reportar em vez de prometer
100%. Ver o histograma de distância antes de gravar é o mínimo.

Construir o índice aceita `--book`, e é assim que ele deve ser construído: um livro por vez,
conferindo a contagem. Um livro reindexado substitui as entradas anteriores dele.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from ..config import DEFAULT_DATASET_CSV, DEFAULT_PDF_DIR, DEFAULT_SAMPLES_DIR
from ..labels import LabelStore
from ..logging_setup import configure_logging, default_log_file
from ..provenance import (
    DEFAULT_DPI,
    DEFAULT_INDEX_PATH,
    DEFAULT_MAX_DISTANCE,
    MatchReport,
    ProvenanceIndex,
    apply_matches,
    build_index,
    match_samples,
    samples_without_provenance,
)

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recupera a procedência dos rótulos órfãos por hash perceptual (S-52).",
        epilog=(
            "A recuperação é parcial por construção: amostra vinda de imagem local, de "
            "recorte à mão ou de PDF fora do acervo não casa. O relatório diz quanto sobrou."
        ),
    )
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV)
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)

    parser.add_argument("--build", action="store_true", help="Constrói (ou amplia) o índice. Caro.")
    parser.add_argument(
        "--book",
        action="append",
        default=[],
        metavar="LIVRO.pdf",
        help="Indexa só estes livros. Repetível. Um livro reindexado substitui o que havia dele.",
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--pages", type=int, default=None, help="Teto de páginas por livro (para ensaiar).")

    parser.add_argument("--match", action="store_true", help="Casa as amostras órfãs contra o índice.")
    parser.add_argument("--max-distance", type=int, default=DEFAULT_MAX_DISTANCE)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava o resultado no labels.csv. Sem isto, o comando só relata.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobrescreve também as 46 linhas que já têm procedência. Elas vieram da "
        "RecognitionOrigin no momento da gravação, que é fonte melhor que um casamento.",
    )
    parser.add_argument("--no-backup", dest="backup", action="store_false")
    parser.add_argument("--json", type=Path, default=None, help="Grava o relatório em JSON.")
    parser.add_argument("--show-distances", type=int, default=12, help="Faixas do histograma listadas.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _run_build(args: argparse.Namespace) -> int:
    base = ProvenanceIndex.load(args.index)
    if base.entries and base.dpi != args.dpi:
        print(f"O índice existente foi construído com dpi={base.dpi}; use --dpi {base.dpi} ou apague-o.")
        return 2

    def _progress(livro: str, pagina: int, total: int, encontrados: int) -> None:
        if pagina % 25 == 0 or pagina == total:
            print(f"  {livro[:46]:48} {pagina}/{total} páginas | {encontrados} diagramas")

    indice = build_index(
        args.pdf_dir,
        dpi=args.dpi,
        books=args.book,
        page_limit=args.pages,
        base=base if base.entries or base.pages_by_book else None,
        progress=_progress,
    )
    indice.save(args.index)

    print()
    print(f"Índice em {args.index}: {len(indice.entries)} diagramas de {len(indice.pages_by_book)} livro(s).")
    for livro, paginas in sorted(indice.pages_by_book.items()):
        quantos = sum(1 for entry in indice.entries if entry.source_pdf == livro)
        print(f"  {livro[:46]:48} {paginas:5d} páginas  {quantos:6d} diagramas")
    print()
    return 0


def _print_report(report: MatchReport, limit: int) -> None:
    print()
    print("=" * 78)
    print("Recuperação de procedência")
    print("=" * 78)
    print(f"  Amostras sem procedência ...... {report.considered}")
    print(f"  Casadas ....................... {report.matched}  ({report.rate:.2%})")
    print(f"  Ambíguas (descartadas) ........ {report.ambiguous}")
    print(f"  Imagem ilegível ............... {report.unreadable}")

    if report.by_book:
        print()
        print("  Por livro")
        for livro, quantas in sorted(report.by_book.items(), key=lambda item: -item[1]):
            print(f"    {livro[:46]:48} {quantas}")

    if report.distances:
        print()
        print("  Histograma da melhor distância (é ele que diz se o limiar está no lugar)")
        faixas = sorted(report.distances.items())[:limit]
        maior = max(report.distances.values())
        for distancia, quantas in faixas:
            barra = "#" * max(1, round(40 * quantas / maior))
            print(f"    {distancia:3d} bits  {quantas:6d}  {barra}")
        if len(report.distances) > limit:
            resto = sum(quantas for d, quantas in sorted(report.distances.items())[limit:])
            print(f"    ... e {resto} amostra(s) em distâncias maiores")
    print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    if not args.build and not args.match:
        print("Nada a fazer: use --build para indexar os PDFs ou --match para casar as amostras.")
        return 2

    if args.build and _run_build(args) != 0:
        return 2

    if not args.match:
        return 0

    indice = ProvenanceIndex.load(args.index)
    if not indice.entries:
        print(f"Índice vazio ou inexistente: {args.index}")
        print("Construa-o primeiro: cvoff-provenance --build --book \"1937 Kemeri.pdf\"")
        return 1

    store = LabelStore(args.csv)
    if not store.exists():
        print(f"CSV de rótulos não encontrado: {args.csv}")
        return 1

    orfaos = samples_without_provenance(store)
    print(f"Índice: {len(indice.entries)} diagramas de {len(indice.pages_by_book)} livro(s).")
    print(f"{len(orfaos)} amostra(s) sem procedência no {args.csv}.")

    report = match_samples(args.samples_dir, indice, orfaos, max_distance=args.max_distance)
    _print_report(report, limit=args.show_distances)

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Relatório em {args.json}")
        print()

    if not args.apply:
        print("Nada foi gravado. Confira a taxa e o histograma acima e rode de novo com --apply.")
        print()
        return 0

    aplicadas = apply_matches(store, report.matches, overwrite=args.overwrite, backup=args.backup)
    print(f"Procedência gravada em {aplicadas} linha(s) de {args.csv}.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
