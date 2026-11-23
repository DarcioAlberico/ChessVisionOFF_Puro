"""As marcas impressas nos diagramas de uma página, lidas do recorte numa thread.

Quando a leitura dos diagramas chega à aba Texto, cada recorte passa pelo detector clássico e pelo modelo
de marcas (`opiniao_das_marcas`), e a folha guarda **o que os dois disseram juntos** (`concordancia`): é
dela que as marcas vão ao EPUB/DOCX da suíte, e ali não há quem confira.

**Numa thread, e não na leitura dos diagramas.** O `service.py` está no fecho de medição (S-218): pôr as
marcas lá dentro venceria os relatórios de campo por uma leitura que eles não medem. E não na thread da
janela: são ~50 ms por diagrama, e uma página de finais tem seis.

**Sem `models/marcas.pt`, nada.** Sem a segunda opinião não há concordância, e o detector sozinho não põe
marca no livro publicado.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from chess_diagram_ocr import detector_de_marcas
from chess_diagram_ocr import opiniao_das_marcas as om

__all__ = ["LeitorDeMarcas", "marcas_dos_recortes"]

logger = logging.getLogger(__name__)

Leitor = Callable[[np.ndarray], dict[str, str]]


def marcas_dos_recortes(recortes: Sequence[np.ndarray], leitor: Leitor) -> list[dict[str, str] | None]:
    """A concordância de cada recorte, na ordem. `None` no recorte vazio ou que um dos leitores não leu."""
    saida: list[dict[str, str] | None] = []
    for recorte in recortes:
        if recorte is None or getattr(recorte, "size", 0) == 0:
            saida.append(None)
            continue
        try:
            do_detector = detector_de_marcas.sugerir_marcas(recorte).casas
            saida.append(om.concordancia(om.juntar(do_detector, leitor(recorte))))
        except (RuntimeError, ValueError, cv2.error) as exc:
            logger.warning("Marcas não lidas num diagrama: %s", exc)
            saida.append(None)
    return saida


class LeitorDeMarcas(QObject):
    """Lê as marcas dos recortes de uma página numa thread e as entrega por `prontas(livro, página, marcas)`.

    `livro` é a chave que quem pediu passou, devolvida como veio: a resposta pode chegar depois de a
    pessoa trocar de livro, e quem a recebe compara antes de aplicar.
    """

    prontas = pyqtSignal(object, int, object)

    def __init__(
        self, parent: QObject | None = None, *, modelo: Callable[[], Path], leitor: Leitor | None = None
    ) -> None:
        super().__init__(parent)
        self._modelo = modelo
        self._leitor = leitor
        self._tentado = leitor is not None
        self._trava = threading.Lock()

    def _leitor_carregado(self) -> Leitor | None:
        with self._trava:
            if self._tentado:
                return self._leitor
            self._tentado = True
            caminho = Path(self._modelo())
            if not caminho.exists():
                logger.info("Sem %s: as marcas dos diagramas não são lidas.", caminho)
                return None
            try:
                from chess_diagram_ocr.modelo_de_marcas import leitor_de_marcas

                self._leitor = leitor_de_marcas(caminho)
            except (OSError, RuntimeError, ValueError) as exc:
                logger.warning("Modelo de marcas não carregado (%s): %s", caminho, exc)
            return self._leitor

    def esquecer(self) -> None:
        """Esquece o modelo carregado: a próxima página relê o arquivo. É o que vem depois de instalar outro."""
        with self._trava:
            self._leitor = None
            self._tentado = False

    def ler(self, livro: object, pagina: int, recortes: Sequence[np.ndarray]) -> threading.Thread | None:
        """Começa a leitura e devolve a thread (para o teste esperar). Página sem diagrama não lê nada."""
        if not recortes:
            return None
        trabalho = threading.Thread(
            target=self._trabalho, args=(livro, int(pagina), list(recortes)), name="marcas-dos-diagramas", daemon=True
        )
        trabalho.start()
        return trabalho

    def _trabalho(self, livro: object, pagina: int, recortes: list[np.ndarray]) -> None:
        leitor = self._leitor_carregado()
        if leitor is None:
            return
        marcas = marcas_dos_recortes(recortes, leitor)
        try:
            self.prontas.emit(livro, pagina, marcas)
        except RuntimeError:
            logger.debug("A aba fechou antes de as marcas chegarem.")
