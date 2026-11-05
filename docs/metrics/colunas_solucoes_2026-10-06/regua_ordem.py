"""A régua S-194 do tronco (cli.texto_ordem.medir_pagina), página a página, numa variante.

Uso: COLUNAS_VARIANTE=p123 python regua_ordem.py saida.jsonl [por_livro]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[0]).parent))
import patch_colunas  # noqa: E402,F401
import pymupdf  # noqa: E402

from chess_diagram_ocr.cli.texto_ordem import medir_pagina  # noqa: E402

saida = Path(sys.argv[1])
por_livro = int(sys.argv[2]) if len(sys.argv) > 2 else 30
pdfs = sorted(Path("PDF").glob("*.pdf")) + [
    Path("C:/Users/AMD/Downloads/Telegram Desktop/Dvoretsky,_Mark_&_Yusupov,_Artur_SFC4_Secrets_of_Positional_Play.pdf")]
with saida.open("w", encoding="utf-8") as out:
    for pdf in pdfs:
        try:
            doc = pymupdf.open(pdf)
        except Exception:  # noqa: BLE001
            continue
        n = doc.page_count
        inicio = int(n * 0.15)
        passo = max(1, (n - inicio) // por_livro)
        for i in range(inicio, n, passo):
            try:
                r = medir_pagina(doc[i])
            except Exception as exc:  # noqa: BLE001
                out.write(json.dumps({"pdf": pdf.name, "pagina": i + 1, "erro": str(exc)[:120]}) + "\n")
                continue
            if r is None:
                continue
            out.write(json.dumps({
                "pdf": pdf.name, "pagina": i + 1, "linhas": r.linhas, "tau": round(r.tau, 4),
                "colunas": r.colunas, "regioes": r.regioes,
                "confiavel": r.descidas_da_referencia <= r.subidas_previstas,
                "descidas": r.descidas_da_referencia, "subidas": r.subidas_previstas,
            }, ensure_ascii=False) + "\n")
print("ok", saida)
