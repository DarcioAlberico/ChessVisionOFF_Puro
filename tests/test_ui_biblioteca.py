"""As facetas do acervo (`ui/biblioteca.IndiceDaBiblioteca`).

`facetas` é a passada única que substitui cinco chamadas a `faceta`, e a abertura -- sem busca e
sem eixo marcado -- sai de `_totais` sem varrer nada. Esse atalho lia um atributo que ninguém
montava, e a primeira chamada sem filtro levantava `AttributeError`. A régua aqui é a definição:
`facetas(filtro)` tem de dizer, eixo a eixo, o mesmo que `faceta(eixo, filtro)`.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from chess_diagram_ocr.ui.biblioteca import EIXO_IDIOMA, EIXOS, Filtro, IndiceDaBiblioteca, ItemDaBiblioteca

ACERVO = (
    ItemDaBiblioteca(Path("a.pdf"), "Meu sistema", autor="Nimzowitsch", idioma="de", ano=1925, diagramas=120),
    ItemDaBiblioteca(Path("b.pdf"), "Táctica", autor="Fulano", idioma="es", ano=1990, diagramas=40, processado=True),
    ItemDaBiblioteca(Path("c.pdf"), "Endgames", autor="Beltrano", idioma="en", ano=2010, diagramas=400),
    ItemDaBiblioteca(Path("d.pdf"), "Mittelspiel", autor="Ciclano", idioma="de", ano=2010),
)


class FacetasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.indice = IndiceDaBiblioteca(ACERVO)

    def _confere(self, filtro: Filtro) -> None:
        facetas = self.indice.facetas(filtro)
        self.assertEqual([faceta.eixo for faceta in facetas], list(EIXOS))
        for faceta in facetas:
            with self.subTest(eixo=faceta.eixo):
                self.assertEqual(faceta, self.indice.faceta(faceta.eixo, filtro))

    def test_na_abertura_as_contagens_sao_as_do_acervo_inteiro(self) -> None:
        self._confere(Filtro())
        idiomas = next(f for f in self.indice.facetas(Filtro()) if f.eixo == EIXO_IDIOMA)
        self.assertEqual(sum(valor.contagem for valor in idiomas.valores), len(ACERVO))

    def test_com_busca_e_com_eixo_marcado_batem_com_a_faceta_avulsa(self) -> None:
        self._confere(Filtro(consulta="mittel"))
        self._confere(Filtro().alternar(EIXO_IDIOMA, ACERVO[0].idioma_ou_ausente))


if __name__ == "__main__":
    unittest.main()
