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
import os
import threading
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from chess_diagram_ocr.config import DEFAULT_PDF_DIR, DEFAULT_READING_ORDER
from chess_diagram_ocr.gallery import DiagramAnnotation, load_annotations
from chess_diagram_ocr.gallery_scan import GalleryIndex, build_gallery_index, load_index, save_index
from chess_diagram_ocr.games_cache import PositionStore, open_store
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

from . import database_choice, scan_scope, strings, texto, tokens
from .busy import BusyRegistry, BusyToken
from .gallery_model import HEADER_FIELDS, GalleryModel, describe_origin
from .games_dialog import GamesDialog
from .review_panel import ReviewSink
from .tooltip import Tooltip

logger = logging.getLogger(__name__)

__all__ = ["BOARD_VIEW_SIZE", "LARGURA_DA_LATERAL", "LARGURA_MINIMA_DA_GALERIA", "GalleryPanel"]

BOARD_VIEW_SIZE = 420
"""Lado do recorte na tela. Fixo: a galeria é para percorrer, e um tamanho que muda a cada
diagrama faria a imagem pular sob o ponteiro a cada avanço."""

LARGURA_DA_LATERAL = 260
"""Largura reservada para a coluna "Headers do PGN", **medida** e não estimada (S-154).

O `winfo_reqwidth` da lateral montada é **240 px** em `ttk` puro e **246** sob o
`bootstrap-light` -- dez rótulos de campo, dez `Entry` de `width=26` e o `padding=8` do
`LabelFrame`, com o tema acrescentando 6 px de moldura. 260 é o maior dos dois com folga, e a
folga é o item: reservar o número exato de um tema deixa a coluna 6 px curta no outro, que é
a mesma família de defeito, menor.

`tests/test_ui_galeria_layout.py` compara este número com a medição de verdade -- acrescentar
um campo ao PGN sem mexer aqui falha o teste, em vez de voltar a cortar a coluna."""

FOLGA_DO_CORPO = 40
"""O que fica entre a lateral e o recorte, e nas bordas: `padx=(10, 0)` mais o `padding` do painel."""

LARGURA_MINIMA_DA_GALERIA = BOARD_VIEW_SIZE + LARGURA_DA_LATERAL + FOLGA_DO_CORPO
"""O que esta aba de fato precisa de largura, somado das partes (S-154).

**É este número que o painel esquerdo passou a ter de piso.** Os 420 de `LARGURA_MINIMA_ESQUERDA`
eram da S-31, de quando a Galeria não existia -- e a consequência estava fotografada: na posição
padrão do divisor sobravam ~680 px para 700 pedidos, e quem perdia era a lateral, porque o centro
já tinha tomado o espaço com `expand=True`. Campos cortados, "Copiar headers para to…" cortado, o
texto verde de procedência cortado."""

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


@dataclass
class _LivroVarrido:
    """O que a varredura de um livro produziu, ou por que ela não aconteceu.

    Os três campos são mutuamente exclusivos, e é de propósito que sejam três e não um estado:
    "pulado" e "falhou" contam histórias diferentes no relatório, e um `indice=None` sozinho não
    distinguiria as duas. É o mesmo `BookResult` do `cvoff-scan`, na versão que a janela precisa.
    """

    path: Path
    indice: GalleryIndex | None = None
    pulado: str = ""
    erro: Exception | None = None

    @property
    def resumo(self) -> str:
        if self.erro is not None:
            return f"{self.path.name}: erro — {self.erro}"
        if self.pulado:
            return f"{self.path.name}: pulado — {self.pulado}"
        indice = self.indice
        parcial = "" if indice is None or indice.complete else " (parcial)"
        return f"{self.path.name}: {len(indice or ())} diagrama(s){parcial}"


def _mesmo_arquivo(um: Path | None, outro: Path | None) -> bool:
    """O mesmo PDF, apesar de `..`, de barra invertida e de maiúsculas no Windows.

    Comparar `Path` cru diria que `PDF/livro.pdf` e `C:\\...\\PDF\\Livro.pdf` são livros
    diferentes -- e é dessa comparação que dependem *duas* decisões: se a fila de revisão é
    alimentada, e se a galeria recarrega no fim. Errar para menos deixa a fila vazia sem dizer
    por quê; errar para mais mistura livros na mesma fila.
    """
    if um is None or outro is None:
        return False
    try:
        return os.path.normcase(Path(um).resolve()) == os.path.normcase(Path(outro).resolve())
    except OSError:  # pragma: no cover - caminho que o sistema recusa resolver
        return os.path.normcase(str(um)) == os.path.normcase(str(outro))


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
        review_sink: Callable[[], ReviewSink | None] | None = None,
        on_annotations_changed: Callable[[], None] = lambda: None,
        busy: BusyRegistry | None = None,
        ask_scan_scope: Callable[[Path | None], scan_scope.ScanScope | None] | None = None,
        ask_databases: Callable[[Sequence[Path]], Sequence[Path] | None] | None = None,
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
        self._on_annotations_changed = on_annotations_changed
        """A anotação de exportação deste livro mudou -- quem pinta o violeta da página precisa
        saber (S-116). Padrão neutro: a aba abre sozinha num roteiro de teste."""
        self._ask_scan_scope = ask_scan_scope
        """Quem pergunta **quais livros** varrer. `None` abre o diálogo de verdade.

        Recebe o livro aberto (ou `None`) e devolve o escopo escolhido, ou `None` se a pessoa
        desistiu. Existe injetável porque uma janela modal não se dirige de um roteiro de teste."""

        self._ask_databases = ask_databases
        """Quem pergunta **em quais bases** procurar. `None` abre o diálogo de verdade."""

        self._bases: tuple[Path, ...] | None = None
        """As bases escolhidas nesta sessão. `None` é "ninguém escolheu ainda" -- e aí valem
        todos os `.pgn` da pasta, que é o que a S-93 fixou e continua sendo o padrão da caixa.

        A escolha vale para a sessão e para **tudo** que lê base nesta aba: as duas buscas, o
        cache de posições e a lista de candidatas. Guardá-la só dentro de uma das buscas faria a
        janela procurar num conjunto e responder com o cache de outro."""

        self._review_sink = review_sink
        """Quem quer a fila de revisão desta varredura (S-119). Mesma razão do de cima: esta
        aba não conhece a de Revisão, ela só oferece o que leu a quem a janela apontar. `None`
        varre só para a Galeria, que é o que um roteiro de teste monta."""

        self._busy_registry = busy
        """Onde as três operações longas desta aba se declaram (S-112). `None` fora do app --
        a aba tem de abrir num roteiro de teste que não montou registro nenhum."""
        self._busy_token: BusyToken | None = None

        self.model = GalleryModel()
        self._store: PositionStore | None = None
        """A conexão aberta com o cache de posições (S-140). Uma por painel, e não por livro.

        Trocar de livro deixou de ler artefato nenhum: a mesma conexão responde sobre o livro
        novo, e enxerga o que outro processo gravou desde que ela foi aberta -- cada consulta
        abre a sua leitura. Ela só é refeita quando a **base** muda debaixo da sessão, que é a
        única coisa que invalida o que está guardado."""
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
        self.btn_scan = ttk.Button(topo, text=strings.VARRER_LIVRO, command=self.scan)
        self.btn_scan.pack(side=tk.LEFT)
        Tooltip(self.btn_scan).set_text(
            "Pergunta antes quais livros varrer: o que está aberto, outros escolhidos em disco, "
            f"ou todos os .pdf de {DEFAULT_PDF_DIR.name}. Com mais de um livro, os que já têm "
            "índice completo são pulados."
        )
        self.btn_cancel = ttk.Button(topo, text="Cancelar", command=self.cancel_scan, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=6)
        Tooltip(
            self.btn_cancel,
            "Só fica ativo enquanto uma varredura ou busca está rodando.\n"
            "A varredura do livro retoma da página seguinte à última terminada; a busca por\n"
            "posição descarta a passada inteira, porque meia base lida dá contagens que não valem.",
        )
        # Os dois caminhos, lado a lado e com o criterio no proprio rotulo: "na base" nao
        # distinguia mais nada depois que a busca por posicao virou botao tambem (S-92).
        self.btn_games = ttk.Button(topo, text="Buscar por nome", command=self.search_database)
        self.btn_games.pack(side=tk.LEFT, padx=6)
        Tooltip(self.btn_games).set_text(
            "Procura na base de partidas os diagramas cuja legenda traz os jogadores, e "
            "preenche lance, vez e headers -- só onde estiver vazio. Uma passada pela base, "
            "e nada sai da máquina. Pergunta antes em quais .pgn procurar."
        )
        self.btn_positions = ttk.Button(topo, text="Buscar pela posição", command=self.search_by_position)
        self.btn_positions.pack(side=tk.LEFT, padx=6)
        Tooltip(self.btn_positions).set_text(
            "Procura pelas 64 casas de cada diagrama, e não pela legenda: alcança todo diagrama, "
            "inclusive os sem nome nenhum impresso. Reproduz os lances da base inteira -- cerca "
            "de meia hora na primeira vez, segundos nas seguintes, porque a resposta fica "
            "guardada. Dá para cancelar. Pergunta antes em quais .pgn procurar -- e cada "
            "conjunto de bases guarda as respostas dele em separado."
        )
        ttk.Label(topo, textvariable=self.scan_var).pack(side=tk.LEFT, padx=10)

        corpo = ttk.Frame(self)
        corpo.pack(fill=tk.BOTH, expand=True, pady=6)

        # A lateral primeiro: ela reserva a largura que pede, e o centro fica com o resto (S-154).
        self._build_side_frame(corpo)

        centro = ttk.Frame(corpo)
        centro.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(centro, width=BOARD_VIEW_SIZE, height=BOARD_VIEW_SIZE, highlightthickness=1)
        self.canvas.pack()
        ttk.Label(centro, textvariable=self.position_var).pack(pady=(6, 0))

        navegacao = ttk.Frame(centro)
        navegacao.pack(pady=4)
        ttk.Button(navegacao, text=strings.PRIMEIRO, width=4, command=lambda: self._go(0, absolute=True)).pack(side=tk.LEFT)
        ttk.Button(navegacao, text=f"{strings.ANTERIOR} anterior", command=lambda: self._go(-1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(navegacao, text=f"próximo {strings.PROXIMO}", command=lambda: self._go(1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(navegacao, text=strings.ULTIMO, width=4, command=lambda: self._go(-1, absolute=True)).pack(side=tk.LEFT)

        self._build_caption(centro)
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
        lateral = ttk.LabelFrame(parent, text=strings.CABECALHOS_DO_PGN, padding=8)
        # `side=RIGHT`, e empacotada **antes** do centro (S-154). O `pack` reparte na ordem em
        # que recebe, e o `expand=True` do centro tomava tudo: a lateral -- que são os controles
        # que gravam a procedência de uma partida, o produto da S-83 à S-94 inteira -- ficava
        # com o que sobrasse, e não sobrava. Reservar a largura dela primeiro é o item.
        lateral.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self.lateral = lateral

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
            "nenhum outro diagrama.\n"
            "Fica cinza quando este diagrama não tem nenhum header preenchido."
        )

        # A procedencia da base fica **junto dos campos que ela preencheu**, e nao na barra de
        # status: a barra fala do ultimo gesto, e esta pergunta ("quem preencheu isto?") se faz
        # ao chegar num diagrama, que pode ser dias depois da busca.
        texto.acompanhar(
            ttk.Label(lateral, textvariable=self.origin_var, foreground=tokens.RESERVA[tokens.PRONTO_TEXTO])
        ).grid(row=livre + 5, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # A lista de partidas fica **junto da procedencia**: as duas respondem "de onde veio
        # isto?", e a lista e o unico caminho para os 350 diagramas do acervo em que a base
        # sabe a resposta e nenhuma regra sabe qual das candidatas e (S-86).
        self.btn_candidates = ttk.Button(lateral, text="Partidas da base", command=self.open_games_dialog)
        self.btn_candidates.grid(row=livre + 6, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.btn_candidates.configure(state=tk.DISABLED)
        Tooltip(self.btn_candidates).set_text(
            "As partidas da base que contêm esta posição. Escolher uma preenche lance, vez e "
            "headers, e a escolha fica registrada -- uma nova busca na base não a desfaz.\n"
            "Fica cinza enquanto a busca na base não achou candidata para este diagrama."
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
            "Não recupera o que a cópia sobrescreveu -- por isso a pergunta antes.\n"
            "Fica cinza até haver uma cópia desta sessão para desfazer."
        )

    def _build_footer(self) -> None:
        rodape = ttk.LabelFrame(self, text="Este diagrama", padding=8)
        rodape.pack(fill=tk.X)

        ttk.Label(rodape, text="Lance").pack(side=tk.LEFT)
        lance = ttk.Entry(rodape, textvariable=self.move_var, width=6)
        lance.pack(side=tk.LEFT, padx=(4, 12))
        lance.bind("<FocusOut>", lambda _evento: self._commit_move())
        lance.bind("<Return>", lambda _evento: self._commit_move())

        ttk.Label(rodape, text=strings.LADO_A_JOGAR).pack(side=tk.LEFT)
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
        """Pergunta **quais livros** e varre os escolhidos, um a um, em thread (S-119).

        Até 2026-08-18 esta passada e a da fila de revisão eram duas: o mesmo
        `iter_pdf_diagrams`, os mesmos parâmetros, arquivos diferentes, e nenhuma consumindo o
        resultado da outra. Medido no `PDF/1000 Chess Problems` (420 páginas): **338 s + 299 s**.
        Agora o índice desta aba é o superconjunto -- todo diagrama, sem gate -- e a fila é
        montada do mesmo fluxo, pelo `ReviewSink`.

        **O escopo passou a ser pergunta, e não pressuposto.** O botão só sabia varrer o livro
        aberto, e sem PDF na tela ele recusava; quem quisesse os outros do acervo tinha o
        `cvoff-scan --all` e mais nada -- linha de comando para o mesmo gesto que o botão do
        lado já fazia. Ver `scan_scope` para os três escopos e para por que "pular os já
        completos" só vale quando há mais de um livro.
        """
        if self._scanning:
            return
        escopo = self._ask_scope()
        if escopo is None:
            # Desistiu no diálogo: nem rodapé, nem log. Cancelar não é evento.
            return
        if escopo.is_empty:
            # Pré-condição: rodapé com severidade de aviso, e não caixa modal (S-164).
            self._on_status("Nenhum livro para varrer: abra um PDF, escolha um em disco ou ponha .pdf na pasta padrão.")
            return
        self._start_scan(escopo)

    def _ask_scope(self) -> scan_scope.ScanScope | None:
        """O diálogo do escopo, ou o que o teste injetou no lugar dele.

        Mesma razão do `campos.linha_de_caminho`: uma janela modal do sistema não se dirige de
        um roteiro, e o que se quer afirmar é que **a lista escolhida vira varredura** -- não
        que o Tk sabe desenhar rádios.
        """
        if self._ask_scan_scope is not None:
            return self._ask_scan_scope(self._pdf_path())
        return scan_scope.ask_scan_scope(self, open_book=self._pdf_path(), folder=DEFAULT_PDF_DIR)

    def _start_scan(self, escopo: scan_scope.ScanScope) -> None:
        aberto = self._pdf_path()
        # A fila de revisão é **do livro aberto**: o `ReviewSink` nasce ligado ao `pdf_path` da
        # janela (ver `ScanRequest`), e alimentá-lo com diagramas de outro livro montaria uma
        # fila que diz uma procedência e carrega outra. Varrer o acervo grava o índice de cada
        # livro; a fila continua sendo a do que está na tela -- e só se ele estiver no lote.
        varre_o_aberto = aberto is not None and any(_mesmo_arquivo(aberto, livro) for livro in escopo.books)

        self._scanning = True
        self._cancel.clear()
        # Criado aqui, na thread do Tk, porque ele le os widgets de configuracao da janela --
        # e so aqui. Nada de disco: ver `ReviewSink`.
        coletor = self._review_sink() if self._review_sink is not None and varre_o_aberto else None
        # `loses_work=False` desde a S-120: a varredura retoma da página seguinte à última
        # terminada, então fechar a janela custa **a página em curso**, e não o livro. Era
        # `True` na S-112, com o comentário nomeando este item como o que inverteria o valor.
        detalhe = escopo.books[0].name if len(escopo.books) == 1 else f"{len(escopo.books)} livros"
        self._register_busy("varredura do livro", loses_work=False, detail=detalhe)
        self._busy(True)
        self.scan_var.set("varrendo...")
        threading.Thread(target=self._scan_worker, args=(escopo, coletor, aberto), daemon=True).start()

    def cancel_scan(self) -> None:
        """Cancela a operação longa em curso -- e o que se perde depende de qual é ela.

        A varredura do livro não descarta o que já leu (ver `build_gallery_index`), e a busca
        por posição **descarta a passada inteira** (ver `scan_by_positions`): meia base lida dá
        contagens que não valem, e é a contagem que decide se preencher é honesto.
        """
        self._cancel.set()
        self.scan_var.set("cancelando...")

    def _scan_worker(
        self,
        escopo: scan_scope.ScanScope,
        coletor: ReviewSink | None,
        aberto: Path | None,
    ) -> None:
        """Os livros do escopo, um a um, na mesma thread e com o mesmo modelo carregado.

        **Um livro que quebra não derruba o lote.** É a mesma decisão do `cvoff-scan` (S-121):
        com 34 livros, interromper no primeiro PDF corrompido faria a pessoa descobrir o
        problema três horas depois, com os 30 seguintes por varrer. O erro vira linha do
        relatório; o rastro completo fica no log.
        """
        resultados: list[_LivroVarrido] = []
        for numero, caminho in enumerate(escopo.books, start=1):
            if self._cancel.is_set():
                break
            resultados.append(
                self._scan_one(
                    caminho,
                    numero=numero,
                    livros=len(escopo.books),
                    coletor=coletor if _mesmo_arquivo(caminho, aberto) else None,
                    skip_complete=escopo.skip_complete,
                )
            )
        self.after(0, partial(self._scan_finished, escopo, resultados, coletor, aberto))

    def _scan_one(
        self,
        caminho: Path,
        *,
        numero: int,
        livros: int,
        coletor: ReviewSink | None,
        skip_complete: bool,
    ) -> _LivroVarrido:
        try:
            # Retomar de onde parou (S-120). O indice no disco pode ser parcial de uma
            # varredura cancelada ou de uma janela fechada, e `build_gallery_index` ignora
            # sozinho o que estiver completo -- aqui so se entrega o que ha.
            anterior = load_index(caminho)
            if skip_complete and anterior is not None and anterior.complete and anterior.entries:
                # Ler o disco aqui, e nao no dialogo: sao 34 arquivos, e o laco do Tk nao abre
                # arquivo para desenhar botao (S-116).
                return _LivroVarrido(caminho, pulado=f"{len(anterior.entries)} diagrama(s), índice completo")
            # `model_session` empresta o modelo do servico em vez de carregar outro: e a
            # mesma razao da S-57, e a varredura da galeria e tao longa quanto a da fila.
            indice = build_gallery_index(
                caminho,
                self._model_path(),
                resume_from=anterior,
                max_boards_per_page=self._max_boards(),
                reading_order=DEFAULT_READING_ORDER,
                cancel_event=self._cancel,
                progress_callback=partial(
                    self._progress, coletor=coletor, nome=caminho.name, numero=numero, livros=livros
                ),
                model_session=self._service.model_session(self._model_path()),
                caption_reader=getattr(self._service, "caption_reader", None),
                # A fila de revisao sai desta mesma passada (S-119). O `on_scanned` recebe o
                # diagrama com tudo o que a varredura produziu -- entropia, casas incertas, o
                # que o decodificador reparou --, que e o que a `GalleryEntry` nao carrega e a
                # prioridade da S-22 precisa.
                on_scanned=None if coletor is None else coletor.feed,
            )
            save_index(caminho, indice)
            return _LivroVarrido(caminho, indice=indice)
        except Exception as exc:  # noqa: BLE001 - a varredura toca modelo, PDF e disco
            logger.exception("Varredura de %s falhou.", caminho.name)
            return _LivroVarrido(caminho, erro=exc)

    def _progress(
        self,
        pagina: int,
        total: int,
        _diagramas: int,
        _aceitos: int,
        coletor: ReviewSink | None = None,
        nome: str = "",
        numero: int = 1,
        livros: int = 1,
    ) -> None:
        onde = "" if livros == 1 else f"livro {numero} de {livros} · "
        if self._busy_token is not None:
            # O número no registro é o que vira barra determinada no rodapé (S-164). **Um só**:
            # a varredura é uma desde a S-119, e dois registros para ela dariam duas barras
            # contando a mesma coisa. Com vários livros, a barra é a do livro em curso e o
            # texto diz de qual -- uma barra que somasse páginas de livros de tamanhos
            # diferentes andaria em saltos que não querem dizer nada.
            self._busy_token.update(f"{onde}página {pagina} de {total}", feito=pagina, total=total)
        rotulo = f"varrendo {onde}página {pagina} de {total}..." if livros == 1 else f"{onde}{nome[:24]}: página {pagina} de {total}..."
        self.after(0, lambda: self.scan_var.set(rotulo))
        if coletor is not None:
            coletor.progress(pagina, total)

    def _scan_finished(
        self,
        escopo: scan_scope.ScanScope,
        resultados: list[_LivroVarrido],
        coletor: ReviewSink | None,
        aberto: Path | None,
    ) -> None:
        """Fecha a operação e conta o que aconteceu -- por livro, ou em uma linha para o lote.

        **A fila de revisão é entregue daqui**, e não da thread: `_apply_scan` grava o arquivo
        e redesenha uma tabela, e as duas coisas são do laço do Tk (S-119).
        """
        self._scanning = False
        self._busy(False)

        # Só o livro aberto volta para a tela desta aba. Carregar o índice de outro deixaria a
        # galeria mostrando diagramas de um livro que o visualizador não tem aberto, e a
        # sincronia das duas abas (S-67) passaria a virar páginas erradas. O índice dos outros
        # está no disco e aparece quando a pessoa abrir aquele livro.
        if aberto is not None and any(_mesmo_arquivo(item.path, aberto) for item in resultados):
            self.load_pdf(aberto)
        if coletor is not None:
            # A fila fica como estava quando nada foi lido; o que nao pode ficar e a aba de
            # revisao com o botao cinza para sempre por causa do que aconteceu deste lado.
            coletor.deliver(cancelled=self._cancel.is_set())

        if not resultados:
            self.scan_var.set("cancelada")
            self._on_status("Varredura cancelada antes do primeiro livro: nada foi lido.")
            return
        if len(resultados) == 1 and len(escopo.books) == 1:
            self._report_one_book(resultados[0], aberto)
            return
        self._report_many_books(escopo, resultados)

    def _report_one_book(self, item: _LivroVarrido, aberto: Path | None) -> None:
        """Diz **quanto do livro** foi varrido, e não só quantos diagramas saíram (S-120).

        Um índice truncado é indistinguível de um completo pelo número de diagramas -- é a
        parte do defeito que custa mais que o tempo perdido --, então o estado parcial vira
        texto na tela, com a página em que a varredura parou e o convite a continuar.
        """
        if item.erro is not None:
            self.scan_var.set("falhou")
            messagebox.showerror("Galeria", f"Não foi possível varrer o livro:\n{item.erro}")
            return
        if item.pulado:  # defensivo: com um livro só o escopo não pula nada
            self.scan_var.set("pulado")
            self._on_status(f"Galeria: {item.path.name} pulado — {item.pulado}.")
            return

        indice = item.indice
        do_aberto = aberto is not None and _mesmo_arquivo(item.path, aberto)
        # Do modelo quando é o livro da tela (é ele que a pessoa vai navegar agora), do índice
        # quando não é: o modelo não foi trocado, e citar o número dele seria falar do livro errado.
        quantos = len(self.model) if do_aberto else len(indice or ())
        onde = "" if do_aberto else f" em {item.path.name}"
        completo = bool(getattr(indice, "complete", True))
        ate = int(getattr(indice, "last_page_done", -1))
        if completo:
            self.scan_var.set(f"{quantos} diagrama(s)")
            self._on_status(f"Galeria: {quantos} diagrama(s) varrido(s){onde}, livro inteiro.")
            return
        self.scan_var.set(f"{quantos} diagrama(s) — parcial até a página {ate + 1}")
        self._on_status(
            f"Galeria: **parcial**. {quantos} diagrama(s){onde} até a página {ate + 1}; "
            "varrer de novo continua daí, sem repetir o que já foi lido."
        )

    def _report_many_books(self, escopo: scan_scope.ScanScope, resultados: list[_LivroVarrido]) -> None:
        """Uma linha para o lote inteiro, e o detalhe de cada livro no log.

        Rodapé e não caixa modal (S-164): varrer o acervo é o gesto que se deixa rodando, e uma
        modal esperando clique no fim seria a janela travada de que a S-121 tirou o projeto.
        """
        feitos = [item for item in resultados if item.indice is not None]
        pulados = [item for item in resultados if item.pulado]
        erros = [item for item in resultados if item.erro is not None]
        parciais = [item for item in feitos if not item.indice.complete]  # type: ignore[union-attr]
        diagramas = sum(len(item.indice or ()) for item in feitos)

        partes = [f"{len(feitos)} livro(s) varrido(s), {diagramas} diagrama(s)"]
        if parciais:
            partes.append(f"{len(parciais)} parcial(is) — varrer de novo continua de onde parou")
        if pulados:
            partes.append(f"{len(pulados)} pulado(s) por índice já completo")
        if erros:
            partes.append(f"{len(erros)} com erro (o rastro está no log)")
        faltaram = len(escopo.books) - len(resultados)
        if faltaram:
            partes.append(f"cancelada com {faltaram} livro(s) sem varrer")

        for item in resultados:
            logger.info("Varredura: %s", item.resumo)
        self.scan_var.set(f"{len(feitos)} de {len(escopo.books)} livro(s)")
        self._on_status("Galeria: " + "; ".join(partes) + ".")

    # ------------------------------------------------------------------- busca na base (S-72)

    def _bases_atuais(self) -> list[Path]:
        """As bases que valem agora: as escolhidas, ou a pasta inteira enquanto ninguém escolheu."""
        return database_paths() if self._bases is None else list(self._bases)

    def _store_path(self, bases: Sequence[Path]) -> Path:
        """O arquivo de cache **deste** conjunto de bases. Ver `database_choice.store_path_for`."""
        return database_choice.store_path_for(bases, default_bases=database_paths())

    def _ask_bases(self) -> list[Path] | None:
        """Pergunta em quais bases procurar. `None` é "desistiu", e aí nada acontece.

        A resposta é adotada **antes** de a busca começar: trocar o conjunto troca o cache de
        posições junto (cada conjunto tem o seu arquivo, ver `database_choice.store_path_for`),
        e uma busca que rodasse com o conjunto novo e o cache antigo devolveria contagens de
        uma base sobre as partidas de outra.
        """
        atuais = self._bases_atuais()
        if self._ask_databases is not None:
            escolhidas = self._ask_databases(atuais)
        else:
            escolhidas = database_choice.ask_databases(self, selected=atuais)
        if escolhidas is None:
            return None
        escolhidas = list(escolhidas)
        if escolhidas == atuais:
            # Confirmar o que já valia não pode custar uma reabertura do cache: a conexão em
            # pé responde pelo mesmo conjunto, e fechá-la e reabri-la seria trabalho por nada.
            self._bases = tuple(escolhidas)
            return escolhidas
        self._bases = tuple(escolhidas)
        self.model.database_paths = tuple(escolhidas)
        # Reabre o cache no arquivo deste conjunto. Sem isto a conexão aberta continuaria
        # respondendo pelo conjunto anterior -- e ela é a que preenche a lista de candidatas.
        self._load_position_cache()
        return escolhidas

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
            # Pré-condição de uma frase: rodapé (S-164). O `_SEM_BASE` logo abaixo continua
            # modal -- ele é uma instrução de várias linhas, e o rodapé é uma linha só.
            self._on_status("Varra o livro antes: a busca usa as legendas dos diagramas.")
            return
        if not self._bases_atuais():
            messagebox.showinfo("Base de partidas", _SEM_BASE)
            return
        bases = self._ask_bases()
        if not bases:
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
            # Pré-condição de uma frase: rodapé (S-164).
            self._on_status("Varra o livro antes: a busca usa as posições dos diagramas.")
            return
        if not self._bases_atuais():
            messagebox.showinfo("Base de partidas", _SEM_BASE)
            return
        bases = self._ask_bases()
        if not bases:
            return

        alvos = {entrada.placement for entrada in self.model.index.entries if entrada.placement}
        self._load_position_cache()
        if self._store is None:
            self._on_status("O cache de posições não abriu; a busca precisa dele para não repetir a base.")
            return
        faltando = self._store.missing(alvos)
        if not faltando:
            self._positions_done(alvos, games_read=0)
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
            target=self._positions_worker,
            args=(bases, alvos, faltando, self._store_path(bases)),
            daemon=True,
        ).start()

    def _positions_worker(
        self, bases: list[Path], alvos: set[str], faltando: set[str], store_path: Path | None = None
    ) -> None:
        """A passada pela base, fora da thread do Tk -- **com a conexão dela** (S-140).

        A conexão de `self._store` é da thread da janela e continua respondendo à tela
        enquanto isto roda; uma segunda, aberta aqui e fechada aqui, é o que evita duas threads
        no mesmo objeto de banco. As linhas gravadas aparecem para a primeira sozinhas: cada
        consulta dela abre a sua própria leitura do arquivo.
        """
        try:
            indice = scan_by_positions(bases, faltando, progress=self._positions_progress, cancel=self._cancel)
            if self._cancel.is_set():
                self.after(0, self._positions_cancelled)
                return
            if not indice.complete:
                # Descartada sem ninguem ter cancelado: um processo morreu no meio (S-171). O
                # cache recusa a gravacao sozinho; o que falta e a tela dizer o que houve, em
                # vez de anunciar "0 casamentos" como se a base tivesse respondido isso.
                self.after(0, self._positions_incomplete)
                return
            # `faltando` inteiro, e nao so as posicoes que casaram: uma posicao que a base nao
            # conhece precisa ficar registrada como **perguntada**, senao ela volta ao alvo de
            # toda busca futura -- e no acervo medido essas sao a maioria (S-84).
            # No arquivo **deste** conjunto de bases: a conexao da tela ja esta nele, e gravar
            # no caminho padrao misturaria as respostas de dois conjuntos no mesmo cache.
            with open_store(store_path or self._store_path(bases), database=bases) as gravacao:
                gravacao.update(indice, faltando)
            self.after(0, partial(self._positions_done, alvos, indice.games_read))
        except Exception as exc:  # noqa: BLE001 - a base e de terceiro e o arquivo e enorme
            logger.exception("Busca por posição falhou.")
            self.after(0, partial(self._search_failed, exc))

    def _positions_progress(self, feitos: int, total: int) -> None:
        """Vem da thread da busca; a `StringVar` só pode ser tocada pelo laço do Tk."""
        if self._busy_token is not None:
            # A mais cara do programa -- ~56 min medidos na Fase 13 -- e a que mais precisa de
            # uma fração: só o número diz se vale esperar ou cancelar agora (S-164).
            self._busy_token.update(f"pedaço {feitos} de {total}", feito=feitos, total=total)
        self.after(0, lambda: self.scan_var.set(f"base: pedaço {feitos} de {total}..."))

    def _positions_done(self, alvos: set[str], games_read: int) -> None:
        """Aplica o que a base respondeu e **deixa o cache em pé** para a lista de candidatas.

        O botão "Partidas da base" acende no mesmo gesto, e agora sem passar objeto nenhum de
        volta: a conexão que a tela já tem enxerga as linhas que a thread gravou. Mandar a
        pessoa reabrir o livro para vê-las seria esconder o que ela pagou meia hora para ter.
        """
        self._scanning = False
        self._busy(False)
        cache = self._store
        if cache is None:  # pragma: no cover - so acontece se o cache fechou no meio
            self._on_status("A busca terminou, mas o cache de posições fechou antes de responder.")
            return
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

    def _positions_incomplete(self) -> None:
        """A passada morreu no meio, e ninguém cancelou (S-171).

        A frase é diferente da de cancelamento de propósito: ali a pessoa sabe o que fez, aqui
        ela não fez nada e precisa saber que **pode tentar de novo** -- nada foi gravado, então
        as colocações continuam por perguntar.
        """
        self._scanning = False
        self._busy(False)
        self.scan_var.set("interrompida")
        self._on_status(
            "A busca por posição foi interrompida: um dos processos de leitura da base morreu. "
            "Nada foi gravado, e as posições continuam por perguntar -- dá para tentar de novo. "
            "O arquivo de log tem a linha com o que aconteceu."
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
        meia hora: a varredura já respondeu, e a resposta está em `data/games_positions.sqlite`.
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
        """Volta da janela de candidatas: grava, redesenha e conta o que houve.

        **E avisa quem pinta as caixas da página** (S-116, corte 2). Escolher uma candidata é o
        que grava `confirmed_from`, e é o violeta do visualizador. Até aqui ele só reaparecia na
        próxima gravação de amostra -- porque o `Ctrl+S` relia as anotações do livro de
        carona --, o que era acidente antes e passaria a ser defeito depois de o `Ctrl+S`
        parar de ler. Agora quem muda a anotação é quem avisa.
        """
        self._persist()
        self.refresh(request_page=False)
        self._on_annotations_changed()
        self._on_status(mensagem)

    def _load_position_cache(self) -> None:
        """Deixa o cache de posições aberto e apontado à base de agora. Falha em silêncio.

        Sem cache o botão fica desligado e o resto da aba funciona igual: a lista é um caminho
        a mais, e não uma pré-condição para anotar um livro.

        **Aberto uma vez, e não relido por livro (S-140).** Até 2026-08-18 isto era um
        `json.loads` do acervo inteiro a cada troca de PDF -- ~4,2 s de parse e ~190 MB para
        responder sobre as ~1.400 posições de um livro. Agora abrir é uma conexão, e o que ela
        custa não cresce com o acervo. A base é reconferida a cada chamada porque é a única
        coisa que pode ter mudado: um `.pgn` a mais na pasta muda as contagens de tudo que está
        guardado, e uma conexão aberta antes dele responderia o número de ontem.
        """
        bases = self._bases_atuais()
        caminho = self._store_path(bases)
        try:
            if self._store is not None:
                if self._store.path == caminho and self._store.matches(bases):
                    self.model.position_cache = self._store
                    return
                self._store.close()
                self._store = None
            self._store = open_store(caminho, database=bases)
            self.model.position_cache = self._store
        except Exception:  # noqa: BLE001 - cache e material derivado; sem ele a aba segue
            logger.exception("Não foi possível ler o cache de posições.")
            self._store = None
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
            database_paths=tuple(self._bases_atuais()),
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
