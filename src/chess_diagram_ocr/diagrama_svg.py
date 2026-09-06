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
- **O tamanho é em `em`** para o EPUB, e não em pixel: `width="18em"` deixa o leitor reflui-lo com o
  corpo do texto, que é a diferença entre um livro e uma página fixa. Quem embute o arquivo num
  formato que não tem corpo de texto -- o `.docx`, onde o SVG é uma parte solta do pacote -- pede
  outra `unidade` (`cm`) e a `declaracao` de XML que o Word espera no começo do arquivo.
- **O lado a jogar é uma plaqueta na margem direita**, como os livros imprimem: círculo vazado para
  as brancas, cheio para as pretas, do lado do tabuleiro em que aquele jogador está sentado --
  embaixo com as brancas embaixo, em cima quando `virado`. Sai da FEN quando ela traz o campo; um
  `placement` sozinho não diz de quem é a vez, e a plaqueta não aparece.

## Contraste: a régua e a plaqueta são lidas, ou não estão lá

A moldura é escura (`MOLDURA`), e sobre ela a tinta tem de ser clara. Na primeira rodada as duas
coisas desenhadas na margem saíram na cor errada: as coordenadas em `COORDENADA` (**2,51:1**, abaixo
do piso 4,5:1 da S-146) e o ponto das pretas pintado com a **própria cor da moldura** -- razão
**1,0:1**, um ponto invisível dizendo de quem era a vez. A régua passa a resolver-se por
`tokens.sobre_superficie(moldura)`, que é o instrumento que a S-146 escreveu exatamente para isto,
e a plaqueta a desenhar-se sobre `CASA_CLARA`, com a tinta das peças (`GLIFO_CLARO`/`GLIFO_ESCURO`)
e o contorno escuro que toda peça branca já tem. Todos os três passam de 12:1.

Nada de Qt aqui, e nada de arquivo: quem grava é `epub.py`, ou quem chamar.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, replace

import chess
import chess.svg

from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.desenho_do_tabuleiro import reguas

__all__ = [
    "CASA",
    "DECLARACAO_XML",
    "LARGURA_PADRAO_EM",
    "MARGEM",
    "Cores",
    "PosicaoInvalida",
    "cores_padrao",
    "descricao_da_posicao",
    "lado_da_fen",
    "svg_da_posicao",
    "tabuleiro_de",
]


class PosicaoInvalida(ValueError):
    """A posição não desenha, e o texto diz por quê **em pt-BR**.

    O `python-chess` levanta `ValueError: expected 8 rows in position part of fen: '8/8/8'` -- em
    inglês, e falando de "position part of fen", que não é o vocabulário de quem digitou um
    diagrama errado. O projeto já resolve isto por tradução (`cli/__init__.message_for`), e a regra
    de lá vale aqui: a frase em português, **e o original entre parênteses**, porque a tradução
    ajuda quem lê e o original é o que se pesquisa.
    """


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

DECLARACAO_XML = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
"""O cabeçalho que um `.svg` **como arquivo** leva. Dentro do XHTML do EPUB o SVG é um elemento e a
declaração não entra; dentro do `.docx` ele é uma parte do pacote, e o Word espera arquivo."""


@dataclass(frozen=True)
class Cores:
    """As cores do diagrama. **Chegam prontas**, resolvidas de `ui/tokens.py` por `cores_padrao`."""

    clara: str
    escura: str
    moldura: str
    coordenada: str
    peca_clara: str = ""
    """A tinta do círculo de "brancas jogam". Vazio usa `clara`."""

    peca_escura: str = ""
    """A tinta do círculo de "pretas jogam" e do contorno dos dois. Vazio usa `moldura`."""

    def resolvidas(self) -> Cores:
        """Com as duas tintas da plaqueta preenchidas, para quem construiu `Cores` com quatro."""
        return replace(self, peca_clara=self.peca_clara or self.clara, peca_escura=self.peca_escura or self.moldura)


def cores_padrao() -> Cores:
    """As cores da paleta de reserva do projeto -- as mesmas casas da janela sob tema claro.

    **A coordenada não é o papel `COORDENADA`**, e é de propósito: aquele papel é resolvido contra a
    superfície em que o texto vai cair (`sobre_superficie`, S-146), e aqui a superfície é a moldura
    escura do diagrama, não o fundo do painel. Resolvê-lo é o que tira as letras de 2,51:1.
    """
    moldura = tokens.cor(tokens.MOLDURA)
    return Cores(
        clara=tokens.cor(tokens.CASA_CLARA),
        escura=tokens.cor(tokens.CASA_ESCURA),
        moldura=moldura,
        coordenada=tokens.sobre_superficie(moldura),
        peca_clara=tokens.cor(tokens.GLIFO_CLARO),
        peca_escura=tokens.cor(tokens.GLIFO_ESCURO),
    )


def tabuleiro_de(fen_ou_placement: str) -> chess.BaseBoard:
    """A posição daquele texto -- FEN completa ou só o campo de peças.

    Levanta `PosicaoInvalida` para o que não é nem uma coisa nem outra, em vez de desenhar um
    tabuleiro vazio: um diagrama em branco no meio do livro é o defeito que ninguém acha.
    """
    texto = " ".join(str(fen_ou_placement or "").split())
    if not texto:
        raise PosicaoInvalida("posição vazia: não há o que desenhar.")
    placement = texto.split(" ", 1)[0]
    try:
        return chess.BaseBoard(placement)
    except ValueError as erro:
        raise PosicaoInvalida(f"posição inválida: {placement!r} não é uma FEN nem um campo de peças ({erro})") from erro


def descricao_da_posicao(fen_ou_placement: str, *, marca: str = "") -> str:
    """A frase que descreve o diagrama: a marca, de quem é a vez, e a posição em FEN.

    É o `alt` da imagem no EPUB e o `descr` do desenho no DOCX. **`alt="Diagrama 1"` não descreve
    nada** -- para quem lê com leitor de tela, é o mesmo que uma imagem sem alternativa, e é o que a
    EPUB Accessibility 1.1 chama de alternativa não descritiva. A FEN, essa, é a posição inteira em
    trinta caracteres, e quem lê xadrez a lê; é também o que permite copiar o diagrama para um
    tabuleiro. A marca (`Diagrama 3`, `[Diagrama 3]`) continua na frente, porque ela **nunca
    desaparece** (S-250).
    """
    fen = " ".join(str(fen_ou_placement or "").split())
    vez = {"w": "As brancas jogam", "b": "As pretas jogam"}.get(lado_da_fen(fen), "")
    partes = [parte for parte in (str(marca).strip(), vez) if parte]
    return ". ".join([*partes, f"FEN: {fen}"])


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
    unidade: str = "em",
    declaracao: bool = False,
    cores: Cores | None = None,
    titulo: str = "",
    margem: int | None = None,
) -> str:
    """O diagrama daquela posição, como texto SVG bem formado.

    `lado_a_jogar` é `"w"`, `"b"`, `""` (sem plaqueta) ou `None` -- e `None` quer dizer "o que a FEN
    disser". `virado` põe as pretas embaixo, como `Estudo.invertido`, e a plaqueta desce com elas.

    `unidade` é a do `width`/`height` do elemento raiz: `em` no EPUB, onde o diagrama reflui com o
    corpo do texto; `cm` no DOCX, onde ele é uma parte do pacote e o Word mede a página em
    centímetros. `declaracao` põe o `<?xml?>` na frente, que é o que um `.svg` **como arquivo** leva.

    `margem` é a faixa em volta, em unidades do `viewBox`; `None` é `MARGEM`, que é o EPUB de hoje.
    Ela é **argumento desde a S-544** porque o lote de diagramas escolhe uma proporção só para os
    dois formatos: a faixa daqui era um terço da casa e a de `diagrama_png.py` dois quintos, e o
    PNG e o SVG do mesmo diagrama saíam com molduras de larguras diferentes. O que a acompanha
    escala junto -- o corpo da régua e o raio da plaqueta --, para que passar a faixa de hoje
    devolva o desenho de hoje, unidade por unidade.
    """
    tabuleiro = tabuleiro_de(fen_ou_placement)
    lado = lado_da_fen(fen_ou_placement) if lado_a_jogar is None else lado_a_jogar.lower()
    paleta = (cores or cores_padrao()).resolvidas()

    faixa = MARGEM if margem is None else max(0, int(margem))
    margem = faixa if (com_reguas or lado) else 0
    lado_total = 8 * CASA + 2 * margem
    raiz = ET.Element(
        "svg",
        {
            "xmlns": SVG_NS,
            "xmlns:xlink": XLINK_NS,
            "viewBox": f"0 0 {lado_total} {lado_total}",
            "width": f"{largura_em:g}{unidade}",
            "height": f"{largura_em:g}{unidade}",
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
        _ponto_do_lado(raiz, margem, lado, paleta, virado=virado)
    return (DECLARACAO_XML if declaracao else "") + ET.tostring(raiz, encoding="unicode")


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
    corpo = TAMANHO_DA_REGUA * margem / MARGEM
    comum = {
        "class": "regua",
        "fill": paleta.coordenada,
        "font-family": "sans-serif",
        "font-size": f"{corpo:g}",
        "font-weight": "bold",
        "text-anchor": "middle",
    }
    base = margem + 8 * CASA
    for indice, letra in enumerate(colunas):
        x = margem + indice * CASA + CASA / 2
        texto = ET.SubElement(raiz, "text", {**comum, "x": f"{x:g}", "y": f"{base + margem * 0.75:g}"})
        texto.text = letra
    for indice, numero in enumerate(linhas):
        y = margem + indice * CASA + CASA / 2 + corpo / 3
        texto = ET.SubElement(raiz, "text", {**comum, "x": f"{margem / 2:g}", "y": f"{y:g}"})
        texto.text = numero


def _ponto_do_lado(raiz: ET.Element, margem: int, lado: str, paleta: Cores, *, virado: bool = False) -> None:
    """A plaqueta da margem direita: círculo vazado para as brancas, cheio para as pretas.

    **Ela fica do lado em que aquele jogador está sentado**, e não sempre embaixo: com as pretas
    embaixo (`virado`), "pretas jogam" é uma marca no pé do diagrama, junto de quem joga. Era o que
    faltava -- o diagrama virado dizia "as pretas jogam" apontando para o alto, que é onde as
    brancas estavam.

    O quadrado claro por baixo é o que a torna visível: a moldura é escura, e um círculo escuro sobre
    ela tem razão de contraste 1,0:1. Sobre `CASA_CLARA` os dois estados passam de 12:1 -- o cheio
    pela tinta, o vazado pelo contorno --, e é o mesmo par de tintas com que uma peça é desenhada.
    """
    brancas = lado == "w"
    embaixo = brancas != virado
    raio = RAIO_DO_LADO * margem / MARGEM
    x = margem + 8 * CASA + margem / 2
    y = margem + 8 * CASA - raio - 1 if embaixo else margem + raio + 1
    meia = raio + 1.5
    ET.SubElement(
        raiz,
        "rect",
        {
            "class": "plaqueta-do-lado",
            "x": f"{x - meia:g}",
            "y": f"{y - meia:g}",
            "width": f"{2 * meia:g}",
            "height": f"{2 * meia:g}",
            "fill": paleta.clara,
        },
    )
    ET.SubElement(
        raiz,
        "circle",
        {
            "class": "lado-a-jogar brancas" if brancas else "lado-a-jogar pretas",
            "cx": f"{x:g}",
            "cy": f"{y:g}",
            "r": f"{raio:g}",
            "fill": paleta.peca_clara if brancas else paleta.peca_escura,
            "stroke": paleta.peca_escura,
            "stroke-width": "1",
        },
    )
