"""Toda entrada modal do Qt, trocada na suíte por um substituto que anota e não espera (S-414, S-872).

**O defeito.** Sob `QT_QPA_PLATFORM=offscreen` uma caixa modal **abre**, e o laço aninhado dela espera
para sempre por um clique que ninguém vai dar: sem tempo limite, sem mensagem, e sem nomear o teste,
porque o `-v` já imprimiu o nome do anterior. Até 2026-11-09 o `conftest` desarmava só os cinco
atalhos estáticos do `QMessageBox`; a caixa de falha da aba Texto (`qt/dialogos.mostrar_falha`) monta
um `QMessageBox` e chama o `exec()` **da instância**, que passava por fora -- e a integração da
solidez parou dentro de `tests/test_qt_texto_prosa.py` esperando esse clique.

**A troca é na entrada do laço, e não nas funções do projeto.** Toda caixa do programa termina numa
destas: `QDialog.exec` (que o `QMessageBox`, o `QFileDialog`, o `QInputDialog`, o
`QPrintPreviewDialog` e os diálogos de `qt/dialogos.py` herdam), o `exec` próprio do `QPrintDialog`,
do `QPageSetupDialog` e do `QMenu`, e os atalhos estáticos do `QMessageBox`, do `QFileDialog`, do
`QInputDialog`, do `QColorDialog` e do `QFontDialog`. Trocar `dialogos.mostrar_falha` também seria
trocar duas vezes a mesma decisão, e não pegaria quem a importou por nome antes da troca.

**O substituto anota e devolve a resposta de quem fecha a caixa sem escolher** (`Rejected`, `NoButton`,
nome de arquivo vazio, `ok=False`). Ele não levanta: a caixa de falha da aba Texto é aberta por um
slot, e exceção em slot do PyQt6 é `qFatal` -- o processo do pytest morreria sem rastro, que é pior
do que travar. Quem reprova é a fixture do `conftest`, na desmontagem do teste, com a mensagem que a
caixa mostraria e a linha que a abriu.

**O remendo do teste vence.** O `mock.patch.object(QMessageBox, "question", ...)` do próprio teste é
aplicado depois da fixture, por cima do substituto, e desfeito antes dela; é o que a suíte já faz em
dezenas de lugares, e é como se diz qual resposta a pessoa daria.
"""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ESTE_ARQUIVO = Path(__file__).resolve()


@dataclass(frozen=True)
class Abertura:
    """Uma caixa que teria aberto: por onde (`QMessageBox.exec`), o que diria e quem chamou."""

    entrada: str
    mostraria: str
    onde: str

    def descrita(self) -> str:
        return f"`{self.entrada}` ({self.mostraria}) em {self.onde}"


_ABERTAS: list[Abertura] = []
_TRAVA = threading.Lock()


def recolher() -> list[Abertura]:
    """As aberturas anotadas desde a última recolha, e a lista esvaziada."""
    with _TRAVA:
        abertas = list(_ABERTAS)
        _ABERTAS.clear()
    return abertas


def _quem_chamou() -> str:
    """As três últimas linhas da pilha fora deste arquivo e do pytest: a do programa e a do teste."""
    pilha = [
        quadro
        for quadro in traceback.extract_stack()
        if Path(quadro.filename).resolve() != ESTE_ARQUIVO and "site-packages" not in quadro.filename
    ]
    return " <- ".join(f"{Path(q.filename).name}:{q.lineno} {q.name}" for q in reversed(pilha[-3:]))


def _anotar(entrada: str, mostraria: str) -> None:
    with _TRAVA:
        _ABERTAS.append(Abertura(entrada, mostraria, _quem_chamou()))


def _frase(*partes: object) -> str:
    return " | ".join(repr(str(parte)) for parte in partes if parte) or "sem texto"


def _o_que_o_widget_mostra(widget: object) -> str:
    from PyQt6.QtWidgets import QMenu, QMessageBox, QWidget

    if isinstance(widget, QMessageBox):
        return _frase(widget.windowTitle(), widget.text(), widget.informativeText(), widget.detailedText())
    if isinstance(widget, QMenu):
        return _frase(*(acao.text() for acao in widget.actions()))
    if isinstance(widget, QWidget):
        return _frase(type(widget).__name__, widget.windowTitle())
    return _frase(type(widget).__name__)


def _exec_de_instancia(entrada: str, resposta: object) -> Callable[..., object]:
    def exec_(self: object, *args: object, **kwargs: object) -> object:
        _anotar(entrada, _o_que_o_widget_mostra(self))
        return resposta

    return exec_


def _atalho(entrada: str, resposta: Callable[[], object], titulo_em: int = 1) -> staticmethod:
    """Os estáticos recebem `(pai, título, texto, ...)`; o título e o texto são o que a pessoa leria."""

    def atalho(*args: object, **kwargs: object) -> object:
        textos = list(args[titulo_em : titulo_em + 2])
        textos += [kwargs[chave] for chave in ("title", "caption", "text", "label") if chave in kwargs]
        _anotar(entrada, _frase(*textos))
        return resposta()

    return staticmethod(atalho)


def substitutos() -> dict[tuple[type, str], object]:
    """(classe, atributo) → substituto. Importa o Qt: só é chamado com o PyQt6 presente."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QColor, QFont
    from PyQt6.QtPrintSupport import QPageSetupDialog, QPrintDialog
    from PyQt6.QtWidgets import QColorDialog, QDialog, QFileDialog, QFontDialog, QInputDialog, QMenu, QMessageBox

    rejeitado = int(QDialog.DialogCode.Rejected.value)
    tabela: dict[tuple[type, str], object] = {
        (QDialog, "exec"): _exec_de_instancia("QDialog.exec", rejeitado),
        (QPrintDialog, "exec"): _exec_de_instancia("QPrintDialog.exec", rejeitado),
        (QPageSetupDialog, "exec"): _exec_de_instancia("QPageSetupDialog.exec", rejeitado),
        (QMenu, "exec"): _exec_de_instancia("QMenu.exec", None),
    }
    for nome in ("information", "warning", "critical", "question"):
        tabela[(QMessageBox, nome)] = _atalho(f"QMessageBox.{nome}", lambda: QMessageBox.StandardButton.NoButton)
    for nome in ("about", "aboutQt"):
        tabela[(QMessageBox, nome)] = _atalho(f"QMessageBox.{nome}", lambda: None)
    vazios: dict[str, Callable[[], object]] = {
        "getOpenFileName": lambda: ("", ""),
        "getOpenFileNames": lambda: ([], ""),
        "getSaveFileName": lambda: ("", ""),
        "getExistingDirectory": lambda: "",
        "getOpenFileUrl": lambda: (QUrl(), ""),
        "getOpenFileUrls": lambda: ([], ""),
        "getSaveFileUrl": lambda: (QUrl(), ""),
        "getExistingDirectoryUrl": lambda: QUrl(),
    }
    for nome, resposta in vazios.items():
        tabela[(QFileDialog, nome)] = _atalho(f"QFileDialog.{nome}", resposta)
    desistencias: dict[str, Callable[[], object]] = {
        "getText": lambda: ("", False),
        "getMultiLineText": lambda: ("", False),
        "getItem": lambda: ("", False),
        "getInt": lambda: (0, False),
        "getDouble": lambda: (0.0, False),
    }
    for nome, resposta in desistencias.items():
        tabela[(QInputDialog, nome)] = _atalho(f"QInputDialog.{nome}", resposta)
    tabela[(QColorDialog, "getColor")] = _atalho("QColorDialog.getColor", QColor, titulo_em=2)
    tabela[(QFontDialog, "getFont")] = _atalho("QFontDialog.getFont", lambda: (QFont(), False), titulo_em=2)
    return tabela


class Desarme:
    """Instala os substitutos, os reinstala a cada teste e devolve os originais no fim da sessão.

    **Reinstalar a cada teste** custa ~30 `setattr` e desfaz o remendo que um teste esqueceu de
    desfazer: sem isso um `setattr(QMessageBox, "exec", falso)` sem limpeza responderia por todos os
    testes seguintes, e uma caixa nova passaria calada neles.
    """

    def __init__(self) -> None:
        self._tabela = substitutos()
        self._originais = {(classe, nome): vars(classe)[nome] for classe, nome in self._tabela}

    def armar(self) -> None:
        for (classe, nome), substituto in self._tabela.items():
            setattr(classe, nome, substituto)

    def desarmar(self) -> None:
        for (classe, nome), original in self._originais.items():
            setattr(classe, nome, original)
