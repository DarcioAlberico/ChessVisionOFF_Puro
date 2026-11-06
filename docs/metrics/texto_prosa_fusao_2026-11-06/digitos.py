"""S-743 e a saída de dígitos da S-729: números de lance e casas inválidos, com o árbitro desligado e ligado.

    digitos.py livro <nome no PDF/> <língua> <saida.json>    folhas espaçadas de um livro (o Bachmann e o Neumann)
    digitos.py prata <saida.json> [--de N --ate M]           as folhas da prata

**Esta contagem não sai da gramática do árbitro:** as expressões abaixo são a régua desta medida, escritas à parte. A forma de lance é
larga de propósito no denominador. Cada folha lê uma vez com o glifo e com o Tesseract, e as duas variantes fundem as mesmas leituras.
Só contagens saem daqui; o token inválido vai à tela, para quem mede olhar.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import fitz

from chess_diagram_ocr.cli.texto_prosa import _achar_livros, _pastas_padrao, folhas_do_conjunto
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import arbitro, leitor, leitor_de_linha, lexico
from chess_diagram_ocr.text import regua_prosa as regua
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

HOMOGLIFOS = "ıIl|i]zZgqAsSöbGyvTB"
PECA = "KDTLSBRQNCFAP"
CASA = rf"[a-h][1-8{re.escape(HOMOGLIFOS)}]"
SEP = r"[-—–―=<>×xX:~]+"
PONTA = r"[+#†‡✝t!?.,;:)\]]*"
NUM = r"(?:[\dıIl|oOzZsSBGy]{1,3}(?:\.{1,3}|\))\s*)?"
FORMA = re.compile(rf"^[(\[:]?{NUM}(?:[{PECA}]?{CASA}{SEP}{CASA}|[{PECA}][a-h]?[1-8]?[xX:×]?{CASA}){PONTA}$")
CASA_OK = re.compile(
    rf"^[(\[:]?(?:\d{{1,3}}(?:\.{{1,3}}|\))\s*)?(?:[{PECA}]?[a-h][1-8]{SEP}[a-h][1-8]|[{PECA}][a-h]?[1-8]?[xX:×]?[a-h][1-8]){PONTA}$"
)
NUMERO = re.compile(r"^[(\[]?[\dıIl|oOzZ]{1,3}(?:\.{1,3}|\))$")
NUMERO_OK = re.compile(r"^[(\[]?\d{1,3}(?:\.{1,3}|\))$")
SO_ANTIGO = re.compile(r"^[(\[]?(?:Io|ıı|Il|II|lo|ıo)\.")


def contar(texto: str, palavras: frozenset[str]) -> Counter[str]:
    c: Counter[str] = Counter()
    tokens = texto.split()
    for k, t in enumerate(tokens):
        if FORMA.match(t) and not (re.sub(r"[^\w]", "", t).casefold() in palavras and not any(ch.isdigit() for ch in t)):
            c["casas"] += 1
            if not CASA_OK.match(t):
                c["casas_invalidas"] += 1
                c[f"inv:{t}"] += 1
        if NUMERO.match(t) and k + 1 < len(tokens) and (FORMA.match(tokens[k + 1]) or re.match(r"^[a-h][1-8]", tokens[k + 1])):
            c["numeros"] += 1
            if not NUMERO_OK.match(t):
                c["numeros_invalidos"] += 1
                c[f"inv:{t}"] += 1
    c["io"] += sum(1 for t in tokens if SO_ANTIGO.match(t))
    return c


class LeituraUnica:
    """Um Tesseract por lote: as duas variantes recebem o mesmo texto, e a diferença entre elas é só o árbitro."""

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


def medir_folha(pdf: str, indice: int, lingua: str, rec: object, palavras: frozenset[str], totais: dict[bool, Counter[str]]) -> None:
    imagem = render_pdf_page(pdf, indice, 220)
    leitor_unico = LeituraUnica()
    real = leitor.linhas_do_glifo
    guardada: list[object] = []

    def glifo_uma_vez(*a, **k):  # type: ignore[no-untyped-def]
        if not guardada:
            guardada.append(real(*a, **k))
        return guardada[0]

    leitor.linhas_do_glifo = glifo_uma_vez
    try:
        for ligado in (False, True):
            arbitro.GRAMATICA = ligado
            pagina = leitor.ler_pagina(pdf, indice, motor="fusao", reconhecedor=rec, imagem_rgb=imagem, dpi=220, lingua=lingua, leitor_de_linha=leitor_unico)
            totais[ligado].update(contar(regua.texto_de(ln.texto for ln in regua.linhas_da_pagina(pagina)), palavras))
    finally:
        leitor.linhas_do_glifo = real
        arbitro.GRAMATICA = True


def publicar(nome: str, totais: dict[bool, Counter[str]], folhas: int) -> dict[str, object]:
    saida: dict[str, object] = {"folhas": folhas}
    for ligado, c in totais.items():
        numeros = {k: v for k, v in c.items() if not k.startswith("inv:")}
        numeros["casas_validas"] = round(1 - c["casas_invalidas"] / max(1, c["casas"]), 4)
        saida["com_arbitro" if ligado else "sem_arbitro"] = numeros
    print(nome, json.dumps(saida, ensure_ascii=False))
    print("  ainda inválidos:", [(k[4:], v) for k, v in totais[True].most_common() if k.startswith("inv:")][:30])
    return saida


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raiz = os.environ.get("CVOFF_RAIZ", "")
    rec = build_glyph_recognizer()
    totais: dict[bool, Counter[str]] = {False: Counter(), True: Counter()}
    if sys.argv[1] == "livro":
        nome, lingua, destino = sys.argv[2:5]
        pdf = next(p for p in (Path(raiz) / "PDF").glob("*.pdf") if p.name.startswith(nome))
        with fitz.open(pdf) as doc:
            n = len(doc)
        folhas = list(range(30, n - 5, (n - 35) // 16))
        palavras = frozenset(lexico.do_livro(lingua) or ())
        for f in folhas:
            medir_folha(str(pdf), f, lingua, rec, palavras, totais)
        Path(destino).write_bytes((json.dumps(publicar(nome, totais, len(folhas)), ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
        return 0
    destino = sys.argv[2]
    de = int(sys.argv[sys.argv.index("--de") + 1]) if "--de" in sys.argv else 0
    ate = int(sys.argv[sys.argv.index("--ate") + 1]) if "--ate" in sys.argv else 10**6
    folhas_da_prata = folhas_do_conjunto("prata", "")[de:ate]
    achados = _achar_livros(folhas_da_prata, _pastas_padrao(raiz))
    for f in folhas_da_prata:
        medir_folha(str(achados[f.identidade]), f.folha - 1, f.lingua, rec, frozenset(lexico.do_livro(f.lingua) or ()), totais)
    Path(destino).write_bytes((json.dumps(publicar("prata", totais, len(folhas_da_prata)), ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
