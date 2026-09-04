"""A barra da sala de estudo: uma fila, agrupada por tarefa, com ícone e rótulo curto (S-527).

**A decisão não é reescrita, e é o item.** `ui/barra_da_sala.py` diz quais são os grupos, que ação é
principal, qual vai para o "Mais", qual é interruptor, que ícone e que dica cada uma tem, e -- dado o
que cada botão pede de largura -- **quem fica na fila** quando falta espaço (`cabem`). Este módulo
mede os botões, pergunta, e executa.

**`QAction` e não `QPushButton`, e é isso que faz o resto do painel não mudar.** Cada ação da
tabela vira uma `QAction`, que é ao mesmo tempo o botão da fila (`QToolButton.setDefaultAction`) e
o item do menu "Mais": texto, ícone, marcado e habilitado são **um** estado, e o painel continua
chamando `btn_treino.setChecked(...)`, `btn_dobra.setText(...)` e `btn_recorte.isEnabled()` como
chamava -- a `QAction` responde aos mesmos nomes que o botão respondia. Quando a ação vai para o
"Mais", ela leva o estado junto.

**O interruptor do catálogo não alterna duas vezes.** É o defeito que a medição de 2026-09-04
achou por acidente: um `QPushButton` marcável alterna `checked` **antes** de emitir `clicked`, e
`alternar_treino` inverte `isChecked()` de novo -- o clique de mouse em "Treinar" ligava e desligava
o treino no mesmo gesto, e só o menu e a paleta (que chamam o método sem botão) treinavam. Aqui o
`triggered` do interruptor do catálogo **devolve** o estado antes de chamar o método, e o método
alterna uma vez, como faz para o menu. `SEGUIR_OCR` é o caso contrário -- o método lê o estado -- e
usa `toggled`, como o `QCheckBox` que ele substitui.

**O que a segunda rodada mudou aqui** (2026-09-04, depois do crítico): dois níveis de botão
(`Acao.com_texto`: ícone e texto, ou só ícone); o "Mais" logo depois do último botão, com o vão à
direita; o cabeçalho de grupo do "Mais" como item desabilitado em negrito (`PROPRIEDADE_DE_CABECALHO`);
o ícone desenhado a 16 px e repintado na troca de pele; e a tecla da sala (`atalhos.TECLAS_DA_SALA`)
ligada na própria `QAction`, com alcance no painel. O estado marcado é da folha (`QToolButton:checked`
em `qt/tema.py`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QResizeEvent
from PyQt6.QtWidgets import QHBoxLayout, QLayout, QMenu, QSizePolicy, QToolButton, QWidget

from chess_diagram_ocr.qt import atalhos as qt_atalhos
from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import atalhos, espaco, estilos, tokens
from chess_diagram_ocr.ui import barra_da_sala as declarada

logger = logging.getLogger(__name__)

__all__ = ["LADO_DO_ICONE", "PROPRIEDADE_DE_CABECALHO", "BarraDaSala"]

LADO_DO_ICONE = 16
"""Lado do ícone, em pixel: o mesmo `LADO_DO_ICONE_DA_SALA` da faixa de navegação (S-520), porque é
a mesma aba -- dezesseis é a altura da letra da interface na base 9, e o par ícone-texto parece uma
coisa só.

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


class BarraDaSala(QWidget):
    """Uma fila de `QToolButton` com separador entre grupos, "Exportar ▾" e "Mais ▾".

    `executar(nome)` é o único caminho de volta ao painel: é o `PainelDeEstudo.executar`, que
    resolve o método pela tabela. A barra não conhece método nenhum.
    """

    def __init__(self, parent: QWidget | None, *, com_motor: bool, executar: Callable[[str], None]) -> None:
        super().__init__(parent)
        self._executar = executar
        self._com_motor = com_motor
        self._registros = declarada.acoes_para(com_motor=com_motor)
        self.acoes: dict[str, QAction] = {}
        """Toda ação da tabela -- inclusive as do submenu "Exportar" -- pelo nome."""
        self._botoes: list[tuple[QToolButton, declarada.Acao]] = []
        self._separadores: dict[str, QWidget] = {}
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
        for registro in declarada.principais(com_motor=com_motor):
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
        da sala quando `atalhos.TECLAS_DA_SALA` declara uma."""
        # O texto da `QAction` é o do **menu**: o rótulo curto só quando ele vai ser escrito num
        # botão (`com_texto`); o botão só com ícone não o mostra, e no "Mais" o item sai por extenso,
        # como os que nunca tiveram botão.
        acao = QAction(registro.rotulo_curto if registro.com_texto else registro.rotulo_longo, self)
        acao.setToolTip(declarada.dica_de(registro))
        acao.setProperty("acao", registro.acao)
        acao.setProperty("grupo", registro.grupo)
        acao.setCheckable(registro.marcavel)
        sequencia = atalhos.sequencia_da_sala(registro.acao) if registro.no_catalogo else ""
        if sequencia:
            # **Com alcance no painel da sala e nos filhos dele**, e não na janela: a tecla é da
            # sala (ver `TECLAS_DA_SALA`). A `QAction` é adicionada ao pai da barra -- o painel --
            # para que o foco em qualquer canto da sala a alcance, e uma ação desabilitada não
            # dispara, então a regra do modo vale para o teclado de graça.
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
                submenu.addAction(self.acoes.get(nome) or self._acao(declarada.acao(nome)))
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
        """A largura do "Mais" e a altura da fila: o menor estado, com tudo no menu.

        O padrão do `QWidget` responde a soma dos botões **visíveis**, e um pai que a respeitasse
        nunca estreitaria a barra -- `cabem` decidiria sobre uma largura que não muda. É o que a
        primeira montagem fazia, medido: pedida a 500 px, a fila continuava com 1387.
        """
        margens = self.contentsMargins()
        mais = getattr(self, "btn_mais", None)
        reserva = mais.sizeHint().width() if mais is not None else 0
        return QSize(
            reserva + margens.left() + margens.right(),
            self._fila.sizeHint().height() + margens.top() + margens.bottom(),
        )

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
            + self.btn_mais.sizeHint().width()
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
                reserva=self.btn_mais.sizeHint().width(),
                espaco=self._fila.spacing(),
                separador=1,
            )
            grupos_visiveis: set[str] = set()
            for indice, (botao, registro) in enumerate(self._botoes):
                visivel = indice in dentro
                botao.setVisible(visivel)
                if visivel:
                    grupos_visiveis.add(registro.grupo)
            primeiro = True
            for grupo in declarada.GRUPOS:
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
        for grupo in declarada.GRUPOS:
            do_grupo = [r for r in transbordo if r.grupo == grupo]
            do_grupo += [r for r in declarada.secundarias(com_motor=self._com_motor) if r.grupo == grupo]
            if not do_grupo:
                continue
            if not primeiro:
                self.menu_mais.addSeparator()
            primeiro = False
            # O título como item desabilitado em negrito, e não `addSection`: ver
            # `PROPRIEDADE_DE_CABECALHO`. A cor do desabilitado é a de `QMenu::item:disabled` na folha.
            titulo = QAction(declarada.rotulo_do_grupo(grupo), self.menu_mais)
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
        para recortar". A regra do grupo e a condição se somam -- desligado por qualquer uma.
        """
        desligados = declarada.grupos_desligados(qual)
        for registro in self._registros:
            acao = self.acoes[registro.acao]
            ligada = registro.grupo not in desligados and condicoes.get(registro.acao, True)
            acao.setEnabled(ligada)
