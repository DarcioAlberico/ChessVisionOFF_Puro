from __future__ import annotations

import io
import json
import logging
import threading
import tkinter as tk
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import chess
import chess.pgn
import cv2
import numpy as np
from PIL import Image, ImageTk

from chess_diagram_ocr.board_detection import detect_boards
from chess_diagram_ocr.config import (
    BOARD_SIZE,
    DEFAULT_DATASET_CSV,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_SAMPLES_DIR,
    find_default_pdf_path,
)
from chess_diagram_ocr.dataset import append_training_sample
from chess_diagram_ocr.detection import detect_diagrams_in_pdf_page
from chess_diagram_ocr.fen_utils import board_from_fen, is_valid_fen, square_name
from chess_diagram_ocr.inference import load_model, predict_with_orientation
from chess_diagram_ocr.logging_setup import configure_logging, default_log_file
from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page
from chess_diagram_ocr.pdf_to_pgn import ExportReport, default_pgn_output_path, save_pdf_positions_to_pgn
from chess_diagram_ocr.training import train_model
from chess_diagram_ocr.webview2_panel import EmbeddedWebView2, WebView2SupportError

ROOT = Path(__file__).resolve().parent
PIECE_IMAGE_DIR = ROOT / "assets" / "piece_images"
APP_STATE_PATH = ROOT / "data" / "app_tkinter_state.json"

logger = logging.getLogger(__name__)

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

NET_CORRECT_URL = "https://helpman.komtera.lt/predict"


class ChessOcrTkApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Chess Diagram OCR - Tkinter")
        self.root.geometry("1700x980")

        self.pdf_source: Any = None
        self.pdf_name: str = ""
        self.page_count = 0
        self.page_rgb: np.ndarray | None = None
        self.page_loaded_for_index: int | None = None
        self.result_items: list[dict[str, Any]] = []
        self.fen_edits: list[str] = []
        self.study_board = chess.Board()
        self.study_game = chess.pgn.Game()
        self.study_game.setup(self.study_board.copy(stack=False))
        self.study_current_node: chess.pgn.GameNode = self.study_game
        self.study_selected_square: int | None = None
        self.study_drag_from_square: int | None = None
        self.study_drag_piece: chess.Piece | None = None
        self.study_drag_pointer: tuple[float, float] | None = None
        self.study_drag_start_pointer: tuple[float, float] | None = None
        self.study_drag_active = False
        self.study_press_selected_new_piece = False
        self.study_origin_var = tk.StringVar(value="Base: posicao inicial")
        self.study_status_var = tk.StringVar(value="")
        self.study_fen_var = tk.StringVar(value=self.study_board.fen())
        self.study_variation_var = tk.StringVar(value="")
        self.study_follow_ocr_var = tk.BooleanVar(value=True)
        self.study_flipped_var = tk.BooleanVar(value=False)
        self.left_tabs: ttk.Notebook | None = None
        self.local_results_tab: ttk.Frame | None = None
        self.board_canvas: tk.Canvas | None = None
        self.study_canvas: tk.Canvas | None = None
        self.study_moves_text: tk.Text | None = None
        self.study_variation_combo: ttk.Combobox | None = None
        self._study_board_geom: dict[str, float] = {}

        self._model_cache = None
        self._model_cache_path: Path | None = None
        self._model_device: str | None = None

        self.page_photo: ImageTk.PhotoImage | None = None
        self._piece_image_sources = self._load_piece_image_sources()
        self._piece_photo_cache: dict[tuple[str, int], ImageTk.PhotoImage] = {}

        self.model_path_var = tk.StringVar(value=str(DEFAULT_MODEL_PATH))
        self.dataset_csv_var = tk.StringVar(value=str(DEFAULT_DATASET_CSV))
        self.samples_dir_var = tk.StringVar(value=str(DEFAULT_SAMPLES_DIR))
        self.orientation_var = tk.StringVar(value=DEFAULT_ORIENTATION_MODE)
        self.page_index_var = tk.IntVar(value=0)
        self.dpi_var = tk.IntVar(value=220)
        self.max_boards_var = tk.IntVar(value=8)
        self.selected_diag_var = tk.IntVar(value=1)
        self.selected_diag_idx = 0
        self.fen_var = tk.StringVar(value="")
        self.epochs_var = tk.IntVar(value=8)
        self.batch_var = tk.IntVar(value=128)
        self.lr_var = tk.DoubleVar(value=0.001)
        self.pdf_zoom_var = tk.DoubleVar(value=0.7)
        self.board_zoom_var = tk.DoubleVar(value=0.85)
        self.main_pane: tk.PanedWindow | None = None
        self.btn_train_model: ttk.Button | None = None
        self.train_dialog: tk.Toplevel | None = None
        self.train_progress: ttk.Progressbar | None = None
        self.train_dialog_status_var = tk.StringVar(value="")
        self.train_dialog_metrics_var = tk.StringVar(value="")
        self._is_training = False
        self._training_total_epochs = 0
        self.btn_correct_net: ttk.Button | None = None
        self._is_correcting_net = False
        self.btn_ocr_local_best: ttk.Button | None = None
        self.btn_ocr_local_all: ttk.Button | None = None
        self.btn_ocr_best: ttk.Button | None = None
        self.btn_ocr_all: ttk.Button | None = None
        self.btn_pdf_select: ttk.Button | None = None
        self.btn_export_pdf_pgn: ttk.Button | None = None
        self._is_exporting_pdf_pgn = False
        self._is_running_ocr = False
        self._pdf_select_mode = False
        self._pdf_select_start_canvas: tuple[float, float] | None = None
        self._pdf_select_rect_id: int | None = None
        self.pdf_view_tabs: ttk.Notebook | None = None
        self.pdf_ocr_tab: ttk.Frame | None = None
        self.pdf_reader_tab: ttk.Frame | None = None
        self.pdf_reader_host: ttk.Frame | None = None
        self.pdf_reader_notice_var = tk.StringVar(value="Modo leitura pronto para carregar.")
        self._webview2_panel: EmbeddedWebView2 | None = None
        self._webview2_supported = False
        self._webview2_support_reason = ""

        self._build_ui()
        self._update_zoom_labels()
        self._refresh_study_view()
        self._set_study_status("Clique em uma peca para estudar.")
        self._restore_state_or_default_pdf()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(180, self._set_initial_sashes)

    def _build_ui(self) -> None:
        self.main_pane = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            sashrelief=tk.RAISED,
            sashwidth=10,
            showhandle=True,
            handlesize=10,
        )
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        self.left_frame = ttk.Frame(self.main_pane, padding=10)
        self.right_frame = ttk.Frame(self.main_pane, padding=10)
        self.main_pane.add(self.left_frame, minsize=420)
        self.main_pane.add(self.right_frame, minsize=520)

        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        tabs = ttk.Notebook(self.left_frame)
        tabs.pack(fill=tk.BOTH, expand=True)
        self.left_tabs = tabs

        cfg_tab = ttk.Frame(tabs, padding=6)
        local_tab = ttk.Frame(tabs, padding=6)
        self.local_results_tab = local_tab
        analysis_tab = ttk.Frame(tabs, padding=6)
        tabs.add(cfg_tab, text="Configuracao")
        tabs.add(local_tab, text="Imagem local")
        tabs.add(analysis_tab, text="Analise")

        self._entry_row(cfg_tab, "Modelo (.pt)", self.model_path_var)
        self._entry_row(cfg_tab, "CSV labels", self.dataset_csv_var)
        self._entry_row(cfg_tab, "Pasta samples", self.samples_dir_var)

        # Tri-estado no lugar do checkbox: "auto" decide por diagrama, o que resolve livro
        # com orientacoes misturadas -- o booleano valia para todos de uma vez (S-13).
        orient_row = ttk.Frame(cfg_tab)
        orient_row.pack(anchor="w", fill="x", padx=8, pady=4)
        ttk.Label(orient_row, text="Orientacao do diagrama", width=24).pack(side="left")
        for rotulo, valor in (("Automatica", "auto"), ("0 graus", "0"), ("180 graus", "180")):
            ttk.Radiobutton(orient_row, text=rotulo, value=valor, variable=self.orientation_var).pack(side="left", padx=4)
        self._spin_row(cfg_tab, "DPI", self.dpi_var, 120, 320, 20)
        self._spin_row(cfg_tab, "Max diagramas", self.max_boards_var, 1, 20, 1)

        btns_model = ttk.Frame(cfg_tab)
        btns_model.pack(fill=tk.X, padx=8, pady=(4, 8))
        ttk.Button(btns_model, text="Recarregar modelo", command=self.reload_model).pack(side=tk.LEFT)

        train_box = ttk.LabelFrame(cfg_tab, text="Treino (salva em piece_classifier.pt)")
        train_box.pack(fill=tk.X, padx=8, pady=(4, 8))
        self._spin_row(train_box, "Epocas", self.epochs_var, 1, 200, 1)
        self._spin_row(train_box, "Batch size", self.batch_var, 16, 512, 16)
        self._entry_row(train_box, "Learning rate", self.lr_var)
        self.btn_train_model = ttk.Button(train_box, text="Treinar modelo", command=self.train_model_in_thread)
        self.btn_train_model.pack(anchor="w", padx=8, pady=8)

        local_btns = ttk.Frame(local_tab)
        local_btns.pack(fill=tk.X, padx=8, pady=8)
        self.btn_ocr_local_best = ttk.Button(local_btns, text="OCR local (melhor)", command=self.ocr_local_best)
        self.btn_ocr_local_best.pack(side=tk.LEFT)
        self.btn_ocr_local_all = ttk.Button(local_btns, text="OCR local (todos)", command=self.ocr_local_all)
        self.btn_ocr_local_all.pack(side=tk.LEFT, padx=6)
        ttk.Label(local_tab, text="Use imagem local para OCR fora do PDF.").pack(anchor="w", padx=8, pady=(2, 8))

        rec_box = ttk.LabelFrame(local_tab, text="Reconhecido (SVG)")
        rec_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        zoom_row = ttk.Frame(rec_box)
        zoom_row.pack(fill=tk.X, padx=8, pady=(6, 0))
        ttk.Label(zoom_row, text="Zoom board").pack(side=tk.LEFT)
        ttk.Button(zoom_row, text="-", width=3, command=lambda: self.zoom_board(-0.1)).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(zoom_row, text="+", width=3, command=lambda: self.zoom_board(0.1)).pack(side=tk.LEFT, padx=(2, 6))
        self.lbl_board_zoom = ttk.Label(zoom_row, text="85%")
        self.lbl_board_zoom.pack(side=tk.LEFT)

        self.board_canvas = tk.Canvas(rec_box, width=440, height=440, bg="#f2f2f2", highlightthickness=0)
        self.board_canvas.pack(padx=8, pady=8)
        self.board_canvas.bind("<Map>", lambda _event: self._redraw_current_result_board())

        nav_diag = ttk.Frame(rec_box)
        nav_diag.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(nav_diag, text="Diagrama anterior", command=self.prev_diagram).pack(side=tk.LEFT)
        ttk.Button(nav_diag, text="Proximo diagrama", command=self.next_diagram).pack(side=tk.LEFT, padx=6)
        ttk.Label(nav_diag, text="Selecionado").pack(side=tk.LEFT, padx=(12, 4))
        self.spin_diag = ttk.Spinbox(
            nav_diag,
            from_=1,
            to=1,
            textvariable=self.selected_diag_var,
            width=6,
            command=self.on_diagram_spin,
        )
        self.spin_diag.pack(side=tk.LEFT)
        self.spin_diag.bind("<Return>", lambda _event: self.on_diagram_spin())
        self.spin_diag.bind("<FocusOut>", lambda _event: self.on_diagram_spin())

        fen_box = ttk.LabelFrame(local_tab, text="FEN e acoes")
        fen_box.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(fen_box, text="FEN").pack(anchor="w", padx=8, pady=(6, 0))
        fen_entry = ttk.Entry(fen_box, textvariable=self.fen_var)
        fen_entry.pack(fill=tk.X, padx=8, pady=(0, 4))
        fen_entry.bind("<Return>", lambda _event: self.apply_fen_edit())
        apply_row = ttk.Frame(fen_box)
        apply_row.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(apply_row, text="Aplicar FEN", command=self.apply_fen_edit).pack(side=tk.LEFT)
        ttk.Button(apply_row, text="Salvar posição reconhecida", command=self.save_current).pack(side=tk.LEFT, padx=6)
        ttk.Button(apply_row, text="Salvar todos", command=self.save_all).pack(side=tk.LEFT, padx=6)
        self.btn_correct_net = ttk.Button(apply_row, text="Corrigir Net", command=self.correct_fen_with_net)
        self.btn_correct_net.pack(side=tk.LEFT, padx=6)

        self._build_study_tab(analysis_tab)
        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(self.left_frame, textvariable=self.status_var).pack(anchor="w", pady=(6, 0))

    def _set_initial_sashes(self) -> None:
        try:
            if self.main_pane is not None:
                total_w = max(1, self.main_pane.winfo_width())
                self.main_pane.sash_place(0, int(total_w * 0.42), 0)
        except tk.TclError as exc:
            # Erro transitorio de geometria enquanto o primeiro layout se estabiliza.
            logger.debug("Nao foi possivel posicionar o divisor inicial: %s", exc)

    def _build_study_tab(self, parent: ttk.Frame) -> None:
        top_row = ttk.Frame(parent)
        top_row.pack(fill=tk.X, padx=4, pady=(0, 4))
        ttk.Button(top_row, text="Carregar OCR atual", command=self.load_study_from_recognized).pack(side=tk.LEFT)
        ttk.Button(top_row, text="Posicao inicial", command=self.load_study_initial_position).pack(side=tk.LEFT, padx=6)
        ttk.Button(top_row, text="Virar board", command=self.flip_study_board).pack(side=tk.LEFT, padx=6)
        ttk.Button(top_row, text="Trocar vez", command=self.toggle_study_turn).pack(side=tk.LEFT, padx=6)
        ttk.Button(top_row, text="Salvar PGN", command=self.save_study_pgn).pack(side=tk.LEFT, padx=6)

        action_row = ttk.Frame(parent)
        action_row.pack(fill=tk.X, padx=4, pady=(0, 6))
        ttk.Button(action_row, text="|<", width=4, command=self.go_to_start_of_study_line).pack(side=tk.LEFT)
        ttk.Button(action_row, text="<", width=4, command=self.undo_study_move).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(action_row, text=">", width=4, command=self.redo_study_move).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(action_row, text=">|", width=4, command=self.go_to_end_of_study_line).pack(side=tk.LEFT, padx=(6, 6))
        ttk.Button(action_row, text="Aplicar FEN", command=self.apply_study_fen).pack(side=tk.LEFT, padx=6)
        ttk.Button(action_row, text="Copiar FEN", command=self.copy_study_fen).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(
            action_row,
            text="Seguir OCR selecionado",
            variable=self.study_follow_ocr_var,
            command=self.on_study_follow_ocr_toggle,
        ).pack(side=tk.RIGHT)

        variation_row = ttk.Frame(parent)
        variation_row.pack(fill=tk.X, padx=4, pady=(0, 6))
        ttk.Label(variation_row, text="Continuacoes").pack(side=tk.LEFT)
        self.study_variation_combo = ttk.Combobox(variation_row, textvariable=self.study_variation_var, state="readonly", width=46)
        self.study_variation_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.study_variation_combo.bind("<<ComboboxSelected>>", lambda _event: self._set_study_status("Continuacao selecionada."))
        ttk.Button(variation_row, text="Entrar", command=self.redo_study_move).pack(side=tk.LEFT)

        ttk.Label(parent, textvariable=self.study_origin_var).pack(anchor="w", padx=6)
        ttk.Label(parent, textvariable=self.study_status_var, wraplength=620).pack(anchor="w", padx=6, pady=(0, 6))

        ttk.Label(parent, text="FEN do estudo").pack(anchor="w", padx=6)
        study_entry = ttk.Entry(parent, textvariable=self.study_fen_var)
        study_entry.pack(fill=tk.X, padx=6, pady=(0, 6))
        study_entry.bind("<Return>", lambda _event: self.apply_study_fen())

        self.study_canvas = tk.Canvas(parent, width=430, height=430, bg="#262421", highlightthickness=0, cursor="hand2")
        self.study_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.study_canvas.bind("<ButtonPress-1>", self.on_study_board_press)
        self.study_canvas.bind("<B1-Motion>", self.on_study_board_drag)
        self.study_canvas.bind("<ButtonRelease-1>", self.on_study_board_release)
        self.study_canvas.bind("<Left>", lambda _event: self.undo_study_move())
        self.study_canvas.bind("<Right>", lambda _event: self.redo_study_move())
        self.study_canvas.bind("<Home>", lambda _event: self.go_to_start_of_study_line())
        self.study_canvas.bind("<End>", lambda _event: self.go_to_end_of_study_line())
        self.study_canvas.bind("<Configure>", lambda _event: self._draw_study_board())

        move_box = ttk.LabelFrame(parent, text="Linha de estudo")
        move_box.pack(fill=tk.BOTH, expand=False, padx=6, pady=(0, 2))
        self.study_moves_text = tk.Text(move_box, height=5, wrap="word", font=("Consolas", 10), state=tk.DISABLED)
        self.study_moves_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _build_right_panel(self) -> None:
        pdf_box = ttk.LabelFrame(self.right_frame, text="PDF (direita)")
        pdf_box.pack(fill=tk.BOTH, expand=True)

        row_pdf = ttk.Frame(pdf_box)
        row_pdf.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(row_pdf, text="Abrir PDF", command=self.open_pdf).pack(side=tk.LEFT)
        self.lbl_pdf = ttk.Label(row_pdf, text="Nenhum PDF")
        self.lbl_pdf.pack(side=tk.LEFT, padx=8)

        nav_row = ttk.Frame(pdf_box)
        nav_row.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(nav_row, text="Pagina anterior", command=self.prev_page).pack(side=tk.LEFT)
        ttk.Button(nav_row, text="Proxima pagina", command=self.next_page).pack(side=tk.LEFT, padx=6)
        ttk.Label(nav_row, text="Pagina").pack(side=tk.LEFT, padx=(12, 4))
        self.spin_page = ttk.Spinbox(
            nav_row,
            from_=0,
            to=0,
            textvariable=self.page_index_var,
            width=8,
            command=self.on_page_spin,
        )
        self.spin_page.pack(side=tk.LEFT)

        ocr_row = ttk.Frame(pdf_box)
        ocr_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.btn_ocr_best = ttk.Button(ocr_row, text="OCR melhor diagrama", command=self.ocr_best)
        self.btn_ocr_best.pack(side=tk.LEFT)
        self.btn_ocr_all = ttk.Button(ocr_row, text="OCR todos diagramas", command=self.ocr_all)
        self.btn_ocr_all.pack(side=tk.LEFT, padx=6)
        self.btn_pdf_select = ttk.Button(ocr_row, text="Selecionar area (OCR)", command=self.toggle_pdf_area_selection)
        self.btn_pdf_select.pack(side=tk.LEFT, padx=6)
        self.btn_export_pdf_pgn = ttk.Button(ocr_row, text="Exportar PDF -> PGN", command=self.export_pdf_to_pgn)
        self.btn_export_pdf_pgn.pack(side=tk.LEFT, padx=6)

        zoom_row_pdf = ttk.Frame(pdf_box)
        zoom_row_pdf.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(zoom_row_pdf, text="Zoom PDF").pack(side=tk.LEFT)
        ttk.Button(zoom_row_pdf, text="-", width=3, command=lambda: self.zoom_pdf(-0.1)).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(zoom_row_pdf, text="+", width=3, command=lambda: self.zoom_pdf(0.1)).pack(side=tk.LEFT, padx=(2, 6))
        self.lbl_pdf_zoom = ttk.Label(zoom_row_pdf, text="70%")
        self.lbl_pdf_zoom.pack(side=tk.LEFT)

        self.pdf_view_tabs = ttk.Notebook(pdf_box)
        self.pdf_view_tabs.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.pdf_ocr_tab = ttk.Frame(self.pdf_view_tabs)
        self.pdf_reader_tab = ttk.Frame(self.pdf_view_tabs)
        self.pdf_view_tabs.add(self.pdf_ocr_tab, text="OCR")
        self.pdf_view_tabs.add(self.pdf_reader_tab, text="Leitura")
        self.pdf_view_tabs.bind("<<NotebookTabChanged>>", lambda _event: self.on_pdf_view_mode_changed())

        canvas_wrap = ttk.Frame(self.pdf_ocr_tab)
        canvas_wrap.pack(fill=tk.BOTH, expand=True)
        self.pdf_canvas = tk.Canvas(canvas_wrap, bg="#1c1c1c", highlightthickness=0)
        self.pdf_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.pdf_vscroll = ttk.Scrollbar(canvas_wrap, orient=tk.VERTICAL, command=self.pdf_canvas.yview)
        self.pdf_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.pdf_hscroll = ttk.Scrollbar(self.pdf_ocr_tab, orient=tk.HORIZONTAL, command=self.pdf_canvas.xview)
        self.pdf_hscroll.pack(fill=tk.X, pady=(0, 8))
        self.pdf_canvas.configure(yscrollcommand=self.pdf_vscroll.set, xscrollcommand=self.pdf_hscroll.set)
        self.pdf_canvas_image_id: int | None = None
        self.pdf_canvas.bind("<ButtonPress-1>", self._on_pdf_canvas_button_press)
        self.pdf_canvas.bind("<B1-Motion>", self._on_pdf_canvas_drag)
        self.pdf_canvas.bind("<ButtonRelease-1>", self._on_pdf_canvas_button_release)

        supported, reason = EmbeddedWebView2.is_supported()
        self._webview2_supported = supported
        self._webview2_support_reason = reason
        self.pdf_reader_host = ttk.Frame(self.pdf_reader_tab)
        self.pdf_reader_host.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            self.pdf_reader_host,
            textvariable=self.pdf_reader_notice_var,
            justify=tk.LEFT,
            wraplength=560,
        ).pack(anchor="nw", padx=12, pady=12)
        if not supported:
            self.pdf_reader_notice_var.set(f"Leitura via WebView2 indisponivel.\n{reason}")

    def _entry_row(self, parent: ttk.Widget, label: str, var: Any) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _spin_row(self, parent: ttk.Widget, label: str, var: tk.Variable, frm: int, to: int, inc: int) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=frm, to=to, increment=inc, textvariable=var, width=12).pack(side=tk.LEFT)

    def _set_default_pdf_if_exists(self) -> None:
        default_pdf = find_default_pdf_path()
        if default_pdf is not None and default_pdf.exists():
            self.load_pdf(default_pdf)

    def _restore_state_or_default_pdf(self) -> None:
        if not self._load_app_state():
            self._set_default_pdf_if_exists()

    def _load_app_state(self) -> bool:
        if not APP_STATE_PATH.exists():
            return False
        try:
            raw = APP_STATE_PATH.read_text(encoding="utf-8")
            state = json.loads(raw)
            if not isinstance(state, dict):
                return False

            pdf_zoom = state.get("pdf_zoom")
            if isinstance(pdf_zoom, (int, float)):
                self.pdf_zoom_var.set(max(0.25, min(2.0, float(pdf_zoom))))
                self._update_zoom_labels()

            last_pdf = state.get("last_pdf")
            if not isinstance(last_pdf, str) or not last_pdf.strip():
                return False
            pdf_path = Path(last_pdf)
            if not pdf_path.exists():
                self._set_status(f"Ultimo PDF nao encontrado: {pdf_path}")
                return False

            self.load_pdf(pdf_path)

            last_page = state.get("last_page")
            if isinstance(last_page, int) and self.page_count > 0:
                clamped_page = max(0, min(self.page_count - 1, last_page))
                if clamped_page != int(self.page_index_var.get()):
                    self.page_index_var.set(clamped_page)
                    self.page_loaded_for_index = None
                    self.render_current_page()
            return True
        except (OSError, json.JSONDecodeError, ValueError, tk.TclError) as exc:
            logger.warning("Estado da aplicacao ignorado (%s): %s", APP_STATE_PATH, exc)
            return False

    def _save_app_state(self) -> None:
        try:
            state = {}
            if APP_STATE_PATH.exists():
                try:
                    state = json.loads(APP_STATE_PATH.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning("Estado anterior corrompido, sera sobrescrito: %s", exc)

            pdf_history = state.get("pdf_history", {})
            if self.pdf_source is not None:
                pdf_key = str(self.pdf_source.resolve())
                pdf_history[pdf_key] = int(self.page_index_var.get())

            state["last_pdf"] = str(self.pdf_source) if self.pdf_source is not None else ""
            state["last_page"] = int(self.page_index_var.get())
            state["pdf_zoom"] = float(self.pdf_zoom_var.get())
            state["pdf_history"] = pdf_history

            APP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            APP_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, TypeError, ValueError, tk.TclError) as exc:
            # Falhar em salvar o estado nao deve derrubar a aplicacao. Escrita atomica: ver S-25.
            logger.warning("Nao foi possivel salvar o estado da aplicacao: %s", exc)

    def _on_close(self) -> None:
        self._save_app_state()
        if self._webview2_panel is not None:
            self._webview2_panel.destroy()
        self.root.destroy()

    def _set_status(self, text: str) -> None:
        def _apply() -> None:
            self.status_var.set(text)
            self.root.update_idletasks()

        if threading.current_thread() is threading.main_thread():
            _apply()
        else:
            self.root.after(0, _apply)

    def _set_train_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        if self.btn_train_model is not None:
            self.btn_train_model.configure(state=state)

    def _set_ocr_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in (
            self.btn_ocr_local_best,
            self.btn_ocr_local_all,
            self.btn_ocr_best,
            self.btn_ocr_all,
            self.btn_pdf_select,
        ):
            if button is not None:
                button.configure(state=state)

    def _set_pdf_export_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        if self.btn_export_pdf_pgn is not None:
            self.btn_export_pdf_pgn.configure(state=state)

    def _open_training_dialog(self) -> None:
        if self.train_dialog is not None and self.train_dialog.winfo_exists():
            self.train_dialog.deiconify()
            self.train_dialog.lift()
            if self.train_progress is not None:
                self.train_progress.start(10)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Treinando modelo")
        dlg.geometry("520x170")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.protocol("WM_DELETE_WINDOW", dlg.withdraw)

        wrap = ttk.Frame(dlg, padding=12)
        wrap.pack(fill=tk.BOTH, expand=True)
        ttk.Label(wrap, text="Status do treino").pack(anchor="w")
        ttk.Label(wrap, textvariable=self.train_dialog_status_var, wraplength=480).pack(anchor="w", pady=(6, 0))
        ttk.Label(wrap, textvariable=self.train_dialog_metrics_var, wraplength=480).pack(anchor="w", pady=(4, 0))

        self.train_progress = ttk.Progressbar(wrap, mode="indeterminate")
        self.train_progress.pack(fill=tk.X, pady=(10, 0))
        self.train_progress.start(10)
        self.train_dialog = dlg

    def _set_training_dialog_text(self, status_text: str, metrics_text: str = "") -> None:
        def _apply() -> None:
            self.train_dialog_status_var.set(status_text)
            self.train_dialog_metrics_var.set(metrics_text)

        if threading.current_thread() is threading.main_thread():
            _apply()
        else:
            self.root.after(0, _apply)

    def _close_training_dialog(self) -> None:
        if self.train_progress is not None:
            self.train_progress.stop()
            self.train_progress = None
        if self.train_dialog is not None and self.train_dialog.winfo_exists():
            self.train_dialog.destroy()
        self.train_dialog = None

    def _format_train_metrics(self, row: dict[str, Any]) -> str:
        parts = []
        epoch = row.get("epoch")
        if epoch is not None:
            parts.append(f"epoca={epoch}")
        if "train_loss" in row:
            parts.append(f"train_loss={float(row['train_loss']):.4f}")
        if "train_acc" in row:
            parts.append(f"train_acc={float(row['train_acc']):.4f}")
        if "val_loss" in row:
            parts.append(f"val_loss={float(row['val_loss']):.4f}")
        if "val_acc" in row:
            parts.append(f"val_acc={float(row['val_acc']):.4f}")
        return " | ".join(parts)

    def _on_training_progress(self, row: dict[str, Any]) -> None:
        epoch = int(row.get("epoch", 0))
        status = f"Treinando... epoca {epoch}/{self._training_total_epochs}"
        self._set_status(status)
        self._set_training_dialog_text(status, self._format_train_metrics(row))

    def _finish_training_ui(self) -> None:
        self._is_training = False
        self._set_train_controls_enabled(True)
        self._close_training_dialog()

    def _update_zoom_labels(self) -> None:
        self.lbl_pdf_zoom.config(text=f"{int(self.pdf_zoom_var.get() * 100)}%")
        self.lbl_board_zoom.config(text=f"{int(self.board_zoom_var.get() * 100)}%")

    def zoom_pdf(self, delta: float) -> None:
        new_zoom = max(0.25, min(2.0, self.pdf_zoom_var.get() + delta))
        self.pdf_zoom_var.set(new_zoom)
        self._update_zoom_labels()
        self._refresh_pdf_view()
        self._save_app_state()

    def zoom_board(self, delta: float) -> None:
        new_zoom = max(0.45, min(1.8, self.board_zoom_var.get() + delta))
        self.board_zoom_var.set(new_zoom)
        self._update_zoom_labels()
        if self.result_items:
            self._draw_board_canvas(self.fen_var.get().strip())

    def _rgb_to_photo(self, image_rgb: np.ndarray, max_w: int, max_h: int) -> ImageTk.PhotoImage:
        pil = Image.fromarray(image_rgb)
        pil.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(pil)

    def _refresh_pdf_view(self) -> None:
        if self.page_rgb is None:
            return

        zoom = float(self.pdf_zoom_var.get())
        pil = Image.fromarray(self.page_rgb)
        target_w = max(1, int(pil.width * zoom))
        target_h = max(1, int(pil.height * zoom))
        if target_w != pil.width or target_h != pil.height:
            pil = pil.resize((target_w, target_h), Image.Resampling.LANCZOS)

        self.page_photo = ImageTk.PhotoImage(pil)
        self.pdf_canvas.delete("all")
        self.pdf_canvas_image_id = self.pdf_canvas.create_image(0, 0, anchor="nw", image=self.page_photo)
        self._pdf_select_rect_id = None
        self.pdf_canvas.configure(scrollregion=(0, 0, pil.width, pil.height))
        self.pdf_canvas.xview_moveto(0)
        self.pdf_canvas.yview_moveto(0)
        self._sync_webview2_to_current_pdf()

    def _is_reader_mode_selected(self) -> bool:
        if self.pdf_view_tabs is None or self.pdf_reader_tab is None:
            return False
        current = self.pdf_view_tabs.select()
        return bool(current) and current == str(self.pdf_reader_tab)

    def on_pdf_view_mode_changed(self) -> None:
        if self._is_reader_mode_selected():
            self._disable_pdf_area_selection()
            self._ensure_webview2_panel()
            self._sync_webview2_to_current_pdf()
            if self._webview2_panel is not None:
                self._webview2_panel.show()
        elif self._webview2_panel is not None:
            self._webview2_panel.hide()

    def _on_webview2_error(self, message: str) -> None:
        self.root.after(0, lambda: self.pdf_reader_notice_var.set(f"Falha ao iniciar WebView2:\n{message}"))

    def _ensure_webview2_panel(self) -> None:
        if not self._webview2_supported:
            return
        if self.pdf_reader_host is None:
            return
        if self._webview2_panel is not None:
            self._webview2_panel.resize()
            return

        try:
            self.pdf_reader_notice_var.set("Inicializando leitura via WebView2...")
            panel = EmbeddedWebView2(self.pdf_reader_host, error_cb=self._on_webview2_error)
            panel.ensure_started()
            self._webview2_panel = panel
            self.pdf_reader_host.bind("<Configure>", lambda _event: self._webview2_panel.resize() if self._webview2_panel is not None else None)
            self.pdf_reader_notice_var.set("Leitura via WebView2 pronta.")
        except WebView2SupportError as exc:
            self._webview2_supported = False
            self._webview2_support_reason = str(exc)
            self.pdf_reader_notice_var.set(f"Leitura via WebView2 indisponivel.\n{exc}")

    def _sync_webview2_to_current_pdf(self) -> None:
        if not self._is_reader_mode_selected():
            return
        if self.pdf_source is None or not isinstance(self.pdf_source, Path):
            return
        self._ensure_webview2_panel()
        if self._webview2_panel is None:
            return

        try:
            self._webview2_panel.load_pdf(self.pdf_source, int(self.page_index_var.get()))
        except WebView2SupportError as exc:
            self.pdf_reader_notice_var.set(f"Leitura via WebView2 indisponivel.\n{exc}")

    def toggle_pdf_area_selection(self) -> None:
        if self._is_reader_mode_selected() and self.pdf_view_tabs is not None and self.pdf_ocr_tab is not None:
            self.pdf_view_tabs.select(self.pdf_ocr_tab)
        if self._pdf_select_mode:
            self._disable_pdf_area_selection("Selecao de area cancelada.")
            return
        if self.pdf_source is None or self.page_rgb is None:
            messagebox.showwarning("Aviso", "Abra um PDF antes de selecionar uma area.")
            return
        self._pdf_select_mode = True
        self._pdf_select_start_canvas = None
        self._clear_pdf_selection_overlay()
        self.pdf_canvas.configure(cursor="crosshair")
        if self.btn_pdf_select is not None:
            self.btn_pdf_select.configure(text="Cancelar selecao")
        self._set_status("Selecao ativa: arraste no PDF para reconhecer a area automaticamente.")

    def _disable_pdf_area_selection(self, status_text: str = "") -> None:
        self._pdf_select_mode = False
        self._pdf_select_start_canvas = None
        self._clear_pdf_selection_overlay()
        self.pdf_canvas.configure(cursor="")
        if self.btn_pdf_select is not None:
            self.btn_pdf_select.configure(text="Selecionar area (OCR)")
        if status_text:
            self._set_status(status_text)

    def _clear_pdf_selection_overlay(self) -> None:
        if self._pdf_select_rect_id is not None:
            try:
                self.pdf_canvas.delete(self._pdf_select_rect_id)
            except tk.TclError as exc:
                logger.debug("Retangulo de selecao ja removido: %s", exc)
            self._pdf_select_rect_id = None

    def _clamp_pdf_canvas_point(self, x: float, y: float) -> tuple[float, float]:
        if self.page_rgb is None:
            return x, y
        zoom = float(self.pdf_zoom_var.get())
        max_x = float(self.page_rgb.shape[1]) * zoom
        max_y = float(self.page_rgb.shape[0]) * zoom
        return max(0.0, min(x, max_x)), max(0.0, min(y, max_y))

    def _on_pdf_canvas_button_press(self, event: tk.Event) -> None:
        if not self._pdf_select_mode or self.page_rgb is None:
            return
        x, y = self._clamp_pdf_canvas_point(self.pdf_canvas.canvasx(event.x), self.pdf_canvas.canvasy(event.y))
        self._pdf_select_start_canvas = (x, y)
        self._clear_pdf_selection_overlay()
        self._pdf_select_rect_id = self.pdf_canvas.create_rectangle(
            x,
            y,
            x,
            y,
            outline="#00ff88",
            width=2,
            dash=(6, 4),
        )

    def _on_pdf_canvas_drag(self, event: tk.Event) -> None:
        if not self._pdf_select_mode or self.page_rgb is None or self._pdf_select_start_canvas is None:
            return
        x, y = self._clamp_pdf_canvas_point(self.pdf_canvas.canvasx(event.x), self.pdf_canvas.canvasy(event.y))
        x0, y0 = self._pdf_select_start_canvas
        if self._pdf_select_rect_id is None:
            self._pdf_select_rect_id = self.pdf_canvas.create_rectangle(x0, y0, x, y, outline="#00ff88", width=2, dash=(6, 4))
        else:
            self.pdf_canvas.coords(self._pdf_select_rect_id, x0, y0, x, y)

    def _on_pdf_canvas_button_release(self, event: tk.Event) -> None:
        if not self._pdf_select_mode or self.page_rgb is None or self._pdf_select_start_canvas is None:
            return

        x1, y1 = self._clamp_pdf_canvas_point(self.pdf_canvas.canvasx(event.x), self.pdf_canvas.canvasy(event.y))
        x0, y0 = self._pdf_select_start_canvas
        self._disable_pdf_area_selection()

        x0c, x1c = sorted((x0, x1))
        y0c, y1c = sorted((y0, y1))
        if (x1c - x0c) < 12 or (y1c - y0c) < 12:
            self._set_status("Selecao muito pequena. Tente novamente.")
            return

        zoom = float(self.pdf_zoom_var.get())
        h, w = self.page_rgb.shape[:2]
        ix0 = max(0, min(w - 1, int(x0c / zoom)))
        iy0 = max(0, min(h - 1, int(y0c / zoom)))
        ix1 = max(ix0 + 1, min(w, int(x1c / zoom)))
        iy1 = max(iy0 + 1, min(h, int(y1c / zoom)))
        cropped = self.page_rgb[iy0:iy1, ix0:ix1].copy()
        if cropped.size == 0:
            self._set_status("Selecao vazia. Tente novamente.")
            return

        origin = f"pdf:{self.pdf_name}:page:{self.page_index_var.get()}:crop=({ix0},{iy0})-({ix1},{iy1})"
        self._start_ocr_from_image(
            cropped,
            origin=origin,
            max_boards=int(self.max_boards_var.get()),
            fallback_to_full_image=True,
        )

    def _get_model(self, model_path: Path | None = None):
        model_path = model_path or Path(self.model_path_var.get().strip())
        if self._model_cache is None or self._model_cache_path != model_path:
            self._set_status(f"Carregando modelo: {model_path}")
            model, device = load_model(model_path)
            self._model_cache = model
            self._model_cache_path = model_path
            self._model_device = device
        return self._model_cache, self._model_device

    def reload_model(self) -> None:
        self._model_cache = None
        self._model_cache_path = None
        self._model_device = None
        self._set_status("Modelo recarregado.")

    def open_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            title="Selecione o PDF",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            initialdir=str(ROOT),
        )
        if not filename:
            return
        self.load_pdf(Path(filename))


    def load_pdf(self, pdf_path: Path) -> None:
        try:
            self.pdf_source = pdf_path
            self.pdf_name = pdf_path.name
            self.page_count = get_pdf_page_count(self.pdf_source)
            self.lbl_pdf.config(text=f"{self.pdf_name} ({self.page_count} pags)")

            target_page = 0
            if APP_STATE_PATH.exists():
                try:
                    state = json.loads(APP_STATE_PATH.read_text(encoding="utf-8"))
                    history = state.get("pdf_history", {})
                    pdf_key = str(self.pdf_source.resolve())
                    if pdf_key in history:
                        target_page = history[pdf_key]
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    logger.warning("Historico de paginas ignorado: %s", exc)

            self.page_index_var.set(max(0, min(self.page_count - 1, target_page)))
            self.spin_page.config(to=max(self.page_count - 1, 0))
            self.page_loaded_for_index = None
            self.render_current_page()
            self._save_app_state()
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao abrir PDF:\n{exc}")

    def export_pdf_to_pgn(self) -> None:
        if self.pdf_source is None or not isinstance(self.pdf_source, Path):
            messagebox.showwarning("Aviso", "Abra um PDF antes de exportar o PGN.")
            return
        if self._is_exporting_pdf_pgn:
            messagebox.showinfo("Exportacao em andamento", "Ja existe uma exportacao de PDF para PGN em execucao.")
            return

        default_output = default_pgn_output_path(self.pdf_source)
        filename = filedialog.asksaveasfilename(
            title="Exportar PDF inteiro para PGN",
            defaultextension=".pgn",
            filetypes=[("PGN", "*.pgn"), ("Todos", "*.*")],
            initialdir=str(default_output.parent),
            initialfile=default_output.name,
        )
        if not filename:
            return

        output_path = Path(filename)
        if output_path.exists():
            overwrite = messagebox.askyesno(
                "Sobrescrever PGN",
                f"O arquivo ja existe:\n{output_path}\n\nDeseja sobrescrever?",
            )
            if not overwrite:
                return

        self._is_exporting_pdf_pgn = True
        self._set_pdf_export_controls_enabled(False)
        self._set_status("Iniciando exportacao do PDF para PGN...")

        worker = threading.Thread(
            target=self._export_pdf_to_pgn_worker,
            kwargs={
                "pdf_path": self.pdf_source,
                "output_path": output_path,
                "model_path": Path(self.model_path_var.get().strip()),
                "dpi": int(self.dpi_var.get()),
                "max_boards_per_page": int(self.max_boards_var.get()),
                "orientation": self.orientation_var.get(),
            },
            daemon=True,
        )
        worker.start()

    def _export_pdf_to_pgn_worker(
        self,
        *,
        pdf_path: Path,
        output_path: Path,
        model_path: Path,
        dpi: int,
        max_boards_per_page: int,
        orientation: str,
    ) -> None:
        def _progress(page_index: int, total_pages: int, page_boards: int, total_positions: int) -> None:
            current_page = page_index + 1
            self.root.after(
                0,
                lambda: self._set_status(
                    f"Exportando PDF -> PGN... pagina {current_page}/{total_pages} | diagramas na pagina: {page_boards} | total: {total_positions}"
                ),
            )

        try:
            report = save_pdf_positions_to_pgn(
                pdf_source=pdf_path,
                output_path=output_path,
                model_path=model_path,
                dpi=dpi,
                max_boards_per_page=max_boards_per_page,
                orientation=orientation,
                progress_callback=_progress,
            )
            self.root.after(0, lambda: self._on_export_pdf_to_pgn_success(report))
        except Exception as exc:
            self.root.after(0, lambda err=exc: self._on_export_pdf_to_pgn_error(err))
        finally:
            self.root.after(0, self._finish_export_pdf_to_pgn)

    def _on_export_pdf_to_pgn_success(self, report: ExportReport) -> None:
        self._set_status(f"Exportacao concluida. {report.summary()}.")

        linhas = [
            "Arquivo gerado com sucesso.",
            "",
            f"PGN: {report.output_path}",
            f"Aceitos: {len(report.accepted)} de {report.total}",
        ]
        # O gate so ajuda se o usuario souber o que ficou de fora (S-15).
        if report.review_path is not None:
            linhas += [
                "",
                f"Para revisao: {len(report.needs_review)} de baixa confianca, {len(report.rejected)} ilegais.",
                f"Arquivo: {report.review_path}",
            ]
        messagebox.showinfo("Exportar PDF para PGN", "\n".join(linhas))

    def _on_export_pdf_to_pgn_error(self, exc: Exception) -> None:
        self._set_status("Falha na exportacao do PDF para PGN.")
        messagebox.showerror("Exportar PDF para PGN", f"Nao foi possivel exportar o PDF:\n{exc}")

    def _finish_export_pdf_to_pgn(self) -> None:
        self._is_exporting_pdf_pgn = False
        self._set_pdf_export_controls_enabled(True)

    def on_page_spin(self) -> None:
        self.page_loaded_for_index = None
        self.render_current_page()

    def prev_page(self) -> None:
        if self.page_count == 0:
            return
        self.page_index_var.set(max(0, self.page_index_var.get() - 1))
        self.page_loaded_for_index = None
        self.render_current_page()

    def next_page(self) -> None:
        if self.page_count == 0:
            return
        self.page_index_var.set(min(self.page_count - 1, self.page_index_var.get() + 1))
        self.page_loaded_for_index = None
        self.render_current_page()

    def render_current_page(self) -> None:
        if self.pdf_source is None:
            return
        idx = int(self.page_index_var.get())
        if self.page_loaded_for_index == idx and self.page_rgb is not None:
            return
        try:
            self._set_status(f"Renderizando pagina {idx}...")
            self.page_rgb = render_pdf_page(self.pdf_source, idx, dpi=int(self.dpi_var.get()))
            self.page_loaded_for_index = idx
            self._refresh_pdf_view()
            self._save_app_state()
            self._set_status(f"Pagina {idx} pronta.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao renderizar pagina:\n{exc}")

    def ocr_best(self) -> None:
        self._run_ocr_from_current_page(max_boards=1)

    def ocr_all(self) -> None:
        self._run_ocr_from_current_page(max_boards=int(self.max_boards_var.get()))

    def _run_ocr_from_current_page(self, max_boards: int) -> None:
        if self.pdf_source is None:
            messagebox.showwarning("Aviso", "Abra um PDF primeiro.")
            return
        self.render_current_page()
        if self.page_rgb is None:
            return
        self._start_ocr_from_image(
            np.asarray(self.page_rgb).copy(),
            origin=f"pdf:{self.pdf_name}:page:{self.page_index_var.get()}",
            max_boards=max_boards,
            refine_detected_boards=True,
            # Contexto do PDF: habilita o detector hibrido (S-12), o mesmo que a exportacao
            # usa. Sem ele, a GUI e o PGN poderiam recortar diagramas diferentes.
            pdf_page=(self.pdf_source, int(self.page_index_var.get())),
        )

    def ocr_local_best(self) -> None:
        self._ocr_local(max_boards=1)

    def ocr_local_all(self) -> None:
        self._ocr_local(max_boards=int(self.max_boards_var.get()))

    def _ocr_local(self, max_boards: int) -> None:
        filename = filedialog.askopenfilename(
            title="Selecione a imagem",
            filetypes=[("Imagem", "*.png;*.jpg;*.jpeg;*.webp"), ("Todos", "*.*")],
            initialdir=str(ROOT),
        )
        if not filename:
            return
        image_bgr = cv2.imread(filename)
        if image_bgr is None:
            messagebox.showerror("Erro", "Nao foi possivel abrir a imagem.")
            return
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        self._start_ocr_from_image(
            image_rgb,
            origin=f"local-image:{Path(filename).name}",
            max_boards=max_boards,
            refine_detected_boards=True,
        )

    def _refine_board_from_quad(
        self,
        image_rgb: np.ndarray,
        quad: np.ndarray | None,
        pad_ratio: float = 0.08,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        if quad is None:
            resized = cv2.resize(image_rgb, (BOARD_SIZE, BOARD_SIZE))
            return resized, None

        h, w = image_rgb.shape[:2]
        xs = quad[:, 0]
        ys = quad[:, 1]
        x0 = max(0, int(np.floor(np.min(xs))))
        y0 = max(0, int(np.floor(np.min(ys))))
        x1 = min(w, int(np.ceil(np.max(xs))))
        y1 = min(h, int(np.ceil(np.max(ys))))
        bw = max(1, x1 - x0)
        bh = max(1, y1 - y0)
        pad = int(max(bw, bh) * pad_ratio)

        rx0 = max(0, x0 - pad)
        ry0 = max(0, y0 - pad)
        rx1 = min(w, x1 + pad)
        ry1 = min(h, y1 + pad)
        roi = image_rgb[ry0:ry1, rx0:rx1]
        if roi.size == 0:
            resized = cv2.resize(image_rgb, (BOARD_SIZE, BOARD_SIZE))
            return resized, None

        refined_candidates = detect_boards(image_rgb=roi, max_boards=1)
        if not refined_candidates:
            resized = cv2.resize(image_rgb[y0:y1, x0:x1], (BOARD_SIZE, BOARD_SIZE))
            return resized, quad

        refined_board, refined_quad = refined_candidates[0]
        if refined_quad is not None:
            offset = np.array([rx0, ry0], dtype=np.float32)
            refined_quad = refined_quad + offset
        return refined_board, refined_quad

    def _detect_and_predict_items(
        self,
        image_rgb: np.ndarray,
        max_boards: int,
        model_path: Path,
        orientation: str,
        fallback_to_full_image: bool = False,
        refine_detected_boards: bool = False,
        pdf_page: tuple[Any, int] | None = None,
    ) -> list[dict[str, Any]]:
        if pdf_page is not None:
            # Pagina de PDF: usa o detector das duas fontes, igual a exportacao (S-12).
            source, page_index = pdf_page
            boards = [
                (candidate.board_rgb, None)
                for candidate in detect_diagrams_in_pdf_page(source, page_index, image_rgb, max_boards=max_boards)
            ]
            # O recorte embutido ja vem alinhado pelo warp; refinar de novo so acrescenta erro.
            refine_detected_boards = False
        else:
            boards = detect_boards(image_rgb=image_rgb, max_boards=max_boards)
        if fallback_to_full_image and not boards:
            boards = [(image_rgb, None)]
        if not boards:
            raise ValueError("Nenhum tabuleiro foi detectado na imagem selecionada.")

        model, device = self._get_model(model_path=model_path)
        items: list[dict[str, Any]] = []
        for idx, (board_rgb, quad) in enumerate(boards):
            board_for_pred = board_rgb
            quad_for_item = quad
            if refine_detected_boards:
                board_for_pred, quad_for_item = self._refine_board_from_quad(image_rgb=image_rgb, quad=quad)
            oriented = predict_with_orientation(
                board_for_pred,
                model,
                device,
                mode=orientation,  # type: ignore[arg-type]
            )
            prediction = oriented.prediction
            items.append(
                {
                    "index": idx,
                    "board_rgb": board_for_pred,
                    "quad": quad_for_item.tolist() if quad_for_item is not None else None,
                    "fen_pred": prediction.fen_board,
                    "confidence": prediction.mean_confidence,
                    "min_confidence": prediction.min_confidence,
                    "uncertain_squares": prediction.uncertain_squares,
                    "is_legal": prediction.position.is_legal,
                    "is_fatal": prediction.position.is_fatal,
                    "problems": prediction.position.problems,
                    "rotation": oriented.rotation,
                    "orientation_ambiguous": oriented.ambiguous,
                    "orientation_reason": oriented.reason,
                }
            )
        return items

    def _start_ocr_from_image(
        self,
        image_rgb: np.ndarray,
        origin: str,
        max_boards: int,
        fallback_to_full_image: bool = False,
        refine_detected_boards: bool = False,
        pdf_page: tuple[Any, int] | None = None,
    ) -> None:
        if self._is_running_ocr:
            self._set_status("OCR em andamento. Aguarde a conclusao.")
            return

        self._is_running_ocr = True
        self._set_ocr_controls_enabled(False)
        self._set_status("Preparando OCR...")
        model_path = Path(self.model_path_var.get().strip())
        orientation = self.orientation_var.get()
        worker = threading.Thread(
            target=self._ocr_worker,
            kwargs={
                "image_rgb": np.asarray(image_rgb).copy(),
                "origin": origin,
                "max_boards": max_boards,
                "model_path": model_path,
                "orientation": orientation,
                "fallback_to_full_image": fallback_to_full_image,
                "refine_detected_boards": refine_detected_boards,
                "pdf_page": pdf_page,
            },
            daemon=True,
        )
        worker.start()

    def _ocr_worker(
        self,
        *,
        image_rgb: np.ndarray,
        origin: str,
        max_boards: int,
        model_path: Path,
        orientation: str,
        fallback_to_full_image: bool,
        refine_detected_boards: bool,
        pdf_page: tuple[Any, int] | None = None,
    ) -> None:
        try:
            self._set_status("Detectando diagramas...")
            items = self._detect_and_predict_items(
                image_rgb=image_rgb,
                max_boards=max_boards,
                model_path=model_path,
                orientation=orientation,
                fallback_to_full_image=fallback_to_full_image,
                refine_detected_boards=refine_detected_boards,
                pdf_page=pdf_page,
            )
            self.root.after(0, lambda result_items=items, source=origin: self._apply_ocr_result_items(result_items, source))
        except Exception as exc:
            self.root.after(0, lambda err=exc: self._on_ocr_error(err))
        finally:
            self.root.after(0, self._finish_ocr_ui)

    def _apply_ocr_result_items(self, items: list[dict[str, Any]], origin: str) -> None:
        self.result_items = items
        self.fen_edits = [item["fen_pred"] for item in items]
        self.selected_diag_idx = 0
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=max(len(items), 1))
        self.fen_var.set(self.fen_edits[0] if self.fen_edits else "")
        self._show_local_results_tab()
        self._update_result_views()
        self.root.after_idle(self._redraw_current_result_board)
        self._set_status(f"OCR pronto. Diagramas detectados: {len(items)} | origem: {origin}")

    def _on_ocr_error(self, exc: Exception) -> None:
        if "Nenhum tabuleiro foi detectado" in str(exc):
            self._clear_ocr_results()
        self._set_status("Falha no OCR.")
        messagebox.showerror("Erro", f"Falha no OCR:\n{exc}")

    def _finish_ocr_ui(self) -> None:
        self._is_running_ocr = False
        self._set_ocr_controls_enabled(True)

    def _clear_ocr_results(self) -> None:
        self.result_items = []
        self.fen_edits = []
        self.selected_diag_idx = 0
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=1)
        self.fen_var.set("")
        self._update_result_views()

    def _selected_index(self) -> int:
        if not self.result_items:
            return 0
        return max(0, min(self.selected_diag_idx, len(self.result_items) - 1))

    def on_diagram_spin(self) -> None:
        self._sync_fen_from_entry_to_current()
        if self.result_items:
            try:
                requested = int(self.selected_diag_var.get()) - 1
            except (ValueError, tk.TclError):
                # Campo vazio ou nao numerico: mantem a selecao atual.
                requested = self.selected_diag_idx
            self.selected_diag_idx = max(0, min(requested, len(self.result_items) - 1))
        self.selected_diag_var.set(self.selected_diag_idx + 1)
        self._refresh_for_selected_diagram()

    def prev_diagram(self) -> None:
        if not self.result_items:
            return
        self._sync_fen_from_entry_to_current()
        self.selected_diag_idx = max(0, self.selected_diag_idx - 1)
        self.selected_diag_var.set(self.selected_diag_idx + 1)
        self._refresh_for_selected_diagram()

    def next_diagram(self) -> None:
        if not self.result_items:
            return
        self._sync_fen_from_entry_to_current()
        self.selected_diag_idx = min(len(self.result_items) - 1, self.selected_diag_idx + 1)
        self.selected_diag_var.set(self.selected_diag_idx + 1)
        self._refresh_for_selected_diagram()

    def _sync_fen_from_entry_to_current(self) -> None:
        if not self.result_items:
            return
        idx = self._selected_index()
        self.fen_edits[idx] = self.fen_var.get().strip()

    def _confidence_summary(self, idx: int) -> str:
        """Resumo de confianca e legalidade do diagrama para a barra de status.

        Mostra o minimo antes da media: a media fica ~0,97 mesmo quando ha erro, entao
        so ela nunca alertaria o usuario (S-10).
        """
        item = self.result_items[idx]
        parts = [f"conf min {float(item.get('min_confidence', 0.0)):.3f}"]
        parts.append(f"media {float(item.get('confidence', 0.0)):.3f}")

        # Orientacao antes do resto: se o diagrama estiver de cabeca para baixo, conferir
        # casa por casa e perda de tempo (S-13).
        if item.get("orientation_ambiguous"):
            parts.append(f"ORIENTACAO INCERTA ({item.get('orientation_reason') or 'as duas eram plausiveis'})")
        elif item.get("rotation"):
            parts.append(f"lido a {item['rotation']} graus")

        uncertain = item.get("uncertain_squares") or []
        if uncertain:
            nomes = ", ".join(square_name(square) for square in uncertain[:4])
            sufixo = f" +{len(uncertain) - 4}" if len(uncertain) > 4 else ""
            parts.append(f"casas inseguras: {nomes}{sufixo}")

        if item.get("is_legal") is False:
            problems = item.get("problems") or ()
            detalhe = f" ({'; '.join(problems)})" if problems else ""
            # "Xeque invertido" nao e erro de leitura: o diagrama nao diz de quem e a vez e
            # o app assume brancas. Chamar isso de ILEGAL manda o usuario procurar um erro
            # que nao existe no tabuleiro.
            rotulo = "LADO A JOGAR" if item.get("is_fatal") is False else "ILEGAL"
            parts.append(rotulo + detalhe)

        return " | ".join(parts)

    def _refresh_for_selected_diagram(self) -> None:
        if not self.result_items:
            return
        idx = self._selected_index()
        self.selected_diag_idx = idx
        self.selected_diag_var.set(idx + 1)
        self.fen_var.set(self.fen_edits[idx])
        self._set_status(f"Diagrama {idx + 1}/{len(self.result_items)} | {self._confidence_summary(idx)}")
        self._update_result_views()

    def apply_fen_edit(self) -> None:
        if not self.result_items:
            return
        self._sync_fen_from_entry_to_current()
        self._update_result_views()

    def _update_result_views(self) -> None:
        if self.board_canvas is None:
            return
        if not self.result_items:
            self.board_canvas.delete("all")
            return

        idx = self._selected_index()
        fen = self.fen_edits[idx]

        self._draw_board_canvas(fen)
        self._maybe_sync_study_with_current_fen()

    def _show_local_results_tab(self) -> None:
        if self.left_tabs is None or self.local_results_tab is None:
            return
        try:
            self.left_tabs.select(self.local_results_tab)
        except tk.TclError as exc:
            logger.debug("Nao foi possivel focar a aba de resultados: %s", exc)

    def _redraw_current_result_board(self) -> None:
        if self.board_canvas is None:
            return
        if not self.result_items:
            self.board_canvas.delete("all")
            return
        self._draw_board_canvas(self.fen_var.get().strip())

    def _load_piece_image_sources(self) -> dict[str, Image.Image]:
        images: dict[str, Image.Image] = {}
        for color_code in ("w", "b"):
            for piece_code in ("p", "n", "b", "r", "q", "k"):
                key = f"{color_code}{piece_code}"
                path = PIECE_IMAGE_DIR / f"{key}.png"
                if not path.exists():
                    continue
                try:
                    with Image.open(path) as img:
                        images[key] = img.convert("RGBA")
                except (OSError, ValueError) as exc:
                    # Sem a imagem, o tabuleiro cai no fallback de simbolos Unicode.
                    logger.warning("Imagem de peca invalida em %s: %s", path, exc)
        return images

    def _get_piece_photo(self, piece: Any, cell: int) -> ImageTk.PhotoImage | None:
        key = f"{'w' if piece.color else 'b'}{piece.symbol().lower()}"
        source = self._piece_image_sources.get(key)
        if source is None:
            return None

        icon_size = max(12, int(cell * 0.86))
        cache_key = (key, icon_size)
        cached = self._piece_photo_cache.get(cache_key)
        if cached is not None:
            return cached

        if hasattr(Image, "Resampling"):
            resized = source.resize((icon_size, icon_size), resample=Image.Resampling.LANCZOS)
        else:
            resized = source.resize((icon_size, icon_size), resample=Image.LANCZOS)
        photo = ImageTk.PhotoImage(resized)
        self._piece_photo_cache[cache_key] = photo
        return photo

    def _draw_board_canvas(self, fen: str) -> None:
        if self.board_canvas is None:
            return
        self.board_canvas.delete("all")
        size = int(440 * float(self.board_zoom_var.get()))
        size = max(220, min(size, 760))
        origin_x, origin_y = 16, 16
        cell = size // 8
        light = "#f0d9b5"
        dark = "#b58863"
        canvas_w = min(560, size + 42)
        canvas_h = min(560, size + 42)
        self.board_canvas.configure(width=canvas_w, height=canvas_h)

        if not fen:
            self.board_canvas.create_text(canvas_w // 2, canvas_h // 2, text="Sem FEN", font=("Segoe UI", 14))
            return

        if not is_valid_fen(fen):
            self.board_canvas.create_text(canvas_w // 2, canvas_h // 2, text="FEN invalida", fill="red", font=("Segoe UI", 14, "bold"))
            return

        board = board_from_fen(fen)

        for row in range(8):
            for col in range(8):
                x0 = origin_x + col * cell
                y0 = origin_y + row * cell
                x1 = x0 + cell
                y1 = y0 + cell
                color = light if (row + col) % 2 == 0 else dark
                self.board_canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color)

                square = (7 - row) * 8 + col
                piece = board.piece_at(square)
                if piece is not None:
                    piece_photo = self._get_piece_photo(piece, cell)
                    if piece_photo is not None:
                        self.board_canvas.create_image(x0 + cell / 2, y0 + cell / 2, image=piece_photo)
                    else:
                        symbol = UNICODE_PIECES.get(piece.symbol(), piece.symbol())
                        self.board_canvas.create_text(
                            x0 + cell / 2,
                            y0 + cell / 2,
                            text=symbol,
                            fill="#111111",
                            font=("Segoe UI Symbol", int(cell * 0.56)),
                        )

        for i, file_char in enumerate("abcdefgh"):
            self.board_canvas.create_text(origin_x + i * cell + cell / 2, origin_y + size + 12, text=file_char, font=("Segoe UI", 10))
        for i in range(8):
            self.board_canvas.create_text(origin_x - 10, origin_y + i * cell + cell / 2, text=str(8 - i), font=("Segoe UI", 10))

    def _set_study_status(self, text: str = "") -> None:
        turn_text = "brancas" if self.study_board.turn else "pretas"
        if text:
            self.study_status_var.set(f"{text} | vez: {turn_text}")
        else:
            self.study_status_var.set(f"Vez: {turn_text}")

    def _create_study_game(self, board: chess.Board) -> chess.pgn.Game:
        game = chess.pgn.Game()
        game.headers["Event"] = "ChessVisionOFF Study"
        game.headers["Site"] = "Local"
        game.headers["Result"] = "*"
        game.setup(board.copy(stack=False))
        return game

    def _sync_study_board_from_current_node(self) -> None:
        self.study_board = self.study_current_node.board()

    def _study_child_variation_labels(self) -> list[str]:
        labels: list[str] = []
        current_board = self.study_board.copy(stack=False)
        for idx, child in enumerate(self.study_current_node.variations, start=1):
            san = current_board.san(child.move)
            labels.append(f"{idx}. {san}")
        return labels

    def _update_study_variation_selector(self) -> None:
        if self.study_variation_combo is None:
            return
        labels = self._study_child_variation_labels()
        if not labels:
            self.study_variation_combo.configure(values=(), state="disabled")
            self.study_variation_var.set("")
            return
        self.study_variation_combo.configure(values=labels, state="readonly")
        if self.study_variation_var.get() not in labels:
            self.study_variation_var.set(labels[0])
        self.study_variation_combo.current(labels.index(self.study_variation_var.get()))

    def _get_selected_study_variation_index(self) -> int:
        labels = self._study_child_variation_labels()
        if not labels:
            return 0
        value = self.study_variation_var.get()
        if value in labels:
            return labels.index(value)
        return 0

    def _update_study_moves_text(self) -> None:
        if self.study_moves_text is None:
            return

        exporter = chess.pgn.StringExporter(headers=False, variations=True, comments=True)
        text = self.study_game.accept(exporter).strip()
        if not text:
            text = "Sem lances."

        self.study_moves_text.configure(state=tk.NORMAL)
        self.study_moves_text.delete("1.0", tk.END)
        self.study_moves_text.insert("1.0", text)
        self.study_moves_text.configure(state=tk.DISABLED)

    def _refresh_study_view(self) -> None:
        self._sync_study_board_from_current_node()
        self.study_fen_var.set(self.study_board.fen())
        self._update_study_moves_text()
        self._update_study_variation_selector()
        self._draw_study_board()

    def _set_study_board_state(self, board: chess.Board, origin: str, status: str) -> None:
        self.study_game = self._create_study_game(board)
        self.study_current_node = self.study_game
        self._sync_study_board_from_current_node()
        self.study_selected_square = None
        self._clear_study_drag_state()
        self.study_origin_var.set(origin)
        self._refresh_study_view()
        self._set_study_status(status)

    def _load_study_position(self, fen: str, origin: str, status: str) -> None:
        if not fen:
            messagebox.showwarning("Aviso", "Nao ha FEN para carregar no tabuleiro de analise.")
            return
        if not is_valid_fen(fen):
            messagebox.showerror("Erro", "A FEN informada para analise e invalida.")
            return
        self._set_study_board_state(board_from_fen(fen), origin=origin, status=status)

    def _maybe_sync_study_with_current_fen(self, force: bool = False) -> None:
        if not force and not self.study_follow_ocr_var.get():
            return
        fen = self.fen_var.get().strip()
        if not fen or not is_valid_fen(fen):
            return
        self._load_study_position(fen, origin="Base: OCR selecionado", status="Tabuleiro sincronizado com o OCR.")

    def on_study_follow_ocr_toggle(self) -> None:
        if self.study_follow_ocr_var.get():
            self._maybe_sync_study_with_current_fen(force=True)
        else:
            self._set_study_status("Sincronismo com OCR desativado.")

    def load_study_from_recognized(self) -> None:
        self._load_study_position(
            self.fen_var.get().strip(),
            origin="Base: OCR selecionado",
            status="Posicao reconhecida carregada no tabuleiro.",
        )

    def load_study_initial_position(self) -> None:
        self.study_follow_ocr_var.set(False)
        self._set_study_board_state(
            chess.Board(),
            origin="Base: posicao inicial",
            status="Tabuleiro reiniciado na posicao inicial.",
        )

    def apply_study_fen(self) -> None:
        self.study_follow_ocr_var.set(False)
        self._load_study_position(
            self.study_fen_var.get().strip(),
            origin="Base: FEN manual",
            status="FEN aplicada no tabuleiro de analise.",
        )

    def copy_study_fen(self) -> None:
        fen = self.study_board.fen()
        self.root.clipboard_clear()
        self.root.clipboard_append(fen)
        self._set_study_status("FEN do estudo copiada.")

    def _study_pgn_payload(self) -> str:
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        return self.study_game.accept(exporter).strip()

    def _write_study_pgn(self, path: Path, append: bool) -> None:
        payload = self._study_pgn_payload()
        if append and path.exists() and path.stat().st_size > 0:
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n\n")
                handle.write(payload)
                handle.write("\n")
            return
        path.write_text(payload + "\n", encoding="utf-8")

    def save_study_pgn(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="Salvar estudo em PGN",
            defaultextension=".pgn",
            filetypes=[("PGN", "*.pgn"), ("Todos", "*.*")],
            initialdir=str(ROOT),
        )
        if not filename:
            return
        path = Path(filename)
        append = False
        if path.exists():
            answer = messagebox.askyesnocancel(
                "PGN existente",
                "O arquivo ja existe.\n\nSim: acrescentar esta analise ao final.\nNao: sobrescrever o arquivo.\nCancelar: abortar o salvamento.",
            )
            if answer is None:
                return
            append = bool(answer)
        try:
            self._write_study_pgn(path, append=append)
            if append:
                self._set_study_status(f"Analise acrescentada em {path.name}.")
            else:
                self._set_study_status(f"PGN salvo em {path.name}.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar PGN:\n{exc}")

    def flip_study_board(self) -> None:
        self.study_flipped_var.set(not self.study_flipped_var.get())
        self._draw_study_board()

    def toggle_study_turn(self) -> None:
        board = self.study_board.copy(stack=False)
        board.turn = not board.turn
        self.study_follow_ocr_var.set(False)
        self._set_study_board_state(
            board,
            origin="Base: lado a jogar ajustado",
            status="Lado a jogar invertido.",
        )

    def undo_study_move(self) -> None:
        if self.study_current_node.parent is None:
            self._set_study_status("Nao ha lances para desfazer.")
            return
        self.study_current_node = self.study_current_node.parent
        self.study_selected_square = None
        self._clear_study_drag_state()
        self._refresh_study_view()
        self._set_study_status("Ultimo lance desfeito.")

    def redo_study_move(self) -> None:
        if not self.study_current_node.variations:
            self._set_study_status("Nao ha lances para refazer.")
            return
        idx = self._get_selected_study_variation_index()
        idx = max(0, min(idx, len(self.study_current_node.variations) - 1))
        self.study_current_node = self.study_current_node.variations[idx]
        self.study_selected_square = None
        self._clear_study_drag_state()
        self._refresh_study_view()
        self._set_study_status("Lance refeito.")

    def go_to_start_of_study_line(self) -> None:
        if self.study_current_node.parent is None:
            self._set_study_status("Ja esta no inicio da linha.")
            return
        while self.study_current_node.parent is not None:
            self.study_current_node = self.study_current_node.parent
        self.study_selected_square = None
        self._clear_study_drag_state()
        self._refresh_study_view()
        self._set_study_status("Voltou para o inicio da linha.")

    def go_to_end_of_study_line(self) -> None:
        if not self.study_current_node.variations:
            self._set_study_status("Ja esta no fim da linha.")
            return
        first_step = True
        while self.study_current_node.variations:
            idx = self._get_selected_study_variation_index() if first_step else 0
            idx = max(0, min(idx, len(self.study_current_node.variations) - 1))
            self.study_current_node = self.study_current_node.variations[idx]
            first_step = False
        self.study_selected_square = None
        self._clear_study_drag_state()
        self._refresh_study_view()
        self._set_study_status("Avancou para o fim da linha.")

    def _study_square_to_display(self, square: int) -> tuple[int, int]:
        file_idx = chess.square_file(square)
        rank_idx = chess.square_rank(square)
        if self.study_flipped_var.get():
            return rank_idx, 7 - file_idx
        return 7 - rank_idx, file_idx

    def _study_display_to_square(self, row: int, col: int) -> int:
        if self.study_flipped_var.get():
            file_idx = 7 - col
            rank_idx = row
        else:
            file_idx = col
            rank_idx = 7 - row
        return chess.square(file_idx, rank_idx)

    def _study_legal_moves_from(self, square: int) -> list[chess.Move]:
        return [move for move in self.study_board.legal_moves if move.from_square == square]

    def _clear_study_drag_state(self) -> None:
        self.study_drag_from_square = None
        self.study_drag_piece = None
        self.study_drag_pointer = None
        self.study_drag_start_pointer = None
        self.study_drag_active = False
        self.study_press_selected_new_piece = False

    def _choose_study_promotion(self) -> int | None:
        choice: dict[str, int | None] = {"piece_type": None}
        dlg = tk.Toplevel(self.root)
        dlg.title("Promocao")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        wrap = ttk.Frame(dlg, padding=12)
        wrap.pack(fill=tk.BOTH, expand=True)
        ttk.Label(wrap, text="Escolha a peca para promocao").pack(anchor="w", pady=(0, 8))

        def _select(piece_type: int) -> None:
            choice["piece_type"] = piece_type
            dlg.destroy()

        for label, piece_type in (("Dama", chess.QUEEN), ("Torre", chess.ROOK), ("Bispo", chess.BISHOP), ("Cavalo", chess.KNIGHT)):
            ttk.Button(wrap, text=label, command=lambda current=piece_type: _select(current)).pack(fill=tk.X, pady=2)

        ttk.Button(wrap, text="Cancelar", command=dlg.destroy).pack(fill=tk.X, pady=(8, 0))
        self.root.wait_window(dlg)
        return choice["piece_type"]

    def _push_study_move(self, move: chess.Move) -> None:
        san = self.study_board.san(move)
        existing_child = next((child for child in self.study_current_node.variations if child.move == move), None)
        if existing_child is not None:
            self.study_current_node = existing_child
        else:
            self.study_current_node = self.study_current_node.add_variation(move)
        self.study_selected_square = None
        self._clear_study_drag_state()
        self._refresh_study_view()
        suffix = "Variante seguida." if existing_child is not None else "Lance salvo."
        self._set_study_status(f"{san} | {suffix}")

    def _study_square_from_xy(self, x: float, y: float) -> int | None:
        geom = self._study_board_geom
        if not geom:
            return None
        origin_x = geom["origin_x"]
        origin_y = geom["origin_y"]
        size = geom["size"]
        cell = geom["cell"]
        if not (origin_x <= x < origin_x + size and origin_y <= y < origin_y + size):
            return None
        col = int((x - origin_x) // cell)
        row = int((y - origin_y) // cell)
        if not (0 <= row <= 7 and 0 <= col <= 7):
            return None
        return self._study_display_to_square(row, col)

    def _play_study_move_to_square(self, target_square: int) -> bool:
        if self.study_selected_square is None:
            return False
        candidate_moves = [move for move in self._study_legal_moves_from(self.study_selected_square) if move.to_square == target_square]
        if not candidate_moves:
            return False

        move = candidate_moves[0]
        if len(candidate_moves) > 1:
            promotion = self._choose_study_promotion()
            if promotion is None:
                self._set_study_status("Promocao cancelada.")
                return True
            selected_move = next((item for item in candidate_moves if item.promotion == promotion), None)
            if selected_move is None:
                self._set_study_status("Promocao invalida.")
                return True
            move = selected_move

        self.study_follow_ocr_var.set(False)
        self._push_study_move(move)
        return True

    def _handle_study_square_action(self, square: int | None, allow_deselect: bool) -> None:
        if square is None:
            if self.study_drag_active:
                self._set_study_status("Arraste cancelado.")
            return

        board = self.study_board
        piece = board.piece_at(square)
        if self.study_selected_square is None:
            if piece is None or piece.color != board.turn:
                self._set_study_status("Selecione uma peca do lado a jogar.")
                return
            self.study_selected_square = square
            self._draw_study_board()
            self._set_study_status(f"Peca selecionada em {chess.square_name(square)}.")
            return

        if square == self.study_selected_square and allow_deselect:
            self.study_selected_square = None
            self._draw_study_board()
            self._set_study_status("Selecao removida.")
            return

        if piece is not None and piece.color == board.turn:
            self.study_selected_square = square
            self._draw_study_board()
            self._set_study_status(f"Peca selecionada em {chess.square_name(square)}.")
            return

        if not self._play_study_move_to_square(square):
            self._set_study_status("Lance ilegal para a posicao atual.")

    def on_study_board_press(self, event: tk.Event) -> None:
        if self.study_canvas is not None:
            self.study_canvas.focus_set()
        square = self._study_square_from_xy(event.x, event.y)
        self.study_drag_pointer = (event.x, event.y)
        self.study_drag_start_pointer = (event.x, event.y)
        self.study_drag_from_square = square
        self.study_drag_active = False
        self.study_press_selected_new_piece = False

        if square is None:
            self.study_drag_piece = None
            return

        piece = self.study_board.piece_at(square)
        if piece is not None and piece.color == self.study_board.turn:
            self.study_press_selected_new_piece = self.study_selected_square != square
            self.study_drag_piece = piece
            self.study_selected_square = square
            self._draw_study_board()
            return

        self.study_drag_piece = None

    def on_study_board_drag(self, event: tk.Event) -> None:
        if self.study_drag_piece is None or self.study_drag_from_square is None:
            return
        self.study_drag_pointer = (event.x, event.y)
        if not self.study_drag_active:
            origin = self._study_board_geom
            cell = max(1.0, float(origin.get("cell", 1.0)))
            if self.study_drag_start_pointer is None:
                self.study_drag_start_pointer = self.study_drag_pointer
            start_x, start_y = self.study_drag_start_pointer
            current_x, current_y = self.study_drag_pointer
            if abs(current_x - start_x) < cell * 0.12 and abs(current_y - start_y) < cell * 0.12:
                return
            self.study_drag_active = True
        self._draw_study_board()

    def on_study_board_release(self, event: tk.Event) -> None:
        target_square = self._study_square_from_xy(event.x, event.y)
        allow_deselect = (not self.study_drag_active) and (not self.study_press_selected_new_piece)
        self._handle_study_square_action(target_square, allow_deselect=allow_deselect)
        self._clear_study_drag_state()
        self._draw_study_board()

    def _study_square_center(self, square: int) -> tuple[float, float]:
        row, col = self._study_square_to_display(square)
        geom = self._study_board_geom
        origin_x = geom["origin_x"]
        origin_y = geom["origin_y"]
        cell = geom["cell"]
        return origin_x + col * cell + cell / 2, origin_y + row * cell + cell / 2

    def _draw_study_board(self) -> None:
        if self.study_canvas is None:
            return

        canvas = self.study_canvas
        canvas.delete("all")
        canvas_w = max(320, canvas.winfo_width())
        canvas_h = max(320, canvas.winfo_height())
        size = max(240, min(canvas_w - 36, canvas_h - 36, 520))
        cell = size / 8
        origin_x = (canvas_w - size) / 2
        origin_y = (canvas_h - size) / 2
        self._study_board_geom = {"origin_x": origin_x, "origin_y": origin_y, "size": size, "cell": cell}

        light = "#f0d9b5"
        dark = "#b58863"
        selected_fill = "#f7ec74"
        last_move_fill = "#cdd26a"
        target_outline = "#3f7f4c"

        last_move = self.study_current_node.move
        last_move_squares = set()
        if last_move is not None:
            last_move_squares = {last_move.from_square, last_move.to_square}
        legal_targets = {move.to_square for move in self._study_legal_moves_from(self.study_selected_square)} if self.study_selected_square is not None else set()

        canvas.create_rectangle(origin_x - 2, origin_y - 2, origin_x + size + 2, origin_y + size + 2, fill="#312e2b", outline="")

        for row in range(8):
            for col in range(8):
                square = self._study_display_to_square(row, col)
                rank_idx = chess.square_rank(square)
                file_idx = chess.square_file(square)
                x0 = origin_x + col * cell
                y0 = origin_y + row * cell
                x1 = x0 + cell
                y1 = y0 + cell

                color = light if (rank_idx + file_idx) % 2 == 0 else dark
                if square in last_move_squares:
                    color = last_move_fill
                if square == self.study_selected_square:
                    color = selected_fill
                canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color)

                if self.study_drag_active and square == self.study_drag_from_square:
                    continue

                piece = self.study_board.piece_at(square)
                if piece is not None:
                    piece_photo = self._get_piece_photo(piece, int(cell))
                    if piece_photo is not None:
                        canvas.create_image(x0 + cell / 2, y0 + cell / 2, image=piece_photo)
                    else:
                        symbol = UNICODE_PIECES.get(piece.symbol(), piece.symbol())
                        canvas.create_text(
                            x0 + cell / 2,
                            y0 + cell / 2,
                            text=symbol,
                            fill="#111111",
                            font=("Segoe UI Symbol", max(14, int(cell * 0.56))),
                        )
                elif square in legal_targets:
                    radius = max(6, int(cell * 0.12))
                    canvas.create_oval(
                        x0 + cell / 2 - radius,
                        y0 + cell / 2 - radius,
                        x0 + cell / 2 + radius,
                        y0 + cell / 2 + radius,
                        fill=target_outline,
                        outline="",
                    )

        if legal_targets:
            for target in legal_targets:
                piece = self.study_board.piece_at(target)
                if piece is None:
                    continue
                row, col = self._study_square_to_display(target)
                x0 = origin_x + col * cell
                y0 = origin_y + row * cell
                x1 = x0 + cell
                y1 = y0 + cell
                canvas.create_rectangle(x0 + 4, y0 + 4, x1 - 4, y1 - 4, outline=target_outline, width=2)

        file_labels = "hgfedcba" if self.study_flipped_var.get() else "abcdefgh"
        rank_labels = "12345678" if self.study_flipped_var.get() else "87654321"
        for idx, file_char in enumerate(file_labels):
            canvas.create_text(origin_x + idx * cell + cell / 2, origin_y + size + 12, text=file_char, fill="#d8d8d8", font=("Segoe UI", 10, "bold"))
        for idx, rank_char in enumerate(rank_labels):
            canvas.create_text(origin_x - 10, origin_y + idx * cell + cell / 2, text=rank_char, fill="#d8d8d8", font=("Segoe UI", 10, "bold"))

        if self.study_drag_active and self.study_drag_piece is not None and self.study_drag_pointer is not None:
            drag_x, drag_y = self.study_drag_pointer
            piece_photo = self._get_piece_photo(self.study_drag_piece, int(cell))
            if piece_photo is not None:
                canvas.create_image(drag_x, drag_y, image=piece_photo)
            else:
                symbol = UNICODE_PIECES.get(self.study_drag_piece.symbol(), self.study_drag_piece.symbol())
                canvas.create_text(
                    drag_x,
                    drag_y,
                    text=symbol,
                    fill="#111111",
                    font=("Segoe UI Symbol", max(14, int(cell * 0.56))),
                )

    def save_current(self) -> None:
        if not self.result_items:
            messagebox.showwarning("Aviso", "Nao ha OCR para salvar.")
            return
        self._sync_fen_from_entry_to_current()
        idx = self._selected_index()
        fen = self.fen_edits[idx]
        if not is_valid_fen(fen):
            messagebox.showerror("Erro", "FEN atual invalida.")
            return
        try:
            path = append_training_sample(
                board_rgb=self.result_items[idx]["board_rgb"],
                fen=fen,
                csv_path=Path(self.dataset_csv_var.get()),
                samples_dir=Path(self.samples_dir_var.get()),
            )
            self._set_status(f"Exemplo salvo: {path}")
            messagebox.showinfo("Sucesso", f"Diagrama salvo em:\n{path}")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar:\n{exc}")

    def save_all(self) -> None:
        if not self.result_items:
            messagebox.showwarning("Aviso", "Nao ha OCR para salvar.")
            return
        self._sync_fen_from_entry_to_current()
        saved = 0
        invalid = 0
        for idx, item in enumerate(self.result_items):
            fen = self.fen_edits[idx]
            if not is_valid_fen(fen):
                invalid += 1
                continue
            append_training_sample(
                board_rgb=item["board_rgb"],
                fen=fen,
                csv_path=Path(self.dataset_csv_var.get()),
                samples_dir=Path(self.samples_dir_var.get()),
            )
            saved += 1
        self._set_status(f"Salvar todos: {saved} salvos, {invalid} invalidos.")
        messagebox.showinfo("Salvar todos", f"Salvos: {saved}\nInvalidos: {invalid}")

    def correct_fen_with_net(self) -> None:
        if not self.result_items:
            messagebox.showwarning("Aviso", "Nao ha OCR para corrigir.")
            return
        if self._is_correcting_net:
            return

        idx = self._selected_index()
        board_rgb = self.result_items[idx].get("board_rgb")
        if board_rgb is None:
            messagebox.showerror("Erro", "Diagrama atual sem imagem para enviar.")
            return

        self._is_correcting_net = True
        if self.btn_correct_net is not None:
            self.btn_correct_net.configure(state=tk.DISABLED)
        self._set_status("Corrigindo FEN via Net...")

        worker = threading.Thread(
            target=self._correct_fen_with_net_worker,
            args=(idx, np.asarray(board_rgb).copy()),
            daemon=True,
        )
        worker.start()

    def _correct_fen_with_net_worker(self, idx: int, board_rgb: np.ndarray) -> None:
        try:
            fen = self._predict_fen_via_net(board_rgb)
            if not is_valid_fen(fen):
                raise ValueError("API retornou FEN invalida.")
            self.root.after(0, lambda fen_value=fen: self._apply_corrected_fen(idx, fen_value))
        except Exception as exc:
            self.root.after(0, lambda err=exc: self._on_net_correction_error(err))
        finally:
            self.root.after(0, self._finish_net_correction)

    def _finish_net_correction(self) -> None:
        self._is_correcting_net = False
        if self.btn_correct_net is not None:
            self.btn_correct_net.configure(state=tk.NORMAL)

    def _on_net_correction_error(self, exc: Exception) -> None:
        self._set_status("Falha ao corrigir com Net.")
        messagebox.showerror("Corrigir Net", f"Nao foi possivel corrigir o FEN:\n{exc}")

    def _apply_corrected_fen(self, idx: int, fen: str) -> None:
        if idx < 0 or idx >= len(self.fen_edits):
            self._set_status("Correcao recebida, mas o OCR atual mudou.")
            return
        self.fen_edits[idx] = fen
        if idx == self._selected_index():
            self.fen_var.set(fen)
            self._update_result_views()
        self._set_status(f"FEN corrigida via Net (diagrama {idx + 1}).")

    def _predict_fen_via_net(self, board_rgb: np.ndarray) -> str:
        if board_rgb.size == 0:
            raise ValueError("Imagem vazia.")

        image = Image.fromarray(board_rgb.astype(np.uint8))
        with io.BytesIO() as buffer:
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()

        boundary = f"----ChessVisionBoundary{uuid.uuid4().hex}"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("ascii"),
                b'Content-Disposition: form-data; name="file"; filename="board.png"\r\n',
                b"Content-Type: image/png\r\n\r\n",
                image_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode("ascii"),
            ]
        )
        request = urllib.request.Request(
            NET_CORRECT_URL,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace").strip()
            details = details or f"HTTP {exc.code}"
            raise RuntimeError(details) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Erro de rede: {exc.reason}") from exc

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Resposta da API nao esta em JSON.") from exc

        results = parsed.get("results")
        if not isinstance(results, list) or not results:
            message = parsed.get("message") if isinstance(parsed, dict) else ""
            raise RuntimeError(str(message or "API nao retornou resultados."))

        fen = str(results[0].get("fen", "")).strip()
        if not fen:
            raise RuntimeError("API retornou FEN vazia.")
        return fen

    def train_model_in_thread(self) -> None:
        if self._is_training:
            messagebox.showinfo("Treino em andamento", "Ja existe um treino em execucao.")
            return

        csv_path = Path(self.dataset_csv_var.get())
        samples_dir = Path(self.samples_dir_var.get())
        model_path = Path(self.model_path_var.get())
        epochs = int(self.epochs_var.get())
        batch_size = int(self.batch_var.get())
        lr = float(self.lr_var.get())

        self._is_training = True
        self._training_total_epochs = epochs
        self._set_train_controls_enabled(False)
        self._set_training_dialog_text("Preparando treino...", "")
        self._open_training_dialog()

        thread = threading.Thread(
            target=self._train_model_worker,
            kwargs={
                "csv_path": csv_path,
                "samples_dir": samples_dir,
                "model_path": model_path,
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
            },
            daemon=True,
        )
        thread.start()

    def _train_model_worker(
        self,
        csv_path: Path,
        samples_dir: Path,
        model_path: Path,
        epochs: int,
        batch_size: int,
        lr: float,
    ) -> None:
        try:
            self._set_status("Treinando modelo...")
            self._set_training_dialog_text("Treinando modelo...", "")
            history = train_model(
                csv_path=csv_path,
                samples_dir=samples_dir,
                model_path=model_path,
                epochs=epochs,
                batch_size=batch_size,
                lr=lr,
                progress_cb=self._on_training_progress,
            )
            self.reload_model()
            last = history[-1] if history else {}
            self._set_status("Treino concluido.")
            self._set_training_dialog_text("Treino concluido.", self._format_train_metrics(last))
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Treino concluido",
                    f"Epocas: {len(history)}\nUltima metrica: {last}",
                ),
            )
        except Exception as exc:
            self._set_status("Falha no treino.")
            self._set_training_dialog_text("Falha no treino.", str(exc))
            error_text = str(exc)
            self.root.after(0, lambda msg=error_text: messagebox.showerror("Erro no treino", msg))
        finally:
            self.root.after(0, self._finish_training_ui)


def main() -> None:
    configure_logging(log_file=default_log_file())
    logger.info("Iniciando interface desktop.")
    root = tk.Tk()
    ChessOcrTkApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
