"""O lote de diagramas gravado no disco, um arquivo por posição (S-544).

**Quem decide o que sai é `ui/lote_de_diagramas.py`**; aqui é a travessia: pedir os bytes ao
desenhista do formato escolhido, gravar com o nome que a decisão deu, contar o andamento e parar
quando mandarem parar. É a mesma separação de `estudo_paragrafos.py` e `epub.py`.

**Um diagrama ruim não derruba o lote.** É a regra do `batch.run_batch`, e vale aqui pelo mesmo
motivo: um livro varrido traz posições que o modelo leu errado, e uma FEN com nove colunas numa
página no meio de quinhentas não pode custar as outras 499. A falha entra no relatório com o nome
que o arquivo teria e o motivo, e a varredura segue.

**E o disco também não derruba o lote** (segunda rodada, 2026-09-05). Até aqui só a *falha de
desenho* virava relatório: uma pasta em disco cheio, num pendrive tirado no meio, ou dentro de um
caminho que não existe levantava `OSError` de dentro de `gravar_lote` -- e o crítico mediu o
sintoma, um `FileNotFoundError` cru subindo pela thread com quinhentos diagramas já desenhados e
nenhuma linha de relatório dizendo o que aconteceu. As duas falhas são a mesma pergunta para quem
espera -- "o que saiu e o que não saiu?" --, e agora têm a mesma resposta. A pasta que não abre é
falha do lote inteiro e aparece uma vez, com o caminho; o arquivo que não grava é falha daquele
arquivo, e os outros seguem.

**O cancelamento é conferido entre arquivos, e não dentro de um.** Um diagrama leva milissegundos
para desenhar; conferir mais fino custaria mais que o desenho. É a mesma resposta da S-24 entre
páginas, na escala deste trabalho.

Sem Qt aqui: quem mostra a barra é `qt/lote_de_diagramas.py`, e este módulo grava igual chamado de
um teste ou de um comando de linha.
"""

from __future__ import annotations

import errno
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .atomic_io import atomic_write_bytes
from .diagrama_png import png_da_posicao
from .diagrama_svg import PosicaoInvalida, svg_da_posicao
from .ui.lote_de_diagramas import PNG, ItemDoLote, Opcoes, cores_da_pele, formato_registrado, nomes_do_lote

logger = logging.getLogger(__name__)

__all__ = [
    "RelatorioDoLote",
    "bytes_do_item",
    "frase_de_disco",
    "frase_do_relatorio",
    "gravar_lote",
]

Progresso = Callable[[int, int, str], None]
"""`(feitos, total, nome do arquivo)`. Chamado **depois** de cada gravação, na thread que grava."""


@dataclass(frozen=True)
class RelatorioDoLote:
    """O que a rodada fez. Congelado: é o que a tela lê depois que a thread termina."""

    pasta: Path
    gravados: tuple[Path, ...] = ()
    falhas: tuple[tuple[str, str], ...] = ()
    """`(nome do arquivo, motivo)` de cada diagrama que não desenhou. Ver o cabeçalho."""

    bytes_totais: int = 0
    segundos: float = 0.0
    cancelado: bool = False
    total: int = 0
    """Quantos itens o lote tinha. Difere de `len(gravados)` quando houve falha ou cancelamento."""

    @property
    def media_de_bytes(self) -> int:
        """O tamanho médio do arquivo. Zero sem nenhum gravado -- e não uma divisão por zero."""
        return round(self.bytes_totais / len(self.gravados)) if self.gravados else 0

    @property
    def por_segundo(self) -> float:
        """Quantos diagramas por segundo. É o número que o critério de aceite do item cobra."""
        return len(self.gravados) / self.segundos if self.segundos > 0 else 0.0


def bytes_do_item(item: ItemDoLote, opcoes: Opcoes) -> bytes:
    """Os bytes do arquivo daquele diagrama, no formato escolhido.

    O SVG sai **com a declaração XML** (`DECLARACAO_XML`) porque aqui ele é arquivo, e não um
    elemento dentro do XHTML de um EPUB -- é a distinção que `diagrama_svg` já escreve.

    O `width`/`height` do SVG vai em pixel e não em `em`: um `em` é o corpo do texto em volta, e um
    arquivo solto não tem texto em volta. O `viewBox` não muda, então o arquivo continua crescendo
    sem perder -- o pixel aqui é o tamanho **sugerido**, que é o que um editor importa.
    """
    cores = cores_da_pele(opcoes.pele)
    if formato_registrado(opcoes.formato).nome == PNG:
        return png_da_posicao(
            item.fen,
            virado=item.virado,
            com_reguas=opcoes.coordenadas,
            lado_a_jogar=opcoes.lado_a_jogar,
            cores=cores,
            pasta_de_pecas=opcoes.pasta_do_conjunto,
            casa_px=opcoes.casa_px,
            margem=opcoes.faixa_px,
            engrossar=opcoes.engrossar,
        )
    texto = svg_da_posicao(
        item.fen,
        virado=item.virado,
        com_reguas=opcoes.coordenadas,
        lado_a_jogar=opcoes.lado_a_jogar,
        largura_em=opcoes.tamanho,
        unidade="px",
        declaracao=True,
        cores=cores,
        titulo=item.titulo,
        margem=opcoes.faixa_svg,
    )
    return texto.encode("utf-8")


def frase_de_disco(erro: OSError) -> str:
    """Por que o disco recusou, em pt-BR. Pura, e por isso afirmável sem um pendrive.

    A régua é `errno` e não o texto: a mensagem do sistema vem no idioma do Windows de quem usa --
    e em português ela já vem traduzida, o que faria uma busca por palavra em inglês passar num
    computador e falhar no outro. `strerror` vai junto entre parênteses, como em `cli.message_for`:
    a tradução é para quem lê, e o original é o que se pesquisa.
    """
    causas = {
        errno.EACCES: "sem permissão para escrever nesta pasta",
        errno.EPERM: "sem permissão para escrever nesta pasta",
        errno.ENOENT: "o caminho não existe",
        errno.ENOSPC: "não há espaço em disco",
        errno.EROFS: "o disco é somente-leitura",
        errno.ENOTDIR: "um dos nomes do caminho não é uma pasta",
        errno.EEXIST: "já existe um arquivo com o nome de uma das pastas do caminho",
    }
    causa = causas.get(erro.errno or 0, "o sistema recusou a escrita")
    detalhe = erro.strerror or type(erro).__name__
    return f"{causa} ({detalhe})"


def gravar_lote(
    itens: Sequence[ItemDoLote],
    opcoes: Opcoes,
    pasta: Path,
    *,
    cancelar: threading.Event | None = None,
    progresso: Progresso | None = None,
) -> RelatorioDoLote:
    """Grava um arquivo por item em `pasta` e devolve o que aconteceu. **Nunca levanta por disco.**

    A pasta é criada se não existir -- `atomic_write_bytes` já o faz por arquivo, e fazê-lo uma vez
    aqui é o que permite a pasta vazia existir quando o lote inteiro falha.

    Ver o cabeçalho para por que a falha de disco é relatório e não exceção.
    """
    comeco = time.perf_counter()
    destino = Path(pasta)
    nomes = nomes_do_lote(itens, opcoes.formato)

    gravados: list[Path] = []
    falhas: list[tuple[str, str]] = []
    bytes_totais = 0
    cancelado = False
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as erro:
        # A pasta é uma falha só, e não uma por item: quinhentas linhas iguais num relatório
        # escondem justamente a linha que diz o que houve.
        logger.warning("A pasta de destino %s não abriu: %s", destino, erro)
        return RelatorioDoLote(
            pasta=destino,
            falhas=((str(destino), frase_de_disco(erro)),),
            segundos=time.perf_counter() - comeco,
            total=len(itens),
        )
    for feitos, (item, nome) in enumerate(zip(itens, nomes, strict=True), start=1):
        if cancelar is not None and cancelar.is_set():
            cancelado = True
            break
        arquivo = destino / nome
        try:
            dados = bytes_do_item(item, opcoes)
        except (PosicaoInvalida, ValueError) as erro:
            logger.warning("O diagrama %s não desenhou: %s", nome, erro)
            falhas.append((nome, str(erro)))
            continue
        try:
            atomic_write_bytes(arquivo, dados)
        except OSError as erro:
            logger.warning("O diagrama %s não gravou: %s", nome, erro)
            falhas.append((nome, frase_de_disco(erro)))
            continue
        gravados.append(arquivo)
        bytes_totais += len(dados)
        if progresso is not None:
            progresso(feitos, len(itens), nome)
    return RelatorioDoLote(
        pasta=destino,
        gravados=tuple(gravados),
        falhas=tuple(falhas),
        bytes_totais=bytes_totais,
        segundos=time.perf_counter() - comeco,
        cancelado=cancelado,
        total=len(itens),
    )


def frase_do_relatorio(relatorio: RelatorioDoLote) -> str:
    """O que a barra de status diz quando o lote termina.

    Traz o **caminho inteiro** pela razão da S-546: quem acabou de gravar quinhentos arquivos
    precisa saber onde procurar, e "na pasta escolhida" não é um caminho.
    """
    partes = [f"{len(relatorio.gravados)} de {relatorio.total} diagrama(s) em {relatorio.pasta}."]
    if relatorio.falhas:
        partes.append(f"{len(relatorio.falhas)} não desenharam (veja o registro).")
    if relatorio.cancelado:
        partes.append("Cancelado: o que já saiu ficou gravado.")
    partes.append(f"Tamanho médio: {relatorio.media_de_bytes / 1024:.1f} KB.")
    return " ".join(partes)
