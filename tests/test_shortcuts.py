"""Guarda de foco dos atalhos (S-20/S-31).

O `bind_all` liga as teclas na janela inteira, e é isso que faz `←` funcionar com o foco em
qualquer lugar. O preço é que, dentro do campo de FEN, `←` e `Del` pertencem ao campo -- e
sem a guarda, digitar uma FEN à mão trocaria de diagrama a cada seta.

Testável sem janela porque a regra é sobre a **classe** do widget, não sobre o evento.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import ttk

from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.ui.shortcuts import (
    CEDIDAS_A_TODO_CAMPO,
    CEDIDAS_SO_AO_MULTILINHA,
    cede_a_tecla,
    guard,
    ignores_widget,
    owns_key,
)


class _FakeEvent:
    def __init__(self, widget: object) -> None:
        self.widget = widget


class _FakeEntry(ttk.Entry):
    """Instanciar `ttk.Entry` exige um Tk; a checagem é de tipo, então basta a classe."""

    def __init__(self) -> None:  # noqa: D107 - sem chamar o __init__ do Tk de proposito
        pass


class IgnoreTests(unittest.TestCase):
    def test_text_entry_widgets_keep_their_own_keys(self) -> None:
        for classe in (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox):
            with self.subTest(widget=classe.__name__):
                self.assertTrue(ignores_widget(classe.__new__(classe)))

    def test_the_spinbox_is_included_because_it_already_uses_the_arrows(self) -> None:
        """Sem isto, uma seta no seletor "Selecionado" mudaria o diagrama duas vezes."""
        self.assertTrue(ignores_widget(ttk.Spinbox.__new__(ttk.Spinbox)))

    def test_other_widgets_do_not_swallow_the_shortcut(self) -> None:
        for classe in (tk.Canvas, tk.Frame, ttk.Button, ttk.Label):
            with self.subTest(widget=classe.__name__):
                self.assertFalse(ignores_widget(classe.__new__(classe)))

    def test_an_event_without_a_widget_does_not_crash(self) -> None:
        self.assertFalse(ignores_widget(None))


class GuardTests(unittest.TestCase):
    def test_the_handler_runs_and_the_key_is_consumed_outside_a_text_field(self) -> None:
        chamadas: list[int] = []
        resultado = guard(lambda: chamadas.append(1))(_FakeEvent(tk.Canvas.__new__(tk.Canvas)))

        self.assertEqual(chamadas, [1])
        # "break" impede o Tk de repassar a tecla adiante, que e o que evita a acao dupla.
        self.assertEqual(resultado, "break")

    def test_inside_a_text_field_the_handler_does_not_run_and_the_key_passes_through(self) -> None:
        chamadas: list[int] = []
        resultado = guard(lambda: chamadas.append(1))(_FakeEvent(_FakeEntry()))

        self.assertEqual(chamadas, [])
        # `None` (e nao "break") e o que faz o Entry continuar recebendo a seta.
        self.assertIsNone(resultado)


if __name__ == "__main__":
    unittest.main()


class WidgetQueJaDeclarouATeclaTests(unittest.TestCase):
    """A seta não executa dois painéis ao mesmo tempo (S-117).

    O tabuleiro de estudo liga `<Left>`/`<Right>` no próprio canvas e os handlers devolvem
    `None`; o `bind_all` daqui liga as mesmas teclas ao editor. Os dois disparavam: analisar
    uma posição com as setas na aba Análise movia, invisivelmente, o cursor do editor em outra
    aba -- e o `Ctrl+S` seguinte gravava outro diagrama.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        # A raiz é a do processo, e não uma deste módulo (S-416): duas raízes vivas fazem uma
        # `PhotoImage` nascer no interpretador errado, e o Tk recusa a imagem com a mensagem
        # que parece coleta de lixo. O porquê inteiro está em `tests/tk_root.py`.
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.disparos: list[str] = []
        self.quadro = tk.Frame(self.root)
        self.addCleanup(self.quadro.destroy)

    def _evento(self, widget: object) -> tk.Event:
        evento = tk.Event()
        evento.widget = widget  # type: ignore[assignment]
        return evento

    def test_o_canvas_que_declarou_a_seta_fica_com_ela(self) -> None:
        """A decisão, testada onde ela é tomada.

        Dirigir o Tk com `event_generate` aqui testaria o roteamento de evento do Tk -- que
        entrega por foco quando o alvo não é focável -- e não a guarda. O que a S-117 muda é a
        resposta de `guard` diante de um widget que já declarou a tecla, e é isso que se afirma.
        """
        canvas = tk.Canvas(self.quadro, width=40, height=40)
        canvas.bind("<Left>", lambda _e: None)
        protegido = guard(lambda: self.disparos.append("editor"), "<Left>")

        self.assertIsNone(protegido(self._evento(canvas)), "cedeu, então o Tk segue para o canvas")
        self.assertEqual(self.disparos, [], "o handler do editor não pode ter rodado")

    def test_fora_dele_o_atalho_do_editor_continua_valendo(self) -> None:
        outro = tk.Frame(self.quadro, width=40, height=40)
        protegido = guard(lambda: self.disparos.append("editor"), "<Left>")

        self.assertEqual(protegido(self._evento(outro)), "break")
        self.assertEqual(self.disparos, ["editor"])

    def test_sem_sequencia_a_segunda_pergunta_nao_e_feita(self) -> None:
        """`guard(handler)` sem tecla mantém o comportamento anterior à S-117 -- e há quem o use."""
        canvas = tk.Canvas(self.quadro, width=40, height=40)
        canvas.bind("<Left>", lambda _e: None)

        self.assertEqual(guard(lambda: self.disparos.append("editor"))(self._evento(canvas)), "break")
        self.assertEqual(self.disparos, ["editor"])

    def test_o_campo_de_texto_continua_vencendo(self) -> None:
        """A guarda antiga não pode ter sido substituída pela nova: as duas valem."""
        campo = ttk.Entry(self.quadro)
        protegido = guard(lambda: self.disparos.append("editor"), "<Left>")

        self.assertIsNone(protegido(self._evento(campo)))
        self.assertEqual(self.disparos, [])

    def test_owns_key_e_por_sequencia_e_nao_por_widget(self) -> None:
        """Ceder o widget inteiro tiraria `Ctrl+S` de quem está com o tabuleiro em foco."""
        canvas = tk.Canvas(self.quadro, width=40, height=40)
        canvas.bind("<Left>", lambda _e: None)

        self.assertTrue(owns_key(canvas, "<Left>"))
        self.assertFalse(owns_key(canvas, "<Control-s>"))

    def test_um_objeto_sem_bind_nao_derruba_a_guarda(self) -> None:
        self.assertFalse(owns_key(object(), "<Left>"))
        self.assertFalse(owns_key(None, "<Left>"))


class CedeATeclaTests(unittest.TestCase):
    """A guarda cede a tecla, e não o teclado (S-294).

    Até este item ela perguntava só "é campo de texto?" e cedia **os dezoito** atalhos da janela.
    A `SPEC_APARENCIA` da S-223 anotou o sintoma por escrito: digitar uma FEN e apertar `Ctrl+S`
    não salvava, e ninguém tinha decidido isso.
    """

    def campo(self) -> object:
        return ttk.Entry.__new__(ttk.Entry)

    def editor(self) -> object:
        return tk.Text.__new__(tk.Text)

    def test_o_campo_fica_com_as_teclas_que_ele_usa(self) -> None:
        for tecla in ("<Left>", "<Right>", "<Home>", "<End>", "<Delete>", "<Control-z>", "<Control-y>"):
            with self.subTest(tecla=tecla):
                self.assertTrue(cede_a_tecla(self.campo(), tecla))

    def test_o_campo_nao_engole_a_tecla_que_ele_nao_usa(self) -> None:
        """São nove, e as três que a SPEC_APARENCIA nomeia estão entre elas."""
        for tecla in ("<Control-s>", "<Control-S>", "<Control-n>", "<Control-P>", "<Control-0>", "<Control-Return>"):
            with self.subTest(tecla=tecla):
                self.assertFalse(cede_a_tecla(self.campo(), tecla))

    def test_o_ctrl_s_no_campo_de_fen_passa_a_salvar(self) -> None:
        """O sintoma que a SPEC_APARENCIA registrou, afirmado no caminho que a janela usa."""
        chamadas: list[int] = []
        resultado = guard(lambda: chamadas.append(1), "<Control-s>")(_FakeEvent(self.campo()))
        self.assertEqual([1], chamadas)
        self.assertEqual("break", resultado)

    def test_a_seta_no_campo_de_fen_continua_do_campo(self) -> None:
        """O que a guarda existe para proteger desde a S-20, e que não pode ter se perdido."""
        chamadas: list[int] = []
        resultado = guard(lambda: chamadas.append(1), "<Left>")(_FakeEvent(self.campo()))
        self.assertEqual([], chamadas)
        self.assertIsNone(resultado)

    def test_a_rolagem_e_so_de_quem_rola(self) -> None:
        """`PgUp` num campo de uma linha não faz nada: cedê-la ali era desligar a virada de página."""
        for tecla in ("<Prior>", "<Next>"):
            with self.subTest(tecla=tecla):
                self.assertTrue(cede_a_tecla(self.editor(), tecla))
                self.assertFalse(cede_a_tecla(self.campo(), tecla))

    def test_fora_de_campo_de_texto_nada_e_cedido(self) -> None:
        canvas = tk.Canvas.__new__(tk.Canvas)
        for tecla in ("<Left>", "<Control-s>", "<Prior>"):
            with self.subTest(tecla=tecla):
                self.assertFalse(cede_a_tecla(canvas, tecla))

    def test_sem_sequencia_cede_tudo_como_antes(self) -> None:
        """Quem chama `guard` sem dizer que tecla ligou não dá como responder: o lado seguro é o
        comportamento anterior."""
        self.assertTrue(cede_a_tecla(self.campo(), ""))

    def test_toda_tecla_cedida_e_um_atalho_da_janela_ou_uma_tecla_de_edicao(self) -> None:
        """Uma tecla cedida que não existe em lugar nenhum é linha morta na tabela."""
        from chess_diagram_ocr.ui import atalhos as tabela

        da_janela = {a.sequencia for a in tabela.ATALHOS}
        de_edicao = {"<Up>", "<Down>", "<BackSpace>"}
        for tecla in CEDIDAS_A_TODO_CAMPO | CEDIDAS_SO_AO_MULTILINHA:
            with self.subTest(tecla=tecla):
                self.assertIn(tecla, da_janela | de_edicao)

    def test_a_tecla_declarada_pelo_widget_continua_dele(self) -> None:
        """A S-117 não pode ter se perdido: é ela que segura o `Ctrl+R` do editor agora."""
        from chess_diagram_ocr.ui import atalhos as tabela

        self.assertIn("alinhar_direita", tabela.TECLAS_DO_EDITOR)
        self.assertEqual("<Control-r>", tabela.TECLAS_DO_EDITOR["alinhar_direita"])
        self.assertFalse(cede_a_tecla(self.editor(), "<Control-r>"), "o cobertor voltou")
