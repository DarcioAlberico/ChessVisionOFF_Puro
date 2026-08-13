"""A base de partidas como terceira fonte de verdade (S-72).

Sem a base de 9,7 GB: um PGN de três partidas escrito na hora cobre o que pode quebrar --
casar sobrenome contra `Sobrenome, Nome`, colher só as partidas pedidas, achar o lance cuja
posição bate, e o teto por par.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

import chess

from chess_diagram_ocr.gallery_scan import GalleryEntry
from chess_diagram_ocr.games_db import (
    GameRecord,
    default_database_path,
    match_entries,
    pair_from_caption,
    scan_by_players,
    surname,
)

IMORTAL = "1. e4 e5 2. f4 exf4 3. Bc4 Qh4+ 4. Kf1 b5 5. Bxb5 Nf6 6. Nf3 Qh6 7. d3 Nh5"
OUTRA = "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 5. e3 O-O"

PGN = f"""[Event "London"]
[Site "London ENG"]
[Date "1851.06.21"]
[Round "?"]
[White "Anderssen, Adolf"]
[Black "Kieseritzky, Lionel"]
[Result "1-0"]
[ECO "C33"]

{IMORTAL} 1-0

[Event "Revanche"]
[Site "Paris"]
[Date "1852.??.??"]
[White "Anderssen, Adolf"]
[Black "Kieseritzky, Lionel"]
[Result "0-1"]

{OUTRA} 0-1

[Event "Outro torneio"]
[Site "Berlim"]
[Date "1860.??.??"]
[White "Morphy, Paul"]
[Black "Harrwitz, Daniel"]
[Result "1/2-1/2"]

{OUTRA} 1/2-1/2
"""


def colocacao_apos(movetext: str, lances: int) -> tuple[str, int, bool]:
    """A colocação depois de N meios-lances, com o número do lance e a vez."""
    tabuleiro = chess.Board()
    for token in movetext.split():
        if token[0].isdigit():
            continue
        tabuleiro.push_san(token)
        lances -= 1
        if lances == 0:
            break
    return tabuleiro.board_fen(), tabuleiro.fullmove_number, tabuleiro.turn == chess.WHITE


class NomesTests(unittest.TestCase):
    def test_sobrenome_ignora_o_nome_e_o_acento(self) -> None:
        self.assertEqual(surname("De Castellvi, Francisco"), "de castellvi")
        self.assertEqual(surname("Réti, Richard"), "reti")
        self.assertEqual(surname("Coull"), "coull")

    def test_par_sai_da_legenda_pelo_interpretador_da_s16(self) -> None:
        self.assertEqual(pair_from_caption("Coull - Stanciu\n3 b5 4 b6"), ("coull", "stanciu"))

    def test_legenda_sem_nomes_nao_inventa_par(self) -> None:
        self.assertIsNone(pair_from_caption("2 . . .\n3 b5\n4 b6"))


class ScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.base = Path(self.pasta.name) / "base.pgn"
        self.base.write_text(PGN, encoding="utf-8")

    def tearDown(self) -> None:
        self.pasta.cleanup()

    def test_colhe_so_o_par_pedido(self) -> None:
        colhidas = scan_by_players(self.base, [("anderssen", "kieseritzky")])
        self.assertEqual(list(colhidas), [("anderssen", "kieseritzky")])
        self.assertEqual(len(colhidas[("anderssen", "kieseritzky")]), 2)

    def test_cabecalhos_da_partida_chegam_inteiros(self) -> None:
        colhidas = scan_by_players(self.base, [("anderssen", "kieseritzky")])
        primeira = colhidas[("anderssen", "kieseritzky")][0]
        self.assertEqual(primeira.headers["Event"], "London")
        self.assertEqual(primeira.headers["Date"], "1851.06.21")
        self.assertEqual(primeira.headers["ECO"], "C33")
        self.assertIn("Anderssen", primeira.label)

    def test_par_invertido_nao_casa(self) -> None:
        """Brancas e pretas não são intercambiáveis: a mesma dupla jogou dos dois lados."""
        self.assertEqual(scan_by_players(self.base, [("kieseritzky", "anderssen")]), {})

    def test_teto_por_par(self) -> None:
        colhidas = scan_by_players(self.base, [("anderssen", "kieseritzky")], max_games_per_pair=1)
        self.assertEqual(len(colhidas[("anderssen", "kieseritzky")]), 1)

    def test_pedido_vazio_nao_abre_o_arquivo(self) -> None:
        """A base tem 9,7 GB: varrê-la para responder "nada" seria caro e inútil."""
        self.assertEqual(scan_by_players(Path("nao_existe.pgn"), []), {})

    def test_cancelar_para_a_varredura(self) -> None:
        cancelado = threading.Event()
        cancelado.set()
        colhidas = scan_by_players(self.base, [("anderssen", "kieseritzky")], cancel=cancelado)
        # O cancelamento é conferido a cada 200 mil partidas: num PGN de três, ele não chega a
        # agir, e o que o teste garante é que a bandeira ligada não quebra a varredura.
        self.assertIn(("anderssen", "kieseritzky"), colhidas)

    def test_a_base_padrao_e_o_maior_pgn_da_pasta(self) -> None:
        (Path(self.pasta.name) / "torneio.pgn").write_text(PGN[:100], encoding="utf-8")
        self.assertEqual(default_database_path(Path(self.pasta.name)), self.base)

    def test_pasta_sem_base_devolve_nada(self) -> None:
        self.assertIsNone(default_database_path(Path(self.pasta.name) / "vazia"))


class MatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.partida = GameRecord(
            headers={"White": "Anderssen, Adolf", "Black": "Kieseritzky, Lionel", "Event": "London"},
            movetext=IMORTAL,
        )
        self.games = {("anderssen", "kieseritzky"): [self.partida]}

    def test_posicao_lida_acha_o_lance_e_a_vez(self) -> None:
        colocacao, lance, vez_branca = colocacao_apos(IMORTAL, 7)  # depois de 4.Kf1
        entrada = GalleryEntry(10, 2, colocacao, caption="Anderssen - Kieseritzky")
        (achado,) = match_entries([entrada], self.games)
        self.assertEqual(achado.key, (10, 2))
        self.assertEqual(achado.move_number, lance)
        self.assertEqual(achado.side_to_move, "w" if vez_branca else "b")
        self.assertEqual(achado.headers["Event"], "London")

    def test_uma_casa_errada_nao_e_casamento_parcial(self) -> None:
        """63 de 64 não é "quase": é outra posição, e preencher headers dali seria mentira."""
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        estragada = colocacao.replace("p", "n", 1)
        entrada = GalleryEntry(10, 2, estragada, caption="Anderssen - Kieseritzky")
        self.assertEqual(match_entries([entrada], self.games), [])

    def test_diagrama_sem_nome_na_legenda_fica_de_fora(self) -> None:
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        entrada = GalleryEntry(10, 2, colocacao, caption="Diagrama 41")
        self.assertEqual(match_entries([entrada], self.games), [])

    def test_posicao_comum_conta_quantas_partidas_a_contem(self) -> None:
        """Posição de abertura casa com toda partida que a atravessou -- e quem consome
        precisa saber disso antes de preencher header nenhum: duas partidas diferentes com a
        mesma posição não dizem de qual delas o diagrama saiu."""
        colocacao, _, _ = colocacao_apos(IMORTAL, 2)  # depois de 1.e4 e5
        segunda = GameRecord(headers={**self.partida.headers, "Event": "Revanche"}, movetext=IMORTAL)
        entrada = GalleryEntry(0, 0, colocacao, caption="Anderssen - Kieseritzky")
        (achado,) = match_entries([entrada], {("anderssen", "kieseritzky"): [self.partida, segunda]})
        self.assertEqual(achado.games_matched, 2)

    def test_lance_ilegal_interrompe_a_partida_sem_derrubar_a_varredura(self) -> None:
        quebrada = GameRecord(headers={"White": "A, A", "Black": "B, B"}, movetext="1. e4 e5 2. Zz9 Nf6")
        posicoes = list(quebrada.positions())
        self.assertEqual(len(posicoes), 2, "para no lance recusado, e devolve o que já leu")


if __name__ == "__main__":
    unittest.main()
