"""A disposição de mesa da janela: o divisor com os lados trocados (S-640/S-645).

**Quando** a mesa vale é de `ui/mesa.py`; este módulo é o que a executa sobre o `QSplitter` da
janela -- trocar os dois lados de ordem, dar a cada disposição a sua alça, e devolver ao
visualizador a rolagem que a largura nova reflui. Mora fora de `qt/janela.py` porque a janela tem
teto de linhas (S-31, `tests/test_packaging.py`) e porque nada disto pergunta à janela outra coisa
além dos três widgets.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QAbstractScrollArea, QSplitter, QWidget

from chess_diagram_ocr.ui import geometria, mesa
from chess_diagram_ocr.ui.state import AppState

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

__all__ = ["DisposicaoDeMesa"]


class DisposicaoDeMesa:
    """Os dois lados do divisor da janela, na ordem de antes ou na da mesa."""

    def __init__(
        self,
        divisor: QSplitter,
        *,
        trabalho: QWidget,
        livro: QWidget,
        visor: QAbstractScrollArea,
        estado: AppState,
        texto_a_frente: Callable[[], bool],
        texto: PainelDeTexto | None = None,
    ) -> None:
        self._divisor = divisor
        self._texto = texto
        """A aba Texto. Com a mesa armada ela acompanha a página do visualizador e mostra o bloco
        impresso (S-643, S-644), e a folha e o texto apontam um para o outro (S-642): o bloco sob o
        cursor ganha contorno na folha, e o clique na folha põe o cursor no bloco."""
        if texto is not None:
            texto.bloco_destacado.connect(self._destacar)
            # O modo foco esconde o visualizador e o devolve (S-658).
            texto.foco_mudou.connect(lambda ligado: self._livro.setVisible(not ligado))
            ponto = getattr(visor, "ponto_clicado", None)
            if ponto is not None:
                ponto.connect(self._clicou_na_folha)
        self._texto_a_frente = texto_a_frente
        """A pergunta "a aba Texto está à frente?" -- é da janela, que sabe onde cada área mora."""
        self._trabalho = trabalho
        self._livro = livro
        self._visor = visor
        self._estado = estado
        self.armada = False
        """O divisor está na disposição de mesa -- o livro à esquerda, o trabalho à direita."""
        self._fracao_de_antes: float | None = None
        """A alça da disposição de antes, guardada ao entrar na mesa para voltar a ela."""

    def arrumar(self, *_: object) -> None:
        """Arma ou desarma conforme a área à frente, a preferência e a largura -- só se mudou.

        Slot da troca de modo e de aba, e chamado na primeira aparição da janela. **Só com a janela
        mostrada**: antes do `show()` a largura é a da montagem, e a mesa decide pela largura.
        """
        janela = self._divisor.window()
        if janela is None or not janela.isVisible():
            return
        quer = mesa.vale_a_mesa(self._estado.texto_mesa, texto_a_frente=self._texto_a_frente(), largura=janela.width())
        if quer != self.armada:
            self._trocar(para_a_mesa=quer)

    @property
    def ligada(self) -> bool:
        """A preferência liga a mesa ao abrir o Texto? É o que o interruptor do menu mostra."""
        return mesa.ligada(self._estado.texto_mesa)

    def alternar(self) -> bool:
        """O interruptor do menu Texto: a mesa ao abrir o Texto, ou nunca. Devolve se ficou ligada."""
        ligada = not self.ligada
        self._estado.texto_mesa = mesa.MESA_AO_ABRIR_O_TEXTO if ligada else mesa.MESA_NUNCA
        self.arrumar()
        return ligada

    def _destacar(self, bbox: object) -> None:
        destacar = getattr(self._visor, "definir_destaque", None)
        if destacar is not None:
            destacar(bbox if self.armada else None)

    def _clicou_na_folha(self, x: float, y: float) -> None:
        if self.armada and self._texto is not None:
            self._texto.ir_ao_ponto(x, y)

    def anotar(self, *, escolhida: bool = True) -> None:
        """Põe as duas alças no estado, cada uma na sua chave (S-156/S-640).

        Na mesa, a alça à esquerda é a do PDF: ela vai para `mesa_fraction`, e `sash_fraction`
        fica com a que a disposição de antes tinha -- gravar a da mesa por cima abriria a sessão
        seguinte com a coluna do trabalho do tamanho que o PDF tinha aqui.

        **`escolhida=False` não grava a alça do trabalho** (S-552): é a repartição de fábrica, e
        gravá-la a faria valer como decisão de alguém na sessão seguinte. A da mesa grava sempre
        -- ela nunca é a de fábrica da janela, é a de `mesa.fracao_da_mesa`.
        """
        tamanhos = self._divisor.sizes()
        if len(tamanhos) < 2 or sum(tamanhos) <= 0:
            return
        fracao = geometria.fracao_de_divisor(tamanhos[0], sum(tamanhos))
        if not self.armada:
            if escolhida:
                self._estado.sash_fraction = fracao
            return
        self._estado.mesa_fraction = fracao
        if self._fracao_de_antes and escolhida:
            self._estado.sash_fraction = self._fracao_de_antes

    def _trocar(self, *, para_a_mesa: bool) -> None:
        """Troca a ordem dos lados **sem desorientar quem lê**.

        Os dois widgets são os mesmos -- o `QSplitter` só muda a ordem --, então a página aberta e o
        zoom do visualizador ficam; a rolagem é devolvida pela fração em que estava, porque a largura
        nova reflui a página.
        """
        tamanhos = self._divisor.sizes()
        total = sum(tamanhos) or self._divisor.width()
        barra = self._visor.verticalScrollBar()
        rolagem = barra.value() / barra.maximum() if barra is not None and barra.maximum() > 0 else None
        medido = total > 0 and len(tamanhos) >= 2
        if para_a_mesa:
            if medido:
                self._fracao_de_antes = geometria.fracao_de_divisor(tamanhos[0], total)
            self._divisor.insertWidget(0, self._livro)
            fracao = mesa.fracao_da_mesa(self._estado.mesa_fraction)
        else:
            if medido:
                self._estado.mesa_fraction = geometria.fracao_de_divisor(tamanhos[0], total)
            self._divisor.insertWidget(0, self._trabalho)
            fracao = self._fracao_de_antes or self._estado.sash_fraction or mesa.FRACAO_PADRAO
        # O trabalho continua o lado que cresce menos, como na montagem: o fator segue o widget.
        self._divisor.setStretchFactor(self._divisor.indexOf(self._trabalho), 2)
        self._divisor.setStretchFactor(self._divisor.indexOf(self._livro), 3)
        if total > 0:
            esquerda = max(1, int(total * fracao))
            self._divisor.setSizes([esquerda, max(1, total - esquerda)])
        self.armada = para_a_mesa
        if self._texto is not None:
            self._texto.definir_mesa(para_a_mesa)
            if not para_a_mesa:
                self._destacar(None)
        if rolagem is not None and barra is not None:
            barra.setValue(round(rolagem * barra.maximum()))
