from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

from .config import BOARD_SIZE, CELL_SIZE, DEFAULT_MAX_BOARDS, DEFAULT_READING_ORDER, ReadingOrder

logger = logging.getLogger(__name__)


class NoBoardDetectedError(RuntimeError):
    pass


MIN_AREA_FRACTION = 0.004
"""Fração da página abaixo da qual um contorno não é considerado. **Sem medição registrada.**

Este arquivo tinha 0 constantes nomeadas e 179 literais numéricos quando a S-131 o olhou --
contra 11 nomeadas em `detection/embedded.py`, 6 em `detection/hybrid.py` e 5 em
`preprocess.py`, todas com o número medido ao lado. Era o único caminho do núcleo sem
constante, sem medição e sem instrumento, e é a **única fonte de candidato** nos livros cuja
página não traz imagem embutida.

Nomear não é medir, e este docstring não finge o contrário: os números destas oito constantes
vêm da Fase 1 e ninguém os mediu desde então. O que a S-131 entrega é o **instrumento** --
`cvoff-census --recusas` grava o que cada uma barrou, com score, contraste e caixa --, para que
o primeiro a mexer num deles tenha contra o que comparar. A ordem é a da S-82, e não é
estética: `ANALISE_DETECCAO.md` §5 registra dois ajustes de limiar feitos sem censo, os dois
reprovados.
"""

ASPECT_MIN, ASPECT_MAX = 0.62, 1.62
"""Faixa de proporção largura/altura aceita. **Sem medição registrada** -- ver `MIN_AREA_FRACTION`.

Larga de propósito: o contorno de um diagrama impresso raramente fecha quadrado, e um
tabuleiro com legenda embutida no recorte estica no eixo vertical.
"""

AREA_SATURATION = 0.12
"""Fração da página em que a nota de área satura, para caixa grande não vencer só por tamanho."""

MIN_VISIBLE_RATIO = 0.65
"""Quanto da caixa precisa estar dentro da página. Corta o quad que sangra para fora da folha."""

MIN_QUAD_INSIDE_RATIO = 0.5
"""Quantos dos 4 cantos precisam cair dentro da página (com a margem de `QUAD_MARGIN_RATIO`)."""

QUAD_MARGIN_RATIO = 0.015
"""Folga, em fração do lado da página, para um canto contar como "dentro"."""

DEDUPE_IOU = 0.9
"""Acima disto, dois candidatos das duas passadas de limiar são o mesmo, e o pior sai."""

MIN_RELATIVE_AREA = 0.02
"""Fração da área do **maior** candidato abaixo da qual os outros são ruído da mesma página."""

MIN_SCORE_FLOOR = 0.06
"""Piso absoluto de score. Abaixo disto o candidato não entra, mesmo sendo o melhor da página."""

MIN_SCORE_RELATIVE = 0.25
"""Fração do score do melhor candidato abaixo da qual os outros saem. Vale o maior dos dois."""


@dataclass(frozen=True)
class RejectedQuad:
    """Um candidato de contorno que **não** entrou, e por qual guarda (S-131).

    O censo da S-82 conta o que entra e é cego ao que foi barrado — que é justamente onde mora
    o recall perdido. Sem isto, mexer num limiar é medir só um dos dois lados do efeito: dá
    para ver o falso positivo que sumiu, e não o diagrama que sumiu junto.

    A caixa é em **pixels da imagem** recebida por `detect_boards`, como o resto deste módulo;
    quem grava em pontos do PDF converte (é o que `detection_census` faz).
    """

    bbox: tuple[int, int, int, int]
    score: float
    checker: float
    """Contraste de casa do recorte (S-143). `0.0` quando a recusa foi antes de haver recorte."""

    reason: str
    """Qual guarda barrou. Os valores estão em `MOTIVOS_DE_RECUSA`."""


MOTIVOS_DE_RECUSA = (
    "aspecto",
    "fora-da-pagina",
    "area-relativa",
    "score-baixo",
    "sobreposicao",
    "teto",
)
"""Os motivos que `detect_boards` sabe registrar, na ordem em que as guardas rodam.

Tupla e não texto livre para que o relatório possa agrupar sem depender de ortografia, e para
que acrescentar uma guarda sem acrescentar o motivo seja um erro visível.

**Não há motivo para "abaixo do piso de área", e a ausência é decisão.** Ver o comentário em
`_extract_candidate_quads`: registrá-lo produziu 2,6 milhões de linhas de speckle de 4,6 pt num
CSV de 280 MB, contra 499 candidatos aceitos. Instrumento que ninguém abre não instrumenta.
"""


def order_quad_points(points: np.ndarray) -> np.ndarray:
    pts = np.array(points, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)

    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = pts[np.argmin(s)]  # top-left
    ordered[2] = pts[np.argmax(s)]  # bottom-right
    ordered[1] = pts[np.argmin(diff)]  # top-right
    ordered[3] = pts[np.argmax(diff)]  # bottom-left
    return ordered


def warp_from_quad(image_rgb: np.ndarray, quad: np.ndarray, target_size: int = BOARD_SIZE) -> np.ndarray:
    src = order_quad_points(quad)
    dst = np.array(
        [
            [0, 0],
            [target_size - 1, 0],
            [target_size - 1, target_size - 1],
            [0, target_size - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image_rgb, matrix, (target_size, target_size))


def _contour_geometry_score(quad: np.ndarray, image_area: float) -> float:
    area = cv2.contourArea(quad.astype(np.float32))
    if area <= 0:
        return 0.0
    # Keep small diagrams but reject tiny noisy contours.
    if area < image_area * MIN_AREA_FRACTION:
        return 0.0

    x, y, w, h = cv2.boundingRect(quad.astype(np.int32))
    if h == 0:
        return 0.0
    ratio = w / float(h)
    if ratio < ASPECT_MIN or ratio > ASPECT_MAX:
        return 0.0

    area_ratio = area / image_area
    # Saturates to avoid very large non-board boxes dominating by area only.
    area_component = min(area_ratio / AREA_SATURATION, 1.0)
    squareness = max(0.0, 1.0 - (abs(math.log(ratio)) / math.log(ASPECT_MAX)))
    return area_component * (squareness**2.4)


def _bbox_from_quad(quad: np.ndarray) -> tuple[int, int, int, int]:
    xs = quad[:, 0]
    ys = quad[:, 1]
    x0, y0 = int(np.min(xs)), int(np.min(ys))
    x1, y1 = int(np.max(xs)), int(np.max(ys))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def _bbox_iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / float(union) if union > 0 else 0.0


def _sort_selected_candidates(
    selected: list[tuple[np.ndarray, float, tuple[int, int, int, int]]],
    reading_order: ReadingOrder,
) -> None:
    if reading_order == "row":
        selected.sort(key=lambda item: (item[2][1], item[2][0]))
        return
    if reading_order != "column":
        raise ValueError("reading_order deve ser 'row' ou 'column'.")

    selected.sort(key=lambda item: item[2][0] + item[2][2] / 2.0)
    widths = [bbox[2] for _, _, bbox in selected]
    median_width = float(np.median(widths)) if widths else 0.0
    column_gap = max(8.0, median_width * 0.55)
    columns: list[list[tuple[np.ndarray, float, tuple[int, int, int, int]]]] = []

    for candidate in selected:
        _, _, bbox = candidate
        center_x = bbox[0] + bbox[2] / 2.0
        if not columns:
            columns.append([candidate])
            continue

        last_column = columns[-1]
        last_centers = [item[2][0] + item[2][2] / 2.0 for item in last_column]
        if abs(center_x - float(np.mean(last_centers))) <= column_gap:
            last_column.append(candidate)
        else:
            columns.append([candidate])

    ordered: list[tuple[np.ndarray, float, tuple[int, int, int, int]]] = []
    for column in columns:
        column.sort(key=lambda item: (item[2][1], item[2][0]))
        ordered.extend(column)
    selected[:] = ordered


def _bbox_visible_ratio(bbox: tuple[int, int, int, int], image_shape: tuple[int, int, int]) -> float:
    x, y, w, h = bbox
    if w <= 0 or h <= 0:
        return 0.0

    img_h, img_w = image_shape[:2]
    ix1 = max(0, x)
    iy1 = max(0, y)
    ix2 = min(img_w, x + w)
    iy2 = min(img_h, y + h)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    return (iw * ih) / float(w * h)


def _quad_point_inside_ratio(
    quad: np.ndarray,
    image_shape: tuple[int, int, int],
    margin_ratio: float = QUAD_MARGIN_RATIO,
) -> float:
    img_h, img_w = image_shape[:2]
    margin_x = img_w * margin_ratio
    margin_y = img_h * margin_ratio
    inside = (
        (quad[:, 0] >= -margin_x)
        & (quad[:, 0] <= (img_w - 1) + margin_x)
        & (quad[:, 1] >= -margin_y)
        & (quad[:, 1] <= (img_h - 1) + margin_y)
    )
    return float(np.mean(inside))


def _periodic_peak_score(profile: np.ndarray, period: int) -> float:
    if profile.size <= period:
        return 0.0
    expected = [period * i for i in range(1, 8)]
    peaks: list[float] = []
    radius = max(2, period // 8)
    for center in expected:
        left = max(0, center - radius)
        right = min(profile.size, center + radius + 1)
        if right <= left:
            continue
        peaks.append(float(np.max(profile[left:right])))
    if not peaks:
        return 0.0

    baseline = float(np.percentile(profile, 55))
    spread = float(np.percentile(profile, 90) - baseline)
    if spread <= 1e-6:
        return 0.0
    return float(np.clip((np.mean(peaks) - baseline) / spread, 0.0, 1.0))


def _small_gray(warped_rgb: np.ndarray) -> np.ndarray:
    """O recorte em 160x160 cinza -- 20 px por casa, que é onde as duas parcelas foram calibradas."""
    gray = cv2.cvtColor(warped_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    # 20 px per cell: enough for line and checker texture cues.
    return cv2.resize(gray, (160, 160), interpolation=cv2.INTER_AREA)


def _checker_score(small: np.ndarray) -> float:
    """Quanto as casas de paridade oposta diferem entre si, descontada a variação dentro de cada uma.

    É a parcela que responde **"isto é um tabuleiro?"**, e a única das duas que não tem como
    ser imitada por acaso: exige que as 32 casas de uma paridade sejam sistematicamente mais
    claras que as 32 da outra, num reticulado 8×8 alinhado com o recorte. Foto, retrato e
    moldura não têm 8×8 nenhum, a diferença entre as duas metades é ruído, e o `clip` em 0
    entrega **exatamente zero** -- ver `MIN_CHECKER_CONTRAST` na S-143.

    Não confundir com "quantas peças há": tabuleiro cheio derruba este número (as peças cobrem
    as casas) sem zerá-lo, porque o que sobra de casa visível continua sistemático.
    """
    cell_means = small.reshape(8, 20, 8, 20).mean(axis=(1, 3))
    parity = (np.indices((8, 8)).sum(axis=0) % 2) == 0
    even_cells = cell_means[parity]
    odd_cells = cell_means[~parity]
    contrast = abs(float(even_cells.mean()) - float(odd_cells.mean())) / 255.0
    within_var = (float(even_cells.std()) + float(odd_cells.std())) / (2.0 * 255.0)
    return float(np.clip(contrast * 2.4 - within_var * 0.9, 0.0, 1.0))


def _grid_score(small: np.ndarray) -> float:
    """Quanto a borda do recorte se repete a cada 20 px, nos dois eixos.

    Mede **linha periódica**, que um tabuleiro tem -- e uma moldura de quadro, uma faixa de
    fotos e uma fachada também. Sozinha ela não distingue tabuleiro de retrato emoldurado
    (medido: 0,43 a 0,80 nas fotos do relato da S-143), e é por isso que ela não serve de
    guarda. Como parcela da textura ela continua útil: é o que separa grade nítida de grade
    borrada entre dois recortes **do mesmo diagrama**, que é o uso da S-38 e da S-81.
    """
    gx = np.abs(np.diff(small, axis=1)).mean(axis=0)
    gy = np.abs(np.diff(small, axis=0)).mean(axis=1)
    return (_periodic_peak_score(gx, period=20) + _periodic_peak_score(gy, period=20)) / 2.0


def _board_pattern_score(warped_rgb: np.ndarray) -> float:
    small = _small_gray(warped_rgb)
    return float(np.clip(0.6 * _checker_score(small) + 0.4 * _grid_score(small), 0.0, 1.0))


def board_checker_score(warped_rgb: np.ndarray) -> float:
    """Só a parcela de xadrez de `_board_pattern_score`, para quem precisa dela isolada."""
    return _checker_score(_small_gray(warped_rgb))


def _extract_candidate_quads(
    image_rgb: np.ndarray,
    rejected: list[RejectedQuad] | None = None,
) -> list[tuple[np.ndarray, float, tuple[int, int, int, int]]]:
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh_base = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        41,
        8,
    )
    image_area = float(image_rgb.shape[0] * image_rgb.shape[1])
    raw_candidates: list[tuple[np.ndarray, float, tuple[int, int, int, int], float]] = []
    kernel = np.ones((3, 3), np.uint8)
    threshold_passes = [thresh_base, cv2.morphologyEx(thresh_base, cv2.MORPH_CLOSE, kernel, iterations=1)]

    for thresh in threshold_passes:
        # RETR_LIST keeps inner contours too. This helps when board is inside a larger rectangle.
        contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            if len(contour) < 4:
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter <= 0:
                continue
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)

            if len(approx) == 4:
                quad = approx.reshape(4, 2).astype(np.float32)
            else:
                rect = cv2.minAreaRect(contour)
                quad = cv2.boxPoints(rect).astype(np.float32)

            geom_score = _contour_geometry_score(quad, image_area)
            if geom_score <= 0:
                # **O que fica de fora do registro, e por quê.** Medido na primeira corrida do
                # instrumento: 2.627.289 recusas contra 499 aceitos, e o lado mediano da recusa
                # era 4,6 pt. Um CSV de 280 MB de manchas de contorno não é instrumento, é
                # ruído com cabeçalho. Só entra o que passou do piso de área -- abaixo dele o
                # `_contour_geometry_score` não está julgando um candidato, está descartando
                # speckle, e a recusa não pode ser recall perdido. Sobram as recusas por
                # **aspecto**, que são as informativas: algo do tamanho de um diagrama que foi
                # barrado por não ser quadrado o bastante.
                if rejected is not None and cv2.contourArea(quad.astype(np.float32)) >= image_area * MIN_AREA_FRACTION:
                    rejected.append(RejectedQuad(_bbox_from_quad(quad), 0.0, 0.0, "aspecto"))
                continue

            bbox = _bbox_from_quad(quad)
            # Reject heavily out-of-frame quads; they tend to produce page-level false positives.
            fora = (
                _bbox_visible_ratio(bbox, image_rgb.shape) < MIN_VISIBLE_RATIO
                or _quad_point_inside_ratio(quad, image_rgb.shape) < MIN_QUAD_INSIDE_RATIO
            )
            if fora:
                if rejected is not None:
                    rejected.append(RejectedQuad(bbox, geom_score, 0.0, "fora-da-pagina"))
                continue

            warped = warp_from_quad(image_rgb, quad, target_size=320)
            pattern_score = _board_pattern_score(warped)
            score = geom_score * (0.55 + 0.45 * pattern_score)
            quad_area = float(cv2.contourArea(quad.astype(np.float32)))
            raw_candidates.append((quad, float(score), bbox, quad_area))

    if not raw_candidates:
        return []

    raw_candidates.sort(key=lambda item: item[1], reverse=True)
    deduped: list[tuple[np.ndarray, float, tuple[int, int, int, int], float]] = []
    for candidate in raw_candidates:
        _, _, bbox, _ = candidate
        # A duplicata das duas passadas de limiar **não** vai para as recusas: ela é o mesmo
        # candidato visto duas vezes, e registrá-la faria o relatório contar cada achado como
        # um achado mais uma perda.
        if any(_bbox_iou(bbox, kept_bbox) > DEDUPE_IOU for _, _, kept_bbox, _ in deduped):
            continue
        deduped.append(candidate)

    largest_area = max(item[3] for item in deduped)
    min_relative_area = largest_area * MIN_RELATIVE_AREA
    if rejected is not None:
        rejected.extend(
            RejectedQuad(item[2], round(item[1], 4), 0.0, "area-relativa")
            for item in deduped
            if item[3] < min_relative_area
        )
    candidates = [item[:3] for item in deduped if item[3] >= min_relative_area]

    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates


def detect_boards(
    image_rgb: np.ndarray,
    target_size: int = BOARD_SIZE,
    max_boards: int = DEFAULT_MAX_BOARDS,
    iou_threshold: float = 0.25,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    warn_on_cap: bool = True,
    rejected: list[RejectedQuad] | None = None,
) -> list[tuple[np.ndarray, np.ndarray | None]]:
    """Recorta os diagramas de uma página, numerados em `reading_order` (S-14).

    O padrão vem de `config.DEFAULT_READING_ORDER` para que GUI e exportação numerem os
    diagramas igual: o padrão daqui era `"row"` e a exportação passava `"column"`, então o
    `[Diagram "2"]` do PGN podia apontar para outra posição que a da tela.

    `warn_on_cap=False` para quem pede **um** tabuleiro de propósito -- refinar o recorte
    de um candidato já localizado, por exemplo. Ali o teto é o pedido, não um limite do
    usuário, e o aviso da Fase 5 mandava "aumente 'Max diagramas'" numa configuração que
    não tem efeito nenhum sobre essa chamada.

    `rejected`, quando dado, recebe um `RejectedQuad` por candidato **barrado**, com o motivo
    (S-131). É o instrumento que faltava para mexer em limiar aqui: o censo da S-82 conta o que
    entra e é cego ao que foi barrado, e é do lado barrado que se vê o recall perdido. Custa
    uma lista por página quando pedido, e nada quando não.
    """
    candidates = _extract_candidate_quads(image_rgb, rejected)
    top_score = candidates[0][1] if candidates else 0.0
    min_score = max(MIN_SCORE_FLOOR, top_score * MIN_SCORE_RELATIVE)
    selected: list[tuple[np.ndarray, float, tuple[int, int, int, int]]] = []
    dropped_by_cap: list[float] = []

    def _anota(bbox: tuple[int, int, int, int], score: float, motivo: str) -> None:
        if rejected is not None:
            rejected.append(RejectedQuad(bbox, round(score, 4), 0.0, motivo))

    for candidate in candidates:
        _, score, bbox = candidate
        if score < min_score:
            _anota(bbox, score, "score-baixo")
            continue
        if any(_bbox_iou(bbox, kept_bbox) > iou_threshold for _, _, kept_bbox in selected):
            _anota(bbox, score, "sobreposicao")
            continue
        if len(selected) >= max_boards:
            dropped_by_cap.append(score)
            _anota(bbox, score, "teto")
            continue
        selected.append(candidate)

    if dropped_by_cap and warn_on_cap:
        # O corte e por score, e o score nao ordena diagrama por posicao: numa grade 3x3 o
        # nono pode ser o do canto superior direito. Cortar em silencio fez exatamente isso
        # no "A Matter of Endgame Technique", e nada na tela dizia que faltava um.
        logger.warning(
            "max_boards=%d cortou %d candidato(s) que passaram no filtro de qualidade "
            "(scores %s contra %.4f do ultimo aceito). Se a pagina tem mais diagramas que "
            "isso, aumente 'Max diagramas'.",
            max_boards,
            len(dropped_by_cap),
            ", ".join(f"{score:.4f}" for score in dropped_by_cap[:4]),
            selected[-1][1] if selected else 0.0,
        )

    if not selected:
        return []

    _sort_selected_candidates(selected, reading_order)
    boards: list[tuple[np.ndarray, np.ndarray | None]] = []
    for quad, _, _ in selected:
        boards.append((warp_from_quad(image_rgb, quad, target_size=target_size), quad))
    return boards


def detect_board(image_rgb: np.ndarray, target_size: int = BOARD_SIZE) -> tuple[np.ndarray, np.ndarray | None]:
    boards = detect_boards(image_rgb=image_rgb, target_size=target_size, max_boards=1, warn_on_cap=False)
    if not boards:
        raise NoBoardDetectedError("Nenhum tabuleiro de xadrez foi detectado na imagem.")
    return boards[0]


def split_board_into_cells(board_rgb: np.ndarray) -> list[np.ndarray]:
    if board_rgb.shape[0] != BOARD_SIZE or board_rgb.shape[1] != BOARD_SIZE:
        board_rgb = cv2.resize(board_rgb, (BOARD_SIZE, BOARD_SIZE))

    cells: list[np.ndarray] = []
    for row in range(8):
        for col in range(8):
            y0 = row * CELL_SIZE
            y1 = (row + 1) * CELL_SIZE
            x0 = col * CELL_SIZE
            x1 = (col + 1) * CELL_SIZE
            cells.append(board_rgb[y0:y1, x0:x1])
    return cells
