"""S-730: traço vertical contra ponto, pela geometria da caixa.

Decisão com caixas sintéticas, que roda no CI sem modelo nem livro. Cada família tem o caso que reproduz o
defeito com a constante desligada: teste que passa com o conserto revertido não guarda nada.
"""

from __future__ import annotations

import unittest
from unittest import mock

from glifo_sintetico import DE_X, I2C, _lidos, _linha, _matriz, _texto

from chess_diagram_ocr.text import traco_vertical
from chess_diagram_ocr.text.boxes import Caixa


class TracoVerticalTests(unittest.TestCase):
    """S-730: `will` saía `wi..`, e `I` saía `.`."""

    def _ler(self, desenho: list[tuple[str, int, int]], lexico: frozenset[str] = frozenset()) -> str:
        chars, caixas = _linha(desenho)
        return _texto(traco_vertical.corrigir(_lidos(chars), _matriz(chars), caixas, I2C, lexico, escala=28.0))

    def test_o_traco_alto_lido_como_ponto_e_letra(self) -> None:
        self.assertEqual(self._ler([*DE_X, ("w", 15, 20), ("i", 3, 27), (".", 3, 27), (".", 3, 27)]), "aenwill")

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(traco_vertical, "LIGADO", False):
            self.assertEqual(self._ler([*DE_X, ("w", 15, 20), ("i", 3, 27), (".", 3, 27), (".", 3, 27)]), "aenwi..")

    def test_o_traco_lido_como_travessao_tambem_e_letra(self) -> None:
        """Onde o `.` não vence, vence o `—`, e o `l` cai para o sexto lugar. O rank não decide."""
        self.assertEqual(self._ler([*DE_X, ("—", 3, 27), ("o", 12, 20)]), "aenlo")

    def test_o_ponto_de_verdade_fica(self) -> None:
        self.assertEqual(self._ler([*DE_X, ("t", 8, 25), (".", 4, 4)]), "aent.")

    def test_a_marca_alta_mas_larga_nao_e_traco(self) -> None:
        """A proporção é a segunda condição: sem ela, uma caixa alta qualquer lida como `-` viraria `l`."""
        self.assertEqual(self._ler([*DE_X, ("-", 20, 27), ("o", 12, 20)]), "aen-o")

    def test_sozinho_e_o_pronome(self) -> None:
        chars, caixas = _linha(DE_X)
        ultimo = caixas[-1]
        chars = [*chars, ".", "w", "e"]
        caixas = [*caixas, Caixa(ultimo.x2 + 30, 73, ultimo.x2 + 33, 100), Caixa(ultimo.x2 + 60, 80, ultimo.x2 + 72, 100),
                  Caixa(ultimo.x2 + 75, 80, ultimo.x2 + 87, 100)]
        lidos = traco_vertical.corrigir(_lidos(chars), _matriz(chars), caixas, I2C, frozenset(), escala=28.0)
        self.assertEqual(lidos[3][0], "I")

    def test_no_numero_e_um(self) -> None:
        """`11.`, a família também custa na notação."""
        self.assertEqual(self._ler([*DE_X, ("1", 8, 27), (".", 3, 27)]), "aen11")

    def test_no_fim_do_lance_e_um(self) -> None:
        chars, caixas = _linha([("a", 12, 20), ("e", 12, 20)], vao=40)
        extra_chars, extra = _linha([("R", 14, 27), ("f", 8, 27), (".", 3, 27)], x=caixas[-1].x2 + 40)
        lidos = traco_vertical.corrigir(_lidos(chars + extra_chars), _matriz(chars + extra_chars), caixas + extra, I2C, frozenset())
        self.assertEqual(_texto(lidos), "aeRf1")

    def test_o_i_sem_pingo(self) -> None:
        """Em scan o pingo se perde: `fixed` saía `f.xed`, e `flxed` não é palavra."""
        lido = self._ler([("f", 8, 27), (".", 3, 27), ("x", 12, 20), ("e", 12, 20), ("d", 12, 27)], frozenset({"fixed"}))
        self.assertEqual(lido, "fixed")

    def test_no_comeco_o_lexico_separa_l_de_i(self) -> None:
        lexico = frozenset({"look", "informant"})
        self.assertEqual(self._ler([(".", 3, 27), ("o", 12, 20), ("o", 12, 20), ("k", 12, 27), *DE_X], lexico)[0], "l")
        self.assertEqual(self._ler([(".", 3, 27), ("n", 12, 20)], frozenset())[0], "I", "`In`, na lista das curtas")

    def test_o_l_lido_no_comeco_so_vira_i_se_a_palavra_for_outra(self) -> None:
        self.assertEqual(self._ler([("l", 3, 27), ("f", 8, 27), *DE_X[:0]])[:2], "If")
        self.assertEqual(self._ler([("l", 3, 27), ("i", 3, 27), ("k", 12, 27), ("e", 12, 20)], frozenset({"like"}))[:4], "like")

    def test_a_barra_baixa_que_desce_e_virgula(self) -> None:
        """`entanto,` saía `entantol`, e a classe `,` nem aparece entre as oito primeiras do modelo."""
        chars, caixas = _linha(DE_X)
        chars = [*chars, "/"]
        caixas = [*caixas, Caixa(caixas[-1].x2 + 2, 94, caixas[-1].x2 + 6, 106)]
        lidos = traco_vertical.corrigir(_lidos(chars), _matriz(chars), caixas, I2C, frozenset(), escala=28.0)
        self.assertEqual(lidos[-1][0], ",")
        self.assertAlmostEqual(lidos[-1][1], 1e-5, msg="a confiança é a da classe escolhida")

    def test_a_barra_alta_fica(self) -> None:
        self.assertEqual(self._ler([*DE_X, ("/", 8, 28)]), "aen/")

    def test_a_barra_pequena_no_alto_fica(self) -> None:
        """Fração impressa pequena: meia altura de letra, mas não desce abaixo da base."""
        chars, caixas = _linha(DE_X)
        chars = [*chars, "/"]
        caixas = [*caixas, Caixa(caixas[-1].x2 + 2, 78, caixas[-1].x2 + 6, 90)]
        lidos = traco_vertical.corrigir(_lidos(chars), _matriz(chars), caixas, I2C, frozenset(), escala=28.0)
        self.assertEqual(lidos[-1][0], "/")


class LimiaresDoTracoTests(unittest.TestCase):
    """Cada limiar preso dos dois lados, em caixa de verdade: altura-de-x 20, das letras `aen`."""

    def _ler(self, char: str, largura: int, altura: int) -> str:
        chars, caixas = _linha([*DE_X, (char, largura, altura), ("o", 12, 20)])
        return traco_vertical.corrigir(_lidos(chars), _matriz(chars), caixas, I2C, frozenset(), escala=28.0)[3][0]

    def test_toda_marca_alta_e_traco(self) -> None:
        for char in ".,'`-–—_":
            self.assertEqual(self._ler(char, 3, 27), "l", char)

    def test_toda_coluna_no_fim_do_lance(self) -> None:
        for coluna in "abcdefgh":
            chars, caixas = _linha([("R", 14, 27), (coluna, 8, 27), (".", 3, 27)])
            lidos = traco_vertical.corrigir(_lidos(chars), _matriz(chars), caixas, I2C, frozenset(), escala=28.0)
            self.assertEqual(lidos[-1][0], "1", coluna)

    def test_a_altura(self) -> None:
        self.assertEqual(self._ler(".", 3, 21), "l", "1,05: o traço mais baixo medido é 1,03")
        self.assertEqual(self._ler(".", 2, 12), ".", "0,60: entre o ponto e o traço, fica como está")

    def test_a_proporcao(self) -> None:
        self.assertEqual(self._ler("-", 8, 27), "l", "0,30")
        self.assertEqual(self._ler("-", 12, 27), "-", "0,44: acima do traço medido, e não é traço")

    def _ultima(self, char: str, y1: int, y2: int) -> str:
        chars, caixas = _linha(DE_X)
        chars, caixas = [*chars, char], [*caixas, Caixa(caixas[-1].x2 + 2, y1, caixas[-1].x2 + 6, y2)]
        return traco_vertical.corrigir(_lidos(chars), _matriz(chars), caixas, I2C, frozenset(), escala=28.0)[-1][0]

    def test_todo_traco_baixo_que_desce_e_virgula(self) -> None:
        for char in "/l1I|":
            self.assertEqual(self._ultima(char, 94, 106), ",", char)

    def test_a_altura_da_virgula(self) -> None:
        self.assertEqual(self._ultima("/", 89, 107), "/", "0,90 de altura: é barra de verdade, mesmo descendo")

    def test_a_descida_da_virgula(self) -> None:
        self.assertEqual(self._ultima("/", 91, 103), "/", "só 0,25 da caixa abaixo da base")
        self.assertEqual(self._ultima("/", 88, 100), "/", "nada abaixo da base")
        self.assertEqual(self._ultima("/", 95, 105), ",", "0,50")


if __name__ == "__main__":
    unittest.main()
