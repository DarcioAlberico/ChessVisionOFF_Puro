"""O lance seguinte como evidência sobre a posição (C11 do ciclo 2 OCR/UI).

Três coisas são travadas: o lance impresso que replica **não muda nada** (e diz que replicou);
o lance que só replica com **uma** troca de segunda opção numa casa hesitante adota a troca --
o caso do Burgess e5, `...♛xe5` provando a cor da dama --; e o que não fecha de forma única
(empate, lance de outra página, casa em que o modelo tinha certeza) **não repara nada**.
"""

from __future__ import annotations

import unittest

import chess
import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.config import PIECE_TO_IDX
from chess_diagram_ocr.fen_utils import square_name
from chess_diagram_ocr.inference import prediction_from_probs, prediction_with_squares
from chess_diagram_ocr.lance_seguinte import apply_next_move, conferir
from chess_diagram_ocr.pdf_text import DiagramContext
from chess_diagram_ocr.semantics import SideToMove


def square_index(name: str) -> int:
    return next(index for index in range(64) if square_name(index) == name)


#: Pretas jogam; a dama preta de e5 captura em e5... não: a dama preta está em d6 e captura
#: a torre branca de e5 (`...♛xe5`). O classificador leu a dama de d6 como **branca** (`Q`).
TRUTH = "6k1/5ppp/3q4/4R3/8/8/5PPP/6K1"
MISREAD = "6k1/5ppp/3Q4/4R3/8/8/5PPP/6K1"


def _misread_probs() -> tuple[np.ndarray, list[int]]:
    probs = probs_for_fen(MISREAD, confidence=0.99)
    d6 = square_index("d6")
    probs[d6] = 0.0
    probs[d6, PIECE_TO_IDX["Q"]] = 0.71  # a cor trocada, com confiança alta -- o caso do campo
    probs[d6, PIECE_TO_IDX["q"]] = 0.29
    return probs, [int(i) for i in probs.argmax(axis=1)]


class ReplicaTests(unittest.TestCase):
    def test_a_line_that_replays_changes_nothing(self) -> None:
        probs = probs_for_fen(TRUTH, confidence=0.99)
        reparo = conferir(probs, [int(i) for i in probs.argmax(axis=1)],
                          linha="23...♛xe5 24.f4 ♛e3+", turn=chess.BLACK, fullmove=23)
        self.assertTrue(reparo.replicou)
        self.assertEqual(reparo.trocas, ())
        self.assertEqual(reparo.lance, "23...♛xe5")
        self.assertEqual(reparo.placement, TRUTH)

    def test_no_printed_move_is_no_evidence(self) -> None:
        probs = probs_for_fen(TRUTH)
        reparo = conferir(probs, [int(i) for i in probs.argmax(axis=1)], linha="", turn=chess.BLACK)
        self.assertIsNone(reparo.replicou)
        prosa = conferir(probs, [int(i) for i in probs.argmax(axis=1)],
                         linha="Black to play and win", turn=chess.BLACK)
        self.assertIsNone(prosa.replicou)


class ReparoTests(unittest.TestCase):
    def test_the_move_proves_the_colour_of_the_queen(self) -> None:
        """Burgess e5 (análise §3.9): `...♛xe5` é ilegal com a dama branca; só a segunda opção
        da casa hesitante (a dama preta) fecha a linha, e é adotada."""
        probs, lidos = _misread_probs()
        d6 = square_index("d6")
        reparo = conferir(probs, lidos, linha="23...♛xe5 24.f4 ♛e3+", turn=chess.BLACK, fullmove=23)
        self.assertFalse(reparo.replicou)
        self.assertEqual(reparo.trocas, ((d6, PIECE_TO_IDX["Q"], PIECE_TO_IDX["q"]),))
        self.assertEqual(reparo.placement, TRUTH)
        self.assertIn("d6 Q→q", reparo.motivo)

    def test_a_line_that_stops_before_the_required_moves_repairs_nothing(self) -> None:
        """A guarda: a troca tem de fechar os três primeiros lances, não só o primeiro."""
        probs, lidos = _misread_probs()
        reparo = conferir(probs, lidos, linha="23...♛xe5 24.f4 ♛h1", turn=chess.BLACK, fullmove=23)
        self.assertFalse(reparo.replicou)
        self.assertEqual(reparo.trocas, ())

    def test_the_neighbours_move_repairs_nothing(self) -> None:
        """A sabotagem do campo: o lance de outro diagrama não fecha, e nada é adotado."""
        probs, lidos = _misread_probs()
        reparo = conferir(probs, lidos, linha="31.♖a8+ ♚g7 32.♖a7", turn=chess.WHITE, fullmove=31)
        self.assertFalse(reparo.replicou)
        self.assertEqual(reparo.trocas, ())
        self.assertFalse(reparo.ambiguo)

    def test_a_confident_piece_may_only_change_colour(self) -> None:
        """A dama lida a 0,99 como branca: a segunda opção não conta (o modelo não hesitou), mas
        a **cor** conta -- é o erro que o campo mede -- e é a única troca que fecha a linha."""
        probs = probs_for_fen(MISREAD, confidence=0.99)
        lidos = [int(i) for i in probs.argmax(axis=1)]
        d6 = square_index("d6")
        reparo = conferir(probs, lidos, linha="23...♛xe5 24.f4 ♛e3+", turn=chess.BLACK, fullmove=23)
        self.assertEqual(reparo.trocas, ((d6, PIECE_TO_IDX["Q"], PIECE_TO_IDX["q"]),))

    def test_an_empty_confident_square_is_never_filled(self) -> None:
        """`1.♕xe5` sem dama branca na leitura: nenhuma casa vazia a 0,99 vira dama, porque
        a segunda opção só entra onde o modelo hesitou (margem < 0,9)."""
        misread = "6k1/5ppp/8/4r3/8/8/5PPP/6K1"
        probs = probs_for_fen(misread, confidence=0.99)
        lidos = [int(i) for i in probs.argmax(axis=1)]
        reparo = conferir(probs, lidos, linha="1.♕xe5 ♚h8 2.♕e8+", turn=chess.WHITE, fullmove=1)
        self.assertFalse(reparo.replicou)
        self.assertEqual(reparo.trocas, ())
        self.assertFalse(reparo.ambiguo)

    def test_one_printed_move_confirms_but_never_repairs(self) -> None:
        probs, lidos = _misread_probs()
        reparo = conferir(probs, lidos, linha="23...♛xe5", turn=chess.BLACK, fullmove=23)
        self.assertFalse(reparo.replicou)
        self.assertEqual(reparo.trocas, ())
        self.assertIn("um lance só", reparo.motivo)

    def test_a_tie_between_two_repairs_adopts_none(self) -> None:
        """Duas casas hesitantes, cada uma sozinha fecha a linha: empate, revisão."""
        # Brancas jogam `1.♕xe5`: nenhuma dama branca na leitura, duas casas que podem ser ela.
        misread = "6k1/5ppp/8/4r3/8/8/5PPP/6K1"
        probs = probs_for_fen(misread, confidence=0.99)
        for name in ("a1", "h5"):
            index = square_index(name)
            probs[index] = 0.0
            probs[index, PIECE_TO_IDX["empty"]] = 0.55
            probs[index, PIECE_TO_IDX["Q"]] = 0.45
        lidos = [int(i) for i in probs.argmax(axis=1)]
        reparo = conferir(probs, lidos, linha="1.♕xe5 ♚h8 2.♕e8+", turn=chess.WHITE, fullmove=1)
        self.assertFalse(reparo.replicou)
        self.assertTrue(reparo.ambiguo)
        self.assertEqual(reparo.trocas, ())


class PredictionTests(unittest.TestCase):
    def test_prediction_with_squares_keeps_the_matrix_and_records_the_change(self) -> None:
        probs, _ = _misread_probs()
        prediction = prediction_from_probs(probs, constrained=False)
        d6 = square_index("d6")
        trocada = prediction_with_squares(prediction, [(d6, PIECE_TO_IDX["Q"], PIECE_TO_IDX["q"])])
        self.assertEqual(trocada.fen_board, TRUTH)
        self.assertIs(trocada.probs, prediction.probs)
        self.assertEqual(trocada.decode.changed_squares, [(d6, PIECE_TO_IDX["Q"], PIECE_TO_IDX["q"])])
        self.assertAlmostEqual(float(trocada.square_confidences[d6]), 0.29)
        self.assertAlmostEqual(trocada.min_confidence, 0.29)
        with self.assertRaises(ValueError):
            prediction_with_squares(prediction, [(d6, PIECE_TO_IDX["K"], PIECE_TO_IDX["q"])])

    def test_apply_next_move_uses_the_context_line(self) -> None:
        probs, _ = _misread_probs()
        prediction = prediction_from_probs(probs, constrained=False)
        context = DiagramContext(first_move_number=(23, True), first_moves_text="23...♛xe5 24.f4 ♛e3+")
        side = SideToMove(color=chess.BLACK, source="move-number")
        repaired, reparo = apply_next_move(prediction, context, side)
        self.assertIsNotNone(reparo)
        self.assertEqual(repaired.fen_board, TRUTH)
        self.assertEqual(reparo.casas, [square_index("d6")])
        same, nothing = apply_next_move(prediction, None, side)
        self.assertIs(same, prediction)
        self.assertIsNone(nothing)


if __name__ == "__main__":
    unittest.main()
