"""A base de partidas como terceira fonte de verdade sobre um diagrama (S-72).

**O que ela responde.** A legenda do livro diz "Coull - Stanciu" e mais nada. A base diz em
que torneio, em que ano, com que resultado -- e, o que nenhuma outra fonte do projeto sabe
dizer, **em que lance** aquela posição acontece e **de quem é a vez** ali. Os dois últimos são
justamente os campos que a pessoa preenche contando à mão no livro.

**Por que isso é diferente de tudo que já existe aqui.** Toda verdade do projeto vem de
humano: o `labels.csv` é trabalho humano, o lado a jogar da S-16 é texto que um humano
escreveu no livro, a fila da S-22 ordena para um humano olhar. Um casamento contra a base é o
primeiro **oráculo externo**: as 64 casas da posição lida têm de bater com as 64 casas de um
lance de uma partida registrada. Não é opinião, e não é confiança do modelo -- é coincidência
de 64 símbolos, que não acontece por acaso.

**Duas regras que a arquitetura de hoje impõe, e que não são detalhe.**

1. **Casar pela colocação de peças, nunca pela FEN inteira.** Roque e *en passant* são
   inferidos (S-17), o contador de lances é o que estamos tentando descobrir, e a vez a jogar
   costuma ser palpite. Comparar a FEN completa faria todo casamento falhar por campos que o
   projeto sabe que não conhece.
2. **A busca é por livro, não por diagrama.** Uma passada pela base custa ~150 s e responde
   por todos os diagramas de uma vez; uma passada por diagrama custaria os mesmos 150 s cada.
   É a mesma economia da S-61 -- uma abertura por varredura, não uma por página.

**O que este módulo não faz.** Busca por posição, para os diagramas cuja legenda não traz
nome. Ela exige reproduzir os lances das 10,5 M partidas (~7,5 h num processo), e a decisão
de pagá-la espera o número que a medição está levantando. Ver `docs/ROADMAP_FASE7.md`.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chess

from .config import PROJECT_ROOT
from .pdf_text import fold, parse_context

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_DATABASE_DIR",
    "DiagramMatch",
    "GameRecord",
    "PlayerPair",
    "default_database_path",
    "match_entries",
    "pair_from_caption",
    "scan_by_players",
    "surname",
]

DEFAULT_DATABASE_DIR = PROJECT_ROOT / "pgn_database"
"""Onde procurar a base quando ninguém disser. Fora do git, como todo material de terceiro."""

MAX_GAMES_PER_PAIR = 40
"""Teto de partidas guardadas por par de nomes.

Kasparov x Karpov são 170 partidas na base, e reproduzir todas para achar uma posição custaria
memória e tempo sem melhorar a resposta: o que decide o casamento são as 64 casas, e se a
posição não apareceu nas 40 primeiras partidas do par, o problema não é falta de amostra."""

_RE_HEADER = re.compile(r'^\[(\w+)\s+"(.*)"\s*\]\s*$')
_RE_BRACES = re.compile(r"\{[^}]*\}")
_RE_SAN = re.compile(r"[a-hKQRBNOx1-8=+#\-]{2,7}")
_KEPT_HEADERS = ("White", "Black", "Event", "Site", "Date", "Round", "Result", "ECO")
"""Os que viram header de PGN nosso. O resto da base (`SourceQuality`, `EventCountry`...)
descreve a base, não a partida."""

PlayerPair = tuple[str, str]


def surname(name: str) -> str:
    """`De Castellvi, Francisco` -> `de castellvi`; `Coull` -> `coull`.

    O sobrenome é o que as duas pontas têm em comum: a base escreve `Sobrenome, Nome` e o
    livro escreve `Sobrenome - Sobrenome`. Comparar nome completo não casaria nunca.
    """
    return fold(str(name).split(",")[0]).strip()


def pair_from_caption(caption: str) -> PlayerPair | None:
    """Os dois sobrenomes que a legenda declara, ou `None`.

    Reusa o interpretador da S-16 em vez de ter um seu: quem já sabe separar "Coull - Stanciu"
    de "2 @b4 @d4!" é o `parse_context`, e uma segunda regra de leitura de legenda divergiria
    da primeira -- foi exatamente isso que a 6.4 encontrou nos rótulos de procedência.
    """
    jogadores = parse_context(caption).players
    if not jogadores:
        return None
    par = (surname(jogadores[0]), surname(jogadores[1]))
    return par if par[0] and par[1] else None


def default_database_path(directory: Path | None = None) -> Path | None:
    """O maior `.pgn` da pasta da base, ou `None` se não houver.

    "O maior" e não "o primeiro": quem baixa uma gigabase costuma deixar ao lado dela o PGN de
    um torneio, e escolher por ordem de diretório pegaria o torneio.
    """
    pasta = directory or DEFAULT_DATABASE_DIR
    if not pasta.is_dir():
        return None
    candidatos = sorted(pasta.glob("*.pgn"), key=lambda p: p.stat().st_size, reverse=True)
    return candidatos[0] if candidatos else None


@dataclass(frozen=True)
class GameRecord:
    """Uma partida da base: os headers que interessam e o movetext cru."""

    headers: dict[str, str] = field(default_factory=dict)
    movetext: str = ""

    def positions(self) -> Iterator[tuple[str, int, bool]]:
        """Cada lance da partida como `(colocação, número do lance, vez das brancas)`.

        A colocação é `Board.board_fen()` -- campo de peças e nada mais, pela regra 1 do
        módulo. Um lance ilegal interrompe a partida em vez de derrubá-la: a base tem 10,5
        milhões de partidas e algumas trazem notação que o `python-chess` recusa, e perder o
        resto de uma partida é melhor que perder a varredura.
        """
        tabuleiro = chess.Board()
        for token in _RE_BRACES.sub(" ", self.movetext).replace(".", ". ").split():
            limpo = token.replace("!", "").replace("?", "")
            if not limpo or limpo[0].isdigit() or not _RE_SAN.fullmatch(limpo):
                continue
            try:
                tabuleiro.push_san(limpo)
            except (ValueError, AssertionError):
                logger.debug("Lance recusado em %s: %r", self.headers.get("White", "?"), limpo)
                return
            yield tabuleiro.board_fen(), tabuleiro.fullmove_number, tabuleiro.turn == chess.WHITE

    @property
    def label(self) -> str:
        """Como a partida aparece na barra de status: quem, contra quem, onde e quando."""
        evento = " ".join(x for x in (self.headers.get("Event", ""), self.headers.get("Date", "")[:4]) if x)
        return f"{self.headers.get('White', '?')} x {self.headers.get('Black', '?')}" + (f", {evento}" if evento else "")


@dataclass(frozen=True)
class DiagramMatch:
    """O que a base sabe sobre um diagrama, quando ela o reconhece."""

    page_index: int
    diagram_index: int
    move_number: int
    side_to_move: str
    headers: dict[str, str]
    games_matched: int = 1
    """Quantas partidas contêm a posição.

    Acima de um punhado ela deixa de identificar a partida -- um final de rei e peão aparece em
    centenas --, e é por isso que quem consome isto olha o número antes de preencher header.
    """

    game_label: str = ""

    @property
    def key(self) -> tuple[int, int]:
        return (self.page_index, self.diagram_index)


def scan_by_players(
    database: Path,
    wanted: Iterable[PlayerPair],
    *,
    max_games_per_pair: int = MAX_GAMES_PER_PAIR,
    progress: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
) -> dict[PlayerPair, list[GameRecord]]:
    """Uma passada pela base, colhendo só as partidas dos pares pedidos.

    **Sem índice, e é uma decisão medida.** Um índice por nome custaria ~1 GB no disco e uma
    construção de vários minutos para poupar 150 s por livro -- e livro se varre uma vez. O
    dia em que a busca virar por diagrama e não por livro, o índice passa a valer.

    `progress` recebe o número de partidas lidas, a cada 200 mil. `cancel` é conferido no mesmo
    ponto: entre partidas, nunca no meio de uma, pela razão da S-24.
    """
    alvos = {tuple(par) for par in wanted}
    colhidas: dict[PlayerPair, list[GameRecord]] = {}
    if not alvos:
        return colhidas

    partidas = 0
    cabecalho: dict[str, str] = {}
    branco = ""
    coletando: PlayerPair | None = None
    movetext: list[str] = []

    def fechar() -> None:
        nonlocal coletando, movetext
        if coletando is not None and movetext:
            colhidas.setdefault(coletando, []).append(
                GameRecord(headers=dict(cabecalho), movetext=" ".join(movetext))
            )
        coletando, movetext = None, []

    with database.open("r", encoding="utf-8-sig", errors="replace") as fh:
        for linha in fh:
            if linha.startswith("["):
                if linha.startswith("[Event "):
                    # Fechar **só** na fronteira de partida. Fechar a cada cabeçalho desligaria
                    # a coleta na linha seguinte ao `[Black]`, antes de o movetext chegar --
                    # defeito que custou uma varredura inteira medindo zero casamentos.
                    fechar()
                    partidas += 1
                    if partidas % 200_000 == 0:
                        if cancel is not None and cancel.is_set():
                            logger.info("Busca na base cancelada em %d partidas.", partidas)
                            break
                        if progress is not None:
                            progress(partidas)
                    cabecalho = {}
                    branco = ""
                casado = _RE_HEADER.match(linha.rstrip())
                if casado is None:
                    continue
                campo, valor = casado.group(1), casado.group(2)
                if campo in _KEPT_HEADERS:
                    cabecalho[campo] = valor
                if campo == "White":
                    branco = surname(valor)
                elif campo == "Black":
                    par = (branco, surname(valor))
                    if par in alvos and len(colhidas.get(par, ())) < max_games_per_pair:
                        coletando, movetext = par, []
                continue
            texto = linha.strip()
            if texto:
                movetext.append(texto)
            elif movetext:
                fechar()
    fechar()

    logger.info("Base varrida: %d partidas, %d pares com partida.", partidas, len(colhidas))
    return colhidas


def match_entries(
    entries: Sequence[Any],
    games: Mapping[PlayerPair, Sequence[GameRecord]],
) -> list[DiagramMatch]:
    """Cruza os diagramas do livro com as partidas colhidas.

    Um diagrama casa quando a **colocação lida** aparece em algum lance de alguma partida do
    par que a legenda dele nomeia. Casamento é exato: 63 casas certas e uma errada não é
    casamento parcial, é outra posição. Medido em 91 diagramas, não existe meio-termo -- ou
    bate nas 64, ou a distância é grande.
    """
    por_par: dict[PlayerPair, list[tuple[str, int, bool, GameRecord]]] = {}
    achados: list[DiagramMatch] = []

    for entrada in entries:
        caption = getattr(entrada, "caption", "") or ""
        par = pair_from_caption(caption)
        if par is None or not games.get(par):
            continue
        if par not in por_par:
            por_par[par] = [
                (colocacao, lance, vez, partida)
                for partida in games[par]
                for colocacao, lance, vez in partida.positions()
            ]
        alvo = getattr(entrada, "placement", "")
        casamentos = [item for item in por_par[par] if item[0] == alvo]
        if not casamentos:
            continue
        _, lance, vez, partida = casamentos[0]
        achados.append(
            DiagramMatch(
                page_index=int(entrada.page_index),
                diagram_index=int(entrada.diagram_index),
                move_number=int(lance),
                side_to_move="w" if vez else "b",
                headers={campo: partida.headers[campo] for campo in _KEPT_HEADERS if partida.headers.get(campo)},
                games_matched=len({id(item[3]) for item in casamentos}),
                game_label=partida.label,
            )
        )
    return achados
