"""A barra da sala de estudo: a fila de `qt/barra.py` com a tabela de `ui/barra_da_sala.py` (S-527).

**Este arquivo é a amarração, e ficou pequeno na S-528.** A fila -- `QAction` por ação, separador
entre grupos, dois níveis de botão, o "Mais ▾" com cabeçalho de grupo, o rearranjo por `cabem` e o
interruptor que não alterna duas vezes -- é `qt/barra.BarraEmFila`, porque nada dela é da sala: o
painel do PDF a usa igual desde a S-528. O que sobra aqui é dizer **qual** tabela a sala usa e
**quais** ações esta montagem tem (sem motor, o grupo `MOTOR` não existe -- S-33).

O nome `BarraDaSala` fica porque é por ele que o painel e os testes da S-527 a chamam, e porque
"a barra da sala" continua sendo o que ela é.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.qt.barra import LADO_DO_ICONE, PROPRIEDADE_DE_CABECALHO, BarraEmFila
from chess_diagram_ocr.ui import barra_da_sala as declarada

logger = logging.getLogger(__name__)

__all__ = ["LADO_DO_ICONE", "PROPRIEDADE_DE_CABECALHO", "BarraDaSala"]


class BarraDaSala(BarraEmFila):
    """A fila da sala de estudo, com ou sem motor."""

    def __init__(self, parent: QWidget | None, *, com_motor: bool, executar: Callable[[str], None]) -> None:
        super().__init__(
            parent,
            tabela=declarada,
            registros=declarada.acoes_para(com_motor=com_motor),
            executar=executar,
        )
