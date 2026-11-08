"""Fila de revisão por valor de informação (S-22).

O fluxo até aqui é página por página, e o usuário não tem como saber quais diagramas do
livro merecem atenção. O valor de cada correção, porém, é muito desigual: corrigir um
diagrama que o modelo já lê com 0,999 não ensina nada ao modelo nem conserta nada no PGN.
Em 289 páginas do Kemeri com ~1,5 diagramas por página, a diferença é entre 430 revisões e
as ~30 que importam.

**Ordem de prioridade, e o que ela tem de diferente do que a S-22 propunha.** A spec pede
"ilegal > fontes de detecção discordantes (S-12) > confiança mínima baixa > entropia média
alta > classe rara presente". Quatro dos cinco entram como estão. O segundo não existe da
forma escrita: depois da medição da Fase 2 o detector híbrido **não** lê o diagrama duas
vezes -- a imagem embutida localiza e o contorno alinha, uma leitura por candidato -- então
não há duas leituras para discordarem entre si (ver `detection/hybrid.py`). O que existe,
e é discordância de fonte de verdade, é a da Fase 3: o texto do PDF dizendo um lado a jogar
e a legalidade da posição impondo o outro (`SideToMove.conflicting`). Esse entrou no lugar,
com o mesmo peso relativo, e junto veio a orientação ambígua da S-13 -- que a S-22 não
tinha como prever porque a S-13 ainda não existia quando ela foi escrita, e que é o item
mais caro de todos: uma casa insegura custa uma correção, um diagrama de cabeça para baixo
custa o diagrama inteiro.

A fila é persistida (`data/review_queue.json`) porque revisar um livro não cabe numa
sessão, e refazer a varredura de 1.121 páginas para reencontrar os mesmos 30 itens seria
absurdo. As miniaturas ficam em disco, referenciadas por caminho: guardar 430 imagens de
tabuleiro em JSON não é uma opção.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

from .arquivo_do_dono import ConteudoIlegivel, Leitura, Lida, conferir_versao_exata, gravar_json, ler
from .atomic_io import write_image
from .config import (
    ACCEPT_MIN_CONFIDENCE,
    DATA_DIR,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
    PIECE_CLASSES,
    OrientationMode,
    ReadingOrder,
)
from .fen_utils import labels_from_fen, square_name
from .gallery import load_annotations
from .labels import LabelStore
from .pdf_to_pgn import DiagramPosition, ProgressCallback, ScannedDiagram, iter_pdf_diagrams
from .relogio import agora_iso
from .ui.livros import chave_do_livro, mesmo_livro

logger = logging.getLogger(__name__)

QUEUE_VERSION = 1

DEFAULT_QUEUE_PATH = DATA_DIR / "review_queue.json"
DEFAULT_CACHE_DIR = DATA_DIR / "review_cache"

ReviewStatus = Literal["pending", "done", "skipped"]

# Pesos em faixas separadas por ordem de grandeza: cada motivo domina inteiramente os de
# baixo. E o que faz a fila respeitar a precedencia da S-22 em vez de somar sinais
# incomparaveis -- 40 casas ligeiramente inseguras nao podem passar na frente de 1 ilegal.
WEIGHT_ILLEGAL = 1000.0
WEIGHT_ORIENTATION_AMBIGUOUS = 500.0
WEIGHT_SOURCES_DISAGREE = 250.0
WEIGHT_SIDE_TO_MOVE_WRONG = 120.0
WEIGHT_LOW_CONFIDENCE = 100.0
"""Multiplicador do quanto a confiança mínima ficou abaixo do limiar de aceite (0..1)."""

WEIGHT_ENTROPY = 10.0
WEIGHT_RARE_CLASS = 5.0
WEIGHT_DECODE_REPAIR = 30.0

RARE_CLASS_SHARE = 0.005
"""Classe que ocupa menos que isto das casas rotuladas conta como rara."""


@dataclass(frozen=True)
class ReviewItem:
    """Um diagrama que vale a pena olhar, e por quê."""

    pdf_path: str
    page_index: int
    diagram_index: int
    board_image: str
    """Caminho do recorte em cache -- não a imagem em memória, como a S-22 já previa."""

    fen: str
    side_to_move: str
    min_confidence: float
    mean_entropy: float
    priority: float
    reasons: tuple[str, ...]
    uncertain_squares: tuple[int, ...] = ()
    square_confidences: tuple[float, ...] = ()
    """As 64 confianças, para o heatmap da S-21 abrir sem reprocessar a página."""

    changed_squares: tuple[int, ...] = ()
    """Casas reescritas pela decodificação restrita (S-11)."""

    status: ReviewStatus = "pending"

    @property
    def page_number(self) -> int:
        return self.page_index + 1

    @property
    def label(self) -> str:
        return f"p.{self.page_number} d.{self.diagram_index}"

    @property
    def first_uncertain_square(self) -> int | None:
        """Casa mais suspeita, para a UI abrir o editor já com ela selecionada."""
        return self.uncertain_squares[0] if self.uncertain_squares else None

    def describe(self) -> str:
        motivo = "; ".join(self.reasons) if self.reasons else "sem motivo registrado"
        return f"{self.label} | prioridade {self.priority:.1f} | {motivo}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf_path": self.pdf_path,
            "page_index": self.page_index,
            "diagram_index": self.diagram_index,
            "board_image": self.board_image,
            "fen": self.fen,
            "side_to_move": self.side_to_move,
            "min_confidence": self.min_confidence,
            "mean_entropy": self.mean_entropy,
            "priority": self.priority,
            "reasons": list(self.reasons),
            "uncertain_squares": list(self.uncertain_squares),
            "square_confidences": [round(value, 5) for value in self.square_confidences],
            "changed_squares": list(self.changed_squares),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ReviewItem:
        status = raw.get("status", "pending")
        return cls(
            pdf_path=str(raw.get("pdf_path", "")),
            page_index=int(raw.get("page_index", 0)),
            diagram_index=int(raw.get("diagram_index", 1)),
            board_image=str(raw.get("board_image", "")),
            fen=str(raw.get("fen", "")),
            side_to_move=str(raw.get("side_to_move", "w")),
            min_confidence=float(raw.get("min_confidence", 0.0)),
            mean_entropy=float(raw.get("mean_entropy", 0.0)),
            priority=float(raw.get("priority", 0.0)),
            reasons=tuple(str(item) for item in raw.get("reasons", ())),
            uncertain_squares=tuple(int(item) for item in raw.get("uncertain_squares", ())),
            square_confidences=tuple(float(item) for item in raw.get("square_confidences", ())),
            changed_squares=tuple(int(item) for item in raw.get("changed_squares", ())),
            status=status if status in ("pending", "done", "skipped") else "pending",
        )


@dataclass
class ReviewQueue:
    """Fila ordenada por prioridade, com o que já foi resolvido marcado."""

    source_pdf: str = ""
    created_at: str = ""
    items: list[ReviewItem] = field(default_factory=list)
    scanned_diagrams: int = 0
    """Total varrido, não só o que entrou na fila. É o denominador de qualquer medição."""

    pages_scanned: int = 0

    paginas_vistas: frozenset[int] = field(default=frozenset(), compare=False)
    """As páginas que esta fila descreve por inteiro: as que a passada visitou, menos as que o
    `limit` cortou. É o que `fundir_fila_retomada` precisa saber da passada (S-816). Não é gravado:
    a fila lida do disco não é passada nenhuma."""

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[ReviewItem]:
        return iter(self.items)

    def pending(self) -> list[ReviewItem]:
        return [item for item in self.items if item.status == "pending"]

    def sort(self) -> None:
        """Prioridade desc; empate resolvido pela ordem do livro, para ficar reproduzível."""
        self.items.sort(key=lambda item: (-item.priority, item.page_index, item.diagram_index))

    def index_of(self, page_index: int, diagram_index: int) -> int | None:
        for position, item in enumerate(self.items):
            if item.page_index == page_index and item.diagram_index == diagram_index:
                return position
        return None

    def mark(self, position: int, status: ReviewStatus) -> None:
        if not 0 <= position < len(self.items):
            raise IndexError(f"Item {position} fora da fila de {len(self.items)}.")
        self.items[position] = replace(self.items[position], status=status)

    def update_fen(self, position: int, fen: str, side_to_move: str | None = None) -> None:
        """Grava a correção feita na UI, sem perder o motivo pelo qual o item entrou."""
        if not 0 <= position < len(self.items):
            raise IndexError(f"Item {position} fora da fila de {len(self.items)}.")
        item = self.items[position]
        self.items[position] = replace(
            item,
            fen=fen,
            side_to_move=side_to_move if side_to_move in ("w", "b") else item.side_to_move,
        )

    def summary(self) -> str:
        pendentes = len(self.pending())
        return (
            f"{len(self.items)} itens na fila ({pendentes} pendentes) de {self.scanned_diagrams} "
            f"diagramas em {self.pages_scanned} páginas"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": QUEUE_VERSION,
            "source_pdf": self.source_pdf,
            "created_at": self.created_at,
            "scanned_diagrams": self.scanned_diagrams,
            "pages_scanned": self.pages_scanned,
            "items": [item.to_dict() for item in self.items],
        }


def carregar_fila(path: Path = DEFAULT_QUEUE_PATH) -> Leitura[ReviewQueue]:
    """A fila gravada. Vazia quando não há arquivo.

    **Ilegível, ou de outra versão, é leitura travada (S-812).** Antes a fila voltava vazia e a
    próxima gravação -- a de uma revarredura, ou a de marcar um item -- escrevia a fila vazia por
    cima das correções. A versão diferente da nossa, mais velha inclusive, trava do mesmo jeito: não
    há migração, e regravar seria apagar.
    """
    return ler(Path(path), _interpretar_fila, ReviewQueue)


def _interpretar_fila(texto: str) -> ReviewQueue:
    raw = json.loads(texto)
    conferir_versao_exata(raw, "version", QUEUE_VERSION)
    fila = ReviewQueue(
        source_pdf=str(raw.get("source_pdf", "")),
        created_at=str(raw.get("created_at", "")),
        scanned_diagrams=int(raw.get("scanned_diagrams", 0)),
        pages_scanned=int(raw.get("pages_scanned", 0)),
    )
    # Cada item no seu `try` (S-815): um campo que não é número num item levava a fila inteira a
    # vazia. O que leu chega à tela; a trava continua, porque gravar o parcial apagaria o resto.
    falhas: list[str] = []
    for numero, bruto in enumerate(raw.get("items", []), start=1):
        try:
            if not isinstance(bruto, dict):
                raise ValueError("não é um objeto")
            fila.items.append(ReviewItem.from_dict(bruto))
        except (TypeError, ValueError) as erro:
            falhas.append(f"item {numero}: {erro}")
    if falhas:
        raise ConteudoIlegivel("; ".join(falhas[:3]) + (" ..." if len(falhas) > 3 else ""), parcial=fila)
    return fila


def gravar_fila(lida: Lida[ReviewQueue]) -> Path:
    """Grava a fila onde ela foi lida. Só sobre uma leitura que leu (S-812)."""
    destino = gravar_json(lida, lida.valor.to_dict())
    logger.info("Fila de revisão gravada em %s (%d itens).", destino, len(lida.valor.items))
    return destino


# ------------------------------------------------------------------- prioridade


def priority_for(
    position: DiagramPosition,
    *,
    min_confidence: float,
    mean_entropy: float,
    uncertain_squares: Sequence[int] = (),
    repaired_squares: int = 0,
    rare_classes: Collection[str] = (),
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    confirmed_by_database: str = "",
) -> tuple[float, tuple[str, ...]]:
    """Prioridade e motivos de um diagrama. Prioridade 0 significa "não precisa de olho".

    Recebe os números soltos em vez da `BoardPrediction` para poder ser chamada também
    sobre um item já persistido, que não tem mais a matriz de probabilidades.

    **`confirmed_by_database` cala tudo que é sobre a leitura, e nada do que é sobre a vez a
    jogar** (S-74). Quando as 64 casas batem com um lance de uma partida registrada, não há o
    que revisar na *posição*: confiança baixa, entropia, casa reescrita pela S-11 e classe rara
    são estimativas de erro, e ali existe a resposta. O que a confirmação **não** responde é de
    quem é a vez -- a mesma colocação aparece com brancas e com pretas a jogar em partidas
    diferentes --, então a discordância de fonte e o xeque invertido continuam valendo.

    Confiar nisso tem um risco, e ele é pequeno e nomeado: uma leitura errada que por acaso
    componha outra posição real. Com 64 casas isso exige coincidência estrutural, e o caso em
    que ela é plausível -- final de poucas peças que aparece em centenas de partidas -- é
    justamente o que `apply_matches` recusa preencher.
    """
    score = 0.0
    reasons: list[str] = []

    if confirmed_by_database:
        side = position.side_to_move
        if side is not None and side.conflicting:
            score += WEIGHT_SOURCES_DISAGREE
            reasons.append("texto e posição discordam do lado a jogar")
        if position.needs_side_to_move_flip:
            score += WEIGHT_SIDE_TO_MOVE_WRONG
            reasons.append("lado a jogar assumido não fecha: " + ("; ".join(position.problems) or "xeque invertido"))
        if reasons:
            reasons.append(f"posição confirmada pela base ({confirmed_by_database}); resta a vez a jogar")
        return score, tuple(reasons)

    if position.is_fatal:
        score += WEIGHT_ILLEGAL
        reasons.append("ilegal: " + ("; ".join(position.problems) or "posição impossível"))

    if position.orientation_ambiguous:
        score += WEIGHT_ORIENTATION_AMBIGUOUS
        reasons.append("orientação incerta: " + (position.orientation_reason or "as duas eram plausíveis"))

    side = position.side_to_move
    if side is not None and side.conflicting:
        score += WEIGHT_SOURCES_DISAGREE
        reasons.append("texto e posição discordam do lado a jogar")

    if position.needs_side_to_move_flip:
        score += WEIGHT_SIDE_TO_MOVE_WRONG
        reasons.append("lado a jogar assumido não fecha: " + ("; ".join(position.problems) or "xeque invertido"))

    if min_confidence < accept_threshold:
        gap = (accept_threshold - min_confidence) / max(accept_threshold, 1e-6)
        score += WEIGHT_LOW_CONFIDENCE * gap
        nomes = ", ".join(square_name(index) for index in uncertain_squares[:3])
        detalhe = f" (casas {nomes})" if nomes else ""
        reasons.append(f"confiança mínima {min_confidence:.3f} < {accept_threshold:.2f}{detalhe}")

    score += WEIGHT_ENTROPY * float(mean_entropy)

    if repaired_squares:
        score += WEIGHT_DECODE_REPAIR
        reasons.append(f"{repaired_squares} casa(s) reescritas pela decodificação restrita")

    if rare_classes:
        present = sorted({symbol for symbol in _symbols_in(position.fen) if symbol in rare_classes})
        if present:
            score += WEIGHT_RARE_CLASS * len(present)
            reasons.append("classe rara no tabuleiro: " + ", ".join(present))

    return score, tuple(reasons)


def _symbols_in(placement: str) -> set[str]:
    return {char for char in placement.split(" ")[0] if char.isalpha()}


def rare_classes_from_labels(csv_path: Path, *, share: float = RARE_CLASS_SHARE) -> set[str]:
    """Classes de peça sub-representadas no `labels.csv`.

    A ideia da S-22 é que corrigir um diagrama com dama preta vale mais que corrigir o
    milésimo com peão branco, porque o modelo tem pouco material daquela classe. A conta é
    sobre casas rotuladas, não sobre tabuleiros: é a unidade em que o modelo aprende.

    Ignora `empty`, que é 77% das casas por construção e nunca será rara.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return set()

    try:
        pares = LabelStore(csv_path).read_pairs()
    except (OSError, ValueError) as exc:
        logger.warning("Não foi possível ler as classes de %s: %s", csv_path, exc)
        return set()

    counts: dict[str, int] = {}
    total = 0
    for _filename, raw in pares:
        try:
            indices = labels_from_fen(raw)
        except (ValueError, IndexError):
            continue
        for index in indices:
            name = PIECE_CLASSES[index]
            if name == "empty":
                continue
            counts[name] = counts.get(name, 0) + 1
            total += 1

    if not total:
        return set()
    return {name for name, count in counts.items() if count / total < share}


# --------------------------------------------------------------------- varredura


def cache_board_image(board_rgb: np.ndarray, cache_dir: Path, pdf_path: Path, page_index: int, diagram_index: int) -> Path:
    """Grava a miniatura do diagrama e devolve o caminho. Sobrescreve sem cerimônia.

    O nome é determinístico (livro/página/diagrama) para que revarrer o mesmo PDF reaproveite
    o arquivo em vez de encher o disco com cópias datadas. A pasta é a do **livro**, e não a do
    nome do arquivo: ver `nome_do_livro`.
    """
    directory = Path(cache_dir) / nome_do_livro(pdf_path)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"p{page_index + 1:05d}_d{diagram_index}.png"
    return write_image(path, cv2.cvtColor(board_rgb, cv2.COLOR_RGB2BGR))


def nome_do_livro(pdf_path: Path | str) -> str:
    """O nome de arquivo que é de um livro só: o nome legível e o hash curto da `ChaveDoLivro` (S-815).

    Só o nome do arquivo não basta: o acervo tem livros duplicados em pastas diferentes, e
    `a/Livro.pdf` e `b/Livro.pdf` gravavam as miniaturas na mesma pasta, uma por cima da outra.
    """
    chave = chave_do_livro(pdf_path)
    legivel = _safe_name(Path(pdf_path).stem)
    return legivel if chave is None else f"{legivel}-{chave.curta}"


def _safe_name(name: str) -> str:
    keep = "".join(char if char.isalnum() or char in " -_." else "_" for char in name)
    return keep.strip() or "pdf"


def item_from_scanned(
    scanned: ScannedDiagram,
    *,
    pdf_path: Path,
    cache_dir: Path,
    rare_classes: Collection[str] = (),
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    confirmed: Mapping[tuple[int, int], str] | None = None,
) -> ReviewItem | None:
    """Constrói o item da fila. `None` quando o diagrama não pede revisão nenhuma."""
    position = scanned.position
    prediction = scanned.prediction
    repaired = prediction.decode.changed_square_count if prediction.decode is not None else 0

    priority, reasons = priority_for(
        position,
        min_confidence=prediction.min_confidence,
        mean_entropy=prediction.mean_entropy,
        uncertain_squares=prediction.uncertain_squares,
        repaired_squares=repaired,
        rare_classes=rare_classes,
        accept_threshold=accept_threshold,
        confirmed_by_database=(confirmed or {}).get((position.page_index, position.diagram_index), ""),
    )
    if not reasons:
        # Entropia sozinha nao e motivo: ela pontua em todo diagrama e serve para desempatar,
        # nao para colocar na fila um tabuleiro sobre o qual nao ha nada a dizer.
        return None

    image_path = cache_board_image(
        scanned.board_rgb,
        cache_dir,
        pdf_path,
        position.page_index,
        position.diagram_index,
    )
    return ReviewItem(
        pdf_path=str(pdf_path),
        page_index=position.page_index,
        diagram_index=position.diagram_index,
        board_image=str(image_path),
        fen=position.full_fen,
        side_to_move="w" if position.side_to_move is None or position.side_to_move.color else "b",
        min_confidence=prediction.min_confidence,
        mean_entropy=prediction.mean_entropy,
        priority=priority,
        reasons=reasons,
        uncertain_squares=tuple(prediction.uncertain_squares),
        square_confidences=tuple(float(value) for value in prediction.square_confidences),
        changed_squares=tuple(square for square, _argmax, _final in (prediction.decode.changed_squares if prediction.decode else [])),
    )


class ReviewQueueBuilder:
    """Monta a fila a partir dos `ScannedDiagram` de **uma** varredura (S-119).

    **O que ele existe para eliminar são duas passadas pelo mesmo livro.**
    `build_gallery_index` e `build_review_queue` percorriam o mesmo `iter_pdf_diagrams`, com os
    mesmos parâmetros, e gravavam em arquivos diferentes -- nenhum consumindo o resultado do
    outro. Medido no `PDF/1000 Chess Problems` (420 páginas): **338 s + 299 s**. Abrir um livro
    novo custava ~5 min antes de qualquer trabalho humano, e mais ~5 min quando se descobria
    que a outra aba também precisava da própria varredura. É uma das razões de 27 dos 34 livros
    nunca terem sido abertos.

    **Por que um acumulador e não "derivar do `GalleryIndex`", que era a proposta do
    enunciado.** O índice **não** é superconjunto da fila: ele guarda colocação, confiança
    mínima, legalidade e legenda, e a prioridade da S-22 precisa de `mean_entropy`,
    `uncertain_squares` e das casas que o decodificador reparou -- que a `GalleryEntry` não
    carrega. Derivar dali daria uma fila *parecida*, e o critério de aceite pede a **mesma**.
    Alargar a `GalleryEntry` para caber tudo faria o índice de cada livro crescer para servir
    a um consumidor que já tem arquivo próprio.

    Com o acumulador, `build_review_queue` e a varredura única passam pelo **mesmo** código de
    montagem: a equivalência entre as duas filas é estrutural, e não uma coincidência que um
    teste vigia.
    """

    def __init__(
        self,
        pdf_path: Path,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        rare_classes: Collection[str] = (),
        accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
        confirmed: Mapping[tuple[int, int], str] | None = None,
        limit: int | None = None,
    ) -> None:
        self.pdf_path = Path(pdf_path)
        self.cache_dir = Path(cache_dir)
        self.rare_classes = rare_classes
        self.accept_threshold = accept_threshold
        self.confirmed = confirmed if confirmed is not None else confirmed_by_database(self.pdf_path)
        self.limit = limit
        self.items: list[ReviewItem] = []
        self.scanned_count = 0
        self.pages: set[int] = set()
        if self.confirmed:
            logger.info("%d diagrama(s) deste livro já foram confirmados pela base (S-74).", len(self.confirmed))

    def feed(self, scanned: ScannedDiagram) -> None:
        """Um diagrama lido. Serve como `on_scanned` de `build_gallery_index`."""
        self.scanned_count += 1
        self.pages.add(scanned.position.page_index)
        item = item_from_scanned(
            scanned,
            pdf_path=self.pdf_path,
            cache_dir=self.cache_dir,
            rare_classes=self.rare_classes,
            accept_threshold=self.accept_threshold,
            confirmed=self.confirmed,
        )
        if item is not None:
            self.items.append(item)

    def finish(self, *, created_at: str | None = None) -> ReviewQueue:
        """A fila ordenada, e cortada pelo `limit` **depois** de ordenar."""
        queue = ReviewQueue(
            source_pdf=str(self.pdf_path),
            created_at=created_at or agora_iso(),
            items=self.items,
            scanned_diagrams=self.scanned_count,
            pages_scanned=len(self.pages),
        )
        queue.sort()
        vistas = set(self.pages)
        if self.limit is not None and len(queue.items) > self.limit:
            logger.info(
                "Fila cortada em %d itens; %d ficaram de fora.", self.limit, len(queue.items) - self.limit
            )
            # A pagina com item cortado nao foi descrita por inteiro: o que ela tinha na fila
            # anterior nao "deixou de ser suspeito", so ficou fora do corte (S-816).
            vistas -= {item.page_index for item in queue.items[self.limit :]}
            queue.items = queue.items[: self.limit]
        queue.paginas_vistas = frozenset(vistas)
        return queue


def confirmed_by_database(
    pdf_path: Path, *, reading_order: ReadingOrder = DEFAULT_READING_ORDER
) -> dict[tuple[int, int], str]:
    """Quais diagramas deste livro a base já confirmou (S-74).

    As anotações do livro são a fonte, e não um arquivo próprio da fila: quem grava a
    confirmação é o `cvoff-games` (S-72/S-74), e um segundo lugar para essa verdade morar só
    teria como divergir do primeiro -- a decisão da S-34 sobre o `--skip-existing`.
    """
    return {
        chave: anotacao.confirmed_from
        for chave, anotacao in load_annotations(pdf_path, reading_order=reading_order).entries.items()
        if anotacao.confirmed_from
    }


def build_review_queue(
    pdf_source: Path,
    model_path: Path = DEFAULT_MODEL_PATH,
    *,
    dpi: int = 220,
    max_boards_per_page: int = DEFAULT_MAX_BOARDS,
    orientation: OrientationMode = DEFAULT_ORIENTATION_MODE,
    start_page: int = 0,
    end_page: int | None = None,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    read_text: bool = True,
    caption_reader: Any = None,
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE,
    rare_classes: Collection[str] = (),
    cache_dir: Path = DEFAULT_CACHE_DIR,
    limit: int | None = None,
    cancel_event: threading.Event | None = None,
    progress_callback: ProgressCallback | None = None,
    model_session: AbstractContextManager[tuple[Any, str]] | None = None,
    confirmed: Mapping[tuple[int, int], str] | None = None,
) -> ReviewQueue:
    """Varre o livro inteiro e devolve a fila ordenada por valor de informação.

    Usa o mesmo `iter_pdf_diagrams` da exportação: uma fila construída por um pipeline
    diferente do que gera o PGN mandaria o usuário corrigir um diagrama que o PGN não tem.

    `limit` corta a fila **depois** de ordenar, e o corte fica registrado no log -- fila
    truncada em silêncio se parece com "o livro só tinha 30 problemas".

    `model_session` empresta o modelo do `OcrService` em vez de carregar outro. É uma das
    duas varreduras longas que rodavam fora do lock da S-31 enquanto o treino reescrevia o
    mesmo `.pt` (S-57). `caption_reader` vem do mesmo serviço e pelo mesmo motivo do
    parágrafo acima: a fila tem de ser construída pelo pipeline que gera o PGN, procedência
    do lado a jogar incluída (S-43).
    """
    pdf_path = Path(pdf_source)
    if confirmed is None:
        confirmed = confirmed_by_database(pdf_path, reading_order=reading_order)
    # O mesmo acumulador da varredura unica (S-119): os dois caminhos passam pelo mesmo codigo
    # de montagem, entao a equivalencia entre as duas filas e estrutural.
    builder = ReviewQueueBuilder(
        pdf_path,
        cache_dir=cache_dir,
        rare_classes=rare_classes,
        accept_threshold=accept_threshold,
        confirmed=confirmed,
        limit=limit,
    )

    for scanned in iter_pdf_diagrams(
        pdf_path,
        model_path,
        dpi=dpi,
        max_boards_per_page=max_boards_per_page,
        orientation=orientation,
        start_page=start_page,
        end_page=end_page,
        reading_order=reading_order,
        read_text=read_text,
        caption_reader=caption_reader,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
        model_session=model_session,
    ):
        builder.feed(scanned)

    return builder.finish()


def fundir_fila_retomada(
    anterior: ReviewQueue, nova: ReviewQueue, *, paginas_vistas: Collection[int]
) -> ReviewQueue:
    """Revarredura sem perder o que já foi revisado. A regra mora aqui, e só aqui (S-816).

    **De outro livro, a fila nova substitui** -- conferido pela `ChaveDoLivro` (S-827), e não
    pelo nome do arquivo. A janela tem uma fila só, a do livro aberto; o `cvoff-review` também.

    O item novo manda em tudo -- prioridade, motivos -- menos no que é trabalho humano: o
    `status`, porque o diagrama que o usuário já resolveu não pode voltar para a fila de
    pendentes, e, no item feito, a FEN e o lado a jogar, porque o feito é a correção do editor
    (S-815): trazer de volta a leitura do OCR deixaria o item resolvido com o erro consertado.

    **`paginas_vistas` são as páginas que a passada descreve por inteiro, e é obrigatório**
    (S-119, S-816). Sem ele a fila nova era tomada como a fila inteira e o que ela não tinha
    desaparecia: uma passada retomada (S-120) que leu só as páginas 300 a 420 apagava as
    pendências das 300 primeiras, e o `cvoff-review --start-page` as de fora do intervalo. O
    argumento era opcional, a janela o passava e os dois CLIs não. O que está fora das páginas
    vistas sobrevive como estava; o que está numa página vista e a passada não trouxe deixou de
    ser suspeito, e sai. Quem monta a fila sabe as páginas: `ReviewQueue.paginas_vistas`.
    """
    if not mesmo_livro(anterior.source_pdf, nova.source_pdf):
        return nova
    previous = {(item.page_index, item.diagram_index): item for item in anterior.items}
    merged = [_herdar(item, previous.get((item.page_index, item.diagram_index))) for item in nova.items]
    vistas = set(paginas_vistas)
    trazidos = {(item.page_index, item.diagram_index) for item in nova.items}
    # Os preservados entram depois e o `sort` decide o lugar de cada um. A chave por (pagina,
    # diagrama) importa quando o `limit` cortou: a pagina fica fora das vistas com parte dos itens.
    merged.extend(
        item
        for item in anterior.items
        if item.page_index not in vistas and (item.page_index, item.diagram_index) not in trazidos
    )
    result = ReviewQueue(
        source_pdf=nova.source_pdf,
        created_at=nova.created_at,
        items=merged,
        scanned_diagrams=nova.scanned_diagrams,
        pages_scanned=nova.pages_scanned,
        paginas_vistas=nova.paginas_vistas,
    )
    result.sort()
    return result


def _herdar(novo: ReviewItem, antigo: ReviewItem | None) -> ReviewItem:
    """O item da passada nova com o trabalho humano do antigo. Ver `fundir_fila_retomada`."""
    if antigo is None:
        return novo
    if antigo.status == "done":
        return replace(novo, status="done", fen=antigo.fen, side_to_move=antigo.side_to_move)
    return replace(novo, status=antigo.status)


def error_rate(items: Iterable[ReviewItem], *, accept_threshold: float = ACCEPT_MIN_CONFIDENCE) -> float:
    """Fração de itens com sinal objetivo de erro -- para medir o critério de aceite da S-22.

    "Sinal objetivo" é o que não depende de opinião: ilegal, orientação ambígua, fontes
    discordantes ou confiança abaixo do limiar de aceite. É proxy do erro real, e está
    declarado como proxy: a verdade exige comparar com o PDF à mão.
    """
    items = list(items)
    if not items:
        return 0.0
    suspect = sum(
        1
        for item in items
        if item.min_confidence < accept_threshold
        or any(reason.startswith(("ilegal", "orientação", "texto e posição")) for reason in item.reasons)
    )
    return suspect / len(items)
