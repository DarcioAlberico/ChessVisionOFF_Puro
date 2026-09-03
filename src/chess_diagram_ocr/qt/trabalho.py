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
from collections.abc import Callable
from functools import partial
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from chess_diagram_ocr.cli import message_for

logger = logging.getLogger(__name__)

__all__ = ["DeteccaoDeFundo", "Tarefa"]


class Tarefa(QThread):
    """Roda `funcao()` numa thread e devolve o que ela devolver.

    O resultado vai em `pronto`; a falha vai em `falhou`, com a mensagem já em pt-BR **e** a
    exceção original. As duas coisas porque quem mostra a mensagem e quem decide o que fazer
    são códigos diferentes: a barra de status quer a frase, e o tratamento de "nenhum tabuleiro
    detectado" quer o tipo -- que é informação e não erro, e não pode virar caixa vermelha.
    """

    pronto = pyqtSignal(object)
    falhou = pyqtSignal(str, object)

    def __init__(self, funcao: Callable[[], Any], *, parent: Any = None, nome: str = "tarefa") -> None:
        super().__init__(parent)
        self._funcao = funcao
        self._nome = nome

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
            self.falhou.emit(message_for(exc), exc)
            return
        self.pronto.emit(resultado)


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
        tarefa = Tarefa(funcao, nome=f"detecção da página {pagina + 1}")
        tarefa.pronto.connect(self._pronto)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        _VIVAS.add(tarefa)
        tarefa.finished.connect(partial(_soltar, tarefa))
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
"""As detecções em curso, seguras por referência até terminarem. Ver `DeteccaoDeFundo`."""


def _soltar(tarefa: Tarefa) -> None:
    _VIVAS.discard(tarefa)
    tarefa.deleteLater()
