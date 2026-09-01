"""A barra de ferramentas que quebra em vez de cortar, no Qt (S-151/S-501).

**A decisão não é reescrita, e é o item.** `ui/barra.arranjo` -- que distribui os itens em linhas
dada a largura -- é pura, não toca `tkinter`, e é afirmada nos três regimes em
`tests/test_ui_barra.py`. Este módulo a chama. O que ele escreve do zero é o `QLayout` que
executa o arranjo, e nada mais.

Vale registrar que o defeito da S-151 **existe igual no Qt**, e é por isso que a barra continua
sendo necessária. `QHBoxLayout` não reflui: quando falta largura ele encolhe os itens até o
mínimo e depois deixa a janela ter uma largura mínima maior que a tela. O sintoma é diferente do
Tk -- lá o item some sem aviso, aqui a janela deixa de poder ser estreitada --, mas a causa é a
mesma: nenhum dos dois sabe que a linha pode ser duas.

**Por que um `QLayout` e não `move()` num `resizeEvent`.** Posicionar à mão funciona até o
primeiro widget que muda de tamanho sozinho -- um botão que ganha ícone, um rótulo cujo texto
cresce. O `QLayout` recebe `invalidate()` de graça nesses casos, e é o que faz a barra
reagir ao conteúdo e não só à janela.

**`heightForWidth` é o que faz a janela caber.** Sem ele o Qt pergunta a altura antes de saber a
largura, e uma barra que vai ocupar duas linhas responde a altura de uma -- a segunda linha é
desenhada por cima do painel de baixo. É o equivalente da moldura por linha do Tk, e o motivo de
`hasHeightForWidth` devolver `True`.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget

from chess_diagram_ocr.ui.barra import ESPACO_ENTRE_ITENS, arranjo, linhas_necessarias

logger = logging.getLogger(__name__)

__all__ = ["ESPACO_ENTRE_ITENS", "BarraFluida", "LeiauteFluido", "arranjo", "linhas_necessarias"]


class LeiauteFluido(QLayout):
    """O `QLayout` que põe os itens em linhas conforme `ui/barra.arranjo` mandar.

    Não decide nada: ele mede cada item, pergunta ao arranjo em que linha cada um vai, e desenha.
    A separação é a mesma do outro frontend -- *a decisão é pura; o widget só executa* -- e é o
    que permite afirmar a quebra sem abrir janela.
    """

    def __init__(self, parent: QWidget | None = None, *, espaco: int = ESPACO_ENTRE_ITENS) -> None:
        super().__init__(parent)
        self._itens: list[QLayoutItem] = []
        self._espaco = espaco
        self.setContentsMargins(0, 0, 0, 0)

    # ------------------------------------------------------- o contrato mínimo de um QLayout
    #
    # Os cinco abaixo são o que o Qt exige de qualquer leiaute. Não têm decisão nenhuma; estão
    # aqui porque `QLayout` é abstrata e não porque este módulo tenha algo a dizer sobre eles.

    def addItem(self, a0: QLayoutItem | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is not None:
            self._itens.append(a0)

    def count(self) -> int:
        return len(self._itens)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - assinatura do Qt
        return self._itens[index] if 0 <= index < len(self._itens) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - assinatura do Qt
        return self._itens.pop(index) if 0 <= index < len(self._itens) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802 - assinatura do Qt
        """Nenhuma: a barra ocupa a largura que tem e a altura que precisa.

        Declarar expansão vertical faria a barra disputar altura com o painel que ela encima --
        que é o inverso da S-151, cujo item inteiro é devolver pixel ao documento.
        """
        return Qt.Orientation(0)

    # ------------------------------------------------------------------------- a geometria

    def _larguras(self) -> list[int]:
        """O que cada item pede de largura. É a entrada do arranjo."""
        return [max(1, item.sizeHint().width()) for item in self._itens]

    def _linhas(self, largura: int) -> list[list[int]]:
        margens = self.contentsMargins()
        disponivel = max(1, largura - margens.left() - margens.right())
        return arranjo(self._larguras(), disponivel, espaco=self._espaco)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - assinatura do Qt
        return True

    def heightForWidth(self, a0: int) -> int:  # noqa: N802 - assinatura do Qt
        """A altura que a barra precisa **naquela largura**. Ver o cabeçalho.

        Sem isto o Qt pergunta a altura antes de saber a largura, e a segunda linha é desenhada
        por cima do painel de baixo.
        """
        return self._altura_de(self._linhas(a0))

    def _altura_de(self, linhas: list[list[int]]) -> int:
        if not linhas:
            return 0
        margens = self.contentsMargins()
        alturas = [
            max(self._itens[indice].sizeHint().height() for indice in linha) for linha in linhas
        ]
        return sum(alturas) + self._espaco * (len(linhas) - 1) + margens.top() + margens.bottom()

    def setGeometry(self, a0: QRect) -> None:  # noqa: N802 - assinatura do Qt
        super().setGeometry(a0)
        margens = self.contentsMargins()
        topo = a0.y() + margens.top()
        for linha in self._linhas(a0.width()):
            esquerda = a0.x() + margens.left()
            altura = max(self._itens[indice].sizeHint().height() for indice in linha)
            for indice in linha:
                item = self._itens[indice]
                largura = max(1, item.sizeHint().width())
                item.setGeometry(QRect(QPoint(esquerda, topo), QSize(largura, altura)))
                esquerda += largura + self._espaco
            topo += altura + self._espaco

    def sizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """O tamanho de **uma** linha com tudo, que é a barra no seu melhor caso.

        A altura real vem de `heightForWidth`; esta resposta é o que a janela usa para escolher
        a largura inicial, e escolher a que não quebra nada é o certo -- quebrar é a saída para
        quando não cabe, não o alvo.
        """
        larguras = self._larguras()
        margens = self.contentsMargins()
        if not larguras:
            return QSize(margens.left() + margens.right(), margens.top() + margens.bottom())
        return QSize(
            sum(larguras) + self._espaco * (len(larguras) - 1) + margens.left() + margens.right(),
            self._altura_de([list(range(len(larguras)))]),
        )

    def minimumSize(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """A largura do item **mais largo**, e não a soma.

        **É o que faz a janela poder ser estreitada**, que é o defeito do `QHBoxLayout` descrito
        no cabeçalho. Responder a soma devolveria a barra ao regime em que a largura mínima da
        janela cresce com o número de botões -- e a S-151 mediu cinco barras empilhadas.

        Um item mais largo que a barra inteira ocupa uma linha sozinho e é cortado na borda:
        cortar um é melhor que esconder três, e é o que `arranjo` já documenta como o único caso
        sem saída.
        """
        larguras = self._larguras()
        margens = self.contentsMargins()
        alturas = [item.sizeHint().height() for item in self._itens]
        return QSize(
            (max(larguras) if larguras else 0) + margens.left() + margens.right(),
            (max(alturas) if alturas else 0) + margens.top() + margens.bottom(),
        )


class BarraFluida(QWidget):
    """Uma barra cujos controles quebram para a linha de baixo quando não cabem.

    Monte os controles com `self` como pai e registre-os com `adicionar` -- sem leiaute próprio,
    que é quem esta classe substitui. É a mesma forma de uso de `ui/barra.BarraFluida`, para que
    a montagem de um painel seja reconhecível dos dois lados.
    """

    def __init__(self, parent: QWidget | None = None, *, espaco: int = ESPACO_ENTRE_ITENS) -> None:
        super().__init__(parent)
        self._leiaute = LeiauteFluido(self, espaco=espaco)
        self.setLayout(self._leiaute)
        # `Preferred` na horizontal e `Minimum` na vertical: a barra aceita a largura que lhe
        # derem e não abre mão da altura que `heightForWidth` pediu.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def adicionar(self, widget: QWidget) -> QWidget:
        """Registra um controle na barra, na ordem em que ele deve aparecer. Devolve-o.

        Devolver o widget é o que faz o ponto de chamada caber numa linha --
        `barra.adicionar(QPushButton("Abrir PDF", barra))` -- em vez de precisar de uma variável
        só para registrar em seguida. É o contrato de `ui/barra.adicionar`, e o `TypeVar` de lá
        não é preciso aqui porque `QWidget` já preserva o tipo pelo próprio retorno.
        """
        widget.setParent(self)
        self._leiaute.addWidget(widget)
        return widget

    def esvaziar(self) -> None:
        """Tira e **destrói** todos os itens, deixando a barra pronta para ser remontada.

        Existe para a fita da S-228, que troca de modo em execução. `deleteLater` e não
        `deleteLater()` imediato do C++: destruir um widget dentro do próprio tratamento de
        evento dele é a maneira mais curta de derrubar o processo, e a troca de modo costuma
        vir de um clique num botão desta mesma barra.
        """
        while (item := self._leiaute.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    @property
    def linhas(self) -> int:
        """Quantas linhas a barra está ocupando agora. É o que o teste de aceite lê."""
        return len(self._leiaute._linhas(self.width()))

    def linhas_em(self, largura: int) -> int:
        """Quantas linhas ela ocuparia naquela largura, **sem** mudar o que está na tela.

        Pergunta pura sobre um widget montado, e existe pela razão de `ui/barra.linhas_em`: os
        critérios de aceite falam de larguras que o teste não quer ter de simular -- a S-151
        mede em 1100, que é onde o defeito original apareceu.
        """
        return len(self._leiaute._linhas(largura))
