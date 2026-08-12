"""O estado e as regras do tabuleiro, sem Tk (S-50).

`InteractiveBoard` tinha três responsabilidades num objeto só: **estado** (posição, seleção,
pincel, arrasto), **sinais de diagnóstico** (heatmap, casas mudadas, casas problemáticas,
tooltip de três classes) e **desenho**. As funções puras de edição já tinham saído para
`board_edit.py` -- o que é bom e não bastava, porque o estado que as usa continuava dentro do
widget, e nada acima delas era testável sem janela.

Aqui está o meio-termo que faltava: um objeto que sabe o que está no tabuleiro e o que um
clique significa, e que não sabe desenhar. Clique → arrasta → solta passa a ser três chamadas
de método e uma asserção.

**`BoardChange` é o outro motivo do item.** Toda interação devolve as casas que mudaram, e é
isso que permite ao `BoardRenderer.draw_dirty` redesenhar 2 casas em vez de 64. Antes,
arrastar uma peça reconstruía o canvas inteiro a cada movimento do ponteiro.

O `chess.Board` mora aqui porque lance legal é regra e não desenho; `chess` não é `tkinter`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import chess
import numpy as np

from ..config import PIECE_CLASSES, UNCERTAIN_SQUARE_THRESHOLD
from ..fen_utils import reading_index_from_square as _reading_index
from ..fen_utils import square_from_reading_index as _chess_square
from ..fen_utils import square_name
from . import board_edit

logger = logging.getLogger(__name__)

BoardMode = Literal["play", "edit"]

__all__ = ["BoardChange", "BoardMode", "BoardModel", "ChangeKind"]


class ChangeKind(str, Enum):
    """O que a interação produziu. Quem observa reage a isto, não a sete flags."""

    NONE = "none"
    SELECTION = "selection"
    """Só a casa selecionada mudou. Nada da posição foi tocado."""

    PLACEMENT = "placement"
    """A posição mudou: peça inserida, apagada ou movida em modo de edição."""

    MOVE = "move"
    """Lance legal em modo de jogo. Quem decide o que fazer com ele é o dono do widget."""

    MESSAGE = "message"
    """Nada mudou, mas há o que dizer na barra de status."""


@dataclass(frozen=True)
class BoardChange:
    """O resultado de uma interação, incluindo **quais casas precisam ser redesenhadas**."""

    kind: ChangeKind = ChangeKind.NONE
    dirty: frozenset[int] = frozenset()
    placement: str | None = None
    move: chess.Move | None = None
    message: str = ""

    @property
    def touched_position(self) -> bool:
        return self.kind is ChangeKind.PLACEMENT

    def __bool__(self) -> bool:
        return self.kind is not ChangeKind.NONE


@dataclass
class BoardModel:
    """As 64 casas, a seleção, o pincel e os sinais do modelo -- e nenhum widget."""

    mode: BoardMode = "edit"
    board: chess.Board = field(default_factory=chess.Board)
    selected: int | None = None
    brush: str | None = None
    flipped: bool = False
    last_move: chess.Move | None = None

    confidences: tuple[float, ...] = ()
    """64 confianças em ordem de leitura, ou vazio quando não há heatmap."""

    probs: np.ndarray | None = None
    """Matriz (64, 13) da S-10, para as três classes mais prováveis por casa."""

    changed: frozenset[int] = frozenset()
    """Casas reescritas pela decodificação com restrições (S-11)."""

    problems: frozenset[int] = frozenset()
    """Casas apontadas pelo painel de legalidade (S-21)."""

    disputed: frozenset[int] = frozenset()
    """Casas em que a segunda leitura discorda da primeira (S-66).

    Sobrevive à edição de propósito, ao contrário de `changed`: a marca existe para dizer
    "confira aqui", e apagá-la ao primeiro clique tiraria da tela justamente a lista do que
    ainda falta conferir. Quem a limpa é quem a pôs -- ver `set_disputed`."""

    heatmap_enabled: bool = True
    uncertain_threshold: float = UNCERTAIN_SQUARE_THRESHOLD

    promotion_chooser: Callable[[], int | None] | None = None
    """Como perguntar a peça de promoção. Uma `Callable`, não um diálogo: em teste é um
    `lambda: chess.QUEEN`, e o modelo continua sem saber que existe uma janela."""

    def __post_init__(self) -> None:
        if self.mode not in ("play", "edit"):
            raise ValueError(f"mode deve ser 'play' ou 'edit'; recebido {self.mode!r}.")

    # ------------------------------------------------------------------------- consultas

    @property
    def placement(self) -> str:
        """Campo de peças da posição atual."""
        return self.board.board_fen()

    @property
    def fen(self) -> str:
        return self.board.fen()

    @property
    def side_to_move(self) -> chess.Color:
        return self.board.turn

    def squares(self) -> list[str]:
        """Os 64 símbolos em ordem de leitura; string vazia para casa vazia."""
        return board_edit.squares_from_placement(self.placement)

    def display_from_index(self, index: int) -> tuple[int, int]:
        """(linha, coluna) na tela, já considerando o tabuleiro girado."""
        row, col = divmod(index, 8)
        return (7 - row, 7 - col) if self.flipped else (row, col)

    def index_from_display(self, row: int, col: int) -> int:
        return (7 - row) * 8 + (7 - col) if self.flipped else row * 8 + col

    def legal_targets(self) -> frozenset[int]:
        """Casas alcançáveis pela peça selecionada. Vazio fora do modo de jogo."""
        if self.mode != "play" or self.selected is None:
            return frozenset()
        origem = _chess_square(self.selected)
        return frozenset(
            _reading_index(move.to_square) for move in self.board.legal_moves if move.from_square == origem
        )

    def last_move_squares(self) -> frozenset[int]:
        if self.last_move is None:
            return frozenset()
        return frozenset({_reading_index(self.last_move.from_square), _reading_index(self.last_move.to_square)})

    def heatmap_confidence(self, index: int) -> float | None:
        """Confiança da casa quando ela deve ser tingida, ou `None` quando não deve."""
        if not self.heatmap_enabled or len(self.confidences) != 64:
            return None
        valor = self.confidences[index]
        return valor if valor < self.uncertain_threshold else None

    def top_classes(self, index: int, count: int = 3) -> list[tuple[str, float]]:
        """As `count` classes mais prováveis de uma casa, para tooltip e testes."""
        if self.probs is None or not 0 <= index < 64:
            return []
        row = self.probs[index]
        order = np.argsort(row)[::-1][:count]
        return [(PIECE_CLASSES[int(position)], float(row[int(position)])) for position in order]

    # ------------------------------------------------------------------- entrada de dados

    def set_position(self, fen: str) -> bool:
        """Põe uma posição no modelo. `False` se a FEN não for interpretável.

        Aceita a FEN completa ou só o campo de peças. Em `mode="edit"` posições ilegais são
        bem-vindas: é o estado normal no meio de uma correção.
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
            logger.debug("FEN recusada pelo tabuleiro: %s", exc)
            return False

        self.board = board
        self.selected = None
        return True

    def set_uncertainty(self, per_square_conf: Sequence[float] | None) -> None:
        if per_square_conf is None:
            self.confidences = ()
            return
        values = [float(value) for value in per_square_conf]
        if len(values) != 64:
            raise ValueError(f"Esperadas 64 confianças, recebidas {len(values)}.")
        self.confidences = tuple(values)

    def set_probabilities(self, probs: np.ndarray | None) -> None:
        if probs is not None:
            probs = np.asarray(probs, dtype=float)
            if probs.shape != (64, len(PIECE_CLASSES)):
                raise ValueError(f"Esperada matriz (64, {len(PIECE_CLASSES)}), recebida {probs.shape}.")
        self.probs = probs

    def set_changed_squares(self, squares: Iterable[int]) -> None:
        self.changed = frozenset(int(index) for index in squares)

    def set_problem_squares(self, squares: Iterable[int]) -> None:
        self.problems = frozenset(int(index) for index in squares)

    def set_disputed_squares(self, squares: Iterable[int]) -> None:
        """Casas em que os dois leitores discordam (S-66). Sequência vazia apaga a marca."""
        self.disputed = frozenset(int(index) for index in squares)

    # ---------------------------------------------------------------------- interações

    def select(self, index: int | None) -> BoardChange:
        """Seleciona de fora -- é como a fila de revisão abre o item já na casa suspeita."""
        if index is not None and not 0 <= index < 64:
            raise ValueError(f"Índice de casa fora do intervalo 0..63: {index}")
        if index == self.selected:
            return BoardChange()
        sujas = {i for i in (self.selected, index) if i is not None}
        self.selected = index
        return BoardChange(kind=ChangeKind.SELECTION, dirty=frozenset(sujas))

    def press(self, index: int) -> BoardChange:
        """O botão desceu sobre uma casa. Pinta, seleciona, ou nada."""
        if not 0 <= index < 64:
            return BoardChange()

        if self.mode == "edit" and self.brush is not None:
            # Com pincel ativo o clique pinta e não arrasta: e o gesto de quem sabe qual peça
            # falta e onde, que e o caso comum ao corrigir leitura de OCR.
            return self.paint(index)

        symbol = board_edit.piece_at(self.placement, index)
        if not symbol:
            return BoardChange()
        if self.mode == "play" and chess.Piece.from_symbol(symbol).color != self.board.turn:
            return BoardChange()

        return self.select(index)

    def drop(self, index: int | None, *, allow_deselect: bool = True) -> BoardChange:
        """O botão subiu sobre `index` (ou fora do tabuleiro, com `None`)."""
        if index is None:
            return BoardChange(kind=ChangeKind.MESSAGE, message="Arraste cancelado.")
        if self.selected is None:
            return BoardChange()

        if index == self.selected:
            return self.select(None) if allow_deselect else BoardChange()

        if self.mode == "edit":
            origem = self.selected
            mudanca = self._apply_placement(
                board_edit.move_piece(self.placement, origem, index),
                dirty={origem, index},
                message=f"{square_name(origem)} → {square_name(index)}.",
            )
            self.selected = None
            return mudanca

        symbol = board_edit.piece_at(self.placement, index)
        if symbol and chess.Piece.from_symbol(symbol).color == self.board.turn:
            return self.select(index)

        return self._play_move_to(index)

    def paint(self, index: int) -> BoardChange:
        """Aplica o pincel na casa. `brush=""` apaga, `None` não é pincel.

        **Clicar de novo na mesma peça apaga.** Corrigir leitura de OCR é uma sequência de
        acertos e desacertos -- põe a torre, vê que era o bispo --, e sem alternância desfazer
        exigia largar o pincel, clicar com o direito e pegar o pincel de volta: três gestos
        para desfazer um. Com ela, pôr e tirar são o mesmo gesto.

        A alternância só vale para pincel de peça. Com o pincel "apagar", clicar de novo numa
        casa já vazia continua sendo nada -- alternar ali significaria *criar* uma peça, que é
        o oposto do que o botão diz que faz.
        """
        symbol = self.brush or None
        current = board_edit.piece_at(self.placement, index) or None

        if current == symbol:
            if symbol is None:
                return BoardChange()
            return self._apply_placement(
                board_edit.set_piece(self.placement, index, None),
                dirty={index},
                message=f"{square_name(index)} esvaziada (segundo clique com o mesmo pincel).",
            )

        mensagem = (
            f"{square_name(index)} esvaziada."
            if symbol is None
            else f"{board_edit.PIECE_NAMES_PT[symbol]} em {square_name(index)}."
        )
        return self._apply_placement(
            board_edit.set_piece(self.placement, index, symbol), dirty={index}, message=mensagem
        )

    def erase(self, index: int) -> BoardChange:
        """Botão direito, ou `Del` sobre a casa selecionada. Só faz sentido em edição."""
        if self.mode != "edit" or not 0 <= index < 64:
            return BoardChange()
        if not board_edit.piece_at(self.placement, index):
            return BoardChange()
        return self._apply_placement(
            board_edit.clear_square(self.placement, index),
            dirty={index},
            message=f"Peça removida de {square_name(index)}.",
        )

    def erase_selected(self) -> BoardChange:
        return BoardChange() if self.selected is None else self.erase(self.selected)

    def set_brush(self, symbol: str | None) -> str:
        """Troca o pincel e devolve a frase de status correspondente."""
        self.brush = symbol
        if symbol is None:
            return "Pincel desligado: clique arrasta peças."
        if symbol == "":
            return "Pincel: apagar. Clique numa casa para esvaziá-la."
        return f"Pincel: {board_edit.PIECE_NAMES_PT[symbol]}. Clique numa casa para inserir."

    # ------------------------------------------------------------------------- internos

    def _apply_placement(self, placement: str, *, dirty: set[int], message: str = "") -> BoardChange:
        self.board.set_board_fen(placement)
        # A correção inválida os sinais do modelo: a confiança era da leitura antiga, e
        # deixa-la na tela afirmaria algo sobre uma casa que o usuário acabou de reescrever.
        antes = set(self.changed) | {i for i, c in enumerate(self.confidences) if c < self.uncertain_threshold}
        self.confidences = ()
        self.probs = None
        self.changed = frozenset()
        return BoardChange(
            kind=ChangeKind.PLACEMENT,
            dirty=frozenset(dirty | antes),
            placement=placement,
            message=message,
        )

    def _play_move_to(self, target: int) -> BoardChange:
        assert self.selected is not None
        origem, destino = _chess_square(self.selected), _chess_square(target)
        candidatos = [
            move for move in self.board.legal_moves if move.from_square == origem and move.to_square == destino
        ]
        if not candidatos:
            return BoardChange(kind=ChangeKind.MESSAGE, message="Lance ilegal para a posição atual.")

        move = candidatos[0]
        if len(candidatos) > 1:
            promocao = self.promotion_chooser() if self.promotion_chooser is not None else chess.QUEEN
            if promocao is None:
                return BoardChange(kind=ChangeKind.MESSAGE, message="Promoção cancelada.")
            escolhido = next((item for item in candidatos if item.promotion == promocao), None)
            if escolhido is None:
                return BoardChange(kind=ChangeKind.MESSAGE, message="Promoção inválida.")
            move = escolhido

        anterior = self.selected
        self.selected = None
        return BoardChange(kind=ChangeKind.MOVE, dirty=frozenset({anterior, target}), move=move)
