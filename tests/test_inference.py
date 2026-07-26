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


class FakeModel:
    """Modelo falso que devolve a matriz que lhe for dada, por orientação da imagem.

    A `predict_with_orientation` faz duas inferências sobre a mesma imagem, uma girada. Para
    testar a *decisão* sem modelo treinado, basta reconhecer qual das duas chegou -- e a
    imagem girada é distinguível por construção (metades de cor diferente).
    """

    def __init__(self, upright: np.ndarray, flipped: np.ndarray) -> None:
        self.upright = upright
        self.flipped = flipped
        self.calls = 0

    def __call__(self, batch):  # noqa: ANN001 - duplo de teste
        import torch

        self.calls += 1
        # A primeira metade das casas e clara na imagem de pe e escura na girada.
        is_upright = float(batch[0].mean()) > float(batch[-1].mean())
        matrix = self.upright if is_upright else self.flipped
        return torch.log(torch.tensor(matrix, dtype=torch.float32))


def rotated_fen(fen: str) -> str:
    """A FEN que sai ao ler a mesma imagem girada 180°: as 64 casas em ordem inversa.

    Ler a imagem girada não muda as peças, muda qual casa é qual -- então a posição
    resultante é a original rotacionada. Os testes de orientação precisam disso para que o
    duplo de modelo reproduza o que o modelo de verdade faria.
    """
    from chess_diagram_ocr.fen_utils import fen_from_class_indices, labels_from_fen

    return fen_from_class_indices(list(reversed(labels_from_fen(fen))))


def board_image_with_distinct_halves() -> np.ndarray:
    """Imagem 800×800 cuja metade de cima é clara: girar 180° é detectável."""
    board = np.zeros((800, 800, 3), dtype=np.uint8)
    board[:400] = 240
    board[400:] = 10
    return board


class PredictWithOrientationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = board_image_with_distinct_halves()

    def _run(self, upright: np.ndarray, flipped: np.ndarray, **kwargs):
        from chess_diagram_ocr.inference import predict_with_orientation

        model = FakeModel(upright, flipped)
        return predict_with_orientation(self.board, model, "cpu", **kwargs)  # type: ignore[arg-type]

    def test_picks_the_orientation_with_higher_min_confidence(self) -> None:
        """O sinal que a medição mostrou separar 320 de 320 no split de teste."""
        result = self._run(probs_for_fen(KINGS_ONLY, 0.99), probs_for_fen(KINGS_ONLY, 0.30))

        self.assertEqual(result.rotation, 0)
        self.assertFalse(result.ambiguous)
        self.assertAlmostEqual(result.margin, 0.69, places=6)
        self.assertIn("confiança mínima", result.reason)

    def test_rotates_when_the_flipped_reading_is_the_confident_one(self) -> None:
        result = self._run(probs_for_fen(KINGS_ONLY, 0.20), probs_for_fen(KINGS_ONLY, 0.99))

        self.assertEqual(result.rotation, 180)
        self.assertFalse(result.ambiguous)
        self.assertIsNotNone(result.alternative)

    def test_legality_decides_even_against_a_more_confident_illegal_reading(self) -> None:
        """Leitura ilegal é pior que leitura insegura, então a legalidade filtra primeiro.

        A orientação de pé é ilegal (sem rei branco) e mais confiante; a girada é legal e
        menos confiante. Vence a legal -- e sai marcada como ambígua, porque os dois sinais
        discordaram, o que não é para resolver em silêncio.
        """
        result = self._run(
            probs_for_fen("4k3/8/8/8/8/8/8/8", 0.99),
            probs_for_fen(KINGS_ONLY, 0.60),
            constrained=False,
        )

        self.assertEqual(result.rotation, 180)
        self.assertEqual(result.reason, "única orientação legal")
        self.assertTrue(result.ambiguous)
        self.assertTrue(result.prediction.position.is_legal)

    def test_constrained_decoding_makes_legality_a_rare_but_harmless_tiebreak(self) -> None:
        """Com a S-11 ligada os dois caminhos chegam à mesma orientação, por sinais diferentes.

        A decodificação restrita repara a leitura ilegal *antes* de a legalidade ser
        consultada, então as duas orientações chegam legais e o filtro cala -- é por isso que
        no split de teste ele só decide em 52 dos 320 tabuleiros. Mas o reparo não esconde o
        problema: a casa reescrita fica com a confiança real dela, que é baixa, e o
        `min_confidence` despenca. Ou seja, ligar a S-11 transfere o sinal de ilegalidade
        para a confiança em vez de perdê-lo, e o veredito não muda.
        """
        sem_rei_branco = probs_for_fen("4k3/8/8/8/8/8/8/8", 0.99)
        legal_mas_insegura = probs_for_fen(KINGS_ONLY, 0.60)

        reparado = self._run(sem_rei_branco, legal_mas_insegura, constrained=True)
        cru = self._run(sem_rei_branco, legal_mas_insegura, constrained=False)

        self.assertEqual(reparado.rotation, 180)
        self.assertIn("confiança mínima", reparado.reason)
        self.assertEqual(cru.rotation, 180)
        self.assertEqual(cru.reason, "única orientação legal")

        # A leitura descartada carrega a marca do reparo: confianca baixissima na casa que a
        # busca teve de reescrever.
        self.assertIsNotNone(reparado.alternative)
        assert reparado.alternative is not None
        self.assertLess(reparado.alternative.min_confidence, 0.01)

    def test_pawn_prior_decides_when_confidence_is_noise(self) -> None:
        """A regressão medida no 1937 Kemeri, como teste.

        As duas orientações saem com confiança igualmente baixa -- margem 0,01, ruído -- e
        seguir a margem girava um diagrama cuja leitura de pé estava certa. A estrutura da
        posição resolve: peões brancos embaixo e pretos em cima só acontece na orientação
        correta. Aqui a leitura de pé tem os peões coerentes e a girada, invertidos.
        """
        de_pe = "4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3"
        result = self._run(probs_for_fen(de_pe, 0.60), probs_for_fen(rotated_fen(de_pe), 0.61))

        # A confianca prefere a girada por 0,01; os peoes preferem a de pe por 5 filas.
        self.assertEqual(result.rotation, 0)
        self.assertFalse(result.ambiguous)
        self.assertIn("peões apontam a orientação", result.reason)
        self.assertEqual(result.prediction.fen_board, de_pe)

    def test_pawn_prior_can_also_confirm_a_rotation(self) -> None:
        """O prior não tem preferência por "de pé": mede a estrutura, nos dois sentidos.

        Aqui a imagem está de cabeça para baixo no livro: lida de pé sai com os peões
        invertidos, e lida girada sai coerente. Girar é o certo.
        """
        de_cabeca_para_baixo = "4K3/PPPPPPPP/8/8/8/8/pppppppp/4k3"
        result = self._run(
            probs_for_fen(de_cabeca_para_baixo, 0.61),
            probs_for_fen(rotated_fen(de_cabeca_para_baixo), 0.60),
        )

        self.assertEqual(result.rotation, 180)
        self.assertIn("peões apontam a orientação", result.reason)
        self.assertEqual(result.prediction.fen_board, rotated_fen(de_cabeca_para_baixo))

    def test_thin_margin_is_flagged_instead_of_silently_chosen(self) -> None:
        result = self._run(probs_for_fen(KINGS_ONLY, 0.61), probs_for_fen(KINGS_ONLY, 0.60))

        self.assertTrue(result.ambiguous)
        self.assertIn("margem apertada", result.reason)

    def test_forced_mode_does_not_pay_for_a_second_inference(self) -> None:
        from chess_diagram_ocr.inference import predict_with_orientation

        for mode, expected in (("0", 0), ("180", 180)):
            with self.subTest(mode=mode):
                model = FakeModel(probs_for_fen(KINGS_ONLY, 0.99), probs_for_fen(KINGS_ONLY, 0.99))
                result = predict_with_orientation(self.board, model, "cpu", mode=mode)  # type: ignore[arg-type]

                self.assertEqual(result.rotation, expected)
                self.assertEqual(model.calls, 1)
                self.assertIsNone(result.alternative)
                self.assertFalse(result.ambiguous)

    def test_auto_mode_costs_exactly_two_inferences(self) -> None:
        from chess_diagram_ocr.inference import predict_with_orientation

        model = FakeModel(probs_for_fen(KINGS_ONLY, 0.99), probs_for_fen(KINGS_ONLY, 0.30))
        predict_with_orientation(self.board, model, "cpu")  # type: ignore[arg-type]

        self.assertEqual(model.calls, 2)

    def test_rejects_unknown_mode(self) -> None:
        from chess_diagram_ocr.inference import predict_with_orientation

        model = FakeModel(probs_for_fen(KINGS_ONLY, 0.99), probs_for_fen(KINGS_ONLY, 0.99))
        with self.assertRaises(ValueError):
            predict_with_orientation(self.board, model, "cpu", mode="90")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
