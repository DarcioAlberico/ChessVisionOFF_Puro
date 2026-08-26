"""A linha impressa jogada sobre uma posição (S-208/S-283).

**É a metade que a S-208 ficou devendo por dois dias**, e a spec dela dizia exatamente o que
faltava: *"não entra `validar` -- a legalidade pela posição, com o `chess`. [...] a metade que valida
é a que dá o PGN de partida"*.

O que estes testes travam é o contrato da S-15 aplicado a lance: **propõe, marca, não reescreve
calado**. Não há caminho por onde `validar` conserte um lance -- ela para, e diz onde.

E travam o falso positivo que a metade de cima registrou como insolúvel sem legalidade:
`Capablanca` p72, `7` + `2` → `72`, *"estruturalmente idêntico ao caso que se quer consertar"*.
"""

from __future__ import annotations

import unittest

import chess

from chess_diagram_ocr.text.notacao import LETRA_DA_FIGURINA, para_ingles, validar

ITALIANA = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")


class FigurinaTests(unittest.TestCase):
    def test_a_figurina_vira_a_inicial_inglesa(self) -> None:
        self.assertEqual(para_ingles("♗xb7"), "Bxb7")
        self.assertEqual(para_ingles("♞f6"), "Nf6")

    def test_as_duas_cores_do_mesmo_glifo_dao_a_mesma_letra(self) -> None:
        """**A cor não está na tabela, e não pode estar.** O livro imprime um conjunto só de
        glifos para os dois lados -- a S-208 registra isso como "insolúvel visualmente"."""
        self.assertEqual(LETRA_DA_FIGURINA["♗"], LETRA_DA_FIGURINA["♝"])

    def test_o_que_nao_e_figurina_passa_igual(self) -> None:
        """As iniciais de outras línguas ficam como estão: `R` é *rook* e *rei*, `C` é *cavalo* e
        nada em inglês. Traduzi-las trocaria uma peça por outra num lance que o tabuleiro aceita."""
        self.assertEqual(para_ingles("Cf3"), "Cf3")
        self.assertEqual(para_ingles("exd5"), "exd5")


class LinhaQueFechaTests(unittest.TestCase):
    def test_uma_linha_com_figurinas_vira_lances(self) -> None:
        lida = validar("4.♘g5 d5 5.exd5 ♘a5 6.♗b5+".split(), ITALIANA)
        self.assertTrue(lida.fechou)
        self.assertEqual(lida.san, ("Ng5", "d5", "exd5", "Na5", "Bb5+"))

    def test_o_lado_sai_da_posicao_e_nao_do_glifo(self) -> None:
        """O mesmo `♘f6` é das pretas nesta posição e seria das brancas na anterior. Quem sabe é
        o tabuleiro, e é por isso que `validar` recebe um e `fatiar` não."""
        pretas = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1")
        lida = validar(["♘f6"], pretas)
        self.assertTrue(lida.fechou)
        self.assertEqual(lida.san, ("Nf6",))
        self.assertEqual(lida.lances[0].move, chess.Move.from_uci("g8f6"))

    def test_o_numero_grudado_no_lance_e_entendido(self) -> None:
        """`19...♖g8` é como o livro imprime a resposta das pretas, e o token inteiro não casa com
        lance nenhum -- é o `COMPOSTO` que a S-208 já tratava em `fatiar`."""
        pretas = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 4 4")
        lida = validar(["4...♗c5"], pretas)
        self.assertTrue(lida.fechou)
        self.assertEqual(lida.san, ("Bc5",))
        self.assertEqual(lida.lances[0].numero, 4)

    def test_o_sufixo_de_avaliacao_nao_atrapalha(self) -> None:
        lida = validar("4.♘g5!? d5 5.exd5±".split(), ITALIANA)
        self.assertTrue(lida.fechou)
        self.assertEqual(lida.san, ("Ng5", "d5", "exd5"))

    def test_a_promocao_sobrevive_ao_corte_de_sufixo(self) -> None:
        """`e8=Q+` perde o `+` e mantém o `=Q`: o `=` do sufixo só cai depois da peça."""
        board = chess.Board("8/4P3/8/8/8/8/8/K6k w - - 0 1")
        self.assertEqual(validar(["e8=Q+"], board).san, ("e8=Q",))

    def test_o_roque_com_zero_e_aceito_como_o_livro_o_escreve(self) -> None:
        lida = validar(["4.0-0"], ITALIANA)
        self.assertTrue(lida.fechou)
        self.assertEqual(lida.san, ("O-O",))

    def test_o_resultado_fecha_a_linha_e_o_que_vem_depois_e_prosa(self) -> None:
        lida = validar("4.♘g5 d5 1-0 and White won easily".split(), ITALIANA)
        self.assertTrue(lida.fechou)
        self.assertEqual(lida.san, ("Ng5", "d5"))

    def test_o_tabuleiro_que_entrou_nao_e_modificado(self) -> None:
        antes = ITALIANA.fen()
        validar("4.♘g5 d5".split(), ITALIANA)
        self.assertEqual(ITALIANA.fen(), antes)


class LinhaQueNaoFechaTests(unittest.TestCase):
    """O contrato da S-15: para, diz onde, e não reescreve nada."""

    def test_lance_ilegal_para_a_linha_e_nomeia_o_motivo(self) -> None:
        lida = validar("4.♘g5 d5 5.exd6".split(), ITALIANA)
        self.assertFalse(lida.fechou)
        self.assertEqual(lida.san, ("Ng5", "d5"))
        self.assertEqual(lida.token, "5.exd6")
        self.assertIn("não é legal", lida.motivo)
        self.assertEqual(lida.posicao, 2)

    def test_o_que_nao_e_lance_diz_que_nao_e_lance(self) -> None:
        """Leitura de glifo errada e posição errada pedem coisas diferentes de quem conferir."""
        lida = validar(["4.♘g5", "xyz9"], ITALIANA)
        self.assertFalse(lida.fechou)
        self.assertIn("não é um lance", lida.motivo)

    def test_lance_ambiguo_diz_que_falta_a_coluna(self) -> None:
        board = chess.Board("4k3/8/8/8/8/8/4K3/R6R w - - 0 1")
        lida = validar(["Rd1"], board)
        self.assertFalse(lida.fechou)
        self.assertIn("qual das peças", lida.motivo)

    def test_numero_de_lance_que_nao_bate_com_a_posicao_e_acusado(self) -> None:
        """**O falso positivo que só a legalidade separa** (S-208): `Capablanca` p72, `7` + `2`
        virando `72`. O número é conferido, e não obedecido -- quem decide a vez é a posição."""
        lida = validar(["72.♘g5"], ITALIANA)
        self.assertFalse(lida.fechou)
        self.assertIn("lance 72", lida.motivo)
        self.assertIn("no 4", lida.motivo)

    def test_linha_sem_lance_nenhum_devolve_vazio_sem_levantar(self) -> None:
        lida = validar(["In", "1968", "he", "lost"], ITALIANA)
        self.assertEqual(lida.lances, ())

    def test_o_numero_e_a_reticencia_soltos_nao_sao_lance_nem_erro(self) -> None:
        """`4 ... ♗c5` é como a segmentação às vezes separa o que o livro imprimiu junto: os dois
        primeiros tokens não são lance, e não podem ser contados como erro por não serem."""
        lida = validar(["4", "...", "♗c5"], ITALIANA)
        self.assertEqual(lida.lances, ())
        self.assertIn("não é legal", lida.motivo)
        self.assertEqual(lida.token, "♗c5")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
