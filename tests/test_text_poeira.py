"""S-714: a poeira da margem não pode esticar a caixa da linha."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from chess_diagram_ocr.text import leitor, poeira, quadros
from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.linhas import envolve, ordem_em_faixa, quebrar_em_linhas


def _letras(y: int, *, n: int = 30, x0: int = 300) -> list[Caixa]:
    return [Caixa(x0 + 22 * k, y, x0 + 22 * k + 16, y + 24) for k in range(n)]


def _manchas(n: int) -> list[Caixa]:
    """`n` pontos de poeira de 4 px na margem esquerda, longe de toda letra."""
    return [Caixa(20 + 25 * (k % 8), 100 + 40 * k, 24 + 25 * (k % 8), 104 + 40 * k) for k in range(n)]


class SoltasTests(unittest.TestCase):
    def test_o_ponto_junto_da_letra_nao_esta_solto(self) -> None:
        linha = _letras(100)
        ponto = Caixa(linha[-1].x2 + 3, 118, linha[-1].x2 + 8, 124)
        self.assertEqual(poeira.soltas([*linha, ponto]), [])

    def test_o_pingo_sobre_a_letra_nao_esta_solto(self) -> None:
        linha = _letras(100)
        pingo = Caixa(linha[3].x1 + 4, 90, linha[3].x1 + 9, 95)
        self.assertEqual(poeira.soltas([*linha, pingo]), [])

    def test_a_mancha_na_margem_esta_solta(self) -> None:
        linha = _letras(100)
        self.assertEqual(poeira.soltas([*linha, Caixa(20, 100, 24, 104)]), [len(linha)])

    def test_a_letra_solta_nao_e_poeira(self) -> None:
        """Só caixa pequena: uma inicial isolada tem altura de letra, por mais longe que esteja."""
        linha = _letras(100)
        self.assertEqual(poeira.soltas([*linha, Caixa(20, 100, 36, 124)]), [])

    def test_folha_vazia(self) -> None:
        self.assertEqual(poeira.soltas([]), [])


class SemPoeiraTests(unittest.TestCase):
    def test_poucas_soltas_nao_sao_poeira(self) -> None:
        """O `-` da célula de tabela, o asterisco de separador: a folha limpa fica como estava."""
        caixas = [*_letras(100), *_manchas(poeira.POEIRA_MINIMA_NA_FOLHA - 1)]
        self.assertEqual(poeira.sem_poeira(caixas), caixas)

    def test_a_partir_do_minimo_toda_solta_sai(self) -> None:
        letras = _letras(100)
        self.assertEqual(poeira.sem_poeira([*letras, *_manchas(poeira.POEIRA_MINIMA_NA_FOLHA)]), letras)

    def test_a_constante_desliga(self) -> None:
        caixas = [*_letras(100), *_manchas(poeira.POEIRA_MINIMA_NA_FOLHA)]
        with mock.patch.object(poeira, "TIRAR_POEIRA", False):
            self.assertEqual(poeira.sem_poeira(caixas), caixas)

    def test_a_caixa_da_linha_volta_a_ser_a_da_tinta(self) -> None:
        """O mecanismo inteiro: a mancha na altura da linha entrava nela e levava a caixa até a margem."""
        letras = _letras(100)
        manchas = [*_manchas(poeira.POEIRA_MINIMA_NA_FOLHA - 1), Caixa(200, 110, 204, 114)]
        esticada = envolve(quebrar_em_linhas(ordem_em_faixa([*letras, *manchas]))[1])
        self.assertLess(esticada[0], 300)
        linhas = quebrar_em_linhas(ordem_em_faixa(poeira.sem_poeira([*letras, *manchas])))
        self.assertEqual(len(linhas), 1)
        self.assertEqual(envolve(linhas[0])[0], 300.0)


class ApararTests(unittest.TestCase):
    """A mancha entre duas linhas não está solta: quem a vê é a linha já formada."""

    def test_a_mancha_abaixo_do_miolo_sai(self) -> None:
        linha = _letras(100)
        mancha = Caixa(400, 124 + 12, 405, 124 + 17)
        self.assertEqual(poeira.aparar([[*linha, mancha]]), [linha])

    def test_a_mancha_acima_do_miolo_sai(self) -> None:
        linha = _letras(100)
        mancha = Caixa(400, 100 - 16, 405, 100 - 11)
        self.assertEqual(poeira.aparar([[mancha, *linha]]), [linha])

    def test_virgula_ponto_e_apostrofo_ficam(self) -> None:
        linha = _letras(100)
        virgula = Caixa(linha[5].x2 + 1, 118, linha[5].x2 + 5, 129)
        ponto = Caixa(linha[-1].x2 + 3, 118, linha[-1].x2 + 8, 124)
        apostrofo = Caixa(linha[9].x2 + 1, 94, linha[9].x2 + 5, 102)
        inteira = sorted([*linha, virgula, ponto, apostrofo], key=lambda c: c.x1)
        self.assertEqual(poeira.aparar([inteira]), [inteira])

    def test_a_mancha_depois_do_ponto_final_sai(self) -> None:
        linha = _letras(100)
        ponto = Caixa(linha[-1].x2 + 3, 118, linha[-1].x2 + 8, 124)
        mancha = Caixa(ponto.x2 + 200, 118, ponto.x2 + 205, 123)
        self.assertEqual(poeira.aparar([[*linha, ponto, mancha]]), [[*linha, ponto]])

    def test_a_mancha_antes_da_primeira_letra_sai(self) -> None:
        linha = _letras(100)
        self.assertEqual(poeira.aparar([[Caixa(100, 110, 105, 115), *linha]]), [linha])

    def test_a_letra_que_recebeu_a_mancha_volta_ao_que_uma_letra_alcanca(self) -> None:
        """`unir_pingos` colou a mancha embaixo da letra: é a caixa da linha que descia até a de baixo."""
        linha = _letras(100)
        colada = Caixa(linha[4].x1, linha[4].y1, linha[4].x2, linha[4].y2 + 18)
        saida = poeira.aparar([[*linha[:4], colada, *linha[5:]]])[0]
        self.assertEqual(saida[4].y1, linha[4].y1)
        self.assertEqual(saida[4].y2, 124 + int(poeira.LETRA_ABAIXO_DO_MIOLO * 24))

    def test_o_descendente_e_a_maiuscula_nao_sao_cortados(self) -> None:
        linha = _letras(100)
        descendente = Caixa(linha[2].x1, 100, linha[2].x2, 124 + 8)
        maiuscula = Caixa(linha[6].x1, 100 - 12, linha[6].x2, 124)
        inteira = [*linha[:2], descendente, *linha[3:6], maiuscula, *linha[7:]]
        self.assertEqual(poeira.aparar([inteira]), [inteira])

    def test_a_caixa_de_duas_linhas_nao_e_cortada(self) -> None:
        """Passou do que a mancha alcança, é da S-198 e da S-712."""
        linha = _letras(100)
        dupla = Caixa(linha[4].x1, 100, linha[4].x2, 124 + 40)
        inteira = [*linha[:4], dupla, *linha[5:]]
        self.assertEqual(poeira.aparar([inteira]), [inteira])

    def test_a_linha_com_duas_linhas_dentro_fica_inteira(self) -> None:
        de_cima, de_baixo = _letras(100, n=4), _letras(190, n=4)
        ponto = Caixa(de_baixo[-1].x2 + 3, 208, de_baixo[-1].x2 + 8, 214)
        self.assertEqual(poeira.aparar([[*de_cima, *de_baixo, ponto]]), [[*de_cima, *de_baixo, ponto]])

    def test_a_linha_sem_letras_nao_tem_miolo(self) -> None:
        tracos = [Caixa(100 + 30 * k, 100, 110 + 30 * k, 103) for k in range(5)]
        fundo = _letras(300)
        self.assertEqual(poeira.aparar([tracos, fundo])[0], tracos)

    def test_a_constante_desliga(self) -> None:
        linha = [*_letras(100), Caixa(400, 136, 405, 141)]
        with mock.patch.object(poeira, "TIRAR_POEIRA", False):
            self.assertEqual(poeira.aparar([linha]), [linha])


class VizinhaPequenaTests(unittest.TestCase):
    def test_as_reticencias_nao_estao_soltas(self) -> None:
        """A folha limpa do Capablanca: `9 . . . Cxe4`, três pontos com mais de uma altura de letra de vão até ela."""
        linha = _letras(100)
        pontos = [Caixa(30 + 14 * k, 118, 34 + 14 * k, 122) for k in range(3)]
        self.assertEqual(poeira.soltas([*linha, *pontos]), [])


class SegmentarTests(unittest.TestCase):
    """A fiação: `leitor.segmentar` tem de usar o filtro, na folha inteira."""

    def _pagina(self) -> np.ndarray:
        imagem = np.full((1200, 1000), 255, dtype=np.uint8)
        for linha in range(8):
            for k in range(30):
                y = 100 + 60 * linha
                imagem[y : y + 24, 250 + 22 * k : 250 + 22 * k + 16] = 0
        for k in range(poeira.POEIRA_MINIMA_NA_FOLHA + 3):
            y = 100 + 50 * k
            imagem[y : y + 5, 30 + 20 * (k % 5) : 30 + 20 * (k % 5) + 5] = 0
        return imagem

    def test_a_poeira_nao_chega_as_caixas(self) -> None:
        _c, _b, _e, caixas, _r = leitor.segmentar(self._pagina())
        self.assertEqual(len(caixas), 8 * 30)
        self.assertGreaterEqual(min(c.x1 for c in caixas), 250)

    def test_desligada_a_poeira_volta(self) -> None:
        with mock.patch.object(poeira, "TIRAR_POEIRA", False):
            _c, _b, _e, caixas, _r = leitor.segmentar(self._pagina())
        self.assertLess(min(c.x1 for c in caixas), 250)


class _Meta:
    idx_to_char = {0: "a", 1: "."}


class _Classificador:
    """Tudo é `a`: aqui só a caixa da linha interessa."""

    meta = _Meta

    def probabilidades(self, recortes: list[np.ndarray]) -> np.ndarray:
        return np.tile(np.array([0.9, 0.1], dtype=np.float32), (len(recortes), 1))

    def classificar(self, recortes: list[np.ndarray]) -> list[tuple[str, float]]:
        return [("a", 0.9) for _ in recortes]


class _Reconhecedor:
    classifier = _Classificador()


class LinhasDoGlifoTests(unittest.TestCase):
    """**A mancha entre duas linhas dentro de `linhas_do_glifo`**: arrancar `_poeira.aparar` de lá tem de reprovar aqui."""

    Y = (100, 150, 200)
    ALTURA = 24

    def _folha(self) -> np.ndarray:
        imagem = np.full((400, 1000, 3), 255, dtype=np.uint8)
        for y in self.Y:
            for k in range(30):
                imagem[y : y + self.ALTURA, 100 + 22 * k : 100 + 22 * k + 16] = 0
        return imagem

    def _caixas(self, imagem: np.ndarray) -> list[tuple[float, float, float, float]]:
        cruas, _ = leitor.linhas_do_glifo(
            imagem, (), reconhecedor=_Reconhecedor(), colados="nunca", dicionario=False, dpi=None
        )
        return [(c.caixa.x1, c.caixa.y1, c.caixa.x2, c.caixa.y2) for c in cruas]

    def test_a_folha_sem_mancha(self) -> None:
        caixas = self._caixas(self._folha())
        self.assertEqual([c[1] for c in caixas], list(self.Y))
        self.assertEqual([c[3] for c in caixas], [y + self.ALTURA for y in self.Y])

    def test_a_mancha_entre_duas_linhas_nao_estica_a_caixa(self) -> None:
        """Uma só, entre as letras, a 10 px do fundo da linha: ela não está solta, e o portão da folha nem abre."""
        imagem = self._folha()
        imagem[100 + self.ALTURA + 10 : 100 + self.ALTURA + 14, 200:204] = 0
        caixas = self._caixas(imagem)
        self.assertEqual([c[3] for c in caixas], [y + self.ALTURA for y in self.Y])
        self.assertEqual([c[1] for c in caixas], list(self.Y))

    def test_a_mancha_na_ponta_nao_alarga_a_caixa(self) -> None:
        imagem = self._folha()
        fim = 100 + 22 * 30
        imagem[110:114, fim + 60 : fim + 64] = 0
        self.assertLess(self._caixas(imagem)[0][2], fim)

    def test_a_mancha_colada_na_letra_e_cortada(self) -> None:
        """A ponta de tinta embaixo da letra é um contorno só: `aparar` a corta no que uma letra alcança."""
        imagem = self._folha()
        imagem[100 + self.ALTURA : 100 + self.ALTURA + 16, 100 + 22 * 5 + 4 : 100 + 22 * 5 + 8] = 0
        caixas = self._caixas(imagem)
        self.assertLessEqual(caixas[0][3], 100 + self.ALTURA + int(poeira.LETRA_ABAIXO_DO_MIOLO * self.ALTURA))

    def test_com_a_constante_desligada_a_caixa_estica(self) -> None:
        imagem = self._folha()
        imagem[100 + self.ALTURA + 10 : 100 + self.ALTURA + 14, 200:204] = 0
        with mock.patch.object(poeira, "TIRAR_POEIRA", False):
            # Ela abre a banda de baixo sem fixar fundo, e a linha de baixo a recolhe: é a caixa dela que sobe.
            self.assertLess(self._caixas(imagem)[1][1], self.Y[1])


class DuplaTests(unittest.TestCase):
    def test_a_dupla_na_margem_esta_solta(self) -> None:
        """A dupla do *Dvoretsky* 564: uma vizinha só não faz marca de livro."""
        linha = _letras(100)
        dupla = [Caixa(20, 100, 24, 104), Caixa(32, 104, 36, 108)]
        self.assertEqual(poeira.soltas([*linha, *dupla]), [len(linha), len(linha) + 1])


class MolduraNumaColunaTests(unittest.TestCase):
    """O limiar alto do scan fecha a caixa do nome da partida: ela não é quadro de largura inteira."""

    def _caixas(self, x1: int, x2: int) -> tuple[list[Caixa], np.ndarray]:
        binaria = np.zeros((1000, 1800), np.uint8)
        moldura = Caixa(x1, 400, x2, 540)
        binaria[400:402, x1:x2] = 255
        linhas = [Caixa(x, y, x + 16, y + 24) for y in (415, 455, 495) for x in range(x1 + 40, x2 - 40, 22)]
        margens = [Caixa(100, 100, 116, 124), Caixa(1700, 100, 1716, 124)]
        return ([moldura, *linhas, *margens], binaria)

    def test_a_moldura_de_uma_coluna_nao_corta_a_folha(self) -> None:
        caixas, binaria = self._caixas(1000, 1720)
        self.assertEqual(quadros.molduras_nas_caixas(caixas, binaria, escala=30), [])

    def test_a_que_cruza_o_meio_corta(self) -> None:
        caixas, binaria = self._caixas(400, 1400)
        self.assertEqual(quadros.molduras_nas_caixas(caixas, binaria, escala=30), [(400, 540)])

    def test_a_constante_desliga(self) -> None:
        caixas, binaria = self._caixas(1000, 1720)
        with mock.patch.object(quadros, "MOLDURA_CRUZA_O_MEIO", False):
            self.assertEqual(quadros.molduras_nas_caixas(caixas, binaria, escala=30), [(400, 540)])


if __name__ == "__main__":
    unittest.main()
