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

from PIL import Image, ImageDraw, ImageTk

logger = logging.getLogger(__name__)

__all__ = ["ICONES", "Arco", "Poli", "TRACO_RELATIVO", "cache_de_icones", "icone", "imagem", "limpar_cache"]

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
        Poli((26, 10), (74, 10), (74, 90), (26, 90), fechado=True),
        Poli((12, 50), (88, 50)),
    ),
    # Tabuleiro de quatro casas: ler **um diagrama**. O objeto é outro, e a 16 px é a diferença
    # entre os dois que se enxerga primeiro -- folha alta contra quadrado dividido.
    "ler_melhor": (
        Poli((18, 18), (82, 18), (82, 82), (18, 82), fechado=True),
        Poli((18, 50), (82, 50)),
        Poli((50, 18), (50, 82)),
    ),
    # Os quatro cantos do recorte, que é o gesto que o comando pede.
    "selecionar_area": (
        Poli((14, 34), (14, 14), (34, 14)),
        Poli((66, 14), (86, 14), (86, 34)),
        Poli((86, 66), (86, 86), (66, 86)),
        Poli((34, 86), (14, 86), (14, 66)),
    ),
    # ----------------------------------------------------------------------------- EDICAO
    "aplicar_fen": (Poli((18, 52), (40, 76), (82, 24)),),
    # Casa com o X dentro: o que se apaga é a peça **daquela casa**, e não a posição toda.
    "apagar_casa": (
        Poli((16, 16), (84, 16), (84, 84), (16, 84), fechado=True),
        Poli((34, 34), (66, 66)),
        Poli((66, 34), (34, 66)),
    ),
    "diagrama_anterior": (Poli((62, 18), (30, 50), (62, 82)),),
    "proximo_diagrama": (Poli((38, 18), (70, 50), (38, 82)),),
    # A seta que dá a volta por cima e desce na ponta -- os dois são a mesma forma espelhada, e
    # desenhá-los diferentes seria dizer que não são o mesmo gesto em sentidos opostos. O arco vai
    # de 180 a 360 porque na Pillow o ângulo cresce no sentido horário com o eixo `y` para baixo:
    # 180 é a esquerda, 270 é o **topo**, 360 é a direita.
    "desfazer": (
        Arco((50, 58), 28, 180, 360),
        Poli((10, 42), (22, 58), (34, 42)),
    ),
    "refazer": (
        Arco((50, 58), 28, 180, 360),
        Poli((66, 42), (78, 58), (90, 42)),
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
        Poli((10, 22), (10, 78)),
        Poli((90, 22), (90, 78)),
        Poli((26, 50), (74, 50)),
        Poli((36, 40), (26, 50), (36, 60)),
        Poli((64, 40), (74, 50), (64, 60)),
    ),
    # A folha inteira dentro da moldura: o enquadramento de escolher qual diagrama abrir.
    "ajustar_pagina": (
        Poli((10, 18), (90, 18), (90, 82), (10, 82), fechado=True),
        Poli((34, 30), (66, 30), (66, 70), (34, 70), fechado=True),
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
    tracos = ICONES.get(nome)
    if tracos is None:
        logger.warning("Ícone desconhecido: %r. O botão fica só com o texto.", nome)
        return None

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
    if desenho is None:
        return None

    foto = ImageTk.PhotoImage(desenho)
    _cache[chave] = foto
    return foto


def cache_de_icones() -> int:
    """Quantos ícones estão desenhados agora. Para teste e para depurar consumo."""
    return len(_cache)


def limpar_cache() -> None:
    """Esquece o que foi desenhado. A troca de pele (S-222) chama isto: a cor mudou."""
    _cache.clear()
