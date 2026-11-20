"""G3: toda folha do acervo pelo glifo e pela guarda da S-710. Só contagens por folha, sem texto de livro.

    python varredura.py <saida fora do repositório>            # a varredura; retoma de onde parou
    python varredura.py <saida> --camada                       # as suspeitas contra a camada montada

Da raiz do checkout com os PDFs, ou com `CVOFF_RAIZ` apontando para ela. Num worktree, `PYTHONPATH=<worktree>/src`.
"""

from __future__ import annotations

import glob
import json
import multiprocessing as mp
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

RAIZ = Path(os.environ.get("CVOFF_RAIZ", "."))
TRABALHADORES = 5


def um_livro(args: tuple[str, Path]) -> str:
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    import fitz

    from chess_diagram_ocr.text.leitor import ler_pagina
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    pdf, saida = args
    rec = build_glyph_recognizer(str(RAIZ / "models/char_classifier.pt"))
    nome = Path(pdf).stem
    feito = set()
    for j in saida.glob("*.jsonl"):
        with j.open(encoding="utf-8") as f:
            for linha in f:
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                if d.get("livro") == nome:
                    feito.add(d["folha"])
    doc = fitz.open(pdf)
    with (saida / f"{os.getpid()}_{time.time_ns()}.jsonl").open("a", encoding="utf-8") as arquivo:
        for i in range(doc.page_count):
            if i in feito:
                continue
            t = time.perf_counter()
            reg = {"livro": nome, "folha": i}
            try:
                camada = doc[i].get_text()
                reg["camada_chars"] = len(camada.strip())
                reg["camada_linhas"] = sum(1 for x in camada.splitlines() if x.strip())
                lida = ler_pagina(pdf, i, dpi=220, motor="glifo", reconhecedor=rec)
                reg["lidos"] = len(lida.texto())
                reg["linhas"] = lida.texto().count("\n") + 1
                reg["avisos"] = [a.codigo for a in lida.avisos]
            except Exception as e:  # noqa: BLE001 - a exceção é o que se mede
                reg["erro"] = f"{type(e).__name__}: {e}"[:200]
            reg["segundos"] = round(time.perf_counter() - t, 2)
            arquivo.write(json.dumps(reg, ensure_ascii=False) + "\n")
            arquivo.flush()
    return nome


def um_livro_na_camada(args: tuple[str, list[dict]]) -> list[dict]:
    from chess_diagram_ocr.text.leitor import ler_pagina

    livro, regs = args
    saida = []
    for r in regs:
        lida = ler_pagina(str(RAIZ / "PDF" / f"{livro}.pdf"), r["folha"], dpi=220, motor="camada")
        saida.append({"livro": livro, "folha": r["folha"], "camada_chars": r["camada_chars"], "lidos": r["lidos"], "montada": len(lida.texto())})
    return saida


def varrer(saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    livros = [(p, saida) for p in sorted(glob.glob(str(RAIZ / "PDF" / "*.pdf")))]
    with mp.get_context("spawn").Pool(TRABALHADORES, maxtasksperchild=1) as pool:
        for n, nome in enumerate(pool.imap_unordered(um_livro, livros), 1):
            print(n, nome[:60], time.strftime("%H:%M:%S"), flush=True)


def suspeitas_na_camada(saida: Path) -> None:
    """A contagem crua da camada inclui o tabuleiro desenhado em fonte. A suspeita passa pela camada montada."""
    regs = [json.loads(linha) for f in saida.glob("*.jsonl") for linha in f.open(encoding="utf-8")]
    suspeitas = defaultdict(list)
    for r in regs:
        if "erro" not in r and r["camada_chars"] >= 50 and r["lidos"] < 0.6 * r["camada_chars"] and not r["avisos"]:
            suspeitas[r["livro"]].append(r)
    with mp.get_context("spawn").Pool(TRABALHADORES, maxtasksperchild=1) as pool, (saida.parent / "camada.jsonl").open("w", encoding="utf-8") as f:
        for lote in pool.imap_unordered(um_livro_na_camada, list(suspeitas.items())):
            for d in lote:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if "--camada" in sys.argv:
        suspeitas_na_camada(Path(sys.argv[1]))
    else:
        varrer(Path(sys.argv[1]))
