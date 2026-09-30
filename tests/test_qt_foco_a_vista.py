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

import contextlib
import unittest
from collections.abc import Iterator
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

if TEM_PYQT:
    from PyQt6.QtCore import QPoint, QRect, Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import (
        QCheckBox,
        QLineEdit,
        QListWidget,
        QPushButton,
        QScrollArea,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    from chess_diagram_ocr.qt import dialogos as qt_dialogos
    from chess_diagram_ocr.qt import foco_a_vista
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


def _clique_pela_janela(app: object, janela: QWidget, ponto: QPoint) -> None:
    """Pressiona e solta o botão esquerdo no mesmo ponto da janela, pelo `QWindow` -- o despacho do
    Qt, o que um mouse parado faz (a sonda do crítico da fase 5, ciclo 6)."""
    alca = janela.windowHandle()
    assert alca is not None
    QTest.mousePress(alca, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, ponto)
    app.processEvents()  # type: ignore[attr-defined]
    QTest.mouseRelease(alca, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, ponto)
    app.processEvents()  # type: ignore[attr-defined]


def _sossegar(app: object) -> None:
    """O mouse sossegado: o intervalo do duplo clique e um pouco mais, com o laço de eventos rodando."""
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication

    dicas = QApplication.styleHints()
    assert dicas is not None
    laco = QEventLoop()
    QTimer.singleShot(dicas.mouseDoubleClickInterval() + 100, laco.quit)
    laco.exec()
    app.processEvents()  # type: ignore[attr-defined]


def _mouse_sossegado_desde_ja() -> None:
    """Cada teste começa com o mouse sossegado: o último soltar do teste de antes, que o anotador da
    aplicação guarda, não faz o foco do seguinte esperar."""
    razao = foco_a_vista._razao_do_foco()
    if razao is not None:
        razao.soltou_em = float("-inf")


def _segundo_clique_de_um_duplo(app: object, janela: QWidget, ponto: QPoint) -> None:
    """O segundo clique de um duplo clique como o Qt o entrega: o pressionar, o duplo clique ao
    controle sob o ponteiro, o soltar. O `QTest` põe o intervalo do duplo clique entre dois cliques
    dele, para nunca fazer um duplo clique por acaso: o duplo clique vai à mão, como na sonda do
    crítico (fase 5, ciclo 8)."""
    from PyQt6.QtCore import QEvent, QPointF
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication

    alca = janela.windowHandle()
    assert alca is not None
    QTest.mousePress(alca, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, ponto)
    app.processEvents()  # type: ignore[attr-defined]
    alvo = janela.childAt(ponto)
    assert alvo is not None
    duplo = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(alvo.mapFrom(janela, ponto)),
                        QPointF(janela.mapToGlobal(ponto)), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(alvo, duplo)
    app.processEvents()  # type: ignore[attr-defined]
    QTest.mouseRelease(alca, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, ponto)
    app.processEvents()  # type: ignore[attr-defined]


def _a_vista_embaixo(app: object, rolagem: QScrollArea, controle: QWidget, px: int) -> None:
    """Rola ``rolagem`` até ``controle`` ficar com ``px`` à vista, cortado pela borda de baixo."""
    conteudo = rolagem.widget()
    assert conteudo is not None
    topo = controle.mapTo(conteudo, QPoint(0, 0)).y()
    rolagem.verticalScrollBar().setValue(topo + px - rolagem.viewport().height())
    app.processEvents()  # type: ignore[attr-defined]
    ret = QRect(controle.mapTo(rolagem.viewport(), QPoint(0, 0)), controle.size())
    assert ret.intersected(rolagem.viewport().rect()).height() == px, "a rolagem não chega lá"


@contextlib.contextmanager
def _sem_a_guarda_do_mouse() -> Iterator[None]:
    """A sabotagem: o seguidor rola também no foco que o mouse dá, e no pressionar, como no ciclo 6."""
    with (mock.patch.object(foco_a_vista, "veio_do_mouse", lambda _controle: False),
          mock.patch.object(foco_a_vista, "no_meio_do_clique", lambda: False),
          mock.patch.object(foco_a_vista, "mouse_sossegado", lambda: True)):
        yield


def _guarda_do_ciclo_7(controle: QWidget) -> bool:
    """A guarda do ciclo 7, para a sabotagem: todo foco com um botão apertado é do mouse -- também o
    que o programa manda a outro controle no pressionar."""
    from PyQt6.QtWidgets import QApplication

    if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
        return True
    return controle.focusPolicy() == Qt.FocusPolicy.WheelFocus and controle.underMouse()


def _guarda_do_ponteiro(controle: QWidget) -> bool:
    """A guarda da primeira versão do ciclo 8, para a sabotagem: o ponteiro, e não a razão do foco -- o
    controle (ou quem o tem por procurador do foco) sob o ponteiro com um botão apertado, ou a caixa de
    escolha sob o ponteiro parado."""
    from PyQt6.QtWidgets import QApplication

    def sob(atual: QWidget | None) -> bool:
        while atual is not None:
            if atual.underMouse():
                return True
            pai = atual.parentWidget()
            if pai is None or pai.focusProxy() is not atual:
                return False
            atual = pai
        return False

    if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
        return sob(controle)
    return controle.focusPolicy() == Qt.FocusPolicy.WheelFocus and controle.underMouse()


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
        _mouse_sossegado_desde_ja()
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
        self.marca = QCheckBox("Esconder incerteza", self.conteudo)
        coluna.addWidget(self.marca)
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

    def test_o_clique_num_controle_meio_a_vista_vale_onde_foi_dado(self) -> None:
        """O Qt dá o foco no *pressionar*; o seguidor rolava ali, e o *soltar* caía fora do controle
        -- 15 de 15 cliques do crítico (fase 5, ciclo 6). Com a caixa com 9 px à vista, o clique
        junto do corte a marca e nada rola. A sabotagem: o seguidor rola no foco do mouse, a
        caixa sobe e o clique se perde."""
        for sabotado in (False, True):
            self.marca.setChecked(False)
            self.botao.setFocus(Qt.FocusReason.OtherFocusReason)
            _a_vista_embaixo(self.app, self.rolagem, self.marca, 9)
            antes = self.rolagem.verticalScrollBar().value()
            ponto = self.marca.mapTo(self.janela, QPoint(8, 6))
            with _sem_a_guarda_do_mouse() if sabotado else contextlib.nullcontext():
                _clique_pela_janela(self.app, self.janela, ponto)
            depois = self.rolagem.verticalScrollBar().value()
            if sabotado:
                self.assertNotEqual(depois, antes)
                self.assertFalse(self.marca.isChecked(), "sabotado, o clique se perde")
            else:
                self.assertEqual(depois, antes, "o clique não rola")
                self.assertTrue(self.marca.isChecked())
                self.assertIs(self.app.focusWidget(), self.marca)

    def test_o_controle_que_cabe_por_pouco_aparece_inteiro(self) -> None:
        """Um controle 1 px menor que a vista cabe nela, mas não com a folga em volta: aparece
        inteiro, com menos folga -- a «Verdade da linha» da Rotulagem da suíte tem 549 px numa vista de
        550, e a folga inteira a deixava com 3 px cortados (crítico da fase 5, ciclo 7). A sabotagem:
        o encaixe do ciclo 7, que mostrava o começo com a folga e cortava o fim."""
        self.caixa.setFixedHeight(self.rolagem.viewport().height() - 1)
        for _vez in range(2):
            self.app.processEvents()

        def de_volta_do_botao() -> bool:
            _no_topo(self.rolagem, self.app)
            self.assertIs(_de_volta(self.app, self.botao), self.caixa)
            return _inteiro(self.rolagem, self.caixa)

        self.assertTrue(de_volta_do_botao(), "o controle que cabe aparece inteiro")

        def encaixe_do_ciclo_7(barra: object, inicio: int, fim: int, vista: int) -> None:
            folga = foco_a_vista.FOLGA
            atual = barra.value()  # type: ignore[attr-defined]
            if fim - inicio + 2 * folga > vista or inicio - folga < atual:
                alvo = inicio - folga
            elif fim + folga > atual + vista:
                alvo = fim + folga - vista
            else:
                return
            barra.setValue(max(barra.minimum(), min(barra.maximum(), alvo)))  # type: ignore[attr-defined]

        with mock.patch.object(foco_a_vista, "_encaixar", encaixe_do_ciclo_7):
            self.assertFalse(de_volta_do_botao(), "sabotado, a folga corta o fim")

    def test_o_foco_que_o_programa_move_no_clique_aparece_quando_o_mouse_sossega(self) -> None:
        """Crítico da fase 5, ciclo 7: a linha da tabela da Rotulagem e da Revisão de texto manda o foco
        à «Verdade da linha» no *pressionar*, e a guarda do ciclo 7 (um botão apertado) tomava esse foco
        pelo do mouse -- a verdade ficava fora da vista (0x0 px a 1280x641), e o que se digitava ia
        para lá. Aqui uma lista no alto da rolagem manda o foco à caixa do fim quando a linha muda, no
        pressionar: o clique termina onde foi dado (a linha clicada uma vez), a caixa aparece inteira
        quando o mouse sossega (o intervalo do duplo clique depois do soltar), e o que se digita entra
        nela. As sabotagens: a guarda do ciclo 7 (a caixa fica escondida); o seguidor do ciclo 6, que
        rolava no pressionar (a lista sai de baixo do ponteiro e o clique se perde)."""
        from PyQt6.QtWidgets import QListWidget

        linhas = QListWidget(self.conteudo)
        linhas.addItems(["linha 1", "linha 2", "linha 3"])
        linhas.setFixedHeight(90)
        layout = self.conteudo.layout()
        assert layout is not None
        layout.insertWidget(0, linhas)  # type: ignore[attr-defined]
        # os painéis: a linha escolhida no pressionar manda o foco à verdade
        linhas.currentRowChanged.connect(lambda _r: self.caixa.setFocus(Qt.FocusReason.OtherFocusReason))
        clicado: list[int] = []
        linhas.clicked.connect(lambda indice: clicado.append(indice.row()))
        for _vez in range(2):  # o layout cresce o conteúdo, depois a rolagem o toma
            self.app.processEvents()

        def clicar_a_linha() -> None:
            clicado.clear()
            linhas.setCurrentRow(0)
            self.caixa.setPlainText("uma leitura")
            _no_topo(self.rolagem, self.app)
            self.botao.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app.processEvents()
            self.assertTrue(self.caixa.visibleRegion().isEmpty(), "a caixa começa abaixo da dobra")
            item = linhas.item(1)
            assert item is not None
            ponto = linhas.viewport().mapTo(self.janela, linhas.visualItemRect(item).center())
            _clique_pela_janela(self.app, self.janela, ponto)
            _sossegar(self.app)  # o soltar, o intervalo do duplo clique, e a rolagem
            vistas.append(_inteiro(self.rolagem, self.caixa))
            foco = self.app.focusWidget()
            assert foco is not None
            QTest.keyClicks(foco, "XYZ")
            self.app.processEvents()

        vistas: list[bool] = []
        clicar_a_linha()
        self.assertEqual(clicado, [1], "o clique termina onde foi dado")
        self.assertEqual(linhas.currentRow(), 1)
        self.assertIs(self.app.focusWidget(), self.caixa)
        self.assertEqual(vistas, [True], "o foco que o programa moveu aparece quando o mouse sossega")
        self.assertIn("XYZ", self.caixa.toPlainText(), "e o que se digita vai para onde os olhos estão")
        with mock.patch.object(foco_a_vista, "veio_do_mouse", _guarda_do_ciclo_7):
            clicar_a_linha()
        self.assertIs(self.app.focusWidget(), self.caixa)
        self.assertTrue(self.caixa.visibleRegion().isEmpty(), "sabotado (ciclo 7), o foco fica fora da vista")
        with _sem_a_guarda_do_mouse():
            clicar_a_linha()
        self.assertEqual(clicado, [], "sabotado (ciclo 6), a rolagem no pressionar perde o clique")

    def test_o_ponteiro_parado_nao_e_o_mouse_mas_a_roda_e(self) -> None:
        """A guarda do mouse é o pressionar e a roda, e não o ponteiro: o Tab que cai num botão sob
        o ponteiro parado, com 9 px dele à vista, o mostra inteiro, como a qualquer outro -- a guarda
        que tomava todo controle sob o ponteiro pelo foco do mouse o deixava com 9 px. A caixa de
        escolha, que toma o foco da roda, focada pelo mouse sob o ponteiro (a roda não se fabrica
        pelo Python; o foco é o que ela dá): nada rola, e a roda segue sobre ela. As sabotagens: o
        ponteiro sozinho conta como o mouse (o botão fica com 9 px); sem guarda nenhuma (a caixa
        salta debaixo da roda)."""
        from PyQt6.QtWidgets import QApplication, QComboBox

        gravar = QPushButton("Gravar", self.conteudo)
        pele = QComboBox(self.conteudo)
        pele.addItems(["Foco", "Fita", "Clássica"])
        layout = self.conteudo.layout()
        assert layout is not None
        layout.insertWidget(19, gravar)  # type: ignore[attr-defined]
        layout.insertWidget(10, pele)  # type: ignore[attr-defined]
        for _vez in range(2):  # o layout cresce o conteúdo, depois a rolagem o toma
            self.app.processEvents()
        alca = self.janela.windowHandle()
        assert alca is not None

        def nove_px_sob_o_ponteiro(controle: QWidget) -> int:
            _a_vista_embaixo(self.app, self.rolagem, controle, 9)
            # fora do controle antes: os dois se revezam no mesmo ponto da janela
            QTest.mouseMove(alca, QPoint(2, 2))
            QTest.mouseMove(alca, controle.mapTo(self.janela, QPoint(8, 4)))
            self.app.processEvents()
            self.assertTrue(controle.underMouse())
            self.assertEqual(QApplication.mouseButtons(), Qt.MouseButton.NoButton)
            return self.rolagem.verticalScrollBar().value()

        def tab_ate_o_botao() -> None:
            anterior = gravar.previousInFocusChain()
            assert anterior is not None
            anterior.setFocus(Qt.FocusReason.OtherFocusReason)
            nove_px_sob_o_ponteiro(gravar)
            QTest.keyClick(anterior, Qt.Key.Key_Tab)
            self.app.processEvents()
            self.assertIs(self.app.focusWidget(), gravar)

        def a_roda_na_caixa() -> tuple[int, int]:
            antes = nove_px_sob_o_ponteiro(pele)
            pele.setFocus(Qt.FocusReason.MouseFocusReason)
            self.app.processEvents()
            self.assertIs(self.app.focusWidget(), pele)
            return antes, self.rolagem.verticalScrollBar().value()

        tab_ate_o_botao()
        self.assertTrue(_inteiro(self.rolagem, gravar), "o Tab sob o ponteiro parado mostra o botão")
        antes, depois = a_roda_na_caixa()
        self.assertEqual(depois, antes, "o foco da roda não rola")
        with mock.patch.object(foco_a_vista, "veio_do_mouse", lambda controle: controle.underMouse()):
            tab_ate_o_botao()
        self.assertFalse(_inteiro(self.rolagem, gravar), "sabotado, o ponteiro prende o botão em 9 px")
        with _sem_a_guarda_do_mouse():
            antes, depois = a_roda_na_caixa()
        self.assertNotEqual(depois, antes, "sabotado, a caixa salta debaixo da roda")

    def test_o_foco_que_a_janela_devolve_ao_voltar_espera_o_clique_que_a_reativou(self) -> None:
        """Achado pelo construtor no ciclo 8 (fase 5): quando a janela volta a ser a ativa, o Qt devolve o
        foco ao controle que o tinha (`ActiveWindowFocusReason`), e o Windows ativa a janela antes de
        entregar o pressionar do clique que a reativou. Com a vista levada pela roda para longe daquele
        controle, o seguidor rolava até ele, e o pressionar caía noutro lugar (a sonda
        `c8/sonda_ativacao.py`: a rolagem de 242 a 3, o «Aceitar» sem o clique). Aqui o foco da volta e o
        pressionar saem um atrás do outro, sem o laço de eventos no meio, como no Windows (o
        `activateWindow` do offscreen entra na fila, e o `QTest` entregaria o pressionar antes dela): o
        botão recebe o clique, e nada rola -- o foco da volta espera o intervalo do duplo clique, e o
        clique o levou a outro controle. Sem clique -- a janela reativada de verdade, pelo
        `activateWindow` --, o campo aparece inteiro passado o intervalo. A sabotagem: o foco da volta
        mostrado na hora, e o clique se perde."""
        from PyQt6.QtWidgets import QApplication

        aceitar = QPushButton("Aceitar embaixo", self.conteudo)
        layout = self.conteudo.layout()
        assert layout is not None
        layout.addWidget(aceitar)  # type: ignore[attr-defined]
        clicados: list[bool] = []
        aceitar.clicked.connect(lambda: clicados.append(True))
        for _vez in range(2):  # o layout cresce o conteúdo, depois a rolagem o toma
            self.app.processEvents()
        primeiro = self.conteudo.findChildren(QLineEdit)[0]
        barra = self.rolagem.verticalScrollBar()

        def a_roda_leva_a_vista_ao_fim() -> None:
            primeiro.setFocus(Qt.FocusReason.TabFocusReason)
            self.app.processEvents()
            barra.setValue(barra.maximum())  # o foco fica no primeiro campo, fora da vista
            self.app.processEvents()
            self.assertTrue(primeiro.visibleRegion().isEmpty())

        def a_volta_com_um_clique() -> tuple[int, int]:
            clicados.clear()
            a_roda_leva_a_vista_ao_fim()
            antes = barra.value()
            ponto = aceitar.mapTo(self.janela, aceitar.rect().center())
            primeiro.clearFocus()  # a janela deixou de ser a ativa
            self.app.processEvents()
            primeiro.setFocus(Qt.FocusReason.ActiveWindowFocusReason)  # a janela voltou
            _clique_pela_janela(self.app, self.janela, ponto)  # e o pressionar vem logo atrás
            _sossegar(self.app)
            return antes, barra.value()

        antes, depois = a_volta_com_um_clique()
        self.assertEqual(clicados, [True], "o clique que reativou a janela vale onde foi dado")
        self.assertEqual(depois, antes, "nada rola debaixo do ponteiro")
        self.assertIs(self.app.focusWidget(), aceitar)

        outra = QWidget()
        self.addCleanup(descartar, outra)
        outra.resize(120, 80)
        outra.show()
        a_roda_leva_a_vista_ao_fim()
        outra.activateWindow()
        for _vez in range(3):
            self.app.processEvents()
        self.assertIsNot(QApplication.activeWindow(), self.janela)
        self.janela.activateWindow()
        _sossegar(self.app)
        self.assertIs(self.app.focusWidget(), primeiro, "a janela devolve o foco ao primeiro campo")
        self.assertTrue(_inteiro(self.rolagem, primeiro), "sem clique, o foco da volta aparece em seguida")

        with (mock.patch.object(foco_a_vista, "voltou_com_a_janela", lambda _controle: False),
              mock.patch.object(foco_a_vista, "mouse_sossegado", lambda: True)):
            antes, depois = a_volta_com_um_clique()
        self.assertEqual(clicados, [], "sabotado, o clique que reativou a janela se perde")
        self.assertNotEqual(depois, antes, "sabotado, a vista rola debaixo do ponteiro")

    def test_a_razao_do_foco_e_nao_o_ponteiro_diz_de_quem_e_o_foco(self) -> None:
        """Achado pelo construtor com o clique que deixa a ação rodar, do portão do teclado da suíte
        (fase 5, ciclo 8): depois de um clique na caixa -- o clique engolido do portão na «Verdade da
        linha» -- o ponteiro saiu da janela, e o Qt offscreen não manda o evento de saída: a caixa
        ficou com a marca «sob o mouse». O clique seguinte numa linha da lista manda o foco à caixa no
        pressionar, e a guarda que perguntava o `underMouse` da caixa tomava esse foco pelo do próprio
        clique: a caixa ficava meio à vista. A guarda pergunta a razão do foco (o `setFocus()` do
        programa não é o do mouse): a caixa aparece inteira depois do soltar. E o Tab que vem de fora
        da rolagem para uma caixa de escolha sob o ponteiro parado rola até ela. A sabotagem: a guarda
        do ponteiro, a da primeira versão do ciclo 8 -- a caixa fica meio à vista, a caixa de escolha
        com 9 px."""
        from PyQt6.QtWidgets import QComboBox, QListWidget

        linhas = QListWidget(self.conteudo)
        linhas.addItems(["linha 1", "linha 2", "linha 3"])
        linhas.setFixedHeight(90)
        pele = QComboBox(self.conteudo)
        pele.addItems(["Foco", "Fita", "Clássica"])
        layout = self.conteudo.layout()
        assert layout is not None
        layout.insertWidget(0, linhas)  # type: ignore[attr-defined]
        layout.insertWidget(12, pele)  # type: ignore[attr-defined]
        QWidget.setTabOrder(self.botao, pele)
        # os painéis: a linha escolhida no pressionar manda o foco à verdade
        linhas.currentRowChanged.connect(lambda _r: self.caixa.setFocus(Qt.FocusReason.OtherFocusReason))
        for _vez in range(2):  # o layout cresce o conteúdo, depois a rolagem o toma
            self.app.processEvents()
        alca = self.janela.windowHandle()
        assert alca is not None
        barra = self.rolagem.verticalScrollBar()

        def clicar_a_linha_com_a_marca_velha() -> None:
            # o ponteiro sobre a caixa, depois fora da janela: sem o evento de saída no offscreen
            barra.setValue(barra.maximum())
            self.app.processEvents()
            QTest.mouseMove(alca, self.caixa.mapTo(self.janela, QPoint(8, 8)))
            QTest.mouseMove(alca, QPoint(-20, -20))
            self.app.processEvents()
            self.assertTrue(self.caixa.underMouse(), "a marca velha que o portão deixa")
            linhas.setCurrentRow(0)
            _no_topo(self.rolagem, self.app)
            self.botao.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app.processEvents()
            item = linhas.item(1)
            assert item is not None
            ponto = linhas.viewport().mapTo(self.janela, linhas.visualItemRect(item).center())
            _clique_pela_janela(self.app, self.janela, ponto)
            _sossegar(self.app)
            self.assertIs(self.app.focusWidget(), self.caixa)

        def tab_de_fora_ate_a_caixa_de_escolha_sob_o_ponteiro() -> int:
            # o Tab de fora da rolagem: o de dentro passa pelo focusNextPrevChild dela, que chama o
            # ensureWidgetVisible
            self.botao.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app.processEvents()
            _a_vista_embaixo(self.app, self.rolagem, pele, 9)
            QTest.mouseMove(alca, QPoint(2, 2))
            QTest.mouseMove(alca, pele.mapTo(self.janela, QPoint(8, 4)))
            self.app.processEvents()
            self.assertTrue(pele.underMouse())
            QTest.keyClick(self.botao, Qt.Key.Key_Tab)
            self.app.processEvents()
            self.assertIs(self.app.focusWidget(), pele)
            ret = QRect(pele.mapTo(self.rolagem.viewport(), QPoint(0, 0)), pele.size())
            return ret.intersected(self.rolagem.viewport().rect()).height()

        clicar_a_linha_com_a_marca_velha()
        self.assertTrue(_inteiro(self.rolagem, self.caixa), "o foco do programa aparece quando o mouse sossega")
        self.assertEqual(tab_de_fora_ate_a_caixa_de_escolha_sob_o_ponteiro(), pele.height(), "o Tab a mostra inteira")
        with mock.patch.object(foco_a_vista, "veio_do_mouse", _guarda_do_ponteiro):
            clicar_a_linha_com_a_marca_velha()
            self.assertFalse(_inteiro(self.rolagem, self.caixa), "sabotado, a marca velha esconde o foco do programa")
            self.assertEqual(tab_de_fora_ate_a_caixa_de_escolha_sob_o_ponteiro(), 9, "sabotado, o Tab a deixa com 9 px")


    def _lista_no_alto(self) -> QListWidget:
        """Uma lista de três linhas no alto da rolagem, cuja linha escolhida no pressionar manda o foco
        à caixa do fim -- as tabelas da Rotulagem e da Revisão de texto e a «Verdade da linha»; os
        campos com nome, para dizer onde um clique caiu."""
        for k, campo in enumerate(self.conteudo.findChildren(QLineEdit)):
            campo.setObjectName(f"campo {k}")
        linhas = QListWidget(self.conteudo)
        linhas.addItems(["linha 1", "linha 2", "linha 3"])
        linhas.setFixedHeight(90)
        layout = self.conteudo.layout()
        assert layout is not None
        layout.insertWidget(0, linhas)  # type: ignore[attr-defined]
        linhas.currentRowChanged.connect(lambda _r: self.caixa.setFocus(Qt.FocusReason.OtherFocusReason))
        for _vez in range(2):  # o layout cresce o conteúdo, depois a rolagem o toma
            self.app.processEvents()
        return linhas

    def _na_linha(self, linhas: QListWidget) -> QPoint:
        """A lista na primeira linha, a rolagem no topo, o foco fora: um ponto da segunda linha."""
        linhas.setCurrentRow(0)
        _no_topo(self.rolagem, self.app)
        self.botao.setFocus(Qt.FocusReason.OtherFocusReason)
        self.app.processEvents()
        item = linhas.item(1)
        assert item is not None
        return linhas.viewport().mapTo(self.janela, linhas.visualItemRect(item).center())

    def test_o_segundo_clique_de_um_duplo_clique_cai_onde_o_primeiro_caiu(self) -> None:
        """Crítico da fase 5, ciclo 8: a rolagem que mostrava o foco que o programa moveu no clique vinha
        logo depois do soltar e mexia o conteúdo debaixo do ponteiro parado antes do segundo clique de
        um duplo clique -- na Rotulagem, com a rolagem no fim, o segundo clique na linha 4 caía em
        «Aceitar leitura» e aceitava uma leitura que ninguém aceitou. Aqui o duplo clique pelo
        `QWindow` na segunda linha da lista (pressionar, soltar, 80 ms, o segundo pressionar e soltar
        no mesmo ponto): nada se mexe debaixo do ponteiro entre os dois cliques, os dois caem na lista,
        que recebe o duplo clique naquela linha -- e manda o foco à caixa, como o duplo clique na linha
        da Rotulagem --; e, sossegado o mouse, a caixa aparece inteira. A sabotagem: a rolagem logo
        depois do soltar (o intervalo do duplo clique a 0) -- o conteúdo se mexe, e o segundo clique cai
        fora da lista."""
        from PyQt6.QtCore import QEvent, QObject

        linhas = self._lista_no_alto()
        duplos: list[int] = []
        linhas.doubleClicked.connect(lambda indice: duplos.append(indice.row()))
        linhas.doubleClicked.connect(lambda _i: self.caixa.setFocus(Qt.FocusReason.OtherFocusReason))

        class Receptores(QObject):
            """O primeiro controle a que cada pressionar é entregue."""

            def __init__(self) -> None:
                super().__init__()
                self.controles: list[QWidget] = []
                self._visto = False

            def eventFilter(self, objeto: QObject | None, evento: QEvent | None) -> bool:  # noqa: N802 - Qt
                tipo = evento.type() if evento is not None else None
                if tipo == QEvent.Type.MouseButtonPress and isinstance(objeto, QWidget) and not self._visto:
                    self.controles.append(objeto)
                    self._visto = True
                elif tipo == QEvent.Type.MouseButtonRelease:
                    self._visto = False
                return False

        receptores = Receptores()
        self.app.installEventFilter(receptores)
        self.addCleanup(self.app.removeEventFilter, receptores)

        def duplo_clique() -> tuple[QWidget | None, QWidget | None]:
            duplos.clear()
            receptores.controles.clear()
            ponto = self._na_linha(linhas)
            self.assertTrue(self.caixa.visibleRegion().isEmpty(), "a caixa começa abaixo da dobra")
            sob = self.janela.childAt(ponto)
            _clique_pela_janela(self.app, self.janela, ponto)
            QTest.qWait(80)  # o tempo entre os dois cliques de um duplo clique
            sob_no_segundo = self.janela.childAt(ponto)
            _segundo_clique_de_um_duplo(self.app, self.janela, ponto)
            _sossegar(self.app)
            return sob, sob_no_segundo

        sob, sob_no_segundo = duplo_clique()
        self.assertIs(sob_no_segundo, sob, "nada se mexe debaixo do ponteiro entre os dois cliques")
        self.assertEqual(receptores.controles, [linhas.viewport()] * 2, "os dois pressionares na lista")
        self.assertEqual(duplos, [1], "a lista recebe o duplo clique na segunda linha")
        self.assertTrue(_inteiro(self.rolagem, self.caixa), "sossegado o mouse, a caixa aparece inteira")
        with mock.patch.object(foco_a_vista, "intervalo_do_duplo_clique", lambda: 0):
            sob, sob_no_segundo = duplo_clique()
        self.assertIsNot(sob_no_segundo, sob, "sabotado, o conteúdo se mexeu debaixo do ponteiro")
        self.assertEqual(duplos, [], "sabotado, a lista não recebe o duplo clique")
        self.assertIsNot(receptores.controles[1], linhas.viewport(), "sabotado, o segundo clique cai fora")

    def test_uma_tecla_mostra_na_hora_o_foco_que_espera(self) -> None:
        """O foco que o programa moveu no clique espera o mouse sossegar -- ou a primeira tecla: quem
        clica na linha e digita logo vê a caixa antes de a letra chegar, e a letra entra na caixa à
        vista. Um modificador sozinho (o Shift antes de um Shift+clique) não a mostra. A sabotagem:
        toda tecla tomada por modificador -- a letra entra na caixa abaixo da dobra."""
        linhas = self._lista_no_alto()

        class TodasModificam:
            def __contains__(self, _tecla: object) -> bool:
                return True

        def clique_e_tecla() -> tuple[bool, bool, bool]:
            self.caixa.setPlainText("")
            _clique_pela_janela(self.app, self.janela, self._na_linha(linhas))
            self.assertIs(self.app.focusWidget(), self.caixa)
            QTest.keyClick(self.caixa, Qt.Key.Key_Shift)
            self.app.processEvents()
            so_o_modificador = self.caixa.visibleRegion().isEmpty()
            QTest.keyClicks(self.caixa, "X")
            self.app.processEvents()
            return so_o_modificador, _inteiro(self.rolagem, self.caixa), self.caixa.toPlainText() == "X"

        so_o_modificador, inteira, digitado = clique_e_tecla()
        self.assertTrue(so_o_modificador, "o Shift sozinho não mostra a caixa")
        self.assertTrue(inteira, "a primeira tecla mostra a caixa antes de a letra chegar")
        self.assertTrue(digitado)
        _sossegar(self.app)
        with mock.patch.object(foco_a_vista, "_MODIFICADORES", TodasModificam()):
            _so, inteira, digitado = clique_e_tecla()
        self.assertFalse(inteira, "sabotado, a letra entra na caixa abaixo da dobra")
        self.assertTrue(digitado)
        _sossegar(self.app)

    def test_a_roda_durante_a_espera_fica_e_a_primeira_tecla_mostra_a_caixa(self) -> None:
        """Crítico da fase 5, ciclo 9 (não bloqueante 3): o clique numa linha manda o foco à caixa abaixo
        da dobra, que espera o mouse sossegar; a roda 100 ms depois do clique levava a barra, e no
        sossego o seguidor a trazia de volta para a caixa -- a roda da pessoa desfeita. Aqui, depois do
        clique, um passo da barra para baixo (a ação da roda): no sossego a barra está onde a pessoa a
        deixou, e a caixa não é mostrada; a primeira tecla a mostra, e a letra entra nela. A sabotagem: o
        seguidor surdo à rolagem da pessoa -- no sossego a barra vai à caixa."""
        from PyQt6.QtWidgets import QAbstractSlider

        linhas = self._lista_no_alto()
        barra = self.rolagem.verticalScrollBar()
        assert barra is not None

        def roda_na_espera() -> tuple[int, int, bool, bool]:
            self.caixa.setPlainText("")
            _clique_pela_janela(self.app, self.janela, self._na_linha(linhas))
            self.assertIs(self.app.focusWidget(), self.caixa)
            barra.triggerAction(QAbstractSlider.SliderAction.SliderSingleStepAdd)
            self.app.processEvents()
            rolou = barra.value()
            _sossegar(self.app)
            depois = barra.value()
            escondida = not _inteiro(self.rolagem, self.caixa)
            QTest.keyClick(self.caixa, Qt.Key.Key_X)
            self.app.processEvents()
            mostrada = _inteiro(self.rolagem, self.caixa) and self.caixa.toPlainText() == "x"
            return rolou, depois, escondida, mostrada

        rolou, depois, escondida, mostrada = roda_na_espera()
        self.assertGreater(rolou, 0)
        self.assertEqual(depois, rolou, "no sossego a barra está onde a pessoa a deixou")
        self.assertTrue(escondida, "a caixa não é trazida de volta")
        self.assertTrue(mostrada, "a primeira tecla mostra a caixa, e a letra entra nela")
        _sossegar(self.app)
        barra.actionTriggered.disconnect(self.seguidor._a_pessoa_rolou)
        rolou, depois, _escondida, _mostrada = roda_na_espera()
        self.assertNotEqual(depois, rolou, "sabotado, no sossego o seguidor leva a barra à caixa")

    def test_o_foco_que_o_programa_move_no_soltar_tambem_espera(self) -> None:
        """Um botão dentro da rolagem cujo `clicked` -- no soltar -- manda o foco à caixa do fim: o botão
        não está mais apertado, mas o segundo clique de um duplo clique nele ainda vem. Logo depois do
        soltar nada se mexe debaixo do ponteiro; sossegado o mouse, a caixa aparece inteira. A
        sabotagem: o intervalo do duplo clique a 0 -- a rolagem vem na hora, e o botão sai de baixo do
        ponteiro."""
        proxima = QPushButton("Próxima", self.conteudo)
        layout = self.conteudo.layout()
        assert layout is not None
        layout.insertWidget(0, proxima)  # type: ignore[attr-defined]
        proxima.clicked.connect(lambda: self.caixa.setFocus(Qt.FocusReason.OtherFocusReason))
        for _vez in range(2):  # o layout cresce o conteúdo, depois a rolagem o toma
            self.app.processEvents()

        def clique_no_botao() -> QWidget | None:
            _no_topo(self.rolagem, self.app)
            self.botao.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app.processEvents()
            ponto = proxima.mapTo(self.janela, proxima.rect().center())
            _clique_pela_janela(self.app, self.janela, ponto)
            for _vez in range(3):
                self.app.processEvents()
            self.assertIs(self.app.focusWidget(), self.caixa)
            return self.janela.childAt(ponto)

        self.assertIs(clique_no_botao(), proxima, "logo depois do soltar, o botão ainda está sob o ponteiro")
        _sossegar(self.app)
        self.assertTrue(_inteiro(self.rolagem, self.caixa), "sossegado o mouse, a caixa aparece inteira")
        with mock.patch.object(foco_a_vista, "intervalo_do_duplo_clique", lambda: 0):
            self.assertIsNot(clique_no_botao(), proxima, "sabotado, a rolagem na hora tira o botão dali")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RolagensDoProdutoTests(unittest.TestCase):
    """As três rolagens do tronco que o Tab alcança de fora, com a tecla e a rolagem no topo."""

    def setUp(self) -> None:
        self.app = aplicacao()
        _mouse_sossegado_desde_ja()
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


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DialogoDeBasesTests(unittest.TestCase):
    """O diálogo «Base de partidas» morre com a pergunta, e o seguidor da lista dele com ele."""

    def setUp(self) -> None:
        self.app = aplicacao()
        _mouse_sossegado_desde_ja()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def test_o_seguidor_da_rolagem_destruida_nao_pergunta_nada_a_ela(self) -> None:
        """Achado pelo construtor (fase 5, ciclo 8) com a sonda da rolagem morta do crítico: a
        rolagem destruída com o foco dentro -- o diálogo de bases depois da pergunta -- limpa o foco no
        destrutor, quando a rolagem já se foi e o seguidor, filho dela, ainda não; a primeira versão do
        ciclo 8 perguntava à rolagem morta pelo conteúdo antes de perguntar se havia foco novo:
        «wrapped C/C++ object of type QScrollArea has been deleted», 20 vezes em 20 perguntas, e um
        access violation no fim. O seguidor pergunta primeiro se há foco novo e se a rolagem vive. A
        sabotagem: a ordem daquela primeira versão."""
        import sys

        from PyQt6.QtCore import QCoreApplication, QEvent

        from chess_diagram_ocr.qt.foco_a_vista import RolagemSegueOFoco

        def montar_e_destruir() -> None:
            janela = QWidget()
            self.addCleanup(descartar, janela)
            coluna = QVBoxLayout(janela)
            rolagem = QScrollArea(janela)
            conteudo = QWidget(rolagem)
            campo = QLineEdit(conteudo)
            QVBoxLayout(conteudo).addWidget(campo)
            rolagem.setWidget(conteudo)
            coluna.addWidget(rolagem)
            RolagemSegueOFoco(rolagem)
            janela.show()
            self.app.processEvents()
            campo.setFocus()
            self.app.processEvents()
            self.assertIs(self.app.focusWidget(), campo)
            rolagem.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
            self.app.processEvents()

        erros: list[str] = []

        def anotar(tipo: type[BaseException], valor: BaseException, _tb: object) -> None:
            erros.append(f"{tipo.__name__}: {valor}")

        with mock.patch.object(sys, "excepthook", anotar):
            montar_e_destruir()
        self.assertEqual(erros, [])

        def primeira_versao(seguidor: RolagemSegueOFoco, _antigo: QWidget | None, novo: QWidget | None) -> None:
            conteudo = seguidor._rolagem.widget()  # antes de perguntar se há foco novo
            if (not seguidor._ligado or novo is None or conteudo is None or not conteudo.isAncestorOf(novo)
                    or foco_a_vista.veio_do_mouse(novo)):
                return
            foco_a_vista.mostrar(seguidor._rolagem, novo)

        with (mock.patch.object(sys, "excepthook", anotar),
              mock.patch.object(RolagemSegueOFoco, "_foco_mudou", primeira_versao)):
            montar_e_destruir()
        self.assertTrue(any("has been deleted" in erro for erro in erros), ("sabotado", erros))

    def test_vinte_perguntas_nao_deixam_seguidores_vivos(self) -> None:
        """O crítico da fase 5 (ciclo 6): cada abertura podia deixar um diálogo filho da janela, com
        o seguidor ligado à aplicação -- 7 → 16 seguidores em 20 aberturas (quantos sobram varia:
        o Qt recolhe alguns por conta própria). Com a pergunta, nenhum sobra. A sabotagem: o
        diálogo que não morre, e os seguidores ficam."""
        from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer
        from PyQt6.QtWidgets import QApplication

        for k in range(3):
            (self.pasta / f"base_{k}.pgn").write_bytes(b"x" * 1000)
        janela = QWidget()
        self.addCleanup(descartar, janela)
        janela.show()

        def seguidores() -> int:
            return sum(1 for o in janela.findChildren(QObject) if type(o).__name__ == "RolagemSegueOFoco")

        def perguntar_vinte_vezes() -> None:
            for _ in range(20):
                QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
                qt_dialogos.perguntar_bases(janela, folder=self.pasta, nota=lambda _bases: "")
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.app.processEvents()

        perguntar_vinte_vezes()
        self.assertEqual(seguidores(), 0)
        with mock.patch.object(qt_dialogos.DialogoDeBases, "deleteLater", lambda _self: None):
            perguntar_vinte_vezes()
        self.assertGreater(seguidores(), 0, "sabotado, os seguidores das perguntas ficam vivos")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class CliqueNosModosTests(unittest.TestCase):
    """Os dois cliques que o crítico da fase 5 (ciclo 6) mediu na pele Foco a 1280x641, com o
    controle cortado pela borda de baixo da rolagem dos modos da aba Livro: o tabuleiro do Estudo
    com 13 px abaixo da dobra, e o rádio «Pretas» do Resultado com 9 de 22 px à vista."""

    def setUp(self) -> None:
        self.app = aplicacao()
        _mouse_sossegado_desde_ja()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

    def _no_modo(self, nome: str, painel: QWidget, altura: int) -> tuple[QWidget, QScrollArea]:
        janela = QWidget()
        self.addCleanup(descartar, janela)
        coluna = QVBoxLayout(janela)
        principal = PainelPrincipal(janela)
        principal.adicionar_modo(nome, painel)
        coluna.addWidget(principal, 1)
        fora = QPushButton("Abrir PDF", janela)
        coluna.addWidget(fora)
        janela.resize(1000, altura)
        janela.show()
        self.app.processEvents()
        rolagem = principal.findChild(QScrollArea)
        assert rolagem is not None
        return janela, rolagem

    def test_o_clique_na_casa_e7_so_seleciona_o_peao(self) -> None:
        """Depois de 1.e4, com o foco no campo da FEN, um clique na parte de baixo da casa e7 --
        para selecionar o peão -- rolava 19 px no pressionar, e o soltar, já na e6, jogava 1...e6.
        O tabuleiro completa o lance no soltar, na casa sob o ponteiro. Sabotado, o lance volta."""
        import chess

        from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo

        for sabotado in (False, True):
            estudo = PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
            janela, rolagem = self._no_modo("Estudo", estudo, 420)
            estudo.push_move(chess.Move.from_uci("e2e4"))
            self.app.processEvents()
            tabuleiro = estudo.tabuleiro
            estudo.campo_fen.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app.processEvents()
            _a_vista_embaixo(self.app, rolagem, tabuleiro, tabuleiro.height() - 13)
            antes = rolagem.verticalScrollBar().value()
            geo = tabuleiro.geometria()
            ponto = tabuleiro.mapTo(janela, QPoint(int(geo.origin_x + 4.5 * geo.cell),
                                                   int(geo.origin_y + 2 * geo.cell) - 3))
            with _sem_a_guarda_do_mouse() if sabotado else contextlib.nullcontext():
                _clique_pela_janela(self.app, janela, ponto)
            lances = [lance.uci() for lance in estudo.estudo.tabuleiro.move_stack]
            if sabotado:
                self.assertEqual(lances, ["e2e4", "e7e6"], "sabotado, o lance fantasma volta")
            else:
                self.assertEqual(lances, ["e2e4"], "um clique só seleciona")
                self.assertEqual(rolagem.verticalScrollBar().value(), antes)
                self.assertIsNotNone(tabuleiro.selecionada(), "o peão está selecionado")

    def test_o_clique_em_pretas_marca_pretas(self) -> None:
        """O lado a jogar da posição lida: o clique rolava 19 px e o rádio não marcava; quem salva
        sem conferir grava a FEN com a vez errada. Sabotado, o clique se perde de novo."""
        import numpy as np

        from chess_diagram_ocr.qt.painel_de_resultado import PainelDeResultado
        from chess_diagram_ocr.service import RecognizedDiagram

        for sabotado in (False, True):
            # um item novo em cada volta: o rádio escreve o lado no item carregado
            lido = RecognizedDiagram(index=0, board_rgb=np.full((64, 64, 3), 200, np.uint8),
                                     placement="4k3/8/8/8/8/8/8/4K3", min_confidence=0.93,
                                     square_confidences=[0.99] * 64, side_to_move="w", probs=None)
            painel = PainelDeResultado(mock.MagicMock(), csv_de_rotulos=self.pasta / "l.csv")
            painel.carregar_pagina([lido], chave="livro.pdf", pagina=0)
            janela, rolagem = self._no_modo("Resultado", painel, 360)
            pretas = next(b for b in painel._lados.buttons() if b.property("lado") == "b")
            self.assertTrue(pretas.isEnabled() and not pretas.isChecked())
            _a_vista_embaixo(self.app, rolagem, pretas, 9)
            ponto = pretas.mapTo(janela, QPoint(8, 6))
            with _sem_a_guarda_do_mouse() if sabotado else contextlib.nullcontext():
                _clique_pela_janela(self.app, janela, ponto)
            if sabotado:
                self.assertFalse(pretas.isChecked(), "sabotado, o clique se perde")
            else:
                self.assertTrue(pretas.isChecked())


if __name__ == "__main__":
    unittest.main()
