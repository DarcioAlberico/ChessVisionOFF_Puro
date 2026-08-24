"""O treino do classificador de caracteres: o que decide a época, e o par que sai (S-204/S-205).

**Nenhum teste daqui mede acurácia.** Um treino de três épocas sobre base sintética não tem
número que valha, e um limiar inventado sobre ele só quebraria na próxima máquina. O que se
testa é o que o item promete e que dá para conferir: que a métrica que salva a época é a que
decide e não a que lisonjeia, que o checkpoint sai com procedência e calibração, e que o par
gravado **carrega pelo carregador de verdade** -- que é o único jeito de provar que o treino não
produziu um modelo que este projeto recusa.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from chess_diagram_ocr.text.dataset import Classe
from chess_diagram_ocr.text.modelo import ModeloInvalido, carregar_classificador, limpar_cache
from chess_diagram_ocr.text.treino import (
    MINIMO_PARA_MACRO,
    Resultado,
    avaliar_split,
    gravar_checkpoint,
    logits_de,
    metrica_que_decide,
    recall_por_classe,
    treinar,
)


def base_sintetica(n_classes: int = 4, por_classe: int = 60, semente: int = 0):
    """Recortes separáveis: cada classe é um nível de cinza com ruído. O treino tem o que aprender."""
    aleatorio = np.random.default_rng(semente)
    X = np.empty((n_classes * por_classe, 32 * 32), dtype=np.uint8)
    y = np.empty(n_classes * por_classe, dtype=np.int32)
    for classe in range(n_classes):
        fatia = slice(classe * por_classe, (classe + 1) * por_classe)
        base = 30 + classe * 50
        X[fatia] = np.clip(aleatorio.normal(base, 6, (por_classe, 32 * 32)), 0, 255).astype(np.uint8)
        y[fatia] = classe
    return X, y


class MetricaTests(unittest.TestCase):
    def test_a_metrica_que_decide_nao_e_a_que_lisonjeia(self) -> None:
        """Uma classe gorda certa e uma rara errada: a acurácia sobe, a macro não.

        É o caso que o item existe para separar. Nesta base `lower_a` tem 63.055 recortes e 61
        classes têm um só -- salvar a época pela acurácia salvaria o modelo que acerta `a` e erra
        todo o resto.
        """
        n = MINIMO_PARA_MACRO * 4
        verdade = np.array([0] * n + [1] * MINIMO_PARA_MACRO, dtype=np.int64)
        logits = np.zeros((verdade.size, 2), dtype=np.float32)
        logits[:, 0] = 5.0  # tudo previsto como a classe gorda
        macro, acuracia = metrica_que_decide(logits, verdade, 2)
        self.assertAlmostEqual(acuracia, n / verdade.size, places=6)
        self.assertAlmostEqual(macro, 0.5, places=6)
        self.assertLess(macro, acuracia)

    def test_a_classe_rara_demais_nao_vota_na_epoca(self) -> None:
        """Recall de classe com 2 amostras vale 0, 50% ou 100%: é sorteio, não medição."""
        verdade = np.array([0] * 20 + [1] * 2, dtype=np.int64)
        logits = np.zeros((verdade.size, 2), dtype=np.float32)
        logits[:, 0] = 5.0
        macro, _ = metrica_que_decide(logits, verdade, 2, minimo=MINIMO_PARA_MACRO)
        self.assertEqual(macro, 1.0)  # só a classe 0 é elegível, e ela está 100% certa

    def test_a_recall_por_classe_marca_nan_onde_a_classe_nao_aparece(self) -> None:
        recalls = recall_por_classe(np.array([0, 0]), np.array([0, 0]), 3)
        self.assertEqual(recalls[0], 1.0)
        self.assertTrue(np.isnan(recalls[1]))


class TreinoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(limpar_cache)
        self.X, self.y = base_sintetica()
        indices = np.arange(self.y.size)
        self.treino = indices[indices % 5 != 0]
        self.validacao = indices[indices % 5 == 0]

    def test_o_treino_recusa_validacao_vazia(self) -> None:
        """Sem validação não há época que decida nem temperatura que calibre.

        É a forma que "o treino recusa rodar sem o split" toma aqui: um split que não deixou nada
        em validação não é um split, e treinar assim produziria pesos sem calibração -- que é
        exatamente o que a S-205 existe para impedir.
        """
        with self.assertRaises(ValueError) as erro:
            treinar(self.X, self.y, self.treino, np.array([], dtype=int), 4, epocas=1)
        self.assertIn("validação", str(erro.exception))

    def test_o_treino_recusa_treino_vazio(self) -> None:
        with self.assertRaises(ValueError):
            treinar(self.X, self.y, np.array([], dtype=int), self.validacao, 4, epocas=1)

    def test_o_treino_aprende_uma_base_separavel_e_calibra(self) -> None:
        resultado = treinar(self.X, self.y, self.treino, self.validacao, 4, epocas=3, lote=32, semente=0)
        self.assertGreater(resultado.metricas["val_macro"], 0.5)
        self.assertGreater(resultado.temperatura, 0.0)
        self.assertEqual(len(resultado.historico), 3)
        self.assertIn(resultado.melhor, {e.numero for e in resultado.historico})

    def test_a_mesma_semente_da_o_mesmo_treino(self) -> None:
        a = treinar(self.X, self.y, self.treino, self.validacao, 4, epocas=2, lote=32, semente=4)
        b = treinar(self.X, self.y, self.treino, self.validacao, 4, epocas=2, lote=32, semente=4)
        self.assertEqual(
            [(e.perda, e.macro) for e in a.historico],
            [(e.perda, e.macro) for e in b.historico],
        )

    def test_o_metadado_sai_sempre_com_temperatura(self) -> None:
        """**Treinar e não calibrar é impossível pelo caminho normal** -- é a trava da S-205.

        A calibração não é um passo que alguém possa esquecer de chamar: ela acontece dentro de
        `treinar`, com os pesos da melhor época, e o resultado já sai com ela.
        """
        X, y = base_sintetica()
        indices = np.arange(y.size)
        resultado = treinar(X, y, indices, indices, 4, epocas=1, lote=64, semente=0)

        self.assertGreater(resultado.temperatura, 0.0)
        self.assertTrue(resultado.calibracao)
        self.assertIn("antes", resultado.calibracao)
        self.assertIn("depois", resultado.calibracao)

    def test_a_falha_da_calibracao_nao_derruba_o_treino(self) -> None:
        """Um modelo salvo com temperatura 1,0 e um aviso é muito melhor que nenhum modelo.

        O que não pode acontecer é o número sair sem ninguém saber -- e por isso a falha vira
        `falhou: True` no resultado e rastro no log, e não um `.pt` calado.
        """
        from chess_diagram_ocr.text import calibracao as cal
        from chess_diagram_ocr.text import treino as tr

        def explodir(*_args: object, **_kwargs: object) -> float:
            raise RuntimeError("a algebra nao convergiu")

        original = cal.calibrar
        tr.calibracao.calibrar = explodir  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(tr.calibracao, "calibrar", original))

        X, y = base_sintetica()
        indices = np.arange(y.size)
        with self.assertLogs("chess_diagram_ocr.text.treino", level="ERROR"):
            resultado = treinar(X, y, indices, indices, 4, epocas=1, lote=64, semente=0)

        self.assertEqual(1.0, resultado.temperatura)
        self.assertTrue(resultado.calibracao["falhou"])
        self.assertTrue(resultado.estado, "os pesos da melhor época têm de sobreviver à falha")

    def test_os_logits_de_um_checkpoint_saem_crus(self) -> None:
        """A calibração precisa do que a rede produziu **antes** de dividir pela temperatura.

        `ClassificadorDeGlifo.probabilidades` já divide -- é o que a inferência quer, e o oposto
        do que a medição da S-205 precisa.
        """
        X, y = base_sintetica()
        indices = np.arange(y.size)
        resultado = treinar(X, y, indices, indices, 4, epocas=1, lote=64, semente=0)

        logits, verdade = logits_de(resultado.estado, X, y, indices, 4)

        self.assertEqual((y.size, 4), logits.shape)
        np.testing.assert_array_equal(y, verdade)
        # Logit cru não soma 1: se somasse, alguém já teria aplicado softmax no caminho.
        self.assertFalse(np.allclose(logits.sum(axis=1), 1.0))

    def test_logits_de_conjunto_vazio_nao_derruba(self) -> None:
        X, y = base_sintetica()
        logits, verdade = logits_de({}, X, y, np.empty(0, np.int64), 4)
        self.assertEqual(0, logits.shape[0])
        self.assertEqual(0, verdade.size)

    def test_a_avaliacao_de_um_conjunto_vazio_nao_derruba(self) -> None:
        resultado = treinar(self.X, self.y, self.treino, self.validacao, 4, epocas=1, lote=32)
        metricas, recalls = avaliar_split(resultado.estado, self.X, self.y, np.array([], dtype=int), 4)
        self.assertEqual(metricas["amostras"], 0)
        self.assertTrue(np.isnan(recalls).all())


class CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(limpar_cache)
        self.X, self.y = base_sintetica()
        indices = np.arange(self.y.size)
        self.resultado = treinar(
            self.X, self.y, indices[indices % 5 != 0], indices[indices % 5 == 0], 4, epocas=2, lote=32
        )
        self.classes = [
            Classe("digit_1", "1", 60, 0),
            Classe("lower_a", "a", 60, 0),
            Classe("sym_46", ".", 60, 0),
            Classe("ligature_fi", "fi", 60, 0),
        ]

    def _gravar(self, extra: dict | None = None) -> tuple[Path, Path, dict]:
        pesos, meta = self.tmp / "c.pt", self.tmp / "c.json"
        gravado = gravar_checkpoint(self.resultado, self.classes, pesos, meta, extra=extra)
        return pesos, meta, gravado

    def test_o_checkpoint_registra_a_procedencia_das_amostras(self) -> None:
        """Nesta base a procedência é 100% desconhecida, e o checkpoint tem de dizer isso.

        Não é formalidade: é o que permite a alguém, meses depois, ler o número final sabendo que
        nenhuma amostra tem registro de quem a rotulou nem de que livro veio.
        """
        _, meta, _ = self._gravar({"procedencia": {"humano": 0, "modelo": 0, "desconhecida": 240}})
        gravado = json.loads(meta.read_text(encoding="utf-8"))
        self.assertEqual(gravado["procedencia"]["desconhecida"], 240)
        self.assertEqual(gravado["procedencia"]["humano"], 0)

    def test_o_checkpoint_sai_com_calibracao_e_impressao_digital(self) -> None:
        """Os quatro campos sem os quais `modelo.py` recusa carregar."""
        _, _, meta = self._gravar()
        self.assertEqual(meta["schema_version"], 2)
        self.assertEqual(meta["num_classes"], 4)
        self.assertGreater(meta["temperatura"], 0.0)
        self.assertEqual(len(meta["modelo_sha256"]), 64)
        self.assertEqual(len(meta["classes_sha256"]), 64)
        self.assertTrue(meta["treinado_em"])

    def test_o_par_gravado_carrega_pelo_carregador_de_verdade(self) -> None:
        """A prova que fecha o item: o treino não pode produzir um par que este projeto recusa."""
        pesos, meta, _ = self._gravar()
        classificador = carregar_classificador(meta, pesos)
        self.assertEqual(classificador.meta.num_classes, 4)
        self.assertEqual(classificador.meta.alfabeto, ("1", "a", ".", "fi"))
        saida = classificador.classificar([np.full((32, 32), 80, np.uint8)])
        self.assertEqual(len(saida), 1)
        self.assertIn(saida[0][0], set(classificador.meta.alfabeto))

    def test_o_par_trocado_e_recusado(self) -> None:
        """Trocar o `.pt` por outro depois de gravado tem de levantar, e não ler outra coisa."""
        pesos, meta, _ = self._gravar()
        outro = Resultado(estado={k: v + 1.0 for k, v in self.resultado.estado.items()}, temperatura=1.5)
        gravar_checkpoint(outro, self.classes, self.tmp / "outro.pt", self.tmp / "outro.json")
        pesos.write_bytes((self.tmp / "outro.pt").read_bytes())
        limpar_cache()
        with self.assertRaises(ModeloInvalido):
            carregar_classificador(meta, pesos)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
