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
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from chess_diagram_ocr.cli import message_for

logger = logging.getLogger(__name__)


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
