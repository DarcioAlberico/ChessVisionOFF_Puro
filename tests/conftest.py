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
from fnmatch import fnmatch
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


# ------------------------------------------- o que a rodada grava no `data/` de verdade (S-415)

ESCRITA_LEGITIMA_EM_DATA: tuple[str, ...] = ()
"""Padrões `fnmatch`, relativos a `data/`, que a suíte pode criar sem que isso seja defeito.

Vazia é o estado medido, e não um começo por preguiça: a rodada inteira não cria caminho nenhum
ali. Uma entrada aqui é licença para escrever na árvore de quem roda a suíte, então ela vem com
o motivo escrito ao lado -- e nunca por profilaxia, que é como uma lista destas deixa de valer.
"""

RELATADOS_NO_MAXIMO = 20
"""Quantos nomes a falha imprime. Um caminho novo já é o defeito; trezentos são o mesmo defeito
com a mensagem ilegível."""


def _listagem_de(pasta: Path) -> frozenset[str]:
    """Tudo o que existe sob a pasta, em caminho relativo a ela.

    Custa 0,25 s nos ~20 mil arquivos que `data/samples/` traz numa máquina em uso: barato para
    a rodada inteira e caro demais para cada teste. É o que decide o escopo `session` da guarda
    abaixo, e o preço do escopo é não saber **qual** teste gravou -- os nomes dos arquivos
    criados costumam dizer isso melhor que o nome do teste diria.
    """
    if not pasta.is_dir():
        return frozenset()
    return frozenset(item.relative_to(pasta).as_posix() for item in pasta.rglob("*"))


@pytest.fixture(scope="session", autouse=True)
def nada_novo_no_data_de_verdade() -> Iterator[None]:
    """A suíte não cria arquivo no `data/` de quem a roda (S-415).

    **O caso medido, em 2026-08-31.** Um teste novo chamou `gallery_scan.save_index(livro)` e
    `GalleryModel.save()` sem dizer onde gravar. Os dois resolvem `DEFAULT_GALLERY_DIR` -- que é
    `PROJECT_ROOT / "data" / "gallery"` -- **na definição do argumento**, e um padrão resolvido na
    definição não tem como ser remendado por quem chama. A rodada gravou `data/gallery/livro.json`
    e `data/gallery/livro.index.json` na árvore de trabalho do usuário, e terminou verde.

    **Por que nada acusou, e por que nada acusaria.** `data/gallery/` está no `.gitignore` (a
    S-115 deixa de fora tudo menos o extrato humano), então nem `git status` nem a leitura do diff
    veriam os dois arquivos. Não foi caso de ninguém ter olhado: não havia onde olhar. É a mesma
    forma das outras três desta fase -- o que vaza, o que trava e o que some --, e esta é a que
    **sobrevive à rodada**: pasta temporária e widget morrem no fim, um arquivo em `data/` fica.

    **Por que a guarda olha o efeito, e não a chamada.** Uma varredura estática -- no molde das de
    `tests/test_disciplina_da_suite.py`, que seria o lugar natural -- teria de conhecer cada forma
    de escrever, e já são quatro nomes para a mesma coisa: `directory=` em `save_index` e em
    `save_annotations`, `gallery_dir=` no `GalleryModel`, `pasta_da_galeria=` no painel da galeria.
    Só a primeira vira regra sintática limpa. No `GalleryModel` quem grava é um **campo**, e não a
    chamada: a suíte constrói vinte modelos sem ele que nunca gravam, e o único teste que grava
    direito põe o campo por atribuição **depois** de construir (`test_grava_e_le_de_volta`) --
    cobrar o argumento na construção reprovaria os vinte e o certo junto. O painel é o caso pior:
    quem o constrói não chama `save_index`, ele chama. Todos terminam no mesmo lugar, e é o lugar
    que esta guarda vigia.

    **A pasta é a que o código resolve, e não `RAIZ`.** As duas coincidem sob o pytest, que põe
    `src/` na frente pelo `pythonpath` do `pyproject`. Num processo que importe o pacote da
    instalação editável elas divergem -- e é exatamente aí que a escrita cai no checkout de
    **outra** pessoa, que é o pior caso e o que menos aparece. Uma guarda ancorada em `RAIZ`
    passaria verde justamente sobre ele; a S-218 já pagou por essa lição uma vez.

    **Relata e não apaga.** O que está em `data/` é trabalho humano acumulado (é o que o
    `_project_root` diz sobre o `labels.csv`), e uma guarda que removesse o que julga sobra
    precisaria estar certa todas as vezes. Errar uma vez custaria mais do que o defeito que ela
    persegue, então ela nomeia os arquivos e a remoção fica com quem sabe o que são.
    """
    from chess_diagram_ocr.config import PROJECT_ROOT

    pasta = PROJECT_ROOT / "data"
    antes = _listagem_de(pasta)
    yield
    novos = sorted(
        caminho
        for caminho in _listagem_de(pasta) - antes
        if not any(fnmatch(caminho, padrao) for padrao in ESCRITA_LEGITIMA_EM_DATA)
    )
    if not novos:
        return
    mostrados = ", ".join(novos[:RELATADOS_NO_MAXIMO])
    resto = f" (e mais {len(novos) - RELATADOS_NO_MAXIMO})" if len(novos) > RELATADOS_NO_MAXIMO else ""
    pytest.fail(
        f"A rodada criou {len(novos)} caminho(s) em {pasta}: {mostrados}{resto}. Algum teste "
        "gravou no `data/` de quem roda a suíte, que é uma árvore de trabalho e não um destino "
        "de teste -- e `data/gallery/` está no `.gitignore`, então o `git status` não vai "
        "mostrar isto. Diga onde gravar em vez de aceitar o padrão: `directory=` em `save_index` "
        "e `save_annotations`, `gallery_dir=` no `GalleryModel`, `pasta_da_galeria=` no painel "
        "da galeria. A pasta sai de `pasta_temporaria(self)`, em `tests/ambiente_de_teste.py`."
    )
