"""Sinais candidatos para a guarda de leitura incompleta (S-710), medidos folha a folha.

A: cobertura da tinta fora dos diagramas pelas caixas de linha (a versão literal da S-710 -- o
   crítico da rodada 5 mostrou que ela falha: a caixa degenerada cobre a folha inteira);
B: densidade de leitura = caracteres lidos / componentes de tinta fora dos diagramas;
C: caixa degenerada = altura da maior linha / mediana das alturas de linha.

Uso: cobertura.py saida.tsv entrada1.jsonl [entrada2.jsonl ...]
"""
import json
import os
import sys

import cv2
import numpy as np

# o checkout que tem PDF/ e models/: CVOFF_RAIZ, ou o repositório onde este script mora
RAIZ = os.environ.get("CVOFF_RAIZ") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def main(sai, *ents):
    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text.leitor import ler_pagina
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import banco
    rec = build_glyph_recognizer()
    vistos = set()
    with open(sai, "w", encoding="utf-8") as f:
        f.write("conjunto\tlivro\tfolha\tlinhas_camada\tlinhas_glifo\tA_cobertura\tB_densidade\tC_degenerada\n")
        for ent in ents:
            for linha in open(ent, encoding="utf-8"):
                r = json.loads(linha)
                k = (r["livro"], r["pagina"], r.get("degradar", ""))
                if k in vistos:
                    continue
                vistos.add(k)
                pdf = os.path.join(RAIZ, "PDF", r["livro"])
                img = render_pdf_page(pdf, r["pagina"], 220)
                if r.get("degradar"):
                    import degradar
                    img = degradar.aplicar(img, r["degradar"], semente=r["pagina"])
                pag = ler_pagina(pdf, r["pagina"], motor="glifo", reconhecedor=rec, imagem_rgb=img)
                s = 220 / 72
                g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                for d in pag.diagramas:
                    x0, y0, x1, y1 = [int(v * s) for v in d.bbox]
                    bw[max(0, y0 - 8):y1 + 8, max(0, x0 - 8):x1 + 8] = 0
                tinta = bw > 0
                coberta = np.zeros_like(tinta)
                linhas = banco.linhas_da_pagina(pag)
                alturas = []
                for ln in linhas:
                    x0, y0, x1, y1 = [int(v * s) for v in ln.bbox]
                    coberta[max(0, y0):y1, max(0, x0):x1] = True
                    alturas.append(max(1, y1 - y0))
                a = (tinta & coberta).sum() / max(1, tinta.sum())
                n, _, st, _ = cv2.connectedComponentsWithStats(bw.astype(np.uint8), connectivity=8)
                comps = int(((st[1:, cv2.CC_STAT_AREA] >= 6) & (st[1:, cv2.CC_STAT_HEIGHT] >= 4)).sum())
                lidos = sum(len(ln.texto.replace(" ", "")) for ln in linhas)
                b = lidos / max(1, comps)
                c = max(alturas) / max(1.0, float(np.median(alturas))) if alturas else 0.0
                conj = os.path.basename(ent).split(".")[0]
                f.write(f"{conj}\t{r['livro'][:30]}\t{r['pagina'] + 1}\t{r['n_linhas']['ref']}\t{len(linhas)}\t"
                        f"{a:.3f}\t{b:.3f}\t{c:.1f}\n")
                f.flush()


if __name__ == "__main__":
    main(*sys.argv[1:])
