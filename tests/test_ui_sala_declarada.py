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


class PurezaTests(unittest.TestCase):
    def test_o_modulo_nao_importa_toolkit(self) -> None:
        arvore = ast.parse(Path(sala_declarada.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertEqual(set(), nomes & {"PyQt6", "tkinter"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
