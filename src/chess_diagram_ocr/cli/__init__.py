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
import sys
from collections.abc import Callable, Sequence
from functools import wraps
from pathlib import Path
from typing import Any

from ..config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_DATASET_CSV,
    DEFAULT_DPI,
    DEFAULT_MODEL_PATH,
    DEFAULT_SAMPLES_DIR,
    DEFAULT_SPLITS_PATH,
)
from ..logging_setup import onde_esta_o_rastro

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


def add_verbose(parser: Any) -> None:
    """Declara `-v/--verbose` no molde único dos 40 comandos (S-377).

    O README garante que todo `cvoff-*` aceita `-v`, e a mensagem de erro da S-126 manda usá-lo
    -- "Rode de novo com -v para ver o rastro completo". **Doze comandos respondiam a isso com
    `error: unrecognized arguments: -v`**, e seis deles nem a forma longa tinham. Quem seguia a
    instrução impressa recebia um segundo erro, agora do `argparse`, e código de saída 2 sobre
    uma falha que era outra coisa.

    Declarar aqui e não em cada arquivo é o que impede o décimo terceiro: um comando novo que
    esqueça a linha continua sem `-v`, mas a varredura de `tests/test_entrypoints.py` acusa.
    """
    parser.add_argument("-v", "--verbose", action="store_true", help="Log em nível DEBUG.")


def add_model_argument(parser: Any, *, help: str = "Checkpoint .pt do classificador de peças.") -> None:
    """`--model`, com o padrão que vale para os catorze comandos que o aceitam (S-383)."""
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help=help)


def add_dpi_argument(parser: Any, *, help: str = f"DPI de renderização da página. Padrão: {DEFAULT_DPI}.") -> None:
    """`--dpi`. O número mora no `config`, e não em doze literais iguais (S-383)."""
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=help)


def add_accept_threshold_argument(
    parser: Any,
    *,
    help: str = "Confiança mínima por casa para a posição ser aceita. "
    f"Padrão: {ACCEPT_MIN_CONFIDENCE}.",
) -> None:
    """`--accept-threshold`, o portão da S-13."""
    parser.add_argument("--accept-threshold", type=float, default=ACCEPT_MIN_CONFIDENCE, help=help)


def add_splits_argument(parser: Any, *, help: str = "Arquivo de partição treino/val/teste.") -> None:
    """`--splits`. O caminho mora no `config` desde a S-383 -- eram seis declarações."""
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS_PATH, help=help)


def add_dataset_arguments(parser: Any, *, splits: bool = True, samples: bool = True) -> None:
    """`--csv`, `--samples` e `--splits`: de onde a medição tira o dado (S-383).

    O bloco era copiado à mão em sete comandos, e a cópia divergia: o `--splits` do
    `cvoff-audit` e o do `cvoff-field` vinham de `DEFAULT_DATASET_CSV.parent`, e o dos outros
    quatro de `PROJECT_ROOT / "data"`. Iguais hoje, e o dia em que deixassem de ser não teria
    sintoma nenhum além de dois comandos medirem conjuntos diferentes.
    """
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV, help="CSV de rótulos (filename,fen).")
    if samples:
        parser.add_argument(
            "--samples", type=Path, default=DEFAULT_SAMPLES_DIR, help="Pasta com as imagens dos tabuleiros."
        )
    if splits:
        add_splits_argument(parser)


def confere_baseline(caminho: Any | None, *, rotulo: str = "--baseline") -> int | None:
    """`None` libera; `EXIT_BAD_INPUT` recusa **antes** de medir (S-381).

    Os cinco comandos de regressão têm o mesmo desenho: medem o acervo inteiro e, no fim,
    comparam o número com o de um relatório anterior. A conferência do caminho ficava junto da
    comparação -- **depois** da medição --, e `cvoff-texto-grade --baseline docs/metrics/tex.json`
    com o nome errado varria os livros todos para então dizer que o arquivo não existe. No
    `texto-duas-linhas` e no `texto-vertical` nem conferência havia: o `json.loads` estourava
    `FileNotFoundError` no fim, com o mesmo prejuízo.

    Um caminho que não existe é sabido antes de a primeira página abrir, e é aí que ele tem de
    ser dito.
    """
    if caminho is None:
        return None
    from pathlib import Path

    if Path(caminho).exists():
        return None
    logger.error("%s não encontrado: %s. Nada foi medido -- confira o caminho.", rotulo, caminho)
    return EXIT_BAD_INPUT


def saida_que_nao_quebra_em_caractere() -> None:
    """Faz `stdout` e `stderr` trocarem o caractere que não cabem, em vez de levantar (S-422).

    **Dois `--help` não conseguiam ser impressos.** `cvoff-texto-pagina` e `cvoff-texto-pesquisavel`
    trazem figurina de xadrez na ajuda -- `♔`, `♘` --, e no Windows a saída **redirecionada** não é
    UTF-8: é a página de código do sistema (cp1252 aqui). O `print` do argparse levantava
    `UnicodeEncodeError`, o comando saía com código 2 e a ajuda não aparecia. `cvoff-texto-pagina
    --help > ajuda.txt` era o gesto mais natural do mundo, e não funcionava.

    **`backslashreplace` e não `replace`, e não trocar de codificação.** Trocar para UTF-8 à força
    faria o acento sair como mojibake num console cp1252 -- que é o caso comum, e o que hoje
    funciona. `backslashreplace` mantém a codificação do terminal e escreve `♔` no lugar do
    que não cabe: quem lê continua entendendo a frase, e o comando **termina**.

    Não faz nada quando a saída não é reconfigurável (um `StringIO` de teste, um `pytest` que
    captura), que é a mesma tolerância a ambiente do resto deste módulo.
    """
    for fluxo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(fluxo, "reconfigure", None)
        if reconfigurar is None:  # pragma: no cover - saída substituída por teste
            continue
        try:
            reconfigurar(errors="backslashreplace")
        except (ValueError, OSError):  # pragma: no cover - fluxo fechado ou não reconfigurável
            continue


def run_main(fn: Callable[..., int], argv: Sequence[str] | None = None) -> int:
    """Roda um `main` de CLI traduzindo falha em mensagem pt-BR e código de saída (S-126).

    **O que é capturado, e o que não é.** `ValueError`, `OSError` e o que as bibliotecas de
    terceiros levantam ao abrir um arquivo que não é o que dizem ser -- `pymupdf.FileDataError`
    herda de `RuntimeError`. `KeyboardInterrupt` e `SystemExit` passam direto: a primeira é o
    usuário mandando parar, e a segunda é o `argparse` já tendo dito o que faltava.

    `-v` continua mostrando o traceback, porque é o que quem está depurando pede -- e o
    traceback vai para o **log** em todos os casos, pelo `logger.exception`.

    **E `-v` vinha de `sys.argv` quando ninguém passa `argv` (S-377).** Como *console script*
    o `main` é chamado sem argumento nenhum, então `argv` chega `None` e `argv or []` é uma
    lista vazia: no uso real -- que é o único em que a pessoa digita `-v` -- a bandeira nunca
    era vista, e o traceback que ela pede não aparecia. Nos testes, que passam `argv`, ela
    sempre foi vista, e é por isso que ninguém percebeu.
    """
    saida_que_nao_quebra_em_caractere()
    verboso = any(arg in ("-v", "--verbose") for arg in (sys.argv[1:] if argv is None else argv))
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
        # **Onde o rastro está, e não "no log"** (S-421): num checkout não há arquivo de log,
        # e mandar procurá-lo é mandar procurar o que ninguém escreveu.
        print(f"Rode de novo com -v para ver o rastro completo. {onde_esta_o_rastro()}")
        return classify(exc)
    except Exception as exc:  # noqa: BLE001 - falha inesperada e uma classe propria (codigo 1)
        logger.debug("Falha inesperada.", exc_info=True)
        print()
        print(f"Falha inesperada: {type(exc).__name__}: {message_for(exc)}")
        print(f"{onde_esta_o_rastro()} Rode com -v para vê-lo aqui.")
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
