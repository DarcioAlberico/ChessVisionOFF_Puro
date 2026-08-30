"""Aba de revisão: a fila da S-22 na tela (S-22 + S-20).

O painel não sabe reconhecer nada, não guarda modelo e **não varre**: ele mostra a fila
ordenada e devolve o item escolhido ao dono da janela, que é quem tem o editor de posição. Essa
fronteira é a mesma que a Fase 6 vai querer entre serviço e apresentação (S-31), e mantê-la
agora custa nada.

**Ele varria, até a S-119.** `build_review_queue` e `build_gallery_index` percorriam o mesmo
`iter_pdf_diagrams`, com os mesmos parâmetros, e gravavam em arquivos diferentes: 338 s + 299 s
medidos no `PDF/1000 Chess Problems`. Agora a passada é uma -- a da Galeria --, e o que este
módulo põe nela é o `ReviewSink`: um acumulador que recebe cada diagrama lido e devolve a fila
pronta. `build_review_queue` continua existindo para o `cvoff-review`, que não tem janela.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..config import ACCEPT_MIN_CONFIDENCE, DEFAULT_MAX_BOARDS, DEFAULT_READING_ORDER, OrientationMode, ReadingOrder
from ..pdf_to_pgn import ScannedDiagram
from ..review_queue import (
    DEFAULT_CACHE_DIR,
    DEFAULT_QUEUE_PATH,
    ReviewItem,
    ReviewQueue,
    ReviewQueueBuilder,
    error_rate,
    merge_queues,
    rare_classes_from_labels,
)
from ..service import OcrService
from . import espaco, estilos, formato, strings, tabela, texto
from .busy import BusyRegistry, BusyToken
from .tooltip import Tooltip

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


class ReviewSink:
    """Monta a fila de revisão a partir da varredura da Galeria, e a entrega ao painel (S-119).

    **É o que faz uma passada pelo livro servir às duas abas.** `build_gallery_index` produz o
    superconjunto -- todo diagrama, sem gate --, e cada um deles chega aqui pelo `on_scanned`;
    o `ReviewQueueBuilder` é o mesmo acumulador que o `build_review_queue` usa, então as duas
    filas saem do mesmo código de montagem e a equivalência é estrutural.

    **O construtor não toca disco, e é de propósito.** Ele roda na thread do Tk, junto com o
    clique; o `labels.csv` (3.936 linhas) e as anotações do livro só são lidos no primeiro
    `feed`, que já é a thread da varredura. É a regra da S-116.
    """

    def __init__(self, panel: ReviewPanel, request: ScanRequest, *, cache_dir: Path) -> None:
        self._panel = panel
        self._request = request
        self._cache_dir = cache_dir
        self._builder: ReviewQueueBuilder | None = None

    def _acumulador(self) -> ReviewQueueBuilder:
        if self._builder is None:
            self._builder = ReviewQueueBuilder(
                self._request.pdf_path,
                cache_dir=self._cache_dir,
                rare_classes=rare_classes_from_labels(self._request.labels_csv),
                accept_threshold=self._request.accept_threshold,
            )
        return self._builder

    def feed(self, scanned: ScannedDiagram) -> None:
        """Um diagrama lido pela varredura. Roda na thread dela."""
        self._acumulador().feed(scanned)

    def progress(self, pagina: int, total: int) -> None:
        """A mesma página que a Galeria mostra, na barra desta aba. Vem da thread da varredura.

        Não abre um segundo registro de operação longa: a barra do rodapé é da varredura, e
        ela é uma só desde a S-119. O que falta aqui é só a pessoa que está *nesta* aba não
        ficar olhando uma frase parada enquanto o livro roda.
        """
        self._panel.after(
            0, lambda: self._panel.progress_var.set(f"Varrendo o livro... página {pagina} de {total}")
        )

    def deliver(self, *, cancelled: bool) -> None:
        """A fila pronta, na tela. **Tem de ser chamado na thread do Tk.**

        Nada lido, nada entregue: uma varredura retomada que não achou página nova (S-120) não
        pode substituir a fila por uma vazia. As páginas visitadas viajam junto porque é o que
        impede a fusão de encurtar a fila -- ver `merge_queues`.
        """
        if self._builder is None:
            self._panel._finish_scan()
            return
        paginas = frozenset(self._builder.pages)
        self._panel._apply_scan(self._builder.finish(), cancelled, pages=paginas)
        self._panel._finish_scan()

    def release(self) -> None:
        """A varredura terminou sem entregar -- falhou, ou não havia o que varrer."""
        self._panel._finish_scan()


class ReviewPanel(ttk.Frame):
    """Lista navegável da fila, com varredura em segundo plano e cancelamento."""

    COLUNAS = (
        tabela.Coluna("prioridade", "Prio.", 60, numerica=True),
        tabela.Coluna("página", "Pag.", 50, numerica=True),
        tabela.Coluna("diagrama", "Diag.", 50, numerica=True),
        tabela.Coluna("confiança", "Conf. min", 80, numerica=True),
        tabela.Coluna("status", "Status", 80),
        tabela.Coluna("motivo", "Motivo", 460, elastica=True),
    )
    """Quatro números e dois textos, e a diferença passou a valer (S-153).

    As quatro numéricas estavam com `anchor="w"`: `1623.8`, `40`, `1` e `0.082` alinhados à
    esquerda não se comparam por magnitude, e essa é a leitura inteira de uma fila ordenada por
    prioridade."""

    COLUMNS = tuple(coluna.chave for coluna in COLUNAS)

    def __init__(
        self,
        parent: tk.Misc,
        *,
        scan_request: Callable[[], ScanRequest | None],
        on_open: Callable[[ReviewItem, int], None],
        on_status: Callable[[str], None] | None = None,
        on_scan_book: Callable[[], None] | None = None,
        on_cancel_book: Callable[[], None] | None = None,
        queue_path: Path = DEFAULT_QUEUE_PATH,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        service: OcrService | None = None,
        busy: BusyRegistry | None = None,
    ) -> None:
        """`service` empresta o modelo sob o lock da S-31 durante a varredura (S-57).

        A varredura do livro percorre o PDF inteiro e é uma das duas operações longas que
        carregavam o `.pt` por conta própria, fora do lock -- enquanto o treino, noutra
        thread, reescrevia esse mesmo arquivo.

        **`on_scan_book` e `on_cancel_book` são a varredura única (S-119).** Este painel deixou
        de ter passada própria: ele pede a do livro e recebe a fila pelo `scan_sink`. Sem eles
        o painel abre e funciona -- é o que um roteiro de teste monta --, só não tem como pedir
        varredura nenhuma.
        """
        super().__init__(parent, padding=espaco.linha())
        self._service = service
        self._scan_request = scan_request
        self._on_open = on_open
        self._on_status = on_status or (lambda _text: None)
        self._on_scan_book = on_scan_book
        self._on_cancel_book = on_cancel_book
        self.queue_path = Path(queue_path)
        self.cache_dir = Path(cache_dir)

        self.queue = ReviewQueue.load(self.queue_path)
        self.queue.sort()
        self._scanning = False
        self._busy_registry = busy
        """Onde a varredura do livro se declara como operação longa (S-112). Quem registra hoje
        é a Galeria, que é quem tem a thread; aqui ele fica para não mudar a fronteira do
        construtor por causa de um item de desempenho."""
        self._busy_token: BusyToken | None = None

        self.summary_var = tk.StringVar(value="")
        self.progress_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")
        """O motivo inteiro do item selecionado, para o rodapé da tabela (S-153)."""
        self.only_pending_var = tk.BooleanVar(value=True)
        self._row_index: list[int] = []
        """Posição na `queue.items` de cada linha visível, na ordem da tabela."""

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, espaco.linha()))
        self.btn_scan = ttk.Button(
            toolbar,
            text=strings.VARRER_LIVRO,
            command=self.start_scan,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        )
        self.btn_scan.pack(side=tk.LEFT)
        Tooltip(
            self.btn_scan,
            "Fica cinza enquanto a varredura roda: uma por vez, porque as duas leriam o mesmo\n"
            "livro com o mesmo modelo. Pergunta antes quais livros varrer; a fila desta aba\n"
            "só sai do PDF aberto -- é dele que ela declara a procedência.",
        )
        self.btn_cancel = ttk.Button(
            toolbar,
            text="Cancelar",
            command=self.cancel_scan,
            state=tk.DISABLED,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        )
        self.btn_cancel.pack(side=tk.LEFT, padx=espaco.linha())
        Tooltip(
            self.btn_cancel,
            "Só fica ativo durante a varredura. O cancelamento termina a página em curso\n"
            "antes de parar, e os recortes já gravados continuam valendo.",
        )
        ttk.Button(
            toolbar,
            text="Abrir fila",
            command=self.open_queue_file,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT, padx=espaco.linha())
        ttk.Button(toolbar, text="Salvar fila", command=self.save_queue, style=estilos.estilo_de_botao(estilos.NEUTRO)).pack(side=tk.LEFT)
        ttk.Checkbutton(
            toolbar,
            text="Só pendentes",
            variable=self.only_pending_var,
            command=self.refresh,
        ).pack(side=tk.RIGHT)

        texto.acompanhar(ttk.Label(self, textvariable=self.summary_var)).pack(anchor="w")
        texto.acompanhar(ttk.Label(self, textvariable=self.progress_var)).pack(anchor="w", pady=(0, espaco.linha()))

        self.tree = tabela.montar(self, self.COLUNAS, selectmode="browse", height=14)
        self.tree.bind("<Double-1>", lambda _event: self.open_selected())
        self.tree.bind("<Return>", lambda _event: self.open_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._mostrar_motivo())

        # O motivo **inteiro** do item selecionado, sob a tabela (S-153). Rolar para o lado numa
        # lista de 129 linhas custa a coluna de referência: a tabela dá a visão geral, o rodapé
        # dá o texto, e nenhuma das duas precisa escolher entre as duas coisas.
        texto.acompanhar(
            ttk.Label(self, textvariable=self.detail_var, justify=tk.LEFT)
        ).pack(anchor="w", fill=tk.X, pady=(espaco.linha(), 0))

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(espaco.linha(), 0))
        ttk.Button(actions, text="Corrigir agora", style=estilos.estilo_de_botao(estilos.PRIMARIO), command=self.open_selected).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Marcar revisado",
            command=lambda: self.mark_selected("done"),
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT, padx=espaco.linha())
        ttk.Button(
            actions,
            text="Pular",
            command=lambda: self.mark_selected("skipped"),
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Reabrir",
            command=lambda: self.mark_selected("pending"),
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.LEFT, padx=espaco.linha())
        ttk.Button(
            actions,
            text="Próximo pendente",
            command=self.open_next_pending,
            style=estilos.estilo_de_botao(estilos.NEUTRO),
        ).pack(side=tk.RIGHT)

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
                    # Sem casa decimal, e a confiança em porcentagem (S-169): `1623.8` sugere
                    # que ele difere de `1623.7`, e `0.082` é o mesmo número que a barra de
                    # status escreve como `8,2%`.
                    formato.prioridade(item.priority),
                    item.page_number,
                    item.diagram_index,
                    formato.confianca(item.min_confidence),
                    strings.status_da_fila(item.status),
                    "; ".join(item.reasons),
                ),
            )

        if self.queue.items:
            taxa = error_rate(self.queue.items)
            self.summary_var.set(f"{self.queue.summary()} | {taxa:.0%} com sinal objetivo de erro")
        else:
            self.summary_var.set(f"Fila vazia. Abra um PDF e use '{strings.VARRER_LIVRO}'.")
        self._mostrar_motivo()

    def motivo_selecionado(self) -> str:
        """O motivo inteiro do item selecionado, ou vazio quando não há seleção (S-153).

        Função de leitura, sem widget de saída: é o que permite afirmar o **texto** do rodapé
        sem perguntar a um `Label` o que ele está mostrando.
        """
        posicao = self.selected_position()
        if posicao is None:
            return ""
        item = self.queue.items[posicao]
        return f"Motivo: {'; '.join(item.reasons)}" if item.reasons else "Motivo: sem sinal objetivo de erro."

    def _mostrar_motivo(self) -> None:
        self.detail_var.set(self.motivo_selecionado())

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
        """Pede **a** varredura do livro -- a mesma da Galeria, e a única que existe (S-119).

        Até 2026-08-18 este botão rodava a segunda passada pelo mesmo PDF: `build_review_queue`
        e `build_gallery_index` percorriam o mesmo `iter_pdf_diagrams`, com os mesmos
        parâmetros, e gravavam em arquivos diferentes. Medido no `PDF/1000 Chess Problems`
        (420 páginas): **338 s + 299 s**. Abrir um livro novo custava ~5 min antes de qualquer
        trabalho humano, e mais ~5 quando se descobria que a outra aba também precisava da sua.

        O botão continua aqui -- quem está na fila não deveria ter de saber que a varredura
        "mora" na outra aba --, mas ele e o da Galeria são o mesmo gesto.
        """
        if self._scanning:
            # As duas vão para o rodapé (S-164): "já está rodando" é o que a zona de operação ao
            # lado mostra, e "abra um PDF antes" é um passo que falta -- nenhuma é uma decisão.
            self._on_status("Já existe uma varredura de fila em execução.")
            return
        if self._on_scan_book is None:  # pragma: no cover - fora do app não há quem varra
            self._on_status("Esta janela não tem de onde varrer o livro.")
            return
        self._on_scan_book()

    def cancel_scan(self) -> None:
        if self._on_cancel_book is not None:
            self._on_cancel_book()
            self.progress_var.set("Cancelando... (termina a página atual)")

    def scan_sink(self) -> ReviewSink | None:
        """O coletor que monta a fila a partir da varredura do livro (S-119).

        Chamado pela Galeria **na thread do Tk**, antes de a varredura começar: ele lê os
        widgets de configuração aqui e não toca disco nenhum -- o `labels.csv` e as anotações
        do livro só são lidos quando o primeiro diagrama chega, que já é na thread da
        varredura. Ler 3.936 linhas de CSV para desenhar um botão cinza era o defeito da S-116,
        e ele não volta por esta porta.

        `None` quando não há PDF aberto: a Galeria segue varrendo para a aba dela, e a fila
        fica como estava. Um livro sem PDF não chega aqui, mas a Galeria não precisa saber
        disso para funcionar.
        """
        request = self._scan_request()
        if request is None:
            return None
        self._scanning = True
        self.btn_scan.configure(state=tk.DISABLED)
        self.btn_cancel.configure(state=tk.NORMAL)
        self.progress_var.set("Varrendo o livro...")
        return ReviewSink(self, request, cache_dir=self.cache_dir)

    def _apply_scan(
        self, fresh: ReviewQueue, cancelled: bool, *, pages: Collection[int] | None = None
    ) -> None:
        if self.queue.items and self.queue.source_pdf == fresh.source_pdf:
            # Revarredura não pode ressuscitar o que já foi revisado -- e o que `merge_queues`
            # garante. Sem isso, cada varredura apagaria o trabalho da sessao anterior.
            #
            # `pages` é o que a passada de fato visitou (S-119): a varredura do livro retoma de
            # onde parou (S-120), e sem dizer quais páginas ela viu a fusão encurtaria a fila
            # para as páginas novas.
            fresh = merge_queues(self.queue, fresh, pages=pages)
        self.queue = fresh
        self.save_queue(quiet=True)
        self.refresh()
        sufixo = " (cancelada)" if cancelled else ""
        self.progress_var.set(f"Varredura concluída{sufixo}. {self.queue.summary()}")
        self._on_status(f"Fila de revisão pronta{sufixo}: {self.queue.summary()}")

    def _finish_scan(self) -> None:
        self._scanning = False
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
