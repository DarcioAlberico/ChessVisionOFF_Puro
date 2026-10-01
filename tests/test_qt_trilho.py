"""O trilho de páginas (OCR_UI passo 17): a regra em `ui/trilho.py`, a tinta em `qt/trilho.py`."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.trilho import (
    GLIFO_DIAGRAMA,
    GLIFO_DUVIDA,
    GLIFO_REVISADO,
    MarcaDaPagina,
    dica_da_pagina,
    papel_da_pagina,
    primeira_duvidosa,
    rotulo_da_pagina,
)


@dataclass
class _EstadoDaSuite:
    """O `caissa.ui.trilho.EstadoDaPagina` de mentira: os mesmos nomes de campo."""

    pagina: int
    montada: bool = True
    fonte: str = "text-layer"
    diagramas: int = 0
    diagramas_lidos: int = 0
    texto: bool = True
    duvidosos: int = 0
    revisada: bool = False


class RegraTests(unittest.TestCase):
    def test_o_rotulo_diz_so_o_que_a_pagina_tem(self) -> None:
        self.assertEqual("12", rotulo_da_pagina(MarcaDaPagina(11)))
        cheia = MarcaDaPagina(11, montada=True, diagramas=3, diagramas_lidos=2, texto=True, duvidosos=1)
        rotulo = rotulo_da_pagina(cheia)
        self.assertTrue(rotulo.startswith("12"))
        self.assertIn(f"{GLIFO_DIAGRAMA} 2/3", rotulo)
        self.assertIn(f"{GLIFO_DUVIDA} 1", rotulo)
        self.assertNotIn(GLIFO_REVISADO, rotulo)
        revisada = MarcaDaPagina(0, montada=True, texto=True, revisada=True)
        self.assertIn(GLIFO_REVISADO, rotulo_da_pagina(revisada))

    def test_a_cor_e_a_da_duvida_da_revisao_ou_da_ausencia(self) -> None:
        self.assertEqual(tokens.TEXTO_MORTO, papel_da_pagina(MarcaDaPagina(0)))
        self.assertEqual(tokens.ATENCAO, papel_da_pagina(MarcaDaPagina(0, montada=True, duvidosos=2)))
        self.assertEqual(tokens.PRONTO_TEXTO, papel_da_pagina(MarcaDaPagina(0, montada=True, revisada=True)))
        self.assertEqual(tokens.TEXTO_PADRAO, papel_da_pagina(MarcaDaPagina(0, montada=True, texto=True)))

    def test_a_marca_copia_o_estado_da_suite_por_nome(self) -> None:
        marca = MarcaDaPagina.de(_EstadoDaSuite(4, diagramas=2, diagramas_lidos=1, duvidosos=1))
        self.assertEqual((4, True, 2, 1, True, 1, False), (
            marca.pagina, marca.montada, marca.diagramas, marca.diagramas_lidos, marca.texto,
            marca.duvidosos, marca.revisada,
        ))

    def test_a_primeira_duvidosa_e_a_primeira_em_ordem_de_pagina(self) -> None:
        marcas = [
            MarcaDaPagina(0, montada=True),
            MarcaDaPagina(1, montada=True, duvidosos=1),
            MarcaDaPagina(2, montada=True, duvidosos=5),
        ]
        self.assertEqual(1, primeira_duvidosa(marcas))
        self.assertIsNone(primeira_duvidosa(marcas[:1]))

    def test_a_dica_e_uma_frase_inteira(self) -> None:
        self.assertIn("ainda não lida", dica_da_pagina(MarcaDaPagina(2)))
        frase = dica_da_pagina(MarcaDaPagina(2, montada=True, diagramas=2, diagramas_lidos=2, texto=True))
        self.assertIn("Página 3", frase)
        self.assertIn("2 de 2 diagrama(s)", frase)
        self.assertIn("com texto", frase)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class WidgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        from chess_diagram_ocr.qt.trilho import TrilhoDoLivro

        self.rasterizadas: list[int] = []

        def rasterizar(_pdf: Path, pagina: int, _dpi: int) -> np.ndarray:
            self.rasterizadas.append(pagina)
            return np.full((40, 30, 3), 200, np.uint8)

        # Em linha (`miniaturas_ao_fundo=False`): o teste pergunta pela miniatura na linha seguinte.
        self.trilho = TrilhoDoLivro(miniaturas_ao_fundo=False, rasterizar=rasterizar)
        self.addCleanup(descartar, self.trilho)
        self.trilho.resize(176, 600)
        self.trilho.show()
        self.app.processEvents()

    def test_abrir_o_livro_da_um_item_por_pagina_e_miniaturas_as_visiveis(self) -> None:
        self.trilho.abrir_livro(Path("livro.pdf"), 40)
        self.app.processEvents()
        self.assertEqual(40, self.trilho.lista.count())
        self.assertEqual("1", self.trilho.lista.item(0).text())
        self.assertTrue(self.rasterizadas, "nenhuma miniatura pedida para as páginas à vista")
        self.assertLess(len(self.rasterizadas), 40, "as miniaturas vêm conforme a pessoa rola, não todas")
        self.assertIsNotNone(self.trilho.miniatura(self.rasterizadas[0]))

    def test_clicar_numa_pagina_pede_a_pagina_e_refletir_nao_pede(self) -> None:
        pedidas: list[int] = []
        self.trilho.pagina_pedida.connect(pedidas.append)
        self.trilho.abrir_livro(Path("livro.pdf"), 10)
        self.trilho.marcar_pagina_atual(3)
        self.assertEqual([], pedidas, "refletir a página do visor não é pedir página")
        self.assertEqual(3, self.trilho.lista.currentRow())
        self.trilho.lista.setCurrentRow(7)
        self.assertEqual([7], pedidas)

    def test_os_estados_pintam_as_linhas_e_acendem_os_botoes(self) -> None:
        from chess_diagram_ocr.qt import tema, trilho

        self.trilho.abrir_livro(Path("livro.pdf"), 4)
        self.assertFalse(self.trilho.btn_duvidosa.isEnabled())
        estados = [
            _EstadoDaSuite(0),
            _EstadoDaSuite(1, diagramas=2, diagramas_lidos=1, duvidosos=1),
            _EstadoDaSuite(2, revisada=True),
            _EstadoDaSuite(3, montada=False, texto=False),
        ]
        self.trilho.definir_estados(estados, resumo="4 páginas")
        self.assertIn(GLIFO_DUVIDA, self.trilho.lista.item(1).text())
        self.assertEqual(
            tema.cor_atual(tokens.ATENCAO).lower(),
            self.trilho.lista.item(1).foreground().color().name().lower(),
        )
        self.assertEqual("4", self.trilho.lista.item(3).text(), "página não montada só tem número")
        self.assertTrue(self.trilho.btn_duvidosa.isEnabled())
        self.assertEqual(trilho.suite_disponivel(), self.trilho.btn_exportar.isEnabled())
        self.assertEqual("4 páginas", self.trilho.resumo.text())

        pedidas: list[int] = []
        self.trilho.pagina_pedida.connect(pedidas.append)
        self.trilho.btn_duvidosa.click()
        self.assertEqual([1], pedidas)
        self.assertEqual(1, self.trilho.lista.currentRow())

    def test_a_importacao_troca_os_botoes_e_mostra_a_barra(self) -> None:
        self.trilho.abrir_livro(Path("livro.pdf"), 6)
        self.trilho.importacao_comecou(12)
        self.assertFalse(self.trilho.btn_importar.isVisibleTo(self.trilho))
        self.assertTrue(self.trilho.btn_cancelar.isVisibleTo(self.trilho))
        self.assertTrue(self.trilho.progresso.isVisibleTo(self.trilho))
        self.trilho.importacao_avancou(9, 12)
        self.assertEqual(9, self.trilho.progresso.value())
        from chess_diagram_ocr.qt import tema

        self.trilho.marcar_montada(2)
        self.assertEqual(
            tema.cor_atual(tokens.TEXTO_PADRAO).lower(),
            self.trilho.lista.item(2).foreground().color().name().lower(),
            "a página montada acende (sai do cinza de 'ainda não lida') antes do fim",
        )
        self.trilho.importacao_terminou()
        self.assertTrue(self.trilho.btn_importar.isVisibleTo(self.trilho))
        self.assertFalse(self.trilho.progresso.isVisibleTo(self.trilho))

    def test_os_botoes_vem_do_catalogo(self) -> None:
        from chess_diagram_ocr.ui import comandos

        self.assertEqual(comandos.rotulo_de_botao("importar_livro"), self.trilho.btn_importar.text())
        self.assertEqual(comandos.nome_acessivel("primeira_duvidosa"), self.trilho.btn_duvidosa.accessibleName())
        self.assertEqual(comandos.rotulo_de_botao("exportar_epub"), self.trilho.btn_exportar.text())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
