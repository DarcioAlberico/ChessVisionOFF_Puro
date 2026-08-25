"""`cvoff-texto-correcoes` -- o que a mão corrigiu, agrupado por troca (S-239).

    cvoff-texto-correcoes trabalho/                  # varre a pasta atrás de .cvtxt
    cvoff-texto-correcoes folha58.cvtxt --json saida.json

**Para que ele existe.** Uma página de OCR erra o mesmo glifo muitas vezes: a S-211 mediu 241
substituições de caixa alta em 13 páginas, e a S-186 mediu o `l` itálico virando `/` em **16 de 16**
ocorrências do mesmo trecho. Quem corrige à mão faz a mesma correção dezenas de vezes -- e essa
repetição é justamente a evidência que a **S-213** (*aplicar a todos os semelhantes*) precisa para
decidir que o caso vale ser aplicado em lote.

**Este comando não rotula nada.** Ele lê `.cvtxt` e imprime; não escreve em `training_data/`, não
cria amostra e não toca no modelo. Quem transforma correção em rótulo é a S-212, que tem a fila e o
critério -- e um caminho de rótulo sem revisão é o defeito de que a base já tem cicatriz (S-180).

**A correção não está gravada no arquivo: ela é derivada.** O `.cvtxt` guarda os dois lados -- a
`PaginaLida` que o motor leu e as corridas que estão na tela --, e a diferença entre eles é a
correção. Ver `text/correcao.py`.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..logging_setup import configure_logging
from ..text import arquivo, correcao
from . import cli_errors

logger = logging.getLogger(__name__)

TETO_DE_TROCAS = 20
"""Quantas trocas o resumo imprime. O JSON traz todas.

Existe porque uma página muito corrigida tem cauda longa de pares únicos, e a tela precisa mostrar o
que se repete -- que é o que a S-213 consome. `--todas` desliga o teto."""


def arquivos_de(alvos: list[Path]) -> list[Path]:
    """Os `.cvtxt` sob os caminhos pedidos. Pasta vira varredura; arquivo entra como está.

    Ordenado, e não na ordem do sistema de arquivos: dois relatórios do mesmo acervo têm de sair
    comparáveis por `diff`, e a ordem de `glob` não é a mesma em toda máquina.
    """
    achados: list[Path] = []
    for alvo in alvos:
        if alvo.is_dir():
            achados.extend(sorted(alvo.rglob(f"*{arquivo.EXTENSAO}")))
        elif alvo.exists():
            achados.append(alvo)
        else:
            logger.warning("Nao existe, ignorado: %s", alvo)
    return achados


def levantar(caminhos: list[Path]) -> tuple[list[correcao.Correcao], list[dict[str, Any]]]:
    """As correções de todos os arquivos, e a linha de cada um.

    Arquivo ilegível **não interrompe a varredura**: ele entra no relatório com o motivo. Um
    `.cvtxt` corrompido no meio de uma pasta de trezentos não pode custar o levantamento inteiro.
    """
    todas: list[correcao.Correcao] = []
    por_arquivo: list[dict[str, Any]] = []
    for caminho in caminhos:
        try:
            doc = arquivo.carregar(caminho)
        except (arquivo.ArquivoInvalido, OSError) as erro:
            por_arquivo.append({"arquivo": str(caminho), "erro": str(erro)})
            continue
        achadas = correcao.correcoes(doc)
        todas.extend(achadas)
        por_arquivo.append({"arquivo": str(caminho), "correcoes": len(achadas)})
    return todas, por_arquivo


def linhas_do_resumo(dados: dict[str, Any], *, teto: int | None = TETO_DE_TROCAS) -> list[str]:
    """O relatório em texto. Puro, para o teste afirmar o que a tela mostra."""
    linhas = [f"{dados['total']} correcao(oes) em {dados['blocos']} bloco(s)"]
    if dados["por_motor"]:
        linhas.append("por motor: " + ", ".join(f"{k} {v}" for k, v in dados["por_motor"].items()))
    trocas = dados["trocas"] if teto is None else dados["trocas"][:teto]
    for troca in trocas:
        linhas.append(f"  {troca['antes']!r} -> {troca['depois']!r}   {troca['vezes']}x")
    if teto is not None and len(dados["trocas"]) > teto:
        linhas.append(f"  ... e mais {len(dados['trocas']) - teto} troca(s); use --todas ou --json")
    return linhas


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("alvos", nargs="+", type=Path, help="Arquivos .cvtxt ou pastas.")
    parser.add_argument("--json", type=Path, help="Grava o relatorio completo neste caminho.")
    parser.add_argument("--todas", action="store_true", help="Imprime todas as trocas, sem teto.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)

    caminhos = arquivos_de(list(args.alvos))
    if not caminhos:
        print("Nenhum arquivo .cvtxt encontrado nos caminhos pedidos.")
        return 0

    todas, por_arquivo = levantar(caminhos)
    dados = correcao.resumo(todas)
    dados["arquivos"] = por_arquivo

    print(f"{len(caminhos)} arquivo(s) lido(s).")
    for linha in linhas_do_resumo(dados, teto=None if args.todas else TETO_DE_TROCAS):
        print(linha)
    for entrada in por_arquivo:
        if "erro" in entrada:
            print(f"  nao abriu: {entrada['arquivo']} -- {entrada['erro']}")

    if args.json:
        atomic_write_text(args.json, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
        print(f"Relatorio em {args.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
