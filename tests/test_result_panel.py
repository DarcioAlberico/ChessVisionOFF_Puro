"""O campo do número do lance, na aba Resultado (S-71).

O número mora na anotação da galeria, e é lá que a exportação o lê. O que se testa aqui é a
parte que só quebra com widget: o campo seguir o diagrama selecionado, em branco **apagar** em
vez de gravar zero, número inválido avisar sem gravar, e o campo ficar cinza quando o que está
no editor não é o diagrama de uma página -- caso em que gravar apontaria para o diagrama errado.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.config import BUNDLE_ROOT
from chess_diagram_ocr.service import RecognitionOrigin, RecognizedDiagram
from chess_diagram_ocr.settings import RemoteFenSettings
from chess_diagram_ocr.ui.board_widget import PieceImages
from chess_diagram_ocr.ui.page_results import PageOcrParams
from chess_diagram_ocr.ui.result_panel import ResultPanel

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"
DOCUMENTO = "livro.pdf"
PAGINA = 16


def _diagrama() -> RecognizedDiagram:
    return RecognizedDiagram.from_label(np.zeros((8, 8, 3), dtype=np.uint8), PLACEMENT)


class MoveNumberFieldTests(unittest.TestCase):
    """Uma raiz Tk para a classe toda, pelo mesmo motivo do `test_gallery_panel`."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - maquina sem display
            raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def setUp(self) -> None:
        self.status: list[str] = []
        self.lances: dict[tuple[int, int], int | None] = {}
        self.gravacoes: list[tuple[int, int, int | None]] = []
        self.host = tk.Frame(self.root)

        def _gravar(pagina: int, diagrama: int, valor: int | None) -> None:
            self.gravacoes.append((pagina, diagrama, valor))
            if valor is None:
                self.lances.pop((pagina, diagrama), None)
            else:
                self.lances[(pagina, diagrama)] = valor

        self.panel = ResultPanel(
            self.host,
            service=None,  # type: ignore[arg-type] - so a gravacao o usa, e ela nao roda aqui
            piece_images=PieceImages(BUNDLE_ROOT / "assets" / "piece_images"),
            paths=lambda: (Path("labels.csv"), Path("samples")),
            ocr_params=lambda: PageOcrParams(dpi=220, max_boards=12, orientation="auto", model_path="m.pt"),
            document_key=lambda: DOCUMENTO,
            model_path=lambda: Path("m.pt"),
            on_status=self.status.append,
            on_ocr_local=lambda _max: None,
            max_boards=lambda: 12,
            on_sync_study=lambda: None,
            on_state_changed=lambda: None,
            on_focus_request=lambda: None,
            on_sample_saved=lambda: None,
            remote_fen=RemoteFenSettings,
            on_remote_consent=lambda _cfg: False,
            move_number_of=lambda pagina, diagrama: self.lances.get((pagina, diagrama)),
            on_move_number=_gravar,
        )

    def tearDown(self) -> None:
        self.host.destroy()

    def _abrir_pagina(self, quantos: int = 2) -> None:
        self.panel.show_ocr_results(
            [_diagrama() for _ in range(quantos)],
            RecognitionOrigin.for_page(DOCUMENTO, PAGINA),
        )

    # ------------------------------------------------------------------------ o campo

    def test_sem_nada_no_editor_o_campo_fica_cinza(self) -> None:
        self.assertEqual(str(self.panel.move_number_entry.cget("state")), "disabled")

    def test_com_uma_pagina_aberta_o_campo_liga(self) -> None:
        self._abrir_pagina()
        self.assertEqual(str(self.panel.move_number_entry.cget("state")), "normal")

    def test_grava_o_lance_do_diagrama_selecionado(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("24")
        self.panel._commit_move_number()
        self.assertEqual(self.gravacoes, [(PAGINA, 0, 24)])

    def test_o_campo_segue_o_diagrama_e_nao_vaza_para_o_vizinho(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("24")
        self.panel._commit_move_number()

        self.panel.next_diagram()
        self.assertEqual(self.panel.move_number_var.get(), "", "o lance do vizinho não pode vazar")
        self.panel.prev_diagram()
        self.assertEqual(self.panel.move_number_var.get(), "24")

    def test_trocar_de_diagrama_grava_o_que_estava_digitado(self) -> None:
        """O `FocusOut` do campo não dispara quando o foco está no tabuleiro."""
        self._abrir_pagina()
        self.panel.move_number_var.set("31")
        self.panel.next_diagram()
        self.assertEqual(self.lances[(PAGINA, 0)], 31)

    def test_em_branco_apaga_em_vez_de_gravar_zero(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("24")
        self.panel._commit_move_number()
        self.panel.move_number_var.set("")
        self.panel._commit_move_number()
        self.assertEqual(self.gravacoes[-1], (PAGINA, 0, None))
        self.assertNotIn((PAGINA, 0), self.lances)

    def test_numero_invalido_avisa_e_nao_grava(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("vinte e quatro")
        self.panel._commit_move_number()
        self.assertEqual(self.gravacoes, [])
        self.assertTrue(any("inválido" in mensagem for mensagem in self.status))

    def test_lance_zero_ou_negativo_tambem_e_invalido(self) -> None:
        self._abrir_pagina()
        for texto in ("0", "-3"):
            with self.subTest(texto=texto):
                self.panel.move_number_var.set(texto)
                self.panel._commit_move_number()
                self.assertEqual(self.gravacoes, [])

    def test_o_campo_volta_ao_valor_gravado_depois_de_recusar(self) -> None:
        self._abrir_pagina()
        self.panel.move_number_var.set("12")
        self.panel._commit_move_number()
        self.panel.move_number_var.set("doze")
        self.panel._commit_move_number()
        self.assertEqual(self.panel.move_number_var.get(), "12")

    def test_regravar_o_mesmo_numero_nao_escreve_de_novo(self) -> None:
        """O campo confirma no `FocusOut`, que dispara a cada passagem do foco."""
        self._abrir_pagina()
        self.panel.move_number_var.set("7")
        self.panel._commit_move_number()
        self.panel._commit_move_number()
        self.panel._commit_move_number()
        self.assertEqual(len(self.gravacoes), 1)

    def test_recorte_de_area_nao_tem_onde_gravar_o_lance(self) -> None:
        """Recorte não é o diagrama N da página N: gravar apontaria para outro diagrama."""
        self.panel.show_ocr_results(
            [_diagrama()], RecognitionOrigin.for_crop(DOCUMENTO, PAGINA, (0, 0, 10, 10))
        )
        self.assertEqual(str(self.panel.move_number_entry.cget("state")), "disabled")
        self.panel.move_number_var.set("24")
        self.panel._commit_move_number()
        self.assertEqual(self.gravacoes, [])


if __name__ == "__main__":
    unittest.main()
