"""O diagrama como SVG vetorial, a partir da FEN (S-542).

**Por que vetorial, e por que não os PNGs do projeto.** `assets/piece_images/` são doze PNGs de
70×70 -- o conjunto que a janela desenha, e o que `diagrama_png.py` usa quando o destino é o DOCX.
Um EPUB é lido em tela de 5 e de 13 polegadas, e a mesma imagem de 70 px por casa fica serrilhada
numa e pesada na outra; o SVG desenha certo nas duas e pesa o mesmo. As peças vêm de
`chess.svg.PIECES`, o conjunto Cburnett que o `python-chess` -- **dependência obrigatória desde a
primeira versão** -- embute como caminhos SVG. Não é fonte de xadrez (a Merida e a Alpha não são
do repositório, e uma `@font-face` que o leitor não carregue mostra letras no lugar das peças): é
caminho, e caminho todo leitor de EPUB desenha.

## O que este módulo decide, e o que ele só repete

- **A geometria da casa é a de `chess.svg`**: 45 unidades por casa, porque é o quadro em que os
  caminhos das peças foram desenhados. Reescalar a peça seria uma `transform` a mais em cada uma
  das até 32, para nada.
- **A ordem das réguas é a de `ui/desenho_do_tabuleiro.reguas`** -- a mesma que a janela usa, e
  pelo mesmo motivo: com as brancas embaixo `a` fica à esquerda e `8` no topo; virado, os dois
  invertem. Não se redecide aqui.
- **As cores das casas saem de `ui/tokens.py`**, como a cor de autor sai dele no `.html` da
  Fase 39: nenhum hexadecimal é escrito neste arquivo.
- **O tamanho é em `em`**, e não em pixel: `width="18em"` deixa o leitor reflui-lo com o corpo do
  texto, que é a diferença entre um livro e uma página fixa.
- **O lado a jogar é um ponto na margem direita**, como os livros imprimem: embaixo para as
  brancas, em cima para as pretas. Sai da FEN quando ela traz o campo; um `placement` sozinho não
  diz de quem é a vez, e o ponto não aparece.

Nada de Qt aqui, e nada de arquivo: quem grava é `epub.py`, ou quem chamar.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass

import chess
import chess.svg

from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.desenho_do_tabuleiro import reguas

__all__ = [
    "CASA",
    "LARGURA_PADRAO_EM",
    "MARGEM",
    "Cores",
    "cores_padrao",
    "lado_da_fen",
    "svg_da_posicao",
    "tabuleiro_de",
]

CASA = chess.svg.SQUARE_SIZE
"""O lado da casa, em unidades do `viewBox`. **É o quadro dos caminhos de `chess.svg.PIECES`.**"""

MARGEM = 15
"""A faixa em volta do tabuleiro em que cabem as réguas e o ponto do lado a jogar."""

LARGURA_PADRAO_EM = 18.0
"""Quanto o diagrama mede no texto, em `em`. Dezoito porque é a largura de umas 36 letras de corpo
-- o diagrama de um livro de xadrez ocupa entre metade e dois terços da coluna, e é isso."""

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

TAMANHO_DA_REGUA = 10
"""O corpo das letras `a`–`h` e dos números `1`–`8`, em unidades do `viewBox`."""

RAIO_DO_LADO = 4.5


@dataclass(frozen=True)
class Cores:
    """As cores do diagrama. **Chegam prontas**, resolvidas de `ui/tokens.py` por `cores_padrao`."""

    clara: str
    escura: str
    moldura: str
    coordenada: str


def cores_padrao() -> Cores:
    """As cores da paleta de reserva do projeto -- as mesmas casas da janela sob tema claro."""
    return Cores(
        clara=tokens.cor(tokens.CASA_CLARA),
        escura=tokens.cor(tokens.CASA_ESCURA),
        moldura=tokens.cor(tokens.MOLDURA),
        coordenada=tokens.cor(tokens.COORDENADA),
    )


def tabuleiro_de(fen_ou_placement: str) -> chess.BaseBoard:
    """A posição daquele texto -- FEN completa ou só o campo de peças.

    Levanta `ValueError` para o que não é nem uma coisa nem outra, em vez de desenhar um tabuleiro
    vazio: um diagrama em branco no meio do livro é o defeito que ninguém acha.
    """
    texto = " ".join(str(fen_ou_placement or "").split())
    if not texto:
        raise ValueError("posição vazia: não há o que desenhar.")
    placement = texto.split(" ", 1)[0]
    return chess.BaseBoard(placement)


def lado_da_fen(fen_ou_placement: str) -> str:
    """`"w"`, `"b"` ou `""` -- o segundo campo da FEN, quando ele existe."""
    campos = str(fen_ou_placement or "").split()
    if len(campos) < 2:
        return ""
    lado = campos[1].lower()
    return lado if lado in ("w", "b") else ""


def svg_da_posicao(
    fen_ou_placement: str,
    *,
    virado: bool = False,
    com_reguas: bool = True,
    lado_a_jogar: str | None = None,
    largura_em: float = LARGURA_PADRAO_EM,
    cores: Cores | None = None,
    titulo: str = "",
) -> str:
    """O diagrama daquela posição, como texto SVG bem formado.

    `lado_a_jogar` é `"w"`, `"b"`, `""` (sem ponto) ou `None` -- e `None` quer dizer "o que a FEN
    disser". `virado` põe as pretas embaixo, como `Estudo.invertido`.
    """
    tabuleiro = tabuleiro_de(fen_ou_placement)
    lado = lado_da_fen(fen_ou_placement) if lado_a_jogar is None else lado_a_jogar.lower()
    paleta = cores or cores_padrao()

    margem = MARGEM if (com_reguas or lado) else 0
    lado_total = 8 * CASA + 2 * margem
    raiz = ET.Element(
        "svg",
        {
            "xmlns": SVG_NS,
            "xmlns:xlink": XLINK_NS,
            "viewBox": f"0 0 {lado_total} {lado_total}",
            "width": f"{largura_em:g}em",
            "height": f"{largura_em:g}em",
            "class": "diagrama",
            "role": "img",
            "data-fen": " ".join(str(fen_ou_placement).split()),
        },
    )
    ET.SubElement(raiz, "title").text = titulo or f"Diagrama: {' '.join(str(fen_ou_placement).split())}"

    _definir_pecas(raiz, tabuleiro)
    if margem:
        ET.SubElement(
            raiz,
            "rect",
            {"x": "0", "y": "0", "width": str(lado_total), "height": str(lado_total), "fill": paleta.moldura},
        )
    _casas(raiz, margem, virado, paleta)
    _pecas(raiz, tabuleiro, margem, virado)
    if com_reguas:
        _reguas(raiz, margem, virado, paleta)
    if lado:
        _ponto_do_lado(raiz, margem, lado, paleta)
    return ET.tostring(raiz, encoding="unicode")


def _casas(raiz: ET.Element, margem: int, virado: bool, paleta: Cores) -> None:
    """As 64 casas, **na ordem do índice de `chess`** (a1 = 0), e cada uma diz que casa é.

    A cor não depende de `virado`: e4 é clara vista de qualquer lado. O que vira é onde ela cai,
    e isso fica em `_posicao`."""
    for casa in chess.SQUARES:
        clara = (chess.square_file(casa) + chess.square_rank(casa)) % 2 == 1
        ET.SubElement(
            raiz,
            "rect",
            {
                "class": "casa clara" if clara else "casa escura",
                "data-casa": chess.square_name(casa),
                "width": str(CASA),
                "height": str(CASA),
                "fill": paleta.clara if clara else paleta.escura,
                **_xy(casa, margem, virado=virado),
            },
        )


def _xy(casa: int, margem: int, *, virado: bool) -> dict[str, str]:
    coluna, linha = _posicao(casa, virado)
    return {"x": str(margem + coluna * CASA), "y": str(margem + linha * CASA)}


def _posicao(casa: int, virado: bool) -> tuple[int, int]:
    """`(coluna, linha)` de desenho, de cima para baixo e da esquerda para a direita."""
    coluna_da_casa, fileira = chess.square_file(casa), chess.square_rank(casa)
    if virado:
        return 7 - coluna_da_casa, fileira
    return coluna_da_casa, 7 - fileira


def _definir_pecas(raiz: ET.Element, tabuleiro: chess.BaseBoard) -> None:
    """Um `<g id>` por **tipo de peça presente** -- e só os presentes, para o arquivo não carregar
    doze desenhos num final de rei e peão."""
    presentes = sorted({peca.symbol() for peca in tabuleiro.piece_map().values()})
    if not presentes:
        return
    defs = ET.SubElement(raiz, "defs")
    for simbolo in presentes:
        defs.append(ET.fromstring(chess.svg.PIECES[simbolo]))


def _id_da_peca(simbolo: str) -> str:
    return ET.fromstring(chess.svg.PIECES[simbolo]).get("id", "")


def _pecas(raiz: ET.Element, tabuleiro: chess.BaseBoard, margem: int, virado: bool) -> None:
    """Um `<use>` por peça, na casa em que ela está -- `data-casa` diz qual, e o teste lê."""
    ids: Mapping[str, str] = {simbolo: _id_da_peca(simbolo) for simbolo in chess.svg.PIECES}
    for casa, peca in sorted(tabuleiro.piece_map().items()):
        coluna, linha = _posicao(casa, virado)
        alvo = f"#{ids[peca.symbol()]}"
        ET.SubElement(
            raiz,
            "use",
            {
                "href": alvo,
                "xlink:href": alvo,
                "class": "peca",
                "data-casa": chess.square_name(casa),
                "data-peca": peca.symbol(),
                "transform": f"translate({margem + coluna * CASA},{margem + linha * CASA})",
            },
        )


def _reguas(raiz: ET.Element, margem: int, virado: bool, paleta: Cores) -> None:
    """As letras embaixo e os números à esquerda, **na ordem de `desenho_do_tabuleiro.reguas`**."""
    colunas, linhas = reguas(virado)
    comum = {
        "class": "regua",
        "fill": paleta.coordenada,
        "font-family": "sans-serif",
        "font-size": str(TAMANHO_DA_REGUA),
        "font-weight": "bold",
        "text-anchor": "middle",
    }
    base = margem + 8 * CASA
    for indice, letra in enumerate(colunas):
        x = margem + indice * CASA + CASA / 2
        texto = ET.SubElement(raiz, "text", {**comum, "x": f"{x:g}", "y": f"{base + margem * 0.75:g}"})
        texto.text = letra
    for indice, numero in enumerate(linhas):
        y = margem + indice * CASA + CASA / 2 + TAMANHO_DA_REGUA / 3
        texto = ET.SubElement(raiz, "text", {**comum, "x": f"{margem / 2:g}", "y": f"{y:g}"})
        texto.text = numero


def _ponto_do_lado(raiz: ET.Element, margem: int, lado: str, paleta: Cores) -> None:
    """O ponto da margem direita: embaixo para as brancas, em cima para as pretas."""
    brancas = lado == "w"
    x = margem + 8 * CASA + margem / 2
    y = margem + 8 * CASA - RAIO_DO_LADO - 1 if brancas else margem + RAIO_DO_LADO + 1
    ET.SubElement(
        raiz,
        "circle",
        {
            "class": "lado-a-jogar brancas" if brancas else "lado-a-jogar pretas",
            "cx": f"{x:g}",
            "cy": f"{y:g}",
            "r": str(RAIO_DO_LADO),
            "fill": paleta.clara if brancas else paleta.moldura,
            "stroke": paleta.coordenada,
            "stroke-width": "1",
        },
    )
