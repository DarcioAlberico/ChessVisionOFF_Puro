"""`cvoff-texto-pesquisavel` -- o livro com a camada de texto invisível do que o motor leu (S-210).

    cvoff-texto-pesquisavel "PDF/AAGAARD - Practical Chess Defence.pdf" --paginas 58-62
    cvoff-texto-pesquisavel LIVRO.pdf --paginas 1-40 --seco

**O problema é o mais óbvio que um livro de xadrez tem.** Os livros do acervo ou não têm camada de
texto -- 11 dos 41 na amostra de 2026-08-24 --, ou têm uma que erra a notação inteira: a S-211
mediu **zero figurinas** na camada contra 360 no classificador. Buscar `Nf3` num livro de xadrez é
a coisa mais óbvia a querer fazer, e não dá.

## A página não muda um pixel

O texto entra em `render_mode=3`, invisível, sobre a página original. O que se acrescenta é texto
sem tinta, posicionado sobre cada **linha** lida -- e é por linha, e não por parágrafo, para que o
retângulo que a busca devolve cubra a palavra.

## Duas travas de honestidade, e as duas recusam em vez de adivinhar

**Linha que o motor leu sem votação folgada não entra.** A camada é invisível: quem busca e recebe
um acerto acredita no acerto, e não há nada na tela para desmenti-lo. `--piso` move o corte, e o
relatório conta quantas linhas ficaram de fora.

**Figurina vira letra do algébrico inglês, e isso é declarado.** A fonte da camada é a base 14 do
PDF, que cobre Latin-1 e não tem `♘` -- e nenhuma fonte é copiada para cá antes de a licença ser
conferida. Sem a troca, tudo que o motor leu de mais precioso cairia fora da camada. `♘` -> `N`
põe na busca a forma que quem busca digita; a página continua mostrando a figurina.
`--sem-figurinas` desliga a troca.

## `--seco` diz o que faria, e não grava nada
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from ..logging_setup import configure_logging
from ..text import pdf_pesquisavel as _camada
from . import EXIT_BAD_INPUT, EXIT_OK, add_dpi_argument, add_verbose, cli_errors
from .texto_pagina import intervalo_de_paginas

logger = logging.getLogger(__name__)

SUFIXO = "-pesquisavel"


@cli_errors
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cvoff-texto-pesquisavel",
        description="Escreve o livro com a camada de texto invisível do que o motor leu (S-210).",
    )
    parser.add_argument("pdf", type=Path, help="O livro a tornar pesquisável.")
    parser.add_argument(
        "--paginas",
        default="1",
        help="Páginas 1-based a ler: '58', '58-62' ou '58,60,62'. Padrão: a primeira.",
    )
    parser.add_argument("--saida", type=Path, default=None, help=f"Padrão: o nome do livro com '{SUFIXO}'.")
    add_dpi_argument(parser, help="DPI da leitura. Padrão: 220.")
    parser.add_argument(
        "--motor",
        choices=("glifo", "camada", "auto"),
        default="glifo",
        help="Quem lê a página. Padrão: o classificador deste projeto.",
    )
    parser.add_argument(
        "--piso",
        type=float,
        default=_camada.PISO_DA_CAMADA,
        help=(
            f"Confiança mínima de uma linha para ela entrar na camada. Padrão: {_camada.PISO_DA_CAMADA}. "
            "Abaixo dele a linha fica fora -- um acerto de busca falso não tem como ser desmentido."
        ),
    )
    parser.add_argument(
        "--sem-figurinas",
        action="store_true",
        help="Não troca ♘ por N na camada. Sem a troca, a notação inteira cai fora pela fonte.",
    )
    parser.add_argument(
        "--so-sem-camada",
        action="store_true",
        help="Pula as folhas que já têm texto, em vez de somar a nossa camada à delas.",
    )
    parser.add_argument("--seco", "--dry-run", action="store_true", help="Diz o que faria e não grava nada.")
    add_verbose(parser)
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
    from ..text.recognizer import ModeloInvalido, build_glyph_recognizer

    reconhecedor = None
    if args.motor != "camada":
        try:
            # Um reconhecedor para o livro inteiro: carregá-lo custa ~3 s, e por página um livro
            # de 60 folhas gastaria três minutos só abrindo o mesmo arquivo.
            #
            # **Sem leitor de linha**, e é a S-188: na página inteira o modo bloco custa ~50x o
            # tempo e piora o livro nativo digital. Um livro de 400 folhas com ele seria uma noite.
            reconhecedor = build_glyph_recognizer()
        except ModeloInvalido as exc:
            if args.motor == "glifo":
                logger.error("O motor de glifo não pôde ser carregado: %s", exc)
                return EXIT_BAD_INPUT
            logger.warning("Sem classificador de glifo (%s); só as folhas com camada serão lidas.", exc)

    lidas: list[Any] = []
    for indice in indices:
        logger.info("lendo a folha %d", indice + 1)
        try:
            lidas.append(ler_pagina(args.pdf, indice, dpi=args.dpi, motor=args.motor, reconhecedor=reconhecedor))
        except (ValueError, RuntimeError, OSError) as exc:
            logger.warning("A folha %d não pôde ser lida (%s); ela fica sem camada.", indice + 1, exc)

    if not lidas:
        logger.error("Nenhuma folha foi lida: não há camada a escrever.")
        return EXIT_BAD_INPUT

    destino = args.saida or args.pdf.with_name(f"{args.pdf.stem}{SUFIXO}.pdf")
    relatorio = _camada.escrever_camada(
        lidas,
        destino,
        origem=args.pdf,
        piso=args.piso,
        figurinas=not args.sem_figurinas,
        so_sem_camada=args.so_sem_camada,
        seco=args.seco,
    )

    print(relatorio.resumo())
    for aviso in relatorio.avisos:
        print(f"  aviso: {aviso}")

    pares = _camada.pares_sem_mapeamento(args.pdf)
    if pares:
        print("")
        print("Este livro tem glifo sem mapeamento na camada de origem (o caminho ToUnicode da S-210):")
        for par in pares[:6]:
            print(f"  {par.fonte}: {par.ocorrencias} ocorrência(s) de U+FFFD")

    if relatorio.escrito is not None:
        print(f"Escrito em {relatorio.escrito}")
    elif args.seco:
        print("--seco: nada foi gravado.")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
