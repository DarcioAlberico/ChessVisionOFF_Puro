"""A aba "Resultado": o editor de diagramas reconhecidos (S-31).

**O que ele é.** O lugar onde o usuário conserta o que o OCR leu. Tudo que a Fase 4
construiu desemboca aqui: o tabuleiro editável da S-20, o heatmap e o painel de legalidade
da S-21, o item da fila de revisão da S-22 e a amostra do dataset da S-23 -- as quatro
origens abrem **o mesmo editor**, e é por isso que elas moram juntas neste módulo em vez de
cada uma num canto.

**O que ele guarda.** Três listas paralelas -- os diagramas, as FENs editadas e os lados a
jogar -- mais o índice selecionado e o cache de reconhecimento por página. Estavam soltas no
`ChessOcrTkApp` junto com o estado do PDF e o do estudo, e a mistura era o que permitia a um
método de navegação de página mexer no que estava sendo editado sem que nada dissesse.

**Por que as listas são paralelas e não campos do diagrama.** `fen_edits[i]` é o que o
usuário está editando *agora*; `items[i].placement` é o que o modelo leu. Fundi-los perderia
a leitura original, que é o que o heatmap e a comparação com o rótulo precisam.

**Os três estados de vínculo.** O editor pode estar mostrando o resultado de uma página
(`page_key` preenchido), um item da fila (`review_position`) ou uma amostra do dataset
(`editing_sample`). Eles são exclusivos, e distingui-los é o que faz `Ctrl+S` gravar amostra
nova num caso e **regravar a linha existente** no outro -- salvar de novo criaria uma segunda
amostra da mesma imagem, e o rótulo errado continuaria no arquivo (S-23).
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np

from chess_diagram_ocr.dataset_browser import DatasetRow, update_row
from chess_diagram_ocr.fen_utils import is_valid_fen, square_name
from chess_diagram_ocr.net_correction import predict_fen_via_net
from chess_diagram_ocr.review_queue import ReviewItem
from chess_diagram_ocr.semantics import compose_fen
from chess_diagram_ocr.service import OcrService, RecognitionOrigin, RecognizedDiagram

from . import board_edit
from .board_widget import InteractiveBoard, PieceImages
from .legality import explain_position
from .page_results import PageOcrParams, PageResults, PageResultsCache, PageSwitch, decide_page_switch

logger = logging.getLogger(__name__)

SIDE_SOURCE_LABELS = {
    "text": "do texto do PDF",
    "legality": "deduzido da posicao",
    "default": "assumido",
    "manual": "definido por voce",
    "queue": "vindo da fila de revisao",
}
"""A procedência aparece ao lado do lado a jogar porque "pretas jogam" lido de uma legenda e
"pretas jogam" assumido pelo padrão têm o mesmo texto e valores muito diferentes para quem
vai conferir."""


def confidence_summary(item: RecognizedDiagram) -> str:
    """Resumo de confiança e legalidade do diagrama, para a barra de status.

    Sem Tk, e testável. A ordem é a decisão: o **mínimo** por casa vem antes da média porque
    a média fica em ~0,97 mesmo em tabuleiro com erro (S-10), e a orientação vem antes de
    tudo porque, se o diagrama está de cabeça para baixo, conferir casa por casa é perda de
    tempo (S-13).
    """
    partes = [f"conf min {item.min_confidence:.3f}", f"media {item.mean_confidence:.3f}"]

    if item.orientation_ambiguous:
        partes.append(f"ORIENTACAO INCERTA ({item.orientation_reason or 'as duas eram plausiveis'})")
    elif item.rotation:
        partes.append(f"lido a {item.rotation} graus")

    if item.uncertain_squares:
        nomes = ", ".join(square_name(casa) for casa in item.uncertain_squares[:4])
        sufixo = f" +{len(item.uncertain_squares) - 4}" if len(item.uncertain_squares) > 4 else ""
        partes.append(f"casas inseguras: {nomes}{sufixo}")

    if item.is_legal is False:
        detalhe = f" ({'; '.join(item.problems)})" if item.problems else ""
        # "Xeque invertido" nao e erro de leitura: o diagrama nao diz de quem e a vez e o
        # app assume brancas. Chamar isso de ILEGAL manda o usuario procurar um erro que
        # nao existe no tabuleiro.
        partes.append(("LADO A JOGAR" if item.is_fatal is False else "ILEGAL") + detalhe)

    return " | ".join(partes)


def side_source_label(item: RecognizedDiagram) -> str:
    """Texto entre parênteses ao lado do rádio de lado a jogar. Vazio quando não há o que dizer."""
    if item.side_conflicting:
        return "(texto e posicao discordam)"
    fonte = SIDE_SOURCE_LABELS.get(item.side_to_move_source, "")
    return f"({fonte})" if fonte else ""


def read_board_image(path_text: str) -> np.ndarray | None:
    """Lê a imagem de um tabuleiro do disco em RGB. `None` se ela não existe mais."""
    path = Path(path_text)
    if not path.exists():
        return None
    image_bgr = cv2.imread(str(path))
    if image_bgr is None:
        return None
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


class ResultPanel(ttk.Frame):
    """O editor: diagramas reconhecidos, correção por clique e gravação no dataset."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        service: OcrService,
        piece_images: PieceImages,
        paths: Callable[[], tuple[Path, Path]],
        ocr_params: Callable[[], PageOcrParams],
        document_key: Callable[[], str],
        model_path: Callable[[], Path],
        on_status: Callable[[str], None],
        on_ocr_local: Callable[[int], None],
        max_boards: Callable[[], int],
        on_sync_study: Callable[[], None],
        on_state_changed: Callable[[], None],
        on_focus_request: Callable[[], None],
        on_sample_saved: Callable[[], None],
    ) -> None:
        super().__init__(parent, padding=6)
        self._service = service
        self._paths = paths
        self._ocr_params = ocr_params
        self._document_key = document_key
        self._model_path = model_path
        self._on_status = on_status
        self._on_ocr_local = on_ocr_local
        self._max_boards = max_boards
        self._on_sync_study = on_sync_study
        self._on_state_changed = on_state_changed
        self._on_focus_request = on_focus_request
        self._on_sample_saved = on_sample_saved
        """Chamado depois de regravar a linha de uma amostra: a aba Dataset precisa reler."""

        self.items: list[RecognizedDiagram] = []
        self.fen_edits: list[str] = []
        self.side_edits: list[str] = []
        self.selected_index = 0

        self.origin: RecognitionOrigin | None = None
        self.page_key: tuple[str, int] | None = None
        """De que página de PDF vem o que está no editor. `None` = não veio de uma página
        inteira: imagem local, recorte de área, item da fila ou amostra do dataset."""

        self.review_position: int | None = None
        self.editing_sample: str | None = None
        self.page_results = PageResultsCache()

        self.fen_var = tk.StringVar(value="")
        self.side_to_move_var = tk.StringVar(value="w")
        self.side_source_var = tk.StringVar(value="")
        self.selected_diag_var = tk.IntVar(value=1)
        self.legality_var = tk.StringVar(value="")
        self.material_var = tk.StringVar(value="")
        self.heatmap_var = tk.BooleanVar(value=True)
        self.board_zoom_var = tk.DoubleVar(value=0.85)

        self._is_correcting_net = False
        self._settle_review: Callable[[int, str, str], None] | None = None

        self._build(piece_images)

    # ------------------------------------------------------------------------------ layout

    def _build(self, piece_images: PieceImages) -> None:
        botoes = ttk.Frame(self)
        botoes.pack(fill=tk.X, padx=8, pady=8)
        self.btn_ocr_local_best = ttk.Button(
            botoes, text="OCR local (melhor)", command=lambda: self._on_ocr_local(1)
        )
        self.btn_ocr_local_best.pack(side=tk.LEFT)
        self.btn_ocr_local_all = ttk.Button(
            botoes, text="OCR local (todos)", command=lambda: self._on_ocr_local(self._max_boards())
        )
        self.btn_ocr_local_all.pack(side=tk.LEFT, padx=6)
        ttk.Label(self, text="Use imagem local para OCR fora do PDF.").pack(anchor="w", padx=8, pady=(2, 8))

        caixa = ttk.LabelFrame(self, text="Reconhecido (clique e arraste para corrigir)")
        caixa.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        zoom_row = ttk.Frame(caixa)
        zoom_row.pack(fill=tk.X, padx=8, pady=(6, 0))
        ttk.Label(zoom_row, text="Zoom board").pack(side=tk.LEFT)
        ttk.Button(zoom_row, text="-", width=3, command=lambda: self.zoom(-0.1)).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(zoom_row, text="+", width=3, command=lambda: self.zoom(0.1)).pack(side=tk.LEFT, padx=(2, 6))
        self.lbl_zoom = ttk.Label(zoom_row, text="85%")
        self.lbl_zoom.pack(side=tk.LEFT)
        ttk.Checkbutton(
            zoom_row, text="Heatmap de incerteza", variable=self.heatmap_var, command=self.on_heatmap_toggle
        ).pack(side=tk.RIGHT)

        # O editor da S-20 no lugar do canvas somente-leitura: corrigir uma peca passa de
        # "contar casas e reescrever a FEN" para um arraste.
        self.board = InteractiveBoard(
            caixa,
            mode="edit",
            on_change=self.on_board_changed,
            on_select=self.on_square_selected,
            on_status=self._on_status,
            piece_images=piece_images,
            background="#f2f2f2",
            min_size=260,
            max_size=520,
        )
        self.board.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.board.set_heatmap_enabled(True)

        legal = ttk.Frame(caixa)
        legal.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(legal, textvariable=self.legality_var, wraplength=520, justify=tk.LEFT).pack(anchor="w")
        ttk.Label(legal, textvariable=self.material_var, foreground="#555555").pack(anchor="w")

        nav = ttk.Frame(caixa)
        nav.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(nav, text="Diagrama anterior", command=self.prev_diagram).pack(side=tk.LEFT)
        ttk.Button(nav, text="Proximo diagrama", command=self.next_diagram).pack(side=tk.LEFT, padx=6)
        ttk.Label(nav, text="Selecionado").pack(side=tk.LEFT, padx=(12, 4))
        self.spin_diag = ttk.Spinbox(
            nav, from_=1, to=1, textvariable=self.selected_diag_var, width=6, command=self.on_diagram_spin
        )
        self.spin_diag.pack(side=tk.LEFT)
        self.spin_diag.bind("<Return>", lambda _event: self.on_diagram_spin())
        self.spin_diag.bind("<FocusOut>", lambda _event: self.on_diagram_spin())

        fen_box = ttk.LabelFrame(self, text="FEN e acoes")
        fen_box.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(fen_box, text="FEN").pack(anchor="w", padx=8, pady=(6, 0))
        entry = ttk.Entry(fen_box, textvariable=self.fen_var)
        entry.pack(fill=tk.X, padx=8, pady=(0, 4))
        entry.bind("<Return>", lambda _event: self.apply_fen_edit())

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

        acoes = ttk.Frame(fen_box)
        acoes.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(acoes, text="Aplicar FEN", command=self.apply_fen_edit).pack(side=tk.LEFT)
        ttk.Button(acoes, text="Salvar posição reconhecida", command=self.save_current).pack(side=tk.LEFT, padx=6)
        ttk.Button(acoes, text="Salvar todos", command=self.save_all).pack(side=tk.LEFT, padx=6)
        self.btn_correct_net = ttk.Button(acoes, text="Corrigir Net", command=self.correct_fen_with_net)
        self.btn_correct_net.pack(side=tk.LEFT, padx=6)

    # -------------------------------------------------------------------------------- zoom

    def zoom(self, delta: float) -> None:
        novo = max(0.45, min(1.8, self.board_zoom_var.get() + delta))
        self.board_zoom_var.set(novo)
        self.update_zoom_label()
        self.board.canvas.configure(height=int(520 * novo))
        self.board.redraw()

    def update_zoom_label(self) -> None:
        self.lbl_zoom.config(text=f"{int(self.board_zoom_var.get() * 100)}%")

    def set_ocr_controls_enabled(self, enabled: bool) -> None:
        estado = tk.NORMAL if enabled else tk.DISABLED
        self.btn_ocr_local_best.configure(state=estado)
        self.btn_ocr_local_all.configure(state=estado)

    def on_heatmap_toggle(self) -> None:
        self.board.set_heatmap_enabled(bool(self.heatmap_var.get()))
        self._on_state_changed()

    # ------------------------------------------------------------------ cache por página

    def remember_page_results(self) -> None:
        """Guarda o que está no editor no cache da página de onde ele veio.

        As listas vão **por referência**, então correção feita durante a edição já está no
        cache; o que precisa ser copiado é o índice selecionado, que é escalar.
        """
        if self.page_key is None or not self.items:
            return
        self.sync_fen_from_entry()
        documento, pagina = self.page_key
        self.page_results.put(
            documento,
            PageResults(
                page_index=pagina,
                params=self._ocr_params(),
                items=self.items,
                fen_edits=self.fen_edits,
                side_edits=self.side_edits,
                selected_index=self.selected_index,
            ),
        )

    def restore_results_for_page(self, page_index: int) -> None:
        """Traz de volta o reconhecimento da página, se houver, ao trocar de página."""
        documento = self._document_key()
        guardado = self.page_results.get(documento, page_index, self._ocr_params())
        acao = decide_page_switch(stored=guardado, current_is_page_result=self.page_key is not None)

        if acao is PageSwitch.RESTORE:
            assert guardado is not None
            self._apply_page_results(guardado, documento)
        elif acao is PageSwitch.CLEAR:
            self.page_key = None
            self.clear()
            self._on_status(f"Pagina {page_index}: sem reconhecimento ainda. Rode o OCR.")

    def _apply_page_results(self, guardado: PageResults, documento: str) -> None:
        self.editing_sample = None
        self.review_position = None
        self.items = guardado.items
        self.fen_edits = guardado.fen_edits
        self.side_edits = guardado.side_edits
        self.selected_index = guardado.clamped_index()
        self.page_key = (documento, guardado.page_index)

        self.selected_diag_var.set(self.selected_index + 1)
        self.spin_diag.config(from_=1, to=max(guardado.count, 1))
        self.fen_var.set(self.fen_edits[self.selected_index] if self.fen_edits else "")
        self.sync_side_widgets(self.selected_index)
        self.update_views()
        self.after_idle(self.board.redraw)
        self._on_status(
            f"Pagina {guardado.page_index}: {guardado.count} diagrama(s) do reconhecimento anterior"
            f"{', com correcoes suas' if guardado.has_hand_edits else ''}."
        )

    def discard_document_results(self, document: str) -> None:
        """Trocar de PDF invalida o cache: a chave é (documento, página)."""
        if self._document_key() != document:
            self.page_results.clear()
            self.page_key = None

    # ------------------------------------------------------------------- entrada de dados

    def show_ocr_results(self, items: list[RecognizedDiagram], origin: RecognitionOrigin) -> None:
        # OCR novo substitui o que estava no editor: se veio da fila ou do dataset, a
        # ligacao com aquele item deixa de valer.
        self.editing_sample = None
        self.review_position = None
        self.origin = origin
        self._load(items, [d.placement for d in items], [d.side_to_move for d in items])

        # So pagina inteira vai para o cache; recorte de area, nao -- guarda-lo como "o
        # resultado da pagina 16" devolveria dois diagramas onde a pagina tem nove.
        self.page_key = (
            (self._document_key(), origin.page_index)
            if origin.is_whole_page and origin.page_index is not None
            else None
        )
        self.remember_page_results()
        self._on_status(f"OCR pronto. Diagramas detectados: {len(items)} | origem: {origin}")

    def open_review_item(self, item: ReviewItem, position: int) -> None:
        """Abre um item da fila no editor, já na casa suspeita (S-22)."""
        board_rgb = read_board_image(item.board_image)
        if board_rgb is None:
            messagebox.showerror("Fila de revisao", f"Miniatura nao encontrada:\n{item.board_image}")
            return

        placement = item.fen.split(" ")[0]
        self.editing_sample = None
        self.review_position = position
        # O que entra aqui e um item da fila, nao o reconhecimento de uma pagina: guardar o
        # que estava antes e desligar o vinculo com a pagina, para que navegar depois nao
        # apague o item da fila nem o confunda com resultado de pagina.
        self.remember_page_results()
        self.page_key = None
        self.origin = None
        # A fila guarda as 64 confiancas, nao a matriz (64, 13) -- ela custaria ~5,6 MB por
        # livro em JSON (decisao da S-22). Entao vem heatmap, e nao o tooltip das 3 classes;
        # esse volta quando o usuario roda o OCR da pagina de novo.
        diagrama = RecognizedDiagram.from_label(
            board_rgb,
            placement,
            side_to_move=item.side_to_move,
            side_to_move_source="queue",
            side_to_move_reason="; ".join(item.reasons),
            min_confidence=item.min_confidence,
            mean_confidence=item.min_confidence,
            uncertain_squares=list(item.uncertain_squares),
            square_confidences=list(item.square_confidences),
            changed_squares=list(item.changed_squares),
        )
        self._load([diagrama], [placement], [item.side_to_move])

        if item.first_uncertain_square is not None:
            # Abrir ja na casa suspeita e o que a S-22 pede do "corrigir agora": sem isso o
            # usuario recebe o tabuleiro inteiro de novo e a fila nao economizou nada.
            self.board.select_square(item.first_uncertain_square)
        self._on_status(f"Revisao {item.label}: {'; '.join(item.reasons)}")

    def open_dataset_row(self, row: DatasetRow) -> None:
        """Abre uma amostra do dataset no editor. Salvar regrava a linha, não cria outra."""
        _csv, samples_dir = self._paths()
        board_rgb = read_board_image(str(row.image_path(samples_dir)))
        if board_rgb is None:
            messagebox.showerror("Dataset", f"Imagem nao encontrada:\n{row.image_path(samples_dir)}")
            return

        side = row.side_to_move if row.side_to_move in ("w", "b") else "w"
        self.editing_sample = row.filename
        self.review_position = None
        # Amostra do dataset: mesmo raciocinio do item da fila acima.
        self.remember_page_results()
        self.page_key = None
        self.origin = None

        diagrama = RecognizedDiagram.from_label(
            board_rgb,
            row.placement,
            side_to_move=side,
            side_to_move_source="manual",
            side_to_move_reason="rotulo do dataset",
            detection_source=row.detection_source,
        )
        # A legalidade sai da propria posicao rotulada, e nao das colunas do CSV: o rotulo
        # foi gravado com um lado a jogar, e e com ele que a checagem tem de bater (S-17).
        diagrama.resolve_legality()
        self._load([diagrama], [row.placement], [side])
        self._on_status(f"Editando amostra {row.filename} (Ctrl+S regrava o rotulo).")

    def _load(self, items: list[RecognizedDiagram], fens: list[str], sides: list[str]) -> None:
        self.items = items
        self.fen_edits = fens
        self.side_edits = sides
        self.selected_index = 0
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=max(len(items), 1))
        self.fen_var.set(fens[0] if fens else "")
        self.sync_side_widgets(0)
        self._on_focus_request()
        self.update_views()
        self.after_idle(self.board.redraw)

    def clear(self) -> None:
        self.items = []
        self.fen_edits = []
        self.side_edits = []
        self.selected_index = 0
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=1)
        self.fen_var.set("")
        self.side_to_move_var.set("w")
        self.side_source_var.set("")
        self.update_views()

    # -------------------------------------------------------------------------- navegação

    def clamped_index(self) -> int:
        if not self.items:
            return 0
        return max(0, min(self.selected_index, len(self.items) - 1))

    def sync_fen_from_entry(self) -> None:
        if not self.items:
            return
        self.fen_edits[self.clamped_index()] = self.fen_var.get().strip()

    def on_diagram_spin(self) -> None:
        self.sync_fen_from_entry()
        if self.items:
            try:
                pedido = int(self.selected_diag_var.get()) - 1
            except (ValueError, tk.TclError):
                # Campo vazio ou nao numerico: mantem a selecao atual.
                pedido = self.selected_index
            self.selected_index = max(0, min(pedido, len(self.items) - 1))
        self.selected_diag_var.set(self.selected_index + 1)
        self.refresh_selected()

    def prev_diagram(self) -> None:
        if not self.items:
            return
        self.sync_fen_from_entry()
        self.selected_index = max(0, self.selected_index - 1)
        self.selected_diag_var.set(self.selected_index + 1)
        self.refresh_selected()

    def next_diagram(self) -> None:
        if not self.items:
            return
        self.sync_fen_from_entry()
        self.selected_index = min(len(self.items) - 1, self.selected_index + 1)
        self.selected_diag_var.set(self.selected_index + 1)
        self.refresh_selected()

    def refresh_selected(self) -> None:
        if not self.items:
            return
        idx = self.clamped_index()
        self.selected_index = idx
        self.selected_diag_var.set(idx + 1)
        self.fen_var.set(self.fen_edits[idx])
        self.sync_side_widgets(idx)
        self._on_status(f"Diagrama {idx + 1}/{len(self.items)} | {confidence_summary(self.items[idx])}")
        self.update_views()

    # ------------------------------------------------------------------------ apresentação

    def sync_side_widgets(self, idx: int) -> None:
        if not self.items or idx < 0 or idx >= len(self.side_edits):
            self.side_source_var.set("")
            return
        self.side_to_move_var.set(self.side_edits[idx])
        self.side_source_var.set(side_source_label(self.items[idx]))

    def apply_fen_edit(self) -> None:
        if not self.items:
            return
        self.sync_fen_from_entry()
        self.update_views()

    def update_views(self) -> None:
        if not self.items:
            self.board.set_position(board_edit.EMPTY_PLACEMENT)
            self.board.set_uncertainty(None)
            self.board.set_probabilities(None)
            self.board.set_changed_squares(())
            self.board.set_problem_squares(())
            self.legality_var.set("")
            self.material_var.set("")
            return

        idx = self.clamped_index()
        item = self.items[idx]
        self.board.set_position(self.fen_edits[idx])
        self.board.set_side_to_move(self.side_edits[idx] != "b")
        # Sem estes tres sinais o usuario so tem a FEN e um numero agregado -- e a media de
        # confianca fica em 0,97 mesmo com erro (S-10), entao ela nao aponta lugar nenhum.
        self.board.set_uncertainty(list(item.square_confidences) or None)
        self.board.set_probabilities(item.probs)
        self.board.set_changed_squares(item.changed_squares)
        self.update_legality()
        self._on_sync_study()

    def update_legality(self) -> None:
        """Painel de legalidade da S-21: o problema em pt-BR e as casas que o causam."""
        idx = self.clamped_index()
        if not self.items or idx >= len(self.fen_edits):
            return

        side = self.side_edits[idx] if idx < len(self.side_edits) else "w"
        explicacao = explain_position(compose_fen(self.board.placement, side == "w"))
        self.legality_var.set(explicacao.summary())
        self.material_var.set(explicacao.material_line())
        self.board.set_problem_squares(explicacao.highlight_squares)

    # ------------------------------------------------------------------------------ edição

    def on_side_to_move_change(self) -> None:
        if not self.items:
            return
        idx = self.clamped_index()
        if not (0 <= idx < len(self.side_edits)):
            return
        self.side_edits[idx] = self.side_to_move_var.get()
        self.items[idx].set_side_to_move(self.side_to_move_var.get())
        self.sync_side_widgets(idx)
        self.board.set_side_to_move(self.side_edits[idx] != "b")
        # A legalidade depende de quem joga: trocar a vez pode resolver o "xeque invertido"
        # sem mexer em nenhuma peca (S-17).
        self.update_legality()
        self._on_status(f"Diagrama {idx + 1}: lado a jogar definido como {self.side_to_move_var.get()}.")

    def on_board_changed(self, placement: str) -> None:
        """Toda edição no tabuleiro reescreve a FEN -- o campo de texto segue funcionando."""
        idx = self.clamped_index()
        if not self.items or idx >= len(self.fen_edits):
            return
        self.fen_edits[idx] = placement
        self.fen_var.set(placement)
        self.items[idx].edited_by_hand = True
        self.update_legality()
        self._on_sync_study()

    def on_square_selected(self, index: int | None) -> None:
        if index is None:
            return
        top = self.board.top_classes(index)
        if not top:
            self._on_status(f"Casa {square_name(index)} selecionada.")
            return
        self._on_status(f"Casa {square_name(index)}: " + ", ".join(f"{n} {v:.1%}" for n, v in top))

    def delete_selected_square(self) -> None:
        if self.board.delete_selected():
            return
        self._on_status("Selecione uma casa do tabuleiro para apagar a peca.")

    # --------------------------------------------------------------------------- gravação

    def set_review_settler(self, settler: Callable[[int, str, str], None] | None) -> None:
        """Como devolver a correção à fila. Injetado para não depender do painel de revisão."""
        self._settle_review = settler

    def _save_one(self, idx: int, fen: str) -> Path:
        csv_path, samples_dir = self._paths()
        return self._service.save_sample(
            self.items[idx],
            fen,
            csv_path=csv_path,
            samples_dir=samples_dir,
            origin=self.origin,
            side_to_move=self.side_edits[idx] if 0 <= idx < len(self.side_edits) else None,
        )

    def save_current(self) -> None:
        if not self.items:
            messagebox.showwarning("Aviso", "Nao ha OCR para salvar.")
            return
        self.sync_fen_from_entry()
        idx = self.clamped_index()
        fen = self.fen_edits[idx]
        if not is_valid_fen(fen):
            messagebox.showerror("Erro", "FEN atual invalida.")
            return

        # Amostra vinda da aba Dataset regrava a linha que ja existe; salvar de novo criaria
        # uma segunda amostra da mesma imagem e o rotulo errado continuaria no arquivo (S-23).
        if self.editing_sample is not None:
            self._rewrite_dataset_row(idx, fen)
            return

        try:
            path = self._save_one(idx, fen)
            self._on_status(f"Exemplo salvo: {path}")
            self._settle(idx)
            messagebox.showinfo("Sucesso", f"Diagrama salvo em:\n{path}")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar:\n{exc}")

    def _rewrite_dataset_row(self, idx: int, fen: str) -> None:
        filename = self.editing_sample or ""
        csv_path, _samples = self._paths()
        side = self.side_edits[idx] if idx < len(self.side_edits) else "w"
        try:
            atualizado = update_row(csv_path, filename, fen=fen, side_to_move=side, corrected_by="tkinter")
        except ValueError as exc:
            messagebox.showerror("Dataset", str(exc))
            return

        if not atualizado:
            messagebox.showerror("Dataset", f"Amostra nao encontrada no CSV: {filename}")
            return

        self._on_status(f"Rotulo de {filename} regravado.")
        self._on_sample_saved()
        messagebox.showinfo("Dataset", f"Rotulo regravado:\n{filename}")

    def _settle(self, idx: int) -> None:
        """Fecha na fila o item que acabou de ser corrigido e salvo (S-22)."""
        if self._settle_review is None or self.review_position is None:
            return
        self._settle_review(
            self.review_position,
            self.fen_edits[idx],
            self.side_edits[idx] if idx < len(self.side_edits) else "w",
        )
        self.review_position = None

    def save_all(self) -> None:
        if not self.items:
            messagebox.showwarning("Aviso", "Nao ha OCR para salvar.")
            return
        self.sync_fen_from_entry()
        salvos = 0
        invalidos = 0
        for idx in range(len(self.items)):
            if not is_valid_fen(self.fen_edits[idx]):
                invalidos += 1
                continue
            self._save_one(idx, self.fen_edits[idx])
            salvos += 1
        self._on_status(f"Salvar todos: {salvos} salvos, {invalidos} invalidos.")
        messagebox.showinfo("Salvar todos", f"Salvos: {salvos}\nInvalidos: {invalidos}")

    # ------------------------------------------------------------------------ Corrigir Net

    def correct_fen_with_net(self) -> None:
        """Segunda opinião de um serviço externo. **Envia a imagem para fora da máquina.**"""
        if not self.items:
            messagebox.showwarning("Aviso", "Nao ha OCR para corrigir.")
            return
        if self._is_correcting_net:
            return

        idx = self.clamped_index()
        self._is_correcting_net = True
        self.btn_correct_net.configure(state=tk.DISABLED)
        self._on_status("Corrigindo FEN via Net...")
        threading.Thread(
            target=self._net_worker,
            args=(idx, np.asarray(self.items[idx].board_rgb).copy()),
            daemon=True,
        ).start()

    def _net_worker(self, idx: int, board_rgb: np.ndarray) -> None:
        try:
            fen = predict_fen_via_net(board_rgb)
            if not is_valid_fen(fen):
                raise ValueError("API retornou FEN invalida.")
            self.after(0, partial(self._apply_corrected_fen, idx, fen))
        except Exception as exc:
            self.after(0, partial(self._on_net_error, exc))
        finally:
            self.after(0, self._finish_net)

    def _finish_net(self) -> None:
        self._is_correcting_net = False
        self.btn_correct_net.configure(state=tk.NORMAL)

    def _on_net_error(self, exc: Exception) -> None:
        self._on_status("Falha ao corrigir com Net.")
        messagebox.showerror("Corrigir Net", f"Nao foi possivel corrigir o FEN:\n{exc}")

    def _apply_corrected_fen(self, idx: int, fen: str) -> None:
        if idx < 0 or idx >= len(self.fen_edits):
            self._on_status("Correcao recebida, mas o OCR atual mudou.")
            return
        self.fen_edits[idx] = fen
        if idx == self.clamped_index():
            self.fen_var.set(fen)
            self.update_views()
        self._on_status(f"FEN corrigida via Net (diagrama {idx + 1}).")
