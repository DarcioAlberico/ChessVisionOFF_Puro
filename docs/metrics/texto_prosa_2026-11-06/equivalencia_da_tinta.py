"""A S-712 mudou `TINTA_DE_MANCHA` de 0,8 a 0,9 depois de medir. Em quais folhas medidas alguma caixa muda?

Uso (com o `.venv` do projeto, `PYTHONPATH=<arvore>/src` e `CVOFF_RAIZ` no checkout com `PDF/`):

  equivalencia_da_tinta.py <pasta dos JSONL> <saida.json>

Toda leitura sai das caixas de `segmentar`: folha em que a lista é a mesma com os dois limites dá o mesmo número, e o relatório medido
continua valendo nela. A saída não tem texto de livro.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from pathlib import Path

import fitz
import numpy as np

from chess_diagram_ocr.detection.hybrid import detect_diagrams_in_pdf_page
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import gigantes
from chess_diagram_ocr.text.leitor import segmentar

RAIZ = Path(os.environ.get("CVOFF_RAIZ") or Path(__file__).resolve().parents[3])
DPI = 220
POR_LIVRO = 14
MEDIDAS = ("nv_depois", "ce_depois", "ouro_depois", "prata_depois", "perdidas", "amostra_ce")


def folhas_medidas(pasta: str) -> set[tuple[str, int]]:
    """As folhas dos JSONL e as do censo e da varredura, que são 14 espaçadas por livro."""
    folhas = set()
    for nome in MEDIDAS:
        for r in map(json.loads, open(f"{pasta}/{nome}.jsonl", encoding="utf-8")):
            folhas.add((r.get("nome") or r["livro"], r["pagina"]))
    vistos = set()
    for pdf in sorted(glob.glob(str(RAIZ / "PDF" / "*.pdf"))):
        chave = hashlib.sha256(Path(pdf).read_bytes()[: 1 << 20]).hexdigest()[:16]
        if chave in vistos:
            continue
        vistos.add(chave)
        with fitz.open(pdf) as doc:
            n = doc.page_count
        folhas |= {(os.path.basename(pdf), int(k * (n - 1) / (POR_LIVRO - 1))) for k in range(POR_LIVRO)}
    return folhas


def main(pasta: str, saida: str) -> None:
    folhas = folhas_medidas(pasta)
    s = DPI / 72
    mudam = []
    for nome, i in sorted(folhas):
        pdf = str(RAIZ / "PDF" / nome)
        imagem = render_pdf_page(pdf, i, dpi=DPI)
        retangulos = [tuple(v * s for v in c.bbox_pdf) for c in detect_diagrams_in_pdf_page(pdf, i, imagem)]
        lados = {}
        for limite in (0.8, 0.9):
            gigantes.TINTA_DE_MANCHA = limite
            lados[limite] = segmentar(imagem, retangulos, dpi=DPI)
        caixas = {k: {(c.x1, c.y1, c.x2, c.y2) for c in v[3]} for k, v in lados.items()}
        for c in sorted(caixas[0.8] ^ caixas[0.9]):
            recorte = lados[0.8][1][c[1]:c[3], c[0]:c[2]]
            tinta = round(float(np.count_nonzero(recorte)) / max(1, recorte.size), 3)
            mudam.append({"livro": nome, "pagina": i, "caixa": list(c), "escala": lados[0.8][2], "tinta": tinta})
    Path(saida).write_bytes(json.dumps({
        "o_que": "TINTA_DE_MANCHA de 0,8 a 0,9, depois de medir",
        "folhas_conferidas": len(folhas),
        "caixas_que_mudam": mudam,
        "nota": "fora dessas folhas a lista de caixas é a mesma, e o número medido vale; o censo, a auditoria e a varredura contam o limite de 0,8",
    }, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
