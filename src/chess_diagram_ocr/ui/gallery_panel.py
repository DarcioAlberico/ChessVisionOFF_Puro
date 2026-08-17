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
from chess_diagram_ocr.gallery import DiagramAnnotation, load_annotations
from chess_diagram_ocr.gallery_scan import build_gallery_index, load_index, save_index
from chess_diagram_ocr.games_cache import PositionCache, load_cache, save_cache
from chess_diagram_ocr.games_db import (
    DEFAULT_DATABASE_DIR,
    DiagramMatch,
    database_paths,
    match_entries,
    match_positions,
    scan_by_players,
    scan_by_positions,
)
from chess_diagram_ocr.games_index import DEFAULT_INDEX_PATH
from chess_diagram_ocr.service import OcrService

from .busy import BusyRegistry, BusyToken
from .gallery_model import HEADER_FIELDS, GalleryModel, describe_origin
from .games_dialog import GamesDialog
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

_SEM_BASE = (
    f"Nenhum arquivo .pgn em {DEFAULT_DATABASE_DIR}.\n\n"
    "A base é sua e fica fora do repositório -- ponha um .pgn nessa pasta. Pode ser mais de um: "
    "desde a S-93 todos os .pgn da pasta entram nas buscas."
)
"""O aviso de quem não tem base. Um só, porque os dois botões dizem a mesma coisa -- e duas
cópias do mesmo texto divergem na primeira vez que uma delas for corrigida."""


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
        busy: BusyRegistry | None = None,
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

        self._busy_registry = busy
        """Onde as três operações longas desta aba se declaram (S-112). `None` fora do app --
        a aba tem de abrir num roteiro de teste que não montou registro nenhum."""
        self._busy_token: BusyToken | None = None

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
        # Os dois caminhos, lado a lado e com o criterio no proprio rotulo: "na base" nao
        # distinguia mais nada depois que a busca por posicao virou botao tambem (S-92).
        self.btn_games = ttk.Button(topo, text="Buscar por nome", command=self.search_database)
        self.btn_games.pack(side=tk.LEFT, padx=6)
        Tooltip(self.btn_games).set_text(
            "Procura na base de partidas os diagramas cuja legenda traz os jogadores, e "
            "preenche lance, vez e headers -- só onde estiver vazio. Uma passada pela base, "
            "e nada sai da máquina."
        )
        self.btn_positions = ttk.Button(topo, text="Buscar pela posição", command=self.search_by_position)
        self.btn_positions.pack(side=tk.LEFT, padx=6)
        Tooltip(self.btn_positions).set_text(
            "Procura pelas 64 casas de cada diagrama, e não pela legenda: alcança todo diagrama, "
            "inclusive os sem nome nenhum impresso. Reproduz os lances da base inteira -- cerca "
            "de meia hora na primeira vez, segundos nas seguintes, porque a resposta fica "
            "guardada. Dá para cancelar."
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

        # Junto dos campos que ele limpa, e nao com os dois de baixo: aqueles agem sobre o
        # livro inteiro, e este so sobre este diagrama. A distancia na tela e a diferenca de
        # alcance -- foi confundir as duas que espalhou quatro campos por 1.405 diagramas (S-76).
        self.btn_clear = ttk.Button(lateral, text="Limpar os headers", command=self.clear_headers)
        self.btn_clear.grid(row=livre + 4, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.btn_clear.configure(state=tk.DISABLED)
        Tooltip(self.btn_clear).set_text(
            "Apaga os headers DESTE diagrama, todos de uma vez -- para quando a base preencheu "
            "com a partida errada. O lance, a vez e a partida escolhida ficam. Não mexe em "
            "nenhum outro diagrama."
        )

        # A procedencia da base fica **junto dos campos que ela preencheu**, e nao na barra de
        # status: a barra fala do ultimo gesto, e esta pergunta ("quem preencheu isto?") se faz
        # ao chegar num diagrama, que pode ser dias depois da busca.
        ttk.Label(lateral, textvariable=self.origin_var, wraplength=220, foreground="#2e7d32").grid(
            row=livre + 5, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        # A lista de partidas fica **junto da procedencia**: as duas respondem "de onde veio
        # isto?", e a lista e o unico caminho para os 350 diagramas do acervo em que a base
        # sabe a resposta e nenhuma regra sabe qual das candidatas e (S-86).
        self.btn_candidates = ttk.Button(lateral, text="Partidas da base", command=self.open_games_dialog)
        self.btn_candidates.grid(row=livre + 6, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.btn_candidates.configure(state=tk.DISABLED)
        Tooltip(self.btn_candidates).set_text(
            "As partidas da base que contêm esta posição. Escolher uma preenche lance, vez e "
            "headers, e a escolha fica registrada -- uma nova busca na base não a desfaz."
        )

        # O rotulo diz a **direcao** da copia. "Aplicar a todos" foi lido como "salvar os
        # headers deste diagrama" -- e o clique espalhou quatro campos por 1.405 diagramas.
        aplicar = ttk.Button(lateral, text="Copiar headers para todos", command=self.apply_to_all)
        aplicar.grid(row=livre + 7, column=0, columnspan=2, sticky="we", pady=(10, 0))
        Tooltip(aplicar).set_text(
            "Copia os headers deste diagrama para TODOS os outros do livro, sobrescrevendo o "
            "que eles tiverem nesses campos. Os campos já se salvam sozinhos ao sair deles -- "
            "este botão não é para salvar, é para propagar."
        )

        self.btn_undo = ttk.Button(lateral, text="Desfazer a cópia", command=self.undo_apply_to_all)
        self.btn_undo.grid(row=livre + 8, column=0, columnspan=2, sticky="we", pady=(4, 0))
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

    def _busy(self, busy: bool) -> None:
        """Liga e desliga os três botões que disputam a única thread longa desta aba.

        Eram três blocos de `configure` repetidos em seis lugares, e a S-92 traria o quarto.
        O que o `_scanning` já garantia -- que uma busca não começa em cima de outra -- passa a
        aparecer na tela: um botão que não pode ser clicado agora **parece** que não pode.
        """
        estado = tk.DISABLED if busy else tk.NORMAL
        for botao in (self.btn_scan, self.btn_games, self.btn_positions):
            botao.configure(state=estado)
        self.btn_cancel.configure(state=tk.NORMAL if busy else tk.DISABLED)
        if not busy:
            # Aqui, e não em cada um dos seis `_*_done`/`_*_failed`/`_*_cancelled`: soltar o
            # registro é a metade do par que se esquece, e uma operação que ficou registrada
            # depois de terminar faz a janela perguntar para sempre (S-112).
            self._release_busy()

    def _register_busy(self, name: str, *, loses_work: bool, detail: str = "") -> None:
        """Declara a operação longa que vai começar, e o que fechar a janela custaria (S-112).

        As três desta aba disputam a mesma thread, o mesmo `Event` de cancelamento e o mesmo
        `_busy(...)` -- então o registro entra e sai pelos mesmos dois pontos. O que muda entre
        elas é o nome e o `loses_work`, e é só isso que cada chamador precisa dizer.
        """
        if self._busy_registry is None:
            return
        self._busy_token = self._busy_registry.register(
            name, loses_work=loses_work, cancellable=True, detail=detail, cancel=self.cancel_scan
        )

    def _release_busy(self) -> None:
        if self._busy_token is not None:
            self._busy_token.release()
            self._busy_token = None

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
        # `loses_work=False` desde a S-120: a varredura retoma da página seguinte à última
        # terminada, então fechar a janela custa **a página em curso**, e não o livro. Era
        # `True` na S-112, com o comentário nomeando este item como o que inverteria o valor.
        self._register_busy("varredura da Galeria", loses_work=False, detail=caminho.name)
        self._busy(True)
        self.scan_var.set("varrendo...")
        threading.Thread(target=self._scan_worker, args=(caminho,), daemon=True).start()

    def cancel_scan(self) -> None:
        """Cancela a operação longa em curso -- e o que se perde depende de qual é ela.

        A varredura do livro não descarta o que já leu (ver `build_gallery_index`), e a busca
        por posição **descarta a passada inteira** (ver `scan_by_positions`): meia base lida dá
        contagens que não valem, e é a contagem que decide se preencher é honesto.
        """
        self._cancel.set()
        self.scan_var.set("cancelando...")

    def _scan_worker(self, caminho: Path) -> None:
        try:
            # `model_session` empresta o modelo do servico em vez de carregar outro: e a
            # mesma razao da S-57, e a varredura da galeria e tao longa quanto a da fila.
            # Retomar de onde parou (S-120). O indice no disco pode ser parcial de uma
            # varredura cancelada ou de uma janela fechada, e `build_gallery_index` ignora
            # sozinho o que estiver completo -- aqui so se entrega o que ha.
            anterior = load_index(caminho)
            indice = build_gallery_index(
                caminho,
                self._model_path(),
                resume_from=anterior,
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
        """Diz **quanto do livro** foi varrido, e não só quantos diagramas saíram (S-120).

        Um índice truncado é indistinguível de um completo pelo número de diagramas -- é a
        parte do defeito que custa mais que o tempo perdido --, então o estado parcial vira
        texto na tela, com a página em que a varredura parou e o convite a continuar.
        """
        self._scanning = False
        self._busy(False)
        self.load_pdf(caminho)
        completo = bool(getattr(indice, "complete", True))
        ate = int(getattr(indice, "last_page_done", -1))
        if completo:
            self.scan_var.set(f"{len(self.model)} diagrama(s)")
            self._on_status(f"Galeria: {len(self.model)} diagrama(s) varrido(s), livro inteiro.")
            return
        self.scan_var.set(f"{len(self.model)} diagrama(s) — parcial até a página {ate + 1}")
        self._on_status(
            f"Galeria: **parcial**. {len(self.model)} diagrama(s) até a página {ate + 1}; "
            "varrer de novo continua daí, sem repetir o que já foi lido."
        )

    def _scan_failed(self, exc: Exception) -> None:
        self._scanning = False
        self._busy(False)
        self.scan_var.set("falhou")
        messagebox.showerror("Galeria", f"Não foi possível varrer o livro:\n{exc}")

    # ------------------------------------------------------------------- busca na base (S-72)

    def search_database(self) -> None:
        """Procura na base de partidas o que as legendas deste livro nomeiam.

        **Uma passada por livro, não por diagrama.** Ler a base inteira custa ~150 s por
        gigabase; os pares de nomes vão todos juntos, e a resposta sai para os 178 de uma vez.
        Perguntar por diagrama custaria os mesmos 150 s cada -- é a economia da S-61, de novo.

        **Todos os `.pgn` da pasta (S-93)**, e não o maior deles: a busca custa uma passada por
        arquivo, e a partida procurada costuma estar justamente no que ficava de fora.
        """
        if self._scanning:
            return
        if self.model.is_empty:
            messagebox.showinfo("Base de partidas", "Varra o livro antes: a busca usa as legendas dos diagramas.")
            return
        bases = database_paths()
        if not bases:
            messagebox.showinfo("Base de partidas", _SEM_BASE)
            return
        pares = self.model.pending_pairs()
        if not pares:
            self._on_status("Nenhuma legenda deste livro traz os dois jogadores; a base não tem por onde procurar.")
            return

        self._scanning = True
        self._cancel.clear()
        # Curta perto das outras duas: ~150 s por gigabase, uma passada só. Fechar no meio
        # custa esse tempo de novo, e nada além dele.
        self._register_busy("busca por nome na base", loses_work=False, detail=f"{len(pares)} par(es)")
        self._busy(True)
        self.scan_var.set(f"procurando {len(pares)} par(es) em {len(bases)} base(s)...")
        threading.Thread(target=self._search_worker, args=(bases, pares), daemon=True).start()

    def _search_worker(self, bases: list[Path], pares: set[tuple[str, str]]) -> None:
        try:
            partidas = scan_by_players(
                bases,
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
        self._busy(False)

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
        self._busy(False)
        self.scan_var.set("falhou")
        messagebox.showerror("Base de partidas", f"Não foi possível ler a base:\n{exc}")

    # ------------------------------------------------- busca pela posição (S-92)

    def search_by_position(self) -> None:
        """Procura na base as **posições** deste livro -- todas, numa passada só (S-92).

        **O que ela alcança, e o caminho por nome não.** A busca por nome depende de a legenda
        trazer os dois jogadores, e a maioria não traz: no acervo medido, 53,9% dos diagramas
        não casaram com partida nenhuma, e um diagrama de exercício costuma vir sem nome
        impresso. Aqui a pergunta são as **64 casas lidas**, que todo diagrama tem.

        **Por que o livro inteiro, e não este diagrama.** O custo é da passada pela base, não do
        alvo: o conjunto-alvo cabe na memória sejam 1.400 posições ou 40 mil. Perguntar por uma
        posição custaria os mesmos ~30 min por gigabase que perguntar pelas 1.400 -- é a
        economia da S-61 e da S-73, aqui de novo. Desde a S-93 são **todos** os `.pgn` da pasta
        na mesma passada, então o relógio anda com o tamanho da pasta.

        **E o preço é dito antes.** Meia hora atrás de um botão que não avisa é uma janela
        travada; a caixa diz quantas posições faltam, quanto custa e que a resposta fica
        guardada. Se nada faltar, a base **não é aberta** e a resposta sai do cache na hora --
        que é o caso de todo livro já varrido pelo `cvoff-games`.
        """
        if self._scanning:
            return
        if self.model.is_empty:
            messagebox.showinfo("Base de partidas", "Varra o livro antes: a busca usa as posições dos diagramas.")
            return
        bases = database_paths()
        if not bases:
            messagebox.showinfo("Base de partidas", _SEM_BASE)
            return

        alvos = {entrada.placement for entrada in self.model.index.entries if entrada.placement}
        cache = load_cache(database=bases)
        faltando = cache.missing(alvos)
        if not faltando:
            self._positions_done(cache, alvos, games_read=0)
            return
        if not messagebox.askokcancel(
            "Base de partidas",
            f"{len(faltando)} das {len(alvos)} posições deste livro nunca foram perguntadas à "
            f"base ({len(bases)} arquivo(s) .pgn).\n\n"
            "Procurá-las custa uma passada pelos arquivos inteiros, reproduzindo os lances de "
            "milhões de partidas: cerca de meia hora por gigabase. As outras posições já saem "
            "do cache.\n\n"
            "A resposta fica guardada -- da próxima vez isto responde em segundos, e um livro "
            "novo custa só as posições que ele trouxer.\n\n"
            "Dá para cancelar no meio, mas aí a passada é descartada inteira: meia base lida "
            "dá contagens que não valem.",
        ):
            return

        self._scanning = True
        self._cancel.clear()
        # **A mais cara do programa**, ~56 min medidos na Fase 13, e a única cujo resultado é
        # tudo-ou-nada: o cache só é gravado depois da passada inteira, porque meia base lida
        # dá contagens que não valem. Fechar aos 50 minutos descartava a passada sem uma
        # palavra -- é o caso que a S-112 existe para nomear.
        self._register_busy("busca por posição na base", loses_work=True, detail=f"{len(faltando)} posição(ões)")
        self._busy(True)
        self.scan_var.set(f"base: {len(faltando)} posição(ões) a procurar...")
        threading.Thread(
            target=self._positions_worker, args=(bases, cache, alvos, faltando), daemon=True
        ).start()

    def _positions_worker(
        self, bases: list[Path], cache: PositionCache, alvos: set[str], faltando: set[str]
    ) -> None:
        try:
            indice = scan_by_positions(bases, faltando, progress=self._positions_progress, cancel=self._cancel)
            if self._cancel.is_set():
                self.after(0, self._positions_cancelled)
                return
            # `faltando` inteiro, e nao so as posicoes que casaram: uma posicao que a base nao
            # conhece precisa ficar registrada como **perguntada**, senao ela volta ao alvo de
            # toda busca futura -- e no acervo medido essas sao a maioria (S-84).
            cache.update(indice, faltando)
            save_cache(cache)
            self.after(0, partial(self._positions_done, cache, alvos, indice.games_read))
        except Exception as exc:  # noqa: BLE001 - a base e de terceiro e o arquivo e enorme
            logger.exception("Busca por posição falhou.")
            self.after(0, partial(self._search_failed, exc))

    def _positions_progress(self, feitos: int, total: int) -> None:
        """Vem da thread da busca; a `StringVar` só pode ser tocada pelo laço do Tk."""
        self.after(0, lambda: self.scan_var.set(f"base: pedaço {feitos} de {total}..."))

    def _positions_done(self, cache: PositionCache, alvos: set[str], games_read: int) -> None:
        """Aplica o que a base respondeu e **deixa o cache em pé** para a lista de candidatas.

        Trocar `model.position_cache` é o que faz o botão "Partidas da base" acender no mesmo
        gesto: a varredura acabou de descobrir as candidatas de cada diagrama, e mandar a pessoa
        reabrir o livro para vê-las seria esconder o que ela pagou meia hora para ter.
        """
        self._scanning = False
        self._busy(False)
        self.model.position_cache = cache

        casamentos = match_positions(self.model.index.entries, cache.to_index(alvos))
        relatorio = self.model.apply_matches(casamentos)
        self._persist()
        self.refresh(request_page=False)
        self.scan_var.set(f"{len(casamentos)} diagrama(s) casado(s) por posição")
        if not games_read:
            origem = "sem abrir a base (tudo do cache)"
        elif games_read >= 1_000_000:
            origem = f"{games_read / 1e6:.1f} M partidas lidas"
        else:
            # Uma base pequena lida em "0,0 M" pareceria uma varredura que nao leu nada.
            origem = f"{games_read} partidas lidas"
        self._on_status(
            f"Base por posição: {origem}, {relatorio.confirmed} leitura(s) confirmada(s), "
            f"{relatorio.fields} campo(s) preenchido(s) em {relatorio.touched} diagrama(s). "
            "Nada foi sobrescrito."
        )

    def _positions_cancelled(self) -> None:
        """Cancelou: **nada** é gravado, e a tela diz isso em vez de deixar parecer que gravou."""
        self._scanning = False
        self._busy(False)
        self.scan_var.set("cancelada")
        self._on_status(
            "Busca por posição cancelada. Uma passada interrompida viu parte da base, e as "
            "contagens dela não valem -- nada foi gravado no cache."
        )

    # ------------------------------------------------------- a lista de candidatas (S-86)

    def open_games_dialog(self) -> None:
        """Abre a lista de partidas que contêm a posição deste diagrama.

        **Lê o cache, não a base.** É o que faz disto um clique e não uma janela travada por
        meia hora: a varredura já respondeu, e a resposta está em `data/games_positions.json`.
        """
        candidatas, _total = self.model.current_candidates()
        # Sem candidata a janela ainda abre **se a legenda nomeia os jogadores**: e o caminho
        # da S-87, e ele alcanca os 1.922 diagramas do acervo (53,9%) cuja posicao nao casou.
        if not candidatas and self.model.current_caption_pair() is None:
            messagebox.showinfo(
                "Partidas da base",
                "Nenhuma partida da base contém esta posição, e a legenda não nomeia os dois "
                "jogadores para procurar por nome.\n\n"
                'Se este livro nunca foi perguntado à base pela posição, o botão "Buscar pela '
                'posição" faz isso -- ou, para o acervo inteiro de uma vez:  cvoff-games --all',
            )
            return
        GamesDialog(self, model=self.model, on_applied=self._candidate_applied)

    def _candidate_applied(self, mensagem: str) -> None:
        """Volta da janela de candidatas: grava, redesenha e conta o que houve."""
        self._persist()
        self.refresh(request_page=False)
        self._on_status(mensagem)

    def _load_position_cache(self) -> None:
        """Carrega o cache de posições, se houver. Falha em silêncio -- ele é opcional.

        Sem cache o botão fica desligado e o resto da aba funciona igual: a lista é um caminho
        a mais, e não uma pré-condição para anotar um livro.
        """
        try:
            self.model.position_cache = load_cache(database=database_paths())
        except Exception:  # noqa: BLE001 - cache e material derivado; sem ele a aba segue
            logger.exception("Não foi possível ler o cache de posições.")
            self.model.position_cache = None

    def _refresh_candidates_button(self) -> None:
        candidatas, total = self.model.current_candidates()
        if not candidatas:
            pode_por_nome = self.model.current_caption_pair() is not None
            self.btn_candidates.configure(
                text="Procurar por nome" if pode_por_nome else "Partidas da base",
                state=tk.NORMAL if pode_por_nome else tk.DISABLED,
            )
            return
        # O numero no botao e o que faz a pessoa saber que ha o que escolher **antes** de
        # clicar: um diagrama com 47 candidatas e um com uma so pedem gestos diferentes.
        self.btn_candidates.configure(text=f"Partidas da base ({total})", state=tk.NORMAL)

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
            database_paths=tuple(database_paths()),
            index_path=DEFAULT_INDEX_PATH,
        )
        # O cache é do acervo, não do livro: ele é lido uma vez por troca de PDF porque uma
        # varredura pode ter rodado no meio da sessão, e é barato (2,2 MB para 3.143 posições).
        self._load_position_cache()
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

    def _persist_if_changed(self, before: DiagramAnnotation) -> None:
        """Grava só se a anotação de fato mudou (S-109).

        O modelo já é no-op quando nada muda; o que esta guarda evita é a **escrita**. Os
        quatro `_commit_*` são disparados por `<FocusOut>` e por `<<ComboboxSelected>>`, que
        acontecem ao *passar* por um campo -- e sem isto percorrer os headers de um diagrama
        reescrevia o arquivo do livro inteiro oito vezes, uma por campo.
        """
        if self.model.current_annotation != before:
            self._persist()

    def _commit_move(self) -> None:
        antes = self.model.current_annotation
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
        self._persist_if_changed(antes)

    def _commit_side(self) -> None:
        antes = self.model.current_annotation
        self.model.edit(side_to_move=self.side_var.get() or None)
        self._persist_if_changed(antes)

    def _commit_link(self) -> None:
        antes = self.model.current_annotation
        escolha = self.link_var.get()
        self.model.edit(lichess_link=None if escolha == "" else escolha == "sim")
        self._persist_if_changed(antes)

    def _on_header_event(self, nome: str, _evento: object = None) -> None:
        self._commit_header(nome)

    def _commit_header(self, nome: str) -> None:
        antes = self.model.current_annotation
        self.model.set_header(nome, self.header_vars[nome].get())
        self._persist_if_changed(antes)

    def _commit_free_header(self) -> None:
        nome = self.free_name_var.get().strip()
        if not nome:
            return
        self.model.set_header(nome, self.free_value_var.get())
        self.free_name_var.set("")
        self.free_value_var.set("")
        self._persist()
        self._on_status(f"Header {nome} gravado neste diagrama.")

    def clear_headers(self) -> None:
        """Apaga os headers **deste** diagrama, todos de uma vez -- perguntando antes (S-94).

        A pergunta **nomeia os valores que vão sair**, e não pergunta em abstrato. É a mesma
        regra do `apply_to_all` e a mesma razão: uma confirmação que não diz o que vai
        acontecer não é confirmação, é obstáculo -- e aqui o que se apaga pode ser meia hora
        de digitação de quem tinha o livro na mão.

        Não há desfazer, e a caixa diz isso. Um segundo botão de desfazer ao lado do que já
        existe ("Desfazer a cópia") criaria a dúvida de qual dos dois desfaz o quê, no exato
        momento em que a pessoa está com pressa de consertar algo.
        """
        valores = dict(self.model.current_annotation.headers)
        if not valores:
            self._on_status("Este diagrama não tem header declarado; não há o que limpar.")
            return
        listados = "\n".join(f"    {nome} = {valor}" for nome, valor in sorted(valores.items()))
        if not messagebox.askokcancel(
            "Limpar os headers",
            f"Apagar {len(valores)} header(s) deste diagrama?\n\n{listados}\n\n"
            "Só deste diagrama, e não dá para desfazer. O lance, a vez e a partida escolhida "
            "na lista de candidatas ficam como estão.",
            icon=messagebox.WARNING,
            default=messagebox.CANCEL,
        ):
            self._on_status("Limpeza cancelada.")
            return

        apagados = self.model.clear_headers()
        self._persist()
        self.refresh(request_page=False)
        self._on_status(f"{len(apagados)} header(s) apagado(s) deste diagrama: {', '.join(apagados)}.")

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
        # Desligado onde nao ha header: um botao que responde "nao ha o que limpar" e um botao
        # que mente sobre estar disponivel, e a pergunta que ele abriria seria vazia.
        self.btn_clear.configure(state=tk.NORMAL if anotacao.headers else tk.DISABLED)
        self._refresh_candidates_button()

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
