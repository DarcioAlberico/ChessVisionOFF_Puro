"""Motor UCI mínimo, para exercitar o caminho da S-33 sem Stockfish instalado.

Não joga xadrez: responde os primeiros lances legais e uma avaliação fixa. O que ele prova é o
que interessa testar aqui -- que o `EngineAnalyzer` abre um processo, conversa em UCI,
normaliza a pontuação para o ponto de vista das brancas e devolve a linha em SAN.

Existe como arquivo separado porque `SimpleEngine.popen_uci` precisa de um **processo**:
não há como fingir isso com um objeto em memória sem reimplementar o transporte.

**Ele declara opções desde a S-536**, e sem isso metade daquele item não seria afirmável: o
`SimpleEngine.configure` do `python-chess` levanta `EngineError` para opção que o motor não
anunciou, então um motor sem `option name Hash` faria o teste de "trocar Hash não derruba o
processo" medir o caminho de degradação em vez do caminho normal. O que ele recebe fica em
`OPCOES`, e um `info string opcoes ...` na resposta seguinte deixa o teste ler o que pegou.
"""

from __future__ import annotations

import sys

import chess

# Fixos e distintos entre si para que o teste saiba de onde veio cada numero.
SCORE_CP = 35
DEPTH = 12
NODES = 123_456
NPS = 654_321
ENGINE_NAME = "FakeEngine 1.0"

OPCOES: dict[str, str] = {"Hash": "16", "Threads": "1", "MultiPV": "1", "SyzygyPath": ""}
"""O que o motor recebeu por `setoption`, com os padrões que ele anuncia no `uci`."""


def _responder(linha: str, board: chess.Board) -> chess.Board:
    partes = linha.split()
    if not partes:
        return board

    comando = partes[0]
    if comando == "uci":
        print(f"id name {ENGINE_NAME}")
        print("id author testes")
        # As quatro opcoes que a S-536 mexe. `configure` recusa o que nao esta declarado aqui.
        print("option name Hash type spin default 16 min 1 max 4096")
        print("option name Threads type spin default 1 min 1 max 64")
        print("option name MultiPV type spin default 1 min 1 max 10")
        print("option name SyzygyPath type string default <empty>")
        print("uciok", flush=True)
    elif comando == "isready":
        print("readyok", flush=True)
    elif comando == "setoption":
        _guardar_opcao(partes)
    elif comando == "position":
        board = _posicao(partes)
    elif comando == "go":
        _analisar(board, partes)
    return board


def _guardar_opcao(partes: list[str]) -> None:
    """`setoption name Hash value 512`. Valor ausente é a forma do botão, e vira string vazia."""
    if "name" not in partes:
        return
    inicio = partes.index("name") + 1
    fim = partes.index("value") if "value" in partes else len(partes)
    nome = " ".join(partes[inicio:fim])
    valor = " ".join(partes[fim + 1 :]) if "value" in partes else ""
    OPCOES[nome] = valor


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


def _analisar(board: chess.Board, partes: list[str]) -> None:
    legais = list(board.legal_moves)
    profundidade = _profundidade(partes)
    if not legais:
        # Mate ou afogamento: o UCI manda `bestmove (none)`, e o analisador tem de aguentar.
        print(f"info depth {profundidade} score mate 0")
        print("bestmove (none)", flush=True)
        return

    # As opcoes que pegaram, para o teste as ler sem abrir um segundo canal com o processo.
    print(f"info string opcoes {OPCOES}")
    quantas = max(1, min(int(OPCOES.get("MultiPV", "1") or 1), len(legais)))
    for indice in range(quantas):
        escolhido = legais[indice]
        # A pontuacao do UCI e relativa a quem joga; devolver sempre +SCORE_CP e o que faz o
        # teste conseguir verificar que a normalizacao para as brancas inverte o sinal. As linhas
        # seguintes valem menos, que e a ordem que o MultiPV promete.
        pontos = SCORE_CP - 10 * indice
        cabeca = f"info depth {profundidade} nodes {NODES} nps {NPS}"
        multipv = f" multipv {indice + 1}" if quantas > 1 else ""
        print(f"{cabeca}{multipv} score cp {pontos} pv {escolhido.uci()}")
    print(f"bestmove {legais[0].uci()}", flush=True)


def _profundidade(partes: list[str]) -> int:
    """`go depth N` responde N; o resto responde o fixo. É o que a S-537 pede por lance."""
    if "depth" in partes:
        try:
            return int(partes[partes.index("depth") + 1])
        except (IndexError, ValueError):  # pragma: no cover - forma que ninguem manda
            return DEPTH
    return DEPTH


def main() -> None:
    board = chess.Board()
    for linha in sys.stdin:
        linha = linha.strip()
        if linha == "quit":
            return
        board = _responder(linha, board)


if __name__ == "__main__":
    main()
