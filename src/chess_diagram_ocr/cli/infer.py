from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..board_detection import NoBoardDetectedError, detect_board
from ..config import DEFAULT_MODEL_PATH
from ..inference import load_model, predict_board
from ..logging_setup import configure_logging, default_log_file
from ..pdf_io import render_pdf_page

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconhece a FEN do melhor diagrama de uma pagina de PDF.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=0, help="Indice da pagina, base 0.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--rotate-180", action="store_true", help="Rotaciona o tabuleiro em 180 graus.")
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nivel DEBUG.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    try:
        page_rgb = render_pdf_page(args.pdf, args.page, dpi=args.dpi)
        board_rgb, _quad = detect_board(page_rgb)
    except NoBoardDetectedError as exc:
        logger.error("%s", exc)
        return 1

    model, device = load_model(args.model)
    prediction = predict_board(board_rgb, model, device, rotate_180=args.rotate_180)

    # Resultado vai para stdout (consumivel por pipe); diagnostico vai para o log.
    print(f"FEN: {prediction.fen_board}")
    print(f"Confianca minima: {prediction.min_confidence:.3f}")
    print(f"Confianca media:  {prediction.mean_confidence:.3f}")

    if prediction.uncertain_squares:
        casas = ", ".join(
            f"{name} ({prediction.probs[index, prediction.class_indices[index]]:.2f})"
            for index, name in zip(prediction.uncertain_squares, prediction.uncertain_square_names, strict=True)
        )
        print(f"Casas inseguras: {casas}")

    if prediction.position.is_legal:
        print("Legalidade: posicao legal")
    else:
        print(f"Legalidade: {'; '.join(prediction.position.problems) or 'ilegal'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
