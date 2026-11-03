"""O que a árvore de aberturas mostra, em que ordem, e o que ela se recusa a afirmar (S-535).

**Este módulo é a leitura; `arvore_de_aberturas.py` é o arquivo.** Lá ficam a passada que constrói
e a consulta que responde; aqui, as colunas (`COLUNAS`), a ordem (`linhas`), o que vira travessão
e o que vira frase. É a mesma fronteira de `ui/busca_de_partidas.py`, e pelo mesmo motivo: a
percentagem que a tabela mostra tem de ser afirmável sem abrir janela.

**A ordem é por número de partidas, como no ChessBase.** Não é por percentagem de vitória, e a
diferença é o item inteiro: ordenar por percentagem põe no topo o lance jogado uma vez que ganhou
uma vez, e a pergunta de quem abre uma árvore de aberturas é *o que se joga aqui* -- a frequência
é a resposta, e a percentagem é o que se lê depois de achar a linha. Empate de frequência desempata
pelo SAN, para a mesma posição sair na mesma ordem em duas execuções.

**Três coisas não se mostram, e cada uma é um número que mentiria.**

1. **A percentagem de um punhado.** Abaixo de `MINIMO_PARA_PERCENTUAL` partidas decididas, as três
   percentagens saem como travessão e a barra não é desenhada: `100% das brancas` sobre uma
   partida é a forma de número enganoso que a S-135 custou caro -- ele parece uma medida e é uma
   amostra de um. O número de partidas continua lá, que é o que aquela linha de fato sabe.
2. **O Elo e o ano que a base não tem.** `soma_elo` acumula só as partidas com os dois Elos, e
   `soma_ano` só as com data. Zero partidas com Elo dá travessão, e não `0` -- que seria lido como
   um rating (é a decisão de `ui/lista_de_partidas.linha`, aqui de novo).
3. **O lance que não é legal na posição perguntada.** A chave da árvore é um resumo de 64 bits da
   colocação e da vez (ver `arvore_de_aberturas.chave_da_posicao`), e duas posições podem colidir
   -- ~2×10⁻⁵ de chance em toda a gigabase. `linhas` recusa o ramo cujo SAN a posição não sustenta:
   a colisão vira lance faltando, e não estatística de outra posição em silêncio.

**A abertura de cada lance é o nome da linha, e não o do código** (S-534): `frase_da_abertura`
dá *Ruy Lopez, Berlin Defense, Open Variation* onde `nome(codigo)` daria *Ruy Lopez* em nove
códigos diferentes. É o nome que o ChessBase escreve ao lado do lance, e é a razão de a coluna
existir -- ela responde *que abertura estou entrando se jogar isto*.

Nada de `PyQt6`. `chess` sim -- a legalidade de um lance e a abertura de uma posição são decisões,
e as duas precisam do tabuleiro (`ui/legality.py` e `ui/board_model.py` já o importam).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import chess

from .. import eco as eco_mod
from ..arvore_de_aberturas import ACHOU, COMO_CONSTRUIR, FUNDO_DEMAIS, SEM_ARVORE, SEM_PARTIDA
from . import tokens
from .busca_de_partidas import Filtro
from .tabela import Coluna

__all__ = [
    "COLUNAS",
    "CONTORNO_DA_BARRA",
    "CORES_DA_BARRA",
    "EM_BUSCA",
    "TINTAS_DA_BARRA",
    "Linha",
    "busca_da_posicao",
    "e_aviso",
    "frase_da_construcao",
    "frase_do_fim",
    "linhas",
    "perde_trabalho_ao_fechar",
    "resumo",
]

MINIMO_PARA_PERCENTUAL = 5
"""Quantas partidas **decididas** um ramo precisa ter para as percentagens aparecerem.

**É o erro padrão que escolhe o número, e não o gosto.** O maior erro padrão de uma proporção com
`n` observações é `0,5/√n`: com uma partida decidida a barra diz `100%` e o intervalo é a régua
inteira; com 5 o erro padrão cai a 22 pontos, com 10 a 16 e com 20 a 11. Cinco é onde a barra
começa a dizer alguma coisa -- *"as brancas vão bem aqui"* -- sem prometer a segunda casa.

Abaixo dele a linha continua na tabela com o número de partidas: o que se esconde é a
**percentagem**, que é a afirmação, e não o fato de a base ter jogado aquele lance.

Fora do `__all__` porque quem o aplica é `_percentagens`, aqui dentro: quem chama de fora recebe a
célula já decidida, e um segundo lugar aplicando o corte seria o lugar onde os dois divergem."""

EM_BUSCA = "Procurando na árvore…"
"""O que a tabela diz enquanto a thread trabalha. A consulta é uma sonda de chave primária -- ver
`arvore_de_aberturas.consultar` --, mas o arquivo tem mais de um gigabyte e a primeira leitura de
um SQLite frio custa o disco; a janela não para por causa disso."""

_TRACO = "—"
"""O que uma célula sem valor mostra. Travessão e não zero, pela decisão de
`ui/lista_de_partidas.linha`: `0` numa coluna de Elo é lido como um Elo."""

_SEPARADOR = " · "
"""Entre fatos, o ponto médio de `eco.SEPARADOR` e de `ui/busca_de_partidas`."""

COLUNAS: tuple[Coluna, ...] = (
    Coluna("lance", "Lance", 76),
    Coluna("partidas", "Partidas", 104, numerica=True),
    Coluna("resultado", "Brancas / empate / pretas", 176),
    Coluna("elo", "Elo", 62, numerica=True),
    Coluna("ano", "Ano", 118, numerica=True),
    Coluna("abertura", "Abertura", 230, elastica=True),
)
"""As seis colunas, na ordem da pergunta: **o lance primeiro**, porque é ele que se procura na
lista; quantas partidas, que é a ordem; como elas terminaram; quem as jogou e quando; e o nome da
linha por último, que é a etiqueta -- a mesma ordem de `ui/busca_de_partidas.COLUNAS`, onde o ECO
também fecha a fileira.

**"Partidas" e "Ano" são numéricas apesar de a célula ter texto ao lado.** A célula de partidas é
`8609 · 31%` e a de ano é `2005 (1857–2026)`: `qt/tabela._numero` lê o primeiro token, então a
ordenação pelo cabeçalho compara 8609 com 12 e não `"8609"` com `"12"`. É por isso que o milhar
sai **sem** separador aqui, ao contrário da frase de resumo -- `8.609` viraria o número 8,609.

A abertura é a elástica: é o único campo cujo comprimento não tem teto
(*Sicilian Defense, Najdorf Variation, English Attack* numa coluna só)."""

CORES_DA_BARRA: tuple[str, str, str] = (tokens.GLIFO_CLARO, tokens.DISPENSADO, tokens.GLIFO_ESCURO)
"""Os três tons da barra de resultado: brancas, empate, pretas -- **nessa ordem**.

**São as cores das peças, e não três cores novas.** A barra do Lichess é branco / cinza / preto
porque ela é sobre as peças, e `GLIFO_CLARO` (#f8f8f8) e `GLIFO_ESCURO` (#111111) são exatamente o
par com que esta janela desenha peça branca e peça preta -- declarar um par novo seria a segunda
declaração da mesma ideia, e a que ninguém lembraria de trocar junto.

O empate fica em `DISPENSADO` (#9aa1ad), que é o **único cinza neutro estável das duas peles**: as
luminâncias saem 0,939 / 0,354 / 0,006, ordenadas e separadas. `TEXTO_SECUNDARIO` foi medido e
recusado -- ele é #555555 na pele clara e #a7adb6 na escura, e na clara o segmento do empate ficaria
mais escuro que o das pretas."""


CONTORNO_DA_BARRA = tokens.TEXTO_SECUNDARIO
"""A linha de um pixel em volta da barra. **Ela existe porque o segmento das brancas é branco.**

Medido na foto de 1400×950 (2026-09-05): `GLIFO_CLARO` (#f8f8f8) sobre a linha clara da tabela
não tem borda -- a fatia das brancas some no fundo, e a barra parece começar onde o cinza começa,
o que lê a proporção errada. O Lichess não precisa disso porque a barra dele tem margem colorida
em volta; aqui a célula é da tabela.

`TEXTO_SECUNDARIO` e não `MOLDURA`: ele é o único cinza que **muda com a pele** (#555555 na clara,
#a7adb6 na escura), e é o que faz o contorno aparecer nas duas -- na escura, um contorno quase
preto sobre fundo quase preto seria o mesmo defeito ao contrário."""

TINTAS_DA_BARRA: tuple[str, str, str] = (tokens.GLIFO_ESCURO, tokens.GLIFO_ESCURO, tokens.GLIFO_CLARO)
"""Com que tinta o número é escrito **dentro** de cada segmento de `CORES_DA_BARRA`.

Declarado e não calculado no widget, pela razão de `CORES_DA_BARRA`: qual tinta cai sobre qual
fundo é a mesma pergunta que a paleta responde em todo lugar, e resolvê-la na hora de pintar
poria a régua de contraste dentro de um `paint()`. As razões medidas contra a régua da S-146:
#111111 sobre #f8f8f8 dá 17,78:1, #111111 sobre #9aa1ad dá 7,26:1 e #f8f8f8 sobre #111111 dá
17,78:1 -- as três acima do piso de 4,5 de `tokens.AA_TEXTO`, e é isso que o teste afirma."""


class Ramo(Protocol):
    """O que `linhas` precisa saber de um ramo -- os atributos de `arvore_de_aberturas.Ramo`.

    `Protocol` e não o tipo concreto pela razão de `busca_de_partidas._Achado`: o que a tabela lê
    são doze atributos, e quem os tiver serve -- o teste passa um objeto montado à mão, sem
    construir SQLite nenhum para afirmar que uma percentagem sai com travessão.
    """

    @property
    def lance(self) -> str: ...
    @property
    def partidas(self) -> int: ...
    @property
    def brancas(self) -> int: ...
    @property
    def empates(self) -> int: ...
    @property
    def pretas(self) -> int: ...
    @property
    def decididas(self) -> int: ...
    @property
    def soma_elo(self) -> int: ...
    @property
    def com_elo(self) -> int: ...
    @property
    def soma_ano(self) -> int: ...
    @property
    def com_ano(self) -> int: ...
    @property
    def ano_min(self) -> int: ...
    @property
    def ano_max(self) -> int: ...


class Resposta(Protocol):
    """O que `linhas` e `resumo` leem de `arvore_de_aberturas.Arvore`. Ver `Ramo`."""

    @property
    def estado(self) -> str: ...
    @property
    def ramos(self) -> tuple[Ramo, ...]: ...
    @property
    def profundidade(self) -> int: ...
    @property
    def ply(self) -> int: ...
    @property
    def partidas(self) -> int: ...


@dataclass(frozen=True)
class Linha:
    """Um lance da árvore, pronto para a tabela: as células, a barra e o lance que o clique joga.

    **As três coisas viajam juntas de propósito.** O widget desenha as células, pinta a barra e
    joga o lance -- e as três respondem sobre a *mesma* linha. Devolver só as células obrigaria o
    painel a reencontrar o ramo pela altura na tela, que é exatamente o defeito que
    `qt/tabela.posicao_de` existe para impedir depois que a ordenação pelo cabeçalho entrou.
    """

    lance: str
    celulas: tuple[str, ...]
    fracoes: tuple[float, float, float] = (0.0, 0.0, 0.0)
    """Brancas, empate e pretas como frações de 0 a 1. **Zeros quer dizer "não desenhe a barra"**
    -- é o caso de `MINIMO_PARA_PERCENTUAL`, e o do ramo em que toda partida ficou em `*`."""


def _percentagens(ramo: Ramo) -> tuple[int, int, int] | None:
    """As três percentagens inteiras, somando 100; ou `None` quando não há amostra que as sustente.

    **O empate leva o resto da divisão**, e não cada um o seu arredondamento: três `round()`
    independentes somam 99 ou 101 numa linha em cada três, e uma barra de resultado que soma 101%
    é o tipo de erro que faz a pessoa parar de confiar na tabela inteira. O empate é o que menos
    se lê dos três, e é ele que absorve.
    """
    decididas = ramo.decididas
    if decididas < MINIMO_PARA_PERCENTUAL:
        return None
    brancas = round(100 * ramo.brancas / decididas)
    pretas = round(100 * ramo.pretas / decididas)
    return brancas, 100 - brancas - pretas, pretas


def _celula_de_resultado(percentagens: tuple[int, int, int] | None) -> str:
    """`48% · 32% · 20%`, ou o travessão. É o texto que a barra tem por baixo.

    Existe mesmo com a barra desenhada, e não é redundância: a barra dá a proporção de relance e
    não dá o número, e é o número que se copia para uma anotação. Ela também é o que sobra quando
    a célula é lida pela dica ou por um leitor de tela.
    """
    if percentagens is None:
        return _TRACO
    return _SEPARADOR.join(f"{parte}%" for parte in percentagens)


def _celula_de_partidas(ramo: Ramo, total: int) -> str:
    """`8609 · 31%`: quantas partidas jogaram este lance, e que fatia do nó elas são.

    A fatia é o que separa a linha principal da curiosidade -- e ela **não** é a percentagem de
    vitória: são duas percentagens diferentes na mesma tabela, e por isso a de frequência mora na
    coluna do número que ela divide, e não numa coluna própria ao lado da outra.

    Sem separador de milhar: ver `COLUNAS`.
    """
    if total <= 0:
        return str(ramo.partidas)
    return f"{ramo.partidas}{_SEPARADOR}{round(100 * ramo.partidas / total)}%"


def _celula_de_elo(ramo: Ramo) -> str:
    """A média dos Elos médios das partidas que **têm** os dois Elos, ou travessão.

    O denominador é `com_elo` e não `partidas`: dividir pela contagem cheia diluiria o rating com
    as partidas antigas que não trazem Elo nenhum, e o número sairia baixo e plausível.
    """
    return str(round(ramo.soma_elo / ramo.com_elo)) if ramo.com_elo else _TRACO


def _celula_de_ano(ramo: Ramo) -> str:
    """`2005 (1857–2026)`: o ano médio e a faixa. Um só número quando os extremos coincidem.

    **Os dois, e não um dos dois.** A média sozinha diz *quando esta linha foi jogada*, e é o que
    se compara entre dois lances irmãos; a faixa diz se ela é uma linha antiga que ninguém joga
    mais ou uma que apareceu ano passado -- e duas linhas com a mesma média podem ser essas duas
    coisas. Cabe numa célula porque o primeiro número é o que a coluna ordena (ver `COLUNAS`).
    """
    if not ramo.com_ano:
        return _TRACO
    medio = round(ramo.soma_ano / ramo.com_ano)
    if ramo.ano_min == ramo.ano_max:
        return str(medio)
    return f"{medio} ({ramo.ano_min}–{ramo.ano_max})"


def _abertura(tabuleiro: chess.Board, lance: chess.Move) -> str:
    """O nome da linha que este lance abre, ou vazio quando a tabela ECO não a conhece.

    Vazio e não travessão: uma posição fora do livro de aberturas não é um dado faltando -- é o
    fim do livro, e a coluna em branco é como o ChessBase o escreve.
    """
    tabuleiro.push(lance)
    try:
        abertura = eco_mod.classificar(tabuleiro)
    finally:
        tabuleiro.pop()
    return "" if abertura is None else eco_mod.frase_da_abertura(abertura)


def linhas(resposta: Resposta, tabuleiro: chess.Board) -> tuple[Linha, ...]:
    """Os ramos como linhas de tabela, do mais jogado para o menos.

    **O tabuleiro entra por dois motivos, e nenhum é desenho**: ele diz se o SAN do ramo é legal
    aqui -- a guarda de colisão do cabeçalho -- e é dele que sai o nome da abertura que cada lance
    abre. Ele volta como estava: `_abertura` empilha e desempilha.

    Ramo sem lance legal é **descartado em silêncio**, e não vira linha com aviso: quem lê a
    árvore não tem o que fazer com "esta linha veio de outra posição", e a alternativa -- mostrar
    a estatística de outra posição -- é a que este projeto não faz. Quem conta os descartados é
    `resumo`, que diz "13 de 14 lance(s)" quando eles existem.
    """
    if resposta.estado != ACHOU:
        return ()
    total = resposta.partidas
    saida: list[Linha] = []
    for ramo in sorted(resposta.ramos, key=lambda item: (-item.partidas, item.lance)):
        try:
            lance = tabuleiro.parse_san(ramo.lance)
        except (ValueError, AssertionError):
            continue
        percentagens = _percentagens(ramo)
        fracoes = (
            (0.0, 0.0, 0.0)
            if percentagens is None
            else (percentagens[0] / 100, percentagens[1] / 100, percentagens[2] / 100)
        )
        saida.append(
            Linha(
                lance=ramo.lance,
                celulas=(
                    ramo.lance,
                    _celula_de_partidas(ramo, total),
                    _celula_de_resultado(percentagens),
                    _celula_de_elo(ramo),
                    _celula_de_ano(ramo),
                    _abertura(tabuleiro, lance),
                ),
                fracoes=fracoes,
            )
        )
    return tuple(saida)


def e_aviso(resposta: Resposta) -> bool:
    """A frase de baixo é um estado com saída, e não um resultado. Pinta em cor de atenção.

    Só `SEM_ARVORE` é: ela traz o comando que constrói o arquivo, e é a única das quatro que a
    pessoa pode resolver. "Fundo demais" e "nenhuma partida" são respostas da base -- pintá-las de
    vermelho ensinaria a ler resposta como defeito.
    """
    return resposta.estado == SEM_ARVORE


def resumo(resposta: Resposta, mostrados: int = 0) -> str:
    """A linha sob a tabela: quantas partidas seguem daqui -- ou **de que estado ela está vazia**.

    São quatro frases e não uma, e a distinção é a da S-135 que `estudo_partidas` já escreveu em
    quatro estados: *"nenhum lance foi jogado daqui"* sobre uma posição que ninguém indexou é um
    número enganoso, e é a resposta que a árvore daria em dois dos quatro casos se eles fossem um.

    `mostrados` é o que sobrou depois da guarda de legalidade, e ele só aparece **quando difere**
    do número de ramos: dizer "17 de 17 lances" toda vez ensina a ignorar a frase, e é justamente
    nela que a diferença precisa aparecer.
    """
    if resposta.estado == SEM_ARVORE:
        return (
            "A árvore de aberturas ainda não foi construída para esta base. Ela reproduz os "
            "primeiros lances da base inteira de uma vez -- por isso é um comando e não um "
            f"botão:  {COMO_CONSTRUIR}"
        )
    if resposta.estado == FUNDO_DEMAIS:
        return (
            f"A árvore vai até o lance {resposta.profundidade // 2} e esta posição está no "
            f"{resposta.ply // 2 + 1}. Daqui em diante quase toda posição da base tem uma partida "
            "só, e quem responde por ela é a busca de partidas."
        )
    if resposta.estado == SEM_PARTIDA:
        # **A frase diz "nos N primeiros lances", e não "nenhuma partida"**, e a diferença é o caso
        # mais comum deste programa: um diagrama de livro chega à sala sem o número do lance, e o
        # tabuleiro parte do lance 1. A árvore procuraria uma posição de meio de jogo na abertura e
        # não a acharia -- e "nenhuma partida da base joga daqui" seria falso sobre uma base que
        # pode ter centenas. Dizer até onde ela olhou é o que separa as duas coisas.
        return (
            f"Nenhuma partida da base joga a partir desta posição nos {resposta.profundidade // 2} "
            "primeiros lances, que é tudo o que a árvore conhece. Uma posição de meio de jogo fica "
            "fora dela mesmo quando a base a tem: quem responde por ela é a busca de partidas."
        )
    partidas = f"{resposta.partidas:,}".replace(",", ".")
    lances = (
        f"{mostrados} lance(s)"
        if mostrados == len(resposta.ramos)
        else f"{mostrados} de {len(resposta.ramos)} lance(s)"
    )
    return _SEPARADOR.join(
        (
            f"{partidas} partida(s) seguem daqui",
            lances,
            f"árvore até o lance {resposta.profundidade // 2}",
        )
    )


class Passada(Protocol):
    """O que `frase_do_fim` lê de `arvore_de_aberturas.Construcao`. Ver `Ramo`."""

    @property
    def partidas(self) -> int: ...
    @property
    def ramos(self) -> int: ...
    @property
    def profundidade(self) -> int: ...
    @property
    def segundos(self) -> float: ...
    @property
    def bytes_no_disco(self) -> int: ...
    @property
    def cancelada(self) -> bool: ...


def frase_da_construcao(prontos: int, total: int, partidas: int) -> str:
    """O rótulo da barra enquanto a árvore é construída.

    **Ela conta pedaços e partidas, e não bytes**, ao contrário de `indice_da_base`: a passada
    reparte o arquivo entre processos, e cada um só se sabe pronto quando acaba -- perguntar a um
    filho quantos bytes ele já leu exigiria um canal a mais para responder a uma barra. As
    partidas somadas são o que anda **dentro** de um pedaço, e é o que mostra que ela não travou.
    """
    if total <= 0:
        return "Repartindo a base entre os processos…"
    contagem = f"{partidas:,}".replace(",", ".")
    return f"Lendo a base: pedaço {prontos} de {total} · {contagem} partidas"


def frase_do_fim(passada: Passada) -> str:
    """O que o rodapé diz quando a passada acaba -- **com o que ela custou**.

    O tamanho e o tempo entram na frase porque são a resposta à pergunta que a pessoa fez ao
    clicar ("quanto isto vai custar?"), e ela só a tem depois. Cancelada, a frase diz que **nada**
    ficou: é a decisão de `arvore_de_aberturas.Construcao`, e escondê-la faria a pessoa procurar
    um arquivo que não existe.
    """
    if passada.cancelada:
        return (
            "Árvore de aberturas interrompida: nada foi gravado. Uma passada que não viu a base "
            "inteira daria percentagem sobre a parte que leu, e ela pareceria certa."
        )
    ramos = f"{passada.ramos:,}".replace(",", ".")
    partidas = f"{passada.partidas:,}".replace(",", ".")
    return (
        f"Árvore de aberturas pronta: {ramos} lance(s) de {partidas} partida(s), "
        f"até o lance {passada.profundidade // 2}, em {passada.segundos / 60:.0f} min "
        f"e {passada.bytes_no_disco / 1e6:.0f} MB."
    )


def perde_trabalho_ao_fechar() -> bool:
    """Fechar a janela no meio da passada **perde** o que ela já leu (S-535). É o oposto do índice.

    `indice_da_base.perde_trabalho_ao_fechar` responde falso, e a diferença entre os dois é o que
    torna as duas respostas honestas: lá cada arquivo é uma transação e a rodada seguinte continua
    de onde parou; aqui cada linha é uma **soma**, e uma passada interrompida não tem como ser
    retomada sem contar duas vezes as partidas que já entraram -- então ela é descartada inteira
    (ver `arvore_de_aberturas.Construcao`).

    Dizer "não perde" sobre isto treinaria a pessoa a fechar a janela na décima nona hora... e o
    contrário -- dizer "perde" sobre o índice, que retoma -- treinaria a ignorar o aviso quando
    ele for verdade. É a mesma régua da S-112, e ela só vale enquanto os dois lados forem exatos.
    """
    return True


def busca_da_posicao(colocacao: str, codigo_eco: str) -> Filtro:
    """O filtro que abre a lista das partidas que chegaram a esta posição (S-533 + S-535).

    **A posição sozinha não busca**, e é decisão da S-533: ela não tem árvore no índice, e é
    conferida relendo cada candidata que os outros filtros deixaram passar. O que estreita aqui é
    o **código ECO da própria posição** -- que a árvore já calcula para a coluna Abertura, e que é
    a única coisa que se sabe sobre a posição sem ler partida nenhuma.

    Sem código (uma posição fora do livro de aberturas) o filtro sai só com a posição, e o
    formulário recusa a busca dizendo o que falta -- que é melhor que varrer dez milhões de linhas
    para devolver as cem partidas mais recentes da base.
    """
    return Filtro(eco_de=codigo_eco, eco_ate=codigo_eco, posicao=colocacao)
