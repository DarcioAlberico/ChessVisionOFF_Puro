"""Tirar da página o retângulo que o detector marcou errado (S-177).

**O que isto fecha.** O detector erra, e a caixa errada não é inerte: ela ocupa uma vaga do
`max_boards`, entra na numeração que o `[Diagram "N"]` do PGN usa e -- quando é grande, que é o
caso da faixa de página da S-176 -- esconde os diagramas de verdade debaixo dela. A única
resposta disponível era desligar "Marcar diagramas" para a página inteira, que apaga junto o
que estava certo, ou anotar a página no conjunto de campo, que é gravar no disco uma afirmação
sobre o livro quando o que se queria era limpar a tela.

A regra de `DroppedBoxes` está em `test_page_overlay.py` e o gesto na tela em
`test_pdf_panel.py`. O que sobra para cá é a costura: a janela guardar a remoção, o desenho
seguinte não trazer a caixa de volta, e devolver ser página a página.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.ui.page_overlay import (
    DiagramBox,
    DroppedBoxes,
    OverlayParams,
    PageBoxes,
    PageBoxesCache,
)

PARAMS = OverlayParams(dpi=72, max_boards=12)

FAIXA = DiagramBox(index=0, bbox_pdf=(-9.0, 11.6, 450.8, 414.8), source="embedded")
"""A caixa do relato da S-176: 460×403 pt sobre uma página de 453×666."""

DIAGRAMA = DiagramBox(index=1, bbox_pdf=(278.0, 437.8, 427.8, 606.8), source="embedded")


def _app_tkinter():  # noqa: ANN202
    """`app_tkinter.py` mora na raiz e não é pacote; o pytest só põe `src/` no path."""
    raiz = str(Path(__file__).resolve().parents[1])
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import app_tkinter

    return app_tkinter


class _PainelFalso:
    """O bastante do `PdfPanel` para a janela desenhar caixas sem abrir uma janela."""

    def __init__(self, page_index: int = 14) -> None:
        self.source = Path("Yusupov.pdf")
        self.page_rgb = np.zeros((10, 10, 3), dtype=np.uint8)
        self.page_index = page_index
        self.boxes: PageBoxes | None = None
        self.desenhadas: list[PageBoxes] = []

    def set_diagram_boxes(self, caixas: PageBoxes) -> bool:
        self.boxes = caixas
        self.desenhadas.append(caixas)
        return True


def _janela(painel: _PainelFalso):  # noqa: ANN202
    """A janela reduzida aos métodos que a remoção toca, com os métodos **reais**.

    Mesmo recurso do `test_dataset_panel._janela_minima`: montar o `ChessOcrTkApp` inteiro
    exigiria checkpoint e PDF, e o que se testa aqui é a costura entre a remoção e o desenho.
    """
    app_tkinter = _app_tkinter()
    tipo = type(
        "JanelaMinima",
        (),
        {
            "_drop_box": app_tkinter.ChessOcrTkApp._drop_box,
            "restore_dropped_boxes": app_tkinter.ChessOcrTkApp.restore_dropped_boxes,
            "_refresh_overlay": app_tkinter.ChessOcrTkApp._refresh_overlay,
            "_announce_if_page_done": app_tkinter.ChessOcrTkApp._announce_if_page_done,
            "_document_key": lambda self: str(self.pdf_panel.source),
            "_overlay_params": lambda self: PARAMS,
            "_page_items": lambda self, _pagina: [],
            "_sync_selected_box": lambda self: None,
            "_set_status": lambda self, texto: self.status.append(texto),
            "_request_overlay": lambda self, pagina, _params: self.pedidos.append(pagina),
        },
    )
    janela = tipo()
    janela.pdf_panel = painel
    janela.page_boxes = PageBoxesCache()
    janela.dropped_boxes = DroppedBoxes()
    janela.saved_diagrams = {}
    janela.confirmed_diagrams = {}
    janela.status = []
    janela.pedidos = []
    return janela


class TirarACaixaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.painel = _PainelFalso()
        self.janela = _janela(self.painel)
        self.janela.page_boxes.put(
            str(self.painel.source), PageBoxes(14, PARAMS, (FAIXA, DIAGRAMA))
        )
        self.janela._refresh_overlay(14)

    def _na_tela(self) -> list[int]:
        assert self.painel.boxes is not None
        return [box.index for box in self.painel.boxes.boxes]

    def test_a_caixa_tirada_some_do_desenho_seguinte(self) -> None:
        self.assertEqual(self._na_tela(), [0, 1])
        self.janela._drop_box(0)
        self.assertEqual(self._na_tela(), [1])

    def test_o_cache_do_detector_nao_e_reescrito(self) -> None:
        """O cache guarda o que o **detector** achou; reescrevê-lo faria a remoção parecer
        detecção -- e a remoção é um juízo humano sobre uma página, não um resultado."""
        self.janela._drop_box(0)
        guardadas = self.janela.page_boxes.get(str(self.painel.source), 14, PARAMS)
        assert guardadas is not None
        self.assertEqual([box.index for box in guardadas.boxes], [0, 1])

    def test_virar_a_pagina_e_voltar_nao_traz_a_caixa_de_volta(self) -> None:
        """A remoção é da sessão, e sobrevive dentro dela: senão o gesto não resolve nada."""
        self.janela._drop_box(0)
        self.janela._refresh_overlay(14)
        self.assertEqual(self._na_tela(), [1])

    def test_uma_pagina_com_todas_as_caixas_tiradas_fica_vazia_e_nao_redetecta(self) -> None:
        """Redetectar traria de volta exatamente o que o usuário recusou."""
        self.janela._drop_box(0)
        self.janela._drop_box(1)
        self.janela._refresh_overlay(14)
        self.assertEqual(self._na_tela(), [])
        self.assertEqual(self.janela.pedidos, [], "a página foi mandada de volta ao detector")

    def test_a_barra_de_status_diz_quantas_ja_foram_tiradas(self) -> None:
        self.janela._drop_box(0)
        self.assertIn("Caixa 1 tirada", self.janela.status[-1])
        self.janela._drop_box(1)
        self.assertIn("2 caixas tiradas", self.janela.status[-1])

    def test_tirar_uma_caixa_que_nao_esta_mais_na_pagina_avisa(self) -> None:
        self.janela._drop_box(0)
        self.janela._drop_box(0)
        self.assertIn("não está mais na página", self.janela.status[-1])

    def test_devolver_traz_de_volta_e_repinta(self) -> None:
        self.janela._drop_box(0)
        self.janela.restore_dropped_boxes()
        self.assertEqual(self._na_tela(), [0, 1])
        self.assertIn("1 caixa devolvida", self.janela.status[-1])

    def test_devolver_numa_pagina_sem_remocao_nao_repinta_nem_mente(self) -> None:
        desenhos = len(self.painel.desenhadas)
        self.janela.restore_dropped_boxes()
        self.assertIn("Nenhuma caixa foi tirada", self.janela.status[-1])
        self.assertEqual(len(self.painel.desenhadas), desenhos)

    def test_devolver_e_da_pagina_exibida_e_nao_um_desfazer_global(self) -> None:
        """Desfazer noutra página mudaria o que o usuário não está vendo."""
        self.janela._drop_box(0)
        self.painel.page_index = 15
        self.janela.dropped_boxes.drop(str(self.painel.source), 15, DIAGRAMA.bbox_pdf)
        self.janela.restore_dropped_boxes()
        self.assertEqual(self.janela.dropped_boxes.count(str(self.painel.source), 14), 1)
        self.assertEqual(self.janela.dropped_boxes.count(str(self.painel.source), 15), 0)


if __name__ == "__main__":
    unittest.main()
