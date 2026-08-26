"""A base de partidas perguntada da sala de estudo (S-287).

**Os três estados são o item**, e o que eles separam custa caro confundir: "a base não tem esta
posição" e "ninguém perguntou à base sobre esta posição" são frases diferentes, e colapsá-las daria
um número sobre uma pergunta que não foi feita -- que é a forma de número enganoso que a S-135
registra neste projeto.

A loja entra por `Protocol`, então nada aqui abre um SQLite nem lê um `.pgn`.
"""

from __future__ import annotations

import unittest
from collections.abc import Iterable
from pathlib import Path

from chess_diagram_ocr import estudo_partidas
from chess_diagram_ocr.games_cache import CachedPosition
from chess_diagram_ocr.games_db import PositionHit

ITALIANA = "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"
BASES = (Path("pgn_database/gigabase.pgn"),)


class _Loja:
    """Três linhas, e é tudo o que `consultar` usa de `games_cache.PositionStore`."""

    def __init__(self, guardadas: dict[str, CachedPosition]) -> None:
        self.guardadas = guardadas

    def missing(self, targets: Iterable[str]) -> set[str]:
        return {alvo for alvo in targets if alvo not in self.guardadas}

    def get(self, placement: str) -> CachedPosition:
        return self.guardadas.get(placement, CachedPosition())


def _hit(branco: str, preto: str, lance: int = 12) -> PositionHit:
    return PositionHit(move_number=lance, side_to_move="w", headers={"White": branco, "Black": preto})


class ConsultarTests(unittest.TestCase):
    def test_sem_base_no_disco_diz_onde_por_os_pgn(self) -> None:
        """E diz que eles não saem da máquina: é a promessa da S-73, e ela vale ser repetida onde
        alguém está prestes a apontar o programa para a própria coleção."""
        resposta = estudo_partidas.consultar(_Loja({}), ITALIANA, bases=())
        self.assertEqual(resposta.estado, estudo_partidas.NAO_HA_BASE)
        self.assertIn("pgn_database/", resposta.frase)
        self.assertIn("não saem da sua máquina", resposta.frase)

    def test_sem_loja_aberta_e_o_mesmo_que_nao_haver_base(self) -> None:
        self.assertEqual(
            estudo_partidas.consultar(None, ITALIANA, bases=BASES).estado, estudo_partidas.NAO_HA_BASE
        )

    def test_posicao_nunca_perguntada_diz_isso_e_ensina_o_comando(self) -> None:
        """**O estado que não pode virar "nenhuma partida".** O cache só conhece o que já foi
        perguntado, e a posição depois de três lances de análise nunca foi."""
        resposta = estudo_partidas.consultar(_Loja({}), ITALIANA, bases=BASES)
        self.assertEqual(resposta.estado, estudo_partidas.NAO_PERGUNTADA)
        self.assertIn("cvoff-games", resposta.frase)
        self.assertFalse(resposta.achou)

    def test_perguntada_e_sem_partida_e_uma_resposta(self) -> None:
        """`count=0` é resposta, e não ausência: a base foi lida e não conhece a posição."""
        resposta = estudo_partidas.consultar(
            _Loja({ITALIANA: CachedPosition(count=0)}), ITALIANA, bases=BASES
        )
        self.assertEqual(resposta.estado, estudo_partidas.SEM_PARTIDA)
        self.assertIn("Nenhuma partida", resposta.frase)

    def test_com_partida_devolve_as_guardadas(self) -> None:
        guardada = CachedPosition(count=2, games=(_hit("Capablanca", "Alekhine"), _hit("Tal", "Botvinnik")))
        resposta = estudo_partidas.consultar(_Loja({ITALIANA: guardada}), ITALIANA, bases=BASES)
        self.assertTrue(resposta.achou)
        self.assertEqual(len(resposta.partidas), 2)
        self.assertEqual(resposta.total, 2)
        self.assertFalse(resposta.truncada)
        self.assertIn("Capablanca", resposta.partidas[0].label)

    def test_lista_menor_que_a_contagem_diz_que_e_menor(self) -> None:
        """Mostrar dez de duzentas sem avisar é o número enganoso que a S-135 registra."""
        guardada = CachedPosition(count=214, games=(_hit("Capablanca", "Alekhine"),))
        resposta = estudo_partidas.consultar(_Loja({ITALIANA: guardada}), ITALIANA, bases=BASES)
        self.assertTrue(resposta.truncada)
        self.assertIn("214", resposta.frase)
        self.assertIn("1 guardadas", resposta.frase)

    def test_a_fen_inteira_e_cortada_no_campo_de_pecas(self) -> None:
        """O cache é indexado por **colocação**, e a FEN do estudo traz vez, roque e contadores."""
        guardada = CachedPosition(count=1, games=(_hit("A", "B"),))
        resposta = estudo_partidas.consultar(
            _Loja({ITALIANA: guardada}), f"{ITALIANA} b KQkq - 4 4", bases=BASES
        )
        self.assertTrue(resposta.achou)

    def test_posicao_vazia_nao_e_pergunta(self) -> None:
        self.assertEqual(
            estudo_partidas.consultar(_Loja({}), "", bases=BASES).estado, estudo_partidas.NAO_HA_BASE
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
