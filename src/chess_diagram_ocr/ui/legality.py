"""Painel de legalidade: o problema em pt-BR **e onde ele está** (S-21).

`check_position` já devolve "falta o rei preto" em vez de `Status.NO_BLACK_KING`, o que
resolve metade do item. A outra metade é a que o usuário de fato precisa: um tabuleiro de
64 casas com "mais de um rei da mesma cor" ainda deixa a pergunta "qual dos dois eu
apago?" -- e responder isso à mão é comparar o diagrama casa por casa com o PDF, que é
exatamente o custo que a Fase 4 existe para cortar.

Então cada problema vem com as casas culpadas, em ordem de leitura (0 = a8), prontas para
o `InteractiveBoard` destacar.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import chess

from ..fen_utils import PositionCheck, check_position, reading_index_from_square, square_name


@dataclass(frozen=True)
class LegalityProblem:
    """Uma violação, o texto dela e as casas que a causam."""

    text: str
    squares: tuple[int, ...]
    """Índices em ordem de leitura. Vazio quando não há o que apontar (rei *faltando*)."""

    fatal: bool
    """Independe do lado a jogar: é erro de reconhecimento, não palpite de vez errado."""

    def describe(self) -> str:
        if not self.squares:
            return self.text
        names = ", ".join(square_name(index) for index in self.squares)
        return f"{self.text} ({names})"


@dataclass(frozen=True)
class LegalityExplanation:
    """O que dizer ao usuário sobre a legalidade da posição que está na tela."""

    fen: str
    is_legal: bool
    is_fatal: bool
    problems: tuple[LegalityProblem, ...]
    piece_counts: dict[str, int]
    """Contagem por símbolo FEN (`K`, `p`, ...). Só o que existe no tabuleiro."""

    @property
    def label(self) -> str:
        """Os mesmos três estados do PGN (`DiagramPosition.legality_label`)."""
        if self.is_legal:
            return "legal"
        return "ilegal" if self.is_fatal else "lado a jogar"

    @property
    def highlight_squares(self) -> tuple[int, ...]:
        """União das casas culpadas, para o tabuleiro marcar de uma vez."""
        seen: dict[int, None] = {}
        for problem in self.problems:
            for index in problem.squares:
                seen[index] = None
        return tuple(seen)

    def summary(self) -> str:
        if self.is_legal:
            return "Posição legal."
        detail = "; ".join(problem.describe() for problem in self.problems)
        if self.is_fatal:
            return f"Posição ilegal: {detail}"
        # Sem lado a jogar declarado o pipeline assume brancas; um xeque "invertido" aqui
        # costuma significar que a vez era das pretas, e não que o tabuleiro esta errado.
        return f"Só o lado a jogar não fecha: {detail}"

    def material_line(self) -> str:
        """Material em uma linha, na ordem de valor. Serve para achar peça sobrando."""
        white = " ".join(f"{symbol}×{self.piece_counts[symbol]}" for symbol in "KQRBNP" if self.piece_counts.get(symbol))
        black = " ".join(f"{symbol}×{self.piece_counts[symbol]}" for symbol in "kqrbnp" if self.piece_counts.get(symbol))
        return f"brancas: {white or '—'} | pretas: {black or '—'}"


def _reading_indices(squares: Iterable[chess.Square]) -> tuple[int, ...]:
    return tuple(sorted(reading_index_from_square(square) for square in squares))


def _kings(board: chess.Board, color: chess.Color) -> tuple[int, ...]:
    return _reading_indices(board.pieces(chess.KING, color))


def _pawns_on_backrank(board: chess.Board) -> tuple[int, ...]:
    backranks = chess.BB_RANK_1 | chess.BB_RANK_8
    return _reading_indices(chess.scan_forward(board.pawns & backranks))


def _check_squares(board: chess.Board, color: chess.Color) -> tuple[int, ...]:
    """Rei em xeque da cor dada, mais quem está dando o xeque."""
    king = board.king(color)
    if king is None:
        return ()
    attackers = board.attackers(not color, king)
    return _reading_indices([king, *chess.scan_forward(int(attackers))])


def _problems_for(board: chess.Board, status: chess.Status) -> tuple[LegalityProblem, ...]:
    """Traduz o status em problemas com casas. A ordem é a do impacto: fatal primeiro."""
    problems: list[LegalityProblem] = []

    def add(flag: chess.Status, text: str, squares: tuple[int, ...], *, fatal: bool) -> None:
        if status & flag:
            problems.append(LegalityProblem(text=text, squares=squares, fatal=fatal))

    add(chess.STATUS_EMPTY, "tabuleiro vazio", (), fatal=True)
    add(chess.STATUS_NO_WHITE_KING, "falta o rei branco", (), fatal=True)
    add(chess.STATUS_NO_BLACK_KING, "falta o rei preto", (), fatal=True)
    if status & chess.STATUS_TOO_MANY_KINGS:
        # So aponta a cor que de fato duplicou: marcar os quatro reis mandaria o usuário
        # conferir dois que estao certos.
        squares = tuple(
            sorted(
                index
                for color in (chess.WHITE, chess.BLACK)
                if len(board.pieces(chess.KING, color)) > 1
                for index in _kings(board, color)
            )
        )
        problems.append(LegalityProblem(text="mais de um rei da mesma cor", squares=squares, fatal=True))
    add(
        chess.STATUS_TOO_MANY_WHITE_PAWNS,
        "peões brancos demais",
        _reading_indices(board.pieces(chess.PAWN, chess.WHITE)),
        fatal=True,
    )
    add(
        chess.STATUS_TOO_MANY_BLACK_PAWNS,
        "peões pretos demais",
        _reading_indices(board.pieces(chess.PAWN, chess.BLACK)),
        fatal=True,
    )
    add(
        chess.STATUS_TOO_MANY_WHITE_PIECES,
        "peças brancas demais",
        _reading_indices(chess.scan_forward(int(board.occupied_co[chess.WHITE]))),
        fatal=True,
    )
    add(
        chess.STATUS_TOO_MANY_BLACK_PIECES,
        "peças pretas demais",
        _reading_indices(chess.scan_forward(int(board.occupied_co[chess.BLACK]))),
        fatal=True,
    )
    add(chess.STATUS_PAWNS_ON_BACKRANK, "peão na primeira ou na oitava fila", _pawns_on_backrank(board), fatal=True)

    add(
        chess.STATUS_OPPOSITE_CHECK,
        "o lado que não joga está em xeque",
        _check_squares(board, not board.turn),
        fatal=False,
    )
    add(chess.STATUS_TOO_MANY_CHECKERS, "peças demais dando xeque", _check_squares(board, board.turn), fatal=False)
    add(
        chess.STATUS_IMPOSSIBLE_CHECK,
        "configuração de xeque impossível",
        _check_squares(board, board.turn),
        fatal=False,
    )
    return tuple(problems)


def explain_position(fen: str) -> LegalityExplanation:
    """Diagnóstico completo da posição, pronto para o painel de legalidade da S-21."""
    check: PositionCheck = check_position(fen)
    try:
        board = chess.Board(check.fen)
    except (ValueError, AttributeError, TypeError):
        return LegalityExplanation(
            fen=check.fen,
            is_legal=False,
            is_fatal=True,
            problems=(LegalityProblem(text="FEN não pôde ser interpretada", squares=(), fatal=True),),
            piece_counts={},
        )

    counts: dict[str, int] = {}
    for piece in board.piece_map().values():
        symbol = piece.symbol()
        counts[symbol] = counts.get(symbol, 0) + 1

    return LegalityExplanation(
        fen=check.fen,
        is_legal=check.is_legal,
        is_fatal=check.is_fatal,
        problems=_problems_for(board, check.status),
        piece_counts=counts,
    )


ILLEGAL_SAVE_TITLE = "Posição ilegal"


def illegal_save_question(fen: str) -> str | None:
    """O que perguntar antes de gravar esta posição, ou `None` quando não há o que perguntar.

    **Por que perguntar em vez de recusar.** A recusa vinha de uma premissa que vale para
    quase todo diagrama e não vale para todos: a de que uma posição sem os dois reis é uma
    leitura errada. Num livro ela é, quase sempre. Mas um capítulo de estrutura de peões
    desenha o esqueleto sem rei nenhum de propósito, um estudo de final mostra três peças, e
    um tabuleiro vazio ilustra as coordenadas -- e nesses três o rótulo certo é justamente o
    que o programa se recusava a gravar. Quem sabe de qual dos dois casos se trata é a pessoa
    que está com o PDF aberto do lado, e a única coisa que faltava era perguntar a ela.

    Fica aqui, e não dentro do painel, pela regra que organizou a Fase 6: a caixa de diálogo é
    da janela, mas *quando* perguntar e *o que dizer* dá para testar sem abrir uma.

    Só o fatal pergunta. "O lado que não joga está em xeque" nunca chegou a bloquear gravação
    -- é palpite sobre o turno, não sobre as peças --, e transformá-lo em pergunta poria uma
    caixa no caminho de um salvamento que sempre funcionou.
    """
    explicacao = explain_position(fen)
    if not explicacao.is_fatal:
        return None

    detalhe = "; ".join(problem.describe() for problem in explicacao.problems if problem.fatal)
    return (
        f"Esta posição é ilegal: {detalhe}.\n\n"
        f"{explicacao.material_line()}\n\n"
        "Se o diagrama é assim mesmo -- estrutura de peões, final parcial, tabuleiro de "
        "ilustração --, salvar está correto e a amostra entra no treino marcada como "
        "confirmada.\n"
        "Se foi o leitor que errou uma casa, cancele e conserte o tabuleiro.\n\n"
        "Salvar mesmo assim?"
    )
