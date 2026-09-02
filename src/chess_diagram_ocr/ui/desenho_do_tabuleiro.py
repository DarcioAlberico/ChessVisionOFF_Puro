"""Onde o tabuleiro fica e de que cor a casa fala -- sem toolkit e sem imagem (S-155/S-501).

A margem que as coordenadas exigem, a fonte e o deslocamento delas, a proporção da seta, a rampa
de calor da confiança por casa e a geometria de `BoardGeometry`. Tudo cálculo -- e `BoardGeometry`
já dizia, no próprio docstring, que era "puro cálculo, testável sem Tk".

**As cores saíram na S-511, e não é perda:** elas nunca foram daqui. Este módulo tinha doze
apelidos `X = tokens.RESERVA[Y]`, que davam **cor literal** ao `tk.Canvas` porque ele não conhece
papel. O Qt pergunta ao tema, e os doze ficaram sem um único uso -- ver o comentário abaixo do
`__all__`.

**Por que isso não bastava, e é o item.** O cálculo era puro e morava num arquivo que importa
`tkinter` **e** `PIL.ImageTk` na primeira linha, porque o mesmo arquivo tem o `BoardRenderer`,
que pinta num `tk.Canvas`. O efeito estava escrito, com todas as letras, no cabeçalho de
`qt/tabuleiro.py`:

    `ui/board_render.py` tem duas coisas que este arquivo gostaria: `BoardGeometry.fit` e
    `heatmap_color`. As duas são cálculo puro -- e mesmo assim não dá para importá-las, porque o
    módulo em que moram importa `tkinter` e `PIL` na primeira linha. É o único ponto do fluxo em
    que o segundo frontend teve de repetir uma decisão em vez de chamá-la.

Era o único, e deixou de ser. O tabuleiro do Qt passou a **chamar** as duas, e a incerteza por
casa voltou a ser a mesma rampa nas duas janelas em vez de calor numa e contorno na outra.

**O que ficou de fora, e a fronteira é essa.** As tags de item do `tk.Canvas` (`DRAG_TAG` e as
cinco irmãs) continuam em `ui/board_render.py`: elas nomeiam o que apagar antes de redesenhar, e
um renderizador de Qt não tem tag nenhuma -- estariam aqui descrevendo um toolkit, num módulo que
existe para não conhecer nenhum. `engrossar_traco` também fica lá, porque é PIL.

`ui/board_render.py` reexportava tudo o que está aqui, e saiu no corte do Tk (S-506). Quem desenha
agora é `qt/tabuleiro.py`, `qt/tabuleiro_editavel.py` e `qt/tabuleiro_de_jogo.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import UNCERTAIN_SQUARE_THRESHOLD
from . import tokens

__all__ = [
    "BoardGeometry",
    "COORD_FONT",
    "COORD_OFFSET_PX",
    "LARGURA_DA_SETA",
    "LARGURA_DO_CIRCULO",
    "PAPEL_DE_SETA",
    "PONTA_DA_SETA",
    "UNICODE_PIECES",
    "heatmap_color",
    "margem_de_coordenada",
    "reguas",
]

# **Doze apelidos `X = tokens.RESERVA[Y]` saíram daqui na S-511**, e o motivo é o mesmo para os
# doze: eles existiam para dar **cor literal** ao `tk.Canvas`, que não conhece papel. No Qt a cor
# vem sempre de `tema.cor_atual(papel)`, então o apelido perdeu a função junto com o toolkit --
# medido em 2026-09-01, os doze tinham zero uso em `src/` e zero em `tests/`. Os papéis continuam
# em `ui/tokens.py`, que é onde eles sempre moraram; o que saiu foi a segunda forma de nomeá-los.
#
# Eram: `GLIFO_CLARO`, `GLIFO_ESCURO`, `LIGHT_SQUARE`, `DARK_SQUARE`, `SELECTION_OUTLINE`,
# `LAST_MOVE_SQUARE`, `TARGET_MARK`, `CHANGED_OUTLINE`, `PROBLEM_OUTLINE`, `DISPUTED_OUTLINE`,
# `BOARD_FRAME` e `COORDINATE_TEXT`.

COORD_FONT = ("Segoe UI", 9, "bold")
"""A fonte das letras a–h e dos números 8–1. Um lugar só, porque a margem sai dela (S-155)."""

COORD_OFFSET_PX = 11
"""Quanto o texto da coordenada fica **fora** do tabuleiro, do centro do texto até a borda."""

def reguas(virado: bool) -> tuple[str, str]:
    """As duas réguas na ordem em que se desenham: `(colunas, linhas)` (S-508).

    Com as brancas embaixo, `a` fica à esquerda e `8` no topo; virado, os dois invertem. É uma
    linha de decisão, e ela mora aqui pelo motivo de sempre -- **para ser afirmável sem janela**.

    E aqui há um motivo a mais, que é de bancada: a plataforma `offscreen` da suíte não tem fonte
    nenhuma, então `a` e `h` desenham o mesmo retângulo. Um teste que comparasse o pixel das duas
    réguas passaria em verde com a ordem trocada -- que é exatamente o tipo de guarda vácua que o
    corte do Tk deixou para trás.
    """
    return ("hgfedcba", "12345678") if virado else ("abcdefgh", "87654321")

def margem_de_coordenada(offset: int = COORD_OFFSET_PX, altura_da_fonte: int = COORD_FONT[1]) -> int:
    """A margem que o canvas precisa reservar para as coordenadas caberem inteiras (S-155).

    **O defeito que isto conserta.** `_draw_coordinates` desenha as letras em
    `origin_y + size + 11`, texto centrado de 9 pt em negrito -- precisa de ~18 px abaixo do
    tabuleiro. O chamador reservava `margin=28`, que `BoardGeometry.fit` divide entre os dois
    lados: **14 px**. A base de "a b c d e f g h" era cortada, e isso valia para os **dois**
    tabuleiros da janela.

    Os dois números estavam soltos em arquivos diferentes -- o `11` aqui, o `28` no
    `board_widget` -- e nada os ligava. Agora um sai do outro: `2 × (deslocamento + meia
    altura)`, arredondado para cima, com folga de 1 px para o antialias da fonte.
    """
    return 2 * (offset + (altura_da_fonte + 1) // 2 + 1)

HEATMAP_LOW = (0xF2, 0xC7, 0x44)
"""Amarelo: casa logo abaixo do limiar."""

HEATMAP_HIGH = (0xD6, 0x45, 0x45)
"""Vermelho: casa em que o modelo praticamente não tem opinião."""

UNICODE_PIECES = {
    "P": "♙",
    "N": "♘",
    "B": "♗",
    "R": "♖",
    "Q": "♕",
    "K": "♔",
    "p": "♟",
    "n": "♞",
    "b": "♝",
    "r": "♜",
    "q": "♛",
    "k": "♚",
}

PAPEL_DE_SETA: dict[str, str] = {
    "green": tokens.SETA_VERDE,
    "red": tokens.SETA_VERMELHA,
    "blue": tokens.SETA_AZUL,
    "yellow": tokens.SETA_AMARELA,
}
"""A cor do padrão `[%cal]` traduzida em papel de `ui/tokens.py`.

O modelo guarda `"green"` porque é o que o PGN sabe escrever; o desenho pergunta ao tema. Cor
desconhecida cai no verde, que é exatamente o que `chess.svg.Arrow.pgn` faz ao gravar."""

LARGURA_DA_SETA = 0.16
"""Espessura da haste, em fração da casa. A ponta é `FATOR_DA_PONTA` vezes isso."""

FATOR_DA_PONTA = 2.6
"""Quantas vezes a ponta é mais larga que a haste.

Estava só na prosa de `LARGURA_DA_SETA`, e o desenho do Qt tinha um segundo literal (`0.34`) que
não saía dela -- duas fontes para a mesma proporção, que é a família de defeito da S-145. Agora a
ponta é derivada, e mudar a haste move as duas juntas."""

PONTA_DA_SETA = LARGURA_DA_SETA * FATOR_DA_PONTA
"""Largura da ponta, em fração da casa. Derivada, e não um segundo número."""

LARGURA_DO_CIRCULO = 0.055
"""Espessura do anel da casa marcada, em fração da casa."""

def heatmap_color(confidence: float, threshold: float = UNCERTAIN_SQUARE_THRESHOLD) -> str:
    """Cor da casa em função da confiança: amarelo no limiar, vermelho no chão.

    A escala é relativa ao limiar e não a 0..1 porque a faixa que interessa é estreita:
    medido, casa certa fica em ~0,999 e casa errada em ~0,75. Espalhar a rampa por 0..1
    deixaria todo o erro na mesma tonalidade.
    """
    span = max(threshold, 1e-6)
    ratio = 1.0 - max(0.0, min(1.0, confidence / span))
    red, green, blue = (
        int(low + (high - low) * ratio) for low, high in zip(HEATMAP_LOW, HEATMAP_HIGH, strict=True)
    )
    return f"#{red:02x}{green:02x}{blue:02x}"

@dataclass(frozen=True)
class BoardGeometry:
    """Onde o tabuleiro está no canvas. Puro cálculo, testável sem Tk."""

    origin_x: float
    origin_y: float
    size: float
    cell: float

    @classmethod
    def fit(cls, width: float, height: float, *, min_size: int, max_size: int, margin: int) -> BoardGeometry:
        """O tabuleiro centrado no canvas, e **nunca maior que ele** (S-155).

        O `max(min_size, ...)` sozinho ganhava quando o canvas era menor que `min_size`, e o
        tabuleiro vazava para fora em vez de encolher. Não há tamanho em que desenhar fora do
        canvas seja a resposta certa: abaixo do mínimo, o limite passa a ser o canvas, e quem
        chama sabe que está no limite porque o tamanho devolvido é menor que `min_size`.
        """
        desejado = max(min_size, min(width - margin, height - margin, max_size))
        cabe = max(1.0, min(float(width), float(height)))
        size = min(desejado, cabe)
        return cls(origin_x=(width - size) / 2, origin_y=(height - size) / 2, size=size, cell=size / 8)

    def rect(self, row: int, col: int) -> tuple[float, float, float, float]:
        x0 = self.origin_x + col * self.cell
        y0 = self.origin_y + row * self.cell
        return x0, y0, x0 + self.cell, y0 + self.cell

    def display_at(self, x: float, y: float) -> tuple[int, int] | None:
        """(linha, coluna) sob o ponteiro, ou `None` fora do tabuleiro."""
        if not (self.origin_x <= x < self.origin_x + self.size and self.origin_y <= y < self.origin_y + self.size):
            return None
        col = int((x - self.origin_x) // self.cell)
        row = int((y - self.origin_y) // self.cell)
        return (row, col) if 0 <= row <= 7 and 0 <= col <= 7 else None
