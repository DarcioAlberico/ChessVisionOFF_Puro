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

**Os dois caminhos, e o que cada um custa.**

| | por nome (S-72) | por posição (S-73) |
|---|---|---|
| alcança | os diagramas cuja legenda traz os dois jogadores | **todos** |
| mediu, no `Secrets of Chess Training` | 61 de 1.408 | **581** preenchíveis de 1.408 |
| custo | ~150 s, um processo | ~104 min em dez processos |
| onde mora | botão da Galeria | `cvoff-games --positions` |

O caminho por posição é ~10× mais abrangente e ~40× mais caro, e o custo dele é **por
varredura, não por livro**: o conjunto-alvo cabe na memória sejam 1.400 posições ou 40 mil,
então o acervo inteiro cabe na mesma passada. É por isso que ele é comando de linha e não
botão -- e porque 104 minutos atrás de um botão é uma janela travada que ninguém entende.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
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
    "PositionHit",
    "PositionIndex",
    "default_database_path",
    "match_entries",
    "match_positions",
    "pair_from_caption",
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


@dataclass(frozen=True)
class PositionHit:
    """Uma partida da base que passou por uma posição que estamos procurando (S-73)."""

    move_number: int
    side_to_move: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        evento = " ".join(x for x in (self.headers.get("Event", ""), self.headers.get("Date", "")[:4]) if x)
        return f"{self.headers.get('White', '?')} x {self.headers.get('Black', '?')}" + (f", {evento}" if evento else "")


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

    def sort(self) -> None:
        """Ordena as partidas de cada posição por um critério estável.

        **Sem isto, duas varreduras da mesma base dão respostas diferentes.** Os pedaços do
        arquivo terminam em ordem imprevisível (`imap_unordered`), e quem consome usa a
        *primeira* partida da lista -- então uma posição que aparece em três partidas podia
        sair com lance 84 numa execução e 56 na seguinte, sem nada ter mudado. Aconteceu aqui,
        e apareceu como dois diagramas cuja procedência não batia entre duas execuções.

        A chave é a data, depois os jogadores: a partida mais antiga com aquela posição é a
        escolha mais defensável quando não há como saber qual delas o livro citou.
        """
        for achados in self.hits.values():
            achados.sort(
                key=lambda hit: (
                    hit.headers.get("Date", "9999"),
                    hit.headers.get("White", ""),
                    hit.headers.get("Black", ""),
                    hit.move_number,
                )
            )

    def merge(self, outro: PositionIndex, *, max_hits: int) -> None:
        self.games_read += outro.games_read
        for colocacao, achados in outro.hits.items():
            guardados = self.hits.setdefault(colocacao, [])
            guardados.extend(achados[: max(0, max_hits - len(guardados))])
        for colocacao, quantas in outro.counts.items():
            self.counts[colocacao] = self.counts.get(colocacao, 0) + quantas


MAX_HITS_PER_POSITION = 8
"""Quantas partidas guardar por posição. Acima do teto de `match_positions` ela não preenche
nada, então guardar mais seria carregar o que vai ser descartado."""

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


def _scan_positions_chunk(argumento: tuple[Path, int, int, frozenset[str], int]) -> PositionIndex:
    """Um pedaço do arquivo, num processo. Precisa ser função de módulo para o `spawn`.

    **Binário, e não texto, e isto não é preferência.** Num arquivo de texto o `tell()` não
    devolve deslocamento de byte: devolve um *cookie* opaco que carrega o estado do decodificador
    e pode ser muito maior que a posição real. Comparado contra o fim do pedaço, ele encerra o
    laço cedo -- medido, 5 partidas lidas de 2.000, silenciosamente. Em binário o `tell()` é o
    byte, que é o que os limites do pedaço significam.
    """
    caminho, inicio, fim, alvos, max_hits = argumento
    resultado = PositionIndex()
    cabecalho: dict[str, str] = {}
    movetext: list[str] = []

    def processar() -> None:
        if not movetext:
            return
        partida = GameRecord(headers=dict(cabecalho), movetext=" ".join(movetext))
        for colocacao, lance, vez in partida.positions():
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


def scan_by_positions(
    database: Path,
    targets: Iterable[str],
    *,
    workers: int | None = None,
    max_hits_per_position: int = MAX_HITS_PER_POSITION,
    progress: Callable[[int, int], None] | None = None,
) -> PositionIndex:
    """Procura as posições na base reproduzindo os lances de cada partida (S-73).

    **A busca é invertida, e é o que a torna viável.** O caminho óbvio -- indexar as ~800
    milhões de posições da base -- custaria dezenas de GB no disco e horas de construção. Aqui
    quem vai para a memória são as **nossas** posições, que são milhares, e a base passa uma
    vez. Medido: 104 min em dez processos, 10,5 M partidas.

    E o custo é **por varredura, não por livro**: pôr o acervo inteiro no mesmo conjunto-alvo
    custa o mesmo que pôr um livro. Quem chamar isto uma vez por livro está pagando 32 vezes
    por uma resposta que sai de uma.

    `workers=1` roda no próprio processo, sem `multiprocessing` -- é o caminho do teste e o
    de uma base pequena, onde criar dez processos custaria mais que a varredura.
    """
    alvos = frozenset(targets)
    total = PositionIndex()
    if not alvos or not database.is_file():
        return total

    processos = workers if workers is not None else max(1, (os.cpu_count() or 4) - 2)
    if os.environ.get(WORKER_ENV):
        logger.debug("Já dentro de um processo de varredura: seguindo com um só.")
        processos = 1
    pedacos = chunk_bounds(database, processos) if processos > 1 else [(0, database.stat().st_size)]
    tarefas = [(database, inicio, fim, alvos, max_hits_per_position) for inicio, fim in pedacos]

    if len(tarefas) == 1:
        total.merge(_scan_positions_chunk(tarefas[0]), max_hits=max_hits_per_position)
        if progress is not None:
            progress(1, 1)
        return total

    # `spawn` no Windows reimporta o modulo do processo pai (S-26). Este modulo e importavel
    # sem efeito colateral, e `_scan_positions_chunk` e funcao de topo justamente por isso.
    os.environ[WORKER_ENV] = "1"
    try:
        with mp.Pool(len(tarefas)) as pool:
            for concluidos, parcial in enumerate(pool.imap_unordered(_scan_positions_chunk, tarefas), start=1):
                total.merge(parcial, max_hits=max_hits_per_position)
                if progress is not None:
                    progress(concluidos, len(tarefas))
    finally:
        os.environ.pop(WORKER_ENV, None)
    total.sort()
    return total


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
        primeiro = registros[0]
        achados.append(
            DiagramMatch(
                page_index=int(entrada.page_index),
                diagram_index=int(entrada.diagram_index),
                move_number=primeiro.move_number,
                side_to_move=primeiro.side_to_move,
                headers=dict(primeiro.headers),
                games_matched=quantas,
                game_label=primeiro.label,
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
