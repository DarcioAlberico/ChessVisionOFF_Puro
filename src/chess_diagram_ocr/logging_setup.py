from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%H:%M:%S"

TAMANHO_DO_LOG = 2 * 1024 * 1024
"""Bytes por arquivo de log antes de ele rotacionar (S-389)."""

LOGS_GUARDADOS = 5
"""Quantos arquivos anteriores ficam. Cinco de 2 MB: a sessão de ontem cabe, e o disco tem teto."""

_configured = False


class RedigeCaminho(logging.Formatter):
    r"""O formato do arquivo de log, com a pasta do usuário trocada por `~` (S-909).

    **O arquivo é o que a pessoa anexa a um relato**: a mensagem de erro da S-421 diz onde ele
    está. E dezenas de chamadas interpolam o caminho inteiro -- `C:\Users\<nome>\...` --, com
    o nome de quem usa. Trocar aqui, num lugar só, vale para as que existem e para as que vierem.

    **Formatador, e não filtro**: o filtro vê a mensagem antes de o registro ser formatado, e o
    traceback só ganha texto no `format`. É o traceback que mais carrega caminho -- um quadro
    por linha, e o programa instalado mora na pasta do usuário.

    As duas grafias (`\` e `/`), e sem distinguir caixa no Windows, onde `c:\users` é a mesma
    pasta. O `(?!\w)` não deixa `C:\Users\Ana` comer o começo de `C:\Users\Anabela`.
    """

    def __init__(self, pasta_do_usuario: Path | None = None) -> None:
        super().__init__(LOG_FORMAT, DATE_FORMAT)
        pasta = pasta_do_usuario or Path.home()
        grafias = sorted({str(pasta), pasta.as_posix()}, key=len, reverse=True)
        self._pasta = re.compile(
            "(?:" + "|".join(map(re.escape, grafias)) + r")(?!\w)",
            re.IGNORECASE if os.name == "nt" else 0,
        )

    def format(self, record: logging.LogRecord) -> str:
        return self._pasta.sub("~", super().format(record))


def _info_ou_rastro(registro: logging.LogRecord) -> bool:
    """O que o arquivo grava sem `-v`: INFO para cima, e o traceback em qualquer nível (S-909).

    O DEBUG leva texto do livro e FEN, e deixou de ser o padrão do arquivo. O traceback não:
    o `cli.run_main` o manda em DEBUG para não despejá-lo na tela, e é para recebê-lo que o
    arquivo existe (S-126).
    """
    return registro.levelno >= logging.INFO or registro.exc_info is not None


def _force_utf8_output() -> None:
    """Garante UTF-8 em stdout/stderr.

    No Windows o console usa cp1252 por padrao, o que corrompe texto acentuado.
    Sem isso, mensagens em pt-BR sairiam ilegiveis ou levantariam UnicodeEncodeError
    ao serem redirecionadas.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # Stream nao reconfiguravel (por exemplo, ja substituido por um wrapper).
            pass


_verboso_pedido = False
"""Se o comando que esta rodando pediu `-v`. Ver `verbosidade_pedida` (S-427)."""


def verbosidade_pedida() -> bool:
    """O `-v` **deste** comando, dito por quem o parseou (S-427).

    **O que isto conserta.** `cli.run_main` decidia se mostrava o traceback varrendo o
    `sys.argv` do processo, e num processo que nao e o comando isso e a linha de outra pessoa:
    a CI roda `uv run pytest -v`, e o `-v` do pytest fazia o `run_main` levantar a excecao
    original em vez de traduzi-la para pt-BR e devolver o codigo de saida. Dois testes de
    `test_cli_errors` reprovavam **so na CI** por causa disso -- na maquina de desenvolvimento a
    suite roda sem `-v`.

    O funil e universal: os 40 comandos chamam `configure_logging(verbose=args.verbose)` depois
    de parsear, entao a resposta certa ja passa por aqui uma vez por comando. Perguntar ao
    argparse do proprio comando e o oposto de adivinhar pela linha do processo.
    """
    return _verboso_pedido


def configure_logging(*, verbose: bool = False, log_file: Path | None = None) -> None:
    """Configura o logging da aplicacao. Idempotente: chamadas repetidas nao duplicam handlers.

    Deve ser chamado apenas pelos entrypoints (CLIs e frontends), nunca por modulos
    de biblioteca -- estes so obtem seu logger com `logging.getLogger(__name__)`.

    **Sem `log_file`, o destino é o de `default_log_file()` (S-390).** Ele era um parâmetro que
    cada comando tinha de lembrar de passar, e **23 dos 41 não passavam** -- entre eles uma
    janela Tk. Num checkout isso não muda nada, porque sem `CVOFF_LOG_DIR` aquela função devolve
    `None`; num `.exe`, é a diferença entre ter e não ter rastro, que é o mesmo modo de falha
    que a S-127 fechou para o congelado.
    """
    global _configured, _verboso_pedido
    # **Registrado antes do `return` de idempotencia** (S-427): o segundo comando de um mesmo
    # processo nao reconfigura o logging, e mesmo assim e ele quem esta rodando -- quem pergunta
    # depois quer saber o que **este** comando pediu, e nao o que o primeiro pediu.
    _verboso_pedido = verbose
    if _configured:
        return

    if log_file is None:
        log_file = default_log_file()

    _force_utf8_output()

    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = []
    # **Sem console, não há handler de console (S-389).** No bundle da S-55 o `.exe` é montado
    # com `console=False`, e aí `sys.stderr` é `None`: o `StreamHandler` nasce sem fluxo e
    # **falha a cada registro** -- o logging imprime "--- Logging error ---" para o fluxo que
    # não existe, e o que se vê é nada. O arquivo continuava recebendo, então o defeito era
    # invisível e custava uma exceção por linha de log.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setLevel(level)
        handlers.append(console)

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            # **Rotativo, e não crescente para sempre (S-389).** O arquivo gravava em DEBUG por
            # decisão da S-126 (até a S-909), e DEBUG num programa que lê 402 páginas são
            # dezenas de MB por sessão: `logs/chessvisionoff.log` era um arquivo que só crescia,
            # na pasta do usuário, sem nada que o aparasse. Cinco arquivos de 2 MB é rastro suficiente para
            # a falha de ontem e teto para o disco de amanhã.
            arquivo: logging.Handler = RotatingFileHandler(
                log_file, maxBytes=TAMANHO_DO_LOG, backupCount=LOGS_GUARDADOS, encoding="utf-8"
            )
            # **O traceback no arquivo, e nao na tela** (S-126). E o que permite ao
            # `cli.run_main` mandar o traceback para o log sem despeja-lo na tela: sem isso, a
            # unica escolha era "traceback em ingles no terminal" ou "rastro nenhum em lugar
            # nenhum", e a segunda e o modo de falha que a Fase 18 existe para fechar.
            # **O resto do DEBUG so com `-v`** (S-909): ele leva texto do livro e FEN, e o
            # arquivo e o que a pessoa anexa a um relato. Ver `_info_ou_rastro`.
            arquivo.setLevel(logging.DEBUG)
            if not verbose:
                arquivo.addFilter(_info_ou_rastro)
            arquivo.setFormatter(RedigeCaminho())
            handlers.append(arquivo)
        except OSError as exc:  # disco cheio, permissao, caminho invalido
            logging.getLogger(__name__).warning("Nao foi possivel abrir o arquivo de log %s: %s", log_file, exc)

    # A raiz em DEBUG e cada handler filtrando o seu: com a raiz em INFO, o handler de arquivo
    # nunca receberia o registro de DEBUG para poder grava-lo.
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, datefmt=DATE_FORMAT, handlers=handlers)

    # Bibliotecas de terceiros sao verbosas em DEBUG e nao interessam por padrao.
    for noisy in ("PIL", "matplotlib", "urllib3", "fitz"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def default_log_file() -> Path | None:
    """Arquivo de log padrao. `CVOFF_LOG_DIR` manda; congelado, ha um destino mesmo sem ela.

    **Num checkout, nada mudou**: sem `CVOFF_LOG_DIR` continua devolvendo `None`, e quem roda
    a suite ou um `cvoff-*` no terminal nao ganha arquivo nenhum sem pedir. O terminal ja e o
    rastro.

    **Congelado, `None` era o defeito** (S-127). A `cvoff.spec` desliga o console com o
    comentario "o log continua indo para o arquivo que `default_log_file()` decide, e e la que
    se olha quando algo falha" -- so que nada no bundle define `CVOFF_LOG_DIR`, entao a decisao
    era nao gravar nada. Junto com a S-124, o usuario do `.exe` tinha uma janela que nao
    aparecia, sem console, sem log e sem codigo de saida visivel.

    O destino e `PROJECT_ROOT/logs/`, que congelado e a pasta **ao lado** do `.exe` -- junto
    com `data/`, `models/`, `PDF/` e `PGN/`, que e onde o usuario ja sabe procurar. Nao e
    `_MEIPASS`: aquilo e somente-leitura na pratica e some a cada reinstalacao, que e a pior
    propriedade possivel para o arquivo que existe para sobreviver a uma falha.

    `config` e lido pelo modulo, e nao no `import`, porque `PROJECT_ROOT` sai de `sys.frozen`
    na importacao dele -- e e assim que o teste consegue exercitar este ramo.
    """
    log_dir = os.environ.get("CVOFF_LOG_DIR")
    if log_dir:
        return Path(log_dir) / "chessvisionoff.log"
    if getattr(sys, "frozen", False):
        from . import config

        return config.PROJECT_ROOT / "logs" / "chessvisionoff.log"
    return None


def onde_esta_o_rastro() -> str:
    """A frase que diz **onde** ficou o traceback -- ou que não ficou em lugar nenhum (S-421).

    **Toda mensagem de erro deste programa mandava olhar "o log", e num checkout não há um.**
    `default_log_file` devolve `None` sem `CVOFF_LOG_DIR`, de propósito: no terminal o rastro
    é o terminal. Mas a caixa de erro da janela e o `cli_errors` diziam a mesma frase nos dois
    casos, e no caso comum -- alguém que clonou e rodou -- ela manda procurar um arquivo que
    ninguém escreveu. Quem tenta seguir a instrução conclui que perdeu o rastro; ele nunca
    existiu.

    Devolve o caminho quando há um, e o que fazer para haver quando não há.
    """
    destino = default_log_file()
    if destino is None:
        return (
            "Não há arquivo de log neste ambiente: defina CVOFF_LOG_DIR para criar um, ou "
            "rode o comando pelo terminal com -v."
        )
    return f"O rastro completo está em {destino}."
