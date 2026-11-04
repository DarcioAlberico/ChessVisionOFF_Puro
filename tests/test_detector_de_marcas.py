"""O detector de marcas pela forma (`detector_de_marcas.py`), sobre tabuleiros desenhados aqui.

Os recortes reais dos livros não entram no repositório, pelo direito autoral. O que ele acerta neles
foi medido em 2026-11-04 fora daqui, e os desenhos abaixo guardam os casos que aquela medição ensinou:
a hachura grudada na marca, o diagrama com tantas estrelas que a mediana vira estrela, o traço de
hachura lido como X e o bispo branco lido como bolinha.
"""

from __future__ import annotations

import math
import unittest

import cv2
import numpy as np

from chess_diagram_ocr import detector_de_marcas as dm
from chess_diagram_ocr import marcas_de_casa as mc

CASA = 100
PRETO = (0, 0, 0)
BRANCO = (255, 255, 255)


def tabuleiro() -> np.ndarray:
    """Casas claras brancas e casas escuras hachuradas a 45°, com a densidade medida nos livros.

    Num recorte real a tinta cobre ~8% da casa hachurada. Um desenho mais denso que isso é outra coisa:
    uma versão com 67% reprovava o detector por um defeito que era só do desenho.
    """
    imagem = np.full((8 * CASA, 8 * CASA, 3), 255, np.uint8)
    for fila in range(8):
        for coluna in range(8):
            if (fila + coluna) % 2:
                casa = imagem[fila * CASA : (fila + 1) * CASA, coluna * CASA : (coluna + 1) * CASA]
                for passo in range(-CASA, CASA, 18):
                    cv2.line(casa, (passo, 0), (passo + CASA, CASA), PRETO, 2, cv2.LINE_AA)
    return imagem


def centro(nome: str) -> tuple[int, int]:
    indice = mc.indice_da_casa(nome)
    return indice % 8 * CASA + CASA // 2, indice // 8 * CASA + CASA // 2


def estrela(imagem: np.ndarray, nome: str, *, cheia: bool = True, raio: int = 32) -> None:
    cx, cy = centro(nome)
    pontos = []
    for passo in range(10):
        angulo = -math.pi / 2 + passo * math.pi / 5
        alcance = raio if passo % 2 == 0 else raio * 0.42
        pontos.append((round(cx + alcance * math.cos(angulo)), round(cy + alcance * math.sin(angulo))))
    forma = np.array(pontos, np.int32)
    cv2.fillPoly(imagem, [forma], PRETO if cheia else BRANCO, cv2.LINE_AA)
    if not cheia:
        cv2.polylines(imagem, [forma], isClosed=True, color=PRETO, thickness=3, lineType=cv2.LINE_AA)


def bolinha(imagem: np.ndarray, nome: str, *, cheia: bool, raio: int = 22) -> None:
    if not cheia:
        # A folga branca em volta é como os livros a imprimem.
        cv2.circle(imagem, centro(nome), raio + 6, BRANCO, -1, cv2.LINE_AA)
    cv2.circle(imagem, centro(nome), raio, PRETO, -1 if cheia else 3, cv2.LINE_AA)


def xis(imagem: np.ndarray, nome: str, *, braco: int = 30) -> None:
    cx, cy = centro(nome)
    cv2.line(imagem, (cx - braco, cy - braco), (cx + braco, cy + braco), PRETO, 9, cv2.LINE_AA)
    cv2.line(imagem, (cx - braco, cy + braco), (cx + braco, cy - braco), PRETO, 9, cv2.LINE_AA)


def cruz(imagem: np.ndarray, nome: str, *, braco: int = 30) -> None:
    cx, cy = centro(nome)
    cv2.line(imagem, (cx - braco, cy), (cx + braco, cy), PRETO, 9, cv2.LINE_AA)
    cv2.line(imagem, (cx, cy - braco), (cx, cy + braco), PRETO, 9, cv2.LINE_AA)


def peca_branca(imagem: np.ndarray, nome: str) -> None:
    """Um bispo de mentira: silhueta quase redonda, contorno preto e riscos por dentro."""
    cx, cy = centro(nome)
    cv2.circle(imagem, (cx, cy), 26, BRANCO, -1, cv2.LINE_AA)
    cv2.circle(imagem, (cx, cy), 26, PRETO, 3, cv2.LINE_AA)
    cv2.line(imagem, (cx - 14, cy), (cx + 14, cy), PRETO, 4, cv2.LINE_AA)
    cv2.line(imagem, (cx, cy - 14), (cx, cy + 14), PRETO, 4, cv2.LINE_AA)


def peca_preta(imagem: np.ndarray, nome: str) -> None:
    """Um rei de mentira: grande, cheio e descendo até a base da casa."""
    cx, cy = centro(nome)
    corpo = np.array([(cx - 30, cy + 42), (cx + 30, cy + 42), (cx + 16, cy - 8), (cx + 28, cy - 34), (cx - 28, cy - 34), (cx - 16, cy - 8)])
    cv2.fillPoly(imagem, [corpo], PRETO, cv2.LINE_AA)


def sugestao(imagem: np.ndarray) -> dict[str, str]:
    return dm.sugerir_marcas(cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)).casas


CASA_CLARA, CASA_HACHURADA = "e4", "d4"


class FormasTests(unittest.TestCase):
    """Cada forma, na casa clara e na hachurada: é a hachura que atrapalha."""

    def conferir(self, desenhar, esperado: str, casas: tuple[str, ...] = (CASA_CLARA, CASA_HACHURADA)) -> None:
        for nome in casas:
            with self.subTest(casa=nome):
                imagem = tabuleiro()
                desenhar(imagem, nome)
                self.assertEqual(sugestao(imagem), {nome: esperado})

    def test_estrela_preta(self) -> None:
        self.conferir(estrela, mc.ESTRELA_PRETA)

    def test_estrela_branca(self) -> None:
        self.conferir(lambda imagem, nome: estrela(imagem, nome, cheia=False), mc.ESTRELA_BRANCA)

    def test_bolinha_preta(self) -> None:
        self.conferir(lambda imagem, nome: bolinha(imagem, nome, cheia=True), mc.BOLINHA_PRETA)

    def test_bolinha_oca_na_casa_clara(self) -> None:
        """Na hachurada, ela passa nas imagens reais de hachura clara (14 de 14 na medição), mas não num
        desenho de alto contraste. Não há exemplo real desse caso, e a regra não foi ajustada por um desenho."""
        self.conferir(lambda imagem, nome: bolinha(imagem, nome, cheia=False), mc.BOLINHA_BRANCA, (CASA_CLARA,))

    def test_x(self) -> None:
        self.conferir(xis, mc.X)

    def test_x_grande_que_encosta_na_borda_da_casa(self) -> None:
        self.conferir(lambda imagem, nome: xis(imagem, nome, braco=44), mc.X)

    def test_cruz_na_casa_clara(self) -> None:
        self.conferir(cruz, mc.CRUZ, (CASA_CLARA,))


class SemFalsoAlarmeTests(unittest.TestCase):
    def test_tabuleiro_vazio_nao_tem_marca(self) -> None:
        self.assertEqual(sugestao(tabuleiro()), {})

    def test_o_traco_da_hachura_nao_vira_x(self) -> None:
        imagem = tabuleiro()
        cx, cy = centro(CASA_HACHURADA)
        imagem[cy - 50 : cy + 50, cx - 50 : cx + 50] = 255
        cv2.line(imagem, (cx - 40, cy - 40), (cx + 40, cy + 40), PRETO, 8, cv2.LINE_AA)
        self.assertEqual(sugestao(imagem), {})

    def test_peca_branca_com_riscos_por_dentro_nao_vira_bolinha(self) -> None:
        imagem = tabuleiro()
        peca_branca(imagem, CASA_CLARA)
        self.assertEqual(sugestao(imagem), {})

    def test_peca_preta_grande_nao_vira_marca(self) -> None:
        for nome in (CASA_CLARA, CASA_HACHURADA):
            with self.subTest(casa=nome):
                imagem = tabuleiro()
                peca_preta(imagem, nome)
                self.assertEqual(sugestao(imagem), {})


class CasaTipicaTests(unittest.TestCase):
    def test_muitas_estrelas_na_mesma_cor_nao_viram_a_casa_tipica(self) -> None:
        """A mediana de todas as casas seria a própria estrela, e a estrela se cancelaria nela."""
        imagem = tabuleiro()
        casas = [f"{coluna}{fila}" for coluna in "abcdefgh" for fila in range(1, 9)]
        claras = [nome for nome in casas if (mc.indice_da_casa(nome) // 8 + mc.indice_da_casa(nome) % 8) % 2 == 0]
        marcadas = claras[:22]
        for nome in marcadas:
            estrela(imagem, nome)
        self.assertEqual(sugestao(imagem), dict.fromkeys(marcadas, mc.ESTRELA_PRETA))


class EnquadramentoTests(unittest.TestCase):
    def test_recorte_com_a_grade_deslocada_ainda_acha_a_estrela(self) -> None:
        imagem = tabuleiro()
        cx, cy = centro(CASA_CLARA)
        cv2.circle(imagem, (cx, cy), 49, BRANCO, -1)
        pontos = centro(CASA_CLARA)
        deslocada = imagem.copy()
        estrela(deslocada, CASA_CLARA, raio=30)
        desvio = np.float32([[1, 0, 10], [0, 1, 10]])
        trecho = cv2.warpAffine(deslocada[pontos[1] - 50 : pontos[1] + 50, pontos[0] - 50 : pontos[0] + 50], desvio, (100, 100), borderValue=BRANCO)
        imagem[pontos[1] - 50 : pontos[1] + 50, pontos[0] - 50 : pontos[0] + 50] = trecho
        self.assertEqual(sugestao(imagem), {CASA_CLARA: mc.ESTRELA_PRETA})

    def test_o_tamanho_do_recorte_nao_muda_a_resposta(self) -> None:
        imagem = tabuleiro()
        estrela(imagem, CASA_CLARA)
        xis(imagem, "a1" if (mc.indice_da_casa("a1") // 8 + mc.indice_da_casa("a1") % 8) % 2 == 0 else "b1")
        grande = sugestao(imagem)
        pequena = sugestao(cv2.resize(imagem, (400, 400), interpolation=cv2.INTER_AREA))
        self.assertEqual(pequena, grande)


class RetornoTests(unittest.TestCase):
    def test_devolve_marcas_de_casa_e_nenhum_traco(self) -> None:
        imagem = tabuleiro()
        estrela(imagem, CASA_CLARA)
        marcas = dm.sugerir_marcas(cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB))
        self.assertIsInstance(marcas, mc.MarcasDoDiagrama)
        self.assertEqual(marcas.tracos, ())

    def test_cada_tipo_sugerido_e_do_vocabulario(self) -> None:
        imagem = tabuleiro()
        estrela(imagem, CASA_CLARA)
        for tipo in sugestao(imagem).values():
            self.assertIn(tipo, mc.TIPOS_DE_CASA)


if __name__ == "__main__":
    unittest.main()
