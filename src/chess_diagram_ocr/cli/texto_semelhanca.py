"""`cvoff-texto-semelhanca` -- a precisão de "aplicar a todos os semelhantes", medida aqui (S-213).

    cvoff-texto-semelhanca --amostras 3000

**O número que este comando produz decide a interface do item.** A S-213 diz que, se a precisão
ficar abaixo de ~99% num rigor, aquele rigor entrega a **pré-visualização** e não o lote -- e a
tabela vai para `docs/metrics/texto_semelhanca.json` para que a decisão seja conferível sem
remedir.

## A régua, e as duas colunas que ela tem

Sobre todos os pares de uma amostra rotulada de `training_data/`:

    precisão    dos pares que o critério juntou, quantos são de fato o mesmo caractere
    cobertura   dos pares que **são** o mesmo caractere, quantos o critério alcançou

A verdade é a pasta de onde o recorte veio. A **leitura** da segunda condição é o que o
classificador respondeu, e não a pasta: usar a pasta ali mediria o critério contra ele mesmo -- a
condição passaria a dizer "os dois são da mesma classe", que é a resposta que se quer prever.

## A amostra é estratificada, e não as primeiras N linhas

`training_data/` está ordenada por classe: as primeiras N linhas seriam `digit_0` inteiro. A
amostra sorteia **por classe**, com semente fixa, e a semente vai no JSON -- uma tabela que ninguém
consegue reproduzir não é medição.

## Por que não a base inteira

O par a par completo é exato e quadrático. Em 178 mil imagens distintas seriam 1,6·10¹⁰
comparações -- é a conta que a S-202 registra, e é por isso que ela compara **dentro da classe**.
Aqui a busca é entre classes por definição do item, então o que se controla é o `n`.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..atomic_io import atomic_write_text
from ..config import PROJECT_ROOT
from ..logging_setup import configure_logging
from ..text import semelhanca as _sem
from . import EXIT_BAD_INPUT, EXIT_OK, add_verbose, cli_errors

logger = logging.getLogger(__name__)

BASE_PADRAO = PROJECT_ROOT / "training_data"
DESTINO_PADRAO = PROJECT_ROOT / "docs" / "metrics" / "texto_semelhanca.json"

AMOSTRAS = 3000
"""Quantos recortes entram na amostra. O par a par é quadrático -- 3.000 são 4,5 milhões de pares,
que rodam em segundos; 30.000 seriam 450 milhões, que não cabem no bolso deste comando."""

SEMENTE = 0


def amostra_estratificada(
    y: np.ndarray, quantas: int, *, semente: int = SEMENTE
) -> np.ndarray:
    """Índices sorteados **por classe**, na proporção de cada uma. Ver o cabeçalho.

    Uma classe pequena demais para render uma linha ainda entra com uma: sem isso a amostra teria
    só as classes grandes, e o critério nunca veria o homóglifo raro -- que é justamente onde ele
    erra.
    """
    aleatorio = np.random.default_rng(semente)
    classes = np.unique(y)
    if classes.size == 0 or quantas <= 0:
        return np.empty(0, np.int64)

    escolhidos: list[np.ndarray] = []
    for classe in classes:
        linhas = np.flatnonzero(y == classe)
        cota = max(1, int(round(quantas * linhas.size / y.size)))
        cota = min(cota, linhas.size)
        escolhidos.append(aleatorio.choice(linhas, size=cota, replace=False))
    juntos = np.concatenate(escolhidos)
    if juntos.size > quantas:
        juntos = aleatorio.choice(juntos, size=quantas, replace=False)
    return np.sort(juntos)


def leituras_do_modelo(X: np.ndarray, *, lado: int = 32) -> np.ndarray | None:
    """O que o classificador responde em cada recorte, ou `None` quando ele não carrega.

    `None` é caminho normal, e não erro: os pesos não vêm no repositório (S-182). Sem eles a
    tabela sai só com a linha "imagem", que é o critério principal do item -- a segunda condição
    é uma trava sobre ele, e medir uma trava sem o modelo que a alimenta seria inventar número.
    """
    from ..text.modelo import ModeloInvalido, carregar_classificador

    try:
        classificador = carregar_classificador()
    except (ModeloInvalido, FileNotFoundError) as exc:
        logger.warning("Sem classificador de glifo (%s): a 2ª condição fica fora da tabela.", exc)
        return None

    recortes = [X[i].reshape(lado, lado) for i in range(X.shape[0])]
    lidos = classificador.classificar(recortes)
    return np.array([char for char, _ in lidos], dtype=object)


def medir(
    D: np.ndarray,
    y: np.ndarray,
    leituras: np.ndarray | None,
) -> dict[str, _sem.Placar]:
    """Um placar por rigor, e mais um por rigor quando a 2ª condição pode ser medida.

    A tabela sai com as duas famílias lado a lado porque é a comparação que decide o item: a
    segunda condição existe para segurar a precisão quando se afrouxa o limiar, e isso só se vê
    com as duas linhas juntas no mesmo limiar.
    """
    placares: dict[str, _sem.Placar] = {}
    for rigor in _sem.RIGORES:
        limiar = _sem.LIMIAR_POR_RIGOR[rigor]
        placares[f"imagem/{rigor}"] = _sem.avaliar(D, y, limiar=limiar)
        if leituras is not None:
            placares[f"imagem+leitura/{rigor}"] = _sem.avaliar(D, y, limiar=limiar, leituras=leituras)
    return placares


CURVA = (0.03, 0.06, 0.10, 0.14, 0.18, 0.22, 0.26, 0.30, 0.35, 0.40)
"""Os limiares da varredura de `--curva`. Vão de onde a `dedupe` mede a quase-duplicata (0,03) até
onde a precisão da imagem sozinha desaba (0,40, 45%), passando pelos três rigores."""


def curva(
    D: np.ndarray,
    y: np.ndarray,
    leituras: np.ndarray | None,
    limiares: Sequence[float] = CURVA,
) -> dict[str, _sem.Placar]:
    """A tabela inteira, e não só os três rigores.

    **É ela que torna os rigores conferíveis.** Três números soltos num dicionário não dizem por
    que são esses três; a curva mostra onde a precisão cai e o quanto a segunda condição a segura,
    e é a partir dela que `LIMIAR_POR_RIGOR` foi escrito.
    """
    saida: dict[str, _sem.Placar] = {}
    for limiar in limiares:
        saida[f"imagem@{limiar:.2f}"] = _sem.avaliar(D, y, limiar=limiar)
        if leituras is not None:
            saida[f"imagem+leitura@{limiar:.2f}"] = _sem.avaliar(D, y, limiar=limiar, leituras=leituras)
    return saida


@cli_errors
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cvoff-texto-semelhanca",
        description="Mede a precisão e a cobertura de 'aplicar a todos os semelhantes' (S-213).",
    )
    parser.add_argument("--base", type=Path, default=BASE_PADRAO, help="Pasta de classes rotuladas.")
    parser.add_argument("--amostras", type=int, default=AMOSTRAS, help=f"Recortes na amostra. Padrão: {AMOSTRAS}.")
    parser.add_argument("--semente", type=int, default=SEMENTE, help=f"Semente do sorteio. Padrão: {SEMENTE}.")
    parser.add_argument("--json", type=Path, default=DESTINO_PADRAO, help="Onde gravar a tabela.")
    parser.add_argument("--sem-modelo", action="store_true", help="Não mede a 2ª condição, mesmo com os pesos no disco.")
    parser.add_argument(
        "--curva",
        action="store_true",
        help="Varre a tabela inteira de limiares, e não só os três rigores. É o que os justifica.",
    )
    add_verbose(parser)
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    if not args.base.is_dir():
        logger.error("Base de recortes não encontrada: %s", args.base)
        return EXIT_BAD_INPUT

    from ..text.dataset import BaseVazia, varrer

    try:
        varredura = varrer(args.base)
    except BaseVazia as exc:
        logger.error("%s", exc)
        return EXIT_BAD_INPUT

    linhas = amostra_estratificada(varredura.y, args.amostras, semente=args.semente)
    if linhas.size < 2:
        logger.error("A amostra ficou com %d recortes -- não há par para medir.", linhas.size)
        return EXIT_BAD_INPUT

    X = varredura.X[linhas]
    y = varredura.y[linhas]
    leituras = None if args.sem_modelo else leituras_do_modelo(X)
    D = _sem.descritores_de(X)
    placares = medir(D, y, leituras)
    tabela_da_curva = curva(D, y, leituras) if args.curva else {}

    print(f"Amostra: {linhas.size} recortes de {np.unique(y).size} classes (semente {args.semente}).")
    print("")
    for linha in _sem.tabela(placares):
        print(linha)
    print("")
    print(f"Piso de precisão para entregar lote: {_sem.PISO_DE_PRECISAO:.0%}.")
    if tabela_da_curva:
        print("")
        for linha in _sem.tabela(tabela_da_curva):
            print(linha)

    dados: dict[str, Any] = {
        "item": "S-213",
        "base": str(args.base.name),
        "amostras": int(linhas.size),
        "classes": int(np.unique(y).size),
        "semente": args.semente,
        "piso_de_precisao": _sem.PISO_DE_PRECISAO,
        "limiar_por_rigor": dict(_sem.LIMIAR_POR_RIGOR),
        "segunda_condicao_medida": leituras is not None,
        "placares": {nome: placar.para_json() for nome, placar in placares.items()},
        "curva": {nome: placar.para_json() for nome, placar in tabela_da_curva.items()},
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.json, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")
    print(f"Tabela gravada em {args.json}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
