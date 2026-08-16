"""Interface desktop: montagem e roteamento de eventos (S-31).

Esta classe era 2.544 linhas e ~60 atributos, misturando layout, estado de OCR, tabuleiro
de estudo, orquestração de threads e persistência. O que sobrou aqui é o que só a janela
pode fazer: criar os painéis, ligar um ao outro e traduzir os widgets de configuração nos
parâmetros que o `OcrService` espera.

**Quem faz o quê agora:**

| responsabilidade | onde mora |
|---|---|
| detectar, prever, inferir a vez, gravar amostra | `service.py` |
| PDF: exibir, navegar, selecionar área, marcar diagramas | `ui/pdf_panel.py` |
| onde estão os diagramas da página e o que um clique neles significa | `ui/page_overlay.py` |
| o que a roda do mouse faz e para onde o zoom puxa | `ui/viewport.py` |
| editar o diagrama, legalidade, salvar, fila e dataset | `ui/result_panel.py` |
| tabuleiro de estudo, variantes e PGN | `ui/study_panel.py` |
| exportar o livro para PGN | `ui/export_controller.py` |
| treinar o modelo | `ui/training_dialog.py` |

A regra que decidiu cada corte: **o que dá para testar não fica aqui.** É a mesma da Fase 4,
aplicada agora ao que tinha sobrado.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import cv2
import numpy as np

from chess_diagram_ocr.config import (
    ACCEPT_MIN_CONFIDENCE,
    BUNDLE_ROOT,
    DEFAULT_DATASET_CSV,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_PDF_DIR,
    DEFAULT_READING_ORDER,
    DEFAULT_SAMPLES_DIR,
    PROJECT_ROOT,
    find_default_pdf_path,
)
from chess_diagram_ocr.dataset_browser import DatasetRow
from chess_diagram_ocr.detection import detect_diagrams_in_pdf_page
from chess_diagram_ocr.engine import EngineAnalyzer, find_engine
from chess_diagram_ocr.field_eval import load_field_set, upsert_page
from chess_diagram_ocr.gallery import load_annotations
from chess_diagram_ocr.labels import LabelStore, saved_diagrams_by_page
from chess_diagram_ocr.logging_setup import configure_logging, default_log_file
from chess_diagram_ocr.ocr_caption import caption_reader_from_settings
from chess_diagram_ocr.review_queue import DEFAULT_QUEUE_PATH
from chess_diagram_ocr.service import (
    OcrService,
    RecognitionOptions,
    RecognitionOrigin,
    RecognizedDiagram,
)
from chess_diagram_ocr.settings import (
    DEFAULT_SETTINGS_PATH,
    RemoteFenSettings,
    Settings,
    load_settings,
    save_settings,
)
from chess_diagram_ocr.ui import strings
from chess_diagram_ocr.ui.board_widget import PieceImages
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.dataset_panel import DatasetPanel
from chess_diagram_ocr.ui.export_controller import ExportController, ExportSettings
from chess_diagram_ocr.ui.field_draft import REGIMES, FieldDraft
from chess_diagram_ocr.ui.gallery_panel import GalleryPanel
from chess_diagram_ocr.ui.page_overlay import (
    BoxClick,
    OverlayParams,
    PageBoxes,
    PageBoxesCache,
    boxes_from_candidates,
    boxes_from_diagrams,
    choose_boxes,
    decide_box_click,
    mark_confirmed,
    mark_saved,
)
from chess_diagram_ocr.ui.page_results import PageOcrParams
from chess_diagram_ocr.ui.pdf_panel import PdfPanel
from chess_diagram_ocr.ui.result_panel import ResultPanel, read_board_image
from chess_diagram_ocr.ui.review_panel import ReviewPanel, ScanRequest
from chess_diagram_ocr.ui.shortcuts import bind_shortcuts
from chess_diagram_ocr.ui.state import AppState, load_state, save_state
from chess_diagram_ocr.ui.study_panel import StudyPanel
from chess_diagram_ocr.ui.theme import apply_theme
from chess_diagram_ocr.ui.tooltip import Tooltip
from chess_diagram_ocr.ui.training_dialog import TrainingController, TrainingRequest

# `PROJECT_ROOT` e a pasta gravavel -- o checkout, ou a pasta do `.exe` num bundle (S-55).
# `BUNDLE_ROOT` e onde ficam os recursos somente-leitura que viajam dentro do pacote. A
# distincao existe para que reinstalar nao apague o `labels.csv`, que e trabalho humano.
ROOT = PROJECT_ROOT
PIECE_IMAGE_DIR = BUNDLE_ROOT / "assets" / "piece_images"
APP_STATE_PATH = ROOT / "data" / "app_tkinter_state.json"
FIELD_SET_PATH = ROOT / "data" / "field_set.jsonl"
DEFAULT_SPLITS_PATH = ROOT / "data" / "splits.csv"

logger = logging.getLogger(__name__)


class ChessOcrTkApp:
    """Monta a janela e liga os painéis. Nenhuma regra de OCR mora aqui."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Chess Diagram OCR - Tkinter")
        self.root.geometry("1700x980")

        self.theme = apply_theme(root)
        """Tema em uso (S-53), ou `"ttk"` quando o `ttkbootstrap` não está instalado.

        Aplicado antes de qualquer widget: trocar tema depois de a árvore montada refaz o
        layout inteiro, e a diferença aparece como um piscar."""

        self.piece_images = PieceImages(PIECE_IMAGE_DIR)
        self.state = AppState()
        self.settings: Settings = load_settings()
        """Preferências do usuário (S-32). Por padrão nada sai da máquina."""

        # A configuracao vem antes do servico porque o OCR de legenda (S-43) entra por ele.
        # Construir o motor aqui, e nao dentro do servico, e a mesma separacao da S-32: quem
        # le a configuracao e a interface; o pipeline recebe pronto o que ela autorizou.
        self.service = OcrService(
            model_path=DEFAULT_MODEL_PATH,
            caption_reader=caption_reader_from_settings(self.settings.ocr),
        )

        self.analyzer = self._build_analyzer()
        """Motor de análise (S-33), ou `None`. Sem binário, a seção some da aba Análise."""

        self._is_running_ocr = False

        self.page_boxes = PageBoxesCache()
        """Onde estão os diagramas de cada página já visitada (S-68)."""

        self.saved_diagrams: dict[int, set[int]] = {}
        """Quais diagramas de cada página deste livro já têm amostra salva (S-71).

        Vem do `labels.csv` e não da memória: é o que faz a marcação verde valer entre
        execuções. Relido ao abrir o livro e a cada amostra gravada -- 3.313 linhas custam
        milissegundos, e um índice que mente sobre trabalho já feito custa refazê-lo."""

        self.confirmed_diagrams: dict[int, set[int]] = {}
        """Quais diagramas a base de partidas reconheceu (S-75).

        Mesma mecânica do `saved_diagrams` e outra fonte: as anotações da galeria, onde o
        `cvoff-games` grava. Um diz "eu já trabalhei isto", o outro "isto não precisa de mim"."""

        self._overlay_lock = threading.Lock()
        self._overlay_request: tuple[str, int, OverlayParams, Path, np.ndarray] | None = None
        self._overlay_worker_alive = False
        """Uma thread de detecção por vez, com o pedido mais recente esperando a vez.

        Não é uma fila: virar dez páginas em dois segundos não deve render dez detecções, das
        quais nove serão descartadas ao chegar. O pedido novo **sobrescreve** o que ainda não
        começou, que é a única coisa que o usuário ainda pode querer ver."""

        self._select_after_ocr: int | None = None
        """Diagrama a selecionar quando o OCR pedido por um clique terminar."""

        self.busy = BusyRegistry()
        """O que esta rodando agora (S-60). Fechar a janela consulta isto antes de matar
        oito threads daemon -- ate aqui `_on_close` nao perguntava nada, e um treino de ~9 min
        por epoca morria no `destroy` sem uma palavra."""

        self.model_path_var = tk.StringVar(value=str(DEFAULT_MODEL_PATH))
        self.dataset_csv_var = tk.StringVar(value=str(DEFAULT_DATASET_CSV))
        self.samples_dir_var = tk.StringVar(value=str(DEFAULT_SAMPLES_DIR))
        self.orientation_var = tk.StringVar(value=DEFAULT_ORIENTATION_MODE)
        self.dpi_var = tk.IntVar(value=220)
        self.max_boards_var = tk.IntVar(value=DEFAULT_MAX_BOARDS)
        self.epochs_var = tk.IntVar(value=8)
        self.batch_var = tk.IntVar(value=128)
        self.lr_var = tk.DoubleVar(value=0.001)
        self.fresh_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Pronto.")

        self.main_pane: tk.PanedWindow | None = None
        self.left_tabs: ttk.Notebook | None = None
        self.btn_train_model: ttk.Button | None = None
        self.pdf_panel: PdfPanel | None = None
        self.result_panel: ResultPanel | None = None
        self.study_panel: StudyPanel | None = None
        self.review_panel: ReviewPanel | None = None
        self.dataset_panel: DatasetPanel | None = None
        self.gallery_panel: GalleryPanel | None = None

        self.training = TrainingController(
            self.root,
            request=self._training_request,
            on_status=self._set_status,
            on_controls_enabled=self._set_train_controls_enabled,
            # Ao fim do treino o `.pt` em memória pode não ser mais o do disco. Invalidar
            # aqui espera o OCR em andamento, em vez de disputar com ele (S-31).
            on_finished=self.reload_model,
            busy=self.busy,
        )
        self.export = ExportController(
            self.root,
            # O mesmo servico do OCR: a exportacao passa a rodar sob o lock da S-31, e o
            # treino que termina no meio dela nao troca mais o `.pt` debaixo dela (S-57).
            service=self.service,
            busy=self.busy,
            settings=self._export_settings,
            on_status=self._set_status,
            on_controls_enabled=self._set_export_controls_enabled,
        )

        self._build_ui()
        self._bind_shortcuts()
        self._restore_state_or_default_pdf()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(180, self._set_initial_sashes)

    # ------------------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        self.main_pane = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=10, showhandle=True, handlesize=10
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
        tabs.add(cfg_tab, text="Configuração")
        self._build_config_tab(cfg_tab)

        self.result_panel = ResultPanel(
            tabs,
            service=self.service,
            piece_images=self.piece_images,
            paths=lambda: (Path(self.dataset_csv_var.get()), Path(self.samples_dir_var.get())),
            ocr_params=self._current_ocr_params,
            document_key=self._document_key,
            model_path=lambda: Path(self.model_path_var.get().strip()),
            on_status=self._set_status,
            on_ocr_local=self._ocr_local,
            max_boards=lambda: int(self.max_boards_var.get()),
            on_sync_study=self._sync_study,
            on_state_changed=self._save_app_state,
            on_focus_request=self._focus_result_tab,
            on_sample_saved=self._reload_dataset_panel,
            remote_fen=lambda: self.settings.remote_fen,
            local_reader=lambda: self.settings.local_reader,
            on_remote_consent=self._ask_remote_consent,
            on_selection_changed=self._on_result_selection,
            move_number_of=self._move_number_of,
            on_move_number=self._set_move_number,
        )
        tabs.add(self.result_panel, text="Resultado")

        self.study_panel = StudyPanel(
            tabs,
            piece_images=self.piece_images,
            # Vinculo de mao única: o estudo le a FEN do diagrama selecionado e nunca
            # escreve de volta. Um lance jogado na análise não e uma correção do OCR.
            current_fen=lambda: self.result_panel.fen_var.get() if self.result_panel else "",
            initial_dir=ROOT,
            analyzer=self.analyzer,
        )
        tabs.add(self.study_panel, text="Análise")

        self.review_panel = ReviewPanel(
            tabs,
            scan_request=self._current_scan_request,
            on_open=self._open_review_item,
            on_status=self._set_status,
            queue_path=DEFAULT_QUEUE_PATH,
            service=self.service,
        )
        tabs.add(self.review_panel, text="Revisão")
        self.result_panel.set_review_settler(self._settle_review_item)

        self.dataset_panel = DatasetPanel(
            tabs,
            paths=self._dataset_paths,
            on_edit=self.result_panel.open_dataset_row,
            on_recheck=self.recheck_dataset_row,
            on_status=self._set_status,
        )
        tabs.add(self.dataset_panel, text="Dataset")

        self.gallery_panel = GalleryPanel(
            tabs,
            service=self.service,
            pdf_path=self._pdf_path_or_none,
            model_path=lambda: Path(self.model_path_var.get().strip()),
            max_boards=lambda: int(self.max_boards_var.get()),
            on_status=self._set_status,
            on_page_request=self._gallery_page_request,
        )
        tabs.add(self.gallery_panel, text="Galeria")

        ttk.Label(self.left_frame, textvariable=self.status_var).pack(anchor="w", pady=(6, 0))

    def _build_config_tab(self, cfg_tab: ttk.Frame) -> None:
        self._entry_row(cfg_tab, "Modelo (.pt)", self.model_path_var)
        self._entry_row(cfg_tab, "CSV labels", self.dataset_csv_var)
        self._entry_row(cfg_tab, "Pasta samples", self.samples_dir_var)

        # Tri-estado no lugar do checkbox: "auto" decide por diagrama, o que resolve livro
        # com orientações misturadas -- o booleano valia para todos de uma vez (S-13).
        orient_row = ttk.Frame(cfg_tab)
        orient_row.pack(anchor="w", fill="x", padx=8, pady=4)
        ttk.Label(orient_row, text="Orientação do diagrama", width=24).pack(side="left")
        for valor, rotulo in strings.ORIENTATION_LABELS.items():
            ttk.Radiobutton(orient_row, text=rotulo, value=valor, variable=self.orientation_var).pack(
                side="left", padx=4
            )
        self._spin_row(cfg_tab, "DPI", self.dpi_var, 120, 320, 20)
        # Até 30: uma página de exercicios com grade 3x3 tem 9, e o teto antigo de 8 cortava
        # o nono em silencio. Quem filtra e o piso de score do detector, não este número.
        self._spin_row(cfg_tab, "Max diagramas", self.max_boards_var, 1, 30, 1)

        btns = ttk.Frame(cfg_tab)
        btns.pack(fill=tk.X, padx=8, pady=(4, 8))
        ttk.Button(btns, text="Recarregar modelo", command=self.reload_model).pack(side=tk.LEFT)

        train_box = ttk.LabelFrame(cfg_tab, text="Treino (salva em piece_classifier.pt)")
        train_box.pack(fill=tk.X, padx=8, pady=(4, 8))
        self._spin_row(train_box, "Épocas", self.epochs_var, 1, 200, 1)
        self._spin_row(train_box, "Batch size", self.batch_var, 16, 512, 16)
        self._entry_row(train_box, "Learning rate", self.lr_var)
        ttk.Checkbutton(
            train_box, text="Treinar do zero (ignora o checkpoint atual)", variable=self.fresh_var
        ).pack(anchor="w", padx=8)
        ttk.Label(
            train_box,
            text="Sem isso, o treino continua do checkpoint e só grava por cima se melhorar.",
            wraplength=320,
            foreground="#555555",
        ).pack(anchor="w", padx=8, pady=(0, 4))
        self.btn_train_model = ttk.Button(train_box, text="Treinar modelo", command=self.training.start)
        self.btn_train_model.pack(anchor="w", padx=8, pady=8)

    def _build_right_panel(self) -> None:
        self.pdf_panel = PdfPanel(
            self.right_frame,
            dpi=lambda: int(self.dpi_var.get()),
            initial_page_for=lambda caminho: self.state.page_for(caminho),
            on_status=self._set_status,
            on_ocr_best=self.ocr_best,
            on_ocr_all=self.ocr_all,
            on_region=self._ocr_region,
            on_export=lambda: self.export.start(self.pdf_source),
            on_cancel_export=self._cancel_export,
            on_pdf_opened=self._on_pdf_opened,
            on_before_page_change=self._remember_page_results,
            on_page_rendered=self._on_page_rendered,
            on_zoom_changed=lambda _valor: self._save_app_state(),
            initial_dir=ROOT,
            on_box_click=self._on_box_click,
            on_prefs_changed=self._save_app_state,
        )
        self.pdf_panel.pack(fill=tk.BOTH, expand=True)
        self._build_field_row(self.pdf_panel.field_row)

    def _build_field_row(self, parent: ttk.Widget) -> None:
        """Os controles do conjunto de campo (S-77), junto da página exibida.

        A ordem dos botões é a do gesto: confirmar o que está na tela é o caso comum, "sem
        diagrama" é o segundo mais comum -- e as páginas sem diagrama são obrigatórias, porque
        são as únicas que medem falso positivo (S-41).
        """
        ttk.Label(parent, text="Conjunto de campo").pack(side=tk.LEFT)
        self.field_regime_var = tk.StringVar(value=REGIMES[0])
        ttk.Combobox(
            parent, textvariable=self.field_regime_var, values=list(REGIMES), width=15, state="readonly"
        ).pack(side=tk.LEFT, padx=6)

        botao = ttk.Button(parent, text="Anotar página", command=self.annotate_field_page)
        botao.pack(side=tk.LEFT)
        Tooltip(botao).set_text(
            "Grava as caixas desta página como verdade de referência, revisada por você. "
            "Confira antes: é isto que mede o pipeline, e um erro aqui vira erro na métrica."
        )
        ttk.Button(parent, text="Sem diagrama", command=lambda: self.annotate_field_page(empty=True)).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(parent, text="Tirar o selecionado", command=self.field_drop_selected).pack(side=tk.LEFT)
        self.field_status_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.field_status_var).pack(side=tk.LEFT, padx=10)

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

    def _set_initial_sashes(self) -> None:
        try:
            if self.main_pane is not None:
                self.main_pane.sash_place(0, int(max(1, self.main_pane.winfo_width()) * 0.42), 0)
        except tk.TclError as exc:
            # Erro transitorio de geometria enquanto o primeiro layout se estabiliza.
            logger.debug("Não foi possível posicionar o divisor inicial: %s", exc)

    # ------------------------------------------------------------------------------ estado

    def _set_status(self, text: str) -> None:
        """Escreve na barra de status, de qualquer thread.

        Sem `update_idletasks()`: chamado de dentro de um callback de evento, ele reentra no
        loop de eventos do Tk e permite que outro callback rode no meio deste --
        reentrância que a S-31 manda remover. A variável é observada pelo widget, então o
        texto aparece no próximo ciclo ocioso de qualquer jeito.
        """
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(text)
        else:
            self.root.after(0, partial(self.status_var.set, text))

    def _build_analyzer(self) -> EngineAnalyzer | None:
        """Procura o motor. Não achar é o caso normal, e não é erro (S-33)."""
        caminho = find_engine(self.settings.engine.path or None)
        if caminho is None:
            logger.info("Nenhum motor de análise encontrado; a seção de avaliação fica oculta.")
            return None
        logger.info("Motor de análise disponível: %s", caminho)
        return EngineAnalyzer(
            caminho,
            movetime_ms=self.settings.engine.movetime_ms,
            threads=self.settings.engine.threads,
        )

    def _set_default_pdf_if_exists(self) -> None:
        default_pdf = find_default_pdf_path()
        if default_pdf is not None and default_pdf.exists():
            self.load_pdf(default_pdf)

    def _restore_state_or_default_pdf(self) -> None:
        """Restaura o estado gravado. Sem PDF utilizável, cai no primeiro PDF da pasta."""
        self.state = load_state(APP_STATE_PATH)

        if self.pdf_panel is not None:
            self.pdf_panel.set_zoom(self.state.pdf_zoom)
            self.pdf_panel.show_boxes_var.set(self.state.show_diagram_boxes)
            self.pdf_panel.flip_pages_var.set(self.state.wheel_flips_page)
        if self.result_panel is not None:
            self.result_panel.board_zoom_var.set(self.state.board_zoom)
            self.result_panel.heatmap_var.set(self.state.show_heatmap)
            self.result_panel.board.set_heatmap_enabled(self.state.show_heatmap)
            self.result_panel.update_zoom_label()

        last_pdf = self.state.last_pdf.strip()
        if not last_pdf:
            self._set_default_pdf_if_exists()
            return

        pdf_path = Path(last_pdf)
        if not pdf_path.exists():
            # Antes isto era um `return False` silencioso e o usuário só via o PDF errado
            # abrir, sem saber por que.
            logger.warning("Último PDF do estado não existe mais: %s", pdf_path)
            self._set_status(f"Último PDF não encontrado: {pdf_path}")
            self._set_default_pdf_if_exists()
            return

        self.load_pdf(pdf_path)
        painel = self.pdf_panel
        if painel is not None and painel.page_count > 0:
            pagina = max(0, min(painel.page_count - 1, self.state.last_page))
            if pagina != painel.page_index:
                painel.page_index_var.set(pagina)
                painel.page_loaded_for_index = None
                painel.render_current_page()

    def _save_app_state(self) -> None:
        try:
            if self.pdf_source is not None:
                self.state.remember_page(self.pdf_source, self.page_index)
            self.state.last_pdf = str(self.pdf_source) if self.pdf_source is not None else ""
            self.state.last_page = self.page_index
            if self.pdf_panel is not None:
                self.state.pdf_zoom = float(self.pdf_panel.zoom_var.get())
                self.state.show_diagram_boxes = bool(self.pdf_panel.show_boxes_var.get())
                self.state.wheel_flips_page = bool(self.pdf_panel.flip_pages_var.get())
            if self.result_panel is not None:
                self.state.board_zoom = float(self.result_panel.board_zoom_var.get())
                self.state.show_heatmap = bool(self.result_panel.heatmap_var.get())
            if self.review_panel is not None:
                self.state.review_queue_path = str(self.review_panel.queue_path)
        except tk.TclError as exc:
            logger.warning("Estado da aplicacao não pode ser montado: %s", exc)
            return
        save_state(APP_STATE_PATH, self.state)

    def _on_close(self) -> None:
        aviso = self.busy.close_warning()
        if aviso and not messagebox.askyesno("Operação em andamento", aviso, default=messagebox.NO):
            return
        if aviso:
            # Pedir o cancelamento antes de destruir da a quem sabe parar limpo a chance de
            # fazê-lo -- e o treino grava o checkpoint por epoca, entao parar entre elas nao
            # deixa `.pt` pela metade (S-57).
            self.busy.request_cancel()

        self._save_app_state()
        if self.analyzer is not None:
            # O motor e um processo, nao um widget: fechar a janela nao o encerra.
            self.analyzer.close()
        self.root.destroy()

    def _set_train_controls_enabled(self, enabled: bool) -> None:
        if self.btn_train_model is not None:
            self.btn_train_model.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _set_ocr_controls_enabled(self, enabled: bool) -> None:
        if self.result_panel is not None:
            self.result_panel.set_ocr_controls_enabled(enabled)
        if self.pdf_panel is not None:
            self.pdf_panel.set_ocr_controls_enabled(enabled)

    def _set_export_controls_enabled(self, enabled: bool) -> None:
        if self.pdf_panel is not None:
            self.pdf_panel.set_export_controls_enabled(enabled)

    def reload_model(self) -> None:
        """Descarta o modelo em memória. Espera o OCR em andamento, em vez de disputar."""
        self.service.invalidate_model(Path(self.model_path_var.get().strip()))
        self._set_status("Modelo recarregado.")

    # ---------------------------------------------------------------- parâmetros da tela

    def _recognition_options(self, max_boards: int, **overrides: Any) -> RecognitionOptions:
        return RecognitionOptions(
            model_path=Path(self.model_path_var.get().strip()),
            orientation=str(self.orientation_var.get()),
            max_boards=max_boards,
            dpi=int(self.dpi_var.get()),
            **overrides,
        )

    def _current_ocr_params(self) -> PageOcrParams:
        return PageOcrParams(
            dpi=int(self.dpi_var.get()),
            max_boards=int(self.max_boards_var.get()),
            orientation=str(self.orientation_var.get()),
            model_path=self.model_path_var.get().strip(),
        )

    def _export_settings(self) -> ExportSettings:
        return ExportSettings(
            model_path=Path(self.model_path_var.get().strip()),
            dpi=int(self.dpi_var.get()),
            max_boards_per_page=int(self.max_boards_var.get()),
            orientation=str(self.orientation_var.get()),
        )

    def _training_request(self) -> TrainingRequest:
        return TrainingRequest(
            csv_path=Path(self.dataset_csv_var.get()),
            samples_dir=Path(self.samples_dir_var.get()),
            model_path=Path(self.model_path_var.get()),
            epochs=int(self.epochs_var.get()),
            batch_size=int(self.batch_var.get()),
            lr=float(self.lr_var.get()),
            fresh=bool(self.fresh_var.get()),
            splits_path=DEFAULT_SPLITS_PATH if DEFAULT_SPLITS_PATH.exists() else None,
        )

    def _current_scan_request(self) -> ScanRequest | None:
        """Parâmetros da varredura da fila de revisão, como a janela os tem agora."""
        if self.pdf_source is None:
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
        return (Path(self.dataset_csv_var.get()), Path(self.samples_dir_var.get()), DEFAULT_SPLITS_PATH)

    # ------------------------------------------------------------------ ligações do PDF

    @property
    def pdf_source(self) -> Path | None:
        return self.pdf_panel.source if self.pdf_panel is not None else None

    @property
    def page_index(self) -> int:
        return self.pdf_panel.page_index if self.pdf_panel is not None else 0

    def _document_key(self) -> str:
        return str(self.pdf_source) if self.pdf_source is not None else ""

    def load_pdf(self, pdf_path: Path) -> None:
        if self.pdf_panel is not None:
            self.pdf_panel.load_pdf(pdf_path)

    def _on_pdf_opened(self, pdf_path: Path) -> None:
        self._remember_page_results()
        # As caixas são de um arquivo que pode ter mudado no disco desde a última visita. A
        # chave já inclui o documento, então isto não é correção de bug: é não guardar
        # afirmação sobre um PDF que ninguém mais está olhando.
        self.page_boxes.clear()
        self._reload_saved_diagrams(pdf_path)
        if self.gallery_panel is not None:
            # Sem isto a galeria só conhecia o livro depois de uma varredura -- e o número do
            # lance digitado na aba Resultado (S-71) seria gravado num modelo sem `pdf_path`,
            # que descarta em silêncio.
            self.gallery_panel.load_pdf(pdf_path, request_page=False)
        if self.result_panel is not None:
            self.result_panel.discard_document_results(str(pdf_path))

    def _on_page_rendered(self, page_index: int) -> None:
        """A página apareceu: traz de volta o que já foi reconhecido nela, se houver.

        Depois do render, e não antes: restaurar o editor para uma página que ainda não está
        na tela é exatamente o sintoma que a Fase 5 corrigiu -- o seletor apontando para
        diagramas que não são os da página exibida.
        """
        self._save_app_state()
        if self.result_panel is not None:
            self.result_panel.restore_results_for_page(page_index)
        # Depois de restaurar: se esta página já foi lida, as caixas saem do reconhecimento --
        # que sabe o mesmo sobre *onde* e mais sobre *o que* -- e o detector não precisa rodar.
        self._refresh_overlay(page_index)
        self._refresh_field_status()
        if self.gallery_panel is not None:
            # A galeria acompanha a pagina, e ela propria ignora o aviso quando foi ela quem
            # pediu a virada -- senao os dois se chamariam em circulo (S-67).
            self.gallery_panel.sync_to_page(page_index)

    def _pdf_path_or_none(self) -> Path | None:
        return self.pdf_source

    # O número do lance é anotação de exportação, e quem a guarda é a aba Galeria (S-67). A
    # aba Resultado passou a editá-lo na S-71 e pergunta por aqui: um dono só para o arquivo
    # do livro, duas telas que o mostram.

    def _move_number_of(self, page_index: int, diagram_index: int) -> int | None:
        if self.gallery_panel is None:
            return None
        return self.gallery_panel.move_number_at(page_index, diagram_index)

    def _set_move_number(self, page_index: int, diagram_index: int, value: int | None) -> None:
        if self.gallery_panel is not None:
            self.gallery_panel.set_move_number(page_index, diagram_index, value)

    def _gallery_page_request(self, page_index: int) -> None:
        """A galeria mudou de diagrama; o visualizador vai para a página dele."""
        if self.pdf_panel is not None:
            self.pdf_panel.go_to_page(page_index)

    def _remember_page_results(self) -> None:
        if self.result_panel is not None:
            self.result_panel.remember_page_results()

    def _cancel_export(self) -> None:
        self.export.cancel()
        if self.pdf_panel is not None:
            self.pdf_panel.disable_cancel_button()

    # ------------------------------------------------- diagramas marcados na página (S-68)
    # Ninguém pediu esta detecção -- o usuário só virou a página --, e é isso que decide a
    # forma: roda em thread, a janela nunca espera por ela, falhar não abre caixa de erro, e o
    # resultado é conferido contra a página que estiver na tela quando ele chegar.

    def _overlay_params(self) -> OverlayParams:
        return OverlayParams(dpi=int(self.dpi_var.get()), max_boards=int(self.max_boards_var.get()))

    def _reload_saved_diagrams(self, pdf_path: Path | None = None) -> None:
        """Relê do `labels.csv` o que já foi salvo deste livro (S-71).

        Recebe o caminho porque quem abre o PDF avisa **antes** de o painel adotá-lo -- é a
        janela de tempo em que o editor ainda tem o resultado do livro anterior para guardar.

        Falhar aqui não impede nada: sem o índice, as caixas ficam sem o verde e o resto do
        visualizador segue igual. Um CSV ilegível é assunto da aba Dataset, não do visualizador.
        """
        alvo = pdf_path if pdf_path is not None else self.pdf_source
        if alvo is None:
            self.saved_diagrams = {}
            self.confirmed_diagrams = {}
            return
        try:
            loja = LabelStore(Path(self.dataset_csv_var.get()))
            self.saved_diagrams = saved_diagrams_by_page(loja.read(), alvo.name)
        except Exception:
            logger.exception("Não foi possível ler o que já está salvo de %s.", alvo.name)
            self.saved_diagrams = {}
        self.confirmed_diagrams = self._read_confirmed(alvo)

    def _read_confirmed(self, pdf_path: Path) -> dict[int, set[int]]:
        """O que a base de partidas já confirmou neste livro, por página (S-75).

        Sai das anotações da galeria, que é onde o `cvoff-games` grava -- e não de um arquivo
        próprio do visualizador, pela razão de sempre: dois lugares para a mesma verdade só têm
        como divergir. Falhar aqui não impede nada; as caixas ficam sem o violeta.
        """
        confirmados: dict[int, set[int]] = {}
        try:
            anotacoes = load_annotations(pdf_path)
        except Exception:
            logger.exception("Não foi possível ler as confirmações de %s.", pdf_path.name)
            return {}
        for (pagina, diagrama), anotacao in anotacoes.entries.items():
            if anotacao.confirmed_from:
                confirmados.setdefault(pagina, set()).add(diagrama)
        return confirmados

    def _editor_shows_page(self, page_index: int) -> bool:
        """Se o que está no editor é, ele mesmo, o reconhecimento desta página."""
        if self.result_panel is None:
            return False
        return self.result_panel.page_key == (self._document_key(), page_index)

    def _page_items(self, page_index: int) -> list[RecognizedDiagram]:
        """Os diagramas já lidos desta página: os do editor, se forem dela, ou os do cache."""
        if self.result_panel is None:
            return []
        if self._editor_shows_page(page_index):
            return self.result_panel.items
        guardado = self.result_panel.page_results.get(
            self._document_key(), page_index, self._current_ocr_params()
        )
        return list(guardado.items) if guardado is not None else []

    def _refresh_overlay(self, page_index: int) -> None:
        """Põe na tela as caixas desta página, e manda detectar quando ainda não se sabe."""
        painel = self.pdf_panel
        if painel is None or painel.source is None or painel.page_rgb is None:
            return

        params = self._overlay_params()
        salvos = self.saved_diagrams.get(page_index, set())
        detectadas = self.page_boxes.get(self._document_key(), page_index, params)
        escolhidas = mark_confirmed(
            mark_saved(
                choose_boxes(
                    recognized=boxes_from_diagrams(self._page_items(page_index)),
                    detected=detectadas.boxes if detectadas is not None else (),
                ),
                salvos,
            ),
            self.confirmed_diagrams.get(page_index, set()),
        )
        if escolhidas:
            painel.set_diagram_boxes(PageBoxes(page_index, params, escolhidas))
            self._sync_selected_box()
            return
        if detectadas is not None:
            # Página de prosa já visitada: sabe-se que não há diagrama, e dizê-lo é melhor que
            # mandar o detector percorrê-la de novo a cada volta.
            painel.set_diagram_boxes(detectadas)
            return

        self._request_overlay(page_index, params)

    def _sync_selected_box(self) -> None:
        """Destaca no visualizador o diagrama que está aberto no editor.

        Só quando as caixas na tela são as do reconhecimento **desta** página. Com as caixas do
        detector, o índice do editor não fala da mesma lista -- e um destaque no diagrama errado
        é a resposta errada para a única pergunta que ele existe para responder.
        """
        painel = self.pdf_panel
        if painel is None:
            return
        if painel.boxes is None or not painel.boxes.recognized:
            painel.select_box(None)
            return
        if self.result_panel is None or not self._editor_shows_page(painel.page_index):
            painel.select_box(None)
            return
        painel.select_box(self.result_panel.selected_index if self.result_panel.items else None)

    def _on_result_selection(self, _index: int | None) -> None:
        """O editor trocou de diagrama; o retângulo destacado acompanha."""
        self._sync_selected_box()

    def _request_overlay(self, page_index: int, params: OverlayParams) -> None:
        painel = self.pdf_panel
        if painel is None or painel.source is None or painel.page_rgb is None:
            return

        pedido = (
            self._document_key(),
            page_index,
            params,
            painel.source,
            # Cópia pelo mesmo motivo do OCR: a thread lê esta imagem enquanto a janela pode
            # estar rasterizando outra página por cima da referência.
            np.asarray(painel.page_rgb).copy(),
        )
        with self._overlay_lock:
            self._overlay_request = pedido
            if self._overlay_worker_alive:
                return
            self._overlay_worker_alive = True
        threading.Thread(target=self._overlay_worker, name="marcar-diagramas", daemon=True).start()

    def _overlay_worker(self) -> None:
        while True:
            with self._overlay_lock:
                pedido = self._overlay_request
                self._overlay_request = None
                if pedido is None:
                    self._overlay_worker_alive = False
                    return

            documento, page_index, params, source, page_rgb = pedido
            try:
                candidatos = detect_diagrams_in_pdf_page(
                    source, page_index, page_rgb, max_boards=params.max_boards
                )
            except Exception:
                # Sem caixa de diálogo: a página continua legível no visualizador, e o usuário
                # não pediu nada. O log é onde isto pertence.
                logger.exception("Falha ao procurar diagramas na página %d de %s.", page_index, documento)
                continue

            caixas = PageBoxes(page_index, params, boxes_from_candidates(candidatos))
            self.root.after(0, partial(self._apply_overlay, documento, caixas))

    def _apply_overlay(self, documento: str, caixas: PageBoxes) -> None:
        self.page_boxes.put(documento, caixas)
        painel = self.pdf_panel
        if painel is None or self._document_key() != documento:
            return
        if not painel.set_diagram_boxes(caixas):
            return

        self._sync_selected_box()
        if len(caixas):
            self._set_status(
                f"Página {caixas.page_index}: {len(caixas)} diagrama(s) marcado(s). "
                "Clique num deles para lê-lo."
            )

    def _on_box_click(self, index: int) -> None:
        """Clique num diagrama marcado: abre-o no editor, lendo a página se for preciso."""
        painel = self.pdf_panel
        if painel is None or self.result_panel is None:
            return

        pagina = painel.page_index
        if not self._editor_shows_page(pagina):
            # O clique é um pedido explícito de abrir aquele diagrama. Trazer de volta o
            # resultado guardado é o caminho barato, e o descarte que a `PageSwitch.KEEP` evita
            # é o **implícito** -- o da virada de página, que ninguém pediu.
            self.result_panel.restore_results_for_page(pagina)

        lidos = len(self.result_panel.items) if self._editor_shows_page(pagina) else 0
        if painel.boxes is not None and not painel.boxes.recognized:
            # As caixas na tela são do detector: o índice clicado não fala da mesma lista que o
            # editor. Ver `choose_boxes` -- é o caso do "OCR melhor diagrama".
            lidos = 0

        if decide_box_click(recognized_count=lidos, index=index) is BoxClick.SELECT:
            self.result_panel.select_diagram(index)
            self._focus_result_tab()
            return

        if self._is_running_ocr:
            self._set_status("OCR em andamento. Aguarde a conclusão.")
            return
        self._select_after_ocr = index
        self._set_status(f"Lendo a página para abrir o diagrama {index + 1}...")
        self._run_ocr_from_current_page(max_boards=int(self.max_boards_var.get()))

    # --------------------------------------------------------------------------------- OCR
    # A janela decide *o que* reconhecer, porque e ela que tem os widgets; o servico decide
    # *como*. `run` já vem montado aqui, fechado sobre copias das imagens e sobre as opções
    # lidas dos widgets -- ler `tk.Variable` de outra thread e acesso que o Tcl não promete.

    def ocr_best(self) -> None:
        self._run_ocr_from_current_page(max_boards=1)

    def ocr_all(self) -> None:
        self._run_ocr_from_current_page(max_boards=int(self.max_boards_var.get()))

    def _run_ocr_from_current_page(self, max_boards: int) -> None:
        painel = self.pdf_panel
        if painel is None or painel.source is None:
            messagebox.showwarning("Aviso", "Abra um PDF primeiro.")
            return
        if not painel.render_current_page() or painel.page_rgb is None:
            return

        page_index = painel.page_index
        page_rgb = np.asarray(painel.page_rgb).copy()
        options = self._recognition_options(max_boards)
        source = painel.source
        # `recognize_page` e o caminho do detector hibrido (S-12), o mesmo que a exportação
        # usa. Deixar a GUI noutro detector faria a tela e o PGN recortarem diagramas
        # diferentes -- o mesmo desencontro que a S-14 corrigiu na numeração.
        self._start_ocr(
            lambda: self.service.recognize_page(source, page_index, page_rgb, options=options),
            origin=RecognitionOrigin.for_page(painel.name, page_index),
        )

    # ------------------------------------------------------- conjunto de campo (S-77)

    def _field_draft(self) -> FieldDraft:
        """A anotação desta página: a que já existe no arquivo, ou o que está na tela.

        Retomar a existente é o que permite corrigir sem recomeçar -- confirma-se rápido,
        acha-se um diagrama que faltou, e volta-se a ela.
        """
        nome = self.pdf_source.name if self.pdf_source else ""
        gravadas = {(pagina.pdf, pagina.page): pagina for pagina in load_field_set(FIELD_SET_PATH)}
        existente = gravadas.get((nome, self.page_index))
        if existente is not None:
            return FieldDraft.from_page(existente)

        rascunho = FieldDraft(pdf_name=nome, page=self.page_index, regime=self.field_regime_var.get())
        caixas = self.pdf_panel.boxes if self.pdf_panel is not None else None
        conferidos = self._page_confirmed_placements(self.page_index)
        rascunho.reset_from(
            [
                (box.bbox_pdf, *conferidos.get(indice, ("", False)))
                for indice, box in enumerate(caixas.boxes if caixas is not None else ())
            ]
        )
        return rascunho

    def _page_confirmed_placements(self, page_index: int) -> dict[int, tuple[str, bool]]:
        """Por diagrama da página: a colocação **corrigida** e se alguém a conferiu (S-95).

        **Vem de `fen_edits`, e não de `items[i].placement`.** As duas listas são paralelas de
        propósito -- `ui/editor_model.py:19` diz que fundi-las perderia a leitura original --, e
        a anotação do conjunto de campo estava lendo o lado errado: gravava o que o modelo leu
        como verdade **sobre** o modelo. Corrigir o tabuleiro e anotar a página descartava a
        correção e gravava o erro.

        `edited_by_hand` é o que separa lido de conferido, e é o mesmo sinal que o cache de
        página já usa para decidir o que não pode ser descartado em silêncio.
        """
        painel = self.result_panel
        if painel is None:
            return {}

        if self._editor_shows_page(page_index):
            itens, edicoes = painel.items, painel.fen_edits
        else:
            guardado = painel.page_results.get(self._document_key(), page_index, self._current_ocr_params())
            if guardado is None:
                return {}
            itens, edicoes = list(guardado.items), list(guardado.fen_edits)

        return {
            item.index: (
                edicoes[posicao] if posicao < len(edicoes) else item.placement,
                bool(item.edited_by_hand),
            )
            for posicao, item in enumerate(itens)
        }

    def annotate_field_page(self, *, empty: bool = False) -> None:
        """Grava a página no conjunto de campo, revisada.

        **É o gesto que desbloqueia as Fases 7 e 11.** Com 38 diagramas, a taxa de exportação
        não distingue dois modelos (7.7), e quatro itens de spec foram julgados por ela. O que
        falta não é código: é este clique, página a página.
        """
        if self.pdf_source is None:
            messagebox.showinfo("Conjunto de campo", "Abra um PDF antes de anotar a página.")
            return

        rascunho = FieldDraft(pdf_name=self.pdf_source.name, page=self.page_index) if empty else self._field_draft()
        rascunho.regime = "sem-diagrama" if empty else (self.field_regime_var.get() or rascunho.regime)
        total = upsert_page(FIELD_SET_PATH, rascunho.to_page())
        self.field_status_var.set(f"{rascunho.describe()} · {total} página(s) no conjunto")
        self._set_status(
            f"Página {self.page_index + 1} anotada no conjunto de campo: {rascunho.describe()}. "
            f"O conjunto tem {total} página(s) revisada(s)."
        )

    def field_drop_selected(self) -> None:
        """Tira da anotação o diagrama selecionado -- o falso positivo que o detector achou."""
        if self.pdf_source is None or self.result_panel is None:
            return
        caixas = self.pdf_panel.boxes if self.pdf_panel is not None else None
        if caixas is None or not len(caixas):
            self._set_status("Nenhuma caixa nesta página para tirar.")
            return
        selecionado = self.result_panel.selected_index
        if not 0 <= selecionado < len(caixas.boxes):
            self._set_status("Selecione o diagrama na página antes de tirá-lo da anotação.")
            return

        rascunho = self._field_draft()
        indice = rascunho.index_at(caixas.boxes[selecionado].bbox_pdf)
        if indice is None or not rascunho.remove(indice):
            self._set_status("Esse diagrama não está na anotação desta página.")
            return
        total = upsert_page(FIELD_SET_PATH, rascunho.to_page())
        self.field_status_var.set(f"{rascunho.describe()} · {total} página(s) no conjunto")
        self._set_status(f"Diagrama tirado da anotação. Ficaram {rascunho.describe()}.")

    def _refresh_field_status(self) -> None:
        """Diz, ao virar a página, se ela já está anotada. Sem isso não há como saber."""
        if self.pdf_source is None:
            self.field_status_var.set("")
            return
        gravadas = {(pagina.pdf, pagina.page): pagina for pagina in load_field_set(FIELD_SET_PATH)}
        pagina = gravadas.get((self.pdf_source.name, self.page_index))
        if pagina is None:
            self.field_status_var.set("página não anotada")
            return
        self.field_status_var.set(f"anotada: {FieldDraft.from_page(pagina).describe()}")

    def _ocr_region(self, page_rgb: np.ndarray, region: tuple[int, int, int, int]) -> None:
        options = self._recognition_options(int(self.max_boards_var.get()))
        self._start_ocr(
            lambda: self.service.recognize_region(page_rgb, region, options=options),
            origin=RecognitionOrigin.for_crop(
                self.pdf_panel.name if self.pdf_panel else "", self.page_index, region
            ),
        )

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
            messagebox.showerror("Erro", "Não foi possível abrir a imagem.")
            return
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        options = self._recognition_options(max_boards, refine_detected_boards=True)
        self._start_ocr(
            lambda: self.service.recognize_image(image_rgb, options=options),
            origin=RecognitionOrigin.for_image(Path(filename).name),
        )

    def _start_ocr(self, run: Callable[[], list[RecognizedDiagram]], *, origin: RecognitionOrigin) -> None:
        if self._is_running_ocr:
            self._set_status("OCR em andamento. Aguarde a conclusão.")
            return

        self._is_running_ocr = True
        self._set_ocr_controls_enabled(False)
        self._set_status("Preparando OCR...")
        threading.Thread(target=self._ocr_worker, kwargs={"run": run, "origin": origin}, daemon=True).start()

    def _ocr_worker(self, *, run: Callable[[], list[RecognizedDiagram]], origin: RecognitionOrigin) -> None:
        try:
            self._set_status("Detectando diagramas...")
            diagrams = run()
            self.root.after(0, partial(self._show_results, diagrams, origin))
        except Exception as exc:
            self.root.after(0, partial(self._on_ocr_error, exc))
        finally:
            self.root.after(0, self._finish_ocr_ui)

    def _show_results(self, items: list[RecognizedDiagram], origin: RecognitionOrigin) -> None:
        if self.result_panel is not None:
            self.result_panel.show_ocr_results(items, origin)
            if self._select_after_ocr is not None and origin.is_whole_page:
                # A página foi lida porque alguém clicou num diagrama dela: abrir o primeiro
                # seria responder outra pergunta.
                self.result_panel.select_diagram(self._select_after_ocr)
        self._refresh_overlay(self.page_index)

    def _on_ocr_error(self, exc: Exception) -> None:
        if "Nenhum tabuleiro foi detectado" in str(exc) and self.result_panel is not None:
            self.result_panel.clear()
        self._set_status("Falha no OCR.")
        messagebox.showerror("Erro", f"Falha no OCR:\n{exc}")

    def _finish_ocr_ui(self) -> None:
        self._is_running_ocr = False
        # Limpo aqui, e não em `_show_results`: o pedido morre também quando o OCR falha, e
        # este é o único ponto por onde os dois caminhos passam.
        self._select_after_ocr = None
        self._set_ocr_controls_enabled(True)

    # ------------------------------------------------------------- ligações entre painéis

    def _focus_result_tab(self) -> None:
        if self.left_tabs is None or self.result_panel is None:
            return
        try:
            self.left_tabs.select(self.result_panel)
        except tk.TclError as exc:
            logger.debug("Não foi possível focar a aba de resultados: %s", exc)

    def _sync_study(self) -> None:
        if self.study_panel is not None:
            self.study_panel.sync_with_ocr()

    def _ask_remote_consent(self, configuracao: RemoteFenSettings) -> bool:
        """Aviso antes do primeiro envio, com "não perguntar novamente" (S-32).

        Três respostas, não duas: "Sim" envia uma vez, "Não" cancela, e a caixa marcada
        grava o consentimento para aquele endpoint. Quem só quer experimentar uma vez não
        deveria precisar aceitar para sempre.
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("Correção remota")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        resposta = {"enviar": False}
        nao_perguntar = tk.BooleanVar(value=False)

        wrap = ttk.Frame(dlg, padding=14)
        wrap.pack(fill=tk.BOTH, expand=True)
        ttk.Label(wrap, text=configuracao.consent_message(), wraplength=460, justify=tk.LEFT).pack(anchor="w")
        ttk.Checkbutton(wrap, text="Não perguntar novamente para este endereco", variable=nao_perguntar).pack(
            anchor="w", pady=(10, 0)
        )

        linha = ttk.Frame(wrap)
        linha.pack(fill=tk.X, pady=(12, 0))

        def _responder(enviar: bool) -> None:
            resposta["enviar"] = enviar
            dlg.destroy()

        ttk.Button(linha, text="Enviar", command=partial(_responder, True)).pack(side=tk.LEFT)
        ttk.Button(linha, text="Cancelar", command=partial(_responder, False)).pack(side=tk.LEFT, padx=8)
        self.root.wait_window(dlg)

        if resposta["enviar"] and nao_perguntar.get():
            # `replace` e nao `Settings(...)`: construir um Settings novo aqui devolvia
            # `engine` e `ocr` aos padroes, e a linha seguinte gravava isso por cima do
            # arquivo -- marcar "nao perguntar novamente" apagava o caminho do motor UCI e a
            # configuracao de OCR de quem os tinha declarado.
            self.settings = replace(self.settings, remote_fen=replace(configuracao, acknowledged=True))
            save_settings(DEFAULT_SETTINGS_PATH, self.settings)
        return bool(resposta["enviar"])

    def _reload_dataset_panel(self) -> None:
        """Uma amostra foi gravada: a aba Dataset relê, e o visualizador repinta de verde."""
        if self.dataset_panel is not None:
            self.dataset_panel.reload()
        self._reload_saved_diagrams()
        self._refresh_overlay(self.page_index)

    def _open_review_item(self, item: Any, position: int) -> None:
        if self.result_panel is not None:
            self.result_panel.open_review_item(item, position)

    def _settle_review_item(self, position: int, fen: str, side: str) -> None:
        """Fecha na fila o item que acabou de ser corrigido e salvo (S-22)."""
        if self.review_panel is None:
            return
        self.review_panel.apply_correction(position, fen, side)
        self._set_status(f"Item da fila marcado como revisado. {self.review_panel.queue.summary()}")

    def recheck_dataset_row(self, row: DatasetRow) -> str:
        """Compara o que o modelo lê na amostra com o rótulo gravado (S-23)."""
        samples_dir = Path(self.samples_dir_var.get())
        board_rgb = read_board_image(str(row.image_path(samples_dir)))
        if board_rgb is None:
            raise FileNotFoundError(f"Imagem não encontrada: {row.image_path(samples_dir)}")
        return self.service.recheck_label(board_rgb, row.placement).describe(row.filename)

    # ----------------------------------------------------------------------------- atalhos

    def _bind_shortcuts(self) -> None:
        """Atalhos do ciclo corrigir → salvar → próximo (S-20)."""
        bind_shortcuts(
            self.root,
            {
                "<Left>": self._on_result(lambda p: p.prev_diagram()),
                "<Right>": self._on_result(lambda p: p.next_diagram()),
                "<Control-s>": self._on_result(lambda p: p.save_current()),
                "<Control-S>": self._on_result(lambda p: p.save_all()),
                "<Control-r>": self.ocr_all,
                "<Delete>": self._on_result(lambda p: p.delete_selected_square()),
                "<Control-n>": self._open_next_review_item,
                # Página do PDF, e não diagrama: as setas já são do editor (S-20), e virar a
                # página é a outra navegação que a leitura pede o tempo todo (S-70).
                "<Prior>": self._on_pdf(lambda p: p.prev_page()),
                "<Next>": self._on_pdf(lambda p: p.next_page()),
                "<Control-0>": self._on_pdf(lambda p: p.fit_width()),
            },
        )

    def _on_result(self, action: Callable[[ResultPanel], None]) -> Callable[[], None]:
        def _run() -> None:
            if self.result_panel is not None:
                action(self.result_panel)

        return _run

    def _on_pdf(self, action: Callable[[PdfPanel], None]) -> Callable[[], None]:
        def _run() -> None:
            if self.pdf_panel is not None:
                action(self.pdf_panel)

        return _run

    def _open_next_review_item(self) -> None:
        if self.review_panel is not None:
            self.review_panel.open_next_pending()


def selftest(pdf: Path | None = None, page_index: int = 0) -> int:
    """Abre um PDF e reconhece uma página, sem janela. `0` se o essencial funciona.

    Existe por causa do bundle da S-55. Um `.exe` sem console não tem como dizer "aqui
    funciona": se ele abrir e o torch estiver faltando, o sintoma é uma janela que some. Um
    auto-teste que grava no log responde à única pergunta que interessa numa máquina limpa
    -- *esta instalação lê um diagrama?* -- em vez de deixar o usuário descobrir isso ao
    perder uma correção.

    Roda igualmente num checkout, e é por isso que ele mora aqui e não no `packaging/`.
    """
    caminho = pdf or find_default_pdf_path()
    if caminho is None:
        logger.error(
            "Auto-teste sem PDF: ponha um arquivo em %s (ao lado do executável) e rode de novo.",
            DEFAULT_PDF_DIR,
        )
        return 2

    modelo = Path(DEFAULT_MODEL_PATH)
    if not modelo.exists():
        logger.error("Auto-teste sem checkpoint em %s: o programa abre, mas não lê nada.", modelo)
        return 3

    logger.info("Auto-teste: %s, página %d.", caminho.name, page_index)
    servico = OcrService(model_path=modelo)
    try:
        itens = servico.recognize_page(
            caminho,
            page_index,
            options=RecognitionOptions(max_boards=DEFAULT_MAX_BOARDS, orientation=DEFAULT_ORIENTATION_MODE),
        )
    except Exception:
        logger.exception("Auto-teste falhou ao reconhecer a página.")
        return 1

    for indice, item in enumerate(itens, start=1):
        logger.info(
            "  diagrama %d: %s | conf min %.3f | %s",
            indice,
            item.placement,
            item.min_confidence,
            "legal" if item.is_legal else "ilegal",
        )
    logger.info("Auto-teste concluído: %d diagrama(s) reconhecido(s).", len(itens))

    # O bundle da S-55 promete leitor **e** treinador, e ler nao prova treinar: o caminho de
    # treino usa `torchvision.transforms.v2`, que nada importa estaticamente e que um bundle
    # incompleto derruba so quando o usuario clica "Treinar modelo" -- depois de ele ter
    # corrigido dezenas de diagramas. Montar a pipeline de aumento custa milissegundos e
    # responde a pergunta agora.
    try:
        from chess_diagram_ocr.training import build_train_transform, train_model  # noqa: F401

        build_train_transform()
    except Exception:
        logger.exception("Auto-teste: a leitura funciona, mas o caminho de TREINO não montou.")
        return 4
    logger.info("Auto-teste: o caminho de treino também montou (leitor + treinador).")

    # Zero diagrama nao e falha: ha paginas de prosa. O que se testa aqui e o caminho
    # inteiro -- render, deteccao, torch, decodificacao -- ter rodado sem estourar.
    return 0


def main() -> None:
    # Desde a S-92 a janela cria processos (a busca por posição na Galeria). Num bundle
    # congelado, `spawn` reexecuta o próprio executável para criar cada filho -- e sem isto
    # cada filho abriria outra janela do aplicativo em vez de varrer um pedaço da base. Fora
    # do bundle é uma chamada sem efeito. É a guarda que o `cvoff-games` já tinha (S-26/S-55).
    mp.freeze_support()

    parser = argparse.ArgumentParser(description="Interface desktop do ChessVisionOFF.")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="reconhece uma página e sai, sem abrir a janela. Para conferir uma instalação nova (S-55).",
    )
    parser.add_argument("--pdf", type=Path, default=None, help="PDF do auto-teste; sem isto, o primeiro de PDF/.")
    parser.add_argument("--page", type=int, default=0, help="página do auto-teste (base 0).")
    args = parser.parse_args()

    configure_logging(log_file=default_log_file())
    if args.selftest:
        raise SystemExit(selftest(args.pdf, args.page))

    logger.info("Iniciando interface desktop.")
    root = tk.Tk()
    ChessOcrTkApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
