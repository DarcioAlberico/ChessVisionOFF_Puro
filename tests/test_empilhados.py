"""O glifo de dois contornos empilhados: `:`, `;` e `=` (S-211).

Puro: nenhum destes testes carrega modelo nem abre PDF. O que eles travam é a fusão, a guarda que
mantém o filete fora, e a correção de proporção -- que é a metade do item que quase passou
despercebida, porque fundir sozinho fazia metade dos `=` sair `:`.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text import empilhados as em
from chess_diagram_ocr.text.boxes import Caixa

ESCALA = 30
I2C = {0: ".", 1: ":", 2: ";", 3: "=", 4: "a"}


def _probs(indice: int, n: int = 1) -> np.ndarray:
    m = np.zeros((n, len(I2C)), dtype=np.float32)
    m[:, indice] = 0.9
    return m


class UnirTests(unittest.TestCase):
    def test_dois_pontos_empilhados_viram_um_box(self) -> None:
        acima, abaixo = Caixa(100, 100, 106, 106), Caixa(100, 114, 106, 120)
        saida = em.unir([acima, abaixo], escala=ESCALA)
        self.assertEqual(len(saida), 1)
        self.assertEqual((saida[0].x1, saida[0].y1, saida[0].x2, saida[0].y2), (100, 100, 106, 120))

    def test_a_letra_inteira_nao_e_tocada(self) -> None:
        letra = Caixa(120, 100, 140, 130)
        self.assertEqual(em.unir([letra], escala=ESCALA), [letra])

    def test_o_vao_grande_nao_funde(self) -> None:
        """**É o guarda contra o merge atravessar a linha**, a cicatriz da S-185."""
        acima, abaixo = Caixa(100, 100, 106, 106), Caixa(100, 160, 106, 166)
        self.assertEqual(len(em.unir([acima, abaixo], escala=ESCALA)), 2)

    def test_sem_sobreposicao_em_x_nao_funde(self) -> None:
        acima, abaixo = Caixa(100, 100, 106, 106), Caixa(200, 114, 206, 120)
        self.assertEqual(len(em.unir([acima, abaixo], escala=ESCALA)), 2)

    def test_a_uniao_alta_demais_nao_e_glifo(self) -> None:
        acima, abaixo = Caixa(100, 100, 106, 106), Caixa(100, 130, 106, 145)
        self.assertEqual(len(em.unir([acima, abaixo], escala=ESCALA)), 2)

    def test_cada_metade_entra_em_um_par_so(self) -> None:
        """Um `:` tem duas partes, não três: o terceiro ponto não pode ser absorvido junto."""
        tres = [Caixa(100, 100, 106, 106), Caixa(100, 112, 106, 118), Caixa(100, 124, 106, 130)]
        self.assertEqual(len(em.unir(tres, escala=ESCALA)), 2)

    def test_a_ordem_de_entrada_e_preservada(self) -> None:
        """Quem ordena é `linhas.ordem_em_faixa`; reordenar aqui esconderia um defeito dele."""
        letra = Caixa(10, 100, 30, 130)
        acima, abaixo = Caixa(100, 100, 106, 106), Caixa(100, 114, 106, 120)
        outra = Caixa(200, 100, 220, 130)
        saida = em.unir([letra, acima, abaixo, outra], escala=ESCALA)
        self.assertEqual([c.x1 for c in saida], [10, 100, 200])

    def test_escala_zero_devolve_intacto(self) -> None:
        caixas = [Caixa(100, 100, 106, 106), Caixa(100, 114, 106, 120)]
        self.assertEqual(em.unir(caixas, escala=0), caixas)


class BarraTests(unittest.TestCase):
    """A régua de proporção da S-185 não pode ser desfeita por acidente."""

    def test_a_barra_solta_nao_entra_no_texto(self) -> None:
        """Sozinha ela é filete ou sublinhado, e continua fora -- é a guarda inteira do item."""
        letra = Caixa(120, 100, 140, 130)
        barra = Caixa(200, 100, 224, 103)
        self.assertEqual(em.unir([letra], escala=ESCALA, extras=[barra]), [letra])

    def test_duas_barras_empilhadas_entram_como_uma(self) -> None:
        letra = Caixa(120, 100, 140, 130)
        barras = [Caixa(200, 100, 224, 103), Caixa(200, 110, 224, 113)]
        saida = em.unir([letra], escala=ESCALA, extras=barras)
        self.assertEqual(len(saida), 2)
        fundida = saida[-1]
        self.assertEqual((fundida.x1, fundida.y1, fundida.x2, fundida.y2), (200, 100, 224, 113))

    def test_barras_devolve_lista_vazia_sem_imagem(self) -> None:
        self.assertEqual(em.barras(np.zeros((0, 0), np.uint8), escala=ESCALA), [])

    def test_barras_devolve_lista_vazia_sem_escala(self) -> None:
        self.assertEqual(em.barras(np.zeros((40, 40), np.uint8), escala=0), [])


class ProporcaoTests(unittest.TestCase):
    """A metade do item que quase passou: fundir não basta, porque o resize apaga a proporção."""

    def test_o_box_largo_lido_como_dois_pontos_vira_igual(self) -> None:
        """Medido: `=` fica em 2,4-2,7 de largura sobre altura, e `:` em 0,24-0,25."""
        caixa = Caixa(200, 100, 224, 110)  # 24 x 10 -> 2,4
        saida = em.corrigir([(":", 0.9)], _probs(1), [caixa], I2C)
        self.assertEqual(saida[0][0], "=")

    def test_o_box_alto_lido_como_igual_vira_dois_pontos(self) -> None:
        caixa = Caixa(200, 100, 206, 124)  # 6 x 24 -> 0,25
        self.assertEqual(em.corrigir([("=", 0.9)], _probs(3), [caixa], I2C)[0][0], ":")

    def test_o_ponto_e_virgula_alto_nao_e_tocado(self) -> None:
        caixa = Caixa(200, 100, 206, 124)
        self.assertEqual(em.corrigir([(";", 0.9)], _probs(2), [caixa], I2C)[0][0], ";")

    def test_o_que_nao_e_dos_tres_passa_intacto(self) -> None:
        caixa = Caixa(200, 100, 224, 110)
        self.assertEqual(em.corrigir([("a", 0.9)], _probs(4), [caixa], I2C)[0][0], "a")

    def test_a_confianca_e_a_da_classe_escolhida(self) -> None:
        caixa = Caixa(200, 100, 224, 110)
        probs = np.zeros((1, len(I2C)), np.float32)
        probs[0, 1] = 0.90  # ':'
        probs[0, 3] = 0.07  # '='
        _, conf = em.corrigir([(":", 0.90)], probs, [caixa], I2C)[0]
        self.assertAlmostEqual(conf, 0.07, places=3)

    def test_sem_as_duas_classes_devolve_intacto(self) -> None:
        caixa = Caixa(200, 100, 224, 110)
        self.assertEqual(em.corrigir([(":", 0.9)], _probs(1), [caixa], {1: ":"})[0][0], ":")

    def test_o_corte_e_lido_na_chamada(self) -> None:
        """O defeito de assinatura de `caixa_alta`, que não pode voltar em módulo nenhum."""
        caixa = Caixa(200, 100, 224, 110)
        original = em.PROPORCAO_DE_IGUAL
        try:
            em.PROPORCAO_DE_IGUAL = 9.0
            self.assertEqual(em.corrigir([(":", 0.9)], _probs(1), [caixa], I2C)[0][0], ":")
        finally:
            em.PROPORCAO_DE_IGUAL = original

    def test_lista_vazia_devolve_vazia(self) -> None:
        self.assertEqual(em.corrigir([], np.empty((0, 5), np.float32), [], I2C), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
