"""Um `.djvu` vira um PDF em `data/djvu/`, e o resto do programa continua lendo PDF.

**Por que converter, e não ensinar o programa a ler DjVu.** Render, detecção, camada de texto,
substituição de diagrama e exportação falam com o `fitz.Document` em dezenas de lugares; o MuPDF não
lê DjVu. Um adaptador teria de imitar o `fitz` inteiro, e o PDF é de graça a mesma imagem.

**A conversão não perde pixel, e isso foi medido** (2026-11-05, 3 livros do acervo, página do meio
contra `page.render()`): com `jpeg_quality=None` a diferença média é 0,00 em página bitonal e em
página com fundo. O `jpeg_quality=80` padrão dava 0,73 e arquivo **maior** (35 MB contra 19 MB).
O `dpi` da biblioteca é um teto, e não um alvo: página de 300 DPI pedida a 600 continua com os pixels
dela. Por isso ele vai alto, para nunca reduzir.

**Duas rotas, porque o `write_pdf` é tudo ou nada.** Uma única página ruim derruba o livro inteiro.
A rota rápida guarda camada de texto, marcadores e links; quando ela falha, a rota página a página
guarda só a imagem, e o que não decodifica vira uma folha que diz isso. A numeração das páginas não
pode andar, ou toda referência ao livro passa a apontar para a página errada. O censo de 253 arquivos
de 2026-11-05 achou as duas falhas que esta rota existe para atravessar:

* **Dicionário compartilhado com nome em CP1251.** O `INCL` de uma página aponta para o dicionário
  JB2 pelo nome do componente, e quem gerou o arquivo no Windows russo gravou esse nome em CP1251. O
  arquivo é válido, mas a biblioteca não acha o dicionário ("stream requires shared dict"), e o livro
  inteiro cai. `_paginas_com_dicionario_embutido` resolve sem depender do nome: põe o dicionário
  dentro da própria página e a decodifica sozinha.
* **Capa de 1200 DPI.** A página de 7604x9828 **entra em pânico no Rust**, e o `PanicException` do
  PyO3 descende de `BaseException`: um `except Exception` não o vê, e ele atravessaria a tarefa.
  Pela metade da resolução ela decodifica.

**O acervo inteiro passou por aqui** (2026-11-05, 6 livros por vez): 246 dos 253 arquivos viraram PDF,
48.535 páginas com 3 folhas de aviso, sem nenhuma queda. Os outros 7 são recusados como incompletos
ou danificados. O custo é disco: 906 MB de `.djvu` viram 14,9 GB de PDF (mediana de 27 MB por livro,
máximo de 1,1 GB), porque DjVu comprime muito melhor do que imagem sem perda. O livro mais lento
levou 8 min (423 páginas), e a mediana foi de 23 s.

**A chave é o conteúdo, e não o caminho.** Mover o livro de pasta não perde o que foi feito nele, e
trocar o arquivo por outro de mesmo nome não entrega o PDF antigo. O PDF **não é descartável**: o
estado da janela, as marcas e os recentes apontam para ele, e por isso ele mora em `DATA_DIR`.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import fitz

from .config import DATA_DIR

logger = logging.getLogger(__name__)

SUFIXOS: Final = (".djvu", ".djv")

PASTA_PADRAO: Final = DATA_DIR / "djvu"

_DPI_QUE_NAO_REDUZ: Final = 2400
"""O teto do `write_pdf`. A maior página do acervo medido tem 1200 DPI."""

_TAMANHO_DA_CHAVE: Final = 16
_BLOCO_DE_LEITURA: Final = 1 << 20
_PONTOS_POR_POLEGADA: Final = 72.0
_DPI_SEM_DECLARACAO: Final = 300
_MARGEM_DO_AVISO: Final = 0.05
"""Fração da largura da folha."""
_LETRA_DO_AVISO: Final = 14.0
_LETRAS_POR_LARGURA: Final = 20.0

_SINAIS_DE_ARQUIVO_INCOMPLETO: Final = ("claims", "exceeds FORM children")
"""As falhas de abertura que o censo mediu nos arquivos que terminam antes do que declaram."""


@dataclass(frozen=True)
class Conversao:
    """O PDF de um `.djvu`, e o que ele não conseguiu trazer."""

    pdf: Path
    paginas: int
    ilegiveis: tuple[int, ...] = ()
    """Índices, a partir de 0, das páginas que viraram folha de aviso."""
    reaproveitada: bool = False


def e_djvu(caminho: Path | str) -> bool:
    return Path(caminho).suffix.lower() in SUFIXOS


def _destino(origem: Path, pasta: Path | None) -> Path:
    if not origem.is_file():
        raise ValueError(f"O arquivo {origem} não existe ou não é um arquivo.")
    return (pasta if pasta is not None else PASTA_PADRAO) / _chave(origem) / f"{origem.stem}.pdf"


def ja_convertido(origem: Path | str, *, pasta: Path | None = None) -> Conversao | None:
    """O PDF que o mesmo conteúdo já gerou, ou `None`. Só lê o arquivo e abre o PDF pronto.

    Separado de `pdf_de_djvu` para quem converte em outro processo não pagar o processo à toa.
    """
    return _ja_gravado(_destino(Path(origem), pasta))


def _ja_gravado(destino: Path) -> Conversao | None:
    if not destino.is_file():
        return None
    with fitz.open(str(destino)) as pronto:
        return Conversao(pdf=destino, paginas=pronto.page_count, reaproveitada=True)


def pdf_de_djvu(origem: Path | str, *, pasta: Path | None = None) -> Conversao:
    """O PDF de `origem`: o já convertido, se o mesmo conteúdo já passou por aqui.

    Raises:
        ValueError: arquivo ausente, danificado ou sem nenhuma página legível, com a frase em
            pt-BR. `ValueError` pelo mesmo motivo de `pdf_io._open_document`: é o que o `cli_errors`
            traduz e o que o `except` do painel já apanha.
    """
    origem = Path(origem)
    destino = _destino(origem, pasta)
    pronto = _ja_gravado(destino)
    if pronto is not None:
        return pronto
    destino.parent.mkdir(parents=True, exist_ok=True)
    descritor, nome = tempfile.mkstemp(suffix=".tmp", dir=destino.parent)
    os.close(descritor)
    temporario = Path(nome)
    try:
        paginas, ilegiveis = _escrever(origem, temporario)
        # **Atômico, e só depois de pronto**: um PDF pela metade neste caminho seria reaproveitado
        # para sempre, porque a existência dele é o que diz que a conversão terminou.
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)
    if ilegiveis:
        logger.warning("%s: páginas ilegíveis (a partir de 0): %s", origem.name, list(ilegiveis))
    return Conversao(pdf=destino, paginas=paginas, ilegiveis=ilegiveis)


def _chave(origem: Path) -> str:
    resumo = hashlib.sha256()
    with origem.open("rb") as arquivo:
        while bloco := arquivo.read(_BLOCO_DE_LEITURA):
            resumo.update(bloco)
    return resumo.hexdigest()[:_TAMANHO_DA_CHAVE]


def _biblioteca() -> Any:
    try:
        import djvu_rs
    except ImportError as exc:
        raise ValueError(
            "O decodificador de DjVu (djvu-rs) não está instalado neste ambiente, portanto nenhum "
            ".djvu pode ser aberto. Instale-o com 'pip install djvu-rs'."
        ) from exc
    return djvu_rs


def _falha_da_biblioteca(exc: BaseException, biblioteca: Any) -> bool:
    """Se `exc` é uma falha de decodificação, e não um Ctrl+C ou o fim do processo.

    O `PanicException` não dá para importar (mora em `pyo3_runtime`, que não é um módulo de verdade),
    então ele é reconhecido pelo nome.
    """
    return isinstance(exc, biblioteca.Error) or type(exc).__name__ == "PanicException"


def _escrever(origem: Path, temporario: Path) -> tuple[int, tuple[int, ...]]:
    biblioteca = _biblioteca()
    try:
        documento = biblioteca.Document.open(str(origem))
    except biblioteca.Error as exc:
        raise ValueError(_frase_de_abertura(origem, exc)) from exc
    total = documento.page_count()
    if total < 1:
        raise ValueError(f"{origem.name} não tem nenhuma página.")
    try:
        documento.write_pdf(
            str(temporario), dpi=_DPI_QUE_NAO_REDUZ, jpeg_quality=None, ccitt_g4=True
        )
    except BaseException as exc:  # noqa: BLE001 - o pânico do Rust não é `Exception`; ver a docstring
        if not _falha_da_biblioteca(exc, biblioteca):
            raise
        logger.info("%s: a rota rápida falhou (%s); indo página a página.", origem.name, exc)
    else:
        return total, ()
    return total, _escrever_pagina_a_pagina(documento, total, origem, temporario, biblioteca)


def _frase_de_abertura(origem: Path, exc: BaseException) -> str:
    motivo = str(exc)
    if any(sinal in motivo for sinal in _SINAIS_DE_ARQUIVO_INCOMPLETO):
        return (
            f"{origem.name} está incompleto ou danificado: ele termina antes do que ele mesmo "
            "declara, o que costuma ser um download interrompido. Baixe o arquivo de novo."
        )
    return f"{origem.name} não pôde ser lido como DjVu: {motivo}"


def _escrever_pagina_a_pagina(
    documento: Any, total: int, origem: Path, temporario: Path, biblioteca: Any
) -> tuple[int, ...]:
    avulsas: list[bytes] | None = None
    ilegiveis: list[int] = []
    saida = fitz.open()
    try:
        for indice in range(total):
            pagina = documento.page(indice)
            lado = (pagina.width, pagina.height)
            dpi = pagina.dpi or _DPI_SEM_DECLARACAO
            retangulo = fitz.Rect(
                0, 0, lado[0] * _PONTOS_POR_POLEGADA / dpi, lado[1] * _PONTOS_POR_POLEGADA / dpi
            )
            folha = saida.new_page(width=retangulo.width, height=retangulo.height)
            try:
                imagem = _renderizar(pagina, dpi, biblioteca)
            except BaseException as exc:  # noqa: BLE001 - o pânico do Rust; ver a docstring
                if not _falha_da_biblioteca(exc, biblioteca):
                    raise
                imagem = None
                if "shared dict" in str(exc):
                    if avulsas is None:
                        avulsas = _paginas_com_dicionario_embutido(origem.read_bytes(), total) or []
                    imagem = _renderizar_avulsa(avulsas, indice, lado, dpi, biblioteca)
                if imagem is None:
                    logger.warning("%s, página %d: %s", origem.name, indice + 1, exc)
            if imagem is None:
                _escrever_aviso(folha, retangulo, indice)
                ilegiveis.append(indice)
            else:
                folha.insert_image(retangulo, stream=imagem)
        if len(ilegiveis) == total:
            raise ValueError(f"{origem.name}: nenhuma das {total} páginas pôde ser decodificada.")
        saida.save(str(temporario), garbage=3, deflate=True)
    finally:
        saida.close()
    return tuple(ilegiveis)


def _renderizar(pagina: Any, dpi: int, biblioteca: Any) -> bytes:
    """A página em PNG, na resolução dela -- ou na metade, se ela entra em pânico.

    Só o pânico merece a segunda tentativa: `DecodeError` diz que o conteúdo não decodifica, e
    resolução nenhuma muda isso. Medido: a capa de 7604x9828 do Pachman passa a 600 DPI, e a
    contracapa de 6856x9888 falha em qualquer resolução.
    """
    try:
        return _png(pagina.render())
    except BaseException as exc:  # noqa: BLE001 - o pânico do Rust; ver a docstring
        if isinstance(exc, biblioteca.Error) or type(exc).__name__ != "PanicException":
            raise
    return _png(pagina.render(dpi=dpi / 2))


def _renderizar_avulsa(
    avulsas: list[bytes], indice: int, lado: tuple[int, int], dpi: int, biblioteca: Any
) -> bytes | None:
    if indice >= len(avulsas):
        return None
    try:
        pagina = biblioteca.Document.from_bytes(avulsas[indice]).page(0)
        # **A conferência que segura a suposição de `_paginas_com_dicionario_embutido`.** Página que
        # não bate com a do documento é outra página, e entregá-la seria pior do que a folha de aviso.
        if (pagina.width, pagina.height) != lado:
            return None
        return _renderizar(pagina, dpi, biblioteca)
    except BaseException as exc:  # noqa: BLE001 - o pânico do Rust; ver a docstring
        if not _falha_da_biblioteca(exc, biblioteca):
            raise
        return None


def _png(pixmap: Any) -> bytes:
    """PNG no menor modo que guarda a página **sem perda**: 1 bit, cinza ou cor."""
    from PIL import ImageChops

    imagem = pixmap.to_pil().convert("RGB")
    vermelho, verde, azul = imagem.split()
    if (
        ImageChops.difference(vermelho, verde).getbbox() is None
        and ImageChops.difference(verde, azul).getbbox() is None
    ):
        imagem = vermelho
        if not any(imagem.histogram()[1:255]):
            imagem = imagem.convert("1", dither=0)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


def _escrever_aviso(folha: Any, retangulo: Any, indice: int) -> None:
    """A folha de uma página que não decodificou: **ela diz isso**, e não fica em branco.

    Em branco, ela seria lida como uma página sem conteúdo, que é o que um livro tem de sobra. A letra
    acompanha a folha porque `insert_textbox` não escreve **nada** quando o texto não cabe na caixa.
    """
    margem = retangulo.width * _MARGEM_DO_AVISO
    folha.insert_textbox(
        retangulo + (margem, margem, -margem, -margem),
        f"A página {indice + 1} deste .djvu não pôde ser decodificada.",
        fontsize=min(_LETRA_DO_AVISO, retangulo.width / _LETRAS_POR_LARGURA),
        fontname="helv",
    )


# ---------------------------------------------------------------------- o contêiner IFF do DjVu


def _pedacos(dados: bytes, inicio: int, fim: int) -> list[tuple[bytes, int, int]]:
    """`(nome, início do conteúdo, tamanho)` de cada pedaço IFF entre `inicio` e `fim`.

    Para no primeiro nome zerado: é como termina um arquivo pré-alocado que não baixou até o fim.
    """
    pedacos = []
    posicao = inicio
    while posicao + 8 <= fim:
        nome = dados[posicao : posicao + 4]
        if nome == b"\0\0\0\0":
            break
        tamanho = struct.unpack(">I", dados[posicao + 4 : posicao + 8])[0]
        pedacos.append((nome, posicao + 8, tamanho))
        posicao += 8 + tamanho + (tamanho & 1)
    return pedacos


def _um_arquivo_de_uma_pagina(partes: list[tuple[bytes, bytes]]) -> bytes:
    miolo = bytearray(b"DJVU")
    for nome, conteudo in partes:
        # IFF alinha cada pedaço em posição par contada do início do arquivo, e os 12 bytes de
        # `AT&TFORM<tamanho>` que vêm antes do miolo são pares.
        if len(miolo) % 2:
            miolo += b"\0"
        miolo += nome + struct.pack(">I", len(conteudo)) + conteudo
    return b"AT&TFORM" + struct.pack(">I", len(miolo)) + bytes(miolo)


def _paginas_com_dicionario_embutido(dados: bytes, total: int) -> list[bytes] | None:
    """Um arquivo de uma página para cada página, com os `INCL` resolvidos para dentro dela.

    **O nome do `INCL` não pode ser conferido com o do componente**: a tabela que os liga é o `DIRM`,
    comprimido em BZZ, que a biblioteca não expõe. O que dá para usar é a ordem, e é a que os geradores
    de DjVu produzem: cada componente `DJVI` vem antes da primeira página que o usa, e os nomes novos
    aparecem na ordem dos componentes. Quem foge dela devolve `None`, e `_renderizar_avulsa` ainda
    confere a medida de cada página antes de aceitá-la.

    Medido em 2026-11-05 nos 2 livros de teste: 288 de 288 páginas decodificadas, e as páginas abertas
    para conferir trazem texto, diagramas e o número do rodapé certos.
    """
    if dados[:4] != b"AT&T" or dados[4:8] != b"FORM" or dados[12:16] != b"DJVM":
        return None
    componentes: list[bytes] = []
    resolvidos: dict[bytes, bytes | None] = {}
    avulsas: list[bytes] = []
    for nome, inicio, tamanho in _pedacos(dados, 16, len(dados)):
        if nome != b"FORM":
            continue
        tipo = dados[inicio : inicio + 4]
        fim = min(inicio + tamanho, len(dados))
        filhos = [
            (filho, dados[de : de + quanto]) for filho, de, quanto in _pedacos(dados, inicio + 4, fim)
        ]
        if tipo == b"DJVI":
            componentes.append(dict(filhos).get(b"Djbz", b""))
        elif tipo == b"DJVU":
            partes: list[tuple[bytes, bytes]] = []
            for filho, conteudo in filhos:
                if filho != b"INCL":
                    partes.append((filho, conteudo))
                    continue
                if conteudo not in resolvidos:
                    if len(resolvidos) >= len(componentes):
                        return None
                    resolvidos[conteudo] = componentes[len(resolvidos)]
                # Um `DJVI` sem dicionário é o de anotações compartilhadas, que a imagem não usa.
                if dicionario := resolvidos[conteudo]:
                    partes.append((b"Djbz", dicionario))
            avulsas.append(_um_arquivo_de_uma_pagina(partes))
    return avulsas if len(avulsas) == total else None
