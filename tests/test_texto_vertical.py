"""A tabela dos quatro ângulos: quem entra na medição, e o que ela conta como acerto (S-197).

O giro, a simulação e a decisão de ângulo moravam em `text/vertical.py`, e vieram com o módulo para o
comando que os usa (S-855, D3 da solidez). O árbitro é injetado, e os testes usam árbitros travados.

O comando existe porque o item estava implementado e **sem número** -- a arbitragem do ângulo é
do classificador, e até 2026-08-23 não havia classificador nesta máquina. Aqui o árbitro é
travado, que é o que permite afirmar *por que* uma pilha foi aceita sem carregar 2,6 MB de pesos.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.cli.texto_vertical import (
    ANGULOS,
    ANGULOS_IMPRESSOS,
    MARGEM,
    Arbitro,
    confianca_media,
    decidir_angulo,
    endireitar,
    girar,
    linhas_de_texto,
    medir_linha,
)
from chess_diagram_ocr.text.boxes import Caixa


def _pagina_com_duas_linhas() -> np.ndarray:
    """Papel claro com dois renques de marcas escuras: um no topo, outro embaixo."""
    imagem = np.full((120, 200), 255, dtype=np.uint8)
    for y in (20, 90):
        for i in range(8):
            imagem[y : y + 14, 10 + i * 20 : 10 + i * 20 + 12] = 0
    return imagem


class PeneiraDaCamadaTests(unittest.TestCase):
    """A linha entra porque o PDF diz que ali há texto, e não porque o modelo gostou dela."""

    def test_a_linha_fora_da_camada_de_texto_nao_entra(self) -> None:
        """Escolher pela confiança do classificador mediria o classificador contra ele mesmo."""
        imagem = _pagina_com_duas_linhas()
        so_a_de_cima = [(0.0, 10.0, 200.0, 50.0)]

        linhas = linhas_de_texto(imagem, so_a_de_cima)

        self.assertEqual(1, len(linhas))
        self.assertTrue(all(c.y1 < 60 for c in linhas[0]))

    def test_sem_camada_nenhuma_linha_entra(self) -> None:
        self.assertEqual([], linhas_de_texto(_pagina_com_duas_linhas(), []))

    def test_pagina_em_branco_nao_levanta(self) -> None:
        self.assertEqual([], linhas_de_texto(np.full((50, 50), 255, dtype=np.uint8), [(0, 0, 50, 50)]))


class MedirLinhaTests(unittest.TestCase):
    """As duas réguas saem da mesma leitura, e elas discordam de propósito."""

    LINHA = [Caixa(10 + i * 20, 20, 22 + i * 20, 34) for i in range(6)]

    def test_o_arbitro_indiferente_nao_gira_nada(self) -> None:
        """`decidir_angulo` exige superar o de pé por `MARGEM`: na dúvida, não mexer."""
        medida = medir_linha(_pagina_com_duas_linhas(), self.LINHA, lambda recortes: [0.5] * len(recortes))

        self.assertEqual([0, 0, 0, 0], medida["producao"])
        self.assertEqual([0.0, 0.0, 0.0, 0.0], medida["folgas"])

    def test_a_matriz_tem_uma_fileira_por_angulo_impresso(self) -> None:
        medida = medir_linha(_pagina_com_duas_linhas(), self.LINHA, lambda r: [0.5] * len(r))

        self.assertEqual(len(ANGULOS_IMPRESSOS), len(medida["matriz"]))
        self.assertTrue(all(len(fileira) == len(ANGULOS_IMPRESSOS) for fileira in medida["matriz"]))

    def test_o_argmax_segue_o_arbitro_e_nao_a_geometria(self) -> None:
        """Árbitro que só gosta de recorte deitado: o argmax tem de acompanhá-lo, e não a pilha."""

        def so_gosta_de_deitado(recortes: list[np.ndarray]) -> list[float]:
            return [0.9 if r.shape[1] > r.shape[0] else 0.1 for r in recortes]

        medida = medir_linha(_pagina_com_duas_linhas(), self.LINHA, so_gosta_de_deitado)

        # A caixa é 12x14 (em pé). Lida a 90 ou 270 ela vira 14x12, que é o que este árbitro
        # premia -- então o vencedor de cada fileira nunca é o ângulo impresso.
        self.assertNotIn(0, medida["argmax"][:1])


LADO = 18
PASSO = 22


def pilha(*, x: int = 300, topo: int = 100, quantas: int = 8) -> list[Caixa]:
    """Uma coluna de caixas de tamanho de caractere, encostadas e alinhadas em `x`."""
    return [Caixa(x, topo + i * PASSO, x + LADO, topo + i * PASSO + LADO) for i in range(quantas)]


def pilha_girada(*, x: int = 300, topo: int = 100, quantas: int = 8) -> list[Caixa]:
    """Uma pilha de letras **deitadas**: cada caixa é mais larga que alta.

    **É a forma que uma letra girada tem na página**, e é o que distingue este fixture do
    `pilha`: uma letra comum é mais alta que larga, e girada 90° a caixa dela na página fica mais
    larga que alta. O primeiro fixture que escrevi usava forma de letra em pé, e por isso o
    árbitro respondia -- corretamente -- que a pilha já estava de pé.
    """
    largura, altura, passo = 18, 8, 12
    return [Caixa(x, topo + i * passo, x + largura, topo + i * passo + altura) for i in range(quantas)]


def _arbitro_fixo(valor: float) -> Arbitro:
    def arbitro(recortes: list[np.ndarray]) -> list[float]:
        return [valor] * len(recortes)

    return arbitro


def _arbitro_por_forma(alto: float, baixo: float) -> Arbitro:
    """Confia alto quando o recorte é mais alto que largo. Simula "o glifo está de pé"."""

    def arbitro(recortes: list[np.ndarray]) -> list[float]:
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

    def test_a_pagina_gira_junto_com_as_caixas(self) -> None:
        virada, _ = girar(np.zeros((20, 30), dtype=np.uint8), [], 90)
        self.assertEqual((30, 20), virada.shape)
        self.assertTrue(virada.flags["C_CONTIGUOUS"])


class ArbitroTests(unittest.TestCase):
    """**O classificador dispõe.** Sem ele `decidir_angulo` não mexe em nada."""

    def setUp(self) -> None:
        self.imagem = np.zeros((400, 400), dtype=np.uint8)
        self.pilha = pilha()

    def test_sem_arbitro_nada_muda(self) -> None:
        """**Marcar ângulo por geometria pura mexeria em texto normal para acertar o raro.**

        É a lição de duas fases do projeto de origem: separar glifo colado sem classificador que
        confirmasse custou 2,3 pontos de F1.
        """
        self.assertEqual(0, decidir_angulo(self.imagem, self.pilha, None))

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
