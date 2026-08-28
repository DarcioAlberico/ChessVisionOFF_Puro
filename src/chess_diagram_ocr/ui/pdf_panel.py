"""O lado direito da janela: o PDF, sua navegação e a seleção de área (S-31).

**O que ele guarda.** O documento aberto, a página renderizada e o zoom. Era estado do
`ChessOcrTkApp` misturado com o do OCR, e a mistura tinha consequência: `page_rgb`,
`page_loaded_for_index` e `pdf_source` eram lidos por métodos de reconhecimento espalhados
pela classe, então não havia como saber quem podia invalidá-los.

**O que ele não faz.** Não reconhece nada. A seleção de área devolve um retângulo em
coordenadas de **pixel da página**; recortar, grampear aos limites e decidir o que fazer
quando não há contorno é do `OcrService` (S-31). O painel só sabe converter coordenada de
canvas para coordenada de imagem, que é a única parte que depende do zoom.

**Os diagramas marcados na página (S-68).** Sobre a mesma imagem o painel desenha um retângulo
por diagrama que o detector achou, numerado como o seletor da aba Resultado numera. Clicar num
deles é o gesto que a seleção de área já oferecia, sem o arrasto -- e a decisão do que aquele
clique significa não mora aqui: ela é `page_overlay.decide_box_click`, e quem a executa é a
janela, que é quem tem o OCR. O painel só sabe desenhar, acertar o alvo e avisar.

**Um visualizador só, e por quê (S-69).** Até aqui havia duas abas: esta e uma "Leitura", que
embutia o WebView2 -- o visualizador de PDF do Edge -- dentro de um `Frame` por `SetParent`. Ela
saiu, e o que a matou foi justamente a S-68: um HWND nativo filho pinta **acima** de qualquer
item do canvas, o leitor interno do Edge não aceita JS injetado e não informa a página em que
está. Ou seja, na aba "Leitura" não havia como desenhar os retângulos, capturar o clique nem
saber que página o usuário estava vendo -- a sincronia entre as duas abas era, por construção,
de mão única e cega. E os pixels que o OCR precisa vêm do PyMuPDF, que só esta aba tem.

No lugar dela ficou o botão **Abrir no leitor do sistema**, que entrega o mesmo valor -- rolagem
contínua, busca de texto, render nativo -- sem fingir estar sincronizado com nada. Junto saíram
`pythonnet` e `pywebview`, as duas únicas dependências só-Windows do projeto.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import tkinter as tk
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import numpy as np
from PIL import Image, ImageTk

from chess_diagram_ocr.pdf_io import get_pdf_page_count, render_pdf_page

from . import atalhos, comandos, formato, pele, rodape, strings, theme, tipografia, tokens
from .barra import BarraFluida
from .page_overlay import DiagramBox, PageBoxes, traco_da_caixa
from .tooltip import Tooltip
from .viewport import (
    LADO_DO_DESLIZADOR,
    WheelAction,
    anchor_after_zoom,
    clamp_zoom,
    decide_wheel,
    desvio_de_centralizacao,
    fit_page_zoom,
    fit_width_zoom,
    posicao_do_zoom,
    regiao_de_rolagem,
    wheel_direction,
    zoom_da_posicao,
    zoomed,
)

logger = logging.getLogger(__name__)

PASSO_DE_ZOOM = 0.1
"""Quanto um clique em `+` ou `-` muda o zoom. Aditivo, e não multiplicativo: um clique, um
passo previsível."""

MIN_SELECTION_PX = 12
"""Arrasto menor que isto é clique errado, não seleção. Abaixo disso o recorte não
conteria nem uma casa do tabuleiro.

**Doze pixels de página, e não de tela (S-330).** A comparação era feita nas coordenadas do
canvas, que já vêm multiplicadas pelo zoom: a 25% o piso valia 48 px de página, e a 200%,
6 px. O mesmo arrasto era "muito pequeno" numa vista e recorte válido na outra, e o recado
não dizia nada disso. O que a constante quer dizer -- "menos que isto não contém casa
nenhuma" -- é uma afirmação sobre a folha, então é na folha que ela se mede."""

WHEEL_SCROLL_UNITS = 3
"""Linhas de canvas por giro da roda. Três é o padrão do Windows, e o canvas mede "unidade"
em pixels -- então o passo real é o `yscrollincrement`, que aqui fica no padrão do Tk."""

TAG_CONTORNO = "diagram-box-outline"
"""O contorno de estado de uma caixa, separado do halo e do fundo do número (S-159)."""

CLICK_SLOP_PX = 4
"""Quanto o ponteiro pode andar entre apertar e soltar e ainda ser um clique.

Sem folga, o clique de quem apoia a mão no mouse vira arrasto e não abre diagrama nenhum;
com folga demais, arrastar a barra de rolagem abriria um diagrama por acidente."""

# --- as três cores são **um** eixo: em que ponto do trabalho aquele diagrama está. A seleção
# --- deixou de ser cor na S-71 justamente para não disputar este eixo -- ver `_draw_boxes`.
BOX_OUTLINE = tokens.RESERVA[tokens.A_FAZER]
"""Localizado pelo detector, ainda não lido."""

BOX_OUTLINE_RECOGNIZED = tokens.RESERVA[tokens.LIDO]
"""Lido pelo OCR e **ainda não salvo**: o que falta fazer nesta página."""

SELECTION_HALO_PX = 4
"""Folga da segunda borda do diagrama selecionado, para fora da caixa.

Para **fora** porque a caixa encosta no diagrama: uma borda por dentro cairia sobre as casas
da primeira fila, e a caixa existe justamente para conferir a posição."""

BOX_OUTLINE_SAVED = tokens.RESERVA[tokens.PRONTO]
"""Já tem amostra no `labels.csv`. Verde é a cor de "pronto", e é para isso que ela serve.

Vale mesmo antes de a página ser lida: quem responde é a procedência gravada no CSV, não o
que está em memória. Abrir um livro pela quinta vez e ver de verde o que já foi feito é a
única forma barata de responder "onde eu parei?"."""

BOX_OUTLINE_CONFIRMED = tokens.RESERVA[tokens.DISPENSADO]
"""A base de partidas reconheceu a posição (S-75). Violeta porque não é nem "feito" nem "a
fazer": é **"não precisa"**, que é um estado que a tela não tinha.

Vem do arquivo de anotações e, como o verde, aparece antes de qualquer OCR."""


def box_color(box: DiagramBox) -> str:
    """A cor do retângulo, pelo ponto em que aquele diagrama está.

    A precedência é: salvo > confirmado > lido > localizado -- da informação mais adiantada
    para a menos. Salvo vem antes de confirmado porque ele é trabalho **seu** já feito: um
    diagrama salvo e confirmado não precisa de nada, e o que interessa saber ao olhar a página
    é que aquele já rendeu amostra. Salvo e confirmado valem inclusive antes de a página ser
    lida, e é isso que faz a marcação servir a um livro trabalhado ontem.
    """
    if box.saved:
        return BOX_OUTLINE_SAVED
    if box.confirmed:
        return BOX_OUTLINE_CONFIRMED
    return BOX_OUTLINE_RECOGNIZED if box.recognized else BOX_OUTLINE


def open_in_system_reader(pdf_path: Path) -> None:
    """Abre o PDF no leitor padrão do sistema, na janela dele.

    Substitui o WebView2 embutido (S-69) e cabe em oito linhas porque não tenta ser uma aba:
    quem quer ler o livro ganha o leitor de verdade, com rolagem contínua e busca de texto, e
    o app não promete saber o que acontece lá dentro -- que era a promessa que a aba "Leitura"
    não tinha como cumprir.

    Os três ramos existem porque, sem o WebView2, **não sobrou nada de específico de Windows no
    projeto**. Deixar um `os.startfile` sozinho aqui reintroduziria a dependência de plataforma
    pela porta dos fundos, e por um botão.
    """
    alvo = str(Path(pdf_path).resolve())
    if sys.platform == "win32":
        # `os.startfile` só existe no Windows -- daí o `getattr`, que mantém os três ramos
        # verificáveis nas três plataformas em vez de depender de um `type: ignore`.
        getattr(os, "startfile")(alvo)  # noqa: B009
    elif sys.platform == "darwin":
        subprocess.Popen(["open", alvo])
    else:
        subprocess.Popen(["xdg-open", alvo])


class PdfPanel(ttk.Frame):
    """Visualização e navegação do PDF, com seleção de área para OCR."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        dpi: Callable[[], int],
        initial_page_for: Callable[[Path], int],
        on_status: Callable[[str], None],
        on_ocr_best: Callable[[], None],
        on_ocr_all: Callable[[], None],
        on_region: Callable[[np.ndarray, tuple[int, int, int, int]], None],
        on_export: Callable[[], None],
        on_cancel_export: Callable[[], None],
        on_pdf_opened: Callable[[Path], None],
        on_before_page_change: Callable[[], None],
        on_page_rendered: Callable[[int], None],
        on_zoom_changed: Callable[[float], None],
        initial_dir: Path,
        on_box_click: Callable[[int], None] = lambda _indice: None,
        on_box_drop: Callable[[int], None] = lambda _indice: None,
        on_prefs_changed: Callable[[], None] = lambda: None,
        on_document_state: Callable[[str, bool], None] = lambda _texto, _concluida: None,
    ) -> None:
        super().__init__(parent, padding=10)
        self._dpi = dpi
        self._initial_page_for = initial_page_for
        self._on_status = on_status
        self._on_document_state = on_document_state
        """Onde o estado do documento é publicado: o rodapé da janela (S-163).

        Era um `ttk.Label` no fim da barra de zoom, e a barra reflui (S-151) -- então "3 de 5
        salvo(s)" ia para a segunda linha junto com o botão de zoom, ou saía da tela. Estado do
        documento não é controle de visualização, e o rodapé é onde ele para de disputar largura
        com botão. Padrão inerte para o painel montado sem janela, como o `on_box_click`."""
        self._on_region = on_region
        self._on_pdf_opened = on_pdf_opened
        self._on_box_click = on_box_click
        """Um diagrama marcado foi clicado. Recebe o índice em base 0 -- o mesmo do editor.

        Padrão inerte para que montar o painel sem a janela (nos testes) não exija inventar um
        destino para o clique."""

        self._on_box_drop = on_box_drop
        """O usuário quer **tirar** aquele retângulo da página (S-177). Índice em base 0.

        Separado do `on_box_click` porque as duas respostas ao mesmo retângulo são opostas: uma
        diz "leia isto", a outra diz "isto não é diagrama". Quem guarda a remoção é a janela --
        o painel desenha o que lhe entregam."""

        self._on_prefs_changed = on_prefs_changed
        """Uma preferência de visualização mudou -- marcação de diagramas ou virada de página
        pela roda. Existe para o estado da aplicação lembrar dela entre execuções."""
        self._on_before_page_change = on_before_page_change
        """Chamado antes de trocar a página exibida: é a janela de tempo em que o editor
        ainda tem o reconhecimento da página de origem para guardar no cache."""

        self._on_page_rendered = on_page_rendered
        """Chamado depois de a página aparecer. É onde a janela traz de volta o
        reconhecimento guardado desta página e grava o estado -- fazê-lo antes do render
        restauraria o editor para uma página que ainda não está na tela."""

        self._on_zoom_changed = on_zoom_changed
        self._initial_dir = initial_dir

        self.estado_do_documento = ""
        """A última frase publicada no rodapé sobre a página exibida (S-163).

        Guardada aqui, e não só enviada, porque ela é o que o teste afirma: o painel decide o
        texto, o rodapé o desenha, e as duas coisas se verificam separadamente."""

        self.pagina_concluida = False
        """Se todos os diagramas da página exibida já têm amostra. Decide a cor no rodapé."""

        self.source: Path | None = None
        self.name: str = ""
        self.page_count = 0
        self.page_rgb: np.ndarray | None = None
        self.page_loaded_for_index: int | None = None

        self.page_index_var = tk.IntVar(value=0)
        self.zoom_var = tk.DoubleVar(value=0.7)

        self._page_photo: ImageTk.PhotoImage | None = None
        self._select_mode = False
        self._dpi_var: tk.Variable | None = None
        self._dpi_after: str | None = None
        self._dpi_rasterizado: int | None = None
        """O DPI com que a folha na tela foi rasterizada. `None` até a primeira (S-329)."""
        self._select_start: tuple[float, float] | None = None
        self._select_rect_id: int | None = None
        self._canvas_image_id: int | None = None

        self._desvio: tuple[int, int] = (0, 0)
        """Quanto a página está deslocada dentro do canvas para ficar centralizada (S-157).

        Começa em `(0, 0)` e é isso que faz o painel montado e nunca desenhado se comportar como
        antes: sem página, não há o que centralizar. Ver `_para_pagina`, que é a única fronteira
        entre esta coordenada e todo o resto do painel."""

        self._enquadramento_pendente = True
        """Este livro ainda não recebeu um enquadramento inicial (S-157).

        Existe porque o primeiro `refresh_view` acontece com o canvas ainda por medir --
        `winfo_width()` devolve 1 antes de a janela ser mapeada --, e ajustar à página ali daria
        o zoom mínimo. O ajuste espera o primeiro `<Configure>` de verdade."""

        self.boxes: PageBoxes | None = None
        """Os diagramas marcados na página exibida (S-68). `None` enquanto não se sabe.

        "Não se sabe" e "não há" são estados diferentes e ambos existem: o primeiro é a página
        recém-rasterizada, com a detecção ainda rodando; o segundo é uma página de prosa. Só o
        segundo autoriza dizer ao usuário que ali não tem diagrama."""

        self.show_boxes_var = tk.BooleanVar(value=True)
        self._selected_box: int | None = None
        self._press_at: tuple[float, float] | None = None
        self._hover_box: int | None = None

        self.flip_pages_var = tk.BooleanVar(value=True)
        """Se a roda vira a página ao chegar na borda (S-70)."""

        self._last_page_flip = 0.0
        self._panning = False

        self._deslizador: ttk.Scale | None = None
        self._lbl_zoom_deslizador: ttk.Label | None = None
        self._rodape_de_zoom: ttk.Frame | None = None
        self._movendo_o_deslizador = False
        """Guarda contra o laço: `Scale.set` dispara o `command`, e o `command` chama
        `apply_zoom`, que chama `update_zoom_label`, que chama `Scale.set` (S-225)."""

        self._build(on_ocr_best, on_ocr_all, on_export, on_cancel_export)

    # ------------------------------------------------------------------------------ layout

    def _build(
        self,
        on_ocr_best: Callable[[], None],
        on_ocr_all: Callable[[], None],
        on_export: Callable[[], None],
        on_cancel_export: Callable[[], None],
    ) -> None:
        # Guardados porque a troca de pele refaz as barras, e refazer um botão é precisar de
        # novo da função que ele chama (S-222). O painel não as executa; ele só as segura.
        self._on_ocr_best = on_ocr_best
        self._on_ocr_all = on_ocr_all
        self._on_export = on_export
        self._on_cancel_export = on_cancel_export

        box = ttk.LabelFrame(self, text=strings.LIVRO_EM_PDF)
        box.pack(fill=tk.BOTH, expand=True)
        self._box = box

        # **Duas barras, e não cinco** (S-151). O agrupamento é por pergunta, e não por ordem
        # histórica de quem escreveu cada linha: a primeira é *o que fazer com este livro*, a
        # segunda é *onde estou e quão perto*. Navegação de página e zoom eram duas barras e são
        # um eixo só -- as duas respondem à mesma pergunta com unidades diferentes.
        self._montar_barras()

        # O que se sabe dos diagramas da página **não** entra nesta barra (S-163): ele é estado
        # do documento e vai para o rodapé da janela, via `_on_document_state`. Era o último item
        # da barra de zoom -- o lugar de onde ele saía da tela primeiro.

        self.field_row = ttk.Frame(box)
        """Onde a janela pendura os controles do conjunto de campo (S-77).

        Junto da página, e não numa aba de configuração: anota-se o que se está vendo, e uma
        anotação feita longe da imagem é uma anotação feita de memória.

        **Continua sendo uma terceira faixa, e isso está registrado** (S-151). A spec manda esta
        tarefa para o rodapé da S-163 ou para o menu da S-161, e nenhum dos dois existe ainda;
        movê-la para uma das duas barras a misturaria com controle de visualização, que é
        exatamente o agrupamento por acaso de que este item veio tirar o painel. Ela nasce
        vazia: sem os controles de campo montados pela janela, não ocupa altura nenhuma."""
        self.field_row.pack(fill=tk.X, padx=8, pady=(0, 6))

        # Sem `Notebook`: a página ocupa o painel inteiro desde a S-69. Enquanto havia duas
        # abas, esta metade da janela custava uma linha de abas para oferecer uma escolha que
        # não era uma -- a outra não fazia nada que esta não faça, e não fazia o que esta faz.
        view = ttk.Frame(box)
        view.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        wrap = ttk.Frame(view)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(wrap, bg=theme.cor_atual(tokens.SUPERFICIE_PAGINA), highlightthickness=0)
        theme.ao_repintar(lambda: self.canvas.configure(bg=theme.cor_atual(tokens.SUPERFICIE_PAGINA)))
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.canvas.yview)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll = ttk.Scrollbar(view, orient=tk.HORIZONTAL, command=self.canvas.xview)
        hscroll.pack(fill=tk.X, pady=(0, 8))
        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.canvas.bind("<Configure>", self._ao_redimensionar)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)
        # Botao direito tira o retangulo de baixo do ponteiro (S-177). E o gesto direto, e e o
        # unico que funciona **antes** do OCR: ate a pagina ser lida nao ha diagrama
        # selecionado (ver `_sync_selected_box`), e e justamente ai que se quer matar a caixa
        # errada -- para nao pagar o OCR dela.
        self.canvas.bind("<ButtonPress-3>", self._on_right_click)
        # Botão do meio: deslocar a página mesmo com a seleção de área ligada, que é quando o
        # botão esquerdo pertence ao retângulo verde.
        self.canvas.bind("<ButtonPress-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", self._on_pan_end)
        self._bind_wheel()

    def _montar_barras(self, montagem: str = pele.CROMO_CLASSICO, *, antes: tk.Misc | None = None) -> None:
        """As duas barras do painel. Chamada na construção e de novo a cada troca de pele (S-222).

        `antes` diz onde elas entram no `pack`: na construção não há nada abaixo delas ainda; na
        remontagem há -- e sem isso as barras refeitas nasceriam **depois** do canvas, que é a
        ordem em que o `pack` empilha quem chega por último.

        **Na pele "Foco" os controles são criados e não empacotados** (S-223). Parece desperdício
        e é o contrário: `set_ocr_controls_enabled`, `_open_pdf` e `update_zoom_label` escrevem
        nesses widgets o tempo todo, e fazê-los existir mantém o painel com um contrato só. O que
        a pele decide é o que aparece na tela, não o que o painel sabe fazer -- e os 21 controles
        continuam alcançáveis pelo menu, que é o que a regra 2 exige e a S-233 mede.
        """
        box = self._box
        # `Any` e nao `object`: isto vai para o `pack` por `**`, e a assinatura do `tkinter` e um
        # mosaico de `Literal` que nenhum tipo mais estreito satisfaz.
        embalagem: dict[str, Any] = {} if antes is None else {"before": antes}
        na_tela = montagem == pele.CROMO_CLASSICO

        self.barra_livro = BarraFluida(box)
        self.barra_vista = BarraFluida(box)
        if na_tela:
            self.barra_livro.pack(fill=tk.X, padx=8, pady=6, **embalagem)
            self.barra_vista.pack(fill=tk.X, padx=8, pady=(0, 4), **embalagem)

        livro, vista = self.barra_livro, self.barra_vista
        livro.adicionar(ttk.Button(livro, text=comandos.rotulo_de_botao("abrir_pdf"), style=comandos.estilo("abrir_pdf"), command=self.open_pdf))
        self.btn_system_reader = livro.adicionar(
            ttk.Button(
                livro,
                text=comandos.rotulo_de_botao("abrir_no_leitor"),
                style=comandos.estilo("abrir_no_leitor"),
                command=self.open_in_system_reader,
                state=tk.DISABLED,
            )
        )
        Tooltip(
            self.btn_system_reader,
            "Abre este PDF no leitor padrão do sistema, numa janela própria.\n"
            "Para ler o livro: rolagem contínua e busca de texto, que esta tela não tem.",
        )
        self.lbl_pdf = livro.adicionar(ttk.Label(livro, text="Nenhum PDF"))
        self.btn_ocr_best = livro.adicionar(
            ttk.Button(
                livro,
                text=comandos.rotulo_de_botao("ler_melhor"),
                style=comandos.estilo("ler_melhor"),
                command=self._on_ocr_best,
            )
        )
        self.btn_ocr_all = livro.adicionar(ttk.Button(
                livro, text=comandos.rotulo_de_botao("ler_pagina"), style=comandos.estilo("ler_pagina"), command=self._on_ocr_all
            ))
        self.btn_select = livro.adicionar(
            ttk.Button(
                livro,
                text=comandos.rotulo_de_botao("selecionar_area"),
                style=comandos.estilo("selecionar_area"),
                command=self.toggle_area_selection,
            )
        )
        self.btn_drop_box = livro.adicionar(
            ttk.Button(
                livro,
                text=comandos.rotulo_de_botao("tirar_caixa"),
                style=comandos.estilo("tirar_caixa"),
                command=self.drop_selected_box,
            )
        )
        Tooltip(
            self.btn_drop_box,
            "Tira da página o retângulo do diagrama selecionado -- o que o detector marcou errado.\n"
            "Botão direito sobre qualquer retângulo faz o mesmo, sem precisar selecioná-lo antes.\n"
            "Depois, use Selecionar área (OCR) para recortar o diagrama de verdade.",
        )
        self.btn_export = livro.adicionar(ttk.Button(
                livro,
                text=comandos.rotulo_de_botao("exportar_pgn"),
                style=comandos.estilo("exportar_pgn"),
                command=self._on_export,
            ))
        self.btn_cancel_export = livro.adicionar(
            ttk.Button(
                livro,
                text=comandos.rotulo_de_botao("cancelar_exportacao"),
                style=comandos.estilo("cancelar_exportacao"),
                command=self._on_cancel_export,
                state=tk.DISABLED,
            )
        )
        Tooltip(
            self.btn_export,
            "Fica cinza durante a exportação, que roda uma por vez. Precisa de um PDF aberto.\n"
            "A exportação grava um parcial a cada 5 páginas e retoma de onde parou.",
        )
        Tooltip(
            self.btn_cancel_export,
            "Só fica ativo durante a exportação. O que já foi gravado no parcial continua valendo;\n"
            "a exportação seguinte retoma dali.",
        )

        vista.adicionar(ttk.Button(
                vista,
                text=comandos.rotulo_de_botao("pagina_anterior"),
                style=comandos.estilo("pagina_anterior"),
                command=self.prev_page,
            ))
        vista.adicionar(ttk.Button(
                vista,
                text=comandos.rotulo_de_botao("proxima_pagina"),
                style=comandos.estilo("proxima_pagina"),
                command=self.next_page,
            ))
        vista.adicionar(ttk.Label(vista, text="Página"))
        self.spin_page = vista.adicionar(
            # **Sem `textvariable`, e é isso que põe o campo em base 1 (S-328).** O `IntVar`
            # continua sendo o índice interno, base 0, que trinta chamadas leem; o widget mostra
            # `índice + 1`, que é a folha como o leitor de PDF e o título da janela a chamam.
            ttk.Spinbox(vista, from_=1, to=1, width=8, command=self.on_page_spin)
        )
        # As setas do `Spinbox` chamam `command`; **digitar não chama nada** (S-305). Sem estas
        # duas ligações, o número no campo mudava e a imagem na tela ficava onde estava.
        self.spin_page.bind("<Return>", self._on_page_typed)
        self.spin_page.bind("<KP_Enter>", self._on_page_typed)
        self.spin_page.bind("<FocusOut>", self._on_page_typed)
        vista.adicionar(ttk.Label(vista, text=strings.ZOOM_DA_PAGINA))
        vista.adicionar(ttk.Button(
                vista,
                text=comandos.rotulo_de_botao("zoom_menos"),
                style=comandos.estilo("zoom_menos"),
                width=3,
                command=self.diminuir_zoom,
            ))
        vista.adicionar(ttk.Button(
                vista,
                text=comandos.rotulo_de_botao("zoom_mais"),
                style=comandos.estilo("zoom_mais"),
                width=3,
                command=self.aumentar_zoom,
            ))
        self.lbl_zoom = vista.adicionar(ttk.Label(vista, text="70%"))
        self.btn_fit_width = vista.adicionar(ttk.Button(
                vista,
                text=comandos.rotulo_de_botao("ajustar_largura"),
                style=comandos.estilo("ajustar_largura"),
                command=self.fit_width,
            ))
        Tooltip(
            self.btn_fit_width,
            # A dica dizia que `Ctrl + roda` "faz o mesmo" que este botão, e ele **não** faz:
            # o botão enquadra a largura de uma vez, e a roda com Ctrl aproxima e afasta por
            # passos, ancorada no ponteiro. São dois gestos, e a frase juntava os dois (S-333).
            f"{atalhos.acelerador('ajustar_largura')} faz o mesmo pelo teclado.\n"
            "Ctrl + roda do mouse aproxima e afasta, com o ponteiro como âncora.\n"
            "A roda sozinha rola a página; na borda, ela vira para a página seguinte.",
        )
        self.btn_fit_page = vista.adicionar(ttk.Button(
                vista,
                text=comandos.rotulo_de_botao("ajustar_pagina"),
                style=comandos.estilo("ajustar_pagina"),
                command=self.fit_page,
            ))
        Tooltip(
            self.btn_fit_page,
            "A folha inteira na tela. É o enquadramento de escolher qual diagrama abrir;\n"
            "'Ajustar à largura' é o de ler o enunciado de um.",
        )
        self.chk_flip = vista.adicionar(
            ttk.Checkbutton(
                vista,
                text=comandos.rotulo_de_botao("roda_vira_pagina"),
                variable=self.flip_pages_var,
                command=self._on_prefs_changed,
            )
        )
        Tooltip(
            self.chk_flip,
            "Ligado: rolar além do fim da página vai para a próxima, no topo.\n"
            "Desligado: a roda só rola dentro da página exibida.",
        )
        self.chk_boxes = vista.adicionar(
            ttk.Checkbutton(
                vista,
                text=comandos.rotulo_de_botao("marcar_diagramas"),
                variable=self.show_boxes_var,
                command=self.on_boxes_toggle,
            )
        )
        Tooltip(
            self.chk_boxes,
            "Desenha um retângulo sobre cada diagrama que o detector achou na página.\n"
            "Clique num deles para abri-lo na aba Resultado.",
        )

        # **Depois das barras, e não antes.** `update_zoom_label` escreve no `lbl_zoom`, que
        # é criado acima -- montar o rodapé primeiro escreveria no rótulo da montagem
        # anterior, que a remontagem acabou de destruir.
        if montagem == pele.CROMO_FOCO:
            self._montar_rodape_de_zoom()

    def _montar_rodape_de_zoom(self) -> None:
        """O deslizador da pele "Foco", no rodapé do painel (S-225).

        **O que ele substitui são três controles, e não cinco**: os botões `-` e `+` e o rótulo,
        que ele passa a dizer. "Ajustar à largura" e "Ajustar à página" continuam existindo --
        enquadrar não é um valor de zoom, é uma pergunta sobre a página que o deslizador não sabe
        responder --, e nesta pele elas moram no menu, como os outros dezoito controles.

        `Ctrl+0`, a roda com `Ctrl` e as duas de enquadrar continuam funcionando e **movem** o
        deslizador: quem sincroniza é `update_zoom_label`, que já era chamada por todos eles.
        """
        rodape_do_painel = ttk.Frame(self._box)
        rodape_do_painel.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 6))
        self._rodape_de_zoom = rodape_do_painel

        ttk.Label(rodape_do_painel, text=strings.ZOOM_DA_PAGINA).pack(side=tk.LEFT)
        self._lbl_zoom_deslizador = ttk.Label(rodape_do_painel, width=6, anchor="e")
        self._lbl_zoom_deslizador.pack(side=tk.RIGHT)
        self._deslizador = ttk.Scale(
            rodape_do_painel,
            from_=0.0,
            to=LADO_DO_DESLIZADOR,
            orient=tk.HORIZONTAL,
            command=self._ao_arrastar_zoom,
        )
        self._deslizador.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.update_zoom_label()

    def _ao_arrastar_zoom(self, valor: str) -> None:
        """O arrasto. Sem âncora, então o ponto preservado é o centro da vista -- que é o que
        `apply_zoom` já faz para os botões `+` e `-`."""
        if self._movendo_o_deslizador:
            return
        self.apply_zoom(zoom_da_posicao(float(valor)))

    def _sincronizar_deslizador(self) -> None:
        """Põe o deslizador no zoom em vigor, venha ele de onde vier."""
        if self._deslizador is None:
            return
        self._movendo_o_deslizador = True
        try:
            self._deslizador.set(posicao_do_zoom(self.zoom_var.get()))
        finally:
            self._movendo_o_deslizador = False

    BOTOES_COM_ESTADO = (
        "btn_system_reader",
        "btn_ocr_best",
        "btn_ocr_all",
        "btn_select",
        "btn_export",
        "btn_cancel_export",
    )
    """Os botões das barras cujo `state` é **estado de trabalho**, e não de construção.

    Ler o `state` de cada um antes de destruir e devolvê-lo depois é mais curto e mais exato que
    guardar bandeiras: "Cancelar exportação" só está ativo durante uma exportação, e os três de
    OCR ficam cinzas enquanto um roda. Uma troca de pele no meio de uma exportação devolveria os
    seis ao estado de janela recém-aberta, que é a mentira mais cara que a remontagem pode contar.
    """

    def remontar_cromo(
        self,
        montagem: str = pele.CROMO_CLASSICO,
        *,
        refazer_linha_de_campo: Callable[[ttk.Frame], None] | None = None,
    ) -> None:
        """Destrói as duas barras e a linha de campo, e as refaz no lugar (S-222).

        **O que ela não toca é o item.** O canvas, a página renderizada, o `page_rgb`, os `Var`
        de zoom e de página, as ligações de roda e o PDF aberto continuam onde estavam -- então
        nada precisa ser salvo e restaurado. É a fronteira que a Fase 6 e a S-49 já pagaram: o
        conteúdo não mora nos widgets do cromo.

        **E é por isso que as ligações não se refazem.** `_bind_wheel` usa `bind_all` com
        `add="+"`, que **acumula**; refazê-la a cada troca deixaria N cópias da mesma tecla depois
        de N trocas. Ela é do painel, o painel sobrevive à troca, e a resposta certa é não
        chamá-la de novo. O mesmo vale para os dez atalhos, que são da janela.
        """
        estados = {nome: str(getattr(self, nome).cget("state")) for nome in self.BOTOES_COM_ESTADO}
        for barra in (self.barra_livro, self.barra_vista):
            barra.destroy()
        if self._rodape_de_zoom is not None:
            self._rodape_de_zoom.destroy()
            self._rodape_de_zoom = self._deslizador = self._lbl_zoom_deslizador = None
        self._montar_barras(montagem, antes=self.field_row)
        for nome, estado in estados.items():
            getattr(self, nome).configure(state=estado)
        self._resincronizar_barras()

        if refazer_linha_de_campo is not None:
            for filho in self.field_row.winfo_children():
                filho.destroy()
            refazer_linha_de_campo(self.field_row)

    def _resincronizar_barras(self) -> None:
        """O que as barras recém-nascidas não sabem: o livro aberto, o zoom e a seleção em curso.

        Os `Var` sobrevivem à destruição dos widgets -- eles são do painel --, mas o que é escrito
        num `config` na hora do evento, não: o nome do PDF, o teto do `Spinbox` e o rótulo que o
        `selecionar_area` troca quando liga.
        """
        self.update_zoom_label()
        if self.source is not None:
            self.lbl_pdf.config(text=f"{self.name} ({self.page_count} págs)")
            self.btn_system_reader.configure(state=tk.NORMAL)
            self._faixa_do_campo_de_pagina()
        if self._select_mode:
            self.btn_select.configure(text=comandos.rotulo_alternado("selecionar_area"))

    def _bind_wheel(self) -> None:
        """Liga a roda na janela inteira, e não no canvas -- ver `_pointer_over_canvas`."""
        raiz = self.winfo_toplevel()
        # `add="+"` em todas: `bind_all` sem ele **substitui** a ligação anterior da mesma
        # sequência, e este painel é construído depois das abas roláveis da S-150 -- sem o `+`
        # ele apagaria a roda delas em silêncio. Cada uma checa se o ponteiro está sobre si e
        # só então devolve `"break"`, então conviver é a única coisa que elas precisam fazer.
        raiz.bind_all("<MouseWheel>", self._on_wheel, add="+")
        raiz.bind_all("<Shift-MouseWheel>", self._on_wheel_horizontal, add="+")
        raiz.bind_all("<Control-MouseWheel>", self._on_wheel_zoom, add="+")
        # X11 não tem `MouseWheel`: a roda são os botões 4 e 5, sem delta.
        raiz.bind_all("<Button-4>", partial(self._on_wheel_x11, delta=120), add="+")
        raiz.bind_all("<Button-5>", partial(self._on_wheel_x11, delta=-120), add="+")

    # ------------------------------------------------------------------------------- zoom

    @property
    def page_index(self) -> int:
        return int(self.page_index_var.get())

    def zoom(self, delta: float) -> None:
        """Os botões `+` e `-`. Continuam aditivos: um clique, um passo previsível."""
        self.apply_zoom(self.zoom_var.get() + delta)

    def aumentar_zoom(self) -> None:
        """Um passo para mais. Existe como método porque o botão e o item de menu da S-223
        precisam do **mesmo** passo, e dois lambdas com o número dentro são dois números."""
        self.zoom(PASSO_DE_ZOOM)

    def diminuir_zoom(self) -> None:
        self.zoom(-PASSO_DE_ZOOM)

    def apply_zoom(self, value: float, *, anchor: tuple[int, int] | None = None) -> None:
        """Troca o zoom preservando o ponto de referência. `anchor` é (x, y) no widget.

        Sem âncora o ponto preservado é o **centro da vista**, que é o que faz o botão `+`
        aumentar o que está no meio da tela em vez de saltar para o canto superior esquerdo.
        """
        antigo = float(self.zoom_var.get())
        novo = clamp_zoom(value)
        if novo == antigo or self.page_rgb is None:
            self.zoom_var.set(novo)
            self.update_zoom_label()
            return

        largura = float(self.page_rgb.shape[1])
        altura = float(self.page_rgb.shape[0])
        ax, ay = anchor if anchor is not None else (self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2)
        # Em coordenada de **página**: a âncora é um ponto da folha, e o desvio da S-157 não é.
        px, py = self._para_pagina(self.canvas.canvasx(ax), self.canvas.canvasy(ay))
        fx = anchor_after_zoom(
            pointer_canvas=px,
            pointer_widget=float(ax),
            old_span=largura * antigo,
            new_span=largura * novo,
        )
        fy = anchor_after_zoom(
            pointer_canvas=py,
            pointer_widget=float(ay),
            old_span=altura * antigo,
            new_span=altura * novo,
        )

        self.zoom_var.set(novo)
        self.update_zoom_label()
        self.refresh_view(reset_scroll=False)
        self.canvas.xview_moveto(fx)
        self.canvas.yview_moveto(fy)
        self._on_zoom_changed(novo)

    def fit_width(self) -> None:
        """Ajusta o zoom para a página caber na largura visível."""
        if self.page_rgb is None:
            self._on_status("Abra um PDF antes de ajustar o zoom.")
            return
        alvo = fit_width_zoom(viewport_px=self.canvas.winfo_width(), page_px=int(self.page_rgb.shape[1]))
        if alvo is None:
            return
        self.apply_zoom(alvo, anchor=(0, 0))
        self._on_status(f"Zoom ajustado à largura: {int(alvo * 100)}%.")

    def fit_page(self) -> None:
        """Ajusta o zoom para a **página inteira** caber na área visível (S-157).

        É o enquadramento de escolher entre os nove diagramas de uma página de exercícios;
        "ajustar à largura" é o de ler o enunciado de um deles.
        """
        alvo = self._zoom_de_pagina_inteira()
        if alvo is None:
            if self.page_rgb is None:
                self._on_status("Abra um PDF antes de ajustar o zoom.")
            return
        self.apply_zoom(alvo, anchor=(0, 0))
        self._on_status(f"Zoom ajustado à página: {int(alvo * 100)}%.")

    def _zoom_de_pagina_inteira(self) -> float | None:
        if self.page_rgb is None:
            return None
        return fit_page_zoom(
            viewport_w=self.canvas.winfo_width(),
            viewport_h=self.canvas.winfo_height(),
            page_w=int(self.page_rgb.shape[1]),
            page_h=int(self.page_rgb.shape[0]),
        )

    def _ao_redimensionar(self, _event: tk.Event) -> None:
        """A janela mudou de tamanho: recentraliza, e enquadra o livro novo (S-157).

        Duas coisas acontecem aqui, e a segunda só uma vez por livro. **Recentralizar** é o
        trabalho de sempre: a folga entre a página e o canvas mudou, então o desvio mudou.
        **Enquadrar** é o primeiro `<Configure>` de um livro que ainda não tem zoom escolhido --
        e ele espera este momento porque antes de a janela ser mapeada `winfo_width()` devolve
        **1**, e ajustar à página ali daria o zoom mínimo em toda abertura.
        """
        if self.page_rgb is None:
            return
        if self._enquadramento_pendente:
            alvo = self._zoom_de_pagina_inteira()
            # A bandeira só cai quando o enquadramento de fato **aconteceu**. Baixá-la antes do
            # `if` deixava o item à mercê da ordem dos eventos: o primeiro `<Configure>` de uma
            # janela ainda por medir devolve `None`, e o livro abria no zoom padrão para sempre.
            if alvo is not None:
                self._enquadramento_pendente = False
                self.apply_zoom(alvo, anchor=(0, 0))
                return
        self.refresh_view(reset_scroll=False)

    # --------------------------------------------------------------------- roda e arrasto

    def _pointer_over_canvas(self, event: tk.Event) -> bool:
        """Se o ponteiro está sobre a página.

        A roda é ligada com `bind_all` porque no Windows o `<MouseWheel>` vai para o widget com
        **foco**, e não para o que está sob o ponteiro: ligada só no canvas, ela não rolaria
        nada enquanto o cursor de texto estivesse no campo de FEN. Ligada na janela inteira, é
        esta função que devolve o comportamento que todo mundo espera -- rola o que está
        debaixo do mouse -- sem mexer no foco de ninguém.

        **A conta é aritmética de propósito.** A primeira versão perguntava ao
        `winfo_containing`, que no Windows resolve pelo `WindowFromPoint` do sistema: ele
        devolve `None` quando *qualquer* outra janela cobre aquele ponto da tela. Medido com a
        janela do app atrás do terminal, sobre um canvas de 909x740 na posição certa:
        `winfo_containing` devolveu `None` e a roda não rolava nada. Um retângulo comparado com
        as coordenadas do próprio widget não depende de empilhamento -- nem do tooltip que o
        painel abre justamente por cima dele.

        **E o retângulo sozinho era largo demais (S-332).** Ele diz "o ponteiro está na área do
        canvas", que não é a mesma coisa que "o canvas é o que está debaixo do ponteiro": com a
        paleta de comandos, uma lista suspensa ou um diálogo por cima da folha, a roda rolava o
        PDF **atrás** deles e devolvia `"break"`, então o widget de cima não rolava nada. Quem
        girava a roda sobre uma lista via a página do livro passar.

        A conta continua sendo a mesma, e o `winfo_containing` volta como **desempate**: quando
        ele nomeia um widget desta aplicação, ele sabe o que está por cima, e só o canvas (ou um
        filho dele) manda na roda; quando devolve `None` -- janela de outro programa cobrindo o
        ponto, que é o caso medido -- vale o retângulo, como antes.
        """
        if not self.canvas.winfo_exists() or not self.canvas.winfo_ismapped():
            return False
        x, y = self._canvas_event(event)
        if not (0 <= x < self.canvas.winfo_width() and 0 <= y < self.canvas.winfo_height()):
            return False
        return self._canvas_esta_por_cima(event)

    def _canvas_esta_por_cima(self, event: tk.Event) -> bool:
        """Se o widget desta aplicação sob o ponteiro é o canvas. `True` quando não se sabe."""
        try:
            alvo = self.canvas.winfo_containing(int(event.x_root), int(event.y_root))
        except (tk.TclError, KeyError):
            return True
        if alvo is None:
            return True
        return alvo is self.canvas or str(alvo).startswith(f"{self.canvas}.")

    def _canvas_event(self, event: tk.Event) -> tuple[int, int]:
        """O evento em coordenadas do canvas. Vem da janela, então o deslocamento é relativo."""
        return (
            int(event.x_root) - self.canvas.winfo_rootx(),
            int(event.y_root) - self.canvas.winfo_rooty(),
        )

    def _on_wheel(self, event: tk.Event) -> str | None:
        if not self._pointer_over_canvas(event) or self.page_rgb is None:
            return None

        direcao = wheel_direction(int(event.delta))
        decorrido = time.monotonic() - self._last_page_flip
        acao = decide_wheel(
            direction=direcao,
            view=self.canvas.yview(),
            flip_pages=bool(self.flip_pages_var.get()),
            since_last_flip=decorrido,
        )
        if acao is WheelAction.NEXT_PAGE:
            self._flip_page(+1)
        elif acao is WheelAction.PREV_PAGE:
            self._flip_page(-1)
        else:
            self.canvas.yview_scroll(-direcao * WHEEL_SCROLL_UNITS, "units")
        return "break"

    def _on_wheel_horizontal(self, event: tk.Event) -> str | None:
        if not self._pointer_over_canvas(event) or self.page_rgb is None:
            return None
        self.canvas.xview_scroll(-wheel_direction(int(event.delta)) * WHEEL_SCROLL_UNITS, "units")
        return "break"

    def _on_wheel_zoom(self, event: tk.Event) -> str | None:
        if not self._pointer_over_canvas(event) or self.page_rgb is None:
            return None
        direcao = wheel_direction(int(event.delta))
        self.apply_zoom(zoomed(self.zoom_var.get(), direcao), anchor=self._canvas_event(event))
        return "break"

    def _on_wheel_x11(self, event: tk.Event, *, delta: int) -> str | None:
        """Botões 4 e 5 do X11 traduzidos para o `delta` que o resto do painel entende.

        `event.state` é anotado como `int | str` no `tkinter`, e é `int` em evento de mouse --
        o `str` existe por causa dos eventos virtuais.
        """
        event.delta = delta
        estado = event.state if isinstance(event.state, int) else 0
        if estado & 0x0004:  # Control
            return self._on_wheel_zoom(event)
        if estado & 0x0001:  # Shift
            return self._on_wheel_horizontal(event)
        return self._on_wheel(event)

    def _flip_page(self, delta: int) -> None:
        """Vira a página pela roda, e põe a vista na borda por onde ela entrou.

        Entrar pelo topo ao descer e pelo rodapé ao subir é o que faz a sequência parecer um
        documento contínuo; cair sempre no topo faria a leitura para trás recomeçar a página.
        """
        antes = self.page_index
        if delta > 0:
            self.next_page()
        else:
            self.prev_page()
        if self.page_index == antes:
            return

        self._last_page_flip = time.monotonic()
        self.canvas.yview_moveto(0.0 if delta > 0 else 1.0)

    def _on_pan_start(self, event: tk.Event) -> None:
        self.canvas.scan_mark(event.x, event.y)
        self._panning = True
        self.canvas.configure(cursor="fleur")

    def _on_pan_move(self, event: tk.Event) -> None:
        if self._panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_pan_end(self, _event: tk.Event) -> None:
        self._panning = False
        self.canvas.configure(cursor="")

    def set_zoom(self, value: float) -> None:
        """Aplica um zoom vindo de fora -- hoje, o que estava gravado no estado.

        E com isso **cancela o enquadramento inicial da S-157**: um zoom guardado é uma escolha
        do usuário, e ajustar à página por cima dela seria a interface desfazendo o que ele fez.
        A regra inteira do item cabe aqui: sem escolha guardada, a primeira página aparece
        inteira; com escolha, ela vale.
        """
        self._enquadramento_pendente = False
        self.zoom_var.set(value)
        self.update_zoom_label()

    def update_zoom_label(self) -> None:
        """O texto do zoom, nos dois lugares onde ele aparece, e a posição do deslizador.

        O texto vem de `ui/formato.py` desde a S-225: era um `f"{int(...)}%"` cravado aqui, e a
        pele "Foco" o mostraria num segundo rótulo -- duas formatações do mesmo número é como
        elas divergem.
        """
        texto = formato.porcentagem(self.zoom_var.get(), casas=0)
        self.lbl_zoom.config(text=texto)
        if self._lbl_zoom_deslizador is not None:
            self._lbl_zoom_deslizador.config(text=texto)
        self._sincronizar_deslizador()

    def set_ocr_controls_enabled(self, enabled: bool) -> None:
        estado = tk.NORMAL if enabled else tk.DISABLED
        for botao in (self.btn_ocr_best, self.btn_ocr_all, self.btn_select):
            botao.configure(state=estado)

    def set_export_controls_enabled(self, enabled: bool) -> None:
        self.btn_export.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        # O cancelar só existe enquanto ha o que cancelar.
        self.btn_cancel_export.configure(state=tk.DISABLED if enabled else tk.NORMAL)

    def disable_cancel_button(self) -> None:
        self.btn_cancel_export.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------- abrir e navegar

    def open_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            title="Selecione o PDF",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            initialdir=str(self._initial_dir),
        )
        if filename:
            self.load_pdf(Path(filename))

    @property
    def interruptores_de_vista(self) -> dict[str, tk.BooleanVar]:
        """Os dois interruptores de visualização, por nome de comando do menu (S-161).

        Mora aqui e não na janela porque as duas `BooleanVar` são deste painel: quem acrescentar
        uma terceira preferência de visualização a declara ao lado das outras duas, e ela aparece
        no menu sem ninguém lembrar de ir mexer no `app_tkinter.py`.
        """
        return {"marcar_diagramas": self.show_boxes_var, "roda_vira_pagina": self.flip_pages_var}

    def open_in_system_reader(self) -> None:
        """Manda o PDF para o leitor do sistema. Falhar aqui é aviso, e não erro do app."""
        if self.source is None:
            return
        try:
            open_in_system_reader(self.source)
            self._on_status(f"{self.name} enviado para o leitor do sistema.")
        except Exception as exc:  # noqa: BLE001 - `startfile` e `Popen` levantam tipos diversos
            logger.warning("Não foi possível abrir %s no leitor do sistema: %s", self.source, exc)
            messagebox.showwarning(
                "Leitor do sistema",
                f"Não foi possível abrir o PDF no leitor do sistema:\n{exc}",
            )

    def load_pdf(self, pdf_path: Path) -> None:
        """Troca o livro aberto. **Abre antes de trocar** (S-123).

        A ordem é a correção. Antes, `_on_pdf_opened` era a primeira linha e
        `get_pdf_page_count` -- a única que levanta com arquivo corrompido -- a quarta. Um PDF
        que não abria já tinha limpado as caixas da página, descartado os resultados do livro
        anterior e apontado a Galeria para o arquivo quebrado: **a tela continuava mostrando o
        livro anterior e o programa, por dentro, estava no que não abriu.** O `Ctrl+S`
        seguinte gravava a amostra sob o nome errado.

        Contar as páginas é abrir o documento de verdade, então serve de validação sem custo
        próprio: o `page_count` que ela devolve é o mesmo que seria usado adiante.

        O `except` continua largo de propósito -- no bundle da S-55 (`console=False`) uma
        exceção solta nesta chamada não deixa rastro nenhum -- mas a frase sobre o livro
        anterior é condicionada ao estado real, e não à suposição de que a falha foi na
        abertura: se algo quebrar depois da troca, ela não é dita.
        """
        try:
            page_count = get_pdf_page_count(pdf_path)

            self._on_pdf_opened(pdf_path)
            self.source = pdf_path
            self.name = pdf_path.name
            self.page_count = page_count
            self.lbl_pdf.config(text=f"{self.name} ({self.page_count} págs)")
            self.btn_system_reader.configure(state=tk.NORMAL)

            alvo = self._initial_page_for(pdf_path)
            self.page_index_var.set(max(0, min(self.page_count - 1, alvo)))
            self._faixa_do_campo_de_pagina()
            self.page_loaded_for_index = None
            self.render_current_page()
        except Exception as exc:
            logger.exception("Falha ao abrir %s.", pdf_path)
            preservado = self.source is not None and self.source != pdf_path
            resto = f"\n\n{self.name} continua aberto." if preservado else ""
            messagebox.showerror("Abrir PDF", f"Falha ao abrir {pdf_path.name}:\n{exc}{resto}")

    def on_page_spin(self) -> None:
        """As setas do campo. Sem `textvariable`, elas mudam o texto e mais nada (S-328).

        Delegar a `_on_page_typed` é o que faz seta e digitação passarem pelo mesmo caminho --
        a conversão de base, o corte na faixa do livro e a reposição do número ficam num lugar
        só, que é o que a S-305 já queria e o `textvariable` dividia em dois.
        """
        self._on_page_typed()

    def _on_page_typed(self, _evento: object = None) -> None:
        """O número **digitado** no campo de página vira navegação, e o lixo digitado volta atrás.

        **Dois defeitos numa linha (S-305).** O `command` de um `ttk.Spinbox` só dispara nas
        setas: digitar `15` e teclar `Enter` mudava `page_index_var` e não mudava a imagem.
        Medido num livro de 20 folhas -- `page_index = 15` com `page_loaded_for_index = 0`, a
        imagem da folha 1 na tela, e o rodapé passando a dizer "p. 16 de 20". As caixas de
        diagrama da folha exibida eram então recusadas por serem "de outra página", e a
        detecção passava a falar de uma folha que ninguém estava vendo.

        E texto não numérico derrubava a navegação inteira: `page_index` faz
        `int(self.page_index_var.get())` sobre um `IntVar`, e com `abc` no campo as cinco
        funções que o leem levantam `TclError`. Não há `report_callback_exception` no projeto,
        então isso ia para o stderr e o botão simplesmente não fazia nada.

        **O lixo restaura o campo em vez de navegar.** Mandar para a página 1 seria escolher um
        destino que ninguém pediu; deixar o texto inválido no widget manteria a dessincronia
        que este item conserta. E o `<FocusOut>` com o campo vazio -- que acontece a cada
        limpeza no meio da edição -- cai no mesmo caminho: repõe o número e não navega.
        """
        if self.page_count == 0:
            return
        try:
            digitado = int(str(self.spin_page.get()).strip())
        except (ValueError, tk.TclError):
            self._repor_numero_da_pagina()
            return
        # **Contra `page_loaded_for_index`, e não contra `page_index`.** `go_to_page` compara com
        # `page_index` e recusaria a digitação de uma folha que o índice já aponta mas a tela
        # ainda não mostra. Quem sabe que folha está na tela é `page_loaded_for_index`.
        alvo = max(0, min(self.page_count - 1, digitado - 1))
        self.page_index_var.set(alvo)
        if alvo != self.page_loaded_for_index or self.page_rgb is None:
            self.page_loaded_for_index = None
            self.render_current_page()
        self._repor_numero_da_pagina()

    def _faixa_do_campo_de_pagina(self) -> None:
        """A faixa do `Spinbox` em base 1: de 1 até o total de folhas (S-328).

        Livro nenhum aberto deixa `1..1` em vez de `0..0`, porque "página 0" não existe na
        contagem que o campo passou a usar -- e um `Spinbox` vazio com teto 0 é o que fazia a
        seta para baixo escrever o número que o resto da tela nega.
        """
        self.spin_page.config(from_=1, to=max(self.page_count, 1))
        self._repor_numero_da_pagina()

    def _repor_numero_da_pagina(self) -> None:
        """Devolve ao campo a folha que a tela de fato mostra, em base 1 (S-328)."""
        try:
            atual = self.page_index
        except tk.TclError:
            atual = self.page_loaded_for_index or 0
            self.page_index_var.set(atual)
        self.spin_page.delete(0, tk.END)
        self.spin_page.insert(0, str(atual + 1))

    def prev_page(self) -> None:
        self._ir_para(self.page_index - 1)

    def next_page(self) -> None:
        self._ir_para(self.page_index + 1)

    def _ir_para(self, alvo: int) -> None:
        """A virada de uma folha, e o que ela faz quando **não há folha para onde virar** (S-304).

        `prev_page` e `next_page` grampeavam o índice e mandavam rasterizar de qualquer jeito.
        Na última página, cada giro da roda e cada `Page Down` re-rasterizava a **mesma** folha
        -- medido: cinco giros, cinco `render_pdf_page(2)` --, e como `render_current_page`
        termina em `yview_moveto(0)`, a vista voltava ao topo a cada um. Quem lia o fim de uma
        página larga era jogado para o começo dela, repetidamente, sem que nada mudasse na tela
        além da rolagem. A 220 DPI, que é o padrão da janela, cada uma dessas viagens é uma
        rasterização inteira jogada fora, e `_on_page_rendered` ainda grava o estado em disco.

        A guarda testa `page_rgb` além do índice de propósito: só o índice tiraria também o
        único jeito de tentar de novo depois de um render que falhou -- com a imagem ausente,
        um `Page Down` na última página ainda re-tenta.
        """
        if self.page_count == 0:
            return
        alvo = max(0, min(self.page_count - 1, int(alvo)))
        if alvo == self.page_index and self.page_rgb is not None:
            return
        self.page_index_var.set(alvo)
        self._repor_numero_da_pagina()
        self.page_loaded_for_index = None
        self.render_current_page()

    def go_to_page(self, page_index: int) -> bool:
        """Vai para uma página qualquer. Devolve se **mudou** de página.

        Existe para a galeria (S-67), que navega por diagrama e precisa arrastar o
        visualizador junto. Devolver "mudou" e não "conseguiu" é o que impede o vaivém: a
        galeria só reage quando algo de fato se moveu.
        """
        if self.page_count == 0:
            return False
        alvo = max(0, min(self.page_count - 1, int(page_index)))
        if alvo == self.page_index:
            return False
        self.page_index_var.set(alvo)
        self._repor_numero_da_pagina()
        self.page_loaded_for_index = None
        self.render_current_page()
        return True

    ESPERA_DO_DPI_MS = 400
    """Quanto esperar o campo de DPI parar de mudar antes de re-rasterizar (S-329)."""

    def observar_dpi(self, var: tk.Variable) -> None:
        """Re-rasteriza a folha quando o DPI muda -- e só quando ele para de mudar (S-329).

        O `trace_add` dispara a **cada tecla**: digitar `220` à mão passa por `2`, `22` e `220`,
        e cada disparo custaria uma rasterização de ~0,3 s em dois DPI que ninguém pediu. O
        `after` espera a pessoa terminar, e o `after_cancel` é o que impede a fila.

        Mora no painel, e não na janela, porque quem sabe que a imagem em memória envelheceu é
        quem a rasterizou -- e porque a catraca de `app_tkinter.py` cobra exatamente isso.
        """
        self._dpi_var = var
        var.trace_add("write", self._on_dpi_changed)

    def _on_dpi_changed(self, *_args: object) -> None:
        if self._dpi_after is not None:
            self.after_cancel(self._dpi_after)
        self._dpi_after = self.after(self.ESPERA_DO_DPI_MS, self._aplicar_dpi)

    def _aplicar_dpi(self) -> None:
        self._dpi_after = None
        try:
            dpi = int(self._dpi())
        except tk.TclError:
            return  # campo vazio no meio da digitação: não há DPI para aplicar
        if dpi == self._dpi_rasterizado:
            return
        self._dpi_rasterizado = dpi
        self.invalidar_rasterizacao()

    def invalidar_rasterizacao(self) -> None:
        """A imagem em memória não vale mais: rasteriza de novo agora (S-329).

        Quem chama é quem mudou uma decisão de **rasterização** -- hoje só o DPI. Zoom não entra
        aqui: ele reescala a mesma imagem, de propósito, e re-renderizar a cada passo de zoom
        seria trocar a fluidez por nitidez que o `refresh_view` já dá.

        Sem livro aberto não há o que invalidar, e o `render_current_page` já sabe disso; a
        guarda existe para não gastar a chamada.
        """
        self.page_loaded_for_index = None
        if self.source is not None:
            self.render_current_page()

    def render_current_page(self) -> bool:
        """Rasteriza a página atual, se ainda não estiver em memória. `True` se há imagem.

        Devolve booleano porque quem chama precisa saber se pode seguir para o OCR: falhar
        aqui e prosseguir mandaria o serviço reconhecer a página anterior.
        """
        if self.source is None:
            return False

        idx = self.page_index
        if self.page_loaded_for_index == idx and self.page_rgb is not None:
            return True

        # As caixas da página anterior morrem aqui, e não quando as novas chegarem: a detecção
        # roda em thread, e deixá-las na tela nesse intervalo apontaria para diagramas da
        # página que acabou de sair -- sobre a imagem da que entrou.
        self.clear_diagram_boxes()
        # Antes de trocar de página, o que esta no editor tem de ir para o cache da página
        # de origem -- inclusive o texto que o usuário acabou de digitar no campo de FEN.
        self._on_before_page_change()
        try:
            self._on_status(f"Renderizando página {idx + 1}...")
            self.page_rgb = render_pdf_page(self.source, idx, dpi=self._dpi())
            self.page_loaded_for_index = idx
            self.refresh_view()
            self._on_status(f"Página {idx + 1} pronta.")
        except Exception as exc:
            self.page_rgb = None
            self.page_loaded_for_index = None
            messagebox.showerror("Mostrar a página", f"Falha ao renderizar página:\n{exc}")
            return False

        self._on_page_rendered(idx)
        return True

    def refresh_view(self, *, reset_scroll: bool = True) -> None:
        """Redesenha a página no zoom atual. `reset_scroll` desligado é o caminho do zoom.

        Página nova começa no topo; mudar o zoom, não -- ali quem manda é a âncora calculada
        por `apply_zoom`, e voltar ao topo antes dela jogaria fora o lugar onde a pessoa estava.
        """
        if self.page_rgb is None:
            return

        zoom = float(self.zoom_var.get())
        pil = Image.fromarray(self.page_rgb)
        alvo = (max(1, int(pil.width * zoom)), max(1, int(pil.height * zoom)))
        if alvo != (pil.width, pil.height):
            pil = pil.resize(alvo, Image.Resampling.LANCZOS)

        self._page_photo = ImageTk.PhotoImage(pil)
        self.canvas.delete("all")
        # A página no meio da área visível, e não encostada no canto (S-157). O desvio é zero
        # quando ela é maior que o canvas -- aí não há folga a repartir --, e a região de
        # rolagem cresce junto, senão a página deslocada cairia fora do que o Tk sabe rolar.
        self._desvio = (
            desvio_de_centralizacao(pil.width, self.canvas.winfo_width()),
            desvio_de_centralizacao(pil.height, self.canvas.winfo_height()),
        )
        self._canvas_image_id = self.canvas.create_image(
            self._desvio[0], self._desvio[1], anchor="nw", image=self._page_photo
        )
        self._select_rect_id = None
        self.canvas.configure(
            scrollregion=regiao_de_rolagem(
                (pil.width, pil.height), (self.canvas.winfo_width(), self.canvas.winfo_height())
            )
        )
        if reset_scroll:
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
        # Depois da imagem: `delete("all")` acima levou os retângulos junto, e eles dependem do
        # zoom que acabou de ser aplicado.
        self._draw_boxes()

    # ------------------------------------------------------------ diagramas marcados (S-68)

    def set_diagram_boxes(self, boxes: PageBoxes) -> bool:
        """Recebe as caixas de uma página. Devolve se elas eram **desta** página.

        A recusa é o que protege a tela do resultado atrasado: a detecção roda em thread, e
        quem a pediu para a página 16 pode já estar na 17 quando ela responde. Devolver
        booleano em vez de ignorar em silêncio deixa a janela registrar o descarte.
        """
        if boxes.page_index != self.page_index:
            logger.debug(
                "Caixas da página %d descartadas: a tela está na %d.", boxes.page_index, self.page_index
            )
            return False
        self.boxes = boxes
        self._draw_boxes()
        return True

    def clear_diagram_boxes(self) -> None:
        self.boxes = None
        self._selected_box = None
        self._hover_box = None
        self._draw_boxes()

    def select_box(self, index: int | None) -> None:
        """Marca qual diagrama está aberto no editor. `None` quando não é nenhum daqui."""
        if index == self._selected_box:
            return
        self._selected_box = index
        self._draw_boxes()

    def on_boxes_toggle(self) -> None:
        self._draw_boxes()
        self._on_prefs_changed()

    @property
    def selected_box(self) -> int | None:
        """O índice do retângulo destacado na página, ou `None` quando não há nenhum.

        **É a única resposta confiável a "qual é o selecionado" (S-306).** Quem escreve
        `_selected_box` é só `select_box`, e quem chama `select_box` é só
        `ChessOcrTkApp._sync_selected_box` -- que já aplica as três pré-condições (as caixas
        são as reconhecidas, o editor mostra esta página, e há itens no editor) e põe `None`
        fora delas. Ler daqui dá essas guardas de graça, e casa com o que a interface promete:
        "o selecionado" é o retângulo que está destacado na folha.
        """
        return self._selected_box

    def drop_selected_box(self) -> None:
        """Pede à janela que tire o retângulo do diagrama selecionado (S-177).

        Sem seleção não há o que tirar, e dizer isso é melhor que tirar "o primeiro": até a
        página ser lida, seleção nenhuma existe (`_sync_selected_box` a limpa para as caixas do
        detector), e é aí que o botão direito é o caminho.
        """
        if self.boxes is None or not len(self.boxes):
            self._on_status("Nenhuma caixa nesta página para tirar.")
            return
        if self._selected_box is None:
            self._on_status(
                "Nenhum diagrama selecionado. Clique com o botão direito sobre a caixa que "
                "você quer tirar."
            )
            return
        self._on_box_drop(self._selected_box)

    def _on_right_click(self, event: tk.Event) -> str | None:
        """Botão direito sobre um retângulo: tira aquele retângulo da página (S-177).

        Fora de um retângulo, não faz nada -- e não abre menu de contexto: o painel não tem
        outro comando por retângulo, e um menu de um item só é um clique a mais para a mesma
        ação. Durante a seleção de área o gesto cala, porque ali o botão direito não fala de
        caixa nenhuma.
        """
        if self._select_mode:
            return None
        indice = self._box_at_event(event)
        if indice is None:
            return None
        self._on_box_drop(indice)
        return "break"

    def _draw_boxes(self) -> None:
        """Redesenha os retângulos. Apagar por etiqueta, e não `delete("all")`: a página fica."""
        self.canvas.delete("diagram-box")
        self._update_boxes_label()
        if self.boxes is None or not self.show_boxes_var.get() or self.page_rgb is None:
            return

        zoom = float(self.zoom_var.get())
        for box in self.boxes.boxes:
            pagina = self.boxes.rect_of(box, zoom)
            x0, y0 = self._para_canvas(pagina[0], pagina[1])
            x1, y1 = self._para_canvas(pagina[2], pagina[3])
            selecionado = box.index == self._selected_box
            cor = box_color(box)
            traco = traco_da_caixa(box)
            # Uma propriedade visual, uma informação: a **cor** diz em que ponto do trabalho o
            # diagrama está e a **borda** diz qual está aberto no editor. Enquanto a seleção
            # era uma quarta cor, ela apagava o estado do diagrama selecionado -- justamente o
            # que se quer ver ao chegar nele.
            #
            # O traço é o segundo canal do mesmo estado (S-159): azul contra violeta dava
            # 1,20:1, e para ~8% dos homens "a fazer" e "não precisa" eram o mesmo retângulo.
            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline=cor,
                width=traco.espessura,
                dash=traco.tracejado or "",
                # Etiqueta própria: o contorno de estado é o único item cuja espessura e cujo
                # tracejado significam alguma coisa, e o teste precisa achá-lo entre o halo da
                # seleção e o fundo do número.
                tags=("diagram-box", TAG_CONTORNO),
            )
            if selecionado:
                # **Nada por cima do tabuleiro.** A primeira versão preenchia a caixa
                # selecionada com hachura, e os pontinhos caíam justamente sobre as casas que
                # se está tentando conferir -- que é para o que a caixa existe. A segunda
                # borda, por fora, marca a seleção sem gastar um pixel do diagrama.
                self.canvas.create_rectangle(
                    x0 - SELECTION_HALO_PX,
                    y0 - SELECTION_HALO_PX,
                    x1 + SELECTION_HALO_PX,
                    y1 + SELECTION_HALO_PX,
                    outline=cor,
                    width=2,
                    tags="diagram-box",
                )
            # O número vai num retângulo cheio: por cima do diagrama, texto solto some no
            # xadrez do tabuleiro justamente onde ele mais precisa ser lido. O glifo de estado
            # entra junto (S-159) -- a etiqueta já é preenchida, então ele não custa pixel.
            etiqueta = f"{box.label}{traco.glifo}"
            largura = 22 + (10 if traco.glifo else 0)
            self.canvas.create_rectangle(
                x0, y0 - 18, x0 + largura, y0, outline=cor, fill=cor, tags="diagram-box"
            )
            # Corpo em negrito, e não um degrau acima: o número é rótulo da interface sobre a
            # página, e quem aumenta a fonte do Windows aumenta este junto (S-149).
            self.canvas.create_text(
                x0 + largura // 2, y0 - 9, text=etiqueta, fill=tokens.RESERVA[tokens.TEXTO_SOBRE_MARCACAO],
                font=theme.fonte_atual(tipografia.CORPO, negrito=True), tags="diagram-box",
            )

    def _update_boxes_label(self) -> None:
        """Publica no rodapé o que se sabe dos diagramas da página exibida (S-163).

        A frase é de `ui/rodape.py` e a decisão de quando falar continua aqui: `None` é "ainda
        não se sabe" -- a página recém-rasterizada, com a detecção rodando -- e só "não há"
        autoriza dizer que ali não tem diagrama.
        """
        if self.boxes is None:
            self.estado_do_documento, self.pagina_concluida = "", False
        else:
            self.pagina_concluida = bool(len(self.boxes)) and self.boxes.all_saved
            self.estado_do_documento = rodape.descricao_dos_diagramas(
                len(self.boxes),
                lidos=sum(1 for box in self.boxes.boxes if box.recognized and not box.saved),
                salvos=sum(1 for box in self.boxes.boxes if box.saved),
                confirmados=sum(1 for box in self.boxes.boxes if box.confirmed and not box.saved),
                todos_salvos=self.pagina_concluida,
            )
        self._on_document_state(
            rodape.descricao_do_documento(self.name, self.page_index, self.page_count, self.estado_do_documento),
            self.pagina_concluida,
        )

    def _box_at_event(self, event: tk.Event) -> int | None:
        if self.boxes is None or not self.show_boxes_var.get() or self.page_rgb is None:
            return None
        x, y = self._para_pagina(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        return self.boxes.index_at(x, y, float(self.zoom_var.get()))

    def _on_hover(self, event: tk.Event) -> None:
        """Mão sobre o diagrama. É o que faz o retângulo parecer clicável antes do clique."""
        if self._select_mode:
            return
        indice = self._box_at_event(event)
        if indice == self._hover_box:
            return
        self._hover_box = indice
        self.canvas.configure(cursor="hand2" if indice is not None else "")

    # -------------------------------------------------------------------- seleção de área

    def toggle_area_selection(self) -> None:
        if self._select_mode:
            self.disable_area_selection("Seleção de área cancelada.")
            return
        if self.source is None or self.page_rgb is None:
            # Pré-condição no rodapé (S-164).
            self._on_status("Abra um PDF antes de selecionar uma área.")
            return

        self._select_mode = True
        self._select_start = None
        self._clear_overlay()
        self.canvas.configure(cursor="crosshair")
        self.btn_select.configure(text=comandos.rotulo_alternado("selecionar_area"))
        # As outras peles desenham o mesmo comando, e também precisam mostrar que ele é um
        # **modo** que está ligado (S-396). O botão desta barra continua sendo repintado aqui
        # porque ele existe mesmo quando a pele não o empacota.
        comandos.alternou("selecionar_area", ligado=True)
        self._on_status("Seleção ativa: arraste no PDF para reconhecer a área automaticamente.")

    def disable_area_selection(self, status_text: str = "") -> None:
        self._select_mode = False
        self._select_start = None
        self._hover_box = None
        self._clear_overlay()
        self.canvas.configure(cursor="")
        self.btn_select.configure(text=comandos.rotulo_de_botao("selecionar_area"))
        comandos.alternou("selecionar_area", ligado=False)  # S-396
        if status_text:
            self._on_status(status_text)

    def _clear_overlay(self) -> None:
        if self._select_rect_id is None:
            return
        try:
            self.canvas.delete(self._select_rect_id)
        except tk.TclError as exc:
            logger.debug("Retangulo de seleção já removido: %s", exc)
        self._select_rect_id = None

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        if self.page_rgb is None:
            return x, y
        zoom = float(self.zoom_var.get())
        return (
            max(0.0, min(x, float(self.page_rgb.shape[1]) * zoom)),
            max(0.0, min(y, float(self.page_rgb.shape[0]) * zoom)),
        )

    def _para_pagina(self, x: float, y: float) -> tuple[float, float]:
        """Do canvas para a página, descontando a centralização da S-157.

        **A fronteira que a centralização criou, e a única que ela criou.** Tudo que este painel
        calcula -- a caixa clicada, o retângulo da seleção, a âncora do zoom -- vive em
        coordenada de **página**, com a origem no canto da folha. O desvio existe só no desenho,
        e é aqui que ele entra e sai. Espalhá-lo pelos oito pontos de conversão seria a forma de
        um deles ficar para trás e a caixa clicada passar a ser a do vizinho.
        """
        return x - self._desvio[0], y - self._desvio[1]

    def _para_canvas(self, x: float, y: float) -> tuple[float, float]:
        """Da página para o canvas. O par de `_para_pagina`."""
        return x + self._desvio[0], y + self._desvio[1]

    def _point(self, event: tk.Event) -> tuple[float, float]:
        return self._clamp(*self._para_pagina(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)))

    def _on_press(self, event: tk.Event) -> None:
        self._press_at = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if not self._select_mode:
            # Fora do modo de seleção, o botão esquerdo é a mão do leitor: marca o ponto agora
            # e só arrasta se o ponteiro andar. Quem não andar continua sendo um clique, e o
            # clique continua abrindo o diagrama (S-68).
            self.canvas.scan_mark(event.x, event.y)
            return
        if self.page_rgb is None:
            return
        x, y = self._point(event)
        self._select_start = (x, y)
        self._clear_overlay()
        cx, cy = self._para_canvas(x, y)
        self._select_rect_id = self.canvas.create_rectangle(cx, cy, cx, cy, outline=tokens.RESERVA[tokens.TRACEJADO], width=2, dash=(6, 4))

    def _on_drag(self, event: tk.Event) -> None:
        if not self._select_mode:
            self._drag_page(event)
            return
        if self.page_rgb is None or self._select_start is None:
            return
        cx, cy = self._para_canvas(*self._point(event))
        cx0, cy0 = self._para_canvas(*self._select_start)
        if self._select_rect_id is None:
            self._select_rect_id = self.canvas.create_rectangle(
                cx0, cy0, cx, cy, outline=tokens.RESERVA[tokens.TRACEJADO], width=2, dash=(6, 4)
            )
        else:
            self.canvas.coords(self._select_rect_id, cx0, cy0, cx, cy)

    def _drag_page(self, event: tk.Event) -> None:
        """A mão do leitor: arrastar com o botão esquerdo desloca a página.

        Só começa depois da folga do clique, e é isso que faz o mesmo botão servir para as duas
        coisas -- abrir o diagrama de baixo (S-68) e puxar a página. Sem a folga, quem arrasta
        abriria um diagrama ao soltar; sem o arrasto, a única forma de andar na página ampliada
        seria a barra de rolagem.
        """
        if self.page_rgb is None or self._press_at is None:
            return
        if not self._panning:
            andou = abs(self.canvas.canvasx(event.x) - self._press_at[0]) > CLICK_SLOP_PX or abs(
                self.canvas.canvasy(event.y) - self._press_at[1]
            ) > CLICK_SLOP_PX
            if not andou:
                return
            self._panning = True
            self.canvas.configure(cursor="fleur")
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_release(self, event: tk.Event) -> None:
        if self._panning:
            # Terminou um arrasto: a folga já garantiu que isto não era um clique.
            self._on_pan_end(event)
            self._press_at = None
            return
        if not self._select_mode:
            self._release_on_box(event)
            return
        if self.page_rgb is None or self._select_start is None:
            return

        x1, y1 = self._point(event)
        x0, y0 = self._select_start
        self.disable_area_selection()

        x0c, x1c = sorted((x0, x1))
        y0c, y1c = sorted((y0, y1))

        # Da coordenada do canvas para a do pixel da página -- a única parte que depende do
        # zoom. Recortar e grampear aos limites e do servico (S-31).
        zoom = float(self.zoom_var.get())
        regiao = (int(x0c / zoom), int(y0c / zoom), int(x1c / zoom), int(y1c / zoom))
        # **Depois da conversão, e por isso (S-330):** o piso fala de casa de tabuleiro, que é
        # medida da folha; medi-lo antes fazia o mínimo variar oito vezes entre 25% e 200%.
        if (regiao[2] - regiao[0]) < MIN_SELECTION_PX or (regiao[3] - regiao[1]) < MIN_SELECTION_PX:
            self._on_status("Seleção muito pequena. Tente novamente.")
            return
        self._on_region(np.asarray(self.page_rgb).copy(), regiao)

    def _release_on_box(self, event: tk.Event) -> None:
        """Soltar o botão fora do modo de seleção: se foi clique, e acertou, avisa a janela.

        A distinção entre clique e arrasto é o que deixa a rolagem por arraste conviver com os
        diagramas marcados -- sem ela, todo empurrão na página abriria o diagrama de baixo.
        """
        if self._press_at is None:
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        x0, y0 = self._press_at
        self._press_at = None
        if abs(x - x0) > CLICK_SLOP_PX or abs(y - y0) > CLICK_SLOP_PX:
            return

        indice = self._box_at_event(event)
        if indice is not None:
            self._on_box_click(indice)
