"""A temperatura, e a curva que diz se ela serviu (S-205).

O defeito que o item existe para impedir é de processo: **o retreino apaga a calibração e
ninguém nota**, porque o metadado continua trazendo o número antigo. Os testes daqui cobrem as
duas metades disso -- que não há caminho que produza pesos sem temperatura, e que a curva diz o
que a temperatura sozinha não diz.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.text import calibracao as cal


def _logits_otimistas(n: int = 400, classes: int = 3, folga: float = 6.0, errados: int = 200):
    """Confiança muito acima do acerto real: metade erra com a mesma folga."""
    aleatorio = np.random.default_rng(0)
    verdade = aleatorio.integers(0, classes, n)
    logits = aleatorio.normal(0, 1, (n, classes)).astype(np.float32)
    logits[np.arange(n), verdade] += folga
    logits[:errados] = logits[:errados][:, ::-1]
    return logits, verdade


class TemperaturaTests(unittest.TestCase):
    def test_a_temperatura_encolhe_a_confianca_de_um_modelo_otimista(self) -> None:
        logits, verdade = _logits_otimistas()
        self.assertGreater(cal.calibrar(logits, verdade), 1.0)

    def test_o_conjunto_vazio_devolve_um_em_vez_de_levantar(self) -> None:
        """Calibrar sem dado é o caso de um split sem validação, e quem trata isso é o treino."""
        self.assertEqual(1.0, cal.calibrar(np.empty((0, 3), np.float32), np.empty(0, np.int64)))

    def test_temperatura_nao_positiva_e_recusada_em_vez_de_virar_nan(self) -> None:
        with self.assertRaises(ValueError):
            cal.probabilidades(np.zeros((2, 3), np.float32), 0.0)

    def test_a_frase_da_calibracao_diz_a_direcao(self) -> None:
        self.assertIn("reduz", cal.esperanca_de_confianca(2.5))
        self.assertIn("aumenta", cal.esperanca_de_confianca(0.5))
        self.assertIn("calibrado", cal.esperanca_de_confianca(1.0))


class CurvaTests(unittest.TestCase):
    """A curva de confiabilidade: o que ele disse, contra o que ele acertou."""

    def test_o_modelo_perfeito_tem_ece_zero(self) -> None:
        """Diz 1,0 e acerta 1,0 -- e a faixa do topo é fechada dos dois lados de propósito."""
        verdade = np.array([0, 1, 2, 0, 1, 2])
        logits = np.full((6, 3), -50.0, dtype=np.float32)
        logits[np.arange(6), verdade] = 50.0

        self.assertAlmostEqual(0.0, cal.ece(logits, verdade), places=6)
        self.assertEqual(1, len(cal.curva(logits, verdade)))

    def test_a_faixa_vazia_nao_entra_na_conta(self) -> None:
        """Faixa sem amostra não é desvio zero: ela não existe, e somá-la diluiria o ECE."""
        verdade = np.array([0, 1])
        logits = np.array([[9.0, -9.0], [-9.0, 9.0]], dtype=np.float32)
        self.assertEqual(1, len(cal.curva(logits, verdade, faixas=15)))

    def test_o_ece_soma_o_desvio_de_cada_faixa(self) -> None:
        """Metade das amostras diz ~1,0 e erra: o desvio daquela faixa é o que o ECE mostra."""
        logits, verdade = _logits_otimistas()
        medido = cal.ece(logits, verdade)
        linhas = cal.curva(logits, verdade)
        total = sum(f.amostras for f in linhas)
        esperado = sum(f.amostras * f.desvio for f in linhas) / total
        self.assertAlmostEqual(esperado, medido, places=9)

    def test_o_ece_por_faixa_nao_e_dominado_pela_faixa_mais_cheia(self) -> None:
        """**É a mesma lição da macro contra a acurácia**, aqui aplicada à calibração.

        Uma faixa enorme e perfeita mais uma faixa pequena e péssima: o ponderado quase não vê a
        segunda, e é ela que o programa consulta.
        """
        verdade = np.zeros(1000, dtype=np.int64)
        logits = np.zeros((1000, 2), dtype=np.float32)
        logits[:990, 0] = 50.0  # 990 amostras a ~1,0 de confiança, todas certas
        logits[:990, 1] = -50.0
        logits[990:, 0] = 0.6  # 10 amostras a ~0,55, e metade errada
        logits[990:, 1] = 0.0
        verdade[995:] = 1

        self.assertLess(cal.ece(logits, verdade), 0.01)
        self.assertGreater(cal.ece_por_faixa(logits, verdade), 0.05)

    def test_curva_de_conjunto_vazio_e_vazia_e_o_ece_e_zero(self) -> None:
        vazio, verdade = np.empty((0, 3), np.float32), np.empty(0, np.int64)
        self.assertEqual([], cal.curva(vazio, verdade))
        self.assertEqual(0.0, cal.ece(vazio, verdade))
        self.assertEqual(0.0, cal.ece_por_faixa(vazio, verdade))


class RelatorioTests(unittest.TestCase):
    """O artefato: antes e depois, e nunca só o depois."""

    def test_o_relatorio_traz_a_curva_antes_e_depois(self) -> None:
        logits, verdade = _logits_otimistas()
        relatorio = cal.relatorio(logits, verdade, cal.calibrar(logits, verdade))

        for momento in ("antes", "depois"):
            with self.subTest(momento=momento):
                self.assertIn("ece", relatorio[momento])
                self.assertIn("ece_por_faixa", relatorio[momento])
                self.assertTrue(relatorio[momento]["curva"])
        self.assertEqual(1.0, relatorio["antes"]["temperatura"])

    def test_a_calibracao_de_um_modelo_otimista_baixa_o_ece(self) -> None:
        logits, verdade = _logits_otimistas()
        relatorio = cal.relatorio(logits, verdade, cal.calibrar(logits, verdade))
        self.assertLess(relatorio["depois"]["ece"], relatorio["antes"]["ece"])

    def test_a_leitura_nomeia_a_regua_que_decide_e_a_que_lisonjeia(self) -> None:
        frase = cal.leitura(1.5, 0.11, 0.10, ponderado=(0.004, 0.003))
        self.assertIn("por faixa", frase)
        self.assertIn("ponderado", frase)
        self.assertIn("domina", frase)

    def test_a_leitura_diz_quando_o_ece_piora(self) -> None:
        """A temperatura minimiza a NLL, não o ECE. Quando as duas discordam, quem lê precisa saber."""
        frase = cal.leitura(1.5, 0.10, 0.14)
        self.assertIn("subiu", frase)
        self.assertIn("NLL", frase)


class CurvaPublicadaTests(unittest.TestCase):
    """A curva que está em `docs/metrics/` descreve o modelo que está em `models/`?

    **É a trava de processo da S-205 posta em teste.** O defeito que o item existe para impedir é
    o retreino que apaga a calibração sem ninguém notar; se este teste falhar, o relatório
    publicado está descrevendo outro modelo.
    """

    RAIZ = Path(__file__).resolve().parents[1]
    METADADO = RAIZ / "models" / "char_meta.json"

    def _relatorio(self) -> dict:
        achados = sorted((self.RAIZ / "docs" / "metrics").glob("texto_ece_*.json"))
        if not achados:
            self.skipTest("a curva ainda não foi medida: rode `cvoff-texto-train --so-calibracao`")
        return json.loads(achados[-1].read_text(encoding="utf-8"))

    def test_a_temperatura_corresponde_ao_modelo_gravado(self) -> None:
        relatorio = self._relatorio()
        if not self.METADADO.exists():  # pragma: no cover - clone sem o metadado
            self.skipTest("sem models/char_meta.json")
        publicado = json.loads(self.METADADO.read_text(encoding="utf-8"))

        self.assertEqual(relatorio["modelo_sha256"], publicado["modelo_sha256"])
        self.assertAlmostEqual(relatorio["temperatura_publicada"], publicado["temperatura"], places=6)

    def test_a_temperatura_refeita_confere_com_a_publicada(self) -> None:
        """Refazer a calibração sobre a mesma validação tem de dar o mesmo número.

        Divergir aqui quer dizer que o metadado descreve um modelo que não é o do lado -- ou que
        o split mudou debaixo dele.
        """
        relatorio = self._relatorio()
        self.assertAlmostEqual(
            relatorio["temperatura_publicada"], relatorio["temperatura_refeita"], places=2
        )

    def test_o_relatorio_publicado_traz_as_duas_reguas_nos_dois_momentos(self) -> None:
        relatorio = self._relatorio()
        for momento in ("antes", "depois"):
            for regua in ("ece", "ece_por_faixa"):
                with self.subTest(momento=momento, regua=regua):
                    self.assertIn(regua, relatorio[momento])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
