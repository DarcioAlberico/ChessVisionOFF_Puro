"""A fita da aba Texto (S-650, S-652): as abas e os grupos de `ui/fita_do_texto.py`, desenhados.

**A declaração decide; este módulo executa** -- a mesma divisão de `qt/fita.py` e `qt/barra.py`.
Cada aba é uma `BarraFluida` de grupos: o grupo é a unidade, e um grupo partido ao meio não é um
grupo, então quem quebra a linha é o leiaute, entre um grupo e outro. Cada botão leva o rótulo, o
nome acessível e a dica **do catálogo** (S-324), e a dica diz a tecla quando há uma.

**Comando declarado sem função levanta `KeyError` na montagem**, como em `fita.montar`: um botão
que não faz nada é o item de menu sem comando da S-161, e é mais barato descobri-lo ao abrir a aba
do que no clique de alguém. Os controles com `@` chegam prontos do painel.

**Compacta e recolhida.** Quando a aba não cabe numa linha, os nomes dos grupos somem e os botões
sobem (compacta); `Ctrl+F1` recolhe a fita deixando só as abas, como no Word, e o clique numa aba
a devolve.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QTabWidget, QToolButton, QVBoxLayout, QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.atalhos import sequencia_qt
from chess_diagram_ocr.qt.barra import BarraFluida
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import atalhos, comandos, estilos
from chess_diagram_ocr.ui import fita_do_texto as declaracao

__all__ = ["FitaDoTexto", "tecla_de"]

PASSOS_DA_LISTA = 20
"""Quantos passos a lista do desfazer mostra (S-656): os do WordCraft."""


def tecla_de(acao: str) -> str:
    """O rótulo da tecla daquele comando: a da janela (`ATALHOS`) ou a própria do editor. Vazio sem."""
    rotulo = atalhos.acelerador(acao)
    if rotulo:
        return rotulo
    sequencia = atalhos.TECLAS_DO_EDITOR.get(acao)
    if not sequencia:
        return ""
    try:
        return QKeySequence(sequencia_qt(sequencia)).toString(QKeySequence.SequenceFormat.NativeText)
    except ValueError:
        return ""


class FitaDoTexto(QTabWidget):
    """A fita: uma aba por `declaracao.ABAS`, e a barra de acesso rápido no canto."""

    recolhida_mudou = pyqtSignal(bool)

    def __init__(
        self,
        parent: QWidget | None,
        *,
        alvo: Callable[[str], Callable[[], object] | None],
        controles: Mapping[str, QWidget],
        rotulos_do_desfazer: Callable[[], list[str]] | None = None,
        desfazer_ate: Callable[[int], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAccessibleName("Fita do Texto")
        self.setDocumentMode(True)
        self._alvo = alvo
        self._controles = dict(controles)
        self._rotulos_do_desfazer = rotulos_do_desfazer
        self._desfazer_ate = desfazer_ate
        self.botoes: dict[str, QToolButton] = {}
        """Os botões por comando. É por aqui que o painel marca os de estado e troca rótulos."""
        self.barras: list[BarraFluida] = []
        self._legendas: list[QLabel] = []
        self.recolhida = False
        for aba in declaracao.ABAS:
            self.addTab(self._montar_aba(aba), aba.nome)
        self.setCornerWidget(self._acesso_rapido(), Qt.Corner.TopRightCorner)
        self.setCurrentIndex(1)  # a Página inicial; a Arquivo é a primeira, como no Word
        self.tabBarClicked.connect(self._clicou_na_aba)

    # ---------------------------------------------------------------------------- montagem

    def _montar_aba(self, aba: declaracao.Aba) -> BarraFluida:
        barra = BarraFluida(self)
        for grupo in aba.grupos:
            barra.adicionar(self._grupo(barra, grupo))
        self.barras.append(barra)
        return barra

    def _grupo(self, pai: QWidget, grupo: declaracao.Grupo) -> QWidget:
        caixa = QWidget(pai)
        caixa.setAccessibleName(grupo.nome)
        pilha = QVBoxLayout(caixa)
        pilha.setContentsMargins(4, 0, 4, 0)
        pilha.setSpacing(1)
        linha = QHBoxLayout()
        linha.setSpacing(2)
        for item in grupo.itens:
            if item in declaracao.CONTROLES:
                controle = self._controles.get(item)
                if controle is None:
                    raise KeyError(f"a fita declara o controle {item!r} e o painel não o deu")
                controle.setParent(caixa)
                linha.addWidget(controle)
                continue
            linha.addWidget(self._botao(caixa, item))
        pilha.addLayout(linha)
        legenda = QLabel(grupo.nome, caixa)
        legenda.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        legenda.setEnabled(False)  # o cinza de apoio do tema, sem cor escrita aqui
        pilha.addWidget(legenda)
        self._legendas.append(legenda)
        return caixa

    def _botao(self, pai: QWidget, acao: str) -> QToolButton:
        funcao = self._alvo(acao)
        if funcao is None:
            raise KeyError(f"a fita declara {acao!r} e ninguém o atende")
        botao = QToolButton(pai)
        botao.setText(comandos.rotulo_de_botao(acao))
        botao.setAccessibleName(comandos.nome_acessivel(acao))
        botao.setAutoRaise(True)
        botao.setCheckable(acao in declaracao.DE_ESTADO)
        tecla = tecla_de(acao)
        dica_em(botao, f"{comandos.rotulo(acao)}\nTecla: {tecla}" if tecla else comandos.rotulo(acao))
        tema.aplicar_papel(botao, estilos.NEUTRO)
        botao.clicked.connect(lambda _marcado=False, f=funcao: f())
        self.botoes[acao] = botao
        return botao

    def _acesso_rapido(self) -> QWidget:
        """Salvar, desfazer com a lista dos passos e refazer (S-650, S-656)."""
        canto = QWidget(self)
        linha = QHBoxLayout(canto)
        linha.setContentsMargins(0, 0, 4, 0)
        linha.setSpacing(1)
        for acao in declaracao.ACESSO_RAPIDO:
            botao = self._botao(canto, acao)
            if acao == "desfazer" and self._rotulos_do_desfazer is not None:
                botao.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                menu = QMenu(botao)
                menu.aboutToShow.connect(lambda m=menu: self._encher_a_lista(m))
                botao.setMenu(menu)
                self.lista_do_desfazer = menu
            linha.addWidget(botao)
        return canto

    def _encher_a_lista(self, menu: QMenu) -> None:
        """A lista do desfazer, do passo mais novo ao mais velho: escolher o quinto desfaz cinco."""
        menu.clear()
        rotulos = self._rotulos_do_desfazer() if self._rotulos_do_desfazer is not None else []
        for indice, rotulo in enumerate(rotulos[:PASSOS_DA_LISTA]):
            acao = QAction(f"{indice + 1}. {rotulo}", menu)
            acao.triggered.connect(lambda _marcado=False, n=indice + 1: self._desfazer_ate and self._desfazer_ate(n))
            menu.addAction(acao)
        if not rotulos:
            vazio = QAction("Nada a desfazer", menu)
            vazio.setEnabled(False)
            menu.addAction(vazio)

    # ------------------------------------------------------------------------ comportamento

    def botao(self, acao: str) -> QToolButton:
        return self.botoes[acao]

    def marcar(self, estados: Mapping[str, bool]) -> None:
        """Marca os botões de estado (S-650). O `setChecked` não dispara `clicked`: nada é aplicado."""
        for acao, ligado in estados.items():
            botao = self.botoes.get(acao)
            if botao is not None and botao.isCheckable():
                botao.setChecked(bool(ligado))

    def alternar_recolhida(self) -> bool:
        self.definir_recolhida(not self.recolhida)
        return self.recolhida

    def definir_recolhida(self, recolhida: bool) -> None:
        """Só as abas (S-652). O conteúdo some e a altura cai à da barra de abas."""
        self.recolhida = bool(recolhida)
        for indice in range(self.count()):
            pagina = self.widget(indice)
            if pagina is not None:
                pagina.setVisible(not self.recolhida)
        barra_de_abas = self.tabBar()
        if self.recolhida and barra_de_abas is not None:
            self.setMaximumHeight(barra_de_abas.sizeHint().height() + 2)
        else:
            self.setMaximumHeight(16777215)
        self.recolhida_mudou.emit(self.recolhida)

    def _clicou_na_aba(self, _indice: int) -> None:
        if self.recolhida:
            self.definir_recolhida(False)

    def compacta(self) -> bool:
        """A aba à vista não cabe numa linha: os nomes dos grupos somem (S-652)."""
        return not any(legenda.isVisible() for legenda in self._legendas) if self._legendas else False

    def resizeEvent(self, a0: object) -> None:  # noqa: N802 - API do Qt
        super().resizeEvent(a0)  # type: ignore[arg-type]
        atual = self.currentWidget()
        if isinstance(atual, BarraFluida):
            sobra = atual.linhas_em(max(1, self.width())) > 1
            for legenda in self._legendas:
                legenda.setVisible(not sobra)
