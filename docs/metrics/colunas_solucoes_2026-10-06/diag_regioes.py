"""Diagnóstico: as regiões e calhas que o caminho do glifo acha numa página, e por quê."""
import sys

import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[0]).parent))
import patch_colunas  # noqa: E402,F401

from chess_diagram_ocr.detection.hybrid import detect_diagrams_in_pdf_page
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import regioes as R
from chess_diagram_ocr.text.colunas import piso_de_calha
from chess_diagram_ocr.text.leitor import segmentar
from chess_diagram_ocr.text.linhas import bandas

pdf, indice = sys.argv[1], int(sys.argv[2])
dpi = 220
img = render_pdf_page(pdf, indice, dpi=dpi)
esc = dpi / 72.0
cands = detect_diagrams_in_pdf_page(pdf, indice, img)
rets = [tuple(v * esc for v in c.bbox_pdf) for c in cands]
_, _, escala, caixas, regioes = segmentar(img, rets)
print(f"escala {escala}  caixas {len(caixas)}  piso {piso_de_calha(caixas)} px  diagramas {len(rets)}")
grupos = bandas(caixas)
print(f"bandas {len(grupos)}")
for r in regioes:
    cols = [(round(a / esc), round(b / esc)) for a, b in r.colunas]
    print(f"regiao y {r.topo / esc:.0f}-{r.base / esc:.0f} pt  colunas(pt) {cols}")
    # bandas desta região e a extensão em x de cada uma
    for g in grupos:
        topo = min(c.y1 for c in g)
        if not (r.topo <= topo <= r.base):
            continue
        xs = sorted((c.x1, c.x2) for c in g)
        # trechos contíguos da banda (fundindo vãos menores que 3x o piso)
        trechos = []
        for a, b in xs:
            if trechos and a - trechos[-1][1] < 3 * piso_de_calha(caixas):
                trechos[-1][1] = max(trechos[-1][1], b)
            else:
                trechos.append([a, b])
        print(f"   y {topo / esc:5.0f}  " + " ".join(f"[{a / esc:.0f}-{b / esc:.0f}]" for a, b in trechos))
