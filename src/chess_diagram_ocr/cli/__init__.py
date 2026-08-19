"""Entrypoints de linha de comando.

Instalados como `cvoff-train`, `cvoff-infer` e `cvoff-export` (ver [project.scripts]).
Os scripts na raiz do projeto (`train_model.py`, `infer_pdf.py`, `export_pdf_pgn.py`)
sao invocadores finos mantidos por compatibilidade.

**A saída de um `cvoff-*` é a interface daquele programa** -- é o que o `CONTRIBUTING.md`
declara. Até a S-126, nas três falhas mais prováveis (PDF corrompido, checkpoint de outra
`arch_version`, caminho inexistente) essa interface era um traceback **em inglês** e um código
de saída indistinguível: `cvoff-infer <arquivo de lixo>` produzia 11 quadros terminando em
`pymupdf.FileDataError: Failed to open file '...'`, e **14 dos 15 comandos** se comportavam
assim. O `cli_errors` abaixo é o que fecha isso.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from functools import wraps

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_BAD_INPUT = 2
EXIT_NO_CHECKPOINT = 3
"""Códigos de saída por **classe de falha** (S-126), no molde do `--selftest` da S-55.

| código | significado |
|---|---|
| 0 | ok |
| 1 | falha inesperada -- o traceback vai para o log, não para a tela |
| 2 | entrada inválida: PDF corrompido, caminho inexistente, argumento fora de faixa |
| 3 | checkpoint ausente ou de outra `arch_version` |

Por classe e não por comando porque quem consome isto é script: `cvoff-scan --all && cvoff-...`
precisa distinguir "este livro estava corrompido" de "o modelo sumiu", e as duas de "houve um
defeito no programa"."""

_CHECKPOINT_PISTAS = ("checkpoint", ".pt", "arch_version", "state_dict")
"""Palavras que classificam a falha como 3 em vez de 2.

Heurística sobre o texto da exceção, e ela é honesta sobre o que é: as bibliotecas que
levantam aqui (`torch`, `pymupdf`) não têm tipo de exceção para "isto era um checkpoint". O
erro que sobra é classificar como 2 algo que era 3, e os dois já dizem a mesma frase em
pt-BR -- a diferença só importa para quem lê o código de saída num script."""


_TRADUCOES = (
    ("failed to open", "não foi possível abrir o arquivo: ele não existe, está corrompido, ou não é do tipo esperado"),
    ("no such file", "arquivo ou diretório não encontrado"),
    ("cannot open", "não foi possível abrir o arquivo"),
    ("permission denied", "sem permissão para ler ou escrever neste caminho"),
    ("is a directory", "o caminho é um diretório, e era esperado um arquivo"),
    ("no space left", "sem espaço em disco"),
    ("size mismatch", "o checkpoint não bate com a arquitetura esperada -- ver `arch_version`"),
    ("unexpected key", "o checkpoint não bate com a arquitetura esperada -- ver `arch_version`"),
)
"""As causas mais comuns, em pt-BR (S-126).

**Tradução por padrão e não por tipo de exceção**, porque as bibliotecas não dão tipo: um PDF
que não é PDF vem como `pymupdf.FileDataError: Failed to open file '...'`, e um checkpoint de
outra arquitetura como `RuntimeError: size mismatch for ...`. O texto original vai junto entre
parênteses -- a tradução ajuda quem lê, e o original é o que se pesquisa."""


def message_for(exc: BaseException) -> str:
    """A falha em pt-BR, com o texto original ao lado quando ele acrescenta algo."""
    texto = str(exc)
    baixo = texto.lower()
    for pista, traducao in _TRADUCOES:
        if pista in baixo:
            return f"{traducao} ({texto})"
    return texto or type(exc).__name__


def classify(exc: BaseException) -> int:
    """A classe de falha de uma exceção. Ver `EXIT_NO_CHECKPOINT` para a heurística."""
    texto = str(exc).lower()
    if any(pista in texto for pista in _CHECKPOINT_PISTAS):
        return EXIT_NO_CHECKPOINT
    return EXIT_BAD_INPUT


def run_main(fn: Callable[..., int], argv: Sequence[str] | None = None) -> int:
    """Roda um `main` de CLI traduzindo falha em mensagem pt-BR e código de saída (S-126).

    **O que é capturado, e o que não é.** `ValueError`, `OSError` e o que as bibliotecas de
    terceiros levantam ao abrir um arquivo que não é o que dizem ser -- `pymupdf.FileDataError`
    herda de `RuntimeError`. `KeyboardInterrupt` e `SystemExit` passam direto: a primeira é o
    usuário mandando parar, e a segunda é o `argparse` já tendo dito o que faltava.

    `-v` continua mostrando o traceback, porque é o que quem está depurando pede -- e o
    traceback vai para o **log** em todos os casos, pelo `logger.exception`.
    """
    verboso = any(arg in ("-v", "--verbose") for arg in (argv or []))
    try:
        return fn(argv)
    except (KeyboardInterrupt, SystemExit):
        raise
    except (ValueError, OSError, RuntimeError) as exc:
        # `debug` e nao `exception`: o traceback vai para o **log** e nao para a tela, que e o
        # que o item pede. O handler de arquivo esta em DEBUG desde a S-126 justamente aqui.
        logger.debug("O comando falhou.", exc_info=True)
        print()
        print(f"Erro: {message_for(exc)}")
        print()
        if verboso:
            raise
        print("Rode de novo com -v para ver o rastro completo; ele também está no log.")
        return classify(exc)
    except Exception as exc:  # noqa: BLE001 - falha inesperada e uma classe propria (codigo 1)
        logger.debug("Falha inesperada.", exc_info=True)
        print()
        print(f"Falha inesperada: {type(exc).__name__}: {message_for(exc)}")
        print("O rastro completo está no log. Rode com -v para vê-lo aqui.")
        print()
        if verboso:
            raise
        return EXIT_FAILURE


def cli_errors(fn: Callable[..., int]) -> Callable[..., int]:
    """Decorador para os `main` dos `cvoff-*`. Ver `run_main`.

    Decorador e não um invólucro em `[project.scripts]` porque os `main` também são chamados
    de dentro dos testes e uns dos outros -- e o comportamento de falha tem de ser o mesmo
    nos dois caminhos.
    """

    @wraps(fn)
    def _com_erros(argv: Sequence[str] | None = None) -> int:
        return run_main(fn, argv)

    return _com_erros
