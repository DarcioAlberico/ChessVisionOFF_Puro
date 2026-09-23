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
NOME_LONGO = ("Gaprindashvili, Paata - Imagination in Chess. How To Think Creatively And Avoid "
              "Foolish Mistakes (Bastford, 2005) 2p 145p_OCR_Aprimorar_Aprimorar.pdf · p. 1 de 289 · "
              "nenhum diagrama nesta página")


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

    def _larguras(self, largura: int) -> tuple[int, int]:
        self.rodape.definir_documento(NOME_LONGO)
        self.rodape.resize(largura, 30)
        self.rodape.show()
        for _ in range(4):
            self.app.processEvents()
        return self.rodape._lbl_mensagem.width(), self.rodape._lbl_documento.width()

    def test_a_mensagem_tem_largura_garantida_ao_lado_de_um_nome_longo(self) -> None:
        """Crítico da fase 5: com o nome de 149 caracteres a mensagem ficava com 0 px -- o Qt
        encolhe primeiro o item esticável, e o mínimo dela era zero."""
        self.rodape.mostrar(FRASE)
        mensagem, documento = self._larguras(1248)
        self.assertGreaterEqual(mensagem, rodape.LARGURA_DA_MENSAGEM)
        self.assertGreater(documento, 0, "o nome do livro continua à vista, elidido")

    def test_sem_mensagem_o_nome_do_livro_fica_com_o_espaco(self) -> None:
        self.rodape.mostrar(FRASE)
        self.rodape._expirar()
        self.assertEqual(self.rodape._lbl_mensagem.minimumWidth(), 0)

    def test_a_sabotagem_sem_o_piso_a_mensagem_some(self) -> None:
        original = rodape.LARGURA_DA_MENSAGEM
        rodape.LARGURA_DA_MENSAGEM = 0
        self.addCleanup(setattr, rodape, "LARGURA_DA_MENSAGEM", original)
        self.rodape.mostrar(FRASE)
        mensagem, _documento = self._larguras(1248)
        self.assertLess(mensagem, 50)

    def _linha_cheia(self) -> QPushButton:
        """A mensagem no piso, o nome longo e uma importação em curso, com a barra na linha."""
        from chess_diagram_ocr.ui.busy import BusyOperation

        self.rodape.mostrar(FRASE)
        self.rodape.aplicar_ocupacao([BusyOperation(
            name="Importando o livro", loses_work=False, cancellable=True,
            detail="p. 12 de 289", feito=12, total=289)])
        self._larguras(1248)
        return self.rodape._btn_mensagens

    def test_o_botao_de_mensagens_fica_com_o_seu_minimo_com_a_linha_cheia(self) -> None:
        """O portão da janela estendido (fase 5): com a mensagem no piso e a importação em curso,
        o piso de um pixel deixava o botão com 27 dos 82 px."""
        botao = self._linha_cheia()
        self.assertGreaterEqual(botao.width(), botao.minimumSizeHint().width())
        self.assertLess(self.rodape.minimumSizeHint().width(), 1248,
                        "o rodapé continua sem decidir a largura mínima da janela")

    def test_a_sabotagem_o_piso_de_um_pixel_espreme_o_botao(self) -> None:
        self.rodape._btn_mensagens.setMinimumWidth(1)
        botao = self._linha_cheia()
        self.assertLess(botao.width(), 0.9 * botao.minimumSizeHint().width())


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

    def test_a_barra_horizontal_aparece_quando_o_modo_nao_cabe(self) -> None:
        """Crítico da fase 5: desligada, o que passava da largura ficava sem caminho -- o
        Resultado pede 550 px e a rolagem mostra 526 com a janela no mínimo."""
        from PyQt6.QtCore import Qt

        largo = QWidget()
        largo.setMinimumSize(600, 100)
        self.principal.adicionar_modo("Texto", largo)
        self.principal.definir_modo("Texto")
        rolagem = self.principal.pilha.currentWidget()
        self.assertEqual(rolagem.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.principal.resize(400, 300)
        self.principal.show()
        for _ in range(4):
            self.app.processEvents()
        self.assertTrue(rolagem.horizontalScrollBar().isVisible())


if __name__ == "__main__":
    unittest.main()
