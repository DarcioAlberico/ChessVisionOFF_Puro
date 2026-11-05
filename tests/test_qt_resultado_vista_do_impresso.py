"""O tabuleiro do Resultado é desenhado na vista do diagrama impresso.

Quando a orientação escolheu a leitura de cabeça para baixo (`rotation == 180`), o recorte
mostra o impresso e a posição é a canônica (brancas embaixo): sem virar a vista, a pessoa
corrige olhando para um tabuleiro espelhado do livro. O tabuleiro e o recorte têm de estar
na **mesma** vista -- é o que o pedido de 2026-09-21 fixou.
"""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.service import RecognizedDiagram

if TEM_PYQT:
    from chess_diagram_ocr.qt.painel_de_resultado import PainelDeResultado

LEGAL = "4k3/8/8/8/8/8/8/4K3"


def _diagrama(rotation: int, indice: int = 0) -> RecognizedDiagram:
    return RecognizedDiagram(
        index=indice,
        board_rgb=np.full((64, 64, 3), 200, np.uint8),
        placement=LEGAL,
        min_confidence=0.93,
        square_confidences=[0.99] * 64,
        side_to_move="w",
        rotation=rotation,
    )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class VistaDoImpressoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.painel = PainelDeResultado(mock.MagicMock(), csv_de_rotulos=pasta_temporaria(self) / "l.csv")

    def test_leitura_de_cabeca_para_baixo_desenha_o_tabuleiro_virado_como_o_recorte(self) -> None:
        self.painel.carregar_pagina([_diagrama(180)], chave="livro.pdf", pagina=0)
        self.assertTrue(self.painel.tabuleiro.virado, "tabuleiro na vista do impresso")
        self.assertTrue(self.painel.recorte._virado, "recorte mapeado na mesma vista")
        self.assertEqual(self.painel.tabuleiro.posicao(), LEGAL, "a posição continua canônica")

    def test_leitura_de_pe_fica_com_as_brancas_embaixo(self) -> None:
        self.painel.carregar_pagina([_diagrama(0)], chave="livro.pdf", pagina=0)
        self.assertFalse(self.painel.tabuleiro.virado)
        self.assertFalse(self.painel.recorte._virado)


if __name__ == "__main__":
    unittest.main()
