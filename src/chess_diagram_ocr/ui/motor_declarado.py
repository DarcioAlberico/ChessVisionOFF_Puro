"""O motor como a sala o declara: as opções que se pode mudar e o que o painel dele mostra (S-529/S-536).

**Duas perguntas, e as duas são decisão e não desenho.**

1. *O que se pode pedir ao motor, e até quanto* (S-536). `Hash`, `Threads` e `MultiPV` são opções
   do protocolo UCI, e cada uma tem um teto que **não** é de gosto: pedir mais tabela de transposição
   do que a máquina tem de memória faz o sistema paginar e o motor ficar mais lento do que com um
   quarto dela; pedir mais threads do que há núcleos faz o Stockfish disputar consigo mesmo. Os
   tetos saem dos números da máquina, que entram por argumento -- quem os lê é `qt/preferencias.py`,
   e a régua é afirmável sem máquina nenhuma.

2. *O que a barra de avaliação e as linhas do motor mostram* (S-529). A altura da faixa branca, a
   cor de um mate anunciado e a numeração das linhas MultiPV. Nada disso depende de `QPainter`.

**A curva da barra não é escrita aqui, e isso é o item.** Ela já existe:
`engine.Evaluation.advantage_fraction`, logística de base 10 sobre 400 centipeões -- a curva de
expectativa de pontuação do Elo. Uma segunda curva escrita neste módulo daria uma barra que
discorda do número escrito ao lado dela no dia em que uma das duas mudasse. O que este módulo
acrescenta é o que a fração vira em pixel, e o que acontece quando há mate.

**A grade de comparação com o Lichess, medida em 2026-09-04.** A barra do Lichess usa
`2/(1+e^(-0,00368208·cp)) - 1`; a daqui, `1/(1+10^(-cp/400))`. Em fração da barra:

| centipeões | daqui | Lichess |
|---|---|---|
| 0 | 0,500 | 0,500 |
| 50 | 0,571 | 0,546 |
| 100 | 0,640 | 0,591 |
| 200 | 0,760 | 0,676 |
| 300 | 0,849 | 0,751 |
| 500 | 0,947 | 0,863 |
| 1000 | 0,997 | 0,975 |

A daqui é mais íngreme no miolo e satura antes. **A diferença é a decisão**: numa sala de estudo o
que se lê a metro de distância é *de quem é a posição*, e a curva do Elo responde isso -- ela é
literalmente a probabilidade de ganhar aquele final. A do Lichess reserva mais barra para o que
acontece acima de +5, que é a faixa em que a partida já acabou.

Nada de `PyQt6`: quem monta widget não decide.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..engine import fracao_de_vantagem
from ..settings import EngineSettings
from . import tokens

__all__ = [
    "HASH",
    "LARGURA_DA_BARRA",
    "MOVETIME",
    "MULTIPV",
    "OPCOES",
    "PAPEL_DE_BRANCAS",
    "PAPEL_DE_PRETAS",
    "THREADS",
    "TITULO",
    "altura_de_brancas",
    "espessura_da_moldura",
    "frase_de_desempenho",
    "frase_de_motor_que_nao_responde",
    "linhas_do_motor",
    "opcao",
    "papel_da_moldura",
    "papel_do_lado",
    "plano_de_aplicacao",
    "rotulo_da_barra",
    "teto_de",
    "titulo_da_secao",
    "validar",
    "validar_caminho",
    "validar_pasta_de_tablebase",
]

TITULO = "Motor de análise"
"""O nome da seção nas preferências e o título do diálogo. Um texto, um lugar."""

# ------------------------------------------------------------------------ as opções (S-536)

HASH = "hash_mb"
THREADS = "threads"
MULTIPV = "multipv"
MOVETIME = "movetime_ms"
"""As quatro chaves, e elas são os nomes dos campos de `settings.EngineSettings`.

Serem os nomes dos campos é o que permite a `plano_de_aplicacao` e ao diálogo lerem e escreverem
por `getattr`/`replace` em vez de repetirem uma tabela `campo -> widget` que envelhece sozinha."""

_TETO_DE_MULTIPV = 10
"""O Stockfish aceita 500 linhas. Dez é o teto do que se **lê**: a S-286 mediu que a quarta e a
quinta de um motor a 800 ms já são ruído, e o painel mostra três de fábrica. O teto existe para o
final de sete peças, em que as dez primeiras podem ser todas iguais e isso é a informação."""

_TETO_DE_HASH = 32768
"""32 GB. Acima disto a tabela deixa de caber no que uma máquina de estudo tem, e o teto real passa
a ser a memória -- ver `teto_de`. Existe para o dia em que `memoria_mb` venha absurdo."""

_PISO_DE_HASH = 16
"""O padrão do próprio Stockfish, e o piso aqui. Abaixo disso a tabela de transposição não guarda
uma árvore de meio-jogo inteira e a profundidade cai sem que ninguém entenda por quê."""

_TETO_DE_MOVETIME = 60_000
"""Um minuto por posição. Acima disto a análise contínua deixa de acompanhar quem navega, que é o
que ela existe para fazer."""


@dataclass(frozen=True)
class _Opcao:
    """Uma opção do motor: o campo das preferências, o nome UCI e como ela se lê na tela."""

    chave: str
    uci: str
    """O nome no protocolo. Vazio para o que **não** é opção do motor -- `movetime_ms` é um limite
    que vai em cada `go`, e `multipv` é argumento de `analyse`."""

    rotulo: str
    unidade: str = ""
    piso: int = 1
    dica: str = ""

    @property
    def do_processo(self) -> bool:
        """Muda o processo por `setoption`? É o que separa "sem reiniciar" de "por chamada"."""
        return bool(self.uci)


OPCOES: tuple[_Opcao, ...] = (
    _Opcao(
        HASH,
        "Hash",
        "Tabela de transposição",
        unidade="MB",
        piso=_PISO_DE_HASH,
        dica="Quanto o motor guarda de posições já calculadas. O teto é metade da memória desta\n"
        "máquina: acima disso o sistema recorre ao disco, e o motor fica mais lento do que com um quarto dela.",
    ),
    _Opcao(
        THREADS,
        "Threads",
        "Núcleos",
        piso=1,
        dica="Quantos núcleos o motor usa. O teto é o número de núcleos desta máquina: pedir mais\n"
        "faz o motor disputar consigo mesmo, e a profundidade cai.",
    ),
    _Opcao(
        MULTIPV,
        "",
        "Linhas do motor",
        piso=1,
        dica="Quantas variantes candidatas o painel mostra. Não é opção do processo: entra em cada\n"
        "análise, então mudá-la vale já na próxima -- sem derrubar o motor.",
    ),
    _Opcao(
        MOVETIME,
        "",
        "Tempo por posição",
        unidade="ms",
        piso=50,
        dica="Teto de quanto o motor pensa em cada posição. Numa posição simples ele responde antes.",
    ),
)
"""As quatro que as preferências oferecem, na ordem em que o diálogo as desenha.

**Duas são do processo e duas não são**, e é a distinção que faz o "sem reiniciar" da S-536 ser
verdade em vez de promessa: `Hash` e `Threads` são `setoption` sobre o motor aberto; `MultiPV` e o
tempo por posição são argumentos de cada análise, e mudar qualquer um deles já vale na próxima
resposta sem que uma linha de processo seja tocada."""

_POR_CHAVE: dict[str, _Opcao] = {registro.chave: registro for registro in OPCOES}


def opcao(chave: str) -> _Opcao:
    """O registro daquela opção. Levanta `KeyError` para chave que as preferências não têm."""
    if chave not in _POR_CHAVE:
        raise KeyError(f"opção de motor desconhecida: {chave!r}. As que existem: {list(_POR_CHAVE)}.")
    return _POR_CHAVE[chave]


def _potencia_de_dois_ate(valor: int) -> int:
    """A maior potência de dois que não passa de `valor`, com piso em 1.

    O Stockfish reparte a tabela em posições por potência de dois e **arredonda para baixo** o que
    receber: pedir 3000 MB gasta 2048 e joga fora 952. Oferecer o teto já arredondado é oferecer o
    que a máquina de fato vai usar.
    """
    potencia = 1
    while potencia * 2 <= max(1, int(valor)):
        potencia *= 2
    return potencia


def teto_de(chave: str, *, memoria_mb: int, nucleos: int) -> int:
    """O maior valor são para aquela opção nesta máquina. Puro: os números entram por argumento.

    **Hash é metade da memória, arredondada para baixo à potência de dois.** Metade e não tudo
    porque o resto da máquina existe -- o próprio programa, o PDF aberto, o sistema --, e uma
    tabela que force paginação é mais lenta do que uma tabela pequena: o motor passa a esperar o
    disco em vez de a CPU. Potência de dois porque é o que o Stockfish usa de fato.

    **Threads é o número de núcleos.** Não `núcleos - 1`: quem analisa uma partida inteira quer a
    máquina toda, e a janela continua respondendo porque a análise não roda na linha de eventos.
    Acima do número de núcleos o ganho é negativo, e é aí que o teto morde.
    """
    registro = opcao(chave)
    if registro.chave == HASH:
        return max(registro.piso, min(_TETO_DE_HASH, _potencia_de_dois_ate(max(0, int(memoria_mb)) // 2)))
    if registro.chave == THREADS:
        return max(1, int(nucleos))
    if registro.chave == MULTIPV:
        return _TETO_DE_MULTIPV
    return _TETO_DE_MOVETIME


def validar(chave: str, valor: object, *, memoria_mb: int, nucleos: int) -> str:
    """Por que aquele valor não serve, em pt-BR. Vazio quando serve.

    A frase diz **o intervalo** e não só "inválido": quem digitou 8 em Hash precisa saber que o
    piso é 16 e por quê, e quem digitou 64 threads numa máquina de 8 núcleos precisa ver o 8.
    """
    registro = opcao(chave)
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return f"{registro.rotulo}: informe um número inteiro."
    teto = teto_de(chave, memoria_mb=memoria_mb, nucleos=nucleos)
    if numero < registro.piso:
        return f"{registro.rotulo}: o mínimo é {registro.piso}{_sufixo(registro)}."
    if numero > teto:
        return f"{registro.rotulo}: o máximo nesta máquina é {teto}{_sufixo(registro)}."
    return ""


def _sufixo(registro: _Opcao) -> str:
    return f" {registro.unidade}" if registro.unidade else ""


def validar_caminho(texto: str) -> str:
    """Por que aquele caminho de binário não serve. Vazio serve: é "procure sozinho" (S-33)."""
    limpo = str(texto or "").strip().strip('"')
    if not limpo:
        return ""
    caminho = Path(limpo)
    if caminho.is_dir():
        return "O caminho do motor aponta para uma pasta. Informe o arquivo do executável."
    if not caminho.exists():
        return f"Não há arquivo em {caminho}."
    return ""


def validar_pasta_de_tablebase(texto: str) -> str:
    """Por que aquela pasta de tablebases não serve. Vazio serve: é "não usar tablebase" (S-538)."""
    limpo = str(texto or "").strip().strip('"')
    if not limpo:
        return ""
    caminho = Path(limpo)
    if caminho.is_file():
        return "A pasta de tablebases aponta para um arquivo. Informe a pasta que contém os .rtbw."
    if not caminho.exists():
        return f"Não há pasta em {caminho}."
    return ""


# ------------------------------------------------ o que muda sem derrubar o processo (S-536)


@dataclass(frozen=True)
class _Plano:
    """O que fazer com o motor aberto para que ele passe a obedecer às preferências novas."""

    trocar_processo: bool
    do_processo: dict[str, int | str] = field(default_factory=dict)
    """`nome UCI -> valor`, para o `setoption` sobre o motor **vivo**. Vazio quando nada mudou."""

    por_analise: dict[str, int] = field(default_factory=dict)
    """`chave -> valor` do que entra em cada chamada: `multipv` e `movetime_ms`."""

    @property
    def mudou(self) -> bool:
        return self.trocar_processo or bool(self.do_processo) or bool(self.por_analise)

    def frase(self) -> str:
        """O que dizer no rodapé depois de aplicar. Nomeia o que aconteceu com o processo."""
        if self.trocar_processo:
            return "Motor trocado: o processo anterior foi encerrado e o novo já responde."
        if not self.mudou:
            return "As opções do motor não mudaram."
        quantas = len(self.do_processo) + len(self.por_analise)
        return f"{quantas} opção(ões) do motor aplicada(s) sem derrubar o processo."


def plano_de_aplicacao(antes: EngineSettings, depois: EngineSettings) -> _Plano:
    """O que separa "derrubar e subir outro" de "mandar `setoption`" (S-536).

    **Só o caminho do binário derruba o processo.** Um processo UCI é um programa em execução com
    uma tabela de transposição dentro; trocar `Hash` ou `Threads` nele é uma linha de texto no
    `stdin` -- `setoption name Hash value 512` --, e o Stockfish realoca a tabela sozinho. Fechar e
    reabrir para isso custaria os 100 a 300 ms de inicialização que a S-33 já registrou, e perderia
    a análise em curso.

    **Trocar o binário não tem esse caminho**: o processo que está aberto é o motor antigo, e a
    única forma de falar com outro é abrir outro. Daí o `trocar_processo`, e daí a fiação de
    `qt/preferencias.MotorVivo` fazer isso numa thread -- fechar um motor que está pensando espera
    ele responder, e a janela não pode esperar junto.

    **A pasta de tablebases é do processo** (S-538): `SyzygyPath` é opção UCI do Stockfish, e
    apontá-la faz o próprio motor dar avaliação exata nos finais que ela cobre. É `setoption`
    como as outras.
    """
    trocar = _normalizado(antes.path) != _normalizado(depois.path)
    do_processo: dict[str, int | str] = {}
    por_analise: dict[str, int] = {}
    for registro in OPCOES:
        velho = getattr(antes, registro.chave)
        novo = getattr(depois, registro.chave)
        if velho == novo:
            continue
        if registro.do_processo:
            do_processo[registro.uci] = int(novo)
        else:
            por_analise[registro.chave] = int(novo)
    if _normalizado(antes.syzygy_path) != _normalizado(depois.syzygy_path):
        do_processo["SyzygyPath"] = str(depois.syzygy_path or "")
    if trocar:
        # O motor novo nasce com tudo: mandar `setoption` para um processo que vai morrer seria
        # configurar quem está de saída, e deixaria o que entra com os padrões de fábrica.
        return _Plano(trocar_processo=True)
    return _Plano(trocar_processo=False, do_processo=do_processo, por_analise=por_analise)


def _normalizado(caminho: str) -> str:
    """Dois jeitos de escrever o mesmo caminho não são duas trocas de motor.

    Aspas em volta (o que o Windows põe ao "copiar como caminho"), espaço nas pontas e a barra
    invertida contra a normal -- nenhum deles muda qual binário é. Sem isto, reabrir o diálogo e
    confirmar sem mexer em nada derrubaria o processo.
    """
    return str(caminho or "").strip().strip('"').replace("\\", "/").rstrip("/").casefold()


# ------------------------------------------------------- a barra de avaliação (S-529)

LARGURA_DA_BARRA = 26
"""Largura da barra vertical, em pixel. Vinte e seis porque é o que o **número** precisa (S-529).

Ela nasceu com 18, que é a do Lichess, e o crítico mediu o que isso fazia com o rótulo: em
Consolas 7pt -- a fonte de dado desta janela, dois pontos menor --, `12,34` ocupa **25 px** e
`-12,34` ocupa **30**. Com 18 px o número saía cortado no meio (`-12,34` virava `12`), o que é
pior que não escrevê-lo: um `12` sem sinal e sem casas decimais afirma outra avaliação.

Vinte e seis é `25 + 1` de folga, e é o **menor** número que deixa a maior avaliação plausível
caber inteira. O custo é medido e é de oito pixels de tabuleiro; ver `rotulo_da_barra` para a
outra metade da conta -- o sinal sai do texto porque a **posição** do número já o diz, e é o que
faz 26 bastar onde 32 seriam precisos."""

PAPEL_DE_BRANCAS = tokens.GLIFO_CLARO
PAPEL_DE_PRETAS = tokens.GLIFO_ESCURO
"""As duas faixas da barra saem da tinta das **peças**, e não do tema (S-529).

Elas não seguem pele pela mesma razão que as casas não seguem: a barra diz de quem é a posição, e
uma faixa "das brancas" que escurecesse junto com a janela deixaria de dizer isso. É o mesmo
argumento que `tokens.GLIFO_CLARO` já carrega para a peça desenhada."""

PAPEL_DE_MATE = tokens.ATENCAO
"""Mate anunciado é o **fio** em âmbar, e não a faixa (S-529, segunda rodada).

**A primeira redação pintava de âmbar a faixa de quem mateia, e ela não dizia quem mateia.** Numa
posição de mate a barra está cheia por construção (`fracao_de_vantagem` devolve 1 ou 0), então a
faixa de quem mateia é a barra inteira: `M3` e `-M3` saíam os dois como um retângulo âmbar de ponta
a ponta. Medido em pixel pelo crítico: **zero** pixels de diferença entre os dois desenhos.

Agora a faixa cheia é da cor **do lado** -- branca em cima de `M3`, preta em cima de `-M3`, que é a
diferença que se lê a metro de distância -- e o âmbar é o fio em volta, com o dobro da espessura.
Ele continua sendo o que separa "está ganho" de "acaba em três lances", que era a decisão certa;
o que mudou é onde ele é pintado, porque a faixa já estava ocupada dizendo outra coisa."""


def papel_do_lado(*, brancas: bool) -> str:
    """A cor da faixa daquele lado. Só isso: quem diz "mate" é a moldura (ver `PAPEL_DE_MATE`)."""
    return PAPEL_DE_BRANCAS if brancas else PAPEL_DE_PRETAS


def papel_da_moldura(*, mate: bool = False, cromo_escuro: bool = False) -> str:
    """O fio em volta da barra. **Ele muda com a pele, e a razão é contraste medido** (S-529).

    `tokens.MOLDURA` é uma superfície: ela escurece junto com o cromo. Na pele Foco isso dava
    `#1f1d1b` sobre um fundo `#1f2124` -- **1,04:1** --, e a faixa preta da barra (`#111111`) dava
    **1,17:1** contra o mesmo fundo. As duas somem: a barra inteira desaparecia da janela escura,
    e o que restava era a faixa branca flutuando sem contorno. O piso do projeto para objeto
    gráfico é 3:1.

    O fio passa a ser a tinta da peça **oposta ao fundo**: `MOLDURA` (14,74:1) na pele clara e
    `GLIFO_CLARO` (15,20:1) na escura. Ele não precisa contrastar com as duas faixas -- a faixa da
    cor dele encosta no fundo, que é justamente onde ela é visível sozinha --, precisa contrastar
    com o **fundo**, que é o que faz a barra existir como objeto.

    Mate troca o fio pelo âmbar (5,20:1 na pele clara, 5,09:1 na escura), e aí ele é o que diz que
    há mate anunciado.
    """
    if mate:
        return PAPEL_DE_MATE
    return tokens.GLIFO_CLARO if cromo_escuro else tokens.MOLDURA


def espessura_da_moldura(*, mate: bool = False) -> int:
    """Quantos pixels de fio. Dois no mate, um no resto.

    Dobrar a espessura é o que impede o âmbar de virar detalhe numa barra de 26 px: um pixel de
    cor diferente na borda é a diferença que ninguém vê de longe, e "há mate anunciado" é
    justamente o que se quer ver de longe.
    """
    return 2 if mate else 1


def rotulo_da_barra(display: str) -> str:
    """O número como ele vai **dentro** da barra: sem o sinal (S-529, segunda rodada).

    **O sinal é redundante ali e caro.** A barra escreve o número do lado de quem está melhor --
    embaixo com as brancas melhor, em cima com as pretas --, e essa posição já diz de quem é a
    vantagem: é a regra do Lichess, e é a única que faz o número caber num fio de 26 px. Com o
    sinal, `-12,34` pede 30 px e a barra teria de tomar mais oito do tabuleiro para dizer duas
    vezes a mesma coisa.

    `+1,56` -> `1,56`; `-12,34` -> `12,34`; `-M3` -> `M3`; `1-0` e `=` passam inteiros -- eles são
    resultado e não avaliação, e o traço do meio não é sinal.
    """
    texto = str(display or "").strip()
    if texto[:1] in {"+", "-", "−"}:
        return texto[1:]
    return texto


def titulo_da_secao(nome: str, caminho: str = "") -> str:
    """`Motor (Stockfish dev-20230303)`. O nome que o **motor** diz, e não o do arquivo (S-529).

    O título saía `Motor (stockfish.exe)`, que é o nome do executável -- e num computador com dois
    Stockfish de versões diferentes, ou com o binário renomeado, ele não distingue nada. O UCI
    responde `id name` na abertura, e é esse o nome que todo programa de xadrez mostra.

    Sem nome nenhum (motor ainda fechado, ou motor que não se apresentou) o caminho volta a ser a
    resposta, porque um título `Motor ()` seria pior que o nome do arquivo.
    """
    limpo = str(nome or "").strip() or str(caminho or "").strip()
    return f"Motor ({limpo})" if limpo else "Motor"


def frase_de_motor_que_nao_responde(caminho: str) -> str:
    """O que dizer quando o binário abre e **não fala UCI** (S-536, segunda rodada).

    Medido pelo crítico: apontar as preferências para `python.exe` dá dez segundos de espera e
    depois a palavra `TimeoutError`, crua e em inglês -- que é o nome de uma classe do Python, não
    uma frase. Quem viu isso não sabe se errou o caminho, se o motor travou ou se o programa tem
    um defeito.

    A frase nomeia as três coisas que quem lê precisa: **qual** arquivo, **o que** falhou (ele não
    respondeu ao protocolo), e **o que aconteceu com a sala** (ficou sem motor, que é a degradação
    da S-33 e não um erro a mais).
    """
    onde = str(caminho or "").strip()
    alvo = f" em {onde}" if onde else ""
    return (
        f"O programa{alvo} não respondeu ao protocolo UCI em dez segundos. "
        "Ou ele não é um motor de xadrez, ou não conseguiu abrir. A sala segue sem motor."
    )


def altura_de_brancas(fracao: float, altura: int) -> int:
    """Quantos pixels da barra são das brancas, contados **de baixo** (S-529).

    Brancas embaixo é a convenção do Lichess e da ChessBase, e ela não é arbitrária: o tabuleiro
    ao lado tem as brancas embaixo, e uma barra invertida faria o olho ter de traduzir.

    A fração vem de `Evaluation.advantage_fraction`, e o arredondamento é para o inteiro mais
    próximo -- meio pixel de barra não existe, e truncar deslocaria a linha do meio para baixo em
    toda posição equilibrada.
    """
    if altura <= 0:
        return 0
    limpa = min(1.0, max(0.0, float(fracao)))
    return int(round(limpa * altura))


# --------------------------------------------------------- as linhas do motor (S-529)


@dataclass(frozen=True)
class _Linha:
    """Uma linha do MultiPV como a lista a mostra: a avaliação, a variante e a profundidade."""

    indice: int
    display: str
    variante: str
    lances: tuple[str, ...]
    profundidade: int
    fracao: float = 0.5
    """A avaliação como fração de barra, para **ordenar**. Ver `linhas_do_motor`."""

    def texto(self) -> str:
        """`+0,35  12. Ba4 Nf6 13. O-O`. A avaliação primeiro: é por ela que se compara as linhas."""
        return f"{self.display}  {self.variante}".rstrip()


def linhas_do_motor(
    avaliacoes: Sequence[Any] | None, *, numero_do_lance: int = 1, brancas_jogam: bool = True
) -> tuple[_Linha, ...]:
    """As linhas candidatas, numeradas a partir do lance corrente (S-529).

    **A numeração é o item.** O motor devolve `('Ba4', 'Nf6', 'O-O')`, e uma lista assim ao lado de
    uma notação numerada obriga quem lê a contar nos dedos para saber onde a linha começa. Com o
    número, `12. Ba4 Nf6 13. O-O` casa com a linha da lista de lances letra por letra -- que é a
    comparação que quem estuda está fazendo.

    Com as pretas a jogar a primeira reticência aparece (`12... Nf6 13. Nc3`), como no livro.

    Linha sem lance nenhum -- mate ou afogamento -- não vira `_Linha`: não há variante a mostrar, e
    uma linha vazia numerada seria um número apontando para nada.

    **A ordem é a da avaliação, e não a que o motor devolveu** (segunda rodada). O MultiPV do
    Stockfish é ordenado pela busca *da iteração anterior*: com dez linhas e ~900 ms por resposta,
    a última iteração reordena algumas e a lista sai com `-3,09` acima de `-3,04` -- medido pelo
    crítico. Numa lista cuja razão de ser é *comparar candidatos*, a ordem é a informação, e uma
    lista fora de ordem faz quem lê escolher a segunda melhor achando que é a melhor.

    **O índice não é reordenado junto**, e isso é o que faz o clique continuar certo: `indice` é a
    posição na lista que o motor devolveu, que é a mesma que a sala guarda em `_candidatos`. Ele
    não aparece na tela -- serve de âncora --, então reordenar as linhas sem reordenar os índices
    não deixa buraco nenhum visível.
    """
    saida: list[_Linha] = []
    for indice, avaliacao in enumerate(avaliacoes or (), start=1):
        lances = tuple(getattr(avaliacao, "pv_san", ()) or ())
        if not lances:
            continue
        saida.append(
            _Linha(
                indice=indice,
                display=str(avaliacao.display()),
                variante=variante_numerada(lances, numero=numero_do_lance, brancas=brancas_jogam),
                lances=lances,
                profundidade=int(getattr(avaliacao, "depth", 0) or 0),
                fracao=fracao_de_vantagem(
                    getattr(avaliacao, "score_cp", None), getattr(avaliacao, "mate_in", None)
                ),
            )
        )
    saida.sort(key=lambda linha: linha.fracao, reverse=bool(brancas_jogam))
    return tuple(saida)


def variante_numerada(lances: Sequence[str] | None, *, numero: int, brancas: bool) -> str:
    """`('Ba4','Nf6','O-O')` a partir do lance 12 das brancas -> `12. Ba4 Nf6 13. O-O`.

    Separada de `linhas_do_motor` porque a mesma numeração serve à variante que entra na árvore e à
    que só se lê -- e duas cópias dela divergiriam na primeira reticência.
    """
    partes: list[str] = []
    lance = int(numero)
    vez_das_brancas = bool(brancas)
    for posicao, san in enumerate(lances or ()):
        if vez_das_brancas:
            partes.append(f"{lance}.")
        elif posicao == 0:
            partes.append(f"{lance}...")
        partes.append(str(san))
        if not vez_das_brancas:
            lance += 1
        vez_das_brancas = not vez_das_brancas
    return " ".join(partes)


def frase_de_desempenho(*, profundidade: int, nos: int, nos_por_segundo: int) -> str:
    """`profundidade 22 · 1,4 MN/s · 3,1 Mnós`. O que o motor gastou para dizer o que disse.

    **Profundidade sozinha não compara duas máquinas**, e é por isso que os nós entram: 20 plies
    num final são instantâneos e num meio-jogo travado, não -- é o mesmo argumento que fez
    `EngineAnalyzer` limitar por tempo e não por profundidade. Os nós por segundo dizem se o motor
    está usando a máquina que as preferências mandaram usar, que é a única forma de ver da tela
    que `Threads` pegou.
    """
    partes: list[str] = []
    if profundidade:
        partes.append(f"profundidade {int(profundidade)}")
    if nos_por_segundo:
        partes.append(f"{numero_curto(nos_por_segundo)}N/s")
    if nos:
        partes.append(f"{numero_curto(nos)} nós")
    return " · ".join(partes)


def numero_curto(valor: int) -> str:
    """`1400000` -> `1,4 M`; `820000` -> `820 k`. Vírgula decimal, que é o pt-BR.

    **Três algarismos significativos e não uma casa fixa**: `820,0 k` gasta duas colunas para
    dizer o que `820 k` já disse, e a linha de desempenho fica ao lado de outros dois números.
    """
    numero = int(valor)
    for corte, sufixo in ((1_000_000_000, "G"), (1_000_000, "M"), (1_000, "k")):
        if numero >= corte:
            reduzido = numero / corte
            casas = 0 if reduzido >= 100 else 1
            return f"{reduzido:.{casas}f} {sufixo}".replace(".", ",")
    return str(numero)
