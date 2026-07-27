"""Varredura da biblioteca inteira (S-34).

O critério de aceite é "processar os 27 PDFs numa execução, com relatório e **sem perder
progresso se um livro falhar**". A terceira parte é a que o desenho tem de garantir, e é o
que estes testes exercitam: o `save_pdf_positions_to_pgn` é substituído, para que a falha
possa ser provocada de propósito sem depender de um PDF corrompido de verdade.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from chess_diagram_ocr.batch import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_SKIPPED,
    BatchOptions,
    BookResult,
    find_pdfs,
    run_batch,
)
from chess_diagram_ocr.pdf_to_pgn import DiagramPosition, ExportReport


def _posicao(min_confidence: float) -> DiagramPosition:
    return DiagramPosition(
        page_index=0,
        diagram_index=0,
        fen="8/8/8/8/8/8/8/K6k w - - 0 1",
        confidence=min_confidence,
        min_confidence=min_confidence,
    )


def _report(saida: Path, *, aceitos: int = 2, revisao: int = 1, ilegais: int = 1) -> ExportReport:
    return ExportReport(
        accepted=[_posicao(0.99) for _ in range(aceitos)],
        needs_review=[(_posicao(0.5), "confiança baixa") for _ in range(revisao)],
        rejected=[(_posicao(0.1), "ilegal") for _ in range(ilegais)],
        pages_scanned=10,
        output_path=saida,
        review_path=saida.with_suffix(".review.pgn") if (revisao or ilegais) else None,
    )


class _Biblioteca:
    """Uma pasta com PDFs de mentira. O conteúdo não importa: a exportação é substituída."""

    def __init__(self, nomes: list[str]) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="cvoff-lote-"))
        self.pdfs = self.dir / "PDF"
        self.pdfs.mkdir()
        self.saida = self.dir / "PGN"
        for nome in nomes:
            (self.pdfs / nome).write_bytes(b"%PDF-1.4\n")


class FindTests(unittest.TestCase):
    def test_a_directory_yields_its_pdfs_in_name_order(self) -> None:
        """Ordem estável importa: uma varredura retomada tem de repetir a mesma sequência."""
        biblioteca = _Biblioteca(["c.pdf", "a.pdf", "b.pdf"])
        self.assertEqual([p.name for p in find_pdfs(biblioteca.pdfs)], ["a.pdf", "b.pdf", "c.pdf"])

    def test_a_single_file_is_accepted_too(self) -> None:
        biblioteca = _Biblioteca(["um.pdf"])
        self.assertEqual(find_pdfs(biblioteca.pdfs / "um.pdf"), [biblioteca.pdfs / "um.pdf"])

    def test_subdirectories_are_swept(self) -> None:
        biblioteca = _Biblioteca(["raiz.pdf"])
        (biblioteca.pdfs / "sub").mkdir()
        (biblioteca.pdfs / "sub" / "fundo.pdf").write_bytes(b"%PDF-1.4\n")
        self.assertEqual(len(find_pdfs(biblioteca.pdfs)), 2)


class RunTests(unittest.TestCase):
    def test_every_book_gets_a_result(self) -> None:
        biblioteca = _Biblioteca(["a.pdf", "b.pdf", "c.pdf"])
        with mock.patch(
            "chess_diagram_ocr.batch.save_pdf_positions_to_pgn",
            side_effect=lambda **kw: _report(kw["output_path"]),
        ):
            relatorio = run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida)

        self.assertEqual(len(relatorio.books), 3)
        self.assertTrue(all(livro.status == STATUS_OK for livro in relatorio.books))
        self.assertEqual(relatorio.total_accepted, 6)

    def test_a_failing_book_does_not_stop_the_sweep(self) -> None:
        """O critério de aceite da S-34, na forma em que ele pode ser provado."""
        biblioteca = _Biblioteca(["a.pdf", "b.pdf", "c.pdf"])

        def _exportar(**kw: object) -> ExportReport:
            saida = kw["output_path"]
            assert isinstance(saida, Path)
            if saida.name.startswith("b"):
                raise RuntimeError("PDF corrompido")
            return _report(saida)

        with mock.patch("chess_diagram_ocr.batch.save_pdf_positions_to_pgn", side_effect=_exportar):
            relatorio = run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida)

        self.assertEqual([livro.status for livro in relatorio.books], [STATUS_OK, STATUS_FAILED, STATUS_OK])
        # O que veio antes da falha continua contado, e o que veio depois tambem.
        self.assertEqual(relatorio.total_accepted, 4)

    def test_the_failure_reason_survives_into_the_report(self) -> None:
        """"3 livros falharam" não permite agir; o motivo por nome permite."""
        biblioteca = _Biblioteca(["a.pdf"])
        with mock.patch(
            "chess_diagram_ocr.batch.save_pdf_positions_to_pgn",
            side_effect=RuntimeError("PDF corrompido"),
        ):
            relatorio = run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida)

        self.assertIn("PDF corrompido", relatorio.books[0].error)
        self.assertIn("RuntimeError", relatorio.books[0].error)
        self.assertIn("a.pdf", relatorio.summary())

    def test_an_existing_pgn_is_the_progress_record(self) -> None:
        """`--skip-existing` torna a varredura retomável sem inventar estado próprio."""
        biblioteca = _Biblioteca(["a.pdf", "b.pdf"])
        biblioteca.saida.mkdir(parents=True)
        (biblioteca.saida / "a.pgn").write_text("[Event \"antigo\"]\n", encoding="utf-8")

        with mock.patch(
            "chess_diagram_ocr.batch.save_pdf_positions_to_pgn",
            side_effect=lambda **kw: _report(kw["output_path"]),
        ) as exportar:
            relatorio = run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida)

        self.assertEqual(relatorio.books[0].status, STATUS_SKIPPED)
        self.assertEqual(exportar.call_count, 1, "O livro já exportado não deve ser lido de novo.")

    def test_skipping_can_be_turned_off(self) -> None:
        biblioteca = _Biblioteca(["a.pdf"])
        biblioteca.saida.mkdir(parents=True)
        (biblioteca.saida / "a.pgn").write_text("[Event \"antigo\"]\n", encoding="utf-8")

        with mock.patch(
            "chess_diagram_ocr.batch.save_pdf_positions_to_pgn",
            side_effect=lambda **kw: _report(kw["output_path"]),
        ):
            relatorio = run_batch(
                find_pdfs(biblioteca.pdfs), biblioteca.saida, options=BatchOptions(skip_existing=False)
            )

        self.assertEqual(relatorio.books[0].status, STATUS_OK)

    def test_cancelling_stops_between_books(self) -> None:
        biblioteca = _Biblioteca(["a.pdf", "b.pdf", "c.pdf"])
        cancelar = threading.Event()

        def _exportar(**kw: object) -> ExportReport:
            saida = kw["output_path"]
            assert isinstance(saida, Path)
            cancelar.set()
            return _report(saida)

        with mock.patch("chess_diagram_ocr.batch.save_pdf_positions_to_pgn", side_effect=_exportar):
            relatorio = run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida, cancel_event=cancelar)

        self.assertEqual(len(relatorio.books), 1, "A varredura deve parar depois do livro em curso.")


class ReportFileTests(unittest.TestCase):
    def test_the_report_is_written_after_each_book_and_not_only_at_the_end(self) -> None:
        """Se o processo morrer por algo que o `try` não pega, o já medido fica no disco."""
        biblioteca = _Biblioteca(["a.pdf", "b.pdf"])
        caminho = biblioteca.dir / "relatorio.json"
        vistos: list[int] = []

        def _exportar(**kw: object) -> ExportReport:
            saida = kw["output_path"]
            assert isinstance(saida, Path)
            if caminho.exists():
                vistos.append(len(json.loads(caminho.read_text(encoding="utf-8"))["books"]))
            return _report(saida)

        with mock.patch("chess_diagram_ocr.batch.save_pdf_positions_to_pgn", side_effect=_exportar):
            run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida, report_path=caminho)

        # Ao processar o segundo livro, o primeiro ja estava gravado.
        self.assertEqual(vistos, [1])

    def test_the_report_json_carries_the_numbers_the_txt_never_had(self) -> None:
        biblioteca = _Biblioteca(["a.pdf"])
        caminho = biblioteca.dir / "relatorio.json"
        with mock.patch(
            "chess_diagram_ocr.batch.save_pdf_positions_to_pgn",
            side_effect=lambda **kw: _report(kw["output_path"]),
        ):
            run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida, report_path=caminho)

        dados = json.loads(caminho.read_text(encoding="utf-8"))
        livro = dados["books"][0]
        for campo in ("pages", "accepted", "needs_review", "rejected", "mean_min_confidence", "elapsed_s"):
            with self.subTest(campo=campo):
                self.assertIn(campo, livro)
        self.assertEqual(dados["totals"]["accepted"], 2)


class ConfidenceTests(unittest.TestCase):
    def test_the_mean_confidence_counts_every_diagram_and_not_only_the_accepted(self) -> None:
        """Média só dos aceitos subiria quando o gate rejeitasse mais -- o número melhoraria
        justamente nos livros em que a leitura piorou."""
        biblioteca = _Biblioteca(["a.pdf"])
        with mock.patch(
            "chess_diagram_ocr.batch.save_pdf_positions_to_pgn",
            side_effect=lambda **kw: _report(kw["output_path"], aceitos=1, revisao=1, ilegais=0),
        ):
            relatorio = run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida)

        # (0,99 + 0,50) / 2, e nao 0,99.
        self.assertAlmostEqual(relatorio.books[0].mean_min_confidence, 0.745, places=3)


class LineTests(unittest.TestCase):
    def test_rejected_diagrams_always_appear_in_the_line(self) -> None:
        """O gate da S-15 só ajuda se o usuário souber o que ficou de fora."""
        linha = BookResult(
            pdf=Path("livro.pdf"), status=STATUS_OK, pages=10, accepted=5, needs_review=2, rejected=3
        ).line()
        self.assertIn("3 ilegais", linha)
        self.assertIn("2 p/ revisão", linha)

    def test_a_clean_book_does_not_mention_review_or_rejects(self) -> None:
        linha = BookResult(pdf=Path("livro.pdf"), status=STATUS_OK, pages=10, accepted=5).line()
        self.assertNotIn("revisão", linha)
        self.assertNotIn("ilegais", linha)

    def test_a_failed_book_shows_the_reason_and_not_the_zeros(self) -> None:
        linha = BookResult(pdf=Path("livro.pdf"), status=STATUS_FAILED, error="PDF corrompido").line()
        self.assertIn("FALHOU", linha)
        self.assertIn("PDF corrompido", linha)
        self.assertNotIn("0 aceitos", linha)

    def test_a_cancelled_book_is_marked_but_still_reports_what_it_read(self) -> None:
        linha = BookResult(pdf=Path("livro.pdf"), status=STATUS_CANCELLED, pages=4, accepted=2).line()
        self.assertIn("cancelado", linha)
        self.assertIn("2 aceitos", linha)

    def test_a_skipped_book_says_so(self) -> None:
        self.assertIn("pulado", BookResult(pdf=Path("livro.pdf"), status=STATUS_SKIPPED).line())


if __name__ == "__main__":
    unittest.main()
