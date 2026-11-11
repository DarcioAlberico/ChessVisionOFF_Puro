"""A ligadura sem o `1` a mais (S-733): `first` saía `fi1rst`, e `flee` saía `f1ee`.

No Times do Dvoretsky a ligadura `fi` não é um contorno só: o gancho do `f` com o pingo é uma caixa, e
a haste do `i` é outra. O modelo lê a primeira como `fi` (ele tem a classe, e acerta) e a segunda como
`1`, a 0,99. Medido nas 27 folhas dos 5 livros aprovados: 13 de 14 palavras da família, no Dvoretsky,
com a haste a 1 a 3 px da ligadura, e 0,65 a 0,68 da altura da linha.

A haste não tem como ser `1` de verdade: **nenhum lance tem `fi` antes do número**, porque `i` não é
coluna. Por isso a primeira regra não pergunta ao léxico. Quando o token tem cara de notação por outro
motivo (`peso_de_notacao`), ela fica quieta do mesmo jeito.

`f1` é outro caso: é lance, e o modelo tem até a classe `f1`. Ele só vira `fl` quando vem seguido de
ao menos duas minúsculas (`f1ee`, `f1ank`), o que lance nenhum faz.
"""

from __future__ import annotations

from collections.abc import Sequence

from .boxes import Caixa

LIGADO = True
"""A reversão da S-733."""

QUEM_PERDE_A_HASTE = ("fi", "ffi")
"""As ligaduras em que a haste do `i` sai solta."""

HASTES = "1|"
"""O que o modelo responde para a haste solta. **Sem o `l` e o `I`:** `file` pode ser `fi` + `l` + `e`, e tirar a
haste dele dava `fie` (visto na prata, em `h-file`)."""

FOLGA = 0.5
"""O vão até a haste, em larguras da haste. A medida é de 1 a 3 px, com a haste de 9 a 10 px."""


def _e_notacao(trecho: Sequence[str]) -> bool:
    from .notacao import peso_de_notacao

    return peso_de_notacao("".join(trecho)) > 0


def corrigir(
    lidos: Sequence[tuple[str, float]],
    caixas: Sequence[Caixa],
) -> tuple[list[Caixa], list[tuple[str, float]]]:
    """As caixas e os caracteres, com a haste solta fundida na ligadura e o `f1` de palavra como `fl`.

    **Funde a caixa, e não só apaga o caractere**: o vão seguinte é medido a partir dela, e uma caixa
    sem letra no meio da linha faria `texto_da_linha` medir de um lugar que não está no texto.

    Devolve novas listas de tamanho possivelmente menor, e por isso roda depois de tudo o que indexa
    `probs` pela caixa.
    """
    if not LIGADO or not lidos or len(lidos) != len(caixas):
        return (list(caixas), list(lidos))

    novas: list[Caixa] = []
    saida: list[tuple[str, float]] = []
    k = 0
    while k < len(lidos):
        char, conf = lidos[k]
        caixa = caixas[k]
        if char in QUEM_PERDE_A_HASTE and k + 1 < len(lidos) and lidos[k + 1][0] in HASTES:
            haste = caixas[k + 1]
            depois = [c for c, _ in lidos[k + 2 : k + 8]]
            continua = not depois or not depois[0] or not depois[0][0].isdigit()
            if haste.x1 - caixa.x2 <= FOLGA * haste.largura and continua:
                novas.append(
                    Caixa(
                        min(caixa.x1, haste.x1),
                        min(caixa.y1, haste.y1),
                        max(caixa.x2, haste.x2),
                        max(caixa.y2, haste.y2),
                    )
                )
                saida.append((char, min(conf, lidos[k + 1][1])))
                k += 2
                continue
        if char == "f1" and _duas_minusculas(lidos, k + 1) and not _e_notacao(_antes(lidos, k)):
            novas.append(caixa)
            saida.append(("fl", conf))
            k += 1
            continue
        novas.append(caixa)
        saida.append((char, conf))
        k += 1
    return (novas, saida)


def _antes(lidos: Sequence[tuple[str, float]], k: int) -> list[str]:
    return [c for c, _ in lidos[max(0, k - 3) : k]]


def _duas_minusculas(lidos: Sequence[tuple[str, float]], k: int) -> bool:
    proximas = [c for c, _ in lidos[k : k + 2]]
    return len(proximas) == 2 and all(len(c) == 1 and c.isalpha() and c.islower() for c in proximas)


__all__ = ["FOLGA", "HASTES", "LIGADO", "QUEM_PERDE_A_HASTE", "corrigir"]
