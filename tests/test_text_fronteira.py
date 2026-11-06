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

    def test_of_antes_do_numero_de_lance(self) -> None:
        self.assertEqual(fronteira._corte_antes_de_lance(list("of2.exf6"), [2]), 2)
        self.assertIsNone(fronteira._corte_antes_de_lance(list("Be2."), [2]), "`Be2.` é lance")
        self.assertIsNone(fronteira._corte_antes_de_lance(list("of2"), [2]), "sem o ponto, pode ser casa")


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


if __name__ == "__main__":
    unittest.main()
