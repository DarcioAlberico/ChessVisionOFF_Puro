"""Texto impresso na vertical (S-197).

**É o caso mais perigoso da Fase 28**, e o motivo não é a frequência: os outros quatro fazem o
texto sumir, e este faz o programa devolver **outra letra com confiança de leitura normal**.
Medido no projeto de origem em 10.606 caracteres: 94,2% de pé contra 8,4% no mesmo recorte girado.

O árbitro é injetado, e os testes usam árbitros travados -- é a única forma de afirmar *por que*
uma pilha foi aceita. `test_sem_arbitro_nada_muda` é o que trava a regra principal.
"""

from __future__ import annotations

import unittest
from collections.abc import Sequence

import numpy as np

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.vertical import (
    ANGULOS,
    COM_VIZINHO_LATERAL,
    MARGEM,
    MIN_ITENS,
    candidatos,
    confianca_media,
    decidir_angulo,
    endireitar,
    girar,
    marcar,
    recorte_de_pe,
)

LADO = 18
PASSO = 22


def pilha(*, x: int = 300, topo: int = 100, quantas: int = 8) -> list[Caixa]:
    """Uma coluna de caixas de tamanho de caractere, encostadas e alinhadas em `x`."""
    return [Caixa(x, topo + i * PASSO, x + LADO, topo + i * PASSO + LADO) for i in range(quantas)]


def linha_horizontal(*, y: int, x0: int = 40, quantas: int = 12) -> list[Caixa]:
    return [Caixa(x0 + i * PASSO, y, x0 + i * PASSO + LADO, y + LADO) for i in range(quantas)]


def pilha_girada(*, x: int = 300, topo: int = 100, quantas: int = 8) -> list[Caixa]:
    """Uma pilha de letras **deitadas**: cada caixa é mais larga que alta.

    **É a forma que uma letra girada tem na página**, e é o que distingue este fixture do
    `pilha`: uma letra comum é mais alta que larga, e girada 90° a caixa dela na página fica mais
    larga que alta. O primeiro fixture que escrevi usava forma de letra em pé, e por isso o
    árbitro respondia -- corretamente -- que a pilha já estava de pé.
    """
    largura, altura, passo = 18, 8, 12
    return [Caixa(x, topo + i * passo, x + largura, topo + i * passo + altura) for i in range(quantas)]


def _arbitro_fixo(valor: float) -> object:
    def arbitro(recortes: Sequence[np.ndarray]) -> list[float]:
        return [valor] * len(recortes)

    return arbitro


def _arbitro_por_forma(alto: float, baixo: float) -> object:
    """Confia alto quando o recorte é mais alto que largo. Simula "o glifo está de pé"."""

    def arbitro(recortes: Sequence[np.ndarray]) -> list[float]:
        return [alto if r.shape[0] >= r.shape[1] else baixo for r in recortes]

    return arbitro


class GiroTests(unittest.TestCase):
    def test_endireitar_e_transposicao_e_a_volta_fecha(self) -> None:
        """**Girar por múltiplo de 90° é transposição, não reamostragem.**

        Medido no projeto de origem: os mesmos 9.987 caracteres que o modelo acerta de pé voltam
        a ser acertados depois de ir e voltar, um a um.
        """
        recorte = np.arange(24, dtype=np.uint8).reshape(4, 6)
        for angulo in ANGULOS:
            with self.subTest(angulo=angulo):
                ida = endireitar(recorte, angulo)
                volta = endireitar(ida, 360 - angulo)
                np.testing.assert_array_equal(recorte, volta)

    def test_o_recorte_devolvido_e_contiguo(self) -> None:
        """`np.rot90` devolve uma vista de passo negativo, e o OpenCV recusa isso adiante."""
        for angulo in ANGULOS:
            with self.subTest(angulo=angulo):
                girado = endireitar(np.zeros((4, 6), dtype=np.uint8), angulo)
                self.assertTrue(girado.flags["C_CONTIGUOUS"])

    def test_angulo_zero_nao_toca_no_recorte(self) -> None:
        recorte = np.zeros((4, 6), dtype=np.uint8)
        self.assertIs(recorte, endireitar(recorte, 0))

    def test_recorte_de_pe_e_o_funil_da_volta(self) -> None:
        imagem = np.arange(100 * 100, dtype=np.uint32).astype(np.uint8).reshape(100, 100)
        de_pe = recorte_de_pe(imagem, Caixa(10, 10, 30, 40, 0))
        girado = recorte_de_pe(imagem, Caixa(10, 10, 30, 40, 90))
        self.assertEqual((30, 20), de_pe.shape)
        self.assertEqual((20, 30), girado.shape)


class SimulacaoTests(unittest.TestCase):
    """`girar` é o avesso de `endireitar`, e é o que torna a tabela dos quatro ângulos possível.

    O acervo é de texto de pé. Sem simulação, medir a S-197 exigiria anotar rótulos girados à
    mão -- dezenas de amostras para uma régua que separa 94,2% de 8,4%.
    """

    def test_o_glifo_girado_e_o_mesmo_glifo_depois_de_endireitado(self) -> None:
        """A ida e a volta fecham **byte a byte**: é transposição dos dois lados."""
        imagem = np.arange(40 * 60, dtype=np.uint32).astype(np.uint8).reshape(40, 60)
        caixa = Caixa(10, 5, 22, 19)
        esperado = caixa.recortar(imagem)

        for angulo in (0, 90, 180, 270):
            with self.subTest(angulo=angulo):
                virada, caixas = girar(imagem, [caixa], angulo)
                np.testing.assert_array_equal(esperado, endireitar(caixas[0].recortar(virada), angulo))

    def test_a_caixa_simulada_nao_ja_traz_a_resposta(self) -> None:
        """Em produção ninguém sabe o ângulo antes do classificador; a simulação também não pode."""
        _, caixas = girar(np.zeros((20, 30), dtype=np.uint8), [Caixa(1, 2, 5, 9, 90)], 270)
        self.assertEqual(0, caixas[0].angulo)

    def test_a_pagina_gira_junto_com_as_caixas(self) -> None:
        virada, _ = girar(np.zeros((20, 30), dtype=np.uint8), [], 90)
        self.assertEqual((30, 20), virada.shape)
        self.assertTrue(virada.flags["C_CONTIGUOUS"])


class GeometriaTests(unittest.TestCase):
    """**A geometria propõe**, e nada aqui afirma que a pilha é texto girado."""

    def test_a_pilha_encostada_e_candidata(self) -> None:
        self.assertEqual(1, len(candidatos(pilha())))

    def test_a_pilha_curta_demais_nao_e_candidata(self) -> None:
        """**Cinco, e o quinto foi comprado com medição.**

        Com quatro, 81 páginas sem texto vertical produzem 5 pilhas aceitas por engano -- e as
        cinco são colunas de peças dentro do diagrama. Uma coluna de quatro peças é alta,
        estreita, encostada e de vão zero: passa em toda a geometria.
        """
        self.assertEqual([], candidatos(pilha(quantas=MIN_ITENS - 1)))
        self.assertEqual(1, len(candidatos(pilha(quantas=MIN_ITENS))))

    def test_a_coluna_de_primeiras_letras_nao_e_pilha(self) -> None:
        """**A diferença é estrutural**: letra de linha horizontal tem vizinha ao lado; letra de
        linha vertical tem vizinha em cima e embaixo.

        Sem esta regra, a coluna das primeiras letras de linhas seguidas passa em toda a
        geometria -- ela é uma pilha alinhada e encostada como qualquer outra.
        """
        caixas: list[Caixa] = []
        for i in range(8):
            caixas.extend(linha_horizontal(y=100 + i * PASSO))
        propostas = candidatos(caixas)
        self.assertEqual([], propostas, f"{len(propostas)} pilha(s) numa página só de prosa")

    def test_a_pilha_larga_demais_nao_e_candidata(self) -> None:
        larga = [Caixa(300, 100 + i * PASSO, 300 + LADO * 4, 100 + i * PASSO + LADO) for i in range(8)]
        self.assertEqual([], candidatos(larga))

    def test_a_fracao_de_vizinho_lateral_esta_declarada(self) -> None:
        self.assertGreater(COM_VIZINHO_LATERAL, 0.0)
        self.assertLess(COM_VIZINHO_LATERAL, 1.0)


class ArbitroTests(unittest.TestCase):
    """**O classificador dispõe.** Sem ele este módulo não mexe em nada."""

    def setUp(self) -> None:
        self.imagem = np.zeros((400, 400), dtype=np.uint8)
        self.pilha = pilha()

    def test_sem_arbitro_nada_muda(self) -> None:
        """**Marcar ângulo por geometria pura mexeria em texto normal para acertar o raro.**

        É a lição de duas fases do projeto de origem: separar glifo colado sem classificador que
        confirmasse custou 2,3 pontos de F1.
        """
        self.assertEqual(0, decidir_angulo(self.imagem, self.pilha, None))
        self.assertEqual(self.pilha, marcar(self.imagem, self.pilha, None))

    def test_o_arbitro_indeciso_deixa_tudo_de_pe(self) -> None:
        """Confiança igual nos três ângulos: não há folga, e o vencedor é o texto de pé."""
        self.assertEqual(0, decidir_angulo(self.imagem, self.pilha, _arbitro_fixo(0.8)))

    def test_a_folga_precisa_superar_a_margem(self) -> None:
        """A mediana da folga medida é 0,074, e a margem é conservadora de propósito.

        **Na dúvida, não mexer** -- porque mexer em texto de pé para acertar o raro é o defeito
        que a fase evita.
        """
        deitada = pilha_girada()
        arbitro = _arbitro_por_forma(alto=0.9, baixo=0.9 - MARGEM / 2)
        self.assertEqual(0, decidir_angulo(self.imagem, deitada, arbitro), "aceitou com folga menor que a margem")

    def test_a_pilha_girada_e_aceita_quando_a_folga_e_grande(self) -> None:
        deitada = pilha_girada()
        arbitro = _arbitro_por_forma(alto=0.95, baixo=0.20)
        self.assertIn(decidir_angulo(self.imagem, deitada, arbitro), ANGULOS, "a pilha girada não foi aceita")

    def test_marcar_preenche_o_angulo_das_caixas_da_pilha(self) -> None:
        deitada = pilha_girada()
        marcadas = marcar(self.imagem, deitada, _arbitro_por_forma(alto=0.95, baixo=0.20))
        self.assertTrue(all(c.angulo in ANGULOS for c in marcadas), [c.angulo for c in marcadas])

    def test_a_pilha_de_letras_em_pe_continua_em_pe(self) -> None:
        """O controle do teste acima: uma pilha cujas caixas têm forma de letra em pé -- a coluna
        de primeiras letras de parágrafo -- não é girada por um árbitro que julga pela forma."""
        arbitro = _arbitro_por_forma(alto=0.95, baixo=0.20)
        self.assertEqual(0, decidir_angulo(self.imagem, pilha(), arbitro))

    def test_a_confianca_e_a_media_da_pilha_inteira(self) -> None:
        """E não a da primeira caixa: com quatro amostras a média já é ruído, com uma é chute."""
        self.assertAlmostEqual(0.7, confianca_media(self.imagem, self.pilha, 0, _arbitro_fixo(0.7)))

    def test_pilha_vazia_nao_levanta(self) -> None:
        self.assertEqual(0, decidir_angulo(self.imagem, [], _arbitro_fixo(0.9)))
        self.assertEqual(0.0, confianca_media(self.imagem, [], 0, _arbitro_fixo(0.9)))


class CentoEOitentaTests(unittest.TestCase):
    def test_180_nao_e_candidato(self) -> None:
        """**Livro impresso não traz linha de cabeça para baixo.**

        A medição mostra que o classificador *saberia* separar 180° (99,7% também); ele não entra
        por não existir no material, e não por não dar. Cada ângulo a mais é uma chance a mais de
        virar uma pilha curta pelo lado errado.
        """
        self.assertNotIn(180, ANGULOS)
        self.assertEqual((90, 270), ANGULOS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
