"""O cabeçalho da partida na sala de estudo: a faixa de duas linhas e o formulário (S-530, S-866).

**Saiu de `qt/painel_de_estudo.py` com os dois widgets que só ele usava**: o rótulo que corta o
próprio texto e o diálogo dos nove headers. Quem diz o que a frase diz, quais são os campos e o que
um campo vazio grava é `ui/cabecalho_da_partida.py`; aqui fica o desenho. Gravar continua sendo do
painel, porque gravar é edição da sala e entra no `Ctrl+Z` dela.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFontMetrics, QResizeEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import icones as qt_icones
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import cabecalho_da_partida, espaco, tipografia, tokens

__all__ = ["CabecalhoDaPartida", "JanelaDoCabecalho"]


class CabecalhoDaPartida(QWidget):
    """Duas linhas e um lápis: quem jogou, e onde. Clicar em qualquer uma abre a edição.

    **Duas linhas, e a segunda é secundária.** Jogadores e resultado numa; torneio, local, data
    e rodada na outra, na cor de texto secundário. É a hierarquia do ChessBase, e é o que faz a
    faixa caber em 494 px -- a largura da coluna a 1400x950 -- sem elidir o nome de ninguém.

    **O botão existe porque não há comando.** Editar o cabeçalho ainda não está em
    `ui/comandos.py`, então não há item de menu, tecla nem entrada na paleta para ele -- e uma
    faixa que só responde a duplo clique é uma função que ninguém acha. O lápis ao lado é a
    afirmação de que aquilo é editável; o duplo clique na frase faz o mesmo, que é o gesto que
    quem vem do ChessBase já tem no dedo.
    """

    def __init__(self, pai: QWidget, *, lado_do_icone: int, editar: Callable[[], object]) -> None:
        super().__init__(pai)
        self._lado_do_icone = lado_do_icone
        linha = QHBoxLayout(self)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(espaco.folga())

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(0)
        self.lbl_partida = _RotuloElidido(self)
        self.lbl_partida.setFont(tema.fonte_atual(tipografia.TITULO))
        textos.addWidget(self.lbl_partida)
        self.lbl_torneio = _RotuloElidido(self)
        self.lbl_torneio.setFont(tema.fonte_atual(tipografia.AUXILIAR))
        tema.pintar(self.lbl_torneio, "color", tokens.TEXTO_SECUNDARIO)
        textos.addWidget(self.lbl_torneio)
        linha.addLayout(textos, 1)

        self.btn_cabecalho = QToolButton(self)
        self.btn_cabecalho.setProperty("acao", "editar_cabecalho")
        self.btn_cabecalho.setAutoRaise(True)
        self.btn_cabecalho.setIconSize(qt_icones.tamanho(lado_do_icone))
        self.btn_cabecalho.clicked.connect(editar)
        linha.addWidget(self.btn_cabecalho)

        for alvo in (self.lbl_partida, self.lbl_torneio):
            alvo.setCursor(Qt.CursorShape.PointingHandCursor)
            alvo.mouseDoubleClickEvent = lambda _evento: editar()  # type: ignore[assignment]
        self._pintar_o_lapis()
        tema.ao_repintar(self._pintar_o_lapis)

    def _pintar_o_lapis(self) -> None:
        """O traço do botão do cabeçalho na cor da pele em uso -- a medição da S-220."""
        desenho = qt_icones.icone(
            cabecalho_da_partida.ICONE,
            self._lado_do_icone,
            tema.cor_atual(tokens.TEXTO_PADRAO),
            escala=self.devicePixelRatioF(),
        )
        if desenho is not None:
            self.btn_cabecalho.setIcon(desenho)

    def mostrar(self, headers: Any) -> None:
        """Põe na faixa o que os headers dizem. Quem elide é o próprio rótulo, a cada largura."""
        primeira, segunda = cabecalho_da_partida.linhas(headers)
        self.lbl_partida.definir_texto(primeira)
        self.lbl_torneio.definir_texto(segunda)
        dica_em(
            self.btn_cabecalho,
            f"{cabecalho_da_partida.TITULO}\nDuplo clique na frase ao lado faz o mesmo.",
        )


class _RotuloElidido(QLabel):
    """Um `QLabel` de uma linha que corta o próprio texto com `...` quando ele não cabe (S-530).

    **Elidir no momento de escrever não funciona**, e foi medido: `mostrar` roda dentro do
    `refresh` do painel, que é chamado na montagem -- ali o rótulo ainda tem a largura de fábrica, e
    a frase saía como `Jogadores nã...` numa faixa de 494 px. Quem sabe a largura é o rótulo, e ele
    só a sabe no `resizeEvent` dele.

    A dica carrega a frase inteira: o nome que não coube continua alcançável sem abrir o diálogo,
    que é o que um `...` sozinho não dá.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self._inteiro = ""

    def definir_texto(self, texto: str) -> None:
        self._inteiro = str(texto)
        self.setToolTip(self._inteiro)
        self.setVisible(bool(self._inteiro))
        self._reescrever()

    def texto_inteiro(self) -> str:
        """O que a frase diz antes de ser cortada. É por ele que o teste pergunta."""
        return self._inteiro

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """O mínimo é o da reticência, e não o da frase inteira (o merge do religa com o `main`).

        Um `QLabel` de uma linha pede a largura do texto como mínimo, e um rótulo que corta o
        próprio texto não precisa dela -- é para isso que ele corta. Com a fonte de título do
        religa a frase pedia 384 px, a coluna do tabuleiro não descia abaixo disso, e a fração que
        a sessão guardou não voltava: 0,4 virava 0,48 numa sala de 900 px.
        """
        dica = super().minimumSizeHint()
        return QSize(QFontMetrics(self.font()).horizontalAdvance("…"), dica.height())

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._reescrever()

    def _reescrever(self) -> None:
        largura = self.width()
        if largura <= 0:
            self.setText(self._inteiro)
            return
        metrica = QFontMetrics(self.font())
        self.setText(metrica.elidedText(self._inteiro, Qt.TextElideMode.ElideRight, largura))


class JanelaDoCabecalho(QDialog):
    """O formulário dos nove headers da partida (S-530).

    **Um `QComboBox` para o resultado, e campo livre para o resto.** `1:0`, `1-0 ` e `1–0` com
    travessão são o que se digita sem querer, e qualquer um faz o PGN ser recusado por quem o ler;
    os outros oito não têm forma fechada -- nome de jogador e de torneio são o que o livro imprimiu.

    Quem diz quais são os campos, em que ordem e o que um campo vazio grava é
    `ui/cabecalho_da_partida.py`. Este arquivo só desenha.
    """

    def __init__(
        self,
        pai: QWidget,
        headers: Any,
        gravar: Callable[[dict[str, str]], None],
    ) -> None:
        super().__init__(pai)
        self.setWindowTitle(cabecalho_da_partida.TITULO)
        self._gravar = gravar
        self.campos: dict[str, QWidget] = {}
        pilha = QVBoxLayout(self)
        pilha.setContentsMargins(*(espaco.moldura(),) * 4)
        pilha.setSpacing(espaco.folga())

        grade = QGridLayout()
        grade.setHorizontalSpacing(espaco.folga())
        grade.setVerticalSpacing(espaco.linha())
        valores = cabecalho_da_partida.valores_para_o_formulario(headers)
        # **O campo estreito fica na linha do anterior**, e não na seguinte: `Brancas [nome] Elo
        # [2720]` é uma pergunta só, e separá-los em duas linhas dobraria a altura do formulário
        # para dizer a mesma coisa. `linha` só avança em campo largo.
        linha, coluna = -1, 0
        for campo in cabecalho_da_partida.CAMPOS:
            if campo.estreito and linha >= 0:
                coluna = 2
            else:
                linha += 1
                coluna = 0
            grade.addWidget(QLabel(campo.rotulo, self), linha, coluna)
            editor: QWidget
            if campo.escolhas:
                caixa = QComboBox(self)
                caixa.addItems(campo.escolhas)
                atual = valores.get(campo.chave) or campo.escolhas[0]
                caixa.setCurrentIndex(max(0, caixa.findText(atual)))
                editor = caixa
            else:
                texto = QLineEdit(valores.get(campo.chave, ""), self)
                if campo.estreito:
                    texto.setMaximumWidth(8 * tema.altura_de_linha_atual())
                editor = texto
            if campo.dica:
                dica_em(editor, campo.dica)
            grade.addWidget(editor, linha, coluna + 1)
            self.campos[campo.chave] = editor
        grade.setColumnStretch(1, 1)
        pilha.addLayout(grade)

        # **Os dois botões com texto próprio**, e não `StandardButton.Save`: o texto padrão do Qt
        # é "Save"/"Cancel" em inglês, e a janela inteira fala português. É a forma que
        # `qt/dialogos.py` já usa nos dois diálogos de base.
        botoes = QDialogButtonBox(parent=self)
        botoes.addButton("Gravar", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        pilha.addWidget(botoes)
        # O nome de um jogador não cabe no que a grade pede: `Capablanca, José Raúl` saía cortado
        # num diálogo de 328 px. A altura continua sendo a que os nove campos pedem.
        self.resize(max(520, self.sizeHint().width()), self.sizeHint().height())
        self.show()

    def valores(self) -> dict[str, str]:
        """O que está nos campos agora, por chave de PGN."""
        lidos: dict[str, str] = {}
        for chave, editor in self.campos.items():
            if isinstance(editor, QComboBox):
                lidos[chave] = editor.currentText()
            elif isinstance(editor, QLineEdit):
                lidos[chave] = editor.text()
        return lidos

    def _confirmar(self) -> None:
        valores = self.valores()
        self.accept()
        self._gravar(valores)
