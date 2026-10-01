# Origem: Editor_Diagramas_de_Xadrez/src/chess_pdf_editor/widgets.py
#         (`SelectablePageWidget._handle_centers`, `_handle_at`, `_resized_rect`, `_moved_rect`,
#          `_clamp_point`, `_clamp_rect`, `mousePressEvent`, `mouseReleaseEvent`, `_ARROW_DELTAS`).
# Absorvido em 2026-09-07. Alterações: (a) tudo isto era método de `QLabel` e mexia em
#         `self._selection_rect` -- aqui são funções sobre tuplas, e o gesto virou um `Enum` que
#         se afirma sem janela; (b) os dois números que decidem "isto foi clique, não arrasto"
#         deixaram de ser `10.0`/`18.0` locais e passaram a ser os do tronco, medidos
#         (`ui/leitura_do_pdf.CLICK_SLOP_PX` e `MIN_SELECTION_PX`).
"""O retângulo vivo sobre a página: alça, arrasto, ajuste fino e grampeamento (F9).

**O que existia antes, no aplicativo absorvido.** Só "arrastar do zero": corrigir um recorte 2 pt
torto exigia apagar a seleção e redesenhá-la inteira. O retângulo passou a ser um objeto vivo --
oito alças para redimensionar, o corpo para deslocar, as setas do teclado para o ajuste fino --,
e é essa a metade da capacidade que faz a substituição de diagrama ser usável num livro de
trezentos: o enquadramento tem de bater com o diagrama impresso, e ele nunca bate de primeira.

**Por que isto é `ui/` e não `qt/`.** Onde ficam as oito alças, qual delas um clique acertou,
o que cada uma faz com o retângulo, o que o corpo faz, quando parar de desenhar as de borda,
o que "clique" quer dizer e onde o retângulo para de crescer -- nada disso é desenho. É a mesma
separação que já sustenta `ui/board_model.py`: o widget traduz evento e pinta, e o modelo decide.
Na origem os dois estavam no mesmo `QLabel` de 560 linhas, e a consequência prática é que a
regra de "arrastar dentro da seleção é deslocamento, mas o clique parado ainda foca" -- que é
sutil e foi ajustada mais de uma vez -- não tinha um teste possível sem montar a página.

**Os dois números medidos não são inventados aqui.** `CLICK_SLOP_PX` e `MIN_SELECTION_PX` já
existem no tronco desde a S-330/S-503, com o registro de por que valem o que valem, e significam
exatamente o que a origem chamava de `10.0` e `18.0`. Reusá-los é o que impede que a mesma
pergunta -- "isto foi clique?" -- tenha duas respostas em duas telas do mesmo programa.
"""

from __future__ import annotations

from enum import Enum

from .leitura_do_pdf import CLICK_SLOP_PX, MIN_SELECTION_PX

__all__ = [
    "ALCAS",
    "LADO_DA_ALCA",
    "LADO_MINIMO_PARA_ALCAS_DE_BORDA",
    "PASSO_FINO_PT",
    "PASSO_PT",
    "TOLERANCIA_DA_ALCA",
    "Gesto",
    "Ponto",
    "Retangulo",
    "alca_em",
    "centros_das_alcas",
    "crescido",
    "decidir_gesto",
    "e_clique",
    "grampeado",
    "grampeado_ponto",
    "movido",
    "normalizado",
    "redimensionado",
    "selecao_pequena_demais",
]

Ponto = tuple[float, float]
Retangulo = tuple[float, float, float, float]
"""`(x0, y0, x1, y1)` em **pixel do widget** -- a página já rasterizada e já com zoom.

É outro espaço do `substituicao.Retangulo`, que é em ponto do PDF, e a distância entre os dois é
justamente o que `qt/pagina_selecionavel.py` converte com a escala em vigor. Os nomes coincidem de
propósito: são a mesma forma, e o que muda é a unidade -- confundi-las é o defeito que a
`ASSETS §2.8` documenta um nível acima."""

ALCAS: tuple[str, ...] = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
"""As oito, nomeadas pelos pontos cardeais. A ordem é a de desenho, começando no canto superior
esquerdo e girando com o relógio -- é a ordem em que o olho as percorre."""

LADO_DA_ALCA = 8.0
"""O quadrado desenhado. Oito pixels é o que se vê sobre um diagrama impresso sem cobrir uma casa
do tabuleiro, que é justamente o que a alça de canto fica em cima."""

TOLERANCIA_DA_ALCA = 11.0
"""Quanto o ponteiro pode errar e ainda pegar a alça. **Maior que o desenho, de propósito.**

Mesmo argumento de `cortina.TOLERANCIA_DE_CLIQUE`: acertar 8 px é sorte, não gesto. A folga é
medida em distância de Chebyshev (o maior dos dois eixos) e não euclidiana, porque a alça é um
quadrado -- uma tolerância circular deixaria os cantos dela sem resposta."""

LADO_MINIMO_PARA_ALCAS_DE_BORDA = 34.0
"""Abaixo disto as alças de borda cobririam as de canto, e a seleção vira um borrão de quadrados.

Some-se: duas alças de canto ocupam 8 px cada nas pontas, e a de borda 8 px no meio -- com menos
de ~34 px de lado as três se tocam, e clicar em qualquer ponto pega a alça errada. Cada eixo
decide o seu: uma seleção larga e baixa mantém `n`/`s` e perde `w`/`e`."""

PASSO_PT = 1.0
PASSO_FINO_PT = 0.25
"""O passo das setas do teclado, em **pontos do PDF** e não em pixel. `Shift` usa o fino.

Ponto e não pixel pela razão de sempre neste pacote: um passo em pixel valeria meio ponto a 200%
de zoom e quatro pontos a 25%, e o ajuste fino deixaria de ser fino justamente na vista de longe,
que é onde se enquadra. Quem converte é quem sabe o zoom."""


def normalizado(retangulo: Retangulo) -> Retangulo:
    """Os dois cantos em ordem. Arrastar da direita para a esquerda produz `x1 < x0`."""
    x0, y0, x1, y1 = retangulo
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def centros_das_alcas(retangulo: Retangulo) -> dict[str, Ponto]:
    """Onde cada alça está. As de borda somem quando o lado é curto demais -- ver a constante."""
    x0, y0, x1, y1 = normalizado(retangulo)
    meio_x = (x0 + x1) / 2.0
    meio_y = (y0 + y1) / 2.0
    centros: dict[str, Ponto] = {
        "nw": (x0, y0),
        "ne": (x1, y0),
        "se": (x1, y1),
        "sw": (x0, y1),
    }
    if (x1 - x0) >= LADO_MINIMO_PARA_ALCAS_DE_BORDA:
        centros["n"] = (meio_x, y0)
        centros["s"] = (meio_x, y1)
    if (y1 - y0) >= LADO_MINIMO_PARA_ALCAS_DE_BORDA:
        centros["w"] = (x0, meio_y)
        centros["e"] = (x1, meio_y)
    return centros


def alca_em(retangulo: Retangulo, x: float, y: float, *, tolerancia: float = TOLERANCIA_DA_ALCA) -> str | None:
    """Qual alça aquele ponto acertou, ou `None`.

    **Empate fica com a última avaliada em ordem de dicionário**, e não com a primeira: os
    centros são inseridos com os quatro cantos antes das quatro bordas, então um ponto
    equidistante entre `nw` e `n` -- que só acontece numa seleção quase no limite de
    `LADO_MINIMO_PARA_ALCAS_DE_BORDA` -- resolve na de borda. É arbitrário e precisa ser
    **estável**: o que não pode acontecer é a mesma coordenada pegar alças diferentes em duas
    execuções, que é o que uma iteração de `set` daria.
    """
    melhor: str | None = None
    menor = tolerancia
    for chave, (cx, cy) in centros_das_alcas(retangulo).items():
        distancia = max(abs(x - cx), abs(y - cy))
        if distancia <= menor:
            melhor = chave
            menor = distancia
    return melhor


def redimensionado(alca: str, base: Retangulo, x: float, y: float) -> Retangulo:
    """O retângulo com a borda daquela alça levada até o ponteiro.

    O nome da alça **é** a regra: `"nw"` contém `n` e `w`, então mexe no topo e na esquerda. Uma
    tabela de oito entradas diria a mesma coisa em oito lugares, e é o tipo de tabela que se
    escreve certa e se copia errada na nona.
    """
    x0, y0, x1, y1 = base
    if "w" in alca:
        x0 = x
    if "e" in alca:
        x1 = x
    if "n" in alca:
        y0 = y
    if "s" in alca:
        y1 = y
    return normalizado((x0, y0, x1, y1))


def grampeado_ponto(x: float, y: float, limite: Retangulo | None) -> Ponto:
    """O ponto dentro dos limites da página. Sem limite, ele mesmo."""
    if limite is None:
        return (x, y)
    lx0, ly0, lx1, ly1 = limite
    return (min(max(lx0, x), lx1), min(max(ly0, y), ly1))


def grampeado(retangulo: Retangulo, limite: Retangulo | None) -> Retangulo:
    """O retângulo cortado pela página. **Corta, e por isso encolhe.** Ver `movido`."""
    x0, y0, x1, y1 = normalizado(retangulo)
    ax, ay = grampeado_ponto(x0, y0, limite)
    bx, by = grampeado_ponto(x1, y1, limite)
    return normalizado((ax, ay, bx, by))


def movido(base: Retangulo, dx: float, dy: float, limite: Retangulo | None) -> Retangulo:
    """Desloca **mantendo o tamanho**: encostar na borda não encolhe a seleção.

    É a diferença para `grampeado`, e ela é o item. Deslocar com corte faria o retângulo perder
    largura ao ser empurrado contra a margem e **não recuperá-la** ao voltar -- a pessoa moveria
    o enquadramento até a borda para conferir o alinhamento e o traria de volta menor do que era.
    Aqui o que se grampeia é a **posição**, e o tamanho é invariante do gesto.
    """
    x0, y0, x1, y1 = normalizado(base)
    largura = x1 - x0
    altura = y1 - y0
    nx0 = x0 + dx
    ny0 = y0 + dy
    if limite is not None:
        lx0, ly0, lx1, ly1 = limite
        nx0 = min(max(lx0, nx0), max(lx0, lx1 - largura))
        ny0 = min(max(ly0, ny0), max(ly0, ly1 - altura))
    return (nx0, ny0, nx0 + largura, ny0 + altura)


def crescido(base: Retangulo, dx: float, dy: float, limite: Retangulo | None, *, minimo: float = 2.0) -> Retangulo:
    """Cresce pelo canto inferior-direito -- é o que `Ctrl` + seta faz.

    Pelo canto de baixo e não pelo centro porque o outro canto é a **âncora** do enquadramento:
    quem ajusta um recorte já alinhou uma das pontas com o diagrama impresso, e crescer pelo
    centro desalinharia as duas de uma vez. Mover e redimensionar com o mesmo passo é o que
    mantém o ajuste previsível.
    """
    x0, y0, x1, y1 = normalizado(base)
    largura = max(minimo, (x1 - x0) + dx)
    altura = max(minimo, (y1 - y0) + dy)
    return grampeado((x0, y0, x0 + largura, y0 + altura), limite)


def selecao_pequena_demais(retangulo: Retangulo, *, minimo: float = MIN_SELECTION_PX) -> bool:
    """Um arrasto que não chega a `MIN_SELECTION_PX` nos dois eixos é clique errado, não seleção.

    O número é o do tronco e não o `18.0` da origem, porque a pergunta é a mesma e o tronco já a
    respondeu com medida: abaixo de doze pixels o recorte não conteria nem uma casa do tabuleiro.
    """
    x0, y0, x1, y1 = normalizado(retangulo)
    return (x1 - x0) < minimo and (y1 - y0) < minimo


def e_clique(dx: float, dy: float, *, folga: float = CLICK_SLOP_PX) -> bool:
    """O ponteiro andou tão pouco entre apertar e soltar que aquilo foi um clique.

    `CLICK_SLOP_PX` é do tronco e vale 4, contra os 10 da origem (que comparava o **quadrado** da
    distância com 100). Quatro é mais exigente, e de propósito: aqui o gesto que se está tentando
    separar do clique é *deslocar uma seleção*, e um deslocamento de 5 px é um ajuste fino
    legítimo -- tratá-lo como clique jogaria fora o enquadramento que a pessoa acabou de acertar.
    """
    return (dx * dx + dy * dy) <= (folga * folga)


class Gesto(str, Enum):
    """O que apertar o botão naquele ponto significa. `str` para aparecer legível num rastro."""

    CORTINA = "cortina"
    """Arrastar a divisa da comparação."""

    REDIMENSIONAR = "redimensionar"
    MOVER = "mover"
    NOVA = "nova"
    """Começar uma seleção do zero."""


def decidir_gesto(
    x: float,
    y: float,
    *,
    selecao: Retangulo | None,
    perto_da_cortina: bool,
) -> tuple[Gesto, str | None]:
    """O gesto e, quando for redimensionar, a alça. **A ordem das três perguntas é o item.**

    **A cortina vem antes da seleção.** A divisa cruza a página inteira, então ela cruza também o
    retângulo selecionado. Se o clique nela caísse na seleção, arrastar para comparar viraria
    "mover seleção", e a pessoa perderia o enquadramento sem querer -- no gesto que ela faz
    justamente para **conferir** o enquadramento.

    **A alça vem antes do corpo**, porque a alça de canto fica dentro do retângulo: perguntar
    "está dentro?" primeiro faria as oito alças nunca serem alcançadas.
    """
    if perto_da_cortina:
        return (Gesto.CORTINA, None)
    if selecao is not None:
        alca = alca_em(selecao, x, y)
        if alca is not None:
            return (Gesto.REDIMENSIONAR, alca)
        x0, y0, x1, y1 = normalizado(selecao)
        if x0 <= x <= x1 and y0 <= y <= y1:
            return (Gesto.MOVER, None)
    return (Gesto.NOVA, None)
