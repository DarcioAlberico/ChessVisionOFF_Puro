"""Quantos livros do acervo deixam de assumir o lado a jogar — o critério de saída da Fase 8.

A Fase 8 declara que fecha "quando a procedência `[SideToMoveSource]` deixa de ser `default`
em pelo menos 12 dos 27 livros". Até aqui esse número **não tinha instrumento**: o projeto
sabia dizer a procedência de um diagrama, e não a de um acervo. É a mesma lacuna que a S-41
fechou para a Fase 7, e pelo mesmo motivo -- um critério de saída sem medição é uma opinião
com número.

**O que se mede.** Um punhado de páginas por livro, espalhadas por ele, pelo pipeline que a
exportação usa (`OcrService.recognize_page`). De cada diagrama sai uma procedência, e das
procedências sai a conta por livro.

**A distinção que o relatório não pode colapsar.** `legality` também não é `default`, e
sozinha ela já resolve 118 dos 3.195 rótulos -- contá-la junto faria o critério parecer
atingido por um caminho que existia antes da Fase 8 começar. Por isso o relatório separa
sempre três colunas: **texto** (a camada do PDF ou o OCR da S-43), **legalidade** (a dedução
da S-17) e **assumido**. A manchete usa "não é `default`", que é a letra do critério; a coluna
de texto é o que a Fase 8 de fato entregou.

**Amostragem determinística.** Páginas igualmente espaçadas, sem sorteio: duas execuções do
mesmo comando sobre o mesmo acervo têm de dar o mesmo número, senão a comparação com e sem
OCR mede o sorteio.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .pdf_io import get_pdf_page_count, sample_pages
from .semantics import SideSource
from .service import OcrService, RecognitionOptions

logger = logging.getLogger(__name__)

TEXT_SOURCES: frozenset[str] = frozenset({"text", "ocr", "text-page-scope", "ocr-page-scope"})
"""As procedências que vêm de algo escrito na página -- camada de texto ou OCR (S-43)."""

DEFAULT_PAGES_PER_BOOK = 12
"""Doze páginas por livro, e o número é um compromisso declarado.

Uma página custa ~3 s de CPU; 27 livros a 12 páginas são ~16 minutos, que cabe numa sessão.
Menos que isso e um livro cuja legenda aparece em metade das páginas vira sorte ou azar."""


@dataclass
class BookSides:
    """A conta de um livro."""

    pdf: str
    pages_sampled: int = 0
    pages_with_diagram: int = 0
    diagrams: int = 0
    by_source: Counter[str] = field(default_factory=Counter)

    @property
    def from_text(self) -> int:
        return sum(count for source, count in self.by_source.items() if source in TEXT_SOURCES)

    @property
    def from_legality(self) -> int:
        return self.by_source.get("legality", 0)

    @property
    def assumed(self) -> int:
        return self.by_source.get("default", 0)

    @property
    def resolved(self) -> int:
        """Diagramas cuja procedência não é `default`."""
        return self.diagrams - self.assumed

    @property
    def resolved_share(self) -> float:
        return self.resolved / self.diagrams if self.diagrams else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "pdf": self.pdf,
            "pages_sampled": self.pages_sampled,
            "pages_with_diagram": self.pages_with_diagram,
            "diagrams": self.diagrams,
            "by_source": dict(sorted(self.by_source.items())),
            "from_text": self.from_text,
            "from_legality": self.from_legality,
            "assumed": self.assumed,
            "resolved": self.resolved,
            "resolved_share": round(self.resolved_share, 4),
        }


@dataclass
class SideSurvey:
    """O acervo inteiro, e as três contagens que o critério de saída pede."""

    books: list[BookSides] = field(default_factory=list)
    ocr_engine: str = ""

    @property
    def books_with_diagrams(self) -> list[BookSides]:
        """Um livro em que a amostra não achou diagrama nenhum não diz nada sobre legendas."""
        return [book for book in self.books if book.diagrams]

    @property
    def books_resolved(self) -> list[BookSides]:
        return [book for book in self.books if book.resolved]

    @property
    def books_resolved_by_text(self) -> list[BookSides]:
        return [book for book in self.books if book.from_text]

    @property
    def books_mostly_resolved(self) -> list[BookSides]:
        return [book for book in self.books if book.resolved_share > 0.5]

    @property
    def diagrams(self) -> int:
        return sum(book.diagrams for book in self.books)

    def as_dict(self) -> dict[str, Any]:
        totais: Counter[str] = Counter()
        for book in self.books:
            totais.update(book.by_source)
        return {
            "ocr_engine": self.ocr_engine,
            "books": len(self.books),
            "books_with_diagrams": len(self.books_with_diagrams),
            "books_resolved": len(self.books_resolved),
            "books_resolved_by_text": len(self.books_resolved_by_text),
            "books_mostly_resolved": len(self.books_mostly_resolved),
            "diagrams": self.diagrams,
            "by_source": dict(sorted(totais.items())),
            "per_book": [book.as_dict() for book in self.books],
        }


__all__ = [
    "BookSides",
    "DEFAULT_PAGES_PER_BOOK",
    "SideSurvey",
    "TEXT_SOURCES",
    "sample_pages",
    "source_label",
    "survey_book",
    "survey_collection",
    "write_survey",
]
"""`sample_pages` mudou para `pdf_io` na S-82 e segue reexportada aqui: ela estreou neste
módulo e é assim que os testes e os CLIs a nomeiam. Duas implementações divergiriam, e a
amostragem tem de ser a mesma nos dois levantamentos para que eles falem da mesma página."""


def survey_book(
    pdf_path: Path,
    service: OcrService,
    options: RecognitionOptions,
    *,
    pages: int = DEFAULT_PAGES_PER_BOOK,
) -> BookSides:
    """Amostra um livro e devolve a conta das procedências."""
    resultado = BookSides(pdf=pdf_path.name)
    indices = sample_pages(get_pdf_page_count(pdf_path), pages)
    resultado.pages_sampled = len(indices)

    for indice in indices:
        try:
            lidos = service.recognize_page(pdf_path, indice, options=options)
        except Exception as exc:  # noqa: BLE001 -- um livro ruim nao pode derrubar o acervo
            logger.warning("%s p%d: falhou (%s: %s)", pdf_path.name, indice + 1, type(exc).__name__, exc)
            continue
        if lidos:
            resultado.pages_with_diagram += 1
        for diagrama in lidos:
            resultado.diagrams += 1
            resultado.by_source[str(diagrama.side_to_move_source)] += 1

    return resultado


def survey_collection(
    pdf_dir: Path,
    service: OcrService,
    options: RecognitionOptions,
    *,
    pages: int = DEFAULT_PAGES_PER_BOOK,
    ocr_engine: str = "",
    on_book: Any = None,
) -> SideSurvey:
    """Todos os PDFs do diretório, em ordem de nome. `on_book(BookSides)` a cada livro."""
    survey = SideSurvey(ocr_engine=ocr_engine)
    for pdf_path in sorted(Path(pdf_dir).glob("*.pdf")):
        book = survey_book(pdf_path, service, options, pages=pages)
        survey.books.append(book)
        if on_book is not None:
            on_book(book)
    return survey


def write_survey(path: Path, survey: SideSurvey) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(survey.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def source_label(source: str) -> str:
    """Rótulo curto para a tabela. Aceita `str` porque a UI produz fontes fora do `SideSource`."""
    curtos: dict[SideSource | str, str] = {
        "text": "texto",
        "ocr": "OCR",
        "text-page-scope": "texto/página",
        "ocr-page-scope": "OCR/página",
        "legality": "legalidade",
        "manual": "à mão",
        "default": "assumido",
    }
    return curtos.get(source, source)
