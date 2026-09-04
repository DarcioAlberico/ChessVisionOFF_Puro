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

from chess_diagram_ocr.games_db import GameRecord, database_paths
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

    def test_o_indice_novo_nao_tem_a_segunda_arvore(self) -> None:
        """`WITHOUT ROWID` com a chave composta, e **nenhum** `CREATE INDEX` ao lado (S-140).

        Medido em índice sintético de 1 milhão de partidas: 38,9 MB contra 21,8 MB, -44,0%, com
        a consulta no mesmo tempo. O que este teste trava é o esquema, que é o que produz o
        número -- alguém acrescentar de volta um `CREATE INDEX games_pair` desfaria a economia
        inteira sem quebrar nada.
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

        self.assertIn("WITHOUT ROWID", criacao.upper())
        self.assertIn("PRIMARY KEY", criacao.upper())
        self.assertEqual([], [nome for (nome,) in indices if not nome.startswith("sqlite_autoindex")])

    def test_a_mesma_partida_indexada_duas_vezes_nao_duplica(self) -> None:
        """A chave virou única: antes era uma linha duplicada em silêncio, agora seria erro."""
        conexao = sqlite3.connect(self.indice)
        try:
            linha = conexao.execute("SELECT pair, offset, file FROM games LIMIT 1").fetchone()
            conexao.execute("INSERT OR IGNORE INTO games VALUES (?, ?, ?)", linha)
            conexao.commit()
            repetidas = conexao.execute(
                "SELECT COUNT(*) FROM games WHERE pair = ? AND offset = ? AND file = ?", linha
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
        self.assertEqual(rodada.partidas, 3, "a pequena terminou e ficou; a grande foi desfeita")
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
