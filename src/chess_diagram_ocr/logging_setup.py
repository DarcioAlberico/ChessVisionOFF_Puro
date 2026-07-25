from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%H:%M:%S"

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
    """
    global _configured
    if _configured:
        return

    _force_utf8_output()

    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except OSError as exc:  # disco cheio, permissao, caminho invalido
            logging.getLogger(__name__).warning("Nao foi possivel abrir o arquivo de log %s: %s", log_file, exc)

    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=DATE_FORMAT, handlers=handlers)

    # Bibliotecas de terceiros sao verbosas em DEBUG e nao interessam por padrao.
    for noisy in ("PIL", "matplotlib", "urllib3", "fitz"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def default_log_file() -> Path | None:
    """Arquivo de log padrao, controlado por CVOFF_LOG_DIR. Retorna None se desabilitado."""
    log_dir = os.environ.get("CVOFF_LOG_DIR")
    if not log_dir:
        return None
    return Path(log_dir) / "chessvisionoff.log"
