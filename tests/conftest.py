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
from pathlib import Path

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
