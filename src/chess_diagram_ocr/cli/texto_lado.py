"""`cvoff-texto-lado` -- quantos diagramas deixam de sair `default` com o glifo (S-207).

    cvoff-texto-lado --livros 4 --paginas 12

**O que este comando mede, e por que ele é o item.** A costura do lado a jogar já existia desde a
S-43: o `CaptionReader` lê a faixa em volta do diagrama com o motor que lhe derem, e o `glifo` é
um motor desde a S-181. O que não existia era a **medição por livro** -- e sem ela "o
classificador de casa lê o lado melhor que o RapidOCR" é opinião.

A tabela responde a três perguntas, uma por coluna:

    lidos          diagramas cujo lado veio do glifo, e que sairiam `default` sem ele
    default        continuaram assumidos: ninguém respondeu
    contradições   a leitura e a legalidade da S-17 discordaram

## A contradição é linha da tabela, e não erro a esconder

Quando o texto diz "pretas jogam" e a posição só é legal com as brancas, `infer_side_to_move` faz
a legalidade vencer e marca `conflicting` -- e a fila da S-22 pontua isso com
`WEIGHT_SOURCES_DISAGREE`. **Não há prioridade fixa que resolva**: ou o reconhecimento leu uma peça
errada, ou a legenda foi associada ao diagrama vizinho, e nos dois casos há algo para um humano
olhar. Contar as contradições é o que impede que elas virem ruído de log.

## Os dois lados da comparação

Cada página é lida **duas vezes**: uma sem motor de legenda nenhum (a camada de texto sozinha, que
é o programa antes deste item) e uma com o glifo. A diferença entre as duas colunas `default` é o
que o item entrega.

**Rodar só com o glifo não bastaria**, porque a maioria dos livros do acervo tem camada de texto e
ali o motor nem chega a ser chamado -- `_lines_with_ocr` só o aciona onde a camada calou. Sem o
lado de controle, a tabela mostraria uma cobertura alta que a camada já dava sozinha.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text import lado as _lado
from . import EXIT_BAD_INPUT, EXIT_OK, cli_errors

logger = logging.getLogger(__name__)

DESTINO_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_lado.json"

LIVROS = 4
PAGINAS = 12
"""Páginas por livro. O OCR de legenda roda por diagrama, e é o custo que a S-215 acabou de medir."""


def _lados_da_pagina(
    pdf: Path,
    indice: int,
    *,
    caption_reader: Any,
    dpi: int = 220,
) -> tuple[list[Any], list[float]]:
    """`(as decisões de lado, as confianças)` dos diagramas desta página.

    Passa pelo caminho de verdade -- detecção, contexto, `infer_side_to_move` -- em vez de
    reimplementá-lo: é a mesma razão pela qual `iter_pdf_diagrams` existe, e é o que faz esta
    medição descrever o programa e não um primo dele.

    **Não roda o modelo de peças**, e por isso não é uma varredura: a `placement` que a legalidade
    precisa vem do próprio contexto quando ele a traz, e onde não vier a cascata cai na declaração
    do texto -- que é exatamente a metade que este item mede.
    """
    from ..detection.hybrid import detect_diagrams_in_pdf_page
    from ..pdf_io import render_pdf_page
    from ..pdf_text import contexts_for_pdf_page
    from ..semantics import infer_side_to_move

    candidatos = detect_diagrams_in_pdf_page(pdf, indice, render_pdf_page(pdf, indice, dpi=dpi))
    if not candidatos:
        return ([], [])
    bboxes = [tuple(float(v) for v in c.bbox_pdf) for c in candidatos]
    contextos = contexts_for_pdf_page(pdf, indice, bboxes, caption_reader=caption_reader)  # type: ignore[arg-type]

    lados: list[Any] = []
    confiancas: list[float] = []
    for contexto in contextos:
        # `placement` vazio: a legalidade não tem o que provar, e a cascata responde pelo texto ou
        # pelo padrão -- que são as duas colunas que a tabela compara.
        lados.append(infer_side_to_move("8/8/8/8/8/8/8/8", contexto))
        confiancas.append(float(getattr(contexto, "side_to_move_confidence", 1.0)))
    return (lados, confiancas)


def medir_livro(
    pdf: Path,
    *,
    paginas: int,
    caption_reader: Any,
    dpi: int = 220,
) -> _lado.PorLivro:
    """A linha da tabela de um livro, sobre as `paginas` primeiras folhas com diagrama."""
    from ..pdf_io import open_document

    with open_document(pdf) as doc:
        total_de_paginas = doc.page_count

    lados: list[Any] = []
    confiancas: list[float] = []
    vistas = 0
    for indice in range(total_de_paginas):
        if vistas >= paginas:
            break
        da_pagina, das_confiancas = _lados_da_pagina(pdf, indice, caption_reader=caption_reader, dpi=dpi)
        if not da_pagina:
            continue
        vistas += 1
        lados.extend(da_pagina)
        confiancas.extend(das_confiancas)
    return _lado.contabilizar(pdf.stem[:60], lados, confiancas)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cvoff-texto-lado",
        description="Mede quantos diagramas deixam de sair `default` com o glifo lendo a legenda (S-207).",
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta do acervo.")
    parser.add_argument("--pdf", type=Path, default=None, help="Um PDF só, em vez do acervo.")
    parser.add_argument("--livros", type=int, default=LIVROS, help=f"Quantos livros. Padrão: {LIVROS}.")
    parser.add_argument("--paginas", type=int, default=PAGINAS, help=f"Páginas com diagrama por livro. Padrão: {PAGINAS}.")
    parser.add_argument("--json", type=Path, default=DESTINO_PADRAO, help="Onde gravar a tabela.")
    parser.add_argument("--verbose", action="store_true", help="Log em DEBUG.")
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    if args.pdf is not None:
        if not args.pdf.exists():
            logger.error("PDF não encontrado: %s", args.pdf)
            return EXIT_BAD_INPUT
        livros = [args.pdf]
    else:
        if not args.pdf_dir.is_dir():
            logger.error("Pasta do acervo não encontrada: %s", args.pdf_dir)
            return EXIT_BAD_INPUT
        livros = sorted(p for p in args.pdf_dir.glob("*.pdf") if p.is_file())[: max(1, args.livros)]
    if not livros:
        logger.error("Nenhum PDF para medir em %s.", args.pdf_dir)
        return EXIT_BAD_INPUT

    from ..ocr_caption import build_caption_reader
    from ..text.recognizer import ModeloInvalido, build_glyph_recognizer

    try:
        leitor = build_caption_reader(build_glyph_recognizer())
    except ModeloInvalido as exc:
        logger.error("O motor de glifo não pôde ser carregado: %s", exc)
        return EXIT_BAD_INPUT
    if leitor is None:  # pragma: no cover - build_caption_reader devolve None só sem motor
        logger.error("Não foi possível montar o leitor de legenda.")
        return EXIT_BAD_INPUT

    com_glifo: list[_lado.PorLivro] = []
    so_camada: list[_lado.PorLivro] = []
    for pdf in livros:
        logger.info("%s", pdf.name)
        # O lado de controle vem primeiro: se a corrida for interrompida, o que sobra é o
        # programa de hoje medido, que ainda é um número; o inverso não seria.
        so_camada.append(medir_livro(pdf, paginas=args.paginas, caption_reader=None))
        com_glifo.append(medir_livro(pdf, paginas=args.paginas, caption_reader=leitor))

    print("Sem motor de legenda (a camada de texto sozinha -- o programa antes deste item):")
    for linha in _lado.tabela(so_camada):
        print(linha)
    print("")
    print("Com o glifo lendo a legenda onde a camada calou:")
    for linha in _lado.tabela(com_glifo):
        print(linha)

    antes, depois = _lado.total(so_camada), _lado.total(com_glifo)
    ganho = antes.assumidos - depois.assumidos
    print("")
    print(
        f"Deixaram de sair `default`: {ganho} de {antes.assumidos} diagramas assumidos "
        f"({(ganho / antes.assumidos):.1%} deles)."
        if antes.assumidos
        else "Nenhum diagrama saía `default` nesta amostra: a camada de texto já respondia por todos."
    )
    if depois.contradicoes > antes.contradicoes:
        print(
            f"Contradições novas: {depois.contradicoes - antes.contradicoes}. "
            "Vão para a fila da S-22 marcadas -- não são resolvidas por prioridade fixa."
        )

    dados: dict[str, Any] = {
        "item": "S-207",
        "fonte": _lado.FONTE,
        "livros": len(livros),
        "paginas_por_livro": args.paginas,
        "sem_motor": [linha.para_json() for linha in so_camada],
        "com_glifo": [linha.para_json() for linha in com_glifo],
        "total_sem_motor": antes.para_json(),
        "total_com_glifo": depois.para_json(),
        "deixaram_de_ser_palpite": ganho,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.json, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
    print(f"Tabela gravada em {args.json}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
