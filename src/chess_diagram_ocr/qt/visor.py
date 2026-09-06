"""A página do livro com os diagramas marcados por cima, em Qt.

**Quase nada aqui é decisão nova.** Onde estão as caixas, o que cada estado significa, como
o traço e o glifo distinguem os quatro estados sem depender de cor, qual caixa um clique
acertou quando duas se sobrepõem, o que a roda faz na borda da página, para onde o zoom puxa
e o que "caber na página" quer dizer -- tudo isso é `ui/page_overlay.py` e `ui/viewport.py`,
importados como estão. Nenhum dos dois importa `tkinter`, e é essa a razão de este arquivo
ter o tamanho que tem.

**O que é novo é a ponte.** O Tk fala em fração (`yview` devolve `(primeiro, último)`) e o Qt
fala em pixel (`QScrollBar` tem `value`, `pageStep` e `maximum`). `fracoes_da_vista` é a
tradução, e ela é função pura justamente para que a regra da virada de página continue sendo
afirmada por teste em vez de por clique.
"""

from __future__ import annotations

import time

import numpy as np
from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QScrollArea, QScrollBar, QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.imagens import pixmap_de_rgb
from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.leitura_do_pdf import CLICK_SLOP_PX, MIN_SELECTION_PX, SELECTION_HALO_PX
from chess_diagram_ocr.ui.page_overlay import (
    A_FAZER,
    DISPENSADO,
    LIDO,
    PRONTO,
    DiagramBox,
    PageBoxes,
    estado_da_caixa,
    traco_da_caixa,
)
from chess_diagram_ocr.ui.viewport import (
    WheelAction,
    anchor_after_zoom,
    clamp_zoom,
    decide_wheel,
    fit_page_zoom,
    fit_width_zoom,
    wheel_direction,
    zoomed,
)

PAPEL_DO_ESTADO: dict[str, str] = {
    A_FAZER: tokens.A_FAZER,
    LIDO: tokens.LIDO,
    PRONTO: tokens.PRONTO,
    DISPENSADO: tokens.DISPENSADO,
}
"""Estado da caixa -> papel de cor. O estado e o papel têm o **mesmo nome** em `page_overlay` e em
`tokens`, então isto é a resolução do papel, e não uma segunda escolha de matiz.

**A tinta sai de `tema.cor_atual`, e no momento de pintar.** Saía de `tokens.RESERVA[...]` -- o
hexadecimal de fábrica, que não acompanha a troca de pele -- e era o mesmo achado da S-510 sobre
o glifo de reserva do tabuleiro, numa terceira tela. `RESERVA` é a paleta sem pele; quem responde
é a pele em uso, e ela pode ter mudado desde a montagem. É a triagem da S-511."""


def cor_do_estado(estado: str) -> str:
    """A cor da caixa naquele estado, contra a pele em uso."""
    return tema.cor_atual(PAPEL_DO_ESTADO[estado])


# A folga da segunda borda é `leitura_do_pdf.SELECTION_HALO_PX`: o número já existia, com o
# motivo escrito, e este widget o reescrevia como `HALO_DA_SELECAO = 4` (S-511).

ALTURA_DA_ETIQUETA = 18
LARGURA_DA_ETIQUETA = 22
"""O retângulo cheio do número, acima e à esquerda da caixa. Cheio porque texto solto some no
xadrez do tabuleiro justamente onde ele mais precisa ser lido."""

FRACAO_DE_ROLAGEM = 0.3
"""Quanto da altura visível um giro da roda rola.

É o que o canvas do Tk faz com `yview_scroll(3, "units")` sem `yscrollincrement` declarado --
cada unidade vale um décimo da janela. O número aparece aqui porque no Qt o passo é em pixel,
e herdá-lo do `singleStep` do `QScrollBar` daria um giro quatro vezes menor que o do produto."""

MARGEM_DE_AJUSTE = 4
"""Desconto de barra de rolagem nos dois "ajustar". Sem ele, o ajuste à largura acende a barra
horizontal que ele existe para apagar."""


def fracoes_da_vista(valor: int, passo: int, maximo: int) -> tuple[float, float]:
    """O `(primeiro, último)` do `yview` do Tk, a partir de um `QScrollBar` do Qt.

    O conteúdo inteiro mede `maximo + passo`: o `maximum` de uma barra do Qt é a posição do
    **topo** da última vista, e não o fim do conteúdo. Esquecer o `+ passo` faz a última página
    parecer ter chegado ao fim uma tela antes -- e a roda viraria a página cedo demais.

    Conteúdo que cabe inteiro na vista devolve `(0.0, 1.0)`: está no começo **e** no fim, que é
    o que o Tk devolve e o que faz a roda virar a página numa folha pequena.
    """
    conteudo = int(maximo) + int(passo)
    if conteudo <= 0 or passo <= 0:
        return (0.0, 1.0)
    return (valor / conteudo, min(1.0, (valor + passo) / conteudo))


class _Folha(QWidget):
    """A folha desenhada: a página no zoom atual, e os retângulos por cima.

    Widget separado porque é ele que vai **dentro** do `QScrollArea`: o tamanho dele é o
    tamanho do conteúdo rolável, e é o que faz o Qt saber quando mostrar as barras.
    """

    def __init__(self, visor: VisorDePagina) -> None:
        super().__init__(visor)
        self._visor = visor
        self.setMouseTracking(True)

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        pintor = QPainter(self)
        pintor.fillRect(self.rect(), QColor(tokens.RESERVA[tokens.VAZIO_DE_CANVAS]))
        pagina = self._visor.pagina_escalada()
        if pagina is not None:
            pintor.drawPixmap(0, 0, pagina)
            self._desenhar_caixas(pintor)
            self._desenhar_selecao(pintor)
        pintor.end()

    def _desenhar_selecao(self, pintor: QPainter) -> None:
        """O retângulo tracejado do arrasto, por cima de tudo.

        Tracejado e no papel `TRACEJADO`, como o do produto: ele é um gesto em curso e não um
        estado da página, e um traço cheio o faria disputar leitura com as caixas de diagrama --
        que são exatamente o que ele costuma cruzar.
        """
        retangulo = self._visor.retangulo_da_selecao()
        if retangulo is None:
            return
        caneta = QPen(QColor(tokens.RESERVA[tokens.TRACEJADO]))
        caneta.setWidth(2)
        caneta.setDashPattern([3.0, 2.0])
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawRect(retangulo)

    def _desenhar_caixas(self, pintor: QPainter) -> None:
        caixas = self._visor.caixas
        if caixas is None or not self._visor.mostrar_caixas:
            return
        zoom = self._visor.zoom
        fonte = QFont(pintor.font())
        fonte.setBold(True)
        for caixa in caixas.boxes:
            self._desenhar_uma(pintor, caixa, caixas.rect_of(caixa, zoom), fonte)

    def _desenhar_uma(
        self, pintor: QPainter, caixa: DiagramBox, retangulo: tuple[float, float, float, float], fonte: QFont
    ) -> None:
        x0, y0, x1, y1 = (int(round(valor)) for valor in retangulo)
        cor = QColor(cor_do_estado(estado_da_caixa(caixa)))
        traco = traco_da_caixa(caixa)

        caneta = QPen(cor)
        caneta.setWidth(traco.espessura)
        if traco.tracejado:
            # O padrão do Qt é medido em **larguras de caneta**, e o do Tk em pixels: sem a
            # divisão, o tracejado de uma caixa grossa sairia com o dobro do vão do produto.
            caneta.setDashPattern([valor / traco.espessura for valor in traco.tracejado])
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawRect(QRect(x0, y0, x1 - x0, y1 - y0))

        if caixa.index == self._visor.selecionada:
            halo = QPen(cor)
            halo.setWidth(2)
            pintor.setPen(halo)
            pintor.drawRect(
                QRect(
                    x0 - SELECTION_HALO_PX,
                    y0 - SELECTION_HALO_PX,
                    (x1 - x0) + 2 * SELECTION_HALO_PX,
                    (y1 - y0) + 2 * SELECTION_HALO_PX,
                )
            )

        etiqueta = f"{caixa.label}{traco.glifo}"
        largura = LARGURA_DA_ETIQUETA + (10 if traco.glifo else 0)
        moldura = QRect(x0, y0 - ALTURA_DA_ETIQUETA, largura, ALTURA_DA_ETIQUETA)
        pintor.fillRect(moldura, cor)
        pintor.setPen(QPen(QColor(tokens.RESERVA[tokens.TEXTO_SOBRE_MARCACAO])))
        pintor.setFont(fonte)
        pintor.drawText(moldura, int(Qt.AlignmentFlag.AlignCenter), etiqueta)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """Aperta: começa a seleção de área, ou marca o ponto e espera para saber o que é.

        **O botão esquerdo fora do modo de seleção não decide nada aqui.** Ele marca o ponto e
        deixa `mouseMoveEvent` decidir: quem não andar continua sendo um clique, e o clique
        continua abrindo o diagrama de baixo (S-68). Sem essa espera, arrastar a página abriria
        um diagrama a cada empurrão.
        """
        if a0 is None:
            return
        ponto = a0.position()
        if a0.button() == Qt.MouseButton.RightButton:
            self._visor.dispensar_em(ponto.x(), ponto.y())
            return
        if a0.button() != Qt.MouseButton.LeftButton:
            return
        self._visor.apertou_em(ponto.x(), ponto.y())

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is not None:
            ponto = a0.position()
            self._visor.arrastou_para(ponto.x(), ponto.y())

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None or a0.button() != Qt.MouseButton.LeftButton:
            return
        ponto = a0.position()
        self._visor.soltou_em(ponto.x(), ponto.y())

    def mouseDoubleClickEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """Duplo clique numa caixa: aquele diagrama vai para a sala de estudo.

        **O primeiro clique do par já aconteceu, e fez o que sempre faz** -- selecionou o
        diagrama, ou mandou ler a página. O Qt entrega o segundo aperto como este evento, e não
        como `mousePressEvent`, então a soltura que vem depois não acha ponto marcado e não conta
        um terceiro clique. O que este evento acrescenta é só o destino.
        """
        if a0 is None or a0.button() != Qt.MouseButton.LeftButton:
            return
        ponto = a0.position()
        self._visor.estudar_em(ponto.x(), ponto.y())

    def wheelEvent(self, a0: QWheelEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """A roda é do visor, e não da folha.

        A folha é o widget sob o ponteiro, então é ela que recebe o evento primeiro; deixá-lo
        subir sozinho entregaria a rolagem ao `QScrollArea` **antes** de alguém perguntar se
        aquele giro era para virar a página ou para dar zoom.
        """
        if a0 is not None:
            self._visor.girar_roda(a0)


class VisorDePagina(QScrollArea):
    """A página do PDF: mostra, rola, dá zoom, marca os diagramas e diz em qual clicaram."""

    caixa_clicada = pyqtSignal(int)
    """Índice do diagrama em que se clicou, em base 0 -- o mesmo do seletor do produto."""

    pagina_pedida = pyqtSignal(int)
    """`-1` ou `+1`: a roda chegou à borda e pediu a página vizinha."""

    zoom_mudou = pyqtSignal(float)

    caixa_dispensada = pyqtSignal(int)
    """Botão direito sobre um retângulo: **tire este daqui** (S-177).

    Sinal separado de `caixa_clicada` porque as duas respostas ao mesmo retângulo são opostas:
    uma diz "leia isto", a outra diz "isto não é diagrama". Quem guarda a remoção é a janela; o
    visor desenha o que lhe entregam."""

    caixa_para_estudo = pyqtSignal(int)
    """Duplo clique num retângulo: **estude este**. O índice é o mesmo de `caixa_clicada`.

    Sinal separado porque o primeiro clique do par já saiu como `caixa_clicada`: quem o recebeu
    já selecionou o diagrama, ou já mandou ler a página. O que este acrescenta é o destino -- a
    sala de estudo, e não o editor -- e a janela é quem sabe se a página já foi lida."""

    area_selecionada = pyqtSignal(object)
    """`(x0, y0, x1, y1)` em **pixel da página**, já ordenado e sem o zoom.

    Recortar, grampear aos limites e decidir o que fazer quando não há contorno é do `OcrService`
    (S-31). O visor só sabe converter coordenada de folha para coordenada de imagem, que é a única
    parte que depende do zoom."""

    selecao_pequena = pyqtSignal()
    """O arrasto foi menor que `MIN_SELECTION_PX` **na folha** (S-330)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._folha = _Folha(self)
        self.setWidget(self._folha)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._pagina_rgb: np.ndarray | None = None
        self._pagina: QPixmap | None = None
        self._escalada: QPixmap | None = None
        self._zoom_da_escalada = 0.0
        self._zoom = 1.0
        self._dpi = 220
        self._caixas: PageBoxes | None = None
        self._selecionada: int | None = None
        self._mostrar_caixas = True
        self._ultima_virada = 0.0
        self.virar_paginas = True
        """Se a roda vira a página ao chegar à borda. Desligável porque nem todo mundo quer --
        é a mesma preferência do produto."""

        self._selecionando = False
        self._inicio_da_selecao: tuple[float, float] | None = None
        self._ponto_atual: tuple[float, float] | None = None
        self._apertou_em: tuple[float, float] | None = None
        self._arrastando_a_pagina = False
        self._barras_ao_apertar: tuple[int, int] = (0, 0)

    # ------------------------------------------------------------------------------- estado

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def caixas(self) -> PageBoxes | None:
        return self._caixas

    @property
    def selecionada(self) -> int | None:
        return self._selecionada

    @property
    def mostrar_caixas(self) -> bool:
        return self._mostrar_caixas

    def pagina_escalada(self) -> QPixmap | None:
        """A página já no zoom atual. Reescalada só quando o zoom muda, e não a cada quadro.

        Escalar 1.700x2.200 px a cada `paintEvent` é o que faz a rolagem engasgar: o Qt repinta
        a folha inteira a cada pixel de barra, e a conta do reescalonamento é a mesma toda vez.
        """
        if self._pagina is None:
            return None
        if self._escalada is None or self._zoom_da_escalada != self._zoom:
            tamanho = self._pagina.size() * self._zoom
            self._escalada = self._pagina.scaled(
                tamanho,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._zoom_da_escalada = self._zoom
        return self._escalada

    def _area_visivel(self) -> tuple[int, int]:
        """Largura e altura da área visível.

        Existe pelo `Optional` dos stubs do PyQt6: `viewport()` pode ser nulo num
        `QAbstractScrollArea` em desmontagem, e sem esta conversão a checagem apareceria
        espalhada por três lugares. `(0, 0)` cai no ramo "não dá para saber" dos dois ajustes.
        """
        area = self.viewport()
        return (0, 0) if area is None else (area.width(), area.height())

    def _barras(self) -> tuple[QScrollBar, QScrollBar]:
        """As barras horizontal e vertical, sem o `Optional` dos stubs.

        Num `QScrollArea` vivo elas sempre existem -- o `None` da assinatura é o widget já
        desmontado, e ali qualquer resposta seria mentira. Por isso levanta em vez de devolver
        um substituto.
        """
        horizontal, vertical = self.horizontalScrollBar(), self.verticalScrollBar()
        if horizontal is None or vertical is None:  # pragma: no cover - só num widget desmontado
            raise RuntimeError("O QScrollArea está sem barras de rolagem.")
        return horizontal, vertical

    def mostrar_pagina(self, pagina_rgb: np.ndarray, *, dpi: int) -> None:
        """Troca a página exibida. As caixas caem junto: elas eram da página anterior."""
        self._pagina_rgb = pagina_rgb
        self._pagina = pixmap_de_rgb(pagina_rgb)
        self._escalada = None
        self._caixas = None
        self._selecionada = None
        self._dpi = int(dpi)
        self._ajustar_folha()

    def pagina_rgb(self) -> np.ndarray | None:
        """A página como o pipeline a devolveu. É ela que vai ao OCR, e não o `QPixmap`."""
        return self._pagina_rgb

    def definir_caixas(self, caixas: PageBoxes | None) -> None:
        self._caixas = caixas
        self._folha.update()

    def selecionar(self, indice: int | None) -> None:
        if indice == self._selecionada:
            return
        self._selecionada = indice
        self._folha.update()

    def alternar_caixas(self, mostrar: bool) -> None:
        self._mostrar_caixas = bool(mostrar)
        self._folha.update()

    # -------------------------------------------------------------------------------- zoom

    def definir_zoom(self, valor: float) -> None:
        novo = clamp_zoom(valor)
        if novo == self._zoom:
            return
        self._zoom = novo
        self._ajustar_folha()
        self.zoom_mudou.emit(novo)

    def ajustar_a_largura(self) -> None:
        if self._pagina is None:
            return
        largura, _altura = self._area_visivel()
        alvo = fit_width_zoom(viewport_px=largura, page_px=self._pagina.width(), margin_px=MARGEM_DE_AJUSTE)
        if alvo is not None:
            self.definir_zoom(alvo)

    def ajustar_a_pagina(self) -> None:
        if self._pagina is None:
            return
        largura, altura = self._area_visivel()
        alvo = fit_page_zoom(
            viewport_w=largura,
            viewport_h=altura,
            page_w=self._pagina.width(),
            page_h=self._pagina.height(),
            margin_px=MARGEM_DE_AJUSTE,
        )
        if alvo is not None:
            self.definir_zoom(alvo)

    def _ajustar_folha(self) -> None:
        if self._pagina is None:
            self._folha.resize(1, 1)
            return
        self._folha.resize(self._pagina.size() * self._zoom)
        self._folha.update()

    # -------------------------------------------------------------------------------- roda

    def girar_roda(self, evento: QWheelEvent) -> None:
        """O que um giro significa: zoom com Ctrl, senão rolar -- ou virar, na borda."""
        direcao = wheel_direction(evento.angleDelta().y())
        if direcao == 0:
            return
        if evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._zoom_com_ancora(direcao, evento.position().toPoint())
            evento.accept()
            return

        _horizontal, barra = self._barras()
        acao = decide_wheel(
            direction=direcao,
            view=fracoes_da_vista(barra.value(), barra.pageStep(), barra.maximum()),
            flip_pages=self.virar_paginas,
            since_last_flip=time.monotonic() - self._ultima_virada,
        )
        if acao is WheelAction.SCROLL:
            barra.setValue(barra.value() - int(direcao * barra.pageStep() * FRACAO_DE_ROLAGEM))
        else:
            self._ultima_virada = time.monotonic()
            self.pagina_pedida.emit(-1 if acao is WheelAction.PREV_PAGE else 1)
        evento.accept()

    def _zoom_com_ancora(self, direcao: int, ponteiro: QPoint) -> None:
        """Aumenta o zoom deixando parado o ponto que está sob o ponteiro.

        Sem isto, dar zoom num diagrama do pé da página o joga para fora da vista, e a pessoa
        passa a caçar com a barra de rolagem justamente o que estava tentando ver de perto.

        **`ponteiro` já vem em coordenadas da folha**, e não da área visível: quem recebe a roda
        é a folha, que é o widget sob o cursor, e ela se move com a rolagem. Somar o valor da
        barra a ele -- que foi a primeira versão disto -- conta o deslocamento duas vezes, e o
        zoom pula para longe do ponto justamente quando a página está rolada, que é sempre. A
        conversão para a janela é `folha.pos()`, que responde pelos dois casos ao mesmo tempo:
        a folha rolada (posição negativa) e a folha menor que a vista (centrada, positiva).
        """
        if self._pagina is None:
            return
        anterior = self._zoom
        novo = zoomed(anterior, direcao)
        if novo == anterior:
            return

        horizontal, vertical = self._barras()
        na_janela = self._folha.pos() + ponteiro
        largura_antes, altura_antes = self._pagina.width() * anterior, self._pagina.height() * anterior
        largura_depois, altura_depois = self._pagina.width() * novo, self._pagina.height() * novo

        self.definir_zoom(novo)
        self._mover_barra(horizontal, ponteiro.x(), na_janela.x(), largura_antes, largura_depois)
        self._mover_barra(vertical, ponteiro.y(), na_janela.y(), altura_antes, altura_depois)

    @staticmethod
    def _mover_barra(barra: QScrollBar, na_folha: float, na_janela: float, antes: float, depois: float) -> None:
        fracao = anchor_after_zoom(
            pointer_canvas=na_folha, pointer_widget=na_janela, old_span=antes, new_span=depois
        )
        barra.setValue(int(round(fracao * depois)))

    # ------------------------------------------------------------------------------ clique

    def clicar_em(self, x: float, y: float) -> None:
        """Traduz um clique na folha para o índice do diagrama, se houver um ali.

        Quem decide é o `index_at` de `page_overlay`, que faz a menor caixa ganhar -- o
        detector às vezes acha a moldura do exercício **e** o tabuleiro dentro dela, e devolver
        a maior abriria a moldura, que é o candidato que o modelo lê pior.
        """
        if self._caixas is None or not self._mostrar_caixas:
            return
        indice = self._caixas.index_at(x, y, self._zoom)
        if indice is not None:
            self.caixa_clicada.emit(indice)

    # ------------------------------------------------------------------ seleção de área (S-31)

    @property
    def selecionando(self) -> bool:
        """Se o próximo arrasto recorta uma área em vez de mover a página."""
        return self._selecionando

    def ativar_selecao(self, ligado: bool) -> None:
        """Liga o modo de seleção. O cursor muda porque o mesmo botão passa a fazer outra coisa."""
        self._selecionando = ligado
        self._inicio_da_selecao = None
        self._ponto_atual = None
        self._folha.setCursor(
            Qt.CursorShape.CrossCursor if ligado else Qt.CursorShape.ArrowCursor
        )
        self._folha.update()

    def retangulo_da_selecao(self) -> QRect | None:
        """O retângulo em curso, em coordenada de folha. `None` quando não há arrasto."""
        if self._inicio_da_selecao is None or self._ponto_atual is None:
            return None
        x0, y0 = self._inicio_da_selecao
        x1, y1 = self._ponto_atual
        return QRect(QPoint(int(min(x0, x1)), int(min(y0, y1))), QPoint(int(max(x0, x1)), int(max(y0, y1))))

    def _grampear(self, x: float, y: float) -> tuple[float, float]:
        """O ponto trazido para dentro da folha. Arrastar para fora não recorta o que não existe."""
        pagina = self.pagina_escalada()
        if pagina is None:
            return (x, y)
        return (max(0.0, min(x, float(pagina.width()))), max(0.0, min(y, float(pagina.height()))))

    # ------------------------------------------------------------------------------- gestos

    def dispensar_em(self, x: float, y: float) -> None:
        """Botão direito sobre um retângulo: pede que ele saia da página (S-177)."""
        if self._caixas is None or not self._mostrar_caixas:
            return
        indice = self._caixas.index_at(x, y, self._zoom)
        if indice is not None:
            self.caixa_dispensada.emit(indice)

    def estudar_em(self, x: float, y: float) -> None:
        """Duplo clique sobre um retângulo: o diagrama de baixo vai para a sala de estudo.

        A caixa é a mesma que `clicar_em` acertaria -- a menor sob o ponteiro --, e as caixas
        escondidas não são alvo, como lá. No modo de seleção o botão significa outra coisa.
        """
        if self._caixas is None or not self._mostrar_caixas or self._selecionando:
            return
        indice = self._caixas.index_at(x, y, self._zoom)
        if indice is not None:
            self.caixa_para_estudo.emit(indice)

    def apertou_em(self, x: float, y: float) -> None:
        """Marca o ponto. **Não decide nada**: quem decide é o que o ponteiro fizer depois."""
        self._apertou_em = (x, y)
        self._arrastando_a_pagina = False
        horizontal, vertical = self._barras()
        self._barras_ao_apertar = (horizontal.value(), vertical.value())
        if self._selecionando:
            self._inicio_da_selecao = self._grampear(x, y)
            self._ponto_atual = self._inicio_da_selecao
            self._folha.update()

    def arrastou_para(self, x: float, y: float) -> None:
        """O ponteiro andou com o botão apertado: estica a seleção, ou puxa a página.

        **A mão do leitor só começa depois da folga do clique**, e é isso que faz o mesmo botão
        servir para as duas coisas -- abrir o diagrama de baixo (S-68) e puxar a página. Sem a
        folga, quem arrasta abriria um diagrama ao soltar; sem o arrasto, a única forma de andar
        na página ampliada seria a barra de rolagem.
        """
        if self._apertou_em is None:
            return
        if self._selecionando:
            self._ponto_atual = self._grampear(x, y)
            self._folha.update()
            return
        x0, y0 = self._apertou_em
        if not self._arrastando_a_pagina:
            if abs(x - x0) <= CLICK_SLOP_PX and abs(y - y0) <= CLICK_SLOP_PX:
                return
            self._arrastando_a_pagina = True
            self._folha.setCursor(Qt.CursorShape.ClosedHandCursor)
        # As barras andam pela distância **desde o aperto**, e não desde o último evento: a folha
        # se move junto com o ponteiro, então medir o passo faria o arrasto acelerar sozinho.
        horizontal, vertical = self._barras()
        horizontal.setValue(int(self._barras_ao_apertar[0] - (x - x0)))
        vertical.setValue(int(self._barras_ao_apertar[1] - (y - y0)))

    def soltou_em(self, x: float, y: float) -> None:
        """Solta: fecha a seleção, termina o arrasto, ou -- se nada andou -- é um clique."""
        apertou, self._apertou_em = self._apertou_em, None
        if self._selecionando and self._inicio_da_selecao is not None:
            self._fechar_selecao(x, y)
            return
        if self._arrastando_a_pagina:
            self._arrastando_a_pagina = False
            self._folha.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if apertou is None:
            return
        # Sem a folga, todo empurrão na página abriria o diagrama de baixo.
        if abs(x - apertou[0]) > CLICK_SLOP_PX or abs(y - apertou[1]) > CLICK_SLOP_PX:
            return
        self.clicar_em(x, y)

    def _fechar_selecao(self, x: float, y: float) -> None:
        """Converte o arrasto para pixel de página e o anuncia -- ou recusa, se for pequeno.

        **A medida do piso vem depois da conversão, e por isso** (S-330): ele fala de casa de
        tabuleiro, que é medida da folha; medi-lo antes fazia o mínimo variar oito vezes entre
        25% e 200%.
        """
        assert self._inicio_da_selecao is not None
        x0, y0 = self._inicio_da_selecao
        x1, y1 = self._grampear(x, y)
        self.ativar_selecao(False)

        zoom = self._zoom or 1.0
        regiao = (
            int(min(x0, x1) / zoom),
            int(min(y0, y1) / zoom),
            int(max(x0, x1) / zoom),
            int(max(y0, y1) / zoom),
        )
        if (regiao[2] - regiao[0]) < MIN_SELECTION_PX or (regiao[3] - regiao[1]) < MIN_SELECTION_PX:
            self.selecao_pequena.emit()
            return
        self.area_selecionada.emit(regiao)
