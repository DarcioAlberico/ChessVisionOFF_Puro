"""O que está rodando agora, e o que se perde ao fechar a janela (S-60).

**O defeito.** `app_tkinter._on_close` gravava o estado, destruía o leitor WebView2, fechava
o motor de análise e chamava `root.destroy()`. Não perguntava nada. As oito threads do app
são `daemon=True` e nenhuma é aguardada, então um treino de ~9 min por época em CPU, ou uma
exportação de um livro de 1.121 páginas, morria no `destroy` sem uma palavra.

Pior: o treino **não tinha cancelamento**, então fechar a janela era o único jeito de
pará-lo -- e é o jeito que podia corromper o `.pt`, pela S-57.

**Por que um registro e não um par de flags.** `ExportController` e `TrainingController` já
sabem se estão rodando (`is_running`), e a janela poderia perguntar aos dois. Mas a resposta
que importa não é "está rodando", é **"o que se perde se eu fechar agora"** -- e isso varia:
a exportação tem checkpoint parcial (S-24) e sobrevive, o treino perde o progresso desde a
última época melhor. Quem sabe disso é quem registra, não quem pergunta.

Sem `tkinter` de propósito: é a regra da Fase 6, e aqui ela tem consequência concreta --
a decisão de o que dizer ao usuário fica testável sem abrir janela.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BusyOperation:
    """Uma operação longa em curso, e o que fechar a janela custaria."""

    name: str
    """Como ela aparece na pergunta. Em pt-BR e no vocabulário do usuário."""

    loses_work: bool
    """Fechar agora descarta trabalho que não dá para recuperar automaticamente."""

    cancellable: bool = False
    """Existe um caminho de cancelamento limpo -- ver `BusyRegistry.request_cancel`."""

    detail: str = ""
    """Onde ela está, para a pergunta dizer "época 3 de 8" em vez de só "um treino"."""

    def describe(self) -> str:
        return f"{self.name} ({self.detail})" if self.detail else self.name


class _Token:
    """Handle devolvido por `register`. Solta o registro e atualiza o detalhe."""

    def __init__(self, registry: BusyRegistry, key: int) -> None:
        self._registry = registry
        self._key = key

    def update(self, detail: str) -> None:
        self._registry._update(self._key, detail)

    def release(self) -> None:
        self._registry._release(self._key)

    def __enter__(self) -> _Token:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class BusyRegistry:
    """As operações longas em curso. Escrito das threads de trabalho, lido da thread da UI."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._operations: dict[int, BusyOperation] = {}
        self._cancels: dict[int, Callable[[], None]] = {}
        self._next = 0

    def register(
        self,
        name: str,
        *,
        loses_work: bool,
        cancellable: bool = False,
        detail: str = "",
        cancel: Callable[[], None] | None = None,
    ) -> _Token:
        with self._lock:
            self._next += 1
            key = self._next
            self._operations[key] = BusyOperation(
                name=name, loses_work=loses_work, cancellable=cancellable and cancel is not None, detail=detail
            )
            if cancel is not None:
                self._cancels[key] = cancel
        return _Token(self, key)

    def _update(self, key: int, detail: str) -> None:
        with self._lock:
            atual = self._operations.get(key)
            if atual is not None:
                self._operations[key] = BusyOperation(
                    name=atual.name, loses_work=atual.loses_work, cancellable=atual.cancellable, detail=detail
                )

    def _release(self, key: int) -> None:
        with self._lock:
            self._operations.pop(key, None)
            self._cancels.pop(key, None)

    def running(self) -> list[BusyOperation]:
        with self._lock:
            return list(self._operations.values())

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return bool(self._operations)

    def request_cancel(self) -> int:
        """Pede o cancelamento de tudo que sabe cancelar. Devolve quantas foram avisadas."""
        with self._lock:
            cancels = list(self._cancels.values())
        for cancel in cancels:
            try:
                cancel()
            except Exception:  # pragma: no cover - cancelar é best-effort, não pode derrubar o fechamento
                logger.exception("Falha ao pedir cancelamento de uma operação longa.")
        return len(cancels)

    def close_warning(self) -> str:
        """A pergunta de fechamento, ou `""` quando não há por que perguntar.

        Nomeia o que está rodando e o que se perde. Operação com checkpoint próprio (a
        exportação, S-24) entra na lista sem a frase de perda: fechar durante ela custa
        tempo, não trabalho, e dizer o contrário treinaria o usuário a ignorar o aviso.
        """
        operacoes = self.running()
        if not operacoes:
            return ""

        linhas = [
            "Uma operação ainda está em andamento:"
            if len(operacoes) == 1
            else f"{len(operacoes)} operações ainda estão em andamento:",
            "",
        ]
        linhas.extend(f"  - {operacao.describe()}" for operacao in operacoes)
        linhas.append("")

        perde = [operacao for operacao in operacoes if operacao.loses_work]
        if perde:
            nomes = ", ".join(operacao.name for operacao in perde)
            linhas.append(f"Fechar agora descarta o progresso de: {nomes}.")
        else:
            linhas.append("O progresso já está salvo; fechar agora só interrompe.")

        linhas.append("")
        linhas.append("Fechar mesmo assim?")
        return "\n".join(linhas)
