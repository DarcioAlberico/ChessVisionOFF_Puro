"""O cache de posições (S-84): o que ele promete é que a base não seja aberta duas vezes.

Os testes que importam aqui não são os de ida e volta do JSON -- são os três que guardam
decisões: a pergunta sem resposta fica registrada, o fingerprint descarta o cache de outra
base, e a contagem sobrevive à truncagem da lista.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import chess

from chess_diagram_ocr.cli.games import _positions_index
from chess_diagram_ocr.games_cache import (
    CachedPosition,
    PositionCache,
    database_fingerprint,
    load_cache,
    save_cache,
)
from chess_diagram_ocr.games_db import PositionHit, PositionIndex, scan_by_positions

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
    def test_a_posicao_sem_resposta_fica_registrada_como_perguntada(self) -> None:
        """**A decisão central do módulo.** Sem isto, as 1.922 posições do acervo que a base
        não conhece voltariam ao conjunto-alvo de toda varredura futura, para sempre."""
        cache = PositionCache()
        cache.update(indice(**{UMA: [partida("Anderssen")]}), {UMA, AUSENTE})
        self.assertEqual(cache.missing({UMA, AUSENTE}), set(), "as duas foram perguntadas")
        self.assertEqual(cache.positions[AUSENTE].count, 0, "e uma delas não tem resposta")
        self.assertEqual(cache.answered_of({UMA, AUSENTE}), 1)

    def test_o_que_falta_e_so_o_que_ninguem_perguntou(self) -> None:
        cache = PositionCache()
        cache.update(indice(**{UMA: [partida("Anderssen")]}), {UMA})
        self.assertEqual(cache.missing({UMA, OUTRA}), {OUTRA})

    def test_a_posicao_sem_resposta_nao_vira_casamento(self) -> None:
        cache = PositionCache()
        cache.update(PositionIndex(), {AUSENTE})
        self.assertEqual(cache.to_index({AUSENTE}).hits, {})

    def test_o_indice_reconstruido_traz_contagem_e_candidatas(self) -> None:
        original = indice(**{UMA: [partida("Anderssen"), partida("Morphy")]})
        cache = PositionCache()
        cache.update(original, {UMA})
        refeito = cache.to_index({UMA})
        self.assertEqual(refeito.counts[UMA], 2)
        self.assertEqual([p.headers["White"] for p in refeito.hits[UMA]], ["Anderssen", "Morphy"])

    def test_a_contagem_sobrevive_a_lista_truncada(self) -> None:
        """Uma posição em 147 partidas guarda 32 e conta 147 -- e é a contagem que impede a
        lista curta de passar por completa."""
        muitas = PositionIndex()
        muitas.hits[UMA] = [partida(f"J{n}") for n in range(40)]
        muitas.counts[UMA] = 147
        cache = PositionCache()
        cache.update(muitas, {UMA})
        guardada = cache.positions[UMA]
        self.assertEqual(guardada.count, 147)
        self.assertEqual(len(guardada.games), 32)
        self.assertTrue(guardada.truncated)


class FingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text("[Event \"x\"]\n", encoding="utf-8")
        self.arquivo = self.raiz / "cache.json"

    def tearDown(self) -> None:
        self.pasta.cleanup()

    def _grava(self) -> PositionCache:
        cache = PositionCache(fingerprint=database_fingerprint(self.base))
        cache.update(indice(**{UMA: [partida("Anderssen")]}), {UMA})
        save_cache(cache, self.arquivo)
        return cache

    def test_o_cache_volta_inteiro_da_mesma_base(self) -> None:
        self._grava()
        lido = load_cache(self.arquivo, database=self.base)
        self.assertEqual(lido.missing({UMA}), set())
        self.assertEqual(lido.to_index({UMA}).counts[UMA], 1)

    def test_base_trocada_descarta_o_cache_inteiro(self) -> None:
        """As contagens de uma base não valem para outra, e é a contagem que autoriza
        preencher header (S-74). Meio cache seria procedência inventada."""
        self._grava()
        outra = self.raiz / "outra.pgn"
        outra.write_text("[Event \"y\"]\n" * 50, encoding="utf-8")
        lido = load_cache(self.arquivo, database=outra)
        self.assertEqual(len(lido), 0)
        self.assertEqual(lido.missing({UMA}), {UMA}, "tudo volta a ser perguntado")

    def test_arquivo_ilegivel_devolve_vazio_em_vez_de_derrubar(self) -> None:
        """Falhar para o lado do vazio significa "varra" -- o comportamento anterior ao cache.
        Derrubar o comando trocaria uma varredura por um erro."""
        self.arquivo.write_text("{isto não é json", encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            self.assertEqual(len(load_cache(self.arquivo, database=self.base)), 0)

    def test_versao_desconhecida_e_refeita(self) -> None:
        self.arquivo.write_text(json.dumps({"version": 99, "positions": {UMA: {"count": 3}}}), encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.games_cache", level="WARNING"):
            self.assertEqual(len(load_cache(self.arquivo, database=self.base)), 0)

    def test_arquivo_ausente_e_cache_vazio_e_nao_erro(self) -> None:
        self.assertEqual(len(load_cache(self.raiz / "nunca_existiu.json", database=self.base)), 0)

    def test_a_gravacao_nao_deixa_arquivo_pela_metade(self) -> None:
        """S-25: o temporário é vizinho e o rename é atômico. Aqui o que se confere é que não
        sobrou temporário nenhum na pasta depois de gravar."""
        self._grava()
        self.assertEqual([p.name for p in self.raiz.glob("*.tmp")], [])
        self.assertTrue(self.arquivo.exists())

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
            lido = load_cache(self.arquivo, database=[self.base, outra])
        self.assertEqual(len(lido), 0)
        self.assertEqual(lido.missing({UMA}), {UMA}, "tudo volta a ser perguntado")

    def test_as_duas_bases_juntas_sao_uma_marca_so(self) -> None:
        outra = self.raiz / "outra.pgn"
        outra.write_text('[Event "y"]\n', encoding="utf-8")
        impressao = database_fingerprint([self.base, outra])
        self.assertEqual([item["name"] for item in impressao["files"]], ["base.pgn", "outra.pgn"])


class SerializacaoTests(unittest.TestCase):
    def test_a_candidata_volta_do_json_igual(self) -> None:
        original = PositionHit(move_number=24, side_to_move="b", headers={"White": "Karpov, A.", "Date": "1974"})
        voltou = PositionHit.from_dict(json.loads(json.dumps(original.to_dict())))
        self.assertEqual(voltou, original)
        self.assertEqual(voltou.key, original.key)

    def test_entrada_corrompida_vira_candidata_neutra_em_vez_de_excecao(self) -> None:
        self.assertEqual(PositionHit.from_dict("lixo").move_number, 1)
        self.assertEqual(CachedPosition.from_dict(None).count, 0)

    def test_a_contagem_ausente_no_json_e_o_tamanho_da_lista(self) -> None:
        guardada = CachedPosition.from_dict({"games": [{"move_number": 3, "side_to_move": "w"}]})
        self.assertEqual(guardada.count, 1)


class ComandoTests(unittest.TestCase):
    """O que o `cvoff-games` faz com o cache -- e é aqui que a promessa do módulo é cobrada."""

    PGN = """[Event "London"]
[Site "London ENG"]
[Date "1851.06.21"]
[White "Anderssen, Adolf"]
[Black "Kieseritzky, Lionel"]
[Result "1-0"]

1. e4 e5 2. f4 exf4 3. Bc4 Qh4+ 4. Kf1 1-0
"""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(self.PGN, encoding="utf-8")
        self.arquivo = self.raiz / "cache.json"

        tabuleiro = chess.Board()
        for lance in ("e4", "e5", "f4", "exf4", "Bc4", "Qh4+", "Kf1"):
            tabuleiro.push_san(lance)
        self.colocacao = tabuleiro.board_fen()
        self.ausente = "8/8/8/8/8/8/4K3/4k3"
        self.args = argparse.Namespace(no_cache=False, cache=self.arquivo, workers=1)

    def tearDown(self) -> None:
        self.pasta.cleanup()

    def test_a_segunda_execucao_nao_abre_a_base(self) -> None:
        """**A promessa inteira do S-84 em um teste.** Se alguém reintroduzir a varredura
        incondicional, ela falha aqui em vez de custar 30 minutos por execução.
        """
        alvos = {self.colocacao, self.ausente}
        primeiro = _positions_index(self.base, alvos, self.args)
        self.assertEqual(primeiro.counts[self.colocacao], 1)

        with mock.patch(
            "chess_diagram_ocr.cli.games.scan_by_positions",
            side_effect=AssertionError("abriu a base com tudo em cache"),
        ):
            segundo = _positions_index(self.base, alvos, self.args)
        self.assertEqual(segundo.counts, primeiro.counts)
        self.assertEqual(
            [p.headers for p in segundo.hits[self.colocacao]],
            [p.headers for p in primeiro.hits[self.colocacao]],
        )

    def test_a_posicao_nova_varre_so_ela(self) -> None:
        """Um livro novo custa as posições que ele trouxe, não o acervo inteiro."""
        _positions_index(self.base, {self.colocacao}, self.args)
        with mock.patch(
            "chess_diagram_ocr.cli.games.scan_by_positions", wraps=scan_by_positions
        ) as varredura:
            _positions_index(self.base, {self.colocacao, self.ausente}, self.args)
        pedidos = varredura.call_args.args[1]
        self.assertEqual(pedidos, {self.ausente}, "só a que faltava foi à base")

    def test_no_cache_pergunta_tudo_de_novo_e_nao_grava(self) -> None:
        """A saída para conferir o próprio cache: sem ela, um cache errado seria inauditável."""
        _positions_index(self.base, {self.colocacao}, self.args)
        marca = self.arquivo.stat().st_mtime_ns
        sem_cache = argparse.Namespace(no_cache=True, cache=self.arquivo, workers=1)
        indice = _positions_index(self.base, {self.colocacao}, sem_cache)
        self.assertEqual(indice.counts[self.colocacao], 1)
        self.assertEqual(self.arquivo.stat().st_mtime_ns, marca, "o arquivo não foi tocado")


if __name__ == "__main__":
    unittest.main()
