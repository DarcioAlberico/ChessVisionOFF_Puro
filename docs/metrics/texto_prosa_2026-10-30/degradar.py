"""Degradação sintética de uma página digital para simular escaneamento, sem mexer na geometria.

A geometria fica intacta (sem rotação nem deslocamento) para que a camada editorada continue
sendo referência exata da mesma tinta.
"""
from __future__ import annotations

import cv2
import numpy as np

PERFIS = {
    #            fator  blur  ruido  jpeg  tinta(-1 fina,0,+1 grossa)  manchas
    "leve":   (0.68, 0.6, 6, 60, 0, 0),
    "medio":  (0.50, 0.9, 10, 45, 0, 200),
    "pesado": (0.42, 1.1, 14, 35, 0, 600),
    "fina":   (0.55, 0.8, 8, 45, -1, 100),
    "grossa": (0.55, 0.8, 8, 45, 1, 100),
}


def aplicar(img_rgb: np.ndarray, perfil: str, semente: int = 0) -> np.ndarray:
    fator, blur, ruido, jpeg, tinta, manchas = PERFIS[perfil]
    rng = np.random.default_rng(semente)
    g = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    H, W = g.shape
    if tinta:
        k = np.ones((2, 2), np.uint8)
        g = cv2.dilate(g, k) if tinta < 0 else cv2.erode(g, k)  # fundo branco: dilatar afina a tinta
    p = cv2.resize(g, (int(W * fator), int(H * fator)), interpolation=cv2.INTER_AREA)
    p = cv2.GaussianBlur(p, (0, 0), blur)
    p = p.astype(np.float32) + rng.normal(0, ruido, p.shape)
    if manchas:
        ys = rng.integers(0, p.shape[0], manchas)
        xs = rng.integers(0, p.shape[1], manchas)
        p[ys, xs] = rng.uniform(0, 120, manchas)
    p = np.clip(p, 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", p, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    p = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    g = cv2.resize(p, (W, H), interpolation=cv2.INTER_LINEAR)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2RGB)
