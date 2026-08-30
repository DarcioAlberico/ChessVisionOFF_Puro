"""O cache de posições (S-84): o que ele promete é que a base não seja aberta duas vezes.

Os testes que importam aqui não são os de ida e volta do arquivo -- são os que guardam
decisões: a pergunta sem resposta fica registrada, o fingerprint descarta o cache de outra
base, a contagem sobrevive à truncagem da lista, e — desde a S-140 — **ler sobre um livro não
lê o acervo**.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import chess

from chess_diagram_ocr import games_cache
from chess_diagram_ocr.cli.games import _positions_index
from chess_diagram_ocr.games_cache import (
    CachedPosition,
    PositionCache,
    PositionStore,
    database_fingerprint,
    open_store,
)
from chess_diagram_ocr.games_db import PositionHit, PositionIndex, scan_by_positions
from chess_diagram_ocr.games_index import index_fingerprint

UMA = "8/8/8/8/8/8/4K3/4k3"
OUTRA = "8/8/8/8/8/8/3K4/3k4"
AUSENTE = "8/8/8/8/8/8/2K5/2k5"


def indice(**achados: list[PositionHit]) -> PositionIndex:
    resultado = PositionIndex()
    for colocacao, partidas in achados.items():
        resultado.hits[colocacao] = partidas
        resultado.counts[colocacao] = len(partidas)
    return resultado


def partida(nome: str, data: str = "1990.01.01", lance: int = 20) -> PositionHit:
    return PositionHit(move_number=lance, side_to_move="w", headers={"White": nome, "Date": data})


class PerguntaTests(unittest.TestCase):
    """As decisões do módulo, sobre o cache em memória -- montar um SQLite não muda nenhuma."""

    def setUp(self) -> None:
        self.cache = PositionStore.in_memory()
        self.addCleanup(self.cache.close)

    def test_a_posicao_sem_resposta_fica_registrada_como_perguntada(self) -> None:
        """**A decisão central do módulo.** Sem isto, as 1.922 posições do acervo que a base
        não conhece voltariam ao conjunto-alvo de toda varredura futura, para sempre."""
        self.cache.update(indice(**{UMA: [partida("Anderssen")]}), {UMA, AUSENTE})
        self.assertEqual(self.cache.missing({UMA, AUSENTE}), set(), "as duas foram perguntadas")
        self.assertEqual(self.cache.get(AUSENTE).count, 0, "e uma delas não tem resposta")
        self.assertEqual(self.cache.answered_of({UMA, AUSENTE}), 1)

    def test_o_que_falta_e_so_o_que_ninguem_perguntou(self) -> None:
        self.cache.update(indice(**{UMA: [partida("Anderssen")]}), {UMA})
        self.assertEqual(self.cache.missing({UMA, OUTRA}), {OUTRA})

    def test_a_posicao_sem_resposta_nao_vira_casamento(self) -> None:
        self.cache.update(PositionIndex(), {AUSENTE})
        self.assertEqual(self.cache.to_index({AUSENTE}).hits, {})

    def test_o_indice_reconstruido_traz_contagem_e_candidatas(self) -> None:
        self.cache.update(indice(**{UMA: [partida("Anderssen"), partida("Morphy")]}), {UMA})
        refeito = self.cache.to_index({UMA})
        self.assertEqual(refeito.counts[UMA], 2)
        self.assertEqual([p.headers["White"] for p in refeito.hits[UMA]], ["Anderssen", "Morphy"])

    def test_a_contagem_sobrevive_a_lista_truncada(self) -> None:
        """Uma posição em 147 partidas guarda 32 e conta 147 -- e é a contagem que impede a
        lista curta de passar por completa."""
        muitas = PositionIndex()
        muitas.hits[UMA] = [partida(f"J{n}") for n in range(40)]
        muitas.counts[UMA] = 147
        self.cache.update(muitas, {UMA})
        guardada = self.cache.get(UMA)
        self.assertEqual(guardada.count, 147)
        self.assertEqual(len(guardada.games), 32)
        self.assertTrue(guardada.truncated)

    def test_a_candidata_volta_do_disco_inteira(self) -> None:
        """O que a lista da S-86 mostra vem daqui: lance, vez, headers e o selo de conferida."""
        original = PositionHit(
            move_number=24,
            side_to_move="b",
            headers={"White": "Karpov", "Black": "Korchnoi", "Date": "1974.09.12"},
            verified=False,
        )
        self.cache.update(indice(**{UMA: [original]}), {UMA})
        (volta,) = self.cache.get(UMA).games
        self.assertEqual(volta.move_number, 24)
        self.assertEqual(volta.side_to_move, "b")
        self.assertEqual(volta.headers["Black"], "Korchnoi")
        self.assertFalse(volta.verified, "e o selo, que decide o que pode ser preenchido")

    def test_a_colocacao_nunca_perguntada_responde_vazia_e_nao_erro(self) -> None:
        self.assertEqual(self.cache.get(AUSENTE).count, 0)
        self.assertEqual(self.cache.get(AUSENTE).games, ())


class PorLivroTests(unittest.TestCase):
    """**O item da S-140:** responder sobre um livro não pode custar o acervo.

    O instrumento é contar quantas linhas o cache materializa. Antes era o arquivo inteiro em
    todo caminho -- `json.loads` não sabe ler metade de um JSON --, e o custo crescia com o
    acervo enquanto a pergunta não crescia com nada.
    """

    LIVRO = tuple(f"8/8/8/8/8/8/{n}K5/4k3" for n in range(1, 4))

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.arquivo = Path(self.pasta.name) / "cache.sqlite"
        self.cache = open_store(self.arquivo)
        self.addCleanup(self.cache.close)
        # Um acervo: as tres colocacoes do livro aberto, e 200 de outros livros.
        acervo = {*self.LIVRO, *(f"8/8/8/8/8/{n}p6/8/4k3" for n in range(200))}
        self.cache.update(indice(**{c: [partida("Anderssen")] for c in acervo}), acervo)
        self.assertEqual(len(self.cache), 203, "o acervo inteiro está guardado")

    def _linhas_lidas(self, chamada: object) -> int:
        """Quantas linhas o cache converteu em resposta -- o custo real da pergunta."""
        contador = {"n": 0}
        original = games_cache._da_linha

        def contando(linha: object) -> CachedPosition:
            contador["n"] += 1
            return original(linha)  # type: ignore[arg-type]

        games_cache._da_linha = contando  # type: ignore[assignment]
        try:
            chamada()  # type: ignore[operator]
        finally:
            games_cache._da_linha = original  # type: ignore[assignment]
        return contador["n"]

    def test_o_indice_do_livro_nao_le_as_posicoes_dos_outros(self) -> None:
        lidas = self._linhas_lidas(lambda: self.cache.to_index(set(self.LIVRO)))
        self.assertEqual(lidas, len(self.LIVRO), "três colocações pedidas, três linhas lidas")

    def test_a_candidata_de_um_diagrama_custa_uma_linha(self) -> None:
        """O caminho da tela: abrir a lista de um diagrama não é abrir o acervo."""
        self.assertEqual(self._linhas_lidas(lambda: self.cache.get(self.LIVRO[0])), 1)

    def test_o_que_falta_no_livro_e_respondido_sem_ler_linha_nenhuma(self) -> None:
        """`missing` só precisa das chaves, e é o que a Galeria pergunta antes de varrer."""
        self.assertEqual(self._linhas_lidas(lambda: self.cache.missing(set(self.LIVRO))), 0)

    def test_o_indice_do_livro_traz_o_livro_e_so_ele(self) -> None:
        refeito = self.cache.to_index(set(self.LIVRO))
        self.assertEqual(set(refeito.hits), set(self.LIVRO))

    def test_o_alvo_maior_que_o_lote_de_consulta_nao_derruba(self) -> None:
        """40 mil colocações num `IN (...)` levantariam `too many SQL variables` -- e é o
        conjunto-alvo do `cvoff-games --all`, que é o caso que roda de verdade."""
        alvos = {f"8/8/8/8/8/8/8/{n}k6" for n in range(games_cache._LOTE_CONSULTA * 3)}
        self.assertEqual(self.cache.missing(alvos), alvos)
        self.assertEqual(self.cache.to_index(alvos).hits, {})
        self.assertEqual(self.cache.answered_of(alvos), 0)


class ArquivoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text('[Event "x"]\n', encoding="utf-8")
        self.arquivo = self.raiz / "cache.sqlite"

    def _grava(self) -> None:
        with open_store(self.arquivo, database=self.base) as cache:
            cache.update(indice(**{UMA: [partida("Anderssen")]}), {UMA})

    def test_o_cache_volta_inteiro_da_mesma_base(self) -> None:
        self._grava()
        with open_store(self.arquivo, database=self.base) as lido:
            self.assertEqual(lido.missing({UMA}), set())
            self.assertEqual(lido.to_index({UMA}).counts[UMA], 1)

    def test_base_trocada_descarta_o_cache_inteiro(self) -> None:
        """As contagens de uma base não valem para outra, e é a contagem que autoriza
        preencher header (S-74). Meio cache seria procedência inventada."""
        self._grava()
        outra = self.raiz / "outra.pgn"
        outra.write_text('[Event "y"]\n' * 50, encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            lido = open_store(self.arquivo, database=outra)
        self.addCleanup(lido.close)
        self.assertEqual(len(lido), 0)
        self.assertEqual(lido.missing({UMA}), {UMA}, "tudo volta a ser perguntado")

    def test_arquivo_ilegivel_responde_vazio_em_vez_de_derrubar(self) -> None:
        """Falhar para o lado do vazio significa "varra" -- o comportamento anterior ao cache.
        Derrubar o comando trocaria uma varredura por um erro."""
        self.arquivo.write_text("isto não é um banco", encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            lido = open_store(self.arquivo, database=self.base)
        self.addCleanup(lido.close)
        self.assertEqual(len(lido), 0)
        self.assertTrue(self.arquivo.exists(), "e o arquivo do usuário continua onde estava")

    def test_arquivo_ausente_e_cache_vazio_e_nao_erro(self) -> None:
        with open_store(self.raiz / "nunca_existiu.sqlite", database=self.base) as lido:
            self.assertEqual(len(lido), 0)

    def test_base_inexistente_nao_derruba_o_fingerprint(self) -> None:
        impressao = database_fingerprint(self.raiz / "nao_existe.pgn")
        self.assertEqual(impressao["files"][0]["size"], 0)

    def test_acrescentar_uma_base_descarta_o_cache(self) -> None:
        """**A parte da S-93 que mais importa para a honestidade dos números.** Uma base a mais
        muda a contagem de *todas* as posições já perguntadas: a que estava em uma partida pode
        estar em três. Um cache que sobrevivesse a isso responderia "partida única" sobre uma
        base que tem quatro -- e é a contagem que autoriza preencher header (S-74).
        """
        self._grava()
        outra = self.raiz / "outra.pgn"
        outra.write_text('[Event "y"]\n', encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            lido = open_store(self.arquivo, database=[self.base, outra])
        self.addCleanup(lido.close)
        self.assertEqual(len(lido), 0)
        self.assertEqual(lido.missing({UMA}), {UMA}, "tudo volta a ser perguntado")

    def test_a_conexao_aberta_sabe_dizer_se_ainda_vale(self) -> None:
        """O que a Galeria pergunta a cada troca de livro, e é o que substituiu reler tudo."""
        with open_store(self.arquivo, database=self.base) as cache:
            self.assertTrue(cache.matches(self.base))
            outra = self.raiz / "outra.pgn"
            outra.write_text('[Event "y"]\n', encoding="utf-8")
            self.assertFalse(cache.matches([self.base, outra]))

    # ------------------------------------------ duas passadas ao mesmo tempo (S-113)

    def test_gravar_nao_apaga_o_que_outro_processo_gravou_no_meio(self) -> None:
        """**O fluxo que o próprio README sugere perdia uma das duas passadas.**

        Deixar `cvoff-games --all` rodando enquanto se anota um livro na Galeria: com o cache
        em JSON, os dois liam o dicionário inteiro no começo, varriam ~30 min cada e gravavam
        no fim *o objeto lido lá atrás* -- a segunda a terminar sobrescrevia a primeira, sem
        erro e sem log. Com uma linha por colocação não há retrato para substituir.
        """
        nosso = open_store(self.arquivo, database=self.base)
        self.addCleanup(nosso.close)
        outro_processo = open_store(self.arquivo, database=self.base)
        self.addCleanup(outro_processo.close)

        outro_processo.update(indice(**{OUTRA: [partida("Morphy")]}), {OUTRA})
        nosso.update(indice(**{UMA: [partida("Anderssen")]}), {UMA})

        with open_store(self.arquivo, database=self.base) as lido:
            self.assertEqual(lido.missing({UMA, OUTRA}), set(), "as duas passadas sobrevivem")
            self.assertEqual(lido.to_index({OUTRA}).hits[OUTRA][0].headers["White"], "Morphy")

    def test_a_pergunta_sem_resposta_do_outro_processo_tambem_sobrevive(self) -> None:
        """`count == 0` é resposta, não ausência (S-84) -- e a segunda gravação tem de preservá-la.

        Perder um "a base não conhece esta posição" a devolve ao alvo de toda varredura
        futura, que é o custo que o cache existe para não pagar duas vezes.
        """
        with open_store(self.arquivo, database=self.base) as outro_processo:
            outro_processo.update(indice(), {AUSENTE})
        with open_store(self.arquivo, database=self.base) as nosso:
            nosso.update(indice(**{UMA: [partida("Anderssen")]}), {UMA})
        with open_store(self.arquivo, database=self.base) as lido:
            self.assertEqual(lido.missing({AUSENTE}), set())

    # ------------------------------------------------- o fingerprint, uma regra só (S-113)

    def test_tocar_o_mtime_de_uma_base_intacta_nao_invalida_o_cache(self) -> None:
        """**56 minutos de varredura por um carimbo de data.**

        Uma cópia da pasta, um sync de nuvem ou um antivírus mudam o `mtime` sem tocar num
        byte. O `games_index.py` sempre usou só nome e tamanho; aqui havia `int(st_mtime)`
        junto, e eram duas regras para a mesma pergunta -- com a mais estrita jogando fora o
        trabalho.
        """
        self._grava()
        antigo = self.base.stat().st_mtime
        os.utime(self.base, (antigo + 86_400, antigo + 86_400))
        with open_store(self.arquivo, database=self.base) as lido:
            self.assertEqual(lido.missing({UMA}), set(), "o conteúdo não mudou, o cache vale")

    def test_o_tamanho_continua_descartando_o_cache(self) -> None:
        """O que saiu foi o `mtime`, e não a guarda: base com outro conteúdo tem outro tamanho."""
        self._grava()
        self.base.write_text('[Event "x"]\n' * 99, encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            lido = open_store(self.arquivo, database=self.base)
        self.addCleanup(lido.close)
        self.assertEqual(len(lido), 0)

    def test_a_marca_do_cache_e_a_mesma_regra_da_marca_do_indice(self) -> None:
        """Duas perguntas iguais -- "é a mesma base?" -- não podem ter duas respostas."""
        outra = self.raiz / "outra.pgn"
        outra.write_text('[Event "y"]\n', encoding="utf-8")
        bases = [self.base, outra]
        do_cache = [(item["name"], item["size"]) for item in database_fingerprint(bases)["files"]]
        do_indice = [
            (parte.rsplit(":", 1)[0], int(parte.rsplit(":", 1)[1]))
            for parte in index_fingerprint(bases).split("|")
        ]
        self.assertEqual(do_cache, do_indice)

    # ------------------------------------------------------ o esquema, travado (S-140)

    def test_a_colocacao_e_a_arvore_e_nao_ha_indice_ao_lado(self) -> None:
        """Um `CREATE INDEX placement` desfaria a economia sem quebrar comportamento nenhum --
        é o mesmo guarda que o item 1 pôs no índice por nome."""
        self._grava()
        # `closing` porque o `__exit__` do `sqlite3` **nao** fecha a conexao: ele comita ou
        # desfaz a transacao, e e tudo (S-435). O handle ficava aberto sobre o arquivo, e o
        # `cleanup` do `TemporaryDirectory` deste mesmo teste estourava com `WinError 32`.
        # Hoje passa porque a contagem de referencias do CPython fecha a tempo -- sincronia,
        # nao garantia, e no 3.13 ela deixou de valer.
        with closing(sqlite3.connect(self.arquivo)) as conexao:
            (esquema,) = conexao.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'positions'"
            ).fetchone()
            indices = conexao.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'positions'"
            ).fetchall()
        self.assertIn("WITHOUT ROWID", esquema)
        self.assertIn("PRIMARY KEY", esquema)
        self.assertEqual(indices, [], "a chave primária já é a árvore de busca")


class MigracaoTests(unittest.TestCase):
    """O JSON da S-84 entra uma vez e sai do caminho. Ele não é um formato aceito (S-140)."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text('[Event "x"]\n', encoding="utf-8")
        self.json = self.raiz / "games_positions.json"
        self.sqlite = self.raiz / "games_positions.sqlite"
        # Os **dois** padrões, e o par importa: a migração só roda quando o artefato aberto é
        # o do acervo. Remendar só um deles faria este teste passar sobre o `data/` de verdade
        # -- e foi assim que ele renomeou o JSON desta máquina na primeira execução.
        for nome, valor in (("DEFAULT_CACHE_PATH", self.json), ("DEFAULT_STORE_PATH", self.sqlite)):
            self.addCleanup(setattr, games_cache, nome, getattr(games_cache, nome))
            setattr(games_cache, nome, valor)

    def _json(self, fingerprint: dict[str, object] | None = None) -> None:
        antigo = PositionCache(
            fingerprint=fingerprint if fingerprint is not None else database_fingerprint(self.base)
        )
        antigo.positions[UMA] = CachedPosition(count=3, games=(partida("Anderssen"),))
        antigo.positions[AUSENTE] = CachedPosition(count=0)
        self.json.write_text(
            json.dumps(
                {
                    "version": 1,
                    "database": antigo.fingerprint,
                    "positions": {c: g.to_dict() for c, g in antigo.positions.items()},
                }
            ),
            encoding="utf-8",
        )

    def test_as_56_horas_de_varredura_nao_sao_jogadas_fora(self) -> None:
        """Descartar o JSON custaria uma varredura de ~56 min por acervo, e nada mudou nele:
        a resposta é a mesma, o lugar é que é outro."""
        self._json()
        with open_store(self.sqlite, database=self.base) as cache:
            self.assertEqual(cache.get(UMA).count, 3)
            self.assertEqual(cache.get(UMA).games[0].headers["White"], "Anderssen")
            self.assertEqual(cache.missing({AUSENTE}), set(), "e o 'a base não conhece' também")

    def test_o_json_migrado_sai_do_caminho(self) -> None:
        """Depois da migração não há dois caminhos de leitura vivos -- e o arquivo continua no
        disco, renomeado, porque apagar o que era do usuário não é da alçada de uma migração."""
        self._json()
        open_store(self.sqlite, database=self.base).close()
        self.assertFalse(self.json.exists())
        self.assertTrue(self.json.with_suffix(".json.migrado").exists())

    def test_a_migracao_nao_roda_duas_vezes(self) -> None:
        """Com o banco em pé, um JSON que reaparecesse seria mais velho que ele."""
        self._json()
        open_store(self.sqlite, database=self.base).close()
        self._json()  # alguem restaurou um backup
        with open_store(self.sqlite, database=self.base) as cache:
            self.assertEqual(len(cache), 2)
        self.assertTrue(self.json.exists(), "e ele fica onde está, sem ser lido")

    def test_o_json_de_outra_base_nao_entra(self) -> None:
        """Contagem de outra base é resposta errada, e guardada é pior que uma varredura a pagar."""
        self._json({"files": [{"name": "outra.pgn", "size": 999_999}]})
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            cache = open_store(self.sqlite, database=self.base)
        self.addCleanup(cache.close)
        self.assertEqual(len(cache), 0)

    def test_json_ilegivel_nao_impede_o_cache_de_abrir(self) -> None:
        self.json.write_text("{isto não é json", encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            cache = open_store(self.sqlite, database=self.base)
        self.addCleanup(cache.close)
        self.assertEqual(len(cache), 0)


class SemBaseTests(unittest.TestCase):
    """O `_positions_index` do `cvoff-games`: o que ele lê, e quando ele abre a base."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(
            '[Event "x"]\n[White "Anderssen"]\n[Black "Kieseritzky"]\n\n1. e4 e5 2. f4 *\n',
            encoding="utf-8",
        )
        self.arquivo = self.raiz / "cache.sqlite"

    def _alvo(self) -> str:
        tabuleiro = chess.Board()
        for lance in ("e4", "e5", "f4"):
            tabuleiro.push_san(lance)
        return tabuleiro.board_fen()

    def _args(self, **extra: object) -> object:
        import argparse

        return argparse.Namespace(
            cache=self.arquivo, no_cache=False, workers=1, database=[self.base], **extra
        )

    def test_a_segunda_execucao_nao_abre_a_base(self) -> None:
        """É o que o cache existe para comprar: ~30 min por gigabase viram segundos."""
        alvo = self._alvo()
        primeiro = _positions_index([self.base], {alvo}, self._args())
        self.assertEqual(primeiro.counts[alvo], 1)

        lidas: list[object] = []
        original = games_cache.PositionStore.missing

        def espiando(self_: PositionStore, alvos: object) -> set[str]:
            faltando = original(self_, alvos)  # type: ignore[arg-type]
            lidas.append(faltando)
            return faltando

        games_cache.PositionStore.missing = espiando  # type: ignore[assignment]
        try:
            segundo = _positions_index([self.base], {alvo}, self._args())
        finally:
            games_cache.PositionStore.missing = original  # type: ignore[assignment]
        self.assertEqual(lidas, [set()], "nada faltava, então a base não foi aberta")
        self.assertEqual(segundo.counts[alvo], 1)

    def test_a_varredura_de_verdade_grava_o_que_respondeu(self) -> None:
        alvo = self._alvo()
        achado = scan_by_positions([self.base], {alvo})
        self.assertEqual(achado.counts[alvo], 1)
        with open_store(self.arquivo, database=self.base) as cache:
            self.assertEqual(cache.update(achado, {alvo}), 1)
        with open_store(self.arquivo, database=self.base) as lido:
            self.assertEqual(lido.get(alvo).count, 1)


class PassadaDescartadaTests(unittest.TestCase):
    """Uma varredura que não terminou **não** vira "a base não conhece" (S-171).

    **O defeito, e ele é de corrupção silenciosa.** `scan_by_positions` devolvia um
    `PositionIndex()` vazio tanto para "a base respondeu, e não achou nada" quanto para "a
    passada foi descartada". Quem grava registra o conjunto-alvo **inteiro** como perguntado
    (é a decisão da S-84, e ela é certa), então gravar uma passada descartada escreveria
    `count = 0` sobre milhares de colocações que ninguém chegou a procurar -- e, perguntado
    sendo perguntado, elas nunca mais voltariam ao alvo de varredura nenhuma.

    O caminho de cancelamento escapava por sorte: a Galeria conferia `cancel.is_set()` antes
    de gravar e o `cvoff-games` não tem cancelamento. Com a guarda de filho morto a passada
    passou a poder ser descartada **sem ninguém ter cancelado**, e a sorte acabou.
    """

    def setUp(self) -> None:
        self.cache = PositionStore.in_memory()
        self.addCleanup(self.cache.close)

    def test_a_passada_descartada_nao_grava_uma_linha(self) -> None:
        alvos = {UMA, OUTRA, AUSENTE}
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            gravadas = self.cache.update(PositionIndex(complete=False), alvos)

        self.assertEqual(gravadas, 0)
        self.assertEqual(len(self.cache), 0)

    def test_as_colocacoes_continuam_por_perguntar(self) -> None:
        """**A metade que importa.** Gravar as marcaria como perguntadas, e o cache existe
        justamente para não perguntar duas vezes -- então elas sumiriam para sempre."""
        alvos = {UMA, OUTRA, AUSENTE}
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            self.cache.update(PositionIndex(complete=False), alvos)

        self.assertEqual(self.cache.missing(alvos), alvos)

    def test_a_passada_inteira_que_nao_achou_nada_continua_gravando(self) -> None:
        """O outro lado, e é o que a guarda não pode quebrar: "a base não conhece estas" é
        resposta, e são a maioria (1.922 de 3.563 no acervo medido)."""
        alvos = {UMA, AUSENTE}
        self.assertEqual(self.cache.update(PositionIndex(), alvos), 2)
        self.assertEqual(self.cache.missing(alvos), set(), "perguntadas, e sem resposta")
        self.assertEqual(self.cache.get(AUSENTE).count, 0)

    def test_o_cache_em_memoria_recusa_igual(self) -> None:
        """A guarda vale nas duas formas: o `PositionCache` é o que a migração usa."""
        cache = PositionCache()
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            cache.update(PositionIndex(complete=False), {UMA})
        self.assertEqual(cache.positions, {})

    def test_o_indice_completo_e_o_padrao(self) -> None:
        """Quem monta um `PositionIndex` à mão -- o cache ao reconstruir, os testes -- não pode
        precisar lembrar de dizer que ele está completo."""
        self.assertTrue(PositionIndex().complete)
        self.assertTrue(self.cache.to_index(None).complete)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
