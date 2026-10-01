"""A correção da janela chega ao livro: o gancho que grava a decisão (OCR_UI ciclo 2, passo A3).

**O defeito, medido na análise (§6.2).** A pessoa corrige o diagrama no painel de Resultado e
grava a amostra em `labels.csv`; o EPUB exportado depois traz a FEN que a máquina leu. Nada
ligava a correção ao livro: o exportador reimporta o PDF e só aplica as `ReviewDecisions` do
texto. O contrato que fecha o furo é `caissa.ocr.diagram_decisions` (roadmap C2 §1.1): uma
decisão por `(página, retângulo em pontos)`, casada por IoU ≥ 0,5 na importação, e `record()`
é a função que este lado chama quando a gravação da amostra dá certo.

**Guardado como as abas da suíte** (`qt/painel_de_rotulagem.py`): num checkout do tronco a suíte é
um repositório vizinho e exige Python 3.11; sem ela, gravar a amostra continua gravando a amostra
e a decisão não é registrada -- com o motivo no log, nunca uma caixa. O `import` é resolvido
**por chamada** e num ponto só (`_contrato`), que é o que o teste troca por um falso.

**Em `qt/` e não em `ui/`** de propósito: `tests/test_editor_model.SEM_TKINTER` enumera cada
módulo de `ui/` e reprova o que não estiver declarado; o gancho é uma ponte para outro pacote,
como `qt/importador_de_livro.py`, e mora ao lado dele.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chess_diagram_ocr.semantics import compose_fen

logger = logging.getLogger(__name__)

__all__ = ["ORIGEM", "gravar_decisao", "retangulo_em_pontos"]

ORIGEM = "janela"
"""O `source` da decisão: quem gravou foi a janela do tronco (contrato §1.1)."""

PONTOS_POR_POLEGADA = 72.0


def _contrato() -> tuple[type, Callable[..., Any]] | None:
    """`(DiagramDecision, record)` da suíte, ou `None` quando ela não está ao alcance."""
    try:
        from caissa.ocr.diagram_decisions import DiagramDecision, record
    except Exception as exc:  # noqa: BLE001 - ImportError, SyntaxError num Python antigo, tudo é "não"
        logger.info("decisão de diagrama não registrada: a suíte não está ao alcance (%s).", exc)
        return None
    return DiagramDecision, record


def retangulo_em_pontos(item: Any, dpi: float) -> tuple[float, float, float, float] | None:
    """Onde o diagrama está na página, em **pontos do PDF** -- o que a decisão guarda.

    `bbox_pdf` já vem em pontos (S-41) e é a resposta quando existe. Sem ele, o `quad` são os
    quatro cantos em pixels da página renderizada, e pontos = pixels × 72 / DPI do render. Sem
    nenhum dos dois -- item da fila, amostra do dataset, recorte de área -- não há onde casar a
    decisão, e a resposta honesta é `None`.
    """
    bbox = getattr(item, "bbox_pdf", None)
    if bbox is not None:
        x0, y0, x1, y1 = (float(v) for v in bbox)
        return (x0, y0, x1, y1)
    quad = getattr(item, "quad", None)
    if not quad or not dpi:
        return None
    escala = PONTOS_POR_POLEGADA / float(dpi)
    xs = [float(ponto[0]) * escala for ponto in quad]
    ys = [float(ponto[1]) * escala for ponto in quad]
    return (min(xs), min(ys), max(xs), max(ys))


def gravar_decisao(
    pdf: str | Path,
    *,
    page_index: int,
    item: Any,
    placement: str,
    side: str,
    dpi: float,
    reviewer: str = "",
) -> Path | None:
    """Registra a posição gravada como decisão daquele diagrama. Devolve o arquivo, ou `None`.

    Nunca levanta: a amostra **já está** no `labels.csv` quando isto é chamado, e uma exceção
    aqui produziria "falha ao salvar" sobre uma gravação que aconteceu (a mesma regra de
    `PainelDeResultado._gravar_alvo`).
    """
    contrato = _contrato()
    if contrato is None:
        return None
    rect = retangulo_em_pontos(item, dpi)
    if rect is None:
        logger.info("decisão de diagrama não registrada: o item não tem retângulo na página.")
        return None
    decisao_cls, record = contrato
    lado = "b" if str(side) == "b" else "w"
    try:
        decisao = decisao_cls(
            page_index=int(page_index),
            rect=rect,
            fen=compose_fen(str(placement).split(" ")[0], lado != "b"),
            side=lado,
            decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            reviewer=reviewer,
            source=ORIGEM,
        )
        caminho = record(Path(pdf), decisao)
    except Exception:  # noqa: BLE001 - ver o docstring
        logger.exception("A decisão do diagrama não pôde ser registrada.")
        return None
    logger.info("Decisão do diagrama da página %d registrada em %s.", int(page_index) + 1, caminho)
    return Path(caminho) if caminho is not None else None
