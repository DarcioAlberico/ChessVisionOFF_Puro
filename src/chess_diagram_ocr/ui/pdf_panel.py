"""O lado direito da janela: o PDF, sua navegação e a seleção de área (S-31).

**O que ele guarda.** O documento aberto, a página renderizada e o zoom. Era estado do
`ChessOcrTkApp` misturado com o do OCR, e a mistura tinha consequência: `page_rgb`,
`page_loaded_for_index` e `pdf_source` eram lidos por métodos de reconhecimento espalhados
pela classe, então não havia como saber quem podia invalidá-los.

**O que ele não faz.** Não reconhece nada. A seleção de área devolve um retângulo em
coordenadas de **pixel da página**; recortar, grampear aos limites e decidir o que fazer
quando não há contorno é do `OcrService` (S-31). O painel só sabe converter coordenada de
canvas para coordenada de imagem, que é a única parte que depende do zoom.

**Os diagramas marcados na página (S-68).** Sobre a mesma imagem o painel desenha um retângulo
por diagrama que o detector achou, numerado como o seletor da aba Resultado numera. Clicar num
deles é o gesto que a seleção de área já oferecia, sem o arrasto -- e a decisão do que aquele
clique significa não mora aqui: ela é `page_overlay.decide_box_click`, e quem a executa é a
janela, que é quem tem o OCR. O painel só sabe desenhar, acertar o alvo e avisar.

**Um visualizador só, e por quê (S-69).** Até aqui havia duas abas: esta e uma "Leitura", que
embutia o WebView2 -- o visualizador de PDF do Edge -- dentro de um `Frame` por `SetParent`. Ela
saiu, e o que a matou foi justamente a S-68: um HWND nativo filho pinta **acima** de qualquer
item do canvas, o leitor interno do Edge não aceita JS injetado e não informa a página em que
está. Ou seja, na aba "Leitura" não havia como desenhar os retângulos, capturar o clique nem
saber que página o usuário estava vendo -- a sincronia entre as duas abas era, por construção,
de mão única e cega. E os pixels que o OCR precisa vêm do PyMuPDF, que só esta aba tem.

No lugar dela ficou o botão **Abrir no leitor do sistema**, que entrega o mesmo valor -- rolagem
contínua, busca de texto, render nativo -- sem fingir estar sincronizado com nada. Junto saíram
`pythonnet` e `pywebview`, as duas únicas dependências só-Windows do projeto.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import tkinter as tk
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page

from .page_overlay import DiagramBox, PageBoxes
from .tooltip import Tooltip
from .viewport import (
    WheelAction,
    anchor_after_zoom,
    clamp_zoom,
    decide_wheel,
    fit_width_zoom,
    wheel_direction,
    zoomed,
)

logger = logging.getLogger(__name__)

MIN_SELECTION_PX = 12
"""Arrasto menor que isto é clique errado, não seleção. Abaixo disso o recorte não
conteria nem uma casa do tabuleiro."""

WHEEL_SCROLL_UNITS = 3
"""Linhas de canvas por giro da roda. Três é o padrão do Windows, e o canvas mede "unidade"
em pixels -- então o passo real é o `yscrollincrement`, que aqui fica no padrão do Tk."""

CLICK_SLOP_PX = 4
"""Quanto o ponteiro pode andar entre apertar e soltar e ainda ser um clique.

Sem folga, o clique de quem apoia a mão no mouse vira arrasto e não abre diagrama nenhum;
com folga demais, arrastar a barra de rolagem abriria um diagrama por acidente."""

# --- as três cores são **um** eixo: em que ponto do trabalho aquele diagrama está. A seleção
# --- deixou de ser cor na S-71 justamente para não disputar este eixo -- ver `_draw_boxes`.
BOX_OUTLINE = "#4da3ff"
"""Localizado pelo detector, ainda não lido."""

BOX_OUTLINE_RECOGNIZED = "#ffb02e"
"""Lido pelo OCR e **ainda não salvo**: o que falta fazer nesta página."""

BOX_OUTLINE_SAVED = "#00c07a"
"""Já tem amostra no `labels.csv`. Verde é a cor de "pronto", e é para isso que ela serve.

Vale mesmo antes de a página ser lida: quem responde é a procedência gravada no CSV, não o
que está em memória. Abrir um livro pela quinta vez e ver de verde o que já foi feito é a
única forma barata de responder "onde eu parei?"."""


def box_color(box: DiagramBox) -> str:
    """A cor do retângulo, pelo ponto em que aquele diagrama está.

    Salvo ganha de lido, e lido ganha de localizado: a informação mais adiantada é a que
    interessa. Salvo vem primeiro inclusive quando a página ainda não foi lida -- é o caso que
    faz a marcação valer para um livro que já foi trabalhado antes.
    """
    if box.saved:
        return BOX_OUTLINE_SAVED
    return BOX_OUTLINE_RECOGNIZED if box.recognized else BOX_OUTLINE


def open_in_system_reader(pdf_path: Path) -> None:
    """Abre o PDF no leitor padrão do sistema, na janela dele.

    Substitui o WebView2 embutido (S-69) e cabe em oito linhas porque não tenta ser uma aba:
    quem quer ler o livro ganha o leitor de verdade, com rolagem contínua e busca de texto, e
    o app não promete saber o que acontece lá dentro -- que era a promessa que a aba "Leitura"
    não tinha como cumprir.

    Os três ramos existem porque, sem o WebView2, **não sobrou nada de específico de Windows no
    projeto**. Deixar um `os.startfile` sozinho aqui reintroduziria a dependência de plataforma
    pela porta dos fundos, e por um botão.
    """
    alvo = str(Path(pdf_path).resolve())
    if sys.platform == "win32":
        # `os.startfile` só existe no Windows -- daí o `getattr`, que mantém os três ramos
        # verificáveis nas três plataformas em vez de depender de um `type: ignore`.
        getattr(os, "startfile")(alvo)  # noqa: B009
    elif sys.platform == "darwin":
        subprocess.Popen(["open", alvo])
    else:
        subprocess.Popen(["xdg-open", alvo])


class PdfPanel(ttk.Frame):
    """Visualização e navegação do PDF, com seleção de área para OCR."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        dpi: Callable[[], int],
        initial_page_for: Callable[[Path], int],
        on_status: Callable[[str], None],
        on_ocr_best: Callable[[], None],
        on_ocr_all: Callable[[], None],
        on_region: Callable[[np.ndarray, tuple[int, int, int, int]], None],
        on_export: Callable[[], None],
        on_cancel_export: Callable[[], None],
        on_pdf_opened: Callable[[Path], None],
        on_before_page_change: Callable[[], None],
        on_page_rendered: Callable[[int], None],
        on_zoom_changed: Callable[[float], None],
        initial_dir: Path,
        on_box_click: Callable[[int], None] = lambda _indice: None,
        on_prefs_changed: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__(parent, padding=10)
        self._dpi = dpi
        self._initial_page_for = initial_page_for
        self._on_status = on_status
        self._on_region = on_region
        self._on_pdf_opened = on_pdf_opened
        self._on_box_click = on_box_click
        """Um diagrama marcado foi clicado. Recebe o índice em base 0 -- o mesmo do editor.

        Padrão inerte para que montar o painel sem a janela (nos testes) não exija inventar um
        destino para o clique."""

        self._on_prefs_changed = on_prefs_changed
        """Uma preferência de visualização mudou -- marcação de diagramas ou virada de página
        pela roda. Existe para o estado da aplicação lembrar dela entre execuções."""
        self._on_before_page_change = on_before_page_change
        """Chamado antes de trocar a página exibida: é a janela de tempo em que o editor
        ainda tem o reconhecimento da página de origem para guardar no cache."""

        self._on_page_rendered = on_page_rendered
        """Chamado depois de a página aparecer. É onde a janela traz de volta o
        reconhecimento guardado desta página e grava o estado -- fazê-lo antes do render
        restauraria o editor para uma página que ainda não está na tela."""

        self._on_zoom_changed = on_zoom_changed
        self._initial_dir = initial_dir

        self.source: Path | None = None
        self.name: str = ""
        self.page_count = 0
        self.page_rgb: np.ndarray | None = None
        self.page_loaded_for_index: int | None = None

        self.page_index_var = tk.IntVar(value=0)
        self.zoom_var = tk.DoubleVar(value=0.7)

        self._page_photo: ImageTk.PhotoImage | None = None
        self._select_mode = False
        self._select_start: tuple[float, float] | None = None
        self._select_rect_id: int | None = None
        self._canvas_image_id: int | None = None

        self.boxes: PageBoxes | None = None
        """Os diagramas marcados na página exibida (S-68). `None` enquanto não se sabe.

        "Não se sabe" e "não há" são estados diferentes e ambos existem: o primeiro é a página
        recém-rasterizada, com a detecção ainda rodando; o segundo é uma página de prosa. Só o
        segundo autoriza dizer ao usuário que ali não tem diagrama."""

        self.show_boxes_var = tk.BooleanVar(value=True)
        self._selected_box: int | None = None
        self._press_at: tuple[float, float] | None = None
        self._hover_box: int | None = None

        self.flip_pages_var = tk.BooleanVar(value=True)
        """Se a roda vira a página ao chegar na borda (S-70)."""

        self._last_page_flip = 0.0
        self._panning = False

        self._build(on_ocr_best, on_ocr_all, on_export, on_cancel_export)

    # ------------------------------------------------------------------------------ layout

    def _build(
        self,
        on_ocr_best: Callable[[], None],
        on_ocr_all: Callable[[], None],
        on_export: Callable[[], None],
        on_cancel_export: Callable[[], None],
    ) -> None:
        box = ttk.LabelFrame(self, text="PDF (direita)")
        box.pack(fill=tk.BOTH, expand=True)

        row = ttk.Frame(box)
        row.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(row, text="Abrir PDF", command=self.open_pdf).pack(side=tk.LEFT)
        self.btn_system_reader = ttk.Button(
            row, text="Abrir no leitor do sistema", command=self.open_in_system_reader, state=tk.DISABLED
        )
        self.btn_system_reader.pack(side=tk.LEFT, padx=6)
        Tooltip(
            self.btn_system_reader,
            "Abre este PDF no leitor padrão do sistema, numa janela própria.\n"
            "Para ler o livro: rolagem contínua e busca de texto, que esta tela não tem.",
        )
        self.lbl_pdf = ttk.Label(row, text="Nenhum PDF")
        self.lbl_pdf.pack(side=tk.LEFT, padx=8)

        nav = ttk.Frame(box)
        nav.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(nav, text="Página anterior", command=self.prev_page).pack(side=tk.LEFT)
        ttk.Button(nav, text="Próxima página", command=self.next_page).pack(side=tk.LEFT, padx=6)
        ttk.Label(nav, text="Página").pack(side=tk.LEFT, padx=(12, 4))
        self.spin_page = ttk.Spinbox(
            nav, from_=0, to=0, textvariable=self.page_index_var, width=8, command=self.on_page_spin
        )
        self.spin_page.pack(side=tk.LEFT)

        acoes = ttk.Frame(box)
        acoes.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.btn_ocr_best = ttk.Button(acoes, text="OCR melhor diagrama", command=on_ocr_best)
        self.btn_ocr_best.pack(side=tk.LEFT)
        self.btn_ocr_all = ttk.Button(acoes, text="OCR todos diagramas", command=on_ocr_all)
        self.btn_ocr_all.pack(side=tk.LEFT, padx=6)
        self.btn_select = ttk.Button(acoes, text="Selecionar área (OCR)", command=self.toggle_area_selection)
        self.btn_select.pack(side=tk.LEFT, padx=6)
        self.btn_export = ttk.Button(acoes, text="Exportar PDF -> PGN", command=on_export)
        self.btn_export.pack(side=tk.LEFT, padx=6)
        self.btn_cancel_export = ttk.Button(
            acoes, text="Cancelar exportação", command=on_cancel_export, state=tk.DISABLED
        )
        self.btn_cancel_export.pack(side=tk.LEFT)

        zoom_row = ttk.Frame(box)
        zoom_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(zoom_row, text="Zoom PDF").pack(side=tk.LEFT)
        ttk.Button(zoom_row, text="-", width=3, command=lambda: self.zoom(-0.1)).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(zoom_row, text="+", width=3, command=lambda: self.zoom(0.1)).pack(side=tk.LEFT, padx=(2, 6))
        self.lbl_zoom = ttk.Label(zoom_row, text="70%")
        self.lbl_zoom.pack(side=tk.LEFT)
        self.btn_fit_width = ttk.Button(zoom_row, text="Ajustar à largura", command=self.fit_width)
        self.btn_fit_width.pack(side=tk.LEFT, padx=(8, 0))
        Tooltip(
            self.btn_fit_width,
            "Ctrl + roda do mouse faz o mesmo, com o ponteiro como âncora.\n"
            "A roda rola a página; na borda, ela vira para a página seguinte.",
        )
        self.chk_flip = ttk.Checkbutton(
            zoom_row,
            text="Roda vira a página",
            variable=self.flip_pages_var,
            command=self._on_prefs_changed,
        )
        self.chk_flip.pack(side=tk.LEFT, padx=(12, 0))
        Tooltip(
            self.chk_flip,
            "Ligado: rolar além do fim da página vai para a próxima, no topo.\n"
            "Desligado: a roda só rola dentro da página exibida.",
        )

        self.chk_boxes = ttk.Checkbutton(
            zoom_row,
            text="Marcar diagramas",
            variable=self.show_boxes_var,
            command=self.on_boxes_toggle,
        )
        self.chk_boxes.pack(side=tk.LEFT, padx=(16, 0))
        Tooltip(
            self.chk_boxes,
            "Desenha um retângulo sobre cada diagrama que o detector achou na página.\n"
            "Clique num deles para abri-lo na aba Resultado.",
        )
        self.lbl_boxes = ttk.Label(zoom_row, text="")
        self.lbl_boxes.pack(side=tk.LEFT, padx=(8, 0))

        # Sem `Notebook`: a página ocupa o painel inteiro desde a S-69. Enquanto havia duas
        # abas, esta metade da janela custava uma linha de abas para oferecer uma escolha que
        # não era uma -- a outra não fazia nada que esta não faça, e não fazia o que esta faz.
        view = ttk.Frame(box)
        view.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        wrap = ttk.Frame(view)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(wrap, bg="#1c1c1c", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.canvas.yview)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll = ttk.Scrollbar(view, orient=tk.HORIZONTAL, command=self.canvas.xview)
        hscroll.pack(fill=tk.X, pady=(0, 8))
        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)
        # Botão do meio: deslocar a página mesmo com a seleção de área ligada, que é quando o
        # botão esquerdo pertence ao retângulo verde.
        self.canvas.bind("<ButtonPress-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", self._on_pan_end)
        self._bind_wheel()

    def _bind_wheel(self) -> None:
        """Liga a roda na janela inteira, e não no canvas -- ver `_pointer_over_canvas`."""
        raiz = self.winfo_toplevel()
        raiz.bind_all("<MouseWheel>", self._on_wheel)
        raiz.bind_all("<Shift-MouseWheel>", self._on_wheel_horizontal)
        raiz.bind_all("<Control-MouseWheel>", self._on_wheel_zoom)
        # X11 não tem `MouseWheel`: a roda são os botões 4 e 5, sem delta.
        raiz.bind_all("<Button-4>", partial(self._on_wheel_x11, delta=120))
        raiz.bind_all("<Button-5>", partial(self._on_wheel_x11, delta=-120))

    # ------------------------------------------------------------------------------- zoom

    @property
    def page_index(self) -> int:
        return int(self.page_index_var.get())

    def zoom(self, delta: float) -> None:
        """Os botões `+` e `-`. Continuam aditivos: um clique, um passo previsível."""
        self.apply_zoom(self.zoom_var.get() + delta)

    def apply_zoom(self, value: float, *, anchor: tuple[int, int] | None = None) -> None:
        """Troca o zoom preservando o ponto de referência. `anchor` é (x, y) no widget.

        Sem âncora o ponto preservado é o **centro da vista**, que é o que faz o botão `+`
        aumentar o que está no meio da tela em vez de saltar para o canto superior esquerdo.
        """
        antigo = float(self.zoom_var.get())
        novo = clamp_zoom(value)
        if novo == antigo or self.page_rgb is None:
            self.zoom_var.set(novo)
            self.update_zoom_label()
            return

        largura = float(self.page_rgb.shape[1])
        altura = float(self.page_rgb.shape[0])
        ax, ay = anchor if anchor is not None else (self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2)
        fx = anchor_after_zoom(
            pointer_canvas=self.canvas.canvasx(ax),
            pointer_widget=float(ax),
            old_span=largura * antigo,
            new_span=largura * novo,
        )
        fy = anchor_after_zoom(
            pointer_canvas=self.canvas.canvasy(ay),
            pointer_widget=float(ay),
            old_span=altura * antigo,
            new_span=altura * novo,
        )

        self.zoom_var.set(novo)
        self.update_zoom_label()
        self.refresh_view(reset_scroll=False)
        self.canvas.xview_moveto(fx)
        self.canvas.yview_moveto(fy)
        self._on_zoom_changed(novo)

    def fit_width(self) -> None:
        """Ajusta o zoom para a página caber na largura visível."""
        if self.page_rgb is None:
            self._on_status("Abra um PDF antes de ajustar o zoom.")
            return
        alvo = fit_width_zoom(viewport_px=self.canvas.winfo_width(), page_px=int(self.page_rgb.shape[1]))
        if alvo is None:
            return
        self.apply_zoom(alvo, anchor=(0, 0))
        self._on_status(f"Zoom ajustado à largura: {int(alvo * 100)}%.")

    # --------------------------------------------------------------------- roda e arrasto

    def _pointer_over_canvas(self, event: tk.Event) -> bool:
        """Se o ponteiro está sobre a página.

        A roda é ligada com `bind_all` porque no Windows o `<MouseWheel>` vai para o widget com
        **foco**, e não para o que está sob o ponteiro: ligada só no canvas, ela não rolaria
        nada enquanto o cursor de texto estivesse no campo de FEN. Ligada na janela inteira, é
        esta função que devolve o comportamento que todo mundo espera -- rola o que está
        debaixo do mouse -- sem mexer no foco de ninguém.

        **A conta é aritmética de propósito.** A primeira versão perguntava ao
        `winfo_containing`, que no Windows resolve pelo `WindowFromPoint` do sistema: ele
        devolve `None` quando *qualquer* outra janela cobre aquele ponto da tela. Medido com a
        janela do app atrás do terminal, sobre um canvas de 909x740 na posição certa:
        `winfo_containing` devolveu `None` e a roda não rolava nada. Um retângulo comparado com
        as coordenadas do próprio widget não depende de empilhamento -- nem do tooltip que o
        painel abre justamente por cima dele.
        """
        if not self.canvas.winfo_exists() or not self.canvas.winfo_ismapped():
            return False
        x, y = self._canvas_event(event)
        return 0 <= x < self.canvas.winfo_width() and 0 <= y < self.canvas.winfo_height()

    def _canvas_event(self, event: tk.Event) -> tuple[int, int]:
        """O evento em coordenadas do canvas. Vem da janela, então o deslocamento é relativo."""
        return (
            int(event.x_root) - self.canvas.winfo_rootx(),
            int(event.y_root) - self.canvas.winfo_rooty(),
        )

    def _on_wheel(self, event: tk.Event) -> str | None:
        if not self._pointer_over_canvas(event) or self.page_rgb is None:
            return None

        direcao = wheel_direction(int(event.delta))
        decorrido = time.monotonic() - self._last_page_flip
        acao = decide_wheel(
            direction=direcao,
            view=self.canvas.yview(),
            flip_pages=bool(self.flip_pages_var.get()),
            since_last_flip=decorrido,
        )
        if acao is WheelAction.NEXT_PAGE:
            self._flip_page(+1)
        elif acao is WheelAction.PREV_PAGE:
            self._flip_page(-1)
        else:
            self.canvas.yview_scroll(-direcao * WHEEL_SCROLL_UNITS, "units")
        return "break"

    def _on_wheel_horizontal(self, event: tk.Event) -> str | None:
        if not self._pointer_over_canvas(event) or self.page_rgb is None:
            return None
        self.canvas.xview_scroll(-wheel_direction(int(event.delta)) * WHEEL_SCROLL_UNITS, "units")
        return "break"

    def _on_wheel_zoom(self, event: tk.Event) -> str | None:
        if not self._pointer_over_canvas(event) or self.page_rgb is None:
            return None
        direcao = wheel_direction(int(event.delta))
        self.apply_zoom(zoomed(self.zoom_var.get(), direcao), anchor=self._canvas_event(event))
        return "break"

    def _on_wheel_x11(self, event: tk.Event, *, delta: int) -> str | None:
        """Botões 4 e 5 do X11 traduzidos para o `delta` que o resto do painel entende.

        `event.state` é anotado como `int | str` no `tkinter`, e é `int` em evento de mouse --
        o `str` existe por causa dos eventos virtuais.
        """
        event.delta = delta
        estado = event.state if isinstance(event.state, int) else 0
        if estado & 0x0004:  # Control
            return self._on_wheel_zoom(event)
        if estado & 0x0001:  # Shift
            return self._on_wheel_horizontal(event)
        return self._on_wheel(event)

    def _flip_page(self, delta: int) -> None:
        """Vira a página pela roda, e põe a vista na borda por onde ela entrou.

        Entrar pelo topo ao descer e pelo rodapé ao subir é o que faz a sequência parecer um
        documento contínuo; cair sempre no topo faria a leitura para trás recomeçar a página.
        """
        antes = self.page_index
        if delta > 0:
            self.next_page()
        else:
            self.prev_page()
        if self.page_index == antes:
            return

        self._last_page_flip = time.monotonic()
        self.canvas.yview_moveto(0.0 if delta > 0 else 1.0)

    def _on_pan_start(self, event: tk.Event) -> None:
        self.canvas.scan_mark(event.x, event.y)
        self._panning = True
        self.canvas.configure(cursor="fleur")

    def _on_pan_move(self, event: tk.Event) -> None:
        if self._panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_pan_end(self, _event: tk.Event) -> None:
        self._panning = False
        self.canvas.configure(cursor="")

    def set_zoom(self, value: float) -> None:
        self.zoom_var.set(value)
        self.update_zoom_label()

    def update_zoom_label(self) -> None:
        self.lbl_zoom.config(text=f"{int(self.zoom_var.get() * 100)}%")

    def set_ocr_controls_enabled(self, enabled: bool) -> None:
        estado = tk.NORMAL if enabled else tk.DISABLED
        for botao in (self.btn_ocr_best, self.btn_ocr_all, self.btn_select):
            botao.configure(state=estado)

    def set_export_controls_enabled(self, enabled: bool) -> None:
        self.btn_export.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        # O cancelar só existe enquanto ha o que cancelar.
        self.btn_cancel_export.configure(state=tk.DISABLED if enabled else tk.NORMAL)

    def disable_cancel_button(self) -> None:
        self.btn_cancel_export.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------- abrir e navegar

    def open_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            title="Selecione o PDF",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            initialdir=str(self._initial_dir),
        )
        if filename:
            self.load_pdf(Path(filename))

    def open_in_system_reader(self) -> None:
        """Manda o PDF para o leitor do sistema. Falhar aqui é aviso, e não erro do app."""
        if self.source is None:
            return
        try:
            open_in_system_reader(self.source)
            self._on_status(f"{self.name} enviado para o leitor do sistema.")
        except Exception as exc:  # noqa: BLE001 - `startfile` e `Popen` levantam tipos diversos
            logger.warning("Não foi possível abrir %s no leitor do sistema: %s", self.source, exc)
            messagebox.showwarning(
                "Leitor do sistema",
                f"Não foi possível abrir o PDF no leitor do sistema:\n{exc}",
            )

    def load_pdf(self, pdf_path: Path) -> None:
        try:
            self._on_pdf_opened(pdf_path)
            self.source = pdf_path
            self.name = pdf_path.name
            self.page_count = get_pdf_page_count(pdf_path)
            self.lbl_pdf.config(text=f"{self.name} ({self.page_count} págs)")
            self.btn_system_reader.configure(state=tk.NORMAL)

            alvo = self._initial_page_for(pdf_path)
            self.page_index_var.set(max(0, min(self.page_count - 1, alvo)))
            self.spin_page.config(to=max(self.page_count - 1, 0))
            self.page_loaded_for_index = None
            self.render_current_page()
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao abrir PDF:\n{exc}")

    def on_page_spin(self) -> None:
        self.page_loaded_for_index = None
        self.render_current_page()

    def prev_page(self) -> None:
        if self.page_count == 0:
            return
        self.page_index_var.set(max(0, self.page_index - 1))
        self.page_loaded_for_index = None
        self.render_current_page()

    def next_page(self) -> None:
        if self.page_count == 0:
            return
        self.page_index_var.set(min(self.page_count - 1, self.page_index + 1))
        self.page_loaded_for_index = None
        self.render_current_page()

    def go_to_page(self, page_index: int) -> bool:
        """Vai para uma página qualquer. Devolve se **mudou** de página.

        Existe para a galeria (S-67), que navega por diagrama e precisa arrastar o
        visualizador junto. Devolver "mudou" e não "conseguiu" é o que impede o vaivém: a
        galeria só reage quando algo de fato se moveu.
        """
        if self.page_count == 0:
            return False
        alvo = max(0, min(self.page_count - 1, int(page_index)))
        if alvo == self.page_index:
            return False
        self.page_index_var.set(alvo)
        self.page_loaded_for_index = None
        self.render_current_page()
        return True

    def render_current_page(self) -> bool:
        """Rasteriza a página atual, se ainda não estiver em memória. `True` se há imagem.

        Devolve booleano porque quem chama precisa saber se pode seguir para o OCR: falhar
        aqui e prosseguir mandaria o serviço reconhecer a página anterior.
        """
        if self.source is None:
            return False

        idx = self.page_index
        if self.page_loaded_for_index == idx and self.page_rgb is not None:
            return True

        # As caixas da página anterior morrem aqui, e não quando as novas chegarem: a detecção
        # roda em thread, e deixá-las na tela nesse intervalo apontaria para diagramas da
        # página que acabou de sair -- sobre a imagem da que entrou.
        self.clear_diagram_boxes()
        # Antes de trocar de página, o que esta no editor tem de ir para o cache da página
        # de origem -- inclusive o texto que o usuário acabou de digitar no campo de FEN.
        self._on_before_page_change()
        try:
            self._on_status(f"Renderizando página {idx}...")
            self.page_rgb = render_pdf_page(self.source, idx, dpi=self._dpi())
            self.page_loaded_for_index = idx
            self.refresh_view()
            self._on_status(f"Página {idx} pronta.")
        except Exception as exc:
            self.page_rgb = None
            self.page_loaded_for_index = None
            messagebox.showerror("Erro", f"Falha ao renderizar página:\n{exc}")
            return False

        self._on_page_rendered(idx)
        return True

    def refresh_view(self, *, reset_scroll: bool = True) -> None:
        """Redesenha a página no zoom atual. `reset_scroll` desligado é o caminho do zoom.

        Página nova começa no topo; mudar o zoom, não -- ali quem manda é a âncora calculada
        por `apply_zoom`, e voltar ao topo antes dela jogaria fora o lugar onde a pessoa estava.
        """
        if self.page_rgb is None:
            return

        zoom = float(self.zoom_var.get())
        pil = Image.fromarray(self.page_rgb)
        alvo = (max(1, int(pil.width * zoom)), max(1, int(pil.height * zoom)))
        if alvo != (pil.width, pil.height):
            pil = pil.resize(alvo, Image.Resampling.LANCZOS)

        self._page_photo = ImageTk.PhotoImage(pil)
        self.canvas.delete("all")
        self._canvas_image_id = self.canvas.create_image(0, 0, anchor="nw", image=self._page_photo)
        self._select_rect_id = None
        self.canvas.configure(scrollregion=(0, 0, pil.width, pil.height))
        if reset_scroll:
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
        # Depois da imagem: `delete("all")` acima levou os retângulos junto, e eles dependem do
        # zoom que acabou de ser aplicado.
        self._draw_boxes()

    # ------------------------------------------------------------ diagramas marcados (S-68)

    def set_diagram_boxes(self, boxes: PageBoxes) -> bool:
        """Recebe as caixas de uma página. Devolve se elas eram **desta** página.

        A recusa é o que protege a tela do resultado atrasado: a detecção roda em thread, e
        quem a pediu para a página 16 pode já estar na 17 quando ela responde. Devolver
        booleano em vez de ignorar em silêncio deixa a janela registrar o descarte.
        """
        if boxes.page_index != self.page_index:
            logger.debug(
                "Caixas da página %d descartadas: a tela está na %d.", boxes.page_index, self.page_index
            )
            return False
        self.boxes = boxes
        self._draw_boxes()
        return True

    def clear_diagram_boxes(self) -> None:
        self.boxes = None
        self._selected_box = None
        self._hover_box = None
        self._draw_boxes()

    def select_box(self, index: int | None) -> None:
        """Marca qual diagrama está aberto no editor. `None` quando não é nenhum daqui."""
        if index == self._selected_box:
            return
        self._selected_box = index
        self._draw_boxes()

    def on_boxes_toggle(self) -> None:
        self._draw_boxes()
        self._on_prefs_changed()

    def _draw_boxes(self) -> None:
        """Redesenha os retângulos. Apagar por etiqueta, e não `delete("all")`: a página fica."""
        self.canvas.delete("diagram-box")
        self._update_boxes_label()
        if self.boxes is None or not self.show_boxes_var.get() or self.page_rgb is None:
            return

        zoom = float(self.zoom_var.get())
        for box in self.boxes.boxes:
            x0, y0, x1, y1 = self.boxes.rect_of(box, zoom)
            selecionado = box.index == self._selected_box
            cor = box_color(box)
            # Uma propriedade visual, uma informação: a **cor** diz em que ponto do trabalho o
            # diagrama está e a **hachura** diz qual está aberto no editor. Enquanto a seleção
            # era uma quarta cor, ela apagava o estado do diagrama selecionado -- justamente o
            # que se quer ver ao chegar nele.
            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline=cor,
                width=4 if selecionado else 2,
                fill=cor if selecionado else "",
                stipple="gray12" if selecionado else "",
                tags="diagram-box",
            )
            # O número vai num retângulo cheio: por cima do diagrama, texto solto some no
            # xadrez do tabuleiro justamente onde ele mais precisa ser lido.
            self.canvas.create_rectangle(
                x0, y0 - 18, x0 + 22, y0, outline=cor, fill=cor, tags="diagram-box"
            )
            self.canvas.create_text(
                x0 + 11, y0 - 9, text=box.label, fill="#101010", font=("Segoe UI", 9, "bold"),
                tags="diagram-box",
            )

    def _update_boxes_label(self) -> None:
        if self.boxes is None:
            self.lbl_boxes.config(text="")
        elif not len(self.boxes):
            self.lbl_boxes.config(text="nenhum diagrama nesta página")
        else:
            lidos = sum(1 for box in self.boxes.boxes if box.recognized and not box.saved)
            salvos = sum(1 for box in self.boxes.boxes if box.saved)
            partes = [f"{len(self.boxes)} diagrama(s)"]
            if lidos:
                partes.append(f"{lidos} lido(s)")
            if salvos:
                partes.append(f"{salvos} salvo(s)")
            self.lbl_boxes.config(text=" · ".join(partes))

    def _box_at_event(self, event: tk.Event) -> int | None:
        if self.boxes is None or not self.show_boxes_var.get() or self.page_rgb is None:
            return None
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        return self.boxes.index_at(x, y, float(self.zoom_var.get()))

    def _on_hover(self, event: tk.Event) -> None:
        """Mão sobre o diagrama. É o que faz o retângulo parecer clicável antes do clique."""
        if self._select_mode:
            return
        indice = self._box_at_event(event)
        if indice == self._hover_box:
            return
        self._hover_box = indice
        self.canvas.configure(cursor="hand2" if indice is not None else "")

    # -------------------------------------------------------------------- seleção de área

    def toggle_area_selection(self) -> None:
        if self._select_mode:
            self.disable_area_selection("Seleção de área cancelada.")
            return
        if self.source is None or self.page_rgb is None:
            messagebox.showwarning("Aviso", "Abra um PDF antes de selecionar uma área.")
            return

        self._select_mode = True
        self._select_start = None
        self._clear_overlay()
        self.canvas.configure(cursor="crosshair")
        self.btn_select.configure(text="Cancelar seleção")
        self._on_status("Seleção ativa: arraste no PDF para reconhecer a área automaticamente.")

    def disable_area_selection(self, status_text: str = "") -> None:
        self._select_mode = False
        self._select_start = None
        self._hover_box = None
        self._clear_overlay()
        self.canvas.configure(cursor="")
        self.btn_select.configure(text="Selecionar área (OCR)")
        if status_text:
            self._on_status(status_text)

    def _clear_overlay(self) -> None:
        if self._select_rect_id is None:
            return
        try:
            self.canvas.delete(self._select_rect_id)
        except tk.TclError as exc:
            logger.debug("Retangulo de seleção já removido: %s", exc)
        self._select_rect_id = None

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        if self.page_rgb is None:
            return x, y
        zoom = float(self.zoom_var.get())
        return (
            max(0.0, min(x, float(self.page_rgb.shape[1]) * zoom)),
            max(0.0, min(y, float(self.page_rgb.shape[0]) * zoom)),
        )

    def _point(self, event: tk.Event) -> tuple[float, float]:
        return self._clamp(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    def _on_press(self, event: tk.Event) -> None:
        self._press_at = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if not self._select_mode:
            # Fora do modo de seleção, o botão esquerdo é a mão do leitor: marca o ponto agora
            # e só arrasta se o ponteiro andar. Quem não andar continua sendo um clique, e o
            # clique continua abrindo o diagrama (S-68).
            self.canvas.scan_mark(event.x, event.y)
            return
        if self.page_rgb is None:
            return
        x, y = self._point(event)
        self._select_start = (x, y)
        self._clear_overlay()
        self._select_rect_id = self.canvas.create_rectangle(x, y, x, y, outline="#00ff88", width=2, dash=(6, 4))

    def _on_drag(self, event: tk.Event) -> None:
        if not self._select_mode:
            self._drag_page(event)
            return
        if self.page_rgb is None or self._select_start is None:
            return
        x, y = self._point(event)
        x0, y0 = self._select_start
        if self._select_rect_id is None:
            self._select_rect_id = self.canvas.create_rectangle(
                x0, y0, x, y, outline="#00ff88", width=2, dash=(6, 4)
            )
        else:
            self.canvas.coords(self._select_rect_id, x0, y0, x, y)

    def _drag_page(self, event: tk.Event) -> None:
        """A mão do leitor: arrastar com o botão esquerdo desloca a página.

        Só começa depois da folga do clique, e é isso que faz o mesmo botão servir para as duas
        coisas -- abrir o diagrama de baixo (S-68) e puxar a página. Sem a folga, quem arrasta
        abriria um diagrama ao soltar; sem o arrasto, a única forma de andar na página ampliada
        seria a barra de rolagem.
        """
        if self.page_rgb is None or self._press_at is None:
            return
        if not self._panning:
            andou = abs(self.canvas.canvasx(event.x) - self._press_at[0]) > CLICK_SLOP_PX or abs(
                self.canvas.canvasy(event.y) - self._press_at[1]
            ) > CLICK_SLOP_PX
            if not andou:
                return
            self._panning = True
            self.canvas.configure(cursor="fleur")
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_release(self, event: tk.Event) -> None:
        if self._panning:
            # Terminou um arrasto: a folga já garantiu que isto não era um clique.
            self._on_pan_end(event)
            self._press_at = None
            return
        if not self._select_mode:
            self._release_on_box(event)
            return
        if self.page_rgb is None or self._select_start is None:
            return

        x1, y1 = self._point(event)
        x0, y0 = self._select_start
        self.disable_area_selection()

        x0c, x1c = sorted((x0, x1))
        y0c, y1c = sorted((y0, y1))
        if (x1c - x0c) < MIN_SELECTION_PX or (y1c - y0c) < MIN_SELECTION_PX:
            self._on_status("Seleção muito pequena. Tente novamente.")
            return

        # Da coordenada do canvas para a do pixel da página -- a única parte que depende do
        # zoom. Recortar e grampear aos limites e do servico (S-31).
        zoom = float(self.zoom_var.get())
        regiao = (int(x0c / zoom), int(y0c / zoom), int(x1c / zoom), int(y1c / zoom))
        self._on_region(np.asarray(self.page_rgb).copy(), regiao)

    def _release_on_box(self, event: tk.Event) -> None:
        """Soltar o botão fora do modo de seleção: se foi clique, e acertou, avisa a janela.

        A distinção entre clique e arrasto é o que deixa a rolagem por arraste conviver com os
        diagramas marcados -- sem ela, todo empurrão na página abriria o diagrama de baixo.
        """
        if self._press_at is None:
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        x0, y0 = self._press_at
        self._press_at = None
        if abs(x - x0) > CLICK_SLOP_PX or abs(y - y0) > CLICK_SLOP_PX:
            return

        indice = self._box_at_event(event)
        if indice is not None:
            self._on_box_click(indice)
