"""A janela de achar e substituir, que não tinha teste nenhum (S-418).

**É a única janela do programa que edita texto em bloco.** Uma troca dela reescreve dezenas de
lugares de uma vez, sobre um documento que alguém passou a tarde corrigindo -- e a suíte não
tocava nela: nem no `Enter` que **não** substitui (a regra 2 da revisão, S-342), nem no botão que
recusa trocar antes de listar, nem no `casar_figurina`, que é o que separa `♘` de `N`.

O que se afirma aqui é o contrato da janela, e não o algoritmo de busca -- esse tem
`tests/test_texto_busca.py`, e é dele que sai a `Ocorrencia` que estes testes conferem.
"""

from __future__ import annotations

import tkinter as tk
import unittest

from ambiente_de_teste import quadro
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.text import rico
from chess_diagram_ocr.ui.texto_busca import JanelaDeBusca


def _documento(*textos: str) -> rico.DocumentoRico:
    """Um documento com uma corrida de texto por argumento."""
    return rico.DocumentoRico(corridas=tuple(rico.Corrida(texto=texto, tipo=rico.TEXTO) for texto in textos))


class JanelaDeBuscaTests(unittest.TestCase):
    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.host = quadro(self, self.root)
        self.trocas: list[tuple[tuple[str, ...], str]] = []
        self.mostrados: list[tuple[int, int]] = []
        self.doc = _documento("O peao vai a e4. O peao volta. Outro peao.")
        self.janela = JanelaDeBusca(
            self.host,
            documento=lambda: self.doc,
            ao_substituir=self._substituir,
            ao_mostrar=lambda inicio, fim: self.mostrados.append((inicio, fim)),
        )
        self.addCleanup(self.janela.destroy)

    def _substituir(self, ocorrencias, novo: str) -> int:  # noqa: ANN001
        self.trocas.append((tuple(o.contexto for o in ocorrencias), novo))
        return len(ocorrencias)

    # ------------------------------------------------------------------------------ achar

    def test_listar_acha_e_marca_tudo(self) -> None:
        """Marcadas por padrão: desmarcar o que não deve ser trocado é o gesto, e não o inverso."""
        self.janela.agulha_var.set("peao")
        achadas = self.janela.listar()

        self.assertEqual(3, len(achadas))
        self.assertEqual(3, self.janela.lista.size())
        self.assertEqual(3, len(self.janela.marcadas()))
        self.assertIn("3 ocorrência(s)", self.janela.status_var.get())

    def test_a_primeira_ocorrencia_e_mostrada_no_editor(self) -> None:
        """Achar sem levar até lá seria uma lista sobre um texto que ninguém está vendo."""
        self.janela.agulha_var.set("peao")
        achadas = self.janela.listar()
        self.assertEqual([(achadas[0].inicio, achadas[0].fim)], self.mostrados)

    def test_agulha_vazia_pede_o_que_procurar_em_vez_de_achar_tudo(self) -> None:
        self.janela.agulha_var.set("   ")
        self.assertEqual((), self.janela.listar())
        self.assertIn("Digite o que procurar", self.janela.status_var.get())

    def test_enter_acha_e_nao_substitui(self) -> None:
        """**A regra 2 desta revisão** (S-342): trocar é o gesto destrutivo, e ele exige o botão.

        Uma tecla que dispare a troca pelo caminho de "achar" é exatamente o que ninguém pediu --
        e com a lista na tela `Enter` refaz a busca, que é o que se quer depois de mudar o texto.
        """
        self.janela.agulha_var.set("peao")
        self.janela.novo_var.set("peão")

        self.assertEqual("break", self.janela._ao_teclar_enter())

        self.assertEqual(3, self.janela.lista.size())
        self.assertEqual([], self.trocas, "`Enter` não pode trocar nada")

    # --------------------------------------------------------------------------- substituir

    def test_trocar_sem_lista_lista_e_pede_confirmacao(self) -> None:
        """Achar antes de trocar não é passo a mais: é a confirmação."""
        self.janela.agulha_var.set("peao")
        self.janela.novo_var.set("peão")

        self.assertEqual(0, self.janela.trocar_marcadas())

        self.assertEqual([], self.trocas)
        self.assertEqual(3, self.janela.lista.size())
        self.assertIn("clique de novo", self.janela.status_var.get())

    def test_o_segundo_clique_troca_as_marcadas(self) -> None:
        self.janela.agulha_var.set("peao")
        self.janela.novo_var.set("peão")
        self.janela.trocar_marcadas()

        feitas = self.janela.trocar_marcadas()

        self.assertEqual(3, feitas)
        self.assertEqual(1, len(self.trocas))
        self.assertEqual("peão", self.trocas[0][1])
        self.assertEqual(0, self.janela.lista.size(), "a lista trocada não pode ficar na tela")
        self.assertIn("3 troca(s)", self.janela.status_var.get())

    def test_nada_marcado_nao_troca_nada(self) -> None:
        """Desmarcar tudo é uma decisão, e a resposta a ela é não fazer nada -- dizendo isso."""
        self.janela.agulha_var.set("peao")
        self.janela.listar()
        self.janela.lista.selection_clear(0, tk.END)

        self.assertEqual(0, self.janela.trocar_marcadas())

        self.assertEqual([], self.trocas)
        self.assertIn("Nada marcado", self.janela.status_var.get())

    def test_so_o_que_ficou_marcado_e_trocado(self) -> None:
        """O crivo é a lista: é ali que se decide quais das dezenas de ocorrências mudam."""
        self.janela.agulha_var.set("peao")
        achadas = self.janela.listar()
        self.janela.lista.selection_clear(0, tk.END)
        self.janela.lista.selection_set(1)

        self.assertEqual(1, self.janela.trocar_marcadas())
        self.assertEqual((achadas[1].contexto,), self.trocas[0][0])

    # ------------------------------------------------------------------------------ figurina

    def test_casar_figurina_e_uma_escolha_da_janela(self) -> None:
        """`♘f3` e `Nf3` são a mesma jogada e não o mesmo texto: quem decide é quem procura."""
        self.doc = _documento("1.♘f3 Nf6")
        self.janela.agulha_var.set("Nf")

        self.janela.figurina_var.set(False)
        sem = self.janela.listar()
        self.janela.figurina_var.set(True)
        com = self.janela.listar()

        self.assertEqual(1, len(sem))
        self.assertEqual(2, len(com))

    # --------------------------------------------------------------------------------- teclas

    def test_esc_fecha(self) -> None:
        """A mesma saída da paleta e dos diálogos (S-395)."""
        self.assertEqual("break", self.janela._ao_teclar_esc())
        self.assertFalse(self.janela.winfo_exists())

    def test_escolher_na_lista_leva_o_editor_ate_la(self) -> None:
        self.janela.agulha_var.set("peao")
        achadas = self.janela.listar()
        self.mostrados.clear()

        self.janela.lista.selection_clear(0, tk.END)
        self.janela.lista.selection_set(2)
        self.janela._mostrar_escolhida()

        self.assertEqual([(achadas[2].inicio, achadas[2].fim)], self.mostrados)
