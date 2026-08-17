"""`cvoff-census` — o que o detector aceita no acervo, e o diff contra a corrida anterior (S-82).

    cvoff-census --csv docs/metrics/deteccao_base.csv        # a linha de base
    cvoff-census --pdf "PDF/Secrets...pdf" --all-pages       # um livro inteiro
    cvoff-census --csv nova.csv --baseline docs/metrics/deteccao_base.csv

O terceiro comando é o item. Ele responde, sem rótulo humano nenhum, a única pergunta que
importa depois de mexer em detecção: **o que sumiu, e algum dos que sumiram era diagrama de
verdade?**

Não carrega modelo. `--pdf-dir` inteiro a 24 páginas por livro leva ~5 min; um livro inteiro
de 1181 páginas, ~8 min.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..config import DEFAULT_MAX_BOARDS, DEFAULT_PDF_DIR, DEFAULT_READING_ORDER
from ..detection_census import (
    DEFAULT_FRONT_MATTER,
    DEFAULT_PAGES_PER_BOOK,
    HISTOGRAM_BIN_PT,
    SUSPECT_BELOW_PT,
    BookCensus,
    CensusDiff,
    DetectionCensus,
    census_book,
    census_collection,
    diff_census,
    read_census_csv,
    write_census_csv,
    write_census_json,
)
from ..logging_setup import configure_logging, default_log_file
from . import cli_errors

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Conta o que o detector de diagramas aceita, por livro, sem carregar modelo (S-82).",
        epilog=(
            "O censo não julga, conta: não há rótulo humano de 'aqui há diagrama' no acervo. "
            "O que ele entrega é uma distribuição e três contagens que denunciam defeito -- "
            "suspeitos, numeração deslocada e gabarito de tamanho misturado."
        ),
    )
    origem = parser.add_mutually_exclusive_group()
    origem.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Acervo inteiro.")
    origem.add_argument("--pdf", type=Path, default=None, help="Um livro só.")

    paginas = parser.add_mutually_exclusive_group()
    paginas.add_argument("--pages", type=int, default=DEFAULT_PAGES_PER_BOOK, help="Páginas amostradas por livro.")
    paginas.add_argument("--all-pages", action="store_true", help="Varre o livro inteiro, sem amostrar.")

    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--max-boards", type=int, default=DEFAULT_MAX_BOARDS)
    parser.add_argument("--reading-order", default=DEFAULT_READING_ORDER, choices=("row", "column"))
    parser.add_argument(
        "--suspect-below-pt",
        type=float,
        default=SUSPECT_BELOW_PT,
        help="Lado em pontos abaixo do qual o candidato é marcado suspeito. Lente, não filtro.",
    )
    parser.add_argument(
        "--front-matter",
        type=int,
        default=DEFAULT_FRONT_MATTER,
        help=(
            "Páginas do começo do livro varridas além da amostra (capa, rosto, prancha). "
            "A amostra as descarta, e é onde a S-143 achou o falso positivo. 0 desliga."
        ),
    )
    parser.add_argument("--csv", type=Path, default=None, help="Grava uma linha por candidato.")
    parser.add_argument("--json", type=Path, default=None, help="Grava o resumo por livro.")
    parser.add_argument("--baseline", type=Path, default=None, help="CSV de uma corrida anterior, para o diff.")
    parser.add_argument(
        "--fail-on-loss",
        action="store_true",
        help="Sai com código 1 se o diff perder algum candidato acima do limiar de suspeita.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _print_book(book: BookCensus) -> None:
    if not book.candidates:
        print(f"  {book.pdf[:52]:54} — sem candidato nas {book.pages_sampled} páginas")
        return
    suspeitos = len(book.suspects)
    marca = f" ⚠ {suspeitos} suspeito(s)" if suspeitos else ""
    fontes = book.by_source
    print(
        f"  {book.pdf[:52]:54} {book.candidates:5d} cand. | "
        f"embutida {fontes.get('embedded', 0):4d} · contorno {fontes.get('contour', 0):4d} | "
        f"aparados {book.trimmed:4d}{marca}"
    )


def _print_histogram(census: DetectionCensus) -> None:
    """O gráfico onde o vale entre glifo e diagrama aparece sozinho."""
    histograma: dict[int, int] = {}
    for book in census.books:
        for faixa, contagem in book.side_histogram().items():
            histograma[faixa] = histograma.get(faixa, 0) + contagem
    if not histograma:
        return

    maior = max(histograma.values())
    limiar = census.suspect_below_pt
    print()
    print(f"  Lado do candidato na página, em pontos (barra de {HISTOGRAM_BIN_PT:.0f} pt)")
    for faixa in sorted(histograma):
        contagem = histograma[faixa]
        barra = "█" * max(1, int(round(40 * contagem / maior)))
        marca = " ⚠" if faixa < limiar else "  "
        print(f"    {faixa:5d} pt {marca} {contagem:6d}  {barra}")


def _print_census(census: DetectionCensus) -> None:
    print()
    print("=" * 78)
    print("Censo de detecção" + (" (livro inteiro)" if census.pages_per_book is None else ""))
    print("=" * 78)
    livros_com_candidato = [book for book in census.books if book.candidates]
    print(f"  Livros ......................... {len(census.books)} ({len(livros_com_candidato)} com candidato)")
    print(f"  Candidatos ..................... {census.candidates}")
    fontes = census.as_dict()["by_source"]
    for fonte, contagem in sorted(fontes.items(), key=lambda kv: -kv[1]):
        share = contagem / census.candidates if census.candidates else 0.0
        rotulo = {"embedded": "imagem embutida", "contour": "contorno"}.get(fonte, fonte)
        print(f"    {rotulo:20} {contagem:6d}  {share:6.1%}")

    _print_histogram(census)

    print()
    print(f"  Sinais de defeito (suspeito = lado < {census.suspect_below_pt:.0f} pt)")
    print(f"    Candidatos suspeitos ................... {census.suspects}")
    print(f"      em quantos livros .................... {len(census.books_with_suspects)}")
    print(f"    Páginas com numeração deslocada ........ {sum(b.pages_numbering_shifted for b in census.books)}")
    print(f"    Páginas com gabarito misturado ......... {sum(b.pages_size_prior_mixed for b in census.books)}")
    if census.suspects:
        print()
        print('    Um suspeito antes de um diagrama consome o número que o [Diagram "N"] do PGN usa;')
        print("    um suspeito ao lado de um diagrama desloca a mediana que serve de gabarito de")
        print("    tamanho, e o prior passa a recusar diagrama real. Ver docs/ANALISE_DETECCAO.md.")
    print()


def _print_diff(mudancas: list[CensusDiff], baseline: Path) -> int:
    print()
    print("=" * 78)
    print(f"Diff contra {baseline}")
    print("=" * 78)
    if not mudancas:
        print("  Nada mudou.")
        print()
        return 0

    perdidos_reais = 0
    for mudanca in mudancas:
        print(
            f"  {mudanca.pdf[:52]:54} +{len(mudanca.gained):4d} / -{len(mudanca.lost):4d} / "
            f"~{len(mudanca.moved):4d}  (dos perdidos, {len(mudanca.lost_suspects)} suspeitos)"
        )
        for row in mudanca.lost_real[:6]:
            perdidos_reais += 1
            print(
                f"      ✗ perdido acima do limiar: p{row.page} #{row.index} "
                f"{row.side_pt:.0f} pt, {row.source}, textura {row.texture:.3f}"
            )
        restantes = len(mudanca.lost_real) - 6
        if restantes > 0:
            perdidos_reais += restantes
            print(f"      ✗ e mais {restantes} acima do limiar")

    print()
    print(f"  Ganhos ......................... {sum(len(m.gained) for m in mudancas)}")
    print(f"  Reajustados (mesma caixa) ...... {sum(len(m.moved) for m in mudancas)}")
    print(f"  Perdas ......................... {sum(len(m.lost) for m in mudancas)}")
    print(f"    das quais suspeitas .......... {sum(len(m.lost_suspects) for m in mudancas)}")
    print(f"    das quais acima do limiar .... {perdidos_reais}  ← é esta que precisa de justificativa")
    print()
    return perdidos_reais


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    pages = None if args.all_pages else args.pages
    comuns = {
        "pages": pages,
        "dpi": args.dpi,
        "max_boards": args.max_boards,
        "reading_order": args.reading_order,
        "suspect_below_pt": args.suspect_below_pt,
        "front_matter": args.front_matter,
    }

    if args.pdf is not None:
        pdf_path = Path(args.pdf)
        if not pdf_path.is_file():
            print(f"PDF não encontrado: {pdf_path}")
            return 2
        alcance = "livro inteiro" if pages is None else f"{pages} página(s)"
        print(f"Varrendo {pdf_path.name} ({alcance})...")
        book = census_book(pdf_path, **comuns)  # type: ignore[arg-type]
        _print_book(book)
        census = DetectionCensus(
            books=[book],
            dpi=args.dpi,
            max_boards=args.max_boards,
            reading_order=args.reading_order,
            pages_per_book=pages,
            suspect_below_pt=args.suspect_below_pt,
            front_matter=args.front_matter,
        )
    else:
        pdf_dir = Path(args.pdf_dir)
        if not pdf_dir.is_dir():
            print(f"Diretório de PDFs não encontrado: {pdf_dir}")
            return 2
        alcance = "livro inteiro" if pages is None else f"{pages} página(s) por livro"
        print(f"Varrendo {pdf_dir} ({alcance})...")
        census = census_collection(pdf_dir, on_book=_print_book, **comuns)  # type: ignore[arg-type]

    _print_census(census)

    if args.csv is not None:
        write_census_csv(args.csv, census)
        print(f"Censo por candidato em {args.csv}")
    if args.json is not None:
        write_census_json(args.json, census)
        print(f"Resumo em {args.json}")

    perdidos_reais = 0
    if args.baseline is not None:
        baseline = Path(args.baseline)
        if not baseline.is_file():
            print(f"Baseline não encontrada: {baseline}")
            return 2
        perdidos_reais = _print_diff(
            diff_census(read_census_csv(baseline), census.rows, suspect_below_pt=args.suspect_below_pt),
            baseline,
        )

    if args.fail_on_loss and perdidos_reais:
        print(f"--fail-on-loss: {perdidos_reais} candidato(s) acima do limiar sumiram.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
