"""Uma `QApplication` para o **processo** inteiro, e a plataforma sem tela.

**Duas regras, e as duas doem quando quebradas.**

1. *Uma só.* O Qt recusa a segunda `QApplication` do processo -- não com uma exceção legível,
   mas com `RuntimeError: A QApplication instance already exists` no melhor caso e uma queda
   do interpretador no pior. É a mesma razão do `tests/tk_root.py`, e por isso a forma é a
   mesma: quem precisa de janela chama `aplicacao()`, e ninguém constrói a sua.
2. *Sem tela.* `QT_QPA_PLATFORM=offscreen` é o que faz a suíte rodar num agente de CI sem
   servidor gráfico **e** o que impede uma janela de piscar na cara de quem roda a suíte na
   própria máquina. Precisa ser definida antes da primeira `QApplication` -- depois dela não
   tem mais efeito --, e é por isso que ela mora aqui em vez de num `setUp`.

Widget de teste não pendura na janela principal do processo pela mesma razão do `quadro()` do
`ambiente_de_teste`: o pai sobrevive ao módulo, e com ele os sinais ligados.
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from typing import Any

TEM_PYQT = importlib.util.find_spec("PyQt6") is not None
"""Se o PyQt6 está instalado. Sem ele os testes de janela **pulam**, e o `-ra` do `pyproject.toml`
faz o motivo aparecer no fim da rodada -- que é o que a S-417 exige de todo pulo: ser visível em
vez de virar um `s` no meio de quatro mil pontos.

**Ele deixou de ser um extra no corte do Tk (S-506)**, e a checagem continua valendo por outro
motivo: um `.venv` antigo, de antes de o PyQt6 entrar nas dependências de base, ainda não o tem --
e ali pular com o motivo escrito é melhor que um `ImportError` na coleta."""

MOTIVO = "o PyQt6 não está instalado (uv sync)"

_APLICACAO: Any = None


def aplicacao() -> Any:
    """A `QApplication` compartilhada. Levanta `SkipTest` sem o PyQt6 instalado."""
    global _APLICACAO
    if not TEM_PYQT:
        raise unittest.SkipTest(MOTIVO)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    if _APLICACAO is None:
        _APLICACAO = QApplication.instance() or QApplication([])
    return _APLICACAO


def esperar(janela: Any, *, limite_ms: int = 60_000) -> None:
    """Roda a linha de eventos até a janela ficar ociosa: tarefa, leitura adiada e detector.

    Sem isto o teste que dispara uma leitura termina antes da thread, e o `QThread` morre com
    o objeto Python dele -- o que derruba o processo inteiro e leva junto os testes seguintes,
    com uma mensagem (`QThread: Destroyed while thread is still running`) que não nomeia quem
    fez isso.
    """
    from PyQt6.QtCore import QEventLoop, QTimer

    def ocupada() -> bool:
        # Três coisas: a tarefa trancada, a leitura que o clique simples adiou pelo intervalo do
        # duplo clique, e o detector de fundo da página que acabou de aparecer (S-68).
        detector = getattr(janela, "_detector", None)
        adiada = getattr(janela, "_leitura_adiada", None)
        return (
            janela._tarefa is not None
            or bool(adiada is not None and adiada.isActive())
            or bool(detector is not None and detector.ocupado)
        )

    if not ocupada():
        return
    laco = QEventLoop()
    relogio = QTimer()
    relogio.timeout.connect(lambda: laco.quit() if not ocupada() else None)
    relogio.start(20)
    QTimer.singleShot(limite_ms, laco.quit)
    laco.exec()
    relogio.stop()


def descartar(widget: Any) -> None:
    """Destrói o widget **agora**, e não "quando a linha de eventos girar".

    **`processEvents` não apaga o que `deleteLater` marcou**, e isso custou um teste. O Qt guarda
    o `DeferredDelete` numa fila que `processEvents` pula de propósito -- a documentação dele diz
    que só a linha de eventos principal a esvazia, para que um laço aninhado não destrua o objeto
    de quem o abriu. Quem esvazia à mão é `sendPostedEvents(None, DeferredDelete)`.

    O sintoma de não fazer isto não aparece no teste que esqueceu: aparece **no vizinho**. A fita
    do Qt registra um seguidor em `comandos._SEGUIDORES`, que é estado de módulo compartilhado
    pelos dois frontends; enquanto o botão dela continua vivo o seguidor não é podado, e vinte
    fitas de teste deixaram vinte seguidores para o teste do Tk que conta quantos existem --
    `tests/test_ui_modo_selecionar_area.py`, que afirma "1" e leu "21".

    Use no lugar do par `addCleanup(widget.deleteLater)` sempre que o widget registrar alguma
    coisa fora de si -- seguidor de comando, repintura de tema, ouvinte de sinal global.
    """
    widget.deleteLater()
    from PyQt6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
