"""Censo: livros com camada de texto e as páginas de exercícios/soluções de cada um."""
import json
import re
import sys
from pathlib import Path

import pymupdf

#: Título de página de exercícios ou de soluções, nas línguas do acervo.
TITULO = re.compile(
    r"^\s*(solutions?|exercises?|test(?:s)?|answers?|puzzles?|soluciones|ejercicios|"
    r"solu[cç][oõ]es|exerc[ií]cios|l[oö]sungen|aufgaben|solu[tţ]ii)\b",
    re.IGNORECASE | re.MULTILINE,
)
#: Rótulo de exercício numerado: «Ex. 6-10», «Exercise 12», «Ejercicio 3».
ROTULO = re.compile(r"\b(Ex\.\s*\d+[-.]\d+|Exercise\s+\d+|Ejercicio\s+\d+|Exerc[ií]cio\s+\d+)\b")

saida = {}
pdfs = sorted(Path("PDF").glob("*.pdf")) + [Path(p) for p in sys.argv[1:]]
for pdf in pdfs:
    try:
        doc = pymupdf.open(pdf)
    except Exception as exc:  # noqa: BLE001
        print(f"{pdf.name}: não abriu ({exc})")
        continue
    n = doc.page_count
    com_texto = exerc = 0
    paginas = []
    for i in range(n):
        texto = doc[i].get_text()
        if len(texto.strip()) < 200:
            continue
        com_texto += 1
        if TITULO.search(texto) or len(ROTULO.findall(texto)) >= 2:
            exerc += 1
            paginas.append(i)
    saida[str(pdf)] = {"paginas": n, "com_texto": com_texto, "exercicios": paginas}
    print(f"{pdf.name[:60]:60s} {n:5d} pág  camada {com_texto:5d}  exerc/sol {exerc:4d}", flush=True)
Path(sys.argv[0]).with_name("censo.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
