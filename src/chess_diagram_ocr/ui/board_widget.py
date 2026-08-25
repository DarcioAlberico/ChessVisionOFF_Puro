"""Tabuleiro interativo reaproveitável, em dois modos (S-20) e com heatmap (S-21).

O app já tinha um tabuleiro com arraste funcionando -- na aba "Análise", para jogar lances
legais. E, ao mesmo tempo, corrigir um diagrama reconhecido significava editar a string FEN
num `ttk.Entry`: contar casas, achar o caractere certo, digitar. O widget existia e não
estava onde o trabalho acontece.

Este módulo tira o tabuleiro de lá e o parametriza por modo:

- `mode="play"` -- o comportamento da aba de análise: só lance legal, alvos marcados,
  promoção perguntada. Quem decide o que fazer com o lance é o dono do widget, via
  `on_move`; a árvore de variantes continua fora daqui.
- `mode="edit"` -- correção de OCR: clique move sem perguntar de quem é a vez, botão
  direito apaga, paleta lateral insere. A cada mudança sai `on_change(campo_de_peças)`.

E sobre o modo de edição vem o heatmap da S-21: `set_uncertainty` pinta as casas em que o
modelo está inseguro, `set_probabilities` alimenta o tooltip com as três classes mais
prováveis, e `set_changed_squares` marca o que a decodificação restrita reparou. O ponto é
que o usuário pare de comparar 64 casas com o PDF e olhe as três que importam -- a média
de confiança fica em 0,97 mesmo com erro (S-10), então sem isso não há onde olhar.

**O que a S-50 mudou aqui.** O que este arquivo guardava em três responsabilidades agora
mora em dois módulos sem widget nenhum: `board_model.py` sabe o que está no tabuleiro e o
que um clique significa, `board_render.py` sabe pintá-lo. O que sobrou é o que só o Tk pode
fazer -- canvas, eventos, pixels de arraste, tooltip e paleta -- e o repasse entre os dois.
A API pública não mudou: `set_position`, `select_square`, `top_classes` e as demais
continuam onde estavam, porque `ResultPanel` e `StudyPanel` as chamam por nome.

**A paleta, depois da S-65.** Ela mostrava os símbolos Unicode (`♙♘♗`), que dependem de a
máquina ter uma fonte que os desenhe -- e no Windows a `Segoe UI Symbol` os renderiza
pequenos, finos e de altura irregular, com as brancas quase somindo no fundo claro do botão.
Hoje ela usa as peças de `assets/piece_images/`, que são as mesmas do tabuleiro: a paleta
passa a mostrar exatamente o que o clique vai colocar. Três consequências que vieram junto e
que cada uma tem seu próprio "por quê" no código: o pincel ativo **aparece** (era invisível),
clicar de novo no botão aceso **larga** o pincel, e clicar de novo na mesma peça no tabuleiro
**apaga** (ver `BoardModel.paint`).
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from tkinter import ttk

import chess
import numpy as np

from ..config import UNCERTAIN_SQUARE_THRESHOLD
from ..fen_utils import square_name
from . import board_edit, board_render, theme, tipografia, tokens
from .board_model import BoardChange, BoardMode, BoardModel, ChangeKind
from .board_render import (
    LIGHT_SQUARE,
    UNICODE_PIECES,
    BoardGeometry,
    BoardRenderer,
    DragOverlay,
    PieceImages,
    heatmap_color,
)
from .tooltip import Tooltip

logger = logging.getLogger(__name__)

__all__ = ["BoardMode", "InteractiveBoard", "PieceImages", "heatmap_color"]

CLASS_NAMES_PT: dict[str, str] = {"empty": "casa vazia", **board_edit.PIECE_NAMES_PT}

DRAG_THRESHOLD = 0.12
"""Fração da casa que o ponteiro precisa andar para virar arraste em vez de clique."""

PALETTE_ICON_SIZE = 26
"""Lado do ícone de peça na paleta, em pixels.

Os PNGs de `assets/piece_images/` são 70×70; reduzi-los é barato e nítido. 26 px dá um botão
do tamanho de um `ttk.Button` de três caracteres, que é o que a paleta ocupava antes."""

BRUSH_ERASE = ""
"""Pincel que apaga. Coincide com o valor que `BoardModel.brush` já usava."""

BRUSH_NONE = "\x00sem-pincel"
"""Sentinela para "nenhum pincel" na `StringVar` da paleta.

`tk.StringVar` não guarda `None`, e o valor precisa ser um que nenhum símbolo de peça possa
ter -- daí o byte nulo no começo."""


class InteractiveBoard(ttk.Frame):
    """Tabuleiro de 64 casas com clique e arraste, em modo de jogo ou de edição."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        mode: BoardMode = "play",
        on_change: Callable[[str], None] | None = None,
        on_move: Callable[[chess.Move], None] | None = None,
        on_select: Callable[[int | None], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        promotion_chooser: Callable[[], int | None] | None = None,
        piece_images: PieceImages | None = None,
        show_palette: bool | None = None,
        show_coordinates: bool = True,
        min_size: int = 240,
        max_size: int = 560,
        uncertain_threshold: float = UNCERTAIN_SQUARE_THRESHOLD,
    ) -> None:
        super().__init__(parent)
        if mode not in ("play", "edit"):
            raise ValueError(f"mode deve ser 'play' ou 'edit'; recebido {mode!r}.")

        self.model = BoardModel(
            mode=mode,
            uncertain_threshold=uncertain_threshold,
            promotion_chooser=promotion_chooser,
        )
        self.renderer = BoardRenderer(images=piece_images, show_coordinates=show_coordinates)

        self._on_change = on_change
        self._on_move = on_move
        self._on_select = on_select
        self._on_status = on_status
        self._min_size = min_size
        self._max_size = max_size
        self._show_coordinates = show_coordinates
        self._geometry: BoardGeometry | None = None

        self._drag_from: int | None = None
        self._drag_symbol: str | None = None
        self._drag_pointer: tuple[float, float] | None = None
        self._drag_start: tuple[float, float] | None = None
        self._dragging = False
        self._press_selected_new = False

        self._tooltip: tk.Toplevel | None = None
        self._tooltip_after: str | None = None
        self._tooltip_square: int | None = None

        self._brush_var = tk.StringVar(value=BRUSH_NONE)
        self._palette_buttons: dict[str, tk.Radiobutton] = {}

        # Sem parâmetro de cor: quem decide a esteira é o token, não o painel que hospeda
        # (S-147). Era `background=` no construtor, e o Resultado passava claro enquanto a
        # Análise ficava com o padrão escuro -- o mesmo widget com duas identidades em duas
        # abas vizinhas, e nada além do argumento a justificar.
        self.canvas = tk.Canvas(
            self,
            bg=theme.cor_atual(tokens.SUPERFICIE_TABULEIRO),
            highlightthickness=0,
            cursor="hand2",
        )
        theme.ao_repintar(lambda: self.canvas.configure(bg=theme.cor_atual(tokens.SUPERFICIE_TABULEIRO)))
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _event: self._hide_tooltip())

        self.palette: ttk.Frame | None = None
        if show_palette if show_palette is not None else mode == "edit":
            self.palette = self._build_palette()

    # ------------------------------------------------------------------ estado

    @property
    def mode(self) -> BoardMode:
        return self.model.mode

    @property
    def board(self) -> chess.Board:
        return self.model.board

    @property
    def placement(self) -> str:
        """Campo de peças da posição na tela."""
        return self.model.placement

    @property
    def fen(self) -> str:
        return self.model.fen

    @property
    def selected_square(self) -> int | None:
        """Casa selecionada, em ordem de leitura (0 = a8)."""
        return self.model.selected

    @property
    def flipped(self) -> bool:
        return self.model.flipped

    @property
    def brush(self) -> str | None:
        return self.model.brush

    @property
    def heatmap_enabled(self) -> bool:
        return self.model.heatmap_enabled

    def set_position(self, fen: str) -> bool:
        """Põe uma posição na tela. Devolve `False` se a FEN não for interpretável."""
        if not self.model.set_position(fen):
            return False
        self._clear_drag()
        self.redraw()
        return True

    def set_side_to_move(self, color: chess.Color) -> None:
        if self.model.board.turn != color:
            self.model.board.turn = color
            self.redraw()

    def set_last_move(self, move: chess.Move | None) -> None:
        self.model.last_move = move
        self.redraw()

    def set_flipped(self, flipped: bool) -> None:
        self.model.flipped = bool(flipped)
        self.redraw()

    def select_square(self, index: int | None) -> None:
        """Seleciona uma casa de fora do widget -- é como a fila de revisão abre o item já
        apontando para a casa suspeita (S-22)."""
        self._commit(self.model.select(index), notify_select=True)

    def clear_selection(self) -> None:
        self.select_square(None)

    def delete_selected(self) -> bool:
        """Apaga a peça da casa selecionada (tecla `Del`). Só faz sentido em edição."""
        mudanca = self.model.erase_selected()
        self._commit(mudanca)
        return bool(mudanca)

    # ------------------------------------------------------------- S-21: sinais

    def set_uncertainty(self, per_square_conf: Sequence[float] | None) -> None:
        """Confiança de cada casa, em ordem de leitura. `None` desliga o heatmap."""
        self.model.set_uncertainty(per_square_conf)
        self.redraw()

    def set_probabilities(self, probs: np.ndarray | None) -> None:
        """Matriz (64, 13) da S-10, para o tooltip mostrar as três classes mais prováveis."""
        self.model.set_probabilities(probs)

    def set_changed_squares(self, squares: Iterable[int]) -> None:
        """Casas reescritas pela decodificação com restrições (S-11): contorno azul."""
        self.model.set_changed_squares(squares)
        self.redraw()

    def set_problem_squares(self, squares: Iterable[int]) -> None:
        """Casas apontadas pelo painel de legalidade (S-21): contorno vermelho."""
        self.model.set_problem_squares(squares)
        self.redraw()

    def set_disputed_squares(self, squares: Iterable[int]) -> None:
        """Casas em que a segunda leitura discorda da primeira (S-66): contorno roxo."""
        self.model.set_disputed_squares(squares)
        self.redraw()

    def set_heatmap_enabled(self, enabled: bool) -> None:
        self.model.heatmap_enabled = bool(enabled)
        self.redraw()

    def top_classes(self, index: int, count: int = 3) -> list[tuple[str, float]]:
        """As `count` classes mais prováveis de uma casa, para tooltip e testes."""
        return self.model.top_classes(index, count)

    # ------------------------------------------------------------------ paleta

    def _build_palette(self) -> ttk.Frame:
        """A paleta de edição: 12 peças, apagar e largar o pincel.

        São `Radiobutton` com estilo `Toolbutton`, e não `Button`, por um motivo prático: o
        pincel é um **modo**, e um modo precisa aparecer na tela. Com botões comuns não havia
        como saber qual peça estava no pincel a não ser clicando numa casa e vendo o que
        saía -- e clicar numa casa é justamente a ação destrutiva que se queria conferir
        antes. O `Radiobutton` dá o estado ligado de graça e a exclusividade também.
        """
        frame = ttk.Frame(self)
        frame.pack(fill=tk.X, pady=(4, 0))
        self._palette_buttons.clear()

        for row_index, symbols in enumerate((board_edit.PIECE_SYMBOLS[:6], board_edit.PIECE_SYMBOLS[6:])):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X)
            for symbol in symbols:
                self._palette_buttons[symbol] = self._palette_button(row, symbol)
            if row_index == 1:
                ttk.Frame(row, width=8).pack(side=tk.LEFT)
                self._palette_buttons[BRUSH_ERASE] = self._palette_button(row, BRUSH_ERASE)
                self._palette_buttons[BRUSH_NONE] = self._palette_button(row, BRUSH_NONE)
        return frame

    def _palette_button(self, parent: tk.Misc, value: str) -> tk.Radiobutton:
        """Um botão da paleta.

        `tk.Radiobutton` e não `ttk.Radiobutton` por uma medição, não por gosto: nenhuma das
        variantes de `Toolbutton` do tema em uso (`Toolbutton`, `primary.`, `info.`,
        `*.Outline.`) desenha estado selecionado quando o botão tem imagem e não tem texto --
        os 12 botões ficam idênticos, e o pincel ativo volta a ser invisível. O `Radiobutton`
        clássico com `indicatoron=False` desenha, e é o único jeito de o `selectcolor` ser
        escolhido em vez de herdado.

        As cores saem do tema (`_palette_colors`), então os 30 temas continuam valendo.
        """
        fundo, selecionado, ativo = self._palette_colors()
        rotulo = {BRUSH_ERASE: "Apagar", BRUSH_NONE: "Sem pincel"}.get(value)
        imagem = None if rotulo else self._palette_icon(value)

        opcoes: dict[str, object] = {
            "variable": self._brush_var,
            "value": value,
            "command": self._on_palette_click,
            "indicatoron": False,
            "borderwidth": 2,
            "highlightthickness": 0,
            "offrelief": tk.FLAT,
            "relief": tk.SUNKEN,
            "background": fundo,
            "activebackground": ativo,
            "selectcolor": selecionado,
        }

        if imagem is not None:
            # A margem existe para a seleção ter onde aparecer: o ícone é opaco (ver
            # `PieceImages.icon`), então sem ela o `selectcolor` ficaria escondido atrás da
            # peça e o botão aceso seria igual aos outros onze.
            botao = tk.Radiobutton(parent, image=imagem, padx=4, pady=4, **opcoes)  # type: ignore[arg-type]
            # A referência tem de sobreviver: o Tk não segura a imagem, e uma `PhotoImage`
            # coletada vira um botão vazio. `PieceImages` já a mantém em cache, e o atributo
            # aqui é a segunda amarra, para o caso de o cache ser trocado.
            botao.image = imagem  # type: ignore[attr-defined]
        else:
            texto = rotulo or UNICODE_PIECES.get(value, value)
            cor_texto = str(ttk.Style().lookup("TLabel", "foreground") or tokens.RESERVA[tokens.TEXTO_PADRAO])
            botao = tk.Radiobutton(
                parent, text=texto, padx=8, pady=2, foreground=cor_texto, **opcoes  # type: ignore[arg-type]
            )

        if value in board_edit.PIECE_NAMES_PT:
            Tooltip(botao).set_text(f"Pincel: {board_edit.PIECE_NAMES_PT[value]}")
        elif value == BRUSH_ERASE:
            Tooltip(botao).set_text("Pincel apagar: um clique esvazia a casa.")
        else:
            Tooltip(botao).set_text("Sem pincel: o clique volta a arrastar peças.")

        botao.pack(side=tk.LEFT, padx=1, pady=1)
        return botao

    def _palette_colors(self) -> tuple[str, str, str]:
        """`(fundo, selecionado, sob o ponteiro)`, derivados do tema em uso.

        Nada de hexadecimal fixo: o `ttkbootstrap` traz 30 temas e metade deles é escuro, e
        um `#ffffff` cravado aqui deixaria a paleta como um retângulo branco no meio de uma
        janela preta. O fundo vem do tema; os outros dois são o texto do tema misturado ao
        fundo, o que dá contraste no claro e no escuro pela mesma conta.
        """
        style = ttk.Style()
        fundo = str(style.lookup("TFrame", "background") or tokens.RESERVA[tokens.SUPERFICIE_PADRAO])
        texto = str(style.lookup("TLabel", "foreground") or tokens.RESERVA[tokens.TEXTO_PADRAO])
        return fundo, self._mix(texto, fundo, 0.45), self._mix(texto, fundo, 0.15)

    def _mix(self, cor: str, fundo: str, peso: float) -> str:
        """Mistura duas cores do Tk. `winfo_rgb` resolve nome, `#rgb` e `SystemButtonFace`."""
        try:
            a, b = self.winfo_rgb(cor), self.winfo_rgb(fundo)
        except tk.TclError:
            return fundo
        canais = tuple(int((x * peso + y * (1.0 - peso)) / 257) for x, y in zip(a, b, strict=True))
        return "#{:02x}{:02x}{:02x}".format(*canais)

    def _palette_icon(self, symbol: str):  # noqa: ANN202 - ImageTk.PhotoImage | None
        """A peça do `assets/piece_images/`, ou `None` para cair no símbolo Unicode.

        Sem imagens carregadas -- um checkout sem `assets/`, ou um PNG corrompido -- a paleta
        volta ao que era. Uma peça faltando não pode impedir a aba de abrir.
        """
        imagens = self.renderer.images
        return None if imagens is None else imagens.icon(symbol, PALETTE_ICON_SIZE, background=LIGHT_SQUARE)

    def _on_palette_click(self) -> None:
        """Clicar no botão já marcado **larga** o pincel, em vez de não fazer nada.

        `Radiobutton` reafirma o mesmo valor em silêncio, e o gesto natural de quem terminou
        de pintar é clicar de novo no botão que está aceso. Sem isto, largar o pincel exigia
        achar o "Sem pincel" do outro lado da fila.
        """
        escolhido = self._brush_var.get()
        if escolhido == self._brush_value(self.model.brush) and self.model.brush is not None:
            self.set_brush(None)
            return
        self.set_brush(None if escolhido == BRUSH_NONE else escolhido)

    @staticmethod
    def _brush_value(brush: str | None) -> str:
        """O pincel do modelo como valor de `StringVar` -- que não guarda `None`."""
        return BRUSH_NONE if brush is None else brush

    def set_brush(self, symbol: str | None) -> None:
        """Peça que o próximo clique insere. `""` apaga, `None` volta ao modo arrastar."""
        mensagem = self.model.set_brush(symbol)
        self._brush_var.set(self._brush_value(symbol))
        self._status(mensagem)

    # ------------------------------------------------------------ interação

    def _index_from_xy(self, x: float, y: float) -> int | None:
        if self._geometry is None:
            return None
        posicao = self._geometry.display_at(x, y)
        return None if posicao is None else self.model.index_from_display(*posicao)

    def _on_press(self, event: tk.Event) -> None:
        self.canvas.focus_set()
        self._hide_tooltip()
        index = self._index_from_xy(event.x, event.y)
        self._drag_pointer = (event.x, event.y)
        self._drag_start = (event.x, event.y)
        self._drag_from = index
        self._dragging = False
        self._press_selected_new = False
        self._drag_symbol = None

        if index is None:
            return

        anterior = self.model.selected
        mudanca = self.model.press(index)
        if mudanca.touched_position:
            # Pincel: o clique pintou, e nao ha nada a arrastar.
            self._drag_from = None
            self._commit(mudanca)
            return

        if mudanca.kind is not ChangeKind.SELECTION:
            return

        self._press_selected_new = anterior != index
        self._drag_symbol = board_edit.piece_at(self.model.placement, index)
        self._commit(mudanca, notify_select=True)

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_symbol is None or self._drag_from is None or self._geometry is None:
            return
        self._drag_pointer = (event.x, event.y)
        if not self._dragging:
            cell = max(1.0, self._geometry.cell)
            start_x, start_y = self._drag_start or self._drag_pointer
            if abs(event.x - start_x) < cell * DRAG_THRESHOLD and abs(event.y - start_y) < cell * DRAG_THRESHOLD:
                return
            self._dragging = True
            # A casa de origem passa a nao desenhar a peca; so ela precisa ser refeita.
            self._paint_dirty({self._drag_from})
            return
        # Arrastar toca duas coisas: a peca sob o ponteiro e nada mais. Antes disto o canvas
        # inteiro era reconstruido a cada movimento do mouse (S-50).
        self._paint_dirty(())

    def _on_release(self, event: tk.Event) -> None:
        target = self._index_from_xy(event.x, event.y)
        allow_deselect = (not self._dragging) and (not self._press_selected_new)
        origem = self._drag_from
        mudanca = self.model.drop(target, allow_deselect=allow_deselect)
        self._clear_drag()
        sujas = set(mudanca.dirty) | ({origem} if origem is not None else set())
        self._commit(mudanca, notify_select=True, extra_dirty=sujas)

    def _on_right_click(self, event: tk.Event) -> None:
        index = self._index_from_xy(event.x, event.y)
        if index is None:
            return
        self._commit(self.model.erase(index))

    # ------------------------------------------------------------ repasse

    def _commit(
        self,
        change: BoardChange,
        *,
        notify_select: bool = False,
        extra_dirty: set[int] | None = None,
    ) -> None:
        """Aplica na tela o que o modelo decidiu, e avisa quem observa.

        É o único lugar em que uma mudança do modelo vira pixels e callbacks -- antes cada
        método de interação repetia `redraw()` mais dois `if`.
        """
        sujas = set(change.dirty) | (extra_dirty or set())
        if sujas:
            self._paint_dirty(sujas)

        if change.message:
            self._status(change.message)
        if notify_select and change.kind in (ChangeKind.SELECTION, ChangeKind.MOVE, ChangeKind.PLACEMENT):
            self._notify_select()
        if change.kind is ChangeKind.PLACEMENT and self._on_change is not None and change.placement is not None:
            self._on_change(change.placement)
        if change.kind is ChangeKind.MOVE and self._on_move is not None and change.move is not None:
            self._on_move(change.move)

    def _paint_dirty(self, squares: Iterable[int]) -> None:
        """Redesenho parcial. Cai no total quando ainda não há geometria (primeiro desenho)."""
        if self._geometry is None:
            self.redraw()
            return
        # Alvo legal e casa de ultimo lance dependem da selecao e nao estao em `dirty`;
        # em modo de jogo o conjunto de alvos muda a cada selecao, entao ali o total e o
        # certo. Em edicao -- que e o caminho de arraste que a S-50 quer barato -- nao ha
        # alvos, e o parcial vale.
        if self.model.mode == "play":
            self.redraw()
            return
        self.renderer.draw_dirty(self.canvas, self.model, self._geometry, squares, drag=self._drag_overlay())

    def _drag_overlay(self) -> DragOverlay | None:
        if not self._dragging or self._drag_symbol is None or self._drag_pointer is None or self._drag_from is None:
            return None
        return DragOverlay(self._drag_symbol, self._drag_pointer[0], self._drag_pointer[1], self._drag_from)

    def _clear_drag(self) -> None:
        self._drag_from = None
        self._drag_symbol = None
        self._drag_pointer = None
        self._drag_start = None
        self._dragging = False
        self._press_selected_new = False

    def _notify_select(self) -> None:
        if self._on_select is not None:
            self._on_select(self.model.selected)

    def _status(self, text: str) -> None:
        if self._on_status is not None:
            self._on_status(text)

    # ------------------------------------------------------------------ tooltip

    def _on_motion(self, event: tk.Event) -> None:
        if self.model.probs is None or self._dragging:
            self._hide_tooltip()
            return
        index = self._index_from_xy(event.x, event.y)
        if index != self._tooltip_square:
            self._hide_tooltip()
            self._tooltip_square = index
            if index is not None:
                self._tooltip_after = self.canvas.after(350, lambda: self._show_tooltip(event.x_root, event.y_root))

    def _show_tooltip(self, x_root: int, y_root: int) -> None:
        self._tooltip_after = None
        index = self._tooltip_square
        if index is None or self.model.probs is None:
            return

        lines = [square_name(index)]
        for class_name, probability in self.model.top_classes(index):
            lines.append(f"{CLASS_NAMES_PT.get(class_name, class_name)}: {probability * 100:.1f}%")

        tip = tk.Toplevel(self.canvas)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x_root + 14}+{y_root + 14}")
        fundo = theme.cor_atual(tokens.SUPERFICIE_DICA)
        tk.Label(
            tip,
            text="\n".join(lines),
            justify=tk.LEFT,
            background=fundo,
            # `tk.Label` não herda cor de letra do `Style`: sem isto o texto é preto em
            # qualquer tema, e sobre a dica escura da S-147 ele desapareceria.
            foreground=tokens.sobre_superficie(fundo),
            relief=tk.SOLID,
            borderwidth=1,
            font=theme.fonte_atual(tipografia.CORPO),
            padx=6,
            pady=4,
        ).pack()
        self._tooltip = tip

    def _hide_tooltip(self) -> None:
        if self._tooltip_after is not None:
            self.canvas.after_cancel(self._tooltip_after)
            self._tooltip_after = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._tooltip_square = None

    # ------------------------------------------------------------------ desenho

    def redraw(self) -> None:
        """Redesenho total. Necessário quando a geometria muda ou a posição inteira muda."""
        try:
            canvas_w = max(self._min_size, self.canvas.winfo_width())
            canvas_h = max(self._min_size, self.canvas.winfo_height())
        except tk.TclError:
            return

        self._geometry = BoardGeometry.fit(
            canvas_w,
            canvas_h,
            min_size=self._min_size,
            max_size=self._max_size,
            margin=board_render.margem_de_coordenada() if self._show_coordinates else 8,
        )
        self.renderer.draw(self.canvas, self.model, self._geometry, drag=self._drag_overlay())
