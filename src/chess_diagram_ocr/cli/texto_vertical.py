"""`cvoff-texto-vertical` — a tabela dos quatro ângulos, medida neste acervo (S-197).

    cvoff-texto-vertical --por-livro 3
    cvoff-texto-vertical --baseline docs/metrics/texto_vertical.json

**O item já estava implementado e sem número.** A geometria propõe a pilha e o classificador
decide o ângulo, e até 2026-08-23 não havia classificador nesta máquina para decidir coisa
alguma: a tabela que faltava era a única parte da S-197 que dependia dos pesos.

## O que se mede, e por que a linha girada é simulada

O acervo é de texto de pé. Anotar rótulos girados à mão daria dezenas de amostras, e uma régua
que separa 94,2% de 8,4% precisa de milhares. Então a linha é **girada por transposição**
(`vertical.girar`, o avesso de `endireitar`): nenhum pixel é reamostrado, a ida e a volta fecham
byte a byte, e a resposta certa vem de graça ao lado da leitura.

## Duas réguas, e a segunda é a que o programa usa

| régua | o que ela responde |
|---|---|
| argmax da média | lendo a pilha nos quatro ângulos, o mais confiante é o ângulo impresso? |
| decisão de produção | `decidir_angulo` -- só 0, 90 e 270, e o vencedor supera o de pé por `MARGEM` |

A primeira é a do projeto de origem (99,7% em 1.312 linhas simuladas) e mede o **classificador**.
A segunda mede o que a S-197 de fato faz, com as duas decisões que ela tomou de propósito: 180°
não é candidato, e na dúvida não se mexe. Publicar só a primeira diria que o módulo acerta o que
ele nem tenta.

## A linha é de texto porque o PDF diz, e não porque o modelo gostou dela

Escolher linhas pela confiança do classificador mediria o classificador contra ele mesmo. Aqui a
peneira é a **camada de texto** do PDF: uma linha segmentada só entra se o seu centro cair dentro
de uma linha que a camada declara. É a mesma referência independente que o `cvoff-texto-ordem`
usa para ordem, e ela também exclui de graça as fileiras de peças de um diagrama.

**E aqui a camada de OCR serve, ao contrário do que acontece na S-198.** Esta medição pergunta
*onde há texto*, e não *o que está escrito*: uma camada do Paper Capture pode errar todas as
letras e continuar acertando que ali existe uma linha. Quem não pode usá-la é quem mede CER --
ver o cabeçalho do `cvoff-texto-duas-linhas`.

Livro de scan puro não tem camada nenhuma e fica de fora, listado no relatório como o que é.
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
from ..text import vertical
from . import EXIT_FAILURE, add_verbose, cli_errors, confere_baseline

logger = logging.getLogger(__name__)

SAIDA_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_vertical.json"

DPI = 220.0
"""O mesmo da varredura de produção e o mesmo do `cvoff-texto-ordem`."""

ANGULOS_IMPRESSOS = (0, 90, 180, 270)
"""Os quatro do papel. `vertical.ANGULOS` são os dois que a produção tenta -- ver as duas réguas.

180° está aqui **porque não é candidato lá**: a linha dele diz o preço daquela decisão em vez de
escondê-lo, e livro impresso não traz linha de cabeça para baixo."""

MARGEM_DA_PRODUCAO = vertical.MARGEM
"""A margem que `decidir_angulo` exige, lida de onde ela mora. Ver `folga_contra_o_de_pe`."""

MIN_CAIXAS = 5
"""O mesmo `vertical.MIN_ITENS`: abaixo disso a média da confiança é ruído."""

PIORA_TOLERADA = 0.02
"""Quanto o acerto pode cair contra o `--baseline` antes de o comando falhar."""


def _linhas_da_camada(page: Any, escala: float) -> list[tuple[float, float, float, float]]:
    """Os retângulos das linhas que a camada declara, **em pixels** da página renderizada."""
    caixas = []
    for bloco in page.get_text("dict").get("blocks", []):
        for linha in bloco.get("lines", []):
            x0, y0, x1, y1 = linha["bbox"]
            caixas.append((x0 * escala, y0 * escala, x1 * escala, y1 * escala))
    return caixas


def _dentro(centro: tuple[float, float], retangulos: Sequence[tuple[float, float, float, float]]) -> bool:
    x, y = centro
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in retangulos)


def linhas_de_texto(
    cinza: np.ndarray, retangulos: Sequence[tuple[float, float, float, float]]
) -> list[list[Any]]:
    """As linhas segmentadas da página que a camada de texto confirma serem texto."""
    from ..text.binarizacao import binarize
    from ..text.boxes import caixas_de_caractere, escala_de_texto, unir_pingos
    from ..text.linhas import ordem_em_faixa, quebrar_em_linhas

    binaria = binarize(cinza)
    escala = escala_de_texto(binaria)
    if escala <= 0:
        return []
    caixas = unir_pingos(caixas_de_caractere(binaria, escala=escala), escala=escala)

    escolhidas = []
    for grupo in quebrar_em_linhas(ordem_em_faixa(caixas)):
        if len(grupo) < MIN_CAIXAS:
            continue
        meio_x = (min(c.x1 for c in grupo) + max(c.x2 for c in grupo)) / 2.0
        meio_y = (min(c.y1 for c in grupo) + max(c.y2 for c in grupo)) / 2.0
        if _dentro((meio_x, meio_y), retangulos):
            escolhidas.append(list(grupo))
    return escolhidas


def medir_linha(cinza: np.ndarray, linha: Sequence[Any], arbitro: Any) -> dict[str, Any]:
    """Uma linha lida nos quatro ângulos, depois de impressa em cada um deles.

    Devolve a matriz 4x4 de confiança média -- fileira é o ângulo impresso, coluna o ângulo em
    que se leu --, o argmax de cada fileira e o que `decidir_angulo` responderia.
    """
    from ..text.vertical import confianca_media, decidir_angulo, girar

    matriz: list[list[float]] = []
    argmax: list[int] = []
    producao: list[int] = []
    folgas: list[float] = []
    for impresso in ANGULOS_IMPRESSOS:
        virada, caixas = girar(cinza, linha, impresso)
        fileira = [confianca_media(virada, caixas, lido, arbitro) for lido in ANGULOS_IMPRESSOS]
        matriz.append(fileira)
        argmax.append(ANGULOS_IMPRESSOS[int(np.argmax(fileira))])
        producao.append(decidir_angulo(virada, caixas, arbitro))
        # **A folga é o que decide em produção, e não o argmax.** `decidir_angulo` só aceita um
        # ângulo que supere o de pé por `MARGEM`, então é esta distância -- e não a ordem dos
        # quatro números -- que diz se o módulo mexe ou fica quieto.
        de_pe = fileira[0]
        melhor_girado = max(fileira[1], fileira[3])
        folgas.append(float(melhor_girado - de_pe))
    return {
        "caixas": len(linha),
        "matriz": matriz,
        "argmax": argmax,
        "producao": producao,
        "folgas": folgas,
    }


def arbitro_de(classificador: Any) -> Any:
    """O `vertical.Arbitro` que empresta o classificador de verdade à decisão de ângulo."""

    def ler(recortes: list[np.ndarray]) -> list[float]:
        return [confianca for _, confianca in classificador.classificar(recortes)]

    return ler


def _pagina_em_cinza(page: Any) -> np.ndarray:
    import cv2
    import fitz

    pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72.0, DPI / 72.0), alpha=False)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)


def medir(pdfs: list[Path], *, por_livro: int, por_pagina: int, classificador: Any) -> dict[str, Any]:
    """A tabela agregada dos quatro ângulos, e uma linha por livro medido."""
    import fitz

    arbitro = arbitro_de(classificador)
    soma = np.zeros((len(ANGULOS_IMPRESSOS), len(ANGULOS_IMPRESSOS)), dtype=np.float64)
    acertos_argmax = dict.fromkeys(ANGULOS_IMPRESSOS, 0)
    acertos_producao = dict.fromkeys(ANGULOS_IMPRESSOS, 0)
    folgas: dict[int, list[float]] = {a: [] for a in ANGULOS_IMPRESSOS}
    medido: dict[str, dict[str, Any]] = {}
    sem_camada: list[str] = []
    avisos: list[str] = []
    total = 0

    for caminho in pdfs:
        try:
            doc = fitz.open(caminho)
        except Exception as exc:  # noqa: BLE001 - PDF de terceiro
            avisos.append(f"{caminho.name}: não abriu ({exc})")
            continue
        with doc:
            deste_livro = 0
            paginas = 0
            for indice in range(int(doc.page_count * 0.15), doc.page_count):
                if paginas >= por_livro:
                    break
                try:
                    page = doc[indice]
                    retangulos = _linhas_da_camada(page, DPI / 72.0)
                    if not retangulos:
                        continue
                    cinza = _pagina_em_cinza(page)
                    linhas = linhas_de_texto(cinza, retangulos)
                except Exception as exc:  # noqa: BLE001 - idem
                    avisos.append(f"{caminho.name} p.{indice + 1}: {exc}")
                    continue
                if not linhas:
                    continue
                paginas += 1
                # Espaçadas, e não as primeiras: `linhas[:n]` pegaria o topo da página, que é
                # onde moram cabeçalho e número -- linhas curtas e de fonte diferente do corpo.
                passo = max(1, len(linhas) // por_pagina)
                for linha in linhas[::passo][:por_pagina]:
                    medida = medir_linha(cinza, linha, arbitro)
                    soma += np.asarray(medida["matriz"], dtype=np.float64)
                    for i, impresso in enumerate(ANGULOS_IMPRESSOS):
                        acertos_argmax[impresso] += int(medida["argmax"][i] == impresso)
                        esperado = impresso if impresso in (0, 90, 270) else 0
                        acertos_producao[impresso] += int(medida["producao"][i] == esperado)
                        folgas[impresso].append(medida["folgas"][i])
                    total += 1
                    deste_livro += 1
            if deste_livro:
                medido[caminho.name] = {"linhas": deste_livro, "paginas": paginas}
            else:
                sem_camada.append(caminho.name)
        logger.info("%s: %d linha(s).", caminho.name, deste_livro)

    if not total:
        raise ValueError("nenhuma linha de texto medida: os PDFs deste acervo têm camada de texto?")

    return {
        "dpi": DPI,
        "linhas": total,
        "livros_medidos": len(medido),
        "livros_sem_camada_de_texto": sem_camada,
        # **A régua do projeto de origem**: lendo a pilha nos quatro ângulos, o argmax da média é
        # o ângulo impresso? Ela mede o classificador, e não o que a S-197 faz com ele.
        "argmax_da_media": {
            str(a): {"acertos": acertos_argmax[a], "de": total, "taxa": acertos_argmax[a] / total}
            for a in ANGULOS_IMPRESSOS
        },
        # **A régua da produção**: `decidir_angulo`, com `MARGEM` e sem 180°. Para a linha
        # impressa a 180 o acerto **é** responder 0 -- o módulo não a trata, e a fileira existe
        # aqui para dizer o preço dessa decisão em vez de escondê-lo.
        "decisao_de_producao": {
            str(a): {"acertos": acertos_producao[a], "de": total, "taxa": acertos_producao[a] / total}
            for a in ANGULOS_IMPRESSOS
        },
        # **A folga contra `MARGEM`, que é o que decide se o módulo mexe.** A fileira de 90 e a
        # de 270 são as que importam: nelas a folga tem de ser positiva e maior que a margem
        # para a pilha ser marcada. A de 0 é o controle -- ali uma folga alta seria o módulo
        # querendo girar texto de pé.
        "folga_contra_o_de_pe": {
            str(a): {
                "mediana": float(np.median(folgas[a])),
                "media": float(np.mean(folgas[a])),
                "acima_da_margem": int(sum(1 for f in folgas[a] if f > MARGEM_DA_PRODUCAO)),
                "de": len(folgas[a]),
            }
            for a in ANGULOS_IMPRESSOS
        },
        "margem": MARGEM_DA_PRODUCAO,
        "confianca_media": {
            str(impresso): {str(lido): float(soma[i, j] / total) for j, lido in enumerate(ANGULOS_IMPRESSOS)}
            for i, impresso in enumerate(ANGULOS_IMPRESSOS)
        },
        "por_livro": dict(sorted(medido.items())),
        "avisos": avisos,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mede a tabela dos quatro angulos do texto girado, neste acervo (S-197).",
    )
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Pasta do acervo de livros.")
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="Onde gravar o relatório desta medição.")
    parser.add_argument("--por-livro", type=int, default=3, help="Paginas medidas por livro (padrao 3).")
    parser.add_argument("--por-pagina", type=int, default=8, help="Linhas medidas por pagina (padrao 8).")
    parser.add_argument("--limite", "--limit", type=int, help="So os N primeiros livros.")
    parser.add_argument("--modelo", type=Path, help="Pesos. Padrao: ao lado do char_meta.json.")
    parser.add_argument("--baseline", type=Path, help="Relatorio anterior: falha se o acerto cair.")
    add_verbose(parser)
    return parser.parse_args(argv)


@cli_errors
def main(argv: list[str] | None = None) -> int:
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
    relatorio["modelo"] = {
        "classes": classificador.meta.num_classes,
        "temperatura": classificador.meta.temperatura,
        "modelo_sha256": classificador.meta.modelo_sha256,
    }

    atomic_write_json(Path(args.saida), relatorio)

    print(f"\n{relatorio['linhas']} linhas de {relatorio['livros_medidos']} livro(s)\n")
    print("  impresso    argmax da media    decisao de producao")
    for angulo in ANGULOS_IMPRESSOS:
        argmax = relatorio["argmax_da_media"][str(angulo)]["taxa"]
        producao = relatorio["decisao_de_producao"][str(angulo)]["taxa"]
        print(f"  {angulo:8d}    {argmax:15.4f}    {producao:19.4f}")
    print(f"\nRelatorio em {Path(args.saida)}")

    if args.baseline:
        anterior = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        for angulo in ANGULOS_IMPRESSOS:
            antes = anterior["argmax_da_media"][str(angulo)]["taxa"]
            agora = relatorio["argmax_da_media"][str(angulo)]["taxa"]
            if agora < antes - PIORA_TOLERADA:
                logger.error("Regressao a %d graus: %.4f contra %.4f do baseline.", angulo, agora, antes)
                return EXIT_FAILURE

    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
