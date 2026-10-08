"""Nas páginas «Solutions» do Yusupov a resposta é conhecida: duas colunas.

Para cada rodada (jsonl de medir_colunas.py), quantas páginas de soluções do Yusupov a aba lê com
alguma região de duas colunas -- separadas as que têm o quadro «Scoring» (fim de capítulo).
"""
import json
import sys

import pymupdf

Y = "📚Yusupov Artur. Build Up Your Chess (all volumes).pdf"
doc = pymupdf.open("C:/Python-Chess2/ChessVisionOFF_Puro/PDF/" + Y)


def tipo(pagina):
    texto = doc[pagina - 1].get_text()
    if "Solutions" not in texto:
        return None
    return "scoring" if "Scoring" in texto else "solucoes"


def duas_colunas(r):
    """Alguma faixa horizontal tem duas colunas lado a lado?"""
    cols = r["cols"]
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            lado = a[2] <= b[0] + 2 or b[2] <= a[0] + 2
            sobrepoe_y = min(a[3], b[3]) - max(a[1], b[1]) > 0.3 * min(a[3] - a[1], b[3] - b[1])
            largas = min(a[2] - a[0], b[2] - b[0]) > 120
            if lado and sobrepoe_y and largas:
                return True
    return False


for caminho in sys.argv[1:]:
    linhas = [json.loads(x) for x in open(caminho, encoding="utf-8")]
    conta = {"solucoes": [0, 0], "scoring": [0, 0]}
    for r in linhas:
        if r.get("pdf") != Y or "cols" not in r:
            continue
        t = tipo(r["pagina"])
        if t is None:
            continue
        conta[t][1] += 1
        conta[t][0] += duas_colunas(r)
    print(f"{caminho:28s} soluções: {conta['solucoes'][0]}/{conta['solucoes'][1]} em duas colunas;"
          f"  com Scoring: {conta['scoring'][0]}/{conta['scoring'][1]}")
