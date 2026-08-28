"""A sala de estudo: um estudo por diagrama do livro, com lista de lances e anotação.

A aba se chamava **Análise** e era um tabuleiro: carregava uma posição de cada vez e não devia nada
a ninguém. Desde as Fases 43 a 45 ela é uma **sala** -- um lugar onde se fica, de onde se sai e para
onde se volta, e o que ficou sobre a mesa continua lá.

**O que mudou, e a ordem em que importa.**

1. **O estudo virou dado** (S-268). A árvore, a âncora no livro e a anotação moram em `estudo.py`,
   que não importa `tkinter`. Este arquivo desenha.
2. **Trocar de diagrama parou de apagar análise** (S-270). Antes, `sync_with_ocr` chamava
   `_set_board_state`, que fazia `self.game = self._new_game(board)`: a árvore inteira no lixo, sem
   pergunta e sem desfazer -- e `follow_ocr_var` nasce em `True`, então essa era a configuração
   *padrão*. Agora há uma `Sala`, e trocar de diagrama é ir para a outra mesa.
3. **O estudo abre com a vez certa** (S-269). O painel recebia `current_fen`, que não era uma FEN:
   era o campo de peças. Todo estudo abria com as brancas a jogar e sem direito a roque, mesmo
   quando a S-17 tinha lido "pretas jogam" na legenda. Agora ele recebe uma `PosicaoDeEstudo`.
4. **A lista de lances virou a navegação** (S-273/S-274). Era um `StringExporter` despejado num
   `tk.Text` de cinco linhas com `state=DISABLED`. Quem decide o que ela mostra é
   `ui/estudo_lista.py`, e o que ele produz é conferido contra o `StringExporter` -- a numeração de
   variante é a parte que todo visualizador de PGN erra.
5. **A anotação existe** (S-277/S-278/S-279): comentário, símbolo e seta, os três no nó, os três em
   PGN que o ChessBase e o Lichess leem.

**O vínculo com o OCR continua de mão única, e continua de propósito.** O painel *lê* a posição do
diagrama selecionado e nunca escreve de volta: analisar uma posição não é corrigi-la, e propagar um
lance jogado aqui sobrescreveria o que a pessoa está tentando conferir.

**O nome do arquivo continua `study_panel.py`.** Nome de arquivo não é interface, e renomeá-lo
custaria diff em `app_tkinter.py` e em seis testes sem mudar nada para quem usa o programa.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Protocol

import chess
import chess.engine
import chess.pgn

from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr import estudo_arquivo
from chess_diagram_ocr.engine import EngineAnalyzer, Evaluation
from chess_diagram_ocr.estudo import Ancora, Caminho, Estudo, PosicaoDeEstudo, Sala
from chess_diagram_ocr.fen_utils import is_valid_fen, reading_index_from_square, square_from_reading_index

from . import comandos, estudo_lista, geometria, shortcuts, texto, theme, tipografia, tokens
from .board_widget import InteractiveBoard, PieceImages
from .historico import Historico
from .tooltip import Tooltip

logger = logging.getLogger(__name__)

__all__ = ["StudyPanel"]

RECUO_POR_NIVEL = 18
"""Pixels de recuo por nível de variante na lista. O recuo satura em
`estudo_lista.NIVEL_MAXIMO_DE_RECUO`; a numeração, nunca."""

COMANDOS_DA_ABA: dict[str, str] = {
    "estudo_do_diagrama": "load_from_recognized",
    "estudo_da_posicao_inicial": "load_initial_position",
    "virar_tabuleiro": "flip_board",
    "trocar_vez": "toggle_turn",
    "estudo_aplicar_fen": "apply_fen",
    "copiar_fen": "copy_fen",
    "salvar_estudo": "save_pgn",
    "lance_anterior": "undo_move",
    "proximo_lance": "redo_move",
    "inicio_da_linha": "go_to_start_of_line",
    "fim_da_linha": "go_to_end_of_line",
    "promover_variante": "promover_variante",
    "promover_a_principal": "promover_a_principal",
    "rebaixar_variante": "rebaixar_variante",
    "apagar_variante": "apagar_variante",
    "apagar_continuacao": "apagar_continuacao",
    "simbolo_do_lance": "escolher_simbolo",
    "mostrar_diagrama": "alternar_recorte",
    "linha_do_livro": "jogar_a_linha_do_livro",
    "ir_para_a_pagina": "ir_para_a_pagina",
    "analisar_posicao": "analyse",
    "analise_continua": "alternar_analise_continua",
    "variante_do_motor": "variante_do_motor",
    "partidas_da_posicao": "partidas_da_posicao",
    "colar_estudo": "colar_estudo",
    "abrir_pgn": "abrir_pgn",
    "exportar_estudo_md": "exportar_estudo_md",
    "exportar_estudo_html": "exportar_estudo_html",
    "exportar_estudo_rtf": "exportar_estudo_rtf",
    "estudo_para_o_texto": "levar_para_o_texto",
    "modo_treino": "alternar_treino",
}
"""Comando do catálogo -> método desta aba (S-280).

**A janela gera as ligações desta tabela**, como faz com `texto_panel.COMANDOS_DA_ABA` desde a
S-240: um comando novo da sala entra aqui, numa linha, e chega ao menu, à paleta e às três peles
sozinho. Escrever `lambda p: p.promover_variante()` no `app_tkinter` seria a segunda declaração do
par comando-método, e a primeira é esta -- que é onde os métodos estão.

O nome do comando e o do método divergem em nove casos, e todos por bom motivo: os quatro de
navegação são `undo_move`/`redo_move`/`go_to_*_of_line` porque era assim antes do catálogo, e
`estudo_do_diagrama` é `load_from_recognized` porque o que ele carrega é o que o OCR leu.

`comandos.acoes_fora_do_catalogo(COMANDOS_DA_ABA)` tem de ser vazio, e é o critério de aceite da
S-280."""

ACOES_PROPRIAS: frozenset[str] = frozenset(
    {"diagrama_anterior", "proximo_diagrama", "primeira_pagina", "ultima_pagina"}
)
"""As ações globais que esta aba atende **enquanto tem o foco** (S-244/S-281).

`←` é "diagrama anterior" em toda a janela e "lance anterior" aqui dentro; `Home` é "primeira página
do livro" e aqui é "início da linha". Não são teclas novas: é a mesma tecla com destino conforme o
foco, que é o que qualquer programa de xadrez faz.

**Isto substitui quatro `canvas.bind`.** A aba ligava `<Left>`, `<Right>`, `<Home>` e `<End>` no
canvas do tabuleiro, e as três consequências estão medidas na S-281: as teclas só funcionavam depois
de clicar no tabuleiro, não apareciam em lugar nenhum, e sombreavam as globais -- a docstring de
`shortcuts.owns_key` cita este arquivo pelo nome. O conserto de lá tornou a colisão inofensiva; este
é o conserto de não a ter."""

LADO_DO_RECORTE = 220
"""Lado máximo da miniatura do diagrama, em pixels (S-282).

Cerca de um terço do tabuleiro no arranjo padrão: grande o bastante para se conferir uma casa
duvidosa, pequeno o bastante para não disputar a coluna com o tabuleiro."""

LADO_AMPLIADO = 640
"""Lado máximo do recorte ampliado (S-282). Acima do que qualquer diagrama do acervo tem: os
recortes saem em ~400 px, e o teto existe só para o dia em que um livro traga uma prancha inteira."""

CANDIDATOS_DO_MOTOR = 3
"""Quantas linhas o motor devolve na análise contínua (S-286).

Três e não cinco: a quarta e a quinta de um motor a 800 ms já são ruído, e a pergunta de quem estuda
um livro quase nunca é qual é o melhor lance -- é se o lance que o livro dá está entre os
candidatos."""


TAMANHO_MAXIMO_DE_PGN = 20 * 1024 * 1024
"""O maior `.pgn` que o comando "Abrir PGN…" aceita, em bytes (S-307).

**Por que existe um teto.** `abrir_pgn` lia o arquivo inteiro para a memória na thread do Tk, e
`pgn_database/` -- a pasta que `estudo_partidas.py` manda usar -- tem arquivos de 8,6 GB e
10,3 GB. Medido: 5,2 MB de PGN custam 18,8 s e 220 MB de pico, o que dá ~3,5 min de janela
congelada num arquivo de 62 MB; nos de gigabytes o `read_text` levanta `MemoryError`, que **não**
é `OSError` e por isso escapava da guarda e subia para o laço de eventos.

Vinte megabytes é o corte entre "coleção de um livro" e "base de partidas". A base grande não
deixa de ser consultável: quem a consulta é a busca por posição da S-73, que indexa em vez de
carregar."""

PARTIDAS_MAXIMAS_DE_PGN = 5000
"""E um teto de partidas, para o arquivo pequeno com muita partida dentro.

O teto é **argumento** de `estudos_de_pgn`, e não constante lá dentro: o mesmo laço lê o arquivo
da sala, e um limite global truncaria em silêncio a sala de quem tem mais estudos que o teto --
perda de análise humana, o oposto do que este item quer."""


class StudyPanel(ttk.Frame):
    """Sala de estudo: um estudo por diagrama, com árvore de variantes e anotação."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        piece_images: PieceImages,
        posicao: Callable[[], PosicaoDeEstudo | None],
        initial_dir: Path,
        analyzer: EngineAnalyzer | None = None,
        pasta_de_estudos: Path | None = None,
        recorte: Callable[[Ancora], Any] = lambda _ancora: None,
        linha_impressa: Callable[[Ancora], str] = lambda _ancora: "",
        abrir_pagina: Callable[[Ancora], bool] = lambda _ancora: False,
        bases_de_partidas: Callable[[], Sequence[Path]] = tuple,
        para_o_texto: Callable[[str], bool] = lambda _linha: False,
    ) -> None:
        super().__init__(parent, padding=6)
        self._posicao = posicao
        """De onde vem a posição do diagrama selecionado -- **inteira**, com vez, número de lance e
        âncora no livro. Era `current_fen: Callable[[], str]`, e o que ela devolvia era só o campo
        de peças (S-269)."""

        self._initial_dir = initial_dir
        self._analyzer = analyzer
        """O motor, se houver um. `None` esconde a seção inteira em vez de deixá-la cinza (S-33)."""

        self._recorte = recorte
        """O recorte do diagrama âncora, como a aba Resultado o tem na memória (S-282)."""

        self._linha_impressa = linha_impressa
        """A notação que o livro imprimiu ao lado daquele diagrama, ou `""` (S-283)."""

        self._abrir_pagina = abrir_pagina
        """Leva o visualizador à página da âncora. Devolve se conseguiu (S-284)."""

        self._bases = bases_de_partidas
        """Os `.pgn` de `pgn_database/`. Vazio = não há base a quem perguntar (S-287)."""

        self._para_o_texto = para_o_texto
        """Insere a linha do estudo na aba de texto. `False` quando ela não pode receber (S-289)."""

        self._acertos = 0
        self._erros = 0

        self._pasta_de_estudos = pasta_de_estudos
        self._analysing = False
        self._geracao = 0
        """Cresce a cada mudança de nó. A resposta do motor que chegar com geração velha é
        descartada -- ver `analyse` (S-285)."""

        self._candidatos: list[Evaluation] = []
        self._loja: Any = None
        self._recorte_foto: Any = None
        self._recorte_de = ""
        self._alternaveis: dict[str, tuple[ttk.Button, tk.BooleanVar]] = {}
        self._gravacao_agendada: str | None = None
        self._sujo = False
        self._trechos: tuple[estudo_lista.Trecho, ...] = ()
        self._comentario_do_no: chess.pgn.GameNode | None = None

        self.sala = Sala()
        self.estudo = Estudo.de_posicao(PosicaoDeEstudo())
        self._historico = Historico(self.estudo.para_pgn())
        self._edicao = 0

        self.origin_var = tk.StringVar(value="Base: posição inicial")
        self.status_var = tk.StringVar(value="")
        self.fen_var = tk.StringVar(value=self.estudo.tabuleiro.fen())
        self.follow_ocr_var = tk.BooleanVar(value=True)
        self.flipped_var = tk.BooleanVar(value=False)
        self.recorte_var = tk.BooleanVar(value=False)
        self.continua_var = tk.BooleanVar(value=False)
        self.treino_var = tk.BooleanVar(value=False)
        self.placar_var = tk.StringVar(value="")
        self.engine_var = tk.StringVar(value="")
        self.engine_line_var = tk.StringVar(value="")

        self._build(piece_images)
        self.refresh()
        self.set_status("Clique em uma peça para estudar.")

    # ------------------------------------------------------------------------------ layout

    def _build(self, piece_images: PieceImages) -> None:
        self._build_barra()

        # **Duas colunas** (S-276): tabuleiro à esquerda, lances à direita. Era uma pilha vertical
        # com a lista em cinco linhas no fim -- e a lista é a superfície principal desde a Fase 44.
        # É a repartição que todo programa de xadrez usa, e pela mesma razão: lê-se a linha com o
        # olho ao lado do tabuleiro, e não abaixo dele.
        self.divisor = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.divisor.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        esquerda = ttk.Frame(self.divisor)
        direita = ttk.Frame(self.divisor)
        self.divisor.add(esquerda, weight=3)
        self.divisor.add(direita, weight=2)

        self.board_widget = InteractiveBoard(
            esquerda,
            mode="play",
            on_move=self.push_move,
            on_status=self.set_status,
            on_arrow=self.on_arrow,
            promotion_chooser=self.choose_promotion,
            piece_images=piece_images,
        )
        self.board_widget.pack(fill=tk.BOTH, expand=True, padx=(0, 4), pady=(0, 4))

        # A miniatura do diagrama (S-282). Ela nasce fora do `pack`: estudo sem âncora não mostra
        # espaço reservado para o que não existe -- ver `_desenhar_recorte`.
        self.recorte_label = ttk.Label(esquerda, cursor="hand2")
        self.recorte_label.bind("<Button-1>", lambda _evento: self.ampliar_recorte())

        ttk.Label(esquerda, textvariable=self.origin_var).pack(anchor="w")
        texto.acompanhar(ttk.Label(esquerda, textvariable=self.status_var)).pack(anchor="w", pady=(0, 4))
        campo = ttk.Entry(esquerda, textvariable=self.fen_var, font=theme.fonte_atual(tipografia.DADO))
        campo.pack(fill=tk.X)
        campo.bind("<Return>", lambda _event: self.apply_fen())

        self._build_lista(direita)
        self._build_anotacao(direita)
        self._build_engine_section(direita)

        # **O teclado vem junto com a aba** (S-281). `←` só chegava ao estudo depois de um clique no
        # tabuleiro, porque o canvas só ganhava foco no `_on_press` -- quem abria a aba e apertava a
        # seta trocava de diagrama. Dar o foco ao canvas ao mapear resolve isso sem tirar a seta de
        # dentro da caixa de comentário: ali quem responde é `acoes_proprias`, que devolve vazio.
        self.bind("<Map>", lambda _evento: self.board_widget.canvas.focus_set())

    def _botao(self, pai: tk.Misc, acao: str, **empacotar: object) -> ttk.Button:
        """Um botão da barra, **com o rótulo e a ênfase vindos do catálogo** (S-280).

        Nenhum `text=` escrito à mão sobra nesta aba, e é o critério de aceite do item: com três
        peles, o que não está no catálogo não aparece em nenhuma delas -- é a S-161 outra vez,
        *"o que não era botão não existia"*. O molde é o de `texto_panel._botao`.
        """
        botao = ttk.Button(
            pai,
            text=comandos.rotulo_de_botao(acao),
            style=comandos.estilo(acao),
            command=getattr(self, COMANDOS_DA_ABA[acao]),
        )
        botao.pack(**empacotar)  # type: ignore[arg-type]
        return botao

    def _alternavel(self, pai: tk.Misc, acao: str, variavel: tk.BooleanVar, **empacotar: object) -> ttk.Button:
        """Um botão que troca o próprio texto conforme o estado (S-222).

        **Botão e não `Checkbutton`**, e a razão é o alcance: um `Checkbutton` não é comando, e o
        estado dele viveria só na barra -- a mesma tecla pela paleta da S-231 ou pelo menu não teria
        onde ler o valor de antes. Com botão, `alternar_recorte` é uma função só, e as três portas
        chamam a mesma.

        O texto de ligado é `Comando.rotulo_alternado`, que existe desde a S-222 justamente porque a
        varredura da S-324 só olhava o `text=` do construtor e perdia o que era trocado depois.
        """
        botao = self._botao(pai, acao, **empacotar)
        self._alternaveis[acao] = (botao, variavel)
        self._pintar_alternavel(acao)
        return botao

    def _pintar_alternavel(self, acao: str) -> None:
        botao, variavel = self._alternaveis[acao]
        botao.configure(text=comandos.rotulo_alternado(acao) if variavel.get() else comandos.rotulo_de_botao(acao))

    def _build_barra(self) -> None:
        """Três linhas, e o corte entre elas é o assunto: a posição, a linha, e o que vem de fora."""
        posicao = ttk.Frame(self)
        posicao.pack(fill=tk.X, padx=4, pady=(0, 4))
        self._botao(posicao, "estudo_do_diagrama", side=tk.LEFT)
        for acao in ("estudo_da_posicao_inicial", "virar_tabuleiro", "trocar_vez", "estudo_aplicar_fen"):
            self._botao(posicao, acao, side=tk.LEFT, padx=(6, 0))
        for acao in ("copiar_fen", "salvar_estudo"):
            self._botao(posicao, acao, side=tk.LEFT, padx=(6, 0))
        ttk.Checkbutton(
            posicao,
            text="Seguir OCR selecionado",
            variable=self.follow_ocr_var,
            command=self.on_follow_ocr_toggle,
        ).pack(side=tk.RIGHT)

        linha = ttk.Frame(self)
        linha.pack(fill=tk.X, padx=4, pady=(0, 4))
        self._botao(linha, "inicio_da_linha", side=tk.LEFT)
        for acao in ("lance_anterior", "proximo_lance", "fim_da_linha"):
            self._botao(linha, acao, side=tk.LEFT, padx=(6, 0))
        # As cinco da S-275, no lugar do combobox "Continuações" e do botão "Entrar". Elas são as do
        # ChessBase e do Scid, e a ordem é a do gesto: sobe-se a variante até ela ser a linha, ou
        # apaga-se o que não valia.
        for acao in ("promover_variante", "promover_a_principal", "rebaixar_variante"):
            self._botao(linha, acao, side=tk.LEFT, padx=(12, 0) if acao == "promover_variante" else (6, 0))
        for acao in ("apagar_variante", "apagar_continuacao"):
            self._botao(linha, acao, side=tk.LEFT, padx=(6, 0))
        simbolo = self._botao(linha, "simbolo_do_lance", side=tk.LEFT, padx=(12, 0))
        Tooltip(
            simbolo,
            "O símbolo do lance. Escolher o mesmo de novo tira; escolher outro do mesmo grupo\n"
            "troca. Julgar o lance (!, ?) e julgar a posição (⩲, ±) são duas frases, e somam.",
        )
        self.simbolo_var = tk.StringVar(value="")
        texto.acompanhar(
            theme.pintar(ttk.Label(linha, textvariable=self.simbolo_var), "foreground", tokens.TEXTO_SECUNDARIO)
        ).pack(side=tk.LEFT, padx=(8, 0))

        de_fora = ttk.Frame(self)
        de_fora.pack(fill=tk.X, padx=4, pady=(0, 6))
        # Guardado num atributo com nome (S-347): é ele que fica cinza sem âncora, e a varredura
        # de `tests/test_ui_motivos.py` amarra o motivo ao **nome** do widget que se desabilita.
        self.btn_recorte = self._alternavel(de_fora, "mostrar_diagrama", self.recorte_var, side=tk.LEFT)
        Tooltip(
            self.btn_recorte,
            "O recorte que o modelo leu, ao lado do tabuleiro. Fica cinza quando o estudo não\n"
            "veio de um diagrama do livro -- uma FEN digitada à mão não tem recorte.",
        )
        self._botao(de_fora, "linha_do_livro", side=tk.LEFT, padx=(6, 0))
        Tooltip(
            de_fora.winfo_children()[-1],
            "Joga na árvore a linha impressa ao lado deste diagrama, e para no primeiro lance\n"
            "que a posição não sustenta -- dizendo qual foi. Exige a folha lida na aba Texto.",
        )
        self._botao(de_fora, "ir_para_a_pagina", side=tk.LEFT, padx=(6, 0))
        if self._analyzer is not None:
            self._botao(de_fora, "analisar_posicao", side=tk.LEFT, padx=(12, 0))
            self._alternavel(de_fora, "analise_continua", self.continua_var, side=tk.LEFT, padx=(6, 0))
            Tooltip(
                self._alternaveis["analise_continua"][0],
                "O motor acompanha o lance corrente e grava a avaliação nele, em [%eval].\n"
                "Navegar cancela a análise em curso: a resposta atrasada é descartada.",
            )
            self._botao(de_fora, "variante_do_motor", side=tk.LEFT, padx=(6, 0))
        self._botao(de_fora, "partidas_da_posicao", side=tk.LEFT, padx=(12, 0))

        entra_e_sai = ttk.Frame(self)
        entra_e_sai.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._botao(entra_e_sai, "colar_estudo", side=tk.LEFT)
        self._botao(entra_e_sai, "abrir_pgn", side=tk.LEFT, padx=(6, 0))
        for acao in ("exportar_estudo_md", "exportar_estudo_html", "exportar_estudo_rtf"):
            self._botao(entra_e_sai, acao, side=tk.LEFT, padx=(6, 0) if acao != "exportar_estudo_md" else (12, 0))
        self._botao(entra_e_sai, "estudo_para_o_texto", side=tk.LEFT, padx=(6, 0))
        self._alternavel(entra_e_sai, "modo_treino", self.treino_var, side=tk.LEFT, padx=(12, 0))
        Tooltip(
            self._alternaveis["modo_treino"][0],
            "A linha some e o tabuleiro cobra o lance. A árvore não muda: errar não cria\n"
            "variante -- para guardar o lance que você jogou, desligue o treino.",
        )
        texto.acompanhar(
            theme.pintar(ttk.Label(entra_e_sai, textvariable=self.placar_var), "foreground", tokens.TEXTO_SECUNDARIO)
        ).pack(side=tk.LEFT, padx=(8, 0))

    @staticmethod
    def _nags_oferecidos() -> tuple[int, ...]:
        return estudo_mod.NAGS_DE_LANCE + estudo_mod.NAGS_DE_POSICAO

    def _build_lista(self, parent: tk.Misc) -> None:
        caixa = ttk.LabelFrame(parent, text="Lances")
        caixa.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        self.moves_text = tk.Text(
            caixa,
            wrap="word",
            height=12,
            state=tk.DISABLED,
            cursor="arrow",
            font=theme.fonte_atual(tipografia.CORPO),
            padx=6,
            pady=4,
        )
        barra = ttk.Scrollbar(caixa, orient=tk.VERTICAL, command=self.moves_text.yview)
        self.moves_text.configure(yscrollcommand=barra.set)
        barra.pack(side=tk.RIGHT, fill=tk.Y)
        self.moves_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._configurar_tags()
        theme.ao_repintar(self._configurar_tags)

    def _build_anotacao(self, parent: tk.Misc) -> None:
        caixa = ttk.LabelFrame(parent, text="Comentário do lance")
        caixa.pack(fill=tk.X, pady=(0, 4))
        self.comentario_text = tk.Text(caixa, height=4, wrap="word", font=theme.fonte_atual(tipografia.CORPO))
        self.comentario_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        # Grava ao **sair** do campo e ao navegar, e não a cada tecla: um `<KeyRelease>` que
        # reescrevesse o nó a cada letra faria a lista de lances ser redesenhada trinta vezes por
        # frase, e o cursor pularia junto.
        self.comentario_text.bind("<FocusOut>", lambda _event: self.gravar_comentario())

    def _build_engine_section(self, parent: tk.Misc) -> None:
        """A seção do motor. Sem binário, ela simplesmente não existe (S-33)."""
        if self._analyzer is None:
            return

        caixa = ttk.LabelFrame(parent, text=f"Motor ({self._analyzer.path.name})")
        caixa.pack(fill=tk.X, pady=(0, 2))

        linha = ttk.Frame(caixa)
        linha.pack(fill=tk.X, padx=6, pady=(6, 0))
        self.btn_analyse = ttk.Button(linha, text="Analisar posição", command=self.analyse)
        self.btn_analyse.pack(side=tk.LEFT)
        Tooltip(
            self.btn_analyse,
            "Fica cinza enquanto o motor está pensando nesta posição, e volta quando\n"
            "ele responde. Sem motor UCI instalado, esta seção inteira não aparece.",
        )
        ttk.Label(linha, textvariable=self.engine_var).pack(side=tk.LEFT, padx=(10, 0))

        self.advantage = ttk.Progressbar(caixa, maximum=100.0, value=50.0)
        self.advantage.pack(fill=tk.X, padx=6, pady=(6, 0))
        texto.acompanhar(
            theme.pintar(
                ttk.Label(caixa, textvariable=self.engine_line_var), "foreground", tokens.TEXTO_SECUNDARIO
            )
        ).pack(anchor="w", padx=6, pady=(4, 6))

    # ------------------------------------------------------------------------- a lista

    def _configurar_tags(self) -> None:
        """As tags da lista, **derivadas do tema** e refeitas quando ele muda (regra 4).

        Cor e fonte saem de `ui/tokens.py` e `ui/tipografia.py`; nada de hexadecimal aqui.
        """
        widget = self.moves_text
        secundario = theme.cor_atual(tokens.TEXTO_SECUNDARIO)
        widget.configure(font=theme.fonte_atual(tipografia.CORPO))
        widget.tag_configure(estudo_lista.NUMERO, foreground=secundario)
        widget.tag_configure(estudo_lista.ABRE, foreground=secundario)
        widget.tag_configure(estudo_lista.FECHA, foreground=secundario)
        widget.tag_configure(estudo_lista.RESULTADO, foreground=secundario)
        widget.tag_configure(estudo_lista.RAIZ, foreground=secundario)
        widget.tag_configure(estudo_lista.NAG, font=theme.fonte_atual(tipografia.CORPO, negrito=True))
        widget.tag_configure(
            estudo_lista.COMENTARIO, foreground=secundario, font=theme.fonte_atual(tipografia.AUXILIAR)
        )
        # A linha principal em negrito e as variantes em peso normal: é a hierarquia sem gastar
        # matiz, que depois da S-158 é o recurso escasso do programa.
        widget.tag_configure("principal", font=theme.fonte_atual(tipografia.CORPO, negrito=True))
        for nivel in range(estudo_lista.NIVEL_MAXIMO_DE_RECUO + 1):
            recuo = nivel * RECUO_POR_NIVEL
            widget.tag_configure(f"nivel{nivel}", lmargin1=recuo, lmargin2=recuo + RECUO_POR_NIVEL)
        fundo = theme.cor_atual(tokens.SUPERFICIE_DICA)
        widget.tag_configure("corrente", background=fundo, foreground=tokens.sobre_superficie(fundo))

    def _redesenhar_lista(self) -> None:
        """Refaz a lista inteira e **remapeia as tags** (S-274).

        Índice de caractere do Tk não sobrevive a redesenho: é a mesma regra que a S-262 escreveu
        para a pilha do editor. Por isso o mapa de tags nasce junto com o texto, toda vez.
        """
        self._trechos = estudo_lista.trechos(self.estudo)
        corrente = self.estudo.caminho()
        if self.treino_var.get():
            # O corte do treino (S-290): o que vem depois do lance corrente some da tela e continua
            # na árvore. É o item inteiro -- "a linha some, e o tabuleiro cobra o lance".
            self._trechos = estudo_lista.ate(self._trechos, corrente)
        widget = self.moves_text
        # `self.moves_text` e não a variável local nas duas trocas de `state`: a varredura da S-165
        # (`tests/test_ui_motivos.py`) pergunta *qual widget* fica cinza, e um nome local esconderia
        # a resposta dela. O `DISABLED` aqui é o que impede digitar por cima da lista -- não é um
        # controle desligado, e é por isso que ele está declarado em `SEM_MOTIVO`.
        self.moves_text.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)

        for indice, trecho in enumerate(self._trechos):
            if not trecho.texto:
                continue
            # A variante começa e termina em linha própria: é o que dá o bloco recuado que se lê
            # como bloco. O `texto_de` não leva estas quebras -- elas são desenho, não PGN.
            if trecho.papel == estudo_lista.ABRE:
                widget.insert(tk.END, "\n")
            marcas = [trecho.papel, f"nivel{trecho.recuo}", f"t{indice}"]
            if trecho.papel == estudo_lista.LANCE and trecho.nivel == 0:
                marcas.append("principal")
            if trecho.caminho is not None and trecho.caminho == corrente and trecho.papel in (
                estudo_lista.LANCE,
                estudo_lista.RAIZ,
            ):
                marcas.append("corrente")
            widget.insert(tk.END, trecho.texto, tuple(marcas))
            if trecho.papel == estudo_lista.FECHA:
                widget.insert(tk.END, "\n")
            if trecho.caminho is not None:
                widget.tag_bind(f"t{indice}", "<Button-1>", partial(self._clique_na_lista, indice))
                widget.tag_bind(f"t{indice}", "<Enter>", lambda _e: widget.configure(cursor="hand2"))
                widget.tag_bind(f"t{indice}", "<Leave>", lambda _e: widget.configure(cursor="arrow"))

        self.moves_text.configure(state=tk.DISABLED)
        alcance = widget.tag_ranges("corrente")
        if alcance:
            widget.see(alcance[0])

    def _clique_na_lista(self, indice: int, _event: tk.Event) -> str:
        """Vai ao nó daquele trecho. O caminho é resolvido **agora**, e não guardado na tag.

        Promover ou apagar variante muda os índices de variação: um caminho guardado na montagem
        apontaria para o lance que ocupou o lugar do antigo (S-268).
        """
        if not 0 <= indice < len(self._trechos):
            return "break"
        caminho = self._trechos[indice].caminho
        if caminho is None:
            return "break"
        self.gravar_comentario()
        if not self.estudo.ir_para(caminho):
            self.set_status("Aquele lance não existe mais.")
        self.refresh()
        return "break"

    # ------------------------------------------------------------------------------ motor

    @property
    def has_engine(self) -> bool:
        return self._analyzer is not None

    def analyse(self) -> None:
        """Avalia a posição corrente numa thread, para a interface não travar (S-33/S-285).

        **Cada análise carrega a geração em que nasceu.** `_geracao` cresce a cada mudança de nó, e a
        resposta que chega com geração velha é descartada -- porque a thread guardava a posição e o
        `after(0, ...)` não a conferia, então trocar de diagrama durante uma análise escrevia a
        avaliação da posição anterior sobre a nova. Com a sala isso passou a ser um clique.
        """
        if self._analyzer is None:
            self.set_status("Sem motor UCI instalado: ponha o Stockfish em engines/ e reabra.")
            return
        if self._analysing:
            return

        self._analysing = True
        self.btn_analyse.configure(state=tk.DISABLED)
        self.engine_var.set("Analisando...")
        posicao = self.estudo.tabuleiro.copy(stack=False)
        no = self.estudo.no
        threading.Thread(
            target=self._analyse_worker, args=(self._geracao, posicao, no), daemon=True
        ).start()

    def _analyse_worker(self, geracao: int, board: chess.Board, no: chess.pgn.GameNode) -> None:
        assert self._analyzer is not None
        try:
            avaliacoes = self._analyzer.analyse_multi(board, count=CANDIDATOS_DO_MOTOR)
            self.after(0, partial(self._show_evaluation, geracao, no, avaliacoes))
        except Exception as exc:
            logger.warning("Falha na análise: %s", exc)
            self.after(0, partial(self._show_engine_error, geracao, str(exc)))
        finally:
            self.after(0, partial(self._finish_analysis, geracao))

    def _show_evaluation(self, geracao: int, no: chess.pgn.GameNode, avaliacoes: list[Evaluation]) -> None:
        """Só escreve se ainda estamos no mesmo lance -- ver `analyse`."""
        if geracao != self._geracao or not avaliacoes:
            return
        self._candidatos = list(avaliacoes)
        melhor = avaliacoes[0]
        self.engine_var.set(melhor.summary())
        self.advantage.configure(value=melhor.advantage_fraction() * 100.0)
        linhas = [
            f"{indice}. {avaliacao.display()}  {' '.join(avaliacao.pv_san)}"
            for indice, avaliacao in enumerate(avaliacoes, start=1)
            if avaliacao.pv_san
        ]
        self.engine_line_var.set("\n".join(linhas) or "Sem lance legal nesta posição.")
        self._gravar_avaliacao(no, melhor)

    def _gravar_avaliacao(self, no: chess.pgn.GameNode, avaliacao: Evaluation) -> None:
        """`[%eval 0.35,18]` no lance, que é onde o Lichess e o ChessBase o leem (S-285).

        **Fora da pilha de desfazer, e de propósito.** A avaliação não é edição de quem estuda: pô-la
        no histórico faria `Ctrl+Z` desfazer um número que o motor escreveu sozinho, e a pilha de
        quem analisou dez lances seria dez passos de nada. Por isso `_marcar_sujo(historico=False)`.

        Pela mesma razão ela **não conta para `Estudo.vazio()`**: navegar com o motor ligado não pode
        criar estudos na sala.
        """
        if avaliacao.score_cp is None and avaliacao.mate_in is None:
            return
        pontuacao = (
            chess.engine.Mate(avaliacao.mate_in)
            if avaliacao.mate_in is not None
            else chess.engine.Cp(int(avaliacao.score_cp or 0))
        )
        no.set_eval(chess.engine.PovScore(pontuacao, chess.WHITE), avaliacao.depth or None)
        self._marcar_sujo(historico=False, da_maquina=True)

    def _show_engine_error(self, geracao: int, mensagem: str) -> None:
        if geracao != self._geracao:
            return
        self.engine_var.set("O motor não respondeu.")
        self.engine_line_var.set(mensagem)

    def _finish_analysis(self, _geracao: int) -> None:
        self._analysing = False
        try:
            self.btn_analyse.configure(state=tk.NORMAL)
        except tk.TclError:  # pragma: no cover - painel destruído durante a análise
            return
        # A posição pode ter mudado enquanto o motor pensava: com a análise contínua ligada, é aqui
        # que a próxima começa. Sem isto, navegar durante uma análise deixaria o motor parado.
        self._analisar_se_continuo()

    # ------------------------------------------------------------------------------ estado

    def set_status(self, text: str = "") -> None:
        turno = "brancas" if self.estudo.tabuleiro.turn else "pretas"
        self.status_var.set(f"{text} | vez: {turno}" if text else f"Vez: {turno}")

    def refresh(self) -> None:
        """Põe na tela o que o estudo diz: posição, setas, lista, comentário e FEN."""
        tabuleiro = self.estudo.tabuleiro
        self.fen_var.set(tabuleiro.fen())
        self.board_widget.set_position(tabuleiro.fen())
        self.board_widget.set_last_move(getattr(self.estudo.no, "move", None))
        self.board_widget.set_flipped(self.estudo.invertido)
        self.flipped_var.set(self.estudo.invertido)
        self._mostrar_setas()
        self._redesenhar_lista()
        self._mostrar_comentario()
        self._mostrar_nag()
        self._desenhar_recorte()
        self._atualizar_botao_do_recorte()
        self._mostrar_placar()
        # A geração muda **aqui**, e não em cada método de navegação: `refresh` é o único ponto por
        # onde toda mudança de nó passa, e é isso que faz a resposta atrasada do motor ser sempre
        # descartada -- inclusive a de um caminho de navegação que ainda não existe (S-285).
        self._geracao += 1
        self._candidatos = []
        self._analisar_se_continuo()

    def _marcar_sujo(self, *, historico: bool = True, da_maquina: bool = False) -> None:
        """A árvore mudou: a pilha registra, a sala guarda, e o disco recebe depois (S-271/S-275).

        `historico=False` é para o que **não é edição desfazível** -- a avaliação que o motor
        escreve (S-285) e a orientação do tabuleiro (S-346). Pôr qualquer um deles na pilha faria
        `Ctrl+Z` desfazer uma coisa que ninguém fez.

        `da_maquina=True` é mais estreito, e separa **quem** mexeu: só o motor. A inatividade que
        decide a gravação é a do humano, e uma escrita automática a cada 800 ms adiava para sempre
        a gravação de tudo (S-345). Virar o tabuleiro é gesto de gente: não entra na pilha e
        **empurra** o relógio como qualquer outro.
        """
        self._sujo = True
        if historico:
            self._edicao += 1
            self._historico.registrar(self.estudo.para_pgn())
        self.sala.guardar(self.estudo)
        self._agendar_gravacao(adiar=not da_maquina)

    # ------------------------------------------------------------------ desfazer (S-275)

    def contem(self, widget: object) -> bool:
        """Este widget está dentro da sala? É o que decide de quem é o `Ctrl+Z` (S-243)."""
        atual = widget
        while atual is not None:
            if atual is self:
                return True
            atual = getattr(atual, "master", None)
        return False

    @property
    def edicao(self) -> int:
        """Contador que só cresce, como manda `ui/desfazivel.Desfazivel`. Zero = nunca editado."""
        return self._edicao

    def desfazer(self) -> None:
        self._aplicar_pgn(self._historico.desfazer(), "Não há nada para desfazer no estudo.")

    def refazer(self) -> None:
        self._aplicar_pgn(self._historico.refazer(), "Não há nada para refazer no estudo.")

    def _aplicar_pgn(self, pgn: str | None, vazio: str) -> None:
        """Recarrega o estudo daquele PGN, e volta ao lance em que se estava.

        **A pilha guarda o PGN do estudo, e não operações inversas.** O estudo inteiro cabe em
        alguns kilobytes de texto, gravar antes de cada mudança é uma linha, e desfazer é recarregar
        -- enquanto escrever o inverso de `promote_to_main` seria refazer, com bugs, o que a
        serialização já dá de graça. É a mesma decisão que `ui/historico.py` tomou para o tabuleiro.

        O caminho é reaplicado **depois**, e pode não existir mais: desfazer um "apagar variante"
        devolve lances que o nó corrente não tinha, e refazê-lo os tira de novo. `ir_para` cai na
        raiz nesse caso, que é a única resposta que não aponta para o vazio.
        """
        if pgn is None:
            self.set_status(vazio)
            return
        caminho = self.estudo.caminho()
        novo = Estudo.de_pgn(pgn, documento=self.estudo.ancora.documento)
        if novo is None:  # pragma: no cover - PGN que este painel mesmo gerou
            return
        novo.ancora = self.estudo.ancora
        novo.invertido = self.estudo.invertido
        self.estudo = novo
        self.estudo.ir_para(caminho)
        self._sujo = True
        self._edicao += 1
        self.sala.guardar(self.estudo)
        self._agendar_gravacao()
        self.refresh()
        self.set_status("Estudo restaurado.")

    # ------------------------------------------------------------------ o divisor (S-276)

    @property
    def fracao_do_divisor(self) -> float:
        """Onde a alça está, como fração da largura. `0.0` quando ainda não há geometria medida."""
        try:
            return geometria.fracao_de_divisor(
                int(self.divisor.sashpos(0)), int(self.divisor.winfo_width())
            )
        except (tk.TclError, IndexError):  # pragma: no cover - antes do primeiro layout
            return 0.0

    def posicionar_divisor(self, fracao: float) -> None:
        """Põe a alça naquela fração. `0.0` deixa o peso do `PanedWindow` decidir.

        Chamado depois do primeiro layout, e não na montagem: o `PanedWindow` precisa de largura
        medida para posicionar a alça -- é a mesma razão pela qual `_set_initial_sashes` da janela
        roda 180 ms depois da abertura.
        """
        if fracao <= 0.0:
            return
        try:
            self.divisor.sashpos(0, int(max(1, self.divisor.winfo_width()) * fracao))
        except tk.TclError as erro:  # pragma: no cover - geometria ainda instável
            logger.debug("Divisor do estudo não posicionado: %s", erro)

    # --------------------------------------------------------------- vínculo com o OCR

    def sync_with_ocr(self, force: bool = False) -> None:
        """Traz o diagrama selecionado, se o usuário quiser esse acoplamento.

        Silenciosa quando não há posição válida: é chamada a cada edição de casa no painel de
        resultado, e um `messagebox` de "FEN inválida" no meio de uma correção seria pior que não
        sincronizar.
        """
        if not force and not self.follow_ocr_var.get():
            return
        posicao = self._posicao()
        if posicao is None or not posicao.valida():
            return
        self._abrir(posicao, origem="Base: OCR selecionado", status="Estudo do diagrama selecionado.")

    def on_follow_ocr_toggle(self) -> None:
        if self.follow_ocr_var.get():
            self.sync_with_ocr(force=True)
        else:
            self.set_status("Sincronismo com OCR desativado.")

    def load_from_recognized(self) -> None:
        posicao = self._posicao()
        if posicao is None or not posicao.valida():
            # Pré-condição no rodapé, e não em caixa de diálogo (S-164).
            self.set_status("Não há diagrama reconhecido para estudar.")
            return
        self._abrir(posicao, origem="Base: OCR selecionado", status="Estudo do diagrama selecionado.")

    # ------------------------------------------------------------------------- a sala

    def _abrir(self, posicao: PosicaoDeEstudo, *, origem: str, status: str) -> None:
        """Troca de mesa: guarda o que estava aberto e traz o estudo daquele diagrama (S-270)."""
        self.gravar_comentario()
        self.sala.guardar(self.estudo)
        if posicao.ancora.valida and self.sala.documento and posicao.ancora.documento != self.sala.documento:
            self.abrir_livro(posicao.ancora.documento)
        anterior = self.sala.em(posicao.ancora)
        self.estudo = self.sala.abrir(posicao)
        # A pilha é **do estudo**, e trocar de mesa a recomeça: um `Ctrl+Z` que atravessasse a
        # troca de diagrama desfaria um lance que não está na tela.
        self._historico.zerar(self.estudo.para_pgn())
        self.origin_var.set(origem)
        self.refresh()
        if anterior is not None:
            lances = anterior.contagem_de_lances()
            self.set_status(f"{status} {lances} lance(s) já analisados aqui.")
        else:
            self.set_status(status)

    def reabrir_por_chave(self, chave: str) -> bool:
        """Volta à mesa em que a sessão anterior parou. Devolve se achou (S-347).

        **`estudo_aberto` era gravado no `AppState` e nunca lido.** O campo existe desde a S-271
        com o docstring certo -- "voltar ao livro sem voltar ao diagrama devolveria a pessoa à
        porta da sala em vez de à mesa em que ela estava" --, e era exatamente isso que acontecia:
        a sala do livro voltava do disco e a mesa aberta era sempre a do último diagrama
        reconhecido, ou nenhuma.

        A chave é opaca (`sha1 do caminho_pNN_dNN`) e não se desmonta em âncora; quem sabe qual
        estudo ela nomeia é a própria sala, que tem todos eles carregados. Procurar aqui é o que
        evita um segundo formato de chave só para esta pergunta.

        Silencioso quando não acha: o livro pode ter sido varrido de novo, o diagrama pode ter
        mudado de número, e voltar à porta da sala é a degradação certa -- não é erro.
        """
        if not chave:
            return False
        alvo = next((estudo for estudo in self.sala.estudos() if estudo.ancora.chave() == chave), None)
        if alvo is None:
            return False
        self.gravar_comentario()
        self.sala.guardar(self.estudo)
        self.estudo = alvo
        self._historico.zerar(self.estudo.para_pgn())
        self.origin_var.set(f"Base: {alvo.ancora.rotulo()}")
        self.refresh()
        self.set_status(f"Estudo reaberto: {alvo.ancora.rotulo()} · {alvo.contagem_de_lances()} lance(s).")
        return True

    def abrir_livro(self, documento: str) -> None:
        """Carrega a sala daquele livro do disco. Chamado quando um PDF é aberto (S-271).

        **Não pergunta.** Aqui o arquivo *é* o estudo, e não uma cópia de segurança dele: não há
        releitura de onde a análise possa vir, então oferecer seria oferecer apagar o trabalho. É a
        diferença para o rascunho da S-255, e está escrita em `estudo_arquivo`.
        """
        self.salvar_agora()
        self.sala = estudo_arquivo.carregar(documento, pasta=self._pasta_de_estudos)
        if len(self.sala):
            self.set_status(f"{len(self.sala)} estudo(s) deste livro carregados.")

    @property
    def chave_do_estudo_aberto(self) -> str:
        """O que o `AppState` guarda para voltar à mesma mesa (S-271)."""
        return self.estudo.ancora.chave() if self.estudo.ancora.valida else ""

    def _agendar_gravacao(self, *, adiar: bool = True) -> None:
        """Grava depois da inatividade, e não por relógio -- é a régua da S-255.

        **`adiar=False` não empurra o relógio, e é o que faz a gravação acontecer (S-345).** Com a
        análise contínua ligada, o motor escreve `[%eval ...]` no lance a cada ~800 ms, e cada
        escrita passava por aqui cancelando e reagendando: o prazo de inatividade nunca vencia, e a
        sala **nunca era gravada** enquanto o motor estivesse ligado. Quem estuda com a análise
        contínua -- que é o modo em que ela existe para ser usada -- ficava com o disco parado no
        estado de antes de ligar o motor.

        A inatividade é do **humano**: o que a máquina escreve entra na sala e no arquivo da
        próxima gravação, e não adia a que já está marcada. Sem nenhuma marcada, ela marca uma --
        senão a avaliação de um estudo que ninguém mais tocar não chegaria ao disco.
        """
        if self._gravacao_agendada is not None:
            if not adiar:
                return
            try:
                self.after_cancel(self._gravacao_agendada)
            except tk.TclError:  # pragma: no cover - painel destruído entre o agendamento e agora
                pass
        atraso = int(estudo_arquivo.ESPERA_SEGUNDOS * 1000)
        self._gravacao_agendada = self.after(atraso, self.salvar_agora)

    def salvar_agora(self) -> Path | None:
        """Grava a sala. Chamada pela inatividade, ao trocar de livro e ao fechar a janela.

        **A primeira linha é `gravar_comentario`, e a ordem é o item (S-302).** O que está
        digitado na caixa de comentário só entra no nó quando ela perde o foco -- os onze
        chamadores de `gravar_comentario` são todos de navegação e exportação. Quem escreve uma
        nota e fecha o programa com o cursor ainda dentro dela perdia a nota: `salvar_agora` saía
        em `if not self._sujo` sem olhar a caixa, e `_on_close` chama exatamente esta função.
        Reproduzido no painel real -- comentário digitado, `salvar_agora()`, e o texto não estava
        nem no arquivo nem no nó.

        Depois do teste de `_sujo` não adiantaria: é `gravar_comentario` quem liga `_sujo`.
        """
        self._gravacao_agendada = None
        try:
            self.gravar_comentario()
        except tk.TclError:  # pragma: no cover - painel destruído entre o agendamento e agora
            pass
        if not self._sujo or not self.sala.documento:
            return None
        try:
            caminho = estudo_arquivo.gravar(self.sala, pasta=self._pasta_de_estudos)
        except OSError as erro:  # pragma: no cover - disco cheio ou pasta somente leitura
            logger.warning("Sala de estudo não pôde ser gravada: %s", erro)
            return None
        self._sujo = False
        return caminho

    def tem_trabalho_por_gravar(self) -> bool:
        """Para o aviso de fechamento -- é o `loses_work` do `BusyRegistry` aplicado à sala."""
        return self._sujo

    # ------------------------------------------------------------------------------- ações

    def load_initial_position(self) -> None:
        if not self._confirmar_abandono("recomeçar da posição inicial"):
            return
        self.follow_ocr_var.set(False)
        self.sala.guardar(self.estudo)
        self.estudo = Estudo.de_posicao(PosicaoDeEstudo())
        self.origin_var.set("Base: posição inicial")
        self.refresh()
        self.set_status("Tabuleiro reiniciado na posição inicial.")

    def apply_fen(self) -> None:
        fen = self.fen_var.get().strip()
        if not fen:
            self.set_status("Não há FEN para carregar no tabuleiro de estudo.")
            return
        if not is_valid_fen(fen):
            messagebox.showerror("FEN inválida", "A FEN informada para estudo é inválida.")
            return
        if not self._confirmar_abandono("aplicar outra FEN"):
            return
        self.follow_ocr_var.set(False)
        self.sala.guardar(self.estudo)
        self.estudo = Estudo.de_posicao(PosicaoDeEstudo(placement=fen))
        self.origin_var.set("Base: FEN manual")
        self.refresh()
        self.set_status("FEN aplicada no tabuleiro de estudo.")

    def _confirmar_abandono(self, o_que: str, *, sempre: bool = False) -> bool:
        """Pergunta antes de largar um estudo com análise dentro (regra 7 da spec).

        Estudo com âncora válida **em geral** não precisa de pergunta: ele fica guardado na sala e
        volta quando se clicar naquele diagrama de novo. Quem perde alguma coisa é o estudo
        **avulso** -- o de uma FEN digitada à mão --, que não pertence a livro nenhum e não tem para
        onde ir.

        `sempre=True` é para o caso em que nem a âncora salva: trocar o lado a jogar muda a **raiz**,
        e a árvore antiga deixa de fazer sentido sobre a posição nova. Ali o estudo é descartado de
        verdade, e por isso ali se pergunta mesmo estando ancorado.
        """
        if self.estudo.vazio() or (self.estudo.ancora.valida and not sempre):
            return True
        onde = (
            "e ele será descartado"
            if sempre
            else "e não está atado a um diagrama do livro, então ele não será guardado"
        )
        return bool(
            messagebox.askyesno(
                "Estudo em andamento",
                f"Este estudo tem {self.estudo.contagem_de_lances()} lance(s) {onde}."
                f"\n\nQuer mesmo {o_que}?",
                default=messagebox.NO,
            )
        )

    def copy_fen(self) -> None:
        janela = self.winfo_toplevel()
        janela.clipboard_clear()
        janela.clipboard_append(self.estudo.tabuleiro.fen())
        self.set_status("FEN do estudo copiada.")

    def flip_board(self) -> None:
        """Vira o tabuleiro. **Fora da pilha de desfazer** (S-346).

        A orientação é vista, e não árvore: `para_pgn` não muda com ela, então `registrar`
        devolvia `False` e nada entrava na pilha -- mas `_edicao` subia, e é `_edicao` que diz a
        `ui/desfazivel.py` **qual painel** recebe o `Ctrl+Z`. Virar o tabuleiro sequestrava a
        tecla: ela vinha para a sala e não desfazia nada, enquanto a edição real de quem estava
        no editor ao lado ficava lá, sem quem a desfizesse.

        Continua sujando a sala, porque `invertido` é gravado com o estudo -- e continua
        empurrando o prazo de gravação, porque é gesto de gente.
        """
        self.estudo.invertido = not self.estudo.invertido
        self.flipped_var.set(self.estudo.invertido)
        self.board_widget.set_flipped(self.estudo.invertido)
        self._marcar_sujo(historico=False)

    def toggle_turn(self) -> None:
        board = self.estudo.raiz.board()
        board.turn = not board.turn
        # `sempre=True`: trocar a vez muda a **raiz**, e a árvore antiga não vale sobre ela. É a
        # única ação da aba que descarta um estudo ancorado, e por isso é a única que pergunta
        # mesmo havendo âncora.
        if not self._confirmar_abandono("inverter o lado a jogar", sempre=True):
            return
        ancora = self.estudo.ancora
        self.sala.descartar(ancora)
        self.estudo = Estudo.de_posicao(
            PosicaoDeEstudo(
                placement=board.board_fen(),
                vez="b" if not board.turn else "w",
                roque=board.castling_xfen() if board.castling_rights else "-",
                lance=board.fullmove_number,
                ancora=ancora,
            )
        )
        self.origin_var.set("Base: lado a jogar ajustado")
        self.refresh()
        self.set_status("Lado a jogar invertido.")
        self._marcar_sujo()

    # -------------------------------------------------------------------------- navegação

    def undo_move(self) -> None:
        if self.estudo.no.parent is None:
            self.set_status("Não ha lances para desfazer.")
            return
        self.gravar_comentario()
        self.estudo.no = self.estudo.no.parent
        self.refresh()
        self.set_status("Lance anterior.")

    def redo_move(self) -> None:
        if not self.estudo.no.variations:
            self.set_status("Não ha lances para refazer.")
            return
        self.gravar_comentario()
        self.estudo.no = self.estudo.no.variations[0]
        self.refresh()
        self.set_status("Próximo lance.")

    def go_to_start_of_line(self) -> None:
        if self.estudo.no.parent is None:
            self.set_status("Já esta no inicio da linha.")
            return
        self.gravar_comentario()
        self.estudo.no = self.estudo.raiz
        self.refresh()
        self.set_status("Voltou para o inicio da linha.")

    def go_to_end_of_line(self) -> None:
        """Segue a **linha principal a partir daqui**, e é isso que "fim da linha" quer dizer.

        Antes, ele seguia a variante escolhida no combobox no primeiro passo e a principal daí em
        diante -- uma regra que o próprio comentário do código chamava de "leitura usual" e que
        ninguém conseguia prever.
        """
        if not self.estudo.no.variations:
            self.set_status("Já esta no fim da linha.")
            return
        self.gravar_comentario()
        no = self.estudo.no
        while no.variations:
            no = no.variations[0]
        self.estudo.no = no
        self.refresh()
        self.set_status("Avancou para o fim da linha.")

    def push_move(self, move: chess.Move) -> None:
        """Um lance jogado no tabuleiro. Igual ao que já estava, **segue**; diferente, ramifica.

        É o comportamento do ChessBase, e era o único acerto de peso que a aba já tinha.
        """
        if self.treino_var.get():
            self._treinar(move)
            return
        san = self.estudo.tabuleiro.san(move)
        self.gravar_comentario()
        existente = next((filho for filho in self.estudo.no.variations if filho.move == move), None)
        self.estudo.no = existente if existente is not None else self.estudo.no.add_variation(move)
        self.refresh()
        self._marcar_sujo()
        self.set_status(f"{san} | {'Variante seguida.' if existente is not None else 'Lance salvo.'}")

    def choose_promotion(self) -> int | None:
        janela = self.winfo_toplevel()
        escolha: dict[str, int | None] = {"piece_type": None}
        dlg = tk.Toplevel(janela)
        dlg.title("Promoção")
        dlg.resizable(False, False)
        dlg.transient(janela)
        dlg.grab_set()

        wrap = ttk.Frame(dlg, padding=12)
        wrap.pack(fill=tk.BOTH, expand=True)
        ttk.Label(wrap, text="Escolha a peça para promoção").pack(anchor="w", pady=(0, 8))

        def _select(piece_type: int) -> None:
            escolha["piece_type"] = piece_type
            dlg.destroy()

        for rotulo, tipo in (("Dama", chess.QUEEN), ("Torre", chess.ROOK), ("Bispo", chess.BISHOP), ("Cavalo", chess.KNIGHT)):
            # `partial` e não `lambda ...=tipo`: aqui ha laco, então a captura por valor e
            # obrigatoria -- e o `partial` a expressa sem enganar o verificador de tipos.
            ttk.Button(wrap, text=rotulo, command=partial(_select, tipo)).pack(fill=tk.X, pady=2)

        ttk.Button(wrap, text="Cancelar", command=dlg.destroy).pack(fill=tk.X, pady=(8, 0))
        janela.wait_window(dlg)
        return escolha["piece_type"]

    # -------------------------------------------------------------------------- variantes

    def promover_variante(self) -> None:
        self._operar_na_arvore("promote", "Variante promovida um nível.")

    def promover_a_principal(self) -> None:
        self._operar_na_arvore("promote_to_main", "Variante promovida a linha principal.")

    def rebaixar_variante(self) -> None:
        self._operar_na_arvore("demote", "Variante rebaixada.")

    def _operar_na_arvore(self, operacao: str, status: str) -> None:
        """Aplica a operação e **recalcula o caminho depois**.

        As quatro operações de `chess.pgn` são do **pai** e recebem o filho: `pai.promote(no)`, e não
        `no.promote()`. É a assinatura da biblioteca, e escrevê-la errado levanta em vez de fazer
        outra coisa -- o que aqui é sorte, e não desenho.

        Promover reordena as irmãs. Um caminho guardado antes da operação aponta para outro lance
        depois dela -- é a armadilha que `estudo.py` documenta, e é aqui que ela morde. Por isso o
        painel volta a apontar para **o nó**, e o caminho é derivado dele no redesenho.
        """
        no = self.estudo.no
        pai = no.parent
        if pai is None:
            self.set_status("A posição do diagrama não é uma variante.")
            return
        getattr(pai, operacao)(no)
        self.estudo.no = no
        self.refresh()
        self._marcar_sujo()
        self.set_status(status)

    def apagar_variante(self) -> None:
        """Apaga o lance corrente e tudo abaixo dele, e volta ao pai."""
        no = self.estudo.no
        pai = no.parent
        if pai is None:
            self.set_status("A posição do diagrama não pode ser apagada.")
            return
        if not self._confirmar_apagar(no):
            return
        pai.remove_variation(no)
        self.estudo.no = pai
        self.refresh()
        self._marcar_sujo()
        self.set_status("Variante apagada.")

    def apagar_continuacao(self) -> None:
        """Apaga só o que vem **depois** do lance corrente, e o mantém."""
        no = self.estudo.no
        if not no.variations:
            self.set_status("Não há continuação para apagar.")
            return
        if not self._confirmar_apagar(no, so_continuacao=True):
            return
        for filho in list(no.variations):
            no.remove_variation(filho)
        self.refresh()
        self._marcar_sujo()
        self.set_status("Continuação apagada.")

    def _confirmar_apagar(self, no: chess.pgn.GameNode, *, so_continuacao: bool = False) -> bool:
        """Pergunta só quando há o que perder (regra 7 da spec).

        Apagar um lance solto é o desfazer de um clique errado, e perguntar ali seria atrito. Apagar
        uma subárvore com comentário ou com mais de um lance é perder trabalho.
        """
        raiz: Sequence[chess.pgn.GameNode] = list(no.variations) if so_continuacao else [no]
        lances, anotado = _tamanho_da_subarvore(raiz)
        if lances <= 1 and not anotado:
            return True
        return bool(
            messagebox.askyesno(
                "Apagar",
                f"Isto apaga {lances} lance(s)" + (" e a anotação deles" if anotado else "") + ".\n\nApagar?",
                default=messagebox.NO,
            )
        )

    # ------------------------------------------------------------------------- anotação

    def _mostrar_comentario(self) -> None:
        self._comentario_do_no = self.estudo.no
        self.comentario_text.delete("1.0", tk.END)
        self.comentario_text.insert("1.0", estudo_mod.texto_do_comentario(self.estudo.no.comment or ""))

    def gravar_comentario(self) -> None:
        """Grava o que está na caixa **no nó em que ele foi escrito**, e não no nó corrente.

        A distinção é o item: navegar troca o nó corrente antes de a caixa perder o foco, e gravar no
        corrente poria o comentário de um lance em outro.
        """
        no = self._comentario_do_no
        if no is None:
            return
        novo = self.comentario_text.get("1.0", "end-1c").strip()
        if novo == estudo_mod.texto_do_comentario(no.comment or ""):
            return
        # `com_texto` e não `no.comment = novo`: a atribuição direta apagaria as setas e a avaliação
        # daquele lance, que moram dentro do mesmo campo (S-268).
        no.comment = estudo_mod.com_texto(no.comment or "", novo)
        self._marcar_sujo()

    def _mostrar_nag(self) -> None:
        """Os símbolos do lance corrente, ao lado do botão que os põe."""
        nags = sorted(self.estudo.no.nags)
        self.simbolo_var.set(" ".join(estudo_mod.simbolo_de_nag(codigo) for codigo in nags))

    def alternar_nag(self, codigo: int) -> None:
        """Liga, desliga ou troca o símbolo do lance corrente (S-278)."""
        no = self.estudo.no
        if no.parent is None:
            self.set_status("A posição do diagrama não recebe símbolo de lance.")
            return
        no.nags = estudo_mod.alternar_nag(set(no.nags), int(codigo))
        self.refresh()
        self._marcar_sujo()

    def _mostrar_setas(self) -> None:
        """As setas do lance corrente, convertidas para o índice de leitura do tabuleiro."""
        self.board_widget.set_arrows(
            [
                (reading_index_from_square(seta.tail), reading_index_from_square(seta.head), seta.color)
                for seta in estudo_mod.setas_de(self.estudo.no)
            ]
        )

    def on_arrow(self, origem: int, destino: int, cor: str) -> None:
        """O botão direito desenhou (ou apagou) uma seta no lance corrente (S-279)."""
        estudo_mod.trocar_seta(
            self.estudo.no,
            square_from_reading_index(origem),
            square_from_reading_index(destino),
            cor,
        )
        self._mostrar_setas()
        self._redesenhar_lista()
        self._marcar_sujo()

    # ------------------------------------------------------ o dono das ações (S-244/S-281)

    def acoes_proprias(self) -> frozenset[str]:
        """As ações globais que esta aba atende enquanto tem o foco. Ver `ACOES_PROPRIAS`.

        **Vazio enquanto o cursor está em qualquer campo de texto**, e isso é o item e não um
        detalhe: ali `←` é do texto, como a guarda de `ui/shortcuts.ignores_widget` garante desde
        a S-20 para todo campo. Sem esta pergunta, escrever um comentário moveria o estudo a cada
        seta.

        **Era `is self.comentario_text`, e a sala tem quatro campos (S-323):** o `Entry` de FEN e
        as duas `Text` da lista e da anotação também. Com o cursor no campo de FEN, a seta
        esquerda movia o cursor **e** desfazia um lance -- e quem estava conferindo uma FEN à mão
        perdia a posição da árvore sem nenhum sinal. `ignores_widget` já responde por `Entry`,
        `Text`, `Combobox` e `Spinbox` de uma vez, e é a régua que o resto da janela usa.
        """
        try:
            if shortcuts.ignores_widget(self.focus_get()):
                return frozenset()
        except (tk.TclError, KeyError):  # pragma: no cover - janela sem foco, ou destruída
            pass
        return ACOES_PROPRIAS

    def atender(self, acao: str) -> Callable[[], None] | None:
        """A função desta aba para aquela ação, ou `None` se ela não a atende."""
        return {
            "diagrama_anterior": self.undo_move,
            "proximo_diagrama": self.redo_move,
            "primeira_pagina": self.go_to_start_of_line,
            "ultima_pagina": self.go_to_end_of_line,
        }.get(acao)

    # ------------------------------------------------------------------ o símbolo (S-278)

    def escolher_simbolo(self) -> None:
        """O menu dos catorze símbolos, sobre o ponteiro. O molde é `texto_panel._menu_de_simbolos`.

        **Menu e não combobox**, e a troca é da S-280: um `Combobox` não é comando -- ele não tem
        como ser aberto pela paleta da S-231 nem pelo menu, e o que estava na barra era a única
        porta para o símbolo do lance.
        """
        if self.estudo.no.parent is None:
            self.set_status("A posição do diagrama não recebe símbolo de lance.")
            return
        atuais = set(self.estudo.no.nags)
        popup = tk.Menu(self, tearoff=False)
        for codigo in self._nags_oferecidos():
            marca = " ✓" if codigo in atuais else ""
            popup.add_command(
                label=f"{estudo_mod.simbolo_de_nag(codigo)}   {estudo_mod.NOME_DE_NAG[codigo]}{marca}",
                command=partial(self.alternar_nag, codigo),
            )
        try:
            popup.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            popup.grab_release()

    # --------------------------------------------------------- o recorte do diagrama (S-282)

    def alternar_recorte(self) -> None:
        """Liga e desliga a miniatura do diagrama. Uma função só para as três portas -- ver
        `_alternavel`.

        **Sem âncora não há o que mostrar, e o botão diz isso** (S-347). A dica dele promete "fica
        cinza quando o estudo não veio de um diagrama do livro" desde a S-282, e ele nunca ficava:
        num estudo de FEN digitada à mão o clique trocava o rótulo para "Esconder recorte" sem que
        nada tivesse aparecido, e o clique seguinte "escondia" o que não estava lá.
        """
        if not self.estudo.ancora.valida:
            self.set_status("Este estudo não veio de um diagrama do livro: não há recorte para mostrar.")
            self._atualizar_botao_do_recorte()
            return
        self.recorte_var.set(not self.recorte_var.get())
        self._pintar_alternavel("mostrar_diagrama")
        self._desenhar_recorte()

    def _atualizar_botao_do_recorte(self) -> None:
        """Cinza sem âncora, e com o rótulo do que de fato está na tela (S-347)."""
        tem_ancora = self.estudo.ancora.valida
        try:
            self.btn_recorte.configure(state=tk.NORMAL if tem_ancora else tk.DISABLED)
        except tk.TclError:  # pragma: no cover - painel sendo destruído
            return
        if not tem_ancora and self.recorte_var.get():
            # O estado ligado não sobrevive à mesa sem âncora: ele descreveria uma miniatura que
            # não existe, e é o rótulo dele que mentia.
            self.recorte_var.set(False)
        self._pintar_alternavel("mostrar_diagrama")

    def _desenhar_recorte(self) -> None:
        """A miniatura do diagrama âncora, ou nada.

        **Nada, e não um retângulo vazio**: estudo sem âncora não veio de diagrama nenhum, e um
        espaço reservado para o que não existe rouba largura do tabuleiro sem dizer por quê.

        A imagem é reconstruída só quando a **âncora** muda, e não a cada lance: navegar redesenha o
        tabuleiro dezenas de vezes por minuto, e reamostrar o recorte junto seria trabalho por nada.
        O `PhotoImage` fica no atributo porque *o Tk não segura a imagem* -- a mesma amarra que
        `texto_panel` documenta nas miniaturas dela.
        """
        chave = self.estudo.ancora.chave() if self.estudo.ancora.valida else ""
        if not self.recorte_var.get() or not chave:
            self.recorte_label.pack_forget()
            self._recorte_de = ""
            return

        if chave != self._recorte_de:
            imagem = self._recorte(self.estudo.ancora)
            self._recorte_foto = _miniatura(imagem, LADO_DO_RECORTE)
            self._recorte_de = chave
        if self._recorte_foto is None:
            self.recorte_label.pack_forget()
            return
        self.recorte_label.configure(image=self._recorte_foto)
        self.recorte_label.image = self._recorte_foto  # type: ignore[attr-defined]
        if not self.recorte_label.winfo_ismapped():
            self.recorte_label.pack(side=tk.TOP, pady=(0, 4))

    def ampliar_recorte(self) -> None:
        """O recorte no tamanho em que o modelo o leu, numa janela própria (S-282).

        A miniatura cabe na coluna e serve para conferir *que* diagrama é; conferir **uma casa**
        pede o recorte inteiro -- e ele é bem maior que os 220 px do lado da lista. Uma janela e não
        um zoom no lugar: a comparação que se está fazendo é com o tabuleiro ao lado, e trocar a
        miniatura por uma imagem grande empurraria o tabuleiro para fora.
        """
        imagem = self._recorte(self.estudo.ancora) if self.estudo.ancora.valida else None
        foto = _miniatura(imagem, LADO_AMPLIADO)
        if foto is None:
            self.set_status("Não há recorte deste diagrama para ampliar.")
            return
        janela = tk.Toplevel(self)
        janela.title(self.estudo.ancora.rotulo())
        janela.transient(self.winfo_toplevel())
        rotulo = ttk.Label(janela, image=foto)
        rotulo.image = foto  # type: ignore[attr-defined]
        rotulo.pack(padx=8, pady=8)
        ttk.Button(janela, text="Fechar", command=janela.destroy).pack(pady=(0, 8))

    # ------------------------------------------------------- a linha impressa (S-283/S-208)

    def jogar_a_linha_do_livro(self) -> None:
        """Põe na árvore a linha que o livro imprimiu ao lado deste diagrama.

        **É o cliente que faltava à metade não escrita da S-208.** `text/notacao.fatiar` já separava
        lance de prosa; `validar` responde se `♘d7` é possível *nesta* posição, e a posição é a raiz
        deste estudo. O contrato é o da S-15 -- propõe, marca, não reescreve calado --, então a linha
        para no primeiro lance que não fecha e a aba **diz qual foi**.

        A variante entra a partir do **nó corrente**, e não da raiz: quem aperta o botão depois de
        andar três lances quer a continuação dali. Lance que já existe na linha é seguido em vez de
        duplicado, pela mesma regra de `push_move`.
        """
        from ..text import notacao

        if not self.estudo.ancora.valida:
            self.set_status("Este estudo não veio de um diagrama do livro, então não há linha impressa.")
            return
        texto_impresso = self._linha_impressa(self.estudo.ancora).strip()
        if not texto_impresso:
            self.set_status(
                "Não há linha lida para este diagrama. Leia a folha na aba Texto e tente de novo."
            )
            return

        lida = notacao.validar(texto_impresso.split(), self.estudo.tabuleiro)
        if not lida.lances:
            self.set_status(f"Nada da linha impressa fechou: {lida.motivo or 'não há lance nela'}.")
            return

        no = self.estudo.no
        # **O primeiro nó da linha é guardado enquanto ele é criado, e não procurado depois
        # (S-312).** Era `no_em(jogo, caminho() + (0,))` -- "o primeiro filho do nó corrente" --,
        # e isso só é a linha do livro quando o nó corrente não tinha continuação nenhuma. Quem
        # já tinha jogado um lance a partir do diagrama recebia a marca "linha impressa no livro"
        # no **seu** lance, e a linha do livro entrava ao lado sem procedência: o PGN saía
        # `{ linha impressa no livro } 4. d4 ( 4. Ng5 d5 )`, atribuindo ao livro o que a pessoa
        # jogou. É o mesmo recurso que o laço abaixo já usa quinze linhas adiante.
        primeiro: chess.pgn.GameNode | None = None
        for lance in lida.lances:
            existente = next((filho for filho in no.variations if filho.move == lance.move), None)
            no = existente if existente is not None else no.add_variation(lance.move)
            primeiro = primeiro or no
        if primeiro is not None and not primeiro.starting_comment:
            # A procedência do que **não** foi jogado por quem estuda, dita no próprio PGN.
            primeiro.starting_comment = "linha impressa no livro"
        self.estudo.no = no
        self.refresh()
        self._marcar_sujo()
        if lida.fechou:
            self.set_status(f"{len(lida.lances)} lance(s) da linha impressa entraram na árvore.")
        else:
            self.set_status(
                f"{len(lida.lances)} lance(s) entraram; a linha parou em «{lida.token}» -- {lida.motivo}."
            )

    # ------------------------------------------------------------- voltar ao livro (S-284)

    def ir_para_a_pagina(self) -> None:
        """Abre o visualizador na página deste diagrama.

        Quem estuda uma posição quer reler o parágrafo, e o estudo sabe onde ele está desde a S-268.
        Livro que saiu do lugar diz isso no rodapé e não levanta -- é a regra da S-164.
        """
        if not self.estudo.ancora.valida:
            self.set_status("Este estudo não veio de um diagrama do livro.")
            return
        if not self._abrir_pagina(self.estudo.ancora):
            self.set_status(f"Não foi possível abrir {self.estudo.ancora.nome_do_livro} nesta página.")
            return
        self.set_status(f"Página {self.estudo.ancora.pagina + 1} do livro.")

    # ------------------------------------------------------------ o motor (S-285/S-286)

    def alternar_analise_continua(self) -> None:
        """Liga e desliga o motor acompanhando o lance corrente."""
        if self._analyzer is None:
            self.set_status("Sem motor UCI instalado: ponha o Stockfish em engines/ e reabra.")
            return
        self.continua_var.set(not self.continua_var.get())
        self._pintar_alternavel("analise_continua")
        if self.continua_var.get():
            self.analyse()
        else:
            self.engine_var.set("")
            self.engine_line_var.set("")

    def _analisar_se_continuo(self) -> None:
        if self.continua_var.get() and self._analyzer is not None and not self._analysing:
            self.analyse()

    def variante_do_motor(self) -> None:
        """Põe a linha principal do motor na árvore, a partir do lance corrente (S-286).

        **A procedência vai junto, no PGN.** O que a máquina sugeriu e o que a pessoa jogou não podem
        ficar indistinguíveis no arquivo -- é a regra 2 da SPEC_EDITOR aplicada a lance --, e a forma
        padrão de dizê-lo é o comentário de entrada da variante, que o ChessBase e o Lichess mostram.
        """
        if self._analyzer is None:
            self.set_status("Sem motor UCI instalado: ponha o Stockfish em engines/ e reabra.")
            return
        melhor = self._candidatos[0] if self._candidatos else None
        if melhor is None or not melhor.pv_san:
            self.set_status("O motor ainda não respondeu sobre esta posição.")
            return

        tabuleiro = self.estudo.tabuleiro
        no = self.estudo.no
        primeiro: chess.pgn.GameNode | None = None
        for san in melhor.pv_san:
            try:
                lance = tabuleiro.parse_san(san)
            except ValueError:  # pragma: no cover - a linha veio do motor sobre esta posição
                break
            existente = next((filho for filho in no.variations if filho.move == lance), None)
            no = existente if existente is not None else no.add_variation(lance)
            primeiro = primeiro or no
            tabuleiro.push(lance)
        if primeiro is None:
            self.set_status("O motor não deu lance jogável nesta posição.")
            return
        if not primeiro.starting_comment:
            primeiro.starting_comment = f"{self._analyzer.path.name}: {melhor.display()}"
        self.refresh()
        self._marcar_sujo()
        self.set_status(f"Linha do motor na árvore: {' '.join(melhor.pv_san)}")

    # ------------------------------------------------- as partidas da base (S-287)

    def partidas_da_posicao(self) -> None:
        """Que partidas da base do usuário chegam a esta posição.

        **Lê o cache, não a base**, e o motivo está em `estudo_partidas`: reproduzir os lances da
        base inteira custa ~104 min em dez processos, e o custo é da passada e não da posição. Quando
        a posição nunca foi perguntada, a resposta diz **isso** em vez de dizer "nenhuma partida" --
        que seria um número sobre uma pergunta que ninguém fez.

        O `import` mora aqui e não no topo pela mesma regra de `texto_panel.MOTORES`: `games_cache`
        alcança `games_db` e `pdf_text`, e a aba é construída na abertura da janela.
        """
        from .. import estudo_partidas

        resposta = estudo_partidas.consultar(
            self._loja_de_posicoes(), self.estudo.tabuleiro.board_fen(), bases=tuple(self._bases())
        )
        self.set_status(resposta.frase)
        if resposta.achou:
            _JanelaDePartidas(self, resposta)

    def _loja_de_posicoes(self):  # noqa: ANN202 - games_cache.PositionStore | None
        """O cache de posições, aberto uma vez e mantido. `None` quando não há base.

        `open_store` nunca levanta por causa do disco (é decisão dele), então o `None` daqui só
        significa uma coisa: não há PGN em `pgn_database/` para o cache falar a respeito.
        """
        if self._loja is not None:
            return self._loja
        bases = tuple(self._bases())
        if not bases:
            return None
        from .. import games_cache

        self._loja = games_cache.open_store(database=list(bases))
        return self._loja

    # ------------------------------------------------------------- entrada (S-288)

    def colar_estudo(self) -> None:
        """Abre a caixa de colar posição ou partida.

        **Uma caixa e não dois comandos**, e é a decisão do plugin de referência que se copia inteira
        (`ChessStringModal.ts`): quem tem uma FEN e quem tem um PGN faz o mesmo gesto -- copia de
        algum lugar e cola aqui --, e obrigá-los a escolher o comando certo antes é perguntar o que o
        próprio texto responde. Quem responde é `estudo.colar`.
        """
        _JanelaDeColar(self, self._aceitar_colado)

    def _aceitar_colado(self, texto: str) -> None:
        """O que veio da caixa. **Não descarta nada antes de saber que deu certo.**"""
        novo, motivo = estudo_mod.colar(texto)
        if novo is None:
            self.set_status(motivo)
            return
        if not self._confirmar_abandono("abrir o que foi colado"):
            return
        self.follow_ocr_var.set(False)
        self.sala.guardar(self.estudo)
        self._trocar_de_estudo(novo, "Base: colado")
        self.set_status(f"{novo.contagem_de_lances()} lance(s) colados.")

    def abrir_pgn(self) -> None:
        """Abre um `.pgn` do disco: um estudo, ou a coleção de um livro (S-288).

        **Três respostas para três arquivos**, e a diferença não é de tamanho:

        - o `.pgn` que este programa gravou traz `SourcePDF`, `Page` e `Diagram`, e as partidas dele
          entram **na sala** -- é o caminho de volta de quem editou a coleção no ChessBase;
        - um `.pgn` de uma partida qualquer abre como estudo avulso;
        - um `.pgn` de muitas partidas sem âncora abre uma lista para escolher, que é o que uma base
          de partidas é.
        """
        nome = filedialog.askopenfilename(
            parent=self,
            title="Abrir PGN",
            filetypes=[("PGN", "*.pgn"), ("Todos", "*.*")],
            initialdir=str(self._initial_dir),
        )
        if not nome:
            return
        caminho = Path(nome)
        try:
            tamanho = caminho.stat().st_size
        except OSError as erro:
            self.set_status(f"Não foi possível ler {caminho.name}: {erro}")
            return
        if tamanho > TAMANHO_MAXIMO_DE_PGN:
            self.set_status(
                f"{caminho.name} tem {tamanho / 1_048_576:.0f} MB, e a sala abre até "
                f"{TAMANHO_MAXIMO_DE_PGN // 1_048_576} MB. Base de partidas desse tamanho se "
                f"consulta pela busca por posição, que não carrega o arquivo inteiro."
            )
            return
        try:
            with caminho.open(encoding="utf-8", errors="replace") as fluxo:
                achados = estudo_arquivo.estudos_de_pgn(
                    fluxo,
                    documento=self.sala.documento,
                    onde=caminho.name,
                    limite=PARTIDAS_MAXIMAS_DE_PGN,
                )
        except OSError as erro:
            self.set_status(f"Não foi possível ler {caminho.name}: {erro}")
            return

        if not achados:
            self.set_status(f"{caminho.name} não tem nenhuma partida legível.")
            return
        if len(achados) >= PARTIDAS_MAXIMAS_DE_PGN:
            self.set_status(
                f"{caminho.name}: lidas as primeiras {PARTIDAS_MAXIMAS_DE_PGN} partidas; "
                f"o arquivo tem mais."
            )

        # Os que têm âncora deste livro entram na sala; `guardar` recusa os demais sozinho.
        anexados = [e for e in achados if self.sala.guardar(e)]
        if anexados:
            self._trocar_de_estudo(anexados[0], f"Base: {caminho.name}")
            self.set_status(f"{len(anexados)} estudo(s) de {caminho.name} entraram na sala deste livro.")
            self._marcar_sujo()
            return
        if len(achados) == 1:
            if not self._confirmar_abandono(f"abrir {caminho.name}"):
                return
            self._trocar_de_estudo(achados[0], f"Base: {caminho.name}")
            self.set_status(f"{achados[0].contagem_de_lances()} lance(s) de {caminho.name}.")
            return
        _JanelaDeColecao(self, caminho.name, achados, self._escolher_da_colecao)

    def _escolher_da_colecao(self, escolhido: Estudo) -> None:
        if not self._confirmar_abandono("abrir a partida escolhida"):
            return
        self._trocar_de_estudo(escolhido, "Base: PGN aberto")
        self.set_status(f"{escolhido.contagem_de_lances()} lance(s) da partida escolhida.")

    def _trocar_de_estudo(self, novo: Estudo, origem: str) -> None:
        """Põe outro estudo na mesa, recomeçando a pilha de desfazer nele.

        Um `Ctrl+Z` que atravessasse a troca desfaria um lance que não está na tela -- é a mesma
        regra que `_abrir` aplica ao trocar de diagrama.
        """
        self.gravar_comentario()
        self.estudo = novo
        self._historico.zerar(self.estudo.para_pgn())
        self.origin_var.set(origem)
        self.refresh()

    # -------------------------------------------------------------- saída (S-289)

    def exportar_estudo_md(self) -> None:
        """`.md` **porque ele diffa**: dois estudos da mesma posição comparam linha a linha."""
        self._exportar_estudo(".md")

    def exportar_estudo_html(self) -> None:
        """`.html` **porque ele abre**: é o formato para mandar a análise para alguém."""
        self._exportar_estudo(".html")

    def exportar_estudo_rtf(self) -> None:
        """`.rtf` porque o Word abre -- e sem dependência nova nenhuma (S-252)."""
        self._exportar_estudo(".rtf")

    def _exportar_estudo(self, extensao: str) -> None:
        """O estudo naquele formato, com o recorte do diagrama ao lado (S-289).

        **Quem decide o que cada formato faz é `text/exportacao.py`**, e não este painel: aquele
        módulo existe porque "quatro exportadores escritos separadamente dariam quatro respostas, e
        três estariam erradas em silêncio". Aqui só se converte o estudo em `DocumentoRico` e se
        escolhe o destino.

        **E este é o primeiro cliente de `recortes=`.** O parâmetro existe em `exportar` desde a
        S-250 e nunca teve quem o usasse -- a aba de texto exporta sem imagem. É o mesmo caso de
        `validar` na S-208: a peça estava pronta e faltava a pergunta.
        """
        from .. import estudo_saida
        from ..text import exportacao

        formato = exportacao.formato_de(extensao)
        destino = filedialog.asksaveasfilename(
            parent=self,
            title=f"Exportar o estudo para {formato.nome}",
            defaultextension=extensao,
            initialfile=f"{self._nome_sugerido()}{extensao}",
            filetypes=[(formato.nome, f"*{extensao}"), ("Todos", "*.*")],
        )
        if not destino:
            return

        self.gravar_comentario()
        caminho = Path(destino)
        try:
            recortes = self._gravar_recorte(caminho)
            relatorio = exportacao.exportar(estudo_saida.para_documento(self.estudo), formato, recortes=recortes)
            exportacao.escrever(caminho, relatorio)
        except OSError as erro:
            messagebox.showerror("Erro", f"Falha ao exportar o estudo:\n{erro}")
            return
        self.set_status(exportacao.texto_do_relatorio(caminho, relatorio, tamanho=caminho.stat().st_size))

    def _nome_sugerido(self) -> str:
        """`Secrets_p143_d2`, ou `estudo`. É o nome do arquivo que o diálogo oferece."""
        ancora = self.estudo.ancora
        if not ancora.valida:
            return "estudo"
        livro = Path(ancora.nome_do_livro).stem[:40] or "estudo"
        return f"{livro}_p{ancora.pagina + 1}_d{ancora.diagrama + 1}"

    def _gravar_recorte(self, destino: Path) -> dict[int, Path]:
        """Grava o recorte do diagrama ao lado do arquivo, e devolve o mapa que `exportar` quer.

        `diagramas/` ao lado do destino, porque é a pasta que os formatos escrevem no caminho da
        imagem (`Markdown.pasta_de_imagens`). Sem recorte devolve `{}`, e aí a marca `[Diagrama 1]`
        sai sozinha -- que é o que `Relatorio.sem_recorte` conta e o relatório diz.
        """
        from .. import estudo_saida

        imagem = self._recorte(self.estudo.ancora) if self.estudo.ancora.valida else None
        if imagem is None:
            return {}
        pasta = destino.parent / "diagramas"
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / f"{destino.stem}.png"
        try:
            from PIL import Image

            Image.fromarray(imagem).convert("RGB").save(arquivo)
        except Exception as erro:  # noqa: BLE001 - recorte de origem desconhecida
            logger.debug("Recorte não pôde ser gravado (%s): %s", arquivo, erro)
            return {}
        return {estudo_saida.BLOCO_DO_DIAGRAMA: arquivo}

    def levar_para_o_texto(self) -> None:
        """Manda a linha do estudo para a aba de texto, no cursor (S-289).

        **É o inverso exato da S-283.** Lá o parágrafo do livro vira variante; aqui a variante vira
        parágrafo -- e as duas pontas passam pelo mesmo `estudo_lista`, que é o que garante que a
        numeração seja a mesma nos dois sentidos.
        """
        from .. import estudo_saida

        linha = estudo_saida.notacao_do_estudo(self.estudo)
        if not linha:
            self.set_status("Não há lance no estudo para levar ao texto.")
            return
        if not self._para_o_texto(linha):
            self.set_status("A aba Texto não está pronta para receber a linha.")
            return
        self.set_status("Linha do estudo inserida na aba Texto.")

    # ----------------------------------------------------------- treinar (S-290)

    def alternar_treino(self) -> None:
        """Liga e desliga o modo de treino: a linha some, e o tabuleiro cobra o lance."""
        self.treino_var.set(not self.treino_var.get())
        self._pintar_alternavel("modo_treino")
        self._acertos = 0
        self._erros = 0
        self._mostrar_placar()
        self.refresh()
        if self.treino_var.get():
            self.set_status("Treino: jogue o lance da linha. O que vem depois está escondido.")
        else:
            self.set_status("Treino desligado.")

    def _mostrar_placar(self) -> None:
        if not self.treino_var.get():
            self.placar_var.set("")
            return
        self.placar_var.set(f"treino: {self._acertos} certo(s), {self._erros} errado(s)")

    def _treinar(self, move: chess.Move) -> None:
        """Um lance jogado com o treino ligado. **A árvore não muda** (S-290).

        O gabarito é o nó seguinte da linha, e ele já está lá: o estudo tem tudo de que o treino
        precisa, e é por isso que este item não guarda nada.

        **Errar não cria variante**, e o caminho de guardar o lance é declarado na própria frase:
        desligar o treino. Um "quer guardar?" a cada erro transformaria o exercício numa fila de
        caixas, e a resposta certa quase sempre é não.
        """
        esperado = self.estudo.no.variations[0] if self.estudo.no.variations else None
        if esperado is None:
            self.set_status("Fim da linha: não há lance a adivinhar aqui.")
            return
        jogado = self.estudo.tabuleiro.san(move)
        if move == esperado.move:
            self._acertos += 1
            self.estudo.no = esperado
            self.refresh()
            self.set_status(f"{jogado} — certo.")
            return
        self._erros += 1
        self._mostrar_placar()
        self.set_status(
            f"{jogado} não é o lance da linha. Desligue o treino para guardá-lo como variante."
        )

    # --------------------------------------------------------------------------------- PGN

    def pgn_payload(self) -> str:
        return self.estudo.para_pgn()

    def write_pgn(self, path: Path, append: bool) -> None:
        """Grava o estudo em PGN. **Sobrescrever é atômico** (S-346).

        O caminho de sobrescrita usava `write_text`, que trunca antes de escrever: interrompido no
        meio, ele deixa zero byte no lugar do PGN que estava lá -- e o que estava lá é análise
        salva de outro dia. A exportação desta mesma aba passa por `atomic_io` desde a S-254, e a
        gravação da sala também; era este o caminho de fora.

        **Acrescentar continua sendo um `append`**, e a diferença é o modo de falha: ele nunca
        trunca, então uma interrupção deixa o arquivo anterior inteiro com um jogo pela metade no
        fim -- ruim de ler, e nada perdido. Reescrever o arquivo inteiro para acrescentar um jogo
        trocaria esse risco pelo risco de perder tudo.
        """
        from ..atomic_io import atomic_write_text

        payload = self.pgn_payload()
        if append and path.exists() and path.stat().st_size > 0:
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n\n")
                handle.write(payload)
                handle.write("\n")
            return
        atomic_write_text(path, payload + "\n")

    def save_pgn(self) -> None:
        self.gravar_comentario()
        filename = filedialog.asksaveasfilename(
            title="Salvar estudo em PGN",
            defaultextension=".pgn",
            filetypes=[("PGN", "*.pgn"), ("Todos", "*.*")],
            initialdir=str(self._initial_dir),
        )
        if not filename:
            return

        path = Path(filename)
        append = False
        if path.exists():
            # Três respostas, não duas: acrescentar é o caso comum (um arquivo por livro),
            # e oferecer só "sobrescrever ou cancelar" faria perder análise já salva.
            resposta = messagebox.askyesnocancel(
                "PGN existente",
                "O arquivo já existe.\n\nSim: acrescentar esta análise ao final.\n"
                "Não: sobrescrever o arquivo.\nCancelar: abortar o salvamento.",
            )
            if resposta is None:
                return
            append = bool(resposta)

        try:
            self.write_pgn(path, append=append)
            self.set_status(f"Análise acrescentada em {path.name}." if append else f"PGN salvo em {path.name}.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar PGN:\n{exc}")


def _tamanho_da_subarvore(raizes: Sequence[chess.pgn.GameNode]) -> tuple[int, bool]:
    """Quantos lances há embaixo daqueles nós, e se algum deles tem anotação (S-347).

    **A conta era pela linha principal e a pergunta é sobre a subárvore.**
    `len(list(filho.mainline())) + 1` percorre só a continuação principal, e `filho.comment or
    filho.nags` olha só o primeiro nível: uma variante com três sublinhas anotadas anunciava "isto
    apaga 2 lance(s)" e apagava dezoito, com os comentários todos. A caixa existe para dizer o que
    se perde, e ela dizia menos do que se perdia -- que é pior que não perguntar, porque quem lê
    "2 lances" clica em Sim.

    Iterativa, e não recursiva: a árvore de um estudo longo passa de mil nós numa linha só, e a
    profundidade do Python é 1000.
    """
    lances = 0
    anotado = False
    pilha = list(raizes)
    while pilha:
        atual = pilha.pop()
        lances += 1
        anotado = anotado or bool(atual.comment or atual.starting_comment or atual.nags)
        pilha.extend(atual.variations)
    return lances, anotado


def _miniatura(imagem: Any, lado: int) -> Any:
    """O recorte do diagrama como `PhotoImage`, ou `None` quando não há o que desenhar (S-282).

    `Any` na assinatura porque a entrada é um `np.ndarray` RGB e a saída um `ImageTk.PhotoImage`, e
    tipar os dois obrigaria este módulo a importar numpy e PIL no topo por causa de uma anotação --
    o mesmo motivo pelo qual `board_render` guarda as imagens sem prometer o tipo delas.

    Falha para o lado do nada: um recorte estragado esconde a miniatura e deixa a aba inteira em pé,
    que é o contrato de degradação do projeto desde a S-53.
    """
    if imagem is None:
        return None
    try:
        from PIL import Image, ImageTk

        pil = Image.fromarray(imagem).convert("RGB")
        maior = max(pil.width, pil.height) or 1
        escala = min(1.0, lado / maior)
        if escala < 1.0:
            pil = pil.resize((max(1, int(pil.width * escala)), max(1, int(pil.height * escala))))
        return ImageTk.PhotoImage(pil)
    except Exception as erro:  # noqa: BLE001 - recorte de origem desconhecida
        logger.debug("Recorte do diagrama não pôde ser desenhado: %s", erro)
        return None


class _JanelaDeColar(tk.Toplevel):
    """A caixa de colar posição ou partida (S-288).

    O molde é o `ChessStringModal` do plugin de referência, e o que se copia dele é a **decisão**:
    um campo só para os dois, porque o gesto é o mesmo e o próprio texto diz o que é.

    `Toplevel` e não `messagebox`: um PGN tem muitas linhas, e a caixa do sistema só pergunta.
    """

    def __init__(self, pai: tk.Misc, ao_colar: Callable[[str], None]) -> None:
        super().__init__(pai)
        self.title("Colar posição ou partida")
        self.transient(pai.winfo_toplevel())
        self._ao_colar = ao_colar

        moldura = ttk.Frame(self, padding=12)
        moldura.pack(fill=tk.BOTH, expand=True)
        texto.acompanhar(
            ttk.Label(moldura, text="Cole uma FEN ou um PGN. O programa decide qual é pelo conteúdo.")
        ).pack(anchor="w", pady=(0, 8))

        self.caixa = tk.Text(moldura, width=64, height=12, wrap="word", font=theme.fonte_atual(tipografia.DADO))
        self.caixa.pack(fill=tk.BOTH, expand=True)
        self.caixa.focus_set()

        linha = ttk.Frame(moldura)
        linha.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(linha, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)
        # Sem ênfase, e é a regra 1 de `ui/estilos.py` levada a sério: **uma por painel**, e a da
        # sala já é `estudo_do_diagrama`. Uma caixa de duas respostas em que uma delas é a óbvia não
        # precisa de cor para dizer qual -- a posição já diz.
        ttk.Button(linha, text="Abrir", command=self.abrir).pack(side=tk.RIGHT, padx=(0, 6))

    def abrir(self) -> None:
        colado = self.caixa.get("1.0", "end-1c")
        self.destroy()
        self._ao_colar(colado)


class _JanelaDeColecao(tk.Toplevel):
    """As partidas de um `.pgn` aberto, para escolher uma (S-288).

    Só aparece quando o arquivo **não** é uma coleção deste livro: as que trazem `SourcePDF`, `Page`
    e `Diagram` entram na sala e não precisam de escolha nenhuma. Esta é a lista de uma base de
    partidas de fora, que é o que o ChessBase mostra ao abrir um arquivo.
    """

    def __init__(
        self, pai: tk.Misc, nome: str, estudos: Sequence[Estudo], ao_escolher: Callable[[Estudo], None]
    ) -> None:
        super().__init__(pai)
        self.title(nome)
        self.transient(pai.winfo_toplevel())
        self._estudos = list(estudos)
        self._ao_escolher = ao_escolher

        moldura = ttk.Frame(self, padding=12)
        moldura.pack(fill=tk.BOTH, expand=True)
        ttk.Label(moldura, text=f"{len(self._estudos)} partidas em {nome}").pack(anchor="w", pady=(0, 8))

        self.tabela = ttk.Treeview(moldura, columns=("lances",), show="tree headings", height=14)
        self.tabela.heading("#0", text="Partida")
        self.tabela.heading("lances", text="Lances")
        self.tabela.column("lances", width=70, anchor="center")
        for indice, item in enumerate(self._estudos):
            self.tabela.insert("", tk.END, iid=str(indice), text=_rotulo_de_partida(item), values=(item.contagem_de_lances(),))
        self.tabela.pack(fill=tk.BOTH, expand=True)
        self.tabela.bind("<Double-1>", lambda _evento: self.escolher())

        linha = ttk.Frame(moldura)
        linha.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(linha, text="Fechar", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(linha, text="Abrir", command=self.escolher).pack(side=tk.RIGHT, padx=(0, 6))

    def escolher(self) -> None:
        selecao = self.tabela.selection() or ("0",)
        indice = int(selecao[0])
        if not 0 <= indice < len(self._estudos):  # pragma: no cover - seleção fora da lista
            return
        escolhido = self._estudos[indice]
        self.destroy()
        self._ao_escolher(escolhido)

    def linhas(self) -> list[str]:
        """O que a lista mostra. É o que o teste percorre, como em `legenda.linhas`."""
        return [str(self.tabela.item(item, "text")) for item in self.tabela.get_children()]


def _rotulo_de_partida(estudo: Estudo) -> str:
    """`Capablanca x Alekhine, 1927` -- e o endereço no livro quando a partida é um estudo nosso."""
    if estudo.ancora.valida:
        return estudo.ancora.rotulo()
    cabecalhos = estudo.jogo.headers
    nomes = f"{cabecalhos.get('White', '?')} x {cabecalhos.get('Black', '?')}"
    ano = str(cabecalhos.get("Date", ""))[:4]
    return f"{nomes}, {ano}" if ano and ano != "????" else nomes


class _JanelaDePartidas(tk.Toplevel):
    """As partidas da base que chegam à posição do estudo (S-287).

    **Só mostra.** Escolher uma candidata é o que a `GamesDialog` da S-86 faz, e ela escreve na
    anotação do diagrama -- que é trabalho da Galeria, não da sala. Duas janelas que escrevem a mesma
    anotação seriam duas verdades sobre ela.

    E ela **diz quando a lista é menor que a contagem**: `CachedPosition` guarda até um teto de
    partidas por posição, e mostrar dez de duzentas sem avisar é o número enganoso que a S-135
    registra.
    """

    def __init__(self, pai: tk.Misc, resposta: Any) -> None:
        super().__init__(pai)
        self.title("Partidas desta posição")
        self.transient(pai.winfo_toplevel())

        moldura = ttk.Frame(self, padding=12)
        moldura.pack(fill=tk.BOTH, expand=True)
        ttk.Label(moldura, text=resposta.frase, font=theme.fonte_atual(tipografia.CORPO)).pack(
            anchor="w", pady=(0, 8)
        )

        tabela = ttk.Treeview(moldura, columns=("lance", "vez"), show="tree headings", height=12)
        tabela.heading("#0", text="Partida")
        tabela.heading("lance", text="Lance")
        tabela.heading("vez", text="Vez")
        tabela.column("lance", width=60, anchor="center")
        tabela.column("vez", width=70, anchor="center")
        for partida in resposta.partidas:
            tabela.insert(
                "",
                tk.END,
                text=partida.label,
                values=(partida.move_number, "brancas" if partida.side_to_move == "w" else "pretas"),
            )
        tabela.pack(fill=tk.BOTH, expand=True)

        ttk.Button(moldura, text="Fechar", command=self.destroy).pack(anchor="e", pady=(10, 0))

    def linhas(self) -> list[str]:
        """O que a tabela mostra. É o que o teste percorre, como em `legenda.linhas`."""
        tabela = next(
            filho
            for filho in self.winfo_children()[0].winfo_children()
            if isinstance(filho, ttk.Treeview)
        )
        return [str(tabela.item(item, "text")) for item in tabela.get_children()]


def posicao_de_estudo(
    placement: str,
    vez: str,
    *,
    documento: str = "",
    pagina: int = -1,
    diagrama: int = -1,
    lance: int | None = None,
    titulo: str = "",
) -> PosicaoDeEstudo | None:
    """Monta a posição que a janela entrega ao painel, ou `None` quando não há diagrama.

    Mora aqui, e não no `app_tkinter`, porque é uma decisão e não uma montagem de widget: qual é a
    posição do diagrama selecionado é justamente a pergunta que a S-269 corrigiu, e ela tem de ser
    afirmável sem abrir janela.
    """
    limpo = str(placement or "").strip()
    if not limpo:
        return None
    posicao = PosicaoDeEstudo(
        placement=limpo,
        vez="b" if str(vez).lower().startswith("b") else "w",
        lance=lance,
        ancora=Ancora(documento=documento, pagina=pagina, diagrama=diagrama, titulo=titulo),
    )
    return posicao if posicao.valida() else None


class _Variavel(Protocol):
    """O `tk.StringVar` visto de fora: só o que se lê dele. Existe para o falso do teste não
    precisar de um interpretador Tcl para responder uma pergunta que é de texto."""

    def get(self) -> str: ...


class PainelDeDiagrama(Protocol):
    """O mínimo que `posicao_do_painel` usa do `ResultPanel`. Existe para o teste ter um de mentira.

    É o mesmo desenho de `ui/desfazivel.Desfazivel` e de `ui/atalhos.DonoDeAcoes`: a decisão é
    afirmável com um objeto de quatro atributos, e não com meia janela aberta.
    """

    @property
    def fen_var(self) -> _Variavel: ...

    @property
    def side_edits(self) -> list[str]: ...

    @property
    def selected_index(self) -> int: ...

    @property
    def page_key(self) -> tuple[str, int] | None: ...

    @property
    def items(self) -> list[Any]: ...


def posicao_do_painel(
    painel: PainelDeDiagrama | None,
    numero_do_lance: Callable[[int, int], int | None] = lambda _pagina, _diagrama: None,
) -> PosicaoDeEstudo | None:
    """A posição do diagrama selecionado no painel de resultado, **inteira** (S-269).

    A janela entregava `lambda: result_panel.fen_var.get()`, e aquilo não é uma FEN: é o campo de
    peças que `fen_from_class_indices` devolve. O lado a jogar mora em `side_edits`, o número do
    lance na anotação da Galeria (S-67) e o endereço no livro em `page_key` -- e nada disso chegava
    ao estudo. Medido: **todo estudo abria com as brancas a jogar e sem direito a roque.**

    **A página vem do `page_key`, e não da página exibida**, pela mesma razão que
    `result_panel._move_number_target` já usa aquele par: o editor pode estar mostrando o diagrama
    de uma página que o visualizador já deixou para trás, e ancorar o estudo na página *exibida* o
    poria na mesa errada. Item da fila e amostra do dataset não têm par, e ali o estudo nasce
    avulso -- que é o que ele é.
    """
    if painel is None:
        return None
    indice = painel.selected_index
    chave = painel.page_key
    lados = painel.side_edits
    return posicao_de_estudo(
        str(painel.fen_var.get()),
        lados[indice] if 0 <= indice < len(lados) else "w",
        documento=chave[0] if chave is not None else "",
        pagina=chave[1] if chave is not None else -1,
        diagrama=indice if chave is not None else -1,
        lance=numero_do_lance(chave[1], indice) if chave is not None else None,
    )


def recorte_do_painel(painel: PainelDeDiagrama | None, ancora: Ancora) -> Any:
    """O recorte daquele diagrama, como a aba Resultado o tem na memória (S-282).

    `None` quando o editor está mostrando **outra** página: o recorte tem de ser o do diagrama que
    ancorou o estudo, e não o do que está selecionado agora -- mostrar o segundo seria pôr lado a
    lado duas posições diferentes dizendo que são a mesma, que é o defeito exato que a miniatura
    existe para impedir.

    Duck typing como em `posicao_do_painel`, e pelo mesmo motivo: o teste passa quatro atributos.
    """
    if painel is None or not ancora.valida:
        return None
    chave = painel.page_key
    if chave is None or chave[0] != ancora.documento or chave[1] != ancora.pagina:
        return None
    itens = painel.items
    if not 0 <= ancora.diagrama < len(itens):
        return None
    return getattr(itens[ancora.diagrama], "board_rgb", None)


def caminho_do_estudo(painel: StudyPanel) -> Caminho:
    """O caminho do nó corrente. Existe para o teste dizer onde a sala está sem tocar em widget."""
    return painel.estudo.caminho()
