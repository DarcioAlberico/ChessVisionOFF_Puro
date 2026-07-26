"""Edição de posição sem regra de lance: mover, pôr e tirar peça (S-20).

O modo de edição não é o modo de jogo com a validação desligada. São dois modelos
diferentes: no de jogo o que existe é `chess.Move`, e a peça só vai para onde a regra
deixa; na correção de um OCR o usuário precisa pôr um bispo preto em h1 se foi isso que o
livro imprimiu -- e vai precisar, porque metade das correções é justamente uma peça que o
modelo leu na casa errada ou trocou de cor.

Por isso a operação daqui é sobre o **campo de peças da FEN**, e não sobre `chess.Board`:
posição sem rei, com dois reis brancos ou com peão na oitava fila são estados intermediários
normais no meio de uma correção, e um modelo que os recusa obriga o usuário a corrigir na
ordem certa em vez de na ordem que ele enxerga o erro.

Índices são sempre em ordem de leitura (0 = a8, 63 = h1) -- a mesma da saída do modelo,
de `labels_from_fen` e de `square_name`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..config import PIECE_CLASSES

EMPTY_PLACEMENT = "8/8/8/8/8/8/8/8"

PIECE_SYMBOLS: tuple[str, ...] = tuple(name for name in PIECE_CLASSES if name != "empty")
"""Os 12 símbolos da paleta, na ordem de `PIECE_CLASSES` (brancas depois pretas)."""

PIECE_NAMES_PT: dict[str, str] = {
    "P": "peão branco",
    "N": "cavalo branco",
    "B": "bispo branco",
    "R": "torre branca",
    "Q": "dama branca",
    "K": "rei branco",
    "p": "peão preto",
    "n": "cavalo preto",
    "b": "bispo preto",
    "r": "torre preta",
    "q": "dama preta",
    "k": "rei preto",
}


def placement_of(fen: str) -> str:
    """Só o campo de peças, aceitando FEN completa ou já só o campo."""
    return str(fen).strip().split(" ")[0]


def squares_from_placement(placement: str) -> list[str]:
    """As 64 casas em ordem de leitura; casa vazia é string vazia.

    Levanta `ValueError` em campo malformado -- quem edita precisa saber que a FEN digitada
    no campo de texto não descreve um tabuleiro, e não receber 64 casas inventadas.
    """
    rows = placement_of(placement).split("/")
    if len(rows) != 8:
        raise ValueError("O campo de peças da FEN deve ter 8 filas.")

    squares: list[str] = []
    for row in rows:
        expanded: list[str] = []
        for char in row:
            if char.isdigit():
                expanded.extend([""] * int(char))
            elif char in PIECE_NAMES_PT:
                expanded.append(char)
            else:
                raise ValueError(f"Símbolo inválido no campo de peças: {char!r}")
        if len(expanded) != 8:
            raise ValueError("Cada fila da FEN deve resolver para 8 casas.")
        squares.extend(expanded)
    return squares


def placement_from_squares(squares: Sequence[str]) -> str:
    """Inversa de `squares_from_placement`."""
    if len(squares) != 64:
        raise ValueError("Esperadas exatamente 64 casas.")

    rows: list[str] = []
    for start in range(0, 64, 8):
        chunks: list[str] = []
        empty = 0
        for symbol in squares[start : start + 8]:
            if not symbol:
                empty += 1
                continue
            if empty:
                chunks.append(str(empty))
                empty = 0
            chunks.append(symbol)
        if empty:
            chunks.append(str(empty))
        rows.append("".join(chunks))
    return "/".join(rows)


def piece_at(placement: str, index: int) -> str:
    """Símbolo na casa, ou string vazia."""
    _check_index(index)
    return squares_from_placement(placement)[index]


def set_piece(placement: str, index: int, symbol: str | None) -> str:
    """Põe (ou tira, com `None`) uma peça numa casa. Não valida legalidade."""
    _check_index(index)
    if symbol is not None and symbol not in PIECE_NAMES_PT:
        raise ValueError(f"Símbolo de peça desconhecido: {symbol!r}")
    squares = squares_from_placement(placement)
    squares[index] = symbol or ""
    return placement_from_squares(squares)


def move_piece(placement: str, from_index: int, to_index: int) -> str:
    """Move a peça de uma casa para outra, sobrescrevendo o que estiver no destino.

    Origem vazia devolve a posição intacta: arrastar de casa vazia não é erro do usuário,
    é o gesto de quem errou o alvo por um pixel.
    """
    _check_index(from_index)
    _check_index(to_index)
    if from_index == to_index:
        return placement_of(placement)

    squares = squares_from_placement(placement)
    moving = squares[from_index]
    if not moving:
        return placement_from_squares(squares)
    squares[from_index] = ""
    squares[to_index] = moving
    return placement_from_squares(squares)


def clear_square(placement: str, index: int) -> str:
    return set_piece(placement, index, None)


def differing_squares(before: str, after: str) -> tuple[int, ...]:
    """Casas em que duas posições discordam, em ordem de leitura.

    É como o painel de resultado mostra o que a correção manual mudou em relação ao que o
    modelo leu -- e como a S-11 marca o que a decodificação restrita reparou.
    """
    left = squares_from_placement(before)
    right = squares_from_placement(after)
    return tuple(index for index in range(64) if left[index] != right[index])


def counts_by_symbol(placement: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for symbol in squares_from_placement(placement):
        if symbol:
            counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def is_valid_placement(placement: str) -> bool:
    try:
        squares_from_placement(placement)
        return True
    except ValueError:
        return False


def apply_edits(placement: str, edits: Iterable[tuple[int, str | None]]) -> str:
    """Aplica uma sequência de (casa, símbolo) de uma vez. Útil para desfazer em bloco."""
    squares = squares_from_placement(placement)
    for index, symbol in edits:
        _check_index(index)
        if symbol is not None and symbol not in PIECE_NAMES_PT:
            raise ValueError(f"Símbolo de peça desconhecido: {symbol!r}")
        squares[index] = symbol or ""
    return placement_from_squares(squares)


def _check_index(index: int) -> None:
    if not 0 <= index < 64:
        raise ValueError(f"Índice de casa fora do intervalo 0..63: {index}")
