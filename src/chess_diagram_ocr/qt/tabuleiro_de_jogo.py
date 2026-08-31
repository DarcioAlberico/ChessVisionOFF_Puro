"""O tabuleiro em que se **joga**: lance legal, alvos marcados e setas (S-20/S-279/S-503).

Irmão de `qt/tabuleiro_editavel.py`, e a diferença entre os dois é uma palavra: `mode="play"`
contra `mode="edit"` no mesmo `ui/board_model.BoardModel`. É o modelo que sabe que só a peça da
vez pode ser pegada, que `legal_targets` são as casas para onde ela vai, e que soltar fora delas é
desistir do lance -- tudo puro, e com teste sem janela desde a S-49.

**A distinção entre os dois modos é a S-20, e ela não é detalhe.** Corrigir um OCR não é jogar:
quem corrige precisa pôr um bispo preto em h1 se foi isso que o livro imprimiu. Analisar é o
contrário -- um lance ilegal aqui não é uma correção, é um erro de arrasto, e aceitá-lo tiraria da
árvore a única propriedade que a torna PGN.

**A promoção é perguntada por quem tem janela.** O modelo produz o lance; qual peça a coroação
vira é uma escolha da pessoa, e este widget recebe a função que a pergunta -- do mesmo jeito que o
`InteractiveBoard` recebe `promotion_chooser`. Ela devolve `None` quando se desiste, e aí o lance
não acontece.

**A seta é o botão direito, e a cor vem do modificador.** Qual modificador dá qual cor é decisão
compartilhada (`ui/sala_declarada.cor_de_seta_por_modificador`), porque é a ordem do Lichess e do
Chess.com; o que é do toolkit é ler o modificador -- bits de `event.state` no Tk, `enum` aqui.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

import chess
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.tabuleiro import TabuleiroQt
from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.board_model import BoardModel
from chess_diagram_ocr.ui.desenho_do_tabuleiro import BoardGeometry
from chess_diagram_ocr.ui.sala_declarada import cor_de_seta_por_modificador

logger = logging.getLogger(__name__)

__all__ = ["COR_DA_SETA", "LADO_DO_ALVO", "TabuleiroDeJogo"]

LADO_DO_ALVO = 0.28
"""Diâmetro do ponto de "pode ir aqui", em fração da casa.

Ponto e não moldura: numa casa ocupada a moldura disputa com a peça, e o gesto que a marcação
serve -- olhar para onde o bispo alcança -- é justamente o que a peça atrapalha."""

COR_DA_SETA: dict[str, str] = {
    "green": tokens.SETA_VERDE,
    "red": tokens.SETA_VERMELHA,
    "blue": tokens.SETA_AZUL,
    "yellow": tokens.SETA_AMARELA,
}
"""As quatro cores de `[%cal]` resolvidas nos papéis que `ui/tokens.py` já declara para elas.

O nome no PGN é `G`/`R`/`B`/`Y` -- é o que `chess.svg.Arrow.pgn` sabe escrever, e não há escolha
ali. O que existe é a pergunta de **qual verde**, e essa é da paleta: um `#15781b` cravado aqui
seria o único hexadecimal deste pacote, e ele não acompanharia a troca de pele."""


class TabuleiroDeJogo(TabuleiroQt):
    """Um tabuleiro em que se joga. Emite `lance` quando um lance legal é completado."""

    lance = pyqtSignal(object)
    """O `chess.Move` que a pessoa jogou. `object` porque `pyqtSignal` não conhece `chess.Move`."""

    seta = pyqtSignal(int, int, str)
    """`(origem, destino, cor)` em ordem de leitura -- a seta que o botão direito desenhou."""

    recado = pyqtSignal(str)
    """O que o modelo tem a dizer sem mudar nada. Vai para o rodapé."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        escolher_promocao: Callable[[], int | None] | None = None,
        **opcoes: object,
    ) -> None:
        super().__init__(parent, **opcoes)  # type: ignore[arg-type]
        self.modelo = BoardModel(mode="play")
        self._seta_de: int | None = None
        self._seta_para: int | None = None
        self._cor_da_seta = "green"
        self._selecionou_agora = False
        self._ponteiro = QPoint()
        # A promoção é do modelo desde a S-49: `_play_move_to` já pergunta quando há mais de um
        # lance legal entre as duas casas, e `None` ali é "desisti". Perguntar de novo aqui daria
        # duas caixas de coroação para o mesmo peão.
        self.modelo.promotion_chooser = escolher_promocao
        self.setMouseTracking(True)

    # ------------------------------------------------------------------------------- estado

    def mostrar_tabuleiro(self, tabuleiro: chess.Board, *, virado: bool = False, **opcoes: object) -> None:
        """Desenha uma posição de partida **e a carrega no modelo**, para poder ser jogada.

        Recebe o `chess.Board` inteiro, e não o campo de peças: quem joga precisa da vez, do
        roque e do en passant -- é a mesma correção que a S-269 fez na sala, onde o painel recebia
        `current_fen` e o que chegava era só o campo de peças.
        """
        super().mostrar(tabuleiro.board_fen(), virado=virado, **opcoes)  # type: ignore[arg-type]
        self.modelo.board = tabuleiro.copy(stack=False)
        self.modelo.flipped = self._virado
        self.modelo.select(None)
        self.update()

    def definir_setas(self, setas: Iterable[tuple[int, int, str]]) -> None:
        """As setas gravadas no nó. Substituem as anteriores: elas são do lance, não da sessão."""
        self.modelo.set_arrows(setas)
        self.update()

    def selecionada(self) -> int | None:
        return self.modelo.selected

    # ---------------------------------------------------------------------------- interação

    def _casa_em(self, ponto: QPoint) -> int | None:
        alvo = self.geometria().display_at(ponto.x(), ponto.y())
        return None if alvo is None else self.modelo.index_from_display(*alvo)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None:
            return
        casa = self._casa_em(a0.pos())
        if a0.button() == Qt.MouseButton.RightButton:
            modificadores = a0.modifiers()
            self._seta_de = casa
            self._seta_para = casa
            self._cor_da_seta = cor_de_seta_por_modificador(
                shift=bool(modificadores & Qt.KeyboardModifier.ShiftModifier),
                alt=bool(modificadores & Qt.KeyboardModifier.AltModifier),
                ctrl=bool(modificadores & Qt.KeyboardModifier.ControlModifier),
            )
            self.update()
            return
        if a0.button() != Qt.MouseButton.LeftButton or casa is None:
            return
        # **`press` seleciona; quem completa o lance é `drop`, no botão que sobe.** É a mesma
        # ordem do outro frontend, e ela é o que faz clique-clique e arrastar-soltar serem o
        # mesmo caminho: entre os dois só muda onde o ponteiro está quando o botão sobe.
        anterior = self.modelo.selected
        self._selecionou_agora = anterior != casa
        mudanca = self.modelo.press(casa)
        if mudanca.message:
            self.recado.emit(mudanca.message)
        self.update()

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None:
            return
        self._ponteiro = a0.pos()
        if self._seta_de is None:
            return
        alvo = self._casa_em(a0.pos())
        if alvo is not None and alvo != self._seta_para:
            self._seta_para = alvo
            self.update()

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.RightButton:
            self._soltar_seta(self._casa_em(a0.pos()))
            return
        if a0.button() != Qt.MouseButton.LeftButton:
            return
        # `allow_deselect` só quando a peça **já estava** selecionada antes deste clique: sem
        # isso, clicar numa peça e soltar no mesmo lugar a selecionaria e a largaria no mesmo
        # gesto, e o tabuleiro nunca ficaria com nada escolhido.
        mudanca = self.modelo.drop(self._casa_em(a0.pos()), allow_deselect=not self._selecionou_agora)
        self._selecionou_agora = False
        if mudanca.message:
            self.recado.emit(mudanca.message)
        self.update()
        if mudanca.move is not None:
            self.lance.emit(mudanca.move)

    def _soltar_seta(self, destino: int | None) -> None:
        """Solta o botão direito: uma seta, ou nada.

        **Origem igual a destino não é seta**, e é de propósito: um clique direito sem arrastar é
        o gesto de marcar uma *casa*, que o `[%csl]` guarda -- e a sala ainda não o oferece.
        Emitir uma seta de comprimento zero criaria um `[%cal]` que nenhum leitor sabe desenhar.
        """
        origem, self._seta_de = self._seta_de, None
        self._seta_para = None
        self.update()
        if origem is None or destino is None or destino == origem:
            return
        self.seta.emit(origem, destino, self._cor_da_seta)

    # ------------------------------------------------------------------------------ desenho

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """A base desenha o tabuleiro; aqui vão os três sinais que **jogar** acrescenta.

        A ordem é a leitura: a casa escolhida embaixo, os alvos por cima dela, e as setas por
        último -- elas são anotação humana, e ficam acima de tudo o que o programa deduziu.
        """
        super().paintEvent(a0)
        geo = self.geometria()
        if geo.cell <= 0:
            return
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._desenhar_selecao(pintor, geo)
        self._desenhar_alvos(pintor, geo)
        self._desenhar_setas(pintor, geo)
        pintor.end()

    def _retangulo(self, geo: BoardGeometry, indice: int) -> QRectF:
        linha, coluna = self.modelo.display_from_index(indice)
        x0, y0, x1, y1 = geo.rect(linha, coluna)
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def _centro(self, geo: BoardGeometry, indice: int) -> QPointF:
        return self._retangulo(geo, indice).center()

    def _desenhar_selecao(self, pintor: QPainter, geo: BoardGeometry) -> None:
        if self.modelo.selected is None:
            return
        caneta = QPen(QColor(tema.cor_atual(tokens.CONTORNO_DE_SELECAO)))
        caneta.setWidth(3)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawRect(self._retangulo(geo, self.modelo.selected).adjusted(1.5, 1.5, -1.5, -1.5))

    def _desenhar_alvos(self, pintor: QPainter, geo: BoardGeometry) -> None:
        """Um ponto em cada casa para onde a peça escolhida pode ir.

        Quem sabe quais são é `BoardModel.legal_targets`, que é puro e só responde em
        `mode="play"` -- então este método não tem como marcar alvo num tabuleiro de correção.
        """
        alvos = self.modelo.legal_targets()
        if not alvos:
            return
        raio = geo.cell * LADO_DO_ALVO / 2
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(tema.cor_atual(tokens.CONTORNO_DE_SELECAO)))
        for indice in alvos:
            pintor.drawEllipse(self._centro(geo, indice), raio, raio)

    def _desenhar_setas(self, pintor: QPainter, geo: BoardGeometry) -> None:
        """As setas gravadas no nó, mais a que está sendo arrastada agora."""
        setas = list(self.modelo.arrows)
        if self._seta_de is not None and self._seta_para is not None and self._seta_de != self._seta_para:
            setas.append((self._seta_de, self._seta_para, self._cor_da_seta))
        for origem, destino, cor in setas:
            self._desenhar_uma_seta(pintor, geo, origem, destino, cor)

    def _desenhar_uma_seta(
        self, pintor: QPainter, geo: BoardGeometry, origem: int, destino: int, cor: str
    ) -> None:
        papel = COR_DA_SETA.get(cor, tokens.SETA_VERDE)
        tinta = QColor(tema.cor_atual(papel))
        de, para = self._centro(geo, origem), self._centro(geo, destino)
        vetor = QPointF(para.x() - de.x(), para.y() - de.y())
        comprimento = (vetor.x() ** 2 + vetor.y() ** 2) ** 0.5
        if comprimento <= 0:  # pragma: no cover - `_soltar_seta` já recusa a seta de tamanho zero
            return
        unidade = QPointF(vetor.x() / comprimento, vetor.y() / comprimento)
        ponta = geo.cell * 0.34
        # A haste para **antes** da ponta, senão a linha aparece através dela quando a cor é
        # translúcida -- e as quatro do `[%cal]` são.
        fim = QPointF(para.x() - unidade.x() * ponta, para.y() - unidade.y() * ponta)

        caneta = QPen(tinta)
        caneta.setWidthF(max(2.0, geo.cell * 0.14))
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        pintor.setPen(caneta)
        pintor.drawLine(de, fim)

        lado = QPointF(-unidade.y(), unidade.x())
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(tinta)
        pintor.drawPolygon(
            QPolygonF(
                [
                    para,
                    QPointF(fim.x() + lado.x() * ponta * 0.55, fim.y() + lado.y() * ponta * 0.55),
                    QPointF(fim.x() - lado.x() * ponta * 0.55, fim.y() - lado.y() * ponta * 0.55),
                ]
            )
        )
