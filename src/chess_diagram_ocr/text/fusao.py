"""A prosa de um leitor, a notação de outro: o roteador de tokens (S-716, S-717, S-718).

**Nenhum leitor é bom nas duas coisas.** O glifo foi treinado em livro de xadrez e é o único que vê
figurina; o Tesseract lê prosa de 2,7× a 11× melhor e estraga lance de peão (`g4!` -> `24!`). A camada de
um livro nascido digital **é** a tinta na prosa, e não representa figurina nenhuma. Medido em 2026-10-30 no
ouro digital: glifo 3,61% de CER de prosa, Tesseract 1,33%, fusão v5 1,25%, sem perder notação.

## As regras, na ordem: a v5, de quem nasceu digital (S-721)

1. Token de notação **em qualquer lado** -> glifo, salvo se o outro leitor leu ali uma palavra que existe
   (`the`, `with`, `Wissen`): o glifo vê `♔e` em `the`. **O lance inteiro do glifo não é vetado**: `♔a4` contra
   `Das`, `♕xe5` contra `fixes`, `♘xc4` contra `Axed`. O que o glifo inventa em palavra é figurina sem casa.
2. O número de lance do outro leitor só entra quando o glifo o **partiu** (`7.` contra `17.`). Do mesmo
   tamanho (`27.` contra `21.`), é erro do Tesseract, e fica o do glifo.
3. Prosa -> o outro leitor.
4. Divergem, e só a versão do glifo é palavra que existe: fica o glifo.
5. Sem par: notação e dígito do glifo ficam, e a prosa do glifo também, com a confiança mais baixa da linha: o
   leitor que "não viu" não apaga texto. Prosa do outro leitor entra.
6. Nada de "parece com": quem decide é a classe do token e o léxico, nunca a semelhança (regra da S-209).

## A v3, do scan e do ClearScan

No scan o Tesseract lê a notação em letra melhor que o glifo (`Lf1-d3`, `Kxf3`), e só a figurina continua sendo
de quem a vê. **Medida na prata, é por isso que a regra é por estrato.** (1) Token em que o glifo vê figurina ->
glifo, com a mesma ressalva da palavra que existe; (2) notação em letra -> outro leitor; (3) prosa -> outro leitor;
(5) e (6) como na v5. Quem escolhe entre as duas é `leitor.regra_da_folha`, pela admissão.

**A régua fica de fora.** O classificador de token daqui é próprio, e um teste de grafo de import trava
isso: o instrumento não pode compartilhar código com o medido, ou o erro de um vira o acerto do outro.

**As palavras funcionais curtas moram aqui.** `lexico.MIN_TAMANHO = 4` as deixa de fora do léxico, e
acrescentá-las lá mudaria `dicionario.corrigir` e a junção de hífen no caminho do glifo: desligar a fusão
não devolveria o glifo de antes.

## A marca por palavra (S-718, S-761)

Os sinais crus inundam: a discordância marca 10,0% das palavras no ouro e 27,7% na prata; o léxico sozinho,
26,8% e 40,1%. O teto da marca é 5%. Por isso os sinais **ranqueiam**. **Prosa que veio da camada não tem outro
leitor, e nunca é marcada.** Desde a S-761 a fusão marca pela probabilidade de erro de `text/confianca_palavra.py`
contra `CORTE_DE_REVISAR`, e `marcar`, o ranque por folha da S-718, fica com a camada, a reserva e o interruptor.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from . import lexico as _lexico
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
_LANCE_INTEIRO = re.compile(
    rf"^(?:\d+\.+\s*|\.\.\.|…)?[{_PECA}][a-h]?[1-8]?[xX:×]?[a-h][1-8](?:=?[{_PECA}])?[+#†‡✝!?]*$"
)
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
_PALAVRA = re.compile(r"^[^\W\d_]{2,}(?:['’-][^\W\d_]+)*$")
"""Qualquer alfabeto (S-723): até `ÿ`, `după` e o russo nunca existiam, com lista ou sem ela."""
_NUMERO = re.compile(r"^\(?(\d+)(?=\.)")
_SO_FIO = re.compile(r"^[|¦]+$")
"""O Tesseract lê `I` como `|`: 8 de 20 erros da fusão. Barra sozinha contra letra não é leitura melhor."""

CURTAS_POR_LINGUA: dict[str, frozenset[str]] = {
    "eng": frozenset(
        "a an and are as at be but by do for he her his i if in is it its me my no not of on or our she so the "
        "to up us was we who you".split()
    ),
    "por": frozenset("a ao aos as com da das de do dos e é em na nas no nos o os ou para por que se sem um uma à às".split()),
    "spa": frozenset("al el en es la las lo los y del con por que un una su sus".split()),
    "deu": frozenset("am an auf aus bei das dem den der des die ein er es im in ist mit nach nicht und von vor zu zum zur".split()),
    "fra": frozenset("au aux ce de des du en et il la le les ne on ou par pas que qui se un une".split()),
    "nld": frozenset("de een en het in is met niet op te van voor zijn".split()),
    "ron": frozenset("a al ale ca ce cu dar de din e ea el eu in la le lui mai ne nu o pe sa se si și un în".split()),
    "rus": frozenset("а в во да до ее её же за и из к как ко мы на не но о об он от по с со та те то ты у уж".split()),
}
"""As palavras curtas de cada língua, à mão: a lista da S-728 só tem de 4 letras para cima (S-723)."""

CURTAS = frozenset().union(*(CURTAS_POR_LINGUA[lingua] for lingua in ("eng", "por", "spa", "deu", "fra", "nld")))
"""Palavras que existem e o léxico compartilhado descarta. Privadas daqui: ver o cabeçalho.

As seis línguas de sempre, e é este o conjunto do léxico compartilhado: `existe_no` sem língua responde como antes."""

V5 = "v5"
V3 = "v3"
REGRAS = (V5, V3)
LANCE_INTEIRO_NAO_SE_VETA = True
"""O interruptor da exceção à regra 1 (S-721). Desligado, palavra que existe vence até lance inteiro."""

FIGURINA_FORA_DE_LANCE_PERDE = True
"""`nta♔`, `ge♔h1ich`: figurina que não forma lance. Contra palavra só de letras ou lance inteiro, ela perde, mesmo a
palavra estando fora do léxico: `ruinös` não está na lista do alemão, e `nta♔` não é lance em língua nenhuma. Conta como veto."""

MINIMO_DE_LETRAS_DA_PALAVRA = 4

SEM_PAR_NA_V3_SO_FIGURINA = True
"""Na v3, a notação em letra e o dígito são do outro leitor: `Sg1-f3` é um token nele e dois no glifo, e o `f3` a mais entrava."""

NUMERO_DO_GLIFO_NAO_SE_COLA = True
"""O `11` do glifo contra o `28711` ou o `Ea836` do Tesseract, que colou o lance no número: no *Minhas 60*, em cada linha de
lances, porque o glifo põe espaço depois da figurina. Fica o do glifo. Quando é o glifo que partiu (`1 3` e `13`), volta inteiro."""

RETICENCIA_DO_LEITOR = True
"""`6. . . ♕` no glifo e `6...` no leitor: a reticência partida volta inteira, e sem ela a notação perde dois caracteres por lance
de pretas. Sem o leitor ter visto a reticência, os pontos soltos do glifo ficam."""

LANCE_TORTO_NAO_ENTRA = True
"""O lance que o outro leitor estragou, sem par: `14...♕c6` contra `14...` e `Hc6`. O glifo já o leu, colado no número, e o
`Hc6` entraria como prosa ao lado dele: 14 de 22 erros de notação a mais numa folha do *Chess Evolution*."""

GUARDA_SO_O_QUE_EXISTE = True
"""A regra 5 guarda a **palavra** que o outro leitor não viu, e não qualquer coisa que o glifo escreveu."""

REGRA_4 = True
"""Divergem e só o glifo leu palavra: fica o glifo."""

PARENTESE_DO_NUMERO = True
"""`_keep_number_prefix` da suíte (S-707): o número que o glifo partiu volta com o parêntese que o outro leitor viu."""

LEXICO_POR_LINGUA = True
"""O interruptor da S-723: desligado, `existe_do_livro` responde pelo léxico compartilhado, como antes dela."""


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


def existe_no(lexico: Iterable[str], *, curtas: frozenset[str] = CURTAS) -> Callable[[str], bool]:
    """A pergunta "esta palavra existe?" sobre um léxico em caixa baixa, mais as curtas daqui."""
    conjunto = lexico if isinstance(lexico, (set, frozenset)) else frozenset(lexico)

    def existe(token: str) -> bool:
        nu = token.strip(".,;:!?()[]'\"’“”")
        if not _PALAVRA.match(nu) or e_notacao(nu):
            return False
        chave = _lexico.chave_do_lexico(nu)
        return chave in conjunto or chave in curtas

    return existe


def existe_do_livro(lingua: str, palavras_do_livro: Iterable[str] = ()) -> Callable[[str], bool]:
    """A pergunta "esta palavra existe?" na língua do livro (S-723). Sem lista dela, a do léxico compartilhado.

    **O que muda é só a metade da língua**: a lista da S-728 entra no lugar de `idioma`, que mistura oito, e as curtas
    da língua no lugar das de seis. O vocabulário do xadrez (`acervo`) e os nomes ficam, porque nenhuma lista do
    Tesseract conhece `zugzwang` nem `Nimzowitsch`.

    `palavras_do_livro` é o léxico do caderno (S-766): o nome que o dono corrigiu passa a existir nas folhas seguintes. Fora do conjunto
    grande, e não unido a ele: uma união de 350 mil entradas por folha é o custo errado para meia dúzia de nomes.
    """
    if LEXICO_POR_LINGUA:
        lista = _lexico.do_livro(lingua)
        base = existe_no(lista, curtas=CURTAS_POR_LINGUA.get(lingua, CURTAS)) if lista else existe_no(_lexico.carregar())
    else:
        base = existe_no(_lexico.carregar())
    extras = frozenset(_lexico.chave_do_lexico(p) for p in palavras_do_livro)
    return base if not extras else _com_as_do_livro(base, extras)


def _com_as_do_livro(base: Callable[[str], bool], extras: frozenset[str]) -> Callable[[str], bool]:
    do_livro = existe_no(extras, curtas=frozenset())

    def existe(token: str) -> bool:
        return base(token) or do_livro(token)

    return existe


def _numero_colado(do_glifo: str, do_leitor: str) -> bool:
    """O outro leitor grudou algo antes do número do glifo. Quatro dígitos ainda são folha (`66` e `1166`); cinco, não."""
    if not NUMERO_DO_GLIFO_NAO_SE_COLA or not do_glifo.isdigit() or do_leitor == do_glifo or not do_leitor.endswith(do_glifo):
        return False
    return not do_leitor.isdigit() or len(do_leitor) > 4


def _com_reticencia(token: str, do_leitor: str) -> str:
    """`6.` e `6...` dão `6...`: o número é o mesmo, e só o leitor viu os três pontos juntos."""
    if not RETICENCIA_DO_LEITOR:
        return token
    mt = _NUMERO_COM_RETICENCIA.match(do_leitor)
    mg = _NUMERO_SEM_RETICENCIA.match(token)
    if mt and mg and mt.group(1).lstrip("(") == mg.group(1).lstrip("("):
        return f"{mg.group(1)}...{token[mg.end():]}"
    return token


def _ponto_da_reticencia(token: str, saida: Sequence[Token]) -> bool:
    """O ponto solto do glifo que continua um número (`6. . .`), sem o leitor ter visto a reticência."""
    if not RETICENCIA_DO_LEITOR or not _SO_PONTOS.match(token):
        return False
    for anterior in reversed(saida):
        if not _SO_PONTOS.match(anterior.texto):
            return _NUMERO_SEM_RETICENCIA.match(anterior.texto) is not None and anterior.texto.endswith(".")
    return False


def _numero_partido(do_glifo: str, do_leitor: str) -> str:
    """O número do outro leitor, **só** se o do glifo é o fim dele: `7.` contra `17.`, e não `21.` contra `27.`.

    Com o parêntese que só o outro leitor viu (`(17...Ae5` e `7...♘e5` dão `(17...♘e5`).
    """
    mg, mt = _NUMERO.match(do_glifo), _NUMERO.match(do_leitor)
    if mg and mt and len(mt.group(1)) > len(mg.group(1)) and mt.group(1).endswith(mg.group(1)):
        abre = "(" if PARENTESE_DO_NUMERO and do_leitor.startswith("(") and not do_glifo.startswith("(") else ""
        return abre + do_glifo[: mg.start(1)] + mt.group(1) + do_glifo[mg.end(1) :]
    return do_glifo


_PROMOCAO_COM_FIGURINA = re.compile(r"^(?:\d+\.+)?(?:[a-h]x)?[a-h][18]=?[♔-♟][+#†‡!?]*$")
_NUMERO_COM_RETICENCIA = re.compile(r"^(\(?\d+)\.{3}")
_NUMERO_SEM_RETICENCIA = re.compile(r"^(\(?\d+)\.{1,2}(?!\.)")
_SO_PONTOS = re.compile(r"^\.{1,3}$")
_SO_SINAL = re.compile(r"^[!?+#]+$")
_LANCE_TORTO = re.compile(r"^(?:[&€£¢§¥$@%©®]x?[a-h][1-8lI|]|[A-JM-PR-Zi-z]x?[a-h][1-8])$")


def _e_lance_torto(token: str) -> bool:
    nu = token.strip("()[],;:.!?+#")
    return LANCE_TORTO_NAO_ENTRA and _LANCE_TORTO.match(nu) is not None and not e_lance_inteiro(nu)


def _veto_por_letras(token: str) -> bool:
    return _PALAVRA.match(token.strip(".,;:!?()[]'\"’“”")) is not None and not e_notacao(token)


OUVINTE_DE_VETOS: Callable[[str, str], None] | None = None
"""Quem quer saber dos vetos, para contá-los à parte na G1(a): a bancada liga, o produto não. Recebe a leitura do glifo e a
palavra que a venceu."""


def e_lance_inteiro(token: str) -> bool:
    """`♔a4`, `♕xe5,` ou `Nf3!`: peça e casa, com ou sem número. O que o glifo inventa em palavra não tem casa (`♔e`, `wi♔`)."""
    nu = token.strip("()[]{},;:\"'").rstrip(".)]")
    return _LANCE_INTEIRO.match(nu) is not None


def _palavra_veta(do_glifo: str, do_leitor: str, existe: Callable[[str], bool], da_camada: bool = False) -> bool:
    """A palavra do outro leitor vence a notação do glifo? Regra 1, com a exceção do lance inteiro."""
    if _figurina_perde(do_glifo, do_leitor):
        return True
    if not existe(do_leitor):
        return False
    return da_camada or not (LANCE_INTEIRO_NAO_SE_VETA and e_lance_inteiro(do_glifo))


def _figurina_fora_de_lance(token: str) -> bool:
    """Tem figurina, tem letra ou dígito, e não é lance: nem peça e casa, nem promoção, nem o `W♔d5` do enunciado."""
    nu = token.strip("()[]{},;:\"'").rstrip(".)]").lstrip("△□")
    if not _FIGURINA.search(nu) or e_lance_inteiro(nu) or _PROMOCAO_COM_FIGURINA.match(nu) or e_lance_inteiro(nu[1:]):
        return False
    return any(c.isalnum() and not _FIGURINA.match(c) for c in nu)


def _figurina_perde(do_glifo: str, do_leitor: str) -> bool:
    """Palavra de **quatro letras ou mais**: o `acl` de `♖ac1` e o `Wc]` de `♕c` são o lance estragado, e não palavra."""
    if not (FIGURINA_FORA_DE_LANCE_PERDE and _figurina_fora_de_lance(do_glifo)):
        return False
    letras = sum(c.isalpha() for c in do_leitor)
    return (letras >= MINIMO_DE_LETRAS_DA_PALAVRA and _veto_por_letras(do_leitor)) or e_lance_inteiro(do_leitor)


@dataclass(frozen=True)
class Token:
    """Um token da linha fundida, e de onde ele veio."""

    texto: str
    origem: OrigemDoToken
    do_glifo: str = ""
    """O que o glifo leu ali, quando teve par: a diferença é o sinal de discordância."""
    confianca: float | None = None
    """A confiança de **quem escreveu** o token, quando se sabe."""
    do_leitor: str = ""
    """O que o outro leitor leu ali, quando teve par. É a segunda leitura que o árbitro da S-729 pesa."""


def fundir(
    glifo: str,
    leitor: str,
    *,
    existe: Callable[[str], bool],
    confiancas_do_leitor: Sequence[float] = (),
    confiancas_do_glifo: Sequence[float | None] = (),
    bloqueados: Sequence[bool] = (),
    guarda_prosa_sem_par: bool = False,
    regra: str = V5,
    da_camada: bool = False,
) -> list[Token]:
    """A linha fundida, token a token: a regra v5 ou a v3 (ver o cabeçalho), escrita sobre `Token`.

    `bloqueados[j]` diz que o token `j` do outro leitor não é confiável (a camada com figurina em código
    de fonte, ou ligadura que perde letra): no par, fica o glifo; sem par, sai. `guarda_prosa_sem_par`
    é a regra 5 da S-721: o leitor que "não viu" não apaga texto. A camada é a tinta, e ali é `False`.
    `da_camada` diz que o outro leitor é a camada: o que ela escreve vence mesmo um lance inteiro do glifo, porque o
    `♘e1` em cima de `Gelfand` é o glifo errando.
    """
    g, t = glifo.split(), leitor.split()
    confianca = _confiancas_por_token(confiancas_do_leitor, t, leitor)
    saida: list[Token] = []
    menor_da_linha = min((c for c in confiancas_do_glifo if c is not None), default=None)

    def do_glifo(i: int) -> float | None:
        return confiancas_do_glifo[i] if i < len(confiancas_do_glifo) else None

    for i, j in alinhar_tokens(g, t):
        bloqueado = _bloqueado(bloqueados, j)
        if i != -1 and j != -1:
            if _numero_colado(g[i], t[j]) or (_SO_FIO.match(t[j]) and any(c.isalnum() for c in g[i])):
                saida.append(Token(g[i], "glifo", g[i], do_glifo(i), t[j]))
            elif NUMERO_DO_GLIFO_NAO_SE_COLA and g[i].isdigit() and saida and saida[-1].texto.isdigit() and t[j] == saida[-1].texto + g[i]:
                saida[-1] = Token(t[j], "outro", saida[-1].texto + g[i], confianca.get(j), t[j])
            elif regra == V3 and not bloqueado and not _FIGURINA.search(g[i]):
                # Notação em letra e prosa: no scan, as duas são do outro leitor. Sem figurina, não há veto a pesar.
                saida.append(Token(t[j], "outro", g[i], confianca.get(j), t[j]))
            elif regra == V3 and not bloqueado and _palavra_veta(g[i], t[j], existe, da_camada):
                if OUVINTE_DE_VETOS is not None:
                    OUVINTE_DE_VETOS(g[i], t[j])
                saida.append(Token(t[j], "outro", g[i], confianca.get(j), t[j]))
            elif (
                REGRA_4
                and not bloqueado
                and classe_do_token(g[i]) == PROSA
                and classe_do_token(t[j]) == PROSA
                and existe(g[i])
                and not existe(t[j])
            ):
                # Regra 4 da S-721: divergem, e só a versão do glifo é palavra que existe.
                saida.append(Token(g[i], "glifo", g[i], do_glifo(i), t[j]))
            elif bloqueado or ((e_notacao(g[i]) or e_notacao(t[j])) and not _palavra_veta(g[i], t[j], existe, da_camada)):
                token = _com_reticencia(_numero_partido(g[i], t[j]), t[j])
                # O dígito que o glifo deixou solto antes do número (`1 7.♔xf3`) é absorvido aqui.
                if token != g[i] and saida and saida[-1].texto.isdigit() and t[j].lstrip("(").startswith(saida[-1].texto):
                    saida.pop()
                # A palavra que o glifo colou no lance (`of2.exf6`), com o `of` já vindo do outro leitor. Só palavra:
                # o `..` de `.. Hf5` também vem de lá, e tirá-lo de `...♕f5` deixaria um ponto solto.
                anterior = saida[-1].texto if saida and saida[-1].origem == "outro" else ""
                if anterior and any(c.isalpha() for c in anterior) and token.startswith(anterior) and e_notacao(token[len(anterior) :]):
                    token = token[len(anterior) :]
                saida.append(Token(token, "glifo", g[i], do_glifo(i), t[j]))
            else:
                if _FIGURINA.search(g[i]) and OUVINTE_DE_VETOS is not None:
                    OUVINTE_DE_VETOS(g[i], t[j])
                saida.append(Token(t[j], "outro", g[i], confianca.get(j), t[j]))
        elif i != -1:
            anterior = saida[-1].texto if saida else ""
            if _SO_SINAL.match(g[i]) and anterior.endswith(g[i]):
                # `ideal !` no glifo e `ideal!` no leitor: o sinal já veio.
                continue
            if RETICENCIA_DO_LEITOR and _SO_PONTOS.match(g[i]) and anterior.endswith("..."):
                continue
            if (
                _FIGURINA.search(g[i])
                # **Linha que o leitor leu vazia não tem o que oferecer**: lá ele não viu, e o glifo fica com o que é dele.
                if regra == V3 and SEM_PAR_NA_V3_SO_FIGURINA and t
                else (e_notacao(g[i]) or g[i].isdigit() or _ponto_da_reticencia(g[i], saida))
            ):
                saida.append(Token(g[i], "glifo", g[i], do_glifo(i)))
            elif guarda_prosa_sem_par and (existe(g[i]) or not GUARDA_SO_O_QUE_EXISTE):
                saida.append(Token(g[i], "glifo", g[i], menor_da_linha))
        elif bloqueado or _SO_FIO.match(t[j]) or _e_lance_torto(t[j]):
            continue
        elif regra == V3 or not e_notacao(t[j]):
            saida.append(Token(t[j], "outro", "", confianca.get(j)))
    return saida


def _confiancas_por_token(confiancas: Sequence[float], tokens: Sequence[str], leitor: str) -> dict[int, float]:
    """A confiança de cada token do outro leitor, por índice. Vazia quando ele não deu confiança nenhuma."""
    if confiancas and len(confiancas) != len(tokens):
        # Truncar aqui deslocava a confiança em silêncio: a palavra com U+2009 dentro vira dois tokens (S-853).
        raise ValueError(f"{len(confiancas)} confianças para {len(tokens)} tokens do leitor: {leitor!r}")
    return {j: float(c) for j, c in enumerate(confiancas)}


def _bloqueado(bloqueados: Sequence[bool], j: int) -> bool:
    """O token `j` do outro leitor veio marcado como não confiável. `-1` (sem token do leitor) não está."""
    return j != -1 and j < len(bloqueados) and bool(bloqueados[j])


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


CORTE_DE_REVISAR: dict[str, float] = {V5: 0.01621, V3: 0.1793}
"""Da probabilidade de erro para cima, a palavra pede olho (S-761), por estrato. **É o corte da fusão, e de mais ninguém**: o `corte_de_revisar`
de `documento.py` é o `ocr.MIN_CONFIDENCE`, que o `pdf_pesquisavel` e a `coleta` usam e que está no digest da S-218. Sai de `ajustar.py`: é o que
marca 5% das palavras no pedaço reservado do dev."""


def marcar_por_erro(erros: Sequence[Sequence[float]], corte: float) -> list[frozenset[int]]:
    """Quais tokens de cada linha passam do corte. **Sem teto por folha, e é medido:** a folha limpa não gasta marca, e a ruim recebe as que
    precisa. Com o teto de 5% por folha, a captura na prata fica em 35%; com o mesmo calibrador e o corte, em 56%, marcando 6,0%."""
    return [frozenset(k for k, p in enumerate(linha) if p >= corte) for linha in erros]


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
    "CORTE_DE_REVISAR",
    "CURTAS",
    "FRACAO_MARCADA",
    "LANCE_INTEIRO_NAO_SE_VETA",
    "OUVINTE_DE_VETOS",
    "REGRAS",
    "V3",
    "V5",
    "e_lance_inteiro",
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
    "existe_do_livro",
    "existe_na_camada",
    "existe_no",
    "fundir",
    "intervalos_de",
    "marcar",
    "marcar_por_erro",
    "suspeita_de",
    "texto_fundido",
]
