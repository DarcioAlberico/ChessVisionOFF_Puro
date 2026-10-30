"""Refaz partes de um JSONL do banco sem rodar o glifo de novo no texto:
- recalcula `fusao_v4` a partir das linhas gravadas (`hip_linhas`);
- com --oraculo, refaz `tess_oraculo` (renderiza, lê a camada e o glifo só para os diagramas,
  junta as linhas visuais com `banco.caixas_visuais` atual e roda o Tesseract);
- e repontua tudo.

Uso: refazer.py entrada.jsonl saida.jsonl [--oraculo]
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banco  # noqa: E402
import rodar  # noqa: E402

RAIZ = os.environ.get("CVOFF_RAIZ", r"C:\Python-Chess2\ChessVisionOFF_Puro")


def main(ent, sai, oraculo):
    if oraculo:
        from chess_diagram_ocr.pdf_io import render_pdf_page
        from chess_diagram_ocr.text.leitor import ler_pagina
        from chess_diagram_ocr.text.recognizer import build_glyph_recognizer
        rec = build_glyph_recognizer()
        pool = ThreadPoolExecutor(max_workers=10)
    with open(sai, "w", encoding="utf-8") as f:
        for linha in open(ent, encoding="utf-8"):
            r = json.loads(linha)
            gl, ts = r["hip_linhas"]["glifo"], r["hip_linhas"]["tess"]
            r["hip"]["fusao_v4"] = banco.texto_de([rodar.fundir_v4(a, b) for a, b in zip(gl, ts, strict=False)])
            if oraculo:
                pdf = os.path.join(RAIZ, "PDF", r["livro"])
                img = render_pdf_page(pdf, r["pagina"], 220)
                if r.get("degradar"):
                    import degradar
                    img = degradar.aplicar(img, r["degradar"], semente=r["pagina"])
                ref_pag = ler_pagina(pdf, r["pagina"], motor="camada", imagem_rgb=img)
                gl_pag = ler_pagina(pdf, r["pagina"], motor="glifo", reconhecedor=rec, imagem_rgb=img)
                diag = [d.bbox for d in ref_pag.diagramas] + [d.bbox for d in gl_pag.diagramas]
                ref_l = [ln for ln in banco.linhas_da_pagina(ref_pag) if not banco.cruza_diagrama(ln.bbox, diag)]
                ref_txt = banco.texto_de([ln.texto for ln in ref_l])
                assert ref_txt == r["ref"], "a referencia mudou: " + r["livro"]
                vis = banco.caixas_visuais(ref_l, img, 220)
                crops = [banco.recortar(img, bb, 220) for bb, _ in vis]
                r["hip"]["tess_oraculo"] = banco.texto_de(
                    [t for t, _ in pool.map(lambda c, lang=r["lang"]: banco.tess_linha(c, lang), crops)])
                r["n_linhas"]["oraculo_visuais"] = len(vis)
            for tip in (True, False):
                ref = banco.normalizar(r["ref"], tipografia=tip, lang=r["lang"])
                for k, v in r["hip"].items():
                    p = banco.pontuar(ref, banco.normalizar(v, tipografia=tip, lang=r["lang"]))
                    r["placar"][f"{k}|{'tip' if tip else 'cru'}"] = banco.placar_dict(p)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(r["livro"][:30], r["pagina"] + 1, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--oraculo" in sys.argv[3:])
