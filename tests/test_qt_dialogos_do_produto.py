"""A lista de diálogos que o pacote `qt/` declara, achada no código (F9-C12/F9-C14, S-886).

`dialogos_do_produto` é lida por quem confere o teclado de cada janela; uma lista que perde um
diálogo deixa aquela janela fora da conferência sem reprovar nada. Os testes daqui fazem o que o
crítico do ciclo 13 fez -- esconder um diálogo de três jeitos -- e conferem que a lista ainda o acha,
e que a varredura, que lê texto, concorda com a importação, que lê classe.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT

from chess_diagram_ocr import qt as pacote_qt


def _escrever(pasta: Path, relativo: str, texto: str) -> None:
    caminho = pasta / relativo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(texto.encode("utf-8"))


class SabotagemTests(unittest.TestCase):
    """Os jeitos de esconder um diálogo da árvore sintática, e o que ela ainda acha."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)

    def test_os_tres_buracos_do_ciclo_13_ficam_fechados(self) -> None:
        _escrever(
            self.pasta,
            "apelido.py",
            "from PyQt6.QtWidgets import QDialog\nBase = QDialog\nclass PorApelido(Base):\n    pass\n",
        )
        _escrever(self.pasta, "mensagem.py", "class PorMensagem(QMessageBox):\n    pass\n")
        _escrever(self.pasta, "sub/pasta/novo.py", "class NoSubmodulo(QDialog):\n    pass\n")
        self.assertEqual(
            pacote_qt.dialogos_do_produto(self.pasta), ("NoSubmodulo", "PorApelido", "PorMensagem")
        )

    def test_heranca_dentro_do_pacote_e_seguida_ate_o_fim(self) -> None:
        """Neto de diálogo, noutro arquivo, entra; classe que só é widget não entra."""
        _escrever(self.pasta, "a.py", "class BaseComum(QDialog):\n    pass\n")
        _escrever(self.pasta, "b.py", "class Filho(BaseComum):\n    pass\nclass Painel(QWidget):\n    pass\n")
        _escrever(self.pasta, "c.py", "class Neto(Filho, Mistura):\n    pass\n")
        self.assertEqual(pacote_qt.dialogos_do_produto(self.pasta), ("BaseComum", "Filho", "Neto"))

    def test_base_escrita_com_o_modulo_na_frente(self) -> None:
        _escrever(
            self.pasta,
            "m.py",
            "from PyQt6 import QtWidgets\n"
            "class Direto(QtWidgets.QDialog):\n    pass\n"
            "Apelido = QtWidgets.QInputDialog\n"
            "class PeloApelido(Apelido):\n    pass\n",
        )
        self.assertEqual(pacote_qt.dialogos_do_produto(self.pasta), ("Direto", "PeloApelido"))

    def test_cadeia_de_apelidos_e_seguida_e_o_ciclo_para(self) -> None:
        _escrever(
            self.pasta,
            "m.py",
            "A = QDialog\nB = A\nC = B\nclass PelaCadeia(C):\n    pass\n"
            "P = Q\nQ = P\nclass NoCiclo(P):\n    pass\n"
            "x, y = QDialog, QDialog\nclass PorTupla(x):\n    pass\n",
        )
        # A tupla não é atribuição de um nome a um nome: a docstring diz que só esta forma se lê.
        self.assertEqual(pacote_qt.dialogos_do_produto(self.pasta), ("PelaCadeia",))

    def test_pasta_sem_dialogo_devolve_vazio(self) -> None:
        _escrever(self.pasta, "m.py", "class Nada:\n    pass\n")
        self.assertEqual(pacote_qt.dialogos_do_produto(self.pasta), ())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PacoteDeVerdadeTests(unittest.TestCase):
    """Sem argumento a varredura lê o próprio `qt/`, e concorda com o que a importação vê."""

    def test_a_varredura_acha_os_mesmos_dialogos_que_a_importacao(self) -> None:
        from PyQt6.QtWidgets import QDialog

        importados: set[str] = set()
        for info in pkgutil.walk_packages(pacote_qt.__path__, prefix=f"{pacote_qt.__name__}."):
            modulo = importlib.import_module(info.name)
            for nome, classe in inspect.getmembers(modulo, inspect.isclass):
                if classe.__module__ == modulo.__name__ and issubclass(classe, QDialog):
                    importados.add(nome)
        achados = pacote_qt.dialogos_do_produto()
        self.assertEqual(list(achados), sorted(achados))
        self.assertIn("DialogoDePartidas", achados)
        self.assertIn("_JanelaDePartidas", achados, "o sublinhado diz de quem é o código, não se a tela existe")
        self.assertEqual(set(achados), importados)


if __name__ == "__main__":
    unittest.main()
