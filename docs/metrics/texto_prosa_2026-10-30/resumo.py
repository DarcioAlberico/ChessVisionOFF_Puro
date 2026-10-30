"""Agrega o JSONL do banco.

Por motor: CER de prosa com IC95 em DOIS níveis (reamostra livros, depois folhas dentro do livro),
WER de prosa (S+D+I)/N, CER de notação/outro/espaço, inserções, precisão e revocação de figurina.
Por par de motores: diferença pareada com IC95 (mesmo bootstrap de dois níveis).
Por livro: CER de prosa. Por motor: famílias das palavras de prosa erradas, com o livro de origem.

Uso: resumo.py <jsonl> [tip|cru] [--pares a-b,c-d]
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict

import numpy as np

SEMENTE = 7
REAMOSTRAS = 2000


def carregar(caminho):
    return [json.loads(lin) for lin in open(caminho, encoding="utf-8")]


def _indices_dois_niveis(livros: list[str], rng) -> list[np.ndarray]:
    """Uma reamostra por iteração: sorteia livros com reposição, depois folhas dentro de cada um."""
    por_livro = defaultdict(list)
    for k, lin in enumerate(livros):
        por_livro[lin].append(k)
    grupos = list(por_livro.values())
    out = []
    for _ in range(REAMOSTRAS):
        idx = []
        for g in rng.integers(0, len(grupos), len(grupos)):
            folhas = grupos[g]
            idx.extend(np.array(folhas)[rng.integers(0, len(folhas), len(folhas))])
        out.append(np.array(idx))
    return out


def ic95(erros, totais, livros=None, semente=SEMENTE):
    """Taxa agregada e IC95. Com `livros`, bootstrap em dois níveis; sem, por folha."""
    e, t = np.array(erros, float), np.array(totais, float)
    if len(e) == 0:
        return (float("nan"),) * 3
    rng = np.random.default_rng(semente)
    if livros is None:
        idx = rng.integers(0, len(e), (REAMOSTRAS, len(e)))
        amostras = e[idx].sum(1) / np.maximum(1, t[idx].sum(1))
    else:
        amostras = np.array([e[i].sum() / max(1, t[i].sum()) for i in _indices_dois_niveis(livros, rng)])
    return e.sum() / max(1, t.sum()), np.percentile(amostras, 2.5), np.percentile(amostras, 97.5)


def diferenca_pareada(ea, ta, eb, tb, livros, semente=SEMENTE):
    """CER(a) - CER(b) nas mesmas folhas, com IC95 de dois níveis."""
    ea, ta, eb, tb = (np.array(x, float) for x in (ea, ta, eb, tb))
    rng = np.random.default_rng(semente)
    am = []
    for i in _indices_dois_niveis(livros, rng):
        am.append(ea[i].sum() / max(1, ta[i].sum()) - eb[i].sum() / max(1, tb[i].sum()))
    d = ea.sum() / max(1, ta.sum()) - eb.sum() / max(1, tb.sum())
    return d, np.percentile(am, 2.5), np.percentile(am, 97.5)


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def familia(ref, hip):
    if hip == "":
        return "palavra perdida"
    if ref == hip:
        return "fronteira (espaco perdido junto a vizinha)"
    if re.sub(r"[lI|]", ".", ref) == hip or re.sub(r"[lI|]", ".", ref) == re.sub(r"[lI|]", ".", hip) and "." in hip:
        return "traco vertical lido como ponto (l/I -> .)"
    if hip.replace("fi1", "fi").replace("f1", "fl").replace("ff1", "ff") == ref:
        return "ligadura fi/fl com 1 a mais"
    if ref.replace('"', "''") == hip or ref.replace('"', "'") == hip or ref.replace('"', "(") == hip:
        return "aspas duplas"
    if re.search(r"[♔-♟]", hip) and not re.search(r"[♔-♟]", ref):
        return "figurina inventada em palavra"
    if ref.lower() == hip.lower():
        return "caixa (maiusc/minusc)"
    if sem_acento(ref) == sem_acento(hip):
        return "acento"
    r0, h0 = re.sub(r"\W", "", ref), re.sub(r"\W", "", hip)
    if r0 == h0:
        if ref.replace(" ", "") == hip.replace(" ", ""):
            return "espaco"
        return "pontuacao"
    if r0.lower() == h0.lower():
        return "pontuacao+caixa"
    if hip.replace(" ", "") == ref.replace(" ", "") or " " in hip:
        return "espaco"
    if re.sub(r"1", "", hip) == ref or re.sub(r"[1l|I]", "", hip) == re.sub(r"[1l|I]", "", ref):
        return "1/l/I/|"
    if sem_acento(ref).lower() == sem_acento(hip).lower():
        return "acento+caixa"
    if len(hip) > len(ref) and ref in hip:
        return "juncao com vizinha (espaco perdido)"
    if len(hip) < len(ref) and hip and hip in ref:
        return "palavra cortada"
    return "letra trocada"


def linha_de_motor(regs, m, tip):
    P = [r["placar"][f"{m}|{tip}"] for r in regs]
    livros = [r["livro"] for r in regs]
    c, lo, hi = ic95([p["erros"]["prosa"] for p in P], [p["total"]["prosa"] for p in P], livros)
    w = {k: sum(p.get("wer", {}).get(k, 0) for p in P) for k in "sdin"}
    wer = (w["s"] + w["d"] + w["i"]) / max(1, w["n"])
    def cc(k):
        return sum(p["erros"][k] for p in P) / max(1, sum(p["total"][k] for p in P))
    f = {k: sum(p.get("fig", {}).get(k, 0) for p in P) for k in ("ref", "hip", "tp")}
    return {"cer_prosa": c, "ic95": (lo, hi), "wer_prosa": wer, "wer_partes": w,
            "cer_notacao": cc("notacao"), "cer_outro": cc("outro"), "cer_espaco": cc("espaco"),
            "insercoes": sum(p.get("insercoes", 0) for p in P),
            "fig_revocacao": f["tp"] / max(1, f["ref"]), "fig_precisao": f["tp"] / max(1, f["hip"])}


def main():
    args = sys.argv[1:]
    pares = []
    if "--pares" in args:
        k = args.index("--pares")
        pares = [p.split("-") for p in args[k + 1].split(",")]
        del args[k:k + 2]
    regs = carregar(args[0])
    tip = args[1] if len(args) > 1 else "tip"
    motores = list(regs[0]["hip"].keys())
    print(f"folhas={len(regs)} livros={len({r['livro'] for r in regs})} normalizacao={tip} "
          f"(IC95 em dois niveis: livro, folha)")
    print(f"{'motor':13s} {'CER prosa [IC95]':24s} {'WER(S+D+I)':>10s} {'CER notac':>9s} {'CER espaco':>10s} "
          f"{'insercoes':>9s} {'fig rev':>7s} {'fig prec':>8s}")
    for m in motores:
        x = linha_de_motor(regs, m, tip)
        print(f"{m:13s} {x['cer_prosa']:.4f} [{x['ic95'][0]:.4f}-{x['ic95'][1]:.4f}] {x['wer_prosa']:10.4f} "
              f"{x['cer_notacao']:9.4f} {x['cer_espaco']:10.4f} {x['insercoes']:9d} "
              f"{x['fig_revocacao']:7.3f} {x['fig_precisao']:8.3f}")
    print(f"caracteres de prosa={sum(r['placar'][f'glifo|{tip}']['total']['prosa'] for r in regs)} "
          f"palavras de prosa={sum(r['placar'][f'glifo|{tip}'].get('wer', {}).get('n', 0) for r in regs)} "
          f"caracteres de notacao={sum(r['placar'][f'glifo|{tip}']['total']['notacao'] for r in regs)}")
    livros = [r["livro"] for r in regs]
    for a, b in pares:
        for classe in ("prosa", "notacao"):
            Pa = [r["placar"][f"{a}|{tip}"] for r in regs]
            Pb = [r["placar"][f"{b}|{tip}"] for r in regs]
            d, lo, hi = diferenca_pareada([p["erros"][classe] for p in Pa], [p["total"][classe] for p in Pa],
                                          [p["erros"][classe] for p in Pb], [p["total"][classe] for p in Pb], livros)
            melhora = sum(1 for pa, pb in zip(Pa, Pb, strict=False) if pa["erros"][classe] < pb["erros"][classe])
            piora = sum(1 for pa, pb in zip(Pa, Pb, strict=False) if pa["erros"][classe] > pb["erros"][classe])
            print(f"par {a} - {b} [{classe}]: {100*d:+.2f} p.p. IC95 [{100*lo:+.2f}; {100*hi:+.2f}] "
                  f"folhas melhores={melhora} piores={piora}")
    print("\npor livro (CER prosa):")
    porl = defaultdict(list)
    for r in regs:
        porl[r["livro"]].append(r)
    for nome_livro, rs in porl.items():
        linha = []
        for m in motores:
            e = sum(r["placar"][f"{m}|{tip}"]["erros"]["prosa"] for r in rs)
            t = sum(r["placar"][f"{m}|{tip}"]["total"]["prosa"] for r in rs)
            linha.append(f"{m}={e/max(1,t):.4f}")
        print(f"  {nome_livro[:34]:34s} [{rs[0]['lang']}] n={len(rs)} " + " ".join(linha))
    print("\nsegundos por folha:", {k: round(float(np.mean([r["tempo"][k] for r in regs])), 2) for k in regs[0]["tempo"]})
    for m in [x for x in ("glifo", "tess", "rapid", "fusao_v4") if x in motores]:
        fam = Counter()
        ex = defaultdict(Counter)
        orig = defaultdict(Counter)
        for r in regs:
            for k, v in r["placar"][f"{m}|{tip}"]["trocas"].items():
                ref, _, hip = k.partition(" -> ")
                if re.search(r"[A-Za-zÀ-ÿ]", ref) is None:
                    continue
                f = familia(ref, hip)
                fam[f] += v
                ex[f][k] += v
                orig[f][r["livro"][:22]] += v
        tot = sum(fam.values())
        print(f"\nfamilias de palavra de prosa errada -- {m} (total {tot}):")
        for f, v in fam.most_common():
            print(f"  {v:5d} {100*v/max(1,tot):5.1f}%  {f:42s} ex: {[e for e, _ in ex[f].most_common(3)]} "
                  f"livros: {dict(orig[f].most_common(3))}")


if __name__ == "__main__":
    main()
