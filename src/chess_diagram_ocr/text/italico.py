"""A linha em itálico, e o `l` que sai `/` dentro dela (S-211).

**O diagnóstico é do dono do projeto**, e ele veio junto com a página: *"o caractere `/` aparece
muito no lugar do `l` em textos itálicos"*. Estava certo, e a medição só precisou confirmar o
tamanho.

Na página 311 do `Secrets of Chess Training`, o trecho citado em itálico saía assim:

    impresso   not a bad player. He will possibly play better, but I am sure...
    lido       not a bad p/ayer. He wi// possib/y p/ay better, but / am sure...

**Todo** `l` e todo `I` do trecho vira `/`, e a razão é a forma: em itálico o `l` é um traço
inclinado, que é o desenho do `/`. Medido: a classe certa está em **rank 2 em 16 de 16 casos**.

## Por que a régua é o pendor da linha, e não a palavra

`/` legítimo **existe** neste acervo, e é caro errar: `1/2-1/2` é resultado de partida. Medido em
4 páginas de cada um dos 42 livros, as 25 ocorrências de `/` são todas entre dígitos (`1/2`,
`2/4`, `51/2`) ou em `+/-`. Trocar `/` por `l` sem olhar o contexto apagaria placar de torneio.

O que separa os dois casos é que um mora em **linha itálica** e o outro não. E itálico se mede:
o centroide de tinta da metade de cima do glifo fica à **direita** do da metade de baixo, porque o
traço pende. Medido em 157 linhas da mesma página:

    linhas em itálico    n= 12   p10 +0,110   mediana +0,116   p90 +0,126
    linhas em pé         n=145   p10 -0,018   mediana +0,000   p90 +0,010

Não há sobreposição, e o corte fica em 0,05 -- bem no meio do vão.

## O que este módulo não faz

Não conserta `pesition` nem `f6w`: aquilo é confusão de letra por letra, e quem trata disso é o
léxico. Aqui só se decide `/` contra `l`, e só dentro de linha inclinada.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .boxes import Caixa

PENDOR_DE_ITALICO = 0.05
"""Deslocamento do centroide de tinta do topo em relação ao da base, em larguras de box.

Acima disto a linha está inclinada. Medido: itálico em 0,116 e texto em pé em 0,000 -- o corte
fica no meio de um vão de mais de duas ordens de grandeza."""

MIN_BOXES_PARA_MEDIR = 8
"""Abaixo de tantos boxes a mediana do pendor é ruído, e a linha não é declarada itálica.

Uma linha de três caracteres -- um número de lance, um rótulo de eixo -- não tem população para
medir inclinação nenhuma, e chutar ali trocaria `/` em notação, que é onde o `/` é legítimo."""

TROCA = {"/": "l"}
"""O que uma linha itálica corrige. **Um par só, e é o único que foi medido.**

`I` maiúsculo também sai `/` no mesmo trecho, e **não** entra: escolher entre `l` e `I` precisa de
caixa, e caixa nesse par não é altura -- os dois são hastes da mesma altura. Isso é do léxico."""


def pendor_do_box(binaria: np.ndarray, caixa: Caixa) -> float | None:
    """Quanto o topo do glifo pende à direita da base, em larguras de box. `None` se não dá medir.

    O sinal é o do itálico: positivo quando o traço se inclina para a direita, que é o sentido de
    toda fonte itálica latina. Box com menos de quatro linhas de pixel não tem duas metades, e
    devolve `None` em vez de um número inventado.
    """
    recorte = binaria[caixa.y1 : caixa.y2, caixa.x1 : caixa.x2]
    if recorte.size == 0 or recorte.shape[0] < 4 or caixa.largura <= 0:
        return None
    meio = recorte.shape[0] // 2

    def centro(bloco: np.ndarray) -> float | None:
        _, xs = np.nonzero(bloco)
        return float(xs.mean()) if xs.size else None

    topo, base = centro(recorte[:meio]), centro(recorte[meio:])
    if topo is None or base is None:
        return None
    return (topo - base) / caixa.largura


def pendor_da_linha(binaria: np.ndarray, caixas: Sequence[Caixa]) -> float | None:
    """A mediana do pendor dos boxes da linha. `None` quando não há boxes o bastante.

    Mediana e não média pela razão de sempre: um glifo de xadrez ou um respingo no meio da linha
    move a média e não move a mediana.
    """
    medidos = [p for p in (pendor_do_box(binaria, c) for c in caixas) if p is not None]
    if len(medidos) < MIN_BOXES_PARA_MEDIR:
        return None
    return float(np.median(medidos))


def declarar(
    binaria: np.ndarray, caixas: Sequence[Caixa], *, corte: float | None = None
) -> bool | None:
    """A linha está inclinada -- ou **não deu para medir** (S-236).

    Três estados, e o terceiro é o item: `None` é "não se sabe", e não é o mesmo que `False`. Uma
    linha de três boxes não tem população para medir inclinação nenhuma (ver `MIN_BOXES_PARA_MEDIR`),
    e dizer que ela está em pé seria afirmar sobre o que não se olhou. É o mesmo idioma de
    `LinhaLida.negrito`, e pela mesma razão.

    `e_italica` continua existindo e continua achatando `None` em `False`, porque no caminho da
    **correção** é isso que se quer: não se troca `/` por `l` sobre uma dúvida.
    """
    pendor = pendor_da_linha(binaria, caixas)
    if pendor is None:
        return None
    return pendor >= (PENDOR_DE_ITALICO if corte is None else corte)


def e_italica(binaria: np.ndarray, caixas: Sequence[Caixa], *, corte: float | None = None) -> bool:
    """A linha está inclinada? `corte=None` lê `PENDOR_DE_ITALICO` na hora da chamada.

    Não medir é responder `False`: quem chama isto vai **trocar um caractere**, e a dúvida não
    autoriza a troca. Quem quer a diferença entre "está em pé" e "não se mediu" chama `declarar`.
    """
    return declarar(binaria, caixas, corte=corte) is True


def corrigir(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[Caixa],
    idx_to_char: dict[int, str],
    binaria: np.ndarray,
    *,
    corte: float | None = None,
    italica: bool | None = None,
) -> list[tuple[str, float]]:
    """Numa linha itálica, `/` vira `l`. Fora dela, a saída é a entrada.

    A troca só acontece se a classe de destino existir no modelo, e a confiança devolvida é a
    **dela** -- a mesma regra dos módulos irmãos, e pelo mesmo motivo.

    `italica` é a resposta de `declarar` quando quem chama **já a mediu**. Serve para o leitor não
    varrer os boxes duas vezes na mesma linha -- uma para gravar o campo da S-236, outra para
    decidir a troca -- e é o que sustenta a frase de que a S-236 custa zero de tempo de leitura.
    """
    if not lidos or not caixas:
        return list(lidos)
    inclinada = e_italica(binaria, caixas, corte=corte) if italica is None else italica
    if not inclinada:
        return list(lidos)

    indices = {c: i for i, c in idx_to_char.items() if c in TROCA.values()}
    saida: list[tuple[str, float]] = []
    for k, (char, confianca) in enumerate(lidos):
        destino = TROCA.get(char)
        if destino is None or destino not in indices or k >= probs.shape[0]:
            saida.append((char, confianca))
            continue
        saida.append((destino, float(probs[k, indices[destino]])))
    return saida


__all__ = [
    "MIN_BOXES_PARA_MEDIR",
    "PENDOR_DE_ITALICO",
    "TROCA",
    "corrigir",
    "declarar",
    "e_italica",
    "pendor_da_linha",
    "pendor_do_box",
]
