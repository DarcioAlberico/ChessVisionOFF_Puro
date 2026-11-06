"""S-744: `f a t a l e n` volta a `fatalen` quando o léxico concorda, e nunca junta duas palavras."""

from __future__ import annotations

import unittest
from unittest import mock

from chess_diagram_ocr.text import espacado

LISTA = frozenset({"fatalen", "bauer", "figur", "kombinierte", "einer", "feindlichen", "mittel", "abcd", "sicherheit"})
CURTAS = frozenset({"der", "die", "in", "an", "ein", "am", "a", "e", "o"})


def _juntar(texto: str, **extra: object) -> str:
    return espacado.juntar(texto, LISTA, curtas=CURTAS, **extra)  # type: ignore[arg-type]


class JuntarTests(unittest.TestCase):
    def test_a_palavra_que_o_lexico_conhece_volta(self) -> None:
        self.assertEqual(_juntar("den f a t a l e n Zug"), "den fatalen Zug")

    def test_a_palavra_que_o_lexico_nao_conhece_fica(self) -> None:
        self.assertEqual(_juntar("den x y l o p h o n Zug"), "den x y l o p h o n Zug")

    def test_caixa_e_pontuacao_sao_as_da_leitura(self) -> None:
        self.assertEqual(_juntar("(F i g u r, B A U E R."), "(Figur, BAUER.")

    def test_fragmento_de_duas_letras_entra(self) -> None:
        self.assertEqual(_juntar("F i gu r"), "Figur")
        self.assertEqual(_juntar("in S i c h e r he i t."), "in Sicherheit.")

    def test_duas_palavras_ficam_duas(self) -> None:
        """A junção só existe se ela mesma é palavra: é o que a saída do item proíbe."""
        self.assertEqual(_juntar("d e r B a u e r"), "der Bauer")
        self.assertEqual(_juntar("e i n e r fe i nd li ch e n"), "einer feindlichen")

    def test_a_prosa_de_palavra_curta_nao_e_corrida(self) -> None:
        for prosa in ("a o", "e a", "in der Zeit", "am an in", "o a e a"):
            with self.subTest(prosa):
                self.assertEqual(_juntar(prosa), prosa)

    def test_sobrou_letra_a_corrida_fica(self) -> None:
        """`d e sHan d e 1 n s`: a primeira versão achava palavra no meio do que veio errado."""
        lista = frozenset({"shan", "mittel"})
        self.assertEqual(espacado.juntar("d e s h a n d e", lista), "d e s h a n d e")

    def test_a_maiuscula_abre_palavra(self) -> None:
        self.assertEqual(_juntar("F i g u r i n V e r k e t"), "Figur in V e r k e t")

    def test_na_palavra_a_caixa_e_de_palavra(self) -> None:
        self.assertEqual(espacado.juntar("s H a n", frozenset({"shan"})), "s H a n")
        self.assertEqual(espacado.juntar("S H A N x", frozenset({"shan"})), "S H A N x")

    def test_a_corrida_toda_em_maiusculas_e_uma_so(self) -> None:
        self.assertEqual(_juntar("B A U E R"), "BAUER")

    def test_letra_repetida_nao_e_palavra(self) -> None:
        self.assertEqual(espacado.juntar("o o o o", frozenset({"oooo"})), "o o o o")

    def test_na_duvida_entre_duas_coberturas_nada_se_decide(self) -> None:
        lista = frozenset({"klmn", "mnop"})
        curtas = frozenset({"op", "kl"})
        self.assertEqual(espacado.juntar("k l m n o p", lista, curtas=curtas), "k l m n o p")

    def test_a_cobertura_de_menos_pedacos_ganha(self) -> None:
        lista = frozenset({"klmnop", "klmn"})
        self.assertEqual(espacado.juntar("k l m n o p", lista, curtas=frozenset({"op"})), "klmnop")

    def test_a_fileira_de_casas_nao_e_palavra(self) -> None:
        self.assertEqual(_juntar("a b c d"), "a b c d")
        self.assertEqual(_juntar("d c b a"), "d c b a")

    def test_o_nome_so_vale_com_a_corrida_toda_de_uma_letra(self) -> None:
        nomes = frozenset({"yasu", "morphy"})
        self.assertEqual(espacado.juntar("Y a su", nomes, so_da_lingua=frozenset()), "Y a su")
        self.assertEqual(espacado.juntar("M o r p h y", nomes, so_da_lingua=frozenset()), "Morphy")

    def test_o_nome_so_vale_com_maiuscula(self) -> None:
        """`Hande l u n d`: é a `und` com a letra de antes, e `Lund` está na lista dos nomes."""
        self.assertEqual(espacado.juntar("l u n d", frozenset({"lund"}), so_da_lingua=frozenset()), "l u n d")

    def test_a_letra_da_palavra_ao_lado_nao_abre_outra(self) -> None:
        """`M itte l u n d Z we ck`: `Lund` existe, e aqui é o `l` de `Mittel` e `und`."""
        lista = frozenset({"lund", "zweck"})
        curtas = frozenset({"und"})
        self.assertEqual(espacado.juntar("M itte l u n d Z we ck", lista, curtas=curtas), "M itte l u n d Zweck")
        self.assertEqual(espacado.juntar("der l u n d Z we ck", lista, curtas=curtas | {"der"}), "der lund Zweck")

    def test_a_letra_que_vai_para_a_palavra_de_depois(self) -> None:
        lista = frozenset({"undk"})
        curtas = frozenset({"und"})
        self.assertEqual(espacado.juntar("u n d k xyz", lista, curtas=curtas), "u n d k xyz")

    def test_digito_e_lance_nao_entram(self) -> None:
        self.assertEqual(_juntar("1 e b e n d i"), "1 e b e n d i")
        self.assertEqual(_juntar("1 e4 c5 2 f3"), "1 e4 c5 2 f3")

    def test_sem_lista_nada_acontece(self) -> None:
        self.assertEqual(espacado.juntar("f a t a l e n", frozenset()), "f a t a l e n")

    def test_a_constante_desliga(self) -> None:
        with mock.patch.object(espacado, "JUNTAR_ESPACADO", False):
            self.assertEqual(_juntar("f a t a l e n"), "f a t a l e n")

    def test_a_contagem_de_letras_nao_muda(self) -> None:
        """`confiancas` tem um número por caractere que não é espaço, e sobrevive a isto."""
        antes = "den (F i g u r, und d e r B a u e r."
        depois = _juntar(antes)
        self.assertEqual("".join(antes.split()), "".join(depois.split()))


class IntervalosTests(unittest.TestCase):
    def test_o_intervalo_acompanha_o_texto(self) -> None:
        antes = "den f a t a l e n Zug"
        depois = _juntar(antes)
        self.assertEqual(depois, "den fatalen Zug")
        pedidos = ((0, 3), (4, 17), (18, 21))
        self.assertEqual(
            [depois[a:b] for a, b in espacado.intervalos_depois(antes, depois, pedidos)], ["den", "fatalen", "Zug"]
        )

    def test_sem_mudanca_e_o_mesmo(self) -> None:
        self.assertEqual(espacado.intervalos_depois("abc", "abc", ((0, 3),)), ((0, 3),))


class NaLinguaTests(unittest.TestCase):
    def test_lingua_sem_lista(self) -> None:
        self.assertEqual(espacado.juntar_na_lingua("f a t a l e n", "xxx"), "f a t a l e n")

    def test_a_lista_alema_empacotada(self) -> None:
        self.assertEqual(espacado.juntar_na_lingua("k o m b i n i e r t e", "deu"), "kombinierte")


class FiacaoTests(unittest.TestCase):
    def test_ler_pagina_chama_a_juncao_nas_linhas_do_glifo(self) -> None:
        from chess_diagram_ocr.text import leitor
        from chess_diagram_ocr.text.boxes import Caixa

        cruas = [leitor._Cru("den k o m b i n i e r t e Zug", Caixa(0, 0, 10, 10), 0.9, "glifo", revisar_em=((4, 25),))]
        saida = leitor._sem_espacado(cruas, "deu")
        self.assertEqual(saida[0].texto, "den kombinierte Zug")
        self.assertEqual(saida[0].revisar_em, ((4, 15),))


if __name__ == "__main__":
    unittest.main()
