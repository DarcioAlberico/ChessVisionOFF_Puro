"""O tabuleiro da conferência de importação: corrige peças e anota as marcas impressas.

**Herda de `TabuleiroEditavel` em vez de alterá-lo.** O editável é o tabuleiro do painel de resultado
e de outras telas que não têm marca nenhuma; aqui só se acrescenta uma camada por cima e um modo.

**O modo é a ferramenta na mão.** Sem ferramenta, o widget é o editável, inteiro: o clique seleciona e
arrasta peça, e o botão direito apaga peça. Com uma ferramenta de marca, os gestos passam a ser sobre
as marcas: o clique alterna a marca na casa, o arrasto desenha o traço, e o botão direito tira a marca
ou o traço -- **e nunca a peça**, porque quem está anotando não pediu para mexer na posição. A única
exceção é explícita: `definir_esvaziar`.

**Por que marcar esvazia a casa.** O modelo lê marca como peça: na medição de 2026-11-04, as 22 casas
marcadas de 7 diagramas saíram como peça. Sem isto, cada marca custaria dois gestos, e o segundo
esquecido grava uma peça que não existe. A peça riscada, em que a marca está mesmo sobre uma peça, é
o caso raro, e é para ele que a opção desliga.

A camada não entra em `posicao()`: a FEN continua sendo só as peças.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QPainter, QPaintEvent
from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr.fen_utils import square_name
from chess_diagram_ocr.qt import desenho_de_marcas as desenho
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.tabuleiro_editavel import TabuleiroEditavel
from chess_diagram_ocr.ui import board_edit, tokens

__all__ = ["TabuleiroDeMarcas"]

OPACIDADE_DA_SUGESTAO = 0.45
"""A sugestão do detector é mais apagada que a marca anotada: quem olha precisa saber qual é qual."""


class TabuleiroDeMarcas(TabuleiroEditavel):
    """Um `TabuleiroEditavel` com a camada de marcas. Emite `marcas_mudaram` a cada anotação."""

    marcas_mudaram = pyqtSignal(object)
    """As `MarcasDoDiagrama` novas. Só sai de gesto da pessoa: `definir_marcas` não emite, e abrir
    uma imagem não pode parecer uma anotação."""

    def __init__(self, parent: QWidget | None = None, **opcoes: object) -> None:
        super().__init__(parent, **opcoes)
        self._marcas = mc.MarcasDoDiagrama()
        self._sugestao: dict[str, str] = {}
        self._ferramenta: str | None = None
        self._esvaziar = True
        self._traco_de: tuple[float, float] | None = None
        self._traco_ate: tuple[float, float] | None = None

    # ------------------------------------------------------------------------------ estado

    def marcas(self) -> mc.MarcasDoDiagrama:
        return self._marcas

    def definir_marcas(self, marcas: mc.MarcasDoDiagrama) -> None:
        """As marcas da imagem que abriu. Larga o traço pela metade, que era da imagem anterior."""
        self._marcas = marcas
        self._traco_de = self._traco_ate = None
        self.update()

    def definir_sugestao(self, sugestao: dict[str, str]) -> None:
        """O que o detector de marcas viu nesta imagem. Aparece em fantasma e não é anotação."""
        self._sugestao = dict(sugestao)
        self.update()

    def sugestao_pendente(self) -> dict[str, str]:
        """A sugestão nas casas ainda sem marca: o que aceitar acrescentaria."""
        return {nome: tipo for nome, tipo in self._sugestao.items() if nome not in self._marcas.casas}

    def aceitar_sugestao(self) -> None:
        """A sugestão vira anotação, com as mesmas regras de marcar à mão: é a pessoa que decide aqui."""
        novas = self._marcas
        for nome, tipo in self.sugestao_pendente().items():
            novas = novas.alternar_casa(tipo, nome)
            indice = mc.indice_da_casa(nome)
            if self._esvaziar and board_edit.piece_at(self.modelo.placement, indice):
                self._aplicar(self.modelo.erase(indice))
        self._mudou(novas)

    def ferramenta(self) -> str | None:
        return self._ferramenta

    def definir_ferramenta(self, tipo: str | None) -> None:
        """A marca que o próximo gesto põe. `None` devolve o tabuleiro à correção de peças."""
        self._ferramenta = tipo
        self._traco_de = self._traco_ate = None
        if tipo is None:
            self.unsetCursor()
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def definir_esvaziar(self, ligado: bool) -> None:
        """Se pôr uma marca de casa também tira a peça que estiver nela."""
        self._esvaziar = bool(ligado)

    def esvaziar_marcadas(self) -> None:
        """Tira a peça de cada casa marcada. Para quando a posição veio de novo de uma leitura."""
        for nome in self._marcas.casas:
            self._aplicar(self.modelo.erase(mc.indice_da_casa(nome)))

    def _mudou(self, novas: mc.MarcasDoDiagrama) -> None:
        if novas == self._marcas:
            return
        self._marcas = novas
        self.update()
        self.marcas_mudaram.emit(novas)

    # ------------------------------------------------------------------------------ gestos

    def _ponto_em(self, ponto: QPoint) -> tuple[float, float]:
        """O pixel em unidades de casa, na orientação gravada e não na da tela."""
        geo = self.geometria()
        x = (ponto.x() - geo.origin_x) / max(1.0, geo.cell)
        y = (ponto.y() - geo.origin_y) / max(1.0, geo.cell)
        return (8 - x, 8 - y) if self.modelo.flipped else (x, y)

    def _alternar_na_casa(self, indice: int) -> None:
        """Alterna a marca da ferramenta. Só pôr esvazia: tirar a marca não mexe na posição."""
        assert self._ferramenta is not None
        nome = square_name(indice)
        novas = self._marcas.alternar_casa(self._ferramenta, nome)
        if self._esvaziar and nome in novas.casas and board_edit.piece_at(self.modelo.placement, indice):
            self._aplicar(self.modelo.erase(indice))
        self._mudou(novas)

    def _tirar_em(self, ponto: QPoint) -> None:
        """Botão direito com ferramenta: a marca da casa, ou então o traço mais próximo."""
        indice = self._casa_em(ponto)
        nome = square_name(indice) if indice is not None else ""
        if nome in self._marcas.casas:
            self._mudou(self._marcas.sem_casa(nome))
        else:
            self._mudou(self._marcas.sem_traco_perto(self._ponto_em(ponto)))

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None or self._ferramenta is None:
            super().mousePressEvent(a0)
            return
        ponto = a0.position().toPoint()
        if a0.button() == Qt.MouseButton.RightButton:
            self._tirar_em(ponto)
            return
        if a0.button() != Qt.MouseButton.LeftButton:
            return
        indice = self._casa_em(ponto)
        if indice is None:
            return
        if self._ferramenta in mc.TIPOS_DE_TRACO:
            self._traco_de = self._traco_ate = mc.na_grade(*self._ponto_em(ponto))
            self.update()
        else:
            self._alternar_na_casa(indice)

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().mouseMoveEvent(a0)
        if a0 is not None and self._traco_de is not None:
            self._traco_ate = mc.na_grade(*self._ponto_em(a0.position().toPoint()))
            self.update()

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None or self._ferramenta is None:
            super().mouseReleaseEvent(a0)
            return
        if a0.button() != Qt.MouseButton.LeftButton or self._traco_de is None:
            return
        de, self._traco_de, self._traco_ate = self._traco_de, None, None
        self.update()
        self._mudou(self._marcas.com_traco(self._ferramenta, de, mc.na_grade(*self._ponto_em(a0.position().toPoint()))))

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """Com marca de casa na mão, `Espaço`/`Enter` alternam na casa selecionada e `Delete` tira.

        As setas continuam andando pela base. O traço não tem gesto de teclado: precisa de dois
        pontos fora do centro da casa, e fica para quando houver quem peça.
        """
        selecionada = self.modelo.selected
        if a0 is None or self._ferramenta is None or selecionada is None:
            super().keyPressEvent(a0)
            return
        if a0.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._mudou(self._marcas.sem_casa(square_name(selecionada)))
        elif a0.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._ferramenta in mc.TIPOS_DE_CASA:
            self._alternar_na_casa(selecionada)
        else:
            super().keyPressEvent(a0)
            return
        a0.accept()

    # ------------------------------------------------------------------------------ desenho

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().paintEvent(a0)
        pendente = self.sugestao_pendente()
        if self._marcas.vazia and self._traco_de is None and not pendente:
            return
        geo = self.geometria()
        virado = self.modelo.flipped
        pintor = QPainter(self)
        if pendente:
            pintor.setOpacity(OPACIDADE_DA_SUGESTAO)
            desenho.pintar_marcas(
                pintor, mc.MarcasDoDiagrama(casas=pendente), geo.origin_x, geo.origin_y, geo.cell, virado=virado
            )
            pintor.setOpacity(1.0)
            # O modelo costuma ler a marca como peça, e a peça cobriria o fantasma justamente aí.
            for nome in pendente:
                self._anel(pintor, geo, mc.indice_da_casa(nome), tema.cor_atual(tokens.SETA_AZUL), tracejado=True)
        desenho.pintar_marcas(pintor, self._marcas, geo.origin_x, geo.origin_y, geo.cell, virado=virado)
        if self._traco_de is not None and self._traco_ate is not None and self._ferramenta in mc.TIPOS_DE_TRACO:
            rascunho = mc.Traco(self._ferramenta, self._traco_de, self._traco_ate)
            desenho.pintar_traco(pintor, rascunho, geo.origin_x, geo.origin_y, geo.cell, virado=virado, tracejado=True)
        pintor.end()
