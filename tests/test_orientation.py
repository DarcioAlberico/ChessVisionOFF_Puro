"""A cascata de orientação, regra a regra e sem modelo (S-48).

A consequência concreta do item: a tabela de medição que morava num docstring de 112 linhas
vira teste que roda. Cada regra é exercitada isolada, com `BoardPrediction` sintético e sem
torch -- antes, perguntar "o que a legalidade diria sobre este par?" exigia rodar a inferência
duas vezes sobre uma imagem de 800×800.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.config import PIECE_CLASSES
from chess_diagram_ocr.fen_utils import fen_from_class_indices, labels_from_fen
from chess_diagram_ocr.inference import prediction_from_probs
from chess_diagram_ocr.orientation import (
    BoardCoordinates,
    ConfidenceMarginRule,
    CoordinateRule,
    OrientationEvidence,
    OrientationPolicy,
    OrientationVerdict,
    PawnPriorRule,
    SingleLegalRule,
    TightMarginFallback,
)

NUM_CLASSES = len(PIECE_CLASSES)

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3"
SEM_REI_BRANCO = "4k3/8/8/8/8/8/8/8"
PEOES_DE_PE = "4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3"


def _prediction(fen: str, confidence: float = 0.99):
    """`BoardPrediction` que decodifica para `fen` com a confiança pedida em toda casa."""
    labels = labels_from_fen(fen)
    rest = (1.0 - confidence) / (NUM_CLASSES - 1)
    probs = np.full((64, NUM_CLASSES), rest, dtype=np.float64)
    for square, label in enumerate(labels):
        probs[square, label] = confidence
    return prediction_from_probs(probs, constrained=False)


def _rotated(fen: str) -> str:
    """A FEN que sai ao ler a mesma imagem girada 180°: as 64 casas em ordem inversa."""
    return fen_from_class_indices(list(reversed(labels_from_fen(fen))))


class CoordinateRuleTests(unittest.TestCase):
    """A regra da S-45, que hoje cala em 100% dos diagramas porque nada produz o dado."""

    def setUp(self) -> None:
        self.ev = OrientationEvidence(upright=_prediction(KINGS_ONLY), flipped=_prediction(KINGS_ONLY, 0.30))

    def test_sem_coordenadas_a_regra_cala(self) -> None:
        self.assertIsNone(CoordinateRule().decide(self.ev))

    def test_oito_a_um_de_cima_para_baixo_e_ponto_de_vista_das_brancas(self) -> None:
        ev = OrientationEvidence(
            upright=self.ev.upright,
            flipped=self.ev.flipped,
            coordinates=BoardCoordinates((8, 7, 6, 5, 4, 3, 2, 1)),
        )
        verdict = CoordinateRule().decide(ev)
        assert verdict is not None
        self.assertTrue(verdict.upright)
        self.assertFalse(verdict.ambiguous)

    def test_um_a_oito_e_ponto_de_vista_das_pretas_e_ganha_da_confianca(self) -> None:
        """O caso que a S-13 deixou em aberto: a imagem é legítima nas duas interpretações.

        A confiança aponta a leitura de pé com margem folgada; as coordenadas dizem que o
        diagrama está impresso do ponto de vista das pretas, e elas vêm primeiro na cascata
        porque são evidência direta e não prior.
        """
        ev = OrientationEvidence(
            upright=self.ev.upright,
            flipped=self.ev.flipped,
            coordinates=BoardCoordinates((1, 2, 3, 4, 5, 6, 7, 8)),
        )
        resolvido = OrientationPolicy().resolve(ev)
        self.assertEqual(resolvido.rotation, 180)
        self.assertIn("pretas", resolvido.reason)

    def test_leitura_inconclusiva_das_coordenadas_faz_a_regra_calar(self) -> None:
        for ranks in ((8, 3, 6, 1), (5,), ()):
            with self.subTest(ranks=ranks):
                ev = OrientationEvidence(
                    upright=self.ev.upright, flipped=self.ev.flipped, coordinates=BoardCoordinates(ranks)
                )
                self.assertIsNone(CoordinateRule().decide(ev))


class SingleLegalRuleTests(unittest.TestCase):
    """Decide em 16% dos casos e nunca errou nos 320 tabuleiros do split de teste."""

    def test_cala_quando_as_duas_sao_legais(self) -> None:
        ev = OrientationEvidence(upright=_prediction(KINGS_ONLY), flipped=_prediction(_rotated(KINGS_ONLY)))
        self.assertIsNone(SingleLegalRule().decide(ev))

    def test_escolhe_a_legal_mesmo_contra_a_confianca(self) -> None:
        """A leitura ilegal é a mais confiante, e perde. E o par sai marcado como ambíguo."""
        ev = OrientationEvidence(
            upright=_prediction(SEM_REI_BRANCO, 0.99),
            flipped=_prediction(_rotated(KINGS_ONLY), 0.30),
        )
        verdict = SingleLegalRule().decide(ev)
        assert verdict is not None
        self.assertFalse(verdict.upright)
        self.assertEqual(verdict.reason, "única orientação legal")
        self.assertTrue(verdict.ambiguous, "legalidade e confiança discordaram e ninguém disse nada")

    def test_quando_os_sinais_concordam_nao_ha_ambiguidade(self) -> None:
        ev = OrientationEvidence(
            upright=_prediction(SEM_REI_BRANCO, 0.30),
            flipped=_prediction(_rotated(KINGS_ONLY), 0.99),
        )
        verdict = SingleLegalRule().decide(ev)
        assert verdict is not None
        self.assertFalse(verdict.upright)
        self.assertFalse(verdict.ambiguous)


class ConfidenceMarginRuleTests(unittest.TestCase):
    def test_cala_abaixo_do_limiar(self) -> None:
        ev = OrientationEvidence(upright=_prediction(KINGS_ONLY, 0.50), flipped=_prediction(KINGS_ONLY, 0.49))
        self.assertIsNone(ConfidenceMarginRule(0.20).decide(ev))

    def test_decide_acima_do_limiar_e_diz_a_margem(self) -> None:
        ev = OrientationEvidence(upright=_prediction(KINGS_ONLY, 0.99), flipped=_prediction(KINGS_ONLY, 0.30))
        verdict = ConfidenceMarginRule(0.20).decide(ev)
        assert verdict is not None
        self.assertTrue(verdict.upright)
        self.assertFalse(verdict.ambiguous)
        self.assertIn("0.690", verdict.reason)


class PawnPriorRuleTests(unittest.TestCase):
    """O regime de leitura ruim, medido no `1937 Kemeri`: a confiança empata e os peões não."""

    def test_peoes_apontam_a_orientacao_quando_a_margem_e_ruido(self) -> None:
        # 0,60 contra 0,61 e a margem de 0,01 medida no Kemeri. Nao se pode descer ate a
        # confianca real de la (~0,04) num duplo sintetico: com 0,04 no rotulo certo, a massa
        # espalhada pelas outras 12 classes passa a ser maior, e o argmax deixa de ser a FEN
        # pedida -- o teste mediria a construcao do duplo, nao a regra.
        ev = OrientationEvidence(
            upright=_prediction(PEOES_DE_PE, 0.60),
            flipped=_prediction(_rotated(PEOES_DE_PE), 0.61),
        )
        verdict = PawnPriorRule(1.0).decide(ev)
        assert verdict is not None
        self.assertTrue(verdict.upright)
        self.assertIn("peões apontam a orientação", verdict.reason)

    def test_cala_quando_nao_ha_peoes_dos_dois_lados(self) -> None:
        ev = OrientationEvidence(upright=_prediction(KINGS_ONLY, 0.61), flipped=_prediction(KINGS_ONLY, 0.60))
        self.assertIsNone(ev.pawn_gap)
        self.assertIsNone(PawnPriorRule(1.0).decide(ev))


class TightMarginFallbackTests(unittest.TestCase):
    def test_nunca_cala_e_sempre_marca_ambiguo(self) -> None:
        ev = OrientationEvidence(upright=_prediction(KINGS_ONLY, 0.61), flipped=_prediction(KINGS_ONLY, 0.60))
        verdict = TightMarginFallback().decide(ev)
        assert verdict is not None
        self.assertTrue(verdict.ambiguous)
        self.assertIn("sem peões dos dois lados", verdict.reason)


class OrientationPolicyTests(unittest.TestCase):
    def test_a_ordem_e_a_decisao_e_ela_e_trocavel(self) -> None:
        """O mesmo par de leituras, duas ordens, duas respostas.

        É o que o item existe para permitir: medir uma regra isolada é trocar a tupla, não
        recortar uma função de 112 linhas.
        """
        ev = OrientationEvidence(
            upright=_prediction(SEM_REI_BRANCO, 0.99),
            flipped=_prediction(_rotated(KINGS_ONLY), 0.30),
        )
        legalidade_primeiro = OrientationPolicy((SingleLegalRule(), ConfidenceMarginRule(0.20), TightMarginFallback()))
        confianca_primeiro = OrientationPolicy((ConfidenceMarginRule(0.20), SingleLegalRule(), TightMarginFallback()))

        self.assertEqual(legalidade_primeiro.resolve(ev).rotation, 180)
        self.assertEqual(confianca_primeiro.resolve(ev).rotation, 0)

    def test_explain_diz_o_que_cada_regra_disse_inclusive_as_que_calaram(self) -> None:
        ev = OrientationEvidence(upright=_prediction(KINGS_ONLY, 0.99), flipped=_prediction(KINGS_ONLY, 0.30))
        dito = dict(OrientationPolicy().explain(ev))

        self.assertIsNone(dito["coordenadas"], "nada produz BoardCoordinates hoje")
        self.assertIsNone(dito["legalidade"], "as duas leituras são legais: a regra tem de calar")
        self.assertIsNotNone(dito["margem de confiança"])
        # `explain` nao para na primeira que responde: o desempate tambem se pronuncia.
        self.assertIsNotNone(dito["desempate"])

    def test_uma_cascata_sem_desempate_final_falha_alto(self) -> None:
        """Silenciar aqui devolveria uma orientação inventada; falhar diz o que está errado."""
        ev = OrientationEvidence(upright=_prediction(KINGS_ONLY, 0.50), flipped=_prediction(KINGS_ONLY, 0.49))
        with self.assertRaises(ValueError):
            OrientationPolicy((SingleLegalRule(), ConfidenceMarginRule(0.20))).resolve(ev)

    def test_politica_vazia_e_recusada_na_construcao(self) -> None:
        with self.assertRaises(ValueError):
            OrientationPolicy(())

    def test_a_leitura_descartada_vem_junto(self) -> None:
        ev = OrientationEvidence(upright=_prediction(KINGS_ONLY, 0.99), flipped=_prediction(KINGS_ONLY, 0.30))
        resolvido = OrientationPolicy().resolve(ev)
        self.assertIs(resolvido.prediction, ev.upright)
        self.assertIs(resolvido.alternative, ev.flipped)
        self.assertAlmostEqual(resolvido.margin, 0.69, places=6)


class VerdictTests(unittest.TestCase):
    def test_o_veredito_e_imutavel(self) -> None:
        import dataclasses

        with self.assertRaises(dataclasses.FrozenInstanceError):
            OrientationVerdict(True, "x").upright = False  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
