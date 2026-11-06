"""A régua da prosa: quanto um leitor erra no texto que não é lance nem avaliação (S-700, S-701).

**Todo erro caro deste subsistema foi de régua, e não de código.** A régua antiga media a página inteira,
prosa e notação misturadas, e penalizava o glifo onde ele acerta. Esta separa as classes **token a token,
na referência**, conta o erro de cada caractere na classe do caractere da referência, e não faz I/O nenhum:
quem lê o PDF é o `cli/texto_prosa.py`.

**Inclusiva na notação, de propósito, e o contrário do `text/notacao.fatiar`.** Prosa contada como notação só
sai do placar; notação contada como prosa envenena a prosa de todos os motores. O `fatiar` é conservador
porque no PGN o erro caro é prosa virar lance (S-208). São duas funções, e nenhuma serve no lugar da outra.

**Não importa `text/fusao.py`, nem é importada por ele.** O instrumento não pode dividir código com o medido:
o erro de um viraria o acerto do outro. A semelhança dos dois classificadores é de origem, o protótipo
`docs/metrics/texto_prosa_2026-10-30/banco.py`, e cada um segue a sua pergunta.

**A letra de peça por língua só acrescenta.** A letra solta conta como notação se é peça em **alguma** das
línguas de alfabeto latino (`B`, `D`, `T`, `C`... em qualquer livro: o *Capablanca* em português põe a figurina
num token próprio), e a língua do livro acrescenta o que só vale nela (`P` em holandês, `Ф` e `Л` em russo).
Restringir à língua do livro tiraria da notação o `Q` de um livro em português que cita em inglês. `A` solto é
prosa até em espanhol, onde também é o bispo: lá ele é quase sempre a preposição. No começo de um lance ele
continua peça (`Ae4`).

**`ruido` é a classe do que nenhuma língua escreve.** O lixo de figurina da camada de terceiro (`.l:tb1`,
`'ii'xa4`, `Wxf7`, `tlld7+`) e a letra solta de fonte de diagrama (`ç`, `æ+`) não são prosa nem notação, e não
podem contar como nenhuma das duas. Nos livros do ouro a admissão já os recusa; na prata eles existem.

**Como usar sobre um motor novo:** `pontuar(normalizar(ref, "tip", lingua), normalizar(hip, "tip", lingua),
lingua)`, com `ref` montada por `referencia_da_pagina` a partir de `ler_pagina(motor="camada")`. Medir fora
dessa montagem mede a ordem das colunas, e não a leitura (CER 0,999 numa folha que tinha 0,051).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

VERSAO_CLASSIFICADOR = "s701-2026-11-06"
"""Vai em todo relatório: trocar o classificador muda o número publicado (S-701)."""

PROSA = "prosa"
NOTACAO = "notacao"
OUTRO = "outro"
RUIDO = "ruido"
ESPACO = "espaco"
CLASSES = (PROSA, NOTACAO, OUTRO, RUIDO, ESPACO)

TIP = "tip"
CRU = "cru"
MODOS = (TIP, CRU)

LINGUA_PADRAO = "eng"

LETRAS_DE_PECA: dict[str, tuple[str, str, str, str, str]] = {
    "eng": ("K", "Q", "R", "B", "N"),
    "por": ("R", "D", "T", "B", "C"),
    "spa": ("R", "D", "T", "A", "C"),
    "deu": ("K", "D", "T", "L", "S"),
    "fra": ("R", "D", "T", "F", "C"),
    "nld": ("K", "D", "T", "L", "P"),
    "ron": ("R", "D", "T", "N", "C"),
    "rus": ("Кр", "Ф", "Л", "С", "К"),
}
"""Rei, dama, torre, bispo e cavalo em cada língua do acervo, com o código de três letras do Tesseract."""

_APELIDOS = {"en": "eng", "pt": "por", "es": "spa", "de": "deu", "fr": "fra", "nl": "nld", "ro": "ron", "ru": "rus"}

_TIPOGRAFIA = {
    "’": "'", "‘": "'", "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "–": "-", "—": "-", "−": "-", "…": "...", " ": " ", "ﬁ": "fi", "ﬂ": "fl",
    "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "­": "", "‐": "-", "‑": "-", "ʼ": "'",
    "´": "'", "`": "'",
}
_HIFEN_DE_FIM_DE_LINHA = re.compile(r"(?<=\w)-\n(?=\w)")


def lingua_da_regua(lingua: str) -> str:
    """O código de três letras: aceita `por`, `pt` e a soma do Tesseract (`eng+por`, a primeira manda)."""
    primeira = lingua.split("+")[0].strip().lower()
    return _APELIDOS.get(primeira, primeira)


def normalizar(texto: str, modo: str = TIP, lingua: str = LINGUA_PADRAO) -> str:
    """Aplicada igual aos dois lados. `cru`: NFC, hífen de fim de linha juntado, espaços colapsados.

    `tip`, a das metas, ainda troca aspas, travessões, ligaduras e espaço fino por ASCII, e a figurina pela letra
    da língua, com o peão sumindo. A família de pontuação (`—` contra `-`) só existe em `cru`.

    Toda quebra vira `\\n`. O stdout do Tesseract no Windows vem em CRLF, e o protótipo pagava um erro por linha só por
    isso: era quase todo o erro do `tess_pagina` publicado em 2026-10-30.

    O espaço colapsa **antes** de o hífen juntar, e o hífen não consome as letras em volta. O protótipo fazia o
    contrário, e `a-\\n\\nb` e `a-\\nb-\\nc` precisavam de duas passadas: a normalização não era idempotente.
    """
    if modo not in MODOS:
        raise ValueError(f"modo de normalização desconhecido: {modo!r}")
    t = unicodedata.normalize("NFC", texto)
    if modo == TIP:
        t = "".join(_TIPOGRAFIA.get(c, c) for c in t)
        rei, dama, torre, bispo, cavalo = LETRAS_DE_PECA.get(lingua_da_regua(lingua), LETRAS_DE_PECA[LINGUA_PADRAO])
        figurinas = {"♔": rei, "♚": rei, "♕": dama, "♛": dama, "♖": torre, "♜": torre, "♗": bispo, "♝": bispo,
                     "♘": cavalo, "♞": cavalo, "♙": "", "♟": ""}
        t = "".join(figurinas.get(c, c) for c in t)
        t = unicodedata.normalize("NFC", t)
    t = re.sub(r"\r\n?|[\f\v]", "\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n+", "\n", t)
    t = _HIFEN_DE_FIM_DE_LINHA.sub("", t)
    return t.strip()


# ------------------------------------------------------------------------------------- classes de token

_PECA = "KQRBNDTCSLFAP♔♕♖♗♘♙♚♛♜♝♞♟"
_NUMERO_DE_LANCE_NA_FRENTE = r"(?:\d+\.+|\d+…|\.\.\.|…)"
_CASA = rf"[a-h]?[1-8]?[xX:×]?[a-h][1-8](?:=?[{_PECA}])?"
_LANCE = re.compile(
    rf"^{_NUMERO_DE_LANCE_NA_FRENTE}?([{_PECA}]?{_CASA}:?|O-O(-O)?|0-0(-0)?)"
    r"(e\.p\.)?[+#†‡t]*[!?]*[=+\-–—±∓∞⩲⩱]*$"
)
_LANCE_COM_SINAL = re.compile(
    rf"^{_NUMERO_DE_LANCE_NA_FRENTE}?[{_PECA}]?{_CASA}[+#†‡!?]*[-²³°][+#†‡!?]*$"
    rf"|^(?:{_NUMERO_DE_LANCE_NA_FRENTE}[{_PECA}]?|[{_PECA}]){_CASA}[+#†‡!?]*[a-z][+#†‡!?]*$"
)
"""A camada escreve o sinal em código de fonte: `19.Bd3\\uf0b1`, `Rfc1²`, `Rxg5i`, `24...f4e`. A letra solta só conta
com peça ou número de lance na frente: `f4e` sozinho não é lance."""
_LANCE_NUMERADO_NO_COMECO = re.compile(rf"^\d+(?:\.+|…)[{_PECA}]?[a-h]?[1-8]?[xX:×]?[a-h][1-8]")
"""`31.Bxg6fxg632.Qf4Rb733.Rxb7` é a camada que não escreveu o espaço. Com o número na frente, não é palavra."""
_NUMERO_E_PECA = re.compile(rf"^\d+(?:\.+|…)[{_PECA}]$")
"""`1...B`: o resto do lance veio em outro token, a figurina que a camada separou."""
_NUMERO_DE_LANCE = re.compile(r"^\d+\.+$|^\d+…$")
_AVALIACAO = re.compile(r"^([+\-=±∓⩲⩱∞!?#†□△⌓→↑⇆○●N]|\+/-|-/\+|\+-|-\+|=/\+|\+/=|=/∞)+$")
_RESULTADO = re.compile(r"^(1[-–—]0|0[-–—]1|½[-–—]½|1/2[-–—]1/2|\*)$")
_FIGURINA = re.compile(r"[♔-♟]")
_SIMBOLOS = "ʘ⊕⊞⨀□△▲▼○●↑→←⇆⇄∆∇⌓⩲⩱±∓∞#†‡"
"""Os sinais do Informator como cada fonte os codifica (o *Kravtsiv* usa `ʘ`, que para o Unicode é letra)."""
_DESCRITIVA = re.compile(
    r"^(\d+\.+)?[KQRBNPTDACS]{1,3}[1-8]?(-|[xX:])?[KQRBNPTDACS]{0,3}[1-8]?[a-z]{0,2}(ch|mate|\+|#|!|\?)*$"
)
_CIRILICA = re.compile(r"^(\d+\.+)?(Кр|[КФЛС])?[a-hаеЬсd]?[1-8]?[:xх]?[a-hаеЬсd][1-8][+#!?]*$")
"""Com âncora no fim: sem ela, `af7anca` (a camada do *Hertan* sem o espaço) era lance."""
_FONTE_DE_DIAGRAMA = re.compile(r"^[^A-Za-z]*[À-ÿ]{3,}[^A-Za-z]*$")
_LONGA = re.compile(rf"^(\d+\.+)?[{_PECA}]?[a-h]?[1-8][-x×:–—][{_PECA}]?[a-h][1-8]")
_CAPTURA_COM_CRUZ = re.compile(r"×[a-h][1-8]")
"""`×` nenhuma língua escreve em palavra: `97×f6` é o lance que a camada estragou, e não prosa."""
_ROQUE = re.compile(r"^(\d+\.+)?(O-O(-O)?|0-0(-0)?|O–O(–O)?|0–0(–0)?)")
_LETRAS_SOLTAS_LATINAS = frozenset("KQRBNDTCSLF")
_LETRAS_DE_PECA_NO_PLACAR = frozenset("KQRBNDTCSLFP")

_LIXO_DE_FIGURINA = re.compile(r"l:l'|'ii'|\.tg|l:!")
_TERMINA_NUMA_CASA = re.compile(r"^(.+?)[a-h][1-8](?:=?\w)?[+#!?,.;:)\]…]*$")
_SO_LETRAS = re.compile(r"^[^\W\d_]{3,}-?$")
_VOGAL = re.compile(r"[aeiouyàáâãäéêëíîïóôõöúûüAEIOUYÀÁÂÃÄÉÊÍÓÔÕÖÚÜаеёиоуыэюяАЕЁИОУЫЭЮЯ]")
_LETRA_DE_FONTE = re.compile(r"^[çæœßðþøÇÆŒÐÞØ][^\w]*$")
_LETRA_ENTRE_SINAIS = re.compile(r"^[=+\-]+[^\W\d_][=+\-]+$")
_FILEIRA_NUM_TOKEN = re.compile(r"^(?:abcdefgh|ABCDEFGH|hgfedcba|12345678|87654321)$")


def _e_ruido(cru: str, nu: str) -> bool:
    """O lixo de figurina: o que termina numa casa, e o que vem antes da casa não é peça nem palavra."""
    if _LIXO_DE_FIGURINA.search(cru) or _LETRA_DE_FONTE.match(nu) or _LETRA_ENTRE_SINAIS.match(nu):
        return True
    casa = _TERMINA_NUMA_CASA.match(nu)
    if casa is None:
        return False
    antes = casa.group(1)
    # `peão-g6` termina numa casa e é prosa: o que vem antes é uma palavra. `tll` e `lll` não têm vogal.
    return not (_SO_LETRAS.match(antes) and _VOGAL.search(antes))


def classe_do_token(token: str, lingua: str = LINGUA_PADRAO) -> str:
    """`prosa`, `notacao`, `outro` ou `ruido`. Ver o cabeçalho."""
    nu = token.strip("()[]{},;:\"'")
    if not nu:
        return OUTRO
    sem_ponto = nu.rstrip(".)]").replace("×", "x")
    if _FONTE_DE_DIAGRAMA.match(nu):
        return OUTRO
    sem_simbolos = "".join(c for c in sem_ponto if c not in _SIMBOLOS) or sem_ponto
    if (
        _FIGURINA.search(nu)
        or any(_LANCE.match(x) for x in (nu, sem_ponto, sem_simbolos))
        or _LANCE_COM_SINAL.match(sem_ponto)
        or _LANCE_NUMERADO_NO_COMECO.match(nu)
        or _NUMERO_E_PECA.match(sem_ponto)
        or _NUMERO_DE_LANCE.match(nu)
        or _AVALIACAO.match(nu)
        or _RESULTADO.match(nu)
        or _LONGA.match(nu)
        or _LONGA.match(sem_simbolos)
        or _CAPTURA_COM_CRUZ.search(nu)
        or _e_letra_de_peca(nu, lingua)
        or _ROQUE.match(nu)
        or _CIRILICA.match(sem_ponto)
        or (
            _DESCRITIVA.match(sem_ponto)
            and (re.search(r"[0-9:\-]", sem_ponto) or re.search(r"[A-Z][xX][A-Z]", sem_ponto))
        )
    ):
        return NOTACAO
    if not any(c.isalpha() for c in nu):
        return OUTRO
    if _FILEIRA_NUM_TOKEN.match(nu):
        return OUTRO
    if _e_ruido(token, nu):
        return RUIDO
    return PROSA


def _e_letra_de_peca(nu: str, lingua: str) -> bool:
    if nu in _LETRAS_SOLTAS_LATINAS:
        return True
    pecas = LETRAS_DE_PECA.get(lingua_da_regua(lingua), ())
    # `A` solto continua prosa em espanhol: ver o cabeçalho.
    return nu in pecas and nu != "A"


def _e_linha_de_coordenadas(linha: str) -> bool:
    """A fileira de coordenadas em tokens soltos (`a b c d e f g h`, `è é ê ë`): quatro ou mais, todos diferentes."""
    tokens = linha.split()
    if len(tokens) < 4 or len(set(tokens)) != len(tokens):
        return False
    return all(len(t) == 1 and (t in "abcdefgh12345678" or "À" <= t <= "ÿ") for t in tokens)


Classificador = Callable[[str], str]


def classes_por_char(ref: str, lingua: str = LINGUA_PADRAO, *, classificar: Classificador | None = None) -> list[str]:
    """A classe de cada caractere. O separador **entre dois tokens de prosa** é prosa: `if the`->`ifthe` custa.

    `classificar`, quando vem, troca o classificador e desliga a regra da linha de coordenadas: é para provar a
    paridade com o protótipo, e para medir o efeito de um classificador novo, sem rodar motor nenhum.
    """
    classe = classificar if classificar is not None else (lambda t: classe_do_token(t, lingua))
    classes = [ESPACO] * len(ref)
    tokens = list(re.finditer(r"\S+", ref))
    fora = _trechos_de_coordenadas(ref) if classificar is None else []
    for m in tokens:
        c = OUTRO if any(a <= m.start() < b for a, b in fora) else classe(m.group())
        for i in range(m.start(), m.end()):
            classes[i] = c
    for a, b in zip(tokens, tokens[1:], strict=False):
        if classes[a.start()] == PROSA and classes[b.start()] == PROSA:
            for i in range(a.end(), b.start()):
                classes[i] = PROSA
    return classes


def _trechos_de_coordenadas(texto: str) -> list[tuple[int, int]]:
    trechos = []
    inicio = 0
    for linha in texto.split("\n"):
        if _e_linha_de_coordenadas(linha):
            trechos.append((inicio, inicio + len(linha)))
        inicio += len(linha) + 1
    return trechos


def _classes_dos_tokens(texto: str, lingua: str, classificar: Classificador | None) -> tuple[list[str], list[str]]:
    classes = classes_por_char(texto, lingua, classificar=classificar)
    achados = list(re.finditer(r"\S+", texto))
    return [m.group() for m in achados], [classes[m.start()] for m in achados]


# ------------------------------------------------------------------------------------------- alinhamento


def _matriz(av: np.ndarray, bv: np.ndarray) -> np.ndarray:
    """A matriz de Levenshtein, vetorizada por linha: o mínimo acumulado resolve a inserção."""
    n, m = len(av), len(bv)
    d = np.empty((n + 1, m + 1), dtype=np.int32)
    d[0] = np.arange(m + 1)
    eixo = np.arange(m + 1, dtype=np.int32)
    for i in range(1, n + 1):
        anterior = d[i - 1]
        custo = (bv != av[i - 1]).astype(np.int32)
        x = np.empty(m + 1, dtype=np.int32)
        x[0] = i
        x[1:] = np.minimum(anterior[1:] + 1, anterior[:-1] + custo)
        d[i] = np.minimum.accumulate(x - eixo) + eixo
    return d


def alinhar(ref: str, hip: str) -> list[tuple[int, int]]:
    """Levenshtein de caractere com recuo: pares `(i, j)`, com `-1` no lado sem par."""
    n, m = len(ref), len(hip)
    if n == 0:
        return [(-1, j) for j in range(m)]
    if m == 0:
        return [(i, -1) for i in range(n)]
    d = _matriz(
        np.frombuffer(ref.encode("utf-32-le", "surrogatepass"), dtype=np.uint32),
        np.frombuffer(hip.encode("utf-32-le", "surrogatepass"), dtype=np.uint32),
    )
    i, j = n, m
    pares: list[tuple[int, int]] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + (ref[i - 1] != hip[j - 1]):
            pares.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and d[i, j] == d[i - 1, j] + 1:
            pares.append((i - 1, -1))
            i -= 1
        else:
            pares.append((-1, j - 1))
            j -= 1
    pares.reverse()
    return pares


def _wer_por_token(ref: str, hip: str, lingua: str, classificar: Classificador | None) -> dict[str, int]:
    """S+D+I sobre alinhamento de tokens, casamento exato: S e D contam prosa da referência, I conta prosa inserida."""
    r, cr = _classes_dos_tokens(ref, lingua, classificar)
    h, ch = _classes_dos_tokens(hip, lingua, classificar)
    total = sum(c == PROSA for c in cr)
    if not r or not h:
        return {"s": 0, "d": total, "i": sum(c == PROSA for c in ch), "n": total}
    ids: dict[str, int] = {}
    rv = np.array([ids.setdefault(x, len(ids)) for x in r], dtype=np.uint32)
    hv = np.array([ids.setdefault(x, len(ids)) for x in h], dtype=np.uint32)
    d = _matriz(rv, hv)
    i, j = len(r), len(h)
    s = apagadas = inseridas = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + (r[i - 1] != h[j - 1]):
            s += r[i - 1] != h[j - 1] and cr[i - 1] == PROSA
            i -= 1
            j -= 1
        elif i > 0 and d[i, j] == d[i - 1, j] + 1:
            apagadas += cr[i - 1] == PROSA
            i -= 1
        else:
            inseridas += ch[j - 1] == PROSA
            j -= 1
    return {"s": int(s), "d": int(apagadas), "i": int(inseridas), "n": total}


# ------------------------------------------------------------------------------------------------ placar


def _por_classe() -> dict[str, int]:
    return dict.fromkeys(CLASSES, 0)


@dataclass
class Placar:
    """Por classe, erros e totais; inserções à parte; WER (S+D+I)/N; figurina; e as trocas palavra a palavra."""

    erros: dict[str, int] = field(default_factory=_por_classe)
    total: dict[str, int] = field(default_factory=_por_classe)
    palavras_prosa: int = 0
    palavras_prosa_certas: int = 0
    trocas: dict[str, int] = field(default_factory=dict)
    insercoes: int = 0
    insercoes_por_classe: dict[str, int] = field(default_factory=dict)
    wer_s: int = 0
    wer_d: int = 0
    wer_i: int = 0
    wer_n: int = 0
    fig_ref: int = 0
    fig_hip: int = 0
    fig_tp: int = 0

    def somar(self, outro: Placar) -> None:
        for classe in CLASSES:
            self.erros[classe] += outro.erros[classe]
            self.total[classe] += outro.total[classe]
        self.palavras_prosa += outro.palavras_prosa
        self.palavras_prosa_certas += outro.palavras_prosa_certas
        for k, v in outro.trocas.items():
            self.trocas[k] = self.trocas.get(k, 0) + v
        self.insercoes += outro.insercoes
        for k, v in outro.insercoes_por_classe.items():
            self.insercoes_por_classe[k] = self.insercoes_por_classe.get(k, 0) + v
        self.wer_s += outro.wer_s
        self.wer_d += outro.wer_d
        self.wer_i += outro.wer_i
        self.wer_n += outro.wer_n
        self.fig_ref += outro.fig_ref
        self.fig_hip += outro.fig_hip
        self.fig_tp += outro.fig_tp

    def cer(self, classe: str = PROSA) -> float:
        return self.erros[classe] / max(1, self.total[classe])

    def wer_prosa(self) -> float:
        return (self.wer_s + self.wer_d + self.wer_i) / max(1, self.wer_n)

    def para_dict(self) -> dict[str, Any]:
        """O formato do JSONL de medição: o mesmo do protótipo, mais a classe `ruido`."""
        return {
            "erros": dict(self.erros),
            "total": dict(self.total),
            "pp": self.palavras_prosa,
            "ppc": self.palavras_prosa_certas,
            "trocas": dict(self.trocas),
            "insercoes": self.insercoes,
            "insercoes_por_classe": dict(self.insercoes_por_classe),
            "wer": {"s": self.wer_s, "d": self.wer_d, "i": self.wer_i, "n": self.wer_n},
            "fig": {"ref": self.fig_ref, "hip": self.fig_hip, "tp": self.fig_tp},
        }


def _letras_de_peca(lingua: str) -> frozenset[str]:
    pecas = LETRAS_DE_PECA.get(lingua_da_regua(lingua), ())
    return _LETRAS_DE_PECA_NO_PLACAR | frozenset(c for p in pecas for c in p if c.isupper())


def pontuar(ref: str, hip: str, lingua: str = LINGUA_PADRAO, *, classificar: Classificador | None = None) -> Placar:
    """O placar de `hip` contra `ref`, os dois já normalizados. Cada operação vai à classe do caractere da referência.

    A inserção vai à classe do próximo caractere alinhado; no fim do texto, à do último, e não a uma classe que
    ninguém publica. A referência vazia não tem classe nenhuma: a inserção é contada em `insercoes` e em `espaco`.
    """
    classes = classes_por_char(ref, lingua, classificar=classificar)
    pares = alinhar(ref, hip)
    p = Placar()
    pecas = _LETRAS_DE_PECA_NO_PLACAR if classificar is not None else _letras_de_peca(lingua)
    for c in classes:
        p.total[c] += 1
    pendentes = 0
    ultima = ESPACO
    for i, j in pares:
        if i == -1:
            pendentes += 1
            p.insercoes += 1
            continue
        c = classes[i]
        ultima = c
        if pendentes:
            p.erros[c] += pendentes
            p.insercoes_por_classe[c] = p.insercoes_por_classe.get(c, 0) + pendentes
            pendentes = 0
        if j == -1 or ref[i] != hip[j]:
            p.erros[c] += 1
        if c == NOTACAO and ref[i] in pecas and ref[i].isupper():
            p.fig_ref += 1
            if j != -1 and hip[j] == ref[i]:
                p.fig_tp += 1
        if c == NOTACAO and j != -1 and hip[j] in pecas and hip[j].isupper():
            p.fig_hip += 1
    if pendentes:
        p.erros[ultima] += pendentes
        p.insercoes_por_classe[ultima] = p.insercoes_por_classe.get(ultima, 0) + pendentes
    wer = _wer_por_token(ref, hip, lingua, classificar)
    p.wer_s, p.wer_d, p.wer_i, p.wer_n = wer["s"], wer["d"], wer["i"], wer["n"]
    _trocas_de_palavra(p, ref, hip, pares, classes)
    return p


def _trocas_de_palavra(p: Placar, ref: str, hip: str, pares: Sequence[tuple[int, int]], classes: Sequence[str]) -> None:
    """A palavra de prosa certa é a de trecho idêntico, com espaço ou borda dos dois lados na hipótese."""
    da_ref = {i: j for i, j in pares if i != -1}
    for m in re.finditer(r"\S+", ref):
        if classes[m.start()] != PROSA:
            continue
        p.palavras_prosa += 1
        validos = [j for j in (da_ref.get(k, -1) for k in range(m.start(), m.end())) if j != -1]
        lido = hip[min(validos): max(validos) + 1] if validos else ""
        certa = lido == m.group()
        if certa and validos:
            a, b = min(validos), max(validos)
            certa = (a == 0 or hip[a - 1].isspace()) and (b + 1 >= len(hip) or hip[b + 1].isspace())
        if certa:
            p.palavras_prosa_certas += 1
        else:
            chave = f"{m.group()} -> {lido}"
            p.trocas[chave] = p.trocas.get(chave, 0) + 1


# ---------------------------------------------------------------------------------- a família de um erro


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def familia(ref: str, hip: str) -> str:
    """A família da palavra de prosa errada. A primeira que casa ganha: a ordem dos testes importa."""
    if hip == "":
        return "palavra perdida"
    if ref == hip:
        return "fronteira (espaco perdido junto a vizinha)"
    pontos = re.sub(r"[lI|]", ".", ref)
    if pontos == hip or (pontos == re.sub(r"[lI|]", ".", hip) and "." in hip):
        return "traco vertical lido como ponto (l/I -> .)"
    if hip.replace("fi1", "fi").replace("f1", "fl").replace("ff1", "ff") == ref:
        return "ligadura fi/fl com 1 a mais"
    if hip in (ref.replace('"', "''"), ref.replace('"', "'"), ref.replace('"', "(")):
        return "aspas duplas"
    if re.search(r"[♔-♟]", hip) and not re.search(r"[♔-♟]", ref):
        return "figurina inventada em palavra"
    if ref.lower() == hip.lower():
        return "caixa (maiusc/minusc)"
    if _sem_acento(ref) == _sem_acento(hip):
        return "acento"
    r0, h0 = re.sub(r"\W", "", ref), re.sub(r"\W", "", hip)
    if r0 == h0:
        return "espaco" if ref.replace(" ", "") == hip.replace(" ", "") else "pontuacao"
    if r0.lower() == h0.lower():
        return "pontuacao+caixa"
    if hip.replace(" ", "") == ref.replace(" ", "") or " " in hip:
        return "espaco"
    if re.sub(r"1", "", hip) == ref or re.sub(r"[1l|I]", "", hip) == re.sub(r"[1l|I]", "", ref):
        return "1/l/I/|"
    if _sem_acento(ref).lower() == _sem_acento(hip).lower():
        return "acento+caixa"
    if len(hip) > len(ref) and ref in hip:
        return "juncao com vizinha (espaco perdido)"
    if len(hip) < len(ref) and hip and hip in ref:
        return "palavra cortada"
    return "letra trocada"


# ------------------------------------------------------------------------------------------- estatística

SEMENTE = 7
REAMOSTRAS = 2000


def _reamostras(livros: Sequence[str], rng: np.random.Generator, reamostras: int) -> list[np.ndarray]:
    """Uma reamostra por iteração: sorteia livros com reposição, depois folhas dentro de cada um."""
    por_livro: dict[str, list[int]] = defaultdict(list)
    for k, livro in enumerate(livros):
        por_livro[livro].append(k)
    grupos = list(por_livro.values())
    saida = []
    for _ in range(reamostras):
        indices: list[int] = []
        for g in rng.integers(0, len(grupos), len(grupos)):
            folhas = grupos[g]
            indices.extend(np.array(folhas)[rng.integers(0, len(folhas), len(folhas))])
        saida.append(np.array(indices))
    return saida


def ic95(
    erros: Sequence[float],
    totais: Sequence[float],
    livros: Sequence[str] | None = None,
    *,
    semente: int = SEMENTE,
    reamostras: int = REAMOSTRAS,
) -> tuple[float, float, float]:
    """A taxa agregada e o IC95. Com `livros`, em dois níveis (folha do mesmo livro não é independente)."""
    e, t = np.array(erros, float), np.array(totais, float)
    if len(e) == 0:
        return (float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(semente)
    if livros is None:
        idx = rng.integers(0, len(e), (reamostras, len(e)))
        amostras = e[idx].sum(1) / np.maximum(1, t[idx].sum(1))
    else:
        amostras = np.array([e[i].sum() / max(1, t[i].sum()) for i in _reamostras(livros, rng, reamostras)])
    return float(e.sum() / max(1, t.sum())), float(np.percentile(amostras, 2.5)), float(np.percentile(amostras, 97.5))


def diferenca_pareada(
    erros_a: Sequence[float],
    totais_a: Sequence[float],
    erros_b: Sequence[float],
    totais_b: Sequence[float],
    livros: Sequence[str],
    *,
    semente: int = SEMENTE,
    reamostras: int = REAMOSTRAS,
) -> tuple[float, float, float]:
    """CER(a) − CER(b) nas mesmas folhas, com o IC95 do mesmo bootstrap de dois níveis."""
    ea, ta, eb, tb = (np.array(x, float) for x in (erros_a, totais_a, erros_b, totais_b))
    rng = np.random.default_rng(semente)
    amostras = [
        ea[i].sum() / max(1, ta[i].sum()) - eb[i].sum() / max(1, tb[i].sum())
        for i in _reamostras(livros, rng, reamostras)
    ]
    ponto = ea.sum() / max(1, ta.sum()) - eb.sum() / max(1, tb.sum())
    return float(ponto), float(np.percentile(amostras, 2.5)), float(np.percentile(amostras, 97.5))


# ---------------------------------------------------------------------------------- a montagem da folha

Caixa = Sequence[float]


def _mesma_faixa(a: Caixa, b: Caixa) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    vertical = min(ay1, by1) - max(ay0, by0)
    horizontal = min(ax1, bx1) - max(ax0, bx0)
    return bool(vertical >= 0.5 * min(ay1 - ay0, by1 - by0) and horizontal > 0)


def linhas_da_pagina(pagina: Any) -> list[Any]:
    """As linhas de uma `PaginaLida`, na ordem de leitura: colunas, blocos, linhas.

    Cabeçalho e rodapé **só quando nenhuma linha de coluna ocupa a mesma faixa**: o produto monta pelas colunas, e
    no caminho do glifo o cabeçalho volta lido numa coluna. Juntar os dois duplicava `PARTIDA 13` e fabricou metade
    da "perda de leiaute" até a rodada 9 do crítico.
    """
    corpo = [
        linha for coluna in pagina.colunas for bloco in coluna.blocos for linha in (getattr(bloco, "linhas", ()) or ())
    ]
    saida = []
    if pagina.cabecalho is not None and not any(_mesma_faixa(pagina.cabecalho.bbox, ln.bbox) for ln in corpo):
        saida.append(pagina.cabecalho)
    saida.extend(corpo)
    if pagina.rodape is not None and not any(_mesma_faixa(pagina.rodape.bbox, ln.bbox) for ln in corpo):
        saida.append(pagina.rodape)
    return saida


def crescer_diagrama(caixa: Caixa) -> tuple[float, float, float, float]:
    """O retângulo crescido de uma casa, para a fileira de coordenadas em fonte não escapar (S-701)."""
    x0, y0, x1, y1 = caixa
    casa_x, casa_y = (x1 - x0) / 8.0, (y1 - y0) / 8.0
    return (x0 - casa_x, y0 - casa_y, x1 + casa_x, y1 + casa_y)


def cruza_diagrama(caixa: Caixa, diagramas: Iterable[Caixa], fracao: float = 0.3) -> bool:
    """A linha tem pelo menos `fracao` da área dentro de algum retângulo?"""
    x0, y0, x1, y1 = caixa
    area = max(1e-6, (x1 - x0) * (y1 - y0))
    for d0, e0, d1, e1 in diagramas:
        ix = max(0.0, min(x1, d1) - max(x0, d0))
        iy = max(0.0, min(y1, e1) - max(y0, e0))
        if ix * iy >= fracao * area:
            return True
    return False


def fora_da_referencia(linha: str, caixa: Caixa, diagramas: Sequence[Caixa], lingua: str = LINGUA_PADRAO) -> bool:
    """A linha sai da referência? Cruza o diagrama; ou cruza o retângulo crescido de uma casa e não tem palavra nem lance.

    **Crescer não vale para a linha que tem texto.** O roadmap pede o retângulo crescido, para a fileira de coordenadas em
    fonte não escapar (`/èéêëìíîï)` no Seirawan). Medido nas 27 folhas do dev: das 15 linhas a mais que ele tira, 6 são essa
    fileira, e 9 são texto de verdade ao lado do diagrama (`As brancas jogam`, `Not only is Black faced`), que
    tiradas da referência contariam como inserção de todo motor que as leu certo.
    """
    if cruza_diagrama(caixa, diagramas):
        return True
    if not cruza_diagrama(caixa, [crescer_diagrama(d) for d in diagramas]):
        return False
    return not set(classes_por_char(linha, lingua)) & {PROSA, NOTACAO}


def texto_de(linhas: Iterable[str]) -> str:
    return "\n".join(linhas)


__all__ = [
    "CLASSES",
    "CRU",
    "ESPACO",
    "LETRAS_DE_PECA",
    "LINGUA_PADRAO",
    "MODOS",
    "NOTACAO",
    "OUTRO",
    "PROSA",
    "REAMOSTRAS",
    "RUIDO",
    "SEMENTE",
    "TIP",
    "VERSAO_CLASSIFICADOR",
    "Placar",
    "alinhar",
    "classe_do_token",
    "classes_por_char",
    "crescer_diagrama",
    "cruza_diagrama",
    "diferenca_pareada",
    "familia",
    "fora_da_referencia",
    "ic95",
    "linhas_da_pagina",
    "normalizar",
    "pontuar",
    "texto_de",
]
