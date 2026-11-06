"""O texto espaçado (*gesperrt*), que é ênfase e não são letras soltas (S-744).

**Quem sofre é o glifo, e não o Tesseract.** O livro alemão de 1922 enfatiza espaçando as letras, e o vão entre elas passa do
`linhas.VAO_DE_ESPACO`: `k o m b i n i e r t e`, `F i gu re n`, `e i n e r fe i nd li ch e n`. Em seis folhas do *Gutmayer*, o
Tesseract lê a palavra inteira; o glifo, que é o padrão, sai letra a letra. A camada de terceiro do mesmo livro tem 737 corridas,
e não se toca nela: a camada é referência.

**O léxico é o critério, e a régua é só de texto.** Uma corrida é a sequência de ao menos `MIN_TOKENS` tokens de uma ou duas letras,
com metade de uma letra só: `in der Zeit` não é corrida, e `Fi g u r` é. O que ela vira:

- **uma palavra**, se a corrida inteira está no léxico;
- **várias**, se dá para cobri-la inteira com palavras conhecidas de um jeito só que seja o de menos pedaços: `d e r B a u e r`
  vira `der Bauer`, e o espaço entre as duas fica, porque o vão entre palavra e letra se perdeu e quem as separa é o léxico;
- **nada**, se sobra letra. É de propósito: a primeira versão reconhecia a palavra no meio da corrida, deixando o resto, e leu
  `d e s H a n d e 1 n s` como `d e sHan d e 1 n s`, `a. n O h n` como `a. nOhn`, `g e i n e s` como `gein e s`. Sobre o glifo, a
  corrida vem com erro, e o léxico de 396 mil palavras e nomes acha alguma coisa em quase toda sequência de letras.

**A maiúscula abre palavra**, salvo na corrida toda em maiúsculas: `Fi g u r i m N o f.` são duas corridas, e a primeira vira
`Figur im` sem precisar da segunda. Na palavra, a caixa tem de ser a de uma palavra: `sHan` não é.

**Nunca junta duas palavras**: a junção só existe se ela mesma é uma palavra da lista, e `M itte l u n d Z we ck` não vira `lund`:
sem o `l` a palavra ainda existe, e o `itte` ao lado não é palavra. Na dúvida entre duas coberturas fica como estava. Sem lista para a língua nada acontece, porque aproximar é a decisão recusada da S-209.

A régua não acha a palavra errada: `1 e b e n d i g` tem um dígito e fica, porque o léxico não a conhece. E `z u` fica: duas letras
não bastam, e `a o`, `e a` e `y a` são prosa.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache

from . import lexico as _lexico

JUNTAR_ESPACADO = True
"""A reversão da S-744: desligada, o texto sai como foi lido."""

MIN_TOKENS = 3
"""Menos tokens que isto é prosa: `a o`, `e a`."""

_ABRE = "([„\"'«»‚“"
_FECHA = ".,;:!?)]\"'«»“”’"
_TOKEN = re.compile(rf"^([{re.escape(_ABRE)}]?)([^\W\d_]{{1,2}})([{re.escape(_FECHA)}]*)$")


def _partes(token: str) -> tuple[str, str, str] | None:
    achado = _TOKEN.match(token)
    return (achado.group(1), achado.group(2), achado.group(3)) if achado else None


def _e_fila_de_casas(letras: Sequence[str]) -> bool:
    """`a b c d`, `h g f e`: fileira de coordenadas, que o `do_livro` conhece como nome (`abcd`)."""
    if len(letras) < 2 or any(len(p) != 1 or p not in "abcdefgh" for p in letras):
        return False
    passos = {ord(b) - ord(a) for a, b in zip(letras, letras[1:], strict=False)}
    return passos in ({1}, {-1})


def _parece_palavra(escrita: str) -> bool:
    """A caixa de uma palavra, e mais de uma letra diferente: `sHan` e `oooo` estão na lista dos nomes."""
    return len(set(escrita.casefold())) > 1 and (escrita.islower() or escrita.isupper() or escrita.istitle())


def _cobertura(
    letras: Sequence[str], conhece: frozenset[str], so_da_lingua: frozenset[str], curtas: frozenset[str]
) -> list[int] | None:
    """Os fins de pedaço da cobertura inteira de menos pedaços. `None` sem cobertura; `[]` com duas empatadas."""
    n = len(letras)
    # `melhor[i]` é (pedaços, quantas coberturas com esse número, de onde veio) até o token `i`.
    melhor: list[tuple[int, int, int]] = [(0, 1, -1)] + [(n + 1, 0, -1)] * n
    for fim in range(1, n + 1):
        for inicio in range(fim):
            escrita = "".join(letras[inicio:fim])
            palavra = escrita.casefold()
            # **O nome só vale com maiúscula**: `l u n d` é `Handel und` partido, e `Lund` está na lista dos nomes.
            lista = conhece if escrita[0].isupper() else so_da_lingua
            if len(palavra) < 2 or not (palavra in lista or palavra in curtas) or not _parece_palavra(escrita):
                continue
            pedacos, modos, _ = melhor[inicio]
            if not modos:
                continue
            atual = melhor[fim]
            if pedacos + 1 < atual[0]:
                melhor[fim] = (pedacos + 1, modos, inicio)
            elif pedacos + 1 == atual[0]:
                melhor[fim] = (atual[0], atual[1] + modos, atual[2])
    if melhor[n][1] == 0:
        return None
    if melhor[n][1] > 1:
        return []
    fins = []
    fim = n
    while fim > 0:
        fins.append(fim)
        fim = melhor[fim][2]
    return fins[::-1]


def _letra_da_vizinha(resto: str, vizinha: str, lista: frozenset[str], curtas: frozenset[str]) -> bool:
    """A letra da ponta é da palavra ao lado? `M itte l u n d`: sem o `l` sobra a palavra curta `und`, e `itte` não é palavra.

    **Só a palavra curta**: com a longa, `eines` cairia junto de qualquer vizinha mal lida, porque `eine` também existe.
    """
    limpa = vizinha.strip(_ABRE + _FECHA).casefold()
    if not limpa or not any(c.isalnum() for c in limpa) or limpa in lista or limpa in curtas:
        return False
    return resto in curtas


def _partir_na_maiuscula(letras: Sequence[str]) -> list[tuple[int, int]]:
    """Os trechos da corrida, cada um começando numa maiúscula. A corrida toda em maiúsculas é um trecho só."""
    if all(p.isupper() for p in letras):
        return [(0, len(letras))]
    inicios = [0, *(i for i in range(1, len(letras)) if letras[i][0].isupper())]
    return list(zip(inicios, [*inicios[1:], len(letras)], strict=True))


def _uma_corrida(
    tokens: Sequence[str],
    conhece: frozenset[str],
    so_da_lingua: frozenset[str],
    curtas: frozenset[str],
    *,
    antes: str = "",
    depois: str = "",
) -> list[str]:
    partes = [_partes(t) for t in tokens]
    letras = [p[1] for p in partes if p is not None]
    if _e_fila_de_casas(letras):
        return list(tokens)

    def montar(inicio: int, fim: int) -> str:
        abre = partes[inicio][0]  # type: ignore[index]
        fecha = partes[fim - 1][2]  # type: ignore[index]
        return abre + "".join(letras[inicio:fim]) + fecha

    saida: list[str] = []
    for de, ate in _partir_na_maiuscula(letras):
        trecho = letras[de:ate]
        # **O nome só vale com o trecho todo de uma letra**: `Y a su` é prosa, e `Yasu` está na lista dos nomes.
        nomes = conhece if all(len(p) == 1 for p in trecho) else so_da_lingua
        fins = _cobertura(trecho, nomes, so_da_lingua, curtas) if len(trecho) >= 2 else None
        if not fins:
            saida.extend(tokens[de:ate])
            continue
        primeira = "".join(trecho[: fins[0]]).casefold()
        ultima = "".join(trecho[(fins[-2] if len(fins) > 1 else 0) :]).casefold()
        if (de == 0 and _letra_da_vizinha(primeira[1:], antes, so_da_lingua, curtas)) or (
            ate == len(letras) and _letra_da_vizinha(ultima[:-1], depois, so_da_lingua, curtas)
        ):
            saida.extend(tokens[de:ate])
            continue
        inicio = de
        for fim in fins:
            saida.append(montar(inicio, de + fim))
            inicio = de + fim
    return saida


def juntar(
    texto: str,
    conhece: frozenset[str],
    *,
    so_da_lingua: frozenset[str] | None = None,
    curtas: frozenset[str] = frozenset(),
) -> str:
    """O texto com as corridas espaçadas que o léxico reconhece refeitas. Ver o cabeçalho.

    `conhece` é a lista com os nomes, que só vale para palavra com maiúscula e corrida toda de uma letra; `so_da_lingua`, a do
    resto, e `None` é a mesma.
    """
    if not JUNTAR_ESPACADO or not conhece or " " not in texto:
        return texto
    lingua = conhece if so_da_lingua is None else so_da_lingua
    tokens = texto.split(" ")
    saida: list[str] = []
    i = 0
    while i < len(tokens):
        fim = i
        # A pontuação de fechar termina a corrida, e a de abrir só pode vir no começo dela.
        while fim < len(tokens):
            parte = _partes(tokens[fim])
            if parte is None or (fim > i and parte[0]):
                break
            fim += 1
            if parte[2]:
                break
        corrida = tokens[i:fim]
        letras = [p[1] for p in map(_partes, corrida) if p is not None]
        if len(corrida) >= MIN_TOKENS and 2 * sum(len(p) == 1 for p in letras) >= len(letras):
            antes = tokens[i - 1] if i else ""
            depois = tokens[fim] if fim < len(tokens) else ""
            saida.extend(_uma_corrida(corrida, conhece, lingua, curtas, antes=antes, depois=depois))
            i = fim
        else:
            saida.append(tokens[i])
            i += 1
    return " ".join(saida)


@lru_cache(maxsize=8)
def _listas(lingua: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    from .fusao import CURTAS_POR_LINGUA
    from .palavras_curtas import CURTAS

    return (_lexico.do_livro(lingua), _lexico.da_lingua(lingua), CURTAS_POR_LINGUA.get(lingua, CURTAS))


def juntar_na_lingua(texto: str, lingua: str) -> str:
    """`juntar` com as listas da língua do livro (S-723, S-728). Língua sem lista: o texto como veio."""
    conhece, so_da_lingua, curtas = _listas(lingua)
    return juntar(texto, conhece, so_da_lingua=so_da_lingua, curtas=curtas)


def intervalos_depois(
    antes: str, depois: str, intervalos: Sequence[tuple[int, int]]
) -> tuple[tuple[int, int], ...]:
    """Os intervalos de `antes` no texto de `depois`, que só tirou espaços."""
    if not intervalos or antes == depois:
        return tuple(intervalos)
    mapa: list[int] = []
    j = 0
    for char in antes:
        if j < len(depois) and depois[j] == char:
            mapa.append(j)
            j += 1
        else:
            mapa.append(j)
    mapa.append(j)
    return tuple((mapa[a], max(mapa[a], mapa[b - 1] + 1)) for a, b in intervalos)


__all__ = [
    "JUNTAR_ESPACADO",
    "MIN_TOKENS",
    "intervalos_depois",
    "juntar",
    "juntar_na_lingua",
]
