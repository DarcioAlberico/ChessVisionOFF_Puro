"""O que a **camada de texto do PDF** declara sobre a forma da letra, e como isso vira linha.

**Este módulo é a máquina, e não a régua.** Ele não sabe o que é negrito nem o que é itálico: sabe
perguntar à página quais retângulos têm um estilo, medir quanto de cada linha eles cobrem, e
devolver `True`/`False`/`None` por linha. Quem diz *o que* procurar é `text/negrito.py` (peso) e
`text/italico.py` (pendor), cada um com o nome de fonte e o bit que o denunciam.

**Por que ele nasceu separado.** A máquina foi escrita para o negrito na S-237 -- spans → cobertura
→ `marcar` --, e a S-236 registrou por escrito que o itálico da camada precisava dela: *"a máquina
para isso já existe em `text/negrito.py`, e generalizá-la é o que falta"*. Copiá-la para o outro
módulo seria a segunda declaração da mesma regra geométrica, que é o defeito que este projeto passa
o tempo tirando de si. `text/negrito.py` continua exportando os mesmos nomes, agora delegando aqui.

## As três decisões que a máquina carrega, e valem para os dois estilos

**`None` é "não se sabe", e é diferente de `False`.** Um livro cuja camada não registra estilo
nenhum não pode declarar que nada ali é negrito ou itálico -- ele não sabe. Quem separa os dois é o
**documento**, e não a página: uma página de prosa sem itálico num livro que o registra é um `False`
legítimo.

**A unidade é a linha, e a decisão é por maioria da largura.** A `PaginaLida` não tem unidade menor
que a `LinhaLida`, então uma linha meio em itálico é decidida pela fração dela que o estilo cobre.
Onde o estilo é a linha inteira -- título, citação, variante -- o resultado é exato; onde ele é uma
palavra no meio da prosa, é grosso, e isso está declarado.

**Os trechos cobertos são unidos antes de somar.** Dois spans que se sobrepõem não contam duas
vezes; sem isso uma linha poderia "cobrir" mais que 100% de si mesma.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

__all__ = [
    "COBERTURA_MINIMA",
    "PAGINAS_DE_AMOSTRA",
    "Retangulo",
    "cobertura",
    "documento_registra",
    "marcar",
    "spans_com",
]

Retangulo = tuple[float, float, float, float]

COBERTURA_MINIMA = 0.60
"""Fração da largura da linha que precisa ter o estilo para a linha inteira contar como tal.

Maioria, e não qualquer sobreposição: uma linha de prosa com **um** lance em negrito no meio não é
uma linha em negrito, e marcá-la assim seria pior que não marcar."""

PAGINAS_DE_AMOSTRA = 6
"""Quantas páginas se olham para decidir se o **documento** registra aquele estilo.

A pergunta não é da página -- ver "As três decisões" no cabeçalho."""


def spans_com(page: object, e_do_estilo: Callable[[dict], bool]) -> list[Retangulo]:
    """Os retângulos daquele estilo na página, em **pontos do PDF**. Vazio quando não há nenhum.

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
                if e_do_estilo(span):
                    x0, y0, x1, y1 = span["bbox"]
                    saida.append((float(x0), float(y0), float(x1), float(y1)))
    return saida


def documento_registra(
    doc: object,
    e_do_estilo: Callable[[dict], bool],
    *,
    amostra: int = PAGINAS_DE_AMOSTRA,
) -> bool:
    """Este documento registra aquele estilo em algum lugar? Ver `PAGINAS_DE_AMOSTRA`.

    **É a pergunta que separa `False` de `None`.** Uma página sem itálico num livro que o registra é
    "aqui não tem"; num livro que não o registra é "não se sabe", e as duas não podem virar a mesma
    coisa.
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
            if spans_com(doc[indice], e_do_estilo):  # type: ignore[index]
                return True
        except Exception:  # pragma: no cover - página ilegível
            continue
    return False


def cobertura(bbox: Retangulo, spans: Sequence[Retangulo]) -> float:
    """Fração da **largura** da linha coberta pelos spans. `0.0` quando não há sobreposição.

    Largura e não área porque a linha e o span têm a mesma altura por construção -- os dois vêm da
    mesma linha de texto --, e comparar áreas só acrescentaria ruído de arredondamento vertical.
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
    """Uma resposta por linha: `True`, `False`, ou `None` quando o documento não registra o estilo.

    `registra=False` devolve `None` para todas, e é o caminho dos livros do acervo que não têm a
    informação. **Devolver `False` ali seria afirmar que nada tem aquele estilo**, que é uma
    afirmação que ninguém mediu.
    """
    if not registra:
        return [None] * len(bboxes)
    return [cobertura(b, spans) >= minimo for b in bboxes]
