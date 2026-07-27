"""Detector de duas fontes: imagem embutida localiza, contorno alinha (S-12).

A S-12 propunha gerar candidatos das duas fontes de forma independente e, quando
discordassem, **ler as duas** e arbitrar por legalidade. A medição mostrou que não é preciso
pagar por isso, porque as duas fontes não competem pela mesma coisa:

| livro (10 páginas) | embutida crua | embutida + warp | contorno puro |
|---|---|---|---|
| `1937 Kemeri` | 0,478 / 0 ilegais | **0,538 / 0** | 0,431 / **2 ilegais** |
| `AAGAARD` | 0,999 / 0 | 1,000 / 0 | 1,000 / 0 |
| `Schiller` | 0,137 / 0 | **0,360 / 0** | 0,257 / 0 |
| `Karpov 1` | 0,906 / 0 | **0,962** / 1 | 0,948 / 0 |
| `Euwe Band 1-2` | 0,010 / 1 | **0,025 / 1** | 0,014 / 2 |

(confiança mínima média / posições ilegais)

Lido assim: o bbox embutido é melhor em **localizar** -- ele sabe o que é diagrama e o que é
figura, então mata o falso positivo que o contorno inventa (Kemeri: 2 posições ilegais viram
0). O warp por contorno é melhor em **alinhar** -- ele acha os cantos exatos do tabuleiro, e
recortar o bbox cru deixa a grade 8×8 fora de registro, o que derruba a confiança (Schiller:
0,137 contra 0,360).

Então a composição certa é uma por candidato, não uma escolha entre listas: usar o bbox para
saber onde olhar e rodar o contorno **dentro** dele para alinhar. Fica melhor que as duas
fontes isoladas em 4 dos 5 livros, e empata no quinto.

O contorno segue rodando na página inteira também, para não perder o que a imagem embutida
não cobre -- que é a maioria do acervo: 12 dos 27 PDFs são scan de página inteira e 2 são
vetoriais (ver o docstring do pacote).
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz
import numpy as np

from ..board_detection import _bbox_iou, _sort_selected_candidates, detect_boards
from ..config import BOARD_SIZE, DEFAULT_MAX_BOARDS, DEFAULT_READING_ORDER, ReadingOrder
from .embedded import DiagramCandidate, _pixels_for_bbox, candidates_from_embedded_images

logger = logging.getLogger(__name__)

OVERLAP_IOU = 0.50
"""Acima disto, candidato de contorno é considerado o mesmo diagrama de um embutido."""

REFINE_PADDING_PT = 6.0
"""Folga em pontos ao redor do bbox, para o contorno ter borda onde achar a moldura."""

EMBEDDED_SIZE_TOLERANCE = 0.30
"""Quanto o lado de um achado de contorno pode fugir do lado típico das imagens embutidas.

Numa página que declara diagramas de ~590 pt, o falso positivo do Kemeri tem tamanho bem
diferente e cai fora; os 4 diagramas por livro que o `Schiller` e o `Karpov` não declaram têm
o mesmo tamanho dos declarados e passam.
"""


def refine_candidate_with_contour(
    page: fitz.Page,
    candidate: DiagramCandidate,
    *,
    padding_pt: float = REFINE_PADDING_PT,
) -> DiagramCandidate:
    """Realinha um candidato embutido rodando o detector de contorno dentro do bbox dele.

    Devolve o candidato original quando o contorno não acha nada na região -- caso em que o
    recorte cru é o melhor que se tem, e não há razão para piorá-lo.
    """
    bbox = fitz.Rect(candidate.bbox_pdf)
    padded = fitz.Rect(bbox.x0 - padding_pt, bbox.y0 - padding_pt, bbox.x1 + padding_pt, bbox.y1 + padding_pt)
    padded = padded & page.rect
    if padded.is_empty:
        return candidate

    region = _pixels_for_bbox(page, padded, native_side=max(candidate.native_size))
    if region is None:
        return candidate

    found = detect_boards(region, max_boards=1)
    if not found:
        return candidate

    board_rgb, _quad = found[0]
    return DiagramCandidate(
        board_rgb=board_rgb,
        bbox_pdf=candidate.bbox_pdf,
        source="embedded",
        # Concordância entre as duas fontes é sinal de confiança, e sai de graça.
        detector_score=min(1.0, candidate.detector_score + 0.15),
        native_size=candidate.native_size,
        trimmed=True,
    )


def _pixel_bbox(bbox_pdf: tuple[float, float, float, float], scale: float) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox_pdf
    return (
        int(x0 * scale),
        int(y0 * scale),
        max(1, int((x1 - x0) * scale)),
        max(1, int((y1 - y0) * scale)),
    )


def detect_diagrams(
    page: fitz.Page,
    page_rgb: np.ndarray,
    *,
    max_boards: int = DEFAULT_MAX_BOARDS,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    refine_embedded: bool = True,
    size_prior_tolerance: float | None = EMBEDDED_SIZE_TOLERANCE,
) -> list[DiagramCandidate]:
    """Todos os diagramas da página, das duas fontes, sem duplicar e em ordem de leitura.

    `page_rgb` é a página já renderizada (o chamador costuma precisar dela de todo jeito, para
    exibir), e é o que alimenta o caminho por contorno.

    `size_prior_tolerance` controla o que fazer com candidato de contorno que **não** casa com
    nenhuma imagem embutida, numa página que tem imagens embutidas. Duas medições delimitaram
    a regra:

    - Unir os dois cegamente traz de volta o falso positivo que a imagem embutida evitava: no
      `1937 Kemeri` a figura que rende `8/8/8/8/8/8/8/8` volta pela porta do contorno.
    - Mas tratar a lista embutida como completa perde diagrama de verdade: no `Schiller` e no
      `Karpov`, 4 diagramas por livro que o contorno acha não têm imagem embutida listada.

    Então a lista embutida não vale como whitelist, vale como **prior de tamanho**: numa
    página cujos diagramas medem ~590 pt de lado, um achado de contorno desse tamanho é
    diagrama e um de tamanho muito diferente é figura. `None` desliga o filtro (união cega).
    """
    scale_x = page_rgb.shape[1] / page.rect.width if page.rect.width else 1.0
    scale_y = page_rgb.shape[0] / page.rect.height if page.rect.height else 1.0
    scale = (scale_x + scale_y) / 2.0

    embedded = candidates_from_embedded_images(page)
    if refine_embedded:
        embedded = [refine_candidate_with_contour(page, candidate) for candidate in embedded]

    embedded_boxes = [_pixel_bbox(candidate.bbox_pdf, scale) for candidate in embedded]
    candidates = list(embedded)

    # Lado tipico do diagrama nesta pagina, em pixels, segundo as imagens embutidas. Serve de
    # gabarito para separar achado de contorno que e diagrama de achado que e figura.
    expected_side: float | None = None
    if embedded and size_prior_tolerance is not None:
        sides = [max(box[2], box[3]) for box in embedded_boxes]
        expected_side = float(np.median(sides))

    # O contorno na pagina inteira e a unica fonte quando nao ha imagem embutida -- o caso da
    # maioria do acervo: 12 dos 27 PDFs sao scan de pagina inteira e 2 sao vetoriais.
    for board_rgb, quad in detect_boards(page_rgb, max_boards=max_boards, reading_order=reading_order):
        if quad is None:
            box = (0, 0, page_rgb.shape[1], page_rgb.shape[0])
        else:
            xs, ys = quad[:, 0], quad[:, 1]
            box = (int(xs.min()), int(ys.min()), max(1, int(xs.max() - xs.min())), max(1, int(ys.max() - ys.min())))

        if any(_bbox_iou(box, embedded_box) > OVERLAP_IOU for embedded_box in embedded_boxes):
            continue

        if expected_side is not None and size_prior_tolerance is not None:
            side = max(box[2], box[3])
            if abs(side - expected_side) > expected_side * size_prior_tolerance:
                logger.debug(
                    "contorno descartado por tamanho: %d px contra gabarito de %.0f px",
                    side,
                    expected_side,
                )
                continue

        candidates.append(
            DiagramCandidate(
                board_rgb=board_rgb,
                bbox_pdf=(box[0] / scale, box[1] / scale, (box[0] + box[2]) / scale, (box[1] + box[3]) / scale),
                source="contour",
                detector_score=0.5,
                native_size=(BOARD_SIZE, BOARD_SIZE),
            )
        )

    ordered = _order_candidates(candidates, scale=scale, reading_order=reading_order)
    return ordered[:max_boards]


def detect_diagrams_in_pdf_page(
    pdf_source: str | Path | bytes,
    page_index: int,
    page_rgb: np.ndarray,
    *,
    max_boards: int = DEFAULT_MAX_BOARDS,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
) -> list[DiagramCandidate]:
    """`detect_diagrams` para quem tem o caminho do PDF, e não um `fitz.Page` aberto.

    Existe para que a GUI e a exportação usem **o mesmo** detector. Elas já divergiam na
    ordem de leitura antes da S-14, com o resultado de o "diagrama 2" da tela não ser o
    `[Diagram "2"]` do PGN; repetir o erro na fonte de detecção seria pior, porque aí a
    divergência é no recorte e não só na numeração.

    Abre o documento a cada chamada, como `render_pdf_page` já faz -- irrelevante ao lado do
    render, e mantém a assinatura livre de objeto do PyMuPDF.
    """
    from ..pdf_io import _open_document

    with _open_document(pdf_source) as doc:
        if page_index < 0 or page_index >= doc.page_count:
            raise ValueError(f"Pagina {page_index} fora do intervalo (0..{doc.page_count - 1})")
        return detect_diagrams(
            doc[page_index],
            page_rgb,
            max_boards=max_boards,
            reading_order=reading_order,
        )


def _order_candidates(
    candidates: list[DiagramCandidate],
    *,
    scale: float,
    reading_order: ReadingOrder,
) -> list[DiagramCandidate]:
    """Ordena candidatos das duas fontes juntos, com a mesma regra da S-14.

    Reaproveita `_sort_selected_candidates` em vez de reimplementar o agrupamento por coluna:
    são a mesma decisão, e duas implementações divergiriam com o tempo -- que é exatamente o
    bug que a S-14 corrigiu.
    """
    if len(candidates) <= 1:
        return candidates

    # `_sort_selected_candidates` ordena tuplas (quad, score, bbox) in-place; o indice viaja
    # no lugar do quad para sabermos onde cada candidato foi parar.
    sortable = [
        (np.array([[index, 0]], dtype=np.float32), candidate.detector_score, _pixel_bbox(candidate.bbox_pdf, scale))
        for index, candidate in enumerate(candidates)
    ]
    _sort_selected_candidates(sortable, reading_order)
    return [candidates[int(item[0][0, 0])] for item in sortable]
