"""A mesa numa janela própria (S-646, `docs/ROADMAP_MESA_DE_TEXTO.md`), com a janela de verdade.

Os critérios de aceite: destacar e devolver dez vezes não perde seleção, pilha de desfazer nem zoom;
com o foco na janela da mesa, `Del`, setas, `PgUp`/`PgDn` e `Ctrl+N` não mudam nada na principal;
fechar a principal fecha as duas e grava o caderno. E os três pré-requisitos, cada um com o seu teste.
"""

from __future__ import annotations

import unittest
from unittest import mock

from qt_app import MOTIVO, TEM_PYQT

from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui import abas, mesa

if TEM_PYQT:
    from PyQt6 import sip
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QDialog, QScrollArea
    from test_qt_janela import _JanelaComLivro

else:  # pragma: no cover - sem o PyQt6 as classes pulam, mas precisam de uma base para existir
    _JanelaComLivro = unittest.TestCase

TECLAS_DA_PRINCIPAL = ("apagar_casa", "diagrama_anterior", "proximo_diagrama", "pagina_anterior", "proxima_pagina", "proximo_da_fila")


class DecisaoTests(unittest.TestCase):
    def test_a_mesa_atende_so_as_acoes_do_texto(self) -> None:
        self.assertEqual(set(mesa.ACOES_DA_MESA_DESTACADA), {"salvar", "desfazer", "refazer", "achar", "substituir"})
        self.assertFalse(set(TECLAS_DA_PRINCIPAL) & set(mesa.ACOES_DA_MESA_DESTACADA))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MesaDestacadaTests(_JanelaComLivro):
    def setUp(self) -> None:
        super().setUp()
        self.principal = self.janela()
        self.principal.resize(1400, 900)
        self.principal.show()
        self.app.processEvents()
        self.mesa = self.principal.mesa_destacada
        self.addCleanup(self.mesa.janela.close)
        self.texto = self.principal.texto
        linha = LinhaLida("O cavalo chega a tempo de cobrir a casa de promoção.", (0.0, 0.0, 200.0, 10.0), 0.9, "glifo")
        pagina = PaginaLida(documento=str(self.livro), pagina=0, colunas=(Coluna(indice=0, blocos=(BlocoDeTexto.de_linhas([linha]),)),))
        self.texto.mostrar_pagina(pagina)

    def ativar(self, janela: object) -> None:
        janela.show()  # type: ignore[attr-defined]
        janela.activateWindow()  # type: ignore[attr-defined]
        self.app.processEvents()

    def rolagem_do_texto(self) -> QScrollArea:
        return self.principal.principal.pilha.widget(self.principal.principal.modos().index(abas.TEXTO))  # type: ignore[return-value]

    # -------------------------------------------------------------------- o gesto e o cartão

    def test_destacar_leva_o_painel_e_deixa_o_cartao(self) -> None:
        self.mesa.destacar()
        self.assertTrue(self.mesa.destacada)
        self.assertIs(self.texto.window(), self.mesa.janela)
        self.assertIs(self.rolagem_do_texto().widget(), self.mesa.cartao)
        self.assertTrue(self.mesa.janela.isVisible())
        self.mesa.botao_trazer.click()
        self.assertFalse(self.mesa.destacada)
        self.assertIs(self.rolagem_do_texto().widget(), self.texto)
        self.assertFalse(self.mesa.janela.isVisible())

    def test_a_folha_ganha_a_fracao_da_mesa_e_nao_os_restos_da_fita(self) -> None:
        # A fita pede ~980 px de largura mínima; direto no divisor ela deixava 60 px para a folha.
        self.mesa.destacar()
        self.app.processEvents()
        folha, editor = self.mesa.janela.divisor.sizes()
        self.assertGreaterEqual(folha / (folha + editor), mesa.FRACAO_PADRAO - 0.05)

    def test_fechar_a_janela_da_mesa_devolve_o_texto(self) -> None:
        self.mesa.destacar()
        self.mesa.janela.close()
        self.app.processEvents()
        self.assertFalse(self.mesa.destacada)
        self.assertFalse(sip.isdeleted(self.texto))
        self.assertIs(self.rolagem_do_texto().widget(), self.texto)

    def test_o_comando_do_menu_alterna(self) -> None:
        self.principal._comandos()["destacar_mesa"]()
        self.assertTrue(self.mesa.destacada)
        self.principal._comandos()["destacar_mesa"]()
        self.assertFalse(self.mesa.destacada)

    def test_dez_vezes_nao_perdem_selecao_desfazer_nem_zoom(self) -> None:
        self.texto.aplicar_zoom(2, avisar=False)
        self._selecionar(2, 8)
        self.texto.executar("negrito")
        self._selecionar(2, 8)
        antes = (self.texto._selecao_atual(), len(self.texto._historico), self.texto.zoom_da_vista, self.texto.documento)
        self.assertGreater(antes[1], 0, "a pilha precisa ter o que perder")
        for _ in range(10):
            self.mesa.destacar()
            self.mesa.devolver()
        self.assertFalse(sip.isdeleted(self.texto))
        depois = (self.texto._selecao_atual(), len(self.texto._historico), self.texto.zoom_da_vista, self.texto.documento)
        self.assertEqual(depois, antes)
        self.mesa.destacar()
        self.texto.desfazer()
        self.assertFalse(any(c.atributos.negrito for c in self.texto.documento.corridas), "o desfazer de antes continua valendo")

    def _selecionar(self, inicio: int, fim: int) -> None:
        cursor = self.texto.editor.textCursor()
        cursor.setPosition(self.texto._mapa.posicao(inicio))
        cursor.setPosition(self.texto._mapa.posicao(fim), cursor.MoveMode.KeepAnchor)
        self.texto.editor.setTextCursor(cursor)

    # ------------------------------------------------------------ pré-requisito 1: as teclas

    def test_com_o_foco_na_mesa_as_teclas_da_principal_nao_fazem_nada(self) -> None:
        self.mesa.destacar()
        self.ativar(self.mesa.janela)
        visor = self.mesa.janela.visor
        visor.setFocus()
        self.app.processEvents()
        comandos = self.principal._teclas.comandos_de(visor)
        for acao in TECLAS_DA_PRINCIPAL:
            self.assertNotIn(acao, comandos, acao)
        self.assertEqual(set(comandos), set(mesa.ACOES_DA_MESA_DESTACADA))
        pagina = self.principal.pdf.page_index
        for tecla in (Qt.Key.Key_PageDown, Qt.Key.Key_Delete, Qt.Key.Key_Right):
            QTest.keyClick(visor, tecla)
        QTest.keyClick(visor, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertEqual(self.principal.pdf.page_index, pagina, "o PgDn da mesa virou a página da principal")

    def test_o_controle_com_o_foco_na_principal_o_pgdn_vira_a_pagina(self) -> None:
        # Sem isto o teste de cima passaria também com uma guarda que não atendesse tecla nenhuma.
        self.mesa.destacar()
        self.mesa.devolver()
        self.ativar(self.principal)
        self.principal.pdf.visor.setFocus()
        self.app.processEvents()
        pagina = self.principal.pdf.page_index
        QTest.keyClick(self.principal.pdf.visor, Qt.Key.Key_PageDown)
        self.app.processEvents()
        self.assertEqual(self.principal.pdf.page_index, pagina + 1)

    def test_o_dialogo_aberto_da_mesa_e_da_mesa_e_o_da_principal_e_da_principal(self) -> None:
        self.mesa.destacar()
        da_mesa = QDialog(self.texto)
        da_principal = QDialog(self.principal)
        self.addCleanup(da_mesa.deleteLater)
        self.addCleanup(da_principal.deleteLater)
        guarda = self.principal._teclas
        self.assertNotIn("proxima_pagina", guarda.comandos_de(da_mesa))
        self.assertIn("proxima_pagina", guarda.comandos_de(da_principal))
        self.mesa.devolver()
        self.assertIn("proxima_pagina", guarda.comandos_de(da_mesa), "devolvida, a mesa deixa de ter teclado próprio")

    # -------------------------------------------------- pré-requisito 3: quem traz a aba Texto

    def test_inserir_pelo_estudo_traz_a_mesa_e_nao_o_cartao(self) -> None:
        self.principal.abas.mostrar_area(abas.RESULTADO)
        self.mesa.destacar()
        self.mesa.janela.hide()
        self.principal._linha_para_o_texto("1.e4 e5")
        self.assertTrue(self.mesa.janela.isVisible())
        self.assertIn("1.e4 e5", self.texto.texto())
        self.assertNotEqual(self.principal.abas.area_atual(), self.texto, "a janela principal não foi para o cartão")

    # ---------------------------------------------------------------- fechar a principal

    def test_fechar_a_principal_fecha_as_duas_e_grava_o_caderno(self) -> None:
        self.mesa.destacar()
        with mock.patch.object(self.texto, "confirmar_fechamento", wraps=self.texto.confirmar_fechamento) as gravou:
            self.principal.close()
            self.app.processEvents()
        gravou.assert_called_once()
        self.assertFalse(self.mesa.janela.isVisible())
        self.assertFalse(self.mesa.destacada)


if __name__ == "__main__":
    unittest.main()
