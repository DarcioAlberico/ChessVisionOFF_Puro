"""A ponte entre o `numpy` do pipeline e a imagem do Qt, num lugar só.

O `render_pdf_page` devolve `(H, W, 3)` RGB e o `QImage` quer um buffer contíguo com o passo
de linha declarado. São três linhas, e é justamente por isso que elas têm de morar num lugar:
espalhadas, cada chamada escolheria o seu jeito de lidar com a parte que **não** é óbvia --
que o `QImage` construído sobre um buffer emprestado não copia nada, e morre junto com o
array que o alimentou.
"""

from __future__ import annotations

import cv2
import numpy as np
from PyQt6.QtGui import QImage, QPixmap


def qimage_de_rgb(rgb: np.ndarray) -> QImage:
    """Um `QImage` **próprio** a partir de um array RGB `(H, W, 3)`.

    **Duas cópias, e as duas são necessárias.** O `QImage` construído sobre um buffer não copia
    nada: ele aponta para a memória que recebeu, e o sintoma de deixá-la escapar é uma página
    que aparece rasgada -- ou não aparece -- quando o array numpy é coletado, o que acontece uma
    renderização depois e num lugar que não tem nada a ver com a causa. O `tobytes()` dá um
    buffer que sobrevive à chamada, e o `.copy()` transfere os pixels para memória do próprio
    `QImage`, que é a única que o Qt promete manter viva.

    Uma página a 220 DPI são ~5 MiB, e isto acontece uma vez por virada. É barato; o defeito
    que ele evita não é.
    """
    array = np.ascontiguousarray(rgb[:, :, :3], dtype=np.uint8)
    altura, largura = array.shape[:2]
    return QImage(array.tobytes(), largura, altura, 3 * largura, QImage.Format.Format_RGB888).copy()


def pixmap_de_rgb(rgb: np.ndarray) -> QPixmap:
    """O mesmo, já no formato que o `QPainter` desenha sem reconverter a cada quadro."""
    return QPixmap.fromImage(qimage_de_rgb(rgb))


def reduzir_rgb(rgb: np.ndarray, zoom: float) -> np.ndarray:
    """A página no zoom pedido, como array -- **pelo OpenCV, e não pelo `QImage.scaled`**.

    A razão é o GIL (OCR_UI passo 15). `QImage.scaled` com filtro suave sobre uma página a
    300 DPI custa 24 ms e **segura o interpretador** por 11 ms medidos enquanto roda numa
    thread; `cv2.resize` custa 15 ms e solta o GIL (pior espera da thread da janela: 2,9 ms).
    Como o reescalonamento passou a rodar fora da thread da interface, quem importa não é o
    tempo total e sim quanto dele a janela não consegue usar.

    `INTER_AREA` para reduzir (é o filtro que não deixa moiré nas casas do tabuleiro) e
    `INTER_CUBIC` para ampliar. Devolve o próprio array quando o zoom é 1.
    """
    if zoom == 1.0:
        return rgb
    altura, largura = rgb.shape[:2]
    alvo = (max(1, int(round(largura * zoom))), max(1, int(round(altura * zoom))))
    filtro = cv2.INTER_AREA if zoom < 1.0 else cv2.INTER_CUBIC
    return cv2.resize(np.ascontiguousarray(rgb[:, :, :3]), alvo, interpolation=filtro)
