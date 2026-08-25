"""O rótulo de aba diz quanto trabalho ela carrega (S-162).

As seis abas diziam só o nome. Quanto há para fazer em cada uma -- 129 pendentes na Revisão, 3.936
linhas no Dataset, 1.480 diagramas na Galeria -- só aparecia **depois** de clicar, e é justamente
essa a informação que decide qual aba abrir.

O que estes testes travam são os casos de borda, que é onde a decisão está: o zero que não vira
"(0)", o milhar em pt-BR, e o rótulo que o `AppState` guarda -- que passou a ter número dentro e
por isso deixou de poder ser comparado inteiro.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui import abas, rolagem

RAIZ = Path(__file__).resolve().parents[1]


class RotuloTests(unittest.TestCase):
    def test_sem_contagem_o_rotulo_e_o_nome(self) -> None:
        """`None` é "a aba nunca carregou", e inventar um número ali seria mentir."""
        self.assertEqual(abas.rotulo("Revisão"), "Revisão")
        self.assertEqual(abas.rotulo("Revisão", None), "Revisão")

    def test_zero_nao_vira_parenteses(self) -> None:
        """Fila vazia é um estado bom. Anunciá-lo com "(0)" é ruído permanente na barra de abas."""
        self.assertEqual(abas.rotulo("Revisão", 0), "Revisão")

    def test_a_contagem_aparece_entre_parenteses(self) -> None:
        self.assertEqual(abas.rotulo("Revisão", 129), "Revisão (129)")

    def test_o_milhar_e_ponto_como_no_resto_da_interface(self) -> None:
        """3936 e 39360 têm larguras parecidas e ordens diferentes; o ponto é o que se lê antes."""
        self.assertEqual(abas.rotulo("Dataset", 3936), "Dataset (3.936)")

    def test_o_nome_base_tira_a_contagem(self) -> None:
        self.assertEqual(abas.nome_base("Revisão (129)"), "Revisão")
        self.assertEqual(abas.nome_base("Revisão"), "Revisão")

    def test_o_nome_base_nao_come_parenteses_que_fazem_parte_do_nome(self) -> None:
        """A regra é "termina em número entre parênteses", e não "tem parêntese"."""
        self.assertEqual(abas.contagem_no_rotulo("Configuração (avançada)"), None)

    def test_o_rotulo_e_o_nome_base_sao_inversos(self) -> None:
        for contagem in (None, 0, 1, 129, 3936):
            with self.subTest(contagem=contagem):
                self.assertEqual(abas.nome_base(abas.rotulo("Dataset", contagem)), "Dataset")
                self.assertEqual(abas.contagem_no_rotulo(abas.rotulo("Dataset", contagem)), contagem or None)


class OrdemEAberturaTests(unittest.TestCase):
    """Os dois níveis de navegação, e onde a janela abre (S-162).

    Seis abas de peso igual escondiam que três delas mudam de conteúdo quando se clica num
    retângulo da página e três não. A ordem passou a ser o corte: primeiro o diagrama aberto agora,
    depois o acervo -- e a Configuração no fim, porque é a aba do primeiro dia e quase nunca depois.
    """

    def _ordem_no_codigo(self) -> list[str]:
        """A ordem em que a janela monta as abas, lida do código.

        **Procura a constante e não o literal** (S-226): os nomes passaram a ser declarados em
        `ui/abas.py`, e o teste que caçava `"Resultado"` no `app_tkinter` deixaria de achar
        qualquer coisa -- em silêncio, dando por bom um painel com as abas em qualquer ordem.
        """
        constantes = {getattr(abas, nome): nome for nome in dir(abas) if getattr(abas, nome, None) in abas.ABAS}
        fonte = (RAIZ / "app_tkinter.py").read_text(encoding="utf-8")
        trecho = fonte.split("def _build_left_panel", 1)[1].split("def _build_config_tab", 1)[0]
        achados = []
        for linha in trecho.splitlines():
            if "aba_rolavel" not in linha and "tabs.add" not in linha:
                continue
            for valor, constante in constantes.items():
                if f"abas.{constante}" in linha:
                    achados.append(valor)
        return achados

    def test_a_janela_monta_as_abas_declaradas_na_ordem_declarada(self) -> None:
        """Uma aba nova que entre no `app_tkinter` sem entrar em `abas.ABAS` falha aqui -- e é
        o que impede a lista de virar índice que ninguém verifica (S-134)."""
        self.assertEqual(list(abas.ABAS), self._ordem_no_codigo())

    def test_as_do_diagrama_vem_antes_das_do_acervo(self) -> None:
        ordem = self._ordem_no_codigo()
        corte = len(abas.DO_DIAGRAMA)
        self.assertEqual(ordem[:corte], list(abas.DO_DIAGRAMA))
        self.assertEqual(ordem[corte:], list(abas.DO_ACERVO))

    def test_a_janela_abre_na_aba_de_trabalho_num_checkout_novo(self) -> None:
        """O critério de aceite: a primeira abertura cai onde o trabalho começa."""
        self.assertEqual(abas.ABA_DE_TRABALHO, "Resultado")
        self.assertEqual(self._ordem_no_codigo()[0], abas.ABA_DE_TRABALHO)

    def test_o_teclado_circula_as_abas(self) -> None:
        """`enable_traversal()` nunca tinha sido chamado: a barra só andava com o mouse."""
        fonte = (RAIZ / "app_tkinter.py").read_text(encoding="utf-8")
        self.assertIn("enable_traversal()", fonte)


class AbaLembradaTests(unittest.TestCase):
    """A interação que a contagem criou com a S-156, e que falharia em silêncio.

    O `AppState` guarda a aba aberta **pelo rótulo**. Com a contagem dentro dele, "Revisão (129)"
    guardado numa sessão não casaria com "Revisão (54)" na seguinte: a janela abriria na primeira
    aba, sem erro nenhum, e a explicação estaria a dois módulos de distância.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.addCleanup(self.janela.destroy)
        self.notebook = ttk.Notebook(self.janela)
        self.notebook.pack()
        for texto in ("Resultado", "Revisão (54)", "Dataset (3.936)"):
            self.notebook.add(ttk.Frame(self.notebook), text=texto)

    def test_a_aba_guardada_sem_contagem_encontra_a_de_hoje(self) -> None:
        self.assertTrue(rolagem.selecionar_aba(self.notebook, "Revisão"))
        self.assertEqual(abas.nome_base(str(self.notebook.tab(self.notebook.select(), "text"))), "Revisão")

    def test_a_aba_guardada_com_outra_contagem_ainda_encontra(self) -> None:
        """O caso real: a fila encolheu de 129 para 54 entre duas sessões."""
        self.assertTrue(rolagem.selecionar_aba(self.notebook, "Revisão (129)"))
        self.assertEqual(abas.nome_base(str(self.notebook.tab(self.notebook.select(), "text"))), "Revisão")

    def test_uma_aba_que_nao_existe_mais_nao_muda_nada(self) -> None:
        self.notebook.select(0)
        self.assertFalse(rolagem.selecionar_aba(self.notebook, "Leitura"))
        self.assertEqual(self.notebook.index(self.notebook.select()), 0)


if __name__ == "__main__":
    unittest.main()
