"""O glifo de dois contornos empilhados: `:`, `;` e `=` (S-211).

**A segmentação entrega contorno, e três glifos comuns são dois contornos.** `unir_pingos` (S-185)
resolve o pingo do `i` e o ponto do `!`, e a docstring dela diz o que ela deixa de fora, com todas
as letras: *"dois pontos e ponto e vírgula, que não têm base alta com que se unir"*. Este módulo é
essa exceção, virada de regra -- e o `=` entrou junto porque é o mesmo fenômeno.

## O que estava acontecendo, medido

Em 13 páginas de 4 livros de camada editorada:

    caractere   na camada   no glifo   recall
    :                   9          0       0%
    ;                   4          0       0%
    =                  14          0       0%
    .                 362        469     130%     <- os dois-pontos partidos ao meio

Zero. Não é "lê mal": não chega a existir um box com a forma de `:` para o classificador julgar --
ele vê dois pontos separados e responde `.` duas vezes, corretamente. `defense: he` saía
`defense.. he`, e `g1=♕` saía `g1 ♕`.

**E não é falta de classe**: `:` tem 1.449 amostras na base, `;` tem 225 e `=` tem 164. O modelo
sabe os três. Ninguém nunca os mostrou a ele inteiros.

## As duas metades chegam por caminhos diferentes

O ponto de `:` **passa** pela peneira da S-185 e está entre as caixas. A barra do `=` **não**: ela
tem proporção 8 a 12 de largura sobre altura, e `boxes.PROPORCAO_MAXIMA` corta em 6,0 para separar
glifo de filete e sublinhado. Por isso `barras` existe -- ela recolhe o que aquela régua rejeitou,
e só o devolve ao texto se ele **casar com um par vertical**. Uma barra sozinha continua sendo
filete, e continua fora.

Medido nas mesmas páginas: 38 contornos rejeitados pela régua de proporção, e **28 deles têm
parceiro vertical -- exatamente os 14 `=` da camada**. O teste do par é o que separa os dois.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .boxes import MIN_AREA_GLIFO, PROPORCAO_MAXIMA, Caixa

ALTURA_DE_PARTE = 0.55
"""Altura máxima de um box para ele ser **metade** de um glifo empilhado, em escalas.

Acima disto é letra: o `:` inteiro mede ~0,7 escala, então cada metade fica bem abaixo de 0,55."""

SOBREPOSICAO_MINIMA = 0.50
"""Quanto os dois têm de compartilhar em `x`. Medido: os pares reais ficam entre 0,71 e 1,00."""

VAO_MAXIMO = 0.60
"""Vão vertical máximo entre as duas metades, em escalas. Medido: 0,33 a 0,46 nos pares reais.

**É o guarda contra o merge atravessar a linha de texto**, e é a mesma cicatriz que
`boxes.VAO_MAXIMO_DO_PINGO` registra: entre linhas o vão é de ~1 escala."""

ALTURA_MAXIMA_DA_UNIAO = 1.30
"""Acima disto a união não é um glifo, e o par era coincidência. Medido: 0,67 a 1,23."""

LARGURA_MAXIMA_DE_BARRA = 1.20
"""Largura máxima de uma barra de `=`, em escalas. Medido: 0,77 a 0,80 -- todas.

Existe para o filete e o sublinhado, que são largos, não voltarem junto: eles atravessam a coluna,
e nenhum cabe em 1,2 alturas de caractere."""


def barras(img_bin: np.ndarray, *, escala: int) -> list[Caixa]:
    """Os contornos que a régua de proporção rejeitou e que podem ser **metade de um `=`**.

    Não devolve o filete nem o sublinhado: eles são largos, e `LARGURA_MAXIMA_DE_BARRA` os corta.
    Quem decide de fato é `unir`, que só deixa entrar no texto a barra que **casou com um par** --
    esta função apenas junta os candidatos.
    """
    import cv2

    if img_bin.size == 0 or escala <= 0:
        return []
    piso = MIN_AREA_GLIFO * escala * escala
    teto_de_largura = LARGURA_MAXIMA_DE_BARRA * escala
    contornos, _ = cv2.findContours(img_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    achadas: list[Caixa] = []
    for contorno in contornos:
        x, y, largura, altura = cv2.boundingRect(contorno)
        if largura <= 0 or altura <= 0 or largura * altura < piso:
            continue
        if largura / altura <= PROPORCAO_MAXIMA:
            continue  # já é caixa de caractere; quem a devolve é `caixas_de_caractere`
        if largura > teto_de_largura or altura > ALTURA_DE_PARTE * escala:
            continue
        achadas.append(Caixa(x, y, x + largura, y + altura))
    return achadas


def _casam(acima: Caixa, abaixo: Caixa, escala: int) -> bool:
    """As duas são metades do mesmo glifo? As quatro réguas do cabeçalho, nesta ordem."""
    if acima.y2 > abaixo.y1:
        return False
    largura = max(acima.largura, abaixo.largura)
    if largura <= 0:
        return False
    comum = min(acima.x2, abaixo.x2) - max(acima.x1, abaixo.x1)
    if comum / largura < SOBREPOSICAO_MINIMA:
        return False
    if (abaixo.y1 - acima.y2) > VAO_MAXIMO * escala:
        return False
    return (abaixo.y2 - acima.y1) <= ALTURA_MAXIMA_DA_UNIAO * escala


def unir(caixas: Sequence[Caixa], *, escala: int, extras: Sequence[Caixa] = ()) -> list[Caixa]:
    """As caixas com os pares empilhados fundidos num box só. Ordem de entrada preservada.

    `extras` são as barras de `barras()`: elas **só entram no resultado se casarem**. Uma barra
    solta continua sendo filete, e continua fora do texto -- é o que impede a régua de proporção
    da S-185 de ser desfeita por acidente.

    A ordem de entrada é preservada pela mesma razão de `unir_pingos`: quem ordena é
    `linhas.ordem_em_faixa`, e devolver outra ordem aqui esconderia um defeito dele atrás de um
    daqui. O box fundido ocupa o lugar da metade **de cima**.
    """
    if escala <= 0 or (not caixas and not extras):
        return list(caixas)

    candidatas = [c for c in caixas if c.altura <= ALTURA_DE_PARTE * escala]
    todas = [*candidatas, *extras]
    if len(todas) < 2:
        return list(caixas)

    # Cada metade entra em no máximo um par: um `:` tem duas partes, não três. O primeiro par que
    # casa vence, e a busca é sobre a lista já ordenada por `y` para o de cima vir primeiro.
    ordenadas = sorted(todas, key=lambda c: (c.y1, c.x1))
    usada: set[int] = set()
    uniao: dict[int, Caixa] = {}
    absorvida: set[int] = set()
    for i, acima in enumerate(ordenadas):
        if id(acima) in usada:
            continue
        for abaixo in ordenadas[i + 1 :]:
            if id(abaixo) in usada or not _casam(acima, abaixo, escala):
                continue
            usada.update({id(acima), id(abaixo)})
            uniao[id(acima)] = Caixa(
                min(acima.x1, abaixo.x1),
                acima.y1,
                max(acima.x2, abaixo.x2),
                abaixo.y2,
                acima.angulo,
            )
            absorvida.add(id(abaixo))
            break

    saida: list[Caixa] = []
    for caixa in caixas:
        if id(caixa) in absorvida:
            continue
        saida.append(uniao.get(id(caixa), caixa))
    # A barra que casou entra no texto; a que não casou fica de fora, como a S-185 quer.
    for extra in extras:
        if id(extra) in uniao:
            saida.append(uniao[id(extra)])
    return saida


PROPORCAO_DE_IGUAL = 1.0
"""Largura sobre altura acima da qual o glifo empilhado é `=`, e não `:` nem `;`.

**A fusão não basta, e a razão é o mesmo resize de sempre.** `_entrada` estica todo recorte para
32x32, o que apaga a **proporção** junto com o tamanho: duas barras largas e dois pontos, ambos
esticados para um quadrado, viram a mesma imagem. Depois de fundir, metade dos `=` saía `:`.

Medido em 13 páginas: `=` fica entre 2,40 e 2,67 de largura sobre altura; `:` e `;` entre 0,24 e
0,25. Um fator de dez, e qualquer corte no meio separa 100%. O corte fica no **quadrado** -- mais
largo que alto é `=` --, que é a fronteira que a forma dos dois glifos justifica sozinha."""


def corrigir(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[Caixa],
    idx_to_char: dict[int, str],
    *,
    corte: float | None = None,
) -> list[tuple[str, float]]:
    """Separa `=` de `:` e `;` pela **proporção** do box fundido. Ver `PROPORCAO_DE_IGUAL`.

    Roda depois da classificação e só toca box lido como um dos três: fora deles, a saída é a
    entrada. A confiança devolvida é a da classe escolhida, como nos módulos irmãos.
    """
    if not lidos:
        return []
    indices = {c: i for i, c in idx_to_char.items() if c in ("=", ":")}
    if "=" not in indices or ":" not in indices:
        return list(lidos)
    limite = PROPORCAO_DE_IGUAL if corte is None else corte

    saida: list[tuple[str, float]] = []
    for k, (char, confianca) in enumerate(lidos):
        if char not in ("=", ":", ";") or k >= len(caixas) or k >= probs.shape[0]:
            saida.append((char, confianca))
            continue
        caixa = caixas[k]
        largo = caixa.largura / max(1, caixa.altura) >= limite
        if largo and char != "=":
            saida.append(("=", float(probs[k, indices["="]])))
        elif not largo and char == "=":
            saida.append((":", float(probs[k, indices[":"]])))
        else:
            saida.append((char, confianca))
    return saida


__all__ = [
    "ALTURA_DE_PARTE",
    "ALTURA_MAXIMA_DA_UNIAO",
    "LARGURA_MAXIMA_DE_BARRA",
    "PROPORCAO_DE_IGUAL",
    "SOBREPOSICAO_MINIMA",
    "VAO_MAXIMO",
    "barras",
    "corrigir",
    "unir",
]
