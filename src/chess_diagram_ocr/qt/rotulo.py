"""O rótulo que encolhe em vez de empurrar a janela, e o separador de bloco (F9-C2). **Só pinta.**

**O defeito que obrigou o primeiro, medido pelo crítico do ciclo 1.** Um livro do acervo chama-se
`Gaprindashvili, Paata - Imagination in Chess. How To Think Creatively And Avoid Foolish Mistakes
(Bastford, 2005) 2p 145` -- 149 caracteres, e ele **já está** na pasta `PDF/` do projeto. Um
`QLabel` comum pede a largura do texto inteiro como largura mínima, e o resultado medido foi:

- `minimumSizeHint().width()` da janela subindo de **1243 para 1513 px** -- ou seja, o nome de um
  arquivo decidindo qual é a menor tela em que o programa cabe;
- o próprio rótulo desenhado **fora** da janela de 1920 px (`x=1094`, 906 px de largura);
- `Cancelar exportação` desenhado **por cima** de `Página anterior`, 2.310 px² de sobreposição.

Um rótulo não pode fazer nada disso. `RotuloElidido` responde `0` de largura mínima, aceita a
largura que o leiaute tiver e corta o texto **no meio** -- `ElideMiddle` e não `ElideRight` porque
o fim do nome de um livro costuma carregar o ano e a página, que é o que distingue duas edições.
O nome inteiro fica na dica, que é onde ele não custa pixel nenhum.

**O separador existe pelo mesmo item.** O §7 diz, sobre agrupar a barra do visor: *"separador
visível de 1 px entre blocos, porque 4 px de diferença de vão não é agrupamento"*. Um `QFrame`
`VLine` é o que o Qt tem para isso, e ele é declarado aqui para os três painéis desenharem o mesmo
traço em vez de cada um inventar o seu.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QPixmap, QResizeEvent
from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QSizePolicy, QWidget

__all__ = ["CampoQueAvisaQueContinua", "RecorteElastico", "RotuloElidido", "separador"]

RETICENCIA = "…"
"""O sinal de "isto continua". `U+2026` e nao tres pontos: um ponto por caractere fica com o
espacamento errado numa fonte monoespacada, e o campo da FEN usa `Consolas`."""


class RotuloElidido(QLabel):
    """Um `QLabel` que corta o texto no meio quando não cabe, e nunca pede largura por ele.

    O texto pedido fica em `texto_inteiro`; `text()` devolve o que está desenhado, que é o que
    uma captura de tela lê. A dica recebe o inteiro, e é a saída sem custo de leiaute.
    """

    def __init__(
        self,
        texto: str = "",
        parent: QWidget | None = None,
        *,
        largura_desejada: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._inteiro = ""
        self._teto = LARGURA_DESEJADA if largura_desejada is None else largura_desejada
        """Quanto o rótulo **pede**, no máximo. `0` é "peça o texto inteiro" -- ver `sizeHint`."""
        # `Preferred` na horizontal, com `sizeHint` **com teto** e `minimumSizeHint` **zero**:
        # o rótulo pede o que cabe e aceita encolher até sumir. `Ignored` foi tentado antes e é
        # forte demais -- o leiaute passa a não pedir largura nenhuma por ele, e o bloco inteiro
        # sai com a largura do botão ao lado, com o nome do livro invisível em qualquer janela.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.definir_texto(texto)

    def definir_texto(self, texto: str) -> None:
        """O texto que o rótulo representa. Ele é elidido ao ser desenhado."""
        self._inteiro = texto or ""
        self.setToolTip(self._inteiro)
        self._reelidir()

    @property
    def texto_inteiro(self) -> str:
        """O que foi pedido, sem corte. É o que o teste compara."""
        return self._inteiro

    def _reelidir(self) -> None:
        largura = max(0, self.width())
        if largura <= 0:
            super().setText(self._inteiro)
            return
        metrica = QFontMetrics(self.font())
        super().setText(metrica.elidedText(self._inteiro, Qt.TextElideMode.ElideMiddle, largura))

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._reelidir()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """Zero de largura. **É a linha do item 2 do §7**, e sem ela nada mais adianta.

        `QLabel.minimumSizeHint` devolve a largura do texto inteiro quando não há quebra de
        linha, e é ela que sobe pela árvore de leiautes até virar a largura mínima da janela.
        A altura continua sendo a da fonte: um rótulo de altura zero desaparece.
        """
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """A largura **desejada**: a do texto inteiro, com teto.

        Zero aqui faria o rótulo sumir numa barra que distribui pelo desejado -- que é o caso do
        `LeiauteFluido`. O teto é o que impede um nome de 149 caracteres de empurrar os vizinhos
        para a linha de baixo, que é o outro defeito medido.

        **Mede o texto inteiro e não `super().sizeHint()`, e a diferença é um laço.** O
        `QLabel` responde pela largura do que **está escrito** nele, que é o texto já elidido para
        a largura de agora: pedir aquilo devolveria a largura de agora, o leiaute a concederia, e
        o rótulo encolheria a cada passada até sumir. Foi medido: o bloco do livro saiu com 90 px,
        11 deles de rótulo.
        """
        altura = super().sizeHint().height()
        pedido = QFontMetrics(self.font()).horizontalAdvance(self._inteiro) if self._inteiro else 0
        return QSize(pedido if self._teto <= 0 else min(pedido, self._teto), altura)


LARGURA_DESEJADA = 130
"""Quanto o rótulo do livro **pede** na barra do visor, no máximo, em pixel.

**É o teto da barra, e não do rótulo -- e essa distinção foi paga no ciclo 7** (§4.1). O mesmo
teto valia para o rótulo do **rodapé**, que não tem refluxo nenhum: o leiaute lhe dava 130 px, ele
pedia 313, e o resultado era
`'1937 Kemeri.pdf · p. 121 de 289 · nenhum diagrama nesta página'` desenhado como
`'1937 Kemeri…esta página'` -- **39 de 62 caracteres perdidos** -- com **1534 px livres na mesma
faixa** a 1920, 980 a 1366 e 894 a 1280, em todas as 36 capturas. A carta §3.3 abre com
*"qualquer texto cortado, sobreposto ou com reticências onde caberia"*, e o que morria era a
informação inteira: a página, o total e o resultado da detecção.

Quem passa `largura_desejada=0` pede o texto inteiro e continua com `minimumSizeHint` zero -- ou
seja, continua **não** decidindo a largura mínima da janela, que é o defeito original. O teto
serve a barra fluida, onde um rótulo que pede 906 px decide o refluxo dos vizinhos; no rodapé, que
é uma linha só, ele só produzia reticência gratuita.

**Não é o texto que decide: é a barra.** O crítico mediu que o nome de 149 caracteres pedia
**906 px** -- três vezes a largura de qualquer botão --, e um rótulo que pede mais que a soma de
dois blocos é quem decide o refluxo: a barra deixa de ter mapa espacial e passa a fluir como
texto. O teto é o que devolve a decisão para quem desenha a barra.

**130 e não 240, e o número foi buscado.** É o maior valor em que o bloco [Livro] mais o bloco
[Reconhecer] ainda cabem numa fila só na barra de 500 px -- que é a largura que o painel do PDF
tem numa janela de 1243, o piso do ciclo 1. Um pixel a mais e a barra volta a três filas na
janela estreita, que é exatamente o número que o item 11 do §7 veio derrubar. O nome inteiro
continua na dica, na barra de título e no rodapé."""


class CampoQueAvisaQueContinua(QLineEdit):
    """Um campo editável que **desenha** uma reticência quando o texto passa da borda direita.

    **O defeito, medido em quatro larguras** (F9-C7, §4.5). O campo da FEN da aba Estudo tem
    535 px a 1920, **374 a 1366, 348 a 1280 e 286 a 1024**, e uma FEN de meio-jogo pede 504 px.
    A 1024 vê-se `'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQ'` -- **sem reticência e sem sinal
    nenhum**. Quem lê a FEN na tela para copiá-la à mão copia uma FEN inválida, e o prefixo é o
    caso perigoso: `rnbqkbnr/…/RNBQ` **parece** uma FEN completa, enquanto um sufixo
    (`…RNBQKBNR w KQkq - 0 1`) não parecia.

    **O conserto do ciclo 6 mudou qual ponta some, não se some.** Ele pôs o cursor em 0 -- o
    começo vale mais que o fim, e isso continua certo --, e o teste que o cobra afirma
    `cursorPositionAt(QPoint(4, h/2)) == 0` **três linhas depois de assegurar que o campo é
    estreito demais**: ele monta o caso cortado e verifica só de que lado o corte cai. Não havia
    como ele reprovar enquanto a ponta direita sumisse em silêncio.

    **Por que uma reticência desenhada e não o texto elidido.** O campo é editável -- é por ele
    que se cola uma FEN e se aperta Enter --, e elidir o `text()` de um campo editável corromperia
    o que `apply_fen` lê. Então o texto fica inteiro e o **desenho** ganha o aviso: uma faixa de
    margem à direita, reservada por `setTextMargins`, com a reticência pintada por cima do fundo
    do campo. O texto nunca passa por baixo dela, e `texto_cortado()` responde por ela.

    **E ela some quando não é necessária**: a 1920 a FEN cabe e o campo é um `QLineEdit` comum,
    sem margem reservada e sem marca. Um aviso permanente seria ruído, e ruído permanente é o que
    se aprende a não ver.
    """

    def __init__(self, texto: str = "", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self._margem = 0
        self.textChanged.connect(lambda _texto: self._reavaliar())
        self._reavaliar()

    # --------------------------------------------------------------------------- a pergunta

    def texto_cortado(self) -> bool:
        """Se o texto não cabe na área de desenho do campo -- é o que acende a reticência.

        A conta é `horizontalAdvance` contra a largura útil, e não `cursorPositionAt`: o
        `cursorPositionAt` responde sobre a **rolagem de agora**, e um campo rolado até o fim
        mostraria o último caractere na borda direita com metade do texto escondida à esquerda.
        A pergunta aqui é sobre o texto e a largura, que é o que não depende de onde se rolou.
        """
        return self._pedido() > self._util()

    def _pedido(self) -> int:
        return QFontMetrics(self.font()).horizontalAdvance(self.text()) if self.text() else 0

    def _util(self) -> int:
        margens = self.textMargins()
        moldura = self.contentsRect().width() - margens.left() - margens.right()
        # O `QLineEdit` guarda ~2 px de folga de cada lado antes do primeiro glifo; sem descontá-la
        # a marca acenderia com o texto ainda cabendo, que é ruído por um pixel.
        return max(0, moldura - 4)

    # --------------------------------------------------------------------------- o desenho

    def _largura_da_marca(self) -> int:
        return QFontMetrics(self.font()).horizontalAdvance(RETICENCIA) + 6

    def _reavaliar(self) -> None:
        """Reserva (ou devolve) a faixa da marca. Só mexe no leiaute quando o estado muda."""
        margens = self.textMargins()
        # A pergunta é feita **sem** a margem de agora: com ela reservada, o texto passa a caber
        # e a marca se apagaria, o que devolveria a margem e a faria acender de novo -- um
        # pisca-pisca a cada `resizeEvent`. É a mesma armadilha do `sizeHint` de `RotuloElidido`.
        util = (
            self.contentsRect().width()
            - margens.left()
            - max(0, margens.right() - self._margem)
            - 4
        )
        precisa = self._pedido() > max(0, util)
        alvo = self._largura_da_marca() if precisa else 0
        if alvo == self._margem:
            return
        self.setTextMargins(
            margens.left(), margens.top(), margens.right() - self._margem + alvo, margens.bottom()
        )
        self._margem = alvo
        self.update()

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().paintEvent(a0)
        if not self._margem:
            return
        area = self.contentsRect()
        faixa = area.adjusted(area.width() - self._margem, 0, 0, 0)
        pintor = QPainter(self)
        # O fundo do campo por baixo da marca: sem ele o último glifo do texto rolado aparece
        # atrás da reticência quando o cursor está no fim.
        pintor.fillRect(faixa, self.palette().base())
        cor = QColor(self.palette().text().color())
        cor.setAlpha(190)
        pintor.setPen(cor)
        pintor.drawText(faixa, int(Qt.AlignmentFlag.AlignCenter), RETICENCIA)
        pintor.end()

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._reavaliar()


def separador(parent: QWidget | None = None) -> QFrame:
    """O traço vertical de 1 px que separa dois blocos de uma barra. Ver o cabeçalho."""
    traco = QFrame(parent)
    traco.setFrameShape(QFrame.Shape.VLine)
    traco.setFrameShadow(QFrame.Shadow.Plain)
    traco.setFixedWidth(1)
    return traco


class RecorteElastico(QLabel):
    """Uma imagem quadrada que ocupa o quadrado que couber, entre um piso e um teto.

    **O defeito que ela fecha é o item 4 do §7, e a causa estava isolada pelo crítico**:
    `painel_da_galeria.setFixedSize(420, 420)`. Um tamanho fixo não é uma preferência de desenho,
    é um piso de janela: 420 px de recorte mais a lateral de 260 mais a legenda de oito linhas
    faziam a janela **recusar 1366×768**, a resolução em que de 13 % a 37 % dos controles de cada
    aba ficavam abaixo da borda inferior da tela -- incluindo a ação primária da Revisão e do
    Dataset -- sem barra de rolagem nenhuma.

    O piso continua existindo, e é o argumento original: *"a galeria é para percorrer, e um
    tamanho que muda a cada diagrama faria a imagem pular sob o ponteiro"*. Ela não pula porque o
    lado só muda quando a **janela** muda, e nunca com o diagrama: `heightForWidth` amarra a
    altura à largura concedida, e o pixmap é reescalado a partir do original guardado -- reescalar
    o já reescalado perde definição a cada passo.
    """

    def __init__(self, parent: QWidget | None = None, *, minimo: int, maximo: int) -> None:
        super().__init__(parent)
        self._minimo = minimo
        self._maximo = maximo
        self._original = QPixmap()
        self.setMinimumSize(minimo, minimo)
        self.setMaximumSize(maximo, maximo)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    @property
    def lado(self) -> int:
        """O lado que a imagem tem agora, em pixel. Entre o piso e o teto declarados."""
        return max(self._minimo, min(self._maximo, min(self.width(), self.height())))

    def definir_recorte(self, pixmap: QPixmap) -> None:
        """A imagem a mostrar, no tamanho original. Um pixmap nulo limpa o recorte."""
        self._original = pixmap
        self._reescalar()

    def limpar_recorte(self) -> None:
        self._original = QPixmap()
        self.setPixmap(QPixmap())

    def _reescalar(self) -> None:
        if self._original.isNull():
            self.setPixmap(QPixmap())
            return
        lado = self.lado
        self.setPixmap(
            self._original.scaled(
                lado,
                lado,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - assinatura do Qt
        return True

    def heightForWidth(self, a0: int) -> int:  # noqa: N802 - assinatura do Qt
        """Quadrado: a altura é a largura, grampeada entre o piso e o teto."""
        return max(self._minimo, min(self._maximo, a0))

    def sizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        """O teto. É o tamanho que a galeria quer quando há tela para ele."""
        return QSize(self._maximo, self._maximo)

    def resizeEvent(self, a0: QResizeEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().resizeEvent(a0)
        self._reescalar()
