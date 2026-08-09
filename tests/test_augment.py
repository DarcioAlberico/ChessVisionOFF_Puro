"""Aumento de dados dirigido ao acervo (S-40).

Três coisas são travadas aqui, e as três já quebraram alguma coisa neste projeto:

1. **Piclabilidade.** No Windows o `DataLoader` com `num_workers > 0` usa `spawn` e pickleia
   a pipeline inteira para cada worker. Foi por isso que `_clamp01` deixou de ser `lambda`.
2. **Determinismo sob semente.** O critério de aceite da S-27 é "mesma semente, mesmas
   métricas", e uma transformação que sorteia fora do RNG do torch o quebra em silêncio.
3. **Rótulo preservado.** O espelhamento horizontal é a única transformação cuja validade
   depende do domínio; se ela estiver errada, o dataset dobra de tamanho ensinando o errado.
"""

from __future__ import annotations

import pickle
import unittest

import torch

from chess_diagram_ocr.augment import (
    DEFAULT_AUGMENT,
    AugmentConfig,
    RandomHatch,
    RandomHorizontalFlipCell,
    RandomInvert,
    RandomPaper,
    RandomSpeckle,
    build_augmentations,
)
from chess_diagram_ocr.training import build_train_transform

TODAS = AugmentConfig(hflip=0.5, hatch=0.5, speckle=0.5, paper=0.5, invert=0.5)


def cell(value: float = 0.5) -> torch.Tensor:
    return torch.full((1, 64, 64), value)


def asymmetric_cell() -> torch.Tensor:
    """Casa cuja metade esquerda difere da direita, para o espelhamento ser observável."""
    x = torch.zeros(1, 64, 64)
    x[:, :, :32] = 1.0
    return x


class ConfigTests(unittest.TestCase):
    def test_o_padrao_reproduz_o_treino_anterior_a_s40(self) -> None:
        """`AugmentConfig()` não pode mudar o modelo que já existe."""
        self.assertEqual(DEFAULT_AUGMENT.version, "aug0")
        self.assertEqual(build_augmentations(DEFAULT_AUGMENT), [])

    def test_cada_transformacao_muda_a_versao(self) -> None:
        versoes = {
            AugmentConfig().version,
            AugmentConfig(hflip=0.5).version,
            AugmentConfig(hatch=0.5).version,
            AugmentConfig(speckle=0.5).version,
            AugmentConfig(paper=0.5).version,
            AugmentConfig(invert=0.5).version,
        }
        self.assertEqual(len(versoes), 6, f"versões colidiram: {versoes}")

    def test_a_versao_entra_nos_metadados_do_checkpoint(self) -> None:
        """Sem isso, comparar dois modelos pode estar comparando dois regimes de aumento."""
        import inspect

        from chess_diagram_ocr import training

        self.assertIn("augment_version", inspect.getsource(training.train_model))

    def test_a_ordem_e_a_de_uma_pagina_real(self) -> None:
        """O papel amarela antes de a tinta da hachura ser impressa; a granulação é do scanner."""
        tipos = [type(etapa).__name__ for etapa in build_augmentations(TODAS)]
        self.assertEqual(
            tipos,
            ["RandomHorizontalFlipCell", "RandomInvert", "RandomPaper", "RandomHatch", "RandomSpeckle"],
        )


class LabelPreservationTests(unittest.TestCase):
    def test_o_espelhamento_realmente_espelha(self) -> None:
        original = asymmetric_cell()
        espelhado = RandomHorizontalFlipCell(1.0)(original)
        self.assertFalse(torch.equal(espelhado, original))
        self.assertTrue(torch.equal(torch.flip(espelhado, dims=[-1]), original))

    def test_o_espelhamento_e_so_horizontal(self) -> None:
        """Espelhar na vertical trocaria peça branca por preta no contexto da fila -- e a
        casa não carrega esse contexto, mas o rótulo carrega. Só a horizontal é segura."""
        x = torch.zeros(1, 64, 64)
        x[:, :32, :] = 1.0  # metade de cima diferente da de baixo
        self.assertTrue(torch.equal(RandomHorizontalFlipCell(1.0)(x), x))

    def test_nenhuma_transformacao_muda_o_formato(self) -> None:
        x = cell()
        for etapa in build_augmentations(TODAS):
            with self.subTest(etapa=type(etapa).__name__):
                self.assertEqual(etapa(x).shape, x.shape)

    def test_a_saida_fica_no_intervalo_depois_do_clamp(self) -> None:
        transformacao = build_train_transform(TODAS)
        torch.manual_seed(3)
        for _ in range(20):
            saida = transformacao(cell(0.9))
            self.assertGreaterEqual(float(saida.min()), 0.0)
            self.assertLessEqual(float(saida.max()), 1.0)


class BehaviourTests(unittest.TestCase):
    def test_probabilidade_zero_e_identidade(self) -> None:
        x = cell()
        for classe in (RandomHorizontalFlipCell, RandomHatch, RandomSpeckle, RandomPaper, RandomInvert):
            with self.subTest(classe=classe.__name__):
                self.assertTrue(torch.equal(classe(0.0)(x), x))

    def test_a_hachura_escurece_e_nao_clareia(self) -> None:
        """É tinta sobre papel: só pode tirar luz."""
        torch.manual_seed(1)
        x = cell(0.9)
        saida = RandomHatch(1.0)(x)
        self.assertLessEqual(float(saida.max()), float(x.max()) + 1e-6)
        self.assertLess(float(saida.mean()), float(x.mean()))

    def test_a_hachura_produz_listras_e_nao_um_tom_uniforme(self) -> None:
        torch.manual_seed(1)
        saida = RandomHatch(1.0)(cell(0.9))
        # Duas linhas vizinhas de uma listra diagonal não podem ser iguais.
        self.assertGreater(float(saida.std()), 0.02)

    def test_o_papel_e_um_gradiente_suave_e_nao_um_degrau(self) -> None:
        torch.manual_seed(2)
        saida = RandomPaper(1.0)(cell(1.0))
        colunas = saida[0].mean(dim=0)
        self.assertLess(float(torch.diff(colunas).abs().max()), 0.01)

    def test_a_inversao_e_involutiva(self) -> None:
        x = cell(0.3)
        self.assertTrue(torch.allclose(RandomInvert(1.0)(RandomInvert(1.0)(x)), x))

    def test_a_granulacao_nao_apaga_a_peca(self) -> None:
        """Ruído que destrói o sinal ensina o modelo a chutar, não a ser robusto."""
        torch.manual_seed(4)
        original = asymmetric_cell()
        saida = RandomSpeckle(1.0)(original)
        correlacao = float(
            torch.corrcoef(torch.stack([original.flatten(), saida.flatten()]))[0, 1]
        )
        self.assertGreater(correlacao, 0.85)


class PicklingTests(unittest.TestCase):
    def test_a_pipeline_inteira_e_piclavel(self) -> None:
        """`num_workers > 0` no Windows usa `spawn`, e pickleia isto para cada worker."""
        transformacao = build_train_transform(TODAS)
        recuperada = pickle.loads(pickle.dumps(transformacao))
        torch.manual_seed(5)
        esperado = transformacao(cell())
        torch.manual_seed(5)
        self.assertTrue(torch.allclose(recuperada(cell()), esperado))

    def test_cada_transformacao_isolada_e_piclavel(self) -> None:
        for etapa in build_augmentations(TODAS):
            with self.subTest(etapa=type(etapa).__name__):
                pickle.loads(pickle.dumps(etapa))


class DeterminismTests(unittest.TestCase):
    def test_mesma_semente_mesma_saida(self) -> None:
        """O critério de aceite da S-27 é "mesma semente, mesmas métricas"."""
        transformacao = build_train_transform(TODAS)
        torch.manual_seed(11)
        primeira = transformacao(cell(0.7))
        torch.manual_seed(11)
        segunda = transformacao(cell(0.7))
        self.assertTrue(torch.equal(primeira, segunda))

    def test_sementes_diferentes_dao_saidas_diferentes(self) -> None:
        """Se não derem, o aumento não está sorteando nada e não está aumentando nada."""
        transformacao = build_train_transform(TODAS)
        torch.manual_seed(11)
        primeira = transformacao(cell(0.7))
        torch.manual_seed(12)
        segunda = transformacao(cell(0.7))
        self.assertFalse(torch.equal(primeira, segunda))

    def test_o_sorteio_usa_o_rng_do_torch(self) -> None:
        """O `DataLoader` semeia o RNG do torch por worker; com `random`, dois workers
        aplicariam a mesma sequência de degradações."""
        import inspect

        from chess_diagram_ocr import augment

        fonte = inspect.getsource(augment)
        self.assertNotIn("random.random()", fonte)
        self.assertIn("torch.rand", fonte)


if __name__ == "__main__":
    unittest.main()
