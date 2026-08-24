"""O ganho do corte de linha, medido em faixa dilatada (S-198).

O comando existe porque `duas_linhas.separar` e `descartar_fragmentos` estão implementados e
**não são chamados por ninguém**: os dois dependem de um árbitro, e o árbitro é o classificador.
Este é o número que decide se eles entram no caminho de leitura -- e ele pode dar negativo, que
é uma resposta e não uma falha.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.cli.texto_duas_linhas import (
    BRACOS,
    MIN_CARACTERES,
    RAIO_PT,
    faixas_da_camada,
    ler_faixa,
)


class ClassificadorFalso:
    """Devolve sempre o mesmo caractere. O que se afirma aqui é a segmentação, não a leitura."""

    def __init__(self, confianca: float = 0.9) -> None:
        self.confianca = confianca
        self.lotes: list[int] = []

    def classificar(self, recortes: list[np.ndarray]) -> list[tuple[str, float]]:
        self.lotes.append(len(recortes))
        return [("x", self.confianca) for _ in recortes]


def _faixa_com_fragmento() -> np.ndarray:
    """Uma linha de texto e, na borda da faixa, os pedaços que a dilatação trouxe junto.

    **A escala da faixa é a de uma faixa de verdade, e isso não é decoração.** `escala_de_texto`
    descarta como "bloco" o componente que passa de 1% da área da imagem: numa miniatura, o
    caractere de 26 px vira bloco e a escala sai medida pelos fragmentos -- e aí todo limiar
    relativo mede o contrário do que devia.

    Os fragmentos ficam **abaixo** da linha porque é assim que eles viram banda própria: uma
    banda só de caixa curta não estabelece linha de base (F64), então o renque baixo que vem
    antes do texto entra na banda dele. É a mesma regra que faz o apóstrofo não abrir linha.
    """
    imagem = np.full((160, 900), 255, dtype=np.uint8)
    for i in range(30):  # a linha de verdade: caixas de altura de caractere
        imagem[20:46, 20 + i * 28 : 20 + i * 28 + 16] = 0
    for i in range(12):  # os fragmentos: baixos demais para serem caractere
        imagem[120:127, 22 + i * 28 : 22 + i * 28 + 14] = 0
    return imagem


class BracosTests(unittest.TestCase):
    """Os três braços diferem só no passo que ligam, e é isso que torna o ganho atribuível."""

    def test_sao_tres_e_cada_um_acrescenta_um_passo(self) -> None:
        nomes = [nome for nome, _ in BRACOS]
        self.assertEqual(["cru", "descarte", "descarte_e_corte"], nomes)
        self.assertEqual({"descartar": False, "cortar": False}, BRACOS[0][1])
        self.assertEqual({"descartar": True, "cortar": True}, BRACOS[2][1])

    def test_o_descarte_tira_a_linha_de_fragmentos_e_o_cru_a_le(self) -> None:
        """É o defeito da S-185 por inteiro: 8 pontos de CER vindos de pedaço de descendente."""
        imagem = _faixa_com_fragmento()

        cru, _ = ler_faixa(imagem, ClassificadorFalso(), descartar=False, cortar=False)
        limpo, _ = ler_faixa(imagem, ClassificadorFalso(), descartar=True, cortar=False)

        self.assertGreater(len(cru), len(limpo))
        self.assertTrue(limpo)

    def test_sem_cortar_nenhuma_caixa_e_partida(self) -> None:
        _, partidas = ler_faixa(_faixa_com_fragmento(), ClassificadorFalso(), descartar=True, cortar=False)
        self.assertEqual(0, partidas)

    def test_faixa_em_branco_devolve_texto_vazio_em_vez_de_levantar(self) -> None:
        texto, partidas = ler_faixa(
            np.full((160, 900), 255, dtype=np.uint8), ClassificadorFalso(), descartar=True, cortar=True
        )
        self.assertEqual("", texto)
        self.assertEqual(0, partidas)


class FaixaDaCamadaTests(unittest.TestCase):
    """A faixa vem da camada de texto, dilatada nos 2 pt com que a S-185 mediu o defeito."""

    def _pagina(self):  # noqa: ANN202 - o tipo é do fitz
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=300, height=200)
        page.insert_text((20, 50), "uma linha longa o bastante para medir")
        page.insert_text((20, 100), "curta")
        self.addCleanup(doc.close)
        return page

    def test_a_linha_curta_demais_nao_entra(self) -> None:
        """CER de uma linha de cinco caracteres pula de 0 para 0,2 com um erro só."""
        faixas = faixas_da_camada(self._pagina())

        self.assertEqual(1, len(faixas))
        self.assertGreaterEqual(len(faixas[0][0].strip()), MIN_CARACTERES)

    def test_a_faixa_sai_dilatada_nos_dois_pontos(self) -> None:
        page = self._pagina()
        texto, (x0, y0, x1, y1) = faixas_da_camada(page)[0]

        crua = next(
            linha["bbox"]
            for bloco in page.get_text("dict")["blocks"]
            for linha in bloco["lines"]
            if "".join(t["text"] for t in linha["spans"]).strip() == texto.strip()
        )
        self.assertAlmostEqual(crua[0] - RAIO_PT, x0, places=3)
        self.assertAlmostEqual(crua[3] + RAIO_PT, y1, places=3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
