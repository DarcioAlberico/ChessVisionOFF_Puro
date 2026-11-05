"""Três decisões que o porte para o Qt deixou sem chamador, religadas (S-248, S-292, casa marcada).

Cada uma estava em `SEM_CHAMADOR`, em `test_ui_orfaos`, com o motivo escrito. Os testes afirmam o efeito:
o que a tela e o documento dizem depois do gesto.
"""

from __future__ import annotations

import unittest

import chess
import chess.pgn
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar, pixels_diferentes, renderizar

from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui import texto_declarado

if TEM_PYQT:
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
    from chess_diagram_ocr.qt.tabuleiro_de_jogo import TabuleiroDeJogo


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Aba(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(900, 600)
        self.painel.show()
        self.painel.activateWindow()
        self.app.processEvents()

    def digitar(self, texto: str) -> None:
        self.painel.desenhar_documento(rico.de_texto("abc "))
        self.painel.editor.setFocus()
        cursor = self.painel.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClicks(self.painel.editor, texto)
        self.app.processEvents()


class SequenciaDaPaletaTests(_Aba):
    r"""`\N` vira `♘` ao fechar, com as três regras da S-248."""

    def test_a_sequencia_fechada_vira_o_simbolo_no_documento_e_na_tela(self) -> None:
        self.digitar("\\Nf3")
        self.assertEqual(self.painel.documento.para_texto(), "abc ♘f3")
        self.assertEqual(self.painel.editor.toPlainText(), "abc ♘f3")

    def test_a_sequencia_de_dois_caracteres_fecha_no_segundo(self) -> None:
        self.digitar("\\+-")
        self.assertEqual(self.painel.documento.para_texto(), "abc ±")

    def test_a_barra_sozinha_continua_barra(self) -> None:
        self.digitar("\\")
        self.assertEqual(self.painel.documento.para_texto(), "abc \\")

    def test_barra_com_tecla_que_nao_abre_sequencia_devolve_os_dois(self) -> None:
        self.digitar("\\z")
        self.assertEqual(self.painel.documento.para_texto(), "abc \\z")

    def test_sem_a_barra_nada_e_trocado(self) -> None:
        self.digitar("Nf3")
        self.assertEqual(self.painel.documento.para_texto(), "abc Nf3")

    def test_o_cursor_fica_depois_do_simbolo_e_a_digitacao_continua(self) -> None:
        self.digitar("\\N")
        QTest.keyClicks(self.painel.editor, "e2")
        self.app.processEvents()
        self.assertEqual(self.painel.documento.para_texto(), "abc ♘e2")

    def test_desfazer_devolve_o_que_foi_digitado(self) -> None:
        self.digitar("\\N")
        self.painel.desfazer()
        self.assertEqual(self.painel.documento.para_texto(), "abc \\N")

    def test_colar_nao_e_tecla(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("abc "))
        cursor = self.painel.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText("\\N")
        self.app.processEvents()
        self.assertEqual(self.painel.documento.para_texto(), "abc \\N")


class MostradorDeCorpoTests(_Aba):
    def test_selecao_mista_diz_meia_risca_e_nao_um_numero(self) -> None:
        caixa = self.painel.caixa_de_corpo
        caixa.setValue(caixa.minimum())
        self.assertEqual(caixa.text().strip(), texto_declarado.ROTULO_DO_CORPO_MISTO)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class CasaMarcadaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.tabuleiro = TabuleiroDeJogo()
        self.addCleanup(descartar, self.tabuleiro)
        self.tabuleiro.resize(400, 400)
        self.tabuleiro.show()
        self.app.processEvents()
        self.emitidas: list[tuple[int, int, str]] = []
        self.tabuleiro.seta.connect(lambda a, b, c: self.emitidas.append((a, b, c)))

    def _clique_direito(self) -> None:
        centro = QPointF(self.tabuleiro.rect().center())
        for tipo, botoes in (
            (QEvent.Type.MouseButtonPress, Qt.MouseButton.RightButton),
            (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
        ):
            evento = QMouseEvent(tipo, centro, centro, Qt.MouseButton.RightButton, botoes, Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(self.tabuleiro, evento)
        self.app.processEvents()

    def test_clique_direito_sem_arrastar_marca_a_casa(self) -> None:
        self._clique_direito()
        self.assertEqual(len(self.emitidas), 1)
        origem, destino, _cor = self.emitidas[0]
        self.assertEqual(origem, destino)

    def test_a_casa_marcada_aparece_na_tela(self) -> None:
        antes = renderizar(self.tabuleiro)
        self.tabuleiro.definir_setas([(27, 27, "green")])
        self.app.processEvents()
        self.assertGreater(pixels_diferentes(antes, renderizar(self.tabuleiro)), 0)

    def test_o_gesto_grava_csl_e_o_mesmo_gesto_tira(self) -> None:
        jogo = chess.pgn.Game()
        estudo_mod.trocar_seta(jogo, chess.D4, chess.D4, "green")
        self.assertIn("[%csl Gd4]", jogo.comment)
        estudo_mod.trocar_seta(jogo, chess.D4, chess.D4, "green")
        self.assertNotIn("csl", jogo.comment)


if __name__ == "__main__":
    unittest.main()
