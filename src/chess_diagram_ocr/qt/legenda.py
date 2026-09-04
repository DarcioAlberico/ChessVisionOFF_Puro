"""A legenda de atalhos do menu Ajuda, no Qt (S-165/S-501).

**Gerada da mesma tabela que liga as teclas**, como a do Tk: esta janela percorre
`atalhos.ATALHOS`, e quem acrescentar uma tecla ganha a linha nas **duas** janelas de graça. Uma
segunda lista escrita à mão diverge da primeira -- é o que aconteceu com os rótulos de procedência
antes da S-04.

A frase de cada linha vem de `atalhos.descricao_completa`, que passou a ser pública na S-501 pela
mesma razão: ela conta os três destinos de uma tecla (janela, editor, sala de estudo), e uma
legenda que contasse um só seria pior que não ter legenda. Era privada dentro de `ui/legenda.py`,
cuja classe herda de `tk.Toplevel` -- então nem o import tardio a alcançava.

**Um diálogo e não uma `QMessageBox`**, e é o mesmo argumento do outro lado: a tecla precisa de
destaque tipográfico próprio (é dado, e vai em monoespaçada pela S-149), e a caixa do sistema só
sabe mostrar um bloco de texto -- onde `Ctrl+S` e a frase ao lado teriam a mesma aparência, que é
justamente o que não ajuda a achar a linha certa.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import atalhos, espaco, tipografia, tokens

__all__ = ["TITULO", "JanelaDeAtalhos", "abrir"]

TITULO = "Atalhos de teclado"

NOTA = (
    "A tecla é do editor quando o foco está num campo de texto: ali ← e Delete pertencem ao "
    "campo. As que têm segunda linha acima mudam de destino conforme o foco."
)
"""A guarda de foco da S-20, dita onde ela é procurada: a legenda é o único lugar em que alguém
pergunta "por que a seta não trocou de diagrama agora?"."""

CALHA = 18
"""Entre a tecla e a descrição. **Não é `espaco.folga()`**, e a distinção é da S-447: isto é
separação de coluna de tabela, e não vão entre vizinhos. O mesmo número do outro frontend."""


class JanelaDeAtalhos(QDialog):
    """Uma linha por atalho: a tecla à esquerda, o que ela faz à direita.

    **Rolável, ao contrário da do Tk.** Lá a janela é `resizable(False, False)` e as vinte e uma
    linhas cabem porque cabem; aqui a lista entra num `QScrollArea`, porque o mesmo diálogo numa
    tela de 768 px com a fonte do Windows em 12 pt passa da altura -- e uma legenda cujo fim não
    se alcança é o defeito que ela existe para não ter.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITULO)
        # `Escape` fecha de graça num `QDialog` -- é o que a S-395 teve de amarrar à mão no Tk,
        # e a razão continua valendo: esta é a janela que mais se abre para consultar e fechar.
        fora = QVBoxLayout(self)
        fora.setContentsMargins(*(espaco.moldura(),) * 4)
        fora.setSpacing(espaco.folga())

        titulo = QLabel(TITULO, self)
        titulo.setFont(tema.fonte_atual(tipografia.TITULO))
        fora.addWidget(titulo)

        self._linhas: list[tuple[str, str]] = []
        corpo = QWidget(self)
        grade = QGridLayout(corpo)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setHorizontalSpacing(CALHA)
        grade.setVerticalSpacing(espaco.minima())
        # As da janela e as da sala (S-527): uma tecla que não está escrita em lugar nenhum é o
        # defeito da S-161, e as quatro da sala só apareciam na dica do botão.
        for linha, atalho in enumerate((*atalhos.ATALHOS, *atalhos.TECLAS_DA_SALA)):
            tecla = QLabel(atalho.rotulo, corpo)
            tecla.setFont(tema.fonte_atual(tipografia.DADO))
            tecla.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            descricao = atalhos.descricao_completa(atalho)
            grade.addWidget(tecla, linha, 0)
            grade.addWidget(QLabel(descricao, corpo), linha, 1)
            self._linhas.append((atalho.rotulo, descricao))
        grade.setColumnStretch(1, 1)

        rolagem = QScrollArea(self)
        rolagem.setWidget(corpo)
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.Shape.NoFrame)
        fora.addWidget(rolagem, 1)

        nota = QLabel(NOTA, self)
        nota.setWordWrap(True)
        nota.setFont(tema.fonte_atual(tipografia.AUXILIAR))
        tema.pintar(nota, "color", tokens.TEXTO_SECUNDARIO)
        fora.addWidget(nota)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        botoes.rejected.connect(self.reject)
        fora.addWidget(botoes)

    def linhas(self) -> list[tuple[str, str]]:
        """(tecla, descrição) de cada linha desenhada. É o que o teste percorre.

        Guardadas na montagem em vez de lidas da árvore de widgets. A versão do Tk as relê do
        `winfo_children` e precisa descartar o título e a nota de rodapé pela posição -- o que faz
        acrescentar um rótulo à janela quebrar a leitura. Aqui a lista é o que foi desenhado.
        """
        return list(self._linhas)


def abrir(pai: QWidget) -> JanelaDeAtalhos:
    """Abre a legenda. Uma por vez: reabrir traz a que já está aberta para a frente."""
    for filho in pai.findChildren(JanelaDeAtalhos):
        filho.show()
        filho.raise_()
        filho.activateWindow()
        return filho
    janela = JanelaDeAtalhos(pai)
    janela.show()
    return janela
