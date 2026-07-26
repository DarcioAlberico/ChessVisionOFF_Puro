from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.config import PIECE_CLASSES, PIECE_TO_IDX
from chess_diagram_ocr.fen_utils import labels_from_fen, square_name
from chess_diagram_ocr.inference import prediction_from_probs

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"
NUM_CLASSES = len(PIECE_CLASSES)


def probs_for_fen(fen: str, confidence: float = 0.99) -> np.ndarray:
    """Matriz (64, 13) que decodifica para `fen`, com a massa restante espalhada."""
    labels = labels_from_fen(fen)
    rest = (1.0 - confidence) / (NUM_CLASSES - 1)
    probs = np.full((64, NUM_CLASSES), rest, dtype=np.float64)
    for square, label in enumerate(labels):
        probs[square] = rest
        probs[square, label] = confidence
    return probs


class SquareNameTests(unittest.TestCase):
    def test_reading_order_matches_fen_order(self) -> None:
        # Indice 0 e a casa que aparece primeiro na FEN (a8), 63 e a ultima (h1).
        self.assertEqual(square_name(0), "a8")
        self.assertEqual(square_name(7), "h8")
        self.assertEqual(square_name(56), "a1")
        self.assertEqual(square_name(63), "h1")

    def test_square_name_agrees_with_labels_from_fen(self) -> None:
        # O rei branco de KINGS_ONLY esta em e1; a casa correspondente deve se chamar e1.
        labels = labels_from_fen(KINGS_ONLY)
        white_king_square = labels.index(PIECE_TO_IDX["K"])
        self.assertEqual(square_name(white_king_square), "e1")

    def test_rejects_out_of_range(self) -> None:
        for index in (-1, 64):
            with self.assertRaises(ValueError):
                square_name(index)


class PredictionFromProbsTests(unittest.TestCase):
    def test_decodes_argmax_into_fen(self) -> None:
        prediction = prediction_from_probs(probs_for_fen(KINGS_ONLY))
        self.assertEqual(prediction.fen_board, KINGS_ONLY)
        self.assertTrue(prediction.position.is_legal)

    def test_rejects_matrix_with_wrong_shape(self) -> None:
        with self.assertRaises(ValueError):
            prediction_from_probs(np.full((32, NUM_CLASSES), 1.0 / NUM_CLASSES))

    def test_min_confidence_exposes_the_error_that_the_mean_hides(self) -> None:
        """O motivo de existir da S-10, como teste.

        Uma unica casa insegura em 64: a media mal se move, o minimo cai para o valor
        real daquela casa. Relatar so a media e o que fazia posicao ilegal sair com
        confianca 0,97.
        """
        probs = probs_for_fen(KINGS_ONLY)
        probs[36] = 0.0
        probs[36, PIECE_TO_IDX["empty"]] = 0.51
        probs[36, PIECE_TO_IDX["Q"]] = 0.49

        prediction = prediction_from_probs(probs)

        self.assertAlmostEqual(prediction.min_confidence, 0.51, places=6)
        self.assertGreater(prediction.mean_confidence, 0.97)
        self.assertGreater(prediction.mean_confidence - prediction.min_confidence, 0.4)

    def test_uncertain_squares_are_ordered_by_confidence(self) -> None:
        probs = probs_for_fen(KINGS_ONLY)
        for square, confidence in ((10, 0.60), (20, 0.40), (30, 0.80)):
            probs[square] = (1.0 - confidence) / (NUM_CLASSES - 1)
            probs[square, PIECE_TO_IDX["empty"]] = confidence

        prediction = prediction_from_probs(probs, uncertain_threshold=0.90)

        self.assertEqual(prediction.uncertain_squares, [20, 10, 30])
        self.assertEqual(prediction.uncertain_square_names, ["e6", "c7", "g5"])

    def test_confident_board_has_no_uncertain_squares(self) -> None:
        prediction = prediction_from_probs(probs_for_fen(KINGS_ONLY, confidence=0.999))
        self.assertEqual(prediction.uncertain_squares, [])

    def test_entropy_is_higher_for_a_spread_distribution(self) -> None:
        sharp = prediction_from_probs(probs_for_fen(KINGS_ONLY, confidence=0.999))
        blunt = prediction_from_probs(probs_for_fen(KINGS_ONLY, confidence=0.30))

        self.assertLess(sharp.mean_entropy, blunt.mean_entropy)
        # Limite superior teorico: distribuicao uniforme sobre 13 classes.
        self.assertLess(blunt.mean_entropy, float(np.log(NUM_CLASSES)))

    def test_probs_are_preserved_for_downstream_decoding(self) -> None:
        """S-11 depende de ler a segunda opcao de cada casa; ela precisa sobreviver."""
        probs = probs_for_fen(KINGS_ONLY)
        probs[60] = 0.0
        probs[60, PIECE_TO_IDX["Q"]] = 0.55
        probs[60, PIECE_TO_IDX["K"]] = 0.45

        prediction = prediction_from_probs(probs)

        self.assertEqual(prediction.probs.shape, (64, NUM_CLASSES))
        runner_up_class, runner_up_prob = prediction.runner_up(60)
        self.assertEqual(runner_up_class, PIECE_TO_IDX["K"])
        self.assertAlmostEqual(runner_up_prob, 0.45, places=6)

    def test_illegal_decoding_is_reported_not_hidden(self) -> None:
        # Sem rei branco: o argmax nao tem nenhuma obrigacao de produzir posicao legal.
        prediction = prediction_from_probs(probs_for_fen("4k3/8/8/8/8/8/8/8"))

        self.assertFalse(prediction.position.is_legal)
        self.assertTrue(prediction.position.is_fatal)
        self.assertIn("falta o rei branco", prediction.position.problems)


if __name__ == "__main__":
    unittest.main()
