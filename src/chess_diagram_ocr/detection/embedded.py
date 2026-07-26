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
