"""`cvoff-texto-linha` — o ganho de ler a linha em vez do caractere, medido aqui (S-188/S-189).

    cvoff-texto-linha --motor rapidocr

**O número que este comando existe para refazer** é o maior deste plano: 72,8% por caractere
contra 91,2% por linha, medido no projeto de origem em 6.953 caracteres de 275 linhas. Ele nunca
foi medido neste acervo, e a spec inteira o trata como hipótese até que fosse.

## O motor é o RapidOCR, e a escolha está registrada

O `ROADMAP_TEXTO` põe a escolha do leitor de linha entre as decisões do dono do projeto, com três
opções e uma recomendação: **RapidOCR primeiro, medido** — ele já é extra declarado aqui e não
baixa nada, ao contrário do EasyOCR (~100 MB no primeiro uso), que é de onde o 91,2% veio. Este
comando implementa a recomendação; `--motor` roda outro para quem aceitar o download.

**E o número de lá não atravessa a troca de motor.** Se o ganho aqui for menor, ou negativo, é
isso que a tabela vai dizer — e o item manda registrar o negativo do mesmo jeito, com a leitura
por linha desligada ao lado.

## A referência é a camada editorada, e não a da S-183

As 123 faixas da S-183 ainda não foram transcritas (`conferido: false` em todas), e a medição as
recusa — que é o desenho certo. O que existe é a referência que a S-198 estabeleceu: a **camada de
texto editorada** dos livros que não são digitalização com OCR por cima. Ela é independente dos
dois lados que se comparam aqui, que é o que a torna utilizável.

## Duas réguas, e a segunda é o item S-189

| régua | o que ela responde |
|---|---|
| CER por caractere / por linha | ler a faixa inteira melhora o texto? |
| acerto por faixa de concordância | onde as duas leituras discordam, o erro se concentra? |

A segunda existe porque a confiança do modo bloco **não pode ser inventada**: o leitor de linha
devolve uma confiança para a faixa toda, e distribuí-la igual por todos os boxes seria dizer que
todos valem o mesmo. A regra da S-189 é `max` quando concordam e `min` quando divergem, e a
tabela é a prova de que ela separa o certo do errado.
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
from .texto_duas_linhas import DPI, RAIO_PT, faixas_da_camada, recorte_da_faixa
from .texto_grade import camada_de_ocr
from .texto_placar import cer

logger = logging.getLogger(__name__)

SAIDA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_linha.json"

MOTOR_PADRAO = "rapidocr"
"""A recomendação do `ROADMAP_TEXTO`: ele já é extra declarado e não baixa nada."""


def ler_faixa(cinza: np.ndarray, classificador: Any, leitor: Any) -> tuple[str, str, list[Any]]:
    """`(texto por caractere, texto por linha, os `Lido` de todas as linhas)`.

    O caminho é o do `GlyphRecognizer` como ele está hoje -- descarte de fragmento ligado (S-198),
    separador desligado (S-186) --, com o modo bloco entrando **depois** da segmentação. Medir o
    leitor de linha sobre outro pipeline mediria os dois.
    """
    from ..text import leitura_de_linha as ldl
    from ..text.binarizacao import binarize
    from ..text.boxes import caixas_de_caractere, escala_de_texto, unir_pingos
    from ..text.duas_linhas import descartar_fragmentos
    from ..text.linhas import ordem_em_faixa, quebrar_em_linhas, texto_da_linha

    binaria = binarize(cinza)
    escala = escala_de_texto(binaria)
    if escala <= 0:
        return "", "", []
    caixas = unir_pingos(caixas_de_caractere(binaria, escala=escala), escala=escala)
    grupos = descartar_fragmentos(quebrar_em_linhas(ordem_em_faixa(caixas)), escala=escala)

    por_caractere: list[str] = []
    por_linha: list[str] = []
    todos: list[Any] = []
    for grupo in grupos:
        lidos = classificador.classificar([c.recortar(cinza) for c in grupo])
        if not lidos:
            continue
        por_caractere.append(texto_da_linha(grupo, [char for char, _ in lidos]))
        casados = ldl.em_bloco(cinza, grupo, lidos, leitor)
        todos.extend(casados)
        por_linha.append(texto_da_linha(grupo, [item.caractere for item in casados]))
    return (
        " ".join(t for t in por_caractere if t),
        " ".join(t for t in por_linha if t),
        todos,
    )


def _acerto_por_concordancia(todos: list[Any], referencia: str) -> dict[str, Any]:
    """Onde as duas leituras concordam e onde divergem, o quanto cada grupo aparece na referência.

    **Não é acerto por caractere alinhado**, e a diferença é honesta: sem rótulo por box, o que dá
    para medir é se o caractere lido **existe** na linha de referência. É uma régua fraca, e ela
    está aqui por ser a que os dados permitem -- a régua forte precisa da anotação por box, que é
    trabalho humano da S-212.
    """
    presentes = set(referencia)
    concordam = [item for item in todos if item.concordam]
    divergem = [item for item in todos if not item.concordam]

    def taxa(itens: list[Any]) -> float:
        return float(sum(1 for i in itens if i.caractere in presentes) / len(itens)) if itens else 0.0

    return {
        "concordam": {"n": len(concordam), "na_referencia": taxa(concordam)},
        "divergem": {"n": len(divergem), "na_referencia": taxa(divergem)},
        "confianca_media": {
            "concordam": float(np.mean([i.confianca for i in concordam])) if concordam else 0.0,
            "divergem": float(np.mean([i.confianca for i in divergem])) if divergem else 0.0,
        },
    }


def _curva_da_concordancia(todos: list[Any], referencia: str) -> dict[str, Any]:
    """A curva de confiabilidade da confiança que sai da concordância (S-189).

    **A confiança de lá não sai de um softmax**, e é por isso que ela precisa de curva própria:
    ela é a maior das duas quando as leituras concordam e a menor quando divergem, e nada garante
    que essa combinação continue calibrada. A pergunta é a de sempre -- quando ele diz 0,9, ele
    acerta 0,9?

    O "acerto" aqui é a régua fraca que os dados permitem: o caractere lido **existe** na linha de
    referência. A forte precisa de rótulo por box, que é trabalho humano da S-212.
    """
    from ..text import calibracao as cal

    if not todos:
        return {"faixas": 0, "n": 0, "ece": 0.0, "ece_por_faixa": 0.0, "curva": []}
    presentes = set(referencia)
    linhas = cal.curva_de_confianca(
        [item.confianca for item in todos], [item.caractere in presentes for item in todos]
    )
    ponderado, por_faixa = cal.ece_da_curva(linhas)
    return {
        "faixas": cal.FAIXAS_PADRAO,
        "n": len(todos),
        "ece": ponderado,
        "ece_por_faixa": por_faixa,
        "curva": [f.como_dicionario() for f in linhas],
    }


def medir(
    pdfs: list[Path], *, por_livro: int, por_pagina: int, classificador: Any, leitor: Any
) -> dict[str, Any]:
    """O CER das duas leituras sobre as mesmas faixas da S-198."""
    import fitz

    soma_caractere = soma_linha = 0.0
    com_ocr: dict[str, str] = {}
    avisos: list[str] = []
    total = 0
    medido = 0
    todos: list[Any] = []
    referencia_inteira: list[str] = []

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
                    de_caractere, de_linha, lidos = ler_faixa(cinza, classificador, leitor)
                    for lido, acumulador in ((de_caractere, "c"), (de_linha, "l")):
                        erro = cer(lido, texto)
                        erro = 1.0 if erro == float("inf") else erro
                        if acumulador == "c":
                            soma_caractere += erro
                        else:
                            soma_linha += erro
                    todos.extend(lidos)
                    referencia_inteira.append(texto)
                    total += 1
                    deste_livro += 1
            if deste_livro:
                medido += 1
        logger.info("%s: %d faixa(s).", caminho.name, 0 if marca else deste_livro)

    if not total:
        raise ValueError("nenhuma faixa medida: os PDFs deste acervo têm camada editorada?")

    por_caractere = soma_caractere / total
    por_linha = soma_linha / total
    return {
        "quando": f"{date.today():%Y-%m-%d}",
        "dpi": DPI,
        "raio_pt": RAIO_PT,
        "faixas": total,
        "livros_medidos": medido,
        "livros_com_camada_de_ocr": dict(sorted(com_ocr.items())),
        "referencia": "camada de texto editorada (nao-OCR); a da S-183 ainda nao foi transcrita",
        "cer": {"por_caractere": por_caractere, "por_linha": por_linha},
        # Positivo é ganho. **O negativo é registrado do mesmo jeito**, e nesse caso a leitura
        # por linha fica desligada com esta tabela ao lado -- é o que o critério da S-188 pede.
        "ganho": por_caractere - por_linha,
        "concordancia": _acerto_por_concordancia(todos, "".join(referencia_inteira)),
        "calibracao": _curva_da_concordancia(todos, "".join(referencia_inteira)),
        "avisos": avisos,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mede o ganho de ler a linha em vez do caractere, neste acervo (S-188/S-189).",
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--por-livro", type=int, default=3)
    parser.add_argument("--por-pagina", type=int, default=6)
    parser.add_argument("--limite", type=int, help="So os N primeiros livros.")
    parser.add_argument("--motor", default=MOTOR_PADRAO, help="O leitor de linha. Padrao: rapidocr.")
    parser.add_argument("--modelo", type=Path, help="Pesos do classificador de caractere.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
    from ..ocr import build_recognizer
    from ..settings import OcrSettings
    from ..text.modelo import carregar_classificador

    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))
    if args.limite:
        pdfs = pdfs[: args.limite]
    if not pdfs:
        logger.warning("Nenhum PDF em %s. Nada a medir.", args.pdf_dir)
        return 0

    leitor = build_recognizer(OcrSettings(enabled=True, engine=args.motor))
    if leitor is None:
        raise ValueError(
            f"o motor de linha `{args.motor}` nao subiu. Sem leitor de linha nao ha o que medir: "
            "o braco `por_linha` seria uma copia do `por_caractere`."
        )
    classificador = carregar_classificador(pesos=args.modelo)
    logger.info("Leitor de linha: %s | classificador em %s.", leitor.name, classificador.device)

    relatorio = medir(
        pdfs,
        por_livro=args.por_livro,
        por_pagina=args.por_pagina,
        classificador=classificador,
        leitor=leitor,
    )
    relatorio["motor_de_linha"] = leitor.name
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
    print(f"  CER por caractere  {relatorio['cer']['por_caractere']:.4f}")
    print(f"  CER por linha      {relatorio['cer']['por_linha']:.4f}   ({relatorio['ganho']:+.4f})")
    concordancia = relatorio["concordancia"]
    print()
    print("  as duas leituras   n        na referencia   confianca media")
    for grupo in ("concordam", "divergem"):
        print(
            f"  {grupo:16s} {concordancia[grupo]['n']:6d}   "
            f"{concordancia[grupo]['na_referencia']:13.4f}   "
            f"{concordancia['confianca_media'][grupo]:15.4f}"
        )
    curva = relatorio["calibracao"]
    if curva["curva"]:
        print(
            f"  curva da confianca por concordancia: ECE {curva['ece']:.4f} ponderado, "
            f"{curva['ece_por_faixa']:.4f} por faixa"
        )
    caminho_curva = Path(args.saida).with_name(f"texto_calibracao_{date.today():%Y%m%d}.json")
    atomic_write_text(
        caminho_curva, json.dumps(curva, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  curva-> {caminho_curva}")
    print(f"\nrelatorio-> {args.saida}")
    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
