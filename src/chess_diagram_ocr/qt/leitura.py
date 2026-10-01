"""A leitura da página como operação com progresso, cancelamento e aquecimento (OCR_UI ciclo 2, C2).

Três coisas que `qt/janela.py` fazia às cegas, medidas na análise do ciclo 2 (§6.3):

* **Progresso.** `_rodar` estava em `FORA_DO_REGISTRO`: o rodapé mostrava a frase e nem barra nem
  «Cancelar». Agora a tarefa se registra com `total` = os diagramas já marcados na página, e o
  serviço avisa diagrama a diagrama (`recognize_page(progress=)`).
* **Cancelamento.** `Tarefa.cancelar` acende um `Event` que o serviço consulta antes de cada
  diagrama; o que já foi lido volta em `RecognitionCanceled.partial` e fica na lista.
* **Aquecimento.** O primeiro «Ler» de uma sessão pagava a carga do `.pt`; ela passa a correr numa
  `Tarefa` própria assim que um livro abre -- fora de `_rodar`, que só admite uma tarefa por vez
  e recusaria o «Ler» enquanto aquece. Um «Ler» que chegue no meio espera no lock do serviço.

Mora aqui, e não na janela, pela catraca de `tests/test_packaging.py`: a janela chama; a
mecânica -- a ficha do rodapé, o gancho de cancelar, a frase do modelo ausente -- fica num lugar
que se testa sem janela.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject

from chess_diagram_ocr.qt.trabalho import Tarefa, manter_viva
from chess_diagram_ocr.ui import estado_do_rodape
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken

logger = logging.getLogger(__name__)

__all__ = ["Aquecimento", "ESPERA_PARA_AQUECER_MS", "FRASE_SEM_MODELO", "Ocupacao", "frase_de_cancelamento", "sem_modelo"]

FRASE_SEM_MODELO = "Modelo de casas não encontrado. Aponte o arquivo .pt em Ferramentas ▸ Configurações…"
"""O que o rodapé diz quando o `.pt` falta: onde se resolve, e não só o nome do arquivo."""


def sem_modelo(excecao: object) -> bool:
    """A falha é o `.pt` ausente? É a única que a caixa de erro não deve mostrar como pilha."""
    return isinstance(excecao, FileNotFoundError) and "piece_classifier" in str(excecao)


def frase_de_cancelamento(lidos: int) -> str:
    return (
        f"Leitura cancelada: {lidos} diagrama(s) lido(s) ficaram na lista."
        if lidos
        else "Leitura cancelada antes do primeiro diagrama."
    )


class Ocupacao:
    """A ficha de uma tarefa no rodapé: registrada ao começar, atualizada pelo progresso, solta ao fim.

    `progresso` é o gancho que vai ao serviço, chamado da thread da tarefa -- o registro é seguro
    entre threads, e o rodapé relê por aviso e por relógio (`BusyRegistry.observe`).
    """

    def __init__(self, busy: BusyRegistry) -> None:
        self._busy = busy
        self._ficha: BusyToken | None = None

    def registrar(self, tarefa: Tarefa, *, nome: str, aviso: str, total: int, cancelavel: bool) -> None:
        """Registra a tarefa. A janela prefere `guardar(self.busy.register(...))`: o portão
        `caissa.ui.audit.progresso` atribui cada thread ao `register` feito na mesma função."""
        self.guardar(self._busy.register(
            nome,
            loses_work=False,
            cancellable=cancelavel,
            cancel=tarefa.cancelar if cancelavel else None,
            detail=aviso,
            total=total,
        ))

    def guardar(self, ficha: BusyToken) -> None:
        self.soltar()
        self._ficha = ficha

    def progresso(self, rotulo: str) -> Callable[[int, int], None]:
        """`progress(feito, total)` para `OcrService.recognize_page`, com a frase do rodapé."""

        def avancar(feito: int, total: int) -> None:
            ficha = self._ficha
            if ficha is not None:
                ficha.update(f"{rotulo}: {feito} de {total} diagrama(s)", feito=feito, total=total)

        return avancar

    def soltar(self) -> None:
        ficha, self._ficha = self._ficha, None
        if ficha is not None:
            ficha.release()

    @property
    def registrada(self) -> bool:
        return self._ficha is not None


ESPERA_PARA_AQUECER_MS = 3000
"""Quanto o aquecimento espera depois de o livro abrir, e entre tentativas com a janela ocupada.

**Medido pelo portão `bloqueio` (2026-09-21, Kemeri):** o aquecimento disparado no instante da
abertura punha ~30–80 ms de bloqueio na thread da janela sobre «abrir PDF» e a primeira virada
de página -- a carga do `.pt` é C que segura o GIL (torch + CUDA), e uma thread não a esconde.
Adiada para quando nada está sendo pedido (nenhuma tarefa nem operação registrada), a mesma
carga acontece uma vez, fora de qualquer gesto medido; um «Ler» que chegue antes dela paga a
carga como sempre pagou."""


class Aquecimento:
    """Carrega o modelo de casas ao fundo, uma vez por processo, dizendo no rodapé se ele falta."""

    def __init__(self, servico: Any, busy: BusyRegistry, *, dizer: Callable[[str, str], None],
                 ocupada: Callable[[], bool] | None = None) -> None:
        self._servico = servico
        self._busy = busy
        self._dizer = dizer
        self._ocupada = ocupada or (lambda: False)
        self._feito = False
        self._tarefa: Tarefa | None = None
        self._relogio: Any = None
        self._parent: QObject | None = None
        self._ms = ESPERA_PARA_AQUECER_MS
        self._cancelado = False

    @property
    def em_curso(self) -> bool:
        return self._tarefa is not None

    @property
    def concluido(self) -> bool:
        """A carga já correu (bem ou mal) nesta sessão -- o que o portão `--frio` espera."""
        return self._feito and self._tarefa is None

    def esperar(self, ms: int) -> bool:
        """Espera a carga em curso ao fechar a janela: um `QThread` filho destruído a correr
        derruba o processo. `True` quando não há carga ou ela terminou a tempo."""
        tarefa = self._tarefa
        if tarefa is None:
            return True
        try:
            return bool(tarefa.wait(ms))
        except RuntimeError:  # pragma: no cover - a tarefa já foi destruída pelo Qt
            return True

    def agendar(self, parent: QObject | None = None, *, ms: int = ESPERA_PARA_AQUECER_MS) -> None:
        """Aquece quando a janela estiver ociosa há `ms`: cada gesto que a janela anuncia
        (`adiar`, chamado ao virar a página) reinicia a contagem, e uma tarefa ou operação
        registrada em curso adia mais uma vez."""
        from PyQt6.QtCore import QTimer

        if self._feito or self._cancelado or not callable(getattr(self._servico, "load", None)):
            return
        if self._relogio is None:
            self._relogio = QTimer(parent)
            self._relogio.setSingleShot(True)
            self._relogio.timeout.connect(self._tentar)
        self._parent = parent
        self._ms = ms
        self._relogio.start(ms)

    def adiar(self) -> None:
        """A janela acabou de fazer algo (virar a página): a contagem de ócio recomeça."""
        if self._relogio is not None and not self._feito and not self._cancelado:
            self._relogio.start(self._ms)

    def cancelar(self) -> None:
        """A janela fechou: o que estava agendado não dispara mais.

        Uma janela fechada mas ainda não destruída (o `deleteLater` espera o laço de eventos)
        guardava um relógio armado, e ele disparava o aquecimento **depois** do fecho, numa
        janela morta -- o portão de execução da suíte do tronco acusou duas threads que
        nenhum ponto explicava. Fechar cancela; `adiar` e `_tentar` respeitam o cancelamento.
        """
        self._cancelado = True
        if self._relogio is not None:
            self._relogio.stop()

    def _tentar(self) -> None:
        if self._feito or self._cancelado:
            return
        if self._ocupada() or self._busy.running():
            self._relogio.start(self._ms) if self._relogio is not None else None
            return
        self.iniciar(self._parent)

    def iniciar(self, parent: QObject | None = None) -> Tarefa | None:
        carregar = getattr(self._servico, "load", None)
        if self._feito or self._tarefa is not None or not callable(carregar):
            return None   # um serviço sem `load` (o falso dos testes) não tem o que aquecer
        self._feito = True
        ficha = self._busy.register(
            "aquecendo o modelo", loses_work=False, detail=str(getattr(self._servico, "model_path", ""))
        )
        # **Sem pai** (`manter_viva`, F9-C2): filha da janela, a `Tarefa` seria destruída com ela
        # e o destrutor de `QThread` aborta o processo com a thread a correr -- o `closeEvent`
        # espera `ESPERA_AO_FECHAR_MS`, mas uma carga que passe disso (disco frio, CUDA) não
        # pode derrubar quem fecha. `parent` fica na assinatura por compatibilidade e não é usado.
        del parent
        tarefa = manter_viva(Tarefa(carregar, nome="aquecimento do modelo"))

        def terminou() -> None:
            ficha.release()
            self._tarefa = None

        def falhou(mensagem: str, _excecao: object) -> None:
            logger.warning("O modelo não aqueceu: %s", mensagem)
            nome = getattr(getattr(self._servico, "model_path", None), "name", "") or "piece_classifier.pt"
            try:
                self._dizer(
                    f"Modelo de casas indisponível ({nome}): aponte o arquivo .pt em Ferramentas ▸ Configurações…",
                    estado_do_rodape.AVISO,
                )
            except RuntimeError:   # a janela já fechou: o aviso ficou no log, que é o que resta
                logger.warning("A janela fechou antes de o aviso do modelo chegar ao rodapé.")

        tarefa.falhou.connect(falhou)
        tarefa.finished.connect(terminou)
        self._tarefa = tarefa
        tarefa.start()
        return tarefa
