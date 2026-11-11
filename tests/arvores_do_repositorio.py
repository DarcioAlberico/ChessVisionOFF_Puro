"""As árvores de trabalho deste repositório, e qual delas é o checkout principal (S-299, S-805).

**Uma guarda ancorada em `RAIZ` olha a árvore em que a suíte roda**, e num `git worktree` essa árvore
é `.claude/worktrees/algum-nome`: sem `data/`, sem `PDF/`, sem os `.pt`. É lá que o trabalho
acontece -- remedir campo a partir de um worktree é o procedimento --, e é lá que a guarda ficava
vácua: a de caminho publicado da S-299 passava em verde sobre o arquivo do checkout principal, a de
dados da S-415 vigiava um `data/` que não tinha cache, e os números vivos da S-135 pulavam.

As duas perguntas moram aqui porque três lugares as faziam: `tests/test_docs.py`, o `conftest` e
quem mais vier. A resposta vem do `git worktree list --porcelain`, que lista o principal primeiro.
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


@functools.lru_cache(maxsize=1)
def _arvores() -> tuple[Path, ...]:
    """As árvores que o git conhece, o checkout principal primeiro; vazio sem git utilizável."""
    try:
        resultado = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:  # pragma: no cover - maquina sem git no PATH
        return ()
    if resultado.returncode != 0:
        return ()
    return tuple(
        Path(linha[len("worktree ") :].strip())
        for linha in resultado.stdout.splitlines()
        if linha.startswith("worktree ") and linha[len("worktree ") :].strip()
    )


def raizes_do_repositorio() -> tuple[str, ...]:
    """Toda árvore de trabalho deste repositório, normalizada, e não só aquela em que a suíte roda.

    Devolve pelo menos `RAIZ`: sem git, ou com um git que recusa, a guarda volta a ser o que era,
    e não deixa de existir.
    """
    return tuple(sorted({normalizada(raiz) for raiz in (RAIZ, *_arvores())}))


def checkout_principal() -> Path:
    """O checkout principal, onde moram `data/`, `PDF/`, `pgn_database/` e os `.pt` de quem usa.

    É a própria `RAIZ` fora de um worktree, e também sem git utilizável -- a âncora volta a ser a
    de antes, e não some.
    """
    arvores = _arvores()
    return arvores[0] if arvores else RAIZ


def normalizada(caminho: Path) -> str:
    """A forma em que os caminhos são comparados: barra para frente, sem barra final, minúscula."""
    return str(caminho).replace("\\", "/").rstrip("/").lower()
