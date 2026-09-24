"""O controle que recebe o foco numa rolagem fica à vista, inteiro, também quando o foco vem de fora dela.

`QScrollArea.focusNextPrevChild` só rola até o foco que anda **dentro** da rolagem: o foco que entra
nela vindo de fora -- o Shift+Tab da barra de modos acima do Resultado, o Tab do rodapé da Galeria --
cai onde o controle estiver, e abaixo da dobra ele fica com 0 px à vista. Medido pelo crítico da
fase 5 do ciclo 2 OCR/UI (ciclo 5), a 1280x641 com a rolagem no topo, como quem chega a encontra:
«Esconder incerteza» no Resultado e «Copiar cabeçalhos para todos» na Galeria nas três peles,
«Comentário do lance» no Estudo e «Próximo pendente» na Revisão na Fita -- na Clássica bastavam duas
teclas a partir de «Abrir PDF». Foco invisível reprova sozinho.

**A troca de foco da aplicação, e não um filtro por controle**: a lista de bases do diálogo «Base de
partidas» se redesenha, e um filtro posto nos controles de quando a rolagem nasceu não veria as
caixas novas. **O controle inteiro, e não o cursor**: `ensureWidgetVisible` rola até a `microFocus`
de um campo de texto, e não rola nada quando o cursor já está à vista com o resto do campo cortado.

**Só o foco do teclado.** O Qt dá o foco ao controle no *pressionar* do clique, antes de entregar o
evento; rolar ali tirava o controle de baixo do ponteiro, e o *soltar* caía noutro lugar -- medido pelo
crítico no ciclo 6: na pele Foco a 1280x641, um clique na parte de baixo da casa e7 do Estudo, com as
pretas a jogar, rolava 19 px e jogava 1...e6; o rádio «Pretas» do Resultado não marcava. O foco que o
mouse dá fica onde está (:func:`veio_do_mouse`): o controle já está sob o ponteiro, à vista.

O gêmeo deste arquivo na suíte é `caissa.ui.widgets.foco_a_vista` (a suíte depende do tronco, não o
contrário).
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QPoint, QRect, Qt, pyqtSlot
from PyQt6.QtWidgets import QApplication, QScrollArea, QScrollBar, QWidget

__all__ = ["RolagemSegueOFoco", "mostrar", "seguidor_de", "seguir_o_foco", "veio_do_mouse"]

#: A folga em volta do controle que a rolagem mostra, em px: a moldura do foco fica à vista.
FOLGA = 6


def _encaixar(barra: QScrollBar, inicio: int, fim: int, vista: int) -> None:
    """Põe o intervalo ``[inicio, fim)`` do conteúdo dentro dos ``vista`` px que a barra mostra."""
    atual = barra.value()
    if fim - inicio + 2 * FOLGA > vista or inicio - FOLGA < atual:
        alvo = inicio - FOLGA
    elif fim + FOLGA > atual + vista:
        alvo = fim + FOLGA - vista
    else:
        return
    barra.setValue(max(barra.minimum(), min(barra.maximum(), alvo)))


def veio_do_mouse(controle: QWidget) -> bool:
    """O foco que ``controle`` acaba de receber veio do mouse: um botão está apertado (o clique dá
    o foco no pressionar), ou foi a roda -- o controle toma o foco dela (`Qt.FocusPolicy.WheelFocus`:
    as caixas de escolha e de número) e está sob o ponteiro. Estar sob o ponteiro parado não basta: o
    Tab que cai num botão sob o ponteiro rola até ele como até qualquer outro. Numa caixa de escolha
    sob o ponteiro parado, o Tab não rola (o sinal não diz se o foco veio da roda ou da tecla); ela
    já está à vista, ao menos onde o ponteiro está."""
    if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
        return True
    return controle.focusPolicy() == Qt.FocusPolicy.WheelFocus and controle.underMouse()


def mostrar(rolagem: QScrollArea, controle: QWidget) -> None:
    """Rola ``rolagem`` até ``controle`` ficar inteiro à vista, ou o começo dele quando não cabe."""
    conteudo = rolagem.widget()
    if conteudo is None or not conteudo.isAncestorOf(controle):
        return
    alvo = QRect(controle.mapTo(conteudo, QPoint(0, 0)), controle.size())
    vista = rolagem.viewport().size()
    _encaixar(rolagem.verticalScrollBar(), alvo.top(), alvo.top() + alvo.height(), vista.height())
    _encaixar(rolagem.horizontalScrollBar(), alvo.left(), alvo.left() + alvo.width(), vista.width())


class RolagemSegueOFoco(QObject):
    """Mostra, na ``rolagem``, todo controle dela que recebe o foco, venha o foco de onde vier.

    Filho da rolagem: morre com ela, e a ligação com a aplicação vai junto."""

    def __init__(self, rolagem: QScrollArea) -> None:
        super().__init__(rolagem)
        self._rolagem = rolagem
        self._ligado = True
        aplicacao = QApplication.instance()
        if isinstance(aplicacao, QApplication):
            aplicacao.focusChanged.connect(self._foco_mudou)

    @pyqtSlot(QWidget, QWidget)
    def _foco_mudou(self, _antigo: QWidget | None, novo: QWidget | None) -> None:
        if self._ligado and novo is not None and not veio_do_mouse(novo):
            mostrar(self._rolagem, novo)

    def desligar(self) -> None:
        """A rolagem volta a seguir só o foco que anda dentro dela -- o antes, para a sabotagem."""
        self._ligado = False


def seguir_o_foco(rolagem: QScrollArea) -> QScrollArea:
    """Liga :class:`RolagemSegueOFoco` à ``rolagem`` e a devolve (para montar numa linha)."""
    RolagemSegueOFoco(rolagem)
    return rolagem


def seguidor_de(rolagem: QScrollArea) -> RolagemSegueOFoco | None:
    """O seguidor ligado à ``rolagem``, se houver -- para o teste e para a sabotagem do portão."""
    return rolagem.findChild(RolagemSegueOFoco)
