from __future__ import annotations

import unittest

from chess_diagram_ocr.fen_utils import square_name
from chess_diagram_ocr.ui.legality import explain_position, illegal_save_question

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"


def named(explanation) -> set[str]:
    return {square_name(index) for index in explanation.highlight_squares}


class LegalPositionTests(unittest.TestCase):
    def test_legal_position_has_nothing_to_point_at(self) -> None:
        explanation = explain_position(f"{KINGS_ONLY} w - - 0 1")
        self.assertTrue(explanation.is_legal)
        self.assertEqual(explanation.problems, ())
        self.assertEqual(explanation.highlight_squares, ())
        self.assertEqual(explanation.label, "legal")
        self.assertEqual(explanation.summary(), "Posição legal.")

    def test_material_line_lists_what_is_on_the_board(self) -> None:
        explanation = explain_position(KINGS_ONLY)
        self.assertIn("K×1", explanation.material_line())
        self.assertIn("k×1", explanation.material_line())


class FatalProblemTests(unittest.TestCase):
    """O item da S-21: dizer o problema **e** onde ele está."""

    def test_two_white_kings_points_at_both(self) -> None:
        explanation = explain_position("4k3/8/8/8/8/8/8/K3K3")
        self.assertTrue(explanation.is_fatal)
        self.assertEqual(explanation.label, "ilegal")
        self.assertEqual(named(explanation), {"a1", "e1"})
        self.assertIn("mais de um rei", explanation.summary())

    def test_two_white_kings_does_not_point_at_the_black_king(self) -> None:
        """Marcar os reis pretos mandaria conferir uma casa que está certa."""
        explanation = explain_position("4k3/8/8/8/8/8/8/K3K3")
        self.assertNotIn("e8", named(explanation))

    def test_missing_king_has_no_square_to_blame(self) -> None:
        explanation = explain_position("8/8/8/8/8/8/8/4K3")
        self.assertTrue(explanation.is_fatal)
        self.assertIn("falta o rei preto", explanation.summary())
        self.assertEqual(explanation.highlight_squares, ())

    def test_pawn_on_backrank_points_at_the_pawn(self) -> None:
        explanation = explain_position("P3k3/8/8/8/8/8/8/4K3")
        self.assertTrue(explanation.is_fatal)
        self.assertEqual(named(explanation), {"a8"})

    def test_too_many_white_pawns_points_at_the_pawns(self) -> None:
        explanation = explain_position("4k3/8/8/8/PPPPPPPP/PPPPPPPP/8/4K3")
        self.assertTrue(explanation.is_fatal)
        textos = [problem.text for problem in explanation.problems]
        self.assertIn("peões brancos demais", textos)
        # 16 peoes tambem estouram a contagem de pecas: os dois problemas sao reportados,
        # e as casas dos dois entram no destaque (16 peoes + o rei).
        self.assertIn("peças brancas demais", textos)
        self.assertEqual(len(explanation.highlight_squares), 17)

    def test_empty_board(self) -> None:
        explanation = explain_position("8/8/8/8/8/8/8/8")
        self.assertTrue(explanation.is_fatal)
        self.assertIn("tabuleiro vazio", explanation.summary())

    def test_unparseable_fen(self) -> None:
        explanation = explain_position("isto nao e uma fen")
        self.assertTrue(explanation.is_fatal)
        self.assertIn("não pôde ser interpretada", explanation.summary())


class SideToMoveProblemTests(unittest.TestCase):
    """Xeque invertido não é erro de leitura: é palpite de lado a jogar (S-17)."""

    def test_opposite_check_is_not_fatal_and_names_the_pieces_involved(self) -> None:
        # Torre em a8 da xeque ao rei preto em e8, com as brancas na vez.
        explanation = explain_position("R3k3/8/8/8/8/8/8/4K3 w - - 0 1")
        self.assertFalse(explanation.is_legal)
        self.assertFalse(explanation.is_fatal)
        self.assertEqual(explanation.label, "lado a jogar")
        self.assertIn("Só o lado a jogar não fecha", explanation.summary())
        # O rei em xeque e quem da o xeque: e o par que explica o problema.
        self.assertEqual(named(explanation), {"a8", "e8"})

    def test_flipping_the_side_to_move_resolves_it(self) -> None:
        self.assertTrue(explain_position("R3k3/8/8/8/8/8/8/4K3 b - - 0 1").is_legal)


class IllegalSaveQuestionTests(unittest.TestCase):
    """Quando perguntar antes de gravar, e o que a pergunta precisa dizer."""

    def test_a_legal_position_asks_nothing(self) -> None:
        self.assertIsNone(illegal_save_question(f"{KINGS_ONLY} w - - 0 1"))

    def test_a_pawn_structure_without_kings_is_asked_about(self) -> None:
        pergunta = illegal_save_question("8/pp3ppp/8/8/8/8/PP3PPP/8 w - - 0 1")
        self.assertIsNotNone(pergunta)
        assert pergunta is not None
        self.assertIn("falta o rei branco", pergunta)
        self.assertIn("falta o rei preto", pergunta)
        # A pergunta tem de deixar as duas saidas visiveis: e a diferenca entre confirmar e
        # clicar "sim" so para a caixa sumir.
        self.assertIn("estrutura de peões", pergunta)
        self.assertIn("cancele", pergunta)

    def test_the_question_names_the_guilty_squares(self) -> None:
        pergunta = illegal_save_question("4k3/8/8/8/8/8/8/K3K3 w - - 0 1")
        assert pergunta is not None
        self.assertIn("a1", pergunta)
        self.assertIn("e1", pergunta)

    def test_the_side_to_move_check_never_asks(self) -> None:
        """Xeque invertido nunca bloqueou gravação; virar pergunta seria uma caixa nova."""
        self.assertIsNone(illegal_save_question("R3k3/8/8/8/8/8/8/4K3 w - - 0 1"))


if __name__ == "__main__":
    unittest.main()
