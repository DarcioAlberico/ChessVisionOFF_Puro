"""A calha, e a letra do cabeçalho que a apagava (S-190 e S-191).

**O teste que dá nome a este arquivo é `test_o_cabecalho_nao_apaga_a_calha`.** Era um `OR` — a
projeção marcava o x como ocupado se **qualquer** box caísse nele —, e o cabeçalho corrente
centralizado pousa em cima da calha. Um único box derrubava a calha da página inteira, e o
sintoma era errático porque a variável é onde a letra do cabeçalho calha de cair.

Os fixtures são geométricos: uma página de duas colunas é uma grade de caixas, e é tudo o que a
projeção olha. Nada aqui precisa de imagem.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.colunas import (
    CALHA_EM_CARACTERES,
    COLUNA_MINIMA,
    LINHAS_NA_CALHA,
    LINHAS_PARA_TOLERAR,
    atravessa,
    atribuir_coluna,
    calha,
    detectar_colunas,
)

LARGURA_DA_LETRA = 14
ALTURA_DA_LETRA = 20
PASSO_X = 18
PASSO_Y = 34

ESQUERDA = 40
"""Onde começa a coluna da esquerda."""

DIREITA = 460
"""Onde começa a coluna da direita. A calha fica entre ~350 e 460, ~110 px."""

POR_LINHA = 17
"""Caixas por linha em cada coluna: 17 x 18 px = 306 px de coluna."""


def _linha_de_caixas(x0: int, y: int, quantas: int = POR_LINHA) -> list[Caixa]:
    return [Caixa(x0 + i * PASSO_X, y, x0 + i * PASSO_X + LARGURA_DA_LETRA, y + ALTURA_DA_LETRA) for i in range(quantas)]


def duas_colunas(linhas: int = 30) -> list[Caixa]:
    """Uma página de duas colunas com uma calha larga entre elas."""
    caixas: list[Caixa] = []
    for i in range(linhas):
        y = 120 + i * PASSO_Y
        caixas.extend(_linha_de_caixas(ESQUERDA, y))
        caixas.extend(_linha_de_caixas(DIREITA, y))
    return caixas


def uma_coluna(linhas: int = 30) -> list[Caixa]:
    """Coluna única, larga, com espaço entre palavras em `x` diferente a cada linha.

    **O deslocamento é o item**: numa coluna única de verdade o espaço entre palavras cai num x
    diferente a cada linha, e nenhum x central sobrevive à projeção. Um fixture com o espaço
    sempre no mesmo lugar não é uma coluna única, é duas colunas.
    """
    caixas: list[Caixa] = []
    for i in range(linhas):
        y = 120 + i * PASSO_Y
        largura_total = 2 * POR_LINHA + 1
        buraco = 5 + (i * 3) % (largura_total - 8)
        for j in range(largura_total):
            if j == buraco:
                continue
            x = ESQUERDA + j * PASSO_X
            caixas.append(Caixa(x, y, x + LARGURA_DA_LETRA, y + ALTURA_DA_LETRA))
    return caixas


class CalhaTests(unittest.TestCase):
    def test_a_calha_sai_no_lugar_na_pagina_de_duas_colunas(self) -> None:
        achadas = calha(duas_colunas())
        self.assertEqual(1, len(achadas), f"saíram {achadas}")
        inicio, fim = achadas[0]
        fim_da_esquerda = ESQUERDA + (POR_LINHA - 1) * PASSO_X + LARGURA_DA_LETRA
        self.assertLessEqual(abs(inicio - fim_da_esquerda), PASSO_X)
        self.assertLessEqual(abs(fim - DIREITA), PASSO_X)

    def test_coluna_unica_nao_inventa_calha(self) -> None:
        self.assertEqual([], calha(uma_coluna()))
        self.assertEqual(1, len(detectar_colunas(uma_coluna())))

    def test_sem_caixa_nenhuma_nao_ha_calha_nem_coluna(self) -> None:
        self.assertEqual([], calha([]))
        self.assertEqual([], detectar_colunas([]))

    def test_o_vao_que_encosta_na_margem_esquerda_nao_e_calha(self) -> None:
        """Abrir faixa ali deixaria os boxes da margem fora de toda coluna.

        Com o `OR` ele não tinha como existir — algum box começa em `x_min` por definição —, mas
        a tolerância o cria na página em que só o cabeçalho alcança a margem.
        """
        caixas = duas_colunas()
        # Uma única linha bem à esquerda de tudo: ela define o `x_min` e deixa um vão até o resto.
        caixas.extend(_linha_de_caixas(0, 100, quantas=1))
        achadas = calha(caixas)
        self.assertTrue(all(inicio > 0 for inicio, _ in achadas), f"calha na margem: {achadas}")


class CabecalhoTests(unittest.TestCase):
    """S-191. A causa não era o limiar, era o `OR`."""

    @staticmethod
    def _atravessa_a_calha(y: int) -> Caixa:
        """Uma caixa de cabeçalho que cobre a calha quase inteira.

        **A largura é o item.** No Nunn, o box de 25x27 do cabeçalho derruba a calha de 31 px
        para 7 -- ela não some, fica **estreita demais para qualificar**. Uma caixa estreita no
        meio de uma calha larga deixaria dois pedaços grandes de cada lado e passaria mesmo com
        o `OR`, e o teste não distinguiria nada.
        """
        inicio = ESQUERDA + (POR_LINHA - 1) * PASSO_X + LARGURA_DA_LETRA
        return Caixa(inicio + 7, y, DIREITA - 7, y + 27)

    def test_o_cabecalho_nao_apaga_a_calha(self) -> None:
        """Uma linha atravessando a calha derrubava a página inteira para coluna única.

        Com o `OR`, o que sobra dos dois lados do cabeçalho é estreito demais para ser calha, e a
        página sai com as duas colunas intercaladas. Contando linhas, o cabeçalho é **uma** e
        passa pela tolerância.
        """
        com_cabecalho = [*duas_colunas(), self._atravessa_a_calha(60)]
        self.assertEqual(1, len(calha(com_cabecalho)), "o cabeçalho apagou a calha")
        self.assertEqual(2, len(detectar_colunas(com_cabecalho)))

    def test_o_criterio_conta_linhas_e_nao_boxes(self) -> None:
        """O par que trava a regra: **uma** linha passa, **duas** não.

        Com um `OR` sobre boxes as duas asserções seriam iguais -- uma linha já mataria a calha.
        Com a contagem de linhas e `LINHAS_NA_CALHA = 1`, elas se separam, e é essa separação que
        prova que a projeção conta o que deve.
        """
        self.assertEqual(LINHAS_NA_CALHA, 1, "a tolerância mudou; refazer este teste")
        uma = [*duas_colunas(), self._atravessa_a_calha(60)]
        duas = [*duas_colunas(), self._atravessa_a_calha(60), self._atravessa_a_calha(94)]

        self.assertEqual(1, len(calha(uma)))
        self.assertEqual([], calha(duas), "duas linhas cruzando deveriam matar a calha")

    def test_a_tolerancia_so_vale_em_pagina_com_linhas_de_sobra(self) -> None:
        """**Uma linha de cinco é 20% da página, e aí a tolerância inventa calha.**

        Medido no projeto de origem num recorte de cinco linhas: tolerar uma abre uma terceira
        faixa onde a contagem mínima é 1 — o vão entre duas palavras que calham de se alinhar.
        """
        curta = uma_coluna(linhas=5)
        self.assertLess(5, LINHAS_PARA_TOLERAR, "o fixture deixou de estar abaixo do limiar")
        self.assertEqual([], calha(curta), "a tolerância criou calha numa página de cinco linhas")


class FaixaEstreitaTests(unittest.TestCase):
    def test_a_faixa_estreita_e_fundida_e_nao_descartada(self) -> None:
        """O sumário: número do capítulo, título, número da página.

        Sem o piso, ele vira três colunas e o livro sai com dez números, dez títulos e dez páginas
        em vez de dez linhas. Medido lá: a "coluna" de número de capítulo tem 2% da largura do
        texto e a de número de página 4%, contra 48% de cada coluna de verdade.
        """
        caixas: list[Caixa] = []
        for i in range(20):
            y = 100 + i * PASSO_Y
            caixas.append(Caixa(20, y, 20 + LARGURA_DA_LETRA, y + ALTURA_DA_LETRA))  # o número
            caixas.extend(_linha_de_caixas(200, y, quantas=20))  # o título
            caixas.append(Caixa(900, y, 900 + LARGURA_DA_LETRA, y + ALTURA_DA_LETRA))  # a página
        colunas = detectar_colunas(caixas)
        self.assertLess(len(colunas), 3, f"o sumário virou {len(colunas)} colunas")

    def test_nenhuma_caixa_fica_fora_de_toda_coluna(self) -> None:
        """É o que a fusão garante: uma faixa a menos seria boxes lidos no fim da página."""
        caixas = duas_colunas()
        colunas = detectar_colunas(caixas)
        for caixa in caixas:
            self.assertIn(atribuir_coluna(caixa, colunas), range(len(colunas)))

    def test_o_piso_de_coluna_esta_no_vao_medido(self) -> None:
        self.assertGreater(COLUNA_MINIMA, 0.04, "abaixo da maior falsa coluna medida")
        self.assertLess(COLUNA_MINIMA, 0.45, "acima da menor coluna de verdade medida")

    def test_o_limiar_da_calha_esta_no_vao_medido(self) -> None:
        self.assertLess(CALHA_EM_CARACTERES, 1.0, "acima da menor calha de verdade medida")
        self.assertGreater(CALHA_EM_CARACTERES, 0.75, "abaixo do maior vão que não é calha")


class AtribuicaoTests(unittest.TestCase):
    def test_quem_cai_na_calha_fica_com_a_faixa_mais_proxima(self) -> None:
        """**E não no fim da página**, que é onde ele ia parar antes da F70.

        Com a calha de verdade — 56 px no Nunn — quem mora ali é o caractere central do cabeçalho
        corrente, o mesmo que apagava a calha.
        """
        colunas = [(0, 300), (400, 700)]
        na_calha_perto_da_esquerda = Caixa(320, 0, 340, 20)
        na_calha_perto_da_direita = Caixa(370, 0, 390, 20)
        self.assertEqual(0, atribuir_coluna(na_calha_perto_da_esquerda, colunas))
        self.assertEqual(1, atribuir_coluna(na_calha_perto_da_direita, colunas))

    def test_sem_coluna_declarada_tudo_e_da_primeira(self) -> None:
        self.assertEqual(0, atribuir_coluna(Caixa(0, 0, 10, 10), []))

    def test_o_que_atravessa_a_calha_e_reconhecido(self) -> None:
        colunas = [(0, 300), (400, 700)]
        self.assertTrue(atravessa(Caixa(100, 0, 600, 40), colunas))
        self.assertFalse(atravessa(Caixa(100, 0, 200, 40), colunas))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
