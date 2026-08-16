"""O índice por nome (S-87): onde cada partida mora no arquivo.

Três coisas podem transformar este índice numa fonte de resposta errada, e cada uma tem teste:
a chave instável entre execuções, o offset de uma base que não é mais a mesma, e a colisão de
hash devolvendo a partida de outro par.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.games_index import (
    _read_game_at,
    build_index,
    index_fingerprint,
    lookup_pair,
    pair_hash,
    positions_of,
)

IMORTAL = "1. e4 e5 2. f4 exf4 3. Bc4 Qh4+ 4. Kf1 b5 5. Bxb5 Nf6"
OUTRA = "1. d4 d5 2. c4 e6 3. Nc3 Nf6"

PGN = f"""[Event "London"]
[Site "London ENG"]
[Date "1851.06.21"]
[White "Anderssen, Adolf"]
[Black "Kieseritzky, Lionel"]
[Result "1-0"]

{IMORTAL} 1-0

[Event "Revanche"]
[Date "1852.01.01"]
[White "Kieseritzky, Lionel"]
[Black "Anderssen, Adolf"]
[Result "0-1"]

{OUTRA} 0-1

[Event "Outro"]
[Date "1860.01.01"]
[White "Morphy, Paul"]
[Black "Harrwitz, Daniel"]
[Result "1/2-1/2"]

{OUTRA} 1/2-1/2
"""


class ChaveTests(unittest.TestCase):
    def test_a_chave_e_a_mesma_em_outro_processo(self) -> None:
        """**O defeito que mataria o índice em silêncio.** O `hash()` do Python é aleatorizado
        por processo desde a 3.3: um índice gravado hoje responderia zero amanhã, sem erro
        nenhum. O teste roda um interpretador separado, que é onde isso apareceria.
        """
        codigo = (
            "import sys; sys.path.insert(0, 'src');"
            "from chess_diagram_ocr.games_index import pair_hash;"
            "print(pair_hash(('anderssen', 'kieseritzky')))"
        )
        saida = subprocess.run(
            [sys.executable, "-c", codigo], capture_output=True, text=True, check=True, cwd=Path.cwd()
        )
        self.assertEqual(int(saida.stdout.strip()), pair_hash(("anderssen", "kieseritzky")))

    def test_a_ordem_das_cores_muda_a_chave(self) -> None:
        """Brancas e pretas não são intercambiáveis na chave -- quem quer os dois lados
        pergunta duas vezes, e é o que `lookup_pair` faz."""
        self.assertNotEqual(pair_hash(("a", "b")), pair_hash(("b", "a")))


class ConsultaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(PGN, encoding="utf-8")
        self.indice = self.raiz / "indice.sqlite"
        build_index(self.base, self.indice)

    def tearDown(self) -> None:
        self.pasta.cleanup()

    def test_acha_a_partida_pelo_par(self) -> None:
        (partida,) = lookup_pair(("anderssen", "kieseritzky"), self.base, self.indice, both_colors=False)
        self.assertEqual(partida.headers["Event"], "London")
        self.assertIn("Bxb5", partida.movetext)

    def test_procura_os_dois_lados_por_padrao(self) -> None:
        """A legenda do livro não promete quem tinha as brancas."""
        partidas = lookup_pair(("anderssen", "kieseritzky"), self.base, self.indice)
        self.assertEqual({p.headers["Event"] for p in partidas}, {"London", "Revanche"})

    def test_par_que_nao_existe_devolve_vazio(self) -> None:
        self.assertEqual(lookup_pair(("tal", "botvinnik"), self.base, self.indice), [])

    def test_o_teto_limita_a_leitura(self) -> None:
        self.assertEqual(len(lookup_pair(("anderssen", "kieseritzky"), self.base, self.indice, limit=1)), 1)

    def test_base_trocada_nao_responde_com_offset_velho(self) -> None:
        """**Offsets são do arquivo.** Numa base diferente cada um aponta para o meio de outra
        partida, e a leitura devolveria movetext cortado com cara de partida."""
        outra = self.raiz / "outra.pgn"
        outra.write_text(PGN * 3, encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_index", level="WARNING"):
            self.assertEqual(lookup_pair(("anderssen", "kieseritzky"), outra, self.indice), [])

    def test_colisao_de_hash_nao_vira_resposta_errada(self) -> None:
        """Uma colisão custa uma leitura descartada, e não a partida de outro par na lista."""
        conexao = sqlite3.connect(self.indice)
        # Aponta o par procurado para o offset da partida do Morphy, como uma colisao faria.
        # O `0` e o numero do arquivo: com uma base so, e sempre a primeira (S-93).
        offset = PGN.index('[Event "Outro"]')
        conexao.execute("INSERT INTO games VALUES (?, ?, ?)", (pair_hash(("tal", "botvinnik")), offset, 0))
        conexao.commit()
        conexao.close()
        self.assertEqual(lookup_pair(("tal", "botvinnik"), self.base, self.indice), [])

    def test_indice_ausente_devolve_vazio_em_vez_de_levantar(self) -> None:
        """Quem chama tem a lista do cache como caminho alternativo; um erro tiraria os dois."""
        self.assertEqual(lookup_pair(("anderssen", "kieseritzky"), self.base, self.raiz / "nao_existe"), [])

    def test_o_offset_que_nao_comeca_partida_nao_vira_meia_partida(self) -> None:
        with self.base.open("rb") as fh:
            self.assertIsNone(_read_game_at(fh, 40))

    def test_o_indice_parcial_nao_fica_no_lugar_do_bom(self) -> None:
        self.assertEqual(list(self.raiz.glob("*.parcial")), [])

    def test_acha_em_que_lance_a_posicao_aparece(self) -> None:
        """O índice mudou *como se chega* às partidas, não o que conta como casamento: as 64
        casas continuam tendo de bater."""
        import chess

        tabuleiro = chess.Board()
        for lance in ("e4", "e5", "f4", "exf4", "Bc4", "Qh4+", "Kf1"):
            tabuleiro.push_san(lance)
        partidas = lookup_pair(("anderssen", "kieseritzky"), self.base, self.indice)
        achados = positions_of(partidas, tabuleiro.board_fen())
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0][1], tabuleiro.fullmove_number)

    def test_posicao_ausente_nao_casa_com_partida_nenhuma(self) -> None:
        partidas = lookup_pair(("anderssen", "kieseritzky"), self.base, self.indice)
        self.assertEqual(positions_of(partidas, "8/8/8/8/8/8/4K3/4k3"), [])


class DuasBasesTests(unittest.TestCase):
    """O índice sobre mais de um arquivo (S-93) -- o offset sozinho deixou de identificar."""

    OUTRO = (
        '[Event "Havana"]\n[Site "Havana CUB"]\n[Date "1921.03.15"]\n'
        '[White "Capablanca, Jose Raul"]\n[Black "Lasker, Emanuel"]\n[Result "1-0"]\n\n'
        "1. d4 d5 2. c4 e6 3. Nc3 Nf6 1-0\n"
    )

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.raiz = Path(self.pasta.name)
        self.primeira = self.raiz / "a_primeira.pgn"
        self.primeira.write_text(PGN, encoding="utf-8")
        self.segunda = self.raiz / "b_segunda.pgn"
        self.segunda.write_text(self.OUTRO, encoding="utf-8")
        self.bases = [self.primeira, self.segunda]
        self.indice = self.raiz / "indice.sqlite"
        build_index(self.bases, self.indice)

    def tearDown(self) -> None:
        self.pasta.cleanup()

    def test_acha_a_partida_que_esta_na_segunda_base(self) -> None:
        """O caso real: a partida procurada estava no arquivo que a busca não abria."""
        (partida,) = lookup_pair(("capablanca", "lasker"), self.bases, self.indice, both_colors=False)
        self.assertEqual(partida.headers["Event"], "Havana")
        self.assertIn("d4", partida.movetext)

    def test_a_primeira_base_continua_respondendo(self) -> None:
        partidas = lookup_pair(("anderssen", "kieseritzky"), self.bases, self.indice)
        self.assertEqual({p.headers["Event"] for p in partidas}, {"London", "Revanche"})

    def test_o_offset_nao_e_lido_no_arquivo_errado(self) -> None:
        """**O defeito que a coluna `file` existe para impedir.** O byte 0 começa uma partida
        nas duas bases. Sem saber de qual arquivo é o offset, a consulta leria a partida da
        primeira, a conferência de nomes a descartaria, e a partida da segunda base não
        voltaria -- em silêncio, que é exatamente como uma base inteira ficou invisível.
        """
        partidas = lookup_pair(("capablanca", "lasker"), self.bases, self.indice)
        self.assertEqual(len(partidas), 1)
        self.assertEqual(partidas[0].headers["White"], "Capablanca, Jose Raul")
        self.assertIn("d4", partidas[0].movetext, "o movetext é o do arquivo certo")

    def test_acrescentar_um_arquivo_invalida_o_indice(self) -> None:
        """Ele não sabe as partidas do arquivo novo, e responder sem elas seria dizer "a base
        não tem" sobre um arquivo que ninguém indexou."""
        terceira = self.raiz / "c_terceira.pgn"
        terceira.write_text(self.OUTRO, encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_index", level="WARNING"):
            self.assertEqual(lookup_pair(("capablanca", "lasker"), [*self.bases, terceira], self.indice), [])

    def test_indice_de_formato_anterior_avisa_em_vez_de_quebrar(self) -> None:
        """Com uma base só, o fingerprint da versão 1 é idêntico ao da 2: sem a marca de
        versão, um índice antigo passaria pela conferência e quebraria no `SELECT ... file`."""
        antigo = self.raiz / "antigo.sqlite"
        conexao = sqlite3.connect(antigo)
        conexao.execute("CREATE TABLE games (pair INTEGER NOT NULL, offset INTEGER NOT NULL)")
        conexao.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conexao.execute("INSERT INTO meta VALUES ('database', ?)", (index_fingerprint(self.primeira),))
        conexao.commit()
        conexao.close()
        with self.assertLogs("chess_diagram_ocr.games_index", level="WARNING"):
            self.assertEqual(lookup_pair(("anderssen", "kieseritzky"), self.primeira, antigo), [])


if __name__ == "__main__":
    unittest.main()
