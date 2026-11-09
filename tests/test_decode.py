from __future__ import annotations

import unittest

import numpy as np
from test_inference import probs_for_fen

from chess_diagram_ocr.config import ACCEPT_MIN_CONFIDENCE, PIECE_CLASSES, PIECE_TO_IDX
from chess_diagram_ocr.decode import CLASSIC_RULES, MIN_KING_PROBABILITY, DecodeRules, decode_constrained
from chess_diagram_ocr.fen_utils import check_position, labels_from_fen, square_name
from chess_diagram_ocr.inference import prediction_from_probs

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


class KingEvidenceTests(unittest.TestCase):
    """Diagrama de esquema ou de marcas pode não ter rei: o reparo não pode inventar um."""

    NO_BLACK_KING = "8/8/8/8/7K/8/8/8"

    def test_no_evidence_leaves_the_king_missing_and_says_so(self) -> None:
        probs = probs_for_fen(self.NO_BLACK_KING, confidence=0.99)

        result = decode_constrained(probs)

        self.assertEqual(result.fen_board, self.NO_BLACK_KING)
        self.assertEqual(result.changed_squares, [])
        self.assertFalse(result.constraints_satisfied)
        self.assertEqual(result.remaining_problems, ("falta o rei preto",))

    def test_no_king_on_the_board_names_both(self) -> None:
        result = decode_constrained(probs_for_fen("8/8/8/3P4/8/8/8/8", confidence=0.99))

        self.assertEqual(result.changed_squares, [])
        self.assertEqual(result.remaining_problems, ("falta o rei branco", "falta o rei preto"))

    def test_the_threshold_decides_at_the_square(self) -> None:
        d4 = square_index("d4")
        for p_rei, repara in ((MIN_KING_PROBABILITY, True), (MIN_KING_PROBABILITY * 0.99, False)):
            with self.subTest(p_rei=p_rei):
                probs = probs_for_fen(self.NO_BLACK_KING, confidence=0.99)
                probs[d4, PIECE_TO_IDX["k"]] = p_rei

                result = decode_constrained(probs)

                self.assertEqual(result.class_indices[d4] == PIECE_TO_IDX["k"], repara)
                self.assertEqual(result.constraints_satisfied, repara)

    def test_other_violations_are_still_repaired(self) -> None:
        """Sem indício de rei, o peão na oitava fila continua sendo conserto a fazer."""
        a8 = square_index("a8")
        probs = probs_for_fen("P7/8/8/8/7K/8/8/8", confidence=0.99)
        probs[a8] = 0.0
        probs[a8, PIECE_TO_IDX["P"]] = 0.55
        probs[a8, PIECE_TO_IDX["R"]] = 0.45

        result = decode_constrained(probs)

        self.assertEqual(result.class_indices[a8], PIECE_TO_IDX["R"])
        self.assertEqual(result.remaining_problems, ("falta o rei preto",))

    def test_repair_of_another_rule_does_not_smuggle_a_king(self) -> None:
        """O rei sem indício também não entra como alternativa de outra regra."""
        a8 = square_index("a8")
        probs = probs_for_fen("P7/8/8/8/7K/8/8/8", confidence=0.99)
        probs[a8] = 1e-6
        probs[a8, PIECE_TO_IDX["P"]] = 0.99
        probs[a8, PIECE_TO_IDX["k"]] = 0.005
        probs[a8, PIECE_TO_IDX["empty"]] = 0.001

        result = decode_constrained(probs)

        self.assertEqual(result.class_indices[a8], PIECE_TO_IDX["empty"])

    def test_stops_without_spending_the_search(self) -> None:
        probs = probs_for_fen(self.NO_BLACK_KING, confidence=0.99)

        result = decode_constrained(probs, max_expansions=1)

        self.assertEqual(result.remaining_problems, ("falta o rei preto",))

    def test_threshold_zero_is_the_old_decoder(self) -> None:
        probs = probs_for_fen(self.NO_BLACK_KING, confidence=0.99)

        result = decode_constrained(probs, rules=DecodeRules(min_king_probability=0.0))

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_square_count, 1)
        self.assertEqual(decode_constrained(probs, rules=CLASSIC_RULES).class_indices, result.class_indices)


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


class ReparoNaoPassaNoGateTests(unittest.TestCase):
    """Uma posição reparada nunca é exportada, e é aritmética e não tendência (S-132).

    Uma casa reparada recebeu uma classe que **não** era o argmax, e a confiança relatada é a
    dessa classe -- que é no máximo a segunda maior da casa. A segunda maior não passa de 0,5:
    se passasse, a maior também passaria, e as duas somariam mais que 1. `min_confidence` é o
    mínimo sobre as 64 casas, e o gate é `ACCEPT_MIN_CONFIDENCE = 0,80`.

    Não é defeito, é propriedade. O que ela custa está na S-132: o reparo é uma das entregas
    centrais da Fase 2, e o número "casas reparadas" que o `cvoff-field` publicava ao lado da
    taxa de exportação descrevia diagramas que **nenhum** foi exportado.

    O teste existe para que a propriedade não mude sem alguém decidir mudá-la. Se um dia o
    reparo tiver de chegar ao PGN, o que muda é o **gate**, não o decodificador.
    """

    def _probs_com_reparo(self) -> np.ndarray:
        """Probabilidades que forçam o decodificador a consertar pelo menos uma casa.

        O caso real do `Kemeri` (S-11): a leitura sai sem rei branco porque em fonte figurina
        alemã o K vira Q. Tudo a 0,97 no argmax, para que só a casa reparada possa derrubar o
        mínimo -- se o teste falhar, é por causa do reparo e não do ruído de fundo.
        """
        probs = probs_for_fen(KEMERI_NO_WHITE_KING, confidence=0.97)
        a7 = square_index("a7")
        probs[a7] = 0.0
        probs[a7, PIECE_TO_IDX["Q"]] = 0.55  # o que o argmax leu
        probs[a7, PIECE_TO_IDX["K"]] = 0.45  # a leitura correta, descartada pelo argmax
        return probs

    def test_a_casa_reparada_carrega_a_confianca_da_segunda_opcao(self) -> None:
        probs = self._probs_com_reparo()
        resultado = decode_constrained(probs)

        self.assertTrue(resultado.changed_squares, "o caso precisa produzir reparo")
        for casa, argmax, final in resultado.changed_squares:
            self.assertNotEqual(argmax, final)
            self.assertLess(probs[casa, final], probs[casa, argmax])

    def test_nenhum_diagrama_reparado_passa_no_gate(self) -> None:
        probs = self._probs_com_reparo()
        predicao = prediction_from_probs(probs, constrained=True)

        self.assertLess(predicao.min_confidence, ACCEPT_MIN_CONFIDENCE)
        self.assertLessEqual(predicao.min_confidence, 0.5, "o teto da segunda opção")

    def test_o_teto_de_0_5_e_algebrico_e_nao_do_conjunto(self) -> None:
        """A segunda maior de uma distribuição não passa de 0,5, para qualquer distribuição.

        É o que faz a propriedade valer também para um modelo melhor que este: subir a
        confiança do classificador não move o teto da casa **reparada**.
        """
        gerador = np.random.default_rng(11)
        for _ in range(2000):
            distribuicao = gerador.dirichlet(np.full(len(PIECE_CLASSES), 0.2))
            self.assertLessEqual(float(np.sort(distribuicao)[-2]), 0.5)

    def test_sem_reparo_a_confianca_pode_passar_do_gate(self) -> None:
        """O controle: sem reparo, o mesmo desenho de probabilidades exporta."""
        predicao = prediction_from_probs(probs_for_fen(LEGAL, confidence=0.97), constrained=True)

        self.assertEqual(predicao.fen_board, LEGAL)
        self.assertGreaterEqual(predicao.min_confidence, ACCEPT_MIN_CONFIDENCE)


if __name__ == "__main__":
    unittest.main()


class TetoDaBuscaTests(unittest.TestCase):
    """A busca sujeita às regras tem um teto que cabe no tempo, e ele é de expansões (S-358, S-834).

    Um tabuleiro legal nem entra na busca (~0,1 ms); um tabuleiro ilegal gastava as 5.000
    expansões inteiras para no fim admitir que não achou -- 3,5 s medidos aqui, e **duas vezes por
    diagrama**, porque o modo `auto` lê a 0° e a 180°. A S-358 pôs um prazo de relógio; a S-834 o
    tirou (o relógio fazia a mesma matriz sair diferente numa máquina carregada) e baixou o teto
    de expansões até o pior caso caber no mesmo meio segundo.
    """

    def _ilegal(self) -> np.ndarray:
        """Rei branco como argmax em todas as 64 casas: o pior caso da busca."""
        probs = np.full((64, len(PIECE_CLASSES)), 0.02)
        probs[:, PIECE_CLASSES.index("K")] = 0.30
        probs[:, PIECE_CLASSES.index("empty")] = 0.28
        return probs / probs.sum(axis=1, keepdims=True)

    def test_o_pior_caso_cabe_no_teto_padrao(self) -> None:
        import time

        inicio = time.perf_counter()
        resultado = decode_constrained(self._ilegal())
        gasto = time.perf_counter() - inicio

        # ~0,5 s numa máquina ociosa; o dobro dá folga para a suíte em paralelo sem deixar
        # passar o teto de antes, que levava sete vezes isso.
        self.assertLess(gasto, 2.0, "o teto padrão de expansões não segura o pior caso")
        self.assertFalse(resultado.constraints_satisfied)

    def test_o_teto_de_expansoes_vale(self) -> None:
        resultado = decode_constrained(self._ilegal(), max_expansions=50)
        self.assertFalse(resultado.constraints_satisfied)

    def test_o_tabuleiro_legal_nao_e_afetado(self) -> None:
        probs = np.full((64, len(PIECE_CLASSES)), 0.001)
        probs[:, PIECE_CLASSES.index("empty")] = 0.9
        probs[4] = 0.001
        probs[4, PIECE_CLASSES.index("K")] = 0.95
        probs[60] = 0.001
        probs[60, PIECE_CLASSES.index("k")] = 0.95
        probs = probs / probs.sum(axis=1, keepdims=True)

        resultado = decode_constrained(probs)

        self.assertTrue(resultado.constraints_satisfied)
        self.assertEqual(resultado.changed_square_count, 0)


class BishopColourTests(unittest.TestCase):
    """C11 (ciclo 2 OCR/UI): dois bispos de um lado na mesma cor consomem um peão ausente."""

    #: Brancas com os oito peões e dois bispos em casas claras (c4 e f1 são claras): impossível.
    TWO_LIGHT_BISHOPS_ALL_PAWNS = "4k3/8/8/8/2B5/8/PPPPPPPP/4KB2"
    #: O mesmo com um bispo em cada cor (c4 clara, c1 escura): a posição de sempre.
    ONE_OF_EACH = "4k3/8/8/8/2B5/8/PPPPPPPP/2B1K3"
    #: Dois bispos claros com sete peões: uma promoção explica, e nada é violado.
    TWO_LIGHT_BISHOPS_SEVEN_PAWNS = "4k3/8/8/8/2B5/8/PPPPPPP1/4KB2"

    def test_two_same_colour_bishops_with_all_pawns_are_repaired(self) -> None:
        probs = probs_for_fen(self.TWO_LIGHT_BISHOPS_ALL_PAWNS, confidence=0.99)
        f1 = square_index("f1")
        probs[f1] = 0.0
        probs[f1, PIECE_TO_IDX["B"]] = 0.55
        probs[f1, PIECE_TO_IDX["b"]] = 0.45  # a cor trocada -- a dúvida do Stefaniu f1

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [(f1, PIECE_TO_IDX["B"], PIECE_TO_IDX["b"])])

    def test_the_classic_rules_let_it_pass(self) -> None:
        """A sabotagem: sem a regra, a posição passa intacta (o antes do C11)."""
        probs = probs_for_fen(self.TWO_LIGHT_BISHOPS_ALL_PAWNS, confidence=0.99)
        result = decode_constrained(probs, rules=CLASSIC_RULES)
        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [])
        self.assertEqual(decode_constrained(probs, rules=DecodeRules(bishop_colors=False)).changed_squares, [])

    def test_one_bishop_of_each_colour_is_left_alone(self) -> None:
        result = decode_constrained(probs_for_fen(self.ONE_OF_EACH))
        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [])

    def test_a_missing_pawn_explains_the_second_bishop(self) -> None:
        """Não é violação absoluta: com um peão a menos a promoção é possível."""
        result = decode_constrained(probs_for_fen(self.TWO_LIGHT_BISHOPS_SEVEN_PAWNS))
        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [])

    def test_the_colour_rule_does_not_double_count_the_third_bishop(self) -> None:
        """Três bispos, dois claros: dois promovidos (não três) -- seis peões bastam."""
        three = "4k3/8/8/8/2B5/1B6/PPPPPP2/4KB2"  # c4 clara, b3 escura, f1 clara
        result = decode_constrained(probs_for_fen(three))
        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [])


class AdjacentKingsTests(unittest.TestCase):
    """C11: reis que se tocam nunca são uma posição -- e o de antes deixava passar."""

    TOUCHING = "8/8/8/3kK3/8/8/8/2q5"

    def test_touching_kings_are_repaired_through_the_cheapest_squares(self) -> None:
        """O rei preto lido em d5 era a dama, e a "dama" de c1 era o rei -- o par de trocas
        mais barato que separa os reis (o de antes do C11 devolvia a posição intacta)."""
        probs = probs_for_fen(self.TOUCHING, confidence=0.99)
        d5, c1 = square_index("d5"), square_index("c1")
        probs[d5] = 0.0
        probs[d5, PIECE_TO_IDX["k"]] = 0.60
        probs[d5, PIECE_TO_IDX["q"]] = 0.40
        probs[c1] = 0.0
        probs[c1, PIECE_TO_IDX["q"]] = 0.55
        probs[c1, PIECE_TO_IDX["k"]] = 0.45

        result = decode_constrained(probs)

        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(sorted(square for square, _, _ in result.changed_squares), sorted([d5, c1]))
        self.assertEqual(result.class_indices[d5], PIECE_TO_IDX["q"])
        self.assertEqual(result.class_indices[c1], PIECE_TO_IDX["k"])

    def test_the_classic_rules_let_touching_kings_pass(self) -> None:
        result = decode_constrained(probs_for_fen(self.TOUCHING), rules=CLASSIC_RULES)
        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [])

    def test_kings_a_knights_move_apart_are_fine(self) -> None:
        result = decode_constrained(probs_for_fen("8/8/8/3k4/8/4K3/8/8"))
        self.assertTrue(result.constraints_satisfied)
        self.assertEqual(result.changed_squares, [])


class OrcamentoSemRelogioTests(unittest.TestCase):
    """A busca sujeita às regras para por expansões, e não pelo relógio (S-834).

    Com o prazo de 0,5 s da S-358 a mesma matriz de probabilidades podia sair em FEN diferente numa
    máquina carregada, em rodadas paralelas ou na primeira chamada lenta de um processo: o
    relatório de campo deixava de ser reproduzível. O teto é de expansões, e só dele.
    """

    def _kemeri(self) -> np.ndarray:
        """A leitura do `Kemeri` sem rei branco (S-11): o reparo precisa da busca."""
        probs = probs_for_fen(KEMERI_NO_WHITE_KING, confidence=0.80)
        a7 = square_index("a7")
        probs[a7] = 0.01
        probs[a7, PIECE_TO_IDX["Q"]] = 0.60
        probs[a7, PIECE_TO_IDX["K"]] = 0.30
        return probs / probs.sum(axis=1, keepdims=True)

    def test_um_relogio_que_corre_nao_muda_o_resultado(self) -> None:
        from unittest import mock

        esperado = decode_constrained(self._kemeri())
        instantes = iter(float(segundo) for segundo in range(10**6))

        # Um segundo a cada pergunta das horas: a máquina mais carregada que se pode imaginar.
        with mock.patch("time.monotonic", side_effect=lambda: next(instantes)):
            sob_carga = decode_constrained(self._kemeri())

        self.assertTrue(esperado.constraints_satisfied)
        self.assertEqual(esperado.fen_board, KEMERI_FIXED)
        self.assertEqual(sob_carga.fen_board, esperado.fen_board)
        self.assertEqual(sob_carga.constraints_satisfied, esperado.constraints_satisfied)
        self.assertEqual(sob_carga.changed_squares, esperado.changed_squares)


class ViolacaoTipadaTests(unittest.TestCase):
    """S-835: `only_king_missing` confere o tipo da violação, e não o começo da frase.

    Conferia `startswith("falta o rei")`, frase escrita também em `fen_utils` e `ui/legality`:
    reescrever uma delas mudava a orientação sem teste nenhum falhar.
    """

    def test_a_frase_nao_decide(self) -> None:
        from chess_diagram_ocr.decode import DecodeResult, TipoDeViolacao

        sem_rei = DecodeResult(
            class_indices=[0] * 64, fen_board="8/8/8/8/8/8/8/8", log_prob=0.0, changed_squares=[],
            constraints_satisfied=False, remaining_problems=("o rei branco sumiu",),
            remaining_kinds=(TipoDeViolacao.REI_FALTANDO,),
        )
        self.assertTrue(sem_rei.only_king_missing)

    def test_a_busca_registra_o_tipo(self) -> None:
        from chess_diagram_ocr.decode import TipoDeViolacao

        probs = probs_for_fen("4k3/8/8/8/8/8/8/8", confidence=0.99)
        probs[:, PIECE_TO_IDX["K"]] = 1e-6
        probs = probs / probs.sum(axis=1, keepdims=True)

        result = decode_constrained(probs)

        self.assertEqual(result.remaining_kinds, (TipoDeViolacao.REI_FALTANDO,))
        self.assertTrue(result.only_king_missing)
