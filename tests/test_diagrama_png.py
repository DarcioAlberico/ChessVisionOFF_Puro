"""O diagrama em PNG, com as peças de `assets/piece_images/` (S-543).

**Por que se lê pixel aqui e não no SVG.** O SVG declara onde cada peça está; o PNG só tem cor. O
que se afirma é o mínimo que distingue um tabuleiro certo de um errado: a casa vazia tem a cor da
paleta, a casa com peça não tem, e virado põe a1 no canto de cima. A fonte das réguas é a embutida
do Pillow, então o texto não se compara -- a ordem já é afirmada em `test_diagrama_svg`, sobre a
mesma `reguas`.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import chess
from PIL import Image, ImageColor

from chess_diagram_ocr import diagrama_png, diagrama_svg

INICIAL = chess.STARTING_FEN
CASA, MARGEM = diagrama_png.CASA_PX, diagrama_png.MARGEM_PX


def _centro(coluna: int, linha: int, margem: int = MARGEM) -> tuple[int, int]:
    """O pixel do meio da casa desenhada na `coluna` e na `linha` (de cima para baixo)."""
    return margem + coluna * CASA + CASA // 2, margem + linha * CASA + CASA // 2


class BytesTests(unittest.TestCase):
    def test_sai_um_png_de_verdade_com_o_tamanho_das_pecas(self) -> None:
        dados = diagrama_png.png_da_posicao(INICIAL)
        self.assertTrue(dados.startswith(b"\x89PNG\r\n\x1a\n"))
        imagem = Image.open(__import__("io").BytesIO(dados))
        lado = 8 * CASA + 2 * MARGEM
        self.assertEqual(imagem.size, (lado, lado))

    def test_o_png_cabe_no_orcamento_do_livro(self) -> None:
        """55 KB em RGB, 20 KB em paleta: 2.618 estudos são 90 MB de diferença no `.docx`."""
        self.assertLess(len(diagrama_png.png_da_posicao(INICIAL)), 30_000)

    def test_sem_reguas_e_sem_lado_nao_ha_margem(self) -> None:
        imagem = diagrama_png.imagem_da_posicao(INICIAL.split()[0], com_reguas=False)
        self.assertEqual(imagem.size, (8 * CASA, 8 * CASA))


class CasasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cores = diagrama_svg.cores_padrao()
        self.clara = ImageColor.getrgb(self.cores.clara)
        self.escura = ImageColor.getrgb(self.cores.escura)

    def test_a_casa_vazia_tem_a_cor_da_paleta(self) -> None:
        imagem = diagrama_png.imagem_da_posicao(INICIAL)
        self.assertEqual(imagem.getpixel(_centro(4, 4)), self.clara)  # e4
        self.assertEqual(imagem.getpixel(_centro(3, 4)), self.escura)  # d4

    def test_a_casa_com_peca_nao_tem_a_cor_da_casa(self) -> None:
        imagem = diagrama_png.imagem_da_posicao(INICIAL)
        self.assertNotIn(imagem.getpixel(_centro(4, 7)), (self.clara, self.escura))  # rei branco em e1

    def test_virado_poe_a1_no_canto_superior_direito(self) -> None:
        """a1 é escura de qualquer lado; o que vira é onde ela cai."""
        imagem = diagrama_png.imagem_da_posicao("8/8/8/8/8/8/8/8", virado=True)
        self.assertEqual(imagem.getpixel(_centro(7, 0)), self.escura)  # a1
        self.assertEqual(imagem.getpixel(_centro(0, 0)), self.clara)  # h1
        normal = diagrama_png.imagem_da_posicao("8/8/8/8/8/8/8/8")
        self.assertEqual(normal.getpixel(_centro(0, 7)), self.escura)  # a1
        self.assertEqual(normal.getpixel(_centro(7, 7)), self.clara)  # h1

    def test_a_peca_virada_acompanha_a_casa(self) -> None:
        imagem = diagrama_png.imagem_da_posicao("8/8/8/8/8/8/8/4K3 w - - 0 1", virado=True)
        self.assertNotIn(imagem.getpixel(_centro(3, 0)), (self.clara, self.escura))  # e1 virada
        self.assertEqual(imagem.getpixel(_centro(4, 7)), self.escura)  # onde e1 estaria sem virar


class PecasAusentesTests(unittest.TestCase):
    def test_pasta_sem_pecas_desenha_a_letra_e_avisa(self) -> None:
        """`qt/tabuleiro.py` já degrada para glifo quando a pasta falta; um DOCX com `K` na casa é
        melhor que nenhum DOCX."""
        with self.assertLogs(diagrama_png.logger, level="WARNING") as registro:
            imagem = diagrama_png.imagem_da_posicao(
                "8/8/8/8/8/8/8/4K3 w - - 0 1", pasta_de_pecas=Path("C:/nao/existe/pecas")
            )
        self.assertTrue(any("wk" in linha for linha in registro.output))
        clara = ImageColor.getrgb(diagrama_svg.cores_padrao().clara)
        pixels = {imagem.getpixel((x, y)) for x in range(MARGEM + 4 * CASA, MARGEM + 5 * CASA) for y in range(MARGEM + 7 * CASA, MARGEM + 8 * CASA)}
        self.assertGreater(len(pixels - {clara}), 0)

    def test_a_pasta_padrao_e_a_do_bundle(self) -> None:
        self.assertEqual(diagrama_png.PASTA_DE_PECAS.name, "piece_images")
        self.assertTrue((diagrama_png.PASTA_DE_PECAS / "wk.png").exists())


if __name__ == "__main__":
    unittest.main()
