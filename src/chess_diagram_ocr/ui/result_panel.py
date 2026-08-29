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
from collections.abc import Callable, Collection, Sequence
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np

from chess_diagram_ocr.atomic_io import read_image
from chess_diagram_ocr.dataset_browser import DatasetRow, update_row
from chess_diagram_ocr.fen_utils import is_valid_fen, square_name
from chess_diagram_ocr.labels import SavedSample
from chess_diagram_ocr.review_queue import ReviewItem
from chess_diagram_ocr.semantics import compose_fen
from chess_diagram_ocr.service import OcrService, RecognitionOrigin, RecognizedDiagram
from chess_diagram_ocr.settings import LocalReaderSettings, RemoteFenSettings

from . import atalhos, board_edit, comandos, estilos, strings, texto, theme, tipografia, tokens
from .board_widget import InteractiveBoard, PieceImages
from .editor_model import DiagramEditorModel, EditorBinding, SaveKind, SaveTarget
from .historico import Historico
from .legality import ILLEGAL_SAVE_TITLE, explain_position, illegal_save_question
from .net_button import NetCorrectionButton
from .page_results import PageOcrParams, PageResults, PageResultsCache, PageSwitch, decide_page_switch
from .second_opinion_button import SecondOpinionButton
from .tooltip import Tooltip

logger = logging.getLogger(__name__)

MENSAGEM_VAZIA = (
    "Nenhum diagrama aberto. Clique num diagrama marcado da página, "
    'ou use "OCR todos diagramas" para ler a página inteira.'
)
"""O que a aba diz quando não há o que editar (S-170).

Ela **diz o que fazer**, e não que está vazia: "sem dados" descreve a tela; esta frase descreve o
gesto seguinte, que é o que a pessoa está procurando quando lê um estado vazio."""

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
    image_bgr = read_image(path)
    if image_bgr is None:
        return None
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


MOTIVO_SEM_DIAGRAMA = "Fica cinza enquanto não há diagrama aberto."
MOTIVO_SEM_DESFAZER = "Fica cinza enquanto nada foi mudado neste diagrama: a pilha é por diagrama."
MOTIVO_SEM_REFAZER = "Fica cinza enquanto nada foi desfeito -- só há o que refazer depois de um Ctrl+Z."
"""Por que cada botão do histórico está cinza (S-165/S-229).

Três frases e não uma: "não há diagrama" e "não há o que desfazer" são situações diferentes, e uma
dica que servisse às duas não responderia a pergunta que a pessoa tem diante do botão."""


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
        on_sample_saved: Callable[[Sequence[SavedSample]], None],
        remote_fen: Callable[[], RemoteFenSettings],
        on_remote_consent: Callable[[RemoteFenSettings], bool],
        local_reader: Callable[[], LocalReaderSettings] = LocalReaderSettings,
        on_selection_changed: Callable[[int | None], None] = lambda _indice: None,
        saved_diagrams: Callable[[str, int], Collection[int]] = lambda _livro, _pagina: (),
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
        """Chamado depois de gravar ou regravar amostra: a aba Dataset precisa reler.

        **Recebe o que foi gravado desde a S-116 (corte 2)**, e não um aviso vazio. Com o
        aviso, quem ouvia relia o `labels.csv` inteiro para descobrir uma linha que este
        processo acabara de escrever -- 30,9 ms sobre 3.936 linhas, no laço mais interno do
        projeto. Uma sequência vazia é resposta: "o dataset mudou e nenhum diagrama novo ficou
        verde", que é exatamente o caso de regravar uma linha que já existia."""

        self._saved_diagrams = saved_diagrams
        """Quais diagramas de `(livro, página)` já têm amostra gravada, em base 0 (S-451).

        Mora fora do painel porque o índice é da janela: ela o lê do `labels.csv` ao abrir o
        PDF e o mantém a cada gravação (ver `labels.note_saved_diagram`). Relê-lo aqui traria
        de volta a releitura de arquivo que a S-116 tirou deste caminho. O padrão devolve
        vazio -- quem monta o painel sem passar nada não vê pergunta nenhuma, que é melhor que
        ver uma pergunta errada."""

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

        self.historico = Historico()
        """Desfazer e refazer do tabuleiro (S-229). Uma pilha de posições, **por diagrama**.

        Mora no painel e não no `DiagramEditorModel` porque o que ele guarda é do **diagrama
        aberto agora**, e não do carregamento: as listas do modelo sobrevivem à navegação entre
        diagramas da mesma página, e a pilha não pode -- desfazer para dentro de outra posição é
        pior que não desfazer. `_zerar_historico` é chamado de todo lugar que troca o que está no
        tabuleiro, e é a única forma de a pilha começar."""

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

        self._dicas_de_historico: dict[str, Tooltip] = {}
        """A dica de cada botão do histórico, para ser **reescrita** e não recriada (S-229)."""

        self._edicoes = 0
        """Quantas mudanças de posição este painel registrou. É o `edicao` do `ui/desfazivel.py`.

        Existe por causa da tecla, e não por curiosidade: com o foco fora dos dois desfazíveis --
        o cursor num botão da barra, que é onde ele fica depois de qualquer clique -- quem desfaz é
        **o último que recebeu edição** (S-243). Sem este número, `Ctrl+Z` logo depois de uma
        edição não faria nada, que é o defeito clássico deste desenho."""

        self._build(piece_images)
        # **Depois de montar, e não só ao limpar** (S-170): sem esta chamada o tabuleiro abria na
        # posição inicial que o `InteractiveBoard` desenha por padrão, com a FEN vazia ao lado.
        self.update_views()

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
        ttk.Label(zoom_row, text=strings.ZOOM_DO_TABULEIRO).pack(side=tk.LEFT)
        ttk.Button(zoom_row, text="-", width=3, command=lambda: self.zoom(-0.1)).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(zoom_row, text="+", width=3, command=lambda: self.zoom(0.1)).pack(side=tk.LEFT, padx=(2, 6))
        self.lbl_zoom = ttk.Label(zoom_row, text="85%")
        self.lbl_zoom.pack(side=tk.LEFT)
        ttk.Checkbutton(
            zoom_row, text=strings.MAPA_DE_INCERTEZA, variable=self.heatmap_var, command=self.on_heatmap_toggle
        ).pack(side=tk.RIGHT)

        # Desfazer, refazer e limpar (S-229), **junto do tabuleiro** e não na caixa da FEN: o que
        # os três revertem é a posição, e a distância entre o controle e o objeto que ele muda é o
        # que faz a pessoa procurar no menu. Os rótulos saem do catálogo (S-324) -- os três botões
        # antigos desta janela ainda os escrevem à mão, e essa dívida está registrada lá.
        edicao_row = ttk.Frame(caixa)
        edicao_row.pack(fill=tk.X, padx=8, pady=(4, 0))
        self.btn_desfazer = self._botao_de_historico(edicao_row, "desfazer", self.desfazer)
        self.btn_refazer = self._botao_de_historico(edicao_row, "refazer", self.refazer)
        self.btn_limpar = ttk.Button(
            edicao_row, text=comandos.rotulo_de_botao("limpar_tabuleiro"), command=self.limpar_tabuleiro
        )
        self.btn_limpar.pack(side=tk.LEFT, padx=6)
        Tooltip(
            self.btn_limpar,
            "Esvazia as 64 casas para montar a posição do zero.\n"
            "Fica cinza sem diagrama aberto, e é desfazível com Ctrl+Z.",
        )

        # O editor da S-20 no lugar do canvas somente-leitura: corrigir uma peça passa de
        # "contar casas e reescrever a FEN" para um arraste.
        self.board = InteractiveBoard(
            caixa,
            mode="edit",
            on_change=self.on_board_changed,
            on_select=self.on_square_selected,
            on_status=self._on_status,
            piece_images=piece_images,
            min_size=260,
            max_size=520,
        )
        self.board.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.board.set_heatmap_enabled(True)

        # A frase do estado vazio (S-170). Um `Label` que existe sempre e fica em branco quando há
        # diagrama: aparecer e sumir mudaria a altura do painel a cada leitura.
        self.vazio_var = tk.StringVar(value=MENSAGEM_VAZIA)
        lbl_vazio = ttk.Label(
            caixa,
            textvariable=self.vazio_var,
            justify=tk.LEFT,
            foreground=theme.cor_atual(tokens.TEXTO_SECUNDARIO),
        )
        texto.acompanhar(lbl_vazio).pack(anchor="w", padx=8, pady=(0, 6))
        theme.ao_repintar(lambda: lbl_vazio.configure(foreground=theme.cor_atual(tokens.TEXTO_SECUNDARIO)))

        legal = ttk.Frame(caixa)
        legal.pack(fill=tk.X, padx=8, pady=(0, 6))
        texto.acompanhar(ttk.Label(legal, textvariable=self.legality_var, justify=tk.LEFT)).pack(anchor="w")
        theme.pintar(
            ttk.Label(legal, textvariable=self.material_var), "foreground", tokens.TEXTO_SECUNDARIO
        ).pack(anchor="w")

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
        # Monoespaçada (S-149): é o dado central do produto, e em proporcional `1`, `l` e `I`
        # têm larguras diferentes -- duas leituras da mesma posição deixam de alinhar, que é
        # exatamente a comparação que a aba Revisão e a 2ª opinião pedem.
        entry = ttk.Entry(fen_box, textvariable=self.fen_var, font=theme.fonte_atual(tipografia.DADO))
        entry.pack(fill=tk.X, padx=8, pady=(0, 4))
        entry.bind("<Return>", lambda _event: self.apply_fen_edit())
        # E a tecla da tabela, ligada aqui de propósito (S-223). A guarda de foco de
        # `ui/shortcuts.py` cede **qualquer** atalho a um campo de texto, e é dentro deste campo
        # que `Ctrl+Enter` mais faz sentido -- então quem a liga é o próprio campo, pelo caminho
        # que a S-117 abriu. A sequência vem de `ui/atalhos.py`: a declaração continua sendo uma.
        entry.bind(atalhos.por_acao["aplicar_fen"].sequencia, lambda _event: self.apply_fen_edit())

        # Lado a jogar visivel e editavel (S-16/S-19). Até a Fase 3 o app não tinha onde
        # mostrar isso, e a informação -- quando o PDF a dava -- morria na exportação.
        side_row = ttk.Frame(fen_box)
        side_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Label(side_row, text=strings.LADO_A_JOGAR).pack(side=tk.LEFT)
        for valor, rotulo in strings.SIDE_LABELS.items():
            ttk.Radiobutton(
                side_row,
                text=rotulo,
                value=valor,
                variable=self.side_to_move_var,
                command=self.on_side_to_move_change,
            ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(side_row, textvariable=self.side_source_var).pack(side=tk.LEFT, padx=(10, 0))

        # Número do lance (S-71), ao lado do lado a jogar porque é a mesma leitura: os dois
        # saem da legenda impressa, e quem está com o livro aberto declara os dois de uma vez.
        # A gravação vai para a anotação da galeria -- ver `_commit_move_number`.
        # O rótulo **antes** do campo (S-170). Os dois estavam com `side=RIGHT`, e o `pack` põe o
        # primeiro mais à direita: na tela lia-se `[campo] Lance`, ao contrário da ordem de leitura
        # e ao contrário de todos os outros campos da janela. Empacotar o campo primeiro é o que
        # faz o rótulo aparecer à esquerda dele sem mudar o lado da linha em que os dois ficam.
        self.move_number_entry = ttk.Entry(side_row, textvariable=self.move_number_var, width=6)
        self.move_number_entry.pack(side=tk.RIGHT)
        ttk.Label(side_row, text="Lance").pack(side=tk.RIGHT, padx=(10, 4))
        self.move_number_entry.bind("<Return>", lambda _event: self._commit_move_number())
        self.move_number_entry.bind("<FocusOut>", lambda _event: self._commit_move_number())
        Tooltip(
            self.move_number_entry,
            "O número do lance da legenda impressa, para a exportação. Fica cinza quando o\n"
            "diagrama não veio de uma página do livro -- uma imagem solta não tem onde gravá-lo.",
        )

        acoes = ttk.Frame(fen_box)
        acoes.pack(fill=tk.X, padx=8, pady=(0, 6))
        self.btn_apply_fen = ttk.Button(acoes, text="Aplicar FEN", command=self.apply_fen_edit)
        self.btn_apply_fen.pack(side=tk.LEFT)
        self.btn_save = ttk.Button(
            acoes,
            text="Salvar posição reconhecida",
            style=estilos.estilo_de_botao(estilos.PRIMARIO),
            command=self.save_current,
        )
        self.btn_save.pack(side=tk.LEFT, padx=6)
        self.btn_save_all = ttk.Button(acoes, text="Salvar todos", command=self.save_all)
        self.btn_save_all.pack(side=tk.LEFT, padx=6)
        for botao in (self.btn_apply_fen, self.btn_save, self.btn_save_all):
            Tooltip(
                botao,
                "Fica cinza enquanto não há diagrama aberto: clique num diagrama marcado da\n"
                "página, ou use \"OCR todos diagramas\" para ler a página inteira.",
            )
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
                origin=self.model.origin,
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
            self._on_status(f"Página {page_index + 1}: sem reconhecimento ainda. Rode o OCR.")

    def _apply_page_results(self, guardado: PageResults, documento: str) -> None:
        self.model.adopt(
            guardado.items,
            guardado.fen_edits,
            guardado.side_edits,
            page_key=(documento, guardado.page_index),
            origin=guardado.origin,
            selected=guardado.clamped_index(),
        )
        self._sync_widgets_to_model(total=max(guardado.count, 1))
        self.after_idle(self.board.redraw)
        self._on_status(
            f"Página {guardado.page_index + 1}: {guardado.count} diagrama(s) do reconhecimento anterior"
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
        self._zerar_historico(idx)
        self.selected_diag_var.set(idx + 1)
        self.spin_diag.config(from_=1, to=total)
        self.fen_var.set(self.model.fen_at(idx))
        self.sync_side_widgets(idx)
        self.sync_move_number()
        self.update_views()
        self._on_selection_changed(idx if self.model.items else None)

    def clear(self) -> None:
        self.model.clear()
        self.historico.zerar()
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

        digitado = self.move_number_var.get().strip()
        atual = self._move_number_of(*alvo)
        if not digitado:
            if atual is not None:
                self._on_move_number(alvo[0], alvo[1], None)
                self._on_status(f"Diagrama {alvo[1] + 1}: número do lance apagado.")
            return

        try:
            numero = int(digitado)
        except ValueError:
            self._on_status(f"Número de lance inválido: {digitado!r}. Use um inteiro positivo.")
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
        self._zerar_historico(idx)
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

    def _registrar_no_historico(self, placement: str) -> bool:
        """Põe a posição na pilha e conta a edição (S-229/S-243).

        As duas coisas juntas num lugar só porque elas são a mesma: o que entra na pilha é o que
        conta como "este painel recebeu edição", e contar num lugar e empilhar noutro é como as
        duas divergiriam na próxima origem de mudança de posição.
        """
        mudou = self.historico.registrar(placement)
        if mudou:
            self._edicoes += 1
        return mudou

    @property
    def edicao(self) -> int:
        """Quantas edições de posição este painel recebeu -- ver `_edicoes` e `ui/desfazivel.py`."""
        return self._edicoes

    def contem(self, widget: object) -> bool:
        """Aquele widget é este painel ou está dentro dele? É como o foco escolhe o desfazível."""
        atual = widget
        for _ in range(40):
            if atual is None:
                return False
            if atual is self:
                return True
            atual = getattr(atual, "master", None)
        return False

    def apply_fen_edit(self) -> None:
        if not self.model.items:
            return
        self.sync_fen_from_entry()
        # A quarta origem (S-229). Só o campo de peças entra na pilha, que é o que ela guarda --
        # e é o mesmo recorte que `on_board_changed` já grava em `fen_edits` a cada clique.
        self._registrar_no_historico(board_edit.placement_of(self.model.fen_at()))
        self.update_views()

    def _mostrar_estado_vazio(self, vazio: bool) -> None:
        """Liga ou desliga o estado vazio: a frase, e as três ações que não têm o que fazer (S-170).

        **O que ele conserta.** Ao abrir, a aba mostrava um tabuleiro completo na posição inicial
        com o campo de FEN vazio -- parecia um diagrama reconhecido, e era o padrão do
        `InteractiveBoard`. Quem clicasse "Salvar posição reconhecida" ali gravava a posição inicial
        no `labels.csv` como se fosse leitura de uma página.

        O motivo de cada botão cinza está no tooltip, pela regra da S-165.
        """
        self.vazio_var.set(MENSAGEM_VAZIA if vazio else "")
        estado = tk.DISABLED if vazio else tk.NORMAL
        for botao in (self.btn_apply_fen, self.btn_save, self.btn_save_all, self.btn_limpar):
            botao.configure(state=estado)
        # Os dois do histórico têm uma segunda razão para ficar cinza -- pilha vazia --, e por
        # isso não entram no laço: quem decide os dois é `_atualizar_botoes_de_historico`, que já
        # sabe das duas razões e escreve a certa na dica.
        self._atualizar_botoes_de_historico()

    def update_views(self) -> None:
        self._mostrar_estado_vazio(not self.items)
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
        """Toda edição no tabuleiro reescreve a FEN -- o campo de texto segue funcionando.

        **Três das sete origens da S-229 passam por aqui**: pôr peça à mão, arrastar e apagar
        casa. É o que a pilha de estados compra sobre a pilha de gestos -- as três chegam como a
        posição de depois, e nenhuma delas precisou saber o próprio inverso.
        """
        if not self.model.apply_placement(placement):
            return
        self._registrar_no_historico(placement)
        self.fen_var.set(placement)
        self.update_legality()
        self._on_sync_study()
        self._atualizar_botoes_de_historico()

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

    # ------------------------------------------------------------ desfazer e refazer (S-229)

    def _botao_de_historico(self, pai: tk.Misc, acao: str, funcao: Callable[[], None]) -> ttk.Button:
        """Um dos dois botões do histórico, com a dica **trocável** presa a ele.

        Uma dica por botão, criada aqui e reescrita em `_atualizar_botoes_de_historico`. Recriar
        o `Tooltip` a cada mudança de estado perderia os `bind` -- é o que o docstring de
        `ui/tooltip.py` diz, e `set_text` existe por causa disso.
        """
        botao = ttk.Button(pai, text=comandos.rotulo_de_botao(acao), command=funcao)
        botao.pack(side=tk.LEFT, padx=(0, 6))
        self._dicas_de_historico[acao] = Tooltip(botao, "")
        return botao

    def _atualizar_botoes_de_historico(self) -> None:
        """Acende, apaga e **diz por quê** -- a regra da S-165, que achou 13 botões cinzas mudos.

        As duas razões de estar cinza são diferentes, e quem olha precisa saber qual é a sua: sem
        diagrama aberto não há posição nenhuma; com diagrama e a pilha vazia, não há mudança
        anterior *neste* diagrama -- que é a consequência de a pilha ser por diagrama, e a única
        forma de essa decisão aparecer para quem usa o programa.
        """
        tem_diagrama = bool(self.model.items)
        for botao, acao, pode, vazia in (
            (self.btn_desfazer, "desfazer", self.historico.pode_desfazer, MOTIVO_SEM_DESFAZER),
            (self.btn_refazer, "refazer", self.historico.pode_refazer, MOTIVO_SEM_REFAZER),
        ):
            botao.configure(state=tk.NORMAL if (tem_diagrama and pode) else tk.DISABLED)
            motivo = comandos.rotulo(acao) if tem_diagrama and pode else (vazia if tem_diagrama else MOTIVO_SEM_DIAGRAMA)
            tecla = atalhos.acelerador(acao)
            self._dicas_de_historico[acao].set_text(f"{motivo}\nTecla: {tecla}" if tecla else motivo)

    def desfazer(self) -> None:
        """`Ctrl+Z`: devolve a posição anterior deste diagrama."""
        self._voltar_no_historico(self.historico.desfazer(), "Não há mudança anterior neste diagrama para desfazer.")

    def refazer(self) -> None:
        """`Ctrl+Y`: repõe o que o desfazer tirou."""
        self._voltar_no_historico(self.historico.refazer(), "Não há o que refazer: nada foi desfeito.")

    def limpar_tabuleiro(self) -> None:
        """Esvazia as 64 casas -- e a pilha guarda a posição de antes, então é desfazível.

        **Limpar é a posição, e não o editor.** Ver a nota do comando em `ui/comandos.py`: o que a
        S-229 pede é uma das sete origens de mudança que o desfazer reverte, e esvaziar o editor
        inteiro não é uma delas.
        """
        if not self.model.items:
            self._on_status("Não há diagrama aberto para limpar.")
            return
        if board_edit.placement_of(self.model.fen_at()) == board_edit.EMPTY_PLACEMENT:
            self._on_status("O tabuleiro já está vazio.")
            return
        self.on_board_changed(board_edit.EMPTY_PLACEMENT)
        self.board.set_position(board_edit.EMPTY_PLACEMENT)
        self._on_status("Tabuleiro limpo. Ctrl+Z devolve a posição.")

    def _voltar_no_historico(self, placement: str | None, recusa: str) -> None:
        """Põe na tela a posição que a pilha devolveu, ou diz por que não há uma."""
        if placement is None:
            self._on_status(recusa)
            self._atualizar_botoes_de_historico()
            return
        if not self.model.apply_placement(placement):
            return
        self.fen_var.set(placement)
        # `set_position` e não `on_board_changed`: o widget não dispara `on_change` quando a
        # posição vem de fora, e é o que impede a volta de entrar na pilha como edição nova --
        # o laço em que desfazer empilha o próprio efeito e o refazer nunca acontece.
        self.board.set_position(placement)
        self.update_legality()
        self._on_sync_study()
        self._atualizar_botoes_de_historico()

    def _zerar_historico(self, idx: int) -> None:
        """A pilha recomeça na posição do diagrama que passou a estar na tela.

        **Trocar de diagrama zera as duas pilhas** (S-229): desfazer para dentro de outra posição
        é pior que não desfazer -- a pessoa apertaria `Ctrl+Z` esperando a casa de trás e receberia
        o tabuleiro do diagrama anterior, gravável por cima do atual com um `Ctrl+S`.
        """
        self.historico.zerar(board_edit.placement_of(self.model.fen_at(idx)) if self.model.items else "")

    # --------------------------------------------------------------------------- gravação

    def set_review_settler(self, settler: Callable[[int, str, str], None] | None) -> None:
        """Como devolver a correção à fila. Injetado para não depender do painel de revisão."""
        self._settle_review = settler

    def _saved_sample(self, alvo: SaveTarget) -> SavedSample | None:
        """A procedência do que acabou de ser gravado, para quem pinta a caixa de verde (S-116).

        `None` quando não há procedência de página: imagem solta, ou origem ausente. É o mesmo
        crivo de `saved_diagrams_by_page`, que ignora linha sem `source_page` -- e ali por não
        poder inventar de onde ela veio, aqui por não haver o que marcar.

        Os dois índices saem em base 0, que é a contagem da tela. O CSV grava em base 1 (ver
        `RecognitionOrigin.sample_fields` e `save_sample`), e a conversão continua num lugar só.
        """
        origem = self.model.origin
        if origem is None or origem.page_index is None or not origem.document:
            return None
        if not 0 <= alvo.index < len(self.model.items):
            return None
        return SavedSample(
            source_pdf=origem.document,
            page_index=int(origem.page_index),
            diagram_index=int(self.model.items[alvo.index].index),
        )

    def _save_one(self, alvo: SaveTarget, *, allow_illegal: bool = False) -> Path:
        csv_path, samples_dir = self._paths()
        return self._service.save_sample(
            self.model.items[alvo.index],
            alvo.fen,
            csv_path=csv_path,
            samples_dir=samples_dir,
            origin=self.model.origin,
            side_to_move=alvo.side,
            corrected_by=alvo.route,
            allow_illegal=allow_illegal,
        )

    @staticmethod
    def _illegal_question(alvo: SaveTarget) -> str | None:
        """A pergunta desta gravação, ou `None`. A FEN do alvo pode vir só com as peças."""
        return illegal_save_question(compose_fen(alvo.fen.split(" ")[0], alvo.side != "b"))

    def _confirm_illegal(self, alvo: SaveTarget) -> bool | None:
        """`None` quando a posição é legal, senão a resposta da pessoa.

        Três valores em vez de dois porque quem chama precisa dos três: legal segue sem
        caixa nenhuma, "sim" grava com a marca da `ILLEGAL_OK`, "não" cancela. Colapsar
        legal com "sim" faria toda amostra normal ser gravada como ilegal confirmada.
        """
        pergunta = self._illegal_question(alvo)
        if pergunta is None:
            return None
        return messagebox.askyesno(ILLEGAL_SAVE_TITLE, pergunta, default=messagebox.NO, icon=messagebox.WARNING)

    def save_current(self) -> None:
        """Salva o diagrama selecionado. **O que "salvar" significa é decisão do modelo.**

        Este método executa o que `save_target()` mandou e cuida das caixas de diálogo; a
        regra -- amostra nova, regravar a linha do dataset, fechar item da fila -- mora em
        `DiagramEditorModel` e tem teste sem janela (S-49).
        """
        if not self.model.items:
            # Pré-condição, e não falha: vai para o rodapé com severidade de aviso (S-164).
            self._on_status("Não há diagrama lido para salvar: leia uma página antes.")
            return
        self.sync_fen_from_entry()
        alvo = self.model.save_target()
        if not is_valid_fen(alvo.fen):
            messagebox.showerror("Aplicar a FEN", "FEN atual inválida.")
            return

        # A pergunta vem antes de decidir entre amostra nova e regravação porque a resposta
        # vale para as duas: o que está sendo confirmado é a posição, não o destino dela.
        confirmada = self._confirm_illegal(alvo)
        if confirmada is False:
            self._on_status("Gravação cancelada: posição ilegal não confirmada.")
            return

        if alvo.kind is SaveKind.REWRITE_ROW:
            self._rewrite_dataset_row(alvo, allow_illegal=confirmada is True)
            return

        # **O `try` cobre a gravação, e só ela (S-318).** Ele cobria também o repintar da aba
        # Dataset, a marca verde no diagrama e a recontagem das abas -- e um `AttributeError`
        # em qualquer um desses três produzia a caixa "Falha ao salvar" sobre uma amostra que
        # **está no disco**. A pessoa acredita que perdeu a correção, refaz e salva de novo; e
        # como `append_training_sample` nomeia por timestamp e sempre acrescenta, a segunda
        # gravação vira uma linha e um PNG duplicados no `labels.csv`. É o laço mais repetido
        # do projeto -- corrigir, `Ctrl+S`, seta -- mentindo sobre o único gesto que ele tem.
        try:
            path = self._save_one(alvo, allow_illegal=confirmada is True)
        except Exception as exc:
            # `logger.exception` antes do modal: no bundle da S-55 (`console=False`) o
            # `str(exc)` da caixa era o único vestígio no mundo, e ele sumia quando ela era
            # fechada. O `logger` deste módulo estava declarado e ocioso desde sempre.
            logger.exception("Falha ao gravar a amostra corrigida.")
            messagebox.showerror("Erro ao salvar a amostra", f"Falha ao salvar:\n{exc}")
            return

        self._on_status(f"Exemplo salvo: {path}")
        # Daqui para baixo a amostra **já está gravada**: o que falhar aqui é acabamento de
        # tela, e dizer "falha ao salvar" sobre isso é pior que a tela ficar desatualizada.
        try:
            self._settle(alvo)
            # Só o caminho de regravação avisava. Sem isto, a aba Dataset não via a amostra
            # nova e o visualizador não pintava de verde o diagrama que acabou de ser salvo
            # (S-71) -- os dois só se atualizavam na próxima vez que o livro fosse aberto.
            #
            # **Com o que foi gravado, e não vazio** (S-116, corte 2): quem ouve pinta a caixa
            # com este dado em vez de reler o `labels.csv` para redescobri-lo.
            gravada = self._saved_sample(alvo)
            self._on_sample_saved(() if gravada is None else (gravada,))
            # **Sem modal de sucesso** (S-116). Ele dizia o que a barra de status já diz e
            # cobrava uma tecla por amostra no laço mais interno do projeto -- corrigir,
            # `Ctrl+S`, seta, corrigir. Quem quer confirmação visual tem a melhor delas: a
            # caixa do diagrama fica verde na hora (S-71). O modal de **erro** fica, porque
            # ali a informação não é redundante e a interrupção é o ponto.
        except Exception:  # noqa: BLE001 - acabamento de tela não derruba uma gravação boa
            logger.exception("A amostra foi gravada, mas a tela não pôde ser atualizada.")
            self._on_status(f"Exemplo salvo: {path} (a tela não pôde ser atualizada -- ver o log).")

    def _rewrite_dataset_row(self, alvo: SaveTarget, *, allow_illegal: bool = False) -> None:
        filename = alvo.filename or ""
        csv_path, _samples = self._paths()
        try:
            atualizado = update_row(
                csv_path,
                filename,
                fen=alvo.fen,
                side_to_move=alvo.side,
                corrected_by=alvo.route,
                allow_illegal=allow_illegal,
            )
        except ValueError as exc:
            messagebox.showerror("Dataset", str(exc))
            return

        if not atualizado:
            messagebox.showerror("Dataset", f"Amostra não encontrada no CSV: {filename}")
            return

        # Sem `messagebox` (S-164): a frase acima diz a mesma coisa, no rodapé, e um clique para
        # confirmar sucesso é o que treina a pessoa a fechar caixas sem ler -- inclusive as que
        # perguntam algo.
        self._on_status(f"Rótulo de {filename} regravado.")
        # Vazio, e é resposta: regravar a linha de uma amostra que já existia não faz diagrama
        # nenhum ficar verde -- ele já estava. O que mudou foi o rótulo, e disso a aba Dataset
        # é que precisa saber.
        self._on_sample_saved(())

    def _settle(self, alvo: SaveTarget) -> None:
        """Fecha na fila o item que acabou de ser corrigido e salvo (S-22)."""
        if self._settle_review is None or alvo.settle_position is None:
            return
        self._settle_review(alvo.settle_position, alvo.fen, alvo.side)
        self.model.settled()

    def _ja_salvos(self, alvos: Sequence[SaveTarget]) -> set[int]:
        """Quais destes alvos já têm amostra gravada. Devolve `alvo.index`, não o nº do diagrama.

        O índice do alvo é a posição na lista do editor, que é por onde `save_all` filtra; o
        número do diagrama (`items[i].index`) é o que a janela conta e o que o CSV grava. Os
        dois coincidem quase sempre, e não é seguro contar com isso -- a conversão fica aqui.

        Vazio quando não há procedência de página -- imagem solta, recorte, item da fila: sem
        ela não há como saber o que já foi salvo, e perguntar sem saber é pior que não perguntar.
        """
        origem = self.model.origin
        if origem is None or origem.page_index is None or not origem.document:
            return set()
        salvos = set(self._saved_diagrams(origem.document, int(origem.page_index)))
        if not salvos:
            return set()
        return {
            alvo.index
            for alvo in alvos
            if 0 <= alvo.index < len(self.model.items) and self.model.items[alvo.index].index in salvos
        }

    def save_all(self) -> None:
        if not self.model.items:
            # Pré-condição, e não falha: vai para o rodapé com severidade de aviso (S-164).
            self._on_status("Não há diagrama lido para salvar: leia uma página antes.")
            return
        self.sync_fen_from_entry()
        if self.model.binding is EditorBinding.SAMPLE:
            # Uma amostra do dataset e um item so, e "salvar todos" sobre ela e "salvar".
            # Criar amostra nova por este caminho era o defeito que a S-23 fechou no `Ctrl+S`
            # e que continuava aberto aqui, porque `save_all` nunca olhou o vinculo.
            self.save_current()
            return

        alvos = [self.model.save_target(idx) for idx in range(self.model.count)]
        validos = [alvo for alvo in alvos if alvo.kind is not SaveKind.NOTHING and is_valid_fen(alvo.fen)]
        invalidos = len(alvos) - len(validos)

        # **A pergunta que faltava** (S-451). "Salvar todos" é o gesto que se repete -- varrer,
        # corrigir, salvar, virar --, e voltar a uma página já feita era indistinguível de
        # fazê-la pela primeira vez: gravava em silêncio a segunda cópia de cada diagrama.
        # `append_training_sample` nomeia por timestamp e sempre acrescenta, então o preço é uma
        # linha e um PNG duplicados por diagrama, num arquivo que este projeto existe para fazer
        # crescer limpo. Uma pergunta para a página, pelo mesmo motivo da de ilegalidade abaixo.
        repetidos = self._ja_salvos(validos)
        ja_salvos = 0
        if repetidos:
            numeros = ", ".join(str(self.model.items[indice].index + 1) for indice in sorted(repetidos))
            todos = len(repetidos) == len(validos)
            if not messagebox.askyesno(
                "Diagramas já salvos",
                f"{len(repetidos)} de {len(validos)} diagramas desta página já têm amostra "
                f"no dataset: {numeros}.\n\n"
                "Salvar de novo grava uma segunda linha e uma segunda imagem do mesmo "
                "diagrama -- o que vale a pena se você acabou de corrigir a leitura, e é "
                "duplicata se não.\n\n"
                + ("Salvar novamente?" if todos else 'Salvar novamente? Responder "não" salva apenas os outros.'),
                default=messagebox.NO,
            ):
                ja_salvos = len(repetidos)
                validos = [alvo for alvo in validos if alvo.index not in repetidos]
                if not validos:
                    self._on_status(
                        f"Salvar todos: nada a gravar, os {ja_salvos} diagrama(s) desta página já estavam salvos."
                    )
                    return

        # Uma pergunta para a pagina inteira, e nao uma por diagrama. Uma pagina de capitulo
        # sobre estrutura tem os oito diagramas sem rei: perguntar oito vezes a mesma coisa
        # treina a pessoa a clicar "sim" sem ler, que e o oposto do que a confirmacao existe
        # para conseguir.
        ilegais = [alvo for alvo in validos if self._illegal_question(alvo) is not None]
        indices_ilegais = {alvo.index for alvo in ilegais}
        confirmar_ilegais = False
        if ilegais:
            confirmar_ilegais = messagebox.askyesno(
                ILLEGAL_SAVE_TITLE,
                f"{len(ilegais)} de {len(validos)} diagramas têm posição ilegal:\n\n"
                + "\n".join(f"  • {alvo.index + 1}: {self._resumo_ilegal(alvo)}" for alvo in ilegais[:6])
                + (f"\n  ... e mais {len(ilegais) - 6}" if len(ilegais) > 6 else "")
                + "\n\nSalvar também esses? Responder \"não\" salva apenas o resto.",
                default=messagebox.NO,
                icon=messagebox.WARNING,
            )

        pulados = 0
        salvos = 0
        salvos_ilegais = 0
        gravadas: list[SavedSample] = []
        for alvo in validos:
            ilegal = alvo.index in indices_ilegais
            if ilegal and not confirmar_ilegais:
                pulados += 1
                continue
            self._save_one(alvo, allow_illegal=ilegal)
            gravada = self._saved_sample(alvo)
            if gravada is not None:
                gravadas.append(gravada)
            # Dentro do laço, porque é por item: cada diagrama fecha o **seu** item da fila
            # (S-22). Sem isto, `Ctrl+Shift+S` gravava a página inteira e não fechava nenhum,
            # e a fila de revisão mandava corrigir de novo o que já tinha sido corrigido.
            self._settle(alvo)
            salvos += 1
            salvos_ilegais += int(ilegal)

        if salvos:
            # **Uma vez ao fim, e não por diagrama**, com a lista inteira do que foi gravado.
            # O aviso relia o `labels.csv` na thread da janela e dispará-lo por item
            # multiplicaria por N o travamento que o "salvar todos" existe justamente para
            # evitar. Depois do corte 2 da S-116 ele não relê nada -- e a chamada única fica,
            # porque redesenhar a página oito vezes também custa, e por nada.
            self._on_sample_saved(gravadas)

        # Uma linha no rodapé, e não uma caixa modal (S-164): "salvar todos" existe para não
        # travar a pessoa item por item, e terminar num clique obrigatório desfazia metade disso.
        # As quatro parcelas que a caixa mostrava entram na frase; nenhuma se perdeu.
        resumo = f"Salvar todos: {salvos} salvos, {invalidos} inválidos"
        if ja_salvos:
            resumo += f", {ja_salvos} já estavam salvos"
        if salvos_ilegais:
            resumo += f", {salvos_ilegais} ilegais confirmados"
        if pulados:
            resumo += f", {pulados} ilegais não confirmados"
        self._on_status(resumo + ".")

    def _resumo_ilegal(self, alvo: SaveTarget) -> str:
        """Os problemas fatais deste diagrama em uma linha, para a lista do `save_all`."""
        explicacao = explain_position(compose_fen(alvo.fen.split(" ")[0], alvo.side != "b"))
        return "; ".join(problem.text for problem in explicacao.problems if problem.fatal)

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
            # A quinta origem (S-229): a leitura do segundo modelo é adotada, e desfazer devolve
            # a do primeiro. Sem isto, discordar do segundo leitor custaria reler a página.
            self.historico.registrar(board_edit.placement_of(parecer.placement))
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
            # A sexta origem (S-229). A correção vem de fora da máquina, e é justamente a que
            # mais precisa de volta: quem discorda dela não tem como pedir a leitura de novo.
            self.historico.registrar(board_edit.placement_of(fen))
            self.fen_var.set(fen)
            self.update_views()
        self._on_status(f"FEN corrigida via Net (diagrama {idx + 1}).")
