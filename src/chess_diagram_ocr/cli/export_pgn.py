from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path

from ..config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
)
from ..logging_setup import configure_logging, default_log_file
from ..pdf_to_pgn import default_pgn_output_path, save_pdf_positions_to_pgn

logger = logging.getLogger(__name__)

SIDE_SOURCE_LABELS = {
    "text": "pelo texto do PDF",
    "legality": "pela legalidade da posicao",
    "default": "assumido brancas",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Varre um PDF inteiro e salva todas as posicoes encontradas em PGN.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=None, help="Padrao: PGN/<nome-do-pdf>.pgn")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--max-boards-per-page", type=int, default=8)
    parser.add_argument(
        "--orientation",
        choices=("auto", "0", "180"),
        default=DEFAULT_ORIENTATION_MODE,
        help=(
            "Orientacao de cada diagrama (S-13). 'auto' decide por diagrama, o que resolve "
            f"livro com orientacoes misturadas. Padrao: {DEFAULT_ORIENTATION_MODE}."
        ),
    )
    parser.add_argument("--start-page", type=int, default=0)
    parser.add_argument("--end-page", type=int, default=None, help="Exclusivo. Padrao: ate o fim do PDF.")
    parser.add_argument(
        "--reading-order",
        choices=("column", "row"),
        default=DEFAULT_READING_ORDER,
        help=f"Ordem de numeracao dos diagramas na pagina (S-14). Padrao: {DEFAULT_READING_ORDER}.",
    )
    parser.add_argument("--event", type=str, default="ChessVisionOFF PDF OCR")
    parser.add_argument(
        "--accept-threshold",
        type=float,
        default=ACCEPT_MIN_CONFIDENCE,
        help=(
            "Confianca minima por casa para a posicao entrar no PGN principal (S-15). "
            f"Padrao: {ACCEPT_MIN_CONFIDENCE:.2f}. Use 0 para exportar tudo."
        ),
    )
    parser.add_argument(
        "--no-text",
        dest="read_text",
        action="store_false",
        help=(
            "Ignora a camada de texto do PDF (S-16). O lado a jogar passa a sair so da "
            "legalidade e do padrao. Util para comparar o efeito da leitura de legenda."
        ),
    )
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help=(
            "Omite do PGN principal as posicoes repetidas no mesmo PDF (S-18). Sem a opcao, "
            "elas saem com o header [DuplicateOf] apontando a primeira ocorrencia."
        ),
    )
    parser.add_argument("--show-review", type=int, default=10, help="Itens de revisao listados no fim.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nivel DEBUG.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    output_path = args.output or default_pgn_output_path(args.pdf)

    def _progress(page_index: int, total_pages: int, page_boards: int, total_positions: int) -> None:
        logger.info(
            "pagina %d/%d | diagramas na pagina: %d | total acumulado: %d",
            page_index + 1,
            total_pages,
            page_boards,
            total_positions,
        )

    report = save_pdf_positions_to_pgn(
        pdf_source=args.pdf,
        output_path=output_path,
        model_path=args.model,
        dpi=args.dpi,
        max_boards_per_page=args.max_boards_per_page,
        orientation=args.orientation,
        start_page=args.start_page,
        end_page=args.end_page,
        reading_order=args.reading_order,
        event_name=args.event,
        accept_threshold=args.accept_threshold,
        read_text=args.read_text,
        dedupe=args.dedupe,
        progress_callback=_progress,
    )

    print(f"PDF: {args.pdf}")
    print(f"PGN: {report.output_path}")
    if report.review_path is not None:
        print(f"Revisao: {report.review_path}")
    print(report.summary())

    # De onde veio o lado a jogar (S-16/S-17). Sem isso, "pretas jogam" no PGN e uma
    # afirmacao sem procedencia -- e no acervo medido a maioria dela e assumida.
    sources = Counter(
        position.side_to_move.source
        for position in report.accepted
        if position.side_to_move is not None
    )
    if sources:
        detalhe = ", ".join(f"{count} {SIDE_SOURCE_LABELS[source]}" for source, count in sources.most_common())
        print(f"Lado a jogar: {detalhe}")

    # O que foi separado tem de aparecer: o ponto do gate e o usuario saber o que revisar,
    # nao o PGN principal ficar limpo em silencio.
    review_items = report.review_items
    if review_items and args.show_review:
        print()
        print("Precisam de revisao:")
        for position, reason in review_items[: args.show_review]:
            print(f"  pagina {position.page_number} diagrama {position.diagram_index}: {reason}")
        if len(review_items) > args.show_review:
            print(f"  ... e outros {len(review_items) - args.show_review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
