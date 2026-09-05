"""O lote de diagramas gravado no disco, um arquivo por posição (S-544).

**Quem decide o que sai é `ui/lote_de_diagramas.py`**; aqui é a travessia: pedir os bytes ao
desenhista do formato escolhido, gravar com o nome que a decisão deu, contar o andamento e parar
quando mandarem parar. É a mesma separação de `estudo_paragrafos.py` e `epub.py`.

**Um diagrama ruim não derruba o lote.** É a regra do `batch.run_batch`, e vale aqui pelo mesmo
motivo: um livro varrido traz posições que o modelo leu errado, e uma FEN com nove colunas numa
página no meio de quinhentas não pode custar as outras 499. A falha entra no relatório com o nome
que o arquivo teria e o motivo, e a varredura segue.

**O cancelamento é conferido entre arquivos, e não dentro de um.** Um diagrama leva milissegundos
para desenhar; conferir mais fino custaria mais que o desenho. É a mesma resposta da S-24 entre
páginas, na escala deste trabalho.

Sem Qt aqui: quem mostra a barra é `qt/lote_de_diagramas.py`, e este módulo grava igual chamado de
um teste ou de um comando de linha.
"""

from __future__ import annotations

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

__all__ = ["RelatorioDoLote", "bytes_do_item", "frase_do_relatorio", "gravar_lote"]

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


def gravar_lote(
    itens: Sequence[ItemDoLote],
    opcoes: Opcoes,
    pasta: Path,
    *,
    cancelar: threading.Event | None = None,
    progresso: Progresso | None = None,
) -> RelatorioDoLote:
    """Grava um arquivo por item em `pasta` e devolve o que aconteceu.

    A pasta é criada se não existir -- `atomic_write_bytes` já o faz por arquivo, e fazê-lo uma vez
    aqui é o que permite a pasta vazia existir quando o lote inteiro falha.
    """
    comeco = time.perf_counter()
    destino = Path(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    nomes = nomes_do_lote(itens, opcoes.formato)

    gravados: list[Path] = []
    falhas: list[tuple[str, str]] = []
    bytes_totais = 0
    cancelado = False
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
        atomic_write_bytes(arquivo, dados)
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
