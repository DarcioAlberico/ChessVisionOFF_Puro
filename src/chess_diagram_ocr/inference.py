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
    DEFAULT_ORIENTATION_MODE,
    MAX_DECODE_CHANGES,
    ORIENTATION_DECISIVE_MARGIN,
    ORIENTATION_PAWN_PRIOR_MARGIN,
    PIECE_CLASSES,
    UNCERTAIN_SQUARE_THRESHOLD,
    OrientationMode,
)
from .decode import DecodeResult, decode_constrained
from .fen_utils import (
    PositionCheck,
    check_position,
    fen_from_class_indices,
    pawn_direction_score,
    square_name,
)
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


@dataclass(frozen=True, eq=False)
class OrientedPrediction:
    """Leitura de um diagrama junto com a orientação escolhida para ela (S-13)."""

    prediction: BoardPrediction
    rotation: int
    """0 ou 180 graus, aplicado à imagem antes de reconhecer."""

    margin: float
    """`min_confidence` da orientação escolhida menos a da descartada.

    Sempre ≥ 0 quando a escolha foi por confiança. É a medida de quão folgada foi."""

    ambiguous: bool
    """A escolha foi apertada, ou os dois sinais discordaram: vale olho humano."""

    reason: str
    """Por que esta orientação venceu, em pt-BR, para a UI e o arquivo de revisão."""

    alternative: BoardPrediction | None = None
    """A leitura descartada. `None` quando a orientação foi imposta, não escolhida."""


def _pawn_prior_gap(upright: BoardPrediction, flipped: BoardPrediction) -> float | None:
    """Quanto o prior de peões prefere a leitura de pé. `None` se ele não se aplica."""
    score_upright = pawn_direction_score(upright.class_indices)
    score_flipped = pawn_direction_score(flipped.class_indices)
    if score_upright is None and score_flipped is None:
        return None
    # Uma leitura sem peão de alguma cor não pontua; tratá-la como 0 é justo, porque o outro
    # lado é que está afirmando algo sobre a estrutura.
    return (score_upright or 0.0) - (score_flipped or 0.0)


def predict_with_orientation(
    board_rgb: np.ndarray,
    model: PieceClassifier,
    device: str,
    *,
    mode: OrientationMode = DEFAULT_ORIENTATION_MODE,
    uncertain_threshold: float = UNCERTAIN_SQUARE_THRESHOLD,
    constrained: bool = CONSTRAINED_DECODING,
    decisive_margin: float = ORIENTATION_DECISIVE_MARGIN,
    pawn_prior_margin: float = ORIENTATION_PAWN_PRIOR_MARGIN,
) -> OrientedPrediction:
    """Reconhece o diagrama decidindo a orientação por diagrama, não por checkbox global.

    Com `mode="auto"` tenta 0° e 180° e escolhe a leitura mais plausível. A ordem dos
    critérios vem de medição no split de teste (320 tabuleiros), não da intuição:

    | sinal              | acerta | erra | empata |
    |--------------------|--------|------|--------|
    | legalidade         |     52 |    0 |    268 |
    | `min_confidence`   |    320 |    0 |      0 |
    | peões nas filas    |    264 |    9 |     47 |
    | reis nas filas     |    267 |   37 |     16 |

    A legalidade **não** serve como critério dominante, ao contrário do que a S-13 supôs:
    girar a posição 180° manda peão branco da fila `r` para a fila `9-r`, e 2..7 vira 7..2 --
    continua legal. Ela só decide em 16% dos casos, embora nunca erre, então fica como
    primeiro filtro. O prior de **reis** que a S-13 sugeria erra 37 vezes em 320 e ficou fora.

    A tabela acima, porém, só descreve leitura boa. Medido depois no `1937 Kemeri.pdf`, a
    confiança **para de decidir** quando a leitura é ruim: em duas páginas cuja leitura de pé
    era claramente correta, as duas orientações saíram com confiança ~0,04 e margens de 0,001
    e 0,019 -- ruído, e seguir a margem girava o diagrama errado. O prior de peões, que olha a
    estrutura da posição e não a aparência das peças, continuava informativo nos mesmos casos
    (+3,8 contra -4,2). Daí a regra por regime:

    1. Uma orientação ilegal e a outra não → a legal.
    2. Margem de confiança ≥ `decisive_margin` → a mais confiante.
    3. Senão, peões decidem por ≥ `pawn_prior_margin` filas → a que eles apontam.
    4. Senão → a mais confiante, marcada `ambiguous`.

    Atenção ao que isto **não** resolve: diagrama impresso do ponto de vista das pretas. Ali
    as peças estão desenhadas para cima, e o que muda é o mapeamento casa→índice, não os
    pixels. Girar a imagem estragaria a leitura. Ver a pendência da S-13 no ROADMAP.
    """
    if mode not in ("auto", "0", "180"):
        raise ValueError(f"mode deve ser 'auto', '0' ou '180'; recebido {mode!r}.")

    def read(rotate: bool) -> BoardPrediction:
        return predict_board(
            board_rgb,
            model,
            device,
            rotate_180=rotate,
            uncertain_threshold=uncertain_threshold,
            constrained=constrained,
        )

    if mode != "auto":
        rotation = 180 if mode == "180" else 0
        return OrientedPrediction(
            prediction=read(rotation == 180),
            rotation=rotation,
            margin=0.0,
            ambiguous=False,
            reason=f"orientação imposta ({rotation}°)",
        )

    upright, flipped = read(False), read(True)
    margin = upright.min_confidence - flipped.min_confidence

    # A legalidade entra primeiro porque, quando decide, nunca errou -- e uma leitura ilegal
    # é pior que uma de confiança baixa. Quando as duas são legais (84% dos casos) ela cala.
    legal_upright = not upright.position.is_fatal
    legal_flipped = not flipped.position.is_fatal

    if legal_upright != legal_flipped:
        chose_upright = legal_upright
        # Discordância entre sinais nunca apareceu na medição, mas se aparecer é exatamente
        # o que "ambíguo" quer dizer -- e não algo para resolver em silêncio.
        ambiguous = (margin > 0) != chose_upright
        reason = "única orientação legal"
    elif abs(margin) >= decisive_margin:
        chose_upright = margin > 0
        ambiguous = False
        reason = f"maior confiança mínima (margem {abs(margin):.3f})"
    else:
        # Regime de leitura ruim: as duas orientações saem com confiança igualmente baixa e a
        # margem é ruído. Aqui quem sabe algo é a estrutura da posição.
        pawn_gap = _pawn_prior_gap(upright, flipped)
        if pawn_gap is not None and abs(pawn_gap) >= pawn_prior_margin:
            chose_upright = pawn_gap > 0
            ambiguous = False
            reason = f"peões apontam a orientação (vantagem {abs(pawn_gap):.1f} filas, confiança empatada)"
        else:
            chose_upright = margin >= 0
            ambiguous = True
            reason = (
                f"margem apertada ({abs(margin):.3f}) e peões não decidem"
                if pawn_gap is not None
                else f"margem apertada ({abs(margin):.3f}) e sem peões dos dois lados"
            )

    chosen, discarded = (upright, flipped) if chose_upright else (flipped, upright)
    return OrientedPrediction(
        prediction=chosen,
        rotation=0 if chose_upright else 180,
        margin=abs(margin),
        ambiguous=ambiguous,
        reason=reason,
        alternative=discarded,
    )


# `predict_fen_from_board` foi removida junto com o último chamador. Devolvia (FEN, média
# das confianças) -- exatamente o par que a S-10 mostrou ser enganoso, e manter uma porta
# de entrada para ele só convidava a reintroduzir o problema. Use `predict_board`.
