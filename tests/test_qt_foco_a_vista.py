"""A rolagem mostra o controle que recebe o foco, inteiro, venha o foco de onde vier (`qt/foco_a_vista`).

**O defeito, medido pelo crítico da fase 5 do ciclo 2 OCR/UI (ciclo 5).** A 1280x641, com a rolagem
no topo -- como quem chega a encontra --, o Shift+Tab que entra numa rolagem vindo de fora punha o
foco num controle com 0x0 px à vista: «Esconder incerteza» no Resultado e «Copiar cabeçalhos para
todos» na Galeria, nas três peles. A `QScrollArea` só rola até o foco que anda *dentro* dela.

Aqui, com a tecla de verdade (`QTest.keyClick`), cada rolagem que o Tab alcança de fora: a dos modos
da aba Livro (`PainelPrincipal._rolagem_de`), a lateral da Galeria e a lista do diálogo «Base de
partidas» com bases bastantes para rolar -- e, em cada uma, a sabotagem: o seguidor desligado, o foco
volta a cair fora da vista.
"""

from __future__ import annotations

import unittest

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

if TEM_PYQT:
    from PyQt6.QtCore import QPoint, QRect, Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLineEdit, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget

    from chess_diagram_ocr.qt import dialogos as qt_dialogos
    from chess_diagram_ocr.qt import painel_da_galeria as qt_galeria
    from chess_diagram_ocr.qt.foco_a_vista import seguidor_de
    from chess_diagram_ocr.qt.painel_principal import PainelPrincipal


def _inteiro(rolagem: QScrollArea, controle: QWidget) -> bool:
    ret = QRect(controle.mapTo(rolagem.viewport(), QPoint(0, 0)), controle.size())
    return rolagem.viewport().rect().contains(ret)


def _de_volta(app: object, inicio: QWidget) -> QWidget:
    """O controle que recebe o foco com um Shift+Tab a partir de ``inicio``."""
    inicio.setFocus(Qt.FocusReason.TabFocusReason)
    app.processEvents()  # type: ignore[attr-defined]
    QTest.keyClick(inicio, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    app.processEvents()  # type: ignore[attr-defined]
    atual = app.focusWidget()  # type: ignore[attr-defined]
    assert atual is not None
    return atual


def _no_topo(rolagem: QScrollArea, app: object) -> None:
    rolagem.verticalScrollBar().setValue(0)
    rolagem.horizontalScrollBar().setValue(0)
    app.processEvents()  # type: ignore[attr-defined]


def _depois_de(rolagem: QScrollArea) -> QWidget:
    """O primeiro controle que o Tab alcança depois do último da rolagem -- fora dela."""
    conteudo = rolagem.widget()
    assert conteudo is not None
    atual = conteudo.nextInFocusChain()
    ultimo_dentro = None
    for _ in range(2000):
        dentro = conteudo.isAncestorOf(atual)
        tab = bool(atual.focusPolicy().value & Qt.FocusPolicy.TabFocus.value)
        if dentro and tab and atual.isVisible():
            ultimo_dentro = atual
        elif ultimo_dentro is not None and tab and atual.isVisible() and atual.isEnabled():
            return atual
        atual = atual.nextInFocusChain()
    raise AssertionError("nenhum controle depois da rolagem")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SeguidorTests(unittest.TestCase):
    """O seguidor numa janela de mentira: vinte campos e uma caixa de 48 px numa rolagem curta, e um
    botão abaixo dela."""

    def setUp(self) -> None:
        self.app = aplicacao()
        from chess_diagram_ocr.qt.foco_a_vista import RolagemSegueOFoco

        self.janela = QWidget()
        self.addCleanup(descartar, self.janela)
        fora = QVBoxLayout(self.janela)
        self.rolagem = QScrollArea(self.janela)
        self.rolagem.setWidgetResizable(True)
        self.conteudo = QWidget(self.rolagem)
        coluna = QVBoxLayout(self.conteudo)
        for k in range(20):
            coluna.addWidget(QLineEdit(f"campo {k}", self.conteudo))
        self.caixa = QTextEdit(self.conteudo)
        self.caixa.setPlainText("\n".join(f"linha {k}" for k in range(8)))
        self.caixa.setFixedHeight(48)
        coluna.addWidget(self.caixa)
        self.rolagem.setWidget(self.conteudo)
        fora.addWidget(self.rolagem, 1)
        self.botao = QPushButton("Aceitar", self.janela)
        fora.addWidget(self.botao)
        self.seguidor = RolagemSegueOFoco(self.rolagem)
        self.janela.resize(360, 300)
        self.janela.show()
        self.app.processEvents()

    def test_o_foco_que_vem_de_fora_fica_inteiro_a_vista(self) -> None:
        """No topo, e com os primeiros 20 px da caixa à vista -- onde `ensureWidgetVisible` não
        rola nada, porque o cursor dela já está à vista, e o resto fica cortado."""
        topo = self.caixa.mapTo(self.conteudo, QPoint(0, 0)).y()
        for valor in (0, topo - self.rolagem.viewport().height() + 20):
            self.rolagem.verticalScrollBar().setValue(valor)
            self.caixa.moveCursor(QTextCursor.MoveOperation.Start)
            recebeu = _de_volta(self.app, self.botao)
            self.assertIs(recebeu, self.caixa)
            self.assertTrue(_inteiro(self.rolagem, self.caixa), valor)

    def test_um_controle_criado_depois_tambem_e_seguido(self) -> None:
        """A lista de bases se redesenha: o seguidor não é um filtro posto em quem existia."""
        novo = QLineEdit("feito depois", self.conteudo)
        layout = self.conteudo.layout()
        assert layout is not None
        layout.insertWidget(0, novo)  # type: ignore[attr-defined]
        self.app.processEvents()
        self.rolagem.verticalScrollBar().setValue(self.rolagem.verticalScrollBar().maximum())
        novo.setFocus(Qt.FocusReason.OtherFocusReason)
        self.app.processEvents()
        self.assertTrue(_inteiro(self.rolagem, novo))

    def test_sabotagem_desligado_o_foco_cai_fora_da_vista(self) -> None:
        self.seguidor.desligar()
        _no_topo(self.rolagem, self.app)
        recebeu = _de_volta(self.app, self.botao)
        self.assertIs(recebeu, self.caixa)
        self.assertTrue(self.caixa.visibleRegion().isEmpty())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RolagensDoProdutoTests(unittest.TestCase):
    """As três rolagens do tronco que o Tab alcança de fora, com a tecla e a rolagem no topo."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def _confere(self, rolagem: QScrollArea, *, altura_minima: int) -> None:
        """Shift+Tab a partir do primeiro controle depois da rolagem: o último dela recebe o foco,
        inteiro à vista; desligado o seguidor, fora da vista."""
        conteudo = rolagem.widget()
        assert conteudo is not None
        self.assertGreater(conteudo.height(), rolagem.viewport().height() + altura_minima,
                           "a rolagem precisa rolar para o teste valer")
        seguidor = seguidor_de(rolagem)
        assert seguidor is not None, "a rolagem não segue o foco"
        inicio = _depois_de(rolagem)
        _no_topo(rolagem, self.app)
        recebeu = _de_volta(self.app, inicio)
        self.assertTrue(conteudo.isAncestorOf(recebeu), recebeu)
        self.assertTrue(_inteiro(rolagem, recebeu), (recebeu.accessibleName(), type(recebeu)))
        seguidor.desligar()
        _no_topo(rolagem, self.app)
        recebeu = _de_volta(self.app, inicio)
        self.assertTrue(recebeu.visibleRegion().isEmpty(), "sabotado, o foco cai fora da vista")

    def test_os_modos_da_aba_livro(self) -> None:
        """O modo numa janela curta com um botão abaixo, como a barra de ferramentas da janela."""
        janela = QWidget()
        self.addCleanup(descartar, janela)
        coluna = QVBoxLayout(janela)
        principal = PainelPrincipal(janela)
        modo = QWidget()
        pilha = QVBoxLayout(modo)
        for k in range(24):
            pilha.addWidget(QLineEdit(f"campo {k}", modo))
        pilha.addWidget(QPushButton("Esconder incerteza", modo))
        principal.adicionar_modo("Resultado", modo)
        coluna.addWidget(principal, 1)
        coluna.addWidget(QPushButton("Abrir PDF", janela))
        janela.resize(640, 320)
        janela.show()
        self.app.processEvents()
        rolagem = principal.findChild(QScrollArea)
        assert rolagem is not None
        self._confere(rolagem, altura_minima=100)

    def test_a_lateral_da_galeria(self) -> None:
        painel = qt_galeria.PainelDaGaleria(
            service=None,  # type: ignore[arg-type]
            pdf_path=lambda: None,
            model_path=lambda: self.pasta / "modelo.pt",
            max_boards=lambda: 4,
        )
        self.addCleanup(descartar, painel)
        painel.resize(1000, 380)
        painel.show()
        self.app.processEvents()
        campo = painel.campos_de_header["White"]
        rolagem = next(r for r in painel.findChildren(QScrollArea)
                       if r.widget() is not None and r.widget().isAncestorOf(campo))
        self._confere(rolagem, altura_minima=50)

    def test_a_lista_de_bases_com_muitas_bases(self) -> None:
        for k in range(40):
            (self.pasta / f"base_{k:02d}.pgn").write_bytes(b"x" * (1000 + k))
        dialogo = qt_dialogos.DialogoDeBases(folder=self.pasta, nota=lambda _bases: "")
        self.addCleanup(descartar, dialogo)
        dialogo.resize(520, 320)
        dialogo.show()
        self.app.processEvents()
        rolagem = dialogo.findChild(QScrollArea)
        assert rolagem is not None
        self._confere(rolagem, altura_minima=100)


if __name__ == "__main__":
    unittest.main()
