"""S-734: aspas duplas e apóstrofo, pela geometria da caixa.

Decisão com caixas sintéticas, que roda no CI sem modelo nem livro. Cada família tem o caso que reproduz o
defeito com a constante desligada: teste que passa com o conserto revertido não guarda nada.
"""

from __future__ import annotations

import unittest
from unittest import mock

from glifo_sintetico import DE_X, _lidos, _linha, _texto

from chess_diagram_ocr.text import marca_fina
from chess_diagram_ocr.text.boxes import Caixa


class AspasTests(unittest.TestCase):
    """S-734: `"tail` saía `'(tail`, e `rook"` saía `rook''`."""

    @staticmethod
    def _desenho(*riscos: tuple[str, int]) -> tuple[list[str], list[Caixa]]:
        """Letras de corpo, depois os riscos no alto da linha, com o vão pedido."""
        chars, caixas = _linha([("k", 12, 30), ("e", 12, 20), ("n", 12, 20)])
        x = caixas[-1].x2
        for char, vao in riscos:
            x += vao
            caixas.append(Caixa(x, 70, x + 7, 80))
            chars.append(char)
            x += 7
        return (chars, caixas)

    def _ler(self, *riscos: tuple[str, int]) -> str:
        chars, caixas = self._desenho(*riscos)
        return _texto(marca_fina.aspas(_lidos(chars), caixas)[1])

    def test_dois_riscos_sao_aspas(self) -> None:
        self.assertEqual(self._ler(("'", 3), ("'", 3)), 'ken"')
        self.assertEqual(self._ler(("'", 3), ("(", 3)), 'ken"')
        self.assertEqual(self._ler(("(", 3), ("'", 3)), 'ken"')

    def test_a_caixa_e_fundida(self) -> None:
        chars, caixas = self._desenho(("'", 3), ("'", 3))
        novas, _ = marca_fina.aspas(_lidos(chars), caixas)
        self.assertEqual(len(novas), 4)
        self.assertEqual((novas[-1].x1, novas[-1].x2), (caixas[3].x1, caixas[4].x2))

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(marca_fina, "ASPAS_PELA_GEOMETRIA", False):
            self.assertEqual(self._ler(("'", 3), ("(", 3)), "ken'(")

    def test_o_parentese_pequeno_no_alto_e_apostrofo(self) -> None:
        self.assertEqual(self._ler(("(", 3)), "ken'")

    def test_o_parentese_de_verdade_fica(self) -> None:
        chars, caixas = _linha([("(", 8, 34), *DE_X, (")", 8, 34)])
        self.assertEqual(_texto(marca_fina.aspas(_lidos(chars), caixas)[1]), "(aen)")

    def test_a_virgula_baixa_fica(self) -> None:
        chars, caixas = _linha([*DE_X, ("k", 12, 30)])
        chars = [*chars, ","]
        caixas = [*caixas, Caixa(caixas[-1].x2 + 3, 96, caixas[-1].x2 + 8, 105)]
        self.assertEqual(_texto(marca_fina.aspas(_lidos(chars), caixas)[1]), "aenk,")

    def test_dois_riscos_longe_um_do_outro_sao_dois_apostrofos(self) -> None:
        self.assertEqual(self._ler(("'", 3), ("'", 30)), "ken''")


class LimiaresDasAspasTests(AspasTests):
    def test_a_folga_e_de_uma_largura(self) -> None:
        self.assertEqual(self._ler(("'", 3), ("'", 7)), 'ken"', "7 px, com o risco de 7")
        self.assertEqual(self._ler(("'", 3), ("'", 8)), "ken''", "8 px")

    def test_tudo_o_que_o_modelo_responde_no_alto(self) -> None:
        for char in "'(),`":
            self.assertEqual(self._ler((char, 3)), "ken'", char)


if __name__ == "__main__":
    unittest.main()
