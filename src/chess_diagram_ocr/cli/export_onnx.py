"""`cvoff-export-onnx`: grava o checkpoint como ONNX e confere a paridade numérica (S-30)."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import torch

from ..atomic_io import atomic_write_text, read_image
from ..dataset import BoardFenDataset
from ..inference import describe_device, load_model
from ..logging_setup import configure_logging, default_log_file
from ..model import DEFAULT_ARCH, preprocess_cell_to_tensor, with_coordinate_channels
from ..onnx_export import compare_backends, export_onnx, load_onnx_model
from ..splits import load_splits
from . import (
    EXIT_BAD_INPUT,
    EXIT_FAILURE,
    EXIT_NO_CHECKPOINT,
    EXIT_OK,
    add_dataset_arguments,
    add_model_argument,
    add_verbose,
    cli_errors,
)

logger = logging.getLogger(__name__)



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exporta o classificador para ONNX (S-30).")
    add_model_argument(parser, help="Checkpoint .pt de origem.")
    parser.add_argument("--output", type=Path, default=None, help="Destino .onnx. Padrao: o mesmo nome do .pt.")
    add_dataset_arguments(parser)
    parser.add_argument(
        "--verify-split",
        choices=("train", "val", "test", "none"),
        default="test",
        help="Split usado na conferencia de paridade. 'none' pula a conferencia.",
    )
    parser.add_argument("--verify-boards", type=int, default=0, help="Limita a conferencia a N tabuleiros. 0 = todos.")
    parser.add_argument("--tolerance", type=float, default=1e-4, help="Tolerancia da S-30.")
    parser.add_argument("--json", type=Path, default=None, help="Grava o relatorio de paridade em JSON.")
    add_verbose(parser)
    return parser.parse_args(argv)


def _cell_batches(dataset: BoardFenDataset, limit: int) -> list[torch.Tensor]:
    """Um lote de 64 casas por tabuleiro -- o mesmo formato que a inferência usa."""
    import cv2

    from ..board_detection import split_board_into_cells
    from ..config import BOARD_SIZE

    batches: list[torch.Tensor] = []
    entries = dataset.entries[:limit] if limit else dataset.entries
    for entry in entries:
        image = read_image(dataset.samples_dir / entry.filename)
        if image is None:
            continue
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if image.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
            image = cv2.resize(image, (BOARD_SIZE, BOARD_SIZE))
        cells = [
            with_coordinate_channels(preprocess_cell_to_tensor(cell, dataset.arch), square_index, dataset.arch)
            for square_index, cell in enumerate(split_board_into_cells(image))
        ]
        batches.append(torch.stack(cells))
    return batches


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    if not Path(args.model).exists():
        # **Os dois códigos deste comando estavam trocados entre si (S-379).** Checkpoint que
        # falta é a classe 3 da tabela da S-126 -- ela existe exatamente para isto --, e saía
        # como 1, "falha inesperada". No fim do comando acontecia o inverso: a paridade
        # reprovada saía como 2, "entrada inválida", num arquivo que o próprio comando gravou.
        print(f"Checkpoint nao encontrado: {args.model}")
        return EXIT_NO_CHECKPOINT

    output = args.output or Path(args.model).with_suffix(".onnx")
    try:
        export_onnx(Path(args.model), output)
    except Exception as exc:  # noqa: BLE001 -- o erro do exportador e o que interessa ao usuario
        print(f"Falha ao exportar: {type(exc).__name__}: {exc}")
        return EXIT_FAILURE
    print(f"ONNX gravado em {output}")

    if args.verify_split == "none":
        print("Conferencia de paridade pulada (--verify-split none).")
        return 0

    splits = load_splits(args.splits)
    if not splits:
        print(f"Sem arquivo de splits em {args.splits}: nao da para conferir paridade.")
        return EXIT_BAD_INPUT

    torch_model, device = load_model(Path(args.model))
    arch = getattr(torch_model, "arch", DEFAULT_ARCH)
    dataset = BoardFenDataset(args.csv, args.samples, split=args.verify_split, splits=splits, arch=arch, cache_size=0)
    if not dataset.entries:
        print(f"Nenhuma amostra no split '{args.verify_split}'.")
        return EXIT_BAD_INPUT

    try:
        onnx_model, _ = load_onnx_model(output, Path(args.model))
    except ImportError:
        print("onnxruntime nao esta instalado: `uv sync --extra onnx`. O .onnx foi gravado mesmo assim.")
        return EXIT_FAILURE

    batches = _cell_batches(dataset, args.verify_boards)
    print(f"Conferindo {len(batches)} tabuleiros do split '{args.verify_split}' em {describe_device(device)}...")

    started = time.perf_counter()
    report = compare_backends(torch_model, onnx_model, batches, tolerance=args.tolerance)
    elapsed = time.perf_counter() - started

    print()
    print(f"  Amostras (casas) ............. {report.samples}")
    print(f"  Diferenca maxima ............. {report.max_abs_diff:.3e}  (tolerancia {report.tolerance:.0e})")
    print(f"  Diferenca media .............. {report.mean_abs_diff:.3e}")
    print(f"  Argmax discordante ........... {report.argmax_disagreements}")
    print(f"  Veredito ..................... {'PASSA' if report.passes else 'FALHA'}")
    print(f"  (comparacao levou {elapsed:.1f}s rodando os dois backends)")
    print()

    if args.json:
        atomic_write_text(args.json, json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        print(f"Relatorio em {args.json}")

    # Paridade reprovada é falha do que este comando produziu, e não da entrada de quem o
    # chamou: quem consome o código num script precisa dos dois separados (S-379).
    return EXIT_OK if report.passes else EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
