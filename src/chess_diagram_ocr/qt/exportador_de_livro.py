"""*Exportar o livro para EPUB…* / *…para DOCX…*: a exportação de livro da suíte, nesta janela.

**O exportador não mora aqui.** Ele é `caissa.ui.views.exportacao.ExportadorDeLivro`, da suíte
(`Suite_de_Edicao_de_Xadrez`), escrito contra o mesmo PyQt6 e com o mesmo desenho do
`qt/exportador.py` de PGN: `estado` para o rodapé, `controles` para trancar a janela,
`cancelar`. O diálogo (formato, livro completo ou intervalo de páginas, destino) e a regra
(`caissa.export.book`) são de lá. O que este arquivo faz é o que só o tronco pode fazer: dizer
se a suíte está ao alcance e, se estiver, dar o exportador à janela já ligado ao rodapé.

**Por que a importação é guardada** -- a mesma razão de `qt/painel_de_rotulagem.py`: num checkout
do tronco a suíte é um repositório vizinho, não um pacote instalado, e exige Python 3.11. No
bundle os dois pacotes moram no mesmo arquivo. Sem a suíte os dois itens **continuam no menu,
desabilitados e com o motivo na dica** (`menu.impedir`): um menu não promete o que o produto não
faz, e um item cinza sem dica faria a pessoa procurar o defeito na própria máquina.

**O caderno vai junto (R7).** `comecar(..., folhas_para=)` entrega à suíte as folhas corrigidas na
aba Texto (`text/caderno_na_suite.py`), que entram no lugar da leitura dela dessas páginas. Uma
suíte de antes do R7 não conhece o argumento: `montar` o tira, e o livro sai com a leitura dela,
como sempre saiu, em vez de a exportação falhar num `TypeError`.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from PyQt6.QtWidgets import QWidget

__all__ = ["COMANDOS", "MOTIVO_AUSENTE", "ExportadorDeLivro", "disponivel", "montar"]

logger = logging.getLogger(__name__)

COMANDOS: tuple[str, ...] = ("exportar_epub", "exportar_docx")
"""Os dois itens de `ui/menu.py` que só funcionam com a suíte; `menu.impedir` os recebe sem ela."""

FORMATO_DO_COMANDO: dict[str, str] = {"exportar_epub": "epub", "exportar_docx": "docx"}

MOTIVO_AUSENTE = (
    "Precisa da suíte Caïssa (caissa.export), que não está ao alcance deste programa.\n"
    "No Caissa.exe ela vem junto; num checkout, rode com o Python 3.11 da suíte."
)


class ExportadorDeLivro(Protocol):
    """A face do exportador da suíte que a janela usa. Ver `caissa.ui.views.exportacao`."""

    rodando: bool

    def comecar(
        self, pdf_path: Path | None, page_count: int, *, formato: str, pagina_atual: int,
        documento_para: Callable[[Sequence[int] | None], Any] | None = None,
        folhas_para: Callable[[Sequence[int] | None], Sequence[Mapping[str, Any]]] | None = None,
    ) -> bool: ...

    def cancelar(self) -> None: ...


def disponivel() -> bool:
    """Se a suíte está importável daqui -- é o que decide se os dois itens ficam habilitados."""
    try:
        import caissa.ui.views.exportacao  # noqa: F401 - só a pergunta "existe?"
    except Exception:  # noqa: BLE001 - ImportError, SyntaxError num Python antigo, tudo é "não"
        return False
    return True


def montar(
    pai: QWidget, *, dizer: Callable[[str], Any], trancar: Callable[[bool], Any]
) -> ExportadorDeLivro | None:
    """O exportador da suíte já ligado ao rodapé e à tranca da janela, ou `None` com o motivo no log.

    `dizer` recebe cada frase de `estado`; `trancar` recebe `controles`, que vem invertido como o
    do exportador de PGN (`False` é "começou").
    """
    try:
        from caissa.ui.views.exportacao import ExportadorDeLivro as _Exportador
    except Exception as exc:  # noqa: BLE001 - ver o cabeçalho
        logger.info("exportação para EPUB/DOCX ausente: a suíte não está ao alcance (%s).", exc)
        return None
    exportador = _Exportador(pai)
    if "folhas_para" not in inspect.signature(exportador.comecar).parameters:
        # Uma suíte de antes do R7 não leva o caderno ao livro: a exportação segue com a leitura
        # dela, como sempre foi, em vez de falhar no argumento que ela não conhece.
        logger.info("a suíte ao alcance não recebe as folhas do caderno (R7); o EPUB/DOCX sai sem elas.")
        comecar = exportador.comecar

        def _sem_folhas(*args: Any, folhas_para: Any = None, **kwargs: Any) -> Any:
            return comecar(*args, **kwargs)

        exportador.comecar = _sem_folhas
    exportador.estado.connect(dizer)
    exportador.controles.connect(trancar)
    return exportador
