"""Ablação dos interruptores do glifo: CER de prosa com cada etapa desligada."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import banco  # noqa: E402

from chess_diagram_ocr.pdf_io import render_pdf_page  # noqa: E402
from chess_diagram_ocr.text.leitor import ler_pagina  # noqa: E402
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer  # noqa: E402

PAGS = [("📚Hertan Charles. Forcing Chess Moves.pdf", "eng", 285),
        ("📚Hertan Charles. Forcing Chess Moves.pdf", "eng", 642),
        ("Minhas 60 partidas memoráveis Bobby Fischer pt-br algébrico.pdf", "por", 111),
        ("Minhas 60 partidas memoráveis Bobby Fischer pt-br algébrico.pdf", "por", 349),
        ("Dvoretsky - Dvoretsky's Endgame Manual (2025).pdf", "eng", 154),
        ("Melhores Finais de Capablanca - Irving Chernev pt-br - Copia.pdf", "por", 76),
        ("Xadrez Vitorioso - Finais - Yasser Seirawan.pdf", "por", 115)]
VARIANTES = {"producao": {}, "sem_marca_fina": {"marca_fina": False}, "sem_empilhados": {"empilhados": False},
             "sem_caixa_alta": {"caixa_alta": False}, "sem_dicionario": {"dicionario": False},
             "sem_traco": {"traco": False}, "colados_nunca": {"colados": "nunca"},
             "sem_italico": {"italico": False}, "sem_numeros": {"numeros": False},
             "sem_juntar_lance": {"juntar_lance": False}}
rec = build_glyph_recognizer()
tot = {k: [0, 0] for k in VARIANTES}
for nome, lang, idx in PAGS:
    pdf = os.path.join(os.environ.get("CVOFF_RAIZ", r"C:\Python-Chess2\ChessVisionOFF_Puro"), "PDF", nome)
    img = render_pdf_page(pdf, idx, 220)
    ler_pagina(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img)  # aquecimento
    ref = banco.normalizar(banco.texto_de([lin.texto for lin in banco.linhas_da_pagina(
        ler_pagina(pdf, idx, motor="camada", imagem_rgb=img))]), tipografia=True, lang=lang)
    linha = []
    for k, kw in VARIANTES.items():
        p = ler_pagina(pdf, idx, motor="glifo", reconhecedor=rec, imagem_rgb=img, **kw)
        h = banco.normalizar(banco.texto_de([lin.texto for lin in banco.linhas_da_pagina(p)]), tipografia=True, lang=lang)
        pl = banco.pontuar(ref, h)
        tot[k][0] += pl.erros["prosa"]
        tot[k][1] += pl.total["prosa"]
        linha.append(f"{k}={pl.cer('prosa'):.4f}")
    print(nome[:20], idx + 1, " ".join(linha), flush=True)
print(json.dumps({k: round(e / max(1, t), 4) for k, (e, t) in tot.items()}, indent=1))
