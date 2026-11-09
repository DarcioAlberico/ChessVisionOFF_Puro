"""O resultado que chega depois só entra se a tela ainda for a dele: livro **e** página (S-823).

A leitura da janela levava só a página. O livro B abre na página em que a leitura do livro A foi
pedida, e os diagramas de A apareciam na tela de B -- com o nome e a página de B no `Ctrl+S`.
As leituras aqui correm em `TarefaAdiada` (S-805): o resultado só chega quando o teste manda,
depois de a tela ter mudado, que é o caso normal de uma thread.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, TarefaAdiada, aplicacao, esperar
from test_app_pyqt import ServicoComLeituraFixa, diagrama_lido, pdf_de_teste

from chess_diagram_ocr.service import RecognitionCanceled, RecognizedDiagram
from chess_diagram_ocr.ui.ancora_da_tela import AncoraDaTela, ainda_vale, frase_do_descarte

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest


class AncoraDaTelaTests(unittest.TestCase):
    def test_a_mesma_pagina_de_outro_livro_nao_vale(self) -> None:
        self.assertFalse(ainda_vale(AncoraDaTela.de("PDF/A.pdf", 0), AncoraDaTela.de("PDF/B.pdf", 0)))

    def test_outra_pagina_do_mesmo_livro_nao_vale(self) -> None:
        self.assertFalse(ainda_vale(AncoraDaTela.de("PDF/A.pdf", 0), AncoraDaTela.de("PDF/A.pdf", 1)))

    def test_o_mesmo_livro_escrito_de_outro_jeito_vale(self) -> None:
        """A chave do livro (S-827), e não o caminho cru: `..` e a barra não fazem outra tela."""
        self.assertTrue(ainda_vale(AncoraDaTela.de("PDF/sub/../A.pdf", 2), AncoraDaTela.de(Path("PDF") / "A.pdf", 2)))

    def test_a_frase_diz_se_foi_o_livro_ou_a_pagina(self) -> None:
        de_a = AncoraDaTela.de("A.pdf", 4)
        self.assertIn("outro livro", frase_do_descarte(de_a, AncoraDaTela.de("B.pdf", 4)))
        self.assertIn("outra página", frase_do_descarte(de_a, AncoraDaTela.de("A.pdf", 0)))
        self.assertIn("página 5", frase_do_descarte(de_a, AncoraDaTela.de("A.pdf", 0)))


class ServicoQueCancela(ServicoComLeituraFixa):
    """A leitura que parou a pedido depois do primeiro diagrama: devolve o parcial pela exceção."""

    def recognize_page(self, *args: object, **kwargs: object) -> list[RecognizedDiagram]:
        lidos = super().recognize_page(*args, **kwargs)  # type: ignore[arg-type]
        raise RecognitionCanceled(lidos)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ChegadaDepoisDaTrocaTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()
        self.pasta = pasta_temporaria(self)
        TarefaAdiada.pendentes.clear()
        self.addCleanup(TarefaAdiada.pendentes.clear)

    def _janela(self, servico: object):
        from chess_diagram_ocr.qt.janela import JanelaPrincipal

        csv = self.pasta / "labels.csv"
        janela = JanelaPrincipal(
            motor=None,
            servico=servico,  # type: ignore[arg-type]
            csv_de_rotulos=csv,
            caminho_do_cache=self.pasta / "posicoes.sqlite",
            caminho_do_estado=self.pasta / "janela.json",
        )
        self.addCleanup(janela.deleteLater)
        self.addCleanup(janela.close)
        janela.resize(1000, 700)
        return janela

    def _ler_adiado(self, janela: object) -> None:
        """«Ler página», com a tarefa segurada até o teste entregar."""
        from chess_diagram_ocr.qt import janela as modulo

        with mock.patch.object(modulo, "Tarefa", TarefaAdiada):
            janela.ler_pagina()  # type: ignore[attr-defined]
        self.assertEqual(1, len(TarefaAdiada.pendentes), "a leitura não ficou pendente")

    def test_a_leitura_do_livro_a_nao_entra_no_livro_b(self) -> None:
        janela = self._janela(ServicoComLeituraFixa([diagrama_lido(0)]))
        janela.abrir_pdf(pdf_de_teste(self.pasta / "A.pdf"))
        esperar(janela)
        self._ler_adiado(janela)

        janela.abrir_pdf(pdf_de_teste(self.pasta / "B.pdf"))  # abre na página 1, a mesma
        esperar(janela)
        TarefaAdiada.entregar_todas()
        QTest.qWait(0)

        self.assertEqual(0, janela.painel.lista.count(), "os diagramas do livro A entraram na tela do B")
        self.assertIsNone(janela.editor.origin, "o Ctrl+S gravaria a amostra de A com o nome de B")
        self.assertIn("outro livro", janela.rodape.mensagem())

    def test_abrir_outro_livro_cancela_a_leitura_em_curso(self) -> None:
        janela = self._janela(ServicoComLeituraFixa([diagrama_lido(0)]))
        janela.abrir_pdf(pdf_de_teste(self.pasta / "A.pdf"))
        esperar(janela)
        self._ler_adiado(janela)
        janela.abrir_pdf(pdf_de_teste(self.pasta / "B.pdf"))
        esperar(janela)
        self.assertTrue(TarefaAdiada.pendentes[0].cancelada, "a leitura do livro que saiu seguiu correndo")
        TarefaAdiada.entregar_todas()

    def test_cancelar_depois_de_virar_a_pagina_nao_carrega_o_parcial(self) -> None:
        """O cancelamento passava a página **atual**: o parcial da 1 entrava como da 2."""
        janela = self._janela(ServicoQueCancela([diagrama_lido(0)]))
        janela.abrir_pdf(pdf_de_teste(self.pasta / "duas.pdf", paginas=2))
        esperar(janela)
        self._ler_adiado(janela)

        janela.pdf.ir_para_pagina(1)
        esperar(janela)
        QTest.mouseClick(janela.rodape._btn_cancelar, Qt.MouseButton.LeftButton)
        TarefaAdiada.entregar_todas()
        QTest.qWait(0)

        self.assertEqual(0, janela.painel.lista.count(), "o parcial da página 1 entrou como da página 2")
        self.assertIsNone(janela.editor.origin)
        self.assertIn("outra página", janela.rodape.mensagem())

    def test_cancelar_na_mesma_pagina_ainda_carrega_o_parcial(self) -> None:
        """O outro lado: com a tela parada, o lido fica (C2)."""
        janela = self._janela(ServicoQueCancela([diagrama_lido(0)]))
        janela.abrir_pdf(pdf_de_teste(self.pasta / "duas.pdf", paginas=2))
        esperar(janela)
        self._ler_adiado(janela)

        QTest.mouseClick(janela.rodape._btn_cancelar, Qt.MouseButton.LeftButton)
        TarefaAdiada.entregar_todas()
        QTest.qWait(0)

        self.assertEqual(1, janela.painel.lista.count())
        self.assertIn("Leitura cancelada", janela.rodape.mensagem())


if __name__ == "__main__":
    unittest.main()
