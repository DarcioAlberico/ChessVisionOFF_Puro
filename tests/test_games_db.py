"""A base de partidas como terceira fonte de verdade (S-72).

Sem a base de 9,7 GB: um PGN de três partidas escrito na hora cobre o que pode quebrar --
casar sobrenome contra `Sobrenome, Nome`, colher só as partidas pedidas, achar o lance cuja
posição bate, e o teto por par.
"""

from __future__ import annotations

import bz2
import gzip
import json
import os
import tempfile
import threading
import unittest
import zipfile
from itertools import pairwise
from pathlib import Path
from unittest import mock

import chess

from chess_diagram_ocr import games_db
from chess_diagram_ocr.cli.games import _books, _matches_from_json, _matches_to_json, main, parse_args
from chess_diagram_ocr.gallery_scan import GalleryEntry
from chess_diagram_ocr.games_db import (
    SEM_FIM,
    WORKER_ENV,
    DiagramMatch,
    GameRecord,
    PositionHit,
    PositionIndex,
    _scan_positions_chunk,
    abrir_pgn,
    abrir_pgn_bytes,
    chunk_bounds,
    database_paths,
    decodificar_linha,
    existe_base,
    match_entries,
    match_positions,
    nome_da_base,
    occupancy,
    pair_from_caption,
    rank_candidates,
    scan_by_players,
    scan_by_positions,
    surname,
    tamanho_da_base,
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


ESTUDO_FEN = "2B5/5K2/3P1p1p/BbP2P1k/1P5P/r2n1N2/4n3/8"
"""A colocação do primeiro estudo da `Endgame_Study_Database_VI`, copiada do arquivo.

O alvo real do defeito corrigido em 2026-08-19, e por isso ele e não uma posição inventada:
é esta colocação que, procurada na base que a contém, casava zero vezes."""

PGN_DE_ESTUDOS = f"""﻿[Event "13th UAPA internet ty"]
[Site "?"]
[Date "2020.10.10"]
[White "Zilberstein=D"]
[Black "(+0357.52f7h5)"]
[Result "1-0"]
[SetUp "1"]
[FEN "{ESTUDO_FEN} w - - 0 1"]

1. d7 (1. Ba6 $2 Bc6 2. Bb7) 1... Bxd7 2. Bxd7 1-0

[Event "Outro concurso"]
[Site "?"]
[Date "1924.??.??"]
[White "Reti=R"]
[Black "(+0100.01)"]
[Result "1/2-1/2"]
[SetUp "1"]
[FEN "7K/8/k1P5/7p/8/8/8/8 w - - 0 1"]

1. Kg7 h4 2. Kf6 1/2-1/2
"""
"""Duas composições no formato em que a base do Heijden as publica -- **com a marca de ordem de
bytes na frente**, como o arquivo real tem.

A marca é parte do caso: a leitura por pedaços é binária, e sem tratá-la a primeira composição
de todo arquivo gravado no Windows perdia os headers."""


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


def _pedaco(colocacao: str) -> PositionIndex:
    """O que um processo devolveria: uma partida com aquela posição."""
    return PositionIndex(
        hits={colocacao: [PositionHit(move_number=7, side_to_move="b")]},
        counts={colocacao: 1},
        games_read=1,
    )


class _PoolFalso:
    """Um `mp.Pool` que só entrega pedaço quando perguntado com prazo (S-92).

    Existe porque o que a S-92 acrescentou ao laço não é a varredura: é a **espera**. Um pool
    de verdade sobre uma base de três partidas termina antes de o teste conseguir cancelar
    nada, e o que ficaria coberto seria o caso em que o cancelamento não importa.
    """

    def __init__(self, *, entrega: PositionIndex, ao_esperar: object = None) -> None:
        self.entrega = entrega
        self._ao_esperar = ao_esperar
        self.prazos: list[float | None] = []
        self.terminado = False

    def __enter__(self) -> _PoolFalso:
        return self

    def __exit__(self, *_excecao: object) -> bool:
        return False

    def imap_unordered(self, _funcao: object, _tarefas: object) -> _PoolFalso:
        return self

    def next(self, timeout: float | None = None) -> PositionIndex:  # noqa: A003 - o nome e do mp
        self.prazos.append(timeout)
        if self._ao_esperar is not None:
            # O clique chegando **durante** a espera, que e como ele chega de verdade.
            self._ao_esperar()
            raise games_db.mp.TimeoutError
        return self.entrega

    def terminate(self) -> None:
        self.terminado = True


class NomesTests(unittest.TestCase):
    def test_sobrenome_ignora_o_nome_e_o_acento(self) -> None:
        self.assertEqual(surname("De Castellvi, Francisco"), "de castellvi")
        self.assertEqual(surname("Réti, Richard"), "reti")
        self.assertEqual(surname("Coull"), "coull")

    def test_inicial_colada_do_livro_cai(self) -> None:
        """S-90: é como o `400 Quebra-cabeças` escreve um terço das legendas dele.

        Sem isto, `K. Spicak` não casava com `Spicak, Krzysztof` na base -- 109 dos 494 pares
        do acervo (22,1%) nunca chegavam a ser procurados, e sem aviso nenhum.
        """
        self.assertEqual(surname("K. Spicak"), "spicak")
        self.assertEqual(surname("De. Wagner"), "wagner")
        self.assertEqual(surname("E. Mence"), "mence")
        self.assertEqual(surname("A Hong"), "hong")

    def test_a_particula_nao_e_inicial_e_sobrevive(self) -> None:
        """`De` sem ponto e com duas letras é sobrenome, não abreviação. A regra separa os dois
        pelo ponto e pelo tamanho -- e o `De Castellvi` acima é o caso que ela não pode quebrar."""
        self.assertEqual(surname("De Castellvi"), "de castellvi")
        self.assertEqual(surname("Van der Wiel, John"), "van der wiel")

    def test_nome_que_e_so_uma_inicial_nao_vira_vazio(self) -> None:
        """Vazio casaria com qualquer coisa, que é o oposto do que a normalização existe para
        fazer. A guarda é o `len(tokens) > 1`."""
        self.assertEqual(surname("K."), "k.")
        self.assertEqual(surname("A"), "a")

    def test_a_legenda_com_inicial_vira_par_procuravel(self) -> None:
        self.assertEqual(pair_from_caption("Mosesov – De. Wagner"), ("mosesov", "wagner"))

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

    def test_a_base_e_todo_pgn_da_pasta_e_nao_o_maior(self) -> None:
        """Era "o maior", e o maior escondia o resto (S-93).

        Nesta máquina eram duas gigabases, e a partida `Hutchings x Keene, 1973` -- procurada
        por nome, por data e pelas 64 casas na maior -- estava na menor.
        """
        torneio = Path(self.pasta.name) / "torneio.pgn"
        torneio.write_text(PGN[:100], encoding="utf-8")
        self.assertEqual(database_paths(Path(self.pasta.name)), [self.base, torneio])

    def test_a_ordem_e_por_nome_e_nao_por_tamanho(self) -> None:
        """A ordem virou identidade: o índice grava a posição nesta lista como o número do
        arquivo, e uma ordem que mudasse quando um arquivo crescesse faria cada offset apontar
        para o arquivo errado."""
        pasta = Path(self.pasta.name)
        (pasta / "zz_pequena.pgn").write_text(PGN[:80], encoding="utf-8")
        (pasta / "aa_grande.pgn").write_text(PGN * 5, encoding="utf-8")
        nomes = [caminho.name for caminho in database_paths(pasta)]
        self.assertEqual(nomes, ["aa_grande.pgn", "base.pgn", "zz_pequena.pgn"])

    def test_pasta_sem_base_devolve_lista_vazia(self) -> None:
        self.assertEqual(database_paths(Path(self.pasta.name) / "vazia"), [])

    def test_varre_as_duas_bases_na_mesma_busca(self) -> None:
        """O que a S-93 destrava: a segunda base da pasta era invisível."""
        outra = Path(self.pasta.name) / "outra.pgn"
        outra.write_text(
            '[Event "Havana"]\n[White "Capablanca, Jose Raul"]\n[Black "Lasker, Emanuel"]\n'
            f'[Result "1-0"]\n\n{IMORTAL} 1-0\n',
            encoding="utf-8",
        )
        colhidas = scan_by_players(
            [self.base, outra], [("anderssen", "kieseritzky"), ("capablanca", "lasker")]
        )
        self.assertEqual(len(colhidas[("anderssen", "kieseritzky")]), 2, "da primeira base")
        self.assertEqual(len(colhidas[("capablanca", "lasker")]), 1, "da segunda, que antes era ignorada")

    def test_o_teto_por_par_vale_para_o_conjunto_e_nao_por_arquivo(self) -> None:
        """São 40 partidas para reproduzir, venham de onde vierem."""
        outra = Path(self.pasta.name) / "outra.pgn"
        outra.write_text(PGN, encoding="utf-8")
        colhidas = scan_by_players([self.base, outra], [("anderssen", "kieseritzky")], max_games_per_pair=3)
        self.assertEqual(len(colhidas[("anderssen", "kieseritzky")]), 3, "e não 3 por arquivo")


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


class ComposicaoTests(unittest.TestCase):
    """Estudo e problema: a partida que **começa montada**.

    Medido na `Endgame_Study_Database_VI` antes da correção: 93.838 estudos lidos, **zero**
    posições casadas -- com o alvo copiado do `[FEN]` do próprio arquivo. O replay partia da
    posição inicial, o primeiro lance da solução é ilegal ali, e cada composição morria
    inteira e em silêncio.
    """

    ESTUDO = ESTUDO_FEN
    SOLUCAO = "1. d7 (1. Kxf6 $2 Nxb4 2. d7 (2. Bxb4 Rxf3) 2... Nd5+) 1... Bxd7 2. Bxd7"
    """A solução do estudo, com a variante e a sub-variante que o arquivo real traz."""

    def test_a_posicao_montada_e_uma_posicao_da_partida(self) -> None:
        """Num livro de estudos, o diagrama impresso **é** a posição montada -- e só ela."""
        estudo = GameRecord(setup_fen=f"{self.ESTUDO} w - - 0 1", movetext=self.SOLUCAO)
        primeira, lance, vez_branca = next(iter(estudo.positions()))
        self.assertEqual(primeira, self.ESTUDO)
        self.assertEqual(lance, 1)
        self.assertTrue(vez_branca, "a vez sai do próprio FEN, que é o que o livro imprime")

    def test_a_solucao_parte_da_posicao_montada(self) -> None:
        estudo = GameRecord(setup_fen=f"{self.ESTUDO} w - - 0 1", movetext=self.SOLUCAO)
        self.assertEqual(len(list(estudo.positions())), 4, "a montada e os três lances da linha")

    def test_a_variante_nao_entra_como_linha_principal(self) -> None:
        """`1. d7 (1. Ba6 ...)` era lido como `d7 Ba6 ...`: posições que a composição não tem."""
        estudo = GameRecord(setup_fen=f"{self.ESTUDO} w - - 0 1", movetext=self.SOLUCAO)
        colocacoes = [colocacao for colocacao, _, _ in estudo.positions()]

        tabuleiro = chess.Board(f"{self.ESTUDO} w - - 0 1")
        tabuleiro.push_san("Kxf6")
        self.assertNotIn(tabuleiro.board_fen(), colocacoes)

    def test_variante_aninhada_tambem_fica_de_fora(self) -> None:
        estudo = GameRecord(setup_fen=f"{self.ESTUDO} w - - 0 1", movetext=self.SOLUCAO)
        colocacoes = [colocacao for colocacao, _, _ in estudo.positions()]

        tabuleiro = chess.Board(f"{self.ESTUDO} w - - 0 1")
        for lance in ("Kxf6", "Nxb4", "Bxb4", "Rxf3"):
            tabuleiro.push_san(lance)
        self.assertNotIn(tabuleiro.board_fen(), colocacoes)

    def test_parentese_sem_par_fica_no_que_veio_antes_dele(self) -> None:
        """Notação quebrada é regra numa base de 19 GB: o resto cai, como no lance ilegal."""
        estudo = GameRecord(setup_fen=f"{self.ESTUDO} w - - 0 1", movetext="1. d7 (1. Ba6 Bc6 1... Bxd7")
        colocacoes = [colocacao for colocacao, _, _ in estudo.positions()]

        depois_de_d7 = chess.Board(f"{self.ESTUDO} w - - 0 1")
        depois_de_d7.push_san("d7")
        self.assertEqual(colocacoes, [self.ESTUDO, depois_de_d7.board_fen()], "o lance antes do parêntese fica")

    def test_fen_que_o_python_chess_recusa_descarta_a_composicao_inteira(self) -> None:
        """E não meia dela a partir de um tabuleiro que não é o dela."""
        self.assertEqual(list(GameRecord(setup_fen="lixo", movetext="1. e4").positions()), [])

    def test_partida_normal_nao_ganha_a_posicao_inicial(self) -> None:
        """Emiti-la poria a mesma colocação em 21 milhões de partidas, e ela não decide nada."""
        partida = GameRecord(movetext=IMORTAL)
        primeira, _, _ = next(iter(partida.positions()))
        self.assertNotEqual(primeira, chess.Board().board_fen())


class BaseDeEstudosTests(unittest.TestCase):
    """O arquivo inteiro, pelos dois leitores de PGN -- que são dois, e os dois precisavam do FEN."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.base = Path(self.pasta.name) / "estudos.pgn"
        self.base.write_text(PGN_DE_ESTUDOS, encoding="utf-8")

    def test_a_busca_por_posicao_acha_o_diagrama_do_estudo(self) -> None:
        indice = scan_by_positions(self.base, {ESTUDO_FEN}, workers=1)
        self.assertEqual(indice.games_read, 2)
        (achado,) = indice.hits[ESTUDO_FEN]
        self.assertEqual(achado.move_number, 1)
        self.assertEqual(achado.side_to_move, "w")

    def test_os_headers_da_primeira_composicao_sobrevivem_a_marca_de_bytes(self) -> None:
        """Regressão: o `[Event` da primeira vinha com três bytes na frente e ninguém o via."""
        indice = scan_by_positions(self.base, {ESTUDO_FEN}, workers=1)
        (achado,) = indice.hits[ESTUDO_FEN]
        self.assertEqual(achado.headers.get("Event"), "13th UAPA internet ty")
        self.assertEqual(achado.headers.get("White"), "Zilberstein=D")

    def test_a_busca_por_nome_tambem_parte_da_posicao_montada(self) -> None:
        """O outro leitor: o de `scan_by_players`, que colhe a partida e a reproduz depois.

        O par é `(compositor, código GBR)` porque é assim que a base de estudos preenche
        `[White]` e `[Black]` -- e é por isso que o caminho por nome alcança pouco numa base de
        composições: quem procura por ela é a busca por posição.
        """
        par = ("reti=r", surname("(+0100.01)"))
        colhidas = scan_by_players(self.base, {par})
        (estudo,) = colhidas[par]
        self.assertEqual(next(iter(estudo.positions()))[0], "7K/8/k1P5/7p/8/8/8/8")


class PosicaoTests(unittest.TestCase):
    """A busca por posição (S-73): a que alcança diagrama sem nome na legenda."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.base = Path(self.pasta.name) / "base.pgn"
        self.base.write_text(PGN, encoding="utf-8")

    def tearDown(self) -> None:
        self.pasta.cleanup()

    def test_acha_a_posicao_com_lance_vez_e_partida(self) -> None:
        colocacao, lance, vez_branca = colocacao_apos(IMORTAL, 7)
        indice = scan_by_positions(self.base, {colocacao}, workers=1)
        self.assertEqual(indice.games_read, 3)
        (achado,) = indice.hits[colocacao]
        self.assertEqual(achado.move_number, lance)
        self.assertEqual(achado.side_to_move, "w" if vez_branca else "b")
        self.assertEqual(achado.headers["Event"], "London")

    def test_conta_todas_as_partidas_que_passam_pela_posicao(self) -> None:
        """Duas partidas diferentes atravessam a mesma abertura -- e a contagem é o freio."""
        colocacao, _, _ = colocacao_apos(OUTRA, 4)
        indice = scan_by_positions(self.base, {colocacao}, workers=1)
        self.assertEqual(indice.counts[colocacao], 2)

    def test_le_o_pedaco_inteiro_e_nao_para_no_meio(self) -> None:
        """Regressão: em modo texto o `tell()` é um *cookie* opaco, não um byte.

        Comparado contra o fim do pedaço, ele encerrava o laço cedo -- 5 partidas lidas de
        2.000, sem erro nenhum. Um arquivo de três partidas não pega isto: o cookie ainda é
        pequeno. Daí este ter 300.
        """
        grande = Path(self.pasta.name) / "grande.pgn"
        grande.write_text(PGN * 100, encoding="utf-8")
        indice = scan_by_positions(grande, {colocacao_apos(IMORTAL, 7)[0]}, workers=1)
        self.assertEqual(indice.games_read, 300)
        self.assertEqual(indice.counts[colocacao_apos(IMORTAL, 7)[0]], 100)

    def test_posicao_ausente_nao_aparece(self) -> None:
        indice = scan_by_positions(self.base, {"8/8/8/8/8/8/8/K6k"}, workers=1)
        self.assertEqual(indice.hits, {})

    def test_as_duas_bases_entram_na_mesma_varredura(self) -> None:
        """Uma passada só sobre os dois arquivos, e a contagem soma as duas (S-93).

        **Partida repetida nas duas bases conta duas vezes**, e isso não é defeito: são duas
        partidas registradas, e o `max_games` que decide se preencher é honesto continua
        medindo o que a base de fato tem. O efeito colateral é real e está declarado -- uma
        posição que era "partida única" pode passar a ter duas candidatas iguais.
        """
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        outra = Path(self.pasta.name) / "outra.pgn"
        outra.write_text(PGN, encoding="utf-8")
        indice = scan_by_positions([self.base, outra], {colocacao}, workers=1)
        self.assertEqual(indice.games_read, 6, "as três partidas de cada arquivo")
        self.assertEqual(indice.counts[colocacao], 2)

    def test_alvo_vazio_nao_le_o_arquivo(self) -> None:
        self.assertEqual(scan_by_positions(self.base, set(), workers=1).games_read, 0)

    def test_base_inexistente_devolve_vazio_em_vez_de_levantar(self) -> None:
        self.assertEqual(scan_by_positions(Path("nao_existe.pgn"), {"x"}, workers=1).games_read, 0)

    def test_o_corte_em_pedacos_cai_sempre_numa_fronteira_de_partida(self) -> None:
        """Cortar no meio de uma partida faria o pedaço seguinte reproduzir meio movetext."""
        with self.base.open("rb") as fh:
            for inicio, _fim in chunk_bounds(self.base, 3):
                fh.seek(inicio)
                if inicio:
                    self.assertTrue(fh.readline().startswith(b"[Event "))

    def test_os_pedacos_cobrem_o_arquivo_inteiro_sem_sobrepor(self) -> None:
        pedacos = chunk_bounds(self.base, 3)
        self.assertEqual(pedacos[0][0], 0)
        self.assertEqual(pedacos[-1][1], self.base.stat().st_size)
        for anterior, seguinte in pairwise(pedacos):
            self.assertEqual(anterior[1], seguinte[0], "fim de um é começo do outro")

    def test_dividir_em_pedacos_nao_muda_a_resposta(self) -> None:
        """É o que o paralelismo tem de garantir, e o que um corte errado quebraria."""
        colocacao, _, _ = colocacao_apos(OUTRA, 4)
        um = scan_by_positions(self.base, {colocacao}, workers=1)
        varios = PositionIndex()
        for pedaco in chunk_bounds(self.base, 3):
            varios.merge(
                _scan_positions_chunk(
                    (self.base, pedaco[0], pedaco[1], frozenset({colocacao}), frozenset({occupancy(colocacao)}), 8)
                ),
                max_hits=8,
            )
        self.assertEqual(varios.counts, um.counts)
        self.assertEqual(varios.games_read, um.games_read)

    # ----------------------------------------------- o porteiro de ocupação (S-85)
    # 3,6× medido, e o que estes quatro guardam é que ele não mudou uma resposta.

    def test_a_ocupacao_lida_da_string_e_a_do_python_chess(self) -> None:
        """É a garantia de que a conta de bits é a mesma que o `Board` mantém a cada lance --
        e a numeração é a parte fácil de errar: a colocação escreve a oitava fila primeiro."""
        for movetext, lances in ((IMORTAL, 7), (OUTRA, 4), (IMORTAL, 14)):
            colocacao, _, _ = colocacao_apos(movetext, lances)
            tabuleiro = chess.Board(None)
            tabuleiro.set_board_fen(colocacao)
            self.assertEqual(occupancy(colocacao), tabuleiro.occupied, colocacao)

    def test_a_posicao_inicial_ocupa_as_quatro_filas_das_pontas(self) -> None:
        inicial = chess.Board().board_fen()
        self.assertEqual(occupancy(inicial), 0xFFFF00000000FFFF)

    def test_o_porteiro_barra_o_que_nao_e_alvo_e_deixa_passar_o_alvo(self) -> None:
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        partida = GameRecord(headers={"White": "A, A", "Black": "B, B"}, movetext=IMORTAL)
        com = list(partida.positions(frozenset({occupancy(colocacao)})))
        sem = list(partida.positions())
        self.assertEqual(len(sem), 14, "sem porteiro, todo lance sai")
        self.assertIn((colocacao, *com[0][1:]), com, "o alvo continua saindo")
        self.assertLess(len(com), len(sem), "e o que não é alvo nem vira string")

    def test_ocupacao_igual_com_pecas_diferentes_nao_e_casamento(self) -> None:
        """O porteiro é filtro, não critério -- e este teste é o que garante isso.

        Uma dama trocada por um bispo na mesma casa tem a **mesma** ocupação e passa pelo
        porteiro; quem recusa é o `board_fen()` que vem depois, como sempre recusou. Se um dia
        alguém "otimizar" comparando só a ocupação, este teste quebra.
        """
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        impostora = colocacao.replace("q", "b", 1) if "q" in colocacao else colocacao.replace("Q", "B", 1)
        self.assertNotEqual(impostora, colocacao)
        self.assertEqual(occupancy(impostora), occupancy(colocacao), "mesmas casas ocupadas")
        indice = scan_by_positions(self.base, {impostora}, workers=1)
        self.assertEqual(indice.hits, {}, "passou pelo porteiro e foi recusada pela colocação")

    def test_a_varredura_com_porteiro_da_os_mesmos_casamentos(self) -> None:
        """A prova de que a otimização não mudou a resposta: mesmos lances, mesmas contagens.

        `positions()` sem porteiro é o caminho de antes da S-85; a varredura é a de agora.
        """
        for movetext, lances in ((IMORTAL, 7), (OUTRA, 4), (OUTRA, 6)):
            colocacao, lance, vez = colocacao_apos(movetext, lances)
            indice = scan_by_positions(self.base, {colocacao}, workers=1)
            esperado = sum(
                1
                for partida in (
                    GameRecord(movetext=IMORTAL),
                    GameRecord(movetext=OUTRA),
                    GameRecord(movetext=OUTRA),
                )
                for achada, _, _ in partida.positions()
                if achada == colocacao
            )
            self.assertEqual(indice.counts.get(colocacao, 0), esperado, colocacao)
            self.assertEqual(indice.hits[colocacao][0].move_number, lance)
            self.assertEqual(indice.hits[colocacao][0].side_to_move, "w" if vez else "b")

    def test_dentro_de_um_processo_filho_nao_cria_outros(self) -> None:
        """A guarda contra a recursão do `spawn` (S-26) -- ela travou a máquina uma vez.

        Com o marcador no ambiente, `mp.Pool` não pode ser tocado: se ele for, o teste falha
        aqui em vez de o usuário descobrir com centenas de processos abertos.
        """
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        with (
            mock.patch.dict(os.environ, {WORKER_ENV: "1"}),
            mock.patch.object(games_db.mp, "Pool", side_effect=AssertionError("criou processo dentro do filho")),
        ):
            indice = scan_by_positions(self.base, {colocacao}, workers=4)
        self.assertEqual(indice.games_read, 3, "sem paralelismo, mas com a resposta certa")

    def test_o_marcador_nao_sobra_no_ambiente(self) -> None:
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        scan_by_positions(self.base, {colocacao}, workers=1)
        self.assertNotIn(WORKER_ENV, os.environ)

    # ------------------------------------------------- o cancelamento (S-92)
    # Com um pool de verdade estes três seriam corrida: a base tem três partidas e os pedaços
    # terminam antes de qualquer clique. O que se verifica aqui não é a varredura -- é o que o
    # laço faz **enquanto** ela não termina, que é onde o botão de cancelar vive.

    def test_cancelar_descarta_a_passada_inteira(self) -> None:
        """Meia base lida dá contagem que não vale, e a contagem decide se preencher é honesto.

        Uma posição achada em um dos dez pedaços sairia daqui com `count=1` -- a marca de
        partida única, que preenche tudo -- quando a base pode ter 47 partidas com ela.
        """
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        cancelar = threading.Event()
        cancelar.set()
        pool = _PoolFalso(entrega=_pedaco(colocacao))
        with mock.patch.object(games_db.mp, "Pool", return_value=pool):
            indice = scan_by_positions(self.base, {colocacao}, workers=4, cancel=cancelar)
        self.assertEqual(indice.hits, {})
        self.assertEqual(indice.counts, {})
        self.assertTrue(pool.terminado, "os processos ficariam lendo a base depois do cancelamento")

    def test_o_cancelamento_e_notado_enquanto_os_pedacos_rodam(self) -> None:
        """Conferi-lo só entre pedaços concluídos seria esperar a passada dividida por dez."""
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        cancelar = threading.Event()
        pool = _PoolFalso(entrega=_pedaco(colocacao), ao_esperar=cancelar.set)
        with mock.patch.object(games_db.mp, "Pool", return_value=pool):
            indice = scan_by_positions(self.base, {colocacao}, workers=4, cancel=cancelar)
        self.assertEqual(indice.counts, {}, "chegou depois de a espera começar, e ainda assim valeu")
        self.assertTrue(pool.terminado)
        self.assertEqual(pool.prazos, [games_db.CANCEL_POLL_SECONDS], "a espera tem de ter prazo")

    def test_sem_cancelamento_o_laco_junta_todos_os_pedacos(self) -> None:
        """O caminho normal: a espera com prazo não pode perder nem repetir pedaço."""
        colocacao, _, _ = colocacao_apos(IMORTAL, 7)
        pool = _PoolFalso(entrega=_pedaco(colocacao))
        progresso: list[tuple[int, int]] = []
        with mock.patch.object(games_db.mp, "Pool", return_value=pool):
            indice = scan_by_positions(
                self.base, {colocacao}, workers=4, progress=lambda feitos, total: progresso.append((feitos, total))
            )
        feitos, total = progresso[-1]
        self.assertEqual(feitos, total, "o laço só termina quando todos os pedaços voltaram")
        self.assertEqual(progresso, [(i, total) for i in range(1, total + 1)])
        self.assertEqual(indice.counts[colocacao], total, "um de cada pedaço, somados")
        self.assertFalse(pool.terminado)

    def test_a_ordem_das_partidas_nao_depende_de_qual_processo_terminou_antes(self) -> None:
        """Reprodutibilidade: quem consome usa a primeira partida da lista.

        Sem ordenar, a mesma posição saía com um lance numa execução e outro na seguinte --
        e foi assim que dois diagramas ficaram com procedência que não batia.
        """
        indice = PositionIndex()
        antiga = PositionHit(move_number=20, side_to_move="w", headers={"Date": "1851.06.21", "White": "A"})
        nova = PositionHit(move_number=84, side_to_move="b", headers={"Date": "2022.01.01", "White": "Z"})
        indice.hits["x"] = [nova, antiga]
        indice.sort()
        self.assertEqual(indice.hits["x"][0].move_number, 20, "a mais antiga vem primeiro")

    def test_casamento_por_posicao_vira_DiagramMatch(self) -> None:
        colocacao, lance, _ = colocacao_apos(IMORTAL, 7)
        indice = scan_by_positions(self.base, {colocacao}, workers=1)
        entrada = GalleryEntry(3, 1, colocacao, caption="sem nome nenhum aqui")
        (achado,) = match_positions([entrada], indice)
        self.assertEqual(achado.key, (3, 1))
        self.assertEqual(achado.move_number, lance)
        self.assertEqual(achado.games_matched, 1)
        self.assertIn("Anderssen", achado.game_label)

    # -------------------------------------------- as candidatas que sobrevivem (S-83)

    def test_a_posicao_ambigua_entrega_todas_as_candidatas(self) -> None:
        """O que a S-83 conserta: a lista era calculada e o consumidor recebia um elemento.

        Duas partidas da base atravessam a mesma abertura -- e são justamente esses os 373
        diagramas do acervo em que o desempate por data escolhia sozinho.
        """
        colocacao, _, _ = colocacao_apos(OUTRA, 4)
        indice = scan_by_positions(self.base, {colocacao}, workers=1)
        entrada = GalleryEntry(0, 0, colocacao, caption="")
        (achado,) = match_positions([entrada], indice)
        self.assertEqual(achado.games_matched, 2)
        self.assertEqual(len(achado.candidates), 2)
        self.assertTrue(achado.ambiguous)
        self.assertEqual(
            {c.headers.get("Event") for c in achado.candidates},
            {"Revanche", "Outro torneio"},
            "as duas partidas, e não a vencedora duas vezes",
        )

    def test_a_primeira_candidata_e_a_resposta_do_casamento(self) -> None:
        """A lista e os campos preenchidos têm de contar a mesma história: a tela vai mostrar
        uma marcada como escolhida, e a anotação não pode dizer outra."""
        colocacao, _, _ = colocacao_apos(OUTRA, 4)
        indice = scan_by_positions(self.base, {colocacao}, workers=1)
        (achado,) = match_positions([GalleryEntry(0, 0, colocacao, caption="")], indice)
        self.assertEqual(achado.move_number, achado.candidates[0].move_number)
        self.assertEqual(achado.side_to_move, achado.candidates[0].side_to_move)
        self.assertEqual(achado.game_label, achado.candidates[0].label)

    def test_a_chave_da_candidata_identifica_a_partida_e_nao_a_posicao_na_lista(self) -> None:
        """É o que faz a escolha humana sobreviver a uma revarredura que reordene a lista.

        O lance fica de fora: a mesma partida pode passar duas vezes pela mesma posição, e as
        duas continuam sendo a mesma escolha.
        """
        cabecalho = {"White": "Anderssen, Adolf", "Black": "Kieseritzky, Lionel", "Date": "1851.06.21"}
        primeira = PositionHit(move_number=12, side_to_move="w", headers=cabecalho)
        repetida = PositionHit(move_number=30, side_to_move="w", headers=cabecalho)
        outra = PositionHit(move_number=12, side_to_move="w", headers={**cabecalho, "Date": "1852.01.01"})
        self.assertEqual(primeira.key, repetida.key)
        self.assertNotEqual(primeira.key, outra.key)

    def test_o_caminho_por_nome_entrega_candidatas_na_mesma_forma(self) -> None:
        """Duas rotas, um tipo só de candidata -- senão a tela precisaria de dois códigos."""
        colocacao, _, _ = colocacao_apos(OUTRA, 4)
        partida = GameRecord(headers={"White": "A, A", "Black": "B, B", "Date": "1990.01.01"}, movetext=OUTRA)
        segunda = GameRecord(headers={"White": "A, A", "Black": "B, B", "Date": "1980.01.01"}, movetext=OUTRA)
        entrada = GalleryEntry(0, 0, colocacao, caption="A - B")
        (achado,) = match_entries([entrada], {("a", "b"): [partida, segunda]})
        self.assertEqual(len(achado.candidates), 2)
        self.assertEqual(achado.candidates[0].headers["Date"], "1980.01.01", "a mais antiga primeiro")
        self.assertEqual(achado.game_label, achado.candidates[0].label)

    def test_a_mesma_partida_nao_vira_duas_candidatas(self) -> None:
        """Uma repetição de posição faz a partida casar duas vezes; oferecer a mesma escolha
        duas vezes não é oferecer duas escolhas."""
        repeticao = "1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6"
        partida = GameRecord(headers={"White": "A, A", "Black": "B, B"}, movetext=repeticao)
        colocacao = colocacao_apos(repeticao, 2)[0]
        entrada = GalleryEntry(0, 0, colocacao, caption="A - B")
        (achado,) = match_entries([entrada], {("a", "b"): [partida]})
        self.assertEqual(achado.games_matched, 1)
        self.assertEqual(len(achado.candidates), 1)

    def test_o_teto_de_candidatas_e_o_da_varredura(self) -> None:
        self.assertEqual(games_db.MAX_HITS_PER_POSITION, 32, "8 era o teto de quando ninguém escolhia")


class LegendaDesempataTests(unittest.TestCase):
    """A S-91: onde a legenda nomeia uma candidata só, a data deixa de decidir."""

    def _hit(self, brancas: str, pretas: str, data: str, lance: int = 20) -> PositionHit:
        return PositionHit(
            move_number=lance,
            side_to_move="w",
            headers={"White": brancas, "Black": pretas, "Date": data},
        )

    def setUp(self) -> None:
        self.antiga = self._hit("Havasi, Kornel", "Tartakower, Saviely", "1929.01.01", lance=40)
        self.citada = self._hit("Karpov, Anatoly", "Korchnoi, Viktor", "1974.09.12", lance=24)

    def test_a_legenda_puxa_a_candidata_dela_para_a_frente(self) -> None:
        ordenadas, so_uma = rank_candidates([self.antiga, self.citada], ("karpov", "korchnoi"))
        self.assertEqual(ordenadas[0], self.citada, "a data escolheria a de 1929")
        self.assertTrue(so_uma)

    def test_a_ordem_das_cores_nao_e_exigida(self) -> None:
        """O livro escreve "Coull - Stanciu" sem prometer quem tinha as brancas, e o
        interpretador devolve os nomes na ordem em que aparecem."""
        _, so_uma = rank_candidates([self.citada], ("korchnoi", "karpov"))
        self.assertTrue(so_uma)

    def test_legenda_que_bate_com_varias_nao_desempata_mas_ordena(self) -> None:
        segunda = self._hit("Karpov, Anatoly", "Korchnoi, Viktor", "1978.07.07")
        ordenadas, so_uma = rank_candidates([self.antiga, self.citada, segunda], ("karpov", "korchnoi"))
        self.assertFalse(so_uma, "duas partidas do mesmo par não identificam qual")
        self.assertEqual(ordenadas[:2], (self.citada, segunda), "mas as duas vêm na frente")
        self.assertEqual(ordenadas[0].headers["Date"], "1974.09.12", "e entre elas, a mais antiga")

    def test_legenda_que_nao_bate_com_nenhuma_nao_reordena_nem_descarta(self) -> None:
        """**Ordena, não filtra.** 26,5% das legendas discordam da base mesmo em partida única
        -- grafia, legenda do vizinho, o livro nomeando outra coisa. Filtrar por uma fonte que
        erra um quarto das vezes tiraria a partida certa da lista."""
        ordenadas, so_uma = rank_candidates([self.antiga, self.citada], ("gareev", "aitbayev"))
        self.assertEqual(ordenadas, (self.antiga, self.citada), "a ordem por data, intacta")
        self.assertFalse(so_uma)

    def test_sem_legenda_o_resultado_e_o_de_antes(self) -> None:
        ordenadas, so_uma = rank_candidates([self.antiga, self.citada], None)
        self.assertEqual(ordenadas, (self.antiga, self.citada))
        self.assertFalse(so_uma)

    def test_o_casamento_marca_que_a_legenda_confirmou(self) -> None:
        indice = PositionIndex()
        indice.hits["x"] = [self.antiga, self.citada]
        indice.counts["x"] = 2
        entrada = GalleryEntry(0, 0, "x", caption="Karpov - Korchnoi")
        (achado,) = match_positions([entrada], indice)
        self.assertTrue(achado.caption_confirmed)
        self.assertEqual(achado.move_number, 24, "o lance da partida que o livro cita")
        self.assertEqual(achado.candidates[0], self.citada)

    def test_sem_a_legenda_o_mesmo_casamento_cai_na_data(self) -> None:
        indice = PositionIndex()
        indice.hits["x"] = [self.antiga, self.citada]
        indice.counts["x"] = 2
        (achado,) = match_positions([GalleryEntry(0, 0, "x", caption="Diagrama 41")], indice)
        self.assertFalse(achado.caption_confirmed)
        self.assertEqual(achado.move_number, 40, "a mais antiga -- e é isto que erra 72,3%")


class ComandoTests(unittest.TestCase):
    """`cvoff-games`: o que ele decide antes de tocar na base."""

    def test_o_padrao_e_a_busca_por_posicao_e_nao_gravar(self) -> None:
        args = parse_args([])
        self.assertEqual(args.mode, "positions")
        self.assertFalse(args.apply, "gravar em centenas de anotações não pode ser o padrão")
        self.assertEqual(args.max_games, 5)

    def test_names_troca_o_modo(self) -> None:
        self.assertEqual(parse_args(["--names"]).mode, "names")

    def test_livro_pedido_casa_por_pedaco_do_nome(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            galeria = Path(pasta)
            (galeria / "Karpov 1 - Best Games.index.json").write_text("{}", encoding="utf-8")
            (galeria / "Kemeri 1937.index.json").write_text("{}", encoding="utf-8")
            args = parse_args(["--book", "karpov", "--gallery-dir", str(galeria), "--pdf-dir", str(galeria)])
            self.assertEqual([caminho.stem for caminho in _books(args)], ["Karpov 1 - Best Games"])

    def test_todos_pega_os_livros_ja_varridos(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            galeria = Path(pasta)
            (galeria / "A.index.json").write_text("{}", encoding="utf-8")
            (galeria / "B.index.json").write_text("{}", encoding="utf-8")
            args = parse_args(["--all", "--gallery-dir", str(galeria), "--pdf-dir", str(galeria)])
            self.assertEqual(sorted(caminho.stem for caminho in _books(args)), ["A", "B"])

    def test_livro_nao_varrido_avisa_e_nao_entra(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            args = parse_args(["--book", "inexistente", "--gallery-dir", pasta, "--pdf-dir", pasta])
            with self.assertLogs("chess_diagram_ocr.cli.games", level="WARNING"):
                self.assertEqual(_books(args), [])

    def test_sem_base_no_disco_sai_com_codigo_proprio(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            codigo = main(["--all", "--database", str(Path(pasta) / "nao_existe.pgn"), "--gallery-dir", pasta])
            self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()


class DeterminismoDaVarreduraTests(unittest.TestCase):
    """A mesma base e o mesmo alvo devolvem as mesmas candidatas, com 1 e com N processos (S-138).

    **A primeira candidata da lista é a que vira o preenchimento automático.** Antes deste
    item, qual partida preenchia um diagrama dependia de quantos processos a varredura usou --
    um parâmetro de desempenho decidindo procedência.

    Dois defeitos com a mesma raiz: a ordenação acontecia **depois** do corte e **fora** do
    caminho sequencial.
    """

    COLOCACAO = "4k3/8/8/8/8/8/8/4K3"

    def _hit(self, data: str, *, lance: int = 7) -> PositionHit:
        return PositionHit(
            move_number=lance,
            side_to_move="w",
            headers={"White": f"W{data}", "Black": f"B{data}", "Date": data},
        )

    def _pedaco_com(self, datas: list[str]) -> PositionIndex:
        return PositionIndex(
            hits={self.COLOCACAO: [self._hit(data) for data in datas]},
            counts={self.COLOCACAO: len(datas)},
            games_read=len(datas),
        )

    def test_o_teto_guarda_as_mais_antigas_e_nao_as_que_chegaram_antes(self) -> None:
        """**O defeito 2, e o que ele custava.** O corte era por ordem de chegada, sobre um
        `imap_unordered`, e o `sort()` rodava depois -- sobre o que tinha sobrevivido. Para as
        posições com mais de 32 candidatas, duas varreduras da mesma base devolviam conjuntos
        diferentes, e a lista da S-86 mudava de conteúdo entre execuções."""
        recentes = self._pedaco_com([f"20{n:02d}.01.01" for n in range(10)])
        antigas = self._pedaco_com([f"19{n:02d}.01.01" for n in range(10)])

        total = PositionIndex()
        total.merge(recentes, max_hits=5)
        total.merge(antigas, max_hits=5)

        datas = [hit.headers["Date"] for hit in total.hits[self.COLOCACAO]]
        self.assertEqual(datas, [f"19{n:02d}.01.01" for n in range(5)], "as 5 mais antigas do conjunto")

    def test_a_ordem_de_chegada_dos_pedacos_nao_muda_o_resultado(self) -> None:
        """É a invariante inteira numa linha: `imap_unordered` não define ordem de chegada."""
        recentes = self._pedaco_com([f"20{n:02d}.01.01" for n in range(6)])
        antigas = self._pedaco_com([f"19{n:02d}.01.01" for n in range(6)])

        uma = PositionIndex()
        uma.merge(recentes, max_hits=4)
        uma.merge(antigas, max_hits=4)

        outra = PositionIndex()
        outra.merge(antigas, max_hits=4)
        outra.merge(recentes, max_hits=4)

        self.assertEqual(
            [hit.headers["Date"] for hit in uma.hits[self.COLOCACAO]],
            [hit.headers["Date"] for hit in outra.hits[self.COLOCACAO]],
        )

    def test_quem_sai_do_merge_ja_esta_ordenado(self) -> None:
        """A invariante mora no `merge` porque é lá que ela pertence -- e é o que faz o
        caminho sequencial e o paralelo concordarem sem cada um lembrar de ordenar."""
        total = PositionIndex()
        total.merge(self._pedaco_com(["2020.01.01", "1950.01.01", "1999.01.01"]), max_hits=32)

        datas = [hit.headers["Date"] for hit in total.hits[self.COLOCACAO]]
        self.assertEqual(datas, sorted(datas))

    def test_a_contagem_nao_e_cortada_pelo_teto(self) -> None:
        """A lista serve para preencher; a contagem, para decidir se preencher é honesto
        (S-74). Cortar a segunda faria uma posição de abertura parecer identificável."""
        total = PositionIndex()
        total.merge(self._pedaco_com([f"20{n:02d}.01.01" for n in range(10)]), max_hits=3)

        self.assertEqual(len(total.hits[self.COLOCACAO]), 3)
        self.assertEqual(total.counts[self.COLOCACAO], 10)

    def test_workers_1_devolve_a_lista_ordenada(self) -> None:
        """**O defeito 1.** O caminho sequencial devolvia antes do `total.sort()`, e é
        justamente o documentado como o de depuração: `--workers 1 = sem paralelismo`.

        Medido no enunciado com uma base de duas partidas (2020 e 1950) que compartilham uma
        posição: em paralelo a primeira candidata era a de 1950, sequencialmente a de 2020.
        """
        pedaco = self._pedaco_com(["2020.01.01", "1950.01.01"])

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.pgn"
            base.write_text('[Event "x"]\n\n1. e4 *\n', encoding="utf-8")
            with mock.patch.object(games_db, "_scan_positions_chunk", lambda _tarefa: pedaco):
                indice = games_db.scan_by_positions([base], {self.COLOCACAO}, workers=1)

        datas = [hit.headers["Date"] for hit in indice.hits[self.COLOCACAO]]
        self.assertEqual(datas, ["1950.01.01", "2020.01.01"], "a mais antiga primeiro, como o paralelo")


class CasamentosNoDiscoTests(unittest.TestCase):
    """O JSON de casamentos sobrevive à ida e volta, e a v1 continua carregando (S-128).

    **O formato v2 é o artefato dos 104 minutos de 2026-08-13.** Ele tem ramo de
    compatibilidade explícito para a v1 e não tinha teste nenhum: um `--save-matches` que
    gravasse errado só apareceria na próxima vez que alguém tentasse reaplicar -- meses depois,
    com a base já mudada e sem como refazer a comparação.
    """

    def _casamento(self, **campos: object) -> DiagramMatch:
        padrao: dict[str, object] = {
            "page_index": 3,
            "diagram_index": 2,
            "move_number": 24,
            "side_to_move": "b",
            "headers": {"White": "Karpov, Anatoly", "Black": "Korchnoi, Viktor", "Date": "1981.10.19"},
            "games_matched": 3,
            "game_label": "Karpov x Korchnoi, Merano 1981",
            "candidates": (
                PositionHit(move_number=24, side_to_move="b", headers={"White": "Karpov, Anatoly"}),
                PositionHit(move_number=31, side_to_move="w", headers={"White": "Outro"}, verified=False),
            ),
        }
        padrao.update(campos)
        return DiagramMatch(**padrao)  # type: ignore[arg-type]

    def test_a_ida_e_volta_preserva_tudo(self) -> None:
        livro = Path("Karpov 1.pdf")
        original = {livro: [self._casamento(), self._casamento(page_index=9, games_matched=1)]}

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "matches.json"
            caminho.write_text(json.dumps(_matches_to_json(original), ensure_ascii=False), encoding="utf-8")
            voltou = _matches_from_json(caminho, [livro])

        self.assertEqual(voltou[livro], original[livro])

    def test_a_candidata_nao_verificada_volta_nao_verificada(self) -> None:
        """A distinção decide **o que pode ser preenchido**: lance e vez vêm da posição, e sem
        posição seriam invenção (ver `PositionHit.verified`)."""
        livro = Path("livro.pdf")
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "m.json"
            caminho.write_text(json.dumps(_matches_to_json({livro: [self._casamento()]})), encoding="utf-8")
            voltou = _matches_from_json(caminho, [livro])

        self.assertFalse(voltou[livro][0].candidates[1].verified)
        self.assertTrue(voltou[livro][0].candidates[0].verified)

    def test_o_formato_v1_continua_carregando(self) -> None:
        """**É o artefato dos 104 minutos**, e ele não guardou candidatas. Vazio é a resposta
        honesta: inventar uma lista de um elemento diria "só existe esta"."""
        v1 = {
            "version": 1,
            "books": {
                "livro.pdf": [
                    {
                        "page_index": 1,
                        "diagram_index": 1,
                        "move_number": 12,
                        "side_to_move": "w",
                        "headers": {"White": "A", "Black": "B"},
                        "games_matched": 1,
                        "game_label": "A x B",
                    }
                ]
            },
        }
        livro = Path("livro.pdf")
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "v1.json"
            caminho.write_text(json.dumps(v1), encoding="utf-8")
            voltou = _matches_from_json(caminho, [livro])

        self.assertEqual(len(voltou[livro]), 1)
        self.assertEqual(voltou[livro][0].candidates, (), "sem candidatas, e não uma inventada")
        self.assertEqual(voltou[livro][0].move_number, 12)

    def test_livro_ausente_do_arquivo_devolve_lista_vazia(self) -> None:
        """Pedir um livro que não estava na varredura não pode derrubar o comando: o artefato
        cobre o acervo daquele dia, e o acervo cresce."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "m.json"
            caminho.write_text(json.dumps({"version": 2, "books": {}}), encoding="utf-8")
            self.assertEqual(_matches_from_json(caminho, [Path("novo.pdf")]), {Path("novo.pdf"): []})

    def test_o_arquivo_declara_a_versao(self) -> None:
        """Sem a versão gravada, o ramo de compatibilidade seria adivinhação sobre a forma."""
        self.assertEqual(_matches_to_json({})["version"], 2)


class _ProcessoFalso:
    def __init__(self, pid: int) -> None:
        self.pid = pid


class _PoolDePids:
    """O bastante de um `mp.Pool` para a guarda: a lista privada de processos."""

    def __init__(self, pids: list[int]) -> None:
        self._pool = [_ProcessoFalso(pid) for pid in pids]


class FilhoMortoTests(unittest.TestCase):
    """A varredura para em vez de esperar para sempre por um pedaço que não volta.

    **O defeito, reproduzido em 2026-08-18 com um `Pool` de verdade:** um filho que chama
    `os._exit` leva com ele o pedaço que estava lendo, e o `imap_unordered` nunca devolve
    aquele resultado. Com seis pedaços e um filho morto, cinco voltaram e o laço ficou
    pendurado -- 20 s de espera no teste, e numa passada real seriam os ~56 min inteiros com a
    Galeria dizendo "pedaço 9 de 10" até alguém desistir.

    A reprodução completa não cabe na suíte -- ela precisa de um `Pool` de verdade e de um
    filho que morra de propósito, e nenhum dos dois é coisa de rodar 2.000 vezes por dia. O que
    está travado aqui é a **decisão**: qual sinal conta como filho perdido, e o que se faz com
    a passada quando ele aparece.
    """

    def test_o_pool_intacto_nao_dispara_a_guarda(self) -> None:
        pool = _PoolDePids([10, 11, 12])
        nascidos = games_db._pids_do_pool(pool)
        self.assertEqual(nascidos, frozenset({10, 11, 12}))
        self.assertFalse(games_db._perdeu_um_filho(pool, nascidos))

    def test_o_pid_trocado_e_o_sinal(self) -> None:
        """**Por que o pid e não `is_alive()`:** o `Pool` repovoa o trabalhador morto, então
        olhar para "está vivo?" acha três vivos de novo. O que não volta ao que era é o
        conjunto de pids -- medido, ele troca no mesmo décimo de segundo em que o filho morre.
        """
        pool = _PoolDePids([10, 11, 12])
        nascidos = games_db._pids_do_pool(pool)

        pool._pool = [_ProcessoFalso(10), _ProcessoFalso(11), _ProcessoFalso(99)]

        self.assertTrue(games_db._perdeu_um_filho(pool, nascidos))

    def test_um_filho_a_menos_tambem_conta(self) -> None:
        """O caso em que o pool não repovoa a tempo: o conjunto encolhe, e encolher é perder."""
        pool = _PoolDePids([10, 11, 12])
        nascidos = games_db._pids_do_pool(pool)
        pool._pool = [_ProcessoFalso(10), _ProcessoFalso(11)]
        self.assertTrue(games_db._perdeu_um_filho(pool, nascidos))

    def test_sem_a_lista_privada_a_guarda_desliga_em_vez_de_levantar(self) -> None:
        """`_pool` é privado do `multiprocessing`. Numa versão que não o tenha, o que se perde é
        a guarda -- e não a varredura, que é o que um `AttributeError` custaria."""
        sem_pool = object()
        self.assertEqual(games_db._pids_do_pool(sem_pool), frozenset())
        self.assertFalse(games_db._perdeu_um_filho(sem_pool, frozenset()))

    def test_com_zero_nascidos_a_guarda_nao_acusa_pool_saudavel(self) -> None:
        """Sem saber quem nasceu não dá para dizer quem morreu, e acusar seria descartar
        varreduras boas por não ter o instrumento."""
        pool = _PoolDePids([10, 11, 12])
        self.assertFalse(games_db._perdeu_um_filho(pool, frozenset()))

    def test_a_passada_perdida_e_descartada_inteira_e_nao_pela_metade(self) -> None:
        """A mesma regra do cancelamento (S-92), pela mesma razão: quem viu parte da base tem
        contagem que não vale, e é a contagem que autoriza preencher header (S-74).

        Aqui o `Pool` é remendado para nascer já "com um filho a menos" na segunda olhada.
        """
        base = Path(self.pasta.name) / "base.pgn"
        base.write_text(
            '[Event "x"]\n[White "Anderssen"]\n[Black "Kieseritzky"]\n\n1. e4 e5 2. f4 *\n' * 50,
            encoding="utf-8",
        )
        tabuleiro = chess.Board()
        for lance in ("e4", "e5", "f4"):
            tabuleiro.push_san(lance)

        with mock.patch.object(games_db, "_perdeu_um_filho", return_value=True):
            with self.assertLogs("chess_diagram_ocr.games_db", level="ERROR") as registro:
                achado = games_db.scan_by_positions([base], {tabuleiro.board_fen()}, workers=2)

        self.assertEqual(achado.counts, {}, "nada gravado: meia base lida não é resposta")
        self.assertEqual(achado.hits, {})
        self.assertIn("morreu", registro.output[0])
        self.assertIn("descartada", registro.output[0])

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)


class LeitorDePGNTests(unittest.TestCase):
    """O leitor único da S-531: o mesmo PGN solto, em `.gz`, em `.bz2` e dentro de um `.zip`.

    O que pode quebrar calado: a pasta não enxergar o formato, o membro do `.zip` virar um
    `Path` que ninguém sabe abrir, a base comprimida ser cortada em pedaços que não existem, e a
    linha em Latin-1 sair com losango.
    """

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        dados = PGN.encode("utf-8")
        (self.raiz / "solta.pgn").write_bytes(dados)
        with gzip.open(self.raiz / "zipada.pgn.gz", "wb") as fh:
            fh.write(dados)
        with bz2.open(self.raiz / "bz.pgn.bz2", "wb") as fh:
            fh.write(dados)
        with zipfile.ZipFile(self.raiz / "pacote.zip", "w", zipfile.ZIP_DEFLATED) as zipado:
            zipado.writestr("dentro/torneio.pgn", dados)
            zipado.writestr("leia-me.txt", "isto nao e uma base")
        self.membro = self.raiz / "pacote.zip" / "dentro" / "torneio.pgn"

    def test_a_pasta_enxerga_as_quatro_formas_e_o_membro_do_zip(self) -> None:
        """O `.txt` de dentro do `.zip` fica de fora: cada membro `.pgn` é uma base, e só eles."""
        nomes = [nome_da_base(caminho) for caminho in database_paths(self.raiz)]
        self.assertEqual(nomes, ["bz.pgn.bz2", "pacote.zip/dentro/torneio.pgn", "solta.pgn", "zipada.pgn.gz"])

    def test_as_linhas_saem_iguais_venham_de_onde_vierem(self) -> None:
        with abrir_pgn(self.raiz / "solta.pgn") as solta:
            esperado = list(solta)
        for base in database_paths(self.raiz):
            with abrir_pgn(base) as fh:
                self.assertEqual(list(fh), esperado, nome_da_base(base))

    def test_nada_e_gravado_no_disco_ao_ler(self) -> None:
        """"Sem descompactar para o disco" é o item: a pasta tem de ficar como estava."""
        antes = sorted(caminho.name for caminho in self.raiz.iterdir())
        for base in database_paths(self.raiz):
            with abrir_pgn(base) as fh:
                for _ in fh:
                    pass
        self.assertEqual(sorted(caminho.name for caminho in self.raiz.iterdir()), antes)

    def test_a_busca_por_nome_le_a_base_comprimida(self) -> None:
        colhidas = scan_by_players(self.raiz / "zipada.pgn.gz", [("anderssen", "kieseritzky")])
        self.assertEqual(len(colhidas[("anderssen", "kieseritzky")]), 2)

    def test_a_busca_por_posicao_le_o_membro_do_zip_num_pedaco_so(self) -> None:
        """Não há como pular para o meio de um fluxo comprimido: a base é um pedaço, do zero ao
        `SEM_FIM`, e mesmo assim as três partidas são lidas."""
        tabuleiro = chess.Board()
        for lance in ("e4", "e5", "f4", "exf4", "Bc4"):
            tabuleiro.push_san(lance)
        alvo = tabuleiro.board_fen()
        self.assertEqual(chunk_bounds(self.membro, 4), [(0, SEM_FIM)])
        indice = scan_by_positions(self.membro, {alvo}, workers=1)
        self.assertEqual(indice.games_read, 3)
        self.assertEqual(indice.counts.get(alvo), 1)

    def test_os_bytes_lidos_sao_os_do_disco_e_nao_os_descompactados(self) -> None:
        """A régua do progresso é o arquivo comprimido -- é o único tamanho que se conhece antes."""
        base = self.raiz / "zipada.pgn.gz"
        with abrir_pgn_bytes(base) as fh:
            descompactados = sum(len(linha) for linha in fh)
            lidos = fh.bytes_lidos
        self.assertGreater(lidos, 0)
        self.assertLessEqual(lidos, tamanho_da_base(base))
        self.assertLess(lidos, descompactados, "um PGN comprime; se não comprimiu, a régua está no fluxo errado")

    def test_existe_e_tamanho_valem_para_o_membro(self) -> None:
        self.assertTrue(existe_base(self.membro))
        self.assertFalse(existe_base(self.raiz / "pacote.zip" / "nao_existe.pgn"))
        self.assertTrue(0 < tamanho_da_base(self.membro) < len(PGN.encode("utf-8")))
        self.assertEqual(tamanho_da_base(self.raiz / "sumiu.pgn"), 0)

    def test_linha_em_cp1252_decodifica_sem_losango_e_utf8_continua_utf8(self) -> None:
        """A decisão de codificação da S-531: UTF-8 estrito primeiro, cp1252 só na linha que falha."""
        linha = '[White "Prokeš, Ladislav"]'
        self.assertEqual(decodificar_linha(linha.encode("cp1252")), linha)
        self.assertEqual(decodificar_linha(linha.encode("utf-8")), linha)
        self.assertEqual(decodificar_linha(b"\xef\xbb\xbf" + linha.encode("utf-8")), linha, "a marca de bytes cai")

    def test_o_offset_do_fluxo_descompactado_leva_a_mesma_partida(self) -> None:
        """Os offsets do índice são do fluxo descompactado, então valem para o arquivo comprimido."""
        offset = PGN.encode("utf-8").index(b'[Event "Outro torneio"]')
        with abrir_pgn_bytes(self.raiz / "bz.pgn.bz2") as fh:
            fh.seek(offset)
            self.assertTrue(fh.readline().startswith(b'[Event "Outro torneio"]'))
            self.assertEqual(fh.tell(), offset + len(b'[Event "Outro torneio"]\n'))

    def test_zst_fica_fora_da_pasta_sem_o_pacote(self) -> None:
        """Listar o que não se sabe abrir seria uma base que falha na primeira busca."""
        (self.raiz / "moderna.pgn.zst").write_bytes(b"\x28\xb5\x2f\xfd")
        with mock.patch.object(games_db, "_TEM_ZSTANDARD", False):
            with self.assertLogs("chess_diagram_ocr.games_db", level="WARNING") as registro:
                nomes = [caminho.name for caminho in database_paths(self.raiz)]
        self.assertNotIn("moderna.pgn.zst", nomes)
        self.assertIn("zstandard", registro.output[0])

    def test_zip_ilegivel_avisa_e_fica_de_fora(self) -> None:
        (self.raiz / "quebrado.zip").write_bytes(b"isto nao e um zip")
        with self.assertLogs("chess_diagram_ocr.games_db", level="WARNING"):
            nomes = [nome_da_base(caminho) for caminho in database_paths(self.raiz)]
        self.assertFalse(any(nome.startswith("quebrado.zip") for nome in nomes))
