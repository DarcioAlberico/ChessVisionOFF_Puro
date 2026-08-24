"""O zero que sai letra, e o roque que sai `O.O` (S-211).

**Terceiro achado do mesmo tipo, e desta vez o sinal não é geometria: é a companhia.** `0`, `o` e
`O` têm a mesma forma -- um oval --, e o que os separa é o tamanho, que
`ClassificadorDeGlifo._entrada` apaga ao esticar todo recorte para 32x32. `caixa_alta` já resolve
`o` contra `O` por altura; o `0` fica de fora porque a altura dele é a de **maiúscula**, igual à do
`O`.

O que sobra para separá-los é onde o glifo está: `20` vira `2o` e `40` vira `4o`, e **nenhuma
palavra de língua nenhuma é dígito seguido de `o`**. Quem decide aqui é o token inteiro.

## Medido em 2026-08-24

Em 20 páginas de 5 livros, o sintoma aparece **29 vezes** -- `2o ♕h5+`, `3o ♘d4`, `4o ♔c5`, `9o`
--, sempre no fim de um número de lance de dois dígitos. E a classe certa está no lugar de sempre:

    o '0' está em rank 2 em 21 de 21 casos, com probabilidade mediana 0,096

Não há o que aprender; há o que **escolher**, e é a mesma frase dos três módulos irmãos.

## O roque entra junto, e a evidência dele é de outra natureza

`15 0-0?!` saía `1 5 O.O?!`: o `0` virou `O` e o hífen virou ponto. **Só um caso apareceu nas 20
páginas**, então esta metade não é decidida por medição -- é decidida pela forma do token:
`O.O` não é palavra em língua nenhuma, e `0-0` é a única coisa que ele pode ser num livro de
xadrez. Fica escrito que a evidência é essa, e não uma tabela.

## O que este módulo **não** conserta, e foi medido para saber

O número de lance partido em dois -- `15` saindo `1 5` --, que apareceu **41 vezes**, o dobro do
zero. Ele não é consertável aqui: o vão entre os dois dígitos e o vão entre duas palavras têm o
mesmo tamanho. Medido em 44 vãos de dígito contra 971 de palavra, na mesma página:

    vão entre dígitos    p10 0,46   mediana 0,79   p90 1,17   (em larguras medianas de caixa)
    vão entre palavras   p10 0,62   mediana 0,86   p90 1,60

Um corte em 0,55 juntaria 12 dos 44 dígitos e **destruiria 49 espaços de verdade**. A distinção
não está na geometria: está em saber que ali se espera um número de lance, que é a S-208.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np

from .boxes import Caixa

OVAIS = "oO"
"""As letras que o classificador troca pelo zero. Ver o cabeçalho: é o mesmo oval."""

ROQUE = re.compile(r"^[Oo0][.\-–—_][Oo0](?:[.\-–—_][Oo0])?$")
"""O roque como ele sai: `O.O`, `O-O`, `0.0`, e a versão de três partes.

Não casa com palavra alguma -- é a forma que torna a regra segura sem tabela."""


def _e_parte(char: str) -> bool:
    return char.isdigit() or char in OVAIS


def trechos_de_numero(texto: str) -> list[tuple[int, int]]:
    """Os trechos `[inicio, fim)` do token que são um número com oval dentro.

    **Olha dentro do token, e não o token inteiro, e isso foi medido.** A primeira versão exigia
    que o token todo fosse dígitos e ovais, e funcionava no `Secrets`, onde o número de lance vem
    solto (`2o ♕h5`). No `AAGAARD` ele vem colado ao lance -- `4o.♕c5` --, o token traz uma
    figurina, e a régua rejeitava tudo: 12 dos 29 casos escapavam por isso.

    Um trecho vale se tem **pelo menos um dígito e pelo menos um oval**, e se não encosta em letra
    de nenhum dos dois lados. A segunda condição é a que mantém a notação fora: em `♕xc8` o trecho
    é só o `8`, sem oval; em `Rg8` idem. Sem ela, um `o` que é letra de verdade viraria zero.
    """
    achados: list[tuple[int, int]] = []
    i = 0
    while i < len(texto):
        if not _e_parte(texto[i]):
            i += 1
            continue
        j = i
        while j < len(texto) and _e_parte(texto[j]):
            j += 1
        trecho = texto[i:j]
        antes_e_letra = i > 0 and texto[i - 1].isalpha()
        depois_e_letra = j < len(texto) and texto[j].isalpha()
        if (
            not antes_e_letra
            and not depois_e_letra
            and any(c.isdigit() for c in trecho)
            and any(c in OVAIS for c in trecho)
        ):
            achados.append((i, j))
        i = j
    return achados


def e_numero_com_oval(texto: str) -> bool:
    """O token tem algum número em que um `0` saiu `o` ou `O`? Ver `trechos_de_numero`."""
    return bool(trechos_de_numero(texto))


PONTUACAO = ".,;:!?()[]"
"""O que se ignora nas pontas do token antes de decidir, e que **não pode ser reescrito**.

`0-0?!` traz um `?!` que não é parte do lance. A primeira versão deste módulo o incluía no laço de
troca e devolvia `0-0--`: o núcleo certo, e a pontuação virada em hífen."""


def nucleo_do_roque(texto: str) -> tuple[int, int] | None:
    """`(inicio, fim)` do lance dentro do token, ou `None`. Só o núcleo é reescrito.

    Devolver o intervalo, e não um booleano, é o que impede o defeito de `0-0--`: quem corrige
    precisa saber **onde** o lance acaba.
    """
    inicio = 0
    fim = len(texto)
    while inicio < fim and texto[inicio] in PONTUACAO:
        inicio += 1
    while fim > inicio and texto[fim - 1] in PONTUACAO:
        fim -= 1
    return (inicio, fim) if ROQUE.match(texto[inicio:fim]) else None


def e_roque(texto: str) -> bool:
    """O token é um roque escrito errado? Ver `ROQUE`."""
    return nucleo_do_roque(texto) is not None


def _indice(idx_to_char: dict[int, str], alvo: str) -> int | None:
    return next((i for i, c in idx_to_char.items() if c == alvo), None)


def corrigir(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[Caixa],
    idx_to_char: dict[int, str],
) -> list[tuple[str, float]]:
    """Troca por `0` o oval que está dentro de um número, e conserta o roque. Ordem preservada.

    A confiança devolvida é a da classe do zero, como nos módulos irmãos: manter a do `o` recusado
    diria que o programa tem certeza de algo sobre o que acabou de mudar de ideia.
    """
    from .dicionario import palavras

    if not lidos or len(lidos) != len(caixas):
        return list(lidos)
    zero = _indice(idx_to_char, "0")
    if zero is None:
        return list(lidos)
    hifen = _indice(idx_to_char, "-")

    saida = list(lidos)
    for inicio, fim in palavras(caixas, lidos):
        pedaco = [c for c, _ in lidos[inicio:fim]]
        if any(len(c) != 1 for c in pedaco):
            continue
        token = "".join(pedaco)
        trechos = trechos_de_numero(token)
        if trechos:
            for a, b in trechos:
                for i in range(a, b):
                    if pedaco[i] in OVAIS:
                        saida[inicio + i] = ("0", float(probs[inicio + i, zero]))
            continue
        nucleo = nucleo_do_roque(token)
        if nucleo is None:
            continue
        for i in range(*nucleo):
            if pedaco[i] in OVAIS or pedaco[i] == "0":
                saida[inicio + i] = ("0", float(probs[inicio + i, zero]))
            elif hifen is not None:
                saida[inicio + i] = ("-", float(probs[inicio + i, hifen]))
    return saida


__all__ = [
    "OVAIS",
    "PONTUACAO",
    "ROQUE",
    "corrigir",
    "e_numero_com_oval",
    "e_roque",
    "trechos_de_numero",
    "nucleo_do_roque",
]
