"""A fiação da Fase 103: cada decisão tem de chegar ao texto por `linhas_do_glifo` (S-764).

Os testes de decisão chamam cada módulo direto, e ficam verdes com a chamada arrancada do leitor. Aqui a folha é
desenhada, a segmentação é a de verdade, e o classificador é falso: responde pelo tamanho do recorte. Nenhum modelo,
nenhum livro, e a afirmação é sobre o texto que sai.
"""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
from glifo_sintetico import CLASSES, I2C

from chess_diagram_ocr.text import dicionario, leitor

ALTURA = 400
LARGURA = 1000
BASE = 200


class _Meta:
    idx_to_char = I2C


class _Classificador:
    """Responde pelo `(altura, largura)` do recorte. Tamanho desconhecido é erro: o desenho está errado."""

    meta = _Meta

    def __init__(self, mapa: dict[tuple[int, int], tuple[str, str | None]]) -> None:
        self.mapa = mapa

    def probabilidades(self, recortes: list[np.ndarray]) -> np.ndarray:
        m = np.full((len(recortes), len(CLASSES)), 1e-5, dtype=np.float32)
        for k, r in enumerate(recortes):
            primeiro, segundo = self.mapa.get(r.shape[:2], (".", None))
            m[k, CLASSES.index(primeiro)] = 0.6
            if segundo:
                m[k, CLASSES.index(segundo)] = 0.3
        return m

    def classificar(self, recortes: list[np.ndarray]) -> list[tuple[str, float]]:
        m = self.probabilidades(recortes)
        return [(I2C[int(np.argmax(m[k]))], float(m[k].max())) for k in range(len(recortes))]


class _Reconhecedor:
    def __init__(self, classificador: _Classificador) -> None:
        self.classifier = classificador


# (caractere, largura, altura, descida abaixo da base, vão depois, opcional: segundo palpite do modelo)
# As letras de x de cada linha: cada tamanho é uma letra só, porque o classificador falso responde pelo tamanho.
A = ("a", 12, 20, 0, 3)
E = ("e", 11, 20, 0, 3)
N = ("n", 13, 20, 0, 3)


def _ler(desenho: list[tuple], lexico: frozenset[str] = frozenset({"nada"}), extras: dict | None = None) -> str:
    """Desenha a linha numa folha branca, lê por `linhas_do_glifo` e devolve o texto da linha."""
    img = np.full((ALTURA, LARGURA, 3), 255, dtype=np.uint8)
    mapa: dict[tuple[int, int], tuple[str, str | None]] = dict(extras or {})
    x = 40
    for item in desenho:
        char, largura, altura, descida, vao = item[:5]
        fundo = BASE + descida
        topo = (BASE - altura) if descida >= 0 else (fundo - altura)
        img[topo:fundo, x : x + largura] = 0
        if char == "f":  # a haste à esquerda, e o gancho no alto: é o que faz o vão de baixo ser maior
            img[topo + 4 : fundo, x + 3 : x + largura] = 255
        if char == "m":  # o vale: duas partes ligadas por um fio no alto
            meio = x + largura // 2
            img[topo + 2 : fundo, meio - 1 : meio + 1] = 255
        mapa.setdefault((altura + max(descida, 0), largura), (char, item[5] if len(item) > 5 else None))
        x += largura + vao
    with (
        mock.patch.object(dicionario, "carregar", lambda *_a, **_k: lexico),
    ):
        cruas, _ = leitor.linhas_do_glifo(img, (), reconhecedor=_Reconhecedor(_Classificador(mapa)), colados="nunca", dpi=220)
    return " | ".join(c.texto for c in cruas)


class FiacaoTests(unittest.TestCase):
    def test_a_regua_das_letras_de_x(self) -> None:
        """`caixa_alta.decidir`: o `W` na linha de lance. Com a mediana, sairia `w`."""
        desenho = [("W", 24, 28, 0, 3), ("h", 14, 28, 0, 3), ("1", 8, 28, 0, 3), ("2", 9, 28, 0, 3), ("3", 10, 28, 0, 3), ("4", 11, 28, 0, 3), A, E]
        self.assertEqual(_ler(desenho), "Wh1234ae")

    def test_a_escala_chega_a_decisao(self) -> None:
        """A linha de um `W` só, com outra linha de texto para a escala medir: sem a escala, ele vira `w`."""
        desenho = [("W", 24, 28, 0, 3)]
        lido = _ler(desenho)
        self.assertEqual(lido, "W")

    def test_a_cedilha_chega_pelas_caixas(self) -> None:
        desenho = [A, E, N, ("c", 12, 20, 9, 3, "ç"), A]
        self.assertEqual(_ler(desenho), "aençA".replace("A", "a"))

    def test_o_traco_vertical(self) -> None:
        desenho = [A, E, N, ("w", 15, 20, 0, 3), ("i", 3, 27, 0, 3), (".", 4, 27, 0, 3), (".", 5, 27, 0, 3), A, E, N, A, E, N]
        self.assertEqual(_ler(desenho), "aenwillaenaen")

    def test_a_palavra_coerente(self) -> None:
        """O versalete: maiúscula na altura das letras de x. A régua de altura o derruba, e é a palavra que o sobe."""
        desenho = [A, E, ("n", 13, 20, 0, 12), ("U", 18, 20, 0, 3), ("N", 16, 20, 0, 3), ("A", 17, 20, 0, 3), ("S", 19, 20, 0, 3), ("O", 20, 20, 0, 3)]
        self.assertEqual(_ler(desenho), "aen UNASO")

    def test_o_lance_em_minuscula(self) -> None:
        """`KC5`: pela altura o `c` passa do corte, e quem o desce é a mesma chamada de `coerente`."""
        desenho = [("K", 16, 28, 0, 3), ("C", 15, 28, 0, 3), ("5", 12, 28, 0, 3)]
        self.assertEqual(_ler(desenho), "Kc5")

    def test_coerente_recebe_o_lexico(self) -> None:
        desenho = [("B", 16, 28, 0, 3), ("o", 12, 20, 0, 3), ("U", 18, 28, 0, 3), ("e", 11, 20, 0, 3), ("t", 8, 26, 0, 3)]
        self.assertEqual(_ler(desenho, frozenset({"bouet"})), "Bouet")
        self.assertEqual(_ler(desenho), "BoUet", "sem a forma minúscula no léxico, é absolvida")

    def test_o_acento(self) -> None:
        desenho = [E, N, ("t", 8, 26, 0, 3), ("ä", 14, 29, 0, 3, "ã"), ("o", 15, 20, 0, 3)]
        self.assertEqual(_ler(desenho, frozenset({"então"})), "então")

    def test_o_colado_pelo_lexico(self) -> None:
        desenho = [("s", 10, 20, 0, 3), ("m", 30, 26, 0, 3), ("d", 14, 28, 0, 3), ("y", 12, 20, 0, 3)]
        extras = {(26, 14): ("t", None), (26, 16): ("u", None)}
        lido = _ler(desenho, frozenset({"study"}), extras)
        self.assertEqual(lido, "study")

    def test_a_ligadura(self) -> None:
        desenho = [("fi", 14, 28, 0, 1), ("1", 7, 20, 0, 3), ("r", 9, 20, 0, 3), ("s", 10, 20, 0, 3), ("t", 8, 26, 0, 3), A, E]
        self.assertEqual(_ler(desenho), "firstae")

    def test_as_aspas(self) -> None:
        """Dois riscos no alto da linha, depois de uma letra alta."""
        img_desenho = [("k", 12, 30, 0, 3), A, E, N, ("'", 7, 10, -20, 3), ("(", 8, 10, -20, 3)]
        self.assertEqual(_ler(img_desenho), 'kaen"')

    def test_a_fronteira(self) -> None:
        desenho = [("o", 12, 20, 0, 3), ("f", 15, 28, 0, 5), ("t", 8, 26, 0, 3), ("h", 14, 28, 0, 3), E, N]
        self.assertEqual(_ler(desenho, frozenset({"then"})), "of then")

    def test_juntar_o_que_o_vao_separou(self) -> None:
        desenho = [("g", 14, 20, 0, 8), ("a", 12, 20, 0, 8), ("n", 13, 20, 0, 3), ("h", 14, 28, 0, 3), ("o", 15, 20, 0, 3)]
        self.assertEqual(_ler(desenho, frozenset({"ganho"})), "ganho")


if __name__ == "__main__":
    unittest.main()
