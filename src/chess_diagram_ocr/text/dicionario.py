"""O dicionário desempata entre os candidatos do modelo -- e nunca aproxima da palavra parecida.

**Este módulo não é a S-209, e a diferença é o motivo de ele poder existir.** A S-209 decidiu, com
medição, que *"palavra fora do dicionário é sinalizada, nunca aproximada da mais parecida"*: dos 18
lances tão maltratados que escapam do fatiador e caem no léxico, **nenhum** está no dicionário, e
com correção automática seriam 18 lances reescritos como palavra. Essa decisão continua de pé, e
este módulo **não a contraria**, porque ele não faz o que ela proíbe.

## A diferença, em uma frase: aqui o dicionário não propõe nada

A correção por semelhança pergunta *"qual palavra do dicionário se parece com esta?"* e pode
responder qualquer coisa -- é assim que `Nimzowitsch` viraria outra palavra. Aqui a pergunta é
outra: **entre as letras que o próprio classificador já pôs no topo da lista, existe uma
combinação que forma palavra conhecida?** O dicionário só diz sim ou não; quem propõe é sempre o
modelo, e uma letra que ele não considerou nunca entra.

    p/ayer     o modelo já tem `l` em rank 2 naquela caixa  ->  player
    Nimzowitsch   nenhuma troca do top-k forma palavra       ->  sai idêntica

## Quatro guardas, e cada uma tem um caso concreto atrás

1. **Nada com dígito por perto.** É a cicatriz que a S-209 registra: lance maltratado não pode
   virar palavra. Um token com dígito, ou colado a um, não é palavra e não é tocado.
2. **Nada com menos de `MIN_TAMANHO` letras.** `Kf`, `Nc`, `Re` são notação, não palavra -- e elas
   estavam no léxico bruto extraído do acervo até esta régua entrar.
3. **No máximo `MAX_TROCAS` posições mudam.** Sem teto, uma palavra longa alcança meio dicionário.
4. **Ambiguidade não corrige.** Se duas combinações diferentes formam palavras conhecidas, o
   token fica como está: escolher entre elas seria exatamente o palpite que este módulo evita.

## De onde vem o léxico

`assets/lexico/acervo.txt.gz`, 5.617 palavras extraídas da **camada de texto editorada dos 11
livros do acervo que a têm** -- os 20 de camada de OCR ficam de fora, porque trariam os erros do
OCR de terceiro para dentro do dicionário. Uma palavra entra se aparece 3 vezes em 2 livros
distintos, tem 4 letras ou mais e não casa com o padrão de notação.

**Nada baixa da rede**, aqui como no resto do projeto. A contrapartida é que o léxico é do acervo:
palavra que ele não tem simplesmente não é corrigida, o que é o lado seguro do erro.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import PROJECT_ROOT
from .boxes import Caixa

CAMINHO_PADRAO = PROJECT_ROOT / "assets" / "lexico" / "acervo.txt.gz"

MIN_TAMANHO = 4
"""Menos letras que isto não é palavra: é notação. Ver a guarda 2 no cabeçalho."""

MAX_TROCAS = 2
"""Quantas posições podem mudar de uma vez. `wi//` precisa de duas; `p/ayer`, de uma."""

TOPO = 3
"""Quantos candidatos do modelo entram na busca, por posição."""

PISO_DE_CANDIDATO = 0.001
"""Probabilidade mínima para uma alternativa do modelo ser considerada.

Sem piso, a busca inclui classes que o modelo praticamente descartou, e o dicionário passa a
escolher entre ruído -- que é a porta de entrada da correção por semelhança que este módulo
existe para não fazer."""

PALAVRA = re.compile(r"^[A-Za-zÀ-ÿ]+(?:['’-][A-Za-zÀ-ÿ]+)*$")


@lru_cache(maxsize=4)
def carregar(caminho: Path = CAMINHO_PADRAO) -> frozenset[str]:
    """As palavras do léxico, dobradas para minúscula. Vazio quando o arquivo não existe.

    **Ausente não é erro**, e é a mesma regra dos outros recursos opcionais deste projeto: sem
    léxico o leitor devolve o que o modelo leu, que é o que ele sempre fez.

    Em cache porque um livro de 300 páginas o consultaria 300 vezes, e ele não muda entre elas.
    """
    try:
        with gzip.open(caminho, "rt", encoding="utf-8") as fh:
            return frozenset(linha.strip().casefold() for linha in fh if linha.strip())
    except OSError:
        return frozenset()


def conhecida(palavra: str, lexico: frozenset[str]) -> bool:
    """A palavra está no léxico, ignorando caixa? Pontuação nas pontas não é considerada."""
    return palavra.strip(".,;:!?()[]'\"").casefold() in lexico


FRACAO_DE_LETRAS = 0.6
"""Quanto do token tem de ser letra para ele ser candidato a palavra.

**Não pode ser "só letras", e essa foi a primeira coisa que quebrou aqui.** O token que interessa
é justamente o que veio *errado* -- `p/ayer` tem uma barra no meio, e uma régua de só-letras o
rejeita antes de olhar. O que separa palavra de notação não é a pureza: é o dígito (guarda 1) e a
proporção de letras."""


def e_palavra(texto: str) -> bool:
    """Isto é candidato a palavra? Ver as guardas 1 e 2 no cabeçalho.

    Três condições: comprimento, **nenhum dígito** -- é o que mantém lance fora --, e letras na
    maioria. A palavra *lida* pode ter um caractere estranho no meio; é para isso que se corrige.
    """
    limpo = texto.strip(".,;:!?()[]'\"")
    if len(limpo) < MIN_TAMANHO or any(c.isdigit() for c in limpo):
        return False
    letras = sum(1 for c in limpo if c.isalpha())
    return letras / len(limpo) >= FRACAO_DE_LETRAS


def alternativas(
    probs: np.ndarray,
    linha: int,
    idx_to_char: dict[int, str],
    *,
    topo: int = TOPO,
    piso: float = PISO_DE_CANDIDATO,
) -> list[str]:
    """Os caracteres que o modelo pôs no topo para esta caixa, do mais provável ao menos.

    Só caractere **único**: uma ligadura mudaria o comprimento da palavra, e o alinhamento entre
    posição e caixa deixaria de valer no meio da busca.
    """
    if linha >= probs.shape[0]:
        return []
    ordem = np.argsort(-probs[linha])[:topo]
    saida: list[str] = []
    for indice in ordem:
        if probs[linha, indice] < piso:
            break
        char = idx_to_char.get(int(indice), "")
        if len(char) == 1:
            saida.append(char)
    return saida


def variantes(palavra: str, candidatos: Sequence[Sequence[str]], *, max_trocas: int = MAX_TROCAS) -> set[str]:
    """As palavras alcançáveis trocando até `max_trocas` posições pelos candidatos do modelo.

    A palavra original **não** entra no conjunto: o que interessa é o que ela poderia ser, e
    devolvê-la junto faria toda palavra parecer ambígua consigo mesma.
    """
    if len(palavra) != len(candidatos):
        return set()

    achadas: set[str] = set()

    def andar(posicao: int, trocas: int, atual: list[str]) -> None:
        if trocas > max_trocas:
            return
        if posicao == len(palavra):
            nova = "".join(atual)
            if nova != palavra:
                achadas.add(nova)
            return
        # não trocar esta posição
        andar(posicao + 1, trocas, [*atual, palavra[posicao]])
        if trocas == max_trocas:
            return
        for alternativa in candidatos[posicao]:
            if alternativa != palavra[posicao]:
                andar(posicao + 1, trocas + 1, [*atual, alternativa])

    andar(0, 0, [])
    return achadas


def escolher(palavra: str, candidatos: Sequence[Sequence[str]], lexico: frozenset[str]) -> str | None:
    """A única palavra conhecida alcançável, ou `None`. Ver as guardas 3 e 4 no cabeçalho.

    `None` em quatro situações, e as quatro são caminho normal: a palavra já é conhecida, não é
    candidata a palavra, nenhuma variante é conhecida, ou **mais de uma** é. A última é a guarda
    da ambiguidade -- escolher entre duas seria o palpite que este módulo evita.
    """
    if not lexico or not e_palavra(palavra) or conhecida(palavra, lexico):
        return None
    conhecidas = {v for v in variantes(palavra, candidatos) if conhecida(v, lexico)}
    return conhecidas.pop() if len(conhecidas) == 1 else None


def palavras(caixas: Sequence[Caixa], lidos: Sequence[tuple[str, float]]) -> list[tuple[int, int]]:
    """Os trechos `[inicio, fim)` de caixas que formam uma palavra, pela mesma régua do espaço.

    A régua é a de `linhas.texto_da_linha` -- vão maior que `VAO_DE_ESPACO` larguras medianas
    separa palavras --, e é ela de propósito: se as duas discordassem, o dicionário corrigiria um
    recorte que não é o que sai no texto.
    """
    from .linhas import VAO_DE_ESPACO

    if not caixas or len(caixas) != len(lidos):
        return []
    larguras = sorted(c.largura for c in caixas)
    limite = VAO_DE_ESPACO * (larguras[len(larguras) // 2] or 1)

    trechos: list[tuple[int, int]] = []
    inicio = 0
    for i in range(1, len(caixas)):
        if caixas[i].x1 - caixas[i - 1].x2 > limite:
            trechos.append((inicio, i))
            inicio = i
    trechos.append((inicio, len(caixas)))
    return trechos


def corrigir(
    lidos: Sequence[tuple[str, float]],
    probs: np.ndarray,
    caixas: Sequence[Caixa],
    idx_to_char: dict[int, str],
    lexico: frozenset[str],
    *,
    topo: int = TOPO,
    max_trocas: int = MAX_TROCAS,
) -> list[tuple[str, float]]:
    """Corrige as palavras da linha que o léxico decide, e devolve `(caractere, confiança)`.

    **Palavra com ligadura é pulada**, e não é preguiça: uma caixa que devolve dois caracteres faz
    o índice da palavra deixar de casar com o índice da caixa, e a troca cairia na posição errada.

    A confiança devolvida é a da classe escolhida, como nos módulos irmãos -- e onde a letra não
    mudou, a confiança original é preservada intacta.
    """
    if not lidos or not lexico or len(lidos) != len(caixas):
        return list(lidos)

    de_char = {c: i for i, c in idx_to_char.items() if len(c) == 1}
    saida = list(lidos)
    for inicio, fim in palavras(caixas, lidos):
        pedaco = [c for c, _ in lidos[inicio:fim]]
        if any(len(c) != 1 for c in pedaco):
            continue
        palavra = "".join(pedaco)
        candidatos = [
            alternativas(probs, inicio + i, idx_to_char, topo=topo) for i in range(fim - inicio)
        ]
        escolhida = escolher(palavra, candidatos, lexico)
        if escolhida is None or len(escolhida) != len(palavra):
            continue
        for i, novo in enumerate(escolhida):
            if novo == palavra[i]:
                continue
            indice = de_char.get(novo)
            confianca = float(probs[inicio + i, indice]) if indice is not None else 0.0
            saida[inicio + i] = (novo, confianca)
    return saida


__all__ = [
    "CAMINHO_PADRAO",
    "FRACAO_DE_LETRAS",
    "MAX_TROCAS",
    "MIN_TAMANHO",
    "PISO_DE_CANDIDATO",
    "TOPO",
    "alternativas",
    "carregar",
    "conhecida",
    "corrigir",
    "e_palavra",
    "escolher",
    "palavras",
    "variantes",
]
