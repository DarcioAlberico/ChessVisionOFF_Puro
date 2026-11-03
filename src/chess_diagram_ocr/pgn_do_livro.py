"""O PGN que vem com o livro: lido inteiro, e cada nó da árvore achável pela posição (S-585 a S-587).

**O que este arquivo resolve.** Livro digital costuma vir com o `.pgn` das partidas e linhas do autor
-- uma partida por seção do capítulo, com a árvore inteira de variantes. Cada diagrama do PDF é um
nó dessa árvore. Ter o nó é ter a FEN exata, o lado a jogar (que a imagem não diz) e a análise do
autor a partir dali. Medido no Harikrishna (*Beat the French Defence with 3.Nc3*, 2026-10-29): das
913 legendas com imagem, a leitura do modelo é casa por casa uma posição do PGN em 877 (96%), e
nos que discordam o erro é do modelo. Ver `docs/ROADMAP_PDF_COM_PGN.md`.

## A partida que a linha em branco a mais partia em duas (S-585)

O PGN daquele livro traz as partidas sem `[FEN]` com **duas** linhas em branco entre o cabeçalho e
os lances. `chess.pgn.read_game` termina a partida na segunda: sai uma partida só com cabeçalho e
outra só com lances e cabeçalho de fábrica (`?`). Foram 21 de 120. O «Abrir um .pgn…» do Estudo
descartava a primeira (sem lance, sem posição) e mostrava a segunda sem «Chapter 3 / Game 2».

`fluxo_tolerante` embrulha o arquivo **sem lê-lo para a memória** -- `pgn_database/` tem arquivos de
10 GB, e é o mesmo laço que lê os dois (S-307). Ele só junta as linhas em branco que vêm **depois de
uma linha de cabeçalho e antes de um lance**. Antes de outro `[`, elas ficam: ali há duas partidas
de verdade, e juntá-las daria à primeira o cabeçalho da segunda.

## O índice da árvore (S-586)

`IndiceDoLivro` guarda cada nó com o capítulo (`Event`), a seção (`Site`), o rótulo do lance como o
livro o escreve (`5.dxc5`, `3...c5`), o caminho na árvore (`estudo.caminho_de`) e a FEN. As
perguntas são duas: "que nós têm este rótulo neste capítulo?" (a legenda do diagrama) e "que nós
têm esta posição?" (a leitura do modelo, para o livro sem legenda).
"""

from __future__ import annotations

import io
import logging
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO, cast

import chess
import chess.pgn

from .estudo import Caminho, caminho_de, no_em

logger = logging.getLogger(__name__)

__all__ = [
    "IndiceDoLivro",
    "NoDoLivro",
    "fluxo_tolerante",
    "ler_partidas",
    "lance_da_legenda",
    "rotulo_do_lance",
    "sem_desambiguacao",
]


class _FluxoTolerante:
    """`readline` sobre o arquivo, com as linhas em branco depois do cabeçalho reduzidas a uma.

    Ver o docstring do módulo. É só `readline` porque é tudo o que `chess.pgn.read_game` chama.
    """

    def __init__(self, fluxo: TextIO) -> None:
        self._fluxo = fluxo
        self._guardadas: list[str] = []
        self._depois_de_cabecalho = False

    def _proxima(self) -> str:
        return self._guardadas.pop() if self._guardadas else self._fluxo.readline()

    def readline(self) -> str:
        linha = self._proxima()
        if self._depois_de_cabecalho and linha and not linha.strip():
            brancas = [linha]
            seguinte = self._proxima()
            while seguinte and not seguinte.strip():
                brancas.append(seguinte)
                seguinte = self._proxima()
            if seguinte:
                self._guardadas.append(seguinte)
            if len(brancas) > 1 and seguinte and not seguinte.lstrip().startswith("["):
                logger.debug("Linha em branco a mais entre o cabeçalho e os lances: juntada.")
                self._depois_de_cabecalho = False
                return linha
            # antes de outro cabeçalho as linhas em branco separam duas partidas: devolvidas como vieram
            self._guardadas.extend(reversed(brancas[1:]))
            self._depois_de_cabecalho = False
            return linha
        self._depois_de_cabecalho = linha.lstrip().startswith("[") if linha.strip() else self._depois_de_cabecalho
        return linha


def fluxo_tolerante(texto: str | TextIO) -> TextIO:
    """O PGN (texto ou arquivo aberto) pronto para `chess.pgn.read_game`, sem a partida partida."""
    return cast(TextIO, _FluxoTolerante(io.StringIO(texto) if isinstance(texto, str) else texto))


def ler_partidas(caminho: Path | str) -> list[chess.pgn.Game]:
    """Todas as partidas do PGN do livro, na ordem do arquivo.

    O PGN de um livro tem centenas de partidas e cabe na memória; quem lê base grande é
    `estudo_arquivo.estudos_de_pgn`, que usa o mesmo `fluxo_tolerante` sobre o arquivo aberto.
    """
    partidas: list[chess.pgn.Game] = []
    with open(caminho, encoding="utf-8-sig", errors="replace") as arquivo:
        fluxo = fluxo_tolerante(arquivo)
        while (jogo := chess.pgn.read_game(fluxo)) is not None:
            if jogo.errors:
                logger.warning("%s: %d erro(s) na partida %d", caminho, len(jogo.errors), len(partidas) + 1)
            partidas.append(jogo)
    return partidas


def rotulo_do_lance(no: chess.pgn.ChildNode) -> str:
    """O lance como o livro o escreve: `5.dxc5` para as brancas, `3...c5` para as pretas."""
    antes = no.parent.board()
    san = antes.san(no.move)
    numero = antes.fullmove_number
    return f"{numero}.{san}" if antes.turn == chess.WHITE else f"{numero}...{san}"


_LANCE = re.compile(r"\d+\.(?:\.\.)?(?:O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)")
"""O número e o lance, sem xeque, mate nem avaliação -- é a parte que o rótulo do nó tem igual."""


def lance_da_legenda(legenda: str) -> str | None:
    """`5.dxc5` de «5.dxc5±», «5.dxc5+!» ou «8.0-0²»; `None` quando não há lance ali.

    O roque vem com zero em muitos livros (`0-0`) e com letra no PGN (`O-O`). O que segue o lance
    -- `+`, `!?`, `±` e o `²` que a fonte de figurinos põe no lugar de `⩲` -- é avaliação do autor.
    """
    texto = legenda.strip().replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    achado = _LANCE.match(texto)
    return achado.group(0) if achado else None


def sem_desambiguacao(lance: str) -> str:
    """`12.Nc3` de `12.Nbc3`: o livro às vezes desambigua um lance que só uma peça podia fazer."""
    return re.sub(r"(\.+)([KQRBN])[a-h1-8](x?[a-h][1-8])", r"\1\2\3", lance)


def _sem_xeque(rotulo: str) -> str:
    return rotulo.rstrip("+#")


@dataclass(frozen=True)
class NoDoLivro:
    """Um nó da árvore do livro, com o endereço para reabri-lo."""

    partida: int
    """Índice da partida em `IndiceDoLivro.partidas`."""
    caminho: Caminho
    capitulo: str
    secao: str
    rotulo: str
    fen: str

    @property
    def campo_de_pecas(self) -> str:
        return self.fen.split()[0]

    @property
    def lado(self) -> str:
        return self.fen.split()[1]


class IndiceDoLivro:
    """Os nós de todas as partidas do livro, em ordem de leitura (a principal antes das variantes).

    É a ordem em que o livro mostra as linhas, e é ela que desempata uma legenda que se repete no
    capítulo: o diagrama seguinte vem depois do anterior (`proximo_depois`).
    """

    def __init__(self, partidas: Iterable[chess.pgn.Game]) -> None:
        self.partidas = list(partidas)
        self.nos: list[NoDoLivro] = []
        self._por_capitulo: dict[str, list[int]] = defaultdict(list)
        self._por_posicao: dict[str, list[int]] = defaultdict(list)
        for indice, jogo in enumerate(self.partidas):
            capitulo = jogo.headers.get("Event", "")
            secao = jogo.headers.get("Site", "")
            for no in _em_ordem_de_leitura(jogo):
                assert isinstance(no, chess.pgn.ChildNode)
                registro = NoDoLivro(indice, caminho_de(no), capitulo, secao, rotulo_do_lance(no), no.board().fen())
                self._por_capitulo[capitulo].append(len(self.nos))
                self._por_posicao[registro.campo_de_pecas].append(len(self.nos))
                self.nos.append(registro)

    @classmethod
    def do_arquivo(cls, caminho: Path | str) -> IndiceDoLivro:
        return cls(ler_partidas(caminho))

    @property
    def capitulos(self) -> list[str]:
        return list(self._por_capitulo)

    def com_rotulo(self, capitulo: str, lance: str) -> list[int]:
        """Os nós do capítulo cujo lance é `lance` (sem xeque), na ordem de leitura.

        Sem nenhum, tenta de novo sem a desambiguação: `12.Nbc3` no livro, `12.Nc3` no PGN.
        """
        nos = self._por_capitulo.get(capitulo, [])
        achados = [k for k in nos if _sem_xeque(self.nos[k].rotulo) == lance]
        if achados:
            return achados
        simples = sem_desambiguacao(lance)
        return [k for k in nos if sem_desambiguacao(_sem_xeque(self.nos[k].rotulo)) == simples]

    def com_posicao(self, campo_de_pecas: str) -> list[int]:
        """Os nós (de qualquer capítulo) em que o tabuleiro é exatamente este."""
        return list(self._por_posicao.get(campo_de_pecas, []))

    def posicoes(self) -> Iterator[str]:
        """Cada campo de peças distinto do livro, uma vez."""
        return iter(self._por_posicao)

    def no(self, indice: int) -> chess.pgn.GameNode | None:
        """O nó do `chess.pgn` de volta, para abrir no Estudo com a árvore inteira."""
        registro = self.nos[indice]
        return no_em(self.partidas[registro.partida], registro.caminho)


def _em_ordem_de_leitura(jogo: chess.pgn.GameNode) -> Iterator[chess.pgn.GameNode]:
    pilha = list(reversed(jogo.variations))
    while pilha:
        no = pilha.pop()
        yield no
        pilha.extend(reversed(no.variations))
