"""O tabuleiro desenhado com `QPainter`, a partir do campo de peças da FEN.

**O que é reusado e o que não.** As cores, a geometria e a rampa de calor são as mesmas do
produto -- `ui/tokens.py` e `ui/desenho_do_tabuleiro.py`, os dois sem toolkit de propósito -- e as
peças são os mesmos PNGs de `assets/piece_images/`. O que este módulo escreve do zero é o desenho,
e só ele.

**O achado deste arquivo foi fechado na S-501, e vale registrar o que ele era.** Até então o
cabeçalho dizia:

    `ui/board_render.py` tem duas coisas que este arquivo gostaria: `BoardGeometry.fit` e
    `heatmap_color`. As duas são cálculo puro -- e mesmo assim não dá para importá-las, porque o
    módulo em que moram importa `tkinter` e `PIL` na primeira linha. É o único ponto do fluxo em
    que o segundo frontend teve de repetir uma decisão em vez de chamá-la, e é por isso que a
    incerteza aqui aparece como **contorno** na casa e não como calor.

As duas mudaram para `ui/desenho_do_tabuleiro.py`, que não importa nem um nem outro, e este
arquivo passou a chamá-las. A incerteza voltou a ser calor, `UNICODE_PIECES` deixou de existir em
duas cópias, e o enquadramento é o mesmo `BoardGeometry.fit` que o produto usa -- o que significa
que o tabuleiro das duas janelas, na mesma área, tem o mesmo tamanho e a mesma origem.

**A tinta da incerteza tem alfa aqui, e não `stipple`.** O `BoardRenderer` do Tk pinta a casa
quente com `stipple="gray50"` e explica por quê: *"é o único jeito de tingir sem apagar a casa no
canvas do Tk, que não tem canal alfa"*. O Qt tem, então a mesma decisão -- tingir sem esconder a
peça -- é cumprida com meia opacidade de verdade, e não com uma trama de pixels alternados.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.config import BUNDLE_ROOT, IDX_TO_CLASS, UNCERTAIN_SQUARE_THRESHOLD
from chess_diagram_ocr.fen_utils import labels_from_fen
from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.desenho_do_tabuleiro import (
    GLIFO_CLARO,
    GLIFO_ESCURO,
    UNICODE_PIECES,
    BoardGeometry,
    heatmap_color,
)

PASTA_DE_PECAS = BUNDLE_ROOT / "assets" / "piece_images"
"""Os mesmos PNGs do produto. `BUNDLE_ROOT` e não `PROJECT_ROOT` porque peça é recurso
somente-leitura que viaja dentro do pacote -- a distinção é da S-55."""

LADO_MINIMO = 240
MAX_DO_TABULEIRO = 560
"""O piso e o teto do tabuleiro, em pixel. **São os do produto** (`ui/board_widget.py`).

Eram 220 e teto nenhum. Alinhar não é zelo: os dois entram em `BoardGeometry.fit`, e com números
diferentes a mesma posição na mesma área desenharia um tabuleiro de tamanho diferente em cada
janela -- o que faz "comparar as duas telas lado a lado" deixar de responder, que é justamente
para o que a versão de teste existe."""

MARGEM = 8
"""Folga em volta. É o mesmo `margin` que `board_widget` passa quando não desenha coordenadas --
e este tabuleiro não desenha."""

GLIFOS = UNICODE_PIECES
"""O desenho de reserva, quando o PNG da peça não está no disco.

Existe porque `assets/piece_images/` **não** é obrigatório: um checkout sem os artefatos de
dados abre a janela, e um tabuleiro em branco não diria se o que faltou foi a leitura ou a
imagem. O glifo Unicode responde essa pergunta sem depender de arquivo nenhum.

**É `desenho_do_tabuleiro.UNICODE_PIECES`, e não uma tabela própria** (S-501). Era uma cópia byte
a byte da de lá -- doze pares iguais, mantidos em dois lugares. O nome fica como apelido porque é
por ele que este módulo e o teste se referem à tabela."""

TINTA_DA_INCERTEZA = 128
"""Quanto da tinta quente cobre a casa, de 0 a 255. Meia opacidade.

É o `stipple="gray50"` do `BoardRenderer` dito com o canal alfa que o Tk não tem: metade da tinta,
para a peça por baixo continuar legível. Ver o cabeçalho."""


def arquivo_da_peca(classe: str) -> str:
    """`"P"` -> `"wp"`, `"n"` -> `"bn"`. O nome do PNG, que é cor + tipo em minúscula."""
    return ("w" if classe.isupper() else "b") + classe.lower()


def carregar_pecas(pasta: Path = PASTA_DE_PECAS) -> dict[str, QPixmap]:
    """As doze peças, lidas uma vez. Ausente sai de fora do dicionário, e não vazia.

    Um `QPixmap` nulo desenha nada e não levanta: se ele entrasse aqui, o tabuleiro ficaria
    vazio sem que ninguém pudesse dizer por quê. Fora do dicionário, o desenho cai no glifo.
    """
    imagens: dict[str, QPixmap] = {}
    for classe in GLIFOS:
        caminho = Path(pasta) / f"{arquivo_da_peca(classe)}.png"
        if not caminho.exists():
            continue
        mapa = QPixmap(str(caminho))
        if not mapa.isNull():
            imagens[classe] = mapa
    return imagens


class TabuleiroQt(QWidget):
    """Um tabuleiro somente-leitura: mostra o que o modelo leu, e não deixa editar.

    **Somente-leitura de propósito.** Editar casa a casa é o que a aba Resultado do produto
    faz, e ela grava amostra no `labels.csv` -- trabalho humano, com desfazer, quarentena e
    procedência. Uma segunda tela que escrevesse no mesmo arquivo não seria uma versão de
    teste: seria um segundo caminho de escrita sobre o dado que o projeto mais protege.
    """

    def __init__(self, parent: QWidget | None = None, *, pasta_de_pecas: Path = PASTA_DE_PECAS) -> None:
        super().__init__(parent)
        self._pecas = carregar_pecas(pasta_de_pecas)
        self._classes: list[str] = ["empty"] * 64
        self._incertas: set[int] = set()
        self._confiancas: dict[int, float] = {}
        self._limiar = UNCERTAIN_SQUARE_THRESHOLD
        self._virado = False
        self.setMinimumSize(LADO_MINIMO, LADO_MINIMO)

    # ------------------------------------------------------------------------------ estado

    def mostrar(
        self,
        placement: str,
        *,
        incertas: Sequence[int] = (),
        confiancas: Sequence[float] = (),
        limiar: float = UNCERTAIN_SQUARE_THRESHOLD,
        virado: bool = False,
    ) -> None:
        """Desenha um campo de peças. FEN inválida **levanta**, e não vira tabuleiro vazio.

        É a mesma decisão da S-361 em `labels_from_fen`, e pelo mesmo motivo: uma leitura ruim
        que vira 64 casas vazias é indistinguível de uma posição sem peças, e quem olha a tela
        conclui que o modelo não achou nada quando o que houve foi um caractere que ninguém
        soube ler.

        **`incertas` diz *quais* casas, `confiancas` diz *quão* quentes** -- e as duas são
        separadas porque quem chama já tem a primeira pronta (`RecognizedDiagram.uncertain_squares`)
        e nem sempre tem a segunda. Sem confiança, a casa marcada sai na cor do **limiar**, que é
        o topo da rampa: dizer "esta casa é duvidosa" sem inventar o quanto.
        """
        self._classes = [IDX_TO_CLASS[indice] for indice in labels_from_fen(placement)]
        self._incertas = {int(casa) for casa in incertas if 0 <= int(casa) < 64}
        self._limiar = float(limiar)
        self._confiancas = {
            casa: float(valor)
            for casa, valor in enumerate(confiancas)
            if casa in self._incertas
        }
        self._virado = bool(virado)
        self.update()

    def limpar(self) -> None:
        self._classes = ["empty"] * 64
        self._incertas = set()
        self._confiancas = {}
        self.update()

    @property
    def virado(self) -> bool:
        return self._virado

    def casas_incertas(self) -> tuple[int, ...]:
        """As casas marcadas, em ordem de leitura. Existe para o teste afirmar o que a tela diz."""
        return tuple(sorted(self._incertas))

    # ------------------------------------------------------------------------------ desenho

    def _indice_de_leitura(self, linha: int, coluna: int) -> int:
        """Da posição na tela para o índice em ordem de leitura (0 = a8), respeitando o giro."""
        return (7 - linha) * 8 + (7 - coluna) if self._virado else linha * 8 + coluna

    def _classe_da_casa(self, indice: int) -> str:
        """Que peça desenhar naquela casa. **Gancho, e é para isso que ele existe.**

        A subclasse que edita precisa esconder a peça que está sendo arrastada -- ela aparece
        sob o ponteiro, e desenhá-la também na casa de origem a mostraria duas vezes. Sem este
        método, a única saída seria trocar `self._classes` antes de pintar e repor depois, que
        é estado temporário num atributo que o resto da classe lê como se fosse permanente.
        """
        return self._classes[indice]

    def geometria(self) -> BoardGeometry:
        """Onde o tabuleiro está dentro do widget. **A mesma conta do produto** (S-155/S-501).

        Pública porque quem precisa dela não é só o `paintEvent`: o teste que amostra a cor de uma
        casa precisa saber onde a casa está, e recalculá-la do lado de fora é como se escreve um
        teste que continua passando depois de o enquadramento mudar.
        """
        return BoardGeometry.fit(
            self.width(),
            self.height(),
            min_size=LADO_MINIMO,
            max_size=MAX_DO_TABULEIRO,
            margin=MARGEM,
        )

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pintor.fillRect(self.rect(), QColor(tema.cor_atual(tokens.SUPERFICIE_TABULEIRO)))

        geo = self.geometria()
        clara = QColor(tema.cor_atual(tokens.CASA_CLARA))
        escura = QColor(tema.cor_atual(tokens.CASA_ESCURA))
        for linha in range(8):
            for coluna in range(8):
                x0, y0, x1, y1 = geo.rect(linha, coluna)
                retangulo = QRectF(x0, y0, x1 - x0, y1 - y0)
                indice = self._indice_de_leitura(linha, coluna)
                pintor.fillRect(retangulo, clara if (linha + coluna) % 2 == 0 else escura)
                self._desenhar_peca(pintor, retangulo, self._classe_da_casa(indice))
                self._desenhar_incerteza(pintor, retangulo, indice)

        pintor.end()

    def _desenhar_peca(self, pintor: QPainter, casa: QRectF, classe: str) -> None:
        if classe == "empty":
            return
        mapa = self._pecas.get(classe)
        if mapa is not None:
            pintor.drawPixmap(casa.toRect(), mapa)
            return
        fonte = QFont(pintor.font())
        fonte.setPointSizeF(max(6.0, casa.height() * 0.72))
        pintor.setFont(fonte)
        pintor.setPen(QPen(QColor(GLIFO_ESCURO if classe.islower() else GLIFO_CLARO)))
        pintor.drawText(casa, int(Qt.AlignmentFlag.AlignCenter), GLIFOS[classe])

    def _desenhar_incerteza(self, pintor: QPainter, casa: QRectF, indice: int) -> None:
        """A casa duvidosa tingida com a rampa de calor, e contornada na mesma cor (S-501).

        **É a mesma rampa do produto**, `desenho_do_tabuleiro.heatmap_color`, e não uma segunda
        escala: duas escalas para "quão duvidosa é esta casa" seria o defeito que a S-31 corrigiu
        no pipeline, reintroduzido no desenho.

        A tinta cobre a peça em vez de ficar embaixo, exatamente como o `BoardRenderer` faz -- é
        o que faz a casa quente se ver mesmo quando há uma dama preta nela. O que muda é o meio:
        alfa de verdade no lugar do `stipple`, e o resultado é uma tinta lisa em vez de uma trama.

        Meio pixel de folga no contorno porque a caneta do Qt pinta centrada na linha: sem ela,
        metade do traço cai na casa vizinha, e duas casas quentes lado a lado dividem um contorno.
        """
        if indice not in self._incertas:
            return
        # Sem confiança medida, a cor é a do **limiar** -- o topo da rampa. Ver `mostrar`.
        confianca = self._confiancas.get(indice, self._limiar)
        tinta = QColor(heatmap_color(confianca, self._limiar))
        preenchimento = QColor(tinta)
        preenchimento.setAlpha(TINTA_DA_INCERTEZA)
        pintor.fillRect(casa, preenchimento)

        caneta = QPen(tinta)
        caneta.setWidthF(max(2.0, casa.width() * 0.06))
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        folga = caneta.widthF() / 2.0
        pintor.drawRect(casa.adjusted(folga, folga, -folga, -folga))
