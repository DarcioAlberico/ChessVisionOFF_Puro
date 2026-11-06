"""A caixa da altura da folha não intercala as linhas da coluna (S-712). Folhas desenhadas: nenhum livro comercial."""

from __future__ import annotations

import statistics
import unittest
from unittest import mock

import cv2
import numpy as np

from chess_diagram_ocr.text import gigantes, leitor, linhas
from chess_diagram_ocr.text.boxes import Caixa

TEXTOS = (
    "the white knight wins a pawn",
    "black answers with a quiet move",
    "a rook on the open file decides",
    "after the exchange nothing is left",
    "both sides keep their bishops here",
)
"""Linhas diferentes: as iguais alinham os vãos entre as palavras, e a folha vira cinco colunas."""


def _linha(imagem: np.ndarray, n: int, y: int) -> None:
    cv2.putText(imagem, TEXTOS[n % 5], (220, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)


def _folha(*, faixa: bool = False, fio: bool = False, n_linhas: int = 20) -> np.ndarray:
    """Coluna única de texto; a faixa é a lateral sólida, sem nada que feche a volta da folha."""
    imagem = np.full((1400, 1000, 3), 255, dtype=np.uint8)
    for n in range(n_linhas):
        _linha(imagem, n, 80 + 56 * n)
    if faixa:
        imagem[:, :160] = 40
    if fio:
        imagem[40:1360, 190:193] = 0
    return imagem


def _linhas(imagem: np.ndarray) -> list[list[Caixa]]:
    _, _, _, caixas, regioes = leitor.segmentar(imagem)
    saida: list[list[Caixa]] = []
    for _regiao, _coluna, desta in leitor._tiras(caixas, regioes):
        saida.extend(linhas.quebrar_em_linhas(linhas.ordem_em_faixa(desta)))
    return saida


def _alturas(grupos: list[list[Caixa]]) -> list[float]:
    return [linhas.envolve(g)[3] - linhas.envolve(g)[1] for g in grupos]


class MecanismoTests(unittest.TestCase):
    """As folhas 279 e 578 do *Chess Evolution*, reproduzidas: a faixa abre a banda, e a banda engole a coluna."""

    def test_sem_o_conserto_a_faixa_intercala(self) -> None:
        with mock.patch.object(gigantes, "TIRAR_GIGANTES", False):
            alturas = _alturas(_linhas(_folha(faixa=True)))
        self.assertGreater(max(alturas), 1000, "o caso tem de reproduzir o defeito")

    def test_a_faixa_nao_chega_as_linhas(self) -> None:
        grupos = _linhas(_folha(faixa=True))
        self.assertEqual(len(grupos), 20)
        self.assertLess(max(_alturas(grupos)), 1.8 * statistics.median(_alturas(grupos)))

    def test_as_linhas_saem_iguais_as_da_folha_sem_faixa(self) -> None:
        """Uma caixa de folga por linha: a faixa escura muda um pouco a binária, e duas letras se tocam."""
        com_faixa = [len(g) for g in _linhas(_folha(faixa=True))]
        sem_faixa = [len(g) for g in _linhas(_folha())]
        self.assertEqual(len(com_faixa), len(sem_faixa))
        for a, b in zip(com_faixa, sem_faixa, strict=True):
            self.assertLessEqual(abs(a - b), 1)

    def test_o_fio_vertical_que_divide_a_folha_nao_intercala(self) -> None:
        grupos = _linhas(_folha(fio=True))
        self.assertEqual(len(grupos), 20)
        self.assertLess(max(_alturas(grupos)), 1.8 * statistics.median(_alturas(grupos)))


class QuadroTests(unittest.TestCase):
    """O quadro da S-583 é uma caixa alta e larga: ela é medida antes de sair, e a região continua sendo achada."""

    def _emoldurada(self) -> np.ndarray:
        imagem = _folha(n_linhas=6)
        for n in range(7):
            _linha(imagem, n, 500 + 56 * n)
        # Aberto em cima: fechado, o contorno externo engoliria as letras de dentro.
        imagem[470:900, 190:193] = 0
        imagem[470:900, 780:783] = 0
        imagem[897:900, 190:783] = 0
        return imagem

    def test_a_moldura_nao_vira_linha(self) -> None:
        grupos = _linhas(self._emoldurada())
        self.assertEqual(len(grupos), 13)

    def test_quem_mede_o_quadro_ainda_o_ve(self) -> None:
        with mock.patch.object(leitor._quadros, "molduras_nas_caixas", wraps=leitor._quadros.molduras_nas_caixas) as medir:
            leitor.segmentar(self._emoldurada())
        caixas = medir.call_args.args[0]
        self.assertTrue(any(c.altura > 400 for c in caixas), "a moldura tem de chegar a quem a mede")


class SemGigantesTests(unittest.TestCase):
    ESCALA = 20
    BINARIA = np.zeros((6000, 3000), dtype=np.uint8)

    def _caixa(self, altura: int, largura: int = 12) -> Caixa:
        return Caixa(100, 100, 100 + largura, 100 + altura)

    def test_a_folha_sem_gigante_devolve_a_mesma_lista(self) -> None:
        caixas = [self._caixa(20), self._caixa(26)]
        self.assertIs(gigantes.sem_gigantes(caixas, self.BINARIA, escala=self.ESCALA), caixas)

    def test_a_fronteira_da_altura(self) -> None:
        limite = int(gigantes.ALTURA_DE_GIGANTE * self.ESCALA)
        no_limite, acima = self._caixa(limite), self._caixa(limite + 1)
        self.assertEqual(gigantes.sem_gigantes([no_limite, acima], self.BINARIA, escala=self.ESCALA), [no_limite])

    def test_a_capitular_fica(self) -> None:
        """A inicial de três linhas é letra, e a régua não pode alcançá-la."""
        capitular = self._caixa(3 * self.ESCALA + 10, largura=3 * self.ESCALA)
        self.assertEqual(gigantes.sem_gigantes([capitular], self.BINARIA, escala=self.ESCALA), [capitular])

    def test_a_foto_abaixo_do_corte_sai_pela_tinta(self) -> None:
        binaria = np.zeros((400, 400), dtype=np.uint8)
        binaria[10:150, 10:170] = 255
        foto = Caixa(10, 10, 170, 150)
        self.assertEqual(gigantes.sem_gigantes([foto], binaria, escala=self.ESCALA), [])

    def test_a_letra_grande_tem_tinta_de_letra(self) -> None:
        binaria = np.zeros((400, 400), dtype=np.uint8)
        binaria[10:150, 10:60] = 255
        binaria[10:50, 10:170] = 255
        letra = Caixa(10, 10, 170, 150)
        self.assertEqual(gigantes.sem_gigantes([letra], binaria, escala=self.ESCALA), [letra])

    def test_sem_escala_nao_mexe(self) -> None:
        caixas = [self._caixa(5000)]
        self.assertIs(gigantes.sem_gigantes(caixas, self.BINARIA, escala=0), caixas)

    def test_a_constante_desliga(self) -> None:
        caixas = [self._caixa(5000)]
        with mock.patch.object(gigantes, "TIRAR_GIGANTES", False):
            self.assertIs(gigantes.sem_gigantes(caixas, self.BINARIA, escala=self.ESCALA), caixas)


if __name__ == "__main__":
    unittest.main()
