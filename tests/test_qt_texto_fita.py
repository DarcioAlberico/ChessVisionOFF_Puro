"""A fita e os painéis da aba Texto (Fase 95, S-631 e S-650 a S-659), um teste por critério de aceite.

Os critérios estão em `docs/ROADMAP_MESA_DE_TEXTO.md`. Os puros (curinga, sugestões, contar palavras,
`Alt+X`, mover parágrafo) também têm teste aqui, junto da fiação que os usa.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import busca, rico, sugestao
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.ui import fita_do_texto, texto_declarado

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor, QTextOption
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
    from chess_diagram_ocr.qt.texto_formato import formato_de


def _pagina(*textos: str, livro: str = "livro.pdf", folha: int = 0) -> PaginaLida:
    blocos = tuple(BlocoDeTexto.de_linhas([LinhaLida(t, (0.0, 0.0, 9.0, 9.0), 0.9, "glifo")]) for t in textos)  # type: ignore[arg-type]
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=blocos),))


class DeclaracaoTests(unittest.TestCase):
    """S-650: a fita é dado, e o inventário a lê."""

    def test_todo_comando_da_aba_esta_na_fita(self) -> None:
        fora = [acao for acao in texto_declarado.COMANDOS_DA_ABA if not fita_do_texto.na_fita(acao)]
        self.assertEqual(fora, [], "comando da aba fora da fita e da aba Arquivo")

    def test_todo_item_da_fita_e_do_catalogo_ou_um_controle(self) -> None:
        from chess_diagram_ocr.ui import comandos

        for acao in fita_do_texto.acoes():
            with self.subTest(acao=acao):
                comandos.comando(acao)  # levanta se não for do catálogo


class PurosTests(unittest.TestCase):
    def test_curinga_troca_o_grupo_e_nao_toca_ll(self) -> None:
        """S-659: `([0-9])l` por `\\11` transforma `e4l` em `e41` e não toca `ll`."""
        doc = rico.de_texto("e4l ll c5l")
        achados = busca.achar(doc, "([0-9])l", curinga=True)
        self.assertEqual(busca.substituir(doc, achados, "\\11", curinga=True).para_texto(), "e41 ll c51")

    def test_curinga_que_travaria_a_busca_e_recusado(self) -> None:
        with self.assertRaises(ValueError):
            busca.curinga_para_regex("(a*)@")

    def test_palavra_inteira(self) -> None:
        doc = rico.de_texto("bispo bispos o bispo")
        self.assertEqual(len(busca.achar(doc, "bispo", palavra_inteira=True)), 2)

    def test_a_sugestao_de_ocr_vem_primeiro(self) -> None:
        self.assertEqual(sugestao.sugestoes("p/ayer", {"player", "payer", "prayer"})[0], "player")
        self.assertEqual(sugestao.sugestoes("smdy", {"study", "sandy"})[0], "study")

    def test_contar_palavras(self) -> None:
        self.assertEqual(texto_declarado.contar_palavras("1.e4 e5 2.Nf3 o bispo's"), 7)  # o número do lance conta
        self.assertEqual(texto_declarado.frase_das_palavras(357, 12), "12 de 357 palavras")

    def test_alt_x_vai_e_volta(self) -> None:
        self.assertEqual(texto_declarado.codigo_unicode("Proke0161"), (4, "š"))
        self.assertEqual(texto_declarado.codigo_unicode("Prokeš"), (1, "0161"))

    def test_mover_paragrafo_e_os_titulos(self) -> None:
        doc = rico.de_texto("um\n\ndois")
        novo, onde = rico.mover_paragrafo(doc, len("um\n\nd"), -1)
        self.assertEqual((novo.para_texto(), onde), ("dois\n\num", 0))
        doc = rico.aplicar_estilo(rico.de_pagina(_pagina("Abertura", "prosa", "Final")), 0, 1, "titulo")
        doc = rico.aplicar_estilo(doc, len(doc.para_texto()) - 1, len(doc.para_texto()), "titulo")
        self.assertEqual([t for _o, t in rico.titulos(doc)], ["Abertura", "Final"])

    def test_pincel_puro_nao_leva_a_faixa(self) -> None:
        doc = rico.aplicar(rico.de_texto("forte fraco"), 0, 5, negrito=True, cor="nota")
        atributos = rico.atributos_em(doc, 1)
        assert atributos is not None
        pintado = rico.pintar(doc, 7, 7, atributos, paragrafo=False)
        fraca = next(c for c in pintado.corridas if c.texto == "fraco")
        self.assertTrue(fraca.atributos.negrito)
        self.assertEqual(fraca.atributos.cor, "nota")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Aba(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.pasta = pasta_temporaria(self)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=self.pasta / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(1100, 700)
        self.painel.show()
        self.painel.activateWindow()
        self.app.processEvents()

    def selecionar(self, inicio: int, fim: int) -> None:
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(inicio))
        cursor.setPosition(self.painel._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.painel.editor.setTextCursor(cursor)
        self.app.processEvents()


class FitaTests(_Aba):
    def test_todo_botao_tem_nome_por_extenso_e_dica_com_a_tecla(self) -> None:
        from chess_diagram_ocr.qt.fita_do_texto import tecla_de
        from chess_diagram_ocr.ui import comandos

        for acao, botao in self.painel.fita.botoes.items():
            with self.subTest(acao=acao):
                self.assertEqual(botao.accessibleName(), comandos.nome_acessivel(acao))
                tecla = tecla_de(acao)
                if tecla:
                    self.assertIn(tecla, botao.toolTip())

    def test_negrito_centralizado_marca_negrito_e_centro(self) -> None:
        doc = rico.aplicar(rico.de_texto("um lance forte"), 0, 14, negrito=True)
        doc = rico.aplicar_alinhamento(doc, 0, 14, "centro")
        self.painel.desenhar_documento(doc)
        self.selecionar(3, 6)
        botoes = self.painel.fita.botoes
        self.assertTrue(botoes["negrito"].isChecked())
        self.assertTrue(botoes["alinhar_centro"].isChecked())
        self.assertFalse(botoes["italico"].isChecked())
        self.assertFalse(botoes["alinhar_esquerda"].isChecked())

    def test_ctrl_b_na_folha_negrita(self) -> None:
        """A tecla própria do editor estava declarada e não ligada no porte para o Qt."""
        self.painel.desenhar_documento(rico.de_texto("um bispo forte"))
        self.painel.editor.setFocus()
        self.selecionar(3, 8)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(any(c.atributos.negrito and "bispo" in c.texto for c in self.painel.documento.corridas))

    def test_recolher_e_voltar_pelo_estado(self) -> None:
        from chess_diagram_ocr.ui.state import AppState

        self.painel.alternar_fita()
        self.assertTrue(self.painel.fita.recolhida)
        self.assertFalse(self.painel.fita.currentWidget().isVisible())
        estado = AppState()
        self.painel.anotar_estado(estado)
        self.assertTrue(estado.texto_fita_recolhida)
        self.painel.alternar_fita()
        self.painel.aplicar_estado(estado)
        self.assertTrue(self.painel.fita.recolhida)


class CorpoEmPontosTests(_Aba):
    """S-631."""

    def test_o_corpo_do_paragrafo_em_pontos_e_o_misto_vazio(self) -> None:
        doc = rico.aplicar_no_paragrafo(rico.de_pagina(_pagina("grande", "pequeno")), 0, 1, corpo=2)
        self.painel.desenhar_documento(doc)
        self.selecionar(1, 1)
        base = self.painel._base[0]  # type: ignore[index]
        from chess_diagram_ocr.ui import tipografia

        esperado = tipografia.corpo(2, base=base)
        self.assertEqual(self.painel.caixa_de_corpo.value(), esperado)
        self.selecionar(0, len(doc.para_texto()))
        self.assertEqual(self.painel.caixa_de_corpo.value(), self.painel.caixa_de_corpo.minimum(), "o misto não ficou vazio")

    def test_digitar_o_corpo_muda_o_documento_num_passo(self) -> None:
        from paridade_do_texto import divergencias

        self.painel.desenhar_documento(rico.de_texto("um parágrafo"))
        self.selecionar(2, 2)
        passos = len(self.painel._historico)
        self.painel.caixa_de_corpo.setValue(self.painel.caixa_de_corpo.value() + 3)
        self.painel._corpo_digitado()
        self.assertEqual({c.atributos.corpo for c in self.painel.documento.corridas if c.texto.strip()}, {3})
        self.assertEqual(len(self.painel._historico), passos + 1)
        self.assertEqual(divergencias(self.painel), [])


class GaleriaTests(_Aba):
    """S-651."""

    def test_cada_amostra_no_proprio_estilo_e_a_do_cursor_marcada(self) -> None:
        for estilo, amostra in self.painel.amostras.items():
            with self.subTest(estilo=estilo or "normal"):
                esperada = formato_de(rico.Corrida(estilo or "Normal", rico.Atributos(estilo=estilo))).font()
                self.assertEqual((amostra.font().family(), amostra.font().pointSize(), amostra.font().bold()),
                                 (esperada.family(), esperada.pointSize(), esperada.bold()))
        doc = rico.aplicar_estilo(rico.de_pagina(_pagina("Abertura", "prosa")), 0, 1, "titulo")
        self.painel.desenhar_documento(doc)
        self.selecionar(2, 2)
        self.assertTrue(self.painel.amostras["titulo"].isChecked())


class PincelTests(_Aba):
    """S-653."""

    def test_pincelar_negrito_vermelho_numa_palavra_comum(self) -> None:
        from paridade_do_texto import divergencias

        doc = rico.aplicar(rico.de_pagina(_pagina("forte fraco")), 0, 5, negrito=True, cor="nota")
        self.painel.mostrar_pagina(doc.origem)  # type: ignore[arg-type]
        self.painel.desenhar_documento(doc)
        faixas_antes = {c.texto: c.faixa for c in self.painel.documento.corridas}
        self.selecionar(1, 1)
        self.painel.copiar_formato()
        self.selecionar(7, 7)
        passos = len(self.painel._historico)
        self.painel.colar_formato()
        fraca = next(c for c in self.painel.documento.corridas if "fraco" in c.texto)
        self.assertTrue(fraca.atributos.negrito)
        self.assertEqual(fraca.atributos.cor, "nota")
        self.assertEqual(fraca.faixa, faixas_antes.get("fraco", fraca.faixa), "o pincel levou a faixa do motor")
        self.assertEqual(len(self.painel._historico), passos + 1)
        self.assertEqual(divergencias(self.painel), [])
        self.selecionar(8, 8)
        self.assertTrue(self.painel.fita.botoes["negrito"].isChecked())
        self.assertIsNone(self.painel._pincel, "o pincel de um uso continuou armado")

    def test_esc_desarma(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("um bispo"))
        self.selecionar(1, 1)
        self.painel.copiar_formato()
        self.painel.editor.setFocus()
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Escape)
        self.assertIsNone(self.painel._pincel)


class NavegacaoTests(_Aba):
    """S-654."""

    def test_dois_titulos_e_o_clique_no_segundo(self) -> None:
        doc = rico.de_pagina(_pagina("Abertura", "prosa", "Final"))
        texto = doc.para_texto()
        doc = rico.aplicar_estilo(doc, 0, 1, "titulo")
        doc = rico.aplicar_estilo(doc, len(texto) - 1, len(texto), "titulo")
        self.painel.desenhar_documento(doc)
        self.painel.alternar_navegacao()
        lista = self.painel.navegacao.titulos
        self.assertEqual([lista.item(i).text() for i in range(lista.count())], ["Abertura", "Final"])
        lista.itemClicked.emit(lista.item(1))
        self.assertEqual(self.painel._mapa.deslocamento(self.painel.editor.textCursor().position()), texto.index("Final"))

    def test_tres_achados_e_o_clique_no_terceiro_seleciona(self) -> None:
        from chess_diagram_ocr.qt.painel_de_navegacao import RESULTADOS

        texto = "Nf3 e depois Nf3 e outra vez Nf3."
        self.painel.desenhar_documento(rico.de_texto(texto))
        self.painel.alternar_navegacao()
        self.painel.navegacao.setCurrentIndex(RESULTADOS)
        self.painel.navegacao.campo_de_busca.setText("Nf3")
        lista = self.painel.navegacao.resultados
        self.assertEqual(lista.count(), 3)
        lista.itemClicked.emit(lista.item(2))
        self.assertEqual(self.painel.editor.textCursor().selectedText(), "Nf3")
        self.assertEqual(self.painel._intervalo()[0], texto.rindex("Nf3"))


class BarraDeEstadoTests(_Aba):
    """S-655."""

    def test_palavras_com_selecao_e_o_recado_que_some(self) -> None:
        texto = " ".join(f"p{i}" for i in range(357))
        self.painel.desenhar_documento(rico.de_texto(texto))
        fim = len(" ".join(f"p{i}" for i in range(12)))
        self.selecionar(0, fim)
        self.assertEqual(self.painel.caixa_de_palavras.text(), "12 de 357 palavras")
        self.painel.estado.emit("um recado qualquer")
        self.assertFalse(self.painel.recado.isHidden())
        self.assertTrue(self.painel.caixa_de_palavras.isHidden())
        self.assertEqual(self.painel._relogio_do_recado.interval(), 6000)
        self.painel._relogio_do_recado.timeout.emit()
        self.assertTrue(self.painel.recado.isHidden())
        self.assertFalse(self.painel.caixa_de_palavras.isHidden())


class DesfazerComRotuloTests(_Aba):
    """S-656."""

    def test_escolher_o_quinto_desfaz_cinco(self) -> None:
        from paridade_do_texto import divergencias

        self.painel.desenhar_documento(rico.de_texto("um dois tres quatro cinco seis"))
        documentos = [self.painel.documento]
        for acao, (inicio, fim) in zip(
            ("negrito", "italico", "sublinhado", "tachado", "maiusculas", "negrito"),
            ((0, 2), (3, 7), (8, 12), (13, 19), (20, 25), (26, 30)),
            strict=True,
        ):
            self.selecionar(inicio, fim)
            self.painel.executar(acao)
            documentos.append(self.painel.documento)
        rotulos = list(reversed(self.painel._rotulos_do_historico))
        from chess_diagram_ocr.ui import comandos

        self.assertEqual(rotulos[0], comandos.rotulo_de_botao("negrito"))
        self.assertEqual(rotulos[1], comandos.rotulo_de_botao("maiusculas"))
        self.painel.desfazer_ate(5)
        self.assertEqual(self.painel.documento, documentos[1])
        self.assertEqual(divergencias(self.painel), [])


class LexicoTests(_Aba):
    """S-657."""

    def test_a_sugestao_do_menu_e_o_aceite_num_passo(self) -> None:
        self.painel.mostrar_pagina(_pagina("o p/ayer joga"))
        with mock.patch("chess_diagram_ocr.text.dicionario.carregar", return_value=frozenset({"o", "player", "payer", "joga"})):
            self.painel.marcar_fora_do_lexico()
            self.assertEqual(self.painel._fora_do_lexico, [(2, 8)])
            from PyQt6.QtWidgets import QMenu

            menu = QMenu()
            self.addCleanup(menu.deleteLater)
            sobre = QTextCursor(self.painel.editor.document())
            sobre.setPosition(self.painel._mapa.posicao(4))
            ponto = self.painel.editor.cursorRect(sobre).center()
            self.painel._sugestoes_no_menu(menu, ponto)
            self.assertEqual(menu.actions()[0].text(), "player")
            passos = len(self.painel._historico)
            menu.actions()[0].trigger()
        self.assertIn("o player joga", self.painel.documento.para_texto())
        self.assertEqual(len(self.painel._historico), passos + 1)
        self.assertEqual(self.painel._correcoes, 1)

    def test_f7_vai_a_proxima_marcada(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("bem qzxvk bem wvkqz bem"))
        with mock.patch("chess_diagram_ocr.text.dicionario.carregar", return_value=frozenset({"bem"})):
            self.selecionar(0, 0)
            self.painel.proxima_fora_do_lexico()
            self.assertEqual(self.painel.editor.textCursor().selectedText(), "qzxvk")
            self.painel.proxima_fora_do_lexico()
            self.assertEqual(self.painel.editor.textCursor().selectedText(), "wvkqz")


class FocoEMarcasTests(_Aba):
    """S-658."""

    def test_o_modo_foco_esconde_e_o_esc_devolve(self) -> None:
        self.painel.alternar_navegacao()
        avisos: list[bool] = []
        self.painel.foco_mudou.connect(avisos.append)
        self.painel.alternar_modo_foco()
        self.assertTrue(self.painel.fita.isHidden())
        self.assertTrue(self.painel.navegacao.isHidden())
        self.assertEqual(avisos, [True])
        self.painel.editor.setFocus()
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Escape)
        self.assertFalse(self.painel.fita.isHidden())
        self.assertFalse(self.painel.navegacao.isHidden())
        self.assertEqual(avisos, [True, False])

    def test_as_marcas_sobrevivem_ao_negrito_e_nao_vao_ao_texto(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("dois  espaços"))
        self.painel.alternar_marcas_de_formatacao()
        self.selecionar(0, 4)
        self.painel.negrito()  # redesenha com um QTextDocument novo
        opcoes = self.painel.editor.document().defaultTextOption().flags()
        self.assertTrue(opcoes & QTextOption.Flag.ShowTabsAndSpaces)
        self.assertEqual(self.painel.editor.toPlainText(), "dois  espaços")


class CorrecaoWordCraftTests(_Aba):
    """S-659, na tela."""

    def test_mover_o_segundo_paragrafo_para_cima_e_desfazer(self) -> None:
        from paridade_do_texto import divergencias

        self.painel.desenhar_documento(rico.de_texto("primeiro\n\nsegundo"))
        self.selecionar(len("primeiro\n\nse"), len("primeiro\n\nse"))
        self.painel.mover_paragrafo_acima()
        self.assertEqual(self.painel.documento.para_texto(), "segundo\n\nprimeiro")
        self.assertEqual(self.painel.editor.toPlainText(), "segundo\n\nprimeiro")
        self.assertEqual(divergencias(self.painel), [])
        self.painel.desfazer()
        self.assertEqual(self.painel.documento.para_texto(), "primeiro\n\nsegundo")

    def test_alt_x_na_folha(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("Proke0161"))
        self.painel.editor.setFocus()
        self.selecionar(9, 9)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_X, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.painel.documento.para_texto(), "Prokeš")
        QTest.keyClick(self.painel.editor, Qt.Key.Key_X, Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.painel.documento.para_texto(), "Proke0161")


class LexicoDoLivroTests(unittest.TestCase):
    """S-657: o léxico do livro mora no caderno, e não vaza para outro livro."""

    def test_acrescentar_vale_no_livro_e_nao_noutro(self) -> None:
        from chess_diagram_ocr.text import caderno

        raiz = pasta_temporaria(self)
        um, outro = raiz / "um.pdf", raiz / "outro.pdf"
        um.write_bytes(b"%PDF um livro")
        outro.write_bytes(b"%PDF outro livro")
        primeiro = caderno.abrir(um, pasta=raiz / "cadernos")
        assert primeiro is not None
        self.addCleanup(primeiro.fechar)
        self.assertTrue(primeiro.acrescentar_ao_lexico("Dvoretsky"))
        self.assertIn("dvoretsky", caderno.abrir(um, pasta=raiz / "cadernos", travar=False).lexico())  # type: ignore[union-attr]
        self.assertNotIn("dvoretsky", caderno.abrir(outro, pasta=raiz / "cadernos", travar=False).lexico())  # type: ignore[union-attr]
        self.assertEqual((primeiro.pasta / "lexico.txt").read_text(encoding="utf-8"), "dvoretsky\n")


if __name__ == "__main__":
    unittest.main()
