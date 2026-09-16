"""Onde o tabuleiro fica e de que cor a casa fala -- sem toolkit e sem imagem (S-155/S-501).

As cores dos papéis do tabuleiro, a margem que as coordenadas exigem, a rampa de calor da
confiança por casa e a geometria de `BoardGeometry`. Tudo cálculo -- e `BoardGeometry` já dizia,
no próprio docstring, que era "puro cálculo, testável sem Tk".

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
    "BOARD_FRAME",
    "BoardGeometry",
    "CHANGED_OUTLINE",
    "COORDINATE_TEXT",
    "COORD_FONT",
    "COORD_OFFSET_PX",
    "DARK_SQUARE",
    "GLIFO_CLARO",
    "GLIFO_ESCURO",
    "DISPUTED_OUTLINE",
    "HEATMAP_HIGH",
    "HEATMAP_LOW",
    "LARGURA_DA_SETA",
    "LARGURA_DO_CIRCULO",
    "LAST_MOVE_SQUARE",
    "LIGHT_SQUARE",
    "PAPEL_DE_SETA",
    "PROBLEM_OUTLINE",
    "SELECTION_OUTLINE",
    "TARGET_MARK",
    "UNICODE_PIECES",
    "heatmap_color",
    "margem_de_coordenada",
]

GLIFO_CLARO = tokens.RESERVA[tokens.GLIFO_CLARO]

GLIFO_ESCURO = tokens.RESERVA[tokens.GLIFO_ESCURO]

LIGHT_SQUARE = tokens.RESERVA[tokens.CASA_CLARA]

DARK_SQUARE = tokens.RESERVA[tokens.CASA_ESCURA]

SELECTION_OUTLINE = tokens.RESERVA[tokens.CONTORNO_DE_SELECAO]
"""A casa selecionada: um anel, e não uma cor de fundo (S-160)."""

LAST_MOVE_SQUARE = tokens.RESERVA[tokens.CASA_ULTIMO_LANCE]

TARGET_MARK = tokens.RESERVA[tokens.ALVO]

CHANGED_OUTLINE = tokens.RESERVA[tokens.CORRIGIDO]

PROBLEM_OUTLINE = tokens.RESERVA[tokens.PROBLEMA]

DISPUTED_OUTLINE = tokens.RESERVA[tokens.DIVERGENTE]
"""Roxo: as duas leituras discordam desta casa (S-66).

Cor própria, e não o vermelho da ilegalidade nem o azul da decodificação: as três dizem
coisas diferentes e podem acender juntas. "Ilegal" é um fato sobre a posição, "reescrita" é
algo que já aconteceu, e "em disputa" é um pedido -- olhe esta casa."""

BOARD_FRAME = tokens.RESERVA[tokens.MOLDURA]
"""A reserva da moldura. O desenho resolve contra o tema em uso -- ver `_cor_de_moldura`."""

COORDINATE_TEXT = tokens.RESERVA[tokens.COORDENADA]

COORD_FONT = ("Segoe UI", 9, "bold")
"""A fonte das letras a–h e dos números 8–1. Um lugar só, porque a margem sai dela (S-155)."""

COORD_OFFSET_PX = 11
"""Quanto o texto da coordenada fica **fora** do tabuleiro, do centro do texto até a borda."""

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
"""Espessura da haste, em fração da casa. A ponta é 2,6 vezes isso."""

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


def largura_util_do_canvas(altura: int, disponivel: int) -> int:
    """A largura que o canvas de um tabuleiro toma: **nunca mais do que ele desenha** (F9-C3).

    **O item 13, e a resposta que o ciclo 2 não deu.** O tabuleiro é quadrado e centrado, então um
    canvas mais largo que alto é, por construção, dois vãos vazios -- e o do painel Resultado
    media `933×559` para desenhar um tabuleiro de `551`: **58,2 % de ocupação**, com
    `180×580 = 104,4 kpx a 0,17 % de tinta` entre o tabuleiro e a paleta de peças, um vão de duas
    vezes a largura da própria paleta.

    O ciclo 2 respondeu que era geometria -- *"um quadrado não passa de 58 % de um retângulo
    933×559"* -- e a aritmética estava certa e a premissa não: **o canvas é 933 porque o layout o
    deixou ser 933.** Quem pede aquela largura é o `stretch` do `QHBoxLayout`, e não o tabuleiro.

    Com o canvas limitado à própria altura, o quadrado passa a ocupar quase tudo o que lhe é dado
    e a largura que sobra sai do canvas em vez de virar vão -- a paleta encosta no tabuleiro. É
    `min` e não `=` porque num painel mais alto que largo quem manda continua sendo a largura: a
    mesma regra de `BoardGeometry.fit`, aplicada uma etapa antes dela.
    """
    return max(1, min(int(disponivel), int(altura)))
