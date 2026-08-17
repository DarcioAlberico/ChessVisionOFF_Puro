"""O que muda quando o programa é um `.exe` em vez de um checkout (S-55).

Um único defeito de empacotamento é caro de um jeito diferente dos outros: ele só aparece
na máquina de outra pessoa, e o sintoma é uma janela que some. Estes testes cobrem a parte
que **pode** ser verificada aqui — para onde o programa aponta quando `sys.frozen` está
posto — e o resto o `--selftest` responde na máquina de destino.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJETO = Path(__file__).resolve().parents[1]


class FrozenRootTests(unittest.TestCase):
    """`data/`, `models/`, `PDF/` e `PGN/` ficam **ao lado** do executável, não dentro dele."""

    def _config_congelado(self, executavel: str, meipass: str | None):
        """Reimporta `config` fingindo um bundle. É a única forma de exercitar o ramo."""
        import chess_diagram_ocr.config as config

        patches = {"frozen": True, "executable": executavel}
        if meipass is not None:
            patches["_MEIPASS"] = meipass
        with patch.multiple(sys, create=True, **patches):
            return importlib.reload(config)

    def tearDown(self) -> None:
        # Sem isto o modulo fica com a raiz falsa para todo teste que rodar depois.
        import chess_diagram_ocr.config as config

        importlib.reload(config)

    def test_a_raiz_gravavel_e_a_pasta_do_executavel(self) -> None:
        """O `labels.csv` é trabalho humano acumulado: dentro do bundle, reinstalar o apaga."""
        pasta = Path(PROJETO / "dist" / "ChessVisionOFF")
        config = self._config_congelado(str(pasta / "ChessVisionOFF.exe"), str(pasta / "_internal"))

        self.assertEqual(config.PROJECT_ROOT, pasta)
        self.assertEqual(config.DEFAULT_DATASET_CSV, pasta / "data" / "labels.csv")
        self.assertEqual(config.DEFAULT_MODEL_PATH, pasta / "models" / "piece_classifier.pt")
        self.assertEqual(config.DEFAULT_PDF_DIR, pasta / "PDF")

    def test_os_recursos_do_programa_ficam_dentro_do_bundle(self) -> None:
        """Imagem de peça é dado do programa; rótulo é dado do usuário. Não é o mesmo lugar."""
        pasta = Path(PROJETO / "dist" / "ChessVisionOFF")
        config = self._config_congelado(str(pasta / "ChessVisionOFF.exe"), str(pasta / "_internal"))

        self.assertEqual(config.BUNDLE_ROOT, pasta / "_internal")
        self.assertNotEqual(config.BUNDLE_ROOT, config.PROJECT_ROOT)

    def test_num_checkout_as_duas_raizes_coincidem(self) -> None:
        import chess_diagram_ocr.config as config

        self.assertEqual(config.PROJECT_ROOT, PROJETO)
        self.assertEqual(config.BUNDLE_ROOT, PROJETO)


class SpecTests(unittest.TestCase):
    """A spec é código que ninguém importa; sem teste, ela apodrece em silêncio."""

    def setUp(self) -> None:
        self.spec = PROJETO / "packaging" / "cvoff.spec"
        if not self.spec.exists():
            self.skipTest("packaging/cvoff.spec não existe neste checkout")
        self.texto = self.spec.read_text(encoding="utf-8")

    def test_o_ponto_de_entrada_e_a_janela(self) -> None:
        self.assertIn("app_tkinter.py", self.texto)

    def test_o_streamlit_nao_entra_no_bundle(self) -> None:
        """Desde a S-54 ele é exemplo. Empacotar um servidor web num app de desktop, não."""
        excludes = self.texto.split("excludes = [", 1)[1].split("]", 1)[0]
        self.assertIn('"streamlit"', excludes)

    def test_os_dados_do_usuario_nao_viajam_dentro_do_pacote(self) -> None:
        datas = self.texto.split("datas = [", 1)[1].split("]", 1)[0]
        for pasta in ("data", "models", "PDF", "PGN"):
            with self.subTest(pasta=pasta):
                self.assertNotIn(f'"{pasta}"', datas)

    def test_o_modo_e_onedir(self) -> None:
        """`--onefile` extrairia ~700 MB para o temp a cada execução."""
        self.assertIn("COLLECT(", self.texto)
        self.assertIn("exclude_binaries=True", self.texto)


class SelftestTests(unittest.TestCase):
    """O `--selftest` é o que responde "esta instalação funciona?" numa máquina limpa."""

    @staticmethod
    def _app_tkinter():
        """`app_tkinter.py` mora na raiz e não é pacote; o pytest só põe `src/` no path."""
        if str(PROJETO) not in sys.path:
            sys.path.insert(0, str(PROJETO))
        import app_tkinter

        return app_tkinter

    def test_sem_checkpoint_o_codigo_de_saida_diz_o_que_falta(self) -> None:
        app_tkinter = self._app_tkinter()
        with patch.object(app_tkinter, "DEFAULT_MODEL_PATH", Path("nao/existe.pt")):
            self.assertEqual(app_tkinter.selftest(pdf=Path("qualquer.pdf")), 3)

    def test_sem_pdf_o_codigo_de_saida_e_outro(self) -> None:
        """Códigos distintos porque as duas faltas pedem ações distintas do usuário."""
        app_tkinter = self._app_tkinter()
        with patch.object(app_tkinter, "find_default_pdf_path", lambda: None):
            self.assertEqual(app_tkinter.selftest(), 2)


class _RootFalsa:
    """`after(0, fn)` executa na hora. Num teste não há laço de eventos para agendar nada."""

    def __init__(self) -> None:
        self.agendados: list[str] = []

    def after(self, _atraso: int, funcao):  # noqa: ANN001, ANN202 - assinatura do Tk
        self.agendados.append(getattr(getattr(funcao, "func", funcao), "__name__", "?"))
        funcao()


def _janela_minima(app_tkinter, *, result_panel=None):  # noqa: ANN001, ANN202
    """A janela reduzida ao que `_ocr_worker` toca, com os métodos **reais** amarrados nela.

    Montar o `ChessOcrTkApp` inteiro exigiria Tk, checkpoint e PDF; o que se testa aqui é o
    `except`, e ele não depende de nenhum dos três. É o mesmo recurso da S-142.
    """
    janela_class = type(
        "JanelaMinima",
        (),
        {
            "_ocr_worker": app_tkinter.ChessOcrTkApp._ocr_worker,
            "_on_ocr_empty": app_tkinter.ChessOcrTkApp._on_ocr_empty,
            "_on_ocr_error": app_tkinter.ChessOcrTkApp._on_ocr_error,
            "_set_status": lambda self, texto: self.status.append(texto),
            "_show_results": lambda self, *_args: self.lidos.append(_args),
            "_finish_ocr_ui": lambda self: self.status.append("<fim>"),
        },
    )
    janela = janela_class()
    janela.root = _RootFalsa()
    janela.result_panel = result_panel
    janela.status = []
    janela.lidos = []
    return janela


class OcrWorkerLogTests(unittest.TestCase):
    """O worker de OCR registra a exceção como os outros cinco (S-125).

    Era o único dos seis que a engolia: o usuário do `.exe` recebia uma linha de texto e o
    arquivo de log não recebia nada. Junto com a S-127 -- que faz o arquivo existir num
    bundle -- é o par que fecha "reconhecer a página quebrou e ninguém sabe por quê".
    """

    def setUp(self) -> None:
        self.app_tkinter = SelftestTests._app_tkinter()
        self.origem = self.app_tkinter.RecognitionOrigin.for_page("livro.pdf", 16)
        self.caixas: list[tuple[str, str, str]] = []
        for nome in ("showerror", "showinfo"):
            original = getattr(self.app_tkinter.messagebox, nome)
            self.addCleanup(setattr, self.app_tkinter.messagebox, nome, original)
            setattr(
                self.app_tkinter.messagebox,
                nome,
                lambda titulo, texto, _n=nome: self.caixas.append((_n, titulo, texto)),
            )

    def _roda(self, erro: Exception, *, nivel: str):
        janela = _janela_minima(self.app_tkinter)

        def _levanta():
            raise erro

        with self.assertLogs(self.app_tkinter.logger, level=nivel) as registro:
            janela._ocr_worker(run=_levanta, origin=self.origem)
        return janela, registro

    def test_a_falha_de_verdade_vai_para_o_log_com_traceback(self) -> None:
        _janela, registro = self._roda(RuntimeError("o checkpoint é de outra arch_version"), nivel="ERROR")

        self.assertEqual(len(registro.records), 1)
        self.assertEqual(registro.records[0].levelname, "ERROR")
        self.assertIn("Traceback", registro.output[0])
        self.assertIn("pdf:livro.pdf:page:16", registro.output[0])

    def test_a_falha_de_verdade_continua_sendo_caixa_de_erro(self) -> None:
        self._roda(RuntimeError("o checkpoint é de outra arch_version"), nivel="ERROR")

        self.assertEqual([nome for nome, _t, _x in self.caixas], ["showerror"])
        self.assertIn("arch_version", self.caixas[0][2])

    def test_pagina_sem_diagrama_nao_e_erro(self) -> None:
        """Prosa, índice e página de soluções são a maioria de um livro. Não são falha."""
        _janela, registro = self._roda(
            self.app_tkinter.NoBoardDetectedError("Nenhum tabuleiro foi detectado."), nivel="INFO"
        )

        self.assertEqual(registro.records[0].levelname, "INFO")
        self.assertNotIn("Traceback", registro.output[0])
        self.assertEqual([nome for nome, _t, _x in self.caixas], ["showinfo"])

    def test_o_caminho_e_o_tipo_da_excecao_e_nao_o_texto_dela(self) -> None:
        """A separação era `"Nenhum tabuleiro foi detectado" in str(exc)`: traduzir a
        mensagem, ou mudar uma palavra dela, silenciosamente devolvia a caixa vermelha."""
        self._roda(self.app_tkinter.NoBoardDetectedError("outra frase qualquer"), nivel="INFO")

        self.assertEqual([nome for nome, _t, _x in self.caixas], ["showinfo"])

    def test_a_ui_e_liberada_nos_dois_caminhos(self) -> None:
        """O `finally` é o que devolve os botões. Perdê-lo travaria o OCR para sempre."""
        for erro in (RuntimeError("qualquer"), self.app_tkinter.NoBoardDetectedError("nada aqui")):
            with self.subTest(erro=type(erro).__name__):
                janela, _registro = self._roda(erro, nivel="INFO")
                self.assertEqual(janela.status[-1], "<fim>")


if __name__ == "__main__":
    unittest.main()
