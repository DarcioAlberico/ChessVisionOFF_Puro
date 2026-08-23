"""A tabela sai como tabela (S-199).

**A falha que este item conserta é a que menos se percebe.** A tabela de finais da página 236 do
Nunn tem moldura fechada; com `RETR_EXTERNAL`, as 276 caixas de dentro dela não saíam fora de
ordem -- **não saíam**. Uma tabela ausente parece uma página sem tabela.
"""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.tabela import (
    MIN_CELULAS,
    desenhar_grade,
    grade,
    ler,
    moldura_fechada,
    ordem_na_celula,
)

LADO = 60


def com_grade(forma: tuple[int, int]) -> tuple[np.ndarray, Caixa]:
    grade_ = desenhar_grade(forma, lado=LADO)
    altura, largura = grade_.shape
    return grade_, Caixa(0, 0, largura, altura)


def caixa_na_celula(linha: int, coluna: int, *, dentro: int = 20) -> Caixa:
    x = coluna * LADO + dentro
    y = linha * LADO + dentro
    return Caixa(x, y, x + 12, y + 16)


class GradeTests(unittest.TestCase):
    def test_a_grade_vem_da_imagem(self) -> None:
        """E não de folga arbitrária: as linhas da moldura dão as fronteiras de célula."""
        imagem, bloco = com_grade((3, 5))
        horizontais, verticais = grade(imagem, bloco)
        self.assertEqual(4, len(horizontais), f"cortes horizontais: {horizontais}")
        self.assertEqual(6, len(verticais), f"cortes verticais: {verticais}")

    def test_a_moldura_de_tres_pixels_produz_um_corte_e_nao_tres(self) -> None:
        """`_fronteiras` devolve o **centro** de cada faixa contínua de tinta."""
        imagem, bloco = com_grade((2, 2))
        horizontais, _ = grade(imagem, bloco)
        self.assertEqual(sorted(set(horizontais)), horizontais)
        self.assertEqual(3, len(horizontais))

    def test_o_traco_curto_nao_e_fronteira_de_celula(self) -> None:
        """Sublinhado de célula, traço de conteúdo e quebra de scan não abrem coluna.

        Sem isso a tabela sai com dezenas de colunas de um caractere.
        """
        imagem, bloco = com_grade((3, 3))
        cv2.line(imagem, (10, 30), (40, 30), 255, 3)  # um traço de 30 px numa grade de 180
        horizontais, _ = grade(imagem, bloco)
        self.assertEqual(4, len(horizontais), "o traço curto virou fronteira")

    def test_bloco_vazio_nao_tem_grade(self) -> None:
        self.assertEqual(([], []), grade(np.zeros((10, 10), dtype=np.uint8), Caixa(5, 5, 5, 5)))


class LeituraTests(unittest.TestCase):
    def test_a_tabela_sai_com_a_forma_certa(self) -> None:
        imagem, bloco = com_grade((3, 5))
        tabela = ler(imagem, bloco)
        assert tabela is not None
        self.assertEqual((3, 5), tabela.forma)
        self.assertEqual(15, len(tabela.celulas))

    def test_cada_caixa_vai_para_a_celula_que_contem_o_centro_dela(self) -> None:
        imagem, bloco = com_grade((3, 3))
        caixas = [caixa_na_celula(1, 2), caixa_na_celula(0, 0)]
        tabela = ler(imagem, bloco, caixas)
        assert tabela is not None

        celula = tabela.celula(1, 2)
        assert celula is not None
        self.assertEqual((caixas[0],), celula.caixas)

    def test_a_celula_vazia_sai_vazia_e_nao_desloca_as_seguintes(self) -> None:
        """Uma célula vazia que sumisse faria todas as seguintes andarem uma casa."""
        imagem, bloco = com_grade((2, 3))
        tabela = ler(imagem, bloco, [caixa_na_celula(0, 2)])
        assert tabela is not None
        self.assertEqual((2, 3), tabela.forma)

        vazia = tabela.celula(0, 0)
        assert vazia is not None
        self.assertEqual((), vazia.caixas)

        cheia = tabela.celula(0, 2)
        assert cheia is not None
        self.assertEqual(1, len(cheia.caixas))

    def test_o_bloco_sem_grade_nao_e_tabela(self) -> None:
        imagem = np.zeros((200, 300), dtype=np.uint8)
        cv2.putText(imagem, "so texto", (20, 100), 0, 1.0, 255, 2, cv2.LINE_AA)
        self.assertIsNone(ler(imagem, Caixa(0, 0, 300, 200)))

    def test_uma_celula_por_eixo_nao_e_tabela(self) -> None:
        """Menos que o mínimo num eixo é um bloco com uma borda, não uma tabela."""
        imagem, bloco = com_grade((1, 1))
        self.assertLess(1, MIN_CELULAS)
        self.assertIsNone(ler(imagem, bloco))

    def test_a_celula_e_localizavel_por_linha_e_coluna(self) -> None:
        imagem, bloco = com_grade((2, 2))
        tabela = ler(imagem, bloco)
        assert tabela is not None
        self.assertIsNotNone(tabela.celula(1, 1))
        self.assertIsNone(tabela.celula(9, 9))


class OrdemTests(unittest.TestCase):
    def test_dentro_da_celula_nao_se_le_como_se_le_a_pagina(self) -> None:
        """A célula tem a própria escala e a própria margem.

        Usar a banda da página inteira juntaria a célula da esquerda com a da direita -- o mesmo
        defeito da coluna um nível acima.
        """
        imagem, bloco = com_grade((2, 2))
        esquerda = caixa_na_celula(0, 0)
        direita = caixa_na_celula(0, 1)
        tabela = ler(imagem, bloco, [direita, esquerda])
        assert tabela is not None

        celula = tabela.celula(0, 0)
        assert celula is not None
        self.assertEqual([esquerda], ordem_na_celula(celula))

    def test_a_celula_vazia_ordena_para_nada(self) -> None:
        imagem, bloco = com_grade((2, 2))
        tabela = ler(imagem, bloco)
        assert tabela is not None
        celula = tabela.celula(0, 0)
        assert celula is not None
        self.assertEqual([], ordem_na_celula(celula))


class MolduraTests(unittest.TestCase):
    def test_a_moldura_fechada_e_reconhecida(self) -> None:
        imagem, bloco = com_grade((3, 3))
        self.assertTrue(moldura_fechada(imagem, bloco))

    def test_a_tabela_sem_moldura_e_limite_conhecido(self) -> None:
        """**Declarado em vez de heurística frágil.**

        Achá-la exigiria inferir colunas de espaços em branco dentro de um bloco, e o falso
        positivo dessa inferência é uma lista de duas colunas virando tabela.
        """
        imagem = np.zeros((200, 300), dtype=np.uint8)
        for linha in range(4):
            for coluna in range(3):
                cv2.rectangle(imagem, (20 + coluna * 90, 20 + linha * 40), (60 + coluna * 90, 45 + linha * 40), 255, -1)
        bloco = Caixa(0, 0, 300, 200)
        self.assertFalse(moldura_fechada(imagem, bloco))
        self.assertIsNone(ler(imagem, bloco))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
