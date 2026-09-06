"""As abas declaradas: o rótulo que carrega contagem, a ordem, e o que a lista ainda descreve (S-162).

**A parte pura do teste que morreu no corte.** `tests/test_ui_abas.py` existia até a S-506 e lia o
`app_tkinter.py` para comparar a barra montada com `abas.ABAS`; saiu junto com o arquivo que lia,
e `ui/abas.py` ficou um mês sem teste nenhum -- tempo em que a tupla seguiu declarando a aba
Configuração, que a janela do Qt não tem. É o achado da triagem da S-511, e é o mesmo formato do
`NAS_BARRAS_DO_PDF`: uma declaração sem leitor não só perde o chamador, ela **deriva**.

O que se afirma aqui não precisa de janela: o zero que não vira "(0)", o milhar em pt-BR, o rótulo
que o `AppState` guarda -- que passou a ter número dentro e por isso deixou de poder ser comparado
inteiro --, a ordem em dois níveis, e o rename que `nome_atual` lembra. O lado da janela -- *a
barra montada é a tupla* -- é de `test_qt_janela`.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui import abas


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
        self.assertEqual(abas.nome_base("Configuração (avançada)"), "Configuração")

    def test_o_rotulo_e_o_nome_base_sao_inversos(self) -> None:
        for contagem in (None, 0, 1, 129, 3936):
            with self.subTest(contagem=contagem):
                self.assertEqual(abas.nome_base(abas.rotulo("Dataset", contagem)), "Dataset")
                self.assertEqual(abas.contagem_no_rotulo(abas.rotulo("Dataset", contagem)), contagem or None)


class OrdemTests(unittest.TestCase):
    """Os dois níveis de navegação, e onde a janela abre (S-162).

    Seis abas de peso igual escondiam que quatro delas mudam de conteúdo quando se clica num
    retângulo da página e duas não. A ordem é o corte: primeiro o diagrama aberto agora, depois o
    acervo.
    """

    def test_as_do_diagrama_vem_antes_das_do_acervo(self) -> None:
        self.assertEqual(abas.ABAS, abas.DO_DIAGRAMA + abas.DO_ACERVO)
        self.assertEqual(len(set(abas.ABAS)), len(abas.ABAS), "aba declarada duas vezes")

    def test_a_janela_abre_na_aba_de_trabalho(self) -> None:
        """O critério de aceite: a primeira abertura cai onde o trabalho começa."""
        self.assertEqual(abas.ABA_DE_TRABALHO, abas.RESULTADO)
        self.assertEqual(abas.ABAS[0], abas.ABA_DE_TRABALHO)

    def test_a_configuracao_nao_e_mais_declarada(self) -> None:
        """A aba saiu no porte para o Qt (S-506): o conjunto de peças foi para o menu e o treino e
        as bases para diálogos. A tupla a declarou por mais um mês, sem que nada acusasse."""
        self.assertNotIn("Configuração", abas.ABAS)
        self.assertEqual(len(abas.ABAS), 6)


class AbaLembradaTests(unittest.TestCase):
    """O `AppState` guarda a aba aberta pelo rótulo (S-156), e o rótulo mudou duas vezes desde então:
    ganhou contagem (S-162) e uma aba mudou de nome (S-272). `nome_atual` é o que absorve as duas."""

    def test_a_contagem_guardada_nao_atrapalha(self) -> None:
        self.assertEqual(abas.nome_atual("Revisão (129)"), abas.REVISAO)

    def test_o_nome_antigo_da_aba_de_estudo_encontra_o_de_hoje(self) -> None:
        """`Análise` virou `Estudo` na S-272, e uma sessão guardada antes disso ainda diz o nome velho."""
        self.assertEqual(abas.nome_atual("Análise"), abas.ESTUDO)
        self.assertEqual(abas.nome_atual("Análise (3)"), abas.ESTUDO)

    def test_um_nome_que_nunca_existiu_passa_igual(self) -> None:
        """A resposta para "não sei que aba é essa" é a de antes: a janela fica onde já estava."""
        self.assertEqual(abas.nome_atual("Leitura"), "Leitura")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
