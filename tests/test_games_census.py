"""O censo da ambiguidade (S-89): ele não conserta nada, ele torna o estado visível.

O teste que mais importa aqui é o da inferência: o acervo inteiro foi preenchido antes de a
regra existir, e um censo que relatasse "zero a revisar" por não saber olhar seria pior que
nenhum censo -- zero por ignorância parece zero por limpeza.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.gallery import DiagramAnnotation, GalleryAnnotations
from chess_diagram_ocr.gallery_scan import GalleryEntry
from chess_diagram_ocr.games_cache import CachedPosition, PositionCache
from chess_diagram_ocr.games_census import bucket_for, census_book, census_total, inferred_rule
from chess_diagram_ocr.games_db import PositionHit


def _cache(**contagens: int) -> PositionCache:
    cache = PositionCache()
    for colocacao, quantas in contagens.items():
        partidas = tuple(
            PositionHit(move_number=10 + i, side_to_move="w", headers={"White": f"J{i}"})
            for i in range(min(quantas, 32))
        )
        cache.positions[colocacao] = CachedPosition(count=quantas, games=partidas)
    return cache


def _anotacoes(**por_diagrama: DiagramAnnotation) -> GalleryAnnotations:
    conjunto = GalleryAnnotations()
    for chave, anotacao in por_diagrama.items():
        pagina, _, diagrama = chave.partition("_")
        conjunto.set(int(pagina.lstrip("p")), int(diagrama), anotacao)
    return conjunto


class FaixasTests(unittest.TestCase):
    def test_as_faixas_seguem_as_fronteiras_das_regras(self) -> None:
        """O corte em 5 é o `max_games`, e o corte em 1 separa "não há escolha" de "há".
        Não são quantis: elas respondem *quanto trabalho humano sobra*."""
        self.assertEqual(bucket_for(1), "1")
        self.assertEqual(bucket_for(2), "2")
        self.assertEqual(bucket_for(5), "3-5")
        self.assertEqual(bucket_for(6), "6-20")
        self.assertEqual(bucket_for(101), ">100")
        self.assertEqual(bucket_for(10_000), ">100")


class InferenciaTests(unittest.TestCase):
    """A regra deduzida de quem foi preenchido antes de a regra existir."""

    def test_partida_unica_nao_teve_escolha_a_fazer(self) -> None:
        self.assertEqual(inferred_rule(DiagramAnnotation(filled_from="x"), 1), "unique")

    def test_duas_ou_mais_significa_desempate_por_data(self) -> None:
        """É dedução e não chute: aquele código preenchia só até `max_games`, e sempre com a
        primeira da lista ordenada por data."""
        self.assertEqual(inferred_rule(DiagramAnnotation(filled_from="x"), 3), "date")

    def test_a_marca_gravada_vence_a_deduzida(self) -> None:
        anotacao = DiagramAnnotation(filled_from="x", filled_rule="human")
        self.assertEqual(inferred_rule(anotacao, 3), "human")

    def test_quem_nao_foi_preenchido_nao_ganha_regra(self) -> None:
        """Um diagrama confirmado e vazio não tem procedência a deduzir -- e inventar uma o
        faria aparecer como trabalho feito."""
        self.assertEqual(inferred_rule(DiagramAnnotation(confirmed_from="40 partidas"), 40), "")


class CensoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entradas = [
            GalleryEntry(0, 0, "unica"),
            GalleryEntry(1, 0, "duas"),
            GalleryEntry(2, 0, "muitas"),
            GalleryEntry(3, 0, "ausente"),
        ]
        self.cache = _cache(unica=1, duas=2, muitas=147)

    def test_conta_alcance_e_distribuicao(self) -> None:
        placar = census_book("livro.pdf", self.entradas, self.cache, GalleryAnnotations())
        self.assertEqual((placar.diagrams, placar.matched), (4, 3))
        self.assertEqual(placar.buckets, {"1": 1, "2": 1, ">100": 1})
        self.assertEqual(placar.ambiguous, 2)

    def test_a_posicao_que_a_base_nao_conhece_nao_conta_como_casamento(self) -> None:
        cache = _cache(unica=1)
        cache.positions["ausente"] = CachedPosition(count=0)
        placar = census_book("livro.pdf", self.entradas, cache, GalleryAnnotations())
        self.assertEqual(placar.matched, 1, "perguntada e sem resposta não é casamento")

    def test_o_preenchido_as_cegas_vira_fila_de_revisao(self) -> None:
        """**O que o censo existe para produzir.** Sem ele, os 145 diagramas do acervo
        preenchidos por desempate são indistinguíveis de dado conferido."""
        anotacoes = _anotacoes(
            p0_0=DiagramAnnotation(move_number=10, filled_from="J0"),
            p1_0=DiagramAnnotation(move_number=10, filled_from="J0"),
        )
        placar = census_book("livro.pdf", self.entradas, self.cache, anotacoes)
        self.assertEqual(placar.by_rule, {"unique": 1, "date": 1})
        self.assertEqual(placar.to_review, 1)
        self.assertEqual(placar.inferred, 2, "os dois vieram de dedução, e o relatório diz isso")

    def test_a_escolha_humana_sai_da_fila_e_entra_no_placar(self) -> None:
        anotacoes = _anotacoes(
            p1_0=DiagramAnnotation(move_number=11, filled_from="J1", filled_rule="human", chosen_game="J1||||")
        )
        placar = census_book("livro.pdf", self.entradas, self.cache, anotacoes)
        self.assertEqual((placar.chosen, placar.to_review), (1, 0))
        self.assertEqual(placar.inferred, 0, "esta tinha marca gravada")

    def test_o_ambiguo_sem_resposta_e_o_que_a_lista_alcanca(self) -> None:
        placar = census_book("livro.pdf", self.entradas, self.cache, GalleryAnnotations())
        self.assertEqual(placar.pending, 2, "os dois ambíguos, nenhum resolvido")

    def test_escolher_a_partida_tira_o_diagrama_dos_pendentes(self) -> None:
        anotacoes = _anotacoes(p1_0=DiagramAnnotation(chosen_game="J1||||", filled_rule="human"))
        placar = census_book("livro.pdf", self.entradas, self.cache, anotacoes)
        self.assertEqual(placar.pending, 1, "sobrou o de 147 candidatas")

    def test_a_legenda_tambem_tira_do_pendente(self) -> None:
        anotacoes = _anotacoes(p1_0=DiagramAnnotation(move_number=11, filled_from="J1", filled_rule="caption"))
        placar = census_book("livro.pdf", self.entradas, self.cache, anotacoes)
        self.assertEqual(placar.pending, 1)
        self.assertEqual(placar.to_review, 0, "confirmada pela legenda não é palpite")

    def test_o_total_soma_os_livros_sem_perder_faixa(self) -> None:
        um = census_book("a.pdf", self.entradas, self.cache, GalleryAnnotations())
        outro = census_book("b.pdf", self.entradas, self.cache, GalleryAnnotations())
        total = census_total([um, outro])
        self.assertEqual(total.diagrams, 8)
        self.assertEqual(total.buckets, {"1": 2, "2": 2, ">100": 2})

    def test_livro_sem_casamento_nenhum_nao_quebra(self) -> None:
        placar = census_book("vazio.pdf", self.entradas, PositionCache(), GalleryAnnotations())
        self.assertEqual((placar.matched, placar.ambiguous, placar.pending), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
