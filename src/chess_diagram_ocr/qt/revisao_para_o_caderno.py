"""*Trazer as correções da Revisão de texto*: o R7 de volta, do lado do tronco.

**Quem acha as folhas não mora aqui.** É `caissa.export.reviewed_pages.reviewed_page_texts`, da
suíte: ela sabe que regiões o revisor editou, e garante um IR com as decisões aplicadas -- a
importação em mãos, quando ela serve, ou uma importação só dessas páginas. O que este arquivo faz é
o que só o tronco pode: dizer se a suíte está ao alcance, e chamá-la com o livro e a importação que
a janela tem. **A regra de quem vence é do tronco** (`text/caderno_na_suite.trazer_da_suite`), e
quem a aplica é a aba Texto, que tem o caderno aberto.

Guardado como `qt/exportador_de_livro.py`, e pela mesma razão: num checkout do tronco a suíte é um
repositório vizinho, e sem ela o comando diz o motivo no rodapé em vez de não existir.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

__all__ = ["MOTIVO_AUSENTE", "buscar", "disponivel"]

logger = logging.getLogger(__name__)

MOTIVO_AUSENTE = (
    "Trazer as correções da Revisão de texto precisa da suíte Caïssa "
    "(caissa.export.reviewed_pages), que não está ao alcance deste programa."
)


def disponivel() -> bool:
    """Se a suíte que conhece a volta está importável daqui."""
    try:
        import caissa.export.reviewed_pages  # noqa: F401 - só a pergunta "existe?"
    except Exception:  # noqa: BLE001 - ImportError, suíte de antes da volta, Python antigo: tudo é "não"
        return False
    return True


def buscar(pdf: Path | str, *, documento: Any = None, desistir: Callable[[], bool] | None = None) -> list[dict[str, Any]]:
    """As folhas editadas na Revisão de texto, no formato 1. **Na thread de trabalho**: pode reimportar."""
    from caissa.export.reviewed_pages import reviewed_page_texts

    achadas = reviewed_page_texts(Path(pdf), document=documento, should_cancel=desistir)
    if achadas.reimported:
        logger.info("Revisão de texto: %d página(s) importada(s) de novo para trazer as decisões.", len(achadas.pages))
    return [dict(folha) for folha in achadas.page_texts]
