"""Abertura de documento e o critério de aceite da S-61: uma por página, não três.

O teste que carrega o item é `test_uma_abertura_por_pagina_e_nao_tres`. Ele usa um PDF de
verdade (sintético, três páginas) porque o que se mede é justamente o que os *mocks* dos
outros testes escondem: quantas vezes o `fitz` abre o arquivo.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import pdf_io
from chess_diagram_ocr.pdf_io import OpenPdf, get_pdf_page_count, open_document, opened, render_pdf_page
from chess_diagram_ocr.pdf_to_pgn import scan_pdf_positions
from chess_diagram_ocr.ui import leitura_do_pdf

EMPTY_BOARD = "8/8/8/8/8/8/8/8"


def _pdf(path: Path, pages: int = 3) -> Path:
    doc = fitz.open()
    for numero in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Diagrama {numero + 1}", fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


class BorrowingTests(unittest.TestCase):
    def test_um_openpdf_e_emprestado_e_nao_fechado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _pdf(Path(tmp) / "livro.pdf")
            with opened(caminho) as documento:
                antes = pdf_io.open_count()
                with open_document(documento) as doc:
                    self.assertEqual(doc.page_count, 3)
                # Nenhuma abertura nova, e o documento continua utilizavel depois do `with`.
                self.assertEqual(pdf_io.open_count(), antes)
                self.assertEqual(documento.page_count, 3)
                self.assertIsNotNone(documento.page(0))

    def test_opened_e_reentrante(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _pdf(Path(tmp) / "livro.pdf")
            with opened(caminho) as primeiro:
                antes = pdf_io.open_count()
                with opened(primeiro) as segundo:
                    self.assertIs(segundo, primeiro)
                self.assertEqual(pdf_io.open_count(), antes)
                # E o `with` interno nao fechou o documento do externo.
                self.assertEqual(primeiro.page_count, 3)

    def test_as_funcoes_por_caminho_aceitam_o_documento_aberto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _pdf(Path(tmp) / "livro.pdf")
            por_caminho = render_pdf_page(caminho, 0, dpi=72)
            with opened(caminho) as documento:
                por_documento = render_pdf_page(documento, 0, dpi=72)
                self.assertEqual(get_pdf_page_count(documento), 3)

            self.assertTrue(np.array_equal(por_caminho, por_documento))

    def test_um_caminho_continua_sendo_aberto_e_fechado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _pdf(Path(tmp) / "livro.pdf", pages=1)
            antes = pdf_io.open_count()
            self.assertEqual(get_pdf_page_count(caminho), 1)
            self.assertEqual(pdf_io.open_count(), antes + 1)


class ScanOpenCountTests(unittest.TestCase):
    """O critério de aceite da S-61, escrito como teste."""

    @patch("chess_diagram_ocr.pdf_to_pgn.predict_with_orientation")
    @patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams")
    @patch("chess_diagram_ocr.pdf_to_pgn.load_model")
    def test_uma_abertura_por_pagina_e_nao_tres(self, mock_load, mock_detect, mock_predict) -> None:
        from test_pdf_to_pgn import candidate_for, oriented_for

        mock_load.return_value = ("model", "cpu")
        board = np.zeros((800, 800, 3), dtype=np.uint8)
        mock_detect.side_effect = lambda *a, **k: [candidate_for(board, 0)]
        mock_predict.side_effect = lambda *a, **k: oriented_for(EMPTY_BOARD, 0.9)

        with tempfile.TemporaryDirectory() as tmp:
            caminho = _pdf(Path(tmp) / "livro.pdf", pages=3)
            antes = pdf_io.open_count()
            posicoes = scan_pdf_positions(caminho)
            aberturas = pdf_io.open_count() - antes

        self.assertEqual(len(posicoes), 3, "as três páginas foram varridas")
        # Uma para a varredura inteira. Antes da S-61 eram tres por pagina -- render,
        # deteccao e camada de texto --, mais a contagem de paginas: dez para estas tres.
        self.assertEqual(aberturas, 1)

    @patch("chess_diagram_ocr.pdf_to_pgn.predict_with_orientation")
    @patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams")
    @patch("chess_diagram_ocr.pdf_to_pgn.load_model")
    def test_a_varredura_le_o_mesmo_com_documento_emprestado(self, mock_load, mock_detect, mock_predict) -> None:
        """Nenhuma mudança de resultado é a outra metade do critério de aceite."""
        from test_pdf_to_pgn import candidate_for, oriented_for

        mock_load.return_value = ("model", "cpu")
        board = np.zeros((800, 800, 3), dtype=np.uint8)
        mock_detect.side_effect = lambda *a, **k: [candidate_for(board, 0)]
        mock_predict.side_effect = lambda *a, **k: oriented_for(EMPTY_BOARD, 0.9)

        with tempfile.TemporaryDirectory() as tmp:
            caminho = _pdf(Path(tmp) / "livro.pdf", pages=2)
            por_caminho = scan_pdf_positions(caminho)
            with opened(caminho) as documento:
                por_documento = scan_pdf_positions(documento)

        self.assertEqual(
            [(p.page_index, p.diagram_index, p.fen) for p in por_caminho],
            [(p.page_index, p.diagram_index, p.fen) for p in por_documento],
        )

    def test_o_tipo_do_emprestimo_e_o_que_impede_o_fechamento_acidental(self) -> None:
        # Sem `OpenPdf`, um `with fitz.open(...)` no meio do pipeline fecharia o documento da
        # varredura inteira -- e o sintoma apareceria na pagina seguinte, longe da causa.
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _pdf(Path(tmp) / "livro.pdf", pages=1)
            with opened(caminho) as documento:
                self.assertIsInstance(documento, OpenPdf)
                self.assertEqual(documento.source, caminho)


class FraseDeAberturaTests(unittest.TestCase):
    """Por que o livro não abriu, em pt-BR (S-528, segunda rodada).

    **O defeito medido pelo crítico em 2026-09-05**: um PDF truncado abria a caixa "Falha ao abrir
    X.pdf" com o texto da biblioteca embaixo -- `Failed to open file 'C:\\Users\\AMD\\...'`, em
    inglês, com o caminho escapado duas vezes e repetindo o nome que a primeira linha já dava. Um
    arquivo vazio dizia `Cannot open empty file`.

    Pura de propósito: as cinco frases são afirmáveis sem um PDF corrompido em disco -- e o caso de
    baixo, que usa arquivos de verdade, é o que confere que as pistas são as que o PyMuPDF escreve.
    """

    def test_as_cinco_causas_saem_em_portugues_e_nomeiam_o_arquivo(self) -> None:
        casos = {
            "Cannot open empty file": leitura_do_pdf.SEM_CONTEUDO,
            "no such file: 'x'": "não foi encontrado",
            "Permission denied": "negou a permissão",
            "Is a directory": "é uma pasta",
            "Failed to open file 'C:\\Users\\AMD\\livro.pdf'": "corrompido",
        }
        for bruta, pedaco in casos.items():
            with self.subTest(erro=bruta):
                frase = leitura_do_pdf.frase_de_abertura("livro.pdf", RuntimeError(bruta))
                self.assertTrue(frase.startswith("livro.pdf "), frase)
                self.assertIn(pedaco, frase)
                self.assertNotIn("C:\\Users", frase, "o caminho escapado voltou para a tela")

    def test_causa_desconhecida_diz_o_tipo_e_nao_some(self) -> None:
        """Uma frase genérica ainda é melhor que a da biblioteca, e o tipo é o que se pesquisa."""
        frase = leitura_do_pdf.frase_de_abertura("livro.pdf", ZeroDivisionError("x"))
        self.assertIn("ZeroDivisionError", frase)
        self.assertTrue(frase.startswith("livro.pdf "))

    def test_a_recusa_que_ja_e_nossa_passa_intacta(self) -> None:
        """O PDF protegido por senha (S-331): `pdf_io` já escreve a frase em pt-BR, com o que
        fazer a respeito. Reescrevê-la aqui trocaria uma instrução por uma categoria."""
        nossa = "livro.pdf está protegido por senha. Este programa não tem onde pedi-la: …"
        self.assertEqual(nossa, leitura_do_pdf.frase_de_abertura("livro.pdf", ValueError(nossa)))

    def test_o_que_o_pymupdf_de_verdade_levanta_cai_nas_pistas(self) -> None:
        """**A ponte com a biblioteca**, e é ela que envelhece: os nomes de exceção do PyMuPDF
        mudam entre versões, e o que não muda é a frase que ele escreve."""
        pasta = pasta_temporaria(self)
        (pasta / "vazio.pdf").write_bytes(b"")
        (pasta / "lixo.pdf").write_bytes(b"nao sou um pdf" * 40)
        esperado = {"vazio.pdf": leitura_do_pdf.SEM_CONTEUDO, "lixo.pdf": "corrompido"}
        for nome, pedaco in esperado.items():
            with self.subTest(arquivo=nome):
                with self.assertRaises(Exception) as caixa:  # noqa: B017 - o tipo é da biblioteca
                    get_pdf_page_count(pasta / nome)
                self.assertIn(pedaco, leitura_do_pdf.frase_de_abertura(nome, caixa.exception))


if __name__ == "__main__":
    unittest.main()
