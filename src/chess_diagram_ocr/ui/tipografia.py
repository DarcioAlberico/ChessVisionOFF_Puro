"""A escala de fontes do produto, num lugar só — papéis, não números (S-149).

**O que havia antes.** Segoe UI 9 em toda a janela: título de grupo, rótulo de campo, dado e
barra de status com o mesmo tamanho e o mesmo peso. Uma tela sem hierarquia nenhuma para o olho
seguir — tudo igualmente importante é o mesmo que nada importante.

E havia um caso pior que uniformidade. **A FEN é o dado central deste produto**, e ela aparecia
em fonte proporcional. Em proporcional `1`, `l` e `I` têm larguras diferentes, `8/8/8` não
alinha com o `8/8/8` da linha de baixo, e comparar duas leituras da mesma posição — que é a
tarefa da aba Revisão e da segunda opinião da S-66 — passa a exigir contar caractere com o dedo
na tela. O projeto já tinha monoespaçada em dois lugares (`Consolas 10`, cravada) e não a tinha
onde ela decide alguma coisa.

**Este módulo é o irmão do `ui/tokens.py`, e pela mesma razão.** Sem `tkinter` aqui: a escala é
função pura de um tamanho-base, afirmável em 9, 10 e 12 sem abrir janela. Quem lê a
`TkDefaultFont` do sistema e entrega o resultado aos painéis é `ui/theme.py`, que já é o módulo
que sabe de aparência aplicada.

**Derivada, e não cravada.** Os tamanhos saem da `TkDefaultFont`: quem aumenta a fonte do
Windows aumenta a do programa junto. Uma escala de números fixos ignora essa configuração — e
ignorá-la é o mesmo defeito de DPI da S-148 num lugar menor.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import ceil

from . import pele

__all__ = [
    "ACAO",
    "ALTURA_DE_LINHA_NA_BASE",
    "AUXILIAR",
    "BASE_DE_REFERENCIA",
    "CORPO",
    "DADO",
    "DEGRAUS",
    "FATOR_DE_FOLGA",
    "FATOR_DE_LINHA",
    "FOLGA",
    "FOLGAS",
    "FOLGA_DE_LINHA",
    "FOLGA_DE_MOLDURA",
    "FOLGA_MINIMA",
    "LINHA_NA_BASE",
    "MONOESPACADAS_PREFERIDAS",
    "PAPEIS_DE_FOLGA",
    "PAPEIS_DE_FONTE",
    "PAPEL_POR_CLASSE",
    "PESOS",
    "PROPRIEDADE_DE_PAPEL_DE_FONTE",
    "TITULO",
    "altura_de_linha",
    "altura_do_texto",
    "corpo",
    "escala",
    "familia_monoespacada",
    "folga",
    "folgas",
    "fonte",
    "papel_de_fonte_por_classe",
    "peso",
]

TITULO = "TITULO"
"""Título de grupo (`LabelFrame`) e cabeçalho de seção: um degrau acima, e em negrito.

Os dois canais juntos de propósito. Só o tamanho, e a diferença de 1 pt não se vê; só o
negrito, e o título compete com o rótulo em vez de mandar nele."""

CORPO = "CORPO"
"""Rótulo, texto de linha, célula de tabela. O Segoe UI 9 de hoje, e o que a escala referencia."""

ACAO = "ACAO"
"""**O texto que se aperta**: rótulo de botão (F9-C3). Tamanho do corpo, peso meio-negrito.

Ele não é um degrau novo de tamanho -- é o segundo eixo. Ver `PESOS` para a medição que o pediu:
31 dos 106 widgets visíveis da Galeria são `QPushButton`, e o rótulo de um botão saía pixel a
pixel igual ao texto de uma célula de tabela."""

AUXILIAR = "AUXILIAR"
"""Texto secundário: contagem, procedência, linha do motor, barra de status.

Já tinha cor própria desde a S-145 (`TEXTO_SECUNDARIO`) e não tinha tamanho — o que fazia a
hierarquia depender só de contraste, que é o canal mais frágil dos dois."""

DADO = "DADO"
"""**Monoespaçada**: FEN, coluna de FEN, linha de PGN, caminho de arquivo.

O papel existe pelo que a proporcional faz com estes quatro, e não por estilo: `rn1qkbnr` e
`rnbqkbnr` têm a mesma largura em monoespaçada e larguras diferentes em proporcional. Comparar
duas leituras é alinhar duas linhas, e alinhar exige largura igual por caractere."""

PAPEIS_DE_FONTE: tuple[str, ...] = (TITULO, CORPO, ACAO, AUXILIAR, DADO)
"""Todos os papéis. Existe para o teste afirmar que a resolução é **total**."""

PROPRIEDADE_DE_PAPEL_DE_FONTE = "papel_de_fonte"
"""A propriedade dinâmica com que um widget declara em que degrau da escala ele está (F9-C2).

O caminho de escape da tabela de baixo: um `QLabel` que é título de estado vazio não tem classe
própria, e criar uma subclasse por degrau seria caro. Quem sabe o papel o escreve na construção,
e a varredura o obedece."""

PAPEL_POR_CLASSE: dict[str, str] = {
    "QGroupBox": TITULO,
    "QHeaderView": TITULO,
    "QPushButton": ACAO,
    "QToolButton": ACAO,
}
"""Classe do widget -> o degrau da escala que ela ocupa, quando ninguém declarou outro (F9-C2).

**O crítico do ciclo 1 mediu a escala que não estava sendo usada:** 104 widgets visíveis, **dois
tamanhos** (12 e 11 px) e **um peso** (400), com `TITULO` (10 pt/700) aplicado a **zero** widgets
-- ou seja, a escala existia em `DEGRAUS` e não existia na tela. Uma escala de quatro papéis que
resolve para duas combinações não ordena nada; ela só custa código.

As duas classes daqui são as duas que **mandam** numa região sem serem o conteúdo dela: o título
do grupo diz de que é o grupo, e o cabeçalho da coluna diz do que é a coluna. São os dois lugares
onde um degrau acima é informação e não decoração -- e são os dois que o crítico nomeou.

**A tabela é curta de propósito, e ela não menciona `QLabel`.** Rotular todo `QLabel` por classe
faria o degrau perder o sentido: metade dos rótulos da janela é conteúdo, não cabeçalho. Quem é
apoio se declara por `PROPRIEDADE_DE_PAPEL_DE_FONTE` ou pela propriedade `apoio` da folha de
estilo, que é a mesma decisão dita do lado do desenho.

**As duas linhas de botão são do F9-C3**, e elas são por classe justamente porque *toda* classe de
botão é comando: não há `QPushButton` que seja conteúdo. `QCheckBox` e `QRadioButton` ficam de
fora de propósito -- eles não são comandos, são o **estado** de uma opção, e o texto ao lado deles
é a opção e não a ação. Ver `PESOS`."""


def papel_de_fonte_por_classe(classes: tuple[str, ...]) -> str:
    """O degrau declarado da primeira classe conhecida da hierarquia. `""` se nenhuma o for.

    Recebe os **nomes** das classes e não as classes, pela razão de `nomes_acessiveis`: a decisão
    tem de ser afirmável sem importar toolkit nenhum.
    """
    for classe in classes:
        if classe in PAPEL_POR_CLASSE:
            return PAPEL_POR_CLASSE[classe]
    return ""

DEGRAUS: dict[str, int] = {
    TITULO: +3,
    CORPO: 0,
    ACAO: 0,
    AUXILIAR: -1,
    DADO: 0,
}
"""Quantos pontos cada papel fica **acima ou abaixo** da fonte do sistema.

**O título subiu de +1 para +3 no F9-C3, e o motivo é uma medição feita duas vezes.** A escala era
`8 / 9 / 10 pt` = **11 / 12 / 13 px**, dois degraus de **+9 %** e **+8 %** -- e o crítico do ciclo
1 já tinha escrito, com estas palavras, que *"uma diferença de 1 px em 12 (8 %) não produz
hierarquia"*. A resposta do ciclo 2 foi acrescentar um terceiro tamanho exatamente nesse degrau, e
o ciclo 3 mediu o resultado: **99 de 107 widgets (92,5 %) numa única combinação tipográfica**.

Agora é `8 / 9 / 12 pt` = **11 / 12 / 16 px**: o degrau entre corpo e título passou de +8 % para
**+33 %**. É mais que a razão 1,2 de uma escala de página, e é de propósito -- numa janela densa o
título aparece três vezes por aba e precisa ser lido de relance, não comparado lado a lado.

O degrau de baixo continua em -1 pt (11 px contra 12), e isso é decisão e não sobra: `AUXILIAR` se
separa pela **cor** antes de se separar pelo tamanho (ele é o papel de `TEXTO_SECUNDARIO` desde a
S-145), e descê-lo a 10 px esbarraria em `MINIMO_LEGIVEL` na primeira pessoa que pusesse a fonte
do Windows em 10.

`DADO` e `ACAO` ficam no tamanho do corpo porque nenhum dos dois é ênfase de nível: um é outra
**família** -- a FEN monoespaçada gritaria se crescesse numa linha que ela já ocupa inteira -- e o
outro é outro **peso**. Ver `PESOS`."""

PESOS: dict[str, int] = {
    TITULO: 700,
    ACAO: 600,
    CORPO: 400,
    AUXILIAR: 400,
    DADO: 400,
}
"""O peso de cada papel, na escala de 100 a 900 do CSS e do Qt (F9-C3).

**O segundo eixo da escala, e ele existe porque o primeiro não bastava.** Dos oito papéis que o
ciclo 1 listou como tipograficamente idênticos -- rótulo de menu, rótulo de aba, rótulo de botão,
título de grupo, cabeçalho de coluna, dado da tabela, estado vazio, barra de status -- **cinco
continuavam iguais** depois do ciclo 2, e o maior grupo deles é o rótulo de botão: **31 dos 106
widgets visíveis da Galeria são `QPushButton`**, e o texto de um botão saía pixel a pixel igual ao
texto de uma célula de tabela.

`ACAO` a 600 diz a coisa mais simples que uma janela pode dizer sobre o próprio texto: **o que se
aperta é mais pesado do que o que se lê.** Não é decoração; é a separação entre comando e
conteúdo, que numa tela com 31 botões é a primeira pergunta que o olho faz.

Meio-negrito e não negrito: 700 já é o título, e um botão com o peso do título competiria com o
grupo que o contém. 600 é o degrau que existe entre os dois em toda família de sistema -- a Segoe
UI tem Semibold desenhado, e não sintetizado."""


def peso(papel: str) -> int:
    """O peso daquele papel. Levanta para papel desconhecido, como `fonte` e `corpo`.

    Separado de `fonte()` porque aquela devolve a especificação do Tk, que só sabe dizer
    `"bold"`: um `600` na tupla do Tk seria um valor que o toolkit de origem não entende. Quem
    consome os dois eixos é `qt/tema.fonte_atual`, e ele é o único que precisa do número.
    """
    if papel not in PESOS:
        raise KeyError(f"papel de fonte desconhecido: {papel!r}. Os válidos estão em PAPEIS_DE_FONTE.")
    return PESOS[papel]

MINIMO_LEGIVEL = 7
"""Nenhum papel desce daqui, mesmo que a fonte do sistema esteja em 7.

O piso não é gosto: abaixo de 7 pt o Windows deixa de aplicar *hinting* na Segoe UI e as
hastes de `l`, `i` e `1` colapsam. Numa janela cujo trabalho é distinguir `1` de `l` numa FEN,
esse é exatamente o caractere que não pode colapsar."""


MONOESPACADAS_PREFERIDAS = ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Menlo", "Liberation Mono")
"""Monoespaçadas em ordem de preferência, antes de aceitar a que o Tk indicar.

**Por que não confiar direto na `TkFixedFont`.** No Windows ela resolve para **Courier New** —
uma fonte de máquina de escrever, de hastes finas, desenhada para impressão em 1955. Numa FEN
de 70 caracteres na tela ela é justamente onde `1` e `l` voltam a se parecer, que é o defeito
que a monoespaçada veio corrigir.

Consolas vem primeiro porque acompanha o Windows desde o Vista, tem zero cortado e distingue
`1`, `l` e `I` por desenho e não por largura. As outras cobrem Linux e macOS. `Courier New`
**não** está na lista de propósito: se nenhuma daqui existir, a reserva é a que o Tk indicar,
e aí ela entra por ser o que o sistema tem — não por ter sido escolhida."""


def familia_monoespacada(disponiveis: Iterable[object], reserva: str) -> str:
    """A melhor monoespaçada que este sistema tem, ou a `reserva` do Tk. Pura.

    `disponiveis` é o que `tkinter.font.families()` devolveu; qualquer iterável de nomes serve,
    e é o que permite testar a escolha em três sistemas diferentes sem ter os três.
    """
    try:
        instaladas = {str(nome).strip().casefold() for nome in disponiveis}
    except TypeError:  # pragma: no cover - Tk que não responde a lista de famílias
        return reserva
    for nome in MONOESPACADAS_PREFERIDAS:
        if nome.casefold() in instaladas:
            return nome
    return reserva


def escala(base: int) -> dict[str, int]:
    """O tamanho em pontos de cada papel, dado o tamanho-base do sistema.

    Função pura, e é o ponto: a escala é afirmável em 9, 10 e 12 sem abrir janela e sem trocar
    a fonte do Windows. Um `base` não positivo — o que uma `TkDefaultFont` exótica devolve —
    cai no piso, porque fonte de tamanho zero não é fonte pequena, é widget vazio.
    """
    if base <= 0:
        base = MINIMO_LEGIVEL
    return {papel: max(MINIMO_LEGIVEL, base + degrau) for papel, degrau in DEGRAUS.items()}


ALTURA_POR_PONTO = 15 / 8
"""Quantos pixels de altura ocupa **um ponto** de texto desenhado, a 96 dpi. Por cima.

Medido nesta árvore, com a Segoe UI que `capture.impor_a_fonte_do_produto` impõe --
`QFontMetrics.height()`, que é ascendente mais descendente, dividido pelo tamanho em ponto:

    7pt->12   8pt->15   9pt->16  10pt->17  11pt->20  12pt->21  13pt->22
   14pt->26  15pt->27  16pt->28  18pt->32  20pt->36  24pt->43

A maior das razões é a de 8 pt, **15/8 = 1,875**, e é ela que está aqui. **Por cima de propósito:**
quem reserva espaço para texto desenhado só tem um modo de errar que apaga letra, que é reservar
de menos. Dois pixels sobrando são ar; dois pixels faltando são a metade de baixo de um `g`.
"""


def altura_do_texto(pontos: int) -> int:
    """A altura em pixel de uma linha de texto daquele tamanho em ponto. Pura, e por cima.

    **Existe porque a folha de estilo reservava com um token de espaçamento o lugar de um degrau
    da escala tipográfica** (F9-C13, o bloqueante). `QGroupBox { margin-top: espaco.linha() }` --
    4 px na compacta -- guardava a faixa em que `QGroupBox::title { font-size: 12pt; bold }`
    desenha **21 px**, e o primeiro filho do grupo subia para dentro do que sobrava: `Lances`,
    `Comentário do lance` e `Filtros` chegavam à tela com 8 dos seus 21 px apagados por baixo de
    um `QTextBrowser`, de um `QTextEdit` e de um `QLineEdit`. Os dois números vinham de escalas
    diferentes e por isso nunca podiam se encontrar.

    **A resposta é fazer a reserva sair da mesma escala que pinta**, e é o que esta função
    permite: `folha_de_estilo` reserva `altura_do_texto(escala(base)[TITULO])` e pinta
    `escala(base)[TITULO]`. Um degrau a mais no título passa a mover a faixa junto -- a deriva
    deixa de ser possível em vez de ser consertada de novo no ciclo seguinte.

    **Pura, e por isso aproximada.** A altura exata é da fonte instalada e do dpi da tela, e quem
    tem toolkit deve perguntá-la a `QFontMetrics` -- é o que `qt/tema.altura_do_titulo_atual` faz,
    e o que a folha usa quando há aplicação. Esta conta é a reserva de quem não tem tela: ela
    responde no venv sem binding de Qt, que é onde o teste desta folha roda.

    Tamanho não positivo cai em zero pixel de reserva? Não: cai no piso de 1 px, pela mesma razão
    de `folga` -- uma reserva de zero é uma reserva que não existe.
    """
    return max(1, ceil(max(0, int(pontos)) * ALTURA_POR_PONTO))


def corpo(degrau: int, *, base: int, papel: str = CORPO) -> int:
    """O tamanho em pontos daquele papel, `degrau` degraus acima ou abaixo dele (S-260). Pura.

    **É aqui que o degrau vira ponto, e em nenhum outro lugar.** O documento guarda `corpo=+2`
    porque `+2` é uma escolha do autor que vale em qualquer fonte de sistema; quem tem de saber
    quanto isso mede é este módulo, que já sabe quanto medem os quatro papéis. Um `12` cravado na
    aba de texto ou no exportador ignoraria quem aumentou a fonte do Windows -- a regra 3 da
    SPEC_EDITOR, e o defeito de DPI da S-148 num lugar menor.

    O degrau vale **um ponto**, como os degraus de `DEGRAUS`: a escala curta do topo deste arquivo é
    a mesma para os dois, e dois passos diferentes na mesma janela dariam um título de estilo e um
    título de mão com corpos que não coincidem.

    O piso é `MINIMO_LEGIVEL`, e ele é o mesmo de `escala` pela mesma razão -- abaixo de 7 pt as
    hastes de `l`, `i` e `1` colapsam, e distinguir esses três é o trabalho desta janela. É o piso
    que fecha a faixa por baixo, e é por isso que `rico.CORPO_MINIMO` não precisa repeti-lo.
    """
    if papel not in DEGRAUS:
        raise KeyError(f"papel de fonte desconhecido: {papel!r}. Os válidos estão em PAPEIS_DE_FONTE.")
    if base <= 0:
        base = MINIMO_LEGIVEL
    return max(MINIMO_LEGIVEL, escala(base)[papel] + int(degrau))


def fonte(
    papel: str,
    *,
    base: int,
    familia: str,
    mono: str,
    negrito: bool = False,
) -> tuple[str, int] | tuple[str, int, str]:
    """A especificação de fonte do Tk para um papel: `(família, tamanho[, peso])`.

    Levanta `KeyError` para papel desconhecido, e é a mesma disciplina de `tokens.cor`: um papel
    escrito errado que caísse no corpo viraria um widget de fonte plausível e sem significado,
    que é o estado de que este módulo veio tirar a janela.

    `negrito` é do chamador e não do papel porque há um uso legítimo fora do `TITULO` — a linha
    escolhida numa lista, que precisa de peso sem mudar de nível hierárquico.
    """
    if papel not in DEGRAUS:
        raise KeyError(f"papel de fonte desconhecido: {papel!r}. Os válidos estão em PAPEIS_DE_FONTE.")
    tamanho = escala(base)[papel]
    nome = mono if papel == DADO else familia
    return (nome, tamanho, "bold") if (negrito or papel == TITULO) else (nome, tamanho)


# ------------------------------------------------------- a densidade, e o espaço dela (S-232)
#
# **Por que o espaço mora no módulo da fonte.** Ele não é uma segunda escala: é a mesma, medida na
# outra direção. A S-149 já derivou os tamanhos da `TkDefaultFont` porque quem aumenta a fonte do
# Windows quer o programa maior -- e uma janela de fonte 12 com o vão de fonte 9 fica *mais*
# apertada, não igual. Os dois números têm de sair da mesma base ou eles divergem, que é a mesma
# razão de `ui/comandos.py` existir para os rótulos.

BASE_DE_REFERENCIA = 9
"""O tamanho em que a janela de hoje foi desenhada -- a Segoe UI 9 do topo deste arquivo.

É o que faz `FOLGAS` ser uma leitura da janela e não uma escala inventada: nesta base, cada papel
devolve exatamente o número que já está escrito no `padx`/`pady` correspondente."""

LINHA_NA_BASE = 15
"""O `linespace` do corpo nesta base, em pixel. É o `round(9 * 5 / 3)` de `fita.linhas_de_fonte`."""

ALTURA_DE_LINHA_NA_BASE = 20
"""A altura de linha do `ttk.Treeview` nesta base, em pixel -- **o padrão do Tk, medido**.

Está aqui para que a densidade confortável reproduza a janela de hoje **por construção** e não
por coincidência: `altura_de_linha` devolve `linha + 5` porque 20 − 15 = 5, e não porque 5 é um
número bonito."""

FOLGA_DE_MOLDURA = "FOLGA_DE_MOLDURA"
"""A moldura interna de uma janela de diálogo: o `padding=14` da legenda e da paleta."""

FOLGA = "FOLGA"
"""O vão do cromo da janela contra a borda: o `padx=10` da faixa onde a fila e a fita moram."""

FOLGA_DE_LINHA = "FOLGA_DE_LINHA"
"""Entre uma linha de cromo e a seguinte: o `pady=6` da mesma faixa, e o de uma barra para a outra."""

FOLGA_MINIMA = "FOLGA_MINIMA"
"""Entre dois vizinhos do mesmo grupo: o `padx=2` entre dois botões de fita.

O piso é 1 e não 0, e a razão é de desenho: dois botões colados viram um controle só para o olho,
e a densidade compacta existe para caber, não para fundir."""

PAPEIS_DE_FOLGA: tuple[str, ...] = (FOLGA_DE_MOLDURA, FOLGA, FOLGA_DE_LINHA, FOLGA_MINIMA)
"""Todos os papéis de espaço. Existe para o teste afirmar que a resolução é total, como
`PAPEIS_DE_FONTE`."""

FOLGAS: dict[str, int] = {
    FOLGA_DE_MOLDURA: 14,
    FOLGA: 10,
    FOLGA_DE_LINHA: 6,
    FOLGA_MINIMA: 2,
}
"""Quantos pixels cada papel vale na densidade confortável, na base de referência.

**São os números que já estão na janela**, e não uma escala nova: 14 é o `padding` da legenda de
atalhos, 10 e 6 são o `padx`/`pady` da faixa de cromo, e 2 é o `padx` entre dois botões de fita
que a S-228 mediu. A densidade confortável não muda a janela de hoje porque ela **é** a janela de
hoje escrita como dado -- o mesmo movimento que a S-324 fez com os rótulos."""

FATOR_DE_FOLGA: dict[str, float] = {pele.CONFORTAVEL: 1.0, pele.COMPACTA: 0.7}
"""O multiplicador de espaço por densidade. O 0,7 é o da tabela da S-232."""

FATOR_DE_LINHA: dict[str, float] = {pele.CONFORTAVEL: 1.0, pele.COMPACTA: 0.8}
"""O multiplicador da altura de linha de tabela. **0,8 e não 0,7, e a diferença é o conteúdo.**

Espaço vazio encolhe até sumir sem custo; altura de linha carrega texto, e abaixo do `linespace`
ela corta a letra em vez de aproximá-la. A tabela da S-232 já separa os dois fatores, e o piso de
`altura_de_linha` é quem garante que o menor dos dois nunca alcance a letra."""


def folga(papel: str, *, base: int = BASE_DE_REFERENCIA, densidade: str = pele.CONFORTAVEL) -> int:
    """O espaço daquele papel, em pixel, para esta fonte e esta densidade. Pura.

    Levanta `KeyError` para papel ou densidade desconhecidos, como `fonte` e `tokens.cor`: um
    papel escrito errado que caísse no menor devolveria um vão plausível e sem significado.

    O piso é **1 px** e não 0. Dois vizinhos colados viram um controle só para o olho, e a
    densidade compacta existe para caber -- não para fundir. Sem o piso, `FOLGA_MINIMA` a 0,7
    chegaria a 0 na primeira fonte pequena.
    """
    if papel not in FOLGAS:
        raise KeyError(f"papel de folga desconhecido: {papel!r}. Os válidos estão em PAPEIS_DE_FOLGA.")
    if densidade not in FATOR_DE_FOLGA:
        raise KeyError(f"densidade desconhecida: {densidade!r}. As válidas estão em pele.DENSIDADES.")
    if base <= 0:
        base = MINIMO_LEGIVEL
    proporcional = FOLGAS[papel] * base / BASE_DE_REFERENCIA
    return max(1, round(proporcional * FATOR_DE_FOLGA[densidade]))


def folgas(*, base: int = BASE_DE_REFERENCIA, densidade: str = pele.CONFORTAVEL) -> dict[str, int]:
    """Os quatro papéis de uma vez. É o que um painel pergunta quando monta várias linhas."""
    return {papel: folga(papel, base=base, densidade=densidade) for papel in PAPEIS_DE_FOLGA}


def altura_de_linha(linha_de_texto: int, *, densidade: str = pele.CONFORTAVEL) -> int:
    """A altura de uma linha de tabela, em pixel -- o `rowheight` do `Treeview`. Pura.

    `linha_de_texto` é o `linespace` da fonte de corpo, e é por ele que a altura acompanha a fonte
    do sistema em vez de cravar pixel.

    **O piso é o próprio texto mais um.** Uma linha mais baixa que o `linespace` não é uma tabela
    apertada: é uma tabela que corta a perna do `g` e o acento do `á`, e numa coluna de FEN e de
    nome de livro isso é o dado.

    O piso não é teórico: ele **já morde na base de referência**. Com `linespace` 15 a compacta dá
    `round(20 x 0,8) = 16` e o piso é 16 -- empatam. Com a fonte do Windows em 12 (`linespace` 20)
    a conta dá 20 e o piso 21, e é o piso que responde. Ou seja: **da fonte 12 para cima, a
    densidade compacta deixa de encolher a tabela**, porque não há o que encolher sem cortar
    letra. É a resposta certa, e ela fica dita aqui em vez de virar um relato de "a compacta não
    faz nada nesta máquina".
    """
    if densidade not in FATOR_DE_LINHA:
        raise KeyError(f"densidade desconhecida: {densidade!r}. As válidas estão em pele.DENSIDADES.")
    confortavel = linha_de_texto + (ALTURA_DE_LINHA_NA_BASE - LINHA_NA_BASE)
    return max(linha_de_texto + 1, round(confortavel * FATOR_DE_LINHA[densidade]))
