"""A régua de alinhamento do recorte (S-526): o damero deslizado, lido em pixel.

Tudo sintético e determinístico: um damero de 800 px com a grade deslocada de um valor conhecido,
com e sem peças, e uma imagem lisa. O que se afirma é que o deslocamento volta em pixel nos dois
eixos, que peça não engana a régua, e que "sem damero" é uma resposta e não um número aleatório.
"""

from __future__ import annotations

import time
import unittest

import numpy as np

from chess_diagram_ocr import alinhamento
from chess_diagram_ocr.alinhamento import Encaixe, encaixe_do_damero
from chess_diagram_ocr.config import BOARD_SIZE

CLARA, ESCURA = 230, 120


def _damero(sx: int = 0, sy: int = 0, *, pecas: bool = False) -> np.ndarray:
    """Um tabuleiro de `BOARD_SIZE` cuja grade começa em `(sx, sy)` em vez de `(0, 0)`."""
    casa = BOARD_SIZE // 8
    ys, xs = np.indices((BOARD_SIZE, BOARD_SIZE))
    coluna = np.floor_divide(xs - sx, casa)
    linha = np.floor_divide(ys - sy, casa)
    clara = ((coluna + linha) % 2) == 0
    cinza = np.where(clara, CLARA, ESCURA).astype(np.uint8)
    if pecas:
        # Um disco escuro numa casa clara e um claro numa casa escura, a cada duas casas: a peça
        # tem a borda mais forte da imagem, que é o que enganou a primeira régua.
        raio = casa // 3
        for i in range(8):
            for j in range(8):
                if (i + j) % 2 or (i * 8 + j) % 3:
                    continue
                cx = sx + j * casa + casa // 2
                cy = sy + i * casa + casa // 2
                disco = (xs - cx) ** 2 + (ys - cy) ** 2 <= raio**2
                cinza[disco] = 20 if clara[cy % BOARD_SIZE, cx % BOARD_SIZE] else 250
    return np.repeat(cinza[:, :, None], 3, axis=2)


class EncaixeTests(unittest.TestCase):
    def test_damero_alinhado_encaixa_em_zero(self) -> None:
        encaixe = encaixe_do_damero(_damero())
        self.assertEqual((0, 0), (encaixe.dx, encaixe.dy))
        self.assertTrue(encaixe.confiavel)
        self.assertEqual(0, encaixe.desalinhamento_px)
        self.assertFalse(encaixe.desalinhado)

    def test_o_deslocamento_volta_em_pixel_nos_dois_eixos(self) -> None:
        for sx, sy in ((7, 0), (0, -13), (18, -9), (-24, 24), (3, 3)):
            with self.subTest(sx=sx, sy=sy):
                encaixe = encaixe_do_damero(_damero(sx, sy))
                self.assertEqual((sx, sy), (encaixe.dx, encaixe.dy))

    def test_pecas_nas_casas_nao_enganam_a_regua(self) -> None:
        """É o caso que derrubou a primeira versão: a peça tem a borda mais forte da imagem."""
        encaixe = encaixe_do_damero(_damero(15, -6, pecas=True))
        self.assertEqual((15, -6), (encaixe.dx, encaixe.dy))
        self.assertTrue(encaixe.confiavel)

    def test_o_limite_separa_alinhado_de_desalinhado(self) -> None:
        limite = alinhamento.LIMITE_DE_DESALINHAMENTO_PX
        self.assertFalse(encaixe_do_damero(_damero(limite, 0)).desalinhado)
        self.assertTrue(encaixe_do_damero(_damero(limite + 1, 0)).desalinhado)
        self.assertTrue(encaixe_do_damero(_damero(0, -(limite + 1))).desalinhado)

    def test_cor_lisa_nao_tem_damero(self) -> None:
        """Sem damero a resposta é `SEM_DAMERO`, e não o deslocamento em que o ruído foi maior."""
        lisa = np.full((BOARD_SIZE, BOARD_SIZE, 3), 180, dtype=np.uint8)
        encaixe = encaixe_do_damero(lisa)
        self.assertFalse(encaixe.confiavel)
        self.assertEqual(alinhamento.SEM_DAMERO, encaixe.desalinhamento_px)
        self.assertFalse(encaixe.desalinhado)

    def test_recorte_pequeno_demais_responde_sem_damero_em_vez_de_levantar(self) -> None:
        self.assertEqual(Encaixe(0, 0, 0.0), encaixe_do_damero(np.zeros((40, 40, 3), dtype=np.uint8)))

    def test_aceita_cinza_e_rgb_com_a_mesma_resposta(self) -> None:
        rgb = _damero(9, 4)
        self.assertEqual(encaixe_do_damero(rgb), encaixe_do_damero(rgb[:, :, 0]))

    def test_o_alcance_e_menor_que_meia_casa(self) -> None:
        """A partir de meia casa o damero de uma casa adiante encaixa de novo, com as paridades
        trocadas, e a régua deixaria de saber qual dos dois é o certo."""
        self.assertLess(alinhamento.ALCANCE_PX, BOARD_SIZE // 16)

    def test_e_rapida_o_bastante_para_o_censo(self) -> None:
        """Roda por candidato dentro de `cvoff-census`, ao lado de `texture`."""
        imagem = _damero(5, 5, pecas=True)
        inicio = time.perf_counter()
        encaixe_do_damero(imagem)
        self.assertLess(time.perf_counter() - inicio, 1.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
