"""A regra do lote de digitação, sem widget (S-521).

**Por que ela é pura e mora em `ui/texto_declarado.py`.** O que decide se `Ctrl+Z` devolve uma
letra ou uma palavra não tem nada de Qt: é uma comparação entre a edição que chega e a que veio
antes. Deixá-la dentro do ouvinte do painel obrigaria a abrir uma janela para afirmar que `abc`
é um lote -- e a pergunta não é sobre janela nenhuma.

O quarto fecho da S-521 -- passar por uma ferramenta -- **não** está aqui: ele é do painel, porque
só ele sabe que a ferramenta rodou. Está em `test_qt_texto.py::DigitacaoTests`.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui import texto_declarado as declarado


def lotes_de(escrito: str) -> int:
    """Quantas entradas de desfazer a digitação de `escrito` produz, letra a letra.

    É o ouvinte do painel reduzido à parte pura: cada caractere é uma edição contígua de inserção,
    que é o que `QTest.keyClicks` gera.
    """
    lote: declarado.Lote | None = None
    junta = 0
    quantos = 0
    for caractere in escrito:
        if declarado.abre_lote(lote, inserindo=True, junta=junta):
            quantos += 1
        junta += 1
        lote = declarado.lote_apos(inserindo=True, junta=junta, escrito=caractere)
    return quantos


class SeparadorTests(unittest.TestCase):
    """A granularidade é a palavra, e é o espaço e a pontuação que a marcam."""

    def test_o_branco_e_a_pontuacao_separam(self) -> None:
        for caractere in (" ", "\t", "\n", ".", ",", ";", "!", "?", "(", ")"):
            with self.subTest(caractere=caractere):
                self.assertTrue(declarado.separa_palavra(caractere))

    def test_a_letra_e_o_digito_nao_separam(self) -> None:
        for caractere in ("a", "Z", "4", "ç", "ã", "-"):
            with self.subTest(caractere=caractere):
                self.assertFalse(declarado.separa_palavra(caractere))


class LoteTests(unittest.TestCase):
    """Os três fechos que a regra pura decide."""

    def test_sem_lote_aberto_a_primeira_edicao_abre(self) -> None:
        self.assertTrue(declarado.abre_lote(None, inserindo=True, junta=0))

    def test_continuar_escrevendo_no_mesmo_ponto_nao_abre(self) -> None:
        lote = declarado.Lote(inserindo=True, junta=7)
        self.assertFalse(declarado.abre_lote(lote, inserindo=True, junta=7))

    def test_mudar_de_tipo_abre(self) -> None:
        """**Escrever e apagar não se juntam.** Um `Ctrl+Z` sobre a mistura devolveria um estado
        que ninguém digitou -- meia palavra escrita e meia apagada."""
        lote = declarado.Lote(inserindo=True, junta=7)
        self.assertTrue(declarado.abre_lote(lote, inserindo=False, junta=7))

    def test_o_cursor_andar_abre(self) -> None:
        """Digitar no fim da frase e depois no começo são duas edições, não uma."""
        lote = declarado.Lote(inserindo=True, junta=7)
        self.assertTrue(declarado.abre_lote(lote, inserindo=True, junta=2))

    def test_o_separador_fecha_o_lote_que_ele_termina(self) -> None:
        """O espaço entra no lote e o encerra: desfazer tira `b`, e o seguinte tira `a ` inteiro."""
        self.assertIsNone(declarado.lote_apos(inserindo=True, junta=2, escrito=" "))
        self.assertIsNone(declarado.lote_apos(inserindo=True, junta=9, escrito="fim."))

    def test_a_letra_mantem_o_lote_aberto(self) -> None:
        lote = declarado.lote_apos(inserindo=True, junta=3, escrito="a")
        self.assertEqual(lote, declarado.Lote(inserindo=True, junta=3))

    def test_apagar_nao_fecha_por_separador(self) -> None:
        """**Apagar um espaço não fecha o lote.** O fecho por separador é da escrita: quem apaga
        uma frase com `Backspace` atravessa espaços o tempo todo, e um lote por palavra apagada
        faria `Ctrl+Z` devolver a frase aos pedaços."""
        self.assertEqual(
            declarado.lote_apos(inserindo=False, junta=4, escrito=" "),
            declarado.Lote(inserindo=False, junta=4),
        )


class PalavraTests(unittest.TestCase):
    """**O critério de aceite da S-521**, na forma em que ele foi escrito."""

    def test_uma_palavra_e_um_lote_e_duas_sao_dois(self) -> None:
        self.assertEqual(lotes_de("abc"), 1)
        self.assertEqual(lotes_de("a b"), 2)

    def test_uma_frase_de_tres_palavras_e_tres_lotes_e_nao_quinze(self) -> None:
        """A frase do critério: *"três palavras é três entradas na pilha, não quinze"*."""
        frase = "o bispo vai"
        self.assertEqual(lotes_de(frase), 3)
        self.assertGreater(len(frase), 3, "sem isto o teste não separa lote de caractere")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
