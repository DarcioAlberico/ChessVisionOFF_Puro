"""A tarja: texto branco sobre preto (S-195).

**O caso perigoso desta fase não é a foto, é a palavra sublinhada.** O sublinhado gruda as letras
num componente cheio e largo, os vazados do `n` e do `a` viram "glifos" plausíveis, e aceitá-la
substituiria por lixo um texto que o caminho normal já lia certo. Dois testes aqui existem só para
ela.
"""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from chess_diagram_ocr.text.binarizacao import binarize
from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.negativo import (
    ALTURA_TARJA,
    RAZAO,
    candidatos,
    faixa_solida,
    ler_faixa,
    parece_texto,
    positivar,
    substituir_tarjas,
)

ESCALA = 20
LARGURA, ALTURA = 700, 300


def _pagina() -> np.ndarray:
    return np.full((ALTURA, LARGURA), 245, dtype=np.uint8)


def tarja(
    pagina: np.ndarray, *, x: int = 40, y: int = 60, largura: int = 560, altura: int = 55, texto: str = "J.Bolbochan"
) -> Caixa:
    """Uma tarja preta com texto branco dentro. Proporção ~10:1, como as medidas no acervo."""
    cv2.rectangle(pagina, (x, y), (x + largura, y + altura), 15, -1)
    cv2.putText(pagina, texto, (x + 12, y + altura - 14), 0, 1.1, 250, 2, cv2.LINE_AA)
    return Caixa(x, y, x + largura, y + altura)


def palavra_sublinhada(pagina: np.ndarray, *, x: int = 40, y: int = 180) -> Caixa:
    """Texto preto em negrito com sublinhado: cheio, largo, e **não** é tarja.

    Proporção ~3,5 e altura ~1,1 escalas -- dentro das duas faixas medidas para o caso falso.
    """
    cv2.putText(pagina, "Opening", (x, y + 20), 0, 0.8, 15, 3, cv2.LINE_AA)
    cv2.line(pagina, (x, y + 26), (x + 78, y + 26), 15, 3)
    return Caixa(x, y, x + 78, y + 28)


class GeometriaTests(unittest.TestCase):
    def test_a_tarja_e_candidata(self) -> None:
        pagina = _pagina()
        caixa = tarja(pagina)
        achadas = candidatos(binarize(pagina, "otsu"), [caixa], escala=ESCALA)
        self.assertEqual([caixa], achadas)

    def test_a_palavra_sublinhada_nao_e_candidata(self) -> None:
        """**O caso perigoso.** Ela é cheia e larga; o que a recusa são proporção e altura juntas.

        Medido no projeto de origem em 588 páginas:

            tarja de verdade      proporção 5,34 - 13,70    altura 2,57 - 28,50 escalas
            palavra sublinhada    proporção 3,00 -  4,72    altura 0,41 -  1,21
        """
        pagina = _pagina()
        caixa = palavra_sublinhada(pagina)
        self.assertLess(caixa.largura / caixa.altura, RAZAO, "o fixture não tem proporção de palavra")
        self.assertLess(caixa.altura, ALTURA_TARJA * ESCALA, "o fixture não tem altura de palavra")
        self.assertEqual([], candidatos(binarize(pagina, "otsu"), [caixa], escala=ESCALA))

    def test_o_traco_de_letra_comum_nao_e_candidato(self) -> None:
        pagina = _pagina()
        cv2.putText(pagina, "texto normal", (40, 250), 0, 0.9, 15, 2, cv2.LINE_AA)
        caixa = Caixa(40, 232, 60, 252)
        self.assertEqual([], candidatos(binarize(pagina, "otsu"), [caixa], escala=ESCALA))


class AparaTests(unittest.TestCase):
    def test_a_tira_hachurada_acima_da_tarja_e_aparada(self) -> None:
        """Ela é clara o bastante para virar tinta na inversão e funde meia linha num componente.

        Linha de retângulo cheio tem ~100% de tinta; linha de tira hachurada, 55%-75%.
        """
        pagina = _pagina()
        caixa = tarja(pagina, y=80)
        # **A tira é hachurada, e não sólida** -- é o que a distingue da borda da tarja. Cada
        # linha dela cobre ~60% da largura; a borda da tarja cobre ~100%. Uma tira sólida teria
        # linhas cheias e seria indistinguível da borda, que é o caso que a apara não separa.
        for y in range(60, 80, 2):
            for x in range(40, 600, 10):
                cv2.line(pagina, (x, y), (x + 6, y), 15, 1)

        binaria = binarize(pagina, "otsu")
        perfil = (binaria[60:80, 40:600] > 0).mean(axis=1)
        self.assertTrue(all(0.5 <= v <= 0.8 for v in perfil[::2]), f"a tira não ficou hachurada: {perfil[:4]}")
        crua = Caixa(caixa.x1, 60, caixa.x2, caixa.y2)
        aparada = faixa_solida(binaria, crua)
        assert aparada is not None
        self.assertGreaterEqual(aparada.y1, 74, f"a apara não comeu a tira ({aparada.y1})")

    def test_o_eixo_sem_borda_cheia_volta_inteiro(self) -> None:
        """**Não aparar é a resposta certa para a tarja de tom fraco**, e não uma desistência.

        Quando a apara era condição de aceite, a tarja cinza *"6...♘bd7"* -- legível, nove
        caracteres -- era recusada por não ter linha cheia, e o texto ficava perdido do mesmo
        jeito de antes da fase.
        """
        pagina = _pagina()
        caixa = Caixa(40, 60, 600, 115)
        # Tom fraco: a binarização marca parte da faixa, e nenhuma linha chega a `SOLIDO`.
        recorte = pagina[60:115, 40:600]
        recorte[::3, :] = 120
        binaria = binarize(pagina, "otsu")
        aparada = faixa_solida(binaria, caixa)
        assert aparada is not None
        self.assertEqual((caixa.y1, caixa.y2), (aparada.y1, aparada.y2))

    def test_caixa_vazia_devolve_none(self) -> None:
        self.assertIsNone(faixa_solida(np.zeros((10, 10), dtype=np.uint8), Caixa(5, 5, 5, 5)))


class ConteudoTests(unittest.TestCase):
    """**O que decide não é o formato da faixa, é o que tem dentro.**"""

    def test_a_tarja_devolve_os_caracteres_de_dentro(self) -> None:
        pagina = _pagina()
        caixa = tarja(pagina)
        glifos = ler_faixa(pagina, caixa)
        assert glifos is not None
        self.assertGreaterEqual(len(glifos), 8, f"saíram {len(glifos)} glifos")
        for glifo in glifos:
            self.assertGreaterEqual(glifo.x1, caixa.x1)
            self.assertLessEqual(glifo.y2, caixa.y2)

    def test_a_faixa_cheia_sem_texto_nao_e_tarja(self) -> None:
        """Uma foto, um logotipo e uma barra de rodapé passam pela geometria e param aqui."""
        pagina = _pagina()
        cv2.rectangle(pagina, (40, 60), (600, 115), 15, -1)
        self.assertIsNone(ler_faixa(pagina, Caixa(40, 60, 600, 115)))

    def test_a_regua_do_glifo_e_a_altura_da_faixa_e_nao_a_da_pagina(self) -> None:
        """A mediana da página não é confiável para medir glifo: 4 px numa, 18 px na seguinte."""
        faixa = Caixa(0, 0, 500, 50)
        do_tamanho_certo = [Caixa(i * 30, 10, i * 30 + 12, 40) for i in range(5)]
        self.assertTrue(parece_texto(do_tamanho_certo, faixa))
        # As mesmas caixas numa faixa dez vezes mais alta deixam de ter tamanho de caractere.
        self.assertFalse(parece_texto(do_tamanho_certo, Caixa(0, 0, 500, 500)))


class SubstituicaoTests(unittest.TestCase):
    def test_a_tarja_e_trocada_pelos_caracteres(self) -> None:
        pagina = _pagina()
        caixa = tarja(pagina)
        outra = Caixa(40, 240, 54, 260)
        saida, faixas = substituir_tarjas(pagina, binarize(pagina, "otsu"), [caixa, outra], escala=ESCALA)
        self.assertEqual(1, len(faixas))
        self.assertNotIn(caixa, saida)
        self.assertIn(outra, saida)
        self.assertGreater(len(saida), 5)

    def test_a_saida_sai_ordenada_por_y_e_x(self) -> None:
        """**Não é cortesia.** Fora de ordem, o merge vertical casa uma letra da tarja lá em cima
        com uma caixa lá embaixo; a caixa resultante atravessa a página e absorve tudo que cruza a
        coluna dela. Medido no projeto de origem: 1.889 boxes saíram do merge como **27**.
        """
        pagina = _pagina()
        caixa = tarja(pagina)
        antes = Caixa(40, 20, 54, 40)
        depois = Caixa(40, 240, 54, 260)
        saida, _ = substituir_tarjas(pagina, binarize(pagina, "otsu"), [depois, caixa, antes], escala=ESCALA)
        chaves = [(c.y1, c.x1) for c in saida]
        self.assertEqual(sorted(chaves), chaves)

    def test_sem_tarja_nenhuma_a_lista_nao_muda(self) -> None:
        pagina = _pagina()
        caixas = [Caixa(40, 240, 54, 260)]
        saida, faixas = substituir_tarjas(pagina, binarize(pagina, "otsu"), caixas, escala=ESCALA)
        self.assertEqual(caixas, saida)
        self.assertEqual([], faixas)


class PolaridadeTests(unittest.TestCase):
    def test_positivar_e_a_volta_e_ela_e_involutiva(self) -> None:
        """A tinta escura sobre fundo claro é **como o modelo viu no treino**."""
        recorte = np.array([[0, 128, 255]], dtype=np.uint8)
        np.testing.assert_array_equal(np.array([[255, 127, 0]], dtype=np.uint8), positivar(recorte))
        np.testing.assert_array_equal(recorte, positivar(positivar(recorte)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
