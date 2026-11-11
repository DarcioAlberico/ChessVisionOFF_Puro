"""A decisão da Revisão volta ao `.pgn` já exportado, diagrama por diagrama.

**A pendência é da Fase 4** (`docs/ROADMAP.md`): corrigir um item da fila salvava a amostra e
fechava o item, mas o arquivo exportado continuava com a leitura errada, e o único caminho era
exportar o livro de novo, que relê as páginas.

**Cirurgia no texto, e não `chess.pgn` de ida e volta.** O arquivo é da pessoa: ele pode ter
comentários, variantes e cabeçalhos que ela acrescentou num editor de PGN, e reexportar pelo
`chess.pgn` reescreveria o que ninguém pediu para tocar. Só mudam as linhas de cabeçalho do jogo
corrigido; o resto do arquivo sai igual byte a byte, inclusive a quebra de linha (a exportação grava
por `write_text`, então no Windows o arquivo é CRLF).

**O que identifica o jogo são os três cabeçalhos que `build_pgn_games` escreve**: `SourcePDF`,
`Page` e `Diagram`. Sem conferir o livro, escolher o PGN errado reescreveria o diagrama de mesmo
número de outro livro. `ReadingOrder` entra pelo mesmo motivo: `[Diagram "2"]` só significa algo
junto com a ordem em que a página foi numerada, e a fila da janela usa `DEFAULT_READING_ORDER`.

**Os `OCR*` ficam**: eles descrevem o que o OCR leu, e isso não mudou. Por isso o jogo corrigido
ganha `[ReviewedFrom]` com a FEN anterior, e é o que diz a quem lê que aqueles números são da
leitura antiga. Quem descreve a posição do arquivo (`FEN`, `SideToMove*`, o link do Lichess no
comentário) acompanha a correção. O sidecar `.proveniencia.jsonl` também fica: é a procedência da
leitura, e a chave dele continua valendo.

Só entram os itens com status `done`: `pending` e `skipped` não são decisão de ninguém.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path

import chess

from .atomic_io import atomic_write_bytes
from .config import DEFAULT_READING_ORDER
from .gallery import lichess_analysis_url
from .pdf_to_pgn import review_output_path
from .review_queue import ReviewQueue
from .semantics import SideToMove, board_placement, compose_fen

logger = logging.getLogger(__name__)

__all__ = ["Decisao", "PlanoDeReescrita", "decisoes_da_fila", "gravar", "planejar", "reescrever"]

CABECALHO = re.compile(r'^﻿?\[(\w+)\s+"((?:[^"\\]|\\.)*)"\]\s*$')
"""Uma linha de cabeçalho PGN, sem a quebra de linha."""

SUFIXO_DE_REVISAO = ".review.pgn"
Chave = tuple[str, int, int]
"""`(SourcePDF, Page, Diagram)`, os três cabeçalhos que identificam o jogo."""


@dataclass(frozen=True)
class Decisao:
    """O que a pessoa decidiu sobre um diagrama: as peças e o lado a jogar."""

    placement: str
    lado: str

    @property
    def cor(self) -> chess.Color:
        return chess.BLACK if self.lado == "b" else chess.WHITE


@dataclass(frozen=True)
class Reescrita:
    """O resultado sobre um texto. `trocados` são chaves; `texto` já vem com as trocas."""

    texto: str
    trocados: tuple[Chave, ...] = ()
    iguais: tuple[Chave, ...] = ()
    outra_ordem: tuple[Chave, ...] = ()


@dataclass(frozen=True)
class ArquivoPlanejado:
    caminho: Path
    reescrita: Reescrita
    novos_bytes: bytes


@dataclass(frozen=True)
class PlanoDeReescrita:
    """O que `gravar` faria, e o que a pergunta diz antes de ele fazer."""

    arquivos: tuple[ArquivoPlanejado, ...]
    decididos: int

    @property
    def a_gravar(self) -> tuple[ArquivoPlanejado, ...]:
        return tuple(arquivo for arquivo in self.arquivos if arquivo.reescrita.trocados)

    @property
    def trocados(self) -> int:
        return sum(len(arquivo.reescrita.trocados) for arquivo in self.arquivos)

    @property
    def iguais(self) -> int:
        return sum(len(arquivo.reescrita.iguais) for arquivo in self.arquivos)

    @property
    def outra_ordem(self) -> int:
        return sum(len(arquivo.reescrita.outra_ordem) for arquivo in self.arquivos)

    @property
    def fora_do_arquivo(self) -> int:
        return max(0, self.decididos - self.trocados - self.iguais - self.outra_ordem)

    def pergunta(self) -> str:
        nomes = ", ".join(arquivo.caminho.name for arquivo in self.a_gravar)
        return (
            f"Reescrever {self.trocados} diagrama(s) revisado(s) em {nomes}?\n\n"
            "Só mudam os cabeçalhos desses jogos. O arquivo anterior fica ao lado, como "
            f".bak-<data>.{self._ressalvas()}"
        )

    def frase_sem_trocas(self) -> str:
        return f"Nada a reescrever: nenhum dos {self.decididos} item(ns) revisado(s) muda este PGN.{self._ressalvas()}"

    def _ressalvas(self) -> str:
        partes = []
        if self.iguais:
            partes.append(f"{self.iguais} já está(ão) como a revisão decidiu")
        if self.fora_do_arquivo:
            partes.append(f"{self.fora_do_arquivo} não está(ão) neste arquivo")
        if self.outra_ordem:
            partes.append(f"{self.outra_ordem} ficou(aram) de fora porque a página foi numerada em outra ordem")
        return f" ({'; '.join(partes)}.)" if partes else ""


def decisoes_da_fila(fila: ReviewQueue) -> dict[Chave, Decisao]:
    """Os itens que a pessoa fechou, na chave dos cabeçalhos do PGN.

    `Page` é a página contada de 1, como `ReviewItem.page_number`. A FEN do item é completa quando
    veio da varredura e pode ser só o campo de peças quando veio do editor, então se normaliza aqui.
    """
    decisoes: dict[Chave, Decisao] = {}
    for item in fila.items:
        if item.status != "done" or not item.fen.strip():
            continue
        chave = (Path(item.pdf_path).name, item.page_number, item.diagram_index)
        decisoes[chave] = Decisao(board_placement(item.fen), item.side_to_move)
    return decisoes


def _valor_escapado(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace('"', '\\"')


def _blocos_de_cabecalho(linhas: Sequence[str]) -> list[tuple[int, int]]:
    """`(início, fim)` de cada sequência de linhas de cabeçalho."""
    blocos = []
    inicio: int | None = None
    for numero, linha in enumerate(linhas):
        if CABECALHO.match(linha.rstrip("\r\n")):
            if inicio is None:
                inicio = numero
        elif inicio is not None:
            blocos.append((inicio, numero))
            inicio = None
    if inicio is not None:
        blocos.append((inicio, len(linhas)))
    return blocos


def _fim_de_linha(linhas: Sequence[str]) -> str:
    return "\r\n" if linhas and linhas[0].endswith("\r\n") else "\n"


def _fen_nova(antiga: str, decisao: Decisao) -> str:
    """A FEN da decisão, com o número do lance que o arquivo já tinha (a pessoa pode tê-lo declarado)."""
    campos = antiga.split()
    lance = int(campos[5]) if len(campos) == 6 and campos[5].isdigit() else 1
    return compose_fen(decisao.placement, decisao.cor, fullmove=lance)


def reescrever(texto: str, decisoes: Mapping[Chave, Decisao]) -> Reescrita:
    """Aplica as decisões num texto PGN. **Pura.** O que não casa sai igual, byte a byte."""
    linhas = texto.splitlines(keepends=True)
    fim = _fim_de_linha(linhas)
    trocados: list[Chave] = []
    iguais: list[Chave] = []
    outra_ordem: list[Chave] = []
    # De trás para a frente: acrescentar uma linha não pode deslocar os blocos que ainda faltam.
    for inicio, parada in reversed(_blocos_de_cabecalho(linhas)):
        cabecalhos: dict[str, tuple[int, str]] = {}
        for numero in range(inicio, parada):
            achado = CABECALHO.match(linhas[numero].rstrip("\r\n"))
            assert achado is not None  # o bloco só tem linha que casou
            cabecalhos[achado.group(1)] = (numero, achado.group(2))

        try:
            chave: Chave = (cabecalhos["SourcePDF"][1], int(cabecalhos["Page"][1]), int(cabecalhos["Diagram"][1]))
        except (KeyError, ValueError):
            continue
        decisao = decisoes.get(chave)
        if decisao is None or "FEN" not in cabecalhos:
            continue
        if "ReadingOrder" in cabecalhos and cabecalhos["ReadingOrder"][1] != DEFAULT_READING_ORDER:
            outra_ordem.append(chave)
            continue

        numero_da_fen, fen_antiga = cabecalhos["FEN"]
        campos = fen_antiga.split()
        lado_antigo = campos[1] if len(campos) > 1 else "w"
        if campos and campos[0] == decisao.placement and lado_antigo == decisao.lado:
            iguais.append(chave)
            continue

        fen_nova = _fen_nova(fen_antiga, decisao)
        linhas[numero_da_fen] = f'[FEN "{fen_nova}"]{fim}'
        if "SideToMove" in cabecalhos and lado_antigo != decisao.lado:
            lado = SideToMove(color=decisao.cor, source="manual", reason="decidido na fila de revisão")
            linhas[cabecalhos["SideToMove"][0]] = f'[SideToMove "{lado.label}"]{fim}'
            if "SideToMoveSource" in cabecalhos:
                linhas[cabecalhos["SideToMoveSource"][0]] = f'[SideToMoveSource "{lado.source}"]{fim}'
            if "SideToMoveConfidence" in cabecalhos:
                # era a confiança do OCR na vez a jogar, e quem decidiu agora foi a pessoa
                linhas[cabecalhos["SideToMoveConfidence"][0]] = ""
        # O link do Lichess fica no comentário, logo depois do bloco; ele carrega a FEN na URL.
        url_antiga = lichess_analysis_url(fen_antiga)
        for numero in range(parada, min(parada + 4, len(linhas))):
            if url_antiga in linhas[numero]:
                linhas[numero] = linhas[numero].replace(url_antiga, lichess_analysis_url(fen_nova))
                break
        if "ReviewedFrom" not in cabecalhos:
            # A leitura original fica uma vez só: reescrever de novo não apaga de onde se partiu.
            linhas[numero_da_fen] += f'[ReviewedFrom "{_valor_escapado(fen_antiga)}"]{fim}'
        trocados.append(chave)
    return Reescrita("".join(linhas), tuple(reversed(trocados)), tuple(reversed(iguais)), tuple(reversed(outra_ordem)))


def arquivos_do_export(caminho: Path) -> tuple[Path, ...]:
    """O arquivo escolhido e o par dele: a exportação grava `livro.pgn` e `livro.review.pgn`.

    O par importa porque um item da fila costuma estar justamente no `.review.pgn`: foi a leitura
    duvidosa que o gate separou.
    """
    caminho = Path(caminho)
    if caminho.name.lower().endswith(SUFIXO_DE_REVISAO):
        par = caminho.with_name(caminho.name[: -len(SUFIXO_DE_REVISAO)] + caminho.suffix)
    else:
        par = review_output_path(caminho)
    return tuple(p for p in (caminho, par) if p.is_file())


def planejar(caminho: Path, decisoes: Mapping[Chave, Decisao]) -> PlanoDeReescrita:
    """Lê o arquivo e o par, e diz o que mudaria. Não grava nada. Levanta `OSError`/`UnicodeError`."""
    arquivos = []
    for arquivo in arquivos_do_export(caminho):
        reescrita = reescrever(arquivo.read_bytes().decode("utf-8"), decisoes)
        arquivos.append(ArquivoPlanejado(arquivo, reescrita, reescrita.texto.encode("utf-8")))
    return PlanoDeReescrita(tuple(arquivos), decididos=len(decisoes))


def copia_de_seguranca(caminho: Path) -> Path:
    """Copia para um irmão datado, sem nunca escrever por cima de outra cópia (`O_EXCL`)."""
    dados = caminho.read_bytes()
    base = f"{caminho.name}.bak-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    for sufixo in count(1):
        destino = caminho.with_name(base if sufixo == 1 else f"{base}-{sufixo}")
        try:
            descritor = os.open(destino, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0))
        except FileExistsError:
            continue
        try:
            with os.fdopen(descritor, "wb") as handle:
                handle.write(dados)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            destino.unlink(missing_ok=True)
            raise
        return destino
    raise AssertionError("count() não termina")  # pragma: no cover


def gravar(plano: PlanoDeReescrita) -> tuple[Path, ...]:
    """Faz a cópia e troca o arquivo, atomicamente, um por vez. Devolve as cópias feitas.

    A cópia vem antes: se ela falhar nada foi tocado, e se a troca falhar o arquivo antigo fica
    intacto (`atomic_io`). Só grava o arquivo em que algo muda.
    """
    copias = []
    for arquivo in plano.a_gravar:
        copias.append(copia_de_seguranca(arquivo.caminho))
        atomic_write_bytes(arquivo.caminho, arquivo.novos_bytes)
        logger.info("%s: %d diagrama(s) reescrito(s).", arquivo.caminho, len(arquivo.reescrita.trocados))
    return tuple(copias)
