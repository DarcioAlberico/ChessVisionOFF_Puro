from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, get_args

import chess.pgn
import numpy as np

from .atomic_io import atomic_write_text
from .checkpoint import checkpoint_identity
from .config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_DPI,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
    PIECE_CLASSES,
    PROJECT_ROOT,
    OrientationMode,
    ReadingOrder,
)
from .cor_por_livro import calibrador_do_livro
from .export_checkpoint import (
    DEFAULT_CHECKPOINT_EVERY,
    CheckpointWriter,
    ScanParams,
    load_partial,
    partial_path_for,
)
from .fen_utils import square_name
from .gallery import DiagramAnnotation, GaleriaDeOutroLivro, lichess_analysis_url, load_annotations
from .inference import BoardPrediction, load_model
from .pdf_io import PdfSource as _PdfSource
from .pdf_text import DiagramContext
from .provenance import hash_board_rgb
from .proveniencia import Cabecalho, chave, hash_do_arquivo, write_sidecar
from .semantics import SideSource, SideToMove, compose_fen, infer_castling_rights

if TYPE_CHECKING:
    from .detection import DiagramCandidate
    from .service import RecognizedDiagram

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

    colour_repairs: tuple[str, ...] = ()
    """As casas (`e5`) cuja cor a tinta contradisse e o calibrador do livro trocou (C5)."""

    next_move: str = ""
    """O primeiro lance impresso sob o diagrama, quando conferido (C11)."""

    next_move_repairs: tuple[str, ...] = ()
    """As casas (`e5`) trocadas para a segunda opção porque só assim o lance impresso replica.
    Vão ao PGN em `[OCRNextMove]`; o gate as julga por `gate_confidence`."""

    stipulation: str = ""
    """A exigência impressa (`#2`), quando a página a tem (C12)."""

    stipulation_closes: bool | None = None
    """`True` fecha, `False` não fecha (nem com trocas), `None` não verificável (C12)."""

    stipulation_keys: tuple[str, ...] = ()
    """A(s) chave(s) em SAN, quando fecha (C12)."""

    stipulation_repairs: tuple[str, ...] = ()
    """As casas (`e5`) trocadas porque só assim a exigência fecha (C12). Vão ao PGN em
    `[OCRStipulation]`; o gate as julga por `gate_confidence`."""

    stipulation_reason: str = ""

    gate_confidence: float | None = None
    """A confiança que o gate julga (C11/C12): `min_confidence` sem as casas provadas pelo lance
    seguinte ou pela exigência. `None` quando não há reparo externo -- e aí o gate usa
    `min_confidence`."""

    bbox_pdf: tuple[float, float, float, float] | None = None
    """Onde o diagrama está na página, em pontos do PDF (A11): a chave geométrica que o A3
    usa para casar a decisão humana com o diagrama."""

    image_hash: str = ""
    """dHash do recorte lido (`provenance.hash_board_rgb`), para reconhecer o mesmo diagrama
    noutra exportação ou noutro livro (A11)."""

    square_confidences: tuple[float, ...] = ()
    """A confiança das 64 casas, em ordem de leitura (A11). Vazio numa posição montada à mão."""

    repairs: tuple[tuple[str, str, str], ...] = ()
    """`(casa, lida, final)` de cada troca do decodificador, da tinta ou do lance (A11)."""

    @classmethod
    def from_recognized(cls, lido: RecognizedDiagram, *, page_index: int) -> DiagramPosition:
        """A posição que vai ao PGN, a partir do que `OcrService.recognize_page` leu (S-833).

        Nada aqui decide: cada campo é o que o reconhecimento já respondeu, na forma do PGN --
        casas por nome (`e5`) em vez de índice, e o diagrama numerado a partir de 1.
        `gate_confidence` é o de `RecognizedDiagram`, e fica `None` quando não houve reparo
        externo, que é o que o header `[OCR...]` sempre disse (o portão julga `min_confidence`).
        """
        prediction = lido.prediction
        decode = prediction.decode if prediction is not None else None
        return cls(
            page_index=page_index,
            diagram_index=lido.index + 1,
            fen=lido.placement,
            confidence=lido.mean_confidence,
            min_confidence=lido.min_confidence,
            bbox_pdf=lido.bbox_pdf,
            image_hash=hash_board_rgb(lido.board_rgb),
            square_confidences=tuple(round(float(c), 4) for c in lido.square_confidences),
            repairs=tuple(
                (square_name(sq), _piece_letter(before), _piece_letter(after))
                for sq, before, after in (decode.changed_squares if decode is not None else [])
            ),
            colour_repairs=tuple(square_name(c) for c in lido.colour_repairs),
            next_move=lido.next_move,
            next_move_repairs=tuple(square_name(c) for c in lido.next_move_repairs),
            stipulation=lido.stipulation,
            stipulation_closes=lido.stipulation_closes,
            stipulation_keys=lido.stipulation_keys,
            stipulation_repairs=tuple(square_name(c) for c in lido.stipulation_repairs),
            stipulation_reason=lido.stipulation_reason,
            gate_confidence=lido.gate_confidence if lido.external_repairs else None,
            is_legal=lido.is_legal,
            is_fatal=lido.is_fatal,
            problems=lido.problems,
            rotation=lido.rotation,
            orientation_ambiguous=lido.orientation_ambiguous,
            orientation_reason=lido.orientation_reason,
            side_to_move=_lado_lido(lido),
            context=lido.context,
            detection_source=lido.detection_source,
        )

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



def _lado_lido(lido: RecognizedDiagram) -> SideToMove:
    """O lado a jogar de volta na forma da `semantics`, de onde `RecognizedDiagram` o tirou.

    A leitura guarda a procedência como texto porque a interface acrescenta as suas
    (`"queue"`); na varredura ela é sempre uma das da `semantics`, e o que não for cai em
    `"default"`, que é a resposta honesta para uma procedência que não se reconhece.
    """
    cor = chess.WHITE if lido.side_to_move == "w" else chess.BLACK
    for fonte in get_args(SideSource):
        if fonte == lido.side_to_move_source:
            return SideToMove(color=cor, source=fonte, reason=lido.side_to_move_reason,
                              conflicting=lido.side_conflicting)
    return SideToMove(color=cor, source="default", reason=lido.side_to_move_reason,
                      conflicting=lido.side_conflicting)


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

    provenance_path: Path | None = None
    """O sidecar de proveniência gravado ao lado do PGN (A11), quando houve."""

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

    # C11: com reparo pelo lance seguinte, a barra julga as outras casas -- a casa trocada
    # carrega a confiança da segunda opção (a verdade sobre a matriz), mas o lance impresso é
    # evidência que a matriz não tem.
    judged = position.gate_confidence if position.gate_confidence is not None else position.min_confidence
    if judged is not None and judged < accept_threshold:
        return "needs_review", f"confiança mínima {judged:.3f} < {accept_threshold:.2f}"

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


def _piece_letter(class_index: int) -> str:
    name = PIECE_CLASSES[int(class_index)]
    return "" if name == "empty" else name


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
    dpi: int = DEFAULT_DPI,
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
    """O laço de páginas, com o modelo já em mãos.

    **O reconhecimento é o `OcrService.recognize_page`, o mesmo que os relatórios de campo
    medem** (S-833). Aqui ficava uma cópia da corrente -- orientação, cor, lado, lance seguinte,
    exigência, legalidade, portão -- que já tinha se separado da original: as coordenadas da
    borda não chegavam à orientação, e o portão era calculado de outro jeito. O que sobra aqui é
    o que só a varredura faz: renderizar, detectar na ordem de leitura pedida e ler o contexto
    pelo leitor de legenda que ela recebeu.
    """
    from .service import OcrService, RecognitionOptions

    # C5: o calibrador de cor do livro, uma vez por PDF (o perfil da suíte quando
    # ela está importável; `None` sem perfil -- e o tabuleiro responde sozinho).
    calibrador_de_cor = calibrador_do_livro(pdf_source)
    servico = OcrService(loader=lambda _caminho: (model, resolved_device))
    opcoes = RecognitionOptions(
        orientation=orientation,
        max_boards=max_boards_per_page,
        dpi=dpi,
        colour_calibrator=lambda _fonte: calibrador_de_cor,
    )
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
        lidos = (
            servico.recognize_page(
                pdf_source, page_index, page_rgb, options=opcoes, candidates=candidates, contexts=contexts
            )
            if candidates
            else []
        )

        page_positions: list[DiagramPosition] = []
        for candidate, lido in zip(candidates, lidos, strict=True):
            position = DiagramPosition.from_recognized(lido, page_index=page_index)
            page_positions.append(position)
            seen += 1
            assert lido.prediction is not None  # recognize_page sempre lê
            yield ScannedDiagram(
                position=position,
                prediction=lido.prediction,
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
    dpi: int = DEFAULT_DPI,
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
    provenance_file: str = "",
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
        identidade = (position.page_index, position.diagram_index)
        annotation = (annotations or {}).get(identidade)
        reason = (review_reasons or {}).get(identidade)
        game = chess.pgn.Game()
        # A ordem das partes é a ordem dos headers no arquivo, e a anotação vem por último.
        for parte in (
            _headers_de_identidade(position, annotation, source_name, event_name, reading_order),
            _headers_do_lado_a_jogar(position, annotation),
            _headers_do_contexto(position.context),
            _headers_da_deteccao(position),
            _headers_dos_reparos(position),
            _headers_da_estipulacao(position),
            _headers_de_proveniencia(position, provenance_file),
            _headers_de_legalidade(position),
            {"Review": reason} if reason else {},
            _headers_da_anotacao(annotation),
        ):
            game.headers.update(parte)
        if _quer_link(annotation, lichess_links):
            # Comentario, e nao header: o link e para uma pessoa clicar, e leitor de PGN
            # mostra comentario junto do diagrama. Header seria metadado de maquina.
            game.comment = lichess_analysis_url(game.headers["FEN"])
        games.append(game)
    return games


Headers = dict[str, str]
"""Uma parte dos headers de um jogo, devolvida por um construtor por assunto (S-858)."""


def _headers_de_identidade(
    position: DiagramPosition,
    annotation: DiagramAnnotation | None,
    source_name: str,
    event_name: str,
    reading_order: ReadingOrder,
) -> Headers:
    """Quem jogou, de onde a posição saiu e a FEN -- o que todo jogo tem."""
    context = position.context
    white, black = context.players if context and context.players else ("?", "?")
    headers = {
        "Event": (context.event if context and context.event else None) or event_name,
        "Site": "Local",
        "Round": f"{position.page_number}.{position.diagram_index}",
        "White": white,
        "Black": black,
    }
    if context is not None and context.year is not None:
        headers["Date"] = f"{context.year}.??.??"
    return headers | {
        "Result": "*",
        "Annotator": "ChessVisionOFF",
        "SetUp": "1",
        "FEN": position.annotated_fen(annotation),
        "SourcePDF": source_name,
        "Page": str(position.page_number),
        "Diagram": str(position.diagram_index),
        "ReadingOrder": reading_order,
        "OCRConfidence": f"{position.confidence:.3f}",
    }


def _headers_do_lado_a_jogar(position: DiagramPosition, annotation: DiagramAnnotation | None) -> Headers:
    side_to_move = position.annotated_side_to_move(annotation)
    if side_to_move is None:
        return {}
    headers = {"SideToMove": side_to_move.label, "SideToMoveSource": side_to_move.source}
    # So quando quem decidiu foi o OCR (S-43). Escrever a confianca de uma decisao
    # de legalidade -- que pode ter derrubado uma leitura de OCR de 0,55 -- diria
    # que a resposta gravada vale 0,55, e ela nao veio de la. E 1,0 em todo jogo de
    # um livro com camada de texto e ruido que ensina a ignorar o header.
    if side_to_move.source in _OCR_SOURCES and position.context is not None:
        headers["SideToMoveConfidence"] = f"{position.context.side_to_move_confidence:.3f}"
    if infer_castling_rights(position.fen) != "-":
        # So quando ha o que declarar: escrever a proveniencia de um "-" nao informa
        # nada e enche o header de ruido.
        headers["CastlingSource"] = "inferred"
    return headers


def _headers_do_contexto(context: DiagramContext | None) -> Headers:
    """O número do exercício e a legenda, quando a página os tem."""
    headers: Headers = {}
    if context is not None and context.exercise_number is not None:
        headers["ExerciseNumber"] = str(context.exercise_number)
    if context is not None and context.caption:
        headers["Caption"] = _flatten_caption(context.caption)
    return headers


def _headers_da_deteccao(position: DiagramPosition) -> Headers:
    """De onde o recorte veio, se repete outro, e a casa mais insegura da leitura."""
    headers: Headers = {}
    if position.detection_source is not None:
        headers["DetectionSource"] = position.detection_source
    if position.duplicate_of is not None:
        page_number, diagram_index = position.duplicate_of
        headers["DuplicateOf"] = f"{page_number}.{diagram_index}"
    if position.min_confidence is not None:
        headers["OCRMinConfidence"] = f"{position.min_confidence:.3f}"
    return headers


def _sufixo_do_gate(position: DiagramPosition) -> str:
    return f"; gate {position.gate_confidence:.3f}" if position.gate_confidence is not None else ""


def _headers_dos_reparos(position: DiagramPosition) -> Headers:
    headers: Headers = {}
    if position.next_move_repairs:
        # C11: a casa trocada por evidência externa e a confiança que o gate julgou. A
        # `OCRMinConfidence` continua sendo a da matriz -- o PGN não mente sobre ela.
        headers["OCRNextMove"] = (
            f"{position.next_move} prova {' '.join(position.next_move_repairs)}" + _sufixo_do_gate(position)
        )
    if position.colour_repairs:
        # C5: a cor que a tinta contradisse, trocada pelo calibrador do livro.
        headers["OCRColour"] = "tinta trocou " + " ".join(position.colour_repairs)
    return headers


def _veredito_da_estipulacao(position: DiagramPosition) -> str:
    if position.stipulation_closes is True:
        return "fecha" + (f": 1.{position.stipulation_keys[0]}" if position.stipulation_keys else "")
    if position.stipulation_closes is False:
        return "não fecha"
    return "não verificada"


def _headers_da_estipulacao(position: DiagramPosition) -> Headers:
    """C12: a exigência impressa e o que ela disse da leitura.

    `Stipulation` é o header que os leitores de PGN de problemas já conhecem (`#2`);
    `StipulationCheck` diz se a posição exportada a cumpre -- «fecha», «não fecha» ou «não
    verificada».
    """
    if not position.stipulation:
        return {}
    headers = {"Stipulation": position.stipulation, "StipulationCheck": _veredito_da_estipulacao(position)}
    if position.stipulation_repairs:
        headers["OCRStipulation"] = (
            f"{position.stipulation} prova {' '.join(position.stipulation_repairs)}" + _sufixo_do_gate(position)
        )
    return headers


def _headers_de_proveniencia(position: DiagramPosition, provenance_file: str) -> Headers:
    """A11: o PGN aponta para o sidecar; a chave é a mesma identidade do `[Diagram]`."""
    if not provenance_file:
        return {}
    return {
        "ProvenanceFile": provenance_file,
        "ProvenanceKey": chave(position.page_index, position.diagram_index),
    }


def _headers_de_legalidade(position: DiagramPosition) -> Headers:
    headers: Headers = {}
    if position.is_legal is not None:
        headers["OCRLegality"] = position.legality_label
        if not position.is_legal and position.problems:
            headers["OCRProblems"] = "; ".join(position.problems)
    if position.rotation is not None:
        # Registrado sempre, e nao so quando girou: sem isso nao ha como saber depois se
        # a leitura de um diagrama suspeito foi feita de pe ou de cabeca para baixo.
        headers["OCRRotation"] = str(position.rotation)
    return headers


def _headers_da_anotacao(annotation: DiagramAnnotation | None) -> Headers:
    """O que a pessoa escreveu na galeria, que vence tudo que foi inferido.

    Por isso entra por ultimo. `RESERVED_HEADERS` ja tirou `FEN`, `SetUp` e `Result` da
    jogada -- aqueles mudam pelos campos proprios, que sabem recompor a posicao.
    """
    if annotation is None:
        return {}
    headers = dict(annotation.headers)
    if annotation.filled_from:
        # A evidencia do casamento (S-72). Sem ela, `[White "Ljubojevic, Ljubomir"]`
        # num PGN nao diz se alguem digitou aquilo ou se as 64 casas bateram com uma
        # partida registrada -- e as duas coisas valem muito diferente.
        headers["GameSource"] = annotation.filled_from
    return headers


def _quer_link(annotation: DiagramAnnotation | None, lichess_links: bool) -> bool:
    """A decisão do diagrama, quando ele declarou uma; senão o padrão da exportação (S-67)."""
    declarado = annotation.lichess_link if annotation is not None else None
    return lichess_links if declarado is None else declarado

def build_pgn_text(
    positions: Iterable[DiagramPosition],
    *,
    source_name: str,
    event_name: str = "ChessVisionOFF PDF OCR",
    review_reasons: Mapping[tuple[int, int], str] | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    annotations: Mapping[tuple[int, int], DiagramAnnotation] | None = None,
    lichess_links: bool = False,
    provenance_file: str = "",
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
            provenance_file=provenance_file,
        )
    ]
    return "\n\n".join(payload for payload in payloads if payload).strip()


def replace_cabecalho(cabecalho: Cabecalho, *, accept_threshold: float) -> Cabecalho:
    return replace(cabecalho, accept_threshold=float(accept_threshold))


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
    provenance: Cabecalho | None = None,
) -> ExportReport:
    """Escreve o PGN principal só com o que passou no gate, e o resto no `.review.pgn`.

    Com `provenance` (A11) escreve também o sidecar `<nome>.proveniencia.jsonl` -- aceitas e
    de revisão numa lista só, com o veredito de cada uma -- e os dois PGNs apontam para ele.

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
    sidecar_name = ""
    sidecar: Path | None = None
    if provenance is not None:
        sidecar = write_sidecar(
            [(position, "accepted", "") for position in accepted]
            + [(position, "needs_review", reason) for position, reason in needs_review]
            + [(position, "rejected", reason) for position, reason in rejected]
            + [(position, "duplicate", "") for position in duplicates],
            output_path,
            cabecalho=replace_cabecalho(provenance, accept_threshold=accept_threshold),
            annotations=annotations,
        )
        sidecar_name = sidecar.name
    payload = build_pgn_text(
        accepted,
        source_name=source_name,
        event_name=event_name,
        reading_order=reading_order,
        annotations=annotations,
        lichess_links=lichess_links,
        provenance_file=sidecar_name,
    )
    atomic_write_text(output_path, payload + "\n" if payload else "")

    review_items = sorted(
        needs_review + rejected,
        key=lambda item: (item[0].page_index, item[0].diagram_index),
    )
    review_path: Path | None = None
    if not review_items:
        # O `.review.pgn` da rodada anterior não pode ficar ao lado do PGN de agora (S-818).
        review_output_path(output_path).unlink(missing_ok=True)
    else:
        review_path = review_output_path(output_path)
        review_payload = build_pgn_text(
            [position for position, _ in review_items],
            source_name=source_name,
            event_name=event_name,
            review_reasons={(position.page_index, position.diagram_index): reason for position, reason in review_items},
            reading_order=reading_order,
            annotations=annotations,
            lichess_links=lichess_links,
            provenance_file=sidecar_name,
        )
        atomic_write_text(review_path, review_payload + "\n" if review_payload else "")

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
        provenance_path=sidecar,
    )


def save_pdf_positions_to_pgn(
    pdf_source: PdfSource,
    output_path: Path,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = DEFAULT_DPI,
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
        try:
            anotacoes = load_annotations(Path(pdf_source), reading_order=reading_order).as_mapping()
        except GaleriaDeOutroLivro as exc:
            # A galeria de mesmo nome é de outro livro (S-878): este não tem anotação nenhuma, e
            # exportá-lo sem elas é a verdade. Derrubar a exportação faria o lote falhar o
            # segundo de dois livros de mesmo nome, que é o caso que ele agora separa.
            logger.warning("%s; exportando sem anotações da galeria.", exc)
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
        provenance=Cabecalho(
            source_name=source_name,
            source_hash=hash_do_arquivo(pdf_source if isinstance(pdf_source, (str, Path)) else None),
            model_identity=checkpoint_identity(Path(model_path)),
            model_path=str(model_path),
            profile=_profile_summary(pdf_source),
            dpi=dpi,
        ),
    )


def _profile_summary(pdf_source: PdfSource) -> dict[str, Any]:
    """O que o perfil do livro da suíte (C5/X3) diz deste PDF, quando ela está importável."""
    if not isinstance(pdf_source, (str, Path)):
        return {}
    try:
        from caissa.ocr.book_profile import BookProfile
    except ImportError:
        return {}
    try:
        profile = BookProfile.for_pdf(Path(pdf_source))
    except Exception:  # noqa: BLE001 - um perfil ilegível não pode parar a exportação
        return {}
    if profile is None:
        return {}
    return {"fingerprint": profile.fingerprint, "closures": profile.closures,
            "model_identity": profile.model_identity, "dataset_version": profile.dataset_version,
            "colour_diagrams": (profile.colour or {}).get("diagramas", 0)}


def default_pgn_output_path(pdf_path: Path) -> Path:
    return PROJECT_ROOT / "PGN" / f"{pdf_path.stem}.pgn"
