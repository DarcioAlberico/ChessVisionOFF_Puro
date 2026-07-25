from __future__ import annotations

from pathlib import Path
from typing import Union

import fitz
import numpy as np

PdfSource = Union[str, Path, bytes]


def _open_document(pdf_source: PdfSource) -> fitz.Document:
    if isinstance(pdf_source, bytes):
        return fitz.open(stream=pdf_source, filetype="pdf")
    return fitz.open(str(pdf_source))


def get_pdf_page_count(pdf_source: PdfSource) -> int:
    with _open_document(pdf_source) as doc:
        return doc.page_count


def render_pdf_page(pdf_source: PdfSource, page_index: int, dpi: int = 220) -> np.ndarray:
    with _open_document(pdf_source) as doc:
        if page_index < 0 or page_index >= doc.page_count:
            raise ValueError(f"Page index {page_index} out of range (0..{doc.page_count - 1})")

        page = doc[page_index]
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        image = image[:, :, :3]
    return image
