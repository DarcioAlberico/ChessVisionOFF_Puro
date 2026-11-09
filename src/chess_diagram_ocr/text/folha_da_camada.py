"""A folha extraída uma vez por leitura (S-851).

**Uma `ler_pagina(motor="camada")` fazia oito `get_text("dict")` na folha lida**, e com o glifo mais um:
`page_text_lines` e `page_margin_lines`, `spans_com` e `linhas_com` do negrito e do itálico, `quadros`,
`running_page_number` e `camada_tipografica` -- cada uma pedia a extração inteira ao MuPDF e jogava o resto
fora. `running_page_number` lê ainda as quatro vizinhas, e numa varredura cada folha era reextraída umas
quatro vezes como vizinha de outra.

`FolhaDaCamada` é a folha com a extração guardada: o mesmo `get_text` com os mesmos argumentos devolve o
mesmo valor, extraído uma vez. `LivroDaCamada` é o documento que entrega essas folhas, e as extrações
ficam guardadas **por documento** entre uma leitura e a seguinte, para que a vizinha lida pela folha 20
não seja extraída de novo pela 21.

**Por que um invólucro, e não funções puras sobre um valor.** Quem extrai mora em `pdf_text`, `camada`,
`camada_prosa` e `quadros`, e todos recebem a página do PyMuPDF; reescrevê-los para receber o dicionário
mexeria no caminho de medição de campo (`pdf_text` está no fecho da S-218) para devolver o mesmo texto.
O invólucro entrega a eles o que já pediam -- uma página -- e a extração deixa de se repetir sem que
nenhum deles saiba.

**O que se guarda entre leituras é só o extraído**, e nunca a página: o documento de uma leitura fecha no
fim dela, e uma página guardada de documento fechado levanta no primeiro `rect`. O valor guardado é
compartilhado, então quem o recebe não o altera -- todos os leitores de hoje só o percorrem.

**Sem identidade no disco, sem memória entre leituras** (`camada._identidade`): o documento aberto de
`bytes` não tem nome, e uma chave sem ele devolveria a extração de outro livro. Dentro da leitura a
memória vale do mesmo jeito.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Hashable
from typing import TYPE_CHECKING

from . import camada as _camada

if TYPE_CHECKING:
    import fitz

FOLHAS_GUARDADAS = 16
"""Quantas folhas guardam a extração entre leituras, somando todos os documentos.

A leitura de uma folha consulta ela e as quatro vizinhas (`pdf_text._NEIGHBOUR_DELTAS`); dezesseis
cobrem a janela de uma varredura com folga, e a amostra de `documento_registra`, que passa uma vez por
documento, não expulsa a janela inteira."""

Extracoes = dict[Hashable, object]
"""O que uma folha já extraiu: `(método, argumentos)` -> o valor que o PyMuPDF devolveu."""

_GUARDADAS: OrderedDict[tuple[str, float, int], Extracoes] = OrderedDict()
_TRAVA = threading.Lock()


def limpar() -> None:
    """Esquece o que foi guardado entre leituras. Para os testes."""
    with _TRAVA:
        _GUARDADAS.clear()


def _extracoes_guardadas(identidade: tuple[str, float] | None, indice: int) -> Extracoes:
    """As extrações da folha `indice` deste documento, as mesmas da leitura anterior quando há identidade."""
    if identidade is None:
        return {}
    chave = (identidade[0], identidade[1], indice)
    with _TRAVA:
        extracoes = _GUARDADAS.get(chave)
        if extracoes is None:
            extracoes = _GUARDADAS[chave] = {}
        _GUARDADAS.move_to_end(chave)
        while len(_GUARDADAS) > FOLHAS_GUARDADAS:
            _GUARDADAS.popitem(last=False)
        return extracoes


class FolhaDaCamada:
    """Uma página do PyMuPDF cujo `get_text` e `get_texttrace` extraem uma vez. O resto é a página."""

    def __init__(self, pagina: fitz.Page, extracoes: Extracoes | None = None) -> None:
        self._pagina = pagina
        self._extracoes: Extracoes = {} if extracoes is None else extracoes

    def _uma_vez(self, metodo: str, args: tuple[object, ...], kwargs: dict[str, object]) -> object:
        chave = (metodo, args, tuple(sorted(kwargs.items())))
        try:
            hash(chave)
        except TypeError:  # um `clip` em `Rect` não tem hash: extrai, sem guardar
            return getattr(self._pagina, metodo)(*args, **kwargs)
        if chave not in self._extracoes:
            self._extracoes[chave] = getattr(self._pagina, metodo)(*args, **kwargs)
        return self._extracoes[chave]

    def get_text(self, *args: object, **kwargs: object) -> object:
        return self._uma_vez("get_text", args, kwargs)

    def get_texttrace(self, *args: object, **kwargs: object) -> object:
        return self._uma_vez("get_texttrace", args, kwargs)

    @property
    def rect(self) -> fitz.Rect:
        return self._pagina.rect

    def __getattr__(self, nome: str) -> object:
        return getattr(self._pagina, nome)


class LivroDaCamada:
    """O documento do PyMuPDF que entrega `FolhaDaCamada`, com a extração guardada por documento."""

    def __init__(self, doc: fitz.Document) -> None:
        self._doc = doc
        self._identidade = _camada._identidade(doc)
        self._folhas: dict[int, FolhaDaCamada] = {}

    def __getitem__(self, indice: int) -> FolhaDaCamada:
        indice = int(indice)
        if indice < 0:
            indice += len(self)
        folha = self._folhas.get(indice)
        if folha is None:
            folha = self._folhas[indice] = FolhaDaCamada(self._doc[indice], _extracoes_guardadas(self._identidade, indice))
        return folha

    def __len__(self) -> int:
        return len(self._doc)

    def __getattr__(self, nome: str) -> object:
        return getattr(self._doc, nome)


__all__ = ["FOLHAS_GUARDADAS", "FolhaDaCamada", "LivroDaCamada", "limpar"]
