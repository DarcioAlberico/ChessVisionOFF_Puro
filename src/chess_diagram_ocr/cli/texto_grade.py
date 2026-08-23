"""`cvoff-texto-grade` — a direção em que cada livro numera a grade de exercícios (S-216).

    cvoff-texto-grade --por-livro 40
    cvoff-texto-grade --baseline docs/metrics/texto_grade.json

**Este comando existe porque o `cvoff-texto-ordem` não pode responder à pergunta.** A régua da
S-194 é o `tau` contra a ordem em que o PDF emite os spans, e nos livros de grade deste acervo
essa ordem é o palpite de um motor de OCR -- ver "A procedência da camada" abaixo. Aqui a
referência é outra: **o número impresso na página**, que é a numeração que o editor escolheu.

## O que se mede

Duas coisas, e elas são independentes:

- **a página é uma grade?** -- geometria pura, `grade.parece_grade`. Uma fileira de exercícios é
  separada da seguinte por um vão que atravessa todas as colunas, e prosa não tem esse vão.
- **em que direção ela se lê?** -- `grade.direcao_pela_numeracao`, sobre os números impressos.
  Geometria nenhuma responde a isto: `Schiller` e `Karpov` têm grades indistinguíveis numeradas
  ao contrário uma da outra.

A segunda é **constante por livro**, e é isso que o relatório apura: cada livro recebe um
`arranjo` calibrado, com o número de páginas que votaram de cada lado à vista. Uma divergência
grande dentro de um livro é sinal de defeito na medição, e não de um livro que muda de ideia.

## A procedência da camada entra no relatório, porque ela muda o que a medida vale

A S-194 descreve a referência dela como vinda da diagramação. **O acervo é misto**, e o campo
`camada` de cada livro diz de que lado ele está: uns são editorados de verdade (o `Polgar` sai de
LaTeX com a fonte `SkakNew`, o `Dvoretsky` e o `1001` de conversão de ebook), e outros são
digitalização com OCR por cima. **Os quatro livros de grade calibráveis estão todos do segundo
lado** -- `Karpov`, `Schiller`, `Burgess` e `Secrets` trazem camada do `Adobe Acrobat Paper
Capture`.

Isso não invalida o `tau` como régua de regressão, e invalida-o como **árbitro de grade**: medido
contra o número impresso, o motor erra a direção em 24 de 164 páginas, nos dois sentidos -- e no
`Secrets` erra o livro inteiro. Por isso o campo `emissao_contra_impresso` está no relatório: ele é
a prova, e não uma nota de rodapé.

## O bloco `tau`, e por que ele está aqui para ser desobedecido

O relatório traz as páginas de grade sob as três leituras. Na execução de 2026-08-23, 232 páginas:

    coluna a coluna (o que a S-193 faz)     0,1271
    tudo lido como grade                    0,0943   <- "melhora", e está errado
    direção calibrada por livro             0,0676

**A leitura do meio é a armadilha.** Ligar `grade` para todo mundo faz o agregado cair, e um
portão de "o `tau` médio tem de cair" a aprovaria -- enquanto ela leva o `Schiller` de 0,0004 para
0,1705, num livro cuja numeração impressa diz coluna a coluna em 77 de 77 páginas. O agregado
premia o atalho porque o `Karpov` tem mais páginas de grade que o `Schiller`, e não porque o
atalho esteja certo. Por isso o `--baseline` deste comando trava o **acerto** contra o número
impresso, e não o `tau`.

## O que fica de fora, e é um quarto das páginas de grade

As 64 páginas de grade do `Yusupov` não têm numeração legível na camada -- o número do exercício
não sai como inteiro isolado --, e o livro fica `indefinido`, isto é, em `prosa`. O `tau` dele
sugere fortemente `grade` (0,181 contra 0,044), e **isso não basta**: é exatamente a evidência que
o `Secrets` mostrou ser enganosa. Quem fecha esse caso é a S-188, lendo o número da imagem.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_json
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from . import cli_errors

logger = logging.getLogger(__name__)

SAIDA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_grade.json"

MIN_LINHAS = 6
"""Abaixo disto a página é rosto ou folha de guarda: não há grade a medir."""

NUMERO_NA_LINHA = re.compile(r"^\D{0,4}(\d{1,4})\b")
"""O número do exercício abre a legenda, com no máximo quatro não-dígitos antes dele.

A folga cobre o que os livros põem na frente: `№`, `#`, `(`, e o lixo que o OCR deixa no lugar
deles -- o `Karpov` sai como `N!!311.` na camada do Acrobat. Quatro é o que basta para esses, e
pouco o bastante para não pescar o número que vem no meio de uma frase."""

MARCAS_DE_OCR = ("paper capture", "abbyy", "finereader", "tesseract", "ocr")
"""Trechos de `producer`/`creator` que denunciam camada de texto gerada por máquina."""

CONCORDANCIA_MINIMA = 0.80
"""Fração das páginas decidíveis que precisa votar na mesma direção para o livro ser calibrado.

Abaixo disto o livro sai como `indefinido` e continua em `prosa`, que é o lado seguro. Medido nos
quatro livros de grade do acervo, a concordância real é 1,00 nos quatro -- 66 votos no Karpov,
77 no Schiller, 18 no Burgess e 3 no Secrets, sem uma única contradição. O piso não chega perto de
nenhum deles, e existe para o livro que este acervo não tem: o que mistura duas diagramações."""

QUEDA_TOLERADA = 0.02
"""Quanto o acerto pode cair contra o `--baseline` antes de o comando falhar."""


@dataclass(frozen=True)
class PaginaDeGrade:
    """Uma página medida. `direcao_impressa=None` é página que não responde, e não página errada."""

    pagina: int
    e_grade: bool
    fracao_de_vao: float
    colunas: int
    direcao_impressa: str | None
    direcao_emitida: str | None
    """A direção que a **camada** usou, para a comparação que desqualifica o `tau` como árbitro."""

    tau_prosa: float | None = None
    tau_grade: float | None = None


def _linhas_da_camada(page: Any) -> list[tuple[str, tuple[float, float, float, float]]]:
    saida: list[tuple[str, tuple[float, float, float, float]]] = []
    for bloco in page.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            texto = "".join(span["text"] for span in linha["spans"]).strip()
            if texto:
                x0, y0, x1, y1 = (float(v) for v in linha["bbox"])
                saida.append((texto, (x0, y0, x1, y1)))
    return saida


PAGINAS_DE_PROCEDENCIA = 20
"""Quantas páginas se amostram para dizer de onde veio a camada de texto."""

FRACAO_DIGITALIZADA = 0.5
"""Fração das páginas amostradas que precisa ser bitmap com texto por cima para o livro ser scan.

**Uma página não basta, e o acervo mostra por quê.** Livro editorado tem capa digitalizada, e a
`Gaprindashvili` traz uma página de imagem em 21 amostradas -- contá-la classificaria como OCR um
livro cujas fontes são `Cambria` e `Arial`. Meio a meio é folgado nos dois lados: os scans deste
acervo dão 100% e os editorados, 0% ou 5%."""


def camada_de_ocr(doc: Any) -> str | None:
    """O que denuncia a camada de texto como gerada por máquina, ou `None` se nada denunciar.

    Três marcas, e a terceira é a que pega quem não se identifica: **a maior parte do livro é
    bitmap com texto por cima**. Um livro editorado não desenha as próprias páginas como imagem.

    **O acervo é misto, e o comando não pode fingir que não é.** Dos livros com camada de texto,
    uns são digitalização com OCR (`Karpov`, `Schiller`, `Burgess` e `Secrets` -- justamente os
    quatro de grade) e outros são editorados de verdade: o `Polgar` sai de LaTeX com a fonte `SkakNew`, o
    `Dvoretsky` e o `1001` saem de conversão de ebook. A distinção importa porque é ela que diz
    quanto vale a referência da S-194 em cada livro.
    """
    metadados = doc.metadata or {}
    assinatura = f"{metadados.get('producer', '')} {metadados.get('creator', '')}".lower()
    for marca in MARCAS_DE_OCR:
        if marca in assinatura:
            return marca

    amostradas = digitalizadas = 0
    fontes: set[str] = set()
    for indice in range(0, doc.page_count, max(1, doc.page_count // PAGINAS_DE_PROCEDENCIA)):
        pagina = doc[indice]
        area = pagina.rect.width * pagina.rect.height
        if area <= 0:
            continue
        amostradas += 1
        fontes |= {fonte[3] for fonte in pagina.get_fonts(full=True)}
        blocos = pagina.get_text("dict")["blocks"]
        tem_texto = any(
            "".join(s["text"] for s in linha["spans"]).strip()
            for bloco in blocos
            for linha in bloco.get("lines", [])
        )
        maior = max(
            (
                (b["bbox"][2] - b["bbox"][0]) * (b["bbox"][3] - b["bbox"][1])
                for b in blocos
                if b.get("type") == 1
            ),
            default=0.0,
        )
        if tem_texto and maior / area > 0.7:
            digitalizadas += 1

    if any("glyphless" in fonte.lower() for fonte in fontes):
        return "fonte invisível (Tesseract e afins)"
    # As fontes sintéticas que o Paper Capture cria ao vetorizar o glifo reconhecido. Entram
    # porque nem toda cópia carrega o `producer` original -- `Yusupov` passou por um redutor.
    if sum(1 for fonte in fontes if fonte.startswith("Fd")) >= 4:
        return "fontes Fd######## (Paper Capture)"
    if amostradas and digitalizadas / amostradas >= FRACAO_DIGITALIZADA:
        return "imagem de página inteira com texto por cima"
    return None


def medir_pagina(page: Any) -> PaginaDeGrade | None:
    """A geometria, a direção impressa e a direção emitida, ou `None` quando não há o que medir."""
    from ..text.boxes import Caixa
    from ..text.colunas import detectar_colunas
    from ..text.grade import (
        chaves_de_grade,
        corrida_de_exercicio,
        direcao_de,
        fracao_de_vao,
        parece_grade,
    )
    from ..text.pagina import sequencia_de_leitura
    from .texto_ordem import descidas, kendall_tau

    da_camada = _linhas_da_camada(page)
    if len(da_camada) < MIN_LINHAS:
        return None

    caixas = [Caixa(int(b[0]), int(b[1]), int(b[2]), int(b[3])) for _, b in da_camada]
    colunas = detectar_colunas(caixas)
    emitida_em = {id(caixa): i for i, caixa in enumerate(caixas)}
    numerados = [
        (int(achado.group(1)), caixa)
        for (texto, _), caixa in zip(da_camada, caixas, strict=True)
        if (achado := NUMERO_NA_LINHA.match(texto))
    ]

    impressa = emitida = None
    corrida = corrida_de_exercicio(numerados) if len(colunas) > 1 else []
    if corrida:
        chaves = chaves_de_grade(corrida, colunas=colunas)
        impressa = direcao_de([n for n, _ in corrida], chaves)
        # A mesma pergunta, feita à camada: em que direção **ela** emitiu esses mesmos números.
        # O desacordo entre as duas respostas é o que desqualifica o `tau` como árbitro da grade.
        emitida = direcao_de([n for n, _ in sorted(corrida, key=lambda a: emitida_em[id(a[1])])], chaves)

    resultado = PaginaDeGrade(
        pagina=0,
        e_grade=parece_grade(caixas, colunas=colunas),
        fracao_de_vao=round(fracao_de_vao(caixas), 4),
        colunas=len(colunas),
        direcao_impressa=impressa,
        direcao_emitida=emitida,
    )

    if descidas([b[1] for _, b in da_camada]) > max(0, len(colunas) - 1):
        return resultado  # referência fora de ordem: o `tau` mediria a camada, e não a ordenação
    posicao = {(c.x1, c.y1, c.x2, c.y2): i for i, c in enumerate(caixas)}
    if len(posicao) != len(caixas):
        return resultado  # duas linhas com o mesmo retângulo: não há como casar as ordens

    def indices(seq: Sequence[Any]) -> list[int]:
        return [posicao[(c.x1, c.y1, c.x2, c.y2)] for c in seq]

    return replace(
        resultado,
        tau_prosa=kendall_tau(indices(sequencia_de_leitura(caixas))),
        tau_grade=kendall_tau(indices(sequencia_de_leitura(caixas, arranjo="grade"))),
    )


def calibrar(paginas: Sequence[PaginaDeGrade]) -> tuple[str, int, int]:
    """`(arranjo, votos_grade, votos_prosa)` para um livro. Ver `CONCORDANCIA_MINIMA`.

    Só votam as páginas que **são** grade e cuja numeração decide. Uma página de prosa não tem
    opinião sobre a direção de uma grade, e deixá-la votar diluiria o sinal com ruído.
    """
    votos = [p.direcao_impressa for p in paginas if p.e_grade and p.direcao_impressa]
    de_grade = votos.count("grade")
    de_prosa = votos.count("prosa")
    if not votos:
        return "indefinido", 0, 0
    vencedor, quantos = ("grade", de_grade) if de_grade >= de_prosa else ("prosa", de_prosa)
    if quantos / len(votos) < CONCORDANCIA_MINIMA:
        return "indefinido", de_grade, de_prosa
    return vencedor, de_grade, de_prosa


def medir(pdfs: list[Path], *, por_livro: int) -> dict[str, Any]:
    """Uma linha por livro, e o agregado. Ver o cabeçalho para o que cada número quer dizer."""
    import fitz

    por_livro_saida: dict[str, Any] = {}
    sem_referencia: list[str] = []
    avisos: list[str] = []
    editorados: list[str] = []

    for caminho in pdfs:
        try:
            doc = fitz.open(caminho)
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro
            avisos.append(f"{caminho.name}: não abriu ({exc})")
            continue
        with doc:
            marca = camada_de_ocr(doc)
            medidas: list[PaginaDeGrade] = []
            vistas = 0
            for indice in range(doc.page_count):
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
                if resultado.e_grade:
                    medidas.append(replace(resultado, pagina=indice + 1))
        if vistas == 0:
            sem_referencia.append(caminho.name)
            continue
        if marca is None:
            editorados.append(caminho.name)
        if not medidas:
            continue

        arranjo, de_grade, de_prosa = calibrar(medidas)
        decidiveis = [p for p in medidas if p.direcao_impressa]
        concordam = sum(1 for p in decidiveis if p.direcao_emitida == p.direcao_impressa)
        com_tau = [p for p in medidas if p.tau_prosa is not None]
        por_livro_saida[caminho.name] = {
            "camada": marca or "editorado",
            "paginas_de_grade": len(medidas),
            "paginas_decidiveis": len(decidiveis),
            "arranjo": arranjo,
            "votos": {"grade": de_grade, "prosa": de_prosa},
            # A prova de que o `tau` não pode arbitrar: em quantas páginas a camada e o número
            # impresso discordam sobre a direção da própria grade.
            "emissao_contra_impresso": {
                "de_acordo": concordam,
                "contra": len(decidiveis) - concordam,
            },
            "paginas_com_tau": len(com_tau),
            "tau_prosa": (sum(p.tau_prosa or 0 for p in com_tau) / len(com_tau)) if com_tau else None,
            "tau_grade": (sum(p.tau_grade or 0 for p in com_tau) / len(com_tau)) if com_tau else None,
        }

    return _agregar(por_livro_saida, sem_referencia, editorados, avisos)


def _tau_agregado(por_livro: dict[str, Any]) -> dict[str, Any]:
    """O `tau` médio das páginas de grade sob as três leituras. Ver o cabeçalho do módulo.

    Ponderado por página, e não por livro: um livro com 4 páginas de grade não pesa o mesmo que um
    com 91, e é exatamente essa diferença de tamanho que faz o agregado ser o critério errado para
    escolher a direção.
    """
    com_tau = [v for v in por_livro.values() if v.get("paginas_com_tau")]
    total = sum(v["paginas_com_tau"] for v in com_tau)
    if not total:
        return {"paginas": 0, "prosa": None, "grade": None, "calibrado": None}

    def media(escolher: Any) -> float:
        return sum(escolher(v) * v["paginas_com_tau"] for v in com_tau) / total

    return {
        "paginas": total,
        "prosa": media(lambda v: v["tau_prosa"]),
        "grade": media(lambda v: v["tau_grade"]),
        "calibrado": media(lambda v: v["tau_grade"] if v["arranjo"] == "grade" else v["tau_prosa"]),
    }


def _agregar(
    por_livro: dict[str, Any],
    sem_referencia: list[str],
    editorados: list[str],
    avisos: list[str],
) -> dict[str, Any]:
    decidiveis = sum(v["paginas_decidiveis"] for v in por_livro.values())
    contra = sum(v["emissao_contra_impresso"]["contra"] for v in por_livro.values())
    # O acerto é medido **contra o número impresso**, e não contra a ordem emitida: uma página
    # está certa quando o `arranjo` calibrado para o livro dela é o que ela mostra impresso. O
    # livro `indefinido` não acerta nenhuma -- ele fica em `prosa` sem ter sido calibrado, e
    # contá-lo como acerto esconderia exatamente o caso que o piso de concordância existe para ver.
    acertos = sum(v["votos"][v["arranjo"]] for v in por_livro.values() if v["arranjo"] != "indefinido")
    return {
        # **A tabela que decide o item, e por isso ela mora no relatório e não só no documento.**
        # `calibrado` usa o `arranjo` de cada livro -- e `indefinido` conta como `prosa`, que é o
        # que o livro de fato recebe. Sem isso o número seria o de um mundo em que a calibração
        # acertou tudo, inclusive o que ela recusou responder.
        "tau": _tau_agregado(por_livro),
        "livros_medidos": len(por_livro),
        "livros_sem_camada_de_texto": sem_referencia,
        "livros_com_camada_editorada": editorados,
        "paginas_de_grade": sum(v["paginas_de_grade"] for v in por_livro.values()),
        "paginas_decidiveis": decidiveis,
        "acerto": (acertos / decidiveis) if decidiveis else None,
        "emissao_contra_impresso": {"de_acordo": decidiveis - contra, "contra": contra},
        "por_livro": dict(sorted(por_livro.items())),
        "avisos": avisos,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mede a direcao em que cada livro numera a grade de exercicios (S-216).",
        epilog=(
            "A referencia e o numero impresso na pagina, e nao a ordem em que o PDF emite os "
            "spans: nesta colecao essa ordem e de um motor de OCR, e ela erra a direcao da grade."
        ),
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--por-livro", type=int, default=40, help="Paginas medidas por livro (padrao 40).")
    parser.add_argument("--limite", type=int, help="So os N primeiros livros.")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Falha (codigo 1) se o acerto cair contra este relatorio.",
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
    acerto = relatorio["acerto"]
    print(
        f"{relatorio['livros_medidos']} livros, {relatorio['paginas_de_grade']} paginas de grade, "
        f"{relatorio['paginas_decidiveis']} decidiveis  "
        f"acerto {'-' if acerto is None else f'{acerto:.1%}'}"
    )
    for nome, v in relatorio["por_livro"].items():
        if v["arranjo"] != "indefinido" or v["paginas_decidiveis"]:
            print(
                f"   {v['arranjo']:10s} {v['votos']['grade']:3d}x grade / {v['votos']['prosa']:3d}x prosa   "
                f"{nome[:46]}"
            )
    tau = relatorio["tau"]
    if tau["paginas"]:
        print(
            f"tau nas {tau['paginas']} paginas de grade:  coluna a coluna {tau['prosa']:.4f}   "
            f"tudo grade {tau['grade']:.4f}   calibrado por livro {tau['calibrado']:.4f}"
        )
    contra = relatorio["emissao_contra_impresso"]["contra"]
    if contra:
        print(
            f"{contra} de {relatorio['paginas_decidiveis']} paginas em que a camada de texto "
            "discorda do numero impresso: e por isso que o tau nao arbitra a grade."
        )
    if relatorio["livros_com_camada_editorada"]:
        print(f"{len(relatorio['livros_com_camada_editorada'])} livro(s) com camada nao-OCR.")
    else:
        print("Nenhum livro deste acervo tem camada de texto editorada: todas sao de OCR.")

    if args.baseline:
        if not args.baseline.exists():
            logger.error("O baseline %s não existe.", args.baseline)
            return 1
        antes = json.loads(args.baseline.read_text(encoding="utf-8")).get("acerto")
        if antes is not None and acerto is not None and acerto < antes - QUEDA_TOLERADA:
            logger.error(
                "A calibração piorou: acerto %.1f%% contra %.1f%% do baseline (tolerância %.0f p.p.).",
                acerto * 100,
                antes * 100,
                QUEDA_TOLERADA * 100,
            )
            return 1
    return 0


__all__ = ["PaginaDeGrade", "calibrar", "camada_de_ocr", "main", "medir", "medir_pagina", "parse_args"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
