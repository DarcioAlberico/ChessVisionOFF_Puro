"""O painel de navegação da aba Texto (S-654): títulos, folhas, resultados e correções.

É o painel de navegação do WordCraft (`panes.rs:120-310`) com as perguntas desta aba. Quatro abas:

- **Títulos** -- os parágrafos de estilo `titulo` da folha; o clique leva ao título;
- **Folhas** -- o índice do caderno (S-613), o mesmo widget de `qt/indice_do_caderno.py`;
- **Resultados** -- a busca da S-343 em lista, cada achado com o trecho em volta e o achado em
  negrito; o clique o seleciona. A janela de busca continua sendo onde se substitui;
- **Correções** -- o que a mão mudou sobre o que o motor leu (`text/correcao.py`), uma linha por
  troca; o clique leva ao bloco dela. É a lista da S-650 (Revisão › Correções).

**Ele não decide nada.** Quem acha os títulos é `rico.titulos`; quem acha as ocorrências é
`text/busca`; quem conta as correções é `text/correcao`. O painel recebe o que eles devolveram e
diz qual linha foi clicada, em deslocamento do documento.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt.indice_do_caderno import IndiceDoCaderno
from chess_diagram_ocr.text import busca
from chess_diagram_ocr.ui import strings

__all__ = ["ANTES", "DEPOIS", "PainelDeNavegacao"]

ANTES = 30
DEPOIS = 40
"""Quantos caracteres de cada lado o resultado mostra (S-654): os do WordCraft."""

_DESLOCAMENTO = Qt.ItemDataRole.UserRole
_FIM = Qt.ItemDataRole.UserRole + 1

TITULOS, FOLHAS, RESULTADOS, CORRECOES = range(4)


class PainelDeNavegacao(QTabWidget):
    """O painel, à esquerda do editor. Nasce escondido: é um caminho a mais, como a paleta."""

    ir_para = pyqtSignal(int, int)
    """Uma linha clicada: `(início, fim)` no documento. `fim == início` põe só o cursor."""

    busca_mudou = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Painel de navegação")
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance("Títulos Folhas Resultados Correções") + 64)  # as quatro abas cabem sem rolar
        self.titulos = self._lista("Títulos da folha")
        self.indice = IndiceDoCaderno(self)
        self.indice.show()  # dentro do painel ele aparece com a aba; quem esconde é o painel
        self.campo_de_busca = QLineEdit(self)
        self.campo_de_busca.setAccessibleName("Procurar na folha")
        self.campo_de_busca.setPlaceholderText("Procurar na folha…")
        self.palavra_inteira = QCheckBox(strings.BUSCA_PALAVRA_INTEIRA, self)
        self.curingas = QCheckBox(strings.BUSCA_CURINGAS, self)
        self.resultados = self._lista("Resultados da busca")
        self.correcoes = self._lista("Correções da folha")
        aba_de_busca = QWidget(self)
        pilha = QVBoxLayout(aba_de_busca)
        pilha.setContentsMargins(2, 2, 2, 2)
        pilha.addWidget(self.campo_de_busca)
        opcoes = QHBoxLayout()
        opcoes.addWidget(self.palavra_inteira)
        opcoes.addWidget(self.curingas)
        pilha.addLayout(opcoes)
        self.recado_da_busca = QLabel("", self)
        self.recado_da_busca.setWordWrap(True)
        pilha.addWidget(self.recado_da_busca)
        pilha.addWidget(self.resultados, 1)
        self.addTab(self.titulos, "Títulos")
        self.addTab(self.indice, "Folhas")
        self.addTab(aba_de_busca, "Resultados")
        self.addTab(self.correcoes, "Correções")
        self.campo_de_busca.textChanged.connect(lambda _t: self.busca_mudou.emit())
        self.palavra_inteira.toggled.connect(lambda _l: self.busca_mudou.emit())
        self.curingas.toggled.connect(lambda _l: self.busca_mudou.emit())
        self.hide()

    def _lista(self, nome: str) -> QListWidget:
        lista = QListWidget(self)
        lista.setAccessibleName(nome)
        lista.itemClicked.connect(self._clicou)
        lista.itemActivated.connect(self._clicou)
        return lista

    def _clicou(self, item: QListWidgetItem) -> None:
        inicio = item.data(_DESLOCAMENTO)
        if inicio is None:
            return
        fim = item.data(_FIM)
        self.ir_para.emit(int(inicio), int(fim if fim is not None else inicio))

    # ------------------------------------------------------------------------- o conteúdo

    def mostrar_titulos(self, titulos: Sequence[tuple[int, str]]) -> None:
        self.titulos.clear()
        for deslocamento, texto in titulos:
            item = QListWidgetItem(texto.strip() or "(título vazio)")
            item.setData(_DESLOCAMENTO, int(deslocamento))
            self.titulos.addItem(item)

    def mostrar_resultados(self, texto: str, achados: Sequence[busca.Ocorrencia], *, recado: str = "") -> None:
        """Os achados em lista, cada um com 30 caracteres antes e 40 depois, o achado em negrito."""
        self.resultados.clear()
        self.recado_da_busca.setText(recado or (f"{len(achados)} achado(s)" if self.campo_de_busca.text() else ""))
        for ocorrencia in achados:
            antes = texto[max(0, ocorrencia.inicio - ANTES) : ocorrencia.inicio].replace("\n", " ")
            depois = texto[ocorrencia.fim : ocorrencia.fim + DEPOIS].replace("\n", " ")
            item = QListWidgetItem(f"{antes}{ocorrencia.texto}{depois}")
            item.setData(_DESLOCAMENTO, ocorrencia.inicio)
            item.setData(_FIM, ocorrencia.fim)
            item.setToolTip(f"{antes}[{ocorrencia.texto}]{depois}")
            self.resultados.addItem(item)
            rotulo = QLabel(f"{html.escape(antes)}<b>{html.escape(ocorrencia.texto)}</b>{html.escape(depois)}")
            rotulo.setTextFormat(Qt.TextFormat.RichText)
            rotulo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.resultados.setItemWidget(item, rotulo)

    def mostrar_correcoes(self, linhas: Sequence[tuple[int, str]]) -> None:
        self.correcoes.clear()
        for deslocamento, texto in linhas:
            item = QListWidgetItem(texto)
            if deslocamento >= 0:
                item.setData(_DESLOCAMENTO, int(deslocamento))
            self.correcoes.addItem(item)
        if not linhas:
            self.correcoes.addItem(QListWidgetItem("Nenhuma correção sobre o que o motor leu."))

    def opcoes_da_busca(self) -> tuple[str, bool, bool]:
        return self.campo_de_busca.text(), self.palavra_inteira.isChecked(), self.curingas.isChecked()
