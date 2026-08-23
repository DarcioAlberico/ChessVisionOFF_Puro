"""O box que engoliu duas linhas (S-198).

O descendente de um `g` ou de um `p` encosta na linha de baixo, os dois contornos viram um, e um
caractere some. Medido no projeto de origem, o conserto valeu **+0,3 de F1** nas 10 páginas
rotuladas -- e o ganho é do corte de linha, não do modelo.

Este item ganhou um segundo motivo depois da medição da S-185: **a faixa dilatada da
`ocr_caption`** (o `radius_pt`) encosta na linha de cima, e os fragmentos de descendente que
entram custam 8 pontos de CER. `quebrar_em_linhas` os separa em linha à parte corretamente; o que
faltava era alguém dizer que aquela linha é fragmento.

## Duas coisas diferentes, e a segunda não tem valor no vale

**Partir** é para a caixa alta demais: o corte sai do vale do perfil horizontal de tinta, e quando
não há vale -- porque o descendente preenche a faixa -- ele vai para a fronteira que a banda da
S-187 já conhece.

**Descartar** é para a linha inteira que é só fragmento: um punhado de caixas baixas demais e
largas de menos, na borda da faixa. Ela não se parte, ela some.

## A régua é uma probabilidade, e por isso ela não atravessa uma calibração

É o achado da F69 no projeto de origem, e vale como aviso: o árbitro compara a confiança dos dois
pedaços contra a do inteiro, e confiança é uma escala que a temperatura do modelo move. **Se a
temperatura mudar, o limiar do corte precisa ser remedido.** `tests/test_text_duas_linhas.py`
amarra os dois e falha quando um muda sozinho.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from .boxes import Caixa

ALTURA_SUSPEITA = 1.6
"""Acima de quantas escalas de caractere a caixa é candidata a ter engolido duas linhas."""

MARGEM_DO_VALE = 0.25
"""Que fração da altura, em cada ponta, fica fora da busca do vale.

O vale de verdade fica no meio; um mínimo colado na borda é o fim do próprio glifo."""

GANHO_MINIMO = 0.05
"""Quanto a confiança média dos dois pedaços precisa superar a do inteiro para o corte valer.

**É a régua que não atravessa uma calibração** -- ver o cabeçalho. Conservador de propósito: na
dúvida, não cortar, porque cortar um glifo bom troca um caractere certo por dois errados."""

FRAGMENTO_ALTURA = 0.35
"""Abaixo desta fração da escala, a caixa é fragmento de descendente e não caractere."""

FRAGMENTO_FRACAO = 0.7
"""Que fração da linha precisa ser fragmento para a linha inteira ser descartada.

Uma linha com um `.` e cinco letras não é fragmento; uma com quatro pedaços de 4 px é."""


def _perfil_horizontal(binaria: np.ndarray, caixa: Caixa) -> np.ndarray:
    """Tinta por linha do recorte. É onde o vale entre duas linhas de texto aparece."""
    recorte = caixa.recortar(binaria)
    if recorte.size == 0:
        return np.zeros(0, dtype=np.float64)
    return (recorte > 0).mean(axis=1)


def vale(binaria: np.ndarray, caixa: Caixa) -> int | None:
    """A linha do recorte com menos tinta, em coordenadas da página. `None` quando não há vale.

    Ignora as pontas: o mínimo colado na borda é o fim do próprio glifo, e cortar ali produz um
    pedaço vazio.
    """
    perfil = _perfil_horizontal(binaria, caixa)
    if perfil.size < 3:
        return None

    margem = max(1, int(len(perfil) * MARGEM_DO_VALE))
    miolo = perfil[margem : len(perfil) - margem]
    if miolo.size == 0:
        return None
    if float(miolo.min()) >= float(perfil.mean()):
        # Sem vale: o descendente preenche a faixa. Quem corta é a fronteira da banda.
        return None
    return caixa.y1 + margem + int(miolo.argmin())


def partir(
    caixa: Caixa,
    corte: int,
    *,
    arbitro: Callable[[Sequence[Caixa]], float] | None = None,
) -> list[Caixa]:
    """A caixa partida em duas no `corte`, ou intacta quando o árbitro não confirma.

    **Sem árbitro não corta**, e é a mesma regra da S-197: a geometria propõe, o classificador
    dispõe. Cortar sem confirmação custou 2,3 pontos de F1 no projeto de origem.
    """
    if corte <= caixa.y1 or corte >= caixa.y2:
        return [caixa]

    de_cima = Caixa(caixa.x1, caixa.y1, caixa.x2, corte, caixa.angulo)
    de_baixo = Caixa(caixa.x1, corte, caixa.x2, caixa.y2, caixa.angulo)
    if arbitro is None:
        return [caixa]

    inteiro = arbitro([caixa])
    partido = arbitro([de_cima, de_baixo])
    return [de_cima, de_baixo] if partido > inteiro + GANHO_MINIMO else [caixa]


def separar(
    binaria: np.ndarray,
    caixas: Sequence[Caixa],
    *,
    escala: int,
    arbitro: Callable[[Sequence[Caixa]], float] | None = None,
    fronteira: dict[int, int] | None = None,
) -> list[Caixa]:
    """As caixas com as que engoliram duas linhas partidas.

    `fronteira` é `{id(caixa): y do corte}` para quem já sabe onde a banda termina -- é o caminho
    de quando não há vale. Sem ela e sem vale, a caixa fica inteira.
    """
    if escala <= 0:
        return list(caixas)

    piso = ALTURA_SUSPEITA * escala
    saida: list[Caixa] = []
    for caixa in caixas:
        if caixa.altura < piso:
            saida.append(caixa)
            continue
        corte = vale(binaria, caixa)
        if corte is None and fronteira is not None:
            corte = fronteira.get(id(caixa))
        if corte is None:
            saida.append(caixa)
            continue
        saida.extend(partir(caixa, corte, arbitro=arbitro))
    return saida


def e_fragmento(linha: Sequence[Caixa], *, escala: int) -> bool:
    """A "linha" é só fragmento de descendente da linha vizinha?

    É o caso da faixa dilatada da `ocr_caption`: ela encosta na linha de cima, e o que entra são
    pedaços baixos demais para serem caractere. Medido na S-185, custa 8 pontos de CER quando
    ninguém os descarta.
    """
    if not linha or escala <= 0:
        return False
    piso = FRAGMENTO_ALTURA * escala
    fragmentos = sum(1 for c in linha if c.altura < piso)
    return fragmentos >= len(linha) * FRAGMENTO_FRACAO


def descartar_fragmentos(linhas: Sequence[Sequence[Caixa]], *, escala: int) -> list[list[Caixa]]:
    """As linhas sem as que são só fragmento. Ver `e_fragmento`."""
    return [list(linha) for linha in linhas if not e_fragmento(linha, escala=escala)]


__all__ = [
    "ALTURA_SUSPEITA",
    "FRAGMENTO_ALTURA",
    "FRAGMENTO_FRACAO",
    "GANHO_MINIMO",
    "MARGEM_DO_VALE",
    "descartar_fragmentos",
    "e_fragmento",
    "partir",
    "separar",
    "vale",
]
