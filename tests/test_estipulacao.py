"""A estipulação como evidência sobre a posição (C12 do ciclo 2 OCR/UI).

Quatro coisas são travadas: a gramática lê a exigência dos livros do acervo e **recusa** o que
não é mate direto; a busca exaustiva responde «fecha», «não fecha» e «cozido» sem inventar; a
troca única que faz a exigência fechar é adotada (a dama de cor trocada do campo), e o que não
fecha de forma única -- empate, mate em 1, casa segura -- não repara nada; e `apply_stipulation`
cala quando a página não exige nada.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import chess
import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.config import PIECE_TO_IDX
from chess_diagram_ocr.estipulacao import (
    Estipulacao,
    apply_stipulation,
    conferir,
    estipulacao_de_pagina,
    parse_estipulacao,
    verificar,
)
from chess_diagram_ocr.fen_utils import square_name
from chess_diagram_ocr.inference import prediction_from_probs
from chess_diagram_ocr.pdf_text import DiagramContext, parse_context
from chess_diagram_ocr.semantics import SideToMove


def square_index(name: str) -> int:
    return next(index for index in range(64) if square_name(index) == name)


#: Pretas jogam e dão mate em 2: 1...♛d1+ 2.♖e1 ♛xe1#. O classificador leu a dama de d6 como
#: **branca** (`Q`) -- a casa de cor do campo (análise §3.1).
TRUTH = "6k1/5ppp/3q4/4R3/8/8/5PPP/6K1"
MISREAD = "6k1/5ppp/3Q4/4R3/8/8/5PPP/6K1"


def _misread_probs(confidence: float = 0.71) -> tuple[np.ndarray, list[int]]:
    probs = probs_for_fen(MISREAD, confidence=0.99)
    d6 = square_index("d6")
    probs[d6] = 0.0
    probs[d6, PIECE_TO_IDX["Q"]] = confidence
    probs[d6, PIECE_TO_IDX["q"]] = 1.0 - confidence
    return probs, [int(i) for i in probs.argmax(axis=1)]


class GramaticaTests(unittest.TestCase):
    def test_the_collections_forms_are_read(self) -> None:
        casos = {
            "#2": 2, "2.2 Combinations #2 (451-3514)": 2, "3±": 3, "3+": 3, "4‡": 4, "3 #": 3,
            "Mate in two": 2, "White to play and mate in 3": 3, "Matt in 2 Zügen": 2,
            "mate em 2 lances": 2, "Mat en 2 coups": 2, "Mat in twee zetten": 2, "мат в 3 хода": 3,
            "Mate en dos": 2, "Brancas dão mate em três": 3,
        }
        for texto, lances in casos.items():
            with self.subTest(texto=texto):
                lida = parse_estipulacao(texto)
                self.assertIsNotNone(lida, texto)
                assert lida is not None
                self.assertEqual(lida.lances, lances)
                self.assertEqual(lida.rotulo, f"#{lances}")
                self.assertEqual(lida.descricao, f"Mate em {lances}")

    def test_what_is_not_a_direct_mate_is_refused(self) -> None:
        for texto in ("h#2", "s#3", "r#2", "problem #2", "No. #3", "Black to move", "19...Qxe5 #2.5",
                      "#7", "1.e4 e5 2.Nf3", "", "   ", "Zwarte Bristol", "3+ 4", "White wins",
                      "Brancas jogam e ganham", "mate in the end"):
            with self.subTest(texto=texto):
                self.assertIsNone(parse_estipulacao(texto))

    def test_the_page_scope_needs_one_demand_only(self) -> None:
        escopo = estipulacao_de_pagina(["5334 Problems, Combinations & Games", "2.2 Combinations #2 (451-3514)"])
        assert escopo is not None
        self.assertEqual((escopo.lances, escopo.origem), (2, "pagina"))
        self.assertIsNone(estipulacao_de_pagina(["Mate in two", "#3"]), "duas exigências: nenhuma")
        self.assertIsNone(estipulacao_de_pagina(["Chapter 4", "page 12"]))

    def test_the_caption_parser_carries_the_demand(self) -> None:
        contexto = parse_context("No. 63\nG. H. Drese\n3±")
        assert contexto.stipulation is not None
        self.assertEqual(contexto.stipulation.lances, 3)
        self.assertIsNone(parse_context("1699").stipulation)
        # Em prosa a frase não vale: só linha com formato de legenda declara exigência.
        from chess_diagram_ocr.pdf_text import _parse_lines, _ParsedLine

        prosa = _parse_lines(
            [_ParsedLine(text="as brancas ameaçam mate em 2 depois de 23.♘c4, mas a torre segura tudo",
                         caption_like=False, primary=True)],
            page_number=None,
        )
        self.assertIsNone(prosa.stipulation)


class BuscaTests(unittest.TestCase):
    def test_the_truth_closes_with_one_key(self) -> None:
        resposta = verificar(TRUTH, chess.BLACK, Estipulacao(2))
        self.assertTrue(resposta.fecha)
        self.assertEqual(resposta.chaves, ("Qd1+",))
        self.assertEqual(resposta.metodo, "busca")
        self.assertFalse(resposta.cozido)
        self.assertIn("1.Qd1+", resposta.motivo)

    def test_the_misread_does_not_close(self) -> None:
        resposta = verificar(MISREAD, chess.BLACK, Estipulacao(2))
        self.assertIs(resposta.fecha, False)
        self.assertEqual(resposta.chaves, ())
        self.assertIn("não fecha", resposta.motivo)

    def test_a_cook_is_said(self) -> None:
        resposta = verificar("8/8/8/1Q6/8/k7/8/1K6", chess.WHITE, Estipulacao(2))
        self.assertTrue(resposta.fecha)
        self.assertTrue(resposta.cozido)
        self.assertEqual(len(resposta.chaves), 2)
        self.assertIn("cozido", resposta.motivo)

    def test_a_shorter_mate_is_not_the_demand(self) -> None:
        """«Mate em 2» é mate em exatamente 2: um mate em 1 é cozido ou leitura errada -- e é
        o que impede uma peça a mais de «fechar» por um mate que o problema nunca teve."""
        resposta = verificar("k7/8/1K6/8/8/8/8/7Q", chess.WHITE, Estipulacao(2))
        self.assertIs(resposta.fecha, False)
        self.assertIn("mate em 1", resposta.motivo)
        self.assertIn("mais curto", resposta.motivo)

    def test_mate_in_one_is_a_check_that_mates(self) -> None:
        resposta = verificar("6k1/5ppp/8/8/8/8/5PPP/R5K1", chess.WHITE, Estipulacao(1))
        self.assertTrue(resposta.fecha)
        self.assertEqual(resposta.chaves, ("Ra8#",))
        self.assertLess(resposta.nos, 30)

    def test_an_illegal_position_is_not_verified(self) -> None:
        resposta = verificar("8/8/8/8/8/8/8/8", chess.WHITE, Estipulacao(2))
        self.assertIsNone(resposta.fecha)
        self.assertIn("ilegal", resposta.motivo)

    def test_the_budget_says_budget_not_no(self) -> None:
        resposta = verificar(TRUTH, chess.BLACK, Estipulacao(2), limite_nos=5)
        self.assertIsNone(resposta.fecha)
        self.assertIn("orçamento", resposta.motivo)

    def test_mate_in_three_without_an_engine_is_unverified(self) -> None:
        resposta = verificar(TRUTH, chess.BLACK, Estipulacao(3), motor=None)
        self.assertIsNone(resposta.fecha)
        self.assertIn("sem motor", resposta.motivo)

    def test_mate_in_three_asks_the_engine_and_turns_the_score(self) -> None:
        class Motor:
            def __init__(self, mate: int | None) -> None:
                self.mate = mate
                self.pedidos: list[tuple[int, float]] = []

            def mate_in(self, board: chess.Board, lances: int, *, time_s: float) -> object:
                self.pedidos.append((lances, time_s))
                return type("Av", (), {"mate_in": self.mate, "best_move_san": "Qd1+", "depth": 12})()

        # `mate_in` do motor é do ponto de vista das brancas: -3 é mate das pretas em 3.
        pretas = Motor(-3)
        resposta = verificar(TRUTH, chess.BLACK, Estipulacao(3), motor=pretas)  # type: ignore[arg-type]
        self.assertTrue(resposta.fecha)
        self.assertEqual(resposta.metodo, "motor")
        self.assertEqual(pretas.pedidos, [(3, 3.0)])
        sem_mate = Motor(None)
        resposta = verificar(TRUTH, chess.BLACK, Estipulacao(3), motor=sem_mate)  # type: ignore[arg-type]
        self.assertIs(resposta.fecha, False)
        self.assertIn("profundidade 12", resposta.motivo)
        longo = Motor(-5)
        self.assertIs(verificar(TRUTH, chess.BLACK, Estipulacao(3), motor=longo).fecha, False)  # type: ignore[arg-type]


class ReparoTests(unittest.TestCase):
    def test_the_demand_proves_the_colour_of_the_queen(self) -> None:
        probs, lidos = _misread_probs()
        d6 = square_index("d6")
        reparo = conferir(probs, lidos, Estipulacao(2), chess.BLACK)
        self.assertIs(reparo.fecha, False)
        self.assertEqual(reparo.trocas, ((d6, PIECE_TO_IDX["Q"], PIECE_TO_IDX["q"]),))
        self.assertEqual(reparo.placement, TRUTH)
        self.assertEqual(reparo.chaves, ("Qd1+",))
        self.assertIn("d6 Q→q", reparo.motivo)

    def test_a_reading_that_closes_changes_nothing(self) -> None:
        probs = probs_for_fen(TRUTH, confidence=0.99)
        reparo = conferir(probs, [int(i) for i in probs.argmax(axis=1)], Estipulacao(2), chess.BLACK)
        self.assertTrue(reparo.fecha)
        self.assertEqual(reparo.trocas, ())
        self.assertEqual(reparo.placement, TRUTH)

    def test_mate_in_one_confirms_but_never_repairs(self) -> None:
        probs, lidos = _misread_probs()
        reparo = conferir(probs, lidos, Estipulacao(1), chess.BLACK)
        self.assertIs(reparo.fecha, False)
        self.assertEqual(reparo.trocas, ())

    def test_the_engine_tier_never_searches_repairs(self) -> None:
        probs, lidos = _misread_probs()
        chamadas: list[str] = []

        class Motor:
            def mate_in(self, board: chess.Board, lances: int, *, time_s: float) -> object:
                chamadas.append(board.board_fen())
                return type("Av", (), {"mate_in": None, "best_move_san": "", "depth": 9})()

        reparo = conferir(probs, lidos, Estipulacao(3), chess.BLACK, motor=Motor())  # type: ignore[arg-type]
        self.assertIs(reparo.fecha, False)
        self.assertEqual(reparo.trocas, ())
        self.assertEqual(chamadas, [MISREAD], "uma consulta só: a da leitura")

    def test_a_tie_between_two_repairs_adopts_none(self) -> None:
        """Duas casas hesitantes cuja segunda opção fecha: empate, nenhuma adotada."""
        # A dama preta sumiu da leitura (d6 vazia a 0,6) e c6 hesita do mesmo jeito: uma dama
        # preta em qualquer das duas dá mate em exatamente 2 (♛d1+/♛c1+ ♖e1 ♛xe1#).
        probs = probs_for_fen("6k1/5ppp/8/4R3/8/8/5PPP/6K1", confidence=0.99)
        for casa in (square_index("d6"), square_index("c6")):
            probs[casa] = 0.0
            probs[casa, PIECE_TO_IDX["empty"]] = 0.6
            probs[casa, PIECE_TO_IDX["q"]] = 0.4
        lidos = [int(i) for i in probs.argmax(axis=1)]
        reparo = conferir(probs, lidos, Estipulacao(2), chess.BLACK)
        self.assertIs(reparo.fecha, False)
        self.assertTrue(reparo.ambiguo)
        self.assertEqual(reparo.trocas, ())

    def test_a_secure_empty_square_is_never_filled(self) -> None:
        """A exigência falaria a favor de pôr uma dama preta em c6 -- mas a casa está vazia a
        0,99 e só a cor de uma peça lida pode mudar numa casa segura."""
        probs = probs_for_fen("6k1/5ppp/8/4R3/8/8/5PPP/6K1", confidence=0.99)
        lidos = [int(i) for i in probs.argmax(axis=1)]
        reparo = conferir(probs, lidos, Estipulacao(2), chess.BLACK)
        self.assertIs(reparo.fecha, False)
        self.assertEqual(reparo.trocas, ())


class ApplyTests(unittest.TestCase):
    def test_no_demand_is_no_evidence(self) -> None:
        probs, _ = _misread_probs()
        prediction = prediction_from_probs(probs, constrained=False)
        side = SideToMove(color=chess.BLACK, source="text", reason="")
        depois, reparo = apply_stipulation(prediction, DiagramContext(), side)
        self.assertIs(depois, prediction)
        self.assertIsNone(reparo)
        depois, reparo = apply_stipulation(prediction, None, side)
        self.assertIsNone(reparo)

    def test_the_context_demand_repairs_the_prediction(self) -> None:
        probs, _ = _misread_probs()
        prediction = prediction_from_probs(probs, constrained=False)
        self.assertEqual(prediction.fen_board, MISREAD)
        side = SideToMove(color=chess.BLACK, source="text", reason="")
        contexto = DiagramContext(stipulation=Estipulacao(2, texto="#2"))
        depois, reparo = apply_stipulation(prediction, contexto, side)
        assert reparo is not None
        self.assertEqual(depois.fen_board, TRUTH)
        self.assertEqual(reparo.casas, [square_index("d6")])
        assert depois.decode is not None
        self.assertIn((square_index("d6"), PIECE_TO_IDX["Q"], PIECE_TO_IDX["q"]), depois.decode.changed_squares)


class MotorPadraoTests(unittest.TestCase):
    def test_without_a_binary_there_is_no_engine_and_no_error(self) -> None:
        from chess_diagram_ocr import estipulacao

        estipulacao.esquecer_motor()
        try:
            with patch("chess_diagram_ocr.engine.find_engine", return_value=None):
                self.assertIsNone(estipulacao.motor_padrao())
                self.assertIsNone(estipulacao.motor_padrao(), "a resposta é lembrada")
        finally:
            estipulacao.esquecer_motor()


if __name__ == "__main__":
    unittest.main()
