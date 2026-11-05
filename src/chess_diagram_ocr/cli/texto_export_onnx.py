"""`cvoff-texto-export-onnx`: grava o classificador de caracteres como ONNX e confere a paridade.

O par de saída é `<nome>.onnx` + `<nome>.json`. O `.json` traz o mapa de classes, a temperatura,
o preparo da entrada e o SHA-256 do `.onnx`: é o que outro programa precisa para usar o modelo
sem ler este repositório (ver `text/onnx_glifos.py`).

A paridade é conferida contra o torch, em probabilidades, com a tolerância da S-30 (1e-4) e
nenhuma troca de argmax. Os recortes vêm de `--recortes` (uma pasta de PNGs, como a base de
treino) ou, sem ela, são sintéticos: aleatórios, que bastam para provar que o grafo faz a mesma
conta, mas não dizem nada sobre acerto.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from ..atomic_io import atomic_write_text, read_image
from ..logging_setup import configure_logging, default_log_file
from ..onnx_export import ParityReport
from ..text.modelo import CAMINHO_PADRAO_META, ModeloInvalido, carregar_classificador
from ..text.onnx_glifos import ClassificadorDeGlifoOnnx, caminho_do_metadado_onnx, exportar_glifos_onnx
from . import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NO_CHECKPOINT, EXIT_OK, add_verbose, cli_errors

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exporta o classificador de caracteres para ONNX.")
    parser.add_argument("--meta", type=Path, default=CAMINHO_PADRAO_META, help="Metadado das classes (char_meta.json).")
    parser.add_argument("--pesos", type=Path, default=None, help="Pesos .pt. Padrão: o que o metadado acha ao lado.")
    parser.add_argument("--saida", type=Path, required=True, help="Destino .onnx. O .json sai ao lado.")
    parser.add_argument("--recortes", type=Path, default=None, help="Pasta de PNGs para a paridade (recursiva).")
    parser.add_argument("--amostras", type=int, default=512, help="Quantos recortes conferir. Padrão: 512.")
    parser.add_argument("--tolerance", type=float, default=1e-4, help="Tolerância da S-30.")
    parser.add_argument("--json", type=Path, default=None, help="Grava o relatório de paridade em JSON.")
    add_verbose(parser)
    return parser.parse_args(argv)


def _recortes(pasta: Path | None, quantos: int) -> list[np.ndarray]:
    if pasta is None:
        gerador = np.random.default_rng(0)
        return [gerador.integers(0, 256, size=(32, 32), dtype=np.uint8) for _ in range(quantos)]
    lidos: list[np.ndarray] = []
    for arquivo in sorted(pasta.rglob("*.png")):
        imagem = read_image(arquivo)
        if imagem is not None:
            lidos.append(imagem)
        if len(lidos) >= quantos:
            break
    return lidos


def comparar(probs_torch: np.ndarray, probs_onnx: np.ndarray, tolerance: float) -> ParityReport:
    """O veredito da S-30 sobre duas matrizes de probabilidades já calculadas."""
    diff = np.abs(probs_torch.astype(np.float64) - probs_onnx.astype(np.float64))
    return ParityReport(
        samples=int(probs_torch.shape[0]),
        max_abs_diff=float(diff.max()) if diff.size else 0.0,
        mean_abs_diff=float(diff.mean()) if diff.size else 0.0,
        argmax_disagreements=int((probs_torch.argmax(axis=1) != probs_onnx.argmax(axis=1)).sum()) if diff.size else 0,
        tolerance=tolerance,
    )


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    try:
        saida = exportar_glifos_onnx(args.saida, args.meta, args.pesos)
    except ModeloInvalido as exc:
        print(str(exc))
        return EXIT_NO_CHECKPOINT
    print(f"ONNX gravado em {saida}")
    print(f"Metadado gravado em {caminho_do_metadado_onnx(saida)}")

    recortes = _recortes(args.recortes, args.amostras)
    if not recortes:
        print(f"Nenhum PNG em {args.recortes}: não dá para conferir a paridade.")
        return EXIT_BAD_INPUT

    try:
        onnx = ClassificadorDeGlifoOnnx(saida)
    except ImportError:
        print("onnxruntime não está instalado: `uv sync --extra onnx`. O .onnx foi gravado mesmo assim.")
        return EXIT_FAILURE

    torch_ = carregar_classificador(args.meta, args.pesos, device="cpu")
    report = comparar(torch_.probabilidades(recortes), onnx.probabilidades(recortes), args.tolerance)
    origem = "sintéticos (aleatórios)" if args.recortes is None else str(args.recortes)

    print()
    print(f"  Recortes ..................... {report.samples} ({origem})")
    print(f"  Diferença máxima ............. {report.max_abs_diff:.3e}  (tolerância {report.tolerance:.0e})")
    print(f"  Diferença média .............. {report.mean_abs_diff:.3e}")
    print(f"  Argmax discordante ........... {report.argmax_disagreements}")
    print(f"  Veredito ..................... {'PASSA' if report.passes else 'FALHA'}")
    print()

    if args.json:
        atomic_write_text(args.json, json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        print(f"Relatório em {args.json}")

    return EXIT_OK if report.passes else EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
