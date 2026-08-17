"""`cvoff-games` — casa os diagramas do acervo com a base de partidas (S-72/S-73).

    cvoff-games --all                        # relata, sem escrever nada
    cvoff-games --all --apply                # grava lance, vez e headers nas anotações
    cvoff-games --all --census               # o estado do acervo; não abre a base
    cvoff-games --build-index                # o índice por nome, uma vez (~11 min)
    cvoff-games --book "Karpov 1" --names    # só o caminho por nome, ~150 s
    cvoff-games --all --database uma.pgn     # uma base só; repetível

**A base é a pasta, não um arquivo (S-93).** Sem `--database`, todos os `.pgn` de
`pgn_database/` entram -- e o custo é proporcional ao que a pasta tem. Acrescentar um arquivo
invalida o índice por nome e o cache de posições, e os dois avisam como refazer: as contagens
de uma base não valem para outra, e é a contagem que autoriza preencher header.

**Relatar é o padrão, gravar é opção.** Isto escreve na anotação de exportação de centenas de
diagramas de uma vez, e a taxa de casamento é justamente o que decide se vale gravar. É a
mesma disciplina do `cvoff-provenance --match`.

**Um livro por vez é o jeito caro.** A varredura por posição custa ~29 min, e esse custo é da
**passada**, não do livro: o conjunto-alvo cabe na memória sejam 1.400 posições ou 40 mil.
Rodar `--book` cinco vezes custa cinco vezes o que `--all` custa uma. O `--book` existe para
medir um livro isolado, não para processar o acervo.

**E, desde a S-84, o que já foi perguntado não é perguntado de novo.** O cache guarda a
resposta por posição -- inclusive "a base não conhece esta" --, então a segunda execução custa
segundos e um livro novo custa só as posições que ele trouxe.

**A Galeria é dona do arquivo de anotação.** Com o livro aberto naquela aba, ela tem a versão
dela em memória e vai regravá-la ao editar -- então `--apply` num livro aberto perde o que
este comando gravou. Feche a aba, ou reabra o livro depois.
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..config import DEFAULT_PDF_DIR
from ..gallery import DEFAULT_GALLERY_DIR, load_annotations, save_annotations
from ..gallery_scan import GalleryIndex, load_index
from ..games_cache import DEFAULT_CACHE_PATH, load_cache, save_cache
from ..games_census import BUCKETS, census_book, census_total
from ..games_db import (
    DEFAULT_DATABASE_DIR,
    DiagramMatch,
    PositionHit,
    PositionIndex,
    database_paths,
    match_entries,
    match_positions,
    pair_from_caption,
    scan_by_players,
    scan_by_positions,
)
from ..games_index import DEFAULT_INDEX_PATH, build_index
from ..logging_setup import configure_logging, default_log_file
from ..ui.gallery_model import GalleryModel
from . import cli_errors

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
    parser.add_argument(
        "--database",
        type=Path,
        action="append",
        default=[],
        help=f"um .pgn. Repetível. Padrão: TODOS os .pgn de {DEFAULT_DATABASE_DIR}",
    )
    parser.add_argument("--gallery-dir", type=Path, default=DEFAULT_GALLERY_DIR)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--workers", type=int, default=None, help="processos na busca por posição. 1 = sem paralelismo.")
    parser.add_argument(
        "--max-games",
        type=int,
        default=5,
        help="acima disto a posição não identifica partida, e nada é preenchido (padrão: 5).",
    )
    parser.add_argument(
        "--save-matches",
        type=Path,
        default=None,
        help="grava os casamentos num JSON. 104 min de varredura viram um arquivo reaplicável.",
    )
    parser.add_argument(
        "--from-matches",
        type=Path,
        default=None,
        help="lê casamentos de um JSON em vez de varrer a base. Não abre o .pgn.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help=f"cache de posições já perguntadas à base (padrão: {DEFAULT_CACHE_PATH.name}).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignora o cache e pergunta tudo de novo. Para conferir o próprio cache.",
    )
    parser.add_argument(
        "--census",
        action="store_true",
        help="conta o que a base identificou e por qual regra. Não abre o .pgn e não grava.",
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="constrói o índice por nome (~11 min, ~428 MB) e sai. Torna a busca por nome interativa.",
    )
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH, help="onde fica o índice por nome.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _matches_to_json(matches_by_book: dict[Path, list[DiagramMatch]]) -> dict[str, Any]:
    """Versão 2: as candidatas viajam junto (S-83).

    A v1 gravava só a partida vencedora, e por isso refazer a escolha custava a varredura
    inteira. Quem lê continua aceitando a v1 -- é o artefato dos 104 minutos de 2026-08-13.
    """
    return {
        "version": 2,
        "books": {
            livro.name: [
                {
                    "page_index": casamento.page_index,
                    "diagram_index": casamento.diagram_index,
                    "move_number": casamento.move_number,
                    "side_to_move": casamento.side_to_move,
                    "headers": casamento.headers,
                    "games_matched": casamento.games_matched,
                    "game_label": casamento.game_label,
                    "candidates": [candidata.to_dict() for candidata in casamento.candidates],
                }
                for casamento in casamentos
            ]
            for livro, casamentos in matches_by_book.items()
        },
    }


def _matches_from_json(path: Path, books: Sequence[Path]) -> dict[Path, list[DiagramMatch]]:
    dados = json.loads(path.read_text(encoding="utf-8"))
    por_nome = dados.get("books") or {}
    saida: dict[Path, list[DiagramMatch]] = {}
    for livro in books:
        saida[livro] = [
            DiagramMatch(
                page_index=int(item["page_index"]),
                diagram_index=int(item["diagram_index"]),
                move_number=int(item["move_number"]),
                side_to_move=str(item["side_to_move"]),
                headers=dict(item.get("headers") or {}),
                games_matched=int(item.get("games_matched", 1)),
                game_label=str(item.get("game_label", "")),
                # Ausente na v1, e vazio é a resposta honesta: aquele artefato não guardou as
                # candidatas, e inventar uma lista de um elemento diria "só existe esta".
                candidates=tuple(PositionHit.from_dict(c) for c in (item.get("candidates") or [])),
            )
            for item in (por_nome.get(livro.name) or [])
        ]
    return saida


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


def _bases(args: argparse.Namespace) -> list[Path]:
    """As bases desta execução: as pedidas com `--database`, ou **todas** as da pasta (S-93).

    Imprime a lista porque o número de partidas consultadas passou a depender de quantos
    arquivos existem na pasta -- e um relatório que diga "581 casamentos" sem dizer sobre
    quantas bases não é reproduzível.
    """
    escolhidas = [caminho for caminho in (args.database or database_paths()) if caminho.is_file()]
    for caminho in escolhidas:
        print(f"base: {caminho} ({caminho.stat().st_size / 1e9:.1f} GB)")
    return escolhidas


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
    relatorio = modelo.apply_matches(matches, max_games=args.max_games)
    save_annotations(book, modelo.annotations, directory=args.gallery_dir)
    print(f"  gravados ................... {relatorio.fields} campo(s) em {relatorio.touched} diagrama(s)")
    print(f"  leituras confirmadas ....... {relatorio.confirmed}  ({relatorio.ambiguous} sem identificar a partida)")
    if relatorio.recovered:
        print(f"  procedência recuperada ..... {relatorio.recovered} campo(s) de execuções anteriores")
    if relatorio.respected:
        # O número que a S-110 tornou honesto, e por isso ele passa a aparecer: até aqui,
        # metade dos diagramas com escolha humana -- os que **concordavam** com o desempate --
        # eram regravados como `date` em vez de contados aqui. Um número alto nesta linha diz
        # que a varredura passou por cima de um livro já revisado à mão, e não desfez nada.
        print(f"  escolha humana respeitada .. {relatorio.respected} diagrama(s), procedência intacta")


def _positions_index(bases: list[Path], alvos: set[str], args: argparse.Namespace) -> PositionIndex:
    """As posições respondidas: as do cache mais as que faltavam (S-84).

    **O cache é consultado antes de a base ser aberta**, e é o que faz a segunda execução
    custar segundos. O que vai à varredura é só o que ninguém perguntou ainda -- e "perguntou"
    inclui as posições que a base não conhece, senão elas voltariam ao alvo para sempre.
    """
    if args.no_cache:
        indice = scan_by_positions(bases, alvos, workers=args.workers, progress=_chunk_progress)
        print(f"partidas lidas: {indice.games_read}  (--no-cache: o cache não foi lido nem gravado)")
        return indice

    cache = load_cache(args.cache, database=bases)
    faltando = cache.missing(alvos)
    print(f"cache: {len(cache)} posição(ões) já perguntada(s), {cache.answered_of(alvos)} deste acervo com resposta")

    if faltando:
        print(f"a varrer: {len(faltando)}  (as outras {len(alvos) - len(faltando)} saem do cache)")
        parcial = scan_by_positions(bases, faltando, workers=args.workers, progress=_chunk_progress)
        print(f"partidas lidas: {parcial.games_read}")
        cache.update(parcial, faltando)
        print(f"cache gravado em {save_cache(cache, args.cache)}")
    else:
        print("a varrer: nada -- todas as posições já estavam no cache, e a base não foi aberta.")

    return cache.to_index(alvos)


def _chunk_progress(feitos: int, total: int) -> None:
    print(f"  ... pedaço {feitos} de {total}", flush=True)


def _census(indices: dict[Path, GalleryIndex], args: argparse.Namespace) -> int:
    """Conta o que a base identificou e por qual regra (S-89). Não abre a base.

    Sai antes de qualquer varredura de propósito: um instrumento que precisasse de 30 minutos
    para dizer o estado do acervo não seria consultado, e o que não se consulta não mede nada.
    """
    cache = load_cache(args.cache, database=args.database or database_paths())
    if not cache.positions:
        print(f"Cache vazio em {args.cache}. Para produzi-lo:  cvoff-games --all")
        return 2

    placares = []
    for livro, indice in indices.items():
        placares.append(
            census_book(
                livro.name,
                indice.entries,
                cache,
                load_annotations(livro, directory=args.gallery_dir),
                max_games=args.max_games,
            )
        )
    total = census_total(placares)

    faixas = [nome for nome, _ in BUCKETS]
    largura = max(len(p.book) for p in placares) if placares else 10
    print(f"\ncache: {len(cache)} posição(ões) perguntada(s), {cache.answered} com resposta\n")
    print(f"{'livro':{largura}}  {'diagr':>6} {'casou':>6}  " + " ".join(f"{f:>7}" for f in faixas))
    for placar in (*placares, total):
        linha = " ".join(f"{placar.buckets.get(f, 0):>7}" for f in faixas)
        print(f"{placar.book:{largura}}  {placar.diagrams:>6} {placar.matched:>6}  {linha}")

    print(f"\nprocedência do que foi preenchido  (de {total.matched} casamento(s))")
    for regra, rotulo in (
        ("unique", "partida única na base"),
        ("caption", "confirmada pela legenda"),
        ("date", "a mais antiga entre várias"),
        ("human", "escolhida por uma pessoa"),
        ("sem marca", "gravada antes da S-91, regra desconhecida"),
    ):
        print(f"  {rotulo:44} {total.by_rule.get(regra, 0):>6}")
    if total.inferred:
        print(
            f"  ({total.inferred} destes sem marca no arquivo: a regra foi **deduzida** do "
            "número de candidatas, ver `inferred_rule`)"
        )

    print(f"\nambíguos (2+ partidas) ..................... {total.ambiguous:>6}")
    print(f"  já escolhidos por uma pessoa ............. {total.chosen:>6}")
    print(f"  A REVISAR: preenchidos por desempate ..... {total.to_review:>6}")
    print(f"  sem resposta: só a lista da Galeria ...... {total.pending:>6}")
    return 0


@cli_errors
def main(argv: list[str] | None = None) -> int:
    mp.freeze_support()  # o bundle da S-55 congela o processo; sem isto, `spawn` o reexecuta
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    # O indice por nome nao depende de livro nenhum: ele descreve a base, e e construido uma
    # vez para o acervo inteiro. Por isso sai antes de resolver quais livros processar.
    if args.build_index:
        bases = _bases(args)
        if not bases:
            logger.error("Base de partidas não encontrada. Ponha um .pgn em %s.", DEFAULT_DATABASE_DIR)
            return 2
        # `indexadas`, e nao `partidas`: mais abaixo o mesmo nome recebe o dicionario de
        # `scan_by_players`, e uma variavel com dois tipos na mesma funcao e o tipo de
        # coincidencia que o verificador aponta e o leitor nao.
        indexadas = build_index(
            bases, args.index, progress=lambda lidas: print(f"  ... {lidas / 1e6:.1f} M partidas", flush=True)
        )
        print(f"índice: {indexadas} partidas em {args.index} ({args.index.stat().st_size / 1e6:.0f} MB)")
        return 0

    livros = _books(args)
    if not livros:
        logger.error("Nada a fazer: use --all ou --book com um livro já varrido na Galeria.")
        return 2

    indices = {livro: indice for livro in livros if (indice := _load(livro, args.gallery_dir)) is not None}
    if not indices:
        return 2

    # O censo vem antes da checagem da base: ele conta o que já foi respondido, e exigir o
    # .pgn de 10,3 GB para relatar o estado do acervo seria uma pré-condição inventada.
    if args.census:
        return _census(indices, args)

    bases = _bases(args)
    if not bases:
        logger.error("Base de partidas não encontrada. Ponha um .pgn em %s ou passe --database.", DEFAULT_DATABASE_DIR)
        return 2

    if args.from_matches is not None:
        # Reaplicar sem varrer: a varredura por posicao custa ~104 min, e nada nela depende do
        # que se vai fazer com o resultado. Separar as duas coisas e o que permite mudar o
        # `--max-games`, ou corrigir a regra de preenchimento, sem pagar a base de novo.
        print(f"casamentos lidos de {args.from_matches}")
        casamentos_por_livro = _matches_from_json(args.from_matches, list(indices))
        return _finish(indices, casamentos_por_livro, args)

    print(f"livros: {len(indices)}  |  modo: {args.mode}")

    if args.mode == MODE_POSITIONS:
        # Uma varredura para todos os livros: o custo e da passada, nao do alvo.
        alvos = {entrada.placement for indice in indices.values() for entrada in indice.entries}
        print(f"posições-alvo distintas: {len(alvos)}  (a varredura é uma só para todos os livros)")
        indice_posicoes = _positions_index(bases, alvos, args)
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
        partidas = scan_by_players(bases, pares)
        print(f"pares com partida na base: {len(partidas)}")
        casamentos_por_livro = {
            livro: match_entries(indice.entries, partidas) for livro, indice in indices.items()
        }

    return _finish(indices, casamentos_por_livro, args)


def _finish(
    indices: dict[Path, GalleryIndex],
    matches_by_book: dict[Path, list[DiagramMatch]],
    args: argparse.Namespace,
) -> int:
    """Relata, grava se pedido, e guarda os casamentos se pedido."""
    if args.save_matches is not None:
        args.save_matches.parent.mkdir(parents=True, exist_ok=True)
        args.save_matches.write_text(
            json.dumps(_matches_to_json(matches_by_book), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"casamentos gravados em {args.save_matches}")

    total_casados = total_identificaveis = 0
    for livro, indice in indices.items():
        casamentos = matches_by_book.get(livro, [])
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
