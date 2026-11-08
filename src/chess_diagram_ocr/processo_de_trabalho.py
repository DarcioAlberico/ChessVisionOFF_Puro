"""O trabalho que segura o GIL vai para um processo filho (OCR_UI passo 15).

**O que uma thread não resolve.** A janela precisa do interpretador para cada evento, cada
`eventFilter` e cada pulso de `QTimer`; uma `QThread` que roda Python -- ou C que não solta o
GIL -- tira o trabalho da thread da janela só no nome. Medido em 2026-09-16 sobre
`1937 Kemeri.pdf`, com o arnês `caissa.ui.audit.bloqueio`:

* `render_pdf_page` a 300 DPI numa thread: o `get_pixmap` do PyMuPDF 1.28 segura o GIL os
  43–49 ms inteiros, e a pior espera da thread principal é **51 ms**. Em faixas de 512 px
  (cinco `get_pixmap` com `clip`) a pior faixa custa 30 ms e a espera 33 ms, porque o scan
  embutido é decodificado inteiro a cada faixa.
* `load_rows` do `labels.csv` (5.431 linhas, legalidade de cada FEN em Python) numa thread:
  a primeira troca para a aba Dataset trava **54,6 ms** com o intervalo de troca padrão do
  interpretador e 8–20 ms com ele encurtado -- e, enquanto a leitura corre, todo Python da
  janela anda à metade da velocidade, porque as duas threads revezam o GIL.

**Um processo, então.** O filho roda a mesma função (`render_pdf_page`, `load_rows`, o que
for), e o pai só espera -- e esperar um `Pipe` solta o GIL. O que atravessa é o resultado, num
`pickle` que custa uns poucos milissegundos de cada lado (26 MB para uma página a 300 DPI).

**Um filho só, e preguiçoso.** Ele nasce na primeira chamada (ou em `aquecer`, que a abertura
do livro chama de uma thread para pagar o `spawn` fora da janela) e morre com o processo: o
`concurrent.futures` já cuida disso no `atexit`. Se ele morrer no meio, o pai o recria e tenta
de novo, uma vez; se morrer de novo **na mesma chamada**, sobe `PaginaQueDerruba` (S-874).

**A função que derruba o filho nunca roda aqui.** O isolamento existe para o PDF que derruba o
MuPDF, e uma página que derruba derruba sempre: rodá-la em linha depois da segunda queda era
derrubar a janela na terceira. A conta é por chamada: uma queda, horas depois e noutra página,
começa do zero.

**No bundle congelado o `spawn` reexecuta o `.exe`**, e é o `mp.freeze_support()` do
`app_pyqt.main` que impede o filho de abrir outra janela.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import threading
from collections.abc import Callable
from concurrent.futures import BrokenExecutor, Future, ProcessPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

from chess_diagram_ocr.pdf_io import PdfSource, render_pdf_page

logger = logging.getLogger(__name__)

__all__ = ["FalhaDoProcessoDeTrabalho", "PaginaQueDerruba", "ProcessoDeTrabalho", "processo_de_trabalho"]

T = TypeVar("T")


class FalhaDoProcessoDeTrabalho(RuntimeError):
    """O trabalho não voltou do filho. A mensagem é a frase que a tela mostra.

    `pagina` é o índice da página (a primeira é 0) quando o trabalho era de uma página, e `None`
    quando não era -- a leitura do dataset, a das marcas.
    """

    def __init__(self, frase: str, pagina: int | None) -> None:
        super().__init__(frase)
        self.pagina = pagina


class PaginaQueDerruba(FalhaDoProcessoDeTrabalho):
    """O filho morreu duas vezes na mesma chamada (S-874)."""

    def __init__(self, pagina: int | None) -> None:
        if pagina is None:
            frase = "O trabalho derrubou o processo de trabalho duas vezes seguidas e ficou sem fazer."
        else:
            frase = f"A página {pagina + 1} derruba o leitor de PDF: ela foi pulada."
        super().__init__(frase, pagina)


def _aquecer() -> bool:
    """O que o filho roda para existir: importar o que `render_pdf_page` precisa."""
    return True


class ProcessoDeTrabalho:
    """Roda funções fora do processo. Ver o cabeçalho do módulo.

    `em_processo=False` roda tudo em linha, na thread de quem chama -- é o caminho dos testes
    de janela e do `--selftest`, que não têm por que pagar um processo filho.
    """

    def __init__(self, *, em_processo: bool = True) -> None:
        self.em_processo = em_processo
        self._pool: ProcessPoolExecutor | None = None
        self._trava = threading.Lock()

    # ------------------------------------------------------------------------------- vida

    def _garantir(self) -> ProcessPoolExecutor | None:
        """O filho, criado na primeira vez. `None` se o processo não puder existir."""
        with self._trava:
            if self._pool is None:
                try:
                    self._pool = ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"))
                except Exception:  # noqa: BLE001 - ambiente sem `spawn` possível
                    logger.exception("Sem processo de trabalho: tudo será feito em linha.")
                    self.em_processo = False
                    return None
            return self._pool

    def aquecer(self) -> Future[bool] | None:
        """Faz o filho nascer e importar, sem esperar. Chame de uma thread: o `spawn` custa."""
        if not self.em_processo:
            return None
        pool = self._garantir()
        if pool is None:
            return None
        try:
            return pool.submit(_aquecer)
        except BrokenExecutor:
            return None

    def encerrar(self, esperar: bool = False) -> None:
        """Derruba o filho. Sem esperar, por padrão; `esperar` é para quem conta threads (testes)."""
        with self._trava:
            pool = self._pool
        if pool is not None:
            self._descartar(pool, esperar=esperar)

    def _descartar(self, pool: ProcessPoolExecutor, *, esperar: bool = False) -> None:
        """Tira `pool` de uso. Só ele: outra thread pode já ter criado o seguinte."""
        with self._trava:
            if self._pool is pool:
                self._pool = None
        pool.shutdown(wait=esperar, cancel_futures=True)

    # ------------------------------------------------------------------------------ trabalho

    def executar(
        self, funcao: Callable[..., T], /, *args: Any, pagina: int | None = None, **kwargs: Any
    ) -> T:
        """`funcao(*args, **kwargs)` no filho, esperando o resultado. Em linha se ele não existe.

        A função e os argumentos atravessam por `pickle`: função de módulo (não `lambda`) e
        argumentos simples. Quem chama está numa `Tarefa`, nunca na thread da janela -- esperar
        aqui é o que a tira de lá.

        `pagina` (o índice; não vai à função) é a página de que o trabalho trata, para a frase de
        `PaginaQueDerruba`, que sobe quando o filho morre duas vezes nesta chamada.
        """
        if not self.em_processo:
            return funcao(*args, **kwargs)
        try:
            return self._no_filho(funcao, *args, **kwargs)
        except BrokenExecutor as exc:
            logger.warning("O processo de trabalho morreu (%s); criando outro.", exc)
        try:
            return self._no_filho(funcao, *args, **kwargs)
        except BrokenExecutor as de_novo:
            erro = PaginaQueDerruba(pagina)
            logger.error("O processo de trabalho morreu de novo (%s): %s", de_novo, erro)
            raise erro from de_novo

    def _no_filho(self, funcao: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
        pool = self._garantir()
        if pool is None:
            return funcao(*args, **kwargs)
        try:
            return pool.submit(funcao, *args, **kwargs).result()
        except BrokenExecutor:
            self._descartar(pool)
            raise

    def rasterizar(self, source: PdfSource, page_index: int, *, dpi: int) -> np.ndarray:
        """A página como `render_pdf_page` a devolve -- vinda do filho, ou daqui se ele não existe."""
        caminho = Path(source) if isinstance(source, str) else source
        return self.executar(render_pdf_page, caminho, page_index, dpi=dpi, pagina=page_index)


_PARTILHADO: ProcessoDeTrabalho | None = None
_TRAVA = threading.Lock()


def processo_de_trabalho() -> ProcessoDeTrabalho:
    """O processo de trabalho deste processo. Um só: um filho por janela seria um filho por nada."""
    global _PARTILHADO
    with _TRAVA:
        if _PARTILHADO is None:
            _PARTILHADO = ProcessoDeTrabalho()
        return _PARTILHADO
