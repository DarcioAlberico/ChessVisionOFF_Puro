"""A tela da aba Texto concorda com o documento (S-601 a S-604).

**O defeito que estes testes fecham.** O alinhamento e os estilos de parágrafo estavam no documento,
no arquivo e na exportação -- e não na tela. `_desenhar` escrevia o formato do bloco de cada corrida
**antes** de inserir o texto dela, e a corrida separadora (`"\\n\\n"`, sem atributos) chegava com o
cursor ainda no bloco do parágrafo anterior: o formato vazio dela apagava o que o parágrafo tinha
acabado de receber. Só o último parágrafo da folha escapava. A miniatura do diagrama, por sua vez,
nunca recebia o formato da marca (o D2).

Os testes de `texto_formato.bloco_de` continuavam verdes o tempo todo, porque afirmavam o que a
função **devolve**. Estes leem o bloco **desenhado**, por `paridade_do_texto.divergencias`.
"""

from __future__ import annotations

import unittest

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TEM_PYQT:
    from paridade_do_texto import divergencias
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import OBJETO, PainelDeTexto


def _bloco(conteudo: str) -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas([LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), 1.0, "camada", None, None)])  # type: ignore[arg-type]


def _folha(*blocos: object) -> PaginaLida:
    return PaginaLida(documento="livro.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=tuple(blocos)),))  # type: ignore[arg-type]


TRES = ("Primeiro parágrafo da folha.", "Segundo parágrafo, o do meio.", "Terceiro e último parágrafo.")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Aba(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(700, 500)
        self.painel.show()
        self.app.processEvents()

    def cursor_em(self, deslocamento: int, fim: int | None = None) -> None:
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(self.painel._mapa.posicao(deslocamento))
        if fim is not None:
            cursor.setPosition(self.painel._mapa.posicao(fim), QTextCursor.MoveMode.KeepAnchor)
        self.painel.editor.setTextCursor(cursor)

    def concorda(self) -> None:
        self.assertEqual(divergencias(self.painel), [])

    def blocos(self) -> list:
        lista = []
        bloco = self.painel.editor.document().begin()
        while bloco.isValid():
            lista.append(bloco)
            bloco = bloco.next()
        return lista


class ParagrafoTests(_Aba):
    """S-601: o formato de parágrafo chega ao bloco do parágrafo -- o primeiro, o do meio e o último."""

    def setUp(self) -> None:
        super().setUp()
        self.painel.mostrar_pagina(_folha(*(_bloco(t) for t in TRES)))

    def inicio_de(self, indice: int) -> int:
        return self.painel.documento.para_texto().index(TRES[indice])

    def test_o_alinhamento_chega_a_cada_paragrafo(self) -> None:
        for indice in range(3):
            for alinhamento in rico.ALINHAMENTOS:
                with self.subTest(paragrafo=indice, alinhamento=alinhamento):
                    self.cursor_em(self.inicio_de(indice) + 2)
                    self.painel.alinhar(alinhamento)
                    self.concorda()

    def test_o_estilo_chega_a_cada_paragrafo(self) -> None:
        for indice in range(3):
            for estilo in rico.ESTILOS:
                with self.subTest(paragrafo=indice, estilo=estilo):
                    self.cursor_em(self.inicio_de(indice) + 2)
                    self.painel.aplicar_estilo(estilo)
                    self.concorda()

    def test_o_centro_do_paragrafo_do_meio_e_visto_na_tela(self) -> None:
        """O D1 com nome: este era o caso que a tela desenhava à esquerda."""
        self.cursor_em(self.inicio_de(1) + 2)
        self.painel.alinhar_centro()
        meio = next(b for b in self.blocos() if b.text() == TRES[1])
        self.assertEqual(meio.blockFormat().alignment(), Qt.AlignmentFlag.AlignHCenter)

    def test_as_linhas_em_branco_saem_sem_formato(self) -> None:
        self.cursor_em(self.inicio_de(0) + 2)
        self.painel.estilo_titulo()
        self.painel.alinhar_centro()
        for bloco in self.blocos():
            if not bloco.text():
                with self.subTest(bloco=bloco.blockNumber()):
                    formato = bloco.blockFormat()
                    self.assertEqual(formato.alignment(), Qt.AlignmentFlag.AlignLeft)
                    self.assertEqual(formato.topMargin(), 0)
                    self.assertEqual(formato.textIndent(), 0)

    def test_enter_na_linha_em_branco_depois_do_titulo_insere_a_linha(self) -> None:
        """A primeira versão do conserto engolia este `Enter` (primeira revisão do plano)."""
        self.cursor_em(self.inicio_de(0) + 2)
        self.painel.estilo_titulo()
        self.painel.alinhar_centro()
        em_branco = next(b for b in self.blocos() if not b.text())
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(em_branco.position())
        self.painel.editor.setTextCursor(cursor)
        self.painel.editor.setFocus()
        antes = self.painel.documento.para_texto()
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(len(self.painel.documento.para_texto()), len(antes) + 1)
        self.concorda()

    def test_a_tela_concorda_depois_de_digitar_desfazer_refazer_e_aproximar(self) -> None:
        self.cursor_em(self.inicio_de(1) + 2)
        self.painel.alinhar_centro()
        self.cursor_em(self.inicio_de(1) + len(TRES[1]))
        self.painel.editor.setFocus()
        QTest.keyClicks(self.painel.editor, " Mais")
        self.app.processEvents()
        self.concorda()
        QTest.keyClick(self.painel.editor, Qt.Key.Key_Return)
        self.app.processEvents()
        self.concorda()
        self.painel.desfazer()
        self.concorda()
        self.painel.refazer()
        self.concorda()
        self.painel.aproximar_texto()
        self.concorda()


class MiniaturaTests(_Aba):
    """S-602: a figura mora no bloco da marca, e anda com o alinhamento dela."""

    def setUp(self) -> None:
        super().setUp()
        self.painel.definir_livro(None)
        self.pagina = _folha(_bloco("Antes do diagrama."), BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 60.0, 60.0)), _bloco("Depois do diagrama."))
        self.painel.mostrar_pagina(self.pagina, folha_rgb=np.full((400, 400, 3), 210, np.uint8), dpi=72)

    def marca(self) -> tuple[int, int]:
        texto = self.painel.documento.para_texto()
        inicio = texto.index("[Diagrama 1]")
        return inicio, inicio + len("[Diagrama 1]")

    def bloco_da_figura(self):
        return next(b for b in self.blocos() if OBJETO in b.text())

    def test_a_figura_segue_o_alinhamento_da_marca(self) -> None:
        for alinhamento, flag in (
            (rico.ALINHAMENTO_CENTRO, Qt.AlignmentFlag.AlignHCenter),
            (rico.ALINHAMENTO_DIREITA, Qt.AlignmentFlag.AlignRight),
            (rico.ALINHAMENTO_ESQUERDA, Qt.AlignmentFlag.AlignLeft),
        ):
            with self.subTest(alinhamento=alinhamento):
                self.cursor_em(*self.marca())
                self.painel.alinhar(alinhamento)
                self.assertEqual(self.bloco_da_figura().blockFormat().alignment(), flag)
                self.concorda()

    def test_a_figura_nao_herda_o_recuo_da_prosa_de_cima(self) -> None:
        self.cursor_em(2)
        self.painel.estilo_prosa()
        self.assertEqual(self.bloco_da_figura().blockFormat().textIndent(), 0)
        self.concorda()

    def test_sem_separador_antes_a_figura_ganha_bloco_proprio(self) -> None:
        """`rico.editar` deixa apagar o separador; a figura não pode cair no meio da prosa."""
        texto = self.painel.documento.para_texto()
        fim_do_antes = texto.index("Antes do diagrama.") + len("Antes do diagrama.")
        colado = rico.editar(self.painel.documento, fim_do_antes, texto.index("[Diagrama 1]"), "")
        self.assertIn("diagrama.[Diagrama 1]", colado.para_texto())
        self.painel.desenhar_documento(colado)
        figura = self.bloco_da_figura()
        self.assertEqual(figura.text(), OBJETO, "a figura sozinha no bloco dela")
        self.concorda()
        # E a tradução continua certa: a marca é achada onde ela está.
        inicio, fim = self.marca()
        self.cursor_em(inicio, fim)
        self.assertEqual(self.painel._intervalo(), (inicio, fim))

    def test_copiar_a_folha_nao_traz_linha_a_mais(self) -> None:
        self.painel.selecionar_tudo()
        copiado = self.painel.editor.textCursor().selectedText()
        # Uma figura, um separador de bloco depois dela -- e nenhum bloco extra antes.
        self.assertEqual(copiado.count(OBJETO), 1)
        self.assertNotIn("   ", copiado)


if __name__ == "__main__":
    unittest.main()
