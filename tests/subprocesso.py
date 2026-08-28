"""Rodar Python de fora do processo do pytest, de um jeito só (S-419).

**Quatro testes lançavam subprocesso, e cada um resolvia o import do pacote de um jeito.** Um não
resolvia nada e dependia da instalação editável; outro fazia `sys.path.insert(0, 'src')` e
dependia do diretório de trabalho; um terceiro punha `PYTHONPATH`; o quarto escrevia o caminho
dentro do roteiro gerado. Três funcionam neste checkout e **nenhum** dos três funciona nas mesmas
condições -- num `git worktree`, com o `.pth` apontando para o checkout principal, o primeiro
importa o pacote **do outro lugar** e mede outro código.

`PYTHONPATH` é a resposta certa para todos: ela não depende do diretório de trabalho, não depende
de instalação, e é a mesma coisa que o `pythonpath = ["src"]` do `pyproject.toml` faz dentro do
pytest -- então o filho vê exatamente o que o pai vê.

Quem **quer** o contrário -- `tests/test_environment.py`, que mede se a instalação funciona sem
`PYTHONPATH` nenhum -- continua montando o ambiente dele à mão, e a razão está escrita lá.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"


def ambiente_com_o_pacote() -> dict[str, str]:
    """O `os.environ` com `src/` na frente do `PYTHONPATH`, preservando o que já havia."""
    anterior = os.environ.get("PYTHONPATH", "")
    caminho = str(SRC) + (os.pathsep + anterior if anterior else "")
    return {**os.environ, "PYTHONPATH": caminho}


def rodar_python(
    codigo: str,
    *,
    check: bool = True,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    """`python -c codigo` num processo novo, enxergando este checkout.

    `check=True` por padrão: um filho que morreu é um teste que não mediu nada, e deixar isso
    passar como saída vazia é o modo silencioso de falhar que esta suíte já pagou uma vez.
    """
    return subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
        env=ambiente_com_o_pacote(),
    )


def rodar_roteiro(
    caminho: Path,
    *,
    check: bool = False,
    timeout: float = 300.0,
) -> subprocess.CompletedProcess[str]:
    """O mesmo para um arquivo `.py` -- o caso do `multiprocessing`, que precisa de `__main__`."""
    return subprocess.run(
        [sys.executable, str(caminho)],
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
        env=ambiente_com_o_pacote(),
    )
