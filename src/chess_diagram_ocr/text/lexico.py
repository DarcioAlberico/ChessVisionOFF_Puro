"""O léxico: as listas, a sinalização que nunca troca, e as duas fronteiras de palavra (S-209).

**Este módulo é a S-209, e `dicionario.py` não é.** A diferença está escrita no cabeçalho de lá e
vale repetir de cá, porque é ela que autoriza os dois a existirem:

    lexico.py       o que o dicionário SABE, e o que ele DECIDE sozinho
                    -- a palavra está na lista? junta esta hifenizada? --
    dicionario.py   o que o dicionário DESEMPATA entre os candidatos do modelo
                    -- entre as letras que a rede já pôs no topo, alguma forma palavra? --

Aqui o modelo não aparece: as perguntas são sobre texto e sobre a lista, e nenhuma delas propõe
letra nenhuma.

## A regra que contraria o instinto, e que dá valor ao item

**Palavra fora do dicionário é sinalizada, nunca aproximada da mais parecida.** `Nimzowitsch` não
está em lista alguma, e forçar a troca entregaria prosa limpa e falsa. Medido no projeto de
origem: dos 18 lances tão maltratados que escapam do fatiador e caem no léxico, **nenhum** está no
dicionário -- com correção automática, seriam 18 lances reescritos como palavra.

`sinalizar` é o que este módulo faz com a palavra desconhecida: devolve **onde** ela está e o
**texto idêntico**. Não há uma função aqui que troque palavra por palavra parecida, e a ausência é
a entrega.

## O que o dicionário decide sozinho: as duas fronteiras de palavra

Nas duas ele é o **próprio critério** e não precisa de limiar, e é por isso que só elas são
automáticas:

**Juntar a hifenizada na quebra de linha.** `em-` no fim de uma linha e `barrassment` no começo da
seguinte são uma palavra que a diagramação partiu. A condição é dupla e as duas metades importam:
o pedaço da esquerda termina em hífen, **e** a junção está no léxico enquanto as duas metades
soltas não formam a frase que estava lá. Medido no projeto de origem sobre a verdade: **6 de 6
junções certas, com as 2 que não devem juntar recusadas** -- `Xue-Fierro` é nome composto, e
`Saint-` + `Amant` também.

**Partir a colada.** `ofthe` -> `of` `the`. A régua é a certa -- só parte o que **não** está no
dicionário --, e mesmo assim ela **não entrou**, porque foi medida aqui e não paga. Ver
`PARTIR_COLADAS`.

## As duas listas são dados, e o perfil escolhe entre elas

`nomes.txt.gz` e `idioma.txt.gz` são arquivos, e trocá-los não exige mudar código -- é critério de
aceite do item, e `cvoff-texto-lexico` é quem os empacota. O que a S-209 mediu, e que faz o perfil
existir:

    só o idioma            58,5% de recall, 12,1% de alarme falso
    idioma + nomes         53,8% de recall,  5,8% de alarme falso     *(medido lá)*

**Nome próprio baixa o alarme e esconde erro**, e quem escolhe é quem sabe o perfil do livro. Um
livro de partidas comentadas quer os nomes; um manual de finais, talvez não.
"""

from __future__ import annotations

import gzip
import logging
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from ..config import PROJECT_ROOT

logger = logging.getLogger(__name__)

PASTA_DO_LEXICO = PROJECT_ROOT / "assets" / "lexico"

CAMINHO_ACERVO = PASTA_DO_LEXICO / "acervo.txt.gz"
CAMINHO_IDIOMA = PASTA_DO_LEXICO / "idioma.txt.gz"
CAMINHO_NOMES = PASTA_DO_LEXICO / "nomes.txt.gz"

CAMINHO_PADRAO = CAMINHO_ACERVO
"""O nome antigo do arquivo do acervo, quando ele era o único. Mantido para quem o importa."""

EMPACOTADOS = (CAMINHO_ACERVO, CAMINHO_IDIOMA, CAMINHO_NOMES)
"""Os três arquivos que o perfil `completo` une."""

Perfil = Literal["completo", "sem-nomes", "so-idioma", "so-acervo"]

PERFIS: dict[Perfil, tuple[Path, ...]] = {
    "completo": EMPACOTADOS,
    "sem-nomes": (CAMINHO_ACERVO, CAMINHO_IDIOMA),
    "so-idioma": (CAMINHO_IDIOMA,),
    "so-acervo": (CAMINHO_ACERVO,),
}
"""Que arquivos cada perfil une. **É a forma que o critério de aceite pede**: a escolha é de
dados, e acrescentar uma lista é acrescentar uma linha aqui -- não mexer em quem consulta.

`sem-nomes` é o perfil da medição da S-209: nome próprio baixa o alarme falso de 12,1% para 5,8%
**e esconde erro**. `so-idioma` e `so-acervo` existem para a medição comparar uma lista contra
outra, que é o que `docs/metrics/texto_dicionario.json` faz."""

PERFIL_PADRAO: Perfil = "completo"
"""Medido em 40 páginas de 11 livros: os nomes não mudam um caractere do que sai, e protegem 73
palavras de serem tocadas. Ver o cabeçalho de `dicionario.py`."""

MIN_TAMANHO = 4
"""Menos letras que isto não é palavra: é notação. `Kf`, `Nc` e `Re` estavam no léxico bruto
extraído do acervo até esta régua entrar."""

FRACAO_DE_LETRAS = 0.6
"""Quanto do token tem de ser letra para ele ser candidato a palavra.

**Não pode ser "só letras", e essa foi a primeira coisa que quebrou aqui.** O token que interessa é
justamente o que veio *errado* -- `p/ayer` tem uma barra no meio, e uma régua de só-letras o
rejeita antes de olhar. O que separa palavra de notação não é a pureza: é o dígito e a proporção."""

PONTUACAO_DE_BORDA = ".,;:!?()[]'\""
"""O que se apara das pontas de um token antes de perguntar se ele é palavra.

Uma constante, e não o literal repetido: duas réguas sobre o mesmo token é o defeito que este
projeto persegue nos rótulos e nas tabelas de tecla."""

PALAVRA = re.compile(r"^[A-Za-zÀ-ÿ]+(?:['’-][A-Za-zÀ-ÿ]+)*$")

_TOKEN = re.compile(r"[^\s]+")
r"""O que se separa por espaço. **Não** é `\w+`: `Black's` e `Saint-Amant` são um token só."""


@lru_cache(maxsize=8)
def carregar(
    perfil: Perfil = PERFIL_PADRAO,
    *,
    caminho: Path | None = None,
) -> frozenset[str]:
    """As palavras do léxico, dobradas para minúscula. Vazio quando não há arquivo nenhum.

    Sem argumento é o perfil `completo` -- acervo, idioma e nomes unidos. `caminho` lê **aquele
    arquivo e só ele**, que é como a medição compara uma lista contra outra.

    **Ausente não é erro**, e é a mesma regra dos outros recursos opcionais deste projeto: sem
    léxico quem consulta devolve o que o modelo leu, que é o que ele sempre fez. Um clone limpo
    não reconstrói os `.txt.gz` -- as listas de origem não são versionadas, ver
    `assets/lexico/PROCEDENCIA.md`.

    Em cache porque um livro de 300 páginas o consultaria 300 vezes, e ele não muda entre elas.
    """
    if caminho is not None:
        return _de_um_arquivo(Path(caminho))
    arquivos = PERFIS.get(perfil)
    if arquivos is None:
        raise ValueError(f"perfil desconhecido: {perfil!r}. Conhecidos: {', '.join(PERFIS)}")
    return frozenset().union(*(_de_um_arquivo(c) for c in arquivos))


def _de_um_arquivo(caminho: Path) -> frozenset[str]:
    """Um `.txt.gz` de uma palavra por linha, ou o conjunto vazio se ele não estiver lá."""
    try:
        with gzip.open(caminho, "rt", encoding="utf-8") as fh:
            return frozenset(linha.strip().casefold() for linha in fh if linha.strip())
    except OSError:
        return frozenset()


def conhecida(palavra: str, lexico: frozenset[str]) -> bool:
    """A palavra está no léxico, ignorando caixa? Pontuação nas pontas não é considerada."""
    return palavra.strip(PONTUACAO_DE_BORDA).casefold() in lexico


def e_palavra(texto: str) -> bool:
    """Isto é candidato a palavra?

    Três condições: comprimento, **nenhum dígito** -- é o que mantém lance fora --, e letras na
    maioria. A palavra *lida* pode ter um caractere estranho no meio; é para isso que se sinaliza.
    """
    limpo = texto.strip(PONTUACAO_DE_BORDA)
    if len(limpo) < MIN_TAMANHO or any(c.isdigit() for c in limpo):
        return False
    letras = sum(1 for c in limpo if c.isalpha())
    return letras / len(limpo) >= FRACAO_DE_LETRAS


def palavras_de(texto: str) -> tuple[str, ...]:
    """Os tokens de `texto` que **são palavra** por `e_palavra`, já aparados.

    É o denominador da conferência: "3 fora do léxico" não diz nada sem "de 412". Sai do mesmo
    laço de `desconhecidas`, porque duas contagens com réguas diferentes dariam uma fração que não
    fecha.

    **`MIN_TAMANHO` vale aqui também**, e por isso `the` e `of` não entram na conta."""
    return tuple(palavra for _inicio, _fim, palavra in _tokens_de_palavra(texto))


def _tokens_de_palavra(texto: str) -> Iterator[tuple[int, int, str]]:
    """`(inicio, fim, palavra aparada)` de cada token que é candidato a palavra.

    O intervalo é o da palavra **aparada**, e não o do token bruto: numa marca `[Diagrama 3]` o
    que se conferiria seria `[Diagrama`, e o que se sublinharia na tela incluiria o colchete."""
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
    """Os trechos de `texto` que são palavra e o léxico **não** conhece (S-209, S-266).

    Devolve `(inicio, fim, palavra)` em deslocamento de caractere -- que é a moeda das ferramentas
    do editor (`text/rico.py`). Não propõe nada, não ordena por semelhança e não olha o modelo: é
    a pergunta mais simples que este módulo sabe responder, e a única que a S-209 autoriza sobre
    texto já lido.

    **O que não é palavra fica de fora**, e é `e_palavra` quem decide: `Nf3`, `1.d4` e `15` não
    são candidatos a nada. Sem essa guarda a folha inteira ficaria marcada, e uma marcação que
    acende em tudo não distingue coisa nenhuma.

    `ignorar` são intervalos que não se confere, e o cliente é a aba de texto: `[Diagrama 3]` é
    **referência ao diagrama**, e não texto do livro.

    **A caixa não é conferida aqui.** O léxico compara em `casefold`, então `poSition` passa como
    conhecida -- e é o certo: quem separa `s` de `S` é a altura do box na S-211, com medição.
    """
    # **Léxico vazio desliga a conferência (S-357).** Sem palavra nenhuma na lista, `conhecida`
    # responde `False` para tudo e a folha inteira saía sublinhada -- que é o mesmo sintoma que a
    # guarda de `e_palavra` acima existe para evitar, por outra porta. E o caso não é hipotético:
    # é o de um clone sem `data/lexico/`, onde `carregar` devolve o conjunto vazio.
    #
    # É a mesma regra que `escolher` e `juntar_hifenizadas` já seguem: sem lista, o dicionário não
    # decide nada.
    if not lexico:
        return ()
    vetados = tuple((min(a, b), max(a, b)) for a, b in ignorar)
    achados: list[tuple[int, int, str]] = []
    for inicio, fim, palavra in _tokens_de_palavra(texto):
        if conhecida(palavra, lexico):
            continue
        if any(inicio < veto_fim and fim > veto_inicio for veto_inicio, veto_fim in vetados):
            continue
        achados.append((inicio, fim, palavra))
    return tuple(achados)


# --------------------------------------------------------------------------------------
# A sinalizacao: a porta larga, e por que ela nao e a de `e_palavra`
# --------------------------------------------------------------------------------------

MOTIVOS = ("fora-do-lexico",)


@dataclass(frozen=True)
class Marca:
    """Uma palavra que o léxico não conhece, com onde ela está e por que foi marcada.

    `palavra` é o texto **idêntico** ao que estava no documento -- é o critério de aceite do item,
    e é o que separa sinalizar de corrigir. Não há um campo `sugestao` aqui, e a ausência é a
    entrega: a S-209 mediu que os 18 lances maltratados que caem no léxico não estão no dicionário,
    e que uma sugestão os reescreveria como palavra.
    """

    inicio: int
    fim: int
    palavra: str
    motivo: str = "fora-do-lexico"

    @property
    def intervalo(self) -> tuple[int, int]:
        return (self.inicio, self.fim)


def suspeita(texto: str) -> bool:
    """Este token é candidato a **palavra corrompida**? A porta larga da sinalização.

    ## Por que ela não é a de `e_palavra`, e por que as duas coexistem

    `e_palavra` proíbe **qualquer dígito**, e a proibição é certa lá: ela guarda o caminho da
    *correção*, e a cicatriz que a S-209 registra é lance maltratado virando palavra. Só que a
    mesma proibição derruba o exemplo com que a S-209 abre:

        Bib1i0g[aPhY     um erro que o dicionário vê e a legalidade não

    Dois dígitos no meio de dez letras, e `e_palavra` o descarta antes de olhar -- então o item
    entregaria uma sinalização que não sinaliza o caso que o motiva.

    **A pergunta certa não é "tem dígito?", é "isto é notação?"** -- e essa já foi respondida com
    medição pela S-208: `notacao.peso_de_notacao` conhece lance, número de lance, reticência,
    resultado e o composto `19...♖g8`. Aqui ela entra no lugar do veto de dígito.

    **E o custo de errar é diferente dos dois lados, que é o que autoriza duas portas.** Marcar um
    lance por engano custa um sublinhado que a pessoa ignora; *corrigir* um lance por engano custa
    um lance reescrito no PGN. A porta larga só serve à marca.
    """
    from .notacao import peso_de_notacao

    limpo = texto.strip(PONTUACAO_DE_BORDA)
    if len(limpo) < MIN_TAMANHO:
        return False
    letras = sum(1 for c in limpo if c.isalpha())
    if letras / len(limpo) < FRACAO_DE_LETRAS:
        return False
    return peso_de_notacao(texto) == 0


def sinalizar(
    texto: str,
    lexico: frozenset[str],
    *,
    ignorar: Sequence[tuple[int, int]] = (),
) -> tuple[Marca, ...]:
    """As palavras que o léxico não conhece, **marcadas e idênticas**. Nunca troca nada.

    É a entrega da S-209 sobre texto já lido, e a diferença para `desconhecidas` é a porta: aqui
    entra o token com dígito no meio que não é notação (`Bib1i0g[aPhY`), que é o exemplo com que o
    item abre. Ver `suspeita`.

    `ignorar` são intervalos que não se confere -- `[Diagrama 3]` é referência ao diagrama, e não
    texto do livro.
    """
    vetados = tuple((min(a, b), max(a, b)) for a, b in ignorar)
    achadas: list[Marca] = []
    for casamento in _TOKEN.finditer(texto):
        bruto = casamento.group()
        limpo = bruto.strip(PONTUACAO_DE_BORDA)
        if not limpo or not suspeita(bruto) or conhecida(limpo, lexico):
            continue
        inicio = casamento.start() + (len(bruto) - len(bruto.lstrip(PONTUACAO_DE_BORDA)))
        fim = inicio + len(limpo)
        if any(inicio < veto_fim and fim > veto_inicio for veto_inicio, veto_fim in vetados):
            continue
        achadas.append(Marca(inicio=inicio, fim=fim, palavra=limpo))
    return tuple(achadas)


# --------------------------------------------------------------------------------------
# As duas fronteiras de palavra: a que o dicionario decide, e a que ele recusou
# --------------------------------------------------------------------------------------

HIFENS = "-‐‑­"
"""Os hífens que quebram palavra no fim da linha: o comum, o tipográfico, o não-quebrável e o
condicional. **A meia-risca `–` não está aqui** de propósito: ela é intervalo (`1-0`, `pp. 4–7`) e
nunca hifenização, e aceitá-la juntaria dois números de página numa palavra."""

PARTIR_COLADAS = False
"""A outra fronteira de palavra, e a que **não entrou**. `ofthe` -> `of` `the`.

**A régua é a certa e mesmo assim ela não paga neste acervo.** A condição é a mesma da junção -- só
parte o que **não** está no dicionário --, e o projeto de origem a mediu com 7 de 7 partições
certas e nenhuma das 51 palavras boas que também decomporiam sendo partida.

Medido aqui, em 40 páginas de 11 livros (`docs/metrics/texto_dicionario.json`): **0 partições
certas contra 5 erradas.** As cinco vêm dos nomes -- `carrying` vira `carr ying`, porque `Carr` e
`Ying` são sobrenomes de jogador, e a lista de nomes tem 349 mil deles. As colagens reais (`ofthe`,
`timefor`) têm metade com menos de 4 letras, e baixar o piso de `MIN_TAMANHO` para alcançá-las é
exatamente o que abre a porta para as cinco.

**Não há função de partir neste módulo**, e a constante existe para que a ausência seja decisão e
não esquecimento -- `test_a_palavra_boa_que_decomporia_nao_e_partida` afirma as duas coisas. Fica
fora até haver referência que a justifique.

A assimetria entre as duas fronteiras tem explicação, e ela é sobre o léxico e não sobre a régua:
juntar exige que **a junção** esteja na lista, e uma palavra longa raramente aparece por acaso;
partir exige que **os dois pedaços** estejam, e com 349 mil nomes quase todo pedaço de 4 letras
está."""


@dataclass(frozen=True)
class Juncao:
    """Uma hifenizada que a quebra de linha partiu, e que o léxico decidiu juntar."""

    linha: int
    """Índice da linha da **esquerda** -- a que termina em hífen."""

    esquerda: str
    direita: str
    junta: str

    def __str__(self) -> str:
        return f"linha {self.linha}: {self.esquerda}{self.direita} -> {self.junta}"


def juntar_hifenizadas(
    linhas: Sequence[str],
    lexico: frozenset[str],
) -> tuple[list[str], tuple[Juncao, ...]]:
    """Junta a palavra que a quebra de linha partiu. `(linhas novas, o que foi juntado)`.

    ## Por que esta é uma das duas coisas que o dicionário decide sozinho

    Nas duas fronteiras de palavra o dicionário é o **próprio critério**, e não precisa de limiar:
    ou a junção está na lista, ou não está. É o que a separa da correção por semelhança, que
    precisaria escolher entre candidatos -- e é por isso que a S-209 autoriza esta e proíbe aquela.

    ## As três condições, e as duas últimas são as que recusam

    1. a linha da esquerda termina em hífen (`HIFENS`), e há uma linha à direita com token;
    2. **a junção sem o hífen está no léxico** -- `em` + `barrassment` -> `embarrassment` está;
       `Xue` + `Fierro` não, e por isso o nome composto sobrevive à passada;
    3. **a forma COM o hífen não está no léxico** -- se `well-known` é palavra da lista, o hífen é
       do autor e não da diagramação, e juntar apagaria a grafia que o livro escolheu.

    Medido no projeto de origem sobre a verdade: **6 de 6 junções certas, com as 2 que não devem
    juntar recusadas**. As duas recusadas são nome composto, e é a condição 2 que as segura.

    ## O que ela faz com o texto, e por que não é simétrico

    A metade da direita migra para a linha da esquerda, e o hífen some. É a convenção de extração
    de texto: a palavra pertence à linha em que ela **começou**, e é lá que a busca deve encontrá-la
    inteira. Uma linha da direita que fique vazia é preservada como string vazia em vez de sumir --
    quem chama pode ter bbox por linha, e apagar uma linha desalinharia a lista.
    """
    if not lexico or len(linhas) < 2:
        return (list(linhas), ())

    saida = list(linhas)
    juncoes: list[Juncao] = []
    for indice in range(len(saida) - 1):
        esquerda, direita = saida[indice], saida[indice + 1]
        proposta = _propor_juncao(esquerda, direita, lexico)
        if proposta is None:
            continue
        nova_esquerda, nova_direita, juncao = proposta
        saida[indice] = nova_esquerda
        saida[indice + 1] = nova_direita
        juncoes.append(Juncao(linha=indice, **juncao))
    return (saida, tuple(juncoes))


def _propor_juncao(
    esquerda: str,
    direita: str,
    lexico: frozenset[str],
) -> tuple[str, str, dict[str, str]] | None:
    """As duas linhas com a hifenizada juntada, ou `None` quando o léxico não decide."""
    sem_espaco = esquerda.rstrip()
    if not sem_espaco or sem_espaco[-1] not in HIFENS:
        return None
    corte = sem_espaco.rfind(" ")
    cabeca = sem_espaco[corte + 1 : -1]
    if not cabeca or not cabeca[-1].isalpha():
        return None

    resto = direita.lstrip()
    if not resto:
        return None
    fim = resto.find(" ")
    cauda_bruta = resto if fim < 0 else resto[:fim]
    cauda = cauda_bruta.strip(PONTUACAO_DE_BORDA)
    if not cauda or not cauda[0].isalpha():
        return None

    junta = cabeca + cauda
    if not conhecida(junta, lexico):
        return None
    if conhecida(f"{cabeca}-{cauda}", lexico):
        # O hífen é do autor, e não da diagramação: `well-known` está na lista, e juntar apagaria
        # a grafia que o livro escolheu.
        return None

    nova_esquerda = sem_espaco[: corte + 1] + junta + cauda_bruta[len(cauda) :]
    nova_direita = "" if fim < 0 else resto[fim + 1 :]
    return (nova_esquerda, nova_direita, {"esquerda": cabeca, "direita": cauda, "junta": junta})
