"""O que a barra do índice diz e quanto anda, sem janela (S-532)."""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui.indice_da_base import (
    POR_MIL,
    Andamento,
    frase_de_fim,
    frase_de_progresso,
    perde_trabalho_ao_fechar,
)


class AndamentoTests(unittest.TestCase):
    def test_a_barra_do_conjunto_anda_pelo_arquivo_pulado(self) -> None:
        """Uma pasta em que só um arquivo mudou mostraria a barra parada em zero durante o único
        arquivo lido, se o pulado não contasse."""
        andamento = Andamento({"grande.pgn": 900, "pequena.pgn": 100})
        self.assertEqual(andamento.registrar("grande.pgn", 900, 900), 900)
        self.assertEqual(andamento.registrar("pequena.pgn", 50, 100), 950)
        self.assertEqual(andamento.registrar("pequena.pgn", 100, 100), POR_MIL)

    def test_o_aviso_traz_posicao_absoluta_e_nao_incremento(self) -> None:
        andamento = Andamento({"a.pgn": 1000})
        andamento.registrar("a.pgn", 300, 1000)
        self.assertEqual(andamento.registrar("a.pgn", 600, 1000), 600, "e não 900")

    def test_lido_alem_do_tamanho_nao_passa_de_mil(self) -> None:
        andamento = Andamento({"a.pgn": 10})
        self.assertEqual(andamento.registrar("a.pgn", 50, 10), POR_MIL)

    def test_arquivo_que_a_lista_nao_previa_entra_no_total(self) -> None:
        andamento = Andamento({"a.pgn": 100})
        self.assertEqual(andamento.registrar("b.pgn", 100, 100), 500)

    def test_sem_bases_a_barra_esta_cheia(self) -> None:
        self.assertEqual(Andamento({}).por_mil, POR_MIL)


class FrasesTests(unittest.TestCase):
    def test_a_frase_de_progresso_diz_arquivo_quanto_e_partidas(self) -> None:
        frase = frase_de_progresso("gigabase.pgn", 1_200_000_000, 8_600_000_000, 1234567)
        self.assertIn("gigabase.pgn", frase)
        self.assertIn("1,2 GB de 8,6 GB", frase)
        self.assertIn("1.234.567 partidas", frase)

    def test_o_arquivo_pulado_e_dito_como_tal(self) -> None:
        """Bytes cheios com zero partidas lidas é a assinatura do arquivo sem mudança."""
        self.assertIn("sem mudança", frase_de_progresso("a.pgn", 100, 100, 0))

    def test_a_frase_de_fim_diz_o_que_nao_foi_relido(self) -> None:
        frase = frase_de_fim(20_000_000, 1_500, 1, 3, 1, cancelado=False)
        self.assertIn("20.000.000 partidas", frase)
        self.assertIn("1.500 lidas de 1 arquivo(s)", frase)
        self.assertIn("3 arquivo(s) sem mudança", frase)
        self.assertIn("1 arquivo(s) que saíram", frase)

    def test_a_frase_de_fim_cancelada_diz_que_retoma_e_que_a_busca_nao_usa_o_indice(self) -> None:
        frase = frase_de_fim(3, 3, 1, 0, 0, cancelado=True)
        self.assertIn("interrompido", frase)
        self.assertIn("continua de onde parou", frase)
        self.assertIn("não usa o índice", frase)

    def test_fechar_a_janela_nao_perde_trabalho(self) -> None:
        """Cada arquivo é uma transação; dizer o contrário treinaria a pessoa a ignorar o aviso."""
        self.assertFalse(perde_trabalho_ao_fechar())
