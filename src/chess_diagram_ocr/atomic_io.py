"""Escrita de arquivo que não deixa arquivo pela metade (S-25).

Três arquivos do projeto são reescritos inteiros a cada mudança e lidos na abertura
seguinte: o estado da app (`data/app_tkinter_state.json`), a fila de revisão
(`data/review_queue.json`) e o `labels.csv` quando a UI de dataset regrava um rótulo.
Nos três, `path.write_text(...)` trunca o arquivo antes de escrever o conteúdo novo --
uma interrupção nesse intervalo deixa 0 byte no lugar do que existia.

O reparo é o mesmo padrão nos três: escrever num temporário **no mesmo diretório** e
renomear por cima. `os.replace` é atômico dentro do mesmo volume, no Windows inclusive; o
temporário precisa ser vizinho porque renomear entre volumes não é.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def atomic_write_text(path: Path, payload: str, *, encoding: str = "utf-8") -> None:
    """Grava `payload` em `path` sem passar por um estado de arquivo truncado."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding=encoding,
        newline="\n",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            # Sem o fsync, o rename pode chegar ao disco antes do conteudo: o arquivo
            # existe, tem o nome certo e esta vazio -- exatamente o que se quis evitar.
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=indent) + "\n")


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Versão binária, para o `labels.csv` que o pandas escreve via buffer."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
