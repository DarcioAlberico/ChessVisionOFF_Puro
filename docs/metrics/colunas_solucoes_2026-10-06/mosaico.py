"""Mosaico: as colunas que a aba Texto (glifo) acha, desenhadas sobre as páginas marcadas."""
import json
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(sys.argv[0]).parent))
import patch_colunas  # noqa: E402,F401
from chess_diagram_ocr.text.leitor import ler_pagina  # noqa: E402

SP = Path(sys.argv[0]).parent
censo = json.loads((SP / "censo.json").read_text(encoding="utf-8"))
caminho_de = {Path(k).name: k for k in censo}
alvos = [tuple(a.split("|")) for a in sys.argv[2:]]  # "livro|pagina"
saida = sys.argv[1]
CORES = ["#e11d48", "#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#4d7c0f"]
quadros = []
for livro, pagina in alvos:
    caminho = caminho_de[livro]
    i = int(pagina) - 1
    lida = ler_pagina(caminho, i, motor="glifo")
    pix = pymupdf.open(caminho)[i].get_pixmap(dpi=55)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d = ImageDraw.Draw(im)
    k = 55 / 72
    for col in lida.colunas:
        x0, y0, x1, y1 = (v * k for v in col.bbox)
        cor = CORES[col.indice % len(CORES)]
        d.rectangle([x0, y0, x1, y1], outline=cor, width=2)
        d.text((x0 + 2, y0 + 1), str(col.indice), fill=cor)
    d.text((3, im.height - 12), f"{livro[:22]} p{pagina} [{patch_colunas.VARIANTE or 'hoje'}]", fill="#000")
    quadros.append(im)
W = sum(q.width for q in quadros) + 8 * len(quadros)
H = max(q.height for q in quadros)
o = Image.new("RGB", (W, H), "white")
x = 0
for q in quadros:
    o.paste(q, (x, 0))
    x += q.width + 8
o.save(saida)
