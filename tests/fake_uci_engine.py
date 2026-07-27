"""Motor UCI mínimo, para exercitar o caminho da S-33 sem Stockfish instalado.

Não joga xadrez: responde o primeiro lance legal e uma avaliação fixa. O que ele prova é o
que interessa testar aqui -- que o `EngineAnalyzer` abre um processo, conversa em UCI,
normaliza a pontuação para o ponto de vista das brancas e devolve a linha em SAN.

Existe como arquivo separado porque `SimpleEngine.popen_uci` precisa de um **processo**:
não há como fingir isso com um objeto em memória sem reimplementar o transporte.
"""

from __future__ import annotations

import sys

import chess

# Fixos e distintos entre si para que o teste saiba de onde veio cada numero.
SCORE_CP = 35
DEPTH = 12
ENGINE_NAME = "FakeEngine 1.0"


def _responder(linha: str, board: chess.Board) -> chess.Board:
    partes = linha.split()
    if not partes:
        return board

    comando = partes[0]
    if comando == "uci":
        print(f"id name {ENGINE_NAME}")
        print("id author testes")
        print("uciok", flush=True)
    elif comando == "isready":
        print("readyok", flush=True)
    elif comando == "position":
        board = _posicao(partes)
    elif comando == "go":
        _analisar(board)
    return board


def _posicao(partes: list[str]) -> chess.Board:
    board = chess.Board()
    if "fen" in partes:
        i = partes.index("fen")
        fim = partes.index("moves") if "moves" in partes else len(partes)
        board = chess.Board(" ".join(partes[i + 1 : fim]))
    if "moves" in partes:
        for uci in partes[partes.index("moves") + 1 :]:
            board.push(chess.Move.from_uci(uci))
    return board


def _analisar(board: chess.Board) -> None:
    legais = list(board.legal_moves)
    if not legais:
        # Mate ou afogamento: o UCI manda `bestmove (none)`, e o analisador tem de aguentar.
        print(f"info depth {DEPTH} score mate 0")
        print("bestmove (none)", flush=True)
        return

    escolhido = legais[0]
    # A pontuacao do UCI e relativa a quem joga; devolver sempre +SCORE_CP e o que faz o
    # teste conseguir verificar que a normalizacao para as brancas inverte o sinal.
    print(f"info depth {DEPTH} score cp {SCORE_CP} pv {escolhido.uci()}")
    print(f"bestmove {escolhido.uci()}", flush=True)


def main() -> None:
    board = chess.Board()
    for linha in sys.stdin:
        linha = linha.strip()
        if linha == "quit":
            return
        board = _responder(linha, board)


if __name__ == "__main__":
    main()
