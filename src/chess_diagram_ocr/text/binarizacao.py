"""Separar tinta de papel numa página escaneada (S-184).

**Este projeto já binariza, e para outra coisa.** `preprocess.py` trata do recorte de uma casa
de tabuleiro: pequeno, quadrado, alto contraste, e sempre a mesma geometria. Página inteira é
outro problema -- ela tem sombra de encadernação, iluminação irregular e uma faixa de tons que
varia dentro dela.

**A decisão que este módulo carrega, e ela custou uma versão inteira lá: o modo `auto` avalia o
resultado, e não o histograma.** A primeira tentativa testava bimodalidade e errava justamente
no caso que interessa. Numa página com sombra de encadernação, o Otsu separa "metade escura" de
"metade clara" -- duas classes perfeitamente bimodais -- e devolve ~47% de tinta, o que não
segmenta nada. Medido nesse cenário, a fração de tinta que cada método produz:

    limiar fixo   61%
    Otsu          48%
    adaptativo     3%

Só o terceiro tem cara de texto, e o critério que o escolhe é olhar o número, não a forma da
distribuição de onde ele veio.

**A polaridade é contrato, não gosto: tinta em branco (255), fundo em preto.** É o que
`cv2.findContours` espera, e é o que a S-185 e a S-187 consomem. Trocá-la depois quebra tudo o
que vem em cima em silêncio -- por isso há teste travando.
"""

from __future__ import annotations

import cv2
import numpy as np

METODOS = ("auto", "otsu", "adaptive", "fixed")

TINTA_PLAUSIVEL = (0.0005, 0.35)
"""Fração de pixels de tinta que uma página de texto pode plausivelmente ter.

Texto corrido fica em torno de 3%-15%; acima de 35% não é texto, é mancha. O piso existe para o
outro extremo -- uma página em branco binarizada com sucesso também não é texto."""

LIMIAR_FIXO_PADRAO = 180
"""O comportamento antigo do projeto de origem, mantido só para comparação."""


def _cinza(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img


def fracao_de_tinta(img_bin: np.ndarray) -> float:
    """Quanto da imagem binarizada é tinta. Espera a polaridade deste módulo."""
    return float((img_bin > 0).mean()) if img_bin.size else 0.0


def tinta_plausivel(img_bin: np.ndarray) -> bool:
    """O resultado da binarização parece texto? Ver o cabeçalho: avalia o **resultado**."""
    return TINTA_PLAUSIVEL[0] <= fracao_de_tinta(img_bin) <= TINTA_PLAUSIVEL[1]


def binarize(img: np.ndarray, method: str = "auto", fixed_threshold: int = LIMIAR_FIXO_PADRAO) -> np.ndarray:
    """Binariza deixando a **tinta em branco (255)** e o fundo em preto.

    ``auto``      Otsu se o que sair parecer texto, senão adaptativo
    ``otsu``      sempre Otsu
    ``adaptive``  limiar adaptativo gaussiano (iluminação irregular)
    ``fixed``     limiar fixo, para comparação
    """
    if method not in METODOS:
        raise ValueError(f"método inválido: {method!r} (use um de {METODOS})")

    cinza = _cinza(img)
    if cinza.size == 0:
        return cinza.copy()

    if method == "auto":
        _, otsu = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        if tinta_plausivel(otsu):
            return otsu
        method = "adaptive"

    if method == "otsu":
        _, saida = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return saida

    if method == "adaptive":
        # Janela ímpar e proporcional à página: pequena demais recorta o miolo dos glifos,
        # grande demais volta a se comportar como limiar global.
        lado = max(15, (min(cinza.shape[:2]) // 20) | 1)
        return cv2.adaptiveThreshold(cinza, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, lado, 10)

    _, saida = cv2.threshold(cinza, fixed_threshold, 255, cv2.THRESH_BINARY_INV)
    return saida


def metodo_escolhido(img: np.ndarray) -> str:
    """Qual método o `auto` escolheria. Existe para a medição e para o diagnóstico.

    Sem isto, "o `auto` está fazendo a coisa certa nesta página?" só se responde comparando
    saídas pixel a pixel -- e a resposta que interessa é o nome do ramo.
    """
    cinza = _cinza(img)
    if cinza.size == 0:
        return "otsu"
    _, otsu = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return "otsu" if tinta_plausivel(otsu) else "adaptive"


__all__ = [
    "LIMIAR_FIXO_PADRAO",
    "METODOS",
    "TINTA_PLAUSIVEL",
    "binarize",
    "fracao_de_tinta",
    "metodo_escolhido",
    "tinta_plausivel",
]
