"""A regra do recorte, sem janela: casa ↔ pixel, as três leituras, a margem e o âmbar (passo 13).

**Sem `PyQt6` de propósito**: tudo o que `qt/painel_de_recorte.py` e `qt/tabuleiro_editavel.py`
desenham sai destas funções, e é aqui -- e não dirigindo widgets -- que se afirma que a casa sob o
ponteiro é a casa que o modelo leu, que a dica diz o que o modelo apostou e que o âmbar segue a
hesitação e não a confiança.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.config import PIECE_CLASSES, UNCERTAIN_SQUARE_THRESHOLD
from chess_diagram_ocr.ui import recorte_do_diagrama as regra
from chess_diagram_ocr.ui import strings


def _matriz(**apostas: tuple[float, ...]) -> np.ndarray:
    """(64, 13) com toda casa certa de «vazia», salvo as casas nomeadas (`c12=(0.6, 0.35)`).

    As apostas nomeadas vão para as classes `Q` (primeira) e `q` (segunda); o resto da linha é
    repartido igualmente entre as outras classes.
    """
    probs = np.zeros((64, len(PIECE_CLASSES)))
    probs[:, PIECE_CLASSES.index("empty")] = 1.0
    for nome, (primeira, segunda) in apostas.items():
        casa = int(nome[1:])
        linha = np.full(len(PIECE_CLASSES), (1.0 - primeira - segunda) / (len(PIECE_CLASSES) - 2))
        linha[PIECE_CLASSES.index("Q")] = primeira
        linha[PIECE_CLASSES.index("q")] = segunda
        probs[casa] = linha
    return probs


class CasaEPixelTests(unittest.TestCase):
    def test_o_retangulo_e_o_inverso_de_casa_em(self) -> None:
        """Toda casa, nas duas orientações: o centro do retângulo dela cai nela mesma."""
        for virado in (False, True):
            for casa in range(64):
                x0, y0, x1, y1 = regra.retangulo_da_casa(casa, 320, 320, virado=virado)
                with self.subTest(casa=casa, virado=virado):
                    self.assertEqual(regra.casa_em((x0 + x1) / 2, (y0 + y1) / 2, 320, 320, virado=virado), casa)

    def test_a8_e_o_canto_superior_esquerdo_sem_giro_e_o_inferior_direito_com(self) -> None:
        """`rotation == 180` (o diagrama impresso de cabeça para baixo): o classificador leu a
        imagem girada, então a casa de leitura 0 está no canto oposto do recorte impresso."""
        self.assertEqual(regra.casa_em(1, 1, 80, 80), 0)
        self.assertEqual(regra.casa_em(79, 79, 80, 80), 63)
        self.assertEqual(regra.casa_em(1, 1, 80, 80, virado=True), 63)
        self.assertEqual(regra.casa_em(79, 79, 80, 80, virado=True), 0)

    def test_fora_do_recorte_e_none(self) -> None:
        self.assertIsNone(regra.casa_em(-1, 10, 80, 80))
        self.assertIsNone(regra.casa_em(80, 10, 80, 80))
        self.assertIsNone(regra.casa_em(10, 10, 0, 0))

    def test_um_recorte_que_nao_e_quadrado_ainda_divide_em_oito(self) -> None:
        x0, y0, x1, y1 = regra.retangulo_da_casa(9, 160, 80)
        self.assertEqual((x0, y0, x1, y1), (20.0, 10.0, 40.0, 20.0))

    def test_casa_fora_das_64_levanta(self) -> None:
        with self.assertRaises(ValueError):
            regra.retangulo_da_casa(64, 80, 80)


class LeiturasTests(unittest.TestCase):
    def test_as_tres_leituras_saem_da_maior_para_a_menor(self) -> None:
        probs = _matriz(c12=(0.6, 0.35))
        leituras = regra.alternativas(probs, 12)
        self.assertEqual([leitura.classe for leitura in leituras], ["Q", "q", "empty"][:2] + [leituras[2].classe])
        self.assertAlmostEqual(leituras[0].probabilidade, 0.6)
        self.assertAlmostEqual(leituras[1].probabilidade, 0.35)
        self.assertEqual(leituras[0].nome, "dama branca")

    def test_sem_matriz_nao_ha_leitura_e_a_margem_e_um(self) -> None:
        self.assertEqual(regra.alternativas(None, 12), ())
        self.assertEqual(regra.margem(None, 12), 1.0)
        self.assertEqual(regra.margens(None), ())
        self.assertEqual(regra.casas_ambar(None), ())

    def test_a_margem_e_a_vencedora_menos_a_segunda(self) -> None:
        probs = _matriz(c12=(0.6, 0.35), c20=(0.9, 0.05))
        self.assertAlmostEqual(regra.margem(probs, 12), 0.25)
        self.assertAlmostEqual(regra.margem(probs, 20), 0.85)
        self.assertAlmostEqual(regra.margem(probs, 0), 1.0)

    def test_o_ambar_segue_a_margem_e_nao_a_confianca(self) -> None:
        """c12 hesita (0,60 × 0,35: âmbar); c20 é pouco confiante pela régua antiga (0,80 < 0,90)
        mas não hesita (segunda a 0,05): fica limpa. É a diferença entre as duas réguas."""
        probs = _matriz(c12=(0.6, 0.35), c20=(0.8, 0.05), c30=(0.5, 0.45))
        self.assertEqual(regra.casas_ambar(probs), (30, 12))
        self.assertLess(0.8, UNCERTAIN_SQUARE_THRESHOLD, "c20 seria incerta pela régua antiga")

    def test_a_tinta_e_por_margem_com_matriz_e_pela_regua_antiga_sem(self) -> None:
        probs = _matriz(c12=(0.6, 0.35))
        com = regra.tinta_do_diagrama(probs, casas_incertas=[3], confiancas=[0.5] * 64)
        self.assertTrue(com.por_margem)
        self.assertEqual(com.casas, (12,))
        self.assertEqual(len(com.valores), 64)
        self.assertEqual(com.limiar, regra.LIMIAR_DE_MARGEM)

        sem = regra.tinta_do_diagrama(None, casas_incertas=[3, 70], confiancas=[0.5] * 64)
        self.assertFalse(sem.por_margem)
        self.assertEqual(sem.casas, (3,), "a casa 70 não existe e cai fora")
        self.assertEqual(sem.limiar, UNCERTAIN_SQUARE_THRESHOLD)
        self.assertEqual(len(sem.valores), 64)

    def test_confiancas_incompletas_nao_viram_valores(self) -> None:
        sem = regra.tinta_do_diagrama(None, casas_incertas=[3], confiancas=[0.5, 0.6])
        self.assertEqual(sem.valores, ())

    def test_duvidoso_e_ter_alguma_casa_a_conferir(self) -> None:
        self.assertTrue(regra.e_duvidoso(_matriz(c12=(0.6, 0.35))))
        self.assertFalse(regra.e_duvidoso(_matriz()))
        self.assertTrue(regra.e_duvidoso(None, casas_incertas=[5]))
        self.assertFalse(regra.e_duvidoso(None))


class DicaTests(unittest.TestCase):
    def test_a_dica_diz_a_casa_as_leituras_e_a_margem_com_virgula(self) -> None:
        probs = _matriz(c12=(0.6, 0.35))
        leituras = regra.alternativas(probs, 12)
        dica = regra.dica_da_casa(12, leituras, regra.margem(probs, 12))
        self.assertTrue(dica.startswith("e7 · dama branca 0,600 · dama preta 0,350 · "), dica)
        self.assertTrue(dica.endswith("· margem 0,25"), dica)
        self.assertNotIn(".", dica.split("·")[1])

    def test_sem_leituras_a_dica_e_so_o_nome_da_casa(self) -> None:
        self.assertEqual(regra.dica_da_casa(0, ()), "a8")
        self.assertEqual(regra.dica_da_casa(0, (), 0.3), "a8", "margem sem leitura não é dita")

    def test_o_nome_da_classe_vazia_e_vazia(self) -> None:
        self.assertEqual(regra.nome_da_classe("empty"), "vazia")
        self.assertEqual(regra.nome_da_classe("n"), "cavalo preto")
        self.assertEqual(regra.nome_da_classe("?"), "?", "classe desconhecida sai crua, não some")


class LegendaTests(unittest.TestCase):
    """A legenda numa linha: a medição que a motivou está em `strings.LIMITE_DA_LEGENDA`."""

    def test_uma_legenda_curta_sai_inteira_e_numa_linha(self) -> None:
        self.assertEqual(strings.resumo_da_legenda("Schwarz:\n La5—c7!"), "Schwarz: La5—c7!")

    def test_uma_legenda_longa_e_cortada_com_reticencias(self) -> None:
        longa = " ".join(["lance"] * 100)
        resumo = strings.resumo_da_legenda(longa)
        self.assertLessEqual(len(resumo), strings.LIMITE_DA_LEGENDA)
        self.assertTrue(resumo.endswith("…"))
        self.assertNotIn("\n", resumo)

    def test_vazio_continua_vazio(self) -> None:
        self.assertEqual(strings.resumo_da_legenda(""), "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
