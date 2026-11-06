"""A janela de «Corrigir em todas as folhas» (S-766): quem decide é `text/correcao_no_livro.py`, e aqui só se mostra a prévia.

**A prévia é obrigatória, e o botão diz isso.** «Aplicar» só acende com uma lista na tela, e mudar um dos dois campos a apaga: a lista que a pessoa vê é sempre
a da troca que vai acontecer. Cada ocorrência tem a caixa dela, e a folha conferida vem desmarcada.

**A janela não é modal, e isso custou texto.** A pessoa vê a prévia, digita na folha da tela e aplica: a troca lia o disco, regravava por cima e o `abrir` limpava o histórico, e o que ela digitou sumia da tela e do
disco. Por isso `aplicar_marcadas` guarda a folha da tela **antes**: o digitado vai ao caderno, o resumo da folha deixa de bater com o da prévia, e ela é contada como mudada. E o caderno tem de ser ainda o da
aba: trocar de livro com a janela aberta gravava no caderno antigo, já sem a trava, e recarregava a folha de mesmo índice do livro novo.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.text import correcao_no_livro as modelo
from chess_diagram_ocr.ui import estilos

logger = logging.getLogger(__name__)


class JanelaDeCorrecaoNoLivro(QDialog):
    """A troca, a lista, e os dois botões. Ver o cabeçalho."""

    def __init__(self, painel: Any, caderno: Any, *, antes: str = "", depois: str = "", pai: QWidget | None = None) -> None:
        super().__init__(pai if pai is not None else painel)
        self._painel = painel
        self._caderno = caderno
        self._vista: modelo.Previa | None = None
        self.setWindowTitle("Corrigir em todas as folhas")
        self.setModal(False)
        self.campo_antes = QLineEdit(antes, self)
        self.campo_depois = QLineEdit(depois, self)
        self.campo_antes.setAccessibleName("A palavra como o motor a leu")
        self.campo_depois.setAccessibleName("A palavra corrigida")
        formulario = QFormLayout()
        formulario.addRow("Trocar", self.campo_antes)
        formulario.addRow("por", self.campo_depois)
        self.resumo = QLabel("Veja a prévia antes de aplicar: nada muda sem você ver.", self)
        self.resumo.setWordWrap(True)
        self.lista = QListWidget(self)
        self.lista.setAccessibleName("As ocorrências em cada folha do caderno")
        self.btn_previa = QPushButton("Ver a prévia", self)
        self.btn_aplicar = QPushButton("Aplicar nas marcadas", self)
        self.btn_aplicar.setEnabled(False)
        self.btn_fechar = QPushButton("Fechar", self)
        for botao in (self.btn_previa, self.btn_aplicar, self.btn_fechar):
            tema.aplicar_papel(botao, estilos.NEUTRO)
        botoes = QHBoxLayout()
        botoes.addWidget(self.btn_previa)
        botoes.addStretch(1)
        botoes.addWidget(self.btn_aplicar)
        botoes.addWidget(self.btn_fechar)
        fora = QVBoxLayout(self)
        fora.addLayout(formulario)
        fora.addWidget(self.resumo)
        fora.addWidget(self.lista, 1)
        fora.addLayout(botoes)
        self.resize(620, 420)
        self.btn_previa.clicked.connect(self._clicou_previa)
        self.btn_aplicar.clicked.connect(self._clicou_aplicar)
        self.btn_fechar.clicked.connect(self.close)
        self.campo_antes.textChanged.connect(self._campo_mudou)
        self.campo_depois.textChanged.connect(self._campo_mudou)

    def _clicou_previa(self, _marcado: bool = False) -> None:
        self.ver_previa()

    def _clicou_aplicar(self, _marcado: bool = False) -> None:
        self.aplicar_marcadas()

    def _campo_mudou(self, _texto: str) -> None:
        """A lista na tela era de outra troca: ela sai, e o botão apaga."""
        self._vista = None
        self.lista.clear()
        self.btn_aplicar.setEnabled(False)
        self.resumo.setText("A troca mudou: veja a prévia de novo.")

    def _caderno_ainda_e_o_da_aba(self) -> bool:
        if self._painel.caderno_aberto is self._caderno:
            return True
        self._vista = None
        self.lista.clear()
        self.btn_aplicar.setEnabled(False)
        self.btn_previa.setEnabled(False)
        self.resumo.setText("O livro da aba mudou: esta troca era do outro. Feche e abra de novo, no livro certo.")
        return False

    def ver_previa(self) -> modelo.Previa | None:
        if not self._caderno_ainda_e_o_da_aba():
            return None
        vista = modelo.previa(self._caderno, self.campo_antes.text().strip(), self.campo_depois.text().strip())
        self._vista = vista
        self.lista.clear()
        desmarcadas = vista.desmarcadas_por_padrao()
        for i, item in enumerate(vista.ocorrencias):
            linha = QListWidgetItem(item.rotulo + ("  (conferida)" if item.conferida else ""), self.lista)
            linha.setFlags(linha.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            linha.setCheckState(Qt.CheckState.Unchecked if i in desmarcadas else Qt.CheckState.Checked)
        self.btn_aplicar.setEnabled(bool(vista.ocorrencias) and bool(vista.depois))
        self.resumo.setText(modelo.frase_da_previa(vista))
        return vista

    def _fora(self) -> list[int]:
        return [i for i in range(self.lista.count()) if (linha := self.lista.item(i)) is not None and linha.checkState() != Qt.CheckState.Checked]

    def aplicar_marcadas(self) -> modelo.Aplicado | None:
        """Aplica o que está marcado. **Sem prévia na tela não há o que aplicar**, e o botão nem acende."""
        if self._vista is None or not self.btn_aplicar.isEnabled() or not self._caderno_ainda_e_o_da_aba():
            return None
        if not self._painel._guardar_a_folha():  # noqa: SLF001 - o que foi digitado depois da prévia tem de estar no disco: ver o cabeçalho
            self.resumo.setText("A folha da tela não gravou, e nada foi trocado: ela perderia o que você digitou.")
            return None
        feito = modelo.aplicar(self._caderno, self._vista, fora=self._fora())
        self.resumo.setText(modelo.frase_do_resultado(feito))
        self.btn_aplicar.setEnabled(False)
        self._vista = None
        self.lista.clear()
        self._painel.folhas_corrigidas_no_livro(feito)
        return feito
