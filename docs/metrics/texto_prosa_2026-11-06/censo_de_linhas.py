"""Censo da S-712: linhas acima de 1,8 mediana da tira, em folhas espaçadas do acervo, sem classificador.

Uso (com o `.venv` do projeto, `PYTHONPATH=<arvore>/src` e `CVOFF_RAIZ` no checkout com `PDF/`):

  censo_de_linhas.py <saida.jsonl> [folhas por livro]
  censo_de_linhas.py --ouro <medido.jsonl>     as folhas de um JSONL do medir.py, e a contagem da Saída do roadmap

A saída não tem texto de livro: só contagens, nomes de arquivo e retângulos. Mesmo assim, fora do repositório.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import statistics
import sys
from pathlib import Path

from chess_diagram_ocr.detection.hybrid import detect_diagrams_in_pdf_page
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text.duas_linhas import descartar_fragmentos, partir_linhas_altas
from chess_diagram_ocr.text.leitor import _tiras, segmentar
from chess_diagram_ocr.text.linhas import envolve, ordem_em_faixa, quebrar_em_linhas

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(os.environ.get("CVOFF_RAIZ") or Path(__file__).resolve().parents[3])
DPI = 220
ALTA = 1.8


def medir_folha(pdf: str, indice: int) -> tuple[int, list[dict], int]:
    """(linhas, as altas, escala) de uma folha, pelo mesmo caminho de `leitor.linhas_do_glifo`, sem o classificador."""
    imagem = render_pdf_page(pdf, indice, dpi=DPI)
    s = DPI / 72
    retangulos = [tuple(v * s for v in c.bbox_pdf) for c in detect_diagrams_in_pdf_page(pdf, indice, imagem)]
    _, _, escala, caixas, regioes = segmentar(imagem, retangulos, dpi=DPI)
    if not caixas:
        return 0, [], escala
    total, altas = 0, []
    for _regiao, _coluna, desta in _tiras(caixas, regioes):
        grupos = descartar_fragmentos(partir_linhas_altas(quebrar_em_linhas(ordem_em_faixa(desta))), escala=escala)
        alturas = [envolve(g)[3] - envolve(g)[1] for g in grupos]
        if not alturas:
            continue
        mediana = statistics.median(alturas)
        total += len(grupos)
        altas.extend(
            {"h": h, "mediana": mediana, "caixas": len(g), "maior_em_escalas": round(max(c.altura for c in g) / escala, 2)}
            for g, h in zip(grupos, alturas, strict=True)
            if h > ALTA * mediana
        )
    return total, altas, escala


def censo(saida: str, por_livro: int) -> None:
    import fitz

    vistos = set()
    with open(saida, "w", encoding="utf-8") as f:
        for pdf in sorted(glob.glob(str(RAIZ / "PDF" / "*.pdf"))):
            chave = hashlib.sha256(Path(pdf).read_bytes()[: 1 << 20]).hexdigest()[:16]
            if chave in vistos:
                continue
            vistos.add(chave)
            with fitz.open(pdf) as doc:
                n = doc.page_count
            for i in sorted({int(k * (n - 1) / max(1, por_livro - 1)) for k in range(por_livro)}):
                try:
                    total, altas, escala = medir_folha(pdf, i)
                except Exception as exc:  # noqa: BLE001 - uma folha ruim não derruba o censo
                    print("falhou", os.path.basename(pdf)[:30], i, exc, flush=True)
                    continue
                f.write(json.dumps({"nome": os.path.basename(pdf), "pagina": i, "escala": escala, "linhas": total, "altas": altas}, ensure_ascii=False) + "\n")
                f.flush()
            print("livro", os.path.basename(pdf)[:40], n, flush=True)


def ouro(medido: str) -> None:
    linhas = altas = 0
    for registro in map(json.loads, open(medido, encoding="utf-8")):
        total, destas, _ = medir_folha(str(RAIZ / "PDF" / registro["livro"]), registro["pagina"])
        linhas += total
        altas += len(destas)
    print(json.dumps({"linhas": linhas, "altas": altas}))


if __name__ == "__main__":
    if sys.argv[1] == "--ouro":
        ouro(sys.argv[2])
    else:
        censo(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 14)
