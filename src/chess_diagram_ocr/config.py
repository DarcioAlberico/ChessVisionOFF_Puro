from pathlib import Path

PIECE_CLASSES = [
    "empty",
    "P",
    "N",
    "B",
    "R",
    "Q",
    "K",
    "p",
    "n",
    "b",
    "r",
    "q",
    "k",
]

PIECE_TO_IDX = {name: idx for idx, name in enumerate(PIECE_CLASSES)}
IDX_TO_CLASS = {idx: name for name, idx in PIECE_TO_IDX.items()}

BOARD_SIZE = 800
CELL_SIZE = BOARD_SIZE // 8
MODEL_IMAGE_SIZE = 64

# Abaixo disso a casa entra em `BoardPrediction.uncertain_squares` (S-10). O valor e alto
# de proposito: o modelo e confiante ate quando erra (media ~0,80 nas casas erradas contra
# ~0,999 nas certas), entao um limiar baixo nao separaria nada.
UNCERTAIN_SQUARE_THRESHOLD = 0.90

# Decodificacao sujeita as regras do xadrez (S-11) em vez de argmax por casa.
# O efeito medido esta em docs/BASELINE.md; ligado por padrao porque o argmax nao tem
# nenhuma obrigacao de produzir posicao legal.
CONSTRAINED_DECODING = True

# Teto de casas que o reparo pode reescrever. Alto demais e o decodificador "conserta"
# uma leitura ruim inventando uma posicao legal e errada -- pior que admitir a falha.
MAX_DECODE_CHANGES = 6

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_CSV = PROJECT_ROOT / "data" / "labels.csv"
DEFAULT_SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "piece_classifier.pt"
DEFAULT_PDF_DIR = PROJECT_ROOT / "PDF"


def find_default_pdf_path() -> Path | None:
    if not DEFAULT_PDF_DIR.exists():
        return None

    pdfs = sorted(path for path in DEFAULT_PDF_DIR.glob("*.pdf") if path.is_file())
    return pdfs[0] if pdfs else None
