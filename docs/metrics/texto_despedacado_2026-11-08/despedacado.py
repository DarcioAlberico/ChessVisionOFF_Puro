"""O corte do texto despedaçado na folha com moldura (`guarda_de_leitura.RUIDO_POR_TOKEN`). Só contagens, sem texto de livro.

    python despedacado.py censo <pasta>              # toda folha do acervo: tem moldura? se tem, o glifo e os caracteres por token
    python despedacado.py reserva <pasta> [limite]   # as emolduradas de 1,3 ao limite (4,0), pela reserva do Tesseract
    python despedacado.py apurar <pasta> <saida.json>

`<pasta>`, fora do repositório, recebe `censo/`, `reserva.json` e os textos lidos (uso local: texto de livro). Da raiz do
checkout com os PDFs, ou com `CVOFF_RAIZ` apontando para ela; num worktree, `PYTHONPATH=<worktree>/src`. O censo retoma de
onde parou, e leva cerca de cinco horas com cinco processos.

**A camada é régua grosseira aqui.** Os livros da faixa são scans com camada de OCR de terceiro, e a reserva também é
Tesseract: a concordância das duas sai inflada. Por isso a régua é a fração de palavras (3+ letras) do glifo que existem na
camada, e o veredito de cada faixa foi conferido lendo as folhas.
"""

from __future__ import annotations

import glob
import json
import multiprocessing as mp
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(os.environ.get("CVOFF_RAIZ", "."))
TRABALHADORES = 5
FAIXAS = [(1.3, 2.0), (2.0, 2.5), (2.5, 2.8), (2.8, 3.0), (3.0, 3.3), (3.3, 4.0)]
CORTE_ANTIGO = 1.3
CORTE_NOVO = 3.0


def _censo_um(args: tuple[str, Path]) -> str:
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    import fitz

    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text import guarda_de_leitura as g
    from chess_diagram_ocr.text import leitor, moldura
    from chess_diagram_ocr.text.binarizacao import binarize
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    pdf, saida = args
    rec = build_glyph_recognizer(str(RAIZ / "models/char_classifier.pt"))
    visto: dict = {}
    parece, medir = g.parece_ruido, g.medir

    def espia_parece(tokens):
        visto.update(chars=sum(len(t) for t in tokens), toks=len(tokens))
        return parece(tokens)

    def espia_medir(*a, **k):
        visto["m"] = medir(*a, **k)
        return visto["m"]

    g.parece_ruido, g.medir = espia_parece, espia_medir
    livro = Path(pdf).stem
    with fitz.open(pdf) as d:
        n = d.page_count
    with (saida / f"{os.getpid()}_{time.time_ns()}.jsonl").open("a", encoding="utf-8") as f:
        for i in range(n):
            r: dict = {"livro": livro, "folha": i}
            try:
                img = render_pdf_page(pdf, i, dpi=220)
                r["moldura"] = int(moldura.tirar_moldura(binarize(img))[1])  # como leitor._e_ruido_emoldurado
                if r["moldura"]:
                    visto.clear()
                    p = leitor.ler_pagina(pdf, i, dpi=220, motor="glifo", reconhecedor=rec, imagem_rgb=img)
                    m = visto["m"]
                    r.update(
                        chars=visto.get("chars"),
                        toks=visto.get("toks"),
                        lidos=m.lidos,
                        comp=m.componentes,
                        camada=m.caracteres_da_camada,
                        avisos=[a.codigo for a in p.avisos],
                        texto=p.texto()[:4000],
                    )
            except Exception as e:  # uma folha ruim não para o censo, e o erro fica no registro
                r["erro"] = repr(e)[:200]
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
    return livro


def _reserva_um(args: tuple[str, list[int]]) -> list[dict]:
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    import fitz

    from chess_diagram_ocr.text import guarda_de_leitura as g
    from chess_diagram_ocr.text import leitor
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    livro, folhas = args
    rec = build_glyph_recognizer(str(RAIZ / "models/char_classifier.pt"))
    pdf = str(RAIZ / "PDF" / f"{livro}.pdf")
    g.RUIDO_POR_TOKEN = 99.0  # toda folha da faixa vai à reserva, também as que o corte deixa no glifo
    saida = []
    with fitz.open(pdf) as d:
        for i in folhas:
            r: dict = {"livro": livro, "folha": i}
            try:
                p = leitor.ler_pagina(pdf, i, dpi=220, motor="glifo", reconhecedor=rec, reserva=True)
                r.update(
                    reserva=p.texto()[:6000], avisos_reserva=[a.codigo for a in p.avisos], camada=d[i].get_text()[:8000]
                )
            except Exception as e:
                r["erro"] = repr(e)[:200]
            saida.append(r)
    return saida


def _censo(pasta: Path) -> list[dict]:
    return [
        json.loads(linha) for a in glob.glob(str(pasta / "censo" / "*.jsonl")) for linha in open(a, encoding="utf-8")
    ]


def _medidas(r: dict) -> bool:
    return bool(r.get("moldura")) and bool(r.get("toks")) and r["chars"] >= 40


def _q(r: dict) -> float:
    return r["chars"] / r["toks"]


def censo(pasta: Path) -> None:
    saida = pasta / "censo"
    saida.mkdir(parents=True, exist_ok=True)
    feitos = {r["livro"] for r in _censo(pasta)}
    pdfs = sorted(p for p in glob.glob(str(RAIZ / "PDF" / "*.pdf")) if Path(p).stem not in feitos)
    print(len(pdfs), "livros", flush=True)
    with mp.get_context("spawn").Pool(TRABALHADORES, maxtasksperchild=1) as pool:
        for k, livro in enumerate(pool.imap_unordered(_censo_um, [(p, saida) for p in pdfs]), 1):
            print(k, livro[:50], time.strftime("%H:%M:%S"), flush=True)


def reserva(pasta: Path, limite: float) -> None:
    por: dict[str, list[int]] = defaultdict(list)
    for r in _censo(pasta):
        if _medidas(r) and CORTE_ANTIGO < _q(r) <= limite:
            por[r["livro"]].append(r["folha"])
    print(sum(map(len, por.values())), "folhas", flush=True)
    with mp.get_context("spawn").Pool(TRABALHADORES, maxtasksperchild=1) as pool:
        regs = [r for lote in pool.imap_unordered(_reserva_um, list(por.items())) for r in lote]
    (pasta / "reserva.json").write_bytes(json.dumps(regs, ensure_ascii=False).encode("utf-8"))


def _palavras(texto: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[^\W\d_]{3,}", texto)]


def _contra(texto: str, ref: set[str]) -> tuple[float, float]:
    """Precisão (palavras lidas que existem na camada) e revocação (palavras da camada que foram lidas)."""
    lidas = _palavras(texto)
    precisao = sum(w in ref for w in lidas) / len(lidas) if lidas else 0.0
    return precisao, len(set(lidas) & ref) / len(ref)


def _mediana(linhas: list, k: int, j: int) -> float:
    return round(statistics.median(x[k][j] for x in linhas), 2)


def apurar(pasta: Path, destino: Path) -> None:
    regs = _censo(pasta)
    medidas = [r for r in regs if _medidas(r)]
    por_livro: dict[str, list[float]] = defaultdict(list)
    for r in medidas:
        por_livro[r["livro"]].append(_q(r))
    indice = {(r["livro"], r["folha"]): r for r in medidas}
    faixas = []
    perdas = []
    linhas = []
    for s in json.load(open(pasta / "reserva.json", encoding="utf-8")):
        if "erro" in s:
            continue
        c = indice[(s["livro"], s["folha"])]
        ref = set(_palavras(s["camada"]))
        if len(ref) < 15:
            continue
        g, t = _contra(c["texto"], ref), _contra(s["reserva"], ref)
        linhas.append((_q(c), g, t))
        if t[1] <= g[1]:
            perdas.append({"livro": s["livro"], "folha": s["folha"], "caracteres_por_token": round(_q(c), 3)})
    for a, b in FAIXAS:
        lin = [x for x in linhas if a < x[0] <= b]
        faixas.append(
            {
                "faixa": [a, b],
                "folhas_com_camada": len(lin),
                "glifo": {"precisao": _mediana(lin, 1, 0), "revocacao": _mediana(lin, 1, 1)},
                "reserva": {"precisao": _mediana(lin, 2, 0), "revocacao": _mediana(lin, 2, 1)},
                "reserva_revoca_mais": sum(x[2][1] > x[1][1] for x in lin),
            }
        )
    novas = [r for r in medidas if CORTE_ANTIGO < _q(r) <= CORTE_NOVO]
    figurina = min((r for r in medidas if "Chess Evolution" in r["livro"]), key=_q)
    corpo = {
        "data": "2026-11-08",
        "o_que": "S-711: o texto despedaçado na folha com moldura, e o corte de RUIDO_POR_TOKEN subido de 1,3 para 3,0",
        "script": "docs/metrics/texto_despedacado_2026-11-08/despedacado.py",
        "populacao": {
            "folhas": len(regs),
            "erros": sum("erro" in r for r in regs),
            "com_moldura": sum(bool(r.get("moldura")) for r in regs),
            "com_40_ou_mais_caracteres": len(medidas),
        },
        "por_livro": {
            livro: {
                "folhas": len(v),
                "ruido_ate_1_3": sum(x <= CORTE_ANTIGO for x in v),
                "despedacado_1_3_a_3_0": sum(CORTE_ANTIGO < x <= CORTE_NOVO for x in v),
                "de_3_0_a_4_0": sum(CORTE_NOVO < x <= 4.0 for x in v),
                "mediana": round(statistics.median(v), 2),
            }
            for livro, v in sorted(por_livro.items(), key=lambda kv: -len(kv[1]))
        },
        "faixas_contra_a_camada": faixas,
        "reserva_nao_revoca_mais": perdas,
        "corte_novo": {
            "valor": CORTE_NOVO,
            "folhas_que_passam_a_avisar": len(novas),
            "avisos_que_elas_tinham": dict(Counter(a for r in novas for a in r["avisos"])),
            "por_livro": dict(Counter(r["livro"] for r in novas)),
        },
        "figurina_mais_baixa": {
            "livro": figurina["livro"],
            "folha": figurina["folha"],
            "caracteres_por_token": round(_q(figurina), 3),
        },
    }
    destino.write_bytes((json.dumps(corpo, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo == "censo":
        censo(Path(sys.argv[2]))
    elif modo == "reserva":
        reserva(Path(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else 4.0)
    elif modo == "apurar":
        apurar(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(__doc__)
