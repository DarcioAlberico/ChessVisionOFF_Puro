"""A árvore de aberturas: que lances a base jogou a partir desta posição, e com que resultado (S-535).

**O gesto que faltava.** `estudo_partidas.consultar` responde *que partidas passam por aqui*, e o
docstring dele registra, desde a S-287, o que ele **não** faz: *"não devolve os lances jogados a
partir daqui e a frequência de cada um, que é a segunda metade da janela de aberturas do
ChessBase"*. Isto é a segunda metade.

## Por que um índice novo, e não uma pergunta ao que já existe

O índice da S-533 (`games_index.py`, versão 6) é **por partida**: uma linha por jogo, com
jogadores, ano, Elo, resultado e ECO. Ele não conhece posição nenhuma -- `buscar` confere a
posição **relendo** até `TETO_DE_REPLAY` candidatas do `.pgn`, e diz quantas leu. Para *"que
lances saem desta posição"* isso não serve: a resposta precisa de **todas** as partidas que
passam pela posição, não de uma amostra de duas mil.

O cache da S-84 (`games_cache.py`) guarda, por colocação, quantas partidas a contêm e até 32
delas -- e **não guarda a continuação**, que é o lance jogado dali. Derivá-la exigiria reproduzir
as partidas de novo.

Então o que este módulo constrói é o que não existia: **um lance por linha, agregado**.

## O que foi medido antes de escolher a profundidade

Medido em 2026-09-05 sobre a `LumbrasGigaBase_OTB_Complete.pgn` (8,6 GB, 10.355.488 partidas),
em dez pedaços de 100 mil partidas espalhados pelo arquivo -- um milhão de partidas ao todo:

| ply | linhas | pares `(posição, lance)` distintos | com 2+ partidas | fator |
|---|---|---|---|---|
| 4 | 1.000.000 | 11.608 | 6.393 | 0,012 |
| 9 | 1.000.000 | 119.879 | 43.109 | 0,120 |
| 14 | 1.000.000 | 359.778 | 79.376 | 0,360 |
| 15 | 1.000.000 | 419.734 | 83.546 | 0,420 |
| **19** | 1.000.000 | **649.958** | 79.250 | **0,650** |
| 24 | 988.631 | 845.760 | 48.404 | 0,855 |
| 29 | 968.713 | 915.494 | 23.350 | 0,945 |
| 39 | 907.914 | 896.172 | 7.817 | 0,987 |

**O `fator` é onde a árvore deixa de ser árvore.** Ele é a fração de linhas que são um par novo:
0,012 no ply 4 quer dizer que 86 partidas passam pelo par médio; 0,987 no ply 39 quer dizer que
**cada partida está sozinha no seu nó**, e uma "árvore" em que todo lance tem uma partida é a
lista de partidas com outro nome -- que é o que `games_index.buscar` já dá, sem custar índice.

A coluna *com 2+ partidas* diz a mesma coisa pelo outro lado: ela **cresce até o ply 15** (83.546)
e **cai** a partir dali; no ply 39 são 7.817 nós, 0,9% dos 896.172.

**Vinte meios-lances -- dez lances de cada lado -- é onde os dois números ainda pagam**, e é o
`PROFUNDIDADE` deste módulo. As três profundidades que o item pedia, medidas na mesma passada de um
milhão de partidas (os pares acumulados até aquele ply) e no mesmo custo de replay por partida:

| profundidade | pares distintos | contra os 20 plies | µs por partida |
|---|---|---|---|
| **20 plies** | **4.303.194** | 1× | 869 |
| 30 plies | 12.675.668 | 2,95× | 1.331 (1,53×) |
| 40 plies | 21.823.278 | 5,07× | 1.681 (1,93×) |

Quarenta plies custariam cinco vezes o disco e o dobro do tempo para responder o que a busca por
filtros já responde: no ply 39, **987 de cada mil** nós têm uma partida só.

## O que este módulo não promete

**A posição fora da profundidade não é "nenhuma partida".** É `FUNDO_DEMAIS`, e a diferença é a
mesma que a S-135 custou caro para aprender e que `estudo_partidas` escreveu em quatro estados:
dizer *"nenhum lance foi jogado daqui"* sobre uma posição que ninguém indexou é um número
enganoso. Quem pergunta passa o `ply` da posição junto, e é ele que separa os dois.

**A chave é a colocação e a vez, e nada mais** -- a mesma que `games_db.GameRecord.positions`
produz e que `games_cache` guarda, pela regra 1 do módulo de lá. Roque e *en passant* ficam de
fora, então duas posições iguais nas 64 casas e na vez, com direitos de roque diferentes, somam as
estatísticas.

**E isso quase nunca acontece, agora com número.** Medido em 2026-09-05 no mesmo milhão de
partidas, até o ply 40: das **20.381.789** chaves `(colocação, vez)` distintas, **193** -- nove
em cada dez milhões, 0,0009% -- aparecem com mais de um conjunto de direitos de roque. Inventar
aqui uma segunda chave de posição (a FEN de quatro campos, ou o `_transposition_key` privado do
`python-chess`) faria o programa ter duas noções de "mesma posição" por causa disso, e a que a
sala usa para tudo o mais é esta.

Nada de `PyQt6` aqui, e nada de decisão de tela: o que a árvore mostra, como se ordena e como se
formata está em `ui/arvore_de_aberturas.py`.
"""

from __future__ import annotations

import hashlib
import logging
import multiprocessing as mp
import os
import sqlite3
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess

from .config import PROJECT_ROOT
from .games_db import (
    _ABRE_CABECALHO,
    _BOM,
    _RE_BRACES,
    _RE_HEADER,
    _RE_SAN,
    CANCEL_POLL_SECONDS,
    WORKER_ENV,
    _filho_sem_o_main_do_pai,
    _perdeu_um_filho,
    _pids_do_pool,
    _sem_variantes,
    abrir_pgn_bytes,
    as_databases,
    chunk_bounds,
    decodificar_linha,
    eh_comprimida,
    existe_base,
)
from .games_index import index_fingerprint
from .ui.busca_de_partidas import ANO_MAXIMO, ANO_MINIMO, ELO_MAXIMO

logger = logging.getLogger(__name__)

__all__ = [
    "ACHOU",
    "DEFAULT_TREE_PATH",
    "FUNDO_DEMAIS",
    "PROFUNDIDADE",
    "SEM_ARVORE",
    "SEM_PARTIDA",
    "TREE_VERSION",
    "Arvore",
    "Construcao",
    "Ramo",
    "chave_da_posicao",
    "construir",
    "consultar",
    "resumo_do_arquivo",
]

DEFAULT_TREE_PATH = PROJECT_ROOT / "data" / "games_openings.sqlite"
"""Onde a árvore mora. Em `data/`, com o resto do que é derivado e reconstruível."""

TREE_VERSION = 1

PROFUNDIDADE = 20
"""Quantos meios-lances de cada partida entram na árvore. Dez lances de cada lado.

**É o número que a medição escolheu**, e a tabela do cabeçalho do módulo é o argumento: no ply 19
ainda há 79.250 nós com duas partidas ou mais num milhão de partidas, e o fator de nós novos é
0,650; no ply 29 o fator é 0,945 -- cada partida sozinha no seu nó -- e os nós com 2+ caíram para
23.350. Indexar até lá custaria 2,95× o disco para responder o que a busca por filtros já responde.

**E é o número que decide o que a árvore promete.** Uma posição no ply 20 ou além sai como
`FUNDO_DEMAIS` e não como "nenhuma partida": ver o cabeçalho do módulo."""

MINIMO_DE_PLIES = 1
"""Profundidade mínima aceita por `construir`. Zero seria um arquivo com a posição inicial e nada
mais -- e o `argparse` de quem digitar `--profundidade 0` merece o erro aqui e não um arquivo."""

SEM_ARVORE = "sem-arvore"
"""Não há arquivo de árvore, ou ele é de outro formato, ou de outra base."""

FUNDO_DEMAIS = "fundo-demais"
"""A posição está além da profundidade gravada. **Não é "nenhuma partida"** -- ver o módulo."""

SEM_PARTIDA = "sem-partida"
"""A posição está dentro da profundidade e a base não chega a ela por lance nenhum."""

ACHOU = "achou"

COMO_CONSTRUIR = "cvoff-games --build-tree"
"""O comando que faz a passada. Escrito aqui e não na janela, porque a frase que o cita é daqui --
a mesma regra de `estudo_partidas.COMO_PERGUNTAR`."""

_CAMPOS = ("Result", "WhiteElo", "BlackElo", "Date", "FEN")
"""Os headers que a passada guarda. `FEN` só para **descartar** a partida: uma composição montada
não tem abertura, e as jogadas dela não saem da posição inicial."""

_LOTE_DE_RAMOS = 400_000
"""Pares acumulados na memória de um processo antes de descarregar no parcial dele.

Quatrocentos mil pares são ~120 MB de dicionário Python nesta máquina, e dez processos cabem nos
16 GB livres medidos. Menos que isso multiplica as gravações -- cada descarga é um `UPSERT` por
par --, e mais que isso é a máquina paginando durante uma passada de meia hora."""

_INTERVALO_DE_PROGRESSO = 0.5
"""Segundos entre dois avisos de progresso. A passada é de dezenas de minutos e o aviso é uma
barra: dois por segundo já é mais do que qualquer olho lê."""

Progresso = Callable[[int, int, int], None]
"""`(pedaços prontos, pedaços ao todo, partidas lidas)`. Os pedaços são a unidade porque é a que
termina: dentro de um pedaço não há como saber quantas partidas faltam sem lê-las."""


@dataclass(frozen=True)
class Ramo:
    """Um lance jogado a partir da posição perguntada, com o que a base diz sobre ele.

    **Os três resultados são contados, e o `*` não é nenhum deles.** `partidas` é o total;
    `brancas + empates + pretas` pode ser menor, e a diferença são as partidas cujo header
    `[Result]` é `*` -- interrompidas, ou de um arquivo que não o registra. Somar `*` a empate
    seria inventar meio ponto, e distribuí-lo entre os três seria pior.
    """

    lance: str
    partidas: int
    brancas: int
    empates: int
    pretas: int

    soma_elo: int = 0
    com_elo: int = 0
    """Soma dos Elos médios e quantas partidas os têm. **Dois campos e não a média** porque a
    média de um nó é a média das partidas dele, e somar médias de sub-nós daria outro número."""

    soma_ano: int = 0
    com_ano: int = 0
    ano_min: int = 0
    ano_max: int = 0

    @property
    def decididas(self) -> int:
        """Quantas terminaram. É o denominador das percentagens -- ver `ui/arvore_de_aberturas`."""
        return self.brancas + self.empates + self.pretas


@dataclass(frozen=True)
class Arvore:
    """O que a base respondeu sobre a posição: os lances, e de que estado a resposta é."""

    estado: str
    ramos: tuple[Ramo, ...] = ()
    profundidade: int = 0
    """A profundidade **do arquivo**, e não a da pergunta: é ela que a frase de `FUNDO_DEMAIS`
    precisa citar, e ela vale mesmo quando não há ramo nenhum."""

    ply: int = 0

    @property
    def achou(self) -> bool:
        return self.estado == ACHOU

    @property
    def partidas(self) -> int:
        """Quantas partidas da base passam por esta posição -- a soma dos ramos.

        **É a soma e não uma contagem própria**, e ela não é a contagem de partidas por duas
        razões medidas. Para **menos**: quem termina *na* posição não joga lance nenhum dali e
        não está em ramo algum -- por isso este número pode ficar abaixo do de
        `estudo_partidas.consultar`, que conta a posição e não a continuação. Para **mais**: uma
        partida que volta à mesma posição conta as duas passagens, porque as duas são um lance
        jogado dali. Medido numa fatia de 20 MB da gigabase: 7 partidas de 27.395 voltam à
        **posição inicial** com um vaivém de cavalos (`1.Nc3 Nc6 2.Nb1 Nb8`), e a raiz soma
        27.403.
        """
        return sum(ramo.partidas for ramo in self.ramos)


@dataclass(frozen=True)
class Construcao:
    """O que uma rodada de `construir` fez."""

    partidas: int = 0
    ramos: int = 0
    profundidade: int = PROFUNDIDADE
    segundos: float = 0.0
    bytes_no_disco: int = 0
    cancelada: bool = False
    """A rodada parou a pedido. **O arquivo não recebe a marca da base**, e por isso a consulta o
    recusa: meia árvore responderia "duzentas partidas" onde há duas mil, e uma percentagem sobre
    a metade que se leu é pior que nenhuma -- ver `games_cache.PositionStore.update`, mesma regra."""


def chave_da_posicao(colocacao: str, vez: str) -> int:
    """As 64 casas e a vez como um inteiro de 64 bits. Estável entre execuções.

    **Não é o `hash()` do Python**, pela mesma razão de `games_index.pair_hash`: ele é
    aleatorizado por processo desde a 3.3, e uma árvore gravada hoje não seria consultável amanhã
    -- em silêncio, respondendo "nenhum lance".

    **A colisão aqui custa mais que lá, e é por isso que ela está medida.** Em `pair_hash` quem
    consulta relê a partida e confere os nomes; aqui não há o que reler -- duas posições que
    colidissem somariam as estatísticas. Com 64 bits e as ~28 milhões de chaves que a gigabase
    produz em vinte plies, a probabilidade de haver **alguma** colisão é ~2×10⁻⁵ (aniversário:
    n²/2^65). A guarda que sobra é de `ui/arvore_de_aberturas.ramos_legais`, que descarta o lance
    que não é legal na posição perguntada: uma colisão vira lance faltando, e não estatística
    errada em silêncio.

    Guardar a colocação inteira em vez do resumo custaria ~50 bytes por chave -- mais de um
    gigabyte de texto num artefato cuja linha inteira tem 45 -- para tirar um erro de 2×10⁻⁵.
    """
    marca = f"{colocacao} {vez}".encode()
    return int.from_bytes(hashlib.blake2b(marca, digest_size=8).digest(), "big") & 0x7FFFFFFFFFFFFFFF


# --------------------------------------------------------------------------------- o arquivo

_CRIAR = (
    "CREATE TABLE IF NOT EXISTS ramos ("
    "chave INTEGER NOT NULL, lance TEXT NOT NULL, n INTEGER NOT NULL, "
    "brancas INTEGER NOT NULL, empates INTEGER NOT NULL, pretas INTEGER NOT NULL, "
    "soma_elo INTEGER NOT NULL, com_elo INTEGER NOT NULL, "
    "soma_ano INTEGER NOT NULL, com_ano INTEGER NOT NULL, "
    "ano_min INTEGER NOT NULL, ano_max INTEGER NOT NULL, "
    "PRIMARY KEY (chave, lance)) WITHOUT ROWID"
)
"""`WITHOUT ROWID`, e é a decisão que a S-533 já mediu no índice por nome (v3): a chave de busca
**é** a árvore, e as doze colunas viajam na mesma folha. Aqui não há um segundo caminho de busca --
pergunta-se sempre pela chave --, então o argumento que fez a v5 desfazer aquilo não vale."""

_MENOR_ANO = (
    "coalesce(min(nullif(ano_min, 0), nullif(excluded.ano_min, 0)), "
    "nullif(ano_min, 0), nullif(excluded.ano_min, 0), 0)"
)
"""O menor ano **entre os que existem**, e zero quando nenhum existe.

**`min(a, b)` cru estava errado, e o defeito foi visto na gigabase inteira**: zero é "esta linha
não tem partida com data", e `min(0, 1902)` é 0 -- a coluna Ano saía `2015 (0–2026)` no ramo `6.d3`
da Ruy Lopez fechada. O `nullif` transforma o zero em ausência, e o `min` de dois argumentos do
SQLite devolve NULL se qualquer um for NULL: por isso os dois `coalesce` de reserva, que respondem
quando só um dos lados tem ano. Ver `_fundir`, que faz o mesmo com o `min` de agregação."""

_UPSERT = (
    "INSERT INTO ramos VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
    "ON CONFLICT(chave, lance) DO UPDATE SET "
    "n = n + excluded.n, brancas = brancas + excluded.brancas, "
    "empates = empates + excluded.empates, pretas = pretas + excluded.pretas, "
    "soma_elo = soma_elo + excluded.soma_elo, com_elo = com_elo + excluded.com_elo, "
    "soma_ano = soma_ano + excluded.soma_ano, com_ano = com_ano + excluded.com_ano, "
    f"ano_min = {_MENOR_ANO}, ano_max = max(ano_max, excluded.ano_max)"
)

_LER = (
    "SELECT lance, n, brancas, empates, pretas, soma_elo, com_elo, soma_ano, com_ano, ano_min, ano_max "
    "FROM ramos WHERE chave = ?"
)


def _preparar(conexao: sqlite3.Connection) -> None:
    conexao.execute(_CRIAR)
    conexao.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conexao.commit()


def _meta(conexao: sqlite3.Connection, chave: str) -> str:
    linha = conexao.execute("SELECT value FROM meta WHERE key = ?", (chave,)).fetchone()
    return "" if linha is None else str(linha[0])


def _gravar_meta(conexao: sqlite3.Connection, valores: dict[str, str]) -> None:
    with conexao:
        conexao.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", sorted(valores.items()))


# ------------------------------------------------------------------------------- a construção


def _inteiro(texto: str) -> int:
    limpo = texto.strip()
    return int(limpo) if limpo.isdigit() else 0


def _na_faixa(valor: int, menor: int, maior: int) -> int:
    """O valor, ou zero quando ele está fora da faixa. Zero é "a base não disse" em toda coluna.

    **A faixa é a que o formulário de busca já declara** (`ui/busca_de_partidas.ANO_MINIMO`,
    `ANO_MAXIMO`, `ELO_MAXIMO`), e reusá-la é o item: são as mesmas perguntas -- *este ano é um
    ano?*, *este Elo é um rating?* --, e duas réguas divergiriam na primeira vez que uma fosse
    corrigida.

    **Sem isto, a coluna Ano da raiz saía `2005 (2–2026)`**, medido na gigabase inteira em
    2026-09-05: a base tem partidas com `[Date "0002.??.??"]`, e `2` é um número que ninguém
    mediu ocupando a ponta de uma faixa. Descartar o campo é o que o resto do programa já faz
    com data ilegível (`_ano` de `games_index`), e o efeito na média é nulo -- são punhados de
    partidas em dez milhões.
    """
    return valor if menor <= valor <= maior else 0


def _elo_medio(cabecalho: dict[str, str]) -> int:
    """A média dos dois Elos, ou zero quando um deles falta ou está fora da faixa.

    **Média e não o menor**, ao contrário de `games_index._linha_da_partida`: lá o número responde
    *"esta partida é de que nível?"*, e uma partida de 2882 contra 2100 não é de 2700. Aqui a
    coluna responde *"quem joga este lance?"*, e a resposta é o nível dos dois jogadores -- que é
    o que o ChessBase mostra na coluna Elo da árvore.
    """
    branco = _na_faixa(_inteiro(cabecalho.get("WhiteElo", "")), 1, ELO_MAXIMO)
    preto = _na_faixa(_inteiro(cabecalho.get("BlackElo", "")), 1, ELO_MAXIMO)
    return (branco + preto) // 2 if branco and preto else 0


_PONTOS = {"1-0": 0, "1/2-1/2": 1, "0-1": 2}
"""`[Result] -> qual dos três contadores sobe`. O que não estiver aqui -- `*`, e o header ausente --
não sobe nenhum, e a diferença para `n` é o que `Ramo.decididas` mede."""


LANCE_DESCONHECIDO = frozenset({"--", "Z0", "z0"})
"""O que a base escreve onde o lance não foi registrado, e o `python-chess` aceita como lance nulo.

**Ele encerra a partida aqui, e isso é decisão.** `parse_san` traduz `--` num lance nulo -- a
posição fica igual e só a vez troca --, e o efeito na árvore foi medido: numa fatia de 20 MB da
gigabase, **7 partidas de 27.395** voltavam à posição inicial depois de dois `--` e contavam duas
vezes na raiz. Uma partida cujo lance ninguém anotou não tem continuação a mostrar: as posições
depois dele são ficção, e uma árvore feita de ficção é pior que uma árvore mais curta."""


def _plies_da_partida(movetext: str, teto: int) -> Iterable[str]:
    """Os SAN da linha principal, até `teto`. Sem tabuleiro: só o filtro de token da `games_db`.

    **As variantes saem antes**, pela razão que `games_db._sem_variantes` mede: sem isso,
    `1. d7 (1. Ba6 Bc6 2. Bb7) 1... Bxd7` é lido como `d7 Ba6 Bc6 Bb7 Bxd7`, e o replay sai da
    linha no primeiro parêntese -- produzindo posições que a partida nunca teve.
    """
    quantos = 0
    for token in _sem_variantes(_RE_BRACES.sub(" ", movetext)).replace(".", ". ").split():
        limpo = token.replace("!", "").replace("?", "")
        if not limpo or limpo[0].isdigit() or not _RE_SAN.fullmatch(limpo):
            continue
        if limpo in LANCE_DESCONHECIDO:
            return
        yield limpo
        quantos += 1
        if quantos >= teto:
            return


def _somar(acumulado: dict[tuple[int, str], list[int]], chave: tuple[int, str], cabecalho: dict[str, str]) -> None:
    registro = acumulado.get(chave)
    if registro is None:
        registro = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        acumulado[chave] = registro
    registro[0] += 1
    ponto = _PONTOS.get(cabecalho.get("Result", "").strip())
    if ponto is not None:
        registro[1 + ponto] += 1
    elo = _elo_medio(cabecalho)
    if elo:
        registro[4] += elo
        registro[5] += 1
    ano = _na_faixa(_inteiro(cabecalho.get("Date", "")[:4]), ANO_MINIMO, ANO_MAXIMO)
    if ano:
        registro[6] += ano
        registro[7] += 1
        registro[8] = ano if not registro[8] else min(registro[8], ano)
        registro[9] = max(registro[9], ano)


def _descarregar(conexao: sqlite3.Connection, acumulado: dict[tuple[int, str], list[int]]) -> None:
    if not acumulado:
        return
    with conexao:
        conexao.executemany(
            _UPSERT,
            [(chave, lance, *valores) for (chave, lance), valores in acumulado.items()],
        )
    acumulado.clear()


def _pedaco(argumento: tuple[Path, int, int, int, str]) -> tuple[int, str]:
    """Um pedaço do arquivo, num processo, gravando o parcial dele. Devolve `(partidas, caminho)`.

    Função de topo porque o `spawn` do Windows precisa importá-la pelo nome -- a mesma razão da
    S-26 em `games_db._scan_positions_chunk`, e o mesmo contrato: nada que atravesse a fila pode
    vir do `__main__` de quem chamou.

    **Cada processo tem o seu arquivo, e o pai os funde no fim.** A alternativa -- dez processos
    gravando no mesmo SQLite -- serializaria as dez em uma, que é o oposto de repartir a passada.
    """
    caminho, inicio, fim, profundidade, destino = argumento
    conexao = sqlite3.connect(destino)
    conexao.execute("PRAGMA journal_mode = OFF")
    conexao.execute("PRAGMA synchronous = OFF")
    _preparar(conexao)

    acumulado: dict[tuple[int, str], list[int]] = {}
    partidas = 0
    cabecalho: dict[str, str] = {}
    movetext: list[str] = []
    aberta = False

    def processar() -> None:
        nonlocal partidas
        if not aberta:
            return
        partidas += 1
        if cabecalho.get("FEN") or not movetext:
            return
        tabuleiro = chess.Board()
        for san in _plies_da_partida(" ".join(movetext), profundidade):
            chave = (chave_da_posicao(tabuleiro.board_fen(), "w" if tabuleiro.turn else "b"), san)
            try:
                tabuleiro.push_san(san)
            except (ValueError, AssertionError):
                return
            _somar(acumulado, chave, cabecalho)

    with abrir_pgn_bytes(caminho) as fh:
        if inicio:
            fh.seek(inicio)
        while fh.tell() < fim:
            linha = fh.readline()
            if not linha:
                break
            if linha.startswith(_ABRE_CABECALHO):
                if linha.lstrip(_BOM).startswith(b"[Event "):
                    processar()
                    if len(acumulado) >= _LOTE_DE_RAMOS:
                        _descarregar(conexao, acumulado)
                    movetext, cabecalho, aberta = [], {}, True
                casado = _RE_HEADER.match(decodificar_linha(linha).rstrip())
                if casado is not None and casado.group(1) in _CAMPOS:
                    cabecalho[casado.group(1)] = casado.group(2)
                continue
            texto = linha.strip()
            if texto:
                movetext.append(decodificar_linha(texto))
        processar()
    _descarregar(conexao, acumulado)
    conexao.close()
    return partidas, destino


def _tarefas(bases: Sequence[Path], workers: int, profundidade: int, pasta: Path) -> list[tuple[Path, int, int, int, str]]:
    """Os pedaços de todas as bases, cada um com o arquivo parcial dele.

    A repartição é a de `games_db.chunk_bounds`, e ela já sabe que **uma base comprimida é um
    pedaço só** (S-531): não há como pular para o meio de um `.gz` sem descompactar o que vem
    antes.
    """
    tarefas: list[tuple[Path, int, int, int, str]] = []
    for base in bases:
        partes = 1 if eh_comprimida(base) else max(1, workers)
        for inicio, fim in chunk_bounds(base, partes):
            destino = pasta / f"parcial_{len(tarefas):03d}.sqlite"
            tarefas.append((base, inicio, fim, profundidade, str(destino)))
    return tarefas


def _fundir(destino: Path, parciais: Sequence[str], profundidade: int, marca: str, partidas: int) -> int:
    """Soma os parciais num arquivo só, e devolve quantos ramos ficaram.

    **Uma instrução de SQL, e não um laço em Python.** Os parciais somam dezenas de milhões de
    linhas; lê-las de volta para o Python custaria mais que a passada que as produziu. O `GROUP
    BY` ordena por `(chave, lance)`, que é exatamente a ordem da árvore de destino -- então a
    inserção anda para a frente numa folha por vez em vez de sondar a árvore por linha.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.unlink()
    conexao = sqlite3.connect(str(destino))
    try:
        conexao.execute("PRAGMA journal_mode = OFF")
        conexao.execute("PRAGMA synchronous = OFF")
        _preparar(conexao)
        uniao = []
        for numero, parcial in enumerate(parciais):
            conexao.execute(f"ATTACH DATABASE ? AS p{numero}", (parcial,))
            uniao.append(f"SELECT * FROM p{numero}.ramos")
        if uniao:
            with conexao:
                conexao.execute(
                    "INSERT INTO ramos SELECT chave, lance, sum(n), sum(brancas), sum(empates), "
                    "sum(pretas), sum(soma_elo), sum(com_elo), sum(soma_ano), sum(com_ano), "
                    # `min` de agregacao pula NULL sozinho, entao aqui basta um `coalesce`.
                    "coalesce(min(nullif(ano_min, 0)), 0), max(ano_max) FROM ("
                    + " UNION ALL ".join(uniao)
                    + ") GROUP BY chave, lance ORDER BY chave, lance"
                )
        for numero in range(len(parciais)):
            conexao.execute(f"DETACH DATABASE p{numero}")
        (ramos,) = conexao.execute("SELECT count(*) FROM ramos").fetchone()
        _gravar_meta(
            conexao,
            {
                "version": str(TREE_VERSION),
                "profundidade": str(profundidade),
                "partidas": str(partidas),
                "ramos": str(ramos),
                "database": marca,
            },
        )
        conexao.execute("VACUUM")
        return int(ramos)
    finally:
        conexao.close()


def construir(
    databases: Path | Sequence[Path],
    path: Path = DEFAULT_TREE_PATH,
    *,
    profundidade: int = PROFUNDIDADE,
    workers: int | None = None,
    progress: Progresso | None = None,
    cancel: threading.Event | None = None,
) -> Construcao:
    """Reproduz os `profundidade` primeiros meios-lances de cada partida e grava a árvore.

    **É uma passada e não um botão**, pela mesma razão que `estudo_partidas` escreve sobre
    `cvoff-games --all`: o custo é da **passada**, não da posição -- construir a árvore de uma
    abertura custa o mesmo que construir a de todas. Ver `COMO_CONSTRUIR`.

    **Refaz do zero, e não incrementa.** O índice por nome da S-532 é incremental porque uma
    linha dele é uma partida, e um torneio acrescentado são linhas novas ao lado das velhas.
    Aqui uma linha é uma **soma**: acrescentar um arquivo sem saber se ele já entrou somaria as
    mesmas partidas duas vezes, e o sintoma seria uma percentagem que continua plausível. O
    manifesto que tornaria isso seguro é o item seguinte, e não este.

    `cancel` descarta a rodada inteira: o arquivo fica sem a marca da base, e a consulta o recusa.
    """
    bases = [caminho for caminho in as_databases(databases) if existe_base(caminho)]
    if not bases:
        raise ValueError("Não há base de partidas para construir a árvore.")
    if profundidade < MINIMO_DE_PLIES:
        raise ValueError(f"profundidade precisa ser ao menos {MINIMO_DE_PLIES}, veio {profundidade}")

    quantos = workers if workers is not None and workers > 0 else max(1, (os.cpu_count() or 4) - 2)
    if os.environ.get(WORKER_ENV):
        # Já dentro de um processo de varredura (S-26): seguir com um só, em vez de multiplicar.
        logger.debug("Já dentro de um processo de varredura: a árvore sai num processo só.")
        quantos = 1
    comeco = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="cvoff-arvore-") as temporaria:
        tarefas = _tarefas(bases, quantos, profundidade, Path(temporaria))
        partidas, parciais, cancelada = 0, [], False
        if quantos == 1:
            for feitos, tarefa in enumerate(tarefas, start=1):
                if cancel is not None and cancel.is_set():
                    cancelada = True
                    break
                lidas, parcial = _pedaco(tarefa)
                partidas += lidas
                parciais.append(parcial)
                if progress is not None:
                    progress(feitos, len(tarefas), partidas)
        else:
            partidas, parciais, cancelada = _em_paralelo(tarefas, quantos, progress, cancel)
        if cancelada:
            logger.warning("A árvore de aberturas foi descartada: a passada não viu a base inteira.")
            return Construcao(partidas, 0, profundidade, time.perf_counter() - comeco, 0, True)
        ramos = _fundir(Path(path), parciais, profundidade, index_fingerprint(bases), partidas)

    tamanho = Path(path).stat().st_size if Path(path).exists() else 0
    return Construcao(partidas, ramos, profundidade, time.perf_counter() - comeco, tamanho)


def _em_paralelo(
    tarefas: Sequence[tuple[Path, int, int, int, str]],
    quantos: int,
    progress: Progresso | None,
    cancel: threading.Event | None,
) -> tuple[int, list[str], bool]:
    """Os pedaços em processos, com as duas guardas de `games_db.scan_by_positions`.

    **Um filho que morre descarta a passada**, e não a deixa pendurada: o pedaço que ele lia
    nunca volta pelo `imap_unordered`, e o laço que contasse conclusões esperaria para sempre --
    é o defeito que a S-171 reproduziu. E meia árvore não é meia resposta: uma percentagem
    calculada sobre a metade do arquivo que se leu parece um número certo.

    A espera é com prazo (`CANCEL_POLL_SECONDS`) e não um `for` sobre o iterador: é o que devolve
    o controle a tempo de honrar o cancelamento enquanto os pedaços rodam.
    """
    partidas = 0
    parciais: list[str] = []
    os.environ[WORKER_ENV] = "1"
    try:
        with _filho_sem_o_main_do_pai():
            pool = mp.Pool(min(quantos, len(tarefas)))
        with pool:
            nascidos = _pids_do_pool(pool)
            pendentes = pool.imap_unordered(_pedaco, tarefas)
            ultimo = 0.0
            while len(parciais) < len(tarefas):
                if _perdeu_um_filho(pool, nascidos):
                    pool.terminate()
                    logger.error(
                        "Um processo da árvore morreu em %d de %d pedaços; a passada foi descartada.",
                        len(parciais),
                        len(tarefas),
                    )
                    return partidas, [], True
                if cancel is not None and cancel.is_set():
                    pool.terminate()
                    return partidas, [], True
                try:
                    lidas, parcial = pendentes.next(timeout=CANCEL_POLL_SECONDS)
                except mp.TimeoutError:
                    continue
                partidas += lidas
                parciais.append(parcial)
                agora = time.perf_counter()
                if progress is not None and (
                    agora - ultimo >= _INTERVALO_DE_PROGRESSO or len(parciais) == len(tarefas)
                ):
                    ultimo = agora
                    progress(len(parciais), len(tarefas), partidas)
    finally:
        os.environ.pop(WORKER_ENV, None)
    return partidas, parciais, False


# --------------------------------------------------------------------------------- a consulta


def _abrir(bases: Sequence[Path], path: Path) -> tuple[sqlite3.Connection | None, str]:
    """A conexão só de leitura, conferidos versão e marca da base; ou `(None, motivo)`.

    O motivo já vem em pt-BR e com a instrução, como em `games_index._abrir_para_consulta`: a
    frase que a janela mostra é a mesma que o log escreve, e escrevê-la duas vezes é como as
    duas divergem.
    """
    refazer = f"Construa a árvore: {COMO_CONSTRUIR}"
    if not Path(path).exists():
        return None, f"A árvore de aberturas ainda não foi construída. {refazer}"
    try:
        conexao = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return None, f"Árvore de aberturas ilegível ({exc}). {refazer}"
    try:
        gravada = _meta(conexao, "version")
        if gravada != str(TREE_VERSION):
            return None, (
                f"A árvore está no formato {gravada or 'desconhecido'!r} e este programa lê o "
                f"{TREE_VERSION}. {refazer}"
            )
        marca = _meta(conexao, "database")
        if not marca:
            return None, f"A árvore está em obras: uma rodada não chegou ao fim. {refazer}"
        if bases and marca != index_fingerprint(bases):
            return None, (
                "A árvore foi construída para outra base: as contagens não valem para esta. "
                f"{refazer}"
            )
    except sqlite3.Error as exc:
        conexao.close()
        return None, f"Árvore de aberturas sem as tabelas esperadas ({exc}). {refazer}"
    return conexao, ""


def consultar(
    colocacao: str,
    vez: str,
    *,
    ply: int,
    path: Path = DEFAULT_TREE_PATH,
    bases: Sequence[Path] = (),
) -> Arvore:
    """Os lances jogados a partir daquela posição, um `Ramo` por lance. Milissegundos.

    **`ply` não é decoração: é o que separa "não há partida" de "não perguntei".** Uma posição
    além da profundidade gravada não tem linha no arquivo, e devolver `SEM_PARTIDA` ali diria
    *"nenhuma partida da base joga daqui"* sobre uma pergunta que ninguém indexou -- a forma de
    número enganoso que a S-135 custou caro e que `estudo_partidas` já corrigiu com quatro
    estados em vez de dois.

    `bases` vazio pula a conferência da marca -- é o caminho do teste, que constrói a árvore de
    um punhado de partidas e não tem pasta de bases para nomear.
    """
    conexao, motivo = _abrir(bases, path)
    if conexao is None:
        logger.debug("Árvore de aberturas indisponível: %s", motivo)
        return Arvore(SEM_ARVORE)
    try:
        profundidade = int(_meta(conexao, "profundidade") or PROFUNDIDADE)
        if ply >= profundidade:
            return Arvore(FUNDO_DEMAIS, (), profundidade, ply)
        linhas = conexao.execute(_LER, (chave_da_posicao(colocacao, vez),)).fetchall()
    except (sqlite3.Error, ValueError) as exc:
        logger.warning("A árvore de aberturas não respondeu (%s).", exc)
        return Arvore(SEM_ARVORE)
    finally:
        conexao.close()

    ramos = tuple(
        Ramo(
            lance=str(linha[0]),
            partidas=int(linha[1]),
            brancas=int(linha[2]),
            empates=int(linha[3]),
            pretas=int(linha[4]),
            soma_elo=int(linha[5]),
            com_elo=int(linha[6]),
            soma_ano=int(linha[7]),
            com_ano=int(linha[8]),
            ano_min=int(linha[9]),
            ano_max=int(linha[10]),
        )
        for linha in linhas
    )
    if not ramos:
        return Arvore(SEM_PARTIDA, (), profundidade, ply)
    return Arvore(ACHOU, ramos, profundidade, ply)


def resumo_do_arquivo(path: Path = DEFAULT_TREE_PATH) -> dict[str, Any]:
    """O que o arquivo declara de si -- versão, profundidade, partidas, ramos --, sem abri-lo para
    escrita. Vazio quando não há arquivo ou ele não é uma árvore.

    Existe pela razão de `games_cache.stored_summary`: quem precisa **dizer** o que há antes de
    perguntar não pode descobri-lo pela porta que recusa.
    """
    caminho = Path(path)
    if not caminho.exists():
        return {}
    try:
        conexao = sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    try:
        return {
            "version": _meta(conexao, "version"),
            "profundidade": _meta(conexao, "profundidade"),
            "partidas": _meta(conexao, "partidas"),
            "ramos": _meta(conexao, "ramos"),
            "database": _meta(conexao, "database"),
            "bytes": caminho.stat().st_size,
        }
    except sqlite3.Error:
        return {}
    finally:
        conexao.close()
