"""A suíte irmã lendo as folhas da régua (S-707): grava o JSONL que o `cvoff-texto-prosa --importar` recebe.

Roda **com o Python da suíte** (`Suite_de_Edicao_de_Xadrez/.venv`, com `PYTHONPATH=<suite>/src`), e não importa nada deste
repositório: o tronco ela alcança pela ponte dela (`caissa.vision.classify.cvoff`). A entrada é o JSONL da própria régua, que diz
as folhas e a língua, e a lista de PDF vem por `--pastas`, porque a identidade é a do caderno (o sha1 do primeiro MiB).

**`recognize_image`, e não `recognize` com o PDF.** Com a página de PDF na mão, a suíte lê primeiro a camada (`pdf_text_layer`, nível
0 do `routing.py`), e medir contra a própria camada daria ~0 por construção, sem dizer nada da fusão. É o mesmo cuidado da M0 contra
a M1 (seção 3 do roadmap): o que se compara com `fusao` é o caminho da imagem.

Saída: uma linha por folha, `{identidade, folha, texto, segundos}`. **Tem texto de livro: fora do repositório.** Em pedaços: quem já
está na saída não é lido de novo, e `--limite-segundos` para depois da folha em curso.

Uso: suite_ler.py <regua.jsonl> <saida.jsonl> --pastas A B [--dpi 300] [--limite-segundos N] [--maximo N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path


def identidade_de(pdf: Path) -> str:
    with pdf.open("rb") as arquivo:
        return hashlib.sha1(arquivo.read(1 << 20)).hexdigest()[:16]


def achar(pastas: list[str], procurados: set[str]) -> dict[str, Path]:
    achados: dict[str, Path] = {}
    for pasta in pastas:
        for pdf in sorted(Path(pasta).glob("*.pdf")):
            identidade = identidade_de(pdf)
            if identidade in procurados and identidade not in achados:
                achados[identidade] = pdf
    return achados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("regua")
    ap.add_argument("saida")
    ap.add_argument("--pastas", nargs="+", required=True)
    ap.add_argument("--dpi", type=float, default=300.0)
    ap.add_argument("--diagramas", default="", help="o JSON do suite_diagramas.py: os retângulos que ela não tem por onde receber")
    ap.add_argument("--limite-segundos", type=float, default=0.0)
    ap.add_argument("--maximo", type=int, default=0)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.ERROR)

    import fitz
    from caissa.ingest.pdf.ocr_service import OcrService

    with open(args.regua, encoding="utf-8") as arquivo:
        folhas = [(r["identidade"], r["folha"], r["lingua"]) for r in map(json.loads, arquivo)]
    saida = Path(args.saida)
    feitas = set()
    if saida.is_file():
        with saida.open(encoding="utf-8") as arquivo:
            feitas = {(r["identidade"], r["folha"]) for r in map(json.loads, arquivo)}
    faltam = [f for f in folhas if (f[0], f[1]) not in feitas]
    if args.maximo:
        faltam = faltam[: args.maximo]
    achados = achar(args.pastas, {f[0] for f in faltam})
    diagramas = json.loads(Path(args.diagramas).read_text(encoding="utf-8")) if args.diagramas else {}
    servico = OcrService()
    inicio = time.perf_counter()
    with saida.open("a", encoding="utf-8", newline="\n") as destino:
        for n, (identidade, folha, lingua) in enumerate(faltam, start=1):
            if args.limite_segundos and time.perf_counter() - inicio > args.limite_segundos:
                print(f"# parou pelo limite: faltam {len(faltam) - n + 1}", flush=True)
                return 3
            t0 = time.perf_counter()
            with fitz.open(achados[identidade]) as doc:
                imagem = _render(doc[folha - 1], args.dpi)
                _pintar(imagem, diagramas.get(f"{identidade}:{folha}", ()), args.dpi)
                resposta = servico.recognize_image(imagem, dpi=args.dpi, lang=lingua, page_index=folha - 1)
            registro = {"identidade": identidade, "folha": folha, "texto": resposta.text, "segundos": time.perf_counter() - t0}
            destino.write(json.dumps(registro, ensure_ascii=False) + "\n")
            destino.flush()
            print(f"  {n}/{len(faltam)} {identidade[:8]} f{folha} {registro['segundos']:.1f}s {len(resposta.text)} caracteres", flush=True)
    return 0


def _pintar(imagem, retangulos, dpi: float) -> None:
    """Os diagramas de branco, com a folga de 8 px a 220 dpi do `tess_pagina`."""
    s = dpi / 72.0
    folga = int(round(8 * dpi / 220))
    for x0, y0, x1, y1 in retangulos:
        imagem[max(0, int(y0 * s) - folga): int(y1 * s) + folga, max(0, int(x0 * s) - folga): int(x1 * s) + folga] = 255


def _render(pagina, dpi: float):
    import numpy as np

    pix = pagina.get_pixmap(dpi=int(dpi), alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()


if __name__ == "__main__":
    raise SystemExit(main())
