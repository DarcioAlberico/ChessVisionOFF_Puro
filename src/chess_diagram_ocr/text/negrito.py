"""O negrito vem da camada de texto, e nunca da imagem (S-211).

**A metade que funciona, e a metade que foi medida e recusada.** Negrito é atributo de forma, e há
dois lugares de onde tirá-lo: o nome da fonte na camada de texto do PDF, que é **metadado** e não
erra, e a espessura do traço na imagem, que é palpite. Este módulo faz só o primeiro.

## Por que a imagem ficou de fora, com número

Medido em 2026-08-24 sobre 940 palavras rotuladas pela camada, em 3 livros:

    medida                 melhor acerto    chutar "normal" sempre
    espessura do traço            82,2%              82,7%
    densidade de tinta            85,6%              82,7%

A espessura **não passa do acaso**. A densidade passa um pouco, e a acurácia engana com 17% de
positivos -- a curva de verdade é esta:

    corte    cobertura   precisão
    0,410      81,0%       46,8%
    0,448      54,0%       58,3%
    0,474      29,4%       63,2%     melhor F1 = 0,60

**Metade do que fosse marcado sairia errado.** Subir de 220 para 400 dpi não muda (86,6% contra
85,6%): o problema não é resolução, é que a densidade depende mais do limiar de binarização e do
corpo da fonte do que do peso. A régua deste projeto para aplicar em lote é 99,29% (S-213).

> **Um erro de método que vale ficar escrito.** A primeira medição normalizou a espessura pela
> **mediana da linha**, e isso apaga o sinal justamente quando a linha inteira é negrito -- que é o
> caso comum: título, lance principal. Normalizar pela linha só faria sentido se o negrito fosse
> sempre parcial dentro dela.

## A cobertura é irregular, e o desconhecido é dito

Dos 42 livros do acervo: **13 têm negrito na camada**, 16 têm camada sem nenhum negrito, e 10 não
têm camada. Por isso `negrito` é `bool | None` e não `bool`: `None` é **"não se sabe"**, e é
diferente de `False`. Um livro cuja camada não registra peso nenhum não pode declarar que nada ali
é negrito -- ele não sabe.

## A unidade é a linha, e isso é uma limitação declarada

A `PaginaLida` não tem unidade menor que a `LinhaLida`, então uma linha meio em negrito é decidida
pela **maioria** da largura dela. Onde o negrito é um lance no meio da prosa, o resultado é
grosso; onde ele é a linha inteira -- título, variante principal --, é exato.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

FONTE_NEGRITO = re.compile(r"bold|black|heavy|semib|demi", re.I)
"""O nome da fonte que denuncia peso. `Times-Bold`, `Calibri-Black`, `Helvetica-SemiBold`.

Vale junto com o bit `2**4` de `flags`, que o PyMuPDF preenche a partir do descritor da fonte --
os dois porque nenhum dos dois sozinho pega tudo: há PDF com o nome sem o bit, e vice-versa."""

BIT_DE_NEGRITO = 2**4
"""O bit de negrito em `span["flags"]` do `get_text("dict")`."""

COBERTURA_MINIMA = 0.60
"""Fração da largura da linha que precisa estar em negrito para a linha inteira contar como tal.

Maioria, e não qualquer sobreposição: uma linha de prosa com **um** lance em negrito no meio não é
uma linha em negrito, e marcá-la assim seria pior que não marcar. Ver a limitação declarada no
cabeçalho."""

PAGINAS_DE_AMOSTRA = 6
"""Quantas páginas se olham para decidir se o **documento** registra negrito.

A pergunta não é da página: uma página de prosa sem nenhum negrito num livro que o registra é um
`False` legítimo, e num livro que não o registra é um `None`. Quem separa as duas é o documento, e
por isso a amostra é dele."""


Retangulo = tuple[float, float, float, float]


def _span_e_negrito(span: dict) -> bool:
    """O nome da fonte **ou** o bit. Ver `FONTE_NEGRITO`."""
    return bool(FONTE_NEGRITO.search(str(span.get("font", "")))) or bool(
        int(span.get("flags", 0)) & BIT_DE_NEGRITO
    )


def spans_de_negrito(page: object) -> list[Retangulo]:
    """Os retângulos em negrito da página, em **pontos do PDF**. Vazio quando não há nenhum.

    Pontos e não pixels, como todo bbox da `PaginaLida`: quem converte é quem tem o DPI.
    """
    try:
        dicionario = page.get_text("dict")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - página sem camada nenhuma
        return []
    saida: list[Retangulo] = []
    for bloco in dicionario.get("blocks", []):
        for linha in bloco.get("lines", []):
            for span in linha.get("spans", []):
                if _span_e_negrito(span):
                    x0, y0, x1, y1 = span["bbox"]
                    saida.append((float(x0), float(y0), float(x1), float(y1)))
    return saida


def documento_registra_negrito(doc: object, *, amostra: int = PAGINAS_DE_AMOSTRA) -> bool:
    """Este documento registra peso de fonte em algum lugar? Ver `PAGINAS_DE_AMOSTRA`.

    **É a pergunta que separa `False` de `None`.** Uma página sem negrito num livro que o registra
    é "aqui não tem"; num livro que não o registra é "não se sabe", e as duas não podem virar a
    mesma coisa.
    """
    try:
        total = int(doc.page_count)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        return False
    if total <= 0:
        return False
    passos = max(1, total // (amostra + 1))
    for indice in range(passos, total, passos):
        try:
            if spans_de_negrito(doc[indice]):  # type: ignore[index]
                return True
        except Exception:  # pragma: no cover - página ilegível
            continue
    return False


def cobertura(bbox: Retangulo, spans: Sequence[Retangulo]) -> float:
    """Fração da **largura** da linha coberta por span de negrito. `0.0` quando não há sobreposição.

    Largura e não área porque a linha e o span têm a mesma altura por construção -- os dois vêm da
    mesma linha de texto --, e comparar áreas só acrescentaria ruído de arredondamento vertical.

    Os trechos cobertos são unidos antes de somar: dois spans que se sobrepõem não contam duas
    vezes, e sem isso uma linha poderia "cobrir" mais que 100% de si mesma.
    """
    x0, y0, x1, y1 = bbox
    largura = x1 - x0
    if largura <= 0:
        return 0.0

    partes: list[tuple[float, float]] = []
    for sx0, sy0, sx1, sy1 in spans:
        if min(y1, sy1) - max(y0, sy0) <= 0:
            continue
        a, b = max(x0, sx0), min(x1, sx1)
        if b > a:
            partes.append((a, b))
    if not partes:
        return 0.0

    partes.sort()
    total = 0.0
    atual_a, atual_b = partes[0]
    for a, b in partes[1:]:
        if a > atual_b:
            total += atual_b - atual_a
            atual_a, atual_b = a, b
        else:
            atual_b = max(atual_b, b)
    total += atual_b - atual_a
    return min(1.0, total / largura)


def marcar(
    bboxes: Sequence[Retangulo],
    spans: Sequence[Retangulo],
    *,
    registra: bool,
    minimo: float = COBERTURA_MINIMA,
) -> list[bool | None]:
    """Uma resposta por linha: `True`, `False`, ou `None` quando o documento não registra peso.

    `registra=False` devolve `None` para todas, e é o caminho dos 26 livros do acervo que não têm
    a informação. **Devolver `False` ali seria afirmar que nada é negrito**, que é uma afirmação
    que ninguém mediu.
    """
    if not registra:
        return [None] * len(bboxes)
    return [cobertura(b, spans) >= minimo for b in bboxes]


__all__ = [
    "BIT_DE_NEGRITO",
    "COBERTURA_MINIMA",
    "FONTE_NEGRITO",
    "PAGINAS_DE_AMOSTRA",
    "cobertura",
    "documento_registra_negrito",
    "marcar",
    "spans_de_negrito",
]
