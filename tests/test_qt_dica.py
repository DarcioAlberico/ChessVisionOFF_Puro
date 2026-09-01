"""A dica do segundo frontend (S-32/S-403/S-501).

O `QToolTip` faz sozinho o que `ui/tooltip.py` escreve em 147 linhas -- o tempo, o cancelamento,
e o esquecimento do agendamento quando o widget morre antes de a dica aparecer (S-402). O que
sobra a testar são as duas decisões que continuam sendo do projeto e o defeito que o Qt traz de
fábrica:

1. o tempo é **um só** na janela inteira, e é o mesmo dos dois frontends (S-403);
2. a cor é a do tema, e não um amarelo cravado (S-147);
3. um controle desabilitado **não recebe evento de ponteiro no Qt** -- e um botão cinza sem
   explicação é o defeito que a S-32 existe para fechar.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import tokens

if TEM_PYQT:
    from PyQt6.QtCore import QEvent, QPoint
    from PyQt6.QtGui import QHelpEvent
    from PyQt6.QtWidgets import QPushButton, QWidget

    from chess_diagram_ocr.qt import dica, tema


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AtrasoTests(unittest.TestCase):
    """Uma decisão tomada uma vez, e não uma por dica."""

    def test_ajustar_fixa_o_tempo_no_qt(self) -> None:
        """**Afirma o efeito, e não a chamada.**

        A primeira versão deste teste comparava 700 com 700 quando o Qt não respondia -- e foi
        assim que um `QToolTip.setWaitTime` que **não existe** no Qt6 passou por verde: a chamada
        levantava, o `except` tolerante engolia, e a S-403 não valia. O tempo da dica é a dica de
        estilo `SH_ToolTip_WakeUpDelay`, e é ela que se pergunta aqui.
        """
        aplicacao()
        self.addCleanup(dica.ajustar_atraso)
        self.assertTrue(dica.ajustar_atraso(700))
        self.assertEqual(dica.atraso_em_vigor(), 700)

    def test_o_padrao_e_o_atraso_do_projeto(self) -> None:
        aplicacao()
        self.assertTrue(dica.ajustar_atraso())
        self.assertEqual(dica.atraso_em_vigor(), dica.ATRASO_DA_DICA)

    def test_ajustar_nunca_levanta(self) -> None:
        """Uma dica no tempo de fábrica é pior que a do projeto e melhor que uma janela fechada."""
        aplicacao()
        self.addCleanup(dica.ajustar_atraso)
        dica.ajustar_atraso(-1)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class CorTests(unittest.TestCase):
    """A dica segue o tema, e a letra segue a superfície dela (S-147)."""

    def test_a_dica_esta_na_folha_com_a_cor_do_papel(self) -> None:
        for cromo_escuro in (False, True):
            with self.subTest(cromo_escuro=cromo_escuro):
                qss = tema.folha_de_estilo(cromo_escuro=cromo_escuro)
                fundo = tokens.cor(tokens.SUPERFICIE_DICA, None, cromo_escuro=cromo_escuro)
                self.assertIn(f"QToolTip {{ background-color: {fundo};", qss)
                self.assertIn(f"color: {tokens.sobre_superficie(fundo)};", qss)

    def test_a_letra_da_dica_e_legivel_sobre_o_fundo_dela(self) -> None:
        """O defeito da S-147: letra clara sobre `#ffffe0` sob tema escuro.

        Era a única explicação que um botão desabilitado oferece, e era ilegível.
        """
        for cromo_escuro in (False, True):
            fundo = tokens.cor(tokens.SUPERFICIE_DICA, None, cromo_escuro=cromo_escuro)
            with self.subTest(cromo_escuro=cromo_escuro):
                self.assertGreaterEqual(
                    tokens.razao_de_contraste(tokens.sobre_superficie(fundo), fundo),
                    tokens.AA_TEXTO,
                )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DesabilitadoTests(unittest.TestCase):
    """O item da S-32: um botão cinza sem explicação é pior que um botão ausente."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.painel = QWidget()
        self.painel.resize(200, 100)
        self.botao = QPushButton("Treinar", self.painel)
        self.botao.setGeometry(10, 10, 100, 30)
        dica.dica_em(self.botao, "Escolha um conjunto antes de treinar.")
        # A ordem importa: um filho criado depois de o pai aparecer não é mostrado sozinho, e
        # `childAt` não devolve o que não está visível -- o filtro responderia `False` e o teste
        # mediria a ausência de botão em vez do comportamento da dica.
        self.painel.show()
        self.app.processEvents()
        self.addCleanup(self.painel.deleteLater)
        self.filtro = dica.DicaEmDesabilitado(self.painel)

    def evento(self, x: int = 50, y: int = 25) -> QHelpEvent:
        ponto = QPoint(x, y)
        return QHelpEvent(QEvent.Type.ToolTip, ponto, self.painel.mapToGlobal(ponto))

    def test_o_desabilitado_ganha_a_dica_que_o_qt_engoliria(self) -> None:
        """Um `QWidget` desabilitado não recebe evento de ponteiro: o Qt os entrega ao pai.

        `setToolTip` num botão desabilitado, então, não mostra nada -- e é literalmente o
        critério de aceite da S-32 que o padrão do Qt reprova.
        """
        self.botao.setEnabled(False)
        self.assertTrue(self.filtro.eventFilter(self.painel, self.evento()))

    def test_o_habilitado_segue_pelo_caminho_normal_do_qt(self) -> None:
        """Interceptá-lo faria este filtro reimplementar, pior, o que já funciona."""
        self.botao.setEnabled(True)
        self.assertFalse(self.filtro.eventFilter(self.painel, self.evento()))

    def test_o_desabilitado_sem_dica_nao_mostra_caixa_vazia(self) -> None:
        self.botao.setEnabled(False)
        dica.dica_em(self.botao, "")
        self.assertFalse(self.filtro.eventFilter(self.painel, self.evento()))

    def test_fora_de_todo_filho_nao_e_tratado(self) -> None:
        self.botao.setEnabled(False)
        self.assertFalse(self.filtro.eventFilter(self.painel, self.evento(180, 90)))

    def test_evento_que_nao_e_dica_passa_batido(self) -> None:
        self.assertFalse(self.filtro.eventFilter(self.painel, QEvent(QEvent.Type.Show)))
        self.assertFalse(self.filtro.eventFilter(self.painel, None))

    def test_o_filtro_nasce_filho_do_painel(self) -> None:
        """Um `QObject` sem referência é coletado, e um filtro coletado deixa de ser chamado.

        O sintoma seria a dica funcionar às vezes -- a mesma razão de `qt/atalhos.ligar`.
        """
        self.assertIs(self.filtro.parent(), self.painel)

    def test_texto_vazio_apaga_a_dica(self) -> None:
        """É o comportamento de `Tooltip.set_text`: quando o botão volta a estar habilitado,
        não há mais o que explicar."""
        dica.dica_em(self.botao, "")
        self.assertEqual(self.botao.toolTip(), "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
