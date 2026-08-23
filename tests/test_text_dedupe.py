"""A quase-duplicata: o mesmo glifo que difere num pixel de antialiasing (S-202).

**O que se testa aqui é o contrato, e não a qualidade do agrupamento.** Se um par de imagens é
ou não irmão é julgamento sobre o material — e ele foi feito olhando pares reais de
`training_data/`, com o resultado registrado em `dedupe.LIMIAR_PADRAO` e no cabeçalho do módulo.
O que um teste pode travar é o que quebraria calado: o descritor mudando de lado, uma amostra
sumindo, a altura decidindo onde ela não devia, e o grupo deixando de ser mais grosso que o de
entrada.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.text.dedupe import (
    LADO_DESCRITOR,
    LIMIAR_PADRAO,
    RAZAO_MAXIMA,
    agrupar,
    descritor,
)


def base(n_por_classe: int = 2, n_classes: int = 3, semente: int = 0):
    """Imagens bem separadas: nada se funde por acaso."""
    aleatorio = np.random.default_rng(semente)
    X = aleatorio.integers(0, 255, (n_por_classe * n_classes, 1024), dtype=np.uint8)
    y = np.repeat(np.arange(n_classes), n_por_classe).astype(np.int32)
    return X, y, np.arange(X.shape[0], dtype=np.int32)


def com_irma(X: np.ndarray, linha: int, delta: int = 2) -> np.ndarray:
    """Uma cópia quase igual da linha pedida, deslocada em `delta` níveis de cinza."""
    return np.clip(X[linha].astype(np.int16) + delta, 0, 255).astype(np.uint8)


class DescritorTests(unittest.TestCase):
    def test_o_descritor_tem_lado_24(self) -> None:
        """24 e não 32, e o motivo é aritmético: 1024/576 = 1,78.

        A spec de origem mede que 32 não muda a precisão e custa 78% mais memória, e é
        exatamente essa razão. O teste trava o número porque mudá-lo invalida o `LIMIAR_PADRAO`,
        que foi medido nesta escala -- e a invalidação seria calada.
        """
        self.assertEqual(24, LADO_DESCRITOR)
        X, _, _ = base()
        D = descritor(X)
        self.assertEqual(D.shape[1], 24 * 24)
        self.assertAlmostEqual(1024 / (24 * 24), 1.78, places=2)

    def test_o_descritor_sai_normalizado_em_zero_um(self) -> None:
        """O limiar é uma distância RMS nesta escala; sair em 0-255 o multiplicaria por 255."""
        X, _, _ = base()
        D = descritor(X)
        self.assertGreaterEqual(D.min(), 0.0)
        self.assertLessEqual(D.max(), 1.0)
        self.assertEqual(D.dtype, np.float32)

    def test_o_limiar_padrao_nao_e_o_do_projeto_de_origem(self) -> None:
        """0,20 é de outra métrica e aqui casaria 12% a 24% de **todos** os pares de uma classe.

        A regra do projeto é que um número de fora é hipótese até ser remedido aqui, e este foi.
        """
        self.assertLess(LIMIAR_PADRAO, 0.20)
        self.assertAlmostEqual(0.03, LIMIAR_PADRAO, places=3)


class AgruparTests(unittest.TestCase):
    def test_a_quase_duplicata_nao_remove_amostra(self) -> None:
        """O critério de aceite da S-202: ela agrupa, nunca poda.

        A precisão do critério não passa de ~99,3% nem na origem, e o que sobra são homóglifos
        de verdade. Um agrupador que apagasse levaria amostra boa junto.
        """
        X, y, g = base(n_por_classe=3)
        X = np.vstack([X, com_irma(X, 0), com_irma(X, 4)])
        y = np.concatenate([y, [y[0], y[4]]]).astype(np.int32)
        g = np.arange(X.shape[0], dtype=np.int32)
        novo, resumo = agrupar(X, y, g, limiar=0.05)

        self.assertEqual(novo.shape, y.shape)
        for classe in np.unique(y):
            self.assertEqual(int((y == classe).sum()), int((y[novo >= 0] == classe).sum()))
        self.assertEqual(resumo.grupos_antes, X.shape[0])
        self.assertLess(resumo.grupos_depois, resumo.grupos_antes)

    def test_a_irma_cai_no_mesmo_grupo_e_a_estranha_nao(self) -> None:
        X, y, g = base(n_por_classe=2)
        X = np.vstack([X, com_irma(X, 0)])
        y = np.concatenate([y, [y[0]]]).astype(np.int32)
        g = np.arange(X.shape[0], dtype=np.int32)
        novo, _ = agrupar(X, y, g, limiar=0.05)
        self.assertEqual(novo[0], novo[-1])
        self.assertNotEqual(novo[0], novo[1])

    def test_a_mesma_imagem_em_classes_diferentes_nao_se_funde(self) -> None:
        """A S-202 exige "a mesma leitura" junto do limiar.

        Duas imagens quase iguais com leituras diferentes não são irmãs -- são homóglifo ou erro
        de rótulo, e quem trata disso é `conflitos.py`.
        """
        X, y, g = base(n_por_classe=1, n_classes=2)
        X = np.vstack([X, com_irma(X, 0)])
        y = np.array([0, 1, 1], np.int32)  # a irmã da linha 0 está arquivada na classe 1
        g = np.arange(3, dtype=np.int32)
        novo, _ = agrupar(X, y, g, limiar=0.05)
        self.assertNotEqual(novo[0], novo[2])

    def test_a_altura_nativa_separa_irmas_de_corpos_diferentes(self) -> None:
        """A proporção e a altura entram "por fora" do descritor, como a spec manda."""
        X, y, g = base(n_por_classe=1, n_classes=1)
        X = np.vstack([X, com_irma(X, 0)])
        y = np.array([0, 0], np.int32)
        g = np.arange(2, dtype=np.int32)
        juntas = np.array([[10, 10], [10, 10]], np.int16)
        longe = np.array([[10, 10], [int(10 * RAZAO_MAXIMA) + 5, 10]], np.int16)
        self.assertEqual(*agrupar(X, y, g, dims=juntas, limiar=0.05)[0])
        self.assertNotEqual(*agrupar(X, y, g, dims=longe, limiar=0.05)[0])

    def test_a_altura_desconhecida_nao_decide(self) -> None:
        """58% dos recortes desta base chegaram em 32x32 da origem.

        Para eles a altura é o valor que a normalização impôs, não o do glifo -- e deixá-la
        separar seria decidir por um número que ninguém mediu.
        """
        X, y, g = base(n_por_classe=1, n_classes=1)
        X = np.vstack([X, com_irma(X, 0)])
        y = np.array([0, 0], np.int32)
        g = np.arange(2, dtype=np.int32)
        desconhecida = np.zeros((2, 2), np.int16)
        self.assertEqual(*agrupar(X, y, g, dims=desconhecida, limiar=0.05)[0])

    def test_o_grupo_novo_e_sempre_mais_grosso_que_o_de_entrada(self) -> None:
        """Nunca parte um grupo exato em dois: as cópias byte a byte continuam juntas."""
        X, y, _ = base(n_por_classe=4, n_classes=3)
        exatos = np.repeat(np.arange(6), 2).astype(np.int32)  # pares de cópia exata
        novo, _ = agrupar(X, y, exatos, limiar=0.05)
        for grupo in np.unique(exatos):
            self.assertEqual(1, np.unique(novo[exatos == grupo]).size)

    def test_o_limiar_zero_nao_funde_nada(self) -> None:
        X, y, g = base(n_por_classe=2)
        novo, resumo = agrupar(X, y, g, limiar=0.0)
        self.assertEqual(resumo.fundidos, 0)
        self.assertEqual(resumo.grupos_depois, resumo.grupos_antes)
        self.assertEqual(np.unique(novo).size, y.size)

    def test_a_entrada_de_tamanhos_diferentes_levanta(self) -> None:
        X, y, g = base()
        with self.assertRaises(ValueError):
            agrupar(X, y[:-1], g)

    def test_a_classe_com_uma_imagem_so_atravessa_intacta(self) -> None:
        X, y, g = base(n_por_classe=1, n_classes=4)
        novo, resumo = agrupar(X, y, g, limiar=0.5)
        self.assertEqual(resumo.fundidos, 0)
        self.assertEqual(np.unique(novo).size, 4)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
