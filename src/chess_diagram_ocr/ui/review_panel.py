"""Aba de revisão: a fila da S-22 na tela (S-22 + S-20).

O painel não sabe reconhecer nada e não guarda modelo: ele varre com `build_review_queue`,
mostra o resultado ordenado e devolve o item escolhido ao dono da janela, que é quem tem o
editor de posição. Essa fronteira é a mesma que a Fase 6 vai querer entre serviço e
apresentação (S-31), e mantê-la agora custa nada.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..config import ACCEPT_MIN_CONFIDENCE, DEFAULT_MAX_BOARDS, DEFAULT_READING_ORDER, OrientationMode, ReadingOrder
from ..review_queue import (
    DEFAULT_CACHE_DIR,
    DEFAULT_QUEUE_PATH,
    ReviewItem,
    ReviewQueue,
    build_review_queue,
    error_rate,
    merge_queues,
    rare_classes_from_labels,
)
from ..service import OcrService
from . import estilos
from .busy import BusyRegistry, BusyToken

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanRequest:
    """Os parâmetros da varredura, como a janela principal os tem configurados."""

    pdf_path: Path
    model_path: Path
    labels_csv: Path
    dpi: int = 220
    max_boards_per_page: int = DEFAULT_MAX_BOARDS
    orientation: OrientationMode = "auto"
    reading_order: ReadingOrder = DEFAULT_READING_ORDER
    start_page: int = 0
    end_page: int | None = None
    accept_threshold: float = ACCEPT_MIN_CONFIDENCE


class ReviewPanel(ttk.Frame):
    """Lista navegável da fila, com varredura em segundo plano e cancelamento."""

    COLUMNS = ("prioridade", "página", "diagrama", "confiança", "status", "motivo")
    HEADINGS = {
        "prioridade": "Prio.",
        "página": "Pag.",
        "diagrama": "Diag.",
        "confiança": "Conf. min",
        "status": "Status",
        "motivo": "Motivo",
    }
    WIDTHS = {"prioridade": 60, "página": 50, "diagrama": 50, "confiança": 80, "status": 80, "motivo": 460}

    def __init__(
        self,
        parent: tk.Misc,
        *,
        scan_request: Callable[[], ScanRequest | None],
        on_open: Callable[[ReviewItem, int], None],
        on_status: Callable[[str], None] | None = None,
        queue_path: Path = DEFAULT_QUEUE_PATH,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        service: OcrService | None = None,
        busy: BusyRegistry | None = None,
    ) -> None:
        """`service` empresta o modelo sob o lock da S-31 durante a varredura (S-57).

        A varredura da fila percorre o livro inteiro e é uma das duas operações longas que
        carregavam o `.pt` por conta própria, fora do lock -- enquanto o treino, noutra
        thread, reescrevia esse mesmo arquivo.
        """
        super().__init__(parent, padding=6)
        self._service = service
        self._scan_request = scan_request
        self._on_open = on_open
        self._on_status = on_status or (lambda _text: None)
        self.queue_path = Path(queue_path)
        self.cache_dir = Path(cache_dir)

        self.queue = ReviewQueue.load(self.queue_path)
        self.queue.sort()
        self._cancel_event: threading.Event | None = None
        self._scanning = False
        self._busy_registry = busy
        """Onde a varredura da fila se declara como operação longa (S-112)."""
        self._busy_token: BusyToken | None = None

        self.summary_var = tk.StringVar(value="")
        self.progress_var = tk.StringVar(value="")
        self.only_pending_var = tk.BooleanVar(value=True)
        self._row_index: list[int] = []
        """Posição na `queue.items` de cada linha visível, na ordem da tabela."""

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        self.btn_scan = ttk.Button(toolbar, text="Varrer PDF", command=self.start_scan)
        self.btn_scan.pack(side=tk.LEFT)
        self.btn_cancel = ttk.Button(toolbar, text="Cancelar", command=self.cancel_scan, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=6)
        ttk.Button(toolbar, text="Abrir fila", command=self.open_queue_file).pack(side=tk.LEFT, padx=6)
        ttk.Button(toolbar, text="Salvar fila", command=self.save_queue).pack(side=tk.LEFT)
        ttk.Checkbutton(
            toolbar,
            text="Só pendentes",
            variable=self.only_pending_var,
            command=self.refresh,
        ).pack(side=tk.RIGHT)

        ttk.Label(self, textvariable=self.summary_var, wraplength=760).pack(anchor="w")
        ttk.Label(self, textvariable=self.progress_var, wraplength=760).pack(anchor="w", pady=(0, 4))

        table_wrap = ttk.Frame(self)
        table_wrap.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(table_wrap, columns=self.COLUMNS, show="headings", selectmode="browse", height=14)
        for column in self.COLUMNS:
            self.tree.heading(column, text=self.HEADINGS[column])
            self.tree.column(column, width=self.WIDTHS[column], anchor="w", stretch=(column == "motivo"))
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self.tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _event: self.open_selected())
        self.tree.bind("<Return>", lambda _event: self.open_selected())

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(actions, text="Corrigir agora", style=estilos.estilo_de_botao(estilos.PRIMARIO), command=self.open_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="Marcar revisado", command=lambda: self.mark_selected("done")).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="Pular", command=lambda: self.mark_selected("skipped")).pack(side=tk.LEFT)
        ttk.Button(actions, text="Reabrir", command=lambda: self.mark_selected("pending")).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="Próximo pendente", command=self.open_next_pending).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------ tabela

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._row_index.clear()

        only_pending = bool(self.only_pending_var.get())
        for position, item in enumerate(self.queue.items):
            if only_pending and item.status != "pending":
                continue
            self._row_index.append(position)
            self.tree.insert(
                "",
                tk.END,
                values=(
                    f"{item.priority:.1f}",
                    item.page_number,
                    item.diagram_index,
                    f"{item.min_confidence:.3f}",
                    item.status,
                    "; ".join(item.reasons),
                ),
            )

        if self.queue.items:
            taxa = error_rate(self.queue.items)
            self.summary_var.set(f"{self.queue.summary()} | {taxa:.0%} com sinal objetivo de erro")
        else:
            self.summary_var.set("Fila vazia. Abra um PDF e use 'Varrer PDF'.")

    def selected_position(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        row = self.tree.index(selection[0])
        if not 0 <= row < len(self._row_index):
            return None
        return self._row_index[row]

    def open_selected(self) -> None:
        position = self.selected_position()
        if position is None:
            self._on_status("Selecione um item da fila.")
            return
        self._on_open(self.queue.items[position], position)

    def open_next_pending(self) -> None:
        """Atalho do ciclo de correção: pega o mais prioritário ainda não resolvido."""
        for position, item in enumerate(self.queue.items):
            if item.status == "pending":
                self.select_position(position)
                self._on_open(item, position)
                return
        self._on_status("Nenhum item pendente na fila.")

    def select_position(self, position: int) -> None:
        if position not in self._row_index:
            return
        row = self._row_index.index(position)
        children = self.tree.get_children()
        if row < len(children):
            self.tree.selection_set(children[row])
            self.tree.see(children[row])

    def mark_selected(self, status: str) -> None:
        position = self.selected_position()
        if position is None:
            self._on_status("Selecione um item da fila.")
            return
        self.queue.mark(position, status)  # type: ignore[arg-type]
        self.save_queue(quiet=True)
        self.refresh()
        self._on_status(f"Item {self.queue.items[position].label} marcado como {status}.")

    def apply_correction(self, position: int, fen: str, side_to_move: str) -> None:
        """Grava na fila a correção que o editor fez e marca o item como revisado."""
        if not 0 <= position < len(self.queue.items):
            return
        self.queue.update_fen(position, fen, side_to_move)
        self.queue.mark(position, "done")
        self.save_queue(quiet=True)
        self.refresh()

    # ---------------------------------------------------------------- varredura

    def start_scan(self) -> None:
        if self._scanning:
            messagebox.showinfo("Varredura em andamento", "Já existe uma varredura de fila em execução.")
            return
        request = self._scan_request()
        if request is None:
            messagebox.showwarning("Aviso", "Abra um PDF antes de montar a fila de revisão.")
            return

        self._scanning = True
        self._cancel_event = threading.Event()
        if self._busy_registry is not None:
            self._busy_token = self._busy_registry.register(
                "varredura da fila de revisão",
                # Os recortes vão para `data/review_cache/` página a página, por `write_image`:
                # refazer a varredura relê o PDF, mas não paga de novo a parte cara. Fechar
                # aqui custa tempo, não trabalho -- é a mesma conta da exportação (S-24).
                loses_work=False,
                cancellable=True,
                detail=request.pdf_path.name,
                cancel=self.cancel_scan,
            )
        self.btn_scan.configure(state=tk.DISABLED)
        self.btn_cancel.configure(state=tk.NORMAL)
        self.progress_var.set("Preparando varredura...")

        worker = threading.Thread(target=self._scan_worker, args=(request, self._cancel_event), daemon=True)
        worker.start()

    def cancel_scan(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.progress_var.set("Cancelando... (termina a página atual)")

    def _scan_worker(self, request: ScanRequest, cancel_event: threading.Event) -> None:
        def _progress(page_index: int, total_pages: int, page_boards: int, total_positions: int) -> None:
            self.after(
                0,
                lambda: self.progress_var.set(
                    f"Varrendo... página {page_index + 1} de {total_pages} | diagramas: {total_positions}"
                ),
            )

        try:
            rare = rare_classes_from_labels(request.labels_csv)
            fresh = build_review_queue(
                request.pdf_path,
                request.model_path,
                dpi=request.dpi,
                max_boards_per_page=request.max_boards_per_page,
                orientation=request.orientation,
                start_page=request.start_page,
                end_page=request.end_page,
                reading_order=request.reading_order,
                accept_threshold=request.accept_threshold,
                rare_classes=rare,
                cache_dir=self.cache_dir,
                cancel_event=cancel_event,
                progress_callback=_progress,
                # Mesmo OCR de legenda do reconhecimento e da exportação (S-43): uma fila
                # montada por outro pipeline manda corrigir um diagrama que o PGN não tem.
                caption_reader=getattr(self._service, "caption_reader", None),
                model_session=(
                    self._service.model_session(request.model_path) if self._service is not None else None
                ),
            )
            self.after(0, lambda: self._apply_scan(fresh, cancel_event.is_set()))
        except Exception as exc:  # noqa: BLE001 - erro de varredura vira mensagem, não crash
            logger.exception("Falha ao montar a fila de revisão.")
            detalhe = str(exc)
            self.after(0, lambda: messagebox.showerror("Fila de revisão", f"Falha na varredura:\n{detalhe}"))
        finally:
            self.after(0, self._finish_scan)

    def _apply_scan(self, fresh: ReviewQueue, cancelled: bool) -> None:
        if self.queue.items and self.queue.source_pdf == fresh.source_pdf:
            # Revarredura não pode ressuscitar o que já foi revisado -- e o que `merge_queues`
            # garante. Sem isso, cada varredura apagaria o trabalho da sessao anterior.
            fresh = merge_queues(self.queue, fresh)
        self.queue = fresh
        self.save_queue(quiet=True)
        self.refresh()
        sufixo = " (cancelada)" if cancelled else ""
        self.progress_var.set(f"Varredura concluída{sufixo}. {self.queue.summary()}")
        self._on_status(f"Fila de revisão pronta{sufixo}: {self.queue.summary()}")

    def _finish_scan(self) -> None:
        self._scanning = False
        self._cancel_event = None
        if self._busy_token is not None:
            self._busy_token.release()
            self._busy_token = None
        self.btn_scan.configure(state=tk.NORMAL)
        self.btn_cancel.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------ arquivo

    def save_queue(self, quiet: bool = False) -> None:
        try:
            self.queue.save(self.queue_path)
            if not quiet:
                self._on_status(f"Fila salva em {self.queue_path}.")
        except OSError as exc:
            logger.warning("Não foi possível salvar a fila de revisão: %s", exc)
            if not quiet:
                messagebox.showerror("Fila de revisão", f"Não foi possível salvar a fila:\n{exc}")

    def open_queue_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Abrir fila de revisão",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
            initialdir=str(self.queue_path.parent),
        )
        if not filename:
            return
        self.queue_path = Path(filename)
        self.queue = ReviewQueue.load(self.queue_path)
        self.queue.sort()
        self.refresh()
        self._on_status(f"Fila carregada de {self.queue_path}.")
