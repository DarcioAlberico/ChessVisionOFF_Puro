"""A prata (S-705) e a guarda da leitura do teste por livro (S-706): identidades, três estratos, nada em comum com o ouro."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from chess_diagram_ocr.text import ouro, prata

RAIZ = Path(__file__).resolve().parents[1]
CAMINHO = RAIZ / "assets/texto_prosa/prata.json"


def _prata(**kw) -> prata.Prata:
    livros = (
        prata.LivroDaPrata("a", "eng", prata.CLEARSCAN),
        prata.LivroDaPrata("b", "deu", prata.ATE_150, 144),
        prata.LivroDaPrata("c", "spa", prata.DE_300, 300),
    )
    folhas = tuple(prata.FolhaDaPrata(x.identidade, 5, x.lingua, x.estrato) for x in livros)
    return replace(prata.Prata(prata.VERSAO, livros, folhas), **kw)


class EstratoTests(unittest.TestCase):
    def test_clearscan_pela_fonte(self) -> None:
        self.assertEqual(prata.CLEARSCAN, prata.estrato_de_producao(["Fd123", "ABCDEF+Fd4", "Times"], 600))
        self.assertNotEqual(prata.CLEARSCAN, prata.estrato_de_producao(["Fd123", "Times", "Arial"], 600))

    def test_resolucao(self) -> None:
        self.assertEqual(prata.ATE_150, prata.estrato_de_producao([], 149))
        self.assertEqual(prata.ATE_150, prata.estrato_de_producao(["GlyphLessFont"], 150))
        self.assertEqual(prata.DE_300, prata.estrato_de_producao([], 299))
        self.assertEqual(prata.DE_300, prata.estrato_de_producao([], 600))

    def test_o_meio_fica_de_fora(self) -> None:
        self.assertIsNone(prata.estrato_de_producao([], 200))
        self.assertIsNone(prata.estrato_de_producao([], 0))


class ManifestoTests(unittest.TestCase):
    def test_valido(self) -> None:
        self.assertEqual([], prata.problemas(_prata()))

    def test_acusa(self) -> None:
        p = _prata()
        casos = [
            (replace(p, versao=9), "versão"),
            (replace(p, livros=(*p.livros, prata.LivroDaPrata("", "eng", prata.DE_300))), "sem identidade"),
            (replace(p, livros=(*p.livros, p.livros[0])), "repetido"),
            (replace(p, livros=(prata.LivroDaPrata("a", "xxx", prata.CLEARSCAN), *p.livros[1:])), "língua"),
            (replace(p, livros=(prata.LivroDaPrata("a", "eng", "outro"), *p.livros[1:])), "estrato"),
            (replace(p, folhas=(*p.folhas, prata.FolhaDaPrata("z", 1, "eng", prata.DE_300))), "não lista"),
            (replace(p, folhas=(*p.folhas, prata.FolhaDaPrata("a", 6, "eng", prata.DE_300))), "estrato"),
            (replace(p, folhas=(*p.folhas, prata.FolhaDaPrata("a", 6, "por", prata.CLEARSCAN))), "e o livro não"),
            (replace(p, folhas=(*p.folhas, prata.FolhaDaPrata("a", 0, "eng", prata.CLEARSCAN))), "base 1"),
            (replace(p, folhas=(*p.folhas, p.folhas[0])), "repetida"),
            (replace(p, livros=p.livros[:2], folhas=p.folhas[:2]), "faltam estratos"),
            (replace(p, folhas=p.folhas[:2]), "sem folha"),
        ]
        for manifesto, trecho in casos:
            erros = prata.problemas(manifesto)
            self.assertTrue(any(trecho in e for e in erros), (trecho, erros))

    def test_gravar_e_carregar_voltam_iguais(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "p.json"
            prata.gravar(_prata(), caminho)
            self.assertEqual(_prata(), prata.carregar(caminho))
            self.assertNotIn(b"\r", caminho.read_bytes())


class VersionadoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.p = prata.carregar(CAMINHO)
        self.o = ouro.carregar(RAIZ / "assets/texto_prosa/ouro.json")

    def test_vale_e_nao_cruza_com_o_ouro(self) -> None:
        self.assertEqual([], prata.problemas(self.p, self.o))

    def test_so_identidades(self) -> None:
        self.assertNotIn(b".pdf", CAMINHO.read_bytes())
        for livro in self.p.livros:
            self.assertRegex(livro.identidade, r"^[0-9a-f]{16}$")

    def test_tres_estratos_e_as_trinta_folhas(self) -> None:
        self.assertEqual(set(prata.ESTRATOS), {x.estrato for x in self.p.livros})
        self.assertEqual(30, len(self.p.folhas))
        self.assertEqual(10, len(self.p.livros))

    def test_gravar_reproduz_o_arquivo(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "p.json"
            prata.gravar(self.p, caminho)
            self.assertEqual(CAMINHO.read_bytes(), caminho.read_bytes())


class LeituraDoTesteTests(unittest.TestCase):
    """A guarda que a S-702 deixou para a S-706: o livro acrescentado tem a sua própria data."""

    def setUp(self) -> None:
        m = ouro.carregar(RAIZ / "assets/texto_prosa/ouro.json")
        self.m = replace(m, primeira_leitura_do_teste=None)
        self.congelado = next(x.identidade for x in self.m.livros if x.split == ouro.TESTE)
        novo = ouro.LivroDoOuro("feedfacefeedface", ouro.RESERVA, "spa", grupo="")
        folhas = [(i, ouro.PROSA) for i in range(10, 16)]
        self.com_novo = ouro.acrescentar_ao_teste(self.m, novo, folhas, entrou_em="2026-11-10")

    def test_congelado_grava_a_data_do_manifesto(self) -> None:
        novo = ouro.registrar_leitura_do_teste(self.m, "2026-11-06", [self.congelado])
        self.assertEqual("2026-11-06", novo.primeira_leitura_do_teste)
        self.assertEqual({}, novo.leituras_dos_acrescentados)

    def test_a_primeira_data_nao_sobe(self) -> None:
        a = ouro.registrar_leitura_do_teste(self.m, "2026-11-06", [self.congelado])
        self.assertEqual("2026-11-06", ouro.registrar_leitura_do_teste(a, "2026-12-01", [self.congelado]).primeira_leitura_do_teste)

    def test_livro_que_nao_e_do_teste_levanta(self) -> None:
        dev = next(x.identidade for x in self.m.livros if x.split == ouro.DEV)
        with self.assertRaisesRegex(ValueError, "não é do teste"):
            ouro.registrar_leitura_do_teste(self.m, "2026-11-06", [dev])

    def test_data_torta_levanta(self) -> None:
        with self.assertRaises(ValueError):
            ouro.registrar_leitura_do_teste(self.m, "06/11/2026", [self.congelado])

    def test_acrescentado_grava_a_propria_linha(self) -> None:
        novo = ouro.registrar_leitura_do_teste(self.com_novo, "2026-11-10", ["feedfacefeedface"])
        self.assertEqual({"feedfacefeedface": "2026-11-10"}, novo.leituras_dos_acrescentados)
        self.assertIsNone(novo.primeira_leitura_do_teste)

    def test_leitura_antes_de_entrar_e_recusada(self) -> None:
        with self.assertRaisesRegex(ValueError, "antes de entrar"):
            ouro.registrar_leitura_do_teste(self.com_novo, "2026-11-09", ["feedfacefeedface"])
        torto = replace(self.com_novo, leituras_dos_acrescentados={"feedfacefeedface": "2026-11-09"})
        self.assertTrue(any("antes de entrar" in e for e in ouro.problemas(torto)))

    def test_leitura_no_dia_de_entrar_vale(self) -> None:
        certo = replace(self.com_novo, leituras_dos_acrescentados={"feedfacefeedface": "2026-11-10"})
        self.assertEqual([], [e for e in ouro.problemas(certo) if "entrar" in e])

    def test_leitura_de_livro_que_nao_foi_acrescentado_e_recusada(self) -> None:
        torto = replace(self.m, leituras_dos_acrescentados={self.congelado: "2026-11-10"})
        self.assertTrue(any("não é um livro acrescentado" in e for e in ouro.problemas(torto)))

    def test_o_campo_so_aparece_quando_existe(self) -> None:
        self.assertNotIn("leituras_dos_acrescentados", ouro.para_json(self.m))
        cheio = replace(self.com_novo, leituras_dos_acrescentados={"feedfacefeedface": "2026-11-10"})
        self.assertIn("leituras_dos_acrescentados", ouro.para_json(cheio))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "m.json"
            ouro.gravar(cheio, caminho)
            self.assertEqual(cheio.leituras_dos_acrescentados, ouro.carregar(caminho).leituras_dos_acrescentados)


if __name__ == "__main__":
    unittest.main()
