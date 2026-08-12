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
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np

from chess_diagram_ocr.dataset_browser import DatasetRow, update_row
from chess_diagram_ocr.fen_utils import is_valid_fen, square_name
from chess_diagram_ocr.review_queue import ReviewItem
from chess_diagram_ocr.semantics import compose_fen
from chess_diagram_ocr.service import OcrService, RecognitionOrigin, RecognizedDiagram
from chess_diagram_ocr.settings import LocalReaderSettings, RemoteFenSettings

from . import board_edit, strings
from .board_widget import InteractiveBoard, PieceImages
from .editor_model import DiagramEditorModel, EditorBinding, SaveKind, SaveTarget
from .legality import explain_position
from .net_button import NetCorrectionButton
from .page_results import PageOcrParams, PageResults, PageResultsCache, PageSwitch, decide_page_switch
from .second_opinion_button import SecondOpinionButton

logger = logging.getLogger(__name__)

def confidence_summary(item: RecognizedDiagram) -> str:
    """Resumo de confiança e legalidade do diagrama, para a barra de status.

    Sem Tk, e testável. A ordem é a decisão: o **mínimo** por casa vem antes da média porque
    a média fica em ~0,97 mesmo em tabuleiro com erro (S-10), e a orientação vem antes de
    tudo porque, se o diagrama está de cabeça para baixo, conferir casa por casa é perda de
    tempo (S-13).
    """
    partes = [f"conf min {item.min_confidence:.3f}", f"média {item.mean_confidence:.3f}"]

    if item.orientation_ambiguous:
        partes.append(f"ORIENTAÇÃO INCERTA ({item.orientation_reason or 'as duas eram plausíveis'})")
    elif item.rotation:
        partes.append(f"lido a {item.rotation} graus")

    if item.uncertain_squares:
        nomes = ", ".join(square_name(casa) for casa in item.uncertain_squares[:4])
        sufixo = f" +{len(item.uncertain_squares) - 4}" if len(item.uncertain_squares) > 4 else ""
        partes.append(f"casas inseguras: {nomes}{sufixo}")

    if item.is_legal is False:
        detalhe = f" ({'; '.join(item.problems)})" if item.problems else ""
        # "Xeque invertido" não e erro de leitura: o diagrama não diz de quem e a vez e o
        # app assume brancas. Chamar isso de ILEGAL manda o usuário procurar um erro que
        # não existe no tabuleiro.
        partes.append(("LADO A JOGAR" if item.is_fatal is False else "ILEGAL") + detalhe)

    return " | ".join(partes)


def side_source_label(item: RecognizedDiagram) -> str:
    """Texto entre parênteses ao lado do rádio de lado a jogar.

    O vocabulário vem de `ui/strings.py` porque o Streamlit mostra o mesmo, e as duas
    versões já tinham divergido em quatro dos cinco rótulos (S-04).
    """
    fonte = strings.side_source_label(item.side_to_move_source, conflicting=item.side_conflicting)
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
        remote_fen: Callable[[], RemoteFenSettings],
        on_remote_consent: Callable[[RemoteFenSettings], bool],
        local_reader: Callable[[], LocalReaderSettings] = LocalReaderSettings,
        on_selection_changed: Callable[[int | None], None] = lambda _indice: None,
        move_number_of: Callable[[int, int], int | None] = lambda _pagina, _diagrama: None,
        on_move_number: Callable[[int, int, int | None], None] = lambda _p, _d, _v: None,
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

        self._remote_fen = remote_fen
        self._local_reader = local_reader
        """Segundo leitor local (S-66). Padrão `LocalReaderSettings`, que sai desligado: quem
        constrói o painel sem passar nada tem o botão cinza, não uma leitura inesperada."""

        self._on_selection_changed = on_selection_changed
        """Qual diagrama está aberto agora, em base 0, ou `None` quando não há nenhum.

        É o vínculo de volta para o visualizador (S-68): o retângulo destacado na página é o
        diagrama que está neste editor. Mão única, como o da aba Análise -- o painel avisa e
        não pergunta nada, para que quem escuta possa ignorar sem quebrar o editor."""

        self._move_number_of = move_number_of
        self._on_move_number = on_move_number
        """Leitura e gravação do número do lance, por (página, diagrama) (S-71).

        Moram fora porque o dono da anotação é a aba Galeria: ela já edita o mesmo campo, do
        mesmo diagrama, no mesmo arquivo. Duas cópias em memória do `data/gallery/<livro>.json`
        divergiriam, e a última a gravar apagaria o que a outra tivesse escrito."""

        self._on_remote_consent = on_remote_consent
        """Pergunta ao usuário se a imagem pode sair da máquina, e devolve a resposta.

        Mora fora do painel porque a resposta afirmativa com "não perguntar novamente" tem
        de ser **gravada** nas preferências, e persistência não é assunto de widget."""

        self.model = DiagramEditorModel()
        """As três listas paralelas, o índice e o vínculo (S-49).

        Este painel não guarda mais estado de edição: ele observa o modelo e desenha. Os
        atributos antigos continuam legíveis como propriedades, porque o roteiro headless e
        o resto da janela os usam por nome."""

        self.page_results = PageResultsCache()

        self.fen_var = tk.StringVar(value="")
        self.side_to_move_var = tk.StringVar(value="w")
        self.side_source_var = tk.StringVar(value="")
        self.selected_diag_var = tk.IntVar(value=1)
        self.move_number_var = tk.StringVar(value="")
        """O número do lance do diagrama selecionado, como texto -- vazio é "não declarado"."""

        self.legality_var = tk.StringVar(value="")
        self.material_var = tk.StringVar(value="")
        self.heatmap_var = tk.BooleanVar(value=True)
        self.board_zoom_var = tk.DoubleVar(value=0.85)

        self._settle_review: Callable[[int, str, str], None] | None = None

        self._build(piece_images)

    # ------------------------------------------------------- o estado, que mora no modelo

    @property
    def items(self) -> list[RecognizedDiagram]:
        return self.model.items

    @property
    def fen_edits(self) -> list[str]:
        return self.model.fen_edits

    @property
    def side_edits(self) -> list[str]:
        return self.model.side_edits

    @property
    def selected_index(self) -> int:
        return self.model.clamped_index()

    @property
    def page_key(self) -> tuple[str, int] | None:
        return self.model.page_key

    @property
    def review_position(self) -> int | None:
        return self.model.review_position

    @property
    def editing_sample(self) -> str | None:
        return self.model.editing_sample

    @property
    def origin(self) -> RecognitionOrigin | None:
        return self.model.origin

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

        # O editor da S-20 no lugar do canvas somente-leitura: corrigir uma peça passa de
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
        ttk.Button(nav, text="Próximo diagrama", command=self.next_diagram).pack(side=tk.LEFT, padx=6)
        ttk.Label(nav, text="Selecionado").pack(side=tk.LEFT, padx=(12, 4))
        self.spin_diag = ttk.Spinbox(
            nav, from_=1, to=1, textvariable=self.selected_diag_var, width=6, command=self.on_diagram_spin
        )
        self.spin_diag.pack(side=tk.LEFT)
        self.spin_diag.bind("<Return>", lambda _event: self.on_diagram_spin())
        self.spin_diag.bind("<FocusOut>", lambda _event: self.on_diagram_spin())

        fen_box = ttk.LabelFrame(self, text="FEN e ações")
        fen_box.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(fen_box, text="FEN").pack(anchor="w", padx=8, pady=(6, 0))
        entry = ttk.Entry(fen_box, textvariable=self.fen_var)
        entry.pack(fill=tk.X, padx=8, pady=(0, 4))
        entry.bind("<Return>", lambda _event: self.apply_fen_edit())

        # Lado a jogar visivel e editavel (S-16/S-19). Até a Fase 3 o app não tinha onde
        # mostrar isso, e a informação -- quando o PDF a dava -- morria na exportação.
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

        # Número do lance (S-71), ao lado do lado a jogar porque é a mesma leitura: os dois
        # saem da legenda impressa, e quem está com o livro aberto declara os dois de uma vez.
        # A gravação vai para a anotação da galeria -- ver `_commit_move_number`.
        ttk.Label(side_row, text="Lance").pack(side=tk.RIGHT, padx=(0, 4))
        self.move_number_entry = ttk.Entry(side_row, textvariable=self.move_number_var, width=6)
        self.move_number_entry.pack(side=tk.RIGHT)
        self.move_number_entry.bind("<Return>", lambda _event: self._commit_move_number())
        self.move_number_entry.bind("<FocusOut>", lambda _event: self._commit_move_number())

        acoes = ttk.Frame(fen_box)
        acoes.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(acoes, text="Aplicar FEN", command=self.apply_fen_edit).pack(side=tk.LEFT)
        ttk.Button(acoes, text="Salvar posição reconhecida", command=self.save_current).pack(side=tk.LEFT, padx=6)
        ttk.Button(acoes, text="Salvar todos", command=self.save_all).pack(side=tk.LEFT, padx=6)
        self.net_button = NetCorrectionButton(
            acoes,
            settings=self._remote_fen,
            board_image=self._selected_board_image,
            on_status=self._on_status,
            on_consent=self._on_remote_consent,
            on_corrected=self._apply_corrected_fen,
            schedule=self.after,
        )
        self.net_button.pack(side=tk.LEFT, padx=6)
        self.second_opinion_button = SecondOpinionButton(
            acoes,
            settings=self._local_reader,
            board_image=self._selected_board_image,
            on_status=self._on_status,
            on_read=self._apply_second_opinion,
            schedule=self.after,
        )
        self.second_opinion_button.pack(side=tk.LEFT, padx=6)
        # Editor vazio não tem diagrama a que atribuir lance: o campo nasce cinza, e não
        # aceitando um número que seria descartado em silêncio.
        self.sync_move_number()

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
        if self.model.page_key is None or not self.model.items:
            return
        self.sync_fen_from_entry()
        documento, pagina = self.model.page_key
        self.page_results.put(
            documento,
            PageResults(
                page_index=pagina,
                params=self._ocr_params(),
                items=self.model.items,
                fen_edits=self.model.fen_edits,
                side_edits=self.model.side_edits,
                selected_index=self.model.clamped_index(),
            ),
        )

    def restore_results_for_page(self, page_index: int) -> None:
        """Traz de volta o reconhecimento da página, se houver, ao trocar de página."""
        documento = self._document_key()
        guardado = self.page_results.get(documento, page_index, self._ocr_params())
        acao = decide_page_switch(stored=guardado, current_is_page_result=self.model.page_key is not None)

        if acao is PageSwitch.RESTORE:
            assert guardado is not None
            self._apply_page_results(guardado, documento)
        elif acao is PageSwitch.CLEAR:
            self.clear()
            self._on_status(f"Página {page_index}: sem reconhecimento ainda. Rode o OCR.")

    def _apply_page_results(self, guardado: PageResults, documento: str) -> None:
        self.model.adopt(
            guardado.items,
            guardado.fen_edits,
            guardado.side_edits,
            page_key=(documento, guardado.page_index),
            selected=guardado.clamped_index(),
        )
        self._sync_widgets_to_model(total=max(guardado.count, 1))
        self.after_idle(self.board.redraw)
        self._on_status(
            f"Página {guardado.page_index}: {guardado.count} diagrama(s) do reconhecimento anterior"
            f"{', com correções suas' if guardado.has_hand_edits else ''}."
        )

    def discard_document_results(self, document: str) -> None:
        """Trocar de PDF inválida o cache: a chave é (documento, página)."""
        if self._document_key() != document:
            self.page_results.clear()
            self.model.unbind_page()

    # ------------------------------------------------------------------- entrada de dados

    def show_ocr_results(self, items: list[RecognizedDiagram], origin: RecognitionOrigin) -> None:
        # OCR novo substitui o que estava no editor: se veio da fila ou do dataset, a
        # ligacao com aquele item deixa de valer -- e quem garante isso agora e o `load` do
        # modelo, que e o ponto unico de troca de vinculo.
        #
        # So página inteira vai para o cache; recorte de área, não -- guarda-lo como "o
        # resultado da página 16" devolveria dois diagramas onde a página tem nove.
        de_pagina = origin.is_whole_page and origin.page_index is not None
        page_key = (self._document_key(), origin.page_index) if de_pagina else None
        self.model.load(
            items,
            binding=EditorBinding.PAGE if page_key else EditorBinding.NONE,
            page_key=page_key,  # type: ignore[arg-type]
            origin=origin,
        )
        self._after_load()
        self.remember_page_results()
        self._on_status(f"OCR pronto. Diagramas detectados: {len(items)} | origem: {origin}")

    def open_review_item(self, item: ReviewItem, position: int) -> None:
        """Abre um item da fila no editor, já na casa suspeita (S-22)."""
        board_rgb = read_board_image(item.board_image)
        if board_rgb is None:
            messagebox.showerror("Fila de revisão", f"Miniatura não encontrada:\n{item.board_image}")
            return

        placement = item.fen.split(" ")[0]
        # O que entra aqui e um item da fila, não o reconhecimento de uma página: guardar o
        # que estava antes, para que navegar depois não apague o item da fila nem o confunda
        # com resultado de página. Desligar o vinculo e o `load` abaixo que faz.
        self.remember_page_results()
        # A fila guarda as 64 confianças, não a matriz (64, 13) -- ela custaria ~5,6 MB por
        # livro em JSON (decisão da S-22). Então vem heatmap, e não o tooltip das 3 classes;
        # esse volta quando o usuário roda o OCR da página de novo.
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
        self.model.load(
            [diagrama], [placement], [item.side_to_move],
            binding=EditorBinding.REVIEW,
            review_position=position,
        )
        self._after_load()

        if item.first_uncertain_square is not None:
            # Abrir já na casa suspeita e o que a S-22 pede do "corrigir agora": sem isso o
            # usuário recebe o tabuleiro inteiro de novo e a fila não economizou nada.
            self.board.select_square(item.first_uncertain_square)
        self._on_status(f"Revisão {item.label}: {'; '.join(item.reasons)}")

    def open_dataset_row(self, row: DatasetRow) -> None:
        """Abre uma amostra do dataset no editor. Salvar regrava a linha, não cria outra."""
        _csv, samples_dir = self._paths()
        board_rgb = read_board_image(str(row.image_path(samples_dir)))
        if board_rgb is None:
            messagebox.showerror("Dataset", f"Imagem não encontrada:\n{row.image_path(samples_dir)}")
            return

        side = row.side_to_move if row.side_to_move in ("w", "b") else "w"
        # Amostra do dataset: mesmo raciocinio do item da fila acima.
        self.remember_page_results()

        diagrama = RecognizedDiagram.from_label(
            board_rgb,
            row.placement,
            side_to_move=side,
            side_to_move_source="manual",
            side_to_move_reason="rotulo do dataset",
            detection_source=row.detection_source,
        )
        # A legalidade sai da própria posição rotulada, e não das colunas do CSV: o rotulo
        # foi gravado com um lado a jogar, e e com ele que a checagem tem de bater (S-17).
        diagrama.resolve_legality()
        self.model.load(
            [diagrama], [row.placement], [side],
            binding=EditorBinding.SAMPLE,
            editing_sample=row.filename,
        )
        self._after_load()
        self._on_status(f"Editando amostra {row.filename} (Ctrl+S regrava o rotulo).")

    def _after_load(self) -> None:
        """Põe os widgets no estado que o modelo acabou de assumir, e pede o foco."""
        self._sync_widgets_to_model(total=max(self.model.count, 1))
        self._on_focus_request()
        self.after_idle(self.board.redraw)

    def _sync_widgets_to_model(self, *, total: int) -> None:
        idx = self.model.clamped_index()
        self.selected_diag_var.set(idx + 1)
        self.spin_diag.config(from_=1, to=total)
        self.fen_var.set(self.model.fen_at(idx))
        self.sync_side_widgets(idx)
        self.sync_move_number()
        self.update_views()
        self._on_selection_changed(idx if self.model.items else None)

    def clear(self) -> None:
        self.model.clear()
        self.selected_diag_var.set(1)
        self.spin_diag.config(from_=1, to=1)
        self.fen_var.set("")
        self.side_to_move_var.set("w")
        self.side_source_var.set("")
        self.sync_move_number()
        self.update_views()
        self._on_selection_changed(None)

    # -------------------------------------------------------------------------- navegação

    def clamped_index(self) -> int:
        return self.model.clamped_index()

    def sync_fen_from_entry(self) -> None:
        """Recolhe o que está nos campos antes de a seleção mudar ou de salvar.

        O número do lance entra aqui, e não só no `FocusOut`: trocar de diagrama pelo botão
        "Próximo" com o foco ainda no campo de FEN não dispara o `FocusOut` do campo de lance,
        e o que a pessoa digitou iria embora sem aviso.
        """
        self.model.set_fen(self.fen_var.get())
        self._commit_move_number()

    def on_diagram_spin(self) -> None:
        self.sync_fen_from_entry()
        try:
            pedido = int(self.selected_diag_var.get()) - 1
        except (ValueError, tk.TclError):
            # Campo vazio ou não numerico: mantem a seleção atual.
            pedido = self.model.selected
        self.model.select(pedido)
        self.selected_diag_var.set(self.model.clamped_index() + 1)
        self.refresh_selected()

    # ---------------------------------------------------------------- número do lance (S-71)

    def _move_number_target(self) -> tuple[int, int] | None:
        """(página, diagrama) do que está no editor, ou `None` se não é resultado de página.

        Item da fila e amostra do dataset não têm par: a anotação é do diagrama **daquele
        livro naquela página**, e uma amostra solta do `labels.csv` não sabe mais de onde veio
        com essa precisão. Ali o campo fica cinza, em vez de gravar no diagrama errado.
        """
        if self.model.page_key is None or not self.model.items:
            return None
        return (self.model.page_key[1], self.model.clamped_index())

    def sync_move_number(self) -> None:
        """Traz para o campo o lance do diagrama selecionado."""
        alvo = self._move_number_target()
        if alvo is None:
            self.move_number_var.set("")
            self.move_number_entry.configure(state=tk.DISABLED)
            return
        self.move_number_entry.configure(state=tk.NORMAL)
        numero = self._move_number_of(*alvo)
        self.move_number_var.set("" if numero is None else str(numero))

    def _commit_move_number(self) -> None:
        """Grava o que está no campo. Em branco **apaga** a declaração.

        Só grava quando o valor muda de fato: o campo confirma no `FocusOut`, que dispara a
        cada passagem do foco, e regravar o mesmo número reescreveria o JSON do livro inteiro
        a cada clique fora do campo.
        """
        alvo = self._move_number_target()
        if alvo is None:
            return

        texto = self.move_number_var.get().strip()
        atual = self._move_number_of(*alvo)
        if not texto:
            if atual is not None:
                self._on_move_number(alvo[0], alvo[1], None)
                self._on_status(f"Diagrama {alvo[1] + 1}: número do lance apagado.")
            return

        try:
            numero = int(texto)
        except ValueError:
            self._on_status(f"Número de lance inválido: {texto!r}. Use um inteiro positivo.")
            self.sync_move_number()
            return
        if numero <= 0:
            self._on_status(f"Número de lance inválido: {numero}. Use um inteiro positivo.")
            self.sync_move_number()
            return
        if numero == atual:
            return
        self._on_move_number(alvo[0], alvo[1], numero)
        self._on_status(f"Diagrama {alvo[1] + 1}: lance {numero}.")

    def select_diagram(self, index: int) -> None:
        """Seleciona um diagrama a pedido de fora -- o clique no diagrama marcado (S-68).

        Passa pelo mesmo caminho do seletor "Selecionado", inclusive o `sync_fen_from_entry`:
        clicar no visualizador com uma FEN pela metade no campo não pode ser um jeito de perder
        o que já estava digitado.
        """
        if not self.model.items:
            return
        self.sync_fen_from_entry()
        self.model.select(index)
        self.refresh_selected()

    def prev_diagram(self) -> None:
        self._step_diagram(-1)

    def next_diagram(self) -> None:
        self._step_diagram(+1)

    def _step_diagram(self, delta: int) -> None:
        if not self.model.items:
            return
        self.sync_fen_from_entry()
        self.selected_diag_var.set(self.model.step(delta) + 1)
        self.refresh_selected()

    def refresh_selected(self) -> None:
        if not self.model.items:
            return
        idx = self.model.clamped_index()
        self.selected_diag_var.set(idx + 1)
        self.fen_var.set(self.model.fen_at(idx))
        self.sync_side_widgets(idx)
        self.sync_move_number()
        self._on_status(f"Diagrama {idx + 1}/{self.model.count} | {confidence_summary(self.model.items[idx])}")
        self.update_views()
        self._on_selection_changed(idx)

    # ------------------------------------------------------------------------ apresentação

    def sync_side_widgets(self, idx: int) -> None:
        if not self.model.items or idx < 0 or idx >= len(self.model.side_edits):
            self.side_source_var.set("")
            return
        self.side_to_move_var.set(self.model.side_edits[idx])
        self.side_source_var.set(side_source_label(self.model.items[idx]))

    def apply_fen_edit(self) -> None:
        if not self.model.items:
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
            self.board.set_disputed_squares(())
            self.legality_var.set("")
            self.material_var.set("")
            return

        idx = self.clamped_index()
        item = self.items[idx]
        self.board.set_position(self.fen_edits[idx])
        self.board.set_side_to_move(self.side_edits[idx] != "b")
        # Sem estes três sinais o usuário só tem a FEN e um número agregado -- e a media de
        # confiança fica em 0,97 mesmo com erro (S-10), então ela não aponta lugar nenhum.
        self.board.set_uncertainty(list(item.square_confidences) or None)
        self.board.set_probabilities(item.probs)
        self.board.set_changed_squares(item.changed_squares)
        self.board.set_disputed_squares(self.model.disputed_squares(idx))
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
        lado = self.side_to_move_var.get()
        if not self.model.set_side(lado):
            return
        idx = self.model.clamped_index()
        self.sync_side_widgets(idx)
        self.board.set_side_to_move(lado != "b")
        # A legalidade depende de quem joga: trocar a vez pode resolver o "xeque invertido"
        # sem mexer em nenhuma peça (S-17).
        self.update_legality()
        self._on_status(f"Diagrama {idx + 1}: lado a jogar definido como {lado}.")

    def on_board_changed(self, placement: str) -> None:
        """Toda edição no tabuleiro reescreve a FEN -- o campo de texto segue funcionando."""
        if not self.model.apply_placement(placement):
            return
        self.fen_var.set(placement)
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
        self._on_status("Selecione uma casa do tabuleiro para apagar a peça.")

    # --------------------------------------------------------------------------- gravação

    def set_review_settler(self, settler: Callable[[int, str, str], None] | None) -> None:
        """Como devolver a correção à fila. Injetado para não depender do painel de revisão."""
        self._settle_review = settler

    def _save_one(self, alvo: SaveTarget) -> Path:
        csv_path, samples_dir = self._paths()
        return self._service.save_sample(
            self.model.items[alvo.index],
            alvo.fen,
            csv_path=csv_path,
            samples_dir=samples_dir,
            origin=self.model.origin,
            side_to_move=alvo.side,
            corrected_by=alvo.route,
        )

    def save_current(self) -> None:
        """Salva o diagrama selecionado. **O que "salvar" significa é decisão do modelo.**

        Este método executa o que `save_target()` mandou e cuida das caixas de diálogo; a
        regra -- amostra nova, regravar a linha do dataset, fechar item da fila -- mora em
        `DiagramEditorModel` e tem teste sem janela (S-49).
        """
        if not self.model.items:
            messagebox.showwarning("Aviso", "Não ha OCR para salvar.")
            return
        self.sync_fen_from_entry()
        alvo = self.model.save_target()
        if not is_valid_fen(alvo.fen):
            messagebox.showerror("Erro", "FEN atual inválida.")
            return

        if alvo.kind is SaveKind.REWRITE_ROW:
            self._rewrite_dataset_row(alvo)
            return

        try:
            path = self._save_one(alvo)
            self._on_status(f"Exemplo salvo: {path}")
            self._settle(alvo)
            # Só o caminho de regravação avisava. Sem isto, a aba Dataset não via a amostra
            # nova e o visualizador não pintava de verde o diagrama que acabou de ser salvo
            # (S-71) -- os dois só se atualizavam na próxima vez que o livro fosse aberto.
            self._on_sample_saved()
            messagebox.showinfo("Sucesso", f"Diagrama salvo em:\n{path}")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar:\n{exc}")

    def _rewrite_dataset_row(self, alvo: SaveTarget) -> None:
        filename = alvo.filename or ""
        csv_path, _samples = self._paths()
        try:
            atualizado = update_row(
                csv_path, filename, fen=alvo.fen, side_to_move=alvo.side, corrected_by=alvo.route
            )
        except ValueError as exc:
            messagebox.showerror("Dataset", str(exc))
            return

        if not atualizado:
            messagebox.showerror("Dataset", f"Amostra não encontrada no CSV: {filename}")
            return

        self._on_status(f"Rotulo de {filename} regravado.")
        self._on_sample_saved()
        messagebox.showinfo("Dataset", f"Rotulo regravado:\n{filename}")

    def _settle(self, alvo: SaveTarget) -> None:
        """Fecha na fila o item que acabou de ser corrigido e salvo (S-22)."""
        if self._settle_review is None or alvo.settle_position is None:
            return
        self._settle_review(alvo.settle_position, alvo.fen, alvo.side)
        self.model.settled()

    def save_all(self) -> None:
        if not self.model.items:
            messagebox.showwarning("Aviso", "Não ha OCR para salvar.")
            return
        self.sync_fen_from_entry()
        if self.model.binding is EditorBinding.SAMPLE:
            # Uma amostra do dataset e um item so, e "salvar todos" sobre ela e "salvar".
            # Criar amostra nova por este caminho era o defeito que a S-23 fechou no `Ctrl+S`
            # e que continuava aberto aqui, porque `save_all` nunca olhou o vinculo.
            self.save_current()
            return

        salvos = 0
        invalidos = 0
        for idx in range(self.model.count):
            alvo = self.model.save_target(idx)
            if alvo.kind is SaveKind.NOTHING or not is_valid_fen(alvo.fen):
                invalidos += 1
                continue
            self._save_one(alvo)
            salvos += 1
        self._on_status(f"Salvar todos: {salvos} salvos, {invalidos} inválidos.")
        messagebox.showinfo("Salvar todos", f"Salvos: {salvos}\nInválidos: {invalidos}")

    # ------------------------------------------------------------------------ Corrigir Net

    def refresh_remote_availability(self) -> None:
        """Reavalia os dois botões de segunda leitura depois de as preferências mudarem."""
        self.net_button.refresh()
        self.second_opinion_button.refresh()

    def correct_fen_with_net(self) -> None:
        """Atalho de teclado e roteiro headless entram por aqui; a lógica é do botão."""
        self.net_button.correct()

    def read_with_second_opinion(self) -> None:
        """Idem, para o segundo leitor local (S-66)."""
        self.second_opinion_button.read()

    def _apply_second_opinion(self, idx: int, placement: str) -> None:
        """Adota a leitura do segundo modelo e acende as casas em disputa."""
        leitor = "O segundo leitor"
        parecer = self.model.mark_second_opinion(idx, placement, reader=leitor)
        if parecer is None:
            self._on_status("Segunda leitura recebida, mas o OCR atual mudou.")
            return
        if idx == self.model.clamped_index():
            self.fen_var.set(parecer.placement)
            self.update_views()
        self._on_status(parecer.describe())

    def _selected_board_image(self) -> tuple[int, np.ndarray] | None:
        """O que vai para fora da máquina: uma cópia, e só do diagrama selecionado."""
        if not self.model.items:
            return None
        idx = self.model.clamped_index()
        return idx, np.asarray(self.model.items[idx].board_rgb).copy()

    def _apply_corrected_fen(self, idx: int, fen: str) -> None:
        # `mark_net_corrected` registra a procedencia da S-52 junto com a FEN: esta leitura
        # nao veio do modelo local nem de uma pessoa, e sem essa marca ela seria gravada como
        # `ocr-corrigido` -- fazendo a coluna contar leitura de terceiro como trabalho humano.
        if not self.model.mark_net_corrected(idx, fen):
            self._on_status("Correção recebida, mas o OCR atual mudou.")
            return
        if idx == self.model.clamped_index():
            self.fen_var.set(fen)
            self.update_views()
        self._on_status(f"FEN corrigida via Net (diagrama {idx + 1}).")
