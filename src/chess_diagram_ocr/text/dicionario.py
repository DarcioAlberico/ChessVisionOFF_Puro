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

## De onde vem o léxico: três arquivos, três procedências

| arquivo | palavras | de onde |
|---|---:|---|
| `acervo.txt.gz` | 6.947 | camada de texto **editorada** dos 11 livros do acervo que a têm |
| `idioma.txt.gz` | 10.002 | as listas de palavras entregues, o que começa em minúscula |
| `nomes.txt.gz` | 150.186 | as mesmas listas, o que começa em maiúscula: jogador, cidade, torneio |

União, depois do `casefold`: **164.723** palavras.

O `acervo` sai da camada editorada e **não** dos 20 livros de camada de OCR, que trariam os erros
do OCR de terceiro para dentro do dicionário; uma palavra entra se aparece 3 vezes em 2 livros
distintos. Os outros dois saem de `cvoff-texto-lexico`, que empacota uma pasta de listas -- trocar
a lista não é mexer em código, que é o que a S-209 pede.

**Nada baixa da rede**, aqui como no resto do projeto.

### O que as listas mudaram, medido em 40 páginas de 11 livros

**Nenhum caractere.** As correções são as mesmas 6 com o acervo sozinho e com os três arquivos
juntos, e o CER fica em 0,1181 nos três casos. O que muda é o balde em que cada palavra cai:

    palavra já conhecida        2.428 -> 2.467 -> 2.489     (+61)
    nenhuma variante conhecida    255 ->   216 ->   195     (-60)
                                acervo  +idioma  +nomes

**E isso é ganho, ainda que o texto saia igual.** A primeira guarda de `escolher` é *a palavra já
está no léxico?* -- e palavra conhecida é palavra que este módulo **nunca reescreve**. As 61 que
mudaram de balde deixaram de ser candidatas a correção: o léxico maior protege o que já estava
certo, e é por isso que `Nimzowitsch` agora está no arquivo em vez de depender da sorte da busca.

Essa proteção não é hipótese: na sonda de uma regra que **apagasse** o apóstrofo -- regra que não
entrou --, o acervo sozinho reescrevia `Let's` como `Lets`, e com as listas `let's` já é palavra
conhecida e o token nem chega a ser candidato. A busca de hoje só **troca** letra, então ela não
alcançaria essa reescrita de qualquer forma; o que a sonda mostra é o que o léxico maior evita
quando a busca cresce.

**O que as listas não trazem é correção nova**, e a razão está medida em
`docs/metrics/texto_dicionario.json`: o que sobra errado precisa de *inserção* ou *remoção* de
letra -- o `i` em itálico que a segmentação parte em `l` + `'` (`técnl'ca`), a palavra colada
(`ofthe`), a hifenização na quebra de linha --, e esta busca só **troca** letra por letra. Nenhuma
lista conserta isso; a caixa do pingo, sim.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from . import lexico as _lexico
from .boxes import Caixa

# **As constantes e as perguntas puras sobre palavra moram em `text/lexico.py`** (S-209), e são
# importadas aqui em vez de repetidas. A fronteira: lá está o que o dicionário **sabe** e o que ele
# **decide sozinho** (a lista, a palavra desconhecida, a hifenizada da quebra de linha); aqui está
# o que ele **desempata** entre os candidatos que o modelo já pôs no topo. Duas cópias de
# `e_palavra` divergiriam no primeiro ajuste, e a divergência sairia como marca na tela discordando
# da correção no texto -- o mesmo defeito que este projeto persegue nos rótulos e nas teclas.
from .lexico import (
    CAMINHO_ACERVO,
    CAMINHO_IDIOMA,
    CAMINHO_NOMES,
    CAMINHO_PADRAO,
    EMPACOTADOS,
    FRACAO_DE_LETRAS,
    MIN_TAMANHO,
    PALAVRA,
    PASTA_DO_LEXICO,
    PONTUACAO_DE_BORDA,
    conhecida,
    desconhecidas,
    e_palavra,
    palavras_de,
)

__all__ = [
    # **Um `__all__` só, e é este (S-316).** Havia um segundo no fim do arquivo, e como ele era
    # o último a ser executado, era ele que valia -- sem `PALAVRA` e sem `PASTA_DO_LEXICO`, os
    # dois nomes que este módulo reexporta de `text/lexico.py` de propósito, para que quem lê o
    # dicionário não precise saber que a régua de palavra mora ao lado.
    "CAMINHO_ACERVO",
    "CAMINHO_IDIOMA",
    "CAMINHO_NOMES",
    "CAMINHO_PADRAO",
    "EMPACOTADOS",
    "FRACAO_DE_LETRAS",
    "MAX_TROCAS",
    "MIN_TAMANHO",
    "PALAVRA",
    "PASTA_DO_LEXICO",
    "PISO_DE_CANDIDATO",
    "PONTUACAO_DE_BORDA",
    "TOPO",
    "alternativas",
    "carregar",
    "conhecida",
    "corrigir",
    "desconhecidas",
    "e_palavra",
    "escolher",
    "palavras",
    "palavras_de",
    "variantes",
]

MAX_TROCAS = 2
"""Quantas posições podem mudar de uma vez. `wi//` precisa de duas; `p/ayer`, de uma."""

TOPO = 3
"""Quantos candidatos do modelo entram na busca, por posição."""

PISO_DE_CANDIDATO = 0.001
"""Probabilidade mínima para uma alternativa do modelo ser considerada.

Sem piso, a busca inclui classes que o modelo praticamente descartou, e o dicionário passa a
escolher entre ruído -- que é a porta de entrada da correção por semelhança que este módulo
existe para não fazer."""


def carregar(caminho: Path | None = None, *, nomes: bool = True) -> frozenset[str]:
    """As palavras do léxico. **É `lexico.carregar` com a assinatura que este módulo sempre teve.**

    Fica como envoltório em vez de virar um alias porque `nomes: bool` é o que os chamadores deste
    módulo escrevem desde a S-209, e trocá-los por `perfil=` mudaria seis lugares para não mudar
    nada. O perfil é a forma nova, e é ela que `PERFIS` documenta.
    """
    return _lexico.carregar("completo" if nomes else "sem-nomes", caminho=caminho)


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


def escolher(
    palavra: str,
    candidatos: Sequence[Sequence[str]],
    lexico: frozenset[str],
    *,
    max_trocas: int = MAX_TROCAS,
) -> str | None:
    """A única palavra conhecida alcançável, ou `None`. Ver as guardas 3 e 4 no cabeçalho.

    `None` em quatro situações, e as quatro são caminho normal: a palavra já é conhecida, não é
    candidata a palavra, nenhuma variante é conhecida, ou **mais de uma** é. A última é a guarda
    da ambiguidade -- escolher entre duas seria o palpite que este módulo evita.

    **`max_trocas` chega até aqui de propósito.** `corrigir` sempre teve o parâmetro e nunca o
    repassava: quem pedisse um teto diferente recebia o teto padrão em silêncio, e a medição que
    varresse o teto mediria sempre a mesma coisa.
    """
    if not lexico or not e_palavra(palavra) or conhecida(palavra, lexico):
        return None
    conhecidas = {
        v for v in variantes(palavra, candidatos, max_trocas=max_trocas) if conhecida(v, lexico)
    }
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
        escolhida = escolher(palavra, candidatos, lexico, max_trocas=max_trocas)
        if escolhida is None or len(escolhida) != len(palavra):
            continue
        for i, novo in enumerate(escolhida):
            if novo == palavra[i]:
                continue
            indice = de_char.get(novo)
            confianca = float(probs[inicio + i, indice]) if indice is not None else 0.0
            saida[inicio + i] = (novo, confianca)
    return saida

