"""O estudo impresso e em PDF: a folha desenhada, o diagrama em vetor, a prévia (S-545).

**O que ele não decide.** Onde a página quebra, o que não se separa do quê, a margem e o texto do
cabeçalho e do rodapé são de `ui/impressao_do_estudo.py`. Aqui há `QPainter`, fonte e `QPrinter` --
a mesma fronteira de `qt/lote_de_diagramas.py`.

**Um desenhista, dois dispositivos.** `QPdfWriter` e `QPrinter` são os dois `QPagedPaintDevice`, e
o Qt já os faz iguais para quem pinta: mesma `width()`/`height()` da área útil, mesmo
`newPage()`. Por isso "Salvar como PDF" e "Imprimir" não são dois desenhos -- são o mesmo
`FolhaDoEstudo.desenhar` recebendo um dispositivo diferente. Duas implementações dariam duas
paginações, e a que ninguém confere é a que sai errada.

**O diagrama é vetor, e é o motivo de o desenho passar pelo SVG.** `QSvgRenderer.render(pintor,
retângulo)` emite caminho no PDF -- linha, retângulo e elipse --, e não uma imagem amostrada:
ampliar a página a 800% continua mostrando a borda da casa reta. Um `QPixmap` desenhado no mesmo
lugar sairia embutido como bitmap e serrilharia na primeira ampliação, além de multiplicar o
tamanho do arquivo. O SVG é o de `diagrama_svg.py`, o mesmo do EPUB.

**O texto é texto, e não desenho de texto.** Cada linha sai por `QTextLine.draw`, que escreve
operador de texto no PDF: dá para selecionar, copiar e procurar dentro do arquivo. É por isso que
o parágrafo é medido com `QTextLayout` em vez de ser quebrado à mão -- a quebra que o desenho fez
é a mesma que a paginação recebeu, linha por linha, e não uma segunda estimativa.

**Sem thread.** Um estudo de 300 lances vira PDF em menos de um segundo, e o
`QPrintPreviewDialog` chama `paintRequested` na linha de eventos por construção: uma travessia
aqui seria fiação sem trabalho para atravessar. Ver `docs/ARCHITECTURE.md`, seção Threads.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QByteArray, QMarginsF, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QTextCharFormat,
    QTextLayout,
    QTextOption,
)
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.diagrama_svg import svg_da_posicao
from chess_diagram_ocr.estudo import Estudo
from chess_diagram_ocr.estudo_paragrafos import COMENTARIO_DO_ESTUDO, DIAGRAMA, TITULO, VARIANTE, titulo_do_estudo
from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.impressao_do_estudo import (
    LARGURA_DO_DIAGRAMA,
    MARGEM_MM,
    Bloco,
    Pagina,
    Pedaco,
    blocos_do_estudo,
    cabecalho,
    paginar,
    rodape,
)
from chess_diagram_ocr.ui.lote_de_diagramas import PADRAO, cores_da_pele

logger = logging.getLogger(__name__)

__all__ = ["FolhaDoEstudo", "abrir_previa_de_impressao", "pdf_do_estudo"]

CORPO_PT = 10.5
"""O corpo do texto, em pontos. É o de um livro de xadrez: a notação é curta e densa, e um corpo
de 12 põe metade das linhas de análise em duas."""

TITULO_PT = 15.0
"""O título do capítulo. Um degrau e meio acima do corpo, que é o que basta para ele ser título
sem virar cartaz -- a folha tem um só, e ele não disputa atenção com o diagrama."""

RECUO_DA_VARIANTE = 3.0
"""O recuo da variante, **em larguras do caractere `0`** da fonte do corpo. Em caractere e não em
milímetro: o recuo tem de acompanhar o corpo do texto, e um número de milímetros ficaria certo num
tamanho de fonte e errado nos outros. Três é o degrau da lista da sala (`RECUO_POR_NIVEL`) na
escala da folha."""

RESOLUCAO_DO_PDF = 300
"""Pontos por polegada do `QPdfWriter`. O padrão dele é 1200, que é resolução de fotolito: o texto
é vetor e o diagrama é vetor, então a resolução só decide a **grade** em que as coordenadas caem,
e 300 já é mais fina que qualquer impressora de escritório."""


def _disposto(
    texto: str,
    fonte: QFont,
    largura: float,
    *,
    recuo: float = 0.0,
    alinhamento: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
) -> tuple[QTextLayout, list[float]]:
    """Um texto quebrado em linhas naquela largura, **com a tinta carimbada em cada trecho**.

    O carimbo é `QTextLayout.FormatRange` sobre o texto inteiro, e é o que faz a cor sobreviver à
    regravação da pré-visualização: ver `FolhaDoEstudo._margens`. A tinta é a do documento --
    `tokens.cor(TEXTO_PADRAO)` sem `cromo_escuro`, que é a fronteira da S-224: papel não tem
    aparência, e a folha não escurece com a pele da janela.

    Devolve a disposição e a altura de cada linha, que é o que a paginação pura consome.
    """
    disposicao = QTextLayout(texto, fonte)
    opcao = QTextOption(alinhamento)
    opcao.setWrapMode(QTextOption.WrapMode.WordWrap)
    disposicao.setTextOption(opcao)
    faixa = QTextLayout.FormatRange()
    faixa.start = 0
    faixa.length = len(texto)
    caractere = QTextCharFormat()
    caractere.setForeground(QColor(tokens.cor(tokens.TEXTO_PADRAO)))
    faixa.format = caractere
    disposicao.setFormats([faixa])

    alturas: list[float] = []
    disposicao.beginLayout()
    while True:
        linha = disposicao.createLine()
        if not linha.isValid():
            break
        linha.setLineWidth(max(1.0, largura - recuo))
        linha.setPosition(QPointF(recuo, sum(alturas)))
        alturas.append(max(1.0, linha.height()))
    disposicao.endLayout()
    return disposicao, alturas


class FolhaDoEstudo:
    """O estudo desenhado em folhas, num dispositivo paginado do Qt.

    Guarda os blocos e o título; a medição acontece por dispositivo, porque a fonte e a área útil
    dependem dele -- a mesma folha vale em A4 e em Carta, e a paginação sai diferente nas duas.
    """

    def __init__(self, estudo: Estudo, *, titulo: str = "") -> None:
        self.estudo = estudo
        self.titulo = " ".join((titulo or titulo_do_estudo(estudo)).split())
        self.blocos: tuple[Bloco, ...] = blocos_do_estudo(estudo)
        self.paginas: tuple[Pagina, ...] = ()
        """As páginas do último desenho. Vazio antes do primeiro -- ver `desenhar`."""

    # ------------------------------------------------------------------------------ o desenho

    def desenhar(self, dispositivo: QPdfWriter | QPrinter) -> int:
        """Desenha o estudo inteiro no dispositivo e devolve quantas páginas saíram.

        O `QPainter` é aberto e fechado aqui: um `QPdfWriter` só fecha o arquivo quando o pintor
        que o pinta é destruído, e deixar isso para o coletor faria o teste ler um PDF pela
        metade -- que é o modo de falha que não aparece na máquina de quem escreveu o código.
        """
        pintor = QPainter()
        if not pintor.begin(dispositivo):
            logger.warning("O dispositivo de impressão recusou o pintor; nada foi desenhado.")
            return 0
        try:
            return self._desenhar(pintor, dispositivo)
        finally:
            pintor.end()

    def _desenhar(self, pintor: QPainter, dispositivo: QPdfWriter | QPrinter) -> int:
        # **A tinta é a do documento, e não a do cromo** -- é a fronteira da S-224 aplicada à
        # folha: `tokens.cor(TEXTO_PADRAO)` **sem** `cromo_escuro` é o preto de 21:1 contra o
        # branco, e é o mesmo nas três peles, porque papel não tem aparência. A caneta responde
        # por tudo o que não seja texto; quem carimba o texto é `_disposto`, e o docstring de
        # `_margens` diz por que o carimbo é necessário além dela.
        pintor.setPen(QColor(tokens.cor(tokens.TEXTO_PADRAO)))
        largura = float(dispositivo.width())
        altura = float(dispositivo.height())
        corpo, titulo, medida = self._fontes(pintor)
        banda = medida.height() * 1.6
        """A faixa do cabeçalho e a do rodapé. Uma linha e meia: a linha do texto mais o ar que a
        separa do corpo -- sem ele o número da página encosta na última linha da análise."""

        alto = banda
        altura_util = max(1.0, altura - 2 * banda)
        espaco = medida.height() * 0.5

        desenhos = [self._medir(bloco, largura, corpo, titulo, medida) for bloco in self.blocos]
        self.paginas = paginar(
            [alturas for _disposicao, alturas, _lado in desenhos],
            altura_util=altura_util,
            espaco=espaco,
            com_o_proximo=[bloco.com_o_proximo for bloco in self.blocos],
        )

        for indice, pagina in enumerate(self.paginas):
            if indice:
                dispositivo.newPage()
            self._margens(pintor, pagina, largura, altura, corpo)
            for pedaco in pagina.pedacos:
                self._pedaco(pintor, pedaco, desenhos, alto, largura)
        return len(self.paginas)

    def _fontes(self, pintor: QPainter) -> tuple[QFont, QFont, QFontMetricsF]:
        """As duas fontes e a métrica do corpo, já no dispositivo em que se está pintando."""
        corpo = QFont(pintor.font())
        corpo.setPointSizeF(CORPO_PT)
        titulo = QFont(corpo)
        titulo.setPointSizeF(TITULO_PT)
        titulo.setBold(True)
        return corpo, titulo, QFontMetricsF(corpo, pintor.device())

    def _medir(
        self, bloco: Bloco, largura: float, corpo: QFont, titulo: QFont, medida: QFontMetricsF
    ) -> tuple[QTextLayout | None, list[float], float]:
        """Aquele bloco medido: o texto já quebrado em linhas, as alturas, e o lado do diagrama.

        O diagrama devolve `None` e **uma** altura: ele é uma linha só, e é o que faz a regra de
        "não se parte" cair de graça na paginação -- não há onde parti-lo.
        """
        if bloco.tipo == DIAGRAMA:
            lado = largura * LARGURA_DO_DIAGRAMA
            return None, [lado], lado
        fonte = QFont(titulo if bloco.tipo == TITULO else corpo)
        if bloco.tipo == VARIANTE:
            fonte.setItalic(True)
        elif bloco.tipo not in (TITULO, COMENTARIO_DO_ESTUDO):
            # A linha principal em negrito, como o livro imprime: é ela que se segue com o dedo.
            fonte.setBold(True)
        recuo = self._recuo(bloco, medida)
        disposicao, alturas = _disposto(bloco.texto, fonte, largura, recuo=recuo)
        return disposicao, alturas, 0.0

    def _recuo(self, bloco: Bloco, medida: QFontMetricsF) -> float:
        """O recuo da variante, em pixels do dispositivo. Zero para todo o resto.

        A métrica vem de fora e é a do **dispositivo**: uma `QFontMetricsF(fonte)` sem device mede
        na resolução da tela, e a 300 pontos por polegada o recuo sairia sete vezes menor -- um
        degrau de meio milímetro, que na folha não é degrau nenhum.
        """
        if bloco.tipo != VARIANTE:
            return 0.0
        return medida.horizontalAdvance("0") * RECUO_DA_VARIANTE * max(1, bloco.nivel)

    def _pedaco(
        self,
        pintor: QPainter,
        pedaco: Pedaco,
        desenhos: list[tuple[QTextLayout | None, list[float], float]],
        alto: float,
        largura: float,
    ) -> None:
        """Um pedaço de bloco na página: as linhas que a paginação escolheu, ou o diagrama."""
        disposicao, alturas, lado = desenhos[pedaco.bloco]
        topo = alto + pedaco.topo
        if disposicao is None:
            self._diagrama(pintor, self.blocos[pedaco.bloco], topo, lado, largura)
            return
        primeira = disposicao.lineAt(pedaco.de)
        recuo = QPointF(0.0, topo - primeira.position().y())
        for indice in range(pedaco.de, min(pedaco.ate, len(alturas))):
            disposicao.lineAt(indice).draw(pintor, recuo)

    def _diagrama(self, pintor: QPainter, bloco: Bloco, topo: float, lado: float, largura: float) -> None:
        """O tabuleiro em vetor, centrado na coluna. Ver o cabeçalho: `QSvgRenderer`, não `QPixmap`."""
        texto = svg_da_posicao(
            bloco.fen,
            virado=bloco.virado,
            cores=cores_da_pele(PADRAO),
            titulo=self.titulo,
        )
        renderizador = QSvgRenderer(QByteArray(texto.encode("utf-8")))
        if not renderizador.isValid():
            logger.warning("O diagrama %d não desenhou na folha: SVG recusado.", bloco.numero)
            return
        renderizador.render(pintor, QRectF((largura - lado) / 2, topo, lado, lado))

    def _margens(self, pintor: QPainter, pagina: Pagina, largura: float, altura: float, corpo: QFont) -> None:
        """O cabeçalho e o rodapé, nas faixas que a área útil deixou livres.

        **Os dois saem pelo mesmo `QTextLayout` do corpo, e não por `drawText`.** Não é gosto: na
        pré-visualização o `QPrintPreviewWidget` grava a página num `QPicture` e a repinta com um
        pintor cuja caneta é a da **paleta do widget**, e um `drawText` que herda a caneta sai com
        a cor do cromo. Medido em 2026-09-05 na pele Foco: o título e o número da página saíam em
        `#e9eaec` -- cinza claro sobre papel branco --, e o corpo saía preto, porque `_disposto`
        carimba a tinta em cada trecho e o carimbo sobrevive à regravação. A folha é papel, e a
        prévia é justamente onde se confere a folha antes de gastar impressão.
        """
        fonte = QFont(corpo)
        fonte.setPointSizeF(CORPO_PT * 0.85)
        acima = cabecalho(self.titulo, pagina.numero)
        if acima:
            disposicao, _alturas = _disposto(acima, fonte, largura)
            disposicao.draw(pintor, QPointF(0.0, 0.0))
        disposicao, alturas = _disposto(
            rodape(pagina.numero, len(self.paginas)), fonte, largura, alinhamento=Qt.AlignmentFlag.AlignHCenter
        )
        disposicao.draw(pintor, QPointF(0.0, altura - sum(alturas)))


def pdf_do_estudo(estudo: Estudo, caminho: Path, *, titulo: str = "") -> int:
    """Grava o estudo como PDF paginado e devolve quantas páginas saíram.

    A4 cravado, e não o papel do sistema: um PDF é lido na tela e impresso em qualquer lugar, e o
    tamanho de página do último driver instalado não é uma escolha de quem exporta. Quem imprime
    escolhe o papel na caixa do sistema, que é onde a escolha existe -- ver
    `abrir_previa_de_impressao`.
    """
    escritor = QPdfWriter(str(caminho))
    escritor.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    escritor.setPageMargins(QMarginsF(MARGEM_MM, MARGEM_MM, MARGEM_MM, MARGEM_MM), QPageLayout.Unit.Millimeter)
    escritor.setResolution(RESOLUCAO_DO_PDF)
    folha = FolhaDoEstudo(estudo, titulo=titulo)
    escritor.setTitle(folha.titulo)
    escritor.setCreator("ChessVisionOFF")
    return folha.desenhar(escritor)


def abrir_previa_de_impressao(
    parent: QWidget | None, estudo: Estudo, *, titulo: str = "", mostrar: bool = True
) -> QPrintPreviewDialog:
    """A pré-visualização paginada, com a caixa de impressão do sistema atrás dela.

    **Prévia e não impressão direta**, e é o critério do item: a quebra de página é a decisão que
    este trabalho toma por quem imprime, e ela tem de ser conferível **antes** de gastar folha. A
    caixa de escolher impressora vem depois, pelo botão da própria prévia.

    `mostrar=False` não chama `exec()`; é o caminho do teste sob `offscreen`, como em
    `qt/fila_de_livros.abrir_fila_de_livros`. A prévia já desenha uma vez ao ser montada, então o
    teste tem o que afirmar sem abrir janela modal.
    """
    impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
    impressora.setPageMargins(QMarginsF(MARGEM_MM, MARGEM_MM, MARGEM_MM, MARGEM_MM), QPageLayout.Unit.Millimeter)
    folha = FolhaDoEstudo(estudo, titulo=titulo)
    impressora.setDocName(folha.titulo)
    dialogo = QPrintPreviewDialog(impressora, parent)
    dialogo.setWindowTitle("Imprimir o estudo")
    # O sinal manda **a impressora** que a prévia quer pintar, e não a que foi passada: ela usa
    # uma cópia com a resolução da tela para desenhar a miniatura. Pintar a de fora encheria a
    # janela de nada, que é o defeito clássico deste diálogo.
    dialogo.paintRequested.connect(folha.desenhar)
    # **As duas referências são obrigatórias, e a segunda derruba o processo quando falta.**
    # `QPrinter` não é um `QObject`: o diálogo guarda o ponteiro dele e **não** vira dono, então
    # a impressora local morre com esta função e o `show()` seguinte pinta sobre memória liberada
    # -- violação de acesso, sem exceção, medida em 2026-09-05. A folha é o outro lado do mesmo
    # cuidado: o `connect` a um método de objeto que não é `QObject` não o mantém vivo. É a razão
    # de `_VIVAS` em `qt/trabalho.py`, aplicada a um diálogo.
    dialogo.impressora = impressora  # type: ignore[attr-defined]
    dialogo.folha = folha  # type: ignore[attr-defined]
    if mostrar:
        dialogo.exec()
    return dialogo
