from __future__ import annotations

import cv2
import numpy as np
import torch
import torch.nn as nn

from .config import MODEL_IMAGE_SIZE, PIECE_CLASSES


class PieceClassifier(nn.Module):
    def __init__(self, num_classes: int = len(PIECE_CLASSES)) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128 * 8 * 8, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.25),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        return self.classifier(x)


def preprocess_cell_to_tensor(cell_bgr: np.ndarray) -> torch.Tensor:
    gray = cv2.cvtColor(cell_bgr, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(gray, (MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE), interpolation=cv2.INTER_AREA)
    normalized = resized.astype(np.float32) / 255.0
    return torch.from_numpy(normalized).unsqueeze(0)
