"""`cvoff-texto-duas-linhas` — o ganho do corte de linha, medido neste acervo (S-198).

    cvoff-texto-duas-linhas --por-livro 3
    cvoff-texto-duas-linhas --baseline docs/metrics/texto_duas_linhas.json

**O código da S-198 existe desde 2026-08-22 e não é chamado por ninguém.** `duas_linhas.separar`
e `duas_linhas.descartar_fragmentos` estão implementados e travados por teste, e o
`GlyphRecognizer` não os usa. Isso não é esquecimento: os dois dependem de um árbitro, o árbitro
é o classificador, e o classificador não existia nesta máquina. Este comando é o número que
decide se eles entram no caminho de leitura.

## A faixa é dilatada de propósito, e é assim que o defeito aparece

O defeito da S-198 não acontece numa faixa justa: ele acontece quando a faixa que se manda ler
**encosta na linha de cima**. É o que a `ocr_caption` produz de verdade, e a medição da S-185
registrou o preço com estes números, na página 21 do `AAGAARD`:

    S-184/S-185/S-187, faixa justa            CER 0,14
    S-184/S-185/S-187, faixa dilatada em 2pt  CER 0,22   <- +8 pontos

Aqui a faixa de cada linha da camada de texto é dilatada nos mesmos **2 pt**, e a referência é o
que a camada diz que está escrito nela. A comparação é contra o mesmo defeito, no acervo inteiro
em vez de numa página.

## Três braços, e o terceiro é o do item

| braço | o que ele faz |
|---|---|
| `cru` | o `GlyphRecognizer` como ele é hoje |
| `descarte` | `descartar_fragmentos`: a "linha" que é só pedaço de descendente some |
| `descarte_e_corte` | mais `separar`: a caixa alta demais é partida no vale, com o árbitro confirmando |

**Os dois são medidos separados porque são defeitos diferentes.** O descarte tira linha que não
devia existir; o corte conserta caixa que engoliu duas. Somar os dois num número só esconderia
qual deles paga.

## O livro cuja camada é de OCR fica de fora, e isso não é preciosismo

Metade deste acervo é digitalização com texto por cima -- `camada_de_ocr` diz qual, pela marca do
`producer`, pela fonte sintética do Paper Capture ou pela página que é um bitmap inteiro. Nesses
livros a camada **é o palpite de outro motor de OCR**, e medir CER contra ela seria comparar dois
chutes e chamar o resultado de erro. É a mesma circularidade que a S-183 recusou para a legenda.

Eles saem nomeados no relatório, com a marca que os denunciou, junto dos que não têm camada
nenhuma.

## A régua é uma probabilidade, e por isso ela não atravessa uma calibração

`GANHO_MINIMO` compara a confiança dos dois pedaços contra a do inteiro, e confiança é uma escala
que a temperatura move. O relatório grava a temperatura com que mediu, e
`tests/test_text_duas_linhas.py` falha quando o modelo publicado passa a ter outra -- o limiar
tem de ser remedido, não herdado.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_json
from ..config import DEFAULT_PDF_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging
from . import EXIT_FAILURE, add_verbose, cli_errors, confere_baseline
from .texto_grade import camada_de_ocr
from .texto_placar import cer

logger = logging.getLogger(__name__)

SAIDA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_duas_linhas.json"

DPI = 220.0
"""O mesmo do `cvoff-texto-vertical` e da varredura de produção."""

RAIO_PT = 2.0
"""A dilatação da faixa, em pontos do PDF. **É o número da medição da S-185**, e não uma escolha.

Com faixa justa o defeito não aparece; com os 60 pt da `ocr_caption` em volta de um diagrama a
faixa engole linhas inteiras e a referência de uma linha deixa de fazer sentido. 2 pt é o que
faz o descendente da linha de cima entrar -- que é o caso do item."""

MIN_CARACTERES = 12
"""Linha curta demais tem CER instável: um caractere errado em quatro vale 0,25."""

PIORA_TOLERADA = 0.02
"""Quanto o CER pode subir contra o `--baseline` antes de o comando falhar."""


def faixas_da_camada(page: Any) -> list[tuple[str, tuple[float, float, float, float]]]:
    """`(texto, bbox em pontos)` de cada linha que a camada declara, já dilatada em `RAIO_PT`."""
    saida = []
    for bloco in page.get_text("dict").get("blocks", []):
        for linha in bloco.get("lines", []):
            texto = "".join(trecho.get("text", "") for trecho in linha.get("spans", []))
            if len(texto.strip()) < MIN_CARACTERES:
                continue
            x0, y0, x1, y1 = linha["bbox"]
            saida.append((texto, (x0 - RAIO_PT, y0 - RAIO_PT, x1 + RAIO_PT, y1 + RAIO_PT)))
    return saida


def _arbitro_de_caixas(cinza: np.ndarray, classificador: Any) -> Any:
    """O árbitro que `duas_linhas.partir` espera: caixas -> confiança média delas."""

    def julgar(caixas: Sequence[Any]) -> float:
        recortes = [c.recortar(cinza) for c in caixas]
        recortes = [r for r in recortes if r.size]
        if not recortes:
            return 0.0
        lidos = classificador.classificar(recortes)
        return float(sum(c for _, c in lidos) / len(lidos)) if lidos else 0.0

    return julgar


def ler_faixa(cinza: np.ndarray, classificador: Any, *, descartar: bool, cortar: bool) -> tuple[str, int]:
    """A faixa lida por um dos três braços. Devolve `(texto, caixas partidas)`.

    O caminho é o do `GlyphRecognizer`, aberto aqui para que os dois passos da S-198 possam ser
    ligados um de cada vez -- que é o que a tabela do item pede.
    """
    from ..text.binarizacao import binarize
    from ..text.boxes import caixas_de_caractere, escala_de_texto, unir_pingos
    from ..text.duas_linhas import descartar_fragmentos, separar
    from ..text.linhas import ordem_em_faixa, quebrar_em_linhas, texto_da_linha

    binaria = binarize(cinza)
    escala = escala_de_texto(binaria)
    if escala <= 0:
        return "", 0
    caixas = unir_pingos(caixas_de_caractere(binaria, escala=escala), escala=escala)

    partidas = 0
    if cortar:
        antes = len(caixas)
        caixas = separar(
            binaria, caixas, escala=escala, arbitro=_arbitro_de_caixas(cinza, classificador)
        )
        partidas = len(caixas) - antes

    grupos = quebrar_em_linhas(ordem_em_faixa(caixas))
    if descartar:
        grupos = descartar_fragmentos(grupos, escala=escala)
    if not grupos:
        return "", partidas

    linhas = []
    for grupo in grupos:
        lidos = classificador.classificar([c.recortar(cinza) for c in grupo])
        if lidos:
            linhas.append(texto_da_linha(grupo, [char for char, _ in lidos]))
    return " ".join(t for t in linhas if t), partidas


BRACOS = (
    ("cru", {"descartar": False, "cortar": False}),
    ("descarte", {"descartar": True, "cortar": False}),
    ("descarte_e_corte", {"descartar": True, "cortar": True}),
)
"""Os três braços, e a ordem importa: cada um acrescenta um passo ao anterior."""


def recorte_da_faixa(page: Any, bbox: tuple[float, float, float, float]) -> np.ndarray:
    import cv2
    import fitz

    escala = DPI / 72.0
    faixa = fitz.Rect(*bbox) & page.rect
    if faixa.is_empty:
        return np.zeros((0, 0), dtype=np.uint8)
    pix = page.get_pixmap(matrix=fitz.Matrix(escala, escala), clip=faixa, alpha=False)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)


def medir(pdfs: list[Path], *, por_livro: int, por_pagina: int, classificador: Any) -> dict[str, Any]:
    """O CER dos três braços sobre as faixas dilatadas do acervo."""
    import fitz

    soma = {nome: 0.0 for nome, _ in BRACOS}
    medido: dict[str, dict[str, Any]] = {}
    sem_camada: list[str] = []
    com_ocr: dict[str, str] = {}
    avisos: list[str] = []
    total = 0
    partidas = 0
    faixas_com_corte = 0

    for caminho in pdfs:
        try:
            doc = fitz.open(caminho)
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro
            avisos.append(f"{caminho.name}: não abriu ({exc})")
            continue
        with doc:
            # **A camada de OCR não é referência de conteúdo, e usá-la seria medir o nosso
            # motor contra o palpite de outro.** É a mesma circularidade que a S-183 recusou
            # para a legenda: lá a camada seria "a verdade do conteúdo", e é justamente uma das
            # fontes medidas. Para *localizar* linha ela serviria; para dizer o que está escrito
            # nelas, não. O livro sai nomeado, com a marca que o denunciou.
            marca = camada_de_ocr(doc)
            if marca:
                com_ocr[caminho.name] = marca
                continue

            deste_livro = 0
            paginas = 0
            por_livro_cer = {nome: 0.0 for nome, _ in BRACOS}
            for indice in range(int(doc.page_count * 0.15), doc.page_count):
                if paginas >= por_livro:
                    break
                try:
                    page = doc[indice]
                    faixas = faixas_da_camada(page)
                except Exception as exc:  # noqa: BLE001 - idem
                    avisos.append(f"{caminho.name} p.{indice + 1}: {exc}")
                    continue
                if not faixas:
                    continue
                paginas += 1
                passo = max(1, len(faixas) // por_pagina)
                for texto, bbox in faixas[::passo][:por_pagina]:
                    cinza = recorte_da_faixa(page, bbox)
                    if cinza.size == 0:
                        continue
                    cortou = 0
                    for nome, modo in BRACOS:
                        lido, novas = ler_faixa(cinza, classificador, **modo)
                        erro = cer(lido, texto)
                        if erro == float("inf"):
                            erro = 1.0
                        soma[nome] += erro
                        por_livro_cer[nome] += erro
                        cortou = max(cortou, novas)
                    partidas += cortou
                    faixas_com_corte += int(cortou > 0)
                    total += 1
                    deste_livro += 1
            if deste_livro:
                medido[caminho.name] = {
                    "faixas": deste_livro,
                    "cer": {nome: por_livro_cer[nome] / deste_livro for nome, _ in BRACOS},
                }
            else:
                sem_camada.append(caminho.name)
        logger.info("%s: %d faixa(s).", caminho.name, deste_livro)

    if not total:
        raise ValueError("nenhuma faixa medida: os PDFs deste acervo têm camada de texto?")

    medias = {nome: soma[nome] / total for nome, _ in BRACOS}
    return {
        "dpi": DPI,
        "raio_pt": RAIO_PT,
        "faixas": total,
        "livros_medidos": len(medido),
        "livros_sem_camada_de_texto": sem_camada,
        "livros_com_camada_de_ocr": dict(sorted(com_ocr.items())),
        "cer": medias,
        # Positivo é ganho: o CER cai quando o passo ajuda.
        "ganho": {
            "descarte": medias["cru"] - medias["descarte"],
            "corte": medias["descarte"] - medias["descarte_e_corte"],
            "total": medias["cru"] - medias["descarte_e_corte"],
        },
        "faixas_com_corte": faixas_com_corte,
        "caixas_partidas": partidas,
        "por_livro": dict(sorted(medido.items())),
        "avisos": avisos,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mede o ganho do corte de linha e do descarte de fragmento (S-198).",
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta do acervo de livros.")
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="Onde gravar o relatório desta medição.")
    parser.add_argument("--por-livro", type=int, default=3, help="Paginas medidas por livro (padrao 3).")
    parser.add_argument("--por-pagina", type=int, default=6, help="Faixas medidas por pagina (padrao 6).")
    parser.add_argument("--limite", "--limit", type=int, help="So os N primeiros livros.")
    parser.add_argument("--modelo", type=Path, help="Pesos. Padrao: ao lado do char_meta.json.")
    parser.add_argument("--baseline", type=Path, help="Relatorio anterior: falha se o CER subir.")
    add_verbose(parser)
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    from ..text.duas_linhas import ALTURA_SUSPEITA, FRAGMENTO_ALTURA, GANHO_MINIMO
    from ..text.modelo import carregar_classificador

    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    if (codigo := confere_baseline(args.baseline)) is not None:
        return codigo

    pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))
    if args.limite:
        pdfs = pdfs[: args.limite]
    if not pdfs:
        logger.warning("Nenhum PDF em %s. Nada a medir.", args.pdf_dir)
        return 0

    classificador = carregar_classificador(pesos=args.modelo)
    logger.info("Medindo %d livro(s) com o classificador em %s.", len(pdfs), classificador.device)

    relatorio = medir(
        pdfs, por_livro=args.por_livro, por_pagina=args.por_pagina, classificador=classificador
    )
    # **A régua é uma probabilidade.** Gravar a temperatura ao lado dos limiares é o que permite
    # ao teste dizer, depois de um retreino, que este número descreve outro modelo.
    relatorio["modelo"] = {
        "classes": classificador.meta.num_classes,
        "temperatura": classificador.meta.temperatura,
        "modelo_sha256": classificador.meta.modelo_sha256,
    }
    relatorio["limiares"] = {
        "ganho_minimo": GANHO_MINIMO,
        "altura_suspeita": ALTURA_SUSPEITA,
        "fragmento_altura": FRAGMENTO_ALTURA,
    }

    atomic_write_json(Path(args.saida), relatorio)

    print(f"\n{relatorio['faixas']} faixas de {relatorio['livros_medidos']} livro(s), dilatadas em {RAIO_PT} pt\n")
    for nome, _ in BRACOS:
        print(f"  {nome:20s} CER {relatorio['cer'][nome]:.4f}")
    print(
        f"\n  ganho do descarte {relatorio['ganho']['descarte']:+.4f}"
        f"   ganho do corte {relatorio['ganho']['corte']:+.4f}"
    )
    print(f"  {relatorio['caixas_partidas']} caixa(s) partida(s) em {relatorio['faixas_com_corte']} faixa(s)")
    print(f"\nRelatorio em {Path(args.saida)}")

    if args.baseline:
        anterior = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        for nome, _ in BRACOS:
            antes = anterior["cer"][nome]
            agora = relatorio["cer"][nome]
            if agora > antes + PIORA_TOLERADA:
                logger.error("Regressao no braco %s: CER %.4f contra %.4f do baseline.", nome, agora, antes)
                return EXIT_FAILURE

    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
