"""A opção `--ocr`, compartilhada pelos comandos que leem PDF (S-42/S-43).

Mora num módulo próprio por um motivo concreto: `cvoff-field` e `cvoff-export` precisam da
**mesma** opção, e o critério de aceite da S-43 depende disso -- ele exige rodar o conjunto
de campo com e sem OCR e comparar. Duas cópias do argumento divergiriam no primeiro ajuste
de padrão, e a comparação passaria a medir a divergência.

`--ocr off` é o padrão, e o padrão do `data/settings.json` também é desligado. A linha de
comando vence o arquivo pela mesma razão da S-32: um script e a CI precisam poder garantir o
comportamento sem depender do que está gravado em disco.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from ..ocr import KNOWN_ENGINES
from ..settings import OcrSettings, load_settings

logger = logging.getLogger(__name__)

OFF = "off"
FROM_SETTINGS = "settings"


def add_ocr_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ocr",
        default=OFF,
        choices=(OFF, FROM_SETTINGS, *KNOWN_ENGINES),
        help=(
            "Motor de OCR para as legendas das páginas sem camada de texto (S-42). "
            f"'{OFF}' (padrão) usa só a camada de texto, que é o projeto como sempre foi; "
            f"'{FROM_SETTINGS}' obedece ao data/settings.json; um nome de motor o liga "
            "diretamente. Sem o extra instalado o comando avisa e segue sem OCR."
        ),
    )


def caption_reader_from_args(args: argparse.Namespace) -> Any:
    """O `CaptionReader` que os argumentos pedem, ou `None`.

    Import tardio do `ocr_caption` para que um comando com `--ocr off` -- que é a maioria
    das invocações -- não pague nem o import do módulo.
    """
    escolha = str(getattr(args, "ocr", OFF) or OFF)
    if escolha == OFF:
        return None

    from ..ocr_caption import caption_reader_from_settings

    settings = load_settings().ocr if escolha == FROM_SETTINGS else OcrSettings(enabled=True, engine=escolha)
    reader = caption_reader_from_settings(settings)
    if reader is None:
        # Aviso e nao erro: a varredura de um livro inteiro nao deve morrer porque um extra
        # opcional falta. Mas o silencio seria pior -- quem pediu `--ocr rapidocr` precisa
        # saber que a saida foi produzida sem ele.
        logger.warning("OCR pedido (%s) não está disponível; o comando segue só com a camada de texto.", escolha)
    else:
        logger.info("OCR de legenda ligado: %s", reader.name)
    return reader
