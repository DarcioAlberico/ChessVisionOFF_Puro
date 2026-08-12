"""O desenho do tabuleiro no canvas do Tk, e só ele (S-50).

Duas consequências, e as duas são o motivo do item:

**`draw_dirty` acaba com o redesenho total.** `InteractiveBoard.redraw()` reconstruía as 64
casas, as coordenadas e a moldura a cada mudança -- inclusive a cada movimento do ponteiro
durante um arraste. `BoardChange.dirty` diz quais casas mudaram, e arrastar uma peça toca 2.

**Este é o único arquivo a reescrever numa troca de framework.** O `BoardModel` serve ao Tk,
a uma cena Qt e ao Streamlit igualmente; o que é específico do canvas está aqui. É a metade
barata da S-53, e a razão de ela poder ser adiada por gatilho em vez de por gosto.

Cada casa desenha com a tag `sq{índice}`, e é isso que torna o redesenho parcial possível:
apagar por tag e redesenhar. O item arrastado tem tag própria e é reerguido no fim, porque
redesenhar uma casa põe itens novos por cima dele.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageTk

from ..config import UNCERTAIN_SQUARE_THRESHOLD
from .board_model import BoardModel

logger = logging.getLogger(__name__)

__all__ = ["BoardGeometry", "BoardRenderer", "PieceImages", "heatmap_color"]

LIGHT_SQUARE = "#f0d9b5"
DARK_SQUARE = "#b58863"
SELECTED_SQUARE = "#f7ec74"
LAST_MOVE_SQUARE = "#cdd26a"
TARGET_MARK = "#3f7f4c"
CHANGED_OUTLINE = "#3d7dd4"
PROBLEM_OUTLINE = "#c0392b"
DISPUTED_OUTLINE = "#8e44ad"
"""Roxo: as duas leituras discordam desta casa (S-66).

Cor própria, e não o vermelho da ilegalidade nem o azul da decodificação: as três dizem
coisas diferentes e podem acender juntas. "Ilegal" é um fato sobre a posição, "reescrita" é
algo que já aconteceu, e "em disputa" é um pedido -- olhe esta casa."""
BOARD_FRAME = "#312e2b"
COORDINATE_TEXT = "#d8d8d8"

HEATMAP_LOW = (0xF2, 0xC7, 0x44)
"""Amarelo: casa logo abaixo do limiar."""

HEATMAP_HIGH = (0xD6, 0x45, 0x45)
"""Vermelho: casa em que o modelo praticamente não tem opinião."""

UNICODE_PIECES = {
    "P": "♙",
    "N": "♘",
    "B": "♗",
    "R": "♖",
    "Q": "♕",
    "K": "♔",
    "p": "♟",
    "n": "♞",
    "b": "♝",
    "r": "♜",
    "q": "♛",
    "k": "♚",
}

DRAG_TAG = "cvoff-drag"
FRAME_TAG = "cvoff-frame"
COORDS_TAG = "cvoff-coords"


def heatmap_color(confidence: float, threshold: float = UNCERTAIN_SQUARE_THRESHOLD) -> str:
    """Cor da casa em função da confiança: amarelo no limiar, vermelho no chão.

    A escala é relativa ao limiar e não a 0..1 porque a faixa que interessa é estreita:
    medido, casa certa fica em ~0,999 e casa errada em ~0,75. Espalhar a rampa por 0..1
    deixaria todo o erro na mesma tonalidade.
    """
    span = max(threshold, 1e-6)
    ratio = 1.0 - max(0.0, min(1.0, confidence / span))
    red, green, blue = (
        int(low + (high - low) * ratio) for low, high in zip(HEATMAP_LOW, HEATMAP_HIGH, strict=True)
    )
    return f"#{red:02x}{green:02x}{blue:02x}"


@dataclass(frozen=True)
class BoardGeometry:
    """Onde o tabuleiro está no canvas. Puro cálculo, testável sem Tk."""

    origin_x: float
    origin_y: float
    size: float
    cell: float

    @classmethod
    def fit(cls, width: float, height: float, *, min_size: int, max_size: int, margin: int) -> BoardGeometry:
        size = max(min_size, min(width - margin, height - margin, max_size))
        return cls(origin_x=(width - size) / 2, origin_y=(height - size) / 2, size=size, cell=size / 8)

    def rect(self, row: int, col: int) -> tuple[float, float, float, float]:
        x0 = self.origin_x + col * self.cell
        y0 = self.origin_y + row * self.cell
        return x0, y0, x0 + self.cell, y0 + self.cell

    def display_at(self, x: float, y: float) -> tuple[int, int] | None:
        """(linha, coluna) sob o ponteiro, ou `None` fora do tabuleiro."""
        if not (self.origin_x <= x < self.origin_x + self.size and self.origin_y <= y < self.origin_y + self.size):
            return None
        col = int((x - self.origin_x) // self.cell)
        row = int((y - self.origin_y) // self.cell)
        return (row, col) if 0 <= row <= 7 and 0 <= col <= 7 else None


class PieceImages:
    """Cache de imagens de peça por tamanho, com fallback para símbolo Unicode.

    Estava embutido no `app_tkinter`; virou classe porque agora há mais de um tabuleiro na
    tela e recarregar/redimensionar PNG por tabuleiro seria desperdício visível ao arrastar.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._sources: dict[str, Image.Image] = {}
        self._cache: dict[tuple[str, int, str | None], ImageTk.PhotoImage] = {}
        self._load_sources()

    def _load_sources(self) -> None:
        for color_code in ("w", "b"):
            for piece_code in ("p", "n", "b", "r", "q", "k"):
                key = f"{color_code}{piece_code}"
                path = self.directory / f"{key}.png"
                if not path.exists():
                    continue
                try:
                    with Image.open(path) as img:
                        self._sources[key] = img.convert("RGBA")
                except (OSError, ValueError) as exc:
                    logger.warning("Imagem de peça inválida em %s: %s", path, exc)

    def photo(self, symbol: str, cell: int) -> ImageTk.PhotoImage | None:
        """Imagem da peça para uma casa de `cell` pixels. `None` cai no Unicode."""
        return self.icon(symbol, max(12, int(cell * 0.86)))

    def icon(self, symbol: str, size: int, *, background: str | None = None) -> ImageTk.PhotoImage | None:
        """Imagem da peça no tamanho exato pedido, para fora do tabuleiro.

        A paleta de edição usa isto: os símbolos Unicode (`♙♘♗`) dependem de a máquina ter
        uma fonte que os desenhe, e no Windows a `Segoe UI Symbol` os renderiza pequenos,
        finos e de altura irregular -- as brancas quase somem sobre o fundo claro do botão.
        As peças do `assets/piece_images/` são as mesmas que aparecem no tabuleiro, então a
        paleta passa a mostrar exatamente o que o clique vai colocar.

        `background` acha a peça sobre uma cor opaca em vez do fundo do widget, e a paleta o
        usa com a cor da casa clara. Não é enfeite: os PNGs são traço preto com transparência,
        e num dos 15 temas escuros do `ttkbootstrap` as seis peças pretas somem no fundo da
        janela. Sobre casa clara elas aparecem em qualquer tema -- e é assim que elas se
        parecem no tabuleiro, que é o que a paleta está prometendo.
        """
        key = f"{'w' if symbol.isupper() else 'b'}{symbol.lower()}"
        source = self._sources.get(key)
        if source is None:
            return None

        size = max(8, int(size))
        cached = self._cache.get((key, size, background))
        if cached is not None:
            return cached

        resized = source.resize((size, size), resample=Image.Resampling.LANCZOS)
        if background is not None:
            tile = Image.new("RGBA", (size, size), background)
            tile.alpha_composite(resized)
            resized = tile

        photo = ImageTk.PhotoImage(resized)
        self._cache[(key, size, background)] = photo
        return photo


@dataclass(frozen=True)
class DragOverlay:
    """A peça que está sob o ponteiro durante um arraste, e a casa de onde ela saiu."""

    symbol: str
    x: float
    y: float
    origin: int


class BoardRenderer:
    """Pinta um `BoardModel` num `tk.Canvas`. Não guarda estado de tabuleiro."""

    def __init__(
        self,
        *,
        images: PieceImages | None = None,
        show_coordinates: bool = True,
    ) -> None:
        self.images = images
        self.show_coordinates = show_coordinates

    def draw(
        self,
        canvas: tk.Canvas,
        model: BoardModel,
        geometry: BoardGeometry,
        *,
        drag: DragOverlay | None = None,
    ) -> None:
        """Redesenha tudo. Só é preciso quando a geometria ou a posição inteira mudam."""
        canvas.delete("all")
        canvas.create_rectangle(
            geometry.origin_x - 2,
            geometry.origin_y - 2,
            geometry.origin_x + geometry.size + 2,
            geometry.origin_y + geometry.size + 2,
            fill=BOARD_FRAME,
            outline="",
            tags=(FRAME_TAG,),
        )
        self._draw_squares(canvas, model, geometry, range(64), drag=drag)
        if self.show_coordinates:
            self._draw_coordinates(canvas, model, geometry)
        self._draw_drag(canvas, geometry, drag)

    def draw_dirty(
        self,
        canvas: tk.Canvas,
        model: BoardModel,
        geometry: BoardGeometry,
        squares: Iterable[int],
        *,
        drag: DragOverlay | None = None,
    ) -> None:
        """Redesenha só as casas afetadas. `BoardChange.dirty` diz quais são."""
        indices = [index for index in squares if 0 <= index < 64]
        if not indices:
            self._draw_drag(canvas, geometry, drag)
            return
        for index in indices:
            canvas.delete(self._tag(index))
        self._draw_squares(canvas, model, geometry, indices, drag=drag)
        # Uma casa recem-desenhada fica por cima de tudo que ja estava no canvas, inclusive
        # da peca arrastada e das coordenadas -- dai o reerguer.
        canvas.tag_raise(COORDS_TAG)
        self._draw_drag(canvas, geometry, drag)

    # -------------------------------------------------------------------------- internos

    @staticmethod
    def _tag(index: int) -> str:
        return f"cvoff-sq{index}"

    def _draw_squares(
        self,
        canvas: tk.Canvas,
        model: BoardModel,
        geometry: BoardGeometry,
        indices: Iterable[int],
        *,
        drag: DragOverlay | None,
    ) -> None:
        squares = model.squares()
        last_move = model.last_move_squares()
        targets = model.legal_targets()

        for index in indices:
            tag = self._tag(index)
            row, col = model.display_from_index(index)
            x0, y0, x1, y1 = geometry.rect(row, col)
            cell = geometry.cell

            base = LIGHT_SQUARE if (index // 8 + index % 8) % 2 == 0 else DARK_SQUARE
            if index in last_move:
                base = LAST_MOVE_SQUARE
            if index == model.selected:
                base = SELECTED_SQUARE
            canvas.create_rectangle(x0, y0, x1, y1, fill=base, outline=base, tags=(tag,))

            confidence = model.heatmap_confidence(index)
            if confidence is not None:
                color = heatmap_color(confidence, model.uncertain_threshold)
                # `stipple` e o único jeito de tingir sem apagar a casa no canvas do Tk, que
                # não tem canal alfa: a peça por baixo continua legivel.
                canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color, stipple="gray50", tags=(tag,))
                canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=color, width=2, tags=(tag,))

            if index in model.problems:
                canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=PROBLEM_OUTLINE, width=3, tags=(tag,))
            elif index in model.changed:
                canvas.create_rectangle(
                    x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=CHANGED_OUTLINE, width=2, dash=(4, 3), tags=(tag,)
                )

            if index in model.disputed:
                # Contorno de dentro, e nao `elif`: a casa em disputa e justamente a que tem
                # mais chance de ser tambem ilegal ou reescrita, e esconder um sinal atras do
                # outro apagaria a coincidencia que interessa ver.
                canvas.create_rectangle(
                    x0 + 5, y0 + 5, x1 - 5, y1 - 5, outline=DISPUTED_OUTLINE, width=2, tags=(tag,)
                )

            if drag is not None and index == drag.origin:
                # A peca esta sob o ponteiro; desenha-la tambem na origem seria mostra-la duas
                # vezes, que e o sintoma classico de arraste sem estado.
                continue

            symbol = squares[index]
            if symbol:
                self._draw_piece(canvas, symbol, x0 + cell / 2, y0 + cell / 2, cell, tags=(tag,))
                if index in targets:
                    canvas.create_rectangle(
                        x0 + 4, y0 + 4, x0 + cell - 4, y0 + cell - 4, outline=TARGET_MARK, width=2, tags=(tag,)
                    )
            elif index in targets:
                radius = max(6, int(cell * 0.12))
                canvas.create_oval(
                    x0 + cell / 2 - radius,
                    y0 + cell / 2 - radius,
                    x0 + cell / 2 + radius,
                    y0 + cell / 2 + radius,
                    fill=TARGET_MARK,
                    outline="",
                    tags=(tag,),
                )

    def _draw_piece(
        self, canvas: tk.Canvas, symbol: str, center_x: float, center_y: float, cell: float, *, tags: tuple[str, ...]
    ) -> None:
        photo = self.images.photo(symbol, int(cell)) if self.images is not None else None
        if photo is not None:
            canvas.create_image(center_x, center_y, image=photo, tags=tags)
            return
        canvas.create_text(
            center_x,
            center_y,
            text=UNICODE_PIECES.get(symbol, symbol),
            fill="#111111",
            font=("Segoe UI Symbol", max(12, int(cell * 0.56))),
            tags=tags,
        )

    def _draw_coordinates(self, canvas: tk.Canvas, model: BoardModel, geometry: BoardGeometry) -> None:
        files = "hgfedcba" if model.flipped else "abcdefgh"
        ranks = "12345678" if model.flipped else "87654321"
        for index, char in enumerate(files):
            canvas.create_text(
                geometry.origin_x + index * geometry.cell + geometry.cell / 2,
                geometry.origin_y + geometry.size + 11,
                text=char,
                fill=COORDINATE_TEXT,
                font=("Segoe UI", 9, "bold"),
                tags=(COORDS_TAG,),
            )
        for index, char in enumerate(ranks):
            canvas.create_text(
                geometry.origin_x - 10,
                geometry.origin_y + index * geometry.cell + geometry.cell / 2,
                text=char,
                fill=COORDINATE_TEXT,
                font=("Segoe UI", 9, "bold"),
                tags=(COORDS_TAG,),
            )

    def _draw_drag(self, canvas: tk.Canvas, geometry: BoardGeometry, drag: DragOverlay | None) -> None:
        canvas.delete(DRAG_TAG)
        if drag is None:
            return
        self._draw_piece(canvas, drag.symbol, drag.x, drag.y, geometry.cell, tags=(DRAG_TAG,))
