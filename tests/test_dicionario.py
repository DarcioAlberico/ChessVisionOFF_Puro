"""O dicionário que desempata entre os candidatos do modelo (e não é a S-209).

O teste que mais importa aqui é o que **não** deve acontecer: `Nimzowitsch` sai idêntica. É a
decisão medida da S-209 -- palavra fora do dicionário nunca é aproximada da mais parecida --, e
este módulo só pode existir porque não a contraria.
"""

from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.text import dicionario as dic
from chess_diagram_ocr.text.boxes import Caixa

LEXICO = frozenset({"player", "world", "mainly", "position", "will", "bishop", "squares"})


def _cand(*por_posicao: str) -> list[list[str]]:
    """`_cand("p", "/l", "a")` -> a primeira posição só tem `p`, a segunda tem `/` e `l`."""
    return [list(s) for s in por_posicao]


class GuardasTests(unittest.TestCase):
    def test_notacao_nao_e_palavra(self) -> None:
        """A cicatriz da S-209: lance maltratado não pode virar palavra."""
        for token in ("Kf3", "1/2", "Nc", "e4", "2...Qh5"):
            with self.subTest(token=token):
                self.assertFalse(dic.e_palavra(token))

    def test_palavra_com_caractere_errado_no_meio_ainda_e_candidata(self) -> None:
        """`p/ayer` é justamente o que se quer corrigir -- uma régua de só-letras o rejeitaria."""
        self.assertTrue(dic.e_palavra("p/ayer"))

    def test_palavra_curta_demais_fica_de_fora(self) -> None:
        self.assertFalse(dic.e_palavra("abc"))

    def test_qualquer_digito_derruba_o_token(self) -> None:
        self.assertFalse(dic.e_palavra("posi7ion"))


class EscolherTests(unittest.TestCase):
    def test_a_palavra_desconhecida_sem_variante_conhecida_sai_identica(self) -> None:
        """`Nimzowitsch` não está em lista alguma, e forçar a troca entregaria prosa falsa."""
        nome = "Nimzowitsch"
        self.assertIsNone(dic.escolher(nome, [[c, "l", "o"] for c in nome], LEXICO))

    def test_a_troca_vem_do_candidato_do_modelo(self) -> None:
        self.assertEqual(dic.escolher("p/ayer", _cand("p", "/l", "a", "y", "e", "r"), LEXICO), "player")

    def test_a_letra_que_o_modelo_nao_propos_nunca_entra(self) -> None:
        """Sem `l` entre os candidatos, `p/ayer` fica como está -- quem proponha é o modelo."""
        self.assertIsNone(dic.escolher("p/ayer", _cand("p", "/", "a", "y", "e", "r"), LEXICO))

    def test_a_palavra_ja_conhecida_nao_e_tocada(self) -> None:
        self.assertIsNone(dic.escolher("player", _cand("p", "pl", "a", "y", "e", "r"), LEXICO))

    def test_a_ambiguidade_nao_corrige(self) -> None:
        """Duas conhecidas alcançáveis: escolher entre elas é o palpite que o módulo evita."""
        lexico = frozenset({"lata", "rata"})
        self.assertIsNone(dic.escolher("xata", _cand("xlr", "a", "t", "a"), lexico))

    def test_o_lexico_vazio_nunca_corrige(self) -> None:
        self.assertIsNone(dic.escolher("p/ayer", _cand("p", "/l", "a", "y", "e", "r"), frozenset()))

    def test_mais_trocas_que_o_teto_nao_alcancam(self) -> None:
        cand = _cand("x", "yo", "zr", "wl", "vd")
        self.assertNotIn("world", dic.variantes("xyzwv", cand, max_trocas=2))


class CarregarTests(unittest.TestCase):
    def test_o_arquivo_ausente_devolve_lexico_vazio(self) -> None:
        """Ausente não é erro -- é a mesma regra dos outros recursos opcionais do projeto."""
        self.assertEqual(dic.carregar(Path("nao/existe/lexico.txt.gz")), frozenset())

    def test_o_lexico_e_dobrado_para_minuscula(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "l.txt.gz"
            with gzip.open(caminho, "wt", encoding="utf-8") as fh:
                fh.write("Player\nWORLD\n")
            lexico = dic.carregar(caminho)
        self.assertEqual(lexico, frozenset({"player", "world"}))

    def test_o_lexico_do_projeto_nao_tem_notacao(self) -> None:
        """`Kf`, `Nc` e `Re` estavam no léxico bruto do acervo até a régua de notação entrar."""
        lexico = dic.carregar()
        if not lexico:
            self.skipTest("assets/lexico/acervo.txt.gz não está no checkout")
        for token in ("kf", "nc", "re", "qf", "rxc"):
            with self.subTest(token=token):
                self.assertNotIn(token, lexico)

    def test_toda_palavra_do_lexico_tem_o_tamanho_minimo(self) -> None:
        lexico = dic.carregar()
        if not lexico:
            self.skipTest("assets/lexico/acervo.txt.gz não está no checkout")
        curtas = [p for p in lexico if len(p) < dic.MIN_TAMANHO]
        self.assertEqual(curtas, [], "palavra curta no léxico é notação disfarçada")

    def test_nenhuma_palavra_do_lexico_tem_digito(self) -> None:
        """Palavra com dígito no léxico seria lance entrando como alvo de correção."""
        lexico = dic.carregar()
        if not lexico:
            self.skipTest("assets/lexico não está no checkout")
        com_digito = [p for p in lexico if any(c.isdigit() for c in p)][:5]
        self.assertEqual([], com_digito)

    def test_sem_argumento_e_a_uniao_das_listas_empacotadas(self) -> None:
        """`carregar()` é o léxico do projeto; `carregar(caminho)` é um arquivo só."""
        uniao = dic.carregar()
        if not uniao:
            self.skipTest("assets/lexico não está no checkout")
        for caminho in dic.EMPACOTADOS:
            parte = dic.carregar(caminho)
            if parte:
                self.assertTrue(parte <= uniao, f"{caminho.name} ficou de fora da união")

    def test_os_nomes_proprios_saem_quando_nao_sao_pedidos(self) -> None:
        """A S-209 mediu a troca: nome próprio baixa o alarme falso **e esconde erro**."""
        nomes = dic.carregar(dic.CAMINHO_NOMES)
        if not nomes:
            self.skipTest("assets/lexico/nomes.txt.gz não está no checkout")
        sem_nomes = dic.carregar(nomes=False)
        self.assertTrue(sem_nomes < dic.carregar())
        self.assertFalse(nomes <= sem_nomes, "a lista de nomes continuou dentro")


class TetoDeTrocasTests(unittest.TestCase):
    """`max_trocas` chegava até `corrigir` e morria ali: `escolher` sempre usava o padrão."""

    def test_o_teto_pedido_e_o_teto_usado(self) -> None:
        cand = _cand("xw", "wo", "zr", "yl", "vd")
        self.assertEqual("world", dic.escolher("xwzyv", cand, LEXICO, max_trocas=5))
        self.assertIsNone(
            dic.escolher("xwzyv", cand, LEXICO, max_trocas=2),
            "com teto 2 não se alcança uma palavra a 5 trocas de distância",
        )

    def test_corrigir_repassa_o_teto(self) -> None:
        """Sem o repasse, medir o teto mediria sempre a mesma coisa."""
        palavra = "p/ayer"
        caixas = [Caixa(i * 10, 0, i * 10 + 8, 20) for i in range(len(palavra))]
        lidos = [(c, 0.9) for c in palavra]
        i2c = {0: "p", 1: "/", 2: "a", 3: "y", 4: "e", 5: "r", 6: "l"}
        probs = np.zeros((len(caixas), 7), np.float32)
        for k, (c, _) in enumerate(lidos):
            probs[k, [i for i, v in i2c.items() if v == c][0]] = 0.9
        probs[1, 6] = 0.05
        self.assertEqual(
            "player", "".join(c for c, _ in dic.corrigir(lidos, probs, caixas, i2c, LEXICO, max_trocas=1))
        )
        self.assertEqual(
            palavra,
            "".join(c for c, _ in dic.corrigir(lidos, probs, caixas, i2c, LEXICO, max_trocas=0)),
            "teto zero não troca nada",
        )


class CorrigirLinhaTests(unittest.TestCase):
    def _linha(self, palavra: str) -> tuple[list[Caixa], list[tuple[str, float]]]:
        caixas = [Caixa(i * 10, 0, i * 10 + 8, 20) for i in range(len(palavra))]
        return caixas, [(c, 0.9) for c in palavra]

    def test_a_palavra_da_linha_e_corrigida(self) -> None:
        caixas, lidos = self._linha("p/ayer")
        i2c = {0: "p", 1: "/", 2: "a", 3: "y", 4: "e", 5: "r", 6: "l"}
        probs = np.zeros((len(caixas), 7), np.float32)
        for k, (c, _) in enumerate(lidos):
            probs[k, [i for i, v in i2c.items() if v == c][0]] = 0.9
        probs[1, 6] = 0.05  # `l` em rank 2 na posição da barra
        saida = dic.corrigir(lidos, probs, caixas, i2c, LEXICO)
        self.assertEqual("".join(c for c, _ in saida), "player")

    def test_a_confianca_da_letra_trocada_e_a_dela(self) -> None:
        caixas, lidos = self._linha("p/ayer")
        i2c = {0: "p", 1: "/", 2: "a", 3: "y", 4: "e", 5: "r", 6: "l"}
        probs = np.zeros((len(caixas), 7), np.float32)
        for k, (c, _) in enumerate(lidos):
            probs[k, [i for i, v in i2c.items() if v == c][0]] = 0.9
        probs[1, 6] = 0.05
        saida = dic.corrigir(lidos, probs, caixas, i2c, LEXICO)
        self.assertAlmostEqual(saida[1][1], 0.05, places=3)
        self.assertAlmostEqual(saida[0][1], 0.9, places=3, msg="a letra que não mudou mantém a sua")

    def test_sem_lexico_a_linha_sai_intacta(self) -> None:
        caixas, lidos = self._linha("p/ayer")
        i2c = {0: "p", 1: "/", 2: "a", 3: "y", 4: "e", 5: "r"}
        probs = np.zeros((len(caixas), 6), np.float32)
        self.assertEqual(dic.corrigir(lidos, probs, caixas, i2c, frozenset()), lidos)

    def test_a_palavra_separada_por_espaco_e_um_token(self) -> None:
        """A régua do espaço é a de `linhas.texto_da_linha`; discordar dela corrigiria outro texto."""
        caixas = [Caixa(0, 0, 8, 20), Caixa(9, 0, 17, 20), Caixa(200, 0, 208, 20)]
        lidos = [("a", 0.9), ("b", 0.9), ("c", 0.9)]
        self.assertEqual(dic.palavras(caixas, lidos), [(0, 2), (2, 3)])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
