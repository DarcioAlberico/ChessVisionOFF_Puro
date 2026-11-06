"""ACERTO do árbitro contra a camada: cada troca, certa, errada ou indecisa, numa fatia digital. `casas válidas` é o juiz da própria correção.

    acerto.py <identidade> <saida.json> [--folhas N]

Só o split dev: o teste não abre aqui. Folhas espaçadas do livro, lidas uma vez, fundidas com o árbitro desligado e ligado, nas duas regras: a
**v3 forçada** é o caso difícil, porque no digital a v5 quase não dá notação em letra ao árbitro, e num scan real não há referência que julgue.

Uma troca é a diferença entre as duas saídas. A referência alinhada ao token de antes decide: certa se ela é o texto novo, errada se é o de antes.
Indecisa é quando não é nenhum dos dois: a camada escreve o lance noutro formato, ou o token de antes já estava errado de outro jeito. Só contagens
vão para o JSON; as trocas vão para a tela, para quem mede olhar.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from unittest import mock

import fitz

from chess_diagram_ocr.cli.texto_prosa import _achar_livros, _pastas_padrao, folhas_do_conjunto
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import arbitro, bancada_prosa, fusao, leitor, leitor_de_linha
from chess_diagram_ocr.text import regua_prosa as regua
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer


class LeituraUnica:
    def __init__(self) -> None:
        self.real = leitor_de_linha.LeitorTesseract()
        self.guardadas: dict[bytes, object] = {}

    def ler_linhas(self, recortes, *, lingua, dpi):  # type: ignore[no-untyped-def]
        chave = b"".join(r.tobytes()[:64] for r in recortes)
        if chave not in self.guardadas:
            self.guardadas[chave] = self.real.ler_linhas(recortes, lingua=lingua, dpi=dpi)
        return self.guardadas[chave]

    def ler_folha(self, cinza, *, lingua, dpi):  # type: ignore[no-untyped-def]
        return self.real.ler_folha(cinza, lingua=lingua, dpi=dpi)


def nu(token: str, lingua: str) -> str:
    return re.sub(r"[.,;:()\[\]!?]+$|^[(\[]+", "", regua.normalizar(token, regua.TIP, lingua))


def trocas(ref: list[str], antes: list[str], depois: list[str], lingua: str) -> list[tuple[str, str, str]]:
    """`(de, para, veredito)`, com a referência alinhada ao texto de antes."""
    ref_n = [nu(t, lingua) for t in ref]
    alinhado: dict[int, str] = {}
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ref_n, [nu(t, lingua) for t in antes], autojunk=False).get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            for d in range(j2 - j1):
                alinhado[j1 + d] = ref_n[i1 + d]
    saida = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, antes, depois, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        de, para = " ".join(antes[i1:i2]), " ".join(depois[j1:j2])
        certo = " ".join(alinhado.get(i, "") for i in range(i1, i2)).strip()
        if nu(para, lingua) == certo or (not certo and nu(para, lingua) in ref_n and nu(de, lingua) not in ref_n):
            veredito = "certa"
        elif nu(de, lingua) == certo or (not certo and nu(de, lingua) in ref_n and nu(para, lingua) not in ref_n):
            veredito = "errada"
        else:
            veredito = "indecisa"
        saida.append((de, para, veredito))
    return saida


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    identidade, destino = sys.argv[1:3]
    quantas = int(sys.argv[sys.argv.index("--folhas") + 1]) if "--folhas" in sys.argv else 12
    raiz = os.environ.get("CVOFF_RAIZ", "")
    dev = [f for f in folhas_do_conjunto("ouro", "dev") if f.identidade == identidade]
    if not dev:
        raise SystemExit(f"{identidade} não está no split dev")
    pdf = str(_achar_livros(dev, _pastas_padrao(raiz))[identidade])
    lingua = dev[0].lingua
    with fitz.open(pdf) as doc:
        n = len(doc)
    passo = max(1, (n - 40) // quantas)
    folhas = list(range(20, n - 20, passo))[:quantas]
    rec = build_glyph_recognizer()
    contas: dict[str, Counter[str]] = {fusao.V5: Counter(), fusao.V3: Counter()}
    for indice in folhas:
        imagem = render_pdf_page(pdf, indice, 220)
        unico = LeituraUnica()
        real = leitor.linhas_do_glifo
        guardada: list[object] = []

        def glifo_uma_vez(*a, g=guardada, r=real, **k):  # type: ignore[no-untyped-def]
            if not g:
                g.append(r(*a, **k))
            return g[0]

        with mock.patch.object(leitor, "linhas_do_glifo", glifo_uma_vez):
            folha = bancada_prosa.preparar_folha(pdf, indice, lingua=lingua, imagem=imagem, reconhecedor=rec, dpi=220, leitor_de_linha=unico)
            ref = regua.texto_de(ln.texto for ln in folha.linhas_da_referencia).split()
            for regra in contas:
                textos = {}
                for ligado in (False, True):
                    with mock.patch.object(arbitro, "GRAMATICA", ligado), mock.patch.object(leitor, "regra_da_folha", return_value=regra):
                        pagina = leitor.ler_pagina(pdf, indice, motor="fusao", reconhecedor=rec, imagem_rgb=imagem, dpi=220, lingua=lingua, leitor_de_linha=unico)
                    textos[ligado] = regua.texto_de(ln.texto for ln in regua.linhas_da_pagina(pagina)).split()
                for de, para, veredito in trocas(ref, textos[False], textos[True], lingua):
                    contas[regra][veredito] += 1
                    print(f"{regra} f{indice + 1} {veredito:8s} {de!r} -> {para!r}", flush=True)
                contas[regra]["folhas"] += 1
    saida = {"identidade": identidade, "folhas": folhas, "por_regra": {r: dict(c) for r, c in contas.items()}}
    print(json.dumps(saida["por_regra"], ensure_ascii=False))
    Path(destino).write_bytes((json.dumps(saida, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
