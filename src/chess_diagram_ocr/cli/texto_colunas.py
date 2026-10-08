"""`cvoff-texto-colunas` — a estrutura de colunas medida contra páginas anotadas à mão (S-524).

    cvoff-texto-colunas
    cvoff-texto-colunas --motor glifo --saida docs/metrics/texto_colunas_glifo.json
    cvoff-texto-colunas --baseline docs/metrics/texto_colunas.json

## Por que uma régua a mais, se a S-194 já mede a ordem

A régua da S-194 compara a nossa ordem com a ordem em que o PDF emite as linhas, e **é cega onde a
camada é zigue-zague**: no `Yusupov - Build Up Your Chess` a camada vai da coluna da esquerda para a
da direita linha a linha, o guarda marca a referência como suspeita, e das 120 páginas de exercício
medidas só 24 entram na conta. Foi assim que as páginas de soluções desse livro saíram intercaladas
durante semanas sem nenhum número vermelho (`docs/PLANO_COLUNAS_SOLUCOES.md`, §1.2).

A régua daqui é a da diagramação: para cada página do conjunto, **quantas colunas tem a região mais
dividida** (`regioes.colunas_da_folha`), anotado à mão depois de olhar a página com as colunas
desenhadas sobre ela. Página de soluções é de duas; lista de lances de uma coluna é de uma; a
picada em tiras estreitas erra porque a região mais dividida tem quatro.

## Dois motores, e o conjunto é o mesmo

`camada` lê as linhas da camada de texto, como a S-194 -- rápido, sem modelo, roda em qualquer
máquina com o acervo. `glifo` segmenta a imagem em caixas de caractere, como a aba Texto
(`leitor.segmentar`), e é o que mede o que o usuário vê; custa ~1 s por página e precisa de `cv2`.
A página sem camada de texto (scan puro) sai de `camada` como "sem camada", e não como erro.

## O baseline é por página, e não por média

**Nenhuma página que acertava pode passar a errar.** Uma média esconderia a troca de uma página
certa por outra -- e foi uma troca dessas que o preenchimento da S-507 comprou sem que ninguém
visse. O `--baseline` reprova se qualquer página certa no relatório anterior estiver errada agora,
com os nomes à vista; o acerto total é informado, mas não é o que trava.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..atomic_io import atomic_write_json
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from . import EXIT_BAD_INPUT, EXIT_FAILURE, add_verbose, cli_errors, confere_baseline

logger = logging.getLogger(__name__)

ANOTADAS_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "colunas_anotadas.json"
SAIDA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_colunas.json"

DPI = 220
"""O mesmo da aba Texto e da varredura de produção."""

MIN_LINHAS = 6
"""Abaixo disto a camada não descreve a página: é "sem camada", como na S-194."""

Motor = Literal["camada", "glifo"]


@dataclass(frozen=True)
class Anotada:
    pdf: str
    pagina: int
    """Número impresso no visualizador, a partir de 1."""

    colunas: int
    """As colunas da região mais dividida, anotadas à mão."""

    grupo: str
    nota: str = ""


@dataclass(frozen=True)
class Medida:
    anotada: Anotada
    achado: int | None
    """`None` quando o motor não tem o que ler (sem camada, sem livro)."""

    regioes: tuple[int, ...]
    motivo: str = ""

    @property
    def acerto(self) -> bool | None:
        return None if self.achado is None else self.achado == self.anotada.colunas


def carregar_anotadas(caminho: Path) -> list[Anotada]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return [
        Anotada(
            pdf=str(p["pdf"]),
            pagina=int(p["pagina"]),
            colunas=int(p["colunas"]),
            grupo=str(p.get("grupo", "")),
            nota=str(p.get("nota", "")),
        )
        for p in dados["paginas"]
    ]


def regioes_pela_camada(page: Any) -> list[Any] | None:
    """As regiões das linhas da camada de texto, ou `None` sem camada que preste."""
    from ..text.boxes import Caixa
    from ..text.leitor import calha_de_linhas
    from ..text.quadros import quadros_da_camada
    from ..text.regioes import detectar_regioes
    from .texto_ordem import _linhas_da_camada

    linhas = _linhas_da_camada(page)
    if len(linhas) < MIN_LINHAS:
        return None
    caixas = [Caixa(int(b[0]), int(b[1]), int(b[2]), int(b[3])) for _, b in linhas]
    quadros = [(int(y0), int(y1)) for y0, y1 in quadros_da_camada(page)]
    return detectar_regioes(caixas, calha_minima=calha_de_linhas(caixas), quadros=quadros)


def regioes_pelo_glifo(pdf: Path, indice: int) -> list[Any]:
    """As regiões das caixas de caractere, como a aba Texto as acha (`leitor.segmentar`)."""
    from ..detection.hybrid import detect_diagrams_in_pdf_page
    from ..pdf_io import render_pdf_page
    from ..text.leitor import segmentar

    imagem = render_pdf_page(pdf, indice, dpi=DPI)
    escala = DPI / 72.0
    retangulos = [tuple(v * escala for v in c.bbox_pdf) for c in detect_diagrams_in_pdf_page(pdf, indice, imagem)]
    _, _, _, _, regioes = segmentar(imagem, retangulos)
    return regioes


def medir_pagina(anotada: Anotada, pdf: Path, motor: Motor) -> Medida:
    import fitz

    from ..text.regioes import colunas_da_folha

    indice = anotada.pagina - 1
    if motor == "camada":
        with fitz.open(pdf) as doc:
            if indice >= doc.page_count:
                return Medida(anotada, None, (), "página fora do livro")
            regioes = regioes_pela_camada(doc[indice])
        if regioes is None:
            return Medida(anotada, None, (), "sem camada")
    else:
        regioes = regioes_pelo_glifo(pdf, indice)
    return Medida(anotada, len(colunas_da_folha(regioes)), tuple(len(r.colunas) for r in regioes))


def medir(anotadas: Sequence[Anotada], *, pdf_dir: Path, motor: Motor) -> dict[str, Any]:
    paginas: list[dict[str, Any]] = []
    nao_encontradas: list[str] = []
    for anotada in anotadas:
        pdf = pdf_dir / anotada.pdf
        if not pdf.is_file():
            nao_encontradas.append(f"{anotada.pdf} p.{anotada.pagina}")
            continue
        try:
            medida = medir_pagina(anotada, pdf, motor)
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro; a página vira registro, não queda
            medida = Medida(anotada, None, (), f"falhou: {exc}")
        paginas.append(
            {
                "pdf": anotada.pdf,
                "pagina": anotada.pagina,
                "grupo": anotada.grupo,
                "esperado": anotada.colunas,
                "achado": medida.achado,
                "regioes": list(medida.regioes),
                "acerto": medida.acerto,
                "motivo": medida.motivo,
                "nota": anotada.nota,
            }
        )
    medidas = [p for p in paginas if p["acerto"] is not None]
    por_grupo: dict[str, dict[str, int]] = {}
    for p in medidas:
        grupo = por_grupo.setdefault(p["grupo"], {"paginas": 0, "acertos": 0})
        grupo["paginas"] += 1
        grupo["acertos"] += int(bool(p["acerto"]))
    return {
        "motor": motor,
        "dpi": DPI,
        "paginas_anotadas": len(anotadas),
        "paginas_medidas": len(medidas),
        "acertos": sum(1 for p in medidas if p["acerto"]),
        "por_grupo": dict(sorted(por_grupo.items())),
        "paginas": paginas,
        "sem_medida": [f"{p['pdf']} p.{p['pagina']}: {p['motivo']}" for p in paginas if p["acerto"] is None],
        "nao_encontradas": nao_encontradas,
    }


def regressoes(relatorio: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """As páginas certas no baseline e erradas agora. Vazio é o que o portão exige."""
    certas_antes = {(p["pdf"], p["pagina"]) for p in baseline.get("paginas", ()) if p.get("acerto")}
    return [
        f"{p['pdf']} p.{p['pagina']} ({p['grupo']}): esperava {p['esperado']}, achou {p['achado']}"
        for p in relatorio["paginas"]
        if (p["pdf"], p["pagina"]) in certas_antes and p["acerto"] is False
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mede a estrutura de colunas contra paginas anotadas a mao (S-524).",
        epilog="O --baseline reprova se qualquer pagina certa no relatorio anterior estiver errada agora.",
    )
    parser.add_argument("--anotadas", type=Path, default=ANOTADAS_PADRAO, help="O conjunto anotado (JSON).")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta do acervo de livros.")
    parser.add_argument("--motor", choices=("camada", "glifo"), default="camada", help="Por onde ler a pagina.")
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="Onde gravar o relatório desta medição.")
    parser.add_argument("--baseline", type=Path, help="Falha (codigo 1) se alguma pagina certa neste relatorio errar.")
    add_verbose(parser)
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    if (codigo := confere_baseline(args.baseline)) is not None:
        return codigo
    if (codigo := confere_baseline(args.anotadas, rotulo="--anotadas")) is not None:
        return codigo

    relatorio = medir(carregar_anotadas(args.anotadas), pdf_dir=args.pdf_dir, motor=args.motor)
    atomic_write_json(args.saida, relatorio)
    print(
        f"motor {args.motor}: {relatorio['acertos']} de {relatorio['paginas_medidas']} paginas com a "
        f"estrutura certa ({relatorio['paginas_anotadas']} anotadas)"
    )
    for grupo, conta in relatorio["por_grupo"].items():
        print(f"   {grupo:12s} {conta['acertos']:3d} / {conta['paginas']}")
    for erro in (p for p in relatorio["paginas"] if p["acerto"] is False):
        print(f"   errada: {erro['pdf'][:48]} p.{erro['pagina']}  esperava {erro['esperado']}, achou {erro['achado']}")
    if relatorio["sem_medida"]:
        print(f"{len(relatorio['sem_medida'])} pagina(s) sem medida: {'; '.join(relatorio['sem_medida'][:4])}")
    if relatorio["nao_encontradas"]:
        print(f"{len(relatorio['nao_encontradas'])} pagina(s) de livro que nao esta neste checkout.")

    if args.baseline:
        anterior = json.loads(args.baseline.read_text(encoding="utf-8"))
        if anterior.get("motor") not in (None, args.motor):
            logger.error("O baseline foi medido com o motor %s, e esta medicao com %s.", anterior.get("motor"), args.motor)
            return EXIT_BAD_INPUT
        piores = regressoes(relatorio, anterior)
        if piores:
            logger.error("%d pagina(s) que acertavam passaram a errar:\n  %s", len(piores), "\n  ".join(piores))
            return EXIT_FAILURE
    return 0


__all__ = ["Anotada", "Medida", "carregar_anotadas", "main", "medir", "medir_pagina", "parse_args", "regressoes"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
