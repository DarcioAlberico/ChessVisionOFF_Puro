"""O que o `eventFilter` do `PainelDeTexto` faz, assunto por assunto (S-825).

**Caracterização, e não defeito.** O filtro era uma cadeia de `if` com nove assuntos; a S-825 o
trocou por uma tabela `(objeto, tipo do evento) -> tratador`. Estes testes foram escritos **antes**
da troca, contra a cadeia, e passam igual depois dela: cada um entrega o evento como o Qt entrega
(por `QTest` ou `sendEvent`) e confere o que a pessoa veria. Cada assunto tem também o lado em que
o filtro **não** come o evento, porque o erro de uma tabela é o evento que passa a ser engolido.
"""

from __future__ import annotations

import unittest

import test_qt_texto_diagramas as diagramas
from qt_app import MOTIVO, TEM_PYQT

from chess_diagram_ocr.text import rico

if TEM_PYQT:
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QHelpEvent, QTextCursor, QWheelEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QToolTip


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FiltroDoPainelTests(diagramas._Aba):
    ponto_da_miniatura = diagramas.CliqueNaMiniaturaTests.ponto_da_miniatura

    def folha_com_diagrama(self) -> None:
        self.painel.mostrar_pagina(diagramas._pagina(), folha_rgb=diagramas._folha())

    def pedidos_na_sala(self) -> list[tuple[int, int]]:
        pedidos: list[tuple[int, int]] = []
        self.painel.diagrama_ativado.connect(lambda folha, indice: pedidos.append((folha, indice)))
        return pedidos

    def selecionar(self, inicio: int, fim: int) -> None:
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel.espelho.mapa.posicao(inicio))
        cursor.setPosition(self.painel.espelho.mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.painel.editor.setTextCursor(cursor)

    def rodar(self, passo: int, modificador: Qt.KeyboardModifier) -> bool:
        viewport = self.painel.editor.viewport()
        assert viewport is not None
        evento = QWheelEvent(
            QPointF(30, 30),
            QPointF(viewport.mapToGlobal(QPoint(30, 30))),
            QPoint(0, 0),
            QPoint(0, passo),
            Qt.MouseButton.NoButton,
            modificador,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        return bool(QApplication.sendEvent(viewport, evento))

    # 1. o histórico do teclado
    def test_ctrl_z_e_ctrl_y_dentro_da_folha_sao_do_painel(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("Uma frase."))
        self.painel.editor.setFocus()
        cursor = self.painel.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClicks(self.painel.editor, " Mais")
        self.assertEqual(self.painel.texto(), "Uma frase. Mais")
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.painel.texto(), "Uma frase.")
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.painel.texto(), "Uma frase. Mais")
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Z)  # sem Ctrl é a letra
        self.assertEqual(self.painel.texto(), "Uma frase. Maisz")

    # 2. o Esc
    def test_esc_sai_do_modo_foco_e_sem_nada_armado_passa(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("Uma frase."))
        self.painel.alternar_modo_foco()
        self.painel.editor.setFocus()
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Escape)
        self.assertFalse(self.painel.barra_do_foco.isVisibleTo(self.painel), "o Esc não saiu do modo foco")
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Escape)  # nada armado: o Esc segue, e não reabre
        self.assertFalse(self.painel.barra_do_foco.isVisibleTo(self.painel))
        self.assertEqual(self.painel.texto(), "Uma frase.")

    # 3. o Enter na marca
    def test_enter_na_marca_inteira_pede_o_diagrama_e_com_outra_selecao_e_o_enter(self) -> None:
        self.folha_com_diagrama()
        pedidos = self.pedidos_na_sala()
        self.painel.editor.setFocus()
        inicio = self.painel.texto().index("[Diagrama 1]")
        self.selecionar(inicio, inicio + len("[Diagrama 1]"))
        antes = self.painel.texto()
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Return)
        self.assertEqual(pedidos, [(0, 0)])
        self.assertEqual(self.painel.texto(), antes)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(pedidos, [(0, 0)], "Shift+Enter não é a ativação da marca")
        self.selecionar(0, 5)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Enter)
        self.assertEqual(pedidos, [(0, 0)])
        self.assertNotEqual(self.painel.texto(), antes)

    # 4. o clique no rodapé
    def test_o_clique_no_rodape_devolve_a_fita_e_vai_ao_campo_de_folha(self) -> None:
        self.painel.fita.setCurrentIndex(0)
        self.painel.alternar_fita()
        self.assertTrue(self.painel.fita.recolhida)
        QTest.mouseClick(self.painel.vista.status, Qt.MouseButton.RightButton)  # qualquer botão
        self.assertFalse(self.painel.fita.recolhida)
        self.assertTrue(self.painel.leitura.campo_de_folha.isVisible())

    # 5. o vazio acompanha a folha
    def test_o_vazio_acompanha_a_area_da_folha_quando_ela_muda_de_tamanho(self) -> None:
        self.painel.desenhar_documento(rico.DocumentoRico())
        viewport = self.painel.editor.viewport()
        assert viewport is not None
        for largura, altura in ((900, 640), (520, 380)):
            self.painel.resize(largura, altura)
            self.app.processEvents()
            self.assertEqual(self.painel.vazio.geometry(), viewport.rect())

    # 6. a dica
    def test_a_dica_sobre_a_miniatura_e_fora_dela(self) -> None:
        self.folha_com_diagrama()
        viewport = self.painel.editor.viewport()
        assert viewport is not None
        ponto = self.ponto_da_miniatura()
        evento = QHelpEvent(QEvent.Type.ToolTip, ponto, viewport.mapToGlobal(ponto))  # type: ignore[arg-type]
        self.assertTrue(QApplication.sendEvent(viewport, evento))
        self.assertTrue(QToolTip.text().startswith("Diagrama 1"))
        fora = QHelpEvent(QEvent.Type.ToolTip, QPoint(4, 4), viewport.mapToGlobal(QPoint(4, 4)))
        self.assertTrue(QApplication.sendEvent(viewport, fora), "fora da marca a dica é escondida, e o evento comido")
        QTest.qWait(500)  # o Qt esconde a dica com um relógio, e não na hora
        self.assertFalse(QToolTip.isVisible())

    # 7. Ctrl+roda
    def test_ctrl_roda_e_o_zoom_da_vista_e_a_roda_sozinha_rola(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("Uma frase."))
        self.assertTrue(self.rodar(+120, Qt.KeyboardModifier.ControlModifier))
        self.assertEqual(self.painel.vista.zoom_da_vista, 1)
        self.assertTrue(self.rodar(0, Qt.KeyboardModifier.ControlModifier), "Ctrl+roda parada também é do painel")
        self.assertEqual(self.painel.vista.zoom_da_vista, 1)
        self.rodar(+120, Qt.KeyboardModifier.NoModifier)
        self.assertEqual(self.painel.vista.zoom_da_vista, 1, "a roda sem Ctrl mexeu no zoom")

    # 8. o clique na miniatura
    def test_o_clique_esquerdo_na_miniatura_seleciona_a_marca_e_o_direito_nao(self) -> None:
        self.folha_com_diagrama()
        viewport = self.painel.editor.viewport()
        assert viewport is not None
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
        self.assertEqual(self.painel.editor.textCursor().selectedText(), "")
        QTest.mouseClick(viewport, Qt.MouseButton.RightButton, pos=self.ponto_da_miniatura())
        self.assertEqual(self.painel.editor.textCursor().selectedText(), "")
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=self.ponto_da_miniatura())
        self.assertEqual(self.painel.editor.textCursor().selectedText(), "[Diagrama 1]")

    # 9. o duplo clique na miniatura
    def test_o_duplo_clique_na_miniatura_pede_o_diagrama_e_fora_dela_nao(self) -> None:
        self.folha_com_diagrama()
        pedidos = self.pedidos_na_sala()
        viewport = self.painel.editor.viewport()
        assert viewport is not None
        QTest.mouseDClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
        self.assertEqual(pedidos, [])
        QTest.mouseDClick(viewport, Qt.MouseButton.LeftButton, pos=self.ponto_da_miniatura())
        self.assertEqual(pedidos, [(0, 0)])
