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

from .board_detection import split_board_into_cells
from .config import BOARD_SIZE, IDX_TO_CLASS, PIECE_CLASSES
from .dataset import BoardFenDataset
from .fen_utils import check_position, fen_from_class_indices, labels_from_fen
from .inference import load_model
from .model import PieceClassifier, preprocess_cell_to_tensor

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

    def expected_calibration_error(self, bins: int = 10) -> float:
        """ECE: diferença média entre confiança declarada e acerto observado.

        0 significa que "confiança 0,9" corresponde de fato a 90% de acerto.
        """
        confidences = np.array(self.conf_when_correct + self.conf_when_wrong)
        correct = np.array([1.0] * len(self.conf_when_correct) + [0.0] * len(self.conf_when_wrong))
        if confidences.size == 0:
            return 0.0

        edges = np.linspace(0.0, 1.0, bins + 1)
        error = 0.0
        for low, high in zip(edges[:-1], edges[1:], strict=True):
            mask = (confidences > low) & (confidences <= high)
            if not mask.any():
                continue
            weight = mask.mean()
            error += weight * abs(correct[mask].mean() - confidences[mask].mean())
        return float(error)

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
            "confidence_auc_min_square": self.confidence_auc(use_min=True),
            "confidence_auc_mean_square": self.confidence_auc(use_min=False),
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
    model: PieceClassifier,
    device: str,
    *,
    split_name: str = "?",
    model_path: Path | None = None,
    boards_per_batch: int = 8,
) -> EvaluationReport:
    """Avalia o modelo sobre os tabuleiros de um dataset já filtrado por split."""
    report = EvaluationReport(
        split=split_name,
        model_path=Path(model_path) if model_path else Path("<memória>"),
        device=device,
    )

    pending: list[tuple[str, np.ndarray, list[int], str]] = []

    def flush() -> None:
        if not pending:
            return
        tensors = [preprocess_cell_to_tensor(cell) for _, board, _, _ in pending for cell in split_board_into_cells(board)]
        batch = torch.stack(tensors).to(device)
        with torch.inference_mode():
            probs = torch.softmax(model(batch), dim=1)
            confidences, predictions = probs.max(dim=1)

        preds = predictions.cpu().numpy().reshape(len(pending), 64)
        confs = confidences.cpu().numpy().reshape(len(pending), 64)

        for row, (filename, _board, true_labels, expected_fen) in enumerate(pending):
            pred_labels = [int(v) for v in preds[row]]
            square_confs = [float(v) for v in confs[row]]
            _record(report, filename, true_labels, pred_labels, square_confs, expected_fen)
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
) -> EvaluationReport:
    dataset = BoardFenDataset(csv_path, samples_dir, split=split, splits=splits)  # type: ignore[arg-type]
    if not dataset.entries:
        raise ValueError(f"Nenhuma amostra no split '{split}'. Rode `cvoff-audit` e verifique data/splits.csv.")

    model, resolved_device = load_model(Path(model_path), device=device)
    return evaluate_dataset(
        dataset,
        model,
        resolved_device,
        split_name=split,
        model_path=Path(model_path),
        boards_per_batch=boards_per_batch,
    )
