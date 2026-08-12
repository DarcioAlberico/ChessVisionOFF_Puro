"""O instrumento do critério de saída da Fase 8 (`cvoff-sides`).

Sem PDF e sem modelo: o que se testa aqui é a contabilidade e a amostragem, e nenhuma das
duas precisa de um livro de verdade. A medição real mora em `docs/metrics/`.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from chess_diagram_ocr.side_survey import (
    BookSides,
    SideSurvey,
    sample_pages,
    source_label,
    survey_book,
    write_survey,
)


class _Diagrama:
    def __init__(self, source: str) -> None:
        self.side_to_move_source = source


class _Servico:
    """Um `OcrService` de mentira: devolve o que o teste mandou, por página."""

    def __init__(self, por_pagina: dict[int, list[str]]) -> None:
        self.por_pagina = por_pagina
        self.paginas_vistas: list[int] = []

    def recognize_page(self, pdf_source, page_index, *, options=None):  # noqa: ANN001, ARG002
        self.paginas_vistas.append(page_index)
        return [_Diagrama(source) for source in self.por_pagina.get(page_index, [])]


class SamplePagesTests(unittest.TestCase):
    def test_evenly_spaced_and_never_the_edges(self) -> None:
        indices = sample_pages(100, 4)
        self.assertEqual(len(indices), 4)
        self.assertNotIn(0, indices)
        self.assertNotIn(99, indices)
        self.assertEqual(indices, sorted(indices))

    def test_short_book_returns_every_page(self) -> None:
        self.assertEqual(sample_pages(3, 12), [0, 1, 2])

    def test_is_deterministic(self) -> None:
        # Se sorteasse, comparar "com OCR" e "sem OCR" mediria o sorteio.
        self.assertEqual(sample_pages(402, 12), sample_pages(402, 12))

    def test_degenerate_inputs_are_empty(self) -> None:
        self.assertEqual(sample_pages(0, 12), [])
        self.assertEqual(sample_pages(100, 0), [])


class BookAccountingTests(unittest.TestCase):
    def _livro(self, fontes: list[str]) -> BookSides:
        book = BookSides(pdf="x.pdf", diagrams=len(fontes))
        for fonte in fontes:
            book.by_source[fonte] += 1
        return book

    def test_text_legality_and_assumed_are_counted_apart(self) -> None:
        """Colapsá-las faria o critério parecer atingido por um caminho anterior à Fase 8."""
        book = self._livro(["text", "ocr-page-scope", "legality", "legality", "default"])
        self.assertEqual(book.from_text, 2)
        self.assertEqual(book.from_legality, 2)
        self.assertEqual(book.assumed, 1)
        self.assertEqual(book.resolved, 4)
        self.assertAlmostEqual(book.resolved_share, 0.8)

    def test_a_book_that_assumes_everything_resolves_nothing(self) -> None:
        book = self._livro(["default"] * 6)
        self.assertEqual(book.resolved, 0)
        self.assertEqual(book.resolved_share, 0.0)

    def test_share_of_an_empty_book_is_zero_not_a_division_error(self) -> None:
        self.assertEqual(BookSides(pdf="vazio.pdf").resolved_share, 0.0)


class SurveyTests(unittest.TestCase):
    def test_survey_book_tallies_every_sampled_page(self) -> None:
        servico = _Servico({20: ["text", "default"], 40: ["legality"]})
        with patch("chess_diagram_ocr.side_survey.get_pdf_page_count", return_value=60):
            book = survey_book(Path("livro.pdf"), servico, options=None, pages=2)

        self.assertEqual(servico.paginas_vistas, [20, 40])
        self.assertEqual(book.diagrams, 3)
        self.assertEqual(book.pages_with_diagram, 2)
        self.assertEqual(book.from_text, 1)
        self.assertEqual(book.from_legality, 1)
        self.assertEqual(book.assumed, 1)

    def test_a_book_that_raises_does_not_take_the_collection_down(self) -> None:
        class Explode(_Servico):
            def recognize_page(self, pdf_source, page_index, *, options=None):  # noqa: ANN001, ARG002
                if page_index == 20:
                    raise RuntimeError("PDF corrompido")
                return [_Diagrama("text")]

        with patch("chess_diagram_ocr.side_survey.get_pdf_page_count", return_value=60):
            book = survey_book(Path("livro.pdf"), Explode({}), options=None, pages=2)

        self.assertEqual(book.pages_sampled, 2)
        self.assertEqual(book.diagrams, 1)

    def test_collection_counts_books_by_the_two_criteria(self) -> None:
        survey = SideSurvey()
        survey.books = [
            BookSides(pdf="a.pdf", diagrams=4, by_source={"text": 3, "default": 1}),  # type: ignore[arg-type]
            BookSides(pdf="b.pdf", diagrams=4, by_source={"legality": 1, "default": 3}),  # type: ignore[arg-type]
            BookSides(pdf="c.pdf", diagrams=4, by_source={"default": 4}),  # type: ignore[arg-type]
            BookSides(pdf="d.pdf"),
        ]

        self.assertEqual([b.pdf for b in survey.books_with_diagrams], ["a.pdf", "b.pdf", "c.pdf"])
        self.assertEqual([b.pdf for b in survey.books_resolved], ["a.pdf", "b.pdf"])
        self.assertEqual([b.pdf for b in survey.books_resolved_by_text], ["a.pdf"])
        # b.pdf resolve 1 de 4: nao e maioria, e a diferenca entre os dois numeros e o ponto.
        self.assertEqual([b.pdf for b in survey.books_mostly_resolved], ["a.pdf"])

    def test_json_round_trips(self) -> None:
        import json
        import tempfile

        survey = SideSurvey(ocr_engine="rapidocr")
        survey.books = [BookSides(pdf="a.pdf", diagrams=2, by_source={"ocr": 2})]  # type: ignore[arg-type]
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "sides.json"
            write_survey(destino, survey)
            lido = json.loads(destino.read_text(encoding="utf-8"))

        self.assertEqual(lido["ocr_engine"], "rapidocr")
        self.assertEqual(lido["books_resolved_by_text"], 1)
        self.assertEqual(lido["per_book"][0]["from_text"], 2)

    def test_labels_survive_an_unknown_source(self) -> None:
        # A interface produz fontes fora do `SideSource` ("queue"); a tabela nao pode quebrar.
        self.assertEqual(source_label("legality"), "legalidade")
        self.assertEqual(source_label("queue"), "queue")


if __name__ == "__main__":
    unittest.main()
