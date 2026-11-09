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
   cresce a cada `refresh`, e a resposta que chegar com geração velha é descartada (S-285).
3. **A gravação por inatividade é um `QTimer` de disparo único**, e o `adiar=False` da S-345 vira
   "não reinicie o relógio": com a análise contínua ligada, o motor escreve a cada ~800 ms, e cada
   escrita reagendando fazia o prazo nunca vencer -- a sala **nunca** era gravada.
4. **O `QSplitter` guarda a fração por `sizes()`**, e não por `sashpos`.

**E a barra de cima é uma fila desde a S-527.** Eram três `BarraFluida` com 28 botões de texto, que
a 715 px quebravam em quatro fileiras. Quem decide grupo, o que é principal, ícone, dica e quem cabe
na largura é `ui/barra_da_sala.py`; `qt/barra_da_sala.py` mede e executa. Os botões que o resto deste
arquivo chama pelo nome -- `btn_dobra`, `btn_recorte`, `btn_treino`, `btn_continua`, `seguir_ocr` --
são `QAction`s daquela barra, e respondem aos mesmos `setChecked`, `setText` e `setEnabled`.

**E desde a S-866 o painel é composição.** Eram 3.708 linhas; o que tem estado próprio saiu com ele
-- `self.motor` (`qt/sala_motor.py`), `self.partidas`, `self.treino` e `self.leiaute` --, e os widgets
e as funções de arquivo foram para `qt/sala_*.py`. Aqui ficam a árvore, a navegação, a anotação, a
sala no disco, e um método por comando do catálogo, que delega quando o trabalho é de uma parte.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chess
import chess.engine
import chess.pgn
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QResizeEvent, QShowEvent
from PyQt6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import eco, estudo_arquivo
from chess_diagram_ocr import estudo as estudo_mod
from chess_diagram_ocr.arquivo_do_dono import GravacaoRecusada, Leitura, Lida, gravavel
from chess_diagram_ocr.config import DEFAULT_PDF_DIR
from chess_diagram_ocr.engine import EngineAnalyzer
from chess_diagram_ocr.estudo import Ancora, Estudo, PosicaoDeEstudo, Sala
from chess_diagram_ocr.fen_utils import is_valid_fen, reading_index_from_square, square_from_reading_index
from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import sala_arquivos as arquivos
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.barra_da_sala import BarraDaSala
from chess_diagram_ocr.qt.dialogos import perguntar_recusando
from chess_diagram_ocr.qt.motor import BarraDeAvaliacao
from chess_diagram_ocr.qt.rotulo import CampoQueAvisaQueContinua
from chess_diagram_ocr.qt.sala_cabecalho import CabecalhoDaPartida, JanelaDoCabecalho
from chess_diagram_ocr.qt.sala_coluna import LADO_DO_ICONE_DA_SALA, FaixaDeNavegacao, RecorteDoDiagrama
from chess_diagram_ocr.qt.sala_leiaute import LeiauteDaSala
from chess_diagram_ocr.qt.sala_lista import ListaDeLances
from chess_diagram_ocr.qt.sala_motor import MotorDaSala
from chess_diagram_ocr.qt.sala_partidas import PartidasDaBase
from chess_diagram_ocr.qt.sala_treino import TreinoDaSala
from chess_diagram_ocr.qt.tabuleiro_de_jogo import TabuleiroDeJogo
from chess_diagram_ocr.settings import DEFAULT_SETTINGS_PATH
from chess_diagram_ocr.ui import (
    atalhos,
    barra_da_sala,
    cabecalho_da_partida,
    comandos,
    espaco,
    tipografia,
)
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.historico import Historico
from chess_diagram_ocr.ui.sala_declarada import (
    ACOES_PROPRIAS,
    COMANDOS_DA_ABA,
    Sincronia,
    decidir_sincronia,
    nags_oferecidos,
)

if TYPE_CHECKING:
    from PyQt6.QtPrintSupport import QPrintPreviewDialog

    from chess_diagram_ocr.qt.analise_da_partida import AnalisadorDaPartida
    from chess_diagram_ocr.qt.lote_de_diagramas import DialogoDoLote
    from chess_diagram_ocr.qt.painel_de_treino import ExtratorDeTaticas, JanelaDeTreino

logger = logging.getLogger(__name__)


__all__ = ["LADO_DO_ICONE_DA_SALA", "PainelDeEstudo"]


class PainelDeEstudo(QWidget):
    """Sala de estudo: um estudo por diagrama, com árvore de variantes e anotação."""

    estado = pyqtSignal(str)
    """Uma frase para a barra de status desta aba. Ela sempre carrega a vez a jogar junto."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        posicao: Callable[[], PosicaoDeEstudo | None] = lambda: None,
        pasta_inicial: Path = DEFAULT_PDF_DIR,
        analyzer: EngineAnalyzer | None = None,
        pasta_de_estudos: Path | None = None,
        recorte: Callable[[Ancora], Any] = lambda _ancora: None,
        linha_impressa: Callable[[Ancora], str] = lambda _ancora: "",
        abrir_pagina: Callable[[Ancora], bool] = lambda _ancora: False,
        bases_de_partidas: Callable[[], Sequence[Path]] = tuple,
        para_o_texto: Callable[[str], bool] = lambda _linha: False,
        caminho_do_cache: Path | None = None,
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
        self._recorte = recorte
        self._linha_impressa = linha_impressa
        self._abrir_pagina = abrir_pagina
        self._para_o_texto = para_o_texto
        self._busy = busy
        """O registro de operações longas da janela. As partes que rodam passadas longas o recebem
        também; aqui ele serve ao lote de diagramas."""
        self._pasta_de_estudos = pasta_de_estudos

        # **As partes com estado próprio** (S-866). Nascem antes da montagem porque ela
        # pergunta ao motor se há seção a desenhar, e cada uma é um `QObject` filho desta sala: o
        # slot ligado a um método delas cai junto com a sala, como caía quando era método dela.
        self.motor = MotorDaSala(
            self, analyzer=analyzer, caminho_das_preferencias=caminho_das_preferencias, busy=busy
        )
        self.partidas = PartidasDaBase(
            self, bases=bases_de_partidas, caminho_do_cache=caminho_do_cache, busy=busy
        )
        self.treino = TreinoDaSala(self, pasta_de_treino=pasta_de_treino, busy=busy)
        self.leiaute = LeiauteDaSala(self)
        self._sujo = False
        self._comentario_do_no: chess.pgn.GameNode | None = None
        self._montando = False

        self.sala = Sala()
        self._leitura_da_sala: Leitura[Sala] | None = None
        """De onde a sala veio e se ela pode voltar para lá (S-812). `None`: sala sem livro."""
        self.estudo = Estudo.de_posicao(PosicaoDeEstudo())
        self._historico = Historico(self.estudo.para_pgn())
        self._edicao = 0

        self._relogio_de_gravacao = QTimer(self)
        self._relogio_de_gravacao.setSingleShot(True)
        self._relogio_de_gravacao.timeout.connect(self.salvar_agora)

        self._montar()
        self.leiaute.definir_fracao_do_tabuleiro(0.0)
        self.refresh()
        self.set_status("Clique em uma peça para estudar.")
        atalhos.conferir_dono(self, "PainelDeEstudo")

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.margem_da_aba(),) * 4)
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
        self.divisor.splitterMoved.connect(self.leiaute.divisor_movido_a_mao)
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
        barra = BarraDaSala(self, com_motor=self.motor.has_engine, executar=self.executar)
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

    def executar(self, acao: str) -> None:
        """Roda o método que o catálogo liga àquela ação. Levanta para ação que a aba não tem.

        O interruptor "Seguir OCR" não é comando do catálogo, e o método dele vem de
        `barra_da_sala.METODOS_PROPRIOS` -- a mesma forma de tabela, para o mesmo motivo (S-280).
        """
        metodo = COMANDOS_DA_ABA.get(acao) or barra_da_sala.METODOS_PROPRIOS[acao]
        getattr(self, metodo)()

    def _esquerda(self) -> QWidget:
        coluna = QWidget(self.divisor)
        pilha = QVBoxLayout(coluna)
        pilha.setContentsMargins(0, 0, espaco.linha(), 0)

        # **O cabeçalho da partida acima do tabuleiro** (S-530), como no ChessBase. Os nove
        # headers existiam -- `Estudo.de_posicao` escreve cinco, um `.pgn` traz os nove -- e nenhum
        # aparecia na tela: quem abrisse Capablanca-Alekhine via um tabuleiro sem nome, sem torneio
        # e sem resultado. Quem decide o que a frase diz é `ui/cabecalho_da_partida.py`.
        self.cabecalho = CabecalhoDaPartida(self, lado_do_icone=LADO_DO_ICONE_DA_SALA, editar=self.editar_cabecalho)
        pilha.addWidget(self.cabecalho)

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
                coluna, caixa=self.leiaute.caixa_do_tabuleiro, virado=lambda: self.estudo.invertido
            )
            if self.motor.has_engine
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
            self.leiaute.faixa_do_tabuleiro = faixa
        self.navegacao = FaixaDeNavegacao(self, executar=self.executar)
        pilha.addWidget(self.navegacao)

        # A miniatura do diagrama (S-282). Ela nasce escondida: estudo sem âncora não mostra
        # espaço reservado para o que não existe.
        self.recorte_label = RecorteDoDiagrama(coluna, recorte=self._recorte, ampliar=self.ampliar_recorte)
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

        # **Um campo que avisa quando a FEN não cabe** (F9-C7, §4.5): a 1024 o campo tem 286 px
        # e uma FEN de meio-jogo pede 504, e o que sumia sumia em silêncio. Ver
        # `qt/rotulo.CampoQueAvisaQueContinua`.
        self.campo_fen = CampoQueAvisaQueContinua(self.estudo.tabuleiro.fen(), coluna)
        # **O nome não pode ser a FEN** (F9-C2): `QLineEdit.text()` aqui devolve
        # `"rnbqkbnr/pppppppp/8/8/..."`, e era isso que o leitor de tela anunciava como o nome do
        # campo -- 56 caracteres de conteúdo no lugar de duas palavras de identidade.
        self.campo_fen.setAccessibleName("FEN da posição em estudo")
        self.campo_fen.setFont(tema.fonte_atual(tipografia.DADO))
        self.campo_fen.setCursorPosition(0)
        self.campo_fen.returnPressed.connect(self.apply_fen)
        pilha.addWidget(self.campo_fen)
        return coluna

    # ----------------------------------------------------- o cabeçalho da partida (S-530)

    def _mostrar_cabecalho(self) -> None:
        """Põe na faixa o que os headers dizem. A faixa é `qt/sala_cabecalho.CabecalhoDaPartida`."""
        self.cabecalho.mostrar(self.estudo.jogo.headers)

    def editar_cabecalho(self) -> QDialog:
        """Abre o formulário dos nove campos. O que ele gravar entra no `Ctrl+Z` da sala."""
        return JanelaDoCabecalho(self, self.estudo.jogo.headers, self._gravar_cabecalho)

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
        self.leiaute.acomodar_o_tabuleiro()
        if self.vantagem is not None:
            self.vantagem.update()

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
        self.lista = ListaDeLances(lances)
        self.lista.anchorClicked.connect(self._clique_na_lista)
        dentro.addWidget(self.lista)

        anotacao = QGroupBox("Comentário do lance", coluna)
        dentro = QVBoxLayout(anotacao)
        dentro.setContentsMargins(*(espaco.linha(),) * 4)
        self.comentario = QTextEdit(anotacao)
        self.comentario.setAccessibleName("Comentário do lance")
        # O `Tab` sai da caixa, e sair grava (abaixo). Guardado pela caixa, ele escrevia uma
        # tabulação no comentário e a tecla nunca passava dali: quem anda pelo teclado não
        # alcançava o resto da sala (OCR_UI ciclo 2, fase 5, crítico do ciclo 4, portão `teclado`).
        self.comentario.setTabChangesFocus(True)
        # **Piso e não altura fixa** (S-519): com o divisor, quem decide a altura é quem lê. As
        # quatro linhas de antes eram o teto e o piso ao mesmo tempo, e a caixa onde se escreve a
        # frase do livro era a menor da coluna.
        self.comentario.setMinimumHeight(3 * tema.altura_de_linha_atual())
        # Grava ao **sair** do campo, e não a cada tecla: um sinal por letra faria a lista de
        # lances ser redesenhada trinta vezes por frase, e o cursor pularia junto.
        self.comentario.focusOutEvent = self._saiu_do_comentario  # type: ignore[method-assign,assignment]
        dentro.addWidget(self.comentario)

        if self.motor.has_engine:
            self.motor.montar_secao(coluna)
        # A altura de fábrica reparte por uso, e não em partes iguais: a lista é a maior, o
        # comentário cabe um parágrafo, e o motor fica no que a seção dele pede.
        # **O motor pesa como o comentario desde a S-529**: com tres linhas de MultiPV e o rodape
        # de desempenho, o `1` de antes dava uma caixa de duas linhas com barra de rolagem enquanto
        # a lista de lances ficava com metade da altura vazia -- medido a 1400x950.
        for indice, peso in enumerate((3, 2, 2)[: coluna.count()]):
            coluna.setStretchFactor(indice, peso)
        self.divisor_vertical = coluna
        return coluna

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
        # `acomodar_o_tabuleiro` já não faz nada quando a alça foi escolhida, então chamá-la aqui
        # não atropela nem a pessoa nem a sessão anterior.
        self.leiaute.acomodar_o_tabuleiro()

    # -------------------------------------------------------------------------------- lista

    def _redesenhar_lista(self) -> None:
        """Refaz a lista de lances (`qt/sala_lista.py`); treinando, cortada no lance corrente."""
        self.lista.desenhar(self.estudo, treinando=self.btn_treino.isChecked())

    def _mostrar_lance_corrente(self) -> None:
        """O lance corrente e a vez, na faixa sob o tabuleiro (S-517).

        **O texto sai dos mesmos trechos que a lista desenha** -- ver `ListaDeLances.texto_do_lance`.

        **E o ECO** (S-534), que muda com o lance e por isso é atualizado aqui. O header `[ECO]` da
        partida vence -- é a classificação de quem a publicou --, e sem ele a tabela embutida
        classifica pela posição, o que faz a transposição chegar ao mesmo código. Custa ~0,5 ms por
        lance, medido; a tabela por posição é montada uma vez (84 ms) e fica em cache.
        """
        self.navegacao.lbl_lance.setText(self.lista.texto_do_lance(self.estudo.caminho()))
        self.navegacao.lbl_vez.setText("brancas jogam" if self.estudo.tabuleiro.turn else "pretas jogam")
        self.navegacao.lbl_eco.setText(
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
        caminho = self.lista.caminho_do_trecho(int(endereco.removeprefix("trecho:")))
        if caminho is None:
            return
        self.gravar_comentario()
        if not self.estudo.ir_para(caminho):
            self.set_status("Aquele lance não existe mais.")
        self.refresh()

    # ------------------------------------------------------------------ dobrar variantes (S-516)

    def _alternar_uma_dobra(self, indice: int) -> None:
        """Dobra ou desdobra a variante cujo `(` foi clicado. **A identidade é o caminho.**"""
        if not self.lista.alternar_uma_dobra(indice):  # pragma: no cover - a lista foi refeita entre o desenho e o clique
            return
        self._redesenhar_lista()
        self._atualizar_botao_da_dobra()

    def alternar_dobra(self) -> None:
        """Dobra **todas** as variantes, ou desdobra todas se já houver alguma dobrada.

        **É o caminho descobrível**, e o clique no `(` é o atalho de quem já viu que ele responde.
        Sem um comando, dobrar seria um gesto que só se acha por acidente -- e o estudo em que ele
        vale é justamente o grande, aberto de um PGN, onde a pessoa quer esconder antes de ler.

        Dobrar não muda a árvore nem o PGN: é vista. `edicao` não sobe, e o `Ctrl+Z` não a enxerga.
        """
        frase = self.lista.alternar_todas()
        self._redesenhar_lista()
        self._atualizar_botao_da_dobra()
        self.set_status(frase)

    def _atualizar_botao_da_dobra(self) -> None:
        """Cinza sem variante, e com o rótulo do que de fato está na tela -- como a S-347 fez
        com o botão do recorte, e pela mesma razão: um botão que alterna sobre o que não existe
        troca de texto sem que nada mude."""
        self.btn_dobra.setEnabled(bool(self.lista.variantes))
        self.btn_dobra.setChecked(bool(self.lista.dobradas))
        self.btn_dobra.setText(
            comandos.rotulo_alternado("dobrar_variantes")
            if self.lista.dobradas
            else comandos.rotulo_de_botao("dobrar_variantes")
        )

    # ------------------------------------------- o motor, em qt/sala_motor.py (S-866)

    def analyse(self) -> None:
        self.motor.analyse()

    def alternar_analise_continua(self) -> None:
        self.motor.alternar_analise_continua()

    def variante_do_motor(self) -> None:
        """Põe a **primeira** linha do motor na árvore, a partir do lance corrente (S-286)."""
        self.motor.inserir_linha_do_motor(1)

    def analisar_partida(self) -> AnalisadorDaPartida | None:
        return self.motor.analisar_partida()

    def opcoes_do_motor(self) -> QDialog | None:
        return self.motor.opcoes_do_motor()

    # ------------------------------------------------------------------------------- estado

    def set_status(self, texto: str = "") -> None:
        turno = "brancas" if self.estudo.tabuleiro.turn else "pretas"
        # **Um separador só na interface** (F9-C12). O produto declara `" · "` em dez lugares
        # (`ui/estado_do_rodape`, `ui/strings`, `qt/painel_de_resultado`, `qt/painel_da_galeria`,
        # `qt/campo`, `qt/paleta`) e usava `" | "` em quatro, dois deles desenhados na tela em
        # toda pele e largura. `tests/unit/ui/test_dialogos.py` cobra a grafia única.
        frase = f"{texto} · vez: {turno}" if texto else f"Vez: {turno}"
        self.lbl_status.setText(frase)
        self.estado.emit(frase)

    def _mostrar_fen_do_comeco(self) -> None:
        """Rola o campo da FEN para o **inicio**, que e a parte que identifica a posicao.

        **Achado olhando as capturas do ciclo 6, a 1280x800.** `QLineEdit.setText` deixa o cursor
        no fim, e o campo passa a mostrar o fim: numa janela de 1280 a FEN inicial aparece como
        `qkbnr/pppppppp/...` -- as tres primeiras casas somem, **sem reticencia e sem nenhum
        sinal**. Quem le a FEN na tela para copiar a mao copia uma FEN invalida. A 1920 o campo
        cabe inteiro e nada disso aparece, que e por que nenhuma medida de layout pegou: nao ha
        rotulo espremido nem controle fora da janela, so texto rolado.

        O comeco vale mais que o fim: `rnbqkbnr/...` e a colocacao das pecas, e o rabo
        (`w KQkq - 0 1`) e o mesmo em quase toda posicao de abertura.
        """
        self.campo_fen.setCursorPosition(0)

    def refresh(self) -> None:
        """Põe na tela o que o estudo diz: posição, setas, lista, comentário e FEN."""
        self._montando = True
        try:
            self.campo_fen.setText(self.estudo.tabuleiro.fen())
            # **O começo, e não o fim** (S-552, quinta rodada). `setText` deixa o cursor no fim, e
            # um `QLineEdit` estreito rola até ele: a 1024 a caixa mostrava `2pP1N2/...` no lugar de
            # `1q1r1nk1/...`. Ela é rolável, e é justamente o que torna o defeito silencioso --
            # quem olha lê uma posição que não é a da tela. O primeiro campo da FEN é a fileira 8,
            # que é a metade do tabuleiro que se confere primeiro. Ver `_mostrar_fen_do_comeco`.
            self._mostrar_fen_do_comeco()
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
            self.treino.mostrar_placar()
            self._mostrar_cabecalho()
            self._aplicar_modo_da_barra()
        finally:
            self._montando = False
        # O motor e a árvore de aberturas acompanham o nó corrente aqui, e não em cada método de
        # navegação: `refresh` é o único ponto por onde toda mudança de nó passa (S-285, S-535).
        self.motor.posicao_mudou()
        self.partidas.acompanhar(self.estudo.tabuleiro)

    def _aplicar_modo_da_barra(self) -> None:
        """Sem estudo, variante e exportar ficam cinza; treinando, a árvore fica cinza (S-527).

        A regra é de `ui/barra_da_sala.grupos_desligados`; o que o painel acrescenta são as duas
        condições que só ele sabe -- a da dobra (S-516) e a do recorte (S-347) --, e as duas se
        somam à do grupo em vez de substituí-la.
        """
        self.barra.aplicar_modo(
            barra_da_sala.modo(vazio=self.estudo.vazio(), treinando=self.btn_treino.isChecked()),
            {
                "dobrar_variantes": bool(self.lista.variantes),
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
        self._leitura_da_sala = estudo_arquivo.carregar(documento, pasta=self._pasta_de_estudos)
        self.sala = self._leitura_da_sala.valor
        if not isinstance(self._leitura_da_sala, Lida):
            self.set_status(self._leitura_da_sala.mensagem)
        elif len(self.sala):
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
        if not self._sujo or not self.sala.documento or self._leitura_da_sala is None:
            return None
        try:
            caminho = estudo_arquivo.gravar(gravavel(self._leitura_da_sala).com(self.sala))
        except GravacaoRecusada as recusa:
            self.set_status(str(recusa))
            return None
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
        return perguntar_recusando(
            self,
            "Estudo em andamento",
            f"Este estudo tem {self.estudo.contagem_de_lances()} lance(s) {onde}."
            f"\n\nQuer mesmo {o_que}?",
        )

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
            self.treino.treinar(move)
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
        return perguntar_recusando(
            self,
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
        self.navegacao.lbl_simbolo.setText(" ".join(estudo_mod.simbolo_de_nag(codigo) for codigo in nags))

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
        """A miniatura do diagrama âncora, ou nada. Ver `qt/sala_coluna.RecorteDoDiagrama`."""
        self.recorte_label.mostrar(self.estudo.ancora, ligado=self.btn_recorte.isChecked())

    def ampliar_recorte(self) -> QDialog | None:
        """O recorte no tamanho em que o modelo o leu, numa janela própria (S-282)."""
        janela = self.recorte_label.ampliado(self.estudo.ancora, self)
        if janela is None:
            self.set_status("Não há recorte deste diagrama para ampliar.")
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

    # ------------------------------- as partidas da base, em qt/sala_partidas.py (S-866)

    def partidas_da_posicao(self) -> QDialog | None:
        return self.partidas.partidas_da_posicao()

    def buscar_partidas(self) -> QDialog | None:
        return self.partidas.buscar_partidas()

    def arvore_de_aberturas(self) -> QDialog | None:
        return self.partidas.arvore_de_aberturas()

    def indexar_base(self) -> None:
        self.partidas.indexar_base()

    def abrir_no_livro(self, jogo: Any, caminho: tuple[int, ...], *, origem: str) -> bool:
        """Põe na mesa a partida do PGN do livro inteira, posicionada no nó do diagrama (S-592).

        É a análise do autor a partir dali: as variantes que o texto comenta estão todas na árvore,
        e andar para a frente leva ao próximo diagrama. A partida chega com `SourcePDF`, `Page` e
        `Diagram` do diagrama, e é por eles que a sala a guarda junto dos outros estudos do livro.
        """
        novo = estudo_mod.Estudo.de_jogo(jogo)
        if not novo.ir_para(caminho):
            self.set_status("O lance do diagrama não está mais na partida do livro.")
            return False
        if not self._confirmar_abandono("abrir a partida do livro"):
            return False
        self.seguir_ocr.setChecked(False)
        self.sala.guardar(self.estudo)
        self._trocar_de_estudo(novo, origem)
        self.set_status(f"{origem}: a árvore do livro, no lance do diagrama.")
        return True

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

    # --------------------------------- entrada e saída, em qt/sala_arquivos.py (S-866)

    def colar_estudo(self) -> QDialog:
        return arquivos.colar_estudo(self)

    def abrir_pgn(self) -> None:
        arquivos.abrir_pgn(self)

    def exportar_estudo_md(self) -> None:
        """`.md` **porque ele diffa**: dois estudos da mesma posição comparam linha a linha."""
        arquivos.exportar_texto_marcado(self, ".md")

    def exportar_estudo_html(self) -> None:
        """`.html` **porque ele abre**: é o formato para mandar a análise para alguém."""
        arquivos.exportar_texto_marcado(self, ".html")

    def exportar_estudo_rtf(self) -> None:
        """`.rtf` porque o Word abre -- e sem dependência nova nenhuma (S-252)."""
        arquivos.exportar_texto_marcado(self, ".rtf")

    def exportar_estudo_epub(self) -> None:
        """`.epub` **porque o leitor de livro repagina** (S-542)."""
        from chess_diagram_ocr import epub

        arquivos.exportar_empacotado(self, ".epub", "EPUB", epub.exportar_estudo_epub)

    def exportar_estudo_docx(self) -> None:
        """`.docx` **porque o texto continua sendo escrito** (S-543)."""
        from chess_diagram_ocr import docx_saida

        arquivos.exportar_empacotado(self, ".docx", "DOCX", docx_saida.exportar_estudo_docx)

    def exportar_estudo_pdf(self) -> None:
        arquivos.exportar_estudo_pdf(self)

    def imprimir_estudo(self) -> QPrintPreviewDialog:
        return arquivos.imprimir_estudo(self)

    def exportar_diagramas_em_lote(self) -> DialogoDoLote | None:
        return arquivos.exportar_diagramas_em_lote(self)

    def levar_para_o_texto(self) -> None:
        arquivos.levar_para_o_texto(self)

    # ------------------------------------------ o treino, em qt/sala_treino.py (S-866)

    def alternar_treino(self) -> None:
        self.treino.alternar_treino()

    def extrair_taticas(self) -> ExtratorDeTaticas | None:
        return self.treino.extrair_taticas()

    def treinar_a_agenda(self) -> JanelaDeTreino | None:
        return self.treino.treinar_a_agenda()

    # --------------------------------------------------------------------------------- PGN

    def pgn_payload(self) -> str:
        return self.estudo.para_pgn()

    def save_pgn(self) -> None:
        arquivos.save_pgn(self)


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

