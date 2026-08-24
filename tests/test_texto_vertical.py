"""A tabela dos quatro ângulos: quem entra na medição, e o que ela conta como acerto (S-197).

O comando existe porque o item estava implementado e **sem número** -- a arbitragem do ângulo é
do classificador, e até 2026-08-23 não havia classificador nesta máquina. Aqui o árbitro é
travado, que é o que permite afirmar *por que* uma pilha foi aceita sem carregar 2,6 MB de pesos.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.cli.texto_vertical import ANGULOS_IMPRESSOS, linhas_de_texto, medir_linha
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
