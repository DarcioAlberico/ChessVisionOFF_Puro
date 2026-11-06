"""O contrato do segundo leitor: quem lê as linhas que o glifo achou (S-720).

**`None` é "não leu", `""` é "leu vazio"**, e a fusão depende da diferença: a linha que o leitor não leu
fica com o glifo, inteira, e a folha ganha aviso; a linha que ele leu vazia passa pela regra de quem tem
par. **Ausência de motor não levanta no caminho da janela**: a aba abre e lê com o glifo.

O RapidOCR não está aqui: o `onnxruntime` fica fora do bundle e o modelo do wheel não lê acento. Ele
continua só na régua.

**O cache é do leitor, e nasce desligado** (S-725): `text/cache_texto.py` diz por quê.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from . import cache_texto, tesseract

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Leitura:
    """O que o leitor devolve para um lote de recortes. `falha` é a frase do aviso, quando não leu."""

    linhas: tuple[tesseract.LinhaDoTesseract | None, ...]
    falha: str = ""
    aviso: str = ""
    """Leu, e algo em volta não deu: o cache que não gravou (S-725). A leitura vale."""


class LeitorDeLinha(Protocol):
    """Quem lê recortes de linha, e a folha inteira quando a segmentação do glifo se perde."""

    def ler_linhas(self, recortes: Sequence[np.ndarray], *, lingua: str, dpi: int) -> Leitura: ...

    def ler_folha(self, cinza: np.ndarray, *, lingua: str, dpi: int) -> tuple[list[tesseract.Palavra], str]: ...


class LeitorTesseract:
    """O `LeitorDeLinha` de produção. Nunca levanta: toda falha vira `Leitura.falha`."""

    def __init__(
        self, motor: tesseract.Motor | None = None, *, cache: cache_texto.CacheDeLeitura | None = None, modelo: str = ""
    ) -> None:
        self._motor = motor
        self._cache = cache
        self._modelo = modelo

    def _achado(self) -> tesseract.Motor:
        return tesseract.achar_motor() if self._motor is None else self._motor

    def ler_linhas(self, recortes: Sequence[np.ndarray], *, lingua: str, dpi: int, sem_dicionario: bool = False) -> Leitura:
        motor = self._achado()
        if not motor.disponivel:
            return Leitura((None,) * len(recortes), motor.motivo)
        chave = None
        if self._cache is not None:
            chave = cache_texto.chave_de(
                recortes,
                motor=motor,
                lingua=lingua,
                dpi=dpi,
                opcoes=("load_system_dawg=0",) if sem_dicionario else (),
                modelo=self._modelo,
            )
            guardadas = self._cache.ler(chave)
            if guardadas is not None and len(guardadas) == len(recortes):
                return Leitura(tuple(guardadas))
        try:
            linhas = tesseract.ler_linhas(recortes, lingua=lingua, dpi=dpi, motor=motor, sem_dicionario=sem_dicionario)
        except tesseract.FalhaDoTesseract as exc:
            logger.warning("Leitura por linha falhou: %s", exc)
            return Leitura((None,) * len(recortes), str(exc))
        aviso = self._cache.gravar(chave, linhas) if self._cache is not None and chave is not None else ""
        return Leitura(tuple(linhas), aviso=aviso)

    def ler_folha(self, cinza: np.ndarray, *, lingua: str, dpi: int) -> tuple[list[tesseract.Palavra], str]:
        motor = self._achado()
        if not motor.disponivel:
            return ([], motor.motivo)
        try:
            return (tesseract.ler_folha(cinza, lingua=lingua, dpi=dpi, motor=motor), "")
        except tesseract.FalhaDoTesseract as exc:
            logger.warning("Leitura da folha falhou: %s", exc)
            return ([], str(exc))


def leitor_padrao(*, cache: cache_texto.CacheDeLeitura | None = None) -> LeitorDeLinha:
    """Sem cache, se ninguém pedir: é o que a régua e os CLIs recebem. Quem pede é a janela."""
    return LeitorTesseract(cache=cache)


__all__ = ["LeitorDeLinha", "LeitorTesseract", "Leitura", "leitor_padrao"]
