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

**O clique não rola; o que o programa foca durante ele, quando o mouse sossega.** O Qt dá o foco ao
controle no *pressionar* do clique, antes de entregar o evento; rolar ali tirava o controle de baixo do
ponteiro, e o *soltar* caía noutro lugar -- medido pelo crítico no ciclo 6: na pele Foco a 1280x641, um
clique na parte de baixo da casa e7 do Estudo, com as pretas a jogar, rolava 19 px e jogava 1...e6; o
rádio «Pretas» do Resultado não marcava. O foco que o clique dá ao controle clicado fica onde está
(:func:`veio_do_mouse`): o controle já está à vista, onde o ponteiro está. Mas no mesmo clique um painel
pode mandar o foco a **outro** controle -- a linha da tabela da Rotulagem e da Revisão de texto da suíte
manda o foco à «Verdade da linha» (crítico, ciclo 7: com o seguidor calado ali, a verdade ficava com 0x0
px a 1280x641). E mostrá-lo logo depois do soltar mexia o conteúdo debaixo do ponteiro parado antes do
segundo clique de um duplo clique: na Rotulagem, com a rolagem no fim, o segundo clique na linha 4 caía
em «Aceitar leitura» e aceitava uma leitura que ninguém aceitou (crítico, ciclo 8). Esse foco aparece
**quando o mouse sossega** (:func:`mouse_sossegado`) -- nenhum botão apertado, e o intervalo do duplo
clique da plataforma passado desde o último soltar: o segundo clique cai onde o primeiro caiu --, ou na
primeira tecla, antes de ela chegar ao controle.

**A razão do foco, e não o ponteiro.** Quem diz qual foco é o do mouse é a razão do `QFocusEvent`
(:class:`_RazaoDoFoco`): o clique e a roda dão `MouseFocusReason`, o Tab dá a dele, o `setFocus()` do
programa dá `OtherFocusReason`. Perguntar ao `underMouse` do controle, como a primeira versão do ciclo
8, falhava quando a marca ficava velha -- o ponteiro que sai da janela sem o evento de saída, a rolagem
que se mexe sob o ponteiro parado --: a verdade, clicada antes, parecia «sob o ponteiro» no clique da
linha, e ficava fora da vista (o portão do teclado da suíte, com o clique que deixa a ação rodar).

**O foco que a janela devolve ao voltar espera o mesmo sossego.** Quando a janela volta a ser a ativa, o
Qt devolve o foco ao controle que o tinha (`ActiveWindowFocusReason`), e o Windows ativa a janela
**antes** de entregar o pressionar do clique que a reativou: se a roda tinha levado a vista para longe
daquele controle, rolar até ele ali tirava de baixo do ponteiro o controle clicado (achado pelo
construtor no ciclo 8, a sonda `c8/sonda_ativacao.py`: o «Aceitar» não recebia o clique). Esse foco
espera o intervalo do duplo clique inteiro (:func:`voltou_com_a_janela`): o clique que reativou a janela
chega dentro dele, e o foco da volta só aparece se o clique não o levou a outro controle; sem clique (o
Alt+Tab, o diálogo que fechou), aparece passado o intervalo, ou na primeira tecla. O Tab e o Shift+Tab
rolam na hora (:func:`veio_do_teclado`).

O gêmeo deste arquivo na suíte é `caissa.ui.widgets.foco_a_vista` (a suíte depende do tronco, não o
contrário).
"""

from __future__ import annotations

import time

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import QApplication, QScrollArea, QScrollBar, QWidget

__all__ = [
    "RolagemSegueOFoco",
    "intervalo_do_duplo_clique",
    "mostrar",
    "mouse_sossegado",
    "no_meio_do_clique",
    "seguidor_de",
    "seguir_o_foco",
    "veio_do_mouse",
    "veio_do_teclado",
    "voltou_com_a_janela",
]

#: A folga em volta do controle que a rolagem mostra, em px: a moldura do foco fica à vista.
FOLGA = 6

#: O intervalo do duplo clique do Qt, em ms, quando a aplicação não diz o dela.
INTERVALO_PADRAO_DO_DUPLO_CLIQUE = 400

#: As teclas que só modificam o clique ou a tecla seguinte: não mostram o foco que espera.
_MODIFICADORES = frozenset(tecla.value for tecla in (
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr,
    Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock, Qt.Key.Key_ScrollLock,
))


def _encaixar(barra: QScrollBar, inicio: int, fim: int, vista: int) -> None:
    """Põe o intervalo ``[inicio, fim)`` do conteúdo dentro dos ``vista`` px que a barra mostra: com a
    :data:`FOLGA` em volta quando cabe, e com menos folga quando só o controle cabe (a «Verdade da
    linha» da Rotulagem da suíte tem 549 px numa vista de 550, e a folga inteira a deixava com 3 px
    cortados -- crítico da fase 5, ciclo 7). Maior que a vista, o começo dele."""
    atual = barra.value()
    tamanho = fim - inicio
    if tamanho > vista:
        alvo = inicio - FOLGA
    else:
        folga = min(FOLGA, (vista - tamanho) // 2)
        if inicio - folga < atual:
            alvo = inicio - folga
        elif fim + folga > atual + vista:
            alvo = fim + folga - vista
        else:
            return
    barra.setValue(max(barra.minimum(), min(barra.maximum(), alvo)))


class _RazaoDoFoco(QObject):
    """A razão do último foco que um controle recebeu na aplicação.

    `QApplication.focusChanged` não diz a razão, e o `QFocusEvent` que a diz chega ao controle antes do
    sinal: o clique dá o foco ao controle clicado (ou a quem aceita o foco acima dele) com
    `MouseFocusReason`, e a roda também; o Tab e o Shift+Tab, com as deles; o `setFocus()` do programa,
    com `OtherFocusReason`. Um filtro só, na aplicação, para todos os seguidores, e ele só anota: o
    controle e a razão (o `FocusIn` vai também ao estilo, que não é um controle), e a hora do último
    soltar de um botão do mouse (:func:`mouse_sossegado`).
    """

    def __init__(self, aplicacao: QApplication) -> None:
        super().__init__(aplicacao)
        self.aplicacao = aplicacao
        self.controle: QWidget | None = None
        self.razao = Qt.FocusReason.OtherFocusReason
        self.soltou_em = float("-inf")
        aplicacao.installEventFilter(self)

    def eventFilter(self, objeto: QObject | None, evento: QEvent | None) -> bool:  # noqa: N802 - assinatura do Qt
        if evento is None:
            return False
        tipo = evento.type()
        if tipo == QEvent.Type.FocusIn and isinstance(objeto, QWidget):
            self.controle = objeto
            self.razao = evento.reason()  # type: ignore[attr-defined]  # o FocusIn é um QFocusEvent
        elif tipo == QEvent.Type.MouseButtonRelease:
            self.soltou_em = time.monotonic()
        return False


_RAZAO: list[_RazaoDoFoco] = []


def _razao_do_foco() -> _RazaoDoFoco | None:
    """O anotador da razão do foco da aplicação de agora, posto nela na primeira vez."""
    aplicacao = QApplication.instance()
    if not isinstance(aplicacao, QApplication):
        return None
    if not _RAZAO or sip.isdeleted(_RAZAO[0]) or _RAZAO[0].aplicacao is not aplicacao:
        _RAZAO[:] = [_RazaoDoFoco(aplicacao)]
    return _RAZAO[0]


def no_meio_do_clique() -> bool:
    """Um botão do mouse está apertado: o clique está entre o pressionar e o soltar."""
    return QApplication.mouseButtons() != Qt.MouseButton.NoButton


def intervalo_do_duplo_clique() -> int:
    """O intervalo do duplo clique da plataforma, em ms (`QStyleHints.mouseDoubleClickInterval`): o
    segundo clique de um duplo clique chega dentro dele, e até lá o que está sob o ponteiro não muda."""
    dicas = QApplication.styleHints()
    if dicas is None:
        return INTERVALO_PADRAO_DO_DUPLO_CLIQUE
    return dicas.mouseDoubleClickInterval()


def mouse_sossegado() -> bool:
    """Nenhum botão apertado, e o intervalo do duplo clique passado desde o último soltar."""
    if no_meio_do_clique():
        return False
    razao = _razao_do_foco()
    if razao is None:
        return True
    return (time.monotonic() - razao.soltou_em) * 1000 >= intervalo_do_duplo_clique()


def veio_do_mouse(controle: QWidget) -> bool:
    """O foco que ``controle`` acaba de receber é o do mouse sobre ele, e a rolagem não se mexe: o
    clique nele, ou a roda -- a razão do `QFocusEvent` dele é `MouseFocusReason` (:class:`_RazaoDoFoco`).
    O foco que o programa manda a outro controle no mesmo clique tem outra razão (o `setFocus()`,
    `OtherFocusReason`), e é mostrado quando o mouse sossega; o Tab e o Shift+Tab rolam até o controle,
    também quando ele está sob o ponteiro parado."""
    razao = _razao_do_foco()
    return razao is not None and razao.controle is controle and razao.razao == Qt.FocusReason.MouseFocusReason


def voltou_com_a_janela(controle: QWidget) -> bool:
    """O foco que ``controle`` acaba de receber é o que a janela devolve ao voltar a ser a ativa
    (`ActiveWindowFocusReason`): o controle que tinha o foco quando ela deixou de ser. O pressionar do
    clique que a reativou chega depois dele."""
    razao = _razao_do_foco()
    return (razao is not None and razao.controle is controle
            and razao.razao == Qt.FocusReason.ActiveWindowFocusReason)


def veio_do_teclado(controle: QWidget) -> bool:
    """O foco que ``controle`` acaba de receber é o do Tab ou do Shift+Tab: a rolagem vai na hora."""
    razao = _razao_do_foco()
    return (razao is not None and razao.controle is controle
            and razao.razao in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason))


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
        self._pendente: QWidget | None = None
        self._esperando = False
        self._sossego = QTimer(self)
        self._sossego.setSingleShot(True)
        self._sossego.setTimerType(Qt.TimerType.PreciseTimer)
        self._sossego.timeout.connect(self._sossegou)
        aplicacao = QApplication.instance()
        if isinstance(aplicacao, QApplication):
            _razao_do_foco()
            aplicacao.focusChanged.connect(self._foco_mudou)

    @pyqtSlot(QWidget, QWidget)
    def _foco_mudou(self, _antigo: QWidget | None, novo: QWidget | None) -> None:
        # Primeiro se há foco novo e se a rolagem vive: a rolagem destruída com o foco dentro (o
        # diálogo de bases depois da pergunta) limpa o foco no destrutor, quando a rolagem já se foi
        # e este seguidor, filho dela, ainda não.
        if not self._ligado or novo is None or sip.isdeleted(self._rolagem):
            return
        if self._esperando and novo is not self._pendente:
            self._parar_de_esperar()  # o foco que esperava saiu dele
        conteudo = self._rolagem.widget()
        if conteudo is None or not conteudo.isAncestorOf(novo) or veio_do_mouse(novo):
            return
        if not veio_do_teclado(novo) and (voltou_com_a_janela(novo) or not mouse_sossegado()):
            self._esperar_o_sossego(novo)
            return
        mostrar(self._rolagem, novo)

    def _esperar_o_sossego(self, controle: QWidget) -> None:
        """Mostra ``controle`` quando o mouse sossegar -- nenhum botão apertado e o intervalo do duplo
        clique passado desde o último soltar (o relógio para no pressionar e recomeça no soltar) --, ou
        na primeira tecla que não é só um modificador, antes de ela chegar a ele. O filtro fica na
        aplicação só durante a espera."""
        self._pendente = controle
        aplicacao = QApplication.instance()
        if not self._esperando and aplicacao is not None:
            aplicacao.installEventFilter(self)
            self._esperando = True
        if no_meio_do_clique():
            self._sossego.stop()  # o soltar arma o relógio
        else:
            self._sossego.start(intervalo_do_duplo_clique())

    def eventFilter(self, objeto: QObject | None, evento: QEvent | None) -> bool:  # noqa: N802 - assinatura do Qt
        if self._esperando and evento is not None:
            tipo = evento.type()
            if tipo in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
                self._sossego.stop()
            elif tipo == QEvent.Type.MouseButtonRelease:
                self._sossego.start(intervalo_do_duplo_clique())
            elif tipo == QEvent.Type.KeyPress and evento.key() not in _MODIFICADORES:  # type: ignore[attr-defined]
                self._mostrar_o_pendente()
        return super().eventFilter(objeto, evento)

    def _sossegou(self) -> None:
        if not no_meio_do_clique():
            self._mostrar_o_pendente()

    def _parar_de_esperar(self) -> QWidget | None:
        """Tira o filtro e o relógio, e devolve o controle que esperava."""
        self._sossego.stop()
        aplicacao = QApplication.instance()
        if self._esperando and aplicacao is not None:
            aplicacao.removeEventFilter(self)
        self._esperando = False
        controle, self._pendente = self._pendente, None
        return controle

    def _mostrar_o_pendente(self) -> None:
        controle = self._parar_de_esperar()
        if (controle is None or not self._ligado or sip.isdeleted(controle)
                or sip.isdeleted(self._rolagem) or QApplication.focusWidget() is not controle):
            return
        mostrar(self._rolagem, controle)

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
