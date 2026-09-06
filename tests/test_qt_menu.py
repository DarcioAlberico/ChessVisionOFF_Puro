"""A barra de menus do segundo frontend (S-161/S-324/S-501).

**O que estes testes cobrem, e o que não.** A declaração `MENUS` -- que menus existem, que itens
cada um tem, que todo item está no catálogo -- é pura e já é afirmada em `tests/test_ui_menu.py`.
Repetir aquilo aqui mediria o mesmo código duas vezes, e a graça deste módulo é justamente não
ter uma segunda declaração.

O que só existe deste lado são três coisas:

1. **A montagem alcança a declaração inteira.** Um `elif` esquecido não levanta: ele desenha um
   menu com menos itens, e ninguém compara as duas janelas linha a linha.
2. **O acelerador é mostrado e não ligado.** Se a `QAction` ficar com a tecla, `←` dispara com o
   cursor dentro do campo de FEN -- o defeito da S-20, reintroduzido por uma conveniência do Qt.
3. **A trava de `montar`.** Um menu que desenha uma linha inerte é pior que um menu sem ela.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import atalhos, pele
from chess_diagram_ocr.ui import comandos as catalogo
from chess_diagram_ocr.ui import menu as declaracao

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMainWindow, QMenu

    from chess_diagram_ocr.qt import menu as qt_menu


def comandos_de_mentira(chamadas: list[str]) -> dict[str, object]:
    """Uma função por ação declarada, cada uma registrando o próprio nome."""
    return {acao: (lambda acao=acao: chamadas.append(acao)) for acao in declaracao.acoes_declaradas()}


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MontagemTests(unittest.TestCase):
    """A barra sai da mesma declaração, inteira."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.chamadas: list[str] = []
        self.janela = QMainWindow()
        self.addCleanup(self.janela.deleteLater)
        self.montada = qt_menu.montar(self.janela, comandos_de_mentira(self.chamadas))

    def menus(self) -> list[QMenu]:
        return [acao.menu() for acao in self.montada.barra.actions() if acao.menu() is not None]

    def test_os_sete_menus_da_declaracao_estao_na_barra(self) -> None:
        self.assertEqual(
            [menu.title() for menu in self.menus()],
            [declarado.titulo for declarado in declaracao.MENUS],
        )

    def test_todo_comando_declarado_virou_linha(self) -> None:
        """**O teste que dá sentido ao módulo.**

        Um `elif` esquecido em `montar` não levanta: ele desenha um menu com menos itens, e o
        sintoma é uma janela em que "Abrir o log" simplesmente não existe. Aqui a declaração e a
        barra são comparadas ação a ação.
        """
        esperadas = {
            item.acao
            for declarado in declaracao.MENUS
            for item in declarado.itens
            if item.tipo in (declaracao.COMANDO, declaracao.INTERRUPTOR)
        }
        self.assertEqual(set(self.montada.acoes), esperadas)

    def test_os_submenus_de_escolha_e_de_recentes_tambem(self) -> None:
        escolhas = {
            item.acao
            for declarado in declaracao.MENUS
            for item in declarado.itens
            if item.tipo in declaracao.TIPOS_DE_ESCOLHA
        }
        self.assertEqual(set(self.montada.grupos), escolhas)

    def test_o_rotulo_vem_do_catalogo_e_nao_e_escrito_aqui(self) -> None:
        """A fronteira da S-324: `ui/menu.py` decide *onde*, o catálogo decide *o que*.

        O menu escrevia o texto que `ui/pdf_panel.py` escrevia de novo, com outra redação, e nada
        comparava os dois. Um frontend novo que escrevesse o texto dele traria de volta o mesmo
        defeito, agora entre janelas.
        """
        for acao, item in self.montada.acoes.items():
            with self.subTest(acao=acao):
                self.assertEqual(item.text(), catalogo.rotulo(acao))

    def test_clicar_no_item_chama_o_comando_amarrado(self) -> None:
        self.montada.acoes["salvar"].trigger()
        self.assertEqual(self.chamadas, ["salvar"])

    def test_a_barra_e_pendurada_na_janela_principal(self) -> None:
        self.assertIs(self.janela.menuBar(), self.montada.barra)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AceleradorTests(unittest.TestCase):
    """Mostrado e não ligado: quem responde por tecla é a guarda de `qt/atalhos.py`."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.chamadas: list[str] = []
        self.janela = QMainWindow()
        self.addCleanup(self.janela.deleteLater)
        self.montada = qt_menu.montar(self.janela, comandos_de_mentira(self.chamadas))

    def test_o_item_com_atalho_mostra_o_acelerador(self) -> None:
        """Depois da S-150 a legenda deixou de ser conveniência: num notebook, `Ctrl+S` era o
        único caminho para salvar. Um menu que não mostra a tecla esconde isso."""
        for acao in atalhos.por_acao:
            item = self.montada.acoes.get(acao)
            if item is None:
                continue  # a ação existe na tabela mas não tem linha de menu
            with self.subTest(acao=acao):
                self.assertFalse(item.shortcut().isEmpty(), f"{acao} não mostra acelerador")

    def test_a_qaction_nao_fica_dona_da_tecla(self) -> None:
        """**Se ela ficar, `←` dispara com o cursor dentro do campo de FEN.**

        É o defeito da S-20 reintroduzido por uma conveniência do Qt: `setShortcut` liga a tecla
        junto com o texto, e a `QAction` não sabe ceder. Quem tem de responder é a guarda, que é
        a única peça que conhece as três respostas da S-294.
        """
        for acao, item in self.montada.acoes.items():
            if item.shortcut().isEmpty():
                continue
            with self.subTest(acao=acao):
                self.assertEqual(
                    item.shortcutContext(),
                    Qt.ShortcutContext.WidgetShortcut,
                    f"{acao} disputaria a tecla com a guarda de foco",
                )

    def test_o_acelerador_e_o_mesmo_que_a_guarda_traduz(self) -> None:
        """Duas traduções da mesma tabela divergiriam, e o menu mentiria sobre a tecla."""
        from PyQt6.QtGui import QKeySequence

        from chess_diagram_ocr.qt.atalhos import sequencia_qt

        for acao, item in self.montada.acoes.items():
            atalho = atalhos.por_acao.get(acao)
            if atalho is None:
                continue
            with self.subTest(acao=acao):
                self.assertEqual(item.shortcut(), QKeySequence(sequencia_qt(atalho.sequencia)))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EscolhaEInterruptorTests(unittest.TestCase):
    """A marca, que no Tk mora numa variável do Tcl e aqui é estado da `QAction`."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.chamadas: list[str] = []
        self.janela = QMainWindow()
        self.addCleanup(self.janela.deleteLater)
        self.montada = qt_menu.montar(self.janela, comandos_de_mentira(self.chamadas))

    def test_o_interruptor_e_marcavel(self) -> None:
        for acao in ("marcar_diagramas", "roda_vira_pagina", "modo_bloco", "quebrar_linha"):
            with self.subTest(acao=acao):
                self.assertTrue(self.montada.acoes[acao].isCheckable())

    def test_marcar_nao_dispara_o_comando(self) -> None:
        """**O laço que `toggled` criaria e `triggered` não cria.**

        `marcar` é chamada pelo painel para *refletir* estado. Com `toggled`, refletir o estado
        rodaria o comando que produziu aquele estado -- um laço que no Tk não existe porque lá a
        variável e o comando são coisas separadas.
        """
        self.montada.marcar("modo_bloco", ligado=True)
        self.assertTrue(self.montada.acoes["modo_bloco"].isChecked())
        self.assertEqual(self.chamadas, [], "refletir estado disparou o comando")

    def test_marcar_o_que_nao_e_interruptor_e_silencioso(self) -> None:
        """Quem levanta é `montar`, na montagem. Refletir estado não derruba janela."""
        self.montada.marcar("salvar", ligado=True)
        self.montada.marcar("acao_que_nao_existe", ligado=True)
        self.assertFalse(self.montada.acoes["salvar"].isChecked())

    def test_a_pele_escolhida_e_a_unica_marcada(self) -> None:
        self.montada.escolher("aparencia", pele.FOCO)
        marcadas = [a.data() for a in self.montada.grupos["aparencia"].actions() if a.isChecked()]
        self.assertEqual(marcadas, [pele.FOCO])

    def test_o_submenu_de_pele_sai_do_registro_e_nao_de_uma_lista_a_mao(self) -> None:
        grupo = self.montada.grupos["aparencia"]
        self.assertEqual([a.data() for a in grupo.actions()], [p.nome for p in pele.PELES])
        self.assertEqual([a.text() for a in grupo.actions()], [p.rotulo for p in pele.PELES])

    def test_o_valor_fica_no_data_e_nao_no_rotulo(self) -> None:
        """`pele.Pele` separa `nome` de `rotulo` desde a S-166: chave e texto de interface."""
        grupo = self.montada.grupos["aparencia"]
        classica = next(a for a in grupo.actions() if a.data() == pele.CLASSICA)
        self.assertNotEqual(classica.text(), classica.data())

    def test_escolher_valor_desconhecido_e_silencioso(self) -> None:
        self.montada.escolher("aparencia", "pele-que-nao-existe")
        self.montada.escolher("acao-que-nao-existe", pele.FOCO)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RecentesTests(unittest.TestCase):
    """Os livros recentes, refeitos a cada abertura (S-156)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.chamadas: list[str] = []
        self.janela = QMainWindow()
        self.addCleanup(self.janela.deleteLater)
        self.livros: list[tuple[str, object]] = []
        self.montada = qt_menu.montar(
            self.janela, comandos_de_mentira(self.chamadas), recentes=lambda: self.livros
        )

    def submenu(self) -> QMenu:
        arquivo = next(a.menu() for a in self.montada.barra.actions() if a.text() == "Arquivo")
        alvo = catalogo.rotulo("abrir_recente")
        return next(a.menu() for a in arquivo.actions() if a.text() == alvo)

    def test_o_submenu_e_refeito_a_cada_abertura(self) -> None:
        """Um submenu montado uma vez mostraria o acervo de quando a janela subiu."""
        submenu = self.submenu()
        self.livros = [("Aagaard.pdf", lambda: self.chamadas.append("aagaard"))]
        submenu.aboutToShow.emit()
        self.assertEqual([a.text() for a in submenu.actions()], ["Aagaard.pdf"])

        self.livros = [("Anand.pdf", lambda: self.chamadas.append("anand"))]
        submenu.aboutToShow.emit()
        self.assertEqual([a.text() for a in submenu.actions()], ["Anand.pdf"])

    def test_sem_livro_o_submenu_diz_isso_em_vez_de_ficar_vazio(self) -> None:
        """Um submenu vazio no Qt é um retângulo de dois pixels, e quem o abre conclui que o
        menu está quebrado em vez de concluir que não abriu livro nenhum."""
        submenu = self.submenu()
        submenu.aboutToShow.emit()
        self.assertEqual(len(submenu.actions()), 1)
        self.assertFalse(submenu.actions()[0].isEnabled())

    def test_clicar_num_recente_abre_aquele_livro(self) -> None:
        self.livros = [("Aagaard.pdf", lambda: self.chamadas.append("aagaard"))]
        submenu = self.submenu()
        submenu.aboutToShow.emit()
        submenu.actions()[0].trigger()
        self.assertEqual(self.chamadas, ["aagaard"])

    def test_ler_o_estado_que_levanta_nao_derruba_o_menu(self) -> None:
        def explode() -> list[tuple[str, object]]:
            raise RuntimeError("o estado não abriu")

        janela = QMainWindow()
        self.addCleanup(janela.deleteLater)
        montada = qt_menu.montar(janela, comandos_de_mentira(self.chamadas), recentes=explode)
        arquivo = next(a.menu() for a in montada.barra.actions() if a.text() == "Arquivo")
        alvo = catalogo.rotulo("abrir_recente")
        submenu = next(a.menu() for a in arquivo.actions() if a.text() == alvo)
        with self.assertLogs("chess_diagram_ocr.qt.menu", level="ERROR"):
            submenu.aboutToShow.emit()
        self.assertEqual(len(submenu.actions()), 1, "devia cair na linha de 'nenhum livro'")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class TravaTests(unittest.TestCase):
    """A mesma trava de `ui/menu.montar`, e ela é o motivo de o menu ser confiável."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.janela = QMainWindow()
        self.addCleanup(self.janela.deleteLater)

    def test_item_sem_comando_levanta_em_vez_de_desenhar_linha_inerte(self) -> None:
        """Uma linha que não faz nada é pior que a ausência dela: a pessoa conclui que a função
        existe e está quebrada."""
        with self.assertRaises(KeyError) as erro:
            qt_menu.montar(self.janela, {"salvar": lambda: None})
        self.assertIn("sem comando", str(erro.exception))

    def test_a_mensagem_nomeia_o_que_falta(self) -> None:
        """Bissectar isso à mão é o que a S-161 evitou nomeando o item na exceção."""
        faltando = dict(comandos_de_mentira([]))
        faltando.pop("salvar")
        with self.assertRaises(KeyError) as erro:
            qt_menu.montar(self.janela, faltando)
        self.assertIn("salvar", str(erro.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
