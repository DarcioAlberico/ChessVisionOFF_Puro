import sys

import cv2

from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text.leitor import ler_pagina
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

pdf, idx, saida = sys.argv[1], int(sys.argv[2]), sys.argv[3]
img = render_pdf_page(pdf, idx, 220)
rec = build_glyph_recognizer()
p = ler_pagina(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img)
print("dims", img.shape, "colunas", len(p.colunas))
for c in p.colunas:
    for b in c.blocos:
        print(" ", b.tipo, [round(v) for v in b.bbox], (b.texto if isinstance(getattr(b,"texto",""),str) else b.texto())[:80].replace("\n", " | "))
s = 220/72
for b in p.blocos:
    x0,y0,x1,y1 = [int(v*s) for v in b.bbox]
    cv2.rectangle(img, (x0,y0), (x1,y1), (255,0,0) if b.tipo=="diagrama" else (0,160,0), 4)
ok, png = cv2.imencode(".png", cv2.resize(img, None, fx=0.4, fy=0.4)[:, :, ::-1])
open(saida, "wb").write(png.tobytes())
