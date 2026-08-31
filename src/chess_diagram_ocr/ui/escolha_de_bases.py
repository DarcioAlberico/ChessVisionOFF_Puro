"""Contra quais `.pgn` perguntar, onde mora o cache disso, e o que se perde ao trocar (S-503).

`describe_size`, `store_path_for` e `cache_note`. As três eram puras dentro de
`ui/database_choice.py` -- nenhuma toca widget --, e a do meio é a que mais importa: **cada
conjunto de bases tem o seu arquivo de cache**, porque a contagem de partidas de uma posição muda
quando um `.pgn` entra, e é a contagem que autoriza preencher um header (S-74). Sem isso,
experimentar uma base sozinha apagaria as respostas do acervo inteiro -- ~56 min medidos de cada
lado, por um clique reversível.

**Por que isso pede endereço próprio.** `ui/database_choice.py` importa `tkinter` na primeira
linha do corpo (`DatabaseDialog` herda de `tk.Toplevel`), e o segundo frontend precisa das três e
de widget nenhum. Uma segunda `store_path_for` com outro esquema de nome faria as duas janelas
guardarem o mesmo trabalho em arquivos diferentes -- e cada uma refazendo a meia hora que a outra
já fez.

`ui/database_choice.py` reexporta tudo o que está aqui.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..games_cache import (
    DEFAULT_STORE_PATH,
    database_fingerprint,
    same_database,
    stored_summary,
)
from ..games_db import database_paths

__all__ = ["cache_note", "describe_size", "store_path_for"]

def describe_size(caminho: Path) -> str:
    """O tamanho do arquivo como quem vai esperar por ele o lê: `8,6 GB`, `62 MB`."""
    try:
        bytes_ = caminho.stat().st_size
    except OSError:
        return "ausente"
    if bytes_ >= 1_000_000_000:
        return f"{bytes_ / 1e9:.1f} GB".replace(".", ",")
    if bytes_ >= 1_000_000:
        return f"{bytes_ / 1e6:.0f} MB"
    return f"{bytes_ / 1e3:.0f} kB"


def _mesmo_conjunto(um: Sequence[Path], outro: Sequence[Path]) -> bool:
    return sorted(caminho.name.lower() for caminho in um) == sorted(caminho.name.lower() for caminho in outro)


def store_path_for(
    bases: Sequence[Path],
    *,
    default_bases: Sequence[Path] | None = None,
    default_path: Path = DEFAULT_STORE_PATH,
) -> Path:
    """Onde mora o cache **deste** conjunto de bases.

    A pasta inteira continua no arquivo de sempre -- é o conjunto que o `cvoff-games` usa, e
    mudar o caminho dele deixaria a linha de comando e a janela com dois caches que não se
    enxergam. Qualquer outro conjunto ganha um arquivo vizinho, nomeado pelos arquivos que o
    compõem.

    **O nome sai dos nomes, e não do fingerprint.** Tamanho entra na guarda de dentro do cache
    (é ela que descarta quando um `.pgn` cresce); se entrasse também no caminho, um arquivo que
    crescesse viraria um cache novo e abandonaria o anterior no disco sem ninguém para apagá-lo.
    """
    padrao = list(default_bases) if default_bases is not None else database_paths()
    alvo = Path(default_path)
    if not bases or _mesmo_conjunto(bases, padrao):
        return alvo
    # Um nome legível vale mais que um hash: quem abrir `data/` precisa saber o que apagar.
    marca = "-".join(sorted(Path(base).stem[:12].replace(" ", "_") for base in bases))
    return alvo.with_name(f"{alvo.stem}__{marca[:60]}{alvo.suffix}")


def cache_note(bases: Sequence[Path], *, store_path: Path | None = None) -> str:
    """O que o cache deste conjunto tem hoje, e o que a próxima busca fará com ele.

    Lê o cache **em modo leitura** (`stored_summary`): abrir pela porta normal já descartaria o
    que esta frase existe para avisar que vai ser descartado.
    """
    if not bases:
        return "Nenhuma base marcada: as buscas não têm onde procurar."
    caminho = store_path if store_path is not None else store_path_for(bases)
    marca, linhas = stored_summary(caminho)
    if not linhas:
        return "Sem respostas guardadas para este conjunto: a primeira busca por posição lê os arquivos inteiros."
    if same_database(marca, database_fingerprint(bases)):
        return f"{linhas} posição(ões) já respondidas continuam valendo — a busca só pergunta o que faltar."
    return (
        f"As {linhas} posição(ões) guardadas foram respondidas por outro conjunto de arquivos e "
        "serão descartadas na próxima busca por posição: a contagem de uma base não vale para outra."
    )


