"""Ponto, hífen ou travessão, decidido pela forma do box.

Puro: nenhum destes testes carrega modelo nem abre PDF. O que eles travam são as duas decisões e as
**guardas** que as limitam -- o box mais alto que largo só vira `.` quando o ponto é a melhor classe
que não é traço, e o traço curto só vira `-` quando tem a forma de traço e a página tem escala.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text import traco as po
from chess_diagram_ocr.text.boxes import Caixa

I2C = {0: "—", 1: "-", 2: "–", 3: ".", 4: "R", 5: "v"}

PONTO_EM_NEGRITO = Caixa(10, 20, 14, 25)
"""4x5 px: o ponto do negrito do Seirawan a 220 dpi, que o modelo lia como travessão."""

HIFEN = Caixa(10, 14, 20, 16)
"""10x2 px: o hífen da mesma página."""

ESCALA = 18.0
"""A escala de texto daquela página: o hífen de 10 px mede 0,56 dela."""

TRAVESSAO = Caixa(10, 14, 40, 17)
"""30x3 px: um travessão de verdade na mesma escala, 1,67 dela."""


def _probs(n: int, *, depois_dos_tracos: int = 3) -> np.ndarray:
    """O travessão ganha, os outros dois traços vêm atrás, e `depois_dos_tracos` é o quarto."""
    m = np.zeros((n, len(I2C)), dtype=np.float32)
    m[:, 0] = 0.38
    m[:, 1] = 0.14
    m[:, 2] = 0.11
    m[:, depois_dos_tracos] = 0.09
    return m


class FormaTests(unittest.TestCase):
    def test_o_quadrado_nao_e_traco(self) -> None:
        self.assertFalse(po.e_traco_pela_forma(PONTO_EM_NEGRITO.largura, PONTO_EM_NEGRITO.altura))

    def test_o_retangulo_deitado_e(self) -> None:
        self.assertTrue(po.e_traco_pela_forma(HIFEN.largura, HIFEN.altura))

    def test_box_sem_altura_nao_e_mexido(self) -> None:
        self.assertTrue(po.e_traco_pela_forma(5, 0))

    def test_o_limiar_e_lido_na_chamada(self) -> None:
        self.assertFalse(po.e_traco_pela_forma(10, 2, corte=6.0))
        antes = po.PROPORCAO_MINIMA
        try:
            po.PROPORCAO_MINIMA = 0.5
            self.assertTrue(po.e_traco_pela_forma(4, 5))
        finally:
            po.PROPORCAO_MINIMA = antes


class LarguraTests(unittest.TestCase):
    def test_o_hifen_e_curto(self) -> None:
        self.assertTrue(po.e_hifen_pela_largura(HIFEN.largura, ESCALA))

    def test_o_travessao_nao_e(self) -> None:
        self.assertFalse(po.e_hifen_pela_largura(TRAVESSAO.largura, ESCALA))

    def test_a_meia_risca_medida_nao_e(self) -> None:
        """12 px numa escala de 13: a meia-risca do Capablanca, a mais curta medida."""
        self.assertFalse(po.e_hifen_pela_largura(11, 13))

    def test_sem_escala_nao_se_julga(self) -> None:
        self.assertFalse(po.e_hifen_pela_largura(5, 0))

    def test_o_limiar_e_lido_na_chamada(self) -> None:
        self.assertFalse(po.e_hifen_pela_largura(10, 18, corte=0.5))
        antes = po.LARGURA_DO_HIFEN
        try:
            po.LARGURA_DO_HIFEN = 2.0
            self.assertTrue(po.e_hifen_pela_largura(30, 18))
        finally:
            po.LARGURA_DO_HIFEN = antes


class CorrigirTests(unittest.TestCase):
    def test_a_reticencia_em_negrito_volta_a_ser_reticencia(self) -> None:
        """`2.——Rd6` -> `2...Rd6`, que é o caso que abriu o item."""
        caixas = [Caixa(0, 20, 4, 25), PONTO_EM_NEGRITO, Caixa(16, 20, 20, 25), Caixa(22, 0, 34, 25)]
        lidos = [(".", 0.47), ("—", 0.38), ("—", 0.38), ("R", 1.0)]
        saida = po.corrigir(lidos, _probs(4), caixas, I2C)
        self.assertEqual("".join(c for c, _ in saida), "...R")

    def test_sem_escala_o_traco_fica(self) -> None:
        saida = po.corrigir([("—", 0.38), ("-", 0.30)], _probs(2), [HIFEN, HIFEN], I2C)
        self.assertEqual([c for c, _ in saida], ["—", "-"])

    def test_o_hifen_lido_como_travessao_volta_a_ser_hifen(self) -> None:
        """`f4—f8` -> `f4-f8`, o caso que abriu a segunda decisão."""
        saida = po.corrigir([("—", 0.32), ("–", 0.30)], _probs(2), [HIFEN, HIFEN], I2C, escala=ESCALA)
        self.assertEqual([c for c, _ in saida], ["-", "-"])

    def test_a_confianca_do_hifen_e_a_dele(self) -> None:
        _, conf = po.corrigir([("—", 0.38)], _probs(1), [HIFEN], I2C, escala=ESCALA)[0]
        self.assertAlmostEqual(conf, 0.14, places=3)

    def test_o_travessao_comprido_fica(self) -> None:
        saida = po.corrigir([("—", 0.38)], _probs(1), [TRAVESSAO], I2C, escala=ESCALA)
        self.assertEqual(saida, [("—", 0.38)])

    def test_o_sublinhado_curto_nao_vira_hifen(self) -> None:
        """Só meia-risca e travessão descem a hífen: o `_` não foi medido."""
        saida = po.corrigir([("_", 0.38)], _probs(1), [HIFEN], {**I2C, 6: "_"}, escala=ESCALA)
        self.assertEqual(saida, [("_", 0.38)])

    def test_o_traco_em_pe_nao_vira_hifen(self) -> None:
        """O `–` de 7x20 do Flores Rios: curto, mas não tem forma de traço -- e não é ponto."""
        em_pe = Caixa(0, 0, 7, 20)
        saida = po.corrigir([("–", 0.57)], _probs(1, depois_dos_tracos=5), [em_pe], I2C, escala=20.0)
        self.assertEqual(saida, [("–", 0.57)])

    def test_sem_a_classe_do_hifen_devolve_intacto(self) -> None:
        sem = {i: c for i, c in I2C.items() if c != "-"}
        saida = po.corrigir([("—", 0.38)], _probs(1), [HIFEN], sem, escala=ESCALA)
        self.assertEqual(saida, [("—", 0.38)])

    def test_a_confianca_e_a_do_ponto(self) -> None:
        """Manter os 0,38 do travessão recusado seria confiança inventada."""
        _, conf = po.corrigir([("—", 0.38)], _probs(1), [PONTO_EM_NEGRITO], I2C)[0]
        self.assertAlmostEqual(conf, 0.09, places=3)

    def test_se_a_melhor_nao_traco_nao_e_o_ponto_nada_muda(self) -> None:
        """O `–` de 15x16 era um `-+` grudado: trocá-lo por outra classe trocaria um erro por outro."""
        saida = po.corrigir([("—", 0.38)], _probs(1, depois_dos_tracos=5), [PONTO_EM_NEGRITO], I2C)
        self.assertEqual(saida, [("—", 0.38)])

    def test_o_que_nao_e_traco_passa_intacto(self) -> None:
        saida = po.corrigir([("R", 1.0)], _probs(1), [PONTO_EM_NEGRITO], I2C)
        self.assertEqual(saida, [("R", 1.0)])

    def test_sem_a_classe_do_ponto_devolve_intacto(self) -> None:
        sem = {i: c for i, c in I2C.items() if c != "."}
        saida = po.corrigir([("—", 0.38)], _probs(1), [PONTO_EM_NEGRITO], sem)
        self.assertEqual(saida, [("—", 0.38)])

    def test_lista_vazia_devolve_vazia(self) -> None:
        self.assertEqual(po.corrigir([], np.empty((0, 6), np.float32), [], I2C), [])

    def test_menos_caixas_que_lidos_nao_estoura(self) -> None:
        saida = po.corrigir([("R", 1.0), ("—", 0.38)], _probs(2), [Caixa(0, 0, 12, 25)], I2C)
        self.assertEqual([c for c, _ in saida], ["R", "—"])

    def test_todo_traco_e_um_caractere(self) -> None:
        self.assertTrue(all(len(c) == 1 for c in po.TRACOS))
        self.assertNotIn(po.PONTO, po.TRACOS)
        self.assertTrue(set(po.LONGOS) <= set(po.TRACOS))
        self.assertNotIn(po.HIFEN, po.LONGOS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
