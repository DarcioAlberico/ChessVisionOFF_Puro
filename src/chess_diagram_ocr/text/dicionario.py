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

## Seis guardas, e cada uma tem um caso concreto atrás

1. **Dígito só passa quando o modelo o desmente.** Era *"nada com dígito por perto"*, pela
   cicatriz que a S-209 registra -- lance maltratado não pode virar palavra. A S-508 estreitou:
   o dígito é perdoado quando o **próprio classificador** oferece uma letra para aquela caixa, e
   o token não é notação por `notacao.peso_de_notacao`. Ver `candidata`.
2. **Nada com menos de `MIN_TAMANHO` letras.** `Kf`, `Nc`, `Re` são notação, não palavra -- e elas
   estavam no léxico bruto extraído do acervo até esta régua entrar.
3. **No máximo `MAX_TROCAS` posições mudam.** Sem teto, uma palavra longa alcança meio dicionário.
4. **Ambiguidade não corrige.** Se duas combinações diferentes formam palavras conhecidas, o
   token fica como está: escolher entre elas seria exatamente o palpite que este módulo evita.
5. **Meia palavra não é palavra.** Token terminado em hífen é a metade que a quebra de linha
   deixou; quem junta as duas é `lexico.juntar_hifenizadas` (S-353), e só então há o que corrigir.
6. **Caixa não é decisão de dicionário.** A alternativa que é a mesma letra em outra caixa sai da
   busca: quem decide maiúscula é a altura do box, em `caixa_alta`, e ela já decidiu. Ver
   `sem_troca_de_caixa`.

## O par `l`/`1`, e por que ele precisou das guardas 1 e 6 (S-508)

Depois do resize para 32x32 o `l` e o `1` são a mesma imagem, e o classificador escolhe por
frequência. Medido na folha 11 do `Nunn - Secrets of Minor Piece Endings`, o modelo põe `l` em
**rank 2 em todas** as 22 caixas em que escreveu `1` dentro de palavra -- a resposta certa sempre
esteve à mão, e duas guardas a barravam:

    on1y  B1ack  whi1e  resu1t  sett1e  va1id  b1ockading  actua11y  natura1  de1ay

A guarda 1 barrava o token inteiro, por causa do dígito. A guarda 4 barrava o resto: `conhecida`
dobra para minúscula antes de olhar o léxico, então `reSult` e `result` chegavam à ambiguidade
como duas respostas, e 13 dos 22 morriam aí.

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

import unicodedata
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
    HIFENS,
    MIN_TAMANHO,
    PALAVRA,
    PASTA_DO_LEXICO,
    PONTUACAO_DE_BORDA,
    conhecida,
    desconhecidas,
    e_palavra,
    palavras_de,
    suspeita,
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
    "candidata",
    "carregar",
    "conhecida",
    "corrigir",
    "desconhecidas",
    "e_palavra",
    "escolher",
    "palavras",
    "palavras_de",
    "sem_troca_de_caixa",
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


def candidata(palavra: str, candidatos: Sequence[Sequence[str]]) -> bool:
    """Este token é candidato a correção? Ver as guardas 1 e 5 do cabeçalho (S-508).

    Duas portas. A de sempre é `e_palavra`, que proíbe **qualquer** dígito. A segunda abre só para
    o dígito que **o próprio classificador escreveu**: se o modelo oferece uma letra para aquela
    caixa, o dígito é palpite dele e não tinta do livro, e o token volta a ser palavra.

    A porta larga é a de `lexico.suspeita` -- comprimento, fração de letras e `peso_de_notacao`,
    que é a régua de notação medida pela S-208. Ela não bastava sozinha para a correção, e o
    cabeçalho de lá diz por quê: *"corrigir um lance por engano custa um lance reescrito no PGN"*.
    O que autoriza usá-la aqui é a segunda condição, que a S-208 não tinha à mão -- ela é sobre o
    modelo, e não sobre o texto.
    """
    if _meia_palavra(palavra):
        return False
    if e_palavra(palavra):
        return True
    return _digito_do_classificador(palavra, candidatos)


def _meia_palavra(palavra: str) -> bool:
    """Termina em hífen? Então é a metade que a quebra de linha deixou, e não uma palavra.

    **Meia palavra não está no dicionário, e o que se alcança a partir dela é lixo.** Medido em 4
    folhas do `Nunn`: `interest-` virava `interest`, `combina-` virava `combina` e `sim-` virava
    `simI` -- o hífen sumia ou virava letra. Quem junta as duas metades é `lexico.juntar_hifenizadas`
    (S-353), depois, e ali a palavra inteira passa por este mesmo dicionário.
    """
    return bool(palavra) and palavra.strip(PONTUACAO_DE_BORDA).endswith(tuple(HIFENS))


def _digito_do_classificador(palavra: str, candidatos: Sequence[Sequence[str]]) -> bool:
    """Todo dígito deste token tem uma **letra** entre os candidatos do modelo para aquela caixa?

    É o que separa `on1y` de `e5.knight`: no primeiro o modelo põe `l` em rank 2 na caixa do `1`;
    no segundo o `5` é o único candidato, e é tinta do livro.

    **As duas perguntas são feitas sobre strings diferentes, e é isso que faz a régua funcionar.**
    Comprimento e fração de letras são sobre a palavra que o modelo oferece -- `wi11` tem metade de
    dígitos e seria recusada pela fração, enquanto `will` passa. *Isto é notação?* é sobre o que
    está escrito na folha: `Rxd1` vira `Rxdl` ao trocar o dígito, e `Rxdl` não é lance nenhum --
    perguntar sobre a troca perderia justamente o lance que a guarda existe para proteger.
    """
    from .notacao import peso_de_notacao

    provavel = _desmentindo_os_digitos(palavra, candidatos)
    return provavel is not None and peso_de_notacao(palavra) == 0 and suspeita(provavel)


def _desmentindo_os_digitos(
    palavra: str, candidatos: Sequence[Sequence[str]]
) -> str | None:
    """O token com cada dígito trocado pela melhor letra que o modelo ofereceu para a caixa dele.

    `None` quando algum dígito não tem letra nenhuma no topo -- aí ele é do livro --, e também
    quando não há dígito: sem dígito a pergunta é de `e_palavra`, e ela já foi feita.
    """
    deslocamento = len(palavra) - len(palavra.lstrip(PONTUACAO_DE_BORDA))
    limpo = palavra.strip(PONTUACAO_DE_BORDA)
    saida: list[str] = []
    achou = False
    for i, char in enumerate(limpo):
        if not char.isdigit():
            saida.append(char)
            continue
        achou = True
        posicao = deslocamento + i
        alternativas = candidatos[posicao] if posicao < len(candidatos) else ()
        letra = next((a for a in alternativas if a.isalpha()), None)
        if letra is None:
            return None
        saida.append(letra)
    return "".join(saida) if achou else None


def sem_troca_de_caixa(
    palavra: str, candidatos: Sequence[Sequence[str]]
) -> list[list[str]]:
    """Os mesmos candidatos, sem a alternativa que é a **mesma letra** com outra caixa ou outro
    acento (S-508).

    **Quem decide maiúscula é a altura do box, e ela já decidiu.** `caixa_alta.decidir` roda antes
    deste módulo, com uma régua medida (CER 0,1434 -> 0,1114); o dicionário decide *qual letra*, e
    desfazer a decisão de caixa numa posição que ninguém perguntou não é resposta dele.

    **O que isso destrava é a maioria das correções.** `conhecida` dobra para minúscula antes de
    olhar o léxico, então `reSult` e `result` são as duas "conhecidas" -- e a guarda da ambiguidade
    recusava as duas. Medido em 4 folhas do `Nunn`: 13 dos 22 tokens com dígito eram recusados
    assim, todos por uma maiúscula no meio da palavra que palavra nenhuma tem.

    **O acento entrou junto, e ele custou a única palavra certa quebrada da medição.** Ao destravar
    a caixa, `façanha` virou `facanha` na folha 47 do `Xadrez Vitorioso`: a cedilha não está no
    léxico e `facanha` está. Só que a cedilha é **tinta na imagem** -- ao contrário do tamanho, que
    o resize para 32x32 apaga --, então tirá-la é desfazer o que o classificador viu para
    acomodar uma falta do dicionário. Com esta linha, `quebraram_palavra_certa` volta a zero.
    """
    return [
        [a for a in alternativas if _outra_letra(a, palavra[i])]
        if i < len(palavra)
        else list(alternativas)
        for i, alternativas in enumerate(candidatos)
    ]


def _outra_letra(alternativa: str, atual: str) -> bool:
    """São letras diferentes, e não a mesma com outra caixa ou outro acento?"""
    return _cru(alternativa) != _cru(atual)


def _cru(char: str) -> str:
    """O caractere sem acento e em minúscula. `Ç`, `ç` e `c` viram o mesmo."""
    sem_marca = "".join(
        c for c in unicodedata.normalize("NFD", char) if not unicodedata.combining(c)
    )
    return sem_marca.casefold()


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
    if not lexico or conhecida(palavra, lexico) or not candidata(palavra, candidatos):
        return None
    conhecidas = {
        v
        for v in variantes(palavra, sem_troca_de_caixa(palavra, candidatos), max_trocas=max_trocas)
        if conhecida(v, lexico)
    }
    if not conhecidas:
        return None
    # **Pontuação de borda não é ambiguidade (S-349).** `conhecida` apara `.,;:!?()[]'"` antes de
    # olhar o léxico, então `black.` e `black,` são a **mesma** resposta do dicionário -- e duas
    # respostas iguais chegavam aqui como duas variantes distintas, disparando a guarda da
    # ambiguidade. `blaek.` com o ponto entre os candidatos da última caixa era recusado por
    # "duas conhecidas", quando a correção era uma só: `black`.
    #
    # A caixa é comparada **sem** `casefold`: `Black` e `black` são duas respostas de verdade, e
    # decidir entre elas é o palpite que este módulo não dá.
    nucleos = {v.strip(PONTUACAO_DE_BORDA) for v in conhecidas}
    if len(nucleos) != 1:
        return None
    return _com_a_pontuacao_de(palavra, nucleos.pop())


def _com_a_pontuacao_de(original: str, nucleo: str) -> str:
    """O núcleo corrigido, com a pontuação de borda que o original tinha (S-349).

    A pontuação vem do original e não da variante escolhida porque é o **original** que a leitura
    viu: trocar `black.` por `black,` porque a vírgula estava entre os candidatos da caixa seria
    corrigir o que ninguém pediu -- o dicionário decide letra, e não sinal.
    """
    dianteira = original[: len(original) - len(original.lstrip(PONTUACAO_DE_BORDA))]
    traseira = original[len(original.rstrip(PONTUACAO_DE_BORDA)) :]
    return f"{dianteira}{nucleo}{traseira}"


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

