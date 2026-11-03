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

    def test_destacada_a_principal_so_arma_na_posicao_sempre(self) -> None:
        largura = mesa.LARGURA_MINIMA
        self.assertTrue(mesa.vale_a_mesa(mesa.MESA_AO_ABRIR_O_TEXTO, texto_a_frente=True, largura=largura))
        self.assertFalse(mesa.vale_a_mesa(mesa.MESA_AO_ABRIR_O_TEXTO, texto_a_frente=True, largura=largura, destacada=True))
        self.assertTrue(mesa.vale_a_mesa(mesa.MESA_SEMPRE, texto_a_frente=True, largura=largura, destacada=True))
        self.assertFalse(mesa.vale_a_mesa(mesa.MESA_NUNCA, texto_a_frente=True, largura=largura, destacada=True))

    def test_a_folha_vizinha_nao_sai_do_livro(self) -> None:
        self.assertEqual(mesa.folha_vizinha(0, +1, 3), 1)
        self.assertIsNone(mesa.folha_vizinha(0, -1, 3))
        self.assertIsNone(mesa.folha_vizinha(2, +1, 3))
        self.assertIsNone(mesa.folha_vizinha(0, +1, 0), "sem o número de folhas não há para onde virar")
        self.assertEqual(mesa.frase_da_folha_da_mesa(12, 289), "Folha 13 de 289")
        self.assertEqual(mesa.frase_da_folha_da_mesa(12, 0), "Folha 13")


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

    def esperar(self, condicao: object, ate_ms: int = 3000) -> bool:
        passos = max(1, ate_ms // 20)
        for _ in range(passos):
            if condicao():  # type: ignore[operator]
                return True
            QTest.qWait(20)
        return bool(condicao())  # type: ignore[operator]

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

    # ------------------------------------------------------------- a folha da janela da mesa

    def test_destacada_a_aba_e_mesa_e_a_principal_desarma_a_dela(self) -> None:
        self.principal._estado.texto_mesa = mesa.MESA_AO_ABRIR_O_TEXTO
        self.principal.abas.mostrar_area(abas.TEXTO)
        self.app.processEvents()
        self.assertTrue(self.principal.mesa.armada, "o controle: com o Texto à frente a principal arma")
        self.mesa.destacar()
        self.assertTrue(self.texto._na_mesa, "na janela da mesa a aba é mesa")
        self.assertFalse(self.principal.mesa.armada, "o PDF ao lado do cartão é a mesa sem o texto")
        self.mesa.devolver()
        self.assertTrue(self.principal.mesa.armada)
        self.assertTrue(self.texto._na_mesa)

    def test_a_seta_vira_a_folha_do_livro_e_a_vista_diz_que_ela_nao_foi_lida(self) -> None:
        self.mesa.destacar()
        janela = self.mesa.janela
        pagina = self.principal.pdf.page_index
        self.assertFalse(janela.botao_anterior.isEnabled(), "na primeira folha não há anterior")
        self.assertTrue(janela.botao_seguinte.isEnabled())
        self.assertIs(janela.pilha_da_folha.currentWidget(), janela.visor)
        janela.botao_seguinte.click()
        self.assertTrue(self.esperar(lambda: self.texto.folha_atual()[0] == pagina + 1), "a aba não acompanhou a folha")
        self.assertEqual(self.principal.pdf.page_index, pagina + 1, "o visualizador do livro não foi junto")
        total = self.principal.pdf.page_count
        self.assertEqual(janela.rotulo_da_folha.text(), mesa.frase_da_folha_da_mesa(pagina + 1, total))
        self.assertIs(janela.pilha_da_folha.currentWidget(), janela.aviso_da_folha, "a vista mostrava a folha de antes")
        self.assertTrue(janela.botao_anterior.isEnabled())
        janela.botao_anterior.click()
        self.assertTrue(self.esperar(lambda: self.texto.folha_atual()[0] == pagina))
        self.assertIn("cavalo", self.texto.texto(), "a folha lida não voltou do caderno")
        self.assertIs(janela.pilha_da_folha.currentWidget(), janela.visor)

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
