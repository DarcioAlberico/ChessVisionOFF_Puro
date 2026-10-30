"""Tesseract na PÁGINA INTEIRA, com o leiaute dele (psm 3), diagramas mascarados de branco.

Acrescenta hip['tess_pagina'] a um JSONL do banco e repontua. Serve para saber se o leiaute do próprio
Tesseract é opinante melhor que as caixas de linha do glifo (Fase 101).

Uso: tess_pagina.py entrada.jsonl saida.jsonl [psm]
"""
import json
import os
import subprocess
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banco  # noqa: E402

RAIZ = os.environ.get("CVOFF_RAIZ", r"C:\Python-Chess2\ChessVisionOFF_Puro")


def main(ent, sai, psm="3"):
    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text.leitor import ler_pagina
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer
    rec = build_glyph_recognizer()
    with open(sai, "w", encoding="utf-8") as f:
        for linha in open(ent, encoding="utf-8"):
            r = json.loads(linha)
            pdf = os.path.join(RAIZ, "PDF", r["livro"])
            img = render_pdf_page(pdf, r["pagina"], 220)
            ref_pag = ler_pagina(pdf, r["pagina"], motor="camada", imagem_rgb=img)
            gl_pag = ler_pagina(pdf, r["pagina"], motor="glifo", reconhecedor=rec, imagem_rgb=img)
            s = 220 / 72
            g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            for d in list(ref_pag.diagramas) + list(gl_pag.diagramas):
                x0, y0, x1, y1 = [int(v * s) for v in d.bbox]
                g[max(0, y0 - 8):y1 + 8, max(0, x0 - 8):x1 + 8] = 255
            ok, png = cv2.imencode(".png", g)
            out = subprocess.run([banco.TESS, "stdin", "stdout", "-l", r["lang"], "--psm", psm, "--dpi", "220"],
                                 input=png.tobytes(), capture_output=True)
            r["hip"]["tess_pagina"] = out.stdout.decode("utf-8", "replace")
            for tip in (True, False):
                ref = banco.normalizar(r["ref"], tipografia=tip, lang=r["lang"])
                p = banco.pontuar(ref, banco.normalizar(r["hip"]["tess_pagina"], tipografia=tip, lang=r["lang"]))
                r["placar"][f"tess_pagina|{'tip' if tip else 'cru'}"] = banco.placar_dict(p)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(r["livro"][:24], r["pagina"] + 1, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
