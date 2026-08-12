"""Exportacao ONNX e paridade numerica (S-30).

Os testes pulam quando `onnxruntime` nao esta instalado: o extra e opcional de proposito,
e a CI nao deve exigi-lo para validar o resto do projeto.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import torch

from chess_diagram_ocr.checkpoint import save_checkpoint
from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.model import ArchConfig, build_model
from chess_diagram_ocr.onnx_export import ParityReport, compare_backends, export_onnx, load_onnx_model

try:
    import onnxruntime  # noqa: F401

    HAS_ONNXRUNTIME = True
except ImportError:  # pragma: no cover
    HAS_ONNXRUNTIME = False


def _checkpoint(path: Path, arch: ArchConfig, *, temperature: float = 1.0) -> None:
    save_checkpoint(
        path,
        build_model(arch, pretrained=False).state_dict(),
        metadata={"arch_version": arch.version, "class_names": list(PIECE_CLASSES)},
        temperature=temperature,
    )


class ParityReportTests(unittest.TestCase):
    """A logica do veredito nao depende do onnxruntime e vale a pena travar sozinha."""

    def test_small_difference_with_no_argmax_change_passes(self) -> None:
        self.assertTrue(ParityReport(64, 1e-7, 1e-9, 0, 1e-4).passes)

    def test_difference_above_tolerance_fails(self) -> None:
        self.assertFalse(ParityReport(64, 1e-3, 1e-5, 0, 1e-4).passes)

    def test_an_argmax_flip_fails_even_when_the_difference_is_tiny(self) -> None:
        """Divergencia minima num empate troca a classe -- e ai a FEN muda."""
        self.assertFalse(ParityReport(64, 1e-9, 1e-12, 1, 1e-4).passes)


@unittest.skipUnless(HAS_ONNXRUNTIME, "onnxruntime nao instalado (extra opcional)")
class ExportTests(unittest.TestCase):
    def test_exported_graph_matches_torch_within_the_s30_tolerance(self) -> None:
        arch = ArchConfig()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _checkpoint(root / "m.pt", arch)
            export_onnx(root / "m.pt", root / "m.onnx")

            torch_model = build_model(arch, pretrained=False)
            torch_model.load_state_dict(
                torch.load(root / "m.pt", map_location="cpu", weights_only=True)["model_state"]
            )
            onnx_model, _ = load_onnx_model(root / "m.onnx", root / "m.pt")

            batches = [torch.randn(64, 1, 64, 64), torch.randn(17, 1, 64, 64)]
            report = compare_backends(torch_model, onnx_model, batches)

            self.assertTrue(report.passes, f"divergencia {report.max_abs_diff:.2e}")
            self.assertEqual(report.argmax_disagreements, 0)
            self.assertEqual(report.samples, 81)

    def test_batch_axis_is_dynamic(self) -> None:
        """O pipeline chama o modelo com 64 casas, 448 (com TTA) e 512 (avaliacao)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _checkpoint(root / "m.pt", ArchConfig())
            export_onnx(root / "m.pt", root / "m.onnx")
            onnx_model, _ = load_onnx_model(root / "m.onnx", root / "m.pt")

            for size in (1, 64, 448):
                with self.subTest(batch=size):
                    saida = onnx_model(torch.zeros(size, 1, 64, 64))
                    self.assertEqual(tuple(saida.shape), (size, len(PIECE_CLASSES)))

    def test_architecture_and_temperature_come_from_the_sibling_checkpoint(self) -> None:
        arch = ArchConfig(channels="rgb", image_size=32)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _checkpoint(root / "m.pt", arch, temperature=1.7)
            export_onnx(root / "m.pt", root / "m.onnx")

            onnx_model, device = load_onnx_model(root / "m.onnx", root / "m.pt")
            self.assertEqual(onnx_model.arch, arch)
            self.assertAlmostEqual(onnx_model.temperature, 1.7)
            self.assertEqual(device, "cpu")

    def test_every_architecture_of_the_grid_exports(self) -> None:
        for arch in (
            ArchConfig(),
            ArchConfig(channels="rgb"),
            ArchConfig(image_size=32),
            ArchConfig(head="gap"),
            ArchConfig(coords=True),
            ArchConfig(head="board"),
        ):
            with self.subTest(arch=arch.version), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _checkpoint(root / "m.pt", arch)
                self.assertTrue(export_onnx(root / "m.pt", root / "m.onnx").exists())

    def test_the_board_head_keeps_a_dynamic_batch_after_tracing(self) -> None:
        """O `reshape(-1, 64, D)` da S-62b existe por causa deste teste.

        Com o número de tabuleiros calculado em Python, o tracing o congelaria como constante
        e o `dynamic_axes` passaria a mentir: o grafo exportado com 1 tabuleiro recusaria 2, ou
        pior, aceitaria e leria errado.
        """
        arch = ArchConfig(head="board")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _checkpoint(root / "m.pt", arch)
            onnx_model, _device = load_onnx_model(export_onnx(root / "m.pt", root / "m.onnx"))

            for tabuleiros in (1, 3):
                with self.subTest(tabuleiros=tabuleiros):
                    entrada = torch.zeros(tabuleiros * 64, arch.in_channels, arch.image_size, arch.image_size)
                    self.assertEqual(tuple(onnx_model(entrada).shape), (tabuleiros * 64, len(PIECE_CLASSES)))


if __name__ == "__main__":
    unittest.main()
