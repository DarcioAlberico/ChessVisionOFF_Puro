"""`cvoff-export-onnx`: grava o checkpoint como ONNX e confere a paridade numérica (S-30)."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import torch

from ..config import DEFAULT_DATASET_CSV, DEFAULT_MODEL_PATH, DEFAULT_SAMPLES_DIR, PROJECT_ROOT
from ..dataset import BoardFenDataset
from ..inference import describe_device, load_model
from ..logging_setup import configure_logging, default_log_file
from ..model import DEFAULT_ARCH, preprocess_cell_to_tensor, with_coordinate_channels
from ..onnx_export import compare_backends, export_onnx, load_onnx_model
from ..splits import load_splits
from . import cli_errors

logger = logging.getLogger(__name__)

DEFAULT_SPLITS_PATH = PROJECT_ROOT / "data" / "splits.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exporta o classificador para ONNX (S-30).")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Checkpoint .pt de origem.")
    parser.add_argument("--output", type=Path, default=None, help="Destino .onnx. Padrao: o mesmo nome do .pt.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES_DIR)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS_PATH)
    parser.add_argument(
        "--verify-split",
        choices=("train", "val", "test", "none"),
        default="test",
        help="Split usado na conferencia de paridade. 'none' pula a conferencia.",
    )
    parser.add_argument("--verify-boards", type=int, default=0, help="Limita a conferencia a N tabuleiros. 0 = todos.")
    parser.add_argument("--tolerance", type=float, default=1e-4, help="Tolerancia da S-30.")
    parser.add_argument("--json", type=Path, default=None, help="Grava o relatorio de paridade em JSON.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _cell_batches(dataset: BoardFenDataset, limit: int) -> list[torch.Tensor]:
    """Um lote de 64 casas por tabuleiro -- o mesmo formato que a inferência usa."""
    import cv2

    from ..board_detection import split_board_into_cells
    from ..config import BOARD_SIZE

    batches: list[torch.Tensor] = []
    entries = dataset.entries[:limit] if limit else dataset.entries
    for entry in entries:
        image = cv2.imread(str(dataset.samples_dir / entry.filename))
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
        print(f"Checkpoint nao encontrado: {args.model}")
        return 1

    output = args.output or Path(args.model).with_suffix(".onnx")
    try:
        export_onnx(Path(args.model), output)
    except Exception as exc:  # noqa: BLE001 -- o erro do exportador e o que interessa ao usuario
        print(f"Falha ao exportar: {type(exc).__name__}: {exc}")
        return 1
    print(f"ONNX gravado em {output}")

    if args.verify_split == "none":
        print("Conferencia de paridade pulada (--verify-split none).")
        return 0

    splits = load_splits(args.splits)
    if not splits:
        print(f"Sem arquivo de splits em {args.splits}: nao da para conferir paridade.")
        return 1

    torch_model, device = load_model(Path(args.model))
    arch = getattr(torch_model, "arch", DEFAULT_ARCH)
    dataset = BoardFenDataset(args.csv, args.samples, split=args.verify_split, splits=splits, arch=arch, cache_size=0)
    if not dataset.entries:
        print(f"Nenhuma amostra no split '{args.verify_split}'.")
        return 1

    try:
        onnx_model, _ = load_onnx_model(output, Path(args.model))
    except ImportError:
        print("onnxruntime nao esta instalado: `uv sync --extra onnx`. O .onnx foi gravado mesmo assim.")
        return 1

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
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Relatorio em {args.json}")

    return 0 if report.passes else 2


if __name__ == "__main__":
    raise SystemExit(main())
