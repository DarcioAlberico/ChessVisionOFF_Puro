from __future__ import annotations

import logging
import os
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
    global _configured
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
            # **Rotativo, e não crescente para sempre (S-389).** O arquivo grava em DEBUG por
            # decisão da S-126, e DEBUG num programa que lê 402 páginas são dezenas de MB por
            # sessão: `logs/chessvisionoff.log` era um arquivo que só crescia, na pasta do
            # usuário, sem nada que o aparasse. Cinco arquivos de 2 MB é rastro suficiente para
            # a falha de ontem e teto para o disco de amanhã.
            arquivo: logging.Handler = RotatingFileHandler(
                log_file, maxBytes=TAMANHO_DO_LOG, backupCount=LOGS_GUARDADOS, encoding="utf-8"
            )
            # **O arquivo sempre em DEBUG, a tela no nivel pedido** (S-126). E o que permite ao
            # `cli.run_main` mandar o traceback para o log sem despeja-lo na tela: sem isso, a
            # unica escolha era "traceback em ingles no terminal" ou "rastro nenhum em lugar
            # nenhum", e a segunda e o modo de falha que a Fase 18 existe para fechar.
            arquivo.setLevel(logging.DEBUG)
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
