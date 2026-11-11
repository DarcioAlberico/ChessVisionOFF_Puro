"""Exportação do classificador de caracteres para ONNX (`text/onnx_glifos.py`).

Os testes usam uma rede de pesos aleatórios com um metadado gerado na hora: o que se trava aqui é
a conta e o par (`.onnx` + `.json`), não o acerto do modelo publicado, cujos pesos não moram no
repositório. Pulam sem `onnxruntime`, como os da S-30.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from chess_diagram_ocr.cli.texto_export_onnx import comparar
from chess_diagram_ocr.cli.texto_export_onnx import main as cli_main
from chess_diagram_ocr.text.modelo import (
    ModeloInvalido,
    _construir_rede,
    carregar_classificador,
    impressao_das_classes,
    impressao_do_arquivo,
)
from chess_diagram_ocr.text.onnx_glifos import (
    ClassificadorDeGlifoOnnx,
    caminho_do_metadado_onnx,
    exportar_glifos_onnx,
    ler_metadado_onnx,
)

try:
    import onnxruntime  # noqa: F401

    HAS_ONNXRUNTIME = True
except ImportError:  # pragma: no cover
    HAS_ONNXRUNTIME = False

ALFABETO = ["a", "b", "c", "♘", "±", "∞"]


def _par(raiz: Path, *, temperatura: float = 1.5) -> Path:
    """Grava `char_meta.json` + `char_classifier.pt` de uma rede aleatória e devolve o metadado."""
    torch.manual_seed(0)
    pesos = raiz / "char_classifier.pt"
    torch.save(_construir_rede(len(ALFABETO)).state_dict(), pesos)
    idx_to_char = dict(enumerate(ALFABETO))
    meta = raiz / "char_meta.json"
    meta.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "idx_to_char": {str(i): c for i, c in idx_to_char.items()},
                "num_classes": len(ALFABETO),
                "temperatura": temperatura,
                "modelo_sha256": impressao_do_arquivo(pesos),
                "classes_sha256": impressao_das_classes(idx_to_char),
                "treinado_em": "2026-11-04T00:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return meta


def _recortes(n: int) -> list[np.ndarray]:
    gerador = np.random.default_rng(1)
    # Tamanhos variados de propósito: o preparo redimensiona, e é ali que um desvio apareceria.
    return [gerador.integers(0, 256, size=(20 + i % 30, 14 + i % 25), dtype=np.uint8) for i in range(n)]


@unittest.skipUnless(HAS_ONNXRUNTIME, "onnxruntime nao instalado (extra opcional)")
class ExportacaoTests(unittest.TestCase):
    def test_onnx_probabilities_match_torch_within_the_s30_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            meta = _par(raiz)
            onnx = exportar_glifos_onnx(raiz / "chess-glyphs.onnx", meta)

            recortes = _recortes(300)
            torch_ = carregar_classificador(meta, device="cpu").probabilidades(recortes)
            report = comparar(torch_, ClassificadorDeGlifoOnnx(onnx).probabilidades(recortes), 1e-4)

            self.assertTrue(report.passes, f"divergência {report.max_abs_diff:.2e}")
            self.assertEqual(report.samples, 300)

    def test_the_two_backends_read_the_same_characters(self) -> None:
        """S-854: o preparo e a decisão são uma função só; o que sobra de diferença é o motor.

        Recortes em cinza e em RGB, de tamanhos variados: o caractere é o mesmo em todos, e a
        confiança e a margem diferem no máximo 1e-4 (a tolerância da S-30).
        """
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            meta = _par(raiz)
            onnx = ClassificadorDeGlifoOnnx(exportar_glifos_onnx(raiz / "g.onnx", meta))
            torch_ = carregar_classificador(meta, device="cpu")
            recortes = _recortes(150) + [np.stack([r, r, r], axis=-1) for r in _recortes(150)]

            pelo_torch, pelo_onnx = torch_.classificar(recortes), onnx.classificar(recortes)
            self.assertEqual([c for c, _ in pelo_torch], [c for c, _ in pelo_onnx])
            np.testing.assert_allclose([p for _, p in pelo_torch], [p for _, p in pelo_onnx], atol=1e-4, rtol=0)
            np.testing.assert_allclose(torch_.margem(recortes), onnx.margem(recortes), atol=1e-4, rtol=0)

    def test_the_sidecar_carries_classes_in_index_order_and_the_temperature(self) -> None:
        """É o `.json` que traduz índice em caractere em outro programa; a ordem é o contrato."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            onnx = exportar_glifos_onnx(raiz / "chess-glyphs.onnx", _par(raiz, temperatura=1.75))
            dados = json.loads(caminho_do_metadado_onnx(onnx).read_text(encoding="utf-8"))

            self.assertEqual(caminho_do_metadado_onnx(onnx).name, "chess-glyphs.json")
            self.assertEqual(dados["classes"], ALFABETO)
            self.assertEqual(dados["num_classes"], len(ALFABETO))
            self.assertEqual(dados["temperatura"], 1.75)
            self.assertEqual(dados["entrada"]["forma"], ["lote", 1, 32, 32])
            self.assertEqual(dados["onnx_sha256"], impressao_do_arquivo(onnx))

    def test_batch_axis_is_dynamic(self) -> None:
        """A página manda de um a milhares de recortes de uma vez."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            onnx = ClassificadorDeGlifoOnnx(exportar_glifos_onnx(raiz / "g.onnx", _par(raiz)))
            for n in (1, 7, 513):
                self.assertEqual(onnx.probabilidades(_recortes(n)).shape, (n, len(ALFABETO)))
            self.assertEqual(onnx.classificar([]), [])

    def test_a_swapped_onnx_is_refused_before_the_session_opens(self) -> None:
        """O descasamento calado da S-179, do lado do consumidor: o `.json` descreve outro arquivo."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            onnx = exportar_glifos_onnx(raiz / "g.onnx", _par(raiz))
            onnx.write_bytes(onnx.read_bytes() + b"\0")
            with self.assertRaises(ModeloInvalido):
                ler_metadado_onnx(onnx)

    def test_weights_that_do_not_match_the_metadata_are_not_exported(self) -> None:
        """O exportador passa por `carregar_classificador`, que recusa o `.pt` por hash."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            meta = _par(raiz)
            torch.manual_seed(99)
            torch.save(_construir_rede(len(ALFABETO)).state_dict(), raiz / "char_classifier.pt")
            with self.assertRaises(ModeloInvalido):
                exportar_glifos_onnx(raiz / "g.onnx", meta)
            self.assertFalse((raiz / "g.onnx").exists())

    def test_cli_exports_and_reports_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            meta = _par(raiz)
            codigo = cli_main(
                ["--meta", str(meta), "--saida", str(raiz / "g.onnx"), "--amostras", "64", "--json", str(raiz / "p.json")]
            )
            self.assertEqual(codigo, 0)
            self.assertTrue(json.loads((raiz / "p.json").read_text(encoding="utf-8"))["passes"])

    def test_cli_without_weights_exits_as_missing_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            meta = _par(raiz)
            (raiz / "char_classifier.pt").unlink()
            self.assertEqual(cli_main(["--meta", str(meta), "--saida", str(raiz / "g.onnx")]), 3)


if __name__ == "__main__":
    unittest.main()
