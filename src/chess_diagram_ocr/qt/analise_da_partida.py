"""A partida inteira pelo motor, com barra, Cancelar e o gráfico do resultado (S-537).

**A fiação, e nada mais.** Quanto um lance custou, onde estão os cortes de `?!`/`?`/`??` e em que
pixel o gráfico desenha cada ply são de `ui/analise_da_partida.py`. Aqui há três coisas de Qt:

1. **A thread.** Quarenta lances a profundidade 16 são ~40 s de motor, e a linha de eventos não
   pode ficar nisso -- é o mesmo argumento de `qt/trabalho.py`, e é a mesma `Tarefa`. O progresso
   volta por **sinal**, porque ele é emitido na thread de trabalho e tocar widget de lá derruba o
   processo sem exceção. É a forma que `qt/indice_da_base.py` já usa para o índice da base.
2. **O Cancelar.** Um `threading.Event` que o worker confere entre uma posição e a seguinte. O que
   já foi avaliado **fica**: cancelar não desfaz os vinte primeiros lances, do mesmo modo que
   cancelar o índice não apaga os arquivos já lidos.
3. **O gráfico.** `QPainter` e nada mais -- sem biblioteca. Um gráfico de linha com uma divisa no
   meio não precisa de eixos, legenda nem escala automática, que é tudo o que uma biblioteca de
   gráficos traria; e trazê-la poria uma dependência de desenho num programa que já desenha
   tabuleiro, ícone e página com `QPainter`.

**A árvore não atravessa a fronteira de thread.** O worker recebe FENs (`analise_da_partida.
percurso`) e devolve números; quem escreve `[%eval]` e o símbolo nos nós é a sala, na linha de
eventos, depois. Passar `GameNode` para a thread seria lê-los enquanto alguém promove uma variante.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from PyQt6.QtCore import QObject, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPolygon
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressDialog,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.ui import analise_da_partida as declarada
from chess_diagram_ocr.ui import espaco, motor_declarado, tipografia, tokens
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken

logger = logging.getLogger(__name__)

__all__ = [
    "ALTURA_DO_GRAFICO",
    "AnalisadorDaPartida",
    "DialogoDaProfundidade",
    "GraficoDaPartida",
    "JanelaDaAnalise",
    "analisar_com_dialogo",
]

ALTURA_DO_GRAFICO = 140
"""Altura do gráfico, em pixel. Com menos, meio peão deixa de ser um pixel e a curva vira um traço
reto; com muito mais, o relatório deixa de caber ao lado da lista de erros numa janela de 1400."""


class AnalisadorDaPartida(QObject):
    """Passa a linha principal pelo motor e conta o andamento por sinal.

    `progresso(feito, total, san)` chega uma vez por posição; `terminou(lista de Avaliado)` e
    `falhou(mensagem, exceção)` são os dois fins possíveis, e exatamente um deles chega -- é o
    contrato de `qt/trabalho.Tarefa`, e a razão dele está no docstring de `run`.
    """

    progresso = pyqtSignal(int, int, str)
    terminou = pyqtSignal(object)
    falhou = pyqtSignal(str, object)

    def __init__(self, parent: QObject | None = None, *, analisador: Any, busy: BusyRegistry | None = None) -> None:
        super().__init__(parent)
        self._analisador = analisador
        self._tarefa: Tarefa | None = None
        self._cancelar = threading.Event()
        self._busy = busy
        self._token: BusyToken | None = None
        self.resultado: list[Any] = []
        """O que a última rodada avaliou. Sobrevive ao cancelamento: o que foi medido, foi."""
        self.cancelada = False
        self.dialogo: QProgressDialog | None = None
        self.profundidade = 0
        """A profundidade **pedida** na última rodada. O relatório a compara com a alcançada."""

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def iniciar(self, jogo: Any, *, profundidade: int) -> bool:
        """Começa a rodada. Falso se já há uma em curso -- duas disputariam o mesmo processo."""
        if self._tarefa is not None:
            return False
        fens, passos = declarada.percurso(jogo)
        if not passos:
            return False
        self._cancelar = threading.Event()
        self.resultado = []
        self.cancelada = False
        cancelar = self._cancelar
        relatar = self._relatar
        analisador = self._analisador
        fundura = max(declarada.PROFUNDIDADE_MINIMA, min(declarada.PROFUNDIDADE_MAXIMA, int(profundidade)))
        self.profundidade = fundura

        def _trabalho() -> list[Any]:
            return _avaliar(analisador, fens, passos, fundura, cancelar, relatar)

        tarefa = Tarefa(_trabalho, parent=self, nome="análise da partida")
        tarefa.pronto.connect(self._pronto)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        self._registrar_ocupado(len(passos))
        self._tarefa = tarefa
        tarefa.start()
        return True

    def cancelar(self) -> None:
        """Pede para parar. O worker responde entre uma posição e a seguinte."""
        self.cancelada = True
        self._cancelar.set()

    def esperar(self, espera_ms: int) -> bool:
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    # ------------------------------------------------------------- da thread de trabalho

    def _relatar(self, feito: int, total: int, san: str) -> None:
        # Chamado na thread de trabalho: so emite.
        self.progresso.emit(int(feito), int(total), str(san))

    # --------------------------------------------------------------- na thread da interface

    def _pronto(self, avaliados: Any) -> None:
        self.resultado = list(avaliados or [])
        if self._token is not None:
            self._token.update("análise da partida", feito=len(self.resultado), total=len(self.resultado) or 1)
        self.terminou.emit(self.resultado)

    def _falhou(self, mensagem: str, excecao: object) -> None:
        logger.warning("A análise da partida falhou: %s", mensagem)
        self.falhou.emit(mensagem, excecao)

    def _terminou(self) -> None:
        self._soltar_ocupado()
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()

    def _registrar_ocupado(self, quantos: int) -> None:
        if self._busy is None:
            return
        self._token = self._busy.register(
            "análise da partida",
            loses_work=False,
            cancellable=True,
            detail=f"{quantos} lance(s)",
            total=quantos,
            cancel=self.cancelar,
        )

    def _soltar_ocupado(self) -> None:
        if self._token is not None:
            self._token.release()
            self._token = None


def _avaliar(
    analisador: Any,
    fens: tuple[str, ...],
    passos: tuple[Any, ...],
    profundidade: int,
    cancelar: threading.Event,
    relatar: Any,
) -> list[Any]:
    """O laço do motor, **na thread de trabalho**. Devolve o que deu tempo de avaliar.

    O teto por posição é o que dá ao Cancelar um limite de espera: sem ele, um meio-jogo travado a
    profundidade 24 poderia segurar o botão por meio minuto. Ele **escala com a profundidade**
    desde a segunda rodada (`declarada.teto_por_lance_ms`), porque com os 3 s fixos a profundidade
    30 que o diálogo oferece não era alcançada em 41 de 46 posições.
    """
    import chess

    teto = declarada.teto_por_lance_ms(profundidade)
    centipeoes: list[int] = []
    mates: list[int | None] = []
    profundidades: list[int] = []
    acabou: list[bool] = []
    for indice, fen in enumerate(fens):
        if cancelar.is_set():
            break
        relatar(indice + 1, len(passos), passos[min(indice, len(passos) - 1)].san)
        tabuleiro = chess.Board(fen)
        avaliacao = analisador.analyse(tabuleiro, depth=profundidade, movetime_ms=teto)
        centipeoes.append(declarada.avaliacao_em_centipeoes(avaliacao.score_cp, avaliacao.mate_in))
        mates.append(avaliacao.mate_in)
        profundidades.append(int(getattr(avaliacao, "depth", 0) or 0))
        acabou.append(not any(tabuleiro.generate_legal_moves()))

    avaliados: list[Any] = []
    for indice, passo in enumerate(passos):
        if indice + 1 >= len(centipeoes):
            break
        perda, juizo = declarada.julgar(
            centipeoes[indice], centipeoes[indice + 1], brancas_jogaram=passo.brancas
        )
        avaliados.append(
            declarada.Avaliado(
                ply=indice + 1,
                numero=passo.numero,
                brancas=passo.brancas,
                san=passo.san,
                centipeoes=centipeoes[indice + 1],
                mate_em=mates[indice + 1],
                perda=perda,
                juizo=juizo,
                perda_de_chance=declarada.perda_de_expectativa(
                    centipeoes[indice], centipeoes[indice + 1], brancas_jogaram=passo.brancas
                ),
                profundidade=profundidades[indice + 1],
                acabou=acabou[indice + 1],
            )
        )
    return avaliados


class DialogoDaProfundidade(QDialog):
    """Quantos plies por lance. Um campo, dois botões, e o texto deles em português.

    **A pergunta existe porque a resposta muda a conta de tempo em uma ordem de grandeza**, e quem
    manda analisar precisa poder escolher entre "um café" e "agora". O padrão é o medido
    (`PROFUNDIDADE_PADRAO`), e o aviso ao lado diz o que cada escolha custa.
    """

    def __init__(self, parent: QWidget | None = None, *, lances: int = 0) -> None:
        super().__init__(parent)
        self.setWindowTitle("Analisar a partida")
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.setSpacing(espaco.folga())
        quantos = f"{lances} lance(s) na linha principal. " if lances else ""
        # **A conta de tempo é medida e está na tela**, e não só na dica: a profundidade é a única
        # escolha desta caixa, e ela muda o custo em uma ordem de grandeza -- 10 s contra 16 min na
        # mesma partida. Sem o número, escolher 30 é escolher às cegas.
        aviso = QLabel(
            f"{quantos}Cada lance é avaliado à profundidade escolhida, e o resultado grava a\n"
            "avaliação em cada um e marca as imprecisões, os erros e os erros graves.\n"
            "Nesta máquina, uma partida de 60 lances custou 10 s à profundidade 16, 44 s à 20,\n"
            "3 min à 24 e 16 min à 30.",
            self,
        )
        aviso.setWordWrap(True)
        pilha.addWidget(aviso)

        linha = QHBoxLayout()
        linha.addWidget(QLabel("Profundidade (plies):", self))
        self.campo = QSpinBox(self)
        self.campo.setRange(declarada.PROFUNDIDADE_MINIMA, declarada.PROFUNDIDADE_MAXIMA)
        self.campo.setValue(declarada.PROFUNDIDADE_PADRAO)
        dica_em(
            self.campo,
            "Abaixo de 10 o motor não vê a tática que a análise existe para achar. Cada ply a mais\n"
            "custa cerca de 40% de tempo, medido nesta máquina. O padrão é onde a curva vira.\n"
            "O teto de tempo por posição acompanha a profundidade, e o relatório diz quantas\n"
            "posições pararam nele antes de chegar lá.",
        )
        linha.addWidget(self.campo)
        linha.addStretch(1)
        pilha.addLayout(linha)

        botoes = QDialogButtonBox(parent=self)
        botoes.addButton("Analisar", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)

    def profundidade(self) -> int:
        return int(self.campo.value())


class GraficoDaPartida(QWidget):
    """A avaliação ao longo da partida, desenhada com `QPainter` (S-537).

    **Sem biblioteca de gráficos, e a razão não é peso.** Um gráfico com eixos, legenda, escala
    automática e ticks seria *pior* aqui: o eixo vertical não tem unidade que se escreva (é fração
    de vantagem, não centipeões) e o horizontal é o ply, que a lista ao lado já nomeia. O que
    precisa aparecer é a forma da curva e onde ela cai -- e para isso são quatro chamadas de
    `QPainter`.

    **Clicar leva ao lance.** É o gesto inteiro do item: o gráfico existe para achar onde a partida
    virou, e um gráfico que não leva até lá deixa a busca para o dedo de quem lê a lista.
    """

    escolhido = pyqtSignal(int)
    """O índice (base zero) do lance sob o clique -- o mesmo índice da lista de `Avaliado`."""

    DICA = "A avaliação lance a lance. Acima da linha do meio é vantagem das brancas.\nClique para ir ao lance."

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._avaliados: tuple[Any, ...] = ()
        self._corrente = -1
        """O índice do lance em que a sala está, ou `-1`. Ver `marcar`."""

        self.setMinimumHeight(ALTURA_DO_GRAFICO)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        dica_em(self, self.DICA)
        tema.ao_repintar(self.update)

    def definir(self, avaliados: Any) -> None:
        self._avaliados = tuple(avaliados or ())
        self.update()

    def marcar(self, ply: int) -> None:
        """Onde a sala está, marcado no gráfico por um fio vertical (S-537, segunda rodada).

        **Sem ele o relatório e o tabuleiro deixam de conversar.** Clicar num vale move a sala até
        lá, e a partir daí o gráfico continua mostrando a partida inteira sem dizer *onde* aquele
        tabuleiro está nela -- que é a única coisa que o gráfico tem para dizer depois do clique.
        `ply` fora da partida apaga a marca, que é o que a posição inicial deve fazer.
        """
        alvo = -1
        for indice, lance in enumerate(self._avaliados):
            if int(lance.ply) == int(ply):
                alvo = indice
                break
        if alvo != self._corrente:
            self._corrente = alvo
            self.update()

    def corrente(self) -> int:
        """O índice marcado, ou `-1`. É por ele que o teste pergunta."""
        return self._corrente

    def pontos(self) -> tuple[tuple[int, int], ...]:
        """Os pontos que `paintEvent` desenha. É por eles que o teste pergunta."""
        return declarada.pontos_do_grafico(self._avaliados, self.width(), self.height())

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        pontos = self.pontos()
        pintor = QPainter(self)
        try:
            # **Duas faixas, como na barra vertical**: o que está **abaixo** da curva é das
            # brancas, o que está acima é das pretas. É a mesma leitura girada 90°, e é o que faz
            # os dois desenhos da mesma tela dizerem a mesma coisa. A primeira redação preenchia
            # só a área entre a curva e a linha do meio, e com uma cor só: na fotografia o gráfico
            # saiu inteiro claro, e não dava para ver de quem era a partida em ponto nenhum.
            pintor.fillRect(self.rect(), QColor(tema.cor_atual(motor_declarado.PAPEL_DE_PRETAS)))
            meio = declarada.y_do_meio(self.height())
            if len(pontos) >= 2:
                contorno = [*pontos, (pontos[-1][0], self.height()), (pontos[0][0], self.height())]
                pintor.setPen(Qt.PenStyle.NoPen)
                pintor.setBrush(QColor(tema.cor_atual(motor_declarado.PAPEL_DE_BRANCAS)))
                pintor.drawPolygon(QPolygon([QPoint(x, y) for x, y in contorno]))
                pintor.setBrush(Qt.BrushStyle.NoBrush)
            # A linha do equilíbrio **por cima das duas faixas**: sem ela o gráfico não tem zero, e
            # ela é o único traço que precisa ser lido contra as duas cores.
            pintor.setPen(QPen(QColor(tema.cor_atual(tokens.ATENCAO)), 1, Qt.PenStyle.DashLine))
            pintor.drawLine(0, meio, self.width(), meio)
            if len(pontos) < 2:
                return
            self._marcar_erros(pintor, pontos)
            self._marcar_corrente(pintor, pontos)
        finally:
            pintor.end()

    def _marcar_corrente(self, pintor: QPainter, pontos: tuple[tuple[int, int], ...]) -> None:
        """O fio vertical no lance em que a sala está, com um anel sobre o ponto. Ver `marcar`.

        Fio inteiro e não só o anel: um ponto a mais num gráfico que já tem pontos de erro seria
        mais um ponto; o traço de cima a baixo é lido como "estou aqui" sem precisar de legenda.

        **A cor é `VIZINHA_TEXTO`, e ela foi escolhida por medição e não por gosto.** O fio
        atravessa as duas faixas do gráfico -- a clara das brancas e a escura das pretas --, então
        ele precisa de 3:1 contra as **duas**. Na paleta do projeto o azul `#1565c0` é o único papel
        que passa nas duas pontas: **5,46:1** sobre `GLIFO_CLARO` e **3,29:1** sobre `GLIFO_ESCURO`.
        Os candidatos naturais reprovam num dos lados -- `CASA_ULTIMO_LANCE` dá 1,53:1 sobre a
        faixa clara, e `CONTORNO_DE_SELECAO` some na escura.
        """
        if not (0 <= self._corrente < len(pontos)):
            return
        x, y = pontos[self._corrente]
        pintor.setPen(QPen(QColor(tema.cor_atual(tokens.VIZINHA_TEXTO)), 1))
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawLine(x, 0, x, self.height())
        pintor.drawEllipse(QPoint(x, y), 5, 5)

    def _marcar_erros(self, pintor: QPainter, pontos: tuple[tuple[int, int], ...]) -> None:
        """Um ponto sobre cada lance julgado. A cor é a do juízo, e ela vem de `ui/tokens.py`."""
        cores = {
            declarada.IMPRECISAO: tema.cor_atual(tokens.DIVERGENTE),
            declarada.ERRO: tema.cor_atual(tokens.ATENCAO),
            declarada.ERRO_GRAVE: tema.cor_atual(tokens.PROBLEMA),
        }
        for indice, lance in enumerate(self._avaliados):
            cor = cores.get(lance.juizo)
            if cor is None or indice >= len(pontos):
                continue
            raio = 4 if lance.juizo == declarada.ERRO_GRAVE else 3
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(QColor(cor))
            x, y = pontos[indice]
            pintor.drawEllipse(QPoint(x, y), raio, raio)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None or not self._avaliados:  # pragma: no cover - clique sem evento
            return
        self.escolhido.emit(
            declarada.indice_no_x(int(a0.position().x()), len(self._avaliados), self.width())
        )

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """A dica passa a dizer **qual** lance está sob o ponteiro (S-537, segunda rodada).

        `setToolTip` a cada movimento e não uma janela própria: a dica do Qt já sabe esperar,
        posicionar-se e sumir, e trocar o texto dela é o mecanismo que `qt/tabela.py` usa para o
        mesmo fim. Fora dos pontos, a dica volta a explicar o gráfico.
        """
        if a0 is None:  # pragma: no cover - movimento sem evento
            return
        self.setToolTip(self.frase_em(int(a0.position().x())))

    def frase_em(self, x: int) -> str:
        """O que a dica diz sobre o pixel `x`. É por ela que o teste pergunta."""
        if not self._avaliados:
            return self.DICA
        indice = declarada.indice_no_x(int(x), len(self._avaliados), self.width())
        return declarada.frase_do_ponto(self._avaliados[indice])


class JanelaDaAnalise(QDialog):
    """O relatório: o resumo, o gráfico e a lista dos lances julgados (S-537).

    Não modal, e é decisão: a razão de existir do relatório é ser lido **com o tabuleiro ao lado**
    -- clicar num erro leva a sala até ele, e uma janela modal impediria justamente isso.
    """

    def __init__(self, pai: QWidget, avaliados: Any, *, ir_para: Any, profundidade: int = 0) -> None:
        super().__init__(pai)
        self.setWindowTitle("Análise da partida")
        self.resize(720, 420)
        self._avaliados = list(avaliados or [])
        self._ir_para = ir_para
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.setSpacing(espaco.folga())

        self.lbl_resumo = QLabel(declarada.resumo(self._avaliados), self)
        self.lbl_resumo.setWordWrap(True)
        self.lbl_resumo.setFont(tema.fonte_atual(tipografia.TITULO))
        pilha.addWidget(self.lbl_resumo)

        # **O aviso de truncamento é um segundo rótulo, e não um pedaço do resumo.** Ele não fala
        # da partida, fala da medição: quantas posições pararam no teto de tempo antes de chegar à
        # profundidade pedida. Grudado na contagem de erros ele pareceria mais um número dela.
        self.lbl_truncadas = QLabel(declarada.frase_de_truncamento(self._avaliados, profundidade), self)
        self.lbl_truncadas.setWordWrap(True)
        tema.pintar(self.lbl_truncadas, "color", tokens.TEXTO_SECUNDARIO)
        self.lbl_truncadas.setVisible(bool(self.lbl_truncadas.text()))
        pilha.addWidget(self.lbl_truncadas)

        self.grafico = GraficoDaPartida(self)
        self.grafico.definir(self._avaliados)
        self.grafico.escolhido.connect(self._escolher)
        pilha.addWidget(self.grafico)

        self.lista = QListWidget(self)
        self.lista.setFont(tema.fonte_atual(tipografia.CORPO))
        self._julgados = [lance for lance in self._avaliados if lance.juizo]
        for lance in self._julgados:
            self.lista.addItem(lance.rotulo)
        if not self._julgados:
            self.lista.addItem("Nenhum lance passou do corte de imprecisão.")
        self.lista.itemClicked.connect(self._clique_na_lista)
        pilha.addWidget(self.lista, 1)

        # **"Fechar" e não `StandardButton.Close`**: o texto padrão do Qt é "Close" em inglês, e a
        # janela inteira fala português -- é a mesma razão de `qt/dialogos.py` escrever os seus.
        botoes = QDialogButtonBox(parent=self)
        botoes.addButton("Fechar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        self.show()

    def _escolher(self, indice: int) -> None:
        if 0 <= indice < len(self._avaliados):
            self._ir(self._avaliados[indice].ply)

    def _clique_na_lista(self, item: Any) -> None:
        linha = self.lista.row(item)
        if 0 <= linha < len(self._julgados):
            self._ir(self._julgados[linha].ply)

    def _ir(self, ply: int) -> None:
        """Move a sala **e** a marca do gráfico. Os dois caminhos passam por aqui de propósito:
        clicar no gráfico e clicar na lista têm de deixar a tela no mesmo estado."""
        self.grafico.marcar(int(ply))
        self._ir_para(int(ply))


def analisar_com_dialogo(
    parent: QWidget | None,
    *,
    analisador: Any,
    jogo: Any,
    profundidade: int,
    busy: BusyRegistry | None = None,
    mostrar: bool = True,
) -> AnalisadorDaPartida:
    """Um `QProgressDialog` com Cancelar em cima de `AnalisadorDaPartida`. Devolve o analisador.

    É a mesma forma de `qt/indice_da_base.indexar_com_dialogo`, e de propósito: as duas são a mesma
    operação longa com barra e Cancelar, e duas formas diferentes para isso seriam duas caixas que
    se comportam diferente na mesma janela.

    `mostrar=False` é o caminho do teste sob `offscreen`.
    """
    rodada = AnalisadorDaPartida(parent, analisador=analisador, busy=busy)
    _, passos = declarada.percurso(jogo)
    dialogo = QProgressDialog("Analisando a partida…", "Cancelar", 0, max(1, len(passos) + 1), parent)
    dialogo.setWindowTitle("Análise da partida")
    dialogo.setWindowModality(Qt.WindowModality.WindowModal)
    dialogo.setMinimumDuration(0)
    dialogo.setAutoClose(False)
    dialogo.setAutoReset(False)
    dialogo.setMinimumWidth(420)
    dialogo.canceled.connect(rodada.cancelar)
    def _andou(feito: int, total: int, san: str) -> None:
        dialogo.setValue(feito)
        dialogo.setLabelText(declarada.frase_de_progresso(feito, total, san))

    rodada.progresso.connect(_andou)

    def _fechar(*_ignorado: object) -> None:
        dialogo.close()
        dialogo.deleteLater()
        rodada.dialogo = None

    rodada.terminou.connect(_fechar)
    rodada.falhou.connect(_fechar)
    rodada.dialogo = dialogo
    if not rodada.iniciar(jogo, profundidade=profundidade):
        _fechar()
        return rodada
    if mostrar:
        dialogo.show()
    return rodada
