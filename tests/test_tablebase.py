"""As tablebases Syzygy: quando perguntar, o que dizer, e o que acontece sem elas (S-538).

**Não há um `.rtbw` nesta máquina, e não haverá numa suíte.** O menor conjunto útil (cinco peças)
passa de 1 GB, e o `python-chess` não embarca tabela nenhuma no wheel -- foi conferido. Então o que
se mede aqui é o que **é** mensurável sem os arquivos, e são as três coisas que decidem:

1. a decisão pura -- quando vale perguntar, o que cada WDL quer dizer, como a barra reage;
2. a degradação **contra o `chess.syzygy` de verdade**, apontado para uma pasta vazia: é o caso da
   máquina de quem não baixou nada, e ele tem de responder "não sei" em vez de levantar;
3. o caminho da resposta até a tela, com uma tabela **injetada** -- é o que prova que um WDL de
   `+2` vira a frase certa e move a barra, sem depender de o arquivo existir.

O que fica declarado como não medido: nenhuma consulta a uma tabela Syzygy real. O `Finais` aceita
`tabela=` por injeção justamente para que essa dívida seja a única.
"""

from __future__ import annotations

import unittest
from typing import Any

import chess
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import tablebase
from chess_diagram_ocr.ui import finais


class QuandoPerguntarTests(unittest.TestCase):
    """A ida ao disco custa, e a sala passa o tempo em posições de vinte peças."""

    def test_sem_pasta_nunca_se_pergunta(self) -> None:
        self.assertFalse(finais.deve_consultar(3, tem_pasta=False))

    def test_ate_sete_pecas_pergunta_e_acima_nao(self) -> None:
        """Sete porque as tabelas de sete peças existem; acima disso não há arquivo que possa
        estar lá, e perguntar seria pagar a ida ao disco por nada."""
        self.assertTrue(finais.deve_consultar(3, tem_pasta=True))
        self.assertTrue(finais.deve_consultar(7, tem_pasta=True))
        self.assertFalse(finais.deve_consultar(8, tem_pasta=True))
        self.assertFalse(finais.deve_consultar(32, tem_pasta=True))

    def test_a_contagem_e_a_do_tabuleiro_com_os_reis(self) -> None:
        """`KRvK` são três peças, que é como Syzygy nomeia os arquivos."""
        board = chess.Board("8/8/8/8/8/8/4K1k1/4R3 b - - 0 1")
        self.assertEqual(3, chess.popcount(board.occupied))
        self.assertTrue(finais.deve_consultar(chess.popcount(board.occupied), tem_pasta=True))

    def test_a_tabela_ganha_do_motor_so_quando_responde(self) -> None:
        """`None` é o caso de quem tem só os cinco peças e chegou a uma posição de seis: ali a
        estimativa do motor volta a ser a melhor resposta que existe."""
        self.assertTrue(finais.vence_o_motor(0))
        self.assertTrue(finais.vence_o_motor(-2))
        self.assertFalse(finais.vence_o_motor(None))


class FraseTests(unittest.TestCase):
    """O resultado exato, e o que ele **não** diz."""

    def test_tabuas_e_tabuas_e_nao_uma_avaliacao(self) -> None:
        self.assertEqual("Tábuas (tabela de finais).", finais.frase_do_resultado(0))

    def test_a_frase_nomeia_a_cor_e_nao_diz_voce(self) -> None:
        """O WDL é do lado que está no lance; "vitória" sozinho ao lado de um tabuleiro com as
        pretas a jogar seria lido como vitória das brancas por qualquer um.

        E o sujeito é **quem joga**, não quem ganha: `-2` com as pretas na vez é "derrota das
        pretas", e não "vitória das brancas" -- inverter o sinal antes de escrever seria uma conta
        a mais no caminho entre o arquivo e a tela."""
        self.assertIn("vitória das brancas", finais.frase_do_resultado(2, brancas_jogam=True))
        self.assertIn("vitória das pretas", finais.frase_do_resultado(2, brancas_jogam=False))
        self.assertIn("derrota das pretas", finais.frase_do_resultado(-2, brancas_jogam=False))

    def test_a_zeragem_aparece_com_o_nome_que_ela_tem(self) -> None:
        """**Não é "mate em N"**: DTZ é a distância até a próxima captura ou lance de peão, e o
        arquivo de Syzygy não contém distância até o mate. Chamá-la assim poria na tela um número
        que a tabela não guarda."""
        frase = finais.frase_do_resultado(2, 14)
        self.assertIn("zeragem em 14", frase)
        self.assertNotIn("mate", frase.casefold())

    def test_a_vitoria_que_os_cinquenta_lances_anulam_tem_nome_proprio(self) -> None:
        """`±1` é o "cursed win": chamá-lo de vitória mentiria sobre o resultado da partida, e
        chamá-lo de tábuas esconderia que o final é ganho."""
        self.assertIn("teórica", finais.frase_do_resultado(1))
        self.assertIn("teórica", finais.frase_do_resultado(-1))

    def test_sem_resposta_nao_ha_frase(self) -> None:
        self.assertEqual("", finais.frase_do_resultado(None))

    def test_a_barra_vai_para_onde_o_resultado_manda(self) -> None:
        """Uma tabela dizendo "tábuas" com a barra ainda em +3,45 é a tela discordando de si."""
        self.assertEqual(1000, finais.centipeoes_de(2, brancas_jogam=True))
        self.assertEqual(-1000, finais.centipeoes_de(2, brancas_jogam=False))
        self.assertEqual(0, finais.centipeoes_de(0))
        self.assertIsNone(finais.centipeoes_de(None))

    def test_a_vitoria_teorica_vale_zero_na_barra(self) -> None:
        """No placar da partida ela é tábua, e é o placar que a barra mostra. A frase ao lado é
        quem diz que o final é ganho."""
        self.assertEqual(0, finais.centipeoes_de(1, brancas_jogam=True))


class _TabelaDeMentira:
    """Uma tabela que responde o que o teste mandar. Ver o cabeçalho: `.rtbw` não cabe na suíte."""

    def __init__(self, wdl: Any, dtz: Any = None) -> None:
        self._wdl = wdl
        self._dtz = dtz
        self.perguntas: list[str] = []
        self.fechada = False

    def get_wdl(self, board: chess.Board) -> Any:
        self.perguntas.append(board.fen())
        if isinstance(self._wdl, Exception):
            raise self._wdl
        return self._wdl

    def get_dtz(self, _board: chess.Board) -> Any:
        if isinstance(self._dtz, Exception):
            raise self._dtz
        return self._dtz

    def close(self) -> None:
        self.fechada = True


class LeitorTests(unittest.TestCase):
    """`tablebase.Finais`: abrir, perguntar e degradar."""

    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)

    def test_sem_pasta_configurada_nao_ha_leitor(self) -> None:
        """Vazio é "não usar tablebase", e nada no programa muda (S-33 aplicada aqui)."""
        self.assertIsNone(tablebase.abrir(""))
        self.assertIsNone(tablebase.abrir(None))
        self.assertIsNone(tablebase.abrir('  "" '))

    def test_a_pasta_que_nao_existe_nao_levanta_e_nao_responde(self) -> None:
        leitor = tablebase.abrir(str(self.pasta / "nao-existe"))
        assert leitor is not None
        self.assertFalse(leitor.abrir())
        self.assertIsNone(leitor.consultar(chess.Board("8/8/8/8/8/8/4K1k1/4R3 b - - 0 1")))

    def test_a_pasta_vazia_abre_e_responde_que_nao_sabe(self) -> None:
        """**É o `chess.syzygy` de verdade**, apontado para uma pasta sem arquivo nenhum: é a
        máquina de quem configurou a pasta e não baixou as tabelas, e ali a resposta certa é
        "não sei" -- o painel volta a mostrar o que o motor disse."""
        leitor = tablebase.abrir(str(self.pasta))
        assert leitor is not None
        self.addCleanup(leitor.close)
        self.assertTrue(leitor.abrir())
        self.assertIsNone(leitor.consultar(chess.Board("8/8/8/8/8/8/4K1k1/4R3 b - - 0 1")))

    def test_com_tabela_a_resposta_chega_inteira(self) -> None:
        tabela = _TabelaDeMentira(2, -14)
        leitor = tablebase.Finais(self.pasta, tabela=tabela)
        achado = leitor.consultar(chess.Board("8/8/8/8/8/8/4K1k1/4R3 b - - 0 1"))
        assert achado is not None
        self.assertEqual(2, achado.wdl)
        self.assertEqual(-14, achado.dtz)
        self.assertEqual(1, len(tabela.perguntas))

    def test_quem_baixou_so_as_WDL_nao_perde_a_resposta(self) -> None:
        """As tabelas de DTZ são o dobro do tamanho, e há quem baixe só metade."""
        leitor = tablebase.Finais(self.pasta, tabela=_TabelaDeMentira(0, KeyError("sem dtz")))
        achado = leitor.consultar(chess.Board("8/8/8/8/8/8/4K1k1/4R3 b - - 0 1"))
        assert achado is not None
        self.assertEqual(0, achado.wdl)
        self.assertIsNone(achado.dtz)

    def test_o_direito_de_roque_e_nao_sei_e_nao_erro(self) -> None:
        """Syzygy não representa roque -- as tabelas são geradas sobre posições sem ele --, e
        `probe_wdl` levanta `ValueError` ali. A resposta certa é "não sei"."""
        tabela = _TabelaDeMentira(2)
        leitor = tablebase.Finais(self.pasta, tabela=tabela)
        com_roque = chess.Board("4k2r/8/8/8/8/8/8/4K3 b k - 0 1")
        self.assertIsNone(leitor.consultar(com_roque))
        self.assertEqual([], tabela.perguntas, "nem chegou a perguntar")

    def test_a_falha_da_tabela_vira_nao_sei(self) -> None:
        """Arquivo truncado, disco de rede que sumiu: nenhum é motivo para a sala parar."""
        leitor = tablebase.Finais(self.pasta, tabela=_TabelaDeMentira(OSError("disco")))
        self.assertIsNone(leitor.consultar(chess.Board("8/8/8/8/8/8/4K1k1/4R3 b - - 0 1")))

    def test_o_leitor_fecha_a_tabela(self) -> None:
        tabela = _TabelaDeMentira(0)
        with tablebase.Finais(self.pasta, tabela=tabela) as leitor:
            self.assertTrue(leitor.aberta)
        self.assertTrue(tabela.fechada)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
