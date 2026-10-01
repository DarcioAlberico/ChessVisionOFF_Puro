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


class PontuacaoNaoEAmbiguidadeTests(unittest.TestCase):
    """Duas variantes que só diferem na pontuação de borda são a mesma resposta (S-349).

    `conhecida` apara `.,;:!?()[]'"` antes de olhar o léxico, então `black.` e `black,` **são** a
    mesma palavra para o dicionário -- e chegavam à guarda da ambiguidade como duas, fazendo o
    módulo recusar uma correção que era única.
    """

    LEXICO = frozenset({"black", "blaek"})

    def test_a_correcao_sai_com_a_pontuacao_do_original(self) -> None:
        candidatos = [["b"], ["l"], ["a"], ["e", "c"], ["k"], [".", ","]]
        self.assertEqual(dic.escolher("blaek.", candidatos, frozenset({"black"})), "black.")

    def test_sem_pontuacao_nada_muda(self) -> None:
        candidatos = [["b"], ["l"], ["a"], ["e", "c"], ["k"]]
        self.assertEqual(dic.escolher("blaek", candidatos, frozenset({"black"})), "black")

    def test_duas_palavras_diferentes_continuam_ambiguas(self) -> None:
        """A guarda que importa segue de pé: o que ela recusa é escolher entre **palavras**."""
        candidatos = [["b"], ["l"], ["a", "o"], ["e", "c"], ["k"]]
        self.assertIsNone(
            dic.escolher("blaek", candidatos, frozenset({"black", "block"}))
        )

    def test_a_caixa_deixou_de_ser_ambiguidade(self) -> None:
        """**Isto era `assertIsNone`, e a S-508 desfez a decisão. Ver `sem_troca_de_caixa`.**

        A S-349 escreveu que `Black` e `black` eram "duas respostas de verdade". Não eram: o
        original chegou com `b` minúsculo porque `caixa_alta.decidir` mediu a **altura** daquele
        box, e trocar por `B` desfaria uma decisão que ninguém pediu para rever. Não havia escolha
        a fazer, e recusar a correção custava as 13 palavras por folha que a S-508 mediu.
        """
        candidatos = [["b", "B"], ["l"], ["a"], ["e", "c"], ["k"]]
        self.assertEqual(dic.escolher("blaek", candidatos, frozenset({"black"})), "black")

    def test_duas_letras_diferentes_no_mesmo_box_continuam_ambiguas(self) -> None:
        """O que a guarda recusa é escolher **letra**, e isso não mudou: `l` contra `i`."""
        candidatos = [["a"], ["1", "l", "i"], ["s"], ["o"]]
        self.assertIsNone(dic.escolher("a1so", candidatos, frozenset({"also", "aiso"})))


class ParELEUmTests(unittest.TestCase):
    """O `l` que sai `1`, e as duas guardas que barravam a correção (S-508).

    Depois do resize para 32x32 o `l` e o `1` são a mesma imagem. O modelo põe `l` em rank 2 em
    **todas** as caixas em que escreveu `1` dentro de palavra, medido na folha 11 do `Nunn`; o que
    faltava era deixar o dicionário olhar.
    """

    LEXICO = frozenset({"only", "black", "result", "while", "natural", "also", "aiso"})

    def test_o_digito_que_o_modelo_desmente_deixa_de_barrar_o_token(self) -> None:
        candidatos = _cand("o", "n", "1li", "y")
        self.assertEqual(dic.escolher("on1y", candidatos, self.LEXICO), "only")

    def test_a_fracao_de_letras_e_medida_na_palavra_que_o_modelo_oferece(self) -> None:
        """`wi11` tem metade de dígitos e a fração de `lexico.suspeita` a recusaria; `will`, não.

        As duas perguntas são feitas sobre strings diferentes de propósito -- ver
        `_digito_do_classificador`.
        """
        candidatos = _cand("w", "i", "1li", "1li")
        self.assertEqual(dic.escolher("wi11", candidatos, self.LEXICO | {"will"}), "will")

    def test_o_digito_no_comeco_da_palavra_tambem(self) -> None:
        candidatos = _cand("1li", "e", "s", "s")
        self.assertEqual(dic.escolher("1ess", candidatos, self.LEXICO | {"less"}), "less")

    def test_o_digito_no_fim_de_palavra_tambem(self) -> None:
        """`natura1` não é notação, e o `1` final é do classificador como qualquer outro."""
        candidatos = _cand("n", "a", "t", "u", "r", "a", "1li")
        self.assertEqual(dic.escolher("natura1", candidatos, self.LEXICO), "natural")

    def test_o_lance_continua_intocado_mesmo_com_a_letra_no_topo(self) -> None:
        """**A guarda que importa.** `Rxd1` tem `l` em rank 2 no `1` como qualquer outro dígito,
        e mesmo assim não é palavra: quem diz isso é `notacao.peso_de_notacao` (S-208)."""
        candidatos = _cand("R", "x", "d", "1li")
        self.assertFalse(dic.candidata("Rxd1", candidatos))
        self.assertIsNone(dic.escolher("Rxd1", candidatos, self.LEXICO | {"rxdl"}))

    def test_o_digito_que_o_modelo_confirma_barra_o_token(self) -> None:
        """`e5.knight`: o `5` é o único candidato daquela caixa, e é tinta do livro."""
        candidatos = _cand("e", "5", ".", "k", "n", "i", "g", "h", "t")
        self.assertFalse(dic.candidata("e5.knight", candidatos))

    def test_meia_palavra_da_quebra_de_linha_fica_de_fora(self) -> None:
        """`interest-` virava `interest` e `sim-` virava `simI`: o hífen sumia ou virava letra."""
        self.assertFalse(dic.candidata("interest-", _cand("i", "n", "t", "e", "r", "e", "s", "t", "-.")))

    def test_a_troca_de_caixa_sai_da_busca(self) -> None:
        """`S` na caixa do `s` não é alternativa: quem decide caixa é a altura, em `caixa_alta`.

        A alternativa igual ao que já está lá some junto, e é inócuo: `variantes` nunca a usaria.
        """
        self.assertEqual(
            dic.sem_troca_de_caixa("resu1t", _cand("r", "e", "sS", "u", "1li", "t")),
            [[], [], [], [], ["l", "i"], []],
        )

    def test_sem_a_troca_de_caixa_a_correcao_deixa_de_ser_ambigua(self) -> None:
        """O par: com `S` na busca, `reSult` e `result` empatam e o token fica errado."""
        candidatos = _cand("r", "e", "sS", "u", "1li", "t")
        self.assertEqual(dic.escolher("resu1t", candidatos, self.LEXICO), "result")

    def test_o_acento_nao_e_trocado_pela_falta_no_lexico(self) -> None:
        """**A única palavra certa que a medição viu quebrada.**

        `façanha` não está no léxico e `facanha` está, e sem esta guarda o dicionário trocava uma
        pela outra. A cedilha é tinta na imagem -- ao contrário do tamanho, que o resize apaga --,
        e tirá-la seria desfazer o que o classificador viu para acomodar uma falta do dicionário.
        """
        candidatos = _cand("f", "a", "çc", "a", "n", "h", "a")
        self.assertIsNone(dic.escolher("façanha", candidatos, frozenset({"facanha"})))

    def test_a_ambiguidade_de_letra_continua_recusando(self) -> None:
        """O que a guarda 4 recusa é escolher **letra**: `also` contra `aiso`, os dois no léxico."""
        self.assertIsNone(dic.escolher("a1so", _cand("a", "1li", "s", "o"), self.LEXICO))
