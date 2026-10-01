"""O recorte do diagrama no Qt: o que ele desenha, o que ele emite e o que o teclado alcança.

A regra (casa ↔ pixel, dica, âmbar) é de `ui/recorte_do_diagrama.py` e tem teste sem janela. Aqui
se afirma o que só existe deste lado: que um clique num pixel vira a casa certa, que o ponteiro e
o teclado emitem o que o tabuleiro ao lado espelha, e que o vazio é desenhado com uma frase.
"""

from __future__ import annotations

import unittest

import numpy as np
from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.ui import recorte_do_diagrama as regra

if TEM_PYQT:
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QKeyEvent, QMouseEvent
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt.painel_de_recorte import (
        LADO_MINIMO,
        LADO_PREFERIDO,
        MENSAGEM_SEM_RECORTE,
        PainelDeRecorte,
    )


def _recorte_rgb() -> np.ndarray:
    return np.full((256, 256, 3), 180, np.uint8)


def _probs() -> np.ndarray:
    probs = np.zeros((64, len(PIECE_CLASSES)))
    probs[:, PIECE_CLASSES.index("empty")] = 1.0
    probs[12] = 0.0
    probs[12, PIECE_CLASSES.index("Q")] = 0.6
    probs[12, PIECE_CLASSES.index("q")] = 0.35
    probs[12, PIECE_CLASSES.index("empty")] = 0.05
    return probs


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelDeRecorteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.recorte = PainelDeRecorte()
        self.addCleanup(self.recorte.deleteLater)
        self.recorte.resize(328, 328)
        self.recorte.show()
        self.app.processEvents()
        self.clicadas: list[int] = []
        self.apontadas: list[object] = []
        self.recorte.casa_clicada.connect(self.clicadas.append)
        self.recorte.casa_apontada.connect(self.apontadas.append)

    def mostrar(self, *, virado: bool = False) -> None:
        tinta = regra.tinta_do_diagrama(_probs())
        self.recorte.mostrar(_recorte_rgb(), virado=virado, tinta=tinta, leituras=_probs())

    def centro(self, casa: int) -> QPoint:
        return self.recorte.retangulo_da_casa(casa).center().toPoint()

    # ------------------------------------------------------------------------------ estado

    def test_nasce_vazio_e_nomeado_e_focavel(self) -> None:
        self.assertFalse(self.recorte.tem_recorte())
        self.assertEqual(self.recorte.accessibleName(), "Recorte do diagrama")
        self.assertNotEqual(self.recorte.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(self.recorte.minimumWidth(), LADO_MINIMO)
        self.assertEqual(self.recorte.sizeHint().width(), LADO_PREFERIDO)

    def test_o_vazio_tem_uma_frase_que_orienta(self) -> None:
        self.assertIn("recorte", MENSAGEM_SEM_RECORTE)
        self.assertIsNone(self.recorte.casa_em(self.recorte.rect().center()), "sem recorte não há casa")

    def test_mostrar_e_limpar(self) -> None:
        self.mostrar()
        self.assertTrue(self.recorte.tem_recorte())
        self.assertEqual(self.recorte.casas_marcadas()["hesitacao"], (12,))
        self.recorte.limpar()
        self.assertFalse(self.recorte.tem_recorte())
        self.assertEqual(self.recorte.casas_marcadas()["hesitacao"], ())

    def test_o_centro_de_cada_casa_cai_nela(self) -> None:
        for virado in (False, True):
            self.mostrar(virado=virado)
            for casa in (0, 7, 27, 56, 63):
                with self.subTest(casa=casa, virado=virado):
                    self.assertEqual(self.recorte.casa_em(self.centro(casa)), casa)

    def test_a_dica_diz_as_leituras_da_casa(self) -> None:
        self.mostrar()
        self.assertTrue(self.recorte.dica_da_casa(12).startswith("e7 · dama branca 0,600"))
        self.assertEqual(self.recorte.dica_da_casa(0).split(" · ")[1], "vazia 1,000")

    # ------------------------------------------------------------------------------ gestos

    def test_o_clique_emite_a_casa(self) -> None:
        self.mostrar()
        QTest.mouseClick(self.recorte, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, self.centro(27))
        self.assertEqual(self.clicadas, [27])

    def test_o_clique_sem_recorte_nao_emite(self) -> None:
        QTest.mouseClick(self.recorte, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 50))
        self.assertEqual(self.clicadas, [])

    def test_o_ponteiro_emite_a_casa_e_o_none_ao_sair(self) -> None:
        self.mostrar()
        ponto = self.centro(9)
        self.recorte.mouseMoveEvent(
            QMouseEvent(QEvent.Type.MouseMove, QPointF(ponto), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        )
        self.assertEqual(self.apontadas, [9])
        self.assertEqual(self.recorte.casas_marcadas()["apontada"], (9,))
        self.recorte.leaveEvent(QEvent(QEvent.Type.Leave))
        self.assertEqual(self.apontadas, [9, None])

    def test_apontar_e_selecionar_de_fora_nao_emitem_de_volta(self) -> None:
        """O espelho: o tabuleiro aponta aqui, e emitir de volta seria o laço infinito."""
        self.mostrar()
        self.recorte.apontar(5)
        self.recorte.selecionar(6)
        self.assertEqual(self.apontadas, [])
        self.assertEqual(self.recorte.casas_marcadas()["apontada"], (5,))
        self.assertEqual(self.recorte.casas_marcadas()["selecionada"], (6,))
        self.recorte.apontar(None)
        self.recorte.selecionar("nada")  # type: ignore[arg-type]
        self.assertEqual(self.recorte.casas_marcadas()["apontada"], ())
        self.assertEqual(self.recorte.casas_marcadas()["selecionada"], ())

    def test_as_setas_andam_e_o_enter_clica(self) -> None:
        self.mostrar()
        self.recorte.selecionar(27)
        for tecla, esperada in ((Qt.Key.Key_Right, 28), (Qt.Key.Key_Down, 36), (Qt.Key.Key_Left, 35), (Qt.Key.Key_Up, 27)):
            self.recorte.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))
            self.assertEqual(self.recorte.apontada(), esperada, tecla)
        self.recorte.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.clicadas, [27])

    def test_a_seta_nao_da_a_volta_na_linha(self) -> None:
        self.mostrar()
        self.recorte.apontar(7)
        self.recorte.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.recorte.apontada(), 7, "h8 → Direita não vai para a7")

    def test_desenhar_com_marcas_nao_levanta(self) -> None:
        self.mostrar(virado=True)
        self.recorte.apontar(3)
        self.recorte.selecionar(12)
        self.recorte.repaint()
        self.recorte.limpar()
        self.recorte.repaint()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
