"""`cvoff-texto-ordem` — a ordem de leitura medida contra a do próprio PDF (S-194).

    cvoff-texto-ordem --limite 5
    cvoff-texto-ordem --baseline docs/metrics/texto_ordem.json

**O defeito que este comando existe para pegar é invisível.** Ordem de leitura não muda a FEN, não
muda a legenda e não aparece na tela -- só aparece quando alguém exporta um livro e lê. Sem régua,
uma regressão passa meses despercebida.

## A referência não é anotada à mão, e é melhor assim

A spec pedia 12 páginas anotadas. Ao implementar apareceu uma referência **melhor e gratuita**:
nos 20 livros com camada de texto, o próprio PDF já traz a ordem de leitura -- é a ordem em que o
produtor emitiu os spans, e ela vem da diagramação, não de nenhuma medição nossa.

**Ela é independente do que se mede.** A S-190 acha a coluna projetando caixas na imagem; a camada
de texto sabe a ordem porque o typesetter a escreveu. Nenhum dos dois olha para o outro, e é isso
que faz da comparação uma medição em vez de um espelho.

**E não é circular como a semeadura da S-183 seria.** Lá a camada seria a *verdade do conteúdo*, e
é uma das fontes medidas. Aqui ela é a verdade da *ordem*, e ordem é justamente o que nenhum dos
três motores produz.

## A régua é Kendall-tau, e não "acertou tudo"

Uma página com 40 linhas e um par fora de ordem não é o mesmo defeito que uma com as duas colunas
intercaladas. A distância de Kendall conta **pares invertidos** sobre o total de pares:

    0,00   a ordem é a mesma
    0,05   um punhado de trocas locais
    0,50   as duas colunas intercaladas

Os livros de scan puro não têm camada de texto e ficam de fora -- eles aparecem no relatório como
"sem referência", que é o que são.

## A referência nem sempre é a ordem de leitura, e isso é medido antes de ser usado

**Achado de 2026-08-22, na primeira execução.** No `400 Quebra-cabeças ..._hq` a camada emite o
número de página (y=797), depois a metade de baixo (y=309..630) e **só então o topo** (y=88..281).
Três blocos, cada um internamente ordenado, na ordem errada entre si. A nossa saída é
estritamente de cima para baixo -- e o `tau` contra essa referência dava 0,53, como se estivéssemos
lendo a página quase ao contrário.

O guarda é geométrico e barato: numa página de **uma** coluna a ordem de leitura é, por definição,
crescente em `y`; numa de duas ela desce uma vez, ao passar da primeira coluna para a segunda. Uma
referência com mais descidas que `colunas - 1` está emitindo blocos fora de ordem, e o que ela mede
não é a nossa ordenação.

Essas páginas não são descartadas em silêncio: elas entram no relatório em
`paginas_com_referencia_suspeita`, com o número à vista.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_json
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from . import cli_errors

logger = logging.getLogger(__name__)

SAIDA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_ordem.json"

DPI = 220.0
"""O mesmo da varredura de produção. A ordem não deveria mudar com o DPI, e há teste."""

MIN_LINHAS = 6
"""Abaixo disto a página é rosto, folha de guarda ou uma linha solta: não há ordem a medir."""

PIORA_TOLERADA = 0.01
"""Quanto a distância média pode subir contra o `--baseline` antes de o comando falhar.

Regressão de ordem é regressão. A folga existe porque a detecção de diagrama mexe no conjunto de
caixas e uma página a mais ou a menos move a média na terceira casa."""


@dataclass(frozen=True)
class Pagina:
    pdf: str
    pagina: int
    linhas: int
    tau: float
    """Fração de pares invertidos. 0,0 é ordem idêntica à da camada de texto."""

    colunas: int = 1
    descidas_da_referencia: int = 0
    """Quantas vezes a camada volta para cima. Ver "A referência nem sempre é a ordem de leitura"."""

    @property
    def referencia_confiavel(self) -> bool:
        """Uma coluna desce zero vezes; duas colunas descem uma. Mais que isso é bloco fora de ordem."""
        return self.descidas_da_referencia <= max(0, self.colunas - 1)


def kendall_tau(ordem: list[int]) -> float:
    """Fração de pares fora de ordem numa permutação. `0,0` é ordenada, `1,0` é o inverso exato.

    O par é o que importa, e não a posição: uma página com 40 linhas e uma troca local não é o
    mesmo defeito que uma com as duas colunas intercaladas.
    """
    n = len(ordem)
    if n < 2:
        return 0.0
    invertidos = sum(1 for i in range(n) for j in range(i + 1, n) if ordem[i] > ordem[j])
    return invertidos / (n * (n - 1) / 2)


def _linhas_da_camada(page: Any) -> list[tuple[int, tuple[float, float, float, float]]]:
    """`(posição na camada, bbox)` por linha, na ordem em que o PDF as emitiu."""
    saida: list[tuple[int, tuple[float, float, float, float]]] = []
    for bloco in page.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            texto = "".join(span["text"] for span in linha["spans"]).strip()
            if texto:
                x0, y0, x1, y1 = (float(v) for v in linha["bbox"])
                saida.append((len(saida), (x0, y0, x1, y1)))
    return saida


def _centro(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def descidas(topos: Sequence[float], *, folga: float = 2.0) -> int:
    """Quantas vezes a sequência volta para cima. A folga absorve o rasgo da linha justificada."""
    return sum(1 for antes, depois in zip(topos, topos[1:], strict=False) if depois < antes - folga)


def medir_pagina(page: Any) -> Pagina | None:
    """A distância entre a nossa ordem e a da camada, ou `None` quando não há o que medir.

    A nossa ordem sai de `pagina.sequencia_de_leitura` sobre as **caixas da camada de texto**, e
    não sobre caixas segmentadas da imagem. É deliberado: o que se mede aqui é a *ordenação*, e
    alimentá-la com a segmentação misturaria dois erros num número só. A S-206 é quem mede os dois
    juntos.
    """
    from ..text.boxes import Caixa
    from ..text.colunas import detectar_colunas
    from ..text.pagina import sequencia_de_leitura

    da_camada = _linhas_da_camada(page)
    if len(da_camada) < MIN_LINHAS:
        return None

    caixas = [Caixa(int(b[0]), int(b[1]), int(b[2]), int(b[3])) for _, b in da_camada]
    posicao = {_centro(b): i for i, b in da_camada}

    nossa = sequencia_de_leitura(caixas)
    ordem = []
    for elemento in nossa:
        if not isinstance(elemento, Caixa):  # pragma: no cover - sem diagramas nesta medição
            continue
        chave = ((elemento.x1 + elemento.x2) / 2.0, (elemento.y1 + elemento.y2) / 2.0)
        indice = posicao.get(chave)
        if indice is None:
            # O `int()` das coordenadas pode empatar dois centros; casa pelo mais próximo.
            alvo = chave
            perto = min(posicao, key=lambda c: abs(c[0] - alvo[0]) + abs(c[1] - alvo[1]))
            indice = posicao[perto]
        ordem.append(indice)

    return Pagina(
        pdf="",
        pagina=0,
        linhas=len(ordem),
        tau=kendall_tau(ordem),
        colunas=len(detectar_colunas(caixas)),
        descidas_da_referencia=descidas([b[1] for _, b in da_camada]),
    )


def medir(pdfs: list[Path], *, por_livro: int) -> dict[str, Any]:
    """Uma linha por livro, e o agregado. Livro sem camada de texto aparece como tal."""
    import fitz

    por_pdf: dict[str, list[float]] = {}
    sem_referencia: list[str] = []
    avisos: list[str] = []
    piores: list[dict[str, Any]] = []
    suspeitas: list[dict[str, Any]] = []

    for caminho in pdfs:
        try:
            doc = fitz.open(caminho)
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro
            avisos.append(f"{caminho.name}: não abriu ({exc})")
            continue
        with doc:
            medidas: list[float] = []
            vistas = 0
            for indice in range(int(doc.page_count * 0.15), doc.page_count):
                if vistas >= por_livro:
                    break
                try:
                    resultado = medir_pagina(doc[indice])
                except Exception as exc:  # noqa: BLE001 - idem
                    avisos.append(f"{caminho.name} p.{indice + 1}: {exc}")
                    continue
                if resultado is None:
                    continue
                vistas += 1
                registro = {
                    "pdf": caminho.name,
                    "pagina": indice + 1,
                    "linhas": resultado.linhas,
                    "colunas": resultado.colunas,
                    "tau": resultado.tau,
                    "descidas_da_referencia": resultado.descidas_da_referencia,
                }
                if not resultado.referencia_confiavel:
                    suspeitas.append(registro)
                    continue
                medidas.append(resultado.tau)
                piores.append(registro)
        if medidas:
            por_pdf[caminho.name] = medidas
        elif vistas == 0:
            sem_referencia.append(caminho.name)

    todas = [t for medidas in por_pdf.values() for t in medidas]
    piores.sort(key=lambda p: -p["tau"])
    return {
        "dpi": DPI,
        "livros_medidos": len(por_pdf),
        "livros_sem_referencia": sem_referencia,
        "paginas": len(todas),
        "tau_medio": (sum(todas) / len(todas)) if todas else None,
        "paginas_em_ordem": sum(1 for t in todas if t == 0.0),
        "por_livro": {
            livro: {"paginas": len(medidas), "tau_medio": sum(medidas) / len(medidas)}
            for livro, medidas in sorted(por_pdf.items())
        },
        "piores": piores[:10],
        # **Não são descartes silenciosos.** São páginas em que a camada de texto emite blocos
        # fora da ordem de leitura, e ali o `tau` mede a referência e não a nossa ordenação.
        "paginas_com_referencia_suspeita": len(suspeitas),
        "referencias_suspeitas": suspeitas[:10],
        "avisos": avisos,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mede a ordem de leitura contra a da camada de texto do proprio PDF (S-194).",
        epilog=(
            "Os livros de scan puro nao tem camada de texto e ficam de fora: eles aparecem no "
            "relatorio como 'sem referencia', que e o que sao."
        ),
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--por-livro", type=int, default=5, help="Paginas medidas por livro (padrao 5).")
    parser.add_argument("--limite", type=int, help="So os N primeiros livros.")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Falha (codigo 1) se a distancia media piorar contra este relatorio. Regressao de ordem e regressao.",
    )
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()

    pdfs = sorted(p for p in args.pdf_dir.glob("*.pdf") if p.is_file())
    if args.limite:
        pdfs = pdfs[: args.limite]
    if not pdfs:
        logger.warning("Nenhum PDF em %s. Nada a medir.", args.pdf_dir)
        return 0

    relatorio = medir(pdfs, por_livro=args.por_livro)
    for aviso in relatorio["avisos"]:
        logger.warning("%s", aviso)

    atomic_write_json(args.saida, relatorio)
    medio = relatorio["tau_medio"]
    print(
        f"{relatorio['livros_medidos']} livros, {relatorio['paginas']} paginas  "
        f"tau medio {'-' if medio is None else f'{medio:.4f}'}  "
        f"{relatorio['paginas_em_ordem']} paginas em ordem exata"
    )
    if relatorio["livros_sem_referencia"]:
        print(f"{len(relatorio['livros_sem_referencia'])} livro(s) sem camada de texto ficaram de fora.")
    if relatorio["paginas_com_referencia_suspeita"]:
        print(
            f"{relatorio['paginas_com_referencia_suspeita']} pagina(s) fora: a camada emite blocos "
            "fora da ordem de leitura, e ali o tau mede a referencia."
        )
    for pior in relatorio["piores"][:3]:
        print(f"   pior: {pior['tau']:.3f}  {pior['pdf'][:52]} p.{pior['pagina']}")

    if args.baseline:
        if not args.baseline.exists():
            logger.error("O baseline %s não existe.", args.baseline)
            return 1
        antes = json.loads(args.baseline.read_text(encoding="utf-8")).get("tau_medio")
        if antes is not None and medio is not None and medio > antes + PIORA_TOLERADA:
            logger.error(
                "A ordem piorou: tau médio %.4f contra %.4f do baseline (tolerância %.2f).",
                medio,
                antes,
                PIORA_TOLERADA,
            )
            return 1
    return 0


__all__ = ["Pagina", "kendall_tau", "main", "medir", "medir_pagina", "parse_args"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
