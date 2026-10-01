"""O que o trilho de páginas diz de cada página, sem toolkit (OCR_UI_ROADMAP passo 17).

**A regra é da suíte; aqui mora a tradução para tinta.** Quem sabe se uma página é duvidosa,
revisada ou ainda não lida é `caissa.ui.trilho` (a partir do relatório da importação e das
decisões do revisor). Este módulo recebe esse estado -- ou o que o tronco sabe sozinho, sem a
suíte: quais páginas têm diagramas detectados e amostras gravadas -- e decide **como se lê**: o
rótulo curto de cada miniatura, o papel de cor da marca e a frase da dica. É a mesma fronteira
de `ui/page_overlay.py` para as caixas: decisão testável sem janela, pintura em `qt/trilho.py`.

**Três marcas, e só três** (SPEC OCR_UI, superfície *Trilho do livro*): diagramas, texto,
revisado. A quarta -- *duvidosa* -- não é uma marca: é o que decide a **cor** da linha, porque é
o que decide para onde a pessoa vai.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chess_diagram_ocr.ui import tokens

__all__ = [
    "MarcaDaPagina",
    "dica_da_pagina",
    "papel_da_pagina",
    "anterior_duvidosa",
    "primeira_duvidosa",
    "proxima_duvidosa",
    "rotulo_da_pagina",
]

GLIFO_DIAGRAMA = "▣"  # ▣
GLIFO_TEXTO = "¶"  # ¶
GLIFO_REVISADO = "✓"  # ✓
GLIFO_DUVIDA = "⚠"  # ⚠
"""Os glifos das marcas. Glifo **e** cor, e não só cor: é a regra da S-158 (sem depender de matiz)."""


@dataclass(frozen=True)
class MarcaDaPagina:
    """O estado de uma página como o trilho o desenha.

    Os campos são os de `caissa.ui.trilho.EstadoDaPagina`, de propósito: `de` copia por nome, e
    a suíte pode mandar o objeto dela sem que o tronco a importe.
    """

    pagina: int
    montada: bool = False
    diagramas: int = 0
    diagramas_lidos: int = 0
    texto: bool = False
    duvidosos: int = 0
    revisada: bool = False
    hesitantes: int = 0
    """Dos lidos, quantos hesitam (casa < 0,90) e ninguém corrigiu (C8)."""

    @property
    def duvidosa(self) -> bool:
        return self.duvidosos > 0

    @classmethod
    def de(cls, estado: Any) -> MarcaDaPagina:
        """Uma marca a partir de qualquer objeto com os mesmos nomes de campo."""
        return cls(
            pagina=int(estado.pagina),
            montada=bool(getattr(estado, "montada", True)),
            diagramas=int(getattr(estado, "diagramas", 0)),
            diagramas_lidos=int(getattr(estado, "diagramas_lidos", 0)),
            texto=bool(getattr(estado, "texto", False)),
            duvidosos=int(getattr(estado, "duvidosos", 0)),
            revisada=bool(getattr(estado, "revisada", False)),
            hesitantes=int(getattr(estado, "hesitantes", 0) or 0),
        )


def rotulo_da_pagina(marca: MarcaDaPagina) -> str:
    """O texto curto sob a miniatura: o número e, quando há, as marcas.

    `p. 12` sozinho quando a página não foi montada -- não se afirma nada sobre o que não se leu.
    """
    partes = [f"{marca.pagina + 1}"]
    if not marca.montada:
        return partes[0]
    if marca.diagramas:
        partes.append(f"{GLIFO_DIAGRAMA} {marca.diagramas_lidos}/{marca.diagramas}")
    if marca.texto:
        partes.append(GLIFO_TEXTO)
    if marca.revisada:
        partes.append(GLIFO_REVISADO)
    if marca.duvidosa:
        partes.append(f"{GLIFO_DUVIDA} {marca.duvidosos}")
    return "  ".join(partes)


def papel_da_pagina(marca: MarcaDaPagina) -> str:
    """O papel de cor do rótulo: dúvida em `ATENCAO`, revisada em `PRONTO_TEXTO`, não lida em
    `TEXTO_MORTO`, o resto no texto padrão. Só papéis de **texto**: o rótulo é texto sobre a
    superfície da lista, e o portão de contraste mede exatamente esses pares."""
    if not marca.montada:
        return tokens.TEXTO_MORTO
    if marca.duvidosa:
        return tokens.ATENCAO
    if marca.revisada:
        return tokens.PRONTO_TEXTO
    return tokens.TEXTO_PADRAO


def dica_da_pagina(marca: MarcaDaPagina) -> str:
    """A frase inteira, para a dica e para o leitor de tela."""
    if not marca.montada:
        return f"Página {marca.pagina + 1}: ainda não lida pela importação."
    partes = [f"Página {marca.pagina + 1}"]
    if marca.diagramas:
        partes.append(f"{marca.diagramas_lidos} de {marca.diagramas} diagrama(s) com posição")
    else:
        partes.append("sem diagramas")
    partes.append("com texto" if marca.texto else "sem texto")
    if marca.duvidosa:
        partes.append(f"{marca.duvidosos} item(ns) para rever")
    elif marca.revisada:
        partes.append("revisada")
    return ": ".join([partes[0], ", ".join(partes[1:])]) + "."


def primeira_duvidosa(marcas: list[MarcaDaPagina]) -> int | None:
    for marca in marcas:
        if marca.duvidosa:
            return marca.pagina
    return None


def proxima_duvidosa(marcas: list[MarcaDaPagina], atual: int) -> int | None:
    """A primeira duvidosa **depois** de `atual` (passo C8); `None` quando não há mais."""
    for marca in marcas:
        if marca.pagina > atual and marca.duvidosa:
            return marca.pagina
    return None


def anterior_duvidosa(marcas: list[MarcaDaPagina], atual: int) -> int | None:
    """A última duvidosa **antes** de `atual`; `None` quando não há."""
    alvo = None
    for marca in marcas:
        if marca.pagina >= atual:
            break
        if marca.duvidosa:
            alvo = marca.pagina
    return alvo
