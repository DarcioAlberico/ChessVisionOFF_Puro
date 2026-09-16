"""O recorte do diagrama, ampliado ao lado do tabuleiro editável (OCR_UI passo 13, U1).

**O que ele desenha.** O tabuleiro retificado que o classificador leu
(`RecognizedDiagram.board_rgb`), com um fio neutro de 1 px em volta (passo 16), a casa sob o
ponteiro e a casa selecionada espelhadas do tabuleiro ao lado, e as casas em que o modelo hesitou
contornadas na rampa de calor -- **contorno, e não tinta**: no recorte o que se quer ver é o pixel
impresso, e uma tinta por cima esconderia justamente o que a pessoa veio conferir.

**O que ele decide: nada.** Casa ↔ pixel, as três leituras da dica e o âmbar por margem são de
`ui/recorte_do_diagrama.py`, sem toolkit (R3.2). Aqui ficam os eventos e o `QPainter`.

**A sincronia é de mão dupla e mora no painel de Resultado**, não aqui: este widget emite
`casa_apontada` e `casa_clicada` e recebe `apontar` e `selecionar`. É o `PainelDeResultado` que
liga um ao outro -- e é o fio que o portão `percurso --sabotar sem_sincronia` corta, para provar
que sem ele a correção custa um clique a mais.

**Teclado.** O recorte é focável e nomeado (o portão `teclado` cobra os dois): as setas movem
a casa apontada, `Espaço`/`Enter` clicam nela -- o mesmo gesto do ponteiro, para quem não usa
mouse chegar à casa que o olho achou no recorte.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from PyQt6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QToolTip, QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.imagens import pixmap_de_rgb
from chess_diagram_ocr.ui import recorte_do_diagrama as regra
from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.desenho_do_tabuleiro import heatmap_color

__all__ = ["LADO_MINIMO", "LADO_PREFERIDO", "MENSAGEM_SEM_RECORTE", "PainelDeRecorte"]

LADO_MINIMO = 160
"""O piso do recorte, em pixel: 20 px por casa. Abaixo disso a casa deixa de ser conferível, e o
recorte passa a ser miniatura -- que a página já é."""

LADO_PREFERIDO = 240
"""O que o recorte **pede** ao divisor: o mesmo piso do tabuleiro (`qt/tabuleiro.LADO_MINIMO`).

É a conta que faz os dois quadrados saírem iguais: o grupo do tabuleiro pede `240 + paleta +
margens`, o recorte pede `240`, e com esticamento 1:1 a folga do divisor se reparte ao meio --
cada lado ganha a mesma folga sobre o mesmo piso, e o tabuleiro e o recorte terminam do mesmo
tamanho em qualquer largura. Com o pedido em 160 (o mínimo), o recorte saía com 175 px ao lado de
um tabuleiro de 436 a 1920 -- uma miniatura, que é o que ele existe para não ser."""

MARGEM = 4
"""Folga em volta da imagem, para os contornos das casas da borda não serem cortados."""

MENSAGEM_SEM_RECORTE = "Sem diagrama aberto: o recorte da página aparece aqui."
"""O estado vazio, desenhado (passo 13, tarefa 5). Uma frase e não um retângulo mudo: o crítico do
ciclo 1 mediu o que uma área vazia sem orientação faz numa tela (S-170)."""

LARGURA_DO_CONTORNO = 0.08
"""Anel de seleção e de hesitação, em fração da casa -- um pouco mais que o do tabuleiro (0,06),
porque aqui o fundo é impresso e irregular."""


class PainelDeRecorte(QWidget):
    """O recorte com a grade das 64 casas por cima, espelhando o tabuleiro ao lado."""

    casa_clicada = pyqtSignal(int)
    """A casa do recorte que recebeu um clique (ou `Espaço`/`Enter`), em ordem de leitura."""

    casa_apontada = pyqtSignal(object)
    """A casa sob o ponteiro, ou `None` quando ele saiu do recorte. `object` pelo `None`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mapa: QPixmap | None = None
        self._virado = False
        self._tinta: regra.Tinta | None = None
        self._apontada: int | None = None
        self._selecionada: int | None = None
        self._leituras: Any = None
        """A matriz (64, 13), para a dica. `None` sem leitura -- a dica vira só o nome da casa."""
        self.setMinimumSize(LADO_MINIMO, LADO_MINIMO)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Recorte do diagrama")
        tema.ao_repintar(self.update)

    # ------------------------------------------------------------------------------ estado

    def mostrar(
        self,
        rgb: np.ndarray | None,
        *,
        virado: bool = False,
        tinta: regra.Tinta | None = None,
        leituras: Any = None,
    ) -> None:
        """O recorte de agora, ou `None` para o estado vazio. A tinta é a do tabuleiro ao lado."""
        self._mapa = pixmap_de_rgb(rgb) if rgb is not None and rgb.size else None
        self._virado = bool(virado)
        self._tinta = tinta
        self._leituras = leituras
        self._apontada = None
        self._selecionada = None
        self.update()

    def limpar(self) -> None:
        self.mostrar(None)

    def tem_recorte(self) -> bool:
        return self._mapa is not None

    def apontar(self, casa: object) -> None:
        """A casa que o **outro** lado está apontando. `None` apaga."""
        nova = casa if isinstance(casa, int) and 0 <= casa < 64 else None
        if nova != self._apontada:
            self._apontada = nova
            self.update()

    def selecionar(self, casa: object) -> None:
        nova = casa if isinstance(casa, int) and 0 <= casa < 64 else None
        if nova != self._selecionada:
            self._selecionada = nova
            self.update()

    def apontada(self) -> int | None:
        return self._apontada

    def selecionada(self) -> int | None:
        return self._selecionada

    # ---------------------------------------------------------------------------- geometria

    def sizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        return QSize(LADO_PREFERIDO, LADO_PREFERIDO)

    def area_da_imagem(self) -> QRect:
        """Onde o recorte está dentro do widget: quadrado, centrado, com a margem em volta."""
        lado = max(1, min(self.width(), self.height()) - 2 * MARGEM)
        x = (self.width() - lado) // 2
        y = (self.height() - lado) // 2
        return QRect(x, y, lado, lado)

    def casa_em(self, ponto: QPoint) -> int | None:
        """A casa sob um ponto do widget, ou `None` fora do recorte (ou sem recorte)."""
        if self._mapa is None:
            return None
        area = self.area_da_imagem()
        return regra.casa_em(
            ponto.x() - area.x(), ponto.y() - area.y(), area.width(), area.height(), virado=self._virado
        )

    def retangulo_da_casa(self, casa: int) -> QRectF:
        area = self.area_da_imagem()
        x0, y0, x1, y1 = regra.retangulo_da_casa(casa, area.width(), area.height(), virado=self._virado)
        return QRectF(area.x() + x0, area.y() + y0, x1 - x0, y1 - y0)

    def dica_da_casa(self, casa: int) -> str:
        """O texto da dica sobre uma casa: nome, as três leituras e a margem (`ui/recorte_do_diagrama`)."""
        leituras = regra.alternativas(self._leituras, casa)
        folga = regra.margem(self._leituras, casa) if leituras else None
        return regra.dica_da_casa(casa, leituras, folga)

    # ------------------------------------------------------------------------------ eventos

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None:
            return
        self._apontar_daqui(self.casa_em(a0.position().toPoint()))

    def leaveEvent(self, a0: QEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().leaveEvent(a0)
        self._apontar_daqui(None)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None or a0.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        casa = self.casa_em(a0.position().toPoint())
        if casa is not None:
            self.casa_clicada.emit(casa)

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """Setas andam pela grade; `Espaço`/`Enter` clicam. O resto sobe para o pai."""
        if a0 is None or self._mapa is None:
            super().keyPressEvent(a0)
            return
        passo = {
            Qt.Key.Key_Left: -1,
            Qt.Key.Key_Right: 1,
            Qt.Key.Key_Up: -8,
            Qt.Key.Key_Down: 8,
        }.get(a0.key())
        if passo is not None:
            atual = self._apontada if self._apontada is not None else (self._selecionada or 0)
            if passo in (-1, 1) and (atual % 8) + passo not in range(8):
                return
            nova = atual + passo
            if 0 <= nova < 64:
                self._apontar_daqui(nova)
            return
        if a0.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._apontada is not None:
                self.casa_clicada.emit(self._apontada)
            return
        super().keyPressEvent(a0)

    def event(self, a0: QEvent | None) -> bool:
        """A dica é por casa, e não por widget: o Qt pergunta `ToolTip` com a posição, e a resposta
        é a leitura da casa que está ali -- as três classes e a margem."""
        if a0 is not None and a0.type() == QEvent.Type.ToolTip and self._mapa is not None:
            ponto = getattr(a0, "pos", lambda: QPoint())()
            casa = self.casa_em(ponto)
            if casa is not None:
                QToolTip.showText(getattr(a0, "globalPos", lambda: QPoint())(), self.dica_da_casa(casa), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(a0)

    def _apontar_daqui(self, casa: int | None) -> None:
        if casa == self._apontada:
            return
        self._apontada = casa
        self.update()
        self.casa_apontada.emit(casa)

    # ------------------------------------------------------------------------------ desenho

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pintor.fillRect(self.rect(), QColor(tema.cor_atual(tokens.SUPERFICIE_PADRAO)))
        area = self.area_da_imagem()
        if self._mapa is None:
            self._desenhar_vazio(pintor, area)
            pintor.end()
            return
        pintor.drawPixmap(area, self._mapa)
        self._desenhar_hesitacao(pintor)
        if self._selecionada is not None:
            self._anel(pintor, self._selecionada, tema.cor_atual(tokens.CONTORNO_DE_SELECAO))
        if self._apontada is not None and self._apontada != self._selecionada:
            self._anel(pintor, self._apontada, tema.cor_atual(tokens.CONTORNO_DE_SELECAO), tracejado=True)
        # O fio neutro **sobre** o pixel mais externo (passo 16): a folha impressa é branca e sem
        # ele acaba onde o olho adivinha.
        caneta = QPen(QColor(tema.cor_atual(tokens.CONTORNO_DE_CROMO)))
        caneta.setWidth(1)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawRect(area.adjusted(0, 0, -1, -1))
        pintor.end()

    def _desenhar_vazio(self, pintor: QPainter, area: QRect) -> None:
        """O vazio desenhado: a moldura tracejada onde o recorte vai estar, e a frase."""
        caneta = QPen(QColor(tema.cor_atual(tokens.CONTORNO_DE_CROMO)))
        caneta.setWidth(1)
        caneta.setStyle(Qt.PenStyle.DashLine)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawRect(area.adjusted(0, 0, -1, -1))
        pintor.setPen(QColor(tema.cor_atual(tokens.TEXTO_SECUNDARIO)))
        pintor.drawText(
            area.adjusted(MARGEM * 2, MARGEM * 2, -MARGEM * 2, -MARGEM * 2),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            MENSAGEM_SEM_RECORTE,
        )

    def _desenhar_hesitacao(self, pintor: QPainter) -> None:
        """As casas em que o modelo hesitou, contornadas na rampa de calor -- a mesma do tabuleiro."""
        if self._tinta is None:
            return
        for casa in self._tinta.casas:
            valor = self._tinta.valores[casa] if len(self._tinta.valores) == 64 else self._tinta.limiar
            self._anel(pintor, casa, heatmap_color(valor, self._tinta.limiar))

    def _anel(self, pintor: QPainter, casa: int, cor: str, *, tracejado: bool = False) -> None:
        retangulo = self.retangulo_da_casa(casa)
        caneta = QPen(QColor(cor))
        caneta.setWidthF(max(2.0, retangulo.width() * LARGURA_DO_CONTORNO))
        if tracejado:
            caneta.setStyle(Qt.PenStyle.DashLine)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        folga = caneta.widthF() / 2.0
        pintor.drawRect(retangulo.adjusted(folga, folga, -folga, -folga))

    def casas_marcadas(self) -> dict[str, Sequence[int]]:
        """O que está aceso agora, por papel. Existe para o teste afirmar o que a tela diz."""
        return {
            "selecionada": () if self._selecionada is None else (self._selecionada,),
            "apontada": () if self._apontada is None else (self._apontada,),
            "hesitacao": () if self._tinta is None else tuple(self._tinta.casas),
        }
