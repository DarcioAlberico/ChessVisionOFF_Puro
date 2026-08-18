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


def write_image(path: Path, image_bgr: Any) -> Path:
    """Grava a imagem e **levanta** quando o OpenCV recusa. Devolve o caminho (S-111).

    `cv2.imwrite` não levanta: devolve `False`. Disco cheio, pasta em rede fora do ar,
    antivírus segurando o arquivo -- em todos, quem chamava seguia adiante e gravava a linha
    no `labels.csv` apontando para um PNG que não existe. O prejuízo é o trabalho humano
    daquela correção, e ele aparece semanas depois no relatório da auditoria, na linha
    "rótulos cujo PNG sumiu -- descartados em silêncio no treino".

    A ordem de quem chama já é favorável -- a imagem vem antes do CSV --, então levantar aqui
    deixa o CSV intacto e o erro chega a quem está na frente da tela.

    **O OpenCV não abre o arquivo, nós abrimos.** `cv2.imwrite` recebe o caminho como
    `std::string` e o entrega ao `fopen` estreito do CRT, que o converte pela code page ANSI
    do processo -- cp1252 nesta máquina. Um livro russo em
    `review_cache/_Болеславский_И_Избранные_партии/` falhava aí: o `mkdir` do Python usa a API
    wide e criava a pasta, o `imwrite` devolvia `False` e a mensagem acima mandava conferir
    espaço em disco e permissão, que estavam ambos em ordem. Codificar em memória e escrever
    os bytes pelo Python tira o CRT do caminho -- `net_correction.py` já fazia assim.

    Não é escrita atômica, e é de propósito: o nome do PNG é único por timestamp
    (`dataset.py`) ou determinístico e reescrito por inteiro (`review_queue.py`), então não há
    versão anterior a proteger. O que faltava era conferir a resposta.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import cv2  # local: o `atomic_io` é importado por módulos que não dependem de OpenCV

    try:
        ok, buffer = cv2.imencode(path.suffix, image_bgr)
    except cv2.error as exc:  # extensão que nenhum codec reconhece
        raise OSError(f"O OpenCV não sabe codificar '{path.suffix}' para gravar {path}.") from exc
    if not ok:
        raise OSError(f"O OpenCV não conseguiu codificar a imagem de {path}.")

    try:
        path.write_bytes(buffer.tobytes())
    except OSError as exc:
        raise OSError(
            f"Não foi possível gravar {path}: {exc}. "
            "Verifique espaço em disco e permissão de escrita."
        ) from exc
    return path


def read_image(path: Path | str) -> Any | None:
    """Lê uma imagem em BGR. `None` quando ela não existe ou não decodifica.

    Contrapartida de `write_image`, e pelo mesmo motivo: `cv2.imread` sofre da mesma conversão
    ANSI do caminho, então um PNG sob nome cirílico voltava `None` mesmo com `path.exists()`
    dizendo `True` -- "a imagem não existe mais" numa imagem que estava lá. Ler os bytes pelo
    Python e decodificar em memória resolve as duas pontas.

    Devolve `None` em vez de levantar para que os sete pontos de chamada mantenham o
    tratamento que já tinham para o `None` do `imread`.
    """
    import cv2
    import numpy as np

    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if not data:
        return None
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


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
