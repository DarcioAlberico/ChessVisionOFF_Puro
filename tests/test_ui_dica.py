"""A dica da janela: uma implementação só, e um `after` que morre com o widget (S-402/S-403).

Havia **duas** dicas na mesma janela: a de `ui/tooltip.py`, que explica um controle, e a do
`ui/board_widget.py`, que diz o que o modelo leu numa casa. Mesma `Toplevel` retirada, mesma
superfície, mesma borda -- e 350 ms contra 450. Atravessar a barra para o tabuleiro fazia a dica
aparecer mais cedo sem que nada explicasse por quê.

E as duas agendavam um `after` que ninguém cancelava quando o widget morria: sair de uma barra que
a troca de pele destrói no mesmo gesto deixava um relógio marcado para um widget inexistente.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.ui import board_widget, theme, tokens
from chess_diagram_ocr.ui.tooltip import TOOLTIP_DELAY_MS, Tooltip, janela_de_dica


class UmaDicaSoTests(unittest.TestCase):
    """O tempo e o cromo são da janela, e não de cada widget que mostra dica (S-403)."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.host = tk.Frame(self.root)
        self.addCleanup(self.host.destroy)

    def test_o_tabuleiro_usa_o_tempo_da_janela(self) -> None:
        """O 350 cravado era a segunda decisão sobre o mesmo número."""
        fonte = Path(board_widget.__file__).read_text(encoding="utf-8")
        self.assertNotIn("after(350", fonte)
        self.assertIn("TOOLTIP_DELAY_MS", fonte)

    def test_ha_um_unico_lugar_que_monta_a_caixinha(self) -> None:
        """`wm_overrideredirect` é a assinatura de uma dica: uma janela sem moldura, sem foco e
        sem barra de título. Duas ocorrências em `ui/` seriam duas dicas outra vez."""
        montam = [
            caminho.name
            for caminho in sorted(Path(board_widget.__file__).parent.glob("*.py"))
            if "wm_overrideredirect" in caminho.read_text(encoding="utf-8")
        ]
        self.assertEqual(["tooltip.py"], montam)

    def test_a_caixinha_nasce_com_a_cor_do_tema(self) -> None:
        janela = janela_de_dica(self.host, "uma dica", x=10, y=10)
        self.addCleanup(janela.destroy)
        rotulo = janela.winfo_children()[0]
        fundo = theme.cor_atual(tokens.SUPERFICIE_DICA)
        self.assertEqual(fundo, str(rotulo.cget("background")))
        self.assertEqual(tokens.sobre_superficie(fundo), str(rotulo.cget("foreground")))

    def test_a_fonte_e_opcional_e_e_do_chamador(self) -> None:
        """O tabuleiro passa a dele; a barra não passa nenhuma e fica com a do `Style`."""
        sem = janela_de_dica(self.host, "a", x=0, y=0)
        self.addCleanup(sem.destroy)
        com = janela_de_dica(self.host, "a", x=0, y=0, fonte=("Segoe UI", 9))
        self.addCleanup(com.destroy)
        self.assertEqual("", str(sem.winfo_children()[0].cget("font")))
        self.assertIn("Segoe UI", str(com.winfo_children()[0].cget("font")))


class DicaAgendadaMorreComOWidgetTests(unittest.TestCase):
    """O `after` de 450 ms que sobrevivia ao widget (S-402)."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.host = tk.Frame(self.root)
        self.botao = ttk.Button(self.host, text="um botão")
        self.dica = Tooltip(self.botao, "por que este botão está cinza")

    def tearDown(self) -> None:
        if self.host.winfo_exists():
            self.host.destroy()

    def test_destruir_o_widget_cancela_o_agendamento(self) -> None:
        self.dica._schedule()
        self.assertIsNotNone(self.dica._after)

        self.botao.destroy()

        self.assertIsNone(self.dica._after)

    def test_a_dica_que_acorda_depois_da_morte_nao_levanta(self) -> None:
        """O sintoma é este: um traceback na saída padrão por passar o ponteiro na hora errada.

        `report_callback_exception` é por onde o Tk manda o que estourou dentro de um `after` --
        e é o único lugar onde isso aparecia, porque o `after` não é do fluxo de ninguém.
        """
        estourou: list[BaseException] = []
        anterior = self.root.report_callback_exception
        self.root.report_callback_exception = lambda _tipo, valor, _tb: estourou.append(valor)
        self.addCleanup(setattr, self.root, "report_callback_exception", anterior)

        self.dica._schedule()
        self.botao.destroy()
        self.root.after(TOOLTIP_DELAY_MS + 60, self.root.quit)
        self.root.mainloop()

        self.assertEqual([], estourou)

    def test_a_morte_de_um_filho_nao_cancela_a_dica_do_pai(self) -> None:
        """`<Destroy>` sobe dos filhos, e a própria caixinha é filha do widget: sem a pergunta
        "foi você que morreu?", a dica se apagaria no instante em que aparecesse."""
        self.dica._schedule()
        agendado = self.dica._after
        ttk.Label(self.botao).destroy()
        self.assertEqual(agendado, self.dica._after)

