"""Onde cada partida mora no arquivo, para perguntar por nome em milissegundos (S-87).

**A condição que este módulo cumpre estava escrita no `games_db.py` desde 2026-08-13:**

> *"Um índice por nome custaria ~1 GB no disco (…) para poupar 150 s por livro -- e livro se
> varre uma vez. **O dia em que a busca virar por diagrama e não por livro, o índice passa a
> valer.**"*

É esse dia. A S-86 pôs uma pessoa parada num diagrama, olhando uma lista e querendo perguntar
outra coisa à base -- e ela não pode pagar 150 s por pergunta.

**O que ele dá, além de velocidade.** Medido em 2026-08-15, dos 22 diagramas ambíguos em que a
legenda não acha candidata nenhuma, **9 têm a lista truncada em 32** e a partida certa pode ter
ficado de fora. Perguntar por nome não tem lista para truncar. E ele alcança os **1.922
diagramas (53,9%) que a posição não casou**: a base pode ter a partida sem ter aquela posição
exata, quando a leitura do diagrama saiu com uma casa errada.

**O custo, medido e não estimado.** Sobre a `LumbrasGigaBase_OTB_Complete` (8,6 GB, 10.355.488
partidas), as duas versões na mesma sessão de 2026-09-04:

| | tempo | disco |
|---|---|---|
| v4 -- `(pair, file, offset)` | 8,9 min | 235 MB |
| **v5** -- treze colunas, dois dicionários, seis árvores | **10,2 min** | **1.764 MB** |

**+14% de tempo e 7,5× de disco**, e é o que faz *"as partidas de Carlsen em 2019 com Elo acima
de 2700 na Najdorf"* custar **52 ms** em vez da passada de dez minutos. Proporcional ao que a
pasta tem: com duas gigabases, o dobro. Fora do git, ao lado da base, como todo material derivado
dela.

**Os offsets são do arquivo, então o arquivo é parte da chave.** Trocada a base, cada offset
aponta para o meio de outra partida -- e a leitura devolveria movetext cortado com cara de
partida. O fingerprint fica gravado no próprio índice e é conferido antes de qualquer consulta.

**E "o arquivo" virou plural na S-93**, quando a base deixou de ser um `.pgn` e passou a ser a
pasta. Cada partida guarda *de qual* arquivo é o seu offset, na coluna `file`, e a tabela
`files` diz que arquivo é esse. O byte 4.000.000 existe nas duas bases e começa partidas
diferentes; sem a coluna, o offset da segunda seria lido na primeira, e o que se perderia é a
**resposta**: a conferência de nomes descartaria a partida lida, e a base recém-acrescentada
responderia zero -- em silêncio, que é como a S-93 começou.

**E o índice deixou de ser refeito do zero a cada arquivo novo (S-532).** A tabela `files` é
um **manifesto**: por base, tamanho, `mtime` e a marca dos primeiros e dos últimos 64 KB. Um
arquivo cuja marca não mudou não é relido; um que saiu da pasta sai do índice; um que só
cresceu -- o PGN em que alguém anexa as partidas da semana -- é lido a partir do byte em que
parou, se a cauda antiga ainda estiver lá. Uma pasta de 18 GB com um torneio novo custa o
torneio, e não os 18 GB.

**E o índice passou a responder a perguntas que não são "quem contra quem" (S-533/S-534).**
Até a versão 4 a linha era `(par, arquivo, offset)`: bastava para achar a partida de uma legenda,
e não dizia nada sobre ela. A sala de estudo quer *as partidas de Carlsen em 2019 com Elo acima
de 2700 na Najdorf*, e a legenda sob o tabuleiro quer o código ECO. A linha ganhou **quem, onde,
quando, com que Elo, com que resultado e em que abertura** -- e o nome do jogador e o do evento
não vão na linha: vão em dois dicionários (`players`, `events`) e a linha guarda o número. Dez
milhões de linhas com `Carlsen, Magnus` escrito em cada uma seriam 200 MB de repetição; com o
número são 30 MB, e a busca por sobrenome vira uma consulta ao dicionário (uma tabela de
centenas de milhares de linhas, não de dez milhões) seguida de uma sonda no índice.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .eco import classificar_lances, codigo_do_header, lances_do_movetext
from .games_db import (
    _ABRE_CABECALHO,
    _BOM,
    _KEPT_HEADERS,
    _RE_HEADER,
    GameRecord,
    PlayerPair,
    abrir_pgn_bytes,
    arquivo_fisico,
    as_databases,
    decodificar_linha,
    eh_comprimida,
    existe_base,
    nome_da_base,
    occupancy,
    surname,
    tamanho_da_base,
)
from .pdf_text import fold
from .ui.busca_de_partidas import Filtro

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_INDEX_PATH",
    "INDEX_VERSION",
    "INTERVALO_DE_PROGRESSO",
    "PAGINA",
    "TETO_DE_CONTAGEM",
    "TETO_DE_REPLAY",
    "Achado",
    "Busca",
    "Indexacao",
    "IndiceIndisponivel",
    "Progresso",
    "build_index",
    "buscar",
    "index_fingerprint",
    "lookup_pair",
    "pair_hash",
    "partida_em",
    "positions_of",
]

DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "games_index.sqlite"

INDEX_VERSION = 6
"""O formato do arquivo. **6** desde a segunda rodada da S-533, que acrescentou duas árvores.

A **2** é da S-93, quando a partida passou a guardar em que base mora. A versão declarada
existe porque o fingerprint não bastava para notar a diferença: com uma base só, a marca da
versão 1 (`nome:tamanho`) é *idêntica* à da 2, e um índice antigo passaria pela conferência
para depois quebrar na primeira consulta -- `SELECT ... file` numa tabela sem essa coluna. Uma
versão declarada transforma isso num aviso com instrução, que é o que o resto do módulo faz
com todo desencontro.

**O que mudou na 3.** Até a 2, `games` tinha rowid implícito e havia um `CREATE INDEX
games_pair ON games (pair)` ao lado. Cada linha existia em **duas árvores**: a coluna de busca
no índice, e `offset`/`file` na tabela, que só existia para ser sondada. Toda consulta pagava
uma sonda aleatória a mais, e o disco pagava a linha duas vezes.

Na 3 a tabela é `WITHOUT ROWID` com `PRIMARY KEY (pair, file, offset)`: a chave de busca **é**
a árvore, e `offset`/`file` viajam na mesma folha. Uma árvore, uma sonda.

**Medido** num índice sintético de 1 milhão de partidas, os dois esquemas sobre as mesmas
linhas:

| | tamanho | 200 consultas |
|---|---|---|
| v2 — rowid + `CREATE INDEX` | 38,9 MB | 14,6 ms |
| v3 — `WITHOUT ROWID` | **21,8 MB** | 13,7 ms |

**-44,0%**, e a consulta não fica mais lenta.

**O que muda na 4.** `files` ganhou `size`, `mtime`, `head`, `tail` e `games` -- o manifesto
que decide o que reler --, e o índice passou a ser **editado no lugar**, um arquivo por
transação, em vez de nascer inteiro num `.parcial` e ser renomeado no fim. Um índice v3 é
recusado com a instrução de refazer, como sempre; refazer custa a mesma passada de antes, uma
vez, e a partir daí só o que mudar.

**O que muda na 5, e por que ela desfaz a 3.** A linha ganhou `white`, `black`, `event` (números
dos dicionários `players` e `events`), `date`, `year`, `welo`, `belo`, `elo` (o menor dos dois),
`result` e `eco`. Com **seis** caminhos de busca -- par, brancas, pretas, evento, ECO e
ano+Elo -- a chave composta da v3 seria copiada inteira dentro de cada índice secundário (14
bytes por linha em cada um), e o rowid de 4 bytes sai mais barato: a tabela voltou a ter
`id INTEGER PRIMARY KEY`, com `UNIQUE (file, offset)` fazendo o papel de chave única que a v3
tinha de graça. O argumento da v3 valia para uma árvore só; com seis, inverte.

**A migração é refazer.** Um índice v4 não tem nomes, datas nem códigos gravados -- só o par em
hash --, e uma "segunda passada" que os buscasse pelos offsets leria os mesmos bytes que a
passada inteira, na mesma ordem, com um `seek` por partida a mais. Não há o que aproveitar: um
v4 é apagado e refeito, como sempre foi com formato anterior, e `lookup_pair`/`buscar` avisam
com a instrução até isso acontecer.

`INSERT OR IGNORE` porque a chave é única: a mesma partida indexada duas vezes era uma linha
duplicada e silenciosa antes, e agora seria um erro em cima de uma varredura de horas.

**O que muda na 6, e por que ela é a primeira que não manda refazer.** Nenhuma coluna: duas
árvores. `games_elo (elo)` -- porque "Elo mínimo 3500" sem mais nada era uma varredura de dez
milhões de linhas para responder *nenhuma*, 1,08 s medido -- e `games_ordem (year, date)`, que é
a **ordem** da resposta e não um filtro: sem ela, todo filtro que casa milhões (um ano, uma faixa
de ECO larga, um pedaço curto de nome de evento) pagava a ordenação de milhões de linhas para
devolver cem, de 1,9 s a 5,4 s medidos. As tabelas são idênticas às da 5, e por isso uma v5 é
**completada** em vez de refeita: ver `_VERSOES_QUE_SO_GANHAM_ARVORE`."""

MAX_GAMES_PER_LOOKUP = 40
"""Teto de partidas lidas por consulta -- o mesmo do `MAX_GAMES_PER_PAIR`, e pela mesma razão:
Kasparov x Karpov são 170 partidas, e reproduzir todas para achar uma posição custaria tempo
sem melhorar a resposta."""

BYTES_DA_MARCA = 64 * 1024
"""Quantos bytes de cada ponta entram na marca de um arquivo do manifesto.

Tamanho igual não diz que o conteúdo é o mesmo, e `mtime` igual não diz nada num sync de nuvem
(S-113 registra o antivírus que reescreve o carimbo sem tocar num byte). Os 64 KB de cada
ponta custam menos de um milissegundo por arquivo e pegam o caso comum: um `.pgn` regravado
começa diferente ou termina diferente. O meio do arquivo trocado com as pontas iguais e o mesmo
tamanho não é um caso que aconteça sem intenção, e quem o fizer tem `--build-index` para
refazer do zero."""

INTERVALO_DE_PROGRESSO = 0.1
"""No máximo ~10 avisos de progresso por segundo. Mais que isso é fila de eventos na janela, e
não informação: ninguém lê onze barras por segundo."""

PAGINA = 100
"""Quantas linhas uma página da busca traz por padrão. Cem cabem numa tela com rolagem curta, e
a página seguinte custa a mesma consulta com outro `OFFSET`."""

TETO_DE_CONTAGEM = 100_000
"""Até onde a busca conta. Contar *todas* as partidas de `1.e4` numa base de dez milhões custaria
segundos para dizer um número que ninguém vai ler até o fim; acima do teto a frase diz "mais de
100.000", que é a informação inteira."""

TETO_DE_REPLAY = 2_000
"""Quantas candidatas a busca reproduz quando o filtro pede a posição corrente.

A posição não está no índice -- guardá-la seria a varredura de uma hora da S-92 --, então ela é
conferida **lendo** cada candidata que os outros filtros deixaram passar. Dois mil replays com o
porteiro da S-85 custam ~1 s; quem quer mais estreita o filtro, e a resposta diz quantas foram
examinadas em vez de fingir que foram todas."""

_LINHAS_POR_CONFERENCIA = 16_384
"""De quantas em quantas linhas o relógio e a bandeira de cancelamento são conferidos.

Dezesseis mil linhas são ~1 MB de PGN, uns 10 ms a 100 MB/s; o cancelamento é honrado bem
dentro do segundo que a S-532 exige, e o custo de olhar o relógio some no ruído."""

_LINHAS_DE_MOVETEXT_LIDAS = 2
"""Quantas linhas do movetext a classificação ECO sem header lê. Uma linha de 80 colunas traz
uns 16 meios-lances; duas passam dos 24 que `eco.LANCES_EXAMINADOS` percorre."""

INDICE_DA_ORDEM = "games_ordem"
"""A árvore `(year, date, id, result)`, que é a **ordem em que a busca responde** (S-533, r2).

Ela existe porque `ORDER BY … LIMIT 100` sobre um filtro que não estreita era a conta inteira: o
crítico mediu `ano 2019` sozinho em 2,8 s, a faixa `A00–E99` em 5,4 s e o evento `ch-` em 5,1 s
nesta gigabase, e nos três casos a contagem já parava no teto em dezenas de milissegundos --
quem custava eram os milhões de linhas ordenadas para devolver cem. Com a árvore da ordem o
sqlite anda por ela de trás para a frente, confere o filtro linha a linha e para na centésima que
passa: o custo deixa de ser *quantas casam* e passa a ser *quantas se olha até achar cem*. Ver
`buscar`, que escolhe entre os dois planos pela contagem.

**As duas colunas do fim não são ordem, e cada uma resolve uma coisa.** O `id` é o rowid escrito
de novo, e é o que faz o prefixo da árvore ser `(year, date, id)` -- exatamente o `ORDER BY`, sem
o `USE TEMP B-TREE FOR RIGHT PART OF ORDER BY` que aparece sem ele. O `result` é o único filtro
que **não** tem árvore própria (a posição também não, mas ela é lida do `.pgn`), e sem ele na
folha a contagem de *"1990–2020, vitória das brancas"* era uma sonda na tabela por linha: 1,25 s
para contar cem mil, contra **12 ms** com a folha cobrindo. Medido em 2026-09-04."""

_CAMPOS_DO_INDICE = frozenset({"Event", "Date", "White", "Black", "Result", "WhiteElo", "BlackElo", "ECO", "FEN"})
"""Os headers que a passada de índice guarda de cada partida. `FEN` só para saber que a partida
**não** começa na posição inicial -- e aí não há abertura a classificar."""

_INDICES_DE_BUSCA: tuple[tuple[str, str], ...] = (
    ("games_pair", "games (pair)"),
    ("games_white", "games (white)"),
    ("games_black", "games (black)"),
    ("games_event", "games (event)"),
    ("games_eco", "games (eco)"),
    ("games_year", "games (year, elo)"),
    ("games_elo", "games (elo)"),
    (INDICE_DA_ORDEM, "games (year, date, id, result)"),
)
"""Os oito caminhos de busca. São **derrubados antes de uma rodada grande e refeitos no fim**:
inserir dez milhões de linhas com seis árvores abertas é dez milhões de sondas aleatórias em cada
uma, e criá-las de uma vez sobre a tabela pronta é uma ordenação por árvore -- segundos, não
minutos. Numa rodada pequena (o torneio anexado) eles ficam, porque refazê-los custaria mais que
as linhas novas. Ver `_refaz_os_indices`."""

_TAMANHO_DO_LOTE = 100_000
"""Linhas acumuladas antes de cada `executemany`. Eram 200 mil com três colunas; com treze, o
mesmo pico de memória cabe na metade."""

Progresso = Callable[[Path, int, int, int], None]
"""`(base, bytes_lidos, bytes_totais, partidas)`. Os bytes são os do disco -- comprimidos, se a
base for --, porque são os únicos comparáveis ao tamanho do arquivo; as partidas são as lidas
**nesta rodada**, somadas sobre os arquivos."""


class IndiceIndisponivel(RuntimeError):
    """A busca não pode responder: não há índice, ele é de outro formato, ou está em obras.

    É exceção e não lista vazia porque quem chama é uma janela com uma tabela: "nenhuma partida"
    e "o índice ainda não foi feito" são frases diferentes, e devolver `[]` nos dois casos foi o
    que a S-93 mediu como silêncio. `lookup_pair` continua devolvendo vazio, porque quem o chama
    tem um caminho alternativo (a lista do cache) e um erro ali tiraria os dois.
    """


@dataclass(frozen=True)
class Indexacao:
    """O que uma rodada de `build_index` fez -- e o que ela **não** precisou fazer.

    `relidas` e `arquivos_pulados` são o item da S-532 em forma de número: a segunda rodada
    sobre a mesma pasta tem de sair com `relidas == 0`, e é isso que o teste afirma.
    """

    partidas: int = 0
    """Quantas partidas o índice conhece ao fim da rodada, somando todos os arquivos."""

    relidas: int = 0
    """Quantas foram lidas do disco nesta rodada."""

    arquivos_relidos: int = 0
    arquivos_pulados: int = 0
    arquivos_removidos: int = 0

    cancelado: bool = False
    """A rodada parou a pedido. O que já estava gravado ficou; a marca da base **não** foi
    escrita, e a consulta recusa o índice até uma rodada terminar."""


@dataclass(frozen=True)
class Achado:
    """Uma linha da busca (S-533): o que a tabela mostra, e onde a partida mora para abri-la."""

    brancas: str
    elo_brancas: int
    pretas: str
    elo_pretas: int
    resultado: str
    evento: str
    data: str
    eco: str
    caminho: Path
    """A base em que a partida está -- o `Path` de `as_databases`, que pode ser um membro de
    `.zip`."""
    offset: int


@dataclass(frozen=True)
class Busca:
    """O que `buscar` devolveu: a página, quantas há ao todo, e -- com posição -- quantas leu."""

    achados: tuple[Achado, ...] = ()
    total: int = 0
    """Quantas partidas os filtros do índice casam, até `TETO_DE_CONTAGEM`."""

    total_e_teto: bool = False
    """`total` parou no teto: há mais do que ele diz."""

    offset: int = 0
    examinadas: int = 0
    """Com posição no filtro, quantas candidatas foram lidas e reproduzidas nesta página. Sem
    posição, zero: ninguém foi lido."""

    @property
    def proximo_offset(self) -> int:
        """Onde a página seguinte começa: depois do que foi examinado, ou do que foi devolvido."""
        return self.offset + (self.examinadas if self.examinadas else len(self.achados))

    @property
    def ha_mais(self) -> bool:
        return self.proximo_offset < self.total or self.total_e_teto


def pair_hash(pair: PlayerPair) -> int:
    """Um inteiro de 63 bits, **estável entre execuções**, para o par de sobrenomes.

    Não é o `hash()` do Python: ele é aleatorizado por processo desde a 3.3, e um índice
    gravado hoje não seria consultável amanhã -- em silêncio, devolvendo zero resultados.

    Colisão é possível e **não é problema**, porque quem consulta lê a partida e confere os
    nomes: uma colisão custa uma leitura descartada, não uma resposta errada.
    """
    digest = hashlib.blake2b("|".join(pair).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") & 0x7FFFFFFFFFFFFFFF


def index_fingerprint(databases: Path | Sequence[Path]) -> str:
    """Nome e tamanho de **cada** base, na ordem em que entraram. Offsets são do arquivo.

    Acrescentar um `.pgn` à pasta muda esta marca, e é assim que se descobre que o índice
    ficou incompleto: ele não sabe as partidas do arquivo novo, e responder sem elas seria
    dizer "a base não tem" sobre um arquivo que ninguém indexou (S-93).

    O nome é o de `nome_da_base` -- `base.zip/membro.pgn` para um membro de `.zip` --, e o
    tamanho é o do disco, comprimido se for o caso (S-531).
    """
    return "|".join(f"{nome_da_base(caminho)}:{tamanho_da_base(caminho)}" for caminho in as_databases(databases))


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path))


def _versao_gravada(path: Path) -> str | None:
    """A versão declarada num índice existente, ou `None` se não dá para ler."""
    try:
        conexao = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        linha = conexao.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
    except sqlite3.Error:
        return None
    finally:
        conexao.close()
    return None if linha is None else str(linha[0])


_VERSOES_QUE_SO_GANHAM_ARVORE = frozenset({"5"})
"""As versões cujas **tabelas** são iguais às de hoje: só faltam árvores de busca.

Refazer um índice destes seria reler 8,6 GB de PGN para gravar exatamente as mesmas linhas. O que
a v6 acrescentou à v5 foram duas árvores (`games_elo` e `games_ordem`), e o fim de toda rodada já
as cria com `CREATE INDEX IF NOT EXISTS`: a rodada sobre uma pasta que não mudou pula todos os
arquivos, cria o que falta e grava a versão nova. A regra "migração é refazer" das versões 3, 4 e
5 valia porque **faltava dado gravado**; aqui não falta nenhum, e cobrar a passada inteira seria
zelo cobrado do usuário."""


def _abrir_para_escrita(path: Path) -> sqlite3.Connection:
    """O índice pronto para receber esta rodada: o existente, se for desta versão; senão, um novo.

    Um índice de outra versão é apagado e refeito -- é o que `--build-index` sempre significou
    para ele --, e o `.parcial` de uma versão anterior interrompida vai junto. A exceção é a
    versão que só perdeu árvores: ver `_VERSOES_QUE_SO_GANHAM_ARVORE`.
    """
    path.with_suffix(path.suffix + ".parcial").unlink(missing_ok=True)
    gravada = _versao_gravada(path) if path.exists() else None
    if path.exists() and gravada != str(INDEX_VERSION):
        if gravada in _VERSOES_QUE_SO_GANHAM_ARVORE:
            logger.info("O índice em %s é da versão %s: as árvores que faltam são criadas no fim da rodada.", path, gravada)
        else:
            logger.info("O índice em %s é de outro formato e será refeito do zero.", path)
            path.unlink()
    conexao = _connect(path)
    # Com jornal, porque o arquivo agora e editado no lugar: sem ele, um processo morto no meio
    # de um arquivo deixaria o SQLite corrompido, e nao so incompleto. `DELETE` e nao
    # `TRUNCATE`: o segundo deixa um `.sqlite-journal` vazio ao lado do indice para sempre, e
    # `data/` tem guarda contra artefato que ninguem declarou. Sao poucas transacoes -- uma por
    # arquivo --, entao criar e apagar o jornal a cada uma nao custa nada. `synchronous=OFF`
    # porque uma queda de energia custa refazer a rodada, e o disco e o gargalo da rodada.
    conexao.execute("PRAGMA journal_mode=DELETE")
    conexao.execute("PRAGMA synchronous=OFF")
    # 256 MB de cache: e o que deixa as seis arvores de busca em memoria numa rodada pequena que
    # insere com elas abertas (o torneio anexado a gigabase). Numa rodada grande elas sao
    # derrubadas antes e refeitas no fim, e o cache so ajuda a tabela.
    conexao.execute("PRAGMA cache_size=-262144")
    # `id INTEGER PRIMARY KEY` e nao mais `WITHOUT ROWID` (v5): ver `INDEX_VERSION`.
    conexao.execute(
        "CREATE TABLE IF NOT EXISTS games ("
        "id INTEGER PRIMARY KEY, "
        "pair INTEGER NOT NULL, file INTEGER NOT NULL, offset INTEGER NOT NULL, "
        "white INTEGER NOT NULL, black INTEGER NOT NULL, event INTEGER NOT NULL, "
        "date TEXT NOT NULL, year INTEGER NOT NULL, "
        "welo INTEGER NOT NULL, belo INTEGER NOT NULL, elo INTEGER NOT NULL, "
        "result TEXT NOT NULL, eco TEXT NOT NULL, "
        "UNIQUE (file, offset))"
    )
    conexao.execute("CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, surname TEXT NOT NULL)")
    conexao.execute("CREATE INDEX IF NOT EXISTS players_surname ON players (surname)")
    conexao.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, folded TEXT NOT NULL)")
    # O zero e "sem nome"/"sem evento": a linha da partida sempre aponta para alguem, e a
    # consulta junta as tres tabelas sem `LEFT JOIN`.
    conexao.execute("INSERT OR IGNORE INTO players VALUES (0, '', '')")
    conexao.execute("INSERT OR IGNORE INTO events VALUES (0, '', '')")
    conexao.execute(
        "CREATE TABLE IF NOT EXISTS files ("
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, size INTEGER NOT NULL, mtime REAL NOT NULL, "
        "head TEXT NOT NULL, tail TEXT NOT NULL, games INTEGER NOT NULL)"
    )
    conexao.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conexao.execute("INSERT OR REPLACE INTO meta VALUES ('version', ?)", (str(INDEX_VERSION),))
    conexao.commit()
    return conexao


def _marca(fisico: Path, inicio: int, fim: int) -> str:
    """O `blake2b` dos bytes `[inicio, fim)` do arquivo. Vazio se não deu para ler."""
    if fim <= inicio:
        return hashlib.blake2b(b"", digest_size=16).hexdigest()
    try:
        with fisico.open("rb") as fh:
            fh.seek(inicio)
            dados = fh.read(fim - inicio)
    except OSError:
        return ""
    return hashlib.blake2b(dados, digest_size=16).hexdigest()


def _marcas(fisico: Path, tamanho: int) -> tuple[str, str]:
    """A cabeça e a cauda do arquivo físico -- os primeiros e os últimos `BYTES_DA_MARCA`."""
    return _marca(fisico, 0, min(tamanho, BYTES_DA_MARCA)), _marca(fisico, max(0, tamanho - BYTES_DA_MARCA), tamanho)


@dataclass(frozen=True)
class _Registro:
    """Uma linha do manifesto."""

    id: int
    name: str
    size: int
    mtime: float
    head: str
    tail: str
    games: int


def _manifesto(conexao: sqlite3.Connection) -> dict[str, _Registro]:
    return {
        str(linha[1]): _Registro(int(linha[0]), str(linha[1]), int(linha[2]), float(linha[3]), str(linha[4]), str(linha[5]), int(linha[6]))
        for linha in conexao.execute("SELECT id, name, size, mtime, head, tail, games FROM files")
    }


@dataclass(frozen=True)
class _Plano:
    """O que a rodada vai fazer com uma base, decidido pelo manifesto antes de ler um byte."""

    base: Path
    nome: str
    mtime: float
    tamanho: int
    cabeca: str
    cauda: str
    antigo: _Registro | None
    inicio: int
    """De que byte ler: zero para inteiro; o tamanho antigo para a cauda anexada."""

    pular: bool
    """Nada mudou: não é relido."""


def _planejar(base: Path, antigo: _Registro | None) -> _Plano | None:
    """Pulado, cauda ou inteiro -- a tabela do docstring de `build_index`. `None` se não dá para ler."""
    nome = nome_da_base(base)
    fisico = arquivo_fisico(base)
    try:
        mtime = fisico.stat().st_mtime
        tamanho_fisico = fisico.stat().st_size
    except OSError:
        return None
    tamanho = tamanho_da_base(base)
    cabeca, cauda = _marcas(fisico, tamanho_fisico)
    if antigo is not None and (antigo.size, antigo.head, antigo.tail) == (tamanho, cabeca, cauda):
        return _Plano(base, nome, mtime, tamanho, cabeca, cauda, antigo, tamanho, True)
    inicio = 0
    if (
        antigo is not None
        and not eh_comprimida(base)
        and tamanho > antigo.size
        and _marca(fisico, 0, min(antigo.size, BYTES_DA_MARCA)) == antigo.head
        and _marca(fisico, max(0, antigo.size - BYTES_DA_MARCA), antigo.size) == antigo.tail
    ):
        # So a cauda: o que estava la continua la, byte a byte, e os offsets antigos continuam
        # valendo. As duas marcas sao refeitas sobre os MESMOS trechos que o manifesto mediu --
        # num arquivo menor que 64 KB a cabeca era o arquivo inteiro, e compara-la com a cabeca
        # de agora, mais comprida, diria "mudou" sobre um arquivo que so cresceu.
        inicio = antigo.size
    return _Plano(base, nome, mtime, tamanho, cabeca, cauda, antigo, inicio, False)


def _refaz_os_indices(planos: Sequence[_Plano]) -> bool:
    """Se esta rodada derruba as árvores de busca antes e as refaz depois.

    A régua é bytes: o que vai ser lido contra o que fica como está. Uma rodada que lê mais do
    que mantém (o índice do zero; a segunda gigabase) refaz as árvores no fim, que é uma
    ordenação por árvore; uma que lê menos (o torneio anexado) insere com elas abertas, porque
    refazer seis árvores de dez milhões de linhas por causa de trezentas partidas custaria mais
    que as trezentas partidas.
    """
    a_ler = sum(plano.tamanho - plano.inicio for plano in planos if not plano.pular)
    ficam = sum(plano.inicio for plano in planos)
    return a_ler > ficam


class _Dicionario:
    """`nome -> número` de uma das duas tabelas de nomes, com o que já está gravado carregado.

    Carregar o dicionário inteiro na memória é o que faz a passada custar um `dict.get` por
    nome e não uma consulta por partida: dez milhões de `SELECT id FROM players WHERE name = ?`
    seriam minutos. Numa gigabase são ~600 mil nomes, uns 60 MB -- o preço, medido, de gravar o
    nome uma vez em vez de dez milhões.
    """

    def __init__(self, conexao: sqlite3.Connection, tabela: str, derivada: Callable[[str], str]) -> None:
        self._tabela = tabela
        self._derivada = derivada
        self._ids: dict[str, int] = {str(nome): int(numero) for nome, numero in conexao.execute(f"SELECT name, id FROM {tabela}")}
        self._proximo = max(self._ids.values(), default=0) + 1
        self._novos: list[tuple[int, str, str]] = []

    def numero(self, nome: str) -> int:
        numero = self._ids.get(nome)
        if numero is None:
            numero = self._proximo
            self._proximo += 1
            self._ids[nome] = numero
            self._novos.append((numero, nome, self._derivada(nome)))
        return numero

    def gravar(self, conexao: sqlite3.Connection) -> None:
        """Insere os nomes novos desde a última gravação. Nada aqui faz `commit`."""
        if self._novos:
            conexao.executemany(f"INSERT OR IGNORE INTO {self._tabela} VALUES (?, ?, ?)", self._novos)
            self._novos.clear()


def build_index(
    databases: Path | Sequence[Path],
    path: Path = DEFAULT_INDEX_PATH,
    *,
    progress: Progresso | None = None,
    cancel: threading.Event | None = None,
) -> Indexacao:
    """Põe o índice em dia com as bases: relê só o que mudou, e diz quanto foi (S-87/S-532).

    **Uma passada de cabeçalhos, sem reproduzir lance nenhum** -- é por isso que ela custa
    minutos e não a meia hora da varredura por posição. O movetext é pulado como texto: aqui ele
    não interessa, e quem for consultar lê a partida inteira na hora. A única exceção (S-534) são
    as duas primeiras linhas dele numa partida **sem** header `[ECO]` e sem `[FEN]`: elas viram
    lances por expressão regular e entram em `eco.classificar_lances`, que é uma árvore de
    prefixos sem tabuleiro -- microssegundos, e não o milissegundo do replay.

    **O arquivo faz parte da chave desde a S-93**, e o número dele vem do manifesto (S-532):
    um arquivo que já estava no índice mantém o `id`, um novo recebe o próximo livre. A ordem da
    lista deixou de importar para o offset -- o que casa é o nome.

    **O que decide reler**, arquivo a arquivo, com o manifesto na mão:

    | o manifesto diz | o que acontece |
    |---|---|
    | mesmo tamanho, mesma cabeça, mesma cauda | **pulado**; só o `mtime` é atualizado se mudou |
    | cresceu, mesma cabeça, e a cauda antiga ainda está no mesmo lugar | lido **a partir do tamanho antigo** -- é o PGN em que se anexa |
    | qualquer outra diferença, ou base comprimida que mudou | as partidas dele saem e ele é relido inteiro |
    | não está mais na lista | as partidas dele saem do índice |

    **Uma transação por lote, e não mais por arquivo** (S-533, r2). Era por arquivo, e a gigabase
    **é** um arquivo: cancelar no nono minuto desfazia os nove, e a rodada seguinte relia 8,6 GB
    do começo. A cada `_TAMANHO_DO_LOTE` partidas gravadas o manifesto anota até que byte o
    arquivo está lido -- na mesma forma que ele usa para o torneio anexado da S-532 --, e a
    rodada seguinte continua **de lá**. O que se perde ao cancelar passa a ser o lote em curso, e
    não o arquivo. Base comprimida fica de fora: ali o byte lido não é o byte do disco.

    E enquanto a rodada não termina a `meta.database` fica **apagada**: é ela que `lookup_pair`
    confere, então um índice pela metade recusa a consulta em vez de responder menos do que a
    base tem (S-25, agora sem `.parcial`).

    `progress` recebe `(base, bytes_lidos, bytes_totais, partidas)` no máximo ~10 vezes por
    segundo, e uma vez por arquivo pulado, com os bytes cheios -- para a barra do conjunto andar
    também pelo que não precisou ser lido. `cancel` é conferido a cada 16 mil linhas.
    """
    bases = as_databases(databases)
    conexao = _abrir_para_escrita(path)
    arquivos_relidos = pulados = removidos = 0
    lidas_na_rodada = 0
    cancelado = False
    try:
        manifesto = _manifesto(conexao)
        atuais = {nome_da_base(base) for base in bases}

        # A marca da base sai ANTES de qualquer mudanca: a partir daqui o indice esta em obras, e
        # a consulta tem de recusa-lo ate a rodada terminar.
        conexao.execute("DELETE FROM meta WHERE key = 'database'")
        conexao.commit()

        for nome, registro in list(manifesto.items()):
            if nome in atuais:
                continue
            conexao.execute("DELETE FROM games WHERE file = ?", (registro.id,))
            conexao.execute("DELETE FROM files WHERE id = ?", (registro.id,))
            conexao.commit()
            del manifesto[nome]
            removidos += 1
            logger.info("Índice por nome: %s saiu da pasta e as partidas dele saíram do índice.", nome)

        planos: list[_Plano] = []
        for base in bases:
            plano = _planejar(base, manifesto.get(nome_da_base(base)))
            if plano is None:
                logger.warning("Índice por nome: %s não pôde ser lido e ficou de fora.", nome_da_base(base))
                continue
            planos.append(plano)

        if _refaz_os_indices(planos):
            for indice, _colunas in _INDICES_DE_BUSCA:
                conexao.execute(f"DROP INDEX IF EXISTS {indice}")
            conexao.commit()

        jogadores = _Dicionario(conexao, "players", surname)
        eventos = _Dicionario(conexao, "events", fold)
        proximo_id = max((registro.id for registro in manifesto.values()), default=-1) + 1
        for plano in planos:
            if cancel is not None and cancel.is_set():
                cancelado = True
                break
            base, nome, antigo, tamanho = plano.base, plano.nome, plano.antigo, plano.tamanho

            if plano.pular and antigo is not None:
                if antigo.mtime != plano.mtime:
                    conexao.execute("UPDATE files SET mtime = ? WHERE id = ?", (plano.mtime, antigo.id))
                    conexao.commit()
                pulados += 1
                if progress is not None:
                    progress(base, tamanho, tamanho, lidas_na_rodada)
                continue

            partidas_antes = 0
            if antigo is None:
                identificador, proximo_id = proximo_id, proximo_id + 1
            else:
                identificador = antigo.id
                if plano.inicio:
                    partidas_antes = antigo.games
                    logger.info("Índice por nome: %s cresceu; lendo a partir do byte %d.", nome, plano.inicio)
                else:
                    conexao.execute("DELETE FROM games WHERE file = ?", (identificador,))

            def _anotar(ate: int, lidas_ate_aqui: int, *, plano: _Plano = plano, identificador: int = identificador, antes: int = partidas_antes) -> None:
                """Fecha uma transação no meio do arquivo e anota até onde ele está lido.

                O manifesto guarda o **prefixo** -- tamanho, cabeça e cauda medidos até `ate` --,
                que é exatamente a forma que `_planejar` reconhece como "o arquivo cresceu": a
                rodada seguinte lê a partir daí, sem reler o que já entrou. É o mesmo mecanismo
                do torneio anexado da S-532, aplicado ao arquivo interrompido.
                """
                fisico = arquivo_fisico(plano.base)
                conexao.execute(
                    "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        identificador,
                        plano.nome,
                        ate,
                        plano.mtime,
                        _marca(fisico, 0, min(ate, BYTES_DA_MARCA)),
                        _marca(fisico, max(0, ate - BYTES_DA_MARCA), ate),
                        antes + lidas_ate_aqui,
                    ),
                )
                conexao.commit()

            lidas, terminou = _indexar_arquivo(
                conexao,
                base,
                identificador,
                plano.inicio,
                tamanho,
                lidas_na_rodada,
                progress,
                cancel,
                jogadores,
                eventos,
                # Base comprimida não retoma: o byte que se lê é o descomprimido, e `_planejar`
                # já recusa o caminho da cauda para ela. Um marco ali anotaria um ponto que a
                # rodada seguinte leria como outro lugar do arquivo.
                None if eh_comprimida(base) else _anotar,
            )
            if not terminou:
                conexao.rollback()
                cancelado = True
                logger.info("Índice por nome cancelado em %s, com %d partidas lidas dele.", nome, lidas)
                break
            conexao.execute(
                "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identificador, nome, tamanho, plano.mtime, plano.cabeca, plano.cauda, partidas_antes + lidas),
            )
            conexao.commit()
            manifesto[nome] = _Registro(identificador, nome, tamanho, plano.mtime, plano.cabeca, plano.cauda, partidas_antes + lidas)
            lidas_na_rodada += lidas
            arquivos_relidos += 1

        if not cancelado:
            # `IF NOT EXISTS` sempre: numa rodada pequena eles ja estao la e isto nao custa nada;
            # numa grande foram derrubados; e depois de uma cancelada podem ter ficado de fora.
            for indice, colunas in _INDICES_DE_BUSCA:
                conexao.execute(f"CREATE INDEX IF NOT EXISTS {indice} ON {colunas}")
            conexao.execute("INSERT OR REPLACE INTO meta VALUES ('database', ?)", (index_fingerprint(bases),))
            conexao.commit()
        total = sum(registro.games for registro in manifesto.values())
    finally:
        conexao.close()

    resultado = Indexacao(
        partidas=total,
        relidas=lidas_na_rodada,
        arquivos_relidos=arquivos_relidos,
        arquivos_pulados=pulados,
        arquivos_removidos=removidos,
        cancelado=cancelado,
    )
    logger.info(
        "Índice por nome: %d partidas de %d base(s) em %s (%d relida(s), %d pulada(s), %d removida(s)%s)",
        resultado.partidas,
        len(bases),
        path,
        arquivos_relidos,
        pulados,
        removidos,
        ", cancelado" if cancelado else "",
    )
    return resultado


def _inteiro(texto: str) -> int:
    """`2839` -> 2839; `-`, `?`, vazio -> 0. Elo sem número é Elo que não existe."""
    limpo = texto.strip()
    return int(limpo) if limpo.isdigit() else 0


def _ano(data: str) -> int:
    """`2019.01.12` -> 2019; `????.??.??` -> 0. Só os quatro primeiros caracteres contam."""
    return _inteiro(data[:4])


def _linha_da_partida(
    cabecalho: dict[str, str],
    movetext: Sequence[str],
    offset: int,
    identificador: int,
    jogadores: _Dicionario,
    eventos: _Dicionario,
) -> tuple[Any, ...]:
    """A linha de `games` para uma partida lida, na ordem das colunas de `_INSERIR`."""
    branco = cabecalho.get("White", "")
    preto = cabecalho.get("Black", "")
    data = cabecalho.get("Date", "").strip()
    welo = _inteiro(cabecalho.get("WhiteElo", ""))
    belo = _inteiro(cabecalho.get("BlackElo", ""))
    # O header vence (S-534): e a classificacao que quem publicou a partida escolheu. Sem ele, e
    # so numa partida que comeca na posicao inicial, os primeiros lances classificam.
    eco = codigo_do_header(cabecalho.get("ECO", ""))
    if not eco and movetext and "FEN" not in cabecalho:
        abertura = classificar_lances(lances_do_movetext(" ".join(movetext)))
        eco = "" if abertura is None else abertura.codigo
    return (
        pair_hash((surname(branco), surname(preto))),
        identificador,
        offset,
        jogadores.numero(branco),
        jogadores.numero(preto),
        eventos.numero(cabecalho.get("Event", "")),
        data,
        _ano(data),
        welo,
        belo,
        # O menor dos dois, e zero se um falta: "Elo minimo 2700" pergunta pelo nivel da partida,
        # e uma partida em que um dos lados nao tem Elo nao pode afirmar esse nivel.
        min(welo, belo) if welo and belo else 0,
        cabecalho.get("Result", "").strip(),
        eco,
    )


_INSERIR = (
    "INSERT OR IGNORE INTO games "
    "(pair, file, offset, white, black, event, date, year, welo, belo, elo, result, eco) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


Marco = Callable[[int, int], None]
"""`(byte até onde está gravado, partidas lidas até aqui)` -- o ponto de retomada (S-533, r2).

Chamado depois de cada lote gravado, e o byte é sempre **começo de partida**: é o que a rodada
seguinte usa para continuar de onde esta parou. Ver `_indexar_arquivo` e `build_index`."""


def _indexar_arquivo(
    conexao: sqlite3.Connection,
    base: Path,
    identificador: int,
    inicio: int,
    tamanho: int,
    partidas_anteriores: int,
    progress: Progresso | None,
    cancel: threading.Event | None,
    jogadores: _Dicionario,
    eventos: _Dicionario,
    marco: Marco | None = None,
) -> tuple[int, bool]:
    """Grava uma linha de `games` por partida de `base` a partir de `inicio`.

    Devolve `(partidas lidas, terminou)`. `terminou` falso é cancelamento: quem chama desfaz a
    transação.

    A partida é fechada quando a **próxima** começa (ou no fim do arquivo), e não no header
    `[Black]` como até a v4: `Result`, `WhiteElo` e `ECO` vêm depois dele, e o movetext que
    classifica a partida sem `[ECO]` vem depois de todos.

    **`marco` é o que faz o cancelamento não custar a rodada inteira.** A transação era por
    arquivo, e a gigabase **é** um arquivo: cancelar no nono minuto desfazia os nove. A cada lote
    gravado -- `_TAMANHO_DO_LOTE` partidas -- este aviso diz até que byte o índice está completo,
    e quem chama fecha ali uma transação e anota o ponto no manifesto. `None` é o caminho da base
    comprimida, onde o byte lido não é o byte do disco e retomar não é possível (ver `_planejar`).
    """
    partidas = 0
    lote: list[tuple[Any, ...]] = []
    comeco = inicio
    cabecalho: dict[str, str] = {}
    movetext: list[str] = []
    aberta = False
    linhas = 0
    ultimo_aviso = time.monotonic()

    def gravar() -> None:
        jogadores.gravar(conexao)
        eventos.gravar(conexao)
        conexao.executemany(_INSERIR, lote)
        lote.clear()

    with abrir_pgn_bytes(base) as fh:
        if inicio:
            fh.seek(inicio)
        while True:
            posicao = fh.tell()
            linha = fh.readline()
            if not linha:
                break
            linhas += 1
            if linhas % _LINHAS_POR_CONFERENCIA == 0:
                if cancel is not None and cancel.is_set():
                    return partidas, False
                agora = time.monotonic()
                if progress is not None and agora - ultimo_aviso >= INTERVALO_DE_PROGRESSO:
                    progress(base, min(fh.bytes_lidos, tamanho), tamanho, partidas_anteriores + partidas)
                    ultimo_aviso = agora
            if linha.startswith(_ABRE_CABECALHO):
                if linha.lstrip(_BOM).startswith(b"[Event "):
                    if aberta:
                        lote.append(_linha_da_partida(cabecalho, movetext, comeco, identificador, jogadores, eventos))
                        if len(lote) >= _TAMANHO_DO_LOTE:
                            gravar()
                            # `posicao` e nao `comeco`: a partida que fechou entrou no lote, e a
                            # que comeca AQUI ainda nao foi lida. Retomar deste byte le a
                            # proxima, sem repetir a anterior nem pular nenhuma.
                            if marco is not None:
                                marco(posicao, partidas)
                    comeco, cabecalho, movetext, aberta = posicao, {}, [], True
                    partidas += 1
                casado = _RE_HEADER.match(decodificar_linha(linha).rstrip())
                if casado is not None and casado.group(1) in _CAMPOS_DO_INDICE:
                    cabecalho[casado.group(1)] = casado.group(2)
            elif aberta and len(movetext) < _LINHAS_DE_MOVETEXT_LIDAS and "ECO" not in cabecalho and "FEN" not in cabecalho:
                # So o que a classificacao sem header precisa; o resto do movetext e pulado.
                texto = linha.strip()
                if texto:
                    movetext.append(decodificar_linha(texto))
    if aberta:
        lote.append(_linha_da_partida(cabecalho, movetext, comeco, identificador, jogadores, eventos))
    gravar()
    if progress is not None:
        progress(base, tamanho, tamanho, partidas_anteriores + partidas)
    return partidas, True


def _read_game_at(fh: Any, offset: int) -> GameRecord | None:
    """Lê a partida que começa naquele byte. `None` se ali não começa partida nenhuma.

    A guarda do `[Event ` não é zelo: um índice de outra base aponta para o meio de um
    movetext, e sem ela isto devolveria meia partida com cara de partida inteira.
    """
    fh.seek(offset)
    primeira = fh.readline()
    if not primeira.lstrip(_BOM).startswith(b"[Event "):
        return None

    cabecalho: dict[str, str] = {}
    movetext: list[str] = []
    linha = primeira
    while linha:
        if linha.startswith(_ABRE_CABECALHO):
            if movetext:
                break  # comecou a proxima partida
            casado = _RE_HEADER.match(decodificar_linha(linha).rstrip())
            if casado is not None and casado.group(1) in _KEPT_HEADERS:
                cabecalho[casado.group(1)] = casado.group(2)
        else:
            texto = linha.strip()
            if texto:
                movetext.append(decodificar_linha(texto))
            elif movetext:
                break
        linha = fh.readline()
    return GameRecord(headers=cabecalho, movetext=" ".join(movetext))


def partida_em(caminho: Path, offset: int) -> GameRecord | None:
    """A partida que começa naquele byte daquela base -- o par de `Achado.caminho`/`Achado.offset`.

    **É o que o índice existe para permitir**: um `seek` e uma leitura, em vez da passada de
    minutos. `None` quando ali não começa partida nenhuma, que é o sintoma de um índice adiantado
    em relação ao arquivo -- e é resposta e não exceção porque quem chama é uma janela que precisa
    dizer isso à pessoa (ver a guarda do `[Event ` em `_read_game_at`).
    """
    if not existe_base(caminho):
        return None
    with abrir_pgn_bytes(caminho) as fh:
        return _read_game_at(fh, offset)


def _abrir_para_consulta(bases: Sequence[Path], path: Path) -> tuple[sqlite3.Connection | None, str]:
    """A conexão só de leitura, conferidos versão e fingerprint; ou `(None, motivo)`.

    O motivo já vem em pt-BR e com a instrução, porque as duas consultas -- `lookup_pair`, que o
    põe no log, e `buscar`, que o levanta -- dizem a mesma coisa.
    """
    refazer = "Refaça o índice: menu da sala de estudo, ou cvoff-games --build-index"
    if not path.exists():
        return None, f"O índice da base de partidas ainda não foi construído. {refazer}"
    try:
        conexao = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return None, f"Índice por nome ilegível ({exc}). {refazer}"
    try:
        gravada = conexao.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
    except sqlite3.Error:
        gravada = None
    if gravada is None or gravada[0] != str(INDEX_VERSION):
        conexao.close()
        return None, (
            f"O índice por nome está no formato {None if gravada is None else gravada[0]!r} e este programa "
            f"lê o {INDEX_VERSION}. {refazer}"
        )
    gravado = conexao.execute("SELECT value FROM meta WHERE key = 'database'").fetchone()
    atual = index_fingerprint(bases)
    if gravado is None:
        conexao.close()
        return None, f"O índice da base está em obras: uma rodada não chegou ao fim. {refazer}"
    if gravado[0] != atual:
        conexao.close()
        return None, (
            f"O índice por nome foi feito para {gravado[0]!r} e a base agora é {atual!r}: os offsets não valem, "
            f"e a consulta seria lixo. {refazer}"
        )
    return conexao, ""


def _arquivos_do_indice(conexao: sqlite3.Connection, bases: Sequence[Path]) -> dict[int, Path]:
    """`número do arquivo -> base`, casado por nome e não pela ordem.

    Se um arquivo for renomeado o fingerprint já recusou a consulta, e casar por nome deixa o
    erro aparecer aqui em vez de virar leitura do arquivo errado.
    """
    por_nome = {nome_da_base(caminho): caminho for caminho in bases}
    return {
        int(identificador): por_nome[nome]
        for identificador, nome in conexao.execute("SELECT id, name FROM files")
        if nome in por_nome
    }


def lookup_pair(
    pair: PlayerPair,
    databases: Path | Sequence[Path],
    path: Path = DEFAULT_INDEX_PATH,
    *,
    both_colors: bool = True,
    limit: int = MAX_GAMES_PER_LOOKUP,
) -> list[GameRecord]:
    """As partidas daquele par, lidas direto dos offsets. Milissegundos.

    `both_colors` procura também com as cores trocadas, e é o padrão porque a legenda do livro
    não promete quem tinha as brancas -- "Coull - Stanciu" é como o autor escreveu, não uma
    declaração de cor.

    Devolve vazio, e não levanta, quando não há índice, quando ele é de outra base, quando é
    de um formato anterior ou quando uma rodada de `build_index` não chegou ao fim: quem chama
    tem um caminho alternativo (a lista do cache), e um erro aqui tiraria os dois.

    **Numa base comprimida a leitura é uma passada, e não 40 seeks** (S-531): os offsets são
    lidos em ordem crescente, então o descompactador anda para a frente uma vez só. São
    segundos numa base de gigabytes -- o preço de não a ter descompactado, dito em
    `EXTENSOES_DE_BASE`.
    """
    bases = [caminho for caminho in as_databases(databases) if existe_base(caminho)]
    if not path.exists() or not bases:
        return []
    conexao, motivo = _abrir_para_consulta(bases, path)
    if conexao is None:
        logger.warning("%s", motivo)
        return []

    try:
        arquivos = _arquivos_do_indice(conexao, bases)
        procurados = [tuple(pair)] + ([(pair[1], pair[0])] if both_colors else [])
        # **Uma consulta por cor, com cota propria** (S-139). Um `IN (?,?) LIMIT ?` da uma cota
        # unica para os dois hashes, e ela se esgota na primeira cor: medido no indice real
        # (20.902.904 partidas), Karpov x Kasparov tem 245 partidas com um hash e outras tantas
        # com o outro, entao a segunda **nunca era lida**. O `both_colors=True` ficava inerte,
        # em silencio, exatamente nos pares mais citados pelos livros.
        por_cor = [
            [
                (int(linha[1]), int(linha[0]))
                for linha in conexao.execute(
                    "SELECT offset, file FROM games WHERE pair=? LIMIT ?",
                    (pair_hash(procurado), limit),  # type: ignore[arg-type]
                )
            ]
            for procurado in procurados
        ]
        achados = _fair_share(por_cor, limit)
    finally:
        conexao.close()

    esperados = {frozenset(p) for p in procurados}
    partidas = []
    for partida in _ler_partidas(arquivos, achados):
        # Confere os nomes: uma colisao de hash custa esta leitura, e nao uma resposta
        # errada. E um indice desatualizado por edicao da base cai aqui tambem.
        lidos = frozenset({surname(partida.headers.get("White", "")), surname(partida.headers.get("Black", ""))})
        if lidos in esperados:
            partidas.append(partida)
    return partidas


def _ler_partidas(arquivos: dict[int, Path], achados: Iterable[tuple[int, int]]) -> Iterable[GameRecord]:
    """As partidas de `(arquivo, offset)`, agrupadas por arquivo e em ordem de offset.

    Abrir o mesmo `.pgn` a cada offset seria pagar o `open` por partida em vez de por base -- e,
    numa base comprimida, voltar atrás seria descompactar do zero de novo.
    """
    pedidos = list(achados)
    for identificador in sorted({arquivo for arquivo, _ in pedidos}):
        caminho = arquivos.get(identificador)
        if caminho is None:
            logger.warning("O índice aponta para um arquivo que não está mais na pasta da base.")
            continue
        with abrir_pgn_bytes(caminho) as fh:
            for arquivo, offset in sorted(pedidos, key=lambda item: item[1]):
                if arquivo != identificador:
                    continue
                partida = _read_game_at(fh, offset)
                if partida is not None and partida.movetext:
                    yield partida


def _fair_share(por_grupo: list[list[tuple[int, int]]], limit: int) -> list[tuple[int, int]]:
    """Reparte `limit` leituras entre os grupos, dando a cada um a sua fatia antes de sobrar.

    **Um teto global consumido em ordem não é uma cota por cor** (S-139): dar `LIMIT limit` às
    duas consultas e depois cortar a concatenação em `limit` devolve exatamente o que a
    consulta única devolvia, porque a primeira cor volta a comer tudo. A repartição é o que
    torna `both_colors=True` observável.

    A fatia é `limit // grupos`, e o que sobrar -- porque um dos lados tem menos partidas que a
    fatia dele -- é distribuído em ordem. Um par que só jogou com uma cor continua recebendo o
    `limit` inteiro.

    `limit` continua sendo teto: ele é o custo em leituras de disco que quem chama aceitou
    pagar, e são até 40 seeks num arquivo de gigabytes.
    """
    if not por_grupo:
        return []
    fatia = max(1, limit // len(por_grupo))
    escolhidos: list[tuple[int, int]] = []
    for grupo in por_grupo:
        escolhidos.extend(grupo[:fatia])
    # A sobra: quem tinha menos que a fatia deixou espaco, e ele vai para quem tinha mais.
    for grupo in por_grupo:
        if len(escolhidos) >= limit:
            break
        escolhidos.extend(grupo[fatia : fatia + limit - len(escolhidos)])
    return escolhidos[:limit]


# ------------------------------------------------------------------------------- busca (S-533)

_SUFIXOS_DE_GERACAO = ("jr", "jr.", "sr", "sr.", "ii", "iii", "iv")
"""O que a base cola no sobrenome e o dicionário guarda junto (S-533, r2).

`Vehre Jr, John L` entra em `players` com o sobrenome `vehre jr`, porque `games_db.surname`
corta na vírgula e o `Jr` está **antes** dela -- e são 264 grafias assim na gigabase. Quem digita
`Vehre` procura `vehre` e não acha nenhuma delas, em silêncio.

Consertar no `surname` seria o caminho curto e ele custa a passada inteira: o `pair` de cada uma
das 10,3 milhões de linhas é `pair_hash` sobre o sobrenome, e mudá-lo invalidaria a coluna. Aqui
o conserto é do lado de quem pergunta -- as formas com sufixo entram no `IN` como valores
exatos, que a árvore `players_surname` resolve com uma sonda cada."""


def _sobrenomes(digitado: str) -> tuple[str, ...]:
    """As formas de `players.surname` que este texto pode querer dizer, sem repetição.

    Três leituras do mesmo campo, e cada uma nasceu de uma busca que respondia zero:

    - **`Carlsen, Magnus`** -> `carlsen`. É a da base, e `games_db.surname` já a dá.
    - **`Magnus Carlsen`** -> `carlsen` **também**. A ordem natural é como se escreve um nome
      fora de um arquivo `.pgn`, e `surname` a lê como `magnus carlsen` -- que não é o
      sobrenome de ninguém. Sem vírgula e com mais de uma palavra, a última palavra entra como
      segunda forma. Ela **acrescenta** e não substitui: `Van der Wiel` continua inteiro na
      primeira forma, e a segunda (`wiel`) não casa com nada, o que não custa nada.
    - **`Vehre`** -> também `vehre jr`. Ver `_SUFIXOS_DE_GERACAO`.
    """
    principal = surname(digitado)
    if not principal:
        return ()
    formas = [principal]
    if "," not in digitado:
        palavras = principal.split()
        if len(palavras) > 1:
            formas.append(palavras[-1])
    formas.extend(f"{forma} {sufixo}" for forma in list(formas) for sufixo in _SUFIXOS_DE_GERACAO)
    return tuple(dict.fromkeys(formas))


def _jogador(formas: Sequence[str]) -> str:
    """`(SELECT id FROM players WHERE surname IN (?, ?, …))` com um `?` por forma.

    Os números de todo nome cujo sobrenome é o pedido: `Carlsen, Magnus`, `Carlsen, M` e
    `Carlsen,Magnus` são três linhas de `players` e o mesmo jogador. É uma subconsulta e não uma
    lista de `?` sobre `games` porque um sobrenome comum (`Ivanov`) tem centenas de grafias, e o
    limite de parâmetros do SQLite não é o lugar de descobrir isso.
    """
    return f"(SELECT id FROM players WHERE surname IN ({','.join('?' * len(formas))}))"


def _clausulas(filtro: Filtro) -> tuple[list[str], list[Any]]:
    """O `WHERE` da busca, uma cláusula por filtro preenchido, com os parâmetros ao lado.

    Cada cláusula usa um dos seis índices de `_INDICES_DE_BUSCA`; o SQLite escolhe o mais
    seletivo e filtra o resto na linha. O evento é `LIKE` sobre a forma dobrada (`fold`) do
    dicionário `events` -- uma varredura, mas de cem mil linhas e não de dez milhões.
    """
    onde: list[str] = []
    parametros: list[Any] = []
    brancas = _sobrenomes(filtro.brancas)
    pretas = _sobrenomes(filtro.pretas)
    if brancas and pretas:
        b, p = _jogador(brancas), _jogador(pretas)
        if filtro.qualquer_cor:
            onde.append(f"((white IN {b} AND black IN {p}) OR (white IN {p} AND black IN {b}))")
            parametros += [*brancas, *pretas, *pretas, *brancas]
        else:
            onde.append(f"white IN {b} AND black IN {p}")
            parametros += [*brancas, *pretas]
    elif brancas or pretas:
        um = brancas or pretas
        alvo = _jogador(um)
        if filtro.qualquer_cor:
            onde.append(f"(white IN {alvo} OR black IN {alvo})")
            parametros += [*um, *um]
        else:
            onde.append(f"{'white' if brancas else 'black'} IN {alvo}")
            parametros += [*um]
    if filtro.evento.strip():
        padrao = fold(filtro.evento).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        onde.append("event IN (SELECT id FROM events WHERE folded LIKE ? ESCAPE '\\')")
        parametros.append(f"%{padrao}%")
    if filtro.ano_de:
        onde.append("year >= ?")
        parametros.append(int(filtro.ano_de))
    if filtro.ano_ate:
        onde.append("year <= ?")
        parametros.append(int(filtro.ano_ate))
    if filtro.elo_minimo:
        onde.append("elo >= ?")
        parametros.append(int(filtro.elo_minimo))
    if filtro.resultado:
        onde.append("result = ?")
        parametros.append(filtro.resultado)
    eco_de = codigo_do_header(filtro.eco_de)
    eco_ate = codigo_do_header(filtro.eco_ate)
    if eco_de or eco_ate:
        onde.append("eco >= ? AND eco <= ?")
        parametros += [eco_de or eco_ate, eco_ate or eco_de]
    return onde, parametros


_ORDEM = "ORDER BY year DESC, date DESC, id DESC"

_POR_ORDEM = (
    f"SELECT id FROM games INDEXED BY {INDICE_DA_ORDEM}{{clausula}} {_ORDEM} LIMIT ? OFFSET ?"
)
"""O plano do filtro **largo**: andar pela árvore da ordem e parar na centésima que passa.

`INDEXED BY` e não confiança no planejador: sem `ANALYZE` o sqlite não sabe quantas linhas um
`eco BETWEEN 'A00' AND 'E99'` casa, e este Python traz um sqlite sem `STAT4` -- toda faixa vale a
mesma estimativa de fábrica para ele. O plano certo aqui não depende de estatística nenhuma: a
contagem já disse que casam mais de cem mil, e com essa densidade cem linhas aparecem nas
primeiras milhares que se olha."""

_POR_FILTRO = (
    f"SELECT id FROM (SELECT id, year, date FROM games{{clausula}} LIMIT {TETO_DE_CONTAGEM + 1}) {_ORDEM} LIMIT ? OFFSET ?"
)
"""O plano do filtro **estreito**: escolher pela árvore do filtro e ordenar o que sobrou.

O `LIMIT` de dentro é o que dá o teto ao trabalho -- e ele nunca corta nada, porque este plano só
é usado quando a contagem ficou **abaixo** do teto. Ele está ali para tirar a decisão do
planejador de duas maneiras: a subconsulta sem `ORDER BY` faz o sqlite escolher a árvore mais
seletiva do filtro (e não a da ordem, que aqui seria uma varredura inteira à procura das poucas
que casam), e o teto garante que a ordenação de fora nunca veja mais de cem mil linhas."""

_SELECIONAR_LINHA = (
    "SELECT g.id, g.file, g.offset, pw.name, g.welo, pb.name, g.belo, g.result, ev.name, g.date, g.eco "
    "FROM games g JOIN players pw ON pw.id = g.white JOIN players pb ON pb.id = g.black "
    "JOIN events ev ON ev.id = g.event"
)


def buscar(
    filtro: Filtro,
    databases: Path | Sequence[Path],
    path: Path = DEFAULT_INDEX_PATH,
    *,
    limite: int = PAGINA,
    offset: int = 0,
) -> Busca:
    """As partidas que casam o filtro, da mais recente para a mais antiga, uma página (S-533).

    **A ordem é por data, e a página é por `OFFSET`.** `ORDER BY year DESC, date DESC, id DESC` --
    o `id` desempata para a paginação ser estável entre duas chamadas.

    **A contagem vem primeiro, e é ela que escolhe o plano.** Contar para em `TETO_DE_CONTAGEM`,
    então custa dezenas de milissegundos em qualquer filtro; e o número que ela devolve é a única
    coisa que separa os dois planos possíveis, que têm custos opostos:

    | a contagem diz | o plano | o custo |
    |---|---|---|
    | passou do teto (o filtro casa milhões) | `_POR_ORDEM`: andar pela árvore `(year, date)` de trás para a frente e conferir o filtro linha a linha | quantas se olha até achar cem -- com 10% de densidade, mil |
    | ficou abaixo (o filtro escolhe) | `_POR_FILTRO`: a árvore mais seletiva do filtro, com teto, e ordenar o que sobrou | no máximo cem mil linhas ordenadas |

    Antes desta rodada havia um plano só -- o segundo, sem teto --, e ele pagava a ordenação de
    **todas** as linhas que casassem: `ano 2019` sozinho custava 2,8 s, a faixa `A00–E99` 5,4 s e
    o evento `ch-` 5,1 s na gigabase de 10,3 milhões de partidas, enquanto a contagem das mesmas
    três já parava no teto em 40 ms. A conta nunca foi *achar*, foi *ordenar o que se achou*.

    **O ano vem antes da data, e não é redundância.** A data é o texto do header, e a base escreve
    o que não sabe com interrogação: `2019.??.??`. Ordenado como texto, `?` (0x3F) é **maior** que
    qualquer dígito -- então `????.??.??` viria antes de `2024.12.31`, e a primeira página de toda
    busca seria feita das partidas sem data. Com `year` na frente (zero quando o header não diz
    ano), a partida sem data cai no fim, que é onde o docstring sempre disse que ela ficava; dentro
    do mesmo ano o texto ainda ordena, e `2019.??.??` fica antes de `2019.12.31` -- um mês
    desconhecido não tem lugar certo, e o que importa ali é ser do mesmo ano.

    **Com posição no filtro, a resposta é medida e não completa.** Os outros filtros escolhem as
    candidatas, na mesma ordem; até `TETO_DE_REPLAY` delas são lidas e reproduzidas com o
    porteiro da S-85, e o que passa pela posição é a página. `Busca.examinadas` diz quantas foram
    lidas, e `proximo_offset` continua de lá.

    Levanta `IndiceIndisponivel` quando não há índice, ele é de outro formato ou está em obras --
    a frase já diz o que fazer.
    """
    bases = [caminho for caminho in as_databases(databases) if existe_base(caminho)]
    if not bases:
        raise IndiceIndisponivel("Não há base de partidas em pgn_database/.")
    conexao, motivo = _abrir_para_consulta(bases, path)
    if conexao is None:
        raise IndiceIndisponivel(motivo)
    try:
        onde, parametros = _clausulas(filtro)
        clausula = (" WHERE " + " AND ".join(onde)) if onde else ""
        total = int(
            conexao.execute(
                f"SELECT COUNT(*) FROM (SELECT 1 FROM games{clausula} LIMIT ?)", [*parametros, TETO_DE_CONTAGEM + 1]
            ).fetchone()[0]
        )
        total_e_teto = total > TETO_DE_CONTAGEM
        total = min(total, TETO_DE_CONTAGEM)
        quantas = TETO_DE_REPLAY if filtro.posicao else limite
        molde = _POR_ORDEM if total_e_teto else _POR_FILTRO
        ids = [
            int(linha[0])
            for linha in conexao.execute(molde.format(clausula=clausula), [*parametros, quantas, offset])
        ]
        arquivos = _arquivos_do_indice(conexao, bases)
        linhas: dict[int, tuple[Any, ...]] = {}
        for comeco in range(0, len(ids), 500):
            pedaco = ids[comeco : comeco + 500]
            marcas = ",".join("?" * len(pedaco))
            for linha in conexao.execute(f"{_SELECIONAR_LINHA} WHERE g.id IN ({marcas})", pedaco):
                linhas[int(linha[0])] = tuple(linha)
    finally:
        conexao.close()

    achados: list[Achado] = []
    for identificador in ids:
        linha = linhas.get(identificador)
        if linha is None:
            continue
        caminho = arquivos.get(int(linha[1]))
        if caminho is None:
            continue
        achados.append(
            Achado(
                brancas=str(linha[3]),
                elo_brancas=int(linha[4]),
                pretas=str(linha[5]),
                elo_pretas=int(linha[6]),
                resultado=str(linha[7]),
                evento=str(linha[8]),
                data=str(linha[9]),
                eco=str(linha[10]),
                caminho=caminho,
                offset=int(linha[2]),
            )
        )
    if not filtro.posicao:
        return Busca(tuple(achados), total, total_e_teto, offset, 0)

    examinadas = len(achados)
    por_chave = {(arquivo, offset_): indice for indice, (arquivo, offset_) in enumerate((a.caminho, a.offset) for a in achados)}
    pedidos = [(numero, achado.offset) for numero, achado in ((_numero_de(arquivos, a.caminho), a) for a in achados)]
    passam: set[int] = set()
    for numero_e_offset, partida in _ler_com_chave(arquivos, pedidos):
        caminho = arquivos[numero_e_offset[0]]
        if positions_of([partida], filtro.posicao):
            passam.add(por_chave[(caminho, numero_e_offset[1])])
    escolhidos = [achado for indice, achado in enumerate(achados) if indice in passam][:limite]
    return Busca(tuple(escolhidos), total, total_e_teto, offset, examinadas)


def _numero_de(arquivos: dict[int, Path], caminho: Path) -> int:
    for numero, base in arquivos.items():
        if base == caminho:
            return numero
    raise KeyError(caminho)


def _ler_com_chave(arquivos: dict[int, Path], pedidos: list[tuple[int, int]]) -> Iterable[tuple[tuple[int, int], GameRecord]]:
    """`_ler_partidas` devolvendo também `(arquivo, offset)`, para quem precisa saber qual leu."""
    for identificador in sorted({arquivo for arquivo, _ in pedidos}):
        caminho = arquivos.get(identificador)
        if caminho is None:
            continue
        with abrir_pgn_bytes(caminho) as fh:
            for arquivo, offset in sorted(pedidos, key=lambda item: item[1]):
                if arquivo != identificador:
                    continue
                partida = _read_game_at(fh, offset)
                if partida is not None and partida.movetext:
                    yield (arquivo, offset), partida


def positions_of(games: Iterable[GameRecord], placement: str) -> list[tuple[GameRecord, int, bool]]:
    """Em quais das partidas aquela colocação aparece, e em que lance.

    O casamento continua sendo exato nas 64 casas -- o índice mudou *como se chega* às
    partidas, não o que conta como casamento.

    **Com o porteiro da S-85** (S-139): `positions` recebe a ocupação da colocação procurada e
    só monta a FEN das posições cujo mapa de casas ocupadas bate. A S-85 mediu que isso corta
    ~3× o custo de reproduzir os lances, e este caminho pagava o preço cheio -- na thread do
    Tk, porque quem o chama é a busca por nome da janela de candidatas.

    O porteiro é **filtro e não critério**: o que decide continua sendo a igualdade das 64
    casas, três linhas abaixo. É o que o docstring de `GameRecord.positions` garante.
    """
    porteiro = frozenset({occupancy(placement)})
    achados = []
    for partida in games:
        for colocacao, lance, vez in partida.positions(porteiro):
            if colocacao == placement:
                achados.append((partida, lance, vez))
                break
    return achados
