"""Os ativos derivados têm texto dos livros do teste do scan-ouro? Só contagens saem daqui (S-703).

    ativos.py <pasta de cache, fora do repositório> [limite em segundos]

Conta, por livro do teste, as palavras distintas da camada dele (`lexico.palavras_de`, em caixa dobrada), quantas estão em cada lista empacotada, e
quantas dessas **só** ele tem: nenhum outro PDF de `PDF/` traz a palavra na camada, nem a lista da língua a conhece. Só essas não têm outra explicação.
A camada é OCR de terceiro, então um erro de OCR dele numa lista seria a impressão digital. Rodar de novo continua de onde parou. Raiz: `CVOFF_RAIZ`.
"""

from __future__ import annotations

import gzip
import json
import os
import sys
import time
from pathlib import Path

import fitz

from chess_diagram_ocr.text import lexico, scan_ouro
from chess_diagram_ocr.text.caderno import identidade_de

AQUI = Path(__file__).resolve().parent
RAIZ = Path(os.environ.get("CVOFF_RAIZ") or AQUI.parents[2])
LINGUAS = ("eng", "por", "spa", "deu", "nld", "fra", "ron", "rus")


def vocabulario(pdf: Path, cache: Path) -> set[str]:
    if cache.is_file():
        return set(json.loads(gzip.decompress(cache.read_bytes())))
    palavras: set[str] = set()
    with fitz.open(pdf) as doc:
        for pagina in doc:
            palavras.update(p.casefold() for p in lexico.palavras_de(pagina.get_text()))
    cache.write_bytes(gzip.compress(json.dumps(sorted(palavras), ensure_ascii=False).encode("utf-8")))
    return palavras


def main(pasta: str, limite: float = 150.0) -> int:
    cache = Path(pasta)
    cache.mkdir(parents=True, exist_ok=True)
    inicio = time.perf_counter()
    teste = {livro.identidade for livro in scan_ouro.carregar().livros if livro.split == scan_ouro.TESTE}
    do_teste: dict[str, set[str]] = {}
    outros: set[str] = set()
    pdfs = sorted((RAIZ / "PDF").glob("*.pdf"))
    for n, pdf in enumerate(pdfs):
        if time.perf_counter() - inicio > limite:
            print(f"# parou pelo limite em {n} de {len(pdfs)}: rode de novo")
            return 3
        identidade = identidade_de(pdf) or ""
        v = vocabulario(pdf, cache / f"{identidade}.json.gz")
        if identidade in teste:
            do_teste[identidade] = v
        else:
            outros |= v
    assert set(do_teste) == teste
    listas = {c.name: lexico._de_um_arquivo(c) for c in lexico.EMPACOTADOS}  # noqa: SLF001
    linguas = frozenset().union(*(lexico.da_lingua(x) for x in LINGUAS))
    for identidade, v in sorted(do_teste.items()):
        for nome, lista in listas.items():
            cruzam = v & lista
            so_dele = cruzam - outros - linguas - frozenset().union(*(w for k, w in do_teste.items() if k != identidade))
            print(f"{identidade[:8]} {len(v):7d} palavras; {nome:14} cruzam {len(cruzam):6d}; só dele {len(so_dele):5d}")
    uniao = frozenset().union(*do_teste.values())
    for nome, lista in listas.items():
        print(f"os 5, {nome}: {len(uniao & lista)} cruzam; {len((uniao & lista) - outros - linguas)} só deles, de {len(lista)} na lista")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1], *(float(x) for x in sys.argv[2:3])))
