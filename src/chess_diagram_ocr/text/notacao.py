"""Fatiar: onde acaba a prosa e começa o lance (S-208).

**É a peça central do item, e ela vem antes de qualquer correção.** A spec diz por quê em uma
frase: *"aplicar lista de palavras a `Bxf6` destruiria a parte do livro que o programa existe para
ler"*. Tudo que este subpacote já faz -- léxico, dicionário, caixa alta -- tem de saber onde não
mexer, e é este módulo que responde.

## O que entra aqui, e o que ainda não

Entra `fatiar`, e entra a primeira coisa que só ele consegue decidir: **o número de lance partido
em dois**. `15 0-0?!` saía `1 5 0-0?!`, e 41 vezes em 20 páginas.

Ele **não** é consertável por geometria, e isso foi medido antes de este módulo existir: o vão
entre os dois dígitos de `15` e o vão entre duas palavras têm o mesmo tamanho.

    vão entre dígitos    p10 0,46   mediana 0,79   p90 1,17   (em larguras medianas de caixa)
    vão entre palavras   p10 0,62   mediana 0,86   p90 1,60

Um corte em 0,55 juntaria 12 dos 44 dígitos e **destruiria 49 espaços de verdade**. O que separa
os dois casos não está na tinta: está em saber que ali se espera um **número de lance**, isto é,
um dígito seguido de ponto e de um lance. É a informação que só a notação tem.

**Não entra `validar`** -- a legalidade pela posição, com o `chess`, e o `.review.pgn` de quem não
fecha. Por isso a S-208 fica **parcial** e não implementada: a metade que valida é a que dá o PGN
de partida, e ela é outro trabalho.

## A régua é conservadora de propósito

Um lance mal lido que este módulo tome por prosa perde uma correção; um trecho de prosa que ele
tome por lance vira erro no PGN. Os dois custos não são simétricos, e por isso `fatiar` só declara
lance o que casa com a forma inteira -- não há "parece um lance".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import chess

FIGURINAS = "♔♕♖♗♘♙♚♛♜♝♞♟"
"""As peças como o classificador as devolve. O livro usa **um** conjunto para os dois lados, e
quem decide a cor é a paridade do número do lance -- que é trabalho da validação, não daqui."""

LETRAS_DE_PECA = "KQRBNSTLDCP"
"""As iniciais de peça nas notações que o acervo tem: inglesa, alemã, portuguesa, espanhola."""

FIGURINAS_DA_LETRA: dict[str, str] = {
    "K": "♔♚",
    "Q": "♕♛",
    "R": "♖♜",
    "B": "♗♝",
    "N": "♘♞",
    "P": "♙♟",
}
"""Inicial **inglesa** de peça -> as duas figurinas daquela peça. Quem consome é a busca (S-245).

**Só o inglês, e é decisão medida em risco.** As outras notações do acervo colidem entre si:
`R` é *rook* em inglês e *rei* em português, `C` é *cavalo* em português e nada em inglês, `B` é
*bispo* e *Bauer*. Uma tabela que mapeasse todas ofereceria, na busca por `R`, tanto a torre quanto
o rei -- e a S-245 é explícita sobre o que a busca faz: ela **oferece**, e oferta que traz o que
não se pediu é pior que oferta nenhuma. O inglês entra porque é a notação do SAN, que é o que
alguém digita quando procura um lance.

O caminho contrário -- figurina -> letra -- é derivado em `LETRA_DA_FIGURINA`, e não recopiado."""

LETRA_DA_FIGURINA: dict[str, str] = {
    figurina: letra for letra, figurinas in FIGURINAS_DA_LETRA.items() for figurina in figurinas
}
"""Figurina -> a inicial inglesa da peça. Derivado de `FIGURINAS_DA_LETRA`, e não escrito de novo.

**A cor não está aqui, e não pode estar** (S-283). O livro imprime `♗xb7` para o bispo das brancas e
para o das pretas -- é um conjunto só de glifos para os dois lados, e a S-208 registra isso como
"insolúvel visualmente". Quem sabe de quem é a vez é o **tabuleiro**, e é por isso que `validar`
recebe um e `fatiar` não: a mesma linha, começando numa posição de brancas ou de pretas, produz
lances diferentes e os dois são legítimos."""

_CASA = r"[a-h][1-8]"
_PECA = f"[{LETRAS_DE_PECA}{FIGURINAS}]"
_SUFIXO = r"[+#!?±∓⩲⩱=]*"

_PROMOCAO = rf"(?:=[{LETRAS_DE_PECA}{FIGURINAS}])?"

LANCE = re.compile(
    rf"^(?:"
    rf"{_PECA}[a-h]?[1-8]?x?{_CASA}"          # lance de peça: Nf3, Nbd2, N1e2, Bxf6
    rf"|[a-h]x{_CASA}{_PROMOCAO}"             # captura de peão: exd5, gxf1=Q
    rf"|{_CASA}{_PROMOCAO}"                   # avanço de peão: e4, a8=Q
    rf"|0-0(?:-0)?|O-O(?:-O)?"                # roque
    rf"){_SUFIXO}$"
)
"""Um lance inteiro, e nada além dele. Ver "A régua é conservadora" no cabeçalho.

**As três formas de peão são separadas de propósito.** Uma expressão com tudo opcional --
`peça? coluna? linha? x? casa` -- casa também com `xf6`, que não é lance nenhum: em SAN toda
captura tem algo antes do `x`. Frouxidão aqui vira prosa tratada como lance, que é o custo caro
dos dois."""

NUMERO_DE_LANCE = re.compile(r"^\d{1,3}$")
RETICENCIA = re.compile(r"^\.{2,3}$|^…$")


@dataclass(frozen=True)
class Fatia:
    """Um trecho contíguo de tokens, e o que ele é."""

    inicio: int
    fim: int
    """`[inicio, fim)` sobre a lista de tokens que entrou."""

    tipo: str
    """`lance` ou `prosa`."""

    @property
    def e_lance(self) -> bool:
        return self.tipo == "lance"


def e_numero_de_lance(token: str) -> bool:
    """`15`, `15.`, `15...` -- o número com o ponto ou a reticência que vier grudada nele."""
    return bool(NUMERO_DE_LANCE.match(_sem_envoltorio(token).rstrip(".…")))


ENVOLVE = "([{)]},;:"
"""Pontuação que envolve o token e não faz parte dele: `(instead`, `19...exf2+?)`.

O ponto final **não** entra: ele é parte do número de lance (`15.`), e tirá-lo aqui apagaria a
única coisa que distingue `15.` de um `15` qualquer no meio da prosa."""

RESULTADOS = ("1-0", "0-1", "½-½", "1/2-1/2", "½–½")

COMPOSTO = re.compile(r"^(\d{1,3})(\.{1,3}|…)(.+)$")
"""`19...♖g8` -- número, reticência e lance grudados num token só.

É como o livro imprime a resposta das pretas, e sem isto ela vira prosa: o token inteiro não casa
com lance nenhum, e o número dentro dele não é visto."""


def _sem_envoltorio(token: str) -> str:
    return token.strip().strip(ENVOLVE)


def _e_de_notacao(token: str) -> bool:
    """O token pertence a uma sequência de notação -- lance, número, reticência ou resultado.

    Aceita também o **composto** `19...♖g8`, que é um token só com número e lance dentro; ver
    `COMPOSTO`.
    """
    return peso_de_notacao(token) > 0


def peso_de_notacao(token: str) -> int:
    """Quanto o token conta para o mínimo de `fatiar`: `0`, `1` ou `2`.

    **O composto vale dois, e é o item.** `19...♖g8` é número *e* lance no mesmo token: exigir dois
    tokens seguidos o deixaria de fora sempre que ele viesse sozinho, e ele é como o livro imprime
    a resposta das pretas.
    """
    limpo = _sem_envoltorio(token)
    if not limpo:
        return 0
    achado = COMPOSTO.match(limpo)
    if achado and _e_lance(achado.group(3)):
        return 2
    if _e_lance(limpo) or e_numero_de_lance(limpo) or RETICENCIA.match(limpo):
        return 1
    return 1 if limpo in RESULTADOS else 0


def _tem_lance(token: str) -> bool:
    """O token **é** um lance, ou traz um dentro (o composto `19...♖g8`)."""
    limpo = _sem_envoltorio(token)
    achado = COMPOSTO.match(limpo)
    return _e_lance(limpo) or bool(achado and _e_lance(achado.group(3)))


def _e_lance(texto: str) -> bool:
    """`LANCE`, tolerando o ponto final de frase que vem depois dele.

    O ponto não entra em `ENVOLVE` porque ele é parte do **número** (`15.`); aqui ele é o fim da
    frase, e um lance nunca termina em ponto."""
    return bool(LANCE.match(texto.rstrip(".")))


SO_PONTUACAO = re.compile(r"^[.,;:!?+=…()\[\]{}'\"\-—–△⌓✝#]+$")
"""Token que é só pontuação ou símbolo de anotação, e **não vota** em `e_linha_de_notacao`.

Ele não é evidência de prosa nem de lance: é o que sobra quando o OCR separa a marca do lance que
ela qualifica. `28 . . . b6 ! !` são sete tokens, dos quais cinco são pontuação solta -- e com eles
no denominador uma linha de lances inteira fica em minoria de si mesma.

Medido: ver `e_linha_de_notacao`."""


def e_linha_de_notacao(texto: str, *, maioria: float = 0.5) -> bool:
    """A **maioria** dos tokens deste trecho é notação? Ver `peso_de_notacao` (S-249).

    Existe porque a legenda de um diagrama e a linha de lances logo abaixo dele são vizinhas na
    página, e a régua que casa linha com diagrama (`pdf_text.assign_lines_to_diagrams`) não sabe
    distinguir as duas -- ela mede distância, não conteúdo. Medido no conjunto de campo
    (`docs/metrics/texto_legenda.json`): dos 83 parágrafos atados a um diagrama, **14 (17%) são
    linha de lances**.

    Maioria, e não "tem um lance": `Ivkov—Dueckstein 1967` traz um `1967` que parece número de
    lance, e continua sendo legenda. Dois tokens de notação num parágrafo de dez é comentário; seis
    em dez é notação.

    **Pontuação solta não entra na conta**, nem de um lado nem do outro -- ver `SO_PONTUACAO`.
    Medido em 2026-08-26 contra `docs/metrics/texto_notacao_referencia.jsonl`, 305 blocos rotulados
    à mão em 24 folhas de 15 livros:

        régua                          precisão   recall     F1
        pontuação votava                  0,8800   0,6822   0,7686
        pontuação não vota                0,8899   0,7519   0,8151

    Nove linhas de lances a mais reconhecidas, sem nenhum falso a mais -- os mesmos 12. É o vão que
    a regra 5 da SPEC_EDITOR pede para uma troca entrar ligada.

    **E o que a mesma medição diz que esta régua não serve para fazer**: derivar o estilo `notacao`
    sozinha, no editor. Ver `docs/metrics/texto_notacao_estilo.json` e a S-249 na SPEC_EDITOR.

    Trecho vazio responde `False`: não há o que decidir, e "não é notação" é o lado que não muda o
    desenho.
    """
    tokens = [t for t in texto.split() if t and not SO_PONTUACAO.match(t)]
    if not tokens:
        return False
    de_notacao = sum(1 for token in tokens if peso_de_notacao(token) > 0)
    return de_notacao >= max(2, int(len(tokens) * maioria))


def fatiar(tokens: Sequence[str], *, minimo: int = 2) -> list[Fatia]:
    """Os tokens partidos em fatias de `lance` e de `prosa`, na ordem.

    `minimo` é quantos tokens de notação seguidos são precisos para a fatia contar como lance.
    **Dois, e não um**, porque um número solto no meio da prosa é ano, página ou quantidade -- e
    `e4` sozinho é uma casa citada no texto. Notação de verdade vem em sequência.

    A régua é conservadora nos dois sentidos, e a assimetria é a do cabeçalho: perder um lance
    custa uma correção; ganhar uma prosa custa um erro no PGN.
    """
    if not tokens:
        return []
    pesos = [peso_de_notacao(t) for t in tokens]
    marcas = [p > 0 for p in pesos]

    # Um bloco de notação só vale se tiver `minimo` tokens; abaixo disso ele volta a ser prosa.
    fatias: list[Fatia] = []
    i = 0
    while i < len(tokens):
        if not marcas[i]:
            j = i
            while j < len(tokens) and not marcas[j]:
                j += 1
            fatias.append(Fatia(i, j, "prosa"))
            i = j
            continue
        j = i
        while j < len(tokens) and marcas[j]:
            j += 1
        # **A fatia precisa de um lance de verdade, e não só de números.** Sem esta condição,
        # `capítulo 3 4 do livro` vira notação -- dois números seguidos somam o mínimo sozinhos --
        # e a junção de número de lance os funde em `34`. Foi o primeiro falso positivo do item.
        tem_lance = any(_tem_lance(tokens[k]) for k in range(i, j))
        tipo = "lance" if tem_lance and sum(pesos[i:j]) >= minimo else "prosa"
        fatias.append(Fatia(i, j, tipo))
        i = j

    # Prosa vizinha vira uma fatia só: duas seguidas seriam um corte que nada explica.
    juntas: list[Fatia] = []
    for fatia in fatias:
        if juntas and juntas[-1].tipo == fatia.tipo == "prosa":
            juntas[-1] = Fatia(juntas[-1].inicio, fatia.fim, "prosa")
        else:
            juntas.append(fatia)
    return juntas


MAX_DIGITOS = 3
"""Um número de lance não passa de três dígitos. Junta `1`+`5`, e recusa juntar o quarto."""


def _digitos_iniciais(token: str) -> str:
    prefixo = ""
    for char in token:
        if not char.isdigit():
            break
        prefixo += char
    return prefixo


def _continua_o_numero(atual: str, seguinte: str) -> bool:
    """`1` + `5` e também `1` + `9...♕xf4!` -- o segundo token pode trazer o lance grudado.

    **A segunda forma é a mais comum, e escapou da primeira versão.** O livro imprime a resposta
    das pretas como `19...♕xf4!`, e quando a segmentação parte o número o que sobra é um dígito
    solto ao lado de um token que **começa** por dígito. Exigir que os dois fossem dígitos puros
    deixava esse caso de fora.
    """
    # **Só um dígito à esquerda**, e isso saiu de uma regressão medida. A divisão acontece DENTRO
    # do número, então o pedaço da esquerda é um dígito só. Sem esta condição, `15 2 f3 xg5` --
    # duas numerações legítimas lado a lado, na notação espaçada do `Capablanca` -- virava `152`.
    if len(atual) != 1 or not atual.isdigit():
        return False
    prefixo = _digitos_iniciais(seguinte)
    if not prefixo:
        return False
    if len(atual) + len(prefixo) > MAX_DIGITOS:
        return False
    # o resto do token seguinte, se houver, tem de ser continuação de número de lance
    resto = seguinte[len(prefixo) :]
    return not resto or bool(COMPOSTO.match(seguinte)) or resto.startswith((".", "…"))


def juntar_numero_de_lance(texto: str, *, minimo: int = 2) -> str:
    """`1 5 0-0?!` -> `15 0-0?!`. Só dentro de fatia de lance; a prosa sai intacta.

    **A regra que só a notação permite:** em notação de xadrez **não existem dois números
    seguidos**. Um número de lance é sempre seguido de um lance ou de uma reticência, então dois
    tokens de dígito lado a lado ali são um número que a segmentação partiu.

    Fora da notação a mesma sequência é legítima -- `In 1968 he lost`, `capítulo 3 4` -- e por isso
    a junção acontece depois de `fatiar`, e nunca antes. Ver o cabeçalho: a geometria não separa os
    dois casos, e esta é a informação que ela não tem.
    """
    tokens = texto.split()
    if len(tokens) < 2:
        return texto

    juntar: set[int] = set()
    for fatia in fatiar(tokens, minimo=minimo):
        if not fatia.e_lance:
            continue
        for k in range(fatia.inicio, fatia.fim - 1):
            if _continua_o_numero(tokens[k], tokens[k + 1]):
                juntar.add(k)
    if not juntar:
        return texto

    saida: list[str] = []
    i = 0
    while i < len(tokens):
        atual = tokens[i]
        while i in juntar and i + 1 < len(tokens):
            atual += tokens[i + 1]
            i += 1
        saida.append(atual)
        i += 1
    return " ".join(saida)


# --------------------------------------------------------------------------- validar (S-283)

_SUFIXO_SOLTO = "+#!?±∓⩲⩱∞=→⊕↑"
"""O que se tira do fim de um lance antes de o entregar ao tabuleiro.

`=` está aqui e **não** quebra a promoção: `e8=Q` termina em `Q`, e só o que sobra depois da peça é
que cai. `e8=Q+` perde o `+`, `13.♗g5!?` perde o `!?`, e `e4=` -- que é como alguns livros escrevem
"igual" colado no lance -- perde o `=`."""


@dataclass(frozen=True)
class LanceLido:
    """Um lance da linha impressa que o tabuleiro aceitou."""

    token: str
    """Como o livro escreveu, com figurina e sufixo. É o que se mostra a quem for conferir."""

    san: str
    """O SAN que o `chess` devolveu -- já com a peça em inglês e a desambiguação que a posição pede."""

    move: chess.Move
    numero: int | None = None
    """O número de lance que o livro imprimiu junto, quando imprimiu. `None` = não disse."""


@dataclass(frozen=True)
class LinhaValidada:
    """O que a linha impressa deu quando jogada sobre uma posição (S-208/S-283).

    **Propõe, marca, não reescreve calado** -- é o contrato da S-15. Lance que fecha vira `move`;
    lance que não fecha para a linha e sai com o motivo, e nada é adivinhado no lugar dele.
    """

    lances: tuple[LanceLido, ...] = ()
    motivo: str = ""
    """Por que a linha parou. Vazio = ela fechou inteira."""

    token: str = ""
    """O token que não fechou. É o que vai para a revisão junto com o motivo."""

    posicao: int = -1
    """O índice desse token na lista que entrou. `-1` quando a linha fechou."""

    @property
    def fechou(self) -> bool:
        return not self.motivo

    @property
    def san(self) -> tuple[str, ...]:
        return tuple(lance.san for lance in self.lances)


def para_ingles(token: str) -> str:
    """O lance com as figurinas trocadas pelas iniciais inglesas: `♗xb7` -> `Bxb7`.

    Só as figurinas. As iniciais de outras línguas ficam como estão, e é a decisão que
    `FIGURINAS_DA_LETRA` já documenta: `R` é *rook* em inglês e *rei* em português, `C` é *cavalo*
    e nada em inglês. Traduzi-las exigiria saber a língua do livro, e errar a língua troca uma peça
    por outra **num lance que o tabuleiro aceita** -- que é o pior defeito possível aqui.
    """
    return "".join(LETRA_DA_FIGURINA.get(caractere, caractere) for caractere in str(token or ""))


def _limpo(token: str) -> str:
    """O token pronto para o `parse_san`: sem envoltório, sem sufixo e com a peça em inglês."""
    return para_ingles(_sem_envoltorio(token)).rstrip(_SUFIXO_SOLTO)


def validar(tokens: Sequence[str], board: chess.Board) -> LinhaValidada:
    """Joga a linha impressa sobre a posição, e para no primeiro lance que ela não sustenta.

    **É a metade que faltava à S-208.** `fatiar` separa lance de prosa; isto responde se `♘d7` é
    possível *nesta* posição -- e é a única coisa que separa os dois falsos positivos que aquele
    item registrou: `Capablanca` p72, `7` + `2` -> `72`, "estruturalmente idêntico ao caso que se
    quer consertar".

    **O tabuleiro é o dicionário.** `Nf3` é válido numa posição e impossível na seguinte, e nenhuma
    lista de palavras sabe disso. Por isso a assinatura pede uma posição, e por isso o resultado
    diz *onde* parou: uma linha que fecha inteira é uma linha lida certo, e uma que para no quarto
    lance diz que os três primeiros estão bons.

    **O número de lance impresso é conferido, e não obedecido.** Quem decide de quem é a vez é a
    posição; o número serve para acusar divergência -- um `15.` numa posição de pretas é sinal de
    que a leitura perdeu ou inventou um meio-lance, e isso vale mais dito que corrigido.

    `board` não é modificado: a linha é jogada numa cópia.
    """
    tabuleiro = board.copy(stack=False)
    lidos: list[LanceLido] = []
    numero: int | None = None

    for indice, bruto in enumerate(tokens):
        token = str(bruto or "").strip()
        if not token:
            continue

        nu = _sem_envoltorio(token)
        if nu in RESULTADOS:
            # O resultado fecha a partida: o que vier depois dele é prosa, não lance.
            break
        if RETICENCIA.match(nu):
            continue
        if e_numero_de_lance(token):
            numero = int(nu.rstrip(".…"))
            continue

        # **`token` continua sendo o que o livro escreveu**, e `parte` é o que vai ao tabuleiro. A
        # distinção não é cosmética: quem for conferir procura `5.exd6` na página, e não `exd6`.
        parte = token
        composto = COMPOSTO.match(para_ingles(nu))
        if composto is not None:
            numero = int(composto.group(1))
            parte = composto.group(3)

        esperado = tabuleiro.fullmove_number
        if numero is not None and numero != esperado:
            return LinhaValidada(
                tuple(lidos),
                motivo=f"o livro escreveu o lance {numero} e a posição está no {esperado}",
                token=token,
                posicao=indice,
            )

        limpo = _limpo(parte)
        if not limpo:
            continue
        try:
            move = tabuleiro.parse_san(limpo)
        except (chess.IllegalMoveError, chess.InvalidMoveError, chess.AmbiguousMoveError, ValueError) as erro:
            return LinhaValidada(
                tuple(lidos),
                motivo=_motivo_de(erro, limpo),
                token=token,
                posicao=indice,
            )

        san = tabuleiro.san(move)
        tabuleiro.push(move)
        lidos.append(LanceLido(token=token, san=san, move=move, numero=numero))
        numero = None

    return LinhaValidada(tuple(lidos))


def _motivo_de(erro: Exception, limpo: str) -> str:
    """A frase que vai para a revisão. Nomeia o lance e o que houve com ele, e nada mais.

    Três casos e não um: *ilegal* diz que a leitura está certa e a posição não bate; *não é lance*
    diz que a leitura errou o glifo; *ambíguo* diz que faltou a coluna de desambiguação -- e os
    três pedem coisas diferentes de quem for conferir.
    """
    if isinstance(erro, chess.IllegalMoveError):
        return f"{limpo} não é legal nesta posição"
    if isinstance(erro, chess.AmbiguousMoveError):
        return f"{limpo} não diz qual das peças joga"
    return f"{limpo} não é um lance"

__all__ = [
    "COMPOSTO",
    "LanceLido",
    "LinhaValidada",
    "ENVOLVE",
    "FIGURINAS",
    "LANCE",
    "LETRAS_DE_PECA",
    "MAX_DIGITOS",
    "NUMERO_DE_LANCE",
    "RESULTADOS",
    "RETICENCIA",
    "Fatia",
    "e_linha_de_notacao",
    "e_numero_de_lance",
    "fatiar",
    "juntar_numero_de_lance",
    "peso_de_notacao",
    "para_ingles",
    "validar",
]
