"""A tabela do segundo frontend, montada das mesmas `Coluna` (S-153/S-501).

**O que estes testes cobrem, e o que não.** O que uma coluna decide -- alinhamento, largura
mínima, se a tabela precisa rolar -- é puro e já é afirmado em `tests/test_ui_tabela.py`. Repetir
aquilo aqui mediria o mesmo código duas vezes.

O que só existe deste lado são as três coisas em que o Qt difere do Tk e que quebram calado:

1. **A última coluna estica sozinha** no `QHeaderView`, e a que devia esticar é a que
   `Coluna.elastica` declara -- que nem sempre é a última.
2. **A largura mínima é única para a tabela inteira** no Qt, e as colunas desta tabela não têm o
   mesmo mínimo. Sem um limite por seção, arrastar o separador de "Motivo" até 5 px é possível.
3. **O alinhamento de célula não vem da coluna**: é por item, e esquecê-lo devolve a coluna
   numérica à esquerda -- que é metade do defeito que a S-153 mediu.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import tabela as tabela_pura
from chess_diagram_ocr.ui.tabela import Coluna

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFontMetrics
    from PyQt6.QtWidgets import QHeaderView

    from chess_diagram_ocr.qt import tabela as qt_tabela

COLUNAS = (
    Coluna("arquivo", "Arquivo", 180),
    Coluna("fen", "FEN", 300, elastica=True),
    Coluna("prioridade", "Prioridade", 90, numerica=True),
)

PISO_DA_JANELA = 940
"""A largura em que a S-153 fotografou o defeito: 6 das 8 colunas do Dataset inalcançáveis."""


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e este módulo não a reescreve."""

    def test_a_coluna_e_a_do_outro_frontend(self) -> None:
        self.assertIs(qt_tabela.Coluna, tabela_pura.Coluna)
        self.assertIs(qt_tabela.largura_total, tabela_pura.largura_total)
        self.assertIs(qt_tabela.precisa_de_barra_horizontal, tabela_pura.precisa_de_barra_horizontal)

    def test_o_alinhamento_deriva_da_ancora_e_nao_de_coluna_numerica(self) -> None:
        """Perguntar `coluna.numerica` direto seria a mesma resposta por um caminho paralelo --
        e o caminho paralelo é o que diverge quando alguém acrescenta um terceiro tipo."""
        for coluna in COLUNAS:
            with self.subTest(coluna=coluna.chave):
                esperado = (
                    Qt.AlignmentFlag.AlignRight
                    if tabela_pura.ancora(coluna) == tabela_pura.ANCORA_NUMERO
                    else Qt.AlignmentFlag.AlignLeft
                )
                self.assertTrue(qt_tabela.alinhamento(coluna) & esperado)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MontagemTests(unittest.TestCase):
    """O `QTreeWidget` configurado pelas colunas."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.tabela = qt_tabela.TabelaQt(COLUNAS)
        self.addCleanup(self.tabela.deleteLater)
        self.tabela.resize(600, 300)
        self.tabela.show()
        self.app.processEvents()

    def cabecalho(self) -> QHeaderView:
        cabecalho = self.tabela.header()
        assert cabecalho is not None
        return cabecalho

    def test_as_colunas_e_os_titulos_saem_da_declaracao(self) -> None:
        self.assertEqual(self.tabela.columnCount(), len(COLUNAS))
        titulos = self.tabela.headerItem()
        assert titulos is not None
        self.assertEqual(
            [titulos.text(i) for i in range(len(COLUNAS))], [c.titulo for c in COLUNAS]
        )

    def test_quem_estica_e_a_elastica_e_nao_a_ultima(self) -> None:
        """**O padrão do Qt é esticar a última**, e a elástica desta tabela é a do meio.

        Com o padrão, "Prioridade" comeria a folga que era da FEN, e a barra horizontal deixaria
        de aparecer quando devia -- que é a metade do defeito da S-153 que o Qt *tem* igual.
        """
        cabecalho = self.cabecalho()
        self.assertFalse(cabecalho.stretchLastSection())
        for indice, coluna in enumerate(COLUNAS):
            with self.subTest(coluna=coluna.chave):
                esperado = (
                    QHeaderView.ResizeMode.Stretch
                    if coluna.elastica
                    else QHeaderView.ResizeMode.Interactive
                )
                self.assertEqual(cabecalho.sectionResizeMode(indice), esperado)

    def test_a_coluna_nao_encolhe_abaixo_do_minimo_dela(self) -> None:
        """O `QHeaderView` só tem um mínimo para a tabela inteira, e as colunas não o têm igual.

        Sem o limite por seção, arrastar o separador de "Motivo" até 5 px é possível -- e o texto
        que diz o que conferir volta a ser o que não se pode ler, que é o defeito da S-153
        chegando pela mão em vez de pelo layout.

        **O piso é o maior entre o declarado e o que o próprio título pede** (F9-C4). Enquanto a
        folha de estilo não mexia na fonte do cabeçalho os dois eram o mesmo número, e a
        expectativa podia ser só `largura_minima`. Com o cabeçalho em 12 px peso 700 eles
        divergem, e o piso que interessa é o que impede o título de ser cortado -- ver
        `TabelaQt.alargar_o_que_corta_o_titulo`, escrita porque "Conf. mín" aparecia como
        "onf. min" em 6 das 36 capturas do ciclo 4.
        """
        cabecalho = self.cabecalho()
        for indice, coluna in enumerate(COLUNAS):
            if coluna.elastica:
                continue  # a elástica é governada pelo modo `Stretch`
            with self.subTest(coluna=coluna.chave):
                pedido_pelo_titulo = (
                    QFontMetrics(cabecalho.font()).horizontalAdvance(coluna.titulo)
                    + qt_tabela.RECHEIO_DO_TITULO
                )
                cabecalho.resizeSection(indice, 5)
                self.assertEqual(
                    cabecalho.sectionSize(indice),
                    max(tabela_pura.largura_minima(coluna), pedido_pelo_titulo),
                )

    def test_a_fonte_maior_do_cabecalho_alarga_a_coluna_em_vez_de_cortar_o_titulo(self) -> None:
        """**Medir uma vez no construtor mede a fonte errada** (F9-C4).

        `_largura_da_secao` usa `header().font()`, e no construtor essa é a fonte de fábrica: a
        folha de estilo do produto chega depois e dá ao cabeçalho 12 px em peso 700. O resultado
        estava em **6 das 36 capturas** do ciclo 4 -- a aba Revisão nas três larguras e nas duas
        peles --, onde `"Conf. mín"` (80 px declarados, 100 pedidos) aparece como **"onf. min"**:
        a coluna é numérica, alinha à direita, e o que a sobra come é a **primeira** letra.
        """
        cabecalho = self.cabecalho()
        estreita = 2  # "Prioridade", 90 px declarados e alinhada à direita, como a "Conf. mín"
        antes = cabecalho.sectionSize(estreita)

        fonte = cabecalho.font()
        fonte.setPointSize(fonte.pointSize() + 12)
        fonte.setBold(True)
        cabecalho.setFont(fonte)
        self.app.processEvents()

        precisa = QFontMetrics(cabecalho.font()).horizontalAdvance(COLUNAS[estreita].titulo)
        precisa += qt_tabela.RECHEIO_DO_TITULO
        self.assertGreater(precisa, antes, "a fonte não cresceu o bastante para o caso valer")
        self.assertGreaterEqual(
            cabecalho.sectionSize(estreita),
            precisa,
            "o título do cabeçalho continua sendo cortado depois de a fonte crescer",
        )

    def test_alargar_pela_fonte_nao_desfaz_o_arrasto_de_quem_alargou_mais(self) -> None:
        """Quem arrastou uma coluna para 400 px quer 400 px. A remedida **só alarga**."""
        cabecalho = self.cabecalho()
        cabecalho.resizeSection(0, 400)
        self.tabela.alargar_o_que_corta_o_titulo()
        self.assertEqual(cabecalho.sectionSize(0), 400)

    def test_o_piso_da_secao_sobe_junto_com_a_fonte(self) -> None:
        """Senão a mesma alça devolveria o corte pela mão, que é o defeito da S-153 de novo."""
        cabecalho = self.cabecalho()
        fonte = cabecalho.font()
        fonte.setPointSize(fonte.pointSize() + 12)
        fonte.setBold(True)
        cabecalho.setFont(fonte)
        self.app.processEvents()

        precisa = QFontMetrics(cabecalho.font()).horizontalAdvance(COLUNAS[2].titulo)
        precisa += qt_tabela.RECHEIO_DO_TITULO
        cabecalho.resizeSection(2, 5)
        self.assertGreaterEqual(cabecalho.sectionSize(2), precisa)

    def test_o_limite_nao_impede_alargar(self) -> None:
        cabecalho = self.cabecalho()
        cabecalho.resizeSection(0, 400)
        self.assertEqual(cabecalho.sectionSize(0), 400)

    def test_a_celula_numerica_encosta_a_direita(self) -> None:
        """`1623.8` e `40` à esquerda só se comparam lendo os dígitos um a um."""
        self.tabela.preencher([("a.png", "8/8/8/8/8/8/8/8", "1623.8")])
        item = self.tabela.topLevelItem(0)
        assert item is not None
        self.assertTrue(item.textAlignment(2) & Qt.AlignmentFlag.AlignRight)
        self.assertTrue(item.textAlignment(0) & Qt.AlignmentFlag.AlignLeft)

    def test_preencher_troca_o_conteudo_inteiro(self) -> None:
        self.tabela.preencher([("a.png", "8/8", "1"), ("b.png", "8/8", "2")])
        self.assertEqual(self.tabela.topLevelItemCount(), 2)
        self.tabela.preencher([("c.png", "8/8", "3")])
        self.assertEqual(self.tabela.topLevelItemCount(), 1)

    def test_linha_com_menos_celulas_levanta(self) -> None:
        """Uma linha curta aceita apareceria com as últimas colunas em branco, e quem olhasse
        concluiria que o dado está faltando quando o que houve foi a chamada errada."""
        with self.assertRaises(ValueError):
            self.tabela.preencher([("a.png", "8/8")])

    def test_a_tabela_de_oito_colunas_precisa_rolar_no_piso_da_janela(self) -> None:
        """O critério de aceite da S-153, medido onde ele foi fotografado.

        Oito colunas de dados não cabem em 940 px, e a resposta certa é rolar -- e não encolher
        cada uma até 20 px, que é o que o Tk fazia e o que fazia a barra nunca aparecer.
        """
        muitas = [Coluna(f"c{i}", f"Coluna {i}", 150) for i in range(8)]
        self.assertTrue(tabela_pura.precisa_de_barra_horizontal(muitas, PISO_DA_JANELA))

        tabela = qt_tabela.TabelaQt(muitas)
        self.addCleanup(tabela.deleteLater)
        tabela.resize(PISO_DA_JANELA, 300)
        tabela.show()
        self.app.processEvents()
        self.assertTrue(tabela.precisa_rolar())

    def test_montar_devolve_a_tabela_sem_empacotar(self) -> None:
        """Quem posiciona é o leiaute de quem chama: um `addWidget` escondido aqui tiraria do
        painel a decisão de onde a tabela fica."""
        from PyQt6.QtWidgets import QWidget

        pai = QWidget()
        self.addCleanup(pai.deleteLater)
        tabela = qt_tabela.montar(pai, COLUNAS)
        self.assertIsInstance(tabela, qt_tabela.TabelaQt)
        self.assertIs(tabela.parent(), pai)
        self.assertIsNone(pai.layout(), "montar não pode escolher o leiaute do painel")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
