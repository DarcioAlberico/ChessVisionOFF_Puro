"""O teste congelado das marcas (`teste_de_marcas.py`): de onde os casos vêm, o congelamento e a régua."""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr import teste_de_marcas as tm
from chess_diagram_ocr.atomic_io import write_image

FEN = "8/3k4/8/3K4/3P4/8/8/8 w - - 0 1"


def _png(caminho: Path, tom: int) -> None:
    write_image(caminho, np.full((80, 80, 3), tom, dtype=np.uint8))


class CasosTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.samples = self.pasta / "samples"
        self.samples.mkdir()
        self.labels = self.pasta / "labels.csv"
        with self.labels.open("w", encoding="utf-8", newline="") as handle:
            escritor = csv.writer(handle)
            escritor.writerow(["filename", "fen"])
            escritor.writerow(["a.png", FEN])
            escritor.writerow(["b.png", FEN])
        _png(self.samples / "a.png", 200)
        _png(self.samples / "b.png", 210)
        self.anotacoes = self.pasta / "anotacoes.json"
        self.arquivo = mc.ArquivoDeMarcas(self.anotacoes)
        self.arquivo.gravar("k-a", mc.MarcasDoDiagrama(casas={"c6": mc.X}), amostra="a.png", livro="Livro A")
        self.arquivo.gravar("k-sem", mc.MarcasDoDiagrama(casas={"a1": mc.X}), imagem="solta.png")
        self.arquivo.gravar("k-fora", mc.MarcasDoDiagrama(casas={"a1": mc.X}), amostra="nao-rotulada.png")

    def test_entra_so_a_anotacao_com_amostra_rotulada_no_disco(self) -> None:
        casos, fora = tm.casos_das_anotacoes(self.anotacoes, self.labels, self.samples)
        self.assertEqual([caso.amostra for caso in casos], ["a.png"])
        self.assertEqual(casos[0].casas, {"c6": mc.X})
        self.assertEqual(casos[0].fen, FEN)
        self.assertEqual(casos[0].livro, "Livro A")
        self.assertEqual(len(fora), 2)

    def test_acrescentar_nao_muda_o_caso_que_ja_estava(self) -> None:
        teste = self.pasta / "teste.json"
        casos, _ = tm.casos_das_anotacoes(self.anotacoes, self.labels, self.samples)
        self.assertEqual(len(tm.acrescentar(teste, casos)), 1)

        # Reanotar a mesma imagem e anotar outra: só a nova entra, e a antiga guarda o gabarito do congelamento.
        self.arquivo.gravar("k-a", mc.MarcasDoDiagrama(casas={"c6": mc.CRUZ}))
        self.arquivo.gravar("k-b", mc.MarcasDoDiagrama(casas={"h8": mc.ESTRELA_PRETA}), amostra="b.png")
        casos, _ = tm.casos_das_anotacoes(self.anotacoes, self.labels, self.samples)
        entraram = tm.acrescentar(teste, casos)
        self.assertEqual([caso.amostra for caso in entraram], ["b.png"])
        congelados = {caso.amostra: caso.casas for caso in tm.ler_teste(teste)}
        self.assertEqual(congelados, {"a.png": {"c6": mc.X}, "b.png": {"h8": mc.ESTRELA_PRETA}})
        self.assertEqual(tm.acrescentar(teste, casos), [])

    def test_amostra_trocada_depois_do_congelamento_e_acusada(self) -> None:
        teste = self.pasta / "teste.json"
        casos, _ = tm.casos_das_anotacoes(self.anotacoes, self.labels, self.samples)
        tm.acrescentar(teste, casos)
        self.assertEqual(tm.conferir_amostras(tm.ler_teste(teste), self.samples), [])
        _png(self.samples / "a.png", 90)
        self.assertEqual(len(tm.conferir_amostras(tm.ler_teste(teste), self.samples)), 1)

    def test_teste_ilegivel_levanta_em_vez_de_virar_vazio(self) -> None:
        teste = self.pasta / "teste.json"
        teste.write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            tm.ler_teste(teste)
        with self.assertRaises(ValueError):
            tm.acrescentar(teste, [])
        self.assertEqual(tm.ler_teste(self.pasta / "nao-existe.json"), [])


class PlacarTests(unittest.TestCase):
    def _caso(self, casas: dict[str, str]) -> tm.CasoDeTeste:
        return tm.CasoDeTeste(amostra="a.png", sha256="0" * 64, casas=casas)

    def test_acerto_falta_falso_e_troca_de_tipo(self) -> None:
        caso = self._caso({"c6": mc.X, "d6": mc.ESTRELA_PRETA, "e6": mc.BOLINHA_PRETA})
        placar = tm.pontuar([caso], {"a.png": {"c6": mc.X, "d6": mc.BOLINHA_PRETA, "h1": mc.CRUZ}})
        self.assertEqual(placar.acertos[mc.X], 1)
        self.assertEqual(placar.faltas[mc.ESTRELA_PRETA], 1)
        self.assertEqual(placar.faltas[mc.BOLINHA_PRETA], 1)
        self.assertEqual(placar.falsos[mc.BOLINHA_PRETA], 1)
        self.assertEqual(placar.falsos[mc.CRUZ], 1)
        self.assertEqual(placar.trocas[(mc.ESTRELA_PRETA, mc.BOLINHA_PRETA)], 1)
        self.assertEqual(placar.trocas[(tm.SEM_MARCA, mc.CRUZ)], 1)
        self.assertEqual(placar.marcas, 3)
        self.assertAlmostEqual(placar.revocacao, 1 / 3)
        self.assertAlmostEqual(placar.precisao, 1 / 3)
        self.assertEqual((placar.diagramas, placar.diagramas_exatos, placar.diagramas_com_falso), (1, 0, 1))

    def test_leitor_que_nao_leu_o_diagrama_perde_as_marcas_dele(self) -> None:
        placar = tm.pontuar([self._caso({"c6": mc.X})], {})
        self.assertEqual((placar.acertos[mc.X], placar.faltas[mc.X]), (0, 1))
        self.assertEqual(placar.diagramas_exatos, 0)

    def test_outra_fica_fora_da_conta(self) -> None:
        placar = tm.pontuar([self._caso({"c6": mc.OUTRA})], {"a.png": {}})
        self.assertEqual((placar.marcas, placar.casas_ignoradas, placar.diagramas_exatos), (0, 1, 1))

    def test_tipos_pontuados_sao_os_da_anotacao_sem_outra(self) -> None:
        self.assertNotIn(mc.OUTRA, tm.TIPOS_PONTUADOS)
        self.assertEqual(set(tm.TIPOS_PONTUADOS) | {mc.OUTRA}, set(mc.TIPOS_DE_CASA))


if __name__ == "__main__":
    unittest.main()
