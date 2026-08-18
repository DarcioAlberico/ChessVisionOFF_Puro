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

**A base é a pasta inteira, e não um arquivo (S-93).** Todos os `.pgn` de `pgn_database/`
entram em toda busca. Era um só -- o maior --, e o preço disso apareceu medido: a segunda
gigabase desta máquina tem 10.355.488 partidas que nunca foram consultadas, e a partida
`Hutchings x Keene, Hexagon North Devon 1973` -- procurada por nome, por data e pelas 64 casas
na base "oficial", e ausente das três -- está nela.

Medido nos mesmos 4 livros, em 2026-08-16: os casamentos por posição vão de **1.641 para
2.104** em 3.563 diagramas. O custo também está medido, e é real: **981 diagramas deixaram de
ser "partida única"**, e 63,5% disso é a mesma partida repetida nas duas bases, com o evento
escrito de outro jeito em cada uma. Ver `docs/PLANO_BASE_PARTIDAS.md`.

**Duas regras que a arquitetura de hoje impõe, e que não são detalhe.**

1. **Casar pela colocação de peças, nunca pela FEN inteira.** Roque e *en passant* são
   inferidos (S-17), o contador de lances é o que estamos tentando descobrir, e a vez a jogar
   costuma ser palpite. Comparar a FEN completa faria todo casamento falhar por campos que o
   projeto sabe que não conhece.
2. **A busca é por livro, não por diagrama.** Uma passada pela base custa ~150 s e responde
   por todos os diagramas de uma vez; uma passada por diagrama custaria os mesmos 150 s cada.
   É a mesma economia da S-61 -- uma abertura por varredura, não uma por página.

**Os dois caminhos, e o que cada um custa.**

| | por nome (S-72) | por posição (S-73) |
|---|---|---|
| alcança | os diagramas cuja legenda traz os dois jogadores | **todos** |
| mediu, no `Secrets of Chess Training` | 61 de 1.408 | **581** preenchíveis de 1.408 |
| custo | ~150 s, um processo | **28,7 min** em dez (eram 104, antes da S-85) |
| onde mora | botão da Galeria | `cvoff-games --positions` **e** botão da Galeria (S-92) |

O caminho por posição é ~10× mais abrangente e ~12× mais caro, e o custo dele é **por
varredura, não por livro**: o conjunto-alvo cabe na memória sejam 1.400 posições ou 40 mil,
então o acervo inteiro cabe na mesma passada.

**Ele foi comando de linha e não botão até a S-92**, e a razão continua verdadeira: meia hora
atrás de um botão é uma janela travada que ninguém entende. O que mudou foi o que cerca o
botão -- ele diz o preço antes, mostra em que pedaço está, dá para cancelar, e o cache da S-84
faz a segunda vez custar segundos. Sem essas quatro coisas ele continuaria não devendo existir.

**Nenhum dos dois é mais o caminho de quem está parado num diagrama.** Desde a S-84 a resposta
da varredura fica em `games_cache.py`, e a tela a lê do disco; desde a S-87, quem quiser
perguntar à base pelos nomes *agora* usa o índice do `games_index.py`, que responde em
milissegundos. Estes dois caminhos aqui são os que **produzem** aquelas respostas, em lote.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import re
import sys
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
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
    "PositionHit",
    "PositionIndex",
    "as_databases",
    "database_paths",
    "match_entries",
    "match_positions",
    "occupancy",
    "agrees_with_caption",
    "kept_headers",
    "pair_from_caption",
    "rank_candidates",
    "scan_by_players",
    "scan_by_positions",
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
    """`De Castellvi, Francisco` -> `de castellvi`; `K. Spicak` -> `spicak`.

    O sobrenome é o que as duas pontas têm em comum: a base escreve `Sobrenome, Nome` e o
    livro escreve `Sobrenome - Sobrenome`. Comparar nome completo não casaria nunca.

    **A inicial colada do livro é a segunda forma, e ela custava um quinto da busca (S-90).**
    A vírgula da base sempre foi tratada; `K. Spicak`, `De. Wagner`, `E. Mence` -- como o
    `400 Quebra-cabeças` escreve **um terço** das suas legendas -- não eram, e não casavam com
    `Spicak, Krzysztof` na base. Medido no acervo: **109 de 494 pares (22,1%)** nunca chegavam
    a ser procurados, e em silêncio, porque `scan_by_players` só não os encontrava.

    **A partícula sobrevive e a inicial não**, e a diferença é o critério: `De Castellvi`
    continua inteiro porque `De` não tem ponto nem é letra solta; `De. Wagner` vira `wagner`
    porque tem. A guarda do `len` é o que impede um nome que é *só* uma inicial de virar vazio
    -- e vazio casaria com qualquer coisa, que é o oposto do que isto existe para fazer.
    """
    tokens = fold(str(name).split(",")[0]).split()
    while len(tokens) > 1 and (tokens[0].endswith(".") or len(tokens[0]) == 1):
        tokens = tokens[1:]
    return " ".join(tokens)


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


def database_paths(directory: Path | None = None) -> list[Path]:
    """**Todos** os `.pgn` da pasta, em ordem estável. A base é o conjunto deles (S-93).

    Até aqui a base era *um* arquivo -- o maior --, e a razão escrita era que "quem baixa uma
    gigabase costuma deixar ao lado dela o PGN de um torneio". Ela estava certa sobre o risco e
    errada sobre a saída: o torneio ao lado **também** tem partidas, e escolher um arquivo é
    jogar fora tudo que os outros sabem.

    **Medido nesta máquina, e é o que motivou a mudança.** A pasta tinha duas gigabases; a
    menor (8,6 GB, 10.355.488 partidas) era invisível por ser a menor. A partida
    `Hutchings x Keene, Hexagon North Devon 1973` -- procurada por nome, por data e pelas 64
    casas na base "oficial", e ausente das três -- está nela, com as 44 posições batendo.

    **A ordem é por nome, e não por tamanho, porque ela virou identidade.** O índice por nome
    grava *em que arquivo* cada partida mora, e esse número é a posição nesta lista; uma ordem
    que mudasse quando um arquivo crescesse faria cada offset apontar para o arquivo errado --
    o defeito que o fingerprint existe para impedir.
    """
    pasta = directory or DEFAULT_DATABASE_DIR
    if not pasta.is_dir():
        return []
    return sorted(pasta.glob("*.pgn"), key=lambda caminho: caminho.name.lower())


def as_databases(databases: Path | Sequence[Path] | None) -> list[Path]:
    """Um caminho, vários ou nenhum -- sempre uma lista. Existe para as assinaturas aceitarem os três.

    Quem já tinha um `.pgn` na mão -- um teste, um `--database`, uma chamada anterior à S-93 --
    continua passando um `Path`; quem tem a pasta passa a lista. Sem isto cada função de
    varredura ganharia um segundo nome, e duas implementações da mesma coisa divergem.
    """
    if databases is None:
        return []
    return [databases] if isinstance(databases, Path) else list(databases)


def occupancy(placement: str) -> int:
    """As casas ocupadas de uma colocação, como o inteiro de 64 bits do `python-chess` (S-85).

    Lida direto da string em vez de montar um `Board` e ler `.occupied`: os dois dão o mesmo
    número (há teste), e a varredura chama isto uma vez por alvo -- 40 mil vezes no acervo
    inteiro -- antes de abrir a base.

    A numeração é a do `python-chess`: `a1` é o bit 0 e `a8` é o 56, enquanto a colocação
    escreve a **oitava** fila primeiro. É de onde vem o `(7 - fila) * 8`.
    """
    bits = 0
    for fila, linha in enumerate(placement.split("/")):
        casa = (7 - fila) * 8
        for simbolo in linha:
            if simbolo.isdigit():
                casa += int(simbolo)
            else:
                bits |= 1 << casa
                casa += 1
    return bits


@dataclass(frozen=True)
class GameRecord:
    """Uma partida da base: os headers que interessam e o movetext cru."""

    headers: dict[str, str] = field(default_factory=dict)
    movetext: str = ""

    def positions(self, occupancies: frozenset[int] | None = None) -> Iterator[tuple[str, int, bool]]:
        """Cada lance da partida como `(colocação, número do lance, vez das brancas)`.

        A colocação é `Board.board_fen()` -- campo de peças e nada mais, pela regra 1 do
        módulo. Um lance ilegal interrompe a partida em vez de derrubá-la: a base tem 10,5
        milhões de partidas e algumas trazem notação que o `python-chess` recusa, e perder o
        resto de uma partida é melhor que perder a varredura.

        **`occupancies` é o porteiro que barateou a varredura em 3,5× (S-85).** `board_fen()` a
        cada lance é **75% do custo** da busca por posição: o replay custa 2 s e as 213.830
        strings de 64 casas custam mais 6 -- para 152 comparações que interessam.
        `Board.occupied` é um inteiro que o `python-chess` já atualiza a cada lance, e ocupação
        igual é *condição necessária* para colocação igual. Quem passa o conjunto das ocupações
        dos seus alvos só paga a string no punhado que passa pelo porteiro.

        Medido num pedaço de 304 MB da base, 332.823 partidas, com os 3.143 alvos reais do
        acervo: **928,2 s -> 262,3 s**, e as **mesmas 516 posições casadas**, as mesmas 20.758
        ocorrências, os mesmos lances e a mesma vez.

        Não é aproximação: o que o porteiro deixar passar por engano -- mesmas casas ocupadas,
        peças diferentes -- o `board_fen()` seguinte recusa, como sempre recusou. `None` desliga
        o porteiro, que é o caminho de quem já tem poucas partidas em mão (`match_entries`).
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
            if occupancies is not None and tabuleiro.occupied not in occupancies:
                continue
            yield tabuleiro.board_fen(), tabuleiro.fullmove_number, tabuleiro.turn == chess.WHITE

    @property
    def label(self) -> str:
        """Como a partida aparece na barra de status: quem, contra quem, onde e quando."""
        evento = " ".join(x for x in (self.headers.get("Event", ""), self.headers.get("Date", "")[:4]) if x)
        return f"{self.headers.get('White', '?')} x {self.headers.get('Black', '?')}" + (f", {evento}" if evento else "")


@dataclass(frozen=True)
class PositionHit:
    """Uma partida da base que passa pela posição procurada -- uma **candidata** (S-73/S-83).

    Nasceu como resultado interno da varredura por posição e virou o tipo que atravessa o
    projeto inteiro: é o que a lista da tela mostra e o que a pessoa escolhe. Os dois caminhos
    -- por nome e por posição -- produzem isto, e por isso não existem dois tipos de candidata.
    """

    move_number: int
    side_to_move: str
    headers: dict[str, str] = field(default_factory=dict)

    verified: bool = True
    """As 64 casas do diagrama aparecem nesta partida, no lance declarado.

    **Falso significa que a partida é do par certo e a posição não bate** -- é o que a busca por
    nome (S-87) encontra em 68 dos 140 diagramas do acervo cuja legenda nomeia os jogadores e
    cuja posição não casou com partida nenhuma. A base tem a partida; ela só não tem aquela
    posição, seja porque a leitura saiu com uma casa errada, seja porque o livro mostra um
    momento que o registro não guardou.

    A distinção não é acadêmica: ela decide **o que pode ser preenchido**. Evento, data e
    resultado vêm da partida e são verdade sobre ela; o número do lance e a vez vêm da posição,
    e sem posição eles seriam invenção. `GalleryModel.choose_game` respeita isso."""

    @property
    def label(self) -> str:
        evento = " ".join(x for x in (self.headers.get("Event", ""), self.headers.get("Date", "")[:4]) if x)
        nome = f"{self.headers.get('White', '?')} x {self.headers.get('Black', '?')}" + (f", {evento}" if evento else "")
        return nome if self.verified else f"{nome} (posição não confere)"

    @property
    def key(self) -> str:
        """A identidade da **partida**, para uma escolha humana sobreviver a uma revarredura.

        Não é o índice na lista: a ordem muda quando a base muda, e guardar "a terceira" faria
        a escolha de ontem apontar para outra partida hoje. Não é o `label` tampouco -- ele é
        texto para gente ler, e junta evento e ano no mesmo campo.

        O lance fica **de fora** de propósito: a mesma partida pode passar duas vezes pela
        mesma posição (repetição), e as duas continuam sendo a mesma escolha.
        """
        return "|".join(self.headers.get(campo, "") for campo in ("White", "Black", "Date", "Round", "Event"))

    def to_dict(self) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "move_number": self.move_number,
            "side_to_move": self.side_to_move,
            "headers": dict(self.headers),
        }
        # Só quando falso: o cache guarda casamentos de posição, que são verificados por
        # definição, e uma chave repetida 40 mil vezes para dizer "sim" é peso morto no arquivo.
        if not self.verified:
            dados["verified"] = False
        return dados

    @classmethod
    def from_dict(cls, dados: Any) -> PositionHit:
        if not isinstance(dados, dict):
            return cls(move_number=1, side_to_move="w")
        return cls(
            move_number=int(dados.get("move_number", 1)),
            side_to_move=str(dados.get("side_to_move", "w")),
            headers={str(k): str(v) for k, v in (dados.get("headers") or {}).items()},
            verified=bool(dados.get("verified", True)),
        )


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

    caption_confirmed: bool = False
    """A legenda do diagrama nomeia os jogadores desta partida, e **só dela** (S-91).

    É a diferença entre uma escolha e um desempate. Medido nos 47 diagramas ambíguos cujas
    legendas trazem os dois jogadores: o desempate por data discorda da legenda **72,3%** das
    vezes, contra um piso de ruído de 26,5% medido nos casamentos de partida única. Onde a
    legenda aponta uma candidata só, ela responde -- e a data deixa de decidir.

    Vale também **acima** do teto de `max_games`: uma posição em 47 partidas não identifica
    partida nenhuma pela contagem, mas identifica se a legenda nomeia exatamente uma delas.
    São os 232 diagramas do acervo que hoje ficam confirmados e vazios.
    """

    candidates: tuple[PositionHit, ...] = ()
    """As partidas que contêm a posição, até o teto de `MAX_HITS_PER_POSITION` (S-83).

    **Antes disto, a lista era calculada e jogada fora três vezes**: a varredura guardava até
    oito partidas, `match_positions` usava a primeira e descartava as outras sete, e
    `--save-matches` gravava só a vencedora. Refazer a escolha custava 104 minutos de varredura,
    porque o artefato que sobrevivia já vinha decidido.

    `move_number`, `side_to_move` e `headers` continuam sendo **a primeira candidata**, e é o
    que mantém tudo que consome isto funcionando como antes. A diferença é que agora dá para
    discordar dela: 373 dos 1.641 casamentos do acervo têm mais de uma partida, e em 141 deles
    o desempate por data escolheu sozinho -- discordando da legenda do livro 72,3% das vezes.

    Vazio quando o casamento veio de um artefato v1, anterior à S-83.
    """

    @property
    def key(self) -> tuple[int, int]:
        return (self.page_index, self.diagram_index)

    @property
    def ambiguous(self) -> bool:
        """Mais de uma partida contém a posição -- há o que escolher."""
        return self.games_matched > 1


def scan_by_players(
    databases: Path | Sequence[Path],
    wanted: Iterable[PlayerPair],
    *,
    max_games_per_pair: int = MAX_GAMES_PER_PAIR,
    progress: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
) -> dict[PlayerPair, list[GameRecord]]:
    """Uma passada por **cada** base, colhendo só as partidas dos pares pedidos.

    **Sem índice, e é uma decisão medida.** Um índice por nome custaria ~1 GB no disco e uma
    construção de vários minutos para poupar 150 s por livro -- e livro se varre uma vez. O
    dia em que a busca virar por diagrama e não por livro, o índice passa a valer.

    `progress` recebe o número de partidas lidas, a cada 200 mil, **somado entre as bases** --
    quem olha a barra quer saber quanto já se leu, não em qual arquivo se está. `cancel` é
    conferido no mesmo ponto: entre partidas, nunca no meio de uma, pela razão da S-24.

    O teto por par (`max_games_per_pair`) vale para o **conjunto** das bases, e não por
    arquivo: são 40 partidas para reproduzir, venham de onde vierem.
    """
    # `(par[0], par[1])` e nao `tuple(par)`: o segundo perde o tamanho do par para o verificador
    # de tipos, que passa a ver `tuple[str, ...]` onde o resto do modulo promete dois nomes.
    alvos = {(par[0], par[1]) for par in wanted}
    colhidas: dict[PlayerPair, list[GameRecord]] = {}
    if not alvos:
        return colhidas

    lidas = 0
    for base in as_databases(databases):
        lidas = _collect_players(base, alvos, colhidas, max_games_per_pair, progress, cancel, lidas)
        # Depois do arquivo, e nao antes: dentro dele o cancelamento ja e conferido a cada 200
        # mil partidas, e conferi-lo aqui na entrada faria uma bandeira ligada de antemao
        # devolver vazio sem ler nada -- que nao e o que "cancelar" significou ate agora.
        if cancel is not None and cancel.is_set():
            break

    logger.info("Base varrida: %d partidas, %d pares com partida.", lidas, len(colhidas))
    return colhidas


def _collect_players(
    database: Path,
    alvos: set[PlayerPair],
    colhidas: dict[PlayerPair, list[GameRecord]],
    max_games_per_pair: int,
    progress: Callable[[int], None] | None,
    cancel: threading.Event | None,
    lidas: int,
) -> int:
    """Um arquivo. Devolve o total de partidas lidas **incluindo** as das bases anteriores."""
    partidas = lidas
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
    return partidas


@dataclass
class PositionIndex:
    """O resultado de uma varredura por posição: as partidas por colocação, e quantas foram.

    A **contagem** é separada da lista porque elas respondem coisas diferentes: a lista serve
    para preencher os campos, e a contagem para decidir se preencher é honesto. Guardar todas
    as partidas de uma posição de abertura custaria memória para produzir uma resposta que a
    própria contagem manda descartar.
    """

    hits: dict[str, list[PositionHit]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    games_read: int = 0

    complete: bool = True
    """A passada leu a base inteira? **Falso não é "não achou nada": é "não vale nada"** (S-171).

    Sem este campo, os dois estados saíam idênticos daqui -- um `PositionIndex()` vazio --, e
    quem grava não tinha como distinguir. A consequência é a pior possível para este cache:
    `update` registra o conjunto-alvo inteiro como **perguntado**, então uma passada descartada
    gravaria "a base não conhece" sobre milhares de colocações que ninguém chegou a procurar --
    e elas nunca mais voltariam ao alvo de varredura nenhuma (é a decisão da S-84, aqui virada
    contra si mesma).

    O caminho de cancelamento escapava disso por sorte: a Galeria conferia `cancel.is_set()`
    antes de gravar, e o `cvoff-games` não tem cancelamento. Com a S-171 a passada passou a
    poder ser descartada **sem ninguém ter cancelado**, e a sorte acabou.

    A guarda mora no `update` do cache, e não em cada chamador: quem chama não deve precisar
    lembrar de perguntar."""

    def sort(self) -> None:
        """Ordena as partidas de cada posição por um critério estável.

        **Sem isto, duas varreduras da mesma base dão respostas diferentes.** Os pedaços do
        arquivo terminam em ordem imprevisível (`imap_unordered`), e quem consome usa a
        *primeira* partida da lista -- então uma posição que aparece em três partidas podia
        sair com lance 84 numa execução e 56 na seguinte, sem nada ter mudado. Aconteceu aqui,
        e apareceu como dois diagramas cuja procedência não batia entre duas execuções.

        A chave é a data, depois os jogadores: a partida mais antiga com aquela posição é a
        escolha mais defensável quando não há como saber qual delas o livro citou.

        **Continua existindo depois da S-138**, que passou a ordenar dentro do `merge`: quem
        monta um `PositionIndex` a mão -- o cache, os testes -- não passa por `merge` nenhum.
        """
        for achados in self.hits.values():
            achados.sort(key=_hit_order)

    def merge(self, outro: PositionIndex, *, max_hits: int) -> None:
        """Junta o resultado de um pedaço, **ordenando antes de cortar** (S-138).

        Dois defeitos com a mesma raiz moravam aqui, e os dois faziam a resposta depender de
        quantos processos a varredura usou -- ou seja, **qual partida preenche um diagrama
        dependia de um parâmetro de desempenho**.

        1. O corte era por **ordem de chegada**: `achados[:max_hits - len(guardados)]` sobre um
           `imap_unordered`, com o `sort()` rodando depois, sobre o que tinha sobrevivido. Para
           as posições com mais de 32 candidatas, duas varreduras da mesma base sobre o mesmo
           alvo devolviam **conjuntos diferentes**, e a lista da S-86 mudava de conteúdo entre
           execuções sem que nada tivesse mudado.
        2. O caminho sequencial (`--workers 1`) devolvia antes do `total.sort()`, então a
           garantia de determinismo que o `sort` declara não valia justamente no caminho
           documentado como o de depuração.

        Ordenar aqui conserta os dois de uma vez, porque é aqui que a invariante pertence: um
        `PositionIndex` que passou por `merge` está ordenado e cortado pelas **32 mais
        antigas do conjunto**, e não pelas 32 primeiras a chegar. Custa uma ordenação por
        pedaço, e é o preço do teto determinístico.
        """
        self.games_read += outro.games_read
        for colocacao, achados in outro.hits.items():
            guardados = self.hits.setdefault(colocacao, [])
            guardados.extend(achados)
            guardados.sort(key=_hit_order)
            del guardados[max(0, max_hits) :]
        for colocacao, quantas in outro.counts.items():
            self.counts[colocacao] = self.counts.get(colocacao, 0) + quantas


def _hit_order(hit: PositionHit) -> tuple[str, str, str, int]:
    """A ordem canônica de uma lista de candidatas: data, jogadores, lance (S-73).

    Função de topo porque `sort` e `merge` têm de usar a **mesma** chave -- duas cópias dela
    divergiriam na primeira vez que uma fosse corrigida, e o sintoma seria um teto que corta
    candidatas diferentes das que a lista mostra.
    """
    return (
        hit.headers.get("Date", "9999"),
        hit.headers.get("White", ""),
        hit.headers.get("Black", ""),
        hit.move_number,
    )


MAX_HITS_PER_POSITION = 32
"""Quantas partidas guardar por posição.

**Eram 8, quando o único consumidor era o preenchimento automático** -- acima do teto de
`match_positions` nada era preenchido, então guardar mais seria carregar o que ia ser
descartado. A S-83 mudou o consumidor: quem lê isto agora é uma pessoa escolhendo, e o que ela
não recebe ela não pode escolher.

**32 é o tamanho de uma lista que se lê rolando uma vez**, não "quanto mais melhor": acima
disso quem resolve é o filtro da tela, não a rolagem. O custo é desprezível porque só posição
que casou aloca -- no acervo medido, 1.641 de 3.563 diagramas, e a maioria com uma candidata
só. `PositionIndex.counts` continua sendo a verdade sobre **quantas existem**, e é ele que
impede uma lista truncada de passar por completa."""

CANCEL_POLL_SECONDS = 0.5
"""De quanto em quanto tempo a espera por um pedaço devolve o controle para conferir o
cancelamento (S-92).

Meio segundo é imperceptível para quem clicou e desprezível numa passada de meia hora. O que
ele evita é a alternativa óbvia -- conferir o cancelamento **entre** pedaços concluídos --,
que numa varredura de dez processos significa esperar um pedaço inteiro: a passada dividida
por dez, ou seja, minutos depois do clique."""

WORKER_ENV = "CVOFF_GAMES_WORKER"
"""Marca herdada pelos processos-filhos, e a guarda contra a recursão que a S-26 previu.

No Windows o `spawn` faz cada filho **reimportar o `__main__` do pai**. Se esse `__main__` for
um script sem `if __name__ == "__main__"` -- um trecho colado no interpretador, uma célula de
notebook --, o filho reexecuta o script inteiro, que chama esta função de novo, que cria mais
filhos: recursão que consome a máquina em segundos. Aconteceu ao testar isto.

O marcador vai no ambiente **antes** de o `Pool` existir, então o filho já o encontra ao
reimportar, e ali `scan_by_positions` responde com um processo só. A varredura fica lenta num
uso que já estava errado, em vez de derrubar a máquina."""


def chunk_bounds(database: Path, parts: int) -> list[tuple[int, int]]:
    """Corta o arquivo em pedaços, cada um começando numa fronteira de partida.

    Cortar por byte e "andar até o próximo `[Event `" é o que permite dividir 9,7 GB sem
    lê-los antes: a alternativa -- indexar as partidas para saber onde cortar -- custaria uma
    passada inteira para poupar segundos de uma passada inteira.
    """
    tamanho = database.stat().st_size
    marcos = [0]
    with database.open("rb") as fh:
        for i in range(1, max(1, parts)):
            fh.seek(tamanho * i // max(1, parts))
            fh.readline()  # a linha cortada ao meio não é de ninguém
            while True:
                posicao = fh.tell()
                linha = fh.readline()
                if not linha or linha.startswith(b"[Event "):
                    marcos.append(posicao)
                    break
    marcos.append(tamanho)
    return [(marcos[i], marcos[i + 1]) for i in range(len(marcos) - 1) if marcos[i] < marcos[i + 1]]


def _scan_positions_chunk(argumento: tuple[Path, int, int, frozenset[str], frozenset[int], int]) -> PositionIndex:
    """Um pedaço do arquivo, num processo. Precisa ser função de módulo para o `spawn`.

    **Binário, e não texto, e isto não é preferência.** Num arquivo de texto o `tell()` não
    devolve deslocamento de byte: devolve um *cookie* opaco que carrega o estado do decodificador
    e pode ser muito maior que a posição real. Comparado contra o fim do pedaço, ele encerra o
    laço cedo -- medido, 5 partidas lidas de 2.000, silenciosamente. Em binário o `tell()` é o
    byte, que é o que os limites do pedaço significam.
    """
    caminho, inicio, fim, alvos, ocupacoes, max_hits = argumento
    resultado = PositionIndex()
    cabecalho: dict[str, str] = {}
    movetext: list[str] = []

    def processar() -> None:
        if not movetext:
            return
        partida = GameRecord(headers=dict(cabecalho), movetext=" ".join(movetext))
        for colocacao, lance, vez in partida.positions(ocupacoes):
            if colocacao not in alvos:
                continue
            resultado.counts[colocacao] = resultado.counts.get(colocacao, 0) + 1
            guardados = resultado.hits.setdefault(colocacao, [])
            if len(guardados) < max_hits:
                guardados.append(
                    PositionHit(move_number=lance, side_to_move="w" if vez else "b", headers=dict(cabecalho))
                )

    with caminho.open("rb") as fh:
        fh.seek(inicio)
        while fh.tell() < fim:
            linha = fh.readline()
            if not linha:
                break
            if linha.startswith(b"["):
                if linha.startswith(b"[Event "):
                    processar()
                    movetext, cabecalho = [], {}
                    resultado.games_read += 1
                casado = _RE_HEADER.match(linha.decode("utf-8", "replace").rstrip())
                if casado is not None and casado.group(1) in _KEPT_HEADERS:
                    cabecalho[casado.group(1)] = casado.group(2)
                continue
            texto = linha.strip()
            if texto:
                movetext.append(texto.decode("utf-8", "replace"))
        processar()
    return resultado


def _pids_do_pool(pool: Any) -> frozenset[int]:
    """Os pids dos processos que o `Pool` acabou de criar. Vazio se não der para saber.

    `_pool` é atributo privado do `multiprocessing`, e é lido por `getattr` de propósito: numa
    versão que não o tenha, isto devolve vazio e a guarda de `_perdeu_um_filho` desliga sozinha
    -- volta-se ao comportamento anterior, que é ruim, e não a um `AttributeError`, que é pior.
    """
    return frozenset(
        processo.pid for processo in getattr(pool, "_pool", ()) if processo.pid is not None
    )


def _perdeu_um_filho(pool: Any, nascidos: frozenset[int]) -> bool:
    """Algum processo da varredura morreu? **Então um pedaço da base não foi lido.**

    **O defeito, reproduzido em 2026-08-18:** um filho que morre -- OOM, crash nativo, `kill` --
    leva com ele o pedaço que estava lendo, e o `imap_unordered` **nunca** devolve aquele
    resultado. O laço contava conclusões até `len(tarefas)`, então ele esperava para sempre: com
    seis pedaços e um filho morto, cinco voltaram e a varredura ficou pendurada com a barra
    parada em 5 de 6. Numa passada de ~56 min sobre 10 GB de PGN, o sintoma é a Galeria dizendo
    "pedaço 9 de 10" até alguém desistir.

    **O sinal é a troca de pid, e ela é confiável porque o `Pool` repovoa.** Ao perder um
    trabalhador, o `_maintain_pool` cria outro no lugar -- então o conjunto de pids deixa de ser
    o que nasceu com o pool, e isso é observável na volta seguinte do laço. Medido: a troca
    aparece no mesmo décimo de segundo em que o filho morre.

    **A resposta é descartar a passada**, e é a mesma do cancelamento, pela mesma razão da S-92:
    quem viu parte da base tem contagem de partidas por posição que não vale, e é a contagem que
    decide se preencher um header é honesto (S-74). Meia varredura gravada seria procedência
    inventada.
    """
    if not nascidos:
        return False
    return _pids_do_pool(pool) != nascidos


@contextmanager
def _filho_sem_o_main_do_pai() -> Iterator[bool]:
    """Cada filho de `spawn` deixa de reexecutar o script que abriu a janela (S-141).

    **Medido nesta máquina:** o filho reimporta `app_tkinter.py` como `__mp_main__` e isso
    custa **3,14 s e 2.212 módulos** -- `torch`, `cv2`, `PIL` e os seis painéis da interface,
    dos quais ele não usa **nenhum**: ele lê PGN e reproduz lances. Com dez processos são
    ~31 s de CPU e ~2,3 GB de RAM no arranque de cada varredura, numa máquina que ao mesmo
    tempo pode estar treinando.

    **A alavanca é o `main_path`.** O `multiprocessing.spawn.get_preparation_data` só manda o
    caminho do `__main__` ao filho se `sys.modules["__main__"].__file__` existir; sem ele, o
    `_fixup_main_from_path` do outro lado não roda e o filho arranca com o interpretador nu.
    Tirar o atributo enquanto os processos nascem, e devolvê-lo em seguida, é o que separa um
    filho de 2.212 módulos de um de ~50.

    **O preço, dito aqui porque é o que decide se isto pode ser copiado:** o `__main__` do
    filho fica vazio, então **nada que atravesse a fila pode ser definido no script do pai**.
    Nesta chamada nada é: o alvo é `_scan_positions_chunk`, função de topo deste módulo -- que
    já era função de topo por causa da S-26 --, e as tarefas são `Path`, `int` e `frozenset`.
    Se um dia o alvo ou um argumento vier do `__main__`, o filho morre ao desempacotar e o
    laço de espera fica sem resposta. É o contrato desta função, e ele é estreito de propósito.

    **Num bundle congelado isto não roda.** Ali o `spawn` reexecuta o próprio `.exe` e quem
    intercepta é o `freeze_support` (S-55); o caminho é outro, não foi medido aqui, e mexer
    nele às cegas trocaria 3 s por um risco que não sei dimensionar.

    Devolve se a supressão de fato aconteceu -- o teste pergunta isso, e um `pass` silencioso
    passaria por uma economia que não existiu.
    """
    principal = sys.modules.get("__main__")
    caminho = getattr(principal, "__file__", None)
    if principal is None or caminho is None or getattr(sys, "frozen", False):
        yield False
        return
    del principal.__file__
    try:
        yield True
    finally:
        principal.__file__ = caminho


def scan_by_positions(
    databases: Path | Sequence[Path],
    targets: Iterable[str],
    *,
    workers: int | None = None,
    max_hits_per_position: int = MAX_HITS_PER_POSITION,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
) -> PositionIndex:
    """Procura as posições na base reproduzindo os lances de cada partida (S-73).

    **A busca é invertida, e é o que a torna viável.** O caminho óbvio -- indexar as ~800
    milhões de posições da base -- custaria dezenas de GB no disco e horas de construção. Aqui
    quem vai para a memória são as **nossas** posições, que são milhares, e a base passa uma
    vez. Medido: 104 min em dez processos, 10,5 M partidas -- **antes** do porteiro de ocupação
    da S-85, que mede 3,54× num pedaço de 304 MB da base e ainda não foi cronometrado na
    passada inteira. A projeção é ~30 min; o número que vale é o da próxima varredura do acervo.

    E o custo é **por varredura, não por livro**: pôr o acervo inteiro no mesmo conjunto-alvo
    custa o mesmo que pôr um livro. Quem chamar isto uma vez por livro está pagando 32 vezes
    por uma resposta que sai de uma.

    **Várias bases entram na mesma passada (S-93), e não uma passada por arquivo.** Cada
    arquivo é cortado em pedaços e todos os pedaços vão para a mesma fila: os processos não
    ficam ociosos esperando o arquivo grande terminar, o progresso é um só, e o cancelamento
    vale para o conjunto. O `_scan_positions_chunk` já recebia o caminho em cada tarefa, então
    o que mudou aqui foi de onde a lista de tarefas vem.

    `workers=1` roda no próprio processo, sem `multiprocessing` -- é o caminho do teste e o
    de uma base pequena, onde criar dez processos custaria mais que a varredura.

    **`cancel` descarta a passada inteira, e isso não é desperdício: é a única resposta
    verdadeira (S-92).** Uma varredura interrompida viu *parte* da base, e a contagem de
    partidas por posição é justamente o que decide se preencher um header é honesto (S-74). Uma
    posição achada em um dos dez pedaços sairia daqui com `count=1` -- a marca de "partida
    única", que preenche tudo -- quando a base pode ter 47 partidas com ela. Guardar meia
    varredura no cache seria gravar procedência inventada, que é pior que campo vazio.

    Ele é conferido **enquanto os pedaços rodam**, e não entre eles: ver `CANCEL_POLL_SECONDS`.
    Com um pedaço só -- `workers=1`, ou dentro de um processo-filho -- não há o que
    interromper, e o cancelamento só é notado por quem chamou, depois.
    """
    alvos = frozenset(targets)
    total = PositionIndex()
    bases = [caminho for caminho in as_databases(databases) if caminho.is_file()]
    if not alvos or not bases:
        return total

    # O porteiro da S-85, calculado uma vez e enviado pronto aos processos: recalculá-lo em cada
    # filho seria o mesmo trabalho dez vezes, e ele é a condição de a varredura custar 29 min.
    ocupacoes = frozenset(occupancy(colocacao) for colocacao in alvos)

    processos = workers if workers is not None else max(1, (os.cpu_count() or 4) - 2)
    if os.environ.get(WORKER_ENV):
        logger.debug("Já dentro de um processo de varredura: seguindo com um só.")
        processos = 1
    tarefas = [
        (caminho, inicio, fim, alvos, ocupacoes, max_hits_per_position)
        for caminho in bases
        for inicio, fim in (
            chunk_bounds(caminho, processos) if processos > 1 else [(0, caminho.stat().st_size)]
        )
    ]

    if processos == 1:
        # Sequencial, e **não** um pedaço só: com duas bases são duas tarefas, e o caminho sem
        # `multiprocessing` continua tendo de ler as duas.
        for indice, tarefa in enumerate(tarefas, start=1):
            total.merge(_scan_positions_chunk(tarefa), max_hits=max_hits_per_position)
            if progress is not None:
                progress(indice, len(tarefas))
        # Este `return` nao tinha `sort` nenhum, e era o defeito 2 da S-138. Depois de o
        # `merge` passar a ordenar ele e redundante -- e fica, porque e barato e porque a
        # invariante "quem sai daqui esta ordenado" nao pode depender de o leitor saber disso.
        total.sort()
        return total

    # `spawn` no Windows reimporta o modulo do processo pai (S-26). Este modulo e importavel
    # sem efeito colateral, e `_scan_positions_chunk` e funcao de topo justamente por isso.
    os.environ[WORKER_ENV] = "1"
    try:
        # `min`, e nao `len(tarefas)`: com duas bases a lista tem o dobro de pedacos, e um
        # processo por pedaco abriria vinte processos numa maquina de doze nucleos.
        with _filho_sem_o_main_do_pai():
            pool = mp.Pool(min(processos, len(tarefas)))
        with pool:
            nascidos = _pids_do_pool(pool)
            pendentes = pool.imap_unordered(_scan_positions_chunk, tarefas)
            concluidos = 0
            while concluidos < len(tarefas):
                if _perdeu_um_filho(pool, nascidos):
                    pool.terminate()
                    logger.error(
                        "Um processo da varredura morreu em %d de %d pedaços. A passada foi "
                        "descartada: o pedaço que ele lia não voltou, e uma contagem que não viu "
                        "a base inteira não pode preencher header nenhum (S-74).",
                        concluidos,
                        len(tarefas),
                    )
                    return PositionIndex(complete=False)
                if cancel is not None and cancel.is_set():
                    # `terminate` e nao `close`: os processos estao no meio de um pedaco, e
                    # espera-los terminar e exatamente o que o cancelamento pede para nao fazer.
                    pool.terminate()
                    logger.info(
                        "Varredura por posição cancelada em %d de %d pedaços; a passada foi descartada.",
                        concluidos,
                        len(tarefas),
                    )
                    return PositionIndex(complete=False)
                try:
                    # Espera com prazo, e nao um `for` sobre o iterador: e o que devolve o
                    # controle a tempo de conferir o cancelamento enquanto os pedacos rodam.
                    parcial = pendentes.next(timeout=CANCEL_POLL_SECONDS)
                except mp.TimeoutError:
                    continue
                total.merge(parcial, max_hits=max_hits_per_position)
                concluidos += 1
                if progress is not None:
                    progress(concluidos, len(tarefas))
    finally:
        os.environ.pop(WORKER_ENV, None)
    total.sort()
    return total


def agrees_with_caption(hit: PositionHit, pair: PlayerPair) -> bool:
    """A partida é entre os dois nomes que a legenda declara (S-91).

    **Sem exigir a ordem das cores.** O livro escreve "Coull - Stanciu" sem prometer quem tinha
    as brancas, e o `parse_context` devolve os nomes na ordem em que aparecem. Exigir a ordem
    reprovaria metade dos acertos por uma informação que a legenda não deu.
    """
    return {surname(hit.headers.get("White", "")), surname(hit.headers.get("Black", ""))} == set(pair)


def rank_candidates(
    candidates: Sequence[PositionHit], pair: PlayerPair | None
) -> tuple[tuple[PositionHit, ...], bool]:
    """Põe na frente as candidatas que a legenda confirma. Devolve `(lista, só uma bateu)`.

    **Ordena, não filtra**, e a diferença é medida: 26,5% das legendas que trazem nomes
    discordam da partida mesmo quando a posição aparece numa única partida da base -- grafia
    diferente, legenda do diagrama vizinho, o livro nomeando outra coisa. Filtrar por uma fonte
    que erra um quarto das vezes tiraria a partida certa da lista, e a lista é justamente o que
    a pessoa tem para discordar de nós.

    A ordem de dentro de cada grupo é a que veio -- por data, pela S-73 --, então quando a
    legenda não diz nada o resultado é exatamente o de antes.
    """
    if pair is None or not candidates:
        return tuple(candidates), False
    confirmadas = [hit for hit in candidates if agrees_with_caption(hit, pair)]
    if not confirmadas:
        return tuple(candidates), False
    restantes = [hit for hit in candidates if not agrees_with_caption(hit, pair)]
    return (*confirmadas, *restantes), len(confirmadas) == 1


def match_positions(entries: Sequence[Any], index: PositionIndex, *, max_games: int = 5) -> list[DiagramMatch]:
    """Cruza os diagramas com o que a varredura por posição achou.

    Diferente do caminho por nome em um ponto que importa: aqui **não há legenda para
    confirmar**. O que sustenta o casamento são as 64 casas e nada mais, e por isso a contagem
    de partidas é o único freio -- uma posição que aparece em 300 partidas não identifica
    partida nenhuma, e o `max_games` de quem consome decide o que fazer com ela.
    """
    achados: list[DiagramMatch] = []
    for entrada in entries:
        colocacao = getattr(entrada, "placement", "")
        registros = index.hits.get(colocacao)
        if not registros:
            continue
        quantas = index.counts.get(colocacao, len(registros))
        # A legenda entra aqui e não na varredura: ela é do diagrama, e a varredura responde
        # por posição -- a mesma posição pode estar em dois livros com legendas diferentes.
        candidatas, pela_legenda = rank_candidates(registros, pair_from_caption(getattr(entrada, "caption", "") or ""))
        primeiro = candidatas[0]
        achados.append(
            DiagramMatch(
                page_index=int(entrada.page_index),
                diagram_index=int(entrada.diagram_index),
                move_number=primeiro.move_number,
                side_to_move=primeiro.side_to_move,
                headers=dict(primeiro.headers),
                games_matched=quantas,
                game_label=primeiro.label,
                caption_confirmed=pela_legenda,
                candidates=candidatas,
            )
        )
    return achados


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
        # Uma candidata por **partida**, e não por casamento: uma repetição de posição faz a
        # mesma partida aparecer duas vezes em `casamentos`, e oferecer duas vezes a mesma
        # escolha à pessoa não é oferecer duas escolhas.
        candidatas = _candidates_from_games(casamentos)
        # Aqui a legenda já escolheu as partidas -- foi ela que definiu o par procurado --, e o
        # que `rank_candidates` acrescenta é só a resposta sobre unicidade. Chamá-lo mesmo assim
        # mantém uma regra só de "a legenda confirma?" nos dois caminhos.
        candidatas, pela_legenda = rank_candidates(candidatas, par)
        # A primeira candidata é a resposta, e não mais "a primeira partida que a base guardou"
        # (S-83). São os dois caminhos passando a concordar sobre *qual* é a escolha padrão --
        # antes, a tela mostraria a lista com uma marcada e a anotação diria outra.
        primeira = candidatas[0]
        achados.append(
            DiagramMatch(
                page_index=int(entrada.page_index),
                diagram_index=int(entrada.diagram_index),
                move_number=primeira.move_number,
                side_to_move=primeira.side_to_move,
                headers=dict(primeira.headers),
                games_matched=len({id(item[3]) for item in casamentos}),
                game_label=primeira.label,
                caption_confirmed=pela_legenda,
                candidates=candidatas,
            )
        )
    return achados


def kept_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Só os headers que descrevem a partida. O resto da base descreve a base."""
    return {campo: headers[campo] for campo in _KEPT_HEADERS if headers.get(campo)}


def _candidates_from_games(
    matches: Sequence[tuple[str, int, bool, GameRecord]],
    *,
    max_hits: int = MAX_HITS_PER_POSITION,
) -> tuple[PositionHit, ...]:
    """As candidatas do caminho por nome, na mesma forma que as do caminho por posição (S-83).

    A ordem é a de `PositionIndex.sort` -- data, jogadores, lance --, e pela mesma razão da
    S-73: quem consome usa a primeira, e ela não pode depender da ordem em que a base guardou
    as partidas.
    """
    vistas: dict[str, PositionHit] = {}
    for _, lance, vez, partida in matches:
        candidata = PositionHit(
            move_number=int(lance), side_to_move="w" if vez else "b", headers=kept_headers(partida.headers)
        )
        vistas.setdefault(candidata.key, candidata)
    ordenadas = sorted(
        vistas.values(),
        key=lambda hit: (
            hit.headers.get("Date", "9999"),
            hit.headers.get("White", ""),
            hit.headers.get("Black", ""),
            hit.move_number,
        ),
    )
    return tuple(ordenadas[:max_hits])
