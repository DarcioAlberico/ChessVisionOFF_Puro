"""Texto claro sobre faixa preta (S-527): a faixa achada, virada, e as iscas deixadas em paz.

**As páginas são desenhadas aqui, não são de livro.** O cabeçalho é escrito em branco sobre um
retângulo preto e, na página de referência, o mesmo cabeçalho em preto sobre papel: o que a
inversão produz dentro da faixa é medido contra tinta que este arquivo desenhou. A franja do
scanner é uma tira de textura aleatória colada na borda de cima, como na folha 19 do Yusupov.
"""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from chess_diagram_ocr.text import leitor
from chess_diagram_ocr.text.faixas import (
    FAIXA_FRANJA,
    FAIXA_INVERTER,
    achar_faixas,
    desinverter_faixas,
)

DPI = 300
LARGURA, ALTURA = 1700, 1150
CAIXA = (300, 150, 1300, 210)
"""Onde a faixa é desenhada: `x1, y1, x2, y2`, exclusivos."""
LINHAS_DE_FRANJA = 6
TEXTO = "E.Jackson - D.Baird"


def _pagina(*, faixa: bool = True, franja: bool = True, iscas: bool = True, semente: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """`(pagina, referencia)`. Com `faixa=False` o cabeçalho sai em preto nas duas."""
    base = np.full((ALTURA, LARGURA), 255, dtype=np.uint8)
    for linha in range(10):
        cv2.putText(base, "texto corrido de exemplo para a folha", (320, 320 + linha * 60), 0, 1.2, 0, 2, cv2.LINE_AA)
    x1, y1, x2, y2 = CAIXA

    def desenhar(img: np.ndarray, *, reversa: bool) -> None:
        if reversa:
            cv2.rectangle(img, (x1, y1), (x2 - 1, y2 - 1), 0, -1)
        (tw, th), _ = cv2.getTextSize(TEXTO, 0, 1.3, 2)
        tx = (x1 + x2 - tw) // 2
        ty = (y1 + y2 + th) // 2
        cv2.putText(img, TEXTO, (tx, ty), 0, 1.3, 255 if reversa else 0, 2, cv2.LINE_AA)
        if iscas:
            cv2.putText(img, "Solutions", (640, 90), 0, 2.4, 0, 5, cv2.LINE_AA)
            cv2.rectangle(img, (100, 260), (1600, 263), 0, -1)
            lado = 50
            for fila in range(8):
                for coluna in range(8):
                    if (fila + coluna) % 2:
                        cx, cy = 1250 + coluna * lado, 700 + fila * lado
                        cv2.rectangle(img, (cx, cy), (cx + lado - 1, cy + lado - 1), 0, -1)
            cv2.rectangle(img, (1250, 700), (1250 + 8 * lado - 1, 700 + 8 * lado - 1), 0, 2)

    pagina = base.copy()
    referencia = base.copy()
    desenhar(pagina, reversa=faixa)
    desenhar(referencia, reversa=False)
    if faixa and franja:
        rng = np.random.default_rng(semente)
        tira = pagina[y1 - LINHAS_DE_FRANJA:y1, x1:x2]
        tira[rng.random(tira.shape) < 0.6] = 0
    return pagina, referencia


def _tinta(img: np.ndarray) -> np.ndarray:
    return img < 128


def _f1(achada: np.ndarray, verdade: np.ndarray) -> float:
    vp = float(np.count_nonzero(achada & verdade))
    fp = float(np.count_nonzero(achada & ~verdade))
    fn = float(np.count_nonzero(~achada & verdade))
    if vp == 0.0:
        return 0.0
    precisao, cobertura = vp / (vp + fp), vp / (vp + fn)
    return 2.0 * precisao * cobertura / (precisao + cobertura)


class AcharFaixasTests(unittest.TestCase):
    def test_a_faixa_e_achada_onde_foi_desenhada(self) -> None:
        pagina, _ = _pagina()
        faixas, mascara = achar_faixas(pagina, DPI)
        self.assertEqual(1, len(faixas), [f.como_tupla() for f in faixas])
        x1, y1, x2, y2 = CAIXA
        achada = faixas[0]
        # O núcleo é a faixa menos 0,012 pol de cada ponta (4 px a 300 dpi): as linhas de
        # franja em cima não entram, e a entrelinha da faixa perde só a borda.
        self.assertLessEqual(max(abs(achada.x1 - x1), abs(achada.x2 - x2)), 5, achada)
        self.assertLessEqual(max(abs(achada.y1 - y1), abs(achada.y2 - y2)), 5, achada)
        self.assertGreaterEqual(achada.y1, y1)
        self.assertLessEqual(achada.y2, y2)
        self.assertGreaterEqual(achada.x1, x1)
        self.assertLessEqual(achada.x2, x2)
        self.assertGreater(achada.fracao_escura, 0.55)
        dentro = mascara[achada.y1:achada.y2, achada.x1:achada.x2]
        self.assertGreater((dentro == FAIXA_INVERTER).mean(), 0.98)
        franja = mascara[y1 - LINHAS_DE_FRANJA:y1, x1:x2]
        self.assertTrue((franja == FAIXA_FRANJA).any())
        self.assertFalse((franja == FAIXA_INVERTER).any())

    def test_titulo_filete_e_diagrama_nao_sao_faixa(self) -> None:
        pagina, _ = _pagina(faixa=False)
        faixas, _ = achar_faixas(pagina, DPI)
        self.assertEqual([], faixas, [f.como_tupla() for f in faixas])

    def test_a_regua_e_fisica_e_nao_em_pixels(self) -> None:
        """Metade da resolução a metade do DPI: a mesma faixa, uma só."""
        pagina, _ = _pagina()
        pequena = cv2.resize(pagina, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        faixas, _ = achar_faixas(pequena, DPI // 2)
        self.assertEqual(1, len(faixas), [f.como_tupla() for f in faixas])
        self.assertLessEqual(max(abs(faixas[0].x1 - CAIXA[0] // 2), abs(faixas[0].y1 - CAIXA[1] // 2)), 3, faixas[0])

    def test_imagem_vazia_e_pagina_em_branco_nao_estouram(self) -> None:
        self.assertEqual(([], ), (achar_faixas(np.zeros((0, 0), dtype=np.uint8), DPI)[0],))
        branca = np.full((200, 400), 255, dtype=np.uint8)
        self.assertEqual([], achar_faixas(branca, DPI)[0])
        saida, faixas = desinverter_faixas(branca, DPI)
        self.assertIs(saida, branca)
        self.assertEqual([], faixas)


class DesinverterFaixasTests(unittest.TestCase):
    def test_o_cabecalho_virado_e_o_cabecalho_em_preto_da_referencia(self) -> None:
        pagina, referencia = _pagina()
        saida, faixas = desinverter_faixas(pagina, DPI)
        self.assertEqual(1, len(faixas))
        f = faixas[0]
        f1 = _f1(_tinta(saida[f.y1:f.y2, f.x1:f.x2]), _tinta(referencia[f.y1:f.y2, f.x1:f.x2]))
        self.assertGreater(f1, 0.95, f"F1 da tinta do cabeçalho virado: {f1:.3f}")

    def test_fora_da_faixa_nenhum_pixel_muda(self) -> None:
        """O texto corrido, o título, o filete e o diagrama saem idênticos ao que entraram."""
        pagina, _ = _pagina()
        saida, _ = desinverter_faixas(pagina, DPI)
        x1, y1, x2, y2 = CAIXA
        intacto = np.ones(pagina.shape, dtype=bool)
        intacto[y1 - LINHAS_DE_FRANJA - 3:y2 + 3, x1 - 3:x2 + 3] = False
        self.assertTrue(np.array_equal(saida[intacto], pagina[intacto]))

    def test_a_franja_do_scanner_e_apagada(self) -> None:
        pagina, _ = _pagina()
        saida, _ = desinverter_faixas(pagina, DPI)
        x1, y1, x2, _ = CAIXA
        antes = pagina[y1 - LINHAS_DE_FRANJA:y1, x1:x2]
        depois = saida[y1 - LINHAS_DE_FRANJA:y1, x1:x2]
        self.assertGreater((antes == 0).mean(), 0.4, "a franja de teste não foi desenhada")
        self.assertTrue((depois == 255).all(), "a franja sobreviveu como ruído")


class SegmentarComDpiTests(unittest.TestCase):
    """O que a S-527 muda no leitor: as letras da faixa viram caixas de caractere."""

    def _caixas_na_faixa(self, dpi: int | None) -> int:
        pagina, _ = _pagina()
        rgb = cv2.cvtColor(pagina, cv2.COLOR_GRAY2RGB)
        _, _, _, caixas, _ = leitor.segmentar(rgb, dpi=dpi)
        x1, y1, x2, y2 = CAIXA
        return sum(
            1 for c in caixas
            if x1 <= c.x1 and c.x2 <= x2 and y1 - 2 <= c.y1 and c.y2 <= y2 + 2
            and (c.y2 - c.y1) < (y2 - y1) * 0.8
        )

    def test_sem_dpi_a_faixa_nao_rende_caractere_nenhum(self) -> None:
        self.assertEqual(0, self._caixas_na_faixa(None))

    def test_com_dpi_as_letras_do_cabecalho_sao_caixas(self) -> None:
        self.assertGreaterEqual(self._caixas_na_faixa(DPI), 12)


if __name__ == "__main__":
    unittest.main()
