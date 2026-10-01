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
    COBERTURA_DE_SCAN,
    DPI_ALVO_DE_SCAN,
    IDENTITY,
    OTSU,
    SAUVOLA,
    SEM_CAMINHO_DE_SCAN,
    BoardNormalizer,
    NormalizerConfig,
    ScanConfig,
    binarizar_pagina,
    estimate_skew,
    pagina_e_scan,
    preparar_pagina_de_scan,
    reamostrar_pagina,
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


# ------------------------------------------------- a página de scan puro (S-547)


def pagina_de_scan(largura: int = 600, altura: int = 800, *, sombra: bool = False) -> np.ndarray:
    """Uma página cinzenta com um tabuleiro no meio. Com `sombra`, o lado direito é escuro.

    A sombra é o que separa Otsu de Sauvola: um limiar global tem de escolher entre o lado
    claro e o lado escuro da página, e um local decide em cada janela.
    """
    pagina = np.full((altura, largura, 3), 220, dtype=np.uint8)
    lado = min(largura, altura) // 2
    y0 = (altura - lado) // 2
    x0 = (largura - lado) // 2
    pagina[y0 : y0 + lado, x0 : x0 + lado] = board(lado)
    if sombra:
        rampa = np.linspace(1.0, 0.35, largura, dtype=np.float32)[None, :, None]
        pagina = np.clip(pagina.astype(np.float32) * rampa, 0, 255).astype(np.uint8)
    return pagina


class PortaDoScanTests(unittest.TestCase):
    """Quando a página **é** um scan -- e o que a medição do acervo disse sobre isso."""

    def test_a_porta_e_ou_e_nao_e(self) -> None:
        """Os dois sinais discordam em livro demais para um `e` valer: o `Koblenz` tem camada de
        texto **e** é scan de página inteira (o OCR de quem digitalizou deixou o texto lá); o
        `Simple Chess` não tem camada nenhuma e também não tem imagem de página inteira."""
        self.assertTrue(pagina_e_scan(False, 0.0), "sem camada de texto")
        self.assertTrue(pagina_e_scan(True, 0.95), "uma imagem cobrindo a página")
        self.assertFalse(pagina_e_scan(True, 0.10), "texto e uma figura pequena: não é scan")

    def test_o_piso_de_cobertura_e_o_mesmo_da_deteccao(self) -> None:
        """`MAX_PAGE_COVERAGE` decide "esta imagem é fundo e não diagrama"; aqui o mesmo número
        decide "esta página é um scan". Dois números para a mesma observação divergiriam."""
        from chess_diagram_ocr.detection.embedded import MAX_PAGE_COVERAGE

        self.assertEqual(COBERTURA_DE_SCAN, MAX_PAGE_COVERAGE)
        self.assertTrue(pagina_e_scan(True, COBERTURA_DE_SCAN))
        self.assertFalse(pagina_e_scan(True, COBERTURA_DE_SCAN - 0.01))


class CaminhoDeScanTests(unittest.TestCase):
    """O caminho existe, é testado, e vem **desligado** -- ver o docstring de `ScanConfig`."""

    def test_o_padrao_e_identidade_e_devolve_a_mesma_imagem(self) -> None:
        pagina = pagina_de_scan()
        self.assertTrue(SEM_CAMINHO_DE_SCAN.is_identity)
        self.assertIs(preparar_pagina_de_scan(pagina), pagina)

    def test_binarizacao_desconhecida_levanta_em_vez_de_cair_no_padrao(self) -> None:
        """Um método escrito errado que virasse "não binariza" seria uma medição silenciosamente
        feita sobre outra coisa."""
        with self.assertRaises(ValueError):
            ScanConfig(binarizacao="niblack")
        with self.assertRaises(ValueError):
            binarizar_pagina(pagina_de_scan(), "niblack")

    def test_dpi_alvo_negativo_e_recusado(self) -> None:
        """Uma escala negativa não reduz nem amplia: ela é um engano de sinal que o `cv2.resize`
        transformaria numa exceção três camadas adiante."""
        with self.assertRaises(ValueError):
            ScanConfig(dpi_alvo=-300)

    def test_a_binaria_sai_com_tres_canais_e_so_dois_valores(self) -> None:
        """Tudo o que consome a página renderizada espera `(H, W, 3)`; um canal só faria a troca
        aparecer como erro de forma três camadas adiante."""
        for metodo in (OTSU, SAUVOLA):
            binaria = binarizar_pagina(pagina_de_scan(), metodo)
            self.assertEqual(binaria.shape, (800, 600, 3), metodo)
            self.assertEqual(set(np.unique(binaria).tolist()), {0, 255}, metodo)

    def test_otsu_e_global_e_sauvola_e_local(self) -> None:
        """Numa página com sombra de lombada, o limiar global entrega o lado escuro inteiro como
        tinta; o local atravessa a sombra. É a escolha que o item tinha de medir."""
        com_sombra = pagina_de_scan(sombra=True)
        escuro = slice(-60, None)
        preto_otsu = float((binarizar_pagina(com_sombra, OTSU)[:, escuro, 0] == 0).mean())
        preto_sauvola = float((binarizar_pagina(com_sombra, SAUVOLA)[:, escuro, 0] == 0).mean())
        self.assertGreater(preto_otsu, 0.9, "o Otsu apaga o lado escuro")
        self.assertLess(preto_sauvola, 0.5, "o Sauvola decide por janela")

    def test_reamostrar_para_o_mesmo_dpi_e_identidade(self) -> None:
        pagina = pagina_de_scan()
        self.assertIs(reamostrar_pagina(pagina, dpi=220, dpi_alvo=220), pagina)
        self.assertIs(reamostrar_pagina(pagina, dpi=220, dpi_alvo=0), pagina)

    def test_reamostrar_muda_a_escala_e_nao_o_conteudo(self) -> None:
        pagina = pagina_de_scan()
        maior = reamostrar_pagina(pagina, dpi=220, dpi_alvo=440)
        self.assertEqual(maior.shape[:2], (1600, 1200))
        menor = reamostrar_pagina(pagina, dpi=220, dpi_alvo=110)
        self.assertEqual(menor.shape[:2], (400, 300))

    def test_a_reamostragem_vem_antes_da_binarizacao(self) -> None:
        """A binarização mede estatísticas em janela de pixels: fazê-la antes seria decidir o
        limiar numa escala e usá-lo noutra."""
        pronta = preparar_pagina_de_scan(
            pagina_de_scan(), ScanConfig(binarizacao=SAUVOLA, dpi_alvo=110), dpi=220
        )
        self.assertEqual(pronta.shape[:2], (400, 300))
        self.assertEqual(set(np.unique(pronta).tolist()), {0, 255})

    def test_o_dpi_alvo_declarado_e_o_que_a_medicao_usou(self) -> None:
        """300 DPI está declarado e **não** é o padrão: medido, o `Koblenz` perde 8 dos 120
        diagramas e o `Niemeijer` 33 dos 51 ao ser lido a 300."""
        self.assertEqual(DPI_ALVO_DE_SCAN, 300)
        self.assertEqual(ScanConfig().dpi_alvo, 0)
        self.assertEqual(ScanConfig().binarizacao, "")


if __name__ == "__main__":
    unittest.main()
