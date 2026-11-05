"""Tamanho de amostra e poder para os portões.

Modo 1 (largura): quantos livros (e folhas por livro) o teste precisa para o IC95 de dois níveis do
CER de prosa de um motor ter uma meia-largura dada.
  amostra.py <jsonl> <motor> [tip|cru]

Modo 2 (poder pareado, S-755): com as diferenças POR FOLHA medidas entre dois motores (A e B), em
quantos conjuntos simulados de K livros x F folhas o limite superior do IC95 da diferença pareada
relativa (A - B) / B fica < 0 -- isto é, em quantos o portão de promoção de A sobre B abriria.
  amostra.py <jsonl> --pareado <A> <B> [tip|cru]

Método: reamostra livros e folhas do conjunto medido (60 simulações por configuração; o IC de
cada simulação usa 400 reamostras de dois níveis).
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resumo  # noqa: E402
from resumo import _indices_dois_niveis, ic95  # noqa: E402

resumo.REAMOSTRAS = 400
CONFIGS = [(6, 6), (8, 6), (12, 6), (16, 6), (24, 6)]


def largura(regs, motor, norm):
    por_livro = defaultdict(list)
    for r in regs:
        p = r["placar"][f"{motor}|{norm}"]
        por_livro[r["livro"]].append((p["erros"]["prosa"], p["total"]["prosa"]))
    livros = list(por_livro.values())
    rng = np.random.default_rng(11)
    pontual = sum(e for lin in livros for e, _ in lin) / sum(t for lin in livros for _, t in lin)
    print(f"{motor}: CER de prosa no conjunto medido = {pontual:.4f} ({len(livros)} livros)")
    print(f"{'livros':>6s} {'folhas/livro':>12s} {'meia-largura sup. (mediana)':>28s} {'p90':>8s}")
    for K in (6, 8, 12, 16, 24):
        for F in (4, 6, 8):
            sup = []
            for _ in range(60):
                es, ts, ls = [], [], []
                for k, b in enumerate(rng.integers(0, len(livros), K)):
                    folhas = livros[b]
                    for f in rng.integers(0, len(folhas), F):
                        es.append(folhas[f][0])
                        ts.append(folhas[f][1])
                        ls.append(str(k))
                c, lo, hi = ic95(es, ts, ls)
                sup.append(hi - c)
            print(f"{K:6d} {F:12d} {100*np.median(sup):27.2f}pp {100*np.percentile(sup, 90):7.2f}pp")


def poder(regs, a, b, norm):
    por_livro = defaultdict(list)
    for r in regs:
        pa, pb = r["placar"][f"{a}|{norm}"], r["placar"][f"{b}|{norm}"]
        por_livro[r["livro"]].append((pa["erros"]["prosa"], pb["erros"]["prosa"], pa["total"]["prosa"]))
    livros = list(por_livro.values())
    ea = sum(x for lin in livros for x, _, _ in lin)
    eb = sum(y for lin in livros for _, y, _ in lin)
    print(f"{a} contra {b}: diferença relativa medida = {(ea - eb) / max(1, eb):+.1%} ({len(livros)} livros)")
    print(f"{'livros':>6s} {'folhas/livro':>12s} {'poder (teto do IC da dif. relativa < 0)':>40s}")
    rng = np.random.default_rng(13)
    for K, F in CONFIGS:
        abre = 0
        for _ in range(60):
            xa, xb, tt, ls = [], [], [], []
            for k, bk in enumerate(rng.integers(0, len(livros), K)):
                folhas = livros[bk]
                for f in rng.integers(0, len(folhas), F):
                    xa.append(folhas[f][0])
                    xb.append(folhas[f][1])
                    tt.append(folhas[f][2])
                    ls.append(str(k))
            xa, xb = np.array(xa, float), np.array(xb, float)
            am = []
            for i in _indices_dois_niveis(ls, rng):
                am.append((xa[i].sum() - xb[i].sum()) / max(1.0, xb[i].sum()))
            if np.percentile(am, 97.5) < 0:
                abre += 1
        print(f"{K:6d} {F:12d} {100 * abre / 60:39.0f}%")


def main():
    regs = [json.loads(lin) for lin in open(sys.argv[1], encoding="utf-8")]
    if "--pareado" in sys.argv:
        k = sys.argv.index("--pareado")
        a, b = sys.argv[k + 1], sys.argv[k + 2]
        norm = sys.argv[k + 3] if len(sys.argv) > k + 3 else "tip"
        poder(regs, a, b, norm)
    else:
        largura(regs, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "tip")


if __name__ == "__main__":
    main()
