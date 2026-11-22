"""A sugestão de marcas com dois leitores (`opiniao_das_marcas.py`): o que entra e o que vira discordância."""

from __future__ import annotations

import unittest

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr import opiniao_das_marcas as om


class JuntarTests(unittest.TestCase):
    def test_sem_modelo_vale_o_detector_sem_discordancia(self) -> None:
        opiniao = om.juntar({"c5": mc.ESTRELA_PRETA}, None)
        self.assertEqual(opiniao.casas, {"c5": mc.ESTRELA_PRETA})
        self.assertEqual(opiniao.discordancias, {})
        self.assertFalse(opiniao.com_modelo)

    def test_concordancia_entra_sem_discordancia(self) -> None:
        opiniao = om.juntar({"c5": mc.X}, {"c5": mc.X})
        self.assertEqual((opiniao.casas, opiniao.discordancias), ({"c5": mc.X}, {}))
        self.assertTrue(opiniao.com_modelo)

    def test_o_que_so_um_ve_entra_e_vira_discordancia(self) -> None:
        opiniao = om.juntar({"d3": mc.X}, {"c6": mc.BOLINHA_BRANCA})
        self.assertEqual(opiniao.casas, {"c6": mc.BOLINHA_BRANCA, "d3": mc.X})
        self.assertEqual(opiniao.discordancias, {"c6": (None, mc.BOLINHA_BRANCA), "d3": (mc.X, None)})

    def test_tipo_diferente_leva_o_do_modelo_e_a_frase_diz_os_dois(self) -> None:
        opiniao = om.juntar({"e4": mc.BOLINHA_PRETA}, {"e4": mc.ESTRELA_PRETA})
        self.assertEqual(opiniao.casas, {"e4": mc.ESTRELA_PRETA})
        self.assertEqual(
            om.descrever_discordancias(opiniao), "e4: modelo estrela preta, detector bolinha preta"
        )

    def test_a_frase_fica_nas_casas_pedidas(self) -> None:
        opiniao = om.juntar({"d3": mc.X}, {"c6": mc.BOLINHA_BRANCA})
        self.assertEqual(om.descrever_discordancias(opiniao, {"c6": mc.BOLINHA_BRANCA}), "c6: modelo bolinha branca, detector nada")
        self.assertEqual(om.descrever_discordancias(opiniao, {}), "")


class ConcordanciaTests(unittest.TestCase):
    def test_so_o_que_os_dois_dizem_igual(self) -> None:
        opiniao = om.juntar({"c5": mc.X, "d3": mc.X, "e4": mc.BOLINHA_PRETA}, {"c5": mc.X, "f6": mc.ESTRELA_PRETA, "e4": mc.CRUZ})
        self.assertEqual(om.concordancia(opiniao), {"c5": mc.X})

    def test_sem_modelo_nao_ha_concordancia(self) -> None:
        self.assertIsNone(om.concordancia(om.juntar({"c5": mc.X}, None)), "o detector sozinho não põe marca no livro")

    def test_os_dois_sem_marca_e_lido_sem_marca(self) -> None:
        self.assertEqual(om.concordancia(om.juntar({}, {})), {})

    def test_a_variavel_desvia_o_modelo(self) -> None:
        import os
        from pathlib import Path
        from unittest import mock

        with mock.patch.dict(os.environ, {om.ENV_MODELO_DE_MARCAS: "outro.pt"}):
            self.assertEqual(om.caminho_do_modelo_de_marcas(), Path("outro.pt"))
        with mock.patch.dict(os.environ, {om.ENV_MODELO_DE_MARCAS: ""}):
            self.assertEqual(om.caminho_do_modelo_de_marcas(), om.MODELO_DE_MARCAS)


if __name__ == "__main__":
    unittest.main()
