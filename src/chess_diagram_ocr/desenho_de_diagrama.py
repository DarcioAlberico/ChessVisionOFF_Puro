# Origem: Editor_Diagramas_de_Xadrez/src/chess_pdf_editor/renderer.py
#         (`render_board_pdf`, `render_board_png`, `_find_merida_font`, `_merida_rows`,
#          `_render_with_merida_font_pdf`, `_render_with_merida_font`, `_render_with_python_chess*`).
# Absorvido em 2026-09-07. Alterações: (a) a reserva raster deixou de desenhar glifo Unicode em
#         Arial e passa a compor os **PNGs do próprio tronco** (`assets/piece_images/`) com o
#         `engrossar_traco` da S-230 -- o tronco tem conjunto de peças, e desenhar um segundo
#         seria a duplicação que a `ASSETS §6` proíbe; (b) as cores das casas saíram de
#         `(240, 217, 181)` cravado e passaram a ser `ui/tokens.CASA_CLARA`/`CASA_ESCURA`, que
#         são exatamente os mesmos valores e agora têm um dono só; (c) `to_full_fen` virou
#         `semantics.compose_fen`, que é o que este projeto usa desde a S-67; (d) as saídas em
#         PDF vetorial e SVG saíram na S-881, com a substituição de diagrama que as chamava.
"""Um campo de peças virando PNG, sem Qt.

**Para que serve.** A aba Texto desenha a posição lida quando a folha não está à mão, e o livro
com PGN desenha o diagrama a partir da partida; os dois pedem bytes de imagem, não widget. O
tronco desenha tabuleiro muito bem em `qt/tabuleiro.py`, mas ali o desenho é um `QPainter` sobre
um `QWidget`: precisa de `QApplication`, e não roda em lote nem em thread de trabalho. Por isso o
módulo mora na raiz do pacote, só com PIL, e não em `ui/` nem em `qt/`.

O módulo nasceu para a substituição de diagrama dentro do PDF (F9), com PDF vetorial e SVG além
do PNG; a substituição foi retirada na S-881 (decisão D7 da solidez), e as duas saídas com ela.

**Duas fontes de desenho.** Com uma fonte de xadrez (Merida) instalada, o PNG sai dela; sem ela,
que é o caso normal (o tronco não a distribui), sai das peças do próprio tronco.

**Por que reusar as peças do tronco é o item, e não detalhe.** A `ASSETS §6` manda procurar a
implementação existente e estendê-la. O tronco tem doze peças em `assets/piece_images/`, tem um
registro de conjuntos (`ui/conjuntos.py`), tem o filtro de traço grosso medido da S-230
(`ui/pecas.engrossar_traco`) e tem as cores das casas com papel em `ui/tokens.py`. Um segundo
desenho de tabuleiro produziria diagramas **diferentes** no que se exporta e na tela que o
exportou -- duas respostas para a mesma pergunta, que é o defeito que a S-158 nomeia. A origem
desenhava glifo Unicode em Arial, um desenho que nenhuma outra tela do programa usa.
"""

from __future__ import annotations

import io
import logging
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.ui import board_edit, conjuntos, pecas, tokens
from chess_diagram_ocr.ui.desenho_do_tabuleiro import UNICODE_PIECES

logger = logging.getLogger(__name__)

__all__ = [
    "FONTE_MERIDA_ENV",
    "LADO_PADRAO_PX",
    "png_do_diagrama",
]

LADO_PADRAO_PX = 1024
"""O lado do tabuleiro renderizado, quando ninguém pede outro."""

FONTE_MERIDA_ENV = "CVOFF_MERIDA_FONT"
"""A variável que aponta uma fonte de xadrez para o desenho.

**Renomeada da origem** (`CHESS_MERIDA_FONT`) para o prefixo do projeto, que é o de
`conjuntos.CONJUNTO_ENV` (`CVOFF_PIECES`) -- duas variáveis de ambiente com prefixos diferentes
no mesmo programa é o tipo de coisa que ninguém descobre sem ler o código."""

PASTA_DE_FONTES = BUNDLE_ROOT / "assets" / "fonts"
"""Onde uma fonte de xadrez é procurada. `BUNDLE_ROOT` pela razão da S-55: recurso
somente-leitura viaja dentro do pacote.

A pasta **não** faz parte do repositório: a Merida é uma fonte de terceiros, e o tronco não a
distribui. Sem ela o desenho sai das peças do tronco, que sempre existem."""

_NOMES_DE_MERIDA = ("Merida.ttf", "MERIDA.TTF", "Merida.otf", "MERIDA.OTF", "chessmerida.otf")

# A Merida é uma fonte legada: as peças estão mapeadas em letras ASCII, com uma variante por cor
# de casa, e não nos code points Unicode de xadrez. Usar `UNICODE_PIECES` com ela produziria
# apenas `.notdef` -- o que é pior que não desenhar, porque o retângulo sai cheio de caixinhas.
_GLIFO_EM_CASA_CLARA = {
    "P": "p", "N": "n", "B": "b", "R": "r", "Q": "q", "K": "k",
    "p": "o", "n": "m", "b": "v", "r": "t", "q": "w", "k": "l",
    "": " ",
}
_GLIFO_EM_CASA_ESCURA = {
    "P": "P", "N": "N", "B": "B", "R": "R", "Q": "Q", "K": "K",
    "p": "O", "n": "M", "b": "V", "r": "T", "q": "W", "k": "L",
    "": "+",
}


def _rgb(papel: str) -> tuple[int, int, int]:
    """O papel de `ui/tokens.py` como triplo para o PIL. **Nenhum hexadecimal cravado aqui.**"""
    valor = tokens.cor(papel).lstrip("#")
    return (int(valor[0:2], 16), int(valor[2:4], 16), int(valor[4:6], 16))


@lru_cache(maxsize=1)
def _procurar_merida(env: str, pasta: str) -> Path | None:
    candidatos: list[Path] = []
    if env.strip():
        candidatos.append(Path(env.strip()))
    raiz = Path(pasta)
    candidatos.extend(raiz / nome for nome in _NOMES_DE_MERIDA)
    if raiz.is_dir():
        candidatos.extend(
            caminho
            for caminho in sorted(raiz.iterdir())
            if caminho.suffix.lower() in (".ttf", ".otf") and "merida" in caminho.name.lower()
        )
    for caminho in candidatos:
        if caminho.is_file():
            return caminho
    return None


def fonte_merida() -> Path | None:
    """A fonte de xadrez em vigor, ou `None`. O resultado é lembrado por par (variável, pasta).

    O cache é por argumento e não global justamente para o teste poder apontar outra pasta sem
    envenenar a resposta do teste seguinte -- é a razão de `_procurar_merida` receber os dois
    valores em vez de lê-los de dentro.
    """
    return _procurar_merida(os.getenv(FONTE_MERIDA_ENV, ""), str(PASTA_DE_FONTES))


def _linhas_de_merida(placement: str) -> list[str]:
    """As oito fileiras como texto da fonte legada -- glifo por casa, variante por cor da casa."""
    casas = board_edit.squares_from_placement(board_edit.placement_of(placement))
    linhas: list[str] = []
    for fileira in range(8):
        letras: list[str] = []
        for coluna in range(8):
            simbolo = casas[fileira * 8 + coluna]
            escura = (fileira + coluna) % 2 == 1
            tabela = _GLIFO_EM_CASA_ESCURA if escura else _GLIFO_EM_CASA_CLARA
            letras.append(tabela[simbolo])
        linhas.append("".join(letras))
    return linhas


@lru_cache(maxsize=4)
def _pecas_carregadas(pasta: str, engrossa: bool) -> dict[str, Image.Image]:
    """Os doze PNGs do conjunto, em RGBA. Ausente fica **fora** do dicionário.

    Fora e não vazio, pela mesma razão de `qt/tabuleiro.carregar_pecas`: uma imagem nula desenha
    nada e não levanta, e o tabuleiro sairia vazio sem que ninguém pudesse dizer por quê. Fora do
    dicionário, o desenho cai no glifo -- que responde a pergunta.
    """
    raiz = Path(pasta)
    carregadas: dict[str, Image.Image] = {}
    for simbolo in UNICODE_PIECES:
        nome = ("w" if simbolo.isupper() else "b") + simbolo.lower()
        caminho = raiz / f"{nome}.png"
        if not caminho.is_file():
            continue
        try:
            with Image.open(caminho) as arquivo:
                imagem = arquivo.convert("RGBA")
        except OSError:
            logger.warning("Peça ilegível em %s; caindo no glifo", caminho)
            continue
        carregadas[simbolo] = pecas.engrossar_traco(imagem) if engrossa else imagem
    return carregadas


PASTA_DE_PECAS = BUNDLE_ROOT / "assets" / "piece_images"
"""Os mesmos PNGs que a janela desenha. `BUNDLE_ROOT` pela razão da S-55, como em `qt/tabuleiro.py`."""


def _pasta_do_conjunto(pasta_do_usuario: str = "") -> tuple[str, bool]:
    """A pasta das peças em vigor e se aquele conjunto engrossa o traço.

    Pergunta a `ui/conjuntos.py`, que é o registro do tronco, e não a um caminho fixo: quem
    trocou o conjunto vê o desenho com o conjunto que escolheu, e o traço grosso da S-230 vale
    igual no PNG.

    **A pasta do usuário entra por argumento e não é lida daqui.** Ela mora no estado da
    aplicação, e este módulo roda em lote e em thread de trabalho -- ler estado de janela num
    exportador seria a dependência que ele existe para não ter. Pasta vazia, ou que não existe,
    cai no padrão em vez de recusar, que é o que `qt/tabuleiro.pasta_do_conjunto` já faz.
    """
    registro = conjuntos.registrado(conjuntos.valida(conjuntos.escolhido()))
    escolhida = Path(pasta_do_usuario) if (registro.do_usuario and pasta_do_usuario) else PASTA_DE_PECAS
    return (str(escolhida if escolhida.is_dir() else PASTA_DE_PECAS), bool(registro.engrossa))


def png_do_diagrama(
    placement: str, *, lado_px: int = LADO_PADRAO_PX, pasta_do_usuario: str = ""
) -> bytes:
    """O diagrama como PNG. **Sempre responde** -- é a reserva que não depende de nada opcional."""
    lado = max(64, int(lado_px))
    com_merida = _png_com_merida(placement, lado_px=lado)
    if com_merida is not None:
        return com_merida
    return _png_com_pecas(placement, lado_px=lado, pasta_do_usuario=pasta_do_usuario)


def _png_com_merida(placement: str, *, lado_px: int) -> bytes | None:
    caminho = fonte_merida()
    if caminho is None:
        return None
    try:
        linhas = _linhas_de_merida(placement)
        imagem = Image.new("RGB", (lado_px, lado_px), "white")
        desenho = ImageDraw.Draw(imagem)
        casa = lado_px / 8.0
        fonte = ImageFont.truetype(str(caminho), max(22, int(casa * 0.98)))
        for fileira, linha in enumerate(linhas):
            for coluna, glifo in enumerate(linha):
                x0 = int(coluna * casa)
                y0 = int(fileira * casa)
                if glifo == " ":
                    # Casa clara vazia: a fonte não desenha nada, e o fundo já é branco.
                    continue
                tx0, ty0, tx1, ty1 = desenho.textbbox((0, 0), glifo, font=fonte)
                x = int(x0 + (casa - (tx1 - tx0)) / 2 - tx0)
                y = int(y0 + (casa - (ty1 - ty0)) / 2 - ty0)
                desenho.text((x, y), glifo, fill=(0, 0, 0), font=fonte)
        return _bytes_de(imagem)
    except Exception:  # noqa: BLE001 - fonte exótica não pode derrubar a exportação
        logger.warning("Falha no PNG com a fonte de xadrez para %r", placement, exc_info=True)
        return None


def _png_com_pecas(placement: str, *, lado_px: int, pasta_do_usuario: str = "") -> bytes:
    """As casas tingidas pelos papéis do tronco, com os PNGs do conjunto por cima.

    **O tabuleiro não segue tema**, e é o que `ui/tokens.CASA_CLARA` já registra: xadrez impresso
    é claro-e-escuro em qualquer tema, e um diagrama que mudasse de cor com a janela deixaria de
    ser reconhecível como diagrama -- ainda mais num PNG exportado, que ninguém abre na janela.
    """
    casas = board_edit.squares_from_placement(board_edit.placement_of(placement))
    clara = _rgb(tokens.CASA_CLARA)
    escura = _rgb(tokens.CASA_ESCURA)
    imagem = Image.new("RGB", (lado_px, lado_px), clara)
    desenho = ImageDraw.Draw(imagem)
    lado_da_casa = lado_px / 8.0

    pasta, engrossa = _pasta_do_conjunto(pasta_do_usuario)
    disponiveis = _pecas_carregadas(pasta, engrossa)
    corpo = max(12, int(lado_da_casa * 0.78))
    glifos = _fonte_de_glifo(corpo)

    for fileira in range(8):
        for coluna in range(8):
            x0 = int(coluna * lado_da_casa)
            y0 = int(fileira * lado_da_casa)
            x1 = int((coluna + 1) * lado_da_casa)
            y1 = int((fileira + 1) * lado_da_casa)
            if (fileira + coluna) % 2 == 1:
                desenho.rectangle([x0, y0, x1 - 1, y1 - 1], fill=escura)
            simbolo = casas[fileira * 8 + coluna]
            if not simbolo:
                continue
            peca = disponiveis.get(simbolo)
            if peca is not None:
                alvo = max(1, x1 - x0)
                escalada = peca.resize((alvo, max(1, y1 - y0)), Image.Resampling.LANCZOS)
                imagem.paste(escalada, (x0, y0), escalada)
            elif glifos is not None:
                _glifo(desenho, glifos, simbolo, (x0, y0, x1, y1))

    # A moldura de 2 px, um degrau abaixo da esteira: é o anel que assenta o tabuleiro no papel,
    # e ela tem papel próprio (`ui/tokens.MOLDURA`) desde a S-147.
    largura = max(1, int(round(lado_px / 340.0)))
    desenho.rectangle([0, 0, lado_px - 1, lado_px - 1], outline=_rgb(tokens.MOLDURA), width=largura)
    return _bytes_de(imagem)


def _fonte_de_glifo(corpo: int) -> ImageFont.FreeTypeFont | None:
    """A fonte da reserva de glifo Unicode. `None` quando nenhuma da lista existe.

    Nenhuma fonte é o caso do agente de CI sem fontes instaladas: ali a casa fica lisa e a
    posição não aparece, o que é honesto -- é melhor que uma fileira de retângulos `.notdef`,
    que parece desenho e não é. E é caso raro: sem peça **e** sem fonte.
    """
    for nome in ("seguisym.ttf", "DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(nome, corpo)
        except OSError:
            continue
    return None


def _glifo(
    desenho: ImageDraw.ImageDraw,
    fonte: ImageFont.FreeTypeFont,
    simbolo: str,
    casa: tuple[int, int, int, int],
) -> None:
    x0, y0, x1, y1 = casa
    texto = UNICODE_PIECES.get(simbolo, simbolo)
    tx0, ty0, tx1, ty1 = desenho.textbbox((0, 0), texto, font=fonte)
    x = int(x0 + ((x1 - x0) - (tx1 - tx0)) / 2 - tx0)
    y = int(y0 + ((y1 - y0) - (ty1 - ty0)) / 2 - ty0)
    tinta = tokens.GLIFO_CLARO if simbolo.isupper() else tokens.GLIFO_ESCURO
    desenho.text((x, y), texto, fill=_rgb(tinta), font=fonte)


def _bytes_de(imagem: Image.Image) -> bytes:
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
