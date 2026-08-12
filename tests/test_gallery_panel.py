"""A aba Galeria montada de verdade, sem PDF e sem varredura (S-67).

O `gallery_model` cobre a regra; o que sobra para cá é o que só quebra com widget: os campos
lerem a anotação certa ao trocar de diagrama, o pedido de página não voltar em círculo, e o
`Entry` em branco apagar a declaração em vez de gravar string vazia.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from chess_diagram_ocr.gallery import GalleryAnnotations, load_annotations
from chess_diagram_ocr.gallery_scan import GalleryEntry, GalleryIndex
from chess_diagram_ocr.ui.gallery_model import GalleryModel
from chess_diagram_ocr.ui.gallery_panel import GalleryPanel

PLACEMENT = "4k3/8/8/8/8/8/8/4K3"


class GalleryPanelTests(unittest.TestCase):
    """Uma raiz Tk para a classe toda, e não uma por teste.

    Não é micro-otimização: nesta máquina, criar e destruir `tk.Tk()` repetidamente acaba
    falhando com `Can't find a usable init.tcl`, e o resultado é um arquivo de teste que
    passa, pula ou falha conforme quantos rodaram antes dele. Uma raiz só torna o resultado
    determinístico; cada teste ainda monta o seu painel do zero.
    """

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
        self.pedidos: list[int] = []
        self.status: list[str] = []
        self.pasta = tempfile.TemporaryDirectory()
        self.host = tk.Frame(self.root)

        self.panel = GalleryPanel(
            self.host,
            service=None,  # type: ignore[arg-type] - so a varredura o usa, e ela nao roda aqui
            pdf_path=lambda: Path(self.pasta.name) / "livro.pdf",
            model_path=lambda: Path("modelo.pt"),
            max_boards=lambda: 12,
            on_status=self.status.append,
            on_page_request=self.pedidos.append,
        )
        self.panel.model = GalleryModel(
            index=GalleryIndex(
                entries=[
                    GalleryEntry(0, 0, PLACEMENT, side_to_move="w"),
                    GalleryEntry(4, 0, PLACEMENT, side_to_move="b"),
                ]
            ),
            annotations=GalleryAnnotations(),
            pdf_path=Path(self.pasta.name) / "livro.pdf",
            gallery_dir=Path(self.pasta.name),
        )
        self.panel.refresh()

    def tearDown(self) -> None:
        self.host.destroy()
        self.pasta.cleanup()

    def test_abre_no_primeiro_e_pede_a_pagina_dele(self) -> None:
        self.assertIn("diagrama 1 de 2", self.panel.position_var.get())
        self.assertEqual(self.pedidos[-1], 0)

    def test_navegar_pede_a_pagina_do_novo_diagrama(self) -> None:
        self.panel._go(1)
        self.assertIn("página 5", self.panel.position_var.get())
        self.assertEqual(self.pedidos[-1], 4)

    def test_a_vez_lida_pela_varredura_aparece_no_radio(self) -> None:
        self.panel._go(1)
        self.assertEqual(self.panel.side_var.get(), "b")

    def test_campos_seguem_o_diagrama_selecionado(self) -> None:
        self.panel.move_var.set("24")
        self.panel._commit_move()
        self.panel._go(1)
        self.assertEqual(self.panel.move_var.get(), "", "o lance do vizinho não pode vazar")
        self.panel._go(-1)
        self.assertEqual(self.panel.move_var.get(), "24")

    def test_lance_invalido_avisa_e_nao_grava(self) -> None:
        self.panel.move_var.set("vinte")
        self.panel._commit_move()
        self.assertIsNone(self.panel.model.current_annotation.move_number)
        self.assertTrue(any("inválido" in mensagem for mensagem in self.status))

    def test_header_em_branco_apaga_em_vez_de_gravar_vazio(self) -> None:
        self.panel.header_vars["White"].set("Tal")
        self.panel._commit_header("White")
        self.assertEqual(self.panel.model.current_annotation.headers, {"White": "Tal"})

        self.panel.header_vars["White"].set("")
        self.panel._commit_header("White")
        self.assertEqual(self.panel.model.annotated_count(), 0)

    def test_link_tri_estado(self) -> None:
        self.panel.link_var.set("não")
        self.panel._commit_link()
        self.assertIs(self.panel.model.current_annotation.lichess_link, False)

        self.panel.link_var.set("")
        self.panel._commit_link()
        self.assertIsNone(self.panel.model.current_annotation.lichess_link)

    def test_sincronia_de_volta_nao_repede_a_pagina(self) -> None:
        """O visualizador avisa que a página mudou; responder pedindo de novo seria círculo."""
        antes = len(self.pedidos)
        self.panel.sync_to_page(4)
        self.assertIn("página 5", self.panel.position_var.get())
        self.assertEqual(len(self.pedidos), antes, "sync não deve pedir página de volta")

    def test_pagina_sem_diagrama_nao_mexe_na_galeria(self) -> None:
        self.panel._go(1)
        self.panel.sync_to_page(9)
        self.assertIn("diagrama 2 de 2", self.panel.position_var.get())

    def test_editar_grava_no_arquivo(self) -> None:
        self.panel.move_var.set("7")
        self.panel._commit_move()
        voltou = load_annotations(self.panel.model.pdf_path, directory=Path(self.pasta.name))
        self.assertEqual(voltou.get(0, 0).move_number, 7)

    def test_aplicar_a_todos_avisa_quando_nao_ha_o_que_aplicar(self) -> None:
        self.panel.apply_to_all()
        self.assertTrue(any("Nada a aplicar" in mensagem for mensagem in self.status))

    def test_aplicar_a_todos_propaga_e_grava(self) -> None:
        self.panel.header_vars["Event"].set("Kemeri 1937")
        self.panel._commit_header("Event")
        self.panel.apply_to_all()
        voltou = load_annotations(self.panel.model.pdf_path, directory=Path(self.pasta.name))
        self.assertEqual(voltou.get(4, 0).headers, {"Event": "Kemeri 1937"})

    def test_galeria_vazia_desenha_o_convite_sem_levantar(self) -> None:
        self.panel.model = GalleryModel()
        self.panel.refresh()
        self.assertEqual(self.panel.position_var.get(), "nenhum diagrama varrido")


if __name__ == "__main__":
    unittest.main()
