"""O tabuleiro e a paleta de marcas: os gestos, e o que eles não podem tocar.

A decisão sobre as marcas é de `marcas_de_casa.py` e está em `tests/test_marcas_de_casa.py`. Aqui
fica o que só o widget tem: o clique em pixel que vira marca, o arrasto que vira traço, e a fronteira
com a correção de peças, que é o que `TabuleiroEditavel` faz sem ferramenta na mão.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr import marcas_de_casa as mc

if TEM_PYQT:
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QImage, QKeyEvent, QMouseEvent

    from chess_diagram_ocr.qt.paleta_de_marcas import FILEIRAS, PaletaDeMarcas
    from chess_diagram_ocr.qt.tabuleiro_de_marcas import TabuleiroDeMarcas

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
A8, E4, E2, H1 = 0, 36, 52, 63


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class GestosTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.tabuleiro = TabuleiroDeMarcas()
        self.addCleanup(descartar, self.tabuleiro)
        self.tabuleiro.resize(400, 400)
        self.tabuleiro.show()
        self.app.processEvents()
        self.tabuleiro.mostrar(INICIAL)
        self.emitidas: list[mc.MarcasDoDiagrama] = []
        self.tabuleiro.marcas_mudaram.connect(self.emitidas.append)
        self.posicoes: list[str] = []
        self.tabuleiro.posicao_mudou.connect(self.posicoes.append)

    def pixel(self, x: float, y: float) -> QPoint:
        """O pixel do ponto `(x, y)` em unidades de casa, na tela."""
        geo = self.tabuleiro.geometria()
        return QPoint(round(geo.origin_x + x * geo.cell), round(geo.origin_y + y * geo.cell))

    def centro(self, indice: int) -> QPoint:
        return self.pixel(indice % 8 + 0.5, indice // 8 + 0.5)

    @staticmethod
    def _evento(tipo: QEvent.Type, ponto: QPoint, botao: Qt.MouseButton) -> QMouseEvent:
        return QMouseEvent(tipo, QPointF(ponto), botao, botao, Qt.KeyboardModifier.NoModifier)

    def clicar(self, ponto: QPoint, botao: Qt.MouseButton = Qt.MouseButton.LeftButton) -> None:
        self.tabuleiro.mousePressEvent(self._evento(QEvent.Type.MouseButtonPress, ponto, botao))
        self.tabuleiro.mouseReleaseEvent(self._evento(QEvent.Type.MouseButtonRelease, ponto, botao))

    def arrastar(self, de: QPoint, para: QPoint) -> None:
        botao = Qt.MouseButton.LeftButton
        self.tabuleiro.mousePressEvent(self._evento(QEvent.Type.MouseButtonPress, de, botao))
        self.tabuleiro.mouseMoveEvent(self._evento(QEvent.Type.MouseMove, para, botao))
        self.tabuleiro.mouseReleaseEvent(self._evento(QEvent.Type.MouseButtonRelease, para, botao))

    # --------------------------------------------------------------------- marca de casa

    def test_clique_com_ferramenta_poe_e_tira_a_marca_e_emite(self) -> None:
        self.tabuleiro.definir_ferramenta(mc.ESTRELA_PRETA)
        self.clicar(self.centro(E4))
        self.assertEqual(self.tabuleiro.marcas().casas, {"e4": mc.ESTRELA_PRETA})
        self.clicar(self.centro(E4))
        self.assertTrue(self.tabuleiro.marcas().vazia)
        self.assertEqual(len(self.emitidas), 2)

    def test_marcar_esvazia_a_casa_e_tirar_a_marca_nao_devolve_a_peca(self) -> None:
        self.tabuleiro.definir_ferramenta(mc.BOLINHA_BRANCA)
        self.clicar(self.centro(E2))
        self.assertEqual(self.tabuleiro.posicao(), "rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR")
        self.assertEqual(self.posicoes, [self.tabuleiro.posicao()], "a FEN da janela precisa saber")

        self.clicar(self.centro(E2))
        self.assertEqual(self.tabuleiro.posicao(), "rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR")

    def test_com_a_opcao_desligada_a_marca_fica_sobre_a_peca(self) -> None:
        self.tabuleiro.definir_esvaziar(False)
        self.tabuleiro.definir_ferramenta(mc.X)
        self.clicar(self.centro(E2))
        self.assertEqual(self.tabuleiro.marcas().casas, {"e2": mc.X})
        self.assertEqual(self.tabuleiro.posicao(), INICIAL)

    def test_botao_direito_com_ferramenta_tira_a_marca_e_nunca_a_peca(self) -> None:
        self.tabuleiro.definir_esvaziar(False)
        self.tabuleiro.definir_ferramenta(mc.X)
        self.clicar(self.centro(E2))
        self.clicar(self.centro(E2), Qt.MouseButton.RightButton)
        self.assertTrue(self.tabuleiro.marcas().vazia)

        self.clicar(self.centro(E2), Qt.MouseButton.RightButton)
        self.assertEqual(self.tabuleiro.posicao(), INICIAL, "sem marca para tirar, a peça continua")
        self.assertEqual(self.posicoes, [])

    def test_a_posicao_nunca_carrega_a_marca(self) -> None:
        self.tabuleiro.mostrar("8/8/8/8/8/8/8/8")
        self.tabuleiro.definir_ferramenta(mc.ESTRELA_BRANCA)
        self.clicar(self.centro(E4))
        self.assertEqual(self.tabuleiro.posicao(), "8/8/8/8/8/8/8/8")

    def test_clique_fora_do_tabuleiro_nao_faz_nada(self) -> None:
        self.tabuleiro.resize(600, 300)
        self.app.processEvents()
        self.tabuleiro.definir_ferramenta(mc.X)
        self.clicar(QPoint(2, 2))
        self.assertTrue(self.tabuleiro.marcas().vazia)

    def test_definir_marcas_nao_emite(self) -> None:
        self.tabuleiro.definir_marcas(mc.MarcasDoDiagrama().alternar_casa(mc.X, "a1"))
        self.assertEqual(self.emitidas, [], "abrir uma imagem não é anotar")

    # ---------------------------------------------------------------------------- traço

    def test_arrasto_vira_traco_na_grade_de_meia_casa(self) -> None:
        self.tabuleiro.definir_ferramenta(mc.SETA)
        self.arrastar(self.pixel(7.45, 4.55), self.pixel(1.55, 4.45))
        self.assertEqual(self.tabuleiro.marcas().tracos, (mc.Traco(mc.SETA, (7.5, 4.5), (1.5, 4.5)),))
        self.assertEqual(self.tabuleiro.posicao(), INICIAL, "traço não mexe em peça")

    def test_clique_com_traco_nao_cria_traco_de_comprimento_zero(self) -> None:
        self.tabuleiro.definir_ferramenta(mc.RETA)
        self.clicar(self.centro(E4))
        self.assertTrue(self.tabuleiro.marcas().vazia)
        self.assertEqual(self.emitidas, [])

    def test_botao_direito_tira_o_traco(self) -> None:
        self.tabuleiro.definir_ferramenta(mc.RETA)
        self.arrastar(self.pixel(0.5, 4.5), self.pixel(7.5, 4.5))
        self.clicar(self.pixel(4.2, 4.6), Qt.MouseButton.RightButton)
        self.assertTrue(self.tabuleiro.marcas().vazia)

    def test_tabuleiro_virado_grava_na_orientacao_do_diagrama(self) -> None:
        self.tabuleiro.mostrar(INICIAL, virado=True)
        self.tabuleiro.definir_esvaziar(False)
        self.tabuleiro.definir_ferramenta(mc.RETA)
        self.arrastar(self.pixel(0.5, 0.5), self.pixel(1.5, 0.5))
        self.assertEqual(self.tabuleiro.marcas().tracos, (mc.Traco(mc.RETA, (7.5, 7.5), (6.5, 7.5)),))

    def test_as_marcas_aparecem_na_tela(self) -> None:
        self.tabuleiro.mostrar("8/8/8/8/8/8/8/8")
        antes = self.tabuleiro.grab().toImage()
        self.tabuleiro.definir_marcas(
            mc.MarcasDoDiagrama().alternar_casa(mc.ESTRELA_PRETA, "e4").com_traco(mc.SETA, (0.5, 0.5), (7.5, 0.5))
        )
        depois = self.tabuleiro.grab().toImage()
        self.assertNotEqual(antes.convertToFormat(QImage.Format.Format_RGB32), depois.convertToFormat(QImage.Format.Format_RGB32))

    # ------------------------------------------------------------------------- sem ferramenta

    def test_sem_ferramenta_e_o_tabuleiro_de_sempre(self) -> None:
        self.arrastar(self.centro(E2), self.centro(E4))
        self.assertEqual(self.tabuleiro.posicao(), "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR")
        self.clicar(self.centro(E4), Qt.MouseButton.RightButton)
        self.assertEqual(self.tabuleiro.posicao(), "rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR")
        self.assertEqual(self.emitidas, [])

    def test_largar_a_ferramenta_devolve_a_correcao_de_pecas(self) -> None:
        self.tabuleiro.definir_ferramenta(mc.X)
        self.tabuleiro.definir_ferramenta(None)
        self.clicar(self.centro(H1), Qt.MouseButton.RightButton)
        self.assertEqual(self.tabuleiro.posicao(), "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN1")

    # --------------------------------------------------------------------------- teclado

    def _tecla(self, chave: Qt.Key) -> None:
        self.tabuleiro.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, chave, Qt.KeyboardModifier.NoModifier))

    def test_espaco_poe_e_delete_tira_na_casa_selecionada(self) -> None:
        self.tabuleiro.mostrar("8/8/8/8/8/8/8/8")
        self.tabuleiro.selecionar_casa(A8)
        self.tabuleiro.definir_ferramenta(mc.CRUZ)
        self._tecla(Qt.Key.Key_Space)
        self.assertEqual(self.tabuleiro.marcas().casas, {"a8": mc.CRUZ})
        self._tecla(Qt.Key.Key_Right)
        self.assertEqual(self.tabuleiro.selecionada(), A8 + 1, "as setas continuam andando")
        self.tabuleiro.selecionar_casa(A8)
        self._tecla(Qt.Key.Key_Delete)
        self.assertTrue(self.tabuleiro.marcas().vazia)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PaletaTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()
        self.paleta = PaletaDeMarcas()
        self.addCleanup(descartar, self.paleta)
        self.emitidas: list[object] = []
        self.paleta.ferramenta.connect(self.emitidas.append)

    def test_a_paleta_oferece_todo_o_vocabulario_uma_vez(self) -> None:
        oferecidos = [tipo for par in FILEIRAS for tipo in par]
        self.assertEqual(sorted(oferecidos), sorted((*mc.TIPOS_DE_CASA, *mc.TIPOS_DE_TRACO)))

    def test_clicar_acende_um_e_clicar_no_aceso_larga(self) -> None:
        self.paleta._botoes[mc.X].click()
        self.assertEqual(self.paleta.escolhido, mc.X)
        self.paleta._botoes[mc.SETA].click()
        self.assertEqual([tipo for tipo, botao in self.paleta._botoes.items() if botao.isChecked()], [mc.SETA])
        self.paleta._botoes[mc.SETA].click()
        self.assertIsNone(self.paleta.escolhido)
        self.assertEqual(self.emitidas, [mc.X, mc.SETA, None])

    def test_cada_botao_tem_icone_e_nome_acessivel(self) -> None:
        for tipo, botao in self.paleta._botoes.items():
            self.assertFalse(botao.icon().isNull(), tipo)
            self.assertIn(mc.NOMES[tipo], botao.accessibleName())

    def test_apagar_a_paleta_larga_a_ferramenta_e_diz_por_que(self) -> None:
        self.paleta.escolher(mc.X)
        self.paleta.habilitar(False, motivo="arquivo estragado")
        self.assertIsNone(self.paleta.escolhido)
        self.assertFalse(self.paleta._botoes[mc.X].isEnabled())
        self.assertIn("arquivo estragado", self.paleta._botoes[mc.X].toolTip())
        self.paleta.habilitar(True)
        self.assertNotIn("arquivo estragado", self.paleta._botoes[mc.X].toolTip())


if __name__ == "__main__":
    unittest.main()
