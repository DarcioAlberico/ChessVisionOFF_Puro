"""Separar tinta de papel, e a armadilha que custou uma versão inteira (S-184).

**Os fixtures são gerados, não são páginas de livro.** O repositório não versiona PDF nem
digitalização, e o que estes testes exercitam é a regra de decisão -- que se reproduz com uma
página sintética e uma sombra desenhada por cima.
"""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from chess_diagram_ocr.text.binarizacao import (
    METODOS,
    TINTA_PLAUSIVEL,
    binarize,
    fracao_de_tinta,
    metodo_escolhido,
    tinta_plausivel,
)

LARGURA, ALTURA = 400, 300


def _pagina_limpa() -> np.ndarray:
    """Papel claro e uniforme, com texto escuro. O caso fácil."""
    img = np.full((ALTURA, LARGURA), 240, dtype=np.uint8)
    for linha in range(4):
        cv2.putText(img, "texto de exemplo", (20, 50 + linha * 60), 0, 0.9, 20, 2, cv2.LINE_AA)
    return img


def _pagina_com_sombra() -> np.ndarray:
    """A página com sombra de encadernação: metade escura, metade clara.

    É o caso que derruba o Otsu global -- e que derrubava o critério de bimodalidade, porque as
    duas metades **são** duas classes perfeitamente separadas.
    """
    img = _pagina_limpa()
    gradiente = np.linspace(0, 200, LARGURA, dtype=np.float64)
    escurecida = np.clip(img.astype(np.float64) - gradiente[None, :], 0, 255)
    return escurecida.astype(np.uint8)


class PolaridadeTests(unittest.TestCase):
    def test_a_polaridade_e_tinta_branca_e_fundo_preto(self) -> None:
        """É contrato, não gosto: `cv2.findContours` espera assim, e a S-185 conta com isso.

        Trocar a polaridade depois quebraria toda a segmentação **em silêncio** -- os contornos
        passariam a ser os do papel, e um deles cobriria a página inteira.
        """
        binaria = binarize(_pagina_limpa(), "otsu")
        self.assertLess(fracao_de_tinta(binaria), 0.5, "a tinta virou maioria: a polaridade inverteu")
        self.assertEqual({0, 255}, set(np.unique(binaria)))

    def test_pagina_em_branco_nao_tem_tinta(self) -> None:
        self.assertEqual(0.0, fracao_de_tinta(binarize(np.full((50, 50), 255, dtype=np.uint8), "fixed")))


class AutoTests(unittest.TestCase):
    """A decisão do módulo: o `auto` avalia o **resultado**, e não o histograma."""

    def test_a_pagina_limpa_vai_para_o_otsu(self) -> None:
        self.assertEqual("otsu", metodo_escolhido(_pagina_limpa()))

    def test_a_pagina_com_sombra_nao_vai_para_o_otsu(self) -> None:
        """O Otsu ali separa "metade escura" de "metade clara" e devolve ~47% de tinta.

        São duas classes perfeitamente bimodais, e é exatamente por isso que o critério de
        bimodalidade errava neste caso -- que é o caso que interessa.
        """
        sombreada = _pagina_com_sombra()
        _, otsu = cv2.threshold(sombreada, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        self.assertGreater(fracao_de_tinta(otsu), TINTA_PLAUSIVEL[1], "o fixture não reproduz o caso")
        self.assertEqual("adaptive", metodo_escolhido(sombreada))

    def test_o_auto_devolve_o_que_o_metodo_escolhido_diz(self) -> None:
        for imagem, nome in ((_pagina_limpa(), "limpa"), (_pagina_com_sombra(), "sombra")):
            with self.subTest(pagina=nome):
                escolhido = metodo_escolhido(imagem)
                np.testing.assert_array_equal(binarize(imagem, "auto"), binarize(imagem, escolhido))

    def test_o_resultado_do_auto_sempre_parece_texto_na_pagina_limpa(self) -> None:
        self.assertTrue(tinta_plausivel(binarize(_pagina_limpa(), "auto")))


class ContratoTests(unittest.TestCase):
    def test_metodo_desconhecido_levanta_nomeando_os_validos(self) -> None:
        with self.assertRaises(ValueError) as capturado:
            binarize(_pagina_limpa(), "inventado")
        for metodo in METODOS:
            self.assertIn(metodo, str(capturado.exception))

    def test_imagem_rgb_e_cinza_dao_o_mesmo_resultado(self) -> None:
        cinza = _pagina_limpa()
        rgb = cv2.cvtColor(cinza, cv2.COLOR_GRAY2RGB)
        np.testing.assert_array_equal(binarize(cinza, "otsu"), binarize(rgb, "otsu"))

    def test_imagem_vazia_nao_levanta(self) -> None:
        self.assertEqual(0, binarize(np.zeros((0, 0), dtype=np.uint8), "auto").size)

    def test_a_janela_do_adaptativo_e_impar(self) -> None:
        """Janela par faz o OpenCV levantar; e ela é proporcional à página, não fixa.

        Pequena demais recorta o miolo dos glifos, grande demais volta a se comportar como
        limiar global -- que é o que o adaptativo existe para não ser.
        """
        for lado in (40, 100, 400, 1200):
            with self.subTest(lado=lado):
                imagem = np.full((lado, lado), 200, dtype=np.uint8)
                self.assertEqual(imagem.shape, binarize(imagem, "adaptive").shape)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
