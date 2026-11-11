"""O léxico é achado no programa instalado, e não só na árvore do projeto."""

from __future__ import annotations

import unittest
from pathlib import Path

from subprocesso import rodar_python

from chess_diagram_ocr.text import lexico


class LexicoNoBundleTests(unittest.TestCase):
    def test_a_pasta_segue_o_bundle(self) -> None:
        codigo = (
            "import sys; sys._MEIPASS = r'C:\\bundle\\_internal'; "
            "from chess_diagram_ocr.text import lexico; print(lexico.PASTA_DO_LEXICO)"
        )
        saida = rodar_python(codigo).stdout
        self.assertEqual(Path(saida.strip()), Path(r"C:\bundle\_internal") / "assets" / "lexico")

    def test_as_tres_listas_existem_na_arvore(self) -> None:
        for caminho in (lexico.CAMINHO_ACERVO, lexico.CAMINHO_IDIOMA, lexico.CAMINHO_NOMES):
            with self.subTest(caminho=caminho.name):
                self.assertTrue(caminho.is_file())


if __name__ == "__main__":
    unittest.main()
