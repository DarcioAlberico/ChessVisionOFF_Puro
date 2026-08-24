"""`cvoff-texto-colados` — o separador de glifo colado, medido antes de ser ligado (S-186).

    cvoff-texto-colados --por-livro 3

**Este comando existe para decidir se o separador deve ficar desligado.** No projeto de origem,
depois que as classes de ligadura entraram no modelo, a vantagem dele caiu de +0,3 para +0,1 de
F1 e os cortes bons de 23 para 13 — o modelo lê `fi`, `e4` e `xf6` inteiros, e o que sobra para
o separador é pouco. Portar e ligar seria herdar um ganho que já estava evaporando lá.

## Três modos, e a tabela é sobre eles

| modo | o que faz |
|---|---|
| `nunca` | não toca em nada. **É o padrão**, até esta tabela dizer o contrário |
| `auto` | a geometria propõe o corte, o classificador confirma pela confiança dos dois pedaços |
| `sempre` | corta onde houver vale, sem perguntar |

**A linha do `sempre` é o preço de ignorar o árbitro**, e ela está aqui por isso: separar sem
confirmação custou 2,3 pontos de F1 no projeto de origem, e um número herdado que ninguém remede
vira folclore.

## A referência, e por que ela não é a da S-183

O critério de aceite do item pede a tabela sobre o conjunto de referência da S-183 — as 123
faixas de legenda transcritas à mão. **Elas não existem ainda**: as 123 estão semeadas com
`conferido: false`, e a medição as recusa, que é o desenho certo.

O que existe é a referência que a S-198 estabeleceu e que é independente do que se mede: a
**camada de texto editorada** dos 11 livros que não são digitalização com OCR por cima. É a mesma
faixa, o mesmo recorte e o mesmo CER — o que muda entre as três linhas é só o modo. Quando a
S-183 tiver a referência humana, esta tabela pode ser refeita sobre ela, e a comparação entre as
duas dirá mais do que qualquer uma sozinha.
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
from ..text import colados
from . import cli_errors
from .texto_duas_linhas import DPI, RAIO_PT, faixas_da_camada, recorte_da_faixa
from .texto_grade import camada_de_ocr
from .texto_placar import cer

logger = logging.getLogger(__name__)

SAIDA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_colados.json"

MODOS_MEDIDOS = (colados.NUNCA, colados.AUTO, colados.SEMPRE)


def _arbitro_de_caixas(cinza: np.ndarray, classificador: Any) -> Any:
    """Caixas -> confiança média delas. O mesmo árbitro que a S-198 usa, e de propósito."""

    def julgar(caixas: Any) -> float:
        recortes = [c.recortar(cinza) for c in caixas]
        recortes = [r for r in recortes if r.size]
        if not recortes:
            return 0.0
        lidos = classificador.classificar(recortes)
        return float(sum(c for _, c in lidos) / len(lidos)) if lidos else 0.0

    return julgar


def ler_faixa(cinza: np.ndarray, classificador: Any, *, modo: str) -> tuple[str, int]:
    """A faixa lida com o separador num dos três modos. Devolve `(texto, caixas partidas)`.

    O resto do caminho é o do `GlyphRecognizer` **como ele está hoje**, com o descarte de
    fragmento da S-198 ligado: medir o separador sobre um pipeline diferente do de produção
    mediria os dois.
    """
    from ..text.binarizacao import binarize
    from ..text.boxes import caixas_de_caractere, escala_de_texto, unir_pingos
    from ..text.duas_linhas import descartar_fragmentos
    from ..text.linhas import ordem_em_faixa, quebrar_em_linhas, texto_da_linha

    binaria = binarize(cinza)
    escala = escala_de_texto(binaria)
    if escala <= 0:
        return "", 0
    caixas = unir_pingos(caixas_de_caractere(binaria, escala=escala), escala=escala)

    antes = len(caixas)
    caixas = colados.separar(
        binaria, caixas, escala=escala, arbitro=_arbitro_de_caixas(cinza, classificador), modo=modo
    )
    partidas = len(caixas) - antes

    grupos = descartar_fragmentos(quebrar_em_linhas(ordem_em_faixa(caixas)), escala=escala)
    linhas = []
    for grupo in grupos:
        lidos = classificador.classificar([c.recortar(cinza) for c in grupo])
        if lidos:
            linhas.append(texto_da_linha(grupo, [char for char, _ in lidos]))
    return " ".join(t for t in linhas if t), partidas


def _varrer_limiar(
    faixas: list[tuple[str, np.ndarray]], classificador: Any, limiares: list[float]
) -> list[dict[str, Any]]:
    """O braço `auto` refeito em vários `LARGURA_SUSPEITA`. **É o que separa achado de desafino.**

    Sem isto, "o separador piora o CER" é indistinguível de "o limiar de largura estava mal
    escolhido". Com a varredura, ou a conclusão sobrevive a todos os limiares ou ela era do
    limiar -- e nos dois casos o número está no relatório.
    """
    original = colados.LARGURA_SUSPEITA
    saida: list[dict[str, Any]] = []
    try:
        for limiar in limiares:
            colados.LARGURA_SUSPEITA = limiar
            soma, cortes = 0.0, 0
            for texto, cinza in faixas:
                lido, partidas = ler_faixa(cinza, classificador, modo=colados.AUTO)
                erro = cer(lido, texto)
                soma += 1.0 if erro == float("inf") else erro
                cortes += partidas
            saida.append(
                {"largura_suspeita": limiar, "cer": soma / len(faixas), "cortes": cortes}
            )
    finally:
        colados.LARGURA_SUSPEITA = original
    return saida


def medir(
    pdfs: list[Path],
    *,
    por_livro: int,
    por_pagina: int,
    classificador: Any,
    limiares: list[float] | None = None,
) -> dict[str, Any]:
    """O CER dos três modos sobre as mesmas faixas da S-198."""
    import fitz

    soma = dict.fromkeys(MODOS_MEDIDOS, 0.0)
    cortes = dict.fromkeys(MODOS_MEDIDOS, 0)
    faixas_com_corte = dict.fromkeys(MODOS_MEDIDOS, 0)
    com_ocr: dict[str, str] = {}
    sem_camada: list[str] = []
    avisos: list[str] = []
    total = 0
    medido = 0
    guardadas: list[tuple[str, np.ndarray]] = []

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
            deste_livro = 0
            paginas = 0
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
                    guardadas.append((texto, cinza))
                    for modo in MODOS_MEDIDOS:
                        lido, partidas = ler_faixa(cinza, classificador, modo=modo)
                        erro = cer(lido, texto)
                        soma[modo] += 1.0 if erro == float("inf") else erro
                        cortes[modo] += partidas
                        faixas_com_corte[modo] += int(partidas > 0)
                    total += 1
                    deste_livro += 1
            if deste_livro:
                medido += 1
            elif not marca:
                sem_camada.append(caminho.name)
        logger.info("%s: %d faixa(s).", caminho.name, deste_livro if not marca else 0)

    if not total:
        raise ValueError("nenhuma faixa medida: os PDFs deste acervo têm camada editorada?")

    medias = {modo: soma[modo] / total for modo in MODOS_MEDIDOS}
    return {
        "quando": f"{date.today():%Y-%m-%d}",
        "dpi": DPI,
        "raio_pt": RAIO_PT,
        "faixas": total,
        "livros_medidos": medido,
        "livros_com_camada_de_ocr": dict(sorted(com_ocr.items())),
        "livros_sem_camada_de_texto": sem_camada,
        "referencia": (
            "camada de texto editorada (nao-OCR). A referencia da S-183 -- as 123 faixas "
            "transcritas a mao -- ainda nao existe: elas estao semeadas com conferido=false."
        ),
        "cer": medias,
        "ganho_do_auto": medias[colados.NUNCA] - medias[colados.AUTO],
        "custo_do_sempre": medias[colados.SEMPRE] - medias[colados.NUNCA],
        "cortes": {modo: cortes[modo] for modo in MODOS_MEDIDOS},
        "faixas_com_corte": {modo: faixas_com_corte[modo] for modo in MODOS_MEDIDOS},
        "limiares": {
            "largura_suspeita": colados.LARGURA_SUSPEITA,
            "ganho_minimo": colados.GANHO_MINIMO,
            "padrao": colados.PADRAO,
        },
        "varredura_do_limiar": _varrer_limiar(guardadas, classificador, limiares or []),
        "avisos": avisos,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mede o separador de glifo colado nos tres modos, antes de liga-lo (S-186).",
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--por-livro", type=int, default=3, help="Paginas medidas por livro.")
    parser.add_argument("--por-pagina", type=int, default=6, help="Faixas medidas por pagina.")
    parser.add_argument("--limite", type=int, help="So os N primeiros livros.")
    parser.add_argument("--modelo", type=Path, help="Pesos. Padrao: ao lado do char_meta.json.")
    parser.add_argument(
        "--limiares",
        type=float,
        nargs="*",
        default=[1.35, 1.6, 1.8, 2.0, 2.5],
        help="Larguras suspeitas em que o braco `auto` e refeito. Vazio desliga a varredura.",
    )
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
        logger.warning("Nenhum PDF em %s. Nada a medir.", args.pdf_dir)
        return 0

    classificador = carregar_classificador(pesos=args.modelo)
    logger.info("Medindo %d livro(s) com o classificador em %s.", len(pdfs), classificador.device)

    relatorio = medir(
        pdfs,
        por_livro=args.por_livro,
        por_pagina=args.por_pagina,
        classificador=classificador,
        limiares=args.limiares,
    )
    relatorio["modelo"] = {
        "classes": classificador.meta.num_classes,
        "temperatura": classificador.meta.temperatura,
        "modelo_sha256": classificador.meta.modelo_sha256,
    }
    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        Path(args.saida), json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n{relatorio['faixas']} faixas de {relatorio['livros_medidos']} livro(s)\n")
    print("  modo       CER      cortes   faixas com corte")
    for modo in MODOS_MEDIDOS:
        print(
            f"  {modo:8s} {relatorio['cer'][modo]:7.4f}   {relatorio['cortes'][modo]:6d}   "
            f"{relatorio['faixas_com_corte'][modo]:6d}"
        )
    print(
        f"\n  ganho do auto {relatorio['ganho_do_auto']:+.4f}   "
        f"custo do sempre {relatorio['custo_do_sempre']:+.4f}"
    )
    if relatorio["varredura_do_limiar"]:
        print()
        print("  largura suspeita   CER do auto   cortes")
        for linha in relatorio["varredura_do_limiar"]:
            print(
                f"  {linha['largura_suspeita']:16.2f}   {linha['cer']:11.4f}   "
                f"{linha['cortes']:6d}"
            )
    print(f"\nrelatorio-> {args.saida}")
    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
