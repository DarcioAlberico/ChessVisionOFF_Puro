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

import argparse
import logging
import pickle
import sqlite3
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any

from ..config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_DATASET_CSV,
    DEFAULT_DPI,
    DEFAULT_MAX_BOARDS,
    DEFAULT_MODEL_PATH,
    DEFAULT_ORIENTATION_MODE,
    DEFAULT_PDF_DIR,
    DEFAULT_READING_ORDER,
    DEFAULT_SAMPLES_DIR,
    DEFAULT_SPLITS_PATH,
    PROJECT_ROOT,
)
from ..logging_setup import onde_esta_o_rastro, verbosidade_pedida

logger = logging.getLogger(__name__)

Declarador = argparse._ActionsContainer
"""Onde um argumento é declarado: o parser ou um grupo dele (S-857).

O tipo é o ancestral comum de `ArgumentParser` e dos grupos que `add_mutually_exclusive_group`
devolve -- o `cvoff-census` declara `--pdf-dir` e `--pages` dentro de grupos. Ele é privado no
`argparse`, mas é o que o `typeshed` declara como dono de `add_argument`; a alternativa era `Any`."""

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



class EntradaInvalida(ValueError):
    """O que a pessoa apontou não serve: a falha sai com 2 (S-857).

    **Levantada só na fronteira de entrada** -- onde o comando confere ou abre o que lhe deram
    (ver `fronteira`, `exige_documento`, `exige_checkpoint`). Até a S-857 o `run_main` tratava
    todo `ValueError`, `OSError` e `RuntimeError` como entrada inválida: um `int("x")` de defeito
    interno saía 2, dizendo à pessoa que a culpa era do arquivo dela, e o 3 era decidido por
    palavras no texto da mensagem (`"checkpoint"`, `".pt"`). Agora a classe vem do tipo, e o tipo
    de quem sabe -- o código que abriu o arquivo. Todo o resto é defeito: código 1.

    Herda de `ValueError` porque é o que ela é, e para que quem já esperava `ValueError` de uma
    validação de argumento (como `texto_pagina.intervalo_de_paginas`) continue esperando.
    """

    codigo = EXIT_BAD_INPUT


class CheckpointInvalido(EntradaInvalida):
    """O checkpoint apontado não existe, não carrega, ou é de outra `arch_version`: código 3."""

    codigo = EXIT_NO_CHECKPOINT


_FALHAS_DE_ENTRADA = (OSError, ValueError, RuntimeError, EOFError, pickle.UnpicklingError, sqlite3.Error)
"""O que abrir um arquivo de terceiro levanta. `pymupdf.FileDataError` herda de `RuntimeError`;
um `torch.load` de lixo levanta `UnpicklingError` (que não é `ValueError`), e um truncado,
`RuntimeError` ou `EOFError`; um banco que não é banco, `sqlite3.DatabaseError`."""


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


@contextmanager
def fronteira(rotulo: str, *, checkpoint: bool = False) -> Iterator[None]:
    """O que falhar aqui dentro é culpa da entrada `rotulo`, e não do programa (S-857).

    Envolva **só** a abertura do que a pessoa apontou -- o `open`, o `fitz.open`, o `torch.load`,
    o `sqlite3.connect` --, e nunca o trabalho que vem depois: um defeito dentro da fronteira
    sairia 2, que é o engano que a S-857 desfaz. `checkpoint=True` faz a falha sair 3.
    """
    try:
        yield
    except EntradaInvalida:
        raise
    except _FALHAS_DE_ENTRADA as exc:
        classe = CheckpointInvalido if checkpoint else EntradaInvalida
        raise classe(f"{rotulo}: {message_for(exc)}") from exc


def exige_documento(caminho: Path, *, rotulo: str = "o livro") -> None:
    """Abre e fecha o PDF ou DjVu apontado: o que não abre sai 2 **antes** de o comando trabalhar.

    Abrir duas vezes custa milissegundos, e é o que mantém a fronteira estreita: o PDF que abre
    e quebra no meio da varredura é defeito (1), e não entrada inválida.
    """
    from ..pdf_io import open_document

    with fronteira(f"{rotulo} {caminho}"), open_document(caminho):
        pass


def exige_checkpoint(caminho: Path, *, rotulo: str = "--model") -> None:
    """Carrega o `.pt` apontado como o programa o carrega: o que não serve sai 3 antes do trabalho.

    Para os comandos que passam o caminho a um serviço que carrega por dentro: lá dentro, um
    checkpoint truncado ou de outra arquitetura já não tem como chegar aqui como 3. Carregar
    duas vezes custa uma fração de segundo diante da varredura de um livro. Quem carrega o
    modelo ele mesmo envolve o `load_model` com `fronteira(..., checkpoint=True)` e não precisa
    disto.
    """
    from ..inference import load_model

    with fronteira(f"{rotulo} {caminho}", checkpoint=True):
        load_model(Path(caminho), device="cpu")


def add_verbose(parser: Declarador) -> None:
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


def add_model_argument(parser: Declarador, *, help: str = "Checkpoint .pt do classificador de peças.") -> None:
    """`--model`, com o padrão que vale para os catorze comandos que o aceitam (S-383)."""
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help=help)


def add_dpi_argument(parser: Declarador, *, help: str = f"DPI de renderização da página. Padrão: {DEFAULT_DPI}.") -> None:
    """`--dpi`. O número mora no `config`, e não em doze literais iguais (S-383)."""
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=help)


def add_accept_threshold_argument(
    parser: Declarador,
    *,
    help: str = "Confiança mínima por casa para a posição ser aceita. "
    f"Padrão: {ACCEPT_MIN_CONFIDENCE}.",
) -> None:
    """`--accept-threshold`, o portão da S-13."""
    parser.add_argument("--accept-threshold", type=float, default=ACCEPT_MIN_CONFIDENCE, help=help)


def add_splits_argument(parser: Declarador, *, help: str = "Arquivo de partição treino/val/teste.") -> None:
    """`--splits`. O caminho mora no `config` desde a S-383 -- eram seis declarações."""
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS_PATH, help=help)


def add_dataset_arguments(parser: Declarador, *, splits: bool = True, samples: bool = True) -> None:
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


BASE_DE_CARACTERE = PROJECT_ROOT / "training_data"
"""A base de amostras de caractere, uma subpasta por classe. Eram cinco `BASE_PADRAO` iguais (S-857)."""

CACHE_DA_BASE = PROJECT_ROOT / "models" / ".texto_base_cache.npz"
"""A varredura da base em cache, que o treino e a grade de variantes dividem (S-857)."""


def add_pdf_dir_argument(parser: Declarador, *, help: str = "Pasta do acervo de livros.") -> None:
    """`--pdf-dir`, a pasta do acervo. Vinte comandos o escreviam à mão (S-857)."""
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help=help)


def add_json_argument(parser: Declarador, *, default: Path | None = None, help: str = "Grava o relatório em JSON.") -> None:
    """`--json`, o caminho onde o comando grava o que mediu (S-857)."""
    parser.add_argument("--json", type=Path, default=default, help=help)


def add_baseline_argument(parser: Declarador, *, help: str) -> None:
    """`--baseline`, o relatório anterior contra o qual o comando falha. Ver `confere_baseline`."""
    parser.add_argument("--baseline", type=Path, help=help)


def add_amostra_do_acervo(
    parser: Declarador, *, saida: Path, por_livro: int, por_pagina: int | None = None, o_que: str = "Linhas"
) -> None:
    """`--pdf-dir`, `--saida`, `--por-livro`, `--por-pagina` e `--limite` das medições de texto (S-857).

    Sete comandos medem uma amostra do acervo -- tantas páginas por livro, tantas linhas (ou
    faixas) por página, nos N primeiros livros -- e cada um copiava o bloco à mão, com o texto da
    ajuda divergindo de cópia em cópia. `o_que` é o que se conta na página: linhas ou faixas.
    """
    add_pdf_dir_argument(parser)
    parser.add_argument("--saida", type=Path, default=saida, help="Onde gravar o relatório desta medição.")
    parser.add_argument(
        "--por-livro", type=int, default=por_livro, help=f"Páginas medidas por livro (padrão {por_livro})."
    )
    if por_pagina is not None:
        parser.add_argument(
            "--por-pagina", type=int, default=por_pagina, help=f"{o_que} medidas por página (padrão {por_pagina})."
        )
    parser.add_argument("--limite", "--limit", type=int, help="Só os N primeiros livros.")


def add_pesos_de_caractere_argument(parser: Declarador) -> None:
    """`--modelo` dos comandos que leem com o classificador de caractere: `None` é o publicado."""
    parser.add_argument(
        "--modelo", type=Path, help="Pesos do classificador de caractere. Padrão: ao lado do char_meta.json."
    )


def add_base_de_caractere_argument(parser: Declarador, *, help: str = "Pasta com uma subpasta por classe.") -> None:
    """`--base`, a base de amostras de caractere (S-857)."""
    parser.add_argument("--base", type=Path, default=BASE_DE_CARACTERE, help=help)


def add_cache_da_base_arguments(parser: Declarador) -> None:
    """`--cache` e `--revarrer`: a varredura da base guardada, e como ignorá-la (S-857)."""
    parser.add_argument("--cache", type=Path, default=CACHE_DA_BASE, help="Varredura da base em cache (.npz).")
    parser.add_argument("--revarrer", action="store_true", help="Ignora o cache e varre a base de novo.")


def add_fracoes_do_split_arguments(parser: Declarador) -> None:
    """`--val` e `--teste`, as frações da base de caractere fora do treino (S-857)."""
    parser.add_argument("--val", type=float, default=0.1, help="Fração da base reservada à validação.")
    parser.add_argument("--teste", type=float, default=0.1, help="Fração da base reservada ao teste.")


def add_device_argument(parser: Declarador) -> None:
    """`--device`. `None` deixa quem treina escolher: cuda se houver (S-857)."""
    parser.add_argument("--device", default=None, help="cpu ou cuda. Padrão: cuda se houver.")


def add_tolerance_argument(parser: Declarador) -> None:
    """`--tolerance`, a paridade da exportação ONNX (S-30)."""
    parser.add_argument("--tolerance", type=float, default=1e-4, help="Tolerância da S-30.")


def add_orientation_argument(
    parser: Declarador, *, help: str = "Rotação do tabuleiro. `auto` decide pela confiança das duas leituras."
) -> None:
    """`--orientation`, a rotação do diagrama (S-13). Seis cópias, duas com `'auto'` literal (S-857)."""
    parser.add_argument("--orientation", choices=("auto", "0", "180"), default=DEFAULT_ORIENTATION_MODE, help=help)


def add_reading_order_argument(parser: Declarador, *, help: str) -> None:
    """`--reading-order`, a ordem dos diagramas na página (S-14)."""
    parser.add_argument("--reading-order", choices=("column", "row"), default=DEFAULT_READING_ORDER, help=help)


def add_max_boards_argument(
    parser: Declarador, flag: str = "--max-boards", *, help: str = "Teto de diagramas aceitos por página."
) -> None:
    """O teto de diagramas por página. Dois nomes no acervo de comandos, o mesmo número (S-857)."""
    parser.add_argument(flag, type=int, default=DEFAULT_MAX_BOARDS, help=help)


def add_page_range_arguments(parser: Declarador) -> None:
    """`--start-page` e `--end-page`, o trecho do PDF a varrer, base 0 e fim exclusivo (S-857)."""
    parser.add_argument("--start-page", type=int, default=0, help="Primeira página a varrer, base 0.")
    parser.add_argument("--end-page", type=int, default=None, help="Exclusivo. Padrão: até o fim do PDF.")


def add_pages_per_book_argument(parser: Declarador, *, default: int) -> None:
    """`--pages`, quantas páginas de cada livro a amostra visita (S-857)."""
    parser.add_argument("--pages", type=int, default=default, help="Páginas amostradas por livro.")


def add_paginas_argument(parser: Declarador) -> None:
    """`--paginas`, as páginas 1-based que o comando lê. Ver `texto_pagina.intervalo_de_paginas`."""
    parser.add_argument(
        "--paginas", default="1", help="Páginas 1-based: '58', '58-62' ou '58,60,62'. Padrão: a primeira."
    )


def add_gallery_dir_argument(parser: Declarador, default: Path) -> None:
    """`--gallery-dir`. O padrão vem de quem chama: ele mora em `gallery`, fora do fecho deste módulo."""
    parser.add_argument("--gallery-dir", type=Path, default=default, help="Pasta dos índices da Galeria.")


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


def _pediu_verboso(argv: Sequence[str] | None) -> bool:
    """Se **este comando** pediu `-v`, e não se a linha do processo por acaso tem um (S-427).

    Quando o chamador passa `argv`, a resposta é o que ele passou -- é o caso dos testes, e ali a
    intenção é explícita. Quando não passa, quem sabe é o comando que acabou de parsear: os 40
    chamam `configure_logging(verbose=args.verbose)`, e `logging_setup.verbosidade_pedida` guarda
    aquele valor. Varrer o `sys.argv` do processo era ler a linha de outra pessoa.
    """
    if argv is not None:
        return any(arg in ("-v", "--verbose") for arg in argv)
    return verbosidade_pedida()


def run_main(fn: Callable[..., int], argv: Sequence[str] | None = None) -> int:
    """Roda um `main` de CLI traduzindo falha em mensagem pt-BR e código de saída (S-126).

    **O que é capturado, e o que não é.** `EntradaInvalida` sai com o código dela (2, ou 3 para
    `CheckpointInvalido`) -- e ela só nasce na fronteira de entrada (S-857). Qualquer outra
    exceção é defeito do programa: código 1, com o rastro no log. `KeyboardInterrupt` e
    `SystemExit` passam direto: a primeira é o usuário mandando parar, e a segunda é o
    `argparse` já tendo dito o que faltava.

    `-v` continua mostrando o traceback, porque é o que quem está depurando pede -- e o
    traceback vai para o **log** em todos os casos, pelo `logger.exception`.

    **E `-v` vinha de `sys.argv` quando ninguém passa `argv` (S-377).** Como *console script*
    o `main` é chamado sem argumento nenhum, então `argv` chega `None` e `argv or []` é uma
    lista vazia: no uso real -- que é o único em que a pessoa digita `-v` -- a bandeira nunca
    era vista, e o traceback que ela pede não aparecia. Nos testes, que passam `argv`, ela
    sempre foi vista, e é por isso que ninguém percebeu.

    **Mas `sys.argv` é a linha do processo, e nem todo processo é o comando (S-427).** A CI roda
    `uv run pytest -v`, e aquele `-v` fazia o `run_main` levantar a exceção original em vez de
    traduzi-la: dois testes de `test_cli_errors` reprovavam **só lá**. Quem sabe o que este
    comando pediu é quem o parseou -- os 40 chamam `configure_logging(verbose=args.verbose)` --,
    e é a ele que se pergunta agora, depois de `fn` ter rodado.
    """
    saida_que_nao_quebra_em_caractere()
    try:
        return fn(argv)
    except (KeyboardInterrupt, SystemExit):
        raise
    except EntradaInvalida as exc:
        # `debug` e nao `exception`: o traceback vai para o **log** e nao para a tela, que e o
        # que o item pede. O handler de arquivo esta em DEBUG desde a S-126 justamente aqui.
        logger.debug("O comando falhou.", exc_info=True)
        verboso = _pediu_verboso(argv)
        print()
        print(f"Erro: {exc}")
        print()
        if verboso:
            raise
        # **Onde o rastro está, e não "no log"** (S-421): num checkout não há arquivo de log,
        # e mandar procurá-lo é mandar procurar o que ninguém escreveu.
        print(f"Rode de novo com -v para ver o rastro completo. {onde_esta_o_rastro()}")
        return exc.codigo
    except Exception as exc:  # noqa: BLE001 - falha inesperada e uma classe propria (codigo 1)
        logger.debug("Falha inesperada.", exc_info=True)
        verboso = _pediu_verboso(argv)
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
