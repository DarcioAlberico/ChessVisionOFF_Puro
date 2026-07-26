from __future__ import annotations

import unittest

from chess_diagram_ocr.fen_utils import (
    labels_from_fen,
    reading_index_from_square,
    square_from_reading_index,
    square_name,
)
from chess_diagram_ocr.ui import board_edit
from chess_diagram_ocr.ui.board_widget import heatmap_color

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


class SquareIndexTests(unittest.TestCase):
    """As duas numerações (leitura e `python-chess`) precisam ir e voltar sem erro."""

    def test_round_trip(self) -> None:
        for index in range(64):
            self.assertEqual(reading_index_from_square(square_from_reading_index(index)), index)

    def test_matches_square_name(self) -> None:
        import chess

        for index in range(64):
            self.assertEqual(chess.square_name(square_from_reading_index(index)), square_name(index))

    def test_rejects_out_of_range(self) -> None:
        for index in (-1, 64):
            with self.assertRaises(ValueError):
                square_from_reading_index(index)
            with self.assertRaises(ValueError):
                reading_index_from_square(index)


class PlacementRoundTripTests(unittest.TestCase):
    def test_round_trip_preserves_placement(self) -> None:
        for placement in (KINGS_ONLY, START, board_edit.EMPTY_PLACEMENT):
            squares = board_edit.squares_from_placement(placement)
            self.assertEqual(len(squares), 64)
            self.assertEqual(board_edit.placement_from_squares(squares), placement)

    def test_accepts_full_fen(self) -> None:
        self.assertEqual(
            board_edit.squares_from_placement(f"{KINGS_ONLY} w - - 0 1"),
            board_edit.squares_from_placement(KINGS_ONLY),
        )

    def test_square_order_matches_labels_from_fen(self) -> None:
        """A ordem daqui tem de ser a mesma da saída do modelo, ou o heatmap aponta errado."""
        squares = board_edit.squares_from_placement(START)
        labels = labels_from_fen(START)
        for index in range(64):
            esperado = "empty" if not squares[index] else squares[index]
            from chess_diagram_ocr.config import PIECE_CLASSES

            self.assertEqual(PIECE_CLASSES[labels[index]], esperado)

    def test_rejects_malformed_placement(self) -> None:
        for ruim in ("8/8/8", "9/8/8/8/8/8/8/8", "4x3/8/8/8/8/8/8/8", "7/8/8/8/8/8/8/8"):
            with self.assertRaises(ValueError, msg=ruim):
                board_edit.squares_from_placement(ruim)
            self.assertFalse(board_edit.is_valid_placement(ruim))


class EditOperationTests(unittest.TestCase):
    def test_set_piece_on_empty_square(self) -> None:
        # 0 = a8.
        resultado = board_edit.set_piece(board_edit.EMPTY_PLACEMENT, 0, "Q")
        self.assertEqual(resultado, "Q7/8/8/8/8/8/8/8")
        self.assertEqual(board_edit.piece_at(resultado, 0), "Q")

    def test_set_piece_none_clears(self) -> None:
        self.assertEqual(board_edit.set_piece("Q7/8/8/8/8/8/8/8", 0, None), board_edit.EMPTY_PLACEMENT)
        self.assertEqual(board_edit.clear_square("Q7/8/8/8/8/8/8/8", 0), board_edit.EMPTY_PLACEMENT)

    def test_move_piece_between_squares(self) -> None:
        # e1 (indice 60) -> e2 (indice 52).
        resultado = board_edit.move_piece(KINGS_ONLY, 60, 52)
        self.assertEqual(board_edit.piece_at(resultado, 52), "K")
        self.assertEqual(board_edit.piece_at(resultado, 60), "")

    def test_move_overwrites_destination(self) -> None:
        """Editar não é jogar: pôr peça em cima de outra é uma correção legítima."""
        placement = board_edit.set_piece(KINGS_ONLY, 52, "q")
        resultado = board_edit.move_piece(placement, 60, 52)
        self.assertEqual(board_edit.piece_at(resultado, 52), "K")

    def test_move_from_empty_square_is_a_no_op(self) -> None:
        self.assertEqual(board_edit.move_piece(KINGS_ONLY, 0, 10), KINGS_ONLY)

    def test_move_to_same_square_is_a_no_op(self) -> None:
        self.assertEqual(board_edit.move_piece(KINGS_ONLY, 60, 60), KINGS_ONLY)

    def test_illegal_positions_are_allowed(self) -> None:
        """Estado intermediário ilegal é normal no meio de uma correção (ver docstring)."""
        dois_reis = board_edit.set_piece(KINGS_ONLY, 0, "K")
        self.assertEqual(board_edit.counts_by_symbol(dois_reis)["K"], 2)
        # Peao na oitava fila: o modelo erra isso, e o usuario precisa poder reproduzi-lo
        # antes de consertar.
        com_peao = board_edit.set_piece(KINGS_ONLY, 1, "P")
        self.assertEqual(board_edit.piece_at(com_peao, 1), "P")

    def test_rejects_unknown_symbol(self) -> None:
        with self.assertRaises(ValueError):
            board_edit.set_piece(KINGS_ONLY, 0, "X")

    def test_rejects_out_of_range_index(self) -> None:
        for index in (-1, 64):
            with self.assertRaises(ValueError):
                board_edit.set_piece(KINGS_ONLY, index, "Q")

    def test_apply_edits_in_bulk(self) -> None:
        resultado = board_edit.apply_edits(board_edit.EMPTY_PLACEMENT, [(0, "k"), (63, "K"), (0, None)])
        self.assertEqual(resultado, "8/8/8/8/8/8/8/7K")


class DifferingSquaresTests(unittest.TestCase):
    def test_reports_only_what_changed(self) -> None:
        depois = board_edit.set_piece(KINGS_ONLY, 60, "Q")
        self.assertEqual(board_edit.differing_squares(KINGS_ONLY, depois), (60,))

    def test_identical_positions_differ_in_nothing(self) -> None:
        self.assertEqual(board_edit.differing_squares(START, START), ())

    def test_move_shows_both_ends(self) -> None:
        depois = board_edit.move_piece(KINGS_ONLY, 60, 52)
        self.assertEqual(board_edit.differing_squares(KINGS_ONLY, depois), (52, 60))


class HeatmapColorTests(unittest.TestCase):
    """A rampa é relativa ao limiar: sem isso todo o erro sai da mesma cor (ver S-10)."""

    def test_at_threshold_is_yellow(self) -> None:
        self.assertEqual(heatmap_color(0.90, 0.90), "#f2c744")

    def test_zero_confidence_is_red(self) -> None:
        self.assertEqual(heatmap_color(0.0, 0.90), "#d64545")

    def test_is_monotonic_towards_red(self) -> None:
        def verde(valor: float) -> int:
            return int(heatmap_color(valor, 0.90)[3:5], 16)

        # Menos confianca -> menos verde, que e o que leva o amarelo ao vermelho.
        self.assertLess(verde(0.2), verde(0.8))

    def test_above_threshold_clamps(self) -> None:
        self.assertEqual(heatmap_color(1.5, 0.90), heatmap_color(0.90, 0.90))


if __name__ == "__main__":
    unittest.main()
