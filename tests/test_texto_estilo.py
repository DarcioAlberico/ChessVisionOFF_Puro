"""O estilo da palavra pela imagem (Fase 96, S-661 a S-663): o rótulo, a identidade, a divisão e as réguas."""

from __future__ import annotations

import unittest

import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.cli import texto_estilo_classificador as classificador
from chess_diagram_ocr.cli import texto_estilo_conjunto as conjunto
from chess_diagram_ocr.text import estilo


def _letras(texto: str, negrito: bool = False, italico: bool = False, x: float = 0.0):
    return [(letra, (x + 5.0 * k, 0.0, x + 5.0 * k + 4.0, 10.0), negrito, italico) for k, letra in enumerate(texto)]


class RotuloTests(unittest.TestCase):
    def test_os_dois_bits_dao_as_quatro_classes(self) -> None:
        self.assertEqual(
            [estilo.rotulo(n, i) for i in (False, True) for n in (False, True)],
            ["normal", "negrito", "italico", "negrito-italico"],
        )

    def test_a_linha_vira_palavras_e_a_que_mistura_fica_sem_classe(self) -> None:
        linha = _letras("Lance ") + _letras("forte", negrito=True, x=30) + _letras(" e", x=55) + _letras("x", italico=True, x=65)
        linha += _letras("y -- 12.", x=70)
        palavras = estilo.palavras_de_caracteres(linha)
        self.assertEqual([p.texto for p in palavras], ["Lance", "forte", "exy", "12."])
        self.assertEqual([p.classe for p in palavras], ["normal", "negrito", None, "normal"])
        self.assertEqual(palavras[1].bbox, (30.0, 0.0, 54.0, 10.0))

    def test_sinal_sem_letra_e_letra_sozinha_nao_entram(self) -> None:
        self.assertEqual(estilo.palavras_de_caracteres(_letras("a -- !? b")), [])


class IdentidadeTests(unittest.TestCase):
    TEXTO = "as brancas jogam e ganham porque o cavalo chega a tempo de cobrir a casa de promoção " * 3

    def test_dois_arquivos_do_mesmo_livro_tem_a_mesma_identidade(self) -> None:
        textos = {
            "livro.pdf": estilo.sequencias(self.TEXTO),
            "livro_hq.pdf": estilo.sequencias(self.TEXTO + " uma nota a mais no fim do livro"),
            "outro.pdf": estilo.sequencias("um texto que não tem nada a ver com o primeiro livro do acervo " * 2),
        }
        ident = estilo.identidades(textos)
        self.assertEqual(ident["livro.pdf"], ident["livro_hq.pdf"])
        self.assertNotEqual(ident["livro.pdf"], ident["outro.pdf"])
        self.assertEqual(ident, estilo.identidades(dict(reversed(list(textos.items())))), "a identidade não depende da ordem")

    def test_o_parentesco_e_do_menor_conjunto(self) -> None:
        a = frozenset({"1", "2", "3", "4"})
        self.assertEqual(estilo.parentesco(a, frozenset({"1", "2"})), 1.0)
        self.assertEqual(estilo.parentesco(a, frozenset()), 0.0)


class ParticaoTests(unittest.TestCase):
    def test_cada_livro_numa_particao_e_o_estilo_raro_chega_ao_teste(self) -> None:
        contas = {
            f"livro{i}": {"normal": 1000, "negrito": 50, "italico": 30 if i % 3 == 0 else 0} for i in range(10)
        }
        particao = estilo.particionar(contas)
        self.assertEqual(set(particao), set(contas))
        self.assertEqual(set(particao.values()), {"treino", "validacao", "teste"})
        italico = {p: sum(contas[i]["italico"] for i in contas if particao[i] == p) for p in estilo.PARTICOES}
        self.assertGreater(italico["teste"], 0, italico)
        self.assertGreater(italico["treino"], italico["teste"])
        self.assertEqual(particao, estilo.particionar(contas), "determinístico")


class ImagemTests(unittest.TestCase):
    def test_normalizar_corta_a_palavra_larga_e_completa_a_estreita_com_papel(self) -> None:
        larga, util = estilo.normalizar(np.zeros((40, 1000), np.uint8))
        self.assertEqual((larga.shape, util), ((estilo.ALTURA, estilo.LARGURA_MAXIMA), estilo.LARGURA_MAXIMA))
        estreita, util = estilo.normalizar(np.zeros((40, 40), np.uint8))
        self.assertEqual(util, estilo.ALTURA)
        self.assertTrue((estreita[:, util:] == 255).all())
        vazia, util = estilo.normalizar(np.zeros((0, 5), np.uint8))
        self.assertEqual(util, 0)

    def test_degradar_guarda_o_tamanho_e_repete_com_a_mesma_semente(self) -> None:
        imagem = np.full((32, 192), 255, np.uint8)
        imagem[8:24, 10:100] = 0
        a = estilo.degradar(imagem, np.random.default_rng(1))
        b = estilo.degradar(imagem, np.random.default_rng(1))
        self.assertEqual(a.shape, imagem.shape)
        np.testing.assert_array_equal(a, b)


class ReguaTests(unittest.TestCase):
    def test_chutar_pela_altura_aprende_um_corte_no_treino(self) -> None:
        previsto = estilo.chutar_pela_altura([20, 22, 30, 32], ["normal", "normal", "negrito", "negrito"], [21, 31])
        self.assertEqual(previsto, ["normal", "negrito"])

    def test_o_corte_e_o_menor_que_chega_a_precisao_na_validacao(self) -> None:
        # 10 palavras de negrito com confiança alta e 10 normais que a rede confunde com 0,6.
        p = np.array([[0.1, 0.9, 0, 0]] * 10 + [[0.4, 0.6, 0, 0]] * 10)
        y = np.array([1] * 10 + [0] * 10)
        self.assertEqual(estilo.corte_para(p, y, 1, 0.95), 0.9)
        medida = estilo.regua(p, y, 1, 0.9)
        self.assertEqual((medida.precisao, medida.cobertura), (1.0, 1.0))
        self.assertIsNone(estilo.corte_para(p, y, 2, 0.95), "classe que nunca vence não tem corte")

    def test_julgar_nao_julga_classe_sem_amostra(self) -> None:
        p = np.array([[0.05, 0.95, 0, 0]] * 30 + [[0.9, 0.1, 0, 0]] * 30)
        y = np.array([1] * 30 + [0] * 30)
        julgado = classificador.julgar(p, y, p, y)
        self.assertTrue(julgado["negrito"]["sugerir"]["passa"])
        self.assertTrue(julgado["negrito"]["aplicar"]["passa"])
        self.assertFalse(julgado["italico"]["sugerir"]["passa"])
        self.assertEqual(julgado["italico"]["no_teste"], 0)


class ConjuntoNoDiscoTests(unittest.TestCase):
    def test_gravar_e_carregar_guardam_a_particao_do_livro(self) -> None:
        imagem = np.full((estilo.ALTURA, estilo.LARGURA_MAXIMA), 255, np.uint8)
        textos = (
            "o cavalo chega a tempo de cobrir a casa de promoção e as brancas ganham",
            "as pretas trocam as torres e o final de peões fica empatado sem esforço",
            "um sacrifício de dama abre a coluna e o rei branco não tem para onde ir",
            "a estrutura de peões dobrados decide a partida muito antes do final dela",
        )
        coleta = {
            "recortes": {
                f"livro{i}.pdf": [(imagem, 40, 30, classe, 3, "palavra") for classe in ("normal", "negrito", "italico")]
                for i in range(4)
            },
            "textos": {f"livro{i}.pdf": estilo.sequencias(texto) for i, texto in enumerate(textos)},
            "fora": {},
        }
        coleta["textos"]["livro1.pdf"] = coleta["textos"]["livro0.pdf"]  # o mesmo livro em dois arquivos
        pasta = pasta_temporaria(self)
        contas = conjunto.gravar(coleta, pasta)
        self.assertEqual(contas["palavras"], 12)
        self.assertEqual(list(contas["arquivos_juntados_pela_identidade"].values()), [["livro0.pdf", "livro1.pdf"]])
        dados = classificador.carregar(pasta / "palavras.npz")
        self.assertEqual(dados["imagens"].shape, (12, estilo.ALTURA, estilo.LARGURA_MAXIMA))
        self.assertEqual(len(set(dados["particao"][:6])), 1, "os dois arquivos do mesmo livro caem juntos")
        manifesto = (pasta / "manifesto.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(manifesto[0], "identidade,arquivo,folha,palavra,rotulo,particao,altura_px")
        self.assertEqual(len(manifesto), 13)

    def test_as_folhas_espacadas(self) -> None:
        self.assertEqual(conjunto.folhas_de(100, 3), [25, 50, 75])
        self.assertEqual(conjunto.folhas_de(0, 3), [])


if __name__ == "__main__":
    unittest.main()
