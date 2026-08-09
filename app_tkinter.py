"""Interface desktop: montagem e roteamento de eventos (S-31).

Esta classe era 2.544 linhas e ~60 atributos, misturando layout, estado de OCR, tabuleiro
de estudo, orquestração de threads e persistência. O que sobrou aqui é o que só a janela
pode fazer: criar os painéis, ligar um ao outro e traduzir os widgets de configuração nos
parâmetros que o `OcrService` espera.

**Quem faz o quê agora:**

| responsabilidade | onde mora |
|---|---|
| detectar, prever, inferir a vez, gravar amostra | `service.py` |
| PDF: exibir, navegar, selecionar área, modo leitura | `ui/pdf_panel.py` |
| editar o diagrama, legalidade, salvar, fila e dataset | `ui/result_panel.py` |
| tabuleiro de estudo, variantes e PGN | `ui/study_panel.py` |
| exportar o livro para PGN | `ui/export_controller.py` |
| treinar o modelo | `ui/training_dialog.py` |

A regra que decidiu cada corte: **o que dá para testar não fica aqui.** É a mesma da Fase 4,
aplicada agora ao que tinha sobrado.
"""

from __future__ import annotations

import logging
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
    DEFAULT_DATASET_CSV,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_READING_ORDER,
    DEFAULT_SAMPLES_DIR,
    find_default_pdf_path,
)
from chess_diagram_ocr.dataset_browser import DatasetRow
from chess_diagram_ocr.engine import EngineAnalyzer, find_engine
from chess_diagram_ocr.logging_setup import configure_logging, default_log_file
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
from chess_diagram_ocr.ui.page_results import PageOcrParams
from chess_diagram_ocr.ui.pdf_panel import PdfPanel
from chess_diagram_ocr.ui.result_panel import ResultPanel, read_board_image
from chess_diagram_ocr.ui.review_panel import ReviewPanel, ScanRequest
from chess_diagram_ocr.ui.shortcuts import bind_shortcuts
from chess_diagram_ocr.ui.state import AppState, load_state, save_state
from chess_diagram_ocr.ui.study_panel import StudyPanel
from chess_diagram_ocr.ui.training_dialog import TrainingController, TrainingRequest

ROOT = Path(__file__).resolve().parent
PIECE_IMAGE_DIR = ROOT / "assets" / "piece_images"
APP_STATE_PATH = ROOT / "data" / "app_tkinter_state.json"
DEFAULT_SPLITS_PATH = ROOT / "data" / "splits.csv"

logger = logging.getLogger(__name__)


class ChessOcrTkApp:
    """Monta a janela e liga os painéis. Nenhuma regra de OCR mora aqui."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Chess Diagram OCR - Tkinter")
        self.root.geometry("1700x980")

        self.service = OcrService(model_path=DEFAULT_MODEL_PATH)
        self.piece_images = PieceImages(PIECE_IMAGE_DIR)
        self.state = AppState()
        self.settings = load_settings()
        """Preferências do usuário (S-32). Por padrão nada sai da máquina."""

        self.analyzer = self._build_analyzer()
        """Motor de análise (S-33), ou `None`. Sem binário, a seção some da aba Análise."""

        self._is_running_ocr = False
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
            on_remote_consent=self._ask_remote_consent,
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
        )
        self.pdf_panel.pack(fill=tk.BOTH, expand=True)

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
        if self.pdf_panel is not None:
            self.pdf_panel.destroy_reader()
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

    def _remember_page_results(self) -> None:
        if self.result_panel is not None:
            self.result_panel.remember_page_results()

    def _cancel_export(self) -> None:
        self.export.cancel()
        if self.pdf_panel is not None:
            self.pdf_panel.disable_cancel_button()

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

    def _on_ocr_error(self, exc: Exception) -> None:
        if "Nenhum tabuleiro foi detectado" in str(exc) and self.result_panel is not None:
            self.result_panel.clear()
        self._set_status("Falha no OCR.")
        messagebox.showerror("Erro", f"Falha no OCR:\n{exc}")

    def _finish_ocr_ui(self) -> None:
        self._is_running_ocr = False
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
            self.settings = Settings(remote_fen=replace(configuracao, acknowledged=True))
            save_settings(DEFAULT_SETTINGS_PATH, self.settings)
        return bool(resposta["enviar"])

    def _reload_dataset_panel(self) -> None:
        if self.dataset_panel is not None:
            self.dataset_panel.reload()

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
            },
        )

    def _on_result(self, action: Callable[[ResultPanel], None]) -> Callable[[], None]:
        def _run() -> None:
            if self.result_panel is not None:
                action(self.result_panel)

        return _run

    def _open_next_review_item(self) -> None:
        if self.review_panel is not None:
            self.review_panel.open_next_pending()


def main() -> None:
    configure_logging(log_file=default_log_file())
    logger.info("Iniciando interface desktop.")
    root = tk.Tk()
    ChessOcrTkApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
