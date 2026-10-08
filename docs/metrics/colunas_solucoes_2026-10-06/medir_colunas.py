"""Mede a ordem de leitura e as colunas da aba Texto (motor glifo) contra a camada do PDF.

Referência: a ordem em que o PDF emite as linhas (a régua S-194 de `cli/texto_ordem.py`), com o
mesmo guarda -- a página cuja camada desce mais vezes do que o caminho da camada prevê fica de
fora como «referência suspeita».

Por página: tau (Kendall) do glifo e do caminho da camada; linhas da camada partidas pelo glifo
entre colunas diferentes; colunas estreitas (< 20 % da largura do texto); número de colunas.
"""
import json
import random
import sys
import time
from pathlib import Path

import os

import pymupdf

sys.path.insert(0, str(Path(sys.argv[0]).parent))
import patch_colunas  # noqa: E402,F401 - variante por COLUNAS_VARIANTE

from chess_diagram_ocr.cli.texto_ordem import descidas, kendall_tau, medir_pagina
from chess_diagram_ocr.text.leitor import ler_pagina

SP = Path(sys.argv[0]).parent
censo = json.loads((SP / "censo.json").read_text(encoding="utf-8"))

#: (livro, quantas páginas de exercício, quantas de controle)
AMOSTRA = {
    "📚Yusupov Artur. Build Up Your Chess (all volumes).pdf": (120, 30),
    "Dvoretsky - Dvoretsky's Endgame Manual (2025).pdf": (40, 15),
    "AAGAARD - Practical Chess Defence.pdf": (40, 15),
    "Karpov A - Chess Combinations -World Champions-1 (2011).pdf": (40, 15),
    "La_casa_del_Ajedrez_El_metodo_Yusupov_4_Yusupov_Artur_Fundamentos.pdf": (40, 10),
    "Secrets of Chess Training School of Future Champions 1_ao_5.pdf": (40, 15),
    "A Matter of Endgame Technique – Jacob Aagaard.pdf": (30, 15),
    "📚Burgess G. The Gambit Book of Instructive.pdf": (11, 10),
    "Dvoretsky,_Mark_&_Yusupov,_Artur_SFC4_Secrets_of_Positional_Play.pdf": (11, 10),
    "Schiller - The Big Book of Combinations (1994).pdf": (8, 10),
    "Xadrez Vitorioso - Finais - Yasser Seirawan.pdf": (8, 10),
    "📚Nunn J. Secrets of Minor Piece Endings.pdf": (6, 10),
}


def camada(page):
    linhas = []
    for bloco in page.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            texto = "".join(s["text"] for s in linha["spans"]).strip()
            if texto:
                linhas.append(tuple(float(v) for v in linha["bbox"]))
    return linhas


def cobertura(a, b):
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    return w * h / area


def medir(pdf, indice, doc):
    page = doc[indice]
    ref = camada(page)
    if len(ref) < 6:
        return None
    pela_camada = medir_pagina(page)  # o caminho da camada (S-194), com o guarda dele
    if pela_camada is None:
        return None
    lida = ler_pagina(pdf, indice, motor="glifo")
    ordem, coluna_da_ref = [], {}
    partidas = set()
    larguras = []
    for col in lida.colunas:
        larguras.append(col.bbox[2] - col.bbox[0])
        for bloco in col.blocos:
            for linha in getattr(bloco, "linhas", ()) or ():
                melhor, cob = None, 0.0
                for i, r in enumerate(ref):
                    c = cobertura(linha.bbox, r)
                    if c > cob:
                        melhor, cob = i, c
                if melhor is None or cob < 0.3:
                    continue
                if melhor in coluna_da_ref and coluna_da_ref[melhor] != col.indice:
                    partidas.add(melhor)
                coluna_da_ref.setdefault(melhor, col.indice)
                if melhor not in ordem:
                    ordem.append(melhor)
    xs = [c.bbox[0] for c in lida.colunas] + [c.bbox[2] for c in lida.colunas]
    largura_texto = (max(xs) - min(xs)) if xs else 1.0
    estreitas = sum(1 for w in larguras if w < 0.2 * largura_texto)
    return {
        "pdf": Path(pdf).name, "pagina": indice + 1, "linhas_ref": len(ref),
        "casadas": len(ordem), "tau_glifo": round(kendall_tau(ordem), 4),
        "tau_camada": round(pela_camada.tau, 4),
        "ref_confiavel": pela_camada.descidas_da_referencia <= pela_camada.subidas_previstas,
        "colunas_glifo": len(lida.colunas), "estreitas": estreitas, "partidas": len(partidas),
        "regioes_camada": pela_camada.regioes, "colunas_camada": pela_camada.colunas,
        "cols": [[round(v) for v in c.bbox] for c in lida.colunas],
    }


random.seed(20261006)
saida = SP / os.environ.get("SAIDA", "medida_colunas.jsonl")
feitas = set()
if saida.exists():
    for linha in saida.read_text(encoding="utf-8").splitlines():
        r = json.loads(linha)
        feitas.add((r["pdf"], r["pagina"], r["grupo"]))
with saida.open("a", encoding="utf-8") as out:
    for caminho, info in censo.items():
        nome = Path(caminho).name
        if nome not in AMOSTRA or (os.environ.get("SO") and os.environ["SO"] not in nome):
            continue
        n_ex, n_ctl = AMOSTRA[nome]
        exerc = info["exercicios"]
        doc = pymupdf.open(caminho)
        com_texto = [i for i in range(doc.page_count)
                     if i not in set(exerc) and len(doc[i].get_text().strip()) >= 200]
        grupos = [("exercicio", sorted(random.sample(exerc, min(n_ex, len(exerc))))),
                  ("controle", sorted(random.sample(com_texto, min(n_ctl, len(com_texto)))))]
        for grupo, paginas in grupos:
            for i in paginas:
                if (nome, i + 1, grupo) in feitas:
                    continue
                t = time.time()
                try:
                    r = medir(caminho, i, doc)
                except Exception as exc:  # noqa: BLE001
                    r = {"pdf": nome, "pagina": i + 1, "erro": str(exc)[:200]}
                if r is None:
                    continue
                r["grupo"] = grupo
                r["segundos"] = round(time.time() - t, 1)
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
                out.flush()
        print(f"{nome[:50]} feito", flush=True)
