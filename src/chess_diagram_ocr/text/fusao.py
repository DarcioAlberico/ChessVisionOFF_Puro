"""A prosa de um leitor, a notação de outro: o roteador de tokens (S-716, S-717, S-718).

**Nenhum leitor é bom nas duas coisas.** O glifo foi treinado em livro de xadrez e é o único que vê
figurina; o Tesseract lê prosa de 2,7× a 11× melhor e estraga lance de peão (`g4!` -> `24!`). A camada de
um livro nascido digital **é** a tinta na prosa, e não representa figurina nenhuma. Medido em 2026-10-30 no
ouro digital: glifo 3,61% de CER de prosa, Tesseract 1,33%, fusão v5 1,25%, sem perder notação.

## As regras, na ordem

1. Token de notação **em qualquer lado** -> glifo, salvo se o outro leitor leu ali uma palavra que existe
   (`the`, `with`, `Wissen`): o glifo vê `♔e` em `the`.
2. O número de lance do outro leitor só entra quando o glifo o **partiu** (`7.` contra `17.`). Do mesmo
   tamanho (`27.` contra `21.`), é erro do Tesseract, e fica o do glifo.
3. Prosa -> o outro leitor.
4. Sem par: notação e dígito do glifo ficam; prosa do outro leitor entra.

**A régua fica de fora.** O classificador de token daqui é próprio, e um teste de grafo de import trava
isso: o instrumento não pode compartilhar código com o medido, ou o erro de um vira o acerto do outro.

**As palavras funcionais curtas moram aqui.** `lexico.MIN_TAMANHO = 4` as deixa de fora do léxico, e
acrescentá-las lá mudaria `dicionario.corrigir` e a junção de hífen no caminho do glifo: desligar a fusão
não devolveria o glifo de antes.

## A marca por palavra (S-718)

Os sinais crus inundam: a discordância marca 10,0% das palavras no ouro e 27,7% na prata; o léxico sozinho,
26,8% e 40,1%. O teto da marca é 5%. Por isso os sinais **ranqueiam**, e só as mais suspeitas da folha são
marcadas. **Prosa que veio da camada não tem outro leitor, e nunca é marcada.**
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from .notacao import FIGURINAS, LETRAS_DE_PECA, MEIAS_RISCAS

ClasseDoToken = Literal["prosa", "notacao", "outro"]
OrigemDoToken = Literal["glifo", "outro"]
"""`glifo` ou `outro`: o leitor que não é o glifo (o Tesseract, o RapidOCR ou a camada)."""

PROSA: Final = "prosa"
NOTACAO: Final = "notacao"
OUTRO: Final = "outro"

_PECA = LETRAS_DE_PECA + FIGURINAS
_HIFEN = f"-{MEIAS_RISCAS}"
_FIGURINA = re.compile(r"[♔-♟]")
_LANCE = re.compile(
    rf"^(\d+\.+|\.\.\.|…)?([{_PECA}]?[a-h]?[1-8]?[xX:×]?[a-h][1-8](=?[{_PECA}])?:?|O-O(-O)?|0-0(-0)?)"
    r"(e\.p\.)?[+#†‡t]*[!?]*[=+\-–—±∓∞⩲⩱]*$"
)
_CASA_DO_LANCE = rf"[a-h]?[1-8]?[xX:×]?[a-h][1-8](?:=?[{_PECA}])?[+#†‡!?]*"
_LANCE_COM_SINAL = re.compile(
    rf"^(?:\d+\.+|\.\.\.|…)?[{_PECA}]?{_CASA_DO_LANCE}[\ue000-\uf8ff²³°][+#†‡!?]*$"
    rf"|^(?:(?:\d+\.+|\.\.\.|…)[{_PECA}]?|[{_PECA}]){_CASA_DO_LANCE}[a-z][+#†‡!?]*$"
)
"""O lance com o sinal de avaliação colado, que a camada escreve em código de fonte: `19.Bd3\uf0b1`, `Rfc1²`,
`Rxg5i`, `24...f4e`. A letra solta só conta com peça ou número de lance na frente: `f4e` sozinho não é lance, e
uma letra só é o que tira `af7anca` daqui. Sem isto, 41 lances do *Chess Evolution 2013* iam ao Tesseract como se
fossem prosa, e voltavam `19.2d3+` (S-716, terceira rodada do crítico)."""
_NUMERO_DE_LANCE = re.compile(r"^\d+\.+$")
_AVALIACAO = re.compile(r"^([+\-=±∓⩲⩱∞!?#†□△⌓→↑⇆○●N]|\+/-|-/\+|\+-|-\+|=/\+|\+/=|=/∞)+$")
_RESULTADO = re.compile(rf"^(1[{_HIFEN}]0|0[{_HIFEN}]1|½[{_HIFEN}]½|1/2[{_HIFEN}]1/2|\*)$")
_SIMBOLOS = "ʘ⊕⊞⨀□△▲▼○●↑→←⇆⇄∆∇⌓⩲⩱±∓∞#†‡"
_DESCRITIVA = re.compile(
    rf"^(\d+\.+)?[{LETRAS_DE_PECA}]{{1,3}}[1-8]?(-|[xX:])?[{LETRAS_DE_PECA}]{{0,3}}[1-8]?[a-z]{{0,2}}(ch|mate|\+|#|!|\?)*$"
)
_CIRILICA = re.compile(r"^(\d+\.+)?(Кр|[КФЛС])?[a-hаеЬсd]?[1-8]?[:xх]?[a-hаеЬсd][1-8][+#!?]*$")
"""Com âncora no fim, ao contrário da régua: sem ela `af7anca` era lance, e a palavra certa perdia (S-716)."""
_ACENTOS_DE_FONTE = re.compile(r"^[^A-Za-z]*[À-ÿ]{3,}[^A-Za-z]*$")
_LONGA = re.compile(rf"^(\d+\.+)?[{_PECA}]?[a-h][1-8][-x×:–][a-h][1-8]")
_LETRA_DE_PECA = re.compile(f"^[{LETRAS_DE_PECA.replace('A', '')}]$")
"""A inicial sozinha é notação, menos o `A`: é o artigo do português, do inglês e do italiano, e o léxico
(`_PALAVRA`) não guarda palavra de uma letra para o salvar (S-901)."""
_ROQUE = re.compile(rf"^(\d+\.+)?(O[{_HIFEN}]O([{_HIFEN}]O)?|0[{_HIFEN}]0([{_HIFEN}]0)?)")
_PALAVRA = re.compile(r"^[A-Za-zÀ-ÿ]{2,}(?:['’-][A-Za-zÀ-ÿ]+)*$")
_NUMERO = re.compile(r"^\(?(\d+)(?=\.)")
_SO_FIO = re.compile(r"^[|¦]+$")
"""O Tesseract lê `I` como `|`: 8 de 20 erros da fusão. Barra sozinha contra letra não é leitura melhor."""

CURTAS = frozenset(
    """
    a an and are as at be but by do for he her his i if in is it its me my no not of on or our she so the
    to up us was we who you
    a ao aos as com da das de do dos e é em na nas no nos o os ou para por que se sem um uma à às
    al el en es la las lo los y del con por que un una su sus
    am an auf aus bei das dem den der des die ein er es im in ist mit nach nicht und von vor zu zum zur
    au aux ce de des du en et il la le les ne on ou par pas que qui se un une
    de een en het in is met niet op te van voor zijn
    """.split()
)
"""Palavras que existem e o léxico compartilhado descarta. Privadas daqui: ver o cabeçalho."""


def classe_do_token(token: str) -> ClasseDoToken:
    """`prosa`, `notacao` ou `outro`. Próprio deste módulo: ver o cabeçalho."""
    nu = token.strip("()[]{},;:\"'")
    if not nu:
        return OUTRO
    # `Nc5).` e `Rh1!).`: o lance fechando um parêntese no fim da frase. Sem tirar os dois, ele é prosa, e
    # na camada a figurina do glifo se perde para o código da fonte.
    sem_ponto = nu.rstrip(".)]").replace("×", "x")
    if _ACENTOS_DE_FONTE.match(nu):
        return OUTRO
    sem_simbolos = "".join(c for c in sem_ponto if c not in _SIMBOLOS) or sem_ponto
    if (
        _FIGURINA.search(nu)
        or any(_LANCE.match(x) for x in (nu, sem_ponto, sem_simbolos))
        or _LANCE_COM_SINAL.match(sem_ponto)
        or _NUMERO_DE_LANCE.match(nu)
        or _AVALIACAO.match(nu)
        or _RESULTADO.match(nu)
        or _LONGA.match(nu)
        or _LONGA.match(sem_simbolos)
        or _LETRA_DE_PECA.match(nu)
        or _ROQUE.match(nu)
        or _CIRILICA.match(nu)
        or (
            _DESCRITIVA.match(sem_ponto)
            and (re.search(r"[0-9:\-]", sem_ponto) or re.search(r"[A-Z][xX][A-Z]", sem_ponto))
        )
    ):
        return NOTACAO
    return PROSA if any(c.isalpha() for c in nu) else OUTRO


def e_notacao(token: str) -> bool:
    return classe_do_token(token) == NOTACAO


def existe_na_camada(existe: Callable[[str], bool]) -> Callable[[str], bool]:
    """Na camada, **toda prosa existe**: é o que o editor escreveu, e o léxico não tem `arranca` nem `Gelfand`.

    O que não é confiável nela já chegou bloqueado: ligadura que perde letra e fonte de figurina.
    """

    def da_camada(token: str) -> bool:
        return classe_do_token(token) == PROSA or existe(token)

    return da_camada


def _distancia(a: str, b: str) -> float:
    """Levenshtein normalizado: 0 é igual, 1 é nada em comum."""
    if a == b:
        return 0.0
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1] / max(len(a), len(b))


def alinhar_tokens(g: Sequence[str], t: Sequence[str]) -> list[tuple[int, int]]:
    """Programação dinâmica de tokens: `(i, j)`, com `-1` no lado sem par. Custo de troca: a distância × 1,5."""
    n, m = len(g), len(t)
    custo = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        custo[i][0] = float(i)
    for j in range(1, m + 1):
        custo[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            custo[i][j] = min(
                custo[i - 1][j] + 1,
                custo[i][j - 1] + 1,
                custo[i - 1][j - 1] + _distancia(g[i - 1], t[j - 1]) * 1.5,
            )
    i, j = n, m
    pares: list[tuple[int, int]] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and custo[i][j] == custo[i - 1][j - 1] + _distancia(g[i - 1], t[j - 1]) * 1.5:
            pares.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and custo[i][j] == custo[i - 1][j] + 1:
            pares.append((i - 1, -1))
            i -= 1
        else:
            pares.append((-1, j - 1))
            j -= 1
    pares.reverse()
    return pares


def existe_no(lexico: Iterable[str]) -> Callable[[str], bool]:
    """A pergunta "esta palavra existe?" sobre um léxico em caixa baixa, mais as curtas daqui."""
    conjunto = lexico if isinstance(lexico, (set, frozenset)) else frozenset(lexico)

    def existe(token: str) -> bool:
        nu = token.strip(".,;:!?()[]'\"’“”")
        if not _PALAVRA.match(nu) or e_notacao(nu):
            return False
        chave = nu.casefold()
        return chave in conjunto or chave in CURTAS

    return existe


def _numero_partido(do_glifo: str, do_leitor: str) -> str:
    """O número do outro leitor, **só** se o do glifo é o fim dele: `7.` contra `17.`, e não `21.` contra `27.`."""
    mg, mt = _NUMERO.match(do_glifo), _NUMERO.match(do_leitor)
    if mg and mt and len(mt.group(1)) > len(mg.group(1)) and mt.group(1).endswith(mg.group(1)):
        return do_glifo[: mg.start(1)] + mt.group(1) + do_glifo[mg.end(1) :]
    return do_glifo


@dataclass(frozen=True)
class Token:
    """Um token da linha fundida, e de onde ele veio."""

    texto: str
    origem: OrigemDoToken
    do_glifo: str = ""
    """O que o glifo leu ali, quando teve par: a diferença é o sinal de discordância."""
    confianca: float | None = None
    """A confiança de **quem escreveu** o token, quando se sabe."""


def fundir(
    glifo: str,
    leitor: str,
    *,
    existe: Callable[[str], bool],
    confiancas_do_leitor: Sequence[float] = (),
    confiancas_do_glifo: Sequence[float | None] = (),
    bloqueados: Sequence[bool] = (),
    guarda_prosa_sem_par: bool = False,
) -> list[Token]:
    """A linha fundida, token a token. A regra v5 de 2026-10-30, escrita sobre `Token`.

    `bloqueados[j]` diz que o token `j` do outro leitor não é confiável (a camada com figurina em código
    de fonte, ou ligadura que perde letra): no par, fica o glifo; sem par, sai. `guarda_prosa_sem_par`
    é a regra 5 da S-721: o leitor que "não viu" não apaga texto. A camada é a tinta, e ali é `False`.
    """
    g, t = glifo.split(), leitor.split()
    saida: list[Token] = []
    confianca = {j: float(c) for j, c in enumerate(confiancas_do_leitor) if j < len(t)}

    def do_glifo(i: int) -> float | None:
        return confiancas_do_glifo[i] if i < len(confiancas_do_glifo) else None

    for i, j in alinhar_tokens(g, t):
        bloqueado = j != -1 and j < len(bloqueados) and bool(bloqueados[j])
        if i != -1 and j != -1:
            if _SO_FIO.match(t[j]) and any(c.isalnum() for c in g[i]):
                saida.append(Token(g[i], "glifo", g[i], do_glifo(i)))
            elif (
                not bloqueado
                and classe_do_token(g[i]) == PROSA
                and classe_do_token(t[j]) == PROSA
                and existe(g[i])
                and not existe(t[j])
            ):
                # Regra 4 da S-721: divergem, e só a versão do glifo é palavra que existe.
                saida.append(Token(g[i], "glifo", g[i], do_glifo(i)))
            elif bloqueado or ((e_notacao(g[i]) or e_notacao(t[j])) and not existe(t[j])):
                token = _numero_partido(g[i], t[j])
                # O dígito que o glifo deixou solto antes do número (`1 7.♔xf3`) é absorvido aqui.
                if token != g[i] and saida and saida[-1].texto.isdigit() and t[j].lstrip("(").startswith(saida[-1].texto):
                    saida.pop()
                # A palavra que o glifo colou no lance (`of2.exf6`), com o `of` já vindo do outro leitor.
                anterior = saida[-1].texto if saida and saida[-1].origem == "outro" else ""
                if anterior and token.startswith(anterior) and e_notacao(token[len(anterior) :]):
                    token = token[len(anterior) :]
                saida.append(Token(token, "glifo", g[i], do_glifo(i)))
            else:
                saida.append(Token(t[j], "outro", g[i], confianca.get(j)))
        elif i != -1:
            if e_notacao(g[i]) or g[i].isdigit() or guarda_prosa_sem_par:
                saida.append(Token(g[i], "glifo", g[i], do_glifo(i)))
        elif not e_notacao(t[j]) and not bloqueado and not _SO_FIO.match(t[j]):
            saida.append(Token(t[j], "outro", "", confianca.get(j)))
    return saida


def texto_fundido(tokens: Sequence[Token]) -> str:
    return " ".join(token.texto for token in tokens)


@dataclass(frozen=True)
class PalavraDaFolha:
    """Uma palavra lida na folha, com os sinais que a marca ranqueia."""

    linha: int
    token: int
    suspeita: float


FRACAO_MARCADA = 0.05
"""O teto da marca: no máximo 5% das palavras da folha, as mais suspeitas (G5)."""

_PESO_DISCORDANCIA = 1.0
_PESO_FORA_DO_LEXICO = 1.0
_CORTE_DE_CONFIANCA = 0.9


def suspeita_de(token: Token, *, existe: Callable[[str], bool]) -> float:
    """Quanto este token pede olho. **Só com a confiança de quem o escreveu**, e nunca a de outro motor.

    Prosa da camada não chega aqui (`e_da_camada` em `marcar`). Token do glifo só tem o sinal dele; token
    do outro leitor tem três: discordou do glifo, não existe no léxico, e a confiança dele mesmo.
    """
    suspeita = 0.0
    if token.confianca is not None and token.confianca < _CORTE_DE_CONFIANCA:
        suspeita += _CORTE_DE_CONFIANCA - token.confianca
    if token.origem == "glifo":
        return suspeita
    if classe_do_token(token.texto) != PROSA:
        return suspeita
    if token.do_glifo != token.texto:
        suspeita += _PESO_DISCORDANCIA
    if not existe(token.texto):
        suspeita += _PESO_FORA_DO_LEXICO
    return suspeita


def marcar(
    linhas: Sequence[Sequence[Token]],
    *,
    existe: Callable[[str], bool],
    e_da_camada: bool = False,
    fracao: float = FRACAO_MARCADA,
) -> list[frozenset[int]]:
    """Quais tokens de cada linha ficam marcados: os mais suspeitos, até o teto da folha.

    O teto conta **todas** as palavras da folha, e arredonda para baixo: folha de 19 palavras não marca
    nenhuma. Empate decide pela ordem de leitura, que é determinística. Devolve um conjunto por linha.
    """
    total = sum(len(linha) for linha in linhas)
    teto = int(total * fracao)
    candidatas: list[PalavraDaFolha] = []
    for n, linha in enumerate(linhas):
        for k, token in enumerate(linha):
            if e_da_camada and token.origem != "glifo":
                continue
            suspeita = suspeita_de(token, existe=existe)
            if suspeita > 0:
                candidatas.append(PalavraDaFolha(n, k, suspeita))
    candidatas.sort(key=lambda p: (-p.suspeita, p.linha, p.token))
    marcadas: list[set[int]] = [set() for _ in linhas]
    for palavra in candidatas[:teto]:
        marcadas[palavra.linha].add(palavra.token)
    return [frozenset(m) for m in marcadas]


def intervalos_de(tokens: Sequence[Token], marcados: Iterable[int]) -> tuple[tuple[int, int], ...]:
    """Os tokens marcados como intervalos `[início, fim)` no texto de `texto_fundido(tokens)`."""
    quais = set(marcados)
    saida: list[tuple[int, int]] = []
    posicao = 0
    for k, token in enumerate(tokens):
        if k in quais:
            saida.append((posicao, posicao + len(token.texto)))
        posicao += len(token.texto) + 1
    return tuple(saida)


__all__ = [
    "CURTAS",
    "FRACAO_MARCADA",
    "ClasseDoToken",
    "OrigemDoToken",
    "NOTACAO",
    "OUTRO",
    "PROSA",
    "PalavraDaFolha",
    "Token",
    "alinhar_tokens",
    "classe_do_token",
    "e_notacao",
    "existe_na_camada",
    "existe_no",
    "fundir",
    "intervalos_de",
    "marcar",
    "suspeita_de",
    "texto_fundido",
]
