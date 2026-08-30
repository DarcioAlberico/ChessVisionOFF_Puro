"""O desenho do tabuleiro no canvas do Tk, e só ele (S-50).

Duas consequências, e as duas são o motivo do item:

**`draw_dirty` acaba com o redesenho total.** `InteractiveBoard.redraw()` reconstruía as 64
casas, as coordenadas e a moldura a cada mudança -- inclusive a cada movimento do ponteiro
durante um arraste. `BoardChange.dirty` diz quais casas mudaram, e arrastar uma peça toca 2.

**Este é o único arquivo a reescrever numa troca de framework.** O `BoardModel` serve ao Tk,
a uma cena Qt e ao Streamlit igualmente; o que é específico do canvas está aqui. É a metade
barata da S-53, e a razão de ela poder ser adiada por gatilho em vez de por gosto.

Cada casa desenha com a tag `sq{índice}`, e é isso que torna o redesenho parcial possível:
apagar por tag e redesenhar. O item arrastado tem tag própria e é reerguido no fim, porque
redesenhar uma casa põe itens novos por cima dele.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageTk

from ..config import UNCERTAIN_SQUARE_THRESHOLD
from . import conjuntos, theme, tipografia, tokens
from .board_model import BoardModel

logger = logging.getLogger(__name__)

__all__ = ["BoardGeometry", "BoardRenderer", "PieceImages", "engrossar_traco", "heatmap_color"]

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

DRAG_TAG = "cvoff-drag"
ESTEIRA_TAG = "cvoff-esteira"
VAZIO_TAG = "cvoff-vazio"
FRAME_TAG = "cvoff-frame"
COORDS_TAG = "cvoff-coords"
ARROWS_TAG = "cvoff-arrows"
"""As setas e casas marcadas do lance (S-279). Tag própria porque elas ficam **por cima** das
peças e precisam ser reerguidas depois de todo redesenho parcial."""

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


class PieceImages:
    """Cache de imagens de peça por conjunto e tamanho, com fallback para símbolo Unicode.

    Estava embutido no `app_tkinter`; virou classe porque agora há mais de um tabuleiro na
    tela e recarregar/redimensionar PNG por tabuleiro seria desperdício visível ao arrastar.

    **O conjunto é uma chave, e não uma instância nova** (S-230). Trocar de conjunto com uma
    segunda `PieceImages` jogaria fora o cache do primeiro, e quem compara dois conjuntos os
    alterna -- é exatamente o caso em que o cache paga. O nome do conjunto entra na chave, então
    a mesma peça, no mesmo tamanho, em dois conjuntos, são duas imagens que convivem.
    """

    def __init__(
        self,
        directory: Path,
        *,
        conjunto: str = conjuntos.PADRAO,
        pasta_do_usuario: Path | str | None = None,
    ) -> None:
        self.directory = Path(directory)
        self._conjunto = conjuntos.valida(conjunto)
        self._pasta_do_usuario = Path(pasta_do_usuario) if pasta_do_usuario else None
        self._sources: dict[str, dict[str, Image.Image]] = {}
        self._cache: dict[tuple[str, str, int, str | None], ImageTk.PhotoImage] = {}
        self._avisadas: set[str] = set()
        """As pastas cujo aviso de peça faltando já saiu. O log diz uma vez, e não a cada
        redesenho -- um tabuleiro arrastado pede imagem dezenas de vezes por segundo."""

    @property
    def conjunto(self) -> str:
        """Qual conjunto está desenhando agora."""
        return self._conjunto

    @property
    def pasta_do_usuario(self) -> Path | None:
        return self._pasta_do_usuario

    def usar_conjunto(self, nome: str, *, pasta: Path | str | None = None) -> str:
        """Troca o conjunto em execução e devolve o que de fato ficou valendo.

        Não limpa o cache de propósito: ele é indexado por conjunto, então voltar ao anterior
        reaproveita o que já foi desenhado. É a mesma decisão de `BarraFluida._rearranjar` ao
        desempacotar em vez de destruir a moldura -- quem alterna paga uma vez, e não sempre.
        """
        self._conjunto = conjuntos.valida(nome)
        if pasta is not None:
            self._pasta_do_usuario = Path(pasta) if pasta else None
        return self._conjunto

    def _diretorio_de(self, conjunto: str) -> Path | None:
        """De onde saem os arquivos daquele conjunto, ou `None` quando não há de onde.

        O conjunto do usuário sem pasta escolhida não é erro: é configuração incompleta, e a
        resposta certa é o Unicode que já existe -- não uma exceção no meio de um redesenho.
        """
        if conjuntos.registrado(conjunto).do_usuario:
            return self._pasta_do_usuario
        return self.directory

    def _load_sources(self, conjunto: str) -> dict[str, Image.Image]:
        """Os PNGs daquele conjunto, lidos uma vez. Peça que falta simplesmente não entra."""
        if conjunto in self._sources:
            return self._sources[conjunto]

        carregadas: dict[str, Image.Image] = {}
        diretorio = self._diretorio_de(conjunto)
        if diretorio is not None:
            for key in conjuntos.PECAS:
                path = diretorio / f"{key}.png"
                if not path.exists():
                    continue
                try:
                    with Image.open(path) as img:
                        carregadas[key] = img.convert("RGBA")
                except (OSError, ValueError) as exc:
                    logger.warning("Imagem de peça inválida em %s: %s", path, exc)
            self._avisar_incompleta(conjunto, diretorio, carregadas)
        self._sources[conjunto] = carregadas
        return carregadas

    def _avisar_incompleta(self, conjunto: str, diretorio: Path, carregadas: dict[str, Image.Image]) -> None:
        """Nomeia as peças que faltam, uma vez por pasta -- **avisar e usar o que houver**.

        Recusar o conjunto inteiro por causa de um arquivo seria trocar um comportamento que já
        existe (o Unicode, peça a peça) por um erro que não precisa existir. E nomear as que
        faltam é metade do valor: "faltam wq e bk" diz o que copiar para lá.
        """
        faltando = [peca for peca in conjuntos.PECAS if peca not in carregadas]
        if not faltando:
            return
        marca = f"{conjunto}:{diretorio}"
        if marca in self._avisadas:
            return
        self._avisadas.add(marca)
        logger.warning(
            "Conjunto de peças %r incompleto em %s: faltam %s. As ausentes caem no símbolo Unicode.",
            conjunto,
            diretorio,
            ", ".join(f"{peca}.png" for peca in faltando),
        )

    def photo(self, symbol: str, cell: int) -> ImageTk.PhotoImage | None:
        """Imagem da peça para uma casa de `cell` pixels. `None` cai no Unicode."""
        return self.icon(symbol, max(12, int(cell * 0.86)))

    def icon(self, symbol: str, size: int, *, background: str | None = None) -> ImageTk.PhotoImage | None:
        """Imagem da peça no tamanho exato pedido, para fora do tabuleiro.

        A paleta de edição usa isto: os símbolos Unicode (`♙♘♗`) dependem de a máquina ter
        uma fonte que os desenhe, e no Windows a `Segoe UI Symbol` os renderiza pequenos,
        finos e de altura irregular -- as brancas quase somem sobre o fundo claro do botão.
        As peças do `assets/piece_images/` são as mesmas que aparecem no tabuleiro, então a
        paleta passa a mostrar exatamente o que o clique vai colocar.

        `background` acha a peça sobre uma cor opaca em vez do fundo do widget, e a paleta o
        usa com a cor da casa clara. Não é enfeite: os PNGs são traço preto com transparência,
        e num dos 15 temas escuros do `ttkbootstrap` as seis peças pretas somem no fundo da
        janela. Sobre casa clara elas aparecem em qualquer tema -- e é assim que elas se
        parecem no tabuleiro, que é o que a paleta está prometendo.
        """
        key = f"{'w' if symbol.isupper() else 'b'}{symbol.lower()}"
        source = self._load_sources(self._conjunto).get(key)
        if source is None:
            return None

        size = max(8, int(size))
        cached = self._cache.get((self._conjunto, key, size, background))
        if cached is not None:
            return cached

        resized = source.resize((size, size), resample=Image.Resampling.LANCZOS)
        # **Depois de reduzir** (S-230): é no tamanho de exibição que o traço some, e é nele que
        # engrossá-lo devolve a diferença entre um peão branco e um bispo branco a 20 px.
        if conjuntos.registrado(self._conjunto).engrossa:
            resized = engrossar_traco(resized)
        if background is not None:
            tile = Image.new("RGBA", (size, size), background)
            tile.alpha_composite(resized)
            resized = tile

        photo = ImageTk.PhotoImage(resized)
        self._cache[(self._conjunto, key, size, background)] = photo
        return photo


@dataclass(frozen=True)
class DragOverlay:
    """A peça que está sob o ponteiro durante um arraste, e a casa de onde ela saiu."""

    symbol: str
    x: float
    y: float
    origin: int


class BoardRenderer:
    """Pinta um `BoardModel` num `tk.Canvas`. Não guarda estado de tabuleiro."""

    def __init__(
        self,
        *,
        images: PieceImages | None = None,
        show_coordinates: bool = True,
    ) -> None:
        self.images = images
        self.show_coordinates = show_coordinates

    def draw(
        self,
        canvas: tk.Canvas,
        model: BoardModel,
        geometry: BoardGeometry,
        *,
        drag: DragOverlay | None = None,
    ) -> None:
        """Redesenha tudo. Só é preciso quando a geometria ou a posição inteira mudam."""
        canvas.delete("all")
        self._draw_esteira(canvas, geometry)
        canvas.create_rectangle(
            geometry.origin_x - 2,
            geometry.origin_y - 2,
            geometry.origin_x + geometry.size + 2,
            geometry.origin_y + geometry.size + 2,
            fill=self._cor_de_moldura(),
            outline="",
            tags=(FRAME_TAG,),
        )
        self._draw_squares(canvas, model, geometry, range(64), drag=drag)
        if self.show_coordinates:
            self._draw_coordinates(canvas, model, geometry)
        self.draw_arrows(canvas, model, geometry)
        self._draw_drag(canvas, geometry, drag)

    def draw_dirty(
        self,
        canvas: tk.Canvas,
        model: BoardModel,
        geometry: BoardGeometry,
        squares: Iterable[int],
        *,
        drag: DragOverlay | None = None,
    ) -> None:
        """Redesenha só as casas afetadas. `BoardChange.dirty` diz quais são."""
        indices = [index for index in squares if 0 <= index < 64]
        if not indices:
            self._draw_drag(canvas, geometry, drag)
            return
        for index in indices:
            canvas.delete(self._tag(index))
        self._draw_squares(canvas, model, geometry, indices, drag=drag)
        # Uma casa recem-desenhada fica por cima de tudo que ja estava no canvas, inclusive
        # da peca arrastada, das coordenadas e das setas -- dai o reerguer.
        canvas.tag_raise(COORDS_TAG)
        canvas.tag_raise(ARROWS_TAG)
        self._draw_drag(canvas, geometry, drag)

    # -------------------------------------------------------------------------- internos

    @staticmethod
    def _tag(index: int) -> str:
        return f"cvoff-sq{index}"

    def _draw_squares(
        self,
        canvas: tk.Canvas,
        model: BoardModel,
        geometry: BoardGeometry,
        indices: Iterable[int],
        *,
        drag: DragOverlay | None,
    ) -> None:
        squares = model.squares()
        last_move = model.last_move_squares()
        targets = model.legal_targets()

        for index in indices:
            tag = self._tag(index)
            row, col = model.display_from_index(index)
            x0, y0, x1, y1 = geometry.rect(row, col)
            cell = geometry.cell

            base = LIGHT_SQUARE if (index // 8 + index % 8) % 2 == 0 else DARK_SQUARE
            if index in last_move:
                base = LAST_MOVE_SQUARE
            canvas.create_rectangle(x0, y0, x1, y1, fill=base, outline=base, tags=(tag,))

            if index == model.selected:
                # **Contorno, e não preenchimento** (S-160). A seleção pintava a casa de
                # `#f7ec74` e o último lance de `#cdd26a` -- 1,32:1 entre si, e adjacentes toda
                # vez que se seleciona a casa de destino do lance recém-jogado, que é o gesto
                # mais comum desta aba. O amarelo ficou sozinho no papel dele.
                canvas.create_rectangle(
                    x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=SELECTION_OUTLINE, width=3, tags=(tag,)
                )

            confidence = model.heatmap_confidence(index)
            if confidence is not None:
                color = heatmap_color(confidence, model.uncertain_threshold)
                # `stipple` e o único jeito de tingir sem apagar a casa no canvas do Tk, que
                # não tem canal alfa: a peça por baixo continua legivel.
                canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color, stipple="gray50", tags=(tag,))
                canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=color, width=2, tags=(tag,))

            if index in model.problems:
                canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=PROBLEM_OUTLINE, width=3, tags=(tag,))
            elif index in model.changed:
                canvas.create_rectangle(
                    x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=CHANGED_OUTLINE, width=2, dash=(4, 3), tags=(tag,)
                )

            if index in model.disputed:
                # Contorno de dentro, e nao `elif`: a casa em disputa e justamente a que tem
                # mais chance de ser tambem ilegal ou reescrita, e esconder um sinal atras do
                # outro apagaria a coincidencia que interessa ver.
                canvas.create_rectangle(
                    x0 + 5, y0 + 5, x1 - 5, y1 - 5, outline=DISPUTED_OUTLINE, width=2, tags=(tag,)
                )

            if drag is not None and index == drag.origin:
                # A peca esta sob o ponteiro; desenha-la tambem na origem seria mostra-la duas
                # vezes, que e o sintoma classico de arraste sem estado.
                continue

            symbol = squares[index]
            if symbol:
                self._draw_piece(canvas, symbol, x0 + cell / 2, y0 + cell / 2, cell, tags=(tag,))
                if index in targets:
                    canvas.create_rectangle(
                        x0 + 4, y0 + 4, x0 + cell - 4, y0 + cell - 4, outline=TARGET_MARK, width=2, tags=(tag,)
                    )
            elif index in targets:
                radius = max(6, int(cell * 0.12))
                canvas.create_oval(
                    x0 + cell / 2 - radius,
                    y0 + cell / 2 - radius,
                    x0 + cell / 2 + radius,
                    y0 + cell / 2 + radius,
                    fill=TARGET_MARK,
                    outline="",
                    tags=(tag,),
                )

    def _draw_piece(
        self, canvas: tk.Canvas, symbol: str, center_x: float, center_y: float, cell: float, *, tags: tuple[str, ...]
    ) -> None:
        photo = self.images.photo(symbol, int(cell)) if self.images is not None else None
        if photo is not None:
            canvas.create_image(center_x, center_y, image=photo, tags=tags)
            return
        canvas.create_text(
            center_x,
            center_y,
            text=UNICODE_PIECES.get(symbol, symbol),
            fill=tokens.RESERVA[tokens.TEXTO_SOBRE_MARCACAO],
            font=("Segoe UI Symbol", max(12, int(cell * 0.56))),
            tags=tags,
        )

    @staticmethod
    def _cor_de_moldura() -> str:
        """A moldura resolvida contra o tema em uso (S-147). Reserva quando não há janela.

        Só no desenho completo: `draw_dirty` não toca a moldura, e trocar de tema redesenha
        tudo. Resolver aqui, e não no `__init__`, é o que faz `CVOFF_TTK_THEME=darkly` chegar
        ao anel do tabuleiro sem o renderizador guardar estado de tema.
        """
        try:
            return theme.cor_atual(tokens.MOLDURA)
        except tk.TclError:  # pragma: no cover - sem root o desenho nem acontece
            return BOARD_FRAME

    def draw_vazio(self, canvas: tk.Canvas, mensagem: str) -> None:
        """O canvas quando **não há diagrama aberto**: o vazio e a frase, e tabuleiro nenhum (S-450).

        **O desenho contradizia a frase.** A aba mostrava um tabuleiro 8x8 inteiro, com coordenadas
        e casas pintadas, e logo abaixo dizia "Nenhum diagrama aberto". Um tabuleiro vazio é uma
        **posição** -- é o que a S-229 empilha e o que "Limpar" produz --, e não a ausência de
        posição. Quem abre o programa pela primeira vez vê um tabuleiro e conclui que há algo ali.

        A distinção que este método existe para manter: **"nenhum diagrama aberto" e "diagrama
        aberto e vazio" são estados diferentes.** O segundo continua desenhando o tabuleiro, porque
        é uma posição legítima e a pilha de desfazer pode voltar a ela.

        A frase é desenhada **no canvas** e não num rótulo abaixo dele, que é onde ela estava: ali
        ela ficava sob o desenho que a contradizia, alinhada à esquerda. Aqui ela ocupa o lugar do
        que não existe, que é o lugar para onde o olho já está indo.
        """
        canvas.delete("all")
        largura = max(int(canvas.winfo_width()), self._min_largura_de_texto)
        altura = max(int(canvas.winfo_height()), 1)
        canvas.create_text(
            largura / 2,
            altura / 2,
            text=mensagem,
            fill=self._cor_de_texto_vazio(),
            font=self._fonte_de_texto_vazio(),
            width=largura - 2 * margem_de_coordenada(),
            justify=tk.CENTER,
            tags=(VAZIO_TAG,),
        )

    _min_largura_de_texto = 120
    """Piso da largura usada para quebrar a frase. Um canvas ainda sem geometria reporta 1."""

    @staticmethod
    def _cor_de_texto_vazio() -> str:
        """A letra da frase: secundária, porque ela orienta e não compete."""
        try:
            return theme.cor_atual(tokens.TEXTO_SECUNDARIO)
        except tk.TclError:  # pragma: no cover - sem root o desenho nem acontece
            return tokens.RESERVA[tokens.TEXTO_SECUNDARIO]

    @staticmethod
    def _fonte_de_texto_vazio() -> tuple[str, int] | tuple[str, int, str]:
        """`tipografia.AUXILIAR`: o peso de quem diz o que fazer sem disputar com o documento."""
        try:
            return theme.fonte_atual(tipografia.AUXILIAR)
        except tk.TclError:  # pragma: no cover - sem root o desenho nem acontece
            return COORD_FONT

    def _draw_esteira(self, canvas: tk.Canvas, geometry: BoardGeometry) -> None:
        """A esteira: um retângulo do tamanho do tabuleiro mais a margem da coordenada (S-449).

        **Antes ela não tinha fim.** O canvas enche o painel (`pack(fill=BOTH, expand=True)`) e o
        fundo dele era `SUPERFICIE_TABULEIRO` -- então tudo o que não fosse tabuleiro virava
        esteira. Medido na pele clássica: 691 px de canvas, **429 em `#312e2b`**, 62%, dentro de um
        painel `#f0f0f0`. Um quase-preto de dois terços da largura em volta de espaço que não
        carrega informação nenhuma.

        A esteira continua existindo e continua escura, pela razão da S-147 -- é ela que dá 11,03:1
        às coordenadas, que são desenhadas **em cima dela**. O que muda é que ela passa a ter
        tamanho, e o que sobra é `VAZIO_DE_CANVAS`, vizinho do fundo do painel.

        A margem é a mesma que `BoardGeometry.fit` já reserva para a coordenada caber inteira
        (`margem_de_coordenada`, dividida entre os dois lados) -- e não um número novo: se ela
        mudar, a esteira acompanha, porque as duas leem a mesma função.
        """
        folga = margem_de_coordenada() / 2
        canvas.create_rectangle(
            geometry.origin_x - folga,
            geometry.origin_y - folga,
            geometry.origin_x + geometry.size + folga,
            geometry.origin_y + geometry.size + folga,
            fill=self._cor_de_esteira(),
            outline="",
            tags=(ESTEIRA_TAG,),
        )

    @staticmethod
    def _cor_de_esteira() -> str:
        """A esteira em que o tabuleiro se assenta. Cai na reserva se não houver root."""
        try:
            return theme.cor_atual(tokens.SUPERFICIE_TABULEIRO)
        except tk.TclError:  # pragma: no cover - sem root o desenho nem acontece
            return tokens.RESERVA[tokens.SUPERFICIE_TABULEIRO]

    @staticmethod
    def _cor_de_coordenada(canvas: tk.Canvas) -> str:
        """A cor legível sobre **a esteira**, que é onde a coordenada é desenhada (S-449).

        Era contra `canvas.cget("background")`, e estava certo enquanto o fundo do canvas **era** a
        esteira. Desde que a esteira virou um retângulo com tamanho, o fundo do canvas é
        `VAZIO_DE_CANVAS` -- claro na pele clássica --, e resolver contra ele daria letra escura
        desenhada sobre a esteira escura. O princípio não mudou: quem desenha resolve contra o que
        está debaixo do que ele desenha; o que mudou é o que está debaixo.

        A leitura do canvas fica como reserva: um `Style` que não responda ainda devolve alguma
        coisa, e a coordenada continua legível contra o que o canvas de fato tem.
        """
        try:
            fundo = BoardRenderer._cor_de_esteira()
            if not fundo.startswith("#"):  # pragma: no cover - reserva de reserva
                fundo = str(canvas.cget("background") or "")
            if not fundo.startswith("#"):
                # `SystemButtonFace` e afins: pede ao Tk o RGB de 16 bits e reduz a 8.
                r, g, b = canvas.winfo_rgb(fundo)
                fundo = f"#{r // 257:02x}{g // 257:02x}{b // 257:02x}"
        except tk.TclError:
            return COORDINATE_TEXT
        return tokens.sobre_superficie(fundo)

    def _draw_coordinates(self, canvas: tk.Canvas, model: BoardModel, geometry: BoardGeometry) -> None:
        """As letras a–h e os números 8–1, **na cor que contrasta com o fundo do canvas** (S-146).

        Eram uma constante `#d8d8d8`, escolhida para o tabuleiro escuro da Análise. O Resultado
        desenha sobre `#f2f2f2`: razão **1,27:1**, ou seja, as coordenadas estavam na tela e não
        podiam ser lidas. Num programa cujo trabalho é dizer "o bispo está em c4", a régua que
        nomeia c4 era invisível.

        O fundo vem do próprio canvas e não de um parâmetro: quem desenha é quem sabe onde está,
        e um parâmetro seria mais um número solto em outro arquivo -- que é a família de defeito
        que a S-145 veio fechar.
        """
        cor_coordenada = self._cor_de_coordenada(canvas)
        files = "hgfedcba" if model.flipped else "abcdefgh"
        ranks = "12345678" if model.flipped else "87654321"
        for index, char in enumerate(files):
            canvas.create_text(
                geometry.origin_x + index * geometry.cell + geometry.cell / 2,
                geometry.origin_y + geometry.size + COORD_OFFSET_PX,
                text=char,
                fill=cor_coordenada,
                font=COORD_FONT,
                tags=(COORDS_TAG,),
            )
        for index, char in enumerate(ranks):
            canvas.create_text(
                geometry.origin_x - COORD_OFFSET_PX + 1,
                geometry.origin_y + index * geometry.cell + geometry.cell / 2,
                text=char,
                fill=cor_coordenada,
                font=COORD_FONT,
                tags=(COORDS_TAG,),
            )

    def _draw_drag(self, canvas: tk.Canvas, geometry: BoardGeometry, drag: DragOverlay | None) -> None:
        canvas.delete(DRAG_TAG)
        if drag is None:
            return
        self._draw_piece(canvas, drag.symbol, drag.x, drag.y, geometry.cell, tags=(DRAG_TAG,))

    # ---------------------------------------------------------------- setas (S-279)

    def draw_arrows(
        self,
        canvas: tk.Canvas,
        model: BoardModel,
        geometry: BoardGeometry,
        *,
        extra: tuple[int, int, str] | None = None,
    ) -> None:
        """As setas e casas marcadas do lance, por cima das peças.

        `extra` é a seta que está sendo arrastada agora e ainda não foi gravada -- ela é desenhada
        junto e some quando o botão é solto. Sem ela o gesto pareceria não estar acontecendo.

        Sempre apaga e redesenha o conjunto inteiro: são poucas por lance, e um desenho parcial de
        seta exigiria saber quais casas ela cruza, que é mais caro do que refazê-las.
        """
        canvas.delete(ARROWS_TAG)
        setas = list(model.arrows) + ([extra] if extra is not None else [])
        for origem, destino, cor in setas:
            papel = PAPEL_DE_SETA.get(str(cor), tokens.SETA_VERDE)
            try:
                tinta = theme.cor_atual(papel)
            except tk.TclError:  # pragma: no cover - sem root o desenho nem acontece
                tinta = tokens.RESERVA[papel]
            if origem == destino:
                self._draw_circle(canvas, model, geometry, origem, tinta)
            else:
                self._draw_arrow(canvas, model, geometry, origem, destino, tinta)

    def _centro(self, model: BoardModel, geometry: BoardGeometry, index: int) -> tuple[float, float]:
        row, col = model.display_from_index(index)
        x0, y0, _, _ = geometry.rect(row, col)
        return x0 + geometry.cell / 2, y0 + geometry.cell / 2

    def _draw_circle(
        self, canvas: tk.Canvas, model: BoardModel, geometry: BoardGeometry, index: int, tinta: str
    ) -> None:
        """Casa marcada: um anel, e não um preenchimento.

        Preenchimento esconderia a peça que está na casa, e a casa marcada é quase sempre marcada
        **por causa** da peça que está nela. É a mesma decisão da S-160 para a casa selecionada."""
        centro_x, centro_y = self._centro(model, geometry, index)
        raio = geometry.cell * 0.44
        canvas.create_oval(
            centro_x - raio,
            centro_y - raio,
            centro_x + raio,
            centro_y + raio,
            outline=tinta,
            width=max(2.0, geometry.cell * LARGURA_DO_CIRCULO),
            tags=(ARROWS_TAG,),
        )

    def _draw_arrow(
        self,
        canvas: tk.Canvas,
        model: BoardModel,
        geometry: BoardGeometry,
        origem: int,
        destino: int,
        tinta: str,
    ) -> None:
        """A haste recuada nas duas pontas, para a peça de origem e a de destino continuarem à vista."""
        x0, y0 = self._centro(model, geometry, origem)
        x1, y1 = self._centro(model, geometry, destino)
        dx, dy = x1 - x0, y1 - y0
        comprimento = (dx * dx + dy * dy) ** 0.5
        if comprimento < 1e-6:  # pragma: no cover - origem == destino já foi tratado
            return
        ux, uy = dx / comprimento, dy / comprimento
        recuo = geometry.cell * 0.32
        largura = max(2.0, geometry.cell * LARGURA_DA_SETA)
        canvas.create_line(
            x0 + ux * recuo,
            y0 + uy * recuo,
            x1 - ux * (geometry.cell * 0.12),
            y1 - uy * (geometry.cell * 0.12),
            fill=tinta,
            width=largura,
            arrow=tk.LAST,
            arrowshape=(largura * 2.6, largura * 2.6, largura * 1.1),
            capstyle=tk.ROUND,
            tags=(ARROWS_TAG,),
        )
