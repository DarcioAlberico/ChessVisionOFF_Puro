"""Acrescenta o `produto` aos registros de uma corrida antiga de `medir.py deteccao`, sem reler o que não precisa.

Só a folha de camada rala volta ao glifo, e o livro sem camada nenhuma herda o registro do glifo. Saiu do dia em que a fonte
do produto mudou, com as duas outras já medidas. Hoje `medir.py deteccao` mede as três de uma vez.

Uso: `produto_reaproveitado.py <pasta> <segundos>`, com `deteccao_v1.jsonl` na pasta, `CVOFF_RAIZ` e `PYTHONPATH`.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import fitz

from chess_diagram_ocr.text import lingua
from chess_diagram_ocr.text.leitor import ler_pagina
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

RAIZ = Path(os.environ["CVOFF_RAIZ"])
TENTATIVAS = 25
FOLHAS_FOLGADAS = 4


def _do_produto(livro: str, declarada: str, reconhecedor: list) -> tuple[dict, int | None, int]:
    doc = fitz.open(RAIZ / "PDF" / livro)
    produto = lingua.LinguaDoLivro()
    decidiu_em = None
    abertas = 0
    for indice in range(min(doc.page_count, TENTATIVAS)):
        if len(produto.folhas) >= lingua.FOLHAS_DA_DETECCAO:
            break
        abertas += 1
        camada = doc[indice].get_text()
        if lingua.contar(camada).palavras >= lingua.PALAVRAS_POR_FOLHA:
            produto = produto.com_folha(indice, camada)
        else:
            if not reconhecedor:
                reconhecedor.append(build_glyph_recognizer(str(RAIZ / "models" / "char_classifier.pt")))
            lido = ler_pagina(RAIZ / "PDF" / livro, indice, dpi=220, motor="glifo", reconhecedor=reconhecedor[0]).texto()
            produto = produto.com_folha(indice, lido)
        if decidiu_em is None and produto.detectada == declarada:
            decidiu_em = abertas
        folgada = max(produto.contagem.pontos.values(), default=0) >= 5 * lingua.PONTOS_MINIMOS
        if len(produto.folhas) >= FOLHAS_FOLGADAS and folgada and produto.detectada:
            break
    doc.close()
    return produto.para_json(), decidiu_em, abertas


def main() -> None:
    pasta, orcamento = Path(sys.argv[1]), float(sys.argv[2])
    antigos = [json.loads(linha) for linha in (pasta / "deteccao_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    saida = pasta / "deteccao.jsonl"
    feitos = {json.loads(linha)["livro"] for linha in saida.read_text(encoding="utf-8").splitlines()} if saida.exists() else set()
    reconhecedor: list = []
    inicio = time.monotonic()
    for registro in antigos:
        if registro["livro"] in feitos:
            continue
        if time.monotonic() - inicio > orcamento:
            print("orçamento gasto; rode de novo para continuar")
            return
        if registro["camada"]["contagem"]["palavras"] == 0:
            registro["produto"] = registro["glifo"]
            registro["decidiu_em"]["produto"] = registro["decidiu_em"]["glifo"]
        else:
            registro["produto"], registro["decidiu_em"]["produto"], abertas = _do_produto(registro["livro"], registro["declarada"], reconhecedor)
            registro["folhas_abertas"] = max(registro["folhas_abertas"], abertas)
        with saida.open("a", encoding="utf-8", newline="\n") as fluxo:
            fluxo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    print("fim")


if __name__ == "__main__":
    main()
