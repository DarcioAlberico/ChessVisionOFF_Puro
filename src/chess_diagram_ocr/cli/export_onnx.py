"""`cvoff-export-onnx`: grava o checkpoint como ONNX e confere a paridade numérica (S-30)."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import torch

from ..atomic_io import atomic_write_text, read_image
from ..dataset import BoardFenDataset
from ..inference import describe_device, load_model
from ..leitor_de_diagrama_onnx import caminho_do_contrato, ler_contrato, preparar_tabuleiro
from ..logging_setup import configure_logging, default_log_file
from ..model import DEFAULT_ARCH, ArchConfig, preprocess_cell_to_tensor, with_coordinate_channels
from ..onnx_export import compare_backends, export_onnx, load_onnx_model
from ..splits import load_splits
from . import (
    EXIT_BAD_INPUT,
    EXIT_FAILURE,
    EXIT_NO_CHECKPOINT,
    EXIT_OK,
    add_dataset_arguments,
    add_json_argument,
    add_model_argument,
    add_tolerance_argument,
    add_verbose,
    cli_errors,
    fronteira,
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
    add_tolerance_argument(parser)
    add_json_argument(parser, help="Grava o relatório de paridade em JSON.")
    add_verbose(parser)
    return parser.parse_args(argv)


def _boards(dataset: BoardFenDataset, limit: int) -> list[np.ndarray]:
    """Os tabuleiros do split em RGB, no tamanho em que estão no disco."""
    import cv2

    boards: list[np.ndarray] = []
    entries = dataset.entries[:limit] if limit else dataset.entries
    for entry in entries:
        image = read_image(dataset.samples_dir / entry.filename)
        if image is not None:
            boards.append(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    return boards


def _cell_batch(board_rgb: np.ndarray, arch: ArchConfig) -> torch.Tensor:
    """Um lote de 64 casas -- o mesmo formato que a inferência usa."""
    from ..board_detection import split_board_into_cells

    cells = [
        with_coordinate_channels(preprocess_cell_to_tensor(cell, arch), square_index, arch)
        for square_index, cell in enumerate(split_board_into_cells(board_rgb))
    ]
    return torch.stack(cells)


def _same_preparation(boards: list[np.ndarray], batches: list[torch.Tensor], onnx_path: Path) -> int:
    """Em quantos tabuleiros o leitor avulso monta, byte a byte, o lote que o programa monta.

    O `leitor_de_diagrama_onnx.py` copia o preparo para não depender do torch. A paridade de
    cima prova o grafo; esta prova a cópia, nos tabuleiros reais -- é ela que diz se outro
    programa, seguindo o contrato, entrega ao modelo o mesmo que o ChessVisionOFF entrega.
    """
    contrato = ler_contrato(onnx_path)
    return sum(
        int(np.array_equal(preparar_tabuleiro(board, contrato), batch.numpy())) for board, batch in zip(boards, batches, strict=True)
    )


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
    print(f"ONNX gravado em {output}, com o contrato em {caminho_do_contrato(output)}")
    print("Outro programa le o par sem torch por src/chess_diagram_ocr/leitor_de_diagrama_onnx.py.")

    if args.verify_split == "none":
        print("Conferencia de paridade pulada (--verify-split none).")
        return 0

    with fronteira(f"--splits {args.splits}"):
        splits = load_splits(args.splits)
    if not splits:
        print(f"Sem arquivo de splits em {args.splits}: nao da para conferir paridade.")
        return EXIT_BAD_INPUT

    with fronteira(f"--model {args.model}", checkpoint=True):
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

    boards = _boards(dataset, args.verify_boards)
    batches = [_cell_batch(board, arch) for board in boards]
    print(f"Conferindo {len(batches)} tabuleiros do split '{args.verify_split}' em {describe_device(device)}...")

    started = time.perf_counter()
    report = compare_backends(torch_model, onnx_model, batches, tolerance=args.tolerance)
    elapsed = time.perf_counter() - started
    same = _same_preparation(boards, batches, output)
    passes = report.passes and same == len(batches)

    print()
    print(f"  Amostras (casas) ............. {report.samples}")
    print(f"  Diferenca maxima ............. {report.max_abs_diff:.3e}  (tolerancia {report.tolerance:.0e})")
    print(f"  Diferenca media .............. {report.mean_abs_diff:.3e}")
    print(f"  Argmax discordante ........... {report.argmax_disagreements}")
    print(f"  Preparo do leitor avulso ..... identico em {same} de {len(batches)} tabuleiros")
    print(f"  Veredito ..................... {'PASSA' if passes else 'FALHA'}")
    print(f"  (comparacao levou {elapsed:.1f}s rodando os dois backends)")
    print()

    if args.json:
        relatorio = report.as_dict()
        relatorio.update(preparo_avulso_identico=same, preparo_avulso_conferido=len(batches), passes=passes)
        atomic_write_text(args.json, json.dumps(relatorio, indent=2, ensure_ascii=False))
        print(f"Relatorio em {args.json}")

    # Paridade reprovada é falha do que este comando produziu, e não da entrada de quem o
    # chamou: quem consome o código num script precisa dos dois separados (S-379).
    return EXIT_OK if passes else EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
