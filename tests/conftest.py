"""Diagnóstico do ambiente antes da coleta (S-37).

**O defeito que isto evita.** O projeto foi movido de `C:\\PythonChess\\ChessVisionOFF_Puro`
para outro caminho e o `.venv` não foi ressincronizado. O `.pth` da instalação editável
continuou apontando para o diretório antigo, que não existia mais, e o resultado foi 33
módulos de teste falhando na **coleta** com `ModuleNotFoundError: No module named
'chess_diagram_ocr'`. Nada no repositório notou, e o sintoma parecia muito pior do que era:
o código estava inteiro, e com `PYTHONPATH=src` os 611 testes passavam.

**As duas guardas, e por que são duas.**

1. `pythonpath = ["src"]` no `pyproject.toml` faz a suíte rodar num checkout sem instalação
   nenhuma. É o que impede um diretório movido de desligar os testes.
2. Este `pytest_configure` cobre o que sobra. Se mesmo assim o pacote não for importável, a
   sessão para com **uma** mensagem que nomeia a causa provável -- em vez de 33 rastros de
   importação que não dizem o que fazer.

A primeira guarda sozinha esconderia metade do problema: a suíte passaria e os comandos
`cvoff-*` e o `app_tkinter.py` continuariam quebrados, porque eles dependem da instalação e
não do `sys.path` do pytest. É por isso que existe também o `tests/test_environment.py`.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from tkinter import messagebox

import pytest

PACOTE = "chess_diagram_ocr"
DISTRIBUICAO = "chessvisionoff-puro"
RAIZ = Path(__file__).resolve().parents[1]


def caminhos_pth_inexistentes() -> list[tuple[Path, str]]:
    """Linhas de arquivos `.pth` em `site-packages` que apontam para diretório que sumiu.

    É a assinatura exata de um projeto movido sem `uv sync`. Devolve `(arquivo, linha)` para
    que a mensagem possa mostrar o caminho morto em vez de só dizer que algo está errado.
    """
    quebrados: list[tuple[Path, str]] = []
    for entrada in sys.path:
        pasta = Path(entrada)
        if pasta.name != "site-packages" or not pasta.is_dir():
            continue
        for arquivo in sorted(pasta.glob("*.pth")):
            try:
                linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for linha in linhas:
                alvo = linha.strip()
                # Linhas de `.pth` que começam com `import` são código, não caminho.
                if not alvo or alvo.startswith(("#", "import ", "import\t")):
                    continue
                if not Path(alvo).exists():
                    quebrados.append((arquivo, alvo))
    return quebrados


def pytest_configure(config: pytest.Config) -> None:
    if importlib.util.find_spec(PACOTE) is not None:
        return

    linhas = [
        f"O pacote `{PACOTE}` não é importável, então nenhum teste pode ser coletado.",
        "",
    ]
    quebrados = caminhos_pth_inexistentes()
    if quebrados:
        linhas.append("Um arquivo de caminhos do ambiente aponta para diretório que não existe:")
        linhas.extend(f"    {arquivo.name}: {alvo}" for arquivo, alvo in quebrados)
        linhas.append("")
        linhas.append("O projeto foi movido depois de instalado. Para consertar:")
    else:
        linhas.append("O ambiente não tem o pacote instalado. Para consertar:")

    linhas.extend(["", f"    cd {RAIZ}", "    uv sync --extra dev", ""])
    raise pytest.UsageError("\n".join(linhas))

# ------------------------------------------------------------------ o que vaza de um teste (S-413)

ESPERA_POR_THREAD = 2.0
"""Segundos que uma thread de teste tem para terminar depois que o teste acabou.

Elas são de trabalho -- uma análise do motor, uma leitura de página --, e terminam sozinhas em
milissegundos com os dublês que a suíte usa. A espera existe para o caso normal, não para o
patológico: quem passar disto está vazando, e é o que se quer saber.
"""

THREADS_PERMITIDAS = ("pydevd", "asyncio", "ThreadPoolExecutor", "Dummy")
"""Threads que não são do programa: depurador, `asyncio` e o pool que o `pytest-xdist` usa."""


def _vivas(antes: frozenset[int]) -> list[threading.Thread]:
    return [
        t
        for t in threading.enumerate()
        if t.ident not in antes and t.is_alive() and not t.name.startswith(THREADS_PERMITIDAS)
    ]


@pytest.fixture(autouse=True)
def sem_thread_vazada(request: pytest.FixtureRequest) -> Iterator[None]:
    """Falha **no teste que a deixou**, e não no vizinho que a herdou (S-413).

    **O defeito que isto pega.** `test_estudo_aba` liga a análise contínua, que sobe uma thread de
    verdade com um motor de mentira. O teste termina, o `tearDown` destrói o painel, e a thread
    acorda depois para chamar `self.after(0, ...)` num widget que já não existe -- `TclError` de
    dentro de uma thread, que o `unittest` não vê e o pytest atribui a quem estiver rodando na
    hora. O rastro aparece **em outro arquivo**, e quem for investigar procura no lugar errado.

    A espera é a parte que faz isto não ser um teste instável: uma thread de trabalho termina
    sozinha, e o que se cobra é que ela **termine**, não que nunca tenha existido.
    """
    antes = frozenset(t.ident for t in threading.enumerate() if t.ident is not None)
    yield
    prazo = time.monotonic() + ESPERA_POR_THREAD
    while time.monotonic() < prazo and _vivas(antes):
        time.sleep(0.01)
    vazadas = [t.name for t in _vivas(antes)]
    if vazadas:
        pytest.fail(
            f"{request.node.name} deixou thread viva: {', '.join(sorted(vazadas))}. "
            "Espere o fim dela no próprio teste -- uma thread que sobrevive morre dentro do "
            "teste seguinte, e é lá que o rastro aparece."
        )


@pytest.fixture(autouse=True)
def erro_de_thread_e_do_teste_que_a_criou(request: pytest.FixtureRequest) -> Iterator[None]:
    """O que estourou numa thread reprova **este** teste (S-413).

    `threading.excepthook` é o único lugar onde isso aparece: o `unittest` não vê exceção de
    thread, e sem gancho ela vira duas linhas na saída padrão que ninguém liga a teste nenhum.
    """
    estouros: list[str] = []
    anterior = threading.excepthook

    def registrar(args: threading.ExceptHookArgs) -> None:
        estouros.append(f"{args.thread.name if args.thread else '?'}: {args.exc_type.__name__}: {args.exc_value}")
        anterior(args)

    threading.excepthook = registrar
    try:
        yield
    finally:
        threading.excepthook = anterior
    if estouros:
        pytest.fail(f"{request.node.name} deixou exceção em thread: {'; '.join(estouros)}")


# ------------------------------------------------------- a caixa modal que trava a suíte (S-414)

CAIXAS = ("showerror", "showwarning", "showinfo", "askyesno", "askokcancel", "askyesnocancel", "askquestion")
"""As sete do `tkinter.messagebox` que a interface usa. Ver `tests/test_ui_retorno_modal.py`."""


@pytest.fixture(autouse=True)
def nenhuma_caixa_modal_de_verdade() -> Iterator[None]:
    """Uma caixa aberta de verdade **para** a suíte, e nada a interrompia (S-414).

    **O caso medido:** um `TextoPanel` construído sem `pasta_de_rascunhos` lê `data/rascunhos/` da
    máquina de quem roda a suíte. Se houver um rascunho ali -- e há, na máquina de quem usa o
    programa --, a aba oferece recuperá-lo com um `askyesno`, e a suíte fica parada esperando um
    clique que ninguém vai dar. Sem tempo limite, sem mensagem, e o CI mataria a corrida por
    silêncio uma hora depois.

    Agora ela falha na hora, dizendo qual caixa e com que título. Quem **precisa** exercitar uma
    caixa continua podendo: `mock.patch.object(messagebox, "askyesno", ...)` no próprio teste
    sobrescreve isto, que é o que a suíte já faz em vinte lugares.
    """
    def recusar(nome: str) -> Callable[..., object]:
        def _recusa(*args: object, **kwargs: object) -> object:
            titulo = args[0] if args else kwargs.get("title", "?")
            raise AssertionError(
                f"caixa modal `{nome}` aberta durante o teste (título: {titulo!r}). Uma caixa de "
                "verdade trava a suíte esperando clique: finja-a com `mock.patch.object`, ou "
                "passe ao painel o que evita a pergunta (por exemplo `pasta_de_rascunhos=`)."
            )

        return _recusa

    originais = {nome: getattr(messagebox, nome) for nome in CAIXAS}
    for nome in CAIXAS:
        setattr(messagebox, nome, recusar(nome))
    try:
        yield
    finally:
        for nome, funcao in originais.items():
            setattr(messagebox, nome, funcao)
