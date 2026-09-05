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

**E como esta suíte lê o que o Qt desenhou.** `renderizar`, `pixels_diferentes`, `cor_em` e `tinta`
estão aqui pelo mesmo motivo de `aplicacao()`: são a régua, e uma régua copiada em quatro arquivos
é quatro réguas. A cor de um estado -- marcado, focado, desabilitado -- só se afirma comparando
dois desenhos, e sob `offscreen` **não há fonte**: mede-se fundo e traço, nunca glifo.
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


def renderizar(widget: Any) -> Any:
    """O widget desenhado num `QImage`, para amostrar a cor de um pixel."""
    return widget.grab().toImage()


REPINTURA_LIMITE_MS = 1_500
"""Teto da espera de `assentado`. Alto de propósito: ele nunca é atingido quando o desenho é
estável, e é ele que separa "ainda não repintou" de "não vai repintar"."""

REPINTURA_QUIETA_MS = 50
"""Quanto tempo o desenho precisa ficar **igual** para `assentado` aceitá-lo.

Não é "espere 50 ms": é "só aceite depois de 50 ms sem mudança". A diferença importa porque um
prazo fixo mede a máquina e um período de quietude mede o desenho -- e é o desenho que se está
fotografando. Cinquenta milissegundos é mais que a volta da linha de eventos e menos que o
repolimento de folha que a S-553 mediu (~350 ms na pior das três peles)."""


def assentado(widget: Any, *, limite_ms: int = REPINTURA_LIMITE_MS, quieto_ms: int = REPINTURA_QUIETA_MS) -> Any:
    """O widget desenhado **depois** de o repintar acontecer: gira até o desenho parar de mudar.

    **Um teste que fotografa antes do repintar passa em verde sobre defeito**, e isto foi medido no
    próprio instrumento do projeto em 2026-09-05: `scratchpad/exec_final/prova_indicador.py` girava
    120 ms entre trocar o estado e fotografar, e a pele "Fita" respondia **0 px** de diferença entre
    marcado e desmarcado -- o mesmo número que o defeito que a S-553 tinha acabado de fechar. Com
    350 ms as três peles respondiam 56 px na caixa e 84 no rádio. Não havia defeito nenhum: havia
    uma régua curta.

    **A causa é o polimento do QSS, e ele não é síncrono.** Trocar a folha de estilo -- ou um estado
    que a folha desenhe -- agenda `unpolish`/`polish` e um `update()`; quem chama `processEvents()`
    uma vez pode pegar o widget entre os dois. Um número maior de milissegundos seria a mesma aposta
    com outro número: o que se quer não é "espere 350 ms", é "espere o desenho parar de mudar", e é
    o que `quieto_ms` afirma -- dois desenhos iguais separados por esse intervalo.

    **Dois iguais em seguida não bastariam**, e é a armadilha que este parágrafo existe para marcar:
    antes do repintar os dois são iguais **e velhos**. O período de quietude é o que distingue "não
    mudou mais" de "ainda não mudou".

    Devolve o último `QImage`. No teto, devolve o que houver -- um desenho que nunca estabiliza
    (animação, cursor piscando) é assunto de quem chamou, e travar a suíte não ajudaria a
    diagnosticá-lo.
    """
    import time

    app = aplicacao()
    fim = time.monotonic() + limite_ms / 1000
    anterior = None
    desde = 0.0
    while time.monotonic() < fim:
        app.processEvents()
        atual = widget.grab().toImage()
        agora = time.monotonic()
        if anterior is not None and atual == anterior:
            if (agora - desde) * 1000 >= quieto_ms:
                return atual
        else:
            anterior, desde = atual, agora
        time.sleep(0.005)
    return anterior if anterior is not None else widget.grab().toImage()


def pixels_diferentes(antes: Any, depois: Any) -> int:
    """Quantos pixels os dois desenhos têm diferentes. Tamanhos diferentes levantam.

    Levanta em vez de devolver "muitos": dois desenhos de tamanhos diferentes querem dizer que o
    estado **moveu o layout**, e é o defeito que se está medindo -- não a medição dele.
    """
    if antes.size() != depois.size():
        raise AssertionError(f"o estado mudou o tamanho do widget: {antes.size()} != {depois.size()}")
    return sum(
        1
        for x in range(antes.width())
        for y in range(antes.height())
        if antes.pixel(x, y) != depois.pixel(x, y)
    )


def cor_em(imagem: Any, x: int, y: int) -> str:
    """O pixel `(x, y)` como `#rrggbb`, que é a forma que `ui/tokens.py` fala."""
    valor = imagem.pixel(x, y)
    return f"#{(valor >> 16) & 255:02x}{(valor >> 8) & 255:02x}{valor & 255:02x}"


def tinta(imagem: Any, fundo: str) -> tuple[str, int]:
    """A tinta **mais forte** do desenho contra `fundo`, e quantos pixels não são o fundo.

    Mais forte, e não a média: o traço de um ícone de 16 px tem meia dúzia de pixels cheios e o
    resto é antialiasing, e uma média mede quanta tinta há em vez de qual é a tinta. O que o
    critério de um ícone apagado precisa saber é se **o traço** apagou.

    A régua é `tokens.razao_de_contraste`, que é a do produto (S-146): uma segunda conta de WCAG
    escrita aqui poderia discordar da que a paleta usa para se aprovar.
    """
    from chess_diagram_ocr.ui import tokens

    forte, razao, quantos = fundo, 0.0, 0
    for x in range(imagem.width()):
        for y in range(imagem.height()):
            cor = cor_em(imagem, x, y)
            if cor == fundo:
                continue
            quantos += 1
            candidata = tokens.razao_de_contraste(cor, fundo)
            if candidata > razao:
                forte, razao = cor, candidata
    return forte, quantos


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
