"""A S-725 medida: o lote, a leitura por linha e o cache leem a mesma coisa, nas folhas do ouro-dev?

    python medir.py --dados fora/cache.jsonl --cache fora/cache_texto --limite-segundos 160
    python medir.py --dados fora/cache.jsonl --compilar docs/metrics/texto_cache_20261106.json

Cada folha é lida quatro vezes pelo `ler_pagina(motor="fusao")`: lote sem cache (a régua), um processo por linha
(`tesseract.LOTE_POR_FOLHA` desligada), cache frio e cache quente. Compara o `sha` do texto da página e o das linhas que o
leitor devolveu, com as confianças: **a linha pode mudar sem a fusão deixar ver**.

O JSONL fica fora do repositório, por hábito da régua, mesmo sem texto: leva o `sha` de cada folha. O relatório só leva agregados.
Rode de novo com o mesmo `--dados` para continuar. **O tempo daqui não julga nada** enquanto a máquina estiver dividida: o G4 se
mede depois, com a máquina parada, na janela.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MODOS = ("lote", "por_linha", "cache_frio", "cache_quente")


class _Anotador:
    """O leitor de verdade, anotando o `sha` do que devolveu: é a comparação abaixo da fusão."""

    def __init__(self, leitor: Any) -> None:
        self.leitor = leitor
        self.linhas = 0
        self.soma = hashlib.sha256()

    def ler_linhas(self, recortes: Sequence[Any], *, lingua: str, dpi: int) -> Any:
        leitura = self.leitor.ler_linhas(recortes, lingua=lingua, dpi=dpi)
        self.linhas += len(leitura.linhas)
        for linha in leitura.linhas:
            self.soma.update(repr(None if linha is None else (linha.texto, linha.confiancas)).encode("utf-8"))
        return leitura

    def ler_folha(self, cinza: Any, *, lingua: str, dpi: int) -> Any:
        return self.leitor.ler_folha(cinza, lingua=lingua, dpi=dpi)


def medir(args: argparse.Namespace) -> int:
    from chess_diagram_ocr.cli.texto_prosa import (
        _achar_livros,
        _pastas_padrao,
        folhas_do_conjunto,
        recusar_dentro_do_repositorio,
    )
    from chess_diagram_ocr.pdf_io import render_pdf_page
    from chess_diagram_ocr.text import cache_texto, leitor_de_linha, tesseract
    from chess_diagram_ocr.text.leitor import ler_pagina
    from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

    recusar_dentro_do_repositorio(args.dados)
    recusar_dentro_do_repositorio(args.cache)
    dados = Path(args.dados)
    feitas = set()
    if dados.is_file():
        feitas = {(r["identidade"], r["folha"]) for r in map(json.loads, dados.read_text(encoding="utf-8").splitlines())}
    folhas = folhas_do_conjunto("ouro", "dev", manifesto=None)
    achados = _achar_livros(folhas, _pastas_padrao(args.raiz))
    cache = cache_texto.CacheDeLeitura(Path(args.cache))
    if not feitas:
        cache.limpar()
    reconhecedor = build_glyph_recognizer(args.modelo) if args.modelo else build_glyph_recognizer()
    inicio = time.perf_counter()
    aquecido = False
    print(f"# {len(folhas)} folhas, {len(feitas)} feitas", flush=True)

    def ler(pdf: str, indice: int, imagem: Any, lingua: str, leitor: Any) -> tuple[str, str, int, float, str]:
        anotador = _Anotador(leitor)
        comeco = time.perf_counter()
        lida = ler_pagina(
            pdf, indice, motor="fusao", reconhecedor=reconhecedor, imagem_rgb=imagem, dpi=220, lingua=lingua, leitor_de_linha=anotador
        )
        return (
            hashlib.sha256(lida.texto().encode("utf-8")).hexdigest()[:16],
            anotador.soma.hexdigest()[:16],
            anotador.linhas,
            time.perf_counter() - comeco,
            ",".join(a.codigo for a in lida.avisos),
        )

    with dados.open("a", encoding="utf-8", newline="\n") as saida:
        for f in folhas:
            if (f.identidade, f.folha) in feitas:
                continue
            if args.limite_segundos and time.perf_counter() - inicio > args.limite_segundos:
                print("# parou pelo limite: rode de novo com o mesmo --dados", flush=True)
                return 3
            pdf = str(achados[f.identidade])
            indice = f.folha - 1
            imagem = render_pdf_page(pdf, indice, 220)
            if not aquecido:
                ler_pagina(pdf, indice, motor="glifo", reconhecedor=reconhecedor, imagem_rgb=imagem, dpi=220)
                aquecido = True
            registro: dict[str, Any] = {"identidade": f.identidade, "folha": f.folha, "lingua": f.lingua, "estrato": f.estrato}
            sem_cache = leitor_de_linha.LeitorTesseract()
            com_cache = leitor_de_linha.LeitorTesseract(cache=cache)
            registro["lote"] = ler(pdf, indice, imagem, f.lingua, sem_cache)
            tesseract.LOTE_POR_FOLHA = False
            try:
                registro["por_linha"] = ler(pdf, indice, imagem, f.lingua, sem_cache)
            finally:
                tesseract.LOTE_POR_FOLHA = True
            antes = cache.tamanho()
            registro["cache_frio"] = ler(pdf, indice, imagem, f.lingua, com_cache)
            registro["bytes_da_entrada"] = cache.tamanho() - antes
            registro["cache_quente"] = ler(pdf, indice, imagem, f.lingua, com_cache)
            saida.write(json.dumps(registro) + "\n")
            saida.flush()
            print(f.identidade[:8], f.folha, *(f"{m}={registro[m][3]:.1f}s" for m in MODOS), flush=True)
    return 0


def compilar(args: argparse.Namespace) -> int:
    registros = [json.loads(linha) for linha in Path(args.dados).read_text(encoding="utf-8").splitlines()]
    raiz = Path(__file__).resolve().parents[3]

    def git(*comando: str) -> str:
        return subprocess.run(["git", "-C", str(raiz), *comando], capture_output=True, text=True, check=False).stdout.strip()

    diferentes = {}
    for modo in MODOS[1:]:
        diferentes[modo] = {
            "texto_da_pagina": sum(r[modo][0] != r["lote"][0] for r in registros),
            "linhas_do_leitor": sum(r[modo][1] != r["lote"][1] for r in registros),
            "avisos": sum(r[modo][4] != r["lote"][4] for r in registros),
        }
    relatorio = {
        "item": "S-725: o lote por folha, a leitura por linha e o cache, nas folhas do ouro-dev",
        "como": "docs/metrics/texto_cache_2026-11-06/medir.py",
        "commit": git("rev-parse", "HEAD"),
        "src_sujo": bool(git("status", "--porcelain", "--", "src")),
        "folhas": len(registros),
        "livros": len({r["identidade"] for r in registros}),
        "linhas_lidas": sum(r["lote"][2] for r in registros),
        "folhas_diferentes_do_lote": diferentes,
        "bytes_por_entrada": {
            "media": round(statistics.mean(r["bytes_da_entrada"] for r in registros)),
            "maximo": max(r["bytes_da_entrada"] for r in registros),
        },
        "segundos_por_folha_sob_contencao": {m: round(statistics.mean(r[m][3] for r in registros), 2) for m in MODOS},
        "ressalvas": [
            "Os tempos foram medidos com a máquina dividida com outras duas corridas, com OMP_NUM_THREADS=3. Não julgam o G4, que se mede "
            "depois, com a máquina parada, na janela e com o cache desligado.",
            "As 27 folhas são dev: os livros já foram vistos. O split teste não foi aberto.",
        ],
    }
    Path(args.compilar).write_bytes((json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(relatorio["folhas_diferentes_do_lote"], ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dados", required=True, help="o JSONL por folha, fora do repositório")
    ap.add_argument("--cache", default="", help="a pasta do cache medido, fora do repositório")
    ap.add_argument("--limite-segundos", type=float, default=0.0)
    ap.add_argument("--raiz", default=os.environ.get("CVOFF_RAIZ", ""))
    ap.add_argument("--modelo", default="")
    ap.add_argument("--compilar", default="", help="escreve o relatório neste JSON")
    args = ap.parse_args()
    return compilar(args) if args.compilar else medir(args)


if __name__ == "__main__":
    sys.exit(main())
