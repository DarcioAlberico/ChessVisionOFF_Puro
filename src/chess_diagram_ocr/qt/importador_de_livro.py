"""*Importar o livro*: a importação da suíte nesta janela, com o trilho de páginas como destino.

**O importador não mora aqui.** Ele é `caissa.ui.views.importacao.ImportadorDoLivro`, da suíte,
com o desenho do exportador de livro: `estado` para o rodapé, `progresso` para a barra,
`controles` para trancar, `pagina_montada` a cada página e `terminou` com o
:class:`ImportResult` -- inteiro ou **parcial**, porque a importação corre com `keep_partial`
(R3.5: cancelar deixa o que já foi lido). O que este arquivo faz é o que só o tronco pode:
dizer se a suíte está ao alcance e, se estiver, ligar o importador ao rodapé, ao registro de
operações e ao trilho.

**Por que a importação é guardada** -- a mesma razão de `qt/exportador_de_livro.py`: num checkout
do tronco a suíte é um repositório vizinho, não um pacote instalado, e exige Python 3.11. Sem ela
os botões do trilho ficam desabilitados com o motivo na dica, e os itens do menu recebem
`menu.impedir`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from PyQt6.QtWidgets import QWidget

from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken

__all__ = ["COMANDOS", "MOTIVO_AUSENTE", "ImportadorDoLivro", "Ponte", "disponivel", "estados_do_trilho", "montar"]

logger = logging.getLogger(__name__)

COMANDOS: tuple[str, ...] = ("importar_livro", "cancelar_importacao", "primeira_duvidosa")
"""Os itens de `ui/menu.py` que só funcionam com a suíte; `menu.impedir` os recebe sem ela."""

MOTIVO_AUSENTE = (
    "Precisa da suíte Caïssa (caissa.ui.views.importacao), que não está ao alcance deste programa.\n"
    "No Caissa.exe ela vem junto; num checkout, rode com o Python 3.11 da suíte."
)


class ImportadorDoLivro(Protocol):
    """A face do importador da suíte que a janela usa. Ver `caissa.ui.views.importacao`."""

    rodando: bool
    resultado: Any

    def comecar(
        self, pdf_path: Path | None, page_count: int, *, paginas: tuple[int, ...] | None = None
    ) -> bool: ...

    def cancelar(self) -> None: ...


def disponivel() -> bool:
    try:
        import caissa.ui.views.importacao  # noqa: F401 - só a pergunta "existe?"
    except Exception:  # noqa: BLE001 - ImportError, SyntaxError num Python antigo, tudo é "não"
        return False
    return True


class Ponte:
    """O importador da suíte ligado ao trilho: começa, cancela e traduz o relatório em estados.

    Mora aqui e não em `qt/janela.py` de propósito: a janela é coordenadora, e cada fio que ela
    não precisa segurar é uma linha a menos na catraca de `test_packaging`.
    """

    def __init__(
        self,
        importador: Any,
        trilho: Any,
        *,
        pdf_atual: Callable[[], Path | None],
        paginas: Callable[[], int],
        dizer: Callable[[str], Any],
    ) -> None:
        self.importador = importador
        self._trilho = trilho
        self._pdf_atual = pdf_atual
        self._paginas = paginas
        self._dizer = dizer
        self.resultado: Any = None
        """O `ImportResult` da última importação (inteira ou parcial) do livro aberto."""
        importador.progresso.connect(trilho.importacao_avancou)
        importador.pagina_montada.connect(trilho.marcar_montada)
        importador.terminou.connect(self._chegou)
        trilho.importar_pedido.connect(self.comecar)
        trilho.cancelar_pedido.connect(self.cancelar)

    @property
    def rodando(self) -> bool:
        return bool(self.importador.rodando)

    def comecar(self, paginas: tuple[int, ...] | None = None) -> None:
        """Importa o livro inteiro -- ou `paginas` (base 0), para quem mede ou quer só um capítulo."""
        pdf = self._pdf_atual()
        if pdf is None:
            self._dizer("Abra um PDF antes de importar o livro.")
            return
        self.resultado = None
        quantas = len(paginas) if paginas is not None else self._paginas()
        if self.importador.comecar(pdf, self._paginas(), paginas=paginas):
            self._trilho.importacao_comecou(2 * quantas)

    def cancelar(self) -> None:
        if self.importador.rodando:
            self.importador.cancelar()

    def _chegou(self, resultado: object) -> None:
        """O relatório da importação (inteiro ou parcial) vira o estado das páginas no trilho."""
        self._trilho.importacao_terminou()
        pdf = self._pdf_atual()
        if pdf is None or resultado is None:
            return
        self.resultado = resultado
        try:
            estados, resumo = estados_do_trilho(resultado, pdf, self._paginas())
        except Exception:  # noqa: BLE001 - o trilho é mapa; sem ele o livro continua aberto
            logger.exception("O estado das páginas não pôde ser calculado.")
            return
        self._trilho.definir_estados(estados, resumo=resumo)


def montar(
    pai: QWidget,
    *,
    dizer: Callable[[str], Any],
    trancar: Callable[[bool], Any],
    ocupado: BusyRegistry | None = None,
    trilho: Any = None,
    pdf_atual: Callable[[], Path | None] = lambda: None,
    paginas: Callable[[], int] = lambda: 0,
) -> Ponte | None:
    """O importador da suíte ligado ao rodapé, à tranca, ao registro e ao trilho, ou `None`.

    O registro (`BusyRegistry`) é o que faz o rodapé mostrar a barra determinada com o botão de
    cancelar: a importação é a operação mais longa que esta janela dispara, e R3.5 pede progresso
    real e cancelamento -- os dois passam por aqui.
    """
    try:
        from caissa.ui.views.importacao import ImportadorDoLivro as _Importador
    except Exception as exc:  # noqa: BLE001 - ver o cabeçalho
        logger.info("importação de livro ausente: a suíte não está ao alcance (%s).", exc)
        return None
    importador = _Importador(pai)
    importador.estado.connect(dizer)
    importador.controles.connect(trancar)
    if ocupado is not None:
        _Registro(importador, ocupado)
    return Ponte(importador, trilho, pdf_atual=pdf_atual, paginas=paginas, dizer=dizer)


class _Registro:
    """Traduz os sinais do importador em uma ficha do `BusyRegistry`."""

    def __init__(self, importador: Any, registro: BusyRegistry) -> None:
        self._importador = importador
        self._registro = registro
        self._ficha: BusyToken | None = None
        importador.controles.connect(self._controles)
        importador.progresso.connect(self._progresso)

    def _controles(self, liberado: bool) -> None:
        if not liberado and self._ficha is None:
            self._ficha = self._registro.register(
                "importação do livro",
                # Cancelar não perde nada: o parcial fica (R3.5). Mas é longa, e a barra precisa andar.
                loses_work=False,
                cancellable=True,
                cancel=self._importador.cancelar,
                detail=str(getattr(self._importador, "pdf_path", "") or ""),
            )
        elif liberado and self._ficha is not None:
            ficha, self._ficha = self._ficha, None
            ficha.release()

    def _progresso(self, feito: int, total: int) -> None:
        if self._ficha is not None:
            self._ficha.update(f"página {feito} de {total}", feito=feito, total=total)


def estados_do_trilho(resultado: Any, pdf: Path | None, page_count: int) -> tuple[list[Any], str]:
    """Os estados por página e a frase do resumo, pela regra da suíte (`caissa.ui.trilho`)."""
    from caissa.ocr.review import ReviewDecisions
    from caissa.ui import trilho

    decisoes = ReviewDecisions.for_pdf(pdf) if pdf is not None else None
    estados = trilho.estados(resultado.report, decisions=decisoes, page_count=page_count)
    return estados, trilho.resumo_pt(estados, resultado.report)
