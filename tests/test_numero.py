"""O zero que sai letra, e o roque que sai `O.O` (S-211).

Dois testes carregam este arquivo, e os dois são de coisas que **não** devem acontecer: notação
não vira número (`♕xc8` fica), e a pontuação ao redor do roque não vira hífen (`0-0?!`, e não
`0-0--`, que foi o que a primeira versão devolveu).
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text import numero as nu
from chess_diagram_ocr.text.boxes import Caixa

I2C = {0: "0", 1: "o", 2: "O", 3: "-", 4: ".", 5: "♕", 6: "c", 7: "5", 8: "4", 9: "?", 10: "!"}


class TrechosTests(unittest.TestCase):
    def test_o_numero_solto_e_achado(self) -> None:
        self.assertEqual(nu.trechos_de_numero("2o"), [(0, 2)])

    def test_o_numero_colado_ao_lance_tambem(self) -> None:
        """`4o.♕c5` -- foi o caso que escapou da primeira versão, que olhava o token inteiro."""
        self.assertEqual(nu.trechos_de_numero("4o.♕c5"), [(0, 2)])

    def test_a_notacao_nao_e_numero(self) -> None:
        for token in ("♕xc8", "Rg8", "e4", "b1=♕", "cxd5"):
            with self.subTest(token=token):
                self.assertEqual(nu.trechos_de_numero(token), [])

    def test_o_oval_encostado_em_letra_nao_conta(self) -> None:
        """Sem esta guarda, um `o` que é letra de verdade viraria zero."""
        for token in ("Bo4", "loop", "no4", "4on"):
            with self.subTest(token=token):
                self.assertEqual(nu.trechos_de_numero(token), [])

    def test_sem_digito_nao_ha_numero(self) -> None:
        self.assertEqual(nu.trechos_de_numero("oo"), [])

    def test_sem_oval_nao_ha_o_que_corrigir(self) -> None:
        self.assertEqual(nu.trechos_de_numero("2025"), [])


class RoqueTests(unittest.TestCase):
    def test_as_formas_erradas_sao_reconhecidas(self) -> None:
        for token in ("O.O", "O-O", "0.0", "o-o", "O.O.O", "0-0-0"):
            with self.subTest(token=token):
                self.assertTrue(nu.e_roque(token))

    def test_a_pontuacao_ao_redor_fica_de_fora_do_nucleo(self) -> None:
        """`0-0?!` virava `0-0--` na primeira versão: o `?!` entrava no laço de troca."""
        self.assertEqual(nu.nucleo_do_roque("O.O?!"), (0, 3))

    def test_o_que_nao_e_roque_nao_casa(self) -> None:
        for token in ("O", "OO", "0-0-0-0", "abc", "e4-e5"):
            with self.subTest(token=token):
                self.assertIsNone(nu.nucleo_do_roque(token))


class CorrigirTests(unittest.TestCase):
    def _linha(self, texto: str) -> tuple[list[Caixa], list[tuple[str, float]], np.ndarray]:
        caixas = [Caixa(i * 10, 0, i * 10 + 8, 20) for i in range(len(texto))]
        lidos = [(c, 0.9) for c in texto]
        probs = np.zeros((len(texto), len(I2C)), np.float32)
        for k, c in enumerate(texto):
            indice = next((i for i, v in I2C.items() if v == c), None)
            if indice is not None:
                probs[k, indice] = 0.9
            probs[k, 0] = 0.05   # o zero sempre em rank 2
            probs[k, 3] = 0.04   # e o hifen logo atras
        return caixas, lidos, probs

    def _texto(self, saida: list[tuple[str, float]]) -> str:
        return "".join(c for c, _ in saida)

    def test_o_oval_do_numero_vira_zero(self) -> None:
        caixas, lidos, probs = self._linha("4o")
        self.assertEqual(self._texto(nu.corrigir(lidos, probs, caixas, I2C)), "40")

    def test_o_numero_colado_ao_lance_e_corrigido_e_o_lance_nao(self) -> None:
        caixas, lidos, probs = self._linha("4o.♕c5")
        self.assertEqual(self._texto(nu.corrigir(lidos, probs, caixas, I2C)), "40.♕c5")

    def test_o_roque_sai_com_zero_e_hifen(self) -> None:
        caixas, lidos, probs = self._linha("O.O")
        self.assertEqual(self._texto(nu.corrigir(lidos, probs, caixas, I2C)), "0-0")

    def test_a_pontuacao_do_roque_sobrevive(self) -> None:
        caixas, lidos, probs = self._linha("O.O?!")
        self.assertEqual(self._texto(nu.corrigir(lidos, probs, caixas, I2C)), "0-0?!")

    def test_a_notacao_passa_intacta(self) -> None:
        caixas, lidos, probs = self._linha("♕c5")
        self.assertEqual(self._texto(nu.corrigir(lidos, probs, caixas, I2C)), "♕c5")

    def test_a_confianca_do_zero_e_a_dele(self) -> None:
        caixas, lidos, probs = self._linha("4o")
        _, conf = nu.corrigir(lidos, probs, caixas, I2C)[1]
        self.assertAlmostEqual(conf, 0.05, places=3)

    def test_sem_a_classe_do_zero_devolve_intacto(self) -> None:
        caixas, lidos, probs = self._linha("4o")
        self.assertEqual(self._texto(nu.corrigir(lidos, probs, caixas, {1: "o", 8: "4"})), "4o")

    def test_lista_vazia_devolve_vazia(self) -> None:
        self.assertEqual(nu.corrigir([], np.empty((0, 4), np.float32), [], I2C), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
