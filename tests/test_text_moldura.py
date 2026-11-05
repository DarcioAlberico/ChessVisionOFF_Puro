"""A moldura que envolve a folha não apaga a folha (S-711). Folhas desenhadas aqui: nenhum livro comercial."""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from chess_diagram_ocr.text import leitor, moldura
from chess_diagram_ocr.text.binarizacao import binarize

TEXTO = "the white knight wins a pawn"


def _folha(*, filete: bool = False, faixa: bool = False, linhas: int = 20) -> np.ndarray:
    """Uma folha com texto; o filete fino na borda fecha a volta, e a faixa é a lateral do *Chess Evolution*."""
    imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
    for n in range(linhas):
        cv2.putText(imagem, TEXTO, (220, 80 + 56 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
    if faixa:
        imagem[:, :160] = 40
    if filete:
        cv2.rectangle(imagem, (0, 0), (999, 1399), (40, 40, 40), 2)
    return imagem


def _caixas(imagem: np.ndarray) -> int:
    return len(leitor.segmentar(imagem)[3])


class SegmentarTests(unittest.TestCase):
    """O mecanismo, reproduzido: só a moldura que envolve apaga, e a faixa sozinha não."""

    def test_o_filete_com_a_faixa_nao_apaga_as_letras(self) -> None:
        self.assertGreater(_caixas(_folha(filete=True, faixa=True)), 300)

    def test_o_filete_sozinho_nao_apaga_as_letras(self) -> None:
        self.assertGreater(_caixas(_folha(filete=True)), 300)

    def test_acha_o_mesmo_que_na_folha_sem_moldura(self) -> None:
        limpa = _caixas(_folha())
        self.assertLess(abs(_caixas(_folha(filete=True)) - limpa), limpa * 0.02)

    def test_a_faixa_sem_filete_sempre_leu(self) -> None:
        self.assertGreater(_caixas(_folha(faixa=True)), 300)

    def test_a_escala_nao_sai_da_moldura(self) -> None:
        self.assertEqual(leitor.segmentar(_folha(filete=True))[2], leitor.segmentar(_folha())[2])


class TirarMolduraTests(unittest.TestCase):
    def test_a_folha_sem_moldura_e_o_mesmo_objeto(self) -> None:
        binaria = binarize(_folha())
        limpa, quantas = moldura.tirar_moldura(binaria)
        self.assertIs(limpa, binaria)
        self.assertEqual(quantas, 0)

    def test_sai_so_o_componente_que_envolve(self) -> None:
        binaria = binarize(_folha(filete=True))
        limpa, quantas = moldura.tirar_moldura(binaria)
        self.assertEqual(quantas, 1)
        self.assertEqual(int(limpa[0, 500]), 0)
        self.assertGreater(int((limpa > 0).sum()), 1000, "as letras continuam na binária")

    def test_a_faixa_sozinha_nao_e_moldura(self) -> None:
        self.assertEqual(moldura.tirar_moldura(binarize(_folha(faixa=True)))[1], 0)

    def test_a_tabela_que_atravessa_a_folha_nao_e_moldura(self) -> None:
        """Larga, e não alta: cobre uma direção só."""
        imagem = _folha()
        imagem[200:210, :] = 0
        self.assertEqual(moldura.tirar_moldura(binarize(imagem))[1], 0)

    def test_o_fio_vertical_entre_as_colunas_nao_e_moldura(self) -> None:
        imagem = _folha()
        imagem[:, 500:503] = 0
        self.assertEqual(moldura.tirar_moldura(binarize(imagem))[1], 0)

    def test_o_diagrama_de_folha_inteira_com_margem_nao_e_moldura(self) -> None:
        imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        cv2.rectangle(imagem, (120, 120), (880, 1280), (0, 0, 0), 4)
        self.assertEqual(moldura.tirar_moldura(binarize(imagem))[1], 0)

    def test_o_scan_que_nao_fecha_na_ultima_fileira_ainda_e_moldura(self) -> None:
        imagem = _folha()
        cv2.rectangle(imagem, (0, 0), (960, 1340), (40, 40, 40), 3)
        self.assertEqual(moldura.tirar_moldura(binarize(imagem))[1], 1)

    def test_a_folha_vazia_nao_quebra(self) -> None:
        self.assertEqual(moldura.tirar_moldura(np.zeros((0, 0), dtype=np.uint8))[1], 0)


if __name__ == "__main__":
    unittest.main()
