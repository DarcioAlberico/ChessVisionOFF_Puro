"""O PGN que vem com o livro (S-585, S-586).

O caso que abriu o item é real: no PGN do Harikrishna as 21 partidas sem `[FEN]` têm duas linhas
em branco entre o cabeçalho e os lances, e o `read_game` partia cada uma em duas. A forma do texto
abaixo é a daquele arquivo, com CRLF e tudo.
"""

from __future__ import annotations

import io
import unittest

import chess
import chess.pgn

from chess_diagram_ocr import estudo_arquivo
from chess_diagram_ocr import pgn_do_livro as livro

PARTIDA_PARTIDA = (
    '[Event "Chapter 1"]\r\n[Site "Game 1"]\r\n[White "Chapter 1"]\r\n[Black "Game 1"]\r\n'
    '[Result "*"]\r\n\r\n\r\n1.e4 e6 2.d4 d5 3.Nc3\r\n *\r\n\r\n\r\n'
    '[Event "Chapter 1"]\r\n[Site "Game 2"]\r\n[Result "*"]\r\n'
    '[SetUp "1"]\r\n[FEN "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"]\r\n\r\n'
    "1.e4 e6 2.d4 d5 3.Nc3 c5 (3...a6 4.Nf3) 4.exd5 exd5 5.dxc5\r\n *\r\n"
)


def _partidas(texto: str) -> list[chess.pgn.Game]:
    fluxo = livro.fluxo_tolerante(texto)
    achadas = []
    while (jogo := chess.pgn.read_game(fluxo)) is not None:
        achadas.append(jogo)
    return achadas


class FluxoToleranteTests(unittest.TestCase):
    def test_a_linha_em_branco_a_mais_nao_parte_a_partida(self) -> None:
        partidas = _partidas(PARTIDA_PARTIDA)
        self.assertEqual(2, len(partidas))
        self.assertEqual("Game 1", partidas[0].headers["Site"])
        self.assertEqual("Nc3", partidas[0].end().san())

    def test_sabotagem_sem_o_fluxo_a_partida_se_parte(self) -> None:
        """O defeito que o fluxo conserta, de pé: sem ele saem três partidas, e a primeira é só cabeçalho."""
        fluxo = io.StringIO(PARTIDA_PARTIDA)
        partidas = []
        while (jogo := chess.pgn.read_game(fluxo)) is not None:
            partidas.append(jogo)
        self.assertEqual(3, len(partidas))
        self.assertEqual([], partidas[0].variations)

    def test_antes_de_outro_cabecalho_as_duas_partidas_ficam_separadas(self) -> None:
        """Cabeçalho sem lance seguido de outra partida são duas partidas: juntá-las daria à
        primeira o cabeçalho da segunda."""
        texto = '[Event "A"]\n[Site "1"]\n\n\n[Event "B"]\n[Site "2"]\n\n1.e4 *\n'
        partidas = _partidas(texto)
        self.assertEqual(["A", "B"], [p.headers["Event"] for p in partidas])
        self.assertEqual("e4", partidas[1].end().san())

    def test_o_abrir_pgn_do_estudo_guarda_o_capitulo(self) -> None:
        estudos = estudo_arquivo.estudos_de_pgn(PARTIDA_PARTIDA)
        self.assertEqual(2, len(estudos))
        self.assertEqual("Game 1", estudos[0].jogo.headers["Site"])


class LegendaTests(unittest.TestCase):
    def test_o_lance_sem_avaliacao_nem_xeque(self) -> None:
        self.assertEqual("5.dxc5", livro.lance_da_legenda("5.dxc5±"))
        self.assertEqual("6.Qe2", livro.lance_da_legenda("6.Qe2+!"))
        self.assertEqual("3...c5", livro.lance_da_legenda("3...c5?!"))
        self.assertEqual("8.O-O", livro.lance_da_legenda("8.0-0²"))
        self.assertEqual("12.O-O-O", livro.lance_da_legenda("12.0-0-0"))
        self.assertIsNone(livro.lance_da_legenda("White"))

    def test_desambiguacao_a_mais_do_livro(self) -> None:
        self.assertEqual("12.Nc3", livro.sem_desambiguacao("12.Nbc3"))
        self.assertEqual("12...Rxe8", livro.sem_desambiguacao("12...Raxe8"))
        self.assertEqual("5.dxc5", livro.sem_desambiguacao("5.dxc5"))


class IndiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.indice = livro.IndiceDoLivro(_partidas(PARTIDA_PARTIDA))

    def test_o_rotulo_e_o_do_livro(self) -> None:
        rotulos = [no.rotulo for no in self.indice.nos]
        self.assertIn("3...c5", rotulos)
        self.assertIn("5.dxc5", rotulos)

    def test_a_ordem_e_a_de_leitura(self) -> None:
        """A principal antes das variantes, e a variante antes do lance seguinte da principal."""
        rotulos = [no.rotulo for no in self.indice.nos if no.secao == "Game 2"]
        self.assertEqual(["1.e4", "1...e6", "2.d4", "2...d5", "3.Nc3", "3...c5", "4.exd5", "4...exd5", "5.dxc5", "3...a6", "4.Nf3"], rotulos)

    def test_achar_pelo_rotulo_no_capitulo(self) -> None:
        achados = self.indice.com_rotulo("Chapter 1", "3.Nc3")
        self.assertEqual(2, len(achados))
        self.assertEqual([], self.indice.com_rotulo("Chapter 2", "3.Nc3"))

    def test_achar_pela_posicao_e_voltar_ao_no(self) -> None:
        depois = chess.Board()
        for lance in ("e4", "e6", "d4", "d5", "Nc3", "a6"):
            depois.push_san(lance)
        (k,) = self.indice.com_posicao(depois.board_fen())
        registro = self.indice.nos[k]
        self.assertEqual(("3...a6", "w"), (registro.rotulo, registro.lado))
        no = self.indice.no(k)
        assert no is not None
        self.assertEqual(depois.fen(), no.board().fen())


if __name__ == "__main__":
    unittest.main()
