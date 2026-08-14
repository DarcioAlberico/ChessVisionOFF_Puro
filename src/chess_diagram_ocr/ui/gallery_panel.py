"""A aba "Galeria": um diagrama por vez, sincronizado com a página do PDF (S-67).

**O que ela é, e o que ela não é.** Não é um segundo editor de posição -- a aba Resultado já
é isso, e duplicá-la criaria dois lugares para corrigir a mesma casa. Aqui a unidade de
trabalho é a **anotação de exportação**: o número do lance, a vez, se aquele diagrama sai com
link de análise e os headers de PGN que só quem conhece o livro pode preencher.

Por isso o que aparece no centro é o **recorte original** do livro, e não o tabuleiro
redesenhado a partir da FEN. Quem está digitando "lance 24" está lendo a legenda impressa, e
um tabuleiro redesenhado esconde justamente a fonte dessa informação.

**A sincronia anda nos dois sentidos e nenhum deles arrasta o outro à força.** Navegar na
galeria pede ao visualizador a página do diagrama; virar a página no visualizador move a
galeria **se** aquela página tiver diagrama. Página de texto não move nada -- ver
`GalleryModel.sync_to_page` para por que isso importa.

Toda a lógica que dá para testar está no `gallery_model`. O que sobrou aqui é widget,
thread e o vaivém entre os dois.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from chess_diagram_ocr.config import DEFAULT_READING_ORDER
from chess_diagram_ocr.gallery import load_annotations
from chess_diagram_ocr.gallery_scan import build_gallery_index, load_index, save_index
from chess_diagram_ocr.games_db import (
    DEFAULT_DATABASE_DIR,
    DiagramMatch,
    default_database_path,
    match_entries,
    scan_by_players,
)
from chess_diagram_ocr.service import OcrService

from .gallery_model import HEADER_FIELDS, GalleryModel, describe_origin
from .tooltip import Tooltip

logger = logging.getLogger(__name__)

__all__ = ["GalleryPanel"]

BOARD_VIEW_SIZE = 420
"""Lado do recorte na tela. Fixo: a galeria é para percorrer, e um tamanho que muda a cada
diagrama faria a imagem pular sob o ponteiro a cada avanço."""

CAPTION_LINES = 8
"""Altura da legenda em linhas. O resto rola -- e **nada é cortado**.

Ela era um `Label` com `caption[:220]`, o que bastava enquanto ela fosse só pista de contexto.
Deixou de bastar quando o texto passou a ser matéria-prima: o que se copia de uma legenda
truncada é uma legenda truncada, e o pedaço que falta costuma ser justamente o nome do segundo
jogador ou o ano."""

LINK_CHOICES = (("padrão", ""), ("com link", "sim"), ("sem link", "não"))
"""Tri-estado na tela, igual ao do arquivo. "padrão" é o que a exportação decidir."""


class GalleryPanel(ttk.Frame):
    """Percorre os diagramas do livro e grava as anotações de exportação."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        service: OcrService,
        pdf_path: Callable[[], Path | None],
        model_path: Callable[[], Path],
        max_boards: Callable[[], int],
        on_status: Callable[[str], None],
        on_page_request: Callable[[int], None],
    ) -> None:
        super().__init__(parent, padding=6)
        self._service = service
        self._pdf_path = pdf_path
        self._model_path = model_path
        self._max_boards = max_boards
        self._on_status = on_status
        self._on_page_request = on_page_request
        """Pede ao visualizador para ir àquela página. Mora fora porque a galeria não conhece
        o painel de PDF -- e não deveria: são abas irmãs, não uma dona da outra."""

        self.model = GalleryModel()
        self._cancel = threading.Event()
        self._scanning = False
        self._photo: ImageTk.PhotoImage | None = None
        self._syncing = False
        """Guarda de reentrância: pedir a página ao visualizador faz ele avisar de volta que
        a página mudou, e sem isto os dois se chamariam em círculo."""

        self.move_var = tk.StringVar(value="")
        self.side_var = tk.StringVar(value="w")
        self.link_var = tk.StringVar(value="")
        self.position_var = tk.StringVar(value="nenhum diagrama varrido")
        self.scan_var = tk.StringVar(value="")
        self.header_vars: dict[str, tk.StringVar] = {nome: tk.StringVar(value="") for nome in HEADER_FIELDS}
        self.free_name_var = tk.StringVar(value="")
        self.free_value_var = tk.StringVar(value="")
        self.origin_var = tk.StringVar(value="")
        """A partida da base que preencheu este diagrama, quando foi ela (S-72)."""

        self._last_applied: dict[str, str] = {}
        """O que a última cópia para todos espalhou, para o desfazer.

        Só da sessão: depois de fechar a janela, o desfazer some. É honesto -- o que ele
        promete é reverter **aquele gesto**, e não manter um histórico do arquivo."""

        self._build()
        self.refresh()

    # ------------------------------------------------------------------------ construção

    def _build(self) -> None:
        topo = ttk.Frame(self)
        topo.pack(fill=tk.X)
        self.btn_scan = ttk.Button(topo, text="Varrer livro", command=self.scan)
        self.btn_scan.pack(side=tk.LEFT)
        self.btn_cancel = ttk.Button(topo, text="Cancelar", command=self.cancel_scan, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=6)
        self.btn_games = ttk.Button(topo, text="Buscar na base", command=self.search_database)
        self.btn_games.pack(side=tk.LEFT, padx=6)
        Tooltip(self.btn_games).set_text(
            "Procura na base de partidas os diagramas cuja legenda traz os jogadores, e "
            "preenche lance, vez e headers -- só onde estiver vazio. Uma passada pela base, "
            "e nada sai da máquina."
        )
        ttk.Label(topo, textvariable=self.scan_var).pack(side=tk.LEFT, padx=10)

        corpo = ttk.Frame(self)
        corpo.pack(fill=tk.BOTH, expand=True, pady=6)

        centro = ttk.Frame(corpo)
        centro.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(centro, width=BOARD_VIEW_SIZE, height=BOARD_VIEW_SIZE, highlightthickness=1)
        self.canvas.pack()
        ttk.Label(centro, textvariable=self.position_var).pack(pady=(6, 0))

        navegacao = ttk.Frame(centro)
        navegacao.pack(pady=4)
        ttk.Button(navegacao, text="<<", width=4, command=lambda: self._go(0, absolute=True)).pack(side=tk.LEFT)
        ttk.Button(navegacao, text="< anterior", command=lambda: self._go(-1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(navegacao, text="próximo >", command=lambda: self._go(1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(navegacao, text=">>", width=4, command=lambda: self._go(-1, absolute=True)).pack(side=tk.LEFT)

        self._build_caption(centro)

        self._build_side_frame(corpo)
        self._build_footer()

    def _build_caption(self, parent: tk.Misc) -> None:
        """A legenda impressa, inteira e **selecionável**.

        Ela é a fonte do que a pessoa digita nos campos ao lado -- o nome dos jogadores, o
        evento, o lance --, e enquanto foi um `Label` era a única coisa da tela que não se
        podia aproveitar: quem via "Coull - Stanciu" ali tinha de redigitá-lo à mão no campo
        `Black`. Agora ela se seleciona com o mouse, copia com `Ctrl+C`, e tem um botão para
        quem quer a legenda toda de uma vez.
        """
        moldura = ttk.Frame(parent)
        moldura.pack(fill=tk.BOTH, expand=True, pady=4)

        self.caption_text = tk.Text(
            moldura,
            height=CAPTION_LINES,
            wrap=tk.WORD,
            relief=tk.FLAT,
            highlightthickness=0,
            cursor="xterm",
        )
        fundo, frente = self._caption_colors()
        if fundo:
            self.caption_text.configure(background=fundo)
        if frente:
            self.caption_text.configure(foreground=frente)
        self.caption_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        barra = ttk.Scrollbar(moldura, orient=tk.VERTICAL, command=self.caption_text.yview)
        barra.pack(side=tk.LEFT, fill=tk.Y)
        self.caption_text.configure(yscrollcommand=barra.set)
        self.caption_text.bind("<Key>", self._reject_caption_edit)

        ttk.Button(parent, text="Copiar legenda", command=self.copy_caption).pack(pady=(0, 4))

    def _caption_colors(self) -> tuple[str, str]:
        """Fundo e frente vindos do tema, e não hexadecimal fixo -- a mesma razão da S-65.

        Metade dos 30 temas do `ttkbootstrap` é escura, e um `tk.Text` nasce branco: num tema
        escuro ele seria um retângulo branco no meio da janela. Sem tema resolvido, devolve
        vazio e o Tk usa o padrão dele, que é o que se quer numa instalação sem a biblioteca.
        """
        estilo = ttk.Style()
        return (
            str(estilo.lookup("TFrame", "background") or ""),
            str(estilo.lookup("TLabel", "foreground") or ""),
        )

    def _reject_caption_edit(self, event: tk.Event) -> str | None:
        """Deixa navegar e copiar; recusa qualquer tecla que editaria.

        `state=tk.DISABLED` seria mais curto e é o caminho errado: o widget desabilitado
        também recusa a seleção por teclado e o tema o pinta de cinza-apagado, e o que se
        quer aqui é um texto **de leitura**, não um campo desligado.
        """
        # `event.state` chega como int no Windows e pode chegar como string em outros Tk.
        modificadores = event.state if isinstance(event.state, int) else 0
        if modificadores & 0x0004 and event.keysym.lower() in {"c", "a", "insert"}:
            return None
        if event.keysym in {"Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next", "Shift_L", "Shift_R"}:
            return None
        return "break"

    def _build_side_frame(self, parent: tk.Misc) -> None:
        lateral = ttk.LabelFrame(parent, text="Headers do PGN", padding=8)
        lateral.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))

        for linha, nome in enumerate(HEADER_FIELDS):
            ttk.Label(lateral, text=nome).grid(row=linha, column=0, sticky="w", pady=1)
            campo = ttk.Entry(lateral, textvariable=self.header_vars[nome], width=26)
            campo.grid(row=linha, column=1, sticky="we", pady=1)
            # `partial` e nao `lambda` com argumento-padrao: o corpo do laco reusa `nome`, e
            # um `lambda` que o capturasse por fechamento gravaria todos os campos no ultimo.
            campo.bind("<FocusOut>", partial(self._on_header_event, nome))
            campo.bind("<Return>", partial(self._on_header_event, nome))

        livre = len(HEADER_FIELDS)
        ttk.Separator(lateral, orient=tk.HORIZONTAL).grid(row=livre, column=0, columnspan=2, sticky="we", pady=6)
        ttk.Label(lateral, text="outro").grid(row=livre + 1, column=0, sticky="w")
        ttk.Entry(lateral, textvariable=self.free_name_var, width=26).grid(row=livre + 1, column=1, sticky="we")
        ttk.Entry(lateral, textvariable=self.free_value_var, width=26).grid(row=livre + 2, column=1, sticky="we", pady=1)
        ttk.Button(lateral, text="Gravar", command=self._commit_free_header).grid(row=livre + 3, column=1, sticky="e")

        # A procedencia da base fica **junto dos campos que ela preencheu**, e nao na barra de
        # status: a barra fala do ultimo gesto, e esta pergunta ("quem preencheu isto?") se faz
        # ao chegar num diagrama, que pode ser dias depois da busca.
        ttk.Label(lateral, textvariable=self.origin_var, wraplength=220, foreground="#2e7d32").grid(
            row=livre + 4, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        # O rotulo diz a **direcao** da copia. "Aplicar a todos" foi lido como "salvar os
        # headers deste diagrama" -- e o clique espalhou quatro campos por 1.405 diagramas.
        aplicar = ttk.Button(lateral, text="Copiar headers para todos", command=self.apply_to_all)
        aplicar.grid(row=livre + 5, column=0, columnspan=2, sticky="we", pady=(10, 0))
        Tooltip(aplicar).set_text(
            "Copia os headers deste diagrama para TODOS os outros do livro, sobrescrevendo o "
            "que eles tiverem nesses campos. Os campos já se salvam sozinhos ao sair deles -- "
            "este botão não é para salvar, é para propagar."
        )

        self.btn_undo = ttk.Button(lateral, text="Desfazer a cópia", command=self.undo_apply_to_all)
        self.btn_undo.grid(row=livre + 6, column=0, columnspan=2, sticky="we", pady=(4, 0))
        self.btn_undo.configure(state=tk.DISABLED)
        Tooltip(self.btn_undo).set_text(
            "Remove dos outros diagramas os valores que a última cópia espalhou. "
            "Não recupera o que a cópia sobrescreveu -- por isso a pergunta antes."
        )

    def _build_footer(self) -> None:
        rodape = ttk.LabelFrame(self, text="Este diagrama", padding=8)
        rodape.pack(fill=tk.X)

        ttk.Label(rodape, text="Lance").pack(side=tk.LEFT)
        lance = ttk.Entry(rodape, textvariable=self.move_var, width=6)
        lance.pack(side=tk.LEFT, padx=(4, 12))
        lance.bind("<FocusOut>", lambda _evento: self._commit_move())
        lance.bind("<Return>", lambda _evento: self._commit_move())

        ttk.Label(rodape, text="Vez").pack(side=tk.LEFT)
        for rotulo, valor in (("brancas", "w"), ("pretas", "b")):
            ttk.Radiobutton(
                rodape, text=rotulo, value=valor, variable=self.side_var, command=self._commit_side
            ).pack(side=tk.LEFT, padx=2)

        ttk.Label(rodape, text="Lichess").pack(side=tk.LEFT, padx=(12, 0))
        for rotulo, valor in LINK_CHOICES:
            ttk.Radiobutton(
                rodape, text=rotulo, value=valor, variable=self.link_var, command=self._commit_link
            ).pack(side=tk.LEFT, padx=2)

        ttk.Button(rodape, text="Copiar link", command=self.copy_link).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------------ varredura

    def scan(self) -> None:
        """Varre o livro inteiro. É a operação longa desta aba, e roda em thread."""
        if self._scanning:
            return
        caminho = self._pdf_path()
        if caminho is None:
            messagebox.showwarning("Galeria", "Abra um PDF antes de varrer.")
            return

        self._scanning = True
        self._cancel.clear()
        self.btn_scan.configure(state=tk.DISABLED)
        self.btn_cancel.configure(state=tk.NORMAL)
        self.scan_var.set("varrendo...")
        threading.Thread(target=self._scan_worker, args=(caminho,), daemon=True).start()

    def cancel_scan(self) -> None:
        """Cancelar não descarta o que já foi varrido -- ver `build_gallery_index`."""
        self._cancel.set()
        self.scan_var.set("cancelando...")

    def _scan_worker(self, caminho: Path) -> None:
        try:
            # `model_session` empresta o modelo do servico em vez de carregar outro: e a
            # mesma razao da S-57, e a varredura da galeria e tao longa quanto a da fila.
            indice = build_gallery_index(
                caminho,
                self._model_path(),
                max_boards_per_page=self._max_boards(),
                reading_order=DEFAULT_READING_ORDER,
                cancel_event=self._cancel,
                progress_callback=self._progress,
                model_session=self._service.model_session(self._model_path()),
                caption_reader=getattr(self._service, "caption_reader", None),
            )
            save_index(caminho, indice)
            self.after(0, lambda: self._scan_done(caminho, indice))
        except Exception as exc:  # noqa: BLE001 - a varredura toca modelo, PDF e disco
            logger.exception("Varredura da galeria falhou.")
            # `partial` e nao `lambda`: a excecao viaja ligada por valor, e um `lambda` que
            # fecha sobre `exc` le uma variavel que o `except` ja apagou ao sair do bloco.
            self.after(0, partial(self._scan_failed, exc))

    def _progress(self, pagina: int, total: int, _diagramas: int, _aceitos: int) -> None:
        self.after(0, lambda: self.scan_var.set(f"varrendo página {pagina} de {total}..."))

    def _scan_done(self, caminho: Path, indice: object) -> None:
        self._scanning = False
        self.btn_scan.configure(state=tk.NORMAL)
        self.btn_cancel.configure(state=tk.DISABLED)
        self.load_pdf(caminho)
        cancelada = " (cancelada)" if self._cancel.is_set() else ""
        self.scan_var.set(f"{len(self.model)} diagrama(s){cancelada}")
        self._on_status(f"Galeria: {len(self.model)} diagrama(s) varrido(s){cancelada}.")

    def _scan_failed(self, exc: Exception) -> None:
        self._scanning = False
        self.btn_scan.configure(state=tk.NORMAL)
        self.btn_cancel.configure(state=tk.DISABLED)
        self.scan_var.set("falhou")
        messagebox.showerror("Galeria", f"Não foi possível varrer o livro:\n{exc}")

    # ------------------------------------------------------------------- busca na base (S-72)

    def search_database(self) -> None:
        """Procura na base de partidas o que as legendas deste livro nomeiam.

        **Uma passada por livro, não por diagrama.** A base tem 9,7 GB e ler tudo custa ~150 s;
        os pares de nomes vão todos juntos, e a resposta sai para os 178 de uma vez. Perguntar
        por diagrama custaria os mesmos 150 s cada -- é a economia da S-61, aqui de novo.
        """
        if self._scanning:
            return
        if self.model.is_empty:
            messagebox.showinfo("Base de partidas", "Varra o livro antes: a busca usa as legendas dos diagramas.")
            return
        base = default_database_path()
        if base is None:
            messagebox.showinfo(
                "Base de partidas",
                f"Nenhum arquivo .pgn em {DEFAULT_DATABASE_DIR}.\n\n"
                "A base é sua e fica fora do repositório -- ponha um .pgn nessa pasta.",
            )
            return
        pares = self.model.pending_pairs()
        if not pares:
            self._on_status("Nenhuma legenda deste livro traz os dois jogadores; a base não tem por onde procurar.")
            return

        self._scanning = True
        self._cancel.clear()
        self.btn_scan.configure(state=tk.DISABLED)
        self.btn_games.configure(state=tk.DISABLED)
        self.btn_cancel.configure(state=tk.NORMAL)
        self.scan_var.set(f"procurando {len(pares)} par(es) na base...")
        threading.Thread(target=self._search_worker, args=(base, pares), daemon=True).start()

    def _search_worker(self, base: Path, pares: set[tuple[str, str]]) -> None:
        try:
            partidas = scan_by_players(
                base,
                pares,
                progress=self._search_progress,
                cancel=self._cancel,
            )
            casamentos = match_entries(self.model.index.entries, partidas)
            self.after(0, partial(self._search_done, casamentos, len(partidas)))
        except Exception as exc:  # noqa: BLE001 - a base e de terceiro e o arquivo e enorme
            logger.exception("Busca na base falhou.")
            self.after(0, partial(self._search_failed, exc))

    def _search_progress(self, lidas: int) -> None:
        """Vem da thread da busca; a `StringVar` só pode ser tocada pelo laço do Tk."""
        self.after(0, lambda: self.scan_var.set(f"base: {lidas / 1e6:.1f} M partidas lidas..."))

    def _search_done(self, casamentos: list[DiagramMatch], pares_achados: int) -> None:
        self._scanning = False
        self.btn_scan.configure(state=tk.NORMAL)
        self.btn_games.configure(state=tk.NORMAL)
        self.btn_cancel.configure(state=tk.DISABLED)

        relatorio = self.model.apply_matches(casamentos)
        self._persist()
        self.refresh(request_page=False)
        self.scan_var.set(f"{len(casamentos)} diagrama(s) casado(s)")
        self._on_status(
            f"Base: {pares_achados} par(es) com partida, {relatorio.confirmed} leitura(s) confirmada(s), "
            f"{relatorio.fields} campo(s) preenchido(s) em {relatorio.touched} diagrama(s). "
            "Nada foi sobrescrito."
        )

    def _search_failed(self, exc: Exception) -> None:
        self._scanning = False
        self.btn_scan.configure(state=tk.NORMAL)
        self.btn_games.configure(state=tk.NORMAL)
        self.btn_cancel.configure(state=tk.DISABLED)
        self.scan_var.set("falhou")
        messagebox.showerror("Base de partidas", f"Não foi possível ler a base:\n{exc}")

    # ------------------------------------------------------------------------ ciclo de vida

    def load_pdf(self, pdf_path: Path | None, *, request_page: bool = True) -> None:
        """Troca o livro: carrega o índice já varrido, se houver, e as anotações.

        `request_page` desligado é o caminho de quem **abre** o PDF: ali o visualizador acabou
        de restaurar a página em que o usuário parou (S-25), e a galeria pedir a página do seu
        primeiro diagrama jogaria essa restauração fora.
        """
        if pdf_path is None:
            self.model = GalleryModel()
            self.refresh(request_page=request_page)
            return

        indice = load_index(pdf_path)
        self.model = GalleryModel(
            index=indice if indice is not None else self.model.index.__class__(),
            # As anotações são carregadas mesmo sem varredura: elas não dependem do índice, e
            # desde a S-71 a aba Resultado escreve o número do lance por aqui. Ligá-las à
            # varredura fazia o número digitado lá sumir num livro nunca varrido.
            annotations=load_annotations(pdf_path),
            pdf_path=pdf_path,
        )
        if indice is None:
            self.scan_var.set("livro ainda não varrido")
        self.refresh(request_page=request_page)

    # ------------------------------------------------- anotação vinda de fora (S-71)
    # A aba Resultado também edita o número do lance, e as duas têm de falar do mesmo
    # diagrama. Quem guarda a anotação em memória é este painel -- duas cópias do mesmo
    # arquivo JSON divergiriam, e a última a gravar apagaria o que a outra tinha escrito.

    def move_number_at(self, page_index: int, diagram_index: int) -> int | None:
        return self.model.annotations.get(page_index, diagram_index).move_number

    def set_move_number(self, page_index: int, diagram_index: int, value: int | None) -> None:
        """Grava o número do lance daquele diagrama. `None` apaga a declaração.

        Em branco **apaga** em vez de gravar zero, pela mesma regra do resto da galeria: não
        declarar e declarar vazio são coisas diferentes, e só a primeira deixa a exportação
        decidir.
        """
        self.model.annotations.update(page_index, diagram_index, move_number=value)
        self._persist()
        if self.model.pdf_path is not None:
            self.refresh(request_page=False)

    def sync_to_page(self, page_index: int) -> None:
        """O visualizador virou a página; a galeria acompanha se houver diagrama lá."""
        if self._syncing or self.model.is_empty:
            return
        if self.model.sync_to_page(page_index):
            self.refresh(request_page=False)

    # ------------------------------------------------------------------------ navegação

    def _go(self, delta: int, *, absolute: bool = False) -> None:
        if absolute:
            mudou = self.model.go_to(0 if delta >= 0 else len(self.model) - 1)
        else:
            mudou = self.model.step(delta)
        if mudou:
            self.refresh()

    # ------------------------------------------------------------------------ edição

    def _commit_move(self) -> None:
        texto = self.move_var.get().strip()
        if not texto:
            self.model.edit(move_number=None)
        else:
            try:
                self.model.edit(move_number=max(1, int(texto)))
            except ValueError:
                # Devolver o campo ao valor gravado e nao abrir caixa: digitar e apagar e
                # normal, e um dialogo por tecla errada tornaria a galeria insuportavel.
                self._on_status(f"Lance inválido: {texto!r}. Mantido o valor anterior.")
        self._persist()

    def _commit_side(self) -> None:
        self.model.edit(side_to_move=self.side_var.get() or None)
        self._persist()

    def _commit_link(self) -> None:
        escolha = self.link_var.get()
        self.model.edit(lichess_link=None if escolha == "" else escolha == "sim")
        self._persist()

    def _on_header_event(self, nome: str, _evento: object = None) -> None:
        self._commit_header(nome)

    def _commit_header(self, nome: str) -> None:
        self.model.set_header(nome, self.header_vars[nome].get())
        self._persist()

    def _commit_free_header(self) -> None:
        nome = self.free_name_var.get().strip()
        if not nome:
            return
        self.model.set_header(nome, self.free_value_var.get())
        self.free_name_var.set("")
        self.free_value_var.set("")
        self._persist()
        self._on_status(f"Header {nome} gravado neste diagrama.")

    def apply_to_all(self) -> None:
        """Copia os headers deste diagrama para o livro inteiro -- **perguntando antes**.

        A pergunta nomeia os valores e conta os diagramas porque a ação é irreversível na
        parte que importa: ela **sobrescreve** o mesmo campo em centenas de anotações, e o
        valor anterior deixa de existir. Um clique já espalhou "Ljubojevic / Browne /
        Amsterdam / 1972" por 1.405 diagramas de um livro de 1.408 -- e o dono do projeto só
        descobriu depois, olhando um diagrama que não era daquela partida.
        """
        valores = self.model.headers_to_apply()
        if not valores:
            self._on_status("Nada a copiar: nenhum header preenchido neste diagrama.")
            return
        alvos = max(0, len(self.model) - 1)
        listados = "\n".join(f"    {nome} = {valor}" for nome, valor in valores.items())
        if not messagebox.askokcancel(
            "Copiar headers para todos",
            f"Copiar estes valores para os outros {alvos} diagrama(s) do livro?\n\n{listados}\n\n"
            "O que esses diagramas tiverem nesses campos será sobrescrito, e o valor "
            "anterior não poderá ser recuperado.",
            icon=messagebox.WARNING,
            default=messagebox.CANCEL,
        ):
            self._on_status("Cópia cancelada.")
            return

        atingidos = self.model.apply_headers_to_all()
        self._last_applied = dict(valores)
        self.btn_undo.configure(state=tk.NORMAL if atingidos else tk.DISABLED)
        self._persist()
        self._on_status(f"Headers copiados para {atingidos} outro(s) diagrama(s). Dá para desfazer.")

    def undo_apply_to_all(self) -> None:
        """Tira dos outros diagramas o que a última cópia espalhou.

        Apaga **pelo valor**, e não pela chave: o `Event` que a base preencheu certo em cada
        diagrama e o que foi digitado um a um continuam onde estão.
        """
        if not self._last_applied:
            return
        atingidos = self.model.revert_headers(self._last_applied)
        self._last_applied = {}
        self.btn_undo.configure(state=tk.DISABLED)
        self._persist()
        self.refresh(request_page=False)
        self._on_status(f"Cópia desfeita: header removido de {atingidos} diagrama(s).")

    def caption(self) -> str:
        """A legenda como está na tela. É por aqui que o teste a lê, sem tocar no widget."""
        return self.caption_text.get("1.0", tk.END).strip()

    def copy_caption(self) -> None:
        """Copia a legenda inteira. Nada sai da máquina -- é a área de transferência local."""
        texto = self.caption()
        if not texto:
            self._on_status("Este diagrama não tem legenda para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(texto)
        self._on_status("Legenda copiada.")

    def copy_link(self) -> None:
        url = self.model.lichess_url()
        if not url:
            return
        self.clipboard_clear()
        self.clipboard_append(url)
        self._on_status("Link do Lichess copiado. Nada saiu da máquina.")

    def _persist(self) -> None:
        caminho = self.model.save()
        if caminho is not None:
            self._on_status(f"Galeria: {self.model.annotated_count()} diagrama(s) anotado(s).")

    # ------------------------------------------------------------------------ desenho

    def refresh(self, *, request_page: bool = True) -> None:
        """Redesenha tudo a partir do modelo. Único caminho de atualização da tela."""
        atual = self.model.current
        self.position_var.set(self.model.describe_position())
        self._draw_board(atual)

        anotacao = self.model.current_annotation
        self.move_var.set("" if anotacao.move_number is None else str(anotacao.move_number))
        self.side_var.set(anotacao.side_to_move or (atual.side_to_move if atual else "w"))
        self.link_var.set("" if anotacao.lichess_link is None else ("sim" if anotacao.lichess_link else "não"))
        for nome, variavel in self.header_vars.items():
            variavel.set(anotacao.headers.get(nome, ""))
        self.origin_var.set(describe_origin(anotacao))
        self._set_caption(atual.caption if atual else "")

        if request_page and atual is not None:
            # A guarda evita o circulo: o visualizador avisa de volta que a pagina mudou.
            self._syncing = True
            try:
                self._on_page_request(atual.page_index)
            finally:
                self._syncing = False

    def _set_caption(self, texto: str) -> None:
        """Troca o texto exibido. Recomeça no topo: legenda nova, rolagem antiga é confusão."""
        self.caption_text.delete("1.0", tk.END)
        if texto:
            self.caption_text.insert("1.0", texto)
        self.caption_text.yview_moveto(0.0)

    def _draw_board(self, atual: object) -> None:
        self.canvas.delete("all")
        caminho = getattr(atual, "image_path", "")
        if not caminho or not Path(caminho).exists():
            self._photo = None
            texto = "varra o livro para ver os diagramas" if self.model.is_empty else "recorte não encontrado"
            self.canvas.create_text(BOARD_VIEW_SIZE // 2, BOARD_VIEW_SIZE // 2, text=texto, fill="#888")
            return
        try:
            imagem = Image.open(caminho).convert("RGB").resize((BOARD_VIEW_SIZE, BOARD_VIEW_SIZE))
        except OSError as exc:
            logger.warning("Não foi possível abrir o recorte %s: %s", caminho, exc)
            self._photo = None
            self.canvas.create_text(BOARD_VIEW_SIZE // 2, BOARD_VIEW_SIZE // 2, text="recorte ilegível", fill="#888")
            return
        # A referencia tem de sobreviver a esta funcao: o Tk nao segura a imagem.
        self._photo = ImageTk.PhotoImage(imagem)
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
