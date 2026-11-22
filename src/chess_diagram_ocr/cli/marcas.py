"""`cvoff-marcas` — o teste congelado, o treino e a medição do modelo de marcas.

    cvoff-marcas congelar                      # as anotações novas entram no teste congelado
    cvoff-marcas treinar --epocas 5            # treina do zero, só com marca sintética
    cvoff-marcas medir --alarmes 2000          # modelo x detector clássico no teste, e alarmes fora dele

**`congelar`** lê `data/marcas/anotacoes.json` e acrescenta ao teste os diagramas que ainda não estão
nele (`teste_de_marcas.acrescentar`): o caso que já estava não muda.

**`treinar`** tira do treino as amostras do teste congelado e grava o checkpoint em `--saida`. Não toca
no modelo de peças nem no `labels.csv`.

**`medir`** pontua o modelo e o detector clássico na mesma régua. Com `--alarmes N`, lê também N
amostras de validação e teste que ninguém anotou e conta em quantas cada um deu marca: ali não há
gabarito, e a pergunta é quantos alarmes uma pessoa teria de recusar. `--mosaico` grava as casas
apontadas para essa conferência a olho.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

from .. import marcas_de_casa as mc
from .. import teste_de_marcas as tm
from ..atomic_io import atomic_write_json, read_image, write_image
from ..config import DATA_DIR, PROJECT_ROOT
from ..logging_setup import configure_logging, default_log_file
from ..splits import load_splits
from . import (
    EXIT_BAD_INPUT,
    EXIT_NO_CHECKPOINT,
    EXIT_OK,
    add_dataset_arguments,
    add_device_argument,
    add_json_argument,
    add_verbose,
    cli_errors,
)

if TYPE_CHECKING:
    from ..modelo_de_marcas import ModeloDeMarcas

logger = logging.getLogger(__name__)

TESTE_PADRAO = DATA_DIR / "marcas" / "teste_congelado.json"
MODELO_PADRAO = PROJECT_ROOT / "models" / "marcas.pt"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teste congelado, treino e medição do modelo de marcas de casa.")
    parser.add_argument("acao", choices=["congelar", "treinar", "medir"], help="O que fazer.")
    add_dataset_arguments(parser)
    parser.add_argument("--anotacoes", type=Path, default=mc.ARQUIVO_DAS_MARCAS, help="As anotações de marcas.")
    parser.add_argument("--teste", type=Path, default=TESTE_PADRAO, help="O arquivo do teste congelado.")
    parser.add_argument("--modelo", type=Path, default=MODELO_PADRAO, help="O checkpoint do modelo de marcas.")
    parser.add_argument("--saida", type=Path, default=None, help="Onde o treino grava. Padrão: o --modelo.")
    parser.add_argument("--epocas", type=int, default=5, help="Épocas de treino.")
    parser.add_argument("--lote", type=int, default=256, help="Casas por lote.")
    parser.add_argument("--lr", type=float, default=1e-3, help="Taxa de aprendizado do Adam.")
    parser.add_argument("--semente", type=int, default=42, help="Semente do treino e do sorteio das marcas.")
    parser.add_argument("--workers", type=int, default=4, help="Processos de carregamento. 0 carrega no principal.")
    parser.add_argument(
        "--tabuleiros",
        type=int,
        default=None,
        help="Treina só com estes tabuleiros sorteados: treino curto de conferência.",
    )
    parser.add_argument("--p-marca", type=float, default=0.5, help="Fração das casas vazias que recebe marca de casa.")
    parser.add_argument(
        "--p-traco", type=float, default=0.3, help="Fração das casas vazias que recebe traço de distração."
    )
    parser.add_argument(
        "--p-traco-na-marca", type=float, default=0.0, help="Fração das marcas desenhadas atravessadas por um traço. Desligado: ver SorteioDeMarca."
    )
    add_device_argument(parser)
    parser.add_argument(
        "--limiar", type=float, default=None, help="Probabilidade mínima da marca. Padrão: a do checkpoint."
    )
    parser.add_argument("--alarmes", type=int, default=0, help="Quantas amostras sem anotação ler para contar alarmes.")
    parser.add_argument(
        "--mosaico", type=Path, default=None, help="Pasta onde gravar as casas apontadas fora do teste."
    )
    add_json_argument(parser, help="Grava a medição em JSON.")
    add_verbose(parser)
    return parser.parse_args(argv)


def _congelar(args: argparse.Namespace) -> int:
    casos, fora = tm.casos_das_anotacoes(args.anotacoes, args.csv, args.samples)
    for motivo in fora:
        print(f"fora: {motivo}")
    entraram = tm.acrescentar(args.teste, casos)
    total = len(tm.ler_teste(args.teste))
    marcas = sum(len(caso.casas) for caso in entraram)
    print(f"Entraram {len(entraram)} diagrama(s), com {marcas} marca(s). O teste tem {total} diagrama(s): {args.teste}")
    return EXIT_OK


def _treinar(args: argparse.Namespace) -> int:
    from ..modelo_de_marcas import treinar

    casos = tm.ler_teste(args.teste)
    if not casos:
        print(
            f"O teste congelado está vazio ({args.teste}). Rode `cvoff-marcas congelar` antes: sem ele o treino veria o teste."
        )
        return EXIT_BAD_INPUT
    anotadas = {str(e.get("amostra")) for e in _entradas(args.anotacoes).values() if e.get("amostra")}
    excluidas = {caso.amostra for caso in casos} | anotadas
    saida = args.saida or args.modelo
    resultado = treinar(
        csv_path=args.csv,
        samples_dir=args.samples,
        splits=load_splits(args.splits),
        saida=saida,
        excluidas=excluidas,
        epocas=args.epocas,
        lote=args.lote,
        lr=args.lr,
        semente=args.semente,
        workers=args.workers,
        device=args.device,
        p_marca=args.p_marca,
        p_traco=args.p_traco,
        p_traco_na_marca=args.p_traco_na_marca,
        tabuleiros_treino=args.tabuleiros,
    )
    print(
        f"Melhor época {resultado.melhor_epoca}, F1 das marcas na validação sintética {resultado.melhor_f1:.4f}; "
        f"{resultado.tabuleiros_treino} tabuleiros de treino, {resultado.excluidos} do teste tirados. Gravado em {saida}"
    )
    return EXIT_OK


def _entradas(anotacoes: Path) -> dict[str, dict[str, object]]:
    if not Path(anotacoes).exists():
        return {}
    return dict(json.loads(Path(anotacoes).read_text(encoding="utf-8")).get("imagens", {}))


def _ler_rgb(caminho: Path) -> np.ndarray | None:
    imagem = read_image(caminho)
    return None if imagem is None else cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)


def _gravar_mosaico(pasta: Path, nome: str, tabuleiro: np.ndarray, casas: dict[str, str]) -> None:
    lado = tabuleiro.shape[0] // 8
    for casa, tipo in casas.items():
        indice = mc.indice_da_casa(casa)
        fila, coluna = divmod(indice, 8)
        recorte = tabuleiro[fila * lado : (fila + 1) * lado, coluna * lado : (coluna + 1) * lado]
        write_image(pasta / f"{tipo}__{Path(nome).stem}__{casa}.png", cv2.cvtColor(recorte, cv2.COLOR_RGB2BGR))


def _medir(args: argparse.Namespace) -> int:
    from ..detector_de_marcas import sugerir_marcas
    from ..modelo_de_marcas import carregar

    if not Path(args.modelo).exists():
        print(f"Modelo de marcas não encontrado: {args.modelo}")
        return EXIT_NO_CHECKPOINT
    casos = tm.ler_teste(args.teste)
    if not casos:
        print(f"O teste congelado está vazio ({args.teste}).")
        return EXIT_BAD_INPUT
    mudadas = tm.conferir_amostras(casos, args.samples)
    if mudadas:
        for problema in mudadas:
            print(f"régua quebrada: {problema}")
        return EXIT_BAD_INPUT

    modelo = carregar(args.modelo, device=args.device or "cpu")
    limiar = args.limiar if args.limiar is not None else modelo.limiar
    lidos_modelo: dict[str, dict[str, str]] = {}
    lidos_detector: dict[str, dict[str, str]] = {}
    for caso in casos:
        tabuleiro = _ler_rgb(Path(args.samples) / caso.amostra)
        if tabuleiro is None:
            continue
        lidos_modelo[caso.amostra] = dict(modelo.ler(tabuleiro, limiar).casas)
        lidos_detector[caso.amostra] = dict(sugerir_marcas(tabuleiro).casas)

    relatorio: dict[str, object] = {
        "modelo": str(args.modelo),
        "limiar": limiar,
        "teste": str(args.teste),
        "diagramas": len(casos),
        "placar_modelo": tm.pontuar(casos, lidos_modelo).to_dict(),
        "placar_detector": tm.pontuar(casos, lidos_detector).to_dict(),
    }
    print(f"Teste congelado: {len(casos)} diagramas, limiar {limiar}")
    for rotulo, lidos in (("modelo", lidos_modelo), ("detector", lidos_detector)):
        print(f"{rotulo}:")
        for linha in tm.pontuar(casos, lidos).linhas():
            print(f"  {linha}")

    if args.alarmes > 0:
        relatorio["alarmes"] = _alarmes(args, modelo, limiar, {caso.amostra for caso in casos}, sugerir_marcas)

    if args.json is not None:
        atomic_write_json(args.json, relatorio)
        print(f"Medição em {args.json}")
    return EXIT_OK


def _alarmes(
    args: argparse.Namespace,
    modelo: ModeloDeMarcas,
    limiar: float,
    do_teste: set[str],
    sugerir: Callable[[np.ndarray], mc.MarcasDoDiagrama],
) -> dict[str, object]:
    """Onde cada leitor dá marca em amostras de validação e teste que ninguém anotou."""
    anotadas = {str(e.get("amostra")) for e in _entradas(args.anotacoes).values() if e.get("amostra")}
    splits = load_splits(args.splits)
    candidatas = sorted(
        nome
        for nome, particao in splits.items()
        if str(particao) in ("val", "test") and nome not in do_teste and nome not in anotadas
    )
    amostras = random.Random(args.semente).sample(candidatas, min(args.alarmes, len(candidatas)))
    contagem = {"modelo": 0, "detector": 0, "os_dois": 0}
    por_tipo: dict[str, dict[str, int]] = {"modelo": {}, "detector": {}}
    apontadas: list[dict[str, object]] = []
    lidas = 0
    for nome in amostras:
        tabuleiro = _ler_rgb(Path(args.samples) / nome)
        if tabuleiro is None:
            continue
        lidas += 1
        do_modelo = dict(modelo.ler(tabuleiro, limiar).casas)
        do_detector = dict(sugerir(tabuleiro).casas)
        for rotulo, casas in (("modelo", do_modelo), ("detector", do_detector)):
            if casas:
                contagem[rotulo] += 1
                for tipo in casas.values():
                    por_tipo[rotulo][tipo] = por_tipo[rotulo].get(tipo, 0) + 1
        if do_modelo and do_detector:
            contagem["os_dois"] += 1
        if do_modelo or do_detector:
            apontadas.append({"amostra": nome, "modelo": do_modelo, "detector": do_detector})
            if args.mosaico is not None:
                _gravar_mosaico(Path(args.mosaico) / "modelo", nome, tabuleiro, do_modelo)
                _gravar_mosaico(Path(args.mosaico) / "detector", nome, tabuleiro, do_detector)
    print(
        f"Alarmes em {lidas} amostras sem anotação: modelo {contagem['modelo']} diagrama(s) {por_tipo['modelo']}, "
        f"detector {contagem['detector']} {por_tipo['detector']}, os dois {contagem['os_dois']}"
    )
    return {"lidas": lidas, "diagramas": contagem, "por_tipo": por_tipo, "apontadas": apontadas}


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())
    if args.acao == "congelar":
        return _congelar(args)
    if args.acao == "treinar":
        return _treinar(args)
    return _medir(args)


if __name__ == "__main__":
    raise SystemExit(main())
