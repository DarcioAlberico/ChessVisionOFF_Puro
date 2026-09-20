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

**Um só OCR do livro (OCR_UI ciclo 2, passo C7; análise §6.4).** A aba *Revisão de texto* tinha o
próprio importador e lia o livro de novo para montar a fila de dúvidas; a `Ponte` passa a entregar
o `ImportResult` a ela (`receber_importacao`) assim que ele chega, e `importacoes` conta quantas
vezes o OCR do livro rodou -- é o número que o teste da janela afirma ser **1** ao revisar.

**E o documento pronto para a exportação (passo A3).** `documento_para(paginas)` devolve o
`ImportResult` quando as páginas pedidas cabem nas importadas e a importação não foi cancelada,
para a exportação pelo trilho não reimportar o livro. `caissa.export.book.export_book(document=)`
já o aceita; quem ainda não o passa é `caissa.ui.views.exportacao.ExportadorDeLivro`, e é ali (e
em `janela._exportar_livro`) que o fio se fecha.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
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
        revisao_de_texto: Any = None,
    ) -> None:
        self.importador = importador
        self._trilho = trilho
        self._pdf_atual = pdf_atual
        self._paginas = paginas
        self._dizer = dizer
        self._revisao_de_texto = revisao_de_texto
        """A aba *Revisão de texto* da suíte, se montada: recebe o `ImportResult` (C7)."""
        self.resultado: Any = None
        """O `ImportResult` da última importação (inteira ou parcial) do livro aberto."""
        self.importacoes = 0
        """Quantas importações (OCR do livro) esta ponte começou. Uma por livro é a promessa de C7."""
        self._pdf_importado: Path | None = None
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
            self.importacoes += 1
            self._pdf_importado = Path(pdf)
            self._trilho.importacao_comecou(2 * quantas)

    def cancelar(self) -> None:
        if self.importador.rodando:
            self.importador.cancelar()

    def _chegou(self, resultado: object) -> None:
        """O relatório da importação (inteiro ou parcial) vira o estado das páginas no trilho."""
        self._trilho.importacao_terminou()
        pdf = self._pdf_importado
        if pdf is None or resultado is None:
            return
        if pdf != self._pdf_atual():
            # O livro mudou enquanto o OCR corria (a janela cancela ao abrir outro, mas o
            # último relatório ainda chega): não é deste livro, não vira trilho nem fila.
            self._dizer(f"A importação de {pdf.name} terminou depois de o livro mudar; descartada.")
            self.resultado = None
            return
        self.resultado = resultado
        if not getattr(resultado.report, "canceled", False):
            # Uma importação cancelada é parcial: serve ao trilho, não à fila de revisão, que
            # substituiria a fila do livro inteiro pela de meio livro.
            self._entregar_a_revisao(resultado, pdf)
        try:
            estados, resumo = estados_do_trilho(resultado, pdf, self._paginas())
        except Exception:  # noqa: BLE001 - o trilho é mapa; sem ele o livro continua aberto
            logger.exception("O estado das páginas não pôde ser calculado.")
            return
        self._trilho.definir_estados(estados, resumo=resumo)

    def _entregar_a_revisao(self, resultado: Any, pdf: Path) -> None:
        """O resultado vai à aba de revisão, que monta a fila sem rodar o OCR de novo (C7)."""
        aba = self._revisao_de_texto
        receber = getattr(aba, "receber_importacao", None)
        if receber is None:
            return
        try:
            receber(resultado, pdf=pdf)
        except Exception:  # noqa: BLE001 - a fila de dúvidas é da aba; sem ela o trilho continua
            logger.exception("A aba Revisão de texto não recebeu a importação.")

    def documento_para(self, paginas: Sequence[int] | None) -> Any:
        """O `ImportResult` importado, se é **exatamente** `paginas` (base 0; `None` = o livro
        inteiro) e é deste livro; senão `None` (A3). É o que `caissa.export.book.export_book(document=)` aceita
        -- o resultado inteiro, para o relatório da importação viajar junto. Uma importação
        cancelada não cobre nada: o parcial serve ao trilho, mas exportar por ele gravaria um
        livro pela metade dizendo que é inteiro."""
        resultado = self.resultado
        if resultado is None or getattr(resultado.report, "canceled", False):
            return None
        if self._pdf_importado != self._pdf_atual():
            return None
        importadas = set(_paginas_importadas(resultado))
        pedidas = set(range(self._paginas())) if paginas is None else {int(p) for p in paginas}
        # Exatamente as mesmas páginas, não um subconjunto: `export_book(document=)` escreve o
        # documento como está, e um livro de 3 páginas pedido como «página 1» sairia com as 3.
        if not pedidas or pedidas != importadas:
            return None
        return resultado


def _paginas_importadas(resultado: Any) -> list[int]:
    """Os índices (base 0) das páginas que o relatório diz ter montado (`PageReport.index`)."""
    relatorio = getattr(resultado, "report", None)
    paginas = getattr(relatorio, "pages", None) or ()
    indices: list[int] = []
    for pagina in paginas:
        indice = getattr(pagina, "index", None)
        if indice is None and isinstance(pagina, dict):
            indice = pagina.get("index")
        if indice is not None:
            indices.append(int(indice))
    return indices


def montar(
    pai: QWidget,
    *,
    dizer: Callable[[str], Any],
    trancar: Callable[[bool], Any],
    ocupado: BusyRegistry | None = None,
    trilho: Any = None,
    pdf_atual: Callable[[], Path | None] = lambda: None,
    paginas: Callable[[], int] = lambda: 0,
    revisao_de_texto: Any = None,
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
    return Ponte(
        importador, trilho, pdf_atual=pdf_atual, paginas=paginas, dizer=dizer, revisao_de_texto=revisao_de_texto
    )


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
