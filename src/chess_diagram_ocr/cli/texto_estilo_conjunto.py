"""`cvoff-texto-estilo-conjunto` -- o conjunto rotulado do estilo da palavra (S-661).

    cvoff-texto-estilo-conjunto --pdf-dir PDF --folhas 15 --json docs/metrics/texto_estilo_conjunto.json

Recortes de **palavra** das folhas tipográficas do acervo, rotulados pelo nome da fonte ou o bit da
camada (`normal`, `negrito`, `italico`, `negrito-italico`), e divididos **por livro** em treino,
validação e teste. A regra de cada passo está em `text/estilo.py`; aqui fica a leitura do PDF.

## Que livros entram

Só o que registra **os dois** estilos nas folhas lidas: um livro cuja camada não marca itálico rotularia
toda palavra itálica como `normal`, e o conjunto ensinaria o erro dele. Os livros que ficam de fora
saem listados no relatório, com o porquê.

## O que sai

Em `data/estilo/` (fora do git, como os outros conjuntos): `palavras.npz` com as imagens em
`ALTURA` x `LARGURA_MAXIMA`, a largura útil, a altura do recorte em pixel a 300 dpi (a régua de
controle da S-663), a classe e o livro de cada uma; e `manifesto.csv` com identidade do livro,
arquivo, folha, palavra, rótulo e partição. O relatório tem a contagem por classe e por partição e os
arquivos que a identidade juntou.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_text
from ..config import DATA_DIR, DEFAULT_PDF_DIR
from ..logging_setup import configure_logging
from ..text import estilo
from . import add_verbose, cli_errors

logger = logging.getLogger(__name__)

DPI = 300
"""A resolução do recorte: a de cima da reamostragem da S-661 (300 -> 150 -> 300)."""

MARGEM_PX = 2
ALTURA_MINIMA_PX = 10
"""A palavra mais baixa que entra: abaixo disso é índice, expoente ou número de nota, e o traço não
tem pixel bastante para se ler peso."""

PASTA_PADRAO = DATA_DIR / "estilo"


def folhas_de(total: int, quantas: int) -> list[int]:
    """`quantas` folhas espaçadas, longe da capa e do fim -- o protocolo da S-429. Pura."""
    if total <= 0:
        return []
    return sorted({min(total - 1, round(total * k / (quantas + 1))) for k in range(1, quantas + 1)})


def palavras_da_folha(pagina: Any) -> list[estilo.PalavraDeCamada]:
    """As palavras da camada desta folha, com o estilo de cada caractere pelo span dele."""
    from ..text.italico import _span_e_italico
    from ..text.negrito import _span_e_negrito

    palavras: list[estilo.PalavraDeCamada] = []
    for bloco in pagina.get_text("rawdict")["blocks"]:
        for linha in bloco.get("lines", []):
            caracteres = []
            for span in linha.get("spans", []):
                negrito, italico = _span_e_negrito(span), _span_e_italico(span)
                for c in span.get("chars", []):
                    caracteres.append((str(c["c"]), tuple(c["bbox"]), negrito, italico))
            palavras.extend(estilo.palavras_de_caracteres(caracteres))
    return palavras


def _cinza(pagina: Any) -> np.ndarray:
    import fitz

    pix = pagina.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, : pix.width]


def coletar(pdfs: list[Path], *, folhas: int) -> dict[str, Any]:
    """Lê as folhas tipográficas de cada livro e devolve os recortes, os textos e o que ficou de fora."""
    import fitz

    from ..text.camada import camada_tipografica

    escala = DPI / 72.0
    recortes: dict[str, list[tuple[np.ndarray, int, int, str, int, str]]] = {}
    textos: dict[str, frozenset[str]] = {}
    fora: dict[str, str] = {}
    for pdf in pdfs:
        try:
            documento = fitz.open(pdf)
        except Exception as erro:  # noqa: BLE001 - um PDF ilegível não derruba a coleta do acervo
            fora[pdf.name] = f"não abriu: {erro}"
            continue
        with documento:
            dele: list[tuple[np.ndarray, int, int, str, int, str]] = []
            tipograficas = 0
            for folha in folhas_de(documento.page_count, folhas):
                pagina = documento[folha]
                if not camada_tipografica(pagina):
                    continue
                tipograficas += 1
                rotuladas = [p for p in palavras_da_folha(pagina) if p.classe is not None]
                if not rotuladas:
                    continue
                cinza = _cinza(pagina)
                for palavra in rotuladas:
                    x0, y0, x1, y1 = (round(v * escala) for v in palavra.bbox)
                    x0, y0 = max(0, x0 - MARGEM_PX), max(0, y0 - MARGEM_PX)
                    x1, y1 = min(cinza.shape[1], x1 + MARGEM_PX), min(cinza.shape[0], y1 + MARGEM_PX)
                    if y1 - y0 < ALTURA_MINIMA_PX or x1 <= x0:
                        continue
                    imagem, util = estilo.normalizar(cinza[y0:y1, x0:x1])
                    dele.append((imagem, util, y1 - y0, str(palavra.classe), folha, palavra.texto))
            classes = Counter(r[3] for r in dele)
            if not tipograficas:
                fora[pdf.name] = "nenhuma folha tipográfica nas lidas (scan, ou camada de outro OCR)"
            elif not (classes["negrito"] + classes["negrito-italico"]) or not (classes["italico"] + classes["negrito-italico"]):
                fora[pdf.name] = f"a camada não registra os dois estilos nas folhas lidas ({dict(classes)})"
            else:
                recortes[pdf.name] = dele
                # A identidade pelo livro **inteiro**, e não pelas folhas lidas: dois arquivos do mesmo
                # livro com número de folhas diferente (o `_hq`) têm as amostras em folhas diferentes, e
                # a comparação pelas amostras não os juntava -- o mesmo livro caía na validação e no teste.
                textos[pdf.name] = estilo.sequencias("\n".join(folha.get_text("text") for folha in documento))
        logger.info("%s: %s", pdf.name, fora.get(pdf.name) or dict(classes))
    return {"recortes": recortes, "textos": textos, "fora": fora}


def gravar(coleta: dict[str, Any], pasta: Path) -> dict[str, Any]:
    """Junta os livros pela identidade, divide por livro e grava o `npz` e o manifesto. Devolve as contas."""
    recortes: dict[str, list[tuple[np.ndarray, int, int, str, int, str]]] = coleta["recortes"]
    identidade = estilo.identidades(coleta["textos"])
    contas: dict[str, Counter[str]] = {}
    for arquivo, dele in recortes.items():
        contas.setdefault(identidade[arquivo], Counter()).update(r[3] for r in dele)
    particao = estilo.particionar(contas)

    imagens, larguras, alturas, classes, livros, linhas = [], [], [], [], [], []
    ordem = sorted({identidade[a] for a in recortes})
    for arquivo in sorted(recortes):
        ident = identidade[arquivo]
        for imagem, util, altura, classe, folha, texto in recortes[arquivo]:
            imagens.append(imagem)
            larguras.append(util)
            alturas.append(altura)
            classes.append(estilo.CLASSES.index(classe))
            livros.append(ordem.index(ident))
            linhas.append((ident, arquivo, folha + 1, texto, classe, particao[ident], altura))
    pasta.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        pasta / "palavras.npz",
        imagens=np.stack(imagens) if imagens else np.zeros((0, estilo.ALTURA, estilo.LARGURA_MAXIMA), np.uint8),
        larguras=np.asarray(larguras, np.int16),
        alturas=np.asarray(alturas, np.int16),
        classes=np.asarray(classes, np.int8),
        livros=np.asarray(livros, np.int16),
        identidades=np.asarray(ordem),
        particoes=np.asarray([particao[i] for i in ordem]),
    )
    with (pasta / "manifesto.csv").open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida, lineterminator="\n")
        escritor.writerow(("identidade", "arquivo", "folha", "palavra", "rotulo", "particao", "altura_px"))
        escritor.writerows(linhas)

    por_particao: dict[str, Counter[str]] = {p: Counter() for p in estilo.PARTICOES}
    for linha in linhas:
        por_particao[linha[5]][linha[4]] += 1
    juntados: dict[str, list[str]] = {}
    for arquivo, ident in identidade.items():
        juntados.setdefault(ident, []).append(arquivo)
    return {
        "palavras": len(linhas),
        "por_classe": dict(Counter(linha[4] for linha in linhas)),
        "por_particao": {p: {c: conta.get(c, 0) for c in estilo.CLASSES} for p, conta in por_particao.items()},
        "livros_por_particao": {
            p: sorted(a for a in recortes if particao[identidade[a]] == p) for p in estilo.PARTICOES
        },
        "arquivos_juntados_pela_identidade": {i: sorted(a) for i, a in juntados.items() if len(a) > 1},
        "identidade_em_duas_particoes": [],  # por construção: a partição é da identidade
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta dos livros (padrao: PDF/).")
    parser.add_argument("--folhas", type=int, default=15, help="Folhas por livro, espacadas (padrao: 15).")
    parser.add_argument("--saida", type=Path, default=PASTA_PADRAO, help="Pasta do conjunto (padrao: data/estilo/).")
    parser.add_argument("--json", type=Path, help="Grava o relatorio neste caminho.")
    add_verbose(parser)
    return parser


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    from ..checkpoint import git_commit, git_worktree_dirty

    pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))
    if not pdfs:
        print(f"Nenhum PDF em {args.pdf_dir}.")
        return 0
    coleta = coletar(pdfs, folhas=args.folhas)
    contas = gravar(coleta, Path(args.saida))
    relatorio = {
        "item": "S-661 · o conjunto rotulado do estilo da palavra",
        "medido_em": date.today().isoformat(),
        "codigo": {"commit": git_commit(), "arvore_suja": git_worktree_dirty()},
        "protocolo": (
            f"{args.folhas} folhas espacadas de cada PDF; so as folhas tipograficas (camada.camada_tipografica); "
            f"a palavra rotulada pelo nome da fonte ou o bit de cada caractere, e a que mistura estilo fica fora; "
            f"recorte a {DPI} dpi em {estilo.ALTURA}x{estilo.LARGURA_MAXIMA}; livros juntados pelo conteudo "
            f"(sequencias de cinco palavras, parentesco > {estilo.PARENTESCO}) e divididos por livro"
        ),
        **contas,
        "livros_fora": coleta["fora"],
    }
    print(f"{contas['palavras']} palavra(s) de {sum(len(v) for v in contas['livros_por_particao'].values())} arquivo(s).")
    for particao, conta in contas["por_particao"].items():
        print(f"  {particao}: {conta}")
    if args.json:
        atomic_write_text(args.json, json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
        print(f"Relatorio em {args.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
