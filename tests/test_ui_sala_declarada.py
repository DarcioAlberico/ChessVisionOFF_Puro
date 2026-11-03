"""A regra que dá o tamanho do tabuleiro da sala e move o divisor (S-551).

**O que se afirma sem janela.** Que o tabuleiro cresce pela **altura** quando ela é o recurso
abundante; que ele para antes de a coluna de leitura ficar mais estreita que o piso dela; que ele
nunca fica menor que o próprio piso; e -- a parte que não é aritmética -- que a régua só empurra a
alça para a direita, nunca para a esquerda. O widget que a executa está em
`tests/test_qt_painel_de_estudo.py`.

As outras decisões deste módulo (`COMANDOS_DA_ABA`, a sincronia com o OCR, a cor da seta) já são
afirmadas em `tests/test_qt_painel_de_estudo.py::DeclaracaoTests`, que é onde nasceram.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from chess_diagram_ocr.ui import estudo_lista, sala_declarada

MINIMO = 240
"""O piso do tabuleiro, que o widget declara (`qt/tabuleiro.LADO_MINIMO`) e a régua recebe."""


class LadoDoTabuleiroTests(unittest.TestCase):
    def test_com_altura_de_sobra_quem_manda_e_a_largura(self) -> None:
        """A aba Estudo é mais alta que larga em toda janela medida, então este é o caso comum: o
        teto é a largura menos o piso da leitura e a alça."""
        lado = sala_declarada.lado_do_tabuleiro(878, 900, minimo=MINIMO, alca=6)
        self.assertEqual(878 - sala_declarada.LARGURA_MINIMA_DA_LEITURA - 6, lado)

    def test_com_altura_curta_quem_manda_e_a_altura(self) -> None:
        """O tabuleiro é quadrado: numa caixa baixa e larga ele para na altura, e o que sobra de
        largura fica com a leitura."""
        self.assertEqual(400, sala_declarada.lado_do_tabuleiro(1200, 400, minimo=MINIMO, alca=6))

    def test_nunca_abaixo_do_piso_do_proprio_tabuleiro(self) -> None:
        """Numa janela apertada a conta daria negativo, e um lado negativo é um `BoardGeometry`
        que não desenha."""
        self.assertEqual(MINIMO, sala_declarada.lado_do_tabuleiro(300, 900, minimo=MINIMO, alca=6))
        self.assertEqual(MINIMO, sala_declarada.lado_do_tabuleiro(0, 0, minimo=MINIMO, alca=6))

    def test_a_leitura_tem_piso_e_ele_e_somado_das_partes(self) -> None:
        """**O piso é o que impede a resposta óbvia e errada.** Com altura sobrando sempre,
        "cresça até a altura" sozinho daria o tabuleiro inteiro e uma coluna de lances de 46 px --
        que foi o que a primeira conta deste item produziu a 1400x950."""
        largura, altura = 697, 900
        lado = sala_declarada.lado_do_tabuleiro(largura, altura, minimo=MINIMO, alca=6)
        self.assertEqual(sala_declarada.LARGURA_MINIMA_DA_LEITURA, largura - lado - 6)
        # Somado das partes, e a maior delas é o recuo de variante mais fundo.
        recuo = sala_declarada.RECUO_POR_NIVEL * estudo_lista.NIVEL_MAXIMO_DE_RECUO
        self.assertLess(recuo, sala_declarada.LARGURA_MINIMA_DA_LEITURA)
        self.assertGreater(sala_declarada.LARGURA_MINIMA_DA_LEITURA, 2 * recuo // 3)


class FracaoTests(unittest.TestCase):
    def test_a_alca_vai_para_onde_o_tabuleiro_precisa(self) -> None:
        fracao = sala_declarada.fracao_para_o_tabuleiro(878, 900, minimo=MINIMO, alca=6)
        lado = sala_declarada.lado_do_tabuleiro(878, 900, minimo=MINIMO, alca=6)
        self.assertAlmostEqual((lado + 6) / 878, fracao)

    def test_ela_so_empurra_para_a_direita(self) -> None:
        """**A parte que não é aritmética.** A 1400x950 o teto de largura dá 481 px contra os 494
        que os pesos do `QSplitter` já davam: sem o piso, o item que pediu um tabuleiro maior o
        teria deixado 13 px menor."""
        atual = 494 / 697
        fracao = sala_declarada.fracao_para_o_tabuleiro(697, 671, minimo=MINIMO, alca=6, fracao_atual=atual)
        self.assertEqual(atual, fracao)

    def test_com_janela_grande_ela_de_fato_move(self) -> None:
        """A 1920x1080 a coluna tem 878 px e o tabuleiro tinha 616: a régua o leva a 662."""
        atual = 622 / 878
        fracao = sala_declarada.fracao_para_o_tabuleiro(878, 755, minimo=MINIMO, alca=6, fracao_atual=atual)
        self.assertGreater(fracao, atual)
        self.assertEqual(662, int(878 * fracao) - 6)

    def test_nunca_passa_de_um_inteiro_nem_fica_negativa(self) -> None:
        self.assertLessEqual(sala_declarada.fracao_para_o_tabuleiro(300, 9000, minimo=MINIMO, alca=6), 1.0)
        self.assertGreaterEqual(sala_declarada.fracao_para_o_tabuleiro(0, 0, minimo=MINIMO, alca=6), 0.0)

    def test_sem_largura_a_fracao_de_agora_e_devolvida(self) -> None:
        """Antes do primeiro `show` o `QSplitter` ainda não tem largura, e dividir por zero ali
        poria a alça num lugar que a janela nunca pediu."""
        self.assertEqual(0.42, sala_declarada.fracao_para_o_tabuleiro(0, 800, minimo=MINIMO, fracao_atual=0.42))


class EsteiraDaColunaTests(unittest.TestCase):
    """A barra de avaliação mora na coluna esquerda, e a régua tem de saber (S-551, 3ª rodada).

    **O número que este bloco existe para não deixar voltar**: medido na janela de verdade a
    1024x768 com o motor ligado, o widget do tabuleiro tinha 240 px e **203** apareciam -- 36 px
    fora da coluna, sem a coluna `h` e sem as duas réguas de coordenadas.
    """

    ESTEIRA = 42
    """Os 42 px medidos na base de referência: 6 de margem da coluna, 26 da barra e 10 de vão."""

    def test_a_esteira_sai_do_lado_do_tabuleiro(self) -> None:
        """Sem descontá-la, a régua entrega ao tabuleiro largura que a barra já ocupa."""
        sem = sala_declarada.lado_do_tabuleiro(1384, 735, minimo=MINIMO, alca=4)
        com = sala_declarada.lado_do_tabuleiro(1384, 735, minimo=MINIMO, alca=4, esteira=self.ESTEIRA)
        self.assertEqual(sem, com, "limitado pela altura, a esteira não muda o lado")
        estreita = 700
        self.assertEqual(
            sala_declarada.lado_do_tabuleiro(estreita, 900, minimo=MINIMO, alca=4, esteira=self.ESTEIRA),
            sala_declarada.lado_do_tabuleiro(estreita, 900, minimo=MINIMO, alca=4) - self.ESTEIRA,
            "limitado pela largura, ela sai inteira do tabuleiro",
        )

    def test_a_alca_vai_para_o_tabuleiro_mais_a_esteira(self) -> None:
        """A alça que ignorasse a barra ficaria 42 px cedo demais, e o tabuleiro sairia cortado."""
        largura, alca = 1384, 4
        fracao = sala_declarada.fracao_para_o_tabuleiro(
            largura, 735, minimo=MINIMO, alca=alca, esteira=self.ESTEIRA
        )
        lado = sala_declarada.lado_do_tabuleiro(
            largura, 735, minimo=MINIMO, alca=alca, esteira=self.ESTEIRA
        )
        self.assertEqual(int(largura * fracao), lado + self.ESTEIRA + alca)

    def test_no_aperto_a_leitura_cede_e_o_tabuleiro_fica_inteiro(self) -> None:
        """**É o caso de 1024**: os dois pisos somam 492 px numa aba de 480, e o `QSplitter` que
        não consegue atender nenhum dos dois reparte meio a meio e corta o tabuleiro.

        A ordem não é de gosto: a coluna de leitura reflui e rola, e o tabuleiro não.
        """
        largura, alca = 480, 4
        piso = sala_declarada.piso_da_leitura(largura, minimo=MINIMO, alca=alca, esteira=self.ESTEIRA)
        self.assertEqual(194, piso)
        self.assertLess(piso, sala_declarada.LARGURA_MINIMA_DA_LEITURA)
        fracao = sala_declarada.fracao_para_o_tabuleiro(
            largura, 466, minimo=MINIMO, alca=alca, esteira=self.ESTEIRA
        )
        esquerda = int(largura * fracao)
        self.assertGreaterEqual(esquerda - self.ESTEIRA, MINIMO, "o tabuleiro sairia cortado")
        self.assertGreaterEqual(largura - esquerda, piso, "a alça passou do piso da leitura")

    def test_com_largura_de_sobra_o_piso_da_leitura_e_o_declarado(self) -> None:
        """Ele só cede onde não cabe: numa janela larga, os 210 px valem como sempre valeram."""
        self.assertEqual(
            sala_declarada.LARGURA_MINIMA_DA_LEITURA,
            sala_declarada.piso_da_leitura(1384, minimo=MINIMO, alca=4, esteira=self.ESTEIRA),
        )

    def test_a_regua_desce_exigencia_e_nunca_sobe_a_de_quem_pede_pouco(self) -> None:
        """**A regressão da quarta rodada, e ela custou 53 px de tabuleiro.**

        O painel aplica esta resposta em `setMinimumWidth`, que é piso nos dois sentidos: sem o
        `pedido`, a régua *subia* a exigência da coluna que pedia menos do que ela. Medido na
        janela de verdade a 1024, sem motor: a coluna pede 136 px, a régua respondia 192, e o
        tabuleiro caía de 298 para **245** px -- uma troca que ninguém pediu, no item cujo assunto
        é justamente o tabuleiro não encolher.
        """
        largura, alca = 480, 4
        sem_pedido = sala_declarada.piso_da_leitura(largura, minimo=MINIMO, alca=alca, esteira=self.ESTEIRA)
        self.assertEqual(194, sem_pedido, "o caso de 1024 mudou de número")
        self.assertEqual(
            136,
            sala_declarada.piso_da_leitura(
                largura, minimo=MINIMO, alca=alca, esteira=self.ESTEIRA, pedido=136
            ),
            "a régua subiu o mínimo de quem pedia pouco",
        )
        self.assertEqual(
            sem_pedido,
            sala_declarada.piso_da_leitura(
                largura, minimo=MINIMO, alca=alca, esteira=self.ESTEIRA, pedido=386
            ),
            "quem pede demais continua descendo ao que cabe",
        )

    def test_o_pedido_e_teto_e_nao_troca_de_lugar_com_o_declarado(self) -> None:
        """Numa janela larga os dois tetos valem, e quem manda é o menor: a coluna que pede 300 px
        continua parando nos 210 declarados, e a que pede 90 para nos 90 dela."""
        for pedido, esperado in ((90, 90), (300, sala_declarada.LARGURA_MINIMA_DA_LEITURA)):
            with self.subTest(pedido=pedido):
                self.assertEqual(
                    esperado,
                    sala_declarada.piso_da_leitura(
                        1384, minimo=MINIMO, alca=4, esteira=self.ESTEIRA, pedido=pedido
                    ),
                )

    def test_o_piso_da_leitura_nunca_e_zero_nem_negativo(self) -> None:
        """Uma coluna de zero pixel é um `QSplitter` de que não há gesto de mouse que volte."""
        for largura in (0, 100, 240, 300):
            with self.subTest(largura=largura):
                self.assertGreaterEqual(
                    sala_declarada.piso_da_leitura(largura, minimo=MINIMO, alca=4, esteira=self.ESTEIRA), 1
                )


class PurezaTests(unittest.TestCase):
    def test_o_modulo_nao_importa_toolkit(self) -> None:
        arvore = ast.parse(Path(sala_declarada.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertEqual(set(), nomes & {"PyQt6", "tkinter"})


class ColunaQueEncolheTests(unittest.TestCase):
    """A leitura recupera o piso quando a coluna encolhe (S-552, quinta rodada).

    **O achado do crítico, com os números dele.** "Só empurra para a direita" é uma promessa sobre
    pixel de tabuleiro, e ela estava guardada em **fração** -- que é a mesma coisa só enquanto a
    largura não muda. Encolhida a janela, o `QSplitter` reparte em proporção antes de a régua
    rodar, a fração de uma coluna larga chega intacta a uma estreita, e ali ela compra mais
    tabuleiro do que a estreita tem para vender: medido na janela de verdade, 1400 -> 1600 -> 1400
    deixava a coluna de leitura em **183 px** (190 a 1920, vindo de 2120) e ela estacionava.

    Um degrau, não um acúmulo, e igual em `96ec6bb`: nunca foi regressão de rodada nenhuma, era o
    preço não declarado da promessa guardada na moeda errada.
    """

    MINIMO = 240
    LARGA = 800
    ESTREITA = 697
    """Os dois lados do ciclo, em largura de **coluna** e não de janela: 697 px é o que a aba
    Estudo tem numa janela de 1400, e 800 é o que ela tem numa de 1600."""

    def fracao(self, largura: int, atual: float, anterior: int = 0) -> float:
        return sala_declarada.fracao_para_o_tabuleiro(
            largura, 671, minimo=self.MINIMO, alca=6, fracao_atual=atual, largura_anterior=anterior
        )

    def test_o_ciclo_de_crescer_e_encolher_devolve_o_piso_a_leitura(self) -> None:
        """**A guarda do achado**, na moeda em que ele foi medido: pixel de coluna de leitura."""
        larga = self.fracao(self.LARGA, 494 / self.ESTREITA, anterior=self.ESTREITA)
        leitura_larga = self.LARGA - int(self.LARGA * larga)
        self.assertGreaterEqual(leitura_larga, sala_declarada.LARGURA_MINIMA_DA_LEITURA)

        volta = self.fracao(self.ESTREITA, larga, anterior=self.LARGA)
        leitura = self.ESTREITA - int(self.ESTREITA * volta)
        self.assertGreaterEqual(
            leitura,
            sala_declarada.LARGURA_MINIMA_DA_LEITURA,
            "a fração da coluna larga comprou tabuleiro que a estreita não tem",
        )

    def test_encolhendo_o_teto_e_o_piso_da_leitura_e_nada_mais(self) -> None:
        """O grampo é **só** o piso da leitura naquela largura: ele não move a alça para trás de
        onde a régua a poria, e no aperto ele cede junto com `piso_da_leitura`."""
        for largura in (400, 500, 697, 900, 1200):
            with self.subTest(largura=largura):
                piso = sala_declarada.piso_da_leitura(largura, minimo=self.MINIMO, alca=6)
                fracao = self.fracao(largura, 0.99, anterior=largura + 200)
                self.assertLessEqual(int(largura * fracao), largura - piso)

    def test_crescendo_a_regua_continua_so_empurrando_para_a_direita(self) -> None:
        """**Nenhum número da S-551 se mexe.** A 1400x950 recém-aberta a leitura continua com os
        203 px que os pesos do `QSplitter` já davam: ali a coluna não está encolhendo, e não há
        promessa de encolher o tabuleiro numa janela que não encolheu."""
        atual = 494 / self.ESTREITA
        for anterior in (0, self.ESTREITA, 500):
            with self.subTest(largura_anterior=anterior):
                self.assertEqual(atual, self.fracao(self.ESTREITA, atual, anterior=anterior))

    def test_sem_largura_anterior_nada_e_encolhimento(self) -> None:
        """`0` é "não sei qual era a largura de antes" -- o primeiro desenho --, e o padrão do
        argumento é ele: quem não passa nada tem a régua de sempre."""
        atual = 494 / self.ESTREITA
        self.assertEqual(
            sala_declarada.fracao_para_o_tabuleiro(
                self.ESTREITA, 671, minimo=self.MINIMO, alca=6, fracao_atual=atual
            ),
            self.fracao(self.ESTREITA, atual, anterior=0),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
