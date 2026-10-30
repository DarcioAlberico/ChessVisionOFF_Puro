"""Roda o banco sobre uma lista de (pdf, lang, n_paginas) e grava um JSONL por página."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import fitz

sys.path.insert(0, os.path.dirname(__file__))
import banco  # noqa: E402

RAIZ = os.environ.get("CVOFF_RAIZ", r"C:\Python-Chess2\ChessVisionOFF_Puro")


def escolher_paginas(pdf: str, n: int, min_prosa=700, frac=0.55, pular=0.08, frac_max=1.01) -> list[int]:
    """Folhas de prosa (padrao) ou do estrato misto (frac=0.20, frac_max=0.55, min_prosa=300)."""
    d = fitz.open(pdf)
    cands = []
    for i in range(int(d.page_count * pular), int(d.page_count * (1 - pular))):
        t = d[i].get_text()
        if len(t) < min_prosa:
            continue
        toks = re.findall(r"\S+", t)
        cl = [banco.classe_do_token(x) for x in toks]
        pc = sum(len(x) for x, c in zip(toks, cl, strict=False) if c == "prosa")
        tot = sum(len(x) for x in toks)
        if pc >= min_prosa and frac <= pc / max(1, tot) < frac_max:
            cands.append(i)
    if not cands:
        return []
    if len(cands) <= n:
        return cands
    passo = len(cands) / n
    return [cands[int(passo * k + passo / 2)] for k in range(n)]


def alinhar_tokens(g: list[str], t: list[str]):
    """DP de tokens: custo de troca = distância normalizada."""
    def lev(a, b):
        if a == b:
            return 0.0
        pr = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(pr[j] + 1, cur[j - 1] + 1, pr[j - 1] + (ca != cb)))
            pr = cur
        return pr[-1] / max(len(a), len(b))
    n, m = len(g), len(t)
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        D[i][0] = i
    for j in range(1, m + 1):
        D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + lev(g[i - 1], t[j - 1]) * 1.5)
    i, j, out = n, m, []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and abs(D[i][j] - (D[i - 1][j - 1] + lev(g[i - 1], t[j - 1]) * 1.5)) < 1e-9:
            out.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and abs(D[i][j] - (D[i - 1][j] + 1)) < 1e-9:
            out.append((i - 1, -1))
            i -= 1
        else:
            out.append((-1, j - 1))
            j -= 1
    return out[::-1]


def e_notacao_do_glifo(tok: str) -> bool:
    return banco.classe_do_token(tok) == "notacao"


_NUM = re.compile(r"^\(?(\d+)(?=\.)")


def _com_numero_da_linha(tok_g: str, tok_t: str) -> str:
    mg, mt = _NUM.match(tok_g), _NUM.match(tok_t)
    if mt and (not mg or mg.group(1) != mt.group(1)):
        if mg:
            return tok_g[: mg.start(1)] + mt.group(1) + tok_g[mg.end(1):]
        return tok_g
    return tok_g


def fundir(glifo: str, tess: str) -> str:
    g, t = glifo.split(), tess.split()
    out = []
    for i, j in alinhar_tokens(g, t):
        if i != -1 and j != -1:
            if e_notacao_do_glifo(g[i]) or e_notacao_do_glifo(t[j]):
                out.append(_com_numero_da_linha(g[i], t[j]))
            else:
                out.append(t[j])
        elif i != -1:
            if e_notacao_do_glifo(g[i]):
                out.append(g[i])
        else:
            if not e_notacao_do_glifo(t[j]):
                out.append(t[j])
    return " ".join(out)


_FIG = re.compile(r"[♔-♟]")
_PALAVRA = re.compile(r"^[A-Za-zÀ-ÿ]{2,}(?:['’-][A-Za-zÀ-ÿ]+)*[.,;:!?)\]]*$")


def fundir_v4(glifo: str, linha: str) -> str:
    """A regra original (notacao de QUALQUER lado -> glifo, com o numero de lance da linha) mais o
    veto de palavra: se o leitor de linha leu ali uma palavra so de letras, a palavra vence.
    Medido em 2026-10-30: a v2/v3 entregava a notacao em letra ao Tesseract, que estraga lance de
    peao (`g4!`->`24!`, `g3`->`¢3`, `f6`->`£6`)."""
    g, t = glifo.split(), linha.split()
    out = []
    for i, j in alinhar_tokens(g, t):
        if i != -1 and j != -1:
            palavra = _PALAVRA.match(t[j].lstrip("(['\"")) and not e_notacao_do_glifo(t[j])
            if (e_notacao_do_glifo(g[i]) or e_notacao_do_glifo(t[j])) and not palavra:
                out.append(_com_numero_da_linha(g[i], t[j]))
            else:
                out.append(t[j])
        elif i != -1:
            if e_notacao_do_glifo(g[i]):
                out.append(g[i])
        else:
            if not e_notacao_do_glifo(t[j]):
                out.append(t[j])
    return " ".join(out)


def fundir_v2(glifo: str, linha: str, veto: bool = False) -> str:
    """Glifo so manda onde ve figurina. Com veto: se o leitor de linha leu ali uma palavra so de
    letras (`the`, `with`), a palavra vence a figurina (o glifo viu `♔e` em `the`)."""
    g, t = glifo.split(), linha.split()
    out = []
    for i, j in alinhar_tokens(g, t):
        if i != -1 and j != -1:
            palavra = _PALAVRA.match(t[j].lstrip("(['\"")) and not e_notacao_do_glifo(t[j])
            if _FIG.search(g[i]) and not (veto and palavra):
                out.append(_com_numero_da_linha(g[i], t[j]))
            else:
                out.append(t[j])
        elif i != -1:
            if _FIG.search(g[i]):
                out.append(g[i])
        else:
            out.append(t[j])
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--livro", action="append", required=True, help="pdf|lang|n")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--escala-tess", type=float, default=1.0)
    ap.add_argument("--dpi-tess", type=int, default=0, help="dpi declarado ao Tesseract (0 = o real)")
    ap.add_argument("--degradar", default="")
    ap.add_argument("--sem-oraculo", action="store_true")
    ap.add_argument("--paginas", default="", help="lista fixa i,j,k (só com um livro)")
    ap.add_argument("--estrato", default="prosa", choices=["prosa", "misto"])
    ap.add_argument("--acrescentar", action="store_true", help="acrescenta ao JSONL em vez de recriar")
    ap.add_argument("--sem-rapid", action="store_true")
    ap.add_argument("--modelo", default="", help="caminho do char_classifier.pt (padrão: o de models/ do pacote)")
    ap.add_argument("--exigir-src", default="", help="aborta se o pacote importado não morar sob esta pasta")
    args = ap.parse_args()

    import subprocess as _sp

    import chess_diagram_ocr as _pac
    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text.leitor import ler_pagina
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer
    pacote = os.path.dirname(os.path.dirname(os.path.abspath(_pac.__file__)))
    raiz_pac = os.path.dirname(pacote)
    commit = _sp.run(["git", "-C", raiz_pac, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    sujo = bool(_sp.run(["git", "-C", raiz_pac, "status", "--porcelain", "--", "src"], capture_output=True,
                        text=True).stdout.strip())
    print(f"# pacote medido: {pacote} commit {commit[:10]}{' (src sujo)' if sujo else ''}", flush=True)
    if args.exigir_src and not os.path.normcase(os.path.abspath(pacote)).startswith(
            os.path.normcase(os.path.abspath(args.exigir_src))):
        raise SystemExit(f"o pacote importado mora em {pacote}, não sob {args.exigir_src}: use PYTHONPATH=<arvore>/src")
    rec = build_glyph_recognizer(args.modelo) if args.modelo else build_glyph_recognizer()
    pool = ThreadPoolExecutor(max_workers=10)
    saida = open(args.saida, "a" if args.acrescentar else "w", encoding="utf-8")
    aquecido = False
    for spec in args.livro:
        nome, lang, n = spec.split("|")
        pdf = os.path.join(RAIZ, "PDF", nome)
        if args.paginas:
            paginas = [int(x) for x in args.paginas.split(",")]
        elif args.estrato == "misto":
            paginas = escolher_paginas(pdf, int(n), min_prosa=300, frac=0.20, frac_max=0.55)
        else:
            paginas = escolher_paginas(pdf, int(n))
        print(f"## {nome[:50]} {lang} paginas={paginas}", flush=True)
        for idx in paginas:
            img = render_pdf_page(pdf, idx, args.dpi)
            if args.degradar:
                import degradar
                img = degradar.aplicar(img, args.degradar, semente=idx)
            if not aquecido:
                ler_pagina(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=args.dpi)
                aquecido = True
            t0 = time.perf_counter()
            ref_pag = ler_pagina(pdf, idx, motor="camada", imagem_rgb=img, dpi=args.dpi)
            t1 = time.perf_counter()
            gl_pag = ler_pagina(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img, dpi=args.dpi)
            t2 = time.perf_counter()
            diagramas = [d.bbox for d in ref_pag.diagramas] + [d.bbox for d in gl_pag.diagramas]
            ref_todas = banco.linhas_da_pagina(ref_pag)
            # a camada desenha o diagrama com fonte em alguns livros (Seirawan): fora da referencia
            ref_l = [ln for ln in ref_todas if not banco.cruza_diagrama(ln.bbox, diagramas)]
            gl_l = banco.linhas_da_pagina(gl_pag)
            crops = [banco.recortar(img, ln.bbox, args.dpi) for ln in gl_l]
            t3 = time.perf_counter()
            tess = list(pool.map(lambda c, lang=lang: banco.tess_linha(
                c, lang, args.escala_tess, dpi_declarado=args.dpi_tess or args.dpi * args.escala_tess), crops))
            t4 = time.perf_counter()
            rapid = [""] * len(crops) if args.sem_rapid else [banco.rapid_linha(c) for c in crops]
            t5 = time.perf_counter()
            if not args.sem_oraculo:
                vis = banco.caixas_visuais(ref_l, img, args.dpi)
                crops_o = [banco.recortar(img, bb, args.dpi) for bb, _ in vis]
                tess_o = list(pool.map(lambda c, lang=lang: banco.tess_linha(
                    c, lang, args.escala_tess, dpi_declarado=args.dpi_tess or args.dpi * args.escala_tess), crops_o))
            else:
                tess_o = None
            hip = {
                "glifo": [ln.texto for ln in gl_l],
                "tess": [t for t, _ in tess],
                "rapid": rapid,
                "fusao": [fundir(ln.texto, t) for ln, (t, _) in zip(gl_l, tess, strict=False)],
                "fusao_rapid": [fundir(ln.texto, t) for ln, t in zip(gl_l, rapid, strict=False)],
                "fusao_v2": [fundir_v2(ln.texto, t) for ln, (t, _) in zip(gl_l, tess, strict=False)],
                "fusao_v3": [fundir_v2(ln.texto, t, veto=True) for ln, (t, _) in zip(gl_l, tess, strict=False)],
                "fusao_v4": [fundir_v4(ln.texto, t) for ln, (t, _) in zip(gl_l, tess, strict=False)],
            }
            if args.sem_rapid:
                del hip["rapid"], hip["fusao_rapid"]
            if tess_o is not None:
                hip["tess_oraculo"] = [t for t, _ in tess_o]
            ref_txt = banco.texto_de([ln.texto for ln in ref_l])
            reg = {"livro": nome, "lang": lang, "pagina": idx, "degradar": args.degradar,
                   # sem caminho absoluto: relatório publicado não carrega a pasta do usuário (S-706)
                   "codigo": {"commit": commit, "src_sujo": sujo,
                              "arvore": "checkout principal" if os.path.normcase(raiz_pac) == os.path.normcase(RAIZ)
                              else "worktree " + os.path.basename(raiz_pac)},
                   "tempo": {"camada": t1 - t0, "glifo": t2 - t1, "tess": t4 - t3, "rapid": t5 - t4},
                   "n_linhas": {"ref": len(ref_l), "ref_no_diagrama": len(ref_todas) - len(ref_l),
                                "glifo": len(gl_l)},
                   "hip_linhas": {"glifo": hip["glifo"], "tess": hip["tess"]},
                   "ref": ref_txt, "hip": {k: banco.texto_de(v) for k, v in hip.items()},
                   "tess_conf": [list(p) for _, p in tess], "placar": {}}
            for tip in (True, False):
                r = banco.normalizar(ref_txt, tipografia=tip, lang=lang)
                for k, v in reg["hip"].items():
                    p = banco.pontuar(r, banco.normalizar(v, tipografia=tip, lang=lang))
                    reg["placar"][f"{k}|{'tip' if tip else 'cru'}"] = banco.placar_dict(p)
            saida.write(json.dumps(reg, ensure_ascii=False) + "\n")
            saida.flush()
            pl = reg["placar"]
            linha = " ".join(f"{k}={pl[k+'|tip']['erros']['prosa']/max(1,pl[k+'|tip']['total']['prosa']):.4f}"
                             for k in hip)
            print(f"  p{idx+1}: prosa_chars={pl['glifo|tip']['total']['prosa']} {linha} "
                  f"t_gl={t2-t1:.1f}s t_tess={t4-t3:.1f}s t_rap={t5-t4:.1f}s", flush=True)


if __name__ == "__main__":
    main()
