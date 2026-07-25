from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch

from .board_detection import split_board_into_cells
from .fen_utils import fen_from_class_indices
from .model import PieceClassifier, preprocess_cell_to_tensor


def _load_checkpoint(path: Path, map_location: str) -> object:
    try:
        return torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:
        return torch.load(path, map_location=map_location)


def load_model(model_path: Path, device: Optional[str] = None) -> tuple[PieceClassifier, str]:
    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = PieceClassifier()
    model_path = Path(model_path)

    if model_path.exists():
        ckpt = _load_checkpoint(model_path, map_location=dev)
        state_dict = ckpt["model_state"] if isinstance(ckpt, dict) and "model_state" in ckpt else ckpt
        model.load_state_dict(state_dict, strict=False)
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
