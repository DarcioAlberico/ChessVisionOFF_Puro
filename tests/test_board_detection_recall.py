"""As três recuperações de recall dentro do detector (OCR_UI ciclo 2, passo A1).

Vieram de `caissa.vision.detect.recall` (suíte, F3), onde eram *monkeypatch* de duas funções
deste pacote e por isso valiam para a importação da suíte e não para a janela -- e as duas no
mesmo processo se pisavam. Aqui são um parâmetro (`RecallOptions`), ligado por padrão.

As páginas são sintéticas e reproduzem **a forma** de uma falha medida -- a legenda soldada ao
tabuleiro (`Reinfeld`), a casa escura hachurada (`Niemeijer`) --, e cada teste afirma o par: o
detector cru (`recall=None`) não acha, e o padrão acha o tabuleiro onde ele está. Os números de
campo (0,9478 → 0,9913) ficam com `benchmarks/validate_detection.py` da suíte.
"""

from __future__ import annotations

import inspect
import unittest

import cv2
import numpy as np

from chess_diagram_ocr import board_detection as bd
from chess_diagram_ocr.board_detection import SQUARE_MIN_ELONGATION, _score_quad, detect_boards, square_anchors
from chess_diagram_ocr.config import DEFAULT_RECALL, RecallOptions
from chess_diagram_ocr.detection.hybrid import detect_diagrams

CRU = None
SEM_PISO_EMBUTIDO = RecallOptions(embedded_floor=None)


def pagina_com_tabuleiro(
    *,
    lado: int = 320,
    origem: tuple[int, int] = (90, 80),
    pagina: tuple[int, int] = (520, 720),
    legenda: int = 0,
    hachura: int = 0,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Uma página branca com um tabuleiro 8×8 e o defeito pedido.

    `legenda` solda uma barra preta à base do tabuleiro (o número de exercício em negrito do
    `Reinfeld`); `hachura` desenha as casas escuras com traços diagonais (o `Niemeijer`).
    Devolve a página e a caixa verdadeira ``(x, y, w, h)``.
    """
    imagem = np.full((pagina[1], pagina[0], 3), 255, np.uint8)
    x0, y0 = origem
    casa = lado // 8
    for linha in range(8):
        for coluna in range(8):
            if (linha + coluna) % 2 == 0:
                continue
            x, y = x0 + coluna * casa, y0 + linha * casa
            if hachura:
                for desloc in range(0, casa, hachura):
                    cv2.line(imagem, (x, y + desloc), (x + casa - 1 - desloc, y + casa - 1), (50, 50, 50), 1)
                    cv2.line(imagem, (x + desloc, y), (x + casa - 1, y + casa - 1 - desloc), (50, 50, 50), 1)
            else:
                cv2.rectangle(imagem, (x, y), (x + casa - 1, y + casa - 1), (70, 70, 70), -1)
    if legenda:
        cv2.rectangle(imagem, (x0, y0 + lado), (x0 + 90, y0 + lado + legenda), (20, 20, 20), -1)
    return imagem, (x0, y0, lado, lado)


def caixas(imagem: np.ndarray, recall: RecallOptions | None) -> list[tuple[int, int, int, int]]:
    return [bd._bbox_from_quad(quad) for _, quad in detect_boards(imagem, max_boards=6, recall=recall) if quad is not None]


def melhor_iou(achadas: list[tuple[int, int, int, int]], alvo: tuple[int, int, int, int]) -> float:
    return max((bd._bbox_iou(caixa, alvo) for caixa in achadas), default=0.0)


class PadraoLigadoTests(unittest.TestCase):
    def test_o_padrao_das_tres_rotas_e_o_pacote_ligado(self) -> None:
        """A janela e a suíte detectam pela mesma função com o mesmo padrão -- é o ponto do A1."""
        for funcao in (bd._extract_candidate_quads, detect_boards, detect_diagrams):
            with self.subTest(funcao=funcao.__name__):
                self.assertIs(inspect.signature(funcao).parameters["recall"].default, DEFAULT_RECALL)
        self.assertEqual(DEFAULT_RECALL, RecallOptions(scales=(0.5,), rescue_squares=True, embedded_floor=0.0))

    def test_uma_escala_fora_do_intervalo_e_recusada(self) -> None:
        imagem, _ = pagina_com_tabuleiro()
        with self.assertRaisesRegex(ValueError, "escala"):
            detect_boards(imagem, max_boards=4, recall=RecallOptions(scales=(1.5,)))


class UmaReguaSoTests(unittest.TestCase):
    def test_o_score_do_resgate_e_a_conta_do_passe_cru(self) -> None:
        """Um candidato resgatado compete com os do passe cru: tem de ser medido igual."""
        imagem, _ = pagina_com_tabuleiro()
        crus = bd._contour_candidates(imagem)
        self.assertTrue(crus, "a página sintética precisa produzir candidatos")
        area = float(imagem.shape[0] * imagem.shape[1])
        for quad, score, _ in crus:
            medido = _score_quad(imagem, quad, area)
            self.assertIsNotNone(medido)
            self.assertAlmostEqual(medido[0], score, places=9)  # type: ignore[index]

    def test_o_pacote_nunca_perde_o_que_o_cru_achava(self) -> None:
        imagem, alvo = pagina_com_tabuleiro()
        cru = caixas(imagem, CRU)
        empacotado = caixas(imagem, SEM_PISO_EMBUTIDO)
        self.assertGreater(melhor_iou(cru, alvo), 0.9)
        for caixa in cru:
            self.assertGreater(melhor_iou(empacotado, caixa), 0.9, f"o pacote perdeu {caixa}, que o cru achava")


class ResgateDeQuadradoTests(unittest.TestCase):
    def test_square_anchors_sao_o_maior_quadrado_em_tres_posicoes(self) -> None:
        quads = square_anchors((10, 20, 100, 160))
        self.assertEqual(len(quads), 3)
        for quad in quads:
            xs, ys = quad[:, 0], quad[:, 1]
            self.assertAlmostEqual(float(xs.max() - xs.min()), 100.0)
            self.assertAlmostEqual(float(ys.max() - ys.min()), 100.0)
        self.assertEqual(sorted(float(q[:, 1].min()) for q in quads), [20.0, 50.0, 80.0])

    def test_square_anchors_de_uma_caixa_quadrada_sao_a_caixa(self) -> None:
        for quad in square_anchors((5, 7, 64, 64)):
            self.assertEqual(bd._bbox_from_quad(quad), (5, 7, 64, 64))

    def test_a_legenda_soldada_ao_tabuleiro_e_recuperada_como_quadrado(self) -> None:
        """A forma do `Reinfeld`: o contorno emenda tabuleiro e legenda e o contraste lê zero."""
        imagem, alvo = pagina_com_tabuleiro(legenda=90)
        cru = caixas(imagem, CRU)
        self.assertEqual(cru, [], f"o cru deveria falhar nesta página, devolveu {cru}")
        recusados: list[bd.RejectedQuad] = []
        detect_boards(imagem, max_boards=6, rejected=recusados, recall=CRU)
        self.assertIn("sem-contraste-de-casa", {r.reason for r in recusados})
        empacotado = caixas(imagem, SEM_PISO_EMBUTIDO)
        self.assertGreater(melhor_iou(empacotado, alvo), 0.95, f"esperado {alvo}, veio {empacotado}")

    def test_so_o_resgate_ja_recupera_o_reinfeld(self) -> None:
        imagem, alvo = pagina_com_tabuleiro(legenda=90)
        so_resgate = caixas(imagem, RecallOptions(scales=(), rescue_squares=True, embedded_floor=None))
        self.assertGreater(melhor_iou(so_resgate, alvo), 0.95)
        sem_resgate = caixas(imagem, RecallOptions(scales=(), rescue_squares=False, embedded_floor=None))
        self.assertEqual(sem_resgate, [])

    def test_o_resgate_deixa_uma_recusa_ja_quadrada_em_paz(self) -> None:
        """Ruído quadrado sem xadrez continua recusado: o resgate não é segunda chance."""
        rng = np.random.default_rng(20260907)
        imagem = np.full((720, 520, 3), 255, np.uint8)
        ruido = rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)
        imagem[80:380, 90:390] = cv2.GaussianBlur(ruido, (9, 9), 0)
        cv2.rectangle(imagem, (90, 80), (390, 380), (0, 0, 0), 3)
        empacotado = caixas(imagem, SEM_PISO_EMBUTIDO)
        self.assertLess(melhor_iou(empacotado, (90, 80, 300, 300)), 0.5, f"ruído quadrado virou tabuleiro: {empacotado}")

    def test_o_piso_de_alongamento_e_onde_o_resgate_ainda_ganha(self) -> None:
        self.assertGreater(SQUARE_MIN_ELONGATION, 1.0)
        quads = square_anchors((0, 0, 100, int(100 * SQUARE_MIN_ELONGATION)))
        self.assertEqual({bd._bbox_from_quad(q)[3] for q in quads}, {100})


class MultiescalaTests(unittest.TestCase):
    def test_o_tabuleiro_hachurado_e_achado_pelo_passe_a_meia_escala(self) -> None:
        """A forma do `Niemeijer`: casas escuras a traço, que o limiar local vê como cerca."""
        imagem, alvo = pagina_com_tabuleiro(hachura=5)
        self.assertEqual(caixas(imagem, CRU), [], "o cru deveria falhar na página hachurada")
        so_multiescala = caixas(imagem, RecallOptions(rescue_squares=False, embedded_floor=None))
        self.assertGreater(melhor_iou(so_multiescala, alvo), 0.9, f"esperado {alvo}, veio {so_multiescala}")

    def test_desligar_as_escalas_devolve_o_cru(self) -> None:
        imagem, _ = pagina_com_tabuleiro(hachura=5)
        self.assertEqual(caixas(imagem, RecallOptions(scales=(), rescue_squares=False)), [])

    def test_recall_none_e_o_passe_cru_candidato_a_candidato(self) -> None:
        imagem, _ = pagina_com_tabuleiro()
        crus = bd._contour_candidates(imagem)
        via_none = bd._extract_candidate_quads(imagem, recall=None)
        self.assertEqual([c[2] for c in crus], [c[2] for c in via_none])


class PisoDoEmbutidoTests(unittest.TestCase):
    @staticmethod
    def _pdf_com_imagem(imagem_rgb: np.ndarray):  # noqa: ANN205
        import pymupdf

        altura, largura = imagem_rgb.shape[:2]
        doc = pymupdf.open()
        pagina = doc.new_page(width=420.0, height=560.0)
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, largura, altura, np.ascontiguousarray(imagem_rgb).tobytes(), False)
        pagina.insert_image(pymupdf.Rect(60, 60, 60 + largura, 60 + altura), pixmap=pixmap)
        blob = doc.tobytes()
        doc.close()
        return pymupdf.open("pdf", blob)

    @staticmethod
    def _tabuleiro(lado: int = 240) -> np.ndarray:
        imagem = np.full((lado, lado, 3), 250, np.uint8)
        casa = lado // 8
        for linha in range(8):
            for coluna in range(8):
                if (linha + coluna) % 2:
                    cv2.rectangle(
                        imagem,
                        (coluna * casa, linha * casa),
                        ((coluna + 1) * casa - 1, (linha + 1) * casa - 1),
                        (60, 60, 60),
                        -1,
                    )
        return imagem

    def test_o_piso_mantem_o_tabuleiro_e_derruba_a_fotografia(self) -> None:
        """O zero da S-143, aplicado à fonte que nunca o teve; não contradiz a S-12."""
        import pymupdf

        rng = np.random.default_rng(11)
        foto = cv2.GaussianBlur(rng.integers(0, 255, (240, 240, 3), dtype=np.uint8), (11, 11), 0)
        for bitmap, esperado in ((self._tabuleiro(), 1), (foto, 0)):
            doc = self._pdf_com_imagem(bitmap)
            try:
                pagina = doc[0]
                pix = pagina.get_pixmap(matrix=pymupdf.Matrix(220 / 72.0, 220 / 72.0), alpha=False)
                rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()
                sem_piso = [c for c in detect_diagrams(pagina, rgb, recall=SEM_PISO_EMBUTIDO) if c.source == "embedded"]
                self.assertEqual(len(sem_piso), 1)
                com_piso = [c for c in detect_diagrams(pagina, rgb) if c.source == "embedded"]
                self.assertEqual(len(com_piso), esperado)
            finally:
                doc.close()


if __name__ == "__main__":
    unittest.main()
