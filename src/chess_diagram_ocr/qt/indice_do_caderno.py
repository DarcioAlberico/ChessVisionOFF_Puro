"""O índice das folhas do caderno: quanto do livro já foi lido, corrigido e conferido (S-613).

É o painel "Páginas" do painel de navegação do WordCraft, com a pergunta deste projeto. Uma linha
por folha que tem caderno, com o estado, o número de correções e a data; o clique abre a folha.

**As linhas vêm do `indice.json`, e nenhum `.cvtxt` é aberto para desenhá-las.** Um livro de 300
folhas corrigidas são 300 arquivos; abrir cada um para pintar uma lista seria pagar a leitura do
livro inteiro a cada gravação. A frase de cada linha é de `ui/texto_declarado.linha_do_indice`;
aqui só se desenha e se diz qual foi clicada.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QMenu, QWidget

from chess_diagram_ocr.text.caderno import EstadoDaFolha
from chess_diagram_ocr.ui.texto_declarado import linha_do_indice

__all__ = ["IndiceDoCaderno"]

_PAGINA = Qt.ItemDataRole.UserRole


class IndiceDoCaderno(QListWidget):
    """A lista das folhas do caderno. Nasce escondida, como a paleta de glifos: é um caminho a mais."""

    folha_escolhida = pyqtSignal(int)
    """A folha clicada ou ativada pelo teclado, 0-based como `PaginaLida.pagina`."""

    alinhar_pedido = pyqtSignal(str)
    """«Alinhar todos os diagramas do caderno» (S-621), pelo menu do botão direito do índice:
    `"esquerda"`, `"centro"` ou `""` (como a preferência). É um comando do caderno inteiro, e é aqui,
    na lista das folhas, que o caderno inteiro está à vista."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Folhas do caderno")
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance("M") * 16)
        # O clique, e o `Enter` pelo teclado (`keyPressEvent`). **Não** o `itemActivated`: no
        # Windows ele é o duplo clique, que chega junto com o `itemClicked` e abriria a folha duas vezes.
        self.itemClicked.connect(self._escolheu)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._abrir_menu)
        self.hide()

    def menu(self) -> QMenu:
        """O menu do botão direito: alinhar os diagramas do caderno inteiro."""
        menu = QMenu(self)
        for rotulo, alinhamento in (
            ("Alinhar todos os diagramas do caderno à esquerda", "esquerda"),
            ("Alinhar todos os diagramas do caderno ao centro", "centro"),
            ("Diagramas do caderno como a preferência", ""),
        ):
            acao = QAction(rotulo, menu)
            acao.triggered.connect(lambda _marcado=False, a=alinhamento: self.alinhar_pedido.emit(a))
            menu.addAction(acao)
        return menu

    def _abrir_menu(self, ponto: object) -> None:
        menu = self.menu()
        menu.exec(self.viewport().mapToGlobal(ponto))  # type: ignore[union-attr,arg-type]
        menu.deleteLater()

    def keyPressEvent(self, e: object) -> None:  # noqa: N802 - API do Qt
        from PyQt6.QtGui import QKeyEvent

        if isinstance(e, QKeyEvent) and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.currentItem():
            self._escolheu(self.currentItem())  # type: ignore[arg-type]
            return
        super().keyPressEvent(e)  # type: ignore[arg-type]

    def mostrar(self, folhas: Sequence[EstadoDaFolha], *, atual: int | None = None) -> None:
        """Redesenha as linhas. A folha da tela fica selecionada, sem disparar `folha_escolhida`."""
        self.blockSignals(True)
        try:
            self.clear()
            for folha in folhas:
                item = QListWidgetItem(linha_do_indice(folha.pagina, folha.estado, folha.correcoes, folha.gravada_em))
                item.setData(_PAGINA, folha.pagina)
                self.addItem(item)
                if folha.pagina == atual:
                    self.setCurrentItem(item)
        finally:
            self.blockSignals(False)

    def paginas(self) -> tuple[int, ...]:
        """As folhas listadas, na ordem da lista. É o que o teste confere sem ler o texto das linhas."""
        return tuple(int(self.item(i).data(_PAGINA)) for i in range(self.count()))  # type: ignore[union-attr]

    def _escolheu(self, item: QListWidgetItem) -> None:
        self.folha_escolhida.emit(int(item.data(_PAGINA)))
