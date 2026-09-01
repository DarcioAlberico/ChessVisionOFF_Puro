"""O tabuleiro que se corrige: clique, arrasto e pincel sobre um `BoardModel` (S-20/S-49/S-502).

**A máquina de estados não é reescrita, e é o item.** `ui/board_model.BoardModel` tem as 64
casas, a seleção, o pincel e o que cada gesto produz -- `press`, `drop`, `paint`, `erase`,
`select` --, e devolve um `BoardChange` dizendo *o que mudou e quais casas precisam ser
redesenhadas*. É puro, está em `SEM_TKINTER`, e tem teste sem janela desde a S-49. O
`InteractiveBoard` do Tk é um desenhador e um roteador de eventos por cima dele, e este arquivo é
o mesmo papel com outro toolkit.

O que se escreve aqui, então, são três coisas: traduzir clique do Qt em chamada do modelo,
desenhar os quatro sinais que a edição acrescenta (seleção, casa corrigida, casa problemática,
peça sendo arrastada) e emitir sinal quando a posição muda.

**Por que herda de `TabuleiroQt` em vez de repetir o desenho.** A base já sabe enquadrar com
`BoardGeometry.fit`, pintar casa clara e escura, desenhar as doze peças com reserva em glifo e
tingir a casa duvidosa com a rampa do produto. Editar não muda nada disso -- muda o que se
desenha **por cima** e o que acontece ao clicar. Duas cópias do desenho divergiriam no primeiro
conjunto de peças novo.

**A regra de lance fica de fora, e é a S-20.** Corrigir um OCR não é jogar: quem corrige precisa
pôr um bispo preto em h1 se foi isso que o livro imprimiu, e vai precisar -- metade das correções
é peça na casa errada ou com a cor trocada. `board_edit` opera sobre o campo de peças da FEN
justamente por isso, e o modo deste widget é `"edit"`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from PyQt6.QtCore import QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.qt import tema
from chess_diagram_ocr.qt.tabuleiro import TabuleiroQt
from chess_diagram_ocr.ui import board_edit, tokens
from chess_diagram_ocr.ui.board_model import BoardChange, BoardModel, ChangeKind
from chess_diagram_ocr.ui.desenho_do_tabuleiro import BoardGeometry

logger = logging.getLogger(__name__)

__all__ = ["LIMIAR_DE_ARRASTO", "TabuleiroEditavel"]

LIMIAR_DE_ARRASTO = 0.25
"""Quanto o ponteiro precisa andar, em fração da casa, para o gesto virar arrasto.

É o `DRAG_THRESHOLD` de `ui/board_widget.py`, e o número importa nos dois sentidos: pequeno
demais faz todo clique virar arrasto de um pixel e a peça piscar; grande demais faz o arrasto
curto -- de e4 para e5 -- não ser reconhecido, e a peça volta para onde estava."""

LARGURA_DO_CONTORNO = 0.06
"""Espessura dos anéis de seleção e de correção, em fração da casa. Acompanha o zoom."""


class TabuleiroEditavel(TabuleiroQt):
    """Um tabuleiro que se corrige. Emite `posicao_mudou` quando o campo de peças muda.

    O sinal carrega o campo de peças novo, e não o widget: quem ouve é a janela, que precisa
    guardar a correção no `DiagramEditorModel` e reacender o botão de salvar. Passar o widget
    obrigaria quem ouve a perguntar de volta, e é assim que dois estados se separam.
    """

    posicao_mudou = pyqtSignal(str)
    selecao_mudou = pyqtSignal(object)
    """A casa selecionada, ou `None`. `object` e não `int` porque `None` é uma resposta legítima
    -- é "nada selecionado", e um sinal de `int` a converteria em zero, que é a casa a8."""

    recado = pyqtSignal(str)
    """O que o modelo tem a dizer sem mudar nada -- `BoardChange.message`. Vai para o rodapé."""

    def __init__(self, parent: QWidget | None = None, **opcoes: object) -> None:
        super().__init__(parent, **opcoes)  # type: ignore[arg-type]
        self.modelo = BoardModel(mode="edit")
        self._arrastando = False
        self._arrasto_de: int | None = None
        self._arrasto_simbolo = ""
        self._ponteiro = QPoint()
        self._inicio = QPoint()
        self._selecionou_agora = False
        self.setMouseTracking(False)

    # ------------------------------------------------------------------------------ estado

    def mostrar(self, placement: str, **opcoes: object) -> None:
        """Desenha um campo de peças **e o carrega no modelo**, para poder ser editado.

        A base guarda as 64 classes para desenhar; o modelo guarda a posição para o clique
        operar sobre ela. Manter os dois é o que evita a pergunta "qual dos dois é a verdade?"
        no meio de uma correção -- a resposta é o modelo, e a base é reescrita a partir dele.
        """
        super().mostrar(placement, **opcoes)  # type: ignore[arg-type]
        self.modelo.set_position(board_edit.placement_of(placement))
        # **`virado` tem uma fonte de verdade só.** A base guarda `_virado` para desenhar e o
        # modelo guarda `flipped` para traduzir clique em casa; deixar os dois seguirem sozinhos
        # daria um tabuleiro em que a peça aparece em cima e o clique acerta embaixo.
        self.modelo.flipped = self._virado
        self.modelo.select(None)

    def posicao(self) -> str:
        """O campo de peças como ele está agora, com as correções. É o que se grava."""
        return self.modelo.placement

    def selecionada(self) -> int | None:
        return self.modelo.selected

    def definir_pincel(self, simbolo: str | None) -> str | None:
        """Peça que o próximo clique insere. `""` apaga, `None` volta ao modo arrastar.

        Devolve o pincel que ficou valendo e manda a frase de status por `recado` -- é o que
        `board_widget.set_brush` faz com `self._status(mensagem)`, com o sinal no lugar da
        chamada.

        **Não alterna, e a ausência é fidelidade.** Clicar no botão já aceso para *largar* o
        pincel é gesto de paleta, e no Tk ele mora em `board_widget._on_palette_click` -- lá
        porque `Radiobutton` reafirma o mesmo valor em silêncio. Pôr o alternador aqui daria
        duas regras para a mesma pergunta no dia em que a paleta do Qt existir.
        """
        self.recado.emit(self.modelo.set_brush(simbolo))
        self.update()
        return self.modelo.brush

    def definir_casas_corrigidas(self, casas: Iterable[int]) -> None:
        """As casas em que a correção manual discorda do que o modelo leu (S-11)."""
        self.modelo.set_changed_squares(casas)
        self.update()

    def definir_casas_problematicas(self, casas: Iterable[int]) -> None:
        """As casas que tornam a posição ilegal. Vermelho, e por cima da correção."""
        self.modelo.set_problem_squares(casas)
        self.update()

    def apagar_selecionada(self) -> bool:
        """`Del`: tira a peça da casa selecionada. `False` quando não havia o que apagar."""
        return self._aplicar(self.modelo.erase_selected())

    # ------------------------------------------------------------------------- interação

    def _casa_em(self, ponto: QPoint) -> int | None:
        """O índice em ordem de leitura sob o ponteiro, ou `None` fora do tabuleiro."""
        alvo = self.geometria().display_at(ponto.x(), ponto.y())
        return None if alvo is None else self.modelo.index_from_display(*alvo)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None:
            return
        ponto = a0.position().toPoint()
        if a0.button() == Qt.MouseButton.RightButton:
            # Botão direito apaga, no modo de edição. É o gesto de `_on_right_press` do Tk, e
            # ele existe porque tirar peça é metade das correções -- pedir "selecione e aperte
            # Del" para isso é dois gestos onde um basta.
            casa = self._casa_em(ponto)
            if casa is not None:
                self._aplicar(self.modelo.erase(casa))
            return
        if a0.button() != Qt.MouseButton.LeftButton:
            return

        self._ponteiro = self._inicio = ponto
        self._arrastando = False
        self._arrasto_de = casa = self._casa_em(ponto)
        self._arrasto_simbolo = ""
        self._selecionou_agora = False
        if casa is None:
            return

        anterior = self.modelo.selected
        mudanca = self.modelo.press(casa)
        if mudanca.touched_position:
            # Pincel: o clique pintou, e não há nada a arrastar.
            self._arrasto_de = None
            self._aplicar(mudanca)
            return
        if mudanca.kind is not ChangeKind.SELECTION:
            return
        self._selecionou_agora = anterior != casa
        self._arrasto_simbolo = board_edit.piece_at(self.modelo.placement, casa)
        self._aplicar(mudanca)

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None or not self._arrasto_simbolo or self._arrasto_de is None:
            return
        self._ponteiro = a0.position().toPoint()
        if not self._arrastando:
            casa = max(1.0, self.geometria().cell)
            andou = max(
                abs(self._ponteiro.x() - self._inicio.x()), abs(self._ponteiro.y() - self._inicio.y())
            )
            if andou < casa * LIMIAR_DE_ARRASTO:
                return
            self._arrastando = True
        self.update()

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        if a0 is None or a0.button() != Qt.MouseButton.LeftButton:
            return
        alvo = self._casa_em(a0.position().toPoint())
        # **A desseleção só vale para um clique que não moveu nada e não acabou de selecionar.**
        # É a regra do Tk, e o que ela evita é o clique que seleciona uma casa e, na mesma
        # descida-subida do botão, a desmarca -- de forma que selecionar exigiria dois cliques.
        permite_desmarcar = (not self._arrastando) and (not self._selecionou_agora)
        mudanca = self.modelo.drop(alvo, allow_deselect=permite_desmarcar)
        self._arrastando = False
        self._arrasto_de = None
        self._arrasto_simbolo = ""
        self._aplicar(mudanca)

    def _aplicar(self, mudanca: BoardChange) -> bool:
        """Redesenha e avisa quem ouve. Devolve se a **posição** mudou.

        O `BoardChange` é quem diz o que aconteceu; este método é a tradução dele para sinais do
        Qt. Redesenhar o widget inteiro em vez das casas de `dirty` é decisão: no Tk cada casa é
        um item de canvas e refazer todas custava caro (S-50), enquanto aqui o `paintEvent`
        pinta 64 retângulos sobre um `QPixmap` já carregado -- e um `update()` parcial obrigaria
        a converter `dirty` em região a cada gesto para economizar o que não custa.
        """
        if mudanca.message:
            self.recado.emit(mudanca.message)
        if mudanca.kind is ChangeKind.NONE:
            return False
        self.update()
        if mudanca.kind is ChangeKind.SELECTION:
            self.selecao_mudou.emit(self.modelo.selected)
            return False
        if mudanca.touched_position:
            self._classes = self._classes_do_modelo()
            self.selecao_mudou.emit(self.modelo.selected)
            self.posicao_mudou.emit(self.modelo.placement)
            return True
        return False

    def _classes_do_modelo(self) -> list[str]:
        """As 64 classes que a base desenha, tiradas do modelo.

        `""` é casa vazia em `board_edit` e `"empty"` na tabela de classes do projeto -- a
        tradução é aqui porque é a fronteira entre os dois vocabulários, e espalhá-la faria
        cada ponto de desenho escolher o seu.
        """
        return [simbolo or "empty" for simbolo in self.modelo.squares()]

    # ------------------------------------------------------------------------------ desenho

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 - assinatura do Qt
        super().paintEvent(a0)
        pintor = QPainter(self)
        geo = self.geometria()
        self._desenhar_marcas(pintor, geo)
        self._desenhar_arrasto(pintor, geo)
        pintor.end()

    def _retangulo(self, geo: BoardGeometry, indice: int) -> QRectF:
        linha, coluna = self.modelo.display_from_index(indice)
        x0, y0, x1, y1 = geo.rect(linha, coluna)
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def _anel(self, pintor: QPainter, geo: BoardGeometry, indice: int, cor: str, *, tracejado: bool = False) -> None:
        caneta = QPen(QColor(cor))
        caneta.setWidthF(max(2.0, geo.cell * LARGURA_DO_CONTORNO))
        if tracejado:
            caneta.setStyle(Qt.PenStyle.DashLine)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        folga = caneta.widthF() / 2.0
        pintor.drawRect(self._retangulo(geo, indice).adjusted(folga, folga, -folga, -folga))

    def _desenhar_marcas(self, pintor: QPainter, geo: BoardGeometry) -> None:
        """Seleção, casa corrigida e casa problemática -- **nesta ordem, e ela é a do Tk**.

        As três podem acender na mesma casa, e a última desenhada é a que se vê inteira. A
        problemática vem por último de propósito: "esta casa torna a posição ilegal" é o que
        precisa ser lido primeiro, e "eu corrigi esta casa" é o que a pessoa já sabe.
        """
        for indice in sorted(self.modelo.changed):
            self._anel(pintor, geo, indice, tema.cor_atual(tokens.CORRIGIDO), tracejado=True)
        for indice in sorted(self.modelo.problems):
            self._anel(pintor, geo, indice, tema.cor_atual(tokens.PROBLEMA))
        if self.modelo.selected is not None:
            self._anel(pintor, geo, self.modelo.selected, tema.cor_atual(tokens.CONTORNO_DE_SELECAO))

    def _desenhar_arrasto(self, pintor: QPainter, geo: BoardGeometry) -> None:
        """A peça acompanhando o ponteiro, centrada nele e por cima de tudo.

        Meia opacidade não: a peça arrastada é a que se está mirando, e apagá-la pela metade
        para "mostrar o que está embaixo" mostra o que não interessa. O que a origem faz é
        deixar de desenhar a peça enquanto o arrasto dura -- ver `_classes_em_arrasto`.
        """
        if not self._arrastando or not self._arrasto_simbolo:
            return
        mapa = self._pecas.get(self._arrasto_simbolo)
        if mapa is None:
            return
        lado = geo.cell
        alvo = QRectF(self._ponteiro.x() - lado / 2, self._ponteiro.y() - lado / 2, lado, lado)
        pintor.drawPixmap(alvo.toRect(), mapa)

    def _classes_em_arrasto(self) -> list[str]:
        """As classes com a origem do arrasto vazia, para a peça não aparecer duas vezes."""
        classes = list(self._classes)
        if self._arrastando and self._arrasto_de is not None:
            classes[self._arrasto_de] = "empty"
        return classes

    def _classe_da_casa(self, indice: int) -> str:
        """O gancho da base, para esconder a peça que está sendo arrastada na casa de origem."""
        return self._classes_em_arrasto()[indice]

    def pixmap_da_peca(self, classe: str) -> QPixmap | None:
        """Existe para o teste conferir que a peça arrastada é a que saiu da casa de origem."""
        return self._pecas.get(classe)

    def casas_marcadas(self) -> dict[str, tuple[int, ...]]:
        """O que está aceso agora, por papel. Existe para o teste afirmar o que a tela diz."""
        return {
            "selecionada": () if self.modelo.selected is None else (self.modelo.selected,),
            "corrigidas": tuple(sorted(self.modelo.changed)),
            "problematicas": tuple(sorted(self.modelo.problems)),
        }
