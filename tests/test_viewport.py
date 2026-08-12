"""A vista da página: roda, zoom ancorado e ajuste à largura (S-70).

Três decisões que só se percebe errando ao usar -- a roda que vira quatro páginas de uma vez,
o zoom que joga fora o que a pessoa estava olhando, o "ajustar à largura" que acende a barra
horizontal que ele deveria apagar. Nenhuma precisa de janela para ser conferida.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui.viewport import (
    MAX_ZOOM,
    MIN_ZOOM,
    PAGE_FLIP_COOLDOWN_S,
    WheelAction,
    anchor_after_zoom,
    clamp_zoom,
    decide_wheel,
    fit_width_zoom,
    wheel_direction,
    zoomed,
)

MEIO = (0.3, 0.7)
"""A vista no meio da página: nem no topo, nem no rodapé."""

TOPO = (0.0, 0.4)
RODAPE = (0.6, 1.0)
FRIO = PAGE_FLIP_COOLDOWN_S + 1.0
"""Tempo desde a última virada, folgado o bastante para a carência ter passado."""


class WheelDirectionTests(unittest.TestCase):
    def test_windows_manda_multiplos_de_120_e_o_mac_manda_um(self) -> None:
        """Só o sinal é comum às plataformas, e só ele é lido."""
        self.assertEqual(wheel_direction(120), 1)
        self.assertEqual(wheel_direction(1), 1)
        self.assertEqual(wheel_direction(-240), -1)
        self.assertEqual(wheel_direction(0), 0)


class WheelDecisionTests(unittest.TestCase):
    def test_no_meio_da_pagina_a_roda_so_rola(self) -> None:
        self.assertIs(
            decide_wheel(direction=-1, view=MEIO, since_last_flip=FRIO), WheelAction.SCROLL
        )
        self.assertIs(
            decide_wheel(direction=1, view=MEIO, since_last_flip=FRIO), WheelAction.SCROLL
        )

    def test_descer_no_rodape_vira_para_a_proxima(self) -> None:
        self.assertIs(
            decide_wheel(direction=-1, view=RODAPE, since_last_flip=FRIO), WheelAction.NEXT_PAGE
        )

    def test_subir_no_topo_volta_uma_pagina(self) -> None:
        self.assertIs(
            decide_wheel(direction=1, view=TOPO, since_last_flip=FRIO), WheelAction.PREV_PAGE
        )

    def test_no_rodape_subindo_ainda_e_rolagem(self) -> None:
        """Chegar ao fim não prende a roda para trás."""
        self.assertIs(
            decide_wheel(direction=1, view=RODAPE, since_last_flip=FRIO), WheelAction.SCROLL
        )

    def test_a_rajada_da_roda_inercial_nao_pula_quatro_paginas(self) -> None:
        self.assertIs(
            decide_wheel(direction=-1, view=RODAPE, since_last_flip=0.05), WheelAction.SCROLL
        )

    def test_desligada_a_virada_a_borda_deixa_de_ser_borda(self) -> None:
        self.assertIs(
            decide_wheel(direction=-1, view=RODAPE, flip_pages=False, since_last_flip=FRIO),
            WheelAction.SCROLL,
        )

    def test_a_pagina_que_cabe_inteira_esta_nas_duas_bordas(self) -> None:
        """`yview()` devolve (0,0, 1,0) quando não há o que rolar -- e aí a roda navega."""
        inteira = (0.0, 1.0)
        self.assertIs(
            decide_wheel(direction=-1, view=inteira, since_last_flip=FRIO), WheelAction.NEXT_PAGE
        )
        self.assertIs(
            decide_wheel(direction=1, view=inteira, since_last_flip=FRIO), WheelAction.PREV_PAGE
        )

    def test_giro_sem_direcao_nao_faz_nada(self) -> None:
        self.assertIs(
            decide_wheel(direction=0, view=RODAPE, since_last_flip=FRIO), WheelAction.SCROLL
        )

    def test_a_borda_e_aproximada_porque_a_fracao_e_float(self) -> None:
        self.assertIs(
            decide_wheel(direction=-1, view=(0.6, 0.9999), since_last_flip=FRIO),
            WheelAction.NEXT_PAGE,
        )


class ZoomTests(unittest.TestCase):
    def test_o_passo_e_multiplicativo(self) -> None:
        """Aditivo de 0,1 dá salto de 33% em 0,3 e de 5% em 1,9 -- a mesma tecla, efeitos
        diferentes."""
        perto = zoomed(0.30, +1) / 0.30
        longe = zoomed(1.00, +1) / 1.00
        self.assertAlmostEqual(perto, longe, places=6)

    def test_respeita_os_limites_nos_dois_lados(self) -> None:
        self.assertEqual(zoomed(MIN_ZOOM, -1), MIN_ZOOM)
        self.assertEqual(zoomed(MAX_ZOOM, +1), MAX_ZOOM)

    def test_sem_direcao_o_zoom_so_e_grampeado(self) -> None:
        self.assertEqual(zoomed(5.0, 0), MAX_ZOOM)
        self.assertEqual(clamp_zoom(0.01), MIN_ZOOM)


class AnchorTests(unittest.TestCase):
    def test_o_ponto_sob_o_ponteiro_fica_parado(self) -> None:
        """Dobrar o zoom com o ponteiro no meio de uma página de 1.000 px."""
        fracao = anchor_after_zoom(
            pointer_canvas=500.0, pointer_widget=100.0, old_span=1000.0, new_span=2000.0
        )
        # O ponto foi de 500 para 1.000; para ele continuar 100 px abaixo do topo da janela,
        # a vista precisa começar em 900 -- que é 0,45 de 2.000.
        self.assertAlmostEqual(fracao, 0.45)

    def test_perto_da_borda_a_fracao_nao_escapa_do_intervalo(self) -> None:
        self.assertEqual(
            anchor_after_zoom(pointer_canvas=0.0, pointer_widget=300.0, old_span=1000.0, new_span=2000.0),
            0.0,
        )
        self.assertEqual(
            anchor_after_zoom(pointer_canvas=1000.0, pointer_widget=0.0, old_span=1000.0, new_span=2000.0),
            1.0,
        )

    def test_pagina_sem_tamanho_nao_divide_por_zero(self) -> None:
        self.assertEqual(
            anchor_after_zoom(pointer_canvas=10.0, pointer_widget=5.0, old_span=0.0, new_span=100.0),
            0.0,
        )


class FitWidthTests(unittest.TestCase):
    def test_a_pagina_cabe_na_largura_visivel(self) -> None:
        self.assertAlmostEqual(fit_width_zoom(viewport_px=904, page_px=900, margin_px=4), 1.0)

    def test_a_margem_desconta_a_barra_de_rolagem(self) -> None:
        """Sem ela, ajustar à largura acende a barra horizontal que ele existe para apagar."""
        self.assertLess(fit_width_zoom(viewport_px=900, page_px=900) or 0.0, 1.0)

    def test_pagina_larga_demais_ainda_respeita_o_minimo(self) -> None:
        self.assertEqual(fit_width_zoom(viewport_px=100, page_px=9000), MIN_ZOOM)

    def test_sem_janela_medida_ainda_devolve_nada_em_vez_de_um_palpite(self) -> None:
        """A largura vem de `winfo_width`, que é 1 enquanto o layout não assentou."""
        self.assertIsNone(fit_width_zoom(viewport_px=1, page_px=900))
        self.assertIsNone(fit_width_zoom(viewport_px=800, page_px=0))


class NoTkinterTests(unittest.TestCase):
    def test_o_modulo_nao_importa_tkinter(self) -> None:
        import ast
        from pathlib import Path

        from chess_diagram_ocr.ui import viewport

        arvore = ast.parse(Path(viewport.__file__).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for node in ast.walk(arvore):
            if isinstance(node, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                importados.add(node.module.split(".")[0])

        self.assertNotIn("tkinter", importados)


if __name__ == "__main__":
    unittest.main()
