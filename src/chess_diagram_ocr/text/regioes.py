"""Até onde a coluna vale, medido na imagem (S-507).

A S-190 responde *"onde a coluna acaba"* no eixo `x`. Falta a outra metade: **a coluna não vale a
folha inteira**. A página de prosa em duas colunas quase sempre traz também um bloco de largura
inteira -- o cabeçalho corrente, o parágrafo de abertura de seção, a nota de rodapé --, e esse
bloco cobre a calha em todas as linhas dele.

## O sintoma, e por que a tolerância não o alcança

`colunas.LINHAS_NA_CALHA` tolera **uma** linha na calha, e esse número está medido: duas começam a
partir o Yusupov. Um parágrafo de largura inteira tem quatro. Medido na folha 10 do
`Nunn - Secrets of Minor Piece Endings`, 45 bandas a 220 dpi:

    x da calha de verdade      557 a 597
    bandas que a cobrem        3   (as três primeiras linhas do parágrafo de abertura)
    bandas nas colunas         17 a 38

A calha é um mínimo fundo -- 3 contra 17 -- e mesmo assim some, porque 3 > 1. A página inteira sai
como **uma** coluna, e o resultado é o defeito que a S-190 existe para não ter: as duas colunas
intercaladas linha a linha.

    (1): This is a position of reciprocal zugzwang. [...] 2 lLig3 Knights are notoriously bad
    at fight- c8 3 lL!f5 c:Ji;c7 4 lL!e7 (or 4 lL!d6). ing against rook's pawns, so one
                     ^ coluna da direita          ^ coluna da esquerda

Subir a tolerância para quatro consertaria esta folha e quebraria as que a S-190 mediu. O que está
errado não é o número: é a **premissa** de que a calha atravessa a folha.

## A régua: a calha não precisa atravessar a folha, precisa atravessar a região

A folha é uma pilha de regiões horizontais, e a coluna é propriedade da região. Achar a região é
achar a **maior corrida de bandas consecutivas** em que existe calha; o que sobra acima e abaixo
dela é outra região, e a busca se repete ali.

**A folha inteira é tentada primeiro, e é isso que preserva o que já estava medido.** Onde a S-190
acha calha hoje, a resposta é uma região só com a calha dela -- nada muda nas 456 páginas de prosa
que fixaram `CALHA_EM_CARACTERES`, `LINHAS_NA_CALHA` e `LINHAS_PARA_TOLERAR`. A busca por região
só roda onde a régua de hoje devolve "uma coluna", que é onde ela já estava errada ou já estava
certa por não haver nada a achar.

**Medido contra a régua da S-194** -- a ordem em que o próprio PDF emite as linhas --, em 420
folhas de 46 livros do acervo, 12 por livro, e comparado folha a folha com a produção de hoje:

    73 folhas a régua parte em região        23 melhoram, 0 pioram, 5 empatam
    155 folhas que as duas réguas aceitam     0 melhoram, 0 pioram   <- nada do que já ia bem mudou
    folhas em ordem exata                   109 -> 127
    tau médio                            0,0183 -> 0,0175

## A coluna da região tem de parecer uma coluna

**A busca por região olha toda janela de bandas da folha, e não só a folha: as chances de um vão
coincidir sobem na mesma proporção.** Achado ao medir, na folha 74 do
`Melhores Finais de Capablanca`: é prosa de coluna única com uma lista de lances no meio, e a
margem direita das linhas curtas de prosa alinha com o começo da coluna dos lances das pretas. Há
calha ali por doze bandas seguidas, e a "região de duas colunas" que sai daí põe **todos** os
lances das brancas antes de **todos** os das pretas.

O que separa a coluna de verdade do alinhamento por acaso é quanto da coluna a linha ocupa --
`PREENCHIMENTO_DA_COLUNA`. Medido nas mesmas 420 folhas, na pior coluna de cada região candidata:

    regiões em folhas cuja ordem PIORA     0,087 a 0,664   (11 folhas)
    regiões em folhas que não pioram       0,265 a 0,979   (16 folhas)
    prosa de duas colunas do Nunn e do Aagaard      0,84 a 0,99

**A barra é mais alta aqui do que na régua de folha, e isso é deliberado.** As colunas que a S-190
acha na folha inteira têm preenchimento mediano 0,83 e chegam a 0,09 -- e continuam valendo, porque
ali a evidência é outra: **todas** as bandas da folha concordam com a calha. A região é uma janela
escolhida entre muitas, e o que ela pede a mais é a compensação disso. É o mesmo raciocínio de
`LINHAS_PARA_TOLERAR`, um nível acima.

Uma segunda régua foi medida e **recusada**: a fração de bandas com tinta em todas as colunas. Ela
não separa nada -- as folhas que pioram vão de 0,07 a 1,00, e a de 1,00 é a lista de lances.

## A banda que cruza a calha é uma região de uma coluna, e não uma linha partida

Achar a região não basta. A corrida vencedora pode conter a linha tolerada por
`LINHAS_NA_CALHA` -- e no caminho do glifo, que atribui **caractere** a coluna, essa linha sairia
cortada em duas metades, uma em cada coluna:

    up the material in all four of the minor  ->  "up the material in all"  +  "four of the minor"

Por isso a corrida é quebrada nas bandas que cruzam a calha: cada uma vira região de uma coluna, e
o que sobra de cada lado continua colunar. É a mesma ideia do elemento transversal da S-193 -- o
que atravessa não pertence a coluna nenhuma, e serve de separador --, aplicada uma camada antes,
onde a linha ainda não foi costurada.

## O piso da calha é da página, e não da região

`colunas.piso_de_calha` sai da largura mediana de caractere. Medi-la nas quatro caixas de um
cabeçalho daria um piso que não descreve o livro. Ele é calculado uma vez, sobre todas as caixas,
e desce para cada região -- que é o mesmo motivo pelo qual `leitor.calha_de_linhas` existe.

## A região colunar não é aceita com menos de doze bandas

`LINHAS_PARA_TOLERAR` já registra por quê: num recorte de cinco linhas, o vão entre duas palavras
que calham de se alinhar vira coluna. A busca por região multiplica as chances disso -- ela olha
**toda** janela de bandas da folha, e não só a folha --, então o piso de bandas é o mesmo 12 e a
faixa achada ainda tem de sobreviver à `COLUNA_MINIMA`. Uma corrida cuja calha se funde de volta
numa coluna só é descartada: partir a folha para não achar coluna nenhuma é custo sem ganho.

## A banda isolada da borda não vota na calha (S-523)

A folha inteira tolera **uma** banda na calha, e a página de soluções do `Yusupov - Build Up Your
Chess` tem **duas**: o título centralizado («Solutions») e o número de página, que cai no meio da
calha. A folha é recusada, a busca por região acha o corpo -- e o reprova no preenchimento, porque
coluna de solução é feita de linha curta («1.♗h3!», «(1 point)» encostado à direita). Medido em
2026-10-06 (`docs/PLANO_COLUNAS_SOLUCOES.md`): das 84 páginas de soluções medidas, **15** saíam em
duas colunas; as outras saíam com as colunas intercaladas, ou picadas em tiras estreitas, que o
preenchimento aprova por se encherem com pouco.

A régua: quando a folha inteira não tem calha, até `BORDA_MAX` bandas em cada borda que estejam
**isoladas** -- separadas da vizinha por um vão de `VAO_DE_BORDA` passos medianos entre bandas --
saem da projeção, e o corpo que sobra é tentado com a **mesma** régua da folha inteira, sem
preenchimento. As bandas de borda viram regiões de uma coluna. Onde a folha inteira acha calha, nada
muda: é o mesmo princípio que preservou a S-190 na S-507.

    Yusupov, páginas de soluções em duas colunas     15 de 84  ->  79 de 81   (vão 1,5)
                                                                  77 de 81   (vão 2,0)
    régua da S-194, 1.090 folhas de 36 livros         0 pioram; 15 mudam de estrutura (vão 1,5)

Das 15 que mudam, as olhadas são duas colunas de verdade que a folha não achava (Neumann p. 40 e
61, Gunderam p. 26) e uma grade de diagramas (Журавлев p. 88), assunto da S-216. **A regressão
conhecida** é a legenda de estrelas do `Aagaard - A Matter of Endgame Technique` (p. 546): as
estrelas numa coluna e a descrição noutra -- o que a régua de folha já fazia em qualquer página
assim sem título; esta régua só estende a dela ao corpo. O que a borda **não** resolve é o quadro de
largura inteira com muitas bandas: o «Scoring» de fim de capítulo, que é a S-525.

## O quadro já achado corta a folha em trechos (S-525)

O quadro de largura inteira -- o «Scoring», cinco bandas emolduradas cruzando a calha -- chega aqui
já achado por `text/quadros.py` (a moldura oca no glifo, a imagem com linhas centradas na camada),
como intervalo de `y`. A banda cujo topo cai nele é região de uma coluna, e cada trecho da folha
entre quadros passa pela régua de sempre por conta própria: folha (o trecho) inteira, depois a
borda da S-523, depois a busca por região. **O trecho curto que o corte deixa é de uma coluna**:
abaixo do «Scoring» sobram duas linhas em itálico e o fólio, e com três bandas o espaço entre
palavras que calha de se alinhar vira calha -- é o piso de `BANDAS_NA_REGIAO` pelo mesmo motivo.
Medido no conjunto anotado da S-524: pelo glifo, o motor da aba, as páginas com «Scoring» vão de
2 de 8 a **8 de 8** (41 de 42 no conjunto); pela camada, 5 de 8 -- nas outras três a própria camada
junta as duas colunas numa linha, ou está quebrada. A régua da S-194 não piora folha nenhuma.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .boxes import Caixa
from .colunas import (
    LINHAS_NA_CALHA,
    LINHAS_PARA_TOLERAR,
    faixas_entre,
    piso_de_calha,
    vaos,
)
from .linhas import bandas

PREENCHIMENTO_DA_COLUNA = 0.70
"""Quanto de sua largura uma coluna de região precisa ocupar, na banda mediana. Ver o cabeçalho.

**É o menos confiante dos três números deste módulo, e o cabeçalho diz por quê**: entre o maior
falso medido (0,664) e o menor verdadeiro (0,704) há 1,06x, contra os 6,7x que separam a calha do
vão que não é calha na S-190. O que segura a decisão não é a folga, é o resultado: varrido contra
a régua da ordem de leitura, **qualquer valor de 0,70 a 0,85 dá o mesmo** -- 23 folhas melhoram,
nenhuma piora --, e abaixo de 0,70 as regressões voltam."""

BANDAS_NA_REGIAO = LINHAS_PARA_TOLERAR
"""Quantas bandas uma região precisa ter para poder ser colunar. Ver o cabeçalho.

É o mesmo número de `colunas.LINHAS_PARA_TOLERAR`, e de propósito: os dois respondem à mesma
pergunta -- *a partir de quantas linhas um vão alinhado deixa de ser coincidência* --, e deixá-los
divergir seria duas respostas para ela.

**Uma das doze pode ser a linha tolerada**, então o piso efetivo de bandas *colunares* é onze. Não
é frouxidão: a janela de doze é a população sobre a qual a tolerância da S-190 foi medida, e
descontá-la aqui mediria a calha com uma régua e a região com outra."""

BORDA_MAX = 2
"""Quantas bandas, no máximo, cada borda da folha pode ceder ao corpo (S-523). Ver o cabeçalho.

Duas: o título e, quando há, um subtítulo ou o cabeçalho corrente. Um **bloco** na borda -- o
quadro «Scoring», uma lista de lances separada do texto por espaço -- não é título, e tratá-lo como
tal parte a lista de lances do `Melhores Finais de Capablanca` (p. 172) em duas colunas: medido e
recusado no plano."""

VAO_DE_BORDA = 1.5
"""O vão que isola uma banda de borda, em passos medianos entre as bandas da folha (S-523).

Varrido em 1,5, 2,0 e 2,5 contra a régua da S-194: nenhum piora folha com referência confiável. O
1,5 é o que alcança as três páginas de duas colunas olhadas que o 2,0 não alcança (Neumann p. 40 e
61, Gunderam p. 26), e leva as soluções do Yusupov a 79 de 81."""


@dataclass(frozen=True)
class Regiao:
    """Uma faixa horizontal da folha, com as colunas que valem **dentro dela**.

    `topo` e `base` são cortes em `y`, em pixels da imagem, e as regiões de uma folha os
    ladrilham sem buraco nem sobreposição: uma caixa pertence à região cujo intervalo contém o
    **topo** dela. É a mesma convenção da fileira da S-216 -- um diagrama é mais alto que o corte
    seguinte e pertence à região em que começa.
    """

    topo: int
    base: int
    colunas: tuple[tuple[int, int], ...]

    @property
    def transversal(self) -> bool:
        """A região se lê de margem a margem? É o cabeçalho, o título, o parágrafo de largura
        inteira -- tudo que não pertence a coluna nenhuma."""
        return len(self.colunas) < 2


def detectar_regioes(
    caixas: Sequence[Caixa],
    *,
    calha_minima: int | None = None,
    quadros: Sequence[tuple[int, int]] = (),
) -> list[Regiao]:
    """As regiões horizontais da folha, de cima para baixo. Uma só quando a folha é homogênea.

    `calha_minima=None` deriva o piso de `colunas.piso_de_calha`, que é o certo quando as caixas
    são **caracteres**. Quem só tem caixas de linha passa o piso de `leitor.calha_de_linhas` --
    ver a docstring de lá, que traz o número.

    `quadros` são intervalos de `y` (na unidade das caixas) de quadros de largura inteira já
    achados -- `text/quadros.py` (S-525). A banda cujo topo cai num quadro é região de uma
    coluna, e cada trecho da folha entre quadros passa pela régua de sempre por conta própria.
    """
    if not caixas:
        return []

    grupos = bandas(caixas)
    x_min = min(c.x1 for c in caixas)
    x_max = max(c.x2 for c in caixas)
    y_min = min(c.y1 for c in caixas)
    y_max = max(c.y2 for c in caixas)
    largura = x_max - x_min
    if largura <= 1:
        return [Regiao(y_min, y_max, ((x_min, x_max),))]

    if calha_minima is None:
        calha_minima = piso_de_calha(caixas)

    mascaras = [_mascara(grupo, x_min, largura) for grupo in grupos]
    cortadas: list[tuple[int, int, tuple[tuple[int, int], ...]]] = []
    topos = [min(c.y1 for c in grupo) for grupo in grupos]
    no_quadro = [any(y1 <= topo <= y2 for y1, y2 in quadros) for topo in topos]
    cortada = any(no_quadro)
    k = 0
    while k < len(grupos):
        m = k + 1
        while m < len(grupos) and no_quadro[m] == no_quadro[k]:
            m += 1
        # **O trecho curto que um quadro deixa é de uma coluna.** Abaixo do «Scoring» sobram
        # duas linhas em itálico e o fólio: com três bandas, o espaço entre palavras que calha
        # de se alinhar vira calha, e o rodapé saía em quatro "colunas". É o mesmo piso de
        # `BANDAS_NA_REGIAO`, pelo mesmo motivo; a folha sem quadro nenhum não passa por aqui.
        if no_quadro[k] or (cortada and m - k < BANDAS_NA_REGIAO):
            cortadas.append((k, m, ((x_min, x_max),)))
        else:
            _trecho(mascaras, grupos, k, m, x_min, x_max, calha_minima, cortadas)
        k = m
    return _com_cortes_em_y(_fundir_iguais(cortadas), grupos, y_min, y_max)


def _trecho(
    mascaras: list[np.ndarray],
    grupos: Sequence[Sequence[Caixa]],
    a: int,
    b: int,
    x_min: int,
    x_max: int,
    calha_minima: int,
    saida: list[tuple[int, int, tuple[tuple[int, int], ...]]],
) -> None:
    """As regiões das bandas `[a, b)`, pela régua de sempre: a folha (aqui, o trecho) inteira
    primeiro; sem calha nela, o corpo sem as bordas isoladas (S-523); sem calha nele, a busca
    por região (S-507)."""
    corpo = _corpo_sem_as_bordas(mascaras[a:b], grupos[a:b], x_min, x_max, calha_minima)
    if corpo is None:
        _cortar(mascaras, a, b, x_min, x_max, calha_minima, saida)
        return
    i, j, cortes, faixas = corpo
    if i:
        saida.append((a, a + i, ((x_min, x_max),)))
    _quebrar_nas_transversais(mascaras, a + i, a + j, x_min, x_max, cortes, faixas, calha_minima, saida)
    if a + j < b:
        saida.append((a + j, b, ((x_min, x_max),)))


def _bandas_isoladas_nas_bordas(grupos: Sequence[Sequence[Caixa]]) -> tuple[int, int]:
    """`[a, b)`: as bandas do corpo, sem as isoladas do topo e da base. Ver "A banda isolada".

    O passo é a mediana da distância entre topos de bandas vizinhas -- o entrelinha do corpo --, e
    uma banda de borda é isolada quando o vão até a vizinha é `VAO_DE_BORDA` vezes isso. Cada
    borda cede no máximo `BORDA_MAX` bandas, uma de cada vez: a segunda só sai se também estiver
    isolada da que vem depois dela.
    """
    n = len(grupos)
    if n < 2 * BORDA_MAX:
        return 0, n
    topos = [min(caixa.y1 for caixa in grupo) for grupo in grupos]
    passo = float(np.median(np.diff(topos)))
    if passo <= 0:
        return 0, n
    vao = VAO_DE_BORDA * passo
    a = 0
    while a < BORDA_MAX and a + 1 < n and topos[a + 1] - topos[a] >= vao:
        a += 1
    b = n
    while n - b < BORDA_MAX and b - 1 > a and topos[b - 1] - topos[b - 2] >= vao:
        b -= 1
    return a, b


def _corpo_sem_as_bordas(
    mascaras: Sequence[np.ndarray], grupos: Sequence[Sequence[Caixa]], x_min: int, x_max: int,
    calha_minima: int,
) -> tuple[int, int, list[tuple[int, int]], tuple[tuple[int, int], ...]] | None:
    """`(a, b, calhas, colunas)` do corpo sem as bordas, ou `None` para seguir o caminho de sempre.

    Os índices são relativos a `grupos` -- que pode ser um trecho da folha (S-525). `None` em três
    casos, e os três são "nada a fazer aqui": o trecho inteiro já tem calha (e aí a régua da S-190
    responde, como sempre); nenhuma banda de borda está isolada; o corpo sem elas também não tem
    calha -- e então é a busca por região da S-507 que decide.
    """
    n = len(grupos)
    _, faixas = _calhas(np.sum(mascaras, axis=0), x_min, x_max, calha_minima, n)
    if faixas:
        return None
    a, b = _bandas_isoladas_nas_bordas(grupos)
    if (a, b) == (0, n):
        return None
    cortes, faixas = _calhas(np.sum(mascaras[a:b], axis=0), x_min, x_max, calha_minima, b - a)
    if not faixas:
        return None
    return a, b, cortes, faixas


def atribuir_regiao(caixa: Caixa, regioes: Sequence[Regiao]) -> int:
    """Em qual região esta caixa está, **pelo topo dela**. `0` quando não há região nenhuma."""
    for i, regiao in enumerate(regioes):
        if caixa.y1 <= regiao.base:
            return i
    return max(0, len(regioes) - 1)


def colunas_da_folha(regioes: Sequence[Regiao]) -> list[tuple[int, int]]:
    """As colunas da região mais dividida. É o que responde *"esta folha é de duas colunas?"*.

    Existe para quem só sabe perguntar por folha -- a régua da ordem de leitura da S-194, que
    conta quantas vezes a leitura sobe --, e não para quem monta a página: ali a pergunta certa é
    por região.
    """
    if not regioes:
        return []
    return list(max(regioes, key=lambda r: len(r.colunas)).colunas)


def _mascara(grupo: Sequence[Caixa], x_min: int, largura: int) -> np.ndarray:
    """Que `x` esta banda cobre. É uma linha da projeção de `colunas.linhas_por_x`."""
    desta = np.zeros(largura + 2, dtype=bool)
    for caixa in grupo:
        desta[max(0, caixa.x1 - x_min) : max(0, caixa.x2 - x_min) + 1] = True
    return desta


def _tolerado(bandas_na_faixa: int) -> int:
    return LINHAS_NA_CALHA if bandas_na_faixa >= LINHAS_PARA_TOLERAR else 0


def _calhas(
    conta: np.ndarray, x_min: int, x_max: int, calha_minima: int, quantas: int
) -> tuple[list[tuple[int, int]], tuple[tuple[int, int], ...]]:
    """`(calhas, colunas)` desta projeção. As colunas saem vazias quando não há duas."""
    cortes = vaos(conta <= _tolerado(quantas), x_min, calha_minima)
    if not cortes:
        return ([], ())
    faixas = tuple(faixas_entre(cortes, x_min, x_max))
    return (cortes, faixas if len(faixas) > 1 else ())


def _cortar(
    mascaras: list[np.ndarray],
    a: int,
    b: int,
    x_min: int,
    x_max: int,
    calha_minima: int,
    saida: list[tuple[int, int, tuple[tuple[int, int], ...]]],
) -> None:
    """Parte `[a, b)` em regiões, recursivamente. Ver "A régua" no cabeçalho."""
    if b <= a:
        return

    cortes, faixas = _calhas(np.sum(mascaras[a:b], axis=0), x_min, x_max, calha_minima, b - a)
    if faixas:
        _quebrar_nas_transversais(mascaras, a, b, x_min, x_max, cortes, faixas, calha_minima, saida)
        return

    achado = _maior_corrida(mascaras, a, b, x_min, x_max, calha_minima)
    if achado is None:
        saida.append((a, b, ((x_min, x_max),)))
        return

    i, j, cortes, faixas = achado
    _cortar(mascaras, a, i, x_min, x_max, calha_minima, saida)
    _quebrar_nas_transversais(mascaras, i, j, x_min, x_max, cortes, faixas, calha_minima, saida)
    _cortar(mascaras, j, b, x_min, x_max, calha_minima, saida)


def _quebrar_nas_transversais(
    mascaras: list[np.ndarray],
    i: int,
    j: int,
    x_min: int,
    x_max: int,
    cortes: Sequence[tuple[int, int]],
    faixas: tuple[tuple[int, int], ...],
    calha_minima: int,
    saida: list[tuple[int, int, tuple[tuple[int, int], ...]]],
) -> None:
    """A faixa colunar quebrada na banda que cruza a calha. Ver o cabeçalho.

    A banda tolerada por `LINHAS_NA_CALHA` está *dentro* da faixa por construção -- é o que a
    tolerância quer dizer --, e ela é uma linha de largura inteira: sai como região de uma coluna,
    para não ser partida na calha.
    """
    cruzam = [_cruza(mascaras[k], cortes, x_min, calha_minima) for k in range(i, j)]
    k = i
    while k < j:
        cruza = cruzam[k - i]
        m = k + 1
        while m < j and cruzam[m - i] == cruza:
            m += 1
        saida.append((k, m, ((x_min, x_max),) if cruza else faixas))
        k = m


def _cruza(
    mascara: np.ndarray, cortes: Sequence[tuple[int, int]], x_min: int, calha_minima: int
) -> bool:
    """Esta banda **fecha** alguma calha, em vez de só encostar nela?

    **Tinta dentro da calha não basta, e a diferença custou uma medição.** A régua ingênua -- tem
    tinta na calha, logo é transversal -- transformava em linha de largura inteira a banda de duas
    colunas em que uma vírgula do fim da linha da esquerda entra na calha. Medido na folha 15 do
    `Euwe, Kramer - Das Mittelspiel Band 7`: calha de 8 pt em 271..279, a linha da esquerda acaba
    em 275 e a da direita começa em 304 -- há 28 pt de branco ali, e as duas linhas são duas.

    A pergunta certa é sobre a banda, e não sobre o pedaço da calha: **sobrou, nesta banda, um vão
    que ainda serve de calha e que passa por onde a calha da região passa?** A linha de largura
    inteira não deixa nenhum -- os vãos dela são espaços entre palavras.
    """
    livres = _vaos_da_banda(mascara, calha_minima)
    return not any(
        inicio < c2 - x_min and fim > c1 - x_min for c1, c2 in cortes for inicio, fim in livres
    )


def _vaos_da_banda(mascara: np.ndarray, calha_minima: int) -> list[tuple[int, int]]:
    """Os trechos sem tinta desta banda que ainda são largos o bastante para ser calha.

    Ao contrário de `colunas.vaos`, o que encosta na borda conta: a linha curta da coluna da
    esquerda deixa branco dali até a margem, e é exatamente esse branco que prova que ela não
    atravessa.
    """
    bordas = np.diff(np.concatenate(([True], mascara, [True])).astype(np.int8))
    inicios = np.flatnonzero(bordas == -1)
    fins = np.flatnonzero(bordas == 1)
    largos = (fins - inicios) >= calha_minima
    return [(int(a), int(b)) for a, b in zip(inicios[largos], fins[largos], strict=True)]


def _maior_corrida(
    mascaras: list[np.ndarray], a: int, b: int, x_min: int, x_max: int, calha_minima: int
) -> tuple[int, int, list[tuple[int, int]], tuple[tuple[int, int], ...]] | None:
    """A maior corrida de bandas de `[a, b)` que tem calha, ou `None`.

    **A janela cresce, e a contagem só sobe.** Acima de `LINHAS_PARA_TOLERAR` a tolerância é
    constante, então uma janela sem calha nunca volta a ter uma ao ser esticada: parar na primeira
    falha é exato, e não uma heurística de custo.
    """
    n = b - a
    if n < BANDAS_NA_REGIAO:
        return None

    melhor: tuple[int, int, list[tuple[int, int]], tuple[tuple[int, int], ...]] | None = None
    for i in range(a, b - BANDAS_NA_REGIAO + 1):
        if melhor is not None and b - i <= melhor[1] - melhor[0]:
            break
        conta = np.sum(mascaras[i : i + BANDAS_NA_REGIAO], axis=0).astype(np.int32)
        cortes, faixas = _calhas(conta, x_min, x_max, calha_minima, BANDAS_NA_REGIAO)
        if not faixas:
            continue
        j = i + BANDAS_NA_REGIAO
        while j < b:
            adiante = conta + mascaras[j]
            proximos, proximas = _calhas(adiante, x_min, x_max, calha_minima, j + 1 - i)
            if not proximas:
                break
            conta, cortes, faixas, j = adiante, proximos, proximas, j + 1
        if not _colunas_cheias(mascaras, i, j, faixas, x_min):
            continue
        if melhor is None or (j - i) > (melhor[1] - melhor[0]):
            melhor = (i, j, cortes, faixas)
    return melhor


def _colunas_cheias(
    mascaras: list[np.ndarray], i: int, j: int, faixas: tuple[tuple[int, int], ...], x_min: int
) -> bool:
    """Toda coluna desta corrida se parece com uma coluna? Ver "A coluna da região" no cabeçalho.

    A medida é a **mediana**, sobre as bandas que têm tinta na coluna, da fração da largura dela
    que a banda ocupa -- do primeiro ao último pixel de tinta. A mediana, e não a média, porque a
    última linha de parágrafo é curta por definição e não diz nada sobre a coluna.

    **É julgada na corrida inteira, e uma corrida reprovada é descartada por completo** -- não se
    procura o pedaço dela que passaria. Um pedaço menor teria menos bandas para a mediana, e a
    busca voltaria a decidir por poucas linhas, que é o que `BANDAS_NA_REGIAO` existe para impedir.
    """
    return all(_preenchimento(mascaras, i, j, faixa, x_min) >= PREENCHIMENTO_DA_COLUNA
               for faixa in faixas)


def _preenchimento(
    mascaras: list[np.ndarray], i: int, j: int, faixa: tuple[int, int], x_min: int
) -> float:
    x1, x2 = faixa
    largura = max(1, x2 - x1)
    fracoes: list[float] = []
    for k in range(i, j):
        dentro = np.flatnonzero(mascaras[k][x1 - x_min : x2 - x_min + 1])
        if dentro.size:
            fracoes.append(float(dentro[-1] - dentro[0] + 1) / largura)
    return float(np.median(fracoes)) if fracoes else 0.0


def _fundir_iguais(
    cortadas: list[tuple[int, int, tuple[tuple[int, int], ...]]],
) -> list[tuple[int, int, tuple[tuple[int, int], ...]]]:
    """Junta regiões vizinhas de mesmas colunas. É o cabeçalho grudando no parágrafo de abertura:
    duas regiões de largura inteira em sequência são uma."""
    fundidas: list[tuple[int, int, tuple[tuple[int, int], ...]]] = []
    for a, b, faixas in cortadas:
        if fundidas and fundidas[-1][1] == a and fundidas[-1][2] == faixas:
            fundidas[-1] = (fundidas[-1][0], b, faixas)
        else:
            fundidas.append((a, b, faixas))
    return fundidas


def _com_cortes_em_y(
    cortadas: Sequence[tuple[int, int, tuple[tuple[int, int], ...]]],
    grupos: Sequence[Sequence[Caixa]],
    y_min: int,
    y_max: int,
) -> list[Regiao]:
    """Índices de banda -> cortes em `y` que ladrilham a folha.

    O corte fica **um pixel acima do topo da primeira banda da região seguinte**, e isso é exato:
    `linhas.bandas` percorre as caixas ordenadas por `y1`, então toda caixa de uma banda tem topo
    menor ou igual ao de qualquer caixa da banda seguinte.
    """
    regioes: list[Regiao] = []
    topo = y_min
    for k, (_, b, faixas) in enumerate(cortadas):
        ultima = k == len(cortadas) - 1
        base = y_max if ultima else min(c.y1 for c in grupos[b]) - 1
        regioes.append(Regiao(topo, base, faixas))
        topo = base + 1
    return regioes


__all__ = [
    "BANDAS_NA_REGIAO",
    "BORDA_MAX",
    "PREENCHIMENTO_DA_COLUNA",
    "VAO_DE_BORDA",
    "Regiao",
    "atribuir_regiao",
    "colunas_da_folha",
    "detectar_regioes",
]
