"""Auditoria da S-712: as caixas que saem da lista, com a regra ligada contra desligada, na mesma folha.

Uso (com o `.venv` do projeto, `PYTHONPATH=<arvore>/src` e `CVOFF_RAIZ` no checkout com `PDF/`):

  auditoria_das_caixas.py <detalhe.jsonl> <resumo.json> [folhas por livro]

`detalhe.jsonl` **tem texto de livro** (o que a camada e o Tesseract leem na caixa): fora do repositório. `resumo.json` só
tem contagens, e é o que `compilar.py` publica.

**Folha sem camada é metade do que importa**, e a primeira versão desta conta era cega ali: o que sai dela não toca palavra
nenhuma por construção. Por isso toda caixa de ao menos `ALTURA_LIDA` escalas passa também pelo Tesseract. Ele alucina em
foto, então o número é um teto, e cada caso se confere à vista.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from unittest import mock

import fitz
import numpy as np

from chess_diagram_ocr.detection.hybrid import detect_diagrams_in_pdf_page
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import gigantes, moldura, tesseract
from chess_diagram_ocr.text.leitor import segmentar

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(os.environ.get("CVOFF_RAIZ") or Path(__file__).resolve().parents[3])
DPI = 220
ALTURA_LIDA = 3.0
PALAVRA = re.compile(r"[^\W\d_]{3,}")


def _classe(caixa: tuple[int, int, int, int], escala: int, altura_da_folha: int) -> str:
    x1, y1, x2, y2 = caixa
    largura, altura = x2 - x1, y2 - y1
    if altura <= gigantes.ALTURA_DE_GRANDE * escala:
        return "mancha" if altura >= gigantes.LADO_DE_MANCHA * escala else "miolo_da_faixa"
    if altura >= gigantes.FRACAO_DA_FOLHA * altura_da_folha:
        return "faixa"
    if largura < gigantes.LARGURA_DE_FIO * escala:
        return "fio"
    return "moldura_aberta"


def _sem_a_regra(imagem: np.ndarray, retangulos: list[tuple[float, ...]]) -> set[tuple[int, int, int, int]]:
    with mock.patch.object(gigantes, "TIRAR_GIGANTES", False), mock.patch.object(
        moldura, "_miolo_da_faixa", lambda m: np.zeros(m.shape[:2], dtype=bool)
    ):
        return {(c.x1, c.y1, c.x2, c.y2) for c in segmentar(imagem, retangulos, dpi=DPI)[3]}


def main(detalhe: str, resumo: str, por_livro: int) -> None:
    s = DPI / 72
    motor = tesseract.achar_motor()
    vistos = set()
    folhas = com_caixa = sem_camada_com_caixa = 0
    classes: Counter[str] = Counter()
    tocam, em_folha_sem_camada, tess_leu = Counter(), Counter(), Counter()
    with open(detalhe, "w", encoding="utf-8") as f:
        for pdf in sorted(glob.glob(str(RAIZ / "PDF" / "*.pdf"))):
            chave = hashlib.sha256(Path(pdf).read_bytes()[: 1 << 20]).hexdigest()[:16]
            if chave in vistos:
                continue
            vistos.add(chave)
            with fitz.open(pdf) as doc:
                n = doc.page_count
            for i in sorted({int(k * (n - 1) / max(1, por_livro - 1)) for k in range(por_livro)}):
                imagem = render_pdf_page(pdf, i, dpi=DPI)
                retangulos = [tuple(v * s for v in c.bbox_pdf) for c in detect_diagrams_in_pdf_page(pdf, i, imagem)]
                _, _, escala, caixas, _ = segmentar(imagem, retangulos, dpi=DPI)
                folhas += 1
                fora = _sem_a_regra(imagem, retangulos) - {(c.x1, c.y1, c.x2, c.y2) for c in caixas}
                if not fora or escala <= 0:
                    continue
                com_caixa += 1
                with fitz.open(pdf) as doc:
                    palavras = doc[i].get_text("words")
                sem_camada_com_caixa += not palavras
                for caixa in sorted(fora):
                    x1, y1, x2, y2 = caixa
                    classe = _classe(caixa, escala, imagem.shape[0])
                    classes[classe] += 1
                    na_camada = [p[4] for p in palavras if p[0] * s < x2 and p[2] * s > x1 and p[1] * s < y2 and p[3] * s > y1]
                    tocam[classe] += bool(na_camada)
                    em_folha_sem_camada[classe] += not palavras
                    lido = ""
                    if y2 - y1 >= ALTURA_LIDA * escala:
                        recorte = imagem[y1:y2, x1:x2].mean(axis=2).astype(np.uint8)
                        lido = tesseract.ler_linhas([recorte], lingua="eng", dpi=DPI, motor=motor)[0].texto
                        tess_leu[classe] += bool(PALAVRA.search(lido))
                    f.write(json.dumps({"nome": os.path.basename(pdf), "pagina": i, "escala": escala, "caixa": caixa, "classe": classe,
                                        "camada": " ".join(na_camada)[:80], "tesseract": lido[:80]}, ensure_ascii=False) + "\n")
            print("livro", os.path.basename(pdf)[:40], n, flush=True)
    Path(resumo).write_bytes(json.dumps({
        "folhas_no_censo": folhas,
        "folhas_com_caixa_a_menos": com_caixa,
        "dessas_sem_camada": sem_camada_com_caixa,
        "caixas_a_menos": sum(classes.values()),
        "por_classe": dict(classes),
        "que_tocam_texto_da_camada": dict(tocam),
        "em_folha_sem_camada": dict(em_folha_sem_camada),
        "em_que_o_tesseract_le_palavra": dict(tess_leu),
        "nota": "o Tesseract roda só em caixa de ao menos 3 escalas, e alucina em foto: é teto, conferido à vista",
    }, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 14)
