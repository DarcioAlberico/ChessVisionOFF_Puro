"""Detecção de diagramas na página, por duas fontes independentes (S-12).

`board_detection.py` (contorno) continua sendo a única fonte que funciona em qualquer PDF.
Este pacote acrescenta a fonte que os PDFs já oferecem de graça -- a imagem embutida com
bounding box exato -- para os livros em que ela existe.

Levantamento dos 27 PDFs do acervo, amostrando 12 páginas do meio de cada um:

| o que a página tem | livros | a imagem embutida serve? |
|---|---|---|
| imagem quadrada por diagrama | 10 | sim |
| a página inteira é um scan | 12 | não: uma imagem só, cobrindo tudo |
| diagrama vetorial/fonte | 2 | não: não há imagem |
| misto | 3 | às vezes |

Ou seja: o caminho por contorno **não** é um fallback para casos exóticos, é a maioria do
acervo. Os 10 em que a imagem embutida serve incluem, por outro lado, justamente os mais
difíceis para o contorno (`1937 Kemeri`, `AAGAARD - Practical Chess Defence`, `Schiller`,
`Karpov`) -- e trazem mais resolução: o diagrama do Kemeri é 590×590 nativo contra ~430 px
que o render da página a 220 DPI produz.
"""

from .embedded import DiagramCandidate, candidates_from_embedded_images, trim_to_frame, trim_to_grid
from .hybrid import detect_diagrams, detect_diagrams_in_pdf_page, refine_candidate_with_contour

__all__ = [
    "DiagramCandidate",
    "candidates_from_embedded_images",
    "detect_diagrams",
    "detect_diagrams_in_pdf_page",
    "refine_candidate_with_contour",
    "trim_to_frame",
    "trim_to_grid",
]
