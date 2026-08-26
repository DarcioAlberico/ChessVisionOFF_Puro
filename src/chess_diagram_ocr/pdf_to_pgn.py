from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import chess.pgn
import numpy as np

from .checkpoint import checkpoint_identity
from .config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
    PROJECT_ROOT,
    OrientationMode,
    ReadingOrder,
)
from .export_checkpoint import (
    DEFAULT_CHECKPOINT_EVERY,
    CheckpointWriter,
    ScanParams,
    load_partial,
    partial_path_for,
)
from .fen_utils import check_position
from .gallery import DiagramAnnotation, lichess_analysis_url, load_annotations
from .inference import BoardPrediction, load_model, predict_with_orientation
from .pdf_io import PdfSource as _PdfSource
from .pdf_text import DiagramContext
from .semantics import SideToMove, compose_fen, infer_castling_rights, infer_side_to_move

if TYPE_CHECKING:
    from .detection import DiagramCandidate

logger = logging.getLogger(__name__)

PdfSource = _PdfSource
"""Reexportado de `pdf_io`, e agora com o `OpenPdf` da S-61 dentro: uma varredura abre o
documento uma vez e passa o objeto adiante, em vez de um caminho que cada etapa reabre.

O nome continua aqui porque é por ele que dezenas de assinaturas deste módulo passam, e
trocá-lo por um import direto em cada uma não compraria nada."""
ProgressCallback = Callable[[int, int, int, int], None]
PageCallback = Callable[[int, list["DiagramPosition"]], None]
"""Chamado ao fim de cada página com (índice, posições daquela página). Ver S-24."""

MAX_CAPTION_HEADER = 300
"""Corte da legenda no header do PGN. Header não quebra linha, e comentário inteiro não cabe."""


@dataclass(frozen=True)
class DiagramPosition:
    page_index: int
    diagram_index: int
    fen: str
    """Campo de peças, sem lado a jogar. Ver `full_fen` para a FEN que vai ao PGN."""

    confidence: float
    """Confiança média das 64 casas. Mantida por compatibilidade; ver `min_confidence`."""

    min_confidence: float | None = None
    """Confiança da casa mais insegura (S-10). `None` em posições montadas à mão."""

    is_legal: bool | None = None
    """Legal exatamente como está escrita, lado a jogar incluído (S-05).

    `None` quando não foi avaliada."""

    is_fatal: bool | None = None
    """Viola uma regra que não depende do lado a jogar: erro real de reconhecimento.

    A distinção importa e não é sutil. Um diagrama de livro não diz de quem é a vez, e o
    export assume brancas; se as pretas estiverem em xeque, a posição sai como "ilegal"
    sendo que o tabuleiro está perfeito -- errado é o palpite do lado a jogar. Descartar
    esse caso jogaria fora leitura boa. Só `is_fatal` significa "o modelo leu errado".
    """

    problems: tuple[str, ...] = ()
    """Descrições dos problemas de legalidade, quando houver."""

    rotation: int | None = None
    """Orientação usada para ler o diagrama, em graus (S-13). `None` se não foi decidida."""

    orientation_ambiguous: bool = False
    """As duas orientações eram plausíveis. O diagrama pode estar de cabeça para baixo."""

    orientation_reason: str = ""
    """Por que esta orientação venceu -- só interessa quando `orientation_ambiguous`."""

    side_to_move: SideToMove | None = None
    """De quem é a vez e de onde veio a resposta (S-16/S-17). `None` = não foi decidido."""

    context: DiagramContext | None = None
    """O que a camada de texto do PDF diz sobre este diagrama (S-16)."""

    detection_source: str | None = None
    """`embedded` ou `contour` (S-12). Vai para o PGN: leitura ruim costuma ter fonte em comum."""

    duplicate_of: tuple[int, int] | None = None
    """(página, diagrama) da primeira ocorrência desta mesma posição no PDF (S-18)."""

    @property
    def full_fen(self) -> str:
        """A FEN que vai para o PGN, com o lado a jogar decidido e o roque inferido.

        Antes da Fase 3 isto era `f"{fen} w - - 0 1"` -- o ponto exato onde metade dos
        exercícios de um livro de táticas passava a mentir. Sem lado decidido o padrão
        continua sendo brancas, porque uma FEN precisa de um: a diferença é que agora o PGN
        registra em `[SideToMoveSource]` que aquilo foi assumido.
        """
        if self.side_to_move is None:
            return _normalize_fen_for_pgn(self.fen)
        return compose_fen(self.fen, self.side_to_move)

    def annotated_fen(self, annotation: DiagramAnnotation | None) -> str:
        """`full_fen` com o que a pessoa declarou na galeria por cima (S-67).

        A anotação **vence** a dedução, e é essa a razão de ela existir: quem abriu a galeria
        e digitou "pretas" está corrigindo o palpite da S-17, não o reforçando. O que a
        anotação não declara continua vindo do pipeline.
        """
        if annotation is None or (annotation.side_to_move is None and annotation.move_number is None):
            return self.full_fen

        lado = self.annotated_side_to_move(annotation)
        if lado is None:
            lado = SideToMove(color=chess.WHITE, source="default")
        return compose_fen(self.fen, lado, fullmove=annotation.move_number or 1)

    def annotated_side_to_move(self, annotation: DiagramAnnotation | None) -> SideToMove | None:
        """O lado que vai ao header, já com a declaração da galeria por cima (S-67).

        **`"manual"` só quando foi mesmo uma pessoa.** Depois da S-72 a galeria também é
        preenchida pela base de partidas, e marcar aquilo como declarado à mão seria dizer que
        alguém conferiu -- exatamente o tipo de procedência inventada que a Fase 3 existe para
        eliminar. Quando o campo veio da base, o header diz `database` e carrega a partida.
        """
        if annotation is None or annotation.side_to_move is None:
            return self.side_to_move
        da_base = "side_to_move" in annotation.filled_fields
        return SideToMove(
            color=chess.WHITE if annotation.side_to_move == "w" else chess.BLACK,
            source="database" if da_base else "manual",
            reason=f"casou com {annotation.filled_from}" if da_base else "declarado na galeria",
        )

    @property
    def needs_side_to_move_flip(self) -> bool:
        """A posição só não fecha por causa do lado a jogar assumido (S-17)."""
        return self.is_legal is False and self.is_fatal is False

    @property
    def legality_label(self) -> str:
        """Como a legalidade aparece no PGN: três estados, não dois."""
        if self.is_legal is None:
            return "nao-avaliada"
        if self.is_legal:
            return "legal"
        return "lado-a-jogar" if self.is_fatal is False else "ilegal"

    @property
    def page_number(self) -> int:
        return self.page_index + 1


Verdict = Literal["accepted", "needs_review", "rejected"]


@dataclass(frozen=True)
class ExportReport:
    """Resultado de uma exportação, com cada posição em um dos três destinos (S-15).

    Antes disso o export escrevia tudo no mesmo arquivo, inclusive posições ilegais: o
    usuário só descobria ao abrir o PGN num visualizador que reclamava -- e não tinha como
    saber quais dos 300 diagramas eram os ruins.
    """

    accepted: list[DiagramPosition]
    """Legais e confiantes. Vão para o PGN principal."""

    needs_review: list[tuple[DiagramPosition, str]]
    """Legais, mas com alguma casa insegura. Vão para o `.review.pgn` com o motivo."""

    rejected: list[tuple[DiagramPosition, str]]
    """Ilegais mesmo depois da decodificação restrita (S-11), ou tabuleiro vazio.

    Também vão para o `.review.pgn`, e não para o lixo: uma posição ilegal costuma estar a
    uma casa da correta, e é justamente o que vale a pena corrigir à mão. O que a S-15
    exige é que o PGN **principal** saia limpo, não que o diagrama desapareça.
    """

    pages_scanned: int
    output_path: Path
    review_path: Path | None
    """`None` quando nada precisou de revisão -- nesse caso o arquivo não é criado."""

    duplicates: list[DiagramPosition] = field(default_factory=list)
    """Repetições omitidas sob `--dedupe` (S-18). Vazio quando a opção está desligada.

    Existem como lista, e não como contador, pela mesma razão da S-15: o usuário precisa
    poder ver o que não entrou no arquivo.
    """

    cancelled: bool = False
    """A varredura foi interrompida (S-24). O PGN sai com o que deu tempo de ler."""

    partial_path: Path | None = None
    """Checkpoint que sobreviveu, quando cancelado. `None` quando a exportação terminou."""

    resumed_from_page: int | None = None
    """Página em que esta execução retomou um parcial anterior. `None` = varredura nova."""

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.needs_review) + len(self.rejected) + len(self.duplicates)

    @property
    def review_items(self) -> list[tuple[DiagramPosition, str]]:
        """Tudo que precisa de olho humano, na ordem em que foi encontrado no PDF."""
        items = self.needs_review + self.rejected
        return sorted(items, key=lambda item: (item[0].page_index, item[0].diagram_index))

    def summary(self) -> str:
        duplicates = f", {len(self.duplicates)} duplicados" if self.duplicates else ""
        suffix = " (cancelada)" if self.cancelled else ""
        return (
            f"{len(self.accepted)} aceitos, {len(self.needs_review)} para revisão, "
            f"{len(self.rejected)} rejeitados{duplicates} em {self.pages_scanned} páginas{suffix}"
        )


def classify_position(
    position: DiagramPosition,
    *,
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
) -> tuple[Verdict, str]:
    """Destino de uma posição na exportação, com o motivo em texto.

    Campos não medidos (`None`) não condenam a posição: `DiagramPosition` também é usada
    para posições montadas à mão, e afirmar "ilegal" sem ter verificado seria pior que não
    afirmar nada.
    """
    if position.is_fatal:
        problems = "; ".join(position.problems) or "posição ilegal"
        return "rejected", f"ilegal: {problems}"

    # Orientação antes de tudo o mais: uma casa insegura custa uma correção, um diagrama de
    # cabeça para baixo custa o diagrama inteiro. É o aviso mais urgente que o gate pode dar.
    if position.orientation_ambiguous:
        detalhe = position.orientation_reason or "as duas orientações eram plausíveis"
        return "needs_review", f"orientação incerta: {detalhe}"

    side = position.side_to_move
    if side is not None and side.conflicting:
        # O texto do PDF e a posicao discordam. A posicao venceu (ver `infer_side_to_move`),
        # entao o que sai e legal -- mas uma das duas fontes esta errada, e as duas causas
        # possiveis merecem olho humano: casa lida errado, ou legenda do diagrama vizinho.
        return "needs_review", f"texto e posição discordam do lado a jogar: {side.reason}"

    if position.needs_side_to_move_flip:
        # Leitura provavelmente boa, palpite de lado a jogar ruim. Antes da S-17 todo diagrama
        # com xeque invertido caia aqui; agora a legalidade resolve esses -- o que sobra sao
        # posicoes ilegais das *duas* formas, que nenhuma escolha de lado a jogar conserta.
        return "needs_review", "lado a jogar assumido errado: " + ("; ".join(position.problems) or "xeque invertido")

    if position.min_confidence is not None and position.min_confidence < accept_threshold:
        return "needs_review", f"confiança mínima {position.min_confidence:.3f} < {accept_threshold:.2f}"

    return "accepted", ""


def partition_positions(
    positions: Iterable[DiagramPosition],
    *,
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
) -> tuple[list[DiagramPosition], list[tuple[DiagramPosition, str]], list[tuple[DiagramPosition, str]]]:
    accepted: list[DiagramPosition] = []
    needs_review: list[tuple[DiagramPosition, str]] = []
    rejected: list[tuple[DiagramPosition, str]] = []

    for position in positions:
        verdict, reason = classify_position(position, accept_threshold=accept_threshold)
        if verdict == "accepted":
            accepted.append(position)
        elif verdict == "needs_review":
            needs_review.append((position, reason))
        else:
            rejected.append((position, reason))

    return accepted, needs_review, rejected


def review_output_path(output_path: Path) -> Path:
    """`PGN/livro.pgn` -> `PGN/livro.review.pgn`."""
    output_path = Path(output_path)
    return output_path.with_suffix(f".review{output_path.suffix}")


def _normalize_fen_for_pgn(fen: str) -> str:
    normalized = fen.strip()
    if " " not in normalized:
        return f"{normalized} w - - 0 1"
    return normalized


_OCR_SOURCES = frozenset({"ocr", "ocr-page-scope", "glifo", "glifo-page-scope"})
"""Procedências em que o lado a jogar foi lido por um motor, e não do arquivo (S-43, S-207).

São as únicas em que `[SideToMoveConfidence]` significa alguma coisa.

**As duas do `glifo` entraram junto com o valor, e não depois.** O classificador devolve confiança
por caractere e a legenda sai com a mínima delas -- é exatamente o número que este header existe
para carregar. Deixá-las de fora faria a leitura de casa sair sem a régua que a de terceiros tem,
que é o contrário do que a S-207 pede: `[SideToMoveConfidence]` ao lado quando houve dúvida."""


def _flatten_caption(caption: str) -> str:
    """Legenda em uma linha e sem aspas: header de PGN não quebra linha nem escapa aspas."""
    flat = " / ".join(line.strip() for line in caption.splitlines() if line.strip())
    flat = flat.replace('"', "'")
    if len(flat) > MAX_CAPTION_HEADER:
        flat = flat[: MAX_CAPTION_HEADER - 1].rstrip() + "…"
    return flat


def mark_duplicates(positions: Iterable[DiagramPosition]) -> list[DiagramPosition]:
    """Anota cada repetição de uma mesma posição apontando para a primeira ocorrência (S-18).

    Repetição é comum e legítima: livro de exercícios reimprime o diagrama na página de
    solução, e coleção de finais reusa a mesma posição em capítulos diferentes. Por isso o
    padrão é **anotar**, não remover -- a remoção fica no `--dedupe`, que é decisão de quem
    exporta e não do exportador.

    O critério é a colocação das peças, não a FEN completa: a mesma posição com lados a
    jogar diferentes é o mesmo diagrama impresso duas vezes, e é justamente esse par que
    interessa ver.
    """
    first_seen: dict[str, tuple[int, int]] = {}
    marked: list[DiagramPosition] = []
    for position in positions:
        key = position.fen.strip().split(" ")[0]
        origin = first_seen.get(key)
        if origin is None:
            first_seen[key] = (position.page_number, position.diagram_index)
            marked.append(position)
        else:
            marked.append(replace(position, duplicate_of=origin))
    return marked


def _opened(pdf_source: PdfSource) -> Any:
    """Indireção pelo mesmo motivo das três abaixo: deixar os testes trocarem o pipeline.

    Ver `pdf_io.opened_or_source` sobre por que não levantar aqui.
    """
    from .pdf_io import opened_or_source

    return opened_or_source(pdf_source)


def _get_pdf_page_count(pdf_source: PdfSource) -> int:
    from .pdf_io import get_pdf_page_count

    return get_pdf_page_count(pdf_source)


def _render_pdf_page(pdf_source: PdfSource, page_index: int, dpi: int) -> np.ndarray:
    # Indirecao mantida para permitir mock nos testes sem tocar em pdf_io.
    from .pdf_io import render_pdf_page

    return render_pdf_page(pdf_source, page_index, dpi=dpi)


def _detect_page_diagrams(
    pdf_source: PdfSource,
    page_index: int,
    page_rgb: np.ndarray,
    *,
    max_boards: int,
    reading_order: ReadingOrder,
) -> list[DiagramCandidate]:
    """Candidatos a diagrama da página, pelo detector híbrido (S-12).

    Devolve o candidato inteiro, e não só `board_rgb`: o `bbox_pdf` que ele carrega é o que
    a S-16 usa para achar a legenda, e a `source` vai para o header `[DetectionSource]`.

    Indireção pelo mesmo motivo de `_render_pdf_page`: deixar os testes trocarem a detecção
    sem precisar de PDF de verdade.
    """
    from .detection import detect_diagrams_in_pdf_page

    return detect_diagrams_in_pdf_page(
        pdf_source,
        page_index,
        page_rgb,
        max_boards=max_boards,
        reading_order=reading_order,
    )


def _page_contexts(
    pdf_source: PdfSource,
    page_index: int,
    bboxes: Sequence[tuple[float, float, float, float]],
    caption_reader: Any = None,
) -> list[DiagramContext]:
    """Contexto textual de cada diagrama da página (S-16). Mesma indireção dos anteriores."""
    from .pdf_text import contexts_for_pdf_page

    return contexts_for_pdf_page(pdf_source, page_index, bboxes, caption_reader=caption_reader)


@dataclass(frozen=True, eq=False)
class ScannedDiagram:
    """Um diagrama lido, com tudo o que a varredura produziu sobre ele.

    Existe porque a S-22 precisa do que a `DiagramPosition` deliberadamente joga fora: a
    matriz de probabilidades por casa (para ordenar a fila por incerteza) e a imagem do
    recorte (para a miniatura). Manter os dois na `DiagramPosition` custaria ~6 KB e uma
    imagem por diagrama em toda exportação, que não usa nenhum dos dois.
    """

    position: DiagramPosition
    prediction: BoardPrediction
    board_rgb: np.ndarray
    detector_score: float


def iter_pdf_diagrams(
    pdf_source: PdfSource,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = 220,
    max_boards_per_page: int = DEFAULT_MAX_BOARDS,
    orientation: OrientationMode = DEFAULT_ORIENTATION_MODE,
    device: str | None = None,
    start_page: int = 0,
    end_page: int | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    read_text: bool = True,
    caption_reader: Any = None,
    cancel_event: threading.Event | None = None,
    progress_callback: ProgressCallback | None = None,
    page_callback: PageCallback | None = None,
    model_session: AbstractContextManager[tuple[Any, str]] | None = None,
) -> Iterator[ScannedDiagram]:
    """Gerador de diagramas do PDF, uma página por vez.

    É o laço que `scan_pdf_positions` sempre teve, extraído para que a fila de revisão
    (S-22) não precise reimplementá-lo. Duas implementações do mesmo pipeline divergiriam
    -- e foi exatamente isso que a S-14 teve de corrigir entre a GUI e a exportação.

    `cancel_event` é conferido **antes** de cada página, e não dentro da inferência: uma
    página a 220 DPI leva ~0,18 s, então o pior caso de resposta ao cancelamento é isso.

    `caption_reader` é o `ocr_caption.CaptionReader` da S-43, e `None` -- o padrão -- é o
    projeto inteiro como sempre foi: só a camada de texto. Ele só entra onde a camada cala,
    e vale para os 7 livros do acervo que não têm camada nenhuma. `Any` na assinatura, e não
    o tipo, para que este módulo não passe a importar o extra opcional de OCR.

    `model_session` é o empréstimo do modelo do `OcrService`, com o lock da S-31 segurado
    pela duração da varredura (S-57). Sem ele, esta função carregava o `.pt` por conta
    própria -- e o `ARCHITECTURE.md` afirmava que o modelo ficava "sob lock durante o uso",
    o que valia para o OCR interativo de uma página e **não** para os dois caminhos longos
    que de fato coexistem com um treino: a exportação de um livro e a varredura da fila. O
    treino reescreve o mesmo arquivo que estes leem.

    Continua aceitando `None`, que é o caminho dos CLIs: ali não há serviço, não há treino
    concorrente, e exigir um seria inventar acoplamento para resolver um problema que não
    existe fora da interface.
    """
    # Uma abertura por varredura, e nao tres por pagina (S-61). No `Yusupov` sao 225,7 s de
    # parsing de xref que deixam de acontecer; no `Polgar`, 4,1 s -- e e por isso que o
    # docstring antigo achava a conta irrelevante: ele olhou o livro errado.
    #
    # A contagem de paginas fica **dentro** do `with`, e nao antes dele: fora, ela era a
    # unica abertura que sobrava, e uma sobrando derrota o proposito do item num livro que
    # a varredura abre uma vez.
    with _opened(pdf_source) as documento:
        page_count = _get_pdf_page_count(documento)
        if page_count <= 0:
            return

        if start_page < 0 or start_page >= page_count:
            raise ValueError(f"start_page {start_page} fora do intervalo 0..{page_count - 1}")

        last_page_exclusive = page_count if end_page is None else min(end_page, page_count)
        if last_page_exclusive <= start_page:
            raise ValueError("end_page deve ser maior que start_page.")
        total_pages = last_page_exclusive - start_page

        with model_session or _own_model_session(Path(model_path), device) as (model, resolved_device):
            yield from _scan_pages(
                documento,
                model,
                resolved_device,
                start_page=start_page,
                last_page_exclusive=last_page_exclusive,
                total_pages=total_pages,
                dpi=dpi,
                max_boards_per_page=max_boards_per_page,
                orientation=orientation,
                reading_order=reading_order,
                read_text=read_text,
                caption_reader=caption_reader,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
                page_callback=page_callback,
            )


@contextmanager
def _own_model_session(model_path: Path, device: str | None) -> Iterator[tuple[Any, str]]:
    """Carrega o modelo só para esta varredura. É o caminho dos CLIs -- ver `iter_pdf_diagrams`."""
    yield load_model(model_path, device=device)


def _scan_pages(
    pdf_source: PdfSource,
    model: Any,
    resolved_device: str,
    *,
    start_page: int,
    last_page_exclusive: int,
    total_pages: int,
    dpi: int,
    max_boards_per_page: int,
    orientation: OrientationMode,
    reading_order: ReadingOrder,
    read_text: bool,
    caption_reader: Any,
    cancel_event: threading.Event | None,
    progress_callback: ProgressCallback | None,
    page_callback: PageCallback | None,
) -> Iterator[ScannedDiagram]:
    """O laço de páginas, com o modelo já em mãos. Separado só para manter o `with` legível."""
    seen = 0

    for page_index in range(start_page, last_page_exclusive):
        if cancel_event is not None and cancel_event.is_set():
            logger.info("Varredura cancelada antes da página %d.", page_index + 1)
            return

        page_rgb = _render_pdf_page(pdf_source, page_index, dpi=dpi)
        candidates = _detect_page_diagrams(
            pdf_source,
            page_index,
            page_rgb,
            max_boards=max_boards_per_page,
            reading_order=reading_order,
        )
        contexts = (
            _page_contexts(pdf_source, page_index, [c.bbox_pdf for c in candidates], caption_reader)
            if read_text
            else []
        )

        page_positions: list[DiagramPosition] = []
        for diagram_index, candidate in enumerate(candidates, start=1):
            oriented = predict_with_orientation(
                candidate.board_rgb,
                model,
                resolved_device,
                mode=orientation,
            )
            prediction = oriented.prediction
            context = contexts[diagram_index - 1] if diagram_index - 1 < len(contexts) else None
            side = infer_side_to_move(prediction.fen_board, context)

            # Legalidade re-avaliada com o lado a jogar decidido, e nao com o "w" fixo que a
            # inferencia usou: e o que faz o xeque invertido deixar de ser "ilegal" quando a
            # S-17 descobre que a vez era das pretas.
            resolved = check_position(compose_fen(prediction.fen_board, side))

            position = DiagramPosition(
                page_index=page_index,
                diagram_index=diagram_index,
                fen=prediction.fen_board,
                confidence=prediction.mean_confidence,
                min_confidence=prediction.min_confidence,
                is_legal=resolved.is_legal,
                is_fatal=resolved.is_fatal,
                problems=resolved.problems,
                rotation=oriented.rotation,
                orientation_ambiguous=oriented.ambiguous,
                orientation_reason=oriented.reason,
                side_to_move=side,
                context=context,
                detection_source=candidate.source,
            )
            page_positions.append(position)
            seen += 1
            yield ScannedDiagram(
                position=position,
                prediction=prediction,
                board_rgb=candidate.board_rgb,
                detector_score=candidate.detector_score,
            )

        if page_callback is not None:
            page_callback(page_index, page_positions)
        if progress_callback is not None:
            progress_callback(page_index, total_pages, len(candidates), seen)


def scan_pdf_positions(
    pdf_source: PdfSource,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = 220,
    max_boards_per_page: int = DEFAULT_MAX_BOARDS,
    orientation: OrientationMode = DEFAULT_ORIENTATION_MODE,
    device: str | None = None,
    start_page: int = 0,
    end_page: int | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    read_text: bool = True,
    caption_reader: Any = None,
    cancel_event: threading.Event | None = None,
    progress_callback: ProgressCallback | None = None,
    page_callback: PageCallback | None = None,
    model_session: AbstractContextManager[tuple[Any, str]] | None = None,
) -> list[DiagramPosition]:
    """Varre as páginas e reconhece cada diagrama encontrado.

    `orientation` substituiu o antigo `rotate_180: bool`. A diferença não é só de nome: o
    booleano valia para o PDF inteiro, então um livro que mistura orientações não tinha
    solução. Em `"auto"` cada diagrama decide a sua (S-13).

    `read_text` liga a extração do contexto textual (S-16). Desligar não muda o tabuleiro
    lido -- só faz o lado a jogar cair para a inferência por legalidade e para o padrão.
    `caption_reader` é o OCR da S-43, que só entra onde a camada de texto cala; com
    `read_text=False` ele não roda, porque não há contexto textual nenhum a produzir.

    `cancel_event` interrompe a varredura entre páginas e devolve o que já foi lido (S-24):
    o parcial é justamente o que permite retomar em vez de recomeçar.
    """
    return [
        scanned.position
        for scanned in iter_pdf_diagrams(
            pdf_source,
            model_path,
            dpi=dpi,
            max_boards_per_page=max_boards_per_page,
            orientation=orientation,
            device=device,
            start_page=start_page,
            end_page=end_page,
            reading_order=reading_order,
            read_text=read_text,
            caption_reader=caption_reader,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            page_callback=page_callback,
            model_session=model_session,
        )
    ]


def build_pgn_games(
    positions: Iterable[DiagramPosition],
    *,
    source_name: str,
    event_name: str = "ChessVisionOFF PDF OCR",
    review_reasons: Mapping[tuple[int, int], str] | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    annotations: Mapping[tuple[int, int], DiagramAnnotation] | None = None,
    lichess_links: bool = False,
) -> list[chess.pgn.Game]:
    """Um jogo por posição, só com headers -- o diagrama é a posição inicial.

    `review_reasons`, indexado por (página, diagrama), adiciona o header `[Review]` com o
    motivo pelo qual a posição foi separada. É o que faz o arquivo de revisão dizer *por
    que* cada item está lá em vez de deixar o usuário adivinhar.

    `reading_order` vai para o header porque `[Diagram "2"]` só significa algo junto com a
    ordem em que a página foi numerada (S-14): sem isso, um PGN gerado com outro padrão
    fica impossível de conferir depois.

    `annotations` são as declarações da galeria (S-67), na mesma chave de `review_reasons`.
    Elas **vencem** o que foi inferido -- vez a jogar, número do lance e headers --, porque é
    exatamente para corrigir a inferência que a pessoa abriu a galeria e digitou.

    `lichess_links` é o padrão para os diagramas que **não** declararam nada. Um diagrama que
    declarou `lichess_link=True/False` ignora este padrão: a decisão por diagrama é o pedido
    original da S-67, e um padrão que a atropelasse tornaria a anotação inútil.
    """
    games: list[chess.pgn.Game] = []

    for position in positions:
        context = position.context
        annotation = (annotations or {}).get((position.page_index, position.diagram_index))
        side_to_move = position.annotated_side_to_move(annotation)
        game = chess.pgn.Game()
        game.headers["Event"] = (context.event if context and context.event else None) or event_name
        game.headers["Site"] = "Local"
        game.headers["Round"] = f"{position.page_number}.{position.diagram_index}"
        players = context.players if context and context.players else ("?", "?")
        game.headers["White"], game.headers["Black"] = players
        if context is not None and context.year is not None:
            game.headers["Date"] = f"{context.year}.??.??"
        game.headers["Result"] = "*"
        game.headers["Annotator"] = "ChessVisionOFF"
        game.headers["SetUp"] = "1"
        game.headers["FEN"] = position.annotated_fen(annotation)
        game.headers["SourcePDF"] = source_name
        game.headers["Page"] = str(position.page_number)
        game.headers["Diagram"] = str(position.diagram_index)
        game.headers["ReadingOrder"] = reading_order
        game.headers["OCRConfidence"] = f"{position.confidence:.3f}"

        if side_to_move is not None:
            game.headers["SideToMove"] = side_to_move.label
            game.headers["SideToMoveSource"] = side_to_move.source
            # So quando quem decidiu foi o OCR (S-43). Escrever a confianca de uma decisao
            # de legalidade -- que pode ter derrubado uma leitura de OCR de 0,55 -- diria
            # que a resposta gravada vale 0,55, e ela nao veio de la. E 1,0 em todo jogo de
            # um livro com camada de texto e ruido que ensina a ignorar o header.
            if side_to_move.source in _OCR_SOURCES and context is not None:
                game.headers["SideToMoveConfidence"] = f"{context.side_to_move_confidence:.3f}"
            if infer_castling_rights(position.fen) != "-":
                # So quando ha o que declarar: escrever a proveniencia de um "-" nao informa
                # nada e enche o header de ruido.
                game.headers["CastlingSource"] = "inferred"
        if context is not None:
            if context.exercise_number is not None:
                game.headers["ExerciseNumber"] = str(context.exercise_number)
            if context.caption:
                game.headers["Caption"] = _flatten_caption(context.caption)
        if position.detection_source is not None:
            game.headers["DetectionSource"] = position.detection_source
        if position.duplicate_of is not None:
            page_number, diagram_index = position.duplicate_of
            game.headers["DuplicateOf"] = f"{page_number}.{diagram_index}"
        if position.min_confidence is not None:
            game.headers["OCRMinConfidence"] = f"{position.min_confidence:.3f}"
        if position.is_legal is not None:
            game.headers["OCRLegality"] = position.legality_label
            if not position.is_legal and position.problems:
                game.headers["OCRProblems"] = "; ".join(position.problems)
        if position.rotation is not None:
            # Registrado sempre, e nao so quando girou: sem isso nao ha como saber depois se
            # a leitura de um diagrama suspeito foi feita de pe ou de cabeca para baixo.
            game.headers["OCRRotation"] = str(position.rotation)

        reason = (review_reasons or {}).get((position.page_index, position.diagram_index))
        if reason:
            game.headers["Review"] = reason

        if annotation is not None:
            # Por ultimo, e de proposito: o que a pessoa escreveu na galeria vence tudo que
            # foi inferido acima. `RESERVED_HEADERS` ja tirou `FEN`, `SetUp` e `Result` da
            # jogada -- aqueles mudam pelos campos proprios, que sabem recompor a posicao.
            for nome, valor in annotation.headers.items():
                game.headers[nome] = valor
            if annotation.filled_from:
                # A evidencia do casamento (S-72). Sem ela, `[White "Ljubojevic, Ljubomir"]`
                # num PGN nao diz se alguem digitou aquilo ou se as 64 casas bateram com uma
                # partida registrada -- e as duas coisas valem muito diferente.
                game.headers["GameSource"] = annotation.filled_from

        quer_link = annotation.lichess_link if annotation is not None else None
        if quer_link is None:
            quer_link = lichess_links
        if quer_link:
            # Comentario, e nao header: o link e para uma pessoa clicar, e leitor de PGN
            # mostra comentario junto do diagrama. Header seria metadado de maquina.
            game.comment = lichess_analysis_url(game.headers["FEN"])

        games.append(game)

    return games


def build_pgn_text(
    positions: Iterable[DiagramPosition],
    *,
    source_name: str,
    event_name: str = "ChessVisionOFF PDF OCR",
    review_reasons: Mapping[tuple[int, int], str] | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    annotations: Mapping[tuple[int, int], DiagramAnnotation] | None = None,
    lichess_links: bool = False,
) -> str:
    payloads = [
        game.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True)).strip()
        for game in build_pgn_games(
            positions,
            source_name=source_name,
            event_name=event_name,
            review_reasons=review_reasons,
            reading_order=reading_order,
            annotations=annotations,
            lichess_links=lichess_links,
        )
    ]
    return "\n\n".join(payload for payload in payloads if payload).strip()


def write_gated_pgn(
    positions: Iterable[DiagramPosition],
    output_path: Path,
    *,
    source_name: str,
    event_name: str = "ChessVisionOFF PDF OCR",
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    pages_scanned: int = 0,
    dedupe: bool = False,
    cancelled: bool = False,
    partial_path: Path | None = None,
    resumed_from_page: int | None = None,
    annotations: Mapping[tuple[int, int], DiagramAnnotation] | None = None,
    lichess_links: bool = False,
) -> ExportReport:
    """Escreve o PGN principal só com o que passou no gate, e o resto no `.review.pgn`.

    `dedupe` omite do PGN principal as repetições de uma posição já exportada. Elas ficam
    no relatório, em `report.duplicates`: sem `dedupe` o header `[DuplicateOf]` já diz qual
    é qual, e com `dedupe` o que sumiu do arquivo continua nomeado em algum lugar.

    As anotações da galeria (S-67) vão para os **dois** arquivos. O `.review.pgn` é o que a
    pessoa vai abrir para consertar, e mandá-lo sem o lance e a vez que ela já declarou faria
    o arquivo de revisão contradizer a galeria justamente onde ela trabalhou.
    """
    marked = mark_duplicates(positions)
    duplicates: list[DiagramPosition] = []
    if dedupe:
        duplicates = [position for position in marked if position.duplicate_of is not None]
        marked = [position for position in marked if position.duplicate_of is None]

    accepted, needs_review, rejected = partition_positions(marked, accept_threshold=accept_threshold)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_pgn_text(
        accepted,
        source_name=source_name,
        event_name=event_name,
        reading_order=reading_order,
        annotations=annotations,
        lichess_links=lichess_links,
    )
    output_path.write_text(payload + "\n" if payload else "", encoding="utf-8")

    review_items = sorted(
        needs_review + rejected,
        key=lambda item: (item[0].page_index, item[0].diagram_index),
    )
    review_path: Path | None = None
    if review_items:
        review_path = review_output_path(output_path)
        review_payload = build_pgn_text(
            [position for position, _ in review_items],
            source_name=source_name,
            event_name=event_name,
            review_reasons={(position.page_index, position.diagram_index): reason for position, reason in review_items},
            reading_order=reading_order,
            annotations=annotations,
            lichess_links=lichess_links,
        )
        review_path.write_text(review_payload + "\n" if review_payload else "", encoding="utf-8")

    return ExportReport(
        accepted=accepted,
        needs_review=needs_review,
        rejected=rejected,
        pages_scanned=pages_scanned,
        output_path=output_path,
        review_path=review_path,
        duplicates=duplicates,
        cancelled=cancelled,
        partial_path=partial_path,
        resumed_from_page=resumed_from_page,
    )


def save_pdf_positions_to_pgn(
    pdf_source: PdfSource,
    output_path: Path,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = 220,
    max_boards_per_page: int = DEFAULT_MAX_BOARDS,
    orientation: OrientationMode = DEFAULT_ORIENTATION_MODE,
    device: str | None = None,
    start_page: int = 0,
    end_page: int | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    event_name: str = "ChessVisionOFF PDF OCR",
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    read_text: bool = True,
    caption_reader: Any = None,
    dedupe: bool = False,
    cancel_event: threading.Event | None = None,
    resume: bool = True,
    checkpoint: bool = True,
    checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY,
    progress_callback: ProgressCallback | None = None,
    model_session: AbstractContextManager[tuple[Any, str]] | None = None,
    annotations: Mapping[tuple[int, int], DiagramAnnotation] | None = None,
    lichess_links: bool = False,
) -> ExportReport:
    """Varre o PDF e exporta com o gate de qualidade da S-15.

    Devolve o `ExportReport` -- antes devolvia a lista de posições. O relatório é o que
    permite ao chamador dizer quantas foram para revisão e por quê; a lista continua
    acessível em `report.accepted` e companhia.

    `cancel_event` e `checkpoint` implementam a S-24. Cancelar não descarta trabalho: o
    `.partial.jsonl` fica ao lado do PGN e a execução seguinte com **os mesmos parâmetros**
    retoma da página seguinte à última concluída. Terminar apaga o parcial -- ele existe
    para atravessar a interrupção, não para virar um segundo formato de saída.

    "Os mesmos parâmetros" inclui **o mesmo arquivo de modelo**, e não só o mesmo caminho
    (S-57): o treino reescreve sempre o `models/piece_classifier.pt`, e retomar depois de
    treinar juntaria metade de um PGN lido por um modelo com metade lida por outro.

    `model_session` empresta o modelo do `OcrService` em vez de carregar outro -- ver
    `iter_pdf_diagrams`.

    `annotations` normalmente fica em `None`: as declarações da galeria (S-67) são carregadas
    do `data/gallery/<livro>.json` aqui dentro. Passá-las explicitamente serve a teste e a
    quem exporta a partir de bytes, que não têm nome de arquivo para procurar.
    """
    source_name = Path(pdf_source).name if isinstance(pdf_source, (str, Path)) else "pdf-bytes"

    params = ScanParams(
        source_name=source_name,
        model_path=str(Path(model_path)),
        # O caminho e sempre o mesmo `models/piece_classifier.pt`; o arquivo, nao (S-57).
        model_identity=checkpoint_identity(Path(model_path)),
        dpi=dpi,
        max_boards_per_page=max_boards_per_page,
        orientation=orientation,
        reading_order=reading_order,
        read_text=read_text,
        # Retomar com OCR o que comecou sem ele misturaria duas procedencias no mesmo PGN
        # (S-43), pelo mesmo motivo que `model_identity` existe.
        ocr_engine=getattr(caption_reader, "name", "") if caption_reader is not None else "",
        start_page=start_page,
        end_page=end_page,
    )
    partial_path = partial_path_for(Path(output_path))
    partial = load_partial(partial_path, params) if resume else None

    positions: list[DiagramPosition] = list(partial.positions) if partial is not None else []
    pages_seen = partial.pages_done if partial is not None else 0
    scan_start = partial.resume_from if partial is not None else start_page
    resumed_from_page = partial.resume_from if partial is not None else None
    if partial is not None:
        logger.info(
            "Retomando exportação de %s na página %d (%d posições já lidas).",
            source_name,
            scan_start + 1,
            len(positions),
        )

    writer = CheckpointWriter(partial_path, params, every=checkpoint_every, resumed=partial is not None)

    def _on_page(page_index: int, page_positions: list[DiagramPosition]) -> None:
        nonlocal pages_seen
        pages_seen += 1
        if checkpoint:
            writer.record_page(page_index, page_positions)

    # A contagem de paginas so e necessaria quando retomamos: sem parcial, `scan_start` e o
    # `start_page` que a propria varredura ja valida, e abrir o documento aqui seria custo
    # (e uma dependencia de I/O) por nada.
    should_scan = True
    if partial is not None:
        page_count = _get_pdf_page_count(pdf_source)
        last_page_exclusive = page_count if end_page is None else min(end_page, page_count)
        should_scan = scan_start < last_page_exclusive

    if should_scan:
        positions.extend(
            scan_pdf_positions(
                pdf_source=pdf_source,
                model_path=model_path,
                dpi=dpi,
                max_boards_per_page=max_boards_per_page,
                orientation=orientation,
                device=device,
                start_page=scan_start,
                end_page=end_page,
                reading_order=reading_order,
                read_text=read_text,
                caption_reader=caption_reader,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
                page_callback=_on_page,
                model_session=model_session,
            )
        )

    cancelled = cancel_event is not None and cancel_event.is_set()
    if checkpoint:
        writer.flush()
        if not cancelled:
            writer.discard()

    # As anotacoes da galeria (S-67) sao carregadas aqui, e nao pedidas ao chamador: elas
    # pertencem ao livro, e ter de passa-las em toda chamada faria a GUI exportar com elas e
    # a CLI sem -- dois PGNs diferentes do mesmo PDF, que e o defeito que a S-14 ja corrigiu
    # uma vez na numeracao dos diagramas.
    anotacoes: Mapping[tuple[int, int], DiagramAnnotation] | None = None
    if annotations is None and isinstance(pdf_source, (str, Path)):
        anotacoes = load_annotations(Path(pdf_source), reading_order=reading_order).as_mapping()
    elif annotations is not None:
        anotacoes = annotations

    return write_gated_pgn(
        positions,
        output_path,
        source_name=source_name,
        event_name=event_name,
        accept_threshold=accept_threshold,
        reading_order=reading_order,
        pages_scanned=pages_seen,
        dedupe=dedupe,
        cancelled=cancelled,
        partial_path=partial_path if (cancelled and checkpoint) else None,
        resumed_from_page=resumed_from_page,
        annotations=anotacoes,
        lichess_links=lichess_links,
    )


def default_pgn_output_path(pdf_path: Path) -> Path:
    return PROJECT_ROOT / "PGN" / f"{pdf_path.stem}.pgn"
