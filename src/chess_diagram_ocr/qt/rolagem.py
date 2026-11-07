"""A aba que rola quando não cabe na tela -- a metade da S-150 que o porte perdeu (S-552).

**A S-150 sempre teve duas metades**, e o docstring de `ui/geometria.PISO_MEDIDO` ainda descreve as
duas: *"a altura de 800 não cabe num notebook de 1366x768, e por isso o piso sozinho nunca foi o
item. Ela é o que o conteúdo precisa **sem rolagem**; quem fecha a lacuna é a segunda metade da
S-150, `ui/rolagem.py` -- Resultado, Configuração e Galeria rolam verticalmente"*.

`ui/rolagem.py` não existe nesta árvore. Ele era do Tk, saiu no corte (S-506), e **nada** ocupou o
lugar dele: nenhum painel do Qt tem `QScrollArea`, e a consequência foi medida em 2026-09-04 ao
pedir a janela a 1000x800:

- a Galeria pede `711 x 800` px de mínimo -- 420 de recorte, 260 de lateral e a folga (S-154) --,
  e ela sozinha punha o piso da janela em **902 px de altura**;
- o painel de Resultado pede `301 x 551` com a tela vazia e **`301 x 1095` depois de ler uma
  página**: o rótulo `detalhes` quebra linha, e um `QLabel` com `wordWrap` responde uma altura
  mínima calculada para a largura mais estreita possível. Ler uma página fazia o piso da janela
  subir para **1218 px** -- mais alto que a tela de um notebook de 1366x768, e sem volta na
  sessão.

**A saída é a da S-150, e não encolher o conteúdo.** Os 420 px do recorte da galeria são medidos
(S-154) e os detalhes do reconhecimento são o que a pessoa lê para decidir se aceita a leitura:
cortar qualquer um dos dois seria trocar um defeito de janela por um de produto. O que muda é que
o painel deixa de **exigir** a altura dele da janela -- ele a pede ao viewport, e o que passar vira
rolagem.

**Por dentro é uma linha**, e é de propósito: `QScrollArea` com `setWidgetResizable(True)` faz o
corpo acompanhar a largura do viewport e só rolar na vertical quando a altura falta. Sem
`widgetResizable` o corpo ficaria no `sizeHint` dele e a barra horizontal apareceria sempre.
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

__all__ = ["em_rolagem"]


def em_rolagem(painel: QWidget, corpo: QWidget) -> QScrollArea:
    """Põe `corpo` dentro de uma área rolável que ocupa `painel` inteiro. Devolve a área.

    **O painel continua sendo o widget que a janela conhece**, e é o que faz isto caber num item:
    `qt/janela.py` adiciona `self.painel` e `self.galeria` às abas pelo nome, e nada lá muda. O
    corpo é um filho novo, e quem pergunta ao painel pelos widgets dele -- `campos_de_header`,
    `tabuleiro`, `detalhes` -- continua recebendo os mesmos objetos.

    Sem moldura: a aba já é uma moldura, e a segunda desenharia uma linha dentro da outra.
    """
    fora = QVBoxLayout(painel)
    fora.setContentsMargins(0, 0, 0, 0)
    area = QScrollArea(painel)
    area.setWidget(corpo)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    fora.addWidget(area)
    return area
