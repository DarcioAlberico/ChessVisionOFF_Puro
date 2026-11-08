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

**Uma linha por colocação, e não um arquivo por acervo (S-140, item 2).** O artefato foi um
JSON até 2026-08-18, e ele respondia a pergunta certa pelo caminho errado: `json.loads` do
arquivo inteiro, na thread do Tk, **a cada troca de livro** -- para responder sobre as ~1.400
posições de um livro só. A 1.253 B/posição, os 34 livros do acervo projetam ~50 mil posições,
~63 MB de texto, ~4,2 s de parse e ~190 MB residentes, e o custo cresce com o acervo enquanto a
pergunta não cresce com nada. Agora é um SQLite com `placement` de chave primária, no padrão
que a S-87 já tinha pronto: abrir custa uma conexão, e trocar de livro custa as colocações
daquele livro.

**A trava e a refusão da S-113 não foram perdidas -- foram entregues a quem as faz melhor.** O
item existia porque duas passadas simultâneas se sobrescreviam: cada uma lia o dicionário
inteiro, e a última a gravar substituía o arquivo por um retrato tirado uma hora antes. Com uma
linha por colocação não há retrato para substituir: cada `update` escreve as suas linhas dentro
de uma transação, o SQLite serializa as duas gravações, e as posições das duas sobrevivem --
que é exatamente o que `_funde` fazia à mão, agora com atomicidade de verdade e sem o `.lock`
que podia sobrar de um processo morto.

**O fingerprint da base é a única guarda, e ela não é opcional.** Trocada a base, as contagens
guardadas deixam de ser verdade -- e a contagem é o que decide se preencher um header é honesto
(S-74). Um cache de uma base e uma varredura de outra produziriam procedência inventada, que é
pior que campo vazio, porque campo vazio ninguém confunde com dado conferido.

**Não bateu, não responde -- e não apaga (S-806).** Até a S-806 a guarda descartava o cache
inteiro na abertura, e "o conjunto parece diferente" chegava lá por caminhos que ninguém
escolheu: um `--census --database X`, que diz não abrir a base; um `--all` com um disco fora do
ar; um `stat` que falhou. Em 2026-10-18 foram ~9.810 linhas, ~56 minutos de varredura. Agora cada
linha guarda a impressão do conjunto que a respondeu (coluna `impressao`), e só é lida sob essa
impressão: a de outra base é ignorada, e volta a valer quando aquela base voltar. Apagar é um
gesto, `cvoff-games --limpar-cache`, e é o único `DELETE` do módulo.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .games_db import MAX_HITS_PER_POSITION, PositionHit, PositionIndex, as_databases, impressao_da_base

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_CACHE_PATH",
    "DEFAULT_STORE_PATH",
    "STORE_VERSION",
    "CachedPosition",
    "PositionCache",
    "PositionStore",
    "database_fingerprint",
    "open_store",
    "same_database",
    "stored_summary",
]

DEFAULT_STORE_PATH = DATA_DIR / "games_positions.sqlite"
"""Onde o cache mora. Em `data/`, com o resto do que é derivado e reconstruível."""

STORE_VERSION = 2
"""A 2 (S-806) pôs a impressão em cada linha. A 1 tinha a marca da base só em `meta`, e é
migrada na primeira abertura para gravar sem perder linha -- ver `_migra_da_versao_um`."""

DEFAULT_CACHE_PATH = DATA_DIR / "games_positions.json"
"""O artefato anterior, **lido uma vez e aposentado** -- ver `_migra_json`.

Ele não é um formato aceito: é um arquivo que existe no disco de quem já usou o programa, e
descartá-lo custaria a cada um dos dois usuários conhecidos uma varredura de ~56 minutos por
nada. A migração o lê, grava as linhas no SQLite e renomeia o arquivo -- depois disso não há
dois caminhos de leitura vivos, que é a regra que o `INDEX_VERSION` da S-140 (item 1) fixou."""

BUSY_TIMEOUT = 30.0
"""Segundos que uma gravação espera o SQLite liberar o arquivo.

Trinta, e não os dez da trava de conselho que isto substituiu, porque agora a espera é por uma
transação de milissegundos e não por um `.lock` que pode ser lixo de um processo morto: quem
espera aqui sempre tem alguém do outro lado terminando de gravar. E o que está em jogo é a
passada de ~56 min que produziu as linhas -- desistir dela para não esperar meio minuto seria
a troca ao contrário."""

_LOTE_CONSULTA = 400
"""Colocações por `SELECT ... IN (...)`. Abaixo do teto de variáveis de qualquer SQLite vivo.

O conjunto-alvo de um livro tem ~1.400 colocações e o do acervo ~40 mil; sem os pedaços, a
consulta que responde "o que falta perguntar" levantaria `too many SQL variables` justamente no
acervo inteiro, que é o caso que o `cvoff-games --all` roda."""


def database_fingerprint(databases: Path | Sequence[Path]) -> dict[str, Any]:
    """Nome e tamanho de **cada** base -- o bastante para notar que o conjunto mudou.

    Não é hash do conteúdo: são 19 GB, e lê-los para decidir se vale ler os 19 GB seria a
    piada do módulo. Tamanho erra no caso de uma base editada sem mudar o tamanho, que não é
    um caso que aconteça sem intenção.

    **Quem decide nome e tamanho é `games_db.impressao_da_base` (S-807)**, a mesma função do
    `index_fingerprint`. Aqui havia um `stat()` próprio, e ele dava tamanho 0 a todo membro de
    `.zip` -- o caminho do membro não existe no disco -- e nome sem o `.zip` na frente, então
    reescrever o membro não mudava nada e dois `.zip` com um `games.pgn` cada eram a mesma base.
    O tamanho que não lê é `None`, e não zero.

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
    impressoes = (impressao_da_base(caminho) for caminho in as_databases(databases))
    return {"files": [{"name": impressao.nome, "size": impressao.tamanho} for impressao in impressoes]}


def _arquivos(fingerprint: dict[str, Any]) -> list[dict[str, Any]]:
    """Os arquivos de uma marca, aceitando a forma anterior à S-93 (um arquivo solto)."""
    arquivos = fingerprint.get("files")
    if isinstance(arquivos, list):
        return [item for item in arquivos if isinstance(item, dict)]
    return [fingerprint] if "name" in fingerprint else []


def _chave(fingerprint: dict[str, Any]) -> str | None:
    """A marca como a chave gravada em cada linha: `nome:tamanho|...`. `None` se há desconhecido.

    **Só nome e tamanho entram**, e é o que não invalida os caches que já estão no disco: eles
    foram gravados com `mtime` dentro, e comparar o dicionário inteiro descartaria, na primeira
    execução depois da S-113, exatamente as varreduras que o item existe para deixar de perder.

    **Desconhecido não casa nem descasa (S-806).** Uma base cujo tamanho não leu não identifica
    conjunto nenhum: as linhas não são lidas sob ela, nada é gravado sob ela, e nada é apagado
    por causa dela. É a forma da `impressao_da_base` (S-807) e do `index_fingerprint`.
    """
    pedacos = []
    for item in _arquivos(fingerprint):
        tamanho = item.get("size", 0)
        if tamanho is None:
            return None
        pedacos.append(f"{item.get('name', '?')}:{int(tamanho)}")
    return "|".join(pedacos)


def _same_database(um: dict[str, Any], outro: dict[str, Any]) -> bool:
    """Duas marcas descrevem o mesmo conjunto de bases? Só nome e tamanho decidem (`_chave`)."""
    chave = _chave(um)
    return chave is not None and chave == _chave(outro)


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
    """As posições já perguntadas à base, **na memória**, com o fingerprint de quem respondeu.

    Responde as mesmas perguntas que o `PositionStore` e não tem disco por trás. Sobrou de
    propósito depois da S-140: é a forma que o JSON aposentado assume durante a migração, e é o
    que um teste de `games_census` monta em três linhas -- montar um SQLite para afirmar que
    uma contagem cai na faixa certa seria o instrumento maior que a medida.
    """

    fingerprint: dict[str, Any] = field(default_factory=dict)
    positions: dict[str, CachedPosition] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.positions)

    def get(self, placement: str) -> CachedPosition:
        """O que a base respondeu sobre uma colocação. Nunca perguntada devolve a vazia."""
        return self.positions.get(placement, _VAZIA)

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

        **Passada descartada não entra**, pela mesma razão do `PositionStore.update` (S-171):
        gravá-la registraria "a base não conhece" sobre o que ninguém procurou.
        """
        if not index.complete:
            logger.warning("A varredura não terminou; nada entrou no cache em memória.")
            return
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


def _pedacos(colocacoes: Sequence[str], tamanho: int = _LOTE_CONSULTA) -> Iterator[Sequence[str]]:
    for inicio in range(0, len(colocacoes), tamanho):
        yield colocacoes[inicio : inicio + tamanho]


class PositionStore:
    """As posições já perguntadas, uma linha por colocação, lidas **sob demanda**.

    Responde as mesmas perguntas que o `PositionCache` -- `get`, `missing`, `answered_of`,
    `to_index` -- e nenhuma delas lê o acervo inteiro: cada uma vira um `SELECT` sobre as
    colocações pedidas. É o que faz trocar de livro na Galeria custar o livro, e não o acervo.

    **Não é um dicionário, e a diferença aparece no `update`.** Escrever é uma transação por
    varredura, e não a substituição de um arquivo -- duas passadas simultâneas somam as linhas
    em vez de uma apagar a outra (ver o cabeçalho do módulo, S-113/S-140).

    **Toda pergunta é feita sob a impressão desta abertura (S-806).** As linhas de outro conjunto
    de bases estão no mesmo arquivo e não respondem aqui; com a impressão desconhecida (uma base
    cujo tamanho não leu), nenhuma responde e nada é gravado.
    """

    def __init__(self, path: Path, conexao: sqlite3.Connection, fingerprint: dict[str, Any]) -> None:
        self.path = path
        self.fingerprint = fingerprint
        self._conexao = conexao
        self._chave = _chave(fingerprint)
        # `None` nao casa com linha nenhuma: `impressao = NULL` e falso no SQL, e e o que se quer.
        self._sob = (self._chave,)

    @classmethod
    def in_memory(cls, fingerprint: dict[str, Any] | None = None) -> PositionStore:
        """Um cache que responde tudo e não guarda nada. O disco que falhou, e o teste.

        É para onde o `open_store` cai quando o arquivo não abre: a aba continua funcionando,
        e o que se perde é a memória entre execuções -- que é exatamente o que já se perderia.
        """
        return cls(Path(":memory:"), _conexao_em_memoria(), dict(fingerprint or {}))

    def matches(self, databases: Path | Sequence[Path]) -> bool:
        """Esta conexão responde sobre **esta** base? Só nome e tamanho decidem.

        Existe para quem mantém a conexão aberta por uma sessão inteira -- a Galeria -- poder
        perguntar de graça se ela ainda vale, em vez de reabrir o cache por precaução.
        """
        return _same_database(self.fingerprint, database_fingerprint(databases))

    # ------------------------------------------------------------------ leitura

    def __len__(self) -> int:
        (quantas,) = self._conexao.execute("SELECT count(*) FROM positions WHERE impressao = ?", self._sob).fetchone()
        return int(quantas)

    @property
    def guardadas(self) -> int:
        """Quantas linhas o arquivo tem, **de todas as impressões** -- o que `limpar` poderia apagar."""
        (quantas,) = self._conexao.execute("SELECT count(*) FROM positions").fetchone()
        return int(quantas)

    @property
    def answered(self) -> int:
        """Quantas das perguntadas a base conhece. O resto é `count == 0`."""
        (quantas,) = self._conexao.execute(
            "SELECT count(*) FROM positions WHERE impressao = ? AND count > 0", self._sob
        ).fetchone()
        return int(quantas)

    def answered_of(self, targets: Iterable[str]) -> int:
        """Idem, restrito às colocações pedidas -- o que o acervo aberto agora aproveita."""
        total = 0
        for pedaco in _pedacos(sorted(set(targets))):
            marcas = ",".join("?" * len(pedaco))
            (quantas,) = self._conexao.execute(
                f"SELECT count(*) FROM positions WHERE impressao = ? AND count > 0 AND placement IN ({marcas})",  # noqa: S608
                (*self._sob, *pedaco),
            ).fetchone()
            total += int(quantas)
        return total

    def missing(self, targets: Iterable[str]) -> set[str]:
        """As colocações que ainda não foram perguntadas -- o alvo da próxima varredura.

        É o método que transforma "varrer o acervo" em "varrer o que entrou desde a última
        vez". Um livro novo cujas posições já apareceram em outro livro não custa varredura
        nenhuma.
        """
        alvos = set(targets)
        conhecidas: set[str] = set()
        for pedaco in _pedacos(sorted(alvos)):
            marcas = ",".join("?" * len(pedaco))
            conhecidas.update(
                str(linha[0])
                for linha in self._conexao.execute(
                    f"SELECT placement FROM positions WHERE impressao = ? AND placement IN ({marcas})",  # noqa: S608
                    (*self._sob, *pedaco),
                )
            )
        return alvos - conhecidas

    def get(self, placement: str) -> CachedPosition:
        """O que a base respondeu sobre uma colocação. Nunca perguntada devolve a vazia.

        Uma consulta por diagrama é o caminho da tela, e ele é barato: chave primária, e o
        `WITHOUT ROWID` põe a resposta na mesma folha da chave (S-140, item 1, aqui de novo).
        """
        linha = self._conexao.execute(
            "SELECT count, games FROM positions WHERE impressao = ? AND placement = ?", (*self._sob, placement)
        ).fetchone()
        return _VAZIA if linha is None else _da_linha(linha)

    def to_index(self, targets: Iterable[str] | None = None) -> PositionIndex:
        """Devolve o que `match_positions` consome, sem tocar na base.

        É o caminho de reaplicar: os casamentos saem do disco com as mesmas contagens e as
        mesmas candidatas que a varredura produziu. `targets` limita ao livro pedido; `None`
        devolve tudo -- e `None` é o caso raro, porque quem pergunta pergunta por um livro.
        """
        indice = PositionIndex()
        if targets is None:
            for colocacao, contagem, jogos in self._conexao.execute(
                "SELECT placement, count, games FROM positions WHERE impressao = ? AND count > 0", self._sob
            ):
                _acrescenta(indice, str(colocacao), (contagem, jogos))
            return indice

        for pedaco in _pedacos(sorted(set(targets))):
            marcas = ",".join("?" * len(pedaco))
            for colocacao, contagem, jogos in self._conexao.execute(
                "SELECT placement, count, games FROM positions "  # noqa: S608
                f"WHERE impressao = ? AND count > 0 AND placement IN ({marcas})",
                (*self._sob, *pedaco),
            ):
                _acrescenta(indice, str(colocacao), (contagem, jogos))
        return indice

    # ------------------------------------------------------------------ gravação

    def update(self, index: PositionIndex, asked: Iterable[str]) -> int:
        """Grava o que a varredura respondeu **sobre tudo que ela foi perguntar**. Devolve quantas.

        `asked` é o conjunto-alvo inteiro, e não as chaves de `index.hits`: as posições sem
        resposta precisam ficar registradas como perguntadas, senão voltam ao alvo de toda
        varredura futura -- e elas são a maioria (1.922 de 3.563 no acervo medido).

        **`INSERT OR REPLACE`, e não `OR IGNORE`.** Duas varreduras da mesma base sobre a mesma
        posição dão a mesma resposta -- é o que o fingerprint garante --, então reescrever é
        inócuo; e o dia em que não for, a resposta que vale é a desta passada, que acabou de
        ler a base. Era essa a regra do `_funde`, e ela não mudou de lado.

        **Uma passada descartada não grava nada, e a guarda é aqui** (S-171). `index.complete`
        falso significa "esta passada não viu a base inteira" -- cancelada, ou com um processo
        morto no meio. Gravá-la seria registrar `count = 0` sobre o conjunto-alvo inteiro, ou
        seja **"a base não conhece"** sobre milhares de colocações que ninguém chegou a
        procurar; e, pela decisão da S-84, perguntado é perguntado: elas nunca mais voltariam ao
        alvo de varredura nenhuma. É a pior forma de corrupção que este arquivo admite, porque
        ela se parece com trabalho feito.

        A guarda mora aqui, e não em cada chamador, porque quem chama não deve precisar lembrar
        de perguntar -- e porque houve dois chamadores e só um lembrava.
        """
        if not index.complete:
            logger.warning(
                "A varredura não terminou; nada foi gravado no cache. As %d colocação(ões) "
                "continuam por perguntar.",
                len(set(asked)),
            )
            return 0
        if self._chave is None:
            # Uma base cujo tamanho nao leu: a resposta nao teria conjunto a que pertencer, e
            # nunca mais seria lida -- gravar seria encher o arquivo de linhas mortas (S-806).
            logger.warning("Uma das bases não pôde ser medida (%s); nada foi gravado no cache.", _descreve(self.fingerprint))
            return 0
        linhas = [
            (
                self._chave,
                colocacao,
                int(index.counts.get(colocacao, len(index.hits.get(colocacao, [])))),
                json.dumps(
                    [jogo.to_dict() for jogo in index.hits.get(colocacao, [])[:MAX_HITS_PER_POSITION]],
                    ensure_ascii=False,
                ),
            )
            for colocacao in asked
        ]
        if not linhas:
            return 0
        with self._conexao:
            self._conexao.executemany(_GRAVA_LINHA, linhas)
        return len(linhas)

    def limpar(self) -> int:
        """Apaga as linhas de **outra** impressão e devolve quantas. O único `DELETE` do módulo.

        É o gesto explícito que o `open_store` deixou de fazer sozinho (S-806): `cvoff-games
        --limpar-cache`. Com a impressão desconhecida recusa, porque "tudo que não é desta base"
        seria o arquivo inteiro.
        """
        if self._chave is None:
            logger.warning("Limpeza recusada: uma das bases não pôde ser medida (%s).", _descreve(self.fingerprint))
            return 0
        with self._conexao:
            cursor = self._conexao.execute("DELETE FROM positions WHERE impressao <> ?", self._sob)
        return int(cursor.rowcount)

    def close(self) -> None:
        self._conexao.close()

    def __enter__(self) -> PositionStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _da_linha(linha: Sequence[Any]) -> CachedPosition:
    """`(count, games)` como o SQLite os devolve, virando a resposta que o resto do projeto usa."""
    try:
        crus = json.loads(linha[1]) if linha[1] else []
    except json.JSONDecodeError:
        crus = []
    return CachedPosition(
        count=int(linha[0]), games=tuple(PositionHit.from_dict(item) for item in crus)
    )


def _acrescenta(indice: PositionIndex, colocacao: str, linha: Sequence[Any]) -> None:
    guardada = _da_linha(linha)
    indice.hits[colocacao] = list(guardada.games)
    indice.counts[colocacao] = guardada.count


def open_store(
    path: Path = DEFAULT_STORE_PATH,
    *,
    database: Path | Sequence[Path] | None = None,
    de_outra_thread: bool = False,
    somente_leitura: bool = False,
) -> PositionStore:
    """Abre o cache de posições, criando-o se não houver. **Nunca levanta por causa do disco.**

    **Nunca apaga linha (S-806).** As perguntas são feitas sob a impressão de `database`, e as
    linhas de outro conjunto de bases ficam no arquivo sem responder. Quem só lê -- o censo, a
    sala de estudo, o aviso da janela -- passa `somente_leitura`: a conexão é `mode=ro`, o arquivo
    que não existe não é criado (responde vazio), e o de versão anterior é lido sem ser migrado.

    `de_outra_thread` é para quem abre o cache numa thread de trabalho e o **usa** na thread da
    janela (OCR_UI passo 15: abrir custou 25–60 ms medidos no disco frio, na thread da
    interface). O `sqlite3` recusa por padrão uma conexão usada por outra thread; a conexão
    continua sendo de uma thread por vez -- a da janela, depois de entregue --, só não é a que a
    criou. Quem a usa de duas threads ao mesmo tempo continua errado, com ou sem este parâmetro.

    **Falhar para o lado do vazio é a decisão certa aqui**, e pelo mesmo motivo do
    `load_annotations`: o vazio significa "varra", que é o comportamento anterior ao módulo. Um
    cache ilegível que derrubasse o comando trocaria uma varredura por um erro. O caso extremo
    -- o arquivo existe e não é um SQLite -- cai num cache em memória, que responde tudo e não
    guarda nada; a alternativa seria apagar um arquivo do usuário para poder continuar.

    Trocada a base, as linhas guardadas deixam de responder, e não são apagadas: as contagens
    de outra base não são um cache parcial, são resposta errada -- mas são a resposta certa para
    aquela base, quando ela voltar (ver o cabeçalho do módulo).
    """
    caminho = Path(path)
    atual = database_fingerprint(database) if database is not None else {}
    if somente_leitura:
        return _abre_para_ler(caminho, atual, de_outra_thread)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        criar = not caminho.exists()
        conexao = sqlite3.connect(
            str(caminho), timeout=BUSY_TIMEOUT, check_same_thread=not de_outra_thread
        )
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Cache de posições ilegível em %s (%s); seguindo em memória.", caminho, exc)
        return PositionStore.in_memory(atual)

    try:
        _prepara(conexao)
        # So o artefato padrao migra o artefato padrao. Um `--cache` apontado para outro lugar
        # nao pode puxar -- nem renomear -- o JSON de `data/`: quem pede um cache separado esta
        # justamente pedindo para nao mexer no do acervo.
        if criar and caminho == DEFAULT_STORE_PATH:
            _migra_json(conexao, DEFAULT_CACHE_PATH, atual)
    except sqlite3.Error as exc:
        logger.warning("Cache de posições ilegível em %s (%s); seguindo em memória.", caminho, exc)
        conexao.close()
        return PositionStore.in_memory(atual)

    loja = PositionStore(caminho, conexao, atual)
    logger.info("Cache de posições: %d perguntadas, %d com resposta.", len(loja), loja.answered)
    return loja


def _abre_para_ler(caminho: Path, atual: dict[str, Any], de_outra_thread: bool) -> PositionStore:
    """A porta de quem só lê: `mode=ro`, sem criar, sem migrar. Ilegível responde vazio."""
    if not caminho.exists():
        return PositionStore.in_memory(atual)
    conexao: sqlite3.Connection | None = None
    try:
        conexao = sqlite3.connect(
            f"file:{caminho.as_posix()}?mode=ro", uri=True, timeout=BUSY_TIMEOUT, check_same_thread=not de_outra_thread
        )
        if _versao_do_esquema(conexao) == 1:
            _le_a_versao_um(conexao)
        conexao.execute("SELECT count(*) FROM positions").fetchone()
    except sqlite3.Error as exc:
        logger.warning("Cache de posições ilegível em %s (%s); respondendo vazio.", caminho, exc)
        if conexao is not None:
            conexao.close()
        return PositionStore.in_memory(atual)
    return PositionStore(caminho, conexao, atual)


_CRIA_POSICOES = (
    "CREATE TABLE IF NOT EXISTS {tabela} ("
    "impressao TEXT NOT NULL, placement TEXT NOT NULL, count INTEGER NOT NULL, games TEXT NOT NULL, "
    "PRIMARY KEY (impressao, placement)"
    ") WITHOUT ROWID"
)
"""O esquema da S-140 com a impressão na frente da chave (S-806).

A colocação continua sendo a árvore e a resposta continua viajando na folha; a impressão vem antes
porque toda pergunta é feita sob uma impressão só, e com ela na frente a contagem de uma base e a
limpeza das outras são faixas contíguas da mesma árvore."""

_GRAVA_LINHA = "INSERT OR REPLACE INTO positions (impressao, placement, count, games) VALUES (?, ?, ?, ?)"


def _prepara(conexao: sqlite3.Connection) -> None:
    """As tabelas na versão de agora. Uma da versão 1 é migrada antes, sem perder linha."""
    if _versao_do_esquema(conexao) == 1:
        _migra_da_versao_um(conexao)
    conexao.execute(_CRIA_POSICOES.format(tabela="positions"))
    conexao.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conexao.execute("INSERT OR IGNORE INTO meta VALUES ('version', ?)", (str(STORE_VERSION),))
    conexao.commit()


def _versao_do_esquema(conexao: sqlite3.Connection) -> int:
    """0 sem tabela, 1 sem a coluna `impressao`, 2 com ela. Lido do esquema, e não de `meta`."""
    colunas = {str(linha[1]) for linha in conexao.execute("PRAGMA main.table_info(positions)")}
    if not colunas:
        return 0
    return 2 if "impressao" in colunas else 1


def _chave_da_versao_um(conexao: sqlite3.Connection) -> str:
    """A impressão das linhas de um cache da versão 1: a marca que ele guardava em `meta`.

    `"?"` quando a marca tinha tamanho desconhecido: não casa com impressão nenhuma, e as linhas
    ficam guardadas em vez de sumir."""
    chave = _chave(_fingerprint_gravado(conexao))
    return "?" if chave is None else chave


def _migra_da_versao_um(conexao: sqlite3.Connection) -> None:
    """Põe a impressão gravada em `meta` em cada linha, numa transação. Nenhuma linha se perde.

    É a única troca de tabela do módulo: cria a nova, copia, e só então derruba a antiga, tudo
    dentro do mesmo `BEGIN IMMEDIATE` -- um processo morto no meio deixa a versão 1 intacta. O
    esquema é relido **depois** de tomar a trava, porque um segundo processo que abrisse ao mesmo
    tempo encontraria a tabela já migrada, e copiá-la de novo com a chave de `meta` (já apagada)
    trocaria a impressão de todas as linhas.
    """
    conexao.execute("BEGIN IMMEDIATE")
    try:
        if _versao_do_esquema(conexao) != 1:
            conexao.rollback()
            return
        chave = _chave_da_versao_um(conexao)
        conexao.execute("DROP TABLE IF EXISTS positions_v2")
        conexao.execute(_CRIA_POSICOES.format(tabela="positions_v2"))
        conexao.execute(
            "INSERT INTO positions_v2 (impressao, placement, count, games) "
            "SELECT ?, placement, count, games FROM positions",
            (chave,),
        )
        conexao.execute("DROP TABLE positions")
        conexao.execute("ALTER TABLE positions_v2 RENAME TO positions")
        conexao.execute("DELETE FROM meta WHERE key = 'database'")
        conexao.execute("INSERT OR REPLACE INTO meta VALUES ('version', ?)", (str(STORE_VERSION),))
        conexao.commit()
    except sqlite3.Error:
        conexao.rollback()
        raise
    logger.info("Cache de posições migrado para a versão %d: cada linha leva agora a impressão da base.", STORE_VERSION)


def _le_a_versao_um(conexao: sqlite3.Connection) -> None:
    """Uma conexão só de leitura sobre a versão 1 enxerga o esquema de agora, sem gravar nada.

    Uma vista temporária chamada `positions` -- o `temp` vem antes do `main` na resolução de nomes
    do SQLite -- põe a impressão de `meta` como coluna constante. Ela mora no banco temporário da
    conexão, e o arquivo não é tocado: quem só lê não migra.
    """
    literal = _chave_da_versao_um(conexao).replace("'", "''")
    conexao.execute(
        "CREATE TEMP VIEW positions AS "  # noqa: S608 - o literal e a marca gravada, escapada acima
        f"SELECT '{literal}' AS impressao, placement, count, games FROM main.positions"
    )


def _conexao_em_memoria() -> sqlite3.Connection:
    conexao = sqlite3.connect(":memory:")
    _prepara(conexao)
    return conexao


def _fingerprint_gravado(conexao: sqlite3.Connection) -> dict[str, Any]:
    linha = conexao.execute("SELECT value FROM meta WHERE key = 'database'").fetchone()
    if linha is None:
        return {}
    try:
        marca = json.loads(linha[0])
    except json.JSONDecodeError:
        return {}
    return marca if isinstance(marca, dict) else {}


def stored_summary(
    path: Path = DEFAULT_STORE_PATH, *, database: Path | Sequence[Path] | None = None
) -> tuple[int, int]:
    """Quantas posições valem para `database`, e quantas o arquivo guarda ao todo. Só lê.

    Existe para quem **avisa antes** -- a janela, ao perguntar qual base usar: "N continuam
    valendo", ou "as N guardadas são de outro conjunto". Desde a S-806 nada é descartado ao abrir,
    e o aviso diz o que a busca vai aproveitar, não o que ela vai apagar.

    Nunca levanta, pela mesma razão do `open_store`: um cache ilegível é "não há cache", e o
    caminho de quem não tem cache é varrer -- que é o comportamento anterior ao módulo.
    """
    with open_store(path, database=database, somente_leitura=True) as loja:
        return len(loja), loja.guardadas


def same_database(um: dict[str, Any], outro: dict[str, Any]) -> bool:
    """Duas marcas descrevem o mesmo conjunto de bases? O critério da guarda, exposto.

    A regra já existia (`_same_database`) e era privada porque só `open_store` decidia com ela.
    Quem compara marcas por fora precisa da **mesma** regra: um aviso que dissesse "vale" onde a
    guarda não deixa responder ensinaria a pessoa a ignorar o aviso.
    """
    return _same_database(um, outro)


def _descreve(fingerprint: dict[str, Any]) -> str:
    """A marca da base como uma linha legível, para o aviso dizer *qual* base era.

    Aceita a forma anterior à S-93 (um arquivo solto) porque é justamente ela que vai aparecer
    no aviso de quem tem um cache antigo -- e um aviso que imprimisse `None` sobre a base que não
    responde não explicaria nada.
    """

    def _peso(tamanho: Any) -> str:
        return "tamanho desconhecido" if tamanho is None else f"{tamanho} bytes"

    return ", ".join(f"{item.get('name', '?')} ({_peso(item.get('size', 0))})" for item in _arquivos(fingerprint)) or "nada"


def _migra_json(conexao: sqlite3.Connection, origem: Path, fingerprint: dict[str, Any]) -> int:
    """Traz o JSON da S-84 para dentro do SQLite, uma vez, e aposenta o arquivo. Devolve quantas.

    **Roda só quando o SQLite acabou de ser criado**, que é a única vez em que ela pode não
    apagar trabalho: com o banco já em pé, o JSON que sobrou no disco é mais velho que ele.

    As linhas entram sob a impressão **do JSON**, e não a de agora (S-806): as de outra base não
    respondem por esta -- contagem de outra base é resposta errada --, e ficam guardadas para
    quando aquela base voltar, como qualquer outra linha do cache.
    """
    if not origem.exists():
        return 0
    try:
        dados = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Cache de posições anterior ilegível em %s (%s); ignorado.", origem, exc)
        return 0

    antigo = PositionCache.from_dict(dados)
    chave = _chave(antigo.fingerprint or fingerprint)
    if chave is None:
        logger.warning("O cache anterior em %s não diz de que base é; ignorado.", origem)
        return 0
    if antigo.fingerprint and fingerprint and not _same_database(antigo.fingerprint, fingerprint):
        logger.warning(
            "O cache anterior é de %s e a base agora é %s: as posições dele entram guardadas sob "
            "aquela base, e não respondem por esta.",
            _descreve(antigo.fingerprint),
            _descreve(fingerprint),
        )

    with conexao:
        conexao.executemany(
            _GRAVA_LINHA,
            [
                (
                    chave,
                    colocacao,
                    guardada.count,
                    json.dumps([jogo.to_dict() for jogo in guardada.games], ensure_ascii=False),
                )
                for colocacao, guardada in antigo.positions.items()
            ],
        )
    aposentado = origem.with_suffix(origem.suffix + ".migrado")
    try:
        origem.replace(aposentado)
    except OSError as exc:  # pragma: no cover - disco somente-leitura
        logger.warning("Não foi possível renomear %s (%s); ele será ignorado.", origem, exc)
    logger.info(
        "Cache de posições: %d posição(ões) migradas do JSON anterior; ele virou %s.",
        len(antigo.positions),
        aposentado.name,
    )
    return len(antigo.positions)
