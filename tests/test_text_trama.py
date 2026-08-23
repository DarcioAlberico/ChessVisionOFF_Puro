"""O bloco que engoliu o texto: trama de meio-tom e tabela (S-196).

**A tolerância de quadrado custou uma fase inteira no projeto de origem.** Ela estava em 1,5,
"no meio do vão de propósito", com a observação de que nada no material caía entre 1,3 e 2,6.
Caía: a tabela de finais do Nunn mede 1342x1099, razão **1,22**. Moldura fechada,
`RETR_EXTERNAL`, e as 276 caixas de dentro dela sumiam do livro sem aviso nenhum -- não saíam
fora de ordem, **não saíam**.
"""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.trama import (
    MAX_GLIFOS,
    TOLERANCIA_QUADRADO,
    abrir_blocos,
    binarizar_bloco,
    candidatos,
    e_quadrado,
    glifos_do_bloco,
    ler_bloco,
    parece_texto,
)

ESCALA = 20


def painel_com_trama(*, largura: int = 400, altura: int = 150, passo: int = 3) -> tuple[np.ndarray, Caixa]:
    """Um quadro de pontuação: painel chapado com texto, devolvido pelo scan como nuvem de pontos.

    A proporção é 2,67 -- a mesma do painel medido no projeto de origem (1049x390).
    """
    pagina = np.full((altura + 100, largura + 100), 245, dtype=np.uint8)
    painel = pagina[50 : 50 + altura, 50 : 50 + largura]
    painel[:] = 200
    painel[::passo, ::passo] = 99  # a trama
    for i, texto in enumerate(("Maximum points 22", "Your score 19", "Excellent")):
        cv2.putText(pagina, texto, (60, 85 + i * 40), 0, 0.7, 5, 2, cv2.LINE_AA)
    return pagina, Caixa(50, 50, 50 + largura, 50 + altura)


def tabela_do_nunn() -> tuple[np.ndarray, Caixa]:
    """Um bloco de razão 1,22: **mais alto que largo**, e é o caso que a régua antiga perdia."""
    largura, altura = 320, 390
    pagina = np.full((altura + 100, largura + 100), 245, dtype=np.uint8)
    cv2.rectangle(pagina, (50, 50), (50 + largura, 50 + altura), 20, 3)
    for i in range(6):
        cv2.putText(pagina, f"linha {i} da tabela", (62, 90 + i * 60), 0, 0.55, 20, 2, cv2.LINE_AA)
    return pagina, Caixa(50, 50, 50 + largura, 50 + altura)


class QuadradoTests(unittest.TestCase):
    def test_o_tabuleiro_e_quadrado_e_nao_e_aberto(self) -> None:
        """Ler dentro dele daria uma caixa por peça. Medido: os diagramas medem 578x579,
        579x579, 580x584 -- proporção 1,00 a 1,01."""
        for largura, altura in ((578, 579), (579, 579), (580, 584)):
            with self.subTest(forma=(largura, altura)):
                caixa = Caixa(0, 0, largura, altura)
                self.assertTrue(e_quadrado(caixa))
                self.assertEqual([], candidatos([caixa], escala=ESCALA))

    def test_a_tabela_de_razao_1_22_e_aberta(self) -> None:
        """**O caso que a régua de 1,5 tinha exatamente no vão.**

        E a régua deixa de ser "mais largo que alto": esta tabela é mais **alta** que larga, e a
        versão anterior nem olhava para esse lado.
        """
        caixa = Caixa(0, 0, 1099, 1342)
        self.assertAlmostEqual(1.22, caixa.altura / caixa.largura, places=2)
        self.assertFalse(e_quadrado(caixa))
        self.assertEqual([caixa], candidatos([caixa], escala=ESCALA))

    def test_o_painel_de_pontuacao_e_aberto(self) -> None:
        """1049x390, proporção 2,69 -- bem longe do quadrado."""
        caixa = Caixa(0, 0, 1049, 390)
        self.assertFalse(e_quadrado(caixa))
        self.assertEqual([caixa], candidatos([caixa], escala=ESCALA))

    def test_a_tolerancia_esta_no_vao_medido(self) -> None:
        self.assertGreater(TOLERANCIA_QUADRADO, 1.01, "abaixo da maior razão de diagrama medida")
        self.assertLess(TOLERANCIA_QUADRADO, 1.22, "acima da razão da tabela do Nunn")

    def test_o_bloco_pequeno_nao_e_candidato(self) -> None:
        """Abaixo de quatro escalas nos dois eixos é palavra grande, não painel."""
        self.assertEqual([], candidatos([Caixa(0, 0, 200, 40)], escala=ESCALA))

    def test_escala_zero_nao_propoe_nada(self) -> None:
        self.assertEqual([], candidatos([Caixa(0, 0, 1000, 300)], escala=0))


class RebinarizacaoTests(unittest.TestCase):
    """**Rebinarizar o recorte é o que desfaz a solda.**"""

    def test_o_painel_com_trama_devolve_os_caracteres(self) -> None:
        """Na página inteira o papel domina e o Otsu global corta abaixo da trama, que vira tinta
        e gruda em tudo. Dentro do painel o papel some da conta e o corte sobe."""
        pagina, bloco = painel_com_trama()
        glifos = ler_bloco(pagina, bloco, escala=ESCALA)
        assert glifos is not None
        self.assertGreater(len(glifos), 10, f"saíram {len(glifos)} glifos")

    def test_a_moldura_reaparece_dentro_do_proprio_recorte(self) -> None:
        """Recortar o bloco pelo retângulo dele traz a borda junto, e ali ela é o contorno
        externo de novo. Medido no projeto de origem: 0 glifos com a borda dentro, 12 sem ela."""
        pagina, bloco = tabela_do_nunn()
        com_margem = glifos_do_bloco(pagina, bloco, escala=ESCALA)
        self.assertGreater(len(com_margem), 5, "a margem não tirou a moldura")

    def test_o_limiar_e_o_do_bloco_e_nao_o_da_pagina(self) -> None:
        pagina, bloco = painel_com_trama()
        binaria = binarizar_bloco(pagina, bloco, escala=ESCALA)
        self.assertGreater(binaria.size, 0)
        self.assertEqual({0, 255}, set(np.unique(binaria)))

    def test_bloco_menor_que_a_margem_devolve_vazio_e_nao_outro_pedaco_da_pagina(self) -> None:
        """**O `numpy` fatia a partir do fim quando o índice fica negativo.**

        Com `y2 - margem` negativo, o recorte sai de **outro lugar da imagem** em vez de sair
        vazio -- e o sintoma seriam glifos com coordenadas plausíveis vindos de onde ninguém
        olhou. Achado ao escrever este teste, em 2026-08-22.
        """
        vazia = np.zeros((10, 10), dtype=np.uint8)
        minusculo = Caixa(2, 2, 4, 4)
        self.assertEqual(0, binarizar_bloco(vazia, minusculo, escala=ESCALA).size)
        self.assertEqual([], glifos_do_bloco(vazia, minusculo, escala=ESCALA))


class PeneiraTests(unittest.TestCase):
    def test_a_fotografia_nao_vira_quarenta_mil_glifos(self) -> None:
        """**A página que é uma fotografia tem escala de texto degenerada.**

        Medida a capa do *Chess Evolution 1*, a escala devolve 2 px -- não há texto na página
        para pesar --, e com ela a faixa de altura aceita qualquer grão: o bloco rende 40.382
        "glifos" e a página sai de 1 caixa para 40 mil.
        """
        muitos = [Caixa(i, 0, i + 2, 3) for i in range(MAX_GLIFOS + 500)]
        self.assertFalse(parece_texto(muitos, escala=2))

    def test_poucos_glifos_nao_bastam_para_decidir(self) -> None:
        self.assertFalse(parece_texto([Caixa(0, 0, 10, 20), Caixa(20, 0, 30, 20)], escala=ESCALA))

    def test_tres_glifos_bastam(self) -> None:
        """Para **decidir**, um punhado basta -- é o mesmo mínimo da tarja, e pelo mesmo motivo."""
        tres = [Caixa(i * 20, 0, i * 20 + 10, 20) for i in range(3)]
        self.assertTrue(parece_texto(tres, escala=ESCALA))


class AbrirTests(unittest.TestCase):
    def test_o_bloco_de_texto_e_trocado_pelos_caracteres(self) -> None:
        pagina, bloco = painel_com_trama()
        outra = Caixa(10, 10, 24, 30)
        saida, blocos = abrir_blocos(pagina, [bloco, outra], escala=ESCALA)
        self.assertEqual([bloco], blocos)
        self.assertNotIn(bloco, saida)
        self.assertIn(outra, saida)

    def test_a_saida_sai_ordenada(self) -> None:
        pagina, bloco = painel_com_trama()
        saida, _ = abrir_blocos(pagina, [bloco], escala=ESCALA)
        chaves = [(c.y1, c.x1) for c in saida]
        self.assertEqual(sorted(chaves), chaves)

    def test_sem_bloco_nenhum_a_lista_nao_muda(self) -> None:
        caixas = [Caixa(10, 10, 24, 30)]
        saida, blocos = abrir_blocos(np.zeros((100, 100), dtype=np.uint8), caixas, escala=ESCALA)
        self.assertEqual(caixas, saida)
        self.assertEqual([], blocos)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
