"""O deslizador de zoom da pele "Foco" (S-225).

O zoom do PDF eram cinco controles em fila -- `-`, `+`, o rótulo `70%`, "Ajustar à largura" e
"Ajustar à página" --, e cada clique movia 0,1: ir de 70% a 150% eram **oito cliques**. O
deslizador substitui **três** deles, e não cinco: enquadrar não é um valor de zoom, é uma pergunta
sobre a página que o deslizador não sabe responder.

A aritmética é de `ui/viewport.py` e se afirma sem abrir janela; o que precisa de Tk é a ligação
-- que o arrasto move o zoom, e que tudo o mais move o deslizador.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path

import numpy as np
from tk_root import raiz

from chess_diagram_ocr.ui import formato, pele, viewport
from chess_diagram_ocr.ui.pdf_panel import PdfPanel


class EscalaTests(unittest.TestCase):
    """A conversão posição ↔ zoom, pura."""

    def test_o_deslizador_respeita_o_clamp(self) -> None:
        """As pontas são exatamente `MIN_ZOOM` e `MAX_ZOOM`, e nada fora delas passa."""
        self.assertEqual(viewport.MIN_ZOOM, viewport.zoom_da_posicao(0))
        self.assertEqual(viewport.MAX_ZOOM, viewport.zoom_da_posicao(viewport.LADO_DO_DESLIZADOR))
        self.assertEqual(viewport.MIN_ZOOM, viewport.zoom_da_posicao(-40))
        self.assertEqual(viewport.MAX_ZOOM, viewport.zoom_da_posicao(1000))
        self.assertEqual(0.0, viewport.posicao_do_zoom(0.01))
        self.assertEqual(viewport.LADO_DO_DESLIZADOR, viewport.posicao_do_zoom(9.0))

    def test_a_conversao_volta_no_mesmo_lugar(self) -> None:
        for zoom in (0.25, 0.4, 0.7, 1.0, 1.35, 2.0):
            with self.subTest(zoom=zoom):
                self.assertAlmostEqual(zoom, viewport.zoom_da_posicao(viewport.posicao_do_zoom(zoom)), places=9)

    def test_a_escala_e_logaritmica(self) -> None:
        """O meio do curso é a **média geométrica** das pontas, e não a aritmética.

        Numa escala linear entre 25% e 200% o meio seria 112,5% -- e a metade que importa, a de
        enquadrar um diagrama pequeno, se espremeria nos primeiros milímetros.
        """
        meio = viewport.zoom_da_posicao(viewport.LADO_DO_DESLIZADOR / 2)
        self.assertAlmostEqual((viewport.MIN_ZOOM * viewport.MAX_ZOOM) ** 0.5, meio, places=9)
        self.assertLess(meio, (viewport.MIN_ZOOM + viewport.MAX_ZOOM) / 2)

    def test_passos_iguais_movem_razoes_iguais(self) -> None:
        """A propriedade que a escala logarítmica compra, e a razão de a roda concordar com ela:
        `zoomed` multiplica por `ZOOM_STEP`, e aqui o curso inteiro é multiplicativo."""
        passo = 10.0
        razoes = [
            viewport.zoom_da_posicao(p + passo) / viewport.zoom_da_posicao(p)
            for p in (0.0, 25.0, 50.0, 75.0)
        ]
        for razao in razoes[1:]:
            self.assertAlmostEqual(razoes[0], razao, places=9)


class LigacaoTests(unittest.TestCase):
    """O deslizador ligado ao painel: o que ele move, e o que move ele."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        # Uma janela com geometria de verdade: o teste da âncora lê `xview`, e um canvas de
        # largura 1 não tem vista para preservar.
        self.janela = tk.Toplevel(self.root)
        self.janela.geometry("900x700+40+40")
        self.addCleanup(self.janela.destroy)
        self.host = tk.Frame(self.janela)
        self.host.pack(fill=tk.BOTH, expand=True)
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
            initial_dir=Path("."),
            on_box_click=lambda _indice: None,
            on_box_drop=lambda _indice: None,
            on_prefs_changed=lambda: None,
        )
        self.panel.source = Path("livro.pdf")
        self.panel.name = "livro.pdf"
        self.panel.page_count = 4
        self.panel.page_rgb = np.zeros((900, 600, 3), dtype=np.uint8)
        self.panel.page_loaded_for_index = 0
        self.panel.pack(fill=tk.BOTH, expand=True)
        self.panel.zoom_var.set(0.7)
        self.panel.refresh_view()
        self.root.update_idletasks()

    def test_a_pele_classica_nao_ganha_deslizador(self) -> None:
        """O critério que protege a regra 1: quem não abrir `Ver ▸ Aparência` não vê diferença."""
        self.assertIsNone(self.panel._deslizador)
        self.panel.remontar_cromo(pele.CROMO_CLASSICO)
        self.assertIsNone(self.panel._deslizador)

    def test_arrastar_move_o_zoom_pela_escala(self) -> None:
        self.panel.remontar_cromo(pele.CROMO_FOCO)
        assert self.panel._deslizador is not None

        self.panel._ao_arrastar_zoom(str(viewport.LADO_DO_DESLIZADOR / 2))

        self.assertAlmostEqual(viewport.zoom_da_posicao(50.0), self.panel.zoom_var.get(), places=6)

    def test_enquadrar_move_o_deslizador(self) -> None:
        """"Ajustar à largura" continua existindo, e o deslizador o segue -- é o critério inteiro:
        o deslizador não substitui enquadrar, ele o **mostra**."""
        self.panel.remontar_cromo(pele.CROMO_FOCO)
        assert self.panel._deslizador is not None
        self.root.update_idletasks()

        self.panel.apply_zoom(1.6)

        self.assertAlmostEqual(
            viewport.posicao_do_zoom(1.6), float(self.panel._deslizador.get()), places=6
        )

    def test_a_roda_com_ctrl_tambem_o_move(self) -> None:
        """`zoomed` é multiplicativo e a escala também: um giro move sempre a mesma distância."""
        self.panel.remontar_cromo(pele.CROMO_FOCO)
        assert self.panel._deslizador is not None

        antes = float(self.panel._deslizador.get())
        self.panel.apply_zoom(viewport.zoomed(self.panel.zoom_var.get(), 1))
        um_giro = float(self.panel._deslizador.get()) - antes

        self.panel.apply_zoom(viewport.zoomed(self.panel.zoom_var.get(), 1))
        outro_giro = float(self.panel._deslizador.get()) - antes - um_giro

        self.assertAlmostEqual(um_giro, outro_giro, places=6)

    def test_o_deslizador_preserva_a_ancora(self) -> None:
        """Arrastar mantém no lugar o ponto que está no **centro da vista** -- o mesmo que
        `apply_zoom` já fazia para os botões `+` e `-`, e o que a roda faz com o ponteiro.

        Sem isso, aumentar o zoom saltaria para o canto superior esquerdo da folha, e quem estava
        conferindo um diagrama no meio da página o perderia a cada arrasto.
        """
        self.root.update_idletasks()
        self.panel.remontar_cromo(pele.CROMO_FOCO)
        self.root.update_idletasks()
        if self.panel.canvas.winfo_width() <= 1:  # pragma: no cover - janela sem geometria
            self.skipTest("o canvas não recebeu largura nesta máquina")

        def ponto_no_centro() -> tuple[float, float]:
            """Onde, na folha, está o pixel do meio da vista -- em fração da página."""
            x0, x1 = self.panel.canvas.xview()
            y0, y1 = self.panel.canvas.yview()
            return (x0 + x1) / 2, (y0 + y1) / 2

        self.panel.canvas.xview_moveto(0.4)
        self.panel.canvas.yview_moveto(0.6)
        self.root.update_idletasks()
        antes = ponto_no_centro()

        self.panel._ao_arrastar_zoom(str(viewport.posicao_do_zoom(1.5)))
        self.root.update_idletasks()

        for eixo, (a, b) in enumerate(zip(antes, ponto_no_centro(), strict=True)):
            with self.subTest(eixo="x" if eixo == 0 else "y"):
                self.assertAlmostEqual(a, b, places=2)

    def test_arrastar_nao_entra_em_laco(self) -> None:
        """`Scale.set` dispara o `command`, e o `command` chama `apply_zoom`, que chama
        `update_zoom_label`, que chama `Scale.set`. Sem a guarda, isto não termina."""
        self.panel.remontar_cromo(pele.CROMO_FOCO)
        chamadas: list[float] = []
        original = self.panel.apply_zoom
        self.panel.apply_zoom = lambda valor, **kw: (chamadas.append(valor), original(valor, **kw))[1]  # type: ignore[method-assign]

        self.panel._ao_arrastar_zoom("40")

        self.assertEqual(1, len(chamadas), f"apply_zoom foi chamada {len(chamadas)} vezes")

    def test_o_rotulo_e_o_mesmo_texto_nos_dois_lugares(self) -> None:
        """E ele vem de `ui/formato.py`: era um `f"{int(...)}%"` cravado no painel, e duas
        formatações do mesmo número é como elas divergem."""
        self.panel.remontar_cromo(pele.CROMO_FOCO)
        assert self.panel._lbl_zoom_deslizador is not None
        self.panel.apply_zoom(1.25)

        esperado = formato.porcentagem(1.25, casas=0)
        self.assertEqual("125%", esperado)
        self.assertEqual(esperado, str(self.panel._lbl_zoom_deslizador.cget("text")))
        self.assertEqual(esperado, str(self.panel.lbl_zoom.cget("text")))

    def test_voltar_para_a_classica_leva_o_deslizador_embora(self) -> None:
        self.panel.remontar_cromo(pele.CROMO_FOCO)
        self.panel.remontar_cromo(pele.CROMO_CLASSICO)
        self.assertIsNone(self.panel._deslizador)
        self.assertIsNone(self.panel._rodape_de_zoom)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
