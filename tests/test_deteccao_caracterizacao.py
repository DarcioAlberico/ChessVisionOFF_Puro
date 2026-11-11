"""Caracterização da detecção (S-859): caixas, motivos de recusa e marcas saem iguais byte a byte.

Gravado com `detect_diagrams`, `_contour_candidates` e `detector_de_marcas.classificar` de antes da
partição em cadeias de filtros; a partição não pode mudar uma caixa nem um motivo. As páginas são as
de `tests/fixtures/` mais sintéticas desenhadas para que cada motivo de `MOTIVOS_DE_RECUSA` e de
`detect_diagrams` apareça ao menos uma vez -- o conjunto de campo não tem `fora-da-pagina`,
`prior-de-tamanho` nem `faixa-da-pagina`.

Para regravar (só quando uma caixa muda **de propósito**):
`python tests/test_deteccao_caracterizacao.py --gravar`.
"""

from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path
from typing import Any

import cv2
import fitz
import numpy as np
from test_board_detection import (
    _board_with_glued_caption,
    _board_with_severed_corner_contacts,
    _page_with_boards_in_two_columns,
    _synthetic_grid,
    _tabuleiro_sintetico,
)
from test_detection import board_image, board_with_caption, pdf_with_images, photo_like, render, tiled_board

from chess_diagram_ocr import board_detection as bd
from chess_diagram_ocr import detector_de_marcas as dm
from chess_diagram_ocr.atomic_io import read_image
from chess_diagram_ocr.config import RecallOptions
from chess_diagram_ocr.detection import hybrid

ESPERADO = Path(__file__).parent / "fixtures" / "deteccao_caracterizacao.json"
FIXTURES = Path(__file__).parent / "fixtures"


def _recusas(lista: list[bd.RejectedQuad]) -> list[list[object]]:
    return [[list(r.bbox), r.score, r.checker, r.reason] for r in lista]


def _fora_da_pagina(centro: tuple[float, float], lados: tuple[float, float], giro: float) -> np.ndarray:
    """Um retângulo girado que encosta na borda: o `minAreaRect` dele sai da página."""
    imagem = np.full((600, 600, 3), 255, np.uint8)
    cv2.fillPoly(imagem, [cv2.boxPoints((centro, lados, giro)).astype(np.int32)], (40, 40, 40))
    return imagem


def _png(caminho: Path) -> np.ndarray:
    imagem = read_image(caminho)
    if imagem is None:
        raise FileNotFoundError(caminho)
    return cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)


def _paginas_de_contorno() -> dict[str, np.ndarray]:
    paginas = {png.name: _png(png) for png in sorted(FIXTURES.glob("*.png"))}
    paginas.update(
        grade=_synthetic_grid(3, 3),
        duas_colunas=_page_with_boards_in_two_columns(),
        quinas=_board_with_severed_corner_contacts(),
        legenda=_board_with_glued_caption(),
        filete=_tabuleiro_sintetico(filete=12),
        foto=photo_like(),
        fora_a=_fora_da_pagina((108.24, 21.14), (266.78, 161.35), 45.93),
        fora_b=_fora_da_pagina((2.78, 81.99), (162.53, 174.81), 49.11),
    )
    return paginas


def _contorno() -> dict[str, object]:
    saida: dict[str, object] = {}
    for nome, imagem in _paginas_de_contorno().items():
        variantes: dict[str, dict[str, Any]] = {
            "padrao": {},
            "cru": {"recall": None, "reading_order": "row", "max_boards": 2, "warn_on_cap": False},
            "sem_piso": {"checker_floor": None},
        }
        for variante, opcoes in variantes.items():
            recusas: list[bd.RejectedQuad] = []
            achados = bd.detect_boards(imagem, rejected=recusas, **opcoes)
            caixas = [list(bd._bbox_from_quad(quad)) for _, quad in achados if quad is not None]
            saida[f"{nome}/{variante}"] = {"caixas": caixas, "recusas": _recusas(recusas)}
    return saida


def _faixa() -> np.ndarray:
    """Imagem embutida larga com um tabuleiro pequeno dentro e linhas de texto: a faixa da S-176."""
    faixa = np.full((600, 680, 3), 255, np.uint8)
    faixa[200:400, 40:240] = board_image(200, frame=True)
    for y in range(40, 580, 30):
        cv2.line(faixa, (300, y), (650, y), (0, 0, 0), 6)
    return faixa


def _paginas_hibridas() -> dict[str, tuple[fitz.Page, np.ndarray]]:
    pdfs = {
        "embutido": [(board_image(), fitz.Rect(72, 72, 272, 272))],
        "embutido_e_foto": [(board_image(), fitz.Rect(72, 72, 272, 272)), (photo_like(), fitz.Rect(300, 400, 500, 600))],
        "ladrilhos": [
            (ladrilho, fitz.Rect(72 + c * 100, 72 + li * 100, 172 + c * 100, 172 + li * 100))
            for ladrilho, (li, c) in tiled_board(side=320)
        ],
        "com_legenda": [(board_with_caption(), fitz.Rect(100, 100, 300, 337))],
        "faixa": [(_faixa(), fitz.Rect(60, 60, 400, 360)), (board_image(320, frame=True), fitz.Rect(100, 450, 300, 650))],
        "prior": [(board_image(320, frame=True), fitz.Rect(72, 72, 272, 272))],
    }
    paginas = {}
    for nome, colocacoes in pdfs.items():
        pagina = pdf_with_images(colocacoes)[0]
        paginas[nome] = (pagina, render(pagina))
    # Um tabuleiro de ~90 pt só nos pixels, numa página que declara um de 200 pt.
    pequeno = board_image(272, frame=True, border=12)
    paginas["prior"][1][1500 : 1500 + pequeno.shape[0], 900 : 900 + pequeno.shape[1]] = pequeno
    return paginas


def _hibrido() -> dict[str, object]:
    saida: dict[str, object] = {}
    for nome, (pagina, imagem) in _paginas_hibridas().items():
        variantes: dict[str, dict[str, Any]] = {
            "padrao": {},
            "cru": {
                "max_boards": 2, "reading_order": "row", "refine_embedded": False,
                "size_prior_tolerance": None, "band_board_fill": None, "recall": None,
            },
            "sem_piso": {"checker_contrast_floor": None, "max_boards": 3},
            "faixa": {"recall": RecallOptions(embedded_floor=None), "reading_order": "row"},
        }
        for variante, opcoes in variantes.items():
            recusas: list[bd.RejectedQuad] = []
            achados = hybrid.detect_diagrams(pagina, imagem, rejected=recusas, **opcoes)
            saida[f"{nome}/{variante}"] = {
                "candidatos": [
                    [[round(v, 3) for v in c.bbox_pdf], c.source, c.detector_score, c.trimmed, c.merged_tiles]
                    for c in achados
                ],
                "recusas": _recusas(recusas),
            }
    return saida


_LIMIARES = {
    "lado": [0.0, 0.1, 0.14, 0.1399999, 0.175, 0.2, 0.3, 0.5, 0.72, 0.7200001, 0.9],
    "desvio": [-0.2, -0.18, -0.1800001, -0.1000001, 0.0, 0.05, 0.1, 0.1000001, 0.18, 0.1800001],
    "solidez": [0.4, 0.55, 0.5499999, 0.6, 0.72, 0.7199999, 0.8, 0.85, 0.8500001, 0.9, 0.8999999, 1.0],
    "circularidade": [0.5, 0.72, 0.7199999, 0.8, 0.85, 0.8499999, 0.95],
    "harmonico_5": [0.0, 0.1, 0.13, 0.1299999, 0.2],
    "variacao": [0.0, 5.0, 12.0, 12.000001, 39.0],
    "diagonais": [0.5, 0.75, 0.7499999, 0.9],
    "eixos": [0.4, 0.53, 0.5300001, 0.55, 0.5499999, 0.62, 0.6199999, 0.85, 0.8499999, 0.95],
    "menor": [0.2, 0.4, 0.3999999, 0.5],
    "outras": [0.0, 0.1, 0.25, 0.2500001, 0.4],
}


def _medidas_sorteadas(quantas: int = 6000) -> list[dm.MedidasDaCasa]:
    """Medidas em cima dos limiares (metade) e dentro da região em que as marcas moram (metade)."""
    sorteio = random.Random(859)

    def em_cima(chave: str) -> float:
        return sorteio.choice(_LIMIARES[chave])

    medidas = []
    for indice in range(quantas):
        if indice % 2:
            lado = sorteio.uniform(0.12, 0.75)
            largura, altura = lado, lado * sorteio.uniform(0.8, 1.3)
            numeros = {
                "desvio_x": sorteio.uniform(-0.2, 0.2), "desvio_y": sorteio.uniform(-0.12, 0.12),
                "area": lado * lado * sorteio.uniform(0.5, 0.9), "solidez": sorteio.uniform(0.5, 1.0),
                "circularidade": sorteio.uniform(0.65, 1.0), "harmonico_5": sorteio.uniform(0.0, 0.25),
                "variacao_do_miolo": sorteio.uniform(0.0, 20.0),
                "tinta_nas_diagonais": sorteio.uniform(0.6, 1.0), "tinta_nos_eixos": sorteio.uniform(0.4, 1.0),
                "menor_diagonal": sorteio.uniform(0.3, 0.6), "menor_eixo": sorteio.uniform(0.3, 0.6),
                "outras_manchas": sorteio.uniform(0.0, 0.3),
            }
        else:
            largura, altura = em_cima("lado"), em_cima("lado")
            numeros = {
                "desvio_x": em_cima("desvio"), "desvio_y": em_cima("desvio"), "area": largura * altura * 0.7,
                "solidez": em_cima("solidez"), "circularidade": em_cima("circularidade"),
                "harmonico_5": em_cima("harmonico_5"), "variacao_do_miolo": em_cima("variacao"),
                "tinta_nas_diagonais": em_cima("diagonais"), "tinta_nos_eixos": em_cima("eixos"),
                "menor_diagonal": em_cima("menor"), "menor_eixo": em_cima("menor"), "outras_manchas": em_cima("outras"),
            }
        medidas.append(
            dm.MedidasDaCasa(
                largura=largura, altura=altura, miolo_claro=sorteio.random() < 0.5,
                centro_escuro=sorteio.random() < 0.6, toca_a_borda=sorteio.random() < 0.15, **numeros,
            )
        )
    return medidas


_LETRA = {None: ".", "x": "x", "cruz": "+", "estrela-preta": "E", "estrela-branca": "e",
          "bolinha-preta": "O", "bolinha-branca": "o"}


def _marcas() -> list[str]:
    """O tipo de cada medida sorteada, uma letra por medida e cem por linha."""
    letras = "".join(_LETRA[dm.classificar(medidas)] for medidas in _medidas_sorteadas())
    return [letras[inicio : inicio + 100] for inicio in range(0, len(letras), 100)]


def caracterizacao() -> str:
    dados = {"contorno": _contorno(), "hibrido": _hibrido(), "marcas": _marcas()}
    return json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


class CaracterizacaoDaDeteccaoTests(unittest.TestCase):
    def test_caixas_recusas_e_marcas_saem_iguais_byte_a_byte(self) -> None:
        texto = caracterizacao()
        esperado, agora = json.loads(ESPERADO.read_bytes().decode("utf-8")), json.loads(texto)
        for parte in ("contorno", "hibrido"):
            for chave, valor in esperado[parte].items():
                with self.subTest(parte=parte, pagina=chave):
                    self.assertEqual(agora[parte][chave], valor)
        self.assertEqual(agora["marcas"], esperado["marcas"])
        self.assertEqual(texto, ESPERADO.read_bytes().decode("utf-8"))

    def test_todo_motivo_de_recusa_aparece_na_caracterizacao(self) -> None:
        """Uma caracterização que não passa por um filtro não protege a partição dele."""
        esperado = json.loads(ESPERADO.read_bytes().decode("utf-8"))
        motivos = {
            recusa[3]
            for parte in ("contorno", "hibrido")
            for pagina in esperado[parte].values()
            for recusa in pagina["recusas"]
        }
        dos_filtros = set(bd.MOTIVOS_DE_RECUSA) | {
            "perdeu-para-embutido", "prior-de-tamanho", "faixa-da-pagina", "teto-da-pagina",
        }
        self.assertEqual(motivos, dos_filtros)
        self.assertEqual(set("".join(esperado["marcas"])), set(_LETRA.values()))


if __name__ == "__main__":
    if "--gravar" in sys.argv:
        ESPERADO.write_bytes(caracterizacao().encode("utf-8"))
        print(f"gravado {ESPERADO}")
    else:
        unittest.main()
