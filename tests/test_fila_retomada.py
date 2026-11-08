"""A varredura retomada não apaga as pendências das páginas que ela não releu (S-816).

A varredura do livro retoma da página seguinte à última terminada (S-120), e a fila que ela entrega
só tem as páginas novas. A janela dizia à fusão quais páginas a passada viu (S-119); o `cvoff-scan` e
o `cvoff-review --start-page` não diziam, e as pendências das primeiras páginas sumiam. A regra agora
mora em `fundir_fila_retomada`, e o mesmo caso roda pelos três chamadores.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import TEM_PYQT, aplicacao, descartar
from test_review_queue import KINGS_ONLY, candidate, oriented

from chess_diagram_ocr.arquivo_do_dono import Lida
from chess_diagram_ocr.cli import review as cli_review
from chess_diagram_ocr.cli import scan as cli_scan
from chess_diagram_ocr.config import DEFAULT_READING_ORDER
from chess_diagram_ocr.gallery_scan import GalleryIndex, build_gallery_index
from chess_diagram_ocr.pdf_text import DiagramContext
from chess_diagram_ocr.review_queue import ReviewItem, ReviewQueue, carregar_fila, gravar_fila
from chess_diagram_ocr.ui.varredura_de_revisao import PedidoDeVarredura

PAGINAS = 4


def _item(pdf: Path, pagina: int, *, status: str = "pending") -> ReviewItem:
    return ReviewItem(
        pdf_path=str(pdf),
        page_index=pagina,
        diagram_index=1,
        board_image=f"p{pagina}.png",
        fen=f"{KINGS_ONLY} w - - 0 1",
        side_to_move="w",
        min_confidence=0.2,
        mean_entropy=0.1,
        priority=50.0,
        reasons=("da passada anterior",),
        status=status,  # type: ignore[arg-type]
    )


def _indice_interrompido(pdf: Path) -> GalleryIndex:
    """A Galeria parou depois da página 2 (índice 1): a passada seguinte começa na 3."""
    return GalleryIndex(
        source_pdf=str(pdf),
        reading_order=DEFAULT_READING_ORDER,
        start_page=0,
        last_page_done=1,
        complete=False,
    )


class FilaRetomadaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.pdf = self.pasta / "PDF" / "Livro.pdf"
        self.pdf.parent.mkdir()
        self.pdf.write_bytes(b"%PDF-1.4\n")
        self.cache = self.pasta / "cache"
        remendos = [
            mock.patch("chess_diagram_ocr.pdf_to_pgn._get_pdf_page_count", return_value=PAGINAS),
            mock.patch("chess_diagram_ocr.pdf_to_pgn.load_model", return_value=("model", "cpu")),
            mock.patch(
                "chess_diagram_ocr.pdf_to_pgn._render_pdf_page",
                side_effect=lambda *a, **k: candidate().board_rgb,
            ),
            mock.patch("chess_diagram_ocr.pdf_to_pgn._detect_page_diagrams", side_effect=lambda *a, **k: [candidate()]),
            mock.patch("chess_diagram_ocr.pdf_to_pgn._page_contexts", side_effect=lambda *a, **k: [DiagramContext()]),
            # Toda leitura é suspeita: cada página visitada põe um item na fila.
            mock.patch(
                "chess_diagram_ocr.pdf_to_pgn.predict_with_orientation",
                side_effect=lambda *a, **k: oriented(KINGS_ONLY, 0.20),
            ),
            mock.patch("chess_diagram_ocr.review_queue.load_annotations", return_value=mock.Mock(entries={})),
            mock.patch("chess_diagram_ocr.cli.scan.DEFAULT_CACHE_DIR", self.cache),
            mock.patch("chess_diagram_ocr.cli.scan.save_index"),
            mock.patch("chess_diagram_ocr.cli.scan.load_index", side_effect=lambda _pdf: _indice_interrompido(self.pdf)),
            mock.patch("chess_diagram_ocr.cli.scan.configure_logging"),
            mock.patch("chess_diagram_ocr.cli.review.configure_logging"),
        ]
        for remendo in remendos:
            remendo.start()
            self.addCleanup(remendo.stop)

    # ------------------------------------------------------------------ os três chamadores

    def _pelo_scan(self, anterior: ReviewQueue) -> ReviewQueue:
        pasta_das_filas = self.pasta / "queues"
        destino = cli_scan._queue_path(pasta_das_filas, self.pdf)
        destino.parent.mkdir(parents=True, exist_ok=True)
        gravar_fila(Lida(anterior, destino))
        with mock.patch("builtins.print"):
            codigo = cli_scan.main([str(self.pdf), "--queue-dir", str(pasta_das_filas)])
        self.assertEqual(codigo, 0)
        return carregar_fila(destino).valor

    def _pelo_review(self, anterior: ReviewQueue, *extra: str) -> ReviewQueue:
        destino = self.pasta / "review_queue.json"
        gravar_fila(Lida(anterior, destino))
        argumentos = [str(self.pdf), "--queue", str(destino), "--cache-dir", str(self.cache)]
        argumentos += ["--labels", str(self.pasta / "nao_ha.csv"), "--start-page", "2", *extra]
        with mock.patch("builtins.print"):
            codigo = cli_review.main(argumentos)
        self.assertEqual(codigo, 0)
        return carregar_fila(destino).valor

    def _pela_janela(self, anterior: ReviewQueue) -> ReviewQueue:
        if not TEM_PYQT:
            self.skipTest("PyQt6 ausente")
        from chess_diagram_ocr.qt.painel_de_revisao import PainelDeRevisao

        app = aplicacao()
        self.addCleanup(app.processEvents)
        destino = self.pasta / "fila_da_janela.json"
        gravar_fila(Lida(anterior, destino))
        pedido = PedidoDeVarredura(pdf_path=self.pdf, model_path=self.pasta / "m.pt", labels_csv=self.pasta / "x.csv")
        painel = PainelDeRevisao(pedido_de_varredura=lambda: pedido, queue_path=destino, cache_dir=self.cache)
        self.addCleanup(descartar, painel)
        sumidouro = painel.sumidouro()
        assert sumidouro is not None
        build_gallery_index(
            self.pdf, cache_dir=self.cache, resume_from=_indice_interrompido(self.pdf), on_scanned=sumidouro.feed
        )
        sumidouro.deliver(cancelled=False)
        return carregar_fila(destino).valor

    CHAMADORES: dict[str, Callable[[FilaRetomadaTests, ReviewQueue], ReviewQueue]] = {
        "cvoff-scan": _pelo_scan,
        "cvoff-review --start-page": _pelo_review,
        "janela": _pela_janela,
    }

    # ------------------------------------------------------------------------------ casos

    def test_scan_retomado_preserva_pendencias_das_primeiras_paginas(self) -> None:
        anterior = ReviewQueue(
            source_pdf=str(self.pdf),
            items=[_item(self.pdf, 0), _item(self.pdf, 1, status="done"), _item(self.pdf, 2, status="done")],
        )
        for nome, chamador in self.CHAMADORES.items():
            with self.subTest(chamador=nome):
                fila = chamador(self, anterior)
                estados = {item.page_index: item.status for item in fila.items}
                self.assertEqual(
                    estados,
                    {0: "pending", 1: "done", 2: "done", 3: "pending"},
                    "as duas primeiras páginas não foram relidas e ficam como estavam",
                )

    def test_fila_de_outro_livro_nao_e_fundida(self) -> None:
        """A fonte é conferida pela `ChaveDoLivro`: o que é de outro livro não entra nesta fila."""
        outro = self.pasta / "outro" / "Livro.pdf"
        anterior = ReviewQueue(source_pdf=str(outro), items=[_item(outro, 0)])
        for nome, chamador in self.CHAMADORES.items():
            with self.subTest(chamador=nome):
                fila = chamador(self, anterior)
                self.assertEqual(sorted(item.page_index for item in fila.items), [2, 3])

    def test_review_com_limite_nao_apaga_o_que_o_corte_deixou_de_fora(self) -> None:
        """`--limit` corta a fila nova depois de ordenar; a pendência que estava numa página
        visitada e ficou fora do corte não é "deixou de ser suspeita"."""
        anterior = ReviewQueue(source_pdf=str(self.pdf), items=[_item(self.pdf, 0), _item(self.pdf, 3)])
        fila = self._pelo_review(anterior, "--limit", "1")
        self.assertEqual(sorted({item.page_index for item in fila.items}), [0, 2, 3])
        self.assertEqual(len(fila.items), 3, "e sem item repetido")

    def test_dois_livros_de_mesmo_nome_tem_filas_separadas(self) -> None:
        pasta_das_filas = self.pasta / "queues"
        self.assertNotEqual(
            cli_scan._queue_path(pasta_das_filas, self.pasta / "a" / "Livro.pdf"),
            cli_scan._queue_path(pasta_das_filas, self.pasta / "b" / "Livro.pdf"),
        )

    def test_fila_do_nome_antigo_e_aproveitada_quando_e_deste_livro(self) -> None:
        """A fila gravada como `<nome>.json` antes da S-816 não fica órfã: se ela diz que é deste
        livro, a varredura parte dela."""
        pasta_das_filas = self.pasta / "queues"
        pasta_das_filas.mkdir()
        antiga = pasta_das_filas / "Livro.json"
        gravar_fila(Lida(ReviewQueue(source_pdf=str(self.pdf), items=[_item(self.pdf, 0, status="done")]), antiga))
        with mock.patch("builtins.print"):
            cli_scan.main([str(self.pdf), "--queue-dir", str(pasta_das_filas)])
        fila = carregar_fila(cli_scan._queue_path(pasta_das_filas, self.pdf)).valor
        self.assertEqual({item.page_index: item.status for item in fila.items}, {0: "done", 2: "pending", 3: "pending"})
        self.assertFalse(antiga.exists(), "e o nome antigo sai de cena, para não haver duas filas do livro")


if __name__ == "__main__":
    unittest.main()
