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

import json
import pickle
import tempfile
import unittest
from dataclasses import asdict, fields, replace
from pathlib import Path

import torch

from chess_diagram_ocr.augment import (
    DEFAULT_AUGMENT,
    TIPOS_DE_MARCA,
    AugmentConfig,
    MarcaEmVazia,
    RandomHatch,
    RandomHorizontalFlipCell,
    RandomInvert,
    RandomPaper,
    RandomSpeckle,
    RandomStroke,
    build_augmentations,
    build_marca,
    desenhar_marca,
    from_letters,
    from_metadado,
    regime_of_checkpoint,
    stroke,
)
from chess_diagram_ocr.training import build_train_transform

TODAS = AugmentConfig(hflip=0.5, hatch=0.5, speckle=0.5, paper=0.5, invert=0.5, stroke=0.5)


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
            AugmentConfig(stroke=0.5).version,
        }
        self.assertEqual(len(versoes), 7, f"versões colidiram: {versoes}")

    def test_o_jitter_e_o_afim_tambem_mudam_a_versao(self) -> None:
        """Dois regimes que treinam modelos diferentes saíam ambos como `aug0` (S-376)."""
        versoes = {
            AugmentConfig().version,
            AugmentConfig(jitter=0.0).version,
            AugmentConfig(affine=0.0).version,
            AugmentConfig(blur=0.0).version,
        }
        self.assertEqual(len(versoes), 4, f"versões colidiram: {versoes}")

    def test_a_assinatura_do_padrao_nao_muda(self) -> None:
        """Os checkpoints que existem foram gravados com `aug0` e `augmhsp`: o sufixo só
        aparece quando algum genérico sai do padrão, ou a comparação histórica se perde."""
        self.assertEqual(AugmentConfig().version, "aug0")
        self.assertEqual(AugmentConfig(hflip=0.5, hatch=0.3, speckle=0.25, paper=0.3).version, "augmhsp")
        self.assertEqual(
            AugmentConfig(hflip=0.5, hatch=0.3, speckle=0.25, paper=0.3, stroke=0.3).version, "augmhspe"
        )

    def test_o_raio_do_traco_entra_quando_o_traco_esta_ligado(self) -> None:
        """Como o período da hachura: raio ou margem diferentes são outro regime (C4)."""
        self.assertNotEqual(AugmentConfig(stroke=0.3).version, AugmentConfig(stroke=0.3, stroke_px=(1, 2)).version)
        self.assertNotEqual(AugmentConfig(stroke=0.3).version, AugmentConfig(stroke=0.3, stroke_margin_px=0).version)
        self.assertEqual(AugmentConfig(stroke_px=(1, 2)).version, "aug0")

    def test_o_periodo_da_hachura_entra_quando_a_hachura_esta_ligada(self) -> None:
        """Período diferente é regime diferente; com a hachura desligada ele não diz nada."""
        self.assertNotEqual(
            AugmentConfig(hatch=0.3).version,
            AugmentConfig(hatch=0.3, hatch_period_px=(2, 6)).version,
        )
        self.assertEqual(AugmentConfig(hatch_period_px=(2, 6)).version, "aug0")

    def test_a_versao_entra_nos_metadados_do_checkpoint(self) -> None:
        """Sem isso, comparar dois modelos pode estar comparando dois regimes de aumento.

        Pelos metadados do plano (`_optim_metadata`), que `Trainer.prepare` espalha nos do
        checkpoint: era uma varredura do fonte de `prepare`, e um comentário com o nome bastava
        para ela passar.
        """
        from chess_diagram_ocr.model import ArchConfig
        from chess_diagram_ocr.training import OptimPlan, _optim_metadata

        metadados = _optim_metadata(OptimPlan(augment=TODAS), ArchConfig())
        self.assertEqual(metadados["augment_version"], TODAS.version)
        self.assertEqual(metadados["augment"], asdict(TODAS))

    def test_a_ordem_e_a_de_uma_pagina_real(self) -> None:
        """O papel amarela antes de a tinta da hachura ser impressa; a granulação é do scanner."""
        tipos = [type(etapa).__name__ for etapa in build_augmentations(TODAS)]
        self.assertEqual(
            tipos,
            ["RandomHorizontalFlipCell", "RandomInvert", "RandomStroke", "RandomPaper", "RandomHatch", "RandomSpeckle"],
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


def outlined_piece(gap: int = 6, stroke_px: int = 2) -> torch.Tensor:
    """Um "contorno" sintético: anel de tinta de `stroke_px` com um vão claro de `gap` px.

    É o que uma peça branca é para o modelo -- tinta em volta, papel dentro. O rótulo só
    sobrevive enquanto o vão sobreviver.
    """
    x = torch.ones(1, 64, 64)
    lado = gap + 2 * stroke_px
    inicio = (64 - lado) // 2
    fim = inicio + lado
    x[:, inicio:fim, inicio:fim] = 0.0
    x[:, inicio + stroke_px : fim - stroke_px, inicio + stroke_px : fim - stroke_px] = 1.0
    return x


class StrokeTests(unittest.TestCase):
    """C4 do ciclo 2 OCR/UI: espessura do traço, o eixo que os outros aumentos não cobrem."""

    def test_engrossar_escurece_e_afinar_clareia(self) -> None:
        peca = outlined_piece()
        grossa = stroke(peca, 1, engrossar=True)
        fina = stroke(peca, 1, engrossar=False)
        self.assertLess(float(grossa.mean()), float(peca.mean()))
        self.assertGreater(float(fina.mean()), float(peca.mean()))

    def test_um_pixel_preserva_o_vao_do_contorno(self) -> None:
        """A peça branca continua branca: o interior do contorno continua claro com 1 px."""
        peca = outlined_piece(gap=6, stroke_px=2)
        grossa = stroke(peca, 1, engrossar=True)
        # O anel vai de 27 a 36 e o vão de 29 a 34; dilatado 1 px, o vão fica de 30 a 33.
        centro = grossa[0, 30:34, 30:34]
        self.assertTrue(bool((centro == 1.0).all()), "o vão de 6 px fechou com 1 px")
        self.assertTrue(bool((grossa[0, 29, 29:35] == 0.0).all()), "o anel não engrossou para dentro")

    def test_a_sabotagem_dois_pixels_fecha_o_contorno(self) -> None:
        """O motivo de `stroke_px=(1, 1)`: a 2 px um vão pequeno fecha e o rótulo vira preta.

        Medido em casas reais (docstring de `AugmentConfig.stroke_px`); aqui o vão de 4 px é
        o caso sintético mínimo que reproduz o fechamento.
        """
        peca = outlined_piece(gap=4, stroke_px=2)
        grossa = stroke(peca, 2, engrossar=True)
        # Anel de 28 a 35, vão de 30 a 33: dilatado 2 px, não sobra pixel claro.
        self.assertTrue(bool((grossa[0, 28:36, 28:36] == 0.0).all()), "2 px deveriam fechar o vão de 4 px")
        self.assertEqual(AugmentConfig().stroke_px, (1, 1))

    def test_a_borda_da_casa_fica_como_esta(self) -> None:
        """As linhas da grade e a hachura da casa vizinha não são glifo."""
        x = torch.ones(1, 64, 64)
        x[:, 0, :] = 0.0  # linha da grade no alto
        x[:, :, 63] = 0.0  # e à direita
        grossa = stroke(x, 1, engrossar=True, margin=3)
        self.assertTrue(torch.equal(grossa[:, :3, :], x[:, :3, :]))
        self.assertTrue(torch.equal(grossa[:, :, 61:], x[:, :, 61:]))
        # Sem margem a grade engrossaria: é o que a margem existe para impedir.
        sem_margem = stroke(x, 1, engrossar=True, margin=0)
        self.assertFalse(torch.equal(sem_margem[:, :3, :], x[:, :3, :]))

    def test_raio_zero_e_identidade(self) -> None:
        peca = outlined_piece()
        self.assertTrue(torch.equal(stroke(peca, 0, engrossar=True), peca))

    def test_o_modulo_sorteia_raio_e_sentido_com_o_rng_do_torch(self) -> None:
        torch.manual_seed(7)
        saidas = {float(RandomStroke(1.0)(outlined_piece()).mean()) for _ in range(12)}
        self.assertGreaterEqual(len(saidas), 2, "nunca variou o sentido")
        self.assertEqual(RandomStroke(1.0).px, (1, 1))

    def test_probabilidade_zero_e_identidade(self) -> None:
        x = outlined_piece()
        self.assertTrue(torch.equal(RandomStroke(0.0)(x), x))


class BehaviourTests(unittest.TestCase):
    def test_probabilidade_zero_e_identidade(self) -> None:
        x = cell()
        for classe in (RandomHorizontalFlipCell, RandomHatch, RandomSpeckle, RandomPaper, RandomInvert, RandomStroke):
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

    def test_o_sorteio_usa_so_o_rng_do_torch(self) -> None:
        """O `DataLoader` semeia o RNG do torch por worker; com `random`, dois workers
        aplicariam a mesma sequência de degradações.

        Mesma semente do torch e sementes diferentes do `random` e do numpy: a saída não pode
        mudar. Era uma busca de `torch.rand` no texto do módulo (S-870), e um sorteio por
        `random.uniform` ou `np.random` passava por ela. Vinte sementes para que cada etapa
        de probabilidade 0,5 dispare algumas vezes; a marca entra com probabilidade 1.
        """
        import random

        import numpy as np

        transformacao = build_train_transform(TODAS)
        marca = build_marca(replace(TODAS, marca=1.0))
        assert marca is not None
        for semente in range(20):
            saidas = []
            for alheia in (1, 2):
                random.seed(alheia)
                np.random.seed(alheia)
                torch.manual_seed(semente)
                saidas.append((transformacao(cell(0.7)), marca(cell(0.9))))
            with self.subTest(semente=semente):
                self.assertTrue(torch.equal(saidas[0][0], saidas[1][0]), "a pipeline sorteou fora do torch")
                self.assertTrue(torch.equal(saidas[0][1], saidas[1][1]), "a marca sorteou fora do torch")


class MarcaTests(unittest.TestCase):
    """A marca de casa sintética: tinta sobre a casa vazia, com o rótulo continuando vazio."""

    def test_desligada_por_padrao_e_fora_da_versao(self) -> None:
        self.assertIsNone(build_marca(DEFAULT_AUGMENT))
        self.assertEqual(DEFAULT_AUGMENT.version, "aug0")

    def test_a_letra_x_liga_a_marca_e_entra_na_versao(self) -> None:
        config = from_letters("x")
        self.assertEqual(config.marca, 0.20)
        self.assertEqual(config.version, "augx")
        self.assertEqual(from_letters(config.version), config)
        self.assertIsInstance(build_marca(config), MarcaEmVazia)

    def test_cada_marca_cheia_escurece_o_centro_e_deixa_a_borda(self) -> None:
        for tipo in ("estrela", "x", "ponto", "cruz"):
            with self.subTest(tipo=tipo):
                x = desenhar_marca(cell(0.9), tipo, largura=0.5, tinta=0.0)
                self.assertLess(float(x[0, 26:38, 26:38].mean()), 0.6)
                self.assertTrue(torch.equal(x[0, :6, :], cell(0.9)[0, :6, :]), "a marca vazou para a borda da casa")
                self.assertGreaterEqual(float(x.min()), 0.0)

    def test_as_formas_sao_distintas(self) -> None:
        """Tipos que saíssem iguais seriam um tipo só, com vários nomes."""
        desenhos = [desenhar_marca(cell(1.0), tipo, largura=0.6) for tipo in TIPOS_DE_MARCA]
        for i in range(len(desenhos)):
            for j in range(i + 1, len(desenhos)):
                self.assertGreater(float((desenhos[i] - desenhos[j]).abs().mean()), 0.02)

    def test_o_x_e_a_cruz_girada(self) -> None:
        x = desenhar_marca(cell(1.0), "x", largura=0.6)
        self.assertLess(float(x[0, 20, 20]), 0.5, "o X tem tinta na diagonal")
        self.assertGreater(float(x[0, 32, 14]), 0.9, "e não no meio da borda, onde a cruz teria")
        cruz = desenhar_marca(cell(1.0), "cruz", largura=0.6)
        self.assertLess(float(cruz[0, 32, 14]), 0.5)

    def test_tipo_desconhecido_e_recusado(self) -> None:
        with self.assertRaises(ValueError):
            desenhar_marca(cell(), "raio", largura=0.5)

    def test_a_marca_oca_tem_borda_de_tinta_e_miolo_de_papel(self) -> None:
        """O miolo cobre a hachura: é o que separa a bolinha oca de um anel transparente."""
        for tipo in ("oca", "estrela-branca"):
            with self.subTest(tipo=tipo):
                x = desenhar_marca(cell(0.4), tipo, largura=0.6, espessura=0.06, tinta=0.0, papel=0.95)
                self.assertAlmostEqual(float(x[0, 32, 32]), 0.95, places=3)
                self.assertLess(float(x.min()), 0.05, "e tem traço de tinta em volta")
                self.assertAlmostEqual(float(x[0, 2, 2]), 0.4, places=3, msg="sem tocar o fundo de fora")

    def test_a_reta_atravessa_a_casa_e_o_tracejo_abre_falhas(self) -> None:
        cheia = desenhar_marca(cell(1.0), "reta", largura=1.0, espessura=0.1, tinta=0.0)
        self.assertLess(float(cheia[0, 32, :].max()), 0.01, "a horizontal vai de uma borda à outra")
        tracejada = desenhar_marca(cell(1.0), "reta", largura=1.0, espessura=0.1, tinta=0.0, tracejo=0.25)
        self.assertGreater(float(tracejada[0, 32, :].max()), 0.99, "e a tracejada tem falhas")
        self.assertLess(float(tracejada[0, 32, :].min()), 0.01)

    def test_a_seta_tem_a_ponta_mais_larga_que_a_haste(self) -> None:
        x = desenhar_marca(cell(1.0), "seta", largura=0.4, espessura=0.04, tinta=0.0)
        na_cabeca = int((x[0, :, 8] < 0.5).sum())
        na_haste = int((x[0, :, 3] < 0.5).sum())
        self.assertGreater(na_cabeca, 2 * na_haste)
        self.assertGreater(na_haste, 0, "a haste vem de fora da casa")
        self.assertGreater(float(x[0, 32, 40]), 0.99, "e nada passa da ponta")

    def test_a_moldura_e_vazada(self) -> None:
        x = desenhar_marca(cell(1.0), "moldura", largura=0.8, espessura=0.08, tinta=0.0)
        self.assertGreater(float(x[0, 32, 32]), 0.99)
        self.assertLess(float(x[0, 32, 8]), 0.01)

    def test_todo_tipo_sorteado_fica_no_intervalo_e_muda_a_casa(self) -> None:
        marca = MarcaEmVazia(1.0)
        torch.manual_seed(11)
        for _ in range(200):
            x = marca(cell(0.8))
            self.assertGreaterEqual(float(x.min()), 0.0)
            self.assertLessEqual(float(x.max()), 1.0)

    def test_probabilidade_zero_e_identidade(self) -> None:
        x = cell(0.8)
        self.assertTrue(torch.equal(MarcaEmVazia(0.0)(x), x))

    def test_mesma_semente_mesma_marca(self) -> None:
        marca = MarcaEmVazia(1.0)
        torch.manual_seed(5)
        primeira = marca(cell(0.9))
        torch.manual_seed(5)
        self.assertTrue(torch.equal(primeira, marca(cell(0.9))))

    def test_e_piclavel(self) -> None:
        marca = pickle.loads(pickle.dumps(MarcaEmVazia(0.15)))
        self.assertEqual(marca.p, 0.15)


class RegimeDoCheckpointTests(unittest.TestCase):
    """O checkpoint guarda o regime inteiro, e não só a letra (S-839).

    A letra é um nome curto, e perde informação: `AugmentConfig(hatch=0.9)` e o `hatch=0.3` que
    `from_letters("h")` devolve saem os dois `augh`. Retreinar "no regime do checkpoint" a partir
    da letra treinava noutro regime e gravava a mesma letra -- a classe do incidente `augx`.
    """

    REGIMES = (
        AugmentConfig(),
        TODAS,
        AugmentConfig(hatch=0.9),
        AugmentConfig(hatch=0.3, hatch_period_px=(2, 6)),
        AugmentConfig(stroke=0.3, stroke_px=(1, 2), stroke_margin_px=0),
        AugmentConfig(jitter=0.0, affine=0.5, blur=0.1, marca=0.2),
    )

    def _gravado(self, pasta: Path, config: AugmentConfig) -> Path:
        """Um `.pt` com os metadados de regime que o treino grava."""
        from chess_diagram_ocr.checkpoint import save_checkpoint
        from chess_diagram_ocr.model import ArchConfig
        from chess_diagram_ocr.training import OptimPlan, _optim_metadata

        caminho = pasta / "m.pt"
        metadados = _optim_metadata(OptimPlan(augment=config), ArchConfig())
        save_checkpoint(caminho, {"w": torch.zeros(1)}, metadata=metadados)
        return caminho

    def test_o_dicionario_reconstroi_o_regime_exato(self) -> None:
        for config in self.REGIMES:
            with self.subTest(config=config):
                self.assertEqual(from_metadado(asdict(config)), config)
                # Por JSON as tuplas voltam como listas, e o regime tem de sair o mesmo.
                self.assertEqual(from_metadado(json.loads(json.dumps(asdict(config)))), config)

    def test_todo_campo_fora_do_padrao_volta(self) -> None:
        """Cada campo do regime, um por vez, fora do padrão: nenhum pode voltar no padrão."""
        for campo in fields(AugmentConfig):
            padrao = getattr(DEFAULT_AUGMENT, campo.name)
            if isinstance(padrao, tuple):
                outro: object = tuple(v + 1 for v in padrao)
            elif isinstance(padrao, int):
                outro = padrao + 1
            else:
                outro = padrao + 0.125
            config = replace(DEFAULT_AUGMENT, **{campo.name: outro})
            with self.subTest(campo=campo.name):
                self.assertEqual(from_metadado(asdict(config)), config)

    def test_campo_desconhecido_e_recusado(self) -> None:
        """Um regime de um código mais novo traz transformação que este não sabe aplicar."""
        with self.assertRaises(ValueError):
            from_metadado({**asdict(AugmentConfig()), "dobra": 0.5})

    def test_o_checkpoint_devolve_o_regime_que_o_treino_gravou(self) -> None:
        for config in self.REGIMES:
            with self.subTest(config=config), tempfile.TemporaryDirectory() as tmp:
                caminho = self._gravado(Path(tmp), config)
                self.assertEqual(regime_of_checkpoint(caminho), config)

    def test_hachura_forte_nao_volta_como_a_da_letra(self) -> None:
        """O par que a letra confundia: os dois são `augh`."""
        self.assertEqual(AugmentConfig(hatch=0.9).version, from_letters("h").version)
        with tempfile.TemporaryDirectory() as tmp:
            regime = regime_of_checkpoint(self._gravado(Path(tmp), AugmentConfig(hatch=0.9)))
        self.assertIsNotNone(regime)
        assert regime is not None
        self.assertEqual(regime.hatch, 0.9)

    def test_sufixo_que_a_letra_nao_honra_e_recusado(self) -> None:
        for texto in ("augh-j0", "aug0-b0.1", "auge-e1x2m3", "h-t2x6"):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                from_letters(texto)

    def test_arquivo_ausente_e_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(regime_of_checkpoint(Path(tmp) / "nao-existe.pt"))

    def test_arquivo_truncado_levanta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = self._gravado(Path(tmp), TODAS)
            caminho.write_bytes(caminho.read_bytes()[:200])
            with self.assertRaises(ValueError):
                regime_of_checkpoint(caminho)

    def test_checkpoint_antigo_e_lido_pela_letra_com_aviso(self) -> None:
        from chess_diagram_ocr.checkpoint import save_checkpoint

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "antigo.pt"
            save_checkpoint(caminho, {"w": torch.zeros(1)}, metadata={"augment_version": "augmhsp"})
            with self.assertLogs("chess_diagram_ocr.augment", "WARNING"):
                regime = regime_of_checkpoint(caminho)
        self.assertEqual(regime, AugmentConfig(hflip=0.5, hatch=0.30, speckle=0.25, paper=0.30))

    def test_checkpoint_anterior_a_s40_e_o_generico_com_aviso(self) -> None:
        from chess_diagram_ocr.checkpoint import save_checkpoint

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "pre_s40.pt"
            save_checkpoint(caminho, {"w": torch.zeros(1)}, metadata={})
            with self.assertLogs("chess_diagram_ocr.augment", "WARNING"):
                self.assertEqual(regime_of_checkpoint(caminho), AugmentConfig())


if __name__ == "__main__":
    unittest.main()
