from pathlib import Path
from typing import Optional

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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_CSV = PROJECT_ROOT / "data" / "labels.csv"
DEFAULT_SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "piece_classifier.pt"
DEFAULT_PDF_DIR = PROJECT_ROOT / "PDF"


def find_default_pdf_path() -> Optional[Path]:
    if not DEFAULT_PDF_DIR.exists():
        return None

    pdfs = sorted(path for path in DEFAULT_PDF_DIR.glob("*.pdf") if path.is_file())
    return pdfs[0] if pdfs else None
