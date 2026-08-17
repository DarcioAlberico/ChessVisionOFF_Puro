"""Clique → arrasta → solta, sem janela (S-50).

O critério de aceite do item. Até aqui, exercitar a interação do tabuleiro exigia um
`tk.Canvas` de verdade, com geometria e eventos sintéticos; agora é chamar três métodos.

E `BoardChange.dirty` -- as casas que precisam ser redesenhadas -- é testado junto, porque
é dele que sai o redesenho parcial: arrastar uma peça toca 2 casas, não 64.
"""

from __future__ import annotations

import unittest

import chess
import numpy as np

from chess_diagram_ocr.config import PIECE_CLASSES, PIECE_TO_IDX
from chess_diagram_ocr.ui.board_model import BoardModel, ChangeKind
from chess_diagram_ocr.ui.board_render import BoardGeometry, heatmap_color

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
REIS = "4k3/8/8/8/8/8/8/4K3"

A8, H8, A1, E1, E8 = 0, 7, 56, 60, 4
E2, E4 = 52, 36


class EditInteractionTests(unittest.TestCase):
    """Modo de edição: clique move sem perguntar de quem é a vez."""

    def setUp(self) -> None:
        self.model = BoardModel(mode="edit")
        self.model.set_position(INICIAL)

    def test_clique_arrasta_solta_move_a_peca(self) -> None:
        self.assertIs(self.model.press(A8).kind, ChangeKind.SELECTION)
        self.assertEqual(self.model.selected, A8)

        mudanca = self.model.drop(A1)
        self.assertIs(mudanca.kind, ChangeKind.PLACEMENT)
        self.assertIsNone(self.model.selected, "soltar tem de limpar a seleção")
        self.assertIn("a8 → a1", mudanca.message)

    def test_arrastar_uma_peca_suja_duas_casas_e_nao_sessenta_e_quatro(self) -> None:
        """A consequência que o item existe para entregar."""
        self.model.press(A8)
        mudanca = self.model.drop(A1)
        # `dirty` traz origem e destino; o resto vem de sinais que a edicao invalida, e este
        # modelo nao tem nenhum ligado.
        self.assertEqual(mudanca.dirty, frozenset({A8, A1}))

    def test_clicar_na_casa_ja_selecionada_deseleciona(self) -> None:
        self.model.press(A8)
        mudanca = self.model.drop(A8, allow_deselect=True)
        self.assertIs(mudanca.kind, ChangeKind.SELECTION)
        self.assertIsNone(self.model.selected)

    def test_o_primeiro_clique_numa_casa_nao_a_deseleciona(self) -> None:
        """`allow_deselect=False` é o que o widget passa quando a seleção acabou de nascer."""
        self.model.press(A8)
        self.assertFalse(self.model.drop(A8, allow_deselect=False))
        self.assertEqual(self.model.selected, A8)

    def test_soltar_fora_do_tabuleiro_cancela_e_diz(self) -> None:
        self.model.press(A8)
        mudanca = self.model.drop(None)
        self.assertIs(mudanca.kind, ChangeKind.MESSAGE)
        self.assertIn("cancelado", mudanca.message)

    def test_clicar_em_casa_vazia_nao_seleciona_nada(self) -> None:
        self.model.set_position(REIS)
        self.assertFalse(self.model.press(A8))
        self.assertIsNone(self.model.selected)

    def test_botao_direito_apaga(self) -> None:
        mudanca = self.model.erase(A8)
        self.assertIs(mudanca.kind, ChangeKind.PLACEMENT)
        self.assertEqual(mudanca.dirty, frozenset({A8}))
        self.assertTrue(self.model.placement.startswith("1nbqkbnr"))

    def test_apagar_casa_vazia_nao_e_mudanca(self) -> None:
        self.model.set_position(REIS)
        self.assertFalse(self.model.erase(A8))


class BrushTests(unittest.TestCase):
    def test_com_pincel_o_clique_pinta_em_vez_de_arrastar(self) -> None:
        model = BoardModel(mode="edit")
        model.set_position(REIS)
        model.set_brush("Q")

        mudanca = model.press(A8)
        self.assertIs(mudanca.kind, ChangeKind.PLACEMENT)
        self.assertIsNone(model.selected, "pincel não seleciona: ele pinta")
        self.assertTrue(model.placement.startswith("Q3k3"))

    def test_pincel_vazio_apaga(self) -> None:
        model = BoardModel(mode="edit")
        model.set_position(INICIAL)
        model.set_brush("")
        self.assertIs(model.press(A8).kind, ChangeKind.PLACEMENT)
        self.assertTrue(model.placement.startswith("1nbqkbnr"))

    def test_clicar_de_novo_na_mesma_peca_apaga(self) -> None:
        """Pôr e tirar viram o mesmo gesto.

        Corrigir leitura de OCR é uma sequência de acertos e desacertos -- põe a torre, vê
        que era o bispo. Sem alternância, desfazer exigia largar o pincel, clicar com o botão
        direito e pegar o pincel de volta: três gestos para desfazer um.
        """
        model = BoardModel(mode="edit")
        model.set_position(REIS)
        model.set_brush("Q")

        self.assertIs(model.press(A8).kind, ChangeKind.PLACEMENT)
        self.assertTrue(model.placement.startswith("Q3k3"))

        segundo = model.press(A8)
        self.assertIs(segundo.kind, ChangeKind.PLACEMENT)
        self.assertTrue(model.placement.startswith("4k3"), "o segundo clique tinha de esvaziar")
        self.assertIn("segundo clique", segundo.message)

        # E o terceiro põe de volta: é alternância, não "apagar uma vez".
        self.assertTrue(model.press(A8).kind is ChangeKind.PLACEMENT)
        self.assertTrue(model.placement.startswith("Q3k3"))

    def test_trocar_por_outra_peca_nao_e_alternancia(self) -> None:
        """Só o mesmo símbolo alterna; outro símbolo substitui, como sempre fez."""
        model = BoardModel(mode="edit")
        model.set_position(INICIAL)
        model.set_brush("Q")

        self.assertIs(model.press(A8).kind, ChangeKind.PLACEMENT)
        self.assertTrue(model.placement.startswith("Q"), "a torre preta tinha de virar dama branca")

    def test_o_pincel_apagar_nao_desapaga(self) -> None:
        """Alternar aqui significaria **criar** uma peça, que é o oposto do que o botão diz."""
        model = BoardModel(mode="edit")
        model.set_position(INICIAL)
        model.set_brush("")

        self.assertIs(model.press(A8).kind, ChangeKind.PLACEMENT)
        self.assertFalse(model.press(A8), "clicar de novo com o pincel apagar não pode criar peça")

    def test_a_frase_de_status_diz_o_que_o_pincel_faz(self) -> None:
        model = BoardModel(mode="edit")
        self.assertIn("desligado", model.set_brush(None))
        self.assertIn("apagar", model.set_brush(""))
        self.assertIn("dama", model.set_brush("Q").lower())


class PlayInteractionTests(unittest.TestCase):
    """Modo de jogo: só lance legal, e a vez importa."""

    def setUp(self) -> None:
        self.model = BoardModel(mode="play")
        self.model.set_position(INICIAL)

    def test_nao_se_seleciona_peca_do_lado_que_nao_joga(self) -> None:
        self.assertFalse(self.model.press(A8), "as pretas não jogam na posição inicial")
        self.assertIsNone(self.model.selected)

    def test_um_lance_legal_sai_como_move_e_nao_como_placement(self) -> None:
        """Quem decide o que fazer com o lance é o dono do widget: a árvore fica fora."""
        self.model.press(E2)
        mudanca = self.model.drop(E4)

        self.assertIs(mudanca.kind, ChangeKind.MOVE)
        assert mudanca.move is not None
        self.assertEqual(mudanca.move.uci(), "e2e4")
        self.assertEqual(self.model.placement, INICIAL, "o modelo não aplica o lance sozinho")

    def test_lance_ilegal_e_recusado_com_explicacao(self) -> None:
        # a4 esta vazia: soltar numa peca propria trocaria a selecao em vez de tentar o lance.
        A4 = 32
        self.model.press(E2)
        mudanca = self.model.drop(A4)
        self.assertIs(mudanca.kind, ChangeKind.MESSAGE)
        self.assertIn("ilegal", mudanca.message)

    def test_clicar_em_outra_peca_propria_troca_a_selecao(self) -> None:
        self.model.press(E2)
        self.assertIs(self.model.drop(E2 - 1).kind, ChangeKind.SELECTION)
        self.assertEqual(self.model.selected, E2 - 1)

    def test_alvos_legais_so_existem_em_modo_de_jogo(self) -> None:
        self.model.press(E2)
        self.assertEqual(len(self.model.legal_targets()), 2, "peão de e2 vai a e3 e e4")

        edicao = BoardModel(mode="edit")
        edicao.set_position(INICIAL)
        edicao.press(E2)
        self.assertEqual(edicao.legal_targets(), frozenset())

    def test_promocao_pergunta_e_respeita_o_cancelamento(self) -> None:
        pedidos: list[int] = []

        def _cancela() -> int | None:
            pedidos.append(1)
            return None

        model = BoardModel(mode="play", promotion_chooser=_cancela)
        model.set_position("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        model.press(8)  # a7
        mudanca = model.drop(0)  # a8

        self.assertEqual(len(pedidos), 1)
        self.assertIs(mudanca.kind, ChangeKind.MESSAGE)
        self.assertIn("cancelada", mudanca.message)

    def test_sem_perguntador_a_promocao_e_dama(self) -> None:
        model = BoardModel(mode="play")
        model.set_position("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        model.press(8)
        mudanca = model.drop(0)
        assert mudanca.move is not None
        self.assertEqual(mudanca.move.promotion, chess.QUEEN)


class SignalTests(unittest.TestCase):
    """Heatmap, casas mudadas e tooltip -- os sinais da S-21, sem canvas."""

    def _probs(self) -> np.ndarray:
        probs = np.full((64, len(PIECE_CLASSES)), 0.01, dtype=float)
        probs[A8, PIECE_TO_IDX["r"]] = 0.60
        probs[A8, PIECE_TO_IDX["q"]] = 0.30
        return probs

    def test_top_classes_ordena_por_probabilidade(self) -> None:
        model = BoardModel(mode="edit")
        model.set_probabilities(self._probs())
        top = model.top_classes(A8, 2)
        self.assertEqual([nome for nome, _ in top], ["r", "q"])

    def test_top_classes_sem_matriz_devolve_vazio(self) -> None:
        self.assertEqual(BoardModel().top_classes(A8), [])

    def test_o_heatmap_so_tinge_abaixo_do_limiar(self) -> None:
        model = BoardModel(mode="edit", uncertain_threshold=0.80)
        model.set_uncertainty([0.99] * 63 + [0.20])
        self.assertIsNone(model.heatmap_confidence(0))
        self.assertAlmostEqual(model.heatmap_confidence(63) or 0.0, 0.20)

    def test_desligar_o_heatmap_cala_todas_as_casas(self) -> None:
        model = BoardModel(mode="edit", uncertain_threshold=0.80)
        model.set_uncertainty([0.20] * 64)
        model.heatmap_enabled = False
        self.assertIsNone(model.heatmap_confidence(0))

    def test_uma_edicao_invalida_os_sinais_do_modelo(self) -> None:
        """A confiança era da leitura antiga: deixá-la afirmaria algo sobre o que mudou."""
        model = BoardModel(mode="edit", uncertain_threshold=0.80)
        model.set_position(INICIAL)
        model.set_uncertainty([0.20] * 64)
        model.set_probabilities(self._probs())
        model.set_changed_squares([A8, H8])

        model.erase(A8)
        self.assertEqual(model.confidences, ())
        self.assertIsNone(model.probs)
        self.assertEqual(model.changed, frozenset())

    def test_a_edicao_suja_tambem_as_casas_que_perderam_o_sinal(self) -> None:
        """Senão o contorno azul de uma casa que não foi tocada ficaria na tela."""
        model = BoardModel(mode="edit", uncertain_threshold=0.80)
        model.set_position(INICIAL)
        model.set_changed_squares([H8])

        mudanca = model.erase(A8)
        self.assertIn(H8, mudanca.dirty)

    def test_confiancas_com_tamanho_errado_sao_recusadas(self) -> None:
        with self.assertRaises(ValueError):
            BoardModel().set_uncertainty([0.5] * 10)

    def test_matriz_de_probabilidade_com_forma_errada_e_recusada(self) -> None:
        with self.assertRaises(ValueError):
            BoardModel().set_probabilities(np.zeros((64, 3)))


class OrientationTests(unittest.TestCase):
    def test_girar_o_tabuleiro_troca_o_mapeamento_de_tela(self) -> None:
        model = BoardModel()
        self.assertEqual(model.display_from_index(A8), (0, 0))
        model.flipped = True
        self.assertEqual(model.display_from_index(A8), (7, 7))

    def test_o_mapeamento_de_ida_e_volta_fecha(self) -> None:
        for flipped in (False, True):
            model = BoardModel(flipped=flipped)
            for index in range(64):
                with self.subTest(flipped=flipped, index=index):
                    self.assertEqual(model.index_from_display(*model.display_from_index(index)), index)


class PositionTests(unittest.TestCase):
    def test_aceita_fen_completa_e_campo_de_pecas(self) -> None:
        model = BoardModel(mode="edit")
        self.assertTrue(model.set_position(REIS))
        self.assertTrue(model.set_position(f"{REIS} b - - 0 1"))
        self.assertEqual(model.side_to_move, chess.BLACK)

    def test_recusa_fen_impossivel_sem_estourar(self) -> None:
        model = BoardModel(mode="edit")
        model.set_position(INICIAL)
        for ruim in ("", "   ", "nao-e-fen", "9999999/8/8/8/8/8/8/8"):
            with self.subTest(fen=ruim):
                self.assertFalse(model.set_position(ruim))
        self.assertEqual(model.placement, INICIAL, "uma FEN recusada não pode mexer na posição")

    def test_posicao_ilegal_e_aceita_em_edicao(self) -> None:
        """É o estado normal no meio de uma correção: dois reis brancos, nenhum preto."""
        model = BoardModel(mode="edit")
        self.assertTrue(model.set_position("8/8/8/8/8/8/8/KK6"))

    def test_selecionar_fora_da_faixa_e_erro(self) -> None:
        with self.assertRaises(ValueError):
            BoardModel().select(64)

    def test_modo_desconhecido_e_recusado(self) -> None:
        with self.assertRaises(ValueError):
            BoardModel(mode="desenhar")  # type: ignore[arg-type]


class GeometryTests(unittest.TestCase):
    """A geometria é cálculo puro, e por isso também não precisa de canvas."""

    def test_o_tabuleiro_fica_centrado(self) -> None:
        geom = BoardGeometry.fit(400, 400, min_size=100, max_size=560, margin=28)
        self.assertAlmostEqual(geom.size, 372)
        self.assertAlmostEqual(geom.origin_x, 14)
        self.assertAlmostEqual(geom.cell, 46.5)

    def test_o_ponteiro_fora_do_tabuleiro_nao_cai_em_casa_nenhuma(self) -> None:
        geom = BoardGeometry.fit(400, 400, min_size=100, max_size=560, margin=28)
        self.assertIsNone(geom.display_at(0, 0))
        self.assertIsNone(geom.display_at(399, 399))
        self.assertEqual(geom.display_at(20, 20), (0, 0))

    def test_o_canto_oposto_e_a_ultima_casa(self) -> None:
        geom = BoardGeometry.fit(400, 400, min_size=100, max_size=560, margin=28)
        x = geom.origin_x + geom.size - 1
        y = geom.origin_y + geom.size - 1
        self.assertEqual(geom.display_at(x, y), (7, 7))


class HeatmapColorTests(unittest.TestCase):
    def test_no_limiar_e_amarelo_e_no_chao_e_vermelho(self) -> None:
        self.assertEqual(heatmap_color(0.80, 0.80), "#f2c744")
        self.assertEqual(heatmap_color(0.0, 0.80), "#d64545")


class NoTkinterTests(unittest.TestCase):
    def test_o_modelo_nao_importa_tkinter(self) -> None:
        """O critério de aceite literal da S-50: o modelo serve a Tk, a Qt e ao Streamlit."""
        import ast
        from pathlib import Path

        from chess_diagram_ocr.ui import board_model

        arvore = ast.parse(Path(board_model.__file__).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for node in ast.walk(arvore):
            if isinstance(node, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                importados.add(node.module.split(".")[0])

        self.assertNotIn("tkinter", importados)


if __name__ == "__main__":
    unittest.main()


class DisputedSquaresTests(unittest.TestCase):
    """O quarto canal de sinal do tabuleiro (S-66): casas em que os leitores discordam."""

    def test_padrao_e_vazio(self) -> None:
        self.assertEqual(BoardModel().disputed, frozenset())

    def test_marca_e_apaga(self) -> None:
        model = BoardModel()
        model.set_disputed_squares([3, 7, 3])
        self.assertEqual(model.disputed, frozenset({3, 7}))
        model.set_disputed_squares([])
        self.assertEqual(model.disputed, frozenset())

    def test_sobrevive_a_edicao(self) -> None:
        """A marca é a lista do que falta conferir; sumir ao primeiro clique a inutilizaria."""
        model = BoardModel()
        model.set_disputed_squares([0])
        model.set_brush("Q")
        model.paint(0)
        self.assertEqual(model.disputed, frozenset({0}))


class GeometriaDaMoldura(unittest.TestCase):
    """As coordenadas cabem, e o tabuleiro nunca vaza do canvas (S-155).

    Dois números estavam soltos em arquivos diferentes e nada os ligava: `board_render`
    desenhava a letra 11 px abaixo do tabuleiro, e `board_widget` reservava `margin=28`, que o
    `fit` divide entre os dois lados -- **14 px** para um texto de 9 pt em negrito. A base de
    "a b c d e f g h" era cortada nos **dois** tabuleiros da janela.
    """

    MIN, MAX = 520, 1200

    def test_a_margem_derivada_cabe_o_texto_da_coordenada(self) -> None:
        """O teste que amarra os dois números: a metade da margem tem de passar do offset."""
        from chess_diagram_ocr.ui.board_render import COORD_FONT, COORD_OFFSET_PX, margem_de_coordenada

        margem = margem_de_coordenada()
        meia_altura = (COORD_FONT[1] + 1) // 2
        self.assertGreaterEqual(margem / 2, COORD_OFFSET_PX + meia_altura)

    def test_a_margem_antiga_nao_cabia(self) -> None:
        """O defeito, dito com número: 28/2 = 14 px para um texto que precisa de ~16."""
        from chess_diagram_ocr.ui.board_render import COORD_FONT, COORD_OFFSET_PX

        meia_altura = (COORD_FONT[1] + 1) // 2
        self.assertLess(28 / 2, COORD_OFFSET_PX + meia_altura)

    def test_a_letra_cai_dentro_do_canvas(self) -> None:
        from chess_diagram_ocr.ui.board_render import COORD_FONT, COORD_OFFSET_PX, BoardGeometry, margem_de_coordenada

        margem = margem_de_coordenada()
        meia_altura = (COORD_FONT[1] + 1) // 2
        for lado in (560, 700, 900, 1400):
            with self.subTest(lado=lado):
                g = BoardGeometry.fit(lado, lado, min_size=self.MIN, max_size=self.MAX, margin=margem)
                base_da_letra = g.origin_y + g.size + COORD_OFFSET_PX + meia_altura
                self.assertLessEqual(base_da_letra, lado, "a base de a–h saiu do canvas")

    def test_o_tabuleiro_nunca_excede_o_canvas(self) -> None:
        """O transbordo: com o canvas menor que `min_size`, o `max` externo ganhava e o
        tabuleiro ficava **maior que o canvas** -- vazava em vez de encolher."""
        from chess_diagram_ocr.ui.board_render import BoardGeometry

        for largura, altura in ((300, 300), (200, 900), (900, 180), (64, 64)):
            with self.subTest(canvas=(largura, altura)):
                g = BoardGeometry.fit(largura, altura, min_size=self.MIN, max_size=self.MAX, margin=34)
                self.assertLessEqual(g.size, min(largura, altura))
                self.assertGreaterEqual(g.origin_x, 0.0)
                self.assertGreaterEqual(g.origin_y, 0.0)

    def test_acima_do_minimo_nada_mudou(self) -> None:
        """O controle: a correção do transbordo não pode mexer no caso normal."""
        from chess_diagram_ocr.ui.board_render import BoardGeometry

        g = BoardGeometry.fit(900, 900, min_size=self.MIN, max_size=self.MAX, margin=34)
        self.assertEqual(g.size, 900 - 34)
