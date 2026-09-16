"""O que está rodando agora, e o que se perde ao fechar a janela (S-60).

**O defeito.** `app_tkinter._on_close` gravava o estado, destruía o leitor WebView2 (que saiu
na S-69), fechava o motor de análise e chamava `root.destroy()`. Não perguntava nada. As oito threads do app
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
from dataclasses import dataclass, replace

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

    feito: int = 0
    total: int = 0
    """Quanto já foi e quanto é o todo, **quando a operação sabe** (S-164).

    Zero em `total` significa "não há total conhecido", e não "total zero": a busca por nome na
    base descobre o tamanho enquanto lê, e prometer uma fração ali seria inventá-la. O `detail`
    continua sendo o texto; estes dois são o número, e existem porque uma barra determinada não
    dá para derivar de "época 3 de 8" sem interpretar a frase.
    """

    @property
    def fracao(self) -> float | None:
        """Quanto da operação já foi, entre 0,0 e 1,0 — ou `None` sem total conhecido.

        Limitada a 1,0 de propósito: quem informa `feito` é a callback de progresso da operação,
        e uma contagem que passe do total (uma página relida numa retomada, por exemplo) daria
        uma barra além do fim em vez de um erro que ninguém veria.
        """
        if self.total <= 0:
            return None
        return max(0.0, min(1.0, self.feito / self.total))

    def describe(self) -> str:
        return f"{self.name} ({self.detail})" if self.detail else self.name


class BusyToken:
    """Handle devolvido por `register`. Solta o registro e atualiza o detalhe.

    Público desde a S-112, e o nome é o item: com sete pontos de registro em vez de dois, os
    `_busy_token: object | None` mais `# type: ignore[attr-defined]` que os dois primeiros
    usavam viravam sete cópias de um tipo apagado -- e um `release()` esquecido deixa a janela
    perguntando para sempre sobre uma operação que já acabou.
    """

    def __init__(self, registry: BusyRegistry, key: int) -> None:
        self._registry = registry
        self._key = key

    def update(self, detail: str, *, feito: int = 0, total: int = 0) -> None:
        """Atualiza onde a operação está: o texto e, quando ela sabe, o número (S-164)."""
        self._registry._update(self._key, detail, feito=feito, total=total)

    def release(self) -> None:
        self._registry._release(self._key)

    def __enter__(self) -> BusyToken:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class BusyRegistry:
    """As operações longas em curso. Escrito das threads de trabalho, lido da thread da UI."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._operations: dict[int, BusyOperation] = {}
        self._cancels: dict[int, Callable[[], None]] = {}
        self._observers: list[Callable[[], None]] = []
        self._next = 0

    # ------------------------------------------------------------------ quem quer saber já

    def observe(self, observador: Callable[[], None]) -> None:
        """Chama `observador()` sempre que o conjunto de operações muda (F9-C4).

        **O defeito que isto fecha, medido numa das 36 capturas.** O rodapé lia o registro por
        relógio, a cada `estado_do_rodape.INTERVALO_DE_ACOMPANHAMENTO_MS` = **400 ms**, e a zona de
        mensagem é escrita por sinal direto no instante em que a operação começa. As duas zonas são
        do mesmo rodapé e discordavam por até 400 ms: em
        `benchmarks/reports/ui/c4/c4_claro_1280x800_dataset.png` o rodapé diz **"Lendo o
        dataset…"** com a **barra escondida** e o **`Cancelar` desabilitado** -- que é, palavra por
        palavra, o sintoma com que o defeito bloqueante nº 2 do ciclo 3 reprovou o ciclo 2, agora
        reduzido a uma janela de 400 ms e ainda assim visível em 1 de 36 capturas.

        **O relógio não sai, e o motivo é o da S-112:** um `release()` esquecido deixaria a barra
        girando para sempre, e é por isso que o rodapé pergunta em vez de esperar aviso. O aviso
        fecha a janela de 400 ms; o relógio continua sendo a rede.

        **Sem toolkit, e a assinatura é o que garante isso:** o observador não recebe argumento
        nenhum -- ele é um "algo mudou, releia". Quem sabe em que thread o registro foi escrito, e
        como pular daí para a da janela, é `qt/`; aqui não há como uma decisão depender disso.
        """
        with self._lock:
            self._observers.append(observador)

    def _avisar(self) -> None:
        """Avisa os observadores, **fora do lock** e sem deixar um derrubar o outro.

        Fora do lock porque um observador que perguntasse `running()` de dentro dele travaria com
        um `Lock` simples -- o `RLock` salva a mesma thread, não a de trabalho que registra
        enquanto a da janela lê. E cada aviso é isolado pelo mesmo motivo de `request_cancel`:
        avisar é best-effort e não pode derrubar quem registrou.
        """
        with self._lock:
            observadores = list(self._observers)
        for observador in observadores:
            try:
                observador()
            except Exception:  # pragma: no cover - o mesmo contrato de `request_cancel`
                logger.exception("Falha ao avisar um observador do registro de ocupação.")

    def register(
        self,
        name: str,
        *,
        loses_work: bool,
        cancellable: bool = False,
        detail: str = "",
        total: int = 0,
        cancel: Callable[[], None] | None = None,
    ) -> BusyToken:
        with self._lock:
            self._next += 1
            key = self._next
            self._operations[key] = BusyOperation(
                name=name,
                loses_work=loses_work,
                cancellable=cancellable and cancel is not None,
                detail=detail,
                total=total,
            )
            if cancel is not None:
                self._cancels[key] = cancel
        # Depois do `with`, e não dentro: ver `_avisar`.
        self._avisar()
        return BusyToken(self, key)

    def _update(self, key: int, detail: str, *, feito: int = 0, total: int = 0) -> None:
        mudou = False
        with self._lock:
            atual = self._operations.get(key)
            if atual is not None:
                # `replace` e não construir de novo: a S-32 registra o que custou reconstruir um
                # `dataclass` campo a campo -- o campo novo que ninguém copiou volta ao padrão, e
                # aqui isso apagaria o total a cada atualização de detalhe.
                self._operations[key] = replace(atual, detail=detail, feito=feito, total=total or atual.total)
                mudou = self._operations[key] != atual
        # Só quando **muda**: a barra determinada é atualizada por callback de progresso, e avisar
        # a cada tique idêntico faria o rodapé repintar sem nada novo para dizer.
        if mudou:
            self._avisar()

    def _release(self, key: int) -> None:
        with self._lock:
            saiu = self._operations.pop(key, None) is not None
            self._cancels.pop(key, None)
        if saiu:
            self._avisar()

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


FORA_DO_REGISTRO: dict[tuple[str, str], str] = {
    ("janela.py", "_rodar"): (
        "Marcar os diagramas e reconhecer a página -- as duas passam por aqui. É o laço interno "
        "do programa, limitado por `max_boards`, e o que ele produz aparece na tela: quem fecha "
        "a janela durante ele está desistindo do resultado, não perdendo trabalho gravado."
    ),
    ("trabalho.py", "_comecar"): (
        "A detecção dos diagramas da página que acabou de aparecer (S-68), ao fundo e sem "
        "trancar nada. Ninguém a pediu, ela custa décimos de segundo, e o que produz é um "
        "conjunto de retângulos que a próxima visita à página refaz."
    ),
    ("painel_de_estudo.py", "analyse"): (
        "Uma avaliação do motor sobre a posição na tela (S-33). Segundos, e derivada: a "
        "posição continua lá para pedir de novo."
    ),
    ("painel_do_pdf.py", "_executar"): (
        "Abrir o livro (contar as páginas) e rasterizar a página exibida, fora da thread da "
        "janela (OCR_UI passo 15). Décimos de segundo, e o rodapé já diz «Renderizando página "
        "N…» pela zona de mensagem; registrar faria a barra de progresso piscar a cada virada. "
        "Fechar no meio não perde nada: a página continua no PDF."
    ),
    ("visor.py", "_pedir_reescalonamento"): (
        "A página reduzida ao zoom novo, fora da thread da janela (OCR_UI passo 15). Quinze "
        "milissegundos, derivada da página que já está em memória, e a folha anterior fica na "
        "tela esticada enquanto ela não vem."
    ),
    ("painel_da_galeria.py", "_abrir_cache_de_posicoes"): (
        "Abrir o SQLite do cache de posições quando o livro abre (OCR_UI passo 15). Dezenas de "
        "milissegundos num disco frio; até chegar, o botão de candidatas fica apagado, que é o "
        "que ele já era sem cache. Fechar no meio não perde nada: é só uma conexão."
    ),
    ("trilho.py", "_proxima_miniatura"): (
        "Uma miniatura de página do trilho (OCR_UI passo 17), a 18 DPI, pelo processo de "
        "trabalho: alguns milissegundos cada, uma por vez, as visíveis primeiro. É enfeite -- a "
        "linha da página já existe sem ela --, e fechar no meio não perde nada."
    ),
}
"""As threads de `qt/` que **não** entram no registro, e por quê -- uma linha cada.

Perguntar "fechar mesmo assim?" por causa de uma análise de dois segundos treina o usuário a
responder "sim" sem ler, e aí ele responde "sim" também para a busca por posição, que custa
56 minutos. O registro só vale enquanto quem for avisado tiver motivo para parar.

**Uma thread nova em `qt/` falha a suíte até estar registrada ou declarada aqui** -- é o que a
S-60 não teve: ela cobriu as duas operações longas que existiam então, e as dez que vieram
depois entraram em silêncio. `tests/test_busy.py` é quem cobra.

---

**Por que esta tabela mudou de `tests/test_busy.py` para cá no F9-C3, e por que ela encolheu.**

Ela morava só no teste, e por isso **só o teste** a enxergava. O ciclo 2 pôs aqui as duas leituras
assíncronas que criou (`marcas.pedir` e `painel_do_dataset._reler_agora`) com um motivo correto --
*"é leitura, fechar no meio não perde nada"* --, e o portão `caissa.ui.audit.progresso`, que varre
os pontos de chamada de `register`, **não tinha como ver nem uma nem outra**: uma operação que
nunca se registra é invisível para quem procura registros. O usuário via o resultado: com a
leitura correndo, o rodapé escrevia "Lendo o dataset…" e a barra ao lado ficava em 0 de 100 com o
`Cancelar` cinzento.

A declaração responde *"perde trabalho ao fechar?"*. Ela **não** responde *"precisa de indicação
de progresso?"* -- são duas perguntas, e as duas leituras tinham respostas opostas. As duas
registram desde o F9-C3, e por isso saíram desta tabela: cinco entradas viraram três.

Aqui, em `ui/`, ela é a decisão que o teste cobra **e** que o arnês lê -- e um portão que não
enxerga a operação que ele existe para achar deixa de ser possível."""
