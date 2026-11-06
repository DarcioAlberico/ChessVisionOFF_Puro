"""O contrato do segundo leitor: quem lê as linhas que o glifo achou (S-720).

**`None` é "não leu", `""` é "leu vazio"**, e a fusão depende da diferença: a linha que o leitor não leu
fica com o glifo, inteira, e a folha ganha aviso; a linha que ele leu vazia passa pela regra de quem tem
par. **Ausência de motor não levanta no caminho da janela**: a aba abre e lê com o glifo.

O RapidOCR não está aqui: o `onnxruntime` fica fora do bundle e o modelo do wheel não lê acento. Ele
continua só na régua.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from . import tesseract

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Leitura:
    """O que o leitor devolve para um lote de recortes. `falha` é a frase do aviso, quando não leu."""

    linhas: tuple[tesseract.LinhaDoTesseract | None, ...]
    falha: str = ""


class LeitorDeLinha(Protocol):
    """Quem lê recortes de linha, e a folha inteira quando a segmentação do glifo se perde."""

    def ler_linhas(self, recortes: Sequence[np.ndarray], *, lingua: str, dpi: int) -> Leitura: ...

    def ler_folha(self, cinza: np.ndarray, *, lingua: str, dpi: int) -> tuple[list[tesseract.Palavra], str]: ...


class LeitorTesseract:
    """O `LeitorDeLinha` de produção. Nunca levanta: toda falha vira `Leitura.falha`."""

    def __init__(self, motor: tesseract.Motor | None = None) -> None:
        self._motor = motor

    def _achado(self) -> tesseract.Motor:
        return tesseract.achar_motor() if self._motor is None else self._motor

    def ler_linhas(self, recortes: Sequence[np.ndarray], *, lingua: str, dpi: int, sem_dicionario: bool = False) -> Leitura:
        motor = self._achado()
        if not motor.disponivel:
            return Leitura((None,) * len(recortes), motor.motivo)
        try:
            return Leitura(tuple(tesseract.ler_linhas(recortes, lingua=lingua, dpi=dpi, motor=motor, sem_dicionario=sem_dicionario)))
        except tesseract.FalhaDoTesseract as exc:
            logger.warning("Leitura por linha falhou: %s", exc)
            return Leitura((None,) * len(recortes), str(exc))

    def ler_folha(self, cinza: np.ndarray, *, lingua: str, dpi: int) -> tuple[list[tesseract.Palavra], str]:
        motor = self._achado()
        if not motor.disponivel:
            return ([], motor.motivo)
        try:
            return (tesseract.ler_folha(cinza, lingua=lingua, dpi=dpi, motor=motor), "")
        except tesseract.FalhaDoTesseract as exc:
            logger.warning("Leitura da folha falhou: %s", exc)
            return ([], str(exc))


def leitor_padrao() -> LeitorDeLinha:
    return LeitorTesseract()


__all__ = ["LeitorDeLinha", "LeitorTesseract", "Leitura", "leitor_padrao"]
