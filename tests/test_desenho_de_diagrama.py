"""O diagrama desenhado de novo a partir da posição, em PNG (`desenho_de_diagrama`).

É o desenho que a aba Texto põe no lugar do recorte quando a folha não está à mão, e o que o livro
com PGN usa. O que se afirma é o que quem chama recebe: bytes de PNG de verdade, do lado pedido, com
as casas nas cores do tronco e as peças onde a posição as põe.
"""

from __future__ import annotations

import io
import os
import unittest
from unittest import mock

import chess
from ambiente_de_teste import pasta_temporaria
from PIL import Image, ImageColor

from chess_diagram_ocr import desenho_de_diagrama as dd
from chess_diagram_ocr.ui import tokens

INICIAL = chess.Board().board_fen()
ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"


def _imagem(dados: bytes) -> Image.Image:
    return Image.open(io.BytesIO(dados)).convert("RGB")


def _centro(coluna: int, fileira_de_cima: int, lado: int = dd.LADO_PADRAO_PX) -> tuple[int, int]:
    casa = lado / 8
    return int(coluna * casa + casa / 2), int(fileira_de_cima * casa + casa / 2)


class PngDoDiagramaTests(unittest.TestCase):
    def test_a_posicao_inicial_sai_em_png_de_1024_px_de_lado(self) -> None:
        dados = dd.png_do_diagrama(INICIAL)
        self.assertTrue(dados.startswith(ASSINATURA_PNG))
        self.assertEqual((1024, 1024), _imagem(dados).size)

    def test_sem_fonte_de_xadrez_as_casas_tem_as_cores_do_tronco_e_as_pecas_aparecem(self) -> None:
        """Sem Merida, o desenho é o das peças do tronco sobre `CASA_CLARA`/`CASA_ESCURA`."""
        vazia = pasta_temporaria(self)
        with (
            mock.patch.object(dd, "PASTA_DE_FONTES", vazia),
            mock.patch.dict(os.environ, {dd.FONTE_MERIDA_ENV: ""}),
        ):
            imagem = _imagem(dd.png_do_diagrama(INICIAL))
        clara = ImageColor.getrgb(tokens.cor(tokens.CASA_CLARA))
        escura = ImageColor.getrgb(tokens.cor(tokens.CASA_ESCURA))
        self.assertEqual(clara, imagem.getpixel(_centro(4, 4)))  # e4, casa clara vazia
        self.assertEqual(escura, imagem.getpixel(_centro(3, 4)))  # d4, casa escura vazia
        self.assertNotIn(imagem.getpixel(_centro(4, 7)), (clara, escura))  # e1, o rei branco
        self.assertNotIn(imagem.getpixel(_centro(3, 0)), (clara, escura))  # d8, a dama preta

    def test_posicoes_diferentes_desenham_diferente(self) -> None:
        depois_de_e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"
        self.assertNotEqual(dd.png_do_diagrama(INICIAL), dd.png_do_diagrama(depois_de_e4))


if __name__ == "__main__":
    unittest.main()
