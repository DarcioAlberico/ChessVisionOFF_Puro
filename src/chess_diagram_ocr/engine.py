"""Motor de análise UCI (Stockfish), opcional (S-33).

**Por que opcional de verdade, e não "opcional mas na prática obrigatório".** O produto é um
OCR de diagramas; avaliar a posição é um extra útil. Sem binário instalado, o app funciona
igual e a seção some da tela -- não fica um botão cinza nem uma mensagem de erro a cada
abertura. `find_engine` procura, `EngineAnalyzer` só existe se achou.

**O processo fica aberto entre as análises.** Abrir e fechar o Stockfish a cada posição
custa ~100–300 ms de inicialização, o que sozinho já estouraria o "avaliação em menos de
2 s" do critério de aceite. O preço é ter de fechá-lo explicitamente ao sair -- daí o
`close()` e o suporte a `with`.

**O tempo é teto, não alvo.** `movetime` limita quanto o motor pensa; numa posição simples
ele responde antes. Preferido a `depth` fixo porque profundidade não tem relação estável
com tempo: 20 plies num final são instantâneos e num meio-jogo travado, não.

**O que este módulo não faz.** Não decide se a posição é plausível. A S-33 nota que uma
avaliação bizarra num livro de táticas sugere erro de OCR e poderia alimentar a fila da
S-22; isso é uma hipótese que precisa ser medida antes de virar prioridade, e medi-la exige
o motor instalado -- que não está nesta máquina. Fica registrado como o que é: não feito.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess
import chess.engine

logger = logging.getLogger(__name__)

ENV_ENGINE_PATH = "CVOFF_ENGINE_PATH"

DEFAULT_MOVETIME_MS = 800
"""Bem abaixo dos 2 s do critério de aceite da S-33, com folga para o custo de ida e volta
com o processo. Configurável para quem quiser análise mais funda."""

CANDIDATE_NAMES = ("stockfish", "stockfish.exe")

CANDIDATE_DIRS = (
    Path("engines"),
    Path("Stockfish"),
    Path("C:/Program Files/Stockfish"),
    Path("/usr/games"),
    Path("/usr/local/bin"),
)
"""Onde procurar além do `PATH`. A pasta `engines/` do projeto vem primeiro para que baixar
o binário ali seja a instalação mais simples possível."""


def find_engine(explicit: str | Path | None = None, *, env: dict[str, str] | None = None) -> Path | None:
    """Localiza o binário do motor, ou `None`. Nunca levanta: ausência é o caso normal.

    Ordem: o que foi pedido explicitamente, a variável de ambiente, o `PATH`, e por fim os
    diretórios conhecidos. O explícito vem primeiro porque quem informou um caminho quer
    aquele binário, e cair no do `PATH` em silêncio esconderia o erro de digitação.
    """
    ambiente = os.environ if env is None else env

    for candidato in (explicit, ambiente.get(ENV_ENGINE_PATH, "").strip() or None):
        if candidato:
            caminho = Path(candidato)
            if caminho.is_file():
                return caminho
            logger.warning("Motor informado nao existe: %s", caminho)
            return None

    for nome in CANDIDATE_NAMES:
        achado = shutil.which(nome)
        if achado:
            return Path(achado)

    for diretorio in CANDIDATE_DIRS:
        for nome in CANDIDATE_NAMES:
            caminho = diretorio / nome
            if caminho.is_file():
                return caminho
    return None


@dataclass(frozen=True)
class Evaluation:
    """O que o motor achou da posição, do ponto de vista das **brancas**.

    Normalizar para as brancas é o que faz a barra de vantagem ter um sentido só. O valor
    cru do UCI é relativo a quem joga, e mostrá-lo assim faria a barra pular de lado a cada
    lance sem que a posição tivesse mudado de dono.
    """

    score_cp: int | None
    """Centipeões, positivo para as brancas. `None` quando há mate anunciado."""

    mate_in: int | None
    """Lances até o mate, positivo se quem dá o mate são as brancas."""

    best_move: chess.Move | None
    best_move_san: str = ""
    pv_san: tuple[str, ...] = ()
    depth: int = 0
    elapsed_s: float = 0.0

    @property
    def is_mate(self) -> bool:
        return self.mate_in is not None

    def display(self) -> str:
        """A avaliação como se lê num tabuleiro: `+1,35`, `-0,40`, `M3`, `-M2`."""
        if self.mate_in is not None:
            return f"{'M' if self.mate_in > 0 else '-M'}{abs(self.mate_in)}"
        if self.score_cp is None:
            return "—"
        return f"{self.score_cp / 100:+.2f}".replace(".", ",")

    def advantage_fraction(self) -> float:
        """Posição da barra, de 0 (pretas ganhando) a 1 (brancas ganhando).

        A conversão é logística e não linear: a diferença entre +0,2 e +1,0 muda a partida,
        a diferença entre +8 e +12 não muda nada. Uma barra linear gastaria quase toda a
        sua extensão com vantagens já decididas.
        """
        if self.mate_in is not None:
            return 1.0 if self.mate_in > 0 else 0.0
        if self.score_cp is None:
            return 0.5
        # 1/(1+10^(-cp/400)) e a curva de expectativa de pontuacao do Elo, que e exatamente
        # a relacao entre vantagem e resultado que se quer mostrar.
        return 1.0 / (1.0 + 10 ** (-self.score_cp / 400.0))

    def summary(self) -> str:
        """Uma linha para a interface: avaliação, melhor lance e profundidade."""
        partes = [f"Avaliação: {self.display()}"]
        if self.best_move_san:
            partes.append(f"melhor lance: {self.best_move_san}")
        if self.depth:
            partes.append(f"profundidade {self.depth}")
        return "  |  ".join(partes)


def _to_white_pov(score: chess.engine.PovScore) -> tuple[int | None, int | None]:
    """Extrai `(centipeões, mate_em)` do ponto de vista das brancas."""
    brancas = score.white()
    mate = brancas.mate()
    if mate is not None:
        return None, int(mate)
    centipeoes = brancas.score()
    return (None, None) if centipeoes is None else (int(centipeoes), None)


class EngineAnalyzer:
    """Um processo de motor aberto, analisando posições sob demanda.

    Serializa o acesso com um lock: o protocolo UCI é uma conversa, e duas threads falando
    com o mesmo processo embaralham as respostas -- o resultado de uma análise chegaria
    como se fosse o da outra.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        movetime_ms: int = DEFAULT_MOVETIME_MS,
        threads: int = 1,
    ) -> None:
        self.path = Path(path)
        self.movetime_ms = int(movetime_ms)
        self._lock = threading.RLock()
        self._engine: chess.engine.SimpleEngine | None = None
        self._threads = max(1, int(threads))

    @property
    def name(self) -> str:
        motor = self._engine
        if motor is None:
            return self.path.name
        return str(motor.id.get("name", self.path.name))

    def start(self) -> None:
        with self._lock:
            if self._engine is not None:
                return
            logger.info("Abrindo motor de analise: %s", self.path)
            self._engine = chess.engine.SimpleEngine.popen_uci(str(self.path))
            try:
                self._engine.configure({"Threads": self._threads})
            except chess.engine.EngineError as exc:
                # Nem todo motor UCI aceita `Threads`; nao e motivo para desistir dele.
                logger.debug("Motor nao aceitou a opcao Threads: %s", exc)

    def close(self) -> None:
        with self._lock:
            if self._engine is None:
                return
            try:
                self._engine.quit()
            except Exception as exc:  # pragma: no cover - encerramento e best-effort
                logger.debug("Falha ao encerrar o motor: %s", exc)
            finally:
                self._engine = None

    def __enter__(self) -> EngineAnalyzer:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def analyse(self, board: chess.Board, *, movetime_ms: int | None = None) -> Evaluation:
        """Avalia a posição. Levanta `RuntimeError` se o motor não responder.

        Posição sem lance legal (mate ou afogamento) devolve avaliação sem melhor lance em
        vez de erro: é uma resposta legítima, e o motor não tem o que sugerir.
        """
        import time

        limite = chess.engine.Limit(time=(movetime_ms or self.movetime_ms) / 1000.0)
        inicio = time.monotonic()
        with self._lock:
            self.start()
            assert self._engine is not None
            try:
                info = self._engine.analyse(board, limite)
            except chess.engine.EngineError as exc:
                raise RuntimeError(f"O motor de analise falhou: {exc}") from exc

        return _avaliacao_de(board, info, elapsed_s=time.monotonic() - inicio)


    def analyse_multi(
        self, board: chess.Board, *, count: int = 3, movetime_ms: int | None = None
    ) -> list[Evaluation]:
        """As `count` melhores linhas, da melhor para a pior (S-286).

        **Uma linha diz "o motor prefere isto"; três dizem "estas são as opções"** -- e a segunda
        frase é a que um estudo precisa. Para quem lê um livro a pergunta quase nunca é qual é o
        melhor lance: é se o lance que o livro dá está entre os candidatos.

        `MultiPV` é opção UCI, e nem todo motor a aceita. Motor que recusa devolve **uma** linha em
        vez de erro: a degradação é a mesma que `start` já aplica a `Threads`, e é a regra do
        projeto desde a S-33 -- aparência não derruba ferramenta.

        A opção é reposta em 1 no fim. Deixá-la ligada faria a `analyse` seguinte -- que lê
        `info["pv"]` de um `dict` e não de uma lista -- receber outra forma de resposta.
        """
        quantas = max(1, int(count))
        limite = chess.engine.Limit(time=(movetime_ms or self.movetime_ms) / 1000.0)
        with self._lock:
            self.start()
            assert self._engine is not None
            try:
                infos = self._engine.analyse(board, limite, multipv=quantas)
            except chess.engine.EngineError as exc:
                raise RuntimeError(f"O motor de analise falhou: {exc}") from exc

        avaliacoes = [_avaliacao_de(board, info) for info in infos]
        return avaliacoes or [_avaliacao_de(board, {})]


def _avaliacao_de(board: chess.Board, info: Any, *, elapsed_s: float = 0.0) -> Evaluation:
    """Uma resposta do UCI virada `Evaluation`. É o mesmo molde para a linha única e para o MultiPV.

    Existe porque a S-286 precisava do mesmo desmonte duas vezes, e duas cópias dele divergiriam na
    primeira vez que um campo mudasse -- é o mecanismo que a S-31 registra para todo par de
    implementações da mesma coisa.
    """
    pontuacao = info.get("score")
    cp, mate = _to_white_pov(pontuacao) if pontuacao is not None else (None, None)
    pv = list(info.get("pv") or [])
    melhor = pv[0] if pv and board.is_legal(pv[0]) else None
    return Evaluation(
        score_cp=cp,
        mate_in=mate,
        best_move=melhor,
        best_move_san=board.san(melhor) if melhor is not None else "",
        pv_san=tuple(_variation_san(board, pv)),
        depth=int(str(info.get("depth") or 0)),
        elapsed_s=elapsed_s,
    )


def _variation_san(board: chess.Board, moves: list[chess.Move], *, limit: int = 6) -> list[str]:
    """A linha principal em notação algébrica, cortada em `limit` lances.

    Cortar não é economia de tela: uma variante de 30 plies de um motor a 800 ms é palpite
    depois dos primeiros lances, e mostrá-la inteira sugeriria uma certeza que não existe.
    """
    tabuleiro = board.copy(stack=False)
    saida: list[str] = []
    for lance in moves[:limit]:
        if not tabuleiro.is_legal(lance):
            break
        saida.append(tabuleiro.san(lance))
        tabuleiro.push(lance)
    return saida
