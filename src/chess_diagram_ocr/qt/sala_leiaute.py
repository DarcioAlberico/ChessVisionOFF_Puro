"""A repartição da sala de estudo: a alça das duas colunas, a da coluna de leitura e o tabuleiro (S-866).

**Saiu de `qt/painel_de_estudo.py` com o estado que só ela usava**: se a alça já foi escolhida, a
largura em que a régua da S-551 rodou por último, a fração do tabuleiro (S-518) e a fila "barra de
avaliação + tabuleiro" onde a esteira se mede. Quem decide a fração é `ui/sala_declarada.py`
(`fracao_para_o_tabuleiro`, `piso_da_leitura`); aqui se mede o que os widgets do painel pedem e se
move a alça. O painel chama `acomodar_o_tabuleiro` no `resizeEvent` e no `showEvent`, e a janela
guarda e devolve as três frações por esta classe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QHBoxLayout

from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
from chess_diagram_ocr.ui import geometria
from chess_diagram_ocr.ui.sala_declarada import FRACAO_PADRAO_DO_TABULEIRO, fracao_para_o_tabuleiro, piso_da_leitura

if TYPE_CHECKING:
    from chess_diagram_ocr.qt.painel_de_estudo import PainelDeEstudo

__all__ = ["LeiauteDaSala"]


class LeiauteDaSala(QObject):
    """Onde ficam as alças da sala, e quanto do tabuleiro cabe na coluna esquerda."""

    def __init__(self, sala: PainelDeEstudo) -> None:
        super().__init__(sala)
        self._sala = sala
        self._fracao_do_tabuleiro = FRACAO_PADRAO_DO_TABULEIRO
        self._divisor_escolhido = False
        """A pessoa (ou a sessão anterior) decidiu onde fica a alça? Ver `acomodar_o_tabuleiro`."""
        self._largura_acomodada = 0
        """A largura em que a régua da S-551 rodou da última vez, em pixel.

        Existe para a régua saber se a coluna está **encolhendo** -- o `QSplitter` já repartiu em
        proporção quando ela roda, e sem esta lembrança "só empurra para a direita" vira "guarda a
        fração de uma janela larga numa estreita". Ver `sala_declarada.fracao_para_o_tabuleiro`."""
        self.faixa_do_tabuleiro: QHBoxLayout | None = None
        """A fila "barra de avaliação + tabuleiro", quando há motor. Guardada porque é nela que se
        mede a esteira da coluna esquerda -- ver `_esteira_da_coluna` (S-551, terceira rodada)."""

    def caixa_do_tabuleiro(self) -> tuple[int, int]:
        """Onde o **tabuleiro desenhado** começa e quanto ele mede, para a barra o acompanhar.

        Perguntado pela barra no `paintEvent` dela, e não guardado num `resizeEvent`: `geometria()`
        é a mesma conta que o tabuleiro usa para se desenhar, e ler o resultado dela na hora é o
        que garante que os dois quadrados coincidam sempre -- inclusive na primeira exibição, em
        que a coluna ainda não tem largura (S-529).
        """
        geo = self._sala.tabuleiro.geometria()
        return int(geo.origin_y), int(geo.size)

    def divisor_movido_a_mao(self, _posicao: int, _indice: int) -> None:
        self._divisor_escolhido = True

    def _altura_livre_para_o_tabuleiro(self) -> int:
        """Quanta altura da coluna esquerda sobraria para o tabuleiro se ele não a disputasse.

        É a altura da coluna menos o que os vizinhos pedem -- cabeçalho, faixa de navegação,
        recorte **visível**, os dois rótulos, a FEN -- e menos os vãos entre eles. O recorte
        escondido não conta, e é a diferença que explica a foto do crítico: com um diagrama do
        livro aberto, os 220 px de `LADO_DO_RECORTE` ocupam justamente o vazio que ele mediu.
        """
        coluna = self._sala.divisor.widget(0)
        leiaute = coluna.layout() if coluna is not None else None
        if coluna is None or leiaute is None:
            return 0
        margens = leiaute.contentsMargins()
        ocupado = margens.top() + margens.bottom()
        vizinhos = 0
        for indice in range(leiaute.count()):
            item = leiaute.itemAt(indice)
            widget = item.widget() if item is not None else None
            if widget is None or widget is self._sala.tabuleiro:
                continue
            if widget.isHidden():
                continue
            ocupado += widget.sizeHint().height()
            vizinhos += 1
        ocupado += leiaute.spacing() * vizinhos
        return max(0, coluna.height() - ocupado)

    def _caixa_minima_do_tabuleiro(self) -> int:
        """O lado mínimo da **caixa** do tabuleiro: o piso do desenho mais a margem da coordenada.

        **A régua trabalha na caixa, e não no quadriculado** (S-551, terceira rodada). Passar
        `LADO_MINIMO` cru dava uma coluna de 245 px para um tabuleiro de 240: `BoardGeometry.fit`
        desenha os 240 -- o `max(min_size, ...)` dela vence --, sobram 2,5 px de cada lado, e a
        régua de linhas, escrita em `origin_x - 11`, cai **fora** do widget. Medido a 1024x768 com
        o motor ligado: as letras `a`..`h` apareciam e os números `1`..`8` não.
        """
        return qt_tabuleiro.LADO_MINIMO + qt_tabuleiro.MARGEM

    def _esteira_da_coluna(self) -> int:
        """Quanto da coluna esquerda **não** é tabuleiro, na horizontal (S-551, terceira rodada).

        As margens da coluna mais, quando há motor, a barra de avaliação e o vão até o tabuleiro.
        Medida e não cravada: são 42 px na base de referência (0 + 6 de margem, 26 da barra e 10 de
        vão), e quem aumentar a fonte do sistema ou trocar a densidade muda os dois últimos.

        Vai por argumento para `sala_declarada`, que é onde a decisão mora: a régua precisa saber
        que a coluna carrega essa esteira, e **de que ela é feita** é assunto do widget.
        """
        coluna = self._sala.divisor.widget(0)
        leiaute = coluna.layout() if coluna is not None else None
        if leiaute is None:
            return 0
        margens = leiaute.contentsMargins()
        esteira = margens.left() + margens.right()
        faixa = self.faixa_do_tabuleiro
        if self._sala.vantagem is not None and faixa is not None:
            esteira += self._sala.vantagem.sizeHint().width() + max(0, faixa.spacing())
        return esteira

    def acomodar_o_tabuleiro(self) -> None:
        """Move a alça para o tabuleiro usar a altura que sobra, se ninguém escolheu a alça.

        **A regra é pura** (`sala_declarada.fracao_para_o_tabuleiro`) e só empurra para a direita:
        a fração de agora é o piso. Ela não roda depois de a pessoa arrastar a alça nem depois de
        `posicionar_divisor` restaurar a da sessão anterior -- ali a repartição já foi escolhida, e
        a fração guardada acompanha a largura sozinha, porque é fração e não pixel.

        **O piso da coluna de leitura é aplicado antes, e fora da guarda** (S-551, terceira
        rodada). Ele não é posição, é limite: os `QGroupBox` da leitura declaravam 266 px de mínimo
        -- **386** com o motor ligado, porque o texto das linhas entra na conta --, e numa aba de
        496 px nem esse mínimo nem o do tabuleiro cabiam. O `QSplitter` então não atendia nenhum
        dos dois, repartia 240/240, e o tabuleiro saía **36 px cortado**: sem a coluna `h`, sem as
        duas réguas, com a faixa de navegação em duas fileiras -- e sem volta, porque o mínimo do
        `QGroupBox` não desce quando o motor é desligado. Quem declara o piso da leitura é
        `sala_declarada`, e é ele que passa a valer aqui.

        **E o que a coluna pede vai junto na pergunta -- é a correção da quarta rodada.**
        `piso_da_leitura` responde "o quanto a leitura *pode* exigir"; `setMinimumWidth` é piso, e
        um piso aplicado cru também **sobe** o que a coluna pedia sozinha. Onde os `QGroupBox`
        declaravam 136 px -- a sala sem motor --, a régua os punha em 192, e o tabuleiro pagava a
        diferença sem ninguém ter pedido: medido a 1024x768, ele caiu de 298 para 245 px (301 para
        245 na pele fita, menos 18%), e a 1400x950 de 454 para 447. Quem mede o pedido é o widget,
        e por isso ele vai por argumento, como a esteira e a alça.
        """
        largura = sum(self._sala.divisor.sizes())
        if largura <= 0:
            return
        esteira = self._esteira_da_coluna()
        alca = max(1, self._sala.divisor.handleWidth())
        self._sala.divisor_vertical.setMinimumWidth(
            piso_da_leitura(
                largura,
                minimo=self._caixa_minima_do_tabuleiro(),
                esteira=esteira,
                alca=alca,
                pedido=self._sala.divisor_vertical.minimumSizeHint().width(),
            )
        )
        if self._divisor_escolhido:
            return
        alvo = fracao_para_o_tabuleiro(
            largura,
            self._altura_livre_para_o_tabuleiro(),
            minimo=self._caixa_minima_do_tabuleiro(),
            fracao_atual=self.fracao_do_divisor,
            esteira=esteira,
            alca=alca,
            largura_anterior=self._largura_acomodada,
        )
        self._largura_acomodada = largura
        if abs(alvo - self.fracao_do_divisor) < 0.005:
            return
        esquerda = int(largura * alvo)
        self._sala.divisor.setSizes([esquerda, max(1, largura - esquerda)])

    @property
    def fracao_do_divisor_vertical(self) -> float:
        """Onde está a alça entre lances e comentário, como fração da altura (S-519)."""
        tamanhos = self._sala.divisor_vertical.sizes()
        altura = sum(tamanhos)
        if len(tamanhos) < 2 or altura <= 0:
            return 0.0
        return geometria.fracao_de_divisor(tamanhos[0], altura)

    def posicionar_divisor_vertical(self, fracao: float) -> None:
        """Põe a alça vertical naquela fração. `0.0` deixa os pesos decidirem."""
        if fracao <= 0.0:
            return
        tamanhos = self._sala.divisor_vertical.sizes()
        altura = max(1, sum(tamanhos) or self._sala.divisor_vertical.height())
        primeiro = int(altura * fracao)
        resto = max(1, altura - primeiro)
        if len(tamanhos) <= 2:
            self._sala.divisor_vertical.setSizes([primeiro, resto])
            return
        # Com o motor são três partes, e a fração guardada é só a da primeira: as outras duas
        # repartem o que sobra na proporção que já tinham, senão mover a alça de cima esmagaria a
        # seção do motor sem ninguém ter pedido.
        antes = sum(tamanhos[1:]) or 1
        self._sala.divisor_vertical.setSizes(
            [primeiro, *(max(1, int(resto * lado / antes)) for lado in tamanhos[1:])]
        )

    @property
    def fracao_do_divisor(self) -> float:
        """Onde a alça está, como fração da largura. `0.0` quando ainda não há geometria medida."""
        tamanhos = self._sala.divisor.sizes()
        largura = sum(tamanhos)
        if len(tamanhos) < 2 or largura <= 0:
            return 0.0
        return geometria.fracao_de_divisor(tamanhos[0], largura)

    def posicionar_divisor(self, fracao: float) -> None:
        """Põe a alça naquela fração. `0.0` deixa o peso do `QSplitter` decidir.

        **Uma fração guardada desliga a regra da S-551**, e é o que impede as duas de brigarem: a
        sessão anterior fechou com uma repartição, e ela é uma escolha -- ou da pessoa, que
        arrastou, ou da própria regra, que rodou na primeira abertura e teve o resultado gravado.
        Recalculá-la a cada `resize` sobrescreveria a primeira; nunca calculá-la deixaria a
        primeira abertura com o vazio que este item foi consertar.
        """
        if fracao <= 0.0:
            return
        self._divisor_escolhido = True
        largura = max(1, sum(self._sala.divisor.sizes()) or self._sala.divisor.width())
        esquerda = int(largura * fracao)
        self._sala.divisor.setSizes([esquerda, max(1, largura - esquerda)])

    @property
    def fracao_do_tabuleiro(self) -> float:
        """Que fração da coluna o tabuleiro ocupa. É o leitor que `AppState.board_zoom` não tinha.

        **O campo existia, era gravado, era lido do disco e não tinha ninguém do outro lado**
        (S-518). O commit que religou o estado da janela registrou "`board_zoom` fica sem uso de
        propósito: o tabuleiro do Qt se ajusta ao painel" -- o que era verdade sobre o piso e não
        sobre o teto, porque `MAX_DO_TABULEIRO` o parava em 560 px.
        """
        return self._fracao_do_tabuleiro

    def definir_fracao_do_tabuleiro(self, fracao: float) -> None:
        """Aplica a fração ao tabuleiro da sala. `0.0` é "nunca escolhi", e aí vale o padrão."""
        self._fracao_do_tabuleiro = FRACAO_PADRAO_DO_TABULEIRO if fracao <= 0.0 else float(fracao)
        self._sala.tabuleiro.definir_fracao(self._fracao_do_tabuleiro)
