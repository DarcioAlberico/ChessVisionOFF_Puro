"""A faixa de abas discreta, e o rodapé que não pode sumir (S-226).

A Imagem 1 não tem faixa de abas nem rodapé, e **este é o item em que seguir a imagem à risca faz
o dano mais concreto**. As sete abas são sete painéis; o rodapé, depois da S-163, é onde mora o
**cancelamento** da varredura, da exportação e do treino. Uma pele sem rodapé é uma pele em que
uma varredura de dez horas não pode ser interrompida.

O que entra da imagem é o **peso** da faixa, e não o conteúdo dela. É a regra 2 da SPEC_APARENCIA
no lugar em que ela mais precisa valer.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui import abas, pele, rodape, theme, tokens
from chess_diagram_ocr.ui.busy import BusyOperation


class DeclaracaoDasAbasTests(unittest.TestCase):
    """As sete, declaradas uma vez. Roda sem abrir janela."""

    def test_sao_sete_e_nao_seis(self) -> None:
        """A spec da S-226 dizia seis: era o número da S-162, e a S-211 acrescentou a `Texto`.
        Um número que ninguém reproduziu é o mecanismo da S-135."""
        self.assertEqual(7, len(abas.ABAS))
        self.assertIn(abas.TEXTO, abas.DO_DIAGRAMA)

    def test_o_corte_entre_os_dois_niveis_e_declarado(self) -> None:
        self.assertEqual(abas.DO_DIAGRAMA + abas.DO_ACERVO, abas.ABAS)
        self.assertEqual((), tuple(set(abas.DO_DIAGRAMA) & set(abas.DO_ACERVO)))
        self.assertEqual(abas.CONFIGURACAO, abas.ABAS[-1], "a aba do primeiro dia fecha a fila")

    def test_nenhum_nome_se_repete(self) -> None:
        self.assertEqual(len(set(abas.ABAS)), len(abas.ABAS))

    def test_a_contagem_no_rotulo_e_de_abas_e_de_mais_ninguem(self) -> None:
        """"Nenhuma pele a formata por conta" -- o critério, dito como o teste consegue cobrar:
        o milhar em pt-BR e o zero que **não** vira "(0)" saem de uma função só."""
        self.assertEqual("Revisão (1.480)", abas.rotulo(abas.REVISAO, 1480))
        self.assertEqual("Revisão", abas.rotulo(abas.REVISAO, 0))
        self.assertEqual("Revisão", abas.rotulo(abas.REVISAO, None))


class FaixaLegivelTests(unittest.TestCase):
    """A faixa da pele "Foco" sobre o cromo escuro: ativa e inativa."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.addCleanup(theme.apply_theme, self.root)

    def test_a_faixa_de_abas_e_legivel_no_cromo_escuro(self) -> None:
        """O critério, medido no que o `Style` de fato guardou -- e não nos papéis que se
        pretendia usar."""
        theme.apply_theme(self.root, cromo_escuro=True)
        fundo = theme.cor_atual(tokens.SUPERFICIE_PADRAO)
        mapa = dict(ttk.Style().map(f"{theme.ESTILO_DE_ABAS_DISCRETO}.Tab", "foreground"))

        self.assertEqual({"selected", "!selected"}, set(mapa), "a faixa perdeu um dos dois estados")
        for estado, cor in mapa.items():
            with self.subTest(estado=estado):
                razao = tokens.razao_de_contraste(str(cor), fundo)
                self.assertGreaterEqual(razao, tokens.AA_TEXTO, f"aba {estado}: {razao:.2f}:1")

    def test_a_aba_ativa_se_separa_por_dois_canais(self) -> None:
        """Cor **e** peso de fonte. Sublinhar exigiria um `layout` de elemento próprio, escrito
        por tema e quebrado em cada um dos trinta."""
        theme.apply_theme(self.root, cromo_escuro=True)
        estilo = ttk.Style()
        mapa = dict(estilo.map(f"{theme.ESTILO_DE_ABAS_DISCRETO}.Tab", "foreground"))
        self.assertNotEqual(mapa["selected"], mapa["!selected"])
        self.assertTrue(estilo.map(f"{theme.ESTILO_DE_ABAS_DISCRETO}.Tab", "font"))


class RodapeInteiroTests(unittest.TestCase):
    """O rodapé fica, em toda pele, com o cancelamento alcançável."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.janela.geometry("700x400+40+40")
        self.addCleanup(self.janela.destroy)
        self.cancelamentos: list[int] = []
        self.rodape = rodape.RodapeDaJanela(self.janela, cancelar=lambda: self.cancelamentos.append(1))
        self.rodape.pack(side=tk.BOTTOM, fill=tk.X)
        self.root.update_idletasks()

    def test_o_rodape_existe_em_toda_pele(self) -> None:
        """A troca de pele remonta o cromo do painel, a fila e o menu -- e **não alcança** o
        rodapé, que é filho da janela. Aqui isso é medido, e não deduzido."""
        for registro in pele.PELES:
            theme.apply_theme(self.root, cromo_escuro=registro.cromo_escuro)
            self.root.update_idletasks()
            with self.subTest(pele=registro.nome):
                self.assertTrue(self.rodape.winfo_exists())
                # `winfo_manager` e não `winfo_ismapped`: o que se afirma é que ele continua
                # empacotado. Numa suíte sem janela levantada nada está "mapeado", e um teste
                # que dependesse disso passaria a verde por não medir nada.
                self.assertEqual("pack", self.rodape.winfo_manager(), "o rodapé saiu do layout")
        theme.apply_theme(self.root)

    def test_o_cancelamento_esta_alcancavel_em_toda_pele(self) -> None:
        """Uma varredura de dez horas tem de poder parar em qualquer aparência."""
        for registro in pele.PELES:
            theme.apply_theme(self.root, cromo_escuro=registro.cromo_escuro)
            self.rodape.aplicar_ocupacao(
                [BusyOperation(name="Varrendo o livro", loses_work=True, cancellable=True, feito=1, total=10)]
            )
            self.root.update_idletasks()
            botao = self.rodape._btn_cancelar
            with self.subTest(pele=registro.nome):
                self.assertEqual("pack", botao.winfo_manager(), "o botão de cancelar saiu do rodapé")
                self.assertEqual("normal", str(botao.cget("state")))
        theme.apply_theme(self.root)

        self.rodape._btn_cancelar.invoke()
        self.assertEqual([1], self.cancelamentos)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
