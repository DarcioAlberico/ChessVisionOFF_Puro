"""`cvoff-scan` — varre o acervo sem janela aberta (S-121).

    cvoff-scan --all                    # todos os PDFs de PDF/, o que faltar
    cvoff-scan "livro.pdf"              # um livro
    cvoff-scan --all --force            # revarre inclusive o que já está completo
    cvoff-scan --all --no-queue         # só o índice da Galeria

**O estado do acervo é o argumento do item.** São 34 PDFs e 17.823 páginas; hoje há 5 livros
com PGN, 7 com índice de Galeria e **27 sem nada**. Varrer era operação de primeiro plano, e
mesmo depois da S-119 são ~3,5 h para o acervo inteiro. Ninguém deixa uma janela Tk aberta por
3,5 h.

**Não é interface nova.** É o mesmo `build_gallery_index` chamado de fora da janela, que é onde
uma operação de horas pertence -- a mesma decisão que a S-73 tomou para os 104 minutos da busca
por posição: *"104 minutos atrás de um botão é uma janela travada que ninguém entende"*.

Uma passada por livro produz **os dois** artefatos (S-119), e o que já está completo é pulado
(S-120), então rodar de novo custa só o que falta.
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULT_MAX_BOARDS, DEFAULT_PDF_DIR, DEFAULT_READING_ORDER
from ..gallery_scan import build_gallery_index, index_path_for, load_index, save_index
from ..logging_setup import configure_logging, default_log_file, onde_esta_o_rastro
from ..review_queue import DEFAULT_CACHE_DIR, ReviewQueue, ReviewQueueBuilder, merge_queues
from . import (
    EXIT_BAD_INPUT,
    EXIT_FAILURE,
    EXIT_OK,
    add_dpi_argument,
    add_model_argument,
    add_verbose,
    cli_errors,
    message_for,
)
from ._ocr import add_ocr_argument, caption_reader_from_args

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_DIR = DEFAULT_CACHE_DIR.parent / "queues"
"""Uma fila por livro, e não a `data/review_queue.json` única da janela.

A fila da interface é "o livro que estou revisando agora" e é substituída a cada varredura; o
acervo varrido de uma vez precisa de 34 delas ao mesmo tempo, e sobrescrever uma única faria a
varredura noturna terminar com a do último livro."""


@dataclass
class BookResult:
    """O que a varredura de um livro produziu, ou por que ela não aconteceu."""

    pdf: str
    diagrams: int = 0
    pages: int = 0
    queued: int = 0
    seconds: float = 0.0
    complete: bool = True
    skipped: str = ""
    error: str = ""


@dataclass
class ScanReport:
    books: list[BookResult] = field(default_factory=list)

    @property
    def scanned(self) -> list[BookResult]:
        return [livro for livro in self.books if not livro.skipped and not livro.error]

    def as_lines(self) -> list[str]:
        linhas = ["", "=" * 78, "Varredura do acervo", "=" * 78]
        for livro in self.books:
            nome = livro.pdf[:44]
            if livro.error:
                linhas.append(f"  {nome:46} ERRO: {livro.error[:60]}")
            elif livro.skipped:
                linhas.append(f"  {nome:46} pulado ({livro.skipped})")
            else:
                parcial = "" if livro.complete else "  **parcial**"
                linhas.append(
                    f"  {nome:46} {livro.diagrams:5} diagrama(s), {livro.queued:4} na fila, "
                    f"{livro.seconds / 60:5.1f} min{parcial}"
                )
        feitos = self.scanned
        linhas.append("")
        linhas.append(
            f"  {len(feitos)} livro(s) varrido(s), {sum(item.diagrams for item in feitos)} diagrama(s), "
            f"{sum(item.seconds for item in feitos) / 60:.0f} min no total."
        )
        pulados = [livro for livro in self.books if livro.skipped]
        if pulados:
            linhas.append(f"  {len(pulados)} pulado(s) -- use --force para revarrer.")
        erros = [livro for livro in self.books if livro.error]
        if erros:
            linhas.append(f"  {len(erros)} com erro. {onde_esta_o_rastro()}")
        linhas.append("")
        return linhas


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Varre livros do acervo e grava índice da Galeria e fila de revisão (S-121).",
        epilog="Uma passada por livro produz os dois artefatos. O que já está completo é pulado.",
    )
    parser.add_argument("books", nargs="*", type=Path, help="PDFs a varrer. Vazio com --all: a pasta inteira.")
    parser.add_argument("--all", action="store_true", help="Varre todos os PDFs de --pdf-dir.")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta do acervo de livros.")
    add_model_argument(parser)
    parser.add_argument("--queue-dir", type=Path, default=DEFAULT_QUEUE_DIR, help="Onde as filas de revisão são gravadas.")
    add_dpi_argument(parser)
    parser.add_argument("--max-boards", type=int, default=DEFAULT_MAX_BOARDS, help="Teto de diagramas aceitos por página.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Revarre do zero, inclusive livros com índice completo.",
    )
    parser.add_argument("--no-queue", action="store_true", help="Só o índice da Galeria; não monta fila.")
    parser.add_argument("--limit-books", "--limite-livros", type=int, default=None, help="Para depois de N livros.")
    add_ocr_argument(parser)
    add_verbose(parser)
    return parser.parse_args(argv)


def books_to_scan(args: argparse.Namespace) -> list[Path]:
    """Os PDFs pedidos, ou a pasta inteira em ordem. Ordenado para a retomada ser previsível."""
    if args.books:
        return [Path(livro) for livro in args.books]
    if not args.all:
        return []
    return sorted(p for p in Path(args.pdf_dir).glob("*.pdf") if p.is_file())


def _queue_path(queue_dir: Path, pdf_path: Path) -> Path:
    return Path(queue_dir) / f"{pdf_path.stem}.json"


def scan_book(
    pdf_path: Path,
    args: argparse.Namespace,
    *,
    caption_reader: object = None,
) -> BookResult:
    """Uma passada, dois artefatos. Erro vira linha do relatório, não interrupção da noite."""
    resultado = BookResult(pdf=pdf_path.name)
    anterior = None if args.force else load_index(pdf_path)
    if anterior is not None and anterior.complete and anterior.entries and not args.force:
        resultado.skipped = f"índice completo com {len(anterior.entries)} diagrama(s)"
        return resultado

    construtor = (
        None
        if args.no_queue
        else ReviewQueueBuilder(pdf_path, cache_dir=DEFAULT_CACHE_DIR)
    )
    comeco = time.perf_counter()
    try:
        indice = build_gallery_index(
            pdf_path,
            args.model,
            dpi=args.dpi,
            max_boards_per_page=args.max_boards,
            reading_order=DEFAULT_READING_ORDER,
            caption_reader=caption_reader,
            resume_from=anterior,
            on_scanned=None if construtor is None else construtor.feed,
        )
    except Exception as exc:  # noqa: BLE001 - um livro quebrado nao pode derrubar a noite
        # Mesma razao do `batch` (S-126): o relatorio ja diz o que falhou, em pt-BR.
        logger.debug("Falha ao varrer %s.", pdf_path.name, exc_info=True)
        resultado.error = message_for(exc)
        resultado.seconds = time.perf_counter() - comeco
        return resultado

    resultado.seconds = time.perf_counter() - comeco
    resultado.diagrams = len(indice)
    resultado.pages = indice.pages_scanned
    resultado.complete = indice.complete
    save_index(pdf_path, indice)

    if construtor is not None:
        destino = _queue_path(args.queue_dir, pdf_path)
        fila = construtor.finish()
        if destino.exists():
            # Revarrer nao pode ressuscitar o que ja foi revisado -- e a regra do
            # `merge_queues`, e ela vale tanto aqui quanto na janela.
            fila = merge_queues(ReviewQueue.load(destino), fila)
        destino.parent.mkdir(parents=True, exist_ok=True)
        fila.save(destino)
        resultado.queued = len(fila.items)
    return resultado


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    livros = books_to_scan(args)
    if not livros:
        print("Nenhum livro pedido. Passe caminhos de PDF, ou --all para a pasta inteira.")
        print(f"Pasta padrão: {args.pdf_dir}")
        return EXIT_BAD_INPUT
    if args.limit_books is not None:
        livros = livros[: args.limit_books]

    leitor = caption_reader_from_args(args)
    relatorio = ScanReport()
    for numero, pdf_path in enumerate(livros, start=1):
        if not pdf_path.exists():
            relatorio.books.append(BookResult(pdf=pdf_path.name, error="arquivo não encontrado"))
            continue
        print(f"[{numero}/{len(livros)}] {pdf_path.name}", flush=True)
        relatorio.books.append(scan_book(pdf_path, args, caption_reader=leitor))
        # Impresso a cada livro, e nao so no fim: uma varredura de 3,5 h que so fala no
        # ultimo minuto e indistinguivel de uma travada.
        print(f"    {relatorio.books[-1].diagrams} diagrama(s) em {relatorio.books[-1].seconds / 60:.1f} min", flush=True)

    for linha in relatorio.as_lines():
        print(linha)
    print(f"Índices em {index_path_for(livros[0]).parent}; filas em {args.queue_dir}.")
    print()
    return EXIT_FAILURE if any(livro.error for livro in relatorio.books) else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
