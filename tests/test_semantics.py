from __future__ import annotations

import unittest

import chess

from chess_diagram_ocr.pdf_text import DiagramContext
from chess_diagram_ocr.semantics import (
    board_placement,
    compose_fen,
    infer_castling_rights,
    infer_side_to_move,
)

# Pretas em xeque pela torre em e1. Com "w" a posicao e ilegal; com "b" e legal.
BLACK_IN_CHECK = "4k3/8/8/8/8/8/8/4R1K1"

# Nenhum lado em xeque: as duas vezes sao legais e a posicao nao tem o que dizer.
QUIET = "4k3/8/8/8/8/8/8/4K3"

# Rei e torres nas casas iniciais dos dois lados.
CASTLING_READY = "r3k2r/8/8/8/8/8/8/R3K2R"

# Posicao impossivel dos dois jeitos: os dois reis em xeque ao mesmo tempo.
BOTH_IN_CHECK = "4k3/4R3/8/8/8/8/4r3/4K3"


class InferSideToMoveTests(unittest.TestCase):
    def test_texto_decide_quando_declara(self) -> None:
        context = DiagramContext(side_to_move=chess.BLACK, side_to_move_evidence="pretas jogam")

        decision = infer_side_to_move(QUIET, context)

        self.assertEqual(decision.color, chess.BLACK)
        self.assertEqual(decision.source, "text")
        self.assertIn("pretas jogam", decision.reason)
        self.assertFalse(decision.conflicting)

    def test_legalidade_decide_quando_o_texto_cala(self) -> None:
        """A regra decisiva: o lado que não joga não pode estar em xeque."""
        decision = infer_side_to_move(BLACK_IN_CHECK)

        self.assertEqual(decision.color, chess.BLACK)
        self.assertEqual(decision.source, "legality")

    def test_padrao_brancas_quando_nada_responde(self) -> None:
        decision = infer_side_to_move(QUIET)

        self.assertEqual(decision.color, chess.WHITE)
        self.assertEqual(decision.source, "default")
        self.assertTrue(decision.is_assumed)

    def test_legalidade_vence_texto_que_levaria_a_posicao_ilegal(self) -> None:
        """Emitir FEN que se sabe ilegal seria pior de todos os jeitos -- mas vai para revisão."""
        context = DiagramContext(side_to_move=chess.WHITE, side_to_move_evidence="white to move")

        decision = infer_side_to_move(BLACK_IN_CHECK, context)

        self.assertEqual(decision.color, chess.BLACK)
        self.assertEqual(decision.source, "legality")
        self.assertTrue(decision.conflicting)

    def test_texto_e_legalidade_de_acordo_nao_e_conflito(self) -> None:
        context = DiagramContext(side_to_move=chess.BLACK)

        decision = infer_side_to_move(BLACK_IN_CHECK, context)

        self.assertEqual(decision.source, "text")
        self.assertFalse(decision.conflicting)

    def test_posicao_ilegal_dos_dois_jeitos_cai_no_padrao(self) -> None:
        """Aí o problema não é o lado a jogar, é a leitura -- e inventar uma vez não ajuda."""
        decision = infer_side_to_move(BOTH_IN_CHECK)

        self.assertEqual(decision.source, "default")

    def test_aceita_fen_completa_e_campo_de_pecas(self) -> None:
        self.assertEqual(
            infer_side_to_move(f"{BLACK_IN_CHECK} w - - 0 1").color,
            infer_side_to_move(BLACK_IN_CHECK).color,
        )

    def test_rotulo_em_portugues(self) -> None:
        self.assertEqual(infer_side_to_move(QUIET).label, "brancas")
        self.assertEqual(infer_side_to_move(BLACK_IN_CHECK).label, "pretas")
        self.assertIn("assumido", infer_side_to_move(QUIET).source_label)


class CastlingRightsTests(unittest.TestCase):
    def test_reis_e_torres_nas_casas_iniciais(self) -> None:
        self.assertEqual(infer_castling_rights(CASTLING_READY), "KQkq")

    def test_apenas_o_que_a_posicao_permite(self) -> None:
        self.assertEqual(infer_castling_rights("4k2r/8/8/8/8/8/8/R3K3"), "Qk")

    def test_sem_rei_na_casa_inicial_nao_ha_direito(self) -> None:
        self.assertEqual(infer_castling_rights("r6r/4k3/8/8/8/8/4K3/R6R"), "-")

    def test_fen_impossivel_de_interpretar_nao_derruba(self) -> None:
        self.assertEqual(infer_castling_rights("isto nao e uma fen"), "-")


class ComposeFenTests(unittest.TestCase):
    def test_monta_fen_com_lado_a_jogar_e_roque_inferido(self) -> None:
        decision = infer_side_to_move(CASTLING_READY)

        self.assertEqual(compose_fen(CASTLING_READY, decision), f"{CASTLING_READY} w KQkq - 0 1")

    def test_aceita_cor_direta(self) -> None:
        self.assertEqual(compose_fen(QUIET, chess.BLACK), f"{QUIET} b - - 0 1")

    def test_roque_pode_ser_desligado(self) -> None:
        self.assertEqual(
            compose_fen(CASTLING_READY, chess.WHITE, infer_castling=False),
            f"{CASTLING_READY} w - - 0 1",
        )

    def test_o_resultado_e_legal_no_caso_do_xeque_invertido(self) -> None:
        """O que a Fase 3 entrega na prática: a posição que saía ilegal passa a fechar."""
        decision = infer_side_to_move(BLACK_IN_CHECK)
        board = chess.Board(compose_fen(BLACK_IN_CHECK, decision))

        self.assertTrue(board.is_valid())

    def test_board_placement_extrai_so_o_campo_de_pecas(self) -> None:
        self.assertEqual(board_placement(f"{QUIET} b KQkq e3 0 1"), QUIET)


if __name__ == "__main__":
    unittest.main()
