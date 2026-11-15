"""O leitor avulso do `.onnx` de peças e o contrato `.json` que o acompanha (S-30).

`leitor_de_diagrama_onnx.py` copia o preparo da casa para não depender do torch nem do pacote --
é o arquivo que outro programa leva. Estes testes são o que impede a cópia de derivar: o lote que
ele monta tem de ser **byte a byte** o do pacote, em toda arquitetura da grade, e a leitura tem de
dar a mesma FEN que o programa dá.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import torch
from ambiente_de_teste import pasta_temporaria, pasta_temporaria_da_classe

from chess_diagram_ocr import leitor_de_diagrama_onnx as leitor
from chess_diagram_ocr.atomic_io import write_image
from chess_diagram_ocr.board_detection import split_board_into_cells
from chess_diagram_ocr.checkpoint import save_checkpoint
from chess_diagram_ocr.cli import EXIT_FAILURE, EXIT_OK
from chess_diagram_ocr.cli.export_onnx import main as export_cli_main
from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.fen_utils import fen_from_class_indices, labels_from_fen
from chess_diagram_ocr.inference import board_probabilities
from chess_diagram_ocr.model import ArchConfig, build_model, preprocess_cell_to_tensor, with_coordinate_channels
from chess_diagram_ocr.onnx_export import export_onnx, load_onnx_model

try:
    import onnxruntime  # noqa: F401

    HAS_ONNXRUNTIME = True
except ImportError:  # pragma: no cover
    HAS_ONNXRUNTIME = False

FONTE = Path(leitor.__file__)
PERMITIDOS = {"numpy", "cv2", "onnxruntime"}

GRADE = (
    ArchConfig(),
    ArchConfig(channels="rgb"),
    ArchConfig(image_size=32),
    ArchConfig(coords=True),
    ArchConfig(head="board"),
    ArchConfig(head="gap"),
)


def _tabuleiro(semente: int, altura: int = 517, largura: int = 533) -> np.ndarray:
    """Casas alternadas, com manchas e ruído, num tamanho que não é o de 800 nem quadrado."""
    rng = np.random.default_rng(semente)
    filas, colunas = np.indices((altura, largura))
    escuras = ((filas * 8 // altura) + (colunas * 8 // largura)) % 2 == 1
    imagem = np.where(escuras[..., None], 120, 225).astype(np.int16) + rng.integers(-25, 26, (altura, largura, 3))
    for _ in range(12):
        y, x = int(rng.integers(0, altura - 40)), int(rng.integers(0, largura - 40))
        imagem[y : y + 40, x : x + 30] = rng.integers(0, 60, 3)
    return np.clip(imagem, 0, 255).astype(np.uint8)


def _lote_do_pacote(tabuleiro: np.ndarray, arch: ArchConfig) -> np.ndarray:
    casas = [
        with_coordinate_channels(preprocess_cell_to_tensor(casa, arch), indice, arch)
        for indice, casa in enumerate(split_board_into_cells(tabuleiro))
    ]
    return torch.stack(casas).numpy()


def _modulos_importados(fonte: str) -> list[str]:
    """Os módulos de topo que a fonte importa; import relativo sai como `.<nome>`."""
    nomes: list[str] = []
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Import):
            nomes.extend(alias.name.split(".")[0] for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            nomes.append("." + (no.module or "") if no.level else (no.module or "").split(".")[0])
    return nomes


def _alheios(fonte: str) -> list[str]:
    padrao = set(sys.stdlib_module_names) | {"__future__"}
    return sorted({nome for nome in _modulos_importados(fonte) if nome not in PERMITIDOS | padrao})


class FronteiraTests(unittest.TestCase):
    """O arquivo só serve a outro programa se não arrastar este pacote nem o torch."""

    def test_o_leitor_so_importa_numpy_opencv_onnxruntime_e_a_biblioteca_padrao(self) -> None:
        self.assertEqual([], _alheios(FONTE.read_text(encoding="utf-8")))

    def test_a_guarda_acusa_torch_e_import_do_pacote(self) -> None:
        """Sem isto a guarda de cima poderia passar verde por não achar import nenhum."""
        fonte = "import torch\nfrom .model import ArchConfig\nfrom chess_diagram_ocr.config import X\nimport json\n"
        self.assertEqual([".model", "chess_diagram_ocr", "torch"], _alheios(fonte))


class ContratoTests(unittest.TestCase):
    def _contrato(self, **mudancas: object) -> leitor.Contrato:
        campos: dict[str, object] = {
            "onnx_sha256": "0" * 64,
            "arquitetura": "cnn-gray-64-linear",
            "classes": tuple(PIECE_CLASSES),
            "canais": "gray",
            "lado_da_casa": 64,
            "coordenadas": False,
            "lote_multiplo_de": 1,
            "temperatura": 1.5,
        }
        campos.update(mudancas)
        return leitor.Contrato(**campos)

    def test_ida_e_volta_pelo_dicionario(self) -> None:
        for contrato in (self._contrato(), self._contrato(canais="rgb", coordenadas=True, lote_multiplo_de=64)):
            with self.subTest(canais=contrato.canais):
                volta = leitor.Contrato.de_dicionario(json.loads(json.dumps(contrato.como_dicionario())))
                self.assertEqual(contrato, volta)

    def test_campo_impossivel_e_recusado(self) -> None:
        for mudanca in (
            {"canais": "grey"},
            {"lote_multiplo_de": 32},
            {"lado_da_casa": 0},
            {"classes": ("empty", "P", "P")},
            {"temperatura": 0.0},
        ):
            with self.subTest(mudanca=mudanca), self.assertRaises(leitor.ContratoInvalido):
                self._contrato(**mudanca)

    def test_dicionario_incoerente_e_recusado(self) -> None:
        def estragar(dados: dict[str, object], chave: str, valor: object) -> dict[str, object]:
            dados = json.loads(json.dumps(dados))
            alvo, _, campo = chave.rpartition(".")
            (dados[alvo] if alvo else dados)[campo] = valor
            return dados

        base = self._contrato().como_dicionario()
        for chave, valor in (
            ("schema_version", leitor.SCHEMA_DO_CONTRATO + 1),
            ("num_classes", 12),
            ("entrada.forma", ["lote", 3, 64, 64]),
            ("preparo.coordenadas", "nao"),
            ("temperatura", True),
        ):
            with self.subTest(chave=chave), self.assertRaises(leitor.ContratoInvalido):
                leitor.Contrato.de_dicionario(estragar(base, chave, valor))

    def test_os_passos_acompanham_a_arquitetura(self) -> None:
        simples = " ".join(self._contrato().passos())
        completo = " ".join(self._contrato(canais="rgb", coordenadas=True, lote_multiplo_de=64).passos())
        self.assertIn("COLOR_RGB2GRAY", simples)
        self.assertNotIn("planos constantes", simples)
        self.assertIn("R, G, B", completo)
        self.assertIn("planos constantes", completo)
        self.assertIn("(64, 6, 64, 64)", completo)
        self.assertIn("múltiplo de 64", completo)

    def test_a_fen_sai_da_colocacao(self) -> None:
        for fen in ("8/8/8/8/8/8/8/8", "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR", "r3k2r/8/8/3Qq3/8/8/8/R3K2R"):
            with self.subTest(fen=fen):
                self.assertEqual(fen, leitor.posicao_fen([PIECE_CLASSES[i] for i in labels_from_fen(fen)]))
        with self.assertRaises(ValueError):
            leitor.posicao_fen(["empty"] * 63)

    def test_imagem_que_nao_e_rgb_uint8_e_recusada(self) -> None:
        contrato = self._contrato()
        for imagem in (np.zeros((80, 80), np.uint8), np.zeros((80, 80, 3), np.float32), np.zeros((80, 80, 4), np.uint8)):
            with self.subTest(forma=imagem.shape, tipo=str(imagem.dtype)), self.assertRaises(ValueError):
                leitor.preparar_tabuleiro(imagem, contrato)


@unittest.skipUnless(HAS_ONNXRUNTIME, "onnxruntime nao instalado (extra opcional)")
class ExportadoTests(unittest.TestCase):
    """Cada arquitetura da grade exportada uma vez, com o contrato ao lado."""

    pasta: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.pasta = pasta_temporaria_da_classe(cls)
        for numero, arch in enumerate(GRADE):
            torch.manual_seed(numero)
            pt = cls.pasta / f"m{numero}.pt"
            save_checkpoint(
                pt,
                build_model(arch, pretrained=False).state_dict(),
                metadata={"arch_version": arch.version, "class_names": list(PIECE_CLASSES)},
                temperature=1.25 + numero,
            )
            export_onnx(pt, pt.with_suffix(".onnx"))

    def _onnx(self, arch: ArchConfig) -> Path:
        return self.pasta / f"m{GRADE.index(arch)}.onnx"

    def _modelo_torch(self, arch: ArchConfig) -> torch.nn.Module:
        modelo = build_model(arch, pretrained=False)
        dados = torch.load(self._onnx(arch).with_suffix(".pt"), map_location="cpu", weights_only=True)
        modelo.load_state_dict(dados["model_state"])
        return modelo.eval()

    def test_o_lote_do_leitor_e_o_do_pacote_byte_a_byte(self) -> None:
        for arch in GRADE:
            contrato = leitor.ler_contrato(self._onnx(arch))
            for tabuleiro in (_tabuleiro(1), _tabuleiro(2, 800, 800)):
                with self.subTest(arch=arch.version, forma=tabuleiro.shape):
                    lote = leitor.preparar_tabuleiro(tabuleiro, contrato)
                    self.assertEqual(np.float32, lote.dtype)
                    self.assertTrue(np.array_equal(_lote_do_pacote(tabuleiro, arch), lote))

    def test_a_leitura_do_leitor_e_a_do_programa(self) -> None:
        for arch in GRADE:
            with self.subTest(arch=arch.version):
                tabuleiro = _tabuleiro(3)
                programa = board_probabilities(tabuleiro, self._modelo_torch(arch), "cpu")
                leitura = leitor.LeitorDeDiagramaOnnx(self._onnx(arch)).ler(tabuleiro)
                self.assertLess(float(np.abs(programa - leitura.probabilidades).max()), 1e-4)
                self.assertEqual(fen_from_class_indices(programa.argmax(axis=1)), leitura.fen)

    def test_o_contrato_descreve_a_exportacao(self) -> None:
        for numero, arch in enumerate(GRADE):
            with self.subTest(arch=arch.version):
                contrato = leitor.ler_contrato(self._onnx(arch))
                self.assertEqual(arch.version, contrato.arquitetura)
                self.assertEqual(tuple(PIECE_CLASSES), contrato.classes)
                self.assertEqual(arch.in_channels, contrato.canais_de_entrada)
                self.assertEqual(64 if arch.head == "board" else 1, contrato.lote_multiplo_de)
                self.assertAlmostEqual(1.25 + numero, contrato.temperatura)
                self.assertEqual(f"m{numero}.pt", contrato.origem["path"], "o contrato não publica a pasta")

    def test_a_temperatura_calibrada_e_opcional(self) -> None:
        arch = ArchConfig()
        modelo = leitor.LeitorDeDiagramaOnnx(self._onnx(arch))
        tabuleiro = _tabuleiro(4)
        logits = modelo.logits(tabuleiro)
        np.testing.assert_allclose(leitor.softmax(logits), modelo.probabilidades(tabuleiro), atol=1e-12)
        np.testing.assert_allclose(
            leitor.softmax(logits, modelo.contrato.temperatura), modelo.probabilidades(tabuleiro, calibrada=True), atol=1e-12
        )

    def test_onnx_de_outra_exportacao_e_recusado(self) -> None:
        pasta = pasta_temporaria(self)
        shutil.copy(self._onnx(GRADE[0]).with_suffix(".json"), pasta / "m.json")
        shutil.copy(self._onnx(GRADE[1]), pasta / "m.onnx")
        with self.assertRaisesRegex(leitor.ContratoInvalido, "não é o modelo"):
            leitor.ler_contrato(pasta / "m.onnx")
        with self.assertRaisesRegex(leitor.ContratoInvalido, "não é o modelo"):
            load_onnx_model(pasta / "m.onnx")

    def test_onnx_sem_contrato_e_recusado_pelo_leitor(self) -> None:
        pasta = pasta_temporaria(self)
        shutil.copy(self._onnx(GRADE[0]), pasta / "m.onnx")
        with self.assertRaisesRegex(leitor.ContratoInvalido, "não está em"):
            leitor.LeitorDeDiagramaOnnx(pasta / "m.onnx")

    def test_o_programa_prefere_o_contrato_ao_pt_reescrito(self) -> None:
        """O treino reescreve sempre o mesmo `.pt` (S-57); o `.onnx` antigo não pode herdar dele."""
        pasta = pasta_temporaria(self)
        for sufixo in (".pt", ".onnx", ".json"):
            shutil.copy(self._onnx(GRADE[0]).with_suffix(sufixo), pasta / f"m{sufixo}")
        save_checkpoint(
            pasta / "m.pt",
            build_model(ArchConfig(), pretrained=False).state_dict(),
            metadata={"arch_version": ArchConfig().version, "class_names": list(PIECE_CLASSES)},
            temperature=9.0,
        )
        modelo, _ = load_onnx_model(pasta / "m.onnx")
        self.assertAlmostEqual(1.25, modelo.temperature)

    def test_o_programa_recusa_contrato_com_outras_classes(self) -> None:
        pasta = pasta_temporaria(self)
        shutil.copy(self._onnx(GRADE[0]), pasta / "m.onnx")
        dados = json.loads(self._onnx(GRADE[0]).with_suffix(".json").read_text(encoding="utf-8"))
        dados["classes"] = list(reversed(dados["classes"]))
        (pasta / "m.json").write_text(json.dumps(dados), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(leitor.ContratoInvalido, "outra peça"):
            load_onnx_model(pasta / "m.onnx")

    def test_exportar_nao_pisa_json_alheio(self) -> None:
        pasta = pasta_temporaria(self)
        shutil.copy(self._onnx(GRADE[0]).with_suffix(".pt"), pasta / "m.pt")
        alheio = '{"alfabeto": ["a", "b"]}'
        (pasta / "char_meta.json").write_text(alheio, encoding="utf-8", newline="\n")
        with self.assertRaises(FileExistsError):
            export_onnx(pasta / "m.pt", pasta / "char_meta.onnx")
        self.assertEqual(alheio, (pasta / "char_meta.json").read_text(encoding="utf-8"))
        self.assertFalse((pasta / "char_meta.onnx").exists())

        # O contrato da exportação anterior não é alheio: reexportar no mesmo lugar funciona.
        export_onnx(pasta / "m.pt", pasta / "m.onnx")
        export_onnx(pasta / "m.pt", pasta / "m.onnx")
        leitor.ler_contrato(pasta / "m.onnx")

    def test_o_arquivo_copiado_roda_sozinho(self) -> None:
        """Copiado para outra pasta e carregado fora do pacote, ele lê e escreve a FEN."""
        pasta = pasta_temporaria(self)
        copia = pasta / "leitor_copiado.py"
        shutil.copy(FONTE, copia)
        especificacao = importlib.util.spec_from_file_location("leitor_copiado_cvoff", copia)
        assert especificacao is not None and especificacao.loader is not None
        modulo = importlib.util.module_from_spec(especificacao)
        sys.modules[especificacao.name] = modulo  # o `dataclass` procura o módulo ali
        self.addCleanup(sys.modules.pop, especificacao.name, None)
        especificacao.loader.exec_module(modulo)

        tabuleiro = _tabuleiro(5)
        imagem = pasta / "tabuleiro com acento é.png"
        cv2.imencode(".png", cv2.cvtColor(tabuleiro, cv2.COLOR_RGB2BGR))[1].tofile(str(imagem))
        esperada = leitor.LeitorDeDiagramaOnnx(self._onnx(GRADE[0])).ler(tabuleiro).fen

        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = modulo.main([str(self._onnx(GRADE[0])), str(imagem), str(pasta / "falta.png")])
        self.assertEqual(1, codigo, "uma imagem que falta é falha, e as outras são lidas mesmo assim")
        self.assertEqual(esperada, saida.getvalue().split("\t")[0])
        self.assertIn("falta.png", erro.getvalue())

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, modulo.main([str(pasta / "sem_contrato.onnx"), str(imagem)]))


@unittest.skipUnless(HAS_ONNXRUNTIME, "onnxruntime nao instalado (extra opcional)")
class ComandoTests(unittest.TestCase):
    """`cvoff-export-onnx` confere a cópia do preparo nos tabuleiros, não só o grafo."""

    def _argumentos(self) -> list[str]:
        pasta = pasta_temporaria(self)
        amostras = pasta / "samples"
        amostras.mkdir()
        rotulos, divisao = ["filename,fen"], ["filename,split"]
        for numero in range(2):
            nome = f"b{numero}.png"
            write_image(amostras / nome, cv2.cvtColor(_tabuleiro(10 + numero), cv2.COLOR_RGB2BGR))
            rotulos.append(f"{nome},4k3/8/8/8/8/8/8/4K3 w - - 0 1")
            divisao.append(f"{nome},test")
        (pasta / "labels.csv").write_text("\n".join(rotulos) + "\n", encoding="utf-8", newline="\n")
        (pasta / "splits.csv").write_text("\n".join(divisao) + "\n", encoding="utf-8", newline="\n")
        save_checkpoint(
            pasta / "m.pt",
            build_model(ArchConfig(), pretrained=False).state_dict(),
            metadata={"arch_version": ArchConfig().version, "class_names": list(PIECE_CLASSES)},
        )
        self.pasta = pasta
        return [
            "--model", str(pasta / "m.pt"),
            "--csv", str(pasta / "labels.csv"),
            "--samples", str(amostras),
            "--splits", str(pasta / "splits.csv"),
            "--json", str(pasta / "paridade.json"),
        ]  # fmt: skip

    def _rodar(self, argumentos: list[str]) -> tuple[int, str]:
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = export_cli_main(argumentos)
        return codigo, saida.getvalue()

    def test_o_preparo_identico_passa(self) -> None:
        codigo, saida = self._rodar(self._argumentos())
        self.assertEqual(EXIT_OK, codigo, saida)
        self.assertIn("identico em 2 de 2 tabuleiros", saida)
        relatorio = json.loads((self.pasta / "paridade.json").read_text(encoding="utf-8"))
        self.assertEqual((2, 2, True), (relatorio["preparo_avulso_identico"], relatorio["preparo_avulso_conferido"], relatorio["passes"]))
        leitor.ler_contrato(self.pasta / "m.onnx")

    def test_o_preparo_divergente_reprova_mesmo_com_o_grafo_igual(self) -> None:
        def preparo_errado(tabuleiro: np.ndarray, contrato: leitor.Contrato) -> np.ndarray:
            return leitor.preparar_tabuleiro(tabuleiro, contrato) * np.float32(0.5)

        with mock.patch("chess_diagram_ocr.cli.export_onnx.preparar_tabuleiro", preparo_errado):
            codigo, saida = self._rodar(self._argumentos())
        self.assertEqual(EXIT_FAILURE, codigo, saida)
        self.assertIn("identico em 0 de 2 tabuleiros", saida)
        self.assertIn("Argmax discordante ........... 0", saida, "o grafo continua igual; o que falha é a cópia")


if __name__ == "__main__":
    unittest.main()
