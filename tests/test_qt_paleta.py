"""A paleta de comandos do segundo frontend (S-231/S-503).

**O que estes testes cobrem, e o que não.** A ordem do resultado -- o casamento por subsequência,
o vão, o grupo por trecho, a linha cinza que desce só no empate -- é pura e já é afirmada em
`tests/test_ui_paleta_de_comandos.py`. Repetir aquilo aqui mediria o mesmo código duas vezes.

O que só existe deste lado são as quatro coisas em que o Qt difere do Tk e que quebram calado:

1. **A seta mora no campo**, e o filtro de eventos que a leva à lista tem de comer o evento --
   senão o `Enter` chega ao diálogo, que o trata como botão padrão e fecha a paleta *depois* de
   `executar` ter decidido não fechar.
2. **A linha cinza é por item**, porque o Qt não tem tag: esquecer a cor deixa o comando
   indisponível com a aparência do disponível, que é metade do critério de aceite da S-231.
3. **`accept()` fecha antes de o comando rodar**, e a ordem importa: metade destes comandos abre
   uma caixa de diálogo.
4. **Reabrir não recarrega o inventário**, para não apagar a consulta digitada.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import filtro_de_comandos

if TEM_PYQT:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication, QWidget

    from chess_diagram_ocr.qt import paleta as qt_paleta
    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.ui import tokens


class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e este módulo não a reescreve.

    Sem `skipUnless`: nada aqui importa PyQt6, e o par que ele confere -- o Tk reexportando o
    módulo puro -- é o que sustenta o outro lado poder chamá-lo.
    """

    def test_o_modulo_puro_nao_carrega_tkinter(self) -> None:
        """É a razão de ele existir: `JanelaDaPaleta` herda de `tk.Toplevel`, e classe-base é
        avaliada na importação -- então ler o filtro pelo módulo antigo carrega o Tk junto."""
        import ast
        from pathlib import Path

        fonte = Path(filtro_de_comandos.__file__).read_text(encoding="utf-8")
        importados = {
            no.names[0].name.split(".")[0]
            for no in ast.walk(ast.parse(fonte))
            if isinstance(no, ast.Import)
        } | {
            (no.module or "").split(".")[0]
            for no in ast.walk(ast.parse(fonte))
            if isinstance(no, ast.ImportFrom)
        }
        self.assertNotIn("tkinter", importados)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class JanelaTests(unittest.TestCase):
    """O diálogo montado sobre o filtro puro."""

    def setUp(self) -> None:
        self.app = aplicacao()
        # O foco vaza entre testes de Qt: `deleteLater` só marca, e o widget do teste anterior
        # segue vivo até a linha de eventos girar. Ver o cabeçalho de `tests/qt_app.py`.
        anterior = QApplication.focusWidget()
        if anterior is not None:
            anterior.clearFocus()
        self.rodados: list[str] = []
        self.pai = QWidget()
        self.addCleanup(descartar, self.pai)

    def paleta(self, **amarrados: object) -> qt_paleta.JanelaDaPaleta:
        ligadas = amarrados or {
            "ler_pagina": lambda: self.rodados.append("ler_pagina"),
            "limpar_tabuleiro": lambda: self.rodados.append("limpar_tabuleiro"),
        }
        janela = qt_paleta.JanelaDaPaleta(self.pai, ligadas)  # type: ignore[arg-type]
        janela.show()
        janela.activateWindow()
        self.app.processEvents()
        return janela

    def apertar(self, janela: qt_paleta.JanelaDaPaleta, tecla: Qt.Key) -> None:
        """Aperta a tecla **no campo**, conferindo antes que o foco é mesmo dele.

        A conferência não é zelo: sob `offscreen` o `setFocus` de um widget cuja janela nunca foi
        mostrada não faz nada, e sem ela este teste mediria o filtro de eventos com o foco de
        outro widget -- passando por um caminho que não é o que ele afirma.
        """
        janela.campo.setFocus()
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), janela.campo, "o foco não foi para o campo")
        self.app.sendEvent(janela.campo, QKeyEvent(QEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))

    def test_a_seta_no_campo_anda_na_lista(self) -> None:
        janela = self.paleta()
        primeira = janela.selecionada()
        self.apertar(janela, Qt.Key.Key_Down)
        self.assertEqual(janela.selecionada(), janela.visiveis()[1])
        self.apertar(janela, Qt.Key.Key_Up)
        self.assertEqual(janela.selecionada(), primeira)

    def test_a_seta_nao_da_a_volta_na_ponta(self) -> None:
        """Uma lista circular faz a última linha aparecer onde a primeira deveria estar."""
        janela = self.paleta()
        self.apertar(janela, Qt.Key.Key_Up)
        self.assertEqual(janela.selecionada(), janela.visiveis()[0])

    def test_o_campo_continua_editavel_com_as_setas_ligadas(self) -> None:
        """O filtro come `Up`/`Down`/`Enter` e mais nada: as outras teclas são do campo."""
        janela = self.paleta()
        janela.campo.setFocus()
        self.app.processEvents()
        janela.digitar("ler")
        self.assertEqual(janela.campo.text(), "ler")
        self.assertTrue(janela.visiveis())

    def test_enter_executa_o_selecionado_e_fecha_antes(self) -> None:
        """Fechar antes é a ordem, e não detalhe: metade destes comandos abre uma caixa."""
        ordem: list[str] = []
        janela = self.paleta(ler_pagina=lambda: ordem.append(f"visivel={janela.isVisible()}"))
        janela.digitar("ler esta pagina")
        self.assertEqual(janela.selecionada().acao, "ler_pagina")
        self.apertar(janela, Qt.Key.Key_Return)
        self.assertEqual(ordem, ["visivel=False"])

    def test_enter_na_linha_cinza_nao_faz_nada_e_nao_fecha(self) -> None:
        """O `Enter` tem de ser comido pelo filtro: sem isso o diálogo o trata como botão padrão
        e fecha a paleta que `executar` decidiu deixar aberta."""
        janela = self.paleta(ler_pagina=lambda: self.rodados.append("ler_pagina"))
        janela.digitar("limpar o tabuleiro")
        selecionada = janela.selecionada()
        self.assertFalse(selecionada.habilitado, "o caso precisa de uma linha sem função amarrada")
        self.apertar(janela, Qt.Key.Key_Return)
        self.assertEqual(self.rodados, [])
        self.assertTrue(janela.isVisible())

    def test_a_linha_cinza_e_pintada_por_item(self) -> None:
        """O Qt não tem tag: a cor vai em cada célula, ou o indisponível fica igual ao disponível."""
        janela = self.paleta(ler_pagina=lambda: None)
        cinza = tema.cor_atual(tokens.TEXTO_SECUNDARIO)
        vistas = {True: set(), False: set()}
        for posicao, entrada in enumerate(janela.visiveis()):
            item = janela.lista.topLevelItem(posicao)
            vistas[entrada.habilitado].add(item.foreground(0).color().name().lower())
        self.assertEqual(vistas[False], {cinza.lower()})
        self.assertNotIn(cinza.lower(), vistas[True])

    def test_o_motivo_vai_na_linha_junto_do_rotulo(self) -> None:
        """"Cinza e com o motivo, e não some" -- o texto da célula é `Entrada.no_texto`."""
        janela = self.paleta(ler_pagina=lambda: None)
        janela.digitar("limpar o tabuleiro")
        entrada = janela.selecionada()
        self.assertEqual(entrada.motivo, filtro_de_comandos.MOTIVO_SEM_FUNCAO)
        self.assertIn(entrada.motivo, janela.lista.topLevelItem(0).text(0))

    def test_a_consulta_vazia_traz_o_catalogo_inteiro(self) -> None:
        janela = self.paleta()
        self.assertEqual(len(janela.visiveis()), len(filtro_de_comandos.inventario()))
        self.assertEqual(janela.lista.topLevelItemCount(), len(janela.visiveis()))

    def test_reabrir_traz_a_mesma_janela_e_guarda_a_consulta(self) -> None:
        """A tecla que abre é a que se aperta quando nada parece ter acontecido."""
        primeira = qt_paleta.abrir(self.pai, {"ler_pagina": lambda: None})
        primeira.digitar("pag")
        segunda = qt_paleta.abrir(self.pai, {})
        self.assertIs(segunda, primeira)
        self.assertEqual(segunda.campo.text(), "pag")

    def test_a_lista_e_a_tabela_do_pacote_e_nao_um_treewidget_cru(self) -> None:
        """A largura mínima por seção e a coluna que estica são as regras da S-153."""
        from chess_diagram_ocr.qt.tabela import TabelaQt

        janela = self.paleta()
        self.assertIsInstance(janela.lista, TabelaQt)
        self.assertEqual(janela.lista.colunas, filtro_de_comandos.COLUNAS)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
