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
responderia zero -- em silêncio, que é como a S-93 começou. (Devolver partida *errada* exigiria
que o outro arquivo tivesse, naquele mesmo byte, uma partida do mesmo par. É raro, e a
conferência de nomes é o que sobra contra ele -- não é motivo para dispensar a coluna.)
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from .config import PROJECT_ROOT
from .games_db import _KEPT_HEADERS, _RE_HEADER, GameRecord, PlayerPair, as_databases, surname

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_INDEX_PATH",
    "INDEX_VERSION",
    "build_index",
    "index_fingerprint",
    "lookup_pair",
    "pair_hash",
    "positions_of",
]

DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "games_index.sqlite"

INDEX_VERSION = 2
"""O formato do arquivo. **2** desde a S-93, quando a partida passou a guardar em que base mora.

Existe porque o fingerprint não bastava para notar a diferença: com uma base só, a marca da
versão 1 (`nome:tamanho`) é *idêntica* à da 2, e um índice antigo passaria pela conferência
para depois quebrar na primeira consulta -- `SELECT ... file` numa tabela sem essa coluna. Uma
versão declarada transforma isso num aviso com instrução, que é o que o resto do módulo faz
com todo desencontro."""

MAX_GAMES_PER_LOOKUP = 40
"""Teto de partidas lidas por consulta -- o mesmo do `MAX_GAMES_PER_PAIR`, e pela mesma razão:
Kasparov x Karpov são 170 partidas, e reproduzir todas para achar uma posição custaria tempo
sem melhorar a resposta."""


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
    """
    marcas = []
    for caminho in as_databases(databases):
        try:
            marcas.append(f"{caminho.name}:{caminho.stat().st_size}")
        except OSError:
            marcas.append(f"{caminho.name}:0")
    return "|".join(marcas)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path))


def build_index(
    databases: Path | Sequence[Path],
    path: Path = DEFAULT_INDEX_PATH,
    *,
    progress: Callable[[int], None] | None = None,
) -> int:
    """Percorre cada base uma vez e grava `(par, arquivo, offset)` de cada partida. Devolve quantas.

    **Uma passada de cabeçalhos, sem reproduzir lance nenhum** -- é por isso que ela custa ~11
    min e não os ~30 da varredura por posição. O movetext é pulado como texto: aqui ele não
    interessa, e quem for consultar lê a partida inteira na hora.

    **O arquivo faz parte da chave desde a S-93.** Com duas bases na pasta, um offset sozinho é
    ambíguo -- o byte 4.000.000 existe nas duas, e apontam para partidas diferentes. A tabela
    `files` guarda o nome de cada base e a coluna `file` diz de qual delas é cada offset.

    O índice é construído num arquivo temporário vizinho e renomeado no fim (S-25): um índice
    pela metade é pior que nenhum, porque parece pronto e responde menos do que a base tem.
    """
    bases = as_databases(databases)
    temporario = path.with_suffix(path.suffix + ".parcial")
    temporario.unlink(missing_ok=True)
    conexao = _connect(temporario)
    try:
        # Sem journal e sem fsync por insercao: se isto for interrompido, o arquivo parcial e
        # descartado de qualquer forma -- nao ha nada a recuperar de um indice pela metade.
        conexao.execute("PRAGMA journal_mode=OFF")
        conexao.execute("PRAGMA synchronous=OFF")
        conexao.execute(
            "CREATE TABLE games (pair INTEGER NOT NULL, offset INTEGER NOT NULL, file INTEGER NOT NULL)"
        )
        conexao.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conexao.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conexao.execute("INSERT INTO meta VALUES ('database', ?)", (index_fingerprint(bases),))
        conexao.execute("INSERT INTO meta VALUES ('version', ?)", (str(INDEX_VERSION),))

        partidas = 0
        lote: list[tuple[int, int, int]] = []
        for identificador, base in enumerate(bases):
            conexao.execute("INSERT INTO files VALUES (?, ?)", (identificador, base.name))
            inicio = 0
            branco = ""
            with base.open("rb") as fh:
                while True:
                    posicao = fh.tell()
                    linha = fh.readline()
                    if not linha:
                        break
                    if not linha.startswith(b"["):
                        continue
                    if linha.startswith(b"[Event "):
                        inicio, branco = posicao, ""
                        partidas += 1
                        if partidas % 500_000 == 0 and progress is not None:
                            progress(partidas)
                        continue
                    casado = _RE_HEADER.match(linha.decode("utf-8", "replace").rstrip())
                    if casado is None:
                        continue
                    if casado.group(1) == "White":
                        branco = surname(casado.group(2))
                    elif casado.group(1) == "Black" and branco:
                        lote.append((pair_hash((branco, surname(casado.group(2)))), inicio, identificador))
                        if len(lote) >= 200_000:
                            conexao.executemany("INSERT INTO games VALUES (?, ?, ?)", lote)
                            lote.clear()
        conexao.executemany("INSERT INTO games VALUES (?, ?, ?)", lote)
        conexao.execute("CREATE INDEX games_pair ON games (pair)")
        conexao.commit()
    finally:
        conexao.close()
    temporario.replace(path)
    logger.info("Índice por nome: %d partidas de %d base(s) em %s", partidas, len(bases), path)
    return partidas


def _read_game_at(fh, offset: int) -> GameRecord | None:
    """Lê a partida que começa naquele byte. `None` se ali não começa partida nenhuma.

    A guarda do `[Event ` não é zelo: um índice de outra base aponta para o meio de um
    movetext, e sem ela isto devolveria meia partida com cara de partida inteira.
    """
    fh.seek(offset)
    primeira = fh.readline()
    if not primeira.startswith(b"[Event "):
        return None

    cabecalho: dict[str, str] = {}
    movetext: list[str] = []
    linha = primeira
    while linha:
        if linha.startswith(b"["):
            if movetext:
                break  # comecou a proxima partida
            casado = _RE_HEADER.match(linha.decode("utf-8", "replace").rstrip())
            if casado is not None and casado.group(1) in _KEPT_HEADERS:
                cabecalho[casado.group(1)] = casado.group(2)
        else:
            texto = linha.strip()
            if texto:
                movetext.append(texto.decode("utf-8", "replace"))
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

    Devolve vazio, e não levanta, quando não há índice, quando ele é de outra base ou quando é
    de um formato anterior: quem chama tem um caminho alternativo (a lista do cache), e um erro
    aqui tiraria os dois.
    """
    bases = [caminho for caminho in as_databases(databases) if caminho.is_file()]
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
                "O índice por nome está no formato %r e este programa lê o %d: ele não sabe de "
                "que arquivo é cada partida. Refaça com: cvoff-games --build-index",
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
        por_nome = {caminho.name: caminho for caminho in bases}
        arquivos = {
            int(identificador): por_nome[nome]
            for identificador, nome in conexao.execute("SELECT id, name FROM files")
            if nome in por_nome
        }

        procurados = [tuple(pair)] + ([(pair[1], pair[0])] if both_colors else [])
        chaves = [pair_hash(p) for p in procurados]  # type: ignore[arg-type]
        marcadores = ",".join("?" * len(chaves))
        achados = [
            (int(linha[1]), int(linha[0]))
            for linha in conexao.execute(
                f"SELECT offset, file FROM games WHERE pair IN ({marcadores}) LIMIT ?", (*chaves, limit)
            )
        ]
    finally:
        conexao.close()

    esperados = {frozenset(p) for p in procurados}
    partidas = []
    # Agrupado por arquivo: sao ate 40 leituras, e abrir e fechar o mesmo .pgn a cada uma delas
    # seria pagar o `open` por offset em vez de por base.
    for identificador in sorted({arquivo for arquivo, _ in achados}):
        caminho = arquivos.get(identificador)
        if caminho is None:
            logger.warning("O índice aponta para um arquivo que não está mais na pasta da base.")
            continue
        with caminho.open("rb") as fh:
            for arquivo, offset in achados:
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


def positions_of(games: Iterable[GameRecord], placement: str) -> list[tuple[GameRecord, int, bool]]:
    """Em quais das partidas aquela colocação aparece, e em que lance.

    O casamento continua sendo exato nas 64 casas -- o índice mudou *como se chega* às
    partidas, não o que conta como casamento.
    """
    achados = []
    for partida in games:
        for colocacao, lance, vez in partida.positions():
            if colocacao == placement:
                achados.append((partida, lance, vez))
                break
    return achados
