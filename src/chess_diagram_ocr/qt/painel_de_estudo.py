"""A sala de estudo no segundo frontend: um estudo por diagrama, com árvore e anotação (S-503).

**Quase tudo o que a sala decide já é puro, e é por isso que este arquivo é o que é.**
`estudo.py` tem a árvore, a âncora no livro e a anotação; `estudo_arquivo.py` grava e lê a sala;
`ui/estudo_lista.py` decide o que a lista de lances mostra e é conferido contra o `StringExporter`;
`ui/historico.py` é a pilha de desfazer; `engine.py` fala com o motor; `estudo_saida.py` e
`text/exportacao.py` fazem os três formatos de saída. E desde a S-503 `ui/sala_declarada.py` tem a
tabela `comando -> método`, as seis medidas e a cor da seta.

**A tabela de comandos é a mesma dos dois lados, e isso não é conveniência.** Os métodos deste
painel se chamam `load_from_recognized`, `promover_variante`, `alternar_treino` -- exatamente os
nomes que `COMANDOS_DA_ABA` mapeia -- porque a tabela é uma só. Um painel de Qt que os batizasse
diferente exigiria uma segunda tabela, e a segunda tabela é o lugar onde um comando some sem
ninguém notar: ele continua no catálogo, continua no menu, e não faz nada.

---

**Quatro diferenças do Qt, e as quatro são de mecanismo.**

1. **A lista de lances é um `QTextBrowser` com âncoras**, e não um `tk.Text` com tags ligadas a
   eventos. O clique num lance chega por `anchorClicked` com o índice do trecho, e o índice é
   resolvido **na hora** -- promover ou apagar variante muda os índices de variação, e um caminho
   guardado na montagem apontaria para o lance que ocupou o lugar do antigo (S-268).
2. **A resposta do motor atravessa a thread por sinal.** A geração continua sendo a guarda: ela
   cresce em `refresh`, e a resposta que chegar com geração velha é descartada (S-285).
3. **A gravação por inatividade é um `QTimer` de disparo único**, e o `adiar=False` da S-345 vira
   "não reinicie o relógio": com a análise contínua ligada, o motor escreve a cada ~800 ms, e cada
   escrita reagendando fazia o prazo nunca vencer -- a sala **nunca** era gravada.
4. **O `QSplitter` guarda a fração por `sizes()`**, e não por `sashpos`.
"""

from __future__ import annotations

import html
import logging
import threading
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QShowEvent
from PyQt6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr import estudo_arquivo
from chess_diagram_ocr.engine import EngineAnalyzer, Evaluation
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo, Sala
from chess_diagram_ocr.fen_utils import is_valid_fen, reading_index_from_square, square_from_reading_index
from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabuleiro_de_jogo import TabuleiroDeJogo
from chess_diagram_ocr.ui import (
    comandos,
    espaco,
    estilos,
    estudo_dobra,
    estudo_lista,
    geometria,
    tipografia,
    tokens,
)
from chess_diagram_ocr.ui.historico import Historico
from chess_diagram_ocr.ui.sala_declarada import (
    ACOES_PROPRIAS,
    CANDIDATOS_DO_MOTOR,
    COMANDOS_DA_ABA,
    FRACAO_PADRAO_DO_TABULEIRO,
    LADO_AMPLIADO,
    LADO_DO_RECORTE,
    PAPEIS_COLADOS,
    PARTIDAS_MAXIMAS_DE_PGN,
    RECUO_POR_NIVEL,
    TAMANHO_MAXIMO_DE_PGN,
    Sincronia,
    decidir_sincronia,
    nags_oferecidos,
)

logger = logging.getLogger(__name__)

LADO_DO_ICONE_DA_SALA = 16
"""Lado do ícone nos botões desta aba, em pixel (S-520).

Menor que o da fita (20 a 32): ali o ícone **é** o botão, com o rótulo embaixo; aqui ele acompanha
um rótulo ao lado, numa barra que já tem 28 botões. Dezesseis é a altura da letra da interface na
base 9, que é o que faz o par ícone-texto parecer uma coisa só em vez de duas."""

__all__ = ["LADO_DO_ICONE_DA_SALA", "PainelDeEstudo"]


class PainelDeEstudo(QWidget):
    """Sala de estudo: um estudo por diagrama, com árvore de variantes e anotação."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status desta aba. Ela sempre carrega a vez a jogar junto."""

    _motor_respondeu = pyqtSignal(int, object, object)
    """Interno: `(geração, nó, avaliações)` vindo da thread do motor."""

    _motor_falhou = pyqtSignal(int, str)
    _motor_terminou = pyqtSignal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        posicao: Callable[[], PosicaoDeEstudo | None] = lambda: None,
        pasta_inicial: Path = Path("."),
        analyzer: EngineAnalyzer | None = None,
        pasta_de_estudos: Path | None = None,
        recorte: Callable[[Ancora], Any] = lambda _ancora: None,
        linha_impressa: Callable[[Ancora], str] = lambda _ancora: "",
        abrir_pagina: Callable[[Ancora], bool] = lambda _ancora: False,
        bases_de_partidas: Callable[[], Sequence[Path]] = tuple,
        para_o_texto: Callable[[str], bool] = lambda _linha: False,
    ) -> None:
        super().__init__(parent)
        self._posicao = posicao
        """De onde vem a posição do diagrama selecionado -- **inteira**, com vez, número de lance e
        âncora no livro. Era `current_fen` no Tk, e o que ela devolvia era só o campo de peças
        (S-269)."""

        self._pasta_inicial = Path(pasta_inicial)
        self._analyzer = analyzer
        """O motor, se houver um. `None` esconde a seção inteira em vez de deixá-la cinza (S-33)."""
        self._recorte = recorte
        self._linha_impressa = linha_impressa
        self._abrir_pagina = abrir_pagina
        self._bases = bases_de_partidas
        self._para_o_texto = para_o_texto
        self._pasta_de_estudos = pasta_de_estudos

        self._acertos = 0
        self._erros = 0
        self._analysing = False
        self._geracao = 0
        """Cresce a cada mudança de nó. A resposta do motor que chegar com geração velha é
        descartada -- ver `analyse` (S-285)."""
        self._candidatos: list[Evaluation] = []
        self._loja: Any = None
        self._recorte_de = ""
        self._sujo = False
        self._trechos: tuple[estudo_lista.Trecho, ...] = ()
        self._variantes: tuple[estudo_dobra.Variante, ...] = ()
        self._dobradas: set[tuple[int, ...]] = set()
        """As variantes dobradas, por caminho do primeiro lance delas (S-516).

        Estado de **vista**: não entra na pilha de desfazer, não vai para o PGN e não sobrevive
        à sessão. Caminho que deixou de existir simplesmente não casa com variante nenhuma."""
        self._comentario_do_no: chess.pgn.GameNode | None = None
        self._montando = False
        self._fracao_do_tabuleiro = FRACAO_PADRAO_DO_TABULEIRO

        self.sala = Sala()
        self.estudo = Estudo.de_posicao(PosicaoDeEstudo())
        self._historico = Historico(self.estudo.para_pgn())
        self._edicao = 0

        self._relogio_de_gravacao = QTimer(self)
        self._relogio_de_gravacao.setSingleShot(True)
        self._relogio_de_gravacao.timeout.connect(self.salvar_agora)

        self._montar()
        self.tabuleiro.definir_fracao(self._fracao_do_tabuleiro)
        self._motor_respondeu.connect(self._mostrar_avaliacao)
        self._motor_falhou.connect(self._mostrar_erro_do_motor)
        self._motor_terminou.connect(self._terminar_analise)
        self.refresh()
        self.set_status("Clique em uma peça para estudar.")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.linha(),) * 4)
        fora.setSpacing(espaco.linha())
        for barra in self._barras():
            fora.addWidget(barra)

        # **Duas colunas** (S-276): tabuleiro à esquerda, lances à direita. É a repartição que todo
        # programa de xadrez usa, e pela mesma razão: lê-se a linha com o olho ao lado do
        # tabuleiro, e não abaixo dele.
        self.divisor = QSplitter(Qt.Orientation.Horizontal, self)
        self.divisor.addWidget(self._esquerda())
        self.divisor.addWidget(self._direita())
        self.divisor.setStretchFactor(0, 3)
        self.divisor.setStretchFactor(1, 2)
        fora.addWidget(self.divisor, 1)

    def _botao(self, barra: BarraFluida, acao: str) -> QPushButton:
        """Um botão do catálogo, ligado ao método que `COMANDOS_DA_ABA` nomeia.

        **O método vem da tabela, e não é escrito aqui.** É o que faz um comando novo da sala
        chegar à barra, ao menu e à paleta de uma vez -- e o que garante que os dois frontends
        chamem exatamente os mesmos métodos.
        """
        from chess_diagram_ocr.ui import atalhos

        botao = QPushButton(comandos.rotulo_de_botao(acao), barra)
        # Qual ação este botão serve, legível de fora. O rótulo não responde: os quatro de
        # navegação passaram a desenhar só o ícone (S-520), e um teste que perguntasse pelo texto
        # deixaria de achá-los -- que é a guarda medindo o desenho em vez do arranjo.
        botao.setProperty("acao", acao)
        botao.clicked.connect(lambda _marcado=False, nome=acao: self.executar(nome))
        tema.aplicar_papel(botao, comandos.papel(acao))
        # **O ícone quando o catálogo declara um** (S-520), do mesmo jeito que a fita faz. Aqui
        # ele alcança só os quatro de navegação, e não é decoração: `⏮ ◀ ▶ ⏭` não existem na fonte
        # da interface -- `inFont` responde `False` para os quatro em Segoe UI --, então o rótulo
        # deles vinha de uma fonte de queda, com desenho que não é o da janela. O texto **fica**:
        # ícone que não desenhou devolve `None` e o botão continua legível.
        nome_do_icone = comandos.comando(acao).icone
        if nome_do_icone:
            lado = LADO_DO_ICONE_DA_SALA
            desenho = qt_icones.icone(nome_do_icone, 2 * lado, tema.cor_atual(tokens.TEXTO_PADRAO))
            if desenho is not None:
                botao.setIcon(desenho)
                botao.setIconSize(qt_icones.tamanho(lado))
        motivo = comandos.rotulo(acao)
        tecla = atalhos.acelerador(acao)
        dica_em(botao, f"{motivo}\nTecla: {tecla}" if tecla else motivo)
        barra.adicionar(botao)
        return botao

    def executar(self, acao: str) -> None:
        """Roda o método que o catálogo liga àquela ação. Levanta para ação que a aba não tem."""
        getattr(self, COMANDOS_DA_ABA[acao])()

    def _barras(self) -> list[BarraFluida]:
        """**Três linhas, e o corte entre elas é o assunto** (S-517): a posição, a árvore, e o
        livro somado ao que entra e sai.

        Eram quatro, e a navegação estava na segunda -- encostada na cirurgia de árvore. Medido em
        2026-09-01: 28 botões (31 com motor) ocupando 130 px de 800 a 900 de largura e 155 px de
        620 a 760, antes de qualquer conteúdo.

        **Os quatro de navegação saíram daqui e foram para baixo do tabuleiro**, que é onde a
        frequência os põe: são o único grupo cujo uso justifica estar ao lado do olho que já está no
        tabuleiro. E a fileira que sobrou é só de árvore -- `Apagar variante` deixou de estar
        encostado no `▶`, que era o vizinho mais perigoso que ele podia ter.

        As duas últimas viraram uma: o livro e a entrada/saída são as de menor frequência da aba, e
        juntas ainda cabem numa fileira na largura de trabalho -- e a `BarraFluida` quebra sozinha
        quando não cabem.
        """
        posicao = BarraFluida(self)
        for acao in (
            "estudo_do_diagrama",
            "estudo_da_posicao_inicial",
            "virar_tabuleiro",
            "trocar_vez",
            "estudo_aplicar_fen",
            "copiar_fen",
            "salvar_estudo",
        ):
            self._botao(posicao, acao)
        self.seguir_ocr = QCheckBox("Seguir OCR selecionado", posicao)
        self.seguir_ocr.setChecked(True)
        self.seguir_ocr.toggled.connect(lambda _ligado: self.on_follow_ocr_toggle())
        posicao.adicionar(self.seguir_ocr)

        linha = BarraFluida(self)
        for acao in (
            "promover_variante",
            "promover_a_principal",
            "rebaixar_variante",
            "apagar_variante",
            "apagar_continuacao",
        ):
            self._botao(linha, acao)
        dica_em(
            self._botao(linha, "simbolo_do_lance"),
            "O símbolo do lance. Escolher o mesmo de novo tira; escolher outro do mesmo grupo\n"
            "troca. Julgar o lance (!, ?) e julgar a posição (⩲, ±) são duas frases, e somam.",
        )
        self.btn_dobra = self._botao(linha, "dobrar_variantes")
        self.btn_dobra.setCheckable(True)
        dica_em(
            self.btn_dobra,
            "Esconde o miolo das variantes e deixa `(…)` no lugar. O `(` de cada uma também\n"
            "responde ao clique. A variante que contém o lance corrente não se dobra.",
        )
        self.lbl_simbolo = QLabel("", linha)
        tema.pintar(self.lbl_simbolo, "color", tokens.TEXTO_SECUNDARIO)
        linha.adicionar(self.lbl_simbolo)
        return [posicao, linha, self._barra_de_fora()]

    def _barra_de_navegacao(self) -> BarraFluida:
        """Os quatro de navegação, **sob o tabuleiro**, com o lance corrente e a vez (S-517).

        As duas informações ao lado não são decoração: o lance corrente só existia como fundo
        amarelo no meio da lista, e a vez a jogar só como sufixo da frase do rodapé -- que é a
        última linha da janela, longe do olho de quem está olhando o tabuleiro.
        """
        barra = BarraFluida(self)
        for acao in ("inicio_da_linha", "lance_anterior", "proximo_lance", "fim_da_linha"):
            botao = self._botao(barra, acao)
            if not botao.icon().isNull():
                # **Só aqui o ícone substitui o rótulo** (S-520), e é o único grupo em que isso é
                # honesto: o `rotulo_curto` destes quatro **é** um símbolo (`⏮ ◀ ▶ ⏭`), então
                # mantê-lo ao lado do ícone desenharia a mesma seta duas vezes -- uma da fonte de
                # queda e outra do traço vetorial. O rótulo longo e a tecla continuam na dica, que
                # é onde eles sempre estiveram.
                botao.setText("")
                botao.setIconSize(qt_icones.tamanho(2 * LADO_DO_ICONE_DA_SALA))
        self.lbl_lance = QLabel("", barra)
        self.lbl_lance.setFont(tema.fonte_atual(tipografia.TITULO))
        barra.adicionar(self.lbl_lance)
        self.lbl_vez = QLabel("", barra)
        tema.pintar(self.lbl_vez, "color", tokens.TEXTO_SECUNDARIO)
        barra.adicionar(self.lbl_vez)
        return barra

    def _barra_de_fora(self) -> BarraFluida:
        de_fora = BarraFluida(self)
        self.btn_recorte = self._botao(de_fora, "mostrar_diagrama")
        self.btn_recorte.setCheckable(True)
        dica_em(
            self.btn_recorte,
            "O recorte que o modelo leu, ao lado do tabuleiro. Fica cinza quando o estudo não\n"
            "veio de um diagrama do livro -- uma FEN digitada à mão não tem recorte.",
        )
        dica_em(
            self._botao(de_fora, "linha_do_livro"),
            "Joga na árvore a linha impressa ao lado deste diagrama, e para no primeiro lance\n"
            "que a posição não sustenta -- dizendo qual foi. Exige a folha lida na aba Texto.",
        )
        self._botao(de_fora, "ir_para_a_pagina")
        self.btn_continua: QPushButton | None = None
        if self._analyzer is not None:
            self._botao(de_fora, "analisar_posicao")
            self.btn_continua = self._botao(de_fora, "analise_continua")
            self.btn_continua.setCheckable(True)
            dica_em(
                self.btn_continua,
                "O motor acompanha o lance corrente e grava a avaliação nele, em [%eval].\n"
                "Navegar cancela a análise em curso: a resposta atrasada é descartada.",
            )
            self._botao(de_fora, "variante_do_motor")
        self._botao(de_fora, "partidas_da_posicao")
        self._entrada_e_saida(de_fora)
        return de_fora

    def _entrada_e_saida(self, entra_e_sai: BarraFluida) -> None:
        """O que entra e o que sai, na mesma fileira do livro (S-517).

        Eram duas fileiras, e as duas são as de menor frequência da aba: colar, abrir, exportar e
        levar para o texto acontecem uma vez por sessão, não uma vez por lance. Juntas cabem numa
        linha na largura de trabalho -- e quando não couberem, a `BarraFluida` quebra sozinha, que é
        o item inteiro da S-151.
        """
        for acao in (
            "colar_estudo",
            "abrir_pgn",
            "exportar_estudo_md",
            "exportar_estudo_html",
            "exportar_estudo_rtf",
            "estudo_para_o_texto",
        ):
            self._botao(entra_e_sai, acao)
        self.btn_treino = self._botao(entra_e_sai, "modo_treino")
        self.btn_treino.setCheckable(True)
        dica_em(
            self.btn_treino,
            "A linha some e o tabuleiro cobra o lance. A árvore não muda: errar não cria\n"
            "variante -- para guardar o lance que você jogou, desligue o treino.",
        )
        self.lbl_placar = QLabel("", entra_e_sai)
        tema.pintar(self.lbl_placar, "color", tokens.TEXTO_SECUNDARIO)
        entra_e_sai.adicionar(self.lbl_placar)

    def _esquerda(self) -> QWidget:
        coluna = QWidget(self.divisor)
        pilha = QVBoxLayout(coluna)
        pilha.setContentsMargins(0, 0, espaco.linha(), 0)

        self.tabuleiro = TabuleiroDeJogo(coluna, escolher_promocao=self.choose_promotion)
        self.tabuleiro.lance.connect(self.push_move)
        self.tabuleiro.seta.connect(self.on_arrow)
        self.tabuleiro.recado.connect(self.set_status)
        # **A altura segue a largura** (S-517), e só aqui: sem isto o widget fica com toda a altura
        # sobrando da coluna, o tabuleiro flutua no meio dela, e a faixa de navegação -- que existe
        # para estar colada nele -- aparece ~100 px abaixo do tabuleiro.
        politica = self.tabuleiro.sizePolicy()
        politica.setHeightForWidth(True)
        self.tabuleiro.setSizePolicy(politica)
        pilha.addWidget(self.tabuleiro)
        pilha.addWidget(self._barra_de_navegacao())

        # A miniatura do diagrama (S-282). Ela nasce escondida: estudo sem âncora não mostra
        # espaço reservado para o que não existe.
        self.recorte_label = QLabel("", coluna)
        self.recorte_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recorte_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recorte_label.hide()
        self.recorte_label.mousePressEvent = lambda _evento: self.ampliar_recorte()  # type: ignore[method-assign,assignment]
        pilha.addWidget(self.recorte_label)

        self.lbl_origem = QLabel("Base: posição inicial", coluna)
        self.lbl_status = QLabel("", coluna)
        self.lbl_status.setWordWrap(True)
        pilha.addWidget(self.lbl_origem)
        pilha.addWidget(self.lbl_status)

        self.campo_fen = QLineEdit(self.estudo.tabuleiro.fen(), coluna)
        self.campo_fen.setFont(tema.fonte_atual(tipografia.DADO))
        self.campo_fen.returnPressed.connect(self.apply_fen)
        pilha.addWidget(self.campo_fen)
        return coluna

    def _direita(self) -> QWidget:
        """A coluna de leitura, repartida por um divisor vertical (S-519).

        **Medido em 2026-09-01**: a caixa "Lances" levava todo o esticamento e usava um terço dele
        -- ~370 px vazios a 900x800 e ~590 a 1250x1000, 81% da caixa --, enquanto o comentário, que
        é onde se escreve a frase do livro, tinha quatro linhas fixas.

        A repartição passa a ser de quem lê, e sobrevive à sessão pelo caminho que `estudo_divisor`
        já abriu. **Sem motor a seção não existe** (S-33), e o divisor tem duas partes em vez de
        três: reservar altura para o que não está lá é o defeito que a S-450 tirou do tabuleiro.
        """
        coluna = QSplitter(Qt.Orientation.Vertical, self.divisor)
        coluna.setChildrenCollapsible(False)

        lances = QGroupBox("Lances", coluna)
        dentro = QVBoxLayout(lances)
        dentro.setContentsMargins(*(espaco.linha(),) * 4)
        # `QTextBrowser` e não `QLabel`: a lista rola, o texto é rico, e o clique num lance chega
        # por `anchorClicked` -- que é o `tag_bind` do outro lado sem o mapa de tags à mão.
        self.lista = QTextBrowser(lances)
        self.lista.setOpenLinks(False)
        self.lista.anchorClicked.connect(self._clique_na_lista)
        self.lista.setFont(tema.fonte_atual(tipografia.CORPO))
        dentro.addWidget(self.lista)

        anotacao = QGroupBox("Comentário do lance", coluna)
        dentro = QVBoxLayout(anotacao)
        dentro.setContentsMargins(*(espaco.linha(),) * 4)
        self.comentario = QTextEdit(anotacao)
        # **Piso e não altura fixa** (S-519): com o divisor, quem decide a altura é quem lê. As
        # quatro linhas de antes eram o teto e o piso ao mesmo tempo, e a caixa onde se escreve a
        # frase do livro era a menor da coluna.
        self.comentario.setMinimumHeight(3 * tema.altura_de_linha_atual())
        # Grava ao **sair** do campo, e não a cada tecla: um sinal por letra faria a lista de
        # lances ser redesenhada trinta vezes por frase, e o cursor pularia junto.
        self.comentario.focusOutEvent = self._saiu_do_comentario  # type: ignore[method-assign,assignment]
        dentro.addWidget(self.comentario)

        if self._analyzer is not None:
            self._secao_do_motor(coluna)
        # A altura de fábrica reparte por uso, e não em partes iguais: a lista é a maior, o
        # comentário cabe um parágrafo, e o motor fica no que a seção dele pede.
        for indice, peso in enumerate((3, 2, 1)[: coluna.count()]):
            coluna.setStretchFactor(indice, peso)
        self.divisor_vertical = coluna
        return coluna

    def _secao_do_motor(self, pai: QWidget) -> QGroupBox:
        """A seção do motor. Sem binário, ela simplesmente não existe (S-33)."""
        assert self._analyzer is not None
        caixa = QGroupBox(f"Motor ({self._analyzer.path.name})", pai)
        pilha = QVBoxLayout(caixa)
        pilha.setContentsMargins(*(espaco.linha(),) * 4)

        linha = QHBoxLayout()
        self.btn_analisar = QPushButton("Analisar posição", caixa)
        self.btn_analisar.clicked.connect(self.analyse)
        tema.aplicar_papel(self.btn_analisar, estilos.NEUTRO)
        dica_em(
            self.btn_analisar,
            "Fica cinza enquanto o motor está pensando nesta posição, e volta quando\n"
            "ele responde. Sem motor UCI instalado, esta seção inteira não aparece.",
        )
        linha.addWidget(self.btn_analisar)
        self.lbl_motor = QLabel("", caixa)
        linha.addWidget(self.lbl_motor, 1)
        pilha.addLayout(linha)

        self.vantagem = QProgressBar(caixa)
        self.vantagem.setRange(0, 100)
        self.vantagem.setValue(50)
        self.vantagem.setTextVisible(False)
        pilha.addWidget(self.vantagem)

        self.lbl_linha_do_motor = QLabel("", caixa)
        self.lbl_linha_do_motor.setWordWrap(True)
        tema.pintar(self.lbl_linha_do_motor, "color", tokens.TEXTO_SECUNDARIO)
        pilha.addWidget(self.lbl_linha_do_motor)
        return caixa

    def showEvent(self, a0: QShowEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """**O teclado vem junto com a aba** (S-281): o `<Map>` do outro lado.

        Sem isto `←` só chega ao estudo depois de um clique no tabuleiro, e quem abre a aba e
        aperta a seta troca de diagrama. Dar o foco ao tabuleiro não tira a seta de dentro da caixa
        de comentário: ali quem responde é `acoes_proprias`, que devolve vazio.
        """
        super().showEvent(a0)
        self.tabuleiro.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tabuleiro.setFocus()

    # -------------------------------------------------------------------------------- lista

    def _redesenhar_lista(self) -> None:
        """Refaz a lista inteira e **reancora os trechos** (S-274).

        O índice do trecho vai no `href` e é resolvido **na hora do clique**: promover ou apagar
        variante muda os índices de variação, e um caminho guardado na montagem apontaria para o
        lance que ocupou o lugar do antigo (S-268).
        """
        self._trechos = estudo_lista.trechos(self.estudo)
        corrente = self.estudo.caminho()
        if self.btn_treino.isChecked():
            # O corte do treino (S-290): o que vem depois do lance corrente some da tela e continua
            # na árvore. É o item inteiro -- "a linha some, e o tabuleiro cobra o lance".
            self._trechos = estudo_lista.ate(self._trechos, corrente)

        secundario = tema.cor_atual(tokens.TEXTO_SECUNDARIO)
        fundo = tema.cor_atual(tokens.SUPERFICIE_DICA)
        # As variantes dobradas (S-516). O miolo some, os dois parênteses ficam, e o `(` é o
        # controle: clicar nele desdobra. Quem decide o que some é `ui/estudo_dobra`, e o lance
        # corrente nunca some -- ver o cabeçalho de lá.
        self._variantes = estudo_dobra.variantes(self._trechos)
        ocultos = estudo_dobra.escondidos(self._trechos, self._dobradas, corrente)
        # **Dobrada de verdade**, e não só declarada: a que contém o lance corrente continua na
        # lista de dobradas e é desenhada aberta, então ela não pode mostrar o `(…)`.
        dobrados = {
            variante.abre
            for variante in self._variantes
            if variante.fecha > variante.abre + 1 and variante.abre + 1 in ocultos
        }
        partes: list[str] = []
        aberto: int | None = None
        for indice, trecho in enumerate(self._trechos):
            if not trecho.texto or indice in ocultos:
                continue
            # **Cada corrida de mesmo recuo é um bloco, e o bloco é o que recua** (S-514). Era um
            # `margin-left` no `<span>`, e o `QTextDocument` descarta margem em elemento inline: o
            # número era lido, estava certo, e não pintava um pixel.
            #
            # A variante abre bloco mesmo no mesmo recuo, senão duas irmãs -- `( 2. Bc4 ) ( 2. d4 )`
            # -- correriam na mesma linha. É o que os dois `<br>` de antes faziam, ditos pela
            # estrutura em vez de por quebra solta.
            comeca = trecho.papel == estudo_lista.ABRE
            if aberto != trecho.recuo or comeca:
                if aberto is not None:
                    partes.append("</div>")
                partes.append(f'<div style="margin-left:{trecho.recuo * RECUO_POR_NIVEL}px">')
                aberto = trecho.recuo
            partes.append(self._trecho_em_html(indice, trecho, secundario, fundo, corrente))
            if indice in dobrados:
                partes.append(
                    f'<a href="dobra:{indice}" style="text-decoration:none">'
                    f'<span style="color:{secundario}">…&nbsp;</span></a>'
                )
        if aberto is not None:
            partes.append("</div>")
        self.lista.setHtml("".join(partes))
        self.lista.scrollToAnchor("corrente")

    def _trecho_em_html(
        self,
        indice: int,
        trecho: estudo_lista.Trecho,
        secundario: str,
        fundo: str,
        corrente: object,
    ) -> str:
        """Um trecho como HTML: cor por papel, e âncora quando ele é navegável.

        **Cor e peso saem de `ui/tokens.py` e de `ui/tipografia.py`**, como as tags do outro lado:
        nada de hexadecimal escrito aqui. A linha principal em negrito e as variantes em peso
        normal é a hierarquia sem gastar matiz -- o recurso escasso do programa depois da S-158.

        **O recuo não está mais aqui** (S-514): quem recua é o bloco que `_redesenhar_lista` abre,
        porque margem em `<span>` o `QTextDocument` ignora.
        """
        estilo: list[str] = []
        apagados = (
            estudo_lista.NUMERO,
            estudo_lista.ABRE,
            estudo_lista.FECHA,
            estudo_lista.RESULTADO,
            estudo_lista.RAIZ,
        )
        if trecho.papel in apagados:
            estilo.append(f"color:{secundario}")
        if trecho.papel == estudo_lista.COMENTARIO:
            estilo.append(f"color:{secundario}")
            estilo.append("font-size:smaller")
        if trecho.papel == estudo_lista.NAG or (trecho.papel == estudo_lista.LANCE and trecho.nivel == 0):
            estilo.append("font-weight:bold")
        e_corrente = trecho.caminho is not None and trecho.caminho == corrente and trecho.papel in (
            estudo_lista.LANCE,
            estudo_lista.RAIZ,
        )
        if e_corrente:
            estilo.append(f"background-color:{fundo}")
            estilo.append(f"color:{tokens.sobre_superficie(fundo)}")

        # **Só o que gruda no vizinho leva `&nbsp;`** (S-515). Era *todo* espaço, e sem nenhuma
        # fronteira de palavra o `QTextEdit` -- `WrapAtWordBoundaryOrAnywhere` de fábrica -- quebrava
        # em qualquer caractere: `O-O` saía `O-`/`O`, e a frase do comentário, `guard`/`am`. Quais
        # papéis grudam é decisão de `ui/sala_declarada.PAPEIS_COLADOS`.
        texto = html.escape(trecho.texto)
        if trecho.papel in PAPEIS_COLADOS:
            texto = texto.replace(" ", "&nbsp;")
        marca = ' name="corrente"' if e_corrente else ""
        corpo = f'<span style="{";".join(estilo)}">{texto}</span>' if estilo else f"<span>{texto}</span>"
        if trecho.papel == estudo_lista.ABRE:
            # **O `(` é o controle da dobra** (S-516), e não um glifo novo ao lado dele. Um `▸`
            # sairia de fonte de queda -- é o que a S-508 mediu nos quatro botões de navegação --,
            # e um triângulo desenhado ao lado de cada variante seria ruído numa lista de notação.
            # O parêntese já delimita a variante; o que faltava era ele responder ao clique.
            return f'<a href="dobra:{indice}" style="text-decoration:none">{corpo}</a>'
        if trecho.caminho is None:
            return f"<a{marca}>{corpo}</a>" if marca else corpo
        return f'<a href="trecho:{indice}"{marca} style="text-decoration:none">{corpo}</a>'

    def _mostrar_lance_corrente(self) -> None:
        """O lance corrente e a vez, na faixa sob o tabuleiro (S-517).

        **O texto sai dos mesmos trechos que a lista desenha**, e não de uma segunda formatação:
        `estudo_lista.trecho_do_caminho` acha o trecho do nó corrente, e o `NUMERO` colado nele --
        quando há um -- é o mesmo `12.` que a lista mostra. Uma segunda montagem daria `12. Ba4`
        aqui e `12...Ba4` ali no dia em que a numeração de variante mudasse.

        Na raiz o trecho é o `RAIZ`, e o texto dele já é "posição do diagrama" ou "posição inicial"
        conforme o estudo tenha vindo do livro -- que é exatamente o que se quer ler ali.
        """
        indice = estudo_lista.trecho_do_caminho(self._trechos, self.estudo.caminho())
        if indice < 0:
            self.lbl_lance.setText("")
        else:
            trecho = self._trechos[indice]
            anterior = self._trechos[indice - 1] if indice else None
            numero = (
                anterior.texto
                if anterior is not None
                and anterior.papel == estudo_lista.NUMERO
                and anterior.caminho == trecho.caminho
                else ""
            )
            self.lbl_lance.setText(f"{numero}{trecho.texto}".strip())
        self.lbl_vez.setText("brancas jogam" if self.estudo.tabuleiro.turn else "pretas jogam")

    def _clique_na_lista(self, url: QUrl) -> None:
        """Vai ao nó daquele trecho. O caminho é resolvido **agora**, e não guardado na âncora."""
        endereco = url.toString()
        if endereco.startswith("dobra:"):
            self._alternar_uma_dobra(int(endereco.removeprefix("dobra:")))
            return
        if not endereco.startswith("trecho:"):
            return
        indice = int(endereco.removeprefix("trecho:"))
        if not 0 <= indice < len(self._trechos):
            return
        caminho = self._trechos[indice].caminho
        if caminho is None:
            return
        self.gravar_comentario()
        if not self.estudo.ir_para(caminho):
            self.set_status("Aquele lance não existe mais.")
        self.refresh()

    # ------------------------------------------------------------------ dobrar variantes (S-516)

    def _alternar_uma_dobra(self, indice: int) -> None:
        """Dobra ou desdobra a variante cujo `(` foi clicado. **A identidade é o caminho.**"""
        alvo = next((v for v in self._variantes if v.abre == indice), None)
        if alvo is None:  # pragma: no cover - a lista foi refeita entre o desenho e o clique
            return
        if alvo.chave in self._dobradas:
            self._dobradas.discard(alvo.chave)
        else:
            self._dobradas.add(alvo.chave)
        self._redesenhar_lista()
        self._atualizar_botao_da_dobra()

    def alternar_dobra(self) -> None:
        """Dobra **todas** as variantes, ou desdobra todas se já houver alguma dobrada.

        **É o caminho descobrível**, e o clique no `(` é o atalho de quem já viu que ele responde.
        Sem um comando, dobrar seria um gesto que só se acha por acidente -- e o estudo em que ele
        vale é justamente o grande, aberto de um PGN, onde a pessoa quer esconder antes de ler.

        Dobrar não muda a árvore nem o PGN: é vista. `edicao` não sobe, e o `Ctrl+Z` não a enxerga.
        """
        if self._dobradas:
            self._dobradas.clear()
            frase = "Variantes desdobradas."
        elif self._variantes:
            self._dobradas = {variante.chave for variante in self._variantes}
            frase = f"{len(self._dobradas)} variante(s) dobrada(s)."
        else:
            frase = "Este estudo não tem variante para dobrar."
        self._redesenhar_lista()
        self._atualizar_botao_da_dobra()
        self.set_status(frase)

    def _atualizar_botao_da_dobra(self) -> None:
        """Cinza sem variante, e com o rótulo do que de fato está na tela -- como a S-347 fez
        com o botão do recorte, e pela mesma razão: um botão que alterna sobre o que não existe
        troca de texto sem que nada mude."""
        self.btn_dobra.setEnabled(bool(self._variantes))
        self.btn_dobra.setChecked(bool(self._dobradas))
        self.btn_dobra.setText(
            comandos.rotulo_alternado("dobrar_variantes")
            if self._dobradas
            else comandos.rotulo_de_botao("dobrar_variantes")
        )

    # -------------------------------------------------------------------------------- motor

    @property
    def has_engine(self) -> bool:
        return self._analyzer is not None

    def analyse(self) -> None:
        """Pede a análise da posição corrente. A resposta atrasada é descartada (S-285)."""
        if self._analyzer is None:
            self.set_status("Sem motor UCI instalado: ponha o Stockfish em engines/ e reabra.")
            return
        if self._analysing:
            return
        self._analysing = True
        self.btn_analisar.setEnabled(False)
        self.lbl_motor.setText("pensando...")
        threading.Thread(
            target=self._trabalho_do_motor,
            args=(self._geracao, self.estudo.tabuleiro.copy(stack=False), self.estudo.no),
            daemon=True,
        ).start()

    def _trabalho_do_motor(self, geracao: int, board: chess.Board, no: chess.pgn.GameNode) -> None:
        assert self._analyzer is not None
        try:
            avaliacoes = self._analyzer.analyse_multi(board, count=CANDIDATOS_DO_MOTOR)
            self._motor_respondeu.emit(geracao, no, avaliacoes)
        except Exception as exc:  # noqa: BLE001 - o motor é binário de terceiro
            logger.warning("Falha na análise: %s", exc)
            self._motor_falhou.emit(geracao, str(exc))
        finally:
            self._motor_terminou.emit(geracao)

    def _mostrar_avaliacao(
        self, geracao: int, no: chess.pgn.GameNode, avaliacoes: list[Evaluation]
    ) -> None:
        """Só escreve se ainda estamos no mesmo lance -- ver `analyse`."""
        if geracao != self._geracao or not avaliacoes:
            return
        self._candidatos = list(avaliacoes)
        melhor = avaliacoes[0]
        self.lbl_motor.setText(melhor.summary())
        self.vantagem.setValue(int(melhor.advantage_fraction() * 100))
        linhas = [
            f"{indice}. {avaliacao.display()}  {' '.join(avaliacao.pv_san)}"
            for indice, avaliacao in enumerate(avaliacoes, start=1)
            if avaliacao.pv_san
        ]
        self.lbl_linha_do_motor.setText("\n".join(linhas) or "Sem lance legal nesta posição.")
        self._gravar_avaliacao(no, melhor)

    def _gravar_avaliacao(self, no: chess.pgn.GameNode, avaliacao: Evaluation) -> None:
        """`[%eval 0.35,18]` no lance, que é onde o Lichess e o ChessBase o leem (S-285).

        **Fora da pilha de desfazer, e de propósito.** A avaliação não é edição de quem estuda:
        pô-la no histórico faria `Ctrl+Z` desfazer um número que o motor escreveu sozinho, e a
        pilha de quem analisou dez lances seria dez passos de nada.
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

    def _mostrar_erro_do_motor(self, geracao: int, mensagem: str) -> None:
        if geracao != self._geracao:
            return
        self.lbl_motor.setText("O motor não respondeu.")
        self.lbl_linha_do_motor.setText(mensagem)

    def _terminar_analise(self, _geracao: int) -> None:
        self._analysing = False
        self.btn_analisar.setEnabled(True)
        # A posição pode ter mudado enquanto o motor pensava: com a análise contínua ligada, é aqui
        # que a próxima começa. Sem isto, navegar durante uma análise deixaria o motor parado.
        self._analisar_se_continuo()

    def _analisar_se_continuo(self) -> None:
        if (
            self.btn_continua is not None
            and self.btn_continua.isChecked()
            and self._analyzer is not None
            and not self._analysing
        ):
            self.analyse()

    def alternar_analise_continua(self) -> None:
        """Liga e desliga o motor acompanhando o lance corrente."""
        if self._analyzer is None or self.btn_continua is None:
            self.set_status("Sem motor UCI instalado: ponha o Stockfish em engines/ e reabra.")
            return
        self.btn_continua.setChecked(not self.btn_continua.isChecked())
        if self.btn_continua.isChecked():
            self.analyse()
        else:
            self.lbl_motor.setText("")
            self.lbl_linha_do_motor.setText("")

    # ------------------------------------------------------------------------------- estado

    def set_status(self, texto: str = "") -> None:
        turno = "brancas" if self.estudo.tabuleiro.turn else "pretas"
        frase = f"{texto} | vez: {turno}" if texto else f"Vez: {turno}"
        self.lbl_status.setText(frase)
        self.estado.emit(frase)

    def refresh(self) -> None:
        """Põe na tela o que o estudo diz: posição, setas, lista, comentário e FEN."""
        self._montando = True
        try:
            self.campo_fen.setText(self.estudo.tabuleiro.fen())
            # `no.move` é a aresta que chegou ao nó corrente, e é `None` na raiz (S-509).
            self.tabuleiro.mostrar_tabuleiro(
                self.estudo.tabuleiro,
                virado=self.estudo.invertido,
                ultimo_lance=self.estudo.no.move,
            )
            self._mostrar_setas()
            self._redesenhar_lista()
            self._mostrar_comentario()
            self._mostrar_nag()
            self._desenhar_recorte()
            self._atualizar_botao_do_recorte()
            self._atualizar_botao_da_dobra()
            self._mostrar_lance_corrente()
            self._mostrar_placar()
        finally:
            self._montando = False
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
        a gravação de tudo (S-345).
        """
        self._sujo = True
        if historico:
            self._edicao += 1
            self._historico.registrar(self.estudo.para_pgn())
        self.sala.guardar(self.estudo)
        self._agendar_gravacao(adiar=not da_maquina)

    # ------------------------------------------------------------------ desfazer (S-275)

    def contem(self, widget: object) -> bool:
        """Este widget está dentro da sala? É o que decide de quem é o `Ctrl+Z` (S-243).

        A subida mora em `qt/atalhos.contem` desde a S-506, quando o painel de resultado e o de
        texto entraram na mesma disputa: três laços iguais é onde um deles deixa de subir.
        """
        return qt_atalhos.contem(self, widget)

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
        alguns kilobytes de texto, gravar antes de cada mudança é uma linha, e desfazer é
        recarregar -- enquanto escrever o inverso de `promote_to_main` seria refazer, com bugs, o
        que a serialização já dá de graça.

        O caminho é reaplicado **depois**, e pode não existir mais: desfazer um "apagar variante"
        devolve lances que o nó corrente não tinha. `ir_para` cai na raiz nesse caso, que é a única
        resposta que não aponta para o vazio.
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
    def fracao_do_divisor_vertical(self) -> float:
        """Onde está a alça entre lances e comentário, como fração da altura (S-519)."""
        tamanhos = self.divisor_vertical.sizes()
        altura = sum(tamanhos)
        if len(tamanhos) < 2 or altura <= 0:
            return 0.0
        return geometria.fracao_de_divisor(tamanhos[0], altura)

    def posicionar_divisor_vertical(self, fracao: float) -> None:
        """Põe a alça vertical naquela fração. `0.0` deixa os pesos decidirem."""
        if fracao <= 0.0:
            return
        tamanhos = self.divisor_vertical.sizes()
        altura = max(1, sum(tamanhos) or self.divisor_vertical.height())
        primeiro = int(altura * fracao)
        resto = max(1, altura - primeiro)
        if len(tamanhos) <= 2:
            self.divisor_vertical.setSizes([primeiro, resto])
            return
        # Com o motor são três partes, e a fração guardada é só a da primeira: as outras duas
        # repartem o que sobra na proporção que já tinham, senão mover a alça de cima esmagaria a
        # seção do motor sem ninguém ter pedido.
        antes = sum(tamanhos[1:]) or 1
        self.divisor_vertical.setSizes(
            [primeiro, *(max(1, int(resto * lado / antes)) for lado in tamanhos[1:])]
        )

    @property
    def fracao_do_divisor(self) -> float:
        """Onde a alça está, como fração da largura. `0.0` quando ainda não há geometria medida."""
        tamanhos = self.divisor.sizes()
        largura = sum(tamanhos)
        if len(tamanhos) < 2 or largura <= 0:
            return 0.0
        return geometria.fracao_de_divisor(tamanhos[0], largura)

    def posicionar_divisor(self, fracao: float) -> None:
        """Põe a alça naquela fração. `0.0` deixa o peso do `QSplitter` decidir."""
        if fracao <= 0.0:
            return
        largura = max(1, sum(self.divisor.sizes()) or self.divisor.width())
        esquerda = int(largura * fracao)
        self.divisor.setSizes([esquerda, max(1, largura - esquerda)])

    @property
    def fracao_do_tabuleiro(self) -> float:
        """Que fração da coluna o tabuleiro ocupa. É o leitor que `AppState.board_zoom` não tinha.

        **O campo existia, era gravado, era lido do disco e não tinha ninguém do outro lado**
        (S-518). O commit que religou o estado da janela registrou "`board_zoom` fica sem uso de
        propósito: o tabuleiro do Qt se ajusta ao painel" -- o que era verdade sobre o piso e não
        sobre o teto, porque `MAX_DO_TABULEIRO` o parava em 560 px.
        """
        return self._fracao_do_tabuleiro

    def definir_fracao_do_tabuleiro(self, fracao: float) -> None:
        """Aplica a fração ao tabuleiro da sala. `0.0` é "nunca escolhi", e aí vale o padrão."""
        self._fracao_do_tabuleiro = FRACAO_PADRAO_DO_TABULEIRO if fracao <= 0.0 else float(fracao)
        self.tabuleiro.definir_fracao(self._fracao_do_tabuleiro)

    # --------------------------------------------------------------- vínculo com o OCR

    def sync_with_ocr(self, force: bool = False) -> None:
        """Traz o diagrama selecionado, se quem estuda quiser esse acoplamento.

        Silenciosa quando não há posição válida: é chamada a cada edição de casa no painel de
        resultado, e uma caixa de "FEN inválida" no meio de uma correção seria pior que não
        sincronizar.

        **Quem decide se há o que fazer é `decidir_sincronia`, e ela é pura (S-512).** A ligação
        cobre três casos que não são o mesmo -- outra mesa, a mesma mesa ainda vazia, e a mesma
        mesa já analisada --, e o terceiro é o que impede uma casa corrigida de zerar a pilha de
        desfazer de quem estava estudando aquele diagrama.
        """
        if not force and not self.seguir_ocr.isChecked():
            return
        posicao = self._posicao()
        if posicao is None:
            return
        decisao = decidir_sincronia(self.estudo.ancora, posicao, vazio=self.estudo.vazio())
        if decisao is Sincronia.NADA:
            return
        self._abrir(
            posicao,
            origem="Base: OCR selecionado",
            # A troca de mesa é um acontecimento e se anuncia; a atualização da posição de um
            # estudo ainda vazio, não -- ela chega a cada casa corrigida, e o rodapé é de quem
            # está corrigindo.
            status="Estudo do diagrama selecionado." if decisao is Sincronia.TROCA else "",
        )

    def on_follow_ocr_toggle(self) -> None:
        if self.seguir_ocr.isChecked():
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

    # --------------------------------------------------------------------------------- sala

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
        self.lbl_origem.setText(origem)
        self.refresh()
        # `status` vazio é "não anuncie": a atualização silenciosa da S-512 passa por aqui a cada
        # casa corrigida, e uma frase por tecla no rodapé enterraria a de quem está corrigindo.
        if not status:
            return
        if anterior is not None:
            self.set_status(f"{status} {anterior.contagem_de_lances()} lance(s) já analisados aqui.")
        else:
            self.set_status(status)

    def reabrir_por_chave(self, chave: str) -> bool:
        """Volta à mesa em que a sessão anterior parou. Devolve se achou (S-347).

        A chave é opaca e não se desmonta em âncora; quem sabe qual estudo ela nomeia é a própria
        sala, que tem todos eles carregados. Silencioso quando não acha: o livro pode ter sido
        varrido de novo, e voltar à porta da sala é a degradação certa -- não é erro.
        """
        if not chave:
            return False
        alvo = next((e for e in self.sala.estudos() if e.ancora.chave() == chave), None)
        if alvo is None:
            return False
        self.gravar_comentario()
        self.sala.guardar(self.estudo)
        self.estudo = alvo
        self._historico.zerar(self.estudo.para_pgn())
        self.lbl_origem.setText(f"Base: {alvo.ancora.rotulo()}")
        self.refresh()
        self.set_status(f"Estudo reaberto: {alvo.ancora.rotulo()} · {alvo.contagem_de_lances()} lance(s).")
        return True

    def abrir_livro(self, documento: str) -> None:
        """Carrega a sala daquele livro do disco. Chamado quando um PDF é aberto (S-271).

        **Não pergunta.** Aqui o arquivo *é* o estudo, e não uma cópia de segurança dele: não há
        releitura de onde a análise possa vir, então oferecer seria oferecer apagar o trabalho.
        """
        self.salvar_agora()
        self.sala = estudo_arquivo.carregar(documento, pasta=self._pasta_de_estudos)
        if len(self.sala):
            self.set_status(f"{len(self.sala)} estudo(s) deste livro carregados.")

    @property
    def chave_do_estudo_aberto(self) -> str:
        """O que o estado da aplicação guarda para voltar à mesma mesa (S-271)."""
        return self.estudo.ancora.chave() if self.estudo.ancora.valida else ""

    def _agendar_gravacao(self, *, adiar: bool = True) -> None:
        """Grava depois da inatividade, e não por relógio -- é a régua da S-255.

        **`adiar=False` não empurra o relógio, e é o que faz a gravação acontecer (S-345).** Com a
        análise contínua ligada, o motor escreve `[%eval ...]` a cada ~800 ms, e cada escrita
        passava por aqui reagendando: o prazo de inatividade nunca vencia, e a sala **nunca** era
        gravada enquanto o motor estivesse ligado.

        A inatividade é do **humano**: o que a máquina escreve entra na sala e no arquivo da
        próxima gravação, e não adia a que já está marcada. Sem nenhuma marcada, ela marca uma.
        """
        if self._relogio_de_gravacao.isActive() and not adiar:
            return
        self._relogio_de_gravacao.start(int(estudo_arquivo.ESPERA_SEGUNDOS * 1000))

    def salvar_agora(self) -> Path | None:
        """Grava a sala. Chamada pela inatividade, ao trocar de livro e ao fechar a janela.

        **A primeira linha é `gravar_comentario`, e a ordem é o item (S-302).** O que está digitado
        na caixa de comentário só entra no nó quando ela perde o foco. Quem escreve uma nota e fecha
        o programa com o cursor ainda dentro dela perdia a nota: `salvar_agora` saía em
        `if not self._sujo` sem olhar a caixa. Depois do teste de `_sujo` não adiantaria: é
        `gravar_comentario` quem liga `_sujo`.
        """
        self._relogio_de_gravacao.stop()
        self.gravar_comentario()
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

    # -------------------------------------------------------------------------------- ações

    def load_initial_position(self) -> None:
        if not self._confirmar_abandono("recomeçar da posição inicial"):
            return
        self.seguir_ocr.setChecked(False)
        self.sala.guardar(self.estudo)
        self.estudo = Estudo.de_posicao(PosicaoDeEstudo())
        self.lbl_origem.setText("Base: posição inicial")
        self.refresh()
        self.set_status("Tabuleiro reiniciado na posição inicial.")

    def apply_fen(self) -> None:
        fen = self.campo_fen.text().strip()
        if not fen:
            self.set_status("Não há FEN para carregar no tabuleiro de estudo.")
            return
        if not is_valid_fen(fen):
            QMessageBox.critical(self, "FEN inválida", "A FEN informada para estudo é inválida.")
            return
        if not self._confirmar_abandono("aplicar outra FEN"):
            return
        self.seguir_ocr.setChecked(False)
        self.sala.guardar(self.estudo)
        self.estudo = Estudo.de_posicao(PosicaoDeEstudo(placement=fen))
        self.lbl_origem.setText("Base: FEN manual")
        self.refresh()
        self.set_status("FEN aplicada no tabuleiro de estudo.")

    def _confirmar_abandono(self, o_que: str, *, sempre: bool = False) -> bool:
        """Pergunta antes de largar um estudo com análise dentro (regra 7 da spec).

        Estudo com âncora válida **em geral** não precisa de pergunta: ele fica guardado na sala e
        volta quando se clicar naquele diagrama de novo. Quem perde alguma coisa é o estudo
        **avulso** -- o de uma FEN digitada à mão --, que não pertence a livro nenhum.

        `sempre=True` é para o caso em que nem a âncora salva: trocar o lado a jogar muda a
        **raiz**, e a árvore antiga deixa de fazer sentido sobre a posição nova.
        """
        if self.estudo.vazio() or (self.estudo.ancora.valida and not sempre):
            return True
        onde = (
            "e ele será descartado"
            if sempre
            else "e não está atado a um diagrama do livro, então ele não será guardado"
        )
        return self._perguntar(
            "Estudo em andamento",
            f"Este estudo tem {self.estudo.contagem_de_lances()} lance(s) {onde}."
            f"\n\nQuer mesmo {o_que}?",
        )

    def _perguntar(self, titulo: str, pergunta: str) -> bool:
        """Sim/Não com **Não como padrão**, que é o `default=messagebox.NO` do outro lado.

        Num `QMessageBox` o padrão é o primeiro botão, e as perguntas que passam por aqui descartam
        análise humana: um `Enter` de reflexo não pode ser a confirmação.
        """
        caixa = QMessageBox(self)
        caixa.setIcon(QMessageBox.Icon.Question)
        caixa.setWindowTitle(titulo)
        caixa.setText(pergunta)
        caixa.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        caixa.setDefaultButton(QMessageBox.StandardButton.No)
        return caixa.exec() == QMessageBox.StandardButton.Yes

    def copy_fen(self) -> None:
        from PyQt6.QtWidgets import QApplication

        area = QApplication.clipboard()
        if area is not None:
            area.setText(self.estudo.tabuleiro.fen())
        self.set_status("FEN do estudo copiada.")

    def flip_board(self) -> None:
        """Vira o tabuleiro. **Fora da pilha de desfazer** (S-346).

        A orientação é vista, e não árvore: `para_pgn` não muda com ela, mas `_edicao` subia -- e é
        `_edicao` que diz a `ui/desfazivel.py` **qual painel** recebe o `Ctrl+Z`. Virar o tabuleiro
        sequestrava a tecla: ela vinha para a sala e não desfazia nada, enquanto a edição real de
        quem estava no editor ao lado ficava lá, sem quem a desfizesse.
        """
        self.estudo.invertido = not self.estudo.invertido
        self.tabuleiro.mostrar_tabuleiro(self.estudo.tabuleiro, virado=self.estudo.invertido)
        self._mostrar_setas()
        self._marcar_sujo(historico=False)

    def toggle_turn(self) -> None:
        board = self.estudo.raiz.board()
        board.turn = not board.turn
        # `sempre=True`: trocar a vez muda a **raiz**, e a árvore antiga não vale sobre ela. É a
        # única ação da aba que descarta um estudo ancorado, e por isso a única que pergunta mesmo
        # havendo âncora.
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
        self.lbl_origem.setText("Base: lado a jogar ajustado")
        self.refresh()
        self.set_status("Lado a jogar invertido.")
        self._marcar_sujo()

    # ---------------------------------------------------------------------------- navegação

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
        """Segue a **linha principal a partir daqui**, e é isso que "fim da linha" quer dizer."""
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
        if self.btn_treino.isChecked():
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
        """As quatro peças de coroação, numa caixa. `None` é "desisti", e o lance não acontece."""
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Promoção")
        caixa.setText("Escolha a peça para promoção")
        botoes: dict[QAbstractButton | None, int] = {
            caixa.addButton(rotulo, QMessageBox.ButtonRole.AcceptRole): tipo
            for rotulo, tipo in (
                ("Dama", chess.QUEEN),
                ("Torre", chess.ROOK),
                ("Bispo", chess.BISHOP),
                ("Cavalo", chess.KNIGHT),
            )
        }
        caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caixa.exec()
        return botoes.get(caixa.clickedButton())

    # ---------------------------------------------------------------------------- variantes

    def promover_variante(self) -> None:
        self._operar_na_arvore("promote", "Variante promovida um nível.")

    def promover_a_principal(self) -> None:
        self._operar_na_arvore("promote_to_main", "Variante promovida a linha principal.")

    def rebaixar_variante(self) -> None:
        self._operar_na_arvore("demote", "Variante rebaixada.")

    def _operar_na_arvore(self, operacao: str, status: str) -> None:
        """Aplica a operação e **volta a apontar para o nó**, não para o caminho.

        Promover reordena as irmãs. Um caminho guardado antes da operação aponta para outro lance
        depois dela -- é a armadilha que `estudo.py` documenta, e é aqui que ela morde.
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

        Apagar um lance solto é o desfazer de um clique errado, e perguntar ali seria atrito.
        Apagar uma subárvore com comentário ou com mais de um lance é perder trabalho.
        """
        raizes: Sequence[chess.pgn.GameNode] = list(no.variations) if so_continuacao else [no]
        lances, anotado = _tamanho_da_subarvore(raizes)
        if lances <= 1 and not anotado:
            return True
        return self._perguntar(
            "Apagar",
            f"Isto apaga {lances} lance(s)" + (" e a anotação deles" if anotado else "") + ".\n\nApagar?",
        )

    # ------------------------------------------------------------------------------ anotação

    def _mostrar_comentario(self) -> None:
        self._comentario_do_no = self.estudo.no
        self.comentario.setPlainText(estudo_mod.texto_do_comentario(self.estudo.no.comment or ""))

    def _saiu_do_comentario(self, evento: object) -> None:
        QTextEdit.focusOutEvent(self.comentario, evento)  # type: ignore[arg-type]
        self.gravar_comentario()

    def gravar_comentario(self) -> None:
        """Grava o que está na caixa **no nó em que ele foi escrito**, e não no nó corrente.

        A distinção é o item: navegar troca o nó corrente antes de a caixa perder o foco, e gravar
        no corrente poria o comentário de um lance em outro.
        """
        no = self._comentario_do_no
        if no is None:
            return
        novo = self.comentario.toPlainText().strip()
        if novo == estudo_mod.texto_do_comentario(no.comment or ""):
            return
        # `com_texto` e não `no.comment = novo`: a atribuição direta apagaria as setas e a
        # avaliação daquele lance, que moram dentro do mesmo campo (S-268).
        no.comment = estudo_mod.com_texto(no.comment or "", novo)
        self._marcar_sujo()

    def _mostrar_nag(self) -> None:
        """Os símbolos do lance corrente, ao lado do botão que os põe."""
        nags = sorted(self.estudo.no.nags)
        self.lbl_simbolo.setText(" ".join(estudo_mod.simbolo_de_nag(codigo) for codigo in nags))

    def alternar_nag(self, codigo: int) -> None:
        """Liga, desliga ou troca o símbolo do lance corrente (S-278)."""
        no = self.estudo.no
        if no.parent is None:
            self.set_status("A posição do diagrama não recebe símbolo de lance.")
            return
        no.nags = estudo_mod.alternar_nag(set(no.nags), int(codigo))
        self.refresh()
        self._marcar_sujo()

    def escolher_simbolo(self) -> QMenu | None:
        """O menu dos catorze símbolos, sobre o ponteiro.

        **Menu e não caixa de escolha** (S-280): uma caixa não é comando -- ela não tem como ser
        aberta pela paleta nem pelo menu, e o que estava na barra era a única porta para o símbolo
        do lance.
        """
        if self.estudo.no.parent is None:
            self.set_status("A posição do diagrama não recebe símbolo de lance.")
            return None
        atuais = set(self.estudo.no.nags)
        menu = QMenu(self)
        for codigo in nags_oferecidos():
            marca = " ✓" if codigo in atuais else ""
            acao = QAction(
                f"{estudo_mod.simbolo_de_nag(codigo)}   {estudo_mod.NOME_DE_NAG[codigo]}{marca}", menu
            )
            acao.triggered.connect(partial(self.alternar_nag, codigo))
            menu.addAction(acao)
        from PyQt6.QtGui import QCursor

        menu.popup(QCursor.pos())
        return menu

    def _mostrar_setas(self) -> None:
        """As setas do lance corrente, convertidas para o índice de leitura do tabuleiro."""
        self.tabuleiro.definir_setas(
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

        **Vazio enquanto o cursor está em qualquer campo de texto**, e isso é o item: a sala tem o
        campo de FEN, a lista e a caixa de anotação, e ali `←` é do texto. Com o cursor no campo de
        FEN, a seta esquerda movia o cursor **e** desfazia um lance -- e quem estava conferindo uma
        FEN à mão perdia a posição da árvore sem nenhum sinal (S-323).
        """
        from PyQt6.QtWidgets import QApplication

        foco = QApplication.focusWidget()
        if isinstance(foco, (QLineEdit, QTextEdit, QTextBrowser)):
            return frozenset()
        return ACOES_PROPRIAS

    def atender(self, acao: str) -> Callable[[], object] | None:
        """A função desta aba para aquela ação, ou `None` se ela não a atende."""
        return {
            "diagrama_anterior": self.undo_move,
            "proximo_diagrama": self.redo_move,
            "primeira_pagina": self.go_to_start_of_line,
            "ultima_pagina": self.go_to_end_of_line,
        }.get(acao)

    # --------------------------------------------------------- o recorte do diagrama (S-282)

    def alternar_recorte(self) -> None:
        """Liga e desliga a miniatura do diagrama.

        **Sem âncora não há o que mostrar, e o botão diz isso** (S-347): num estudo de FEN digitada
        à mão o clique trocava o rótulo para "Esconder recorte" sem que nada tivesse aparecido, e o
        clique seguinte "escondia" o que não estava lá.
        """
        if not self.estudo.ancora.valida:
            self.btn_recorte.setChecked(False)
            self.set_status("Este estudo não veio de um diagrama do livro: não há recorte para mostrar.")
            self._atualizar_botao_do_recorte()
            return
        self.btn_recorte.setChecked(not self.btn_recorte.isChecked())
        self._atualizar_botao_do_recorte()
        self._desenhar_recorte()

    def _atualizar_botao_do_recorte(self) -> None:
        """Cinza sem âncora, e com o rótulo do que de fato está na tela (S-347)."""
        tem_ancora = self.estudo.ancora.valida
        self.btn_recorte.setEnabled(tem_ancora)
        if not tem_ancora and self.btn_recorte.isChecked():
            # O estado ligado não sobrevive à mesa sem âncora: ele descreveria uma miniatura que
            # não existe, e é o rótulo dele que mentia.
            self.btn_recorte.setChecked(False)
        self.btn_recorte.setText(
            comandos.rotulo_alternado("mostrar_diagrama")
            if self.btn_recorte.isChecked()
            else comandos.rotulo_de_botao("mostrar_diagrama")
        )

    def _desenhar_recorte(self) -> None:
        """A miniatura do diagrama âncora, ou nada.

        **Nada, e não um retângulo vazio**: estudo sem âncora não veio de diagrama nenhum, e um
        espaço reservado para o que não existe rouba largura do tabuleiro sem dizer por quê.

        A imagem é reconstruída só quando a **âncora** muda, e não a cada lance: navegar redesenha
        o tabuleiro dezenas de vezes por minuto, e reamostrar o recorte junto seria trabalho por
        nada.
        """
        chave = self.estudo.ancora.chave() if self.estudo.ancora.valida else ""
        if not self.btn_recorte.isChecked() or not chave:
            self.recorte_label.hide()
            self._recorte_de = ""
            return
        if chave != self._recorte_de:
            pixmap = _miniatura(self._recorte(self.estudo.ancora), LADO_DO_RECORTE)
            if pixmap is None:
                self.recorte_label.hide()
                return
            self.recorte_label.setPixmap(pixmap)
            self._recorte_de = chave
        self.recorte_label.show()

    def ampliar_recorte(self) -> QDialog | None:
        """O recorte no tamanho em que o modelo o leu, numa janela própria (S-282).

        A miniatura cabe na coluna e serve para conferir *que* diagrama é; conferir **uma casa**
        pede o recorte inteiro. Uma janela e não um zoom no lugar: a comparação que se está fazendo
        é com o tabuleiro ao lado, e trocar a miniatura por uma imagem grande o empurraria para
        fora.
        """
        imagem = self._recorte(self.estudo.ancora) if self.estudo.ancora.valida else None
        pixmap = _miniatura(imagem, LADO_AMPLIADO)
        if pixmap is None:
            self.set_status("Não há recorte deste diagrama para ampliar.")
            return None
        janela = QDialog(self)
        janela.setWindowTitle(self.estudo.ancora.rotulo())
        pilha = QVBoxLayout(janela)
        pilha.setContentsMargins(*(espaco.folga(),) * 4)
        rotulo = QLabel(janela)
        rotulo.setPixmap(pixmap)
        pilha.addWidget(rotulo)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=janela)
        botoes.rejected.connect(janela.reject)
        pilha.addWidget(botoes)
        janela.show()
        return janela

    # ------------------------------------------------------- a linha impressa (S-283/S-208)

    def jogar_a_linha_do_livro(self) -> None:
        """Põe na árvore a linha que o livro imprimiu ao lado deste diagrama.

        O contrato é o da S-15 -- propõe, marca, não reescreve calado --, então a linha para no
        primeiro lance que não fecha e a aba **diz qual foi**. A variante entra a partir do **nó
        corrente**: quem aperta o botão depois de andar três lances quer a continuação dali.
        """
        from chess_diagram_ocr.text import notacao

        if not self.estudo.ancora.valida:
            self.set_status("Este estudo não veio de um diagrama do livro, então não há linha impressa.")
            return
        impresso = self._linha_impressa(self.estudo.ancora).strip()
        if not impresso:
            self.set_status(
                "Não há linha lida para este diagrama. Leia a folha na aba Texto e tente de novo."
            )
            return

        lida = notacao.validar(impresso.split(), self.estudo.tabuleiro)
        if not lida.lances:
            self.set_status(f"Nada da linha impressa fechou: {lida.motivo or 'não há lance nela'}.")
            return

        no = self.estudo.no
        # **O primeiro nó é guardado enquanto ele é criado, e não procurado depois (S-312).** Quem
        # já tinha jogado um lance a partir do diagrama recebia a marca "linha impressa no livro"
        # no **seu** lance, e a linha do livro entrava ao lado sem procedência.
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

    def ir_para_a_pagina(self) -> None:
        """Abre o visualizador na página deste diagrama.

        Quem estuda uma posição quer reler o parágrafo, e o estudo sabe onde ele está desde a
        S-268. Livro que saiu do lugar diz isso no rodapé e não levanta -- é a regra da S-164.
        """
        if not self.estudo.ancora.valida:
            self.set_status("Este estudo não veio de um diagrama do livro.")
            return
        if not self._abrir_pagina(self.estudo.ancora):
            self.set_status(f"Não foi possível abrir {self.estudo.ancora.nome_do_livro} nesta página.")
            return
        self.set_status(f"Página {self.estudo.ancora.pagina + 1} do livro.")

    def variante_do_motor(self) -> None:
        """Põe a linha principal do motor na árvore, a partir do lance corrente (S-286).

        **A procedência vai junto, no PGN.** O que a máquina sugeriu e o que a pessoa jogou não
        podem ficar indistinguíveis no arquivo -- é a regra 2 da SPEC_EDITOR aplicada a lance --, e
        a forma padrão de dizê-lo é o comentário de entrada da variante.
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

    def partidas_da_posicao(self) -> QDialog | None:
        """Que partidas da base do usuário chegam a esta posição.

        **Lê o cache, não a base**, e o motivo está em `estudo_partidas`: reproduzir os lances da
        base inteira custa ~104 min em dez processos, e o custo é da passada e não da posição.
        Quando a posição nunca foi perguntada, a resposta diz **isso** em vez de dizer "nenhuma
        partida" -- que seria um número sobre uma pergunta que ninguém fez.

        O `import` mora aqui e não no topo: `games_cache` alcança `games_db` e `pdf_text`, e a aba
        é construída na abertura da janela.
        """
        from chess_diagram_ocr import estudo_partidas

        resposta = estudo_partidas.consultar(
            self._loja_de_posicoes(), self.estudo.tabuleiro.board_fen(), bases=tuple(self._bases())
        )
        self.set_status(resposta.frase)
        if not resposta.achou:
            return None
        return _JanelaDePartidas(self, resposta)

    def _loja_de_posicoes(self) -> Any:
        """O cache de posições, aberto uma vez e mantido. `None` quando não há base.

        `open_store` nunca levanta por causa do disco (é decisão dele), então o `None` daqui só
        significa uma coisa: não há PGN em `pgn_database/` para o cache falar a respeito.
        """
        if self._loja is not None:
            return self._loja
        bases = tuple(self._bases())
        if not bases:
            return None
        from chess_diagram_ocr import games_cache

        self._loja = games_cache.open_store(database=list(bases))
        return self._loja

    # ------------------------------------------------------------------- entrada (S-288)

    def colar_estudo(self) -> QDialog:
        """Abre a caixa de colar posição ou partida.

        **Uma caixa e não dois comandos**: quem tem uma FEN e quem tem um PGN faz o mesmo gesto --
        copia de algum lugar e cola aqui --, e obrigá-los a escolher o comando certo antes é
        perguntar o que o próprio texto responde. Quem responde é `estudo.colar`.
        """
        return _JanelaDeColar(self, self._aceitar_colado)

    def _aceitar_colado(self, texto: str) -> None:
        """O que veio da caixa. **Não descarta nada antes de saber que deu certo.**"""
        novo, motivo = estudo_mod.colar(texto)
        if novo is None:
            self.set_status(motivo)
            return
        if not self._confirmar_abandono("abrir o que foi colado"):
            return
        self.seguir_ocr.setChecked(False)
        self.sala.guardar(self.estudo)
        self._trocar_de_estudo(novo, "Base: colado")
        self.set_status(f"{novo.contagem_de_lances()} lance(s) colados.")

    def abrir_pgn(self) -> None:
        """Abre um `.pgn` do disco: um estudo, ou a coleção de um livro (S-288).

        **Três respostas para três arquivos**, e a diferença não é de tamanho: o `.pgn` que este
        programa gravou traz `SourcePDF`, `Page` e `Diagram`, e as partidas dele entram **na sala**;
        um `.pgn` de uma partida qualquer abre como estudo avulso; um de muitas partidas sem âncora
        abre uma lista para escolher.
        """
        nome, _filtro = QFileDialog.getOpenFileName(
            self, "Abrir PGN", str(self._pasta_inicial), "PGN (*.pgn);;Todos (*.*)"
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
        self._receber_do_pgn(caminho, achados)

    def _receber_do_pgn(self, caminho: Path, achados: Sequence[Estudo]) -> None:
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
        _JanelaDeColecao(self, caminho.name, list(achados), self._escolher_da_colecao)

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
        self.lbl_origem.setText(origem)
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
        """
        from chess_diagram_ocr import estudo_saida
        from chess_diagram_ocr.text import exportacao

        formato = exportacao.formato_de(extensao)
        destino, _filtro = QFileDialog.getSaveFileName(
            self,
            f"Exportar o estudo para {formato.nome}",
            str(self._pasta_inicial / f"{self._nome_sugerido()}{extensao}"),
            f"{formato.nome} (*{extensao});;Todos (*.*)",
        )
        if not destino:
            return

        self.gravar_comentario()
        caminho = Path(destino)
        try:
            recortes = self._gravar_recorte(caminho)
            relatorio = exportacao.exportar(
                estudo_saida.para_documento(self.estudo), formato, recortes=recortes
            )
            exportacao.escrever(caminho, relatorio)
        except OSError as erro:
            QMessageBox.critical(self, "Exportar o estudo", f"Falha ao exportar o estudo:\n{erro}")
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
        imagem. Sem recorte devolve `{}`, e aí a marca `[Diagrama 1]` sai sozinha.
        """
        from chess_diagram_ocr import estudo_saida

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
        from chess_diagram_ocr import estudo_saida

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
        self.btn_treino.setChecked(not self.btn_treino.isChecked())
        self.btn_treino.setText(
            comandos.rotulo_alternado("modo_treino")
            if self.btn_treino.isChecked()
            else comandos.rotulo_de_botao("modo_treino")
        )
        self._acertos = 0
        self._erros = 0
        self.refresh()
        if self.btn_treino.isChecked():
            self.set_status("Treino: jogue o lance da linha. O que vem depois está escondido.")
        else:
            self.set_status("Treino desligado.")

    def _mostrar_placar(self) -> None:
        if not self.btn_treino.isChecked():
            self.lbl_placar.setText("")
            return
        self.lbl_placar.setText(f"treino: {self._acertos} certo(s), {self._erros} errado(s)")

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

        O caminho de sobrescrita com `write_text` trunca antes de escrever: interrompido no meio,
        ele deixa zero byte no lugar do PGN que estava lá -- e o que estava lá é análise salva de
        outro dia.

        **Acrescentar continua sendo um `append`**, e a diferença é o modo de falha: ele nunca
        trunca, então uma interrupção deixa o arquivo anterior inteiro com um jogo pela metade no
        fim -- ruim de ler, e nada perdido.
        """
        from chess_diagram_ocr.atomic_io import atomic_write_text

        conteudo = self.pgn_payload()
        if append and path.exists() and path.stat().st_size > 0:
            with path.open("a", encoding="utf-8") as arquivo:
                arquivo.write("\n\n")
                arquivo.write(conteudo)
                arquivo.write("\n")
            return
        atomic_write_text(path, conteudo + "\n")

    def save_pgn(self) -> None:
        self.gravar_comentario()
        nome, _filtro = QFileDialog.getSaveFileName(
            self, "Salvar estudo em PGN", str(self._pasta_inicial), "PGN (*.pgn);;Todos (*.*)"
        )
        if not nome:
            return

        caminho = Path(nome)
        append = False
        if caminho.exists():
            # Três respostas, não duas: acrescentar é o caso comum (um arquivo por livro), e
            # oferecer só "sobrescrever ou cancelar" faria perder análise já salva.
            caixa = QMessageBox(self)
            caixa.setWindowTitle("PGN existente")
            caixa.setText("O arquivo já existe.")
            acrescentar = caixa.addButton("Acrescentar ao final", QMessageBox.ButtonRole.AcceptRole)
            sobrescrever = caixa.addButton("Sobrescrever", QMessageBox.ButtonRole.DestructiveRole)
            caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            caixa.exec()
            escolhido = caixa.clickedButton()
            if escolhido not in (acrescentar, sobrescrever):
                return
            append = escolhido is acrescentar

        try:
            self.write_pgn(caminho, append=append)
        except OSError as exc:
            QMessageBox.critical(self, "Salvar PGN", f"Falha ao salvar PGN:\n{exc}")
            return
        self.set_status(
            f"Análise acrescentada em {caminho.name}." if append else f"PGN salvo em {caminho.name}."
        )


def _tamanho_da_subarvore(raizes: Sequence[chess.pgn.GameNode]) -> tuple[int, bool]:
    """Quantos lances há embaixo daqueles nós, e se algum deles tem anotação (S-347).

    **A conta é da subárvore, e não da linha principal.** `len(list(filho.mainline())) + 1`
    percorre só a continuação principal, e olhar `filho.comment` vê só o primeiro nível: uma
    variante com três sublinhas anotadas anunciava "isto apaga 2 lance(s)" e apagava dezoito, com
    os comentários todos. A caixa existe para dizer o que se perde, e ela dizia menos do que se
    perdia -- que é pior que não perguntar, porque quem lê "2 lances" clica em Sim.

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
    """O recorte do diagrama como `QPixmap`, ou `None` quando não há o que desenhar (S-282).

    `Any` na assinatura porque a entrada é um `np.ndarray` RGB, e tipá-la obrigaria este módulo a
    importar numpy no topo por causa de uma anotação.

    Falha para o lado do nada: um recorte estragado esconde a miniatura e deixa a aba inteira em
    pé, que é o contrato de degradação do projeto desde a S-53.
    """
    if imagem is None:
        return None
    try:
        from chess_diagram_ocr.qt.imagens import pixmap_de_rgb

        pixmap = pixmap_de_rgb(imagem)
        maior = max(pixmap.width(), pixmap.height()) or 1
        if maior <= lado:
            return pixmap
        return pixmap.scaled(
            lado, lado, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    except Exception as erro:  # noqa: BLE001 - recorte de origem desconhecida
        logger.debug("Recorte do diagrama não pôde ser desenhado: %s", erro)
        return None


class _JanelaDeColar(QDialog):
    """A caixa de colar posição ou partida (S-288).

    Um campo só para as duas, porque o gesto é o mesmo -- copia de algum lugar e cola aqui -- e o
    próprio texto diz o que é. Quem responde é `estudo.colar`.
    """

    def __init__(self, pai: QWidget, aceitar: Callable[[str], None]) -> None:
        super().__init__(pai)
        self.setWindowTitle("Colar posição ou partida")
        self.resize(520, 320)
        self._aceitar = aceitar
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.addWidget(QLabel("Cole aqui uma FEN ou um PGN. O texto diz qual dos dois é.", self))
        self.campo = QTextEdit(self)
        self.campo.setFont(tema.fonte_atual(tipografia.DADO))
        pilha.addWidget(self.campo, 1)
        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        self.show()

    def _confirmar(self) -> None:
        texto = self.campo.toPlainText()
        self.accept()
        self._aceitar(texto)


class _JanelaDeColecao(QDialog):
    """A lista de partidas de um `.pgn` de muitas, para escolher uma (S-288)."""

    def __init__(self, pai: QWidget, nome: str, achados: list[Estudo], escolher: Callable[[Estudo], None]) -> None:
        from PyQt6.QtWidgets import QListWidget

        super().__init__(pai)
        self.setWindowTitle(nome)
        self.resize(560, 420)
        self._achados = achados
        self._escolher = escolher
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.addWidget(QLabel(f"{len(achados)} partida(s) em {nome}. Escolha uma:", self))
        self.lista = QListWidget(self)
        for estudo in achados:
            self.lista.addItem(estudo.ancora.rotulo() or f"{estudo.contagem_de_lances()} lance(s)")
        self.lista.itemDoubleClicked.connect(lambda *_: self._confirmar())
        pilha.addWidget(self.lista, 1)
        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        self.show()

    def _confirmar(self) -> None:
        linha = self.lista.currentRow()
        if not 0 <= linha < len(self._achados):
            return
        escolhido = self._achados[linha]
        self.accept()
        self._escolher(escolhido)


class _JanelaDePartidas(QDialog):
    """As partidas da base que chegam a esta posição (S-287). Só mostra: a escolha é da Galeria."""

    def __init__(self, pai: QWidget, resposta: Any) -> None:
        from PyQt6.QtWidgets import QListWidget

        super().__init__(pai)
        self.setWindowTitle("Partidas da posição")
        self.resize(560, 400)
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        rotulo = QLabel(resposta.frase, self)
        rotulo.setWordWrap(True)
        pilha.addWidget(rotulo)
        self.lista = QListWidget(self)
        for hit in resposta.partidas:
            self.lista.addItem(hit.label)
        pilha.addWidget(self.lista, 1)
        if resposta.truncada:
            # **Quem exibe tem de dizer que a lista é menor que a base**: sem isto, escolher
            # achando que se viu tudo é o defeito que a Galeria já mede na sua própria lista.
            aviso = QLabel(f"{len(resposta.partidas)} de {resposta.total} partida(s).", self)
            tema.pintar(aviso, "color", tokens.TEXTO_SECUNDARIO)
            pilha.addWidget(aviso)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        self.show()
