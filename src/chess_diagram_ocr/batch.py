"""Varredura de uma biblioteca inteira de PDFs, com relatório consolidado (S-34).

**O que ele substitui.** `PDF/Andamento.txt` — um arquivo de controle mantido à mão, onde o
progresso por livro era anotado a dedo. Um txt manual não sabe quantos diagramas foram
rejeitados, nem com que confiança, nem quanto tempo levou; e ninguém consegue dizer, olhando
para ele, se está atualizado.

**A regra que organiza tudo aqui: um livro que falha não derruba a varredura.** Com 27 PDFs
e minutos por livro, uma exceção no décimo que abortasse o processo custaria tudo que veio
antes. Cada livro é isolado, a falha vira uma linha do relatório com o motivo, e a varredura
segue. É literalmente o critério de aceite da S-34.

**E o relatório é gravado a cada livro, não no fim.** Pelo mesmo motivo: se o processo
morrer por algo que o `try` não pega — falta de memória, o usuário fechando o terminal —, o
que já foi medido continua no disco. Um relatório escrito só no fim é um relatório que não
existe exatamente quando ele seria mais útil.

**`--skip-existing` é o que torna a varredura retomável** sem nenhum estado próprio: o PGN
que já está no disco é o registro de que aquele livro foi feito. Não inventa um segundo
lugar para a verdade morar.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .checkpoint import checkpoint_identity
from .cli import message_for
from .config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
    OrientationMode,
    ReadingOrder,
    caminho_para_relatorio,
)
from .pdf_to_pgn import ExportReport, default_pgn_output_path, save_pdf_positions_to_pgn

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_SKIPPED = "pulado"
STATUS_FAILED = "falhou"
STATUS_CANCELLED = "cancelado"

PageProgress = Callable[[Path, int, int, int], None]
"""`(livro, páginas feitas, páginas do livro, diagramas lidos até agora)` (S-546).

Existe porque `on_book_start`/`on_book_done` bastam para um terminal e não para uma barra: no
`Yusupov` são 2.612 páginas entre um aviso e o outro, e uma janela que ficasse 40 minutos sem
mudar nada é uma janela travada aos olhos de quem espera. O `progress_callback` que
`save_pdf_positions_to_pgn` já emitia por página morria aqui dentro, sem chamador.
"""

SessionFactory = Callable[[Path], AbstractContextManager[tuple[Any, str]]]
"""Empresta o modelo do `OcrService` **por livro**, com o lock da S-31 (S-57).

Por livro e não pela fila inteira de propósito: segurar o lock por uma varredura de cinquenta
livros deixaria a própria janela sem conseguir reconhecer a página aberta durante horas -- o
mesmo raciocínio da S-57, com a granularidade que a fila permite.

`None` -- o padrão -- é o caminho do `cvoff-batch`: ali não há serviço nem treino concorrente, e
cada livro carrega o `.pt` por conta própria como sempre carregou.
"""


@dataclass(frozen=True)
class BatchOptions:
    """Os parâmetros de leitura, iguais para todos os livros da varredura."""

    model_path: Path = DEFAULT_MODEL_PATH
    dpi: int = 220
    max_boards_per_page: int = DEFAULT_MAX_BOARDS
    orientation: OrientationMode = DEFAULT_ORIENTATION_MODE
    reading_order: ReadingOrder = DEFAULT_READING_ORDER
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE
    dedupe: bool = False
    skip_existing: bool = True
    """Livro cujo PGN já existe é pulado. O arquivo no disco **é** o registro de progresso;
    um segundo lugar para essa verdade morar só teria como divergir do primeiro."""


@dataclass(frozen=True)
class BookResult:
    """O que aconteceu com um livro. Sempre existe, mesmo quando ele falhou."""

    pdf: Path
    status: str
    output: Path | None = None
    review_path: Path | None = None
    pages: int = 0
    accepted: int = 0
    needs_review: int = 0
    rejected: int = 0
    duplicates: int = 0
    mean_min_confidence: float = 0.0
    elapsed_s: float = 0.0
    error: str = ""

    @property
    def total_diagrams(self) -> int:
        return self.accepted + self.needs_review + self.rejected

    @property
    def acceptance_rate(self) -> float:
        """Fração aceita no PGN principal. `0.0` quando não houve diagrama nenhum."""
        return self.accepted / self.total_diagrams if self.total_diagrams else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf": str(self.pdf),
            "status": self.status,
            "output": str(self.output) if self.output else None,
            "review_path": str(self.review_path) if self.review_path else None,
            "pages": self.pages,
            "accepted": self.accepted,
            "needs_review": self.needs_review,
            "rejected": self.rejected,
            "duplicates": self.duplicates,
            "mean_min_confidence": round(self.mean_min_confidence, 4),
            "acceptance_rate": round(self.acceptance_rate, 4),
            "elapsed_s": round(self.elapsed_s, 2),
            "error": self.error,
        }

    def line(self) -> str:
        """Uma linha para o terminal. Os rejeitados aparecem sempre que existem (S-15)."""
        if self.status == STATUS_SKIPPED:
            return f"  {self.pdf.name}: já exportado, pulado"
        if self.status == STATUS_FAILED:
            return f"  {self.pdf.name}: FALHOU — {self.error}"

        partes = [
            f"{self.pages} págs",
            f"{self.accepted} aceitos",
        ]
        if self.needs_review:
            partes.append(f"{self.needs_review} p/ revisão")
        if self.rejected:
            partes.append(f"{self.rejected} ilegais")
        if self.duplicates:
            partes.append(f"{self.duplicates} repetidos")
        partes.append(f"conf mín média {self.mean_min_confidence:.3f}")
        partes.append(f"{self.elapsed_s:.1f}s")
        marca = " (cancelado)" if self.status == STATUS_CANCELLED else ""
        return f"  {self.pdf.name}{marca}: " + ", ".join(partes)


@dataclass
class BatchReport:
    """A varredura inteira. Mutável porque é gravada a cada livro, não só no fim."""

    books: list[BookResult] = field(default_factory=list)
    started_at: str = ""

    @property
    def processed(self) -> list[BookResult]:
        return [livro for livro in self.books if livro.status in (STATUS_OK, STATUS_CANCELLED)]

    @property
    def failed(self) -> list[BookResult]:
        return [livro for livro in self.books if livro.status == STATUS_FAILED]

    @property
    def total_accepted(self) -> int:
        return sum(livro.accepted for livro in self.books)

    @property
    def total_needs_review(self) -> int:
        return sum(livro.needs_review for livro in self.books)

    @property
    def total_rejected(self) -> int:
        return sum(livro.rejected for livro in self.books)

    @property
    def elapsed_s(self) -> float:
        return sum(livro.elapsed_s for livro in self.books)

    def summary(self) -> str:
        """O resumo final. Falhas aparecem por nome, não como um contador.

        "3 livros falharam" não permite agir; os nomes permitem.
        """
        pulados = sum(1 for livro in self.books if livro.status == STATUS_SKIPPED)
        linhas = [
            f"{len(self.processed)} livro(s) processado(s), {pulados} pulado(s), "
            f"{len(self.failed)} com falha em {self.elapsed_s / 60:.1f} min.",
            f"Diagramas: {self.total_accepted} aceitos, {self.total_needs_review} para revisão, "
            f"{self.total_rejected} ilegais.",
        ]
        for livro in self.failed:
            linhas.append(f"  falhou: {livro.pdf.name} — {livro.error}")
        return "\n".join(linhas)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "books": [livro.to_dict() for livro in self.books],
            "totals": {
                "processed": len(self.processed),
                "failed": len(self.failed),
                "accepted": self.total_accepted,
                "needs_review": self.total_needs_review,
                "rejected": self.total_rejected,
                "elapsed_s": round(self.elapsed_s, 2),
            },
        }


def find_pdfs(source: Path) -> list[Path]:
    """Os PDFs a varrer, em ordem de nome. Aceita um arquivo ou um diretório."""
    if source.is_file():
        return [source]
    return sorted(p for p in source.rglob("*.pdf") if p.is_file())


def _mean_min_confidence(report: ExportReport) -> float:
    """Confiança mínima média entre **todos** os diagramas lidos, e não só os aceitos.

    Média só dos aceitos subiria conforme o gate rejeitasse mais — o número melhoraria
    justamente nos livros em que a leitura piorou.
    """
    posicoes = (
        list(report.accepted)
        + [p for p, _motivo in report.needs_review]
        + [p for p, _motivo in report.rejected]
    )
    if not posicoes:
        return 0.0
    valores = [float(getattr(p, "min_confidence", 0.0) or 0.0) for p in posicoes]
    return sum(valores) / len(valores)


def run_batch(
    sources: Sequence[Path] | Iterable[Path],
    output_dir: Path,
    *,
    options: BatchOptions | None = None,
    report_path: Path | None = None,
    on_book_start: Callable[[Path, int, int], None] | None = None,
    on_book_done: Callable[[BookResult], None] | None = None,
    on_page: PageProgress | None = None,
    session_factory: SessionFactory | None = None,
    cancel_event: threading.Event | None = None,
) -> BatchReport:
    """Exporta cada PDF para PGN e devolve o relatório consolidado.

    Sequencial de propósito. A S-34 sugere `--workers 2`, mas a inferência do torch já usa
    as CPUs disponíveis: dois processos disputariam os mesmos núcleos e ainda carregariam
    dois modelos na memória. A decisão é a mesma que a S-24 tomou para páginas, pelo mesmo
    motivo, e está registrada no ROADMAP.

    `on_page` e `session_factory` são o que a fila da janela precisava e o terminal não (S-546):
    um aviso por **página**, para a barra do livro andar, e o empréstimo do modelo do serviço.
    Ver `PageProgress` e `SessionFactory`.
    """
    options = options or BatchOptions()
    output_dir.mkdir(parents=True, exist_ok=True)
    relatorio = BatchReport(started_at=time.strftime("%Y-%m-%d %H:%M:%S"))

    livros = list(sources)
    for indice, pdf in enumerate(livros, start=1):
        if cancel_event is not None and cancel_event.is_set():
            logger.info("Varredura cancelada antes de %s.", pdf.name)
            break

        if on_book_start is not None:
            on_book_start(pdf, indice, len(livros))

        resultado = _run_one(pdf, output_dir, options, cancel_event, on_page, session_factory)
        relatorio.books.append(resultado)

        if on_book_done is not None:
            on_book_done(resultado)
        if report_path is not None:
            # A cada livro, e nao no fim: se o processo morrer por algo que o `try` nao
            # pega, o que ja foi medido continua no disco.
            atomic_write_json(report_path, relatorio.to_dict())

    return relatorio


def _run_one(
    pdf: Path,
    output_dir: Path,
    options: BatchOptions,
    cancel_event: threading.Event | None,
    on_page: PageProgress | None = None,
    session_factory: SessionFactory | None = None,
) -> BookResult:
    saida = output_dir / default_pgn_output_path(pdf).name
    if options.skip_existing and saida.exists():
        logger.info("Pulando %s: %s ja existe.", pdf.name, saida.name)
        return BookResult(pdf=pdf, status=STATUS_SKIPPED, output=saida)

    def _pagina(indice: int, total: int, _na_pagina: int, posicoes: int) -> None:
        # `indice + 1` porque o que a barra mostra e "pagina 12 de 70", e nao o indice: quem
        # espera conta a partir de um.
        if on_page is not None:
            on_page(pdf, indice + 1, total, posicoes)

    inicio = time.monotonic()
    try:
        report = save_pdf_positions_to_pgn(
            pdf_source=pdf,
            output_path=saida,
            model_path=options.model_path,
            dpi=options.dpi,
            max_boards_per_page=options.max_boards_per_page,
            orientation=options.orientation,
            reading_order=options.reading_order,
            accept_threshold=options.accept_threshold,
            dedupe=options.dedupe,
            cancel_event=cancel_event,
            progress_callback=_pagina if on_page is not None else None,
            model_session=session_factory(options.model_path) if session_factory is not None else None,
        )
    except Exception as exc:
        # Um livro que falha nao derruba a varredura: com 27 PDFs e minutos por livro, uma
        # excecao no decimo custaria tudo que veio antes (criterio da S-34).
        # `debug` e nao `exception`: o relatorio abaixo ja diz que este livro falhou, e em
        # pt-BR (S-126). O traceback vai para o log, que e onde ele serve -- na tela ele
        # empurrava o resumo dos outros livros para fora do terminal.
        logger.debug("Falha ao exportar %s.", pdf.name, exc_info=True)
        return BookResult(
            pdf=pdf,
            status=STATUS_FAILED,
            output=saida,
            elapsed_s=time.monotonic() - inicio,
            error=f"{type(exc).__name__}: {message_for(exc)}",
        )

    if not report.cancelled and report.pages_scanned <= 0:
        # **Zero página é falha, e não "ok" com zero.** Um PDF truncado -- o download que parou no
        # meio, o arquivo de 0 byte -- abre, não entrega página nenhuma e saía daqui com
        # `status: "ok"`, `pages: 0`, `error: ""` e um `.pgn` de 0 byte ao lado. Na fila da janela
        # isso aparece como um livro pronto que não achou nada, que é o resultado de verdade de
        # cinco livros do acervo (`ROADMAP.md:151`) -- e os dois ficam indistinguíveis. Um livro
        # que não teve página não foi lido.
        return BookResult(
            pdf=pdf,
            status=STATUS_FAILED,
            output=report.output_path,
            review_path=report.review_path,
            elapsed_s=time.monotonic() - inicio,
            error="o livro não entregou página nenhuma; o PDF pode estar truncado ou vazio",
        )

    return BookResult(
        pdf=pdf,
        status=STATUS_CANCELLED if report.cancelled else STATUS_OK,
        output=report.output_path,
        review_path=report.review_path,
        pages=report.pages_scanned,
        accepted=len(report.accepted),
        needs_review=len(report.needs_review),
        rejected=len(report.rejected),
        duplicates=len(report.duplicates),
        mean_min_confidence=_mean_min_confidence(report),
        elapsed_s=time.monotonic() - inicio,
    )


# ------------------------------------------- o relatório de qualidade por livro (S-548)

VERSAO_DO_RELATORIO = 1
"""A versão do **formato** deste JSON, na forma de `text/arquivo.py` e `text/fila.py`.

Quem abrir um relatório antigo daqui a seis meses precisa saber se os campos que ele espera
existiam. Sem isso, um campo acrescentado depois é indistinguível de um campo que a medição
daquele dia deixou em branco.
"""

SUFIXO_DO_RELATORIO = ".qualidade.json"
"""`<livro>.qualidade.json`, **ao lado do PGN** e não em `docs/metrics/`.

`docs/metrics/` é o arquivo de medição do repositório -- versionado, comparado por guarda, com
procedência de código. O relatório de um livro varrido na máquina de quem usa o programa é saída
do usuário, e mora onde a saída dele mora. Ver `docs/SPEC_SUITE.md`, S-548.
"""


def _versao_do_programa() -> str:
    """A versão da distribuição instalada, ou `""` sem instalação a consultar.

    É a **mesma leitura** que `ui/strings._versao_instalada` faz, do **mesmo** `DISTRIBUICAO`, e
    não uma segunda declaração: a verdade é o metadado da distribuição, e ler o mesmo metadado de
    dois lugares não tem como divergir. O que a S-161 proibiu foi *cravar* o número, que é outra
    coisa -- e repetir aqui o nome do pacote seria cravar metade dele.

    Os dois `import` são tardios porque este relatório é gravado uma vez por varredura: importar
    `ui/strings` no topo faria todo `cvoff-batch` ler os metadados da distribuição na partida, para
    um campo que só é escrito no fim.
    """
    from importlib.metadata import PackageNotFoundError, version

    from .ui.strings import DISTRIBUICAO

    try:
        return version(DISTRIBUICAO)
    except PackageNotFoundError:
        return ""


def _por(valor: float, quantos: int) -> float:
    return round(valor / quantos, 4) if quantos else 0.0


def _taxa(parte: int, todo: int) -> float | None:
    """A fração, ou `None` quando não há de que tirar fração.

    **`None` e não `0.0`, e não `1.0`.** `legal_rate` saía `1.0` num livro sem diagrama nenhum --
    "100% das posições são legais" sobre zero posição --, e um relatório que responde a pergunta
    que ninguém pôde medir é pior que um que se cala: quem compara dois livros num gráfico vê o
    livro que falhou no topo. `null` no JSON diz *não medido*, que é a verdade.
    """
    return round(parte / todo, 4) if todo else None


def relatorio_de_qualidade(
    resultado: BookResult, options: BatchOptions, *, medido_em: str = ""
) -> dict[str, Any]:
    """O que aquele livro entregou, e com o quê -- o item da S-548.

    **Quatro perguntas, e as quatro só respondem juntas:** quantas páginas foram lidas, quantos
    diagramas saíram de lá, quantos deles são posições legais, e quanto tempo custou. `120
    diagramas` sozinho não diz se o livro foi bem; `120 diagramas, 0 exportados` diz, e é o
    estado de cinco livros do acervo. O tempo por página é o que torna dois livros comparáveis
    quando um tem 70 páginas e outro 2.612.

    **A procedência entra porque sem ela o número não se reproduz** (S-219). O modelo é
    reescrito por todo treino, então o caminho não o identifica: vai junto o
    `checkpoint_identity`, que é `<tamanho>-<mtime_ns>` e custa um `stat`. E vão os parâmetros de
    leitura, porque o mesmo livro medido a 220 e a 300 DPI dá números diferentes -- medido na
    S-547: no `Niemeijer`, 51 diagramas contra 18.

    Os caminhos saem **relativos à raiz** quando cabem nela, pela mesma razão dos relatórios de
    campo: um relatório com o layout do disco de quem mediu não compara com o de outra máquina.
    """
    modelo = Path(options.model_path)
    return {
        "schema": VERSAO_DO_RELATORIO,
        "book": resultado.pdf.name,
        "status": resultado.status,
        "output": caminho_para_relatorio(resultado.output) if resultado.output else None,
        "review_path": caminho_para_relatorio(resultado.review_path) if resultado.review_path else None,
        "pages": resultado.pages,
        "diagrams": resultado.total_diagrams,
        "exported": resultado.accepted,
        "needs_review": resultado.needs_review,
        "illegal": resultado.rejected,
        "duplicates": resultado.duplicates,
        "export_rate": _taxa(resultado.accepted, resultado.total_diagrams),
        "legal_rate": _taxa(resultado.total_diagrams - resultado.rejected, resultado.total_diagrams),
        "mean_min_confidence": round(resultado.mean_min_confidence, 4),
        "elapsed_s": round(resultado.elapsed_s, 2),
        "seconds_per_page": _por(resultado.elapsed_s, resultado.pages),
        "seconds_per_diagram": _por(resultado.elapsed_s, resultado.total_diagrams),
        "error": resultado.error,
        "provenance": {
            "model": {"path": caminho_para_relatorio(modelo), "identity": checkpoint_identity(modelo)},
            "dpi": options.dpi,
            "max_boards_per_page": options.max_boards_per_page,
            "orientation": options.orientation,
            "reading_order": options.reading_order,
            "accept_threshold": options.accept_threshold,
            "dedupe": options.dedupe,
            "program": _versao_do_programa(),
            "measured_at": medido_em,
        },
    }


def caminho_do_relatorio_de_qualidade(pdf: Path, output_dir: Path) -> Path:
    """`<pasta>/<livro>.qualidade.json`. O nome sai do PDF e não do PGN.

    Do PDF porque o livro pulado nem chega a ter PGN próprio nesta rodada, e o relatório dele --
    que diz justamente "já estava exportado" -- ainda tem de saber onde nascer.
    """
    return Path(output_dir) / f"{Path(pdf).stem}{SUFIXO_DO_RELATORIO}"


def gravar_relatorios_de_qualidade(
    relatorio: BatchReport, options: BatchOptions, output_dir: Path
) -> list[Path]:
    """Um JSON por livro da varredura. Devolve os caminhos gravados, em ordem.

    Escrita por `atomic_write_json`, como todo arquivo de trabalho deste projeto: um relatório
    pela metade é pior que nenhum, porque ele **abre** e responde números truncados.

    Um livro cujo relatório não consegue ser gravado não derruba os outros -- é a mesma regra do
    livro que falha na varredura (S-34), e aqui ela pesa mais: perder cinquenta relatórios porque
    um nome de arquivo é inválido seria perder a medição inteira por causa da última linha dela.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    gravados: list[Path] = []
    for livro in relatorio.books:
        destino = caminho_do_relatorio_de_qualidade(livro.pdf, output_dir)
        try:
            atomic_write_json(destino, relatorio_de_qualidade(livro, options, medido_em=relatorio.started_at))
        except OSError as exc:
            logger.warning("Nao foi possivel gravar %s: %s", destino.name, exc)
            continue
        gravados.append(destino)
    return gravados
