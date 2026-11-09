"""O separador de glifo colado, e a regra que ele carrega: **sem árbitro, não mexer** (S-186).

O item chega com uma suspeita contra si mesmo, e ela é do projeto de origem: depois que as
classes de ligadura entraram no modelo, a vantagem do separador caiu de +0,3 para +0,1 de F1. O
modelo lê `fi` inteiro — e o que sobra para o separador é pouco.
"""

from __future__ import annotations

import unittest
from collections.abc import Sequence

import numpy as np

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.colados import (
    AUTO,
    GANHO_MINIMO,
    NUNCA,
    PADRAO,
    SEMPRE,
    partir,
    separar,
    vale,
)

ESCALA = 20


def _duas_colunas() -> np.ndarray:
    """Duas manchas de tinta com um vale entre elas: o colado horizontal, sintético."""
    binaria = np.zeros((40, 60), np.uint8)
    binaria[10:30, 8:20] = 255
    binaria[10:30, 30:44] = 255
    return binaria


def _arbitro(*, inteiro: float, partido: float):
    def julgar(caixas: Sequence[Caixa]) -> float:
        return partido if len(caixas) == 2 else inteiro

    return julgar


class ValeTests(unittest.TestCase):
    def test_o_vale_sai_entre_as_duas_manchas(self) -> None:
        achado = vale(_duas_colunas(), Caixa(6, 8, 46, 32))
        self.assertIsNotNone(achado)
        self.assertTrue(20 <= int(achado) <= 30, f"o corte saiu em {achado}")

    def test_tinta_uniforme_nao_tem_vale(self) -> None:
        """Sem isto, uma letra de traço uniforme produziria um "vale" em qualquer lugar."""
        cheia = np.full((40, 60), 255, np.uint8)
        self.assertIsNone(vale(cheia, Caixa(6, 8, 46, 32)))

    def test_o_minimo_colado_na_borda_nao_e_vale(self) -> None:
        """Cortar na ponta produz um pedaço vazio, e o pedaço vazio lê como qualquer coisa."""
        binaria = np.zeros((40, 60), np.uint8)
        binaria[10:30, 14:44] = 255  # tinta só à direita: o mínimo está na ponta esquerda
        achado = vale(binaria, Caixa(6, 8, 46, 32))
        if achado is not None:
            self.assertGreater(int(achado), 6 + int(40 * 0.25) - 1)

    def test_recorte_estreito_demais_nao_tem_perfil(self) -> None:
        self.assertIsNone(vale(_duas_colunas(), Caixa(10, 10, 12, 30)))


class ArbitroTests(unittest.TestCase):
    """A regra mais cara do projeto de origem: separar sem confirmar custou 2,3 pontos de F1."""

    CAIXA = Caixa(6, 8, 46, 32)

    def test_sem_arbitro_nenhum_corte_acontece(self) -> None:
        self.assertEqual([self.CAIXA], partir(self.CAIXA, 25, modo=AUTO))

    def test_o_arbitro_que_confirma_corta_em_dois_que_cobrem_o_inteiro(self) -> None:
        pedacos = partir(self.CAIXA, 25, arbitro=_arbitro(inteiro=0.5, partido=0.9))
        self.assertEqual(2, len(pedacos))
        self.assertEqual(self.CAIXA.x1, pedacos[0].x1)
        self.assertEqual(self.CAIXA.x2, pedacos[1].x2)
        self.assertEqual(pedacos[0].x2, pedacos[1].x1)

    def test_a_ligadura_conhecida_nao_e_cortada(self) -> None:
        """**O mecanismo que torna este item pequeno.**

        Se o modelo lê `fi` inteiro com confiança alta, os dois pedaços não superam o inteiro e o
        árbitro recusa — sem que ninguém precise listar ligaduras em lugar nenhum.
        """
        self.assertEqual([self.CAIXA], partir(self.CAIXA, 25, arbitro=_arbitro(inteiro=0.9, partido=0.5)))

    def test_o_ganho_precisa_superar_a_margem(self) -> None:
        raspando = _arbitro(inteiro=0.80, partido=0.80 + GANHO_MINIMO / 2)
        folgado = _arbitro(inteiro=0.80, partido=0.80 + GANHO_MINIMO * 2)
        self.assertEqual(1, len(partir(self.CAIXA, 25, arbitro=raspando)))
        self.assertEqual(2, len(partir(self.CAIXA, 25, arbitro=folgado)))

    def test_corte_fora_da_caixa_e_ignorado(self) -> None:
        for corte in (self.CAIXA.x1, self.CAIXA.x2, 0, 999):
            with self.subTest(corte=corte):
                self.assertEqual(
                    [self.CAIXA], partir(self.CAIXA, corte, arbitro=_arbitro(inteiro=0.1, partido=0.9))
                )


class ModoTests(unittest.TestCase):
    CAIXAS = (Caixa(6, 8, 46, 32),)

    def test_o_padrao_e_nunca_ate_a_tabela_dizer_o_contrario(self) -> None:
        """O oposto de herdar o padrão do projeto de origem, onde o ganho já estava evaporando."""
        self.assertEqual(NUNCA, PADRAO)

    def test_o_modo_nunca_deixa_o_colado_inteiro(self) -> None:
        saida = separar(
            _duas_colunas(),
            self.CAIXAS,
            escala=ESCALA,
            arbitro=_arbitro(inteiro=0.1, partido=0.9),
            modo=NUNCA,
        )
        self.assertEqual(list(self.CAIXAS), saida)

    def test_o_modo_sempre_corta_sem_perguntar(self) -> None:
        """Existe para a tabela ter a linha que mostra o preço de ignorar o árbitro."""
        saida = separar(_duas_colunas(), self.CAIXAS, escala=ESCALA, modo=SEMPRE)
        self.assertEqual(2, len(saida))

    def test_a_caixa_estreita_nao_e_candidata(self) -> None:
        estreita = (Caixa(10, 10, 10 + int(ESCALA), 30),)
        saida = separar(
            _duas_colunas(), estreita, escala=ESCALA, arbitro=_arbitro(inteiro=0.1, partido=0.9), modo=AUTO
        )
        self.assertEqual(list(estreita), saida)

    def test_escala_zero_nao_mexe_em_nada(self) -> None:
        self.assertEqual(
            list(self.CAIXAS), separar(_duas_colunas(), self.CAIXAS, escala=0, modo=SEMPRE)
        )

    def test_modo_desconhecido_levanta(self) -> None:
        with self.assertRaises(ValueError):
            separar(_duas_colunas(), self.CAIXAS, escala=ESCALA, modo="talvez")


class UmArbitroSoTests(unittest.TestCase):
    """O árbitro que se mede é o que roda (S-852).

    Ele estava em três cópias -- o leitor de página e os dois CLIs que mediram o separador e o corte
    de linha --, com um comentário justificando a cópia. Uma edição numa delas separava o que foi
    medido do que está ligado, sem teste nenhum acusar.
    """

    def test_os_tres_chamadores_usam_o_mesmo_arbitro(self) -> None:
        from chess_diagram_ocr.cli import texto_colados, texto_duas_linhas
        from chess_diagram_ocr.text import colados, leitor

        for chamador in (leitor, texto_colados, texto_duas_linhas):
            with self.subTest(chamador=chamador.__name__):
                self.assertIs(colados.arbitro_de_confianca, chamador.arbitro_de_confianca)

    def test_o_arbitro_e_a_confianca_media_dos_recortes_que_tem_tinta(self) -> None:
        from chess_diagram_ocr.text.colados import arbitro_de_confianca

        class Classificador:
            def classificar(self, recortes: Sequence[np.ndarray]) -> list[tuple[str, float]]:
                return [("a", float(r.shape[1]) / 10) for r in recortes]

        julgar = arbitro_de_confianca(np.zeros((40, 60), np.uint8), Classificador())
        self.assertAlmostEqual(0.3, julgar([Caixa(0, 0, 2, 10), Caixa(0, 0, 4, 10), Caixa(5, 5, 5, 5)]))
        self.assertEqual(0.0, julgar([]))


class ValeNosDoisEixosTests(unittest.TestCase):
    """Os gêmeos `colados` e `duas_linhas` acham o vale pela mesma conta, cada um no seu eixo (S-852)."""

    def test_o_vale_de_linha_e_o_vale_de_coluna_da_figura_transposta(self) -> None:
        from chess_diagram_ocr.text import duas_linhas

        binaria = _duas_colunas()
        de_coluna = vale(binaria, Caixa(6, 8, 46, 32))
        de_linha = duas_linhas.vale(np.ascontiguousarray(binaria.T), Caixa(8, 6, 32, 46))
        self.assertIsNotNone(de_coluna)
        self.assertEqual(de_coluna, de_linha)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
