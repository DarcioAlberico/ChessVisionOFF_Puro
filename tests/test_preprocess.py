"""Normalização do tabuleiro (S-39).

Todas as etapas estão **desligadas por padrão, e por medição** — ver
docs/EXPERIMENTS_FASE7.md. O que estes testes travam é o contrato: que o padrão continue
sendo identidade, que a versão distinga configurações (senão um checkpoint treinado com
normalização carrega num pipeline sem ela, que é o defeito que a S-27 corrigiu), e que cada
etapa faça o que o nome diz para quem ligá-la.
"""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from chess_diagram_ocr.preprocess import (
    IDENTITY,
    BoardNormalizer,
    NormalizerConfig,
    estimate_skew,
)


def board(side: int = 800, *, hatched: bool = False) -> np.ndarray:
    """Tabuleiro 8×8. Com `hatched`, as casas escuras são listradas como no Euwe."""
    cell = side // 8
    image = np.full((side, side, 3), 245, dtype=np.uint8)
    for row in range(8):
        for column in range(8):
            if (row + column) % 2 == 0:
                continue
            y0, x0 = row * cell, column * cell
            if hatched:
                for offset in range(0, cell * 2, max(2, side // 64)):
                    cv2.line(image, (x0 + offset, y0), (x0 + offset - cell, y0 + cell), (40, 40, 40), 2)
            else:
                image[y0 : y0 + cell, x0 : x0 + cell] = 60
    return image


def rotated(image: np.ndarray, degrees: float) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)


class VersionTests(unittest.TestCase):
    def test_o_padrao_e_identidade_e_se_chama_norm0(self) -> None:
        self.assertTrue(NormalizerConfig().is_identity)
        self.assertEqual(NormalizerConfig().version, "norm0")

    def test_cada_etapa_muda_a_versao(self) -> None:
        """Sem isto, um checkpoint treinado com normalização carrega num pipeline sem ela."""
        versoes = {
            NormalizerConfig(deskew=True).version,
            NormalizerConfig(flat_field=True).version,
            NormalizerConfig(hatch_suppression=True).version,
            NormalizerConfig(clahe=True).version,
            NormalizerConfig(deskew=True, clahe=True).version,
            NormalizerConfig().version,
        }
        self.assertEqual(len(versoes), 6, f"versões colidiram: {versoes}")

    def test_a_versao_faz_ida_e_volta(self) -> None:
        for config in (
            NormalizerConfig(),
            NormalizerConfig(deskew=True),
            NormalizerConfig(flat_field=True, clahe=True),
            NormalizerConfig(deskew=True, flat_field=True, hatch_suppression=True, clahe=True),
        ):
            with self.subTest(versao=config.version):
                self.assertEqual(NormalizerConfig.from_version(config.version), config)

    def test_versao_desconhecida_e_recusada(self) -> None:
        for texto in ("norm z", "normx", "cnn-gray-64-linear"):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                NormalizerConfig.from_version(texto)

    def test_norm_sem_letra_e_norm0_sao_a_mesma_coisa(self) -> None:
        """Um checkpoint antigo não registra nada, e "nada" tem de significar identidade."""
        self.assertEqual(NormalizerConfig.from_version("norm"), NormalizerConfig())
        self.assertEqual(NormalizerConfig.from_version("norm0"), NormalizerConfig())


class IdentityTests(unittest.TestCase):
    def test_o_padrao_devolve_a_mesma_imagem_sem_copiar(self) -> None:
        original = board()
        self.assertIs(BoardNormalizer(IDENTITY).normalize(original), original)

    def test_num_tabuleiro_limpo_as_etapas_mexem_pouco(self) -> None:
        """A restrição do desenho: normalizar não pode estragar o que já está bom.

        O Polgar sai a 1,000 de taxa de exportação no conjunto de campo, e um normalizador
        que "melhorasse" esse arruinaria mais do que conserta.
        """
        limpo = board()
        for etapa in ("deskew", "flat_field", "clahe"):
            with self.subTest(etapa=etapa):
                saida = BoardNormalizer(NormalizerConfig(**{etapa: True})).normalize(limpo)
                diferenca = float(np.abs(saida.astype(np.float32) - limpo.astype(np.float32)).mean())
                self.assertLess(diferenca, 12.0, f"{etapa} mexeu demais num tabuleiro já limpo")


class SkewTests(unittest.TestCase):
    def test_tabuleiro_alinhado_nao_e_girado(self) -> None:
        """Girar por ruído reamostra a imagem de graça, e reamostrar custa nitidez."""
        self.assertEqual(estimate_skew(board()), 0.0)

    def test_uma_rotacao_pequena_e_detectada_no_sentido_certo(self) -> None:
        torto = rotated(board(), 1.5)
        estimado = estimate_skew(torto)
        self.assertLess(estimado, 0.0, "o sinal do ângulo tem de desfazer a rotação")
        self.assertAlmostEqual(abs(estimado), 1.5, delta=1.0)

    def test_o_deskew_devolve_a_grade_para_o_lugar(self) -> None:
        torto = rotated(board(), 1.5)
        endireitado = BoardNormalizer(NormalizerConfig(deskew=True)).normalize(torto)
        # Periodicidade da grade: maior depois de endireitar.
        from chess_diagram_ocr.preprocess import _grid_periodicity

        antes = _grid_periodicity(cv2.cvtColor(torto, cv2.COLOR_RGB2GRAY))
        depois = _grid_periodicity(cv2.cvtColor(endireitado, cv2.COLOR_RGB2GRAY))
        self.assertGreater(depois, antes)

    def test_a_busca_nao_sai_da_faixa(self) -> None:
        """Além de poucos graus a busca deixa de achar rotação e acha coincidência."""
        from chess_diagram_ocr.preprocess import MAX_SKEW_DEGREES

        self.assertLessEqual(abs(estimate_skew(rotated(board(), 20.0))), MAX_SKEW_DEGREES)


class StageTests(unittest.TestCase):
    def test_o_campo_plano_tira_o_gradiente_de_iluminacao(self) -> None:
        limpo = board()
        altura, largura = limpo.shape[:2]
        rampa = np.linspace(0.55, 1.0, largura, dtype=np.float32)[None, :, None]
        iluminado = np.clip(limpo.astype(np.float32) * rampa, 0, 255).astype(np.uint8)

        corrigido = BoardNormalizer(NormalizerConfig(flat_field=True)).normalize(iluminado)

        def desequilibrio(img: np.ndarray) -> float:
            cinza = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
            return abs(float(cinza[:, : largura // 2].mean() - cinza[:, largura // 2 :].mean()))

        self.assertLess(desequilibrio(corrigido), desequilibrio(iluminado) / 2)

    def test_a_supressao_de_trama_alisa_a_casa_hachurada(self) -> None:
        """A etapa faz o que diz; o que a medição rejeitou foi o **efeito na leitura**."""
        hachurado = board(hatched=True)
        alisado = BoardNormalizer(NormalizerConfig(hatch_suppression=True)).normalize(hachurado)

        def aspereza(img: np.ndarray) -> float:
            casa = cv2.cvtColor(img[100:200, 0:100], cv2.COLOR_RGB2GRAY).astype(np.float32)
            return float(np.abs(np.diff(casa, axis=1)).mean())

        self.assertLess(aspereza(alisado), aspereza(hachurado))

    def test_a_ordem_das_etapas_e_a_declarada(self) -> None:
        """CLAHE por último porque é o único que amplifica; amplificar antes ampliaria a trama."""
        import inspect

        fonte = inspect.getsource(BoardNormalizer.normalize)
        posicoes = [fonte.index(f"self.config.{etapa}") for etapa in ("deskew", "flat_field", "hatch_suppression", "clahe")]
        self.assertEqual(posicoes, sorted(posicoes))


if __name__ == "__main__":
    unittest.main()
