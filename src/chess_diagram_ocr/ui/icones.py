"""O ícone como traço declarado, desenhado na cor que o token resolve (S-220).

**O problema não era falta de arte — era que arte de arquivo não sobrevive a três peles.**
`assets/` tem 12 PNGs de peça e um `.ico`, e mais nada. As duas propostas de interface são
dirigidas a ícone (4 na Imagem 1, 13 na Imagem 2), e um conjunto de PNG resolveria uma e quebraria
a outra: os PNGs deste projeto são traço preto com transparência, e `PieceImages.icon` documenta o
que acontece com eles quando o fundo escurece -- *"num dos 15 temas escuros do `ttkbootstrap` as
seis peças pretas somem no fundo da janela"* (`ui/board_render.py:196-199`). A pele "Foco" é
escura. Traço escuro nela é um botão sem ícone; traço claro na pele "Fita" é o mesmo defeito
espelhado. É a S-146 outra vez -- cor cravada contra fundo variável --, agora numa família de arte
nova.

**A saída é a mesma dos tokens: declarar a forma e derivar o desenho.** Cada ícone é uma tupla de
traços numa caixa `0..100`, sem cor e sem tamanho. `icone(nome, tamanho, cor)` desenha na hora, e
**a cor é do chamador**: quem monta a fita pede `tokens.cor(tokens.TEXTO_PADRAO, style)` e passa. É
isso que faz o mesmo `abrir_pdf` funcionar nas três peles sem uma segunda arte.

**Por que não SVG.** Traria dependência (`cairosvg` ou similar) para desenhar catorze formas de
traço único. O `ImageDraw.line` com `joint="curve"` faz o que estas formas precisam, e a Pillow já
é dependência obrigatória.

**O que este módulo não sabe.** Que comandos existem. `ui/comandos.py` é quem declara qual comando
tem ícone, e a ponte entre os dois é um teste -- nos dois sentidos, para que ícone órfão e comando
apontando para nada falhem igual. Assim o catálogo continua sem importar `PIL`, que é o que o
mantém afirmável sem janela.
"""

from __future__ import annotations

import logging

# **A Pillow é dependência obrigatória, e mesmo assim o import é guardado** (S-234).
#
# Não é zelo: `ui/fila.py` e `ui/fita.py` importam este módulo, e um `ImportError` aqui em cima
# apaga o programa antes de ele existir -- que é exatamente o que a regra 4 proíbe. Guardado, um
# checkout quebrado desenha botões só com texto e diz por quê.
#
# **O que isto não promete:** que o programa inteiro abra sem a Pillow. `ui/board_render.py` a
# importa sem guarda porque as peças são o **documento**, e não cromo -- um tabuleiro que não
# desenha não é uma janela degradada, é uma janela sem produto. O contrato de degradação é da
# aparência, e esta linha é a parte dele que cabe aqui.
try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # pragma: no cover - checkout ou bundle sem a Pillow
    Image = ImageDraw = ImageTk = None  # type: ignore[assignment]

from . import degradacao

logger = logging.getLogger(__name__)

__all__ = [
    "ICONES",
    "MARCAS",
    "MARCA_TRACO",
    "MARCA_VISTO",
    "Arco",
    "Poli",
    "TRACO_RELATIVO",
    "cache_de_icones",
    "caixa_dos_tracos",
    "icone",
    "imagem",
    "limpar_cache",
    "na_grade",
]

Ponto = tuple[float, float]

LADO_DA_CAIXA = 100.0
"""A caixa em que todo traço é declarado. Não é pixel: é a unidade que o tamanho pedido escala."""

TRACO_RELATIVO = 0.09
"""Espessura do traço, em fração do lado. 9 de 100 -- o traço de ícone de linha a 24 px é ~2 px.

Declarado uma vez e não por ícone de propósito: espessura por ícone é o começo de uma família em
que metade dos desenhos parece mais leve que a outra, e a fita da S-228 os põe lado a lado."""


class Poli:
    """Uma sequência de segmentos. `fechado` liga o último ponto ao primeiro.

    Não é `dataclass` porque a declaração fica muito melhor com os pontos soltos --
    `Poli((10, 30), (40, 30))` em vez de `Poli(((10, 30), (40, 30)))` --, e num arquivo que é
    quase todo declaração isso decide a legibilidade dele.
    """

    __slots__ = ("fechado", "pontos")

    def __init__(self, *pontos: Ponto, fechado: bool = False) -> None:
        if len(pontos) < 2:
            raise ValueError("um traço precisa de pelo menos dois pontos")
        self.pontos = tuple(pontos)
        self.fechado = fechado

    def __repr__(self) -> str:  # pragma: no cover - conveniência de depuração
        return f"Poli({', '.join(map(str, self.pontos))}, fechado={self.fechado})"

    def limites(self) -> tuple[float, float, float, float]:
        """`(x_min, y_min, x_max, y_max)`, para a guarda de caixa."""
        xs = [x for x, _ in self.pontos]
        ys = [y for _, y in self.pontos]
        return min(xs), min(ys), max(xs), max(ys)


class Arco:
    """Um arco da elipse inscrita na caixa `centro ± raio`. Ângulos em graus, 0 = leste.

    `Arco((50, 50), 30, 0, 360)` é um círculo -- e é assim que a lupa nasce.
    """

    __slots__ = ("centro", "fim", "inicio", "raio")

    def __init__(self, centro: Ponto, raio: float, inicio: float = 0.0, fim: float = 360.0) -> None:
        self.centro = centro
        self.raio = raio
        self.inicio = inicio
        self.fim = fim

    def __repr__(self) -> str:  # pragma: no cover - conveniência de depuração
        return f"Arco({self.centro}, {self.raio}, {self.inicio}, {self.fim})"

    def limites(self) -> tuple[float, float, float, float]:
        """A caixa do **círculo inteiro**, e não a do arco desenhado.

        É a caixa que a Pillow recebe, então é a que precisa caber -- medir só o arco deixaria
        passar um semicírculo cujo centro está fora da caixa, que desenha cortado do mesmo jeito.
        """
        x, y = self.centro
        return x - self.raio, y - self.raio, x + self.raio, y + self.raio


Traco = Poli | Arco


def caixa_dos_tracos(tracos: tuple[Traco, ...]) -> tuple[float, float, float, float]:
    """A caixa que **todos** os traços de um ícone ocupam juntos, na unidade `0..100`."""
    limites = [traco.limites() for traco in tracos]
    return (
        min(item[0] for item in limites),
        min(item[1] for item in limites),
        max(item[2] for item in limites),
        max(item[3] for item in limites),
    )


def na_grade(tracos: tuple[Traco, ...]) -> tuple[Traco, ...]:
    """Os mesmos traços, **postos na grade única**: o lado maior enche a caixa, centrados.

    **O item 4 do ciclo 6, e ele foi medido antes de ser consertado.** Os botões só-de-ícone da
    barra do visor vinham de **cinco caixas de glifo diferentes** -- 11×11, 12×12, 12×14, 14×10,
    14×12 -- porque cada desenho declarava a sua própria extensão dentro do `0..100`: a lupa vai
    de 16 a 88, a folha de 10 a 90, as paredes da largura de 22 a 78 na vertical.
    `TRACO_RELATIVO` já garantia **um peso** de traço; o que faltava era **uma extensão**, e sem
    ela um ícone saía 27 % maior que o vizinho na mesma fila.

    A escala é **isotrópica** e de propósito: esticar cada desenho até um quadrado faria a seta
    da página anterior virar uma seta gorda e a lupa virar uma elipse. O que se iguala é o
    **tamanho óptico** -- o lado maior --, e o que sobra de diferença entre as caixas é a
    proporção da própria forma, que é o que distingue uma seta de um quadrado.

    **Não vale para `MARCAS`**: o visto e o traço do indeterminado são deliberadamente de
    tamanhos diferentes -- *"ele é horizontal e mais curto que o visto é largo"* --, e essa
    diferença é a WCAG 1.4.1 que o ciclo 1 cobrou. Normalizá-los desfaria o conserto.
    """
    x0, y0, x1, y1 = caixa_dos_tracos(tracos)
    largura, altura = x1 - x0, y1 - y0
    maior = max(largura, altura)
    if maior <= 0:
        return tracos
    escala = LADO_DA_CAIXA / maior
    dx = (LADO_DA_CAIXA - largura * escala) / 2 - x0 * escala
    dy = (LADO_DA_CAIXA - altura * escala) / 2 - y0 * escala

    def mover(ponto: Ponto) -> Ponto:
        return ponto[0] * escala + dx, ponto[1] * escala + dy

    postos: list[Traco] = []
    for traco in tracos:
        if isinstance(traco, Poli):
            postos.append(Poli(*(mover(ponto) for ponto in traco.pontos), fechado=traco.fechado))
        else:
            postos.append(Arco(mover(traco.centro), traco.raio * escala, traco.inicio, traco.fim))
    return tuple(postos)


ICONES: dict[str, tuple[Traco, ...]] = {
    # A chave é o nome do comando em `ui/comandos.py`. Dois comandos podem apontar para a mesma
    # chave -- hoje nenhum aponta, e é por isso que a ponte é testada nos dois sentidos.
    # ---------------------------------------------------------------------------- ARQUIVO
    # Pasta com aba, os pontos da própria spec.
    "abrir_pdf": (Poli((10, 30), (40, 30), (48, 40), (90, 40), (90, 82), (10, 82), fechado=True),),
    # Disquete: corpo com o canto cortado, a portinhola em cima e a etiqueta embaixo.
    "salvar": (
        Poli((16, 16), (68, 16), (84, 32), (84, 84), (16, 84), fechado=True),
        Poli((34, 16), (34, 40), (66, 40), (66, 16)),
        Poli((30, 84), (30, 58), (70, 58), (70, 84)),
    ),
    # Bandeja aberta com a seta saindo por cima: exportar é o que sai do programa.
    "exportar_pgn": (
        Poli((18, 58), (18, 86), (82, 86), (82, 58)),
        Poli((50, 14), (50, 66)),
        Poli((32, 32), (50, 14), (68, 32)),
    ),
    # -------------------------------------------------------------------------------- OCR
    # Folha inteira com o facho atravessando: ler **a página**.
    "ler_pagina": (
        Poli((26, 14), (74, 14), (74, 86), (26, 86), fechado=True),
        Poli((14, 50), (86, 50)),
    ),
    # Tabuleiro de quatro casas: ler **um diagrama**. O objeto é outro, e a 16 px é a diferença
    # entre os dois que se enxerga primeiro -- folha alta contra quadrado dividido.
    "ler_melhor": (
        Poli((18, 18), (82, 18), (82, 82), (18, 82), fechado=True),
        Poli((18, 50), (82, 50)),
        Poli((50, 18), (50, 82)),
    ),
    # Os quatro cantos do recorte, que é o gesto que o comando pede.
    # **Os cantos ficaram mais longos no F9-C6**, e a razão é a densidade medida: com braços de
    # 20 unidades este era o desenho mais **fino** da fila do visor -- 25,0 % de tinta na caixa,
    # contra 73,2 % do vizinho `ajustar_pagina`. Braços de 32 põem os dois na mesma vizinhança
    # sem mexer no que o ícone diz: continua sendo o recorte pelos quatro cantos.
    "selecionar_area": (
        Poli((14, 46), (14, 14), (46, 14)),
        Poli((54, 14), (86, 14), (86, 46)),
        Poli((86, 54), (86, 86), (54, 86)),
        Poli((46, 86), (14, 86), (14, 54)),
    ),
    # ----------------------------------------------------------------------------- EDICAO
    "aplicar_fen": (Poli((18, 52), (40, 76), (82, 24)),),
    # Casa com o X dentro: o que se apaga é a peça **daquela casa**, e não a posição toda.
    "apagar_casa": (
        Poli((16, 16), (84, 16), (84, 84), (16, 84), fechado=True),
        Poli((34, 34), (66, 66)),
        Poli((66, 34), (34, 66)),
    ),
    # **Quadradas, e o que separa as duas famílias passa a ser o preenchimento** (F9-C7, §4.7).
    # Eram 32×64 -- estreitas e altas de propósito, para se distinguirem das setas de **página**,
    # que são 60×60 -- e a proporção custava caro depois que elas saíram do catálogo e foram
    # para a tela: `na_grade` enche o lado maior, então 32×64 vira uma caixa de tinta de **8×16**
    # ao lado de irmãs de 16×16, e a "grade única" que o ciclo 6 conquistou na barra do visor
    # deixaria de valer na janela.
    #
    # O que separa as duas famílias continua existindo e ficou mais forte a 16 px: estas são
    # **abertas** (uma seta em V, traço) e as de página são **fechadas** (triângulo cheio).
    # Preenchimento lê-se num relance; proporção de 2:1 contra 1:1 não.
    "diagrama_anterior": (Poli((78, 20), (22, 50), (78, 80)),),
    "proximo_diagrama": (Poli((22, 20), (78, 50), (22, 80)),),
    # ------------------------------------------------------- os três que faltavam (F9-C6)
    # **Eram caracteres de texto num botão só-de-ícone**, e o crítico do ciclo 5 mediu o pior
    # deles: o `×` de `tirar_caixa` desenhava uma caixa de glifo de **4×5 px dentro de um botão
    # de 26 px** -- um nono da massa visual do vizinho, na mesma fila. `strings.DISPENSAR`,
    # `ANTERIOR` e `PROXIMO` continuam existindo como reserva (o caminho de `_vestir_de_icone`
    # quando a Pillow falta), mas o desenho normal passa a vir da mesma grade que os outros seis.
    #
    # O `×` é o de `apagar_casa` **sem a casa**: o gesto é o mesmo -- tirar --, e o objeto é
    # outro. As duas setas são as de diagrama espelhadas com a barra da margem, que é a
    # convenção de "página" contra "item" em todo leitor de PDF.
    "tirar_caixa": (
        Poli((22, 22), (78, 78)),
        Poli((78, 22), (22, 78)),
    ),
    # **Triângulo fechado e largo, e a barra de margem saiu.** A primeira forma deste ciclo era
    # a seta com a barra -- `|◀` --, e `|◀` é a convenção universal de **primeira** página: um
    # ícone que diz a coisa errada é pior que o `◀` de texto que ele veio substituir. Fechado
    # porque a 16 px o contorno lê como triângulo cheio, que é o `◀` que estava ali; largo
    # (60×60) porque as setas de **diagrama** são estreitas e altas (32×64) e as duas famílias
    # ficam na mesma janela -- a proporção é o que as separa sem legenda.
    "pagina_anterior": (Poli((80, 20), (20, 50), (80, 80), fechado=True),),
    "proxima_pagina": (Poli((20, 20), (80, 50), (20, 80), fechado=True),),
    # ------------------------------------------------- as pontas da linha (F9-C7, §4.7)
    # **Onze glifos de texto ainda faziam papel de ícone na janela**, e o ciclo 6 só olhou a
    # barra do visor: a varredura era `j.pdf.findChildren`, e nos outros quatro painéis o `◀`
    # rendia **5×3 px de tinta** contra **6×6** do `▶` ao lado -- 2,4× de massa entre um par
    # que deveria ser espelho, e ampliado a 10× o `◀` não tem ápice nenhum: é um traço
    # horizontal chato. Segoe UI cobre um dos dois e degenera o outro.
    #
    # Aqui a barra **é** a informação: `|◀` é "primeiro" e `▶|` é "último", e é a convenção de
    # todo leitor de mídia e de PDF. É a diferença para `pagina_anterior`, onde a barra saiu
    # justamente porque ali ela diria "primeira página" no botão de "página anterior".
    "inicio_da_linha": (
        Poli((22, 18), (22, 82)),
        Poli((84, 18), (36, 50), (84, 82), fechado=True),
    ),
    "fim_da_linha": (
        Poli((16, 18), (64, 50), (16, 82), fechado=True),
        Poli((78, 18), (78, 82)),
    ),
    # A seta que dá a volta por cima e desce na ponta -- os dois são a mesma forma espelhada, e
    # desenhá-los diferentes seria dizer que não são o mesmo gesto em sentidos opostos. O arco vai
    # de 180 a 360 porque na Pillow o ângulo cresce no sentido horário com o eixo `y` para baixo:
    # 180 é a esquerda, 270 é o **topo**, 360 é a direita.
    # Três quartos de volta com a ponta da seta: a 20 px a meia-volta de antes ocupava 9 dos 20
    # px de altura e o botão parecia vazio (passo 12: caixa do desenho ≥ metade do lado nos dois
    # eixos).
    "desfazer": (
        Arco((50, 52), 30, 200, 470),
        Poli((10, 40), (22, 60), (36, 42)),
    ),
    "refazer": (
        Arco((50, 52), 30, 70, 340),
        Poli((64, 42), (78, 60), (90, 40)),
    ),
    # O tabuleiro e o que sai dele. **Não é o `apagar_casa` com outro nome**: aquele é uma casa com
    # um X, e este é a posição inteira indo embora -- a 20 px, a diferença que se lê primeiro é o
    # traço de movimento ao lado, e não o desenho de dentro.
    "limpar_tabuleiro": (
        Poli((14, 24), (58, 24), (58, 76), (14, 76), fechado=True),
        Poli((70, 36), (92, 36)),
        Poli((70, 50), (92, 50)),
        Poli((70, 64), (92, 64)),
    ),
    # ----------------------------------------------------------------------- VISUALIZACAO
    # Lupa com sinal. O corpo é o mesmo nos dois: são o mesmo gesto em sentidos opostos, e
    # desenhá-los diferentes seria dizer que não são.
    "zoom_mais": (
        Arco((44, 44), 28),
        Poli((64, 64), (88, 88)),
        Poli((44, 32), (44, 56)),
        Poli((32, 44), (56, 44)),
    ),
    "zoom_menos": (
        Arco((44, 44), 28),
        Poli((64, 64), (88, 88)),
        Poli((32, 44), (56, 44)),
    ),
    # Duas paredes e a seta de dois sentidos entre elas: a largura é que manda.
    "ajustar_largura": (
        Poli((10, 10), (10, 90)),
        Poli((90, 10), (90, 90)),
        Poli((26, 50), (74, 50)),
        Poli((36, 40), (26, 50), (36, 60)),
        Poli((64, 40), (74, 50), (64, 60)),
    ),
    # A folha inteira dentro da moldura: o enquadramento de escolher qual diagrama abrir.
    #
    # **A folha de dentro encolheu no F9-C6.** Duas caixas fechadas quase encostadas faziam deste
    # o desenho mais **sólido** do visor -- 73,2 % de tinta na caixa, contra 25,0 % do
    # `selecionar_area` na mesma fila, que é a "densidade de 30,6 % a 65,7 %" que o crítico do
    # ciclo 5 fotografou. A folha menor diz a mesma coisa (o que cabe **dentro** da moldura) com
    # menos massa, e a moldura continua sendo a forma que se lê primeiro a 16 px.
    "ajustar_pagina": (
        Poli((10, 10), (90, 10), (90, 90), (10, 90), fechado=True),
        Poli((36, 40), (64, 40)),
        Poli((36, 60), (64, 60)),
    ),
}
"""Os dezessete ícones, e a razão de serem dezessete está na conta das duas imagens.

A Imagem 1 pede quatro (ler, próximo diagrama, aplicar FEN, exportar) e a Imagem 2 pede treze; a
união, restrita ao que existia como comando na S-220, dava treze. O décimo quarto é
`diagrama_anterior`: a Imagem 1 desenha só o "próximo", e uma seta que só existe num sentido é um
grupo de fita com metade dos botões sem ícone (S-228).

**Os três últimos são os que a Imagem 2 pedia e o programa não tinha.** Desfazer e Refazer não
tinham implementação nenhuma (achado 4 do roadmap); a S-229 os criou, e com eles o "Limpar", que
não é a `apagar_casa` -- aquele apaga **uma casa** e este esvazia a posição. Enquanto os comandos
não existiam, um ícone para eles seria arte órfã, e a ponte com `ui/comandos.py` é testada nos dois
sentidos justamente para que isso falhe."""


MARCA_VISTO = "marca_visto"
MARCA_TRACO = "marca_traco"
MARCAS: dict[str, tuple[Traco, ...]] = {
    # O visto, em três quartos da caixa: a caixa de seleção tem 14 px e o traço precisa da folga
    # da borda de 2 px para não encostar nela.
    MARCA_VISTO: (Poli((20, 52), (42, 74), (80, 26)),),
    # O traço do indeterminado. Ele é **horizontal e mais curto que o visto é largo**, que é a
    # diferença de forma que a 1.4.1 pede: as duas marcas não se confundem em preto e branco.
    MARCA_TRACO: (Poli((24, 50), (76, 50)),),
}
"""As duas marcas do indicador de seleção. **Não são ícones de comando** (F9-C2, §7 item 17).

**O defeito, medido pelo crítico do ciclo 1:** "marcada" era um quadrado azul cheio e
"indeterminada" um quadrado cinza cheio -- *mesma forma, mesmo tamanho, só a matiz separa*. É
WCAG 1.4.1 nível A: a cor não pode ser o único canal que carrega a informação. Quem não distingue
as duas matizes, ou quem imprime a tela, vê dois quadrados iguais.

Elas moram fora de `ICONES` de propósito, e a razão é a ponte: `ICONES` é fechada contra
`ui/comandos.CATALOGO` nos dois sentidos -- todo ícone é de um comando e todo comando com ícone
tem o seu. Uma marca de indicador não é comando nenhum, e enfiá-la lá quebraria a única regra que
faz aquela tabela não crescer sozinha.

O traço vem de `TRACO_RELATIVO`, como todo o resto: a marca de uma caixa de 14 px é desenhada em
100×100 e reduzida, e é o que a mantém nítida quando alguém aumenta a fonte do Windows."""

SUPERAMOSTRA = 4
"""Fator de desenho antes de reduzir. A Pillow não suaviza traço, e a redução é que suaviza.

Sem isto o traço diagonal do "aplicar_fen" a 20 px vira escada, e o círculo da lupa vira um
octógono -- num tamanho em que o ícone é a única coisa que a pessoa lê no botão."""

_cache: dict[tuple[str, int, str], ImageTk.PhotoImage] = {}


def _largura_do_traco(lado: int) -> int:
    return max(1, round(lado * TRACO_RELATIVO))


def imagem(nome: str, tamanho: int, cor: str) -> Image.Image | None:
    """O ícone como `Image` RGBA de `tamanho × tamanho`, sem passar pelo Tk.

    Existe separado de `icone` para que o desenho seja afirmável sem janela: é aqui que os testes
    de geometria olham, e é o que permite conferir o ícone num tamanho sem abrir um `Tk`.
    """
    # **A grade única entra aqui e não na declaração** (F9-C6, item 4). Pôr as coordenadas já
    # normalizadas na tabela faria a declaração deixar de ser legível -- `Poli((11.7, 3.2), …)`
    # em vez de `Poli((10, 30), …)` --, e faria cada desenho novo ter de ser normalizado à mão
    # para caber na fila, que é exatamente a disciplina que não sobreviveu quatro ciclos.
    # `MARCAS` fica de fora: ver `na_grade`.
    tracos = ICONES.get(nome)
    tracos = na_grade(tracos) if tracos else MARCAS.get(nome)
    if tracos is None:
        # **Uma vez por nome, e não uma por botão** (S-234). A fita pede o mesmo ícone a cada
        # remontagem de cromo e a cada mudança de densidade; sem isto, um nome errado escreve
        # uma linha de log por botão desenhado, e o log deixa de ser lido.
        degradacao.avisar_uma_vez(
            logger, ("icone", nome), "Ícone desconhecido: %r. O botão fica só com o texto.", nome
        )
        return None

    if Image is None or ImageDraw is None:
        degradacao.avisar_uma_vez(
            logger, "pillow", "Pillow indisponível: os botões ficam só com o texto (S-234)."
        )
        return None

    try:
        return _desenhar(tracos, tamanho, cor)
    except Exception as exc:  # noqa: BLE001 - desenho falho é queda, e não motivo para não abrir
        degradacao.avisar_uma_vez(
            logger,
            ("desenho", nome),
            "Ícone %r não desenhou (%s). O botão fica só com o texto.",
            nome,
            exc,
        )
        return None


def _desenhar(tracos: tuple[Traco, ...], tamanho: int, cor: str) -> Image.Image:
    """O desenho propriamente dito. Separado para que `imagem` seja só a guarda e a decisão."""
    tamanho = max(1, int(tamanho))
    lado = tamanho * SUPERAMOSTRA
    largura = _largura_do_traco(lado)
    # O traço é centrado no caminho: um ponto em 0 ou em 100 desenharia metade fora da imagem.
    # Encolher a caixa pela espessura é o que garante que **toda** coordenada válida caiba --
    # e é por isso que a guarda de caixa pode ser `0..100` fechado em vez de uma margem a olho.
    escala = (lado - largura) / LADO_DA_CAIXA
    desloc = largura / 2

    def ponto(par: Ponto) -> tuple[float, float]:
        return desloc + par[0] * escala, desloc + par[1] * escala

    # **O traço vira máscara, e a cor entra só no fim.** Reduzir uma imagem colorida faz a
    # `LANCZOS` interpolar os três canais junto com o alfa, e o `#101010` pedido sai como
    # `#111111` na maior parte dos pixels -- ondulação que, num ícone claro sobre cromo escuro,
    # aparece como halo em volta do traço. Máscara em `L` e cor chapada por cima devolvem
    # exatamente a cor que o token resolveu, com a suavização toda no alfa, que é onde ela deve
    # estar.
    mascara = Image.new("L", (lado, lado), 0)
    pincel = ImageDraw.Draw(mascara)
    for traco in tracos:
        if isinstance(traco, Poli):
            pontos = [ponto(par) for par in traco.pontos]
            if traco.fechado:
                pontos.append(pontos[0])
            # `joint="curve"` arredonda o vértice: sem ele o cotovelo da pasta e o bico do
            # "visto" saem com um entalhe, que a 16 px parece sujeira e não desenho.
            pincel.line(pontos, fill=255, width=largura, joint="curve")
        else:
            x, y = traco.centro
            caixa = [
                *ponto((x - traco.raio, y - traco.raio)),
                *ponto((x + traco.raio, y + traco.raio)),
            ]
            pincel.arc(caixa, traco.inicio, traco.fim, fill=255, width=largura)

    tela = Image.new("RGBA", (tamanho, tamanho), cor)
    tela.putalpha(mascara.resize((tamanho, tamanho), resample=Image.Resampling.LANCZOS))
    return tela


def icone(nome: str, tamanho: int, cor: str) -> ImageTk.PhotoImage | None:
    """O ícone pronto para um widget, no tamanho e na cor pedidos. `None` se o nome não existe.

    **A cor é do chamador, e é o item inteiro.** Quem monta a fita pergunta ao token --
    `tokens.cor(tokens.TEXTO_PADRAO, style)` -- e passa o hexadecimal; a pele escura pergunta o
    mesmo papel e recebe outro. Nenhum ícone tem cor própria, e por isso os catorze servem às três
    peles sem uma segunda arte.

    **Devolve `None` em vez de levantar** para nome desconhecido -- ao contrário de `tokens.cor` e
    de `estilos.estilo_de_botao`. A diferença é o que acontece depois: papel de botão errado
    desenha um botão que mente sobre a sua importância, e ícone que falta desenha um botão só com
    texto, que é legível. Um ícone não pode impedir a janela de abrir (regra 4 da SPEC_APARENCIA).

    O cache guarda `ImageTk.PhotoImage`, que precisa de referência viva para o Tk não a recolher.
    Ele é do módulo, e não de uma instância, porque este processo tem **uma** raiz Tk -- a regra
    que `tests/tk_root.py` documenta e que a suíte inteira segue.
    """
    tamanho = max(1, int(tamanho))
    chave = (nome, tamanho, cor)
    guardado = _cache.get(chave)
    if guardado is not None:
        return guardado

    desenho = imagem(nome, tamanho, cor)
    if desenho is None or ImageTk is None:
        return None

    try:
        foto = ImageTk.PhotoImage(desenho)
    except Exception as exc:  # noqa: BLE001 - sem raiz Tk, ou Tk que recusa a imagem
        degradacao.avisar_uma_vez(
            logger, ("foto", nome), "Ícone %r não virou imagem do Tk (%s).", nome, exc
        )
        return None
    _cache[chave] = foto
    return foto


def cache_de_icones() -> int:
    """Quantos ícones estão desenhados agora. Para teste e para depurar consumo."""
    return len(_cache)


def limpar_cache() -> None:
    """Esquece o que foi desenhado. A troca de pele (S-222) chama isto: a cor mudou."""
    _cache.clear()
