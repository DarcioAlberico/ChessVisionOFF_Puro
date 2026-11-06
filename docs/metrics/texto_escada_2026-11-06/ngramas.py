"""O que falta do degrau 0 da escada (S-745): n-gramas de caractere por língua desempatando as alternativas de `lstm_choice_mode=2`.

    ngramas.py --conjunto ouro --split dev --dados fora/esc_dev.jsonl --limite-segundos 150
    ngramas.py --conjunto prata --dados fora/esc_prata.jsonl --limite-segundos 150

É o `cvoff-texto-prosa` com motores a mais, pela porta 2 de `text/bancada_prosa.py`: mesma referência, mesmas caixas do glifo, mesmo placar.

| motor | o que é |
|---|---|
| `tess` | o Tesseract nas caixas do glifo, em TSV: o de produção |
| `tess_hocr` | o mesmo, em hOCR com `lstm_choice_mode=2`, a primeira escolha: a base do par, e o custo do processo a mais |
| `ng_05`, `ng_10`, `ng_20` | a palavra fora do léxico troca pela alternativa cujo trigrama ganha por 0,5, 1 ou 2 nats |
| `lex` | o controle: a alternativa que é palavra do léxico, sem trigrama nenhum |
| `teto` | **o oráculo**: a alternativa que está na referência. Não é regra possível: é o máximo que as alternativas podem dar |

O modelo é de trigramas com suavização, contado nos **tipos** da lista da língua (`lexico.da_lingua`), que não vem de livro nenhum do ouro nem da
prata. Só palavra de letras, de ao menos 3 letras, fora do léxico: o que o léxico conhece e a notação ficam.
Os segundos sob contenção não julgam nada: servem de razão entre `tess_hocr` e `tess`, na mesma folha.
"""

from __future__ import annotations

import html
import itertools
import math
import re
import sys
from collections import Counter
from functools import lru_cache

from chess_diagram_ocr.cli import texto_prosa
from chess_diagram_ocr.text import bancada_prosa, lexico, tesseract
from chess_diagram_ocr.text import regua_prosa as regua

CONFIANCA_MINIMA = 5.0
"""Alternativa abaixo disso (x_confs, em %) nem é candidata. O hOCR traz dezenas de ruídos de 0,0x."""
POSICOES_MAXIMAS = 2
SUAVIZACAO = 0.5
_ESCOLHA = re.compile(r"title='x_confs ([\d.]+)'>([^<]*)</span>")
_PALAVRA_DE_LETRAS = re.compile(r"^([(\[«\"'„“]*)([^\W\d_]{3,})([)\]»\"'”.,;:!?]*)$")

Palavra = list[list[tuple[str, float]]]
"""Por posição, `(caractere, confiança)`, a primeira sendo a lida."""


def palavras_da_pagina(pagina: str) -> list[list[Palavra]]:
    """Linhas de palavras de uma página do hOCR. Cada recorte é uma página, e cada página é uma linha da folha."""
    linhas: list[list[Palavra]] = []
    for bloco_de_linha in pagina.split("class='ocr_line'")[1:] or [pagina]:
        palavras: list[Palavra] = []
        for bloco in bloco_de_linha.split("class='ocrx_word'")[1:]:
            posicoes: Palavra = []
            for grupo in bloco.split("id='lstm_choices_")[1:]:
                opcoes = [(html.unescape(c), float(n)) for n, c in _ESCOLHA.findall(grupo)]
                # O espaço que o LSTM põe antes da palavra é uma posição como outra no hOCR, e não é letra.
                if opcoes and opcoes[0][0].strip():
                    posicoes.append(opcoes)
            if posicoes:
                palavras.append(posicoes)
        if palavras:
            linhas.append(palavras)
    return linhas


def lida(palavra: Palavra) -> str:
    return "".join(p[0][0] for p in palavra)


def candidatos(palavra: Palavra) -> list[str]:
    """A lida com uma ou duas posições trocadas por uma alternativa de confiança bastante."""
    trocas = [(i, c) for i, opcoes in enumerate(palavra) for c, conf in opcoes[1:] if c.strip() and conf >= CONFIANCA_MINIMA]
    base = [p[0][0] for p in palavra]
    saida: list[str] = []
    for n in range(1, POSICOES_MAXIMAS + 1):
        for grupo in itertools.combinations(trocas, n):
            if len({i for i, _c in grupo}) < n:
                continue
            nova = list(base)
            for i, c in grupo:
                nova[i] = c
            saida.append("".join(nova))
    return list(dict.fromkeys(saida))


@lru_cache(maxsize=8)
def modelo(lingua: str) -> tuple[Counter, Counter, int]:
    tri: Counter = Counter()
    bi: Counter = Counter()
    letras: set[str] = set()
    for palavra in lexico.da_lingua(lingua):
        marcada = f"^{palavra.lower()}$"
        letras.update(marcada)
        for k in range(len(marcada) - 2):
            tri[marcada[k: k + 3]] += 1
            bi[marcada[k: k + 2]] += 1
    return tri, bi, max(1, len(letras))


def pontos(palavra: str, lingua: str) -> float:
    tri, bi, v = modelo(lingua)
    marcada = f"^{palavra.lower()}$"
    return sum(
        math.log((tri[marcada[k: k + 3]] + SUAVIZACAO) / (bi[marcada[k: k + 2]] + SUAVIZACAO * v)) for k in range(len(marcada) - 2)
    )


def elegivel(texto: str, lingua: str) -> re.Match[str] | None:
    achado = _PALAVRA_DE_LETRAS.match(texto)
    if achado is None or achado.group(2).lower() in lexico.da_lingua(lingua):
        return None
    return achado


def escolher(palavra: Palavra, lingua: str, *, margem: float | None = None, no_lexico: bool = False, na_referencia: frozenset[str] | None = None) -> str:
    texto = lida(palavra)
    if na_referencia is not None:
        if texto in na_referencia:
            return texto
        return next((c for c in candidatos(palavra) if c in na_referencia), texto)
    achado = elegivel(texto, lingua)
    if achado is None:
        return texto
    if no_lexico:
        return next((c for c in candidatos(palavra) if (m := _PALAVRA_DE_LETRAS.match(c)) and m.group(2).lower() in lexico.da_lingua(lingua)), texto)
    assert margem is not None
    base = pontos(achado.group(2), lingua)
    melhor, ganho = texto, margem
    for c in candidatos(palavra):
        m = _PALAVRA_DE_LETRAS.match(c)
        if m is not None and pontos(m.group(2), lingua) - base >= ganho:
            melhor, ganho = c, pontos(m.group(2), lingua) - base
    return melhor


def _do_hocr(folha: bancada_prosa.FolhaEmMedida) -> list[list[Palavra]]:
    """Uma linha da folha por página do TIFF. Em cache na folha: as variantes são a mesma leitura, e o processo é um só."""
    if "hocr" not in folha.paginas:
        linhas = regua.linhas_da_pagina(folha.glifo)
        recortes = [bancada_prosa.recortar(folha.imagem, ln.bbox, folha.dpi) for ln in linhas]
        validos = [i for i, r in enumerate(recortes) if r.size]
        saida: list[list[Palavra]] = [[] for _ in recortes]
        if validos:
            hocr = tesseract.rodar(
                tesseract.achar_motor(), tesseract._tiff_de([recortes[i] for i in validos]), lingua=folha.lingua, dpi=folha.dpi, psm=7,  # noqa: SLF001
                timeout=max(tesseract.TIMEOUT_MINIMO, tesseract.TIMEOUT_POR_LINHA * len(validos)), opcoes=("-c", "lstm_choice_mode=2"), formato="hocr",
            )
            paginas = hocr.split("class='ocr_page'")[1:]
            assert len(paginas) == len(validos), (len(paginas), len(validos))
            for i, pagina in zip(validos, paginas, strict=True):
                saida[i] = [p for linha in palavras_da_pagina(pagina) for p in linha]
        folha.paginas["hocr"] = saida
    return folha.paginas["hocr"]


def _motor(**regra) -> bancada_prosa.MotorDeBancada:
    def ler(folha: bancada_prosa.FolhaEmMedida) -> str:
        return regua.texto_de(" ".join(escolher(p, folha.lingua, **regra) for p in linha) for linha in _do_hocr(folha))

    return ler


def _teto(folha: bancada_prosa.FolhaEmMedida) -> str:
    referencia = frozenset(" ".join(ln.texto for ln in folha.linhas_da_referencia).split())
    return regua.texto_de(" ".join(escolher(p, folha.lingua, na_referencia=referencia) for p in linha) for linha in _do_hocr(folha))


def _base(folha: bancada_prosa.FolhaEmMedida) -> str:
    return regua.texto_de(" ".join(lida(p) for p in linha) for linha in _do_hocr(folha))


MOTORES = {
    "tess_hocr": _base,
    "ng_05": _motor(margem=0.5),
    "ng_10": _motor(margem=1.0),
    "ng_20": _motor(margem=2.0),
    "lex": _motor(no_lexico=True),
    "teto": _teto,
}


def main() -> int:
    for nome, funcao in MOTORES.items():
        bancada_prosa.registrar_motor(nome, funcao)
    return texto_prosa.main([*sys.argv[1:], "--motor", "tess," + ",".join(MOTORES)])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
