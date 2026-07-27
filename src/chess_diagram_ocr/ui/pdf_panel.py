"""O lado direito da janela: o PDF, sua navegação e a seleção de área (S-31).

**O que ele guarda.** O documento aberto, a página renderizada e o zoom. Era estado do
`ChessOcrTkApp` misturado com o do OCR, e a mistura tinha consequência: `page_rgb`,
`page_loaded_for_index` e `pdf_source` eram lidos por métodos de reconhecimento espalhados
pela classe, então não havia como saber quem podia invalidá-los.

**O que ele não faz.** Não reconhece nada. A seleção de área devolve um retângulo em
coordenadas de **pixel da página**; recortar, grampear aos limites e decidir o que fazer
quando não há contorno é do `OcrService` (S-31). O painel só sabe converter coordenada de
canvas para coordenada de imagem, que é a única parte que depende do zoom.

**Os dois modos de visualização.** A aba "OCR" é o canvas com a página rasterizada -- é
sobre ela que a seleção acontece. A aba "Leitura" embute o visualizador do sistema via
WebView2, que pode não existir na máquina; quando não existe, a aba explica o motivo em vez
de ficar em branco.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page
from chess_diagram_ocr.webview2_panel import EmbeddedWebView2, WebView2SupportError

logger = logging.getLogger(__name__)

MIN_SELECTION_PX = 12
"""Arrasto menor que isto é clique errado, não seleção. Abaixo disso o recorte não
conteria nem uma casa do tabuleiro."""


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
    ) -> None:
        super().__init__(parent, padding=10)
        self._dpi = dpi
        self._initial_page_for = initial_page_for
        self._on_status = on_status
        self._on_region = on_region
        self._on_pdf_opened = on_pdf_opened
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

        self.reader_notice_var = tk.StringVar(value="Modo leitura pronto para carregar.")
        self._webview2: EmbeddedWebView2 | None = None

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

        self.view_tabs = ttk.Notebook(box)
        self.view_tabs.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ocr_tab = ttk.Frame(self.view_tabs)
        self.reader_tab = ttk.Frame(self.view_tabs)
        self.view_tabs.add(self.ocr_tab, text="OCR")
        self.view_tabs.add(self.reader_tab, text="Leitura")
        self.view_tabs.bind("<<NotebookTabChanged>>", lambda _event: self.on_view_mode_changed())

        wrap = ttk.Frame(self.ocr_tab)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(wrap, bg="#1c1c1c", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.canvas.yview)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll = ttk.Scrollbar(self.ocr_tab, orient=tk.HORIZONTAL, command=self.canvas.xview)
        hscroll.pack(fill=tk.X, pady=(0, 8))
        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        suportado, motivo = EmbeddedWebView2.is_supported()
        self._webview2_supported = suportado
        self.reader_host = ttk.Frame(self.reader_tab)
        self.reader_host.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            self.reader_host, textvariable=self.reader_notice_var, justify=tk.LEFT, wraplength=560
        ).pack(anchor="nw", padx=12, pady=12)
        if not suportado:
            self.reader_notice_var.set(f"Leitura via WebView2 indisponível.\n{motivo}")

    # ------------------------------------------------------------------------------- zoom

    @property
    def page_index(self) -> int:
        return int(self.page_index_var.get())

    def zoom(self, delta: float) -> None:
        novo = max(0.25, min(2.0, self.zoom_var.get() + delta))
        self.zoom_var.set(novo)
        self.update_zoom_label()
        self.refresh_view()
        self._on_zoom_changed(novo)

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

    def load_pdf(self, pdf_path: Path) -> None:
        try:
            self._on_pdf_opened(pdf_path)
            self.source = pdf_path
            self.name = pdf_path.name
            self.page_count = get_pdf_page_count(pdf_path)
            self.lbl_pdf.config(text=f"{self.name} ({self.page_count} págs)")

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

    def refresh_view(self) -> None:
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
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._sync_reader()

    # ------------------------------------------------------------------------ modo leitura

    def is_reader_mode(self) -> bool:
        atual = self.view_tabs.select()
        return bool(atual) and atual == str(self.reader_tab)

    def on_view_mode_changed(self) -> None:
        if self.is_reader_mode():
            # Seleção de área e do canvas; deixa-la ligada ao trocar de aba faria o botao
            # dizer "Cancelar seleção" sobre uma tela onde não se pode selecionar nada.
            self.disable_area_selection()
            self._ensure_reader()
            self._sync_reader()
            if self._webview2 is not None:
                self._webview2.show()
        elif self._webview2 is not None:
            self._webview2.hide()

    def _on_reader_error(self, message: str) -> None:
        self.after(0, lambda: self.reader_notice_var.set(f"Falha ao iniciar WebView2:\n{message}"))

    def _ensure_reader(self) -> None:
        if not self._webview2_supported:
            return
        if self._webview2 is not None:
            self._webview2.resize()
            return

        try:
            self.reader_notice_var.set("Inicializando leitura via WebView2...")
            painel = EmbeddedWebView2(self.reader_host, error_cb=self._on_reader_error)
            painel.ensure_started()
            self._webview2 = painel
            self.reader_host.bind("<Configure>", lambda _event: self._resize_reader())
            self.reader_notice_var.set("Leitura via WebView2 pronta.")
        except WebView2SupportError as exc:
            self._webview2_supported = False
            self.reader_notice_var.set(f"Leitura via WebView2 indisponível.\n{exc}")

    def destroy_reader(self) -> None:
        """Fecha o WebView2 ao encerrar a janela: ele e um processo, não um widget."""
        if self._webview2 is not None:
            self._webview2.destroy()
            self._webview2 = None

    def _resize_reader(self) -> None:
        if self._webview2 is not None:
            self._webview2.resize()

    def _sync_reader(self) -> None:
        if not self.is_reader_mode() or self.source is None:
            return
        self._ensure_reader()
        if self._webview2 is None:
            return
        try:
            self._webview2.load_pdf(self.source, self.page_index)
        except WebView2SupportError as exc:
            self.reader_notice_var.set(f"Leitura via WebView2 indisponível.\n{exc}")

    # -------------------------------------------------------------------- seleção de área

    def toggle_area_selection(self) -> None:
        if self.is_reader_mode():
            self.view_tabs.select(self.ocr_tab)
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
        if not self._select_mode or self.page_rgb is None:
            return
        x, y = self._point(event)
        self._select_start = (x, y)
        self._clear_overlay()
        self._select_rect_id = self.canvas.create_rectangle(x, y, x, y, outline="#00ff88", width=2, dash=(6, 4))

    def _on_drag(self, event: tk.Event) -> None:
        if not self._select_mode or self.page_rgb is None or self._select_start is None:
            return
        x, y = self._point(event)
        x0, y0 = self._select_start
        if self._select_rect_id is None:
            self._select_rect_id = self.canvas.create_rectangle(
                x0, y0, x, y, outline="#00ff88", width=2, dash=(6, 4)
            )
        else:
            self.canvas.coords(self._select_rect_id, x0, y0, x, y)

    def _on_release(self, event: tk.Event) -> None:
        if not self._select_mode or self.page_rgb is None or self._select_start is None:
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
