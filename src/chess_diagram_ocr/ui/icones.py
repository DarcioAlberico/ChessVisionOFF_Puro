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
traços numa caixa `0..100`, sem cor e sem tamanho. `imagem(nome, tamanho, cor)` desenha na hora, e
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
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - checkout ou bundle sem a Pillow
    Image = ImageDraw = None  # type: ignore[assignment]

from . import degradacao

logger = logging.getLogger(__name__)

__all__ = [
    "ICONES",
    "ICONES_DA_SALA",
    "ICONES_DO_PDF",
    "MARCA_TRACO",
    "MARCA_VISTO",
    "Arco",
    "Poli",
    "imagem",
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
    #
    # **As mesmas duas chaves nasceram também na sala de estudo** (S-520), e lá a razão não era
    # estética: `⏮` e `⏭` não existem na fonte da interface (`QFontMetrics.inFont` responde
    # `False`), e o botão desenhava com uma fonte de queda. O desenho que ficou é o daqui; o que
    # a S-520 trouxe e continua valendo é o reuso: `lance_anterior` e `proximo_lance` apontam para
    # `diagrama_anterior` e `proximo_diagrama` em vez de declarar setas próprias -- o mesmo gesto
    # noutra aba, e o primeiro caso do que o comentário do topo previa: dois comandos na mesma
    # chave.
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
    #
    # **A ponta é um triângulo fechado, e não uma cotovelada** (S-554, terceira rodada). O crítico
    # mediu o que a cotovelada valia: a 20 px `desfazer` e `refazer` diferiam em **24 px de 50 de
    # traço**, e o que se via eram dois rabiscos quase iguais -- o arco é o mesmo nos dois, e a
    # única coisa que dizia o sentido eram três segmentos de 1,8 px que o antialias comia. Um
    # triângulo fechado no tamanho do traço é maciço já a 16 px, e é ele que carrega o sentido.
    # O arco é o de três quartos de volta, logo acima; a ponta fechada fica onde a cotovelada estava.
    "desfazer": (
        Arco((50, 52), 30, 200, 470),
        Poli((10, 40), (22, 60), (36, 42), fechado=True),
    ),
    "refazer": (
        Arco((50, 52), 30, 70, 340),
        Poli((64, 42), (78, 60), (90, 40), fechado=True),
    ),
    # O tabuleiro e o que sai dele. **Não é o `apagar_casa` com outro nome**: aquele é uma casa com
    # um X, e este é a posição inteira indo embora -- a 20 px, a diferença que se lê primeiro é a
    # seta ao lado, e não o desenho de dentro.
    #
    # **Eram três traços horizontais**, e o crítico leu o ícone como "lista de texto" -- que é
    # exatamente o que três linhas paralelas ao lado de um retângulo desenham em qualquer outro
    # programa. Elas queriam dizer movimento e diziam parágrafo. Uma seta apontando para fora diz
    # o que elas queriam, e reusa a ponta que `desfazer` e `refazer` acabaram de ganhar.
    "limpar_tabuleiro": (
        Poli((10, 24), (54, 24), (54, 76), (10, 76), fechado=True),
        Poli((62, 50), (84, 50)),
        Poli((78, 38), (96, 50), (78, 62), fechado=True),
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


ICONES_DA_SALA: dict[str, tuple[Traco, ...]] = {
    # **Um segundo dicionário, e não mais chaves no primeiro** (S-527). A chave de `ICONES` é o
    # nome de um comando do catálogo, e `medidas_da_fita.grupos()` põe na fita da janela todo
    # comando que declare `icone` -- então um traço para "promover variante" entrando por lá poria
    # o botão no cromo da janela, ao lado de "Abrir PDF". Aqui a chave é o nome que
    # `ui/barra_da_sala.ACOES` declara, e a ponte nos dois sentidos é com aquela tabela.
    # Quatro ações da sala **reusam** traços de cima (`salvar`, `abrir_pdf`, `exportar_pgn`,
    # `aplicar_fen`): é o mesmo gesto noutra aba, e `imagem` procura nos dois dicionários.
    # ---------------------------------------------------------------------------- POSICAO
    # O tabuleiro de quatro casas do `ler_melhor` com a seta entrando: o que o OCR leu vem para cá.
    "carregar_ocr": (
        Poli((40, 18), (86, 18), (86, 82), (40, 82), fechado=True),
        Poli((40, 50), (86, 50)),
        Poli((63, 18), (63, 82)),
        Poli((6, 50), (30, 50)),
        Poli((20, 40), (30, 50), (20, 60)),
    ),
    # O tabuleiro com as duas fileiras de baixo marcadas: as peças no lugar de partida.
    "posicao_inicial": (
        Poli((18, 18), (82, 18), (82, 82), (18, 82), fechado=True),
        Poli((18, 50), (82, 50)),
        Poli((18, 66), (82, 66)),
    ),
    # Um olho: a sala **observa** o painel de resultado. As pálpebras são dois arcos da mesma
    # curva, espelhados, que se encontram nos cantos (12, 50) e (88, 50); a íris é um anel e não
    # um ponto, porque a 16 px o ponto era a única coisa que sobrava do desenho -- medido na
    # primeira versão, com pálpebras de meia largura.
    "seguir": (
        Arco((50, 60), 39.3, 194.7, 345.3),
        Arco((50, 40), 39.3, 14.7, 165.3),
        Arco((50, 50), 12),
    ),
    # Duas setas que dão a volta, uma em cada sentido: o tabuleiro gira.
    "virar": (
        Arco((50, 50), 30, 200, 340),
        Poli((66, 36), (78, 40), (80, 27)),
        Arco((50, 50), 30, 20, 160),
        Poli((34, 64), (22, 60), (20, 73)),
    ),
    # O disco dividido ao meio: brancas e pretas, e a vez passa de um lado ao outro.
    "trocar_vez": (Arco((50, 50), 30), Poli((50, 20), (50, 80))),
    # Duas folhas sobrepostas: copiar.
    "copiar": (
        Poli((14, 30), (58, 30), (58, 86), (14, 86), fechado=True),
        Poli((32, 30), (32, 14), (86, 14), (86, 68), (58, 68)),
    ),
    # --------------------------------------------------------------------------- VARIANTE
    # Seta para cima, seta para baixo, e a de cima com a barra: sobe um nível, desce um nível,
    # vai ao topo. Três desenhos da mesma família, porque são o mesmo gesto em três medidas.
    "promover": (Poli((50, 84), (50, 20)), Poli((30, 40), (50, 20), (70, 40))),
    "rebaixar": (Poli((50, 16), (50, 80)), Poli((30, 60), (50, 80), (70, 60))),
    "principal": (Poli((26, 12), (74, 12)), Poli((50, 86), (50, 28)), Poli((30, 48), (50, 28), (70, 48))),
    # A lixeira: a variante inteira vai embora.
    "apagar_variante": (
        Poli((22, 28), (78, 28)),
        Poli((40, 28), (40, 18), (60, 18), (60, 28)),
        Poli((28, 28), (32, 84), (68, 84), (72, 28)),
    ),
    # A linha que segue até um X: daqui em diante, nada.
    "apagar_daqui": (Poli((10, 50), (50, 50)), Poli((60, 36), (88, 64)), Poli((88, 36), (60, 64))),
    # O ponto de exclamação -- o símbolo de lance que todo mundo reconhece primeiro. A haste vai
    # de 10 a 62 e o ponto é um **quadradinho fechado** de 8 unidades: a 16 px ele sai como um
    # bloco cheio de 3 px. Um `Arco` de raio menor que o traço não fica cheio na Pillow -- sai um
    # anel quebrado a meio-tom, e foi assim que o crítico da S-527 viu o "!" na pele "Foco".
    "simbolo": (Poli((50, 10), (50, 62)), Poli((46, 80), (54, 80), (54, 88), (46, 88), fechado=True)),
    # Dois ângulos que se fecham um contra o outro: dobrar.
    "dobrar": (Poli((30, 26), (50, 42), (70, 26)), Poli((30, 74), (50, 58), (70, 74))),
    # ------------------------------------------------------------------------------ LIVRO
    # A moldura com a paisagem dentro: uma imagem, que é o que o recorte é.
    "recorte": (
        Poli((14, 20), (86, 20), (86, 80), (14, 80), fechado=True),
        Poli((22, 72), (42, 46), (56, 62), (66, 52), (78, 72)),
    ),
    # O livro aberto, com a lombada no meio.
    "livro": (
        Poli((50, 26), (50, 84)),
        Poli((50, 26), (30, 18), (12, 24), (12, 80), (30, 74), (50, 84)),
        Poli((50, 26), (70, 18), (88, 24), (88, 80), (70, 74), (50, 84)),
    ),
    # A folha do `ler_pagina` com a seta dentro: ir até ela.
    "ver_a_pagina": (
        Poli((26, 10), (74, 10), (74, 90), (26, 90), fechado=True),
        Poli((36, 50), (62, 50)),
        Poli((52, 40), (62, 50), (52, 60)),
    ),
    # ------------------------------------------------------------------------------- BASE
    # A tabela de três linhas: a lista de partidas.
    "partidas": (
        Poli((16, 20), (84, 20), (84, 80), (16, 80), fechado=True),
        Poli((16, 40), (84, 40)),
        Poli((16, 60), (84, 60)),
    ),
    # A árvore de aberturas (S-535): o tronco que se abre em dois ramos, com um nó em cada ponta.
    # De baixo para cima porque é assim que ela cresce na tela -- a posição corrente embaixo, os
    # lances que saem dela acima. Não é a tabela de "partidas": ali a resposta é uma lista, aqui
    # é uma bifurcação, e é a bifurcação que o traço tem de dizer.
    "arvore": (
        Poli((10, 26), (36, 26)),
        Poli((64, 26), (90, 26)),
        Poli((23, 26), (23, 56)),
        Poli((77, 26), (77, 56)),
        Poli((23, 56), (77, 56)),
        Poli((50, 56), (50, 86)),
        Poli((30, 86), (70, 86)),
    ),
    # O índice da base (S-532/S-527): a tabela de partidas com a lupa por cima -- é o que o índice
    # faz, tornar a tabela procurável por nome.
    "indexar": (
        Poli((10, 18), (70, 18), (70, 50)),
        Poli((10, 18), (10, 82), (46, 82)),
        Poli((10, 38), (70, 38)),
        Poli((10, 58), (44, 58)),
        Arco((64, 66), 14),
        Poli((74, 76), (90, 92)),
    ),
    # O funil: a busca por filtros combinados (S-533). Não é outra lupa de propósito -- "indexar"
    # já tem uma, e dois traços com a mesma lupa no mesmo grupo Base seriam dois botões que o olho
    # não separa. Funil é o que a barra de qualquer base de dados usa para "filtre isto".
    "filtrar": (
        Poli((8, 14), (92, 14), (58, 54), (58, 92), (42, 80), (42, 54), fechado=True),
    ),
    # A prancheta: colar o que está na área de transferência.
    "colar": (
        Poli((22, 22), (78, 22), (78, 88), (22, 88), fechado=True),
        Poli((38, 22), (38, 12), (62, 12), (62, 22)),
        Poli((34, 50), (66, 50)),
        Poli((34, 66), (66, 66)),
    ),
    # ------------------------------------------------------------------------------ MOTOR
    # O raio: o motor. A lupa sem sinal é analisar uma vez; o raio com a seta é a linha dele
    # entrando na árvore.
    "motor": (Poli((58, 10), (30, 54), (50, 54), (42, 90), (70, 46), (50, 46), (58, 10)),),
    "lupa": (Arco((44, 44), 28), Poli((64, 64), (88, 88))),
    "linha_do_motor": (
        Poli((46, 10), (22, 50), (40, 50), (34, 84)),
        Poli((56, 62), (90, 62)),
        Poli((80, 52), (90, 62), (80, 72)),
    ),
    # Os dois eixos e a curva que sobe e cai: o gráfico de avaliação da partida inteira (S-537).
    # A curva **cruza** o meio da caixa de propósito -- é o que a análise de uma partida mostra, e
    # uma curva só ascendente seria o ícone de "crescimento" de qualquer painel de negócio.
    "grafico": (
        Poli((12, 10), (12, 88), (92, 88)),
        Poli((22, 62), (40, 34), (58, 68), (86, 24)),
    ),
    # Três cursores de régua: as opções do motor (S-536). Não é a engrenagem porque a engrenagem a
    # 16 px vira um borrão redondo -- é o que a S-527 mediu no "mais" com anéis de raio 5 --, e
    # porque o que este comando abre **são** quatro números com faixa mínima e máxima.
    "ajustes": (
        Poli((10, 24), (90, 24)),
        Poli((10, 50), (90, 50)),
        Poli((10, 76), (90, 76)),
        Poli((28, 16), (36, 16), (36, 32), (28, 32), fechado=True),
        Poli((62, 42), (70, 42), (70, 58), (62, 58), fechado=True),
        Poli((40, 68), (48, 68), (48, 84), (40, 84), fechado=True),
    ),
    # --------------------------------------------------------------------------- EXPORTAR
    # Linhas de texto e a seta saindo para a direita: a linha do estudo vai para a aba Texto.
    "para_o_texto": (
        Poli((12, 26), (60, 26)),
        Poli((12, 42), (60, 42)),
        Poli((12, 58), (44, 58)),
        Poli((58, 74), (88, 74)),
        Poli((78, 64), (88, 74), (78, 84)),
    ),
    # A impressora: o corpo no meio, a folha entrando por cima e a folha saindo por baixo (S-545).
    # É o desenho que todo programa usa há trinta anos, e reconhecê-lo é o ponto -- um ícone de
    # imprimir que precise de legenda já perdeu para o item de menu.
    "imprimir": (
        Poli((10, 40), (90, 40), (90, 72), (10, 72), fechado=True),
        Poli((28, 40), (28, 10), (72, 10), (72, 40)),
        Poli((28, 72), (28, 92), (72, 92), (72, 72)),
    ),
    # Dois tabuleiros empilhados, um atrás do outro (S-544): o lote é o **mesmo** diagrama muitas
    # vezes, e a pilha é como se desenha "vários" sem contar quantos. A cruz só no da frente
    # porque duas cruzes a 16 px viram uma trama, e a trama deixa de ler como tabuleiro.
    "diagramas_em_lote": (
        Poli((10, 10), (64, 10), (64, 64), (10, 64), fechado=True),
        Poli((36, 36), (90, 36), (90, 90), (36, 90), fechado=True),
        Poli((36, 63), (90, 63)),
        Poli((63, 36), (63, 90)),
    ),
    # ----------------------------------------------------------------------------- TREINO
    # O alvo: três anéis.
    "treinar": (Arco((50, 50), 34), Arco((50, 50), 18), Arco((50, 50), 4)),
    # A folha do livro com a seta saindo dela: o exercício sai do livro (S-539). O alvo já é o
    # "treinar" acima, e repeti-lo aqui daria dois botões vizinhos com o mesmo desenho.
    "extrair_taticas": (
        Poli((16, 14), (58, 14), (58, 86), (16, 86), fechado=True),
        Poli((26, 34), (48, 34)),
        Poli((26, 54), (48, 54)),
        Poli((64, 62), (94, 62)),
        Poli((82, 48), (94, 62), (82, 76)),
    ),
    # O calendário da agenda do dia (S-540): a folha, a faixa do cabeçalho e os dois ganchos. É o
    # traço que qualquer programa de repetição espaçada usa, e reconhecê-lo é metade do rótulo.
    "agenda": (
        Poli((12, 26), (88, 26), (88, 90), (12, 90), fechado=True),
        Poli((12, 46), (88, 46)),
        Poli((32, 12), (32, 36)),
        Poli((68, 12), (68, 36)),
    ),
    # ------------------------------------------------------------------- CABECALHO (S-530)
    # O lápis: a haste na diagonal, a ponta triangular embaixo e a virola perto do topo. Ele abre
    # o cabeçalho da partida, que **não é comando do catálogo** -- por isso a chave é o nome que
    # `cabecalho_da_partida.ICONE` declara, e não o de um comando que não existe.
    "editar_cabecalho": (
        Poli((30, 70), (70, 30)),
        Poli((12, 88), (26, 58), (42, 74), fechado=True),
        Poli((60, 20), (80, 40)),
    ),
    # ------------------------------------------------------------------------------- MAIS
    # Três pontos: o que não coube. Quadradinhos fechados (ver "simbolo") e nos cantos da caixa: a
    # primeira versão eram anéis de raio 5 a 22/50/78, e saía com 6 px de altura e nenhum pixel
    # forte a 16 px -- "meio-tom", nas palavras do crítico da S-527.
    "mais": tuple(
        Poli((x - 4, 46), (x + 4, 46), (x + 4, 54), (x - 4, 54), fechado=True) for x in (14, 50, 86)
    ),
}
"""Os vinte e cinco traços da barra da sala (S-527), com a chave que `ui/barra_da_sala.ACOES` pede.

Com os quatro reusados de `ICONES` são vinte e nove nomes para trinta e uma ações: os três formatos
de exportação moram dentro do agrupador e não têm botão, logo não têm traço."""


ICONES_DO_PDF: dict[str, tuple[Traco, ...]] = {
    # **O terceiro dicionário, e pela razão do segundo** (S-528). A chave de `ICONES` é o nome de
    # um comando do catálogo, e `medidas_da_fita.grupos()` põe na fita da janela todo comando que
    # declare `icone` -- então dar traço a "Tirar a caixa" por lá o poria no cromo da janela. Aqui
    # a chave é o nome que `ui/barra_do_pdf.ACOES` declara.
    #
    # **Nove das dezesseis ações do painel reusam traço de `ICONES`** -- `abrir_pdf`, `ler_melhor`,
    # `ler_pagina`, `exportar_pgn`, `zoom_mais`, `zoom_menos`, `ajustar_largura`, `ajustar_pagina`
    # e `selecionar_area` --, e é o esperado: aqueles ícones foram desenhados na S-220 para estes
    # mesmos comandos. Os sete abaixo são os que faltavam.
    # ----------------------------------------------------------------------------- LIVRO
    # Janela do sistema com a seta saindo por cima: o livro sai daqui e abre lá fora.
    "leitor": (
        Poli((12, 26), (56, 26), (56, 84), (12, 84), fechado=True),
        Poli((46, 54), (86, 14)),
        Poli((62, 14), (88, 14), (88, 40)),
    ),
    # O círculo cortado: o "não" universal, e é o que cancela a exportação em curso.
    "cancelar": (Arco((50, 50), 36), Poli((25, 25), (75, 75))),
    # ---------------------------------------------------------------------------- PAGINA
    # A folha que fica e a seta para ela: a barra é a borda da folha, o "V" é o sentido.
    "folha_anterior": (Poli((18, 14), (18, 86)), Poli((74, 14), (38, 50), (74, 86))),
    "folha_seguinte": (Poli((82, 14), (82, 86)), Poli((26, 14), (62, 50), (26, 86))),
    # ----------------------------------------------------------------------------- VISTA
    # A caixa **com a etiqueta do número**: é o que a marcação desenha na página (S-68), e é o que
    # a distingue dos vizinhos. Os quatro cantos já são `selecionar_area` e a moldura dentro de
    # moldura já é `ajustar_pagina` -- os três ficam na mesma fila, e dois ícones iguais lado a
    # lado é o mesmo defeito que dois rótulos iguais.
    "marcar": (
        Poli((24, 28), (90, 28), (90, 84), (24, 84), fechado=True),
        Poli((8, 12), (36, 12), (36, 36), (8, 36), fechado=True),
    ),
    # O corpo do mouse com a rodinha: o gesto é da roda, e não da página.
    "roda": (
        Poli((28, 16), (72, 16), (72, 84), (28, 84), fechado=True),
        Poli((50, 26), (50, 46)),
    ),
    # ---------------------------------------------------------------------------- LEITURA
    # A caixa do diagrama e o X que a tira. O X fica **fora** da caixa, no canto: por cima dela
    # ele vira um risco no meio de um retângulo, que a 16 px é uma mancha.
    "tirar_a_caixa": (
        Poli((10, 22), (64, 22), (64, 76), (10, 76), fechado=True),
        Poli((58, 58), (92, 92)),
        Poli((92, 58), (58, 92)),
    ),
}
"""Os sete traços que o painel do PDF pedia e não existiam (S-528), com a chave que
`ui/barra_do_pdf.ACOES` declara. A ponte nos dois sentidos é com aquela tabela."""


ICONES_DO_RESULTADO: dict[str, tuple[Traco, ...]] = {
    # **O quarto dicionário, e pela razão do segundo e do terceiro** (S-528, terceira barra). A
    # chave de `ICONES` é o nome de um comando do catálogo, e `medidas_da_fita.grupos()` põe na
    # fita da janela todo comando que declare `icone` -- dar traço a "Salvar todos" por lá o poria
    # no cromo da janela, ao lado de "Abrir PDF". Aqui a chave é o nome que
    # `ui/barra_do_resultado.ACOES` declara.
    #
    # **Oito das dez ações do painel reusam traço de cima** -- `diagrama_anterior`,
    # `proximo_diagrama`, `aplicar_fen`, `desfazer`, `refazer`, `limpar_tabuleiro`, `salvar` e
    # `copiar` (este de `ICONES_DA_SALA`) --, e é o esperado: são os mesmos gestos. Os dois abaixo
    # são os que faltavam.
    # ----------------------------------------------------------------------------- GRAVAR
    # Dois disquetes empilhados: o de trás aparece só pelo canto, que é o que diz "e os outros".
    "salvar_todos": (
        Poli((30, 12), (86, 12), (86, 68)),
        Poli((12, 30), (58, 30), (72, 44), (72, 88), (12, 88), fechado=True),
        Poli((28, 30), (28, 50), (56, 50), (56, 30)),
    ),
    # ------------------------------------------------------------------------------ VISTA
    # O tabuleiro de quatro casas com uma delas hachurada: a tinta de dúvida por baixo da peça.
    "mapa_de_incerteza": (
        Poli((14, 14), (86, 14), (86, 86), (14, 86), fechado=True),
        Poli((50, 14), (50, 86)),
        Poli((14, 50), (86, 50)),
        Poli((20, 44), (44, 20)),
        Poli((20, 28), (28, 20)),
        Poli((36, 44), (44, 36)),
    ),
}
"""Os dois traços que o painel de Resultado pedia e não existiam (S-528, terceira barra), com a
chave que `ui/barra_do_resultado.ACOES` declara. A ponte nos dois sentidos é com aquela tabela."""


def tracos_de(nome: str) -> tuple[Traco, ...] | None:
    """Os traços daquele nome, procurando nos quatro dicionários. `None` para nome que não existe."""
    return ICONES.get(nome) or ICONES_DA_SALA.get(nome) or ICONES_DO_PDF.get(nome) or ICONES_DO_RESULTADO.get(nome)


SUPERAMOSTRA = 4
"""Fator de desenho antes de reduzir. A Pillow não suaviza traço, e a redução é que suaviza.

Sem isto o traço diagonal do "aplicar_fen" a 20 px vira escada, e o círculo da lupa vira um
octógono -- num tamanho em que o ícone é a única coisa que a pessoa lê no botão."""

TRACO_MINIMO = 2
"""O traço nunca sai com menos de dois pixels, qualquer que seja o lado (S-527).

A 16 px os 9% dão 1,44 px, e um traço de um pixel e meio raramente cai inteiro num pixel: ele se
reparte entre dois vizinhos e os dois saem cinza -- medido no ícone "mais" da barra da sala, que a
16 px não tinha **nenhum** pixel forte. Dois pixels cobrem ao menos uma coluna (ou linha) inteira em
qualquer posição, e é isso que devolve o preto ao traço. Acima de ~22 px os 9% já passam de dois e
o piso não muda nada."""


def _largura_do_traco(lado: int) -> int:
    """A espessura em pixels **supersamostrados**: os 9% do lado, nunca abaixo do piso de dois pixels
    reais (`TRACO_MINIMO * SUPERAMOSTRA`)."""
    return max(TRACO_MINIMO * SUPERAMOSTRA, round(lado * TRACO_RELATIVO))


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
    #
    # **E a grade vale para os quatro dicionários de comando** que `tracos_de` percorre: as barras
    # em fila da sala, do PDF e do Resultado (S-527/S-528) misturam traço reusado de `ICONES` com
    # traço próprio na mesma fila, e só um dos dois na grade seria o vizinho 27 % maior que ela
    # veio tirar.
    tracos = tracos_de(nome)
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
