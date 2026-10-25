"""O texto ao lado do diagrama à esquerda (S-624, `docs/ROADMAP_MESA_DE_TEXTO.md`).

As cinco conferências do portão (`cli/texto_flutuante.conferir`) sobre uma folha sintética, nas duas
vistas: com o texto ao lado toda figura flutua e o editor continua certo; no desenho de hoje nenhuma
flutua -- o controle que prova que a conta de "flutua" mede alguma coisa.
"""

from __future__ import annotations

import unittest

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.cli import texto_flutuante
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui.state import AppState, load_state, save_state

if TEM_PYQT:
    import numpy as np

    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import OBJETO, PainelDeTexto

PROSA = "As brancas jogam e ganham, porque o cavalo chega a tempo de cobrir a casa de promoção. " * 3


def _folha(quantos: int = 2) -> PaginaLida:
    blocos: list[object] = []
    for indice in range(quantos):
        blocos.append(BlocoDeDiagrama(indice=indice, bbox=(10.0, 10.0 + 90 * indice, 90.0, 90.0 + 90 * indice)))
        blocos.append(BlocoDeTexto.de_linhas([LinhaLida(PROSA, (100.0, 10.0 + 90 * indice, 300.0, 20.0 + 90 * indice), 0.9, "glifo")]))  # type: ignore[arg-type]
    return PaginaLida(documento="livro.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=tuple(blocos)),))  # type: ignore[arg-type]


class PuroTests(unittest.TestCase):
    def test_a_folha_do_argumento_conta_de_um(self) -> None:
        self.assertEqual(texto_flutuante.folha_do_argumento("Kemeri 1937.pdf:53"), ("Kemeri 1937.pdf", 52))
        self.assertEqual(texto_flutuante.folha_do_argumento("C:/livros/a:b.pdf:2"), ("C:/livros/a:b.pdf", 1))
        for errado in ("livro.pdf", "livro.pdf:0", ":3", "livro.pdf:x"):
            with self.subTest(errado=errado), self.assertRaises(ValueError):
                texto_flutuante.folha_do_argumento(errado)

    def test_o_veredito_pede_as_duas_vistas_certas_e_o_controle_sem_flutuar(self) -> None:
        def folha(ao_lado: dict, controle: dict) -> dict:
            return {"livro": "a.pdf", "folha": 1, "ao_lado": ao_lado, "controle": controle}

        certo = {"figuras": 2, "flutuam": 2, "editor_certo": True}
        parado = {"figuras": 2, "flutuam": 0, "editor_certo": True}
        self.assertTrue(texto_flutuante.veredito([folha(certo, parado)])["passa"])
        self.assertFalse(texto_flutuante.veredito([folha({**certo, "flutuam": 1}, parado)])["passa"])
        self.assertFalse(texto_flutuante.veredito([folha({**certo, "editor_certo": False}, parado)])["passa"])
        self.assertFalse(texto_flutuante.veredito([folha(certo, {**parado, "flutuam": 2})])["passa"], "controle que flutua")
        self.assertFalse(texto_flutuante.veredito([])["passa"])

    def test_o_interruptor_vai_e_volta_do_arquivo_de_estado(self) -> None:
        caminho = pasta_temporaria(self) / "estado.json"
        save_state(caminho, AppState(texto_ao_lado=True))
        self.assertTrue(load_state(caminho).texto_ao_lado)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AoLadoNaTelaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(700, 900)
        self.painel.show()
        self.app.processEvents()
        self.painel.definir_diagramas("esquerda")
        self.painel.mostrar_pagina(_folha(), folha_rgb=np.full((400, 400, 3), 200, np.uint8), dpi=72)
        self.texto_cru = self.painel.editor.document().toRawText()

    def test_com_o_texto_ao_lado_as_duas_figuras_flutuam_e_o_editor_continua_certo(self) -> None:
        self.painel.definir_texto_ao_lado(True)
        conferencia = texto_flutuante.conferir(self.painel)
        self.assertEqual((conferencia.figuras, conferencia.flutuam), (2, 2))
        self.assertTrue(conferencia.editor_certo, conferencia.como_dado())

    def test_o_desenho_de_hoje_e_o_controle_nenhuma_flutua(self) -> None:
        conferencia = texto_flutuante.conferir(self.painel)
        self.assertEqual((conferencia.figuras, conferencia.flutuam), (2, 0))
        self.assertTrue(conferencia.editor_certo, conferencia.como_dado())

    def test_o_texto_cru_e_o_mesmo_e_a_folha_nao_fica_por_gravar(self) -> None:
        # O `QTextFrame` pelo cursor poria U+FDD0/U+FDD1 no texto cru; a figura do `<img align=left>` não.
        self.painel.definir_texto_ao_lado(True)
        self.assertEqual(self.painel.editor.document().toRawText(), self.texto_cru)
        self.assertEqual(self.texto_cru.count(OBJETO), 2)
        self.assertFalse(self.painel.tem_alteracoes, "o texto ao lado tornou a folha por gravar")

    def test_a_figura_que_flutua_guarda_o_texto_alternativo(self) -> None:
        from PyQt6.QtGui import QTextFormat

        self.painel.definir_texto_ao_lado(True)
        bloco = self.painel.editor.document().begin()
        alternativos = []
        while bloco.isValid():
            iterador = bloco.begin()
            while not iterador.atEnd():
                formato = iterador.fragment().charFormat()
                if formato.isImageFormat():
                    alternativos.append(formato.property(QTextFormat.Property.ImageAltText))
                iterador += 1
            bloco = bloco.next()
        self.assertEqual(alternativos, ["Diagrama 1", "Diagrama 2"])

    def test_so_flutua_o_que_se_desenha_a_esquerda(self) -> None:
        self.painel.definir_texto_ao_lado(True)
        self.painel.definir_diagramas("")  # ao centro: o texto ao lado não se aplica
        conferencia = texto_flutuante.conferir(self.painel)
        self.assertEqual(conferencia.flutuam, 0)

    def test_exportar_a_folha_leva_a_vista_dos_diagramas_ao_arquivo(self) -> None:
        # S-622: o arquivo mostra o que a tela mostra. A aba chamava `exportar` sem a preferência, e
        # com «à esquerda» na tela o `.html` saía centralizado; agora leva ela e o texto ao lado.
        from unittest import mock

        from test_qt_texto_caderno import _TarefaNaHora

        from chess_diagram_ocr.qt import painel_de_texto

        self.painel.definir_texto_ao_lado(True)
        destino = pasta_temporaria(self) / "folha.html"
        with (
            mock.patch.object(painel_de_texto, "Tarefa", _TarefaNaHora),
            mock.patch.object(painel_de_texto.QFileDialog, "getSaveFileName", return_value=(str(destino), "")),
        ):
            self.painel._exportar(".html")
        conteudo = destino.read_text(encoding="utf-8")
        self.assertEqual(conteudo.count('class="diagrama ao-lado"'), 2)

    def test_a_janela_marca_o_interruptor_pela_vista_do_painel(self) -> None:
        self.painel.definir_texto_ao_lado(True)
        self.assertEqual(self.painel.interruptores_da_vista(), {"diagramas_a_esquerda": True, "texto_ao_lado": True})


if __name__ == "__main__":
    unittest.main()
