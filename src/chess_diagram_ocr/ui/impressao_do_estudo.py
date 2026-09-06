"""A paginação de livro: que pedaço de que bloco cai em que página (S-545).

**O que faltava.** O estudo já saía em quatro formatos de texto (S-289) e em EPUB e DOCX (S-542 e
S-543), e em todos eles quem pagina é o programa que abre o arquivo -- o leitor de EPUB reflui, o
Word quebra onde couber. Não havia caminho nenhum para **imprimir**, nem para o PDF, que é o
formato em que a página é decidida aqui e não lá. E é justamente onde a quebra importa: um
diagrama no alto de uma página e o lance que o pede no pé da anterior obrigam a virar a folha
para trás a cada exercício.

Este módulo é **a decisão de onde a página quebra**, e nada mais. Quem mede a linha e quem
desenha é `qt/impressao_do_estudo.py`: sob o toolkit, a altura de um parágrafo depende da fonte,
da largura da coluna e da resolução do dispositivo, e nenhuma dessas três é decisão -- são
medidas. A travessia por baixo continua sendo `estudo_paragrafos.paragrafos`, a mesma que o EPUB
e o DOCX leem, e é isso que impede o PDF de discordar deles sobre onde a variante começa.

## A unidade é a linha, e é o que torna a decisão fazível

Paginar por **parágrafo** parece mais simples e não funciona: um estudo de 300 lances sem
comentário nenhum é um parágrafo só, mais alto que a página inteira, e uma regra de "parágrafo
não se parte" o deixaria sem lugar onde caber. Então o desenho mede o parágrafo **já quebrado em
linhas** e entrega as alturas; aqui se decide quantas dessas linhas cabem, e o que não pode ser
separado do quê. Um diagrama é uma linha só -- ele não se parte por construção.

## As três regras, e as três vieram de folha impressa

1. **O diagrama não se separa do lance que o pede.** É o item. `[%D]` põe o diagrama depois do
   comentário do lance, e os dois são uma frase; quebrar entre eles obriga a virar a folha para
   trás. O bloco anterior a um diagrama é marcado `com_o_proximo`, e o par anda junto.
2. **O título não fica sozinho no pé da página.** É a viúva clássica da tipografia, e a resposta
   é a mesma da regra 1 -- o título é `com_o_proximo` do primeiro bloco do capítulo.
3. **Nem uma linha nem duas ficam soltas.** `ORFAS` linhas é o mínimo que se deixa embaixo e o
   mínimo que se leva para a página seguinte; abaixo disso o parágrafo inteiro desce. A exceção é
   a página **vazia**: ali sempre se põe o que couber, senão um parágrafo mais alto que a página
   não caberia em lugar nenhum e a paginação não terminaria.

Sem toolkit e sem disco, como todo módulo de `ui/`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..estudo import Estudo
from ..estudo_paragrafos import DIAGRAMA, TITULO, paragrafos

__all__ = [
    "LARGURA_DO_DIAGRAMA",
    "MARGEM_MM",
    "Bloco",
    "Pagina",
    "Pedaco",
    "blocos_do_estudo",
    "cabecalho",
    "frase_do_pdf",
    "paginar",
    "rodape",
]

MARGEM_MM = 18.0
"""A margem da página, em milímetros, igual nos quatro lados.

Dezoito e não os 25,4 do Word: a folha aqui leva diagrama, e um tabuleiro numa coluna de 160 mm
imprime a casa com 8 mm -- que é o tamanho em que um livro de xadrez a imprime. Igual nos quatro
lados porque o estudo não é encadernado: quem imprime frente e verso com lombada ajusta na caixa
de diálogo do sistema, que é onde essa escolha mora.
"""

LARGURA_DO_DIAGRAMA = 0.55
"""Que fração da coluna o diagrama ocupa. **Proporção, e não milímetro**: a mesma decisão vale na
folha A4 e na Carta, e vale na pré-visualização, que desenha noutra escala.

Pouco mais de metade da coluna, e centrado: é como os livros de xadrez imprimem o diagrama no
meio da análise -- grande o bastante para se ler a casa a um palmo, pequeno o bastante para não
empurrar a linha inteira para a página seguinte. A 160 mm de coluna dá 88 mm, ou 11 mm por casa.
"""

ORFAS = 2
"""O mínimo de linhas de um parágrafo que fica numa página. Ver a regra 3 do cabeçalho.

Duas, e não três: as linhas aqui são de notação -- `12.Bxf7+ Kxf7 13.Ng5+` --, e uma exigência de
três empurraria para a página seguinte quase todo parágrafo de linha principal, que é curto por
construção. Três é a régua da prosa corrida, e esta folha não é de prosa corrida.
"""


@dataclass(frozen=True)
class Bloco:
    """Um bloco imprimível do estudo. É o `estudo_paragrafos.Paragrafo` mais a regra de coesão."""

    tipo: str
    texto: str = ""
    nivel: int = 0
    fen: str = ""
    virado: bool = False
    numero: int = 0

    com_o_proximo: bool = False
    """Este bloco **não** pode ser o último da página: o que vem depois é dele. Ver as regras 1 e
    2 do cabeçalho -- o lance que pede o diagrama, e o título que abre o capítulo."""


@dataclass(frozen=True)
class Pedaco:
    """Um pedaço de bloco desenhado numa página: quais linhas dele, e onde.

    `de` e `ate` são índices de linha no estilo do Python -- `ate` exclusivo --, então um bloco
    inteiro de cinco linhas é `de=0, ate=5` e um diagrama é sempre `de=0, ate=1`.
    """

    bloco: int
    de: int
    ate: int
    topo: float
    """A distância do alto da **área útil** (a página menos as margens) até o alto deste pedaço."""

    altura: float


@dataclass(frozen=True)
class Pagina:
    """Uma página pronta: o número dela, a partir de 1, e o que se desenha nela."""

    numero: int
    pedacos: tuple[Pedaco, ...] = ()


def blocos_do_estudo(estudo: Estudo) -> tuple[Bloco, ...]:
    """Os blocos do estudo, na ordem do livro, já com a coesão marcada.

    **A lista é a de `estudo_paragrafos`, e não uma segunda**: o PDF impresso e o capítulo do EPUB
    mostram os mesmos parágrafos do mesmo estudo, ou a folha discordaria do livro exportado pelo
    programa. O que se acrescenta aqui é só a resposta a *"este pode ser o último da página?"*.
    """
    lista = paragrafos(estudo)
    saida: list[Bloco] = []
    for indice, paragrafo in enumerate(lista):
        proximo = lista[indice + 1] if indice + 1 < len(lista) else None
        saida.append(
            Bloco(
                tipo=paragrafo.tipo,
                texto=paragrafo.texto,
                nivel=paragrafo.nivel,
                fen=paragrafo.fen,
                virado=paragrafo.virado,
                numero=paragrafo.numero,
                com_o_proximo=proximo is not None
                and (proximo.tipo == DIAGRAMA or paragrafo.tipo == TITULO),
            )
        )
    return tuple(saida)


def paginar(
    alturas: Sequence[Sequence[float]],
    *,
    altura_util: float,
    espaco: float = 0.0,
    com_o_proximo: Sequence[bool] = (),
    orfas: int = ORFAS,
) -> tuple[Pagina, ...]:
    """Distribui as linhas medidas pelas páginas. Pura: aritmética sobre alturas.

    `alturas[i]` são as alturas das linhas do bloco `i`, na ordem; `com_o_proximo[i]` diz se o
    bloco `i` anda colado no `i+1`. `espaco` é o vão entre dois blocos vizinhos da mesma página --
    ele **não** é cobrado no alto da página, que é onde a margem já responde.

    Devolve pelo menos uma página, mesmo sem bloco nenhum: uma folha em branco com cabeçalho e
    número é o que sai de um estudo vazio, e é melhor que um `QPrinter` que não recebe página.
    """
    limite = max(1.0, float(altura_util))
    paginas: list[Pagina] = []
    atual: list[Pedaco] = []
    topo = 0.0

    def virar() -> None:
        nonlocal atual, topo
        paginas.append(Pagina(len(paginas) + 1, tuple(atual)))
        atual, topo = [], 0.0

    for grupo in _grupos(len(alturas), com_o_proximo):
        junto = sum(sum(alturas[indice]) for indice in grupo) + espaco * (len(grupo) - 1)
        # A regra 1: o grupo inteiro desce se não couber aqui **e** couber numa página limpa.
        # Sem a segunda metade, um grupo mais alto que a folha viraria página para sempre.
        if atual and junto > limite - topo and junto <= limite:
            virar()
        for indice in grupo:
            linhas = list(alturas[indice])
            if not linhas:
                continue
            de = 0
            while de < len(linhas):
                vao = espaco if atual else 0.0
                cabem = _cabem(linhas[de:], limite - topo - vao)
                faltam = len(linhas) - de - cabem
                apertado = faltam > 0 and (cabem < orfas or faltam < orfas)
                if atual and (cabem == 0 or apertado):
                    virar()
                    continue
                # Página limpa em que nem a primeira linha cabe: ela sai transbordando, e é o
                # único caso em que isso acontece. Ver a exceção da regra 3.
                cabem = max(1, cabem)
                altura = sum(linhas[de : de + cabem])
                atual.append(Pedaco(indice, de, de + cabem, topo + vao, altura))
                topo += vao + altura
                de += cabem
    virar()
    return tuple(paginas)


def _grupos(quantos: int, com_o_proximo: Sequence[bool]) -> list[list[int]]:
    """Os blocos agrupados pelo que não se separa. Um bloco solto é um grupo de um."""
    grupos: list[list[int]] = []
    atual: list[int] = []
    for indice in range(quantos):
        atual.append(indice)
        colado = indice < len(com_o_proximo) and bool(com_o_proximo[indice])
        if not colado or indice == quantos - 1:
            grupos.append(atual)
            atual = []
    return grupos


def _cabem(linhas: Sequence[float], espaco_livre: float) -> int:
    """Quantas das primeiras linhas cabem naquela altura. Zero quando nem a primeira cabe."""
    somado, quantas = 0.0, 0
    for altura in linhas:
        if somado + altura > espaco_livre:
            break
        somado += altura
        quantas += 1
    return quantas


def cabecalho(titulo: str, numero: int) -> str:
    """A linha de topo daquela página: o nome do estudo, ou vazio.

    **Vazio na primeira**, e é a regra do livro impresso: o título está no corpo da página de
    abertura, dois centímetros abaixo, e repeti-lo na linha de topo é dizer a mesma coisa duas
    vezes no mesmo campo de visão. Da segunda em diante ele é o que diz de que capítulo é a folha
    que se está segurando.
    """
    return "" if numero <= 1 else " ".join(str(titulo or "").split())


def rodape(numero: int, total: int) -> str:
    """O número da página, com quantas há. `3 de 12`.

    Com o total, e não só o número: uma folha solta de um lote impresso não diz de onde saiu nem
    quantas faltam, e "de 12" responde as duas coisas com duas letras.
    """
    return f"{max(1, int(numero))} de {max(1, int(total))}"


def frase_do_pdf(caminho: str, paginas: int, tamanho: int) -> str:
    """O que a barra de status diz quando o PDF fica pronto.

    Traz o **caminho inteiro** pela razão da S-546: quem acabou de gravar precisa saber onde
    procurar, e "na pasta escolhida" não é um caminho.
    """
    return f"{paginas} página(s) em {caminho} ({tamanho / 1024:.1f} KB)."
