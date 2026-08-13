"""`cvoff-games` — casa os diagramas do acervo com a base de partidas (S-72/S-73).

    cvoff-games --all                        # relata, sem escrever nada
    cvoff-games --all --apply                # grava lance, vez e headers nas anotações
    cvoff-games --book "Karpov 1" --names    # só o caminho por nome, ~150 s

**Relatar é o padrão, gravar é opção.** Isto escreve na anotação de exportação de centenas de
diagramas de uma vez, e a taxa de casamento é justamente o que decide se vale gravar. É a
mesma disciplina do `cvoff-provenance --match`.

**Um livro por vez é o jeito caro.** A varredura por posição custa ~104 min, e esse custo é da
**passada**, não do livro: o conjunto-alvo cabe na memória sejam 1.400 posições ou 40 mil.
Rodar `--book` cinco vezes custa cinco vezes o que `--all` custa uma. O `--book` existe para
medir um livro isolado, não para processar o acervo.

**A Galeria é dona do arquivo de anotação.** Com o livro aberto naquela aba, ela tem a versão
dela em memória e vai regravá-la ao editar -- então `--apply` num livro aberto perde o que
este comando gravou. Feche a aba, ou reabra o livro depois.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
from pathlib import Path

from ..config import DEFAULT_PDF_DIR
from ..gallery import DEFAULT_GALLERY_DIR, load_annotations, save_annotations
from ..gallery_scan import GalleryIndex, load_index
from ..games_db import (
    DEFAULT_DATABASE_DIR,
    DiagramMatch,
    default_database_path,
    match_entries,
    match_positions,
    pair_from_caption,
    scan_by_players,
    scan_by_positions,
)
from ..logging_setup import configure_logging, default_log_file
from ..ui.gallery_model import GalleryModel

logger = logging.getLogger(__name__)

MODE_NAMES = "names"
MODE_POSITIONS = "positions"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Casa os diagramas varridos na Galeria com uma base de partidas em PGN.",
    )
    parser.add_argument("--book", action="append", default=[], help="nome (ou parte) do PDF. Repetível.")
    parser.add_argument("--all", action="store_true", help="todos os livros já varridos na Galeria.")
    parser.add_argument(
        "--positions",
        dest="mode",
        action="store_const",
        const=MODE_POSITIONS,
        default=MODE_POSITIONS,
        help="busca por posição: alcança todo diagrama, custa uma passada com replay (padrão).",
    )
    parser.add_argument(
        "--names",
        dest="mode",
        action="store_const",
        const=MODE_NAMES,
        help="busca por nome: só os diagramas cuja legenda traz os jogadores, ~150 s.",
    )
    parser.add_argument("--apply", action="store_true", help="grava nas anotações. Sem isto, só relata.")
    parser.add_argument("--database", type=Path, default=None, help=f"o .pgn. Padrão: o maior de {DEFAULT_DATABASE_DIR}")
    parser.add_argument("--gallery-dir", type=Path, default=DEFAULT_GALLERY_DIR)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--workers", type=int, default=None, help="processos na busca por posição. 1 = sem paralelismo.")
    parser.add_argument(
        "--max-games",
        type=int,
        default=5,
        help="acima disto a posição não identifica partida, e nada é preenchido (padrão: 5).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _books(args: argparse.Namespace) -> list[Path]:
    """Os PDFs pedidos, resolvidos contra os índices que a Galeria já varreu.

    O índice é a pré-condição: sem varrer, não há diagrama para casar -- e mandar varrer aqui
    faria este comando carregar o modelo, o que ele não faz de propósito.
    """
    indices = sorted(args.gallery_dir.glob("*.index.json"))
    nomes = [caminho.name[: -len(".index.json")] for caminho in indices]
    if args.all:
        escolhidos = nomes
    else:
        escolhidos = [nome for nome in nomes if any(pedaco.lower() in nome.lower() for pedaco in args.book)]
        faltando = [pedaco for pedaco in args.book if not any(pedaco.lower() in nome.lower() for nome in nomes)]
        for pedaco in faltando:
            logger.warning("Nenhum livro varrido casa com %r. Varra-o na aba Galeria primeiro.", pedaco)
    return [args.pdf_dir / f"{nome}.pdf" for nome in escolhidos]


def _load(book: Path, gallery_dir: Path) -> GalleryIndex | None:
    indice = load_index(book, directory=gallery_dir)
    if indice is None or not indice.entries:
        logger.warning("%s: índice vazio ou ausente.", book.name)
        return None
    return indice


def _report(book: Path, entries: int, matches: list[DiagramMatch], max_games: int) -> tuple[int, int]:
    """Imprime o placar do livro e devolve `(casados, identificáveis)`."""
    identificaveis = [casamento for casamento in matches if casamento.games_matched <= max_games]
    print(f"\n{book.name}")
    print(f"  diagramas varridos ......... {entries}")
    print(f"  casaram na base ............ {len(matches)}  ({len(matches) / max(1, entries):.1%})")
    print(f"  identificam a partida ...... {len(identificaveis)}  (até {max_games} partidas)")
    print(f"  com partida única .......... {sum(1 for c in matches if c.games_matched == 1)}")
    return len(matches), len(identificaveis)


def _apply(book: Path, indice: GalleryIndex, matches: list[DiagramMatch], args: argparse.Namespace) -> None:
    """Grava pelo mesmo caminho que a aba usa -- `GalleryModel.apply_matches`.

    Não é reuso por economia de linha: é a única forma de a regra ("preenche só o vazio, e
    posição comum não preenche nada") ser a mesma nos dois lugares. Duas implementações dela
    divergiriam, e foi isso que a 6.4 encontrou nos rótulos de procedência.
    """
    modelo = GalleryModel(
        index=indice,
        annotations=load_annotations(book, directory=args.gallery_dir),
        pdf_path=book,
        gallery_dir=args.gallery_dir,
    )
    tocados, campos = modelo.apply_matches(matches, max_games=args.max_games)
    save_annotations(book, modelo.annotations, directory=args.gallery_dir)
    print(f"  gravados ................... {campos} campo(s) em {tocados} diagrama(s)")


def main(argv: list[str] | None = None) -> int:
    mp.freeze_support()  # o bundle da S-55 congela o processo; sem isto, `spawn` o reexecuta
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    base = args.database or default_database_path()
    if base is None or not base.is_file():
        logger.error("Base de partidas não encontrada. Ponha um .pgn em %s ou passe --database.", DEFAULT_DATABASE_DIR)
        return 2

    livros = _books(args)
    if not livros:
        logger.error("Nada a fazer: use --all ou --book com um livro já varrido na Galeria.")
        return 2

    indices = {livro: indice for livro in livros if (indice := _load(livro, args.gallery_dir)) is not None}
    if not indices:
        return 2

    print(f"base: {base} ({base.stat().st_size / 1e9:.1f} GB)")
    print(f"livros: {len(indices)}  |  modo: {args.mode}")

    if args.mode == MODE_POSITIONS:
        # Uma varredura para todos os livros: o custo e da passada, nao do alvo.
        alvos = {entrada.placement for indice in indices.values() for entrada in indice.entries}
        print(f"posições-alvo distintas: {len(alvos)}  (a varredura é uma só para todos os livros)")
        indice_posicoes = scan_by_positions(
            base,
            alvos,
            workers=args.workers,
            progress=lambda feitos, total: print(f"  ... pedaço {feitos} de {total}", flush=True),
        )
        print(f"partidas lidas: {indice_posicoes.games_read}")
        casamentos_por_livro = {
            livro: match_positions(indice.entries, indice_posicoes, max_games=args.max_games)
            for livro, indice in indices.items()
        }
    else:
        pares = {
            par
            for indice in indices.values()
            for entrada in indice.entries
            if (par := pair_from_caption(entrada.caption)) is not None
        }
        print(f"pares de nomes distintos: {len(pares)}")
        if not pares:
            logger.warning("Nenhuma legenda destes livros traz os dois jogadores.")
            return 0
        partidas = scan_by_players(base, pares)
        print(f"pares com partida na base: {len(partidas)}")
        casamentos_por_livro = {
            livro: match_entries(indice.entries, partidas) for livro, indice in indices.items()
        }

    total_casados = total_identificaveis = 0
    for livro, indice in indices.items():
        casamentos = casamentos_por_livro[livro]
        casados, identificaveis = _report(livro, len(indice.entries), casamentos, args.max_games)
        total_casados += casados
        total_identificaveis += identificaveis
        if args.apply:
            _apply(livro, indice, casamentos, args)

    print(f"\ntotal: {total_casados} casado(s), {total_identificaveis} identificável(is)")
    if not args.apply:
        print("Nada foi gravado. Para gravar nas anotações: cvoff-games ... --apply")
    return 0


if __name__ == "__main__":  # pragma: no cover - entrada de linha de comando
    raise SystemExit(main())
