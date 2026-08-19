"""A varredura da Galeria diz até onde foi, e retoma de lá (S-120).

`build_gallery_index` acumulava tudo em memória e só devolvia no fim. Uma queda ou um
fechamento de janela perdia a varredura do livro -- 6 min no `1001`, ~14 min no Yusupov, ~3,5 h
para revarrer os 34 PDFs.

**Pior que o tempo:** o índice truncado era **indistinguível de um completo**. Ele alimenta em
silêncio a busca por posição, o censo e a fila -- todos concluindo que o livro tem menos
diagramas do que tem.

Nada aqui abre PDF: o que se testa é a contabilidade da faixa varrida e a retomada, e as duas
são estruturas. O gerador de diagramas entra como duplo, com a mesma assinatura de
`iter_pdf_diagrams` -- inclusive o progresso emitido **depois** de cada página, que é o que
torna `last_page_done` confiável.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from chess_diagram_ocr import gallery_scan
from chess_diagram_ocr.cli import scan as cli_scan
from chess_diagram_ocr.gallery_scan import GalleryEntry, GalleryIndex, build_gallery_index

LEGAL = "4k3/8/8/8/8/8/8/4K3"


class _Posicao:
    def __init__(self, page_index: int, diagram_index: int) -> None:
        self.page_index = page_index
        self.diagram_index = diagram_index
        self.fen = LEGAL
        self.side_to_move = None
        self.min_confidence = 0.9
        self.is_legal = True
        self.context = None


class _Lido:
    def __init__(self, page_index: int, diagram_index: int) -> None:
        self.position = _Posicao(page_index, diagram_index)
        self.board_rgb = np.zeros((8, 8, 3), dtype=np.uint8)


def _gerador(paginas: int, *, para_em: int | None = None):
    """Um `iter_pdf_diagrams` de mentira: um diagrama por página, progresso ao fim de cada uma.

    `para_em` simula o cancelamento -- `iter_pdf_diagrams` confere o `cancel_event` **entre**
    páginas, e é essa granularidade que faz `last_page_done` significar "terminada".
    """

    def _iter(_pdf, _model, *, start_page=0, end_page=None, progress_callback=None, cancel_event=None, **_kwargs):  # noqa: ANN001, ANN002, ANN003
        ultimo = paginas - 1 if end_page is None else min(end_page, paginas - 1)
        for pagina in range(start_page, ultimo + 1):
            if cancel_event is not None and cancel_event.is_set():
                return
            if para_em is not None and pagina > para_em:
                return
            yield _Lido(pagina, 1)
            if progress_callback is not None:
                progress_callback(pagina, paginas, 1, 1)

    return _iter


class FaixaVarridaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        remendo = mock.patch.object(gallery_scan, "cache_board_image", lambda *_a, **_k: self.raiz / "b.png")
        remendo.start()
        self.addCleanup(remendo.stop)

    def _varre(self, paginas: int, **kwargs):  # noqa: ANN003
        para_em = kwargs.pop("para_em", None)
        with mock.patch.object(gallery_scan, "iter_pdf_diagrams", _gerador(paginas, para_em=para_em)):
            return build_gallery_index(self.raiz / "livro.pdf", cache_dir=self.raiz, now="2026-08-17", **kwargs)

    def test_varredura_inteira_e_completa(self) -> None:
        indice = self._varre(5)
        self.assertTrue(indice.complete)
        self.assertEqual(indice.start_page, 0)
        self.assertEqual(indice.last_page_done, 4)
        self.assertEqual(len(indice), 5)

    def test_cancelar_no_meio_grava_parcial_com_a_pagina_certa(self) -> None:
        """**O critério de aceite.** `complete=False` e `last_page_done` na última terminada --
        e não na que estava em curso, senão retomar pularia diagramas."""
        cancelar = threading.Event()

        def _cancela_depois_de_duas(page_index: int, *_args: object) -> None:
            if page_index >= 2:
                cancelar.set()

        indice = self._varre(10, cancel_event=cancelar, progress_callback=_cancela_depois_de_duas)

        self.assertFalse(indice.complete)
        self.assertEqual(indice.last_page_done, 2)
        self.assertEqual(len(indice), 3)

    def test_end_page_tambem_produz_indice_incompleto(self) -> None:
        """Truncar de propósito trunca do mesmo jeito: quem consome precisa saber."""
        indice = self._varre(10, end_page=3)
        self.assertFalse(indice.complete)
        self.assertEqual(indice.last_page_done, 3)

    def test_pagina_sem_diagrama_conta_como_terminada(self) -> None:
        """O progresso enxerga a página vazia; a lista de entradas não. Se `last_page_done`
        saísse das entradas, retomar releria todas as páginas de prosa do fim do capítulo."""
        indice = self._varre(5, start_page=3)
        self.assertEqual(indice.start_page, 3)
        self.assertEqual(indice.last_page_done, 4)

    def test_os_tres_campos_sobrevivem_ao_disco(self) -> None:
        indice = self._varre(10, end_page=3)
        dados = json.loads(json.dumps(indice.to_dict()))
        voltou = GalleryIndex.from_dict(dados)

        self.assertEqual((voltou.start_page, voltou.last_page_done, voltou.complete), (0, 3, False))

    def test_indice_gravado_antes_deste_item_e_lido_como_completo(self) -> None:
        """Um índice sem as chaves é tão confiável quanto era ontem. Marcá-lo parcial faria os
        34 livros do acervo gritarem lobo de uma vez, e o aviso deixaria de significar algo."""
        antigo = {"version": 1, "source_pdf": "x.pdf", "entries": []}
        voltou = GalleryIndex.from_dict(antigo)
        self.assertTrue(voltou.complete)
        self.assertEqual(voltou.last_page_done, -1)


class RetomadaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        remendo = mock.patch.object(gallery_scan, "cache_board_image", lambda *_a, **_k: self.raiz / "b.png")
        remendo.start()
        self.addCleanup(remendo.stop)

    def _varre(self, paginas: int, **kwargs):  # noqa: ANN003
        with mock.patch.object(gallery_scan, "iter_pdf_diagrams", _gerador(paginas)):
            return build_gallery_index(self.raiz / "livro.pdf", cache_dir=self.raiz, now="2026-08-17", **kwargs)

    def _parcial(self, ate: int) -> GalleryIndex:
        return GalleryIndex(
            source_pdf="livro.pdf",
            entries=[GalleryEntry(page_index=p, diagram_index=1, placement=LEGAL) for p in range(ate + 1)],
            start_page=0,
            last_page_done=ate,
            complete=False,
        )

    def test_retomar_continua_da_pagina_seguinte_e_nao_repete(self) -> None:
        indice = self._varre(10, resume_from=self._parcial(2))

        self.assertTrue(indice.complete)
        self.assertEqual(len(indice), 10, "3 de antes + 7 lidas agora, sem repetir")
        self.assertEqual([e.page_index for e in indice.entries], list(range(10)))

    def test_indice_completo_nao_e_retomado(self) -> None:
        """Não há o que continuar, e reaproveitar as entradas dele duplicaria o livro."""
        completo = self._parcial(4)
        completo.complete = True

        indice = self._varre(10, resume_from=completo)

        self.assertEqual(len(indice), 10)
        self.assertEqual([e.page_index for e in indice.entries], list(range(10)))

    def test_outra_ordem_de_leitura_nao_e_retomada(self) -> None:
        """A numeração de diagrama por página depende da ordem (S-14): as entradas antigas
        descreveriam outros diagramas, e o índice sairia mentindo em vez de incompleto."""
        parcial = self._parcial(2)
        parcial.reading_order = "column"

        indice = self._varre(10, resume_from=parcial, reading_order="row")

        self.assertEqual(len(indice), 10)
        self.assertEqual(indice.start_page, 0, "recomeça do começo em vez de misturar")

    def test_retomar_uma_retomada_tambem_funciona(self) -> None:
        """Fechar a janela duas vezes é o caso real: quem fecha uma vez fecha de novo."""
        primeira = self._parcial(1)
        segunda = self._varre(10, resume_from=primeira, end_page=5)
        self.assertFalse(segunda.complete)

        terceira = self._varre(10, resume_from=segunda)

        self.assertTrue(terceira.complete)
        self.assertEqual([e.page_index for e in terceira.entries], list(range(10)))


if __name__ == "__main__":
    unittest.main()


class AcervoVarridoSemJanelaTests(unittest.TestCase):
    """`cvoff-scan` varre o acervo de fora da janela (S-121).

    São 34 PDFs e 17.823 páginas; o estado hoje é 5 livros com PGN, 7 com índice de Galeria e
    **27 sem nada**. Mesmo depois da S-119 são ~3,5 h para o acervo, e ninguém deixa uma janela
    Tk aberta por 3,5 h.

    Não é interface nova: é o mesmo `build_gallery_index` chamado de onde uma operação de horas
    pertence -- a decisão que a S-73 já tinha tomado para os 104 minutos da busca por posição.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.pdfs = self.raiz / "PDF"
        self.pdfs.mkdir()
        for nome in ("um.pdf", "dois.pdf"):
            (self.pdfs / nome).write_bytes(b"%PDF-1.4\n")

        self.varridos: list[str] = []
        self.indices: dict[str, GalleryIndex] = {}

        def _varre(pdf_source, _model=None, *, on_scanned=None, resume_from=None, **_kwargs):  # noqa: ANN001, ANN003
            caminho = Path(pdf_source)
            self.varridos.append(caminho.name)
            return GalleryIndex(
                source_pdf=str(caminho),
                entries=[GalleryEntry(page_index=0, diagram_index=1, placement=LEGAL)],
                last_page_done=0,
                complete=True,
            )

        remendos = [
            mock.patch.object(cli_scan, "build_gallery_index", _varre),
            mock.patch.object(cli_scan, "save_index", lambda pdf, indice: self.indices.setdefault(Path(pdf).name, indice)),
            mock.patch.object(cli_scan, "load_index", lambda pdf: self.indices.get(Path(pdf).name)),
        ]
        for remendo in remendos:
            remendo.start()
            self.addCleanup(remendo.stop)

    def _args(self, *extra: str) -> list[str]:
        return [
            "--all",
            "--pdf-dir", str(self.pdfs),
            "--queue-dir", str(self.raiz / "filas"),
            "--no-queue",
            *extra,
        ]

    def test_varre_o_acervo_inteiro(self) -> None:
        self.assertEqual(cli_scan.main(self._args()), 0)
        self.assertEqual(sorted(self.varridos), ["dois.pdf", "um.pdf"])

    def test_a_segunda_execucao_nao_revarre_o_que_esta_completo(self) -> None:
        """**O critério de aceite.** Uma noite deixa os 34 com índice; rodar de novo custa só
        o que falta -- senão a retomada seria um recomeço com outro nome."""
        cli_scan.main(self._args())
        self.varridos.clear()

        self.assertEqual(cli_scan.main(self._args()), 0)

        self.assertEqual(self.varridos, [], "os dois já estavam completos")

    def test_force_revarre_mesmo_o_que_esta_completo(self) -> None:
        cli_scan.main(self._args())
        self.varridos.clear()

        cli_scan.main(self._args("--force"))

        self.assertEqual(sorted(self.varridos), ["dois.pdf", "um.pdf"])

    def test_indice_parcial_e_retomado_e_nao_pulado(self) -> None:
        """Um livro que ficou pela metade é exatamente o que a próxima execução deve pegar."""
        self.indices["um.pdf"] = GalleryIndex(source_pdf="um.pdf", last_page_done=3, complete=False)

        cli_scan.main(self._args())

        self.assertIn("um.pdf", self.varridos)

    def test_um_livro_quebrado_nao_derruba_a_noite(self) -> None:
        """3,5 h de varredura não podem terminar em traceback por causa de um PDF corrompido --
        e o código de saída diz que houve erro, para quem chamou de um script saber."""

        def _explode(pdf_source, *_a, **_k):  # noqa: ANN001, ANN002, ANN003
            self.varridos.append(Path(pdf_source).name)
            if Path(pdf_source).name == "um.pdf":
                raise ValueError("PDF corrompido")
            return GalleryIndex(source_pdf=str(pdf_source), complete=True)

        with mock.patch.object(cli_scan, "build_gallery_index", _explode):
            codigo = cli_scan.main(self._args())

        self.assertEqual(codigo, 1, "houve erro, e quem chamou de um script precisa saber")
        self.assertIn("dois.pdf", self.varridos, "e o livro seguinte foi varrido assim mesmo")

    def test_sem_livro_nenhum_pedido_recusa_e_diz_o_que_fazer(self) -> None:
        self.assertEqual(cli_scan.main(["--pdf-dir", str(self.pdfs), "--no-queue"]), 2)

    def test_o_relatorio_soma_o_que_foi_varrido(self) -> None:
        relatorio = cli_scan.ScanReport(
            books=[
                cli_scan.BookResult(pdf="a.pdf", diagrams=10, seconds=60.0),
                cli_scan.BookResult(pdf="b.pdf", skipped="índice completo"),
                cli_scan.BookResult(pdf="c.pdf", error="corrompido"),
            ]
        )
        texto = "\n".join(relatorio.as_lines())

        self.assertIn("1 livro(s) varrido(s), 10 diagrama(s)", texto)
        self.assertIn("1 pulado(s)", texto)
        self.assertIn("1 com erro", texto)

    def test_o_parcial_aparece_no_relatorio(self) -> None:
        """Um índice truncado indistinguível de um completo é o defeito que a S-120 fechou;
        o relatório do acervo não pode reintroduzi-lo."""
        relatorio = cli_scan.ScanReport(books=[cli_scan.BookResult(pdf="a.pdf", diagrams=3, complete=False)])
        self.assertIn("parcial", "\n".join(relatorio.as_lines()))
