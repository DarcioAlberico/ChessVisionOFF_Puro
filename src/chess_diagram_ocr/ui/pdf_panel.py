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
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page

from .page_overlay import PageBoxes
from .tooltip import Tooltip

logger = logging.getLogger(__name__)

MIN_SELECTION_PX = 12
"""Arrasto menor que isto é clique errado, não seleção. Abaixo disso o recorte não
conteria nem uma casa do tabuleiro."""

CLICK_SLOP_PX = 4
"""Quanto o ponteiro pode andar entre apertar e soltar e ainda ser um clique.

Sem folga, o clique de quem apoia a mão no mouse vira arrasto e não abre diagrama nenhum;
com folga demais, arrastar a barra de rolagem abriria um diagrama por acidente."""

BOX_OUTLINE = "#4da3ff"
"""Diagrama localizado e ainda não lido."""

BOX_OUTLINE_RECOGNIZED = "#00c07a"
"""Diagrama já lido. Verde, mas não o `#00ff88` do retângulo de seleção: os dois podem
aparecer na mesma tela, e são coisas diferentes -- um é o que o detector achou, o outro é o
que a sua mão está desenhando agora."""

BOX_OUTLINE_SELECTED = "#ffb02e"
"""O diagrama que está aberto no editor. Cor própria e traço mais grosso, porque este é o
vínculo entre as duas metades da janela -- é ele que responde "qual desses eu estou vendo?"."""


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
        on_boxes_toggled: Callable[[bool], None] = lambda _ligado: None,
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

        self._on_boxes_toggled = on_boxes_toggled
        """A marcação foi ligada ou desligada. Existe para o estado da aplicação lembrar."""
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
        ligado = bool(self.show_boxes_var.get())
        self._draw_boxes()
        self._on_boxes_toggled(ligado)

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
            cor = (
                BOX_OUTLINE_SELECTED
                if selecionado
                else (BOX_OUTLINE_RECOGNIZED if box.recognized else BOX_OUTLINE)
            )
            self.canvas.create_rectangle(
                x0, y0, x1, y1, outline=cor, width=3 if selecionado else 2, tags="diagram-box"
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
            lidos = sum(1 for box in self.boxes.boxes if box.recognized)
            sufixo = f", {lidos} lido(s)" if lidos else ""
            self.lbl_boxes.config(text=f"{len(self.boxes)} diagrama(s){sufixo}")

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
