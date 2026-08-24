"""Ler a linha, e não o caractere — e a confiança que sai da concordância (S-188/S-189).

**É o maior ganho prometido deste plano, e o argumento cabe em três exemplos.** Medido no projeto
de origem, em 6.953 caracteres de 275 linhas rotuladas:

    por caractere (o melhor que o glifo sozinho dá)   72,8%
    por linha, com alinhamento                        91,2%

`Bib1i0g[aPhY` vira `Bibliography`. `F0reW0rd` vira `Foreword`. `LeVe1` vira `Level`. **Nenhum
desses é decidível olhando um glifo de cada vez**: `0` e `o` da mesma fonte diferem em altura, e
`1` e `l` em quase nada. O que resolve é o contexto, e contexto é o que um leitor de linha tem e
um classificador de glifo não.

E o padrão de erro não é herdado: o diagnóstico de 2026-08-22 sobre a página 21 do `AAGAARD`
errou `i`→`1`, `th`→`an`, `ki`→`h` — os mesmos três tipos.

## O alinhamento, e o detalhe que não é opcional

O leitor de linha devolve **uma** string para a faixa inteira; os boxes são muitos. Quem os casa é
a distância de edição, usando a leitura por caractere como **âncora** — ela tem, por construção,
exatamente um item por box.

**Box vazio vira uma marca, e nunca string vazia.** `"".join` de uma lista com um vazio encurta a
string, o índice do alinhamento deixa de ser o índice do box, e **tudo depois dele anda uma
casa**. A marca é um caractere que não existe em página nenhuma e por isso sempre cede a vez.

## A confiança sai da concordância (S-189)

O leitor de linha devolve uma confiança para a faixa inteira. Distribuí-la igual por todos os
boxes seria inventar precisão que ninguém mediu — e este projeto tem o achado gêmeo do outro
lado: a métrica primária da avaliação de agosto **media confiança e não correção**.

    concordam  ->  vale a MAIOR    (uma leitura corrobora a outra)
    divergem   ->  vale a MENOR    (a linha venceu, mas há dúvida real)

A divergência é onde o erro se concentra, e a menor confiança é o que põe o box na fila de
revisão da S-212 — que é exatamente onde ele deve estar.

**E a temperatura é aplicada antes de qualquer comparação.** Duas réguas não calibradas comparadas
entre si não medem o que se pensa: a F25 do projeto de origem mediu que réguas separadas medem
pior, e duas vezes. Aqui o glifo já vem calibrado (S-205); o que este módulo não pode fazer é
comparar confiança crua com confiança calibrada.

## O que **não** entra no modo bloco

Linha girada (S-197) e linha em negativo (S-195) voltam ao modo por caractere. A faixa delas
deixa de ser um retângulo em pé, e endireitar a faixa inteira é outro problema — não este.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .boxes import Caixa

logger = logging.getLogger(__name__)

MARCA = "�"
"""O que um box sem leitura vira na âncora. **Nunca string vazia** — ver o cabeçalho.

`U+FFFD` (REPLACEMENT CHARACTER) porque ele não existe em página impressa nenhuma: o alinhamento
sempre prefere trocá-lo a trocar um caractere de verdade."""


@dataclass(frozen=True)
class Lido:
    """O que sobrou de uma caixa depois das duas leituras."""

    caractere: str
    confianca: float
    do_glifo: str
    do_bloco: str

    @property
    def concordam(self) -> bool:
        return self.do_glifo == self.do_bloco


def ancora(lidos: Sequence[tuple[str, float]]) -> tuple[str, list[int]]:
    """`(a leitura por caractere como string, o box de cada posição dela)`.

    **Um box não é um caractere, e essa foi a primeira coisa que quebrou aqui.** As classes de
    ligadura devolvem dois caracteres para uma caixa só -- `fi`, `xf6`, `♗a` --, então a âncora é
    mais longa que a lista de boxes, e um `zip` estrito entre as duas estoura. Quem casa as duas
    é o índice devolvido ao lado: ele diz, para cada posição da âncora, de que box ela veio.

    Box vazio vira `MARCA`, e nunca string vazia -- ver o cabeçalho.
    """
    texto: list[str] = []
    de_qual_box: list[int] = []
    for posicao, (char, _) in enumerate(lidos):
        pedaco = char or MARCA
        texto.append(pedaco)
        de_qual_box.extend([posicao] * len(pedaco))
    return "".join(texto), de_qual_box


def alinhar(anc: str, do_bloco: str) -> list[str]:
    """Distribui `do_bloco` sobre os boxes de `anc`. Devolve **uma string por box**.

    Distância de edição com retrocesso: cada box recebe o pedaço da string do bloco que o
    alinhamento pôs em cima dele -- que pode ser vazio (o bloco não viu nada ali), um caractere,
    ou mais de um (o bloco leu dois onde a segmentação viu um, que é o caso do glifo colado).

    **A string maior que os boxes não estica a saída**: o excedente vai para o último box, e não
    inventa box novo. Quem conta boxes é a segmentação.
    """
    n, m = len(anc), len(do_bloco)
    if n == 0:
        return []
    if m == 0:
        return [""] * n

    # Matriz de distância. n e m são dezenas nesta aplicação -- uma linha de texto, não um livro.
    custo = np.zeros((n + 1, m + 1), dtype=np.int32)
    custo[:, 0] = np.arange(n + 1)
    custo[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            troca = custo[i - 1, j - 1] + (anc[i - 1] != do_bloco[j - 1])
            custo[i, j] = min(custo[i - 1, j] + 1, custo[i, j - 1] + 1, troca)

    saida = [""] * n
    i, j = n, m
    while i > 0 and j > 0:
        troca = custo[i - 1, j - 1] + (anc[i - 1] != do_bloco[j - 1])
        if custo[i, j] == troca:
            saida[i - 1] = do_bloco[j - 1] + saida[i - 1]
            i, j = i - 1, j - 1
        elif custo[i, j] == custo[i, j - 1] + 1:
            # O bloco leu um caractere que a segmentação não viu: ele fica com o box da esquerda.
            saida[i - 1] = do_bloco[j - 1] + saida[i - 1] if i > 0 else saida[i - 1]
            j -= 1
        else:
            i -= 1  # a segmentação viu um box que o bloco não leu: ele fica vazio
    if j > 0:
        saida[0] = do_bloco[:j] + saida[0]
    return saida


def confianca_por_concordancia(do_glifo: float, do_bloco: float, *, concordam: bool) -> float:
    """`max` quando as duas leituras concordam, `min` quando divergem (S-189).

    **Divergir não é meio-termo.** Uma média esconderia justamente o box em que as duas fontes
    discordam -- que é onde o erro se concentra, e o que a fila de revisão precisa ver primeiro.
    """
    return max(do_glifo, do_bloco) if concordam else min(do_glifo, do_bloco)


def em_bloco(
    cinza: np.ndarray,
    linha: Sequence[Caixa],
    lidos: Sequence[tuple[str, float]],
    leitor: object | None,
    *,
    margem: int = 2,
) -> list[Lido]:
    """As duas leituras casadas, uma `Lido` por box. **Sem leitor, devolve a do glifo intacta.**

    É a mesma regra da S-197 e da S-186: sem o segundo opinante, não mexer. Um leitor de linha
    ausente não é caso de erro -- ele é opcional por desenho (S-42), e o caminho por caractere é
    o que sempre existiu.

    `linha` girada ou vazia também volta pelo caminho de caractere: a faixa deixa de ser um
    retângulo em pé, e endireitá-la é problema da S-197.
    """
    por_caractere = [
        Lido(caractere=char, confianca=conf, do_glifo=char, do_bloco=char) for char, conf in lidos
    ]
    if leitor is None or not linha or len(linha) != len(lidos):
        return por_caractere
    if any(caixa.angulo for caixa in linha):
        logger.debug("Linha girada: o modo bloco não se aplica, e ela volta ao modo por caractere.")
        return por_caractere

    x1 = max(0, min(c.x1 for c in linha) - margem)
    y1 = max(0, min(c.y1 for c in linha) - margem)
    x2 = min(cinza.shape[1], max(c.x2 for c in linha) + margem)
    y2 = min(cinza.shape[0], max(c.y2 for c in linha) + margem)
    recorte = cinza[y1:y2, x1:x2]
    if recorte.size == 0:
        return por_caractere

    texto, confianca_do_bloco = _ler(leitor, recorte)
    if not texto:
        return por_caractere

    anc, de_qual_box = ancora(lidos)
    pedacos = alinhar(anc, texto)
    # Regrupa por box: uma ligadura ocupa duas posições da âncora e continua sendo **uma** caixa.
    por_box = [""] * len(lidos)
    for posicao, pedaco in enumerate(pedacos):
        por_box[de_qual_box[posicao]] += pedaco

    saida: list[Lido] = []
    for (char, conf), pedaco in zip(lidos, por_box, strict=True):
        do_bloco = pedaco or char
        saida.append(
            Lido(
                caractere=do_bloco,
                confianca=confianca_por_concordancia(
                    conf, confianca_do_bloco, concordam=do_bloco == char
                ),
                do_glifo=char,
                do_bloco=do_bloco,
            )
        )
    return saida


def _ler(leitor: object, recorte: np.ndarray) -> tuple[str, float]:
    """`(texto, confiança)` do leitor de linha, ou `("", 0.0)` quando ele não devolve nada.

    O leitor é o protocolo `TextRecognizer` da S-42 -- qualquer um dos quatro motores serve, e a
    escolha de qual é do dono do projeto (ver o `ROADMAP_TEXTO`). Aqui ele é só um chamável que
    devolve `TextBox`; este módulo não importa motor nenhum.
    """
    import cv2

    rgb = cv2.cvtColor(recorte, cv2.COLOR_GRAY2RGB) if recorte.ndim == 2 else recorte
    try:
        caixas = leitor.read(rgb)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - motor de terceiro; a leitura por caractere sobrevive
        logger.exception("O leitor de linha falhou; a linha volta ao modo por caractere.")
        return "", 0.0
    if not caixas:
        return "", 0.0
    texto = " ".join(str(c.text) for c in caixas if str(c.text).strip())
    confianca = min((float(c.confidence) for c in caixas), default=0.0)
    return texto, confianca


__all__ = [
    "MARCA",
    "Lido",
    "alinhar",
    "ancora",
    "confianca_por_concordancia",
    "em_bloco",
]
