"""A vista da página: o que a roda do mouse faz, para onde o zoom puxa, quanto cabe (S-70).

**Por que isto é um módulo.** A aba "Leitura" saiu na S-69 e levou junto a rolagem contínua e
o zoom do leitor do Edge. O que ficou no lugar foi um canvas com duas barras de rolagem -- o
suficiente para recortar e reconhecer, e pouco para *ler*. Este módulo é a regra dessa parte,
separada do widget pela mesma razão de sempre: cada uma das três decisões abaixo erra de um
jeito que só se percebe usando, e nenhuma delas deveria exigir uma janela para ser conferida.

**As três decisões.**

1. **A roda na borda vira a página.** É o que devolve a sensação de rolagem contínua sem
   fingir que existe um documento contínuo: quem chega ao fim da página e insiste ganha a
   página seguinte, no topo. Com carência, porque roda inercial dispara dezenas de eventos e
   sem ela dois giros pulariam quatro páginas.
2. **O zoom é multiplicativo e ancorado no ponteiro.** Aditivo de 0,1 dá salto de 33% em 0,3 e
   de 5% em 1,9 -- a mesma tecla com efeitos diferentes. E zoom que não ancora joga fora o
   lugar onde a pessoa estava olhando, que é justamente o que ela quer aumentar.
3. **Ajustar à largura** é uma conta, não um palpite: a largura útil dividida pela largura da
   página em pixels a 100%.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "MAX_ZOOM",
    "MIN_ZOOM",
    "PAGE_FLIP_COOLDOWN_S",
    "WheelAction",
    "ZOOM_STEP",
    "anchor_after_zoom",
    "clamp_zoom",
    "decide_wheel",
    "fit_width_zoom",
    "wheel_direction",
    "zoomed",
]

MIN_ZOOM = 0.25
MAX_ZOOM = 2.0
"""Os limites de sempre. Ficam aqui porque agora três lugares os aplicam -- os botões, a roda
e o estado restaurado do disco --, e três cópias de um intervalo divergem."""

ZOOM_STEP = 1.15
"""Passo multiplicativo da roda. ~4 giros dobram o tamanho, que é o ritmo em que dá para
acompanhar o que está acontecendo na tela."""

PAGE_FLIP_COOLDOWN_S = 0.35
"""Quanto tempo a borda ignora a roda depois de virar a página.

Não é anti-*bounce* teórico: uma roda inercial entrega uma rajada de eventos por giro, e sem
carência o primeiro giro depois da virada cairia de novo na borda da página nova."""

EDGE_EPSILON = 0.001
"""`yview()` devolve fração em ponto flutuante; exigir 1,0 exato nunca aceitaria a borda."""


class WheelAction(str, Enum):
    """O que um giro da roda significa, dada a posição da vista."""

    SCROLL = "scroll"
    PREV_PAGE = "prev_page"
    NEXT_PAGE = "next_page"


def wheel_direction(delta: int) -> int:
    """`+1` para cima, `-1` para baixo, `0` para nada.

    O Windows entrega múltiplos de 120 e o macOS entrega ±1; no X11 não há delta nenhum e sim
    os botões 4 e 5, que o painel traduz para ±120 antes de chegar aqui. O sinal é a única
    parte comum às três, e é a única que esta função promete.
    """
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def decide_wheel(
    *,
    direction: int,
    view: tuple[float, float],
    flip_pages: bool = True,
    since_last_flip: float = PAGE_FLIP_COOLDOWN_S,
) -> WheelAction:
    """O que fazer com o giro. `view` é o `(primeiro, último)` do `yview()` do canvas.

    Virar a página exige **três** condições, e cada uma responde a um jeito de errar: estar na
    borda (senão a roda viraria a página no meio do diagrama), a carência ter passado (senão a
    rajada de uma roda inercial pularia quatro páginas de uma vez) e a virada estar ligada
    (quem prefere que a roda só role tem como dizer isso).
    """
    if direction == 0:
        return WheelAction.SCROLL
    if not flip_pages or since_last_flip < PAGE_FLIP_COOLDOWN_S:
        return WheelAction.SCROLL

    primeiro, ultimo = view
    if direction < 0 and ultimo >= 1.0 - EDGE_EPSILON:
        return WheelAction.NEXT_PAGE
    if direction > 0 and primeiro <= EDGE_EPSILON:
        return WheelAction.PREV_PAGE
    return WheelAction.SCROLL


def clamp_zoom(value: float) -> float:
    return max(MIN_ZOOM, min(MAX_ZOOM, float(value)))


def zoomed(current: float, direction: int, *, step: float = ZOOM_STEP) -> float:
    """O zoom depois de um giro, já grampeado. `direction` positivo aumenta."""
    if direction == 0:
        return clamp_zoom(current)
    fator = step if direction > 0 else 1.0 / step
    return clamp_zoom(float(current) * fator)


def anchor_after_zoom(
    *,
    pointer_canvas: float,
    pointer_widget: float,
    old_span: float,
    new_span: float,
) -> float:
    """A fração de `moveto` que deixa parado o ponto que estava sob o ponteiro.

    `pointer_canvas` é a coordenada do ponto na imagem **antes** do zoom (o `canvasx` do
    evento), `pointer_widget` é a mesma posição em relação à janela, e os dois `span` são a
    largura (ou altura) da página em pixels de tela antes e depois.

    Sem isto, aumentar o zoom sobre um diagrama do canto inferior da página o joga para fora da
    vista -- e a pessoa passa a caçar de volta, com a barra de rolagem, aquilo que ela estava
    justamente tentando ver de perto.
    """
    if new_span <= 0 or old_span <= 0:
        return 0.0
    alvo = pointer_canvas / old_span * new_span
    return max(0.0, min(1.0, (alvo - pointer_widget) / new_span))


def fit_width_zoom(*, viewport_px: int, page_px: int, margin_px: int = 4) -> float | None:
    """O zoom que faz a página caber na largura visível. `None` quando não dá para saber.

    `page_px` é a largura da página renderizada a 100%, e a margem desconta a barra de rolagem
    -- sem ela o "ajustar à largura" acende a barra horizontal que ele existe para apagar.
    """
    if viewport_px <= margin_px or page_px <= 0:
        return None
    return clamp_zoom((viewport_px - margin_px) / page_px)
