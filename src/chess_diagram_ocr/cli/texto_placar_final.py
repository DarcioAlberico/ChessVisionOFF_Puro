"""`cvoff-texto-placar-final` — as duas réguas lado a lado, sempre (S-206).

    cvoff-texto-placar-final --por-livro 2

**Publicar "99,1% de acerto" sobre recorte já segmentado quando a página real dá outro número é a
forma de número enganoso que este projeto já cometeu e corrigiu.** Os dois números são verdadeiros
e medem coisas diferentes, e **a distância entre eles é o trabalho que sobra**.

| régua | sobre o quê | o que ela não diz |
|---|---|---|
| acurácia do classificador | recorte já segmentado, split de teste | nada sobre **achar** o recorte |
| CER da página | página real, com o diagrama excluído pelo detector | é a que conta para o usuário |
| livro novo | um livro que o treino não viu | **não existe nesta base** — ver abaixo |

## A terceira coluna não existe, e o relatório diz isso em vez de omiti-la

O item pede uma coluna para o **livro novo**, e ela é o único número que fala sobre fonte nova.
Esta base não a tem: os recortes de `training_data/` não registram livro (S-203), então nenhum
split desta fase deixa um livro inteiro de fora. A coluna sai `null` com o motivo escrito ao lado
— omiti-la faria a tabela parecer completa.

## A régua da página é a pipeline inteira, e não uma faixa

A régua de recorte mede o classificador; a da faixa (S-198, S-186, S-188) mede segmentação de
linha. **Esta mede a página**: renderizar, detectar diagrama e excluí-lo, binarizar, achar caixa,
quebrar em linha, classificar. É o que o usuário recebe.

A referência é a **camada de texto editorada** — os livros que não são digitalização com OCR por
cima. É a mesma escolha da S-198, pelo mesmo motivo: medir contra uma camada de OCR seria comparar
dois palpites.

## O comando recusa publicar só a régua de recorte

Se a régua da página não puder ser medida, o comando **falha** em vez de gravar a metade
lisonjeira. É o critério de aceite do item, e é a única forma de a regra sobreviver a uma pressa.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_text
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from . import cli_errors
from .texto_grade import camada_de_ocr
from .texto_placar import cer

logger = logging.getLogger(__name__)

METRICAS = PROJECT_ROOT / "docs" / "metrics"
SAIDA_PADRAO = METRICAS / "texto_placar_final.json"
DPI = 220.0

SEM_LIVRO = (
    "esta base nao registra livro de origem (S-203), entao nenhum split deixa um livro inteiro "
    "de fora e nenhum numero desta fase mede generalizacao de fonte"
)


def regua_do_recorte(meta_sha: str) -> dict[str, Any]:
    """A acurácia do classificador, lida do relatório de treino que descreve o par publicado.

    **Casa pelo `modelo_sha256`**, e não pela data do arquivo: há quatro relatórios de treino em
    `docs/metrics/`, e três descrevem modelos que não estão em `models/`. Pegar o mais recente
    publicaria o número de outro modelo.
    """
    for caminho in sorted(METRICAS.glob("texto_treino_*.json"), reverse=True):
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if dados.get("modelo_sha256") == meta_sha:
            return {
                "relatorio": caminho.name,
                "macro": dados["metricas"]["teste_macro"],
                "acuracia": dados["metricas"]["teste_acuracia"],
                "n": dados["amostras"]["teste"],
                "split": dados.get("split", ""),
            }
    raise ValueError(
        "nenhum relatorio de treino em docs/metrics/ descreve o modelo publicado. Sem a regua do "
        "recorte nao ha o que comparar: rode `cvoff-texto-train` ou aponte o par certo."
    )


def _texto_da_pagina(page: Any) -> str:
    """Tudo que a camada de texto declara na página, na ordem em que ela emite."""
    partes = []
    for bloco in page.get_text("dict").get("blocks", []):
        for linha in bloco.get("lines", []):
            partes.append("".join(t.get("text", "") for t in linha.get("spans", [])))
    return " ".join(p for p in partes if p.strip())


def ler_pagina(page: Any, classificador: Any, *, pdf: Path) -> str:
    """A página inteira pela pipeline de produção, com o diagrama excluído pelo detector.

    **É o que o usuário recebe**, e é por isso que a detecção entra: sem excluir o diagrama, as
    filas de peças viram texto e o número mede outra coisa.
    """
    import cv2
    import fitz

    from ..detection import detect_diagrams_in_pdf_page
    from ..text.binarizacao import binarize
    from ..text.boxes import caixas_de_caractere, escala_de_texto, excluir_diagramas, unir_pingos
    from ..text.duas_linhas import descartar_fragmentos
    from ..text.linhas import ordem_em_faixa, quebrar_em_linhas, texto_da_linha

    escala_px = DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(escala_px, escala_px), alpha=False)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    cinza = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)

    diagramas: list[tuple[float, float, float, float]] = []
    try:
        # **O caminho, e não `page.parent`.** O detector abre o documento por conta própria, e
        # um `fitz.Document` passado como fonte vira uma tentativa de abrir um arquivo chamado
        # `Document(...)` -- que falha, cai no `except`, e a página passa a ser medida **sem**
        # exclusão de diagrama. O número saía inflado e nada dizia isso.
        for candidato in detect_diagrams_in_pdf_page(pdf, page.number, rgb):
            if candidato.bbox_pdf:
                x0, y0, x1, y1 = candidato.bbox_pdf
                diagramas.append(
                    (x0 * escala_px, y0 * escala_px, x1 * escala_px, y1 * escala_px)
                )
    except Exception:  # noqa: BLE001 - o detector é caro e de outro subsistema
        logger.exception("A detecção falhou nesta página; ela entra sem exclusão de diagrama.")
        diagramas = []

    binaria = binarize(cinza)
    escala = escala_de_texto(binaria)
    if escala <= 0:
        return ""
    caixas = unir_pingos(caixas_de_caractere(binaria, escala=escala), escala=escala)
    if diagramas:
        caixas = excluir_diagramas(caixas, diagramas, escala=escala)
    grupos = descartar_fragmentos(quebrar_em_linhas(ordem_em_faixa(caixas)), escala=escala)

    linhas = []
    for grupo in grupos:
        lidos = classificador.classificar([c.recortar(cinza) for c in grupo])
        if lidos:
            linhas.append(texto_da_linha(grupo, [char for char, _ in lidos]))
    return " ".join(t for t in linhas if t)


def _precisao_e_recall(lido: str, referencia: str) -> tuple[float, float]:
    """Precisão e recall de **caractere**, por multiconjunto.

    **É uma aproximação, e ela é declarada.** A régua forte exige rótulo por box -- saber que
    *aquele* recorte era um `e` --, e isso é anotação humana que a S-212 ainda vai produzir. O que
    a camada de texto permite é comparar quantos caracteres de cada tipo saíram contra quantos
    deviam sair: um motor que inventa caractere perde precisão, um que perde caractere perde
    recall, e a ordem não entra na conta.
    """
    from collections import Counter

    saiu, devia = Counter(lido.split()), Counter(referencia.split())
    saiu = Counter("".join(lido.split()))
    devia = Counter("".join(referencia.split()))
    acertos = sum((saiu & devia).values())
    precisao = acertos / sum(saiu.values()) if saiu else 0.0
    recall = acertos / sum(devia.values()) if devia else 0.0
    return precisao, recall


def regua_da_pagina(pdfs: list[Path], *, por_livro: int, classificador: Any) -> dict[str, Any]:
    """O CER, a precisão e a recall de caractere sobre páginas inteiras de camada editorada."""
    import fitz

    soma_cer = soma_p = soma_r = 0.0
    paginas = 0
    livros = 0
    com_ocr: dict[str, str] = {}
    avisos: list[str] = []

    for caminho in pdfs:
        try:
            doc = fitz.open(caminho)
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro
            avisos.append(f"{caminho.name}: não abriu ({exc})")
            continue
        with doc:
            marca = camada_de_ocr(doc)
            if marca:
                com_ocr[caminho.name] = marca
                continue
            deste = 0
            for indice in range(int(doc.page_count * 0.15), doc.page_count):
                if deste >= por_livro:
                    break
                page = doc[indice]
                referencia = _texto_da_pagina(page)
                if len(referencia.strip()) < 200:
                    continue  # página de rosto, de guarda, ou só diagrama: não há o que medir
                try:
                    lido = ler_pagina(page, classificador, pdf=caminho)
                except Exception as exc:  # noqa: BLE001 - idem
                    avisos.append(f"{caminho.name} p.{indice + 1}: {exc}")
                    continue
                erro = cer(lido, referencia)
                soma_cer += 1.0 if erro == float("inf") else erro
                precisao, recall = _precisao_e_recall(lido, referencia)
                soma_p += precisao
                soma_r += recall
                paginas += 1
                deste += 1
            if deste:
                livros += 1
        logger.info("%s: %d pagina(s).", caminho.name, 0 if marca else deste)

    if not paginas:
        raise ValueError(
            "nenhuma pagina medida. **Este comando recusa publicar so a regua do recorte** -- e o "
            "criterio de aceite da S-206, e a metade lisonjeira sozinha e o defeito que ele evita."
        )

    precisao = soma_p / paginas
    recall = soma_r / paginas
    return {
        "cer": soma_cer / paginas,
        "precisao": precisao,
        "recall": recall,
        "f1": (2 * precisao * recall / (precisao + recall)) if (precisao + recall) else 0.0,
        "n": paginas,
        "livros": livros,
        "referencia": "camada de texto editorada (nao-OCR)",
        "livros_com_camada_de_ocr": dict(sorted(com_ocr.items())),
        "avisos": avisos,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="As duas reguas lado a lado: o classificador e a pagina (S-206).",
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--por-livro", type=int, default=2, help="Paginas medidas por livro.")
    parser.add_argument("--limite", type=int, help="So os N primeiros livros.")
    parser.add_argument("--modelo", type=Path, help="Pesos do classificador.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    from ..text.modelo import carregar_classificador

    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))
    if args.limite:
        pdfs = pdfs[: args.limite]
    if not pdfs:
        raise ValueError(f"nenhum PDF em {args.pdf_dir}: sem pagina nao ha a segunda regua.")

    classificador = carregar_classificador(pesos=args.modelo)
    do_recorte: dict[str, Any] = regua_do_recorte(classificador.meta.modelo_sha256)
    da_pagina: dict[str, Any] = regua_da_pagina(
        pdfs, por_livro=args.por_livro, classificador=classificador
    )

    distancia: dict[str, Any] = {
        "acuracia_do_recorte": do_recorte["acuracia"],
        "acerto_na_pagina": 1.0 - min(1.0, da_pagina["cer"]),
        "o_que_ela_e": (
            "trabalho de segmentacao pendente: o classificador acerta o recorte que lhe dao, e o "
            "que a pagina perde esta em achar o recorte. Os itens que atacam isso sao a S-186 "
            "(glifo colado), a S-188 (leitura por linha) e a S-197 (texto girado)."
        ),
    }
    relatorio = {
        "quando": f"{date.today():%Y-%m-%d}",
        "modelo_sha256": classificador.meta.modelo_sha256,
        "temperatura": classificador.meta.temperatura,
        # **As duas no mesmo objeto, e nunca uma sem a outra.** Ver
        # `test_o_relatorio_traz_as_duas_reguas`.
        "regua_do_recorte": do_recorte,
        "regua_da_pagina": da_pagina,
        "livro_novo": {"macro": None, "cer": None, "n": 0, "por_que_nao_existe": SEM_LIVRO},
        "distancia": distancia,
    }
    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        Path(args.saida), json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print("  regua                          valor        n")
    print(f"  acuracia do classificador   {do_recorte['acuracia']:8.4f}   {do_recorte['n']:6d} recortes")
    print(f"  macro do classificador      {do_recorte['macro']:8.4f}   {do_recorte['n']:6d} recortes")
    print(f"  CER da pagina               {da_pagina['cer']:8.4f}   {da_pagina['n']:6d} paginas")
    print(f"  F1 de caractere na pagina   {da_pagina['f1']:8.4f}   {da_pagina['n']:6d} paginas")
    print(f"  livro novo                       n/d        0   ({SEM_LIVRO})")
    print()
    print(
        f"  a distancia entre as duas: {do_recorte['acuracia']:.4f} no recorte contra "
        f"{1.0 - min(1.0, da_pagina['cer']):.4f} na pagina."
    )
    print(f"  {distancia['o_que_ela_e']}")
    print(f"\nrelatorio-> {args.saida}")
    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
