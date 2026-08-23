"""Onde uma linha acaba e a próxima começa (S-187).

**Cada teste aqui é uma cicatriz.** O corte de linha parece trivial até encontrar o apóstrofo, a
vírgula e a troca de coluna — os três quebram a régua ingênua de formas diferentes, e os três
custaram uma fase cada no projeto de origem (F63, F65 e F61). Os nomes dos testes são o registro
disso; sem eles, o próximo a passar por aqui "simplifica" a regra e reintroduz os 69 cortes no
meio de linha.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.linhas import (
    CAIXA_CURTA,
    FOLGA_DE_COLUNA,
    FOLGA_DE_LINHA,
    envolve,
    ordem_em_faixa,
    quebrar_em_linhas,
    texto_da_linha,
)

ALTURA = 20
"""Altura de letra do fixture. Tudo abaixo é em frações dela, como no código."""


def letra(x: int, y: int = 100, *, largura: int = 14, altura: int = ALTURA, angulo: int = 0) -> Caixa:
    return Caixa(x, y, x + largura, y + altura, angulo)


def curta(x: int, y: int, *, altura: int = 6) -> Caixa:
    """Apóstrofo, vírgula, ponto: caixa que não tem altura de letra."""
    return Caixa(x, y, x + 5, y + altura)


class QuebraSimplesTests(unittest.TestCase):
    def test_uma_linha_continua_uma_linha(self) -> None:
        linha = [letra(x) for x in range(0, 140, 20)]
        self.assertEqual([linha], quebrar_em_linhas(linha))

    def test_voltar_para_a_esquerda_e_fim_de_linha(self) -> None:
        primeira = [letra(x, 100) for x in (0, 20, 40, 60)]
        segunda = [letra(x, 130) for x in (0, 20, 40)]
        self.assertEqual([primeira, segunda], quebrar_em_linhas([*primeira, *segunda]))

    def test_descer_sem_voltar_tambem_e_fim_de_linha(self) -> None:
        primeira = [letra(x, 100) for x in (0, 20)]
        segunda = [letra(x, 100 + ALTURA * 2) for x in (40, 60)]
        self.assertEqual([primeira, segunda], quebrar_em_linhas([*primeira, *segunda]))

    def test_sequencia_vazia(self) -> None:
        self.assertEqual([], quebrar_em_linhas([]))


class ApostrofoTests(unittest.TestCase):
    """F63 e F65: a caixa curta plantada no alto partia a prosa em pedaços."""

    def test_o_apostrofo_nao_abre_linha_nova_por_ter_subido(self) -> None:
        """`we can` / `'t say that` — o apóstrofo mora na altura de ascendente.

        Chegando depois de `can`, que é todo altura de x, ele fica acima do topo da linha. A
        régua ingênua o lê como coluna vizinha. Medido no projeto de origem: o apóstrofo sobe
        0,08-0,14 alturas medianas e a troca de coluna sobe 66-104 — o vão é de 470x, e é por
        isso que a `FOLGA_DE_COLUNA` pode ser generosa sem risco.
        """
        can = [letra(x, 100) for x in (0, 20, 40)]
        apostrofo = curta(60, 96)  # bem no alto, acima do topo da linha
        resto = [letra(x, 100) for x in (70, 90)]
        self.assertEqual(1, len(quebrar_em_linhas([*can, apostrofo, *resto])))

    def test_a_letra_depois_do_apostrofo_nao_parece_ter_descido(self) -> None:
        """F63: a régua contra a **caixa anterior** fazia a letra seguinte descer de linha.

        O fundo de um apóstrofo fica acima da altura de x, e qualquer letra normal tem o centro
        abaixo dele. Contra a **linha inteira**, não: a base é a do que já é letra.
        """
        antes = [letra(x, 100) for x in (0, 20)]
        apostrofo = curta(40, 96)
        depois = [letra(x, 100) for x in (50, 70)]
        self.assertEqual(1, len(quebrar_em_linhas([*antes, apostrofo, *depois])))

    def test_a_caixa_curta_nao_fixa_a_base_da_linha(self) -> None:
        """Uma linha que **começa** com aspas teria a régua no fundo das aspas.

        Sem esta regra o defeito volta pela porta dos fundos: a primeira letra de verdade, que
        desce bem abaixo do fundo das aspas, seria lida como linha nova.
        """
        aspas = curta(0, 96)
        letras = [letra(x, 100) for x in (10, 30, 50)]
        self.assertEqual(1, len(quebrar_em_linhas([aspas, *letras])))


class VirgulaTests(unittest.TestCase):
    def test_a_virgula_que_raspa_a_base_nao_abre_linha(self) -> None:
        """Ela desce um fio abaixo da linha de base, e sem folga isso é "desceu uma linha".

        Medido no projeto de origem, os 26 cortes que sobravam se separam em dois montes sem nada
        entre eles: vírgula em 0,02 altura mediana (11 casos), quebra de verdade em 0,66-4,88
        (15 casos).
        """
        palavra = [letra(x, 100) for x in (0, 20, 40)]
        virgula = Caixa(60, 100 + ALTURA - 5, 65, 100 + ALTURA + 1)  # raspa a base
        seguinte = [letra(x, 100) for x in (70, 90)]
        self.assertEqual(1, len(quebrar_em_linhas([*palavra, virgula, *seguinte])))


class ColunaTests(unittest.TestCase):
    """F61: subir é o fim de uma coluna, e sem essa regra as duas colunas saem coladas."""

    def test_subir_para_o_topo_da_pagina_abre_linha_nova(self) -> None:
        """Da última linha da esquerda para a primeira da direita a sequência **sobe**.

        Ela não desce e não volta para a esquerda: as duas regras antigas deixavam passar, e o
        fim de `...followed by ♔f7.` saía preso ao cabeçalho `ROOK ENDINGS` da coluna vizinha.
        """
        fim_da_esquerda = [letra(x, 600) for x in (0, 20, 40)]
        topo_da_direita = [letra(x, 60) for x in (300, 320, 340)]
        self.assertEqual(
            [fim_da_esquerda, topo_da_direita],
            quebrar_em_linhas([*fim_da_esquerda, *topo_da_direita]),
        )

    def test_subir_e_contra_a_linha_inteira_e_nao_contra_a_anterior(self) -> None:
        """Contra a anterior, a régua corta **dentro** da linha.

        `Gurgenidze,` e `1981` viravam duas linhas: a vírgula mora na base, e a letra seguinte
        começa acima do topo dela.
        """
        nome = [letra(x, 100) for x in (0, 20, 40)]
        virgula = Caixa(60, 100 + ALTURA - 4, 65, 100 + ALTURA)
        ano = [letra(x, 100) for x in (75, 95)]
        self.assertEqual(1, len(quebrar_em_linhas([*nome, virgula, *ano])))

    def test_a_pilha_girada_nao_e_cortada_por_subir(self) -> None:
        """A 90° o texto se lê de baixo para cima: subir ali é o andamento normal da linha.

        Sem a guarda, cada letra de um rótulo vertical vira uma linha.
        """
        pilha = [Caixa(100, y, 118, y + ALTURA, 90) for y in (400, 360, 320, 280, 240)]
        self.assertEqual(1, len(quebrar_em_linhas(pilha)))


class ConstantesTests(unittest.TestCase):
    """Se alguém mexer nos números, o teste diz de onde eles vieram."""

    def test_a_folga_de_coluna_e_maior_que_a_de_linha(self) -> None:
        """**O motivo é físico, e não é ajuste fino.**

        Quem dispara o `subiu` sem ser troca de coluna é o apóstrofo depois de altura de x, e ele
        sobe o vão entre altura de x e ascendente — ~0,4 altura mediana em fonte comum, mais que
        os 0,25 que bastam para a vírgula.
        """
        self.assertGreater(FOLGA_DE_COLUNA, FOLGA_DE_LINHA)
        self.assertGreaterEqual(FOLGA_DE_COLUNA, 0.4, "abaixo do vão x-altura/ascendente")

    def test_a_caixa_curta_esta_abaixo_da_altura_de_letra(self) -> None:
        self.assertLess(CAIXA_CURTA, 1.0)
        self.assertGreater(CAIXA_CURTA, 0.4, "abaixo disto a vírgula passaria a fixar a base")


class OrdemTests(unittest.TestCase):
    def test_a_faixa_e_lida_de_cima_para_baixo_e_da_esquerda_para_a_direita(self) -> None:
        embaralhadas = [letra(60, 140), letra(20, 100), letra(60, 100), letra(20, 140)]
        ordenadas = ordem_em_faixa(embaralhadas)
        self.assertEqual([(20, 100), (60, 100), (20, 140), (60, 140)], [(c.x1, c.y1) for c in ordenadas])

    def test_ordem_de_faixa_vazia(self) -> None:
        self.assertEqual([], ordem_em_faixa([]))


class TextoTests(unittest.TestCase):
    def test_o_vao_largo_vira_espaco(self) -> None:
        linha = [letra(0), letra(16), letra(120)]
        self.assertEqual("ab c", texto_da_linha(linha, ["a", "b", "c"]))

    def test_linha_de_um_caractere(self) -> None:
        self.assertEqual("8", texto_da_linha([letra(0)], ["8"]))

    def test_sem_caractere_nao_levanta(self) -> None:
        self.assertEqual("", texto_da_linha([letra(0)], []))
        self.assertEqual("", texto_da_linha([], ["a"]))

    def test_envolve_cobre_a_linha_inteira(self) -> None:
        self.assertEqual((0.0, 100.0, 74.0, 120.0), envolve([letra(0), letra(30), letra(60)]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
