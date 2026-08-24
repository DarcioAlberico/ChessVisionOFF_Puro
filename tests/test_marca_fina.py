"""Apóstrofo ou vírgula, decidido pela posição na linha (S-211).

Puro: nenhum destes testes carrega modelo nem abre PDF. O que eles travam é a decisão e as **duas
guardas** -- a de posição, que promove, e a de altura, que impede a promoção de virar troca de um
erro por outro.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text import marca_fina as mf
from chess_diagram_ocr.text.boxes import Caixa

I2C = {0: ",", 1: "'", 2: "a", 3: ".", 4: "l"}
TOPO, BASE = 100.0, 122.0
"""Uma linha de 22 px: as letras vão de y=100 a y=122."""


def _probs(n: int) -> np.ndarray:
    """Matriz em que a vírgula ganha e o apóstrofo é o segundo."""
    m = np.zeros((n, len(I2C)), dtype=np.float32)
    m[:, 0] = 0.90
    m[:, 1] = 0.05
    return m


class GeometriaTests(unittest.TestCase):
    def test_a_base_e_a_mediana_e_nao_o_maximo(self) -> None:
        """Um `g` desce abaixo da linha de base; o máximo o tomaria por ela."""
        caixas = [Caixa(0, 100, 8, 122), Caixa(10, 100, 18, 122), Caixa(20, 106, 28, 130)]
        self.assertEqual(mf.referencia_da_linha(caixas), (100.0, 122.0))

    def test_sem_caixas_nao_estoura(self) -> None:
        self.assertEqual(mf.referencia_da_linha([]), (0.0, 0.0))

    def test_a_posicao_vai_de_zero_no_topo_a_um_na_base(self) -> None:
        self.assertAlmostEqual(mf.posicao_na_linha(100, TOPO, BASE), 0.0)
        self.assertAlmostEqual(mf.posicao_na_linha(122, TOPO, BASE), 1.0)

    def test_linha_degenerada_devolve_negativo_e_nao_zero(self) -> None:
        """Zero dispararia a comparação com o corte; negativo nunca dispara."""
        self.assertLess(mf.posicao_na_linha(100, 100, 100), 0)
        self.assertFalse(mf.e_marca_alta(100, 100, 100))


class DuasGuardasTests(unittest.TestCase):
    """A promoção exige **as duas**: no alto, e pequena."""

    def test_marca_pequena_no_alto_e_apostrofo(self) -> None:
        self.assertTrue(mf.e_marca_alta(100, TOPO, BASE, altura=7))

    def test_marca_pequena_na_base_nao_e(self) -> None:
        self.assertFalse(mf.e_marca_alta(118, TOPO, BASE, altura=7))

    def test_letra_alta_no_topo_nao_e_marca(self) -> None:
        """`Qualquer` saía `Qua'quer` sem esta guarda: o `l` também começa no topo da linha."""
        self.assertFalse(mf.e_marca_alta(100, TOPO, BASE, altura=21))

    def test_sem_altura_a_segunda_guarda_nao_opina(self) -> None:
        self.assertTrue(mf.e_marca_alta(100, TOPO, BASE))

    def test_os_dois_limiares_sao_lidos_na_chamada(self) -> None:
        """O defeito de assinatura de `caixa_alta`, que aqui não pode voltar."""
        pos, teto = mf.CORTE_NA_LINHA, mf.ALTURA_MAXIMA
        try:
            mf.CORTE_NA_LINHA = 0.01
            self.assertFalse(mf.e_marca_alta(101, TOPO, BASE, altura=7))
            mf.CORTE_NA_LINHA = pos
            mf.ALTURA_MAXIMA = 0.10
            self.assertFalse(mf.e_marca_alta(100, TOPO, BASE, altura=7))
        finally:
            mf.CORTE_NA_LINHA, mf.ALTURA_MAXIMA = pos, teto


class CorrigirTests(unittest.TestCase):
    def test_a_virgula_no_alto_vira_apostrofo(self) -> None:
        """`Black,s` -> `Black's`, que é o caso que abriu o item."""
        caixas = [Caixa(0, 100, 8, 122), Caixa(10, 100, 14, 107), Caixa(16, 100, 24, 122)]
        lidos = [("a", 0.99), (",", 0.90), ("a", 0.99)]
        saida = mf.corrigir(lidos, _probs(3), caixas, I2C)
        self.assertEqual([c for c, _ in saida], ["a", "'", "a"])

    def test_a_virgula_na_base_fica_virgula(self) -> None:
        caixas = [Caixa(0, 100, 8, 122), Caixa(10, 116, 14, 126)]
        saida = mf.corrigir([("a", 0.99), (",", 0.90)], _probs(2), caixas, I2C)
        self.assertEqual([c for c, _ in saida], ["a", ","])

    def test_a_confianca_e_a_da_classe_escolhida(self) -> None:
        """Manter os 0,90 da vírgula recusada seria confiança inventada."""
        caixas = [Caixa(0, 100, 8, 122), Caixa(10, 100, 14, 107)]
        _, conf = mf.corrigir([("a", 0.99), (",", 0.90)], _probs(2), caixas, I2C)[1]
        self.assertAlmostEqual(conf, 0.05, places=3)

    def test_o_que_nao_e_marca_baixa_passa_intacto(self) -> None:
        caixas = [Caixa(0, 100, 8, 107)]
        self.assertEqual(mf.corrigir([("a", 0.9)], _probs(1), caixas, I2C)[0][0], "a")

    def test_sem_a_classe_do_apostrofo_devolve_intacto(self) -> None:
        """Sem `'` no modelo não há para onde promover -- e inventar outro caractere seria pior."""
        caixas = [Caixa(0, 100, 8, 122), Caixa(10, 100, 14, 107)]
        sem = {0: ",", 2: "a"}
        saida = mf.corrigir([("a", 0.99), (",", 0.90)], _probs(2), caixas, sem)
        self.assertEqual([c for c, _ in saida], ["a", ","])

    def test_lista_vazia_devolve_vazia(self) -> None:
        self.assertEqual(mf.corrigir([], np.empty((0, 5), np.float32), [], I2C), [])

    def test_menos_caixas_que_lidos_nao_estoura(self) -> None:
        saida = mf.corrigir([("a", 0.9), (",", 0.9)], _probs(2), [Caixa(0, 100, 8, 122)], I2C)
        self.assertEqual([c for c, _ in saida], ["a", ","])

    def test_toda_marca_de_BAIXAS_e_um_caractere(self) -> None:
        self.assertTrue(all(len(c) == 1 for c in mf.BAIXAS))
        self.assertEqual(len(mf.ALTA), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
