"""O leitor de marcas que morre antes da resposta chegar (`qt/marcas.LeitorDeMarcas`).

**O que isto fecha.** A `Tarefa` da leitura é sem pai (`qt/trabalho.manter_viva`) e sobrevive à
janela, e os slots dela eram lambdas sobre `self`. Fechada a janela antes de o `labels.csv`
acabar de ser lido, a resposta encontrava o embrulho Python de um `LeitorDeMarcas` já apagado no
C++, `self.prontas.emit` levantava `RuntimeError` dentro do slot, e o PyQt6 transforma exceção não
tratada em slot em `qFatal`: o processo morria com `STATUS_STACK_BUFFER_OVERRUN` e nenhuma linha
de traceback. Na CI do 3.13 era a suíte inteira, parada em `test_box_drop` -- o teste seguinte
ao que troca de livro sem esperar a leitura.

O `sys.excepthook` é trocado por um que anota: com o padrão, a regressão derrubaria o processo
em vez de reprovar este teste.
"""

from __future__ import annotations

import sys
import threading
import unittest
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

if TEM_PYQT:
    from PyQt6 import sip
    from PyQt6.QtCore import QObject
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import marcas, trabalho
    from chess_diagram_ocr.qt.marcas import LeitorDeMarcas


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LeitorQueMorreAntesDaRespostaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.solta = threading.Event()
        self.addCleanup(self.solta.set)
        self.excecoes: list[object] = []

    def _morrer_no_meio(self, leitura) -> None:
        dono = QObject()
        leitor = LeitorDeMarcas(lambda: self.pasta / "labels.csv", dono, em_processo=False)
        recebidas: list[object] = []
        leitor.prontas.connect(lambda livro, marcas_: recebidas.append(livro))
        with (
            mock.patch.object(marcas, "ler_marcas_e_treino", leitura),
            mock.patch.object(sys, "excepthook", lambda *args: self.excecoes.append(args[1])),
        ):
            leitor.pedir(self.pasta / "livro.pdf")
            tarefa = leitor._tarefa
            descartar(dono)
            self.assertTrue(sip.isdeleted(leitor), "o leitor morreu com o dono, antes da resposta")
            self.solta.set()
            for _ in range(500):
                QTest.qWait(10)
                if tarefa not in trabalho._VIVAS:
                    break
        self.assertNotIn(tarefa, trabalho._VIVAS, "a tarefa terminou e foi solta")
        self.assertEqual(self.excecoes, [], "o slot tocou um leitor apagado")
        self.assertEqual(recebidas, [], "a resposta de um leitor morto não é entregue")

    def test_a_resposta_que_chega_depois_nao_levanta_no_slot(self) -> None:
        def lenta(*_args: object) -> object:
            self.solta.wait(5)
            return ({}, None, {})

        self._morrer_no_meio(lenta)

    def test_a_falha_que_chega_depois_nao_levanta_no_slot(self) -> None:
        def falha(*_args: object) -> object:
            self.solta.wait(5)
            raise OSError("labels.csv sumiu")

        self._morrer_no_meio(falha)


if __name__ == "__main__":
    unittest.main()
