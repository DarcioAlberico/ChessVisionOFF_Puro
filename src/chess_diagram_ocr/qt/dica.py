"""A dica que explica um controle desabilitado (S-32/S-403), no Qt.

**Aqui a maior parte do módulo do Tk desaparece, e vale registrar o que era.** `ui/tooltip.py`
tem 147 linhas para uma coisa que o Tk não traz: uma `Toplevel` sem moldura, um `after` de 450 ms,
o cancelamento dele, e -- por causa da S-402 -- um `<Destroy>` para esquecer o agendamento quando
o widget morre antes de a dica aparecer. Aquele último não era zelo: sair de uma barra que a troca
de pele destrói no mesmo gesto deixava um `after` marcado para um widget que não existia mais, e o
`TclError` subia como traceback na saída padrão do programa.

O Qt traz `QToolTip`, e com ele **os três defeitos somem por construção**: o tempo é do sistema, o
cancelamento é do sistema, e uma dica cujo widget morreu é fechada pelo próprio Qt. O que resta a
este módulo são as duas decisões que continuam sendo do projeto:

1. **O tempo é um só na janela inteira** (S-403). O `board_widget.py` tinha a segunda dica do
   programa, com 350 ms contra os 450 daqui -- duas dicas com tempos diferentes na mesma tela não
   são duas decisões, são uma decisão tomada duas vezes. Impor o tempo do projeto custa mais aqui
   do que a frase acima sugere: o Qt **não** expõe o atraso como propriedade, e sim como a dica de
   estilo `SH_ToolTip_WakeUpDelay`. Ver `_EstiloComAtrasoDeDica`.
2. **A cor é a do tema** (S-147). O fundo era um amarelo-pálido cravado e a letra vinha do tema:
   sob cromo escuro isso dava letra clara sobre `#ffffe0` -- a única explicação que um botão
   desabilitado oferece, ilegível. Quem resolve isso aqui é a regra `QToolTip` da folha de
   `qt/tema.py`, que já sai de `tokens.SUPERFICIE_DICA` e de `tokens.sobre_superficie`.

**E a dica de um controle desabilitado precisa de um empurrão**, que é o item da S-32 e a única
parte não trivial deste arquivo. Ver `DicaEmDesabilitado`.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle, QToolTip, QWidget

logger = logging.getLogger(__name__)

__all__ = ["ATRASO_DA_DICA", "DicaEmDesabilitado", "ajustar_atraso", "atraso_em_vigor", "dica_em"]

ATRASO_DA_DICA = 450
"""Tempo parado sobre o widget antes de a dica aparecer, em milissegundos.

Curto o bastante para quem está procurando explicação, longo o bastante para não piscar ao
atravessar a barra. **Uma constante, e não uma por dica** (S-403): o número não é uma propriedade
do widget que a mostra, é uma propriedade da janela.

É o mesmo valor de `ui/tooltip.TOOLTIP_DELAY_MS`, e o teste cobra a igualdade -- as duas janelas
do mesmo produto não podem responder ao ponteiro em tempos diferentes."""


class _EstiloComAtrasoDeDica(QProxyStyle):
    """O estilo da aplicação com **uma** dica de estilo trocada: o tempo de espera da dica.

    **Por que um estilo e não uma chamada.** `QToolTip` não tem `setWaitTime` -- a primeira
    versão deste módulo chamou assim mesmo, e o `AttributeError` caiu no `except` tolerante:
    a janela abria, o log dizia uma linha, e a S-403 simplesmente não valia. O tempo da dica
    no Qt não é propriedade de objeto nenhum, é a dica de estilo `SH_ToolTip_WakeUpDelay`, e
    quem responde por ela é o `QStyle`.

    `QProxyStyle` embrulha o estilo em vigor e delega tudo: o único `styleHint` que muda de
    resposta é este. Trocar o estilo inteiro para acertar um número mudaria a aparência de
    todos os widgets da janela para resolver um item sobre tempo.
    """

    def __init__(self, atraso: int) -> None:
        super().__init__()
        self._atraso = atraso

    def styleHint(  # noqa: N802 - assinatura do Qt
        self,
        hint: QStyle.StyleHint,
        option: object = None,
        widget: object = None,
        returnData: object = None,  # noqa: N803 - assinatura do Qt
    ) -> int:
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return self._atraso
        return super().styleHint(hint, option, widget, returnData)  # type: ignore[arg-type]


def ajustar_atraso(atraso: int = ATRASO_DA_DICA) -> bool:
    """Fixa o tempo de espera das dicas do processo inteiro. Chame uma vez, ao montar a janela.

    Devolve se conseguiu. Nunca levanta: uma dica que aparece no tempo de fábrica é pior que a
    do projeto e melhor que uma janela que não abre.

    **Devolve `bool` e não `None` de propósito.** A primeira versão devolvia `None`, e o teste
    dela não tinha o que afirmar além de "não levantou" -- que é exatamente o que uma
    implementação quebrada também faz. Foi assim que o `setWaitTime` inexistente passou por
    verde. Ver `_EstiloComAtrasoDeDica`.
    """
    aplicacao = QApplication.instance()
    if not isinstance(aplicacao, QApplication):
        logger.info("Sem QApplication: o atraso da dica não foi ajustado.")
        return False
    try:
        aplicacao.setStyle(_EstiloComAtrasoDeDica(atraso))
    except Exception as exc:  # noqa: BLE001 - aparência não derruba a ferramenta
        logger.info("Atraso da dica não ajustado (%s): vale o do sistema.", exc)
        return False
    return True


def atraso_em_vigor() -> int:
    """O que o estilo responde agora. Existe para o teste afirmar o efeito, e não a chamada."""
    aplicacao = QApplication.instance()
    if not isinstance(aplicacao, QApplication):  # pragma: no cover - erro de ordem
        return -1
    estilo = aplicacao.style()
    if estilo is None:  # pragma: no cover - aplicação sem estilo não acontece na prática
        return -1
    return int(estilo.styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay))


def dica_em(widget: QWidget, texto: str) -> QWidget:
    """Põe (ou troca) a dica do widget. Devolve o próprio widget, para caber na montagem.

    Texto vazio **apaga** a dica, e é o comportamento de `Tooltip.set_text`: o motivo de um botão
    estar desabilitado muda -- "não configurado" e "configurado e desligado" são situações
    diferentes --, e quando ele volta a estar habilitado não há mais o que explicar.
    """
    widget.setToolTip(texto)
    return widget


class DicaEmDesabilitado(QObject):
    """Faz a dica aparecer sobre um controle **desabilitado**. É o item da S-32.

    **O defeito que isto conserta é do Qt e não do projeto.** Um `QWidget` desabilitado não
    recebe eventos de ponteiro: o Qt os entrega ao pai. A consequência é que `setToolTip` num
    botão desabilitado não mostra nada -- e um botão cinza sem explicação é pior que um botão
    ausente, porque quem o vê não sabe se está quebrado, se falta configuração ou se falta
    seleção. É literalmente o critério de aceite da S-32, e o padrão do Qt o reprova.

    O conserto é ouvir o `ToolTip` no **pai**, achar qual filho desabilitado está sob o ponteiro
    e mostrar a dica dele à mão. Instale um por painel que tenha controles que nascem
    desabilitados; um por botão seria um `QObject` por controle sem nada a mais.

    Como `qt/atalhos.GuardaDeAtalhos`, ela nasce filha do painel para não ser coletada -- um
    filtro coletado deixa de ser chamado, e o sintoma seria a dica funcionar às vezes.
    """

    def __init__(self, painel: QWidget) -> None:
        super().__init__(painel)
        self._painel = painel
        # Sem isto o Qt suprime a dica de uma janela que não está ativa. É o caso de quem passa
        # o ponteiro por uma janela de fundo para lembrar o que um botão faz -- e, sob
        # `offscreen`, é o caso de toda janela, o que faria o teste medir o silêncio do Qt em
        # vez do comportamento deste filtro.
        painel.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        painel.installEventFilter(self)

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:  # noqa: N802 - assinatura do Qt
        """`True` quando mostrou a dica de um filho desabilitado; `False` para o resto seguir.

        Só o desabilitado é tratado aqui. Um filho habilitado recebe o próprio evento e mostra a
        própria dica pelo caminho normal do Qt, e interceptá-lo faria este filtro reimplementar,
        pior, o que já funciona.
        """
        if not isinstance(a1, QHelpEvent) or a1.type() != QEvent.Type.ToolTip:
            return False
        try:
            filho = self._painel.childAt(a1.pos())
            if filho is None or filho.isEnabled() or not filho.toolTip():
                return False
            QToolTip.showText(a1.globalPos(), filho.toolTip(), self._painel)
            return True
        except Exception:  # noqa: BLE001 - borda do laço de eventos, como em `qt/atalhos.py`
            logger.exception("A dica do controle desabilitado falhou.")
            return False
