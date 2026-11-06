"""S-733: a ligadura sem o `1` a mais.

Decisão com caixas sintéticas, que roda no CI sem modelo nem livro. Cada família tem o caso que reproduz o
defeito com a constante desligada: teste que passa com o conserto revertido não guarda nada.
"""

from __future__ import annotations

import unittest
from unittest import mock

from glifo_sintetico import _lidos, _linha, _texto

from chess_diagram_ocr.text import ligadura


class LigaduraTests(unittest.TestCase):
    """S-733: `first` saía `fi1rst`, e `flee` saía `f1ee`."""

    def _ler(self, desenho: list[tuple[str, int, int]], vao: int = 2) -> tuple[str, int]:
        chars, caixas = _linha(desenho, vao=vao)
        novas, lidos = ligadura.corrigir(_lidos(chars), caixas)
        return (_texto(lidos), len(novas))

    def test_a_haste_solta_se_funde(self) -> None:
        self.assertEqual(self._ler([("fi", 12, 28), ("1", 9, 20), ("r", 8, 20), ("s", 9, 20), ("t", 8, 26)]), ("first", 4))

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(ligadura, "LIGADO", False):
            self.assertEqual(self._ler([("fi", 12, 28), ("1", 9, 20), ("r", 8, 20)]), ("fi1r", 3))

    def test_o_l_de_file_nao_e_haste(self) -> None:
        self.assertEqual(self._ler([("fi", 12, 28), ("l", 3, 27), ("e", 12, 20)]), ("file", 3))

    def test_a_haste_longe_fica(self) -> None:
        self.assertEqual(self._ler([("fi", 12, 28), ("1", 9, 20)], vao=20), ("fi1", 2))

    def test_f1_de_palavra_vira_fl(self) -> None:
        self.assertEqual(self._ler([("f1", 15, 28), ("e", 12, 20), ("e", 12, 20)]), ("flee", 3))

    def test_f1_de_lance_fica(self) -> None:
        self.assertEqual(self._ler([("R", 15, 28), ("f1", 15, 28)]), ("Rf1", 2))
        self.assertEqual(self._ler([("f1", 15, 28), ("-", 8, 3), ("e", 12, 20), ("1", 9, 28)]), ("f1-e1", 4))
        self.assertEqual(self._ler([("f1", 15, 28), ("e", 12, 20), ("2", 9, 28)]), ("f1e2", 3))


if __name__ == "__main__":
    unittest.main()
