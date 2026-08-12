"""Candidatos a diagrama a partir das imagens embutidas da página (S-12).

O PDF que traz o diagrama como imagem já carrega o bounding box exato dele. Procurar
contorno nesse caso é reconstruir informação que estava disponível -- e o contorno erra:
medido, a página 40 do `1937 Kemeri.pdf` rende um "tabuleiro" que decodifica para
`8/8/8/8/8/8/8/8` com confiança 0,891.

Duas armadilhas que a medição mostrou e que este módulo tem de tratar:

1. **O scan de fundo.** No Kemeri, cada página tem também uma imagem de 1633×2468 cobrindo
   tudo. Sem filtro de cobertura, ela entra como "diagrama gigante".
2. **A moldura e a legenda.** No Aagaard a imagem embutida às vezes é 620×704 em vez de
   616×616: inclui a legenda embaixo. Recortar pelo bbox cru desloca a grade 8×8 e a leitura
   sai com `TOO_MANY_KINGS`. É o que `trim_to_grid` resolve.

**E quando ela não resolve** -- a segunda medição, 2026-08-09. `trim_to_grid` procura as 7
linhas internas da grade no perfil de gradiente, e num diagrama de casa **hachurada** essas
linhas não existem: a fronteira entre casa clara e casa escura é uma mudança de textura, não
um traço. No `Karpov 1`, 14 de 173 diagramas chegavam ao classificador com o rodapé de
avaliação (`△`, `+−`) colado embaixo, a grade deslocada, e **8 entregavam posição errada** --
um deles com confiança 0,9385, acima do gate de exportação. `trim_to_frame` é a segunda
tentativa, com um sinal que não depende de haver grade desenhada.

**Três guardas deviam ter pego isso, e as três calaram** -- vale registrar quais, porque o
padrão se repete:

| guarda | por que calou |
|---|---|
| `trim_to_grid` | procura grade onde não há grade desenhada (a hachura não faz linha) |
| `refine_candidate_with_contour` | achou um quad **pior**, e a S-38a corretamente o descartou -- restando o recorte cru |
| `board_texture_score` | 0,3607 no recorte errado contra 0,3897 no certo: **0,03**, quase cego ao alinhamento da grade, que é o que decide a leitura |

O sinal que separava os 14 com precisão perfeita era gratuito e não estava sendo olhado:
**os 159 recortes corretos são exatamente quadrados e os 14 defeituosos não são.**
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import cv2
import fitz
import numpy as np

logger = logging.getLogger(__name__)

CandidateSource = Literal["embedded", "contour"]

MIN_EMBEDDED_SIDE = 120
"""Lado mínimo em pixels nativos. Abaixo disso é ícone, logotipo ou peça solta."""

MAX_PAGE_COVERAGE = 0.70
"""Acima desta fração da área da página, a imagem é o scan de fundo e não um diagrama."""

ASPECT_TOLERANCE = 0.20
"""Quanto o aspecto pode fugir de 1,0. Cobre a imagem que inclui legenda (620×704 = 1,14)."""


@dataclass(frozen=True, eq=False)
class DiagramCandidate:
    """Um recorte candidato a diagrama, com a proveniência preservada.

    `bbox_pdf` fica em coordenadas do PDF (pontos, origem no topo-esquerda da página) e não
    em pixels: é o que permite associar o texto vizinho por proximidade geométrica na Fase 3
    (S-16) sem depender do DPI com que a página foi renderizada.
    """

    board_rgb: np.ndarray
    bbox_pdf: tuple[float, float, float, float]
    source: CandidateSource
    detector_score: float
    """Confiança do detector nesta caixa, em 0..1. Não é confiança de leitura."""

    native_size: tuple[int, int]
    """(largura, altura) em pixels nativos da fonte, antes de qualquer redimensionamento."""

    trimmed: bool = False
    """`trim_to_grid` encontrou a grade e recortou moldura/legenda."""

    @property
    def area_pdf(self) -> float:
        x0, y0, x1, y1 = self.bbox_pdf
        return abs((x1 - x0) * (y1 - y0))


def _gradient_profiles(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Atividade de borda por coluna e por linha.

    As linhas da grade de um tabuleiro são as bordas longas e retas da imagem, então somar o
    gradiente ao longo de cada eixo faz elas aparecerem como picos.
    """
    gradient_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    gradient_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    return gradient_x.mean(axis=0), gradient_y.mean(axis=1)


def _line_positions(profile: np.ndarray, relative_threshold: float = 0.25) -> list[int]:
    """Posições das linhas de grade: um índice por pico, não um por pixel aceso.

    Cada linha do tabuleiro acende 2 ou 3 colunas vizinhas no gradiente; agrupá-las é o que
    permite medir o passo da grade em seguida.
    """
    if profile.size == 0:
        return []

    peak = float(profile.max())
    if peak <= 1e-6:
        return []

    active = np.flatnonzero(profile >= peak * relative_threshold)
    if active.size == 0:
        return []

    lines: list[int] = []
    group_start = int(active[0])
    previous = group_start
    for index in active[1:]:
        index = int(index)
        if index - previous > 2:
            lines.append((group_start + previous) // 2)
            group_start = index
        previous = index
    lines.append((group_start + previous) // 2)
    return lines


def _board_span(profile: np.ndarray, limit: int) -> tuple[int, int] | None:
    """Início e fim do tabuleiro ao longo de um eixo, em pixels.

    Não basta tomar do primeiro ao último pixel com gradiente. Num diagrama **sem moldura** o
    gradiente existe só nas 7 linhas internas -- a borda externa não contrasta com nada -- e
    esse intervalo cobre 6 células, não 8. Foi o que fez a primeira versão recortar 242 px de
    um tabuleiro de 320 e depois não reconhecer a própria grade.

    A saída é medir o **passo** entre linhas e estender para fora até fechar 8 células. Com
    moldura, as linhas externas aparecem e não há o que estender: a mesma conta cobre os dois
    casos.
    """
    lines = _line_positions(profile)
    if len(lines) < 4:
        return None

    diffs = np.diff(np.array(lines, dtype=np.float64))
    diffs = diffs[diffs > 1.0]
    if diffs.size == 0:
        return None

    step = float(np.median(diffs))
    if step < 4.0:
        return None

    first, last = float(lines[0]), float(lines[-1])
    cells_between = int(round((last - first) / step))
    missing = 8 - cells_between
    if missing < 0:
        return None

    before = missing // 2 + missing % 2
    start = int(round(first - before * step))
    end = int(round(start + 8 * step))
    return max(0, start), min(limit, end)


def _grid_periodicity(profile: np.ndarray, start: int, end: int) -> float:
    """Fração das 7 linhas internas da grade que aparecem no trecho `start:end`, em 0..1.

    Conta linhas encontradas em vez de comparar médias contra percentis. A primeira versão
    fazia isso -- `(média dos picos - p55) / (p92 - p55)` -- e reprovava tabuleiro nítido: num
    diagrama limpo de 320 px só 7 colunas têm gradiente, então o p92 ainda cai na linha de
    base, o denominador zera e a nota dá 0. Contagem não tem esse problema, e diz uma coisa
    interpretável: "achei 6 das 7 linhas".

    Só as 7 internas: as duas externas coincidem com a borda do recorte e aceitá-las inflaria
    a nota de qualquer imagem com moldura.
    """
    span = end - start
    if span < 32:
        return 0.0

    segment = profile[start:end]
    baseline = float(np.median(segment))
    top = float(segment.max())
    if top - baseline <= 1e-6:
        return 0.0

    threshold = baseline + 0.30 * (top - baseline)
    cell = span / 8.0
    window = max(1, int(cell * 0.18))

    found = 0
    for step in range(1, 8):
        center = int(start + cell * step)
        low = max(start, center - window)
        high = min(end, center + window + 1)
        if high > low and float(profile[low:high].max()) >= threshold:
            found += 1
    return found / 7.0


def trim_to_grid(image_rgb: np.ndarray, *, min_periodicity: float = 0.70) -> tuple[np.ndarray, bool]:
    """Recorta a imagem na borda do tabuleiro, tirando moldura e legenda.

    Devolve `(imagem, confiou)`. Quando `confiou` é `False` a imagem volta **inalterada**:
    um recorte errado é pior que nenhum recorte, porque desloca a grade 8×8 e estraga as 64
    casas de uma vez. Quem chama decide se ainda quer tentar ler.

    Existe por uma medição: no `AAGAARD - Practical Chess Defence.pdf` a imagem embutida às
    vezes é 620×704 -- inclui a legenda embaixo do diagrama -- e ler o bbox cru produzia
    posição com reis demais.
    """
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError(f"Esperada imagem RGB (H, W, 3), recebida {image_rgb.shape}.")

    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    profile_x, profile_y = _gradient_profiles(gray)

    span_x = _board_span(profile_x, gray.shape[1])
    span_y = _board_span(profile_y, gray.shape[0])
    if span_x is None or span_y is None:
        return image_rgb, False

    left, right = span_x
    top, bottom = span_y
    if right - left < 32 or bottom - top < 32:
        return image_rgb, False

    # O tabuleiro é quadrado: forçar o lado menor centrado no vão ativo corrige o caso em que
    # a legenda estica o eixo vertical.
    side = min(right - left, bottom - top)
    center_x = (left + right) // 2
    center_y = (top + bottom) // 2
    x0 = max(0, min(center_x - side // 2, gray.shape[1] - side))
    y0 = max(0, min(center_y - side // 2, gray.shape[0] - side))

    periodicity = min(
        _grid_periodicity(profile_x, x0, x0 + side),
        _grid_periodicity(profile_y, y0, y0 + side),
    )
    if periodicity < min_periodicity:
        logger.debug("trim_to_grid nao confiou no recorte: periodicidade %.3f", periodicity)
        return image_rgb, False

    return image_rgb[y0 : y0 + side, x0 : x0 + side].copy(), True


FRAME_DARK_LEVEL = 128
"""Abaixo disto o pixel conta como traço de moldura. Diagrama de livro é preto no branco."""

FRAME_MIN_FILL = 0.80
"""Fração da linha/coluna que precisa ser escura para ela ser moldura, e não peça.

Uma fila cheia de peças pretas não passa de ~0,45; a linha da moldura passa de 0,95. O vale
entre os dois é largo, e é por isso que este número não precisa ser calibrado por livro.
"""

FRAME_MIN_COVERAGE = 0.55
"""A moldura tem de conter a maior parte da imagem, senão não é moldura de tabuleiro."""

FRAME_ASPECT_TOLERANCE = 0.10
"""O que sobra dentro da moldura tem de ser quase quadrado -- o tabuleiro é."""

FRAME_INSET = 3
"""Pixels descartados para dentro: o traço da moldura não é casa, e ele encosta na fila 8."""


def trim_to_frame(
    image_rgb: np.ndarray,
    *,
    dark_level: int = FRAME_DARK_LEVEL,
    min_fill: float = FRAME_MIN_FILL,
    min_coverage: float = FRAME_MIN_COVERAGE,
    aspect_tolerance: float = FRAME_ASPECT_TOLERANCE,
    inset: int = FRAME_INSET,
) -> tuple[np.ndarray, bool]:
    """Recorta pela **moldura impressa** do diagrama. Segunda tentativa, quando a grade cala.

    Devolve `(imagem, confiou)`, com o mesmo contrato de `trim_to_grid`: sem confiança, a
    imagem volta inalterada.

    **Por que um segundo aparo, e não um limiar mais frouxo no primeiro.** `trim_to_grid`
    procura as 7 linhas internas da grade no perfil de gradiente. Num diagrama de casa
    **hachurada** essas linhas não existem: a fronteira entre casa clara e casa escura é uma
    mudança de textura, não um traço. Medido nos dois diagramas defeituosos da página 80 do
    `Karpov 1`, o passo mediano entre picos de gradiente sai 9 px e 32 px onde a casa tem 82 e
    88 -- o que `_line_positions` acha é a moldura e as bordas das peças, nunca a grade. Com
    isso `_board_span` calcula 73 e 19 células entre o primeiro e o último pico, desiste, e
    `trim_to_grid` devolve a imagem crua. **Não é um limiar apertado demais; é o sinal errado
    para esta imagem**, e afrouxar o limiar não muda nada porque a função nem chega lá.

    A moldura é um sinal independente e presente exatamente nesses livros: uma linha reta
    escura que atravessa a imagem inteira. Procurá-la é contar pixels escuros por linha e por
    coluna, e uma fila cheia de peças pretas não chega perto de 80%.

    **O que isso corrigia, medido.** No `Karpov 1`, páginas 70-99, 173 diagramas: 14 chegavam
    ao classificador como recorte cru, porque a imagem embutida do PDF inclui a faixa de
    avaliação (`△`, `+−`) abaixo do tabuleiro. Oito ranques divididos sobre tabuleiro **mais
    rodapé** deslocam a grade, e o erro acumula para baixo -- na última fila ele passa de uma
    casa inteira. Oito dos 14 entregavam **posição errada**, e um deles com confiança 0,9385,
    acima do gate de exportação da S-15: ia para o PGN principal como se estivesse certo.

    | | antes | depois |
    |---|---|---|
    | confiança mínima média dos 14 | 0,7551 | **1,0000** |
    | abaixo do gate 0,80 | 8 | **0** |
    | posições erradas | 8 | **0** |

    As três guardas que deveriam ter pego isso e não pegaram estão no docstring do módulo.
    """
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError(f"Esperada imagem RGB (H, W, 3), recebida {image_rgb.shape}.")

    height, width = image_rgb.shape[:2]
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    dark = gray < dark_level

    rows = np.flatnonzero(dark.mean(axis=1) >= min_fill)
    cols = np.flatnonzero(dark.mean(axis=0) >= min_fill)
    if rows.size < 2 or cols.size < 2:
        return image_rgb, False

    top, bottom = int(rows[0]), int(rows[-1]) + 1
    left, right = int(cols[0]), int(cols[-1]) + 1

    # Uma moldura que cobre quase nada da imagem é outra coisa: régua, tarja, sublinhado.
    if (bottom - top) < height * min_coverage or (right - left) < width * min_coverage:
        return image_rgb, False

    inner = image_rgb[top + inset : bottom - inset, left + inset : right - inset]
    inner_h, inner_w = inner.shape[:2]
    if inner_h < 32 or inner_w < 32:
        return image_rgb, False

    aspect = inner_w / inner_h
    if abs(aspect - 1.0) > aspect_tolerance:
        logger.debug("trim_to_frame recusou: proporcao %.3f dentro da moldura", aspect)
        return image_rgb, False

    if (bottom - top) == height and (right - left) == width:
        # A "moldura" é a borda da própria imagem: não há nada a aparar, e dizer que aparou
        # inflaria o `detector_score` de um recorte que ninguém conferiu.
        return image_rgb, False

    logger.info(
        "Aparado pela moldura: %dx%d -> %dx%d. A grade tinha calado (casa hachurada não "
        "produz linha de grade).",
        width,
        height,
        inner_w,
        inner_h,
    )
    return inner.copy(), True


def _pixels_for_bbox(page: fitz.Page, bbox: fitz.Rect, native_side: int) -> np.ndarray | None:
    """Renderiza só a região do diagrama, com DPI escolhido para não perder resolução.

    Renderizar a página inteira a 220 DPI dá ~430 px por diagrama no Kemeri, quando a imagem
    embutida tem 590 px nativos. Aqui o DPI sai do próprio tamanho nativo, então o que chega
    ao classificador é a resolução que o PDF tem para oferecer -- e nada além dela, porque
    ampliar não cria detalhe.
    """
    width_pt = abs(bbox.width)
    if width_pt <= 0 or native_side <= 0:
        return None

    dpi = int(np.clip(72.0 * native_side / width_pt, 72, 600))
    try:
        pix = page.get_pixmap(clip=bbox, dpi=dpi, alpha=False)
    except Exception as exc:  # página com recurso quebrado não deve derrubar a varredura
        logger.warning("Falha ao renderizar recorte %s: %s", tuple(bbox), exc)
        return None

    if pix.width < 16 or pix.height < 16:
        return None

    buffer = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return buffer[:, :, :3].copy() if pix.n == 4 else buffer.copy()


def candidates_from_embedded_images(
    page: fitz.Page,
    *,
    min_side: int = MIN_EMBEDDED_SIDE,
    aspect_tolerance: float = ASPECT_TOLERANCE,
    max_page_coverage: float = MAX_PAGE_COVERAGE,
    trim: bool = True,
) -> list[DiagramCandidate]:
    """Diagramas da página segundo as imagens que o PDF embute.

    Devolve lista vazia quando a página não tem imagem que sirva -- o que é o caso da maioria
    do acervo (12 dos 27 PDFs são scan de página inteira, 2 são vetoriais). Quem chama tem de
    tratar isso como caminho normal, não como erro.
    """
    page_area = abs(page.rect.width * page.rect.height)
    candidates: list[DiagramCandidate] = []

    try:
        infos = page.get_image_info()
    except Exception as exc:
        logger.warning("get_image_info falhou na pagina %s: %s", page.number, exc)
        return []

    for info in infos:
        native_width = int(info.get("width", 0))
        native_height = int(info.get("height", 0))
        if min(native_width, native_height) < min_side:
            continue

        aspect = native_width / native_height if native_height else 0.0
        if not (1.0 - aspect_tolerance) <= aspect <= (1.0 + aspect_tolerance):
            continue

        bbox = fitz.Rect(info["bbox"])
        if bbox.is_empty or bbox.is_infinite:
            continue

        # O scan de fundo do Kemeri (1633x2468 cobrindo a pagina) cai aqui.
        if page_area > 0 and abs(bbox.get_area()) > page_area * max_page_coverage:
            continue

        image = _pixels_for_bbox(page, bbox, native_side=max(native_width, native_height))
        if image is None:
            continue

        trimmed = False
        if trim:
            image, trimmed = trim_to_grid(image)
            if not trimmed:
                # Segunda tentativa, com um sinal que não depende de haver linha de grade
                # desenhada: a moldura impressa. Ver `trim_to_frame` para o que isso corrige.
                image, trimmed = trim_to_frame(image)

        # Aspecto perfeito e recorte confirmado valem mais que caixa esticada aceita no limite.
        score = float(np.clip(1.0 - abs(aspect - 1.0) / max(aspect_tolerance, 1e-6), 0.0, 1.0))
        candidates.append(
            DiagramCandidate(
                board_rgb=image,
                bbox_pdf=(float(bbox.x0), float(bbox.y0), float(bbox.x1), float(bbox.y1)),
                source="embedded",
                detector_score=0.5 + 0.5 * score if trimmed else 0.35 + 0.35 * score,
                native_size=(native_width, native_height),
                trimmed=trimmed,
            )
        )

    return candidates
