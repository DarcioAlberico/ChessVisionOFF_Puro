"""O quadro emoldurado de largura inteira, e a moldura que o separa da lista de lances (S-525).

**O teste que dá nome a este arquivo é `test_a_moldura_oca_e_quadro_e_o_tabuleiro_cheio_nao`.**
A borda da S-523 cede duas bandas; o «Scoring» do Yusupov tem cinco, e tratá-lo como bloco de
borda partia a lista de lances do Chernev. O que só o quadro tem é a moldura: uma caixa larga,
alta e **oca**.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import numpy as np
from test_text_colunas import (  # type: ignore[import-not-found]
    ALTURA_DA_LETRA,
    ESQUERDA,
    LARGURA_DA_LETRA,
    PASSO_X,
    PASSO_Y,
    POR_LINHA,
)

from chess_diagram_ocr.text import quadros
from chess_diagram_ocr.text.boxes import Caixa

ESCALA = ALTURA_DA_LETRA
LARGURA_DO_TEXTO = 2 * POR_LINHA * PASSO_X + 110


def _linha(x0: int, y: int, quantas: int) -> list[Caixa]:
    return [Caixa(x0 + i * PASSO_X, y, x0 + i * PASSO_X + LARGURA_DA_LETRA, y + ALTURA_DA_LETRA) for i in range(quantas)]


def _folha(linhas: int = 20) -> list[Caixa]:
    """Prosa de largura inteira, para dar a largura do texto."""
    return [c for i in range(linhas) for c in _linha(ESQUERDA, 100 + i * PASSO_Y, 2 * POR_LINHA + 6)]


def _binaria(caixas: list[Caixa], *, cheias: list[Caixa] = ()) -> np.ndarray:
    """A imagem binária das caixas: letras como pontos de tinta, `cheias` pintadas inteiras."""
    altura = max(c.y2 for c in caixas) + 10
    largura = max(c.x2 for c in caixas) + 10
    imagem = np.zeros((altura, largura), dtype=np.uint8)
    for c in caixas:
        imagem[c.y1 : c.y2 + 1, c.x1 : c.x1 + 2] = 255  # uma haste por letra: pouca tinta
    for c in cheias:
        imagem[c.y1 : c.y2 + 1, c.x1 : c.x2 + 1] = 255
    return imagem


def _moldura(y: int, linhas_dentro: int = 3) -> tuple[Caixa, list[Caixa]]:
    """Uma caixa larga e alta (a moldura) com `linhas_dentro` linhas curtas dentro dela."""
    altura = (linhas_dentro + 1) * PASSO_Y
    caixa = Caixa(ESQUERDA + 40, y, ESQUERDA + int(0.6 * LARGURA_DO_TEXTO), y + altura)
    dentro = [c for i in range(linhas_dentro) for c in _linha(ESQUERDA + 80, y + (i + 1) * PASSO_Y - 10, 8)]
    return caixa, dentro


class MolduraNasCaixasTests(unittest.TestCase):
    def test_a_moldura_oca_e_quadro_e_o_tabuleiro_cheio_nao(self) -> None:
        folha = _folha()
        y = 100 + 20 * PASSO_Y + PASSO_Y
        moldura, dentro = _moldura(y)
        caixas = [*folha, moldura, *dentro]
        oca = quadros.molduras_nas_caixas(caixas, _binaria(caixas), escala=ESCALA)
        self.assertEqual([(moldura.y1, moldura.y2)], oca)
        # A mesma caixa pintada inteira é um tabuleiro que o detector não achou -- não é quadro.
        cheia = quadros.molduras_nas_caixas(caixas, _binaria(caixas, cheias=[moldura]), escala=ESCALA)
        self.assertEqual([], cheia)

    def test_a_moldura_sem_linha_dentro_nao_e_quadro_de_texto(self) -> None:
        folha = _folha()
        moldura, _ = _moldura(100 + 21 * PASSO_Y)
        caixas = [*folha, moldura]
        self.assertEqual([], quadros.molduras_nas_caixas(caixas, _binaria(caixas), escala=ESCALA))

    def test_a_caixa_estreita_ou_baixa_nao_e_quadro(self) -> None:
        folha = _folha()
        estreita = Caixa(ESQUERDA, 2000, ESQUERDA + int(0.3 * LARGURA_DO_TEXTO), 2000 + 5 * PASSO_Y)
        baixa = Caixa(ESQUERDA, 2400, ESQUERDA + int(0.8 * LARGURA_DO_TEXTO), 2400 + 2 * ESCALA)
        caixas = [*folha, estreita, baixa]
        self.assertEqual([], quadros.molduras_nas_caixas(caixas, _binaria(caixas), escala=ESCALA))

    def test_sem_caixa_nenhuma_nao_ha_quadro(self) -> None:
        self.assertEqual([], quadros.molduras_nas_caixas([], np.zeros((1, 1), dtype=np.uint8), escala=ESCALA))

    def test_dois_quadros_que_se_tocam_sao_um(self) -> None:
        self.assertEqual([(10, 60), (80, 90)], quadros._fundidos([(30, 60), (10, 40), (80, 90)]))


class QuadrosDaCamadaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.raiz = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def _pagina(self, *, imagem: tuple[float, float, float, float] | None, linhas_dentro: int) -> fitz.Page:
        doc = fitz.open()
        page = doc.new_page(width=595.0, height=842.0)
        for i in range(10):
            page.insert_text((60.0, 100.0 + i * 20), f"linha {i}", fontsize=11)
        if imagem is not None:
            x0, y0, x1, y1 = imagem
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
            pix.clear_with(200)
            page.insert_image(fitz.Rect(x0, y0, x1, y1), pixmap=pix)
            # Linhas centradas, que cruzam o meio da imagem, com palavras: o «Scoring».
            for i in range(linhas_dentro):
                page.insert_text(((x0 + x1) / 2 - 60, y0 + 20 + i * 15), f"linha centrada numero {i}", fontsize=10)
        self._doc = doc
        return page

    def test_a_imagem_larga_com_linhas_dentro_e_quadro(self) -> None:
        page = self._pagina(imagem=(60.0, 500.0, 500.0, 600.0), linhas_dentro=3)
        [(y0, y1)] = quadros.quadros_da_camada(page)
        self.assertAlmostEqual(500.0, y0, delta=2.0)
        self.assertAlmostEqual(600.0, y1, delta=2.0)

    def test_a_imagem_sem_linha_dentro_e_diagrama_e_nao_quadro(self) -> None:
        page = self._pagina(imagem=(60.0, 500.0, 500.0, 600.0), linhas_dentro=0)
        self.assertEqual([], quadros.quadros_da_camada(page))

    def test_as_linhas_de_duas_colunas_sobre_a_imagem_de_fundo_nao_fazem_quadro(self) -> None:
        """A lição do Yusupov p. 1872: a imagem de fundo é larga, e as linhas dentro ficam cada
        uma de um lado do meio -- a maioria não cruza, e a imagem não é quadro."""
        doc = fitz.open()
        page = doc.new_page(width=595.0, height=842.0)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
        pix.clear_with(200)
        page.insert_image(fitz.Rect(60.0, 100.0, 540.0, 400.0), pixmap=pix)
        for i in range(8):
            page.insert_text((70.0, 130.0 + i * 20), f"esquerda linha {i}", fontsize=10)
            page.insert_text((330.0, 130.0 + i * 20), f"direita linha {i}", fontsize=10)
        page.insert_text((250.0, 115.0), "um titulo centrado", fontsize=12)
        self.assertEqual([], quadros.quadros_da_camada(page))

    def test_o_lixo_sem_palavras_cruzando_o_meio_nao_faz_quadro(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=595.0, height=842.0)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
        pix.clear_with(200)
        page.insert_image(fitz.Rect(60.0, 500.0, 500.0, 600.0), pixmap=pix)
        for i in range(3):
            page.insert_text((220.0, 520.0 + i * 15), "• • 1. • • •", fontsize=10)
        self.assertEqual([], quadros.quadros_da_camada(page))

    def test_a_imagem_estreita_nao_e_quadro(self) -> None:
        page = self._pagina(imagem=(60.0, 500.0, 200.0, 600.0), linhas_dentro=3)
        self.assertEqual([], quadros.quadros_da_camada(page))

    def test_o_fundo_da_pagina_inteira_nao_e_quadro(self) -> None:
        page = self._pagina(imagem=(0.0, 0.0, 595.0, 842.0), linhas_dentro=3)
        self.assertEqual([], quadros.quadros_da_camada(page))

    def test_sem_imagem_nao_ha_quadro(self) -> None:
        self.assertEqual([], quadros.quadros_da_camada(self._pagina(imagem=None, linhas_dentro=0)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
