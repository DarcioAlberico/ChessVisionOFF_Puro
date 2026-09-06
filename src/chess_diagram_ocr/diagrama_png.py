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

O que se decide aqui é só o desenho de bitmap. A orientação (`virado`), a ordem das réguas, o canto
em que a plaqueta do lado a jogar cai e as cores são **as mesmas de `diagrama_svg.py`**, tomadas de `ui/desenho_do_tabuleiro.reguas` e de
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
from chess_diagram_ocr.ui.pecas import engrossar_traco

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
"""A faixa das réguas e do ponto do lado a jogar. Dois quintos da casa, e é o **padrão**.

**Ela dizia "como `MARGEM` no SVG", e não era** (S-544): lá a faixa é 15 sobre uma casa de 45, um
terço, e o PNG e o SVG do mesmo diagrama saíam com molduras de larguras diferentes. Quem precisa
dos dois iguais passa a faixa por argumento, em proporção da casa -- `ui/lote_de_diagramas.Opcoes`
a declara uma vez e entrega pronta aos dois desenhistas. Este número continua sendo o do DOCX, que
é onde ele foi medido com uma régua de fonte real desenhada dentro dele."""

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
    casa_px: int = CASA_PX,
    margem: int | None = None,
    engrossar: bool = False,
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
        casa_px=casa_px,
        margem=margem,
        engrossar=engrossar,
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
    casa_px: int = CASA_PX,
    margem: int | None = None,
    engrossar: bool = False,
) -> Image.Image:
    """A `Image` RGB do diagrama, para quem quer compor antes de gravar.

    **Os três últimos são da S-544**, e não existiam porque o DOCX não precisava deles: o par
    PNG+SVG de lá sai sempre no tamanho em que as peças foram desenhadas. Um lote de diagramas
    soltos, não -- quem diagrama em outro programa pede uma largura em pixel, e a página que ele
    vai imprimir a 300 pontos por polegada não cabe em 616.

    - `casa_px` é o lado da casa. `CASA_PX` é o dos PNGs de `assets/piece_images/`, e continua
      sendo o padrão pela razão do cabeçalho: reamostrar apaga o traço fino das peças brancas.
      Abaixo dele, quem pede o tamanho pequeno pede junto o conjunto de traço grosso (`engrossar`),
      que é o que `ui/conjuntos.TRACO` existe para responder.
    - `margem` é a faixa das réguas, em pixel; `None` é `MARGEM_PX`. O que a acompanha escala
      junto -- o corpo da régua e o raio da plaqueta --, como no SVG.
    - `engrossar` aplica `ui/pecas.engrossar_traco` **depois** de reduzir, que é onde a linha
      sumiu (S-230).
    """
    tabuleiro = tabuleiro_de(fen_ou_placement)
    lado = lado_da_fen(fen_ou_placement) if lado_a_jogar is None else lado_a_jogar.lower()
    paleta = (cores or cores_padrao()).resolvidas()
    casa_px = max(8, int(casa_px))
    faixa = round(MARGEM_PX * casa_px / CASA_PX) if margem is None else max(0, int(margem))
    borda = faixa if (com_reguas or lado) else 0
    lado_total = 8 * casa_px + 2 * borda

    imagem = Image.new("RGB", (lado_total, lado_total), paleta.moldura)
    desenho = ImageDraw.Draw(imagem)
    for casa in chess.SQUARES:
        clara = (chess.square_file(casa) + chess.square_rank(casa)) % 2 == 1
        x, y = _xy(casa, borda, virado, casa_px)
        desenho.rectangle((x, y, x + casa_px - 1, y + casa_px - 1), fill=paleta.clara if clara else paleta.escura)

    pecas = _Pecas(pasta_de_pecas or PASTA_DE_PECAS, paleta, casa_px=casa_px, engrossar=engrossar)
    for casa, peca in sorted(tabuleiro.piece_map().items()):
        pecas.colar(imagem, peca, _xy(casa, borda, virado, casa_px))

    if com_reguas:
        _reguas(desenho, borda, virado, paleta, casa_px)
    if lado:
        _ponto_do_lado(desenho, borda, lado, paleta, virado=virado, casa_px=casa_px)
    return imagem


def _xy(casa: int, margem: int, virado: bool, casa_px: int = CASA_PX) -> tuple[int, int]:
    """A mesma `_posicao` de `diagrama_svg`: virado espelha a coluna e deixa a fileira crescer."""
    coluna, fileira = chess.square_file(casa), chess.square_rank(casa)
    if virado:
        return margem + (7 - coluna) * casa_px, margem + fileira * casa_px
    return margem + coluna * casa_px, margem + (7 - fileira) * casa_px


class _Pecas:
    """Os PNGs abertos uma vez por diagrama, e a letra no lugar de quem faltar.

    **Falta de arquivo não derruba a exportação**: `qt/tabuleiro.py` já degrada para glifo quando
    a pasta não existe, e um DOCX com `K` desenhado numa casa é melhor que nenhum DOCX. O aviso vai
    para o log uma vez por peça.
    """

    def __init__(
        self, pasta: Path, paleta: Cores, *, casa_px: int = CASA_PX, engrossar: bool = False
    ) -> None:
        self.pasta = pasta
        self.paleta = paleta
        self.casa_px = casa_px
        self.engrossar = engrossar
        self.abertas: dict[str, Image.Image | None] = {}

    def colar(self, imagem: Image.Image, peca: chess.Piece, xy: tuple[int, int]) -> None:
        nome = f"{'w' if peca.color == chess.WHITE else 'b'}{peca.symbol().lower()}"
        figura = self._imagem(nome)
        if figura is not None:
            imagem.paste(figura, xy, figura)
            return
        desenho = ImageDraw.Draw(imagem)
        fonte = _fonte(int(self.casa_px * 0.6))
        desenho.text(
            (xy[0] + self.casa_px / 2, xy[1] + self.casa_px / 2),
            peca.symbol(),
            fill=self.paleta.coordenada,
            font=fonte,
            anchor="mm",
        )

    def _imagem(self, nome: str) -> Image.Image | None:
        """A peça já no tamanho da casa, e engrossada quando o conjunto pede.

        Guardada **pronta** e não crua: um lote de quinhentos diagramas redimensionaria as mesmas
        doze peças dezesseis mil vezes, e a reamostragem é o passo caro do desenho.
        """
        if nome not in self.abertas:
            caminho = self.pasta / f"{nome}.png"
            try:
                figura = Image.open(caminho).convert("RGBA")
            except OSError:
                logger.warning("Peça %s não encontrada em %s; sai como letra.", nome, self.pasta)
                self.abertas[nome] = None
                return None
            if figura.size != (self.casa_px, self.casa_px):
                figura = figura.resize((self.casa_px, self.casa_px), Image.Resampling.LANCZOS)
            self.abertas[nome] = engrossar_traco(figura) if self.engrossar else figura
        return self.abertas[nome]


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=tamanho)
    except (TypeError, OSError):  # pragma: no cover - Pillow sem a fonte embutida escalável
        return ImageFont.load_default()


def _reguas(
    desenho: ImageDraw.ImageDraw, margem: int, virado: bool, paleta: Cores, casa_px: int = CASA_PX
) -> None:
    """As letras embaixo e os números à esquerda, na ordem de `desenho_do_tabuleiro.reguas`."""
    colunas, linhas = reguas(virado)
    fonte = _fonte(max(6, round(TAMANHO_DA_REGUA_PX * casa_px / CASA_PX)))
    base = margem + 8 * casa_px
    for indice, letra in enumerate(colunas):
        x = margem + indice * casa_px + casa_px / 2
        desenho.text((x, base + margem / 2), letra, fill=paleta.coordenada, font=fonte, anchor="mm")
    for indice, numero in enumerate(linhas):
        y = margem + indice * casa_px + casa_px / 2
        desenho.text((margem / 2, y), numero, fill=paleta.coordenada, font=fonte, anchor="mm")


def _ponto_do_lado(
    desenho: ImageDraw.ImageDraw,
    margem: int,
    lado: str,
    paleta: Cores,
    *,
    virado: bool = False,
    casa_px: int = CASA_PX,
) -> None:
    """A plaqueta da margem direita, **com a mesma geometria e as mesmas tintas do SVG**.

    O par PNG+SVG do DOCX é a mesma figura duas vezes: se um deles pusesse a marca do lado a jogar
    em outro canto, o Word e o LibreOffice mostrariam diagramas diferentes do mesmo arquivo.
    """
    brancas = lado == "w"
    embaixo = brancas != virado
    raio = max(2.0, RAIO_DO_LADO_PX * casa_px / CASA_PX)
    x = margem + 8 * casa_px + margem / 2
    y = margem + 8 * casa_px - raio - 2 if embaixo else margem + raio + 2
    meia = raio + 3
    desenho.rectangle((x - meia, y - meia, x + meia, y + meia), fill=paleta.clara)
    caixa = (x - raio, y - raio, x + raio, y + raio)
    desenho.ellipse(caixa, fill=paleta.peca_clara if brancas else paleta.peca_escura, outline=paleta.peca_escura, width=1)
