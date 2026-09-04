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
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QResizeEvent
from PyQt6.QtWidgets import QHBoxLayout, QLayout, QMenu, QSizePolicy, QToolButton, QWidget

from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import barra_da_sala as declarada
from chess_diagram_ocr.ui import espaco, estilos, tokens

logger = logging.getLogger(__name__)

__all__ = ["LADO_DO_ICONE", "BarraDaSala"]

LADO_DO_ICONE = 16
"""Lado do ícone, em pixel: o mesmo `LADO_DO_ICONE_DA_SALA` da faixa de navegação (S-520), porque é
a mesma aba -- dezesseis é a altura da letra da interface na base 9, e o par ícone-texto parece uma
coisa só."""


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

        fila.addStretch(1)
        self.menu_mais = QMenu(self)
        self.btn_mais = QToolButton(self)
        self.btn_mais.setText(declarada.ROTULO_DO_MAIS)
        self.btn_mais.setProperty("acao", declarada.MAIS)
        self.btn_mais.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_mais.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_mais.setAutoRaise(True)
        self.btn_mais.setMenu(self.menu_mais)
        self._pintar_icone(self.btn_mais, declarada.ICONE_DO_MAIS, tokens.TEXTO_PADRAO)
        fila.addWidget(self.btn_mais)
        self._rearranjar()

    # ---------------------------------------------------------------------------- montagem

    def _acao(self, registro: declarada.Acao) -> QAction:
        """A `QAction` de uma linha da tabela, com submenu quando ela é agrupador."""
        acao = QAction(registro.rotulo_curto if registro.principal else registro.rotulo_longo, self)
        acao.setToolTip(declarada.dica_de(registro))
        acao.setProperty("acao", registro.acao)
        acao.setProperty("grupo", registro.grupo)
        acao.setCheckable(registro.marcavel)
        cor = tokens.TEXTO_SOBRE_ENFASE if registro.papel == estilos.PRIMARIO else tokens.TEXTO_PADRAO
        if registro.papel == estilos.DESTRUTIVO:
            cor = tokens.BOTAO_DESTRUTIVO
        desenho = qt_icones.icone(registro.icone, 2 * LADO_DO_ICONE, tema.cor_atual(cor)) if registro.icone else None
        if desenho is not None:
            acao.setIcon(desenho)
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
        botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
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

    def _pintar_icone(self, botao: QToolButton, nome: str, papel: str) -> None:
        desenho = qt_icones.icone(nome, 2 * LADO_DO_ICONE, tema.cor_atual(papel))
        if desenho is not None:
            botao.setIcon(desenho)
            botao.setIconSize(qt_icones.tamanho(LADO_DO_ICONE))

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
        for grupo in declarada.GRUPOS:
            do_grupo = [r for r in transbordo if r.grupo == grupo]
            do_grupo += [r for r in declarada.secundarias(com_motor=self._com_motor) if r.grupo == grupo]
            if not do_grupo:
                continue
            self.menu_mais.addSection(declarada.rotulo_do_grupo(grupo))
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
        """As ações que o menu "Mais" oferece agora, na ordem em que aparecem."""
        return tuple(
            str(acao.property("acao"))
            for acao in self.menu_mais.actions()
            if not acao.isSeparator() and acao.property("acao") is not None
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
