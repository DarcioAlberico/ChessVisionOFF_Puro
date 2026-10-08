"""Compara duas rodadas da régua de ordem (regua_ordem.py), folha a folha."""
import collections
import json
import sys

a = {(r["pdf"], r["pagina"]): r for r in map(json.loads, open(sys.argv[1], encoding="utf-8")) if "erro" not in r}
b = {(r["pdf"], r["pagina"]): r for r in map(json.loads, open(sys.argv[2], encoding="utf-8")) if "erro" not in r}
chaves = sorted(set(a) & set(b))
ambas = [k for k in chaves if a[k]["confiavel"] and b[k]["confiavel"]]
melhora = [k for k in ambas if b[k]["tau"] < a[k]["tau"] - 1e-9]
piora = [k for k in ambas if b[k]["tau"] > a[k]["tau"] + 1e-9]
mudou_estrutura = [k for k in chaves if (a[k]["colunas"], a[k]["regioes"]) != (b[k]["colunas"], b[k]["regioes"])]
so_b = [k for k in chaves if b[k]["confiavel"] and not a[k]["confiavel"]]
so_a = [k for k in chaves if a[k]["confiavel"] and not b[k]["confiavel"]]
print(f"folhas {len(chaves)}  estrutura mudou {len(mudou_estrutura)}")
print(f"confiáveis nas duas {len(ambas)}: melhoram {len(melhora)}, pioram {len(piora)}, "
      f"tau médio {sum(a[k]['tau'] for k in ambas) / len(ambas):.4f} -> {sum(b[k]['tau'] for k in ambas) / len(ambas):.4f}; "
      f"em ordem exata {sum(1 for k in ambas if a[k]['tau'] == 0)} -> {sum(1 for k in ambas if b[k]['tau'] == 0)}")
print(f"passam a confiáveis {len(so_b)} (tau médio nelas {sum(b[k]['tau'] for k in so_b) / max(1, len(so_b)):.4f}, "
      f"em ordem {sum(1 for k in so_b if b[k]['tau'] == 0)}); deixam de ser {len(so_a)}")
por_livro = collections.Counter(k[0][:45] for k in mudou_estrutura)
print("estrutura mudou, por livro:", dict(por_livro.most_common()))
for nome, grupo in (("PIORAM", piora), ("deixam de ser confiáveis", so_a)):
    for k in grupo:
        print(f"  {nome}: {k[0][:45]} p{k[1]}  tau {a[k]['tau']} -> {b[k]['tau']}  "
              f"col {a[k]['colunas']}->{b[k]['colunas']} reg {a[k]['regioes']}->{b[k]['regioes']}")
