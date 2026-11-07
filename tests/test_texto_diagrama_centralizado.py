"""O diagrama que ninguém alinhou fica no centro -- na tela e no arquivo (S-620).

O dono do projeto pediu os diagramas centralizados por padrão e à esquerda por escolha. A
distinção já existia em `rico`: `""` é "ninguém alinhou" e `esquerda` é uma escolha escrita. O que
faltava era alguém **responder** o `""` da marca do diagrama -- e responder num lugar só,
`rico.alinhamento_efetivo`, para a figura não sair centralizada na tela e à esquerda no `.html`.
"""

from __future__ import annotations

import unittest

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import exportacao, rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TEM_PYQT:
    from paridade_do_texto import divergencias
    from PyQt6.QtCore import Qt

    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import OBJETO, PainelDeTexto


def _texto(conteudo: str) -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas([LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), 1.0, "camada", None, None)])  # type: ignore[arg-type]


def _documento() -> rico.DocumentoRico:
    pagina = PaginaLida(
        documento="livro.pdf",
        pagina=0,
        colunas=(Coluna(indice=0, blocos=(_texto("Antes."), BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 60.0, 60.0)), _texto("Depois."))),),
    )
    return rico.de_pagina(pagina)


def _marca(doc: rico.DocumentoRico) -> tuple[int, int]:
    inicio = doc.para_texto().index("[Diagrama 1]")
    return inicio, inicio + len("[Diagrama 1]")


class AlinhamentoEfetivoTests(unittest.TestCase):
    def test_a_marca_sem_escolha_vai_para_o_centro(self) -> None:
        marca = next(c for c in _documento().corridas if c.e_diagrama)
        self.assertEqual(marca.atributos.alinhamento, "", "ninguém alinhou")
        self.assertEqual(rico.alinhamento_efetivo(marca), rico.ALINHAMENTO_CENTRO)

    def test_a_escolha_escrita_vence_o_padrao(self) -> None:
        doc = rico.aplicar_alinhamento(_documento(), *_marca(_documento()), rico.ALINHAMENTO_ESQUERDA)
        marca = next(c for c in doc.corridas if c.e_diagrama)
        self.assertEqual(rico.alinhamento_efetivo(marca), rico.ALINHAMENTO_ESQUERDA)

    def test_o_texto_sem_escolha_continua_sem_alinhamento(self) -> None:
        """O padrão é da figura: parágrafo que ninguém alinhou continua à esquerda, como texto se desenha."""
        prosa = next(c for c in _documento().corridas if c.texto == "Antes.")
        self.assertEqual(rico.alinhamento_efetivo(prosa), "")

    def test_o_padrao_e_parametro(self) -> None:
        """A preferência "à esquerda" da Fase 92 entra por aqui, sem segundo caminho."""
        marca = next(c for c in _documento().corridas if c.e_diagrama)
        self.assertEqual(rico.alinhamento_efetivo(marca, padrao_do_diagrama=rico.ALINHAMENTO_ESQUERDA), "esquerda")


class ExportacaoTests(unittest.TestCase):
    def test_o_html_centraliza_o_diagrama_sem_escolha(self) -> None:
        html = exportacao.exportar(_documento(), exportacao.Html()).conteudo
        self.assertIn('<div class="alinhar-centro">', html)

    def test_o_rtf_tambem(self) -> None:
        self.assertIn("\\qc", exportacao.exportar(_documento(), exportacao.Rtf()).conteudo)

    def test_o_diagrama_alinhado_a_esquerda_nao_e_centralizado(self) -> None:
        doc = rico.aplicar_alinhamento(_documento(), *_marca(_documento()), rico.ALINHAMENTO_ESQUERDA)
        html = exportacao.exportar(doc, exportacao.Html()).conteudo
        self.assertNotIn('<div class="alinhar-centro">', html)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TelaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(700, 500)
        self.painel.show()
        self.app.processEvents()

    def bloco_da_figura(self):
        bloco = self.painel.editor.document().begin()
        while bloco.isValid() and OBJETO not in bloco.text():
            bloco = bloco.next()
        return bloco

    def test_a_folha_nova_desenha_a_figura_no_centro(self) -> None:
        self.painel.abrir(_documento(), folha_rgb=np.full((400, 400, 3), 210, np.uint8))
        self.assertEqual(self.bloco_da_figura().blockFormat().alignment(), Qt.AlignmentFlag.AlignHCenter)
        self.assertEqual(divergencias(self.painel), [])

    def test_a_figura_alinhada_a_esquerda_fica_a_esquerda(self) -> None:
        doc = rico.aplicar_alinhamento(_documento(), *_marca(_documento()), rico.ALINHAMENTO_ESQUERDA)
        self.painel.abrir(doc, folha_rgb=np.full((400, 400, 3), 210, np.uint8))
        self.assertEqual(self.bloco_da_figura().blockFormat().alignment(), Qt.AlignmentFlag.AlignLeft)

    def test_centralizar_por_padrao_nao_e_alteracao_por_gravar(self) -> None:
        """O padrão é desenho: abrir a folha não a torna "editada"."""
        self.painel.abrir(_documento(), folha_rgb=np.full((400, 400, 3), 210, np.uint8))
        self.assertFalse(self.painel.tem_alteracoes)


if __name__ == "__main__":
    unittest.main()
