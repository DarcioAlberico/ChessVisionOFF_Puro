"""A língua do livro (S-723): o decisor com textos curtos, o caderno, e o relatório contra a tabela à mão.

**Nenhum livro é lido aqui.** A detecção de verdade está em `docs/metrics/texto_lingua_20261106.json`, que guarda só as
contagens; o teste refaz a decisão sobre elas, e reprova relatório medido com outro perfil.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.text import caderno, fusao, lexico, lingua
from chess_diagram_ocr.text.lingua import Contagem, LinguaDoLivro, contar, decidir
from chess_diagram_ocr.text.tesseract import LINGUAS

RAIZ = Path(__file__).resolve().parents[1]

TEXTOS = {
    "eng": "The white king has to move to the centre of the board, and this is not an easy task for the player with black.",
    "por": "O rei das brancas não pode sair da coluna, e com uma torre em jogo os peões do lado da dama são mais fortes.",
    "spa": "El rey de las blancas no puede salir de la columna, y con una torre en el juego los peones del flanco son fuertes.",
    "deu": "Der weiße König ist nicht auf dem Feld, und die Dame kann mit einem Zug nach links auch den Bauern von hinten nehmen.",
    "nld": "De witte koning is niet op het veld, en de dame kan met een zet naar links ook van de pion winnen door dit plan.",
    "fra": "Le roi des blancs ne peut pas sortir de la colonne, et avec une tour dans le jeu les pions sont plus forts sur cette aile.",
    "ron": "Regele alb nu este pe coloana care se deschide, și cu un turn în joc pionii din centru sunt mai tari după acest schimb.",
    "rus": "Белый король не может выйти на открытую линию, и при этом пешки становятся сильнее после размена ладей на доске.",
}


class DecisorTests(unittest.TestCase):
    def test_cada_lingua_e_reconhecida_num_texto_curto(self) -> None:
        for codigo, texto in TEXTOS.items():
            with self.subTest(lingua=codigo):
                self.assertEqual(codigo, decidir(contar(texto * 3)))

    def test_as_oito_linguas_do_tesseract_estao_cobertas(self) -> None:
        self.assertEqual(set(LINGUAS), set(TEXTOS))

    def test_pouca_evidencia_nao_decide(self) -> None:
        self.assertEqual("", decidir(contar("the king")))
        self.assertEqual("", decidir(Contagem()))

    def test_empate_nao_decide(self) -> None:
        self.assertEqual("", decidir(Contagem({"por": 10.0, "spa": 9.0})))

    def test_vantagem_folgada_decide(self) -> None:
        self.assertEqual("por", decidir(Contagem({"por": 10.0, "spa": 2.0})))

    def test_portugues_e_espanhol_nao_se_confundem_no_que_dividem(self) -> None:
        """`que`, `para` e `como` valem meio ponto em cada, e quem decide é o que só um deles tem."""
        por = contar(TEXTOS["por"])
        self.assertGreater(por.pontos["por"], por.pontos.get("spa", 0.0))

    def test_notacao_nao_conta(self) -> None:
        """`De4`, `Te1` e `Re1` começam como `de`, `te` e `re`, e são lance."""
        lances = " ".join(["De4", "Te1", "Re1", "1.e4", "e5", "Nf3", "Le5", "Df3"] * 20)
        self.assertEqual({}, dict(contar(lances).pontos))

    def test_maiuscula_e_letra_solta_nao_contam(self) -> None:
        self.assertEqual({}, dict(contar("De Le Te a e o b c d f g h " * 10).pontos))
        self.assertEqual({}, dict(contar("The Und Het Les Der Dans " * 10).pontos))

    def test_o_glifo_que_perde_o_acento_ainda_conta(self) -> None:
        self.assertEqual(contar("não está já").pontos, contar("nao esta ja").pontos)

    def test_o_cirilico_decide_pelo_alfabeto(self) -> None:
        self.assertEqual("rus", decidir(contar("Кр. Белые ладья слон " * 5)))
        self.assertEqual("rus", decidir(Contagem(cirilicas=60, latinas=40)))
        self.assertNotEqual("rus", decidir(Contagem({"eng": 10.0}, cirilicas=5, latinas=95)))


class EstadoTests(unittest.TestCase):
    TEXTO = TEXTOS["por"] * 2

    def test_a_manual_sempre_vence_a_detectada(self) -> None:
        estado = LinguaDoLivro().com_folha(0, self.TEXTO)
        self.assertEqual("por", estado.efetiva("eng"))
        self.assertEqual("deu", estado.com_manual("deu").efetiva("eng"))
        self.assertEqual("deu", estado.com_manual("deu").com_folha(1, self.TEXTO).efetiva("eng"))

    def test_tirar_a_manual_devolve_a_detectada_com_a_conta_intacta(self) -> None:
        estado = LinguaDoLivro().com_folha(0, self.TEXTO).com_manual("deu").com_manual("")
        self.assertEqual("por", estado.efetiva("eng"))
        self.assertEqual((0,), estado.folhas)

    def test_sem_nenhuma_responde_o_padrao(self) -> None:
        self.assertEqual("eng", LinguaDoLivro().efetiva("eng"))

    def test_reler_a_mesma_folha_nao_conta_de_novo(self) -> None:
        uma = LinguaDoLivro().com_folha(3, self.TEXTO)
        self.assertEqual(uma, uma.com_folha(3, self.TEXTO))

    def test_folha_com_poucas_palavras_nao_gasta_uma_das_dez(self) -> None:
        self.assertEqual((), LinguaDoLivro().com_folha(0, "Capa do livro").folhas)

    def test_depois_das_dez_folhas_nada_muda(self) -> None:
        estado = LinguaDoLivro()
        for pagina in range(lingua.FOLHAS_DA_DETECCAO):
            estado = estado.com_folha(pagina, self.TEXTO)
        self.assertEqual("por", estado.detectada)
        depois = estado.com_folha(99, TEXTOS["eng"] * 50)
        self.assertEqual(estado, depois)

    def test_manual_desconhecida_e_recusada(self) -> None:
        self.assertEqual("", LinguaDoLivro().com_manual("klingon").manual)

    def test_ida_e_volta_pelo_json(self) -> None:
        estado = LinguaDoLivro().com_folha(4, self.TEXTO).com_manual("spa")
        relido = LinguaDoLivro.de_json(json.loads(json.dumps(estado.para_json())))
        self.assertEqual(estado.manual, relido.manual)
        self.assertEqual(estado.detectada, relido.detectada)
        self.assertEqual(estado.folhas, relido.folhas)
        self.assertEqual(estado.contagem.palavras, relido.contagem.palavras)

    def test_o_json_estragado_vira_sem_lingua_e_nao_erro(self) -> None:
        for dados in (None, [], "x", {"manual": "klingon", "detectada": 3, "folhas": "abc", "contagem": {"pontos": 1}}, {"folhas": ["x"]}):
            with self.subTest(dados=dados):
                self.assertEqual("", LinguaDoLivro.de_json(dados).efetiva())


class CadernoTests(unittest.TestCase):
    def setUp(self) -> None:
        pasta = pasta_temporaria(self)
        self.livro = pasta / "livro.pdf"
        self.livro.write_bytes(b"%PDF-1.4 livro de teste")
        self.pasta = pasta / "cadernos"
        self.caderno = caderno.abrir(self.livro, pasta=self.pasta)
        assert self.caderno is not None
        self.addCleanup(self.caderno.fechar)

    def test_caderno_novo_nao_tem_lingua(self) -> None:
        self.assertEqual(LinguaDoLivro(), self.caderno.lingua())

    def test_a_lingua_volta_na_reabertura_e_nao_cria_folha(self) -> None:
        self.assertTrue(self.caderno.guardar_lingua(LinguaDoLivro().com_folha(0, TEXTOS["por"] * 2).com_manual("deu")))
        self.caderno.fechar()
        de_novo = caderno.abrir(self.livro, pasta=self.pasta)
        assert de_novo is not None
        self.addCleanup(de_novo.fechar)
        self.assertEqual(("deu", "por"), (de_novo.lingua().manual, de_novo.lingua().detectada))
        self.assertEqual((), de_novo.folhas())

    def test_refazer_o_indice_nao_perde_a_escolha_da_pessoa(self) -> None:
        self.caderno.guardar_lingua(LinguaDoLivro().com_manual("nld"))
        (self.caderno.pasta / "indice.json").write_text("{estragado", encoding="utf-8")
        relido = caderno.Caderno(self.caderno.pasta, self.caderno.identidade)
        self.assertEqual("nld", relido.lingua().manual)

    def test_arquivo_estragado_volta_a_deteccao(self) -> None:
        (self.caderno.pasta / "lingua.json").write_text("{estragado", encoding="utf-8")
        with self.assertLogs("chess_diagram_ocr.text.caderno", level="WARNING"):
            self.assertEqual(LinguaDoLivro(), self.caderno.lingua())

    def test_so_leitura_nao_grava(self) -> None:
        self.caderno.somente_leitura = True
        self.assertFalse(self.caderno.guardar_lingua(LinguaDoLivro().com_manual("por")))
        self.assertFalse((self.caderno.pasta / "lingua.json").exists())


class LexicoDoLivroTests(unittest.TestCase):
    def test_a_palavra_de_cada_alfabeto_existe_na_propria_lingua(self) -> None:
        self.assertTrue(fusao.existe_do_livro("ron")("după"))
        self.assertTrue(fusao.existe_do_livro("rus")("после"))
        self.assertTrue(fusao.existe_do_livro("por")("depois,"))

    def test_o_vocabulario_do_xadrez_e_os_nomes_ficam(self) -> None:
        for codigo in LINGUAS:
            with self.subTest(lingua=codigo):
                self.assertTrue(fusao.existe_do_livro(codigo)("zugzwang"))
                self.assertTrue(fusao.existe_do_livro(codigo)("Nimzowitsch"))

    def test_a_curta_e_da_lingua_do_livro(self) -> None:
        """`und` existe no alemão e `het` no holandês, e nenhuma das duas num livro em português."""
        self.assertTrue(fusao.existe_do_livro("deu")("und"))
        self.assertFalse(fusao.existe_do_livro("por")("und"))
        self.assertTrue(fusao.existe_do_livro("nld")("het"))
        self.assertFalse(fusao.existe_do_livro("por")("het"))

    def test_lingua_sem_lista_cai_no_lexico_compartilhado(self) -> None:
        self.assertTrue(fusao.existe_do_livro("klingon")("und"))
        self.assertEqual(frozenset(), lexico.do_livro("klingon"))

    def test_o_interruptor_volta_ao_de_antes(self) -> None:
        antes = fusao.LEXICO_POR_LINGUA
        self.addCleanup(setattr, fusao, "LEXICO_POR_LINGUA", antes)
        fusao.LEXICO_POR_LINGUA = False
        self.assertTrue(fusao.existe_do_livro("por")("und"))
        self.assertFalse(fusao.existe_do_livro("rus")("после"))

    def test_as_curtas_de_sempre_nao_mudaram(self) -> None:
        """É o conjunto que `existe_no` usa sem língua: as seis de antes, e nem o romeno nem o russo."""
        self.assertIn("het", fusao.CURTAS)
        self.assertIn("the", fusao.CURTAS)
        self.assertNotIn("după", fusao.CURTAS)
        self.assertNotIn("как", fusao.CURTAS)
        self.assertEqual(122, len(fusao.CURTAS))


class RelatorioTests(unittest.TestCase):
    """O relatório publicado, contra a tabela à mão. As contagens não têm texto de livro nenhum."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.relatorio = json.loads((RAIZ / "docs" / "metrics" / "texto_lingua_20261106.json").read_text(encoding="utf-8"))
        cls.tabela = json.loads((RAIZ / "docs" / "metrics" / "texto_lingua_2026-11-06" / "linguas_declaradas.json").read_text(encoding="utf-8"))["livros"]

    def test_o_perfil_medido_e_o_de_hoje(self) -> None:
        """Mudou uma palavra ou uma constante: o relatório não fala mais deste decisor, e se remede."""
        self.assertEqual(lingua.sha_do_perfil(), self.relatorio["perfil_sha"])

    def test_todo_livro_da_tabela_foi_medido(self) -> None:
        self.assertEqual(set(self.tabela), {livro["livro"] for livro in self.relatorio["livros"]})

    def test_a_tabela_tem_as_oito_linguas(self) -> None:
        self.assertEqual(set(LINGUAS), set(self.tabela.values()))

    def test_refazer_a_decisao_da_o_que_o_relatorio_publica(self) -> None:
        for livro in self.relatorio["livros"]:
            with self.subTest(livro=livro["livro"]):
                self.assertEqual(self.tabela[livro["livro"]], livro["declarada"])
                for fonte in ("glifo", "camada", "produto"):
                    self.assertEqual(livro[fonte]["detectada"], decidir(Contagem.de_json(livro[fonte])))

    def test_nenhum_livro_detectado_errado_na_fonte_do_produto(self) -> None:
        """Sem resposta se aceita, e está contado no relatório, com a janela dizendo à pessoa que escolha; língua **errada** não."""
        bilingues = self.relatorio["bilingues"]
        errados = [
            (livro["livro"], livro["produto"]["detectada"])
            for livro in self.relatorio["livros"]
            if livro["produto"]["detectada"] not in ("", livro["declarada"], *bilingues.get(livro["livro"], ()))
        ]
        self.assertEqual([], errados)


if __name__ == "__main__":
    unittest.main()
