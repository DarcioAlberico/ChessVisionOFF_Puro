"""S-732: o espaço que o vão não mostra, e o léxico como árbitro do corte.

Decisão com caixas sintéticas, que roda no CI sem modelo nem livro. Cada família tem o caso que reproduz o
defeito com a constante desligada: teste que passa com o conserto revertido não guarda nada.
"""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
from glifo_sintetico import _lidos, _linha, _texto

from chess_diagram_ocr.text import colados, fronteira
from chess_diagram_ocr.text.boxes import Caixa


class CortesDePalavraTests(unittest.TestCase):
    """S-732: o léxico dispõe, e o vão de baixo propõe."""

    LEXICO = frozenset({"reshevsky", "joga", "carr", "ying", "carrying", "transfer", "pawn", "knight", "romper"})
    SEM_NOMES = frozenset({"joga", "transfer", "pawn", "knight", "romper"})

    def _cortes(self, palavra: str, candidatos: list[int]) -> list[int] | None:
        return fronteira.cortes(list(palavra), candidatos, self.SEM_NOMES, self.LEXICO)

    def test_of_the(self) -> None:
        self.assertEqual(self._cortes("ofthe", [2]), [2])
        self.assertEqual(self._cortes("ifthe", [2]), [2])

    def test_dois_cortes(self) -> None:
        self.assertEqual(self._cortes("oftheknight", [2, 5]), [2, 5])

    def test_nome_longo_vale(self) -> None:
        self.assertEqual(self._cortes("Reshevskyjoga", [9]), [9])

    def test_nome_curto_nao_vale(self) -> None:
        """`carr ying`: o defeito que tirou `PARTIR_COLADAS` de cena."""
        self.assertIsNone(fronteira.cortes(list("carrying"), [4], frozenset(), frozenset({"carr", "ying"})))

    def test_palavra_conhecida_nao_parte(self) -> None:
        self.assertIsNone(self._cortes("carrying", [4]))

    def test_o_verbo_conjugado_nao_parte(self) -> None:
        """`transferem` não está no léxico, e `transfer` + `em` estão. Só o `f` paga direita curta."""
        self.assertIsNone(self._cortes("transferem", [8]))
        self.assertIsNone(self._cortes("romperam", [6]))

    def test_sem_candidato_do_vao_nao_parte(self) -> None:
        self.assertIsNone(self._cortes("ofthe", []))

    def test_ambiguidade_nao_corrige(self) -> None:
        lexico = frozenset({"abcd", "efghij", "abcdef", "ghij"})
        self.assertEqual(fronteira.cortes(list("abcdefghij"), [4], lexico, frozenset()), [4])
        self.assertIsNone(fronteira.cortes(list("abcdefghij"), [4, 6], lexico, frozenset()))

    def test_a_palavra_de_uma_letra_nao_parte(self) -> None:
        self.assertIsNone(self._cortes("eknight", [1]))


class VaoDeBaixoTests(unittest.TestCase):
    """O `f` tem o gancho no alto: o vão entre os bboxes engana, e o de baixo não."""

    def _folha(self, vao: int) -> tuple[np.ndarray, list[str], list[Caixa]]:
        """`of the`, com o gancho do `f` avançando até `vao` px da letra seguinte, só no alto da caixa."""
        binaria = np.zeros((120, 200), dtype=np.uint8)
        caixas = []
        x = 10
        for char, largura, altura in [("o", 12, 20), ("f", 8, 28), ("t", 8, 26), ("h", 12, 28), ("e", 12, 20), ("a", 12, 20)]:
            y1 = 100 - altura
            if char == "f":
                binaria[y1:100, x : x + 3] = 255
                binaria[y1 : y1 + 3, x : x + largura] = 255
            else:
                binaria[y1:100, x : x + largura] = 255
            caixas.append(Caixa(x, y1, x + largura, 100))
            x += largura + (vao if char == "f" else 2)
        return (binaria, list("ofthea"), caixas)

    def test_o_vao_de_baixo_mede_a_haste_do_f(self) -> None:
        binaria, _, caixas = self._folha(4)
        self.assertEqual(fronteira.vao_de_baixo(binaria, caixas[1], caixas[2], 100.0, 20.0), 9.0)

    def test_parte_of_the(self) -> None:
        binaria, chars, caixas = self._folha(4)
        lidos = fronteira.corrigir(_lidos(chars), caixas, binaria, frozenset({"nada"}), frozenset({"nada"}), xh=20.0)
        self.assertEqual(_texto(lidos), "ofthea", "`thea` não é palavra: sem léxico, não parte")
        lidos = fronteira.corrigir(_lidos(chars), caixas, binaria, frozenset({"thea"}), frozenset({"thea"}), xh=20.0)
        self.assertEqual(_texto(lidos), "of thea")

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        binaria, chars, caixas = self._folha(4)
        with mock.patch.object(fronteira, "LIGADO", False):
            lidos = fronteira.corrigir(_lidos(chars), caixas, binaria, frozenset({"thea"}), frozenset({"thea"}), xh=20.0)
        self.assertEqual(_texto(lidos), "ofthea")

    def test_o_espaco_nao_conta_como_caractere(self) -> None:
        """`por_caractere` do leitor pula o espaço: a confiança por letra continua casando."""
        binaria, chars, caixas = self._folha(4)
        lidos = fronteira.corrigir(_lidos(chars), caixas, binaria, frozenset({"thea"}), frozenset({"thea"}), xh=20.0)
        self.assertEqual(sum(not letra.isspace() for c, _ in lidos for letra in c), len(chars))

    def test_a_casa_no_fim_da_frase_nao_parte(self) -> None:
        self.assertIsNone(fronteira._corte_antes_de_lance(list("e7."), [1]), "`e` não está na lista")

    def test_of_antes_do_numero_de_lance(self) -> None:
        self.assertEqual(fronteira._corte_antes_de_lance(list("of2.exf6"), [2]), 2)
        self.assertIsNone(fronteira._corte_antes_de_lance(list("Be2."), [2]), "`Be2.` é lance")
        self.assertIsNone(fronteira._corte_antes_de_lance(list("of2"), [2]), "sem o ponto, pode ser casa")


class VaosDoCorteTests(unittest.TestCase):
    """As duas réguas do corte, com vão e caixa de verdade: sem elas, o léxico sozinho parte o que não deve."""

    LEXICO = frozenset({"thea", "alma", "unto", "like"})

    def _folha(self, esquerda: str, direita: str, cima: int, baixo: int) -> tuple[np.ndarray, list[str], list[Caixa]]:
        """Blocos de 12x20, e entre as metades `cima` px de vão no alto e `baixo` px de vão embaixo.

        O último bloco da esquerda tem um braço no alto, como o `r`, que come o vão de cima: o de baixo é maior.
        """
        binaria = np.zeros((120, 400), dtype=np.uint8)
        chars, caixas = [], []
        x = 10
        for k, char in enumerate(esquerda):
            ultimo = k == len(esquerda) - 1
            largura = 12 + (baixo - cima if ultimo else 0)
            binaria[80:100, x : x + 12] = 255
            if ultimo:
                binaria[80:84, x : x + largura] = 255
            caixas.append(Caixa(x, 80, x + largura, 100))
            chars.append(char)
            x += largura + (cima if ultimo else 2)
        for char in direita:
            binaria[80:100, x : x + 12] = 255
            caixas.append(Caixa(x, 80, x + 12, 100))
            chars.append(char)
            x += 14
        return (binaria, chars, caixas)

    def _ler(self, cima: int, baixo: int, esquerda: str = "un", direita: str = "like") -> str:
        binaria, chars, caixas = self._folha(esquerda, direita, cima, baixo)
        # com o vão largo em toda parte, `palavras` cortaria sozinha: aqui ela fica de fora
        with mock.patch("chess_diagram_ocr.text.dicionario.palavras", lambda c, _: [(0, len(c))]):
            return _texto(fronteira.corrigir(_lidos(chars), caixas, binaria, self.LEXICO, self.LEXICO, xh=20.0))

    def test_com_os_dois_vaos_parte(self) -> None:
        self.assertEqual(self._ler(cima=4, baixo=10), "un like")

    def test_sem_vao_embaixo_nao_parte(self) -> None:
        """`unlikely`, em que `n|l` não tem vão de palavra: 0,10 de altura-de-x, abaixo do mínimo de 0,30."""
        self.assertEqual(self._ler(cima=4, baixo=2), "unlike")
        self.assertEqual(self._ler(cima=4, baixo=4), "unlike", "0,20 ainda é o vão de dentro da palavra")

    def test_sem_vao_em_cima_nao_parte(self) -> None:
        """O braço do `r` encosta: é por isso que `carrying` não parte, ainda que os pedaços existissem."""
        self.assertEqual(self._ler(cima=1, baixo=10), "unlike")

    def test_vao_de_cima_negativo_nao_parte(self) -> None:
        self.assertEqual(self._ler(cima=-1, baixo=10), "unlike")

    def test_depois_do_f_o_vao_de_cima_nao_conta(self) -> None:
        """O gancho do `f` come o vão de cima, e é a exceção que dá nome ao item."""
        self.assertEqual(self._ler(cima=1, baixo=10, esquerda="of", direita="like"), "of like")

    def test_o_lance_tambem_precisa_do_vao(self) -> None:
        binaria, chars, caixas = self._folha("in", "2.", 1, 10)
        with mock.patch("chess_diagram_ocr.text.dicionario.palavras", lambda c, _: [(0, len(c))]):
            lidos = fronteira.corrigir(_lidos(chars), caixas, binaria, self.LEXICO, self.LEXICO, xh=20.0)
        self.assertEqual(_texto(lidos), "in2.")
        binaria, chars, caixas = self._folha("in", "2.", 4, 10)
        with mock.patch("chess_diagram_ocr.text.dicionario.palavras", lambda c, _: [(0, len(c))]):
            lidos = fronteira.corrigir(_lidos(chars), caixas, binaria, self.LEXICO, self.LEXICO, xh=20.0)
        self.assertEqual(_texto(lidos), "in 2.")


class JuntarTests(unittest.TestCase):
    """S-732, a outra direção: `ganhando` saía `ga n ha ndo`."""

    LEXICO = frozenset({"ganhando", "estavam", "maybe", "partida", "cutoff", "apartida", "variantes"})

    def test_junta_o_que_nao_existe(self) -> None:
        self.assertEqual(fronteira.juntar("ga n ha ndo", self.LEXICO), "ganhando")
        self.assertEqual(fronteira.juntar("muito estava m aqui", self.LEXICO | {"estava"}), "muito estavam aqui")
        self.assertEqual(fronteira.juntar("as va riantes,", self.LEXICO), "as variantes,")

    def test_nao_junta_o_que_existe(self) -> None:
        self.assertEqual(fronteira.juntar("may be", self.LEXICO), "may be")
        self.assertEqual(fronteira.juntar("cut off", self.LEXICO), "cut off", "três letras contam como existentes")
        self.assertEqual(fronteira.juntar("a partida", self.LEXICO), "a partida")

    def test_notacao_nao_entra(self) -> None:
        self.assertEqual(fronteira.juntar("1 5", self.LEXICO), "1 5")

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(fronteira, "JUNTAR_PARTIDAS", False):
            self.assertEqual(fronteira.juntar("ga n ha ndo", self.LEXICO), "ga n ha ndo")


class ColadoPeloLexicoTests(unittest.TestCase):
    """S-732: o léxico no lugar da confiança, que recusa o `tu` colado por 0,007."""

    def _ler(self, palavra: str, suspeito: int, pedacos: list[list[str]], lexico: frozenset[str], sem_nomes: frozenset[str] | None = None) -> str:
        desenho = [(c, 30 if k == suspeito else 10, 20) for k, c in enumerate(palavra)]
        chars, caixas = _linha(desenho, vao=1)
        binaria = np.zeros((120, 400), dtype=np.uint8)
        for c in caixas:
            binaria[c.y1 : c.y2, c.x1 : c.x2] = 255
        grande = caixas[suspeito]
        meio = (grande.x1 + grande.x2) // 2
        binaria[grande.y1 : grande.y2, meio] = 0  # o vale
        ler = lambda _: [[(c, 0.5) for c in lista] for lista in pedacos]  # noqa: E731
        lidos = colados.por_lexico(
            _lidos(chars), caixas, binaria, lexico, lexico if sem_nomes is None else sem_nomes, ler, xh=20.0
        )
        return _texto(lidos)

    def test_o_tu_colado(self) -> None:
        self.assertEqual(self._ler("smdy", 1, [["t"], ["u"]], frozenset({"study"})), "study")

    def test_o_defeito_volta_com_a_constante_desligada(self) -> None:
        with mock.patch.object(colados, "POR_LEXICO", False):
            self.assertEqual(self._ler("smdy", 1, [["t"], ["u"]], frozenset({"study"})), "smdy")

    def test_a_palavra_que_existe_nao_e_examinada(self) -> None:
        self.assertEqual(self._ler("comer", 2, [["r"], ["n"]], frozenset({"comer", "corner"})), "comer")

    def test_palavra_de_tres_letras_nao_e_erro(self) -> None:
        """`bom` não está no léxico por ter 3 letras, e virava `born`."""
        self.assertEqual(self._ler("bom", 2, [["r"], ["n"]], frozenset({"born"})), "bom")
        self.assertEqual(self._ler("dum", 2, [["r"], ["n"]], frozenset({"durn"})), "dum", "fora da lista das curtas")

    def test_caixa_estreita_nao_e_suspeita(self) -> None:
        """`Halberstadt`->`Halberstdt`, com o piso de largura baixo: um `a` qualquer tem vale, e dois pedaços."""
        chars, caixas = _linha([(c, 12, 20) for c in "Halberstdat"], vao=1)
        binaria = np.zeros((120, 400), dtype=np.uint8)
        for c in caixas:
            binaria[c.y1 : c.y2, c.x1 : c.x2] = 255
            binaria[c.y1 : c.y2, (c.x1 + c.x2) // 2] = 0
        ler = lambda _: [[("a", 0.5)], [("t", 0.5)]]  # noqa: E731
        lido = colados.por_lexico(_lidos(chars), caixas, binaria, frozenset({"halberstdatat"}), frozenset(), ler, xh=20.0)
        self.assertEqual(_texto(lido), "Halberstdat")

    def test_caixa_alta_e_estreita_nao_e_suspeita(self) -> None:
        """Passa do piso de largura pela altura-de-x, mas é mais alta que larga: não tem dois glifos."""
        chars, caixas = _linha([("a", 12, 20), ("b", 18, 40), ("c", 12, 20), ("d", 12, 20)], vao=1)
        binaria = np.zeros((120, 400), dtype=np.uint8)
        for c in caixas:
            binaria[c.y1 : c.y2, c.x1 : c.x2] = 255
            binaria[c.y1 : c.y2, (c.x1 + c.x2) // 2] = 0
        ler = lambda _: [[("x", 0.5)], [("y", 0.5)]]  # noqa: E731
        lido = colados.por_lexico(_lidos(chars), caixas, binaria, frozenset({"axycd"}), frozenset(), ler, xh=20.0)
        self.assertEqual(_texto(lido), "abcd")

    def test_digito_fora_da_caixa_relida_barra(self) -> None:
        """`cof7ect` é relido, e `co7mect` não: aquele dígito é tinta do livro."""
        self.assertEqual(self._ler("cof7ect", 2, [["r"], ["r"]], frozenset({"correct"})), "cof7ect")
        chars, caixas = _linha([("c", 10, 20), ("o", 10, 20), ("f7", 30, 28), ("e", 10, 20), ("c", 10, 20), ("t", 10, 26)], vao=1)
        binaria = np.zeros((120, 400), dtype=np.uint8)
        for c in caixas:
            binaria[c.y1 : c.y2, c.x1 : c.x2] = 255
        grande = caixas[2]
        binaria[grande.y1 : grande.y2, (grande.x1 + grande.x2) // 2] = 0
        ler = lambda _: [[("r", 0.5)], [("r", 0.5)]]  # noqa: E731
        lido = colados.por_lexico(_lidos(chars), caixas, binaria, frozenset({"correct"}), frozenset({"correct"}), ler, xh=20.0)
        self.assertEqual(_texto(lido), "correct")
        chars[3] = "7"
        lido = colados.por_lexico(_lidos(chars), caixas, binaria, frozenset({"corr7ct"}), frozenset({"corr7ct"}), ler, xh=20.0)
        self.assertEqual(_texto(lido), "cof77ct")

    def test_o_w_nao_entra(self) -> None:
        self.assertEqual(self._ler("paws", 2, [["v"], ["v"]], frozenset({"pavvs"})), "paws")

    def test_pedaco_tem_de_ser_letra(self) -> None:
        """O falso positivo medido: `]!]ZWang`, porque a pontuação das pontas sai na consulta."""
        self.assertEqual(self._ler("smdy", 1, [["t"], ["!"]], frozenset({"st!dy", "study"})), "smdy")

    def test_maiuscula_no_meio_nao_vale(self) -> None:
        """`movem`->`moNIem`, com `Moniem` na lista de nomes."""
        self.assertEqual(self._ler("movems", 2, [["N"], ["I"]], frozenset({"monIems"})), "movems")

    def test_resposta_curta_so_do_lexico_sem_nomes(self) -> None:
        self.assertEqual(self._ler("Bemb", 2, [["n"], ["i"]], frozenset({"benib"}), frozenset()), "Bemb")

    def test_ambiguidade_nao_corrige(self) -> None:
        self.assertEqual(self._ler("smdy", 1, [["t"], ["u", "a"]], frozenset({"study", "stady"})), "smdy")


class LimiaresDoCorteTests(VaosDoCorteTests):
    def test_o_vao_de_baixo_de_0_30(self) -> None:
        self.assertEqual(self._ler(cima=4, baixo=7), "un like", "0,35")
        self.assertEqual(self._ler(cima=4, baixo=5), "unlike", "0,25")

    def test_o_vao_de_cima_de_0_15(self) -> None:
        self.assertEqual(self._ler(cima=3, baixo=10), "un like", "0,15")
        self.assertEqual(self._ler(cima=2, baixo=10), "unlike", "0,10")

    def _com_tinta_em(self, y0: int, y1: int) -> str:
        """`of like`, com um traço saindo da letra da esquerda na altura dada, entre as duas metades."""
        binaria, chars, caixas = self._folha("of", "like", 4, 10)
        f = caixas[1]
        binaria[y0:y1, f.x1 : f.x2] = 255
        with mock.patch("chess_diagram_ocr.text.dicionario.palavras", lambda c, _: [(0, len(c))]):
            return _texto(fronteira.corrigir(_lidos(chars), caixas, binaria, self.LEXICO, self.LEXICO, xh=20.0))

    def test_a_faixa_do_vao_e_de_0_6(self) -> None:
        """Tinta acima da faixa não conta, e tinta dentro dela conta: `y` 88 é o limite, com base 100 e x 20."""
        self.assertEqual(self._com_tinta_em(84, 87), "of like")
        self.assertEqual(self._com_tinta_em(90, 93), "oflike")


class ListaAntesDoLanceTests(unittest.TestCase):
    def test_cada_palavra_da_lista(self) -> None:
        for palavra in ("of", "if", "in", "on", "at", "by", "to", "and", "or", "de", "em", "ou", "com"):  # literal
            k = len(palavra)
            self.assertEqual(fronteira._corte_antes_de_lance(list(palavra + "2.exf6"), [k]), k, palavra)


class LimiaresDosPedacosTests(unittest.TestCase):
    def test_direita_de_tres_letras_sem_f(self) -> None:
        self.assertEqual(fronteira.cortes(list("joganos"), [4], frozenset({"joga"}), frozenset()), [4])

    def test_esquerda_de_duas_letras(self) -> None:
        self.assertEqual(fronteira.cortes(list("seperdem"), [2], frozenset({"perdem"}), frozenset()), [2])

    def test_nome_a_partir_de_seis(self) -> None:
        self.assertEqual(fronteira.cortes(list("Kasimdjoga"), [6], frozenset({"joga"}), frozenset({"kasimd", "joga"})), [6])
        self.assertIsNone(fronteira.cortes(list("Kasimjoga"), [5], frozenset({"joga"}), frozenset({"kasim", "joga"})))

    def test_juncao_a_partir_de_cinco_letras(self) -> None:
        self.assertEqual(fronteira.juntar("ga to", frozenset({"gato"})), "ga to")
        self.assertEqual(fronteira.juntar("ga nho", frozenset({"ganho"})), "ganho")

    def test_juncao_de_ate_quatro_tokens(self) -> None:
        self.assertEqual(fronteira.juntar("g a n ha ndo", frozenset({"ganhando"})), "g a n ha ndo")


class LimiaresDoColadoTests(unittest.TestCase):
    def _ler(self, desenho: list[tuple[str, int, int]], pedacos: tuple[str, str], lexico: frozenset[str], sem_nomes: frozenset[str] | None = None) -> str:
        chars, caixas = _linha(desenho, vao=1)
        binaria = np.zeros((120, 500), dtype=np.uint8)
        for c in caixas:
            binaria[c.y1 : c.y2, c.x1 : c.x2] = 255
            binaria[c.y1 : c.y2, (c.x1 + c.x2) // 2] = 0
        ler = lambda _: [[(pedacos[0], 0.5)], [(pedacos[1], 0.5)]]  # noqa: E731
        return _texto(colados.por_lexico(_lidos(chars), caixas, binaria, lexico, lexico if sem_nomes is None else sem_nomes, ler, xh=20.0))

    def test_a_largura_do_suspeito(self) -> None:
        desenho = [("a", 12, 20), ("m", 18, 20), ("o", 12, 20), ("s", 12, 20)]
        self.assertEqual(self._ler(desenho, ("r", "n"), frozenset({"arnos"})), "arnos", "0,90 altura-de-x")
        desenho = [("a", 12, 20), ("m", 16, 20), ("o", 12, 20), ("s", 12, 20)]
        self.assertEqual(self._ler(desenho, ("r", "n"), frozenset({"arnos"})), "amos", "0,80")

    def test_a_proporcao_do_suspeito(self) -> None:
        desenho = [("a", 12, 20), ("m", 18, 29), ("o", 12, 20), ("s", 12, 20)]
        self.assertEqual(self._ler(desenho, ("r", "n"), frozenset({"arnos"})), "arnos", "0,62")
        desenho = [("a", 12, 20), ("m", 18, 31), ("o", 12, 20), ("s", 12, 20)]
        self.assertEqual(self._ler(desenho, ("r", "n"), frozenset({"arnos"})), "amos", "0,58")

    def test_no_maximo_quatro_suspeitos(self) -> None:
        grande = [("e", 20, 20), ("o", 20, 20), ("a", 20, 20), ("u", 20, 20)]
        self.assertEqual(self._ler([*grande, ("s", 12, 20)], ("r", "n"), frozenset({"eoarns"})), "eoarns", "o quarto")
        self.assertEqual(self._ler([*grande, ("i", 20, 20)], ("r", "n"), frozenset({"eoaurn"})), "eoaui", "o quinto")

    def test_a_resposta_so_de_nome_tem_sete_letras(self) -> None:
        desenho = [("a", 12, 20), ("b", 12, 28), ("m", 20, 20), ("d", 12, 28), ("e", 12, 20), ("o", 12, 20)]
        self.assertEqual(self._ler(desenho, ("r", "n"), frozenset({"abrndeo"}), frozenset()), "abrndeo")
        desenho = desenho[:-1]
        self.assertEqual(self._ler(desenho, ("r", "n"), frozenset({"abrnde"}), frozenset()), "abmde")


if __name__ == "__main__":
    unittest.main()
