"""A escala do caractere e a peneira do glifo (S-185).

Os dois testes que dão nome a este arquivo são os que travam decisões que custaram uma versão
inteira no projeto de origem:

- `test_a_mediana_ponderada_sobrevive_a_trama` — a mediana simples desce para 1 px numa página
  com meio-tom, e todo limiar relativo do pipeline desaba junto;
- `test_a_regua_e_area_e_nao_altura` — cortar por altura derruba o ponto final, e o livro sai
  sem pontuação nenhuma.
"""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from chess_diagram_ocr.text.binarizacao import binarize
from chess_diagram_ocr.text.boxes import (
    CAIXA_CURTA,
    MIN_AREA_GLIFO,
    PROPORCAO_MAXIMA,
    Caixa,
    caixas_de_caractere,
    escala_de_texto,
    excluir_diagramas,
    unir_pingos,
)


def _pagina_de_texto(*, altura_da_fonte: float = 1.0) -> np.ndarray:
    img = np.full((300, 420), 245, dtype=np.uint8)
    for linha in range(4):
        cv2.putText(img, "Steinitz - Bird", (20, 50 + linha * 60), 0, altura_da_fonte, 20, 2, cv2.LINE_AA)
    return img


def _com_painel_de_trama(img: np.ndarray, *, passo: int = 3) -> np.ndarray:
    """O quadro de pontuação: um painel chapado que o escaneamento devolve como nuvem de pontos.

    **É um painel dentro da página, e não a página inteira**, porque é o que o livro tem -- o
    quadro que fecha o capítulo. Uma página que é *toda* trama derrota qualquer mediana, incluindo
    a ponderada, e não é o caso que a régua existe para atravessar.
    """
    saida = img.copy()
    painel = saida[170:290, 210:410]
    painel[::passo, ::passo] = 100
    return saida


class EscalaTests(unittest.TestCase):
    def test_a_escala_de_uma_pagina_de_texto_e_a_altura_da_letra(self) -> None:
        escala = escala_de_texto(binarize(_pagina_de_texto(), "otsu"))
        self.assertGreater(escala, 8)
        self.assertLess(escala, 40)

    def test_a_mediana_ponderada_sobrevive_a_trama(self) -> None:
        """**A mediana simples desce para 1 e leva o pipeline junto.**

        Medido no projeto de origem, a página 18 do *Chess Evolution 1*: 6.765 contornos, 95,8%
        deles de 6x6 px ou menos, mediana das alturas em 2 px. Com essa mediana, a régua de bloco
        joga fora tudo acima de 8 px -- isto é, os caracteres.

        A ponderação por área de tinta é estável porque o ponto de trama tem ~4 px de tinta e uma
        letra tem ~200.
        """
        binaria = binarize(_com_painel_de_trama(_pagina_de_texto()), "otsu")

        n, _, stats, _ = cv2.connectedComponentsWithStats(binaria, connectivity=8)
        simples = float(np.median(stats[1:, cv2.CC_STAT_HEIGHT])) if n > 1 else 0.0
        ponderada = escala_de_texto(binaria)

        self.assertLessEqual(simples, 3.0, "o fixture não reproduz o envenenamento da mediana")
        self.assertGreater(ponderada, 8, f"a ponderada desabou junto com a simples ({ponderada})")

    def test_a_ponderada_degrada_quando_a_trama_pesa_tanto_quanto_o_texto(self) -> None:
        """**O limite da régua, medido aqui e não herdado.**

        A ponderação por tinta funciona porque o texto pesa mais que a trama, não porque ela seja
        imune a ela. Medido neste fixture (página de 300x420 com 6.228 px de tinta de texto):

            passo da trama   componentes   tinta da trama   mediana simples   ponderada
                  4              1.516            1.517            1             17
                  3              2.666            2.681            1             17
                  2              5.877            6.055            1              5   <- paridade

        Aos 6.055 px de trama contra 6.228 de texto, a mediana ponderada cai de 17 para 5. Não é
        defeito a consertar aqui: é a fronteira do instrumento, e quem a atravessa é a S-196, que
        **apaga** a trama antes de medir em vez de tentar sobreviver a ela.
        """
        binaria = binarize(_com_painel_de_trama(_pagina_de_texto(), passo=2), "otsu")
        self.assertLess(escala_de_texto(binaria), 8, "a paridade deixou de degradar; refazer a tabela")

    def test_o_bloco_grande_fica_fora_da_conta(self) -> None:
        """Caractere não ocupa 1% de uma página, e sem esta exclusão a mediana aterrissa no bloco.

        Uma trama que soldou numa malha só é *um* componente com centenas de milhares de pixels
        de tinta -- e ela passaria a ser a mediana ponderada.
        """
        img = _pagina_de_texto()
        cv2.rectangle(img, (200, 180), (400, 290), 10, -1)
        escala = escala_de_texto(binarize(img, "otsu"))
        self.assertLess(escala, 100, f"a mediana aterrissou no bloco ({escala})")

    def test_pagina_sem_tinta_devolve_zero(self) -> None:
        self.assertEqual(0, escala_de_texto(np.zeros((80, 80), dtype=np.uint8)))
        self.assertEqual(0, escala_de_texto(np.zeros((0, 0), dtype=np.uint8)))


class PeneiraTests(unittest.TestCase):
    def test_a_regua_e_area_e_nao_altura(self) -> None:
        """**Cortar por altura derruba o ponto final**, e o livro sai sem pontuação nenhuma.

        Medido no projeto de origem, com a área normalizada pela escala ao quadrado:

            respingo da régua   0,0021 - 0,0031
            ponto final         0,0129 - 0,0514
            letra minúscula     0,1570 - 0,3315

        Este teste reproduz a separação: um ponto de tamanho de pontuação passa, e um respingo
        de tamanho de trama não. Uma régua de altura reprovaria os dois.
        """
        escala = 30
        piso_em_px = MIN_AREA_GLIFO * escala * escala  # 4,5 px de caixa
        img = np.zeros((200, 200), dtype=np.uint8)
        cv2.circle(img, (50, 100), 2, 255, -1)  # ponto final: caixa 5x5 = 25 px, ~0,028
        img[100, 150] = 255  # respingo da régua: caixa 1x1, ~0,001
        self.assertLess(1, piso_em_px, "o fixture do respingo não é menor que o piso")
        self.assertGreater(25, piso_em_px, "o fixture do ponto final não é maior que o piso")

        aceitas = caixas_de_caractere(img, escala=escala)
        centros = [(c.x1 + c.x2) // 2 for c in aceitas]
        self.assertIn(True, [abs(x - 50) < 8 for x in centros], "o ponto final foi descartado")
        self.assertNotIn(True, [abs(x - 150) < 8 for x in centros], "o respingo passou")

    def test_o_filete_nao_e_caractere(self) -> None:
        """Sublinhado, moldura e filete de cabeçalho passam da proporção máxima."""
        img = np.zeros((60, 300), dtype=np.uint8)
        cv2.line(img, (10, 30), (290, 30), 255, 2)
        largura, altura = 280, 2
        self.assertGreater(largura / altura, PROPORCAO_MAXIMA, "o fixture não é um filete")
        self.assertEqual([], caixas_de_caractere(img, escala=12))

    def test_a_escala_de_fora_vence_a_medida_na_faixa(self) -> None:
        """Uma faixa com três letras não tem população para medir escala nenhuma."""
        img = binarize(_pagina_de_texto(), "otsu")
        self.assertTrue(caixas_de_caractere(img, escala=20))
        self.assertEqual([], caixas_de_caractere(img, escala=400), "a escala de fora foi ignorada")

    def test_escala_zero_devolve_nada_em_vez_de_dividir_por_zero(self) -> None:
        self.assertEqual([], caixas_de_caractere(np.zeros((50, 50), dtype=np.uint8)))

    def test_o_limiar_de_area_esta_no_vao_entre_respingo_e_pontuacao(self) -> None:
        """Se alguém mexer no valor, o teste diz de onde ele veio."""
        self.assertGreater(MIN_AREA_GLIFO, 0.0031, "abaixo do maior respingo medido")
        self.assertLess(MIN_AREA_GLIFO, 0.0073, "acima do menor traço legítimo medido")


class UnirPingosTests(unittest.TestCase):
    """O pingo do `i` volta para o `i`.

    **Sem isto a régua de área fica pior que a de altura que ela substituiu**, e a medição de
    2026-08-22 mostrou exatamente isso: `Defensive` saía `Defens1.ve`, e o CER da faixa subia de
    0,21 para 0,35. Não é argumento para voltar à altura -- ela acertava aqui por **descartar** o
    pingo, e o preço era descartar junto o ponto final de verdade.
    """

    def _i(self, x: int = 100, y: int = 100) -> tuple[Caixa, Caixa]:
        """A haste e o pingo de um `i`, com as medidas reais da página 21 do AAGAARD."""
        haste = Caixa(x, y + 9, x + 9, y + 27)  # 9x18
        pingo = Caixa(x + 2, y, x + 7, y + 6)  # 5x6, 3 px acima da haste
        return haste, pingo

    def test_o_pingo_volta_para_a_haste(self) -> None:
        haste, pingo = self._i()
        outras = [Caixa(200, 109, 214, 127), Caixa(220, 109, 234, 127)]
        unidas = unir_pingos([haste, pingo, *outras], escala=30)
        self.assertEqual(3, len(unidas), "o pingo continuou solto")
        primeira = unidas[0]
        self.assertEqual((haste.x1, pingo.y1, haste.x2, haste.y2), (primeira.x1, primeira.y1, primeira.x2, primeira.y2))

    def test_a_regua_e_a_mediana_local_e_nao_a_escala_da_pagina(self) -> None:
        """**O defeito que custou uma medição, registrado como teste.**

        A escala da página é medida por massa de tinta e cai perto da altura de maiúscula -- 30 px
        no AAGAARD. A haste de um `i` minúsculo tem 18. Com `0,65 x 30 = 19,5` a própria haste
        conta como curta, não sobra base com que unir, e o merge não dispara. Este teste passa a
        escala de página "errada" de propósito: a função tem de ignorá-la para esta régua.
        """
        haste, pingo = self._i()
        outras = [Caixa(200, 109, 214, 127), Caixa(220, 109, 234, 127)]
        self.assertLess(haste.altura, CAIXA_CURTA * 30, "o fixture não reproduz o caso")
        self.assertEqual(3, len(unir_pingos([haste, pingo, *outras], escala=30)))

    def test_o_ponto_final_nao_e_unido_a_letra_anterior(self) -> None:
        """Ele vem **ao lado**, e não sobre ela. É o que `SOBREPOSICAO_MINIMA` separa."""
        letra = Caixa(100, 100, 114, 118)
        ponto = Caixa(118, 112, 124, 118)
        unidas = unir_pingos([letra, ponto, Caixa(200, 100, 214, 118)], escala=20)
        self.assertEqual(3, len(unidas))

    def test_o_merge_nao_atravessa_a_linha_de_texto(self) -> None:
        """É a cicatriz da F3.11 no projeto de origem.

        Entre linhas o vão é de ~1 altura de letra; dentro do glifo é uma fração dela. Sem o
        guarda, uma vírgula da linha de cima seria absorvida por uma letra da linha de baixo.
        """
        virgula_de_cima = Caixa(100, 60, 106, 68)
        letra_de_baixo = Caixa(100, 100, 114, 118)
        unidas = unir_pingos([virgula_de_cima, letra_de_baixo, Caixa(130, 100, 144, 118)], escala=20)
        self.assertEqual(3, len(unidas))

    def test_a_ordem_de_entrada_e_preservada(self) -> None:
        """Quem ordena é `linhas.ordem_em_faixa`; reordenar aqui esconderia um defeito dele."""
        caixas = [Caixa(300, 100, 314, 118), Caixa(100, 100, 114, 118), Caixa(200, 100, 214, 118)]
        self.assertEqual([c.x1 for c in caixas], [c.x1 for c in unir_pingos(caixas, escala=20)])

    def test_sem_caixa_alta_nada_e_unido(self) -> None:
        """Dois pontos e ponto e vírgula não têm base alta com que se unir."""
        so_curtas = [Caixa(100, 100, 106, 106), Caixa(100, 112, 106, 118)]
        self.assertEqual(2, len(unir_pingos(so_curtas, escala=20)))

    def test_lista_vazia(self) -> None:
        self.assertEqual([], unir_pingos([], escala=20))


class PingoDeItalicoTests(unittest.TestCase):
    """Em itálico o pingo pousa **à direita** da haste, e a régua horizontal o perde.

    Medido na página 77 do `Minhas 60 partidas memoráveis`, com as medidas reais deste fixture:
    sobreposição 0,500 contra o mínimo de 0,55, e `técnica` saía `técnl'ca`. O `i` **não** é
    recuperável depois -- na haste o classificador responde `/` com 0,915 --, porque ele só existe
    na imagem das duas caixas fundidas.
    """

    def _pagina(self, inclinacao: float) -> tuple[np.ndarray, Caixa, Caixa]:
        """Uma haste inclinada e o pingo dela, nas medidas reais da página do Fischer.

        A haste é desenhada de verdade porque é dela que a inclinação é **medida**: passar um
        número por fora testaria o teste, e não a função.
        """
        img = np.zeros((80, 80), np.uint8)
        altura, base_y = 17, 30
        for k in range(altura):
            y = base_y + altura - 1 - k
            x = 20 + int(round(k * inclinacao))
            img[y, x : x + 3] = 255
        xs = np.nonzero(img.any(axis=0))[0]
        haste = Caixa(int(xs[0]), base_y, int(xs[-1]) + 1, base_y + altura)
        # o pingo acompanha o topo da haste: 3 px acima, e 4 px de largura
        pingo = Caixa(haste.x2 - 2, base_y - 7, haste.x2 + 2, base_y - 3)
        img[pingo.y1 : pingo.y2, pingo.x1 : pingo.x2] = 255
        return img, haste, pingo

    def _outras(self) -> list[Caixa]:
        return [Caixa(60, 30, 74, 47), Caixa(60, 55, 74, 72)]

    def test_sem_binaria_o_pingo_italico_continua_perdido(self) -> None:
        """É o comportamento de hoje, e ele fica travado: o conserto é opt-in."""
        img, haste, pingo = self._pagina(0.20)
        self.assertEqual(4, len(unir_pingos([haste, pingo, *self._outras()], escala=20)))

    def test_com_binaria_o_pingo_italico_volta_para_a_haste(self) -> None:
        img, haste, pingo = self._pagina(0.20)
        unidas = unir_pingos([haste, pingo, *self._outras()], escala=20, binaria=img)
        self.assertEqual(3, len(unidas), "o pingo do itálico continuou solto")
        self.assertEqual(pingo.y1, unidas[0].y1, "a união não subiu até o pingo")

    def test_o_ponto_final_nao_e_arrastado_junto(self) -> None:
        """**O deslocamento é proporcional ao vão, e é isso que protege a pontuação.**

        O ponto final está na altura da letra: o vão dele é ~0, o x dele não se move, e ele
        continua fora. Medido em 40 páginas: 1.140 pontos antes e 1.140 depois.
        """
        img, haste, _ = self._pagina(0.20)
        ponto = Caixa(haste.x2 + 1, haste.y2 - 4, haste.x2 + 5, haste.y2)
        img[ponto.y1 : ponto.y2, ponto.x1 : ponto.x2] = 255
        unidas = unir_pingos([haste, ponto, *self._outras()], escala=20, binaria=img)
        self.assertEqual(4, len(unidas), "o ponto final foi absorvido")

    def test_a_letra_larga_nao_ganha_correcao(self) -> None:
        """`HASTE_ESTREITA`: só um traço carrega pingo, e o que pousa sobre `a` é acento."""
        img, _, _ = self._pagina(0.20)
        larga = Caixa(20, 30, 40, 47)  # 20x17: mais larga que alta/2
        img[larga.y1 : larga.y2, larga.x1 : larga.x2] = 255
        vizinha = Caixa(larga.x2 + 1, 23, larga.x2 + 5, 27)
        img[vizinha.y1 : vizinha.y2, vizinha.x1 : vizinha.x2] = 255
        unidas = unir_pingos([larga, vizinha, *self._outras()], escala=20, binaria=img)
        self.assertEqual(4, len(unidas))


class ExclusaoTests(unittest.TestCase):
    def test_o_que_esta_dentro_do_diagrama_sai(self) -> None:
        caixas = [Caixa(10, 10, 20, 25), Caixa(100, 100, 112, 118)]
        sobrou = excluir_diagramas(caixas, [(90.0, 90.0, 200.0, 200.0)], escala=10, margem=0.0)
        self.assertEqual([caixas[0]], sobrou)

    def test_a_margem_tira_o_rotulo_da_casa(self) -> None:
        """Os rótulos `a`-`h` e `8`-`1` moram **fora** da borda do tabuleiro.

        Sem margem eles entram no texto como linhas de um caractere -- medido no projeto de
        origem, oito linhas contendo só "8", "7", "6"...
        """
        rotulo = Caixa(95, 205, 103, 220)  # logo abaixo do tabuleiro
        tabuleiro = (100.0, 100.0, 200.0, 200.0)
        self.assertEqual([rotulo], excluir_diagramas([rotulo], [tabuleiro], escala=10, margem=0.0))
        self.assertEqual([], excluir_diagramas([rotulo], [tabuleiro], escala=10))

    def test_sem_diagrama_nada_muda(self) -> None:
        caixas = [Caixa(0, 0, 5, 8)]
        self.assertIs(caixas, excluir_diagramas(caixas, [], escala=10))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
