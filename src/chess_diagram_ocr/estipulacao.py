"""A estipulação do problema como evidência sobre a posição (C12 do ciclo 2 OCR/UI).

Um livro de problemas imprime a exigência ao lado do diagrama -- ``#2``, ``3‡``, ``Mate in
two``, ``Matt in 3 Zügen``, ``mate em 2``, ``mat en 3`` --, e a exigência é **verificável**: ou
a posição lida tem um mate forçado em N lances ou não tem. A S-33 registrou a hipótese («uma
avaliação bizarra num livro de táticas sugere erro de OCR») como não feita; o C11 (``lance_
seguinte``) construiu o mecanismo para o lance impresso; este módulo é o mesmo mecanismo com
outro predicado: em vez de jogar a linha impressa, joga-se a **exigência**.

**O que faz.** ``parse_estipulacao`` lê a exigência de uma linha de legenda (só mate direto;
ajudado ``h#``, inverso ``s#`` e reflexo ``r#`` são recusados de propósito -- as regras são
outras). ``verificar`` decide se a posição lida a cumpre: mate em 1–2 por busca exaustiva em
``python-chess`` (ordem de 10³ nós, determinística, sem dependência), mate em 3–4 pelo motor
UCI quando ``engine.find_engine`` o acha (``go mate N`` com teto de tempo) e «não verificado
(sem motor)» quando não. ``conferir`` tenta, quando não fecha, as **mesmas candidatas do C11**
(``lance_seguinte._candidatas``: a segunda opção das casas hesitantes, a cor de qualquer peça) e
adota a troca **única** que faz fechar. ``apply_stipulation`` é a costura para ``service`` e
``pdf_to_pgn``, no molde de ``apply_next_move``.

**O que não faz.** Não inventa: as trocas vêm da matriz, nunca de uma casa segura contra a
qual só a exigência fala. Não decide sozinho: duas trocas que fechem são empate, e empate vai
para a revisão como «ambíguo». Não repara com mate em 1 (muitas trocas criam um mate em 1 --
evidência fraca demais, a regra «uma linha de um lance só confirma» do C11) nem com o motor
(cada verificação custa segundos; ali só a conferência). E uma exigência que não fecha
**nunca apaga a leitura**: vira frase e estado com ação -- a revisão olha.

**Os limites são medidos, não supostos.** ``LANCES_DA_BUSCA = 2``: mate em 2 exaustivo custa
até ~40 × 40 × 40 nós; mate em 3 custaria 40⁵ e não cabe em Python. ``LIMITE_NOS`` é o teto
depois do qual a busca desiste e diz «orçamento» em vez de fingir «não fecha».
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING, Any

import chess

from .config import PIECE_CLASSES
from .fen_utils import check_position, fen_from_class_indices

if TYPE_CHECKING:
    from .engine import EngineAnalyzer
    from .inference import BoardPrediction
    from .semantics import SideToMove

logger = logging.getLogger(__name__)

__all__ = [
    "LANCES_DA_BUSCA",
    "LIMITE_NOS",
    "MAX_LANCES",
    "Estipulacao",
    "ReparoPelaEstipulacao",
    "Verificacao",
    "apply_stipulation",
    "conferir",
    "esquecer_motor",
    "estipulacao_de_pagina",
    "motor_padrao",
    "parse_estipulacao",
    "registrar_fecho",
    "verificar",
]

MAX_LANCES = 6
"""Mate em mais de seis lances não é exigência de livro de problemas de tática -- e ``#7``
numa legenda é mais provavelmente um número que uma exigência."""

LANCES_DA_BUSCA = 2
"""Até aqui a busca exaustiva em Python responde; acima, só o motor UCI (ou «não verificado»)."""

LIMITE_NOS = 400_000
"""Nós (``push``) que a busca exaustiva pode gastar por verificação antes de desistir com
«orçamento». Um mate em 2 real fecha em milhares; uma posição lixo com muitas peças é onde
este teto fala. ~2 s nesta máquina."""

TEMPO_MOTOR_S = 3.0
"""Teto de tempo do ``go mate N`` no motor. Um mate em 3–4 de livro sai em milissegundos; o
teto só é gasto quando **não há** mate -- que é a resposta que interessa."""

MAX_TROCAS = 2
"""Como no C11: uma casa de cor trocada é o caso do campo; duas cobrem um rei recolorido."""

MAX_CASAS = 6
"""Casas hesitantes candidatas à segunda opção (as de menor margem), como no C11."""

MIN_LANCES_PARA_REPARO = 2
"""Mate em 1 só confirma, nunca troca: quase toda troca de peça cria ou destrói um mate em 1."""

_NUMEROS: dict[str, int] = {
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "uno": 1, "una": 1, "dos": 2, "cuatro": 4,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "een": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6,
    "einem": 1, "ein": 1, "zwei": 2, "drei": 3, "funf": 5, "sechs": 6,
}  # fmt: skip

_PALAVRAS = "|".join(sorted(_NUMEROS, key=len, reverse=True))

#: ``#2`` / ``# 2`` / ``‡2`` como token: precedido de espaço, início de linha ou parêntese, seguido de
#: fim, espaço ou pontuação -- mas não de outro dígito (``#2.5``, ``#2-3`` são números). O
#: lookbehind recusa ``h#2``/``s#2``/``r#2`` (ajudado, inverso, reflexo: ``h`` é caractere de
#: palavra) e ``_NUMERO_ANTES`` recusa ``No. #2`` / ``problem #2`` (número de problema, não exigência).
_TOKEN_MATE: re.Pattern[str] = re.compile(r"(?<![\w#])[#‡]\s?([1-6])(?!\d)(?![.,:/-]\d)")
_NUMERO_ANTES: re.Pattern[str] = re.compile(
    r"(?:\b(?:no|nr|num|numero|number|problem|problema|exercicio|exercise|ejercicio|aufgabe|diagram|diagrama)\.?\s*)$"
)
#: ``3#`` / ``3‡`` / ``3±`` / ``3+`` **como linha inteira** -- a forma holandesa/alemã dos livros de
#: problemas (Niemeijer imprime ``3‡``; a camada de texto do scan devolve ``3±`` ou ``3+``). Só a
#: linha inteira: ``3+`` no meio de uma frase é outra coisa.
_LINHA_MATE: re.Pattern[str] = re.compile(r"^\s*([1-6])\s?[#‡±+]\s*$")
#: «mate in two», «mate em 2 lances», «mate en 2», «mat en 2 coups», «mat in 2 zetten», «Matt in 3
#: Zügen», «mates in 2», «mate in 2 moves».
_FRASE_MATE: re.Pattern[str] = re.compile(
    r"\b(?:mates?|mat|matt|xeque-?mate)\s+(?:in|em|en)\s+(" + _PALAVRAS + r")\b"
)
#: A mesma frase em russo, sem dobra de acentos: «мат в 2 хода».
_FRASE_MATE_RU: re.Pattern[str] = re.compile(r"\bмат\s+в\s+([1-6])\b")
#: «and win» / «ganham» não é verificável por busca: fica fora, de propósito.


def _dobrar(text: str) -> str:
    """Minúsculas sem acentos, espaços colapsados -- a mesma dobra de ``pdf_text.fold``."""
    text = text.replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass(frozen=True)
class Estipulacao:
    """A exigência impressa: mate direto em ``lances``."""

    lances: int
    """N de «mate em N»; 1 ≤ N ≤ ``MAX_LANCES``."""

    texto: str = ""
    """O trecho que a declarou, como o livro o escreveu -- para a pessoa poder discordar."""

    origem: str = "legenda"
    """``legenda`` (a linha do diagrama) ou ``pagina`` (a faixa de margem valeu para a página)."""

    @property
    def rotulo(self) -> str:
        """A forma canônica, a do PGN: ``#2``."""
        return f"#{self.lances}"

    @property
    def descricao(self) -> str:
        """Em pt-BR, para o painel e para o ``Diagram.stipulation`` da suíte: «Mate em 2»."""
        return f"Mate em {self.lances}"


def parse_estipulacao(text: str) -> Estipulacao | None:
    """A exigência declarada numa linha, ou ``None``. Nunca inventa: sem padrão, sem resposta."""
    if not text or not text.strip():
        return None
    cru = text.strip()
    linha = _LINHA_MATE.match(cru)
    if linha is not None:
        return Estipulacao(int(linha.group(1)), texto=cru)
    for match in _TOKEN_MATE.finditer(cru):
        antes = _dobrar(cru[: match.start()])
        if _NUMERO_ANTES.search(antes):
            continue
        return Estipulacao(int(match.group(1)), texto=match.group(0).strip())
    dobrado = _dobrar(cru)
    frase = _FRASE_MATE.search(dobrado)
    if frase is not None:
        lances = _NUMEROS.get(frase.group(1).strip())
        if lances is not None and 1 <= lances <= MAX_LANCES:
            return Estipulacao(lances, texto=frase.group(0))
    russo = _FRASE_MATE_RU.search(cru.lower())
    if russo is not None:
        return Estipulacao(int(russo.group(1)), texto=russo.group(0))
    return None


def estipulacao_de_pagina(lines: list[str]) -> Estipulacao | None:
    """A exigência que vale para a página, lida da faixa de margem (o «Combinations #2» do Polgar).

    Duas exigências diferentes na faixa -- ``#2`` no topo e ``#3`` no rodapé -- devolvem
    ``None``: a página está dizendo as duas coisas, a regra dos tiers do lado a jogar.
    """
    achadas = [found for line in lines if (found := parse_estipulacao(line)) is not None]
    if not achadas:
        return None
    if len({found.lances for found in achadas}) > 1:
        logger.debug("faixa de margem declara duas exigências; sem escopo de página")
        return None
    primeira = achadas[0]
    return Estipulacao(primeira.lances, texto=primeira.texto, origem="pagina")


# ------------------------------------------------------------------------------ verificação


class _Orcamento(Exception):
    """A busca gastou ``LIMITE_NOS`` nós sem resposta."""


@dataclass(frozen=True)
class Verificacao:
    """O que a exigência disse sobre uma posição."""

    fecha: bool | None
    """``True``: há mate forçado em N. ``False``: não há (pela busca inteira, ou pelo motor no
    teto de tempo). ``None``: não verificado -- posição ilegal, sem motor para N > 2, ou
    orçamento esgotado."""

    chaves: tuple[str, ...] = ()
    """As chaves achadas, em SAN (até duas: uma é o problema; duas é «cozido»)."""

    metodo: str = ""
    """``busca`` (exaustiva), ``motor`` (UCI) ou vazio quando não verificou."""

    nos: int = 0
    motivo: str = ""
    """Em pt-BR, para o rodapé e para o PGN."""

    @property
    def cozido(self) -> bool:
        return len(self.chaves) > 1


def _tabuleiro(placement: str, turn: chess.Color) -> chess.Board | None:
    try:
        board = chess.Board(f"{placement} {'w' if turn == chess.WHITE else 'b'} - - 0 1")
    except ValueError:
        return None
    if check_position(board.fen()).is_fatal:
        return None
    return board


def _lances_ordenados(board: chess.Board, *, so_xeques: bool) -> list[chess.Move]:
    """Xeques primeiro, depois capturas: a chave de um problema raramente é o lance calmo,
    e para o último lance só um xeque pode dar mate."""
    xeques: list[chess.Move] = []
    capturas: list[chess.Move] = []
    outros: list[chess.Move] = []
    for move in board.legal_moves:
        if board.gives_check(move):
            xeques.append(move)
        elif so_xeques:
            continue
        elif board.is_capture(move):
            capturas.append(move)
        else:
            outros.append(move)
    return xeques + capturas + outros


def _temos_mate_em(board: chess.Board, k: int, contador: list[int], limite: int) -> bool:
    """Quem joga força mate em ``k`` lances."""
    for move in _lances_ordenados(board, so_xeques=(k == 1)):
        board.push(move)
        contador[0] += 1
        try:
            if contador[0] > limite:
                raise _Orcamento
            if _forca_mate_apos(board, k - 1, contador, limite):
                return True
        finally:
            board.pop()
    return False


def _forca_mate_apos(board: chess.Board, k: int, contador: list[int], limite: int) -> bool:
    """Depois do nosso lance: ou é mate agora, ou toda resposta deixa mate em ``k``."""
    if board.is_checkmate():
        return True
    if k <= 0:
        return False
    respostas = list(board.legal_moves)
    if not respostas:
        return False  # afogado: não é mate
    for reply in respostas:
        board.push(reply)
        contador[0] += 1
        try:
            if contador[0] > limite:
                raise _Orcamento
            if not _temos_mate_em(board, k, contador, limite):
                return False
        finally:
            board.pop()
    return True


def _chaves(board: chess.Board, lances: int, limite: int) -> tuple[list[chess.Move], int]:
    """As chaves que forçam mate em ``lances`` (para na segunda), e os nós gastos."""
    contador = [0]
    chaves: list[chess.Move] = []
    for move in _lances_ordenados(board, so_xeques=(lances == 1)):
        board.push(move)
        contador[0] += 1
        try:
            if _forca_mate_apos(board, lances - 1, contador, limite):
                chaves.append(move)
        finally:
            board.pop()
        if len(chaves) >= 2:
            break
    return chaves, contador[0]


def verificar(
    placement: str,
    turn: chess.Color,
    estipulacao: Estipulacao,
    *,
    motor: EngineAnalyzer | None = None,
    limite_nos: int = LIMITE_NOS,
    tempo_motor_s: float = TEMPO_MOTOR_S,
) -> Verificacao:
    """A exigência jogada sobre ``placement`` com ``turn`` a jogar."""
    board = _tabuleiro(placement, turn)
    if board is None:
        return Verificacao(None, motivo=f"{estipulacao.descricao}: posição ilegal, nada a verificar")
    lances = estipulacao.lances
    if lances <= LANCES_DA_BUSCA:
        try:
            # «Mate em N» é mate em **exatamente** N: um mate mais curto é cozido ou leitura
            # errada -- e, na busca de trocas, é o que impede uma peça a mais de «fechar» por
            # um mate em 1 que o problema nunca teve.
            nos = 0
            for curto in range(1, lances):
                chaves_curtas, gastos = _chaves(board, curto, limite_nos)
                nos += gastos
                if chaves_curtas:
                    sans = tuple(board.san(move) for move in chaves_curtas)
                    return Verificacao(False, chaves=sans, metodo="busca", nos=nos,
                                       motivo=f"{estipulacao.descricao}: a leitura tem mate em {curto} "
                                              f"({', '.join(sans)}), mais curto que a exigência")
            chaves, gastos = _chaves(board, lances, limite_nos)
            nos += gastos
        except _Orcamento:
            return Verificacao(None, metodo="busca", nos=limite_nos,
                               motivo=f"{estipulacao.descricao}: busca interrompida no orçamento de {limite_nos} nós")
        sans = tuple(board.san(move) for move in chaves)
        if not chaves:
            return Verificacao(False, metodo="busca", nos=nos,
                               motivo=f"{estipulacao.descricao} não fecha nesta leitura")
        if len(chaves) > 1:
            return Verificacao(True, chaves=sans, metodo="busca", nos=nos,
                               motivo=f"{estipulacao.descricao} fecha por mais de uma chave ({', '.join(sans)}): cozido")
        return Verificacao(True, chaves=sans, metodo="busca", nos=nos,
                           motivo=f"{estipulacao.descricao} fecha: 1.{sans[0]}")
    if motor is None:
        return Verificacao(None, motivo=f"{estipulacao.descricao}: sem motor para mate em {lances}")
    try:
        avaliacao = motor.mate_in(board, lances, time_s=tempo_motor_s)
    except Exception as exc:  # noqa: BLE001 - o motor é opcional; a falha dele é nota, não erro
        logger.warning("Motor falhou ao verificar %s: %s", estipulacao.rotulo, exc)
        return Verificacao(None, motivo=f"{estipulacao.descricao}: o motor falhou ({exc})")
    mate = avaliacao.mate_in
    proprio = mate if turn == chess.WHITE else (-mate if mate is not None else None)
    if proprio is not None and 0 < proprio < lances:
        chave = avaliacao.best_move_san
        return Verificacao(False, chaves=(chave,) if chave else (), metodo="motor",
                           motivo=f"{estipulacao.descricao}: a leitura tem mate em {proprio} (motor), "
                                  "mais curto que a exigência")
    if proprio is not None and proprio == lances:
        chave = avaliacao.best_move_san
        return Verificacao(True, chaves=(chave,) if chave else (), metodo="motor",
                           motivo=f"{estipulacao.descricao} fecha (motor): 1.{chave}")
    return Verificacao(False, metodo="motor",
                       motivo=f"{estipulacao.descricao} não fecha nesta leitura "
                              f"(motor, {tempo_motor_s:g} s, profundidade {avaliacao.depth})")


# --------------------------------------------------------------------------------- reparo


@dataclass(frozen=True)
class ReparoPelaEstipulacao:
    """O que a exigência impressa disse sobre a posição lida."""

    fecha: bool | None
    """``True``: a leitura cumpre a exigência. ``False``: não cumpre, nem com trocas. ``None``:
    não verificável (sem motor, posição ilegal, orçamento)."""

    estipulacao: Estipulacao | None = None
    verificacao: Verificacao | None = None
    """A verificação final (da leitura trocada, quando houve troca)."""

    trocas: tuple[tuple[int, int, int], ...] = ()
    """``(casa em ordem de leitura, classe lida, classe adotada)`` da troca que fez fechar."""

    placement: str = ""
    motivo: str = ""
    ambiguo: bool = False

    @property
    def casas(self) -> list[int]:
        return [casa for casa, _, _ in self.trocas]

    @property
    def chaves(self) -> tuple[str, ...]:
        return self.verificacao.chaves if self.verificacao is not None else ()


def _nome(casa: int) -> str:
    return f"{'abcdefgh'[casa % 8]}{8 - casa // 8}"


def _letra(classe: int) -> str:
    nome = PIECE_CLASSES[int(classe)]
    return "·" if nome == "empty" else nome


def conferir(
    probs: Any,
    class_indices: list[int],
    estipulacao: Estipulacao,
    turn: chess.Color,
    *,
    motor: EngineAnalyzer | None = None,
    max_trocas: int = MAX_TROCAS,
    max_casas: int = MAX_CASAS,
    limite_nos: int = LIMITE_NOS,
) -> ReparoPelaEstipulacao:
    """Joga a exigência sobre a leitura e, se não fecha, procura a troca única que a faz fechar.

    A busca de trocas só corre com a busca exaustiva (``lances <= LANCES_DA_BUSCA``) e só com
    ``lances >= MIN_LANCES_PARA_REPARO``; nos outros casos a resposta é a conferência e pronto.
    """
    import numpy as np

    from .lance_seguinte import _candidatas

    placement = fen_from_class_indices(class_indices)
    primeira = verificar(placement, turn, estipulacao, motor=motor, limite_nos=limite_nos)
    if primeira.fecha is not False:
        return ReparoPelaEstipulacao(primeira.fecha, estipulacao, primeira, placement=placement,
                                     motivo=primeira.motivo)

    probs = np.asarray(probs, dtype=np.float64)
    if probs.shape != (64, len(PIECE_CLASSES)):
        return ReparoPelaEstipulacao(False, estipulacao, primeira, placement=placement,
                                     motivo=primeira.motivo + " (sem matriz para tentar trocas)")
    if estipulacao.lances < MIN_LANCES_PARA_REPARO or estipulacao.lances > LANCES_DA_BUSCA:
        return ReparoPelaEstipulacao(False, estipulacao, primeira, placement=placement,
                                     motivo=primeira.motivo)

    candidatas = _candidatas(probs, list(class_indices), max_casas)
    base = list(class_indices)
    for tamanho in range(1, max(0, max_trocas) + 1):
        fecham: list[tuple[tuple[tuple[int, int, int], ...], Verificacao]] = []
        for escolha in combinations(candidatas, tamanho):
            if len({casa for casa, _ in escolha}) != tamanho:
                continue
            estado = list(base)
            trocas: list[tuple[int, int, int]] = []
            for casa, nova in escolha:
                trocas.append((casa, estado[casa], nova))
                estado[casa] = nova
            tentativa = verificar(fen_from_class_indices(estado), turn, estipulacao,
                                  motor=None, limite_nos=limite_nos)
            if tentativa.fecha:
                fecham.append((tuple(trocas), tentativa))
                if len(fecham) > 1:
                    break
        if len(fecham) == 1:
            trocas, tentativa = fecham[0]
            estado = list(base)
            for casa, _de, para in trocas:
                estado[casa] = para
            descricao = ", ".join(f"{_nome(casa)} {_letra(de)}→{_letra(para)}" for casa, de, para in trocas)
            return ReparoPelaEstipulacao(
                False, estipulacao, tentativa, trocas=trocas, placement=fen_from_class_indices(estado),
                motivo=f"{estipulacao.descricao} só fecha com {descricao} (1.{tentativa.chaves[0]})")
        if len(fecham) > 1:
            return ReparoPelaEstipulacao(
                False, estipulacao, primeira, placement=placement, ambiguo=True,
                motivo=f"{estipulacao.descricao} fecha com trocas diferentes: nenhuma foi adotada")
    return ReparoPelaEstipulacao(
        False, estipulacao, primeira, placement=placement,
        motivo=f"{primeira.motivo}, nem com até {max_trocas} troca(s) nas casas hesitantes")


def apply_stipulation(
    prediction: BoardPrediction,
    context: Any,
    side: SideToMove,
    *,
    motor: EngineAnalyzer | None = None,
) -> tuple[BoardPrediction, ReparoPelaEstipulacao | None]:
    """A exigência devolvida à posição (C12): a leitura, trocada quando ela a prova.

    ``None`` quando a página não imprime exigência para o diagrama. Partilhado pela leitura da
    janela (``service``) e pela exportação (``pdf_to_pgn``), como ``apply_next_move``.
    """
    from .inference import prediction_with_squares

    estipulacao = getattr(context, "stipulation", None) if context is not None else None
    if estipulacao is None:
        return prediction, None
    reparo = conferir(prediction.probs, list(prediction.class_indices), estipulacao, side.color, motor=motor)
    if reparo.trocas:
        prediction = prediction_with_squares(prediction, reparo.trocas)
    return prediction, reparo


# ----------------------------------------------------------------------------------- motor

_MOTOR: dict[str, Any] = {}
"""O motor partilhado do processo (`motor_padrao`): abrir o Stockfish custa 100–300 ms e uma
página de problemas tem seis diagramas. Fechado no `atexit`."""


def motor_padrao() -> EngineAnalyzer | None:
    """O motor UCI das configurações (`settings.engine.path`) ou de `engine.find_engine`, ou
    `None` quando a máquina não tem um. Um processo por sessão; nunca levanta."""
    if "motor" in _MOTOR:
        return _MOTOR["motor"]
    motor: EngineAnalyzer | None = None
    try:
        from . import engine
        from . import settings as preferencias

        configurado = preferencias.load_settings().engine
        caminho = engine.find_engine(configurado.path or None)
        if caminho is not None:
            motor = engine.EngineAnalyzer(caminho, movetime_ms=configurado.movetime_ms, threads=configurado.threads)
            registrar_fecho(motor)
            logger.info("Motor UCI para a estipulação: %s", caminho)
        else:
            logger.info("Sem motor UCI: mate em 3+ fica «não verificado».")
    except Exception:  # noqa: BLE001 - o motor é opcional; a falha dele é nota, não erro
        logger.warning("Não foi possível preparar o motor UCI para a estipulação.", exc_info=True)
        motor = None
    _MOTOR["motor"] = motor
    return motor


def registrar_fecho(motor: Any) -> None:
    """Fecha o motor quando o processo termina -- **antes** do `join` das threads (C12).

    O `SimpleEngine` do python-chess corre o seu laço numa thread que não é *daemon*; o
    desligamento do interpretador junta essas threads **antes** de correr os `atexit`, então um
    `atexit.register(motor.close)` chegaria tarde e o processo ficaria pendurado depois de
    imprimir o relatório (medido no `field_exact` da fase 4). `threading._register_atexit` é o
    gancho que `concurrent.futures` usa para o mesmo problema: corre antes do `join`.
    """
    import atexit
    import threading

    registrar = getattr(threading, "_register_atexit", None)
    if callable(registrar):
        try:
            registrar(motor.close)
            return
        except Exception:  # noqa: BLE001 - ao desligar já, cai no atexit comum
            pass
    atexit.register(motor.close)


def esquecer_motor() -> None:
    """Fecha e esquece o motor partilhado (testes; troca de configuração)."""
    motor = _MOTOR.pop("motor", None)
    if motor is not None:
        try:
            motor.close()
        except Exception:  # noqa: BLE001
            logger.debug("Falha ao fechar o motor da estipulação.", exc_info=True)
