"""`cvoff-sides` — o critério de saída da Fase 8, medido em vez de estimado.

    cvoff-sides                          # só a camada de texto: o projeto como sempre foi
    cvoff-sides --ocr rapidocr           # com o motor da S-42/S-43
    cvoff-sides --json docs/metrics/sides_com_ocr.json

A comparação é o item: o mesmo comando com e sem `--ocr` responde, em dois números, se o
motor entregou o que a Fase 8 existe para entregar.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import DEFAULT_MODEL_PATH, DEFAULT_PDF_DIR
from ..logging_setup import configure_logging, default_log_file
from ..service import OcrService, RecognitionOptions
from ..side_survey import (
    DEFAULT_PAGES_PER_BOOK,
    BookSides,
    SideSurvey,
    source_label,
    survey_collection,
    write_survey,
)
from ._ocr import OFF, add_ocr_argument, caption_reader_from_args

logger = logging.getLogger(__name__)

EXIT_CRITERION_BOOKS = 12
"""Doze dos 27, que é o que a Fase 8 escreveu no critério de saída."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mede em quantos livros do acervo o lado a jogar deixa de ser assumido (Fase 8).",
        epilog=(
            "A manchete usa a letra do critério -- procedência diferente de 'default'. A "
            "coluna de texto é o que a Fase 8 acrescentou; a de legalidade já existia."
        ),
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES_PER_BOOK, help="Páginas amostradas por livro.")
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--max-boards", type=int, default=12)
    parser.add_argument("--orientation", default="auto", choices=("auto", "0", "180"))
    parser.add_argument("--json", type=Path, default=None, help="Grava o levantamento em JSON.")
    add_ocr_argument(parser)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _print_book(book: BookSides) -> None:
    if not book.diagrams:
        print(f"  {book.pdf[:52]:54} — sem diagrama nas {book.pages_sampled} páginas amostradas")
        return
    print(
        f"  {book.pdf[:52]:54} {book.diagrams:4d} diagramas | "
        f"texto {book.from_text:3d} · legalidade {book.from_legality:3d} · assumido {book.assumed:3d} | "
        f"resolvidos {book.resolved_share:.0%}"
    )


def _print_survey(survey: SideSurvey) -> None:
    print()
    print("=" * 78)
    print("Procedência do lado a jogar no acervo" + (f" (OCR: {survey.ocr_engine})" if survey.ocr_engine else ""))
    print("=" * 78)
    print(f"  Livros ......................... {len(survey.books)} ({len(survey.books_with_diagrams)} com diagrama)")
    print(f"  Diagramas amostrados ........... {survey.diagrams}")
    print()
    print("  Por procedência")
    total = survey.as_dict()["by_source"]
    for source, count in sorted(total.items(), key=lambda kv: -kv[1]):
        share = count / survey.diagrams if survey.diagrams else 0.0
        print(f"    {source_label(source):16} {count:5d}  {share:6.1%}")
    print()
    print("  Critério de saída da Fase 8")
    print(f"    Livros com procedência ≠ 'default' ...... {len(survey.books_resolved)} de {len(survey.books)}")
    print(f"      dos quais por texto ou OCR ............ {len(survey.books_resolved_by_text)}")
    print(f"    Livros com a maioria resolvida .......... {len(survey.books_mostly_resolved)}")

    atingido = len(survey.books_resolved) >= EXIT_CRITERION_BOOKS
    veredito = "ATINGIDO" if atingido else "não atingido"
    print(f"    Alvo: ≥ {EXIT_CRITERION_BOOKS} livros ............................ {veredito}")
    print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.is_dir():
        print(f"Diretório de PDFs não encontrado: {pdf_dir}")
        return 2

    options = RecognitionOptions(
        model_path=args.model,
        orientation=args.orientation,
        max_boards=args.max_boards,
        dpi=args.dpi,
    )
    service = OcrService(model_path=args.model, caption_reader=caption_reader_from_args(args))
    motor = "" if str(args.ocr) == OFF else str(args.ocr)

    print(f"Amostrando {args.pages} página(s) por livro em {pdf_dir}...")
    survey = survey_collection(pdf_dir, service, options, pages=args.pages, ocr_engine=motor, on_book=_print_book)
    _print_survey(survey)

    if args.json is not None:
        write_survey(args.json, survey)
        print(f"Levantamento em {args.json}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
