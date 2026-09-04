"""Varredura da biblioteca inteira (S-34).

O critério de aceite é "processar os 27 PDFs numa execução, com relatório e **sem perder
progresso se um livro falhar**". A terceira parte é a que o desenho tem de garantir, e é o
que estes testes exercitam: o `save_pdf_positions_to_pgn` é substituído, para que a falha
possa ser provocada de propósito sem depender de um PDF corrompido de verdade.
"""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.batch import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_SKIPPED,
    VERSAO_DO_RELATORIO,
    BatchOptions,
    BatchReport,
    BookResult,
    caminho_do_relatorio_de_qualidade,
    find_pdfs,
    gravar_relatorios_de_qualidade,
    relatorio_de_qualidade,
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
    """Uma pasta com PDFs de mentira, apagada com o teste. O conteúdo não importa: a exportação é substituída."""

    def __init__(self, caso: unittest.TestCase, nomes: list[str]) -> None:
        self.dir = pasta_temporaria(caso, prefixo="cvoff-lote-")
        self.pdfs = self.dir / "PDF"
        self.pdfs.mkdir()
        self.saida = self.dir / "PGN"
        for nome in nomes:
            (self.pdfs / nome).write_bytes(b"%PDF-1.4\n")


class FindTests(unittest.TestCase):
    def test_a_directory_yields_its_pdfs_in_name_order(self) -> None:
        """Ordem estável importa: uma varredura retomada tem de repetir a mesma sequência."""
        biblioteca = _Biblioteca(self, ["c.pdf", "a.pdf", "b.pdf"])
        self.assertEqual([p.name for p in find_pdfs(biblioteca.pdfs)], ["a.pdf", "b.pdf", "c.pdf"])

    def test_a_single_file_is_accepted_too(self) -> None:
        biblioteca = _Biblioteca(self, ["um.pdf"])
        self.assertEqual(find_pdfs(biblioteca.pdfs / "um.pdf"), [biblioteca.pdfs / "um.pdf"])

    def test_subdirectories_are_swept(self) -> None:
        biblioteca = _Biblioteca(self, ["raiz.pdf"])
        (biblioteca.pdfs / "sub").mkdir()
        (biblioteca.pdfs / "sub" / "fundo.pdf").write_bytes(b"%PDF-1.4\n")
        self.assertEqual(len(find_pdfs(biblioteca.pdfs)), 2)


class RunTests(unittest.TestCase):
    def test_every_book_gets_a_result(self) -> None:
        biblioteca = _Biblioteca(self, ["a.pdf", "b.pdf", "c.pdf"])
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
        biblioteca = _Biblioteca(self, ["a.pdf", "b.pdf", "c.pdf"])

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
        biblioteca = _Biblioteca(self, ["a.pdf"])
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
        biblioteca = _Biblioteca(self, ["a.pdf", "b.pdf"])
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
        biblioteca = _Biblioteca(self, ["a.pdf"])
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
        biblioteca = _Biblioteca(self, ["a.pdf", "b.pdf", "c.pdf"])
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
        biblioteca = _Biblioteca(self, ["a.pdf", "b.pdf"])
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
        biblioteca = _Biblioteca(self, ["a.pdf"])
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
        biblioteca = _Biblioteca(self, ["a.pdf"])
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


class AvisoPorPaginaTests(unittest.TestCase):
    """O que a fila da janela precisava e o terminal não (S-546).

    `on_book_start`/`on_book_done` bastam para uma linha de texto e não para uma barra: no
    `Yusupov` são 2.612 páginas entre um aviso e o outro.
    """

    def test_o_aviso_por_pagina_chega_com_o_livro_e_o_total(self) -> None:
        biblioteca = _Biblioteca(self, ["a.pdf"])
        avisos: list[tuple[str, int, int, int]] = []

        def _exportar(**kw: object) -> ExportReport:
            progresso = kw["progress_callback"]
            assert progresso is not None
            for pagina in range(3):
                progresso(pagina, 3, 1, pagina + 1)  # type: ignore[operator]
            return _report(kw["output_path"])  # type: ignore[arg-type]

        with mock.patch("chess_diagram_ocr.batch.save_pdf_positions_to_pgn", side_effect=_exportar):
            run_batch(
                find_pdfs(biblioteca.pdfs),
                biblioteca.saida,
                on_page=lambda pdf, feitas, total, diagramas: avisos.append(
                    (pdf.name, feitas, total, diagramas)
                ),
            )

        self.assertEqual(avisos, [("a.pdf", 1, 3, 1), ("a.pdf", 2, 3, 2), ("a.pdf", 3, 3, 3)])

    def test_sem_o_aviso_a_varredura_nao_pede_progresso(self) -> None:
        """O `cvoff-batch` não usa o aviso por página, e ligá-lo de graça faria a exportação
        chamar um callback por página em toda varredura de terminal."""
        biblioteca = _Biblioteca(self, ["a.pdf"])
        vistos: list[object] = []

        def _exportar(**kw: object) -> ExportReport:
            vistos.append(kw["progress_callback"])
            return _report(kw["output_path"])  # type: ignore[arg-type]

        with mock.patch("chess_diagram_ocr.batch.save_pdf_positions_to_pgn", side_effect=_exportar):
            run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida)
        self.assertEqual(vistos, [None])

    def test_o_modelo_do_servico_e_pedido_uma_vez_por_livro(self) -> None:
        """Segurar o lock da S-31 pela varredura inteira deixaria a janela sem reconhecer a
        página aberta durante horas -- é a S-57 com a granularidade que a fila permite."""
        biblioteca = _Biblioteca(self, ["a.pdf", "b.pdf"])
        pedidos: list[Path] = []
        sessoes: list[object] = []

        def _exportar(**kw: object) -> ExportReport:
            sessoes.append(kw["model_session"])
            return _report(kw["output_path"])  # type: ignore[arg-type]

        def _sessao(caminho: Path) -> object:
            pedidos.append(caminho)
            return object()

        with mock.patch("chess_diagram_ocr.batch.save_pdf_positions_to_pgn", side_effect=_exportar):
            run_batch(find_pdfs(biblioteca.pdfs), biblioteca.saida, session_factory=_sessao)  # type: ignore[arg-type]

        self.assertEqual(len(pedidos), 2, "um empréstimo por livro, e não um pela varredura")
        self.assertEqual(len({id(sessao) for sessao in sessoes}), 2, "cada livro recebe a sua sessão")


class RelatorioDeQualidadeTests(unittest.TestCase):
    """Um JSON por livro: páginas, diagramas, legalidade, tempo e procedência (S-548)."""

    def _resultado(self, **campos: object) -> BookResult:
        base: dict[str, object] = {
            "pdf": Path("PDF/livro.pdf"),
            "status": STATUS_OK,
            "output": Path("PGN/livro.pgn"),
            "pages": 70,
            "accepted": 3,
            "needs_review": 5,
            "rejected": 2,
            "elapsed_s": 35.0,
        }
        base.update(campos)
        return BookResult(**base)  # type: ignore[arg-type]

    def test_as_quatro_perguntas_do_item_estao_no_json(self) -> None:
        """Páginas lidas, diagramas, legalidade e tempo -- e as quatro só respondem juntas:
        `120 diagramas` sozinho não diz se o livro foi bem; `120 diagramas, 0 exportados` diz."""
        relatorio = relatorio_de_qualidade(self._resultado(), BatchOptions())
        self.assertEqual(relatorio["pages"], 70)
        self.assertEqual(relatorio["diagrams"], 10)
        self.assertEqual(relatorio["exported"], 3)
        self.assertEqual(relatorio["illegal"], 2)
        self.assertEqual(relatorio["legal_rate"], 0.8)
        self.assertEqual(relatorio["elapsed_s"], 35.0)
        self.assertEqual(relatorio["seconds_per_page"], 0.5)
        self.assertEqual(relatorio["seconds_per_diagram"], 3.5)

    def test_um_livro_sem_diagrama_nao_divide_por_zero(self) -> None:
        relatorio = relatorio_de_qualidade(
            self._resultado(accepted=0, needs_review=0, rejected=0, pages=0), BatchOptions()
        )
        self.assertEqual(relatorio["seconds_per_diagram"], 0.0)
        self.assertEqual(relatorio["seconds_per_page"], 0.0)
        self.assertEqual(relatorio["legal_rate"], 1.0)

    def test_a_procedencia_diz_com_que_modelo_e_com_que_dpi(self) -> None:
        """Sem ela o número não se reproduz: o mesmo livro a 220 e a 300 DPI dá outra contagem
        (S-547), e o `.pt` é reescrito por todo treino (S-57)."""
        procedencia = relatorio_de_qualidade(self._resultado(), BatchOptions(dpi=300))["provenance"]
        self.assertEqual(procedencia["dpi"], 300)
        self.assertIn("identity", procedencia["model"])
        self.assertIn("path", procedencia["model"])
        self.assertEqual(procedencia["reading_order"], BatchOptions().reading_order)

    def test_o_caminho_publicado_e_relativo_a_raiz(self) -> None:
        """Um relatório com o layout do disco de quem mediu não compara com o de outra máquina
        (S-219)."""
        relatorio = relatorio_de_qualidade(self._resultado(), BatchOptions())
        self.assertEqual(relatorio["output"], "PGN/livro.pgn")

    def test_um_arquivo_por_livro_com_o_nome_do_pdf(self) -> None:
        biblioteca = _Biblioteca(self, ["a.pdf", "b.pdf"])
        relatorio = BatchReport(started_at="2026-09-04 10:00:00")
        relatorio.books = [
            self._resultado(pdf=biblioteca.pdfs / "a.pdf"),
            self._resultado(pdf=biblioteca.pdfs / "b.pdf", status=STATUS_SKIPPED),
        ]
        gravados = gravar_relatorios_de_qualidade(relatorio, BatchOptions(), biblioteca.saida)
        self.assertEqual([caminho.name for caminho in gravados], ["a.qualidade.json", "b.qualidade.json"])
        conteudo = json.loads(gravados[1].read_text(encoding="utf-8"))
        self.assertEqual(conteudo["status"], STATUS_SKIPPED)
        self.assertEqual(conteudo["book"], "b.pdf")
        self.assertEqual(conteudo["schema"], VERSAO_DO_RELATORIO)

    def test_o_livro_pulado_tambem_ganha_relatorio(self) -> None:
        """Ele nem chega a ter PGN próprio nesta rodada, e o relatório dele -- que diz "já estava
        exportado" -- ainda tem de saber onde nascer."""
        caminho = caminho_do_relatorio_de_qualidade(Path("PDF/livro.pdf"), Path("PGN"))
        self.assertEqual(caminho, Path("PGN/livro.qualidade.json"))


if __name__ == "__main__":
    unittest.main()
