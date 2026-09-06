"""A paleta de pecas da aba Resultado, no Qt (S-65/S-506).

**O que estes testes cobrem, e o que nao.** O que o pincel *faz* -- pintar, alternar, apagar -- e
de `ui/board_model.py`, e puro, e ja e afirmado em `tests/test_board_model.py`. O roteamento do
clique no tabuleiro e de `tests/test_qt_tabuleiro_editavel.py`. Repetir qualquer um dos dois aqui
mediria o mesmo codigo duas vezes.

O que so existe deste lado sao as tres coisas que a S-65 comprou e que o corte do Tk (S-506)
levou junto com `ui/board_widget.py`: **o pincel visivel** (qual botao esta aceso), **o clique no
botao aceso que larga o pincel**, e **a imagem no lugar do glifo** -- com a degradacao que ela
exige, porque `assets/piece_images/` nao e obrigatorio.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import board_edit, conjuntos, tokens

if TEM_PYQT:
    from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.paleta_de_pecas import (
        APAGAR,
        PESO_DO_SELECIONADO,
        PaletaDePecas,
    )

PASTA_VAZIA = Path(tempfile.gettempdir()) / "paleta-sem-pecas"


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PaletaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.paleta = PaletaDePecas()
        # Ela registra repintura de tema e recarga de conjunto: `deleteLater` sozinho deixaria as
        # duas na fila do modulo ate o fim da suite. Ver `qt_app.descartar`.
        self.addCleanup(descartar, self.paleta)
        self.escolhidos: list[object] = []
        self.paleta.pincel.connect(self.escolhidos.append)


class EscolhaTests(PaletaTests):
    """O pincel e um modo, e um modo precisa aparecer na tela (S-65)."""

    def test_a_paleta_nasce_sem_pincel(self) -> None:
        self.assertIsNone(self.paleta.escolhido)
        self.assertEqual([], [v for v, b in self.paleta._botoes.items() if b.isChecked()])

    def test_o_clique_acende_so_o_botao_da_peca(self) -> None:
        self.paleta._botoes["Q"].click()
        self.assertEqual("Q", self.paleta.escolhido)
        self.assertEqual(["Q"], [v for v, b in self.paleta._botoes.items() if b.isChecked()])
        self.assertEqual(["Q"], self.escolhidos)

    def test_clicar_em_outra_peca_troca_o_pincel(self) -> None:
        self.paleta._botoes["Q"].click()
        self.paleta._botoes["n"].click()
        self.assertEqual("n", self.paleta.escolhido)
        self.assertEqual(["n"], [v for v, b in self.paleta._botoes.items() if b.isChecked()])

    def test_clicar_no_botao_aceso_larga_o_pincel(self) -> None:
        """O gesto da S-65: sem ele, largar exige achar o "Sem pincel" do outro lado da fila."""
        self.paleta._botoes["Q"].click()
        self.paleta._botoes["Q"].click()
        self.assertIsNone(self.paleta.escolhido)
        self.assertEqual([], [v for v, b in self.paleta._botoes.items() if b.isChecked()])
        self.assertEqual(["Q", None], self.escolhidos)

    def test_o_apagar_e_um_pincel_como_os_outros(self) -> None:
        """`""` e o valor que `BoardModel.brush` ja usa: a paleta nao traduz nada."""
        self.paleta._botoes[APAGAR].click()
        self.assertEqual(APAGAR, self.paleta.escolhido)
        self.assertTrue(self.paleta._botoes[APAGAR].isChecked())

    def test_sem_pincel_larga_e_responde_mesmo_com_a_mao_vazia(self) -> None:
        """Um botao que responde silencio a um clique e o controle mudo da S-165."""
        self.paleta.btn_largar.click()
        self.assertEqual([None], self.escolhidos)
        self.paleta._botoes["k"].click()
        self.paleta.btn_largar.click()
        self.assertIsNone(self.paleta.escolhido)
        self.assertEqual([None, "k", None], self.escolhidos)


class ArranjoTests(PaletaTests):
    """A coluna ao lado do tabuleiro: pares, e nao fileiras de cor."""

    def test_a_peca_e_a_contraria_dela_ficam_lado_a_lado(self) -> None:
        """Trocar a cor de uma leitura errada e metade das correcoes: e o clique ao lado."""
        grade = self.paleta.layout()
        lugar = {
            simbolo: grade.getItemPosition(grade.indexOf(self.paleta._botoes[simbolo]))[:2]
            for simbolo in board_edit.PIECE_SYMBOLS
        }
        for branca, preta in zip(board_edit.PIECE_SYMBOLS[:6], board_edit.PIECE_SYMBOLS[6:], strict=True):
            with self.subTest(par=f"{branca}{preta}"):
                self.assertEqual(lugar[branca][0], lugar[preta][0], "o par nao esta na mesma fileira")
                self.assertLess(lugar[branca][1], lugar[preta][1], "a branca fica na coluna da esquerda")

    def test_os_dois_controles_atravessam_as_duas_colunas(self) -> None:
        """Um controle com a largura do rotulo encostaria na esquerda, menor que uma peca."""
        grade = self.paleta.layout()
        for botao in (self.paleta._botoes[APAGAR], self.paleta.btn_largar):
            with self.subTest(botao=botao.text()):
                self.assertEqual(2, grade.getItemPosition(grade.indexOf(botao))[3], "nao atravessa as duas")


class DesenhoTests(PaletaTests):
    """As imagens da S-65, e a degradacao que elas exigem."""

    def test_os_doze_botoes_tem_imagem_e_nao_texto(self) -> None:
        """O criterio de aceite da S-65, literal."""
        if not qt_tabuleiro.carregar_pecas():
            self.skipTest("checkout sem assets/piece_images/")
        for simbolo in board_edit.PIECE_SYMBOLS:
            with self.subTest(simbolo=simbolo):
                botao = self.paleta._botoes[simbolo]
                self.assertEqual("", botao.text())
                self.assertFalse(botao.icon().isNull())

    def test_sem_png_o_botao_cai_no_glifo_unicode(self) -> None:
        """Uma peca faltando nao pode impedir a aba de abrir -- e o botao continua dizendo qual e."""
        paleta = PaletaDePecas(pasta_de_pecas=PASTA_VAZIA)
        self.addCleanup(descartar, paleta)
        for simbolo in board_edit.PIECE_SYMBOLS:
            with self.subTest(simbolo=simbolo):
                self.assertEqual(qt_tabuleiro.GLIFOS[simbolo], paleta._botoes[simbolo].text())
                self.assertTrue(paleta._botoes[simbolo].icon().isNull())

    def test_a_troca_de_conjunto_alcanca_a_paleta_ja_montada(self) -> None:
        """Trocar de conjunto e **uma** chamada, e nao uma por widget (S-230)."""
        if not qt_tabuleiro.carregar_pecas():
            self.skipTest("checkout sem assets/piece_images/")
        self.addCleanup(qt_tabuleiro.definir_conjunto, conjuntos.PADRAO)
        qt_tabuleiro.definir_conjunto(conjuntos.PASTA, str(PASTA_VAZIA))
        self.assertEqual(qt_tabuleiro.GLIFOS["P"], self.paleta._botoes["P"].text())
        qt_tabuleiro.definir_conjunto(conjuntos.PADRAO)
        self.assertEqual("", self.paleta._botoes["P"].text())
        self.assertFalse(self.paleta._botoes["P"].icon().isNull())

    def test_o_botao_aceso_se_distingue_do_apagado_nas_duas_peles(self) -> None:
        """A outra metade do criterio da S-65, com o piso do proprio projeto.

        A folha da aplicacao pinta `QWidget` com uma cor de fundo, e cor vinda de folha vale em
        **todos** os estados: sem uma regra `:checked` propria, o botao aceso sai identico aos
        outros doze -- que e o defeito que a S-65 mediu no Tk, com outro mecanismo.
        """
        self.addCleanup(tema.aplicar_tema, self.app, cromo_escuro=False)
        for cromo_escuro in (False, True):
            with self.subTest(cromo_escuro=cromo_escuro):
                tema.aplicar_tema(self.app, cromo_escuro=cromo_escuro)
                superficie = tema.cor_atual(tokens.SUPERFICIE_PADRAO)
                aceso = tokens.mistura(superficie, tema.cor_atual(tokens.TEXTO_PADRAO), PESO_DO_SELECIONADO)
                self.assertIn(f"QToolButton:checked {{ background-color: {aceso}; }}", self.paleta.styleSheet())
                self.assertGreaterEqual(
                    tokens.razao_de_contraste(aceso, superficie),
                    tokens.AA_GRAFICO,
                    "o pincel aceso nao se separa do botao apagado",
                )


class CinzaTests(PaletaTests):
    """Sem diagrama aberto a paleta apaga -- e diz por que (S-165/S-170)."""

    def test_apagada_a_paleta_larga_o_pincel(self) -> None:
        """Um pincel que sobrevivesse a pagina fechada voltaria armado na proxima."""
        self.paleta._botoes["Q"].click()
        self.paleta.habilitar(False, motivo="Nao ha diagrama aberto.")
        self.assertIsNone(self.paleta.escolhido)
        self.assertEqual(["Q", None], self.escolhidos)

    def test_apagada_ela_diz_por_que_esta_cinza(self) -> None:
        self.paleta.habilitar(False, motivo="Nao ha diagrama aberto.")
        for botao in (*self.paleta._botoes.values(), self.paleta.btn_largar):
            with self.subTest(botao=botao.text()):
                self.assertFalse(botao.isEnabled())
                self.assertEqual("Nao ha diagrama aberto.", botao.toolTip())

    def test_acesa_de_novo_ela_volta_a_dizer_o_que_cada_botao_poe(self) -> None:
        self.paleta.habilitar(False, motivo="Nao ha diagrama aberto.")
        self.paleta.habilitar(True)
        self.assertTrue(self.paleta._botoes["b"].isEnabled())
        self.assertIn(board_edit.PIECE_NAMES_PT["b"], self.paleta._botoes["b"].toolTip())

    def test_acender_de_novo_nao_arma_pincel_nenhum(self) -> None:
        """`_atualizar_botoes` roda a cada edicao: acender nao pode ser um gesto de escolha."""
        self.paleta._botoes["Q"].click()
        self.escolhidos.clear()
        self.paleta.habilitar(True)
        self.assertEqual([], self.escolhidos)
        self.assertEqual("Q", self.paleta.escolhido)


if __name__ == "__main__":
    unittest.main()
