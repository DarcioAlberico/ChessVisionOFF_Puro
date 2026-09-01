"""O que o detector aceita no acervo, contado — e comparável com a corrida anterior (S-82).

O projeto mede **leitura** desde a S-08: existe `docs/BASELINE.md`, existe `cvoff-eval`, e
mudar o classificador sem um número é impensável aqui. Para **detecção** não existia nada. A
consequência é medida: o glifo de cavalo do cabeçalho do `Secrets of Chess Training` entrava
como diagrama em **71 das 1181 páginas**, deslocava a numeração do PGN em 14 delas e
envenenava o gabarito de tamanho em 42 — e sobreviveu porque é visível a olho nu e invisível
em qualquer relatório. Ver `docs/ANALISE_DETECCAO.md`.

**O censo não julga; ele conta.** Não existe rótulo humano de "aqui há diagrama" para o
acervo, então não há acurácia de detecção a calcular. O que há é uma distribuição, e ela é
informativa: no livro acima, o lado dos candidatos em pontos é bimodal com um vale de 110 pt
onde não cai uma única amostra. O número que denunciava o defeito estava disponível o tempo
todo; faltava alguém que o imprimisse.

**Por que sem modelo.** Nenhuma inferência, nenhum torch — 0,2 s de import contra ~8 s. Um
censo que custa caro é um censo que não se roda a cada mudança, e rodar a cada mudança é a
única coisa que ele existe para ser.

**As três contagens que denunciam defeito**, e que são o motivo de este módulo não ser um
simples histograma:

| contagem | o que denuncia |
|---|---|
| `suspects` | candidato menor que um diagrama impresso pode ser: glifo, ícone, fragmento |
| `pages_numbering_shifted` | o suspeito veio **antes** de um diagrama de verdade, e consumiu o número que o `[Diagram "N"]` do PGN usa |
| `pages_size_prior_mixed` | suspeito e diagrama na mesma página, então a mediana de `detect_diagrams` cai no vazio entre os dois e o prior de tamanho passa a **recusar** diagrama real |

`suspect_below_pt` é um limiar de **inspeção**, não de filtragem: o censo continua contando o
candidato suspeito em tudo o mais. Quem filtra é o detector, e a decisão de onde cortar é da
S-78 — que este módulo existe para poder medir.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .atomic_io import atomic_write_text
from .board_detection import RejectedQuad
from .config import DEFAULT_MAX_BOARDS, DEFAULT_READING_ORDER, ReadingOrder
from .detection.hybrid import board_texture_score, detect_diagrams
from .pdf_io import PdfSource, opened, render_pdf_page, sample_pages

logger = logging.getLogger(__name__)

DEFAULT_PAGES_PER_BOOK = 24
"""Páginas amostradas por livro quando não se pede o livro inteiro.

O dobro do levantamento de lados (`side_survey`), e cabe no mesmo tempo: aqui uma página custa
~0,4 s porque não há inferência. 27 livros a 24 páginas ficam em ~5 min, que é curto o
bastante para entrar no hábito de rodar antes de commitar detecção."""

DEFAULT_FRONT_MATTER = 8
"""Páginas do **começo** do livro que o censo varre além da amostra (S-143).

`sample_pages` descarta as bordas de propósito -- "a primeira e a última página de um livro de
xadrez são capa, índice ou catálogo, e gastá-las é gastar dois doze avos da amostra em páginas
que nunca têm diagrama". O raciocínio está certo para *achar diagrama* e é exatamente errado
para *achar falso positivo*: capa, folha de rosto e prancha de retrato são onde vive o
ornamento grande, e o censo nunca olhou para lá.

O preço de não olhar, medido: a S-80 registrou o alvo dela -- "capa de capítulo, selo, foto
quadrada" -- como tendo **zero instâncias confirmadas no acervo**, e arquivou a entrega por
isso. As instâncias existiam, nas páginas 1 e 7 do `Karpov 1`, fora da amostra. Quem as
encontrou foi o usuário, abrindo o PDF.

Oito páginas porque é onde a frente do livro acaba no acervo (capa, rosto, créditos, sumário,
prefácio, pranchas). Medido depois da S-143: 73 dos 99 candidatos de contorno desta faixa não
tinham contraste de casa nenhum.

**Linha de base anterior a esta constante não tem estas páginas**, então o primeiro diff depois
da S-143 as mostra como ganho. Ganho não reprova o diff -- `--fail-on-loss` olha perda."""

SUSPECT_BELOW_PT = 72.0
"""Abaixo deste lado em pontos, o candidato é marcado como suspeito no relatório.

Uma polegada: oito filas de 9 pt, já ilegível em papel. Não é um filtro e não decide nada --
é a lente que faz a população de glifos aparecer separada no relatório. No acervo medido em
2026-08-14 o menor diagrama real tem 110 pt (`Euwe Band 1-2`) e o maior glifo tem 50 pt, então
72 pt cai no meio de um vale de 60 pt sem amostra."""

HISTOGRAM_BIN_PT = 10.0
"""Largura da barra do histograma de lado, em pontos. É a resolução em que o vale aparece."""


@dataclass(frozen=True)
class CandidateRow:
    """Um candidato detectado, na granularidade em que o censo compara duas corridas.

    `x0`/`y0` viajam junto porque são a **identidade estável** do candidato entre corridas: o
    índice na ordem de leitura muda assim que um candidato some da página, que é exatamente o
    efeito que se quer medir. Casar por índice faria toda remoção parecer uma remoção mais uma
    substituição.
    """

    pdf: str
    page: int
    """1-based, como a interface e o PGN contam -- o CSV é para leitura humana."""

    index: int
    """Posição na ordem de leitura. É o número que vira `[Diagram "N"]`."""

    source: str
    side_pt: float
    native_width: int
    native_height: int
    trimmed: bool
    detector_score: float
    texture: float
    """`board_texture_score` do recorte **entregue**, pós-refino.

    Medido no recorte entregue e não no cru porque é lá que a separação existe: no cru os dois
    conjuntos se tocam (glifos até 0,3827, diagramas a partir de 0,2364), no entregue não
    (glifos até 0,3827, diagramas a partir de 0,6562). A S-80 depende deste número."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def key(self) -> tuple[str, int, int, int]:
        """Identidade entre corridas: livro, página e canto, arredondado ao ponto."""
        return (self.pdf, self.page, round(self.x0), round(self.y0))


@dataclass(frozen=True)
class RejectionRow:
    """Um candidato de contorno **barrado**, e por qual guarda (S-131).

    O censo da S-82 conta o que entra e é cego ao que foi recusado — e é do lado recusado que
    se vê o recall perdido. Mexer num limiar sem isto é medir metade do efeito: dá para ver o
    falso positivo que sumiu, e não o diagrama que sumiu junto.

    Era só para o caminho de **contorno** até a S-176. A fonte embutida tem a declaração do PDF
    a favor dela e guardas próprias, e as recusas dela apareciam em `logger.debug` com o número
    ao lado desde a S-78 -- mas `"faixa-da-pagina"` apaga um candidato embutido inteiro, e uma
    guarda dessas precisa do mesmo instrumento que as outras. Ver `hybrid.BAND_BOARD_FILL`.
    """

    pdf: str
    page: int
    """1-based, como no `CandidateRow` -- os dois CSVs se leem lado a lado."""

    reason: str
    """Qual guarda barrou. Ver `board_detection.MOTIVOS_DE_RECUSA` e os quatro do `hybrid`."""

    score: float
    checker: float
    """Contraste de casa (S-143). `0.0` quando a recusa foi antes de existir recorte."""

    side_pt: float
    x0: float
    y0: float
    x1: float
    y1: float


REJECTION_CSV_FIELDS = (
    "pdf",
    "page",
    "reason",
    "score",
    "checker",
    "side_pt",
    "x0",
    "y0",
    "x1",
    "y1",
)


CSV_FIELDS = (
    "pdf",
    "page",
    "index",
    "source",
    "side_pt",
    "native_width",
    "native_height",
    "trimmed",
    "detector_score",
    "texture",
    "x0",
    "y0",
    "x1",
    "y1",
)


@dataclass
class BookCensus:
    """A conta de um livro. Tudo o que interessa deriva de `rows`."""

    pdf: str
    pages_sampled: int = 0
    pages_with_candidate: int = 0
    pages_failed: int = 0
    rows: list[CandidateRow] = field(default_factory=list)
    suspect_below_pt: float = SUSPECT_BELOW_PT

    @property
    def candidates(self) -> int:
        return len(self.rows)

    @property
    def by_source(self) -> Counter[str]:
        return Counter(row.source for row in self.rows)

    @property
    def suspects(self) -> list[CandidateRow]:
        return [row for row in self.rows if row.side_pt < self.suspect_below_pt]

    @property
    def trimmed(self) -> int:
        return sum(1 for row in self.rows if row.trimmed)

    @property
    def pages_numbering_shifted(self) -> int:
        """Páginas em que um suspeito **não** está no fim da ordem de leitura.

        É a contagem que dá gravidade ao resto: um falso positivo no fim da lista é ruído na
        tela, e um no começo troca a posição a que o `[Diagram "2"]` do PGN se refere.
        """
        shifted = 0
        for _page, rows in self._by_page():
            suspects = [index for index, row in enumerate(rows) if row.side_pt < self.suspect_below_pt]
            if suspects and any(index < len(rows) - len(suspects) for index in suspects):
                shifted += 1
        return shifted

    @property
    def pages_size_prior_mixed(self) -> int:
        """Páginas com suspeito e diagrama juntos, que é onde o prior de tamanho se perde.

        `detect_diagrams` toma a **mediana** dos lados como gabarito da página. Mediana é
        robusta a outlier e não a bimodalidade: com um glifo de 15 pt e um diagrama de 154 pt
        ela dá ~85 pt, e a janela de ±30% passa a recusar todo achado de contorno do tamanho
        real. O prior existe para recuperar diagrama não declarado, e nessas páginas ele faz o
        contrário.
        """
        mixed = 0
        for _page, rows in self._by_page():
            lados = [row.side_pt for row in rows]
            if len(lados) >= 2 and min(lados) < self.suspect_below_pt <= max(lados):
                mixed += 1
        return mixed

    def _by_page(self) -> list[tuple[int, list[CandidateRow]]]:
        agrupado: dict[int, list[CandidateRow]] = {}
        for row in self.rows:
            agrupado.setdefault(row.page, []).append(row)
        return [(page, sorted(rows, key=lambda r: r.index)) for page, rows in sorted(agrupado.items())]

    def side_histogram(self, bin_pt: float = HISTOGRAM_BIN_PT) -> dict[int, int]:
        """Lado em pontos, agrupado. O vale entre glifo e diagrama aparece aqui e só aqui."""
        histograma: Counter[int] = Counter()
        for row in self.rows:
            histograma[int(round(row.side_pt / bin_pt) * bin_pt)] += 1
        return dict(sorted(histograma.items()))

    def texture_stats(self) -> dict[str, float]:
        if not self.rows:
            return {}
        valores = np.array([row.texture for row in self.rows], dtype=np.float64)
        return {
            "min": round(float(valores.min()), 4),
            "p05": round(float(np.percentile(valores, 5)), 4),
            "median": round(float(np.median(valores)), 4),
            "max": round(float(valores.max()), 4),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "pdf": self.pdf,
            "pages_sampled": self.pages_sampled,
            "pages_with_candidate": self.pages_with_candidate,
            "pages_failed": self.pages_failed,
            "candidates": self.candidates,
            "by_source": dict(sorted(self.by_source.items())),
            "trimmed": self.trimmed,
            "suspects": len(self.suspects),
            "pages_numbering_shifted": self.pages_numbering_shifted,
            "pages_size_prior_mixed": self.pages_size_prior_mixed,
            "side_histogram": {str(k): v for k, v in self.side_histogram().items()},
            "texture": self.texture_stats(),
        }


@dataclass
class DetectionCensus:
    """O acervo inteiro, com os parâmetros que produziram os números.

    Os parâmetros ficam gravados junto porque o censo só vale contra outro censo: comparar uma
    corrida a 220 DPI com uma a 300 mede o DPI, não a mudança no detector.
    """

    books: list[BookCensus] = field(default_factory=list)
    dpi: int = 220
    max_boards: int = DEFAULT_MAX_BOARDS
    reading_order: str = DEFAULT_READING_ORDER
    pages_per_book: int | None = DEFAULT_PAGES_PER_BOOK
    suspect_below_pt: float = SUSPECT_BELOW_PT
    front_matter: int = DEFAULT_FRONT_MATTER

    @property
    def rows(self) -> list[CandidateRow]:
        return [row for book in self.books for row in book.rows]

    @property
    def candidates(self) -> int:
        return sum(book.candidates for book in self.books)

    @property
    def suspects(self) -> int:
        return sum(len(book.suspects) for book in self.books)

    @property
    def books_with_suspects(self) -> list[BookCensus]:
        return [book for book in self.books if book.suspects]

    def as_dict(self) -> dict[str, Any]:
        fontes: Counter[str] = Counter()
        for book in self.books:
            fontes.update(book.by_source)
        return {
            "dpi": self.dpi,
            "max_boards": self.max_boards,
            "reading_order": self.reading_order,
            "pages_per_book": self.pages_per_book,
            "front_matter": self.front_matter,
            "suspect_below_pt": self.suspect_below_pt,
            "books": len(self.books),
            "candidates": self.candidates,
            "suspects": self.suspects,
            "books_with_suspects": len(self.books_with_suspects),
            "pages_numbering_shifted": sum(book.pages_numbering_shifted for book in self.books),
            "pages_size_prior_mixed": sum(book.pages_size_prior_mixed for book in self.books),
            "by_source": dict(sorted(fontes.items())),
            "per_book": [book.as_dict() for book in self.books],
        }


def census_page(
    pdf_source: PdfSource,
    page_index: int,
    pdf_name: str,
    *,
    dpi: int = 220,
    max_boards: int = DEFAULT_MAX_BOARDS,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    rejections: list[RejectionRow] | None = None,
) -> list[CandidateRow]:
    """Os candidatos de uma página, na forma em que o censo os grava.

    Chama `detect_diagrams` — o mesmo detector da GUI e da exportação, e não uma cópia dele.
    Um censo que medisse outro caminho mediria outro programa.

    `rejections`, quando dado, recebe também o que foi **barrado** (S-131), convertido de pixel
    para ponto do PDF — a mesma unidade das caixas aceitas, para que os dois CSVs se leiam lado
    a lado e o mesmo candidato possa ser seguido de uma corrida para a outra.
    """
    page_rgb = render_pdf_page(pdf_source, page_index, dpi=dpi)
    recusados: list[RejectedQuad] | None = [] if rejections is not None else None
    with opened(pdf_source) as emprestado:
        page = emprestado.doc[page_index]
        candidatos = detect_diagrams(
            page, page_rgb, max_boards=max_boards, reading_order=reading_order, rejected=recusados
        )
        escala = page_rgb.shape[1] / page.rect.width if page.rect.width else 1.0

    if rejections is not None and recusados:
        for recusa in recusados:
            x, y, largura, altura = recusa.bbox
            x0, y0 = x / escala, y / escala
            x1, y1 = (x + largura) / escala, (y + altura) / escala
            rejections.append(
                RejectionRow(
                    pdf=pdf_name,
                    page=page_index + 1,
                    reason=recusa.reason,
                    score=round(recusa.score, 4),
                    checker=round(recusa.checker, 4),
                    side_pt=round(max(x1 - x0, y1 - y0), 2),
                    x0=round(x0, 2),
                    y0=round(y0, 2),
                    x1=round(x1, 2),
                    y1=round(y1, 2),
                )
            )

    linhas: list[CandidateRow] = []
    for index, candidato in enumerate(candidatos):
        x0, y0, x1, y1 = candidato.bbox_pdf
        linhas.append(
            CandidateRow(
                pdf=pdf_name,
                page=page_index + 1,
                index=index,
                source=candidato.source,
                side_pt=round(max(x1 - x0, y1 - y0), 2),
                native_width=candidato.native_size[0],
                native_height=candidato.native_size[1],
                trimmed=candidato.trimmed,
                detector_score=round(candidato.detector_score, 4),
                texture=round(board_texture_score(candidato.board_rgb), 4),
                x0=round(x0, 2),
                y0=round(y0, 2),
                x1=round(x1, 2),
                y1=round(y1, 2),
            )
        )
    return linhas


def census_book(
    pdf_path: Path,
    *,
    pages: int | None = DEFAULT_PAGES_PER_BOOK,
    dpi: int = 220,
    max_boards: int = DEFAULT_MAX_BOARDS,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    suspect_below_pt: float = SUSPECT_BELOW_PT,
    front_matter: int = DEFAULT_FRONT_MATTER,
    on_page: Callable[[int, int], None] | None = None,
    rejections: list[RejectionRow] | None = None,
) -> BookCensus:
    """Censo de um livro. `pages=None` varre o livro inteiro.

    Abre o documento **uma vez** e empresta (S-61): a varredura completa do `Secrets` são 1181
    páginas, e três aberturas por página custam 28,80 ms cada no pior livro do acervo.

    `front_matter` acrescenta as N primeiras páginas à amostra, que `sample_pages` descarta de
    propósito -- e que é onde a S-143 encontrou o defeito que a S-80 deu como inexistente. Ver
    `DEFAULT_FRONT_MATTER`. `0` desliga e reproduz a amostragem anterior.
    """
    livro = BookCensus(pdf=pdf_path.name, suspect_below_pt=suspect_below_pt)

    with opened(pdf_path) as emprestado:
        total = emprestado.doc.page_count
        indices = list(range(total)) if pages is None else sample_pages(total, pages)
        if pages is not None and front_matter > 0:
            indices = sorted(set(indices) | set(range(min(front_matter, total))))
        livro.pages_sampled = len(indices)

        for posicao, indice in enumerate(indices):
            try:
                linhas = census_page(
                    emprestado,
                    indice,
                    pdf_path.name,
                    dpi=dpi,
                    max_boards=max_boards,
                    reading_order=reading_order,
                    rejections=rejections,
                )
            except Exception as exc:  # noqa: BLE001 -- uma pagina ruim nao pode derrubar o acervo
                logger.warning("%s p%d: falhou (%s: %s)", pdf_path.name, indice + 1, type(exc).__name__, exc)
                livro.pages_failed += 1
                continue

            if linhas:
                livro.pages_with_candidate += 1
                livro.rows.extend(linhas)
            if on_page is not None:
                on_page(posicao + 1, len(indices))

    return livro


def census_collection(
    pdf_dir: Path,
    *,
    pages: int | None = DEFAULT_PAGES_PER_BOOK,
    dpi: int = 220,
    max_boards: int = DEFAULT_MAX_BOARDS,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    suspect_below_pt: float = SUSPECT_BELOW_PT,
    front_matter: int = DEFAULT_FRONT_MATTER,
    on_book: Callable[[BookCensus], None] | None = None,
    rejections: list[RejectionRow] | None = None,
) -> DetectionCensus:
    """Todos os PDFs do diretório, em ordem de nome. `on_book(BookCensus)` a cada livro."""
    censo = DetectionCensus(
        dpi=dpi,
        max_boards=max_boards,
        reading_order=reading_order,
        pages_per_book=pages,
        suspect_below_pt=suspect_below_pt,
        front_matter=front_matter,
    )
    for pdf_path in sorted(Path(pdf_dir).glob("*.pdf")):
        try:
            livro = census_book(
                pdf_path,
                pages=pages,
                dpi=dpi,
                max_boards=max_boards,
                reading_order=reading_order,
                suspect_below_pt=suspect_below_pt,
                front_matter=front_matter,
                rejections=rejections,
            )
        except Exception as exc:  # noqa: BLE001 -- um PDF quebrado nao pode derrubar o acervo
            logger.warning("%s: nao foi possivel abrir (%s: %s)", pdf_path.name, type(exc).__name__, exc)
            livro = BookCensus(pdf=pdf_path.name, suspect_below_pt=suspect_below_pt)
        censo.books.append(livro)
        if on_book is not None:
            on_book(livro)
    return censo


# ---------------------------------------------------------------------------- entrada e saída


def write_census_csv(path: Path, census: DetectionCensus) -> None:
    """Uma linha por candidato. É este arquivo que a corrida seguinte compara."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDS))
        writer.writeheader()
        for row in census.rows:
            writer.writerow({campo: getattr(row, campo) for campo in CSV_FIELDS})


def write_rejections_csv(path: Path, rejections: list[RejectionRow]) -> None:
    """Uma linha por candidato **barrado**, com o motivo (S-131).

    Arquivo separado do censo de aceitos, e não uma coluna nele: os dois têm cardinalidades
    muito diferentes (o barrado é a maioria), e juntá-los faria toda leitura do censo começar
    por um filtro. Além disso o diff da S-82 casa por canto de bbox, e uma linha de recusa não
    é um candidato que a corrida seguinte deva procurar como se fosse entrega.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REJECTION_CSV_FIELDS))
        writer.writeheader()
        for row in rejections:
            writer.writerow({campo: getattr(row, campo) for campo in REJECTION_CSV_FIELDS})


def rejections_by_reason(rejections: list[RejectionRow]) -> Counter[str]:
    """Quantas recusas por guarda. É o resumo que o `--recusas` imprime."""
    return Counter(row.reason for row in rejections)


def read_census_csv(path: Path) -> list[CandidateRow]:
    """Lê a corrida anterior de volta, para o diff."""
    linhas: list[CandidateRow] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for registro in csv.DictReader(handle):
            linhas.append(
                CandidateRow(
                    pdf=registro["pdf"],
                    page=int(registro["page"]),
                    index=int(registro["index"]),
                    source=registro["source"],
                    side_pt=float(registro["side_pt"]),
                    native_width=int(registro["native_width"]),
                    native_height=int(registro["native_height"]),
                    trimmed=registro["trimmed"] in ("True", "true", "1"),
                    detector_score=float(registro["detector_score"]),
                    texture=float(registro["texture"]),
                    x0=float(registro["x0"]),
                    y0=float(registro["y0"]),
                    x1=float(registro["x1"]),
                    y1=float(registro["y1"]),
                )
            )
    return linhas


def write_census_json(path: Path, census: DetectionCensus) -> None:
    atomic_write_text(path, json.dumps(census.as_dict(), indent=2, ensure_ascii=False) + "\n")


MOVED_IOU = 0.5
"""Sobreposição a partir da qual um sumiço e um surgimento na mesma página são **o mesmo
diagrama que mudou de caixa**, e não uma perda mais um ganho.

O número não precisa ser fino porque as duas situações não se parecem: um recorte que se
reajusta guarda 0,6--0,9 do próprio corpo, e dois diagramas distintos da mesma página não se
tocam."""


def _row_iou(a: CandidateRow, b: CandidateRow) -> float:
    largura = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    altura = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = largura * altura
    if inter <= 0:
        return 0.0
    uniao = (a.x1 - a.x0) * (a.y1 - a.y0) + (b.x1 - b.x0) * (b.y1 - b.y0) - inter
    return inter / uniao if uniao > 0 else 0.0


@dataclass
class CensusDiff:
    """O que mudou entre duas corridas, por livro.

    **`lost` é a coluna perigosa.** Toda entrega da Fase de detecção vai matar candidato de
    propósito, e a pergunta que decide se a mudança presta não é "quantos sumiram" e sim
    "quantos dos que sumiram eram diagrama de verdade". Por isso o diff separa o que sumiu
    abaixo do limiar de suspeita (esperado) do que sumiu acima dele (é o que se vai olhar a
    olho, um por um).

    **E `moved` existe porque a primeira versão não o tinha.** A S-81 uniu ladrilhos e o
    candidato resultante ficou com outro canto; o diff leu 26 "perdas acima do limiar" no
    `GALLAGHER` onde havia **um diagrama por página, reajustado**. Um instrumento que grita
    perda a cada reajuste de caixa é um instrumento que ninguém vai olhar na terceira vez.
    """

    pdf: str
    gained: list[CandidateRow] = field(default_factory=list)
    lost: list[CandidateRow] = field(default_factory=list)
    moved: list[tuple[CandidateRow, CandidateRow]] = field(default_factory=list)
    """Pares (antes, depois) do mesmo diagrama com caixa diferente."""

    suspect_below_pt: float = SUSPECT_BELOW_PT

    @property
    def lost_suspects(self) -> list[CandidateRow]:
        return [row for row in self.lost if row.side_pt < self.suspect_below_pt]

    @property
    def lost_real(self) -> list[CandidateRow]:
        """Candidatos grandes que sumiram **de verdade**. Cada um precisa de justificativa."""
        return [row for row in self.lost if row.side_pt >= self.suspect_below_pt]

    @property
    def changed(self) -> bool:
        return bool(self.gained or self.lost or self.moved)


def diff_census(
    baseline: list[CandidateRow],
    current: list[CandidateRow],
    *,
    suspect_below_pt: float = SUSPECT_BELOW_PT,
    moved_iou: float = MOVED_IOU,
) -> list[CensusDiff]:
    """Compara duas corridas por `CandidateRow.key`, e não por índice.

    Casar por índice faria toda remoção parecer remoção mais substituição, porque o índice é
    a posição na ordem de leitura e ela se fecha quando um candidato sai. O canto do `bbox` é
    estável: ou o candidato está lá, ou não está.

    **Segundo passe: o que sobrou casa por sobreposição** (`moved`). O canto é estável entre
    corridas que não mexem no recorte, e deixa de ser assim que uma entrega reajusta a caixa
    -- que é o caso da S-81. Sem este passe, cada diagrama reajustado aparece como uma perda
    e um ganho, e a coluna que decide (`acima do limiar`) enche de ruído.
    """
    antes = {row.key: row for row in baseline}
    depois = {row.key: row for row in current}

    livros = sorted({row.pdf for row in baseline} | {row.pdf for row in current})
    resultado: list[CensusDiff] = []
    for pdf in livros:
        mudanca = CensusDiff(pdf=pdf, suspect_below_pt=suspect_below_pt)
        sumiram = sorted(
            (row for key, row in antes.items() if key[0] == pdf and key not in depois),
            key=lambda r: (r.page, r.index),
        )
        surgiram = sorted(
            (row for key, row in depois.items() if key[0] == pdf and key not in antes),
            key=lambda r: (r.page, r.index),
        )

        # Guloso pelo melhor par: a alternativa exata nao muda nenhuma decisao aqui, porque
        # dois candidatos da mesma pagina que disputassem o mesmo par ja se sobreporiam entre
        # si -- e o detector nunca entrega dois assim (o proprio `detect_boards` desduplica).
        disponiveis = list(surgiram)
        for perdido in sumiram:
            melhor, melhor_iou = None, moved_iou
            for candidato in disponiveis:
                if candidato.page != perdido.page:
                    continue
                iou = _row_iou(perdido, candidato)
                if iou >= melhor_iou:
                    melhor, melhor_iou = candidato, iou
            if melhor is None:
                mudanca.lost.append(perdido)
            else:
                disponiveis.remove(melhor)
                mudanca.moved.append((perdido, melhor))

        mudanca.gained = disponiveis
        if mudanca.changed:
            resultado.append(mudanca)
    return resultado
