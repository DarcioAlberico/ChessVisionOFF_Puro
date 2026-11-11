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

    def test_reis_adjacentes_sao_fatais(self) -> None:
        """S-890: quando nenhuma das duas vezes torna a posição legal, trocar a vez não
        conserta nada. Era "lado a jogar", o painel mandava trocar, e a gravação não perguntava:
        a amostra entrava no dataset sem a marca de ilegal confirmada."""
        casos = {
            "reis adjacentes": ("8/8/8/3kK3/8/8/8/8", {"d5", "e5"}),
            "os dois em xeque": ("4k3/4R3/8/8/8/8/4r3/4K3", {"e8", "e7", "e2", "e1"}),
        }
        for caso, (colocacao, casas) in casos.items():
            for vez in ("w", "b"):
                with self.subTest(caso=caso, vez=vez):
                    explicacao = explain_position(f"{colocacao} {vez} - - 0 1")
                    self.assertTrue(explicacao.is_fatal)
                    self.assertEqual(explicacao.label, "ilegal")
                    self.assertNotIn("Só o lado a jogar", explicacao.summary())
                    self.assertTrue(casas <= named(explicacao), named(explicacao))
                    pergunta = illegal_save_question(f"{colocacao} {vez} - - 0 1")
                    self.assertIsNotNone(pergunta)
                    assert pergunta is not None
                    self.assertIn("nenhum lado a jogar torna a posição legal", pergunta)


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


class OQueAPessoaLeTests(unittest.TestCase):
    """O texto do painel e da caixa de gravação, frase inteira (S-873).

    O painel de legalidade da S-21 é texto: o problema, onde ele está e o material, no
    `lbl_legalidade` e no `lbl_material` do painel de resultado, e na caixa que pergunta antes de
    gravar. Uma frase trocada, um separador perdido ou um problema que some da pergunta é o defeito
    que a pessoa vê -- e os testes acima conferiam um pedaço de cada frase, com o que o mutator da
    S-803 trocava a frase por vazio, ou a vírgula por nada, sem nenhum deles reprovar.
    """

    def test_o_resumo_de_cada_problema(self) -> None:
        casos = {
            "8/8/8/8/8/8/8/8 w - - 0 1": "Posição ilegal: tabuleiro vazio; falta o rei branco; falta o rei preto",
            "4k3/8/8/8/8/8/8/K3K3 w - - 0 1": "Posição ilegal: mais de um rei da mesma cor (a1, e1)",
            "4k3/pppppppp/p7/8/8/8/8/4K3 w - - 0 1": (
                "Posição ilegal: peões pretos demais (a7, b7, c7, d7, e7, f7, g7, h7, a6)"
            ),
            "nnnnknnn/nnnnnnnn/n7/8/8/8/8/4K3 w - - 0 1": (
                "Posição ilegal: peças pretas demais (a8, b8, c8, d8, e8, f8, g8, h8, a7, b7, c7, d7, e7, f7, g7, "
                "h7, a6)"
            ),
            "P3k3/8/8/8/8/8/8/4K3 w - - 0 1": "Posição ilegal: peão na primeira ou na oitava fila (a8)",
            "R3k3/8/8/8/8/8/8/4K3 w - - 0 1": "Só o lado a jogar não fecha: o lado que não joga está em xeque (a8, e8)",
            "k6k/8/8/8/8/8/8/r3K2r w - - 0 1": (
                "Posição ilegal: mais de um rei da mesma cor (a8, h8); configuração de xeque impossível (a1, e1, h1)"
            ),
            "k3r3/k7/8/8/8/3n1n2/8/4K3 w - - 0 1": (
                "Posição ilegal: mais de um rei da mesma cor (a8, a7); peças demais dando xeque (e8, d3, f3, e1); "
                "configuração de xeque impossível (e8, d3, f3, e1)"
            ),
        }
        for fen, resumo in casos.items():
            with self.subTest(fen=fen):
                self.assertEqual(explain_position(fen).summary(), resumo)

    def test_a_linha_de_material(self) -> None:
        """Na ordem de valor, a contagem de cada símbolo, e o travessão no lado que não tem nada."""
        casos = {
            "8/8/8/8/8/8/PP6/KQ6": "brancas: K×1 Q×1 P×2 | pretas: —",
            "kn6/pp6/8/8/8/8/8/8": "brancas: — | pretas: k×1 n×1 p×2",
            "8/8/8/8/8/8/8/8": "brancas: — | pretas: —",
        }
        for colocacao, linha in casos.items():
            with self.subTest(colocacao=colocacao):
                self.assertEqual(explain_position(colocacao).material_line(), linha)

    def test_a_pergunta_nomeia_todo_problema_fatal_e_nenhum_de_lado_a_jogar(self) -> None:
        """A primeira frase da caixa é a lista do que está errado nas peças. O que é palpite
        sobre a vez -- xeque invertido, xeque demais, xeque impossível -- fica de fora mesmo
        quando a posição pergunta por outro motivo."""
        casos = {
            "8/8/8/8/8/8/8/8 w - - 0 1": "tabuleiro vazio; falta o rei branco; falta o rei preto",
            "4k3/pppppppp/p7/8/8/8/8/4K3 w - - 0 1": "peões pretos demais (a7, b7, c7, d7, e7, f7, g7, h7, a6)",
            "4k3/8/8/8/NNNNNNNN/NNNNNNNN/8/4K3 w - - 0 1": (
                "peças brancas demais (a4, b4, c4, d4, e4, f4, g4, h4, a3, b3, c3, d3, e3, f3, g3, h3, e1)"
            ),
            "nnnnknnn/nnnnnnnn/n7/8/8/8/8/4K3 w - - 0 1": (
                "peças pretas demais (a8, b8, c8, d8, e8, f8, g8, h8, a7, b7, c7, d7, e7, f7, g7, h7, a6)"
            ),
            "P3k3/8/8/8/8/8/8/4K3 w - - 0 1": "peão na primeira ou na oitava fila (a8)",
            "R3k3/8/8/8/8/8/8/8 w - - 0 1": "falta o rei branco",
            "k6k/8/8/8/8/8/8/r3K2r w - - 0 1": "mais de um rei da mesma cor (a8, h8)",
            "k3r3/k7/8/8/8/3n1n2/8/4K3 w - - 0 1": "mais de um rei da mesma cor (a8, a7)",
        }
        for fen, problemas in casos.items():
            with self.subTest(fen=fen):
                pergunta = illegal_save_question(fen)
                assert pergunta is not None
                self.assertEqual(pergunta.split("\n")[0], f"Esta posição é ilegal: {problemas}.")

    def test_a_pergunta_inteira(self) -> None:
        self.assertEqual(
            illegal_save_question("4k3/8/8/8/8/8/8/K3K3 w - - 0 1"),
            "Esta posição é ilegal: mais de um rei da mesma cor (a1, e1).\n\n"
            "brancas: K×2 | pretas: k×1\n\n"
            "Se o diagrama é assim mesmo -- estrutura de peões, final parcial, tabuleiro de "
            "ilustração --, salvar está correto e a amostra entra no treino marcada como "
            "confirmada.\n"
            "Se foi o leitor que errou uma casa, cancele e conserte o tabuleiro.\n\n"
            "Salvar mesmo assim?",
        )


if __name__ == "__main__":
    unittest.main()
