"""Tabuleiro interativo reaproveitável, em dois modos (S-20) e com heatmap (S-21).

O app já tinha um tabuleiro com arraste funcionando -- na aba "Análise", para jogar lances
legais. E, ao mesmo tempo, corrigir um diagrama reconhecido significava editar a string FEN
num `ttk.Entry`: contar casas, achar o caractere certo, digitar. O widget existia e não
estava onde o trabalho acontece.

Este módulo tira o tabuleiro de lá e o parametriza por modo:

- `mode="play"` -- o comportamento da aba de análise: só lance legal, alvos marcados,
  promoção perguntada. Quem decide o que fazer com o lance é o dono do widget, via
  `on_move`; a árvore de variantes continua fora daqui.
- `mode="edit"` -- correção de OCR: clique move sem perguntar de quem é a vez, botão
  direito apaga, paleta lateral insere. A cada mudança sai `on_change(campo_de_peças)`.

E sobre o modo de edição vem o heatmap da S-21: `set_uncertainty` pinta as casas em que o
modelo está inseguro, `set_probabilities` alimenta o tooltip com as três classes mais
prováveis, e `set_changed_squares` marca o que a decodificação restrita reparou. O ponto é
que o usuário pare de comparar 64 casas com o PDF e olhe as três que importam -- a média
de confiança fica em 0,97 mesmo com erro (S-10), então sem isso não há onde olhar.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from functools import partial
from pathlib import Path
from tkinter import ttk
from typing import Literal

import chess
import numpy as np
from PIL import Image, ImageTk

from ..config import PIECE_CLASSES, UNCERTAIN_SQUARE_THRESHOLD
from ..fen_utils import reading_index_from_square as _reading_index
from ..fen_utils import square_from_reading_index as _chess_square
from ..fen_utils import square_name
from . import board_edit

logger = logging.getLogger(__name__)

BoardMode = Literal["play", "edit"]

LIGHT_SQUARE = "#f0d9b5"
DARK_SQUARE = "#b58863"
SELECTED_SQUARE = "#f7ec74"
LAST_MOVE_SQUARE = "#cdd26a"
TARGET_MARK = "#3f7f4c"
CHANGED_OUTLINE = "#3d7dd4"
PROBLEM_OUTLINE = "#c0392b"

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

CLASS_NAMES_PT: dict[str, str] = {"empty": "casa vazia", **board_edit.PIECE_NAMES_PT}


class PieceImages:
    """Cache de imagens de peça por tamanho, com fallback para símbolo Unicode.

    Estava embutido no `app_tkinter`; virou classe porque agora há mais de um tabuleiro na
    tela e recarregar/redimensionar PNG por tabuleiro seria desperdício visível ao arrastar.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._sources: dict[str, Image.Image] = {}
        self._cache: dict[tuple[str, int], ImageTk.PhotoImage] = {}
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
        key = f"{'w' if symbol.isupper() else 'b'}{symbol.lower()}"
        source = self._sources.get(key)
        if source is None:
            return None

        size = max(12, int(cell * 0.86))
        cached = self._cache.get((key, size))
        if cached is not None:
            return cached

        resized = source.resize((size, size), resample=Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(resized)
        self._cache[(key, size)] = photo
        return photo


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


class InteractiveBoard(ttk.Frame):
    """Tabuleiro de 64 casas com clique e arraste, em modo de jogo ou de edição."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        mode: BoardMode = "play",
        on_change: Callable[[str], None] | None = None,
        on_move: Callable[[chess.Move], None] | None = None,
        on_select: Callable[[int | None], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        promotion_chooser: Callable[[], int | None] | None = None,
        piece_images: PieceImages | None = None,
        show_palette: bool | None = None,
        show_coordinates: bool = True,
        min_size: int = 240,
        max_size: int = 560,
        background: str = "#262421",
        uncertain_threshold: float = UNCERTAIN_SQUARE_THRESHOLD,
    ) -> None:
        super().__init__(parent)
        if mode not in ("play", "edit"):
            raise ValueError(f"mode deve ser 'play' ou 'edit'; recebido {mode!r}.")

        self.mode: BoardMode = mode
        self._on_change = on_change
        self._on_move = on_move
        self._on_select = on_select
        self._on_status = on_status
        self._promotion_chooser = promotion_chooser
        self._images = piece_images
        self._show_coordinates = show_coordinates
        self._min_size = min_size
        self._max_size = max_size
        self._uncertain_threshold = uncertain_threshold

        self.board = chess.Board()
        self._flipped = False
        self._selected: int | None = None
        self._last_move: chess.Move | None = None
        self._confidences: list[float] | None = None
        self._probabilities: np.ndarray | None = None
        self._changed_squares: set[int] = set()
        self._problem_squares: set[int] = set()
        self._heatmap_enabled = True
        self._brush: str | None = None
        self._geometry: dict[str, float] = {}

        self._drag_from: int | None = None
        self._drag_symbol: str | None = None
        self._drag_pointer: tuple[float, float] | None = None
        self._drag_start: tuple[float, float] | None = None
        self._dragging = False
        self._press_selected_new = False

        self._tooltip: tk.Toplevel | None = None
        self._tooltip_after: str | None = None
        self._tooltip_square: int | None = None

        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _event: self._hide_tooltip())

        self.palette: ttk.Frame | None = None
        if show_palette if show_palette is not None else mode == "edit":
            self.palette = self._build_palette()

    # ------------------------------------------------------------------ estado

    @property
    def placement(self) -> str:
        """Campo de peças da posição na tela."""
        return self.board.board_fen()

    @property
    def fen(self) -> str:
        return self.board.fen()

    @property
    def selected_square(self) -> int | None:
        """Casa selecionada, em ordem de leitura (0 = a8)."""
        return self._selected

    def set_position(self, fen: str) -> bool:
        """Põe uma posição na tela. Devolve `False` se a FEN não for interpretável.

        Aceita tanto a FEN completa quanto só o campo de peças. Em `mode="edit"` posições
        ilegais são bem-vindas: é o estado normal no meio de uma correção.
        """
        text = str(fen).strip()
        if not text:
            return False

        placement = board_edit.placement_of(text)
        if not board_edit.is_valid_placement(placement):
            return False

        board = chess.Board()
        try:
            if " " in text:
                board.set_fen(text)
            else:
                board.set_board_fen(placement)
        except ValueError as exc:
            logger.debug("FEN recusada pelo tabuleiro interativo: %s", exc)
            return False

        self.board = board
        self._selected = None
        self._clear_drag()
        self.redraw()
        return True

    def set_side_to_move(self, color: chess.Color) -> None:
        if self.board.turn != color:
            self.board.turn = color
            self.redraw()

    def set_last_move(self, move: chess.Move | None) -> None:
        self._last_move = move
        self.redraw()

    def set_flipped(self, flipped: bool) -> None:
        self._flipped = bool(flipped)
        self.redraw()

    @property
    def flipped(self) -> bool:
        return self._flipped

    def select_square(self, index: int | None) -> None:
        """Seleciona uma casa de fora do widget -- é como a fila de revisão abre o item já
        apontando para a casa suspeita (S-22)."""
        if index is not None and not 0 <= index < 64:
            raise ValueError(f"Índice de casa fora do intervalo 0..63: {index}")
        self._selected = index
        self._notify_select()
        self.redraw()

    def clear_selection(self) -> None:
        if self._selected is not None:
            self._selected = None
            self._notify_select()
            self.redraw()

    def delete_selected(self) -> bool:
        """Apaga a peça da casa selecionada (tecla `Del`). Só faz sentido em edição."""
        if self.mode != "edit" or self._selected is None:
            return False
        index = self._selected
        if not board_edit.piece_at(self.placement, index):
            return False
        self._apply_placement(board_edit.clear_square(self.placement, index))
        self._status(f"Peça removida de {square_name(index)}.")
        return True

    # ------------------------------------------------------------- S-21: sinais

    def set_uncertainty(self, per_square_conf: Sequence[float] | None) -> None:
        """Confiança de cada casa, em ordem de leitura. `None` desliga o heatmap."""
        if per_square_conf is None:
            self._confidences = None
        else:
            values = [float(value) for value in per_square_conf]
            if len(values) != 64:
                raise ValueError(f"Esperadas 64 confianças, recebidas {len(values)}.")
            self._confidences = values
        self.redraw()

    def set_probabilities(self, probs: np.ndarray | None) -> None:
        """Matriz (64, 13) da S-10, para o tooltip mostrar as três classes mais prováveis."""
        if probs is not None:
            probs = np.asarray(probs, dtype=float)
            if probs.shape != (64, len(PIECE_CLASSES)):
                raise ValueError(f"Esperada matriz (64, {len(PIECE_CLASSES)}), recebida {probs.shape}.")
        self._probabilities = probs

    def set_changed_squares(self, squares: Iterable[int]) -> None:
        """Casas reescritas pela decodificação com restrições (S-11): contorno azul."""
        self._changed_squares = {int(index) for index in squares}
        self.redraw()

    def set_problem_squares(self, squares: Iterable[int]) -> None:
        """Casas apontadas pelo painel de legalidade (S-21): contorno vermelho."""
        self._problem_squares = {int(index) for index in squares}
        self.redraw()

    def set_heatmap_enabled(self, enabled: bool) -> None:
        self._heatmap_enabled = bool(enabled)
        self.redraw()

    @property
    def heatmap_enabled(self) -> bool:
        return self._heatmap_enabled

    def top_classes(self, index: int, count: int = 3) -> list[tuple[str, float]]:
        """As `count` classes mais prováveis de uma casa, para tooltip e testes."""
        if self._probabilities is None or not 0 <= index < 64:
            return []
        row = self._probabilities[index]
        order = np.argsort(row)[::-1][:count]
        return [(PIECE_CLASSES[int(position)], float(row[int(position)])) for position in order]

    # ------------------------------------------------------------------ paleta

    def _build_palette(self) -> ttk.Frame:
        frame = ttk.Frame(self)
        frame.pack(fill=tk.X, pady=(4, 0))

        for row_index, symbols in enumerate((board_edit.PIECE_SYMBOLS[:6], board_edit.PIECE_SYMBOLS[6:])):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X)
            for symbol in symbols:
                button = ttk.Button(
                    row,
                    text=UNICODE_PIECES.get(symbol, symbol),
                    width=3,
                    command=partial(self.set_brush, symbol),
                )
                button.pack(side=tk.LEFT, padx=1, pady=1)
            if row_index == 1:
                ttk.Button(row, text="Apagar", width=8, command=lambda: self.set_brush("")).pack(side=tk.LEFT, padx=(8, 1))
                ttk.Button(row, text="Sem pincel", width=11, command=lambda: self.set_brush(None)).pack(side=tk.LEFT, padx=1)
        return frame

    def set_brush(self, symbol: str | None) -> None:
        """Peça que o próximo clique insere. `""` apaga, `None` volta ao modo arrastar."""
        self._brush = symbol
        if symbol is None:
            self._status("Pincel desligado: clique arrasta peças.")
        elif symbol == "":
            self._status("Pincel: apagar. Clique numa casa para esvaziá-la.")
        else:
            self._status(f"Pincel: {board_edit.PIECE_NAMES_PT[symbol]}. Clique numa casa para inserir.")

    @property
    def brush(self) -> str | None:
        return self._brush

    # ------------------------------------------------------------ interação

    def _index_from_xy(self, x: float, y: float) -> int | None:
        geom = self._geometry
        if not geom:
            return None
        origin_x, origin_y, size, cell = geom["origin_x"], geom["origin_y"], geom["size"], geom["cell"]
        if not (origin_x <= x < origin_x + size and origin_y <= y < origin_y + size):
            return None
        col = int((x - origin_x) // cell)
        row = int((y - origin_y) // cell)
        if not (0 <= row <= 7 and 0 <= col <= 7):
            return None
        return self._index_from_display(row, col)

    def _index_from_display(self, row: int, col: int) -> int:
        if self._flipped:
            return (7 - row) * 8 + (7 - col)
        return row * 8 + col

    def _display_from_index(self, index: int) -> tuple[int, int]:
        row, col = divmod(index, 8)
        if self._flipped:
            return 7 - row, 7 - col
        return row, col

    def _on_press(self, event: tk.Event) -> None:
        self.canvas.focus_set()
        self._hide_tooltip()
        index = self._index_from_xy(event.x, event.y)
        self._drag_pointer = (event.x, event.y)
        self._drag_start = (event.x, event.y)
        self._drag_from = index
        self._dragging = False
        self._press_selected_new = False
        self._drag_symbol = None

        if index is None:
            return

        if self.mode == "edit" and self._brush is not None:
            # Com pincel ativo o clique pinta e não arrasta: e o gesto de quem sabe qual peça
            # falta e onde, que e o caso comum ao corrigir leitura de OCR.
            self._paint(index)
            self._drag_from = None
            return

        symbol = board_edit.piece_at(self.placement, index)
        if not symbol:
            return
        if self.mode == "play" and chess.Piece.from_symbol(symbol).color != self.board.turn:
            return

        self._press_selected_new = self._selected != index
        self._selected = index
        self._drag_symbol = symbol
        self._notify_select()
        self.redraw()

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_symbol is None or self._drag_from is None:
            return
        self._drag_pointer = (event.x, event.y)
        if not self._dragging:
            cell = max(1.0, float(self._geometry.get("cell", 1.0)))
            start_x, start_y = self._drag_start or self._drag_pointer
            if abs(event.x - start_x) < cell * 0.12 and abs(event.y - start_y) < cell * 0.12:
                return
            self._dragging = True
        self.redraw()

    def _on_release(self, event: tk.Event) -> None:
        target = self._index_from_xy(event.x, event.y)
        allow_deselect = (not self._dragging) and (not self._press_selected_new)
        self._handle_square_action(target, allow_deselect=allow_deselect)
        self._clear_drag()
        self.redraw()

    def _on_right_click(self, event: tk.Event) -> None:
        if self.mode != "edit":
            return
        index = self._index_from_xy(event.x, event.y)
        if index is None or not board_edit.piece_at(self.placement, index):
            return
        self._apply_placement(board_edit.clear_square(self.placement, index))
        self._status(f"Peça removida de {square_name(index)}.")

    def _handle_square_action(self, index: int | None, *, allow_deselect: bool) -> None:
        if index is None:
            if self._dragging:
                self._status("Arraste cancelado.")
            return

        if self._selected is None:
            return

        if index == self._selected and allow_deselect:
            self._selected = None
            self._notify_select()
            return

        if self.mode == "edit":
            if index == self._selected:
                return
            self._apply_placement(board_edit.move_piece(self.placement, self._selected, index))
            self._status(f"{square_name(self._selected)} → {square_name(index)}.")
            self._selected = None
            self._notify_select()
            return

        symbol = board_edit.piece_at(self.placement, index)
        if symbol and chess.Piece.from_symbol(symbol).color == self.board.turn:
            self._selected = index
            self._notify_select()
            return

        if not self._play_move_to(index):
            self._status("Lance ilegal para a posição atual.")

    def _paint(self, index: int) -> None:
        symbol = self._brush or None
        current = board_edit.piece_at(self.placement, index)
        if (current or None) == symbol:
            return
        self._apply_placement(board_edit.set_piece(self.placement, index, symbol))
        if symbol is None:
            self._status(f"{square_name(index)} esvaziada.")
        else:
            self._status(f"{board_edit.PIECE_NAMES_PT[symbol]} em {square_name(index)}.")

    def _play_move_to(self, target: int) -> bool:
        if self._selected is None:
            return False
        from_square = _chess_square(self._selected)
        to_square = _chess_square(target)
        candidates = [
            move for move in self.board.legal_moves if move.from_square == from_square and move.to_square == to_square
        ]
        if not candidates:
            return False

        move = candidates[0]
        if len(candidates) > 1:
            promotion = self._promotion_chooser() if self._promotion_chooser is not None else chess.QUEEN
            if promotion is None:
                self._status("Promoção cancelada.")
                return True
            chosen = next((item for item in candidates if item.promotion == promotion), None)
            if chosen is None:
                self._status("Promoção inválida.")
                return True
            move = chosen

        self._selected = None
        self._notify_select()
        if self._on_move is not None:
            self._on_move(move)
        return True

    def _apply_placement(self, placement: str) -> None:
        self.board.set_board_fen(placement)
        # A correção inválida os sinais do modelo: a confiança era da leitura antiga, e
        # deixa-la na tela afirmaria algo sobre uma casa que o usuário acabou de reescrever.
        self._confidences = None
        self._probabilities = None
        self._changed_squares.clear()
        self.redraw()
        if self._on_change is not None:
            self._on_change(placement)

    def _clear_drag(self) -> None:
        self._drag_from = None
        self._drag_symbol = None
        self._drag_pointer = None
        self._drag_start = None
        self._dragging = False
        self._press_selected_new = False

    def _notify_select(self) -> None:
        if self._on_select is not None:
            self._on_select(self._selected)

    def _status(self, text: str) -> None:
        if self._on_status is not None:
            self._on_status(text)

    # ------------------------------------------------------------------ tooltip

    def _on_motion(self, event: tk.Event) -> None:
        if self._probabilities is None or self._dragging:
            self._hide_tooltip()
            return
        index = self._index_from_xy(event.x, event.y)
        if index != self._tooltip_square:
            self._hide_tooltip()
            self._tooltip_square = index
            if index is not None:
                self._tooltip_after = self.canvas.after(350, lambda: self._show_tooltip(event.x_root, event.y_root))

    def _show_tooltip(self, x_root: int, y_root: int) -> None:
        self._tooltip_after = None
        index = self._tooltip_square
        if index is None or self._probabilities is None:
            return

        lines = [square_name(index)]
        for class_name, probability in self.top_classes(index):
            lines.append(f"{CLASS_NAMES_PT.get(class_name, class_name)}: {probability * 100:.1f}%")

        tip = tk.Toplevel(self.canvas)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x_root + 14}+{y_root + 14}")
        tk.Label(
            tip,
            text="\n".join(lines),
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=6,
            pady=4,
        ).pack()
        self._tooltip = tip

    def _hide_tooltip(self) -> None:
        if self._tooltip_after is not None:
            self.canvas.after_cancel(self._tooltip_after)
            self._tooltip_after = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._tooltip_square = None

    # ------------------------------------------------------------------ desenho

    def redraw(self) -> None:
        canvas = self.canvas
        try:
            canvas_w = max(self._min_size, canvas.winfo_width())
            canvas_h = max(self._min_size, canvas.winfo_height())
        except tk.TclError:
            return

        margin = 28 if self._show_coordinates else 8
        size = max(self._min_size, min(canvas_w - margin, canvas_h - margin, self._max_size))
        cell = size / 8
        origin_x = (canvas_w - size) / 2
        origin_y = (canvas_h - size) / 2
        self._geometry = {"origin_x": origin_x, "origin_y": origin_y, "size": size, "cell": cell}

        canvas.delete("all")
        canvas.create_rectangle(origin_x - 2, origin_y - 2, origin_x + size + 2, origin_y + size + 2, fill="#312e2b", outline="")

        last_move_squares: set[int] = set()
        if self._last_move is not None:
            last_move_squares = {_reading_index(self._last_move.from_square), _reading_index(self._last_move.to_square)}

        legal_targets: set[int] = set()
        if self.mode == "play" and self._selected is not None:
            from_square = _chess_square(self._selected)
            legal_targets = {
                _reading_index(move.to_square) for move in self.board.legal_moves if move.from_square == from_square
            }

        squares = board_edit.squares_from_placement(self.placement)
        for index in range(64):
            row, col = self._display_from_index(index)
            x0 = origin_x + col * cell
            y0 = origin_y + row * cell
            x1, y1 = x0 + cell, y0 + cell

            base = LIGHT_SQUARE if (index // 8 + index % 8) % 2 == 0 else DARK_SQUARE
            if index in last_move_squares:
                base = LAST_MOVE_SQUARE
            if index == self._selected:
                base = SELECTED_SQUARE
            canvas.create_rectangle(x0, y0, x1, y1, fill=base, outline=base)

            self._draw_heatmap(index, x0, y0, x1, y1)

            if index in self._problem_squares:
                canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=PROBLEM_OUTLINE, width=3)
            elif index in self._changed_squares:
                canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=CHANGED_OUTLINE, width=2, dash=(4, 3))

            if self._dragging and index == self._drag_from:
                continue

            symbol = squares[index]
            if symbol:
                self._draw_piece(symbol, x0 + cell / 2, y0 + cell / 2, cell)
            elif index in legal_targets:
                radius = max(6, int(cell * 0.12))
                canvas.create_oval(
                    x0 + cell / 2 - radius,
                    y0 + cell / 2 - radius,
                    x0 + cell / 2 + radius,
                    y0 + cell / 2 + radius,
                    fill=TARGET_MARK,
                    outline="",
                )

        for target in legal_targets:
            if not squares[target]:
                continue
            row, col = self._display_from_index(target)
            x0 = origin_x + col * cell
            y0 = origin_y + row * cell
            canvas.create_rectangle(x0 + 4, y0 + 4, x0 + cell - 4, y0 + cell - 4, outline=TARGET_MARK, width=2)

        if self._show_coordinates:
            self._draw_coordinates(origin_x, origin_y, size, cell)

        if self._dragging and self._drag_symbol is not None and self._drag_pointer is not None:
            self._draw_piece(self._drag_symbol, self._drag_pointer[0], self._drag_pointer[1], cell)

    def _draw_heatmap(self, index: int, x0: float, y0: float, x1: float, y1: float) -> None:
        if not self._heatmap_enabled or self._confidences is None:
            return
        confidence = self._confidences[index]
        if confidence >= self._uncertain_threshold:
            return
        color = heatmap_color(confidence, self._uncertain_threshold)
        # `stipple` e o único jeito de tingir sem apagar a casa no canvas do Tk, que não tem
        # canal alfa: a peça por baixo continua legivel.
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color, stipple="gray50")
        self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=color, width=2)

    def _draw_piece(self, symbol: str, center_x: float, center_y: float, cell: float) -> None:
        photo = self._images.photo(symbol, int(cell)) if self._images is not None else None
        if photo is not None:
            self.canvas.create_image(center_x, center_y, image=photo)
            return
        self.canvas.create_text(
            center_x,
            center_y,
            text=UNICODE_PIECES.get(symbol, symbol),
            fill="#111111",
            font=("Segoe UI Symbol", max(12, int(cell * 0.56))),
        )

    def _draw_coordinates(self, origin_x: float, origin_y: float, size: float, cell: float) -> None:
        files = "hgfedcba" if self._flipped else "abcdefgh"
        ranks = "12345678" if self._flipped else "87654321"
        for index, char in enumerate(files):
            self.canvas.create_text(
                origin_x + index * cell + cell / 2,
                origin_y + size + 11,
                text=char,
                fill="#d8d8d8",
                font=("Segoe UI", 9, "bold"),
            )
        for index, char in enumerate(ranks):
            self.canvas.create_text(
                origin_x - 10,
                origin_y + index * cell + cell / 2,
                text=char,
                fill="#d8d8d8",
                font=("Segoe UI", 9, "bold"),
            )
