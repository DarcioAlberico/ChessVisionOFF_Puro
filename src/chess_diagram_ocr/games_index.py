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

**O custo, medido e não estimado:** ~8,4 min e 431 MB para 10,5 M partidas. Proporcional ao que
a pasta tem: com duas gigabases, o dobro. Fora do git, ao lado da base, como todo material
derivado dela.

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

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_INDEX_PATH",
    "INDEX_VERSION",
    "INTERVALO_DE_PROGRESSO",
    "Indexacao",
    "Progresso",
    "build_index",
    "index_fingerprint",
    "lookup_pair",
    "pair_hash",
    "positions_of",
]

DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "games_index.sqlite"

INDEX_VERSION = 4
"""O formato do arquivo. **4** desde a S-532, quando a tabela `files` virou manifesto.

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

`INSERT OR IGNORE` porque a chave é única: a mesma partida indexada duas vezes era uma linha
duplicada e silenciosa antes, e agora seria um erro em cima de uma varredura de horas."""

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

_LINHAS_POR_CONFERENCIA = 16_384
"""De quantas em quantas linhas o relógio e a bandeira de cancelamento são conferidos.

Dezesseis mil linhas são ~1 MB de PGN, uns 10 ms a 100 MB/s; o cancelamento é honrado bem
dentro do segundo que a S-532 exige, e o custo de olhar o relógio some no ruído."""

Progresso = Callable[[Path, int, int, int], None]
"""`(base, bytes_lidos, bytes_totais, partidas)`. Os bytes são os do disco -- comprimidos, se a
base for --, porque são os únicos comparáveis ao tamanho do arquivo; as partidas são as lidas
**nesta rodada**, somadas sobre os arquivos."""


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


def _abrir_para_escrita(path: Path) -> sqlite3.Connection:
    """O índice pronto para receber esta rodada: o existente, se for desta versão; senão, um novo.

    Um índice de outra versão é apagado e refeito -- é o que `--build-index` sempre significou
    para ele --, e o `.parcial` de uma versão anterior interrompida vai junto.
    """
    path.with_suffix(path.suffix + ".parcial").unlink(missing_ok=True)
    if path.exists() and _versao_gravada(path) != str(INDEX_VERSION):
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
    # `WITHOUT ROWID` com a chave composta (S-140): a coluna de busca **e** a arvore, e
    # `offset`/`file` viajam na mesma folha. Ver `INDEX_VERSION` para o numero medido.
    conexao.execute(
        "CREATE TABLE IF NOT EXISTS games ("
        "pair INTEGER NOT NULL, offset INTEGER NOT NULL, file INTEGER NOT NULL, "
        "PRIMARY KEY (pair, file, offset)) WITHOUT ROWID"
    )
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
    não interessa, e quem for consultar lê a partida inteira na hora.

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

    **Uma transação por arquivo, e a marca da base só no fim.** Cancelar (`cancel`) ou morrer
    no meio de um arquivo desfaz esse arquivo e mantém os anteriores -- a rodada seguinte
    continua de onde parou. E enquanto a rodada não termina a `meta.database` fica **apagada**:
    é ela que `lookup_pair` confere, então um índice pela metade recusa a consulta em vez de
    responder menos do que a base tem (S-25, agora sem `.parcial`).

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

        proximo_id = max((registro.id for registro in manifesto.values()), default=-1) + 1
        for base in bases:
            if cancel is not None and cancel.is_set():
                cancelado = True
                break
            nome = nome_da_base(base)
            fisico = arquivo_fisico(base)
            try:
                mtime = fisico.stat().st_mtime
            except OSError:
                logger.warning("Índice por nome: %s não pôde ser lido e ficou de fora.", nome)
                continue
            tamanho = tamanho_da_base(base)
            cabeca, cauda = _marcas(fisico, fisico.stat().st_size)
            antigo = manifesto.get(nome)

            if antigo is not None and (antigo.size, antigo.head, antigo.tail) == (tamanho, cabeca, cauda):
                if antigo.mtime != mtime:
                    conexao.execute("UPDATE files SET mtime = ? WHERE id = ?", (mtime, antigo.id))
                    conexao.commit()
                pulados += 1
                if progress is not None:
                    progress(base, tamanho, tamanho, lidas_na_rodada)
                continue

            inicio = 0
            partidas_antes = 0
            if antigo is None:
                identificador, proximo_id = proximo_id, proximo_id + 1
            else:
                identificador = antigo.id
                if (
                    not eh_comprimida(base)
                    and tamanho > antigo.size
                    and _marca(fisico, 0, min(antigo.size, BYTES_DA_MARCA)) == antigo.head
                    and _marca(fisico, max(0, antigo.size - BYTES_DA_MARCA), antigo.size) == antigo.tail
                ):
                    # So a cauda: o que estava la continua la, byte a byte, e os offsets antigos
                    # continuam valendo. As duas marcas sao refeitas sobre os MESMOS trechos que o
                    # manifesto mediu -- num arquivo menor que 64 KB a cabeca era o arquivo
                    # inteiro, e compara-la com a cabeca de agora, mais comprida, diria "mudou"
                    # sobre um arquivo que so cresceu.
                    inicio, partidas_antes = antigo.size, antigo.games
                    logger.info("Índice por nome: %s cresceu; lendo a partir do byte %d.", nome, inicio)
                else:
                    conexao.execute("DELETE FROM games WHERE file = ?", (identificador,))

            lidas, terminou = _indexar_arquivo(
                conexao, base, identificador, inicio, tamanho, lidas_na_rodada, progress, cancel
            )
            if not terminou:
                conexao.rollback()
                cancelado = True
                logger.info("Índice por nome cancelado em %s, com %d partidas lidas dele.", nome, lidas)
                break
            conexao.execute(
                "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identificador, nome, tamanho, mtime, cabeca, cauda, partidas_antes + lidas),
            )
            conexao.commit()
            manifesto[nome] = _Registro(identificador, nome, tamanho, mtime, cabeca, cauda, partidas_antes + lidas)
            lidas_na_rodada += lidas
            arquivos_relidos += 1

        if not cancelado:
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


def _indexar_arquivo(
    conexao: sqlite3.Connection,
    base: Path,
    identificador: int,
    inicio: int,
    tamanho: int,
    partidas_anteriores: int,
    progress: Progresso | None,
    cancel: threading.Event | None,
) -> tuple[int, bool]:
    """Grava `(par, offset, arquivo)` de cada partida de `base` a partir de `inicio`.

    Devolve `(partidas lidas, terminou)`. `terminou` falso é cancelamento: quem chama desfaz a
    transação. Nada aqui faz `commit`.
    """
    partidas = 0
    lote: list[tuple[int, int, int]] = []
    comeco = inicio
    branco = ""
    linhas = 0
    ultimo_aviso = time.monotonic()
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
            if not linha.startswith(_ABRE_CABECALHO):
                continue
            if linha.lstrip(_BOM).startswith(b"[Event "):
                comeco, branco = posicao, ""
                partidas += 1
                continue
            casado = _RE_HEADER.match(decodificar_linha(linha).rstrip())
            if casado is None:
                continue
            if casado.group(1) == "White":
                branco = surname(casado.group(2))
            elif casado.group(1) == "Black" and branco:
                lote.append((pair_hash((branco, surname(casado.group(2)))), comeco, identificador))
                if len(lote) >= 200_000:
                    conexao.executemany("INSERT OR IGNORE INTO games VALUES (?, ?, ?)", lote)
                    lote.clear()
    conexao.executemany("INSERT OR IGNORE INTO games VALUES (?, ?, ?)", lote)
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
    try:
        conexao = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        logger.warning("Índice por nome ilegível (%s).", exc)
        return []

    try:
        gravada = conexao.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
        if gravada is None or gravada[0] != str(INDEX_VERSION):
            logger.warning(
                "O índice por nome está no formato %r e este programa lê o %d. Refaça com: "
                "cvoff-games --build-index",
                None if gravada is None else gravada[0],
                INDEX_VERSION,
            )
            return []

        gravado = conexao.execute("SELECT value FROM meta WHERE key = 'database'").fetchone()
        atual = index_fingerprint(bases)
        if gravado is None or gravado[0] != atual:
            logger.warning(
                "O índice por nome foi feito para %r e a base agora é %r: os offsets não valem, "
                "e a consulta seria lixo. Refaça com: cvoff-games --build-index",
                None if gravado is None else gravado[0],
                atual,
            )
            return []

        # Nome, e nao a ordem: se um arquivo for renomeado o fingerprint ja recusou a consulta,
        # e casar por nome deixa o erro aparecer aqui em vez de virar leitura do arquivo errado.
        por_nome = {nome_da_base(caminho): caminho for caminho in bases}
        arquivos = {
            int(identificador): por_nome[nome]
            for identificador, nome in conexao.execute("SELECT id, name FROM files")
            if nome in por_nome
        }

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
    # Agrupado por arquivo e em ordem de offset: sao ate 40 leituras, e abrir o mesmo .pgn a
    # cada uma seria pagar o `open` por offset em vez de por base -- e, numa base comprimida,
    # voltar atras seria descompactar do zero de novo.
    for identificador in sorted({arquivo for arquivo, _ in achados}):
        caminho = arquivos.get(identificador)
        if caminho is None:
            logger.warning("O índice aponta para um arquivo que não está mais na pasta da base.")
            continue
        with abrir_pgn_bytes(caminho) as fh:
            for arquivo, offset in sorted(achados, key=lambda item: item[1]):
                if arquivo != identificador:
                    continue
                partida = _read_game_at(fh, offset)
                if partida is None or not partida.movetext:
                    continue
                # Confere os nomes: uma colisao de hash custa esta leitura, e nao uma resposta
                # errada. E um indice desatualizado por edicao da base cai aqui tambem.
                lidos = frozenset(
                    {surname(partida.headers.get("White", "")), surname(partida.headers.get("Black", ""))}
                )
                if lidos in esperados:
                    partidas.append(partida)
    return partidas


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
