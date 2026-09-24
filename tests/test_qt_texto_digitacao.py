"""A digitação na aba Texto do Qt: o que se escreve na folha passa a ser documento.

**O defeito que estes testes fecham.** O editor é editável, e o que se digitava nele ficava só no
widget: `self.documento` -- que é o estado, o que se grava, o que se exporta e o que a busca lê --
continuava sendo a folha de antes. O primeiro redesenho (o negrito seguinte, o `Ctrl+Z`, o zoom)
apagava o texto digitado sem dizer nada, o `.cvtxt` e o `.txt` saíam sem ele, e o mapa de
deslocamento escorregava a cada letra -- o negrito seguinte caía no lugar errado.

O que cada tecla faz com as corridas é de `text/rico.py` e o que fecha um passo de desfazer é de
`ui/texto_declarado.py`, os dois afirmados sem janela em `tests/test_texto_digitacao.py`. Aqui se
afirma a travessia: a tecla de verdade no `QTextEdit` chega ao documento, ao arquivo, à exportação
e ao `Ctrl+Z` -- sem redesenhar a folha a cada tecla.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import arquivo, documento, rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TEM_PYQT:
    from PyQt6.QtCore import QCoreApplication, QEvent, Qt
    from PyQt6.QtGui import QFont, QTextCursor, QTextDocument
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    from test_qt_janela import _JanelaComLivro

    from chess_diagram_ocr.qt import dialogos, tema
    from chess_diagram_ocr.qt import painel_de_texto as qt_texto
    from chess_diagram_ocr.qt.painel_de_texto import OBJETO, PainelDeTexto
else:  # pragma: no cover - sem o PyQt6 as classes pulam, mas precisam de uma base para existir
    _JanelaComLivro = unittest.TestCase


def _bloco(conteudo: str, *, confianca: float = 1.0, procedencia: str = "camada") -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas([LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), confianca, procedencia, None, None)])  # type: ignore[arg-type]


def _pagina() -> PaginaLida:
    """Três blocos: prosa da camada, um diagrama e um parágrafo que o glifo adivinhou."""
    return PaginaLida(
        documento="livro.pdf",
        pagina=0,
        colunas=(
            Coluna(
                indice=0,
                blocos=(
                    _bloco("O bispo vai para c4."),
                    BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 60.0, 60.0)),
                    _bloco("Depois do diagrama.", confianca=0.05, procedencia="glifo"),
                ),
            ),
        ),
    )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Folha(unittest.TestCase):
    """A base: a folha lida, **com a miniatura desenhada**, e o foco no editor.

    Com a miniatura porque é ela que faz o widget ter caracteres que o documento não tem -- sem
    ela, um mapa que escorregasse passaria despercebido em todos os testes.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.painel = PainelDeTexto(dpi=72)
        self.addCleanup(descartar, self.painel)
        self.painel.resize(700, 500)
        self.painel.show()
        self.app.processEvents()
        self.painel.mostrar_pagina(_pagina(), folha_rgb=np.full((400, 400, 3), 210, np.uint8))
        self.editor = self.painel.editor
        self.editor.setFocus()
        self.agora = 100.0
        self.painel._relogio = lambda: self.agora
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)
        self.pasta = pasta_temporaria(self)

    # -- gestos

    def cursor_em(self, deslocamento: int) -> None:
        cursor = self.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(deslocamento))
        self.editor.setTextCursor(cursor)

    def selecionar(self, inicio: int, fim: int) -> None:
        cursor = self.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(inicio))
        cursor.setPosition(self.painel._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def digitar(self, texto: str) -> None:
        QTest.keyClicks(self.editor, texto)

    def tecla(self, tecla: object, modificador: object = None) -> None:
        if modificador is None:
            QTest.keyClick(self.editor, tecla)  # type: ignore[arg-type]
        else:
            QTest.keyClick(self.editor, tecla, modificador)  # type: ignore[arg-type]

    def onde(self, trecho: str) -> int:
        return self.painel.texto().index(trecho)

    # -- conferências

    def assertTelaIgualAoDocumento(self) -> None:
        """O widget sem o desenho (miniatura e a quebra embaixo dela) é o documento, letra a letra."""
        tela = qt_texto._texto_da_tela(self.editor.document()).replace(OBJETO + "\n", "")
        self.assertEqual(tela, self.painel.texto())

    def assertMapaFecha(self) -> None:
        """Toda letra do documento está, pelo mapa, na mesma letra do widget."""
        tela = qt_texto._texto_da_tela(self.editor.document())
        for deslocamento, letra in enumerate(self.painel.texto()):
            posicao = self.painel._mapa.posicao(deslocamento)
            self.assertEqual(tela[posicao], letra, f"o mapa escorregou no deslocamento {deslocamento}")


class DigitarEntraNoDocumentoTests(_Folha):
    """A tecla de verdade chega a `self.documento` -- e a tudo o que lê dele."""

    def test_o_digitado_entra_no_documento_sem_redesenhar_a_folha(self) -> None:
        """**Sem redesenho por tecla**: refazer o `QTextDocument` inteiro, com as miniaturas, é o
        que o portão de bloqueio da thread da janela reprovaria a cada letra."""
        self.cursor_em(self.onde("c4.") + 2)
        with mock.patch.object(self.painel, "_desenhar", wraps=self.painel._desenhar) as desenho:
            self.digitar(" e Nf3")
        self.assertIn("vai para c4 e Nf3.", self.painel.texto())
        desenho.assert_not_called()
        self.assertTelaIgualAoDocumento()
        self.assertMapaFecha()

    def test_o_digitado_sobrevive_ao_negrito_noutra_palavra(self) -> None:
        """**O defeito, como a pessoa o via**: digitar, negritar outra palavra, e a palavra
        digitada sumir no redesenho do negrito."""
        self.cursor_em(self.onde("c4.") + 2)
        self.digitar(" e Nf3")
        self.selecionar(self.onde("bispo"), self.onde("bispo") + len("bispo"))
        self.painel.negrito()
        self.assertIn("vai para c4 e Nf3.", self.painel.texto())
        self.assertTelaIgualAoDocumento()
        negritos = [c.texto for c in self.painel.documento.corridas if c.atributos.negrito]
        self.assertEqual(negritos, ["bispo"])
        digitada = next(c for c in self.painel.documento.corridas if "Nf3" in c.texto)
        self.assertFalse(digitada.atributos.negrito, "o negrito caiu no lugar errado: o mapa escorregou")

    def test_o_digitado_e_da_mao_e_do_paragrafo_em_que_caiu(self) -> None:
        """No começo do parágrafo que o glifo adivinhou: a palavra nova é daquele bloco -- é o que
        `correcao` compara com a leitura -- e **não** herda o vermelho de `revisar`."""
        self.cursor_em(self.onde("Depois"))
        self.digitar("Logo ")
        nova = next(c for c in self.painel.documento.corridas if c.texto == "Logo ")
        adivinhada = next(c for c in self.painel.documento.corridas if c.texto.startswith("Depois"))
        self.assertEqual(adivinhada.faixa, documento.REVISAR, "a folha de teste perdeu a faixa")
        self.assertEqual((nova.bloco, nova.procedencia), (adivinhada.bloco, "humano"))
        self.assertEqual(nova.faixa, documento.faixa_de_confianca(0.0, "humano"))

    def test_a_tela_pinta_o_digitado_como_o_documento_o_guarda(self) -> None:
        """O Qt escreve com o formato da vizinha **da tela**; o documento escolheu outro. Sem a
        repintura, a tela mostraria o vermelho e o arquivo gravaria o tranquilo."""
        self.cursor_em(self.onde("Depois"))
        self.digitar("Logo")
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(self.painel._mapa.posicao(self.onde("Logo")) + 1)
        nova = next(c for c in self.painel.documento.corridas if c.texto == "Logo")
        esperado = qt_texto.formato_de(nova, base=self.painel._base).foreground().color().name()
        self.assertEqual(cursor.charFormat().foreground().color().name(), esperado)

    def test_escrever_por_cima_do_negrito_devolve_negrito(self) -> None:
        self.selecionar(self.onde("bispo"), self.onde("bispo") + 5)
        self.painel.negrito()
        self.selecionar(self.onde("bispo"), self.onde("bispo") + 5)
        self.digitar("cavalo")
        nova = next(c for c in self.painel.documento.corridas if c.texto == "cavalo")
        self.assertTrue(nova.atributos.negrito)
        self.assertEqual(self.editor.textCursor().charFormat().fontWeight(), QFont.Weight.Bold)

    def test_enter_backspace_e_colar_tambem_sao_digitacao(self) -> None:
        from PyQt6.QtWidgets import QApplication

        self.cursor_em(self.onde("c4.") + 3)
        self.tecla(Qt.Key.Key_Return)
        self.digitar("Nova linha")
        self.tecla(Qt.Key.Key_Backspace)
        clip = QApplication.clipboard()
        self.assertIsNotNone(clip)
        clip.setText("colado\ncom quebra")  # type: ignore[union-attr]
        self.painel.colar()
        self.assertIn("c4.\nNova linhcolado\ncom quebra", self.painel.texto())
        self.assertTelaIgualAoDocumento()
        self.assertMapaFecha()

    def test_a_busca_acha_o_que_foi_digitado(self) -> None:
        """A janela de busca lê `self.documento`: antes, a palavra digitada não existia para ela."""
        self.cursor_em(self.onde("c4.") + 2)
        self.digitar(" xadrez")
        janela = self.painel.achar()
        self.addCleanup(descartar, janela)
        janela.campo_agulha.setText("xadrez")
        self.assertEqual(len(janela.procurar()), 1)
        janela.lista.setCurrentRow(0)
        self.assertEqual(self.editor.textCursor().selectedText(), "xadrez")

    def test_o_zoom_nao_apaga_o_digitado_nem_move_o_cursor(self) -> None:
        self.cursor_em(self.onde("c4.") + 2)
        self.digitar(" xadrez")
        onde = self.editor.textCursor().position()
        self.painel.aproximar_texto()
        self.assertIn("c4 xadrez.", self.painel.texto())
        self.assertEqual(self.editor.textCursor().position(), onde)
        self.assertTelaIgualAoDocumento()

    def test_o_mapa_acompanha_depois_do_diagrama(self) -> None:
        """Digitar **antes** do diagrama empurra tudo o que vem depois dele nas duas coordenadas."""
        self.cursor_em(0)
        self.digitar("Nota: ")
        inicio = self.onde("Depois")
        self.selecionar(inicio, inicio + len("Depois"))
        self.assertEqual(self.editor.textCursor().selectedText(), "Depois")
        self.assertMapaFecha()


class GravarEExportarTests(_Folha):
    """O que se digitou vai para o `.cvtxt` e para a exportação."""

    def test_gravar_e_reabrir_traz_o_digitado(self) -> None:
        self.cursor_em(self.onde("c4.") + 2)
        self.digitar(" e Nf3")
        destino = self.pasta / "folha.cvtxt"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            self.painel.salvar_documento_como()
        self.assertIn("c4 e Nf3.", arquivo.carregar(destino).para_texto())

        outro = PainelDeTexto(dpi=72)
        self.addCleanup(descartar, outro)
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(destino), "")):
            outro.abrir_documento()
        self.assertIn("c4 e Nf3.", outro.texto())
        self.assertIn("c4 e Nf3.", outro.editor.toPlainText())
        self.assertFalse(outro.tem_alteracoes, "o arquivo recém-aberto não tem nada por gravar")

    def test_exportar_txt_leva_o_digitado(self) -> None:
        self.cursor_em(self.onde("c4.") + 2)
        self.digitar(" e Nf3")
        destino = self.pasta / "folha.txt"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            self.painel.salvar()
        tarefa = self.painel._tarefa
        self.assertIsNotNone(tarefa, "a exportação não partiu")
        self.assertTrue(tarefa.wait(10_000))  # type: ignore[union-attr]
        self.app.processEvents()
        self.assertIn("c4 e Nf3.", Path(destino).read_text(encoding="utf-8"))


class DesfazerADigitacaoTests(_Folha):
    """`Ctrl+Z` desfaz a palavra digitada inteira -- e é a tecla de verdade, dentro da folha."""

    def test_ctrl_z_tira_a_palavra_digitada_num_passo_so(self) -> None:
        """A guarda de atalhos cede `Ctrl+Z` ao campo de texto, e o desfazer do `QTextEdit` está
        desligado: a tecla precisa chegar à pilha de documentos pelo próprio editor."""
        antes = self.painel.texto()
        self.cursor_em(self.onde("c4.") + 2)
        self.digitar(" cavalo")
        self.assertEqual(len(self.painel._historico), 1, "cada letra virou um passo")
        self.tecla(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.painel.texto(), antes)
        self.assertTelaIgualAoDocumento()
        self.assertFalse(self.painel.pode_desfazer)
        self.tecla(Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertIn("c4 cavalo.", self.painel.texto())

    def test_desfazer_deixa_o_cursor_onde_a_palavra_estava(self) -> None:
        """Com o cursor no começo da folha, a tecla seguinte ao `Ctrl+Z` iria parar no título."""
        self.cursor_em(self.onde("c4.") + 2)
        self.digitar(" cavalo")
        self.painel.desfazer()
        self.digitar("!")
        self.assertIn("c4!.", self.painel.texto())

    def test_a_pausa_o_cursor_que_pula_e_o_negrito_fecham_o_passo(self) -> None:
        self.cursor_em(self.onde("c4.") + 2)
        self.digitar(" um")
        self.agora += 5.0  # a pausa
        self.digitar(" dois")
        self.cursor_em(0)  # o cursor que pula
        self.digitar("Tres ")
        self.selecionar(self.onde("bispo"), self.onde("bispo") + 5)
        self.painel.negrito()
        self.cursor_em(self.onde("Tres ") + 5)
        self.digitar("quatro ")  # depois de uma ferramenta
        self.assertEqual(len(self.painel._historico), 5)
        passos: list[tuple[str, bool]] = []
        while self.painel.pode_desfazer:
            self.painel.desfazer()
            negrito = any(c.atributos.negrito for c in self.painel.documento.corridas)
            passos.append((self.painel.texto(), negrito))
        original = rico.de_pagina(_pagina()).para_texto()
        esperados = [
            ("Tres O bispo vai para c4 um dois.", True),  # saiu "quatro ", o que veio depois do negrito
            ("Tres O bispo vai para c4 um dois.", False),  # saiu o negrito
            ("O bispo vai para c4 um dois.", False),  # saiu o que veio depois do cursor pular
            ("O bispo vai para c4 um.", False),  # saiu o que veio depois da pausa
            ("O bispo vai para c4.", False),
        ]
        self.assertEqual([(texto.split("\n")[0], negrito) for texto, negrito in passos], esperados)
        self.assertEqual(passos[-1][0], original)


class MarcaDoDiagramaTests(_Folha):
    """A marca é do documento, a miniatura é do desenho -- e o documento é quem manda."""

    def test_escrever_dentro_da_marca_e_recusado(self) -> None:
        antes = self.painel.texto()
        self.cursor_em(self.onde("[Diagrama 1]") + 3)
        self.digitar("z")
        self.assertEqual(self.painel.texto(), antes)
        self.assertTelaIgualAoDocumento()
        self.assertIn("não se edita por dentro", self.recados[-1])

    def test_o_backspace_na_marca_tira_o_diagrama_inteiro_e_desfazer_o_devolve(self) -> None:
        fim = self.onde("[Diagrama 1]") + len("[Diagrama 1]")
        self.cursor_em(fim)
        self.tecla(Qt.Key.Key_Backspace)
        self.assertEqual(self.painel.documento.diagramas, ())
        self.assertNotIn("Diagrama", self.painel.texto())
        self.assertNotIn(OBJETO, qt_texto._texto_da_tela(self.editor.document()), "a miniatura ficou órfã")
        self.painel.desfazer()
        self.assertEqual(len(self.painel.documento.diagramas), 1)
        self.assertTelaIgualAoDocumento()

    def test_apagar_so_a_miniatura_nao_apaga_o_diagrama(self) -> None:
        """A miniatura é desenho: o `Backspace` que a alcança sozinha não muda o documento, e ela volta."""
        antes = self.painel.texto()
        self.cursor_em(self.onde("[Diagrama 1]"))
        self.tecla(Qt.Key.Key_Backspace)  # a quebra do desenho
        self.tecla(Qt.Key.Key_Backspace)  # a miniatura
        self.assertEqual(self.painel.texto(), antes)
        self.assertEqual(qt_texto._texto_da_tela(self.editor.document()).count(OBJETO), 1)
        self.assertFalse(self.painel.tem_alteracoes)

    def test_selecionar_tudo_e_escrever_troca_a_folha_inteira_num_passo(self) -> None:
        """A marca coberta inteira pela seleção sai de propósito -- e sem o recado da miniatura,
        que é sobre apagar **só** o desenho."""
        self.painel.selecionar_tudo()
        self.digitar("Nova")
        self.assertEqual(self.painel.texto(), "Nova")
        self.assertEqual(self.painel.documento.diagramas, ())
        self.assertTelaIgualAoDocumento()
        self.assertFalse(any("miniatura" in recado for recado in self.recados), self.recados)
        self.painel.desfazer()
        self.assertEqual(self.painel.texto(), rico.de_pagina(_pagina()).para_texto())

    def test_arrastar_por_cima_do_diagrama_nao_o_perde(self) -> None:
        """O arrasto chega como **uma** janela que cobre origem e destino, com o diagrama no meio.
        Lida como apagar e escrever, a marca voltaria como texto comum e o diagrama sumiria."""
        origem = self.onde("bispo")
        destino = self.onde("Depois")
        de, ate = self.painel._mapa.posicao(origem), self.painel._mapa.posicao(origem + 6)
        para = self.painel._mapa.posicao(destino)
        # O que o `QTextEdit` faz ao soltar: um bloco de edição que tira a seleção e insere texto puro.
        cursor = QTextCursor(self.editor.document())
        cursor.beginEditBlock()
        cursor.setPosition(de)
        cursor.setPosition(ate, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.setPosition(para - (ate - de))
        cursor.insertText("bispo ")
        cursor.endEditBlock()
        self.assertIn("\n\nbispo Depois", self.painel.texto())
        self.assertEqual(len(self.painel.documento.diagramas), 1)
        self.assertTelaIgualAoDocumento()
        self.painel.desfazer()
        self.assertEqual(self.painel.texto(), rico.de_pagina(_pagina()).para_texto())


class AlteracoesPorGravarTests(_Folha):
    """O que ainda não está no disco: a releitura e o fechamento perguntam antes de perder."""

    def test_a_folha_lida_nao_tem_nada_por_gravar_e_a_digitada_tem(self) -> None:
        self.assertFalse(self.painel.tem_alteracoes)
        self.cursor_em(0)
        self.digitar("x")
        self.assertTrue(self.painel.tem_alteracoes)
        self.tecla(Qt.Key.Key_Backspace)
        self.assertFalse(self.painel.tem_alteracoes, "escrever e apagar a mesma letra não deixa nada a perder")

    def test_gravar_zera_e_editar_de_novo_volta_a_contar(self) -> None:
        self.cursor_em(0)
        self.digitar("x")
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.pasta / "f.cvtxt"), "")):
            self.painel.salvar_documento_como()
        self.assertFalse(self.painel.tem_alteracoes)
        self.assertTrue(self.painel.pode_desfazer, "gravar não esvazia a pilha")
        self.digitar("y")
        self.assertTrue(self.painel.tem_alteracoes)

    def test_ler_de_novo_pergunta_e_nao_descarta_quando_a_resposta_e_nao(self) -> None:
        self.painel.definir_livro(self.pasta / "livro.pdf", pagina=0)
        self.cursor_em(0)
        self.digitar("x")
        with mock.patch.object(dialogos, "ha_quem_responda", return_value=True), mock.patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ) as pergunta:
            self.painel.ler()
        pergunta.assert_called_once()
        self.assertIn("foi editado e não foi gravado", pergunta.call_args.args[2])
        self.assertIsNone(self.painel._tarefa, "a leitura partiu mesmo com a resposta Não")
        self.assertTrue(self.painel.texto().startswith("x"))

    def test_sem_tela_ler_de_novo_nao_descarta(self) -> None:
        """Sob `offscreen` não há quem responda: ler de novo **guarda** o texto, e fica no log."""
        self.painel.definir_livro(self.pasta / "livro.pdf", pagina=0)
        self.cursor_em(0)
        self.digitar("x")
        with self.assertLogs("chess_diagram_ocr.qt.painel_de_texto", level="WARNING"):
            self.painel.ler()
        self.assertIsNone(self.painel._tarefa)

    def test_o_digitado_durante_a_leitura_nao_some_quando_ela_chega(self) -> None:
        """A pergunta de `ler` foi sobre o texto de antes; o que se escreveu esperando a folha
        não foi confirmado por ninguém."""
        self.painel._documento_ao_ler = self.painel.documento  # a leitura partiu
        self.cursor_em(0)
        self.digitar("Esperando ")
        with mock.patch.object(dialogos, "ha_quem_responda", return_value=True), mock.patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ):
            self.painel._leitura_terminou(_pagina())
        self.assertTrue(self.painel.texto().startswith("Esperando "))
        self.assertIn("ficou de lado", self.recados[-1])

    def test_sem_edicao_durante_a_leitura_a_folha_chega_sem_segunda_pergunta(self) -> None:
        """A pergunta de `ler` já foi respondida: sem tecla no meio, a folha lida só chega."""
        self.cursor_em(0)
        self.digitar("x")  # editado antes; `ler` perguntou e a pessoa mandou descartar
        self.painel._documento_ao_ler = self.painel.documento  # a leitura partiu
        with mock.patch.object(dialogos, "ha_quem_responda", return_value=True), mock.patch.object(
            QMessageBox, "question"
        ) as pergunta:
            self.painel._leitura_terminou(_pagina())
        pergunta.assert_not_called()
        self.assertEqual(self.painel.texto(), rico.de_pagina(_pagina()).para_texto())
        self.assertFalse(self.painel.tem_alteracoes)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FecharAJanelaComTextoTests(_JanelaComLivro):
    """Fechar a janela com texto digitado e não gravado pergunta -- como as correções do tabuleiro (A7)."""

    def setUp(self) -> None:
        super().setUp()
        self.montada = self.janela(com_livro=False)

    def fechar(self) -> bool:
        from PyQt6.QtGui import QCloseEvent

        evento = QCloseEvent()
        evento.ignore()
        self.montada.closeEvent(evento)
        return evento.isAccepted()

    def digitar(self, texto: str) -> None:
        QTest.keyClicks(self.montada.texto.editor, texto)

    def test_fechar_com_texto_nao_gravado_pergunta(self) -> None:
        self.digitar("Notas da folha")
        with mock.patch.object(dialogos, "ha_quem_responda", return_value=True), mock.patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ) as pergunta:
            self.assertFalse(self.fechar(), "respondeu Não e a janela fechou")
        pergunta.assert_called_once()
        self.assertIn("aba Texto", pergunta.call_args.args[2])
        with mock.patch.object(dialogos, "ha_quem_responda", return_value=True), mock.patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            self.assertTrue(self.fechar())

    def test_gravado_fecha_sem_perguntar(self) -> None:
        self.digitar("Notas da folha")
        destino = self.pasta / "notas.cvtxt"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            self.montada.texto.salvar_documento_como()
        with mock.patch.object(dialogos, "ha_quem_responda", return_value=True), mock.patch.object(
            QMessageBox, "question"
        ) as pergunta:
            self.assertTrue(self.fechar())
        pergunta.assert_not_called()

    def test_sem_tela_o_fechamento_segue_e_fica_no_log(self) -> None:
        """Os arneses de `caissa.ui.audit.*` fecham a janela sob `offscreen`: pergunta ali trava."""
        self.digitar("Notas da folha")
        with self.assertLogs("chess_diagram_ocr.qt.painel_de_texto", level="WARNING"):
            self.assertTrue(self.fechar())


class EditorNaoAcumulaDocumentosTests(_Folha):
    def test_o_redesenho_solta_o_documento_anterior(self) -> None:
        """O `setDocument` do Qt só apaga o documento filho do controle interno; os do painel são
        filhos do editor, e ficavam todos -- uma folha inteira, com miniaturas, por redesenho."""
        for _ in range(5):
            self.painel.aproximar_texto()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        self.assertEqual(len(self.editor.findChildren(QTextDocument)), 1)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MapaTrocarTests(unittest.TestCase):
    """`_Mapa.trocar`, a conta sem widget: o que muda depois da troca anda igual nas duas coordenadas."""

    def mapa(self) -> qt_texto._Mapa:
        # Documento "abcdefgh", com dois caracteres de desenho (uma miniatura) entre "d" e "e".
        mapa = qt_texto._Mapa()
        mapa.registrar(0, 0, 4)
        mapa.registrar(4, 6, 4)
        return mapa

    def test_inserir_no_meio_de_um_trecho_empurra_os_seguintes(self) -> None:
        mapa = self.mapa()
        mapa.trocar(2, 0, 2, 3)
        self.assertEqual([mapa.posicao(d) for d in range(11)], [0, 1, 2, 3, 4, 5, 6, 9, 10, 11, 12])

    def test_apagar_puxa_os_seguintes(self) -> None:
        mapa = self.mapa()
        mapa.trocar(1, 2, 1, 0)
        self.assertEqual([mapa.posicao(d) for d in range(6)], [0, 1, 4, 5, 6, 7])

    def test_os_trechos_colados_se_fundem(self) -> None:
        """Sem a fusão cada tecla deixaria um trecho de uma letra."""
        mapa = self.mapa()
        for i in range(10):
            mapa.trocar(4 + i, 0, 4 + i, 1)
        self.assertEqual(len(mapa._trechos), 2)
        self.assertEqual(mapa.deslocamento(mapa.posicao(13)), 13)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class JanelaDaTrocaTests(unittest.TestCase):
    def test_a_menor_janela_que_leva_um_texto_ao_outro(self) -> None:
        self.assertIsNone(qt_texto._janela_da_troca("igual", "igual"))
        self.assertEqual(qt_texto._janela_da_troca("abcdef", "abXdef"), (2, 1, 1))
        self.assertEqual(qt_texto._janela_da_troca("abc", "abcd"), (3, 0, 1))
        self.assertEqual(qt_texto._janela_da_troca("aaaa", "aaa"), (3, 1, 0))

    def test_a_janela_do_qt_que_nao_bate_e_refeita(self) -> None:
        """A versão do Qt que anunciar o documento inteiro não pode virar troca do documento inteiro."""
        self.assertEqual(qt_texto._janela_informada("abcdef", "abXcdef", 0, 6, 7), (0, 6, 7))
        self.assertEqual(qt_texto._janela_informada("abcdef", "abXcdef", 1, 0, 1), (2, 0, 1))
        self.assertIsNone(qt_texto._janela_informada("formato", "formato", 0, 7, 7))

    def test_o_giro_e_o_arrasto(self) -> None:
        self.assertEqual(qt_texto._giro("bispo vai", "vaibispo "), 6)
        self.assertEqual(qt_texto._giro("abc", "abd"), 0)
        self.assertEqual(qt_texto._giro("a\xa0b c", "b ca "), 2, "o espaço inseparável arrastado vira espaço")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
