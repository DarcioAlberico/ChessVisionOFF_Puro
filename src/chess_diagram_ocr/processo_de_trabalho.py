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
`closeEvent` da janela o mata (`encerrar(matar=True)`), e o `atexit` do `concurrent.futures`
cuida do resto. Se ele morrer no meio, o pai o recria e tenta de novo, uma vez; se morrer de
novo **na mesma chamada**, sobe `PaginaQueDerruba` (S-874).

**Toda chamada tem prazo** (`PRAZO_S`, S-906). A página que pendura o MuPDF não derruba nada, e
sem prazo ela segurava a `Tarefa` para sempre -- e, no fechamento, o processo inteiro: o `atexit`
do `concurrent.futures` espera o trabalho em curso, e a janela sumia deixando o programa vivo no
Gerenciador de Tarefas. Esgotado o prazo, o filho é morto e sobe `PaginaPendurada`.

**O log do filho vai ao arquivo do pai** (S-906). O `spawn` começa um interpretador limpo, sem
`configure_logging`: o aviso da detecção que roda ali caía no `lastResort`, que no `.exe` é um
`stderr` que não existe. O `initializer` do pool põe um `QueueHandler` na raiz do filho, e um
`QueueListener` daqui entrega cada registro ao logger de mesmo nome deste processo.

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
from concurrent.futures import BrokenExecutor, CancelledError, Future, ProcessPoolExecutor
from concurrent.futures import TimeoutError as SemRespostaNoPrazo
from dataclasses import dataclass
from logging.handlers import QueueHandler, QueueListener
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

from chess_diagram_ocr.pdf_io import PdfSource, render_pdf_page

logger = logging.getLogger(__name__)

__all__ = [
    "PRAZO_S",
    "FalhaDoProcessoDeTrabalho",
    "PaginaPendurada",
    "PaginaQueDerruba",
    "ProcessoDeTrabalho",
    "ProcessoEncerrado",
    "processo_de_trabalho",
]

T = TypeVar("T")

PRAZO_S = 60.0
"""Quanto uma chamada espera o filho antes de matá-lo (S-906). O mais lento que passa por aqui é a
leitura do `labels.csv` (alguns segundos), e a página a 300 DPI leva menos de um; o prazo conta
também o `spawn` da primeira chamada. Sessenta segundos é folga de máquina lenta, e não de página."""


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


class PaginaPendurada(FalhaDoProcessoDeTrabalho):
    """O filho não respondeu no prazo, e foi morto (S-906)."""

    def __init__(self, pagina: int | None, prazo_s: float) -> None:
        if pagina is None:
            frase = f"O trabalho não respondeu em {prazo_s:g} s e foi interrompido."
        else:
            frase = (
                f"A página {pagina + 1} não respondeu em {prazo_s:g} s: o leitor de PDF ficou preso nela, "
                "e ela foi pulada."
            )
        super().__init__(frase, pagina)
        self.prazo_s = prazo_s


class ProcessoEncerrado(FalhaDoProcessoDeTrabalho):
    """O pedido chegou depois de `encerrar(matar=True)`: o programa está fechando."""

    def __init__(self) -> None:
        super().__init__("O programa está fechando: o trabalho pedido agora não será feito.", None)


def _iniciar_o_log_do_filho(fila: Queue[logging.LogRecord], niveis: dict[str, int]) -> None:
    """O `initializer` do pool: no filho, todo registro vai para `fila`, com os níveis do pai."""
    raiz = logging.getLogger()
    for manipulador in list(raiz.handlers):
        raiz.removeHandler(manipulador)
    raiz.addHandler(QueueHandler(fila))
    for nome, nivel in niveis.items():
        logging.getLogger(nome).setLevel(nivel)


def _niveis_daqui() -> dict[str, int]:
    """Os níveis postos neste processo: o da raiz (`""`) e os de quem `configure_logging` calou."""
    niveis = {"": logging.getLogger().level}
    for nome, registrador in logging.Logger.manager.loggerDict.items():
        if isinstance(registrador, logging.Logger) and registrador.level != logging.NOTSET:
            niveis[nome] = registrador.level
    return niveis


class _AoLoggerDeMesmoNome(logging.Handler):
    """Entrega o registro vindo do filho ao logger de mesmo nome daqui, e daí aos handlers daqui."""

    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)


@dataclass(frozen=True)
class _Filho:
    """O pool de um filho e a escuta do log dele, que nascem e morrem juntos.

    **Uma fila por filho**, e não uma para a vida do objeto: o filho morto no meio de um `put`
    pode deixar a fila com meia mensagem, e o seguinte não deve herdá-la.
    """

    pool: ProcessPoolExecutor
    fila: Queue[logging.LogRecord]
    escuta: QueueListener


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
        self._filho: _Filho | None = None
        self._trava = threading.Lock()
        self._encerrado = False
        """Depois de `encerrar(matar=True)` nenhum filho nasce: o programa está fechando."""

    # ------------------------------------------------------------------------------- vida

    def _garantir(self) -> _Filho | None:
        """O filho, criado na primeira vez. `None` se o processo não puder existir."""
        with self._trava:
            if self._encerrado:
                raise ProcessoEncerrado()
            if self._filho is None:
                contexto = mp.get_context("spawn")
                try:
                    fila: Queue[logging.LogRecord] = contexto.Queue()
                    pool = ProcessPoolExecutor(
                        max_workers=1,
                        mp_context=contexto,
                        initializer=_iniciar_o_log_do_filho,
                        initargs=(fila, _niveis_daqui()),
                    )
                except Exception:  # noqa: BLE001 - ambiente sem `spawn` possível
                    logger.exception("Sem processo de trabalho: tudo será feito em linha.")
                    self.em_processo = False
                    return None
                escuta = QueueListener(fila, _AoLoggerDeMesmoNome())
                escuta.start()
                self._filho = _Filho(pool, fila, escuta)
            return self._filho

    def aquecer(self) -> Future[bool] | None:
        """Faz o filho nascer e importar, sem esperar. Chame de uma thread: o `spawn` custa."""
        if not self.em_processo:
            return None
        try:
            filho = self._garantir()
            if filho is None:
                return None
            return filho.pool.submit(_aquecer)
        except (BrokenExecutor, ProcessoEncerrado):
            return None

    def encerrar(self, esperar: bool = False, *, matar: bool = False) -> None:
        """Derruba o filho. Sem esperar, por padrão; `esperar` é para quem conta threads (testes).

        `matar` é o do fechamento da janela: o filho morre no meio do que estiver fazendo, a
        chamada em curso recebe `ProcessoEncerrado`, e nenhum filho nasce depois.
        """
        with self._trava:
            filho = self._filho
            if matar:
                self._encerrado = True
        if filho is not None:
            self._descartar(filho, esperar=esperar, matar=matar)

    def _descartar(self, filho: _Filho, *, esperar: bool = False, matar: bool = False) -> None:
        """Tira `filho` de uso, uma vez só. Só ele: outra thread pode já ter criado o seguinte.

        **Quem o tira da vaga é quem o desmonta.** A chamada em curso num filho morto pelo
        fechamento também chega aqui, e a escuta parada duas vezes escreve numa fila já fechada.
        """
        with self._trava:
            if self._filho is not filho:
                return
            self._filho = None
        if matar:
            # **Atributo privado, e não há outro caminho antes do 3.14** (`kill_workers`): o
            # `shutdown` só pede ao filho que saia depois do trabalho em curso, e o trabalho em
            # curso é o que pendurou. Antes do `shutdown`, que apaga o atributo.
            for processo in list((filho.pool._processes or {}).values()):
                processo.kill()
        filho.pool.shutdown(wait=esperar, cancel_futures=True)
        filho.escuta.stop()
        filho.fila.close()
        filho.fila.join_thread()

    # ------------------------------------------------------------------------------ trabalho

    def executar(
        self,
        funcao: Callable[..., T],
        /,
        *args: Any,
        pagina: int | None = None,
        prazo_s: float | None = PRAZO_S,
        **kwargs: Any,
    ) -> T:
        """`funcao(*args, **kwargs)` no filho, esperando o resultado. Em linha se ele não existe.

        A função e os argumentos atravessam por `pickle`: função de módulo (não `lambda`) e
        argumentos simples. Quem chama está numa `Tarefa`, nunca na thread da janela -- esperar
        aqui é o que a tira de lá.

        `pagina` (o índice; não vai à função) é a página de que o trabalho trata, para a frase de
        `PaginaQueDerruba`, que sobe quando o filho morre duas vezes nesta chamada, e para a de
        `PaginaPendurada`, que sobe quando ele não responde em `prazo_s` (`None`: sem prazo).
        """
        if not self.em_processo:
            return funcao(*args, **kwargs)
        try:
            return self._no_filho(funcao, args, kwargs, pagina=pagina, prazo_s=prazo_s)
        except BrokenExecutor as exc:
            logger.warning("O processo de trabalho morreu (%s); criando outro.", exc)
        try:
            return self._no_filho(funcao, args, kwargs, pagina=pagina, prazo_s=prazo_s)
        except BrokenExecutor as de_novo:
            erro = PaginaQueDerruba(pagina)
            logger.error("O processo de trabalho morreu de novo (%s): %s", de_novo, erro)
            raise erro from de_novo

    def _no_filho(
        self,
        funcao: Callable[..., T],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        pagina: int | None,
        prazo_s: float | None,
    ) -> T:
        filho = self._garantir()
        if filho is None:
            return funcao(*args, **kwargs)
        try:
            return filho.pool.submit(funcao, *args, **kwargs).result(timeout=prazo_s)
        except BrokenExecutor:
            self._descartar(filho)
            raise
        except CancelledError as exc:
            # O pedido estava na fila quando outra thread descartou o filho: a culpa não é dele.
            self._descartar(filho)
            raise BrokenExecutor("o pedido foi cancelado junto com o processo de trabalho") from exc
        except SemRespostaNoPrazo:
            self._descartar(filho, matar=True)
            erro = PaginaPendurada(pagina, prazo_s or 0.0)
            logger.error("O processo de trabalho foi morto: %s", erro)
            raise erro from None

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
