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

import gzip
import re
from collections.abc import Iterator, Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import PROJECT_ROOT
from .boxes import Caixa

PASTA_DO_LEXICO = PROJECT_ROOT / "assets" / "lexico"

CAMINHO_ACERVO = PASTA_DO_LEXICO / "acervo.txt.gz"
CAMINHO_IDIOMA = PASTA_DO_LEXICO / "idioma.txt.gz"
CAMINHO_NOMES = PASTA_DO_LEXICO / "nomes.txt.gz"

CAMINHO_PADRAO = CAMINHO_ACERVO
"""O nome antigo do arquivo do acervo, quando ele era o único. Mantido para quem o importa."""

EMPACOTADOS = (CAMINHO_ACERVO, CAMINHO_IDIOMA, CAMINHO_NOMES)
"""Os três arquivos que `carregar()` sem argumento une. Ver a tabela no cabeçalho."""

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


@lru_cache(maxsize=8)
def carregar(caminho: Path | None = None, *, nomes: bool = True) -> frozenset[str]:
    """As palavras do léxico, dobradas para minúscula. Vazio quando não há arquivo nenhum.

    Sem argumento são **as listas empacotadas do projeto**, unidas: acervo, idioma e nomes. Com um
    caminho é aquele arquivo e só ele -- é como a medição compara uma lista contra outra.

    `nomes=False` deixa a lista de nomes próprios de fora. A escolha existe porque a S-209 a mediu:
    nome próprio baixa o alarme falso de 12,1% para 5,8% **e esconde erro**, e quem sabe o perfil
    do livro é quem chama. O padrão os inclui -- medido em 40 páginas, eles não mudam um caractere
    do que sai, e protegem 73 palavras de serem tocadas. Ver o cabeçalho.

    **Ausente não é erro**, e é a mesma regra dos outros recursos opcionais deste projeto: sem
    léxico o leitor devolve o que o modelo leu, que é o que ele sempre fez.

    Em cache porque um livro de 300 páginas o consultaria 300 vezes, e ele não muda entre elas.
    """
    if caminho is not None:
        return _de_um_arquivo(caminho)
    escolhidos = EMPACOTADOS if nomes else tuple(c for c in EMPACOTADOS if c != CAMINHO_NOMES)
    return frozenset().union(*(_de_um_arquivo(c) for c in escolhidos))


def _de_um_arquivo(caminho: Path) -> frozenset[str]:
    """Um `.txt.gz` de uma palavra por linha, ou o conjunto vazio se ele não estiver lá."""
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


PONTUACAO_DE_BORDA = ".,;:!?()[]'\""
"""O que se apara das pontas de um token antes de perguntar se ele é palavra.

Uma constante, e não o literal repetido em `e_palavra` e em `desconhecidas`: as duas têm de aparar
**a mesma coisa**, senão a conferência marca `[Diagrama` e a correção não o vê -- duas réguas sobre
o mesmo token, que é o defeito que este projeto persegue nos rótulos e nas tabelas de tecla."""


def e_palavra(texto: str) -> bool:
    """Isto é candidato a palavra? Ver as guardas 1 e 2 no cabeçalho.

    Três condições: comprimento, **nenhum dígito** -- é o que mantém lance fora --, e letras na
    maioria. A palavra *lida* pode ter um caractere estranho no meio; é para isso que se corrige.
    """
    limpo = texto.strip(PONTUACAO_DE_BORDA)
    if len(limpo) < MIN_TAMANHO or any(c.isdigit() for c in limpo):
        return False
    letras = sum(1 for c in limpo if c.isalpha())
    return letras / len(limpo) >= FRACAO_DE_LETRAS


def palavras_de(texto: str) -> tuple[str, ...]:
    """Os tokens de `texto` que **são palavra** por `e_palavra`, já aparados (S-266).

    É o denominador da conferência: "3 fora do léxico" não diz nada sem "de 412". Sai do mesmo laço
    de `desconhecidas`, porque duas contagens com réguas diferentes dariam uma fração que não fecha.

    **`MIN_TAMANHO` vale aqui também**, e por isso `the` e `of` não entram na conta: a guarda 2
    existe para manter `Kf` e `Nc` fora, e afrouxá-la só para o denominador faria a fração medir
    duas coisas."""
    return tuple(palavra for _inicio, _fim, palavra in _tokens_de_palavra(texto))


def _tokens_de_palavra(texto: str) -> Iterator[tuple[int, int, str]]:
    """`(inicio, fim, palavra aparada)` de cada token que é candidato a palavra.

    O intervalo é o da palavra **aparada**, e não o do token bruto: numa marca `[Diagrama 3]` o que
    se conferiria seria `[Diagrama`, e o que se sublinharia na tela incluiria o colchete."""
    for casamento in _TOKEN.finditer(texto):
        bruto = casamento.group()
        limpo = bruto.strip(PONTUACAO_DE_BORDA)
        if not limpo or not e_palavra(limpo):
            continue
        inicio = casamento.start() + (len(bruto) - len(bruto.lstrip(PONTUACAO_DE_BORDA)))
        yield (inicio, inicio + len(limpo), limpo)


def desconhecidas(
    texto: str,
    lexico: frozenset[str],
    *,
    ignorar: Sequence[tuple[int, int]] = (),
) -> tuple[tuple[int, int, str], ...]:
    """Os trechos de `texto` que são palavra e o léxico **não** conhece (S-266).

    Devolve `(inicio, fim, palavra)` em deslocamento de caractere -- que é a moeda das ferramentas
    do editor (`text/rico.py`). Não propõe nada, não ordena por semelhança e não olha o modelo: é a
    pergunta mais simples que este módulo sabe responder, e é a única que a S-209 autoriza sobre
    texto já lido. *"Palavra fora do dicionário é sinalizada, nunca aproximada da mais parecida."*

    **O que não é palavra fica de fora**, e é `e_palavra` quem decide: `Nf3`, `1.d4` e `15` não são
    candidatos a nada. Sem essa guarda a folha inteira ficaria marcada, e uma marcação que acende em
    tudo não distingue coisa nenhuma.

    `ignorar` são intervalos que não se confere, e o cliente é a aba de texto: `[Diagrama 3]` é
    **referência ao diagrama**, e não texto do livro. Conferir a marca marcaria uma palavra que o
    programa escreveu, e o aviso seria sobre o próprio programa. Fica como parâmetro em vez de uma
    regra aqui dentro porque quem sabe o que é marca é o documento, e este módulo não o conhece.

    **A caixa não é conferida aqui.** O léxico compara em `casefold`, então `poSition` passa como
    conhecida -- e é o certo: quem separa `s` de `S` é a altura do box na S-211, com medição, e uma
    segunda régua discordando dela na tela seria pior que nenhuma.
    """
    vetados = tuple((min(a, b), max(a, b)) for a, b in ignorar)
    achados: list[tuple[int, int, str]] = []
    for inicio, fim, palavra in _tokens_de_palavra(texto):
        if conhecida(palavra, lexico):
            continue
        if any(inicio < veto_fim and fim > veto_inicio for veto_inicio, veto_fim in vetados):
            continue
        achados.append((inicio, fim, palavra))
    return tuple(achados)


_TOKEN = re.compile(r"[^\s]+")
r"""O que se separa por espaço. **Não** é `\w+`: `Black's` e `Saint-Amant` são um token só, e é
assim que `PALAVRA` e `e_palavra` já os leem."""


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


__all__ = [
    "CAMINHO_ACERVO",
    "CAMINHO_IDIOMA",
    "CAMINHO_NOMES",
    "CAMINHO_PADRAO",
    "EMPACOTADOS",
    "FRACAO_DE_LETRAS",
    "MAX_TROCAS",
    "MIN_TAMANHO",
    "PISO_DE_CANDIDATO",
    "PONTUACAO_DE_BORDA",
    "TOPO",
    "alternativas",
    "carregar",
    "conhecida",
    "corrigir",
    "desconhecidas",
    "palavras_de",
    "e_palavra",
    "escolher",
    "palavras",
    "variantes",
]
