"""A matéria-prima da S-760 a S-766: cada folha lida pela fusão, com o que entrou nela e o que a guarda viu.

    coletar.py <conjunto> <saida.jsonl> [--limite-segundos 160] [--alternativas] [--por-livro 12]

`conjunto` é `ouro_dev` e `prata` (as folhas dos manifestos), `reservado_ouro` e `reservado_prata` (o **pedaço reservado**, folhas
dos mesmos livros que nenhum manifesto cita, sorteadas por `sha256("S-760:identidade:folha")`), ou `livro:<identidade>`, para a medida
da S-766. **O split `teste` não passa por aqui**: a função só conhece o dev e a prata.

**A saída tem texto de livro**: vai para fora do repositório. Rodar de novo com a mesma saída continua de onde parou.
Com `--alternativas`, o `lstm_choice_mode=2` em hOCR nas mesmas linhas, ao preço de mais um processo por folha (S-718, S-745).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import fitz

from chess_diagram_ocr.cli.texto_prosa import folhas_do_conjunto
from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.text import (
    admissao,
    bancada_prosa,
    confianca_palavra,
    fusao,
    leitor,
    leitor_de_linha,
    ouro,
    prata,
    regua_prosa,
    tesseract,
)
from chess_diagram_ocr.text.recognizer import build_glyph_recognizer

RAIZ = Path(os.environ.get("CVOFF_RAIZ", "."))
DPI = 220
MINIMO_DE_CARACTERES = 600
"""Folha de prosa do pedaço reservado: a capa e o índice ensinam pouco, e custam o mesmo."""


class LeitorComAlternativas(leitor_de_linha.LeitorTesseract):
    """O leitor de produção, e ao lado dele as alternativas do LSTM nas mesmas linhas."""

    def __init__(self) -> None:
        super().__init__()
        self.por_linha: list[list[dict[str, Any]]] = []

    def ler_linhas(self, recortes, *, lingua, dpi, sem_dicionario=False):  # type: ignore[no-untyped-def]
        leitura = super().ler_linhas(recortes, lingua=lingua, dpi=dpi, sem_dicionario=sem_dicionario)
        self.por_linha = _alternativas(recortes, lingua, dpi)
        return leitura


def _alternativas(recortes: Any, lingua: str, dpi: int) -> list[list[dict[str, Any]]]:
    validos = [i for i, r in enumerate(recortes) if r.size]
    saida: list[list[dict[str, Any]]] = [[] for _ in recortes]
    if not validos:
        return saida
    hocr = tesseract.rodar(
        tesseract.achar_motor(), tesseract._tiff_de([recortes[i] for i in validos]), lingua=lingua, dpi=dpi, psm=tesseract.PSM_DA_LINHA,  # noqa: SLF001
        timeout=max(30.0, 2.0 * len(validos)), opcoes=("-c", "lstm_choice_mode=2"), formato="hocr",
    )
    paginas = hocr.split("class='ocr_page'")[1:]
    for posicao, pagina in enumerate(paginas):
        if posicao < len(validos):
            saida[validos[posicao]] = [_palavra_do_hocr(bloco) for bloco in pagina.split("class='ocrx_word'")[1:]]
    return saida


def _palavra_do_hocr(bloco: str) -> dict[str, Any]:
    import re

    escolha = re.compile(r"title='x_confs ([\d.]+)'>([^<]*)</span>")
    posicoes = []
    for grupo in bloco.split("id='lstm_choices_")[1:]:
        opcoes = [(c, float(n) / 100.0) for n, c in escolha.findall(grupo)]
        if opcoes and opcoes[0][0].strip():
            posicoes.append(opcoes)
    if not posicoes:
        return {"t": "", "topo": 0.0, "margem": 0.0, "alt": 0}
    topo = [p[0][1] for p in posicoes]
    margem = [p[0][1] - (p[1][1] if len(p) > 1 else 0.0) for p in posicoes]
    return {
        "t": "".join(p[0][0] for p in posicoes), "topo": round(min(topo), 4), "margem": round(min(margem), 4),
        "alt": sum(1 for p in posicoes if len(p) > 1),
    }


def _tipo_de(c: Any) -> dict[str, Any]:
    return {"texto": c.texto, "origem": c.origem, "do_glifo": c.do_glifo, "do_leitor": c.do_leitor, "confianca": c.confianca}


def ler_folha(pdf: str, identidade: str, indice: int, lingua: str, reconhecedor: Any, *, alternativas: bool, oraculo: bool) -> dict[str, Any]:
    imagem = render_pdf_page(pdf, indice, DPI)
    leitor_da_folha = LeitorComAlternativas() if alternativas else leitor_de_linha.LeitorTesseract()
    folha = bancada_prosa.preparar_folha(
        pdf, indice, lingua=lingua, imagem=imagem, reconhecedor=reconhecedor, dpi=DPI, leitor_de_linha=leitor_da_folha
    )
    capturado: dict[str, Any] = {"entrada": [], "tokens": [], "regra": "", "medida": None}
    original = leitor._com_prosa_de_outro_leitor  # noqa: SLF001
    original_marcar = fusao.marcar
    original_medir = leitor._guarda.medir  # noqa: SLF001
    original_calibrar = confianca_palavra.calibrar_folha

    def com_prosa(cruas, leituras, **kw):  # type: ignore[no-untyped-def]
        capturado["regra"] = kw.get("regra", "")
        capturado["entrada"] = [
            {
                "g": c.texto,
                "c_g": [None if x is None else round(float(x), 4) for x in leitor._confianca_de_token(c.confiancas, c.texto.split())],  # noqa: SLF001
                "t": None if li is None else li[0],
                "c_t": None if li is None else [round(float(x), 4) for x in li[1]],
                "caixa": [c.caixa.x1, c.caixa.y1, c.caixa.x2, c.caixa.y2],
            }
            for c, li in zip(cruas, leituras, strict=True)
        ]
        return original(cruas, leituras, **kw)

    def marcar(linhas, **kw):  # type: ignore[no-untyped-def]
        capturado["tokens"] = [[_tipo_de(t) for t in linha] for linha in linhas]
        return original_marcar(linhas, **kw)

    def calibrar(linhas, **kw):  # type: ignore[no-untyped-def]
        # Com a S-760 ligada, `marcar` não roda: os tokens saem daqui, com a confiança de quem os escreveu.
        capturado["tokens"] = [[_tipo_de(t) for t in linha] for linha in linhas]
        return original_calibrar(linhas, **kw)

    def medir(*a, **kw):  # type: ignore[no-untyped-def]
        capturado["medida"] = original_medir(*a, **kw)
        return capturado["medida"]

    leitor._com_prosa_de_outro_leitor = com_prosa  # noqa: SLF001
    fusao.marcar = marcar
    leitor._guarda.medir = medir  # noqa: SLF001
    confianca_palavra.calibrar_folha = calibrar
    try:
        inicio = time.perf_counter()
        pagina = leitor.ler_pagina(pdf, indice, motor="fusao", reconhecedor=reconhecedor, imagem_rgb=imagem, dpi=DPI, lingua=lingua, leitor_de_linha=leitor_da_folha)
        segundos = time.perf_counter() - inicio
    finally:
        leitor._com_prosa_de_outro_leitor = original  # noqa: SLF001
        fusao.marcar = original_marcar
        leitor._guarda.medir = original_medir  # noqa: SLF001
        confianca_palavra.calibrar_folha = original_calibrar
    ref = regua_prosa.texto_de(ln.texto for ln in folha.linhas_da_referencia)
    linhas = regua_prosa.linhas_da_pagina(pagina)
    hipoteses = {"fusao": regua_prosa.texto_de(ln.texto for ln in linhas), "glifo": regua_prosa.texto_de(ln.texto for ln in regua_prosa.linhas_da_pagina(folha.glifo))}
    if oraculo:
        hipoteses["tess_oraculo"] = bancada_prosa.MOTORES_DE_BANCADA["tess_oraculo"](folha)
    m = capturado["medida"]
    return {
        "identidade": identidade, "folha": indice + 1, "lingua": lingua, "ref": ref, "hip": hipoteses,
        "placar": bancada_prosa.pontuar_hipoteses(ref, hipoteses, lingua),
        "regra": capturado["regra"], "entrada": capturado["entrada"], "tokens": capturado["tokens"],
        "linhas": [{"texto": ln.texto, "revisar_em": list(ln.revisar_em), "confianca_em": list(ln.confianca_em)} for ln in linhas],
        "alternativas": getattr(leitor_da_folha, "por_linha", None),
        "guarda": None if m is None else {
            "densidade": m.densidade, "componentes": m.componentes, "lidos": m.lidos, "linhas_estimadas": m.linhas_estimadas,
            "linhas_lidas": m.linhas_lidas, "camada": m.caracteres_da_camada, "nao_lida": m.nao_lida, "parcial": m.parcial,
        },
        "avisos": [a.codigo for a in pagina.avisos], "segundos": segundos,
    }


def _livros(identidades: set[str], cache: Path) -> dict[str, str]:
    conhecidos: dict[str, str] = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else {}
    faltam = identidades - set(conhecidos)
    if faltam:
        achados = ouro.localizar(faltam, [RAIZ / "PDF", RAIZ / "PDF Digitais"])
        conhecidos.update({k: str(v) for k, v in achados.items()})
        cache.write_bytes(json.dumps(conhecidos, ensure_ascii=False, indent=0).encode("utf-8"))
    return conhecidos


def reservado(conjunto: str, por_livro: int, cache: Path) -> list[tuple[str, int, str, str]]:
    """O pedaço reservado: `(identidade, folha base 1, língua, domínio)`, pelo sorteio escrito no cabeçalho."""
    if conjunto == "reservado_ouro":
        citadas = {(f.identidade, f.folha) for f in folhas_do_conjunto("ouro", "dev")}
        linguas = {f.identidade: f.lingua for f in folhas_do_conjunto("ouro", "dev")}
    else:
        p = prata.carregar(None)
        citadas = {(f.identidade, f.folha) for f in p.folhas}
        linguas = {f.identidade: f.lingua for f in p.folhas}
    achados = _livros(set(linguas), cache)
    saida = []
    for identidade in sorted(linguas):
        if identidade not in achados:
            print("# livro não achado:", identidade, flush=True)
            continue
        with fitz.open(achados[identidade]) as doc:
            ordem = sorted(range(1, doc.page_count + 1), key=lambda n: hashlib.sha256(f"S-760:{identidade}:{n}".encode()).hexdigest())
            perfil, produtor = (admissao.perfil_do_livro(doc), admissao.produtor_de(doc)) if conjunto == "reservado_ouro" else (None, "")
            tomadas = 0
            for n in ordem:
                if tomadas >= por_livro:
                    break
                if (identidade, n) in citadas or len(doc[n - 1].get_text()) < MINIMO_DE_CARACTERES:
                    continue
                if perfil is not None and not admissao.admitir_folha(doc[n - 1], [], produtor=produtor, perfil=perfil).admitida:
                    continue
                saida.append((identidade, n, linguas[identidade], "digital" if conjunto == "reservado_ouro" else "scan"))
                tomadas += 1
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("conjunto")
    ap.add_argument("saida")
    ap.add_argument("--limite-segundos", type=float, default=160.0)
    ap.add_argument("--alternativas", action="store_true")
    ap.add_argument("--por-livro", type=int, default=12)
    ap.add_argument("--lingua", default="eng")
    ap.add_argument("--folhas", default="", help="livro:<identidade>: de, até, base 1, no passo pedido: 10,200,10")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    saida = Path(args.saida)
    cache = saida.parent / "livros_por_identidade.json"
    if args.conjunto == "ouro_dev":
        folhas = [(f.identidade, f.folha, f.lingua, "digital") for f in folhas_do_conjunto("ouro", "dev")]
    elif args.conjunto == "prata":
        folhas = [(f.identidade, f.folha, f.lingua, "scan") for f in folhas_do_conjunto("prata", "")]
    elif args.conjunto.startswith("reservado_"):
        folhas = reservado(args.conjunto, args.por_livro, cache)
    elif args.conjunto.startswith("livro:"):
        identidade = args.conjunto.split(":", 1)[1]
        de, ate, passo = (int(x) for x in args.folhas.split(","))
        folhas = [(identidade, n, args.lingua, "digital") for n in range(de, ate + 1, passo)]
    else:
        raise SystemExit(f"conjunto desconhecido: {args.conjunto}")
    achados = _livros({f[0] for f in folhas}, cache)
    feitas = set()
    if saida.is_file():
        with saida.open(encoding="utf-8") as arquivo:
            feitas = {(r["identidade"], r["folha"]) for r in map(json.loads, arquivo)}
    faltam = [f for f in folhas if (f[0], f[1]) not in feitas and f[0] in achados]
    print(f"# {len(folhas)} folhas, {len(feitas)} feitas, {len(faltam)} a ler", flush=True)
    if not faltam:
        return 0
    rec = build_glyph_recognizer(str(RAIZ / "models" / "char_classifier.pt"))
    leitor.ler_pagina(achados[faltam[0][0]], faltam[0][1] - 1, motor="glifo", reconhecedor=rec, dpi=DPI)
    inicio = time.perf_counter()
    with saida.open("a", encoding="utf-8", newline="\n") as destino:
        for n, (identidade, folha, lingua, dominio) in enumerate(faltam, 1):
            if time.perf_counter() - inicio > args.limite_segundos:
                print(f"# parou pelo limite: faltam {len(faltam) - n + 1}", flush=True)
                return 3
            registro = ler_folha(achados[identidade], identidade, folha - 1, lingua, rec, alternativas=args.alternativas, oraculo=dominio == "scan")
            registro.update(conjunto=args.conjunto, dominio=dominio)
            destino.write(json.dumps(registro, ensure_ascii=False) + "\n")
            destino.flush()
            p = registro["placar"]["fusao|tip"]
            print(f"  {n}/{len(faltam)} {identidade[:8]} f{folha} {p['erros']['prosa'] / max(1, p['total']['prosa']):.4f} {registro['segundos']:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
