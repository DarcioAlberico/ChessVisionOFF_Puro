"""A janela cabe no portátil: nenhum texto decide a largura, e a altura rola (OCR_UI ciclo 2, C18).

Medido com o livro aberto e as áreas visitadas, o mínimo da janela era **1538×659** lógicos: a
barra de anotação sob o visor (combo e três botões numa `QHBoxLayout`, 810 px na pele Foco), a
frase do rodapé num `QLabel` comum (1.246 px com uma frase de importação) e o painel mais alto dos
modos do livro (o Resultado, 520 px). A área útil de um portátil 1920×1080 a 150 % é 1280×641.
Os testes medem cada motor por si, com a sabotagem de cada um ao lado; o portão da janela inteira
é `caissa.ui.audit.minimo`, na suíte.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qt_app import MOTIVO, TEM_PYQT, aplicacao

if TEM_PYQT:
    from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

    from chess_diagram_ocr.qt import rodape, tema
    from chess_diagram_ocr.qt.campo import PainelDeCampo
    from chess_diagram_ocr.qt.painel_principal import PainelPrincipal

FRASE = ("A importação de 1937 Kemeri.pdf terminou depois de o livro mudar e foi descartada; as "
         "páginas lidas continuam no cache e podem ser exportadas quando o livro voltar. ") * 3


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RodapeNaoDecideALarguraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.rodape = rodape.RodapeDaJanela()
        self.addCleanup(self.rodape.deleteLater)

    def test_uma_frase_longa_nao_sobe_o_minimo(self) -> None:
        antes = self.rodape.minimumSizeHint().width()
        self.rodape.mostrar(FRASE)
        self.assertEqual(self.rodape.minimumSizeHint().width(), antes)
        # o rodapé compõe a frase (sem o espaço final); inteira, e não a desenhada
        self.assertEqual(self.rodape.mensagem(), FRASE.strip(), "a frase inteira continua legível")
        self.assertEqual(self.rodape._lbl_mensagem.toolTip(), FRASE.strip())

    def test_a_sabotagem_um_rotulo_comum_subiria(self) -> None:
        comum = QLabel(FRASE)
        self.assertGreater(comum.minimumSizeHint().width(), 1000)

    def test_dispositivos_e_ocupacao_tambem_elidem(self) -> None:
        self.assertEqual(self.rodape._lbl_dispositivos.minimumSizeHint().width(), 0)
        self.assertEqual(self.rodape._lbl_ocupacao.minimumSizeHint().width(), 0)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class BarraDoCampoFluiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.painel = PainelDeCampo(
            pdf_path=lambda: None, page_index=lambda: 0, caixas=lambda: None,
            caixa_selecionada=lambda: None, colocacoes=dict,
            caminho_do_conjunto=Path(pasta.name) / "field_set.jsonl")
        self.addCleanup(self.painel.deleteLater)

    def test_o_minimo_e_o_do_maior_controle_e_nao_a_soma(self) -> None:
        controles = (self.painel.regime, self.painel.btn_anotar, self.painel.btn_sem_diagrama,
                     self.painel.btn_tirar)
        maior = max(c.minimumSizeHint().width() for c in controles)
        soma = sum(c.minimumSizeHint().width() for c in controles)
        largura = self.painel.minimumSizeHint().width()
        self.assertLessEqual(largura, maior + 40)
        self.assertLess(largura, soma, "a barra fluida não soma os controles numa linha")

    def test_a_sabotagem_uma_linha_so_soma(self) -> None:
        linha = QWidget()
        caixa = QHBoxLayout(linha)
        for texto in ("Anotar página", "Sem diagrama", "Tirar o selecionado"):
            caixa.addWidget(QPushButton(texto))
        self.assertGreater(linha.minimumSizeHint().width(), self.painel.minimumSizeHint().width())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ModosRolamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.principal = PainelPrincipal()
        self.addCleanup(self.principal.deleteLater)
        self.alto = QWidget()
        self.alto.setMinimumSize(300, 900)
        self.baixo = QWidget()
        self.principal.adicionar_modo("Resultado", self.alto)
        self.principal.adicionar_modo("Estudo", self.baixo)

    def test_a_altura_do_modo_mais_alto_nao_sobe_o_minimo(self) -> None:
        self.assertLess(self.principal.minimumSizeHint().height(), 300)

    def test_a_api_devolve_o_painel_e_nao_a_rolagem(self) -> None:
        self.assertIs(self.principal.widget_do_modo("Resultado"), self.alto)
        self.assertIs(self.principal.painel_atual(), self.alto)
        self.assertEqual(self.principal.modo_de(self.baixo), "Estudo")
        self.assertIsNone(self.principal.modo_de(QWidget()))
        self.principal.definir_modo("Estudo")
        self.assertIs(self.principal.painel_atual(), self.baixo)

    def test_a_rolagem_nao_entra_na_ordem_do_tab(self) -> None:
        from PyQt6.QtCore import Qt

        rolagem = self.principal.pilha.widget(0)
        self.assertEqual(rolagem.focusPolicy(), Qt.FocusPolicy.NoFocus)


if __name__ == "__main__":
    unittest.main()
