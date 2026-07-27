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

from chess_diagram_ocr.ui.shortcuts import guard, ignores_widget


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
