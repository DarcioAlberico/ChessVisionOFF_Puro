"""A medição dos leitores de marca (`medicao_de_marcas.py`): a mesma régua para o comando e a janela."""

from __future__ import annotations

import json
import threading
import unittest

import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr import medicao_de_marcas as md
from chess_diagram_ocr import teste_de_marcas as tm
from chess_diagram_ocr.atomic_io import write_image


class AmostrasTests(unittest.TestCase):
    def test_so_validacao_e_teste_fora_das_excluidas_e_a_mesma_semente_sorteia_igual(self) -> None:
        splits = {"a": "train", "b": "val", "c": "test", "d": "val", "e": "test"}
        sorteadas = md.amostras_sem_anotacao(splits, {"d"}, 10)
        self.assertEqual(sorted(sorteadas), ["b", "c", "e"])
        self.assertEqual(md.amostras_sem_anotacao(splits, (), 2, 7), md.amostras_sem_anotacao(splits, (), 2, 7))
        self.assertEqual(md.amostras_sem_anotacao(splits, (), 0), [])

    def test_anotadas_sao_as_amostras_ligadas_as_anotacoes(self) -> None:
        pasta = pasta_temporaria(self)
        arquivo = pasta / "anotacoes.json"
        self.assertEqual(md.anotadas_em(arquivo), set())
        arquivo.write_text(
            json.dumps({"versao": 1, "imagens": {"k": {"casas": {"c6": "x"}, "amostra": "a.png"}, "j": {"casas": {}}}}),
            encoding="utf-8",
        )
        self.assertEqual(md.anotadas_em(arquivo), {"a.png"})


class CompararTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        for nome, tom in (("t.png", 200), ("s1.png", 210), ("s2.png", 90)):
            write_image(self.pasta / nome, np.full((80, 80, 3), tom, np.uint8))
        self.casos = [tm.CasoDeTeste(amostra="t.png", sha256="0" * 64, casas={"c6": mc.X})]
        self.lidas: list[int] = []

    def leitor(self, resposta: dict[str, str], *, so_no_escuro: bool = False, menos_no_tom: int | None = None) -> md.Leitor:
        def ler(tabuleiro: np.ndarray) -> dict[str, str]:
            tom = int(tabuleiro.mean())
            self.lidas.append(tom)
            if (so_no_escuro and tom >= 100) or tom == menos_no_tom:
                return {}
            return dict(resposta)

        return ler

    def test_placar_e_alarmes_de_cada_leitor_na_mesma_leitura(self) -> None:
        comparacao = md.comparar(
            {"a": self.leitor({"c6": mc.X}), "b": self.leitor({"c6": mc.X}, so_no_escuro=True)},
            self.casos,
            self.pasta,
            ["s1.png", "s2.png", "sumiu.png"],
        )
        self.assertEqual(comparacao.amostras_lidas, 2, "o PNG que não abre não conta no denominador")
        self.assertEqual(sum(comparacao.placar("a").acertos.values()), 1)
        self.assertEqual(sum(comparacao.placar("b").acertos.values()), 0)
        self.assertEqual((comparacao.alarmes("a"), comparacao.alarmes("b")), (2, 1))
        self.assertEqual(len(self.lidas), 2 * 3, "cada imagem é lida uma vez e vista pelos dois leitores")

    def test_cancelada_devolve_o_parcial_marcado(self) -> None:
        parar = threading.Event()
        parar.set()
        comparacao = md.comparar({"a": self.leitor({})}, self.casos, self.pasta, ["s1.png"], cancelar=parar)
        self.assertTrue(comparacao.cancelada)
        self.assertEqual(self.lidas, [])

    def test_em_que_perde_cobre_as_tres_contas(self) -> None:
        comparacao = md.comparar(
            {"novo": self.leitor({"a1": mc.CRUZ}), "base": self.leitor({"c6": mc.X}, menos_no_tom=210)},
            self.casos,
            self.pasta,
            ["s1.png", "s2.png"],
        )
        perdas = md.em_que_perde(comparacao, "novo", "base")
        self.assertEqual(len(perdas), 3, perdas)
        self.assertEqual(md.em_que_perde(comparacao, "novo", "novo"), [])


if __name__ == "__main__":
    unittest.main()
