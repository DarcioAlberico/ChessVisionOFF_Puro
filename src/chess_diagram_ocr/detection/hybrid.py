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

import cv2
import fitz
import numpy as np

from ..board_detection import (
    _bbox_iou,
    _board_pattern_score,
    _sort_selected_candidates,
    board_checker_score,
    detect_boards,
)
from ..config import BOARD_SIZE, DEFAULT_MAX_BOARDS, DEFAULT_READING_ORDER, ReadingOrder
from ..pdf_io import PdfSource
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


MIN_CHECKER_CONTRAST = 0.0
"""Piso do contraste entre casas para um achado de **contorno** ser diagrama (S-143).

**O relato.** Capa e prancha de retrato do `Karpov 1` (páginas 1 e 7) rendiam 10 caixas onde
não há diagrama nenhum: o título, a grade de fotos dos campeões, cada retrato, e -- na página
do Steinitz -- três casas do tabuleiro *pintado ao fundo do quadro* mais a moldura inteira.

É exatamente o alvo que a S-80 previu e não conseguiu confirmar: "um ornamento grande -- capa
de capítulo, selo, **foto quadrada** -- passaria dos 72 pt". Ela o deu como tendo "zero
instâncias confirmadas no acervo" porque `sample_pages` **descarta as bordas do livro de
propósito**, e capa e prancha moram ali. O censo nunca olhou onde o defeito vive. Corrigido em
`census_book(front_matter=...)`.

**Por que o contraste de xadrez, e não a textura.** `board_texture_score` é
`0,6·xadrez + 0,4·grade`, e a parcela de **grade** é o que uma foto imita bem: moldura de
quadro, faixa de retratos e fachada produzem borda periódica. Medido nas páginas do relato, a
grade das fotos dá 0,04 a 0,80 -- acima de diagramas legítimos. Misturar as duas foi o que fez
a S-80 medir 0,29 numa foto contra 0,158 num `Polgar` impecável e concluir, corretamente para
o número que ela olhava, que não havia corte que prestasse.

A parcela de **xadrez** não tem como ser imitada: ela exige que as 32 casas de uma paridade
sejam sistematicamente mais claras que as 32 da outra, num reticulado 8×8 alinhado com o
recorte. Onde não há tabuleiro a diferença entre as duas metades é ruído, o `clip` em 0 morde,
e o resultado é **exatamente zero**.

**Medido no acervo (32 livros, amostra do censo + 8 páginas de frente por livro):**

| população | com xadrez zero |
|---|---|
| os 10 do relato | **10 de 10** |
| contorno na frente do livro (capa, rosto, prancha) | 73 de 99 |
| contorno na amostra do censo | 21 de 841 |

**E os 21 não são perda**, que é o que separa isto da S-80. Rodado o OCR de verdade em todo
candidato de contorno do acervo, o corte cai inteiro abaixo do gate de exportação: os 12 do
`Reinfeld` são os recortes da coluna esquerda, que o contorno fecha em 101×116 pt em vez de
116×116 -- tabuleiro **cortado**, que o warp estica e desalinha. Eles leem 0,0001 a 0,41
enquanto os gêmeos bem recortados da mesma página leem 0,998 e acima.

**Zero, e por quê.** O número não é ajustado à amostra: é onde a comparação sinal-contra-ruído
troca de sinal (`contraste·2,4 ≤ dispersão·0,9`). O candidato legítimo mais próximo do corte no
acervo é um `Polgar` de 0,0616 -- posição de abertura, 28 peças, o caso que derruba esta
parcela --, então qualquer valor em (0; 0,06) se comportaria igual aqui. Zero é o que tem
significado independente do acervo, e é preferível por isso.

**Só contorno.** Imagem embutida é *declaração* do PDF e continua ganhando (S-12); ela tem as
guardas dela. Os 3 embutidos com xadrez zero no acervo ficam de fora deste guarda de propósito.
"""


REFINE_TOLERANCE = 0.02
"""Quanto o refino pode piorar a textura de tabuleiro e ainda ser aceito (S-38).

Não é zero porque `_board_pattern_score` tem ruído de reamostragem: o recorte refinado é
outro conjunto de pixels, e uma diferença de ±0,01 entre dois recortes igualmente bons não
significa nada. Zero faria o refino ser recusado metade das vezes por sorteio.
"""


def board_texture_score(board_rgb: np.ndarray) -> float:
    """Quanto este recorte parece um tabuleiro: contraste entre casas mais grade periódica.

    Envelopa `_board_pattern_score` na resolução em que ele foi calibrado (320 px, 40 por
    casa). Chamá-lo direto num recorte de outro tamanho compara números que não são
    comparáveis, e a decisão da S-38 é exatamente uma comparação.
    """
    return _board_pattern_score(cv2.resize(board_rgb, (320, 320), interpolation=cv2.INTER_AREA))


def board_checker_contrast(board_rgb: np.ndarray) -> float:
    """Só a parcela de xadrez da textura, na mesma resolução calibrada (S-143).

    Separada de `board_texture_score` porque as duas parcelas respondem perguntas
    diferentes, e misturá-las é o que fez a S-80 fracassar -- ver `MIN_CHECKER_CONTRAST`.
    """
    return board_checker_score(cv2.resize(board_rgb, (320, 320), interpolation=cv2.INTER_AREA))


def refine_candidate_with_contour(
    page: fitz.Page,
    candidate: DiagramCandidate,
    *,
    padding_pt: float = REFINE_PADDING_PT,
    tolerance: float = REFINE_TOLERANCE,
) -> DiagramCandidate:
    """Realinha um candidato embutido rodando o detector de contorno dentro do bbox dele.

    Devolve o candidato original quando o contorno não acha nada na região -- caso em que o
    recorte cru é o melhor que se tem, e não há razão para piorá-lo.

    **E também quando o que ele acha é pior (S-38).** Até aqui a função conferia se o
    contorno tinha achado *alguma coisa*, nunca se o que achou era *melhor*, e a diferença
    não é acadêmica: na página 80 do `Karpov 1` o bbox embutido do candidato #4 contém um
    diagrama impecável, e o refino o substituía por um trapézio de texto que o modelo lia
    como oito reis brancos, com confiança 0,0004.

    Medido nos seis candidatos daquela página, `board_texture_score` cru → refinado:

    | candidato | cru | refinado | |
    |---|---|---|---|
    | #0 | 0,3138 | 0,6042 | melhora |
    | #1 | 0,2000 | 0,4616 | melhora |
    | #2 | 0,3511 | **0,2388** | **piora** |
    | #3 | 0,2000 | 0,4271 | melhora |
    | #4 | 0,2892 | **0,2252** | **piora -- é o dos oito reis** |
    | #5 | 0,3306 | 0,5059 | melhora |

    O refino ajuda em quatro e atrapalha em dois. Ele fica: alinhar a grade é o que a medição
    da S-12 mostrou valer 0,137 → 0,360 de confiança no `Schiller`. O que muda é passar a
    conferir o resultado, e é a mesma regra que a função já aplicava ao caso "não achou
    nada" -- só que agora aplicada ao caso "achou coisa pior".
    """
    bbox = fitz.Rect(candidate.bbox_pdf)
    padded = fitz.Rect(bbox.x0 - padding_pt, bbox.y0 - padding_pt, bbox.x1 + padding_pt, bbox.y1 + padding_pt)
    padded = padded & page.rect
    if padded.is_empty:
        return candidate

    region = _pixels_for_bbox(page, padded, native_side=max(candidate.native_size))
    if region is None:
        return candidate

    found = detect_boards(region, max_boards=1, warn_on_cap=False)
    if not found:
        return candidate

    board_rgb, _quad = found[0]
    antes = board_texture_score(candidate.board_rgb)
    depois = board_texture_score(board_rgb)
    if depois < antes - tolerance:
        # Descartar em silêncio foi o que deixou o trapézio do Karpov passar por semanas
        # parecendo um problema do classificador.
        logger.info(
            "Refino do contorno descartado em %s: textura de tabuleiro cairia de %.4f para "
            "%.4f. Fica o recorte embutido cru.",
            tuple(round(value) for value in candidate.bbox_pdf),
            antes,
            depois,
        )
        return candidate

    return DiagramCandidate(
        board_rgb=board_rgb,
        bbox_pdf=candidate.bbox_pdf,
        source="embedded",
        # Concordância entre as duas fontes é sinal de confiança, e sai de graça.
        detector_score=min(1.0, candidate.detector_score + 0.15),
        native_size=candidate.native_size,
        trimmed=True,
        # A proveniencia sobrevive ao refino (S-81). Reconstruir o candidato sem ela zerava o
        # `merged_tiles`, e as duas regras que dependem dele -- a uniao nao suprime contorno e
        # a uniao nao calibra o gabarito de tamanho -- nunca chegavam a rodar.
        merged_tiles=candidate.merged_tiles,
    )


MERGED_CONTAINMENT = 0.70
"""Fração da **união de ladrilhos** que precisa estar dentro do achado de contorno para os
dois falarem do mesmo diagrama (S-81).

`OVERLAP_IOU` não serve aqui, e o caso mostra por quê: na página 168 do `GALLAGHER` a união
de 77×91 pt está **97% dentro** do achado de contorno de 120×120, e mesmo assim o IoU dá 0,41
-- porque a união é bem menor, e a diferença de área infla o denominador. IoU pergunta "as
duas caixas são a mesma?"; aqui a pergunta é "uma está dentro da outra?", que é razão sobre a
menor.

Só vale para união. Imagem embutida declarada continua respondendo a `OVERLAP_IOU`, porque
ali as duas fontes disputam o mesmo retângulo e não há contenção a resolver."""

MERGED_TILES_MARGIN = 0.10
"""Quanto o contorno precisa ser melhor que uma **união de ladrilhos** para tomar o lugar dela.

Só existe margem porque `board_texture_score` tem ruído de reamostragem, o mesmo motivo de
`REFINE_TOLERANCE`. Nos dois casos medidos no `GALLAGHER` a diferença é de 0,40 e 0,58 -- muito
acima disto, e a margem não decide nada ali. Ela existe para o empate."""


def _same_region(
    contour_box: tuple[int, int, int, int],
    embedded_box: tuple[int, int, int, int],
    *,
    merged: bool,
) -> bool:
    """As duas caixas falam do mesmo diagrama?

    Para imagem embutida declarada, é `OVERLAP_IOU` como sempre. Para **união de ladrilhos**,
    é contenção: a união costuma ser bem menor que o tabuleiro inteiro que o contorno acha, e
    o IoU castiga essa diferença de área a ponto de dar 0,41 onde uma caixa está 97% dentro
    da outra. Ver `MERGED_CONTAINMENT`.
    """
    if _bbox_iou(contour_box, embedded_box) > OVERLAP_IOU:
        return True
    if not merged:
        return False

    ax, ay, aw, ah = contour_box
    bx, by, bw, bh = embedded_box
    largura = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    altura = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = largura * altura
    menor = min(aw * ah, bw * bh)
    return menor > 0 and inter / menor >= MERGED_CONTAINMENT


def _contour_wins_over_merged(embedded: DiagramCandidate, contour_rgb: np.ndarray) -> bool:
    """O achado de contorno deve substituir este candidato embutido sobreposto? (S-81)

    Quase sempre **não**, e é a regra desde a S-12: a imagem embutida é uma *declaração* do
    PDF sobre onde está o diagrama, e o contorno é uma inferência sobre pixels. Declaração
    ganha.

    **A união de ladrilhos não é declaração nenhuma** -- ela é uma inferência nossa sobre um
    punhado de imagens que se encostam, e nada garante que o retângulo resultante seja um
    tabuleiro. Medido no `GALLAGHER`: nas páginas 168 e 169 a união produziu caixas de 91 pt
    com textura 0,34 e 0,11 que suprimiram achados de contorno de 120 pt com textura 0,74 e
    0,69 -- e na 169 uma união engoliu **dois** diagramas bons.

    Então, e só então, as duas fontes competem, e a comparação é legítima onde a da S-80 não
    era: aqui os dois recortes são **da mesma região da mesma página**, que é exatamente o que
    a S-38 já faz em `refine_candidate_with_contour`. O que não se pode é comparar a nota de
    livros diferentes, ou contra um piso fixo -- ver a S-80 em `docs/ANALISE_DETECCAO.md`,
    onde um corte absoluto apagava diagramas impecáveis do `Polgar` e do `Reinfeld`.

    Duas guardas antes de tentar: só vale para união (`merged_tiles`), e a união tem de estar
    perdendo por uma margem que não seja ruído de reamostragem.
    """
    if not embedded.merged_tiles:
        return False

    nota_embutida = board_texture_score(embedded.board_rgb)
    nota_contorno = board_texture_score(contour_rgb)
    if nota_contorno <= nota_embutida + MERGED_TILES_MARGIN:
        return False

    logger.info(
        "Uniao de %d ladrilhos substituida pelo achado de contorno em %s: textura %.4f contra "
        "%.4f. A uniao e inferencia nossa, nao declaracao do PDF.",
        embedded.merged_tiles,
        tuple(round(valor) for valor in embedded.bbox_pdf),
        nota_embutida,
        nota_contorno,
    )
    return True


def _typical_side(sides: list[float], tolerance: float) -> float | None:
    """O lado de diagrama **desta página**, segundo as imagens embutidas dela.

    Era `np.median(sides)`, e a mediana responde a pergunta errada quando a lista tem duas
    populações. Mediana é robusta a *outlier*, não a **bimodalidade**: numa página com um
    glifo de 15 pt e um diagrama de 154 pt ela dá ~85 pt, que não é o tamanho de nada que
    exista ali. Com a tolerância de 30%, a janela aceita vira 59--110 pt, e **todo achado de
    contorno do tamanho real seria recusado** -- o prior de tamanho, que existe para
    *recuperar* diagrama não declarado (4 por livro no `Schiller` e no `Karpov`, medidos na
    S-12), passava a bloqueá-los. Medido em 42 das 1181 páginas do `Secrets`.

    A S-78 tira o glifo da lista antes de ela chegar aqui, então o caso medido não se repete
    por aquela porta. Esta função fecha a **classe**: qualquer página que misture dois
    tamanhos -- diagrama grande de destaque com diagramas pequenos de variante, capa de
    capítulo, fragmento -- caía no mesmo buraco, e nenhuma dessas some com um piso.

    A regra é agrupar os lados por proximidade relativa e tomar o **maior grupo**, com empate
    resolvido pelo lado maior: numa página com um diagrama grande e um pequeno, o gabarito
    tem de ser o do grupo que se repete, e na dúvida o maior, porque diagrama pequeno demais
    já é o que as outras guardas barram.

    Devolve `None` para lista vazia, e o próprio valor quando há um só -- que é o que a
    mediana fazia, e continua certo.
    """
    if not sides:
        return None
    if len(sides) == 1:
        return sides[0]

    ordenados = sorted(sides)
    grupos: list[list[float]] = [[ordenados[0]]]
    for lado in ordenados[1:]:
        referencia = grupos[-1][-1]
        # A mesma tolerancia que decide o filtro decide o agrupamento: dois lados que o filtro
        # aceitaria como o mesmo diagrama sao, por definicao, o mesmo grupo.
        if referencia > 0 and abs(lado - referencia) <= referencia * tolerance:
            grupos[-1].append(lado)
        else:
            grupos.append([lado])

    maior = max(grupos, key=lambda grupo: (len(grupo), max(grupo)))
    return float(np.median(maior))


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
    checker_contrast_floor: float | None = MIN_CHECKER_CONTRAST,
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

    O gabarito sai de `_typical_side` e não de `np.median` desde a S-79: a mediana entrega um
    número que não é o tamanho de nada quando a página tem duas populações de tamanho, e o
    prior passa a recusar exatamente o diagrama que ele existe para recuperar.

    `checker_contrast_floor` recusa achado de contorno **sem contraste de casa nenhum** -- a
    foto, o retrato e a moldura da S-143. `None` desliga. Não alcança imagem embutida: ali a
    declaração do PDF continua ganhando, como desde a S-12. Ver `MIN_CHECKER_CONTRAST`.
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
    #
    # Uniao de ladrilhos nao entra no gabarito (S-81), pela mesma razao que ela nao suprime
    # contorno em `_contour_wins_over_merged`: ela e inferencia nossa e nao declaracao do PDF.
    # Medido no `GALLAGHER`: uma uniao de 91 px definia o gabarito da pagina e o prior recusava
    # por tamanho o diagrama de 120 px que o contorno tinha achado -- sem sobreposicao nenhuma
    # entre os dois, entao a guarda de IoU nem chegava a opinar.
    expected_side: float | None = None
    if embedded and size_prior_tolerance is not None:
        sides = [
            float(max(box[2], box[3]))
            for box, candidate in zip(embedded_boxes, embedded, strict=True)
            if not candidate.merged_tiles
        ]
        expected_side = _typical_side(sides, size_prior_tolerance)

    # O contorno na pagina inteira e a unica fonte quando nao ha imagem embutida -- o caso da
    # maioria do acervo: 12 dos 27 PDFs sao scan de pagina inteira e 2 sao vetoriais.
    for board_rgb, quad in detect_boards(page_rgb, max_boards=max_boards, reading_order=reading_order):
        # Antes de tudo (S-143). O achado que nao tem contraste de casa nenhum nao e tabuleiro,
        # e a ordem importa: se ele entrasse na disputa, um retrato podia derrubar uma uniao de
        # ladrilhos em `_contour_wins_over_merged` ou envenenar o gabarito de tamanho. Guarda
        # que julga o que a coisa **e** vem antes de guarda que julga com quem ela compete.
        if checker_contrast_floor is not None:
            contraste = board_checker_contrast(board_rgb)
            if contraste <= checker_contrast_floor:
                # `info` pelo mesmo motivo da recusa por tamanho (S-79): esta linha apaga um
                # candidato, e e a unica evidencia de que ela agiu.
                logger.info(
                    "Contorno descartado por nao ter contraste de casa: %.4f. Foto, retrato "
                    "ou moldura -- ou tabuleiro cortado, que o warp desalinha.",
                    contraste,
                )
                continue

        if quad is None:
            box = (0, 0, page_rgb.shape[1], page_rgb.shape[0])
        else:
            xs, ys = quad[:, 0], quad[:, 1]
            box = (int(xs.min()), int(ys.min()), max(1, int(xs.max() - xs.min())), max(1, int(ys.max() - ys.min())))

        conflito = next(
            (
                indice
                for indice, outra in enumerate(embedded_boxes)
                if _same_region(box, outra, merged=bool(embedded[indice].merged_tiles))
            ),
            None,
        )
        if conflito is not None:
            if not _contour_wins_over_merged(embedded[conflito], board_rgb):
                continue
            # O contorno ganhou de uma uniao de ladrilhos: ele passa a ser o candidato daquela
            # regiao, e a uniao sai. Sem remover a caixa, o proximo achado de contorno da mesma
            # regiao seria suprimido por um candidato que ja nao esta na lista.
            candidates.remove(embedded[conflito])
            embedded_boxes[conflito] = (0, 0, 1, 1)

        if expected_side is not None and size_prior_tolerance is not None:
            side = max(box[2], box[3])
            if abs(side - expected_side) > expected_side * size_prior_tolerance:
                # `info` e nao `debug` (S-79): esta linha apaga um diagrama em potencial, e a
                # unica evidencia de que ela agiu. Quando o gabarito estava envenenado, o
                # sintoma era um diagrama que simplesmente nao aparecia na tela -- sem log,
                # sem numero, sem nada a que voltar.
                logger.info(
                    "Contorno descartado por tamanho: %d px contra gabarito de %.0f px da pagina (tolerancia %.0f%%).",
                    side,
                    expected_side,
                    size_prior_tolerance * 100,
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
    pdf_source: PdfSource,
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

    Abre o documento, ou o **empresta** quando `pdf_source` já é um `OpenPdf` (S-61): era
    aqui que morria uma das três aberturas por página. A assinatura continua aceitando caminho,
    que é a porta dos CLIs.
    """
    from ..pdf_io import open_document

    with open_document(pdf_source) as doc:
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
