"""Os diagramas na aba Texto do Qt: a folha que a leitura entrega, o `.cvtxt` reaberto, a exportação.

**O defeito que estes testes fecham.** A miniatura de `[Diagrama N]` é recorte da folha renderizada,
e o porte para o Qt só a desenhava quando um teste lhe dava a folha por `mostrar_pagina(...,
folha_rgb=)`: a leitura de verdade (`ler`) jogava a imagem fora na volta da thread, e no produto a
aba mostrava a marca sem figura nenhuma. O `.md` e o `.html` saíam com `![Diagrama 1]()` de alvo
vazio, e o `.cvtxt` reaberto nunca refazia as miniaturas do livro.

O que cada formato faz com o diagrama é de `text/exportacao.py` (`tests/test_texto_exportacao.py`);
o que o arquivo guarda é de `text/arquivo.py`. Aqui se afirma a costura: a imagem atravessa a thread,
chega ao editor, vira PNG ao lado do arquivo exportado e volta do livro quando ele ainda está lá.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.text import arquivo, rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtWidgets import QFileDialog

    from chess_diagram_ocr.qt import painel_de_texto as qt_texto
    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import OBJETO, PainelDeTexto


def _bloco(conteudo: str) -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas([LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), 1.0, "camada", None, None)])  # type: ignore[arg-type]


def _pagina(livro: str = "livro.pdf") -> PaginaLida:
    return PaginaLida(
        documento=livro,
        pagina=0,
        colunas=(
            Coluna(
                indice=0,
                blocos=(
                    _bloco("Antes do diagrama."),
                    BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 60.0, 60.0)),
                    _bloco("Depois do diagrama."),
                ),
            ),
        ),
    )


def _folha() -> np.ndarray:
    """Uma folha sintética de 400×400 px a 72 dpi: o bbox de (10, 10, 60, 60) pt cabe nela."""
    return np.full((400, 400, 3), 210, np.uint8)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class _Aba(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.pasta = pasta_temporaria(self)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=self.pasta / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.resize(700, 500)
        self.painel.show()
        self.app.processEvents()
        self.recados: list[str] = []
        self.painel.estado.connect(self.recados.append)

    def miniaturas(self) -> int:
        """Quantas imagens o editor desenhou: cada uma é um `OBJETO` no texto do widget."""
        return self.painel.editor.toPlainText().count(OBJETO)

    def esperar_a_tarefa(self) -> None:
        tarefa = self.painel._tarefa
        self.assertIsNotNone(tarefa, "a tarefa não partiu")
        self.assertTrue(tarefa.wait(10_000))  # type: ignore[union-attr]
        self.app.processEvents()


class LeituraEntregaAFolhaTests(_Aba):
    """`ler` rasteriza a folha uma vez, na thread, e a miniatura chega com o texto (S-352)."""

    def test_a_leitura_traz_a_miniatura_do_diagrama(self) -> None:
        self.painel.definir_livro(self.pasta / "livro.pdf", pagina=0)
        with mock.patch.object(qt_texto, "_renderizar", return_value=_folha()) as renderizar, mock.patch.object(
            qt_texto, "_ler", return_value=_pagina()
        ) as ler:
            self.painel.ler()
            self.esperar_a_tarefa()
        renderizar.assert_called_once()
        self.assertIs(ler.call_args.kwargs["imagem_rgb"], renderizar.return_value, "o leitor renderizaria de novo")
        self.assertEqual(self.miniaturas(), 1)
        self.assertIn("[Diagrama 1]", self.painel.texto())
        self.assertIsNotNone(self.painel._pagina_rgb)
        self.assertIn("1 diagrama(s)", self.recados[-1])

    def test_sem_imagem_a_folha_abre_igual_e_a_marca_fica(self) -> None:
        """A miniatura é conforto: um PDF que não renderiza não impede a leitura do texto."""
        self.painel.definir_livro(self.pasta / "livro.pdf", pagina=0)
        with mock.patch.object(qt_texto, "_renderizar", return_value=None), mock.patch.object(
            qt_texto, "_ler", return_value=_pagina()
        ):
            self.painel.ler()
            self.esperar_a_tarefa()
        self.assertEqual(self.miniaturas(), 0)
        self.assertIn("[Diagrama 1]", self.painel.texto())
        self.assertIn("[Diagrama 1]", self.painel.editor.toPlainText())


class ReabrirOArquivoTests(_Aba):
    """O `.cvtxt` guarda bbox e índice, e a miniatura se refaz do livro -- se ele estiver lá (S-238)."""

    def gravar(self, livro: Path) -> Path:
        destino = self.pasta / "folha.cvtxt"
        arquivo.gravar(destino, rico.de_pagina(_pagina(str(livro))))
        return destino

    def test_com_o_livro_no_lugar_as_miniaturas_voltam(self) -> None:
        livro = self.pasta / "livro.pdf"
        livro.write_bytes(b"%PDF-1.4 de mentira")
        destino = self.gravar(livro)
        with mock.patch.object(qt_texto, "_renderizar", return_value=_folha()) as renderizar, mock.patch.object(
            QFileDialog, "getOpenFileName", return_value=(str(destino), "")
        ):
            self.painel.abrir_documento()
        renderizar.assert_called_once_with(livro, 0, dpi=72)
        self.assertEqual(self.miniaturas(), 1)
        self.assertFalse(self.painel.tem_alteracoes)
        self.assertEqual(self.painel._caminho_do_documento, destino, "Salvar grava de volta no arquivo aberto")
        self.assertEqual(self.painel.campo_de_folha.value(), 1)
        self.assertIn("1 com miniatura", self.recados[-1])

    def test_sem_o_livro_o_texto_abre_e_o_rodape_diz_qual_falta(self) -> None:
        destino = self.gravar(self.pasta / "sumiu" / "livro.pdf")
        with mock.patch.object(qt_texto, "_renderizar") as renderizar, mock.patch.object(
            QFileDialog, "getOpenFileName", return_value=(str(destino), "")
        ):
            self.painel.abrir_documento()
        renderizar.assert_not_called()
        self.assertEqual(self.miniaturas(), 0)
        self.assertIn("[Diagrama 1]", self.painel.texto())
        self.assertIn("livro.pdf não está no lugar de antes", self.recados[-1])


class ExportacaoLevaOsRecortesTests(_Aba):
    """O `.md` da aba aponta para um PNG por diagrama, ao lado do arquivo (S-338)."""

    def exportar(self, destino: Path, metodo: str) -> None:
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            getattr(self.painel, metodo)()
        self.esperar_a_tarefa()

    def test_o_md_leva_a_imagem_do_diagrama(self) -> None:
        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        destino = self.pasta / "com_diagrama.md"
        self.exportar(destino, "exportar_md")
        self.assertIn("diagramas/com_diagrama_d1.png", destino.read_text(encoding="utf-8"))
        png = self.pasta / "diagramas" / "com_diagrama_d1.png"
        self.assertTrue(png.exists())
        from PIL import Image

        with Image.open(png) as imagem:
            self.assertEqual(imagem.size, (50, 50), "o recorte é o bbox em pontos × dpi/72")

    def test_o_html_tambem(self) -> None:
        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        destino = self.pasta / "folha.html"
        self.exportar(destino, "exportar_html")
        self.assertIn('src="diagramas/folha_d1.png"', destino.read_text(encoding="utf-8"))

    def test_sem_folha_renderizada_a_marca_sai_sozinha(self) -> None:
        """O comportamento de antes continua sendo o de quem abre um `.cvtxt` sem o livro."""
        self.painel.mostrar_pagina(_pagina())
        destino = self.pasta / "sem_folha.md"
        self.exportar(destino, "exportar_md")
        self.assertNotIn("diagramas/", destino.read_text(encoding="utf-8"))
        self.assertFalse((self.pasta / "diagramas").exists())
        self.assertIn("1 diagrama(s) sem recorte", self.recados[-1])

    def test_o_txt_nao_grava_recorte_nenhum(self) -> None:
        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        destino = self.pasta / "folha.txt"
        self.exportar(destino, "salvar")
        self.assertFalse((self.pasta / "diagramas").exists())
        self.assertIn("[Diagrama 1]", destino.read_text(encoding="utf-8"))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RecorteDaFolhaTests(unittest.TestCase):
    """A função pura que a miniatura e o PNG compartilham."""

    def test_o_bbox_em_pontos_vira_pixel_pelo_dpi(self) -> None:
        folha = np.zeros((600, 400, 3), np.uint8)
        recorte = qt_texto._recorte_da_folha(folha, BlocoDeDiagrama(indice=0, bbox=(10.0, 20.0, 30.0, 50.0)), dpi=144)
        assert recorte is not None
        self.assertEqual(recorte.shape[:2], (60, 40))

    def test_fora_da_folha_e_sem_bbox_nao_ha_recorte(self) -> None:
        folha = np.zeros((100, 100, 3), np.uint8)
        self.assertIsNone(qt_texto._recorte_da_folha(folha, BlocoDeDiagrama(indice=0, bbox=(200.0, 200.0, 300.0, 300.0)), dpi=72))
        self.assertIsNone(qt_texto._recorte_da_folha(folha, object(), dpi=72))

    def test_o_recorte_e_grampeado_na_borda(self) -> None:
        folha = np.zeros((100, 100, 3), np.uint8)
        recorte = qt_texto._recorte_da_folha(folha, BlocoDeDiagrama(indice=0, bbox=(80.0, 80.0, 300.0, 300.0)), dpi=72)
        assert recorte is not None
        self.assertEqual(recorte.shape[:2], (20, 20))


class ZoomDaVistaTests(_Aba):
    """O zoom é um degrau somado ao corpo do sistema, e ele tem de chegar à letra (S-264)."""

    def corpo_do_primeiro_trecho(self) -> int:
        cursor = QTextCursor(self.painel.editor.document())
        cursor.setPosition(1)
        return int(cursor.charFormat().fontPointSize())

    def test_aproximar_aumenta_a_letra_desenhada(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("Uma frase."))
        antes = self.corpo_do_primeiro_trecho()
        self.painel.aplicar_zoom(+3, avisar=False)
        self.assertEqual(self.corpo_do_primeiro_trecho(), antes + 3)
        self.painel.aplicar_zoom(0, avisar=False)
        self.assertEqual(self.corpo_do_primeiro_trecho(), antes, "o degrau parte da origem, não da tela")

    def test_o_digitado_sai_no_corpo_da_vista(self) -> None:
        """O trecho digitado é pintado com a base do último desenho -- com o zoom dentro."""
        from PyQt6.QtTest import QTest

        self.painel.desenhar_documento(rico.de_texto("Uma frase."))
        self.painel.aplicar_zoom(+2, avisar=False)
        corpo = self.corpo_do_primeiro_trecho()
        self.painel.editor.setFocus()
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(0)
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClicks(self.painel.editor, "x")
        self.assertEqual(self.corpo_do_primeiro_trecho(), corpo)


class MiniaturaAcompanhaOZoomTests(_Aba):
    """A miniatura cresce e encolhe com a vista, na mesma razão que a letra (S-264)."""

    def largura_da_miniatura(self) -> int:
        texto = self.painel.editor.toPlainText()
        cursor = QTextCursor(self.painel.editor.document())
        cursor.setPosition(texto.index(OBJETO) + 1)
        formato = cursor.charFormat().toImageFormat()
        self.assertTrue(formato.isValid(), "não há imagem onde o OBJETO está")
        return int(formato.width())

    def test_aproximar_alarga_a_miniatura_e_voltar_a_devolve(self) -> None:
        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        normal = self.largura_da_miniatura()
        self.assertEqual(normal, qt_texto.LARGURA_DA_MINIATURA)
        self.painel.aplicar_zoom(+4, avisar=False)
        maior = self.largura_da_miniatura()
        self.assertGreater(maior, normal)
        corpo = tema.fonte_base()[0]
        self.assertEqual(maior, round(qt_texto.LARGURA_DA_MINIATURA * (corpo + 4) / corpo))
        self.painel.aplicar_zoom(-2, avisar=False)
        self.assertLess(self.largura_da_miniatura(), normal)
        self.painel.aplicar_zoom(0, avisar=False)
        self.assertEqual(self.largura_da_miniatura(), normal)


class LexicoSobreviveAoRedesenhoTests(_Aba):
    """A conferência ligada se refaz depois de cada redesenho (S-293)."""

    def test_o_negrito_nao_apaga_as_marcas(self) -> None:
        self.painel.desenhar_documento(rico.de_texto("uma palavra xyzqk aqui"))
        self.painel.marcar_fora_do_lexico()
        self.assertTrue(self.painel.editor.extraSelections(), "nada foi marcado")
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
        self.painel.editor.setTextCursor(cursor)
        self.painel.negrito()
        self.assertTrue(self.painel.pode_desfazer, "o negrito não redesenhou")
        self.assertTrue(self.painel.editor.extraSelections(), "o redesenho apagou a marcação")
        self.painel.limpar_marcas_do_lexico()
        self.painel.desfazer()
        self.assertEqual(self.painel.editor.extraSelections(), [], "desligada, ela não volta")

    def test_a_palavra_digitada_e_conferida_na_pausa(self) -> None:
        """A tecla comum não redesenha; a conferência ligada se refaz quando a digitação para."""
        from PyQt6.QtTest import QTest

        self.painel.desenhar_documento(rico.de_texto("uma palavra aqui"))
        self.painel.marcar_fora_do_lexico()
        self.assertEqual(self.painel.editor.extraSelections(), [], "o texto de partida tem palavra desconhecida")
        self.painel.editor.setFocus()
        cursor = self.painel.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClicks(self.painel.editor, " qzxvk")
        self.assertEqual(self.painel.editor.extraSelections(), [], "a tecla não reconfere (caminho rápido)")
        self.assertTrue(self.painel._rascunho.isActive(), "a tecla não armou a pausa")
        self.painel._rascunho.timeout.emit()
        marcadas = self.painel.editor.extraSelections()
        self.assertEqual([s.cursor.selectedText() for s in marcadas], ["qzxvk"])
        self.painel.limpar_marcas_do_lexico()
        self.painel._rascunho.timeout.emit()
        self.assertEqual(self.painel.editor.extraSelections(), [], "desligada, a pausa não marca")


class FraseDoRodapeTests(unittest.TestCase):
    """A frase pura do rodapé da aba (`ui/texto_declarado.frase_do_rodape`)."""

    def test_folha_com_tudo_no_lugar(self) -> None:
        from chess_diagram_ocr.ui.texto_declarado import frase_do_rodape

        self.assertEqual(
            frase_do_rodape(folha=13, trechos=43, diagramas=3, miniaturas=3, por_gravar=False),
            "Folha 14 · 43 trecho(s) · 3 diagrama(s)",
        )

    def test_a_miniatura_que_falta_e_dita_e_o_por_gravar_tambem(self) -> None:
        from chess_diagram_ocr.ui.texto_declarado import frase_do_rodape

        self.assertEqual(
            frase_do_rodape(folha=0, trechos=5, diagramas=2, miniaturas=0, por_gravar=True),
            "Folha 1 · 5 trecho(s) · 2 diagrama(s), 0 com miniatura · por gravar",
        )

    def test_sem_texto_nao_ha_frase_e_sem_folha_ela_diz(self) -> None:
        from chess_diagram_ocr.ui.texto_declarado import frase_do_rodape

        self.assertEqual(frase_do_rodape(folha=None, trechos=0, diagramas=0, miniaturas=0, por_gravar=False), "")
        self.assertTrue(
            frase_do_rodape(folha=None, trechos=1, diagramas=0, miniaturas=0, por_gravar=False).startswith(
                "Texto sem folha de origem"
            )
        )


class RodapeDaAbaTests(_Aba):
    """O rótulo de estado da aba existia e ficava vazio desde o porte."""

    def test_o_rodape_acompanha_a_folha_a_edicao_e_a_gravacao(self) -> None:
        from PyQt6.QtTest import QTest

        self.assertEqual(self.painel.status.text(), "")
        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        trechos = len(self.painel.documento.corridas)
        self.assertEqual(self.painel.status.text(), f"Folha 1 · {trechos} trecho(s) · 1 diagrama(s)")
        self.painel.editor.setFocus()
        cursor = self.painel.editor.textCursor()
        cursor.setPosition(0)
        self.painel.editor.setTextCursor(cursor)
        QTest.keyClicks(self.painel.editor, "x")
        self.assertTrue(self.painel.status.text().endswith(" · por gravar"))
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.pasta / "f.cvtxt"), "")):
            self.painel.salvar_documento_como()
        self.assertFalse(self.painel.status.text().endswith("por gravar"))

    def test_sem_miniatura_o_rodape_diz_quantas_faltam(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.assertIn("1 diagrama(s), 0 com miniatura", self.painel.status.text())


FEN = "r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR"


class ComPosicoesTests(unittest.TestCase):
    """`PaginaLida.com_posicoes`: a FEN do OCR de diagramas entra no bloco pelo `indice`, pura."""

    def test_preenche_pelo_indice_e_devolve_a_propria_pagina_quando_nada_muda(self) -> None:
        pagina = _pagina()
        nova = pagina.com_posicoes([FEN])
        self.assertEqual(nova.diagramas[0].placement, FEN)
        self.assertEqual(nova.texto(), pagina.texto(), "só o campo de peças muda")
        self.assertIs(nova.com_posicoes([FEN]), nova)
        self.assertIs(pagina.com_posicoes([]), pagina)
        self.assertIs(pagina.com_posicoes([""]), pagina, "não lido não apaga nem muda")

    def test_o_vazio_nao_apaga_o_que_o_bloco_ja_tinha(self) -> None:
        com = _pagina().com_posicoes([FEN])
        self.assertEqual(com.com_posicoes([""]).diagramas[0].placement, FEN)

    def test_sobrevive_ao_arquivo(self) -> None:
        pagina = _pagina().com_posicoes([FEN])
        volta = PaginaLida.de_json(pagina.para_json())
        self.assertEqual(volta.diagramas[0].placement, FEN)


class PosicoesDoProdutoTests(_Aba):
    """`definir_posicoes`: a leitura dos diagramas e a do texto chegam em qualquer ordem."""

    def test_a_posicao_que_chega_depois_entra_na_folha_sem_virar_alteracao(self) -> None:
        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        self.painel.definir_posicoes(0, [FEN])
        assert self.painel._pagina is not None
        self.assertEqual(self.painel._pagina.diagramas[0].placement, FEN)
        self.assertEqual(self.painel.documento.bloco_de(self.painel.documento.diagramas[0]).placement, FEN)
        self.assertFalse(self.painel.tem_alteracoes, "a posição é leitura, não edição")
        self.assertEqual(self.miniaturas(), 1, "o redesenho manteve a miniatura")

    def test_a_posicao_que_chega_antes_espera_a_folha(self) -> None:
        self.painel.definir_posicoes(0, [FEN])
        self.painel.definir_posicoes(3, ["8/8/8/8/8/8/8/K6k"])
        self.painel.mostrar_pagina(_pagina())
        assert self.painel._pagina is not None
        self.assertEqual(self.painel._pagina.diagramas[0].placement, FEN, "a folha 1 pega a posição da folha 1")

    def test_outra_folha_nao_mexe_na_que_esta_na_tela(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.painel.definir_posicoes(5, [FEN])
        assert self.painel._pagina is not None
        self.assertEqual(self.painel._pagina.diagramas[0].placement, "")

    def test_a_fen_vai_para_o_cvtxt_e_para_o_md(self) -> None:
        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        self.painel.definir_posicoes(0, [FEN])
        destino = self.pasta / "folha.cvtxt"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            self.painel.salvar_documento_como()
        gravado = arquivo.carregar(destino)
        assert gravado.origem is not None
        self.assertEqual(gravado.origem.diagramas[0].placement, FEN)
        md = self.pasta / "folha.md"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(md), "")):
            self.painel.exportar_md()
        self.esperar_a_tarefa()
        self.assertIn(f"<!-- FEN: {FEN} -->", md.read_text(encoding="utf-8"))


class DesenhadaDaPosicaoTests(_Aba):
    """Sem folha, a miniatura e o recorte exportado nascem da posição lida (item 7)."""

    def test_sem_folha_a_miniatura_e_desenhada_da_fen(self) -> None:
        self.painel.mostrar_pagina(_pagina().com_posicoes([FEN]))
        self.assertEqual(self.miniaturas(), 1)
        self.assertNotIn("com miniatura", self.painel.status.text(), "o rodapé não conta falta nenhuma")

    def test_a_posicao_que_chega_depois_desenha_a_miniatura_que_faltava(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.assertEqual(self.miniaturas(), 0)
        self.painel.definir_posicoes(0, [FEN])
        self.assertEqual(self.miniaturas(), 1)

    def test_o_recorte_da_folha_vem_primeiro(self) -> None:
        self.painel.mostrar_pagina(_pagina().com_posicoes([FEN]), folha_rgb=_folha())
        with mock.patch.object(qt_texto, "_png_da_posicao") as desenhar:
            self.painel.aplicar_zoom(+1, avisar=False)
        desenhar.assert_not_called()
        self.assertEqual(self.miniaturas(), 1)

    def test_o_md_sem_folha_leva_o_diagrama_desenhado(self) -> None:
        self.painel.mostrar_pagina(_pagina().com_posicoes([FEN]))
        destino = self.pasta / "desenhado.md"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            self.painel.exportar_md()
        self.esperar_a_tarefa()
        conteudo = destino.read_text(encoding="utf-8")
        self.assertIn("diagramas/desenhado_d1.png", conteudo)
        self.assertIn(f"<!-- FEN: {FEN} -->", conteudo)
        png = self.pasta / "diagramas" / "desenhado_d1.png"
        self.assertTrue(png.exists())
        from PIL import Image

        with Image.open(png) as imagem:
            self.assertEqual(imagem.size, (qt_texto.LADO_DO_RECORTE_DESENHADO, qt_texto.LADO_DO_RECORTE_DESENHADO))
        self.assertNotIn("sem recorte", self.recados[-1])

    def test_sem_folha_e_sem_posicao_continua_sem_figura(self) -> None:
        self.painel.mostrar_pagina(_pagina())
        self.assertEqual(self.miniaturas(), 0)
        self.assertIsNone(qt_texto._png_da_posicao("", lado_px=100))


class CliqueNaMiniaturaTests(_Aba):
    """O clique na miniatura seleciona a marca; o duplo clique pede o diagrama na sala (item 8)."""

    def ponto_da_miniatura(self) -> object:
        from PyQt6.QtCore import QPoint

        texto = self.painel.editor.toPlainText()
        cursor = QTextCursor(self.painel.editor.document())
        cursor.setPosition(texto.index(OBJETO))
        caixa = self.painel.editor.cursorRect(cursor)
        return QPoint(caixa.left() + 12, caixa.top() + 12)

    def test_o_clique_seleciona_a_marca_do_diagrama(self) -> None:
        from PyQt6.QtTest import QTest

        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        QTest.mouseClick(self.painel.editor.viewport(), Qt.MouseButton.LeftButton, pos=self.ponto_da_miniatura())
        self.assertEqual(self.painel.editor.textCursor().selectedText(), "[Diagrama 1]")
        self.assertEqual(self.painel._selecao_atual(), (self.painel.texto().index("[Diagrama 1]"), self.painel.texto().index("]") + 1))

    def test_o_clique_fora_da_miniatura_e_do_editor(self) -> None:
        from PyQt6.QtCore import QPoint
        from PyQt6.QtTest import QTest

        self.painel.mostrar_pagina(_pagina(), folha_rgb=_folha())
        QTest.mouseClick(self.painel.editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
        self.assertEqual(self.painel.editor.textCursor().selectedText(), "")
        self.assertIsNone(self.painel._marca_sob(QPoint(4, 4)))

    def test_o_duplo_clique_pede_o_diagrama_na_sala(self) -> None:
        from PyQt6.QtTest import QTest

        self.painel.mostrar_pagina(_pagina(livro="livro.pdf"), folha_rgb=_folha())
        pedidos: list[tuple[int, int]] = []
        self.painel.diagrama_ativado.connect(lambda folha, indice: pedidos.append((folha, indice)))
        QTest.mouseDClick(self.painel.editor.viewport(), Qt.MouseButton.LeftButton, pos=self.ponto_da_miniatura())
        self.assertEqual(pedidos, [(0, 0)])


class ConfiguracoesDaLeituraTests(unittest.TestCase):
    """A leitura da aba pergunta o DPI e o teto de diagramas às Configurações, como o visualizador.

    Antes o painel nascia com `dpi=220` cravado e lia sem teto: a aba Livro e a aba Texto
    discordavam sobre a escala da folha e sobre quantos diagramas há na página, e a janela
    «Ferramentas ▸ Configurações…» não alcançava esta aba.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        tema.aplicar_tema(self.app)
        self.pasta = pasta_temporaria(self)
        self.recados: list[str] = []

    def painel(self, **argumentos: object) -> PainelDeTexto:
        painel = PainelDeTexto(pasta_de_rascunhos=self.pasta / "rascunhos", **argumentos)  # type: ignore[arg-type]
        self.addCleanup(descartar, painel)
        painel.show()
        self.app.processEvents()
        return painel

    def ler(self, painel: PainelDeTexto) -> tuple[mock.MagicMock, mock.MagicMock]:
        from chess_diagram_ocr.ui import configuracoes

        painel.definir_livro(self.pasta / "livro.pdf", pagina=0)
        with mock.patch.object(configuracoes, "dpi", return_value=150), mock.patch.object(
            configuracoes, "max_boards", return_value=2
        ), mock.patch.object(qt_texto, "_renderizar", return_value=_folha()) as renderizar, mock.patch.object(
            qt_texto, "_ler", return_value=_pagina()
        ) as ler:
            painel.ler()
            tarefa = painel._tarefa
            assert tarefa is not None
            self.assertTrue(tarefa.wait(10_000))
            self.app.processEvents()
        return renderizar, ler

    def test_o_produto_le_com_o_dpi_e_o_teto_das_configuracoes(self) -> None:
        painel = self.painel()
        renderizar, ler = self.ler(painel)
        self.assertEqual(renderizar.call_args.kwargs["dpi"], 150)
        self.assertEqual(ler.call_args.kwargs["dpi"], 150)
        self.assertEqual(ler.call_args.kwargs["max_boards"], 2)
        self.assertEqual(painel._dpi, 150, "o DPI da folha na tela é o da leitura")

    def test_o_dpi_cravado_pelo_teste_vence_e_nao_poe_teto(self) -> None:
        painel = self.painel(dpi=72)
        renderizar, ler = self.ler(painel)
        self.assertEqual(renderizar.call_args.kwargs["dpi"], 72)
        self.assertIsNone(ler.call_args.kwargs["max_boards"])
        self.assertEqual(painel._dpi, 72)

    def test_a_folha_na_tela_guarda_o_dpi_com_que_foi_renderizada(self) -> None:
        """A configuração muda depois da leitura: o recorte continua na escala da folha."""
        from chess_diagram_ocr.ui import configuracoes

        painel = self.painel()
        self.ler(painel)
        with mock.patch.object(configuracoes, "dpi", return_value=300):
            self.assertEqual(painel._dpi, 150)
            self.assertEqual(painel._dpi_para_ler(), 300)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
