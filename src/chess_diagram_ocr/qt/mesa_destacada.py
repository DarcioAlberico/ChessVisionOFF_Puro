"""A mesa numa janela própria: o editor e uma vista da folha, para quem tem dois monitores (S-646).

**O painel que vai para a janela é o mesmo**, e não uma cópia: o `PainelDeTexto` sai da rolagem do
modo Texto (`PainelPrincipal.soltar_modo`) e entra no divisor da janela da mesa, com a seleção, a
pilha de desfazer, o zoom e o caderno aberto que tinha. No lugar dele fica um cartão -- «O texto está
na mesa» · Mostrar · Trazer de volta --, e não um modo vazio que pareceria o texto perdido.

**Os três pré-requisitos que a primeira revisão achou lendo a fiação**, e onde cada um mora:

1. a guarda de atalhos conhece janelas (`GuardaDeAtalhos.registrar_janela`): com o foco aqui só
   valem as ações do texto (`ui/mesa.ACOES_DA_MESA_DESTACADA`), e `Del`, setas, `PgUp`/`PgDn` e
   `Ctrl+N` não mexem na janela principal;
2. o painel sai da `QScrollArea` por `takeWidget`, que não o destrói (`PainelPrincipal.soltar_modo`);
3. quem pede «traga a aba Texto» -- a paleta de glifos, a linha do estudo -- traz a janela da mesa
   para a frente (`trazer`), e não o cartão.

**A vista da folha é do painel**, e não do livro: ela mostra a folha que o editor tem rasterizada, e
o bloco sob o cursor e o clique na folha se apontam como na mesa da janela principal (S-642).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.visor import VisorDePagina
from chess_diagram_ocr.ui import abas, espaco, estilos, mesa

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.atalhos import GuardaDeAtalhos
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto
    from chess_diagram_ocr.qt.painel_principal import PainelPrincipal

__all__ = ["JanelaDaMesa", "MesaDestacada"]

LARGURA_INICIAL = 1280
ALTURA_INICIAL = 820
"""O tamanho da janela da mesa na primeira vez: a folha e o editor lado a lado num monitor comum."""


class JanelaDaMesa(QMainWindow):
    """A janela de topo da mesa: a folha à esquerda, o editor à direita."""

    fechada = pyqtSignal()
    """A pessoa fechou a janela da mesa: o texto volta à janela principal, e não some."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(mesa.TITULO_DA_MESA)
        self.setAccessibleName(mesa.TITULO_DA_MESA)
        self.divisor = QSplitter(Qt.Orientation.Horizontal, self)
        self.visor = VisorDePagina(self.divisor)
        self.visor.setAccessibleName("Folha do texto na mesa")
        self.divisor.addWidget(self.visor)
        # O painel numa rolagem **da mesa**, como no modo: a fita pede ~980 px de largura mínima, e
        # direto no divisor ela espremia a folha a 60 px. Rola na horizontal só quando não cabe.
        self.rolagem = QScrollArea(self.divisor)
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QFrame.Shape.NoFrame)
        self.rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.divisor.addWidget(self.rolagem)
        self.setCentralWidget(self.divisor)

    def closeEvent(self, a0: Any) -> None:  # noqa: N802 - assinatura do Qt
        self.fechada.emit()
        if a0 is not None:
            a0.accept()


class MesaDestacada:
    """Destacar e devolver o painel de texto entre a janela principal e a janela da mesa."""

    def __init__(self, janela: QWidget, principal: PainelPrincipal, texto: PainelDeTexto, guarda: GuardaDeAtalhos) -> None:
        self._principal = principal
        self._texto = texto
        self._guarda = guarda
        self.janela = JanelaDaMesa(janela)
        self.janela.fechada.connect(self.devolver)
        self.cartao = self._montar_cartao()
        self._folha_mostrada: object | None = None
        self._ja_mostrada = False
        texto.bloco_destacado.connect(self._destacar)
        texto.documento_mudou.connect(self._atualizar_a_folha)
        self.janela.visor.ponto_clicado.connect(texto.ir_ao_ponto)

    @property
    def destacada(self) -> bool:
        return self._texto.window() is self.janela

    # ---------------------------------------------------------------------------------- gestos

    def alternar(self) -> None:
        """O comando «Destacar a mesa»: destaca, ou devolve quando já está destacada."""
        if self.destacada:
            self.devolver()
        else:
            self.destacar()

    def destacar(self) -> None:
        if self.destacada:
            self.trazer(self._texto)
            return
        painel = self._principal.soltar_modo(abas.TEXTO, self.cartao)
        if painel is None:
            return
        self.janela.rolagem.setWidget(painel)
        self.janela.divisor.setStretchFactor(0, 2)
        self.janela.divisor.setStretchFactor(1, 3)
        painel.show()
        self._guarda.registrar_janela(self.janela, self._comandos_da_mesa())
        self._folha_mostrada = None
        self._atualizar_a_folha()
        primeira = not self._ja_mostrada
        self.trazer(self._texto)
        if primeira:
            self._repartir()
        self._texto.editor.setFocus()

    def _repartir(self) -> None:
        """Na primeira vez, a janela num tamanho de trabalho e a folha com a fração da mesa (S-640).

        Sem isto o divisor reparte pela `sizeHint`, e a do painel -- com a fita inteira -- pede toda a
        largura: a folha ficava com 60 px. Nas vezes seguintes vale o que a pessoa arrastou.
        """
        self._ja_mostrada = True
        if self.janela.width() < mesa.LARGURA_MINIMA:
            self.janela.resize(LARGURA_INICIAL, ALTURA_INICIAL)
        total = sum(self.janela.divisor.sizes()) or self.janela.width()
        folha = max(1, int(total * mesa.FRACAO_PADRAO))
        self.janela.divisor.setSizes([folha, max(1, total - folha)])

    def devolver(self) -> None:
        """O texto volta à aba, como estava. Fechar a janela da mesa é o mesmo gesto."""
        if not self.destacada:
            return
        self._guarda.esquecer_janela(self.janela)
        # `takeWidget` antes: a rolagem da mesa guarda o painel, e o `setWidget` seguinte dela o destruiria.
        self.janela.rolagem.takeWidget()
        self._principal.devolver_modo(abas.TEXTO)
        self.janela.hide()
        self._texto.editor.setFocus()

    def trazer(self, painel: QWidget) -> bool:
        """Traz a janela da mesa à frente quando `painel` é o texto destacado. `False` quando não é.

        É o pré-requisito 3: quem pede à janela principal «mostre a aba Texto» com a mesa destacada
        receberia o cartão, e a letra inserida pela paleta cairia num editor que ninguém vê.
        """
        if painel is not self._texto or not self.destacada:
            return False
        self.janela.show()
        self.janela.raise_()
        self.janela.activateWindow()
        return True

    def fechar(self) -> None:
        """A janela principal vai fechar: o texto volta, e a mesa fecha junto."""
        self.devolver()
        self.janela.close()

    # ------------------------------------------------------------------------------ por dentro

    def _comandos_da_mesa(self) -> dict[str, Callable[[], object]]:
        comandos: dict[str, Callable[[], object]] = {}
        for acao in mesa.ACOES_DA_MESA_DESTACADA:
            atendida = self._texto.atender(acao)
            if atendida is not None:
                comandos[acao] = atendida
        return comandos

    def _montar_cartao(self) -> QFrame:
        cartao = QFrame()
        cartao.setAccessibleName(mesa.CARTAO_DA_MESA)
        coluna = QVBoxLayout(cartao)
        margem = espaco.margem_da_aba()
        coluna.setContentsMargins(margem, margem, margem, margem)
        frase = QLabel(mesa.CARTAO_DA_MESA, cartao)
        frase.setWordWrap(True)
        coluna.addWidget(frase)
        linha = QHBoxLayout()
        self.botao_mostrar = QPushButton("Mostrar", cartao)
        tema.aplicar_papel(self.botao_mostrar, estilos.PRIMARIO)
        self.botao_mostrar.setToolTip("Trazer a janela da mesa para a frente")
        self.botao_mostrar.clicked.connect(lambda: self.trazer(self._texto))
        self.botao_trazer = QPushButton("Trazer de volta", cartao)
        tema.aplicar_papel(self.botao_trazer, estilos.NEUTRO)
        self.botao_trazer.setToolTip("Devolver o texto a esta aba e fechar a janela da mesa")
        self.botao_trazer.clicked.connect(self.devolver)
        linha.addWidget(self.botao_mostrar)
        linha.addWidget(self.botao_trazer)
        linha.addStretch(1)
        coluna.addLayout(linha)
        coluna.addStretch(1)
        return cartao

    def _atualizar_a_folha(self) -> None:
        """A vista mostra a folha que o editor tem rasterizada; só troca quando ela é outra."""
        if not self.destacada:
            return
        folha, dpi = self._texto.folha_rasterizada()
        if folha is None or folha is self._folha_mostrada:
            return
        self._folha_mostrada = folha
        self.janela.visor.mostrar_pagina(folha, dpi=dpi)

    def _destacar(self, bbox: object) -> None:
        if self.destacada:
            self.janela.visor.definir_destaque(bbox)  # type: ignore[arg-type]
