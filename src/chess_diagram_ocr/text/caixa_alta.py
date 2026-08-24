"""Maiúscula ou minúscula, decidido pela **altura** e não pela forma (S-211).

**O problema é do pré-processamento, e não do modelo.** `ClassificadorDeGlifo._entrada` faz
`cv2.resize(recorte, (32, 32))` em todo glifo, e oito letras do alfabeto latino têm maiúscula e
minúscula com a **mesma forma**, mudando só o tamanho:

    c C   o O   s S   u U   v V   w W   x X   z Z

Depois do resize as duas são a mesma imagem. O modelo não erra por ser fraco: ele erra porque a
informação que decide foi apagada antes de ele ver o recorte.

## O tamanho da coisa, medido

Em 13 páginas de 3 livros de camada **editorada** (Dvoretsky 2025, Capablanca pt-br, Fischer
pt-br), 212 linhas casadas contra a camada, 617 substituições:

    ♔->K, ♖->R, ♕->Q          192    não é erro: o glifo acerta a figurina, a camada usa ASCII
    caixa alta (S->s, V->v…)  ~241    <- isto
    caractere espúrio           ~96
    0->o                          3

E duas medições fecham o caso:

- **a classe certa está em rank 2 em 237 de 237 casos.** Não "quase sempre": todos. O modelo diz
  `S` com 0,96 e `s` com 0,03, sempre nessa ordem. Não há o que aprender -- há o que **escolher**;
- **a altura separa.** Minúscula mede 1,00 da mediana de altura da linha; maiúscula, 1,41.

E o ganho ponta a ponta, medido em 11 páginas de 4 livros pelo caminho de produção
(`docs/metrics/texto_caixa_alta.json`):

    CER 0,1434 -> 0,1114   (-22,3%)   11 páginas melhoram, nenhuma piora, sem custo de tempo

É o maior ganho medido deste subpacote, e é o único dos três interruptores da página que entra
**ligado** -- o modo bloco da S-188 e o separador da S-186 foram medidos e não pagam.

**O caminho da faixa de legenda não usa isto.** A correção mora em `text/leitor.py`, e não em
`GlyphRecognizer.read`: os números publicados da legenda continuam descrevendo o que roda lá.

## Por que o critério é a mediana da linha, e não a escala da página

`boxes.escala_de_texto` é medida por massa de tinta e cai perto da **altura de maiúscula** -- é a
mesma razão pela qual `unir_pingos` usa a mediana das caixas presentes em vez da escala. Aqui a
régua tem de ser a **x-height**, e a mediana das alturas de uma linha de prosa é dominada por
minúscula, que é o que a torna uma boa aproximação dela.

**Por linha, e nunca pela página.** Um título em corpo maior tem x-height maior, e comparar as
letras dele com a mediana da página os promoveria todos a maiúscula.

## O que este módulo não faz

Não decide `l` contra `1`, nem `0` contra `o`: essas trocam **entre alfabetos**, e altura não as
separa (`l` e `1` têm a mesma altura). Elas são da S-209.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

AMBIGUAS = "cosuvwxz"
"""As letras cuja maiúscula e minúscula têm a mesma forma, mudando só o tamanho.

**Oito, e a lista é fechada por inspeção do alfabeto, não por medição.** `k` e `y` quase entram --
a minúscula tem haste que sobe ou desce, e isso muda a forma o bastante para o modelo. As oito
daqui não têm nenhuma diferença de desenho em fonte de texto comum."""

CORTE_DE_CAIXA = 1.25
"""Acima de tantas x-heights, a caixa é alta. Medido em 1.026 casos: separa 99,4%.

**A amostra dos dois lados é muito desigual, e o número acima esconde isso**: são 1.001 minúsculas
contra 25 maiúsculas, porque prosa é quase toda minúscula. O que está bem medido é que minúscula
fica em 1,00; o corte alto o bastante para não rebaixar maiúscula legítima está medido em 25
casos, e é aí que este número pode estar errado. Ver `docs/metrics/texto_caixa_alta.json`."""


def x_height(alturas: Sequence[int]) -> float:
    """A x-height da linha, aproximada pela **mediana** das alturas de box. `0.0` sem boxes.

    Mediana e não média: uma linha com dois parênteses altos e uma vírgula baixa move a média e
    não move a mediana. É a mesma escolha de `unir_pingos`, e pelo mesmo motivo.
    """
    if not alturas:
        return 0.0
    return float(np.median(np.asarray(alturas, dtype=np.float64)))


def pares_de_caixa(idx_to_char: dict[int, str]) -> dict[int, int]:
    """`{índice de classe: índice da mesma letra na outra caixa}`, só para as ambíguas.

    Só entra o par **completo**: uma classe cuja contraparte não existe no modelo fica de fora, e
    não vira meia-regra. Classes de ligadura (`fi`, `Bl`) nunca entram -- elas têm mais de um
    caractere, e a altura de uma ligadura não diz nada sobre a caixa dela.
    """
    de_char = {c: i for i, c in idx_to_char.items() if len(c) == 1}
    pares: dict[int, int] = {}
    for letra in AMBIGUAS:
        baixa, alta = de_char.get(letra), de_char.get(letra.upper())
        if baixa is None or alta is None:
            continue
        pares[baixa] = alta
        pares[alta] = baixa
    return pares


def caixa_pela_altura(altura: float, xh: float, *, corte: float | None = None) -> bool:
    """Este box é caixa alta? `False` quando não há x-height -- ver `decidir`.

    **`corte=None` lê `CORTE_DE_CAIXA` na hora da chamada, e isso é o item.** Escrever
    `corte: float = CORTE_DE_CAIXA` na assinatura amarra o valor no momento em que o módulo é
    importado: quem depois muda a constante -- uma varredura de limiar, um teste -- muda um número
    que ninguém mais lê, e a varredura sai com todas as linhas iguais. Foi exatamente o que
    aconteceu na primeira medição deste item, e o defeito só apareceu porque sete cortes
    diferentes deram o mesmo CER até o quarto decimal.
    """
    if xh <= 0:
        return False
    return altura / xh >= (CORTE_DE_CAIXA if corte is None else corte)


def decidir(
    probs: np.ndarray,
    alturas: Sequence[int],
    idx_to_char: dict[int, str],
    *,
    corte: float | None = None,
    pares: dict[int, int] | None = None,
) -> list[tuple[str, float]]:
    """`(caractere, confiança)` por box, com a caixa das ambíguas decidida pela altura.

    **Restringe o decodificador, e não a saída.** Onde a altura contradiz o argmax, a escolha passa
    para a outra classe do par e a confiança devolvida é a **dela** -- que é o que a torna honesta:
    trocar o caractere e manter os 0,96 do palpite recusado diria que o programa tem certeza de
    algo que ele acabou de mudar de ideia sobre. É a mesma decisão de `GlyphRecognizer`, que tira
    as colunas proibidas da matriz **antes** do argmax; o critério aqui é por box, e não por faixa.

    O que ela **não** faz: mexer em box que não é letra ambígua, e mexer em linha sem x-height.
    Fora as ambíguas, o resultado é `argmax` puro -- byte a byte o que o classificador daria.
    """
    if probs.size == 0:
        return []
    if pares is None:
        pares = pares_de_caixa(idx_to_char)
    xh = x_height(alturas)

    saida: list[tuple[str, float]] = []
    for linha in range(probs.shape[0]):
        escolhido = int(probs[linha].argmax())
        outro = pares.get(escolhido)
        if outro is not None and linha < len(alturas):
            alta = caixa_pela_altura(float(alturas[linha]), xh, corte=corte)
            desejado = outro if idx_to_char[escolhido].isupper() != alta else escolhido
            escolhido = desejado
        saida.append((idx_to_char[escolhido], float(probs[linha, escolhido])))
    return saida


__all__ = [
    "AMBIGUAS",
    "CORTE_DE_CAIXA",
    "caixa_pela_altura",
    "decidir",
    "pares_de_caixa",
    "x_height",
]
