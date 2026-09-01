"""O desenho derivado do conjunto "traço grosso" (S-230/S-506). Puro: PIL, e nada de toolkit.

**Ele voltou porque o conjunto de peças voltou.** `engrossar_traco` morava em
`ui/board_render.py`, que saiu inteiro no corte do Tk (S-506) -- e com ele a única implementação
do que `conjuntos.TRACO` significa. O registro dos três conjuntos sobreviveu em `ui/conjuntos.py`,
declarando uma aparência que nada mais sabia desenhar: exatamente o estado que
`menu.montar` recusa desde a S-161, com o defeito escondido um nível abaixo do menu.

**Aqui e não em `qt/tabuleiro.py`** pela regra de sempre: isto é decisão medida -- o limiar de
luminância e o raio da dilatação -- e não desenho de widget. Um segundo frontend, ou o dia em que
a Galeria quiser as peças engrossadas, chama a mesma função em vez de reencontrar o número.
"""

from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter

__all__ = ["LIMIAR_DE_TRACO", "engrossar_traco"]

LIMIAR_DE_TRACO = 160
"""Abaixo de que luminância um pixel conta como **traço** e não como miolo, ao engrossar (S-230).

160 de 255, e não 128: as peças brancas destes PNGs têm o contorno em preto puro sobre um miolo
branco puro, e a antialiasing da redução produz cinzas intermediários -- um limiar no meio da
escala deixaria de fora justamente a borda que a redução acabou de esmaecer, que é a parte que o
conjunto de traço grosso existe para recuperar."""


def engrossar_traco(imagem: Image.Image) -> Image.Image:
    """O mesmo desenho com a linha escura um pixel mais grossa (S-230). Puro sobre a imagem.

    **Derivado, e não redesenhado.** A 20-24 px -- que é como a paleta de edição e a Galeria
    desenham as peças -- a redução apaga o contorno fino, e as seis peças brancas viram manchas
    parecidas entre si. Engrossar **depois** de reduzir devolve a linha no tamanho em que ela é
    exibida, que é onde o problema está; engrossar antes seria engrossá-la na fonte e perdê-la de
    novo na mesma redução.

    O que ele dilata é a máscara de traço, e não a peça: o miolo claro fica onde está, e o que
    cresce é a borda escura para dentro e para fora dela.
    """
    rgba = imagem.convert("RGBA")
    alfa = rgba.getchannel("A")
    luz = rgba.convert("L")
    # `MinFilter` e não `MaxFilter`: a máscara é clara onde o pixel é **escuro**, e dilatar o
    # escuro numa imagem em `L` é tomar o mínimo da vizinhança.
    escuro = luz.point(lambda valor: 255 if valor < LIMIAR_DE_TRACO else 0)
    dentro = ImageChops.multiply(escuro, alfa.point(lambda valor: 255 if valor > 128 else 0))
    grosso = dentro.filter(ImageFilter.MaxFilter(3))
    tinta = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    saida = rgba.copy()
    saida.paste(tinta, (0, 0), grosso)
    return saida
