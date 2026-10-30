"""Filtra um JSONL do banco — os subconjuntos publicados saem daqui, e não de grep à mão.

Uso:
  filtrar.py entrada.jsonl saida.jsonl [--sem-livro TRECHO]... [--so-livro TRECHO]...
                                       [--oraculo-max 0.10] [--sem-folha-perdida]

--oraculo-max   admite só a folha cujo `tess_oraculo` erra <= o limite de prosa (regra da prata);
--sem-folha-perdida  tira folha em que o glifo achou <= 2 linhas e a camada >= 10 (perda de leiaute).
Imprime o que ficou de fora e por quê.
"""
import json
import sys


def main(argv):
    ent, sai, *resto = argv
    sem, so, oraculo, perdida = [], [], None, False
    k = 0
    while k < len(resto):
        if resto[k] == "--sem-livro":
            sem.append(resto[k + 1])
            k += 2
        elif resto[k] == "--so-livro":
            so.append(resto[k + 1])
            k += 2
        elif resto[k] == "--oraculo-max":
            oraculo = float(resto[k + 1])
            k += 2
        elif resto[k] == "--sem-folha-perdida":
            perdida = True
            k += 1
        else:
            raise SystemExit(f"argumento desconhecido: {resto[k]}")
    n = 0
    with open(sai, "w", encoding="utf-8") as f:
        for linha in open(ent, encoding="utf-8"):
            r = json.loads(linha)
            nome = f"{r['livro'][:30]} folha {r['pagina'] + 1}"
            if any(s in r["livro"] for s in sem) or (so and not any(s in r["livro"] for s in so)):
                continue
            if oraculo is not None and "tess_oraculo|tip" in r["placar"]:
                p = r["placar"]["tess_oraculo|tip"]
                c = p["erros"]["prosa"] / max(1, p["total"]["prosa"])
                if c > oraculo:
                    print(f"fora (oraculo {c:.3f} > {oraculo}): {nome}")
                    continue
            if perdida and r["n_linhas"]["glifo"] <= 2 and r["n_linhas"]["ref"] >= 10:
                print(f"fora (folha perdida pelo leiaute): {nome}")
                continue
            f.write(linha)
            n += 1
    print(f"{n} folhas em {sai}")


if __name__ == "__main__":
    main(sys.argv[1:])
