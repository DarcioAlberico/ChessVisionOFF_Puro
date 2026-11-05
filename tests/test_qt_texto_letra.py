"""A letra de leitura da aba Texto (S-632, `docs/ROADMAP_MESA_DE_TEXTO.md`).

A família da folha é vista, como o zoom: trocar redesenha com ela, não torna a folha «por gravar», e
volta ao reabrir o programa. A notação fica na monoespaçada nas três.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui import texto_declarado as td
from chess_diagram_ocr.ui.state import AppState, load_state, save_state
from chess_diagram_ocr.ui.tipografia import familia_serifada

if TEM_PYQT:
    from PyQt6.QtGui import QTextCursor

    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto


class FamiliaPuraTests(unittest.TestCase):
    def test_o_comando_anda_em_roda_e_o_desconhecido_vale_o_padrao(self) -> None:
        self.assertEqual(td.proxima_familia_da_letra(""), "serifada")
        self.assertEqual(td.proxima_familia_da_letra("serifada"), "monoespacada")
        self.assertEqual(td.proxima_familia_da_letra("monoespacada"), "")
        self.assertEqual(td.proxima_familia_da_letra("de outra versão"), "serifada")

    def test_a_serifada_e_a_primeira_instalada_ou_a_reserva(self) -> None:
        self.assertEqual(familia_serifada(["Segoe UI", "Times New Roman", "Georgia"], "Segoe UI"), "Georgia")
        self.assertEqual(familia_serifada(["segoe ui", "times new roman"], "Segoe UI"), "Times New Roman")
        self.assertEqual(familia_serifada(["Segoe UI", "Consolas"], "Segoe UI"), "Segoe UI")

    def test_a_familia_vai_e_volta_do_arquivo_de_estado(self) -> None:
        caminho = pasta_temporaria(self) / "estado.json"
        save_state(caminho, AppState(texto_familia="monoespacada"))
        self.assertEqual(load_state(caminho).texto_familia, "monoespacada")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LetraNaTelaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(600, 400)
        self.painel.show()
        self.app.processEvents()
        notacao = replace(rico.PADRAO, estilo=rico.ESTILO_NOTACAO)
        self.painel.abrir(
            rico.DocumentoRico(
                corridas=(
                    rico.Corrida("Uma frase de prosa lida.\n\n"),
                    rico.Corrida("1.e4 e5 2.Cf3", notacao),
                )
            ),
            renderizar=False,
        )
        self.antes = self.painel.tem_alteracoes

    def familia_em(self, deslocamento: int) -> list[str]:
        cursor = QTextCursor(self.painel.editor.document())
        cursor.setPosition(self.painel._mapa.posicao(deslocamento) + 1)
        return list(cursor.charFormat().fontFamilies())

    def test_cada_familia_redesenha_a_prosa_e_deixa_a_notacao_na_monoespacada(self) -> None:
        from paridade_do_texto import divergencias

        _, proporcional, monoespacada = tema.fonte_base()
        esperadas = {"": proporcional, "serifada": tema.familia_serifada(proporcional), "monoespacada": monoespacada}
        notacao = len("Uma frase de prosa lida.\n\n") + 1
        for familia, nome in esperadas.items():
            with self.subTest(familia=familia):
                self.painel.definir_familia_da_letra(familia)
                self.assertEqual(self.familia_em(0), [nome])
                self.assertEqual(self.familia_em(notacao), [monoespacada])
                self.assertEqual(divergencias(self.painel), [])
                self.assertEqual(self.painel.tem_alteracoes, self.antes, "a letra tornou a folha por gravar")

    def test_o_comando_do_menu_anda_e_diz_qual_letra(self) -> None:
        recados: list[str] = []
        self.painel.estado.connect(recados.append)
        self.painel.mudar_familia_da_letra()
        self.assertEqual(self.painel.familia_da_letra, "serifada")
        self.assertTrue(recados and recados[-1].startswith("Letra da folha: serifada"), recados)

    def test_a_letra_sobrevive_a_reabrir_pelo_estado(self) -> None:
        self.painel.definir_familia_da_letra("monoespacada")
        estado = AppState()
        self.painel.anotar_estado(estado)
        self.assertEqual(estado.texto_familia, "monoespacada")

        outro = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "outros")
        self.addCleanup(descartar, outro)
        outro.aplicar_estado(estado)
        self.assertEqual(outro.familia_da_letra, "monoespacada")
        outro.aplicar_estado(AppState(texto_familia="gótica"))
        self.assertEqual(outro.familia_da_letra, "", "família desconhecida volta ao padrão")


if __name__ == "__main__":
    unittest.main()
