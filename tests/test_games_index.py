"""O índice por nome (S-87): onde cada partida mora no arquivo.

Três coisas podem transformar este índice numa fonte de resposta errada, e cada uma tem teste:
a chave instável entre execuções, o offset de uma base que não é mais a mesma, e a colisão de
hash devolvendo a partida de outro par.
"""

from __future__ import annotations

import gzip
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import chess
from subprocesso import rodar_python

from chess_diagram_ocr import games_index
from chess_diagram_ocr.games_db import GameRecord, database_paths
from chess_diagram_ocr.games_index import (
    _INDICES_DE_BUSCA,
    INDEX_VERSION,
    INDICE_DA_ORDEM,
    IndiceIndisponivel,
    _read_game_at,
    build_index,
    buscar,
    index_fingerprint,
    lookup_pair,
    pair_hash,
    partida_em,
    positions_of,
)
from chess_diagram_ocr.ui.busca_de_partidas import Filtro

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
            "from chess_diagram_ocr.games_index import pair_hash;"
            "print(pair_hash(('anderssen', 'kieseritzky')))"
        )
        saida = rodar_python(codigo)
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
        conexao.execute(
            "INSERT INTO games (pair, file, offset, white, black, event, date, year, welo, belo, elo, result, eco) "
            "VALUES (?, 0, ?, 0, 0, 0, '', 0, 0, 0, 0, '', '')",
            (pair_hash(("tal", "botvinnik")), offset),
        )
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

    def test_o_indice_da_versao_2_e_recusado_com_a_instrucao_de_refazer(self) -> None:
        """A v2 é **legível** -- tem a coluna `file` e responderia. É por isso que a marca de
        versão importa: sem ela, ninguém notaria que o arquivo tem 44% de gordura (S-140).
        """
        v2 = self.raiz / "v2.sqlite"
        conexao = sqlite3.connect(v2)
        conexao.execute(
            "CREATE TABLE games (pair INTEGER NOT NULL, offset INTEGER NOT NULL, file INTEGER NOT NULL)"
        )
        conexao.execute("CREATE INDEX games_pair ON games (pair)")
        conexao.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conexao.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conexao.execute("INSERT INTO meta VALUES ('database', ?)", (index_fingerprint(self.primeira),))
        conexao.execute("INSERT INTO meta VALUES ('version', '2')")
        conexao.commit()
        conexao.close()

        with self.assertLogs("chess_diagram_ocr.games_index", level="WARNING") as registro:
            self.assertEqual(lookup_pair(("anderssen", "kieseritzky"), self.primeira, v2), [])

        aviso = "\n".join(registro.output)
        self.assertIn("'2'", aviso)
        self.assertIn("cvoff-games --build-index", aviso, "o aviso precisa dizer como refazer")

    def test_a_chave_unica_e_o_par_arquivo_offset_e_as_seis_arvores_existem(self) -> None:
        """**A v5 desfaz a v3, e o teste que travava aquele esquema trava este** (S-533).

        A v3 era `WITHOUT ROWID` com `PRIMARY KEY (pair, file, offset)` e nenhum `CREATE INDEX` ao
        lado: uma árvore só, e a chave de busca **era** a árvore -- 38,9 MB contra 21,8 MB num
        índice sintético de um milhão de partidas, medido na S-140.

        Com **seis** caminhos de busca o argumento inverte: a chave composta da v3 tem 14 bytes e
        seria copiada inteira dentro de cada índice secundário, contra os 4 do rowid. A tabela
        voltou a ter `id INTEGER PRIMARY KEY`, e o `UNIQUE (file, offset)` faz o papel de chave
        única que a v3 tinha de graça -- é ele que impede a linha duplicada em silêncio, e é o que
        o teste abaixo afirma. O que este teste trava é que as seis árvores **existem**: sem elas
        toda busca vira varredura de dez milhões de linhas, e nada quebra -- só demora.
        """
        conexao = sqlite3.connect(f"file:{self.indice}?mode=ro", uri=True)
        try:
            criacao = conexao.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'games'"
            ).fetchone()[0]
            indices = conexao.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'games'"
            ).fetchall()
        finally:
            conexao.close()

        self.assertNotIn("WITHOUT ROWID", criacao.upper())
        self.assertIn("ID INTEGER PRIMARY KEY", criacao.upper())
        self.assertIn("UNIQUE (FILE, OFFSET)", criacao.upper())
        nomes = {nome for (nome,) in indices if not nome.startswith("sqlite_autoindex")}
        self.assertEqual({nome for nome, _colunas in _INDICES_DE_BUSCA}, nomes)

    def test_a_mesma_partida_indexada_duas_vezes_nao_duplica(self) -> None:
        """A chave virou única: antes era uma linha duplicada em silêncio, agora seria erro."""
        conexao = sqlite3.connect(self.indice)
        try:
            linha = conexao.execute("SELECT file, offset FROM games LIMIT 1").fetchone()
            conexao.execute(
                "INSERT OR IGNORE INTO games "
                "(pair, file, offset, white, black, event, date, year, welo, belo, elo, result, eco) "
                "VALUES (0, ?, ?, 0, 0, 0, '', 0, 0, 0, 0, '', '')",
                linha,
            )
            conexao.commit()
            repetidas = conexao.execute(
                "SELECT COUNT(*) FROM games WHERE file = ? AND offset = ?", linha
            ).fetchone()[0]
        finally:
            conexao.close()

        self.assertEqual(repetidas, 1)


if __name__ == "__main__":
    unittest.main()


class ParProlificoTests(unittest.TestCase):
    """O `LIMIT` deixou de ser compartilhado pelas duas cores (S-139).

    A consulta era `SELECT offset, file FROM games WHERE pair IN (?,?) LIMIT ?` -- **uma cota
    única para os dois hashes**. Medido no índice real (20.902.904 partidas), Karpov×Kasparov
    tem 245 partidas com um hash e outras tantas com o outro: a cota se esgotava na primeira
    cor e a segunda **nunca era lida**.

    O `both_colors=True` ficava inerte, em silêncio, exatamente nos pares mais citados pelos
    livros -- e o docstring de `lookup_pair` justifica a opção com *"'Coull - Stanciu' é como o
    autor escreveu, não uma declaração de quem tinha as brancas"*.
    """

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "prolifico.pgn"
        self.base.write_text(self._muitas_partidas(), encoding="utf-8")
        self.indice = self.raiz / "indice.sqlite"
        build_index(self.base, self.indice)

    def _muitas_partidas(self, por_cor: int = 6) -> str:
        """`por_cor` partidas com Karpov de brancas e outras tantas com ele de pretas."""
        blocos = []
        for n in range(por_cor):
            blocos.append(
                f'[Event "Brancas {n}"]\n[White "Karpov, Anatoly"]\n[Black "Kasparov, Garry"]\n'
                f'[Date "20{n:02d}.01.01"]\n\n1. e4 e5 2. Nf3 *\n'
            )
        for n in range(por_cor):
            blocos.append(
                f'[Event "Pretas {n}"]\n[White "Kasparov, Garry"]\n[Black "Karpov, Anatoly"]\n'
                f'[Date "19{n:02d}.01.01"]\n\n1. d4 d5 2. c4 *\n'
            )
        return "\n".join(blocos)

    def test_o_limite_nao_se_esgota_na_primeira_cor(self) -> None:
        """**O critério de aceite**, e o `limit` é menor que uma cor sozinha -- que é a
        condição em que o defeito aparece. Com 6 partidas de cada lado e `limit=4`, a cota
        única era inteiramente consumida pela primeira cor."""
        partidas = lookup_pair(("karpov", "kasparov"), self.base, self.indice, limit=4)

        eventos = {p.headers["Event"].split()[0] for p in partidas}
        self.assertEqual(eventos, {"Brancas", "Pretas"}, "as duas cores, que é o que `both_colors` promete")

    def test_o_limite_continua_sendo_um_teto(self) -> None:
        """Uma cota por cor não pode virar duas cotas: o `limit` é o custo que quem chama
        aceitou pagar em leituras de disco -- até 40 seeks num arquivo de gigabytes."""
        self.assertLessEqual(len(lookup_pair(("karpov", "kasparov"), self.base, self.indice, limit=3)), 3)

    def test_uma_cor_so_recebe_o_limite_inteiro(self) -> None:
        """A repartição não pode virar desperdício: um par que só jogou com uma cor continua
        podendo encher a cota."""
        so_brancas = self.raiz / "so_brancas.pgn"
        partidas = [
            f'[Event "B{n}"]\n[White "Fischer, Robert"]\n[Black "Spassky, Boris"]\n\n1. e4 *\n'
            for n in range(6)
        ]
        so_brancas.write_text("\n".join(partidas), encoding="utf-8")
        indice = self.raiz / "so_brancas.sqlite"
        build_index(so_brancas, indice)

        self.assertEqual(len(lookup_pair(("fischer", "spassky"), so_brancas, indice, limit=4)), 4)

    def test_sem_both_colors_continua_uma_consulta_so(self) -> None:
        partidas = lookup_pair(("karpov", "kasparov"), self.base, self.indice, both_colors=False, limit=20)
        self.assertTrue(all(p.headers["White"].startswith("Karpov") for p in partidas))


class PorteiroNaBuscaPorNomeTests(unittest.TestCase):
    """`positions_of` paga o porteiro da S-85, que ele ignorava (S-139).

    `partida.positions()` era chamado **sem** `occupancies`, e quem o invoca é a busca por nome
    da janela de candidatas -- na thread do Tk. A S-85 mediu que o porteiro corta ~3× o custo
    de reproduzir os lances, e este caminho pagava o preço cheio.

    O critério de aceite da Fase 13 é *"busca por nome de um diagrama: <1 s"*, medido em 27 ms
    quando havia **uma** base; com duas gigabases o caminho já custava 70-220 ms, com a janela
    congelada.
    """

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(PGN, encoding="utf-8")
        self.indice = self.raiz / "indice.sqlite"
        build_index(self.base, self.indice)

    def _partidas(self) -> list[GameRecord]:
        return lookup_pair(("anderssen", "kieseritzky"), self.base, self.indice)

    def test_a_colocacao_procurada_continua_sendo_achada(self) -> None:
        """O porteiro é **filtro e não critério**: o que decide continua sendo a igualdade das
        64 casas. Se ele mudasse a resposta, seria defeito e não otimização."""
        partidas = self._partidas()
        tabuleiro = chess.Board()
        tabuleiro.push_san("e4")
        procurada = tabuleiro.board_fen()

        achados = positions_of(partidas, procurada)

        self.assertTrue(achados, "a posição depois de 1.e4 está nas partidas do PGN de teste")
        for _partida, lance, _vez in achados:
            self.assertGreaterEqual(lance, 1)

    def test_colocacao_ausente_continua_ausente(self) -> None:
        positions = positions_of(self._partidas(), "8/8/8/8/8/8/8/K6k")
        self.assertEqual(positions, [])

    def test_o_porteiro_e_repassado_ao_replay(self) -> None:
        """Sem isto o item é invisível: a resposta é a mesma com e sem porteiro -- o que muda é
        o custo, e custo não aparece numa asserção de igualdade."""
        vistos: list[frozenset[int] | None] = []
        original = GameRecord.positions

        def _espia(self, occupancies=None):  # noqa: ANN001, ANN202
            vistos.append(occupancies)
            return original(self, occupancies)

        with mock.patch.object(GameRecord, "positions", _espia):
            positions_of(self._partidas(), "8/8/8/8/8/8/8/K6k")

        self.assertTrue(vistos, "positions foi chamado")
        self.assertTrue(all(o is not None for o in vistos), "e com o porteiro, não sem ele")


def _pgn_grande(partidas: int) -> str:
    """Um PGN sintético de `partidas` partidas curtas, para o cancelamento ter em que agir."""
    bloco = (
        '[Event "Sintético {n}"]\n[White "Branco{n}, A"]\n[Black "Preto{n}, B"]\n[Result "*"]\n\n'
        "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 *\n\n"
    )
    return "".join(bloco.replace("{n}", str(n)) for n in range(partidas))


class IndiceIncrementalTests(unittest.TestCase):
    """Só o que mudou é relido (S-532), e o manifesto é quem decide.

    Cada teste afirma um número que era invisível antes -- `relidas`, `arquivos_pulados`,
    `arquivos_removidos` --, porque a resposta da consulta é a mesma com e sem incremento: o que
    muda é o custo, e custo não aparece numa asserção de igualdade.
    """

    OUTRO = DuasBasesTests.OUTRO

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.a = self.raiz / "a.pgn"
        self.a.write_text(PGN, encoding="utf-8")
        self.b = self.raiz / "b.pgn"
        self.b.write_text(self.OUTRO, encoding="utf-8")
        self.indice = self.raiz / "indice.sqlite"
        self.avisos: list[tuple[str, int, int, int]] = []
        self.primeira = build_index([self.a, self.b], self.indice, progress=self._anotar)

    def _anotar(self, base: Path, lidos: int, total: int, partidas: int) -> None:
        self.avisos.append((base.name, lidos, total, partidas))

    def _linhas_do_arquivo(self, nome: str) -> int:
        conexao = sqlite3.connect(f"file:{self.indice}?mode=ro", uri=True)
        try:
            (identificador,) = conexao.execute("SELECT id FROM files WHERE name = ?", (nome,)).fetchone()
            return int(conexao.execute("SELECT COUNT(*) FROM games WHERE file = ?", (identificador,)).fetchone()[0])
        finally:
            conexao.close()

    def test_a_primeira_rodada_le_tudo(self) -> None:
        self.assertEqual((self.primeira.partidas, self.primeira.relidas, self.primeira.arquivos_relidos), (4, 4, 2))

    def test_a_segunda_rodada_nao_rele_nada(self) -> None:
        """**O critério de aceite.** Mesma pasta, nenhum byte mudou: zero partidas lidas, e o
        progresso chega uma vez por arquivo com os bytes cheios -- a barra do conjunto anda pelo
        que foi pulado."""
        self.avisos.clear()
        segunda = build_index([self.a, self.b], self.indice, progress=self._anotar)

        self.assertEqual(segunda.relidas, 0)
        self.assertEqual(segunda.arquivos_pulados, 2)
        self.assertEqual(segunda.partidas, 4, "o total continua sendo o do índice inteiro")
        self.assertEqual(
            [(nome, lidos == total) for nome, lidos, total, _ in self.avisos], [("a.pgn", True), ("b.pgn", True)]
        )
        self.assertEqual(len(lookup_pair(("anderssen", "kieseritzky"), [self.a, self.b], self.indice)), 2)

    def test_o_mtime_sozinho_nao_forca_a_releitura(self) -> None:
        """A lição da S-113: um sync de nuvem ou um antivírus reescrevem o carimbo sem tocar num
        byte, e isso jogava fora 56 minutos de varredura. Aqui decidem tamanho e marcas."""
        carimbo = self.a.stat().st_mtime + 3600
        os.utime(self.a, (carimbo, carimbo))
        self.assertEqual(build_index([self.a, self.b], self.indice).relidas, 0)

    def test_arquivo_anexado_rele_so_a_cauda(self) -> None:
        """O PGN em que se anexam as partidas da semana: só elas são lidas, e os offsets antigos
        continuam valendo -- a consulta acha as partidas velhas e a nova."""
        with self.a.open("a", encoding="utf-8") as fh:
            fh.write("\n" + self.OUTRO)
        rodada = build_index([self.a, self.b], self.indice)

        self.assertEqual((rodada.relidas, rodada.arquivos_relidos, rodada.arquivos_pulados), (1, 1, 1))
        self.assertEqual(rodada.partidas, 5)
        self.assertEqual(len(lookup_pair(("anderssen", "kieseritzky"), [self.a, self.b], self.indice)), 2, "as velhas")
        capablanca = lookup_pair(("capablanca", "lasker"), [self.a, self.b], self.indice)
        self.assertEqual(len(capablanca), 2, "a anexada em a.pgn e a que sempre esteve em b.pgn")

    def test_arquivo_reescrito_e_relido_inteiro_sem_deixar_linha_velha(self) -> None:
        """Mesmo nome, outro conteúdo: as linhas antigas dele saem antes de as novas entrarem, senão
        um offset velho apontaria para o meio de outra partida."""
        self.a.write_text(self.OUTRO + "\n" + PGN, encoding="utf-8")
        rodada = build_index([self.a, self.b], self.indice)

        self.assertEqual(rodada.relidas, 4)
        self.assertEqual(self._linhas_do_arquivo("a.pgn"), 4)
        self.assertEqual(len(lookup_pair(("anderssen", "kieseritzky"), [self.a, self.b], self.indice)), 2)

    def test_arquivo_removido_sai_do_indice_sem_aviso_na_consulta(self) -> None:
        self.b.unlink()
        rodada = build_index([self.a], self.indice)

        self.assertEqual(rodada.arquivos_removidos, 1)
        self.assertEqual(rodada.partidas, 3)
        conexao = sqlite3.connect(f"file:{self.indice}?mode=ro", uri=True)
        try:
            self.assertEqual(conexao.execute("SELECT COUNT(*) FROM files WHERE name = 'b.pgn'").fetchone()[0], 0)
            self.assertEqual(conexao.execute("SELECT COUNT(*) FROM games").fetchone()[0], 3)
        finally:
            conexao.close()
        with self.assertNoLogs("chess_diagram_ocr.games_index", level="WARNING"):
            self.assertEqual(lookup_pair(("capablanca", "lasker"), [self.a], self.indice), [])

    def test_o_arquivo_novo_ganha_o_proximo_numero_e_os_antigos_ficam_com_o_deles(self) -> None:
        """O número do arquivo deixou de ser a posição na lista: vem do manifesto e sobrevive."""
        c = self.raiz / "0_antes_de_todos.pgn"
        c.write_text(self.OUTRO, encoding="utf-8")
        build_index([c, self.a, self.b], self.indice)
        conexao = sqlite3.connect(f"file:{self.indice}?mode=ro", uri=True)
        try:
            por_nome = dict(conexao.execute("SELECT name, id FROM files"))
        finally:
            conexao.close()
        self.assertEqual((por_nome["a.pgn"], por_nome["b.pgn"], por_nome["0_antes_de_todos.pgn"]), (0, 1, 2))
        self.assertEqual(len(lookup_pair(("capablanca", "lasker"), [c, self.a, self.b], self.indice)), 2)

    def test_o_indice_de_formato_anterior_e_refeito_do_zero(self) -> None:
        antigo = self.raiz / "v3.sqlite"
        conexao = sqlite3.connect(antigo)
        conexao.execute(
            "CREATE TABLE games (pair INTEGER, offset INTEGER, file INTEGER, "
            "PRIMARY KEY (pair, file, offset)) WITHOUT ROWID"
        )
        conexao.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conexao.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conexao.execute("INSERT INTO meta VALUES ('version', '3')")
        conexao.commit()
        conexao.close()

        rodada = build_index([self.a], antigo)

        self.assertEqual(rodada.relidas, 3)
        self.assertEqual(len(lookup_pair(("anderssen", "kieseritzky"), self.a, antigo)), 2)

    def test_o_indice_parcial_nao_existe_mais_e_nem_o_jornal(self) -> None:
        """A atomicidade passou do `.parcial` para a transação por arquivo, e o jornal do SQLite
        não pode sobrar ao lado: `data/` tem guarda contra artefato que ninguém declarou."""
        self.assertEqual(sorted(caminho.name for caminho in self.raiz.glob("indice.sqlite*")), ["indice.sqlite"])


class CancelamentoDoIndiceTests(unittest.TestCase):
    """Cancelar para em menos de um segundo, desfaz só o arquivo em curso, e a rodada seguinte retoma."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.pequena = self.raiz / "a_pequena.pgn"
        self.pequena.write_text(PGN, encoding="utf-8")
        self.grande = self.raiz / "b_grande.pgn"
        self.grande.write_text(_pgn_grande(400_000), encoding="utf-8")
        self.indice = self.raiz / "indice.sqlite"

    def test_cancelar_para_em_menos_de_um_segundo_e_a_consulta_recusa_o_indice(self) -> None:
        cancelar = threading.Event()
        relogio = threading.Timer(0.3, cancelar.set)
        relogio.start()
        self.addCleanup(relogio.cancel)
        inicio = time.perf_counter()
        rodada = build_index([self.pequena, self.grande], self.indice, cancel=cancelar)
        decorrido = time.perf_counter() - inicio

        self.assertTrue(rodada.cancelado)
        self.assertLess(decorrido, 1.3, "0,3 s até o pedido, e menos de 1 s para honrá-lo")
        self.assertGreaterEqual(
            rodada.partidas,
            3,
            "a pequena terminou e ficou; da grande fica o que os lotes já tinham fechado (S-533, r2)",
        )
        with self.assertLogs("chess_diagram_ocr.games_index", level="WARNING") as registro:
            self.assertEqual(lookup_pair(("anderssen", "kieseritzky"), [self.pequena, self.grande], self.indice), [])
        self.assertIn("cvoff-games --build-index", registro.output[0])

    def test_a_rodada_seguinte_retoma_do_que_ficou_e_o_progresso_nao_passa_de_dez_por_segundo(self) -> None:
        cancelar = threading.Event()
        cancelar.set()
        # Bandeira ja ligada: nada e lido, e nada quebra.
        self.assertTrue(build_index([self.pequena, self.grande], self.indice, cancel=cancelar).cancelado)

        avisos: list[float] = []
        inicio = time.perf_counter()
        rodada = build_index(
            [self.pequena, self.grande], self.indice, progress=lambda *_: avisos.append(time.perf_counter())
        )
        decorrido = time.perf_counter() - inicio

        self.assertFalse(rodada.cancelado)
        self.assertEqual(rodada.partidas, 400_003)
        # Ate dez por segundo dentro de um arquivo, mais um aviso final por arquivo.
        self.assertLessEqual(len(avisos), 10 * decorrido + 2 + 1)
        self.assertEqual(len(lookup_pair(("branco7", "preto7"), [self.pequena, self.grande], self.indice)), 1)

    def test_o_cancelamento_no_meio_do_arquivo_nao_faz_a_proxima_rodada_reler_tudo(self) -> None:
        """A transação era por arquivo, e a gigabase **é** um arquivo (S-533, r2).

        Cancelar no nono minuto desfazia os nove e a rodada seguinte relia 8,6 GB do começo. Com
        a transação por lote, o manifesto anota até que byte o arquivo está lido, e a rodada
        seguinte continua de lá -- o que se perde é o lote em curso.

        O que o teste afirma é o **custo**: a segunda rodada lê menos partidas do que o arquivo
        tem. A resposta final é a mesma nos dois mundos, então uma asserção de igualdade sobre o
        conteúdo não pegaria a regressão.
        """
        cancelar = threading.Event()
        vistos: list[object] = []

        def progresso(*args: object) -> None:
            vistos.append(args)
            if len(vistos) >= 8:
                cancelar.set()

        with (
            mock.patch.object(games_index, "_TAMANHO_DO_LOTE", 1_000),
            mock.patch.object(games_index, "_LINHAS_POR_CONFERENCIA", 4_096),
            mock.patch.object(games_index, "INTERVALO_DE_PROGRESSO", 0.0),
        ):
            primeira = build_index([self.grande], self.indice, progress=progresso, cancel=cancelar)
        self.assertTrue(primeira.cancelado)

        segunda = build_index([self.grande], self.indice)
        self.assertFalse(segunda.cancelado)
        self.assertEqual(segunda.partidas, 400_000, "o índice fica completo, venha de onde vier")
        self.assertLess(segunda.relidas, 400_000, "a segunda rodada releu o arquivo inteiro: o marco não pegou")
        self.assertEqual(len(lookup_pair(("branco7", "preto7"), [self.grande], self.indice)), 1)
        self.assertEqual(len(lookup_pair(("branco399999", "preto399999"), [self.grande], self.indice)), 1)


class IndiceSobreBaseComprimidaTests(unittest.TestCase):
    """O índice sobre `.gz` e membro de `.zip` (S-531): offsets do fluxo descompactado."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        with gzip.open(self.raiz / "base.pgn.gz", "wb") as fh:
            fh.write(PGN.encode("utf-8"))
        with zipfile.ZipFile(self.raiz / "pacote.zip", "w", zipfile.ZIP_DEFLATED) as zipado:
            zipado.writestr("torneio.pgn", DuasBasesTests.OUTRO)
        self.bases = database_paths(self.raiz)
        self.indice = self.raiz / "indice.sqlite"
        build_index(self.bases, self.indice)

    def test_a_consulta_le_a_partida_do_gz_pelo_offset(self) -> None:
        partidas = lookup_pair(("anderssen", "kieseritzky"), self.bases, self.indice)
        self.assertEqual({p.headers["Event"] for p in partidas}, {"London", "Revanche"})
        self.assertIn("Bxb5", next(p for p in partidas if p.headers["Event"] == "London").movetext)

    def test_a_consulta_le_o_membro_do_zip(self) -> None:
        (partida,) = lookup_pair(("capablanca", "lasker"), self.bases, self.indice, both_colors=False)
        self.assertEqual(partida.headers["Event"], "Havana")

    def test_a_base_comprimida_que_mudou_e_relida_inteira(self) -> None:
        """Não há "só a cauda" num `.gz`: recomprimir muda o arquivo inteiro."""
        with gzip.open(self.raiz / "base.pgn.gz", "wb") as fh:
            fh.write((PGN + "\n" + DuasBasesTests.OUTRO).encode("utf-8"))
        rodada = build_index(self.bases, self.indice)
        self.assertEqual(rodada.relidas, 4)
        self.assertEqual(len(lookup_pair(("capablanca", "lasker"), self.bases, self.indice)), 2)

    def test_o_nome_no_manifesto_e_o_do_membro_com_o_zip(self) -> None:
        conexao = sqlite3.connect(f"file:{self.indice}?mode=ro", uri=True)
        try:
            nomes = sorted(nome for (nome,) in conexao.execute("SELECT name FROM files"))
        finally:
            conexao.close()
        self.assertEqual(nomes, ["base.pgn.gz", "pacote.zip/torneio.pgn"])


NAJDORF = "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3 e5"
ESLAVA = "1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Nc3 dxc4"


def _partida(
    evento: str = "Tata Steel Masters",
    data: str = "2019.01.26",
    branco: str = "Carlsen, Magnus",
    preto: str = "Anand, Viswanathan",
    resultado: str = "1-0",
    welo: str = "2835",
    belo: str = "2773",
    eco: str = "",
    fen: str = "",
    lances: str = NAJDORF,
) -> str:
    """Uma partida de teste com os headers que o índice guarda. Vazio não vai para o arquivo."""
    campos = [
        ("Event", evento),
        ("Date", data),
        ("White", branco),
        ("Black", preto),
        ("Result", resultado),
        ("WhiteElo", welo),
        ("BlackElo", belo),
        ("ECO", eco),
        ("SetUp", "1" if fen else ""),
        ("FEN", fen),
    ]
    cabecalho = "".join(f'[{chave} "{valor}"]\n' for chave, valor in campos if valor)
    return f"{cabecalho}\n{lances} {resultado}\n\n"


class ColunaEcoTests(unittest.TestCase):
    """O ECO gravado no índice (S-534): o header vence, e sem ele os primeiros lances decidem."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(
            _partida(branco="Com, Header", eco="C99")
            + _partida(branco="Sem, Header")
            + _partida(branco="Sublinha, A", eco="B90a")
            + _partida(branco="Montada, A", fen="8/8/8/8/8/8/4K3/4k3 w - - 0 1", lances="1. Kd3 Kd1")
            + _partida(branco="Eslava, A", lances=ESLAVA),
            encoding="utf-8",
        )
        self.indice = self.raiz / "indice.sqlite"
        build_index(self.base, self.indice)

    def _eco_de(self, sobrenome: str) -> str:
        conexao = sqlite3.connect(f"file:{self.indice}?mode=ro", uri=True)
        try:
            linha = conexao.execute(
                "SELECT g.eco FROM games g JOIN players p ON p.id = g.white WHERE p.surname = ?", (sobrenome,)
            ).fetchone()
        finally:
            conexao.close()
        return "" if linha is None else str(linha[0])

    def test_o_header_vence_a_classificacao(self) -> None:
        """É a classificação que quem publicou a partida escolheu; a tabela embutida pode discordar
        dela numa transposição rara, e a base é a fonte."""
        self.assertEqual("C99", self._eco_de("com"))

    def test_sem_header_os_primeiros_lances_classificam(self) -> None:
        """É o caso da base exportada de um servidor: sem isto a coluna ficaria vazia nela inteira,
        e o filtro por ECO não responderia nada."""
        self.assertEqual("B90", self._eco_de("sem"))
        self.assertEqual("D15", self._eco_de("eslava"), "outra abertura, outro código: não é um valor fixo")

    def test_a_sublinha_do_header_e_cortada(self) -> None:
        """`B90a` é `B90`: a unidade da classificação são os três caracteres, e é neles que a busca
        filtra. Sem o corte, `eco >= 'B90' AND eco <= 'B90'` deixaria de casar a própria partida."""
        self.assertEqual("B90", self._eco_de("sublinha"))

    def test_a_partida_montada_de_uma_fen_nao_ganha_abertura(self) -> None:
        """Ela não começa na posição inicial: os "primeiros lances" dela não são uma abertura, e
        classificá-los daria um código sobre uma partida que não passou por ele."""
        self.assertEqual("", self._eco_de("montada"))

    def test_a_busca_por_eco_acha_a_que_foi_classificada_sem_header(self) -> None:
        """A ponta a ponta: a coluna existe para ser filtrada."""
        resposta = buscar(Filtro(eco_de="B90"), self.base, self.indice)
        self.assertEqual({"Sem, Header", "Sublinha, A"}, {achado.brancas for achado in resposta.achados})
        self.assertEqual("B90", resposta.achados[0].eco)


class MigracaoDeVersaoTests(unittest.TestCase):
    """Um índice de formato anterior é **apagado e refeito**, e até lá a busca recusa (S-533).

    A migração é refazer, e não converter: um índice v4 não tem nomes, datas nem códigos gravados,
    e uma "segunda passada" que os buscasse pelos offsets leria os mesmos bytes que a passada
    inteira, na mesma ordem, com um `seek` por partida a mais. Não há o que aproveitar.
    """

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(_partida() + _partida(branco="Nepomniachtchi, Ian"), encoding="utf-8")
        self.indice = self.raiz / "indice.sqlite"

    def _indice_antigo(self) -> None:
        """Um índice no formato da v4: três colunas, `WITHOUT ROWID`, e a versão declarada 4."""
        conexao = sqlite3.connect(self.indice)
        conexao.execute(
            "CREATE TABLE games (pair INTEGER NOT NULL, file INTEGER NOT NULL, offset INTEGER NOT NULL, "
            "PRIMARY KEY (pair, file, offset)) WITHOUT ROWID"
        )
        conexao.execute(
            "CREATE TABLE files (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, size INTEGER NOT NULL, "
            "mtime REAL NOT NULL, head TEXT NOT NULL, tail TEXT NOT NULL, games INTEGER NOT NULL)"
        )
        conexao.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conexao.execute("INSERT INTO meta VALUES ('version', '4')")
        conexao.execute("INSERT INTO meta VALUES ('database', ?)", (index_fingerprint(self.base),))
        conexao.execute("INSERT INTO games VALUES (?, 0, 0)", (pair_hash(("carlsen", "anand")),))
        conexao.execute("INSERT INTO files VALUES (0, 'base.pgn', 1, 1.0, '', '', 1)")
        conexao.commit()
        conexao.close()

    def test_a_busca_recusa_o_indice_de_outro_formato_com_a_instrucao(self) -> None:
        """**Exceção e não lista vazia**: "nenhuma partida" e "o índice é de outro formato" são
        frases diferentes, e devolver `[]` nos dois casos foi o que a S-93 mediu como silêncio."""
        self._indice_antigo()
        with self.assertRaises(IndiceIndisponivel) as erro:
            buscar(Filtro(brancas="Carlsen"), self.base, self.indice)
        self.assertIn("'4'", str(erro.exception))
        self.assertIn(str(INDEX_VERSION), str(erro.exception))
        self.assertIn("--build-index", str(erro.exception), "a frase tem de dizer o que fazer")

    def test_a_rodada_seguinte_apaga_o_antigo_e_refaz(self) -> None:
        self._indice_antigo()
        with self.assertLogs("chess_diagram_ocr.games_index", level="INFO"):
            rodada = build_index(self.base, self.indice)
        self.assertEqual(2, rodada.partidas)
        self.assertEqual(2, rodada.relidas, "o índice antigo não conta como pulado")
        resposta = buscar(Filtro(brancas="Carlsen"), self.base, self.indice)
        self.assertEqual(1, resposta.total)
        self.assertEqual("B90", resposta.achados[0].eco, "a coluna nova está preenchida")

    def test_a_versao_gravada_e_a_desta_execucao(self) -> None:
        """Sem a versão declarada, um índice antigo passaria pelo fingerprint e quebraria na
        primeira consulta -- `SELECT ... eco` numa tabela sem essa coluna."""
        build_index(self.base, self.indice)
        conexao = sqlite3.connect(f"file:{self.indice}?mode=ro", uri=True)
        try:
            (gravada,) = conexao.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
        finally:
            conexao.close()
        self.assertEqual(str(INDEX_VERSION), gravada)

    def _rebaixar_para_v5(self) -> None:
        """O índice de hoje sem as duas árvores da v6 e com a versão 5 gravada -- que **é** um v5."""
        conexao = sqlite3.connect(self.indice)
        conexao.execute("DROP INDEX IF EXISTS games_elo")
        conexao.execute(f"DROP INDEX IF EXISTS {INDICE_DA_ORDEM}")
        conexao.execute("INSERT OR REPLACE INTO meta VALUES ('version', '5')")
        conexao.commit()
        conexao.close()

    def test_o_indice_v5_e_completado_e_nao_refeito(self) -> None:
        """A primeira versão que **não** manda refazer, e o motivo é que não falta dado (S-533, r2).

        A v6 acrescentou duas árvores de busca à v5 e nenhuma coluna. Mandar refazer custaria a
        passada inteira -- dez minutos e 8,6 GB relidos na gigabase -- para gravar exatamente as
        mesmas linhas. A regra "migração é refazer" das versões 3, 4 e 5 valia porque faltava dado
        **gravado**; aqui o que falta é uma árvore, e uma árvore se cria sobre a tabela pronta.
        """
        build_index(self.base, self.indice)
        self._rebaixar_para_v5()

        rodada = build_index(self.base, self.indice)

        self.assertEqual(0, rodada.relidas, "não se relê byte nenhum para criar uma árvore")
        self.assertEqual(2, rodada.partidas, "as linhas da v5 continuam lá")
        conexao = sqlite3.connect(f"file:{self.indice}?mode=ro", uri=True)
        try:
            arvores = {nome for (nome,) in conexao.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
            (gravada,) = conexao.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
        finally:
            conexao.close()
        self.assertEqual(str(INDEX_VERSION), gravada)
        self.assertLessEqual({nome for nome, _colunas in _INDICES_DE_BUSCA}, arvores)

    def test_o_v5_ainda_e_recusado_pela_busca_ate_a_rodada_acontecer(self) -> None:
        """Completar é barato, mas não é automático: quem consulta só lê, e a frase diz o que fazer."""
        build_index(self.base, self.indice)
        self._rebaixar_para_v5()
        with self.assertRaises(IndiceIndisponivel) as erro:
            buscar(Filtro(brancas="Carlsen"), self.base, self.indice)
        self.assertIn("'5'", str(erro.exception))
        self.assertIn("--build-index", str(erro.exception))

    def test_o_indice_em_obras_e_recusado_com_frase_propria(self) -> None:
        """A marca da base sai antes de a rodada começar: um índice pela metade recusa a consulta
        em vez de responder menos do que a base tem."""
        build_index(self.base, self.indice)
        conexao = sqlite3.connect(self.indice)
        conexao.execute("DELETE FROM meta WHERE key = 'database'")
        conexao.commit()
        conexao.close()
        with self.assertRaises(IndiceIndisponivel) as erro:
            buscar(Filtro(brancas="Carlsen"), self.base, self.indice)
        self.assertIn("em obras", str(erro.exception))

    def test_sem_indice_a_busca_diz_que_ele_nao_foi_construido(self) -> None:
        with self.assertRaises(IndiceIndisponivel) as erro:
            buscar(Filtro(brancas="Carlsen"), self.base, self.raiz / "nao_existe.sqlite")
        self.assertIn("ainda não foi construído", str(erro.exception))


class BuscaTests(unittest.TestCase):
    """A busca por filtros combinados (S-533): cada filtro, a combinação, a ordem e a página.

    A base de teste tem doze partidas de sete jogadores em três torneios e cinco anos -- pequena o
    bastante para cada asserção nomear a partida esperada, e variada o bastante para um filtro que
    não filtrasse nada passar despercebido em nenhuma delas.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.pasta = tempfile.TemporaryDirectory()
        cls.raiz = Path(cls.pasta.name)
        cls.base = cls.raiz / "base.pgn"
        cls.base.write_text(
            _partida(branco="Carlsen, Magnus", preto="Anand, Viswanathan", data="2019.01.26", eco="B90")
            + _partida(
                branco="Anand, Viswanathan", preto="Carlsen, Magnus", data="2019.01.27", resultado="0-1", eco="C42"
            )
            + _partida(
                branco="Carlsen, Magnus", preto="Caruana, Fabiano", data="2018.11.09", eco="B33",
                evento="World Championship",
            )
            + _partida(
                branco="Caruana, Fabiano", preto="Carlsen, Magnus", data="2018.11.10", resultado="1/2-1/2",
                eco="C65", evento="World Championship",
            )
            + _partida(branco="Carlsen, M", preto="Giri, Anish", data="2020.01.15", eco="D37")
            + _partida(
                branco="Giri, Anish", preto="Anand, Viswanathan", data="2020.01.16", resultado="1/2-1/2", eco="E60"
            )
            + _partida(
                branco="Ivanov, A", preto="Petrov, B", data="1998.05.01", welo="2210", belo="2180", eco="B22",
                evento="ch-RUS",
            )
            + _partida(
                branco="Petrov, B", preto="Ivanov, A", data="1998.05.02", resultado="0-1", welo="2180", belo="2210",
                eco="A45", evento="ch-RUS",
            )
            + _partida(
                branco="Sem, Data", preto="Sem, Elo", data="????.??.??", welo="", belo="", eco="B01", evento="ch-RUS"
            )
            + _partida(
                branco="Nepomniachtchi, Ian", preto="Carlsen, Magnus", data="2021.12.03", resultado="*", eco="C88"
            )
            + _partida(branco="Carlsen, Magnus", preto="Nepomniachtchi, Ian", data="2021.12.04", eco="C88")
            + _partida(branco="Nepomniachtchi, Ian", preto="Giri, Anish", data="2021.12.05", resultado="0-1", eco="B90"),
            encoding="utf-8",
        )
        cls.indice = cls.raiz / "indice.sqlite"
        build_index(cls.base, cls.indice)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.pasta.cleanup()

    def _brancas(self, **campos: object) -> list[str]:
        """Os nomes das brancas achados, na ordem em que a busca os devolveu."""
        resposta = buscar(Filtro(**campos), self.base, self.indice)  # type: ignore[arg-type]
        return [achado.brancas for achado in resposta.achados]

    def test_o_sobrenome_acha_as_grafias_do_mesmo_jogador(self) -> None:
        """`Carlsen, Magnus` e `Carlsen, M` são duas linhas de `players` e o mesmo jogador -- é o
        que a subconsulta por `surname` resolve, e é a razão de o dicionário guardar o sobrenome
        ao lado do nome."""
        achados = self._brancas(brancas="Carlsen", qualquer_cor=False)
        self.assertEqual(4, len(achados))
        self.assertIn("Carlsen, M", achados)

    def test_qualquer_cor_traz_os_dois_lados(self) -> None:
        """O livro escreve `Coull - Stanciu` sem prometer quem tinha as brancas."""
        com = buscar(Filtro(brancas="Carlsen", qualquer_cor=True), self.base, self.indice)
        sem = buscar(Filtro(brancas="Carlsen", qualquer_cor=False), self.base, self.indice)
        self.assertEqual(7, com.total)
        self.assertEqual(4, sem.total)

    def test_o_par_procura_as_duas_montagens(self) -> None:
        """Carlsen × Anand acha as duas em que eles se enfrentaram, em qualquer ordem de cor."""
        par = buscar(Filtro(brancas="Carlsen", pretas="Anand"), self.base, self.indice)
        self.assertEqual(2, par.total)
        com_cor = buscar(Filtro(brancas="Carlsen", pretas="Anand", qualquer_cor=False), self.base, self.indice)
        self.assertEqual(1, com_cor.total)
        self.assertEqual("Carlsen, Magnus", com_cor.achados[0].brancas)

    def test_o_evento_casa_por_pedaco_e_sem_caixa_nem_acento(self) -> None:
        """Ninguém decora o nome inteiro de um torneio, e `fold` é o mesmo do resto do projeto."""
        self.assertEqual(2, buscar(Filtro(evento="world champ"), self.base, self.indice).total)
        self.assertEqual(3, buscar(Filtro(evento="ch-RUS"), self.base, self.indice).total)
        self.assertEqual(0, buscar(Filtro(evento="Linares"), self.base, self.indice).total)

    def test_o_evento_nao_e_padrao_de_like(self) -> None:
        """`%` e `_` digitados no campo são texto e não coringa: sem escapar, `_` casaria tudo."""
        self.assertEqual(0, buscar(Filtro(evento="%"), self.base, self.indice).total)
        self.assertEqual(0, buscar(Filtro(evento="ch_RUS"), self.base, self.indice).total)

    def test_a_faixa_de_ano_inclui_as_duas_pontas(self) -> None:
        self.assertEqual(4, buscar(Filtro(ano_de=2018, ano_ate=2019), self.base, self.indice).total)
        self.assertEqual(2, buscar(Filtro(ano_de=2020, ano_ate=2020), self.base, self.indice).total)
        self.assertEqual(3, buscar(Filtro(ano_de=2021), self.base, self.indice).total)
        # `ano_ate` sozinho e um teto, e a partida sem data tem ano zero: ela cabe abaixo de
        # qualquer teto. E ela **nao** cabe num piso -- e o teste abaixo afirma isso.
        self.assertEqual(3, buscar(Filtro(ano_ate=1998), self.base, self.indice).total)

    def test_a_partida_sem_data_nao_entra_em_faixa_de_ano_nenhuma(self) -> None:
        """`????.??.??` vira ano zero: incluí-la em "desde 1998" seria afirmar um ano que o header
        não diz."""
        self.assertNotIn("Sem, Data", self._brancas(ano_de=1000))

    def test_o_elo_minimo_e_o_menor_dos_dois(self) -> None:
        """"Elo mínimo 2700" pergunta pelo **nível da partida**: uma partida de 2835 contra 2180
        não é uma partida de 2700.

        **A base da classe não contém o par que este docstring cita, e por isso ele ganhou índice
        próprio.** Os doze jogos dela são 2835/2773 ou 2210/2180 -- os dois lados do mesmo lado do
        corte --, e ali `min` e `max` devolvem os mesmos nove. Um crítico trocou `min` por `max` em
        `games_index` e a suíte inteira ficou verde: a guarda existia, o docstring nomeava o caso, e
        o dado que o separa não estava em lugar nenhum. O par abaixo é o do docstring, e é o que faz
        a asserção discordar das duas leituras.
        """
        self.assertEqual(9, buscar(Filtro(elo_minimo=2700), self.base, self.indice).total)
        self.assertEqual(0, buscar(Filtro(elo_minimo=2900), self.base, self.indice).total)

        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            base = raiz / "desigual.pgn"
            base.write_text(
                _partida(branco="Forte, A", preto="Fraco, B", data="2019.03.01", welo="2835", belo="2180", eco="B90")
                + _partida(branco="Forte, A", preto="Forte, C", data="2019.03.02", welo="2835", belo="2773", eco="B90"),
                encoding="utf-8",
            )
            indice = raiz / "desigual.sqlite"
            build_index(base, indice)
            resposta = buscar(Filtro(elo_minimo=2700), base, indice)
            self.assertEqual(1, resposta.total, "a partida de 2835 contra 2180 entrou num filtro de 2700")
            self.assertEqual(["Forte, A"], [a.brancas for a in resposta.achados])
            self.assertEqual("Forte, C", resposta.achados[0].pretas)

    def test_a_partida_sem_elo_nao_entra_no_filtro_de_elo(self) -> None:
        """Uma partida em que um dos lados não tem Elo não pode afirmar nível nenhum."""
        self.assertNotIn("Sem, Data", self._brancas(elo_minimo=1))

    def test_o_resultado_filtra_o_que_o_header_escreve(self) -> None:
        empates = buscar(Filtro(elo_minimo=1, resultado="1/2-1/2"), self.base, self.indice)
        self.assertEqual(2, empates.total)
        for achado in empates.achados:
            self.assertEqual("1/2-1/2", achado.resultado)
        self.assertEqual(1, buscar(Filtro(elo_minimo=1, resultado="*"), self.base, self.indice).total)

    def test_a_faixa_de_eco_e_o_codigo_sozinho(self) -> None:
        self.assertEqual(2, buscar(Filtro(eco_de="B90"), self.base, self.indice).total)
        self.assertEqual(2, buscar(Filtro(eco_de="B90", eco_ate="B90"), self.base, self.indice).total)
        self.assertEqual(5, buscar(Filtro(eco_de="B00", eco_ate="B99"), self.base, self.indice).total)
        # Um so dos dois preenchido e faixa de **um** codigo, e nao "ate A99": e o que o
        # docstring de `Filtro.eco_ate` declara, e e a forma comum ("B90" e a Najdorf).
        self.assertEqual(0, buscar(Filtro(eco_ate="A99"), self.base, self.indice).total)
        self.assertEqual(1, buscar(Filtro(eco_ate="A45"), self.base, self.indice).total)

    def test_os_filtros_combinam(self) -> None:
        """O item inteiro numa linha: *as partidas de Carlsen em 2019 com Elo acima de 2700 na
        Najdorf*. Cada filtro sozinho traz mais; é a combinação que responde."""
        resposta = buscar(
            Filtro(brancas="Carlsen", ano_de=2019, ano_ate=2019, elo_minimo=2700, eco_de="B90"),
            self.base,
            self.indice,
        )
        self.assertEqual(1, resposta.total)
        achado = resposta.achados[0]
        self.assertEqual(
            ("Carlsen, Magnus", "Anand, Viswanathan", "B90", "2019.01.26"),
            (achado.brancas, achado.pretas, achado.eco, achado.data),
        )

    def test_a_ordem_e_da_mais_recente_para_a_mais_antiga(self) -> None:
        datas = [achado.data for achado in buscar(Filtro(ano_de=1000), self.base, self.indice).achados]
        self.assertEqual(sorted(datas, reverse=True), datas)

    def test_a_partida_sem_data_fica_no_fim_e_nao_no_comeco(self) -> None:
        """**O defeito que o `year` na ordenação existe para impedir.** `?` é maior que qualquer
        dígito como texto, então `????.??.??` viria **antes** de `2024.12.31` -- e a primeira
        página de toda busca seria feita das partidas sem data."""
        self.assertEqual("Sem, Data", self._brancas(evento="ch-RUS")[-1])

    def test_a_pagina_seguinte_continua_de_onde_a_anterior_parou(self) -> None:
        primeira = buscar(Filtro(ano_de=1000), self.base, self.indice, limite=5)
        segunda = buscar(Filtro(ano_de=1000), self.base, self.indice, limite=5, offset=primeira.proximo_offset)
        self.assertEqual(5, len(primeira.achados))
        self.assertEqual(11, primeira.total)
        self.assertTrue(primeira.ha_mais)
        self.assertEqual(5, primeira.proximo_offset)
        self.assertEqual([], [a for a in segunda.achados if a in primeira.achados], "página repetida")
        ultima = buscar(Filtro(ano_de=1000), self.base, self.indice, limite=5, offset=10)
        self.assertEqual(1, len(ultima.achados))
        self.assertFalse(ultima.ha_mais)

    def test_o_total_e_o_de_todas_e_nao_o_da_pagina(self) -> None:
        """Sem ele, "5 partidas" seria dito sobre uma busca que achou onze -- e quem escolhesse
        entre as cinco escolheria achando que viu tudo (a S-86 mediu isso)."""
        pagina = buscar(Filtro(ano_de=1000), self.base, self.indice, limite=3)
        self.assertEqual(3, len(pagina.achados))
        self.assertEqual(11, pagina.total)
        self.assertFalse(pagina.total_e_teto)

    def test_a_contagem_para_no_teto(self) -> None:
        """Contar todas as partidas de `1.e4` numa base de dez milhões custaria segundos para
        dizer um número que ninguém lê até o fim."""
        with mock.patch("chess_diagram_ocr.games_index.TETO_DE_CONTAGEM", 2):
            resposta = buscar(Filtro(ano_de=1000), self.base, self.indice)
        self.assertEqual(2, resposta.total)
        self.assertTrue(resposta.total_e_teto)
        self.assertTrue(resposta.ha_mais)

    def test_a_linha_traz_o_que_a_tabela_mostra_e_onde_a_partida_mora(self) -> None:
        achado = buscar(Filtro(brancas="Ivanov", qualquer_cor=False), self.base, self.indice).achados[0]
        self.assertEqual(
            ("Ivanov, A", 2210, "Petrov, B", 2180),
            (achado.brancas, achado.elo_brancas, achado.pretas, achado.elo_pretas),
        )
        self.assertEqual(
            ("1-0", "ch-RUS", "1998.05.01", "B22"),
            (achado.resultado, achado.evento, achado.data, achado.eco),
        )
        self.assertEqual(self.base, achado.caminho)
        partida = partida_em(achado.caminho, achado.offset)
        assert partida is not None
        self.assertEqual("Ivanov, A", partida.headers["White"], "o offset abre a partida da linha")

    def test_a_partida_sem_elo_sai_com_zero_e_nao_com_lixo(self) -> None:
        achado = buscar(Filtro(evento="ch-RUS", eco_de="B01"), self.base, self.indice).achados[0]
        self.assertEqual((0, 0), (achado.elo_brancas, achado.elo_pretas))

    def test_o_filtro_por_posicao_le_as_candidatas_e_diz_quantas_leu(self) -> None:
        """A posição **não** está no índice: ela é conferida relendo cada candidata que os outros
        filtros deixaram passar, e a resposta diz quantas foram examinadas em vez de fingir que
        foram todas."""
        tabuleiro = chess.Board()
        for lance in ("e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Be3", "e5"):
            tabuleiro.push_san(lance)
        resposta = buscar(Filtro(brancas="Carlsen", posicao=tabuleiro.board_fen()), self.base, self.indice)
        self.assertEqual(7, resposta.total, "o total continua sendo o dos filtros do índice")
        self.assertEqual(7, resposta.examinadas)
        self.assertEqual(7, len(resposta.achados), "todas as partidas de teste passam por esta posição")

    def test_a_posicao_que_ninguem_alcanca_devolve_pagina_vazia(self) -> None:
        resposta = buscar(Filtro(brancas="Carlsen", posicao="8/8/8/8/8/8/4K3/4k3"), self.base, self.indice)
        self.assertEqual((), resposta.achados)
        self.assertEqual(7, resposta.examinadas, "sete foram lidas e nenhuma passou")

    def test_a_base_sem_arquivo_nenhum_recusa_com_frase(self) -> None:
        with self.assertRaises(IndiceIndisponivel) as erro:
            buscar(Filtro(brancas="Carlsen"), self.raiz / "vazia", self.indice)
        self.assertIn("pgn_database", str(erro.exception))


class DoisPlanosDeBuscaTests(unittest.TestCase):
    """Os dois planos da segunda rodada da S-533 respondem **a mesma coisa** por caminhos opostos.

    A contagem para em `TETO_DE_CONTAGEM` e é ela que escolhe: acima do teto, a página sai andando
    pela árvore da ordem (`games_ordem`) de trás para a frente; abaixo, sai da árvore mais seletiva
    do filtro com a ordenação por cima. O que o crítico mediu na gigabase foi o segundo plano
    aplicado ao primeiro caso -- `ano 2019` sozinho em 2,8 s, a faixa `A00–E99` em 5,4 s --, e o
    conserto só vale se os dois caminhos derem a mesma página.

    Aqui o teto é rebaixado para 2, que é o que faz uma base de doze partidas exercitar os dois.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.pasta = tempfile.TemporaryDirectory()
        cls.raiz = Path(cls.pasta.name)
        cls.base = cls.raiz / "base.pgn"
        cls.base.write_text(
            "".join(
                _partida(
                    branco="Carlsen, Magnus" if n % 2 else f"Jogador{n}, A",
                    preto=f"Jogador{n}, B" if n % 2 else "Carlsen, Magnus",
                    data=f"20{18 + n % 4:02d}.0{1 + n % 9}.1{n % 10}",
                    eco=f"{chr(65 + n % 5)}{n % 10}{n % 10}",
                    evento="ch-RUS" if n % 3 else "Tata Steel Masters",
                    welo=str(2000 + 10 * n),
                    belo=str(2100 + 5 * n),
                )
                for n in range(12)
            ),
            encoding="utf-8",
        )
        cls.indice = cls.raiz / "indice.sqlite"
        build_index(cls.base, cls.indice)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.pasta.cleanup()

    def _pagina(self, filtro: Filtro, *, teto: int, limite: int = 100, offset: int = 0) -> list[tuple[str, int]]:
        with mock.patch.object(games_index, "TETO_DE_CONTAGEM", teto):
            resposta = buscar(filtro, self.base, self.indice, limite=limite, offset=offset)
        return [(achado.brancas, achado.offset) for achado in resposta.achados]

    def test_os_dois_planos_dao_a_mesma_pagina_para_cada_filtro(self) -> None:
        filtros = {
            "um jogador": Filtro(brancas="Carlsen"),
            "faixa de ECO larga": Filtro(eco_de="A00", eco_ate="E99"),
            "um ano": Filtro(ano_de=2019, ano_ate=2019),
            "evento por pedaço": Filtro(evento="ch-"),
            "Elo mínimo": Filtro(elo_minimo=2000),
            "combinado": Filtro(brancas="Carlsen", ano_de=2018, ano_ate=2021),
        }
        for rotulo, filtro in filtros.items():
            with self.subTest(filtro=rotulo):
                largo = self._pagina(filtro, teto=2)
                estreito = self._pagina(filtro, teto=1_000)
                self.assertEqual(estreito, largo, "os dois planos discordaram")
                self.assertTrue(largo, "o filtro do teste não casa nada e não prova coisa alguma")

    def test_os_dois_planos_paginam_igual(self) -> None:
        """A página seguinte é o mesmo `OFFSET` nos dois, e é onde um plano errado se denuncia."""
        filtro = Filtro(brancas="Carlsen", qualquer_cor=True)
        for offset in (0, 2, 4):
            with self.subTest(offset=offset):
                self.assertEqual(
                    self._pagina(filtro, teto=1_000, limite=2, offset=offset),
                    self._pagina(filtro, teto=2, limite=2, offset=offset),
                )

    def test_a_contagem_para_no_teto_e_a_resposta_diz_que_parou(self) -> None:
        with mock.patch.object(games_index, "TETO_DE_CONTAGEM", 2):
            resposta = buscar(Filtro(brancas="Carlsen"), self.base, self.indice)
        self.assertEqual(2, resposta.total)
        self.assertTrue(resposta.total_e_teto)
        self.assertEqual(12, len(resposta.achados), "o teto é da contagem, e não da página")


class SobrenomeDaBuscaTests(unittest.TestCase):
    """As três leituras do campo de nome (S-533, r2). Ver `games_index._sobrenomes`."""

    def test_a_ordem_natural_acha_o_mesmo_que_a_da_base(self) -> None:
        """`Magnus Carlsen` devolvia zero em silêncio: `surname` lê `magnus carlsen`, que não é o
        sobrenome de ninguém. Fora de um `.pgn` é assim que se escreve um nome."""
        self.assertIn("carlsen", games_index._sobrenomes("Magnus Carlsen"))
        self.assertIn("carlsen", games_index._sobrenomes("Carlsen, Magnus"))
        self.assertIn("carlsen", games_index._sobrenomes("Carlsen"))

    def test_a_forma_inteira_continua_valendo(self) -> None:
        """`Van der Wiel` sem vírgula não vira `wiel` **em vez de**: a forma inteira é a primeira,
        e a última palavra só acrescenta uma sonda que não casa com nada."""
        formas = games_index._sobrenomes("Van der Wiel")
        self.assertEqual("van der wiel", formas[0])
        self.assertIn("wiel", formas)

    def test_o_sufixo_de_geracao_entra_como_forma_propria(self) -> None:
        """`Vehre Jr, John L` entra no dicionário como `vehre jr` -- o `Jr` está antes da vírgula --
        e são 264 grafias assim na gigabase. Quem digita `Vehre` tem de achá-las."""
        formas = games_index._sobrenomes("Vehre")
        self.assertIn("vehre", formas)
        self.assertIn("vehre jr", formas)
        self.assertIn("vehre iii", formas)

    def test_campo_vazio_nao_vira_forma_nenhuma(self) -> None:
        """Uma forma vazia casaria com o jogador zero, que é "sem nome" -- ou seja, com tudo."""
        self.assertEqual((), games_index._sobrenomes(""))
        self.assertEqual((), games_index._sobrenomes("   "))
