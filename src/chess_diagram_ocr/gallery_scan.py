"""O índice da galeria: todos os diagramas de um livro, varridos uma vez (S-67).

**Por que um índice, e não a varredura por página que a aba Resultado já faz.** A aba
Resultado lê a página que está aberta, e é o certo para ela: quem está corrigindo um diagrama
não quer esperar o livro inteiro. A galeria é o oposto -- ela existe para percorrer os
diagramas *sem* ter de achar a página de cada um --, e para isso precisa saber onde todos
estão antes de mostrar o primeiro.

**Por que não reaproveitar a fila de revisão.** A `build_review_queue` faz exatamente esta
varredura, mas guarda só o que vale revisar: `item_from_scanned` descarta o diagrama que
passou no gate. É a decisão certa lá e a errada aqui, porque na galeria o diagrama bem lido é
justamente o que se quer anotar e exportar. O que este módulo reaproveita é o que importa
reaproveitar: o **mesmo** `iter_pdf_diagrams` da exportação. Uma galeria construída por outro
pipeline mostraria diagramas que o PGN não tem -- que é o defeito que a S-14 já corrigiu uma
vez na numeração.

**As imagens vão para o cache da S-22**, pelo mesmo nome determinístico (livro/página/
diagrama). Duas cópias do mesmo recorte em duas pastas seria desperdício de disco e uma
segunda coisa a invalidar quando o livro fosse revarrido.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .config import (
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
    OrientationMode,
    ReadingOrder,
)
from .gallery import DEFAULT_GALLERY_DIR
from .pdf_to_pgn import ProgressCallback, iter_pdf_diagrams
from .review_queue import DEFAULT_CACHE_DIR, cache_board_image

logger = logging.getLogger(__name__)

__all__ = [
    "GalleryEntry",
    "GalleryIndex",
    "build_gallery_index",
    "index_path_for",
    "load_index",
    "save_index",
]


@dataclass(frozen=True)
class GalleryEntry:
    """Um diagrama do livro, com o suficiente para a galeria desenhá-lo e anotá-lo."""

    page_index: int
    diagram_index: int
    placement: str
    """Campo de peças. A vez a jogar mora em `side_to_move` -- juntá-las na mesma string é o
    que fazia a informação de lado se perder pelo caminho (S-17)."""

    side_to_move: str = "w"
    side_to_move_source: str = "default"
    min_confidence: float = 0.0
    is_legal: bool | None = None
    image_path: str = ""
    caption: str = ""
    """A legenda que a S-16 associou ao diagrama. Aparece na galeria como pista de contexto:
    é dali que costuma sair o número do lance que a pessoa vai digitar."""

    @property
    def key(self) -> tuple[int, int]:
        return (self.page_index, self.diagram_index)

    @property
    def page_number(self) -> int:
        return self.page_index + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "diagram_index": self.diagram_index,
            "placement": self.placement,
            "side_to_move": self.side_to_move,
            "side_to_move_source": self.side_to_move_source,
            "min_confidence": round(float(self.min_confidence), 4),
            "is_legal": self.is_legal,
            "image_path": self.image_path,
            "caption": self.caption,
        }

    @classmethod
    def from_dict(cls, dados: Any) -> GalleryEntry | None:
        if not isinstance(dados, dict):
            return None
        try:
            return cls(
                page_index=int(dados["page_index"]),
                diagram_index=int(dados["diagram_index"]),
                placement=str(dados["placement"]),
                side_to_move=str(dados.get("side_to_move") or "w"),
                side_to_move_source=str(dados.get("side_to_move_source") or "default"),
                min_confidence=float(dados.get("min_confidence") or 0.0),
                is_legal=dados.get("is_legal"),
                image_path=str(dados.get("image_path") or ""),
                caption=str(dados.get("caption") or ""),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Entrada de galeria ignorada: %r", dados)
            return None


@dataclass
class GalleryIndex:
    """O que a varredura achou no livro, em ordem de leitura."""

    source_pdf: str = ""
    created_at: str = ""
    reading_order: ReadingOrder = DEFAULT_READING_ORDER
    pages_scanned: int = 0
    entries: list[GalleryEntry] = field(default_factory=list)

    start_page: int = 0
    """Primeira página que esta varredura olhou (S-120)."""

    last_page_done: int = -1
    """Última página **terminada**, em base 0. `-1` é "nenhuma" (S-120).

    Terminada e não iniciada: o progresso é emitido depois de a página inteira ser lida, então
    retomar de `last_page_done + 1` não pula nem repete diagrama."""

    complete: bool = True
    """A varredura chegou ao fim do livro (S-120).

    **O defeito que estes três campos fecham é pior que o tempo perdido.** Uma queda ou um
    fechamento de janela no meio deixava um índice truncado **indistinguível de um completo** --
    e ele alimenta em silêncio a busca por posição, o censo e a fila, todos concluindo que o
    livro tem menos diagramas do que tem.

    O padrão é `True` e a leitura de um arquivo sem a chave também: um índice gravado antes
    deste item é tão confiável quanto era ontem, e marcá-lo parcial faria os 34 livros do
    acervo gritarem lobo de uma vez."""

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[GalleryEntry]:
        return iter(self.entries)

    def position_of(self, page_index: int, diagram_index: int = 0) -> int | None:
        """Posição na lista do diagrama daquela página, para a sincronia com o PDF.

        Com `diagram_index` inexistente devolve o **primeiro** diagrama da página em vez de
        `None`: quem virou a página no visualizador quer chegar nela, não descobrir que o
        terceiro diagrama não existe.
        """
        for posicao, entrada in enumerate(self.entries):
            if entrada.key == (page_index, diagram_index):
                return posicao
        for posicao, entrada in enumerate(self.entries):
            if entrada.page_index == page_index:
                return posicao
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "source_pdf": self.source_pdf,
            "created_at": self.created_at,
            "reading_order": self.reading_order,
            "pages_scanned": self.pages_scanned,
            "start_page": self.start_page,
            "last_page_done": self.last_page_done,
            "complete": self.complete,
            "entries": [entrada.to_dict() for entrada in self.entries],
        }

    @classmethod
    def from_dict(cls, dados: Any) -> GalleryIndex:
        if not isinstance(dados, dict):
            return cls()
        entradas = [GalleryEntry.from_dict(item) for item in (dados.get("entries") or [])]
        ordem = str(dados.get("reading_order") or DEFAULT_READING_ORDER)
        return cls(
            source_pdf=str(dados.get("source_pdf") or ""),
            created_at=str(dados.get("created_at") or ""),
            reading_order=ordem if ordem in ("row", "column") else DEFAULT_READING_ORDER,  # type: ignore[arg-type]
            pages_scanned=int(dados.get("pages_scanned") or 0),
            start_page=int(dados.get("start_page") or 0),
            last_page_done=int(dados.get("last_page_done", -1)),
            # Ausente e `True` sao a mesma coisa aqui, e o docstring do campo diz por que.
            complete=bool(dados.get("complete", True)),
            entries=[entrada for entrada in entradas if entrada is not None],
        )


def index_path_for(pdf_path: Path, *, directory: Path = DEFAULT_GALLERY_DIR) -> Path:
    """`data/gallery/<livro>.index.json`, ao lado das anotações do mesmo livro."""
    return Path(directory) / f"{Path(pdf_path).stem}.index.json"


def load_index(pdf_path: Path, *, directory: Path = DEFAULT_GALLERY_DIR) -> GalleryIndex | None:
    """O índice já varrido, ou `None` se não existe -- que é "varra o livro primeiro".

    `None` e índice vazio são coisas diferentes e a interface as trata diferente: um livro
    sem diagrama nenhum é um resultado, e nunca varrido é um convite a apertar o botão.
    """
    caminho = index_path_for(pdf_path, directory=directory)
    if not caminho.exists():
        return None
    try:
        return GalleryIndex.from_dict(json.loads(caminho.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Nao foi possivel ler %s (%s); tratando como nao varrido.", caminho, exc)
        return None


def save_index(pdf_path: Path, index: GalleryIndex, *, directory: Path = DEFAULT_GALLERY_DIR) -> Path:
    caminho = index_path_for(pdf_path, directory=directory)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(caminho, index.to_dict())
    return caminho


def build_gallery_index(
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
    cache_dir: Path = DEFAULT_CACHE_DIR,
    cancel_event: threading.Event | None = None,
    progress_callback: ProgressCallback | None = None,
    model_session: Any = None,
    now: str | None = None,
    resume_from: GalleryIndex | None = None,
) -> GalleryIndex:
    """Varre o livro e devolve **todos** os diagramas, sem gate e sem filtro de prioridade.

    Cancelar não é erro: o índice sai com o que deu tempo de varrer, e a interface diz até
    onde foi. Descartar o parcial faria a pessoa perder minutos de varredura por ter mudado
    de ideia -- a mesma razão do checkpoint da S-24.

    `resume_from` continua uma varredura interrompida (S-120): as entradas dele são mantidas e
    a leitura começa na página seguinte à última **terminada**. Um índice completo, ou de outra
    ordem de leitura, é ignorado -- no primeiro caso não há o que retomar, e no segundo a
    numeração de diagrama por página muda (S-14) e as entradas antigas descreveriam outros
    diagramas.
    """
    pdf_path = Path(pdf_source)
    entradas: list[GalleryEntry] = []
    paginas: set[int] = set()

    if resume_from is not None and not resume_from.complete and resume_from.reading_order == reading_order:
        entradas = list(resume_from.entries)
        paginas = {entrada.page_index for entrada in entradas}
        start_page = max(start_page, resume_from.last_page_done + 1)
        logger.info(
            "Retomando a varredura de %s da página %d: %d diagrama(s) já lidos (S-120).",
            pdf_path.name,
            start_page,
            len(entradas),
        )

    ultima_pronta = start_page - 1

    def _progresso(page_index: int, total: int, diagramas: int, aceitos: int) -> None:
        # O progresso e emitido **depois** de a pagina inteira ser lida, entao ele e a fonte
        # certa de `last_page_done` -- e a unica que enxerga pagina sem diagrama nenhum, que
        # nao produz entrada e mesmo assim foi varrida.
        nonlocal ultima_pronta
        ultima_pronta = max(ultima_pronta, page_index)
        if progress_callback is not None:
            progress_callback(page_index, total, diagramas, aceitos)

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
        progress_callback=_progresso,
        model_session=model_session,
    ):
        posicao = scanned.position
        paginas.add(posicao.page_index)
        imagem = cache_board_image(
            scanned.board_rgb, cache_dir, pdf_path.name, posicao.page_index, posicao.diagram_index
        )
        contexto = posicao.context
        entradas.append(
            GalleryEntry(
                page_index=posicao.page_index,
                diagram_index=posicao.diagram_index,
                placement=posicao.fen,
                side_to_move="w" if posicao.side_to_move is None else ("w" if posicao.side_to_move.color else "b"),
                side_to_move_source="default" if posicao.side_to_move is None else posicao.side_to_move.source,
                min_confidence=float(posicao.min_confidence or 0.0),
                is_legal=posicao.is_legal,
                image_path=str(imagem),
                caption=(contexto.caption if contexto is not None else "") or "",
            )
        )

    cancelada = cancel_event is not None and cancel_event.is_set()
    return GalleryIndex(
        source_pdf=str(pdf_path),
        created_at=now or datetime.now().isoformat(timespec="seconds"),
        reading_order=reading_order,
        pages_scanned=len(paginas),
        start_page=start_page,
        last_page_done=ultima_pronta,
        # `end_page` tambem trunca de proposito, e o indice resultante nao descreve o livro
        # inteiro: quem consome precisa saber disso tanto quanto no caso do cancelamento.
        complete=not cancelada and end_page is None,
        entries=entradas,
    )
