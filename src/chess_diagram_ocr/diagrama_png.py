"""O diagrama como PNG, a partir da FEN, com as peças de `assets/piece_images/` (S-543).

**Por que existe ao lado de `diagrama_svg.py`.** O DOCX carrega duas imagens por diagrama: o SVG,
que o Word de 2016 em diante desenha como vetor, e um PNG de reserva, que é o que **todo** leitor de
`.docx` mostra -- o LibreOffice, o Google Docs, o Word antigo e o visualizador do celular. Um DOCX
só com SVG abre em branco em metade dessas máquinas; um só com PNG serrilha na impressão. Os dois
juntos é o que o próprio Word grava quando alguém cola um SVG nele, e é o que este par entrega.

**As peças são os PNGs do produto**, os doze de `assets/piece_images/` que a janela desenha, e não
uma rasterização do SVG: rasterizar o SVG exigiria um motor (o `QSvgRenderer` do Qt, ou o `cairosvg`
do extra `second-opinion`), e este módulo é puro de propósito -- o teste roda sem janela, e o
exportador funciona no `--selftest`. A casa mede **70 px**, o tamanho em que os PNGs foram
desenhados: reduzi-los para caber num quadrado menor apagaria o traço fino das peças brancas, que
é o defeito que `ui/conjuntos.TRACO` já registrou.

O que se decide aqui é só o desenho de bitmap. A orientação (`virado`), a ordem das réguas e as
cores são **as mesmas de `diagrama_svg.py`**, tomadas de `ui/desenho_do_tabuleiro.reguas` e de
`ui/tokens.py`: os dois formatos de um mesmo diagrama mostram a mesma coisa, ou o par PNG+SVG do
DOCX discordaria de si mesmo. Sem Qt aqui, e sem arquivo: quem grava é `docx_saida.py`.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import chess
from PIL import Image, ImageDraw, ImageFont

from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.diagrama_svg import Cores, cores_padrao, lado_da_fen, tabuleiro_de
from chess_diagram_ocr.ui.desenho_do_tabuleiro import reguas

logger = logging.getLogger(__name__)

__all__ = [
    "CASA_PX",
    "MARGEM_PX",
    "PASTA_DE_PECAS",
    "imagem_da_posicao",
    "png_da_posicao",
]

CASA_PX = 70
"""O lado da casa em pixels: **o tamanho dos PNGs de `assets/piece_images/`**, sem reamostragem."""

MARGEM_PX = 28
"""A faixa das réguas e do ponto do lado a jogar. Dois quintos da casa, como `MARGEM` no SVG."""

PASTA_DE_PECAS = BUNDLE_ROOT / "assets" / "piece_images"
"""A mesma pasta de `qt/tabuleiro.PASTA_DE_PECAS`: peça é recurso do bundle, não do checkout."""

CORES_DO_PNG = 64
"""Quantas cores a paleta do PNG guarda. Ver `png_da_posicao`."""

TAMANHO_DA_REGUA_PX = 14
RAIO_DO_LADO_PX = 7


def png_da_posicao(
    fen_ou_placement: str,
    *,
    virado: bool = False,
    com_reguas: bool = True,
    lado_a_jogar: str | None = None,
    cores: Cores | None = None,
    pasta_de_pecas: Path | None = None,
) -> bytes:
    """Os bytes PNG do diagrama. Mesma assinatura de `diagrama_svg.svg_da_posicao`, menos o `em`.

    **Sai em paleta de `CORES_DO_PNG` cores, e não em RGB.** Medido na posição da italiana: 55 KB em
    RGB, 20 KB com 64 cores, sem diferença visível -- o diagrama é quatro cores chapadas mais o
    serrilhado das peças. Num livro de 2.618 estudos são 90 MB a menos no `.docx`.
    """
    imagem = imagem_da_posicao(
        fen_ou_placement,
        virado=virado,
        com_reguas=com_reguas,
        lado_a_jogar=lado_a_jogar,
        cores=cores,
        pasta_de_pecas=pasta_de_pecas,
    )
    saida = io.BytesIO()
    imagem.quantize(colors=CORES_DO_PNG).save(saida, format="PNG", optimize=True)
    return saida.getvalue()


def imagem_da_posicao(
    fen_ou_placement: str,
    *,
    virado: bool = False,
    com_reguas: bool = True,
    lado_a_jogar: str | None = None,
    cores: Cores | None = None,
    pasta_de_pecas: Path | None = None,
) -> Image.Image:
    """A `Image` RGB do diagrama, para quem quer compor antes de gravar."""
    tabuleiro = tabuleiro_de(fen_ou_placement)
    lado = lado_da_fen(fen_ou_placement) if lado_a_jogar is None else lado_a_jogar.lower()
    paleta = cores or cores_padrao()
    margem = MARGEM_PX if (com_reguas or lado) else 0
    lado_total = 8 * CASA_PX + 2 * margem

    imagem = Image.new("RGB", (lado_total, lado_total), paleta.moldura)
    desenho = ImageDraw.Draw(imagem)
    for casa in chess.SQUARES:
        clara = (chess.square_file(casa) + chess.square_rank(casa)) % 2 == 1
        x, y = _xy(casa, margem, virado)
        desenho.rectangle((x, y, x + CASA_PX - 1, y + CASA_PX - 1), fill=paleta.clara if clara else paleta.escura)

    pecas = _Pecas(pasta_de_pecas or PASTA_DE_PECAS, paleta)
    for casa, peca in sorted(tabuleiro.piece_map().items()):
        pecas.colar(imagem, peca, _xy(casa, margem, virado))

    if com_reguas:
        _reguas(desenho, margem, virado, paleta)
    if lado:
        _ponto_do_lado(desenho, margem, lado, paleta)
    return imagem


def _xy(casa: int, margem: int, virado: bool) -> tuple[int, int]:
    """A mesma `_posicao` de `diagrama_svg`: virado espelha a coluna e deixa a fileira crescer."""
    coluna, fileira = chess.square_file(casa), chess.square_rank(casa)
    if virado:
        return margem + (7 - coluna) * CASA_PX, margem + fileira * CASA_PX
    return margem + coluna * CASA_PX, margem + (7 - fileira) * CASA_PX


class _Pecas:
    """Os PNGs abertos uma vez por diagrama, e a letra no lugar de quem faltar.

    **Falta de arquivo não derruba a exportação**: `qt/tabuleiro.py` já degrada para glifo quando
    a pasta não existe, e um DOCX com `K` desenhado numa casa é melhor que nenhum DOCX. O aviso vai
    para o log uma vez por peça.
    """

    def __init__(self, pasta: Path, paleta: Cores) -> None:
        self.pasta = pasta
        self.paleta = paleta
        self.abertas: dict[str, Image.Image | None] = {}

    def colar(self, imagem: Image.Image, peca: chess.Piece, xy: tuple[int, int]) -> None:
        nome = f"{'w' if peca.color == chess.WHITE else 'b'}{peca.symbol().lower()}"
        figura = self._imagem(nome)
        if figura is not None:
            if figura.size != (CASA_PX, CASA_PX):
                figura = figura.resize((CASA_PX, CASA_PX), Image.Resampling.LANCZOS)
            imagem.paste(figura, xy, figura)
            return
        desenho = ImageDraw.Draw(imagem)
        fonte = _fonte(int(CASA_PX * 0.6))
        desenho.text(
            (xy[0] + CASA_PX / 2, xy[1] + CASA_PX / 2),
            peca.symbol(),
            fill=self.paleta.coordenada,
            font=fonte,
            anchor="mm",
        )

    def _imagem(self, nome: str) -> Image.Image | None:
        if nome not in self.abertas:
            caminho = self.pasta / f"{nome}.png"
            try:
                self.abertas[nome] = Image.open(caminho).convert("RGBA")
            except OSError:
                logger.warning("Peça %s não encontrada em %s; sai como letra.", nome, self.pasta)
                self.abertas[nome] = None
        return self.abertas[nome]


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=tamanho)
    except (TypeError, OSError):  # pragma: no cover - Pillow sem a fonte embutida escalável
        return ImageFont.load_default()


def _reguas(desenho: ImageDraw.ImageDraw, margem: int, virado: bool, paleta: Cores) -> None:
    """As letras embaixo e os números à esquerda, na ordem de `desenho_do_tabuleiro.reguas`."""
    colunas, linhas = reguas(virado)
    fonte = _fonte(TAMANHO_DA_REGUA_PX)
    base = margem + 8 * CASA_PX
    for indice, letra in enumerate(colunas):
        x = margem + indice * CASA_PX + CASA_PX / 2
        desenho.text((x, base + margem / 2), letra, fill=paleta.coordenada, font=fonte, anchor="mm")
    for indice, numero in enumerate(linhas):
        y = margem + indice * CASA_PX + CASA_PX / 2
        desenho.text((margem / 2, y), numero, fill=paleta.coordenada, font=fonte, anchor="mm")


def _ponto_do_lado(desenho: ImageDraw.ImageDraw, margem: int, lado: str, paleta: Cores) -> None:
    """O ponto da margem direita: embaixo para as brancas, em cima para as pretas, como no SVG."""
    brancas = lado == "w"
    x = margem + 8 * CASA_PX + margem / 2
    y = margem + 8 * CASA_PX - RAIO_DO_LADO_PX - 2 if brancas else margem + RAIO_DO_LADO_PX + 2
    caixa = (x - RAIO_DO_LADO_PX, y - RAIO_DO_LADO_PX, x + RAIO_DO_LADO_PX, y + RAIO_DO_LADO_PX)
    desenho.ellipse(caixa, fill=paleta.clara if brancas else paleta.moldura, outline=paleta.coordenada, width=1)
