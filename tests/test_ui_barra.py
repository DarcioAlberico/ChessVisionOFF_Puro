"""A barra que quebra em vez de cortar (S-151).

**O defeito, e por que ele é invisível.** `pack(side=LEFT)` numa linha de altura fixa: quando
falta largura, o Tk simplesmente **não desenha** o que passou da borda. Em 1100 de largura somem
"Exportar PDF → PGN", "Cancelar exportação" e a contagem de diagramas da página — sem aviso, sem
reticências, sem `>>`. Não há erro a que se agarrar: há um usuário que não sabe que existe um
botão.

A propriedade central é a que hoje falha, e ela é uma só: **nenhum item é descartado**, em
nenhuma largura. Os testes daqui a afirmam nos três regimes que a spec nomeia — cabe em uma
linha, cabe em duas, não cabe — e depois na barra montada, com widget de verdade.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import ttk

from tk_root import raiz

from chess_diagram_ocr.ui.barra import ESPACO_ENTRE_ITENS, BarraFluida, arranjo, linhas_necessarias

LARGURAS = [120, 90, 200, 60, 150]
"""Cinco controles de uma barra plausível: dois botões, um rótulo longo, um `Spinbox`, um botão."""

TOTAL = sum(LARGURAS) + ESPACO_ENTRE_ITENS * (len(LARGURAS) - 1)


class ArranjoTests(unittest.TestCase):
    """Os três regimes, sem Tk. É o que faz o critério de aceite caber num `assertEqual`."""

    def _todos(self, linhas: list[list[int]]) -> list[int]:
        return sorted(indice for linha in linhas for indice in linha)

    def test_cabe_em_uma_linha(self) -> None:
        self.assertEqual(arranjo(LARGURAS, TOTAL), [[0, 1, 2, 3, 4]])

    def test_cabe_em_duas_linhas(self) -> None:
        linhas = arranjo(LARGURAS, 430)
        self.assertEqual(len(linhas), 2)
        self.assertEqual(self._todos(linhas), [0, 1, 2, 3, 4])

    def test_nao_cabe_e_ainda_assim_nenhum_item_e_descartado(self) -> None:
        """**A propriedade que hoje falha.** Em qualquer largura, os cinco continuam na tela."""
        for disponivel in (TOTAL, 430, 300, 120, 40, 1, 0):
            with self.subTest(disponivel=disponivel):
                self.assertEqual(self._todos(arranjo(LARGURAS, disponivel)), [0, 1, 2, 3, 4])

    def test_um_item_maior_que_a_barra_fica_sozinho_na_linha(self) -> None:
        """É o único caso sem saída, e a saída escolhida é cortar **um** em vez de esconder três."""
        linhas = arranjo([500, 40], 100)
        self.assertEqual(linhas, [[0], [1]])

    def test_a_ordem_nunca_muda(self) -> None:
        """Reordenar entre larguras faria o mesmo botão mudar de lugar ao arrastar o divisor."""
        for disponivel in (TOTAL, 430, 300, 120):
            with self.subTest(disponivel=disponivel):
                self.assertEqual(self._todos(arranjo(LARGURAS, disponivel)), [0, 1, 2, 3, 4])
                achatado = [indice for linha in arranjo(LARGURAS, disponivel) for indice in linha]
                self.assertEqual(achatado, sorted(achatado))

    def test_o_espaco_entre_itens_conta_como_largura(self) -> None:
        """Ignorá-lo faria a última posição de cada linha estourar a borda por `padx`."""
        self.assertEqual(arranjo([100, 100], 200, espaco=0), [[0, 1]])
        self.assertEqual(arranjo([100, 100], 200, espaco=10), [[0], [1]])

    def test_o_primeiro_item_da_linha_nao_paga_espaco(self) -> None:
        self.assertEqual(arranjo([200], 200, espaco=50), [[0]])

    def test_quanto_mais_estreito_mais_linhas(self) -> None:
        """Monotônica: apertar a barra nunca reduz o número de linhas."""
        anterior = 0
        for disponivel in (TOTAL, 500, 400, 300, 200, 100):
            atual = linhas_necessarias(LARGURAS, disponivel)
            self.assertGreaterEqual(atual, anterior)
            anterior = atual

    def test_barra_vazia_nao_ocupa_linha(self) -> None:
        self.assertEqual(arranjo([], 800), [])
        self.assertEqual(linhas_necessarias([], 800), 0)


class BarraMontadaTests(unittest.TestCase):
    """A barra com widget de verdade: todo controle está mapeado, em toda largura."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.janela.geometry("900x120")
        self.addCleanup(self.janela.destroy)
        self.barra = BarraFluida(self.janela)
        self.barra.pack(fill=tk.X)
        self.controles = [
            self.barra.adicionar(ttk.Button(self.barra, text=texto))
            for texto in (
                "Abrir PDF",
                "Abrir no leitor do sistema",
                "OCR melhor diagrama",
                "OCR todos diagramas",
                "Exportar PDF -> PGN",
                "Cancelar exportação",
            )
        ]
        self.janela.update()

    def _mapeados(self) -> list[ttk.Button]:
        return [controle for controle in self.controles if controle.winfo_ismapped()]

    def test_todo_controle_esta_na_tela_com_folga(self) -> None:
        self.assertEqual(len(self._mapeados()), len(self.controles))
        self.assertEqual(self.barra.linhas, 1)

    def test_todo_controle_continua_na_tela_apertado(self) -> None:
        """O caso fotografado: em 1100 de largura sumiam três botões e a contagem da página."""
        for largura in (700, 500, 360, 240):
            with self.subTest(largura=largura):
                self.janela.geometry(f"{largura}x160")
                self.janela.update()
                self.assertEqual(
                    len(self._mapeados()),
                    len(self.controles),
                    f"em {largura} px sumiram {len(self.controles) - len(self._mapeados())} controles",
                )

    def test_apertar_a_barra_acrescenta_linha(self) -> None:
        self.janela.geometry("900x160")
        self.janela.update()
        largo = self.barra.linhas

        self.janela.geometry("400x160")
        self.janela.update()
        self.assertGreater(self.barra.linhas, largo, "a barra não quebrou: ela está cortando")

    def test_alargar_de_volta_devolve_a_linha_unica(self) -> None:
        """Sem isto a barra encolheria uma vez e nunca mais voltaria a usar a largura toda."""
        self.janela.geometry("400x160")
        self.janela.update()
        self.janela.geometry("900x160")
        self.janela.update()
        self.assertEqual(self.barra.linhas, 1)

    def test_nenhum_controle_ultrapassa_a_borda_direita(self) -> None:
        """Estar mapeado não basta: o Tk mapeia e recorta. O que importa é caber."""
        self.janela.geometry("500x200")
        self.janela.update()
        borda = self.barra.winfo_rootx() + self.barra.winfo_width()
        estourados = [
            controle.cget("text")
            for controle in self.controles
            if controle.winfo_rootx() + controle.winfo_width() > borda + 1
        ]
        self.assertEqual([], estourados, "controles passando da borda da barra")


class PainelDoPdfTests(unittest.TestCase):
    """O critério de aceite: no máximo duas barras acima da página em 1700 de largura."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        from pathlib import Path

        import numpy as np

        from chess_diagram_ocr.ui.pdf_panel import PdfPanel

        self.janela = tk.Toplevel(self.root)
        self.janela.geometry("1000x800")
        self.addCleanup(self.janela.destroy)
        self.painel = PdfPanel(
            self.janela,
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
        )
        self.painel.pack(fill=tk.BOTH, expand=True)
        self.painel.source = Path("livro.pdf")
        self.painel.page_rgb = np.zeros((400, 300, 3), dtype=np.uint8)
        self.painel.page_loaded_for_index = 0
        self.janela.update()

    def test_o_painel_tem_duas_barras_e_nao_cinco(self) -> None:
        """Eram `row`, `nav`, `acoes`, `field_row` e `zoom_row` -- ~200 px, 20% da altura."""
        self.assertTrue(hasattr(self.painel, "barra_livro"))
        self.assertTrue(hasattr(self.painel, "barra_vista"))
        barras = [
            filho
            for filho in self.painel.winfo_children()[0].winfo_children()
            if isinstance(filho, BarraFluida)
        ]
        self.assertEqual(len(barras), 2)

    def test_a_faixa_do_conjunto_de_campo_nasce_sem_altura(self) -> None:
        """Ela continua sendo uma terceira faixa, e é registrada assim -- mas vazia não custa."""
        self.assertLessEqual(self.painel.field_row.winfo_height(), 1)

    def test_as_duas_barras_cabem_numa_linha_em_1700(self) -> None:
        """O painel do PDF fica com ~980 px em 1700 de janela; o critério é medido nele."""
        self.janela.geometry("1000x800")
        self.janela.update()
        self.assertLessEqual(self.painel.barra_livro.linhas, 2)
        self.assertLessEqual(self.painel.barra_vista.linhas, 2)

    def test_nenhum_controle_do_painel_some_no_piso_da_janela(self) -> None:
        """O critério de aceite inteiro: em qualquer largura permitida, nada fica invisível."""
        registrados = [
            self.painel.btn_system_reader,
            self.painel.btn_ocr_best,
            self.painel.btn_ocr_all,
            self.painel.btn_select,
            self.painel.btn_export,
            self.painel.btn_cancel_export,
            self.painel.btn_fit_width,
            self.painel.btn_fit_page,
            self.painel.chk_flip,
            self.painel.chk_boxes,
            self.painel.spin_page,
            self.painel.lbl_zoom,
            # O estado dos diagramas saiu daqui na S-163: ele é do rodapé da janela, e era o
            # item desta barra que saía da tela primeiro.
            self.painel.lbl_pdf,
        ]
        for largura in (1000, 700, 520):
            self.janela.geometry(f"{largura}x800")
            self.janela.update()
            with self.subTest(largura=largura):
                ausentes = [str(controle) for controle in registrados if not controle.winfo_ismapped()]
                self.assertEqual([], ausentes, f"{len(ausentes)} controles fora da tela em {largura} px")


class ItemVisivelTests(unittest.TestCase):
    """O primeiro item da barra estava **coberto**, e ninguém tinha olhado (S-227).

    `pack(in_=)` muda quem arruma o widget e não quem é o pai dele: a moldura de linha continua
    irmã dos itens, e irmão criado depois desenha por cima. A primeira moldura nasce no primeiro
    `adicionar` -- **depois** do item de índice 0 e antes de todos os outros --, então ela cobria
    exatamente um item: o primeiro. Em toda `BarraFluida` do programa.

    Na janela clássica isso são "Abrir PDF" e "Página anterior", invisíveis desde a S-151. O
    defeito apareceu ao fotografar a fita da pele nova, e o conserto é uma linha: `lift`.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def test_nenhum_item_fica_atras_da_moldura_de_linha(self) -> None:
        janela = tk.Toplevel(self.root)
        self.addCleanup(janela.destroy)
        barra_ = BarraFluida(janela)
        barra_.pack(fill=tk.X)
        for nome in ("Primeiro", "Segundo", "Terceiro"):
            barra_.adicionar(ttk.Button(barra_, text=nome))
        self.root.update_idletasks()

        # `winfo_children` devolve em ordem de empilhamento: quem vem depois desenha por cima.
        classes = [filho.winfo_class() for filho in barra_.winfo_children()]
        ultima_moldura = max(i for i, classe in enumerate(classes) if classe == "TFrame")
        primeiro_item = min(i for i, classe in enumerate(classes) if classe == "TButton")
        self.assertGreater(primeiro_item, ultima_moldura, "há item desenhado atrás de uma moldura")


if __name__ == "__main__":
    unittest.main()
