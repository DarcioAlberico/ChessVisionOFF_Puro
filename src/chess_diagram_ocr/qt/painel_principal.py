"""O painel principal: os quatro painéis do diagrama como **modos**, não como abas (OCR_UI passo 17).

**O que mudou de forma.** Resultado, Estudo, Revisão e Texto eram quatro das oito abas da janela,
com o mesmo peso que Dataset e Galeria. Elas falam do mesmo objeto -- o diagrama e a página que
estão no visor, ao lado -- e o fluxo principal (ler o diagrama → corrigir → exportar) obrigava a
trocar de aba a cada passo. Aqui elas são modos de um painel só: uma barra de botões exclusivos
no topo e o painel do modo escolhido embaixo. A aba que hospeda isto é a `Livro`
(`ui/abas.LIVRO`); as abas do acervo continuam abas.

**O que não mudou.** Os quatro painéis são os de sempre, montados por quem sempre os montou (a
janela); este arquivo só os empilha e os nomeia. A contagem no rótulo (`Revisão (27)`) segue a
mesma regra pura de `ui/abas.rotulo`, porque um modo com fila é a mesma pergunta que uma aba com
fila: quanto falta.

**Um modo é um `QToolButton` marcável e exclusivo**, e não uma aba de segundo nível: a folha de
estilo já desenha `QToolButton:checked` com a cor de seleção, o leitor de tela anuncia "botão,
marcado", e o Tab alcança os quatro na ordem da barra -- que é o que o portão `teclado` cobra.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import abas, espaco, estilos

__all__ = ["PainelPrincipal"]


class PainelPrincipal(QWidget):
    """A barra de modos e a pilha dos painéis do diagrama."""

    modo_mudou = pyqtSignal(str)
    """O nome do modo que passou a estar à frente (`ui/abas.MODOS`)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nomes: list[str] = []
        self._contagens: dict[str, int | None] = {}
        self._botoes: dict[str, QToolButton] = {}
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(espaco.minima())

        self.barra = QWidget(self)
        self.barra.setAccessibleName("Modos do livro")
        linha = QHBoxLayout(self.barra)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(espaco.minima())
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._grupo.idClicked.connect(self._clicou)
        linha.addStretch(1)
        coluna.addWidget(self.barra)

        self.pilha = QStackedWidget(self)
        coluna.addWidget(self.pilha, 1)

    # ------------------------------------------------------------------------------ montagem

    def adicionar_modo(self, nome: str, painel: QWidget) -> None:
        """Um modo a mais, no fim da barra. O primeiro adicionado é o que fica à frente."""
        if nome in self._botoes:
            raise KeyError(f"modo repetido: {nome!r}")
        botao = QToolButton(self.barra)
        botao.setText(abas.rotulo(nome))
        botao.setCheckable(True)
        botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        botao.setAccessibleName(f"Modo {nome}")
        botao.setToolTip(f"Mostrar {nome} neste painel")
        botao.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        tema.aplicar_papel(botao, estilos.NEUTRO)
        indice = len(self._nomes)
        self._grupo.addButton(botao, indice)
        # Antes do `addStretch` que fecha a barra: os botões ficam à esquerda, a folga à direita.
        layout = self.barra.layout()
        assert layout is not None
        layout.insertWidget(indice, botao)  # type: ignore[attr-defined]
        self._nomes.append(nome)
        self._botoes[nome] = botao
        self._contagens[nome] = None
        self.pilha.addWidget(painel)
        if indice == 0:
            botao.setChecked(True)
            self.pilha.setCurrentIndex(0)

    # -------------------------------------------------------------------------------- perguntas

    def modos(self) -> list[str]:
        return list(self._nomes)

    def modo_atual(self) -> str:
        indice = self.pilha.currentIndex()
        return self._nomes[indice] if 0 <= indice < len(self._nomes) else ""

    def widget_do_modo(self, nome: str) -> QWidget | None:
        if nome not in self._botoes:
            return None
        return self.pilha.widget(self._nomes.index(nome))

    def modo_de(self, painel: QWidget) -> str | None:
        """O nome do modo que aquele painel é, ou `None` se ele não mora aqui."""
        indice = self.pilha.indexOf(painel)
        return self._nomes[indice] if indice >= 0 else None

    def painel_atual(self) -> QWidget | None:
        return self.pilha.currentWidget()

    def botao(self, nome: str) -> QToolButton:
        return self._botoes[nome]

    # ---------------------------------------------------------------------------------- gestos

    def definir_modo(self, nome: str) -> bool:
        """Traz aquele modo para a frente. Devolve se **mudou**; nome desconhecido não faz nada."""
        if nome not in self._botoes:
            return False
        indice = self._nomes.index(nome)
        if self.pilha.currentIndex() == indice:
            self._botoes[nome].setChecked(True)
            return False
        self._botoes[nome].setChecked(True)
        self.pilha.setCurrentIndex(indice)
        self.modo_mudou.emit(nome)
        return True

    def _clicou(self, indice: int) -> None:
        if 0 <= indice < len(self._nomes):
            self.definir_modo(self._nomes[indice])

    def definir_contagem(self, nome: str, contagem: int | None) -> None:
        """Quanto trabalho o modo carrega, no rótulo do botão -- a regra de `ui/abas.rotulo`."""
        if nome not in self._botoes:
            return
        self._contagens[nome] = contagem
        self._botoes[nome].setText(abas.rotulo(nome, contagem))

    def rotulo_do_modo(self, nome: str) -> str:
        return self._botoes[nome].text() if nome in self._botoes else ""
