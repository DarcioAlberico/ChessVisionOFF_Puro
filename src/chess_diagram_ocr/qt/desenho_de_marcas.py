"""Como uma marca de diagrama aparece: no tabuleiro, no ícone da paleta e sobre o recorte.

**Tinta de livro, com as cores que o tabuleiro já usa nos glifos**: bolinha branca é miolo claro com
contorno escuro, e a preta é cheia, como na página. O traço leva um halo claro, porque o tabuleiro
da conferência é colorido e a hachura do livro não está nele.

**`cor_unica` desenha só o contorno.** É o modo de pintar por cima do recorte: uma estrela cheia sobre
a estrela impressa esconderia justamente o que se quer conferir, que é se as duas estão no mesmo lugar.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import tokens

__all__ = ["pintar_anel", "pintar_marca", "pintar_marcas", "pintar_traco"]

RAIO_DA_BOLINHA = 0.2
RAIO_DA_ESTRELA = 0.36
MIOLO_DA_ESTRELA = 0.42
"""Razão entre o raio interno e o externo da estrela de cinco pontas."""

BRACO_DO_SIMBOLO = 0.28
LARGURA_DO_CONTORNO = 0.05
LARGURA_DO_TRACO = 0.05
LARGURA_DO_HALO = 2.4
"""Quantas vezes o halo é mais largo que o traço."""

COMPRIMENTO_DA_PONTA = 0.3
LARGURA_DA_PONTA = 0.15
"""A ponta da seta, em fração da casa. `LARGURA_DA_PONTA` é a metade da base."""


def _tintas(cor_unica: str | None) -> tuple[QColor, QColor]:
    """A tinta escura e a clara. Com `cor_unica`, as duas são ela."""
    if cor_unica is not None:
        return QColor(cor_unica), QColor(cor_unica)
    return QColor(tema.cor_atual(tokens.GLIFO_ESCURO)), QColor(tema.cor_atual(tokens.GLIFO_CLARO))


def _estrela(centro: QPointF, raio: float) -> QPolygonF:
    pontos = []
    for passo in range(10):
        angulo = -math.pi / 2 + passo * math.pi / 5
        alcance = raio if passo % 2 == 0 else raio * MIOLO_DA_ESTRELA
        pontos.append(QPointF(centro.x() + alcance * math.cos(angulo), centro.y() + alcance * math.sin(angulo)))
    return QPolygonF(pontos)


def pintar_anel(pintor: QPainter, casa: QRectF, cor: str, *, espessura: float, tracejado: bool = False) -> None:
    """O contorno da casa **por dentro dela**: caneta de `espessura` (2 px no mínimo), recuada meia largura.

    É o anel de seleção, de apontada e de hesitação do recorte e do tabuleiro editável (S-864): o
    recuo é o que deixa dois anéis vizinhos lado a lado em vez de um sobre o outro. Quem chama diz a
    espessura, porque cada tabuleiro tem a sua fração da casa.
    """
    caneta = QPen(QColor(cor))
    caneta.setWidthF(max(2.0, espessura))
    if tracejado:
        caneta.setStyle(Qt.PenStyle.DashLine)
    pintor.setPen(caneta)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    folga = caneta.widthF() / 2.0
    pintor.drawRect(casa.adjusted(folga, folga, -folga, -folga))


def pintar_marca(pintor: QPainter, tipo: str, casa: QRectF, *, cor_unica: str | None = None) -> None:
    """A marca de casa, centrada no retângulo `casa`."""
    escura, clara = _tintas(cor_unica)
    lado = min(casa.width(), casa.height())
    centro = casa.center()
    caneta = QPen(escura)
    caneta.setWidthF(max(1.5, lado * LARGURA_DO_CONTORNO))
    caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    pintor.save()
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setPen(caneta)
    if cor_unica is not None:
        pintor.setBrush(Qt.BrushStyle.NoBrush)
    elif tipo in (mc.BOLINHA_BRANCA, mc.ESTRELA_BRANCA):
        pintor.setBrush(clara)
    else:
        pintor.setBrush(escura)

    if tipo in (mc.BOLINHA_BRANCA, mc.BOLINHA_PRETA):
        raio = lado * RAIO_DA_BOLINHA
        pintor.drawEllipse(centro, raio, raio)
    elif tipo in (mc.ESTRELA_BRANCA, mc.ESTRELA_PRETA):
        pintor.drawPolygon(_estrela(centro, lado * RAIO_DA_ESTRELA))
    elif tipo in (mc.X, mc.CRUZ):
        caneta.setWidthF(max(2.0, lado * LARGURA_DO_CONTORNO * 2))
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        pintor.setPen(caneta)
        braco = lado * BRACO_DO_SIMBOLO
        if tipo == mc.X:
            pintor.drawLine(centro + QPointF(-braco, -braco), centro + QPointF(braco, braco))
            pintor.drawLine(centro + QPointF(-braco, braco), centro + QPointF(braco, -braco))
        else:
            pintor.drawLine(centro + QPointF(-braco, 0), centro + QPointF(braco, 0))
            pintor.drawLine(centro + QPointF(0, -braco), centro + QPointF(0, braco))
    else:
        fonte = QFont(pintor.font())
        fonte.setBold(True)
        fonte.setPixelSize(max(8, round(lado * 0.6)))
        pintor.setFont(fonte)
        pintor.drawText(casa, Qt.AlignmentFlag.AlignCenter, "?")
    pintor.restore()


def _desenhar_linha(pintor: QPainter, traco: mc.Traco, de: QPointF, para: QPointF, casa: float) -> None:
    """A geometria do traço, com a caneta e o pincel que estiverem no pintor."""
    if traco.tipo == mc.MOLDURA:
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawRect(QRectF(de, para).normalized())
        return
    if traco.tipo == mc.RETA:
        pintor.drawLine(de, para)
        return
    comprimento = math.hypot(para.x() - de.x(), para.y() - de.y())
    if comprimento == 0:
        return
    ux, uy = (para.x() - de.x()) / comprimento, (para.y() - de.y()) / comprimento
    ponta = min(casa * COMPRIMENTO_DA_PONTA, comprimento)
    base = QPointF(para.x() - ux * ponta, para.y() - uy * ponta)
    meia = ponta * LARGURA_DA_PONTA / COMPRIMENTO_DA_PONTA
    pintor.drawLine(de, base)
    pintor.drawPolygon(
        QPolygonF([para, QPointF(base.x() - uy * meia, base.y() + ux * meia), QPointF(base.x() + uy * meia, base.y() - ux * meia)])
    )


def pintar_traco(
    pintor: QPainter,
    traco: mc.Traco,
    origem_x: float,
    origem_y: float,
    casa: float,
    *,
    virado: bool = False,
    cor_unica: str | None = None,
    tracejado: bool = False,
) -> None:
    """O traço, com `(0, 0)` do tabuleiro em `(origem_x, origem_y)` e `casa` pixels por casa."""

    def ponto(valor: tuple[float, float]) -> QPointF:
        x, y = (8 - valor[0], 8 - valor[1]) if virado else valor
        return QPointF(origem_x + x * casa, origem_y + y * casa)

    escura, clara = _tintas(cor_unica)
    de, para = ponto(traco.de), ponto(traco.para)
    largura = max(1.5, casa * LARGURA_DO_TRACO)

    pintor.save()
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    if cor_unica is None:
        halo = QPen(clara)
        halo.setWidthF(largura * LARGURA_DO_HALO)
        halo.setCapStyle(Qt.PenCapStyle.RoundCap)
        pintor.setPen(halo)
        pintor.setBrush(clara)
        _desenhar_linha(pintor, traco, de, para, casa)
    caneta = QPen(escura)
    caneta.setWidthF(largura)
    caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
    if tracejado:
        caneta.setStyle(Qt.PenStyle.DashLine)
    pintor.setPen(caneta)
    pintor.setBrush(escura)
    _desenhar_linha(pintor, traco, de, para, casa)
    pintor.restore()


def pintar_marcas(
    pintor: QPainter,
    marcas: mc.MarcasDoDiagrama,
    origem_x: float,
    origem_y: float,
    casa: float,
    *,
    virado: bool = False,
    cor_unica: str | None = None,
) -> None:
    """Todas as marcas do diagrama: primeiro os traços, para a marca de casa ficar por cima."""
    for traco in marcas.tracos:
        pintar_traco(pintor, traco, origem_x, origem_y, casa, virado=virado, cor_unica=cor_unica)
    for nome, tipo in marcas.casas.items():
        indice = mc.indice_da_casa(nome)
        fila, coluna = indice // 8, indice % 8
        if virado:
            fila, coluna = 7 - fila, 7 - coluna
        retangulo = QRectF(origem_x + coluna * casa, origem_y + fila * casa, casa, casa)
        pintar_marca(pintor, tipo, retangulo, cor_unica=cor_unica)
