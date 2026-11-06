"""Corrigir uma vez, corrigir no livro inteiro (S-766): as palavras do livro nos árbitros, e a troca em massa com prévia obrigatória.

**Os testes de janela afirmam efeito no disco e na tela**, com o caderno de verdade, e não uma chamada (`patch-nao-intercepta-slot-ligado`). Nenhuma folha de livro aqui: o documento é sintético.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import caderno, correcao_no_livro, fusao, leitor, rico
from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest
    from test_qt_janela import _JanelaComLivro

    from chess_diagram_ocr.qt.correcao_no_livro import JanelaDeCorrecaoNoLivro
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
else:  # pragma: no cover - sem o PyQt6 as classes pulam, mas precisam de uma base para existir
    _JanelaComLivro = unittest.TestCase


def folha(pagina: int, texto: str, *, documento: str = "livro.pdf") -> rico.DocumentoRico:
    linha = LinhaLida(texto, (0.0, 0.0, 300.0, 12.0), confianca=0.9, procedencia="tesseract")
    lida = PaginaLida(documento=documento, pagina=pagina, largura=400.0, altura=600.0, unidade="pt", colunas=(Coluna(indice=0, blocos=(BlocoDeTexto(linhas=(linha,), procedencia="tesseract"),)),))
    return rico.de_pagina(lida)


def corrigido(doc: rico.DocumentoRico, antes: str, depois: str) -> rico.DocumentoRico:
    inicio = doc.para_texto().index(antes)
    return rico.substituir_intervalo(doc, inicio, inicio + len(antes), depois)


class _ComCaderno(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.pdf = self.pasta / "livro.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 sintetico")
        self.cad = caderno.abrir(self.pdf, pasta=self.pasta / "cadernos")
        assert self.cad is not None
        self.addCleanup(self.cad.fechar)

    def guardar(self, pagina: int, texto: str) -> None:
        self.cad.guardar_leitura(folha(pagina, texto), motor="fusao")


class PalavrasDoLivroTests(_ComCaderno):
    def test_so_palavra_vai_ao_lexico(self) -> None:
        self.assertEqual(correcao_no_livro.palavra_do_livro("Gelfand,"), "Gelfand")
        for nao in ("Nf3", "12.", "e4", "!!", "1-0", ""):
            self.assertEqual(correcao_no_livro.palavra_do_livro(nao), "", nao)

    def test_o_que_a_mao_escreveu_e_o_lexico_nao_conhece_entra(self) -> None:
        doc = corrigido(folha(0, "the Gelfmnd line"), "Gelfmnd", "Gelfand")
        self.assertEqual(correcao_no_livro.ensinar(self.cad, doc, existe=lambda t: t == "the"), ("Gelfand",))
        self.assertIn("gelfand", self.cad.lexico())

    def test_o_que_o_lexico_ja_conhece_nao_entra(self) -> None:
        doc = corrigido(folha(0, "the wbite line"), "wbite", "white")
        self.assertEqual(correcao_no_livro.ensinar(self.cad, doc, existe=lambda _t: True), ())
        self.assertEqual(self.cad.lexico(), frozenset())

    def test_a_palavra_do_livro_passa_a_existir_para_a_fusao(self) -> None:
        sem = fusao.existe_do_livro("eng")
        com = fusao.existe_do_livro("eng", frozenset({"xyzzyq"}))
        self.assertFalse(sem("Xyzzyq,"))
        self.assertTrue(com("Xyzzyq,"))
        self.assertTrue(com("the"), "o léxico de sempre continua lá")
        self.assertFalse(com("Nf3"), "lance não vira palavra")

    def test_a_regra_4_ouve_a_palavra_do_livro(self) -> None:
        """O efeito que se quer: só o glifo leu o nome, e o nome agora existe. Sem ele, fica a leitura do outro leitor."""
        sem = fusao.fundir("o Xyzzyq", "o Xyzzgq", existe=fusao.existe_do_livro("eng"))
        com = fusao.fundir("o Xyzzyq", "o Xyzzgq", existe=fusao.existe_do_livro("eng", {"xyzzyq"}))
        self.assertEqual(fusao.texto_fundido(sem), "o Xyzzgq")
        self.assertEqual(fusao.texto_fundido(com), "o Xyzzyq")

    def test_ler_pagina_leva_as_palavras_ate_o_arbitro(self) -> None:
        pedidos: list[Any] = []
        original = fusao.existe_do_livro

        def espiao(lingua: str, palavras: Any = ()) -> Any:
            pedidos.append(frozenset(palavras))
            return original(lingua, palavras)

        import fitz

        pdf = self.pasta / "uma.pdf"
        doc = fitz.open()
        doc.new_page(width=400, height=600).insert_text((40, 60), "the Xyzzyq line", fontsize=11)
        doc.save(pdf)
        doc.close()

        class Falso:
            def ler_linhas(self, recortes: Any, *, lingua: str, dpi: int) -> Any:
                from chess_diagram_ocr.text.leitor_de_linha import Leitura
                from chess_diagram_ocr.text.tesseract import LinhaDoTesseract

                return Leitura(tuple(LinhaDoTesseract("the Xyzzgq line", (0.9, 0.9, 0.9)) for _ in recortes))

            def ler_folha(self, cinza: Any, *, lingua: str, dpi: int) -> Any:
                return [], ""

        cruas = [leitor._Cru(texto="the Xyzzyq line", caixa=Caixa(40, 50, 300, 70), confianca=0.9, procedencia="glifo") for _ in range(1)]  # noqa: SLF001
        with (
            mock.patch.object(leitor, "linhas_do_glifo", return_value=(cruas, [])),
            mock.patch("chess_diagram_ocr.detection.hybrid.detect_diagrams_in_pdf_page", return_value=[]),
            mock.patch.object(fusao, "existe_do_livro", espiao),
        ):
            lida = leitor.ler_pagina(pdf, 0, dpi=72, motor="fusao", lingua="eng", leitor_de_linha=Falso(), reconhecedor=object(), palavras_do_livro={"xyzzyq"})
        self.assertIn(frozenset({"xyzzyq"}), pedidos)
        self.assertIn("Xyzzyq", lida.texto())


class PreviaEAplicarTests(_ComCaderno):
    def test_a_previa_nao_grava_nada(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        antes = self.cad.caminho(0).read_bytes()
        vista = correcao_no_livro.previa(self.cad, "Gelfmnd", "Gelfand")
        self.assertEqual(len(vista.ocorrencias), 1)
        self.assertEqual(self.cad.caminho(0).read_bytes(), antes)

    def test_sem_previa_nao_troca(self) -> None:
        with self.assertRaises(correcao_no_livro.SemPrevia):
            correcao_no_livro.aplicar(self.cad, ("Gelfmnd", "Gelfand"))  # type: ignore[arg-type]

    def test_troca_em_todas_as_folhas_e_acha_a_palavra_inteira_com_a_caixa_dela(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        self.guardar(1, "Gelfmnd again and Gelfmndx and gelfmnd")
        self.guardar(2, "nothing here")
        vista = correcao_no_livro.previa(self.cad, "Gelfmnd", "Gelfand")
        self.assertEqual([o.pagina for o in vista.ocorrencias], [0, 1])
        feito = correcao_no_livro.aplicar(self.cad, vista)
        self.assertEqual((feito.trocas, feito.folhas), (2, (0, 1)))
        self.assertIn("the Gelfand line", self.cad.folha(0).para_texto())
        self.assertIn("Gelfand again and Gelfmndx and gelfmnd", self.cad.folha(1).para_texto())
        self.assertIn("nothing here", self.cad.folha(2).para_texto())

    def test_a_folha_vai_como_corrigida_e_o_nome_entra_no_lexico(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        feito = correcao_no_livro.aplicar(self.cad, correcao_no_livro.previa(self.cad, "Gelfmnd", "Gelfand"))
        self.assertEqual(self.cad.estado(0).estado, caderno.EDITADA)
        self.assertEqual(self.cad.estado(0).correcoes, 1)
        self.assertTrue(feito.palavra_nova)
        self.assertIn("gelfand", self.cad.lexico())

    def test_desfaz_folha_a_folha(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        self.guardar(1, "more Gelfmnd here")
        correcao_no_livro.aplicar(self.cad, correcao_no_livro.previa(self.cad, "Gelfmnd", "Gelfand"))
        self.assertIn("the Gelfmnd line", self.cad.anterior(0).para_texto())
        self.assertIn("more Gelfmnd here", self.cad.anterior(1).para_texto())
        self.assertIn("more Gelfand here", self.cad.folha(1).para_texto(), "voltar uma folha não mexe na outra")

    def test_a_ocorrencia_desmarcada_fica(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        self.guardar(1, "more Gelfmnd here")
        feito = correcao_no_livro.aplicar(self.cad, correcao_no_livro.previa(self.cad, "Gelfmnd", "Gelfand"), fora=[1])
        self.assertEqual(feito.folhas, (0,))
        self.assertIn("more Gelfmnd here", self.cad.folha(1).para_texto())

    def test_a_folha_conferida_vem_desmarcada(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        self.guardar(1, "more Gelfmnd here")
        self.cad.marcar(1, caderno.CONFERIDA)
        vista = correcao_no_livro.previa(self.cad, "Gelfmnd", "Gelfand")
        self.assertEqual(vista.desmarcadas_por_padrao(), frozenset({1}))

    def test_a_folha_que_mudou_depois_da_previa_fica_como_esta(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        vista = correcao_no_livro.previa(self.cad, "Gelfmnd", "Gelfand")
        self.cad.gravar(corrigido(self.cad.folha(0), "line", "lane"), correcoes=1)
        feito = correcao_no_livro.aplicar(self.cad, vista)
        self.assertEqual(feito.folhas_que_mudaram, (0,))
        self.assertIn("the Gelfmnd lane", self.cad.folha(0).para_texto())

    def test_disco_que_recusa_nao_levanta(self) -> None:
        """Em slot do PyQt6, exceção é `qFatal`: a folha que não gravou é contada."""
        self.guardar(0, "the Gelfmnd line")
        vista = correcao_no_livro.previa(self.cad, "Gelfmnd", "Gelfand")
        with mock.patch.object(self.cad, "gravar", side_effect=OSError("cheio")):
            feito = correcao_no_livro.aplicar(self.cad, vista)
        self.assertEqual(feito.folhas_que_nao_gravaram, (0,))
        self.assertEqual(feito.trocas, 0)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class JanelaTests(_ComCaderno):
    def setUp(self) -> None:
        super().setUp()
        aplicacao()
        self.painel = mock.MagicMock()
        self.painel.caderno_aberto = self.cad
        self.painel._guardar_a_folha.return_value = True  # noqa: SLF001

    def _nova(self, antes: str = "Gelfmnd", depois: str = "Gelfand") -> Any:
        from PyQt6.QtWidgets import QWidget

        pai = QWidget()
        self.addCleanup(descartar, pai)
        return JanelaDeCorrecaoNoLivro(self.painel, self.cad, antes=antes, depois=depois, pai=pai)

    def test_o_botao_so_acende_com_a_lista_na_tela(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        janela = self._nova()
        self.assertFalse(janela.btn_aplicar.isEnabled())
        self.assertIsNone(janela.aplicar_marcadas())
        self.assertIn("Gelfmnd", self.cad.folha(0).para_texto())
        janela.btn_previa.click()
        self.assertTrue(janela.btn_aplicar.isEnabled())
        self.assertEqual(janela.lista.count(), 1)

    def test_mudar_o_campo_apaga_a_previa(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        janela = self._nova()
        janela.btn_previa.click()
        janela.campo_depois.setText("Outro")
        self.assertFalse(janela.btn_aplicar.isEnabled())
        self.assertEqual(janela.lista.count(), 0)

    def test_o_clique_grava_no_caderno_o_que_esta_marcado(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        self.guardar(1, "more Gelfmnd here")
        janela = self._nova()
        janela.btn_previa.click()
        janela.lista.item(1).setCheckState(Qt.CheckState.Unchecked)
        janela.btn_aplicar.click()
        self.assertIn("the Gelfand line", self.cad.folha(0).para_texto())
        self.assertIn("more Gelfmnd here", self.cad.folha(1).para_texto())
        self.painel.folhas_corrigidas_no_livro.assert_called_once()

    def test_a_folha_da_tela_e_guardada_antes_de_trocar(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        janela = self._nova()
        janela.btn_previa.click()
        janela.btn_aplicar.click()
        self.painel._guardar_a_folha.assert_called_once()  # noqa: SLF001

    def test_a_folha_da_tela_que_nao_grava_nao_deixa_trocar(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        janela = self._nova()
        janela.btn_previa.click()
        self.painel._guardar_a_folha.return_value = False  # noqa: SLF001
        janela.btn_aplicar.click()
        self.assertIn("Gelfmnd", self.cad.folha(0).para_texto())
        self.painel.folhas_corrigidas_no_livro.assert_not_called()

    def test_o_caderno_que_nao_e_mais_o_da_aba_recusa(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        janela = self._nova()
        janela.btn_previa.click()
        self.painel.caderno_aberto = object()
        janela.btn_aplicar.click()
        self.assertIn("Gelfmnd", self.cad.folha(0).para_texto())
        self.painel._guardar_a_folha.assert_not_called()  # noqa: SLF001
        self.assertFalse(janela.btn_aplicar.isEnabled())
        self.assertIsNone(janela.ver_previa())

    def test_a_folha_conferida_aparece_desmarcada_e_dita(self) -> None:
        self.guardar(0, "the Gelfmnd line")
        self.cad.marcar(0, caderno.CONFERIDA)
        janela = self._nova()
        janela.btn_previa.click()
        self.assertEqual(janela.lista.item(0).checkState(), Qt.CheckState.Unchecked)
        self.assertIn("conferida", janela.lista.item(0).text())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelTests(unittest.TestCase):
    """A fiação na aba de verdade: a correção na tela ensina o léxico, e o comando abre a janela."""

    def setUp(self) -> None:
        aplicacao()
        self.pasta: Path = pasta_temporaria(self)
        self.pdf = self.pasta / "livro.pdf"
        import fitz

        doc = fitz.open()
        doc.new_page(width=400, height=600).insert_text((40, 60), "the Gelfmnd line", fontsize=11)
        doc.save(self.pdf)
        doc.close()
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=self.pasta / "rascunhos", pasta_de_cadernos=self.pasta / "cadernos")
        self.addCleanup(descartar, self.painel)
        self.painel.definir_livro(self.pdf, pagina=0)
        cad = self.painel._caderno  # noqa: SLF001
        assert cad is not None
        self.cad = cad
        self.cad.guardar_leitura(folha(0, "the Gelfmnd line", documento=str(self.pdf)), motor="fusao")
        self.painel._abrir_do_caderno(0)  # noqa: SLF001

    def test_a_correcao_na_tela_ensina_o_lexico_ao_gravar(self) -> None:
        self.painel._aplicar(corrigido(self.painel.documento, "Gelfmnd", "Xyzzyq"))  # noqa: SLF001
        self.assertTrue(self.painel._guardar_a_folha())  # noqa: SLF001
        self.assertIn("xyzzyq", self.cad.lexico())

    def test_o_comando_abre_com_a_ultima_correcao(self) -> None:
        self.cad.guardar_leitura(folha(1, "more Gelfmnd here", documento=str(self.pdf)), motor="fusao")
        self.painel._aplicar(corrigido(self.painel.documento, "Gelfmnd", "Gelfand"))  # noqa: SLF001
        janela = self.painel.corrigir_em_todas_as_folhas()
        self.addCleanup(descartar, janela)
        self.assertEqual((janela.campo_antes.text(), janela.campo_depois.text()), ("Gelfmnd", "Gelfand"))
        janela.btn_previa.click()
        janela.btn_aplicar.click()
        self.assertIn("more Gelfand here", self.cad.folha(1).para_texto())

    def test_a_folha_da_tela_volta_trocada(self) -> None:
        """**Com a palavra errada ainda na tela**: a versão anterior deste teste a corrigia antes, e passava sem `_abrir_do_caderno`."""
        janela = self.painel.corrigir_em_todas_as_folhas()
        self.addCleanup(descartar, janela)
        janela.campo_antes.setText("Gelfmnd")
        janela.campo_depois.setText("Gelfand")
        self.assertIn("the Gelfmnd line", self.painel.documento.para_texto())
        janela.btn_previa.click()
        janela.btn_aplicar.click()
        self.assertIn("the Gelfand line", self.painel.documento.para_texto())

    def test_sem_caderno_diz_e_nao_abre(self) -> None:
        self.painel._caderno = None  # noqa: SLF001
        frases: list[str] = []
        self.painel.estado.connect(frases.append)
        self.assertIsNone(self.painel.corrigir_em_todas_as_folhas())
        self.assertTrue(frases)



@unittest.skipUnless(TEM_PYQT, MOTIVO)
class NaJanelaDeVerdadeTests(_JanelaComLivro):
    """A `JanelaPrincipal` inteira, com o comando pela tabela dela, o caderno dela e a digitação no editor dela."""

    def preparar(self) -> tuple[Any, Any, Any]:
        janela = self.janela()
        janela.show()
        painel = janela.texto
        cad = painel.caderno_aberto
        assert cad is not None
        cad.guardar_leitura(folha(0, "the Gelfmnd line", documento=str(self.livro)), motor="fusao")
        cad.guardar_leitura(folha(1, "more Gelfmnd here", documento=str(self.livro)), motor="fusao")
        painel._abrir_do_caderno(0)  # noqa: SLF001
        self.app.processEvents()
        return janela, painel, cad

    def abrir_a_troca(self, janela: Any, painel: Any) -> Any:
        janela._comandos()["corrigir_em_todas_as_folhas"]()  # noqa: SLF001
        troca = painel._janela_de_correcao_no_livro  # noqa: SLF001
        self.addCleanup(descartar, troca)
        troca.campo_antes.setText("Gelfmnd")
        troca.campo_depois.setText("Gelfand")
        return troca

    def digitar(self, painel: Any, texto: str) -> None:
        painel.editor.setFocus()
        painel.editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClicks(painel.editor, texto)
        self.app.processEvents()

    def test_o_comando_troca_nas_folhas_e_na_tela(self) -> None:
        janela, painel, cad = self.preparar()
        troca = self.abrir_a_troca(janela, painel)
        troca.btn_previa.click()
        self.assertEqual(troca.lista.count(), 2)
        troca.btn_aplicar.click()
        self.assertIn("the Gelfand line", painel.documento.para_texto())
        self.assertIn("more Gelfand here", cad.folha(1).para_texto())
        self.assertIn("more Gelfmnd here", cad.anterior(1).para_texto())

    def test_o_que_se_digita_depois_da_previa_nao_some(self) -> None:
        """Certo -> errado, o defeito do crítico: `XYZ` sumia da tela e do disco, e nem o `.anterior` o guardava."""
        janela, painel, cad = self.preparar()
        troca = self.abrir_a_troca(janela, painel)
        troca.btn_previa.click()
        self.digitar(painel, "XYZ")
        self.assertIn("XYZ", painel.documento.para_texto())
        troca.btn_aplicar.click()
        self.assertIn("XYZ", painel.documento.para_texto())
        self.assertIn("XYZ", cad.folha(0).para_texto())
        self.assertIn("mudaram depois da prévia", troca.resumo.text())
        self.assertIn("more Gelfand here", cad.folha(1).para_texto(), "a outra folha, que ninguém tocou, foi trocada")

    def test_trocar_de_livro_com_a_janela_aberta_nao_grava_em_nenhum_dos_dois(self) -> None:
        import fitz

        janela, painel, cad = self.preparar()
        troca = self.abrir_a_troca(janela, painel)
        troca.btn_previa.click()
        pasta_antiga = cad.caminho(1)
        antes = pasta_antiga.read_bytes()

        outro = self.pasta / "outro.pdf"
        doc = fitz.open()
        for _ in range(3):
            doc.new_page(width=400, height=600).insert_text((40, 60), "outro livro", fontsize=11)
        doc.save(outro)
        doc.close()
        janela.abrir_pdf(outro)
        self.app.processEvents()
        self._esperar_o_detector(janela)
        novo = painel.caderno_aberto
        self.assertIsNot(novo, cad)
        novo.guardar_leitura(folha(0, "o texto do livro novo", documento=str(outro)), motor="fusao")
        painel._abrir_do_caderno(0)  # noqa: SLF001
        self.digitar(painel, "ABC")

        troca.btn_aplicar.click()
        self.assertIn("ABC", painel.documento.para_texto(), "a folha do livro novo não foi recarregada")
        self.assertEqual(pasta_antiga.read_bytes(), antes, "o caderno antigo, já sem a trava, não foi escrito")
        self.assertIn("mudou", troca.resumo.text())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LeituraDaAbaTests(unittest.TestCase):
    """O efeito na tela: o caderno ensinou o nome, e a fusão lida pela aba fica com ele."""

    def _na_tela(self, *, com_a_palavra: bool) -> str:
        import fitz

        from chess_diagram_ocr.text.leitor_de_linha import Leitura
        from chess_diagram_ocr.text.tesseract import LinhaDoTesseract

        app = aplicacao()
        pasta = pasta_temporaria(self)
        pdf = pasta / "livro.pdf"
        doc = fitz.open()
        pagina = doc.new_page(width=450, height=650)
        for n in range(30):
            pagina.insert_text((60, 60 + 18 * n), "o Xyzzyq vence", fontname="helv", fontsize=11)
        doc.save(pdf)
        doc.close()

        class Falso:
            def ler_linhas(self, recortes: Any, *, lingua: str, dpi: int) -> Any:
                return Leitura(tuple(LinhaDoTesseract("o Xyzzgq vence", (0.9, 0.9, 0.9)) for _ in recortes))

            def ler_folha(self, cinza: Any, *, lingua: str, dpi: int) -> Any:
                return [], ""

        painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta / "rascunhos", pasta_de_cadernos=pasta / "cadernos")
        self.addCleanup(descartar, painel)
        painel.definir_livro(pdf, pagina=0)
        caixa = painel.escolha_de_motor
        caixa.setCurrentIndex(caixa.findData("fusao"))
        caixa.activated.emit(caixa.currentIndex())
        if com_a_palavra:
            painel._caderno.acrescentar_ao_lexico("Xyzzyq")  # noqa: SLF001
        cruas = [leitor._Cru(texto="o Xyzzyq vence", caixa=Caixa(58, 50 + 18 * n, 300, 63 + 18 * n), confianca=0.9, procedencia="glifo") for n in range(30)]  # noqa: SLF001
        with (
            mock.patch.object(leitor, "linhas_do_glifo", return_value=(cruas, [])),
            mock.patch("chess_diagram_ocr.detection.hybrid.detect_diagrams_in_pdf_page", return_value=[]),
            mock.patch("chess_diagram_ocr.text.leitor_de_linha.leitor_padrao", return_value=Falso()),
        ):
            painel.ler()
            tarefa = painel._tarefa  # noqa: SLF001
            self.assertIsNotNone(tarefa)
            self.assertTrue(tarefa.wait(30_000))  # type: ignore[union-attr]
            app.processEvents()
        return painel.documento.para_texto()

    def test_o_nome_ensinado_vence_na_tela_e_sem_ele_nao(self) -> None:
        self.assertIn("Xyzzgq", self._na_tela(com_a_palavra=False))
        self.assertIn("Xyzzyq", self._na_tela(com_a_palavra=True))


if __name__ == "__main__":
    unittest.main()
