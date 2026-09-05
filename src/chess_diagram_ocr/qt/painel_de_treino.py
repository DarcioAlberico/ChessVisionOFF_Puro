"""A tela de treino: a agenda do dia, o exercício e o placar (S-539/S-540/S-541).

**A fiação, e nada mais.** Que exercício vem hoje é de `revisao_espacada.agenda`; em que balde cai o
lance é de `ui/treino_declarado.classificar_o_lance`; o que a solução diz é de `taticas.py`. Aqui há
três coisas de Qt, e as três pela mesma razão de `qt/analise_da_partida.py`:

1. **A extração roda numa thread** (`ExtratorDeTaticas`). Um livro de mil folhas passa pelo
   classificador e pelo leitor de texto, e isso são minutos -- a mesma `Tarefa` de `qt/trabalho.py`,
   com `threading.Event` de cancelamento conferido **entre folhas**, e o que já foi extraído fica.
2. **A comparação com o motor volta por sinal** (`PerdaDoLance`). Perguntar ao motor quanto o lance
   custou leva ~1 s, e a resposta "certo" ou "errado" não pode esperar por isso: ela chega na hora,
   e o número aparece quando o motor termina. É por isso que a frase do rodapé é escrita duas vezes.
3. **A janela** (`JanelaDeTreino`), que é um tabuleiro que cobra o lance e nada mais.

**Não modal, e é decisão.** A sala fica atrás, com o livro e a análise; um exercício que trancasse a
janela obrigaria a fechá-lo para conferir a posição no PDF -- que é justamente o que se faz quando a
solução não convence.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import chess
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr import placar as placar_mod
from chess_diagram_ocr import revisao_espacada, taticas
from chess_diagram_ocr.fen_utils import reading_index_from_square
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabuleiro_de_jogo import TabuleiroDeJogo
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.ui import espaco, estilos, tipografia, tokens
from chess_diagram_ocr.ui import treino_declarado as declarado
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.sala_declarada import FRACAO_PADRAO_DO_TABULEIRO

logger = logging.getLogger(__name__)

__all__ = [
    "COR_DO_ERRO",
    "TECLAS_DE_AVANCO",
    "TEMPO_DA_PERDA_MS",
    "ExtratorDeTaticas",
    "JanelaDeTreino",
    "PerdaDoLance",
    "extrair_com_dialogo",
]

COR_DO_ERRO = "red"
"""A cor da seta que marca o lance recusado (S-541, r2).

**O erro precisava de sinal no tabuleiro, e o tabuleiro já tem um.** A frase do rodapé dizia que o
lance não era o da linha e a peça voltava sozinha para a casa de origem, sem nada explicando por
quê -- quem move rápido joga duas vezes o mesmo lance achando que soltou fora da casa. A seta
vermelha do `TabuleiroDeJogo` (S-279) é o mecanismo que já existe para "este lance, aqui", e
reusá-la é a diferença entre um sinal e um enfeite novo. Ela some no lance seguinte, que é quando a
pergunta deixa de ser a mesma."""

TECLAS_DE_AVANCO: tuple[Qt.Key, ...] = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)
"""As teclas que passam ao exercício seguinte (S-540, r2).

**Elas existem porque o `Enter` já fazia alguma coisa, e a coisa errada.** Num `QDialog` o `Return`
vai para o primeiro botão com `autoDefault`, e o primeiro que este arquivo criava era *Ver a
solução*: apertar `Enter` na abertura revelava o gabarito e reprovava o exercício -- estabilidade
0,4872 e volta amanhã --, sem que ninguém tivesse jogado nada. Desarmar o botão padrão resolve a
metade destrutiva; a outra metade é que uma sessão de sessenta itens **tem** de andar pelo teclado,
que é como o Chessable e o Anki funcionam.

**E o avanço é por tecla e não por relógio.** O Chessable avança sozinho depois do acerto; aqui o
que fica na tela quando o exercício fecha é a solução com a procedência, que é justamente o que se
lê -- um temporizador a apagaria antes de ela ser lida. Uma tecla é o mesmo gesto sem a corrida."""

TEMPO_DA_PERDA_MS = 700
"""Quanto o motor pensa para dizer o que o lance custou, em milissegundos (S-541).

Menos que os 800 ms de `engine.DEFAULT_MOVETIME_MS` e por outra razão: ali o motor está mostrando
candidatos a quem analisa, e aqui ele está julgando um lance que já foi jogado. Setecentos
milissegundos duas vezes -- antes e depois -- é o que mantém o veredicto abaixo de dois segundos, e
dois segundos é o tempo que alguém aceita esperar por uma nota."""


class PerdaDoLance(QObject):
    """Quanto o lance jogado custou, medido fora da linha de eventos (S-541).

    **A avaliação de "antes" é guardada, e é ela que faz a conta caber no tempo.** A posição antes do
    lance é a mesma para todas as tentativas naquele exercício -- errar três vezes não muda o que a
    posição valia --, então ela é perguntada uma vez e reusada. Sem isso, cada erro custaria duas
    buscas em vez de uma.
    """

    pronta = pyqtSignal(object, int, int)
    """`(ficha, avaliação antes, avaliação depois)`, as duas do ponto de vista das brancas.

    **As duas e não a perda pronta**: quem julga é `analise_da_partida.julgar`, que precisa dos dois
    números para aplicar o teto de dez peões e a regra da posição já decidida. Mandar a perda
    calculada daqui seria a segunda régua, e ela discordaria da primeira no primeiro mate."""

    falhou = pyqtSignal(object, str)

    def __init__(self, parent: QObject | None = None, *, analisador: Any = None) -> None:
        super().__init__(parent)
        self._analisador = analisador
        self._tarefa: Tarefa | None = None
        self._antes: dict[str, int] = {}

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def esquecer(self) -> None:
        """Joga fora as avaliações guardadas. A sala chama ao trocar de exercício."""
        self._antes.clear()

    def pedir(self, board: chess.Board, move: chess.Move, ficha: Any) -> bool:
        """Mede o custo daquele lance. Falso quando não há motor ou já há uma medição em curso.

        Devolver falso em vez de enfileirar é deliberado: quem erra três lances em dois segundos
        não quer três notas atrasadas, quer a do último -- e o veredicto de "certo ou errado" já
        chegou sem o motor.
        """
        if self._analisador is None or self._tarefa is not None:
            return False
        posicao = board.copy(stack=False)
        try:
            depois = posicao.copy(stack=False)
            depois.push(move)
        except (AssertionError, ValueError):  # pragma: no cover - lance sempre vem do modelo
            return False
        analisador = self._analisador
        guardadas = self._antes

        def _trabalho() -> tuple[int, int]:
            from chess_diagram_ocr.ui import analise_da_partida as regua

            chave = posicao.fen()
            if chave not in guardadas:
                avaliacao = analisador.analyse(posicao, movetime_ms=TEMPO_DA_PERDA_MS)
                guardadas[chave] = regua.avaliacao_em_centipeoes(avaliacao.score_cp, avaliacao.mate_in)
            seguinte = analisador.analyse(depois, movetime_ms=TEMPO_DA_PERDA_MS)
            return guardadas[chave], regua.avaliacao_em_centipeoes(seguinte.score_cp, seguinte.mate_in)

        tarefa = Tarefa(_trabalho, parent=self, nome="perda do lance")
        tarefa.pronto.connect(lambda par, f=ficha: self.pronta.emit(f, int(par[0]), int(par[1])))
        tarefa.falhou.connect(lambda mensagem, _e, f=ficha: self.falhou.emit(f, str(mensagem)))
        tarefa.finished.connect(self._terminou)
        self._tarefa = tarefa
        tarefa.start()
        return True

    def esperar(self, espera_ms: int) -> bool:
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    def _terminou(self) -> None:
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()


class ExtratorDeTaticas(QObject):
    """Passa um livro por `taticas.de_pdf` e conta o andamento por sinal (S-539).

    Mesma forma de `qt/analise_da_partida.AnalisadorDaPartida`, e de propósito: as duas são a
    operação longa com barra e Cancelar, e duas formas para isso seriam duas caixas que se
    comportam diferente na mesma janela.
    """

    progresso = pyqtSignal(int, int)
    terminou = pyqtSignal(object)
    falhou = pyqtSignal(str, object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        modelo: Any = None,
        analisador: Any = None,
        busy: BusyRegistry | None = None,
    ) -> None:
        super().__init__(parent)
        self._modelo = modelo
        self._analisador = analisador
        """O motor, quando há um. Ele **confirma** o gabarito impresso (S-539), e a confirmação é
        o que separa uma extração de 300 exercícios de uma de 300 linhas de ruído: num livro cuja
        camada de texto é um OCR quebrado, o motor recusou 10 de 10."""
        self._busy = busy
        self._token: BusyToken | None = None
        self._tarefa: Tarefa | None = None
        self._cancelar = threading.Event()
        self.resultado: Any = None
        self.cancelada = False
        self.dialogo: QProgressDialog | None = None

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def iniciar(self, livro: Path, *, inicio: int = 0, fim: int | None = None) -> bool:
        """Começa a extração. Falso se já há uma em curso -- duas disputariam o mesmo modelo."""
        if self._tarefa is not None:
            return False
        self._cancelar = threading.Event()
        self.cancelada = False
        self.resultado = None
        cancelar = self._cancelar
        relatar = self._relatar
        modelo = self._modelo
        analisador = self._analisador
        caminho = Path(livro)

        def _trabalho() -> Any:
            def _andou(feito: int, total: int) -> None:
                if cancelar.is_set():
                    raise _Cancelada
                relatar(feito, total)

            def _avaliar(board: Any) -> tuple[int | None, int | None]:
                avaliacao = analisador.analyse(board, movetime_ms=TEMPO_DA_PERDA_MS)
                return avaliacao.score_cp, avaliacao.mate_in

            return taticas.de_pdf(
                caminho,
                modelo=modelo,
                inicio=inicio,
                fim=fim,
                progresso=_andou,
                avaliar=_avaliar if analisador is not None else None,
            )

        tarefa = Tarefa(_trabalho, parent=self, nome=f"táticas de {caminho.name}")
        tarefa.pronto.connect(self._pronto)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        self._registrar_ocupado(caminho.name)
        self._tarefa = tarefa
        tarefa.start()
        return True

    def cancelar(self) -> None:
        self.cancelada = True
        self._cancelar.set()

    def esperar(self, espera_ms: int) -> bool:
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    def _relatar(self, feito: int, total: int) -> None:
        self.progresso.emit(int(feito), int(total))

    def _pronto(self, extracao: Any) -> None:
        self.resultado = extracao
        self.terminou.emit(extracao)

    def _falhou(self, mensagem: str, excecao: object) -> None:
        if isinstance(excecao, _Cancelada):
            self.terminou.emit(None)
            return
        logger.warning("A extração de táticas falhou: %s", mensagem)
        self.falhou.emit(mensagem, excecao)

    def _terminou(self) -> None:
        self._soltar_ocupado()
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()

    def _registrar_ocupado(self, nome: str) -> None:
        if self._busy is None:
            return
        self._token = self._busy.register(
            "táticas do livro", loses_work=False, cancellable=True, detail=nome, cancel=self.cancelar
        )

    def _soltar_ocupado(self) -> None:
        if self._token is not None:
            self._token.release()
            self._token = None


class _Cancelada(RuntimeError):
    """O Cancelar chegou entre duas folhas. Vira `terminou(None)` e não caixa vermelha."""


def extrair_com_dialogo(
    parent: QWidget | None,
    livro: Path,
    *,
    modelo: Any = None,
    analisador: Any = None,
    busy: BusyRegistry | None = None,
    mostrar: bool = True,
) -> ExtratorDeTaticas:
    """Um `QProgressDialog` com Cancelar em cima de `ExtratorDeTaticas`. `mostrar=False` é o teste."""
    rodada = ExtratorDeTaticas(parent, modelo=modelo, analisador=analisador, busy=busy)
    dialogo = QProgressDialog("Lendo o livro…", "Cancelar", 0, 100, parent)
    dialogo.setWindowTitle("Táticas do livro")
    dialogo.setWindowModality(Qt.WindowModality.WindowModal)
    dialogo.setMinimumDuration(0)
    dialogo.setAutoClose(False)
    dialogo.setAutoReset(False)
    dialogo.setMinimumWidth(420)
    dialogo.canceled.connect(rodada.cancelar)

    def _andou(feito: int, total: int) -> None:
        dialogo.setMaximum(max(1, total))
        dialogo.setValue(feito)
        dialogo.setLabelText(f"Lendo a folha {feito} de {total}…")

    rodada.progresso.connect(_andou)

    def _fechar(*_ignorado: object) -> None:
        dialogo.close()
        dialogo.deleteLater()
        rodada.dialogo = None

    rodada.terminou.connect(_fechar)
    rodada.falhou.connect(_fechar)
    rodada.dialogo = dialogo
    if not rodada.iniciar(livro):
        _fechar()
        return rodada
    if mostrar:
        dialogo.show()
    return rodada


class JanelaDeTreino(QDialog):
    """A fila do dia, um exercício por vez: a posição, o lance cobrado e o gabarito (S-539/S-540).

    **A agenda é montada uma vez, na abertura, e não a cada exercício.** Refazê-la a cada resposta
    faria o item que se acabou de acertar sumir da fila no meio da sessão -- e a pessoa perderia a
    conta de quantos faltam, que é a única informação que sustenta uma sessão de trinta minutos.

    **O resultado só vai para o disco quando a janela fecha.** É a regra de `estudo_arquivo`: uma
    gravação por resposta reescreveria o baralho inteiro sessenta vezes numa sessão, e o que se
    perde numa queda no meio é uma sessão -- não o histórico.
    """

    fechada = pyqtSignal()

    def __init__(
        self,
        pai: QWidget | None,
        *,
        exercicios: Sequence[taticas.Exercicio],
        baralho: dict[str, revisao_espacada.Estado] | None = None,
        placar: placar_mod.Placar | None = None,
        analisador: Any = None,
        hoje: date | None = None,
        gravar: Callable[[dict[str, revisao_espacada.Estado]], None] = lambda _b: None,
    ) -> None:
        super().__init__(pai)
        self.setWindowTitle("Treino de táticas")
        self.resize(900, 620)
        self._hoje = hoje or date.today()
        self._exercicios = {exercicio.chave: exercicio for exercicio in exercicios}
        self._baralho = dict(baralho or {})
        self._placar = placar if placar is not None else placar_mod.Placar()
        self._gravar = gravar
        self._perda = PerdaDoLance(self, analisador=analisador)
        self._perda.pronta.connect(self._chegou_a_perda)
        self._perda.falhou.connect(self._nao_veio_a_perda)

        self.agenda = revisao_espacada.agenda(
            list(self._exercicios), self._baralho, hoje=self._hoje
        )
        self._fila = list(self.agenda.fila)
        self._posicao = 0
        self._feitos = 0
        """Quantos exercícios desta sessão chegaram à tela. É o número do resumo do fim (S-540).

        Contado e não deduzido de `_posicao`: a fila pula a chave cujo exercício sumiu da coleção,
        e um resumo que dissesse "3 exercícios" onde apareceram 2 mentiria sobre a própria sessão."""
        self.tentativa = declarado.Tentativa()
        self.exercicio: taticas.Exercicio | None = None
        self._antes_do_exercicio: revisao_espacada.Estado | None = None
        """O estado que o item tinha **antes** desta volta (S-540).

        **Uma revisão por exercício, e não uma por botão apertado.** Sem isto, `marcar_facil`
        depois de acertar agendaria uma *segunda* revisão no mesmo dia -- e como não passou tempo
        nenhum entre elas, a retenção é 1, o ganho de estabilidade é zero e o "foi fácil" não muda
        data nenhuma. Re-agendar a partir daqui é o que faz o botão fazer o que ele diz."""
        self._tabuleiro_do_exercicio = chess.Board()
        self._virado = False
        """Quem resolve fica embaixo, e a orientação é guardada aqui em vez de perguntada ao
        widget: `TabuleiroQt.virado` existe, mas ler o desenho para decidir o desenho é o laço
        em que uma repintura inverte o tabuleiro."""

        self._montar()
        self._proximo()

    # ------------------------------------------------------------------------------ montagem

    def _montar(self) -> None:
        """Tabuleiro à esquerda, o que se lê à direita -- a repartição da sala (S-276).

        **Duas colunas e não uma pilha**, e a primeira fotografia mostrou por quê: empilhado, o
        tabuleiro tomava 66% da altura e as quatro frases -- agenda, resultado, procedência e
        placar -- ficavam espremidas no rodapé, cada uma quebrando em duas linhas. É a mesma
        repartição da sala de estudo, e pela mesma razão: lê-se com o olho **ao lado** do tabuleiro.

        A altura do tabuleiro segue a largura (`heightForWidth`), como na S-517: sem isso ele
        recebe toda a sobra da coluna e flutua no meio dela.

        **E ele ocupa a coluna inteira, e não 560 px** (S-539, r2). `MAX_DO_TABULEIRO` é herança do
        canvas de tamanho fixo do Tk, e sem `definir_fracao` ele valia aqui: medido em 2026-09-04,
        o tabuleiro do treino ficava em 560×560 em **toda** janela e em toda pele -- 15% da área a
        1400×950, com 861 px de vazio na coluna direita. A sala de estudo já chamava `definir_fracao`
        pela mesma razão (S-518), e a janela cujo assunto é *olhar para uma posição* era a que não
        chamava.
        """
        fora = QHBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.folga())

        esquerda = QVBoxLayout()
        esquerda.setSpacing(espaco.folga())

        self.lbl_vazio = QLabel("", self)
        """A frase que ocupa o lugar do tabuleiro quando não há posição (S-540, r2).

        **Ela nasce escondida, e um rótulo escondido não ocupa espaço** -- é o que permite pô-la
        no meio da coluna do tabuleiro sem mexer no arranjo de quem tem exercício aberto. Sem ela,
        a tela de "nada vence hoje" era a janela inteira vazia com uma linha no canto superior
        direito, que é a mesma falta de assunto do tabuleiro sem peças que ela substituiu."""
        self.lbl_vazio.setWordWrap(True)
        self.lbl_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vazio.setFont(tema.fonte_atual(tipografia.TITULO))
        self.lbl_vazio.hide()
        # **O peso vai no `addWidget` e não na `sizePolicy`**: num `QBoxLayout` quem reparte a
        # sobra é o fator de esticamento, e um `Expanding` com fator zero perde toda a sobra para o
        # `addStretch(1)` do fim -- a frase acabava colada no alto. Escondido, o rótulo não entra na
        # conta, e o arranjo de quem tem exercício aberto não muda.
        esquerda.addWidget(self.lbl_vazio, 4)

        self.tabuleiro = TabuleiroDeJogo(self)
        self.tabuleiro.lance.connect(self.jogar)
        self.tabuleiro.definir_fracao(FRACAO_PADRAO_DO_TABULEIRO)
        # **O tabuleiro é quem recebe o foco**, e é a outra metade da correção do `Enter` (S-541,
        # r2): sem widget nenhum focado, a tecla ia para o botão padrão do diálogo. Com o tabuleiro
        # focável, o anel de foco da S-553 nasce onde se joga.
        self.tabuleiro.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        politica = self.tabuleiro.sizePolicy()
        politica.setHeightForWidth(True)
        self.tabuleiro.setSizePolicy(politica)
        esquerda.addWidget(self.tabuleiro)

        self.lbl_vez = QLabel("", self)
        self.lbl_vez.setFont(tema.fonte_atual(tipografia.TITULO))
        esquerda.addWidget(self.lbl_vez)
        esquerda.addStretch(1)
        fora.addLayout(esquerda, 3)

        direita = QVBoxLayout()
        direita.setSpacing(espaco.folga())
        self.lbl_agenda = QLabel(self._frase_da_agenda(), self)
        self.lbl_agenda.setWordWrap(True)
        self.lbl_agenda.setFont(tema.fonte_atual(tipografia.TITULO))
        direita.addWidget(self.lbl_agenda)

        self.lbl_recado = QLabel("", self)
        self.lbl_recado.setWordWrap(True)
        self.lbl_recado.setAlignment(Qt.AlignmentFlag.AlignTop)
        direita.addWidget(self.lbl_recado)

        self.lbl_procedencia = QLabel("", self)
        self.lbl_procedencia.setWordWrap(True)
        tema.pintar(self.lbl_procedencia, "color", tokens.TEXTO_SECUNDARIO)
        direita.addWidget(self.lbl_procedencia)

        self.lbl_placar = QLabel("", self)
        self.lbl_placar.setWordWrap(True)
        tema.pintar(self.lbl_placar, "color", tokens.TEXTO_SECUNDARIO)
        direita.addWidget(self.lbl_placar)

        # **O vazio fica entre o texto e os botões**, e não no meio das frases: agrupadas no topo,
        # as quatro se leem como um bloco; com o esticador no recado, a procedência e o placar
        # ficavam boiando no meio da coluna -- foi o que a primeira fotografia mostrou.
        direita.addStretch(1)
        for widget in self._botoes():
            direita.addWidget(widget)
        fora.addLayout(direita, 2)
        self._ligar_o_teclado()

    def _botoes(self) -> list[QWidget]:
        """Os três da sessão, mais o Fechar. Um por linha: a coluna é estreita e eles são gestos
        diferentes -- ver a solução desiste do exercício, e "foi fácil" é um julgamento.

        **Nenhum deles é o botão padrão do diálogo, e isto é o defeito 4 da segunda rodada.** Num
        `QDialog` o `Return` vai para o primeiro `QPushButton` com `autoDefault` -- que é o de
        fábrica --, e aqui o primeiro criado era *Ver a solução*: `Enter` na abertura revelava o
        gabarito e reprovava o exercício sem que ninguém tivesse jogado. Desarmá-los é uma linha por
        botão, e o `Enter` passa a ser de quem o declarou (ver `TECLAS_DE_AVANCO`).
        """
        self.btn_solucao = QPushButton("Ver a solução", self)
        self.btn_solucao.clicked.connect(self.revelar)
        dica_em(
            self.btn_solucao,
            "Mostra a linha inteira e marca o exercício como não sabido: ele volta amanhã.\n"
            "Ver a resposta é não saber a resposta, e a agenda trata os dois igual.",
        )
        tema.aplicar_papel(self.btn_solucao, estilos.NEUTRO)

        self.btn_facil = QPushButton("Foi fácil", self)
        self.btn_facil.clicked.connect(self.marcar_facil)
        dica_em(
            self.btn_facil,
            "Só depois de acertar. Estica bastante o intervalo -- o programa nunca dá esta nota\n"
            "sozinho, porque ela é um julgamento sobre a própria memória.",
        )
        tema.aplicar_papel(self.btn_facil, estilos.NEUTRO)

        self.btn_proximo = QPushButton("Próximo", self)
        self.btn_proximo.clicked.connect(self._proximo)
        dica_em(
            self.btn_proximo,
            "Vai ao exercício seguinte da fila de hoje.\n"
            "A barra de espaço e o Enter fazem o mesmo, depois que o exercício fecha.",
        )
        tema.aplicar_papel(self.btn_proximo, estilos.PRIMARIO)

        botoes = QDialogButtonBox(parent=self)
        botoes.addButton("Fechar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.rejected.connect(self.reject)
        for botao in (self.btn_proximo, self.btn_solucao, self.btn_facil, *botoes.buttons()):
            if isinstance(botao, QPushButton):
                botao.setAutoDefault(False)
                botao.setDefault(False)
        return [self.btn_proximo, self.btn_solucao, self.btn_facil, botoes]

    def _ligar_o_teclado(self) -> None:
        """As teclas da sessão. Ver `TECLAS_DE_AVANCO` para por que elas existem (S-540, r2).

        `QShortcut` na janela e não filtro de eventos: a guarda da S-20 existe para a janela
        principal, onde uma tecla pode ter de ser **cedida** a um campo de texto em foco. Aqui não
        há campo nenhum -- é um tabuleiro e três botões --, e a resposta é sempre a mesma.
        """
        for tecla in TECLAS_DE_AVANCO:
            atalho = QShortcut(QKeySequence(tecla), self)
            atalho.activated.connect(self.avancar)

    # -------------------------------------------------------------------------- a fila

    def _frase_da_agenda(self) -> str:
        """A frase do topo da coluna direita, e ela tem de saber por que a fila está vazia (S-540).

        **"Nada para revisar hoje" servia a duas situações opostas**, e uma delas não é problema
        nenhum: quem não extraiu exercício nenhum precisa extrair, e quem já revisou tudo precisa
        saber **quando** o material volta. A data do próximo vencimento e o tamanho da coleção são
        o que separa as duas -- ver `treino_declarado.frase_da_agenda`.
        """
        return declarado.frase_da_agenda(
            self.agenda,
            volta_em=revisao_espacada.proximo_vencimento(
                list(self._exercicios), self._baralho, hoje=self._hoje
            ),
            colecao=len(self._exercicios),
        )

    def avancar(self) -> None:
        """A tecla de avanço: passa adiante **só** com o exercício fechado (S-540, r2).

        Com o exercício em aberto ela não faz nada, e é de propósito: um `Enter` distraído no meio
        de uma combinação pularia o item sem resposta, e a agenda o contaria como visto. É a mesma
        razão de o `Enter` não revelar a solução -- ver `TECLAS_DE_AVANCO`.
        """
        if self.exercicio is not None and not self.tentativa.terminou:
            return
        if self.btn_proximo.isEnabled():
            self._proximo()

    def _proximo(self) -> None:
        """Vai para o exercício seguinte da fila, ou fecha a sessão quando ela acaba."""
        self._perda.esquecer()
        while self._posicao < len(self._fila):
            exercicio = self._exercicios.get(self._fila[self._posicao])
            self._posicao += 1
            if exercicio is not None:
                self._feitos += 1
                self._abrir(exercicio)
                return
        self._encerrar()

    def _encerrar(self) -> None:
        """O fim da fila: o resumo da sessão, e nenhum tabuleiro (S-540, r2).

        **Três defeitos numa tela só, e os três medidos em 2026-09-04.** A agenda continuava
        anunciando *"Hoje você tem 3 para revisar"* ao lado de *"Fila concluída"* -- duas frases que
        se contradizem na mesma coluna; o resumo não existia, e meia hora de sessão acabava sem
        nenhum número; e o tabuleiro ficava na última posição jogada, que já não é pergunta nenhuma.

        O resumo é `treino_declarado.frase_do_fim`, e ele vai para onde o tabuleiro estava
        (`lbl_vazio`): a agenda **se apaga**, porque uma agenda que continua anunciando a fila de
        meia hora atrás ao lado de "fila concluída" é a contradição que a fotografia mostrou.

        **Fila vazia na abertura não é sessão encerrada**, e por isso o resumo só aparece quando
        houve exercício: quem abre a janela num dia sem vencimento tem de ler *quando* o material
        volta (ver `_frase_da_agenda`), e não "0 exercício(s), nenhum lance jogado".
        """
        self.exercicio = None
        self.tentativa = declarado.Tentativa()
        self.lbl_vazio.setText(
            declarado.frase_do_fim(self._feitos, self._placar.sessao)
            if self._feitos
            else self._frase_da_agenda()
        )
        self.lbl_agenda.setText("")
        self.lbl_vez.setText("")
        self.lbl_recado.setText("")
        self.lbl_procedencia.setText("")
        self._mostrar_o_tabuleiro(False)
        self._pintar_placar()
        self.btn_solucao.setEnabled(False)
        self.btn_facil.setEnabled(False)
        self.btn_proximo.setEnabled(False)

    def _mostrar_o_tabuleiro(self, visivel: bool) -> None:
        """Some com o tabuleiro quando não há posição a olhar, e a frase toma o lugar (S-540, r2).

        **Um tabuleiro vazio em 60% da janela era a tela de "nada para revisar hoje"**: 64 casas
        desenhadas, nenhuma peça, e a frase espremida ao lado. Escondê-lo é metade da correção; a
        outra é a frase ir para onde o tabuleiro estava, porque uma janela inteiramente vazia com
        uma linha no canto não é melhor que um tabuleiro sem peças.

        **Os três botões da sessão somem junto.** *Próximo*, *Ver a solução* e *Foi fácil* são
        gestos sobre um exercício, e sem exercício eles já estavam desabilitados -- três controles
        cinza numa tela sem assunto só dizem que falta alguma coisa. O *Fechar* fica, porque é o
        que se faz ali.
        """
        mostrar = bool(visivel)
        self.tabuleiro.setVisible(mostrar)
        self.lbl_vez.setVisible(mostrar)
        self.lbl_vazio.setVisible(not mostrar)
        for botao in (self.btn_proximo, self.btn_solucao, self.btn_facil):
            botao.setVisible(mostrar)

    def _abrir(self, exercicio: taticas.Exercicio) -> None:
        self.exercicio = exercicio
        self.tentativa = declarado.Tentativa(lances=exercicio.lances)
        self._antes_do_exercicio = self._baralho.get(exercicio.chave)
        self._tabuleiro_do_exercicio = exercicio.tabuleiro()
        # **O tabuleiro nasce virado para quem resolve** -- as peças de quem joga embaixo. É o que
        # todo programa de táticas faz, e a razão é que resolver de cabeça para baixo é outro
        # exercício.
        self._virado = not self._tabuleiro_do_exercicio.turn
        self._mostrar_o_tabuleiro(True)
        self._marcar_o_erro(None)
        self._desenhar()
        self.lbl_vez.setText(
            "Brancas jogam e ganham." if self._tabuleiro_do_exercicio.turn else "Pretas jogam e ganham."
        )
        self.lbl_recado.setText("")
        self.lbl_procedencia.setText(exercicio.procedencia.frase())
        self.btn_solucao.setEnabled(True)
        self.btn_facil.setEnabled(False)
        self.btn_proximo.setEnabled(True)
        self._pintar_placar()
        # **O foco vai para o tabuleiro a cada exercício**, e não só na abertura: um clique no botão
        # "Próximo" o leva embora, e a tecla de avanço do exercício seguinte cairia nele.
        self.tabuleiro.setFocus()

    def _marcar_o_erro(self, move: chess.Move | None) -> None:
        """A seta vermelha sobre o lance recusado, ou nenhuma seta. Ver `COR_DO_ERRO`."""
        if move is None:
            self.tabuleiro.definir_setas(())
            return
        self.tabuleiro.definir_setas(
            [
                (
                    reading_index_from_square(move.from_square),
                    reading_index_from_square(move.to_square),
                    COR_DO_ERRO,
                )
            ]
        )

    def _desenhar(self) -> None:
        self.tabuleiro.mostrar_tabuleiro(self._tabuleiro_do_exercicio, virado=self._virado)

    # ----------------------------------------------------------------------- o lance jogado

    def jogar(self, move: chess.Move) -> None:
        """Um lance no tabuleiro do exercício. **Nada é gravado no livro** (S-539)."""
        if self.exercicio is None or self.tentativa.terminou:
            return
        if move not in self._tabuleiro_do_exercicio.legal_moves:
            # O widget só emite lance legal, e mesmo assim: `chess.Board.san` **levanta** para
            # lance ilegal, e uma exceção num slot do Qt derruba o processo sem mensagem. O que
            # custa uma linha aqui custaria a sessão inteira lá.
            return
        esperado = self.tentativa.esperado
        jogado = self._tabuleiro_do_exercicio.san(move)
        julgamento = declarado.classificar_o_lance(jogado, esperado)
        if julgamento.resultado == placar_mod.CERTO:
            self._acertou(move, jogado, esperado)
            return
        self.tentativa.errou()
        self.lbl_recado.setText(declarado.frase_do_resultado(julgamento, jogado, esperado))
        # **O lance errado é desfeito na tela**, e é o que "a árvore não muda" quer dizer aqui: o
        # modelo do widget jogou sobre a própria cópia, e sem redesenhar a pessoa fica olhando uma
        # posição que o exercício não tem.
        self._desenhar()
        # E o erro fica marcado onde ele aconteceu: a peça voltando sozinha para a origem, sem
        # nenhum sinal no tabuleiro, se lê como "soltei fora da casa" (S-541, r2).
        self._marcar_o_erro(move)
        # O motor entra **depois** do veredicto, e só para dizer o preço: a nota já foi dada.
        ficha = (jogado, esperado, bool(self._tabuleiro_do_exercicio.turn))
        if not self._perda.pedir(self._tabuleiro_do_exercicio, move, ficha):
            self._contar(julgamento)

    def _acertou(self, move: chess.Move, jogado: str, esperado: str) -> None:
        self._tabuleiro_do_exercicio.push(move)
        resposta = self.tentativa.acertou()
        if resposta:
            try:
                self._tabuleiro_do_exercicio.push_san(resposta)
            except ValueError:  # pragma: no cover - o gabarito já foi validado na extração
                logger.debug("A resposta %s não é legal na posição do exercício.", resposta)
        self._desenhar()
        self._marcar_o_erro(None)
        self._contar(declarado.classificar_o_lance(jogado, esperado))
        if self.tentativa.terminou:
            self._fechar_exercicio(certo=True)
        else:
            self.lbl_recado.setText(f"{jogado} — certo. Continue.")

    def _contar(self, julgamento: declarado.Julgamento) -> None:
        livro = self.exercicio.procedencia.livro if self.exercicio is not None else ""
        self._placar.registrar(livro, julgamento.resultado, perda=julgamento.perda)
        self._pintar_placar()
        self._gravar_o_placar()

    def _gravar_o_placar(self) -> None:
        """Manda o placar do livro para o disco, **a cada lance** (S-541, r2).

        **É o defeito 3 da segunda rodada, e ele era total.** `done()` gravava só o baralho de
        revisão; o placar vivia num objeto na memória, o `fechada → _mostrar_placar` da sala apenas
        repintava um rótulo, e `placar.json` **nunca era criado**. A spec afirmava "sobrevive a
        desligar ✅" sobre um arquivo que não existia.

        Por lance e não ao fechar, que é a decisão que a S-541 já tinha tomado para a sala: o
        arquivo tem uma linha por livro e alguns bytes, e o que se perde numa queda é justamente a
        sessão que ninguém vai repetir. (O baralho é o contrário -- ele reescreve o acervo inteiro.)

        **Sem origem, nada é gravado.** Um `Placar()` que não veio do disco -- o de um teste, o de
        quem colou uma posição à mão -- não tem para onde voltar, e `placar.gravar` cairia em
        `CAMINHO_PADRAO`, que é `data/placar.json` da árvore do programa: gravar ali seria escrever
        na instalação por causa de um objeto que ninguém pediu para persistir.
        """
        if self._placar.origem is None:
            return
        try:
            placar_mod.gravar(self._placar)
        except OSError as erro:  # pragma: no cover - disco cheio ou arquivo em uso
            logger.warning("O placar do treino não pôde ser gravado: %s", erro)

    def _chegou_a_perda(self, ficha: Any, antes: int, depois: int) -> None:
        jogado, esperado, brancas = ficha
        julgamento = declarado.classificar_o_lance(
            jogado, esperado, antes=antes, depois=depois, brancas=brancas
        )
        self.lbl_recado.setText(declarado.frase_do_resultado(julgamento, jogado, esperado))
        self._contar(julgamento)

    def _nao_veio_a_perda(self, ficha: Any, _mensagem: str) -> None:
        jogado, esperado, _brancas = ficha
        self._contar(declarado.classificar_o_lance(jogado, esperado))

    # ------------------------------------------------------------------------ o fim do item

    def revelar(self) -> None:
        """Mostra a linha inteira e fecha o exercício como não sabido."""
        if self.exercicio is None:
            return
        self.tentativa.revelar()
        self._mostrar_gabarito()
        self._fechar_exercicio(certo=False)

    def marcar_facil(self) -> None:
        """A nota `FACIL`, que o programa nunca dá sozinho. Ver `revisao_espacada.nota_do_treino`."""
        if self.exercicio is None:
            return
        self._agendar(revisao_espacada.FACIL)
        self.btn_facil.setEnabled(False)
        self.lbl_recado.setText("Marcado como fácil: ele volta bem mais tarde.")

    def _fechar_exercicio(self, *, certo: bool) -> None:
        nota = revisao_espacada.nota_do_treino(
            certo=certo, tentativas=self.tentativa.tentativas, viu_a_solucao=self.tentativa.revelou
        )
        self._agendar(nota)
        self.btn_solucao.setEnabled(False)
        self.btn_facil.setEnabled(certo and not self.tentativa.revelou)
        if certo:
            self._mostrar_gabarito()

    def _mostrar_gabarito(self) -> None:
        """A solução por extenso, o que ela faz e de onde ela veio -- **depois** de o exercício
        fechar. "Dá mate" ao lado do tabuleiro antes de a pessoa jogar é meia resposta."""
        if self.exercicio is None:
            return
        self.lbl_recado.setText(
            declarado.frase_do_gabarito(
                self.exercicio.lances,
                self.exercicio.procedencia.frase(),
                self.exercicio.desfecho,
            )
        )

    def _agendar(self, nota: int) -> None:
        """Agenda o item **a partir do estado de antes desta volta**. Ver `_antes_do_exercicio`."""
        if self.exercicio is None:
            return
        chave = self.exercicio.chave
        atual = self._antes_do_exercicio
        if atual is None:
            self._baralho[chave] = revisao_espacada.estado_inicial(chave, nota, hoje=self._hoje)
        else:
            self._baralho[chave] = revisao_espacada.proximo(atual, nota, hoje=self._hoje)

    def _pintar_placar(self) -> None:
        livro = self.exercicio.procedencia.livro if self.exercicio is not None else ""
        self.lbl_placar.setText(
            declarado.frase_do_placar(self._placar.sessao, self._placar.do_livro(livro))
        )

    # ---------------------------------------------------------------------------- o fim

    def done(self, a0: int) -> None:  # noqa: N802 - assinatura do Qt
        """Grava o baralho ao fechar, e **espera o motor** antes de morrer.

        Uma `QThread` destruída enquanto roda derruba o processo, e a medição da perda é a única
        que pode estar em curso quando alguém fecha a janela no meio de um exercício.
        """
        self._perda.esperar(3000)
        try:
            self._gravar(self._baralho)
        except OSError as erro:  # pragma: no cover - disco cheio ou arquivo em uso
            logger.warning("O baralho de revisão não pôde ser gravado: %s", erro)
        self.fechada.emit()
        super().done(a0)

    @property
    def baralho(self) -> dict[str, revisao_espacada.Estado]:
        """O que a sessão agendou até agora. É por aqui que o teste confere o adiamento."""
        return dict(self._baralho)
