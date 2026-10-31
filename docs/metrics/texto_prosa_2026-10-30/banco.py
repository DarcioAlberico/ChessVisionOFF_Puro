"""Banco de medição de OCR de TEXTO, prosa separada de notação.

Referência: camada editorada do PDF, montada pelo MESMO ler_pagina (motor=camada).
Hipóteses: o glifo de produção (ler_pagina motor=glifo) e, sobre as MESMAS caixas de linha
do glifo, Tesseract (LSTM) e RapidOCR (PP-OCRv4 rec). Variante "oráculo": Tesseract nas caixas
de linha da própria camada (mede quanto a segmentação de linha do glifo custa).
"""
from __future__ import annotations

import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field

import cv2
import numpy as np

TESS = os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

# ----------------------------------------------------------------------------- normalização
TIPOGRAFIA = {
    "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u00ab": '"',
    "\u00bb": '"', "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2026": "...", "\u00a0": " ",
    "\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl", "\u00ad": "",
    "\u2010": "-", "\u2011": "-", "\u02bc": "'", "\u00b4": "'", "`": "'",
}
FIGURINA = {"♔": "K", "♚": "K", "♕": "Q", "♛": "Q", "♖": "R", "♜": "R", "♗": "B", "♝": "B",
            "♘": "N", "♞": "N", "♙": "", "♟": ""}


LETRAS_DE_PECA = {"eng": "KQRBN", "por": "RDTBC", "spa": "RDTAC", "deu": "KDTLS", "fra": "RDTFC",
                  "nld": "KDTLP"}


def normalizar(texto: str, *, tipografia: bool, lang: str = "eng") -> str:
    t = unicodedata.normalize("NFC", texto)
    if tipografia:
        t = "".join(TIPOGRAFIA.get(c, c) for c in t)
        k, q, r, bb, n = LETRAS_DE_PECA.get(lang.split("+")[0], "KQRBN")
        mapa = {"♔": k, "♚": k, "♕": q, "♛": q, "♖": r, "♜": r, "♗": bb, "♝": bb, "♘": n, "♞": n,
                "♙": "", "♟": ""}
        t = "".join(mapa.get(c, c) for c in t)
    # junta hifenização de fim de linha nos dois lados, do mesmo jeito
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n+", "\n", t)
    return t.strip()


# ----------------------------------------------------------------------------- classes de token
_PECA = "KQRBNDTCSLFAP♔♕♖♗♘♙♚♛♜♝♞♟"
_LANCE = re.compile(
    rf"^(\d+\.+|\d+\.\.\.|\.\.\.|…)?([{_PECA}]?[a-h]?[1-8]?[xX:×]?[a-h][1-8](=?[{_PECA}])?:?|O-O(-O)?|0-0(-0)?)"
    r"(e\.p\.)?[+#†‡t]*[!?]*[=+\-±∓∞⩲⩱]*$"
)
_NUM_LANCE = re.compile(r"^\d+\.+$|^\d+\.\.\.$")
_AVAL = re.compile(r"^([+\-=±∓⩲⩱∞!?#†□△⌓→↑⇆○●N]|\+/-|-/\+|\+-|-\+|=/\+|\+/=|=/∞)+$")
_RESULT = re.compile(r"^(1-0|0-1|½-½|1/2-1/2|\*)$")
_FIG = re.compile(r"[♔-♟]")
# símbolos de avaliação do Informator como cada fonte os codifica (o Kravtsiv usa ʘ)
_SIMBOLOS = "ʘ⊕⊞⨀□△▲▼○●↑→←⇆⇄∆∇⌓⩲⩱±∓∞#†‡"
# notação descritiva (en P-K4, QxQch; es T3Cj, AXD, TXPTR) -- só maiúsculas, com dígito ou captura
_DESCRITIVA = re.compile(r"^(\d+\.+)?[KQRBNPTDACS]{1,3}[1-8]?(-|[xX:])?[KQRBNPTDACS]{0,3}[1-8]?[a-z]{0,2}"
                         r"(ch|mate|\+|#|!|\?)*$")
# letras de peça em cirílico (Кр, Ф, Л, С, К) diante de casa latina ou homóglifo cirílico
_CIRILICO = re.compile(r"^(\d+\.+)?(Кр|[КФЛС])?[a-hаеЬсd]?[1-8]?[:xх]?[a-hаеЬсd][1-8]")
# fileira de coordenadas ou diagrama desenhado com fonte: só letras acentuadas latinas, sem ASCII
_FONTE_DE_DIAGRAMA = re.compile(r"^[^A-Za-z]*[À-ÿ]{3,}[^A-Za-z]*$")
_LONGA = re.compile(rf"^(\d+\.+)?[{_PECA}]?[a-h][1-8][-x×:–][a-h][1-8]")
_LETRA_DE_PECA = re.compile(r"^[KQRBNDTCSLF]$")
_ROQUE = re.compile(r"^(\d+\.+)?(O-O(-O)?|0-0(-0)?|O–O(–O)?|0–0(–0)?)")


def classe_do_token(tok: str) -> str:
    nu = tok.strip("()[]{},;:\"'")
    nu2 = nu.rstrip(".")
    if not nu:
        return "outro"
    nu3 = nu2.replace("×", "x")
    if _FONTE_DE_DIAGRAMA.match(nu):
        return "outro"
    nu4 = "".join(c for c in nu3 if c not in _SIMBOLOS) or nu3
    if _FIG.search(nu) or _LANCE.match(nu) or _LANCE.match(nu3) or _LANCE.match(nu4) or _NUM_LANCE.match(nu) \
            or _AVAL.match(nu) or _RESULT.match(nu) or _LONGA.match(nu) or _LONGA.match(nu4) \
            or _LETRA_DE_PECA.match(nu) or _ROQUE.match(nu) or _CIRILICO.match(nu) \
            or (_DESCRITIVA.match(nu3) and (re.search(r"[0-9:\-]", nu3) or re.search(r"[A-Z][xX][A-Z]", nu3))):
        return "notacao"
    letras = sum(ch.isalpha() for ch in nu)
    if letras == 0:
        return "outro"  # números soltos, pontuação solta
    return "prosa"


def classes_por_char(ref: str) -> list[str]:
    """Classe de cada caractere da referência. O separador ENTRE dois tokens de prosa é prosa:
    `if the`->`ifthe` tem de custar no CER de prosa, não numa classe que ninguém publica."""
    cls = ["espaco"] * len(ref)
    toks = list(re.finditer(r"\S+", ref))
    for m in toks:
        c = classe_do_token(m.group())
        for i in range(m.start(), m.end()):
            cls[i] = c
    for a, b in zip(toks, toks[1:], strict=False):
        if cls[a.start()] == "prosa" and cls[b.start()] == "prosa":
            for i in range(a.end(), b.start()):
                cls[i] = "prosa"
    return cls


def wer_por_token(ref: str, hip: str) -> dict:
    """WER de prosa com S+D+I: alinhamento de tokens (casamento exato custa 0, o resto 1).
    S e D contam token de prosa da referência; I conta token inserido que é prosa."""
    r, h = ref.split(), hip.split()
    n, m = len(r), len(h)
    ids: dict = {}
    rv = np.array([ids.setdefault(x, len(ids)) for x in r], dtype=np.uint32)
    hv = np.array([ids.setdefault(x, len(ids)) for x in h], dtype=np.uint32)
    D = _matriz(rv, hv) if n and m else None
    if D is None:
        return {"s": 0, "d": sum(classe_do_token(t) == "prosa" for t in r),
                "i": sum(classe_do_token(t) == "prosa" for t in h),
                "n": sum(classe_do_token(t) == "prosa" for t in r)}
    i, j = n, m
    s = d = ins = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i, j] == D[i - 1, j - 1] + (r[i - 1] != h[j - 1]):
            if r[i - 1] != h[j - 1] and classe_do_token(r[i - 1]) == "prosa":
                s += 1
            i -= 1
            j -= 1
        elif i > 0 and D[i, j] == D[i - 1, j] + 1:
            if classe_do_token(r[i - 1]) == "prosa":
                d += 1
            i -= 1
        else:
            if classe_do_token(h[j - 1]) == "prosa":
                ins += 1
            j -= 1
    return {"s": s, "d": d, "i": ins, "n": sum(classe_do_token(t) == "prosa" for t in r)}


# ----------------------------------------------------------------------------- alinhamento
def alinhar(a: str, b: str) -> list[tuple[int, int]]:
    """Levenshtein com backtrace; devolve pares (i, j) com -1 para lacuna. a=ref, b=hip."""
    n, m = len(a), len(b)
    if n == 0:
        return [(-1, j) for j in range(m)]
    if m == 0:
        return [(i, -1) for i in range(n)]
    av = np.frombuffer(a.encode("utf-32-le"), dtype=np.uint32)
    bv = np.frombuffer(b.encode("utf-32-le"), dtype=np.uint32)
    D = _matriz(av, bv)
    i, j = n, m
    pares = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i, j] == D[i - 1, j - 1] + (a[i - 1] != b[j - 1]):
            pares.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and D[i, j] == D[i - 1, j] + 1:
            pares.append((i - 1, -1))
            i -= 1
        else:
            pares.append((-1, j - 1))
            j -= 1
    pares.reverse()
    return pares


def _matriz(av: np.ndarray, bv: np.ndarray) -> np.ndarray:
    """Matriz de Levenshtein vetorizada por linha (mínimo acumulado para a inserção)."""
    n, m = len(av), len(bv)
    D = np.empty((n + 1, m + 1), dtype=np.int32)
    D[0] = np.arange(m + 1)
    ar = np.arange(m + 1, dtype=np.int32)
    for i in range(1, n + 1):
        prev = D[i - 1]
        cost = (bv != av[i - 1]).astype(np.int32)
        x = np.empty(m + 1, dtype=np.int32)
        x[0] = i
        x[1:] = np.minimum(prev[1:] + 1, prev[:-1] + cost)
        D[i] = np.minimum.accumulate(x - ar) + ar
    return D


@dataclass
class Placar:
    erros: dict = field(default_factory=lambda: {"prosa": 0, "notacao": 0, "outro": 0, "espaco": 0})
    total: dict = field(default_factory=lambda: {"prosa": 0, "notacao": 0, "outro": 0, "espaco": 0})
    palavras_prosa: int = 0
    palavras_prosa_certas: int = 0
    trocas: dict = field(default_factory=dict)  # (ref_word -> hip_word) da prosa errada
    insercoes: int = 0
    insercoes_por_classe: dict = field(default_factory=dict)
    wer_s: int = 0
    wer_d: int = 0
    wer_i: int = 0
    wer_n: int = 0
    fig_ref: int = 0   # letras de peça em notação na referência
    fig_hip: int = 0   # letras de peça em notação na hipótese
    fig_tp: int = 0    # acertadas na mesma posição alinhada

    def somar(self, o: Placar) -> None:
        for k in self.erros:
            self.erros[k] += o.erros[k]
            self.total[k] += o.total[k]
        self.palavras_prosa += o.palavras_prosa
        self.palavras_prosa_certas += o.palavras_prosa_certas
        for k, v in o.trocas.items():
            self.trocas[k] = self.trocas.get(k, 0) + v

    def cer(self, k: str) -> float:
        return self.erros[k] / max(1, self.total[k])

    def wer_prosa(self) -> float:
        return 1 - self.palavras_prosa_certas / max(1, self.palavras_prosa)


_LETRAS_DE_PECA_TODAS = set("KQRBNDTCSLFP")


def pontuar(ref: str, hip: str) -> Placar:
    cls = classes_por_char(ref)
    pares = alinhar(ref, hip)
    p = Placar()
    for c in cls:
        p.total[c] += 1
    # erros por classe; inserção vai para a classe do próximo char de ref alinhado
    # (no fim do texto, para a do último). Inserções também contadas à parte.
    pend_ins = 0
    ultimo = "espaco"
    for (i, j) in pares:
        if i == -1:
            pend_ins += 1
            p.insercoes += 1
            continue
        c = cls[i]
        ultimo = c
        if pend_ins:
            p.erros[c] += pend_ins
            p.insercoes_por_classe[c] = p.insercoes_por_classe.get(c, 0) + pend_ins
            pend_ins = 0
        if j == -1 or ref[i] != hip[j]:
            p.erros[c] += 1
        # figurina (já mapeada para letra de peça) dentro de token de notação
        if c == "notacao" and ref[i] in _LETRAS_DE_PECA_TODAS and ref[i].isupper():
            p.fig_ref += 1
            if j != -1 and hip[j] == ref[i]:
                p.fig_tp += 1
        if c == "notacao" and j != -1 and hip[j] in _LETRAS_DE_PECA_TODAS and hip[j].isupper():
            p.fig_hip += 1
    if pend_ins:
        p.erros[ultimo] += pend_ins
        p.insercoes_por_classe[ultimo] = p.insercoes_por_classe.get(ultimo, 0) + pend_ins
    w = wer_por_token(ref, hip)
    p.wer_s, p.wer_d, p.wer_i, p.wer_n = w["s"], w["d"], w["i"], w["n"]
    # palavra de prosa certa: o trecho da hipótese alinhado ao token é idêntico
    ref_para_hip = {}
    for (i, j) in pares:
        if i != -1:
            ref_para_hip[i] = j
    for m in re.finditer(r"\S+", ref):
        if classe_do_token(m.group()) != "prosa":
            continue
        p.palavras_prosa += 1
        js = [ref_para_hip.get(k, -1) for k in range(m.start(), m.end())]
        # pega trecho hip entre o primeiro e o último j válido, incluindo inserções internas
        validos = [j for j in js if j != -1]
        if not validos:
            hip_tok = ""
        else:
            hip_tok = hip[min(validos): max(validos) + 1]
        # fronteira: o char antes/depois na hipótese precisa ser espaço/borda
        ok = hip_tok == m.group()
        if ok and validos:
            a, b = min(validos), max(validos)
            if (a > 0 and not hip[a - 1].isspace()) or (b + 1 < len(hip) and not hip[b + 1].isspace()):
                ok = False
        if ok:
            p.palavras_prosa_certas += 1
        else:
            k = f"{m.group()} -> {hip_tok}"
            p.trocas[k] = p.trocas.get(k, 0) + 1
    return p


# ----------------------------------------------------------------------------- motores de linha
def recortar(img: np.ndarray, bbox_pt, dpi: int, pad_frac=0.12) -> np.ndarray:
    s = dpi / 72.0
    x0, y0, x1, y1 = [v * s for v in bbox_pt]
    h = y1 - y0
    pad = max(2, int(round(h * pad_frac)))
    H, W = img.shape[:2]
    x0 = max(0, int(x0) - pad)
    x1 = min(W, int(np.ceil(x1)) + pad)
    y0 = max(0, int(y0) - pad)
    y1 = min(H, int(np.ceil(y1)) + pad)
    return img[y0:y1, x0:x1]


def tess_linha(crop: np.ndarray, lang: str, escala: float = 1.0, psm: int = 7,
               dpi_declarado: int = 300) -> tuple[str, list]:
    """`dpi_declarado` e o que se diz ao Tesseract. O protótipo de 2026-10-30 declarava 300 sobre
    imagem de 220 dpi (defeito achado na rodada 4); o certo é a resolução real vezes `escala`."""
    if crop.size == 0:
        return "", []
    g = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
    if escala != 1.0:
        g = cv2.resize(g, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
    g = cv2.copyMakeBorder(g, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
    ok, png = cv2.imencode(".png", g)
    r = subprocess.run([TESS, "stdin", "stdout", "-l", lang, "--psm", str(psm), "--dpi", str(int(round(dpi_declarado))), "tsv"],
                       input=png.tobytes(), capture_output=True)
    palavras = []
    for linha in r.stdout.decode("utf-8", "replace").splitlines()[1:]:
        c = linha.split("\t")
        if len(c) >= 12 and c[0] == "5" and c[11].strip():
            palavras.append((c[11], float(c[10])))
    return " ".join(w for w, _ in palavras), palavras


_RAPID = None


def rapid_linha(crop: np.ndarray) -> str:
    global _RAPID
    if _RAPID is None:
        from rapidocr_onnxruntime import RapidOCR
        _RAPID = RapidOCR()
    if crop.size == 0:
        return ""
    bgr = crop[:, :, ::-1].copy() if crop.ndim == 3 else cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    res, _ = _RAPID(bgr, use_det=False, use_cls=False, use_rec=True)
    if not res:
        return ""
    return " ".join(str(r[0]).strip() for r in res)


# ----------------------------------------------------------------------------- páginas
def _mesma_faixa(a, b) -> bool:
    """As duas caixas ocupam a mesma faixa da folha (sobreposição vertical e horizontal)?"""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    sv = min(ay1, by1) - max(ay0, by0)
    sh = min(ax1, bx1) - max(ax0, bx0)
    return sv >= 0.5 * min(ay1 - ay0, by1 - by0) and sh > 0


def linhas_da_pagina(pagina) -> list:
    """Linhas na ordem de leitura do PaginaLida: colunas/blocos, e cabeçalho e rodapé **só** quando
    nenhuma linha de coluna já ocupa a mesma faixa.

    O produto monta o texto pelas colunas (`PaginaLida.texto`). No caminho do glifo o cabeçalho vem
    da camada (S-356) **e** a mesma linha volta lida pelo glifo numa coluna; juntar os dois duplicava
    `PARTIDA 13` e fabricava erro de inserção (achado da rodada 9 do crítico)."""
    corpo = []
    for col in pagina.colunas:
        for b in col.blocos:
            for ln in getattr(b, "linhas", ()) or ():
                corpo.append(ln)
    out = []
    for extra in (pagina.cabecalho,):
        if extra is not None and not any(_mesma_faixa(extra.bbox, ln.bbox) for ln in corpo):
            out.append(extra)
    out.extend(corpo)
    if pagina.rodape is not None and not any(_mesma_faixa(pagina.rodape.bbox, ln.bbox) for ln in corpo):
        out.append(pagina.rodape)
    return out


def texto_de(linhas_txt: list[str]) -> str:
    return "\n".join(t for t in linhas_txt if t is not None)


def placar_dict(p: Placar) -> dict:
    return {"erros": p.erros, "total": p.total, "pp": p.palavras_prosa, "ppc": p.palavras_prosa_certas,
            "trocas": p.trocas, "insercoes": p.insercoes, "insercoes_por_classe": p.insercoes_por_classe,
            "wer": {"s": p.wer_s, "d": p.wer_d, "i": p.wer_i, "n": p.wer_n},
            "fig": {"ref": p.fig_ref, "hip": p.fig_hip, "tp": p.fig_tp}}


def cruza_diagrama(bbox, diagramas, frac=0.3) -> bool:
    """A linha tem >= frac da area dentro de algum retangulo de diagrama?"""
    x0, y0, x1, y1 = bbox
    area = max(1e-6, (x1 - x0) * (y1 - y0))
    for d0, e0, d1, e1 in diagramas:
        ix = max(0.0, min(x1, d1) - max(x0, d0))
        iy = max(0.0, min(y1, e1) - max(y0, e0))
        if ix * iy >= frac * area:
            return True
    return False


def caixas_visuais(linhas, img, dpi):
    """Oraculo: junta as linhas da camada que sao a mesma linha visual e aperta a caixa a tinta.
    Devolve [(bbox_pt, [indices das linhas da camada])] na ordem da primeira linha de cada grupo."""
    s = dpi / 72.0
    grupos = []
    for k, ln in enumerate(linhas):
        x0, y0, x1, y1 = ln.bbox
        h = max(1e-6, y1 - y0)
        # so junta com o grupo IMEDIATAMENTE anterior na ordem da camada, a direita dele e a menos
        # de uma altura de distancia: e o trecho em negrito partido da mesma linha, nunca a coluna
        # vizinha (juntar por sobreposicao vertical fundia as duas colunas do Chess Evolution)
        if grupos:
            gx0, gy0, gx1, gy1 = grupos[-1][0]
            sob = min(y1, gy1) - max(y0, gy0)
            vao = x0 - gx1
            if sob >= 0.5 * min(h, gy1 - gy0) and -0.5 * h <= vao <= 1.0 * h:
                grupos[-1][0] = (min(x0, gx0), min(y0, gy0), max(x1, gx1), max(y1, gy1))
                grupos[-1][1].append(k)
                continue
        grupos.append([(x0, y0, x1, y1), [k]])
    out = []
    H, W = img.shape[:2]
    for (x0, y0, x1, y1), ks in grupos:
        a0, b0 = max(0, int(x0 * s)), max(0, int(y0 * s))
        a1, b1 = min(W, int(x1 * s) + 1), min(H, int(y1 * s) + 1)
        rec = img[b0:b1, a0:a1]
        if rec.size:
            g = cv2.cvtColor(rec, cv2.COLOR_RGB2GRAY) if rec.ndim == 3 else rec
            _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            ys, xs = np.nonzero(bw)
            if len(xs):
                x0, x1 = (a0 + xs.min()) / s, (a0 + xs.max() + 1) / s
                y0, y1 = (b0 + ys.min()) / s, (b0 + ys.max() + 1) / s
        out.append(((x0, y0, x1, y1), sorted(ks)))
    return out
