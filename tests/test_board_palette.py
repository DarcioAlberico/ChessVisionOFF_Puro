"""A paleta de edição: imagens em vez de fonte, e o pincel visível (S-65).

Estes testes precisam de uma janela -- a paleta é widget, e a S-50 pôs de propósito em
`board_model.py` tudo o que não é. O que se confere aqui é só o que exige Tk: que os botões
recebam imagem de verdade, que o pincel ativo apareça, e que a paleta não quebre quando as
imagens não estão no disco.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path

from chess_diagram_ocr.ui.board_render import LIGHT_SQUARE, PieceImages
from chess_diagram_ocr.ui.board_widget import (
    BRUSH_ERASE,
    BRUSH_NONE,
    PALETTE_ICON_SIZE,
    InteractiveBoard,
)

RAIZ = Path(__file__).resolve().parents[1]
IMAGENS = RAIZ / "assets" / "piece_images"


class PaletteTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - máquina sem display
            self.skipTest(f"sem Tk disponível: {exc}")
        self.root.withdraw()
        self.imagens = PieceImages(IMAGENS) if IMAGENS.exists() else None
        self.board = InteractiveBoard(self.root, mode="edit", piece_images=self.imagens)

    def tearDown(self) -> None:
        self.root.destroy()

    def test_as_doze_pecas_usam_imagem_e_nao_fonte(self) -> None:
        """Os símbolos Unicode dependem de a máquina ter uma fonte que os desenhe."""
        if self.imagens is None:
            self.skipTest("assets/piece_images ausente neste checkout")

        com_imagem = [chave for chave, botao in self.board._palette_buttons.items() if botao.cget("image")]
        self.assertEqual(len(com_imagem), 12, f"peças sem imagem: {com_imagem}")
        for botao in self.board._palette_buttons.values():
            if botao.cget("image"):
                self.assertEqual(botao.cget("text"), "", "imagem e texto no mesmo botão")

    def test_apagar_e_sem_pincel_continuam_texto(self) -> None:
        """Não são peças: um ícone para "apagar" seria adivinhação."""
        self.assertEqual(self.board._palette_buttons[BRUSH_ERASE].cget("text"), "Apagar")
        self.assertEqual(self.board._palette_buttons[BRUSH_NONE].cget("text"), "Sem pincel")

    def test_o_pincel_ativo_aparece_na_paleta(self) -> None:
        """Pincel é um **modo**, e um modo invisível é um modo que se esquece de largar."""
        self.board.set_brush("Q")
        self.assertEqual(self.board._brush_var.get(), "Q")

        self.board.set_brush(None)
        self.assertEqual(self.board._brush_var.get(), BRUSH_NONE)

        self.board.set_brush("")
        self.assertEqual(self.board._brush_var.get(), BRUSH_ERASE)

    def test_clicar_de_novo_no_botao_aceso_larga_o_pincel(self) -> None:
        """Sem isto, largar exigia achar o "Sem pincel" do outro lado da fila."""
        self.board.set_brush("R")
        self.assertEqual(self.board.brush, "R")

        self.board._on_palette_click()
        self.assertIsNone(self.board.brush)
        self.assertEqual(self.board._brush_var.get(), BRUSH_NONE)

    def test_clicar_num_botao_diferente_troca_o_pincel(self) -> None:
        self.board.set_brush("R")
        self.board._brush_var.set("n")
        self.board._on_palette_click()
        self.assertEqual(self.board.brush, "n")

    def test_sem_imagens_a_paleta_volta_ao_unicode_em_vez_de_quebrar(self) -> None:
        """Um checkout sem `assets/` não pode impedir a aba de abrir."""
        board = InteractiveBoard(self.root, mode="edit", piece_images=None)
        self.assertEqual(board._palette_buttons["Q"].cget("text"), "♕")
        self.assertFalse(board._palette_buttons["Q"].cget("image"))

    def test_modo_de_jogo_nao_tem_paleta(self) -> None:
        board = InteractiveBoard(self.root, mode="play", piece_images=self.imagens)
        self.assertIsNone(board.palette)

    def test_as_cores_saem_do_tema_e_nao_de_hexadecimal_fixo(self) -> None:
        """Metade dos 30 temas do ttkbootstrap é escura; um `#ffffff` cravado os quebraria."""
        fundo, selecionado, ativo = self.board._palette_colors()
        for cor in (fundo, selecionado, ativo):
            self.assertTrue(self.board.winfo_rgb(cor), f"cor não resolvível pelo Tk: {cor}")
        self.assertNotEqual(fundo, selecionado, "selecionado idêntico ao fundo é seleção invisível")


class PieceIconTests(unittest.TestCase):
    def setUp(self) -> None:
        if not IMAGENS.exists():
            self.skipTest("assets/piece_images ausente neste checkout")
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover
            self.skipTest(f"sem Tk disponível: {exc}")
        self.root.withdraw()
        self.imagens = PieceImages(IMAGENS)

    def tearDown(self) -> None:
        self.root.destroy()

    def test_o_icone_sai_no_tamanho_pedido(self) -> None:
        icone = self.imagens.icon("Q", PALETTE_ICON_SIZE)
        assert icone is not None
        self.assertEqual((icone.width(), icone.height()), (PALETTE_ICON_SIZE, PALETTE_ICON_SIZE))

    def test_o_fundo_entra_no_cache_como_parte_da_chave(self) -> None:
        """Sem isso, pedir a mesma peça com e sem fundo devolveria a primeira das duas."""
        sem = self.imagens.icon("k", 24)
        com = self.imagens.icon("k", 24, background=LIGHT_SQUARE)
        self.assertIsNot(sem, com)
        self.assertIs(com, self.imagens.icon("k", 24, background=LIGHT_SQUARE), "o cache parou de valer")

    def test_peca_desconhecida_devolve_none_em_vez_de_estourar(self) -> None:
        self.assertIsNone(PieceImages(RAIZ / "nao" / "existe").icon("Q", 24))


if __name__ == "__main__":
    unittest.main()
