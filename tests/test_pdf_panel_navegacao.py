"""A virada de folha: o que ela faz, e o que ela deixa de fazer (S-304, S-305).

Dois defeitos de navegação que a suíte não pegava porque nada tocava `prev_page`, `next_page`
nem o campo de página -- os testes de roda substituem `render_current_page`, e os de caixas
entram pela lateral.

**S-304.** `prev_page`/`next_page` grampeavam o índice e mandavam rasterizar de qualquer jeito.
Na última folha, cada giro da roda re-rasterizava a *mesma* página, e como `render_current_page`
termina em `yview_moveto(0)`, a vista voltava ao topo a cada giro. Quem lia o fim de uma folha
larga era jogado para o começo dela, sem que nada mudasse na tela.

**S-305.** O `command` de um `ttk.Spinbox` só dispara nas setas. Digitar `15` e teclar `Enter`
mudava `page_index_var` sem mudar a imagem: o rodapé passava a falar de uma folha, e a tela
mostrava outra -- e as caixas de diagrama da folha exibida eram recusadas por serem "de outra
página". Texto não numérico era pior: `page_index` faz `int()` sobre um `IntVar`, e as cinco
funções que o leem levantavam `TclError` num projeto sem `report_callback_exception`.
"""

from __future__ import annotations

import shutil
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

import fitz
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.ui.pdf_panel import PdfPanel


class _Navegacao(unittest.TestCase):
    """Um painel de verdade sobre um PDF de verdade, com o render instrumentado."""

    root: tk.Tk
    paginas = 3

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cvoff-nav-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.livro = self.tmp / "livro.pdf"
        doc = fitz.open()
        for _ in range(self.paginas):
            doc.new_page(width=200, height=300)
        doc.save(str(self.livro))
        doc.close()

        self.host = tk.Frame(self.root)
        self.addCleanup(self.host.destroy)
        self.panel = PdfPanel(
            self.host,
            dpi=lambda: 72,
            initial_page_for=lambda _caminho: 0,
            on_status=lambda _texto: None,
            on_ocr_best=lambda: None,
            on_ocr_all=lambda: None,
            on_region=lambda _imagem, _regiao: None,
            on_export=lambda: None,
            on_cancel_export=lambda: None,
            on_pdf_opened=lambda _caminho: None,
            on_before_page_change=lambda: None,
            on_page_rendered=lambda _indice: None,
            on_zoom_changed=lambda _zoom: None,
            initial_dir=self.tmp,
        )
        self.panel.pack()
        self.panel.load_pdf(self.livro)
        self.root.update_idletasks()

        self.renderizadas: list[int] = []
        original = self.panel.render_current_page

        def contando() -> bool:
            self.renderizadas.append(self.panel.page_index)
            return original()

        self.panel.render_current_page = contando  # type: ignore[method-assign]


class LimiteDoLivroTests(_Navegacao):
    def test_a_roda_na_ultima_folha_nao_re_rasteriza(self) -> None:
        """S-304: cinco `next_page` na última folha davam cinco rasterizações da mesma página."""
        self.panel.go_to_page(self.paginas - 1)
        self.renderizadas.clear()

        for _ in range(5):
            self.panel.next_page()

        self.assertEqual(self.renderizadas, [])
        self.assertEqual(self.panel.page_index, self.paginas - 1)

    def test_a_roda_na_primeira_folha_nao_re_rasteriza(self) -> None:
        self.panel.go_to_page(0)
        self.renderizadas.clear()

        for _ in range(3):
            self.panel.prev_page()

        self.assertEqual(self.renderizadas, [])
        self.assertEqual(self.panel.page_index, 0)

    def test_virar_para_uma_folha_que_existe_continua_rasterizando(self) -> None:
        """O contrário, e é ele que impede a guarda de virar "a virada parou de funcionar"."""
        self.panel.go_to_page(0)
        self.renderizadas.clear()

        self.panel.next_page()

        self.assertEqual(self.renderizadas, [1])
        self.assertEqual(self.panel.page_index, 1)

    def test_sem_imagem_a_ultima_folha_ainda_re_tenta(self) -> None:
        """A guarda testa `page_rgb` além do índice: só o índice tiraria o jeito de tentar de
        novo depois de um render que falhou."""
        self.panel.go_to_page(self.paginas - 1)
        self.panel.page_rgb = None
        self.renderizadas.clear()

        self.panel.next_page()

        self.assertEqual(self.renderizadas, [self.paginas - 1])


class NumeroDigitadoTests(_Navegacao):
    def test_o_numero_digitado_navega(self) -> None:
        """S-305: `Enter` no campo mudava o número e deixava a imagem onde estava."""
        self.renderizadas.clear()
        self.panel.spin_page.delete(0, tk.END)
        self.panel.spin_page.insert(0, "2")

        self.panel._on_page_typed()

        self.assertEqual(self.panel.page_index, 2)
        self.assertEqual(self.renderizadas, [2])

    def test_texto_invalido_nao_derruba_e_repoe_o_numero(self) -> None:
        """Antes: `TclError` em `page_index` e em mais quatro funções, direto no stderr.

        Repor é a única resposta honesta: mandar para a folha 1 escolheria um destino que
        ninguém pediu, e deixar `abc` no campo manteria a dessincronia que o item conserta.
        """
        self.panel.go_to_page(1)
        self.renderizadas.clear()
        self.panel.spin_page.delete(0, tk.END)
        self.panel.spin_page.insert(0, "abc")

        self.panel._on_page_typed()

        self.assertEqual(self.panel.page_index, 1)
        self.assertEqual(str(self.panel.spin_page.get()), "1")
        self.assertEqual(self.renderizadas, [])

    def test_campo_vazio_no_focus_out_repoe_o_numero(self) -> None:
        """Acontece a cada limpeza no meio da edição, e não pode navegar para lugar nenhum."""
        self.panel.go_to_page(1)
        self.panel.spin_page.delete(0, tk.END)

        self.panel._on_page_typed()

        self.assertEqual(self.panel.page_index, 1)
        self.assertEqual(str(self.panel.spin_page.get()), "1")

    def test_numero_fora_da_faixa_volta_para_onde_a_tela_esta(self) -> None:
        self.panel.go_to_page(1)
        self.renderizadas.clear()
        self.panel.spin_page.delete(0, tk.END)
        self.panel.spin_page.insert(0, "999")

        self.panel._on_page_typed()

        self.assertEqual(self.panel.page_index, self.paginas - 1)
        self.assertEqual(str(self.panel.spin_page.get()), str(self.paginas - 1))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
