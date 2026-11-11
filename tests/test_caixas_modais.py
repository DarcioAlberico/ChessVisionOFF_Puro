"""Uma caixa modal aberta sem remendo reprova o teste, e rápido, em vez de parar a suíte (S-872).

A prova é um pytest **filho**, com o `conftest` desta suíte carregado como plugin: o que se quer ver é
o desfecho da sessão inteira -- reprovou, com a frase da caixa, e não ficou parada --, e isso não se
observa de dentro do próprio teste que a abriria. O caso que motivou é o primeiro: a caixa de falha
da aba Texto, um `QMessageBox` montado e aberto por `exec()` de instância, que o desarme de antes não
cobria e que travou a integração da solidez em `tests/test_qt_texto_prosa.py`.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from subprocesso import rodar_python

TESTES = Path(__file__).resolve().parent

SONDAS = """
from unittest import mock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox

from chess_diagram_ocr.qt import dialogos

APP = QApplication.instance() or QApplication([])


def test_falha_da_leitura_sem_remendo():
    dialogos.mostrar_falha(None, "A leitura nao terminou", "A pagina 3 nao foi lida.", "Traceback: rastro")


def test_falha_aberta_por_um_slot():
    QTimer.singleShot(0, lambda: dialogos.mostrar_falha(None, "Pelo slot", "aberta por um sinal"))
    for _ in range(5):
        APP.processEvents()


def test_arquivo_sem_remendo():
    QFileDialog.getOpenFileName(None, "Escolha o livro", "", "PDF (*.pdf)")


def test_texto_sem_remendo():
    QInputDialog.getText(None, "Nome da folha", "Como chamar a folha?")


def test_menu_sem_remendo():
    menu = QMenu()
    menu.addAction("Apagar folha")
    menu.exec()


def test_pergunta_estatica_sem_remendo():
    QMessageBox.question(None, "Descartar?", "Descartar as correcoes?")


def test_o_remendo_do_teste_vence():
    with mock.patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes):
        assert dialogos.perguntar_recusando(None, "Apagar?", "Apagar a folha?")
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        assert QMessageBox.question(None, "t", "q") == QMessageBox.StandardButton.Yes
"""

ESPERA_DO_FILHO = 120.0
"""Segundos. O filho termina em poucos; sem o desarme ele fica parado na primeira caixa até isto."""


@unittest.skipUnless(importlib.util.find_spec("PyQt6"), "PyQt6 ausente")
class CaixaSemRemendoReprovaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with tempfile.TemporaryDirectory(prefix="cvoff-caixas-") as pasta:
            arquivo = Path(pasta) / "test_sondas_de_caixa.py"
            arquivo.write_bytes(SONDAS.encode("utf-8"))
            argumentos = [str(arquivo), "-p", "conftest", "-p", "no:cacheprovider", "-q", "--rootdir", pasta]
            codigo = (
                f"import sys; sys.path.insert(0, {str(TESTES)!r}); import pytest; "
                f"sys.exit(pytest.main({json.dumps(argumentos)}))"
            )
            try:
                cls.filho = rodar_python(codigo, check=False, timeout=ESPERA_DO_FILHO)
            except subprocess.TimeoutExpired as estouro:
                raise AssertionError(
                    f"o pytest filho ficou parado {ESPERA_DO_FILHO:.0f} s: uma caixa modal abriu de verdade"
                ) from estouro
        cls.saida = cls.filho.stdout + cls.filho.stderr

    def test_a_sessao_termina_reprovando_as_seis_caixas_e_aprovando_o_remendo(self) -> None:
        self.assertEqual(1, self.filho.returncode, self.saida[-3000:])
        # As seis caixas reprovam na desmontagem (`error`); o corpo de cada teste chega ao fim (`passed`).
        self.assertIn("7 passed, 6 errors", self.saida, self.saida[-3000:])

    def test_a_reprovacao_traz_a_frase_que_a_caixa_mostraria(self) -> None:
        for frase in (
            "A leitura nao terminou",
            "A pagina 3 nao foi lida.",
            "aberta por um sinal",
            "Escolha o livro",
            "Como chamar a folha?",
            "Apagar folha",
            "Descartar as correcoes?",
        ):
            with self.subTest(frase=frase):
                self.assertIn(frase, self.saida)

    def test_a_reprovacao_aponta_a_linha_do_teste(self) -> None:
        self.assertIn("test_sondas_de_caixa.py:", self.saida)
        self.assertIn("test_falha_da_leitura_sem_remendo", self.saida)


if __name__ == "__main__":
    unittest.main()
