from __future__ import annotations

import argparse
import json
import logging
import textwrap
from pathlib import Path

from ..calibration import confidence_for_accuracy
from ..config import (
    ACCEPT_MIN_CONFIDENCE,
    DEFAULT_DATASET_CSV,
    DEFAULT_MODEL_PATH,
    DEFAULT_SAMPLES_DIR,
    MAX_DECODE_CHANGES,
    PROJECT_ROOT,
)
from ..evaluation import EvaluationReport, evaluate_split
from ..inference import describe_device
from ..logging_setup import configure_logging, default_log_file
from ..splits import load_splits
from . import cli_errors

logger = logging.getLogger(__name__)

DEFAULT_SPLITS_PATH = PROJECT_ROOT / "data" / "splits.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Avalia o modelo em um split, reportando acurácia exata por tabuleiro.",
    )
    parser.add_argument("--split", choices=("train", "val", "test"), default="test")
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATASET_CSV)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES_DIR)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--device", type=str, default=None, help="cpu ou cuda. Padrão: detecta.")
    parser.add_argument("--batch-boards", type=int, default=8, help="Tabuleiros por lote de inferência.")
    parser.add_argument("--json", type=Path, default=None, help="Grava as métricas em JSON.")
    parser.add_argument("--show-errors", type=int, default=5, help="Tabuleiros com erro exibidos em detalhe.")
    parser.add_argument(
        "--no-constrained-decoding",
        action="store_true",
        help="Avalia com argmax puro, sem a decodificacao restrita (S-11).",
    )
    parser.add_argument("--tta", action="store_true", help="Soma as sete vistas do TTA (S-29). ~7x mais lento.")
    parser.add_argument(
        "--calibration-target",
        type=float,
        default=None,
        help="Deriva o limiar de aceite (S-15) da curva: menor confianca minima cuja "
        "fracao de tabuleiros exatos atinge este alvo (ex.: 0.95).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _print_calibration(report: EvaluationReport, target: float | None) -> None:
    """A curva de calibração e o limiar que ela justifica (S-28).

    O `ACCEPT_MIN_CONFIDENCE = 0,80` da S-15 foi escolhido olhando a distribuição e está
    documentado como provisório desde a Fase 2. Aqui ele passa a ter uma derivação: qual é
    a menor confiança mínima a partir da qual a fração de tabuleiros **exatos** atinge o
    alvo. Note a granularidade -- o gate aceita ou rejeita o diagrama inteiro, então o
    limiar tem de ser derivado por tabuleiro, não por casa.
    """
    print("  Curva de calibração por casa (S-28)")
    print(f"    {'faixa':>13} {'casas':>9} {'confiança':>10} {'acerto':>9} {'lacuna':>9}")
    for faixa in report.reliability():
        print(
            f"    {faixa['low']:.2f}–{faixa['high']:.2f}   {faixa['count']:>9} "
            f"{faixa['mean_confidence']:>10.4f} {faixa['accuracy']:>9.4f} {faixa['gap']:>+9.4f}"
        )
    print()

    if target is None:
        return

    confidences, exact = report.board_confidence_arrays()
    threshold = confidence_for_accuracy(confidences, exact, target)
    print(f"  Limiar de aceite derivado da curva, para {target:.0%} de tabuleiros exatos")
    if threshold is None:
        print("    Nenhum limiar atinge o alvo neste split.")
        print("    Não é falha da conta: significa que o erro não está concentrado onde a")
        print("    confiança é baixa. Ver o caso do bispo lido como peão com confiança 1,000.")
    else:
        aceitos = int((confidences >= threshold).sum())
        precisao = float(exact[confidences >= threshold].mean())
        print(f"    confiança mínima >= {threshold:.2f}")
        print(f"    aceita {aceitos} de {len(confidences)} tabuleiros, {precisao:.4f} deles exatos")
        print(f"    (ACCEPT_MIN_CONFIDENCE em uso hoje: {ACCEPT_MIN_CONFIDENCE:.2f})")
    print()


def _print_report(report: EvaluationReport, show_errors: int, calibration_target: float | None = None) -> None:
    print()
    print("=" * 78)
    print(f"Avaliação -- split '{report.split}'")
    print("=" * 78)
    print(f"  Modelo ......................... {report.model_path}")
    print(f"  Dispositivo .................... {describe_device(report.device)}")
    print(f"  Temperatura (S-28) ............. {report.temperature:.4f}{'' if report.temperature != 1.0 else '  (não calibrado)'}")
    print(f"  TTA (S-29) ..................... {'7 vistas' if report.tta else 'desligado'}")
    print(f"  Tabuleiros ..................... {report.board_count}")
    print(f"  Casas .......................... {report.square_count}")
    if report.split_caveat:
        # **Antes** dos números, e não depois: a S-07 inteira existe para tornar impossível
        # medir num conjunto que o modelo já viu, e uma ressalva impressa embaixo de um
        # `0,9906` é lida depois de o número já ter sido anotado (S-103).
        print()
        print("  !! Ressalva sobre a partição")
        for linha in textwrap.wrap(report.split_caveat, width=72):
            print(f"     {linha}")
    print()
    print("  Acurácia")
    print(f"    Exata por tabuleiro .......... {report.board_exact_accuracy:.4f}   <-- métrica primária")
    print(f"    Com até 1 casa errada ........ {report.board_within_one_accuracy:.4f}")
    print(f"    Por casa ..................... {report.square_accuracy:.4f}")
    errors = report.square_count - report.square_correct
    print(f"    Casas erradas ................ {errors} de {report.square_count}")
    print(f"    Tabuleiros com erro .......... {report.board_count - report.boards_exact}")
    print()
    print("  Legalidade")
    print(f"    Predições ilegais ............ {report.illegal_predictions} ({report.illegal_rate:.4f})")
    print(f"    Rótulos ilegais no split ..... {report.illegal_expected}")
    print()
    print("  Decodificação")
    if not report.constrained_decoding:
        print("    Argmax puro (--no-constrained-decoding)")
    else:
        print(f"    Restrita (S-11), até {MAX_DECODE_CHANGES} trocas")
        print(f"    Tabuleiros reparados ......... {report.decoder_repaired_boards}")
        print(f"    Casas reescritas ............. {report.decoder_repaired_squares}")
        print(f"      viraram a classe correta ... {report.decoder_squares_fixed}   <-- ganho")
        print(f"      estragaram casa correta .... {report.decoder_squares_broken}   <-- custo")
        print(f"      erro trocado por erro ...... {report.decoder_squares_still_wrong}")
        print(f"    Tabuleiros que viraram exatos  {report.decoder_helped}")
        print(f"    Tabuleiros exatos perdidos ... {report.decoder_hurt}   <-- tem de ser 0")
        print(f"    Buscas sem solução ........... {report.decoder_gave_up}")
    print()
    print("  Calibração da confiança")
    metrics = report.as_dict()
    print(f"    Média quando acerta .......... {metrics['mean_confidence_when_correct']:.4f}")
    print(f"    Média quando erra ............ {metrics['mean_confidence_when_wrong']:.4f}")
    print(f"    ECE .......................... {report.expected_calibration_error():.4f}")
    auc_min = report.confidence_auc(use_min=True)
    auc_mean = report.confidence_auc(use_min=False)
    print(f"    AUC detectando erro (mínimo) . {auc_min:.4f}   <-- proposta S-10")
    print(f"    AUC detectando erro (média) .. {auc_mean:.4f}   <-- comportamento atual")
    if auc_min == auc_min and auc_mean == auc_mean:  # descarta NaN
        delta = auc_min - auc_mean
        veredito = "mínimo é melhor" if delta > 0.01 else ("média é melhor" if delta < -0.01 else "empate")
        print(f"    Veredito ..................... {veredito} (Δ {delta:+.4f})")
    print()
    _print_calibration(report, calibration_target)
    print("  Por classe")
    print(f"    {'classe':>7} {'suporte':>8} {'recall':>8} {'precisão':>9}")
    for name, values in report.per_class().items():
        if not values["support"]:
            continue
        print(f"    {name:>7} {values['support']:>8} {values['recall']:>8.4f} {values['precision']:>9.4f}")

    confusions = report.top_confusions(limit=10)
    if confusions:
        print()
        print("  Confusões mais frequentes (esperado -> predito)")
        for expected, predicted, count in confusions:
            print(f"    {expected:>5} -> {predicted:<5} {count}")

    failing = [board for board in report.boards if not board.is_exact]
    if failing and show_errors:
        print()
        print(f"  Tabuleiros com erro (primeiros {min(show_errors, len(failing))} de {len(failing)})")
        for board in sorted(failing, key=lambda b: -b.errors)[:show_errors]:
            print(f"    {board.filename}  erros={board.errors}  conf_min={board.min_confidence:.3f}")
            print(f"      esperado: {board.expected_fen.split()[0]}")
            print(f"      predito : {board.predicted_fen}")
    print()


@cli_errors
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose, log_file=default_log_file())

    splits = load_splits(args.splits)
    if not splits:
        print(f"Arquivo de splits vazio ou ausente: {args.splits}")
        print("Gere-o antes de avaliar (ver docs/SPEC.md, S-07).")
        return 1

    report = evaluate_split(
        args.csv,
        args.samples,
        args.model,
        split=args.split,
        splits=splits,
        device=args.device,
        boards_per_batch=args.batch_boards,
        constrained=not args.no_constrained_decoding,
        tta=args.tta,
    )
    _print_report(report, show_errors=args.show_errors, calibration_target=args.calibration_target)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Métricas gravadas em {args.json}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
