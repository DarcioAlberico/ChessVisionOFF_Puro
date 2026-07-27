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
    ACCEPT_MIN_CONFIDENCE,
    BOARD_SIZE,
    DEFAULT_DATASET_CSV,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
    DEFAULT_SAMPLES_DIR,
    find_default_pdf_path,
)
from chess_diagram_ocr.dataset import append_training_sample
from chess_diagram_ocr.dataset_browser import DatasetRow, update_row
from chess_diagram_ocr.detection import detect_diagrams_in_pdf_page
from chess_diagram_ocr.export_checkpoint import partial_path_for
from chess_diagram_ocr.fen_utils import board_from_fen, check_position, is_valid_fen, square_name
from chess_diagram_ocr.inference import describe_device, load_model, predict_board, predict_with_orientation
from chess_diagram_ocr.logging_setup import configure_logging, default_log_file
from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page
from chess_diagram_ocr.pdf_text import DiagramContext, contexts_for_pdf_page
from chess_diagram_ocr.pdf_to_pgn import (
    ExportReport,
    default_pgn_output_path,
    save_pdf_positions_to_pgn,
)
from chess_diagram_ocr.review_queue import DEFAULT_QUEUE_PATH, ReviewItem
from chess_diagram_ocr.semantics import compose_fen, infer_side_to_move
from chess_diagram_ocr.training import train_model
from chess_diagram_ocr.ui import board_edit
from chess_diagram_ocr.ui.board_widget import InteractiveBoard, PieceImages
from chess_diagram_ocr.ui.dataset_panel import DatasetPanel
from chess_diagram_ocr.ui.legality import explain_position
from chess_diagram_ocr.ui.page_results import (
    PageOcrParams,
    PageResults,
    PageResultsCache,
    PageSwitch,
    decide_page_switch,
    page_index_from_origin,
)
from chess_diagram_ocr.ui.review_panel import ReviewPanel, ScanRequest
from chess_diagram_ocr.ui.state import AppState, load_state, save_state
from chess_diagram_ocr.webview2_panel import EmbeddedWebView2, WebView2SupportError

ROOT = Path(__file__).resolve().parent
PIECE_IMAGE_DIR = ROOT / "assets" / "piece_images"
APP_STATE_PATH = ROOT / "data" / "app_tkinter_state.json"
DEFAULT_SPLITS_PATH = ROOT / "data" / "splits.csv"

logger = logging.getLogger(__name__)

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
        self.side_edits: list[str] = []
        """Lado a jogar por diagrama, editavel. Espelha `fen_edits` (S-19)."""

        self._page_results = PageResultsCache()
        """Reconhecimento guardado por pagina, para navegar sem perde-lo."""

        self._results_page_key: tuple[str, int] | None = None
        """De que pagina de PDF vem o que esta no editor agora.

        `None` significa que o conteudo atual nao veio de uma pagina inteira de PDF -- e
        imagem local, recorte de area, item da fila de revisao ou amostra do dataset. Trocar
        de pagina nao mexe nesses: apagar o trabalho de quem estava editando uma amostra do
        dataset porque a pagina do PDF mudou seria pior que nao guardar nada.
        """

        self.study_board = chess.Board()
        self.study_game = chess.pgn.Game()
        self.study_game.setup(self.study_board.copy(stack=False))
        self.study_current_node: chess.pgn.GameNode = self.study_game
        # Selecao e arraste moraram aqui ate a S-20; agora sao estado interno do
        # `InteractiveBoard`, e o app so guarda a arvore de variantes.
        self.study_origin_var = tk.StringVar(value="Base: posicao inicial")
        self.study_status_var = tk.StringVar(value="")
        self.study_fen_var = tk.StringVar(value=self.study_board.fen())
        self.study_variation_var = tk.StringVar(value="")
        self.study_follow_ocr_var = tk.BooleanVar(value=True)
        self.study_flipped_var = tk.BooleanVar(value=False)
        self.left_tabs: ttk.Notebook | None = None
        self.local_results_tab: ttk.Frame | None = None
        self.result_board: InteractiveBoard | None = None
        self.study_board_widget: InteractiveBoard | None = None
        self.study_moves_text: tk.Text | None = None
        self.study_variation_combo: ttk.Combobox | None = None
        self.review_panel: ReviewPanel | None = None
        self.dataset_panel: DatasetPanel | None = None
        self._review_position: int | None = None
        """Índice do item da fila que está aberto no editor, para devolver a correção."""

        self._editing_sample: str | None = None
        """Amostra do dataset aberta no editor (S-23). `None` = editando OCR."""

        self._model_cache = None
        self._model_cache_path: Path | None = None
        self._model_device: str | None = None

        self.page_photo: ImageTk.PhotoImage | None = None
        self.piece_images = PieceImages(PIECE_IMAGE_DIR)
        self.state = AppState()

        self.model_path_var = tk.StringVar(value=str(DEFAULT_MODEL_PATH))
        self.dataset_csv_var = tk.StringVar(value=str(DEFAULT_DATASET_CSV))
        self.samples_dir_var = tk.StringVar(value=str(DEFAULT_SAMPLES_DIR))
        self.orientation_var = tk.StringVar(value=DEFAULT_ORIENTATION_MODE)
        self.page_index_var = tk.IntVar(value=0)
        self.dpi_var = tk.IntVar(value=220)
        self.max_boards_var = tk.IntVar(value=DEFAULT_MAX_BOARDS)
        self.selected_diag_var = tk.IntVar(value=1)
        self.selected_diag_idx = 0
        self.fen_var = tk.StringVar(value="")
        self.side_to_move_var = tk.StringVar(value="w")
        self.side_source_var = tk.StringVar(value="")
        self.heatmap_var = tk.BooleanVar(value=True)
        self.legality_var = tk.StringVar(value="")
        self.material_var = tk.StringVar(value="")
        self.epochs_var = tk.IntVar(value=8)
        self.batch_var = tk.IntVar(value=128)
        self.lr_var = tk.DoubleVar(value=0.001)
        self.fresh_var = tk.BooleanVar(value=False)
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
        self.btn_cancel_export: ttk.Button | None = None
        self._export_cancel_event: threading.Event | None = None
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
        self._bind_shortcuts()
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
        tabs.add(local_tab, text="Resultado")
        tabs.add(analysis_tab, text="Analise")

        # Fila de revisao (S-22) e navegador do dataset (S-23) como abas proprias: o codigo
        # delas mora em `ui/`, para nao repetir o inchaco que a Fase 6 vai ter de desfazer.
        self.review_panel = ReviewPanel(
            tabs,
            scan_request=self._current_scan_request,
            on_open=self.open_review_item,
            on_status=self._set_status,
            queue_path=DEFAULT_QUEUE_PATH,
        )
        tabs.add(self.review_panel, text="Revisao")

        self.dataset_panel = DatasetPanel(
            tabs,
            paths=self._dataset_paths,
            on_edit=self.open_dataset_row,
            on_recheck=self.recheck_dataset_row,
            on_status=self._set_status,
        )
        tabs.add(self.dataset_panel, text="Dataset")

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
        # Ate 30: uma pagina de exercicios com grade 3x3 tem 9, e o teto antigo de 8
        # cortava o nono em silencio. Quem filtra e o piso de score do detector, nao este
        # numero -- medido, subir o teto nao admite candidato a mais em livro nenhum.
        self._spin_row(cfg_tab, "Max diagramas", self.max_boards_var, 1, 30, 1)

        btns_model = ttk.Frame(cfg_tab)
        btns_model.pack(fill=tk.X, padx=8, pady=(4, 8))
        ttk.Button(btns_model, text="Recarregar modelo", command=self.reload_model).pack(side=tk.LEFT)

        train_box = ttk.LabelFrame(cfg_tab, text="Treino (salva em piece_classifier.pt)")
        train_box.pack(fill=tk.X, padx=8, pady=(4, 8))
        self._spin_row(train_box, "Epocas", self.epochs_var, 1, 200, 1)
        self._spin_row(train_box, "Batch size", self.batch_var, 16, 512, 16)
        self._entry_row(train_box, "Learning rate", self.lr_var)
        ttk.Checkbutton(
            train_box,
            text="Treinar do zero (ignora o checkpoint atual)",
            variable=self.fresh_var,
        ).pack(anchor="w", padx=8)
        ttk.Label(
            train_box,
            text="Sem isso, o treino continua do checkpoint e so grava por cima se melhorar.",
            wraplength=320,
            foreground="#555555",
        ).pack(anchor="w", padx=8, pady=(0, 4))
        self.btn_train_model = ttk.Button(train_box, text="Treinar modelo", command=self.train_model_in_thread)
        self.btn_train_model.pack(anchor="w", padx=8, pady=8)

        local_btns = ttk.Frame(local_tab)
        local_btns.pack(fill=tk.X, padx=8, pady=8)
        self.btn_ocr_local_best = ttk.Button(local_btns, text="OCR local (melhor)", command=self.ocr_local_best)
        self.btn_ocr_local_best.pack(side=tk.LEFT)
        self.btn_ocr_local_all = ttk.Button(local_btns, text="OCR local (todos)", command=self.ocr_local_all)
        self.btn_ocr_local_all.pack(side=tk.LEFT, padx=6)
        ttk.Label(local_tab, text="Use imagem local para OCR fora do PDF.").pack(anchor="w", padx=8, pady=(2, 8))

        rec_box = ttk.LabelFrame(local_tab, text="Reconhecido (clique e arraste para corrigir)")
        rec_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        zoom_row = ttk.Frame(rec_box)
        zoom_row.pack(fill=tk.X, padx=8, pady=(6, 0))
        ttk.Label(zoom_row, text="Zoom board").pack(side=tk.LEFT)
        ttk.Button(zoom_row, text="-", width=3, command=lambda: self.zoom_board(-0.1)).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(zoom_row, text="+", width=3, command=lambda: self.zoom_board(0.1)).pack(side=tk.LEFT, padx=(2, 6))
        self.lbl_board_zoom = ttk.Label(zoom_row, text="85%")
        self.lbl_board_zoom.pack(side=tk.LEFT)
        ttk.Checkbutton(
            zoom_row,
            text="Heatmap de incerteza",
            variable=self.heatmap_var,
            command=self.on_heatmap_toggle,
        ).pack(side=tk.RIGHT)

        # O editor da S-20 no lugar do canvas somente-leitura: corrigir uma peca passa de
        # "contar casas e reescrever a FEN" para um arraste.
        self.result_board = InteractiveBoard(
            rec_box,
            mode="edit",
            on_change=self.on_result_board_changed,
            on_select=self.on_result_square_selected,
            on_status=self._set_status,
            piece_images=self.piece_images,
            background="#f2f2f2",
            min_size=260,
            max_size=520,
        )
        self.result_board.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.result_board.set_heatmap_enabled(True)

        legal_box = ttk.Frame(rec_box)
        legal_box.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(legal_box, textvariable=self.legality_var, wraplength=520, justify=tk.LEFT).pack(anchor="w")
        ttk.Label(legal_box, textvariable=self.material_var, foreground="#555555").pack(anchor="w")

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

        # Lado a jogar visivel e editavel (S-16/S-19). Ate a Fase 3 o app nao tinha onde
        # mostrar isso, e a informacao -- quando o PDF a dava -- morria na exportacao.
        side_row = ttk.Frame(fen_box)
        side_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(side_row, text="Lado a jogar").pack(side=tk.LEFT)
        for texto, valor in (("Brancas", "w"), ("Pretas", "b")):
            ttk.Radiobutton(
                side_row,
                text=texto,
                value=valor,
                variable=self.side_to_move_var,
                command=self.on_side_to_move_change,
            ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(side_row, textvariable=self.side_source_var).pack(side=tk.LEFT, padx=(10, 0))

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

        # Mesmo widget do painel de resultado, em modo de jogo (S-20). Antes eram duas
        # implementacoes de tabuleiro no mesmo arquivo, e so uma delas era interativa.
        self.study_board_widget = InteractiveBoard(
            parent,
            mode="play",
            on_move=self._push_study_move,
            on_status=self._set_study_status,
            promotion_chooser=self._choose_study_promotion,
            piece_images=self.piece_images,
        )
        self.study_board_widget.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        canvas = self.study_board_widget.canvas
        canvas.bind("<Left>", lambda _event: self.undo_study_move())
        canvas.bind("<Right>", lambda _event: self.redo_study_move())
        canvas.bind("<Home>", lambda _event: self.go_to_start_of_study_line())
        canvas.bind("<End>", lambda _event: self.go_to_end_of_study_line())

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
        self.btn_cancel_export = ttk.Button(
            ocr_row,
            text="Cancelar exportacao",
            command=self.cancel_pdf_export,
            state=tk.DISABLED,
        )
        self.btn_cancel_export.pack(side=tk.LEFT)

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
        """Restaura o estado gravado. Sem PDF utilizável, cai no primeiro PDF da pasta.

        Fonte única de leitura (S-25): `load_pdf` não relê mais o arquivo por conta própria,
        consulta `self.state`.
        """
        self.state = load_state(APP_STATE_PATH)

        self.pdf_zoom_var.set(self.state.pdf_zoom)
        self.board_zoom_var.set(self.state.board_zoom)
        self.heatmap_var.set(self.state.show_heatmap)
        if self.result_board is not None:
            self.result_board.set_heatmap_enabled(self.state.show_heatmap)
        self._update_zoom_labels()

        last_pdf = self.state.last_pdf.strip()
        if not last_pdf:
            self._set_default_pdf_if_exists()
            return

        pdf_path = Path(last_pdf)
        if not pdf_path.exists():
            # Antes isto era um `return False` silencioso e o usuario so via o PDF errado
            # abrir, sem saber por que.
            logger.warning("Ultimo PDF do estado nao existe mais: %s", pdf_path)
            self._set_status(f"Ultimo PDF nao encontrado: {pdf_path}")
            self._set_default_pdf_if_exists()
            return

        self.load_pdf(pdf_path)
        if self.page_count > 0:
            clamped_page = max(0, min(self.page_count - 1, self.state.last_page))
            if clamped_page != int(self.page_index_var.get()):
                self.page_index_var.set(clamped_page)
                self.page_loaded_for_index = None
                self.render_current_page()

    def _save_app_state(self) -> None:
        try:
            if self.pdf_source is not None:
                self.state.remember_page(self.pdf_source, int(self.page_index_var.get()))
            self.state.last_pdf = str(self.pdf_source) if self.pdf_source is not None else ""
            self.state.last_page = int(self.page_index_var.get())
            self.state.pdf_zoom = float(self.pdf_zoom_var.get())
            self.state.board_zoom = float(self.board_zoom_var.get())
            self.state.show_heatmap = bool(self.heatmap_var.get())
            if self.review_panel is not None:
                self.state.review_queue_path = str(self.review_panel.queue_path)
        except tk.TclError as exc:
            logger.warning("Estado da aplicacao nao pode ser montado: %s", exc)
            return
        save_state(APP_STATE_PATH, self.state)

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
        if self.btn_cancel_export is not None:
            # O cancelar so existe enquanto ha o que cancelar.
            self.btn_cancel_export.configure(state=tk.DISABLED if enabled else tk.NORMAL)

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
        # A ordem importa: `val_board_exact_acc` (S-27) e a metrica que decide qual epoca
        # e salva, entao ela vem primeiro. `val_acc` por casa fica ~0,999 mesmo quando um
        # em cada vinte tabuleiros tem erro -- ver o comentario em training.py.
        for key, label in (
            ("val_board_exact_acc", "exata/tabuleiro"),
            ("train_loss", "train_loss"),
            ("train_square_acc", "train_acc"),
            ("val_loss", "val_loss"),
            ("val_square_acc", "val_acc/casa"),
        ):
            if key in row:
                parts.append(f"{label}={float(row[key]):.4f}")
        if row.get("is_best"):
            parts.append("(melhor ate agora)")
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
        if self.result_board is not None:
            self.result_board.canvas.configure(height=int(520 * new_zoom))
            self.result_board.redraw()

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
            # S-30: o dispositivo era escolhido em silencio, entao uma maquina com placa
            # mas com o torch +cpu instalado rodava em CPU sem nada dizer.
            self._set_status(f"Modelo carregado em {describe_device(device)}.")
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
            # Reconhecimento guardado e por (documento, pagina): trocar de PDF invalida
            # tudo o que estava em cache, e mante-lo faria a pagina 17 do livro novo
            # devolver os diagramas da pagina 17 do anterior.
            self._remember_current_page_results()
            if self._document_key() != str(pdf_path):
                self._page_results.clear()
                self._results_page_key = None
            self.pdf_source = pdf_path
            self.pdf_name = pdf_path.name
            self.page_count = get_pdf_page_count(self.pdf_source)
            self.lbl_pdf.config(text=f"{self.pdf_name} ({self.page_count} pags)")

            target_page = self.state.page_for(pdf_path)
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
        partial_path = partial_path_for(output_path)
        resume = True
        if partial_path.exists():
            # Retomar e o padrao, mas nao em silencio: quem esta refazendo a exportacao de
            # proposito precisa poder dizer "comeca do zero" (S-24).
            answer = messagebox.askyesnocancel(
                "Exportacao interrompida encontrada",
                f"Existe um progresso parcial em:\n{partial_path}\n\n"
                "Sim: retomar de onde parou.\n"
                "Nao: recomecar do zero, descartando o parcial.\n"
                "Cancelar: abortar.",
            )
            if answer is None:
                return
            resume = bool(answer)
            if not resume:
                partial_path.unlink(missing_ok=True)
        elif output_path.exists():
            overwrite = messagebox.askyesno(
                "Sobrescrever PGN",
                f"O arquivo ja existe:\n{output_path}\n\nDeseja sobrescrever?",
            )
            if not overwrite:
                return

        self._is_exporting_pdf_pgn = True
        self._export_cancel_event = threading.Event()
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
                "resume": resume,
                "cancel_event": self._export_cancel_event,
            },
            daemon=True,
        )
        worker.start()

    def cancel_pdf_export(self) -> None:
        if self._export_cancel_event is None:
            return
        self._export_cancel_event.set()
        self._set_status("Cancelando exportacao... o progresso da pagina atual sera preservado.")
        if self.btn_cancel_export is not None:
            self.btn_cancel_export.configure(state=tk.DISABLED)

    def _export_pdf_to_pgn_worker(
        self,
        *,
        pdf_path: Path,
        output_path: Path,
        model_path: Path,
        dpi: int,
        max_boards_per_page: int,
        orientation: str,
        resume: bool,
        cancel_event: threading.Event,
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
                resume=resume,
                cancel_event=cancel_event,
                progress_callback=_progress,
            )
            self.root.after(0, lambda: self._on_export_pdf_to_pgn_success(report))
        except Exception as exc:
            self.root.after(0, lambda err=exc: self._on_export_pdf_to_pgn_error(err))
        finally:
            self.root.after(0, self._finish_export_pdf_to_pgn)

    def _on_export_pdf_to_pgn_success(self, report: ExportReport) -> None:
        self._set_status(f"Exportacao concluida. {report.summary()}.")

        titulo = "Exportacao cancelada" if report.cancelled else "Arquivo gerado com sucesso."
        linhas = [
            titulo,
            "",
            f"PGN: {report.output_path}",
            f"Aceitos: {len(report.accepted)} de {report.total}",
        ]
        if report.resumed_from_page is not None:
            linhas.insert(1, f"(retomada a partir da pagina {report.resumed_from_page + 1})")
        # O gate so ajuda se o usuario souber o que ficou de fora (S-15).
        if report.review_path is not None:
            linhas += [
                "",
                f"Para revisao: {len(report.needs_review)} de baixa confianca, {len(report.rejected)} ilegais.",
                f"Arquivo: {report.review_path}",
            ]
        if report.cancelled and report.partial_path is not None:
            linhas += [
                "",
                "O progresso foi preservado. Exportar de novo para o mesmo arquivo oferece retomar.",
                f"Parcial: {report.partial_path}",
            ]
        messagebox.showinfo("Exportar PDF para PGN", "\n".join(linhas))

    def _on_export_pdf_to_pgn_error(self, exc: Exception) -> None:
        self._set_status("Falha na exportacao do PDF para PGN.")
        messagebox.showerror("Exportar PDF para PGN", f"Nao foi possivel exportar o PDF:\n{exc}")

    def _finish_export_pdf_to_pgn(self) -> None:
        self._is_exporting_pdf_pgn = False
        self._export_cancel_event = None
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

        # Antes de trocar de pagina, o que esta no editor tem de ir para o cache da pagina
        # de origem -- inclusive o texto que o usuario acabou de digitar no campo de FEN.
        self._remember_current_page_results()
        try:
            self._set_status(f"Renderizando pagina {idx}...")
            self.page_rgb = render_pdf_page(self.pdf_source, idx, dpi=int(self.dpi_var.get()))
            self.page_loaded_for_index = idx
            self._refresh_pdf_view()
            self._save_app_state()
            self._set_status(f"Pagina {idx} pronta.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao renderizar pagina:\n{exc}")
            return

        self._restore_results_for_page(idx)

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
        contexts: list[DiagramContext] = []
        detection_sources: list[str] = []
        if pdf_page is not None:
            # Pagina de PDF: usa o detector das duas fontes, igual a exportacao (S-12).
            source, page_index = pdf_page
            candidates = detect_diagrams_in_pdf_page(source, page_index, image_rgb, max_boards=max_boards)
            boards = [(candidate.board_rgb, None) for candidate in candidates]
            detection_sources = [candidate.source for candidate in candidates]
            # Mesmo contexto textual que a exportacao usa (S-16): a GUI mostrando um lado a
            # jogar e o PGN gravando outro seria pior que nao mostrar nada.
            contexts = contexts_for_pdf_page(source, page_index, [c.bbox_pdf for c in candidates])
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
            context = contexts[idx] if idx < len(contexts) else None
            side = infer_side_to_move(prediction.fen_board, context)
            resolved = check_position(compose_fen(prediction.fen_board, side))
            items.append(
                {
                    "index": idx,
                    "board_rgb": board_for_pred,
                    "quad": quad_for_item.tolist() if quad_for_item is not None else None,
                    "fen_pred": prediction.fen_board,
                    "confidence": prediction.mean_confidence,
                    "min_confidence": prediction.min_confidence,
                    "uncertain_squares": prediction.uncertain_squares,
                    # Insumos do heatmap e do tooltip (S-21). A matriz por casa ja existia
                    # desde a S-10 e era descartada aqui -- a UI so via o agregado.
                    "probs": prediction.probs,
                    "square_confidences": [float(value) for value in prediction.square_confidences],
                    "changed_squares": [square for square, _argmax, _final in (prediction.decode.changed_squares if prediction.decode else [])],
                    # Legalidade com o lado a jogar ja decidido (S-17): o "xeque invertido"
                    # que a GUI mostrava some quando a inferencia descobre de quem e a vez.
                    "is_legal": resolved.is_legal,
                    "is_fatal": resolved.is_fatal,
                    "problems": resolved.problems,
                    "rotation": oriented.rotation,
                    "orientation_ambiguous": oriented.ambiguous,
                    "orientation_reason": oriented.reason,
                    "side_to_move": "w" if side.color else "b",
                    "side_to_move_source": side.source,
                    "side_to_move_reason": side.reason,
                    "side_conflicting": side.conflicting,
                    "context": context,
                    "detection_source": detection_sources[idx] if idx < len(detection_sources) else "",
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

    def _document_key(self) -> str:
        return str(self.pdf_source) if self.pdf_source is not None else ""

    def _current_ocr_params(self) -> PageOcrParams:
        return PageOcrParams(
            dpi=int(self.dpi_var.get()),
            max_boards=int(self.max_boards_var.get()),
            orientation=str(self.orientation_var.get()),
            model_path=self.model_path_var.get().strip(),
        )

    def _remember_current_page_results(self) -> None:
        """Guarda o que esta no editor no cache da pagina de onde ele veio.

        As listas vao por referencia, entao correcao feita durante a edicao ja esta no
        cache; o que precisa ser copiado e o indice selecionado, que e escalar.
        """
        if self._results_page_key is None or not self.result_items:
            return
        self._sync_fen_from_entry_to_current()
        documento, pagina = self._results_page_key
        self._page_results.put(
            documento,
            PageResults(
                page_index=pagina,
                params=self._current_ocr_params(),
                items=self.result_items,
                fen_edits=self.fen_edits,
                side_edits=self.side_edits,
                selected_index=self.selected_diag_idx,
            ),
        )

    def _restore_results_for_page(self, page_index: int) -> None:
        """Traz de volta o reconhecimento da pagina, se houver, ao trocar de pagina.

        Sem isto o seletor "Selecionado" continua apontando para os diagramas da pagina
        reconhecida anteriormente, que nao sao os da pagina na tela.
        """
        documento = self._document_key()
        guardado = self._page_results.get(documento, page_index, self._current_ocr_params())
        acao = decide_page_switch(stored=guardado, current_is_page_result=self._results_page_key is not None)

        if acao is PageSwitch.RESTORE:
            assert guardado is not None
            self._apply_page_results(guardado, documento)
        elif acao is PageSwitch.CLEAR:
            self._results_page_key = None
            self._clear_ocr_results()
            self._set_status(f"Pagina {page_index}: sem reconhecimento ainda. Rode o OCR.")

    def _apply_page_results(self, guardado: PageResults, documento: str) -> None:
        self._editing_sample = None
        self._review_position = None
        self.result_items = guardado.items
        self.fen_edits = guardado.fen_edits
        self.side_edits = guardado.side_edits
        self.selected_diag_idx = guardado.clamped_index()
        self._results_page_key = (documento, guardado.page_index)

        self.selected_diag_var.set(self.selected_diag_idx + 1)
        self.spin_diag.config(from_=1, to=max(guardado.count, 1))
        self.fen_var.set(self.fen_edits[self.selected_diag_idx] if self.fen_edits else "")
        self._sync_side_widgets(self.selected_diag_idx)
        self._update_result_views()
        self.root.after_idle(self._redraw_current_result_board)
        self._set_status(
            f"Pagina {guardado.page_index}: {guardado.count} diagrama(s) do reconhecimento anterior"
            f"{', com correcoes suas' if guardado.has_hand_edits else ''}."
        )

    def _page_key_from_origin(self, origin: str) -> tuple[str, int] | None:
        pagina = page_index_from_origin(origin)
        return None if pagina is None else (self._document_key(), pagina)

    def _apply_ocr_result_items(self, items: list[dict[str, Any]], origin: str) -> None:
        # OCR novo substitui o que estava no editor: se veio da fila ou do dataset, a
        # ligacao com aquele item deixa de valer.
        self._editing_sample = None
        self._review_position = None
        self.result_items = items
        self.fen_edits = [item["fen_pred"] for item in items]
        self.side_edits = [str(item.get("side_to_move") or "w") for item in items]
        self.selected_diag_idx = 0
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=max(len(items), 1))
        self.fen_var.set(self.fen_edits[0] if self.fen_edits else "")
        self._sync_side_widgets(0)
        self._show_local_results_tab()
        self._update_result_views()
        self.root.after_idle(self._redraw_current_result_board)

        self._results_page_key = self._page_key_from_origin(origin)
        self._remember_current_page_results()

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
        self.side_edits = []
        self.selected_diag_idx = 0
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=1)
        self.fen_var.set("")
        self.side_to_move_var.set("w")
        self.side_source_var.set("")
        self._update_result_views()

    def _sync_side_widgets(self, idx: int) -> None:
        """Põe na tela o lado a jogar do diagrama e de onde ele veio.

        A procedência aparece junto porque "pretas jogam" lido de uma legenda e "pretas
        jogam" assumido pelo padrão têm o mesmo texto e valores completamente diferentes
        para quem vai conferir.
        """
        if not self.result_items or idx < 0 or idx >= len(self.side_edits):
            self.side_source_var.set("")
            return

        self.side_to_move_var.set(self.side_edits[idx])
        item = self.result_items[idx]
        rotulos = {
            "text": "do texto do PDF",
            "legality": "deduzido da posicao",
            "default": "assumido",
            "manual": "definido por voce",
            "queue": "vindo da fila de revisao",
        }
        fonte = rotulos.get(str(item.get("side_to_move_source")), "")
        if item.get("side_conflicting"):
            fonte = "texto e posicao discordam"
        self.side_source_var.set(f"({fonte})" if fonte else "")

    def on_side_to_move_change(self) -> None:
        if not self.result_items:
            return
        idx = self._selected_index()
        if 0 <= idx < len(self.side_edits):
            self.side_edits[idx] = self.side_to_move_var.get()
            self.result_items[idx]["side_to_move_source"] = "manual"
            self.result_items[idx]["side_conflicting"] = False
            self._sync_side_widgets(idx)
            if self.result_board is not None:
                self.result_board.set_side_to_move(self.side_edits[idx] != "b")
            # A legalidade depende de quem joga: trocar a vez pode resolver o "xeque
            # invertido" sem mexer em nenhuma peca (S-17).
            self._update_legality_panel()
            self._set_status(f"Diagrama {idx + 1}: lado a jogar definido como {self.side_to_move_var.get()}.")

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
        self._sync_side_widgets(idx)
        self._set_status(f"Diagrama {idx + 1}/{len(self.result_items)} | {self._confidence_summary(idx)}")
        self._update_result_views()

    def apply_fen_edit(self) -> None:
        if not self.result_items:
            return
        self._sync_fen_from_entry_to_current()
        self._update_result_views()

    def _update_result_views(self) -> None:
        if self.result_board is None:
            return
        if not self.result_items:
            self.result_board.set_position(board_edit.EMPTY_PLACEMENT)
            self.result_board.set_uncertainty(None)
            self.result_board.set_probabilities(None)
            self.result_board.set_changed_squares(())
            self.result_board.set_problem_squares(())
            self.legality_var.set("")
            self.material_var.set("")
            return

        idx = self._selected_index()
        fen = self.fen_edits[idx]
        item = self.result_items[idx]

        self.result_board.set_position(fen)
        self.result_board.set_side_to_move(self.side_edits[idx] != "b")
        self._apply_prediction_signals(item)
        self._update_legality_panel()
        self._maybe_sync_study_with_current_fen()

    def _apply_prediction_signals(self, item: dict[str, Any]) -> None:
        """Põe na tela o que o modelo achou de cada casa (S-21).

        Sem isso o usuário só tem a FEN e um número agregado -- e a média de confiança fica
        em 0,97 mesmo quando há erro (S-10), então ela não aponta lugar nenhum.
        """
        if self.result_board is None:
            return

        confidences = item.get("square_confidences")
        self.result_board.set_uncertainty(list(confidences) if confidences is not None else None)
        self.result_board.set_probabilities(item.get("probs"))
        self.result_board.set_changed_squares(item.get("changed_squares") or ())

    def _update_legality_panel(self) -> None:
        """Painel de legalidade da S-21: o problema em pt-BR e as casas que o causam."""
        if self.result_board is None:
            return

        idx = self._selected_index()
        if not self.result_items or idx >= len(self.fen_edits):
            return

        placement = self.result_board.placement
        side = self.side_edits[idx] if idx < len(self.side_edits) else "w"
        explanation = explain_position(compose_fen(placement, side == "w"))

        self.legality_var.set(explanation.summary())
        self.material_var.set(explanation.material_line())
        self.result_board.set_problem_squares(explanation.highlight_squares)

    def on_heatmap_toggle(self) -> None:
        if self.result_board is not None:
            self.result_board.set_heatmap_enabled(bool(self.heatmap_var.get()))
        self._save_app_state()

    def on_result_board_changed(self, placement: str) -> None:
        """Toda edição no tabuleiro reescreve a FEN -- o campo de texto segue funcionando."""
        idx = self._selected_index()
        if not self.result_items or idx >= len(self.fen_edits):
            return
        self.fen_edits[idx] = placement
        self.fen_var.set(placement)
        self.result_items[idx]["edited_by_hand"] = True
        self._update_legality_panel()
        self._maybe_sync_study_with_current_fen()

    def on_result_square_selected(self, index: int | None) -> None:
        if index is None or self.result_board is None:
            return
        top = self.result_board.top_classes(index)
        if not top:
            self._set_status(f"Casa {square_name(index)} selecionada.")
            return
        detalhe = ", ".join(f"{nome} {valor:.1%}" for nome, valor in top)
        self._set_status(f"Casa {square_name(index)}: {detalhe}")

    def _show_local_results_tab(self) -> None:
        if self.left_tabs is None or self.local_results_tab is None:
            return
        try:
            self.left_tabs.select(self.local_results_tab)
        except tk.TclError as exc:
            logger.debug("Nao foi possivel focar a aba de resultados: %s", exc)

    def _redraw_current_result_board(self) -> None:
        if self.result_board is not None:
            self.result_board.redraw()

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
        self._push_position_to_study_widget()

    def _push_position_to_study_widget(self) -> None:
        """Sincroniza o widget com o no atual da arvore. A arvore continua sendo do app."""
        if self.study_board_widget is None:
            return
        self.study_board_widget.set_position(self.study_board.fen())
        self.study_board_widget.set_last_move(self.study_current_node.move)

    def _set_study_board_state(self, board: chess.Board, origin: str, status: str) -> None:
        self.study_game = self._create_study_game(board)
        self.study_current_node = self.study_game
        self._sync_study_board_from_current_node()
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
        if self.study_board_widget is not None:
            self.study_board_widget.set_flipped(self.study_flipped_var.get())

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
        self._refresh_study_view()
        self._set_study_status("Ultimo lance desfeito.")

    def redo_study_move(self) -> None:
        if not self.study_current_node.variations:
            self._set_study_status("Nao ha lances para refazer.")
            return
        idx = self._get_selected_study_variation_index()
        idx = max(0, min(idx, len(self.study_current_node.variations) - 1))
        self.study_current_node = self.study_current_node.variations[idx]
        self._refresh_study_view()
        self._set_study_status("Lance refeito.")

    def go_to_start_of_study_line(self) -> None:
        if self.study_current_node.parent is None:
            self._set_study_status("Ja esta no inicio da linha.")
            return
        while self.study_current_node.parent is not None:
            self.study_current_node = self.study_current_node.parent
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
        self._refresh_study_view()
        self._set_study_status("Avancou para o fim da linha.")

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
        self._refresh_study_view()
        suffix = "Variante seguida." if existing_child is not None else "Lance salvo."
        self._set_study_status(f"{san} | {suffix}")

    # ------------------------------------------------------------------ Fase 4
    # Fila de revisao (S-22), navegador do dataset (S-23) e atalhos (S-20).

    def _current_scan_request(self) -> ScanRequest | None:
        """Parâmetros da varredura como a janela os tem configurados agora."""
        if self.pdf_source is None or not isinstance(self.pdf_source, Path):
            return None
        return ScanRequest(
            pdf_path=self.pdf_source,
            model_path=Path(self.model_path_var.get().strip()),
            labels_csv=Path(self.dataset_csv_var.get()),
            dpi=int(self.dpi_var.get()),
            max_boards_per_page=int(self.max_boards_var.get()),
            orientation=self.orientation_var.get(),  # type: ignore[arg-type]
            reading_order=DEFAULT_READING_ORDER,
            accept_threshold=ACCEPT_MIN_CONFIDENCE,
        )

    def _dataset_paths(self) -> tuple[Path, Path, Path]:
        return (
            Path(self.dataset_csv_var.get()),
            Path(self.samples_dir_var.get()),
            DEFAULT_SPLITS_PATH,
        )

    def open_review_item(self, item: ReviewItem, position: int) -> None:
        """Abre um item da fila no editor, já com o heatmap e a casa suspeita selecionados."""
        board_rgb = self._read_cached_board(item.board_image)
        if board_rgb is None:
            messagebox.showerror("Fila de revisao", f"Miniatura nao encontrada:\n{item.board_image}")
            return

        placement = item.fen.split(" ")[0]
        self._editing_sample = None
        self._review_position = position
        # O que entra aqui e um item da fila, nao o reconhecimento de uma pagina: guardar
        # o que estava antes e desligar o vinculo com a pagina, para que navegar depois nao
        # apague o item da fila nem o confunda com resultado de pagina.
        self._remember_current_page_results()
        self._results_page_key = None
        self.result_items = [
            {
                "index": 0,
                "board_rgb": board_rgb,
                "quad": None,
                "fen_pred": placement,
                "confidence": item.min_confidence,
                "min_confidence": item.min_confidence,
                "uncertain_squares": list(item.uncertain_squares),
                "probs": None,
                "square_confidences": list(item.square_confidences) or None,
                "changed_squares": list(item.changed_squares),
                "is_legal": None,
                "is_fatal": None,
                "problems": (),
                "rotation": None,
                "orientation_ambiguous": False,
                "orientation_reason": "",
                "side_to_move": item.side_to_move,
                "side_to_move_source": "queue",
                "side_to_move_reason": "; ".join(item.reasons),
                "side_conflicting": False,
                "context": None,
                "detection_source": "",
            }
        ]
        self.fen_edits = [placement]
        self.side_edits = [item.side_to_move]
        self.selected_diag_idx = 0
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=1)
        self.fen_var.set(placement)
        self._sync_side_widgets(0)
        self._show_local_results_tab()
        self._update_result_views()

        if self.result_board is not None and item.first_uncertain_square is not None:
            # Abrir ja na casa suspeita e o que a S-22 pede do "corrigir agora": sem isso o
            # usuario recebe o tabuleiro inteiro de novo e a fila nao economizou nada.
            self.result_board.select_square(item.first_uncertain_square)
        self._set_status(f"Revisao {item.label}: {'; '.join(item.reasons)}")

    def _read_cached_board(self, path_text: str) -> np.ndarray | None:
        path = Path(path_text)
        if not path.exists():
            return None
        image_bgr = cv2.imread(str(path))
        if image_bgr is None:
            return None
        return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    def open_dataset_row(self, row: DatasetRow) -> None:
        """Abre uma amostra do dataset no editor. Salvar regrava a linha, não cria outra."""
        samples_dir = Path(self.samples_dir_var.get())
        board_rgb = self._read_cached_board(str(row.image_path(samples_dir)))
        if board_rgb is None:
            messagebox.showerror("Dataset", f"Imagem nao encontrada:\n{row.image_path(samples_dir)}")
            return

        placement = row.placement
        side = row.side_to_move if row.side_to_move in ("w", "b") else "w"
        self._editing_sample = row.filename
        self._review_position = None
        # Amostra do dataset: mesmo raciocinio do item da fila acima.
        self._remember_current_page_results()
        self._results_page_key = None
        self.result_items = [
            {
                "index": 0,
                "board_rgb": board_rgb,
                "quad": None,
                "fen_pred": placement,
                "confidence": 0.0,
                "min_confidence": 0.0,
                "uncertain_squares": [],
                "probs": None,
                "square_confidences": None,
                "changed_squares": [],
                "is_legal": row.legality == "legal",
                "is_fatal": row.legality == "ilegal",
                "problems": row.problems,
                "rotation": None,
                "orientation_ambiguous": False,
                "orientation_reason": "",
                "side_to_move": side,
                "side_to_move_source": "manual",
                "side_to_move_reason": "rotulo do dataset",
                "side_conflicting": False,
                "context": None,
                "detection_source": row.detection_source,
            }
        ]
        self.fen_edits = [placement]
        self.side_edits = [side]
        self.selected_diag_idx = 0
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=1)
        self.fen_var.set(placement)
        self._sync_side_widgets(0)
        self._show_local_results_tab()
        self._update_result_views()
        self._set_status(f"Editando amostra {row.filename} (Ctrl+S regrava o rotulo).")

    def recheck_dataset_row(self, row: DatasetRow) -> str:
        """Roda o modelo na amostra e compara com o rótulo gravado (S-23).

        É o caminho para achar rótulo **humano** errado: se o modelo discorda em uma casa e
        o rótulo é o esquisito, quem está errado é a anotação.
        """
        samples_dir = Path(self.samples_dir_var.get())
        board_rgb = self._read_cached_board(str(row.image_path(samples_dir)))
        if board_rgb is None:
            raise FileNotFoundError(f"Imagem nao encontrada: {row.image_path(samples_dir)}")

        model, device = self._get_model()
        prediction = predict_board(cv2.resize(board_rgb, (BOARD_SIZE, BOARD_SIZE)), model, device)
        divergentes = board_edit.differing_squares(row.placement, prediction.fen_board)

        linhas = [
            f"Amostra: {row.filename}",
            f"Rotulo:  {row.placement}",
            f"Modelo:  {prediction.fen_board}",
            f"Confianca minima do modelo: {prediction.min_confidence:.3f}",
            "",
        ]
        if not divergentes:
            linhas.append("O modelo concorda com o rotulo em todas as 64 casas.")
        else:
            linhas.append(f"Divergem em {len(divergentes)} casa(s):")
            rotulo = board_edit.squares_from_placement(row.placement)
            lido = board_edit.squares_from_placement(prediction.fen_board)
            for index in divergentes[:12]:
                confianca = float(prediction.square_confidences[index])
                linhas.append(
                    f"  {square_name(index)}: rotulo {rotulo[index] or 'vazia'} | "
                    f"modelo {lido[index] or 'vazia'} ({confianca:.1%})"
                )
            if len(divergentes) > 12:
                linhas.append(f"  ... e outras {len(divergentes) - 12}")
        return "\n".join(linhas)

    def _bind_shortcuts(self) -> None:
        """Atalhos do ciclo corrigir → salvar → próximo (S-20).

        Ligados na janela e filtrados por foco: com o cursor num `Entry` ou `Text`, as setas
        e o `Del` pertencem ao campo de texto, não à navegação de diagramas.
        """
        bindings = {
            "<Left>": lambda _event: self.prev_diagram(),
            "<Right>": lambda _event: self.next_diagram(),
            "<Control-s>": lambda _event: self.save_current(),
            "<Control-S>": lambda _event: self.save_all(),
            "<Control-r>": lambda _event: self.ocr_all(),
            "<Delete>": lambda _event: self._delete_selected_square(),
            "<Control-n>": lambda _event: self._open_next_review_item(),
        }
        for sequence, handler in bindings.items():
            self.root.bind_all(sequence, self._guard_shortcut(handler))

    def _guard_shortcut(self, handler: Any) -> Any:
        def _wrapped(event: tk.Event) -> str | None:
            widget = getattr(event, "widget", None)
            if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox)):
                return None
            handler(event)
            return "break"

        return _wrapped

    def _delete_selected_square(self) -> None:
        if self.result_board is not None and self.result_board.delete_selected():
            return
        self._set_status("Selecione uma casa do tabuleiro para apagar a peca.")

    def _open_next_review_item(self) -> None:
        if self.review_panel is None:
            return
        self.review_panel.open_next_pending()

    def _sample_metadata(self, idx: int) -> dict[str, Any]:
        """Campos da S-19 para a amostra: lado a jogar e de onde ela veio.

        Gravar a origem é o que permite, depois, agrupar o split por livro (S-07), auditar
        por fonte e voltar ao PDF para recortar de novo. Os 3.195 rótulos existentes não a
        têm porque ela nunca foi pedida aqui.
        """
        item = self.result_items[idx] if 0 <= idx < len(self.result_items) else {}
        return {
            "side_to_move": self.side_edits[idx] if 0 <= idx < len(self.side_edits) else None,
            "source_pdf": self.pdf_name,
            "source_page": self.page_index_var.get() + 1 if self.pdf_source is not None else "",
            "source_diagram": idx + 1,
            "detection_source": str(item.get("detection_source") or ""),
        }

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

        # Amostra vinda da aba Dataset regrava a linha que ja existe; salvar de novo criaria
        # uma segunda amostra da mesma imagem e o rotulo errado continuaria no arquivo (S-23).
        if self._editing_sample is not None:
            self._save_edited_dataset_sample(idx, fen)
            return

        try:
            path = append_training_sample(
                board_rgb=self.result_items[idx]["board_rgb"],
                fen=fen,
                csv_path=Path(self.dataset_csv_var.get()),
                samples_dir=Path(self.samples_dir_var.get()),
                **self._sample_metadata(idx),
            )
            self._set_status(f"Exemplo salvo: {path}")
            self._settle_review_item(idx)
            messagebox.showinfo("Sucesso", f"Diagrama salvo em:\n{path}")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar:\n{exc}")

    def _save_edited_dataset_sample(self, idx: int, fen: str) -> None:
        filename = self._editing_sample or ""
        side = self.side_edits[idx] if idx < len(self.side_edits) else "w"
        try:
            atualizado = update_row(
                Path(self.dataset_csv_var.get()),
                filename,
                fen=fen,
                side_to_move=side,
                corrected_by="tkinter",
            )
        except ValueError as exc:
            messagebox.showerror("Dataset", str(exc))
            return

        if not atualizado:
            messagebox.showerror("Dataset", f"Amostra nao encontrada no CSV: {filename}")
            return

        self._set_status(f"Rotulo de {filename} regravado.")
        if self.dataset_panel is not None:
            self.dataset_panel.reload()
        messagebox.showinfo("Dataset", f"Rotulo regravado:\n{filename}")

    def _settle_review_item(self, idx: int) -> None:
        """Fecha na fila o item que acabou de ser corrigido e salvo (S-22)."""
        if self.review_panel is None or self._review_position is None:
            return
        self.review_panel.apply_correction(
            self._review_position,
            self.fen_edits[idx],
            self.side_edits[idx] if idx < len(self.side_edits) else "w",
        )
        self._set_status(f"Item da fila marcado como revisado. {self.review_panel.queue.summary()}")
        self._review_position = None

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
                **self._sample_metadata(idx),
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
        fresh = bool(self.fresh_var.get())

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
                "fresh": fresh,
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
        fresh: bool = False,
    ) -> None:
        try:
            self._set_status("Treinando modelo...")
            self._set_training_dialog_text("Treinando modelo...", "")
            run = train_model(
                csv_path=csv_path,
                samples_dir=samples_dir,
                model_path=model_path,
                epochs=epochs,
                batch_size=batch_size,
                lr=lr,
                progress_cb=self._on_training_progress,
                splits_path=DEFAULT_SPLITS_PATH if DEFAULT_SPLITS_PATH.exists() else None,
                fresh=fresh,
            )
            self.reload_model()
            # A epoca salva e a melhor, nao a ultima (S-27): mostrar a ultima faria o
            # usuario ler uma metrica que nao corresponde ao checkpoint no disco.
            melhor = run.history[run.best_epoch - 1] if run.history and run.best_epoch else {}
            resumo = self._format_train_metrics(melhor)
            if run.ece_after is not None:
                resumo += f" | T={run.temperature:.3f}"
            self._set_status("Treino concluido.")
            self._set_training_dialog_text("Treino concluido.", resumo)
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Treino concluido",
                    f"Epocas: {len(run.history)}\nMelhor epoca: {run.best_epoch}\n{resumo}",
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
