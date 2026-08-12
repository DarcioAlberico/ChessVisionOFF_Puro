"""Onde estão os diagramas da página exibida, para desenhá-los e para clicá-los (S-68).

**O problema.** O visualizador mostrava a página e nada mais: descobrir onde estavam os
diagramas exigia rodar o OCR da página inteira, e escolher *um* deles exigia arrastar o mouse
em volta dele à mão. Só que quem sabe onde eles estão é o detector da S-12, e ele já rodava --
o resultado ia direto para o reconhecimento e nunca chegava à tela.

**O que este módulo é.** A parte disso que dá para verificar sem abrir janela: converter a
caixa de um diagrama em retângulo de canvas, decidir qual caixa um clique acertou, e decidir o
que aquele clique significa. O desenho e os eventos ficam no `ui/pdf_panel.py`.

**Por que a caixa viaja em pontos do PDF, e não em pixels.** É a decisão da S-41, pela mesma
razão: o pixel só existe em relação a um DPI, e o DPI é um campo da tela que o usuário mexe. As
duas fontes já falam pontos -- `DiagramCandidate.bbox_pdf` e `RecognizedDiagram.bbox_pdf` --,
então guardar pixel aqui seria converter cedo para converter de volta depois.

**Por que o DPI entra na conversão e não vem do widget.** `canvas_rect` recebe o DPI em que a
página **na tela** foi rasterizada, que é o que `OverlayParams` guarda junto das caixas. Ler o
spinbox no momento de desenhar produziria retângulos deslocados no intervalo entre mudar o DPI
e a página ser rasterizada de novo -- e um retângulo deslocado é pior que nenhum, porque ele
afirma que o diagrama está onde não está.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - só para os tipos
    from chess_diagram_ocr.detection import DiagramCandidate
    from chess_diagram_ocr.service import RecognizedDiagram

logger = logging.getLogger(__name__)

__all__ = [
    "BoxClick",
    "DiagramBox",
    "OverlayParams",
    "PageBoxes",
    "PageBoxesCache",
    "boxes_from_candidates",
    "boxes_from_diagrams",
    "canvas_rect",
    "choose_boxes",
    "decide_box_click",
    "hit_test",
]

POINTS_PER_INCH = 72.0
"""O ponto do PDF. `pixel = ponto × dpi / 72`, e é a única conversão que existe aqui."""

DEFAULT_MAX_CACHED_PAGES = 64
"""Oito vezes o teto do `page_results`, e ainda assim irrisório: uma caixa são quatro floats e
um rótulo, contra os 1,83 MiB por diagrama que aquele cache carrega. O que limita este é a
utilidade de lembrar de páginas que o usuário não vai revisitar, não a memória."""


@dataclass(frozen=True)
class OverlayParams:
    """O que precisa ser igual para as caixas guardadas ainda valerem.

    Só dois campos, contra os quatro do `PageOcrParams`: detectar não usa modelo nem
    orientação. `dpi` entra porque a página rasterizada é a entrada do caminho por contorno --
    e porque é ele que converte ponto em pixel na hora de desenhar. `max_boards` entra porque é
    o teto que decide quantas caixas existem.
    """

    dpi: int
    max_boards: int


@dataclass(frozen=True)
class DiagramBox:
    """Um diagrama localizado na página, com o número que o editor usa para ele."""

    index: int
    """Posição do diagrama na página, em base 0 -- o mesmo índice do seletor "Selecionado".

    É o que faz o clique no retângulo e o número na aba Resultado falarem do mesmo diagrama.
    Que os dois venham da mesma ordenação não é coincidência: a caixa sai do mesmo detector, na
    mesma ordem de leitura, que o `recognize_page` vai usar (S-12/S-14).
    """

    bbox_pdf: tuple[float, float, float, float]
    source: str = ""
    """`"embedded"` ou `"contour"` (S-12). Vai para a dica de tela, não para a decisão."""

    recognized: bool = False
    """Se esta caixa veio de um diagrama **já lido**, e não só localizado.

    Muda o que o clique faz e como o retângulo é pintado. A distinção importa porque as duas
    fontes são igualmente confiáveis quanto a *onde*, e completamente diferentes quanto a *o
    que já se sabe* -- e prometer leitura onde só houve detecção seria o pior dos dois.
    """

    @property
    def label(self) -> str:
        """O número como o usuário o vê: base 1, igual ao seletor da aba Resultado."""
        return str(self.index + 1)


@dataclass(frozen=True)
class PageBoxes:
    """As caixas de uma página, com os parâmetros em que elas foram achadas."""

    page_index: int
    params: OverlayParams
    boxes: tuple[DiagramBox, ...] = ()

    def __len__(self) -> int:
        return len(self.boxes)

    @property
    def recognized(self) -> bool:
        """Se estas caixas vieram do OCR. Vazio não é reconhecido: é vazio."""
        return bool(self.boxes) and all(box.recognized for box in self.boxes)

    def rect_of(self, box: DiagramBox, zoom: float) -> tuple[float, float, float, float]:
        return canvas_rect(box, dpi=self.params.dpi, zoom=zoom)

    def index_at(self, x: float, y: float, zoom: float) -> int | None:
        return hit_test(self.boxes, x, y, dpi=self.params.dpi, zoom=zoom)


def canvas_rect(box: DiagramBox, *, dpi: int, zoom: float) -> tuple[float, float, float, float]:
    """A caixa em coordenadas do canvas: ponto do PDF → pixel da página → pixel da tela."""
    escala = (float(dpi) / POINTS_PER_INCH) * float(zoom)
    x0, y0, x1, y1 = box.bbox_pdf
    return (x0 * escala, y0 * escala, x1 * escala, y1 * escala)


def hit_test(
    boxes: Sequence[DiagramBox],
    x: float,
    y: float,
    *,
    dpi: int,
    zoom: float,
) -> int | None:
    """Qual diagrama o ponto acertou, ou `None`. **A menor caixa vence.**

    Empate acontece de verdade: o caminho por contorno às vezes acha a moldura do exercício
    *e* o tabuleiro dentro dela, e as duas caixas contêm o mesmo clique. Devolver a maior faria
    o clique no tabuleiro abrir a moldura -- que é o candidato que o modelo lê pior. Escolher a
    menor é escolher o mais específico, que é o que o dedo do usuário estava apontando.
    """
    achado: int | None = None
    menor_area: float | None = None
    for box in boxes:
        x0, y0, x1, y1 = canvas_rect(box, dpi=dpi, zoom=zoom)
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        area = (x1 - x0) * (y1 - y0)
        if menor_area is None or area < menor_area:
            menor_area, achado = area, box.index
    return achado


def boxes_from_candidates(candidates: Sequence[DiagramCandidate]) -> tuple[DiagramBox, ...]:
    """As caixas do detector (S-12), antes de qualquer leitura.

    A lista chega ordenada por ordem de leitura, e é dela que sai o índice: o mesmo detector,
    com os mesmos parâmetros, vai produzir a mesma ordem quando o OCR rodar. Renumerar aqui
    faria o "3" do retângulo abrir o diagrama 5 do editor -- o desencontro que a S-14 corrigiu
    entre a tela e o PGN, recriado entre a tela e ela mesma.
    """
    return tuple(
        DiagramBox(index=indice, bbox_pdf=tuple(candidato.bbox_pdf), source=candidato.source)  # type: ignore[arg-type]
        for indice, candidato in enumerate(candidates)
    )


def boxes_from_diagrams(items: Sequence[RecognizedDiagram]) -> tuple[DiagramBox, ...]:
    """As caixas do que já foi lido. Diagrama sem `bbox_pdf` não vira caixa.

    Fica de fora o resultado de recorte de área e o item aberto da fila ou do dataset: nenhum
    deles sabe de que ponto da página veio, e inventar um lugar para ele seria apontar para um
    diagrama que não é aquele. O índice é a posição na lista, que é o que o seletor
    "Selecionado" usa -- e não `item.index`, que num recorte de uma imagem qualquer é sempre 0.
    """
    return tuple(
        DiagramBox(
            index=indice,
            bbox_pdf=tuple(item.bbox_pdf),  # type: ignore[arg-type]
            source=item.detection_source,
            recognized=True,
        )
        for indice, item in enumerate(items)
        if item.bbox_pdf is not None
    )


def choose_boxes(
    *,
    recognized: tuple[DiagramBox, ...],
    detected: tuple[DiagramBox, ...],
) -> tuple[DiagramBox, ...]:
    """Qual das duas fontes vai para a tela quando as duas existem.

    O reconhecimento ganha, porque sabe o mesmo sobre *onde* e mais sobre *o que*: ele desenha
    verde, o clique nele é instantâneo e o destaque do diagrama aberto passa a valer.

    **Menos que o detector achou é o caso que obriga a regra a existir.** "OCR melhor diagrama"
    deixa a página com um resultado só, e o detector tinha desenhado seis caixas. Deixar o
    reconhecimento ganhar ali apagaria cinco diagramas da tela -- e, pior, prometeria que a
    caixa restante é a de número 1 da lista do detector, o que não é verdade: com `max_boards`
    igual a 1 o caminho por contorno devolve o candidato de maior score, e não o primeiro em
    ordem de leitura. Nesse caso ficam as seis caixas do detector, nenhuma marcada como lida --
    que é exatamente o que se sabe.
    """
    if recognized and len(recognized) >= len(detected):
        return recognized
    return detected


class BoxClick(str, Enum):
    """O que fazer quando o usuário clica num retângulo."""

    SELECT = "select"
    """Este diagrama já foi lido: levar o editor até ele. Instantâneo, e não refaz nada."""

    RECOGNIZE = "recognize"
    """Ainda não: reconhecer a página e então selecioná-lo."""


def decide_box_click(*, recognized_count: int, index: int) -> BoxClick:
    """A decisão do clique, dada a quantidade de diagramas já lidos **desta** página.

    **Por que reconhecer a página inteira, e não só o diagrama clicado.** Ler um recorte
    isolado é o caminho da seleção de área, e ele custa duas coisas que aqui não vale pagar: o
    recorte sai da página rasterizada em vez da imagem embutida do PDF -- que no `1937 Kemeri`
    tem 590×590 nativos contra ~430 px do render a 220 DPI (S-12) -- e não recebe o contexto de
    texto que decide o lado a jogar (S-16/S-17). O resultado seria um diagrama lido pior que o
    mesmo diagrama lido pelo botão "OCR todos diagramas", sem que nada na tela dissesse por
    quê. Reconhecer a página custa os outros diagramas uma vez; a partir daí todo clique nela é
    `SELECT`, inclusive o clique que só queria conferir.

    `recognized_count` menor que o índice clicado também cai em `RECOGNIZE`: é o caso do "OCR
    melhor diagrama", que deixa a página com um resultado só enquanto o detector desenhou seis
    caixas. Selecionar o índice 4 de uma lista de 1 abriria um diagrama que não é o clicado.
    """
    if index < 0:
        raise ValueError(f"Índice de caixa negativo: {index}")
    return BoxClick.SELECT if index < recognized_count else BoxClick.RECOGNIZE


class PageBoxesCache:
    """Cache LRU das caixas por `(documento, página)`.

    Existe porque virar a página e voltar não deveria pagar o detector de novo: ele é o passo
    caro do caminho (contorno em toda a página, mais a extração das imagens embutidas), e
    navegar para frente e para trás numa sequência de exercícios é o uso normal.

    O mesmo desenho do `PageResultsCache`, e de propósito: parâmetro divergente é **descartado,
    não adaptado** (S-24). Caixa achada a 220 DPI redesenhada como se fosse de 300 apontaria
    para o lugar errado com toda a confiança do mundo.
    """

    def __init__(self, max_pages: int = DEFAULT_MAX_CACHED_PAGES) -> None:
        self.max_pages = max(1, int(max_pages))
        self._entries: OrderedDict[tuple[str, int], PageBoxes] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: tuple[str, int]) -> bool:
        return key in self._entries

    def put(self, document: str, boxes: PageBoxes) -> None:
        key = (document, boxes.page_index)
        self._entries[key] = boxes
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_pages:
            self._entries.popitem(last=False)

    def get(self, document: str, page_index: int, params: OverlayParams) -> PageBoxes | None:
        """As caixas guardadas, ou `None` se não há ou se os parâmetros mudaram."""
        key = (document, page_index)
        guardado = self._entries.get(key)
        if guardado is None:
            return None
        if guardado.params != params:
            logger.debug(
                "Caixas da página %d descartadas: %s → %s.", page_index, guardado.params, params
            )
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return guardado

    def discard(self, document: str, page_index: int) -> None:
        self._entries.pop((document, page_index), None)

    def clear(self) -> None:
        self._entries.clear()
