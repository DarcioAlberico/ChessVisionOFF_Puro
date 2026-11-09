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
`cvoff-*` e o `app_pyqt.py` continuariam quebrados, porque eles dependem da instalação e
não do `sys.path` do pytest. É por isso que existe também o `tests/test_environment.py`.
"""

from __future__ import annotations

import gc
import importlib.util
import os
import sqlite3
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import caixas_modais
import pytest
import sonda_de_escrita
from arvores_do_repositorio import checkout_principal

PACOTE = "chess_diagram_ocr"
DISTRIBUICAO = "chessvisionoff-puro"
RAIZ = Path(__file__).resolve().parents[1]


# ------------------------------------------------ data/ e pgn_database/ de quem roda a suíte

DADOS_DA_SUITE = tempfile.TemporaryDirectory(prefix="cvoff-dados-da-suite-", ignore_cleanup_errors=True)
"""Onde o programa, rodado pela suíte, guarda o que guardaria em `data/` e procura as bases.

**O defeito que isto evita.** A janela abre o cache de posições padrão
(`data/games_positions.sqlite`) com as bases achadas em `pgn_database/`, e `open_store`
**esvazia a tabela** quando a lista de bases não bate com a gravada (S-84). Rodada num checkout
de verdade, a suíte abria o cache *de quem a roda*: medido em 2026-09-24, `test_qt_janela.py` e
vizinhos reescreveram o arquivo de 10,9 MB do dono, e num worktree limpo nascia um cache novo
com `{"files": []}`. Bastava um teste abrir o padrão com outra lista -- a vazia serve -- para
jogar fora uma varredura de ~56 minutos.

**O desvio é feito no import do conftest, e não num fixture**, porque os caminhos nascem no
import dos módulos: `config.DATA_DIR` lê a variável uma vez, e `open_store(path=DEFAULT_STORE_PATH)`
congela o padrão na definição da função. O pytest importa este arquivo antes de qualquer módulo
de teste, e a variável chega aos subprocessos porque `tests/subprocesso.py` copia o `os.environ`.
"""

DESVIOS = {
    "CVOFF_DATA_DIR": Path(DADOS_DA_SUITE.name) / "data",
    "CVOFF_PGN_DATABASE_DIR": Path(DADOS_DA_SUITE.name) / "pgn_database",
}
"""Variável → pasta. **Impostas, e não `setdefault`**: um `CVOFF_DATA_DIR` no terminal de quem roda
a suíte pode ser justamente a pasta de dados de verdade. As duas começam ausentes, como num clone
sem uso: o programa cria `data/` quando precisa, e sem `pgn_database/` não há base a perguntar."""

os.environ.update({variavel: str(pasta) for variavel, pasta in DESVIOS.items()})


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


@pytest.fixture(autouse=True, scope="session")
def trabalho_em_linha() -> Iterator[None]:
    """A suíte roda o passo 15 da OCR_UI **em linha**: sem processo filho e sem folha ao fundo.

    O produto abre o livro, rasteriza a página, lê o `labels.csv` e detecta diagramas num
    processo de trabalho (`chess_diagram_ocr.processo_de_trabalho`), e o visor troca de folha
    quando ela chega por sinal. Na suíte isso seria (a) um `spawn` de um segundo por sessão com
    threads de serviço que sobrevivem ao teste -- e `sem_thread_vazada` está certo em recusá-las
    -- e (b) uma centena de testes de janela que perguntam pela folha na linha seguinte a
    `abrir_pdf` e passariam a ver a página anterior. As duas bandeiras são desligadas uma vez,
    aqui; os testes do próprio caminho ao fundo as ligam explicitamente na construção.
    """
    if importlib.util.find_spec("PyQt6") is None:
        yield
        return
    from chess_diagram_ocr import processo_de_trabalho
    from chess_diagram_ocr.qt import painel_do_pdf

    processo_de_trabalho.processo_de_trabalho().em_processo = False
    anterior = painel_do_pdf.RASTERIZAR_AO_FUNDO
    painel_do_pdf.RASTERIZAR_AO_FUNDO = False
    yield
    painel_do_pdf.RASTERIZAR_AO_FUNDO = anterior


# ------------------------------- o que a suíte grava em data/ e pgn_database/ de quem a roda (S-415, S-805)

PASTAS_DE_QUEM_USA = ("data", "pgn_database")

AVISO_DO_DESVIO = (
    "A suíte desvia data/ e pgn_database/ para uma pasta temporária antes de importar o pacote "
    "(CVOFF_DATA_DIR e CVOFF_PGN_DATABASE_DIR, em tests/conftest.py). O que escapou foi um caminho "
    "montado sem passar por `config.DATA_DIR`, um padrão aceito sem dizer onde gravar -- `directory=` "
    "em `save_index` e `save_annotations`, `gallery_dir=` no `GalleryModel`, `pasta_da_galeria=` no "
    "painel da galeria, com a pasta de `pasta_temporaria(self)` --, ou o desvio saiu do conftest. "
    "Refazer o cache de posições do acervo custa ~56 minutos de varredura."
)

RELATADOS_NO_MAXIMO = 20
"""Quantas escritas a falha imprime. Uma já é o defeito; trezentas são o mesmo defeito com a mensagem
ilegível."""


def pastas_de_dados_reais() -> tuple[Path, ...]:
    """`data/` e `pgn_database/` do `PROJECT_ROOT`, desta árvore e do checkout principal.

    As duas primeiras raízes coincidem sob o pytest (`pythonpath = ["src"]`), mas é o `PROJECT_ROOT`
    que o código usa -- e uma guarda ancorada só na `RAIZ` passaria verde justamente onde as duas
    divergem: num processo que importe o pacote da instalação editável a escrita cai no checkout de
    **outra** pessoa, que é o pior caso e o que menos aparece. A S-218 já pagou por essa lição.

    **A terceira é a que tem o que perder (S-805).** Num worktree, `PROJECT_ROOT/data/` não tem cache
    nenhum: o cache de ~56 minutos de varredura e o trabalho de quem usa moram no checkout principal.
    """
    from chess_diagram_ocr.config import PROJECT_ROOT

    raizes = dict.fromkeys((PROJECT_ROOT, RAIZ, checkout_principal()))
    return tuple(raiz / pasta for raiz in raizes for pasta in PASTAS_DE_QUEM_USA)


def pytest_sessionstart(session: pytest.Session) -> None:
    sonda_de_escrita.instalar(pastas_de_dados_reais())


def _escritas_relatadas(escritas: list[sonda_de_escrita.Escrita]) -> str:
    descritas = list(dict.fromkeys(escrita.descrita() for escrita in escritas))
    resto = len(descritas) - RELATADOS_NO_MAXIMO
    return "; ".join(descritas[:RELATADOS_NO_MAXIMO]) + (f" (e mais {resto})" if resto > 0 else "")


@pytest.fixture(autouse=True)
def dados_de_quem_roda_ficam_onde_estao(request: pytest.FixtureRequest) -> Iterator[None]:
    """Reprova **o teste** em cujo processo houve escrita nos dados de quem roda a suíte.

    **A pergunta é "este processo escreveu?", e não "a pasta mudou?" (S-805).** Quem responde é a
    `tests/sonda_de_escrita.py`, por auditoria: a guarda de antes comparava `mtime` e listagem, e
    acusava o programa do dono, aberto ao lado, gravando uma amostra a cada ~15 s. O que ela não vê
    -- subprocesso e escrita feita em C -- está escrito lá.

    **Os casos medidos.** Em 2026-08-31 um teste chamou `gallery_scan.save_index(livro)` e
    `GalleryModel.save()` sem dizer onde gravar; os dois resolvem `data/gallery/` na definição do
    argumento, e a rodada gravou dois arquivos que o `.gitignore` esconde do `git status` (S-415). Em
    2026-09-24 a janela regravou o `data/games_positions.sqlite` do dono, de 10,9 MB, que o
    `open_store` esvazia quando a lista de bases muda (S-84). A guarda olha a escrita, e não a chamada,
    porque já são quatro nomes para dizer onde gravar e no `GalleryModel` quem decide é um campo.

    **Falha no teste, e não no fim da corrida**, pela regra da S-413: o rastro aponta para quem fez. A
    thread vai na mensagem: uma `Tarefa` que grave depois de o seu teste acabar aparece no seguinte,
    fora da thread principal, e a escrita depois do último teste a conferência da sessão pega.

    **Relata e não apaga.** O que está em `data/` é trabalho humano acumulado, e uma guarda que
    removesse o que julga sobra precisaria estar certa todas as vezes.
    """
    yield
    escritas = sonda_de_escrita.SONDA.recolher()
    if escritas:
        pytest.fail(
            f"{request.node.name} escreveu nos dados de quem roda a suíte: {_escritas_relatadas(escritas)}. "
            f"{AVISO_DO_DESVIO}"
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """A mesma conferência para o que foi escrito depois do último teste."""
    escritas = sonda_de_escrita.SONDA.recolher()
    if not escritas:
        return
    relator = session.config.pluginmanager.get_plugin("terminalreporter")
    if relator is not None:
        relator.write_sep("=", "a suíte escreveu nos dados de quem a roda", red=True)
        relator.write_line(_escritas_relatadas(escritas))
        relator.write_line(AVISO_DO_DESVIO)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def _fecha_os_caches_esquecidos(pasta: Path) -> None:
    """Fecha as conexões SQLite que o programa deixou abertas dentro da pasta da suíte.

    A Galeria guarda o cache aberto até trocá-lo, e um painel de teste destruído não o fecha. No
    Windows um arquivo aberto não sai, e a pasta ficaria em `%TEMP%` a cada corrida -- o vazamento
    que a S-415 mediu. A sessão acabou: ninguém mais vai ler por essas conexões.
    """
    dentro = os.path.normcase(str(pasta))
    for objeto in gc.get_objects():
        if not isinstance(objeto, sqlite3.Connection):
            continue
        try:
            arquivo = objeto.execute("PRAGMA database_list").fetchone()[2]
            if arquivo and os.path.normcase(arquivo).startswith(dentro):
                objeto.close()
        except sqlite3.Error:  # fechada, ou de outra thread: não é esta que segura a pasta
            continue


def pytest_unconfigure(config: pytest.Config) -> None:
    _fecha_os_caches_esquecidos(Path(DADOS_DA_SUITE.name))
    DADOS_DA_SUITE.cleanup()


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


def _tarefas_rodando() -> list[object]:
    """As `Tarefa` do Qt rodando agora (S-805), ou nenhuma se o teste não chegou a carregar o Qt.

    **Pelo `sys.modules`, e não por import**: o teste de parser não paga o PyQt6 para a guarda
    descobrir que não havia tarefa. Quem nunca importou `qt.trabalho` não construiu `Tarefa`.
    """
    trabalho = sys.modules.get("chess_diagram_ocr.qt.trabalho")
    return [] if trabalho is None else list(trabalho.tarefas_rodando())


def _tarefas_novas(antes: frozenset[int]) -> list[object]:
    return [tarefa for tarefa in _tarefas_rodando() if id(tarefa) not in antes]


_CADERNOS_DA_SUITE = iter(range(1 << 30))


@pytest.fixture(autouse=True)
def caderno_de_cada_teste() -> Iterator[None]:
    """Cada teste tem a sua pasta de cadernos (S-610), e não a da suíte inteira.

    **O `CVOFF_DATA_DIR` desvia a pasta, mas é um só para a corrida toda**, e o caderno acha o
    livro pelo conteúdo: dois testes de janela que abrem o mesmo PDF de fixture -- mesmo copiado
    para pastas diferentes -- abririam o mesmo caderno, e o segundo veria «Abrir folha» com a
    folha que o primeiro leu. É o vazamento do rascunho entre testes, só que com memória melhor.
    A pasta não é criada aqui: só nasce no teste que grava.
    """
    from chess_diagram_ocr.text import caderno

    original = caderno.PASTA_PADRAO
    caderno.PASTA_PADRAO = Path(DADOS_DA_SUITE.name) / "cadernos" / f"t{next(_CADERNOS_DA_SUITE)}"
    try:
        yield
    finally:
        caderno.PASTA_PADRAO = original


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

    **E as `Tarefa` do Qt (S-805)**, que não estão em `threading.enumerate()` -- ou estão como
    `Dummy-N`, que a lista acima aceita. Vêm de `qt.trabalho.tarefas_rodando`, que vê toda `Tarefa`
    construída, com pai ou sem pai; a mensagem as nomeia pelo `nome` que a pessoa veria na caixa.
    """
    antes = frozenset(t.ident for t in threading.enumerate() if t.ident is not None)
    tarefas_antes = frozenset(id(tarefa) for tarefa in _tarefas_rodando())
    yield
    prazo = time.monotonic() + ESPERA_POR_THREAD
    while time.monotonic() < prazo and (_vivas(antes) or _tarefas_novas(tarefas_antes)):
        time.sleep(0.01)
    vazadas = [t.name for t in _vivas(antes)]
    vazadas += [f"Tarefa «{getattr(tarefa, 'nome', '?')}»" for tarefa in _tarefas_novas(tarefas_antes)]
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


# ------------------------------------------------- a caixa modal que trava a suíte (S-414, S-872)


@pytest.fixture(autouse=True, scope="session")
def caixas_desarmadas() -> Iterator[caixas_modais.Desarme | None]:
    """Toda entrada modal do Qt trocada por um substituto que anota e não espera (`tests/caixas_modais.py`).

    **De sessão**, e não de teste, para cobrir também o `setUpClass` e o que roda na coleta; a fixture
    de cada teste só rearma, que é barato. Sem PyQt6 não há caixa a desarmar.
    """
    if importlib.util.find_spec("PyQt6") is None:
        yield None
        return
    desarme = caixas_modais.Desarme()
    desarme.armar()
    try:
        yield desarme
    finally:
        desarme.desarmar()


@pytest.fixture(autouse=True)
def nenhuma_caixa_modal_de_verdade(
    request: pytest.FixtureRequest, caixas_desarmadas: caixas_modais.Desarme | None
) -> Iterator[None]:
    """Uma caixa aberta de verdade **para** a suíte, e nada a interrompia (S-414, S-872).

    **Os casos medidos.** Um painel de texto construído sem `pasta_de_rascunhos` lia `data/rascunhos/`
    da máquina, e um rascunho ali abria a pergunta de recuperação (`QMessageBox.question`). Em
    2026-11-09 foi a caixa de falha da aba Texto -- um `QMessageBox` montado e aberto por `exec()` de
    instância, que o desarme dos atalhos estáticos não via -- e a integração da solidez parou dentro de
    `tests/test_qt_texto_prosa.py`. Sem tempo limite, sem mensagem, e o `-v` já tinha impresso o nome
    do teste anterior.

    Agora o teste **reprova**, na desmontagem, dizendo qual entrada, o que a caixa diria e a linha que
    a abriu. A que abriu entre dois testes -- num `setUpClass`, na desmontagem de outra fixture --
    reprova o seguinte, e a linha diz de onde veio. Quem **precisa** de uma resposta diz qual:
    `mock.patch.object(QMessageBox, "question", ...)`, ou `"exec"`, no próprio teste, vence o
    substituto -- é aplicado depois e desfeito antes.
    """
    if caixas_desarmadas is not None:
        caixas_desarmadas.armar()
    yield
    abertas = caixas_modais.recolher()
    if abertas:
        pytest.fail(
            f"{request.node.name} abriu caixa modal sem dizer a resposta: "
            f"{'; '.join(caixa.descrita() for caixa in abertas)}. Uma caixa de verdade trava a suíte "
            "esperando clique: diga a resposta com `mock.patch.object` no teste, ou passe ao painel o "
            "que evita a pergunta (por exemplo `pasta_de_rascunhos=`)."
        )
