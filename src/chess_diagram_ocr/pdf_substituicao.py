# Origem: Editor_Diagramas_de_Xadrez/src/chess_pdf_editor/pdf_service.py
#         (`_write_space_cropbox`, `_to_write_space`, `_erase_rects`, `apply_page_operations`,
#          `find_coordinate_labels`, `_insert_lichess_link_below_diagram`, `lichess_analysis_url`,
#          `render_page_with_operations`, `apply_operations_to_pdf`, `crop_from_rendered_page`).
# Absorvido em 2026-09-07. Alterações: (a) as decisões saíram para `ui/substituicao.py` -- aqui
#         ficou o que fala PyMuPDF; (b) o desenho do tabuleiro passou a ser o do tronco
#         (`desenho_de_diagrama.py`), com as peças de `assets/piece_images/`; (c) a gravação usa
#         `atomic_io.atomic_write_bytes`, que é o gravador atômico do tronco (S-25/S-373) e já traz
#         a segunda chance do Windows -- o `_CancelableWriter` da origem (ASSETS §2.9) **não** veio,
#         e o porquê está em `gravar_pdf`.
"""Apagar um diagrama de uma página e carimbar outro no lugar (F9).

**A capacidade.** Um livro de xadrez traz o diagrama impresso como imagem ou como texto de uma
fonte legada; nos dois casos ele é ilegível para quem lê em tela pequena, e em nenhum dos dois é
possível analisar a posição. Este módulo troca o diagrama por um desenhado agora, **no mesmo
lugar da página**, com o resto do livro intacto -- e opcionalmente com um link de análise.

**O que dá errado, e por isso o módulo existe (ASSETS §2.8).** Uma página com `/Rotate` -- livro
escaneado de lado -- ou com CropBox deslocada -- livro preparado para impressão -- tem **dois**
espaços de coordenada. O retângulo que a pessoa selecionou está no espaço de `page.rect`; escrever
no conteúdo da página é no espaço de escrita. Sem converter, o apagamento não cobre o diagrama
original e o tabuleiro novo vai para outro lugar, deitado. A conversão em si é pura e mora em
`ui/substituicao.EspacoDeEscrita`; o que fica aqui é lê-la do documento, em quatro linhas.

**Um caminho de código só para a prévia e para a exportação.** `aplicar_na_pagina` é o ponto
único: o que a comparação mostra na tela é literalmente o que o PDF exportado vai conter, porque
é a mesma função sobre a mesma página. Duas implementações "equivalentes" divergiriam no primeiro
campo novo -- e a origem registra exatamente isso tendo acontecido com o link por diagrama.

**Fora de `ui/` pela mesma regra de `pdf_io.py`**: leitura e escrita de arquivo não são decisão de
interface. Nada aqui importa toolkit, e é isso que permite exportar um livro inteiro sem janela.
"""

from __future__ import annotations

import io
import logging
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from urllib.parse import quote

import fitz
from PIL import Image

from chess_diagram_ocr import desenho_de_diagrama
from chess_diagram_ocr.atomic_io import atomic_write_bytes
from chess_diagram_ocr.semantics import compose_fen
from chess_diagram_ocr.ui.substituicao import (
    Apagamento,
    EspacoDeEscrita,
    Retangulo,
    Substituicao,
    assinatura_da_pagina,
    folga_aplicada,
    quer_link_lichess,
    vazio,
)

logger = logging.getLogger(__name__)

__all__ = [
    "COBERTURA_MINIMA_DA_CORRIDA",
    "DPI_DO_CARIMBO",
    "FAIXA_DE_COORDENADA",
    "MINIMO_DE_COORDENADAS_EM_FILA",
    "PaginaRenderizada",
    "ServicoDeSubstituicao",
    "achar_coordenadas",
    "aplicar_na_pagina",
    "apagar_retangulos",
    "cropbox_de_escrita",
    "espaco_de_escrita",
    "fen_completa",
    "gravar_pdf",
    "limpar_cache_de_desenho",
    "recorte_de_png",
    "substituir_no_pdf",
    "url_da_operacao",
    "url_de_analise",
]


# --------------------------------------------------------------------- os dois espaços


def cropbox_de_escrita(pagina: fitz.Page) -> fitz.Rect:
    """A CropBox -- a região visível -- em coordenadas de escrita.

    **É também o recorte correto para qualquer retângulo já convertido**, e isto é o que se erra:
    numa página girada, `page.rect` tem largura e altura trocadas em relação ao espaço de
    escrita, e usá-lo como limite corta o que é válido. O sintoma é uma substituição que sai pela
    metade, ou uma coordenada legítima que o detector descarta.
    """
    media = pagina.mediabox
    crop = pagina.cropbox
    nativo = fitz.Rect(crop.x0, media.y1 - crop.y1, crop.x1, media.y1 - crop.y0)
    return nativo * pagina.transformation_matrix


def espaco_de_escrita(pagina: fitz.Page) -> EspacoDeEscrita:
    """As três coisas que a conversão precisa, lidas do documento. O resto é aritmética.

    A origem é o canto superior-esquerdo da CropBox **no espaço de escrita**; sem rotação ela é
    `(0, 0)`, porque a `transformation_matrix` já embute o deslocamento -- e é por isso que o caso
    comum atravessa isto inalterado.
    """
    origem = cropbox_de_escrita(pagina).tl
    derotacao = pagina.derotation_matrix
    rotacao = pagina.rotation_matrix
    return EspacoDeEscrita(
        origem=(float(origem.x), float(origem.y)),
        derotacao=(derotacao.a, derotacao.b, derotacao.c, derotacao.d, derotacao.e, derotacao.f),
        rotacao=(rotacao.a, rotacao.b, rotacao.c, rotacao.d, rotacao.e, rotacao.f),
    )


def _retangulo(valores: Retangulo) -> fitz.Rect:
    return fitz.Rect(*valores)


# --------------------------------------------------------------------- render


@dataclass(frozen=True)
class PaginaRenderizada:
    """Uma página virada bitmap, com a matriz que leva ponto do PDF a pixel da imagem.

    A matriz viaja junto e não é recalculada por quem recebe: o zoom pode ter mudado entre o
    render e o clique, e um retângulo convertido com a matriz errada afirma que o diagrama está
    onde ele não está -- que é pior do que não marcar nada (é a razão que `ui/page_overlay.py`
    já registra para o DPI viajar com as caixas).
    """

    pagina: int
    largura_px: int
    altura_px: int
    png: bytes
    matriz: tuple[float, float, float, float, float, float]


def _png_do_pixmap(pix: fitz.Pixmap) -> bytes:
    """RGBA composto sobre branco.

    Compor e não converter: um PDF com transparência ou máscara -- livro digitalizado com fundo
    recortado -- vira mancha preta quando o canal alfa é simplesmente descartado.
    """
    rgba = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    rgb = Image.new("RGB", rgba.size, "white")
    rgb.paste(rgba, mask=rgba.getchannel("A"))
    buffer = io.BytesIO()
    rgb.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _renderizar(pagina: fitz.Page, numero: int, zoom: float) -> PaginaRenderizada:
    matriz = fitz.Matrix(zoom, zoom)
    pix = pagina.get_pixmap(matrix=matriz, colorspace=fitz.csRGB, alpha=True)
    return PaginaRenderizada(
        pagina=numero,
        largura_px=pix.width,
        altura_px=pix.height,
        png=_png_do_pixmap(pix),
        matriz=(matriz.a, matriz.b, matriz.c, matriz.d, matriz.e, matriz.f),
    )


def _renderizar_regiao(pagina: fitz.Page, zoom: float, retangulo: Retangulo) -> bytes:
    recorte = _retangulo(retangulo) & pagina.rect
    if recorte.is_empty:
        raise ValueError("A região pedida não tem interseção com a página.")
    pix = pagina.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=True, clip=recorte)
    return _png_do_pixmap(pix)


def recorte_de_png(png: bytes, retangulo: Retangulo) -> bytes:
    """Um pedaço de uma página já renderizada, em pixel da imagem. É o "antes" da comparação."""
    imagem = Image.open(io.BytesIO(png)).convert("RGB")
    x0, y0, x1, y1 = retangulo
    ax = max(0, int(round(min(x0, x1))))
    ay = max(0, int(round(min(y0, y1))))
    bx = min(imagem.width, int(round(max(x0, x1))))
    by = min(imagem.height, int(round(max(y0, y1))))
    if bx <= ax or by <= ay:
        raise ValueError("Seleção inválida para recorte.")
    buffer = io.BytesIO()
    imagem.crop((ax, ay, bx, by)).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# --------------------------------------------------------------------- desenho, com cache

DPI_DO_CARIMBO = 450
"""A resolução com que o diagrama é rasterizado quando o caminho vetorial não existe.

450 e não 300: o retângulo de um diagrama de livro mede ~140 pt de lado, o que a 300 dpi dá 583
px -- perto demais do limite em que a linha da peça começa a serrilhar quando alguém amplia o PDF
para conferir uma casa, que é exatamente o que se faz com um diagrama de exercício."""

_TETO_DO_CACHE = 48
"""Quantos desenhos ficam guardados. Mesma FEN e mesmo lado dão o mesmo asset, e a prévia
re-renderiza a cada ajuste de folga -- sem cache, mexer num campo numérico redesenha 64 casas a
cada tecla."""

_cache_pdf: OrderedDict[tuple[str, int, str], bytes | None] = OrderedDict()
_cache_png: OrderedDict[tuple[str, int, str], bytes] = OrderedDict()
_trava = Lock()
"""A exportação roda numa thread enquanto a prévia continua desenhando na linha de eventos: as
duas mexem nestes dicionários, e `move_to_end` + `popitem` não são atômicos entre si."""


def limpar_cache_de_desenho() -> None:
    with _trava:
        _cache_pdf.clear()
        _cache_png.clear()


def _guardado(
    cache: OrderedDict, chave: tuple[str, int, str], desenhar: Callable[[], object]
) -> object:
    with _trava:
        if chave in cache:
            cache.move_to_end(chave)
            return cache[chave]
    # **O desenho roda fora da trava**: é a parte cara, e duas threads desenharem a mesma posição
    # uma vez a mais é melhor do que uma segurar a outra por dezenas de milissegundos.
    valor = desenhar()
    with _trava:
        cache[chave] = valor
        while len(cache) > _TETO_DO_CACHE:
            cache.popitem(last=False)
    return valor


def _pontos_em_pixel(pontos: float, *, dpi: int = DPI_DO_CARIMBO) -> int:
    return max(64, int(round((pontos / 72.0) * dpi)))


def _pdf_do_diagrama(placement: str, lado_px: int) -> bytes | None:
    chave = (placement, int(lado_px), desenho_de_diagrama.escopo_do_desenho())
    valor = _guardado(_cache_pdf, chave, lambda: desenho_de_diagrama.pdf_do_diagrama(placement, lado_px=lado_px))
    return valor if valor is None or isinstance(valor, bytes) else None


def _png_do_diagrama(placement: str, lado_px: int) -> bytes:
    chave = (placement, int(lado_px), desenho_de_diagrama.escopo_do_desenho())
    valor = _guardado(_cache_png, chave, lambda: desenho_de_diagrama.png_do_diagrama(placement, lado_px=lado_px))
    assert isinstance(valor, bytes)  # noqa: S101 - o desenho raster sempre responde
    return valor


# --------------------------------------------------------------------- apagar


def apagar_retangulos(pagina: fitz.Page, retangulos: Sequence[fitz.Rect]) -> None:
    """Apaga todas as áreas **de uma vez**, e a passada única é o item.

    Duas razões, e as duas foram medidas na origem: uma passada de `apply_redactions` evita
    reescrever o content stream da página N vezes -- custo que aparece na prévia ao vivo --, e
    garante que nenhum diagrama já desenhado seja apagado por uma redação posterior. Apagar
    depois de carimbar é o defeito clássico deste desenho, e ele some quando só existe uma passada.

    **A reserva pinta branco por cima.** A redação remove o conteúdo por baixo, que é melhor; num
    PDF exótico em que ela falha, um retângulo branco ainda resolve visualmente -- e o contrato
    aqui é o mesmo do resto do projeto: o caminho de degradação existe e é registrado.
    """
    alvos = [rect for rect in retangulos if not rect.is_empty]
    if not alvos:
        return
    try:
        for rect in alvos:
            pagina.add_redact_annot(rect, fill=(1, 1, 1))
        pagina.apply_redactions()
        return
    except Exception:  # noqa: BLE001 - ver o docstring: a reserva é visual e vale
        logger.warning(
            "apply_redactions falhou em %d área(s); usando retângulo branco", len(alvos), exc_info=True
        )
        for rect in alvos:
            pagina.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)


# --------------------------------------------------------------------- link de análise


def fen_completa(op: Substituicao) -> str:
    """A FEN inteira da operação: peças mais as etiquetas (lado a jogar, número do lance).

    Pública porque quem edita as etiquetas precisa **ver** o que elas produzem -- é a única saída
    delas no PDF, já que nenhuma muda um pixel do tabuleiro desenhado. Uma segunda cópia da regra
    no painel divergiria no dia em que o campo de roque deixasse de ser inferido.
    """
    import chess

    return compose_fen(
        op.placement, chess.WHITE if str(op.lado) != "b" else chess.BLACK, fullmove=int(op.lance)
    )


def url_de_analise(fen: str) -> str:
    """URL de análise do Lichess para uma FEN completa. **Ponto único.**

    A origem tinha duas implementações, com codificadores diferentes (`QUrl.toPercentEncoding` e
    este `quote`). As duas concordavam -- e concordar não era o ponto: o link que a interface
    mostra e o link que vai **para dentro do PDF** têm de ser o mesmo, e nada garantia isso além
    de terem sido escritas parecidas.
    """
    partes = " ".join(str(fen).split()).split(" ")
    if not partes or not partes[0]:
        return "https://lichess.org/analysis"
    placement = partes[0]
    if len(partes) == 1:
        return f"https://lichess.org/analysis/{placement}"
    cauda = " ".join(partes[1:])
    return f"https://lichess.org/analysis/{placement}{quote(' ' + cauda, safe='')}"


def url_da_operacao(op: Substituicao) -> str:
    return url_de_analise(fen_completa(op))


TEXTO_DO_LINK = "Lichess"
VAO_DO_LINK_PT = 2.0
COR_DO_LINK = (0.0, 0.2, 1.0)
"""O azul do rótulo, em RGB do PDF.

**Não é `ui/tokens.py`, e a ausência é decisão.** Os papéis de lá são medidos contra as
superfícies **desta janela**; este rótulo é tinta no arquivo de outra pessoa, lido em qualquer
leitor, e o que ele precisa ser é "azul de link" no vocabulário de quem lê PDF. Pôr um papel
aqui prometeria que trocar a pele do programa mudaria o livro exportado, o que não pode ser
verdade -- um PDF não tem tema."""


def _palavras(pagina: fitz.Page) -> list[tuple[fitz.Rect, str]]:
    """As palavras da página com a caixa de cada uma.

    `get_text(clip=...)` **não** serve para detectar sobreposição: ele devolve o texto *contido*
    no retângulo, então uma legenda larga passando por trás de um rótulo estreito não apareceria.
    Aqui as caixas vêm todas e quem decide a interseção é o chamador.
    """
    try:
        return [
            (fitz.Rect(palavra[0], palavra[1], palavra[2], palavra[3]), str(palavra[4]))
            for palavra in pagina.get_text("words")
        ]
    except Exception:  # noqa: BLE001 - página sem camada de texto legível não impede o carimbo
        logger.warning("Não foi possível ler as palavras da página", exc_info=True)
        return []


def _area_livre(pagina: fitz.Page, rect: fitz.Rect) -> bool:
    """Não há texto do livro nesta área?

    A checagem roda **depois** das redações, então o que o apagamento já cobriu não conta como
    ocupado -- e o rótulo de uma operação anterior na mesma página conta, o que impede dois links
    se sobreporem.
    """
    if rect.is_empty:
        return False
    return all(not texto.strip() or (caixa & rect).is_empty for caixa, texto in _palavras(pagina))


def _vagas_do_rotulo(pagina: fitz.Page, rect: fitz.Rect, corpo: float) -> list[float]:
    """Linhas de base candidatas, da preferida para a alternativa: abaixo do diagrama, e acima."""
    vagas = [rect.y1 + VAO_DO_LINK_PT + corpo, rect.y0 - VAO_DO_LINK_PT]
    # `rect` já é de escrita, então o limite da página também tem de ser.
    visivel = cropbox_de_escrita(pagina)
    return [base for base in vagas if base + 2.0 <= visivel.y1 and base - corpo >= visivel.y0]


def _inserir_link(pagina: fitz.Page, rect: fitz.Rect, op: Substituicao) -> None:
    """Rótulo `Lichess` clicável, **sem escrever por cima do livro**.

    A versão anterior da origem desenhava o rótulo logo abaixo do diagrama e pronto. Só que é
    justamente ali que o livro costuma pôr a legenda ("Diagrama 12", "as brancas jogam"): o texto
    azul saía sobreposto ao do autor e os dois ficavam ilegíveis -- num arquivo que a pessoa vai
    ler, não num rascunho.

    Agora ele procura espaço livre. Não havendo nenhum, o **diagrama inteiro** vira a área
    clicável, sem texto visível: o link continua existindo e nada do livro é estragado. Perde-se
    a descoberta visual, que é o preço certo a pagar -- a alternativa é vandalizar a página.
    """
    corpo = min(12.0, max(7.0, rect.height * 0.09))
    largura = fitz.get_text_length(TEXTO_DO_LINK, fontname="helv", fontsize=corpo)
    centro = (rect.x0 + rect.x1) / 2.0
    visivel = cropbox_de_escrita(pagina)
    x0 = max(visivel.x0 + 1.0, centro - (largura / 2.0) - 2.0)
    x1 = min(visivel.x1 - 1.0, centro + (largura / 2.0) + 2.0)
    uri = url_da_operacao(op)

    if x1 > x0:
        for base in _vagas_do_rotulo(pagina, rect, corpo):
            caixa = fitz.Rect(x0, base - corpo, x1, base + 2.0) & visivel
            if not _area_livre(pagina, caixa):
                continue
            pagina.insert_text(
                fitz.Point(x0 + 2.0, base),
                TEXTO_DO_LINK,
                fontsize=corpo,
                fontname="helv",
                color=COR_DO_LINK,
                overlay=True,
            )
            pagina.insert_link({"kind": fitz.LINK_URI, "from": caixa, "uri": uri})
            return

    reserva = fitz.Rect(rect) & visivel
    if reserva.is_empty:
        return
    logger.info(
        "Sem espaço livre para o rótulo na página %d; o diagrama inteiro virou o link",
        (pagina.number or 0) + 1,
    )
    pagina.insert_link({"kind": fitz.LINK_URI, "from": reserva, "uri": uri})


# --------------------------------------------------------------------- coordenadas residuais
#
# O diagrama do livro quase sempre traz as coordenadas impressas em volta do tabuleiro (a-h
# embaixo, 1-8 na lateral). O apagamento cobre o tabuleiro e uma folga pequena; as coordenadas
# ficam **fora** dele e sobrevivem à substituição, emoldurando o diagrama novo com as letrinhas
# do antigo.
#
# A detecção é deliberadamente conservadora -- apagar texto do livro por engano é muito pior que
# deixar uma letrinha:
#
#   1. só palavras de um caractere em `a-h` ou `1-8`, ou corridas contíguas dessas sequências;
#   2. só na faixa em volta do tabuleiro, e **fora** dele;
#   3. letras só acima/abaixo, dígitos só à esquerda/direita;
#   4. e -- a regra que de fato segura o resto -- só quando há uma **fileira** delas.
#
# A regra 4 não é excesso de zelo. Em português `a` e `e` são palavras inteiras, e uma legenda
# "Diagrama 12 - as brancas jogam **e** ganham" logo abaixo do diagrama cai direto nas regras 1
# a 3. Sozinho, esse `e` não forma fileira com ninguém; as oito coordenadas de verdade formam.
# Sem essa regra, o apagamento comia a legenda do autor -- foi o que o teste da origem mostrou.
#
# E as corridas existem porque, medido em livros reais, a fileira quase nunca sai como oito
# palavras de um caractere: o PDF a guarda num único text run, e a extração devolve `abcdefgh`
# inteiro -- ou `abcdef` + `gh`, quando o espaçamento quebra o run no meio. A primeira versão do
# detector da origem achava 10 diagramas em 147 pelo motivo mais bobo possível: exigia palavras
# de um caractere.

_LETRAS = frozenset("abcdefgh")
_NUMEROS = frozenset("12345678")
_SEQUENCIA_DE_LETRAS = "abcdefgh"
_SEQUENCIAS_DE_NUMEROS = ("12345678", "87654321")

COBERTURA_MINIMA_DA_CORRIDA = 0.45
"""Quanto a soma das corridas precisa cobrir do lado do tabuleiro para a fileira valer.

Uma corrida sozinha já é sinal forte -- ser um trecho contíguo de `abcdefgh` não acontece por
acaso --, mas exigir cobertura evita adotar um `gh` perdido longe do tabuleiro como se fosse a
fileira inteira. É o que separa `cdef` de `faced`: as duas só têm letras de `a`-`h`, e só a
primeira é um pedaço da sequência."""

FAIXA_DE_COORDENADA = 0.10
FAIXA_MINIMA_PT = 9.0
FAIXA_MAXIMA_PT = 30.0
"""A largura da faixa examinada em volta do tabuleiro, como fração do lado dele, com piso e teto."""

MINIMO_DE_COORDENADAS_EM_FILA = 4
"""Quantas alinhadas fazem uma fileira. Um diagrama traz 8; livro que imprime só as pontas traz 2,
e esse caso fica de fora **de propósito** -- o risco de falso positivo com 2 é alto demais."""

_TOLERANCIA_DE_ALINHAMENTO_PT = 3.0
_FOLGA_DA_COORDENADA_PT = 0.6
"""Folga ao apagar, para não deixar meio pixel do glifo."""


def _tipo_de_corrida(token: str) -> str | None:
    if len(token) < 2:
        return None
    if token.lower() in _SEQUENCIA_DE_LETRAS:
        return "letra"
    if any(token in sequencia for sequencia in _SEQUENCIAS_DE_NUMEROS):
        return "numero"
    return None


def _faixa_pt(rect: fitz.Rect) -> float:
    lado = max(rect.width, rect.height)
    return min(FAIXA_MAXIMA_PT, max(FAIXA_MINIMA_PT, lado * FAIXA_DE_COORDENADA))


def _fileira_alinhada(entradas: list[tuple[fitz.Rect, float]]) -> list[fitz.Rect]:
    """Da lista de um lado, as que formam fileira; vazio se não formarem.

    A referência é a **mediana** e não a média: uma legenda solta longe do tabuleiro puxaria a
    média para fora e levaria a fileira inteira junto, que é o falso positivo que se quer evitar.
    """
    if len(entradas) < MINIMO_DE_COORDENADAS_EM_FILA:
        return []
    posicoes = sorted(posicao for _caixa, posicao in entradas)
    mediana = posicoes[len(posicoes) // 2]
    fileira = [
        caixa for caixa, posicao in entradas if abs(posicao - mediana) <= _TOLERANCIA_DE_ALINHAMENTO_PT
    ]
    return fileira if len(fileira) >= MINIMO_DE_COORDENADAS_EM_FILA else []


def _corridas_que_cobrem(
    entradas: list[fitz.Rect], inicio: float, fim: float, horizontal: bool
) -> list[fitz.Rect]:
    if not entradas:
        return []
    lado = abs(fim - inicio)
    if lado <= 0:
        return []
    coberto = sum((c.x1 - c.x0) if horizontal else (c.y1 - c.y0) for c in entradas)
    return entradas if coberto >= lado * COBERTURA_MINIMA_DA_CORRIDA else []


def achar_coordenadas(pagina: fitz.Page, retangulo: Retangulo) -> list[fitz.Rect]:
    """As caixas das coordenadas do diagrama original em volta de `retangulo`, em espaço de escrita.

    `retangulo` já vem convertido: as caixas do `get_text` são de escrita, e comparar espaços
    diferentes devolveria a fileira errada -- ou nenhuma -- em toda página girada.
    """
    tabuleiro = _retangulo(retangulo)
    if tabuleiro.is_empty:
        return []
    faixa = _faixa_pt(tabuleiro)
    fora = fitz.Rect(
        tabuleiro.x0 - faixa, tabuleiro.y0 - faixa, tabuleiro.x1 + faixa, tabuleiro.y1 + faixa
    )

    # Cada lado é avaliado separadamente: uma fileira de letras embaixo não legitima um dígito
    # solto na lateral.
    sozinhas: dict[str, list[tuple[fitz.Rect, float]]] = {"acima": [], "abaixo": [], "esq": [], "dir": []}
    corridas: dict[str, list[fitz.Rect]] = {"acima": [], "abaixo": [], "esq": [], "dir": []}

    for caixa, texto in _palavras(pagina):
        token = texto.strip()
        if not token or (caixa & fora).is_empty:
            continue
        tipo = _tipo_de_corrida(token)
        e_letra = tipo == "letra" or (len(token) == 1 and token.lower() in _LETRAS)
        e_numero = tipo == "numero" or (len(token) == 1 and token in _NUMEROS)
        if not (e_letra or e_numero):
            continue

        cx = (caixa.x0 + caixa.x1) / 2.0
        cy = (caixa.y0 + caixa.y1) / 2.0
        # "Fora do tabuleiro" é medido pelo **centro**, e não por interseção zero: a fileira
        # encosta na borda, e a caixa da palavra invade o retângulo detectado por 1 ou 2 pt.
        # Exigir interseção vazia descartava justamente as fileiras coladas -- o caso comum.
        if tabuleiro.x0 < cx < tabuleiro.x1 and tabuleiro.y0 < cy < tabuleiro.y1:
            continue
        lado: str | None = None
        if e_letra and tabuleiro.x0 - faixa <= cx <= tabuleiro.x1 + faixa:
            lado = "abaixo" if cy > tabuleiro.y1 else ("acima" if cy < tabuleiro.y0 else None)
        elif e_numero and tabuleiro.y0 - faixa <= cy <= tabuleiro.y1 + faixa:
            lado = "dir" if cx > tabuleiro.x1 else ("esq" if cx < tabuleiro.x0 else None)
        if lado is None:
            continue

        if tipo is not None:
            corridas[lado].append(caixa)
        else:
            sozinhas[lado].append((caixa, cy if lado in ("acima", "abaixo") else cx))

    achadas: list[fitz.Rect] = []
    for entradas in sozinhas.values():
        achadas.extend(_fileira_alinhada(entradas))
    for lado, entradas in corridas.items():
        horizontal = lado in ("acima", "abaixo")
        achadas.extend(
            _corridas_que_cobrem(
                entradas,
                tabuleiro.x0 if horizontal else tabuleiro.y0,
                tabuleiro.x1 if horizontal else tabuleiro.y1,
                horizontal,
            )
        )

    visivel = cropbox_de_escrita(pagina)
    return [
        fitz.Rect(
            caixa.x0 - _FOLGA_DA_COORDENADA_PT,
            caixa.y0 - _FOLGA_DA_COORDENADA_PT,
            caixa.x1 + _FOLGA_DA_COORDENADA_PT,
            caixa.y1 + _FOLGA_DA_COORDENADA_PT,
        )
        & visivel
        for caixa in achadas
    ]


def texto_no_retangulo(pagina: fitz.Page, retangulo: Retangulo) -> str:
    """O texto do livro dentro daquele retângulo da vista.

    O `clip=` do `get_text` é em espaço de escrita, não no de `page.rect`. Passar a seleção crua
    devolvia string vazia em **toda** página girada.
    """
    rect = _retangulo(espaco_de_escrita(pagina).para_escrita(retangulo)) & cropbox_de_escrita(pagina)
    if rect.is_empty:
        return ""
    return str(pagina.get_text("text", clip=rect)).strip()


# --------------------------------------------------------------------- a substituição


def aplicar_na_pagina(
    pagina: fitz.Page,
    substituicoes: Iterable[Substituicao],
    apagamentos: Iterable[Apagamento] = (),
    *,
    apagar_fundo: bool = True,
    link_lichess: bool = True,
    apagar_coordenadas: bool = False,
    pasta_do_usuario: str = "",
) -> None:
    """Aplica apagamentos e substituições numa página **já aberta**. Ponto único de verdade.

    Compartilhado pela prévia e pela exportação: o que a comparação mostra é exatamente o que o
    PDF vai conter, porque é a mesma função sobre a mesma página.

    **Daqui para baixo todo retângulo está em espaço de escrita**, e quem limita é a CropBox
    convertida -- não `page.rect`, que numa página girada tem largura e altura trocadas.
    """
    espaco = espaco_de_escrita(pagina)
    visivel = cropbox_de_escrita(pagina)

    ops = [
        op.com_retangulo(espaco.para_escrita(op.retangulo))
        for op in substituicoes
        if not vazio(op.retangulo)
    ]
    borrachas = [op.com_retangulo(espaco.para_escrita(op.retangulo)) for op in apagamentos]

    a_apagar: list[fitz.Rect] = [_retangulo(op.retangulo) & visivel for op in borrachas]
    if apagar_fundo:
        a_apagar.extend(_retangulo(folga_aplicada(op)) & visivel for op in ops)
    if apagar_coordenadas:
        # Detectado **antes** da redação: depois dela o texto não existe mais para ser encontrado.
        for op in ops:
            a_apagar.extend(achar_coordenadas(pagina, op.retangulo))
    apagar_retangulos(pagina, a_apagar)

    for op in ops:
        rect = _retangulo(op.retangulo)
        lado_px = max(
            _pontos_em_pixel(rect.width),
            _pontos_em_pixel(rect.height),
        )
        # Numa página girada o conteúdo inserido tem de girar junto, senão o tabuleiro sai
        # deitado para quem lê o PDF. Medido na origem: `rotate = page.rotation` devolve um
        # recorte idêntico ao da mesma posição numa página sem rotação.
        giro = int(pagina.rotation) % 360
        vetorial = _pdf_do_diagrama(op.placement, lado_px)
        if vetorial:
            fonte = fitz.open("pdf", vetorial)
            try:
                pagina.show_pdf_page(rect, fonte, 0, overlay=True, keep_proportion=False, rotate=giro)
            finally:
                fonte.close()
        else:
            pagina.insert_image(
                rect,
                stream=_png_do_diagrama(op.placement, lado_px),
                overlay=True,
                keep_proportion=False,
                rotate=giro,
            )

        if op.borda_pt > 0:
            pagina.draw_rect(rect, color=(0, 0, 0), width=float(op.borda_pt), overlay=True)
        if quer_link_lichess(op, link_lichess):
            _inserir_link(pagina, rect, op)

    if pasta_do_usuario:
        # O conjunto de peças da pessoa é escolha da janela, e chega até aqui só para o desenho.
        # Ele não muda nada da geometria acima -- ver `desenho_de_diagrama.png_do_diagrama`.
        logger.debug("Conjunto de peças do usuário em %s", pasta_do_usuario)


class ServicoDeSubstituicao:
    """Um livro aberto, com prévia em cache. É o que a janela segura enquanto a aba está viva.

    **A prévia é um documento de uma página só**, copiado do original e alterado. Não é uma
    segunda implementação do que a exportação faz: é `aplicar_na_pagina` sobre uma cópia, o que
    torna impossível a prévia e o arquivo divergirem.
    """

    def __init__(self, caminho: str | Path) -> None:
        self.caminho = str(caminho)
        self.doc = fitz.open(self.caminho)
        self._previa: fitz.Document | None = None
        self._assinatura: tuple[object, ...] | None = None

    def __enter__(self) -> ServicoDeSubstituicao:
        return self

    def __exit__(self, *_excecao: object) -> None:
        self.fechar()

    def fechar(self) -> None:
        """Fecha o documento. **Chamar duas vezes é inofensivo**, e não é zelo.

        Fechar de novo é condição normal num caminho de erro: a janela fecha o serviço ao trocar
        de livro e o fechamento da aba fecha ao sair, e entre os dois cabe uma abertura que
        falhou. Sem esta guarda o PyMuPDF levanta `document closed` de dentro do fechamento -- ou
        seja, o programa não sairia nem fechando.
        """
        self._descartar_previa()
        if not getattr(self.doc, "is_closed", False):
            self.doc.close()

    @property
    def paginas(self) -> int:
        return len(self.doc)

    def renderizar(self, pagina: int, zoom: float = 2.0) -> PaginaRenderizada:
        return _renderizar(self.doc[pagina], pagina, zoom)

    def renderizar_regiao(self, pagina: int, zoom: float, retangulo: Retangulo) -> bytes:
        """PNG da região na página **original** -- o lado "antes" da comparação."""
        return _renderizar_regiao(self.doc[pagina], zoom, retangulo)

    def _descartar_previa(self) -> None:
        if self._previa is not None:
            try:
                self._previa.close()
            except Exception:  # noqa: BLE001 - já fechado é estado aceitável
                logger.debug("Documento de prévia já estava fechado", exc_info=True)
        self._previa = None
        self._assinatura = None

    def _pagina_de_previa(
        self,
        pagina: int,
        substituicoes: Sequence[Substituicao],
        apagamentos: Sequence[Apagamento] = (),
        *,
        apagar_fundo: bool = True,
        link_lichess: bool = True,
        apagar_coordenadas: bool = False,
    ) -> fitz.Page:
        assinatura = assinatura_da_pagina(
            documento=self.caminho,
            pagina=pagina,
            substituicoes=substituicoes,
            apagamentos=apagamentos,
            apagar_fundo=apagar_fundo,
            link_lichess=link_lichess,
            apagar_coordenadas=apagar_coordenadas,
            escopo_do_desenho=desenho_de_diagrama.escopo_do_desenho(),
        )
        if self._previa is not None and self._assinatura == assinatura:
            return self._previa[0]

        self._descartar_previa()
        previa = fitz.open()
        try:
            previa.insert_pdf(self.doc, from_page=pagina, to_page=pagina, links=False, annots=False)
            aplicar_na_pagina(
                previa[0],
                [op.com_retangulo(op.retangulo) for op in substituicoes if op.pagina == pagina],
                [op.com_retangulo(op.retangulo) for op in apagamentos if op.pagina == pagina],
                apagar_fundo=apagar_fundo,
                link_lichess=link_lichess,
                apagar_coordenadas=apagar_coordenadas,
            )
        except Exception:
            previa.close()
            raise
        self._previa = previa
        self._assinatura = assinatura
        return previa[0]

    def renderizar_com_operacoes(
        self,
        pagina: int,
        zoom: float,
        substituicoes: Sequence[Substituicao],
        apagamentos: Sequence[Apagamento] = (),
        *,
        apagar_fundo: bool = True,
        link_lichess: bool = True,
        apagar_coordenadas: bool = False,
    ) -> PaginaRenderizada:
        """A página **já alterada**, como bitmap. É a cortina do lado "depois"."""
        alvo = self._pagina_de_previa(
            pagina,
            substituicoes,
            apagamentos,
            apagar_fundo=apagar_fundo,
            link_lichess=link_lichess,
            apagar_coordenadas=apagar_coordenadas,
        )
        return _renderizar(alvo, pagina, zoom)

    def renderizar_regiao_com_operacoes(
        self,
        pagina: int,
        zoom: float,
        retangulo: Retangulo,
        substituicoes: Sequence[Substituicao],
        apagamentos: Sequence[Apagamento] = (),
        *,
        apagar_fundo: bool = True,
        link_lichess: bool = True,
        apagar_coordenadas: bool = False,
    ) -> bytes:
        """PNG de um recorte da página já alterada -- a miniatura "depois"."""
        alvo = self._pagina_de_previa(
            pagina,
            substituicoes,
            apagamentos,
            apagar_fundo=apagar_fundo,
            link_lichess=link_lichess,
            apagar_coordenadas=apagar_coordenadas,
        )
        return _renderizar_regiao(alvo, zoom, retangulo)

    def retangulo_de_imagem_para_pdf(
        self, pagina: int, retangulo: Retangulo, matriz: tuple[float, float, float, float, float, float]
    ) -> Retangulo:
        """Da seleção em pixel da imagem para pontos do PDF, cortada pela página."""
        inversa = fitz.Matrix(*matriz)
        inversa.invert()
        x0, y0, x1, y1 = retangulo
        rect = fitz.Rect(fitz.Point(x0, y0) * inversa, fitz.Point(x1, y1) * inversa) & self.doc[pagina].rect
        return (rect.x0, rect.y0, rect.x1, rect.y1)

    def retangulo_de_pdf_para_imagem(
        self, pagina: int, retangulo: Retangulo, matriz: tuple[float, float, float, float, float, float]
    ) -> Retangulo:
        """O caminho de volta. A ida-e-volta é afirmada por teste (ASSETS §2.12)."""
        rect = _retangulo(retangulo) & self.doc[pagina].rect
        m = fitz.Matrix(*matriz)
        saida = fitz.Rect(fitz.Point(rect.x0, rect.y0) * m, fitz.Point(rect.x1, rect.y1) * m)
        return (saida.x0, saida.y0, saida.x1, saida.y1)

    def texto_em(self, pagina: int, retangulo: Retangulo) -> str:
        return texto_no_retangulo(self.doc[pagina], retangulo)


# --------------------------------------------------------------------- gravação


def gravar_pdf(doc: fitz.Document, saida: str | Path) -> None:
    """Grava sem nunca deixar um PDF pela metade no destino.

    `doc.save(destino)` escreve **direto no arquivo da pessoa**: qualquer morte no meio -- queda
    de energia, gerenciador de tarefas -- deixa um PDF truncado ali, e se a exportação era por
    cima de uma anterior, o arquivo bom vai junto. A origem mediu uma gravação abortada na
    terceira chamada a `write` deixando **2 bytes** no destino.

    A gravação atômica aqui é a do tronco (`atomic_io`, S-25/S-373) e não uma segunda: ela já
    escreve num vizinho, dá `fsync` e troca com `os.replace` -- e ainda traz a segunda chance do
    Windows, que é o que salva o caso do arquivo aberto noutro programa. O documento vai para a
    memória antes (`tobytes`), e o custo disso é conhecido: o livro de 900 páginas da medição da
    origem tem 17,8 MB.

    **O `_CancelableWriter` da origem (ASSETS §2.9) não veio, e é escolha registrada.** Ele
    transforma o `save` num bloco abandonável -- medido: 121.495 chamadas de `write`, a primeira
    aos 57% do tempo. O que ele protege é a espera de uma exportação para pasta de rede; o que ele
    custa é um objeto de arquivo próprio, com a armadilha do atributo `name`, e um caminho de
    gravação **diferente** do que os outros três arquivos do projeto usam. Enquanto a exportação
    daqui não roda em thread com botão de parar, ter dois gravadores atômicos seria a duplicação
    que a `ASSETS §6` proíbe. Quando ela rodar, o lugar de ressuscitá-lo é aqui.
    """
    atomic_write_bytes(Path(saida), bytes(doc.tobytes(deflate=True, garbage=3)))


def substituir_no_pdf(
    entrada: str | Path,
    saida: str | Path,
    substituicoes: Iterable[Substituicao],
    apagamentos: Iterable[Apagamento] = (),
    *,
    apagar_fundo: bool = True,
    link_lichess: bool = True,
    apagar_coordenadas: bool = False,
    ao_avancar: Callable[[int, int], None] | None = None,
) -> None:
    """Grava o PDF de saída com todas as alterações aplicadas.

    `ao_avancar(feitas, total)` conta **páginas alteradas**, e não páginas do livro: num livro de
    898 páginas com 60 diagramas o total é 60, e é isso que faz a barra andar de forma honesta.
    """
    origem = Path(entrada)
    if not origem.exists():
        raise FileNotFoundError(f"PDF de entrada não encontrado: {origem}")

    doc = fitz.open(str(origem))
    try:
        por_pagina: dict[int, list[Substituicao]] = {}
        borrachas: dict[int, list[Apagamento]] = {}
        for op in substituicoes:
            if 0 <= op.pagina < len(doc):
                por_pagina.setdefault(op.pagina, []).append(op)
        for op in apagamentos:
            if 0 <= op.pagina < len(doc):
                borrachas.setdefault(op.pagina, []).append(op)

        paginas = sorted(set(por_pagina) | set(borrachas))
        total = len(paginas)
        for feitas, numero in enumerate(paginas, start=1):
            aplicar_na_pagina(
                doc[numero],
                por_pagina.get(numero, []),
                borrachas.get(numero, []),
                apagar_fundo=apagar_fundo,
                link_lichess=link_lichess,
                apagar_coordenadas=apagar_coordenadas,
            )
            if ao_avancar is not None:
                ao_avancar(feitas, total)
        gravar_pdf(doc, saida)
    finally:
        doc.close()
