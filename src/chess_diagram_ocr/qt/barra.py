"""Os dois widgets de barra de ferramentas: o que quebra (S-151) e o que enfileira (S-527/S-528).

As duas decisões moram em `ui/barra.py`; este arquivo tem os dois executores. `BarraFluida` é a
que empilha fileiras; `BarraEmFila` é a que põe o que não coube num menu "Mais" e nunca gasta uma
segunda linha. Quem declara o **conteúdo** de uma fila é a tabela dela (`ui/barra_da_sala.py`,
`ui/barra_do_pdf.py`), e é ela que este widget recebe por argumento.

---

# A barra que quebra em vez de cortar, no Qt (S-151/S-501)

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
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QResizeEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLayout,
    QLayoutItem,
    QMenu,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import barra as declarada
from chess_diagram_ocr.ui import espaco, estilos, tokens
from chess_diagram_ocr.ui.barra import ESPACO_ENTRE_ITENS, arranjo, linhas_necessarias

logger = logging.getLogger(__name__)

__all__ = [
    "ESPACO_ENTRE_ITENS",
    "LADO_DO_ICONE",
    "PROPRIEDADE_DE_CABECALHO",
    "BarraEmFila",
    "BarraFluida",
    "LeiauteFluido",
    "TabelaDeFila",
    "arranjo",
    "linhas_necessarias",
]


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


# ==================================================================================================
# A barra que enfileira: uma fila, grupos com separador, e um "Mais ▾" no fim (S-527/S-528)
# ==================================================================================================

LADO_DO_ICONE = 16
"""Lado do ícone, em pixel: o mesmo `LADO_DO_ICONE_DA_SALA` da faixa de navegação (S-520) --
dezesseis é a altura da letra da interface na base 9, e o par ícone-texto parece uma coisa só.

**Desenhado a 16, e não a 32 reduzido** (segunda rodada da S-527). A primeira montagem pedia o
traço a `2 * LADO` e deixava o botão encolher: o traço de 2 px virava meio-tom de 1, e "mais" saía
sem um pixel forte. `qt_icones.icone(..., escala=devicePixelRatioF())` desenha no tamanho em que
vai ser mostrado, e só numa tela de alta densidade nasce maior."""

PROPRIEDADE_DE_CABECALHO = "cabecalho"
"""A propriedade da `QAction` que é título de grupo no menu "Mais", com o nome do grupo como valor.

O `addSection` do `QMenu` desenha só a linha no estilo `windows11` -- o título fica invisível, e o
crítico da S-527 abriu o menu e não achou "Posição" nem "Variante". O cabeçalho passa a ser um
**item desabilitado em negrito**, que todo estilo desenha; `no_mais()` o distingue por esta
propriedade, e o teste o acha por ela."""


class TabelaDeFila(Protocol):
    """O que uma barra em fila pede da tabela dela. Um **módulo** o satisfaz, e é assim que se usa.

    Só quatro coisas, e nenhuma delas é a lista de ações -- essa vem por argumento, já filtrada
    pelo que aquela montagem tem (a sala sem motor não tem o grupo `MOTOR`). O resto é a forma, e
    a forma mora em `ui/barra.py`.
    """

    GRUPOS: tuple[str, ...]

    def rotulo_do_grupo(self, grupo: str) -> str: ...  # noqa: D102 - assinatura, não método

    def grupos_desligados(self, qual: str) -> frozenset[str]: ...  # noqa: D102

    def sequencia_de(self, nome: str) -> str: ...  # noqa: D102


class BarraEmFila(QWidget):
    """Uma fila de `QToolButton` com separador entre grupos e um "Mais ▾" que recebe o transbordo.

    **A decisão não é reescrita, e é o item.** A tabela diz quais são os grupos, que ação é
    principal, qual vai para o "Mais", qual é interruptor, que ícone e que dica cada uma tem, e --
    dado o que cada botão pede de largura -- **quem fica na fila** (`ui/barra.cabem`). Este widget
    mede os botões, pergunta, e executa.

    **`QAction` e não `QPushButton`, e é isso que faz o resto do painel não mudar.** Cada ação da
    tabela vira uma `QAction`, que é ao mesmo tempo o botão da fila (`QToolButton.setDefaultAction`)
    e o item do menu "Mais": texto, ícone, marcado e habilitado são **um** estado, e o painel
    continua chamando `btn_treino.setChecked(...)` e `btn_recorte.isEnabled()` como chamava -- a
    `QAction` responde aos mesmos nomes que o botão respondia. Quando a ação vai para o "Mais", ela
    leva o estado junto.

    **O interruptor do catálogo não alterna duas vezes.** É o defeito que a medição de 2026-09-04
    achou por acidente: um `QPushButton` marcável alterna `checked` **antes** de emitir `clicked`, e
    `alternar_treino` inverte `isChecked()` de novo -- o clique de mouse em "Treinar" ligava e
    desligava o treino no mesmo gesto, e só o menu e a paleta (que chamam o método sem botão)
    treinavam. Aqui o `triggered` do interruptor do catálogo **devolve** o estado antes de chamar o
    método, e o método alterna uma vez. Um interruptor fora do catálogo é o caso contrário -- o
    método lê o estado -- e usa `toggled`, como o `QCheckBox` que ele substitui.

    `executar(nome)` é o único caminho de volta ao painel: ele resolve o método pela tabela. A
    barra não conhece método nenhum.
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        tabela: TabelaDeFila,
        registros: Sequence[declarada.Acao],
        executar: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._executar = executar
        self._tabela = tabela
        self._registros = tuple(registros)
        self._por_acao = {registro.acao: registro for registro in self._registros}
        self.acoes: dict[str, QAction] = {}
        """Toda ação da tabela -- inclusive as de submenu -- pelo nome."""
        self._botoes: list[tuple[QToolButton, declarada.Acao]] = []
        self._separadores: dict[str, QWidget] = {}
        self._avulsos: list[tuple[QWidget, str]] = []
        """Widget pendurado na fila e o nome do botão que ele acompanha. Ver `encaixar`."""
        self._rearranjando = False

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(espaco.minima())
        # **Sem trava de mínimo**: a largura mínima desta fila é a do "Mais", e é `minimumSizeHint`
        # quem a diz. Com a trava padrão do `QLayout`, o mínimo seria a soma dos botões visíveis, e
        # o pai nunca poderia estreitá-la -- a conta de `cabem` jamais rodaria.
        fila.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._fila = fila

        for registro in self._registros:
            if registro.acao not in self.acoes:
                self._acao(registro)
        grupo_anterior = ""
        for registro in self.principais:
            acao = self.acoes[registro.acao]
            if registro.grupo != grupo_anterior and grupo_anterior:
                separador = self._separador()
                self._separadores[registro.grupo] = separador
                fila.addWidget(separador)
            grupo_anterior = registro.grupo
            botao = self._botao(acao, registro)
            self._botoes.append((botao, registro))
            fila.addWidget(botao)

        # **O "Mais" vem logo depois do último botão, e o vão fica à direita dele.** A primeira
        # montagem o encostava na borda direita com o vão no meio -- a 1920 px eram ~110 px de
        # fila vazia entre "Símbolo" e "Mais", e o crítico mediu o vazio como se fosse botão que
        # faltava. Numa barra de ferramentas o transbordo mora onde a fila acaba.
        self.menu_mais = QMenu(self)
        self.btn_mais = QToolButton(self)
        self.btn_mais.setText(declarada.ROTULO_DO_MAIS)
        self.btn_mais.setProperty("acao", declarada.MAIS)
        self.btn_mais.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_mais.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_mais.setAutoRaise(True)
        self.btn_mais.setMenu(self.menu_mais)
        fila.addWidget(self.btn_mais)
        fila.addStretch(1)
        self._pintar_icones()
        tema.ao_repintar(self._pintar_icones)
        # **O texto de uma ação muda de largura, e a fila tem de reperguntar a `cabem`.** "Treinar"
        # vira "Parar o treino" (+35 px) sem nenhum `resizeEvent`, e a primeira montagem deixava o
        # layout espremer o primário -- fotografado: "Carregar…CR atual" elidido a 1400 px. Um
        # `changed` por ação, coalescidos num único rearranjo no próximo giro do laço.
        self._rearranjo_pendente = False
        for acao in self.acoes.values():
            acao.changed.connect(self._agendar_rearranjo)
        self._rearranjar()

    # -------------------------------------------------------------- o que a tabela responde

    @property
    def principais(self) -> tuple[declarada.Acao, ...]:
        """As ações desta montagem que ganham botão, na ordem da barra."""
        return tuple(registro for registro in self._registros if registro.principal)

    @property
    def secundarias(self) -> tuple[declarada.Acao, ...]:
        """As que vão direto para o "Mais". Item de submenu não está aqui: o lugar dele é o
        agrupador."""
        return tuple(r for r in self._registros if not r.principal and not r.dentro_de)

    def _agendar_rearranjo(self) -> None:
        if self._rearranjo_pendente:
            return
        self._rearranjo_pendente = True
        QTimer.singleShot(0, self._rearranjo_agendado)

    def _rearranjo_agendado(self) -> None:
        self._rearranjo_pendente = False
        try:
            self._rearranjar()
        except RuntimeError:  # a barra morreu entre o agendamento e o giro do laço
            return

    # ---------------------------------------------------------------------------- montagem

    def _acao(self, registro: declarada.Acao) -> QAction:
        """A `QAction` de uma linha da tabela, com submenu quando ela é agrupador, e com a tecla
        que `tabela.sequencia_de` declarar."""
        # O texto da `QAction` é o do **menu**: o rótulo curto só quando ele vai ser escrito num
        # botão (`com_texto`); o botão só com ícone não o mostra, e no "Mais" o item sai por extenso,
        # como os que nunca tiveram botão.
        acao = QAction(registro.rotulo_curto if registro.com_texto else registro.rotulo_longo, self)
        acao.setToolTip(declarada.dica_de(registro))
        acao.setProperty("acao", registro.acao)
        acao.setProperty("grupo", registro.grupo)
        acao.setCheckable(registro.marcavel)
        sequencia = self._tabela.sequencia_de(registro.acao)
        if sequencia:
            # **Com alcance no painel e nos filhos dele**, e não na janela: a tecla é da aba. A
            # `QAction` é adicionada ao pai da barra -- o painel -- para que o foco em qualquer
            # canto dela a alcance, e uma ação desabilitada não dispara, então a regra do modo vale
            # para o teclado de graça.
            acao.setShortcut(QKeySequence(qt_atalhos.sequencia_qt(sequencia)))
            acao.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            pai = self.parentWidget()
            if pai is not None:
                pai.addAction(acao)
        if registro.agrupador:
            # Os itens já viraram `QAction` na passagem pela tabela (eles vêm depois do agrupador,
            # ou antes: a ordem não importa, o dicionário responde pelos dois).
            submenu = QMenu(self)
            for nome in registro.itens_do_submenu:
                submenu.addAction(self.acoes.get(nome) or self._acao(self._por_acao[nome]))
            acao.setMenu(submenu)
        elif registro.marcavel and not registro.alterna_no_metodo:
            acao.toggled.connect(lambda _ligado, nome=registro.acao: self._executar(nome))
        elif registro.marcavel:
            acao.triggered.connect(lambda marcado, a=acao, nome=registro.acao: self._alternar_uma_vez(a, marcado, nome))
        else:
            acao.triggered.connect(lambda _marcado=False, nome=registro.acao: self._executar(nome))
        self.acoes[registro.acao] = acao
        return acao

    def _alternar_uma_vez(self, acao: QAction, marcado: bool, nome: str) -> None:
        """Devolve o estado que o clique já alternou, e deixa o método alternar. Ver o cabeçalho."""
        acao.setChecked(not marcado)
        self._executar(nome)

    def _botao(self, acao: QAction, registro: declarada.Acao) -> QToolButton:
        botao = QToolButton(self)
        botao.setDefaultAction(acao)
        botao.setProperty("acao", registro.acao)
        # Dois níveis (ver `Acao.com_texto`): ícone e texto para o que se lê de longe, só o ícone
        # para o resto -- o rótulo e a tecla estão na primeira linha da dica.
        botao.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon if registro.com_texto else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        botao.setProperty(tema.PROPRIEDADE_DE_NIVEL, tema.NIVEL_TEXTO if registro.com_texto else tema.NIVEL_ICONE)
        botao.setIconSize(qt_icones.tamanho(LADO_DO_ICONE))
        botao.setAutoRaise(True)
        if registro.agrupador:
            botao.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        tema.aplicar_papel(botao, registro.papel)
        return botao

    def _separador(self) -> QWidget:
        """A barra vertical entre dois grupos: o `QWidget#separador-da-fila` da S-522, e não um
        `QFrame.VLine`, que desenha com a cor de texto da paleta e não com a da folha."""
        separador = QWidget(self)
        separador.setObjectName(tema.ID_DO_SEPARADOR)
        separador.setFixedWidth(1)
        separador.setFixedHeight(2 * LADO_DO_ICONE)
        return separador

    def encaixar(self, widget: QWidget, *, depois_de: str) -> QWidget:
        """Pendura um widget que **não é ação** logo depois do botão daquela ação. Devolve-o.

        Existe para o campo de página do painel do PDF (S-528): `[21] de 289` é um `QSpinBox` e um
        rótulo, e eles pertencem à mesma fila que "Página anterior" e "Próxima página" -- pô-los
        numa segunda linha era metade do defeito que este item corrige.

        **O avulso acompanha o botão em que foi encaixado.** Ele não tem prioridade própria e não
        vai para o "Mais": ou o botão a que ele pertence está na fila, e ele também, ou os dois
        somem juntos. Um campo de página sozinho, com as duas setas escondidas no menu, seria um
        controle sem contexto -- e a largura dele entra na conta de `cabem` pela `reserva`, junto
        com o "Mais", porque é largura que a fila não pode dispor.
        """
        self._avulsos.append((widget, depois_de))
        indice = -1
        for posicao in range(self._fila.count()):
            item = self._fila.itemAt(posicao)
            alvo = item.widget() if item is not None else None
            if alvo is not None and alvo.property("acao") == depois_de:
                indice = posicao
                break
        widget.setParent(self)
        self._fila.insertWidget(indice + 1 if indice >= 0 else self._fila.count(), widget)
        self._rearranjar()
        return widget

    def _icone(self, nome: str, papel: str) -> QIcon | None:
        """O traço no tamanho em que vai ser mostrado, na cor que a pele em uso resolve para o papel."""
        return qt_icones.icone(nome, LADO_DO_ICONE, tema.cor_atual(papel), escala=self.devicePixelRatioF())

    def _pintar_icones(self) -> None:
        """Desenha (ou redesenha) o ícone de toda ação e do "Mais" na cor da pele **em uso**.

        Registrado em `tema.ao_repintar`: a troca de pele muda a cor do texto, e um ícone pintado
        para o cromo claro some no escuro -- é a medição da S-220 (*"as seis peças pretas somem no
        fundo"*), e o crítico da S-527 fotografou as três peles. `qt_icones` guarda por cor, então a
        cor nova é um desenho novo e a antiga só espera o `limpar_cache` da janela.
        """
        for registro in self._registros:
            if not registro.icone:
                continue
            cor = tokens.TEXTO_SOBRE_ENFASE if registro.papel == estilos.PRIMARIO else tokens.TEXTO_PADRAO
            if registro.papel == estilos.DESTRUTIVO:
                cor = tokens.BOTAO_DESTRUTIVO
            desenho = self._icone(registro.icone, cor)
            if desenho is not None:
                self.acoes[registro.acao].setIcon(desenho)
        desenho = self._icone(declarada.ICONE_DO_MAIS, tokens.TEXTO_PADRAO)
        if desenho is not None:
            self.btn_mais.setIcon(desenho)
            self.btn_mais.setIconSize(qt_icones.tamanho(LADO_DO_ICONE))

    # ------------------------------------------------------------------------ quem cabe

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._rearranjar()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """A largura da reserva e a altura da fila: o menor estado, com tudo no menu.

        O padrão do `QWidget` responde a soma dos botões **visíveis**, e um pai que a respeitasse
        nunca estreitaria a barra -- `cabem` decidiria sobre uma largura que não muda. É o que a
        primeira montagem fazia, medido: pedida a 500 px, a fila continuava com 1387.
        """
        margens = self.contentsMargins()
        return QSize(
            self._reserva() + margens.left() + margens.right(),
            self._fila.sizeHint().height() + margens.top() + margens.bottom(),
        )

    def _reserva(self) -> int:
        """A largura que a fila **não** pode dispor: o "Mais" e os avulsos visíveis."""
        mais = getattr(self, "btn_mais", None)
        reserva = mais.sizeHint().width() if mais is not None else 0
        for widget, _dono in getattr(self, "_avulsos", ()):
            reserva += widget.sizeHint().width() + self._fila.spacing()
        return reserva

    def largura_para_todas(self) -> int:
        """A largura a partir da qual `cabem` devolve todas as principais: a fila no seu melhor
        caso, como o `sizeHint` da `BarraFluida`. É a conta de `cabem`, de trás para diante."""
        margens = self.contentsMargins()
        larguras = [botao.sizeHint().width() for botao, _registro in self._botoes]
        grupos = {registro.grupo for _botao, registro in self._botoes}
        vao = self._fila.spacing()
        return (
            sum(larguras)
            + vao * len(larguras)
            + (len(grupos) - 1) * (1 + vao)
            + self._reserva()
            + margens.left()
            + margens.right()
        )

    def _rearranjar(self) -> None:
        """Mede, pergunta a `cabem`, e põe no "Mais" quem não coube. Nunca muda a altura."""
        if self._rearranjando:
            return
        self._rearranjando = True
        try:
            itens = [
                declarada.Item(botao.sizeHint().width(), registro.prioridade, registro.grupo)
                for botao, registro in self._botoes
            ]
            margens = self.contentsMargins()
            dentro = declarada.cabem(
                itens,
                max(0, self.width() - margens.left() - margens.right()),
                reserva=self._reserva(),
                espaco=self._fila.spacing(),
                separador=1,
            )
            grupos_visiveis: set[str] = set()
            na_fila: set[str] = set()
            for indice, (botao, registro) in enumerate(self._botoes):
                visivel = indice in dentro
                botao.setVisible(visivel)
                if visivel:
                    grupos_visiveis.add(registro.grupo)
                    na_fila.add(registro.acao)
            for widget, dono in self._avulsos:
                widget.setVisible(dono in na_fila)
            primeiro = True
            for grupo in self._tabela.GRUPOS:
                separador = self._separadores.get(grupo)
                if grupo not in grupos_visiveis:
                    if separador is not None:
                        separador.setVisible(False)
                    continue
                if separador is not None:
                    separador.setVisible(not primeiro)
                primeiro = False
            self._remontar_mais(dentro)
        finally:
            self._rearranjando = False

    def _remontar_mais(self, dentro: frozenset[int]) -> None:
        """O "Mais" tem duas partes: quem não coube na fila, e quem nunca esteve nela.

        Por grupo, com o cabeçalho do grupo como seção -- é a mesma ordem da barra, para que quem
        procura "Trocar vez" saiba que ele está debaixo de "Posição" antes de abrir o menu.
        """
        self.menu_mais.clear()
        transbordo = [registro for indice, (_botao, registro) in enumerate(self._botoes) if indice not in dentro]
        primeiro = True
        for grupo in self._tabela.GRUPOS:
            do_grupo = [r for r in transbordo if r.grupo == grupo]
            do_grupo += [r for r in self.secundarias if r.grupo == grupo]
            if not do_grupo:
                continue
            if not primeiro:
                self.menu_mais.addSeparator()
            primeiro = False
            # O título como item desabilitado em negrito, e não `addSection`: ver
            # `PROPRIEDADE_DE_CABECALHO`. A cor do desabilitado é a de `QMenu::item:disabled` na folha.
            titulo = QAction(self._tabela.rotulo_do_grupo(grupo), self.menu_mais)
            self.menu_mais.addAction(titulo)
            titulo.setEnabled(False)
            titulo.setProperty(PROPRIEDADE_DE_CABECALHO, grupo)
            fonte = titulo.font()
            fonte.setBold(True)
            titulo.setFont(fonte)
            for registro in do_grupo:
                self.menu_mais.addAction(self.acoes[registro.acao])
        self.btn_mais.setEnabled(not self.menu_mais.isEmpty())

    # -------------------------------------------------------------------------- o que se lê

    @property
    def linhas(self) -> int:
        """Sempre uma: é a propriedade que o critério de aceite mede, e a forma garante."""
        return 1

    def na_fila(self) -> tuple[str, ...]:
        """As ações com botão **visível** agora, na ordem da barra."""
        return tuple(registro.acao for botao, registro in self._botoes if not botao.isHidden())

    def no_mais(self) -> tuple[str, ...]:
        """As ações que o menu "Mais" oferece agora, na ordem em que aparecem. Sem os cabeçalhos."""
        return tuple(
            str(acao.property("acao"))
            for acao in self.menu_mais.actions()
            if not acao.isSeparator() and acao.property("acao") is not None
        )

    def cabecalhos_do_mais(self) -> tuple[str, ...]:
        """Os títulos de grupo que o menu "Mais" desenha agora, na ordem da barra."""
        return tuple(
            acao.text()
            for acao in self.menu_mais.actions()
            if acao.property(PROPRIEDADE_DE_CABECALHO) is not None
        )

    def botao_de(self, nome: str) -> QToolButton | None:
        """O `QToolButton` daquela ação principal, ou `None` para ação sem botão."""
        for botao, registro in self._botoes:
            if registro.acao == nome:
                return botao
        return None

    # ------------------------------------------------------------------------------ modo

    def aplicar_modo(self, qual: str, condicoes: Mapping[str, bool] = {}) -> None:  # noqa: B006 - só leitura
        """Habilita cada ação pela regra do modo **e** pela condição própria dela, se houver.

        `condicoes` é o que o painel sabe e a tabela não: "há variante para dobrar", "há âncora
        para recortar", "a exportação está em curso". A regra do grupo e a condição se somam --
        desligado por qualquer uma.
        """
        desligados = self._tabela.grupos_desligados(qual)
        for registro in self._registros:
            acao = self.acoes[registro.acao]
            ligada = registro.grupo not in desligados and condicoes.get(registro.acao, True)
            acao.setEnabled(ligada)
