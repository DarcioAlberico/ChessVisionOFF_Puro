"""Fusão v5 e a régua de preservação de notação (G1 sem referência).

v5 = v4 com duas correções medidas em 2026-10-30:
  1. o veto de palavra só vale para palavra que EXISTE: léxico do projeto (que descarta palavra com
     menos de 4 letras) mais as palavras funcionais curtas de 6 línguas. `Bds` (o Tesseract lendo
     `♗d5`) não é palavra e não veta nada;
  2. o número de lance do leitor de linha só entra quando o glifo PARTIU o número (`7.` contra
     `17.`): o número do Tesseract termina com o do glifo e é mais longo. Número do mesmo tamanho e
     dígito diferente (`27.` contra `21.`) é erro do Tesseract, e fica o do glifo.

Uso: fusao_v5.py entrada.jsonl saida.jsonl   (acrescenta hip['fusao_v5'] e repontua)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banco  # noqa: E402
from rodar import _PALAVRA, alinhar_tokens, e_notacao_do_glifo  # noqa: E402

CURTAS = set("""
a an and are as at be but by do for he her his i if in is it its me my no not of on or our she so the
to up us was we who you
a ao aos as com da das de do dos e é em na nas no nos o os ou para por que se sem um uma à às
al el en es la las lo los y del con por que un una su sus
am an auf aus bei das dem den der des die ein er es im in ist mit nach nicht und von vor zu zum zur
au aux ce de des du en et il la le les ne on ou par pas que qui se un une
de een en het in is met niet op te van voor zijn
""".split())
_NUM = re.compile(r"^\(?(\d+)(?=\.)")
_LEXICO = None


def palavra_que_existe(tok: str) -> bool:
    global _LEXICO
    if _LEXICO is None:
        from chess_diagram_ocr.text import lexico
        _LEXICO = lexico.carregar()
    nu = tok.strip(".,;:!?()[]'\"’“”")
    if not _PALAVRA.match(nu) or e_notacao_do_glifo(nu):
        return False
    return nu.casefold() in _LEXICO or nu.casefold() in CURTAS


def numero_partido(tok_g: str, tok_t: str) -> str:
    mg, mt = _NUM.match(tok_g), _NUM.match(tok_t)
    if mg and mt and len(mt.group(1)) > len(mg.group(1)) and mt.group(1).endswith(mg.group(1)):
        return tok_g[: mg.start(1)] + mt.group(1) + tok_g[mg.end(1):]
    return tok_g


def fundir_v5(glifo: str, linha: str) -> str:
    g, t = glifo.split(), linha.split()
    out = []
    pares = alinhar_tokens(g, t)
    for i, j in pares:
        if i != -1 and j != -1:
            if (e_notacao_do_glifo(g[i]) or e_notacao_do_glifo(t[j])) and not palavra_que_existe(t[j]):
                # o dígito que o glifo deixou solto antes do número (`1 7.♔xf3`) é absorvido aqui
                tok = numero_partido(g[i], t[j])
                if tok != g[i] and out and out[-1].isdigit() and t[j].lstrip("(").startswith(out[-1]):
                    out.pop()
                out.append(tok)
            else:
                out.append(t[j])
        elif i != -1:
            if e_notacao_do_glifo(g[i]) or g[i].isdigit():
                out.append(g[i])
        else:
            if not e_notacao_do_glifo(t[j]):
                out.append(t[j])
    return " ".join(out)


def preservacao(glifo: str, fundida: str) -> tuple[int, int]:
    """Quantos tokens de notação COM FIGURINA do glifo chegam idênticos à saída fundida.
    Régua sem referência: a figurina só o glifo vê, então perdê-la é sempre regressão."""
    fig = [x for x in glifo.split() if re.search(r"[♔-♟]", x)]
    saida = fundida.split()
    restam = list(saida)
    ok = 0
    for x in fig:
        if x in restam:
            restam.remove(x)
            ok += 1
    return ok, len(fig)


def main(ent, sai):
    with open(sai, "w", encoding="utf-8") as f:
        for linha in open(ent, encoding="utf-8"):
            r = json.loads(linha)
            gl, ts = r["hip_linhas"]["glifo"], r["hip_linhas"]["tess"]
            fund = [fundir_v5(a, b) for a, b in zip(gl, ts, strict=False)]
            r["hip"]["fusao_v5"] = banco.texto_de(fund)
            ok = tot = 0
            for a, b in zip(gl, fund, strict=False):
                o, t_ = preservacao(a, b)
                ok += o
                tot += t_
            r["preservacao_v5"] = [ok, tot]
            for tip in (True, False):
                ref = banco.normalizar(r["ref"], tipografia=tip, lang=r["lang"])
                v = r["hip"]["fusao_v5"]
                p = banco.pontuar(ref, banco.normalizar(v, tipografia=tip, lang=r["lang"]))
                r["placar"][f"fusao_v5|{'tip' if tip else 'cru'}"] = banco.placar_dict(p)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
