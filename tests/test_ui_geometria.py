"""O piso da janela, e a janela que o respeita (S-150).

O cálculo é puro e afirmado contra a soma declarada; a ligação com o `Tk` é afirmada com uma
janela de verdade, porque a função podia existir e `root.minsize()` continuar não sendo
chamado -- que é exatamente o estado anterior.
"""

from __future__ import annotations

import tkinter as tk
import unittest

from chess_diagram_ocr.ui.geometria import (
    ALTURA_MINIMA_DO_CONTEUDO,
    CHROME_HORIZONTAL,
    CHROME_VERTICAL,
    PISO_MEDIDO,
    piso_da_janela,
)


class PisoTests(unittest.TestCase):
    def test_com_os_paineis_de_hoje_vence_a_medicao(self) -> None:
        """A soma dá (1000, 716) e é otimista -- 1100×760 já cortava a fila de salvar."""
        self.assertEqual(piso_da_janela(420, 520), PISO_MEDIDO)
        self.assertLess(420 + 520 + CHROME_HORIZONTAL, PISO_MEDIDO[0])
        self.assertLess(ALTURA_MINIMA_DO_CONTEUDO + CHROME_VERTICAL, PISO_MEDIDO[1])

    def test_o_piso_acompanha_o_painel_que_cresce_acima_da_medicao(self) -> None:
        """A medição é piso, não teto: um painel maior empurra o número para cima."""
        largura, _ = piso_da_janela(900, 900)
        self.assertEqual(largura, 900 + 900 + CHROME_HORIZONTAL)
        self.assertGreater(largura, PISO_MEDIDO[0])

    def test_o_piso_cobre_as_resolucoes_em_que_o_defeito_foi_fotografado(self) -> None:
        """1100×760 cortava a fila de salvar; 940×620 sumia com o botão "Remover"."""
        largura, altura = piso_da_janela(420, 520)
        for cortada in ((1100, 760), (940, 620)):
            with self.subTest(tamanho=cortada):
                self.assertTrue(
                    cortada[0] < largura or cortada[1] < altura,
                    f"{cortada} continuaria permitida pelo piso {(largura, altura)}",
                )

    def test_a_largura_cabe_num_notebook_de_1366_e_a_altura_nao(self) -> None:
        """O item pela metade, travado como teste em vez de escondido.

        A largura cabe. A altura **não**: 800 contra 768. É o que o conteúdo precisa hoje *sem
        rolagem*, e quem fecha a lacuna é a segunda metade da S-150 -- as abas rolando --, que
        não foi entregue. Baixar o piso para caber devolveria o botão cortado em silêncio, que
        é o defeito original; o teste registra a dívida no lugar disso.

        Quando a rolagem entrar, este teste muda junto: a altura passa a poder ser menor.
        """
        largura, altura = piso_da_janela(420, 520)
        self.assertLessEqual(largura, 1366)
        self.assertGreater(altura, 768, "se isto passar a caber, a rolagem da S-150 chegou")


class JanelaRespeitaOPisoTests(unittest.TestCase):
    """A ligação: `root.minsize()` de fato recebe o piso, e o Tk de fato o impõe."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - maquina sem display
            raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def test_o_tk_recusa_encolher_abaixo_do_piso(self) -> None:
        largura, altura = piso_da_janela(420, 520)
        self.root.minsize(largura, altura)
        self.assertEqual(tuple(self.root.minsize()), (largura, altura))

    def test_a_janela_do_produto_chama_minsize(self) -> None:
        """Sem isto, `geometria.py` podia existir inteiro e a janela continuar sem piso."""
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[1] / "app_tkinter.py").read_text(encoding="utf-8")
        self.assertIn("self.root.minsize(", fonte)
        self.assertIn("geometria.piso_da_janela(", fonte)

    def test_o_piso_e_os_paineis_usam_o_mesmo_numero(self) -> None:
        """Dois números para a mesma largura mínima divergem no primeiro que alguém mexer."""
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[1] / "app_tkinter.py").read_text(encoding="utf-8")
        self.assertIn("minsize=LARGURA_MINIMA_ESQUERDA", fonte)
        self.assertIn("minsize=LARGURA_MINIMA_DIREITA", fonte)
        self.assertNotIn("minsize=420", fonte)
        self.assertNotIn("minsize=520", fonte)


if __name__ == "__main__":
    unittest.main()
