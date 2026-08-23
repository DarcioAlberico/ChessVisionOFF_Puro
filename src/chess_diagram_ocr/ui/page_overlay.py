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
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING

from chess_diagram_ocr.field_eval import MATCH_IOU, bbox_iou

if TYPE_CHECKING:  # pragma: no cover - só para os tipos
    from chess_diagram_ocr.detection import DiagramCandidate
    from chess_diagram_ocr.service import RecognizedDiagram

logger = logging.getLogger(__name__)

__all__ = [
    "ESTADOS",
    "TRACO_POR_ESTADO",
    "BoxClick",
    "DiagramBox",
    "DroppedBoxes",
    "OverlayParams",
    "PageBoxes",
    "PageBoxesCache",
    "Traco",
    "boxes_from_candidates",
    "boxes_from_diagrams",
    "canvas_rect",
    "choose_boxes",
    "decide_box_click",
    "estado_da_caixa",
    "frase_de_caixa_tirada",
    "frase_de_caixas_devolvidas",
    "hit_test",
    "mark_confirmed",
    "mark_saved",
    "traco_da_caixa",
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

    confirmed: bool = False
    """A base de partidas reconheceu esta posição (S-74/S-75).

    Vem do arquivo de anotações, como o `saved` vem do CSV -- então aparece **antes de qualquer
    OCR**, ao abrir um livro já casado. É a informação de maior valor por pixel do visualizador:
    diz que aquele diagrama não precisa de olho humano, o que nenhuma outra marca da tela sabe
    afirmar. Confiança alta é estimativa; isto é uma partida registrada.
    """

    saved: bool = False
    """Se este diagrama já tem amostra gravada no `labels.csv` (S-71).

    **É independente de `recognized`, e isso é o ponto.** O que responde por ele é a
    procedência gravada no CSV, não o que está em memória: uma página aberta hoje mostra em
    verde o que foi salvo semana passada, antes de qualquer OCR rodar. É a resposta para "onde
    eu parei neste livro?", que é a pergunta que se faz ao abrir um livro pela quinta vez.
    """

    @property
    def label(self) -> str:
        """O número como o usuário o vê: base 1, igual ao seletor da aba Resultado."""
        return str(self.index + 1)


# ------------------------------------------- a cor não é o único portador do estado (S-159)

A_FAZER = "a_fazer"
LIDO = "lido"
PRONTO = "pronto"
DISPENSADO = "dispensado"
ESTADOS: tuple[str, ...] = (A_FAZER, LIDO, PRONTO, DISPENSADO)
"""Os quatro pontos em que um diagrama da página pode estar, na ordem do trabalho.

A mesma ordem de precedência de `box_color`, e é dela que sai `estado_da_caixa`: salvo antes de
confirmado porque salvo é trabalho **seu** já feito."""


@dataclass(frozen=True)
class Traco:
    """Como o retângulo de um estado é desenhado, além da cor.

    `espessura` e `tracejado` são o que o Tk aceita direto em `create_rectangle`; `glifo` vai na
    etiqueta preenchida do número, que já tem contraste medido de 6:1 a 10:1 contra o texto.
    """

    espessura: int
    tracejado: tuple[int, int] | None
    glifo: str

    @property
    def assinatura(self) -> tuple[int, tuple[int, int] | None, str]:
        """O par (traço, glifo) que precisa ser único entre os quatro estados."""
        return (self.espessura, self.tracejado, self.glifo)


TRACO_POR_ESTADO: dict[str, Traco] = {
    A_FAZER: Traco(espessura=2, tracejado=None, glifo=""),
    LIDO: Traco(espessura=2, tracejado=(2, 2), glifo="·"),
    PRONTO: Traco(espessura=4, tracejado=None, glifo="✓"),
    DISPENSADO: Traco(espessura=1, tracejado=(6, 4), glifo="–"),
}
"""**O segundo canal**, e por que ele é barato aqui (S-159).

O visualizador desenhava quatro estados em quatro matizes e mais nada: nem forma, nem traço,
nem letra. E o par mais crítico era o menos distinguível -- azul `#4da3ff` contra violeta
`#9b7bff` dá **1,20:1** de contraste entre si, separados essencialmente por matiz, numa linha de
2 px sobre página impressa hachurada.

Para quem tem protanopia ou deuteranopia -- **~8% dos homens** -- "ainda a fazer" e "não precisa"
eram o mesmo retângulo. E são justamente os dois cuja confusão custa trabalho: refazer o que já
estava pronto, ou pular o que faltava.

A caixa já é um retângulo, então o traço não custa pixel nenhum: contínuo fino para "a fazer",
pontilhado para "lido", **grosso** para "pronto", tracejado largo e fino para "dispensado". E a
etiqueta do número já é preenchida, então o glifo entra sem disputar espaço com o diagrama."""


def estado_da_caixa(box: DiagramBox) -> str:
    """Em que ponto do trabalho este diagrama está. Mesma precedência de `pdf_panel.box_color`.

    Existe separada da cor de propósito: é ela que garante que os dois canais -- matiz e traço
    -- digam **a mesma coisa**. Duas funções decidindo o estado por conta própria é como um
    retângulo verde tracejado de "dispensado" apareceria.
    """
    if box.saved:
        return PRONTO
    if box.confirmed:
        return DISPENSADO
    return LIDO if box.recognized else A_FAZER


def traco_da_caixa(box: DiagramBox) -> Traco:
    """O traço e o glifo desta caixa. Total: todo estado tem um, e todo box tem um estado."""
    return TRACO_POR_ESTADO[estado_da_caixa(box)]


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

    @property
    def all_saved(self) -> bool:
        """Se **todo** diagrama desta página já tem amostra no `labels.csv` (S-142).

        A pergunta da **página**, sobre a mesma verdade que o `saved` responde por diagrama
        (S-71) -- e é a pergunta que o verde caixa a caixa não responde. Contar os retângulos
        verdes e compará-los com o total era aritmética que o usuário fazia de cabeça a cada
        virada de página, e que se erra justamente na página de nove diagramas: a que custa
        caro reabrir depois.

        **Vazio não é concluído: é vazio.** Mesma regra do `recognized`, e pela mesma razão.
        Uma página de prosa não tem diagrama para salvar, e dizer que ela está terminada
        misturaria "não há trabalho aqui" com "o trabalho daqui está feito" -- a distinção que
        o par "não se sabe"/"não há" já mantém em pé no resto do visualizador.

        Só olha `saved`. Um diagrama confirmado pela base (S-75) **não** conta: violeta é "não
        precisa", e uma página de confirmados não rendeu amostra nenhuma para o dataset.
        """
        return bool(self.boxes) and all(box.saved for box in self.boxes)

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


def mark_saved(boxes: Sequence[DiagramBox], saved: Collection[int]) -> tuple[DiagramBox, ...]:
    """Carimba quais caixas já têm amostra gravada (S-71).

    **Um lugar só, e no momento de desenhar.** As caixas do detector ficam num cache por
    página; se o carimbo entrasse nelas quando a detecção rodou, salvar uma amostra não
    pintaria de verde o diagrama que acabou de ser salvo -- ele só mudaria de cor na próxima
    visita àquela página, que é quando o cache fosse refeito. Carimbar na hora de desenhar faz
    a cor acompanhar o CSV, que é a fonte da verdade.
    """
    if not saved:
        return tuple(boxes)
    return tuple(replace(box, saved=box.index in saved) for box in boxes)


def mark_confirmed(boxes: Sequence[DiagramBox], confirmed: Collection[int]) -> tuple[DiagramBox, ...]:
    """Carimba quais posições a base de partidas reconheceu (S-75).

    Função separada da `mark_saved`, e não um parâmetro a mais nela, porque as duas respondem
    perguntas independentes: uma diz que **você** trabalhou aquele diagrama, a outra que ele
    **não precisa** ser trabalhado. Um diagrama pode ter as duas marcas, uma só, ou nenhuma --
    e juntá-las numa chamada faria parecer que uma implica a outra.
    """
    if not confirmed:
        return tuple(boxes)
    return tuple(replace(box, confirmed=box.index in confirmed) for box in boxes)


def boxes_from_candidates(candidates: Sequence[DiagramCandidate]) -> tuple[DiagramBox, ...]:
    """As caixas do detector (S-12), antes de qualquer leitura.

    A lista chega ordenada por ordem de leitura, e é dela que sai o índice: o mesmo detector,
    com os mesmos parâmetros, vai produzir a mesma ordem quando o OCR rodar. Renumerar aqui
    faria o "3" do retângulo abrir o diagrama 5 do editor -- o desencontro que a S-14 corrigiu
    entre a tela e o PGN, recriado entre a tela e ela mesma.

    Quem já foi salvo não se decide aqui: é `mark_saved`, na hora de desenhar.
    """
    return tuple(
        DiagramBox(
            index=indice,
            bbox_pdf=tuple(candidato.bbox_pdf),  # type: ignore[arg-type]
            source=candidato.source,
        )
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


def frase_de_caixa_tirada(box: DiagramBox | None, tiradas_na_pagina: int) -> str:
    """O que a barra de status diz depois de tirar uma caixa (S-177).

    Mora aqui e não na janela pela mesma razão que `rodape.descricao_dos_diagramas`: é decisão
    de texto, é pura, e é o que se quer poder afirmar sem abrir janela.

    **Diz três coisas, e cada uma responde a uma pergunta que o gesto abre.** Qual caixa saiu
    (o número que estava desenhado nela), quantas já saíram desta página (para que remover cinco
    por engano não seja invisível), e **os dois caminhos a partir dali** -- recortar o diagrama à
    mão, que é o motivo de a remoção existir, e devolver o que foi tirado, que é a saída de quem
    errou o alvo. Uma ação destrutiva que não nomeia o caminho de volta obriga a pessoa a
    descobri-lo no menu depois de já ter perdido a caixa.

    `box=None` é "aquele retângulo já não está na página" -- o duplo-clique no botão direito, ou
    o botão disparado sobre uma lista que mudou embaixo dele.
    """
    if box is None:
        return "Essa caixa não está mais na página."
    plural = "s" if tiradas_na_pagina > 1 else ""
    return (
        f"Caixa {box.label} tirada da página "
        f"({tiradas_na_pagina} caixa{plural} tirada{plural} aqui). "
        "Use Selecionar área (OCR) para recortar o diagrama, ou Ver ▸ Devolver as caixas "
        "tiradas desta página para trazê-la de volta."
    )


def frase_de_caixas_devolvidas(quantas: int, page_index: int) -> str:
    """O que a barra diz ao devolver as caixas tiradas de uma página (S-177).

    Zero tem frase própria, e não a mesma com um número: "0 caixas devolvidas" afirma que houve
    uma devolução, e o que houve foi um comando sobre uma página que não tinha o que devolver.
    """
    if not quantas:
        return "Nenhuma caixa foi tirada desta página."
    plural = "s" if quantas > 1 else ""
    return f"{quantas} caixa{plural} devolvida{plural} à página {page_index}."


class DroppedBoxes:
    """As caixas que o usuário **tirou** da página, por `(documento, página)` (S-177).

    **O que isto existe para resolver.** O detector erra, e quando erra a caixa errada não é
    inerte: ela ocupa uma vaga do `max_boards`, entra na numeração que o `[Diagram "N"]` do PGN
    usa, e -- se for grande -- esconde os diagramas de verdade debaixo dela. Até aqui a única
    resposta era desligar "Marcar diagramas" para a página inteira, que apaga junto o que estava
    certo. A S-176 conserta uma classe de erro do detector; esta é a saída para as outras, que
    são inesgotáveis por natureza.

    **Guarda a caixa em pontos do PDF, e não o índice.** É a decisão que faz a remoção
    sobreviver ao que acontece depois dela. O índice de uma caixa é a posição dela numa lista
    que muda: as caixas do detector viram as do reconhecimento quando o OCR roda (`choose_boxes`),
    e as duas listas podem ter tamanhos diferentes -- é exatamente o caso do "OCR melhor
    diagrama". Uma remoção gravada por índice passaria a apagar outro diagrama. Gravada por
    geometria, ela continua apagando **aquele retângulo**, venha ele de que fonte vier.

    O casamento é por IoU, com o mesmo limiar do `field_draft` e do `field_eval`
    (`field_eval.MATCH_IOU`): usar outro número aqui faria a tela chamar de "a mesma caixa" o
    que a avaliação conta como duas.

    **É de sessão, e não vai para arquivo.** O que sobrevive ao programa é o que foi
    *afirmado* -- a amostra do `labels.csv`, a anotação do conjunto de campo --, e tirar uma
    caixa da tela não é uma afirmação sobre o livro: é remover um estorvo do caminho para poder
    usar `Selecionar área (OCR)` em cima do que ficou. Quem quer registrar que ali não há
    diagrama tem `Tirar o selecionado`, que grava no conjunto de campo.
    """

    def __init__(self, same_box_iou: float = MATCH_IOU) -> None:
        self.same_box_iou = float(same_box_iou)
        self._dropped: dict[tuple[str, int], list[tuple[float, float, float, float]]] = {}

    def __len__(self) -> int:
        return sum(len(caixas) for caixas in self._dropped.values())

    def drop(self, document: str, page_index: int, bbox_pdf: tuple[float, float, float, float]) -> None:
        """Marca esta caixa como tirada. Repetir a mesma caixa não a duplica."""
        guardadas = self._dropped.setdefault((document, page_index), [])
        if any(bbox_iou(bbox_pdf, outra) >= self.same_box_iou for outra in guardadas):
            return
        guardadas.append(tuple(float(valor) for valor in bbox_pdf))  # type: ignore[arg-type]

    def count(self, document: str, page_index: int) -> int:
        """Quantas caixas foram tiradas desta página. É o que o rodapé precisa saber."""
        return len(self._dropped.get((document, page_index), ()))

    def restore(self, document: str, page_index: int) -> int:
        """Devolve todas as caixas desta página. Retorna quantas voltaram.

        Página a página, e não um "desfazer" global: a remoção é sobre a página que está na
        tela, e desfazê-la noutra página seria mudar o que o usuário não está vendo.
        """
        return len(self._dropped.pop((document, page_index), ()))

    def clear(self) -> None:
        """Esquece tudo. Chamado ao trocar de livro, junto do resto do estado do documento."""
        self._dropped.clear()

    def apply(
        self, document: str, page_index: int, boxes: Sequence[DiagramBox]
    ) -> tuple[DiagramBox, ...]:
        """Tira da lista as caixas que o usuário removeu desta página.

        **Não renumera o que sobra, e isso é o ponto.** `DiagramBox.index` é o que liga o
        retângulo ao seletor "Selecionado" e ao `[Diagram "N"]` do PGN; renumerar faria o clique
        no retângulo "2" abrir o diagrama 3 do editor. O buraco na numeração é a informação
        honesta: ali havia uma caixa, e você a tirou.
        """
        guardadas = self._dropped.get((document, page_index))
        if not guardadas:
            return tuple(boxes)
        return tuple(
            box
            for box in boxes
            if not any(bbox_iou(box.bbox_pdf, outra) >= self.same_box_iou for outra in guardadas)
        )


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
