"""A barra que quebra em vez de cortar, no Qt (S-151/S-501).

**O que estes testes cobrem, e o que não.** `arranjo` -- que é *a* decisão -- é pura e já é
afirmada nos três regimes em `tests/test_ui_barra.py`, e este módulo a chama em vez de reescrevê-la.
Repetir aquilo aqui mediria o mesmo código duas vezes.

O que só existe deste lado é o `QLayout` que executa o arranjo, e nele há duas coisas que o Tk
não tinha e que quebram em silêncio:

1. **`heightForWidth`**, sem o qual o Qt pergunta a altura antes de saber a largura e desenha a
   segunda linha por cima do painel de baixo;
2. **`minimumSize`**, que é o que faz a janela poder ser estreitada -- responder a soma das
   larguras devolveria a barra ao regime em que a largura mínima cresce com o número de botões.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import barra as barra_tk

if TEM_PYQT:
    from PyQt6.QtCore import QRect
    from PyQt6.QtWidgets import QPushButton, QWidget

    from chess_diagram_ocr.qt import barra


LARGURA_DO_DEFEITO = 1100
"""A largura em que a S-151 mediu o defeito original: quatro controles sumiam sem aviso."""


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DecisaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e este módulo não a reescreve."""

    def test_o_arranjo_e_o_do_outro_frontend(self) -> None:
        """Duas implementações da mesma quebra divergiriam no primeiro botão acrescentado."""
        self.assertIs(barra.arranjo, barra_tk.arranjo)
        self.assertIs(barra.linhas_necessarias, barra_tk.linhas_necessarias)
        self.assertEqual(barra.ESPACO_ENTRE_ITENS, barra_tk.ESPACO_ENTRE_ITENS)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LeiauteTests(unittest.TestCase):
    """O `QLayout` que executa o arranjo."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.barra = barra.BarraFluida()
        self.addCleanup(self.barra.deleteLater)
        self.botoes = [
            self.barra.adicionar(QPushButton(rotulo, self.barra))
            for rotulo in ("Abrir PDF", "Página anterior", "Próxima página", "Ajustar à página")
        ]
        self.barra.show()
        self.app.processEvents()

    def larguras(self) -> list[int]:
        return [max(1, b.sizeHint().width()) for b in self.botoes]

    def test_nenhum_item_e_descartado_em_largura_nenhuma(self) -> None:
        """**É a propriedade que o defeito original violava**, e ela vale em toda largura.

        No Tk o que passou da borda simplesmente não era desenhado -- sem aviso, sem reticências,
        sem `>>`. Aqui a pergunta é feita ao arranjo, e nenhuma largura pode perder um índice.
        """
        for largura in (60, 200, LARGURA_DO_DEFEITO, 4000):
            with self.subTest(largura=largura):
                postos = [i for linha in self.barra._leiaute._linhas(largura) for i in linha]
                self.assertEqual(sorted(postos), list(range(len(self.botoes))))

    def test_a_barra_estreita_quebra_e_a_larga_nao(self) -> None:
        self.assertEqual(self.barra.linhas_em(4000), 1)
        self.assertGreater(self.barra.linhas_em(120), 1)

    def test_a_altura_acompanha_a_largura(self) -> None:
        """Sem `heightForWidth` a segunda linha é desenhada por cima do painel de baixo."""
        leiaute = self.barra._leiaute
        self.assertTrue(leiaute.hasHeightForWidth())
        uma = leiaute.heightForWidth(4000)
        varias = leiaute.heightForWidth(120)
        self.assertGreater(varias, uma, "a barra quebrada não pediu altura a mais")

    def test_a_largura_minima_e_a_do_item_mais_largo_e_nao_a_soma(self) -> None:
        """**É o que faz a janela poder ser estreitada.**

        Responder a soma devolveria a barra ao regime em que a largura mínima da janela cresce
        com o número de botões -- que é o defeito do `QHBoxLayout`, e a razão de este leiaute
        existir. A S-151 mediu cinco barras empilhadas gastando 20% da altura da janela.
        """
        minima = self.barra._leiaute.minimumSize().width()
        self.assertEqual(minima, max(self.larguras()))
        self.assertLess(minima, sum(self.larguras()))

    def test_o_arranjo_desenhado_nao_sobrepoe_dois_itens_da_mesma_linha(self) -> None:
        """A geometria de verdade, e não só a conta: os itens de uma linha não se cobrem."""
        self.barra._leiaute.setGeometry(QRect(0, 0, 240, 200))
        caixas = [b.geometry() for b in self.botoes]
        for i, uma in enumerate(caixas):
            for outra in caixas[i + 1 :]:
                with self.subTest(uma=uma, outra=outra):
                    self.assertFalse(uma.intersects(outra), "dois controles ocupam o mesmo pixel")

    def test_a_ordem_e_preservada(self) -> None:
        """Reordenar entre larguras faria o botão mudar de lugar ao arrastar o divisor.

        A memória motora de quem usa o programa todo dia vale mais que a linha economizada -- é
        o que `arranjo` já documenta, e aqui se afirma que o desenho a respeita.
        """
        self.barra._leiaute.setGeometry(QRect(0, 0, 240, 200))
        cantos = [(b.geometry().y(), b.geometry().x()) for b in self.botoes]
        self.assertEqual(cantos, sorted(cantos), "os controles não saíram na ordem em que entraram")

    def test_adicionar_devolve_o_widget(self) -> None:
        """Para o ponto de chamada caber numa linha, como em `ui/barra.adicionar`."""
        botao = QPushButton("Ler", self.barra)
        self.assertIs(self.barra.adicionar(botao), botao)

    def test_esvaziar_deixa_a_barra_pronta_para_remontar(self) -> None:
        """A fita da S-228 troca de modo em execução, e remontar sem esvaziar duplicaria tudo."""
        self.barra.esvaziar()
        self.assertEqual(self.barra._leiaute.count(), 0)
        self.barra.adicionar(QPushButton("Depois", self.barra))
        self.assertEqual(self.barra._leiaute.count(), 1)

    def test_a_barra_vazia_nao_levanta(self) -> None:
        vazia = barra.BarraFluida()
        self.addCleanup(vazia.deleteLater)
        self.assertEqual(vazia.linhas_em(500), 0)
        self.assertEqual(vazia._leiaute.heightForWidth(500), 0)
        self.assertIsNone(vazia._leiaute.itemAt(0))
        self.assertIsNone(vazia._leiaute.takeAt(0))

    def test_a_barra_nao_disputa_altura_com_o_documento(self) -> None:
        """A S-151 inteira é sobre devolver pixel ao painel que mostra a página."""
        from PyQt6.QtWidgets import QSizePolicy

        self.assertEqual(self.barra.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Minimum)
        # `Qt.Orientation` é uma flag do Qt e não um inteiro: o teste é que ela não contém a
        # vertical, e declará-la faria a barra disputar altura com o painel que ela encima.
        from PyQt6.QtCore import Qt

        expande = self.barra._leiaute.expandingDirections()
        self.assertFalse(expande & Qt.Orientation.Vertical)
        self.assertFalse(expande & Qt.Orientation.Horizontal)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DentroDeUmaJanelaTests(unittest.TestCase):
    """A barra montada num pai, que é como um painel a usa."""

    def setUp(self) -> None:
        self.app = aplicacao()

    def test_a_barra_cabe_na_largura_em_que_o_defeito_aparecia(self) -> None:
        """O critério de aceite da S-151, medido em 1100 -- e da S-223, que exige uma linha ali."""
        from PyQt6.QtWidgets import QVBoxLayout

        janela = QWidget()
        self.addCleanup(janela.deleteLater)
        leiaute = QVBoxLayout(janela)
        fluida = barra.BarraFluida(janela)
        leiaute.addWidget(fluida)
        for rotulo in ("Abrir PDF", "Anterior", "Próxima", "Ler página", "Marcar"):
            fluida.adicionar(QPushButton(rotulo, fluida))
        janela.resize(LARGURA_DO_DEFEITO, 400)
        janela.show()
        self.app.processEvents()
        self.assertEqual(fluida.linhas_em(LARGURA_DO_DEFEITO), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
