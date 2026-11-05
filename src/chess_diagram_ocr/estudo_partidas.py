"""Que partidas da base chegaram a esta posição, e o que dizer quando nenhuma resposta existe (S-287).

**O gesto mais usado do ChessBase, e o tabuleiro de estudo não o alcançava.** A maquinaria já estava
toda pronta -- `games_db.scan_by_positions` varre, `games_cache.PositionStore` guarda, e a S-72/S-73
usa as duas para preencher os headers do PGN exportado. Faltava a pergunta vir da sala.

## Por que isto lê o cache e nunca a base

`cvoff-games` documenta o custo: **~104 min em dez processos** para reproduzir os lances da base
inteira, e *"o custo é da PASSADA, não do livro"* -- perguntar por **uma** posição custa o mesmo que
perguntar por todas. Um botão que fizesse isso travaria a janela por uma hora.

O cache responde em milissegundos, e a consequência é uma limitação honesta que este módulo existe
para **dizer** em vez de esconder: ele só conhece as posições que já foram perguntadas, que são as
dos diagramas dos livros varridos. A raiz de um estudo costuma estar lá; a posição depois de três
lances de análise, não.

**Três estados e não dois**, e a diferença entre os dois primeiros é a que mais importa:

| estado | o que significa |
|---|---|
| `NAO_HA_BASE` | não há PGN em `pgn_database/` -- nada foi perguntado porque não há a quem |
| `NAO_PERGUNTADA` | a base existe e **esta posição nunca foi perguntada a ela** |
| `SEM_PARTIDA` | foi perguntada, e a base não tem nenhuma partida que passe por aqui |
| `ACHOU` | tem, e são estas |

Colapsar `NAO_PERGUNTADA` em `SEM_PARTIDA` diria "nenhuma partida chega aqui" sobre uma pergunta que
ninguém fez -- que é a forma de número enganoso que este projeto já cometeu e corrigiu (S-135).

## O que ele **não** faz, e por quê

Não devolve *os lances jogados a partir daqui e a frequência de cada um*, que é a segunda metade da
janela de aberturas do ChessBase. Não é escolha: `CachedPosition` guarda contagem e cabeçalhos, e
**não guarda a continuação** -- derivá-la exigiria reproduzir as partidas, que é a passada de uma
hora. Fica registrado como não feito, e não como esquecido.

Nada de `tkinter` aqui, e nada de `sqlite3` tampouco: a loja entra por `Protocol`, e o teste passa
um dicionário.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .games_cache import CachedPosition
from .games_db import GameRecord, PositionHit

__all__ = [
    "ACHOU",
    "NAO_HA_BASE",
    "NAO_PERGUNTADA",
    "SEM_PARTIDA",
    "Loja",
    "Resposta",
    "como_pgn",
    "consultar",
]

NAO_HA_BASE = "sem-base"
NAO_PERGUNTADA = "nao-perguntada"
SEM_PARTIDA = "sem-partida"
ACHOU = "achou"

COMO_PERGUNTAR = "cvoff-games --all"
"""O comando que faz a passada. Escrito aqui e não na aba, porque a frase que o cita é daqui."""


class Loja(Protocol):
    """O mínimo que este módulo usa de `games_cache.PositionStore`.

    `Protocol` e não o tipo concreto pela mesma razão de `ui/tokens.Estilo`: quem decide precisa ser
    afirmável sem abrir um SQLite, e o teste passa um objeto de três linhas.
    """

    def missing(self, targets: Iterable[str]) -> set[str]: ...

    def get(self, placement: str) -> CachedPosition: ...


@dataclass(frozen=True)
class Resposta:
    """O que a base disse sobre a posição, e a frase que a aba mostra."""

    estado: str
    frase: str
    partidas: tuple[PositionHit, ...] = ()
    total: int = 0
    """Quantas partidas a base tem. Maior que `len(partidas)` quando a posição é comum."""

    @property
    def truncada(self) -> bool:
        """A lista mostra menos partidas do que existem. Quem exibe **tem** de dizer isso."""
        return self.total > len(self.partidas)

    @property
    def achou(self) -> bool:
        return self.estado == ACHOU


def consultar(loja: Loja | None, placement: str, *, bases: Sequence[Path] = ()) -> Resposta:
    """A resposta da base para aquela colocação, com a frase pronta para o rodapé.

    `loja=None` é "não há cache aberto", que na prática é o mesmo que não haver base: a aba abre a
    loja quando abre o livro, e falhar ali já é falhar em silêncio por decisão de `open_store`.
    """
    colocacao = str(placement or "").strip().split()[0] if placement else ""
    if not colocacao:
        return Resposta(NAO_HA_BASE, "Não há posição para procurar.")

    if loja is None or not bases:
        return Resposta(
            NAO_HA_BASE,
            "Não há base de partidas em pgn_database/. Ponha os seus arquivos .pgn lá -- eles não "
            "saem da sua máquina e não entram no repositório.",
        )

    if colocacao in loja.missing([colocacao]):
        return Resposta(
            NAO_PERGUNTADA,
            "Esta posição ainda não foi perguntada à base. A varredura reproduz os lances da base "
            f"inteira de uma vez -- por isso ela é um comando e não um botão:  {COMO_PERGUNTAR}",
        )

    guardada = loja.get(colocacao)
    if guardada.count <= 0:
        return Resposta(SEM_PARTIDA, "Nenhuma partida da base chega a esta posição.")

    quantas = len(guardada.games)
    frase = f"{guardada.count} partida(s) da base chegam a esta posição"
    if guardada.count > quantas:
        frase += f"; a lista mostra as {quantas} guardadas"
    return Resposta(ACHOU, frase + ".", partidas=guardada.games, total=guardada.count)


def _valor_de_header(valor: str) -> str:
    r"""O valor de um header como o PGN o escreve: `"` e `\` viram sequência de escape.

    Não é zelo -- a base tem eventos com aspas dentro (`ch-URS "A" final`), e um header que não
    fecha faz o `chess.pgn` ler a partida seguinte como continuação desta.
    """
    return str(valor).replace("\\", "\\\\").replace('"', '\\"')


def como_pgn(partida: GameRecord) -> str:
    """A partida da base como texto PGN, pronta para `estudo.colar` (S-533).

    **Por que reconstruir em vez de recortar os bytes.** `GameRecord` já leu os headers e o
    movetext do arquivo, e o que a sala precisa é de um PGN -- não do trecho original: o recorte
    exigiria guardar o byte final de cada partida, que é uma coluna a mais em dez milhões de
    linhas para poupar esta montagem de dez linhas.

    **O `[FEN]` volta com o `[SetUp]` ao lado**, e os dois juntos: `setup_fen` mora fora de
    `headers` de propósito (ver `GameRecord`), e um `[FEN]` sem `[SetUp "1"]` é PGN que alguns
    leitores ignoram -- e ignorá-lo faz a solução de um estudo partir da posição inicial, onde o
    primeiro lance é ilegal e a partida vira uma linha vazia.
    """
    cabecalho = dict(partida.headers)
    if partida.setup_fen:
        cabecalho["SetUp"] = "1"
        cabecalho["FEN"] = partida.setup_fen
    linhas = [f'[{chave} "{_valor_de_header(valor)}"]' for chave, valor in cabecalho.items() if str(valor).strip()]
    return "\n".join(linhas) + "\n\n" + partida.movetext.strip() + "\n"
