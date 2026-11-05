"""A primeira entrega da prosa na janela: a caixa de motor, a língua, o selo e a marca (S-710, S-716 a S-718).

**Os testes afirmam o efeito no texto mostrado**, e não uma chamada: o PDF é de verdade, desenhado aqui, e
`ler_pagina` roda inteiro. Só o que precisa de modelo ou de binário é trocado: as linhas do glifo, o detector
de diagrama e o Tesseract.
"""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import boxes, leitor, pagina, rico, tesseract
from chess_diagram_ocr.text.leitor_de_linha import Leitura
from chess_diagram_ocr.ui import state as estado_da_janela
from chess_diagram_ocr.ui import strings

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto


class _Falso:
    """O Tesseract de mentira: lê o que lhe mandam, e anota em que língua pediram."""

    def __init__(self, texto: str = "the white Nf3 wins a pawn") -> None:
        self.texto = texto
        self.linguas: list[str] = []

    def ler_linhas(self, recortes: Sequence[np.ndarray], *, lingua: str, dpi: int) -> Leitura:
        self.linguas.append(lingua)
        return Leitura(tuple(tesseract.LinhaDoTesseract(self.texto, (0.99,) * len(self.texto.split())) for _ in recortes))

    def ler_folha(self, cinza: np.ndarray, *, lingua: str, dpi: int) -> tuple[list[tesseract.Palavra], str]:
        return ([], "Sem Tesseract.")


def _crua(texto: str, y: int) -> Any:
    return leitor._Cru(texto=texto, caixa=boxes.Caixa(58, y, 300, y + 13), confianca=0.9, procedencia="glifo")  # noqa: SLF001


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Aba(unittest.TestCase):
    def setUp(self) -> None:
        import fitz

        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.pasta = pasta_temporaria(self)
        self.livro = self.pasta / "livro.pdf"
        doc = fitz.open()
        folha = doc.new_page(width=450, height=650)
        for n in range(30):
            folha.insert_text((60, 60 + 18 * n), "the white knight wins a pawn", fontname="helv", fontsize=11)
        doc.save(self.livro)
        doc.close()
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=self.pasta / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(1000, 700)
        self.painel.show()
        self.app.processEvents()
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)
        self.painel.definir_livro(self.livro, pagina=0)

    def escolher(self, motor: str) -> None:
        caixa = self.painel.escolha_de_motor
        caixa.setCurrentIndex(caixa.findData(motor))
        caixa.activated.emit(caixa.currentIndex())

    def ler(self, cruas: Sequence[Any], falso: _Falso | None = None) -> None:
        with (
            mock.patch.object(leitor, "linhas_do_glifo", return_value=(list(cruas), [])),
            mock.patch("chess_diagram_ocr.detection.hybrid.detect_diagrams_in_pdf_page", return_value=[]),
            mock.patch("chess_diagram_ocr.text.leitor_de_linha.leitor_padrao", return_value=falso or _Falso()),
        ):
            self.painel.ler()
            tarefa = self.painel._tarefa
            self.assertIsNotNone(tarefa, "a tarefa não partiu")
            self.assertTrue(tarefa.wait(30_000))  # type: ignore[union-attr]
            self.app.processEvents()

    def boas(self, texto: str = "tne wbite ♘f3 wins a pawn") -> list[Any]:
        return [_crua(texto, 50 + 18 * n) for n in range(30)]


class CaixaDeMotorTests(_Aba):
    def test_os_dois_novos_tem_rotulo_e_nunca_o_identificador_cru(self) -> None:
        caixa = self.painel.escolha_de_motor
        self.assertEqual(caixa.itemText(caixa.findData("camada_prosa")), "Camada na prosa (livro digital)")
        self.assertEqual(caixa.itemText(caixa.findData("fusao")), "Glifo + Tesseract (experimental)")

    def test_o_padrao_nao_mudou(self) -> None:
        self.assertEqual(self.painel.motor, "auto")

    def test_escolher_a_camada_na_prosa_muda_o_texto_na_tela(self) -> None:
        self.escolher("camada_prosa")
        self.ler(self.boas())
        # A camada diz `knight` onde o glifo viu `♘f3`, e a palavra que existe vence: é a regra 1.
        self.assertIn("the white knight wins a pawn", self.painel.texto())
        self.assertNotIn("tne", self.painel.texto())

    def test_escolher_a_fusao_muda_o_texto_na_tela_e_le_na_lingua_escolhida(self) -> None:
        falso = _Falso()
        self.escolher("fusao")
        caixa = self.painel.escolha_de_lingua
        caixa.setCurrentIndex(caixa.findData("por"))
        caixa.activated.emit(caixa.currentIndex())
        self.ler(self.boas(), falso)
        self.assertIn("the white ♘f3 wins a pawn", self.painel.texto())
        self.assertEqual(falso.linguas, ["por"])

    def test_motor_e_lingua_sobrevivem_a_sessao(self) -> None:
        self.painel.definir_motor("fusao")
        self.painel.definir_lingua("deu")
        guardado = estado_da_janela.AppState()
        self.painel.anotar_estado(guardado)
        self.assertEqual((guardado.texto_motor, guardado.texto_lingua), ("fusao", "deu"))
        relido = estado_da_janela.state_from_dict(guardado.to_dict())
        self.assertEqual(relido.texto_lingua, "deu")
        self.painel.definir_motor("glifo")
        self.painel.definir_lingua("eng")
        self.painel.aplicar_estado(relido)
        self.assertEqual((self.painel.motor, self.painel.lingua), ("fusao", "deu"))
        self.assertEqual(self.painel.escolha_de_lingua.currentData(), "deu")

    def test_lingua_desconhecida_e_ignorada(self) -> None:
        self.painel.definir_lingua("klingon")
        self.assertEqual(self.painel.lingua, tesseract.LINGUA_PADRAO)


class SeloTests(_Aba):
    def test_a_folha_lida_nao_tem_selo(self) -> None:
        self.escolher("glifo")
        self.ler(self.boas("the white knight wins a pawn"))
        self.assertTrue(self.painel.selo_da_folha.isHidden())

    def test_a_folha_perdida_mostra_o_selo_em_vez_de_sair_calada(self) -> None:
        self.escolher("glifo")
        self.ler([_crua("h", 50)])
        self.assertFalse(self.painel.selo_da_folha.isHidden())
        self.assertIn("não foi lida inteira", self.painel.selo_da_folha.text())
        self.assertIn("Sem Tesseract.", self.painel.selo_da_folha.text())

    def test_o_selo_some_na_folha_seguinte(self) -> None:
        aviso = pagina.Aviso(pagina.FOLHA_NAO_LIDA, "Não foi lida.")
        self.painel.mostrar_pagina(pagina.PaginaLida(pagina=0, avisos=(aviso,)))
        self.assertFalse(self.painel.selo_da_folha.isHidden())
        self.painel.mostrar_pagina(pagina.PaginaLida(pagina=1))
        self.assertTrue(self.painel.selo_da_folha.isHidden())

    def test_o_selo_volta_com_a_folha_reaberta_do_arquivo(self) -> None:
        from chess_diagram_ocr.text import arquivo

        aviso = pagina.Aviso(pagina.LEIAUTE_DE_RESERVA, "Relida pela reserva.")
        linha = pagina.LinhaLida(texto="texto", bbox=(0, 0, 9, 9))
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        lida = pagina.PaginaLida(colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), avisos=(aviso,))
        reaberto = arquivo.de_json(arquivo.para_json(rico.de_pagina(lida)))
        self.painel.desenhar_documento(reaberto)
        self.painel._atualizar_status()
        self.assertEqual(self.painel.selo_da_folha.text(), "Relida pela reserva.")


class LinguaNoCadernoTests(_Aba):
    """Trocar a língua da fusão é pedir a leitura nova, como trocar de motor (S-717)."""

    def test_o_motor_gravado_leva_a_lingua_so_na_fusao(self) -> None:
        self.painel.definir_motor("fusao")
        self.painel.definir_lingua("por")
        self.assertEqual(self.painel._motor_gravado(), "fusao:por")
        self.painel.definir_motor("glifo")
        self.assertEqual(self.painel._motor_gravado(), "glifo")

    def test_a_folha_lida_em_outra_lingua_nao_abre_do_caderno(self) -> None:
        from chess_diagram_ocr.text import caderno

        estado = caderno.EstadoDaFolha(pagina=0, estado=caderno.LIDA, motor="fusao:eng", modo_bloco=False)
        self.painel.definir_motor("fusao")
        self.painel.definir_lingua("eng")
        self.assertTrue(caderno.abre_do_caderno(estado, motor=self.painel._motor_gravado(), modo_bloco=False))
        self.painel.definir_lingua("por")
        self.assertFalse(caderno.abre_do_caderno(estado, motor=self.painel._motor_gravado(), modo_bloco=False))


class ProximaARevisarTests(_Aba):
    def _com_marca(self) -> None:
        linha = pagina.LinhaLida(texto="uma palavra errada outra", bbox=(0, 0, 9, 9), revisar_em=((4, 11), (19, 24)))
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        self.painel.mostrar_pagina(
            pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), marca_por_palavra=True)
        )

    def test_vai_de_palavra_em_palavra_e_da_a_volta(self) -> None:
        self._com_marca()
        vistas = []
        for _ in range(3):
            self.painel.proxima_a_revisar()
            vistas.append(self.painel.editor.textCursor().selectedText())
        self.assertEqual(vistas, ["palavra", "outra", "palavra"])

    def test_sem_marca_responde_no_rodape(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("nada a revisar"))
        self.painel.proxima_a_revisar()
        self.assertEqual(self.recados[-1], strings.NADA_A_REVISAR)

    def test_o_comando_esta_na_fita(self) -> None:
        self.assertIsNotNone(self.painel.fita.botao("proxima_a_revisar"))


class CorrigirAMarcaNoEditorTests(_Aba):
    """A correção de verdade: o editor grava a diferença mínima, e os pedaços da palavra não são marca.

    **Tem de ser pelo editor.** Trocar a corrida inteira por `replace` é o que nenhuma tecla faz, e foi assim que
    `w` e `ite` chegaram ao arquivo como palavras a revisar sem nenhum teste acusar.
    """

    def _folha(self, texto: str, *marcas: tuple[int, int]) -> None:
        linha = pagina.LinhaLida(texto=texto, bbox=(0, 0, 9, 9), revisar_em=marcas)
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        self.painel.mostrar_pagina(
            pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), marca_por_palavra=True)
        )

    def _cursor(self, inicio: int, fim: int | None = None) -> None:
        editor = self.painel.editor
        cursor = editor.textCursor()
        cursor.setPosition(inicio)
        if fim is not None:
            cursor.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.setFocus()
        self.app.processEvents()

    def _marcas_depois_de_reabrir(self) -> list[str]:
        from chess_diagram_ocr.text import arquivo

        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "folha.cvtxt"
            self.painel._salvar_documento_em(caminho)  # noqa: SLF001
            reaberto = arquivo.carregar(caminho)
        texto = reaberto.para_texto()
        return [texto[a:b] for a, b in rico.intervalos_a_revisar(reaberto)]

    def _paradas(self) -> list[str]:
        vistas = []
        for _ in range(3):
            self.painel.proxima_a_revisar()
            vistas.append(self.painel.editor.textCursor().selectedText())
        return vistas

    def _so_sobra(self, *palavras: str) -> None:
        self.assertEqual(self._marcas_depois_de_reabrir(), list(palavras))
        self.assertEqual(set(self._paradas()), set(palavras))

    def test_backspace_e_a_letra_certa(self) -> None:
        self._folha("the wbite knight wlns a pawn", (4, 9), (17, 21))
        self._cursor(6)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Backspace)
        QTest.keyClicks(self.painel.editor, "h")
        self.assertIn("the white knight", self.painel.editor.toPlainText())
        self._so_sobra("wlns")

    def test_selecionar_a_letra_e_digitar(self) -> None:
        self._folha("the wbite knight wlns a pawn", (4, 9), (17, 21))
        self._cursor(5, 6)
        QTest.keyClicks(self.painel.editor, "h")
        self._so_sobra("wlns")

    def test_a_letra_que_faltava(self) -> None:
        self._folha("the whte knight wlns a pawn", (4, 8), (16, 20))
        self._cursor(6)
        QTest.keyClicks(self.painel.editor, "i")
        self._so_sobra("wlns")

    def test_a_letra_que_faltava_no_comeco(self) -> None:
        """`hite` continua inteiro num trecho igual ao lido, e a palavra agora é outra."""
        self._folha("the hite knight wlns a pawn", (4, 8), (16, 20))
        self._cursor(4)
        QTest.keyClicks(self.painel.editor, "w")
        self._so_sobra("wlns")

    def test_a_letra_a_mais_no_meio(self) -> None:
        self._folha("the whiite knight wlns a pawn", (4, 10), (18, 22))
        self._cursor(6)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self._so_sobra("wlns")

    def test_a_letra_a_mais_no_comeco(self) -> None:
        """O que sobra é igual ao lido, e a palavra corrigida inteira cabe num trecho igual."""
        self._folha("the xwhite knight wlns a pawn", (4, 10), (18, 22))
        self._cursor(4)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self._so_sobra("wlns")

    def test_a_letra_a_mais_no_fim(self) -> None:
        self._folha("the whitex knight wlns a pawn", (4, 10), (18, 22))
        self._cursor(9)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Delete)
        self._so_sobra("wlns")

    def test_o_bloco_de_duas_palavras_marcadas(self) -> None:
        """Só o espaço fica de texto sem marca, e ele basta para não ser a faixa do bloco inteiro."""
        self._folha("wbite wlns", (0, 5), (6, 10))
        self._cursor(2)
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Backspace)
        QTest.keyClicks(self.painel.editor, "h")
        self._so_sobra("wlns")

    def test_a_letra_que_faltava_no_fim(self) -> None:
        self._folha("the whit knight wlns a pawn", (4, 8), (16, 20))
        self._cursor(8)
        QTest.keyClicks(self.painel.editor, "e")
        self._so_sobra("wlns")

    def _trocar_letra(self, posicao: int, letra: str) -> None:
        self._cursor(posicao, posicao + 1)
        QTest.keyClicks(self.painel.editor, letra)

    def test_gravar_corrigir_e_gravar_nao_apaga_a_marca_intacta(self) -> None:
        """O carimbo da primeira gravação funde o resto do bloco, e a segunda não pode tomá-lo por faixa."""
        self._folha("the wbite knight wlns a pawm", (4, 9), (17, 21))
        self._trocar_letra(5, "h")
        self.assertEqual(self._marcas_depois_de_reabrir(), ["wlns"])
        self._trocar_letra(27, "n")
        self._so_sobra("wlns")

    def test_gravar_reabrir_e_corrigir_de_novo(self) -> None:
        from chess_diagram_ocr.text import arquivo

        self._folha("the wbite knight wlns a pawm", (4, 9), (17, 21))
        self._trocar_letra(5, "h")
        caminho = self.pasta / "folha.cvtxt"
        self.painel._salvar_documento_em(caminho)  # noqa: SLF001
        self.painel.desenhar_documento(arquivo.carregar(caminho))
        self._trocar_letra(27, "n")
        self._so_sobra("wlns")

    def test_shift_f7_nao_para_nos_pedacos_antes_de_gravar(self) -> None:
        self._folha("the wbite knight wlns a pawn", (4, 9), (17, 21))
        self._trocar_letra(5, "h")
        self.assertEqual(set(self._paradas()), {"wlns"})

    def test_duas_marcas_na_juncao_das_linhas_sao_duas(self) -> None:
        linhas = [
            pagina.LinhaLida(texto="the wbite", bbox=(0, 0, 9, 9), revisar_em=((4, 9),)),
            pagina.LinhaLida(texto="wlns a pawn", bbox=(0, 10, 9, 19), revisar_em=((0, 4),)),
        ]
        bloco = pagina.BlocoDeTexto.de_linhas(linhas)
        self.painel.mostrar_pagina(
            pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),), marca_por_palavra=True)
        )
        self.assertEqual(set(self._paradas()), {"wbite", "wlns"})
        self._trocar_letra(5, "h")
        self._so_sobra("wlns")

    def _faixa_no_bloco_inteiro(self) -> None:
        """Sem marca por palavra e com confiança baixa: quem leu o parágrafo para corrigi-lo já o conferiu."""
        linha = pagina.LinhaLida(texto="the wbite knight wlns a pawn", bbox=(0, 0, 9, 9), confianca=0.1, procedencia="glifo")
        bloco = pagina.BlocoDeTexto.de_linhas([linha])
        self.painel.mostrar_pagina(pagina.PaginaLida(pagina=0, colunas=(pagina.Coluna(indice=0, blocos=(bloco,)),)))
        self.assertTrue(rico.intervalos_a_revisar(self.painel.documento), "a faixa não veio: o teste não vigiaria nada")

    def test_a_faixa_do_bloco_inteiro_sai_com_uma_letra(self) -> None:
        self._faixa_no_bloco_inteiro()
        self._trocar_letra(5, "h")
        self.assertEqual(self._marcas_depois_de_reabrir(), [])

    def test_a_faixa_do_bloco_inteiro_sai_com_a_palavra_redigitada(self) -> None:
        """Aqui sobram palavras inteiras e intactas em volta, e elas não são marcas de palavra."""
        self._faixa_no_bloco_inteiro()
        self._cursor(4, 9)
        QTest.keyClicks(self.painel.editor, "white")
        self.assertEqual(self._marcas_depois_de_reabrir(), [])

    def test_a_palavra_inteira_redigitada(self) -> None:
        self._folha("the wbite knight wlns a pawn", (4, 9), (17, 21))
        self._cursor(4, 9)
        QTest.keyClicks(self.painel.editor, "white")
        self._so_sobra("wlns")


if __name__ == "__main__":
    unittest.main()
