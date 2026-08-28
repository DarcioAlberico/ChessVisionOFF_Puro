"""`cvoff-texto-custo` -- quanto o texto soma à varredura, medido por etapa (S-215).

    cvoff-texto-custo --livros 6 --paginas-por-livro 3

**Por que este comando existe antes da Fase 30, e não depois.** A S-61 mediu ~2,95 s por página
só do pipeline de diagramas, e extrapolou ~10 h para o acervo. Ler a página inteira **soma** a
isso, e o quanto era palpite. A regra de sequenciamento nº 3 do `ROADMAP_TEXTO` diz que nada da
Fase 30 embarca antes de este número existir -- um leitor de página que triplique uma varredura
de 10 h é uma regressão, e o lugar de descobrir isso é aqui.

## As duas pontas da divisão são medidas na mesma corrida

O comando roda, para cada página sorteada, **duas coisas**: a varredura de diagramas como ela é
hoje (`iter_pdf_diagrams`, com o modelo de peças) e a leitura de texto (`ler_pagina`). O fator que
escolhe a política é a razão entre as duas, medida na mesma máquina, na mesma página, no mesmo
minuto.

**Dividir pelo 2,95 s de agosto estaria errado**, e não por preciosismo: a contenção entre sessões
vale ~40% nesta máquina -- 57,7 s ocioso contra 113 s sob carga no mesmo modelo (ver
`docs/metrics/field_*.json`). Um fator calculado contra um número de outro dia mede o quanto a
máquina estava ocupada.

**E a renderização e a detecção não são contadas duas vezes.** As duas rodam nos dois lados, e a
varredura já as paga; o que o texto acrescenta é o resto. `--json` grava as três colunas --
`hoje`, `texto` e `total` -- para que a conta seja conferível sem refazer a medição.

## A amostra é do livro inteiro, e não das primeiras páginas

As páginas saem por passo constante ao longo do livro, e nunca as N primeiras. É a mesma lição
que a S-214 registra sobre a coleta: as primeiras páginas de um livro são uma fonte, um estado de
digitalização e quase sempre rosto e sumário -- uma amostra delas descreve a capa, não o livro.

## `--baseline`, e por que ele é a trava do `cvoff-census --fail-on-loss`

Regressão de desempenho é regressão. Com `--baseline`, o comando compara contra o perfil
arquivado e sai com código 1 quando o custo por página piora além de `--margem`, nomeando a
etapa. Sem ele, mede e grava.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text import custo as _custo
from . import (
    EXIT_BAD_INPUT,
    EXIT_FAILURE,
    EXIT_OK,
    add_dpi_argument,
    add_model_argument,
    add_verbose,
    cli_errors,
    confere_baseline,
)

logger = logging.getLogger(__name__)

PASTA_DAS_METRICAS = PROJECT_ROOT / "docs" / "metrics"

PAGINAS_POR_LIVRO = 3
"""Quantas páginas de cada livro entram na amostra.

Três é o menor número que dá dispersão dentro do livro sem que a corrida vire uma varredura: a
página de texto custa segundos, e o comando é para ser rodado antes de decidir escopo, não uma
vez por mês."""

LIVROS = 6
"""Quantos livros entram por omissão. O acervo tem 45 arquivos e livros repetidos entre eles --
ver a memória do projeto sobre duplicatas --, e medir os 45 mediria o mesmo livro duas vezes."""


def paginas_amostradas(total: int, quantas: int) -> list[int]:
    """Índices 0-based espalhados pelo livro inteiro, por passo constante.

    Nunca as `quantas` primeiras -- ver "A amostra é do livro inteiro" no cabeçalho. O passo é
    `total/(quantas+1)`, que põe a primeira e a última a meia distância das bordas em vez de na
    capa e na contracapa: com `total=100` e `quantas=3` saem as folhas 25, 50 e 75.

    **O conjunto colapsa índices repetidos, e é de propósito.** Num livro de 2 folhas com
    `quantas=3` os três passos caem na mesma folha, e a amostra sai com uma -- medir a mesma
    página três vezes daria dispersão falsa e um `n` que mentiria no relatório.
    """
    if total <= 0 or quantas <= 0:
        return []
    quantas = min(quantas, total)
    passo = total / (quantas + 1)
    indices = sorted({min(total - 1, int(round(passo * (k + 1)))) for k in range(quantas)})
    return indices


def livros_do_acervo(pasta: Path, quantos: int) -> list[Path]:
    """Os PDFs da pasta, em ordem estável, cortados em `quantos`.

    Ordem por nome e não por tamanho ou data: a amostra tem de ser a mesma entre a corrida que
    grava o baseline e a que o confere, senão `--baseline` compara livros diferentes e acusa
    regressão onde houve troca de acervo.
    """
    achados = sorted(p for p in pasta.glob("*.pdf") if p.is_file())
    return achados[:quantos] if quantos > 0 else achados


def _custo_de_hoje(pdf: Path, indice: int, *, dpi: int, sessao: Any) -> float:
    """Segundos que a varredura de diagramas gasta nesta página, como ela é hoje.

    Roda `iter_pdf_diagrams` sobre a página sozinha -- o mesmo laço que o `cvoff-scan` e a fila da
    S-22 usam, e não uma reimplementação dele. Consumir o gerador inteiro é o ponto: a inferência
    dos diagramas é 76% do tempo de página segundo a S-61, e ela só acontece quando o item é
    puxado.

    **`sessao` empresta o modelo já carregado, e a primeira versão deste comando não o fazia.**
    Sem ele, `iter_pdf_diagrams` carrega o `.pt` por página -- e o log de uma corrida de 18
    páginas trazia 18 linhas de "Modelo carregado". Uma varredura de verdade paga essa carga uma
    vez por livro, então contá-la por página inflava o lado *hoje* da divisão e fazia o fator
    sair **menor** do que é. O erro tinha o sinal cômodo, que é o pior tipo.
    """
    from time import perf_counter

    from ..pdf_to_pgn import iter_pdf_diagrams

    inicio = perf_counter()
    for _ in iter_pdf_diagrams(
        pdf, dpi=dpi, start_page=indice, end_page=indice + 1, model_session=sessao
    ):
        pass
    return perf_counter() - inicio


class _sempre:
    """Um `model_session` reutilizável: cada `with` devolve o mesmo par já carregado.

    `iter_pdf_diagrams` faz `with model_session` **por varredura**, e aqui há uma varredura por
    página -- um `contextmanager` puro só serve à primeira e estoura na segunda. Isto é a menor
    coisa que atende ao contrato de `AbstractContextManager[tuple[modelo, dispositivo]]` sem
    carregar nada de novo.
    """

    def __init__(self, par: tuple[Any, str]) -> None:
        self._par = par

    def __enter__(self) -> tuple[Any, str]:
        return self._par

    def __exit__(self, *_: object) -> None:
        return None


@contextmanager
def _modelo_emprestado(modelo: Path) -> Iterator[tuple[Any, str]]:
    """O `.pt` de peças carregado uma vez para a corrida inteira.

    É a mesma forma que o `OcrService` empresta para a fila da S-22 (`model_session`), e por isso
    `iter_pdf_diagrams` já a aceita: nada aqui é caminho novo de varredura.
    """
    from ..inference import load_model

    yield load_model(modelo)


def _medir_pagina(pdf: Path, indice: int, *, dpi: int, reconhecedor: Any) -> _custo.Cronometro:
    """O cronômetro de uma leitura de página, com as nove etapas envolvidas."""
    from ..text.leitor import ler_pagina

    with _custo.medindo() as relogio:
        ler_pagina(pdf, indice, dpi=dpi, motor="glifo", reconhecedor=reconhecedor)
    return relogio


def _acumular(destino: _custo.Cronometro, parcela: _custo.Cronometro) -> None:
    """Soma um cronômetro de página no acumulado da amostra.

    Existe porque `medindo()` devolve um cronômetro por página -- ele tem de ser fechado para o
    `total` valer --, e o perfil é da amostra inteira.
    """
    for nome, valor in parcela.segundos.items():
        destino.segundos[nome] = destino.segundos.get(nome, 0.0) + valor
    for nome, valor in parcela.chamadas.items():
        destino.chamadas[nome] = destino.chamadas.get(nome, 0) + valor
    destino.total += parcela.total


def relatorio(
    perfil: _custo.Perfil,
    *,
    hoje_por_pagina: float,
    paginas_do_acervo: int,
) -> tuple[str, dict[str, Any]]:
    """`(a tabela para a tela, o dicionário para o JSON)`.

    **As duas unidades saem juntas e das duas colunas**, que é o critério de aceite do item:
    segundos por página diz se a interface trava, horas para o acervo diz se a varredura cabe numa
    noite -- e as duas aparecem para *hoje* e para *com texto*, senão o leitor teria de fazer a
    conta na cabeça para saber o que mudou.
    """
    texto_por_pagina = max(
        0.0,
        perfil.segundos_por_pagina
        - perfil.etapas.get("renderizacao", 0.0)
        - perfil.etapas.get("deteccao", 0.0),
    )
    total_por_pagina = hoje_por_pagina + texto_por_pagina
    fator = total_por_pagina / hoje_por_pagina if hoje_por_pagina > 0 else float("inf")
    chave, frase = _custo.politica_para(fator)

    linhas = [
        f"Amostra: {perfil.paginas} páginas.",
        "",
        "etapa                    s/página   chamadas/página",
    ]
    for nome, valor in perfil.etapas.items():
        chamadas = perfil.chamadas.get(nome)
        coluna = f"{chamadas:9.2f}" if chamadas is not None else " " * 9
        linhas.append(f"  {nome:<22s} {valor:8.4f}   {coluna}")
    linhas += [
        "",
        "                      s/página   h/acervo",
        f"  hoje (diagramas)  {hoje_por_pagina:8.3f}   {_custo.horas_para_o_acervo(hoje_por_pagina, paginas_do_acervo):8.2f}",
        f"  o texto soma      {texto_por_pagina:8.3f}   {_custo.horas_para_o_acervo(texto_por_pagina, paginas_do_acervo):8.2f}",
        f"  total             {total_por_pagina:8.3f}   {_custo.horas_para_o_acervo(total_por_pagina, paginas_do_acervo):8.2f}",
        "",
        f"Fator sobre hoje: {fator:.2f}x  ->  política '{chave}': {frase}",
        f"(acervo estimado em {paginas_do_acervo} páginas)",
    ]

    dados: dict[str, Any] = dict(perfil.para_json())
    dados.update(
        {
            "item": "S-215",
            "hoje_por_pagina": round(hoje_por_pagina, 4),
            "texto_por_pagina": round(texto_por_pagina, 4),
            "total_por_pagina": round(total_por_pagina, 4),
            "paginas_do_acervo": paginas_do_acervo,
            "horas_hoje": round(_custo.horas_para_o_acervo(hoje_por_pagina, paginas_do_acervo), 3),
            "horas_texto": round(_custo.horas_para_o_acervo(texto_por_pagina, paginas_do_acervo), 3),
            "horas_total": round(_custo.horas_para_o_acervo(total_por_pagina, paginas_do_acervo), 3),
            "fator": round(fator, 3),
            "politica": chave,
            "politica_frase": frase,
        }
    )
    return ("\n".join(linhas), dados)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cvoff-texto-custo",
        description=(
            "Mede o custo por página da leitura de texto, etapa a etapa, e diz que política "
            "o número escolhe (S-215)."
        ),
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta do acervo.")
    parser.add_argument("--pdf", type=Path, default=None, help="Um PDF só, em vez do acervo.")
    parser.add_argument("--livros", type=int, default=LIVROS, help=f"Quantos livros. Padrão: {LIVROS}.")
    parser.add_argument(
        "--paginas-por-livro",
        type=int,
        default=PAGINAS_POR_LIVRO,
        help=f"Páginas por livro, espalhadas pelo livro inteiro. Padrão: {PAGINAS_POR_LIVRO}.",
    )
    add_dpi_argument(parser)
    add_model_argument(parser, help="Modelo de peças da varredura de hoje.")
    parser.add_argument(
        "--paginas-do-acervo",
        type=int,
        default=_custo.PAGINAS_DO_ACERVO,
        help=f"Para a segunda unidade (horas). Padrão: {_custo.PAGINAS_DO_ACERVO}.",
    )
    parser.add_argument("--json", type=Path, default=None, help="Onde gravar o perfil. Padrão: docs/metrics/texto_custo_<data>.json.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Compara com um perfil arquivado e sai 1 se o custo piorou. Nada é gravado.",
    )
    parser.add_argument(
        "--margem",
        type=float,
        default=_custo.MARGEM_PADRAO,
        help=f"Quanto pode piorar antes de --baseline acusar. Padrão: {_custo.MARGEM_PADRAO}.",
    )
    add_verbose(parser)
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    if (codigo := confere_baseline(args.baseline)) is not None:
        return codigo

    if args.pdf is not None:
        if not args.pdf.exists():
            logger.error("PDF não encontrado: %s", args.pdf)
            return EXIT_BAD_INPUT
        livros = [args.pdf]
    else:
        if not args.pdf_dir.is_dir():
            logger.error("Pasta do acervo não encontrada: %s", args.pdf_dir)
            return EXIT_BAD_INPUT
        livros = livros_do_acervo(args.pdf_dir, args.livros)
    if not livros:
        logger.error("Nenhum PDF para medir em %s.", args.pdf_dir)
        return EXIT_BAD_INPUT

    from ..pdf_io import open_document
    from ..text.recognizer import ModeloInvalido, build_glyph_recognizer

    try:
        # Um reconhecedor para a corrida inteira: carregar o classificador custa ~3 s, e pagá-lo
        # por página entraria no número que este comando existe para medir.
        reconhecedor = build_glyph_recognizer()
    except ModeloInvalido as exc:
        logger.error("O motor de glifo não pôde ser carregado: %s", exc)
        return EXIT_BAD_INPUT

    acumulado = _custo.Cronometro()
    hoje_total = 0.0
    medidas = 0

    with _modelo_emprestado(args.model) as sessao_do_modelo:
        # `contextmanager` devolve um objeto de uso unico, e `iter_pdf_diagrams` faz `with` nele a
        # cada pagina. O que se empresta e um envoltorio que devolve sempre o mesmo par ja
        # carregado -- carregar de novo e exatamente o que este trecho existe para nao fazer.
        emprestimo = _sempre(sessao_do_modelo)
        for pdf in livros:
            with open_document(pdf) as doc:
                total_de_paginas = doc.page_count
            indices = paginas_amostradas(total_de_paginas, args.paginas_por_livro)
            for indice in indices:
                logger.info("%s p%d", pdf.name, indice + 1)
                hoje_total += _custo_de_hoje(pdf, indice, dpi=args.dpi, sessao=emprestimo)
                _acumular(acumulado, _medir_pagina(pdf, indice, dpi=args.dpi, reconhecedor=reconhecedor))
                medidas += 1

    if not medidas:
        logger.error("Nenhuma página foi medida.")
        return EXIT_BAD_INPUT

    perfil = _custo.Perfil.de_cronometro(acumulado, medidas)
    tabela, dados = relatorio(
        perfil,
        hoje_por_pagina=hoje_total / medidas,
        paginas_do_acervo=args.paginas_do_acervo,
    )
    dados["livros"] = [pdf.name for pdf in livros]
    print(tabela)

    if args.baseline is not None:
        # A existência do caminho já foi conferida antes de medir (S-381).
        arquivado = json.loads(args.baseline.read_text(encoding="utf-8"))
        pioras = _custo.comparar(arquivado, perfil, margem=args.margem)
        if pioras:
            print("")
            print(f"--baseline: o custo piorou além de {args.margem:.0%}, contra {args.baseline.name}:")
            for piora in pioras:
                print(f"  {piora}")
            return EXIT_FAILURE
        print("")
        print(f"--baseline: dentro da margem de {args.margem:.0%}, contra {args.baseline.name}.")
        return EXIT_OK

    destino = args.json or (PASTA_DAS_METRICAS / f"texto_custo_{date.today():%Y%m%d}.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destino, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
    print("")
    print(f"Perfil gravado em {destino}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
