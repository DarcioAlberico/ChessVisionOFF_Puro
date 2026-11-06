"""S-731: a régua de altura pelas letras de x, a palavra coerente, e o `P` pela descida.

Decisão com caixas sintéticas, que roda no CI sem modelo nem livro. Cada família tem o caso que reproduz o
defeito com a constante desligada: teste que passa com o conserto revertido não guarda nada.
"""

from __future__ import annotations

import unittest
from unittest import mock

from glifo_sintetico import DE_X, I2C, _lidos, _linha, _matriz, _texto

from chess_diagram_ocr.text import caixa_alta
from chess_diagram_ocr.text.palavras_curtas import CURTAS, conhecida_ou_curta


class ReguaDeAlturaTests(unittest.TestCase):
    """S-731: a mediana da linha sobe com notação e maiúscula, e derruba o `W`."""

    def _decidir(self, desenho: list[tuple[str, int, int]], escala: float | None = None) -> str:
        chars, caixas = _linha(desenho)
        lidos = caixa_alta.decidir(_matriz(chars), [c.altura for c in caixas], I2C, caixas=caixas, escala=escala)
        return _texto(lidos)

    # O `W` numa linha cheia de lance: a mediana das alturas é a da maiúscula.
    LANCES = [("W", 24, 28), ("h", 12, 28), ("1", 8, 28), ("2", 8, 28), ("3", 8, 28), ("4", 8, 28), ("a", 12, 20), ("e", 12, 20)]

    def test_o_w_na_linha_de_notacao(self) -> None:
        self.assertEqual(self._decidir(self.LANCES), "Wh1234ae")

    def test_o_defeito_volta_com_a_mediana(self) -> None:
        with mock.patch.object(caixa_alta, "XH_COERENTE", False):
            self.assertEqual(self._decidir(self.LANCES), "wh1234ae")

    def test_a_linha_toda_em_maiuscula(self) -> None:
        self.assertEqual(self._decidir([(c, 16, 28) for c in "DEFESA"]), "DEFESA")
        with mock.patch.object(caixa_alta, "XH_COERENTE", False):
            self.assertEqual(self._decidir([(c, 16, 28) for c in "DEFESA"]), "DEFEsA")

    def test_com_letras_de_x_a_regua_e_delas(self) -> None:
        """Haste muito alta não muda a altura-de-x: pela razão das altas, este `C` cairia para `c`."""
        desenho = [*DE_X, ("h", 12, 40), ("d", 12, 40), ("b", 12, 40), ("C", 16, 28)]
        self.assertEqual(self._decidir(desenho), "aenhdbC")

    def test_a_minuscula_sem_letra_de_x_fica_minuscula(self) -> None:
        """`Bc4 Nc5`: nenhum `a`, `e`, `m`, `n`, `r`, e o `c` tem 0,7 da altura das altas."""
        self.assertEqual(self._decidir([("B", 16, 28), ("c", 12, 20), ("4", 10, 28)]), "Bc4")

    def test_a_linha_de_um_sinal_usa_a_escala_da_folha(self) -> None:
        self.assertEqual(self._decidir([("W", 24, 28)], escala=28.0), "W")
        self.assertEqual(self._decidir([("w", 16, 20)], escala=28.0), "w")
        self.assertEqual(self._decidir([("W", 24, 28)]), "w", "sem escala, o que sobra é a mediana da própria caixa")


class PalavraCoerenteTests(unittest.TestCase):
    """S-731: `FcM`, e o versalete, em que altura nenhuma separa."""

    def _coerente(self, palavra: str) -> str:
        chars, caixas = _linha([(c, 12, 20) for c in palavra])
        return _texto(caixa_alta.coerente(_lidos(chars), _matriz(chars), caixas, I2C))

    def test_a_palavra_em_maiuscula_nao_ganha_minuscula(self) -> None:
        self.assertEqual(self._coerente("uNusuAL"), "UNUSUAL")
        self.assertEqual(self._coerente("FcM"), "FCM")
        self.assertEqual(self._coerente("ANTlPoslTloNAL"), "ANTIPOSITIONAL")

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(caixa_alta, "PALAVRA_COERENTE", False):
            self.assertEqual(self._coerente("uNusuAL"), "uNusuAL")

    def test_palavra_comum_fica(self) -> None:
        for palavra in ("Black", "White", "Los", "os"):
            self.assertEqual(self._coerente(palavra), palavra)

    def test_a_ambigua_depois_de_minuscula_desce(self) -> None:
        self.assertEqual(self._coerente("IvanchUk"), "Ivanchuk")
        self.assertEqual(self._coerente("McDonald"), "McDonald", "o `D` tem desenho próprio")

    def test_a_captura_seguida_de_casa_e_minuscula(self) -> None:
        self.assertEqual(self._coerente("QXf7"), "Qxf7")
        self.assertEqual(self._coerente("TXPTR"), "TXPTR", "descritiva")

    def test_lance_fica(self) -> None:
        """Lance tem dígito, e `KxR` é captura: o `x` só sobe a partir de quatro letras."""
        for palavra in ("Nc3", "RxN3", "KxR", "QxB"):
            self.assertEqual(self._coerente(palavra), palavra)
        self.assertEqual(self._coerente("EXPRESs"), "EXPRESS")


class PalavrasCurtasTests(unittest.TestCase):
    def test_toda_palavra_e_curta_e_em_minuscula(self) -> None:
        self.assertTrue(all(len(p) < 4 and p == p.casefold() for p in CURTAS))

    def test_a_consulta(self) -> None:
        self.assertTrue(conhecida_ou_curta("The,", frozenset()))
        self.assertTrue(conhecida_ou_curta("first", frozenset({"first"})))
        self.assertFalse(conhecida_ou_curta("first", frozenset()))
        self.assertFalse(conhecida_ou_curta("...", frozenset({"..."})))


if __name__ == "__main__":
    unittest.main()
