"""Motor de OCR opcional e plugável (S-42).

O que estes testes protegem é a promessa que torna o item aceitável: **sem o extra
instalado, o projeto funciona exatamente como hoje**. Não é uma promessa de conforto -- é a
mesma da S-32 e da S-33, e as três valem pelo mesmo motivo: um recurso opcional que derruba
o pipeline ao faltar não é opcional, é uma dependência com aviso.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from chess_diagram_ocr import ocr
from chess_diagram_ocr.ocr import (
    KNOWN_ENGINES,
    MIN_CONFIDENCE,
    EasyOcrRecognizer,
    RapidOcrRecognizer,
    TesseractRecognizer,
    TextBox,
    TextRecognizer,
    build_recognizer,
    filter_by_allowlist,
)
from chess_diagram_ocr.settings import OcrSettings

SRC = Path(ocr.__file__).resolve().parents[2]


def image(width: int = 40, height: int = 20) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


class FakeRecognizer:
    """O reconhecedor que a S-43 e a S-44 usam para testar sem motor instalado.

    Mora aqui, e não no arquivo de cada uma, porque o contrato que ele implementa é deste
    módulo -- se `TextRecognizer` mudar, é aqui que a mudança tem de doer primeiro.
    """

    def __init__(self, *calls: list[TextBox]) -> None:
        self.calls = list(calls)
        self.seen: list[np.ndarray] = []
        self.allowlists: list[str] = []

    @property
    def name(self) -> str:
        return "fake"

    def read(self, image_rgb: np.ndarray, *, allowlist: str = "") -> list[TextBox]:
        self.seen.append(image_rgb)
        self.allowlists.append(allowlist)
        if not self.calls:
            return []
        return self.calls.pop(0)


class BuildRecognizerTests(unittest.TestCase):
    def test_desligado_por_padrao(self) -> None:
        """O padrão do projeto é sem OCR, e é o padrão que 20 dos 27 livros querem."""
        self.assertIsNone(build_recognizer(OcrSettings()))

    def test_motor_desconhecido_nao_levanta(self) -> None:
        self.assertIsNone(build_recognizer(OcrSettings(enabled=True, engine="tesserato")))

    def test_extra_ausente_devolve_none_em_vez_de_levantar(self) -> None:
        """O contrato do `find_engine` da S-33: não achar é caminho normal, não erro."""

        def sem_o_extra() -> TextRecognizer:
            raise ImportError("No module named 'rapidocr_onnxruntime'")

        original = ocr._build_rapidocr
        ocr._build_rapidocr = sem_o_extra  # type: ignore[assignment]
        try:
            self.assertIsNone(build_recognizer(OcrSettings(enabled=True, engine="rapidocr")))
        finally:
            ocr._build_rapidocr = original  # type: ignore[assignment]

    def test_falha_de_inicializacao_do_motor_tambem_devolve_none(self) -> None:
        """Instalado e quebrado é diferente de ausente, e o pipeline não pode cair por isso.

        O caso real é o Tesseract: o wrapper importa sem o binário existir, e a falha só
        apareceria na primeira leitura -- no meio da varredura de um livro de 1.121 páginas.
        """

        def motor_quebrado() -> TextRecognizer:
            raise RuntimeError("tesseract is not installed or it's not in your PATH")

        original = ocr._build_tesseract
        ocr._build_tesseract = lambda _languages: motor_quebrado()  # type: ignore[assignment]
        try:
            self.assertIsNone(build_recognizer(OcrSettings(enabled=True, engine="tesseract")))
        finally:
            ocr._build_tesseract = original  # type: ignore[assignment]

    def test_importar_o_modulo_nao_importa_motor_nenhum(self) -> None:
        """A promessa de custo zero: `import chess_diagram_ocr.ocr` não carrega nada pesado.

        Em subprocesso porque a resposta depende do `sys.modules` limpo -- um teste anterior
        que tivesse construído um motor tornaria a verificação inútil no processo do pytest.
        """
        codigo = (
            "import sys, chess_diagram_ocr.ocr\n"
            "print(sorted(m for m in ('rapidocr_onnxruntime', 'easyocr', 'pytesseract') if m in sys.modules))"
        )
        resultado = subprocess.run(
            [sys.executable, "-c", codigo],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(SRC)},
            check=True,
        )
        self.assertEqual(resultado.stdout.strip(), "[]")

    def test_motores_conhecidos_todos_tem_construtor(self) -> None:
        for motor in KNOWN_ENGINES:
            with self.subTest(motor=motor):
                # Nao instalado -> None; instalado -> um reconhecedor. O que nao pode e
                # cair no ramo de "motor desconhecido", que e o que este teste pega.
                with self.assertLogs("chess_diagram_ocr.ocr", level="WARNING") as registro:
                    build_recognizer(OcrSettings(enabled=True, engine=motor))
                    ocr.logger.warning("sentinela")
                self.assertNotIn("desconhecido", " ".join(registro.output))


class AllowlistTests(unittest.TestCase):
    def test_filtra_caracteres_fora_do_vocabulario(self) -> None:
        boxes = [TextBox(text="B76", bbox=(0.0, 0.0, 1.0, 1.0), confidence=0.9)]
        self.assertEqual(filter_by_allowlist(boxes, "WB")[0].text, "B")

    def test_caixa_que_fica_vazia_e_descartada(self) -> None:
        boxes = [TextBox(text="1998", bbox=(0.0, 0.0, 1.0, 1.0), confidence=0.9)]
        self.assertEqual(filter_by_allowlist(boxes, "WB"), [])

    def test_sem_allowlist_nada_muda(self) -> None:
        boxes = [TextBox(text="Steinitz - Bird", bbox=(0.0, 0.0, 1.0, 1.0), confidence=0.9)]
        self.assertEqual(filter_by_allowlist(boxes, ""), boxes)


class RapidOcrTests(unittest.TestCase):
    """O motor padrão, exercitado contra a forma da API dele, sem tê-lo instalado."""

    def motor(self, resultado: Any) -> RapidOcrRecognizer:
        return RapidOcrRecognizer(lambda _imagem: resultado)

    def test_quadrilatero_vira_retangulo(self) -> None:
        quad = [[10.0, 4.0], [30.0, 6.0], [30.0, 16.0], [10.0, 14.0]]
        boxes = self.motor(([[quad, "Bremen 1998", 0.94]], 0.1)).read(image())

        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0].text, "Bremen 1998")
        self.assertEqual(boxes[0].bbox, (10.0, 4.0, 30.0, 16.0))

    def test_confianca_abaixo_do_piso_e_descartada(self) -> None:
        quad = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        baixa = MIN_CONFIDENCE - 0.01
        self.assertEqual(self.motor(([[quad, "lixo", baixa]], 0.1)).read(image()), [])

    def test_sem_texto_a_api_devolve_none_e_nao_lista_vazia(self) -> None:
        """A forma que faria um `for` direto levantar, e que acontece em página em branco."""
        self.assertEqual(self.motor((None, 0.1)).read(image()), [])

    def test_imagem_vazia_nao_chega_ao_motor(self) -> None:
        chamadas: list[Any] = []

        def motor(imagem: Any) -> Any:
            chamadas.append(imagem)
            return (None, 0.1)

        self.assertEqual(RapidOcrRecognizer(motor).read(np.zeros((0, 0, 3), dtype=np.uint8)), [])
        self.assertEqual(chamadas, [])

    def test_allowlist_vira_filtro_posterior(self) -> None:
        quad = [[0.0, 0.0], [8.0, 0.0], [8.0, 10.0], [0.0, 10.0]]
        boxes = self.motor(([[quad, "B", 0.71]], 0.1)).read(image(), allowlist="WB")
        self.assertEqual([box.text for box in boxes], ["B"])


class EasyOcrTests(unittest.TestCase):
    class Reader:
        def __init__(self, resultado: Any) -> None:
            self.resultado = resultado
            self.kwargs: dict[str, Any] = {}

        def readtext(self, _imagem: Any, **kwargs: Any) -> Any:
            self.kwargs = kwargs
            return self.resultado

    def test_allowlist_vai_nativa_para_o_decodificador(self) -> None:
        """A diferença que a interface esconde: aqui a restrição vale de verdade."""
        reader = self.Reader([])
        EasyOcrRecognizer(reader).read(image(), allowlist="12345678")
        self.assertEqual(reader.kwargs, {"allowlist": "12345678"})

    def test_sem_allowlist_o_argumento_nao_e_passado(self) -> None:
        reader = self.Reader([])
        EasyOcrRecognizer(reader).read(image())
        self.assertEqual(reader.kwargs, {})

    def test_le_o_formato_do_easyocr(self) -> None:
        quad = [[2, 3], [40, 3], [40, 15], [2, 15]]
        boxes = EasyOcrRecognizer(self.Reader([(quad, "LAS BLANCAS JUEGAN PRIMERO", 0.88)])).read(image())
        self.assertEqual(boxes[0].bbox, (2.0, 3.0, 40.0, 15.0))
        self.assertAlmostEqual(boxes[0].confidence, 0.88)


class TesseractTests(unittest.TestCase):
    class Modulo:
        class Output:
            DICT = "dict"

        def __init__(self, dados: dict[str, list[Any]]) -> None:
            self.dados = dados
            self.config = ""

        def image_to_data(self, _imagem: Any, *, lang: str, config: str, output_type: str) -> dict[str, list[Any]]:
            self.config = config
            self.lang = lang
            return self.dados

    DADOS = {
        "text": ["", "White to move", "ruido"],
        "conf": [-1, 96, 12],
        "left": [0, 10, 5],
        "top": [0, 20, 40],
        "width": [0, 60, 30],
        "height": [0, 12, 10],
    }

    def test_caixas_de_layout_e_ruido_saem(self) -> None:
        modulo = self.Modulo(self.DADOS)
        boxes = TesseractRecognizer(modulo, ("en",)).read(image())

        self.assertEqual([box.text for box in boxes], ["White to move"])
        self.assertEqual(boxes[0].bbox, (10.0, 20.0, 70.0, 32.0))

    def test_idiomas_viram_codigo_do_traineddata(self) -> None:
        modulo = self.Modulo(self.DADOS)
        recognizer = TesseractRecognizer(modulo, ("pt", "en", "es", "de"))
        self.assertEqual(recognizer.name, "tesseract (por+eng+spa+deu)")

    def test_allowlist_vira_whitelist_do_tesseract(self) -> None:
        modulo = self.Modulo({chave: [] for chave in self.DADOS})
        TesseractRecognizer(modulo, ("en",)).read(image(), allowlist="WB")
        self.assertIn("tessedit_char_whitelist=WB", modulo.config)


class ProtocolTests(unittest.TestCase):
    def test_os_tres_provedores_e_o_fake_satisfazem_a_interface(self) -> None:
        provedores = (
            RapidOcrRecognizer(lambda _i: (None, 0.0)),
            EasyOcrRecognizer(EasyOcrTests.Reader([])),
            TesseractRecognizer(TesseractTests.Modulo(TesseractTests.DADOS), ("en",)),
            FakeRecognizer(),
        )
        for provedor in provedores:
            with self.subTest(provedor=type(provedor).__name__):
                self.assertIsInstance(provedor, TextRecognizer)


class InstalledEngineContractTests(unittest.TestCase):
    """Contrato de cada motor de verdade, pulado quando ele não está instalado.

    Nenhum está nesta máquina. O teste existe para quem instalar o extra: é a diferença
    entre "a interface compila" e "o motor obedece a ela".
    """

    def test_motor_instalado_le_uma_imagem_sem_levantar(self) -> None:
        for motor in KNOWN_ENGINES:
            with self.subTest(motor=motor):
                recognizer = build_recognizer(OcrSettings(enabled=True, engine=motor))
                if recognizer is None:
                    self.skipTest(f"motor {motor} não instalado")
                boxes = recognizer.read(image(200, 60))
                self.assertIsInstance(boxes, list)
                for box in boxes:
                    self.assertIsInstance(box, TextBox)


if __name__ == "__main__":
    unittest.main()
