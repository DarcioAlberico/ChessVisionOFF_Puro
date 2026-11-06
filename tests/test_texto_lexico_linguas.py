"""As listas por língua da S-728: o que é aceito, o manifesto contra o disco, e o perfil do glifo intocado."""

from __future__ import annotations

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.cli import texto_lexico as lex
from chess_diagram_ocr.text import lexico
from chess_diagram_ocr.text.tesseract import LINGUAS


class ReguaDaListaTests(unittest.TestCase):
    def test_a_palavra_minuscula_entra_em_qualquer_alfabeto(self) -> None:
        self.assertEqual("peão", lex.aceita_na_lingua("peão", "por"))
        self.assertEqual("după", lex.aceita_na_lingua("după", "ron"))
        self.assertEqual("после", lex.aceita_na_lingua("после", "rus"))

    def test_o_lixo_que_a_lista_do_tesseract_traz_nao_entra(self) -> None:
        for token in ("Rd", "Kf", "<a", "+z", "ma", "the", "NATO", "Kasparov", "abc1", "e4", "exd5", "0-0", "Nf3"):
            with self.subTest(token=token):
                self.assertIsNone(lex.aceita_na_lingua(token, "eng"))

    def test_o_substantivo_alemao_entra_com_a_inicial_maiuscula_e_so_no_alemao(self) -> None:
        self.assertEqual("bauer", lex.aceita_na_lingua("Bauer", "deu"))
        self.assertIsNone(lex.aceita_na_lingua("Bauer", "eng"))
        self.assertIsNone(lex.aceita_na_lingua("BAUER", "deu"))

    def test_o_hifen_e_o_apostrofo_do_meio_ficam(self) -> None:
        self.assertEqual("saint-amant", lex.aceita_na_lingua("saint-amant", "fra"))
        self.assertEqual("l'homme", lex.aceita_na_lingua("l'homme", "fra"))

    def test_a_forma_decomposta_vira_composta(self) -> None:
        """O léxico consulta em NFC: `pea\\u0303o` no arquivo nunca seria achado."""
        self.assertEqual("peão", lex.aceita_na_lingua("pea\u0303o", "por"))

    def test_a_lista_e_um_conjunto_sem_repeticao(self) -> None:
        self.assertEqual({"casa"}, lex.lista_da_lingua(["casa", "casa", "Rd", "ma"], "por"))


def _execucao_falsa(comando: list[str], **_opcoes: object) -> None:
    """Os dois programas do Tesseract, de mentira: o `combine_tessdata` deixa a versão, e o `dawg2wordlist` a lista."""
    if "-u" in comando:
        Path(f"{comando[-1]}version").write_text("4.00.00alpha:x", encoding="utf-8")
    else:
        Path(comando[-1]).write_text("casa\nRd\npalavra\n", encoding="utf-8")


class EmpacotarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.instalacao = pasta_temporaria(self)
        (self.instalacao / "tessdata").mkdir()
        for lingua in LINGUAS:
            (self.instalacao / "tessdata" / f"{lingua}.traineddata").write_bytes(lingua.encode())
        self.destino = pasta_temporaria(self)

    def _empacotar(self, *, seco: bool = False) -> dict:
        with mock.patch.object(lex.subprocess, "run", side_effect=_execucao_falsa):
            return lex.empacotar_linguas(self.instalacao, self.destino, seco=seco)

    def test_grava_as_oito_e_o_manifesto_diz_o_sha_de_cada_uma(self) -> None:
        manifesto = self._empacotar()
        self.assertEqual(set(LINGUAS), set(manifesto["linguas"]))
        for lingua, dados in manifesto["linguas"].items():
            corpo = (self.destino / f"{lingua}.txt.gz").read_bytes()
            self.assertEqual(hashlib.sha256(corpo).hexdigest(), dados["sha256"])
            self.assertEqual(2, dados["entradas"])
            self.assertEqual(3, dados["linhas_no_tessdata"])
            self.assertEqual(hashlib.sha256(lingua.encode()).hexdigest(), dados["traineddata"]["sha256"])

    def test_rodar_de_novo_da_os_mesmos_bytes(self) -> None:
        self._empacotar()
        antes = {c.name: c.read_bytes() for c in self.destino.iterdir()}
        self._empacotar()
        self.assertEqual(antes, {c.name: c.read_bytes() for c in self.destino.iterdir()})

    def test_seco_nao_escreve_nada(self) -> None:
        self._empacotar(seco=True)
        self.assertEqual([], list(self.destino.iterdir()))

    def test_a_linha_de_comando_recusa_pasta_sem_tessdata(self) -> None:
        with mock.patch("builtins.print"):
            self.assertNotEqual(0, lex.main(["--linguas-de", str(self.destino)]))


class ManifestoContraODiscoTests(unittest.TestCase):
    """O que está versionado. Estes não pulam: as listas e o manifesto vão no repositório."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifesto = json.loads(lexico.MANIFESTO_DAS_LINGUAS.read_text(encoding="utf-8"))

    def test_as_oito_linguas_estao_la(self) -> None:
        self.assertEqual(set(LINGUAS), set(self.manifesto["linguas"]))
        self.assertEqual(8, len(LINGUAS))

    def test_o_sha_e_a_contagem_batem_com_o_arquivo(self) -> None:
        for lingua, dados in self.manifesto["linguas"].items():
            with self.subTest(lingua=lingua):
                caminho = lexico.PASTA_DAS_LINGUAS / dados["arquivo"]
                self.assertEqual(dados["sha256"], hashlib.sha256(caminho.read_bytes()).hexdigest())
                with gzip.open(caminho, "rt", encoding="utf-8") as fluxo:
                    self.assertEqual(dados["entradas"], sum(1 for _ in fluxo))

    def test_a_licenca_vai_ao_lado_das_listas(self) -> None:
        """A Apache-2.0 pede a cópia da licença com o que se redistribui, e `assets/` vai no bundle."""
        licenca = (lexico.PASTA_DAS_LINGUAS / "LICENSE.tessdata").read_text(encoding="utf-8")
        self.assertIn("Apache License", licenca)
        self.assertIn("Apache-2.0", self.manifesto["licenca"])

    def test_nenhuma_entrada_e_curta_ou_tem_digito(self) -> None:
        for lingua in LINGUAS:
            lista = lexico.da_lingua(lingua)
            with self.subTest(lingua=lingua):
                self.assertGreater(len(lista), 10_000)
                self.assertEqual([], [p for p in lista if sum(c.isalpha() for c in p) < lexico.MIN_TAMANHO][:5])
                self.assertEqual([], [p for p in lista if any(c.isdigit() for c in p)][:5])

    def test_cada_lista_conhece_a_propria_lingua(self) -> None:
        for lingua, palavra in (
            ("eng", "pawn"),
            ("por", "peão"),
            ("spa", "peón"),
            ("deu", "bauer"),
            ("nld", "zwart"),
            ("fra", "après"),
            ("ron", "după"),
            ("rus", "после"),
        ):
            self.assertIn(palavra, lexico.da_lingua(lingua))


class PerfilDoGlifoIntactoTests(unittest.TestCase):
    def test_nenhum_perfil_le_a_pasta_das_linguas(self) -> None:
        """O `dicionario` do glifo decide pelo perfil: a lista nova não pode entrar nele por engano."""
        for perfil, arquivos in lexico.PERFIS.items():
            for arquivo in arquivos:
                with self.subTest(perfil=perfil, arquivo=arquivo.name):
                    self.assertNotEqual(lexico.PASTA_DAS_LINGUAS, arquivo.parent)

    def test_o_perfil_padrao_nao_tem_as_palavras_so_das_listas_novas(self) -> None:
        self.assertNotIn("după", lexico.carregar())
        self.assertNotIn("после", lexico.carregar())


class DaLinguaTests(unittest.TestCase):
    def test_lingua_sem_lista_devolve_vazio(self) -> None:
        self.assertEqual(frozenset(), lexico.da_lingua("xyz"))

    def test_codigo_que_nao_e_codigo_nem_vira_caminho(self) -> None:
        for codigo in ("../acervo", "por/../eng", "", "POR", "c:\\x"):
            with self.subTest(codigo=codigo):
                self.assertEqual(frozenset(), lexico.da_lingua(codigo))


if __name__ == "__main__":
    unittest.main()
