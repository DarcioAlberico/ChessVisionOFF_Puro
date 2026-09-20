"""Trabalho pesado fora da linha de eventos, com o resultado voltando por sinal.

**Por que existe.** Ler uma página são três coisas caras -- renderizar o PDF, detectar os
diagramas e rodar o `torch` sobre cada casa -- e nenhuma delas cabe na linha de eventos: uma
página de nove diagramas tranca a janela por segundos, e uma janela trancada no Windows vira
"o programa não está respondendo" na cara de quem só esperava.

**Um `QThread` genérico, e não um por operação.** O que muda entre renderizar, detectar e ler
é a função; o que não muda é o par "avisa quando terminar / avisa quando quebrar". A tradução
da falha para pt-BR fica aqui, num lugar só, e é a mesma `message_for` que os 40 comandos de
linha usam -- a janela não deve ser a única superfície do projeto que erra em inglês.
"""

from __future__ import annotations

import logging
import sys
import traceback
from collections.abc import Callable
from functools import partial
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from chess_diagram_ocr.cli import message_for

logger = logging.getLogger(__name__)

__all__ = ["INTERVALO_DE_TROCA_S", "DeteccaoDeFundo", "Tarefa", "ceder_a_interface", "manter_viva", "rastro_de"]

INTERVALO_DE_TROCA_S = 0.0001
"""De quanto em quanto o interpretador troca de thread enquanto há tarefa rodando (OCR_UI 15).

**O padrão do Python é 5 ms, e ele é o que travava a aba Dataset por 55 ms.** A tarefa que lê o
`labels.csv` roda numa `QThread`, mas roda **Python** (a legalidade de cada FEN, linha a linha), e
Python segura o GIL. Cada evento que o Qt entrega à janela durante essa leitura -- e uma troca de
aba são 442 chamadas de `eventFilter` -- precisa do GIL de volta, e espera até o próximo ponto de
troca. Medido pelo arnês `caissa.ui.audit.bloqueio` sobre `1937 Kemeri.pdf` (2026-09-16):

| intervalo | aba Dataset, 1.ª vez | trocar de aba durante a leitura | a leitura inteira |
|---|---|---|---|
| 5 ms (padrão) | **54,6 ms** | 7,0 ms | 678 ms |
| 0,5 ms | 7,8 ms | 7,2 ms | 816 ms |
| 0,1 ms | 6,0 ms | 2,6 ms | 814 ms |

A leitura fica 20 % mais lenta e a interface deixa de travar. É a troca certa para um programa
cujo trabalho pesado roda ao fundo justamente para a janela continuar respondendo; 0,5 ms porque
0,1 ms não compra nada a mais e cobra o mesmo."""

_cedeu = False


def ceder_a_interface() -> None:
    """Encurta o intervalo de troca do interpretador. Uma vez por processo; ver a tabela acima.

    Chamada quando a primeira `Tarefa` é construída: antes dela não há concorrência pelo GIL, e
    depois dela há sempre a possibilidade. Nunca **alonga** um intervalo que alguém já encurtou.
    """
    global _cedeu
    if _cedeu:
        return
    _cedeu = True
    if sys.getswitchinterval() > INTERVALO_DE_TROCA_S:
        sys.setswitchinterval(INTERVALO_DE_TROCA_S)


class Tarefa(QThread):
    """Roda `funcao()` numa thread e devolve o que ela devolver.

    O resultado vai em `pronto`; a falha vai em `falhou`, com a mensagem já em pt-BR **e** a
    exceção original. As duas coisas porque quem mostra a mensagem e quem decide o que fazer
    são códigos diferentes: a barra de status quer a frase, e o tratamento de "nenhum tabuleiro
    detectado" quer o tipo -- que é informação e não erro, e não pode virar caixa vermelha.

    **E o rastro completo fica em `rastro`** (OCR_UI ciclo 2, passo A10). A frase em pt-BR é o que
    se lê; o traceback é o que se cola num relato -- e até aqui ele só existia no log, que a caixa
    de erro mandava a pessoa ir procurar. Formatado **na thread**, no instante da falha, porque é
    ali que a pilha está inteira; a caixa o mostra em «Detalhes» e o botão «Copiar» o leva junto.
    """

    pronto = pyqtSignal(object)
    falhou = pyqtSignal(str, object)

    def __init__(self, funcao: Callable[[], Any], *, parent: Any = None, nome: str = "tarefa") -> None:
        super().__init__(parent)
        self._funcao = funcao
        self._nome = nome
        self.rastro = ""
        """O traceback formatado da falha, ou vazio enquanto a tarefa não falhou."""
        # Na construção, e não num `start` sobrescrito: o vigia de `test_busy` e o portão
        # `caissa.ui.audit.execucao` atribuem cada `QThread.start` ao arquivo de `qt/` que o
        # chamou, e um `start` daqui seria o chamador de todas as threads do programa.
        ceder_a_interface()

    def run(self) -> None:
        """O `except` largo é deliberado: aqui é a borda da thread.

        Uma exceção que escapa de `run()` não sobe para lugar nenhum -- ela morre com a thread,
        e o sintoma é uma barra de progresso que fica girando para sempre. Todo caminho de saída
        tem de emitir um dos dois sinais, e é por isso que este `except BaseException` não
        seleciona tipo.
        """
        try:
            resultado = self._funcao()
        except Exception as exc:  # noqa: BLE001 - ver o docstring: é a borda da thread
            logger.exception("A tarefa %s falhou.", self._nome)
            self.rastro = rastro_de(exc)
            self.falhou.emit(message_for(exc), exc)
            return
        self.pronto.emit(resultado)

    @property
    def nome(self) -> str:
        """Como a tarefa se chama para a pessoa -- «leitura», «detecção» --; vai no título da caixa."""
        return self._nome


def rastro_de(excecao: object) -> str:
    """O traceback formatado de uma exceção, ou a `repr` dela quando não há pilha.

    A exceção guarda a própria pilha em `__traceback__`, então quem só tem o objeto -- o slot do
    outro lado do sinal -- ainda consegue o rastro inteiro. Nunca levanta: um erro ao formatar o
    erro seria a caixa de falha falhando.
    """
    if not isinstance(excecao, BaseException):
        return repr(excecao)
    try:
        return "".join(traceback.format_exception(type(excecao), excecao, excecao.__traceback__)).strip()
    except Exception:  # noqa: BLE001 - ver o docstring
        return repr(excecao)


class DeteccaoDeFundo(QObject):
    """A detecção dos diagramas da página exibida, ao fundo e sem trancar nada (S-68).

    **O critério de aceite da S-68 é que os retângulos apareçam antes de qualquer OCR**, e o
    porte para o Qt só os pedia pelo botão "Marcar diagramas" -- sem ele, um clique na página não
    achava caixa nenhuma. O `app_tkinter` tinha isto no `_overlay_worker`, e o corte o deixou.

    **Um pedido de cada vez, e só o último espera.** Virar dez páginas com a roda não enfileira
    dez detecções: enquanto uma roda, o pedido guardado é substituído pelo mais novo, e é ele que
    roda a seguir. As páginas puladas ficam sem caixa até serem exibidas de novo, que é quando
    voltam a ser pedidas.

    **Não tranca a janela, e é a diferença para `_rodar`.** Ninguém pediu esta detecção, então a
    falha dela vai para o log e não para uma caixa: a página continua legível no visualizador.

    **A thread não é filha deste objeto, e os sinais chegam por método ligado.** Um `QThread`
    destruído enquanto roda derruba o processo -- e quem descarta a janela sem `close()` (os
    testes, por `deleteLater`) destruiria este objeto com a detecção no meio. A thread vive em
    `_VIVAS` até terminar; as ligações a métodos deste objeto o PyQt desfaz sozinho quando ele
    morre, e uma `lambda` não teria esse cuidado.
    """

    achou = pyqtSignal(str, int, object)
    """`(documento, página, candidatos)`. Quem decide se ainda interessa é quem recebe: a página
    pode ter virado, e o livro pode ter trocado."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pedido: tuple[str, int, Callable[[], Any]] | None = None
        self._em_curso: tuple[str, int] | None = None
        self._tarefa: Tarefa | None = None

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def pedir(self, documento: str, pagina: int, funcao: Callable[[], Any]) -> None:
        """Detecte esta página assim que der. Substitui o pedido que ainda não começou."""
        self._pedido = (documento, pagina, funcao)
        self._comecar()

    def parar(self, espera_ms: int) -> bool:
        """Esquece o pedido guardado e espera a detecção em curso. Devolve se ela terminou."""
        self._pedido = None
        tarefa = self._tarefa
        if tarefa is None:
            return True
        terminou = bool(tarefa.wait(espera_ms))
        if terminou:
            # O `finished` ainda vai chegar pela fila e cair em `_terminou`, que não acha pedido.
            # Mas quem perguntou "acabou?" merece a resposta agora, e não na próxima volta.
            self._tarefa = None
        return terminou

    def _comecar(self) -> None:
        if self._tarefa is not None or self._pedido is None:
            return
        documento, pagina, funcao = self._pedido
        self._pedido = None
        self._em_curso = (documento, pagina)
        tarefa = manter_viva(Tarefa(funcao, nome=f"detecção da página {pagina + 1}"))
        tarefa.pronto.connect(self._pronto)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        self._tarefa = tarefa
        tarefa.start()

    def _pronto(self, candidatos: Any) -> None:
        # Sem `assert`: uma exceção num slot derruba o processo, e não há o que afirmar aqui.
        if self._em_curso is None:
            return
        documento, pagina = self._em_curso
        self.achou.emit(documento, pagina, candidatos)

    def _falhou(self, mensagem: str, _excecao: object) -> None:
        if self._em_curso is None:
            return
        documento, pagina = self._em_curso
        logger.warning("A detecção da página %d de %s falhou: %s", pagina + 1, documento, mensagem)

    def _terminou(self) -> None:
        self._tarefa = None
        self._em_curso = None
        self._comecar()


_VIVAS: set[Tarefa] = set()
"""As tarefas em curso, seguras por referência até terminarem. Ver `manter_viva`."""


def manter_viva(tarefa: Tarefa) -> Tarefa:
    """Segura a tarefa até ela terminar, **sem pai**. Devolve-a, para caber numa linha.

    **Uma `Tarefa` com pai widget derruba o processo, e o modo de falha é este** (F9-C2): o Qt
    destrói os filhos junto com o pai, e o destrutor de `QThread` **aborta** se a thread ainda
    estiver rodando -- `STATUS_STACK_BUFFER_OVERRUN`, sem uma linha de traceback, porque a queda é
    no C++. Fechar a janela com uma leitura de CSV em curso é o caso normal, não o exótico: o
    arnês `caissa.ui.audit.bloqueio` fecha a janela seis vezes por execução e caiu nas seis.

    Sem pai a thread não é destruída com o widget; a referência daqui é o que impede o coletor do
    Python de fazer o mesmo. É o que `DeteccaoDeFundo` já fazia desde a S-68, agora com nome, para
    o segundo e o terceiro chamador não terem de redescobri-lo.
    """
    _VIVAS.add(tarefa)
    tarefa.finished.connect(partial(_soltar, tarefa))
    return tarefa


def _soltar(tarefa: Tarefa) -> None:
    _VIVAS.discard(tarefa)
    tarefa.deleteLater()
