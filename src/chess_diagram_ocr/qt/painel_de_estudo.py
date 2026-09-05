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

**E a barra de cima é uma fila desde a S-527.** Eram três `BarraFluida` com 28 botões de texto, que
a 715 px quebravam em quatro fileiras. Quem decide grupo, o que é principal, ícone, dica e quem cabe
na largura é `ui/barra_da_sala.py`; `qt/barra_da_sala.py` mede e executa. Os botões que o resto deste
arquivo chama pelo nome -- `btn_dobra`, `btn_recorte`, `btn_treino`, `btn_continua`, `seguir_ocr` --
são `QAction`s daquela barra, e respondem aos mesmos `setChecked`, `setText` e `setEnabled`.
"""

from __future__ import annotations

import html
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QFontMetrics, QResizeEvent, QShowEvent
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import eco, estudo_arquivo, revisao_arquivo, tablebase, taticas_arquivo
from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr import placar as placar_mod
from chess_diagram_ocr.config import PROJECT_ROOT
from chess_diagram_ocr.engine import EngineAnalyzer, Evaluation
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo, Sala
from chess_diagram_ocr.fen_utils import is_valid_fen, reading_index_from_square, square_from_reading_index
from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.barra_da_sala import BarraDaSala
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.motor import BarraDeAvaliacao, LinhasDoMotor
from chess_diagram_ocr.qt.tabuleiro_de_jogo import TabuleiroDeJogo
from chess_diagram_ocr.settings import DEFAULT_SETTINGS_PATH, EngineSettings, load_settings, save_settings
from chess_diagram_ocr.ui import analise_da_partida as analise_declarada
from chess_diagram_ocr.ui import (
    atalhos,
    barra_da_sala,
    cabecalho_da_partida,
    comandos,
    espaco,
    estilos,
    estudo_dobra,
    estudo_lista,
    geometria,
    motor_declarado,
    tipografia,
    tokens,
    treino_declarado,
)
from chess_diagram_ocr.ui import finais as finais_declarados
from chess_diagram_ocr.ui.busy import BusyRegistry
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
    fracao_para_o_tabuleiro,
    nags_oferecidos,
    piso_da_leitura,
)

logger = logging.getLogger(__name__)

DADOS = PROJECT_ROOT / "data"
"""Onde os arquivos de trabalho do treino moram por omissão (S-539 a S-541). Ver `pasta_de_treino`
no construtor: o padrão é este, e o teste passa outro."""

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
        busy: BusyRegistry | None = None,
        caminho_das_preferencias: Path = DEFAULT_SETTINGS_PATH,
        pasta_de_treino: Path | None = None,
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
        self._busy = busy
        """O registro de operações longas da janela, para o índice da base (S-532) aparecer no rodapé
        como as outras. Sem ele, a janela que nos contém pode tê-lo: ver `indexar_base`."""
        self._indexador: Any = None
        """A rodada do índice em curso -- guardada porque um `QObject` sem referência é recolhido
        com a thread dentro (`qt/indice_da_base.py`)."""
        self._busca: Any = None
        """O diálogo de busca (S-533), guardado e **reusado**: ele não é modal, tem uma thread
        dentro, e abrir o segundo enquanto o primeiro procura destruiria um `QThread` em curso."""
        self._arvore: Any = None
        """A janela da árvore de aberturas (S-535), guardada e reusada pela mesma razão -- e mais
        uma: ela **acompanha** a posição da sala a cada `refresh`, então destruí-la e recriá-la a
        cada abertura descartaria a consulta em curso a cada lance."""
        self._construtor_da_arvore: Any = None
        """A passada que constrói a árvore, guardada porque um `QObject` sem referência é recolhido
        com a thread dentro -- a mesma razão de `_indexador`."""
        self._pasta_de_estudos = pasta_de_estudos

        self._pasta_de_treino = Path(pasta_de_treino) if pasta_de_treino is not None else DADOS
        """Onde moram a coleção de táticas, o baralho de revisão e o placar (S-539 a S-541).

        **Um argumento e não três**, e ele existe pelo motivo dos outros caminhos deste painel: o
        teste não pode escrever no `data/` do repositório. O produto usa o padrão, e a janela não
        precisa passar nada -- é o que mantém `qt/janela.py` do tamanho que a catraca exige."""

        self._placar: placar_mod.Placar | None = None
        """O placar do treino, lido do disco no primeiro uso. Ver a propriedade `placar`."""
        self._perda_do_lance: Any = None
        """O medidor do custo do lance errado (S-541), criado no primeiro erro."""
        self._extrator: Any = None
        """A extração de táticas em curso, guardada porque um `QObject` sem referência é recolhido
        com a thread dentro -- a mesma razão de `_indexador`."""
        self._treino: Any = None
        """A janela de treino aberta (S-540). Não modal, e guardada pela mesma razão."""
        self._analysing = False
        self._geracao = 0
        """Cresce a cada mudança de nó. A resposta do motor que chegar com geração velha é
        descartada -- ver `analyse` (S-285)."""
        self._candidatos: list[Evaluation] = []
        self._caminho_das_preferencias = Path(caminho_das_preferencias)
        """De onde saem e para onde voltam as opções do motor (S-536). Argumento porque o teste
        não pode escrever no `data/settings.json` do repositório."""
        self._motor_vivo: Any = None
        """O `MotorVivo` que aplica a troca fora da linha de eventos. Nasce no primeiro uso: sem
        ele, toda sala de teste carregaria uma `QThread` que nunca roda."""
        self._analise_da_partida: Any = None
        """A rodada de análise da partida inteira (S-537), guardada porque um `QObject` sem
        referência é recolhido com a thread dentro -- a mesma razão de `_indexador`."""
        self._finais: Any = None
        """O leitor de tablebases (S-538), aberto na primeira consulta. `None` é "sem pasta"."""
        self._resultado_de_tabela: Any = None
        """O que a tabela disse da posição analisada, ou `None`. Escrito na thread do motor e lido
        na da interface, na mesma volta em que a avaliação chega -- os dois viajam juntos."""
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
        self._divisor_escolhido = False
        """A pessoa (ou a sessão anterior) decidiu onde fica a alça? Ver `_acomodar_o_tabuleiro`."""
        self._faixa_do_tabuleiro: QHBoxLayout | None = None
        """A fila "barra de avaliação + tabuleiro", quando há motor. Guardada porque é nela que se
        mede a esteira da coluna esquerda -- ver `_esteira_da_coluna` (S-551, terceira rodada)."""

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
        atalhos.conferir_dono(self, "PainelDeEstudo")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.linha(),) * 4)
        fora.setSpacing(espaco.linha())

        # **Uma fila, agrupada por tarefa** (S-527). Eram três `BarraFluida` que quebravam em quatro
        # fileiras a 715 px -- 130 px antes do tabuleiro. Quem decide grupo, principal, ícone, dica e
        # quem cabe é `ui/barra_da_sala.py`; o widget mede e executa.
        self._fora = fora
        self.barra = self._montar_barra()
        fora.addWidget(self.barra)

        # **Duas colunas** (S-276): tabuleiro à esquerda, lances à direita. É a repartição que todo
        # programa de xadrez usa, e pela mesma razão: lê-se a linha com o olho ao lado do
        # tabuleiro, e não abaixo dele.
        self.divisor = QSplitter(Qt.Orientation.Horizontal, self)
        self.divisor.addWidget(self._esquerda())
        self.divisor.addWidget(self._direita())
        self.divisor.setStretchFactor(0, 3)
        self.divisor.setStretchFactor(1, 2)
        # Arrastar a alça desliga a regra da S-551 até o fim da sessão: a partir daí quem decide a
        # repartição é quem arrastou, e a janela guarda a fração ao fechar.
        self.divisor.splitterMoved.connect(self._divisor_movido_a_mao)
        fora.addWidget(self.divisor, 1)

    def _montar_barra(self) -> BarraDaSala:
        """A fila da sala, com ou sem o grupo do motor, e os nomes que o painel usa apontados nela.

        **É método porque a S-536 a remonta.** Uma máquina que abriu sem motor e ganha um pelas
        preferências precisa dos três botões do grupo Motor -- e uma `QAction` não muda de barra
        depois de criada, do mesmo modo que um widget do Tk não muda de pai. Remontar é a única
        saída, e ela custa dez linhas porque toda a decisão de quem entra na fila é de
        `ui/barra_da_sala.py`.

        `seguir_ocr` nasce marcado **sem avisar**: o `toggled` já está ligado ao método, e o método
        sincroniza com um tabuleiro que pode ainda não existir.
        """
        barra = BarraDaSala(self, com_motor=self._analyzer is not None, executar=self.executar)
        # Os nomes que o resto do painel sempre usou apontam para as `QAction`s: `setChecked`,
        # `setText`, `setEnabled` e `isChecked` são os mesmos, e é isso que deixa cada método como
        # estava.
        self.seguir_ocr = barra.acoes[barra_da_sala.SEGUIR_OCR]
        self.seguir_ocr.blockSignals(True)
        self.seguir_ocr.setChecked(True)
        self.seguir_ocr.blockSignals(False)
        self.btn_dobra = barra.acoes["dobrar_variantes"]
        self.btn_recorte = barra.acoes["mostrar_diagrama"]
        self.btn_treino = barra.acoes["modo_treino"]
        self.btn_continua: QAction | None = barra.acoes.get("analise_continua")
        return barra

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
        """Roda o método que o catálogo liga àquela ação. Levanta para ação que a aba não tem.

        O interruptor "Seguir OCR" não é comando do catálogo, e o método dele vem de
        `barra_da_sala.METODOS_PROPRIOS` -- a mesma forma de tabela, para o mesmo motivo (S-280).
        """
        metodo = COMANDOS_DA_ABA.get(acao) or barra_da_sala.METODOS_PROPRIOS[acao]
        getattr(self, metodo)()

    def _barra_de_navegacao(self) -> BarraFluida:
        """Os quatro de navegação, **sob o tabuleiro**, com o lance corrente e a vez (S-517).

        As duas informações ao lado não são decoração: o lance corrente só existia como fundo
        amarelo no meio da lista, e a vez a jogar só como sufixo da frase do rodapé -- que é a
        última linha da janela, longe do olho de quem está olhando o tabuleiro.
        """
        barra = BarraFluida(self)
        for acao in barra_da_sala.NAVEGACAO:
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
        # O símbolo do lance corrente **ao lado do lance** (S-527): ele ficava ao lado do botão
        # "Símbolo", na segunda fileira, e o botão foi para a fila de cima. `12. Ba4 !` é como o
        # livro escreve, e é aqui que o olho já está.
        self.lbl_simbolo = QLabel("", barra)
        tema.pintar(self.lbl_simbolo, "color", tokens.TEXTO_SECUNDARIO)
        barra.adicionar(self.lbl_simbolo)
        self.lbl_vez = QLabel("", barra)
        tema.pintar(self.lbl_vez, "color", tokens.TEXTO_SECUNDARIO)
        barra.adicionar(self.lbl_vez)
        # **O ECO da posição corrente** (S-534), na mesma faixa e pela mesma razão que a vez: é o
        # que um enxadrista lê para saber *em que abertura ele está*, e ele mudava a cada lance
        # sem aparecer em lugar nenhum da janela. Ao lado do tabuleiro, que é onde o olho está.
        self.lbl_eco = QLabel("", barra)
        tema.pintar(self.lbl_eco, "color", tokens.TEXTO_SECUNDARIO)
        dica_em(
            self.lbl_eco,
            "O código ECO da posição. O header [ECO] da partida vence; sem ele, a tabela embutida\n"
            "classifica pela posição -- então uma transposição chega ao mesmo código.",
        )
        barra.adicionar(self.lbl_eco)
        # E o placar do treino, pela mesma razão: ele acompanhava o botão "Treinar" na quarta
        # fileira, e o que ele conta acontece no tabuleiro.
        self.lbl_placar = QLabel("", barra)
        tema.pintar(self.lbl_placar, "color", tokens.TEXTO_SECUNDARIO)
        barra.adicionar(self.lbl_placar)
        return barra

    def _esquerda(self) -> QWidget:
        coluna = QWidget(self.divisor)
        pilha = QVBoxLayout(coluna)
        pilha.setContentsMargins(0, 0, espaco.linha(), 0)

        # **O cabeçalho da partida acima do tabuleiro** (S-530), como no ChessBase. Os nove
        # headers existiam -- `Estudo.de_posicao` escreve cinco, um `.pgn` traz os nove -- e nenhum
        # aparecia na tela: quem abrisse Capablanca-Alekhine via um tabuleiro sem nome, sem torneio
        # e sem resultado. Quem decide o que a frase diz é `ui/cabecalho_da_partida.py`.
        pilha.addWidget(self._cabecalho())

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

        # **A barra de avaliação ao lado do tabuleiro** (S-529), à esquerda dele, como no Lichess.
        # Ela só existe com motor, pela mesma regra da seção: 18 px tomados do tabuleiro para
        # mostrar o que nunca terá número seriam 18 px de promessa. Quando ela existe, o tabuleiro
        # divide a faixa com ela e continua crescendo pela altura (S-551) -- a conta de
        # `LARGURA_MINIMA_DA_LEITURA` não muda, porque a barra sai da coluna esquerda.
        #
        # **E ela espelha junto com o tabuleiro**: `virado` é perguntado no `paintEvent` da barra,
        # como a caixa -- guardar a resposta a deixaria de um lado enquanto o tabuleiro já virou.
        self.vantagem = (
            BarraDeAvaliacao(
                coluna, caixa=self._caixa_do_tabuleiro, virado=lambda: self.estudo.invertido
            )
            if self._analyzer is not None
            else None
        )
        if self.vantagem is None:
            pilha.addWidget(self.tabuleiro)
        else:
            faixa = QHBoxLayout()
            faixa.setContentsMargins(0, 0, 0, 0)
            faixa.setSpacing(espaco.folga())
            faixa.addWidget(self.vantagem)
            faixa.addWidget(self.tabuleiro, 1)
            pilha.addLayout(faixa)
            self._faixa_do_tabuleiro = faixa
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

        # **O que sobra de altura vai para um esticador, e não para os rótulos** (S-551).
        # Sem ele o `QVBoxLayout` reparte a sobra entre os itens que aceitam crescer, e os dois
        # rótulos de status ficam com 79 px cada -- é o que o crítico fotografou como "duas frases
        # de status flutuando" em 230 px de coluna vazia. Com o esticador, o bloco fica colado no
        # tabuleiro e a FEN vira o rodapé da coluna, alinhada com o fim da caixa de comentário ao
        # lado. O vazio deixa de ser texto solto e passa a ser margem, que é o que ele é.
        pilha.addStretch(1)

        self.campo_fen = QLineEdit(self.estudo.tabuleiro.fen(), coluna)
        self.campo_fen.setFont(tema.fonte_atual(tipografia.DADO))
        self.campo_fen.returnPressed.connect(self.apply_fen)
        pilha.addWidget(self.campo_fen)
        return coluna

    # ----------------------------------------------------- o cabeçalho da partida (S-530)

    def _cabecalho(self) -> QWidget:
        """Duas linhas e um lápis: quem jogou, e onde. Clicar em qualquer uma abre a edição.

        **Duas linhas, e a segunda é secundária.** Jogadores e resultado numa; torneio, local, data
        e rodada na outra, na cor de texto secundário. É a hierarquia do ChessBase, e é o que faz a
        faixa caber em 494 px -- a largura da coluna a 1400x950 -- sem elidir o nome de ninguém.

        **O botão existe porque não há comando.** Editar o cabeçalho ainda não está em
        `ui/comandos.py`, então não há item de menu, tecla nem entrada na paleta para ele -- e uma
        faixa que só responde a duplo clique é uma função que ninguém acha. O lápis ao lado é a
        afirmação de que aquilo é editável; o duplo clique na frase faz o mesmo, que é o gesto que
        quem vem do ChessBase já tem no dedo.
        """
        faixa = QWidget(self)
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(espaco.folga())

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(0)
        self.lbl_partida = _RotuloElidido(faixa)
        self.lbl_partida.setFont(tema.fonte_atual(tipografia.TITULO))
        textos.addWidget(self.lbl_partida)
        self.lbl_torneio = _RotuloElidido(faixa)
        self.lbl_torneio.setFont(tema.fonte_atual(tipografia.AUXILIAR))
        tema.pintar(self.lbl_torneio, "color", tokens.TEXTO_SECUNDARIO)
        textos.addWidget(self.lbl_torneio)
        linha.addLayout(textos, 1)

        self.btn_cabecalho = QToolButton(faixa)
        self.btn_cabecalho.setProperty("acao", "editar_cabecalho")
        self.btn_cabecalho.setAutoRaise(True)
        self.btn_cabecalho.setIconSize(qt_icones.tamanho(LADO_DO_ICONE_DA_SALA))
        self.btn_cabecalho.clicked.connect(self.editar_cabecalho)
        linha.addWidget(self.btn_cabecalho)

        for alvo in (self.lbl_partida, self.lbl_torneio):
            alvo.setCursor(Qt.CursorShape.PointingHandCursor)
            alvo.mouseDoubleClickEvent = lambda _evento: self.editar_cabecalho()  # type: ignore[assignment]
        self._pintar_o_lapis()
        tema.ao_repintar(self._pintar_o_lapis)
        return faixa

    def _pintar_o_lapis(self) -> None:
        """O traço do botão do cabeçalho na cor da pele em uso -- a medição da S-220."""
        desenho = qt_icones.icone(
            cabecalho_da_partida.ICONE,
            LADO_DO_ICONE_DA_SALA,
            tema.cor_atual(tokens.TEXTO_PADRAO),
            escala=self.devicePixelRatioF(),
        )
        if desenho is not None:
            self.btn_cabecalho.setIcon(desenho)

    def _mostrar_cabecalho(self) -> None:
        """Põe na faixa o que os headers dizem. Quem elide é o próprio rótulo, a cada largura."""
        primeira, segunda = cabecalho_da_partida.linhas(self.estudo.jogo.headers)
        self.lbl_partida.definir_texto(primeira)
        self.lbl_torneio.definir_texto(segunda)
        dica_em(
            self.btn_cabecalho,
            f"{cabecalho_da_partida.TITULO}\nDuplo clique na frase ao lado faz o mesmo.",
        )

    def editar_cabecalho(self) -> QDialog:
        """Abre o formulário dos nove campos. O que ele gravar entra no `Ctrl+Z` da sala."""
        return _JanelaDoCabecalho(self, self.estudo.jogo.headers, self._gravar_cabecalho)

    def _gravar_cabecalho(self, valores: dict[str, str]) -> None:
        """Escreve nos headers **só o que mudou**, e trata a mudança como edição da sala.

        `_marcar_sujo` empilha o PGN inteiro no histórico e agenda a gravação: com ele, `Ctrl+Z`
        devolve o cabeçalho anterior pelo mesmo caminho que devolve um lance, e o `salvar_agora`
        por inatividade leva os headers junto -- eles já estão em `Estudo.para_pgn`. Sem o filtro
        de `mudancas`, abrir o diálogo e fechá-lo em "Gravar" criaria um passo de desfazer que não
        desfaz coisa alguma.
        """
        mudou = cabecalho_da_partida.mudancas(self.estudo.jogo.headers, valores)
        if not mudou:
            self.set_status("O cabeçalho não mudou.")
            return
        for chave, valor in mudou.items():
            if valor:
                self.estudo.jogo.headers[chave] = valor
            elif chave in self.estudo.jogo.headers:
                del self.estudo.jogo.headers[chave]
        self._marcar_sujo()
        self._mostrar_cabecalho()
        self.set_status(f"Cabeçalho da partida: {len(mudou)} campo(s) atualizado(s).")

    # -------------------------------------------- o tabuleiro cresce pela altura (S-551)

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._acomodar_o_tabuleiro()
        if self.vantagem is not None:
            self.vantagem.update()

    def _caixa_do_tabuleiro(self) -> tuple[int, int]:
        """Onde o **tabuleiro desenhado** começa e quanto ele mede, para a barra o acompanhar.

        Perguntado pela barra no `paintEvent` dela, e não guardado num `resizeEvent`: `geometria()`
        é a mesma conta que o tabuleiro usa para se desenhar, e ler o resultado dela na hora é o
        que garante que os dois quadrados coincidam sempre -- inclusive na primeira exibição, em
        que a coluna ainda não tem largura (S-529).
        """
        geo = self.tabuleiro.geometria()
        return int(geo.origin_y), int(geo.size)

    def _divisor_movido_a_mao(self, _posicao: int, _indice: int) -> None:
        self._divisor_escolhido = True

    def _altura_livre_para_o_tabuleiro(self) -> int:
        """Quanta altura da coluna esquerda sobraria para o tabuleiro se ele não a disputasse.

        É a altura da coluna menos o que os vizinhos pedem -- cabeçalho, faixa de navegação,
        recorte **visível**, os dois rótulos, a FEN -- e menos os vãos entre eles. O recorte
        escondido não conta, e é a diferença que explica a foto do crítico: com um diagrama do
        livro aberto, os 220 px de `LADO_DO_RECORTE` ocupam justamente o vazio que ele mediu.
        """
        coluna = self.divisor.widget(0)
        leiaute = coluna.layout() if coluna is not None else None
        if coluna is None or leiaute is None:
            return 0
        margens = leiaute.contentsMargins()
        ocupado = margens.top() + margens.bottom()
        vizinhos = 0
        for indice in range(leiaute.count()):
            item = leiaute.itemAt(indice)
            widget = item.widget() if item is not None else None
            if widget is None or widget is self.tabuleiro:
                continue
            if widget.isHidden():
                continue
            ocupado += widget.sizeHint().height()
            vizinhos += 1
        ocupado += leiaute.spacing() * vizinhos
        return max(0, coluna.height() - ocupado)

    def _caixa_minima_do_tabuleiro(self) -> int:
        """O lado mínimo da **caixa** do tabuleiro: o piso do desenho mais a margem da coordenada.

        **A régua trabalha na caixa, e não no quadriculado** (S-551, terceira rodada). Passar
        `LADO_MINIMO` cru dava uma coluna de 245 px para um tabuleiro de 240: `BoardGeometry.fit`
        desenha os 240 -- o `max(min_size, ...)` dela vence --, sobram 2,5 px de cada lado, e a
        régua de linhas, escrita em `origin_x - 11`, cai **fora** do widget. Medido a 1024x768 com
        o motor ligado: as letras `a`..`h` apareciam e os números `1`..`8` não.
        """
        return qt_tabuleiro.LADO_MINIMO + qt_tabuleiro.MARGEM

    def _esteira_da_coluna(self) -> int:
        """Quanto da coluna esquerda **não** é tabuleiro, na horizontal (S-551, terceira rodada).

        As margens da coluna mais, quando há motor, a barra de avaliação e o vão até o tabuleiro.
        Medida e não cravada: são 42 px na base de referência (0 + 6 de margem, 26 da barra e 10 de
        vão), e quem aumentar a fonte do sistema ou trocar a densidade muda os dois últimos.

        Vai por argumento para `sala_declarada`, que é onde a decisão mora: a régua precisa saber
        que a coluna carrega essa esteira, e **de que ela é feita** é assunto do widget.
        """
        coluna = self.divisor.widget(0)
        leiaute = coluna.layout() if coluna is not None else None
        if leiaute is None:
            return 0
        margens = leiaute.contentsMargins()
        esteira = margens.left() + margens.right()
        faixa = self._faixa_do_tabuleiro
        if self.vantagem is not None and faixa is not None:
            esteira += self.vantagem.sizeHint().width() + max(0, faixa.spacing())
        return esteira

    def _acomodar_o_tabuleiro(self) -> None:
        """Move a alça para o tabuleiro usar a altura que sobra, se ninguém escolheu a alça.

        **A regra é pura** (`sala_declarada.fracao_para_o_tabuleiro`) e só empurra para a direita:
        a fração de agora é o piso. Ela não roda depois de a pessoa arrastar a alça nem depois de
        `posicionar_divisor` restaurar a da sessão anterior -- ali a repartição já foi escolhida, e
        a fração guardada acompanha a largura sozinha, porque é fração e não pixel.

        **O piso da coluna de leitura é aplicado antes, e fora da guarda** (S-551, terceira
        rodada). Ele não é posição, é limite: os `QGroupBox` da leitura declaravam 266 px de mínimo
        -- **386** com o motor ligado, porque o texto das linhas entra na conta --, e numa aba de
        496 px nem esse mínimo nem o do tabuleiro cabiam. O `QSplitter` então não atendia nenhum
        dos dois, repartia 240/240, e o tabuleiro saía **36 px cortado**: sem a coluna `h`, sem as
        duas réguas, com a faixa de navegação em duas fileiras -- e sem volta, porque o mínimo do
        `QGroupBox` não desce quando o motor é desligado. Quem declara o piso da leitura é
        `sala_declarada`, e é ele que passa a valer aqui.

        **E o que a coluna pede vai junto na pergunta -- é a correção da quarta rodada.**
        `piso_da_leitura` responde "o quanto a leitura *pode* exigir"; `setMinimumWidth` é piso, e
        um piso aplicado cru também **sobe** o que a coluna pedia sozinha. Onde os `QGroupBox`
        declaravam 136 px -- a sala sem motor --, a régua os punha em 192, e o tabuleiro pagava a
        diferença sem ninguém ter pedido: medido a 1024x768, ele caiu de 298 para 245 px (301 para
        245 na pele fita, menos 18%), e a 1400x950 de 454 para 447. Quem mede o pedido é o widget,
        e por isso ele vai por argumento, como a esteira e a alça.
        """
        largura = sum(self.divisor.sizes())
        if largura <= 0:
            return
        esteira = self._esteira_da_coluna()
        alca = max(1, self.divisor.handleWidth())
        self.divisor_vertical.setMinimumWidth(
            piso_da_leitura(
                largura,
                minimo=self._caixa_minima_do_tabuleiro(),
                esteira=esteira,
                alca=alca,
                pedido=self.divisor_vertical.minimumSizeHint().width(),
            )
        )
        if self._divisor_escolhido:
            return
        alvo = fracao_para_o_tabuleiro(
            largura,
            self._altura_livre_para_o_tabuleiro(),
            minimo=self._caixa_minima_do_tabuleiro(),
            fracao_atual=self.fracao_do_divisor,
            esteira=esteira,
            alca=alca,
        )
        if abs(alvo - self.fracao_do_divisor) < 0.005:
            return
        esquerda = int(largura * alvo)
        self.divisor.setSizes([esquerda, max(1, largura - esquerda)])

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
        # **O motor pesa como o comentario desde a S-529**: com tres linhas de MultiPV e o rodape
        # de desempenho, o `1` de antes dava uma caixa de duas linhas com barra de rolagem enquanto
        # a lista de lances ficava com metade da altura vazia -- medido a 1400x950.
        for indice, peso in enumerate((3, 2, 2)[: coluna.count()]):
            coluna.setStretchFactor(indice, peso)
        self.divisor_vertical = coluna
        return coluna

    def _secao_do_motor(self, pai: QWidget) -> QGroupBox:
        """A seção do motor. Sem binário, ela simplesmente não existe (S-33).

        **A S-529 trocou os dois widgets de dentro.** A avaliação era um `QProgressBar` horizontal
        de 0 a 100 aqui embaixo -- ela subiu para a barra vertical ao lado do tabuleiro, que é onde
        se lê --, e as linhas do MultiPV eram um `QLabel` de texto cinza, do qual não havia caminho
        nenhum para pôr a segunda ou a terceira na árvore. Agora são `LinhasDoMotor`, e o clique
        insere. O que ficou aqui é o botão, a frase de estado e o rodapé de desempenho.
        """
        assert self._analyzer is not None
        caixa = QGroupBox(
            motor_declarado.titulo_da_secao(self._analyzer.name, self._analyzer.path.name), pai
        )
        self.caixa_do_motor = caixa
        pilha = QVBoxLayout(caixa)
        pilha.setContentsMargins(*(espaco.linha(),) * 4)

        # **Uma `BarraFluida` e não um `QHBoxLayout`** (S-551, terceira rodada): numa janela de
        # 1024 a coluna de leitura cede para o tabuleiro caber inteiro, e um `QHBoxLayout` não
        # reflui -- o botão saía com o rótulo cortado dos dois lados (`nalisar posiçã`). A fila põe
        # a frase de estado na linha de baixo, que é o que este widget existe para fazer.
        linha = BarraFluida(caixa)
        self.btn_analisar = QPushButton("Analisar posição", linha)
        self.btn_analisar.clicked.connect(self.analyse)
        tema.aplicar_papel(self.btn_analisar, estilos.NEUTRO)
        dica_em(
            self.btn_analisar,
            "Fica cinza enquanto o motor está pensando nesta posição, e volta quando\n"
            "ele responde. Sem motor UCI instalado, esta seção inteira não aparece.",
        )
        linha.adicionar(self.btn_analisar)
        self.lbl_motor = QLabel("", linha)
        linha.adicionar(self.lbl_motor)
        pilha.addWidget(linha)

        self.lbl_linha_do_motor = LinhasDoMotor(caixa)
        self.lbl_linha_do_motor.escolhida.connect(self.inserir_linha_do_motor)
        pilha.addWidget(self.lbl_linha_do_motor, 1)

        # **Profundidade e nós por segundo**, na linha de baixo (S-529). Eles estavam no `summary`
        # da frase de cima, misturados com a avaliação e o melhor lance; separados, o número que
        # diz *o quanto confiar* deixa de disputar espaço com o número que diz *quanto vale*.
        self.lbl_desempenho = QLabel("", caixa)
        tema.pintar(self.lbl_desempenho, "color", tokens.TEXTO_SECUNDARIO)
        dica_em(
            self.lbl_desempenho,
            "Profundidade em plies e nós por segundo. Os nós por segundo são o único número da\n"
            "tela que muda quando a opção «Núcleos» muda -- é por ele que se vê que ela pegou.",
        )
        pilha.addWidget(self.lbl_desempenho)
        return caixa

    def _mostrar_o_titulo_do_motor(self) -> None:
        """`Motor (Stockfish dev-20230303)`: o nome que o **motor** diz, e não o do arquivo (S-529).

        **O nome UCI chega depois da montagem, e é por isso que isto é um método.** O processo só
        sobe na primeira análise -- é decisão de `motor_das_preferencias`, e ela paga os 100 a
        300 ms só de quem pede avaliação --, então na hora de desenhar a seção `EngineAnalyzer.name`
        ainda responde o nome do executável. Chamado outra vez quando o motor responde, o título
        passa a distinguir dois Stockfish de versões diferentes, que é o que este item existe para
        fazer. Quem monta a frase é `ui/motor_declarado`.

        Só escreve quando muda: com a análise contínua isto passa aqui a cada ~800 ms, e um
        `setTitle` por resposta repintaria a moldura da caixa para dizer a mesma coisa.
        """
        motor = self._analyzer
        if motor is None:  # pragma: no cover - sem motor não há seção nem título
            return
        titulo = motor_declarado.titulo_da_secao(motor.name, motor.path.name)
        if titulo != self.caixa_do_motor.title():
            self.caixa_do_motor.setTitle(titulo)

    def showEvent(self, a0: QShowEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """**O teclado vem junto com a aba** (S-281): o `<Map>` do outro lado.

        Sem isto `←` só chega ao estudo depois de um clique no tabuleiro, e quem abre a aba e
        aperta a seta troca de diagrama. Dar o foco ao tabuleiro não tira a seta de dentro da caixa
        de comentário: ali quem responde é `acoes_proprias`, que devolve vazio.
        """
        super().showEvent(a0)
        self.tabuleiro.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tabuleiro.setFocus()
        # **E a régua da altura roda aqui, na primeira vez que a sala aparece** (S-551, segunda
        # rodada). Ela morava só no `resizeEvent`, e o crítico mediu o buraco: numa janela que
        # **nasce** grande a aba nunca é redimensionada depois de aparecer -- a montagem dá a
        # geometria final de uma vez --, então a regra rodava uma única vez, com o divisor ainda
        # invisível e de largura zero, e desistia ali. Medido a 1920×1080: o tabuleiro ficava em
        # 547 px com a régua respondendo 565, e a 2560×1440 em 738 com ela respondendo 800.
        # `_acomodar_o_tabuleiro` já não faz nada quando a alça foi escolhida, então chamá-la aqui
        # não atropela nem a pessoa nem a sessão anterior.
        self._acomodar_o_tabuleiro()

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

        **E o ECO** (S-534), que muda com o lance e por isso é atualizado aqui. O header `[ECO]` da
        partida vence -- é a classificação de quem a publicou --, e sem ele a tabela embutida
        classifica pela posição, o que faz a transposição chegar ao mesmo código. Custa ~0,5 ms por
        lance, medido; a tabela por posição é montada uma vez (84 ms) e fica em cache.
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
        self.lbl_eco.setText(
            eco.frase_do_tabuleiro(self.estudo.tabuleiro, self.estudo.jogo.headers.get("ECO", ""))
        )

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
            # A tabela de finais **antes** do motor, e na mesma thread (S-538): ela responde em
            # microssegundos e a resposta dela vence a do motor onde existe. Perguntar depois faria
            # a tela mostrar a estimativa e trocá-la um instante depois.
            self._resultado_de_tabela = self._perguntar_a_tabela(board)  # type: ignore[assignment]
            # **Quantas linhas é preferência desde a S-536**, e `CANDIDATOS_DO_MOTOR` é o que
            # a sala pede quando ela não diz nada -- a medida da S-286, no lugar em que ela
            # sempre esteve.
            avaliacoes = self._analyzer.analyse_multi(
                board, count=self._analyzer.multipv or CANDIDATOS_DO_MOTOR
            )
            self._motor_respondeu.emit(geracao, no, avaliacoes)
        except Exception as exc:  # noqa: BLE001 - o motor é binário de terceiro
            logger.warning("Falha na análise: %s", exc)
            self._motor_falhou.emit(geracao, str(exc))
        finally:
            self._motor_terminou.emit(geracao)

    def _perguntar_a_tabela(self, board: chess.Board) -> Any:
        """O `Resultado` exato deste final, ou `None`. Sem pasta configurada, sempre `None` (S-538).

        `deve_consultar` é o que impede a ida ao disco em toda posição de meio-jogo: a sala passa
        o tempo em posições de 20 peças, e nenhuma tabela cobre essas.

        Devolve o **resultado** e não a frase: a frase depende da cor a jogar, e montá-la aqui --
        na thread do motor -- obrigaria a passar mais um dado pela fronteira. Quem a escreve é
        `_mostrar_avaliacao`, que já tem o tabuleiro corrente na mão.
        """
        leitor = self._leitor_de_finais()
        if not finais_declarados.deve_consultar(
            chess.popcount(board.occupied), tem_pasta=leitor is not None
        ):
            return None
        assert leitor is not None
        achado = leitor.consultar(board)
        return achado if achado is not None and finais_declarados.vence_o_motor(achado.wdl) else None

    def _leitor_de_finais(self) -> Any:
        """O leitor de tablebases, aberto na primeira consulta. `None` quando não há pasta."""
        if self._finais is None:
            self._finais = tablebase.abrir(self._opcoes_do_motor().syzygy_path)
        return self._finais

    def _mostrar_avaliacao(
        self, geracao: int, no: chess.pgn.GameNode, avaliacoes: list[Evaluation]
    ) -> None:
        """Só escreve se ainda estamos no mesmo lance -- ver `analyse`.

        **A tabela de finais vence o motor onde ela responde** (S-538): a frase de cima passa a ser
        o resultado exato, e a barra vai para onde o resultado manda em vez de ficar na estimativa.
        As linhas candidatas continuam sendo as do motor -- a tabela diz o resultado, não a
        variante --, e é por isso que ela substitui uma parte da tela e não a seção inteira.
        """
        if geracao != self._geracao or not avaliacoes:
            return
        self._candidatos = list(avaliacoes)
        melhor = avaliacoes[0]
        brancas = bool(self.estudo.tabuleiro.turn)
        achado = self._resultado_de_tabela
        frase = (
            finais_declarados.frase_do_resultado(achado.wdl, achado.dtz, brancas_jogam=brancas)
            if achado is not None
            else ""
        )
        self.lbl_motor.setText(frase or melhor.display())
        self._pintar_a_barra(melhor, achado, brancas=brancas)
        self.lbl_linha_do_motor.mostrar(
            motor_declarado.linhas_do_motor(
                avaliacoes,
                numero_do_lance=self.estudo.tabuleiro.fullmove_number,
                brancas_jogam=bool(self.estudo.tabuleiro.turn),
            ),
            vazio="Sem lance legal nesta posição.",
        )
        self.lbl_desempenho.setText(
            motor_declarado.frase_de_desempenho(
                profundidade=melhor.depth, nos=melhor.nodes, nos_por_segundo=melhor.nps
            )
        )
        self._gravar_avaliacao(no, melhor)

    def _pintar_a_barra(self, melhor: Evaluation, achado: Any, *, brancas: bool) -> None:
        """Põe a barra lateral onde a avaliação -- ou o resultado da tabela -- manda.

        Com tabela, o número dentro da barra vira o **resultado** (`1-0`, `0-1`, `=`) e não uma
        avaliação: são os tokens do PGN, que não têm idioma e que qualquer enxadrista lê. Escrever
        `+12,80` ali seria pôr uma estimativa em cima de uma certeza.
        """
        if self.vantagem is None:  # pragma: no cover - sem motor não há barra
            return
        if achado is None:
            self.vantagem.definir(melhor.score_cp, melhor.mate_in, melhor.display())
            return
        exatos = finais_declarados.centipeoes_de(
            achado.wdl, brancas_jogam=brancas, teto=analise_declarada.TETO_DE_AVALIACAO
        )
        self.vantagem.definir(exatos, None, "=" if not exatos else ("1-0" if exatos > 0 else "0-1"))

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
        self.lbl_linha_do_motor.mostrar((), vazio=mensagem)

    def _terminar_analise(self, _geracao: int) -> None:
        self._analysing = False
        self.btn_analisar.setEnabled(True)
        # O processo já subiu (foi ele quem respondeu), então o `id name` do UCI existe: é aqui que
        # o título deixa de ser o nome do arquivo (S-529). Ver `_mostrar_o_titulo_do_motor`.
        self._mostrar_o_titulo_do_motor()
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
            self.lbl_desempenho.setText("")
            self.lbl_linha_do_motor.mostrar(())
            if self.vantagem is not None:
                self.vantagem.limpar()

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
            self._mostrar_cabecalho()
            self._aplicar_modo_da_barra()
        finally:
            self._montando = False
        # A geração muda **aqui**, e não em cada método de navegação: `refresh` é o único ponto por
        # onde toda mudança de nó passa, e é isso que faz a resposta atrasada do motor ser sempre
        # descartada -- inclusive a de um caminho de navegação que ainda não existe (S-285).
        self._geracao += 1
        self._candidatos = []
        self._analisar_se_continuo()
        # A árvore de aberturas acompanha a posição (S-535). Aqui, e não em cada método de
        # navegação, pela razão que a geração acima já usa: `refresh` é o único ponto por onde
        # toda mudança de nó passa. Fechada, ela não custa nada -- e a consulta em curso não é
        # atropelada: `definir_posicao` guarda o pedido e o refaz quando a thread volta.
        if self._arvore is not None and self._arvore.isVisible():
            self._arvore.definir_posicao(self.estudo.tabuleiro)

    def _aplicar_modo_da_barra(self) -> None:
        """Sem estudo, variante e exportar ficam cinza; treinando, a árvore fica cinza (S-527).

        A regra é de `ui/barra_da_sala.grupos_desligados`; o que o painel acrescenta são as duas
        condições que só ele sabe -- a da dobra (S-516) e a do recorte (S-347) --, e as duas se
        somam à do grupo em vez de substituí-la.
        """
        self.barra.aplicar_modo(
            barra_da_sala.modo(vazio=self.estudo.vazio(), treinando=self.btn_treino.isChecked()),
            {
                "dobrar_variantes": bool(self._variantes),
                "mostrar_diagrama": self.estudo.ancora.valida,
            },
        )

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
        """Põe a alça naquela fração. `0.0` deixa o peso do `QSplitter` decidir.

        **Uma fração guardada desliga a regra da S-551**, e é o que impede as duas de brigarem: a
        sessão anterior fechou com uma repartição, e ela é uma escolha -- ou da pessoa, que
        arrastou, ou da própria regra, que rodou na primeira abertura e teve o resultado gravado.
        Recalculá-la a cada `resize` sobrescreveria a primeira; nunca calculá-la deixaria a
        primeira abertura com o vazio que este item foi consertar.
        """
        if fracao <= 0.0:
            return
        self._divisor_escolhido = True
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

    def load_from_recognized(self) -> bool:
        """Abre o estudo do diagrama selecionado. Devolve se abriu: quem traz a aba para a frente
        depois de um duplo clique no visualizador precisa saber se há sala para mostrar."""
        posicao = self._posicao()
        if posicao is None or not posicao.valida():
            # Pré-condição no rodapé, e não em caixa de diálogo (S-164).
            self.set_status("Não há diagrama reconhecido para estudar.")
            return False
        self._abrir(posicao, origem="Base: OCR selecionado", status="Estudo do diagrama selecionado.")
        return True

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
        if self.vantagem is not None:
            # A barra pergunta a orientação no `paintEvent` (S-529), e ninguém a manda repintar ao
            # virar: sem isto ela fica com as brancas do lado errado até a resposta seguinte do
            # motor -- e numa sala sem análise contínua, indefinidamente.
            self.vantagem.update()
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
        """Põe a **primeira** linha do motor na árvore, a partir do lance corrente (S-286)."""
        self.inserir_linha_do_motor(1)

    def inserir_linha_do_motor(self, indice: int = 1) -> None:
        """Põe a `indice`-ésima linha do motor na árvore, a partir do lance corrente (S-286/S-529).

        **A procedência vai junto, no PGN.** O que a máquina sugeriu e o que a pessoa jogou não
        podem ficar indistinguíveis no arquivo -- é a regra 2 da SPEC_EDITOR aplicada a lance --, e
        a forma padrão de dizê-lo é o comentário de entrada da variante.

        **O índice existe desde a S-529**, e é o clique numa linha do MultiPV. Até aqui só a
        primeira era alcançável: as outras duas apareciam num `QLabel` e não havia caminho nenhum
        para pô-las na árvore -- o que anulava metade da razão de o MultiPV existir, que é comparar
        o lance do livro com os **candidatos** e não com o preferido.
        """
        if self._analyzer is None:
            self.set_status("Sem motor UCI instalado: ponha o Stockfish em engines/ e reabra.")
            return
        posicao = max(1, int(indice)) - 1
        melhor = self._candidatos[posicao] if posicao < len(self._candidatos) else None
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

    # ------------------------------------------- a partida inteira pelo motor (S-537)

    def analisar_partida(self) -> Any:
        """Passa a linha principal pelo motor, grava a avaliação e marca os erros (S-537).

        **É a pergunta do dia seguinte ao torneio**: *em que lance eu perdi?* A sala sabia avaliar
        uma posição desde a S-33 e gravar o número no lance desde a S-285; o que faltava era a
        passada inteira e a leitura dela em uma tela.

        Devolve a rodada, para o teste esperá-la. Quem decide profundidade é o diálogo; quem
        classifica e desenha é `ui/analise_da_partida.py` e `qt/analise_da_partida.py`.
        """
        from chess_diagram_ocr.qt import analise_da_partida as qt_analise

        if self._analyzer is None:
            self.set_status("Sem motor UCI instalado: ponha o Stockfish em engines/ e reabra.")
            return None
        if self._analise_da_partida is not None and self._analise_da_partida.ocupado:
            self.set_status("A partida já está sendo analisada.")
            return None
        _fens, passos = analise_declarada.percurso(self.estudo.jogo)
        if not passos:
            self.set_status("Não há lance na linha principal para analisar.")
            return None
        pedido = qt_analise.DialogoDaProfundidade(self, lances=len(passos))
        if pedido.exec() != QDialog.DialogCode.Accepted:
            return None
        rodada = qt_analise.analisar_com_dialogo(
            self,
            analisador=self._analyzer,
            jogo=self.estudo.jogo,
            profundidade=pedido.profundidade(),
            busy=self._busy,
        )
        rodada.terminou.connect(self._chegou_a_analise_da_partida)
        rodada.falhou.connect(lambda mensagem, _erro: self.set_status(f"A análise da partida falhou: {mensagem}"))
        self._analise_da_partida = rodada
        return rodada

    def _chegou_a_analise_da_partida(self, avaliados: Any) -> Any:
        """Grava `[%eval]` e o símbolo em cada lance, e abre o relatório (S-537).

        **O símbolo é NAG e não cor de tela**, e é o que faz a análise sobreviver ao arquivo: um
        `??` gravado como `$4` aparece na lista de lances pelo caminho que já existe, vai para o
        PGN e é lido por qualquer programa de xadrez. Uma marca só de tela morreria ao fechar.

        `_marcar_sujo` uma vez no fim, e não por lance: quarenta chamadas empilhariam quarenta
        passos de desfazer para uma operação que a pessoa mandou fazer uma vez.
        """
        from chess_diagram_ocr.qt import analise_da_partida as qt_analise

        cancelada = bool(self._analise_da_partida is not None and self._analise_da_partida.cancelada)
        marcados = self._marcar_os_lances(avaliados)
        self.refresh()
        if avaliados:
            self._marcar_sujo(historico=False, da_maquina=True)
        self.set_status(analise_declarada.frase_final(len(avaliados or []), marcados, cancelado=cancelada))
        if not avaliados:
            return None
        return qt_analise.JanelaDaAnalise(self, avaliados, ir_para=self.ir_para_o_ply)

    def _marcar_os_lances(self, avaliados: Any) -> int:
        """Escreve a avaliação e o símbolo nos nós da linha principal. Devolve quantos ganharam
        símbolo.

        O casamento é **por posição na linha principal**, e não por nó guardado: a árvore pode ter
        mudado enquanto o motor pensava, e um nó guardado apontaria para um lance que saiu dela.

        **A posição já matada não recebe `[%eval]`** (S-537): o UCI responde `score mate 0` ali, o
        `engine` normaliza para `±1` -- que a barra precisa --, e o que saía no arquivo era um
        `[%eval #1]` numa posição em que o mate **já aconteceu**. Quem decide é `grava_avaliacao`.

        O que se pula é a **avaliação**, e não o nó: a posição que acaba a partida também pode ser
        um afogamento, e afogar no lugar de matar é justamente o `??` que esta passada existe para
        achar. O símbolo continua sendo escrito, e é do símbolo que a análise vive.
        """
        no: Any = self.estudo.raiz
        marcados = 0
        for lance in avaliados or []:
            if not no.variations:
                break
            no = no.variations[0]
            if analise_declarada.grava_avaliacao(lance):
                pontuacao = (
                    chess.engine.Mate(lance.mate_em)
                    if lance.mate_em is not None
                    else chess.engine.Cp(int(lance.centipeoes))
                )
                no.set_eval(chess.engine.PovScore(pontuacao, chess.WHITE))
            codigo = analise_declarada.NAG_DE_JUIZO.get(lance.juizo)
            if codigo is not None:
                no.nags = estudo_mod.alternar_nag(set(no.nags) - {codigo}, codigo)
                marcados += 1
        return marcados

    def ir_para_o_ply(self, ply: int) -> None:
        """Leva o tabuleiro ao `ply`-ésimo lance da linha principal (S-537).

        É o que faz o gráfico e a lista de erros serem clicáveis: o relatório existe para achar
        onde a partida virou, e um relatório que não leva até lá deixa a busca para o dedo.
        """
        self.gravar_comentario()
        no: Any = self.estudo.raiz
        for _passo in range(max(0, int(ply))):
            if not no.variations:
                break
            no = no.variations[0]
        self.estudo.no = no
        self.refresh()

    # ----------------------------------------- as opções do motor, sem reiniciar (S-536)

    def _opcoes_do_motor(self) -> EngineSettings:
        """As preferências do motor como estão no disco. Arquivo ausente dá os padrões (S-32)."""
        return load_settings(self._caminho_das_preferencias).engine

    def opcoes_do_motor(self) -> QDialog | None:
        """Abre o formulário das opções do motor e aplica o que ele devolver (S-536).

        **Existe com e sem motor**, e é a única ação do grupo Motor que existe sem: numa máquina em
        que a procura automática não achou binário nenhum, este é o caminho para dizer onde ele
        está -- e escondê-lo justamente ali seria escondê-lo de quem precisa dele.

        A gravação é atômica e vale para a próxima sessão; a aplicação é imediata e não reinicia
        nada. Quem sabe o que cada mudança faz com o processo é `plano_de_aplicacao`.
        """
        from chess_diagram_ocr.qt.preferencias import DialogoDoMotor

        antes = self._opcoes_do_motor()
        dialogo = DialogoDoMotor(self, opcoes=antes)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return dialogo
        self.aplicar_opcoes_do_motor(antes, dialogo.valores())
        return dialogo

    def aplicar_opcoes_do_motor(self, antes: EngineSettings, depois: EngineSettings) -> Any:
        """Grava as preferências e põe o motor de acordo, fora da linha de eventos (S-536).

        Separada de `opcoes_do_motor` porque é a parte afirmável sem abrir diálogo -- e porque é
        ela que a fotografia e o teste exercitam.
        """
        from chess_diagram_ocr.qt.preferencias import MotorVivo

        preferencias = load_settings(self._caminho_das_preferencias)
        try:
            save_settings(self._caminho_das_preferencias, replace(preferencias, engine=depois))
        except OSError as erro:  # pragma: no cover - disco cheio ou pasta somente leitura
            logger.warning("As preferências do motor não puderam ser gravadas: %s", erro)
        # O leitor de finais é reaberto na próxima consulta: a pasta pode ter mudado.
        if self._finais is not None:
            self._finais.close()
            self._finais = None
        if self._motor_vivo is None:
            self._motor_vivo = MotorVivo(self, analisador=self._analyzer)
            self._motor_vivo.aplicado.connect(self._motor_aplicado)
            self._motor_vivo.falhou.connect(lambda mensagem, _erro: self._motor_aplicado(None, mensagem))
        self._motor_vivo.aplicar(antes, depois)
        return self._motor_vivo

    def _motor_aplicado(self, motor: Any, frase: str) -> None:
        self.trocar_de_motor(motor)
        self.set_status(frase)

    @property
    def analisador(self) -> EngineAnalyzer | None:
        """O motor que a sala está usando **agora**. É por ele que a janela o fecha ao sair.

        A janela guarda o motor que ela construiu, e a sala pode tê-lo trocado (S-536): perguntar
        aqui é o que faz o `closeEvent` fechar o processo que está vivo, e não o que morreu.
        """
        return self._analyzer

    def trocar_de_motor(self, novo: EngineAnalyzer | None) -> None:
        """Troca o motor da sala e acomoda a tela ao que passou a existir (S-536).

        **Três casos, e só o terceiro custa alguma coisa.** Trocar um motor por outro é atualizar
        o título da seção -- o objeto muitas vezes é o mesmo, com outro binário dentro. Perder o
        motor esconde a seção e a barra lateral, como se ele nunca tivesse existido (S-33). Ganhar
        um motor numa sala que abriu sem nenhum é o caso que obriga a montar a seção agora e a
        **remontar a fila**: uma `QAction` não muda de barra depois de criada, e sem a remontagem o
        grupo Motor continuaria ausente até a próxima abertura -- que é o "reiniciar" que este item
        veio tirar.

        A barra lateral **não** nasce depois: ela mora dentro do arranjo da coluna do tabuleiro, e
        recriá-lo mexeria na repartição que a S-551 calcula. A promessa da S-536 é o motor sem
        reiniciar; a barra chega junto com ele na abertura seguinte, e a seção já mostra tudo.
        """
        tinha = self._analyzer is not None
        self._analyzer = novo
        if novo is None and tinha:
            self.btn_continua = None
            self.caixa_do_motor.hide()
        elif novo is not None and tinha:
            # O motor que a troca entrega já está aberto (`MotorVivo` chama `start`), então aqui o
            # título sai com o nome UCI e não com o do binário.
            self._mostrar_o_titulo_do_motor()
            self.caixa_do_motor.show()
        elif novo is not None and not tinha:
            self._secao_do_motor(self.divisor_vertical)
        if (novo is not None) != tinha:
            self._remontar_a_barra()
        self.refresh()

    def _remontar_a_barra(self) -> None:
        """Refaz a fila com (ou sem) o grupo do motor, guardando os interruptores que estavam ligados."""
        antiga = self.barra
        marcados = {
            nome: antiga.acoes[nome].isChecked()
            for nome in (barra_da_sala.SEGUIR_OCR, "modo_treino", "mostrar_diagrama", "dobrar_variantes")
            if nome in antiga.acoes
        }
        nova = self._montar_barra()
        self._fora.replaceWidget(antiga, nova)
        antiga.setParent(None)
        antiga.deleteLater()
        self.barra = nova
        for nome, ligado in marcados.items():
            acao = nova.acoes.get(nome)
            if acao is not None:
                acao.blockSignals(True)
                acao.setChecked(ligado)
                acao.blockSignals(False)

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

    def buscar_partidas(self) -> QDialog | None:
        """Abre o formulário de busca sobre o índice por nome (S-533).

        **A outra pergunta.** `partidas_da_posicao` responde pela posição que está no tabuleiro, e
        só por ela -- e lê o cache, que só conhece o que já foi perguntado. Esta pergunta não nasce
        do tabuleiro: *as partidas de Carlsen em 2019 com Elo acima de 2700 na Najdorf*. Quem
        responde é `games_index.buscar`, e a posição corrente entra como filtro **opcional**.

        O diálogo é guardado e reusado: ele não é modal e tem uma `Tarefa` dentro, e destruir o
        primeiro para abrir o segundo destruiria um `QThread` em curso -- que derruba o processo
        sem exceção. Reabrir só atualiza a posição, que é a única coisa dele que envelhece.
        """
        from chess_diagram_ocr.games_db import database_paths
        from chess_diagram_ocr.qt import busca_de_partidas as qt_busca

        if self._busca is None:
            bases = tuple(self._bases()) or tuple(database_paths())
            if not bases:
                self.set_status("Não há base de partidas (.pgn) para procurar.")
                return None
            dialogo = qt_busca.DialogoDeBusca(self.window(), bases=bases)
            dialogo.partida_escolhida.connect(self.abrir_partida_da_base)
            dialogo.indice_pedido.connect(self.indexar_base)
            self._busca = dialogo
        self._busca.definir_posicao(self.estudo.tabuleiro.board_fen())
        self._busca.show()
        self._busca.raise_()
        return self._busca

    def arvore_de_aberturas(self) -> QDialog | None:
        """A árvore de aberturas da posição corrente: que lances a base joga daqui (S-535).

        **A terceira pergunta à base, e ela é a de quem estuda uma abertura.**
        `partidas_da_posicao` diz *quais* partidas passam por aqui (e só sabe o que já foi
        perguntado, pelo cache); `buscar_partidas` responde a um formulário de seis campos. Esta
        responde *o que se joga daqui*, com o número de partidas, o resultado, o Elo e o ano de
        cada lance -- e ela lê um índice por **posição**, que é o que a S-535 construiu.

        O diálogo é guardado e reusado pelas razões de `buscar_partidas`, e mais uma: ele segue a
        posição da sala a cada `refresh`.
        """
        from chess_diagram_ocr.games_db import database_paths
        from chess_diagram_ocr.qt import arvore_de_aberturas as qt_arvore

        if self._arvore is None:
            bases = tuple(self._bases()) or tuple(database_paths())
            if not bases:
                self.set_status("Não há base de partidas (.pgn) para a árvore de aberturas.")
                return None
            dialogo = qt_arvore.DialogoDaArvore(self.window(), bases=bases)
            dialogo.lance_escolhido.connect(self.jogar_da_arvore)
            dialogo.partidas_pedidas.connect(self.partidas_da_arvore)
            dialogo.construcao_pedida.connect(self.construir_a_arvore)
            self._arvore = dialogo
        self._arvore.definir_posicao(self.estudo.tabuleiro)
        self._arvore.show()
        self._arvore.raise_()
        return self._arvore

    def jogar_da_arvore(self, san: str) -> bool:
        """Joga na árvore de estudo o lance escolhido na árvore de aberturas. Devolve se jogou.

        **Reinterpreta o SAN no tabuleiro da sala**, e não recebe um `chess.Move`: o lance veio de
        uma consulta que rodou numa thread sobre uma cópia, e um `Move` daquela cópia é um par de
        casas sem dono. Ilegal aqui quer dizer que a posição andou entre a consulta e o clique --
        a frase diz isso em vez de jogar outra coisa.

        Quem redesenha a árvore de aberturas é o `refresh` de `push_move`, e não esta função: a
        posição mudaria pelas setas do teclado do mesmo jeito.
        """
        try:
            lance = self.estudo.tabuleiro.parse_san(san)
        except (ValueError, AssertionError):
            self.set_status(f"{san} não é um lance legal na posição que está no tabuleiro agora.")
            return False
        self.push_move(lance)
        return True

    def partidas_da_arvore(self, filtro: Any) -> Any:
        """Abre a busca da S-533 já preenchida com a posição da árvore e o ECO dela.

        É o "mesmo gesto da busca" que o item pede: a lista de partidas que chegam a esta posição
        é a tabela que já existe, com a paginação e a thread que já existem -- e não uma segunda
        lista de partidas neste programa.
        """
        # `Any` e nao `DialogoDeBusca`: o tipo concreto so existe atras do `import` tardio de
        # `buscar_partidas` -- nomea-lo aqui traria o PyQt do dialogo para o topo deste arquivo.
        dialogo: Any = self.buscar_partidas()
        if dialogo is not None:
            dialogo.aplicar_filtro(filtro)
        return dialogo

    def construir_a_arvore(self) -> Any:
        """Constrói a árvore de aberturas com barra e Cancelar, sem sair da janela (S-535).

        A forma é a de `indexar_base` (S-532) e pela mesma razão: a saída de "o arquivo não existe"
        tem de ser um comando da janela e não uma frase mandando abrir um terminal. A diferença é
        o que o cancelamento custa -- aqui a passada inteira é descartada, porque meia árvore dá
        percentagem sobre a metade que se leu, e ela pareceria certa.
        """
        from chess_diagram_ocr.games_db import database_paths
        from chess_diagram_ocr.qt import arvore_de_aberturas as qt_arvore

        if self._construtor_da_arvore is not None and self._construtor_da_arvore.ocupado:
            self.set_status("A árvore de aberturas já está sendo construída.")
            return None
        bases = tuple(self._bases()) or tuple(database_paths())
        if not bases:
            self.set_status("Não há base de partidas (.pgn) para construir a árvore.")
            return None
        busy = self._busy if self._busy is not None else getattr(self.window(), "busy", None)
        construtor = qt_arvore.construir_com_dialogo(self.window(), bases, busy=busy)
        construtor.terminou.connect(lambda feito: self.set_status(qt_arvore.frase_final(feito)))
        construtor.falhou.connect(
            lambda mensagem, _excecao: self.set_status(f"A árvore de aberturas falhou: {mensagem}")
        )
        self._construtor_da_arvore = construtor
        return construtor

    def abrir_partida_da_base(self, caminho: Any, offset: int) -> bool:
        """Põe na mesa a partida que a busca escolheu, lida direto do byte dela (S-533).

        **É o que o índice existe para permitir**: `Achado` guarda em que arquivo e em que byte a
        partida começa, e ler dali custa um `seek` -- não a passada de minutos que a busca por
        posição paga. Se a leitura não devolver partida, o índice está adiantado em relação ao
        arquivo (alguém reescreveu o `.pgn`), e a frase diz isso em vez de abrir meia partida.

        O estudo aberto é guardado na sala antes da troca, como em `_aceitar_colado`: escolher uma
        partida na lista não pode custar a análise que estava na mesa.
        """
        from chess_diagram_ocr import estudo_partidas, games_index

        partida = games_index.partida_em(Path(caminho), int(offset))
        if partida is None or not partida.movetext:
            self.set_status(
                "A partida escolhida não foi encontrada onde o índice diz que ela está. "
                "Refaça o índice: a base mudou depois da última rodada."
            )
            return False
        novo, motivo = estudo_mod.colar(estudo_partidas.como_pgn(partida))
        if novo is None:
            self.set_status(f"A partida escolhida não pôde ser lida: {motivo}")
            return False
        if not self._confirmar_abandono("abrir a partida escolhida na busca"):
            return False
        self.seguir_ocr.setChecked(False)
        self.sala.guardar(self.estudo)
        nomes = f"{partida.headers.get('White', '?')} - {partida.headers.get('Black', '?')}"
        self._trocar_de_estudo(novo, f"Base: {nomes}")
        self.set_status(f"{nomes}: {novo.contagem_de_lances()} lance(s) da base.")
        return True

    def indexar_base(self) -> None:
        """Constrói o índice por nome da base, com barra e Cancelar, sem sair da janela (S-532).

        **A fiação que a S-532 deixou pendente**: o indexador existia e ninguém o chamava -- a janela
        continuava mandando abrir um terminal. A ação mora no grupo Base da barra da sala (dentro do
        "Mais": indexa-se uma vez por torneio acrescentado) e no menu Estudo, pelo catálogo.

        As bases são as que a sala já consulta (`bases_de_partidas`) ou, sem elas, a pasta padrão
        (`database_paths`). O `busy` é o da janela quando ela o passou; senão, o que a janela que
        nos contém tiver -- é o mesmo registro, e uma segunda rodada em curso é recusada pelo
        indexador. A frase final vai para `set_status`, que é o rodapé da aba **e** o da janela.
        """
        from chess_diagram_ocr.games_db import database_paths
        from chess_diagram_ocr.qt import indice_da_base

        if self._indexador is not None and self._indexador.ocupado:
            self.set_status("O índice da base já está sendo construído.")
            return
        bases = tuple(self._bases()) or tuple(database_paths())
        if not bases:
            self.set_status("Não há base de partidas (.pgn) para indexar.")
            return
        busy = self._busy if self._busy is not None else getattr(self.window(), "busy", None)
        indexador = indice_da_base.indexar_com_dialogo(self.window(), bases, busy=busy)
        indexador.terminou.connect(lambda resultado: self.set_status(indice_da_base.frase_final(resultado)))
        indexador.falhou.connect(lambda mensagem, _excecao: self.set_status(f"O índice da base falhou: {mensagem}"))
        self._indexador = indexador

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

    def exportar_estudo_epub(self) -> None:
        """`.epub` **porque o leitor de livro repagina** (S-542).

        Os três de cima entregam um arquivo de texto marcado, e a página é do programa que o abrir;
        o PDF sai com a página cravada. O EPUB é o meio-termo que um livro de xadrez pede: o
        diagrama vai em SVG e acompanha o corpo de letra que a pessoa escolher no leitor.
        """
        from chess_diagram_ocr import epub

        self._exportar_empacotado(".epub", "EPUB", epub.exportar_estudo_epub)

    def exportar_estudo_docx(self) -> None:
        """`.docx` **porque o texto continua sendo escrito** (S-543).

        O RTF já abre no Word, e a diferença é o que se faz depois: o DOCX sai com estilos de
        título nomeados, sumário e o diagrama como imagem numa moldura -- é o formato de quem vai
        continuar escrevendo por cima da análise, e não só lê-la.
        """
        from chess_diagram_ocr import docx_saida

        self._exportar_empacotado(".docx", "DOCX", docx_saida.exportar_estudo_docx)

    def _exportar_empacotado(self, extensao: str, formato: str, exportador: Callable[..., Any]) -> None:
        """O caminho comum do EPUB e do DOCX: escolher o destino, gravar, dizer o que saiu.

        **Os dois não passam por `text/exportacao.py`, e é a mesma razão do PDF**: aquele módulo
        entrega texto marcado, e estes três entregam um **pacote** -- um zip com manifesto,
        imagens e metadados. Quem monta o pacote são `epub.py` e `docx_saida.py`, que já contam o
        que escreveram; aqui só se escolhe o arquivo.

        **A falha vai para a barra de status e não para uma caixa**, como no PDF: a pessoa acabou
        de escolher o destino e clicou em gravar, então ela está olhando para esta tela, e a mesma
        linha que diria "3 capítulo(s)" diz por que não deu (S-164).
        """
        destino, _filtro = QFileDialog.getSaveFileName(
            self,
            f"Exportar o estudo para {formato}",
            str(self._pasta_inicial / f"{self._nome_sugerido()}{extensao}"),
            f"{formato} (*{extensao});;Todos (*.*)",
        )
        if not destino:
            return
        self.gravar_comentario()
        caminho = Path(destino)
        try:
            relatorio = exportador(self.estudo, caminho)
        except OSError as erro:
            self.set_status(f"Não foi possível gravar {caminho.name}: {erro}")
            return
        self.set_status(relatorio.resumo())

    # ------------------------------------------------------- a folha e o lote (S-544/S-545)

    def exportar_estudo_pdf(self) -> None:
        """`.pdf` **porque a página é decidida aqui** (S-545).

        Os três de cima entregam o estudo como texto marcado, e quem pagina é o programa que
        abrir o arquivo. O PDF sai já paginado como livro -- margem, cabeçalho, número de página,
        e a quebra que não separa o diagrama do lance que o pede --, e o diagrama vai em vetor.
        Por isso ele não passa por `text/exportacao.py`: aquele módulo não tem página.

        **A falha vai para a barra de status, e não para uma caixa** -- ao contrário dos três
        vizinhos. É a régua da S-164 e a catraca de `tests/test_ui_retorno_modal.py`: a pessoa
        acabou de escolher o destino e clicou em gravar, então ela está olhando para esta tela, e
        a mesma linha que diria "6 página(s) em …" diz por que não deu. Uma caixa a mais aqui
        seria interrupção para informar o que o rodapé informa sem parar ninguém.
        """
        from chess_diagram_ocr.qt import impressao_do_estudo as qt_impressao
        from chess_diagram_ocr.ui.impressao_do_estudo import frase_do_pdf

        destino, _filtro = QFileDialog.getSaveFileName(
            self,
            "Exportar o estudo para PDF",
            str(self._pasta_inicial / f"{self._nome_sugerido()}.pdf"),
            "PDF (*.pdf);;Todos (*.*)",
        )
        if not destino:
            return
        self.gravar_comentario()
        caminho = Path(destino)
        try:
            paginas = qt_impressao.pdf_do_estudo(self.estudo, caminho)
            tamanho = caminho.stat().st_size
        except OSError as erro:
            self.set_status(f"Não foi possível gravar {caminho.name}: {erro}")
            return
        self.set_status(frase_do_pdf(str(caminho), paginas, tamanho))

    def imprimir_estudo(self) -> Any:
        """A pré-visualização paginada, e a impressora atrás dela (S-545).

        **Prévia e não impressão direta.** A quebra de página é a decisão que o programa toma por
        quem imprime, e ela tem de ser conferível antes de gastar folha -- é a mesma razão de a
        prévia do lote de diagramas existir. A caixa de escolher impressora vem da própria prévia.
        """
        from chess_diagram_ocr.qt import impressao_do_estudo as qt_impressao

        self.gravar_comentario()
        return qt_impressao.abrir_previa_de_impressao(self, self.estudo)

    def exportar_diagramas_em_lote(self) -> Any:
        """Os diagramas desta sala como arquivos soltos, um por posição (S-544).

        **A origem é a sala quando ela tem estudos, e o estudo aberto quando não.** A sala *é* o
        conjunto de diagramas deste livro (S-270), e é ele que quem diagrama noutro programa quer
        -- quinhentos arquivos de uma vez, nomeados pela página. Um estudo avulso, colado ou
        digitado, não está em sala nenhuma, e aí o lote é ele.
        """
        from chess_diagram_ocr.qt.lote_de_diagramas import abrir_lote_de_diagramas
        from chess_diagram_ocr.ui.lote_de_diagramas import de_estudos, do_estudo

        self.gravar_comentario()
        guardados = self.sala.estudos()
        if guardados:
            itens = de_estudos(guardados, origem=Path(self.sala.documento).stem)
            origem = f"{len(guardados)} estudo(s) da sala deste livro."
        else:
            itens = do_estudo(self.estudo)
            origem = "O estudo aberto."
        if not itens:
            self.set_status("Não há diagrama para exportar: o estudo não pede nenhum.")
            return None
        return abrir_lote_de_diagramas(
            self, itens=itens, origem=origem, pasta=self._pasta_inicial, busy=self._busy
        )

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

    # ----------------------------------------------------------- treinar (S-290/S-541)

    def alternar_treino(self) -> None:
        """Liga e desliga o modo de treino: a linha some, e o tabuleiro cobra o lance.

        **A sessão zera aqui, e o placar do livro não** (S-541). Até a S-541 os dois contadores
        eram os mesmos, e desligar o treino -- que é o gesto declarado para guardar um lance que se
        quis jogar -- apagava a tarde inteira. Agora o que zera é a sessão; o que o livro acumulou
        está no disco desde o primeiro lance.
        """
        self.btn_treino.setChecked(not self.btn_treino.isChecked())
        self.btn_treino.setText(
            comandos.rotulo_alternado("modo_treino")
            if self.btn_treino.isChecked()
            else comandos.rotulo_de_botao("modo_treino")
        )
        self.placar.zerar_sessao()
        self.refresh()
        if self.btn_treino.isChecked():
            self.set_status("Treino: jogue o lance da linha. O que vem depois está escondido.")
        else:
            self.set_status("Treino desligado.")

    @property
    def placar(self) -> placar_mod.Placar:
        """O placar do treino, lido do disco na primeira vez que alguém treina (S-541).

        Preguiçoso porque a sala é montada em toda janela e em dezenas de testes, e nenhum deles
        treina: carregar o `placar.json` no `__init__` faria toda montagem tocar o disco por causa
        de uma frase que quase nunca aparece.
        """
        if self._placar is None:
            self._placar = placar_mod.carregar(caminho=self._caminho_do_placar())
        return self._placar

    def _caminho_do_placar(self) -> Path:
        return self._pasta_de_treino / placar_mod.CAMINHO_PADRAO.name

    def _mostrar_placar(self) -> None:
        if not self.btn_treino.isChecked() or self._placar is None:
            self.lbl_placar.setText("")
            return
        livro = self.estudo.ancora.documento or self.sala.documento
        self.lbl_placar.setText(
            treino_declarado.frase_do_placar(self._placar.sessao, self._placar.do_livro(livro))
        )

    def _treinar(self, move: chess.Move) -> None:
        """Um lance jogado com o treino ligado. **A árvore não muda** (S-290/S-541).

        O gabarito é o nó seguinte da linha, e ele já está lá: o estudo tem tudo de que o treino
        precisa. **Errar não cria variante**, e o caminho de guardar o lance é declarado na própria
        frase: desligar o treino.

        **O veredicto chega na hora e o preço chega depois** (S-541). Se o lance é o da linha, não
        há nada a perguntar. Se não é, ele ainda pode valer o mesmo -- e responder isso custa duas
        buscas do motor, que não cabem na linha de eventos. A frase do rodapé é escrita duas vezes:
        uma dizendo que o lance não é o da linha, outra dizendo quanto ele custou. Sem motor, a
        primeira é a única, e ela continua sendo verdade.
        """
        esperado = self.estudo.no.variations[0] if self.estudo.no.variations else None
        if esperado is None:
            self.set_status("Fim da linha: não há lance a adivinhar aqui.")
            return
        antes = self.estudo.tabuleiro.copy(stack=False)
        jogado = antes.san(move)
        gabarito = antes.san(esperado.move)
        if move == esperado.move:
            self.estudo.no = esperado
            self.refresh()
            self._contar_no_treino(treino_declarado.classificar_o_lance(jogado, gabarito), jogado, gabarito)
            return
        # **O redesenho desfaz o lance na tela.** O modelo do tabuleiro jogou sobre a cópia dele, e
        # sem isto a pessoa fica olhando uma posição que a árvore não tem -- o defeito que a S-290
        # deixou passar porque o caminho de erro não redesenhava nada.
        self.refresh()
        if not self._medidor_da_perda().pedir(antes, move, (jogado, gabarito, bool(antes.turn))):
            self._contar_no_treino(treino_declarado.classificar_o_lance(jogado, gabarito), jogado, gabarito)
            return
        self.set_status(f"{jogado} não é o lance da linha: perguntando ao motor quanto custou…")

    def _medidor_da_perda(self) -> Any:
        """O `PerdaDoLance` da sala, criado no primeiro erro. `pedir` recusa sem motor (S-541)."""
        if self._perda_do_lance is None:
            from chess_diagram_ocr.qt.painel_de_treino import PerdaDoLance

            self._perda_do_lance = PerdaDoLance(self, analisador=self._analyzer)
            self._perda_do_lance.pronta.connect(self._chegou_a_perda)
            self._perda_do_lance.falhou.connect(self._nao_veio_a_perda)
        return self._perda_do_lance

    def _chegou_a_perda(self, ficha: Any, antes: int, depois: int) -> None:
        jogado, gabarito, brancas = ficha
        julgamento = treino_declarado.classificar_o_lance(
            jogado, gabarito, antes=int(antes), depois=int(depois), brancas=bool(brancas)
        )
        self._contar_no_treino(julgamento, jogado, gabarito)

    def _nao_veio_a_perda(self, ficha: Any, _mensagem: str) -> None:
        jogado, gabarito, _brancas = ficha
        self._contar_no_treino(treino_declarado.classificar_o_lance(jogado, gabarito), jogado, gabarito)

    def _contar_no_treino(self, julgamento: Any, jogado: str, gabarito: str) -> None:
        """Conta o lance nos dois placares e grava o do livro **agora** (S-541).

        Uma gravação por lance e não por sessão, ao contrário do baralho de revisão: o arquivo tem
        uma linha por livro e alguns bytes, e o que se perde numa queda é justamente a sessão que
        ninguém vai repetir. É a decisão inversa da de `qt/painel_de_treino.JanelaDeTreino`, e a
        diferença é o tamanho do que se grava.
        """
        livro = self.estudo.ancora.documento or self.sala.documento
        self.placar.registrar(livro, julgamento.resultado, perda=julgamento.perda)
        self._mostrar_placar()
        self.set_status(treino_declarado.frase_do_resultado(julgamento, jogado, gabarito))
        try:
            placar_mod.gravar(self.placar, caminho=self._caminho_do_placar())
        except OSError as erro:  # pragma: no cover - disco cheio ou arquivo em uso
            logger.warning("O placar do treino não pôde ser gravado: %s", erro)

    # -------------------------------------------------- táticas e agenda (S-539/S-540)

    def extrair_taticas(self) -> Any:
        """Casa os diagramas deste livro com a solução impressa e grava a coleção (S-539).

        **O livro é o da sala, e não um `filedialog`.** A sala já está aberta sobre um diagrama
        dele, a aba de texto já leu folhas dele, e perguntar de novo qual é o arquivo seria
        desconhecer o que a janela inteira está mostrando.

        A varredura carrega o classificador por conta própria, do caminho padrão -- é o mesmo que
        `cvoff-scan` faz, e é o preço de a extração rodar fora do `OcrService` (que está sob o lock
        da S-31 servindo à página exibida). Dezessete megabytes de modelo por alguns minutos.
        """
        from chess_diagram_ocr.qt import painel_de_treino

        livro = self.estudo.ancora.documento or self.sala.documento
        if not livro or not Path(livro).exists():
            self.set_status("Abra um livro na sala antes de extrair as táticas dele.")
            return None
        if self._extrator is not None and self._extrator.ocupado:
            self.set_status("A extração de táticas deste livro já está em curso.")
            return None
        rodada = painel_de_treino.extrair_com_dialogo(
            self, Path(livro), analisador=self._analyzer, busy=self._busy
        )
        rodada.terminou.connect(partial(self._chegaram_as_taticas, str(livro)))
        rodada.falhou.connect(lambda mensagem, _e: self.set_status(f"A extração falhou: {mensagem}"))
        self._extrator = rodada
        return rodada

    def _chegaram_as_taticas(self, livro: str, extracao: Any) -> None:
        """Grava o que a extração achou e diz o número -- inclusive quando ele é ruim."""
        if extracao is None:
            self.set_status("Extração de táticas cancelada.")
            return
        try:
            taticas_arquivo.gravar(livro, extracao.exercicios, pasta=self._pasta_das_taticas())
        except OSError as erro:
            self.set_status(f"Os exercícios não puderam ser gravados: {erro}")
            return
        self.set_status(extracao.resumo())

    def _pasta_das_taticas(self) -> Path:
        return self._pasta_de_treino / taticas_arquivo.PASTA_PADRAO.name

    def _caminho_da_revisao(self) -> Path:
        return self._pasta_de_treino / revisao_arquivo.CAMINHO_PADRAO.name

    def _gravar_o_baralho(self, caminho: Path, baralho: dict[str, Any]) -> None:
        """A gravação que a janela de treino chama ao fechar. Método e não `lambda`: um `lambda`
        não tem nome para o critério de aceite citar, e a S-546 já registrou o argumento."""
        revisao_arquivo.gravar(baralho, caminho=caminho)

    def treinar_a_agenda(self) -> Any:
        """Abre a fila de hoje da repetição espaçada (S-540).

        Sem exercício nenhum extraído, a janela **não abre**: uma tela de treino vazia não diz o
        que fazer, e a frase diz -- o comando que a preenche está ao lado, no mesmo menu.
        """
        from chess_diagram_ocr.qt.painel_de_treino import JanelaDeTreino

        exercicios = taticas_arquivo.carregar_tudo(pasta=self._pasta_das_taticas())
        if not exercicios:
            self.set_status(
                'Não há exercício extraído ainda. Use "Táticas do livro" com um livro aberto.'
            )
            return None
        caminho = self._caminho_da_revisao()
        janela = JanelaDeTreino(
            self,
            exercicios=exercicios,
            baralho=revisao_arquivo.carregar(caminho=caminho),
            placar=self.placar,
            analisador=self._analyzer,
            gravar=partial(self._gravar_o_baralho, caminho),
        )
        janela.fechada.connect(self._mostrar_placar)
        self._treino = janela
        janela.show()
        return janela

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


class _RotuloElidido(QLabel):
    """Um `QLabel` de uma linha que corta o próprio texto com `...` quando ele não cabe (S-530).

    **Elidir no momento de escrever não funciona**, e foi medido: `_mostrar_cabecalho` roda dentro
    de `refresh`, que é chamado na montagem -- ali o rótulo ainda tem a largura de fábrica, e a
    frase saía como `Jogadores nã...` numa faixa de 494 px. Quem sabe a largura é o rótulo, e ele
    só a sabe no `resizeEvent` dele.

    A dica carrega a frase inteira: o nome que não coube continua alcançável sem abrir o diálogo,
    que é o que um `...` sozinho não dá.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self._inteiro = ""

    def definir_texto(self, texto: str) -> None:
        self._inteiro = str(texto)
        self.setToolTip(self._inteiro)
        self.setVisible(bool(self._inteiro))
        self._reescrever()

    def texto_inteiro(self) -> str:
        """O que a frase diz antes de ser cortada. É por ele que o teste pergunta."""
        return self._inteiro

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._reescrever()

    def _reescrever(self) -> None:
        largura = self.width()
        if largura <= 0:
            self.setText(self._inteiro)
            return
        metrica = QFontMetrics(self.font())
        self.setText(metrica.elidedText(self._inteiro, Qt.TextElideMode.ElideRight, largura))


class _JanelaDoCabecalho(QDialog):
    """O formulário dos nove headers da partida (S-530).

    **Um `QComboBox` para o resultado, e campo livre para o resto.** `1:0`, `1-0 ` e `1–0` com
    travessão são o que se digita sem querer, e qualquer um faz o PGN ser recusado por quem o ler;
    os outros oito não têm forma fechada -- nome de jogador e de torneio são o que o livro imprimiu.

    Quem diz quais são os campos, em que ordem e o que um campo vazio grava é
    `ui/cabecalho_da_partida.py`. Este arquivo só desenha.
    """

    def __init__(
        self,
        pai: QWidget,
        headers: Any,
        gravar: Callable[[dict[str, str]], None],
    ) -> None:
        super().__init__(pai)
        self.setWindowTitle(cabecalho_da_partida.TITULO)
        self._gravar = gravar
        self.campos: dict[str, QWidget] = {}
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.setSpacing(espaco.folga())

        grade = QGridLayout()
        grade.setHorizontalSpacing(espaco.folga())
        grade.setVerticalSpacing(espaco.linha())
        valores = cabecalho_da_partida.valores_para_o_formulario(headers)
        # **O campo estreito fica na linha do anterior**, e não na seguinte: `Brancas [nome] Elo
        # [2720]` é uma pergunta só, e separá-los em duas linhas dobraria a altura do formulário
        # para dizer a mesma coisa. `linha` só avança em campo largo.
        linha, coluna = -1, 0
        for campo in cabecalho_da_partida.CAMPOS:
            if campo.estreito and linha >= 0:
                coluna = 2
            else:
                linha += 1
                coluna = 0
            grade.addWidget(QLabel(campo.rotulo, self), linha, coluna)
            editor: QWidget
            if campo.escolhas:
                caixa = QComboBox(self)
                caixa.addItems(campo.escolhas)
                atual = valores.get(campo.chave) or campo.escolhas[0]
                caixa.setCurrentIndex(max(0, caixa.findText(atual)))
                editor = caixa
            else:
                texto = QLineEdit(valores.get(campo.chave, ""), self)
                if campo.estreito:
                    texto.setMaximumWidth(8 * tema.altura_de_linha_atual())
                editor = texto
            if campo.dica:
                dica_em(editor, campo.dica)
            grade.addWidget(editor, linha, coluna + 1)
            self.campos[campo.chave] = editor
        grade.setColumnStretch(1, 1)
        pilha.addLayout(grade)

        # **Os dois botões com texto próprio**, e não `StandardButton.Save`: o texto padrão do Qt
        # é "Save"/"Cancel" em inglês, e a janela inteira fala português. É a forma que
        # `qt/dialogos.py` já usa nos dois diálogos de base.
        botoes = QDialogButtonBox(parent=self)
        botoes.addButton("Gravar", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        # O nome de um jogador não cabe no que a grade pede: `Capablanca, José Raúl` saía cortado
        # num diálogo de 328 px. A altura continua sendo a que os nove campos pedem.
        self.resize(max(520, self.sizeHint().width()), self.sizeHint().height())
        self.show()

    def valores(self) -> dict[str, str]:
        """O que está nos campos agora, por chave de PGN."""
        lidos: dict[str, str] = {}
        for chave, editor in self.campos.items():
            if isinstance(editor, QComboBox):
                lidos[chave] = editor.currentText()
            elif isinstance(editor, QLineEdit):
                lidos[chave] = editor.text()
        return lidos

    def _confirmar(self) -> None:
        valores = self.valores()
        self.accept()
        self._gravar(valores)


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
