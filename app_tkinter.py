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
from collections.abc import Callable, Sequence
from dataclasses import replace
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import cv2
import numpy as np

from chess_diagram_ocr.atomic_io import read_image
from chess_diagram_ocr.board_detection import NoBoardDetectedError
from chess_diagram_ocr.cli import message_for
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
from chess_diagram_ocr.labels import (
    LabelStore,
    SavedSample,
    note_saved_diagram,
    pages_with_training_samples,
    saved_diagrams_by_page,
)
from chess_diagram_ocr.logging_setup import configure_logging, default_log_file
from chess_diagram_ocr.ocr_caption import caption_reader_from_settings
from chess_diagram_ocr.pdf_io import get_pdf_page_count
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
from chess_diagram_ocr.splits import load_splits
from chess_diagram_ocr.ui import (
    abas,
    atalhos,
    campos,
    estilos,
    geometria,
    legenda,
    menu,
    plataforma,
    rodape,
    rolagem,
    strings,
    texto,
    tokens,
)
from chess_diagram_ocr.ui.board_widget import PieceImages
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.dataset_panel import DatasetPanel
from chess_diagram_ocr.ui.export_controller import ExportController, ExportSettings
from chess_diagram_ocr.ui.field_draft import REGIMES, FieldDraft
from chess_diagram_ocr.ui.gallery_panel import LARGURA_MINIMA_DA_GALERIA, GalleryPanel
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
from chess_diagram_ocr.ui.pdf_panel import PdfPanel, open_in_system_reader
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

LARGURA_MINIMA_ESQUERDA = LARGURA_MINIMA_DA_GALERIA
"""Largura minima do painel esquerdo (editor, dataset, galeria). E o mesmo numero que o
`PanedWindow` usa para o divisor e que o piso da janela soma -- um so, para os dois nao
divergirem (S-150). Era 420 cravado, da S-31, de quando a Galeria nao existia -- agora deriva
da aba mais larga, e o porque esta em `LARGURA_MINIMA_DA_GALERIA` (S-154)."""

LARGURA_MINIMA_DIREITA = 520
"""Largura minima do visualizador de PDF."""

logger = logging.getLogger(__name__)


class ChessOcrTkApp:
    """Monta a janela e liga os painéis. Nenhuma regra de OCR mora aqui."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(strings.titulo_da_janela())
        self.root.geometry("1700x980")
        # O piso, e nao so o tamanho inicial (S-150). Sem ele a janela encolhe ate cortar a
        # fila de salvar do Resultado -- sem erro, sem rolagem, e sem o usuario saber que
        # existe um botao ali. O numero sai dos `minsize` dos paineis, logo abaixo.
        self.root.minsize(*geometria.piso_da_janela(LARGURA_MINIMA_ESQUERDA, LARGURA_MINIMA_DIREITA))

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
        self.lr_var = tk.StringVar(value="0.001")
        """Texto, e não `DoubleVar` (S-168): o `get()` de um `DoubleVar` levanta `TclError` com
        uma letra dentro, e levanta **onde é lido** -- dentro do treino, minutos depois. Como
        texto, o campo diz "não é um número" na tecla seguinte, e quem converte é `_train_lr`."""
        self.fresh_var = tk.BooleanVar(value=False)

        self.rodape = rodape.RodapeDaJanela(self.root, cancelar=self.busy.request_cancel)
        """O rodapé da janela (S-163). Era um `ttk.Label` cru com `StringVar` dentro do **painel
        esquerdo**: longe de onde o trabalho acontece, sem severidade, e fora da tela quando a
        janela encolhia. Empacotado **antes** do `PanedWindow`, que é o que o faz sobreviver ao
        encolher -- o `pack` reparte na ordem em que recebe."""
        self.rodape.pack(side=tk.BOTTOM, fill=tk.X)
        self.rodape.acompanhar(self.busy.running)

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
        self._build_menu()
        self._bind_shortcuts()
        self._restore_state_or_default_pdf()
        self._atualizar_abas()
        self._restore_window_arrangement()
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
        self.main_pane.add(self.left_frame, minsize=LARGURA_MINIMA_ESQUERDA)
        self.main_pane.add(self.right_frame, minsize=LARGURA_MINIMA_DIREITA)

        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        tabs = ttk.Notebook(self.left_frame)
        tabs.pack(fill=tk.BOTH, expand=True)
        # `Ctrl+Tab`, `Shift+Ctrl+Tab` e as teclas de acesso (S-162). Uma linha, e ela nunca tinha
        # sido escrita: a barra de abas era navegável só pelo mouse.
        tabs.enable_traversal()
        self.left_tabs = tabs

        # **A ordem é o item** (S-162). As seis abas misturavam dois níveis: Resultado, Análise e
        # Revisão são do diagrama aberto agora; Dataset, Galeria e Configuração são do acervo. Elas
        # passam a vir nessa ordem, e o corte entre os dois grupos é onde a barra muda de assunto.
        # A Configuração vai para o fim porque é a aba do primeiro dia e quase nunca depois.
        self.result_panel = ResultPanel(
            rolagem.aba_rolavel(tabs, "Resultado"),
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
        self.result_panel.pack(fill=tk.BOTH, expand=True)

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
            on_scan_book=lambda: self.gallery_panel.scan() if self.gallery_panel else None,
            on_cancel_book=lambda: self.gallery_panel.cancel_scan() if self.gallery_panel else None,
            queue_path=DEFAULT_QUEUE_PATH,
            service=self.service,
            busy=self.busy,
        )
        tabs.add(self.review_panel, text="Revisão")
        self.result_panel.set_review_settler(self._settle_review_item)

        self.dataset_panel = DatasetPanel(
            tabs,
            paths=self._dataset_paths,
            on_edit=self.result_panel.open_dataset_row,
            on_recheck=self.recheck_dataset_row,
            on_status=self._set_status,
            busy=self.busy,
        )
        tabs.add(self.dataset_panel, text="Dataset")

        self.gallery_panel = GalleryPanel(
            rolagem.aba_rolavel(tabs, "Galeria"),
            service=self.service,
            pdf_path=self._pdf_path_or_none,
            model_path=lambda: Path(self.model_path_var.get().strip()),
            max_boards=lambda: int(self.max_boards_var.get()),
            on_status=self._set_status,
            on_page_request=self._gallery_page_request,
            # Uma varredura por livro (S-119): a Galeria varre, e a fila de revisão sai da
            # mesma passada. Quem liga as duas abas é a janela -- nenhuma conhece a outra.
            review_sink=lambda: self.review_panel.scan_sink() if self.review_panel else None,
            on_annotations_changed=self._reload_confirmed_diagrams,
            busy=self.busy,
        )
        self.gallery_panel.pack(fill=tk.BOTH, expand=True)

        self._build_config_tab(rolagem.aba_rolavel(tabs, "Configuração", padding=6))

    def _build_config_tab(self, cfg_tab: ttk.Frame) -> None:
        campos.linha_de_caminho(cfg_tab, "Modelo (.pt)", self.model_path_var)
        campos.linha_de_caminho(cfg_tab, "CSV labels", self.dataset_csv_var)
        campos.linha_de_caminho(cfg_tab, "Pasta samples", self.samples_dir_var, tipo=campos.PASTA)

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
        self._spin_row(train_box, strings.TAMANHO_DO_LOTE, self.batch_var, 16, 512, 16)
        campos.linha_de_numero(train_box, strings.TAXA_DE_APRENDIZADO, self.lr_var, minimo=1e-6, maximo=1.0)
        ttk.Checkbutton(
            train_box, text="Treinar do zero (ignora o checkpoint atual)", variable=self.fresh_var
        ).pack(anchor="w", padx=8)
        texto.acompanhar(
            ttk.Label(
                train_box,
                text="Sem isso, o treino continua do checkpoint e só grava por cima se melhorar.",
                foreground=tokens.RESERVA[tokens.TEXTO_SECUNDARIO],
            )
        ).pack(anchor="w", padx=8, pady=(0, 4))
        self.btn_train_model = ttk.Button(train_box, text="Treinar modelo", command=self.training.start)
        self.btn_train_model.pack(anchor="w", padx=8, pady=8)
        Tooltip(
            self.btn_train_model,
            "Fica cinza durante o treino, que roda um por vez. O progresso e o cancelamento\n"
            "ficam no rodapé da janela.",
        )

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
            on_document_state=self.rodape.definir_documento,
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

        botao = ttk.Button(
            parent,
            text="Anotar página",
            style=estilos.estilo_de_botao(estilos.PRIMARIO),
            command=self.annotate_field_page,
        )
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

    def _train_lr(self) -> float:
        """O `Learning rate` como número. Texto inválido cai no padrão, e o campo já avisou."""
        bruto = str(self.lr_var.get()).strip().replace(",", ".")
        return float(bruto) if campos.numero_na_faixa(bruto, minimo=1e-6, maximo=1.0) else 0.001

    def _spin_row(self, parent: ttk.Widget, label: str, var: tk.Variable, frm: int, to: int, inc: int) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=frm, to=to, increment=inc, textvariable=var, width=12).pack(side=tk.LEFT)

    def _set_initial_sashes(self) -> None:
        """Põe o divisor onde ele estava, ou nos 42% da primeira execução (S-156).

        Era o número cravado, aplicado a **toda** abertura: quem trabalha com o PDF grande
        arrastava o divisor toda sessão e o perdia toda sessão.
        """
        fracao = self.state.sash_fraction or geometria.FRACAO_PADRAO_DO_DIVISOR
        try:
            if self.main_pane is not None:
                self.main_pane.sash_place(0, int(max(1, self.main_pane.winfo_width()) * fracao), 0)
        except tk.TclError as exc:
            # Erro transitorio de geometria enquanto o primeiro layout se estabiliza.
            logger.debug("Não foi possível posicionar o divisor inicial: %s", exc)

    def _restore_window_arrangement(self) -> None:
        """Tamanho, posição e aba de onde a sessão anterior parou (S-156).

        O divisor não vem aqui: ele é de `_set_initial_sashes`, que roda 180 ms depois porque o
        `PanedWindow` precisa de largura medida para posicionar a alça.
        """
        alvo = geometria.geometria_a_aplicar(
            self.state.window_geometry,
            plataforma.monitores(self.root),
            piso=geometria.piso_da_janela(LARGURA_MINIMA_ESQUERDA, LARGURA_MINIMA_DIREITA),
        )
        if alvo is not None:
            self.root.geometry(alvo)
        if self.left_tabs is not None:
            # A aba de trabalho na primeira abertura, e a guardada nas seguintes (S-162/S-156). A
            # janela abria na Configuração -- três caminhos de arquivo e os parâmetros de treino,
            # isto é, a aba do primeiro dia e quase nunca depois.
            rolagem.selecionar_aba(self.left_tabs, self.state.active_tab or abas.ABA_DE_TRABALHO)

    # ------------------------------------------------------------------------------ estado

    def _set_status(self, text: str) -> None:
        """Escreve na zona de mensagem do rodapé, de qualquer thread (S-163).

        Sem `update_idletasks()`: chamado de dentro de um callback de evento, ele reentra no
        loop de eventos do Tk e permite que outro callback rode no meio deste -- reentrância
        que a S-31 manda remover. O `after(0)` é o que faz o widget ser tocado só pela thread
        que o criou. A severidade sai da frase, em `ui/rodape.severidade_de`: os seis painéis
        passam por este ponto, e é ele que dá cor de erro aos 60 chamadores que não declaram uma.
        """
        if threading.current_thread() is threading.main_thread():
            self.rodape.mostrar(text)
        else:
            self.root.after(0, partial(self.rodape.mostrar, text))

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
            # `last_pdf` vazio = nunca houve execução anterior, e então não há zoom escolhido a
            # restaurar: quem enquadra é a S-157, com a primeira página inteira na tela.
            if self.state.last_pdf:
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

    def _remember_window_arrangement(self) -> None:
        """Anota tamanho, divisor e aba no estado (S-156)."""
        self.state.window_geometry = (
            geometria.geometria_gravavel(str(self.root.winfo_geometry())) or self.state.window_geometry
        )
        if self.main_pane is not None:
            self.state.sash_fraction = geometria.fracao_de_divisor(
                int(self.main_pane.sash_coord(0)[0]), int(self.main_pane.winfo_width())
            )
        if self.left_tabs is not None and self.left_tabs.select():
            # O **nome**, sem a contagem da S-162: "Revisão (129)" guardado não casaria com
            # "Revisão (54)" na sessão seguinte, e a janela cairia na primeira aba em silêncio.
            self.state.active_tab = abas.nome_base(str(self.left_tabs.tab(self.left_tabs.select(), "text")))

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
            self._remember_window_arrangement()
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
            lr=self._train_lr(),
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
        self._atualizar_titulo()
        self._atualizar_abas()

    def _atualizar_titulo(self) -> None:
        """O livro e a página no título da janela (S-167). Ver `strings.titulo_da_janela`."""
        painel = self.pdf_panel
        self.root.title(
            strings.titulo_da_janela(
                painel.name if painel is not None and painel.source is not None else "",
                painel.page_index if painel is not None else None,
                painel.page_count if painel is not None else None,
            )
        )

    def _on_page_rendered(self, page_index: int) -> None:
        """A página apareceu: traz de volta o que já foi reconhecido nela, se houver.

        Depois do render, e não antes: restaurar o editor para uma página que ainda não está
        na tela é exatamente o sintoma que a Fase 5 corrigiu -- o seletor apontando para
        diagramas que não são os da página exibida.
        """
        self._save_app_state()
        self._atualizar_titulo()
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

    def _reload_confirmed_diagrams(self) -> None:
        """As confirmações da base mudaram: relê as anotações e repinta a página (S-116).

        Quem chama é a Galeria, ao aplicar uma candidata -- que é o único gesto desta janela
        que grava `confirmed_from`. Antes isto vinha de carona no `Ctrl+S`, que relia as
        anotações do livro a cada amostra salva (15,0 ms) sem que salvar amostra pudesse mudar
        confirmação nenhuma.
        """
        if self.pdf_source is None:
            self.confirmed_diagrams = {}
            return
        self.confirmed_diagrams = self._read_confirmed(self.pdf_source)
        self._refresh_overlay(self.page_index)

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
            caixas = PageBoxes(page_index, params, escolhidas)
            painel.set_diagram_boxes(caixas)
            self._sync_selected_box()
            self._announce_if_page_done(caixas)
            return
        if detectadas is not None:
            # Página de prosa já visitada: sabe-se que não há diagrama, e dizê-lo é melhor que
            # mandar o detector percorrê-la de novo a cada volta.
            painel.set_diagram_boxes(detectadas)
            return

        self._request_overlay(page_index, params)

    def _announce_if_page_done(self, caixas: PageBoxes) -> None:
        """Diz na barra de status que esta página acabou -- e só isso (S-142).

        **Só o estado terminal fala.** A barra é uma linha só e todo mundo escreve nela; um
        aviso a cada virada de página gastaria o lugar onde aparecem o erro de OCR e o caminho
        da amostra salva. "Concluída" é raro, é a resposta para "posso virar?" e é a única
        parcela do rótulo do painel que não dá para ler sem contar.

        Vale nos dois momentos em que a resposta muda: ao chegar na página -- inclusive num
        livro trabalhado semanas atrás, porque quem responde é o CSV -- e ao salvar o último
        diagrama que faltava, que é quando ela **passa** a estar concluída. Nesse segundo caso
        isto escreve por cima do "Exemplo salvo: ..." que a aba Resultado acabou de pôr, e é o
        que se quer: o caminho do arquivo ainda aparece na caixa de sucesso, e a página ter
        terminado não aparece em lugar nenhum.
        """
        if caixas.all_saved:
            self._set_status(
                f"Página {caixas.page_index} concluída: todos os {len(caixas)} diagrama(s) "
                "já têm amostra salva."
            )

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
        # A recusa da caixa atrasada mora no `set_diagram_boxes`, mas aqui ela precisa vir
        # antes: quem vai desenhar é o `_refresh_overlay`, e ele também sincroniza a seleção e
        # anuncia a página concluída. Chamá-lo para a 16 com a 17 na tela deixaria o desenho de
        # fora e essas duas afirmações de pé -- sobre a página errada.
        if painel.page_index != caixas.page_index:
            logger.debug(
                "Detecção da página %d chegou tarde: a tela está na %d.",
                caixas.page_index,
                painel.page_index,
            )
            return

        if len(caixas):
            self._set_status(
                f"Página {caixas.page_index}: {len(caixas)} diagrama(s) marcado(s). "
                "Clique num deles para lê-lo."
            )
        # Depois do aviso, e pelo `_refresh_overlay` em vez de direto na tela (S-142). Duas
        # razões, ambas do carimbo: as caixas do detector não têm nenhum, e desenhá-las como
        # vieram deixava sem verde justamente a **primeira** visita à página -- a única em que
        # a pergunta "onde eu parei neste livro?" está sendo feita. E é lá dentro que a página
        # concluída se anuncia, então ela precisa falar por último para não ser sobrescrita
        # pela linha acima. O carimbo continua onde a S-71 o pôs, na hora de desenhar e contra
        # o CSV; o que faltava era este caminho passar por lá. O cache guarda as caixas cruas.
        self._refresh_overlay(caixas.page_index)

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
            # Pré-condição no rodapé, e não em caixa modal (S-164).
            self._set_status("Abra um PDF antes de ler a página.")
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
            self._set_status("Abra um PDF antes de anotar a página.")
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
        """Diz, ao virar a página, se ela já está anotada e se ela serve de referência.

        O aviso de treino é a metade da S-97 que fica na tela: anotar uma página de que já há
        amostra em `train` acrescenta ao conjunto de campo um diagrama que o próximo modelo
        terá visto. Não é proibido -- o conjunto é pequeno demais para recusar página --, mas
        precisa ser uma escolha e não um acidente, e a hora de saber é **antes** do clique.
        """
        if self.pdf_source is None:
            self.field_status_var.set("")
            return
        gravadas = {(pagina.pdf, pagina.page): pagina for pagina in load_field_set(FIELD_SET_PATH)}
        pagina = gravadas.get((self.pdf_source.name, self.page_index))
        estado = "página não anotada" if pagina is None else f"anotada: {FieldDraft.from_page(pagina).describe()}"
        self.field_status_var.set(f"{estado}{self._field_training_warning()}")

    def _field_training_warning(self) -> str:
        """" · N amostra(s) de treino desta página" quando houver, senão string vazia (S-97).

        Lê o `labels.csv` e o `splits.csv` a cada troca de página, e isso é aceitável **aqui**
        pelo mesmo motivo que não seria no `Ctrl+S` (S-116): virar página é um gesto por vez, e
        não o laço interno. Se algum dia doer, o remédio é o mesmo -- um cache invalidado ao
        salvar.
        """
        if self.pdf_source is None:
            return ""
        csv_path, _amostras, splits_path = self._dataset_paths()
        if not csv_path.exists() or not splits_path.exists():
            return ""
        try:
            paginas = pages_with_training_samples(LabelStore(csv_path).read(), load_splits(splits_path))
        except (OSError, ValueError) as exc:
            # Aviso ausente e melhor que janela quebrada: e informacao lateral.
            logger.debug("Não foi possível checar amostras de treino da página: %s", exc)
            return ""
        quantas = paginas.get((self.pdf_source.name, self.page_index), 0)
        return f" · ⚠ {quantas} amostra(s) de treino desta página" if quantas else ""

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
        image_bgr = read_image(filename)
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
        """Reconhece fora da thread da janela, e **registra** o que der errado (S-125).

        Era o único dos seis workers do programa que engolia a exceção sem log nenhum. Ler
        uma página é o que este programa faz: quando isso quebra num `.exe` sem console, o
        usuário recebia uma linha de texto e o arquivo de log não recebia nada.

        Os dois `except` são o item inteiro. "Não há tabuleiro nesta página" é a resposta
        mais comum de um livro -- prosa, índice, solução -- e não é falha: vai para o log em
        `INFO`, sem rastro, e para a tela sem caixa vermelha. O resto é falha de verdade, com
        `logger.exception` como nos outros cinco.
        """
        try:
            self._set_status("Detectando diagramas...")
            diagrams = run()
            self.root.after(0, partial(self._show_results, diagrams, origin))
        except NoBoardDetectedError as exc:
            logger.info("Nenhum tabuleiro em %s.", origin)
            self.root.after(0, partial(self._on_ocr_empty, exc))
        except Exception as exc:
            logger.exception("Falha no OCR de %s.", origin)
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

    def _on_ocr_empty(self, exc: NoBoardDetectedError) -> None:
        """A página não tem diagrama. É resposta à pergunta feita, e não erro (S-125).

        O editor é limpo pelo mesmo motivo de antes: deixar ali o reconhecimento da página
        anterior faria a tela responder outra pergunta. O caminho até aqui era procurar a
        mensagem dentro do texto da exceção, e agora é o tipo dela.

        **Sem caixa nenhuma desde a S-164.** Virar página em livro de exercícios cai em prosa a
        cada duas ou três, e ler uma página de prosa é o caso mais comum do programa: era um
        clique obrigatório para saber que nada aconteceu, na operação que mais se repete.
        """
        if self.result_panel is not None:
            self.result_panel.clear()
        self._set_status(f"{exc} Se há um diagrama aí, use Selecionar área (OCR).")

    def _on_ocr_error(self, exc: Exception) -> None:
        self._set_status("Falha no OCR.")
        messagebox.showerror("Erro", f"Falha no OCR:\n{exc}\n\nO traceback está no arquivo de log.")

    def _finish_ocr_ui(self) -> None:
        self._is_running_ocr = False
        # Limpo aqui, e não em `_show_results`: o pedido morre também quando o OCR falha, e
        # este é o único ponto por onde os dois caminhos passam.
        self._select_after_ocr = None
        self._set_ocr_controls_enabled(True)

    # ------------------------------------------------------------- ligações entre painéis

    def _atualizar_abas(self) -> None:
        """Põe no rótulo de cada aba quanto trabalho ela carrega (S-162).

        Chamado nos pontos em que os números mudam -- abrir livro, salvar amostra, fechar item da
        fila --, e não num relógio: a contagem só muda quando alguém a muda, e um `after` periódico
        redesenharia a barra de abas para dizer o mesmo número.
        """
        if self.left_tabs is None:
            return
        contagens = {
            "Revisão": len(self.review_panel.queue.pending()) if self.review_panel is not None else None,
            "Dataset": self.dataset_panel.contagem_de_amostras() if self.dataset_panel is not None else None,
            "Galeria": len(self.gallery_panel.model) if self.gallery_panel is not None else None,
        }
        for indice in range(int(self.left_tabs.index("end"))):
            nome = abas.nome_base(str(self.left_tabs.tab(indice, "text")))
            if nome in contagens:
                self.left_tabs.tab(indice, text=abas.rotulo(nome, contagens[nome]))

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
        texto.acompanhar(ttk.Label(wrap, text=configuracao.consent_message(), justify=tk.LEFT)).pack(anchor="w")
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

    def _reload_dataset_panel(self, saved: Sequence[SavedSample] = ()) -> None:
        """Uma amostra foi gravada: a aba Dataset relê, e o visualizador repinta de verde.

        **Sem tocar o disco** (S-116, corte 2). `saved` é o que o editor acabou de gravar, e é
        o bastante para o índice de verdes: relê-lo do `labels.csv` custava 30,9 ms sobre 3.936
        linhas, e o arquivo é o que o projeto existe para fazer crescer. A aba Dataset também
        não lê nada aqui -- ela marca `_stale` e recarrega quando for exibida (corte 1).
        """
        if self.dataset_panel is not None:
            self.dataset_panel.reload()
        for amostra in saved:
            note_saved_diagram(self.saved_diagrams, amostra, source_pdf=self._pdf_name())
        self._refresh_overlay(self.page_index)
        self._atualizar_abas()

    def _pdf_name(self) -> str:
        return self.pdf_source.name if self.pdf_source is not None else ""

    def _open_review_item(self, item: Any, position: int) -> None:
        if self.result_panel is not None:
            self.result_panel.open_review_item(item, position)

    def _settle_review_item(self, position: int, fen: str, side: str) -> None:
        """Fecha na fila o item que acabou de ser corrigido e salvo (S-22)."""
        if self.review_panel is None:
            return
        self.review_panel.apply_correction(position, fen, side)
        self._atualizar_abas()
        self._set_status(f"Item da fila marcado como revisado. {self.review_panel.queue.summary()}")

    def recheck_dataset_row(self, row: DatasetRow) -> str:
        """Compara o que o modelo lê na amostra com o rótulo gravado (S-23)."""
        samples_dir = Path(self.samples_dir_var.get())
        board_rgb = read_board_image(str(row.image_path(samples_dir)))
        if board_rgb is None:
            raise FileNotFoundError(f"Imagem não encontrada: {row.image_path(samples_dir)}")
        return self.service.recheck_label(board_rgb, row.placement).describe(row.filename)

    # ----------------------------------------------------------------------------- atalhos

    def _comandos(self) -> dict[str, Callable[[], None]]:
        """Nome → função, para o menu (S-161) e os atalhos (S-165) saírem da mesma fonte.

        **Por que esta tabela mora aqui.** Ela é a única coisa do assunto que precisa dos widgets:
        `ui/atalhos.py` declara qual tecla faz o quê e `ui/menu.py` declara onde cada comando
        aparece, os dois sem `tkinter`. O que sobra é amarrar nome a método, e isso é do objeto que
        **é** a janela -- a mesma razão pela qual a ordem do `pack` da S-163 ficou aqui.

        Os guardas de `None` não são zelo: os painéis são criados em `_build_ui`, e um roteiro de
        teste monta a janela sem eles. Sem o guarda, o menu montaria e o primeiro clique estouraria.
        """
        return {
            "abrir_pdf": self._on_pdf(lambda p: p.open_pdf()),
            "abrir_no_leitor": self._on_pdf(lambda p: p.open_in_system_reader()),
            "exportar_pgn": lambda: self.export.start(self.pdf_source),
            "sair": self._on_close,
            "aplicar_fen": self._on_result(lambda p: p.apply_fen_edit()),
            "apagar_casa": self._on_result(lambda p: p.delete_selected_square()),
            "salvar": self._on_result(lambda p: p.save_current()),
            "salvar_todos": self._on_result(lambda p: p.save_all()),
            "diagrama_anterior": self._on_result(lambda p: p.prev_diagram()),
            "proximo_diagrama": self._on_result(lambda p: p.next_diagram()),
            "proximo_da_fila": self._open_next_review_item,
            # Página do PDF, e não diagrama: as setas já são do editor (S-20), e virar a
            # página é a outra navegação que a leitura pede o tempo todo (S-70).
            "pagina_anterior": self._on_pdf(lambda p: p.prev_page()),
            "proxima_pagina": self._on_pdf(lambda p: p.next_page()),
            "ajustar_largura": self._on_pdf(lambda p: p.fit_width()),
            "ajustar_pagina": self._on_pdf(lambda p: p.fit_page()),
            "marcar_diagramas": self._on_pdf(lambda p: p.on_boxes_toggle()),
            "roda_vira_pagina": self._save_app_state,
            "ler_pagina": self.ocr_all,
            "ler_melhor": self.ocr_best,
            "selecionar_area": self._on_pdf(lambda p: p.toggle_area_selection()),
            "varrer_livro": lambda: self.gallery_panel.scan() if self.gallery_panel is not None else None,
            "recarregar_modelo": self.reload_model,
            "treinar": self.training.start,
            "legenda_de_atalhos": self._abrir_legenda,
            "abrir_log": self._abrir_log,
            "sobre": self._sobre,
        }

    def _build_menu(self) -> None:
        """A barra de menus (S-161). Depois dos painéis: os comandos falam com eles."""
        painel = self.pdf_panel
        menu.montar(
            self.root,
            self._comandos(),
            interruptores={} if painel is None else painel.interruptores_de_vista,
            recentes=self._livros_recentes,
        )

    def _livros_recentes(self) -> list[tuple[str, Callable[[], None]]]:
        """Os livros que o estado lembra, para o submenu "Abrir recente" (S-161)."""
        return [(Path(caminho).name, partial(self.load_pdf, Path(caminho))) for caminho in self.state.recentes()]

    def _abrir_legenda(self) -> None:
        """A legenda de atalhos do menu Ajuda (S-165). Ela se escreve da tabela de `ui/atalhos.py`."""
        legenda.abrir(self.root)

    def _abrir_log(self) -> None:
        """Abre o log no leitor do sistema, ou diz que não há um (S-161/S-127).

        Num checkout `default_log_file()` devolve `None` de propósito -- o terminal já é o rastro --,
        e o item de menu tem de dizer isso em vez de não fazer nada.
        """
        alvo = default_log_file()
        if alvo is None or not alvo.exists():
            self._set_status("Não há arquivo de log neste ambiente: defina CVOFF_LOG_DIR para criar um.")
            return
        open_in_system_reader(alvo)

    def _sobre(self) -> None:
        """Caixa "Sobre", e ela é modal de propósito: quem a abriu pediu por ela pelo menu."""
        messagebox.showinfo(f"Sobre o {strings.PRODUTO}", strings.sobre_o_produto(self.theme))

    def _bind_shortcuts(self) -> None:
        """Atalhos do ciclo corrigir → salvar → próximo (S-20), da tabela de `ui/atalhos.py`."""
        bind_shortcuts(self.root, atalhos.ligacoes(self._comandos()))

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

    # **A ordem responde duas perguntas diferentes, e a da instalação vem primeiro** (Fase 18).
    # O auto-teste existe para dizer "esta instalação funciona?" numa máquina limpa; se o
    # checkpoint não carrega, isso é verdade sobre a instalação e não depende de qual PDF o
    # usuário escolheu. Só depois vem "e este arquivo dá para abrir?".
    #
    # As duas passaram a ser passo próprio porque **classificar exige saber onde falhou**.
    # Exercitadas no `.exe` recém-construído em 2026-08-18, as duas caíam no `except` genérico
    # do reconhecimento e saíam com **1 e um traceback em inglês** -- 1 quer dizer "o programa
    # falhou", e nos dois casos quem falhou foi um arquivo. São duas das três falhas que o
    # critério de saída da Fase 18 nomeia; a terceira (`settings.json` inválido) já estava
    # tratada pela S-124.
    try:
        with servico.model_session(modelo):
            pass
    except Exception as exc:  # noqa: BLE001 - o que o torch levanta aqui não tem tipo próprio
        logger.exception("Auto-teste: o checkpoint não pôde ser lido.")
        logger.error(
            "Auto-teste: o checkpoint em %s existe mas não pôde ser lido (%s). Ele pode estar "
            "truncado, ter vindo pela metade, ou ser de outra arquitetura -- ver `arch_version`. "
            "O rastro completo está no log.",
            modelo,
            message_for(exc),
        )
        return 3

    try:
        get_pdf_page_count(caminho)
    except Exception as exc:  # noqa: BLE001 - o `pymupdf` levanta a sua própria família aqui
        logger.exception("Auto-teste: o PDF não pôde ser aberto.")
        logger.error("Auto-teste: não foi possível abrir %s (%s).", caminho.name, message_for(exc))
        return 2

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
    try:
        # Antes de `tk.Tk()`, e a ordem é o item (S-148): depois da primeira janela o Windows
        # já classificou o processo e a chamada existe sem efeito. Ver `ui/plataforma.py`.
        plataforma.consciencia_de_dpi()
        root = tk.Tk()
        plataforma.preparar_janela(root)
        ChessOcrTkApp(root)
        root.mainloop()
    except Exception:
        # A guarda que faz o arquivo da S-127 valer alguma coisa. Sem ela, uma exceção aqui
        # sobe para o `sys.excepthook`, que escreve em `stderr` -- e num bundle `console=False`
        # `stderr` não vai a lugar nenhum. O arquivo de log existiria e a única falha que
        # ninguém consegue diagnosticar continuaria fora dele.
        logger.exception("A janela não abriu.")
        # Re-levanta: num checkout o traceback no terminal continua sendo o rastro mais curto,
        # e o código de saída continua dizendo que falhou.
        raise


if __name__ == "__main__":
    main()
