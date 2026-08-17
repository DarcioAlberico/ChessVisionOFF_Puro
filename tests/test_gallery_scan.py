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
