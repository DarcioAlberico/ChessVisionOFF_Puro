from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch

from .board_detection import split_board_into_cells
from .checkpoint import load_state_dict
from .config import (
    CONSTRAINED_DECODING,
    MAX_DECODE_CHANGES,
    PIECE_CLASSES,
    UNCERTAIN_SQUARE_THRESHOLD,
)
from .decode import DecodeResult, decode_constrained
from .fen_utils import PositionCheck, check_position, fen_from_class_indices, square_name
from .model import PieceClassifier, preprocess_cell_to_tensor

logger = logging.getLogger(__name__)

_EPS = 1e-12


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


@dataclass(frozen=True, eq=False)
class BoardPrediction:
    """Predição de um tabuleiro com a distribuição por casa preservada.

    O pipeline antigo colapsava as 64×13 probabilidades em uma FEN e um único número (a
    média das confianças). Duas informações se perdiam aí: **onde** o modelo está inseguro
    e **qual** seria a segunda leitura mais provável de cada casa. A primeira alimenta a
    revisão humana (S-21); a segunda é o insumo da decodificação com restrições (S-11).
    """

    probs: np.ndarray
    """(64, 13) — probabilidade de cada classe por casa, em ordem de leitura (a8..h1)."""

    class_indices: list[int]
    """Argmax por casa. Sem restrição de legalidade: pode conter dois reis brancos."""

    fen_board: str
    """Apenas o campo de peças da FEN, sem lado a jogar nem contadores."""

    mean_confidence: float
    """Média das confianças. Enganosa neste domínio: ~77% das casas são vazias e triviais,
    então a média fica ~0,97 mesmo em tabuleiro com erro. Mantida para comparação."""

    min_confidence: float
    """Confiança da casa mais insegura. É o sinal que de fato separa acerto de erro."""

    mean_entropy: float
    """Entropia média por casa, em nats. Alternativa contínua ao mínimo."""

    uncertain_squares: list[int]
    """Índices das casas abaixo do limiar, da menos confiante para a mais confiante."""

    position: PositionCheck
    """Legalidade da posição decodificada (S-05)."""

    decode: DecodeResult | None = None
    """Reparo aplicado pela decodificação com restrições (S-11), quando ativa.

    `None` significa argmax puro. Quando presente, `class_indices` e `fen_board` já são
    os do reparo -- `decode.changed_squares` diz o que mudou em relação ao argmax."""

    @property
    def square_confidences(self) -> np.ndarray:
        return self.probs[np.arange(len(self.class_indices)), self.class_indices]

    @property
    def uncertain_square_names(self) -> list[str]:
        return [square_name(index) for index in self.uncertain_squares]

    def runner_up(self, square_index: int) -> tuple[int, float]:
        """Segunda classe mais provável da casa e sua probabilidade."""
        order = np.argsort(self.probs[square_index])[::-1]
        second = int(order[1])
        return second, float(self.probs[square_index, second])


def prediction_from_probs(
    probs: np.ndarray,
    *,
    uncertain_threshold: float = UNCERTAIN_SQUARE_THRESHOLD,
    constrained: bool = False,
    max_changes: int = MAX_DECODE_CHANGES,
) -> BoardPrediction:
    """Monta a `BoardPrediction` a partir da matriz (64, 13) já normalizada.

    Separada de `predict_board` para permitir testar a lógica de decisão com matrizes
    sintéticas, sem carregar modelo nem imagem.

    O padrão aqui é argmax puro -- esta é a camada de baixo nível, e quem quer a leitura
    do produto usa `predict_board`, que segue `config.CONSTRAINED_DECODING`.

    Com `constrained=True`, a leitura passa pela decodificação sujeita às regras (S-11);
    as confianças reportadas passam a ser as das classes efetivamente escolhidas, então
    uma casa reparada aparece com confiança baixa -- que é a verdade sobre ela.
    """
    expected = (64, len(PIECE_CLASSES))
    if probs.shape != expected:
        raise ValueError(f"Esperada matriz {expected}, recebida {probs.shape}.")

    probs = np.asarray(probs, dtype=np.float64)

    decode = decode_constrained(probs, max_changes=max_changes) if constrained else None
    class_indices = decode.class_indices if decode is not None else [int(idx) for idx in probs.argmax(axis=1)]
    confidences = probs[np.arange(64), class_indices]
    entropy = -(probs * np.log(np.clip(probs, _EPS, None))).sum(axis=1)

    # `stable` garante que casas empatadas saiam em ordem de tabuleiro, e nao arbitraria:
    # a fila de revisao (S-22) fica reproduzivel entre execucoes.
    ordered = np.argsort(confidences, kind="stable")
    uncertain = [int(idx) for idx in ordered if confidences[idx] < uncertain_threshold]

    fen_board = fen_from_class_indices(class_indices)

    return BoardPrediction(
        probs=probs,
        class_indices=class_indices,
        fen_board=fen_board,
        mean_confidence=float(confidences.mean()),
        min_confidence=float(confidences.min()),
        mean_entropy=float(entropy.mean()),
        uncertain_squares=uncertain,
        position=check_position(fen_board),
        decode=decode,
    )


def predict_board(
    board_rgb: np.ndarray,
    model: PieceClassifier,
    device: str,
    *,
    rotate_180: bool = False,
    uncertain_threshold: float = UNCERTAIN_SQUARE_THRESHOLD,
    constrained: bool = CONSTRAINED_DECODING,
) -> BoardPrediction:
    """Reconhece um tabuleiro já recortado e normalizado, preservando as probabilidades."""
    board = cv2.rotate(board_rgb, cv2.ROTATE_180) if rotate_180 else board_rgb

    cells = split_board_into_cells(board)
    batch = torch.stack([preprocess_cell_to_tensor(cell) for cell in cells], dim=0).to(device)

    with torch.inference_mode():
        probs = torch.softmax(model(batch), dim=1)

    return prediction_from_probs(
        probs.cpu().numpy().astype(np.float64),
        uncertain_threshold=uncertain_threshold,
        constrained=constrained,
    )


# `predict_fen_from_board` foi removida junto com o último chamador. Devolvia (FEN, média
# das confianças) -- exatamente o par que a S-10 mostrou ser enganoso, e manter uma porta
# de entrada para ele só convidava a reintroduzir o problema. Use `predict_board`.
