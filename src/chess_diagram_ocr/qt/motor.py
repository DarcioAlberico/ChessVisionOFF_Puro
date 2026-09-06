"""O painel do motor: a barra vertical ao lado do tabuleiro e as linhas candidatas (S-529).

**O que havia.** `qt/painel_de_estudo.py` mostrava a avaliação num `QProgressBar` horizontal de
`0` a `100` sob a caixa de comentário, e as linhas do MultiPV num `QLabel` de três linhas de texto
cinza. Nenhum programa de xadrez faz isso, e a razão não é estética: uma barra horizontal a 400 px
do tabuleiro não é lida junto com ele, e um `QLabel` não responde ao clique -- as linhas 2 e 3 do
motor existiam na tela e **não havia caminho nenhum** para pô-las na árvore (`variante_do_motor` só
alcançava a primeira).

**Três widgets, e cada um responde a uma pergunta que o outro não responde.**

1. `BarraDeAvaliacao` -- *de quem é a posição?* Vertical, colada ao tabuleiro, brancas embaixo. É a
   do Lichess, e a razão de ser vertical é a mesma: ela tem de ser lida com o rabo do olho enquanto
   se olha o tabuleiro, e a única forma disso é estar ao lado dele e ter a mesma altura dele.
2. `LinhasDoMotor` -- *quais são as opções?* Uma linha por candidata, **clicável**: o clique põe
   aquela linha na árvore, com a procedência no PGN. É o que a S-286 declarou como a pergunta de
   quem estuda um livro -- *o lance que o livro dá está entre os candidatos?* -- e é a que o
   `QLabel` não deixava fazer nada a respeito.
3. O rodapé de desempenho -- *dá para confiar nisso?* Profundidade e nós por segundo, que é o
   único número da tela que muda quando `Threads` muda.

**Nenhuma decisão é escrita aqui.** A curva da barra é `engine.fracao_de_vantagem`, a altura em
pixel e a cor de mate são `ui/motor_declarado`, a numeração da variante também. Este arquivo mede
e pinta.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QTextOption
from PyQt6.QtWidgets import QSizePolicy, QTextBrowser, QWidget

from chess_diagram_ocr.engine import fracao_de_vantagem
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.dica import dica_em
from chess_diagram_ocr.ui import motor_declarado, tipografia, tokens

logger = logging.getLogger(__name__)

__all__ = ["BarraDeAvaliacao", "LinhasDoMotor"]

ALTURA_MINIMA_DA_BARRA = 120
"""Abaixo disto a barra deixa de separar +0,3 de +0,6 -- um pixel passa a valer meio peão."""

CORPO_MINIMO_DO_ROTULO = 6
"""O menor corpo em que o número da barra ainda se lê. Abaixo disto ele é mancha, não dígito."""


class BarraDeAvaliacao(QWidget):
    """A barra de vantagem vertical, ao lado do tabuleiro. Brancas embaixo, pretas em cima (S-529).

    **Ela não sabe o que é uma avaliação.** Recebe `(centipeões, mate_em)` e pergunta a
    `engine.fracao_de_vantagem` onde fica a divisa e a `ui/motor_declarado` de que cor é cada
    faixa. É o mesmo par de perguntas que o gráfico da partida inteira faz, e é isso que faz os
    dois desenhos da mesma tela concordarem.

    **Sem resposta do motor ela fica no meio e cinza-clara**, e não escondida: um espaço que
    aparece e some ao lado do tabuleiro faria o tabuleiro mudar de largura a cada análise. Quem
    some é a barra inteira, junto com a seção do motor, quando não há motor nenhum (S-33).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        caixa: Callable[[], tuple[int, int]] | None = None,
        virado: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._fracao = 0.5
        self._mate_em: int | None = None
        self._display = ""
        self._caixa = caixa
        self._virado = virado
        """O tabuleiro está virado? Perguntado no `paintEvent`, como a caixa (S-529).

        **A barra espelha com o tabuleiro**, e é o que o Lichess faz: quem virou o tabuleiro está
        olhando a partida do lado das pretas, e uma barra que continuasse com as brancas embaixo
        obrigaria o olho a traduzir justamente no momento em que ele já está traduzindo o
        tabuleiro. `None` é "não há quem pergunte" -- a barra fica com as brancas embaixo, que é a
        posição de fábrica."""
        """De onde a onde desenhar, em `(topo, lado)`. `None` é o widget inteiro (S-529).

        **Perguntado no `paintEvent`, e não guardado**, porque a resposta muda a cada geometria e o
        que se quer é que ela **nunca** esteja desatualizada. Um `setFixedHeight` na hora do
        `resizeEvent` responde com a geometria de antes: medido na primeira fotografia, a barra
        ficou com 240 px (o piso do tabuleiro) ao lado de um tabuleiro de 425. Aqui o widget ocupa
        a fileira inteira e a barra é pintada exatamente sobre o quadrado do tabuleiro."""

        self.setFixedWidth(motor_declarado.LARGURA_DA_BARRA)
        self.setMinimumHeight(ALTURA_MINIMA_DA_BARRA)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        dica_em(
            self,
            "A vantagem do lado a jogar, como o motor a vê. Brancas embaixo.\n"
            "A escala não é linear: ela é a expectativa de pontuação do Elo, então a diferença\n"
            "entre +0,2 e +1,0 ocupa mais barra que a diferença entre +8 e +12.",
        )
        tema.ao_repintar(self.update)

    # ---------------------------------------------------------------------------- estado

    def definir(self, score_cp: int | None, mate_em: int | None, display: str = "") -> None:
        """A avaliação de agora. `(None, None)` é "o motor ainda não respondeu"."""
        self._fracao = fracao_de_vantagem(score_cp, mate_em)
        self._mate_em = None if mate_em is None else int(mate_em)
        self._display = str(display)
        self.update()

    def limpar(self) -> None:
        self.definir(0, None, "")

    @property
    def fracao(self) -> float:
        """Onde está a divisa, de 0 (pretas ganhando) a 1. É por ela que o teste pergunta."""
        return self._fracao

    def faixa(self) -> tuple[int, int]:
        """`(topo, lado)` da barra dentro do widget -- o quadrado do tabuleiro, ou o widget todo.

        **O widget do tabuleiro é mais alto que o tabuleiro**: `BoardGeometry.fit` centra um
        quadrado na caixa e sobra folga em cima e embaixo. Uma barra da altura do widget passa do
        tabuleiro nas duas pontas (medido: 480 px de barra contra 425 de tabuleiro, 27 px sobrando
        de cada lado), e quem lê os dois juntos vê uma régua que não bate com o que ela mede.
        """
        if self._caixa is None:
            return 0, self.height()
        topo, lado = self._caixa()
        if lado < ALTURA_MINIMA_DA_BARRA:  # pragma: no cover - a coluna ainda sem geometria
            return 0, self.height()
        return max(0, int(topo)), min(self.height(), int(lado))

    def altura_de_brancas(self) -> int:
        """Quantos pixels a faixa branca ocupa agora. O mesmo número que `paintEvent` usa."""
        return motor_declarado.altura_de_brancas(self._fracao, self.faixa()[1])

    def invertida(self) -> bool:
        """A barra está espelhada (pretas embaixo)? É o que `virado` respondeu (S-529)."""
        return bool(self._virado()) if self._virado is not None else False

    def sizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        return QSize(motor_declarado.LARGURA_DA_BARRA, 4 * ALTURA_MINIMA_DA_BARRA)

    # ---------------------------------------------------------------------------- desenho

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        """Duas faixas e um fio. A das brancas é a de baixo -- ou a de cima, com o tabuleiro virado.

        **A ordem importa**: pinta-se a barra inteira com a cor de um lado e depois a faixa do
        outro por cima dela. Pintar as duas por coordenada deixaria uma linha de fundo entre elas no
        arredondamento, e essa linha é visível numa barra de 26 px.
        """
        largura = self.width()
        topo, altura = self.faixa()
        if largura <= 0 or altura <= 0:  # pragma: no cover - widget sem geometria
            return
        de_brancas = motor_declarado.altura_de_brancas(self._fracao, altura)
        invertida = self.invertida()
        mate = self._mate_em is not None
        pintor = QPainter(self)
        try:
            pintor.fillRect(
                0,
                topo,
                largura,
                altura,
                QColor(tema.cor_atual(motor_declarado.papel_do_lado(brancas=False))),
            )
            if de_brancas > 0:
                # Com o tabuleiro virado a faixa das brancas nasce no topo; sem virar, no pé.
                inicio = topo if invertida else topo + altura - de_brancas
                pintor.fillRect(
                    0,
                    inicio,
                    largura,
                    de_brancas,
                    QColor(tema.cor_atual(motor_declarado.papel_do_lado(brancas=True))),
                )
            self._desenhar_moldura(pintor, topo, altura, mate=mate)
            self._escrever_avaliacao(pintor, topo, altura, invertida=invertida)
        finally:
            pintor.end()

    def _desenhar_moldura(self, pintor: QPainter, topo: int, altura: int, *, mate: bool) -> None:
        """O fio em volta, na cor que a pele pede e na espessura que o mate pede (S-529)."""
        papel = motor_declarado.papel_da_moldura(mate=mate, cromo_escuro=tema.cromo_escuro_em_vigor())
        espessura = motor_declarado.espessura_da_moldura(mate=mate)
        pintor.setPen(QColor(tema.cor_atual(papel)))
        for passo in range(espessura):
            largura = self.width() - 1 - 2 * passo
            alto = altura - 1 - 2 * passo
            if largura <= 0 or alto <= 0:  # pragma: no cover - barra sem espaço para o fio
                break
            pintor.drawRect(passo, topo + passo, largura, alto)

    def _escrever_avaliacao(self, pintor: QPainter, topo: int, altura: int, *, invertida: bool) -> None:
        """O número dentro da barra, **do lado de quem está melhor** -- como no Lichess.

        Do lado de quem está melhor porque é ali que há faixa para escrevê-lo com contraste: um
        número no meio ficaria metade sobre cada cor.

        **Sem o sinal e no maior corpo que couber** (segunda rodada). O sinal sai porque a posição
        do número já diz de quem é a vantagem (`motor_declarado.rotulo_da_barra`); o corpo desce de
        um em um ponto até o texto caber na largura da barra, e **se nem o menor couber o número
        não é escrito**. Escrever cortado é pior que não escrever: `-12,34` cortado saía `12`, que
        é uma avaliação diferente e igualmente plausível. O número continua inteiro na seção do
        motor, que é para onde quem precisa do dígito olha.
        """
        rotulo = motor_declarado.rotulo_da_barra(self._display)
        if not rotulo:
            return
        fonte = self._fonte_que_cabe(rotulo)
        if fonte is None:
            return
        pintor.setFont(fonte)
        brancas_melhor = self._fracao >= 0.5
        embaixo = brancas_melhor != invertida
        papel = motor_declarado.PAPEL_DE_PRETAS if brancas_melhor else motor_declarado.PAPEL_DE_BRANCAS
        pintor.setPen(QColor(tema.cor_atual(papel)))
        altura_do_texto = min(altura, QFontMetrics(fonte).height() + 2)
        onde = topo + altura - altura_do_texto if embaixo else topo
        pintor.drawText(
            0,
            onde,
            self.width(),
            altura_do_texto,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            rotulo,
        )

    def _fonte_que_cabe(self, rotulo: str) -> Any:
        """O maior corpo, de `DADO - 2` para baixo, em que `rotulo` cabe na barra. `None` se nenhum.

        A folga de 2 px é a margem: um texto que encosta nos dois fios fica ilegível mesmo cabendo.
        """
        maior = tema.fonte_atual(tipografia.DADO).pointSize() - 2
        for corpo in range(max(CORPO_MINIMO_DO_ROTULO, maior), CORPO_MINIMO_DO_ROTULO - 1, -1):
            fonte = tema.fonte_atual(tipografia.DADO)
            fonte.setPointSize(corpo)
            if QFontMetrics(fonte).horizontalAdvance(rotulo) <= self.width() - 2:
                return fonte
        return None


class LinhasDoMotor(QTextBrowser):
    """As linhas candidatas do MultiPV, uma por linha, **clicáveis** (S-529).

    **O clique põe a linha na árvore**, e a decisão é a do ChessBase: no painel de motor dele uma
    linha se arrasta para a notação, e o que ela leva é a variante inteira com a avaliação junto.
    Aqui o gesto é o clique, porque arrastar num `QTextBrowser` seria um mecanismo novo para o
    mesmo fim -- e porque a sala já tem o caminho pronto (`variante_do_motor`, S-286), que até
    agora só alcançava a primeira linha.

    **A alternativa medida e recusada: o clique só mover o tabuleiro.** Com a análise contínua
    ligada o motor responde a cada ~800 ms, e cada resposta redesenha esta lista; um tabuleiro que
    seguisse a linha do motor sairia da posição e faria o motor recomeçar noutra -- a lista mudaria
    debaixo do cursor de quem ia clicar na segunda linha. A árvore, não: o que entrou nela fica,
    aparece na lista de lances e vai para o PGN.

    **E o lance corrente não se move**, que é o outro lado da mesma decisão: quem clica na linha 1
    quase sempre quer clicar na 2 em seguida, para comparar as duas na árvore. As duas ficam lá,
    lado a lado, sob a mesma posição -- que é exatamente a comparação que a S-286 descreve.

    Um `QTextBrowser` e não uma `QListWidget` pela mesma razão da lista de lances: o clique chega
    por `anchorClicked` com o índice, o texto é rico, e não há mapa de itens a manter.
    """

    escolhida = pyqtSignal(int)
    """O índice da linha clicada, de **1** a N -- a mesma numeração que o texto mostra."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setFont(tema.fonte_atual(tipografia.CORPO))
        self.anchorClicked.connect(self._clique)
        # **Quebra só em espaço de verdade** (a regra da S-515 aplicada aqui): o modo de fábrica é
        # `WrapAtWordBoundaryOrAnywhere`, e numa coluna de 203 px ele partia `Qxg4` ao meio. O
        # número do lance fica colado ao lance por `&nbsp;`, em `_colado`.
        self.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.setMinimumHeight(4 * tema.altura_de_linha_atual())
        dica_em(
            self,
            "As melhores linhas que o motor achou, na ordem de quem está no lance: a primeira é a\n"
            "melhor para ele, e por isso a avaliação das seguintes anda para o lado do adversário.\n"
            "Clique numa delas para pô-la na árvore como variante, a partir do lance corrente.\n"
            "Quantas linhas aparecem é a opção «Linhas do motor» das preferências.",
        )
        self._linhas: tuple[object, ...] = ()
        self._html = ""
        """O último HTML desenhado. Ver `_trocar_html`: igual não redesenha."""

    def mostrar(self, linhas: object, vazio: str = "") -> None:
        """Redesenha a lista. `vazio` é o que dizer quando não há linha nenhuma.

        **A rolagem e a seleção sobrevivem ao redesenho** (segunda rodada). Com a análise contínua
        ligada o motor responde a cada ~900 ms, e cada resposta chamava `setHtml` -- que troca o
        documento inteiro. Medido pelo crítico com `MultiPV 10`: a lista voltava ao topo a cada
        resposta, e quem tinha rolado até a nona linha para clicar nela não conseguia; quem tinha
        selecionado uma linha para copiá-la perdia a seleção antes de chegar ao `Ctrl+C`.

        Duas defesas, e a primeira é a que mais paga: **HTML igual não é redesenhado**. A resposta
        seguinte muda a profundidade e às vezes um centésimo, mas nas posições paradas -- que são
        aquelas em que alguém está lendo a lista com calma -- ela é literalmente a mesma, e aí não
        há redesenho nenhum. Quando muda mesmo, a posição da barra e as pontas da seleção são
        anotadas antes e repostas depois, que é o que `qt/painel_de_texto.py` já faz.
        """
        self._linhas = tuple(linhas or ())  # type: ignore[arg-type]
        if not self._linhas:
            self._trocar_html(
                f'<span style="color:{tema.cor_atual(tokens.TEXTO_SECUNDARIO)}">{html.escape(vazio)}</span>'
            )
            return
        secundario = tema.cor_atual(tokens.TEXTO_SECUNDARIO)
        padrao = tema.cor_atual(tokens.TEXTO_PADRAO)
        partes: list[str] = []
        for linha in self._linhas:
            # A avaliação em negrito e a variante em peso normal: é a hierarquia da lista de
            # lances (S-268), e ela vale aqui pela mesma razão -- compara-se o número primeiro.
            partes.append(
                f'<div><a href="linha:{linha.indice}" style="text-decoration:none;color:{padrao}">'  # type: ignore[attr-defined]
                f'<b>{html.escape(linha.display)}</b>&nbsp;&nbsp;'  # type: ignore[attr-defined]
                f'<span style="color:{secundario}">{_colado(linha.variante)}</span>'  # type: ignore[attr-defined]
                "</a></div>"
            )
        self._trocar_html("".join(partes))

    def _trocar_html(self, marcado: str) -> None:
        """`setHtml` só quando o texto mudou, e com a rolagem e a seleção repostas. Ver `mostrar`."""
        if marcado == self._html:
            return
        self._html = marcado
        barra = self.verticalScrollBar()
        rolagem = barra.value() if barra is not None else 0
        cursor = self.textCursor()
        inicio, fim = cursor.selectionStart(), cursor.selectionEnd()
        self.setHtml(marcado)
        if barra is not None:
            barra.setValue(min(rolagem, barra.maximum()))
        if fim > inicio:
            reposto = self.textCursor()
            limite = len(self.toPlainText())
            reposto.setPosition(min(inicio, limite))
            reposto.setPosition(min(fim, limite), reposto.MoveMode.KeepAnchor)
            self.setTextCursor(reposto)

    def texto_das_linhas(self) -> tuple[str, ...]:
        """O que cada linha diz, sem marcação. É por aqui que o teste lê a lista."""
        return tuple(linha.texto() for linha in self._linhas)  # type: ignore[attr-defined]

    def _clique(self, url: QUrl) -> None:
        endereco = url.toString()
        if not endereco.startswith("linha:"):  # pragma: no cover - só há uma forma de âncora
            return
        self.escolhida.emit(int(endereco.removeprefix("linha:")))


def _colado(variante: str) -> str:
    """`12. Ba4` com o número colado ao lance, para a quebra não os separar (S-515/S-529).

    Em notação, `12.` no fim de uma linha e `Ba4` no começo da seguinte é ilegível -- é a mesma
    decisão de `sala_declarada.PAPEIS_COLADOS`, aplicada ao único par que aqui pode quebrar.
    """
    return html.escape(variante).replace(". ", ".&nbsp;")
