"""Reproduz um conjunto do relatório publicado, folha a folha, a partir do próprio relatório.

As folhas de cada conjunto estão em `conjuntos.<nome>.por_livro.<livro>.folhas` (base 1) e a língua
do Tesseract em `.lingua`. A seleção automática de `rodar.escolher_paginas` depende do classificador
de token e muda quando ele muda — por isso a reprodução usa sempre a lista gravada, nunca `|n`.

Uso (da raiz do repositório, com o .venv do projeto):
  reproduzir.py <relatorio.json> <conjunto> <saida.jsonl> [--exigir-src PASTA] [--modelo .pt]

Conjuntos degradados ganham `--degradar medio --sem-rapid`; os de prata, `--sem-rapid`. A saída é
recriada. Depois: `fusao_v5.py`, `filtrar.py` e `resumo.py`, como no roadmap (seção 10).
"""
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    relatorio, conjunto, saida, *extra = argv
    rel = json.load(open(relatorio, encoding="utf-8"))
    c = rel["conjuntos"][conjunto]
    base = []
    if conjunto.startswith("degradado"):
        base += ["--degradar", "medio", "--sem-rapid"]
    elif conjunto.startswith("prata"):
        base += ["--sem-rapid"]
    if os.path.exists(saida):
        os.remove(saida)
    for livro, info in c["por_livro"].items():
        paginas = ",".join(str(f - 1) for f in info["folhas"])
        cmd = [sys.executable, os.path.join(AQUI, "rodar.py"), "--acrescentar", *base, *extra,
               "--livro", f"{livro}|{info['lingua']}|0", "--paginas", paginas, "--saida", saida]
        print(">>", livro, info["lingua"], paginas, flush=True)
        subprocess.run(cmd, check=True)
    print("gravado", saida)


if __name__ == "__main__":
    main(sys.argv[1:])
