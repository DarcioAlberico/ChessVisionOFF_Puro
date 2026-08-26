"""OCR da faixa de legenda, não da página (S-43).

**Por que não a página inteira.** Mesmo com um motor disponível, rodá-lo sobre a página é
errado por três razões, e as três já estão documentadas na S-16:

1. **Custo.** Uma página a 220 DPI é ~1.100×1.700, e o detector de texto é a parte cara. A
   S-61 mediu ~2,95 s por página só de pipeline; somar um OCR de página inteira a isso
   multiplica o custo de uma varredura que já leva ~10 h para o acervo.
2. **Falso positivo.** A armadilha nº 3 da S-16 -- *"prosa não é legenda"* -- piora com OCR,
   porque o reconhecimento erra e um erro vira padrão que casa.
3. **O tabuleiro vira texto.** O OCR lê as peças como caracteres, e o filtro
   `_is_diagram_font_row`, feito para o `Polgar` (cujo tabuleiro **é** texto), não foi
   desenhado para isso.

**A decisão de projeto deste módulo.** O OCR não é uma via alternativa: é **uma segunda
fonte de `TextLine`**, no mesmo formato que `pdf_text.page_text_lines` devolve e nas mesmas
coordenadas (pontos do PDF). Assim todo o aparato da S-16 continua valendo sem uma linha de
mudança -- agrupamento por coluna, `dominant_placement`, `assign_lines_to_diagrams`, os
tiers de legenda e vizinhança, o filtro de prosa, a checagem de contradição.

**O tabuleiro é apagado antes de o motor ver a imagem.** A faixa lida é o retângulo do
diagrama dilatado por `radius_pt`, e o interior do diagrama é pintado de branco no recorte
renderizado. Um render e um OCR por diagrama, e o problema 3 acima deixa de existir por
construção em vez de por filtro -- que era como a S-16 teria de tratá-lo.

::

        ┌─────────────────────────┐  ← faixa superior (radius_pt acima do bbox)
        │   72. Steinitz - Bird   │
        │      ┌───────────┐      │
        │  76  │  APAGADO  │      │  ← faixa lateral (o marcador W/B da S-44)
        │  B   │           │      │
        │      └───────────┘      │
        │      Bremen 1998        │  ← faixa inferior
        └─────────────────────────┘

**O DPI é maior que o da detecção, de propósito.** O pipeline renderiza a 220 DPI porque é
o que o classificador de casas precisa; texto de legenda em corpo 8 a 220 DPI dá ~11 px de
altura de x, que é onde os motores começam a errar. 300 DPI custa ~1,9× em pixels de uma
faixa que já é uma fração da página, e é a diferença entre ler e adivinhar.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import fitz
import numpy as np

from .ocr import TextBox, TextRecognizer, build_recognizer
from .pdf_text import DEFAULT_RADIUS_PT, TextLine
from .procedencias import DE_TERCEIROS, LineOrigin, procedencia_do_motor
from .settings import OcrSettings

logger = logging.getLogger(__name__)

DEFAULT_OCR_DPI = 300.0
"""Ver o parágrafo sobre DPI no topo do módulo. Renderiza só a faixa, não a página."""

SCOPE_BAND = 0.12
"""Fração do topo e do rodapé lida em busca de declaração de escopo de página.

**Maior que o `MARGIN_BAND` de 0,07, e a diferença foi medida, não escolhida.** As duas
frações respondem a perguntas diferentes: `MARGIN_BAND` decide o que *descartar* como
cabeçalho corrente, e uma faixa apertada erra para o lado seguro ali -- no máximo se perde um
cabeçalho. Aqui a faixa é o que o motor vê, e uma faixa apertada **corta a linha ao meio**: o
motor recebe a metade superior dos glifos e devolve algo com forma de texto.

Medido no `Reinfeld_1001` p40, que é o alvo declarado da S-43:

| faixa | altura | o que o RapidOCR leu |
|---|---|---|
| 0,07 | 34,6 pt | `TIEAANDDIVEDA` (0,71) |
| **0,10** | 49,4 pt | `LAS BLANCAS JUEGAN PRIMERO` (0,94) |
| **0,12** | 59,3 pt | `LAS BLANCAS JUEGAN PRIMERO` (0,93) |
| 0,15 | 74,2 pt | a declaração **mais** dois fragmentos do diagrama de cima |

O 0,71 de confiança do primeiro caso é o que torna isto instrutivo: o motor não avisou que
estava adivinhando, e nenhum limiar razoável o teria barrado. 0,10 já lê; 0,12 é ele com
folga, e 0,15 começa a puxar pedaço de tabuleiro para dentro da faixa."""

MIN_BAND_PT = 6.0
"""Faixa mais estreita que isto não cabe uma linha de texto, e renderizá-la é custo puro."""

_LINE_GAP_RATIO = 0.8
"""Vão vertical, em alturas de linha, a partir do qual duas linhas são blocos diferentes.

Equivalente ao que o `get_text("dict")` do PyMuPDF entrega de graça na camada de texto: lá
o bloco vem do próprio PDF, aqui ele precisa ser reconstruído da geometria. O valor é
conservador -- legenda de três linhas (`5` / `Morphy-De Riviere` / `Paris, 1858`) tem vão
menor que a altura de uma linha, e é ela que precisa continuar sendo um bloco só, porque a
S-16 mede que o número não anda sozinho.
"""


class CaptionReader:
    """Lê a vizinhança de um diagrama com o motor de OCR, e devolve `TextLine`.

    Sem estado entre chamadas de propósito: o motor é que é caro de construir, e ele vem
    pronto de `ocr.build_recognizer`. Assim um `CaptionReader` pode ser criado por
    varredura, por página ou por teste sem custo.
    """

    def __init__(
        self,
        recognizer: TextRecognizer,
        *,
        radius_pt: float = DEFAULT_RADIUS_PT,
        dpi: float = DEFAULT_OCR_DPI,
    ) -> None:
        self._recognizer = recognizer
        self._radius_pt = radius_pt
        self._dpi = dpi

    @property
    def name(self) -> str:
        return self._recognizer.name

    @property
    def procedencia(self) -> LineOrigin:
        """`glifo` quando quem lê é o classificador deste projeto, `ocr` para os de terceiros (S-207).

        **Sai do nome do motor, e não de um argumento de construção**, porque o nome é o que o
        motor declara sobre si e um argumento seria uma segunda fonte para a mesma pergunta -- que
        divergiria da primeira vez que alguém construísse o leitor sem passá-lo.

        Quem traduz nome em procedência é `procedencias.procedencia_do_motor`: este módulo passa o
        nome e recebe a resposta, **sem saber que motores existem** -- é a regra da S-181, e é o
        que permite um motor novo entrar sem uma linha de mudança aqui.
        """
        return procedencia_do_motor(self._recognizer.name)

    # ------------------------------------------------------------------ leitura por diagrama

    def lines_around(
        self,
        page: fitz.Page,
        bbox_pdf: tuple[float, float, float, float],
        vizinhos: Sequence[tuple[float, float, float, float]] = (),
    ) -> list[TextLine]:
        """Linhas na vizinhança do diagrama, em pontos do PDF.

        O interior de `bbox_pdf` é apagado antes da leitura -- ver o desenho no topo do
        módulo. Devolve lista vazia quando não há texto legível ali, que é o caso normal
        num livro de diagramas sem legenda.

        ## `vizinhos`, e o defeito que a S-207 mediu

        **Apagar só o diagrama alvo não basta numa página com mais de um.** O raio de busca é de
        60 pt, e numa folha de quatro problemas a faixa em volta de um deles contém pedaços dos
        outros três. As peças ficam, e a leitura de glifo mede a escala do texto por **massa de
        tinta**: uma peça impressa tem 86 px de altura contra 23 de uma letra, e a peneira de área
        passa a descartar todas as letras. É o mesmo defeito que `text/leitor.escala_fora_dos_diagramas`
        corrige na página inteira, e ele reaparece aqui porque a faixa também tem tabuleiro.

        Medido em 2026-08-26, página 17 do `1000 Chess Problems` (4 diagramas), com o glifo:

            apagando só o alvo        8 caixas, todas figurina e ruído -- nenhum texto
            apagando os quatro        3 caixas, e uma delas é a legenda: `MaT B 2 xoua 4+3`

        `vizinhos` é opcional e vazio por omissão: um chamador antigo continua funcionando
        exatamente como antes, e quem tem a lista de bboxes da página -- que é
        `pdf_text._lines_with_ocr`, e ele sempre a teve -- passa a ler o que estava ali.
        """
        x0, y0, x1, y1 = bbox_pdf
        faixa = fitz.Rect(
            x0 - self._radius_pt,
            y0 - self._radius_pt,
            x1 + self._radius_pt,
            y1 + self._radius_pt,
        ) & page.rect

        if faixa.is_empty or faixa.width < MIN_BAND_PT or faixa.height < MIN_BAND_PT:
            return []

        # O alvo primeiro, e os vizinhos que tocam a faixa depois. Apagar um retângulo que não
        # cruza o recorte é trabalho sem efeito, e `_blank_region` já o ignora -- filtrar aqui é
        # para o caso comum de uma página com muitos diagramas e uma faixa pequena.
        apagar = [fitz.Rect(*bbox_pdf)]
        apagar += [
            retangulo
            for outro in vizinhos
            if not (retangulo := fitz.Rect(*outro)).is_empty and retangulo.intersects(faixa)
        ]
        return self._read_band(page, faixa, blank=apagar)

    # -------------------------------------------------------------------- faixa de margem

    def margin_lines(self, page: fitz.Page) -> list[TextLine]:
        """Linhas do topo e do rodapé -- a faixa que `MARGIN_BAND` descarta (S-43).

        É onde mora o `LAS BLANCAS JUEGAN PRIMERO` do `Reinfeld`, e nos 7 livros sem camada
        de texto ele não tem nenhuma outra forma de ser lido. Quem decide o que fazer com
        isso é `pdf_text.page_scope_declaration`; aqui só se lê.

        A faixa é a de `SCOPE_BAND`, e **não** a de `MARGIN_BAND`: ler com 0,07 devolvia
        `TIEAANDDIVEDA` na página que este método existe para ler. Ver `SCOPE_BAND`.
        """
        altura = page.rect.height or 1.0
        banda = altura * SCOPE_BAND

        lines: list[TextLine] = []
        for faixa in (
            fitz.Rect(page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y0 + banda),
            fitz.Rect(page.rect.x0, page.rect.y1 - banda, page.rect.x1, page.rect.y1),
        ):
            recorte = faixa & page.rect
            if recorte.is_empty or recorte.height < MIN_BAND_PT:
                continue
            lines.extend(self._read_band(page, recorte, group_offset=len(lines)))
        return lines

    # ----------------------------------------------------------------------------- interno

    def _read_band(
        self,
        page: fitz.Page,
        band: fitz.Rect,
        *,
        blank: Sequence[fitz.Rect] = (),
        group_offset: int = 0,
    ) -> list[TextLine]:
        try:
            image_rgb, origin, zoom = _render_band(page, band, dpi=self._dpi)
        except (RuntimeError, ValueError) as exc:
            logger.warning("Nao foi possivel renderizar a faixa %s para OCR (%s).", band, exc)
            return []

        for retangulo in blank:
            _blank_region(image_rgb, retangulo, origin=origin, zoom=zoom)

        try:
            boxes = self._recognizer.read(image_rgb)
        except Exception as exc:  # noqa: BLE001 - motor de terceiro no meio de uma varredura
            logger.warning("Motor de OCR %r falhou nesta faixa (%s); a página segue sem ele.", self.name, exc)
            return []

        return _boxes_to_lines(
            boxes, origin=origin, zoom=zoom, group_offset=group_offset, procedencia=self.procedencia
        )


# --------------------------------------------------------------------------------------
# Render e conversao de coordenadas
# --------------------------------------------------------------------------------------


def _render_band(page: fitz.Page, band: fitz.Rect, *, dpi: float) -> tuple[np.ndarray, tuple[float, float], float]:
    """Renderiza um recorte da página. Devolve `(RGB, origem em pontos, zoom)`.

    A origem é o canto superior esquerdo do recorte **como o PyMuPDF o arredondou**, e não
    o `band.x0` pedido: `get_pixmap` alinha o clip a pixels inteiros, e usar o valor pedido
    deslocaria toda caixa lida por até um pixel. Um pixel a 300 DPI é 0,24 pt, o que não
    muda nenhuma associação -- mas a conversão certa é de graça e a errada precisaria ser
    lembrada depois.
    """
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=band, alpha=False)

    buffer = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    image: np.ndarray = buffer[:, :, :3].copy() if pix.n == 4 else buffer.copy()
    return image, (pix.x / zoom, pix.y / zoom), zoom


def _blank_region(image_rgb: np.ndarray, region: fitz.Rect, *, origin: tuple[float, float], zoom: float) -> None:
    """Pinta de branco a região do diagrama dentro do recorte já renderizado.

    Branco e não preto: o detector de texto dos três motores procura traço escuro sobre
    fundo claro, e um retângulo preto de 400×400 px é a coisa mais parecida com um bloco de
    texto que se pode desenhar.
    """
    altura, largura = image_rgb.shape[:2]
    x0, y0, x1, y1 = _to_pixels(region, origin=origin, zoom=zoom)

    esquerda, topo = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
    direita, base = min(largura, int(np.ceil(x1))), min(altura, int(np.ceil(y1)))
    if direita > esquerda and base > topo:
        image_rgb[topo:base, esquerda:direita] = 255


def _to_pixels(rect: fitz.Rect, *, origin: tuple[float, float], zoom: float) -> tuple[float, float, float, float]:
    ox, oy = origin
    return ((rect.x0 - ox) * zoom, (rect.y0 - oy) * zoom, (rect.x1 - ox) * zoom, (rect.y1 - oy) * zoom)


def _to_points(
    bbox: tuple[float, float, float, float],
    *,
    origin: tuple[float, float],
    zoom: float,
) -> tuple[float, float, float, float]:
    ox, oy = origin
    x0, y0, x1, y1 = bbox
    return (x0 / zoom + ox, y0 / zoom + oy, x1 / zoom + ox, y1 / zoom + oy)


# --------------------------------------------------------------------------------------
# Caixas do motor -> linhas da S-16
# --------------------------------------------------------------------------------------


def _boxes_to_lines(
    boxes: Sequence[TextBox],
    *,
    origin: tuple[float, float],
    zoom: float,
    group_offset: int = 0,
    procedencia: LineOrigin = DE_TERCEIROS,
) -> list[TextLine]:
    """Converte as caixas do motor em `TextLine` agrupadas por bloco.

    O agrupamento é o que a camada de texto entrega pronto e o OCR não: `group_id` é a
    unidade que `assign_lines_to_diagrams` usa para decidir dono, e a S-16 mediu por que
    ele importa -- no `Schiller`, linha a linha, o `6` da legenda de baixo cai mais perto
    do diagrama de cima, e a página inteira sai numerada com um exercício de deslocamento.
    Aqui o bloco é reconstruído da geometria: linhas verticalmente adjacentes que
    compartilham coluna são o mesmo grupo.
    """
    convertidas = [
        (
            _to_points(box.bbox, origin=origin, zoom=zoom),
            " ".join(box.text.split()),
            float(box.confidence),
        )
        for box in boxes
    ]
    convertidas = [item for item in convertidas if item[1]]
    if not convertidas:
        return []

    convertidas.sort(key=lambda item: (item[0][1], item[0][0]))
    grupos = _group_by_block([bbox for bbox, _, _ in convertidas])

    palavras: dict[int, int] = {}
    for grupo, (_, texto, _) in zip(grupos, convertidas, strict=True):
        palavras[grupo] = palavras.get(grupo, 0) + len(texto.split())

    return [
        TextLine(
            text=texto,
            bbox=bbox,
            block_words=palavras[grupo],
            group_id=group_offset + grupo,
            origin=procedencia,
            confidence=confianca,
        )
        for (bbox, texto, confianca), grupo in zip(convertidas, grupos, strict=True)
    ]


def _group_by_block(bboxes: list[tuple[float, float, float, float]]) -> list[int]:
    """Rotula as caixas por bloco: vizinhas na vertical e sobrepostas na horizontal.

    Espelha o que `_split_into_columns` faz do outro lado -- lá quebrando um bloco do PDF
    em colunas, aqui montando o bloco que o PDF não tem. As duas metades da mesma decisão:
    o dono de uma legenda é o grupo, e o grupo é bloco *e* coluna.
    """
    labels = list(range(len(bboxes)))

    def find(index: int) -> int:
        while labels[index] != index:
            labels[index] = labels[labels[index]]
            index = labels[index]
        return index

    for i, (ax0, ay0, ax1, ay1) in enumerate(bboxes):
        for j in range(i + 1, len(bboxes)):
            bx0, by0, bx1, by1 = bboxes[j]
            if min(ax1, bx1) - max(ax0, bx0) <= 0.0:
                continue
            vao = max(by0 - ay1, ay0 - by1, 0.0)
            if vao <= _LINE_GAP_RATIO * max(ay1 - ay0, by1 - by0):
                labels[find(i)] = find(j)

    ordem: dict[int, int] = {}
    for index in range(len(bboxes)):
        raiz = find(index)
        ordem.setdefault(raiz, len(ordem))
    return [ordem[find(index)] for index in range(len(bboxes))]


def build_caption_reader(
    recognizer: TextRecognizer | None,
    *,
    radius_pt: float = DEFAULT_RADIUS_PT,
    dpi: float = DEFAULT_OCR_DPI,
) -> CaptionReader | None:
    """`CaptionReader` quando há motor, `None` quando não há.

    Existe para que o chamador não precise repetir o `if recognizer is None` -- o caminho
    sem OCR é o padrão do projeto, e ele tem de ser o mais curto de escrever.
    """
    if recognizer is None:
        return None
    return CaptionReader(recognizer, radius_pt=radius_pt, dpi=dpi)


def caption_reader_from_settings(
    settings: OcrSettings,
    *,
    radius_pt: float = DEFAULT_RADIUS_PT,
    dpi: float = DEFAULT_OCR_DPI,
) -> CaptionReader | None:
    """Da configuração ao leitor, num passo. `None` quando desligado ou sem o extra.

    O caminho que as duas interfaces e os CLIs usam. Importar este módulo é barato -- os
    motores só entram no `import` dentro de `build_recognizer`, e portanto só quando a
    configuração de fato pede um.
    """
    return build_caption_reader(build_recognizer(settings), radius_pt=radius_pt, dpi=dpi)
