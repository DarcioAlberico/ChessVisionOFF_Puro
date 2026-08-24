"""A caixa decidida pela altura, e não pela forma (S-211).

O módulo é puro: nenhum destes testes carrega modelo, abre PDF ou toca `tkinter`. O que eles
travam é a decisão -- e, principalmente, o **defeito de assinatura** que quase fez a medição sair
sem sentido: um `corte` amarrado como valor padrão na definição não acompanha quem muda a
constante, e uma varredura de sete limiares sai com sete linhas idênticas.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text import caixa_alta as ca

I2C = {0: "s", 1: "S", 2: "a", 3: "A", 4: "o", 5: "O", 6: "fi", 7: "1"}


def _probs(indice: int, valor: float = 0.96, n: int = 1) -> np.ndarray:
    """Uma matriz em que a classe `indice` vence em todas as linhas."""
    m = np.full((n, len(I2C)), (1.0 - valor) / (len(I2C) - 1), dtype=np.float32)
    m[:, indice] = valor
    return m


class ParesTests(unittest.TestCase):
    def test_so_as_letras_de_mesma_forma_formam_par(self) -> None:
        pares = ca.pares_de_caixa(I2C)
        self.assertEqual(pares, {0: 1, 1: 0, 4: 5, 5: 4}, "só s/S e o/O são ambíguos aqui")

    def test_a_letra_que_muda_de_forma_nao_entra(self) -> None:
        """`a` e `A` são desenhos diferentes -- o modelo os separa, e a altura não deve opinar."""
        self.assertNotIn(2, ca.pares_de_caixa(I2C))

    def test_a_ligadura_nunca_entra(self) -> None:
        """A altura de `fi` não diz nada sobre caixa: são dois caracteres num box."""
        self.assertNotIn(6, ca.pares_de_caixa(I2C))

    def test_o_par_incompleto_fica_de_fora(self) -> None:
        """Meia-regra é pior que regra nenhuma: sem a contraparte, não há o que escolher."""
        self.assertEqual(ca.pares_de_caixa({0: "s", 2: "a"}), {})

    def test_toda_letra_de_AMBIGUAS_e_minuscula_e_unica(self) -> None:
        self.assertEqual(ca.AMBIGUAS, "".join(sorted(set(ca.AMBIGUAS))))
        self.assertTrue(ca.AMBIGUAS.islower())


class XHeightTests(unittest.TestCase):
    def test_a_mediana_ignora_o_box_alto_solto(self) -> None:
        """Um parêntese alto no meio da linha move a média e não move a mediana."""
        self.assertEqual(ca.x_height([22, 22, 22, 40, 22]), 22.0)

    def test_linha_sem_box_nao_estoura(self) -> None:
        self.assertEqual(ca.x_height([]), 0.0)


class CorteTests(unittest.TestCase):
    """O defeito de assinatura que quase invalidou a medição deste item."""

    def test_o_corte_e_lido_na_chamada_e_nao_amarrado_na_definicao(self) -> None:
        """`corte: float = CORTE_DE_CAIXA` faria a varredura de limiar não variar nada.

        Foi o que aconteceu na primeira medição: sete cortes, sete CERs iguais até o quarto
        decimal. O teste existe para o defeito não voltar em silêncio.
        """
        original = ca.CORTE_DE_CAIXA
        try:
            ca.CORTE_DE_CAIXA = 1.25
            self.assertTrue(ca.caixa_pela_altura(31, 22))
            ca.CORTE_DE_CAIXA = 1.50
            self.assertFalse(ca.caixa_pela_altura(31, 22), "a constante nova não foi lida")
        finally:
            ca.CORTE_DE_CAIXA = original

    def test_o_corte_explicito_ganha_da_constante(self) -> None:
        self.assertFalse(ca.caixa_pela_altura(31, 22, corte=2.0))

    def test_sem_x_height_nao_promove_ninguem(self) -> None:
        """Linha sem altura conhecida é caso de não opinar, e não de chutar maiúscula."""
        self.assertFalse(ca.caixa_pela_altura(31, 0))


class DecidirTests(unittest.TestCase):
    def test_a_minuscula_e_recuperada_quando_a_altura_contradiz_o_argmax(self) -> None:
        """O caso medido: o modelo diz `S` com 0,96 e `s` com 0,03, e o box tem altura de x."""
        probs = _probs(1)
        self.assertEqual(ca.decidir(probs, [22], I2C, pares={0: 1, 1: 0})[0][0], "s")

    def test_a_maiuscula_legitima_sobrevive(self) -> None:
        alturas = [22, 22, 31, 22, 22]
        lidos = ca.decidir(_probs(1, n=5), alturas, I2C)
        self.assertEqual([c for c, _ in lidos], ["s", "s", "S", "s", "s"])

    def test_a_confianca_devolvida_e_a_da_classe_escolhida(self) -> None:
        """Trocar o caractere e manter os 0,96 do palpite recusado seria confiança inventada."""
        char, conf = ca.decidir(_probs(1), [22], I2C)[0]
        self.assertEqual(char, "s")
        self.assertLess(conf, 0.5, "a confiança tem de ser a do `s`, não a do `S` recusado")

    def test_o_que_nao_e_ambiguo_sai_igual_ao_argmax(self) -> None:
        """Fora das oito letras, o resultado é byte a byte o do classificador."""
        for indice in (2, 3, 6, 7):
            with self.subTest(char=I2C[indice]):
                self.assertEqual(ca.decidir(_probs(indice), [22], I2C)[0][0], I2C[indice])

    def test_uma_linha_sem_altura_nenhuma_nao_mexe_em_nada(self) -> None:
        self.assertEqual(ca.decidir(_probs(1), [], I2C)[0][0], "S")

    def test_lote_vazio_devolve_lista_vazia(self) -> None:
        self.assertEqual(ca.decidir(np.empty((0, len(I2C)), np.float32), [], I2C), [])

    def test_menos_alturas_que_boxes_nao_estoura(self) -> None:
        """A altura vem da segmentação e a probabilidade do modelo; discordar é caso de não opinar."""
        lidos = ca.decidir(_probs(1, n=3), [22], I2C)
        self.assertEqual([c for c, _ in lidos], ["s", "S", "S"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
