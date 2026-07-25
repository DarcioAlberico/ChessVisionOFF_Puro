from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import torch

from .board_detection import split_board_into_cells
from .checkpoint import load_state_dict
from .fen_utils import fen_from_class_indices
from .model import PieceClassifier, preprocess_cell_to_tensor

logger = logging.getLogger(__name__)


def load_model(model_path: Path, device: str | None = None) -> tuple[PieceClassifier, str]:
    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = PieceClassifier()
    model_path = Path(model_path)

    if model_path.exists():
        model.load_state_dict(load_state_dict(model_path, map_location=dev), strict=False)
        logger.info("Modelo carregado de %s em %s.", model_path, dev)
    else:
        logger.warning("Checkpoint nao encontrado em %s: usando pesos aleatorios.", model_path)

    model.to(dev)
    model.eval()
    return model, dev


def predict_fen_from_board(
    board_rgb: np.ndarray,
    model: PieceClassifier,
    device: str,
    rotate_180: bool = False,
) -> tuple[str, float]:
    board = board_rgb
    if rotate_180:
        board = cv2.rotate(board, cv2.ROTATE_180)

    cells = split_board_into_cells(board)
    batch = torch.stack([preprocess_cell_to_tensor(cell) for cell in cells], dim=0).to(device)

    with torch.no_grad():
        logits = model(batch)
        probs = torch.softmax(logits, dim=1)
        conf, pred = probs.max(dim=1)

    fen = fen_from_class_indices(pred.cpu().numpy().tolist())
    confidence = float(conf.mean().item())
    return fen, confidence
