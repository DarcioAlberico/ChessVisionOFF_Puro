"""A legenda de atalhos do segundo frontend (S-165/S-244/S-281/S-501).

**O que estes testes cobrem, e o que não.** Que a tabela é a única declaração de tecla, e que a
descrição conta os três destinos, é afirmado em `tests/test_ui_legenda.py` sobre a tabela e sobre
a janela do Tk. A `descricao_completa` passou a ser de `ui/atalhos.py` e é a mesma nas duas
janelas, então repeti-la aqui mediria o mesmo código duas vezes.

O que só existe deste lado é que **esta** janela é gerada da tabela em vez de listada à mão -- que
é a propriedade inteira da S-165, e a única que pode ser perdida em silêncio ao portar: uma
legenda com dezoito das vinte e uma teclas não levanta, ela só mente.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest import mock

from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import atalhos, menu

if TEM_PYQT:
    from PyQt6.QtWidgets import QWidget

    from chess_diagram_ocr.qt import legenda as qt_legenda


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LegendaTests(unittest.TestCase):
    """Uma linha por atalho, e a frase de cada uma vem da tabela."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pai = QWidget()
        self.addCleanup(self.pai.deleteLater)

    def abrir(self) -> object:
        janela = qt_legenda.abrir(self.pai)
        self.addCleanup(janela.deleteLater)
        return janela

    def test_a_legenda_mostra_todos_com_a_mesma_descricao_da_tabela(self) -> None:
        """As da janela e, depois delas, as quatro da sala (S-527): uma tecla que a legenda não
        lista é a S-161 de novo, e a dica do botão não é onde alguém a procura."""
        esperado = [(a.rotulo, atalhos.descricao_completa(a)) for a in (*atalhos.ATALHOS, *atalhos.TECLAS_DA_SALA)]
        self.assertEqual(self.abrir().linhas(), esperado)
        self.assertIn(("Ctrl+↑", "Promover a variante um nível"), esperado)

    def test_a_legenda_mostra_os_dois_destinos(self) -> None:
        """Uma tecla que faz duas coisas e uma legenda que só conta uma é pior que não ter
        legenda -- é o que a S-244 pede, e o que a S-281 estendeu para a sala de estudo."""
        por_tecla = dict(self.abrir().linhas())
        multiplos = [a for a in atalhos.ATALHOS if a.no_editor or a.na_sala]
        self.assertTrue(multiplos, "a tabela deixou de ter tecla com mais de um destino")
        for atalho in multiplos:
            with self.subTest(tecla=atalho.rotulo):
                for texto in (atalho.no_editor, atalho.na_sala):
                    if texto:
                        self.assertIn(texto, por_tecla[atalho.rotulo])

    def test_um_atalho_novo_aparece_sem_ninguem_editar_a_legenda(self) -> None:
        """**É a propriedade inteira da S-165.**

        Uma segunda lista escrita à mão diverge da primeira -- é o que aconteceu com os rótulos
        de procedência antes da S-04. Aqui a divergência é impossível por construção, e este
        teste é quem cobra que continue sendo.
        """
        inventado = replace(atalhos.ATALHOS[0], sequencia="<F9>", rotulo="F9", acao="inventada",
                            descricao="Uma tecla que não existia", no_editor="", na_sala="")
        with mock.patch.object(atalhos, "ATALHOS", (*atalhos.ATALHOS, inventado)):
            linhas = self.abrir().linhas()
        self.assertIn(("F9", "Uma tecla que não existia"), linhas)

    def test_a_guarda_de_foco_esta_dita_onde_alguem_a_procura(self) -> None:
        """A legenda é o único lugar em que alguém pergunta "por que a seta não trocou de
        diagrama agora?"."""
        self.assertIn("campo", qt_legenda.NOTA)
        self.assertIn("Delete", qt_legenda.NOTA)

    def test_reabrir_traz_a_que_ja_esta_aberta_em_vez_de_empilhar(self) -> None:
        primeira = self.abrir()
        self.assertIs(qt_legenda.abrir(self.pai), primeira)
        self.assertEqual(len(self.pai.findChildren(qt_legenda.JanelaDeAtalhos)), 1)

    def test_a_legenda_esta_no_menu_ajuda(self) -> None:
        """Uma legenda que existe e não tem porta é uma legenda que ninguém abre."""
        self.assertIn("legenda_de_atalhos", menu.acoes_declaradas())

    def test_a_lista_rola_em_vez_de_passar_da_tela(self) -> None:
        """Vinte e uma linhas na fonte do Windows em 12 pt passam de 768 px de altura.

        A janela do Tk é `resizable(False, False)` e cabe porque cabe; uma legenda cujo fim não
        se alcança é o defeito que ela existe para não ter.
        """
        from PyQt6.QtWidgets import QScrollArea

        self.assertTrue(self.abrir().findChildren(QScrollArea))

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
