"""Os retângulos de diagrama de cada folha do JSONL da régua, para a suíte ler a mesma folha que o `tess_pagina` lê (S-707).

Em produção a suíte recebe os diagramas da frente de visão dela. Em `recognize_image` eles não têm por onde entrar, e sem
máscara o tabuleiro vira texto inventado (`o na Po OB a O No á Da Cum`): 58 erros de prosa na folha 58 do Seirawan, 3 na fusão. Isso
mediria a falta da máscara, e não a fusão. Por isso os diagramas saem daqui, os mesmos da régua (camada + glifo), em pontos, e o
`suite_ler.py --diagramas` os pinta de branco.

Sem texto de livro na saída: só identidade, folha e retângulos. Roda com o `.venv` do tronco.

Uso: suite_diagramas.py <regua.jsonl> <saida.json> [--pastas A B]. Raiz com `PDF/` e `PDF Digitais/`: `CVOFF_RAIZ`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import ouro
from chess_diagram_ocr.text.leitor import ler_pagina
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

DPI = 220


def main(regua: str, saida: str) -> None:
    raiz = Path(os.environ.get("CVOFF_RAIZ") or Path(__file__).resolve().parents[3])
    with open(regua, encoding="utf-8") as arquivo:
        folhas = [(r["identidade"], r["folha"]) for r in map(json.loads, arquivo)]
    achados = ouro.localizar({f[0] for f in folhas}, [raiz / "PDF", raiz / "PDF Digitais"])
    reconhecedor = build_glyph_recognizer()
    retangulos: dict[str, list[list[float]]] = {}
    for identidade, folha in folhas:
        pdf = str(achados[identidade])
        imagem = render_pdf_page(pdf, folha - 1, DPI)
        camada = ler_pagina(pdf, folha - 1, motor="camada", imagem_rgb=imagem, dpi=DPI)
        glifo = ler_pagina(pdf, folha - 1, motor="glifo", reconhecedor=reconhecedor, imagem_rgb=imagem, dpi=DPI)
        retangulos[f"{identidade}:{folha}"] = [[round(float(v), 2) for v in d.bbox] for d in (*camada.diagramas, *glifo.diagramas)]
    Path(saida).write_bytes((json.dumps(retangulos, sort_keys=True) + "\n").encode("utf-8"))
    print(f"{len(retangulos)} folhas, {sum(len(v) for v in retangulos.values())} retângulos")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
