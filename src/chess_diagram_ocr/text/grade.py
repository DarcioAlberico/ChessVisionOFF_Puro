"""A grade de exercícios, e a direção que só o número impresso diz (S-216).

`pagina.sequencia_de_leitura` lê **coluna a coluna**: a coluna da esquerda inteira, depois a da
direita. É a ordem certa para prosa em duas colunas, e é a única ordem que a S-193 conhece.

Uma página de exercícios não é prosa. Ela é uma **grade**: células com um diagrama e uma legenda
curta, separadas por vãos largos que atravessam a página. E ali a ordem depende de como o livro
numerou a grade -- que é decisão do editor, e não da geometria.

## A grade se separa da prosa pela geometria; a direção, não

O vão que separa duas fileiras de exercícios é a altura de um tabuleiro, e ele atravessa **todas**
as colunas ao mesmo tempo. Prosa não tem esse vão: onde a coluna da esquerda tem buraco, a da
direita tem texto. É o que `FRACAO_DE_VAO` mede, e ali a separação é limpa.

A **direção**, não. Duas grades geometricamente indistinguíveis, numeradas ao contrário uma da
outra:

    Schiller, Big Book of Combinations    89  92     coluna a coluna
                                          90  93
                                          91  94

    Karpov, Chess Combinations 1         311 312     linha a linha
                                         313 314
                                         315 316

Mesmo número de colunas, mesmo número de fileiras, mesma densidade, e as legendas das duas colunas
pareadas no mesmo `y` nas duas. **Nenhuma régua sobre caixas separa as duas** -- o que as separa é
o número impresso, e é por isso que ele é o sinal.

## E ele é uma constante do livro, não da página

Medido em 2026-08-23 por `cvoff-texto-grade`, lendo a numeração impressa em todas as páginas de
grade do acervo:

    Karpov 1     linha a linha     66 de 66 páginas decidíveis
    Burgess      linha a linha     18 de 18
    Schiller     coluna a coluna   77 de 77
    Secrets      coluna a coluna    3 de 3

**Nenhum livro se contradiz uma única vez em 164 páginas.** É o que torna a calibração por livro
barata e confiável, e é por isso que o `arranjo` **chega de fora** desta camada: ele é calibrado
uma vez por livro, e nunca adivinhado por página.

## Por que o `tau` da S-194 não pode decidir isto

A referência da S-194 é a ordem em que o PDF emite os spans, e a spec dela a descreve como vinda
da diagramação. Isso vale para parte do acervo -- o `Polgar` sai de LaTeX, o `Dvoretsky` e o
`1001` saem de conversão de ebook -- e **não vale justamente nos livros de grade**: `Karpov`,
`Schiller`, `Burgess` e `Secrets`, os quatro que o acervo permite calibrar, são digitalização com
camada do `Adobe Acrobat Paper Capture` por cima. Nas páginas em que a pergunta se faz, a
"ordem do typesetter" é o palpite de um motor de OCR.

E é um palpite que erra **nos dois sentidos**, conferido contra a numeração impressa:

    Karpov 1     49 páginas de acordo com o número impresso, 17 contra
    Schiller     77 de acordo,  0 contra
    Burgess      14 de acordo,  4 contra
    Secrets       0 de acordo,  3 contra   <- e aqui ela erra o livro inteiro

24 de 164, uma em cada sete. Perseguir queda de `tau` aqui seria perseguir o palpite do Acrobat, e
nas 24 páginas em que ele erra o `tau` **premiaria** a ordem errada. Por isso a régua desta
entrega é a numeração impressa (`cvoff-texto-grade`), e o `tau` entra como acompanhamento.

O `Secrets` é o caso mais limpo: as três páginas decidíveis dele trazem `IV/2 IV/3 IV/4` descendo a
coluna da esquerda e `IV/5 IV/6 IV/7` descendo a da direita -- coluna a coluna, sem ambiguidade --,
e a camada emitiu as três atravessando. Ali `tau` sob a leitura errada é 0,014 e sob a certa é
0,262: **o número que a régua da S-194 prefere é o errado, por 18x.**
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from .boxes import Caixa
from .colunas import atribuir_coluna
from .linhas import bandas

Arranjo = Literal["prosa", "grade"]
"""Como a página se lê. `"prosa"` é coluna a coluna (S-193); `"grade"` é fileira a fileira.

**`"prosa"` é o padrão em toda a API, e é o lado seguro do erro.** Tratar prosa como grade
embaralha as quarenta linhas de uma página; tratar grade como prosa desordena os cinco elementos
de uma folha de exercícios. Na dúvida, prosa.
"""

VAO_DE_FILEIRA = 4.0
"""Vão vertical livre, em alturas medianas de caixa, a partir do qual a página parte em fileiras.

O vão entre duas fileiras de exercícios é a altura de um tabuleiro; o vão entre duas linhas de
texto é o entrelinha. Não há nada entre os dois. Medido nas 10 bandas da página 62 do `Karpov 1`,
com altura mediana de caixa de 11 px:

    entre linhas da mesma célula    3, 7, 13, 15, 16, 16 px   (0,3 - 1,5 alturas)
    entre fileiras da grade       131, 133, 134 px            (12 alturas)

O limiar cai no vão: 2,7x acima do maior entrelinha e 3x abaixo do menor vão de fileira.

**Vale para caixa de caractere e para caixa de linha.** A medição acima é sobre caixas de linha,
que é o que a camada de texto entrega; a segmentação da S-185 entrega caixas de caractere, e ali
a altura mediana é a altura de x -- menor, o que aperta o limiar em pixels mas o deixa na mesma
posição relativa entre dois montes separados por 30x. `tests/test_text_grade.py` trava os dois."""

FRACAO_DE_VAO = 0.30
"""Fração da altura de texto que precisa ser vão de fileira para a página ser uma grade.

**Não basta existir um vão largo: uma página de prosa com uma figura no meio também tem um.** O
que distingue a grade é que quase toda a altura dela é vão. Medido em 2026-08-23 nas 276 páginas
de 2+ colunas do acervo, com as duas populações rotuladas por densidade de banda:

    prosa e lista densas (>= 20 bandas, n=103)     0,000 - 0,153, e uma de 0,281
    grade de exercícios (n=62, com vão nenhum)     0,634 - 0,826

A 0,30 nenhuma das 103 densas é classificada como grade e nenhuma das 62 grades é perdida. O
limiar fica 2,0x acima da maior prosa densa e 2,1x abaixo da menor grade.

A página de 0,281 é a 53 do `Neumann` (1870, digitalização do Google Books): não é prosa -- são
diagramas com a camada de OCR em pedaços --, e mesmo assim ela fica **abaixo** do limiar, que é o
lado certo para uma página cujo texto não se pode ler."""


def _altura_mediana(caixas: Sequence[Caixa]) -> float:
    alturas = sorted(c.altura for c in caixas)
    return float(alturas[len(alturas) // 2]) if alturas else 1.0


def vaos_entre_bandas(caixas: Sequence[Caixa]) -> list[tuple[int, int]]:
    """Os intervalos `(fundo, topo)` de `y` livres entre bandas consecutivas, de cima para baixo.

    **O fundo é acumulado, e não o da banda anterior.** Uma legenda alta numa das colunas pode
    terminar abaixo do topo da banda seguinte; sem acumular, o vão seguinte sairia maior do que o
    espaço realmente livre e a página partiria dentro de uma fileira.
    """
    grupos = bandas(caixas)
    if len(grupos) < 2:
        return []
    saida: list[tuple[int, int]] = []
    fundo = max(c.y2 for c in grupos[0])
    for grupo in grupos[1:]:
        topo = min(c.y1 for c in grupo)
        if topo > fundo:
            saida.append((fundo, topo))
        fundo = max(fundo, max(c.y2 for c in grupo))
    return saida


def _vao_minimo(caixas: Sequence[Caixa], vao_minimo: float | None) -> float:
    return VAO_DE_FILEIRA * _altura_mediana(caixas) if vao_minimo is None else vao_minimo


def fracao_de_vao(caixas: Sequence[Caixa], *, vao_minimo: float | None = None) -> float:
    """Quanto da altura de texto da página é vão de fileira. Ver `FRACAO_DE_VAO`."""
    if len(caixas) < 2:
        return 0.0
    altura_texto = max(c.y2 for c in caixas) - min(c.y1 for c in caixas)
    if altura_texto <= 0:
        return 0.0
    limiar = _vao_minimo(caixas, vao_minimo)
    largos = sum(topo - fundo for fundo, topo in vaos_entre_bandas(caixas) if topo - fundo >= limiar)
    return largos / altura_texto


def cortes_de_fileira(caixas: Sequence[Caixa], *, vao_minimo: float | None = None) -> list[int]:
    """Os `y` em que a página parte em fileiras, de cima para baixo. Vazio quando não há fileira.

    O corte fica no **meio** do vão, e não numa das bordas: o símbolo de avaliação impresso na
    base do tabuleiro começa dentro do vão, e ele pertence à fileira do tabuleiro que o produziu,
    não à de baixo.
    """
    if len(caixas) < 2:
        return []
    limiar = _vao_minimo(caixas, vao_minimo)
    return [(fundo + topo) // 2 for fundo, topo in vaos_entre_bandas(caixas) if topo - fundo >= limiar]


def parece_grade(caixas: Sequence[Caixa], *, colunas: Sequence[tuple[int, int]] | None = None) -> bool:
    """A página é uma grade de exercícios, e não prosa? Ver o cabeçalho.

    **Isto não diz em que direção ela se lê.** É a metade do problema que a geometria resolve; a
    direção vem da numeração impressa, medida por livro em `cvoff-texto-grade`. Quem chama isto
    para decidir ordem sozinho está adivinhando, e a S-216 diz por que não dá.

    `colunas` entra só para recusar a página de coluna única: com uma coluna, fileira e linha são
    a mesma coisa e a pergunta não tem conteúdo.
    """
    if colunas is not None and len(colunas) < 2:
        return False
    return fracao_de_vao(caixas) >= FRACAO_DE_VAO


CORRIDA_MINIMA = 4
"""Quantos números consecutivos identificam uma grade numerada.

Três não bastam: numa grade de 2x3 os três da primeira coluna crescem para baixo **e** os três da
primeira fileira crescem para o lado, e as duas leituras dão a mesma resposta em metade dos
arranjos. Com quatro é preciso dobrar a esquina, que é justamente o que se quer perguntar."""


def corrida_de_exercicio(numerados: Sequence[tuple[int, Caixa]]) -> list[tuple[int, Caixa]]:
    """A maior sequência de inteiros **consecutivos**, ordenada. Vazia se for curta demais.

    Consecutivos, e não "todos os números da página": ano de partida, número de página e lance
    também são inteiros, e o que identifica exercício é a numeração seguir sem buraco.
    """
    unicos: dict[int, Caixa] = {}
    for numero, caixa in numerados:
        unicos.setdefault(numero, caixa)

    melhor: list[int] = []
    atual: list[int] = []
    for numero in sorted(unicos):
        atual = [*atual, numero] if atual and numero == atual[-1] + 1 else [numero]
        if len(atual) > len(melhor):
            melhor = atual
    return [(n, unicos[n]) for n in melhor] if len(melhor) >= CORRIDA_MINIMA else []


def chaves_de_grade(
    corrida: Sequence[tuple[int, Caixa]],
    *,
    colunas: Sequence[tuple[int, int]],
) -> dict[int, tuple[int, int]]:
    """`(fileira, coluna)` de cada número da corrida, para ordenar por um ou por outro.

    As fileiras saem das **caixas da corrida**, e não da página inteira: os números de exercício
    de uma mesma fileira estão na mesma altura, então agrupá-los por banda dá as fileiras
    diretamente, sem depender de o vão da página ter sido achado.
    """
    fileira_de = {id(caixa): i for i, grupo in enumerate(bandas([c for _, c in corrida])) for caixa in grupo}
    return {n: (fileira_de[id(c)], atribuir_coluna(c, colunas)) for n, c in corrida}


def direcao_pela_numeracao(
    numerados: Sequence[tuple[int, Caixa]],
    *,
    colunas: Sequence[tuple[int, int]],
) -> Arranjo | None:
    """Em que direção a grade está numerada, ou `None` quando a página não responde.

    **É o único sinal que separa as duas grades**, e a razão está no cabeçalho: a geometria delas
    é a mesma. `None` sai quando não há corrida de exercício, quando há menos de duas colunas, ou
    quando as duas leituras produzem a mesma ordem -- e aí não há nada a decidir nesta página.

    Os números entram como `(valor, caixa)`. Hoje quem os fornece é a camada de texto, em
    `cvoff-texto-grade`; quando a S-188 ler a linha da imagem, ela fornece os mesmos pares e nada
    aqui muda. É por isso que esta função não sabe de PDF.
    """
    if len(colunas) < 2:
        return None
    corrida = corrida_de_exercicio(numerados)
    if not corrida:
        return None

    chaves = chaves_de_grade(corrida, colunas=colunas)
    esperado = [n for n, _ in corrida]
    return direcao_de(esperado, chaves)


def direcao_de(sequencia: Sequence[int], chaves: dict[int, tuple[int, int]]) -> Arranjo | None:
    """A direção que explica esta sequência, ou `None` quando as duas a explicam (ou nenhuma).

    Separada de `direcao_pela_numeracao` porque a mesma pergunta se faz de **duas** sequências: a
    dos números impressos, que é a verdade, e a da ordem em que a camada de texto os emitiu, que é
    o que `cvoff-texto-grade` compara contra ela.
    """
    por_fileira = sorted(sequencia, key=lambda n: chaves[n])
    por_coluna = sorted(sequencia, key=lambda n: chaves[n][::-1])
    if por_fileira == por_coluna:
        return None
    if por_fileira == list(sequencia):
        return "grade"
    if por_coluna == list(sequencia):
        return "prosa"
    return None


__all__ = [
    "CORRIDA_MINIMA",
    "FRACAO_DE_VAO",
    "VAO_DE_FILEIRA",
    "Arranjo",
    "chaves_de_grade",
    "corrida_de_exercicio",
    "cortes_de_fileira",
    "direcao_de",
    "direcao_pela_numeracao",
    "fracao_de_vao",
    "parece_grade",
    "vaos_entre_bandas",
]
