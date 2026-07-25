from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np

PdfSource = str | Path | bytes


def _open_document(pdf_source: PdfSource) -> fitz.Document:
    if isinstance(pdf_source, bytes):
        return fitz.open(stream=pdf_source, filetype="pdf")
    return fitz.open(str(pdf_source))


def get_pdf_page_count(pdf_source: PdfSource) -> int:
    with _open_document(pdf_source) as doc:
        return doc.page_count


def render_pdf_page(pdf_source: PdfSource, page_index: int, dpi: int = 220) -> np.ndarray:
    """Renderiza uma pagina do PDF como array RGB (H, W, 3) proprio e gravavel."""
    with _open_document(pdf_source) as doc:
        if page_index < 0 or page_index >= doc.page_count:
            raise ValueError(f"Pagina {page_index} fora do intervalo (0..{doc.page_count - 1})")

        page = doc[page_index]
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

    # np.frombuffer devolve uma view somente-leitura sobre o buffer do Pixmap.
    # A copia garante um array proprio e gravavel, isolado do ciclo de vida do pix.
    buffer = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    image: np.ndarray = buffer[:, :, :3].copy() if pix.n == 4 else buffer.copy()
    return image
