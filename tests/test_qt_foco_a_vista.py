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


def _a_vista_embaixo(app: object, rolagem: QScrollArea, controle: QWidget, px: int) -> None:
    """Rola ``rolagem`` até ``controle`` ficar com ``px`` à vista, cortado pela borda de baixo."""
    conteudo = rolagem.widget()
    assert conteudo is not None
    topo = controle.mapTo(conteudo, QPoint(0, 0)).y()
    rolagem.verticalScrollBar().setValue(topo + px - rolagem.viewport().height())
    app.processEvents()  # type: ignore[attr-defined]
    ret = QRect(controle.mapTo(rolagem.viewport(), QPoint(0, 0)), controle.size())
    assert ret.intersected(rolagem.viewport().rect()).height() == px, "a rolagem não chega lá"


def _sem_a_guarda_do_mouse() -> contextlib.AbstractContextManager[object]:
    """A sabotagem: o seguidor rola também no foco que o mouse dá, como no ciclo 6."""
    return mock.patch.object(foco_a_vista, "veio_do_mouse", lambda _controle: False)


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


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DialogoDeBasesTests(unittest.TestCase):
    """O diálogo «Base de partidas» morre com a pergunta, e o seguidor da lista dele com ele."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.addCleanup(self.app.processEvents)

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
