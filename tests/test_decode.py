from __future__ import annotations

import unittest

import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.config import PIECE_TO_IDX
from chess_diagram_ocr.decode import decode_constrained
from chess_diagram_ocr.fen_utils import check_position, labels_from_fen, square_name

LEGAL = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R"
KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"

# Caso real medido no 1937 Kemeri.pdf (SPEC S-11): a leitura saiu sem rei branco porque
# em fonte figurina alema o K vira Q. O reparo certo e a7 voltar a ser rei.
KEMERI_NO_WHITE_KING = "8/Q3N3/1P1r4/8/5kr1/8/6P1/8"
KEMERI_FIXED = "8/K3N3/1P1r4/8/5kr1/8/6P1/8"


def square_index(name: str) -> int:
    return next(index for index in range(64) if square_name(index) == name)


class LegalInputTests(unittest.TestCase):
    def test_legal_position_passes_untouched(self) -> None:
        result = decode_constrained(probs_for_fen(LEGAL))

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.fen_board, LEGAL)
        self.assertEqual(result.changed_squares, [])

    def test_kings_only_passes_untouched(self) -> None:
        result = decode_constrained(probs_for_fen(KINGS_ONLY))

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [])


class MissingKingTests(unittest.TestCase):
    def test_repairs_the_measured_kemeri_case(self) -> None:
        """O caso que motivou a S-11: a informacao para corrigir ja estava nas probs."""
        probs = probs_for_fen(KEMERI_NO_WHITE_KING, confidence=0.99)
        a7 = square_index("a7")
        probs[a7] = 0.0
        probs[a7, PIECE_TO_IDX["Q"]] = 0.55  # o que o argmax leu
        probs[a7, PIECE_TO_IDX["K"]] = 0.45  # a leitura correta, descartada pelo argmax

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.fen_board, KEMERI_FIXED)
        self.assertEqual(result.changed_squares, [(a7, PIECE_TO_IDX["Q"], PIECE_TO_IDX["K"])])
        self.assertTrue(check_position(result.fen_board).legal_turn is not None)

    def test_picks_the_cheapest_square_to_become_king(self) -> None:
        """Entre duas casas que poderiam virar rei, vence a que o modelo menos contradiz."""
        probs = probs_for_fen("8/Q3N3/1P1r4/8/5kr1/8/6P1/8", confidence=0.99)
        a7, e7 = square_index("a7"), square_index("e7")
        probs[a7, PIECE_TO_IDX["K"]] = 0.30
        probs[e7, PIECE_TO_IDX["K"]] = 0.05

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual([square for square, _, _ in result.changed_squares], [a7])

    def test_missing_black_king_is_repaired_too(self) -> None:
        probs = probs_for_fen("8/8/8/3R4/8/3K4/nQ2p2b/8", confidence=0.99)
        b1 = square_index("b1")
        probs[b1] = 0.0
        probs[b1, PIECE_TO_IDX["empty"]] = 0.60
        probs[b1, PIECE_TO_IDX["k"]] = 0.40

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.class_indices[b1], PIECE_TO_IDX["k"])


class TooManyKingsTests(unittest.TestCase):
    def test_extra_king_falls_back_to_second_reading(self) -> None:
        # Dois reis brancos: e1 (seguro) e b1 (inseguro, segunda opcao Q).
        probs = probs_for_fen("4k3/8/8/8/8/8/8/1K2K3", confidence=0.99)
        b1 = square_index("b1")
        probs[b1] = 0.0
        probs[b1, PIECE_TO_IDX["K"]] = 0.52
        probs[b1, PIECE_TO_IDX["Q"]] = 0.48

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.class_indices[b1], PIECE_TO_IDX["Q"])
        self.assertEqual(result.fen_board, "4k3/8/8/8/8/8/8/1Q2K3")


class PawnConstraintTests(unittest.TestCase):
    def test_pawn_on_backrank_is_reclassified(self) -> None:
        probs = probs_for_fen("4k3/8/8/8/8/8/8/P3K3", confidence=0.99)
        a1 = square_index("a1")
        probs[a1] = 0.0
        probs[a1, PIECE_TO_IDX["P"]] = 0.55
        probs[a1, PIECE_TO_IDX["R"]] = 0.45

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.class_indices[a1], PIECE_TO_IDX["R"])

    def test_nine_pawns_lose_the_least_confident_one(self) -> None:
        probs = probs_for_fen("4k3/8/8/8/8/PPPPPPPP/P7/4K3", confidence=0.99)
        a2 = square_index("a2")
        probs[a2] = 0.0
        probs[a2, PIECE_TO_IDX["P"]] = 0.51
        probs[a2, PIECE_TO_IDX["empty"]] = 0.49

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.class_indices[a2], PIECE_TO_IDX["empty"])
        self.assertEqual(sum(1 for index in result.class_indices if index == PIECE_TO_IDX["P"]), 8)


class PromotionCoherenceTests(unittest.TestCase):
    def test_impossible_promotion_count_is_rejected(self) -> None:
        """8 peoes brancos e 3 damas brancas exigiriam 2 promocoes -- e nao sobram peoes."""
        fen = "4k3/8/8/8/QQQ5/8/PPPPPPPP/4K3"
        self.assertEqual(len(labels_from_fen(fen)), 64)

        probs = probs_for_fen(fen, confidence=0.99)
        for name in ("a4", "b4"):
            square = square_index(name)
            probs[square] = 0.0
            probs[square, PIECE_TO_IDX["Q"]] = 0.52
            probs[square, PIECE_TO_IDX["empty"]] = 0.48

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        pawns = sum(1 for index in result.class_indices if index == PIECE_TO_IDX["P"])
        queens = sum(1 for index in result.class_indices if index == PIECE_TO_IDX["Q"])
        # Com todos os 8 peoes de pe, nenhuma promocao pode ter acontecido: sobra 1 dama.
        self.assertEqual(pawns, 8)
        self.assertEqual(queens, 1)
        self.assertEqual(result.fen_board, "4k3/8/8/8/2Q5/8/PPPPPPPP/4K3")

    def test_legal_promotion_count_is_left_alone(self) -> None:
        # 2 damas e 7 peoes: uma promocao, um peao a menos. Coerente.
        result = decode_constrained(probs_for_fen("4k3/8/8/8/1Q6/8/PPPPPPP1/3QK3"))

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [])


class SearchLimitTests(unittest.TestCase):
    def test_gives_up_instead_of_inventing_a_position(self) -> None:
        """Leitura irrecuperavel: melhor admitir a falha do que reescrever meio tabuleiro.

        Um tabuleiro de 16 peoes brancos precisa de 8 trocas; com `max_changes=2` nao ha
        solucao, e o resultado tem de dizer isso em vez de devolver algo legal e inventado.
        """
        probs = probs_for_fen("4k3/8/8/8/8/8/PPPPPPPP/PPPPPPPP", confidence=0.99)

        result = decode_constrained(probs, max_changes=2)

        self.assertFalse(result.constraints_satisfied)
        self.assertTrue(result.remaining_problems)
        self.assertLessEqual(result.changed_square_count, 2)

    def test_result_never_increases_probability(self) -> None:
        """O argmax e o otimo irrestrito: qualquer reparo custa probabilidade."""
        probs = probs_for_fen(KEMERI_NO_WHITE_KING, confidence=0.99)
        a7 = square_index("a7")
        probs[a7] = 0.0
        probs[a7, PIECE_TO_IDX["Q"]] = 0.55
        probs[a7, PIECE_TO_IDX["K"]] = 0.45

        argmax_log_prob = float(np.log(probs.max(axis=1)).sum())
        result = decode_constrained(probs)

        self.assertLess(result.log_prob, argmax_log_prob)

    def test_rejects_matrix_with_wrong_shape(self) -> None:
        with self.assertRaises(ValueError):
            decode_constrained(np.full((64, 5), 0.2))


class NonFatalGuaranteeTests(unittest.TestCase):
    """Ponte com a S-05: satisfazer as restricoes tem de implicar posicao nao-fatal."""

    def test_repaired_positions_are_never_fatally_illegal(self) -> None:
        cases = (
            KEMERI_NO_WHITE_KING,
            "8/8/8/3R4/8/3K4/nQ2p2b/1K6",
            "4k3/8/8/8/8/8/8/P3K3",
            "1r1k4/3b2R1/p1n1pN2/P2pP3/8/8/8/8",
        )
        for fen in cases:
            with self.subTest(fen=fen):
                result = decode_constrained(probs_for_fen(fen, confidence=0.95))
                if result.constraints_satisfied:
                    self.assertFalse(check_position(result.fen_board).is_fatal)


if __name__ == "__main__":
    unittest.main()
