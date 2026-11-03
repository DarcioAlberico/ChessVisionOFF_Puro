"""O zoom da aba Texto à vista, no rodapé (S-630).

O zoom existia desde a S-264 -- `Ctrl+roda`, `Ctrl++`, `Ctrl+-`, três itens de menu -- e o pedido
"opção para aumentar e diminuir a fonte da aba texto" mostrou que ninguém o achava. Estes testes
cobram o controle visível: a régua com uma parada por letra diferente, a porcentagem, os dois
botões, o que o leitor de tela ouve, e a roda que deixa parada a linha sob o ponteiro.
"""

from __future__ import annotations

import unittest

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui import texto_declarado, tipografia

if TEM_PYQT:
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent

    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto


class ParadasTests(unittest.TestCase):
    """As duas decisões puras de `ui/texto_declarado`."""

    def test_degraus_que_dao_a_mesma_letra_viram_uma_parada(self) -> None:
        """Numa fonte de 9 pt, −3 e −2 dão os mesmos 7 pt (o piso de legibilidade)."""
        paradas = texto_declarado.paradas_do_zoom(9)
        corpos = [tipografia.corpo(p, base=9) for p in paradas]
        self.assertEqual(len(corpos), len(set(corpos)), "cada parada é uma letra diferente")
        self.assertNotIn(-3, paradas)
        self.assertIn(-2, paradas, "do empate fica o degrau mais perto de zero")
        self.assertIn(0, paradas)
        self.assertEqual(paradas[-1], texto_declarado.ZOOM_MAXIMO)

    def test_numa_fonte_grande_todas_as_paradas_existem(self) -> None:
        paradas = texto_declarado.paradas_do_zoom(14)
        self.assertEqual(paradas, tuple(range(texto_declarado.ZOOM_MINIMO, texto_declarado.ZOOM_MAXIMO + 1)))

    def test_a_porcentagem_e_a_letra_sobre_a_letra_sem_zoom(self) -> None:
        self.assertEqual(texto_declarado.porcentagem_do_zoom(0, 9), 100)
        esperado = round(100 * tipografia.corpo(3, base=9) / tipografia.corpo(0, base=9))
        self.assertEqual(texto_declarado.porcentagem_do_zoom(3, 9), esperado)
        self.assertGreater(esperado, 100)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RodapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(700, 400)
        self.painel.show()
        self.app.processEvents()
        self.base = tema.fonte_base()[0]

    def test_o_controle_esta_no_rodape_e_comeca_em_100(self) -> None:
        self.assertTrue(self.painel.regua_do_zoom.isVisible())
        self.assertEqual(self.painel.porcentagem_do_zoom.text(), "100%")

    def test_o_mais_aproxima_e_o_valor_acompanha(self) -> None:
        self.painel.botao_de_aproximar.click()
        self.assertEqual(self.painel.zoom_da_vista, 1)
        esperado = texto_declarado.porcentagem_do_zoom(1, self.base)
        self.assertEqual(self.painel.porcentagem_do_zoom.text(), f"{esperado}%")

    def test_a_regua_e_o_atalho_dao_o_mesmo_resultado(self) -> None:
        paradas = texto_declarado.paradas_do_zoom(self.base)
        self.painel.regua_do_zoom.setValue(paradas.index(2))
        self.assertEqual(self.painel.zoom_da_vista, 2)
        self.painel.aplicar_zoom(4)
        self.assertEqual(paradas[self.painel.regua_do_zoom.value()], 4, "a régua segue o zoom vindo de outro lugar")

    def test_o_clique_na_porcentagem_volta_a_100(self) -> None:
        self.painel.aplicar_zoom(3)
        self.painel.porcentagem_do_zoom.click()
        self.assertEqual(self.painel.zoom_da_vista, 0)
        self.assertEqual(self.painel.porcentagem_do_zoom.text(), "100%")

    def test_nos_limites_o_botao_daquele_lado_desliga(self) -> None:
        paradas = texto_declarado.paradas_do_zoom(self.base)
        self.painel.aplicar_zoom(paradas[-1])
        self.assertFalse(self.painel.botao_de_aproximar.isEnabled())
        self.assertTrue(self.painel.botao_de_afastar.isEnabled())
        self.painel.aplicar_zoom(paradas[0])
        self.assertFalse(self.painel.botao_de_afastar.isEnabled())

    def test_cada_clique_muda_a_letra(self) -> None:
        """De parada em parada: nenhum `−` fica sem efeito perto do piso de legibilidade."""
        vistos = [self.painel._base[0]]
        while self.painel.botao_de_afastar.isEnabled():
            self.painel.botao_de_afastar.click()
            vistos.append(self.painel._base[0])
        self.assertEqual(len(vistos), len(set(vistos)))

    def test_o_leitor_de_tela_ouve_o_nome_e_a_porcentagem(self) -> None:
        self.painel.aplicar_zoom(2)
        porcentagem = texto_declarado.porcentagem_do_zoom(2, self.base)
        self.assertEqual(self.painel.regua_do_zoom.accessibleName(), "Zoom do texto")
        self.assertIn(f"{porcentagem} por cento", self.painel.regua_do_zoom.accessibleDescription())
        self.assertIn("não muda o documento", self.painel.botao_de_aproximar.toolTip())

    def test_o_zoom_nao_vira_alteracao_por_gravar(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("uma folha"))
        self.painel._documento_gravado = self.painel.documento
        self.painel.botao_de_aproximar.click()
        self.assertFalse(self.painel.tem_alteracoes)

    def test_a_roda_deixa_parada_a_linha_sob_o_ponteiro(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("\n".join(f"linha {n} da folha" for n in range(200))))
        self.app.processEvents()
        barra = self.painel.editor.verticalScrollBar()
        barra.setValue(barra.maximum() // 2)
        self.app.processEvents()
        ponto = QPoint(30, self.painel.editor.viewport().height() // 2)
        antes = self.painel.editor.cursorForPosition(ponto).block().blockNumber()
        evento = QWheelEvent(
            QPointF(ponto),
            QPointF(self.painel.editor.viewport().mapToGlobal(ponto)),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        self.app.sendEvent(self.painel.editor.viewport(), evento)
        self.app.processEvents()
        self.assertEqual(self.painel.zoom_da_vista, 1)
        depois = self.painel.editor.cursorForPosition(ponto).block().blockNumber()
        self.assertEqual(depois, antes)


if __name__ == "__main__":
    unittest.main()
