"""As marcas de um diagrama (`marcas_de_casa.py`): o vocabulário, as operações e o arquivo."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr.fen_utils import square_name


class CasasTests(unittest.TestCase):
    def test_indice_da_casa_e_o_inverso_de_square_name(self) -> None:
        for indice in range(64):
            self.assertEqual(mc.indice_da_casa(square_name(indice)), indice)
        for invalida in ("", "i1", "a9", "a", "e44"):
            with self.assertRaises(ValueError):
                mc.indice_da_casa(invalida)

    def test_mesma_marca_alterna_e_outra_marca_troca(self) -> None:
        marcas = mc.MarcasDoDiagrama().alternar_casa(mc.ESTRELA_PRETA, "f6")
        self.assertEqual(marcas.casas, {"f6": mc.ESTRELA_PRETA})
        self.assertEqual(marcas.alternar_casa(mc.BOLINHA_BRANCA, "f6").casas, {"f6": mc.BOLINHA_BRANCA})
        self.assertTrue(marcas.alternar_casa(mc.ESTRELA_PRETA, "f6").vazia)

    def test_operacao_nao_altera_o_valor_original(self) -> None:
        original = mc.MarcasDoDiagrama().alternar_casa(mc.X, "a1")
        original.alternar_casa(mc.CRUZ, "b2")
        original.sem_casa("a1")
        self.assertEqual(original.casas, {"a1": mc.X})

    def test_marca_ou_casa_desconhecida_e_recusada(self) -> None:
        with self.assertRaises(ValueError):
            mc.MarcasDoDiagrama().alternar_casa("triangulo", "a1")
        with self.assertRaises(ValueError):
            mc.MarcasDoDiagrama().alternar_casa(mc.X, "z9")
        with self.assertRaises(ValueError):
            mc.MarcasDoDiagrama().alternar_casa(mc.SETA, "a1")


class TracosTests(unittest.TestCase):
    def test_grade_pousa_em_meia_casa_dentro_do_tabuleiro(self) -> None:
        self.assertEqual(mc.na_grade(4.4, 1.6), (4.5, 1.5))
        self.assertEqual(mc.na_grade(2.1, 2.9), (2.0, 3.0))
        self.assertEqual(mc.na_grade(-3.0, 9.0), (0.0, 8.0))

    def test_traco_sem_comprimento_ou_repetido_nao_entra(self) -> None:
        marcas = mc.MarcasDoDiagrama().com_traco(mc.SETA, (7.5, 4.5), (1.5, 4.5))
        self.assertEqual(len(marcas.tracos), 1)
        self.assertIs(marcas.com_traco(mc.SETA, (7.5, 4.5), (1.5, 4.5)), marcas)
        self.assertIs(marcas.com_traco(mc.RETA, (3.5, 3.5), (3.5, 3.5)), marcas)

    def test_seta_tem_sentido_e_moldura_nao(self) -> None:
        marcas = mc.MarcasDoDiagrama().com_traco(mc.SETA, (1.0, 1.0), (2.0, 2.0))
        self.assertEqual(len(marcas.com_traco(mc.SETA, (2.0, 2.0), (1.0, 1.0)).tracos), 2)

        moldura = mc.MarcasDoDiagrama().com_traco(mc.MOLDURA, (5.0, 6.0), (2.0, 1.0))
        self.assertEqual(moldura.tracos[0], mc.Traco(mc.MOLDURA, (2.0, 1.0), (5.0, 6.0)))
        self.assertIs(moldura.com_traco(mc.MOLDURA, (2.0, 6.0), (5.0, 1.0)), moldura)
        self.assertTrue(mc.MarcasDoDiagrama().com_traco(mc.MOLDURA, (2.0, 1.0), (2.0, 6.0)).vazia, "moldura sem área")

    def test_tirar_alcanca_o_traco_mais_proximo_e_so_dentro_da_tolerancia(self) -> None:
        marcas = (
            mc.MarcasDoDiagrama()
            .com_traco(mc.RETA, (0.0, 1.0), (8.0, 1.0))
            .com_traco(mc.SETA, (0.0, 2.0), (8.0, 2.0))
        )
        self.assertEqual([t.tipo for t in marcas.sem_traco_perto((4.0, 1.8)).tracos], [mc.RETA])
        self.assertIs(marcas.sem_traco_perto((4.0, 5.0)), marcas)

    def test_na_moldura_so_a_borda_conta(self) -> None:
        marcas = mc.MarcasDoDiagrama().com_traco(mc.MOLDURA, (2.0, 1.0), (5.0, 6.0))
        self.assertIs(marcas.sem_traco_perto((3.5, 3.5)), marcas, "o miolo da moldura é tabuleiro")
        self.assertTrue(marcas.sem_traco_perto((5.1, 3.5)).vazia)


class DescreverTests(unittest.TestCase):
    def test_frase_por_tipo_com_plural_nos_tracos(self) -> None:
        marcas = (
            mc.MarcasDoDiagrama()
            .alternar_casa(mc.ESTRELA_PRETA, "b6")
            .alternar_casa(mc.ESTRELA_PRETA, "a6")
            .com_traco(mc.SETA, (0.0, 0.0), (1.0, 1.0))
            .com_traco(mc.SETA, (0.0, 0.0), (2.0, 2.0))
            .com_traco(mc.RETA, (0.0, 0.0), (3.0, 3.0))
        )
        self.assertEqual(mc.descrever(marcas), "estrela preta em a6, b6; 2 setas; 1 reta")
        self.assertEqual(mc.descrever(mc.MarcasDoDiagrama()), "")


class IdaEVoltaTests(unittest.TestCase):
    def test_dict_volta_igual(self) -> None:
        marcas = (
            mc.MarcasDoDiagrama()
            .alternar_casa(mc.BOLINHA_BRANCA, "f7")
            .com_traco(mc.RETA, (2.0, 3.0), (4.5, 0.5))
        )
        self.assertEqual(mc.MarcasDoDiagrama.from_dict(json.loads(json.dumps(marcas.to_dict()))), marcas)

    def test_valor_estranho_e_recusado_e_nao_ignorado(self) -> None:
        for estranho in (
            [],
            {"casas": []},
            {"casas": {"z9": mc.X}},
            {"casas": {"a1": "triangulo"}},
            {"tracos": [{"tipo": "curva", "de": [0, 0], "para": [1, 1]}]},
            {"tracos": [{"tipo": mc.SETA, "de": [0, 0]}]},
            {"tracos": [{"tipo": mc.SETA, "de": [0, 0], "para": [9, 1]}]},
        ):
            with self.subTest(estranho=estranho), self.assertRaises(ValueError):
                mc.MarcasDoDiagrama.from_dict(estranho)


class ArquivoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.caminho = pasta_temporaria(self) / "marcas" / "anotacoes.json"
        self.marcas = mc.MarcasDoDiagrama().alternar_casa(mc.ESTRELA_PRETA, "f6")

    def test_sem_arquivo_ninguem_anotou(self) -> None:
        arquivo = mc.ArquivoDeMarcas(self.caminho)
        self.assertEqual(len(arquivo), 0)
        self.assertTrue(arquivo.marcas_de("abc").vazia)
        self.assertIsNone(arquivo.entrada("abc"))
        self.assertFalse(self.caminho.exists(), "ler não cria arquivo")

    def test_gravar_sobrevive_a_reabrir_com_as_notas(self) -> None:
        mc.ArquivoDeMarcas(self.caminho).gravar("abc", self.marcas, imagem="C:/x.png", livro="Nunn", recorte="inteira")

        arquivo = mc.ArquivoDeMarcas(self.caminho)
        self.assertEqual(arquivo.marcas_de("abc"), self.marcas)
        entrada = arquivo.entrada("abc")
        assert entrada is not None
        self.assertEqual((entrada["imagem"], entrada["livro"], entrada["recorte"]), ("C:/x.png", "Nunn", "inteira"))
        self.assertTrue(entrada["anotado_em"])

    def test_tirar_a_ultima_marca_tira_a_entrada(self) -> None:
        arquivo = mc.ArquivoDeMarcas(self.caminho)
        arquivo.gravar("abc", self.marcas)
        arquivo.gravar("abc", mc.MarcasDoDiagrama())

        self.assertIsNone(mc.ArquivoDeMarcas(self.caminho).entrada("abc"))

    def test_regravar_guarda_as_notas_que_nao_vieram(self) -> None:
        arquivo = mc.ArquivoDeMarcas(self.caminho)
        arquivo.gravar("abc", self.marcas, imagem="C:/x.png", amostra="a.png")
        arquivo.gravar("abc", self.marcas.alternar_casa(mc.X, "a1"))

        entrada = mc.ArquivoDeMarcas(self.caminho).entrada("abc")
        assert entrada is not None
        self.assertEqual((entrada["imagem"], entrada["amostra"]), ("C:/x.png", "a.png"))

    def test_duas_janelas_nao_apagam_o_trabalho_uma_da_outra(self) -> None:
        primeira, segunda = mc.ArquivoDeMarcas(self.caminho), mc.ArquivoDeMarcas(self.caminho)
        primeira.gravar("um", self.marcas)
        segunda.gravar("dois", self.marcas)

        relido = mc.ArquivoDeMarcas(self.caminho)
        self.assertFalse(relido.marcas_de("um").vazia)
        self.assertFalse(relido.marcas_de("dois").vazia)

    def test_arquivo_estragado_levanta_e_fica_como_esta(self) -> None:
        self.caminho.parent.mkdir(parents=True)
        for conteudo in (
            "{ isto não é json",
            json.dumps({"versao": 99, "imagens": {}}),
            json.dumps({"versao": 1}),
            json.dumps({"versao": 1, "imagens": {"abc": {"casas": {"a1": "triangulo"}}}}),
        ):
            with self.subTest(conteudo=conteudo):
                self.caminho.write_text(conteudo, encoding="utf-8")
                with self.assertRaises(ValueError):
                    mc.ArquivoDeMarcas(self.caminho)
                self.assertEqual(self.caminho.read_text(encoding="utf-8"), conteudo)

    def test_arquivo_que_estragou_depois_de_aberto_nao_e_sobrescrito(self) -> None:
        arquivo = mc.ArquivoDeMarcas(self.caminho)
        arquivo.gravar("abc", self.marcas)
        self.caminho.write_text("{ estragou", encoding="utf-8")

        with self.assertRaises(ValueError):
            arquivo.gravar("dois", self.marcas)
        self.assertEqual(self.caminho.read_text(encoding="utf-8"), "{ estragou")

    def test_vincular_liga_a_amostra_so_de_quem_tem_anotacao(self) -> None:
        arquivo = mc.ArquivoDeMarcas(self.caminho)
        self.assertFalse(arquivo.vincular_amostra("abc", "a.png"))
        self.assertFalse(self.caminho.exists(), "sem anotação, salvar a amostra não cria o arquivo")

        arquivo.gravar("abc", self.marcas)
        self.assertTrue(arquivo.vincular_amostra("abc", "a.png", "inteira"))
        self.assertFalse(arquivo.vincular_amostra("abc", "a.png", "inteira"), "nada mudou")

        entrada = mc.ArquivoDeMarcas(self.caminho).entrada("abc")
        assert entrada is not None
        self.assertEqual((entrada["amostra"], entrada["recorte"]), ("a.png", "inteira"))


class ChaveTests(unittest.TestCase):
    def test_mesmo_conteudo_mesma_chave_em_qualquer_pasta(self) -> None:
        raiz = pasta_temporaria(self)
        (raiz / "a").mkdir()
        (raiz / "b").mkdir()
        for caminho, conteudo in ((raiz / "a" / "1.png", b"um"), (raiz / "b" / "2.png", b"um"), (raiz / "b" / "3.png", b"dois")):
            Path(caminho).write_bytes(conteudo)

        self.assertEqual(mc.chave_da_imagem(raiz / "a" / "1.png"), mc.chave_da_imagem(raiz / "b" / "2.png"))
        self.assertNotEqual(mc.chave_da_imagem(raiz / "a" / "1.png"), mc.chave_da_imagem(raiz / "b" / "3.png"))


if __name__ == "__main__":
    unittest.main()
