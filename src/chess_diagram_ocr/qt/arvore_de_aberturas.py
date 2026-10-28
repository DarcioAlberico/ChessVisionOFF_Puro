"""A janela da árvore de aberturas: a tabela, a barra de resultado e o clique que anda (S-535).

**O que só existe deste lado.** A tabela, a barra de três segmentos, a thread e a passada que
constrói o arquivo. Quem decide o que a árvore contém, em que ordem, o que vira travessão e o que
vira frase é `ui/arvore_de_aberturas.py`; quem responde é `arvore_de_aberturas.consultar`.

**O clique simples joga o lance, e aqui ele é diferente da busca.** Em `qt/busca_de_partidas.py` o
clique escolhe uma linha e o **duplo** abre a partida, porque lá o clique e o gesto seguinte são
coisas diferentes -- olhar a lista e trocar o que está na mesa. Aqui o clique **é** a navegação: a
árvore é uma pilha de posições e clicar num lance é descer um degrau, exatamente como no explorador
do Lichess. O caminho de volta é o "lance anterior" da sala, que já existe e já é uma tecla.

O teclado continua andando pela lista sem jogar nada -- `itemClicked` não dispara com as setas --,
e `Enter` joga a linha marcada.

**A consulta vai para uma `Tarefa`.** Ela é uma sonda de chave primária e custa milissegundos com o
arquivo quente; com ele frio, é a primeira leitura de um SQLite de mais de um gigabyte, e a fila de
eventos não pode esperar pelo disco. É a mesma razão da S-533.

**A árvore recalcula a cada posição, e a posição chega por `definir_posicao`.** O diálogo não
conhece a sala: ele recebe um `chess.Board` e devolve um SAN por sinal. Quem joga o lance é quem
tem a árvore de estudo.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import chess
from PyQt6.QtCore import QModelIndex, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.arvore_de_aberturas import (
    DEFAULT_TREE_PATH,
    PROFUNDIDADE,
    construir,
    consultar,
)
from chess_diagram_ocr.eco import classificar
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabela import TabelaQt
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.ui import espaco, estilos, tokens
from chess_diagram_ocr.ui.arvore_de_aberturas import (
    COLUNAS,
    CONTORNO_DA_BARRA,
    CORES_DA_BARRA,
    EM_BUSCA,
    TINTAS_DA_BARRA,
    Linha,
    busca_da_posicao,
    e_aviso,
    frase_da_construcao,
    frase_do_fim,
    linhas,
    perde_trabalho_ao_fechar,
    resumo,
)
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken

logger = logging.getLogger(__name__)

__all__ = ["BarraDeResultado", "ConstrutorDaArvore", "DialogoDaArvore", "construir_com_dialogo", "frase_final"]

COLUNA_DA_BARRA = 2
"""Qual coluna de `COLUNAS` recebe a barra desenhada. Terceira: `resultado`.

Índice e não busca pela chave porque é o que o `setItemDelegateForColumn` do Qt pede, e porque uma
coluna a mais em `COLUNAS` que mudasse este número quebraria o teste que o afirma -- que é
exatamente o aviso que se quer."""

COLUNA_DA_ORDEM = 1
"""A coluna por onde a tabela nasce ordenada: `partidas`, decrescente.

**Sem isto a ordem decidida em `ui/` não chegava à tela**, e a foto de 1400×950 o mostrou: com
`setSortingEnabled(True)` o Qt reordena pelo indicador corrente a cada preenchimento, e o
indicador de fábrica é a primeira coluna -- a tabela da Najdorf saía `Rg1, Rb1, Qf3, … a3`, ordem
alfabética do SAN. A ordem por frequência é o item (ver o cabeçalho de `ui/arvore_de_aberturas`),
e o clique no cabeçalho continua trocando-a: o que se fixa é de onde ela parte."""

PAPEL_DAS_FRACOES = Qt.ItemDataRole.UserRole + 1
"""Onde as três frações viajam dentro do item. `UserRole` já é da posição original da linha
(`qt/tabela.preencher`), e sobrescrevê-la faria o clique abrir o lance errado."""

ALTURA_DA_BARRA = 14
RECUO_DA_BARRA = 3
LARGURA_MINIMA_DO_NUMERO = 26
"""Abaixo de 26 px um segmento não cabe `48%` na fonte da interface, e o número sai cortado pela
metade -- que é pior que ausente. O segmento continua desenhado: a proporção é o que a barra diz."""


class BarraDeResultado(QStyledItemDelegate):
    """Os três segmentos do resultado, como o Lichess os desenha.

    **Ela substitui o texto da célula, e não o acompanha.** A alternativa medida -- uma tira fina
    sob o texto -- deixa a barra com 6 px numa linha de 22, e a proporção some; e o texto continua
    disponível na dica da célula, que `qt/tabela.preencher` põe em toda uma delas.

    Sem frações (o ramo abaixo de `MINIMO_PARA_PERCENTUAL`) ela não desenha nada e deixa o
    travessão sair pelo caminho normal: a barra é a afirmação, e é ela que a amostra pequena não
    autoriza.
    """

    def paint(self, painter: QPainter | None, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        fracoes = index.data(PAPEL_DAS_FRACOES)
        if painter is None or not isinstance(fracoes, (list, tuple)) or not any(fracoes):
            super().paint(painter, option, index)
            return
        # O fundo (e a marca de selecao) pelo caminho do Qt; so o conteudo e nosso.
        vazio = QStyleOptionViewItem(option)
        self.initStyleOption(vazio, index)
        vazio.text = ""
        super().paint(painter, vazio, index)

        caixa = option.rect.adjusted(RECUO_DA_BARRA, 0, -RECUO_DA_BARRA, 0)
        altura = min(ALTURA_DA_BARRA, max(1, caixa.height() - 2 * RECUO_DA_BARRA))
        topo = caixa.top() + (caixa.height() - altura) // 2
        painter.save()
        esquerda = caixa.left()
        for indice, fracao in enumerate(fracoes[:3]):
            # A ultima fatia leva o resto: tres arredondamentos independentes deixam um vao de
            # um ou dois pixels no fim da barra, e ele aparece como uma falha branca no meio da fila.
            largura = (
                caixa.right() - esquerda + 1
                if indice == 2
                else int(round(caixa.width() * float(fracao)))
            )
            if largura <= 0:
                continue
            painter.setBrush(QColor(tema.cor_atual(CORES_DA_BARRA[indice])))
            painter.setPen(QColor(tema.cor_atual(CONTORNO_DA_BARRA)))
            painter.drawRect(esquerda, topo, largura, altura)
            if largura >= LARGURA_MINIMA_DO_NUMERO:
                painter.setPen(QColor(tema.cor_atual(TINTAS_DA_BARRA[indice])))
                painter.drawText(
                    esquerda,
                    topo,
                    largura,
                    altura,
                    int(Qt.AlignmentFlag.AlignCenter),
                    f"{round(float(fracao) * 100)}%",
                )
            esquerda += largura
        painter.restore()


class DialogoDaArvore(QDialog):
    """A árvore da posição corrente: um lance por linha, e o clique desce um degrau (S-535).

    **Não é modal**, pela razão de `DialogoDeBusca`: quem olha a árvore quer o tabuleiro ao lado, e
    clicar num lance move o tabuleiro **sem fechar a árvore** -- ela recalcula e continua ali.

    Ele é **reusado** entre aberturas, e a posição é a única coisa dele que envelhece: destruir o
    primeiro para abrir o segundo destruiria um `QThread` em curso, que derruba o processo sem
    exceção.
    """

    lance_escolhido = pyqtSignal(str)
    """O SAN que a pessoa escolheu. Texto e não `chess.Move` porque a sala vai reinterpretá-lo no
    tabuleiro dela -- e porque um `Move` de outro tabuleiro é um par de casas sem dono."""

    partidas_pedidas = pyqtSignal(object)
    """O `Filtro` que abre a lista das partidas desta posição na busca da S-533."""

    construcao_pedida = pyqtSignal()
    """A pessoa pediu para construir a árvore daqui. Quem a constrói é a sala, que tem as bases e
    o registro de ocupação da janela -- a mesma divisão de `DialogoDeBusca.indice_pedido`."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        bases: Sequence[Path] = (),
        arvore: Path = DEFAULT_TREE_PATH,
    ) -> None:
        super().__init__(parent)
        self._bases = tuple(bases)
        self._arquivo = arvore
        self._tabuleiro = chess.Board()
        self._tarefa: Tarefa | None = None
        self._pendente = False
        """Uma posição chegou enquanto a consulta anterior rodava. Ver `_perguntar`."""
        self._linhas: tuple[Linha, ...] = ()
        self._abertura: Any = None
        """A `eco.Abertura` da posição corrente, ou `None`. Guardada e não recalculada: o código
        dela é o que estreita a busca por partidas (`ui/arvore_de_aberturas.busca_da_posicao`) e o
        nome é o que a linha de cima escreve, e as duas têm de falar da **mesma** classificação.

        Ela sai do tabuleiro que a sala passou, com a pilha de lances dentro -- `eco.classificar`
        anda para trás por ela. A cópia sem pilha que este diálogo guarda responderia outra coisa:
        só a posição em que está, que numa abertura quase nunca é a que a tabela conhece."""

        self.setWindowTitle("Árvore de aberturas")
        self.resize(880, 460)
        self._montar()

    # ------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.folga())

        self.lbl_posicao = QLabel("", self)
        self.lbl_posicao.setWordWrap(True)
        fora.addWidget(self.lbl_posicao)

        self.tabela = TabelaQt(COLUNAS, self, ordenavel=True)
        self.tabela.setSelectionMode(TabelaQt.SelectionMode.SingleSelection)
        self.tabela.setItemDelegateForColumn(COLUNA_DA_BARRA, BarraDeResultado(self.tabela))
        self.tabela.itemClicked.connect(self._clicou)
        for tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            atalho = QShortcut(QKeySequence(tecla), self.tabela)
            atalho.setContext(Qt.ShortcutContext.WidgetShortcut)
            atalho.activated.connect(self.jogar_selecionado)
        fora.addWidget(self.tabela, 1)

        self.lbl_resumo = QLabel("", self)
        self.lbl_resumo.setWordWrap(True)
        fora.addWidget(self.lbl_resumo)
        fora.addLayout(self._rodape())
        # Sem árvore não há lance a jogar, e um botão que não faz nada é pior que um cinza (S-32).
        self.btn_jogar.setEnabled(False)

    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        self.btn_jogar = QPushButton("Jogar o lance", self)
        self.btn_jogar.clicked.connect(self.jogar_selecionado)
        tema.aplicar_papel(self.btn_jogar, estilos.PRIMARIO)
        self.btn_partidas = QPushButton("Ver as partidas…", self)
        self.btn_partidas.clicked.connect(self.pedir_partidas)
        dica_em(
            self.btn_partidas,
            "Abre a busca de partidas com esta posição e o ECO dela. A posição não está no índice\n"
            "por nome: é o ECO que estreita, e a busca diz quantas candidatas releu.",
        )
        self.btn_construir = QPushButton("Construir a árvore…", self)
        self.btn_construir.clicked.connect(self.construcao_pedida.emit)
        dica_em(
            self.btn_construir,
            "Reproduz os primeiros lances de cada partida da base. Leva dezenas de minutos e é\n"
            "cancelável; depois disso toda pergunta custa milissegundos.",
        )
        fechar = QPushButton("Fechar", self)
        fechar.clicked.connect(self.reject)
        for botao in (self.btn_jogar, self.btn_partidas, self.btn_construir, fechar):
            botao.setAutoDefault(False)
            if botao is not self.btn_jogar:
                tema.aplicar_papel(botao, estilos.NEUTRO)
        rodape.addWidget(self.btn_jogar)
        rodape.addWidget(self.btn_partidas)
        rodape.addStretch(1)
        rodape.addWidget(self.btn_construir)
        rodape.addWidget(fechar)
        return rodape

    # -------------------------------------------------------------------------- consulta

    def definir_posicao(self, tabuleiro: chess.Board) -> bool:
        """A posição da sala mudou: recalcula a árvore. Devolve se a consulta começou agora.

        Falso não é falha: é "havia uma consulta em curso, e esta ficou pendente" -- ver
        `_perguntar`.
        """
        # `stack=False`: a pilha de lances nao viaja, e `ply()` continua respondendo pelo numero
        # de lance e pela vez -- que e o que a arvore precisa saber (quantos meios-lances desde a
        # posicao inicial). A copia e o que impede a corrida: `linhas` empilha e desempilha para
        # achar o nome de cada abertura, e a sala esta usando o tabuleiro dela ao mesmo tempo.
        self._tabuleiro = tabuleiro.copy(stack=False)
        self._abertura = classificar(tabuleiro)
        self.lbl_posicao.setText(self._frase_da_posicao())
        return self._perguntar()

    def _perguntar(self) -> bool:
        """Dispara a consulta da posição guardada. Devolve se ela começou.

        **Com uma consulta em curso, o pedido fica pendente e é refeito no fim** -- e não
        descartado. A árvore acompanha o `refresh` da sala, e navegar três lances com a seta em
        meio segundo dispara três pedidos: sem isto, a tabela ficaria mostrando a posição do
        primeiro. Guardar só o último é o certo -- os do meio já não interessam a ninguém --, e é
        a mesma forma de `qt/trabalho.DeteccaoDeFundo`.
        """
        if self._tarefa is not None:
            self._pendente = True
            return False
        self._pendente = False
        colocacao, vez = self._tabuleiro.board_fen(), "w" if self._tabuleiro.turn else "b"
        ply, arquivo, bases = self._tabuleiro.ply(), self._arquivo, self._bases
        self.tabela.preencher(())
        self._linhas = ()
        self._escrever(EM_BUSCA)
        tarefa = Tarefa(
            lambda: consultar(colocacao, vez, ply=ply, path=arquivo, bases=bases),
            parent=self,
            nome="árvore de aberturas",
        )
        tarefa.pronto.connect(self._chegou)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        self._tarefa = tarefa
        tarefa.start()
        return True

    def _frase_da_posicao(self) -> str:
        """Qual posição está sendo perguntada -- **e ela precisa estar escrita**.

        O diálogo não fecha quando o tabuleiro anda, e sem esta linha a tabela de dez lances de uma
        Najdorf é indistinguível da de outra: o título diria "Árvore de aberturas" nas duas.
        """
        lance = self._tabuleiro.ply() // 2 + 1
        vez = "brancas" if self._tabuleiro.turn else "pretas"
        nome = "" if self._abertura is None else f" · {self._abertura.codigo} {self._abertura.nome}"
        return f"Lance {lance}, jogam as {vez}{nome}"

    def _chegou(self, resposta: Any) -> None:
        self._linhas = linhas(resposta, self._tabuleiro)
        self.tabela.preencher(linha.celulas for linha in self._linhas)
        self.tabela.sortItems(COLUNA_DA_ORDEM, Qt.SortOrder.DescendingOrder)
        self._marcar_fracoes()
        self._escrever(resumo(resposta, len(self._linhas)), atencao=e_aviso(resposta))
        self.btn_jogar.setEnabled(bool(self._linhas))

    def _marcar_fracoes(self) -> None:
        """Põe as frações de cada linha no item que a tabela montou, para o delegado achá-las.

        Pela posição **original** e não pela altura na tela: com a ordenação pelo cabeçalho ligada
        as duas divergem, e a barra sairia na linha errada -- o mesmo defeito que
        `qt/tabela.posicao_de` existe para impedir na escolha.
        """
        for altura in range(self.tabela.topLevelItemCount()):
            item = self.tabela.topLevelItem(altura)
            if item is None:
                continue
            posicao = self.tabela.posicao_de(item)
            if 0 <= posicao < len(self._linhas):
                item.setData(COLUNA_DA_BARRA, PAPEL_DAS_FRACOES, self._linhas[posicao].fracoes)

    def _falhou(self, mensagem: str, _excecao: object) -> None:
        logger.warning("A árvore de aberturas falhou: %s", mensagem)
        self._escrever(mensagem, atencao=True)

    def _terminou(self) -> None:
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()
        if self._pendente:
            self._perguntar()

    def esperar(self, espera_ms: int = 30_000) -> bool:
        """Espera a consulta em curso terminar. O par de `DialogoDeBusca.esperar`."""
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    # --------------------------------------------------------------------------- escolha

    def _clicou(self, item: QTreeWidgetItem, _coluna: int) -> None:
        self._jogar(self.tabela.posicao_de(item))

    def jogar_selecionado(self) -> None:
        """Emite `lance_escolhido` para a linha marcada. É o que o `Enter` e o botão fazem."""
        self._jogar(self.tabela.posicao_selecionada())

    def _jogar(self, posicao: int) -> None:
        if 0 <= posicao < len(self._linhas):
            self.lance_escolhido.emit(self._linhas[posicao].lance)

    def pedir_partidas(self) -> None:
        """Emite `partidas_pedidas` com o filtro desta posição. Ver `busca_da_posicao`."""
        codigo = "" if self._abertura is None else self._abertura.codigo
        self.partidas_pedidas.emit(busca_da_posicao(self._tabuleiro.board_fen(), codigo))

    def _escrever(self, texto: str, *, atencao: bool = False) -> None:
        self.lbl_resumo.setText(texto)
        tema.pintar(self.lbl_resumo, "color", tokens.PROBLEMA_TEXTO if atencao else tokens.TEXTO_SECUNDARIO)


# ------------------------------------------------------------------------- a construção


class ConstrutorDaArvore(QObject):
    """Constrói a árvore numa thread e conta o andamento por sinal. O par de `IndexadorDaBase`.

    A forma é a da S-532 e pelo mesmo motivo: `construir` avisa na thread de trabalho, e um
    `QThread` que tocasse widget direto derrubaria o processo sem exceção. `progresso` é emitido
    lá e o slot roda aqui, na thread da interface.
    """

    progresso = pyqtSignal(int, int, int)
    terminou = pyqtSignal(object)
    falhou = pyqtSignal(str, object)

    def __init__(self, parent: QObject | None = None, *, busy: BusyRegistry | None = None) -> None:
        super().__init__(parent)
        self._tarefa: Tarefa | None = None
        self._cancelar = threading.Event()
        self._busy = busy
        self._token: BusyToken | None = None
        self.resultado: Any = None
        """O que a última rodada fez; `None` enquanto nenhuma terminou."""
        self.dialogo: QProgressDialog | None = None

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def iniciar(
        self,
        bases: Sequence[Path],
        caminho: Path = DEFAULT_TREE_PATH,
        *,
        profundidade: int = PROFUNDIDADE,
    ) -> bool:
        """Começa a passada. Devolve falso se já há uma em curso -- duas escreveriam no mesmo arquivo."""
        if self._tarefa is not None:
            return False
        lista = [Path(base) for base in bases]
        self._cancelar = threading.Event()
        self.resultado = None
        cancelar, relatar = self._cancelar, self._relatar

        def _trabalho() -> Any:
            return construir(lista, caminho, profundidade=profundidade, progress=relatar, cancel=cancelar)

        tarefa = Tarefa(_trabalho, parent=self, nome="árvore de aberturas")
        tarefa.pronto.connect(self._pronto)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._acabou)
        self._registrar_ocupado(len(lista), profundidade)
        self._tarefa = tarefa
        tarefa.start()
        return True

    def cancelar(self) -> None:
        """Pede para parar. **A passada inteira é descartada** -- ver `arvore_de_aberturas.Construcao`."""
        self._cancelar.set()

    def esperar(self, espera_ms: int) -> bool:
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    def _relatar(self, prontos: int, total: int, partidas: int) -> None:
        # Chamado na thread de trabalho: so emite.
        self.progresso.emit(prontos, total, partidas)

    def _pronto(self, resultado: Any) -> None:
        self.resultado = resultado
        self.terminou.emit(resultado)

    def _falhou(self, mensagem: str, excecao: object) -> None:
        logger.warning("A árvore de aberturas falhou: %s", mensagem)
        self.falhou.emit(mensagem, excecao)

    def _acabou(self) -> None:
        if self._token is not None:
            self._token.release()
            self._token = None
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()

    def _registrar_ocupado(self, quantas: int, profundidade: int) -> None:
        """A passada entra no registro de ocupação da janela, e ela **perde trabalho ao fechar**.

        É o contrário do índice (S-532), e a razão está em
        `ui/arvore_de_aberturas.perde_trabalho_ao_fechar`: aqui não há transação por arquivo a
        recuperar -- a passada interrompida é descartada inteira.
        """
        if self._busy is None:
            return
        self._token = self._busy.register(
            "árvore de aberturas",
            loses_work=perde_trabalho_ao_fechar(),
            cancellable=True,
            detail=f"{quantas} arquivo(s), {profundidade} meios-lances",
            cancel=self.cancelar,
        )


def construir_com_dialogo(
    parent: QWidget | None,
    bases: Sequence[Path],
    caminho: Path = DEFAULT_TREE_PATH,
    *,
    profundidade: int = PROFUNDIDADE,
    busy: BusyRegistry | None = None,
    mostrar: bool = True,
) -> ConstrutorDaArvore:
    """Um `QProgressDialog` com Cancelar em cima de `ConstrutorDaArvore`. Devolve o construtor.

    **O passo é o pedaço, e não o byte**, ao contrário do índice da S-532: a passada reparte o
    arquivo entre processos e cada um só sabe que terminou quando terminou -- não há como perguntar
    a um filho quantas partidas faltam sem interrompê-lo. Dez pedaços dão uma barra de dez degraus,
    e é a contagem de partidas ao lado que anda no meio de cada um.

    `mostrar=False` não chama `show()`: é o caminho do teste sob `offscreen`.
    """
    construtor = ConstrutorDaArvore(parent, busy=busy)
    dialogo = QProgressDialog(frase_da_construcao(0, 0, 0), "Cancelar", 0, 1, parent)
    dialogo.setWindowTitle("Árvore de aberturas")
    dialogo.setWindowModality(Qt.WindowModality.WindowModal)
    dialogo.setMinimumDuration(0)
    dialogo.setAutoClose(False)
    dialogo.setAutoReset(False)
    dialogo.setMinimumWidth(440)
    dialogo.canceled.connect(construtor.cancelar)

    def _andou(prontos: int, total: int, partidas: int) -> None:
        dialogo.setMaximum(max(1, total))
        dialogo.setValue(prontos)
        dialogo.setLabelText(frase_da_construcao(prontos, total, partidas))

    construtor.progresso.connect(_andou)

    def _fechar(*_ignorado: object) -> None:
        dialogo.close()
        dialogo.deleteLater()
        construtor.dialogo = None

    construtor.terminou.connect(_fechar)
    construtor.falhou.connect(_fechar)
    construtor.dialogo = dialogo
    if not construtor.iniciar(bases, caminho, profundidade=profundidade):
        _fechar()
        return construtor
    if mostrar:
        dialogo.show()
    return construtor


def frase_final(resultado: Any) -> str:
    """A frase de `ui/arvore_de_aberturas.frase_do_fim` -- o que vai ao rodapé da sala."""
    return frase_do_fim(resultado)
