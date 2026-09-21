"""O tabuleiro que se corrige, no Qt (S-20/S-49/S-502).

**O que estes testes cobrem, e o que não.** O que cada gesto *significa* -- `press`, `drop`,
`paint`, `erase`, e o que cada um devolve em `BoardChange` -- é de `ui/board_model.py`, é puro, e
já é afirmado em `tests/test_board_model.py`. As operações sobre o campo de peças são de
`ui/board_edit.py` e estão em `tests/test_board_edit.py`. Repetir qualquer um dos dois aqui
mediria o mesmo código duas vezes.

O que só existe deste lado é o **roteamento**: clique do Qt virando chamada do modelo, e o que o
modelo respondeu virando pixel e sinal. É onde um porte erra em silêncio -- um `mouseReleaseEvent`
que esquece `allow_deselect` faz selecionar exigir dois cliques, e nada levanta.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import board_edit

if TEM_PYQT:
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QWidget

    from chess_diagram_ocr.qt.tabuleiro_editavel import LIMIAR_DE_ARRASTO, TabuleiroEditavel

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
VAZIO = "8/8/8/8/8/8/8/8"


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TabuleiroEditavelTests(unittest.TestCase):
    """O roteamento do gesto para o modelo, e de volta para a tela."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.tabuleiro = TabuleiroEditavel()
        self.addCleanup(self.tabuleiro.deleteLater)
        self.tabuleiro.resize(400, 400)
        self.tabuleiro.show()
        self.app.processEvents()
        self.tabuleiro.mostrar(INICIAL)

        self.posicoes: list[str] = []
        self.selecoes: list[object] = []
        self.tabuleiro.posicao_mudou.connect(self.posicoes.append)
        self.tabuleiro.selecao_mudou.connect(self.selecoes.append)

    # ------------------------------------------------------------------ gestos, em pixel

    def centro(self, indice: int) -> QPoint:
        """O centro da casa, em pixel do widget. Perguntado à geometria, não recalculado."""
        linha, coluna = self.tabuleiro.modelo.display_from_index(indice)
        x0, y0, x1, y1 = self.tabuleiro.geometria().rect(linha, coluna)
        return QPoint(int((x0 + x1) / 2), int((y0 + y1) / 2))

    def _evento(self, tipo: QEvent.Type, ponto: QPoint, botao: Qt.MouseButton) -> QMouseEvent:
        return QMouseEvent(tipo, QPointF(ponto), botao, botao, Qt.KeyboardModifier.NoModifier)

    def clicar(self, indice: int, *, botao: Qt.MouseButton = Qt.MouseButton.LeftButton) -> None:
        ponto = self.centro(indice)
        self.tabuleiro.mousePressEvent(self._evento(QEvent.Type.MouseButtonPress, ponto, botao))
        self.tabuleiro.mouseReleaseEvent(self._evento(QEvent.Type.MouseButtonRelease, ponto, botao))

    def arrastar(self, de: int, para: int) -> None:
        """Pressiona, anda o bastante para passar do limiar, e solta."""
        origem, destino = self.centro(de), self.centro(para)
        self.tabuleiro.mousePressEvent(
            self._evento(QEvent.Type.MouseButtonPress, origem, Qt.MouseButton.LeftButton)
        )
        self.tabuleiro.mouseMoveEvent(
            self._evento(QEvent.Type.MouseMove, destino, Qt.MouseButton.LeftButton)
        )
        self.tabuleiro.mouseReleaseEvent(
            self._evento(QEvent.Type.MouseButtonRelease, destino, Qt.MouseButton.LeftButton)
        )

    # ------------------------------------------------------------------------ seleção

    def test_clicar_numa_peca_a_seleciona(self) -> None:
        self.clicar(0)  # a8, a torre preta
        self.assertEqual(self.tabuleiro.selecionada(), 0)
        self.assertEqual(self.selecoes[-1], 0)

    def test_um_clique_seleciona_e_nao_desmarca_no_mesmo_gesto(self) -> None:
        """**O `allow_deselect` do `drop`, e o que ele evita.**

        `mousePressEvent` seleciona e `mouseReleaseEvent` chama `drop`. Sem a guarda, o mesmo
        clique que selecionou desmarcaria, e selecionar passaria a exigir dois cliques -- que é
        o tipo de defeito que não levanta e que quem usa descreve como "o tabuleiro está lento".
        """
        self.clicar(0)
        self.assertEqual(self.tabuleiro.selecionada(), 0)

    def test_clicar_de_novo_na_mesma_casa_desmarca(self) -> None:
        self.clicar(0)
        self.clicar(0)
        self.assertIsNone(self.tabuleiro.selecionada())

    def test_clicar_fora_do_tabuleiro_nao_levanta(self) -> None:
        fora = QPoint(2, 2)
        self.tabuleiro.mousePressEvent(
            self._evento(QEvent.Type.MouseButtonPress, fora, Qt.MouseButton.LeftButton)
        )
        self.tabuleiro.mouseReleaseEvent(
            self._evento(QEvent.Type.MouseButtonRelease, fora, Qt.MouseButton.LeftButton)
        )

    # ------------------------------------------------------------------------ correção

    def test_arrastar_move_a_peca_e_avisa(self) -> None:
        self.arrastar(48, 40)  # a2 -> a3, o peão branco
        posicao = self.tabuleiro.posicao()
        self.assertEqual(board_edit.piece_at(posicao, 40), "P")
        self.assertEqual(board_edit.piece_at(posicao, 48), "")
        self.assertEqual(self.posicoes[-1], posicao)

    def test_o_botao_direito_apaga(self) -> None:
        """Tirar peça é metade das correções: pedir "selecione e aperte Del" são dois gestos
        onde um basta."""
        self.clicar(0, botao=Qt.MouseButton.RightButton)
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 0), "")
        self.assertTrue(self.posicoes)

    def test_o_pincel_deposita_a_peca_no_clique(self) -> None:
        self.tabuleiro.mostrar(VAZIO)
        self.tabuleiro.definir_pincel("Q")
        self.clicar(27)  # d5
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 27), "Q")

    def test_o_pincel_manda_a_frase_de_status_por_sinal(self) -> None:
        """É o `self._status(mensagem)` de `board_widget.set_brush`, com sinal no lugar da
        chamada -- e a frase vem do modelo, que é quem sabe dizer "dama branca"."""
        recados: list[str] = []
        self.tabuleiro.recado.connect(recados.append)
        self.assertEqual(self.tabuleiro.definir_pincel("Q"), "Q")
        self.assertIn("dama branca", recados[-1])
        self.assertIsNone(self.tabuleiro.definir_pincel(None))
        self.assertIn("desligado", recados[-1])

    def test_o_pincel_nao_alterna_aqui(self) -> None:
        """Largar o pincel clicando no botão aceso é gesto de **paleta**, e no Tk mora em
        `board_widget._on_palette_click`. Duas regras para a mesma pergunta divergiriam."""
        self.assertEqual(self.tabuleiro.definir_pincel("Q"), "Q")
        self.assertEqual(self.tabuleiro.definir_pincel("Q"), "Q")

    def test_apagar_a_selecionada(self) -> None:
        self.clicar(0)
        self.assertTrue(self.tabuleiro.apagar_selecionada())
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 0), "")

    def test_apagar_sem_selecao_devolve_falso(self) -> None:
        self.assertFalse(self.tabuleiro.apagar_selecionada())

    def test_a_correcao_de_peca_inexistente_nao_muda_nada(self) -> None:
        """Arrastar de casa vazia não é erro do usuário: é o gesto de quem errou o alvo."""
        antes = self.tabuleiro.posicao()
        self.arrastar(32, 40)  # a5 -> a3, as duas vazias
        self.assertEqual(self.tabuleiro.posicao(), antes)

    # ------------------------------------------------------------------------- desenho

    def test_a_peca_arrastada_some_da_casa_de_origem(self) -> None:
        """Ela aparece sob o ponteiro; desenhá-la também na origem a mostraria duas vezes.

        É o gancho `_classe_da_casa` que a base expõe, e este é o teste que o justifica.
        """
        origem, destino = self.centro(48), self.centro(40)
        self.tabuleiro.mousePressEvent(
            self._evento(QEvent.Type.MouseButtonPress, origem, Qt.MouseButton.LeftButton)
        )
        self.tabuleiro.mouseMoveEvent(
            self._evento(QEvent.Type.MouseMove, destino, Qt.MouseButton.LeftButton)
        )
        self.assertEqual(self.tabuleiro._classe_da_casa(48), "empty")
        self.assertEqual(self.tabuleiro._classes[48], "P", "a base não podia ter sido alterada")

    def test_o_arrasto_curto_demais_nao_conta(self) -> None:
        """Pequeno demais e todo clique vira arrasto de um pixel, e a peça pisca."""
        origem = self.centro(48)
        casa = self.tabuleiro.geometria().cell
        perto = QPoint(origem.x() + int(casa * LIMIAR_DE_ARRASTO / 2), origem.y())
        self.tabuleiro.mousePressEvent(
            self._evento(QEvent.Type.MouseButtonPress, origem, Qt.MouseButton.LeftButton)
        )
        self.tabuleiro.mouseMoveEvent(
            self._evento(QEvent.Type.MouseMove, perto, Qt.MouseButton.LeftButton)
        )
        self.assertFalse(self.tabuleiro._arrastando)

    def test_as_marcas_acesas_sao_as_pedidas(self) -> None:
        self.tabuleiro.definir_casas_corrigidas([5, 12])
        self.tabuleiro.definir_casas_problematicas([4])
        self.clicar(0)
        self.assertEqual(
            self.tabuleiro.casas_marcadas(),
            {"selecionada": (0,), "apontada": (), "corrigidas": (5, 12), "problematicas": (4,),
             "disputadas": ()},   # C3: a segunda opinião ainda não leu
        )

    def test_desenhar_com_marcas_e_arrasto_nao_levanta(self) -> None:
        """O `paintEvent` inteiro, com tudo aceso ao mesmo tempo."""
        self.tabuleiro.definir_casas_corrigidas([5])
        self.tabuleiro.definir_casas_problematicas([4])
        self.clicar(0)
        self.tabuleiro.mousePressEvent(
            self._evento(QEvent.Type.MouseButtonPress, self.centro(48), Qt.MouseButton.LeftButton)
        )
        self.tabuleiro.mouseMoveEvent(
            self._evento(QEvent.Type.MouseMove, self.centro(40), Qt.MouseButton.LeftButton)
        )
        self.assertFalse(self.tabuleiro.grab().isNull())

    # -------------------------------------------------------------------------- o giro

    def test_virar_move_o_clique_junto_com_a_peca(self) -> None:
        """**Duas fontes de verdade para "virado" dariam um tabuleiro que desenha em cima e
        acerta embaixo.** A base guarda `_virado` e o modelo guarda `flipped`.
        """
        self.tabuleiro.mostrar(INICIAL, virado=True)
        self.assertTrue(self.tabuleiro.modelo.flipped)
        self.clicar(0)  # a8 continua sendo a8, mas agora fica no canto de baixo
        self.assertEqual(self.tabuleiro.selecionada(), 0)

    def test_a_geometria_e_o_modelo_concordam_sobre_a_casa(self) -> None:
        for virado in (False, True):
            self.tabuleiro.mostrar(INICIAL, virado=virado)
            for indice in (0, 7, 27, 56, 63):
                with self.subTest(virado=virado, casa=indice):
                    self.assertEqual(self.tabuleiro._casa_em(self.centro(indice)), indice)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TecladoTests(unittest.TestCase):
    """OCR_UI ciclo 2, passo C8: corrigir uma casa pelo teclado em duas teclas.

    `Tab` vai à duvidosa, a letra põe a peça (Shift = branca), `Delete` esvazia, as setas andam.
    A regra mora em `ui/teclado_do_tabuleiro`; aqui é o widget recebendo a tecla de verdade.
    """

    def setUp(self) -> None:
        from PyQt6.QtTest import QTest

        self.QTest = QTest
        self.app = aplicacao()
        self.tabuleiro = TabuleiroEditavel()
        self.addCleanup(self.tabuleiro.deleteLater)
        self.tabuleiro.resize(400, 400)
        self.tabuleiro.show()
        self.app.processEvents()
        self.tabuleiro.mostrar(INICIAL)

    def tecla(self, chave, modificador=Qt.KeyboardModifier.NoModifier, texto: str = "") -> None:
        self.QTest.keyClick(self.tabuleiro, chave, modificador) if not texto else self.QTest.keyClick(
            self.tabuleiro, texto, modificador)
        self.app.processEvents()

    def test_o_tabuleiro_aceita_foco(self) -> None:
        self.assertEqual(self.tabuleiro.focusPolicy(), Qt.FocusPolicy.StrongFocus)

    def test_tab_vai_a_duvidosa_e_a_letra_poe_a_peca_em_duas_teclas(self) -> None:
        # a8 é o índice 0 na ordem de leitura; a torre preta está lá na posição inicial.
        self.tabuleiro.definir_duvidosas([0, 12])
        self.tecla(Qt.Key.Key_Tab)
        self.assertEqual(self.tabuleiro.selecionada(), 0)
        self.tecla(Qt.Key.Key_Q, texto="q")
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 0), "q")
        # Shift + letra: a branca.
        self.tecla(Qt.Key.Key_Tab)
        self.assertEqual(self.tabuleiro.selecionada(), 12)
        self.tecla(Qt.Key.Key_N, Qt.KeyboardModifier.ShiftModifier, texto="N")
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 12), "N")
        # ...e o Tab dá a volta.
        self.tecla(Qt.Key.Key_Tab)
        self.assertEqual(self.tabuleiro.selecionada(), 0)

    def test_sem_duvidosas_o_tab_percorre_as_ocupadas(self) -> None:
        self.tecla(Qt.Key.Key_Tab)
        self.assertEqual(self.tabuleiro.selecionada(), 0)
        self.tecla(Qt.Key.Key_Tab)
        self.assertEqual(self.tabuleiro.selecionada(), 1)
        self.tecla(Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.tabuleiro.selecionada(), 0)

    def test_setas_andam_e_delete_esvazia(self) -> None:
        self.tabuleiro.selecionar_casa(8)   # a7, um peão preto
        self.tecla(Qt.Key.Key_Right)
        self.assertEqual(self.tabuleiro.selecionada(), 9)
        self.tecla(Qt.Key.Key_Down)
        self.assertEqual(self.tabuleiro.selecionada(), 17)
        self.tecla(Qt.Key.Key_Up)
        self.tecla(Qt.Key.Key_Left)
        self.assertEqual(self.tabuleiro.selecionada(), 8)
        self.tecla(Qt.Key.Key_Delete)
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 8), "")

    def _guarda_de_atalhos(self, chamadas: list[str]):
        """A guarda de atalhos da janela, ligada na aplicação como `qt/janela.py` a liga.

        É a condição real: `←`/`→`/`Del` são atalhos globais, e a guarda vê a tecla **antes** do
        widget em foco. Sem ela o teste do widget sozinho passava e o produto não andava.
        """
        from chess_diagram_ocr.qt import atalhos as atalhos_qt

        dona = QWidget()
        self.addCleanup(dona.deleteLater)
        guarda = atalhos_qt.ligar(
            dona,
            {
                "diagrama_anterior": lambda: chamadas.append("diagrama_anterior"),
                "proximo_diagrama": lambda: chamadas.append("proximo_diagrama"),
                "apagar_casa": lambda: chamadas.append("apagar_casa"),
            },
            aplicacao=self.app,
        )
        self.addCleanup(self.app.removeEventFilter, guarda)
        return guarda

    def test_com_a_guarda_de_atalhos_ligada_as_setas_ainda_andam_no_tabuleiro_em_foco(self) -> None:
        """S-244 aplicada ao tabuleiro: a seta é dele enquanto ele tem o foco; o diagrama vizinho
        fica com os botões e com o foco fora daqui. A sabotagem (o tabuleiro sem `acoes_proprias`)
        é o produto de antes: a guarda entregava a seta à janela e a seleção não saía do lugar."""
        chamadas: list[str] = []
        self._guarda_de_atalhos(chamadas)
        self.tabuleiro.setFocus()
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), self.tabuleiro)

        self.tabuleiro.selecionar_casa(8)
        self.tecla(Qt.Key.Key_Right)
        self.assertEqual(self.tabuleiro.selecionada(), 9, "a seta andou no tabuleiro")
        self.tecla(Qt.Key.Key_Delete)
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 9), "", "o Delete esvaziou aqui")
        self.assertEqual(chamadas, [], "a janela não recebeu a seta nem o Delete")

        # Com o foco fora do tabuleiro a mesma tecla continua sendo o atalho global.
        outro = QWidget()
        self.addCleanup(outro.deleteLater)
        outro.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        outro.show()
        outro.setFocus()
        self.app.processEvents()
        self.QTest.keyClick(outro, Qt.Key.Key_Right)
        self.assertEqual(chamadas, ["proximo_diagrama"])

    def test_sabotagem_sem_tomar_as_acoes_a_guarda_come_a_seta(self) -> None:
        from unittest import mock

        chamadas: list[str] = []
        self._guarda_de_atalhos(chamadas)
        self.tabuleiro.setFocus()
        self.app.processEvents()
        self.tabuleiro.selecionar_casa(8)
        with mock.patch.object(TabuleiroEditavel, "acoes_proprias", lambda self: frozenset()):
            self.tecla(Qt.Key.Key_Right)
        self.assertEqual(self.tabuleiro.selecionada(), 8, "a seleção não saiu do lugar")
        self.assertEqual(chamadas, ["proximo_diagrama"], "a janela ficou com a seta")

    def test_a_letra_nao_muda_o_pincel_da_paleta(self) -> None:
        self.tabuleiro.definir_pincel("R")
        self.tabuleiro.selecionar_casa(8)
        self.tecla(Qt.Key.Key_B, texto="b")
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 8), "b")
        self.assertEqual(self.tabuleiro.modelo.brush, "R")
        # Enter aplica o pincel da paleta.
        self.tecla(Qt.Key.Key_Return)
        self.assertEqual(board_edit.piece_at(self.tabuleiro.posicao(), 8), "R")

    def test_a_regra_sem_toolkit(self) -> None:
        from chess_diagram_ocr.ui import teclado_do_tabuleiro as regra

        self.assertEqual(regra.acao_da_tecla("k").simbolo, "k")
        self.assertEqual(regra.acao_da_tecla("k", shift=True).simbolo, "K")
        self.assertEqual(regra.acao_da_tecla("Tab").passo, 1)
        self.assertEqual(regra.acao_da_tecla("Tab", shift=True).passo, -1)
        self.assertIsNone(regra.acao_da_tecla("x"))
        self.assertEqual(regra.proxima_duvidosa([5, 20, 40], None, 1), 5)
        self.assertEqual(regra.proxima_duvidosa([5, 20, 40], 20, 1), 40)
        self.assertEqual(regra.proxima_duvidosa([5, 20, 40], 40, 1), 5)
        # A ordem é a da lista (a que mais merece o olho primeiro), não a do tabuleiro.
        self.assertEqual(regra.proxima_duvidosa([40, 5, 20], None, 1), 40)
        self.assertEqual(regra.proxima_duvidosa([40, 5, 20], 40, 1), 5)
        self.assertEqual(regra.proxima_duvidosa([5, 20, 40], 21, -1), 40, "fora da lista: a última")
        self.assertIsNone(regra.proxima_duvidosa([], 3, 1))
