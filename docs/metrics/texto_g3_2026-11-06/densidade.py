"""O corte do aviso `leitura_com_ruido`: a densidade de leitura nas folhas que podem disparar. Só contagens, sem texto de livro.

    python densidade.py amostra <varredura> <pasta>   # pelo ler_pagina: toda folha com 3.000+ lidos, e 15 sorteadas por livro
    python densidade.py cota <varredura> <pasta>      # o resto com 300+ lidos: componentes reais, sem o classificador
    python densidade.py reler <pasta>                 # as candidatas da cota, de novo pelo ler_pagina

`<varredura>` é a pasta de `varredura.py`; `<pasta>`, fora do repositório, recebe `saida/`, `cota/` e
`candidatas_relidas.json`. Da raiz do checkout com os PDFs, ou com `CVOFF_RAIZ` apontando para ela; num worktree,
`PYTHONPATH=<worktree>/src`. As duas primeiras retomam de onde pararam.

**A cota evita ler 18 mil folhas de novo.** O que a varredura contou nunca é menos do que a guarda conta, então
lidos da varredura ÷ componentes é um teto da densidade: folha abaixo do corte por esse teto não dispara. Folha com menos
de 300 lidos não chega ao mínimo de 500, e nem entra.
"""

from __future__ import annotations

import glob
import json
import multiprocessing as mp
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

RAIZ = Path(os.environ.get("CVOFF_RAIZ", "."))
TRABALHADORES = 5
SEMENTE = 20261107
CORTE = 4.0


def _jsonl(pasta: Path) -> list[dict]:
    regs = []
    for arquivo in pasta.glob("*.jsonl"):
        with arquivo.open(encoding="utf-8") as f:
            regs += [json.loads(linha) for linha in f]
    return regs


def _varredura(pasta: Path) -> list[dict]:
    regs = []
    for arquivo in glob.glob(str(pasta / "*.jsonl")):
        with open(arquivo, encoding="utf-8") as f:
            regs += [json.loads(linha) for linha in f]
    return regs


def _espiar_a_guarda() -> dict:
    """Guarda a última `Medida`: é só nela que estão os componentes."""
    from chess_diagram_ocr.text import guarda_de_leitura as g

    ultima: dict = {}
    original = g.medir

    def medir(*a, **k):
        ultima["m"] = original(*a, **k)
        return ultima["m"]

    g.medir = medir
    return ultima


def _amostra_um(args: tuple[str, list[tuple[int, str]], Path]) -> str:
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    from chess_diagram_ocr.text import leitor
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    livro, folhas, saida = args
    rec = build_glyph_recognizer(str(RAIZ / "models/char_classifier.pt"))
    pdf = str(RAIZ / "PDF" / f"{livro}.pdf")
    ultima = _espiar_a_guarda()
    with (saida / f"{os.getpid()}_{time.time_ns()}.jsonl").open("a", encoding="utf-8") as f:
        for i, origem in folhas:
            r: dict = {"livro": livro, "folha": i, "origem": origem}
            try:
                ultima.clear()
                p = leitor.ler_pagina(pdf, i, dpi=220, motor="glifo", reconhecedor=rec)
                r.update(texto=len(p.texto()), avisos=[a.codigo for a in p.avisos])
                if m := ultima.get("m"):
                    r.update(
                        comp=m.componentes,
                        lidos=m.lidos,
                        linhas=m.linhas_lidas,
                        est=m.linhas_estimadas,
                        camada=m.caracteres_da_camada,
                        ruido=m.ruido,
                        dens=round(m.densidade, 4),
                    )
            except Exception as e:  # uma folha ruim não para a medição, e o erro fica no registro
                r["erro"] = repr(e)[:200]
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
    return livro


def _cota_um(args: tuple[str, list[tuple[int, int]], Path]) -> str:
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    from chess_diagram_ocr.text import leitor

    livro, folhas, saida = args
    pdf = str(RAIZ / "PDF" / f"{livro}.pdf")
    ultima = _espiar_a_guarda()
    leitor.linhas_do_glifo = lambda *a, **k: ([], None)
    with (saida / f"{os.getpid()}_{time.time_ns()}.jsonl").open("a", encoding="utf-8") as f:
        for i, lidos in folhas:
            r: dict = {"livro": livro, "folha": i, "texto": lidos}
            try:
                ultima.clear()
                leitor.ler_pagina(pdf, i, dpi=220, motor="glifo", reserva=False)
                r["comp"] = ultima["m"].componentes
                r["camada"] = ultima["m"].caracteres_da_camada
            except Exception as e:
                r["erro"] = repr(e)[:200]
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
    return livro


def _reler_um(args: tuple[str, list[int]]) -> list[dict]:
    from chess_diagram_ocr.text import leitor
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    livro, folhas = args
    rec = build_glyph_recognizer(str(RAIZ / "models/char_classifier.pt"))
    pdf = str(RAIZ / "PDF" / f"{livro}.pdf")
    ultima = _espiar_a_guarda()
    saida = []
    for i in folhas:
        ultima.clear()
        p = leitor.ler_pagina(pdf, i, dpi=220, motor="glifo", reconhecedor=rec)
        r: dict = {"livro": livro, "folha": i, "texto": len(p.texto()), "avisos": [a.codigo for a in p.avisos]}
        if m := ultima.get("m"):
            r.update(comp=m.componentes, lidos=m.lidos, dens=round(m.densidade, 3), camada=m.caracteres_da_camada)
        saida.append(r)
    return saida


def _rodar(funcao, tarefas: list) -> list:
    with mp.get_context("spawn").Pool(TRABALHADORES, maxtasksperchild=1) as pool:
        return list(pool.imap_unordered(funcao, tarefas))


def amostra(varredura: Path, pasta: Path) -> None:
    saida = pasta / "saida"
    saida.mkdir(parents=True, exist_ok=True)
    feitas = {(d["livro"], d["folha"]) for d in _jsonl(saida)}
    por: dict[str, list[dict]] = defaultdict(list)
    for r in _varredura(varredura):
        por[r["livro"]].append(r)
    rnd = random.Random(SEMENTE)
    lista: dict[str, dict[int, str]] = defaultdict(dict)
    for livro, regs in por.items():
        for r in regs:
            if "erro" in r or r.get("lidos", 0) >= 3000:
                lista[livro][r["folha"]] = "muita"
        for r in rnd.sample(regs, min(15, len(regs))):
            lista[livro].setdefault(r["folha"], "sorteio")
    tarefas = [
        (livro, [(i, o) for i, o in sorted(d.items()) if (livro, i) not in feitas], saida) for livro, d in lista.items()
    ]
    tarefas = [t for t in tarefas if t[1]]
    print(sum(len(t[1]) for t in tarefas), "folhas", flush=True)
    _rodar(_amostra_um, tarefas)


def cota(varredura: Path, pasta: Path) -> None:
    saida = pasta / "cota"
    saida.mkdir(parents=True, exist_ok=True)
    feitas = {(d["livro"], d["folha"]) for d in _jsonl(pasta / "saida") + _jsonl(saida)}
    por: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in _varredura(varredura):
        if "erro" not in r and r["lidos"] >= 300 and (r["livro"], r["folha"]) not in feitas:
            por[r["livro"]].append((r["folha"], r["lidos"]))
    print(sum(map(len, por.values())), "folhas", flush=True)
    _rodar(_cota_um, [(livro, folhas, saida) for livro, folhas in por.items()])


def reler(pasta: Path) -> None:
    por: dict[str, list[int]] = defaultdict(list)
    for r in _jsonl(pasta / "cota"):
        if "erro" not in r and r["texto"] / max(r["comp"], 1) >= CORTE:
            por[r["livro"]].append(r["folha"])
    regs = [r for lote in _rodar(_reler_um, [(livro, sorted(f)) for livro, f in por.items()]) for r in lote]
    regs.sort(key=lambda r: (r["livro"], r["folha"]))
    corpo = json.dumps(regs, ensure_ascii=False, indent=0) + "\n"
    (pasta / "candidatas_relidas.json").write_bytes(corpo.encode("utf-8"))


if __name__ == "__main__":
    modo = sys.argv[1]
    if modo == "amostra":
        amostra(Path(sys.argv[2]), Path(sys.argv[3]))
    elif modo == "cota":
        cota(Path(sys.argv[2]), Path(sys.argv[3]))
    elif modo == "reler":
        reler(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
