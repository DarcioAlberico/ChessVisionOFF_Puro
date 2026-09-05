"""O estudo em PDF e na prévia de impressão (S-545): página, vetor e texto selecionável.

A paginação é pura e já é afirmada em `tests/test_impressao_do_estudo.py`. O que só existe aqui é
o que o `QPainter` produz: quantas páginas o dispositivo recebeu, se o diagrama saiu como caminho
ou como imagem amostrada, e se o texto do PDF é **texto**. O leitor é o PyMuPDF, que o projeto já
usa para abrir os livros -- ler o próprio artefato com a mesma biblioteca com que se lê um livro
de xadrez é o que impede a guarda de acreditar no desenho que ela mesma fez.

**A fonte é instalada pelo teste.** Sob `offscreen` o Qt não acha família nenhuma
(`QFontDatabase.families()` devolve lista vazia), e um PDF desenhado ali sai sem uma letra --
medido em 2026-09-05: zero caracteres extraídos. Não é defeito do produto, que roda numa máquina
com fontes; é o ambiente da suíte. `_familia_de_teste` registra uma `.ttf` do ambiente como fonte
de aplicação e a devolve; sem nenhuma candidata, o caso **pula com o motivo escrito** (S-417).
"""

from __future__ import annotations

import unittest
from pathlib import Path

import chess
import chess.pgn
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo
from chess_diagram_ocr.ui.impressao_do_estudo import MARGEM_MM

if TEM_PYQT:
    from PyQt6.QtGui import QFont, QFontDatabase
    from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog

    from chess_diagram_ocr.qt import painel_de_estudo as qt_estudo
    from chess_diagram_ocr.qt.impressao_do_estudo import FolhaDoEstudo, abrir_previa_de_impressao, pdf_do_estudo

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"

SEM_FONTE = "o ambiente não tem nenhuma .ttf para registrar, e sob offscreen o Qt não traz fonte"


def _candidatas() -> list[Path]:
    """Onde procurar uma `.ttf` -- a do matplotlib do ambiente primeiro, depois as do sistema."""
    achadas: list[Path] = []
    try:
        import matplotlib

        achadas.append(Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf" / "DejaVuSans.ttf")
    except Exception:  # noqa: BLE001 - o matplotlib é opcional; a busca segue no sistema
        pass
    achadas.extend(Path(pasta) / nome for pasta in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu")
                   for nome in ("DejaVuSans.ttf", "arial.ttf"))
    return [caminho for caminho in achadas if caminho.is_file()]


def _familia_de_teste(caso: unittest.TestCase) -> str:
    """Uma família de fonte utilizável nesta sessão, registrada e desfeita no fim do teste."""
    if QFontDatabase.families():
        return QFontDatabase.families()[0]
    for caminho in _candidatas():
        identificador = QFontDatabase.addApplicationFont(str(caminho))
        familias = QFontDatabase.applicationFontFamilies(identificador) if identificador >= 0 else []
        if familias:
            # Desfeito no fim: a `QApplication` é do processo inteiro, e uma fonte deixada
            # registrada mudaria a métrica dos testes de layout que vierem depois.
            caso.addCleanup(QFontDatabase.removeApplicationFont, identificador)
            return str(familias[0])
    raise unittest.SkipTest(SEM_FONTE)


def _estudo(*, lances: int = 0, a_cada: int = 0, ancora: Ancora = Ancora()) -> Estudo:
    estudo = Estudo.de_posicao(PosicaoDeEstudo(placement=INICIAL, vez="w", ancora=ancora))
    tabuleiro = chess.Board()
    for numero in range(lances):
        lance = list(tabuleiro.legal_moves)[numero % 4]
        estudo.no = estudo.no.add_main_variation(lance)
        tabuleiro.push(lance)
        if a_cada and (numero + 1) % a_cada == 0:
            estudo.no.comment = (
                "Uma observacao do autor sobre esta posicao, longa o bastante para ocupar mais "
                "de uma linha da coluna impressa. [%D]"
            )
    estudo.jogo.headers["White"] = "Carlsen, M."
    estudo.jogo.headers["Black"] = "Nepomniachtchi, I."
    estudo.jogo.headers["Event"] = "Tata Steel"
    return estudo


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PdfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.familia = _familia_de_teste(self)
        # O desenho usa a fonte do `QPainter`, que é a de fábrica da aplicação: apontá-la para a
        # família registrada é o que faz o glifo existir nesta sessão.
        anterior = self.app.font()
        self.app.setFont(QFont(self.familia, 10))
        self.addCleanup(self.app.setFont, anterior)

    def _pdf(self, estudo: Estudo, nome: str = "estudo.pdf") -> tuple[Path, int]:
        alvo = self.pasta / nome
        return alvo, pdf_do_estudo(estudo, alvo)

    def _aberto(self, caminho: Path):  # noqa: ANN202 - `fitz.Document`, sem importá-lo no topo
        import fitz

        documento = fitz.open(caminho)
        self.addCleanup(documento.close)
        return documento

    def test_o_arquivo_sai_com_as_paginas_que_a_funcao_declara(self) -> None:
        alvo, paginas = self._pdf(_estudo(lances=40, a_cada=20))
        self.assertGreaterEqual(paginas, 1)
        self.assertTrue(alvo.is_file())
        self.assertEqual(paginas, self._aberto(alvo).page_count)

    def test_o_texto_do_pdf_e_texto_e_nao_desenho_de_texto(self) -> None:
        """Selecionar, copiar e procurar dentro do arquivo: é o que separa este PDF de uma
        digitalização. Cada linha sai por `QTextLine.draw`, que escreve operador de texto."""
        alvo, _paginas = self._pdf(_estudo(lances=20, a_cada=10))
        documento = self._aberto(alvo)
        todo = "".join(documento[indice].get_text() for indice in range(documento.page_count))
        self.assertIn("Carlsen", todo, "o título do capítulo não é selecionável")
        self.assertIn("Nepomniachtchi", todo)
        self.assertGreater(len(todo.strip()), 200, "o PDF saiu quase sem texto")

    def test_o_diagrama_e_vetor_e_nao_bitmap(self) -> None:
        """`QSvgRenderer.render` emite caminho no PDF: ampliar a 800% continua mostrando a borda
        da casa reta, e o arquivo não carrega uma imagem amostrada por diagrama."""
        alvo, _paginas = self._pdf(_estudo())
        documento = self._aberto(alvo)
        self.assertEqual(0, len(documento[0].get_images(full=True)), "o diagrama entrou como imagem")
        self.assertGreater(len(documento[0].get_drawings()), 64, "menos caminhos que casas do damero")

    def test_o_cabecalho_repete_o_titulo_da_segunda_pagina_em_diante(self) -> None:
        """Na primeira ele não sai: o título está no corpo, dois centímetros abaixo."""
        alvo, paginas = self._pdf(_estudo(lances=200, a_cada=50))
        self.assertGreater(paginas, 1, "o estudo de teste coube numa página só")
        documento = self._aberto(alvo)
        primeira = documento[0].get_text().strip().splitlines()
        segunda = documento[1].get_text().strip().splitlines()
        self.assertIn("Carlsen", segunda[0], "a linha de topo da página 2 não traz o capítulo")
        self.assertNotIn("Carlsen", primeira[0], "a página 1 repetiu o título na linha de topo")

    def test_toda_pagina_traz_o_numero_e_o_total(self) -> None:
        alvo, paginas = self._pdf(_estudo(lances=200, a_cada=50))
        documento = self._aberto(alvo)
        for indice in range(paginas):
            with self.subTest(pagina=indice + 1):
                self.assertIn(f"{indice + 1} de {paginas}", documento[indice].get_text())

    def test_a_margem_da_folha_e_a_declarada(self) -> None:
        """A margem é da decisão pura, e o `QPdfWriter` a recebe em milímetro."""
        alvo, _paginas = self._pdf(_estudo())
        pagina = self._aberto(alvo)[0]
        # 1 mm = 72/25.4 pontos do PDF; a caixa de tudo o que foi desenhado não invade a margem.
        margem_pt = MARGEM_MM * 72.0 / 25.4
        desenhado = pagina.get_drawings()
        esquerda = min(caminho["rect"].x0 for caminho in desenhado)
        self.assertGreaterEqual(esquerda, margem_pt - 1.0, "o desenho entrou na margem")

    def test_um_estudo_sem_lance_ainda_vira_uma_folha(self) -> None:
        alvo, paginas = self._pdf(_estudo(), "vazio.pdf")
        self.assertEqual(1, paginas)
        self.assertEqual(1, self._aberto(alvo).page_count)

    def test_a_tinta_da_folha_nao_segue_a_pele_da_janela(self) -> None:
        """**A fronteira da S-224 aplicada ao papel**: o cromo escurece, a folha não.

        Sem o carimbo de cor em cada trecho, o título e o número da página saíam com a cor de
        texto da paleta -- medido em 2026-09-05 na pele Foco: `#e9eaec`, cinza claro sobre papel
        branco, e justamente na pré-visualização, que é a tela em que se confere a folha antes de
        gastar impressão. O corpo não tinha o defeito, e é o que faz o defeito passar despercebido.
        """
        from chess_diagram_ocr.qt import tema

        anterior = tema.cromo_escuro_em_vigor()
        self.addCleanup(tema.aplicar_tema, self.app, cromo_escuro=anterior)
        for cromo_escuro in (False, True):
            with self.subTest(cromo_escuro=cromo_escuro):
                tema.aplicar_tema(self.app, cromo_escuro=cromo_escuro)
                alvo, _paginas = self._pdf(_estudo(lances=30), f"tinta_{cromo_escuro}.pdf")
                documento = self._aberto(alvo)
                escritos = [
                    (trecho["text"], trecho["color"])
                    for pagina in range(documento.page_count)
                    for bloco in documento[pagina].get_text("dict")["blocks"]
                    for linha in bloco.get("lines", [])
                    for trecho in linha["spans"]
                    if "Carlsen" in trecho["text"] or " de " in trecho["text"]
                ]
                self.assertTrue(escritos, "nem o título nem o rodapé saíram na folha")
                for texto, cor in escritos:
                    self.assertEqual(0, cor, f"{texto!r} saiu com a tinta do cromo, e não a do papel")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PreviaTests(unittest.TestCase):
    """A prévia desenha **a mesma folha**, e é o critério: prévia e PDF não são dois desenhos."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.familia = _familia_de_teste(self)
        anterior = self.app.font()
        self.app.setFont(QFont(self.familia, 10))
        self.addCleanup(self.app.setFont, anterior)

    def test_a_previa_pinta_a_folha_quando_pedem_tinta(self) -> None:
        """**Afirma o efeito e não o `connect`**: trocar o método depois de ligado não troca quem
        o sinal chama, então o que se mede é a folha ter páginas depois de o sinal passar.

        O sinal é emitido aqui em vez de vir do `QPrintPreviewWidget`: sob `offscreen` o
        `updatePreview()` dele derruba o processo com violação de acesso (medido em 2026-09-05),
        porque a vista não tem superfície onde desenhar. O que a guarda tem a provar é que
        `paintRequested` chega à folha -- e o caminho do sinal é o mesmo pelos dois lados.
        """
        dialogo = abrir_previa_de_impressao(None, _estudo(lances=20, a_cada=10), mostrar=False)
        self.addCleanup(descartar, dialogo)
        folha = dialogo.folha
        self.assertEqual((), folha.paginas, "a folha desenhou antes de alguém pedir")
        impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
        impressora.setOutputFileName(str(self.pasta / "da_previa.pdf"))
        dialogo.paintRequested.emit(impressora)
        self.assertGreaterEqual(len(folha.paginas), 1, "o `paintRequested` não chegou à folha")

    def test_a_folha_da_previa_e_a_do_pdf(self) -> None:
        """Duas implementações dariam duas paginações, e a que ninguém confere é a que sai errada.
        Aqui a mesma `FolhaDoEstudo` recebe os dois dispositivos e conta os mesmos blocos."""
        estudo = _estudo(lances=60, a_cada=20)
        folha = FolhaDoEstudo(estudo)
        impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
        impressora.setOutputFileName(str(self.pasta / "pela_impressora.pdf"))
        pela_impressora = folha.desenhar(impressora)
        self.assertGreaterEqual(pela_impressora, 1)
        self.assertEqual(pela_impressora, len(folha.paginas))
        self.assertEqual(len(folha.blocos), len(FolhaDoEstudo(estudo).blocos))

    def test_o_titulo_da_folha_e_o_do_capitulo(self) -> None:
        """A linha de topo e a abertura do capítulo dizem o mesmo nome, e o nome é o de
        `estudo_paragrafos.titulo_do_estudo` -- não um segundo."""
        from chess_diagram_ocr.estudo_paragrafos import titulo_do_estudo

        estudo = _estudo(ancora=Ancora(documento="C:/PDF/Secrets.pdf", pagina=142, diagrama=1))
        self.assertEqual(titulo_do_estudo(estudo), FolhaDoEstudo(estudo).titulo)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class AcaoDaSalaTests(unittest.TestCase):
    """As duas ações de menu, afirmadas pelo efeito."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.familia = _familia_de_teste(self)
        anterior = self.app.font()
        self.app.setFont(QFont(self.familia, 10))
        self.addCleanup(self.app.setFont, anterior)
        self.painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, self.painel)

    def test_exportar_para_pdf_grava_o_arquivo_escolhido_e_diz_onde(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        alvo = self.pasta / "da acao.pdf"
        original = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *_a, **_k: (str(alvo), ""))  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(QFileDialog, "getSaveFileName", original))
        self.painel.exportar_estudo_pdf()
        self.assertTrue(alvo.is_file())
        self.assertIn(str(alvo), self.painel.lbl_status.text())
        self.assertIn("página(s)", self.painel.lbl_status.text())

    def test_desistir_do_dialogo_nao_grava_nada(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        original = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *_a, **_k: ("", ""))  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(QFileDialog, "getSaveFileName", original))
        self.painel.exportar_estudo_pdf()
        self.assertEqual([], list(self.pasta.glob("*.pdf")))

    def test_imprimir_abre_a_previa_com_a_folha_deste_estudo(self) -> None:
        """O `exec()` é fingido: sob `offscreen` a prévia **abre** e espera para sempre por um
        clique que ninguém vai dar -- é o mesmo modo de falha que o `conftest` desarma para o
        `QMessageBox`, e a razão de o método de produção mostrar a janela de verdade."""
        abertas: list[QPrintPreviewDialog] = []
        original = QPrintPreviewDialog.exec
        QPrintPreviewDialog.exec = lambda janela: abertas.append(janela) or 0  # type: ignore[method-assign]
        self.addCleanup(lambda: setattr(QPrintPreviewDialog, "exec", original))

        self.painel.push_move(chess.Move.from_uci("e2e4"))
        dialogo = self.painel.imprimir_estudo()
        self.addCleanup(descartar, dialogo)
        self.assertIsInstance(dialogo, QPrintPreviewDialog)
        self.assertEqual([dialogo], abertas, "a prévia não foi mostrada")
        self.assertEqual(self.painel.estudo, dialogo.folha.estudo)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
