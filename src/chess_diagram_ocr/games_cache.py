"""O que a base respondeu, guardado por **posição** e não por livro (S-84).

**A chave certa é a colocação, porque é ela que a base responde.** O livro é só quem pergunta:
duas obras que mostrem a mesma posição -- e elas mostram, os clássicos circulam entre livros --
recebem a mesma resposta, e a varredura não deveria ser paga duas vezes por isso. O artefato
anterior (`--save-matches`, S-73) era indexado por livro, e com ele um livro novo custava a
passada inteira mesmo que metade das posições dele já tivesse sido perguntada.

**O que este arquivo compra, em minutos.** A varredura por posição custa ~30 min depois da
S-85, e nada nela depende do que se faz com o resultado. Separadas as duas coisas:

| operação | antes | com o cache |
|---|---|---|
| reaplicar com outro `--max-games` | ~30 min | segundos |
| reaplicar depois de corrigir a regra de preenchimento | ~30 min | segundos |
| abrir a lista de candidatas de um diagrama | impossível | leitura de arquivo |
| varrer um livro novo cujas posições já foram perguntadas | ~30 min | segundos |

**A pergunta é guardada, não só a resposta.** Uma posição que a base não conhece precisa
constar do arquivo como *perguntada e sem resposta* -- senão ela volta para o conjunto-alvo de
toda varredura futura, para sempre. No acervo medido isso é a maioria: 1.922 dos 3.563
diagramas não casaram, e são justamente eles que reapareceriam.

**O fingerprint da base é a única guarda, e ela não é opcional.** Trocada a base, as contagens
guardadas deixam de ser verdade -- e a contagem é o que decide se preencher um header é honesto
(S-74). Um cache de uma base e uma varredura de outra produziriam procedência inventada, que é
pior que campo vazio, porque campo vazio ninguém confunde com dado conferido. Não bateu,
descarta inteiro: reconstruir custa uma varredura, e confiar no que não se pode conferir custa
o valor da ferramenta.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .config import PROJECT_ROOT
from .games_db import MAX_HITS_PER_POSITION, PositionHit, PositionIndex, as_databases

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_CACHE_PATH",
    "CachedPosition",
    "PositionCache",
    "database_fingerprint",
    "load_cache",
    "save_cache",
]

DEFAULT_CACHE_PATH = PROJECT_ROOT / "data" / "games_positions.json"
"""Onde o cache mora. Em `data/`, com o resto do que é derivado e reconstruível."""

CACHE_VERSION = 1

LOCK_TIMEOUT = 10.0
"""Segundos que uma gravação espera pela trava antes de gravar sem ela (S-113).

Dez porque a gravação em si é de milissegundos -- ler um JSON, fundir dois dicionários e
renomear -- e dez segundos já são duas ordens de grandeza acima do pior caso honesto. Além
disso o mais provável é que a trava seja lixo de um processo morto, e esperar mais seria
punir quem chegou depois."""


def database_fingerprint(databases: Path | Sequence[Path]) -> dict[str, Any]:
    """Nome e tamanho de **cada** base -- o bastante para notar que o conjunto mudou.

    Não é hash do conteúdo: são 19 GB, e lê-los para decidir se vale ler os 19 GB seria a
    piada do módulo. Tamanho erra no caso de uma base editada sem mudar o tamanho, que não é
    um caso que aconteça sem intenção.

    **O `mtime` saiu na S-113, e é o item.** Ele estava aqui e não em `index_fingerprint`
    (`games_index.py`), que sempre usou só nome e tamanho -- duas regras para a mesma pergunta,
    e a mais estrita descartava o trabalho. Copiar a pasta de bases, um sync de nuvem ou um
    antivírus que reescreve o carimbo mudam o `mtime` sem tocar num byte do conteúdo, e isso
    jogava fora **56 minutos** de varredura por posição sem que nada tivesse mudado.

    **Uma lista, e não um arquivo só, desde a S-93**, e a diferença não é cosmética: acrescentar
    um `.pgn` à pasta muda as contagens de *todas* as posições já perguntadas -- a mesma posição
    que estava em uma partida pode estar em três. Um cache que sobrevivesse a isso responderia
    "partida única" sobre uma base que tem quatro, e é a contagem que autoriza preencher header.
    """
    arquivos = []
    for caminho in as_databases(databases):
        try:
            arquivos.append({"name": caminho.name, "size": caminho.stat().st_size})
        except OSError:
            arquivos.append({"name": caminho.name, "size": 0})
    return {"files": arquivos}


def _same_database(um: dict[str, Any], outro: dict[str, Any]) -> bool:
    """Duas marcas descrevem o mesmo conjunto de bases? Só nome e tamanho decidem.

    Compara campo a campo em vez de `==` sobre o dicionário **para não invalidar os caches que
    já estão no disco**: eles foram gravados com `mtime` dentro, e uma igualdade literal
    descartaria, na primeira execução depois da S-113, exatamente as varreduras que o item
    existe para deixar de perder.
    """

    def _marcas(fingerprint: dict[str, Any]) -> list[tuple[str, int]]:
        arquivos = fingerprint.get("files")
        if not isinstance(arquivos, list):
            arquivos = [fingerprint]
        return [(str(item.get("name", "?")), int(item.get("size", 0))) for item in arquivos]

    return _marcas(um) == _marcas(outro)


@dataclass(frozen=True)
class CachedPosition:
    """O que a base respondeu sobre uma colocação: quantas partidas, e quais delas."""

    count: int = 0
    """Quantas partidas da base contêm a posição. **Zero é resposta**, não ausência: significa
    que a pergunta foi feita e a base não conhece a posição."""

    games: tuple[PositionHit, ...] = ()
    """As candidatas guardadas, até `MAX_HITS_PER_POSITION`. Menos que `count` quando a posição
    é comum -- e é por isso que os dois campos existem separados."""

    @property
    def truncated(self) -> bool:
        """A lista mostra menos partidas do que existem. Quem exibe tem de dizer isso."""
        return self.count > len(self.games)

    def to_dict(self) -> dict[str, Any]:
        return {"count": self.count, "games": [jogo.to_dict() for jogo in self.games]}

    @classmethod
    def from_dict(cls, dados: Any) -> CachedPosition:
        if not isinstance(dados, dict):
            return cls()
        jogos = tuple(PositionHit.from_dict(item) for item in (dados.get("games") or []))
        return cls(count=int(dados.get("count", len(jogos))), games=jogos)


_VAZIA = CachedPosition()
"""A resposta de quem nunca foi perguntado, para o `get` não precisar de dois ramos."""


@dataclass
class PositionCache:
    """As posições já perguntadas à base, com o fingerprint de qual base respondeu."""

    fingerprint: dict[str, Any] = field(default_factory=dict)
    positions: dict[str, CachedPosition] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.positions)

    @property
    def answered(self) -> int:
        """Quantas das perguntadas a base conhece. O resto é `count == 0`."""
        return sum(1 for guardada in self.positions.values() if guardada.count)

    def answered_of(self, targets: Iterable[str]) -> int:
        """Idem, restrito às colocações pedidas -- o que o acervo aberto agora aproveita."""
        return sum(1 for colocacao in set(targets) if self.positions.get(colocacao, _VAZIA).count)

    def missing(self, targets: Iterable[str]) -> set[str]:
        """As colocações que ainda não foram perguntadas -- o alvo da próxima varredura.

        É o método que transforma "varrer o acervo" em "varrer o que entrou desde a última
        vez". Um livro novo cujas posições já apareceram em outro livro não custa varredura
        nenhuma.
        """
        return {colocacao for colocacao in targets if colocacao not in self.positions}

    def update(self, index: PositionIndex, asked: Iterable[str]) -> None:
        """Grava o que a varredura respondeu **sobre tudo que ela foi perguntar**.

        `asked` é o conjunto-alvo inteiro, e não as chaves de `index.hits`: as posições sem
        resposta precisam ficar registradas como perguntadas, senão voltam ao alvo de toda
        varredura futura -- e elas são a maioria (1.922 de 3.563 no acervo medido).
        """
        for colocacao in asked:
            achadas = index.hits.get(colocacao, [])
            self.positions[colocacao] = CachedPosition(
                count=index.counts.get(colocacao, len(achadas)),
                games=tuple(achadas[:MAX_HITS_PER_POSITION]),
            )

    def to_index(self, targets: Iterable[str] | None = None) -> PositionIndex:
        """Devolve o que `match_positions` consome, sem tocar na base.

        É o caminho de reaplicar: os casamentos saem do disco com as mesmas contagens e as
        mesmas candidatas que a varredura produziu. `targets` limita ao livro pedido; `None`
        devolve tudo que o cache conhece.
        """
        indice = PositionIndex()
        chaves = self.positions.keys() if targets is None else (c for c in targets if c in self.positions)
        for colocacao in chaves:
            guardada = self.positions[colocacao]
            if not guardada.count:
                continue
            indice.hits[colocacao] = list(guardada.games)
            indice.counts[colocacao] = guardada.count
        return indice

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CACHE_VERSION,
            "database": self.fingerprint,
            "positions": {
                colocacao: guardada.to_dict() for colocacao, guardada in sorted(self.positions.items())
            },
        }

    @classmethod
    def from_dict(cls, dados: Any) -> PositionCache:
        if not isinstance(dados, dict):
            return cls()
        return cls(
            fingerprint=dict(dados.get("database") or {}),
            positions={
                str(colocacao): CachedPosition.from_dict(valor)
                for colocacao, valor in (dados.get("positions") or {}).items()
            },
        )


def load_cache(
    path: Path = DEFAULT_CACHE_PATH, *, database: Path | Sequence[Path] | None = None
) -> PositionCache:
    """Lê o cache, ou devolve um vazio -- inclusive quando a base não é a mesma.

    **Falhar para o lado do vazio é a decisão certa aqui**, e pelo mesmo motivo do
    `load_annotations`: o vazio significa "varra", que é o comportamento anterior ao módulo.
    Um cache ilegível que derrubasse o comando trocaria uma varredura por um erro.
    """
    cache = _read_cache(Path(path))
    if cache is None:
        return PositionCache()

    if database is not None:
        atual = database_fingerprint(database)
        if cache.fingerprint and not _same_database(cache.fingerprint, atual):
            logger.warning(
                "O cache foi feito com %s e a base de agora é %s: as contagens guardadas "
                "deixaram de valer, e o cache será refeito.",
                _descreve(cache.fingerprint),
                _descreve(atual),
            )
            return PositionCache(fingerprint=atual)
        cache.fingerprint = atual
    logger.info("Cache de posições: %d perguntadas, %d com resposta.", len(cache), cache.answered)
    return cache


def _read_cache(caminho: Path) -> PositionCache | None:
    """O arquivo como está, sem conferir base nenhuma. `None` quando não há o que ler.

    Separado do `load_cache` porque a gravação precisa reler o disco (ver `save_cache`) e não
    pode revalidar o fingerprint nem repetir o log de abertura -- ela não está abrindo o cache,
    está conferindo se alguém escreveu nele enquanto a varredura rodava.
    """
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Cache de posições ilegível em %s (%s); seguindo sem ele.", caminho, exc)
        return None
    if int(dados.get("version", 0)) != CACHE_VERSION:
        logger.warning("Cache de posições em versão %r; será refeito.", dados.get("version"))
        return None
    return PositionCache.from_dict(dados)


def _descreve(fingerprint: dict[str, Any]) -> str:
    """A marca da base como uma linha legível, para o aviso dizer *qual* base era.

    Aceita a forma anterior à S-93 (um arquivo solto) porque é justamente ela que vai aparecer
    no aviso de quem tem um cache antigo -- e um aviso que imprimisse `None` sobre o cache que
    está sendo descartado não explicaria nada.
    """
    arquivos = fingerprint.get("files")
    if not isinstance(arquivos, list):
        arquivos = [fingerprint]
    return ", ".join(f"{item.get('name', '?')} ({item.get('size', 0)} bytes)" for item in arquivos) or "nada"


@contextmanager
def _exclusive(caminho: Path, *, timeout: float = LOCK_TIMEOUT) -> Iterator[bool]:
    """Trava de conselho por arquivo vizinho. Devolve se conseguiu -- e **nunca bloqueia**.

    **A correção mora na refusão, não aqui.** Fundir é idempotente e comutativo: dois
    processos que gravem fora de ordem chegam ao mesmo arquivo. A trava só estreita a janela
    entre reler e substituir, e por isso ela pode desistir: preferir gravar sem trava a
    travar uma varredura de meia hora atrás de um `.lock` que sobrou de um processo morto.

    A limpeza é por idade, e não por PID: um `.lock` mais velho que o timeout é lixo de um
    processo que não existe mais, e mantê-lo faria toda gravação seguinte pagar a espera
    inteira. Sistema de arquivos sem `O_EXCL` cai no mesmo caminho de "segue sem trava".
    """
    trava = caminho.with_name(caminho.name + ".lock")
    descritor: int | None = None
    limite = time.monotonic() + timeout
    while True:
        try:
            trava.parent.mkdir(parents=True, exist_ok=True)
            descritor = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= limite:
                _descarta_trava_velha(trava, timeout)
                logger.warning("Trava do cache de posições ocupada por %.0f s; gravando sem ela.", timeout)
                break
            time.sleep(0.05)
        except OSError as exc:
            logger.debug("Sem trava para o cache de posições (%s); gravando assim mesmo.", exc)
            break
    try:
        yield descritor is not None
    finally:
        if descritor is not None:
            os.close(descritor)
            trava.unlink(missing_ok=True)


def _descarta_trava_velha(trava: Path, timeout: float) -> None:
    try:
        if time.time() - trava.stat().st_mtime > timeout:
            trava.unlink(missing_ok=True)
    except OSError:
        pass


def save_cache(cache: PositionCache, path: Path = DEFAULT_CACHE_PATH) -> Path:
    """Relê o disco, funde e grava de forma atômica (S-25 + S-113). Devolve o caminho.

    **A releitura é o item.** A Galeria lê o cache antes de varrer (~56 min, 8.034 alvos) e
    grava no fim *o objeto lido lá atrás*; `cvoff-games` faz igual. O fluxo que o próprio
    README sugere -- deixar `cvoff-games --all` rodando enquanto se anota um livro na janela --
    **perdia uma das duas passadas**: sem erro, sem log, sem nada na tela, porque a segunda a
    terminar sobrescrevia a primeira com um retrato tirado uma hora antes.

    **A fusão é segura porque a chave é a colocação e a resposta é da mesma base.** Duas
    varreduras da mesma base sobre a mesma posição dão a mesma contagem e as mesmas candidatas
    -- é o que o fingerprint garante. Marca diferente no disco não é conflito a resolver, é
    resposta de outra base: essa não entra, e a nossa vale.

    Serve também ao caso de a máquina cair no meio: o que já estava gravado sobrevive à
    gravação seguinte em vez de ser apagado por ela.
    """
    caminho = Path(path)
    with _exclusive(caminho):
        disco = _read_cache(caminho)
        if disco is not None:
            _funde(cache, disco)
        atomic_write_json(caminho, cache.to_dict(), indent=1)
    return caminho


def _funde(cache: PositionCache, disco: PositionCache) -> int:
    """Traz para `cache` o que o disco tem e ele não. Devolve quantas posições entraram."""
    if cache.fingerprint and disco.fingerprint and not _same_database(cache.fingerprint, disco.fingerprint):
        logger.warning(
            "O cache no disco é de %s e esta gravação é de %s: as posições dele não entram.",
            _descreve(disco.fingerprint),
            _descreve(cache.fingerprint),
        )
        return 0
    novas = {
        colocacao: guardada
        for colocacao, guardada in disco.positions.items()
        if colocacao not in cache.positions
    }
    if novas:
        # Log em `info` e não `debug`: a passada de 56 min que **quase** se perdeu é
        # exatamente o que ninguém veria acontecer, e a linha é o rastro de que não se perdeu.
        logger.info("Cache de posições: %d posição(ões) gravadas por outro processo, preservadas.", len(novas))
        cache.positions.update(novas)
    return len(novas)
