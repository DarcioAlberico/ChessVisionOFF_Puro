"""O índice por nome construído de dentro da janela, com barra e botão Cancelar (S-532).

**Por que ele existe.** Até aqui o índice era `cvoff-games --build-index`, um comando de terminal
de minutos, e a janela só sabia dizer *"se o índice ainda não foi construído: cvoff-games
--build-index"* (`qt/dialogos.py`). Quem acrescenta um torneio à pasta e volta à sala de estudo
descobre que a busca por nome recusou o índice -- e a saída era abrir um terminal.

**O que ele faz.** Roda `games_index.build_index` numa `Tarefa` (o `QThread` de `qt/trabalho.py`),
com o progresso voltando por **sinal** -- o `progress` do índice é chamado na thread de trabalho,
e um `QThread` que tocasse widget direto derrubaria o processo sem exceção. O `cancel` é um
`threading.Event` que o botão Cancelar liga; o índice o confere a cada 16 mil linhas e desfaz só
o arquivo em curso, então cancelar não perde o que já foi gravado.

**O que ele não decide.** A frase da barra, a régua por mil e a resposta a "perde trabalho ao
fechar?" são de `ui/indice_da_base.py`. Aqui é a fiação: sinal, thread, diálogo.

**Quem o chama.** Um `connect` na sala de estudo ou no menu -- `indexar_com_dialogo(janela,
bases)` -- e nada mais: o módulo não conhece painel nenhum.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QProgressDialog, QWidget

from chess_diagram_ocr.games_db import nome_da_base, tamanho_da_base
from chess_diagram_ocr.games_index import DEFAULT_INDEX_PATH, Indexacao, build_index
from chess_diagram_ocr.qt.trabalho import Tarefa
from chess_diagram_ocr.ui.busy import BusyRegistry, BusyToken
from chess_diagram_ocr.ui.indice_da_base import (
    POR_MIL,
    Andamento,
    frase_de_fim,
    frase_de_progresso,
    perde_trabalho_ao_fechar,
)

logger = logging.getLogger(__name__)

__all__ = ["IndexadorDaBase", "frase_final", "indexar_com_dialogo"]


class IndexadorDaBase(QObject):
    """Constrói o índice numa thread e conta o andamento por sinal.

    `progresso(nome, bytes_lidos, bytes_totais, partidas)` chega de qualquer arquivo, até dez
    vezes por segundo; `avancou(por_mil)` é o mesmo aviso já somado sobre o conjunto, pronto para
    uma barra. `terminou(Indexacao)` e `falhou(mensagem, exceção)` são os dois fins possíveis, e
    exatamente um deles chega.
    """

    progresso = pyqtSignal(str, int, int, int)
    avancou = pyqtSignal(int)
    terminou = pyqtSignal(object)
    falhou = pyqtSignal(str, object)

    def __init__(self, parent: QObject | None = None, *, busy: BusyRegistry | None = None) -> None:
        super().__init__(parent)
        self._tarefa: Tarefa | None = None
        self._cancelar = threading.Event()
        self._busy = busy
        self._token: BusyToken | None = None
        self._andamento = Andamento({})
        self.resultado: Indexacao | None = None
        """O que a última rodada fez; `None` enquanto nenhuma terminou."""
        self.dialogo: QProgressDialog | None = None
        """O diálogo em cima desta rodada, se `indexar_com_dialogo` o montou. Volta a `None`
        quando ele fecha -- depois disso o widget já foi marcado para destruição."""
        # A soma e feita neste lado da fronteira de thread: `progresso` e emitido na thread de
        # trabalho, e o slot roda na thread deste objeto -- a da interface.
        self.progresso.connect(self._somar)

    @property
    def ocupado(self) -> bool:
        return self._tarefa is not None

    def iniciar(self, bases: Sequence[Path], caminho: Path = DEFAULT_INDEX_PATH) -> bool:
        """Começa a rodada. Devolve falso se já há uma em curso -- duas escreveriam no mesmo arquivo."""
        if self._tarefa is not None:
            return False
        lista = [Path(base) for base in bases]
        self._cancelar = threading.Event()
        self._andamento = Andamento({nome_da_base(base): tamanho_da_base(base) for base in lista})
        self.resultado = None
        cancelar = self._cancelar
        relatar = self._relatar

        def _trabalho() -> Indexacao:
            return build_index(lista, caminho, progress=relatar, cancel=cancelar)

        tarefa = Tarefa(_trabalho, parent=self, nome="índice da base de partidas")
        tarefa.pronto.connect(self._pronto)
        tarefa.falhou.connect(self._falhou)
        tarefa.finished.connect(self._terminou)
        self._registrar_ocupado(len(lista))
        self._tarefa = tarefa
        tarefa.start()
        return True

    def cancelar(self) -> None:
        """Pede para parar. O índice responde em menos de um segundo e desfaz só o arquivo em curso."""
        self._cancelar.set()

    def esperar(self, espera_ms: int) -> bool:
        """Espera a rodada em curso terminar. Devolve se terminou."""
        tarefa = self._tarefa
        return True if tarefa is None else bool(tarefa.wait(espera_ms))

    # --------------------------------------------------------------- da thread de trabalho

    def _relatar(self, base: Path, bytes_lidos: int, bytes_totais: int, partidas: int) -> None:
        # Chamado na thread de trabalho: so emite. Quem soma e mostra e o slot, do outro lado.
        self.progresso.emit(nome_da_base(base), bytes_lidos, bytes_totais, partidas)

    # ----------------------------------------------------------------- na thread da interface

    def _somar(self, nome: str, bytes_lidos: int, bytes_totais: int, _partidas: int) -> None:
        self.avancou.emit(self._andamento.registrar(nome, bytes_lidos, bytes_totais))
        if self._token is not None:
            self._token.update(nome, feito=self._andamento.por_mil, total=POR_MIL)

    def _pronto(self, resultado: Any) -> None:
        self.resultado = resultado
        self.terminou.emit(resultado)

    def _falhou(self, mensagem: str, excecao: object) -> None:
        logger.warning("O índice da base falhou: %s", mensagem)
        self.falhou.emit(mensagem, excecao)

    def _terminou(self) -> None:
        self._soltar_ocupado()
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.deleteLater()

    def _registrar_ocupado(self, quantas: int) -> None:
        if self._busy is None:
            return
        self._token = self._busy.register(
            "índice da base de partidas",
            loses_work=perde_trabalho_ao_fechar(),
            cancellable=True,
            detail=f"{quantas} arquivo(s)",
            total=POR_MIL,
            cancel=self.cancelar,
        )

    def _soltar_ocupado(self) -> None:
        if self._token is not None:
            self._token.release()
            self._token = None


def indexar_com_dialogo(
    parent: QWidget | None,
    bases: Sequence[Path],
    caminho: Path = DEFAULT_INDEX_PATH,
    *,
    busy: BusyRegistry | None = None,
    mostrar: bool = True,
) -> IndexadorDaBase:
    """Um `QProgressDialog` com Cancelar em cima de `IndexadorDaBase`. Devolve o indexador.

    O diálogo é **modal à janela** e não à aplicação: a pessoa não deve editar a sala enquanto o
    índice roda -- a busca por nome recusaria o índice em obras --, mas nada impede outra janela.
    Ele fecha sozinho no fim, e o rótulo final fica no `resultado` do indexador para quem quiser
    pô-lo no rodapé: `indexador.terminou.connect(lambda r: rodape.mostrar(frase_de_fim(...)))`.

    `mostrar=False` não chama `show()` -- é o caminho do teste sob `offscreen`. (Com
    `minimumDuration` em zero o `QProgressDialog` ainda se exibe sozinho no primeiro `setValue`;
    sem tela isso não custa nada, e o teste não afirma nada sobre visibilidade no meio.)
    """
    indexador = IndexadorDaBase(parent, busy=busy)
    dialogo = QProgressDialog("Conferindo os arquivos da base…", "Cancelar", 0, POR_MIL, parent)
    dialogo.setWindowTitle("Índice da base de partidas")
    dialogo.setWindowModality(Qt.WindowModality.WindowModal)
    dialogo.setMinimumDuration(0)
    dialogo.setAutoClose(False)
    dialogo.setAutoReset(False)
    dialogo.setMinimumWidth(420)
    dialogo.canceled.connect(indexador.cancelar)
    indexador.avancou.connect(dialogo.setValue)
    indexador.progresso.connect(
        lambda nome, lidos, total, partidas: dialogo.setLabelText(frase_de_progresso(nome, lidos, total, partidas))
    )

    def _fechar(*_ignorado: object) -> None:
        dialogo.close()
        dialogo.deleteLater()
        indexador.dialogo = None

    indexador.terminou.connect(_fechar)
    indexador.falhou.connect(_fechar)
    indexador.dialogo = dialogo
    if not indexador.iniciar(bases, caminho):
        _fechar()
        return indexador
    if mostrar:
        dialogo.show()
    return indexador


def frase_final(resultado: Indexacao) -> str:
    """A frase de `ui/indice_da_base.frase_de_fim` para um `Indexacao` -- o que vai ao rodapé."""
    return frase_de_fim(
        resultado.partidas,
        resultado.relidas,
        resultado.arquivos_relidos,
        resultado.arquivos_pulados,
        resultado.arquivos_removidos,
        resultado.cancelado,
    )
