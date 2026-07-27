"""Medição de qualidade do reconhecimento.

Antes disto o projeto não tinha como afirmar que uma mudança melhorou algo: a única
métrica era acurácia por casa calculada durante o treino, sobre dados de treino.

A métrica que importa aqui é `board_exact_accuracy` -- a fração de diagramas que sai
sem **nenhuma** correção manual. Acurácia por casa é enganosa neste domínio: 77% das
casas são vazias, então um modelo que só respondesse "vazio" marcaria 77%.

Ver S-08 em docs/SPEC.md.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn as nn

from .board_detection import split_board_into_cells
from .calibration import expected_calibration_error, reliability_table
from .config import BOARD_SIZE, CONSTRAINED_DECODING, IDX_TO_CLASS, PIECE_CLASSES, TTA_ENABLED
from .dataset import BoardFenDataset
from .decode import DecodeResult
from .fen_utils import check_position, fen_from_class_indices, labels_from_fen
from .inference import board_probabilities, load_model, prediction_from_probs
from .model import DEFAULT_ARCH, preprocess_cell_to_tensor

logger = logging.getLogger(__name__)

NUM_CLASSES = len(PIECE_CLASSES)


@dataclass
class BoardResult:
    filename: str
    true_labels: list[int]
    pred_labels: list[int]
    square_confidences: list[float]
    predicted_fen: str
    expected_fen: str

    @property
    def errors(self) -> int:
        # strict=True: um descasamento de tamanho e bug, nao algo a truncar em silencio.
        return sum(1 for a, b in zip(self.true_labels, self.pred_labels, strict=True) if a != b)

    @property
    def is_exact(self) -> bool:
        return self.errors == 0

    @property
    def min_confidence(self) -> float:
        return min(self.square_confidences) if self.square_confidences else 0.0

    @property
    def mean_confidence(self) -> float:
        return float(np.mean(self.square_confidences)) if self.square_confidences else 0.0


@dataclass
class EvaluationReport:
    split: str
    model_path: Path
    device: str
    board_count: int = 0
    square_count: int = 0
    square_correct: int = 0
    boards_exact: int = 0
    boards_within_one: int = 0
    illegal_predictions: int = 0
    illegal_expected: int = 0
    constrained_decoding: bool = False
    decoder_repaired_boards: int = 0
    """Tabuleiros em que a decodificação com restrições alterou pelo menos uma casa."""

    decoder_repaired_squares: int = 0
    decoder_helped: int = 0
    """Reparos que transformaram um tabuleiro errado em exato -- o ganho da S-11."""

    decoder_hurt: int = 0
    """Reparos que estragaram um tabuleiro que o argmax já acertava. Tem de ser ~0."""

    decoder_squares_fixed: int = 0
    """Casas em que o reparo trocou a classe errada pela correta.

    Contar por casa e não só por tabuleiro é o que torna o efeito visível: um reparo em
    tabuleiro que já tinha dois erros não muda `decoder_helped`, mas reduzir de dois erros
    para um é um ganho real -- é uma casa menos para o humano corrigir.
    """

    decoder_squares_broken: int = 0
    """Casas corretas no argmax que o reparo estragou. É o custo direto da S-11."""

    decoder_squares_still_wrong: int = 0
    """Casas que já estavam erradas e continuaram erradas, com outra classe.

    Neutro para a acurácia, mas não para a legalidade: é assim que a busca satisfaz as
    regras quando o modelo não colocou a classe certa em nenhuma posição alta.
    """

    decoder_gave_up: int = 0
    """Tabuleiros em que a busca esgotou o limite sem achar posição legal."""

    temperature: float = 1.0
    """Temperatura da calibração aplicada nas probabilidades (S-28). 1,0 = não calibrado."""

    tta: bool = False
    """Se a leitura somou as sete vistas do TTA (S-29)."""

    confusion: np.ndarray = field(default_factory=lambda: np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64))
    conf_when_correct: list[float] = field(default_factory=list)
    conf_when_wrong: list[float] = field(default_factory=list)
    boards: list[BoardResult] = field(default_factory=list)

    # ---- métricas derivadas ----

    @property
    def square_accuracy(self) -> float:
        return self.square_correct / self.square_count if self.square_count else 0.0

    @property
    def board_exact_accuracy(self) -> float:
        """Métrica primária: diagramas sem nenhuma casa errada."""
        return self.boards_exact / self.board_count if self.board_count else 0.0

    @property
    def board_within_one_accuracy(self) -> float:
        """Diagramas com no máximo uma casa errada: aproxima o custo de correção."""
        return self.boards_within_one / self.board_count if self.board_count else 0.0

    @property
    def illegal_rate(self) -> float:
        return self.illegal_predictions / self.board_count if self.board_count else 0.0

    def per_class(self) -> dict[str, dict[str, float | int]]:
        result: dict[str, dict[str, float | int]] = {}
        for idx, name in enumerate(PIECE_CLASSES):
            support = int(self.confusion[idx].sum())
            predicted = int(self.confusion[:, idx].sum())
            hits = int(self.confusion[idx, idx])
            result[name] = {
                "support": support,
                "recall": hits / support if support else 0.0,
                "precision": hits / predicted if predicted else 0.0,
            }
        return result

    def top_confusions(self, limit: int = 10) -> list[tuple[str, str, int]]:
        pairs: list[tuple[str, str, int]] = []
        for true_idx in range(NUM_CLASSES):
            for pred_idx in range(NUM_CLASSES):
                if true_idx == pred_idx:
                    continue
                count = int(self.confusion[true_idx, pred_idx])
                if count:
                    pairs.append((PIECE_CLASSES[true_idx], PIECE_CLASSES[pred_idx], count))
        return sorted(pairs, key=lambda item: -item[2])[:limit]

    def _confidence_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        confidences = np.array(self.conf_when_correct + self.conf_when_wrong, dtype=np.float64)
        correct = np.array([1.0] * len(self.conf_when_correct) + [0.0] * len(self.conf_when_wrong), dtype=np.float64)
        return confidences, correct

    def expected_calibration_error(self, bins: int = 10) -> float:
        """ECE por casa: diferença média entre confiança declarada e acerto observado.

        0 significa que "confiança 0,9" corresponde de fato a 90% de acerto. A conta mora
        em `calibration.py` desde a S-28, para que o número que decide o limiar e o número
        que o relatório imprime não possam divergir.
        """
        confidences, correct = self._confidence_arrays()
        return expected_calibration_error(confidences, correct, bins=bins)

    def reliability(self, bins: int = 10) -> list[dict[str, float | int]]:
        """Curva de calibração por faixa de confiança, para a S-28."""
        confidences, correct = self._confidence_arrays()
        return [
            {
                "low": faixa.low,
                "high": faixa.high,
                "count": faixa.count,
                "mean_confidence": faixa.mean_confidence,
                "accuracy": faixa.accuracy,
                "gap": faixa.gap,
            }
            for faixa in reliability_table(confidences, correct, bins=bins)
        ]

    def board_confidence_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """Confiança mínima por tabuleiro e se ele saiu exato.

        É a granularidade em que o gate da S-15 decide -- ele aceita ou rejeita o diagrama
        inteiro, não a casa --, então é nela que o limiar tem de ser derivado.
        """
        return (
            np.array([board.min_confidence for board in self.boards], dtype=np.float64),
            np.array([1.0 if board.is_exact else 0.0 for board in self.boards], dtype=np.float64),
        )

    def confidence_auc(self, use_min: bool = True) -> float:
        """AUC da confiança do tabuleiro como detector de erro.

        Mede se a confiança serve para priorizar revisão manual. 0,5 é aleatório.
        `use_min` compara o mínimo por casa (proposta da S-10) em vez da média atual.
        """
        scores_exact: list[float] = []
        scores_wrong: list[float] = []
        for board in self.boards:
            score = board.min_confidence if use_min else board.mean_confidence
            (scores_exact if board.is_exact else scores_wrong).append(score)

        if not scores_exact or not scores_wrong:
            return float("nan")

        # AUC via contagem de pares concordantes (equivalente a Mann-Whitney U).
        wrong = np.array(scores_wrong)
        wins = 0.0
        for score in scores_exact:
            wins += float((wrong < score).sum()) + 0.5 * float((wrong == score).sum())
        return wins / (len(scores_exact) * len(scores_wrong))

    def as_dict(self) -> dict[str, Any]:
        return {
            "split": self.split,
            "model_path": str(self.model_path),
            "device": self.device,
            "board_count": self.board_count,
            "square_count": self.square_count,
            "square_accuracy": self.square_accuracy,
            "board_exact_accuracy": self.board_exact_accuracy,
            "board_within_one_accuracy": self.board_within_one_accuracy,
            "illegal_rate": self.illegal_rate,
            "illegal_predictions": self.illegal_predictions,
            "illegal_expected": self.illegal_expected,
            "mean_confidence_when_correct": float(np.mean(self.conf_when_correct)) if self.conf_when_correct else 0.0,
            "mean_confidence_when_wrong": float(np.mean(self.conf_when_wrong)) if self.conf_when_wrong else 0.0,
            "expected_calibration_error": self.expected_calibration_error(),
            "reliability": self.reliability(),
            "confidence_auc_min_square": self.confidence_auc(use_min=True),
            "confidence_auc_mean_square": self.confidence_auc(use_min=False),
            "temperature": self.temperature,
            "tta": self.tta,
            "constrained_decoding": self.constrained_decoding,
            "decoder_repaired_boards": self.decoder_repaired_boards,
            "decoder_repaired_squares": self.decoder_repaired_squares,
            "decoder_helped": self.decoder_helped,
            "decoder_hurt": self.decoder_hurt,
            "decoder_squares_fixed": self.decoder_squares_fixed,
            "decoder_squares_broken": self.decoder_squares_broken,
            "decoder_squares_still_wrong": self.decoder_squares_still_wrong,
            "decoder_gave_up": self.decoder_gave_up,
            "per_class": self.per_class(),
            "top_confusions": [
                {"expected": a, "predicted": b, "count": c} for a, b, c in self.top_confusions(limit=15)
            ],
        }


def _load_board_image(path: Path) -> np.ndarray | None:
    image = cv2.imread(str(path))
    if image is None:
        return None
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    if image.shape[:2] != (BOARD_SIZE, BOARD_SIZE):
        image = cv2.resize(image, (BOARD_SIZE, BOARD_SIZE))
    return image


def evaluate_dataset(
    dataset: BoardFenDataset,
    model: nn.Module,
    device: str,
    *,
    split_name: str = "?",
    model_path: Path | None = None,
    boards_per_batch: int = 8,
    constrained: bool = CONSTRAINED_DECODING,
    tta: bool = TTA_ENABLED,
) -> EvaluationReport:
    """Avalia o modelo sobre os tabuleiros de um dataset já filtrado por split.

    `constrained` liga a decodificação com restrições (S-11). Avaliar com e sem é o que
    permite afirmar se ela ajuda -- por isso o relatório carrega o flag e conta reparos
    que ajudaram e que atrapalharam separadamente.
    """
    report = EvaluationReport(
        split=split_name,
        model_path=Path(model_path) if model_path else Path("<memória>"),
        device=device,
        constrained_decoding=constrained,
    )

    arch = getattr(model, "arch", DEFAULT_ARCH)
    temperature = float(getattr(model, "temperature", 1.0))
    report.temperature = temperature
    report.tta = tta

    pending: list[tuple[str, np.ndarray, list[int], str]] = []

    def flush() -> None:
        if not pending:
            return
        if tta:
            matrices = np.stack([board_probabilities(board, model, device, tta=True) for _, board, _, _ in pending])
        else:
            tensors = [
                preprocess_cell_to_tensor(cell, arch)
                for _, board, _, _ in pending
                for cell in split_board_into_cells(board)
            ]
            batch = torch.stack(tensors).to(device)
            with torch.inference_mode():
                probs = torch.softmax(model(batch) / temperature, dim=1)
            matrices = probs.cpu().numpy().astype(np.float64).reshape(len(pending), 64, NUM_CLASSES)

        for row, (filename, _board, true_labels, expected_fen) in enumerate(pending):
            prediction = prediction_from_probs(matrices[row], constrained=constrained)
            _record(
                report,
                filename,
                true_labels,
                prediction.class_indices,
                [float(value) for value in prediction.square_confidences],
                expected_fen,
                decode=prediction.decode,
            )
        pending.clear()

    for entry_idx, entry in enumerate(dataset.entries):
        image = _load_board_image(dataset.samples_dir / entry.filename)
        if image is None:
            logger.warning("Imagem ilegível, ignorada na avaliação: %s", entry.filename)
            continue
        try:
            true_labels = labels_from_fen(entry.fen)
        except ValueError as exc:
            logger.warning("Rótulo inválido em %s: %s", entry.filename, exc)
            continue

        pending.append((entry.filename, image, true_labels, entry.fen))
        if len(pending) >= boards_per_batch:
            flush()
        if entry_idx and entry_idx % 500 == 0:
            logger.info("Avaliados %d/%d tabuleiros...", entry_idx, len(dataset.entries))

    flush()
    return report


def _record(
    report: EvaluationReport,
    filename: str,
    true_labels: list[int],
    pred_labels: list[int],
    square_confidences: list[float],
    expected_fen: str,
    decode: DecodeResult | None = None,
) -> None:
    predicted_fen = fen_from_class_indices(pred_labels)
    result = BoardResult(
        filename=filename,
        true_labels=true_labels,
        pred_labels=pred_labels,
        square_confidences=square_confidences,
        predicted_fen=predicted_fen,
        expected_fen=expected_fen,
    )
    report.boards.append(result)
    report.board_count += 1
    report.square_count += len(true_labels)

    for true_idx, pred_idx, confidence in zip(true_labels, pred_labels, square_confidences, strict=True):
        report.confusion[true_idx, pred_idx] += 1
        if true_idx == pred_idx:
            report.square_correct += 1
            report.conf_when_correct.append(confidence)
        else:
            report.conf_when_wrong.append(confidence)

    if result.is_exact:
        report.boards_exact += 1
    if result.errors <= 1:
        report.boards_within_one += 1

    if check_position(predicted_fen).is_fatal:
        report.illegal_predictions += 1
    if check_position(expected_fen).is_fatal:
        report.illegal_expected += 1

    if decode is not None and decode.changed_squares:
        report.decoder_repaired_boards += 1
        report.decoder_repaired_squares += len(decode.changed_squares)

        # Comparar com o que o argmax teria dado e o unico jeito de separar reparo que
        # ajudou de reparo que estragou. `changed_squares` guarda a classe original.
        argmax_labels = list(pred_labels)
        for square, base_class, _ in decode.changed_squares:
            argmax_labels[square] = base_class
        argmax_exact = argmax_labels == true_labels

        if result.is_exact and not argmax_exact:
            report.decoder_helped += 1
        elif not result.is_exact and argmax_exact:
            report.decoder_hurt += 1

        for square, base_class, final_class in decode.changed_squares:
            expected_class = true_labels[square]
            if final_class == expected_class:
                report.decoder_squares_fixed += 1
            elif base_class == expected_class:
                report.decoder_squares_broken += 1
            else:
                report.decoder_squares_still_wrong += 1

    if decode is not None and not decode.constraints_satisfied:
        report.decoder_gave_up += 1


def class_distribution(dataset: BoardFenDataset) -> Counter[str]:
    counts: Counter[str] = Counter()
    for entry in dataset.entries:
        try:
            for class_idx in labels_from_fen(entry.fen):
                counts[IDX_TO_CLASS[class_idx]] += 1
        except ValueError:
            continue
    return counts


def evaluate_split(
    csv_path: Path,
    samples_dir: Path,
    model_path: Path,
    *,
    split: str,
    splits: dict[str, Any],
    device: str | None = None,
    boards_per_batch: int = 8,
    constrained: bool = CONSTRAINED_DECODING,
    tta: bool = TTA_ENABLED,
) -> EvaluationReport:
    model, resolved_device = load_model(Path(model_path), device=device)
    arch = getattr(model, "arch", DEFAULT_ARCH)

    dataset = BoardFenDataset(csv_path, samples_dir, split=split, splits=splits, arch=arch)  # type: ignore[arg-type]
    if not dataset.entries:
        raise ValueError(f"Nenhuma amostra no split '{split}'. Rode `cvoff-audit` e verifique data/splits.csv.")

    return evaluate_dataset(
        dataset,
        model,
        resolved_device,
        split_name=split,
        model_path=Path(model_path),
        boards_per_batch=boards_per_batch,
        constrained=constrained,
        tta=tta,
    )
