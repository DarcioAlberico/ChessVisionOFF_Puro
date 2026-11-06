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

**`--quarentena` é a única saída para o treino, e não é rótulo** (S-762): só o par palavra a palavra que a pessoa tocou, com a versão do
modelo que errou, na pasta da S-214, de onde só uma pessoa o promove. O livro do teste não vai. Ver `text/dado_corrigido.py`.

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
from . import add_dpi_argument, add_verbose, cli_errors

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


def para_quarentena(caminhos: list[Path], destino: Path, *, dpi: int) -> dict[str, Any]:
    """Leva à quarentena o que a mão tocou nos arquivos. O PDF é o que a folha diz, e sem ele o arquivo não vai."""
    from ..pdf_io import render_pdf_page
    from ..text import dado_corrigido

    total = dado_corrigido.EnvioAQuarentena()
    por_arquivo: list[dict[str, Any]] = []
    recortes = []
    for caminho in caminhos:
        try:
            doc = arquivo.carregar(caminho)
        except (arquivo.ArquivoInvalido, OSError):
            continue
        if doc.origem is None or not dado_corrigido.pares_tocados(doc):
            continue
        pdf = Path(doc.origem.documento)
        if not pdf.is_file():
            por_arquivo.append({"arquivo": str(caminho), "recusado": f"o PDF não está em {pdf}"})
            continue
        imagem = render_pdf_page(pdf, doc.origem.pagina, dpi=dpi) if not dado_corrigido.livro_recusado(pdf) else None
        destes, envio = dado_corrigido.preparar(doc, pdf, imagem, dpi=dpi)  # type: ignore[arg-type]
        recortes.extend(destes)
        total.juntar(envio)
        por_arquivo.append({"arquivo": str(caminho), **envio.para_json()})
    relatorio = dado_corrigido.enviar(recortes, destino) if recortes else None
    return {
        **total.para_json(),
        "gravados": relatorio.gravados if relatorio else 0,
        "destino": str(destino),
        "arquivos": por_arquivo,
    }


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
    parser.add_argument(
        "--quarentena",
        type=Path,
        help="Leva o par que a mao tocou a esta pasta de quarentena (S-214), com a versao do modelo. Nao grava na base.",
    )
    add_dpi_argument(parser, help="DPI do recorte da folha, com --quarentena.")
    add_verbose(parser)
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

    if args.quarentena:
        enviado = para_quarentena(caminhos, args.quarentena, dpi=args.dpi)
        dados["quarentena"] = enviado
        print(
            f"Quarentena: {enviado['pares']} par(es), {enviado['gravados']} recorte(s) em {enviado['destino']}, "
            f"{enviado['sem_recorte']} par(es) sem recorte."
        )
        for entrada in enviado["arquivos"]:
            if entrada.get("recusado"):
                print(f"  fora: {entrada['arquivo']} -- {entrada['recusado']}")

    if args.json:
        atomic_write_text(args.json, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
        print(f"Relatorio em {args.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
