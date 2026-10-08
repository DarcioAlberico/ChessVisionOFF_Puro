"""Compara duas rodadas de medir_colunas.py (motor glifo), página a página."""
import collections
import json
import sys


def carregar(caminho):
    return {(r["pdf"], r["pagina"], r["grupo"]): r for r in map(json.loads, open(caminho, encoding="utf-8"))
            if "erro" not in r}


a, b = carregar(sys.argv[1]), carregar(sys.argv[2])
chaves = sorted(set(a) & set(b))
mudou = [k for k in chaves if a[k]["cols"] != b[k]["cols"]]
print(f"páginas {len(chaves)}  estrutura mudou {len(mudou)}")
um_antes = sum(1 for k in chaves if a[k]["colunas_glifo"] == 1)
um_depois = sum(1 for k in chaves if b[k]["colunas_glifo"] == 1)
print(f"lidas como uma coluna só: {um_antes} -> {um_depois}")
print(f"com coluna estreita: {sum(1 for k in chaves if a[k]['estreitas'])} -> {sum(1 for k in chaves if b[k]['estreitas'])};"
      f" com linha da camada partida: {sum(1 for k in chaves if a[k]['partidas'])} -> {sum(1 for k in chaves if b[k]['partidas'])}")
ambas = [k for k in chaves if a[k]["ref_confiavel"] and b[k]["ref_confiavel"]]
pioram = [k for k in ambas if b[k]["tau_glifo"] > a[k]["tau_glifo"] + 0.005]
melhoram = [k for k in ambas if b[k]["tau_glifo"] < a[k]["tau_glifo"] - 0.005]
print(f"tau do glifo nas confiáveis nas duas ({len(ambas)}): melhoram {len(melhoram)}, pioram {len(pioram)}")
cont = collections.Counter((k[0][:40], k[2][:3]) for k in mudou)
for (livro, grupo), n in sorted(cont.items()):
    tot = sum(1 for k in chaves if k[0][:40] == livro and k[2][:3] == grupo)
    print(f"   {livro:40s} {grupo} mudou {n}/{tot}")
print("MUDARAM:")
for k in mudou:
    print(f"   {k[0][:40]:40s} p{k[1]:<5} {k[2][:3]}  colunas {a[k]['colunas_glifo']}->{b[k]['colunas_glifo']}"
          f"  estreitas {a[k]['estreitas']}->{b[k]['estreitas']}  partidas {a[k]['partidas']}->{b[k]['partidas']}"
          f"  tau {a[k]['tau_glifo']}->{b[k]['tau_glifo']} ({'conf' if a[k]['ref_confiavel'] and b[k]['ref_confiavel'] else '-'})")
