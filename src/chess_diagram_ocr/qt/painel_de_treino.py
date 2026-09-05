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
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.qt.tabuleiro_de_jogo import TabuleiroDeJogo
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.ui import espaco, estilos, tipografia, tokens
from chess_diagram_ocr.ui import treino_declarado as declarado
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken

logger = logging.getLogger(__name__)

__all__ = [
    "TEMPO_DA_PERDA_MS",
    "ExtratorDeTaticas",
    "JanelaDeTreino",
    "PerdaDoLance",
    "extrair_com_dialogo",
]

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
        """
        fora = QHBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.folga())

        esquerda = QVBoxLayout()
        esquerda.setSpacing(espaco.folga())
        self.tabuleiro = TabuleiroDeJogo(self)
        self.tabuleiro.lance.connect(self.jogar)
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
        self.lbl_agenda = QLabel(declarado.frase_da_agenda(self.agenda), self)
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

    def _botoes(self) -> list[QWidget]:
        """Os três da sessão, mais o Fechar. Um por linha: a coluna é estreita e eles são gestos
        diferentes -- ver a solução desiste do exercício, e "foi fácil" é um julgamento."""
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
        tema.aplicar_papel(self.btn_proximo, estilos.PRIMARIO)

        botoes = QDialogButtonBox(parent=self)
        botoes.addButton("Fechar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.rejected.connect(self.reject)
        return [self.btn_proximo, self.btn_solucao, self.btn_facil, botoes]

    # -------------------------------------------------------------------------- a fila

    def _proximo(self) -> None:
        """Vai para o exercício seguinte da fila, ou fecha a sessão quando ela acaba."""
        self._perda.esquecer()
        while self._posicao < len(self._fila):
            exercicio = self._exercicios.get(self._fila[self._posicao])
            self._posicao += 1
            if exercicio is not None:
                self._abrir(exercicio)
                return
        self.exercicio = None
        self.tentativa = declarado.Tentativa()
        self.lbl_vez.setText("")
        self.lbl_recado.setText("Fila de hoje concluída.")
        self.lbl_procedencia.setText("")
        self._pintar_placar()
        self.btn_solucao.setEnabled(False)
        self.btn_facil.setEnabled(False)
        self.btn_proximo.setEnabled(False)

    def _abrir(self, exercicio: taticas.Exercicio) -> None:
        self.exercicio = exercicio
        self.tentativa = declarado.Tentativa(lances=exercicio.lances)
        self._antes_do_exercicio = self._baralho.get(exercicio.chave)
        self._tabuleiro_do_exercicio = exercicio.tabuleiro()
        # **O tabuleiro nasce virado para quem resolve** -- as peças de quem joga embaixo. É o que
        # todo programa de táticas faz, e a razão é que resolver de cabeça para baixo é outro
        # exercício.
        self._virado = not self._tabuleiro_do_exercicio.turn
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
        self._contar(declarado.classificar_o_lance(jogado, esperado))
        if self.tentativa.terminou:
            self._fechar_exercicio(certo=True)
        else:
            self.lbl_recado.setText(f"{jogado} — certo. Continue.")

    def _contar(self, julgamento: declarado.Julgamento) -> None:
        livro = self.exercicio.procedencia.livro if self.exercicio is not None else ""
        self._placar.registrar(livro, julgamento.resultado, perda=julgamento.perda)
        self._pintar_placar()

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
