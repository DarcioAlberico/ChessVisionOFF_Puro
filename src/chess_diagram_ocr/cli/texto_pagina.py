"""`cvoff-texto-pagina` — a página inteira lida como texto, e não só a faixa de legenda (S-211).

    cvoff-texto-pagina "PDF/AAGAARD - Practical Chess Defence.pdf" --paginas 58-62
    cvoff-texto-pagina LIVRO.pdf --paginas 40 --motor camada --json saida.json

**Para que ele existe.** `text/leitor.py` monta a `PaginaLida`, e sem um comando ela só seria
observável de dentro da janela -- que é onde nenhuma medição deveria precisar entrar. Este é o
lado sem interface do mesmo caminho: a aba de texto e este comando chamam `ler_pagina`, e é por
isso que o que a aba mostra é reproduzível fora dela.

## O que sai, e por que em duas formas

`--texto` (o padrão) escreve o texto corrido na ordem de leitura, com `[Diagrama N]` onde o
diagrama entra. É o que se lê para conferir e o que se cola em outro lugar.

`--json` escreve a `PaginaLida` serializada: coluna, bloco, linha, bbox, confiança e procedência.
É o que outro programa consome, e o que sobrevive a ir e voltar sem perda -- travado por teste.

## O motor não é escolha de gosto

O padrão é `glifo` -- o classificador treinado neste projeto --, e não a camada de texto do PDF.
Medido em 2026-08-24 sobre 16 páginas de 4 livros **com** camada: a camada devolveu **zero**
figurinas de xadrez contra 360 do classificador, porque onde o livro imprime `♘` ela traz o
codepoint cru da fonte, sem mapeamento (`2.♘xd4` vira `2.l0xd4`). E a codificação muda de livro
para livro. O raciocínio inteiro está no cabeçalho de `text/leitor.py`.

`--motor camada` continua existindo para quem quiser a camada de um livro específico, e é o que
serve à comparação: `docs/metrics/texto_pagina.json` foi feito rodando os dois lados.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ..logging_setup import configure_logging
from . import EXIT_BAD_INPUT, cli_errors

logger = logging.getLogger(__name__)


def intervalo_de_paginas(texto: str) -> list[int]:
    """`"58"`, `"58-62"`, `"58,60,62"` -> índices 0-based.

    **Os números da linha de comando são 1-based**, como os que o leitor de PDF mostra, e o índice
    interno é 0-based. A conversão mora aqui, num lugar só, porque tê-la em dois é como o "diagrama
    2" da tela deixou de ser o `[Diagram "2"]` do PGN antes da S-14.
    """
    saida: list[int] = []
    for pedaco in str(texto).split(","):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        if "-" in pedaco[1:]:
            inicio, _, fim = pedaco.partition("-")
            a, b = int(inicio), int(fim)
            if b < a:
                raise ValueError(f"intervalo invertido: {pedaco!r}")
            saida.extend(range(a - 1, b))
        else:
            saida.append(int(pedaco) - 1)
    if any(i < 0 for i in saida):
        raise ValueError("página 0 não existe: a numeração da linha de comando começa em 1")
    return saida


def _resumo(pagina: Any) -> str:
    """A linha de status de uma página: o que foi achado e de onde veio."""
    procedencias = ", ".join(f"{k}:{v}" for k, v in sorted(pagina.procedencias().items()))
    return (
        f"p{pagina.pagina + 1:<5d} colunas={len(pagina.colunas)} blocos={len(pagina.blocos)} "
        f"diagramas={len(pagina.diagramas)} conf_min={pagina.confianca_minima:.2f} "
        f"impresso={pagina.numero_impresso if pagina.numero_impresso is not None else '-'} "
        f"[{procedencias or 'vazia'}]"
    )


@cli_errors
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cvoff-texto-pagina",
        description="Lê a página inteira como texto (S-211) e escreve o texto ou a PaginaLida.",
    )
    parser.add_argument("pdf", type=Path, help="O PDF a ler.")
    parser.add_argument(
        "--paginas",
        default="1",
        help="Páginas 1-based: '58', '58-62' ou '58,60,62'. Padrão: a primeira.",
    )
    parser.add_argument(
        "--motor",
        choices=("glifo", "camada", "auto"),
        default="glifo",
        help=(
            "glifo (padrão) lê com o classificador deste projeto; camada usa a camada de texto do "
            "PDF; auto é o glifo com a camada como reserva se os pesos não carregarem."
        ),
    )
    parser.add_argument("--dpi", type=int, default=220, help="DPI de renderização. Padrão: 220.")
    parser.add_argument(
        "--arranjo",
        choices=("prosa", "grade"),
        default="prosa",
        help="grade lê fileira a fileira, para folha de exercícios (S-216). Padrão: prosa.",
    )
    parser.add_argument(
        "--bloco",
        action="store_true",
        help=(
            "Liga o modo bloco da S-188 no motor de glifo. Desligado por padrão: medido em "
            "docs/metrics/texto_pagina.json, ele custa ~50x o tempo e na média piora."
        ),
    )
    parser.add_argument(
        "--colados",
        choices=("auto", "nunca", "sempre"),
        default="auto",
        help=(
            "Separador de glifo colado (S-186). Padrão auto: o árbitro confirma cada corte. "
            "Em itálico as letras encostam, e sem ele 'Mecking' sai 'M♔king'. 'sempre' parte "
            "figurina correta e fica fora. Ver docs/metrics/texto_colados_pagina.json."
        ),
    )
    parser.add_argument(
        "--sem-caixa-alta",
        action="store_true",
        help=(
            "Desliga a decisão de maiúscula/minúscula pela altura do box. Ligada por padrão: "
            "medido em docs/metrics/texto_caixa_alta.json, CER 0,1434 -> 0,1114 em 11 páginas, "
            "com 11 melhorando e nenhuma piorando."
        ),
    )
    parser.add_argument(
        "--sem-marca-fina",
        action="store_true",
        help=(
            "Desliga a promoção a apóstrofo da marca que assenta no alto da linha "
            "(Black,s -> Black's). Ligada por padrão -- e não pelo CER, que não se move: ver "
            "docs/metrics/texto_marca_fina.json."
        ),
    )
    parser.add_argument(
        "--sem-empilhados",
        action="store_true",
        help=(
            "Desliga a fusão do glifo de dois contornos (: ; =). Ligada por padrão: sem ela os "
            "três têm recall ZERO -- nunca chegam inteiros ao classificador. Ver "
            "docs/metrics/texto_empilhados.json."
        ),
    )
    parser.add_argument(
        "--sem-italico",
        action="store_true",
        help=(
            "Desliga a correção de `/` para `l` em linha inclinada. Ligada por padrão: em texto "
            "itálico o `l` é um traço pendido, que é o desenho do `/`. Ver "
            "docs/metrics/texto_italico.json."
        ),
    )
    parser.add_argument(
        "--dicionario",
        action="store_true",
        help=(
            "Liga o léxico para desempatar entre os candidatos do modelo. Desligado por padrão: "
            "medido, ele corrige ZERO -- ver docs/metrics/texto_dicionario.json."
        ),
    )
    parser.add_argument(
        "--sem-numeros",
        action="store_true",
        help=(
            "Desliga a troca do oval por zero dentro de número (2o -> 20) e o conserto do roque "
            "(O.O -> 0-0). Ligada por padrão: ver docs/metrics/texto_numero.json."
        ),
    )
    parser.add_argument(
        "--sem-negrito",
        action="store_true",
        help=(
            "Não anota o peso da fonte. Ligado por padrão, e vem da CAMADA de texto -- 13 dos 41 "
            "livros a registram; nos outros o campo fica 'não se sabe'. A via da imagem foi "
            "medida e recusada: ver docs/metrics/texto_negrito.json."
        ),
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Grava a PaginaLida serializada aqui, em vez do texto na saída padrão.",
    )
    parser.add_argument(
        "--sem-marcas",
        action="store_true",
        help="Não escreve [Diagrama N] no texto -- para quem quer só a prosa.",
    )
    parser.add_argument("--verbose", action="store_true", help="Log em DEBUG.")
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    if not args.pdf.exists():
        logger.error("PDF não encontrado: %s", args.pdf)
        return EXIT_BAD_INPUT
    try:
        indices = intervalo_de_paginas(args.paginas)
    except ValueError as exc:
        logger.error("--paginas inválido: %s", exc)
        return EXIT_BAD_INPUT
    if not indices:
        logger.error("--paginas não selecionou nenhuma página.")
        return EXIT_BAD_INPUT

    from ..text.leitor import ler_pagina

    # **Um reconhecedor para todas as páginas.** Carregar o classificador custa ~3 s, e construí-lo
    # por página faria um livro de 60 páginas gastar três minutos só abrindo o mesmo arquivo.
    reconhecedor = None
    if args.motor != "camada":
        from ..text.leitor import leitor_de_linha_padrao
        from ..text.recognizer import ModeloInvalido, build_glyph_recognizer

        try:
            reconhecedor = build_glyph_recognizer(
                leitor_de_linha=leitor_de_linha_padrao() if args.bloco else None
            )
        except ModeloInvalido as exc:
            if args.motor == "glifo":
                logger.error("O motor de glifo não pôde ser carregado: %s", exc)
                return EXIT_BAD_INPUT
            logger.warning("Sem classificador de glifo (%s); só as páginas com camada serão lidas.", exc)

    lidas: list[Any] = []
    for indice in indices:
        try:
            pagina = ler_pagina(
                args.pdf,
                indice,
                dpi=args.dpi,
                motor=args.motor,
                arranjo=args.arranjo,
                reconhecedor=reconhecedor,
                modo_bloco=args.bloco,
                colados=args.colados,
                caixa_alta=not args.sem_caixa_alta,
                marca_fina=not args.sem_marca_fina,
                empilhados=not args.sem_empilhados,
                italico=not args.sem_italico,
                dicionario=args.dicionario,
                numeros=not args.sem_numeros,
                marcar_negrito=not args.sem_negrito,
            )
        except (IndexError, ValueError) as exc:
            logger.warning("Página %d não pôde ser lida: %s", indice + 1, exc)
            continue
        lidas.append(pagina)
        logger.info("%s", _resumo(pagina))

    if not lidas:
        logger.error("Nenhuma página foi lida.")
        return EXIT_BAD_INPUT

    if args.json is not None:
        from ..atomic_io import atomic_write_text

        conteudo = json.dumps([p.para_json() for p in lidas], ensure_ascii=False, indent=2)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(args.json, conteudo + "\n")
        logger.info("PaginaLida de %d página(s) em %s", len(lidas), args.json)
        return 0

    for pagina in lidas:
        if len(lidas) > 1:
            print(f"\n===== página {pagina.pagina + 1} =====")
        print(pagina.texto(com_marcas=not args.sem_marcas))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
