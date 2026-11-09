from __future__ import annotations

import unittest

import chess

from chess_diagram_ocr.fen_utils import (
    check_position,
    describe_status,
    fen_from_class_indices,
    is_legal_position,
    is_syntactically_valid_fen,
    labels_from_fen,
    pawn_direction_score,
)

# Posicoes legais de referencia.
INITIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"


class SyntaxVersusLegalityTests(unittest.TestCase):
    """A distincao que faltava: sintaxe valida nao implica posicao legal."""

    def test_syntax_check_accepts_illegal_positions(self) -> None:
        # Comportamento intencional e documentado: e um teste de sintaxe.
        for fen in (
            "8/8/8/3R4/8/3K4/nQ2p2b/1K6",  # dois reis brancos
            "8/8/8/8/8/8/PPPPPPPP/PPPPPPPP",  # 16 peoes, peoes na primeira fila
            "8/8/8/8/8/8/8/8",  # vazio
        ):
            with self.subTest(fen=fen):
                self.assertTrue(is_syntactically_valid_fen(fen))

    def test_legality_check_rejects_them(self) -> None:
        for fen in (
            "8/8/8/3R4/8/3K4/nQ2p2b/1K6",
            "8/8/8/8/8/8/PPPPPPPP/PPPPPPPP",
            "8/8/8/8/8/8/8/8",
        ):
            with self.subTest(fen=fen):
                self.assertFalse(is_legal_position(fen))
                self.assertTrue(check_position(fen).is_fatal)

    def test_syntax_check_tolerates_non_text_input(self) -> None:
        # Celula vazia do CSV chega como float NaN; nao deve levantar excecao.
        self.assertFalse(is_syntactically_valid_fen(float("nan")))  # type: ignore[arg-type]
        self.assertFalse(is_syntactically_valid_fen(None))  # type: ignore[arg-type]


class FatalStatusTests(unittest.TestCase):
    def test_each_fatal_status_is_detected(self) -> None:
        cases = [
            ("4k3/8/8/8/8/8/8/8", "falta o rei branco"),
            ("8/8/8/8/8/8/8/4K3", "falta o rei preto"),
            ("4k3/8/8/8/8/8/8/3KK3", "mais de um rei da mesma cor"),
            ("4k3/8/8/8/8/8/8/PPPPPKPP", "peão na primeira ou na oitava fila"),
            ("8/8/8/8/8/8/8/8", "tabuleiro vazio"),
        ]
        for fen, expected_problem in cases:
            with self.subTest(fen=fen):
                result = check_position(fen)
                self.assertTrue(result.is_fatal, f"{fen} deveria ser fatal")
                self.assertFalse(result.is_legal)
                self.assertIn(expected_problem, result.problems)

    def test_too_many_pawns_is_fatal(self) -> None:
        result = check_position("4k3/8/8/8/8/PPPPPPPP/PPPPPPPP/4K3")
        self.assertTrue(result.is_fatal)
        self.assertIn("peões brancos demais", result.problems)

    def test_fatal_position_has_no_legal_turn(self) -> None:
        # Nenhuma escolha de lado a jogar salva uma posicao sem rei.
        result = check_position("8/8/8/8/8/8/8/4K3")
        self.assertIsNone(result.legal_turn)
        self.assertFalse(result.needs_side_to_move_flip)


class TurnDependentStatusTests(unittest.TestCase):
    """OPPOSITE_CHECK nao e erro de reconhecimento: e o lado a jogar assumido errado."""

    def test_opposite_check_is_not_fatal_and_suggests_flip(self) -> None:
        # Pretas em xeque pela torre em a8; com "w" isso e ilegal, com "b" e legal.
        fen = "R3k3/8/8/8/8/8/8/4K3"
        result = check_position(fen)

        self.assertFalse(result.is_legal)
        self.assertFalse(result.is_fatal)
        self.assertEqual(result.legal_turn, chess.BLACK)
        self.assertTrue(result.needs_side_to_move_flip)
        self.assertIn("o lado que não joga está em xeque", result.problems)

    def test_explicit_black_to_move_is_legal(self) -> None:
        result = check_position("R3k3/8/8/8/8/8/8/4K3 b - - 0 1")
        self.assertTrue(result.is_legal)
        self.assertFalse(result.is_fatal)
        self.assertEqual(result.legal_turn, chess.BLACK)

    def test_real_dataset_sample_flagged_as_flip_not_corruption(self) -> None:
        # Amostra real do labels.csv classificada como OPPOSITE_CHECK.
        result = check_position("r1bqr3/ppp2k1p/2np2p1/8/3pP3/1Q6/PPP2PPP/RNB1K2R")
        self.assertFalse(result.is_fatal, "nao e corrupcao de rotulo")
        self.assertTrue(result.needs_side_to_move_flip)


class LegalPositionTests(unittest.TestCase):
    def test_legal_positions_pass(self) -> None:
        for fen in (INITIAL, KINGS_ONLY, "8/8/8/3k4/8/3K4/8/8"):
            with self.subTest(fen=fen):
                result = check_position(fen)
                self.assertTrue(result.is_legal, f"{fen}: {result.problems}")
                self.assertFalse(result.is_fatal)
                self.assertEqual(result.problems, ())

    def test_eight_pawns_per_side_is_legal(self) -> None:
        self.assertTrue(is_legal_position(INITIAL))

    def test_castling_and_ep_noise_is_ignored(self) -> None:
        # O sufixo padrao "w - - 0 1" nao deve gerar problemas reportados.
        result = check_position("r3k2r/8/8/8/8/8/8/R3K2R")
        self.assertTrue(result.is_legal)
        self.assertEqual(result.problems, ())

    def test_describe_status_of_valid_is_empty(self) -> None:
        self.assertEqual(describe_status(chess.STATUS_VALID), ())


class FenRoundTripTests(unittest.TestCase):
    def test_labels_and_fen_round_trip(self) -> None:
        labels = labels_from_fen(INITIAL)
        self.assertEqual(len(labels), 64)
        self.assertEqual(fen_from_class_indices(labels), INITIAL)

    def test_labels_from_fen_rejects_wrong_rank_count(self) -> None:
        with self.assertRaises(ValueError):
            labels_from_fen("8/8/8")

    def test_fen_from_class_indices_rejects_wrong_length(self) -> None:
        with self.assertRaises(ValueError):
            fen_from_class_indices([0] * 63)


class PawnDirectionScoreTests(unittest.TestCase):
    """O prior estrutural que decide a orientação quando a confiança empata (S-13)."""

    def test_initial_position_scores_strongly_upright(self) -> None:
        # Peoes brancos na fila 2, pretos na 7: diferenca de 5 filas.
        self.assertAlmostEqual(pawn_direction_score(labels_from_fen(INITIAL)), 5.0, places=6)

    def test_score_flips_sign_when_the_board_is_upside_down(self) -> None:
        upright = labels_from_fen(INITIAL)
        flipped = list(reversed(upright))

        score_upright = pawn_direction_score(upright)
        score_flipped = pawn_direction_score(flipped)

        assert score_upright is not None and score_flipped is not None
        self.assertAlmostEqual(score_upright, -score_flipped, places=6)

    def test_returns_none_when_a_colour_has_no_pawn(self) -> None:
        """Sem peão de um dos lados o prior não tem o que dizer -- e diz isso."""
        for fen in ("4k3/8/8/8/8/8/PPPPPPPP/4K3", "4k3/pppppppp/8/8/8/8/8/4K3", "4k3/8/8/8/8/8/8/4K3"):
            with self.subTest(fen=fen):
                self.assertIsNone(pawn_direction_score(labels_from_fen(fen)))

    def test_rejects_wrong_length(self) -> None:
        with self.assertRaises(ValueError):
            pawn_direction_score([0] * 63)


if __name__ == "__main__":
    unittest.main()


class FenComCaractereEstranhoTests(unittest.TestCase):
    """Caractere de peça desconhecido levanta, e não vira casa vazia (S-361).

    O `.get(peca, empty)` transformava qualquer lixo numa casa vazia plausível, e o pior cliente
    disso é a segunda opinião: as duas leituras viravam `empty` na mesma casa e ela anunciava
    **acordo total** sobre um tabuleiro que nenhuma das duas leu.
    """

    def test_a_fen_valida_continua_valendo(self) -> None:
        self.assertEqual(len(labels_from_fen("4k3/8/8/8/8/8/8/4K3")), 64)

    def test_o_caractere_desconhecido_levanta(self) -> None:
        with self.assertRaises(ValueError) as capturado:
            labels_from_fen("4k3/8/8/8/8/8/8/4X3")
        self.assertIn("X", str(capturado.exception))

    def test_a_figurina_unicode_tambem(self) -> None:
        """É o caso real: a leitura de glifo devolve `♔` e ninguém a converte antes."""
        with self.assertRaises(ValueError):
            labels_from_fen("4k3/8/8/8/8/8/8/4♔3")


class UmParserDeColocacaoTests(unittest.TestCase):
    """S-842: um parser de FEN só, `Colocacao`, e ele concorda com o python-chess.

    `labels_from_fen` aceitava o que o python-chess recusa (dois dígitos seguidos, o zero), e
    `is_syntactically_valid_fen` recusava: os dois parsers do projeto discordavam justamente
    aí. E `fen_from_class_indices` indexava antes de conferir, levantando `KeyError`.
    """

    def test_labels_from_fen_recusa_o_que_o_python_chess_recusa(self) -> None:
        for fen in ("8/8/8/8/8/8/8/44", "4k3/8/8/8/8/8/8/4004", "4k3/8/8/8/8/8/8/08"):
            with self.subTest(fen=fen):
                self.assertFalse(is_syntactically_valid_fen(fen))
                with self.assertRaises(ValueError):
                    labels_from_fen(fen)

    def test_classe_fora_do_alfabeto_e_value_error(self) -> None:
        with self.assertRaises(ValueError):
            fen_from_class_indices([13] * 64)
        with self.assertRaises(ValueError):
            fen_from_class_indices([13] * 63)

    def test_colocacao_concorda_com_o_python_chess_em_dez_mil_fens(self) -> None:
        """Propriedade: aceita exatamente o que `chess.BaseBoard` aceita, e lê as mesmas peças.

        As FENs são sorteadas perto da fronteira: fileiras boas, e estragos do tipo que a
        leitura produz (dígito partido em dois, zero, nove, letra fora do alfabeto, fileira a
        mais ou a menos). O `~` da variante crazyhouse fica de fora: o python-chess o aceita, e
        nenhum livro o imprime.
        """
        import random

        from chess_diagram_ocr.fen_utils import Colocacao, square_from_reading_index

        sorteio = random.Random(842)
        pecas = "PNBRQKpnbrqk"

        def fileira() -> str:
            casas = [sorteio.choice(pecas) if sorteio.random() < 0.4 else "" for _ in range(8)]
            texto, vazias = "", 0
            for casa in casas:
                if not casa:
                    vazias += 1
                    continue
                texto += (str(vazias) if vazias else "") + casa
                vazias = 0
            texto += str(vazias) if vazias else ""
            if sorteio.random() < 0.08:
                posicao = sorteio.randrange(len(texto) + 1)
                texto = texto[:posicao] + sorteio.choice("0912345678xX♔ ") + texto[posicao:]
            if sorteio.random() < 0.05 and "8" in texto:
                texto = texto.replace("8", sorteio.choice(("44", "71", "17", "35")), 1)
            return texto

        aceitas = recusadas = 0
        for _ in range(10_000):
            quantas = 8 if sorteio.random() < 0.95 else sorteio.choice((7, 9))
            fen = "/".join(fileira() for _ in range(quantas))
            try:
                referencia: chess.BaseBoard | None = chess.BaseBoard(fen)
            except ValueError:
                referencia = None
            try:
                colocacao: Colocacao | None = Colocacao.de_fen(fen)
            except ValueError:
                colocacao = None
            self.assertEqual(colocacao is None, referencia is None, fen)
            if colocacao is None or referencia is None:
                recusadas += 1
                continue
            aceitas += 1
            for indice, casa in enumerate(colocacao.casas):
                peca = referencia.piece_at(square_from_reading_index(indice))
                self.assertEqual(casa, peca.symbol() if peca else None, (fen, indice))
            self.assertEqual(colocacao.fen(), referencia.board_fen(), fen)
        self.assertGreater(min(aceitas, recusadas), 1_000, "o sorteio não chegou perto da fronteira")
