from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import torch

logger = logging.getLogger(__name__)


def load_state_dict(path: Path, *, map_location: str) -> dict[str, Any]:
    """Le um checkpoint .pt e devolve o state_dict do modelo.

    Aceita os dois formatos em uso: `{"model_state": ...}` (gravado por `train_model`)
    e um state_dict cru. Prefere `weights_only=True`, com fallback para versoes de
    torch que ainda nao suportam o parametro.
    """
    try:
        checkpoint = torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:
        logger.debug("torch.load sem weights_only nesta versao; usando fallback.")
        checkpoint = torch.load(path, map_location=map_location)

    if isinstance(checkpoint, dict) and "model_state" in checkpoint:
        state = checkpoint["model_state"]
    else:
        state = checkpoint

    if not isinstance(state, dict):
        raise ValueError(f"Checkpoint invalido em {path}: esperado dict de pesos, obtido {type(state).__name__}.")
    return state
