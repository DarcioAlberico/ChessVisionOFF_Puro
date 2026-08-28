from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..audit import audit_dataset
from ..augment import AugmentConfig
from ..config import (
    DEFAULT_BOARD_CACHE_SIZE,
)
from ..logging_setup import configure_logging, default_log_file
from ..model import ArchConfig
from ..training import DEFAULT_CLASS_WEIGHTS, OptimPlan, train_model
from . import EXIT_BAD_INPUT, add_dataset_arguments, add_model_argument, add_splits_argument, add_verbose, cli_errors

logger = logging.getLogger(__name__)



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Treina o classificador de pecas do Chess Diagram OCR.")
    add_dataset_arguments(parser, splits=False)
    add_model_argument(parser, help="Caminho do checkpoint .pt.")
    parser.add_argument("--epochs", type=int, default=8, help="Épocas de treino. A parada antecipada pode encurtar.")
    parser.add_argument("--batch-size", type=int, default=128, help="Casas por lote (cabeça por janela).")
    parser.add_argument("--lr", type=float, default=1e-3, help="Taxa de aprendizado do Adam.")
    parser.add_argument(
        "--patience",
        type=int,
        default=15,
        help="Epocas sem melhora antes de parar antecipadamente. 0 desativa.",
    )
    add_splits_argument(parser, help="Arquivo de splits persistido. O split 'test' nunca e usado no treino.")
    parser.add_argument(
        "--no-splits",
        action="store_true",
        help="Ignora o arquivo de splits e sorteia a validacao (comportamento antigo, nao recomendado).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Treina do zero, ignorando o checkpoint existente.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Semente. Gravada no checkpoint (S-27).")
    parser.add_argument(
        "--augment",
        default="aug0",
        help=(
            "Aumento dirigido ao acervo (S-40), como as letras de `AugmentConfig.version`: "
            "m=espelhar, h=hachura, s=granulacao, p=papel, i=inversao. Ex.: --augment mhsp. "
            "'aug0' (padrao) e o conjunto generico de antes da S-40. NAO MEDIDO ainda: ligar "
            "muda o modelo, e a comparacao honesta e treinar as duas variantes com a mesma "
            "semente e medir com `cvoff-field`."
        ),
    )
    parser.add_argument(
        "--class-weights",
        choices=["none", "balanced"],
        default=DEFAULT_CLASS_WEIGHTS,
        help="Pesos inversos a frequencia na loss. Medido: 'balanced' nao muda a acuracia por "
        "tabuleiro e triplica as casas erradas (docs/EXPERIMENTS.md).",
    )
    parser.add_argument(
        "--cache-size",
        type=int,
        default=DEFAULT_BOARD_CACHE_SIZE,
        help="Tabuleiros residentes no cache do dataset (S-26). 0 desliga.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="Processos de carregamento. Padrao: min(4, cpus//2). 0 carrega no processo principal.",
    )
    parser.add_argument("--no-calibrate", action="store_true", help="Pula a calibracao de temperatura (S-28).")
    parser.add_argument(
        "--keep-ties",
        action="store_true",
        help=(
            "Grava tambem a epoca que EMPATOU com a melhor, em `<modelo>.tie-e<N>.pt` (S-104). "
            "Existe para um experimento, nao para o uso normal: a pergunta e se a epoca "
            "empatada de menor `val_loss` exporta mais em pagina real. Compare com "
            "`cvoff-field --model` nos dois."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Treina mesmo com a auditoria reprovando o dataset (S-102). O que ela barra sao "
            "limites ja declarados: ilegal fatal, FEN nao interpretavel, PNG ausente e o teto "
            "de redundancia da S-63."
        ),
    )

    grupo_arch = parser.add_argument_group("arquitetura (S-29)")
    grupo_arch.add_argument(
        "--backbone", choices=["cnn", "mobilenet_v3_small"], default="cnn", help="Extrator de características."
    )
    grupo_arch.add_argument(
        "--channels", choices=["gray", "rgb"], default="gray", help="Canais da entrada do modelo."
    )
    grupo_arch.add_argument("--image-size", type=int, default=64, help="Lado da casa em pixels, na entrada.")
    grupo_arch.add_argument(
        "--head",
        choices=["linear", "gap", "board"],
        default="linear",
        help="'board' é a cabeça por tabuleiro da S-62b: as 64 casas decididas juntas.",
    )
    grupo_arch.add_argument(
        "--boards-per-batch",
        type=int,
        default=OptimPlan.boards_per_batch,
        help="Tabuleiros por lote com --head board. Ignorado pelas outras cabeças (S-62b).",
    )
    grupo_arch.add_argument(
        "--coords",
        action="store_true",
        help=(
            "Canais de coordenada e paridade na entrada da casa (S-62a). Muda a arch_version "
            "para '...-coords': o checkpoint resultante não carrega num pipeline sem eles, e "
            "vice-versa, de propósito."
        ),
    )

    add_verbose(parser)
    return parser.parse_args(argv)


def _log_epoch(row: dict[str, object]) -> None:
    parts = [f"época {row.get('epoch')}/{row.get('total_epochs', '?')}"]
    for key in ("train_loss", "train_square_acc", "val_loss", "val_square_acc", "val_board_exact_acc"):
        if key in row:
            parts.append(f"{key}={float(row[key]):.6f}")  # type: ignore[arg-type]
    if row.get("is_best"):
        parts.append("★ melhor")
    logger.info("%s", " | ".join(parts))

    recall = row.get("val_per_class_recall")
    if isinstance(recall, dict):
        # Recall por classe importa porque a acuracia por casa e dominada pelas vazias:
        # uma dama que o modelo nunca acerta some dentro de 0,9988.
        piores = sorted((value, name) for name, value in recall.items() if value == value)[:4]
        logger.info("    piores classes: %s", ", ".join(f"{name}={value:.4f}" for value, name in piores))


def _augment_from_letters(texto: str) -> AugmentConfig:
    """`"mhsp"` ou `"augmhsp"` -> `AugmentConfig`. Probabilidades fixas, ligado ou desligado.

    Uma letra liga a transformacao na probabilidade que a S-40 propos; afinar valor por
    valor pela linha de comando seria oferecer um espaco de busca que ninguem mediu.
    """
    letras = texto[3:] if texto.startswith("aug") else texto
    if letras in ("", "0"):
        return AugmentConfig()
    desconhecidas = set(letras) - set("mhspi")
    if desconhecidas:
        raise ValueError(f"Letras desconhecidas em --augment: {''.join(sorted(desconhecidas))} (validas: mhspi)")
    return AugmentConfig(
        hflip=0.5 if "m" in letras else 0.0,
        hatch=0.30 if "h" in letras else 0.0,
        speckle=0.25 if "s" in letras else 0.0,
        paper=0.30 if "p" in letras else 0.0,
        invert=0.03 if "i" in letras else 0.0,
    )


def _audit_gate(args: argparse.Namespace) -> int | None:
    """Audita antes de montar o dataset. `None` libera; `2` recusa com a mensagem (S-102).

    **Nada no fluxo consultava a auditoria antes de treinar.** A CI roda `ruff`, `mypy`,
    `pytest` e um teste de import; o `cvoff-train` montava o dataset sem perguntar nada. O
    resultado era um teto declarado -- o da S-63 -- estourado em 11,0% e um rótulo cujo PNG
    sumiu, *"descartado em silêncio no treino"*, com o comando saindo 0.

    **Sem duplicatas de propósito**, e é o que mantém o portão barato: `check_duplicates=False`
    pula o hash perceptual de milhares de imagens 800x800. Em troca, o teto de redundância não
    é conferido aqui -- ele é o único dos quatro limites que precisa dos hashes, e vigiá-lo é
    trabalho do `cvoff-audit --strict`, que a CI roda. O que este portão pega são os três que
    corrompem o **treino desta execução**: ilegal fatal, FEN não interpretável e PNG ausente.

    Um dataset ausente não é reprovação: num clone limpo o `labels.csv` pode nem existir, e
    quem reclama disso é o próprio `train_model`, com mensagem melhor que esta.
    """
    if args.force or not Path(args.csv).exists():
        return None

    relatorio = audit_dataset(args.csv, args.samples, check_duplicates=False)
    violacoes = relatorio.violations()
    if not violacoes:
        return None

    print("A auditoria reprovou o dataset, e o treino não começou:")
    for violacao in violacoes:
        print(f"  - {violacao}")
    print()
    print("Confira o quadro inteiro com: cvoff-audit")
    print("Para treinar assim mesmo:     cvoff-train --force")
    return EXIT_BAD_INPUT


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    try:
        augment = _augment_from_letters(args.augment)
    except ValueError as exc:
        print(f"Erro: {exc}")
        return EXIT_BAD_INPUT
    if not augment.version.endswith("0"):
        logger.info("Aumento dirigido ligado: %s. Isto muda o modelo (S-40).", augment.version)

    recusa = _audit_gate(args)
    if recusa is not None:
        return recusa

    run = train_model(
        csv_path=args.csv,
        samples_dir=args.samples,
        model_path=args.model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        patience=args.patience,
        progress_cb=_log_epoch,
        fresh=args.fresh,
        splits_path=None if args.no_splits else args.splits,
        arch=ArchConfig(
            backbone=args.backbone,
            channels=args.channels,
            image_size=args.image_size,
            head=args.head,
            coords=args.coords,
        ),
        class_weights=args.class_weights,
        seed=args.seed,
        cache_size=args.cache_size,
        # Diferente do padrao da biblioteca (0): este e um entrypoint com guarda
        # `if __name__ == "__main__"`, entao `spawn` no Windows e seguro aqui.
        num_workers=args.num_workers,
        calibrate=not args.no_calibrate,
        augment=augment,
        boards_per_batch=args.boards_per_batch,
        keep_ties=args.keep_ties,
    )

    logger.info(
        "Melhor época: %d de %d (%s = %.6f).",
        run.best_epoch,
        len(run.history),
        run.best_metric_name,
        run.best_metric,
    )
    if run.ece_after is not None:
        logger.info("Temperatura calibrada: %.4f (ECE no val %.5f → %.5f).", run.temperature, run.ece_before, run.ece_after)
    logger.info("Confira o resultado no conjunto de teste com: cvoff-eval --split test --model %s", args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
