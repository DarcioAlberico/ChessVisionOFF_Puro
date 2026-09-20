from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

from .config import (
    BOARD_SIZE,
    CELL_SIZE,
    DEFAULT_MAX_BOARDS,
    DEFAULT_READING_ORDER,
    DEFAULT_RECALL,
    ReadingOrder,
    RecallOptions,
    recall_em_vigor,
)

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

ASPECT_MAX = 1.62
"""Alongamento máximo -- lado maior sobre lado menor -- aceito num candidato. **Sem medição
registrada** -- ver `MIN_AREA_FRACTION`.

Largo de propósito: o contorno de um diagrama impresso raramente fecha quadrado, e um
tabuleiro com legenda embutida no recorte estica no eixo vertical.

**Era um par -- `ASPECT_MIN, ASPECT_MAX = 0.62, 1.62` -- e o par media a caixa alinhada aos
eixos (S-160).** Naquela régua "largo demais" e "alto demais" são dois casos, porque a caixa
tem orientação de página. Medindo o quad, que carrega a inclinação dele, os dois viram um só:
alongamento, sempre ≥ 1. `ASPECT_MIN` saiu junto com a medição que o justificava, e com ele
some uma assimetria que nunca teve significado nenhum -- 0,62 contra 1/1,62 = 0,6173. Por que
a caixa era a régua errada está em `_contour_geometry_score`.
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
"""Acima disto, dois candidatos das três passadas de limiar são o mesmo, e o pior sai."""

MIN_RELATIVE_AREA = 0.02
"""Fração da área do **maior** candidato abaixo da qual os outros são ruído da mesma página."""

MIN_SCORE_FLOOR = 0.06
"""Piso absoluto de score. Abaixo disto o candidato não entra, mesmo sendo o melhor da página."""

MIN_SCORE_RELATIVE = 0.25
"""Fração do score do melhor candidato abaixo da qual os outros saem. Vale o maior dos dois."""


SQUARE_KERNEL = np.ones((3, 3), np.uint8)
"""Elemento reto do fechamento. Está aqui desde o commit inicial, e continua intocado."""

DIAGONAL_KERNELS = (np.eye(3, dtype=np.uint8), np.fliplr(np.eye(3, dtype=np.uint8)).copy())
"""Os dois elementos diagonais do reparo de contato de quina (S-175).

**O defeito.** As casas escuras de um diagrama impresso são de uma paridade só, e duas casas
da mesma paridade **encostam apenas pela quina**. É por esses 49 pontos, e só por eles, que a
tinta do tabuleiro forma uma única componente 8-conexa para o `findContours` -- que é o que
este módulo assume ao tomar a extensão do contorno pela extensão do tabuleiro.

Se um contato de quina não sobrevive à rasterização, a corrente parte e o contorno fecha um
pedaço do tabuleiro. E não parte um contato de cada vez: os 7 contatos de uma mesma linha da
grade caem no **mesmo x**, então dividem a mesma fase sub-pixel e morrem juntos. O que sai é
um quad com uma fileira a menos -- 7/8 exatos do tabuleiro.

**Medido**, `Reinfeld_1001_Sacrificios_y_Combinaciones_Brillantes_1977.pdf`, página 141
(0-based) a 220 DPI: a coluna esquerda fechava em 101×116 pt e a direita em 116×116. Em
pixels o contorno da esquerda ia de x=99 a x=410, e a borda direita do tabuleiro está em
x=454: 311 px de 355, que é 7 casas de 8.

**E desde a S-160 a página não entregava nem o recorte torto: entregava três diagramas a
menos.** Um tabuleiro cortado em 7/8 e esticado pelo warp perde o reticulado 8×8, então o
contraste de casa dele é **exatamente 0,0000** -- e o piso da S-143, que a S-160 mudou para
antes da disputa, o mata. Medido na mesma página: os três da esquerda saem como
`sem-contraste-de-casa` com score 0,2798 a 0,2971, e `recognize_page` devolve **3** dos 6
diagramas. A guarda estava certa (aquele recorte não é tabuleiro) e escondia o defeito, que é
o que a própria S-143 registrou como pendência.

**Não é uma propriedade daquela coluna, nem daquele livro: é da fase.** Renderizada a 240 DPI
ou acima, a mesma página entrega 116×116 na esquerda sem reparo nenhum; a 150, 180 e 220 ela
não entrega nada. Nada no PDF muda entre essas corridas -- o que muda é onde a grade cai em
relação à malha de pixels, e por isso o mesmo defeito espera em qualquer livro cujo diagrama
caia na fase errada.

**Por que o fechamento reto não repara.** `MORPH_CLOSE` é dilatação seguida de erosão. A
dilatação com o elemento quadrado atravessa a quina, mas o pescoço que ela cria tem a largura
de um pixel e a erosão com o **mesmo** elemento o corta de volta. Fechar ao longo da diagonal
sobrevive porque a erosão corre na direção da ponte, e não contra ela.
"""

MIN_CHECKER_CONTRAST = 0.0
"""Piso do contraste entre casas para um achado de contorno ser diagrama (S-143).

**O relato.** Capa e prancha de retrato do `Karpov 1` (páginas 1 e 7) rendiam 10 caixas onde
não há diagrama nenhum: o título, a grade de fotos dos campeões, cada retrato, e -- na página
do Steinitz -- três casas do tabuleiro *pintado ao fundo do quadro* mais a moldura inteira.

**Por que o contraste de xadrez, e não a textura.** `_board_pattern_score` é
`0,6·xadrez + 0,4·grade`, e a parcela de **grade** é o que uma foto imita bem: moldura de
quadro, faixa de retratos e fachada produzem borda periódica. Medido nas páginas do relato, a
grade das fotos dá 0,04 a 0,80 -- acima de diagramas legítimos. A parcela de **xadrez** não tem
como ser imitada: ela exige que as 32 casas de uma paridade sejam sistematicamente mais claras
que as 32 da outra, num reticulado 8×8 alinhado com o recorte. Onde não há tabuleiro a diferença
entre as duas metades é ruído, o `clip` em 0 morde, e o resultado é **exatamente zero**.

**Zero, e por quê.** O número não é ajustado à amostra: é onde a comparação sinal-contra-ruído
troca de sinal (`contraste·2,4 ≤ dispersão·0,9`). O candidato legítimo mais próximo do corte no
acervo é um `Polgar` de 0,0616 -- posição de abertura, 28 peças, o caso que derruba esta
parcela --, então qualquer valor em (0; 0,06) se comportaria igual aqui. Zero é o que tem
significado independente do acervo, e é preferível por isso.

**Só contorno.** Imagem embutida é *declaração* do PDF e continua ganhando (S-12); ela tem as
guardas dela, e este piso mora no caminho de contorno justamente por isso.

**Ele morava no laço de `detection/hybrid.detect_diagrams`, e ali era tarde demais (S-160).**
O comentário daquele laço enunciava a regra certa -- *"guarda que julga o que a coisa é vem
antes de guarda que julga com quem ela compete"* --, mas o laço percorre o que `detect_boards`
**já devolveu**, e `detect_boards` ordena por score e suprime por IoU antes de devolver. Na
página 62 do `Vishy_Anand_Great_Chess_Combinations` a sequência era esta:

1. uma faixa de hachura vencia por score (0,6423 contra 0,6012);
2. o tabuleiro de verdade sobrepunha a faixa (IoU 0,49, acima de `iou_threshold`) e saía
   como `sobreposicao`;
3. só então a faixa vencedora morria aqui, por contraste zero.

A guarda removia o vencedor **depois** de o vencedor já ter comido o tabuleiro, e a página
voltava sem diagrama nenhum -- na interface, uma página em branco; no `cvoff-infer`, que chama
`detect_board` direto e nunca teve esta guarda, o losango e a FEN de vinte reis. Ela agora roda
em `_extract_candidate_quads`, antes de qualquer disputa, que é onde a própria frase mandava.
"""


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
    "sem-contraste-de-casa",
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
    """Os quatro cantos em `TL, TR, BR, BL`, **sem repetir nenhum** (S-363).

    A regra antiga era a das somas e diferenças: canto de menor soma é o superior-esquerdo, de
    maior soma o inferior-direito, e as diagonais saem da diferença `y - x`. Ela funciona para
    quadrilátero de pé e **quebra no quad a 45°** -- que é justamente o candidato torto que a
    geometria mais precisa julgar. Num losango de vértices `(100,0) (200,100) (100,200) (0,100)`
    o mesmo ponto ganhava `argmin(soma)` e `argmin(diferença)`: a saída tinha três cantos e um
    repetido, e `getPerspectiveTransform` sobre isso é uma matriz sem sentido.

    O ângulo em torno do centro não empata: quatro pontos distintos de um quadrilátero convexo
    têm quatro ângulos distintos, e ordená-los por ele dá a volta na figura. Com `y` crescendo
    para baixo -- a convenção da imagem --, o sentido do ângulo crescente é o horário, que é a
    ordem que `warp_from_quad` espera. O `roll` só escolhe **por onde começar**: o canto de menor
    soma, que é o mesmo critério de superior-esquerdo de antes.
    """
    pts = np.array(points, dtype=np.float32).reshape(4, 2)
    centro = pts.mean(axis=0)
    angulos = np.arctan2(pts[:, 1] - centro[1], pts[:, 0] - centro[0])
    horario = pts[np.argsort(angulos, kind="stable")]
    inicio = int(np.argmin(horario.sum(axis=1)))
    return np.roll(horario, -inicio, axis=0).astype(np.float32)


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


INNER_GRID_MAX_INSET = 0.12
"""Até onde, em fração do lado, a borda do tabuleiro pode estar para dentro do recorte."""

INNER_GRID_MIN_GAIN = 1.15
"""Quanto a grade ajustada tem de responder acima da uniforme para o eixo ser candidato a
aperto. É só o primeiro filtro (barato); quem decide é `INNER_GRID_MIN_CHECKER_GAIN`."""

INNER_GRID_MIN_CHECKER_GAIN = (0.10, 1.3)
"""O aperto só entra se o contraste de xadrez (`_checker_score`) subir **pelo menos 0,10 e
pelo menos 30 %** com ele.

A energia de borda sozinha aceitava apertos de 2–13 px em recortes que já estavam certos e
derrubava o conjunto de campo de 103 para 97 exatos (Gallagher p60/80/95/140, Flores Rios
p50/p200). O contraste de xadrez é a régua certa para "a grade 8×8 está sobre as casas": nos
recortes de moldura dupla ele dobra (Koblenz 0,31–0,39 → 0,58–0,67; Niemeijer 0,20 → 0,31),
e num recorte já justo um aperto de 2 px o move em 0,00–0,07 -- abaixo dos dois pisos. O
Burgess p60 é o caso que o piso pega do outro lado: a borda respondia mais, e o contraste caía
de 0,61 para 0,39."""


def _edge_profile(gray: np.ndarray, axis: int) -> np.ndarray:
    """Energia de borda por coluna (`axis=1`) ou por linha (`axis=0`), suavizada em 5 px."""
    perfil = np.abs(np.diff(gray, axis=axis)).sum(axis=1 - axis)
    kernel = np.ones(5, dtype=np.float32) / 5.0
    return np.convolve(perfil, kernel, mode="same")


def _fit_grid_1d(profile: np.ndarray, *, max_inset: float, cells: int = 8) -> tuple[int, int, float, float]:
    """Onde começa e termina a grade de `cells` casas neste eixo, e as duas respostas.

    Devolve `(inicio, fim, resposta_ajustada, resposta_uniforme)`: o par que maximiza a soma da
    energia de borda nas nove linhas da grade, procurado com o início em `[0, max_inset]` e o
    fim em `[1 - max_inset, 1]` do comprimento. A resposta uniforme é a do par `(0, fim)`.
    """
    comprimento = len(profile) + 1
    inset = max(1, int(comprimento * max_inset))
    inicios = np.arange(0, inset)
    fins = np.arange(comprimento - inset, comprimento)
    ks = np.arange(cells + 1, dtype=np.float32)
    # posições [n_inicios, n_fins, 9]
    posicoes = inicios[:, None, None] + (fins[None, :, None] - inicios[:, None, None]) * ks / cells
    indices = np.clip(np.rint(posicoes).astype(int), 0, len(profile) - 1)
    respostas = profile[indices].sum(axis=2)
    melhor = np.unravel_index(int(np.argmax(respostas)), respostas.shape)
    uniforme = float(respostas[0, -1])
    return int(inicios[melhor[0]]), int(fins[melhor[1]]), float(respostas[melhor]), uniforme


def fit_inner_board(board_rgb: np.ndarray) -> tuple[int, int, int, int] | None:
    """O retângulo do tabuleiro de verdade dentro de um recorte que pegou moldura, ou `None`.

    O contorno de página acha o **quadro** do diagrama; nos livros de moldura dupla esse quadro
    tem um filete de 1–2 % de cada lado, e a grade uniforme 8×8 sobre o recorte inteiro cai fora
    das casas. Aqui a grade é reajustada eixo a eixo pela energia de borda: onde as nove linhas
    respondem mais. Só é aceito o eixo em que a grade ajustada responde `INNER_GRID_MIN_GAIN`
    vezes mais que a uniforme -- num recorte já justo a uniforme é a melhor e nada muda.
    Devolve `(x0, y0, x1, y1)` em pixels do recorte.
    """
    if board_rgb is None or board_rgb.size == 0:
        return None
    gray = cv2.cvtColor(board_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    altura, largura = gray.shape
    x0, x1, ganho_x, uniforme_x = _fit_grid_1d(_edge_profile(gray, axis=1), max_inset=INNER_GRID_MAX_INSET)
    y0, y1, ganho_y, uniforme_y = _fit_grid_1d(_edge_profile(gray, axis=0), max_inset=INNER_GRID_MAX_INSET)
    if not (uniforme_x > 0 and ganho_x >= INNER_GRID_MIN_GAIN * uniforme_x):
        x0, x1 = 0, largura
    if not (uniforme_y > 0 and ganho_y >= INNER_GRID_MIN_GAIN * uniforme_y):
        y0, y1 = 0, altura
    if (x0, y0, x1, y1) == (0, 0, largura, altura):
        return None
    return x0, y0, x1, y1


def tighten_board(board_rgb: np.ndarray) -> np.ndarray:
    """O recorte apertado ao tabuleiro de verdade (`fit_inner_board`), no mesmo tamanho.

    Quando não há moldura a tirar, devolve o próprio recorte -- é o caso de todo livro que já
    saía certo, e é por isso que esta função pode ficar no caminho de todos.
    """
    caixa = fit_inner_board(board_rgb)
    if caixa is None:
        return board_rgb
    x0, y0, x1, y1 = caixa
    altura, largura = board_rgb.shape[:2]
    interior = board_rgb[y0:y1, x0:x1]
    if interior.size == 0:
        return board_rgb
    apertado = cv2.resize(interior, (largura, altura), interpolation=cv2.INTER_LINEAR)
    antes, depois = board_checker_score(board_rgb), board_checker_score(apertado)
    minimo_absoluto, minimo_relativo = INNER_GRID_MIN_CHECKER_GAIN
    if depois < antes + minimo_absoluto or depois < antes * minimo_relativo:
        return board_rgb
    logger.debug(
        "Recorte apertado ao tabuleiro: caixa %s, contraste de xadrez %.3f -> %.3f.", caixa, antes, depois
    )
    return apertado


def _quad_elongation(quad: np.ndarray) -> float:
    """Lado maior sobre lado menor do quad, na inclinação dele. Nunca menor que 1.

    `cv2.minAreaRect` e não `cv2.boundingRect`: a caixa alinhada aos eixos mede a **pegada na
    página**, e não a forma do candidato. As duas só coincidem quando o candidato está de pé, e
    é justamente o candidato torto que precisa ser julgado -- ver `_contour_geometry_score`.
    """
    (_, (largura, altura), _) = cv2.minAreaRect(quad.astype(np.float32))
    if largura <= 0.0 or altura <= 0.0:
        return math.inf
    return float(max(largura, altura) / min(largura, altura))


def _contour_geometry_score(quad: np.ndarray, image_area: float) -> float:
    """Quanto o candidato parece diagrama pela geometria: grande, e quadrado.

    **A régua era a caixa alinhada aos eixos, e ela premiava exatamente o que devia recusar
    (S-160).** Um quadrilátero inclinado a 45° fecha caixa quadrada seja qual for o formato
    dele. Na página 62 do `Vishy_Anand_Great_Chess_Combinations` -- as casas escuras são
    hachura a 45°, e o limiar adaptativo emenda as diagonais vizinhas numa faixa só -- os
    números eram estes:

    | candidato | lados do quad | alongamento | caixa | razão da caixa | squareness | score |
    |---|---|---|---|---|---|---|
    | faixa de hachura | 620×314 | **1,98** | 662×659 | 1,0046 | 0,978 | **0,6423** |
    | tabuleiro | 466×453 | 1,03 | 469×455 | 1,0308 | 0,856 | 0,6012 |

    Alongamento 1,98 está muito além de `ASPECT_MAX` e devia ter sido recusado por aspecto; a
    inclinação o convertia em razão 1,0046, e a faixa saía **mais quadrada que o tabuleiro**.
    Ela vencia, o warp entregava um losango ao classificador, e a FEN vinha com vinte reis.

    Medido no acervo: 5 das 244 páginas daquele livro, e o mesmo padrão no `Schiller` e no
    `1937 Kemeri`, onde a imagem embutida ainda socorre. Livro cujas casas escuras são chapadas
    não produz a faixa e não muda de resposta.
    """
    area = cv2.contourArea(quad.astype(np.float32))
    if area <= 0:
        return 0.0
    # Keep small diagrams but reject tiny noisy contours.
    if area < image_area * MIN_AREA_FRACTION:
        return 0.0

    alongamento = _quad_elongation(quad)
    if alongamento > ASPECT_MAX:
        return 0.0

    area_ratio = area / image_area
    # Saturates to avoid very large non-board boxes dominating by area only.
    area_component = min(area_ratio / AREA_SATURATION, 1.0)
    squareness = max(0.0, 1.0 - (math.log(alongamento) / math.log(ASPECT_MAX)))
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


def _texture_from_parts(checker: float, grid: float) -> float:
    """A textura a partir das duas parcelas já medidas.

    Existe separada de `_board_pattern_score` para que `_extract_candidate_quads` possa olhar
    a parcela de xadrez sozinha -- é o piso da S-143 -- sem medir o recorte duas vezes.
    """
    return float(np.clip(0.6 * checker + 0.4 * grid, 0.0, 1.0))


def _board_pattern_score(warped_rgb: np.ndarray) -> float:
    small = _small_gray(warped_rgb)
    return _texture_from_parts(_checker_score(small), _grid_score(small))


def board_checker_score(warped_rgb: np.ndarray) -> float:
    """Só a parcela de xadrez de `_board_pattern_score`, para quem precisa dela isolada."""
    return _checker_score(_small_gray(warped_rgb))


def _repaired_pass(thresh: np.ndarray) -> np.ndarray:
    """O terceiro passe de limiar: o fechamento nas duas diagonais, unidas (S-175).

    Existe para que o contato de quina entre casas da mesma paridade sobreviva à binarização,
    que é o que mantém o tabuleiro como uma componente só. O porquê, com os números, está em
    `DIAGONAL_KERNELS`.

    A caixa **não** cresce, e isso não é detalhe: dilatar repararia a quina do mesmo jeito e
    entregaria 117×117 onde o tabuleiro mede 116×116, deslocando toda caixa de contorno do
    acervo em ~1 pt. O fechamento devolve a forma ao tamanho original, então o diff do censo
    continua mostrando só o que de fato mudou.
    """
    reparado = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, DIAGONAL_KERNELS[0], iterations=1)
    for kernel in DIAGONAL_KERNELS[1:]:
        reparado = cv2.bitwise_or(reparado, cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1))
    return reparado


def _threshold_passes(thresh_base: np.ndarray) -> list[np.ndarray]:
    """As três binarizações de que os candidatos saem, cada uma contribuindo a **sua** lista.

    O cru, o fechamento reto (aqui desde o commit inicial, e intocado) e o reparo de quina da
    S-175.

    **Três imagens, e não uma.** A primeira versão da S-175 unia o fechamento reto e o reparo
    numa imagem só, para não pagar um `findContours` a mais. O raciocínio era que a união é um
    superconjunto do fechamento reto e portanto "só pode ligar mais" -- verdade sobre
    **conexidade** e falsa sobre **candidatos**: juntar duas componentes tira as duas da lista
    de contornos e põe a fundida no lugar. Onde o contorno **justo** era o bom, ele
    simplesmente deixava de existir.

    Medido no `Gaprindashvili`, cujos diagramas fecham dois contornos -- um justo de 112 pt (a
    borda da grade) e um largo de 116 pt (a moldura impressa em volta). A moldura não é a borda
    do tabuleiro, e incluí-la tira a grade 8×8 de registro. Nas 13 páginas que o censo amostra
    daquele livro, os dois desenhos entregam os **mesmos 68 candidatos de contorno** -- e não é
    a contagem que muda, é qual dos dois contornos sobra:

    | desenho | acima do gate de 0,80 |
    |---|---|
    | três passes separados | **59** de 68 |
    | reto e reparo fundidos numa imagem | 56 de 68 |

    Os 3 são as páginas 35, 69 e 92: o candidato de 112 pt que lia 1,0000 / 0,9999 / 0,9998 é
    substituído pelo de 116 pt, que lê **0,2973 / 0,2897 / 0,0608**. Em passes separados o justo
    continua na lista, continua ganhando no score, e os três ficam acima do gate.

    **O preço**, medido nesta função sobre 8 páginas já renderizadas: 61,6 → 95,0 ms por
    página, **+54%**. Está em avaliar mais candidato, não em binarizar mais uma vez.
    """
    return [
        thresh_base,
        cv2.morphologyEx(thresh_base, cv2.MORPH_CLOSE, SQUARE_KERNEL, iterations=1),
        _repaired_pass(thresh_base),
    ]


def _contour_candidates(
    image_rgb: np.ndarray,
    rejected: list[RejectedQuad] | None = None,
    checker_floor: float | None = MIN_CHECKER_CONTRAST,
) -> list[tuple[np.ndarray, float, tuple[int, int, int, int]]]:
    """A busca de contorno numa escala só: o detector cru, sem recuperação nenhuma.

    Era o corpo de `_extract_candidate_quads` até o passo A1 do OCR_UI ciclo 2; ela ficou com
    o nome e ganhou as recuperações de `RecallOptions` **em volta** deste passe, que não mudou
    em nada -- inclusive a lista `rejected`, que sai com os mesmos motivos.
    """
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
    threshold_passes = _threshold_passes(thresh_base)

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

            small = _small_gray(warp_from_quad(image_rgb, quad, target_size=320))
            checker = _checker_score(small)
            # Antes de qualquer disputa (S-143, reposicionada na S-160). O achado sem contraste
            # de casa nenhum não é tabuleiro -- é foto, retrato, moldura ou faixa de hachura --,
            # e deixá-lo entrar na competição não o fazia vencer sozinho: fazia com que, ao
            # vencer por score, ele suprimisse por IoU o diagrama de verdade e morresse depois,
            # levando o diagrama junto. Ver `MIN_CHECKER_CONTRAST`.
            if checker_floor is not None and checker <= checker_floor:
                if rejected is not None:
                    rejected.append(RejectedQuad(bbox, round(geom_score, 4), round(checker, 4), "sem-contraste-de-casa"))
                continue

            pattern_score = _texture_from_parts(checker, _grid_score(small))
            score = geom_score * (0.55 + 0.45 * pattern_score)
            quad_area = float(cv2.contourArea(quad.astype(np.float32)))
            raw_candidates.append((quad, float(score), bbox, quad_area))

    if not raw_candidates:
        return []

    raw_candidates.sort(key=lambda item: item[1], reverse=True)
    deduped: list[tuple[np.ndarray, float, tuple[int, int, int, int], float]] = []
    for candidate in raw_candidates:
        _, _, bbox, _ = candidate
        # A duplicata das três passadas de limiar **não** vai para as recusas: ela é o mesmo
        # candidato visto mais de uma vez, e registrá-la faria o relatório contar cada achado
        # como um achado mais uma perda.
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


SQUARE_MIN_ELONGATION = 1.02
"""Alongamento a partir do qual vale tentar o resgate de quadrado (`RecallOptions.rescue_squares`).

Abaixo disto o maior quadrado que cabe no achado **é** o próprio achado, e o resgate devolveria
o mesmo recorte que a guarda acabou de recusar -- custo sem chance de ganho. Os dois casos
medidos do `Reinfeld` estão em 1,087 e 1,090: nove por cento de legenda a mais no eixo vertical.
"""

_Scored = tuple[np.ndarray, float, tuple[int, int, int, int], float]


def _score_quad(image_rgb: np.ndarray, quad: np.ndarray, image_area: float) -> tuple[float, float] | None:
    """``(score, contraste)`` de um quad pelas guardas e pela conta de `_contour_candidates`.

    ``None`` quando uma guarda -- geometria, aspecto, fora-da-página -- já diz que este quad não
    é candidato. A conta é a **mesma** de `_contour_candidates` (``geometria × (0,55 + 0,45 ×
    textura)``): um quad resgatado ou vindo da escala reduzida compete com os da escala cheia,
    e tem de ser medido pela mesma régua, senão a lista somada é ordenada por duas.
    """
    geom = _contour_geometry_score(quad, image_area)
    if geom <= 0:
        return None
    bbox = _bbox_from_quad(quad)
    if (
        _bbox_visible_ratio(bbox, image_rgb.shape) < MIN_VISIBLE_RATIO
        or _quad_point_inside_ratio(quad, image_rgb.shape) < MIN_QUAD_INSIDE_RATIO
    ):
        return None
    small = _small_gray(warp_from_quad(image_rgb, quad, target_size=320))
    checker = _checker_score(small)
    pattern = _texture_from_parts(checker, _grid_score(small))
    return float(geom * (0.55 + 0.45 * pattern)), float(checker)


def square_anchors(bbox: tuple[int, int, int, int]) -> list[np.ndarray]:
    """O maior quadrado que cabe na caixa, em três posições: início, fim e meio.

    Três e não cinco: o quadrado só desliza no eixo **longo** da caixa, então os quatro cantos
    são dois a dois o mesmo recorte. Numa caixa 356×387 os três são "encostado no topo",
    "encostado na base" e "centrado" -- e é o primeiro que acerta o `Reinfeld`, porque a legenda
    está embaixo do tabuleiro.

    `bbox` é ``(x, y, largura, altura)`` em pixels da página; saem três quads de 4 pontos em
    ``float32``, na convenção de `warp_from_quad`.
    """
    x, y, width, height = bbox
    side = float(min(width, height))
    slack_x = float(width) - side
    slack_y = float(height) - side
    quads: list[np.ndarray] = []
    for ox, oy in ((0.0, 0.0), (slack_x, slack_y), (slack_x / 2.0, slack_y / 2.0)):
        ax, ay = float(x) + ox, float(y) + oy
        quads.append(
            np.array(
                [[ax, ay], [ax + side, ay], [ax + side, ay + side], [ax, ay + side]],
                dtype=np.float32,
            )
        )
    return quads


def _pool_finish(pooled: list[_Scored]) -> list[tuple[np.ndarray, float, tuple[int, int, int, int]]]:
    """A deduplicação e o corte de área relativa, sobre a lista somada das fontes.

    São as duas únicas etapas de `_contour_candidates` que olham a lista inteira e não um
    candidato por vez, e por isso as duas que precisam rodar **depois** de as fontes extras
    entrarem. Os limiares são os mesmos (`DEDUPE_IOU`, `MIN_RELATIVE_AREA`); nada aqui é
    número novo.
    """
    if not pooled:
        return []
    pooled.sort(key=lambda item: item[1], reverse=True)
    kept: list[_Scored] = []
    for candidate in pooled:
        if any(_bbox_iou(candidate[2], other[2]) > DEDUPE_IOU for other in kept):
            continue
        kept.append(candidate)
    largest = max(item[3] for item in kept)
    floor = largest * MIN_RELATIVE_AREA
    out = [item[:3] for item in kept if item[3] >= floor]
    out.sort(key=lambda item: item[1], reverse=True)
    return out


def _extract_candidate_quads(
    image_rgb: np.ndarray,
    rejected: list[RejectedQuad] | None = None,
    checker_floor: float | None = MIN_CHECKER_CONTRAST,
    recall: RecallOptions | None = DEFAULT_RECALL,
) -> list[tuple[np.ndarray, float, tuple[int, int, int, int]]]:
    """Os candidatos de contorno da página: o passe cru mais as recuperações de `recall`.

    O caminho de escala 1,0 é `_contour_candidates`, chamado sem alteração nenhuma --
    inclusive a lista `rejected`, que continua saindo com os mesmos motivos. Com `recall`
    (padrão `DEFAULT_RECALL`; `None` é o detector cru) a lista devolvida passa a incluir:

    * os achados do mesmo passe rodando sobre a página reduzida a cada escala de
      `recall.scales`, com o quad multiplicado de volta e **repontuado na resolução cheia**
      (senão dois candidatos da mesma página teriam sido medidos em imagens diferentes e o
      score não os ordenaria). `INTER_AREA` a meia escala faz a média da hachura: uma casa
      escura desenhada com traços vira cinza chapado e o limiar adaptativo passa a ver casa
      sólida em vez de cerca -- o único jeito de o `Niemeijer` fechar contorno. **Somando, e
      não substituindo**: buscar só a meia escala perde seis diagramas do `Reinfeld`, cujo
      tabuleiro de 116 pt não sobrevive à redução;
    * o resgate de quadrado (`square_anchors`) sobre cada recusa por `sem-contraste-de-casa`
      alongada além de `SQUARE_MIN_ELONGATION`: quando o contorno emenda o diagrama com a
      legenda, as 64 casas saem fora de registro, o contraste dá exatamente zero e a guarda
      mata o candidato. A guarda está certa sobre o recorte que viu; ela viu o recorte errado.
      O resgate oferece o maior quadrado que cabe no achado e deixa a **mesma** guarda julgar
      (medido no `Reinfeld`: o contraste sobe de 0,0000 para 0,2317 e 0,3209).

    Um achado da escala reduzida que já duplica um da escala cheia (IoU acima de `DEDUPE_IOU`)
    é descartado **antes** de ser repontuado: a deduplicação ficaria com o da escala cheia de
    qualquer jeito e o warp de 320×320 é a parte cara.
    """
    recall = recall_em_vigor(recall)
    if recall is None:
        return _contour_candidates(image_rgb, rejected, checker_floor)

    image_area = float(image_rgb.shape[0] * image_rgb.shape[1])
    local: list[RejectedQuad] = []
    pooled: list[_Scored] = [
        (quad, score, bbox, float(cv2.contourArea(quad)))
        for quad, score, bbox in _contour_candidates(image_rgb, local, checker_floor)
    ]
    if rejected is not None:
        rejected.extend(local)

    height, width = image_rgb.shape[:2]
    for scale in recall.scales:
        if scale <= 0.0 or scale >= 1.0:
            raise ValueError(f"escala de busca deve estar em (0, 1); recebida {scale!r}")
        smaller = cv2.resize(
            image_rgb,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        for quad, _, _ in _contour_candidates(smaller, None, checker_floor):
            back = np.asarray(quad, dtype=np.float32) / scale
            bbox = _bbox_from_quad(back)
            if any(_bbox_iou(bbox, other[2]) > DEDUPE_IOU for other in pooled):
                continue
            measured = _score_quad(image_rgb, back, image_area)
            if measured is None:
                continue
            score, checker = measured
            if checker_floor is not None and checker <= checker_floor:
                continue
            pooled.append((back, score, bbox, float(cv2.contourArea(back))))

    if recall.rescue_squares:
        for item in local:
            if item.reason != "sem-contraste-de-casa":
                continue
            _, _, box_w, box_h = item.bbox
            shorter = min(box_w, box_h)
            if shorter <= 0 or max(box_w, box_h) / shorter < SQUARE_MIN_ELONGATION:
                continue
            for quad in square_anchors(item.bbox):
                measured = _score_quad(image_rgb, quad, image_area)
                if measured is None:
                    continue
                score, checker = measured
                if checker_floor is not None and checker <= checker_floor:
                    continue
                pooled.append((quad, score, _bbox_from_quad(quad), float(cv2.contourArea(quad))))

    return _pool_finish(pooled)


def detect_boards(
    image_rgb: np.ndarray,
    target_size: int = BOARD_SIZE,
    max_boards: int = DEFAULT_MAX_BOARDS,
    iou_threshold: float = 0.25,
    reading_order: ReadingOrder = DEFAULT_READING_ORDER,
    warn_on_cap: bool = True,
    rejected: list[RejectedQuad] | None = None,
    checker_floor: float | None = MIN_CHECKER_CONTRAST,
    recall: RecallOptions | None = DEFAULT_RECALL,
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

    `checker_floor` é o piso de contraste de casa da S-143, e ele vale aqui e não mais no
    `hybrid` porque precisa correr **antes** da disputa por score e IoU desta função -- ver
    `MIN_CHECKER_CONTRAST`. `None` desliga, e quem desliga assume achar diagrama onde não há.

    `recall` são as recuperações de recall do OCR_UI ciclo 2 (passo A1) -- multiescala somando
    e resgate de quadrado --, ligadas por padrão (`config.DEFAULT_RECALL`); `None` é o
    detector cru, que só serve para medir o que elas valem. Parâmetro explícito, e não
    atributo de módulo: a janela e a importação da suíte detectam no mesmo processo, e o
    *monkeypatch* que a suíte fazia antes fazia a janela detectar ora com ora sem o pacote.
    """
    candidates = _extract_candidate_quads(image_rgb, rejected, checker_floor, recall)
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
        # O quad e o quadro do diagrama; o tabuleiro pode estar um filete para dentro dele
        # (moldura dupla). `tighten_board` so mexe quando a grade ajustada responde mais.
        boards.append((tighten_board(warp_from_quad(image_rgb, quad, target_size=target_size)), quad))
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
