"""A aba Galeria montada de verdade, sem PDF e sem varredura (S-67).

O `gallery_model` cobre a regra; o que sobra para cá é o que só quebra com widget: os campos
lerem a anotação certa ao trocar de diagrama, o pedido de página não voltar em círculo, e o
`Entry` em branco apagar a declaração em vez de gravar string vazia.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.gallery import GalleryAnnotations, load_annotations
from chess_diagram_ocr.gallery_scan import GalleryEntry, GalleryIndex
from chess_diagram_ocr.games_cache import CachedPosition, PositionCache
from chess_diagram_ocr.games_db import DiagramMatch, PositionHit, PositionIndex
from chess_diagram_ocr.ui import gallery_panel
from chess_diagram_ocr.ui.gallery_model import GalleryModel
from chess_diagram_ocr.ui.gallery_panel import GalleryPanel
from chess_diagram_ocr.ui.games_dialog import GamesDialog

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
        cls.root = raiz_do_processo()

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
        self.assertTrue(any("Nada a copiar" in mensagem for mensagem in self.status))

    def test_aplicar_a_todos_propaga_e_grava(self) -> None:
        self.panel.header_vars["Event"].set("Kemeri 1937")
        self.panel._commit_header("Event")
        with mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=True):
            self.panel.apply_to_all()
        voltou = load_annotations(self.panel.model.pdf_path, directory=Path(self.pasta.name))
        self.assertEqual(voltou.get(4, 0).headers, {"Event": "Kemeri 1937"})

    def test_a_copia_pergunta_antes_e_o_cancelar_nao_toca_em_nada(self) -> None:
        """A ação sobrescreve o mesmo campo em centenas de diagramas, e o anterior some."""
        self.panel.header_vars["Event"].set("Kemeri 1937")
        self.panel._commit_header("Event")
        with mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=False) as pergunta:
            self.panel.apply_to_all()
        pergunta.assert_called_once()
        self.assertEqual(self.panel.model.annotations.get(4, 0).headers, {})
        self.assertTrue(any("cancelada" in mensagem for mensagem in self.status))

    def test_a_pergunta_mostra_os_valores_e_quantos_diagramas(self) -> None:
        self.panel.header_vars["Event"].set("Kemeri 1937")
        self.panel._commit_header("Event")
        with mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=False) as pergunta:
            self.panel.apply_to_all()
        texto = str(pergunta.call_args)
        self.assertIn("Kemeri 1937", texto)
        self.assertIn("1 diagrama", texto, "são 2 no índice: o atual não conta")

    def test_desfazer_tira_o_que_a_copia_espalhou(self) -> None:
        self.panel.header_vars["Event"].set("Kemeri 1937")
        self.panel._commit_header("Event")
        with mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=True):
            self.panel.apply_to_all()
        self.assertEqual(self.panel.model.annotations.get(4, 0).headers, {"Event": "Kemeri 1937"})

        self.panel.undo_apply_to_all()
        self.assertEqual(self.panel.model.annotations.get(4, 0).headers, {})
        self.assertTrue(any("desfeita" in mensagem for mensagem in self.status))

    def test_desfazer_nao_apaga_o_que_outro_diagrama_declarou_por_si(self) -> None:
        """Apaga pelo valor: o `Event` que a base preencheu em cada diagrama fica."""
        self.panel.model.annotations.update(4, 0, headers={"Event": "Linares 10th"})
        self.panel.header_vars["Event"].set("Kemeri 1937")
        self.panel._commit_header("Event")
        with mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=True):
            self.panel.apply_to_all()
        self.panel.undo_apply_to_all()
        self.assertEqual(self.panel.model.annotations.get(4, 0).headers, {})

    def test_desfazer_so_existe_depois_de_uma_copia(self) -> None:
        self.assertEqual(str(self.panel.btn_undo["state"]), "disabled")
        self.panel.undo_apply_to_all()
        self.assertFalse(any("desfeita" in mensagem for mensagem in self.status))

    # ------------------------------------------------ limpar os headers (S-94)

    def test_o_botao_de_limpar_nasce_desligado_e_acende_com_header(self) -> None:
        """Um botão que responderia "não há o que limpar" é um botão que mente sobre estar
        disponível."""
        self.assertEqual(str(self.panel.btn_clear["state"]), "disabled")
        self.panel.header_vars["Event"].set("Linares")
        self.panel._commit_header("Event")
        self.panel.refresh(request_page=False)
        self.assertEqual(str(self.panel.btn_clear["state"]), "normal")

    def test_a_pergunta_nomeia_o_que_vai_sair(self) -> None:
        """A lição da S-76: confirmação que não diz o que vai acontecer é obstáculo, não guarda.
        Aqui o que se apaga pode ser meia hora de digitação."""
        self.panel.model.annotations.update(0, 0, headers={"Event": "Linares", "White": "Karpov"})
        self.panel.refresh(request_page=False)
        with mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=False) as pergunta:
            self.panel.clear_headers()
        texto = str(pergunta.call_args)
        self.assertIn("Event = Linares", texto)
        self.assertIn("White = Karpov", texto)
        self.assertIn("não dá para desfazer", texto)
        self.assertEqual(self.panel.model.current_annotation.headers, {"Event": "Linares", "White": "Karpov"})

    def test_confirmar_limpa_a_tela_e_o_arquivo(self) -> None:
        self.panel.model.annotations.update(
            0, 0, move_number=24, headers={"Event": "Linares", "White": "Karpov"}
        )
        self.panel.refresh(request_page=False)
        with mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=True):
            self.panel.clear_headers()
        self.assertEqual(self.panel.header_vars["Event"].get(), "", "o campo da tela também")
        self.assertEqual(self.panel.model.current_annotation.headers, {})
        self.assertEqual(self.panel.model.current_annotation.move_number, 24, "o lance fica")
        self.assertTrue(any("2 header(s) apagado(s)" in mensagem for mensagem in self.status))
        self.assertEqual(load_annotations(self.panel.model.pdf_path, directory=Path(self.pasta.name)).get(0, 0).headers, {})

    def test_limpar_sem_header_avisa_em_vez_de_abrir_caixa(self) -> None:
        with mock.patch.object(gallery_panel.messagebox, "askokcancel") as pergunta:
            self.panel.clear_headers()
        pergunta.assert_not_called()
        self.assertTrue(any("não há o que limpar" in mensagem for mensagem in self.status))

    def test_limpar_nao_toca_no_diagrama_vizinho(self) -> None:
        self.panel.model.annotations.update(0, 0, headers={"Event": "Linares"})
        self.panel.model.annotations.update(4, 0, headers={"Event": "Linares"})
        self.panel.refresh(request_page=False)
        with mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=True):
            self.panel.clear_headers()
        self.assertEqual(self.panel.model.annotations.get(4, 0).headers, {"Event": "Linares"})

    def test_galeria_vazia_desenha_o_convite_sem_levantar(self) -> None:
        self.panel.model = GalleryModel()
        self.panel.refresh()
        self.assertEqual(self.panel.position_var.get(), "nenhum diagrama varrido")

    # ------------------------------------------------------------------ a busca na base (S-72)

    def test_sem_legenda_com_nomes_a_busca_nem_abre_a_base(self) -> None:
        """A base tem 9,7 GB: varrê-la sem ter o que procurar seriam 150 s por nada.

        A base é remendada porque ela não está no repositório: sem isto, o teste passaria
        nesta máquina e falharia em qualquer outra -- que é a falha que a S-37 existe para
        não deixar acontecer de novo.
        """
        with (
            mock.patch("chess_diagram_ocr.ui.gallery_panel.database_paths", return_value=[Path("base.pgn")]),
            mock.patch("chess_diagram_ocr.ui.gallery_panel.scan_by_players") as varredura,
        ):
            self.panel.search_database()
        varredura.assert_not_called()
        self.assertTrue(any("não tem por onde procurar" in m for m in self.status))

    def test_sem_base_no_disco_a_aba_diz_onde_poe_la(self) -> None:
        with (
            mock.patch("chess_diagram_ocr.ui.gallery_panel.database_paths", return_value=[]),
            mock.patch("chess_diagram_ocr.ui.gallery_panel.messagebox.showinfo") as aviso,
        ):
            self.panel.search_database()
        aviso.assert_called_once()
        self.assertIn("pgn_database", str(aviso.call_args))

    def test_livro_nao_varrido_avisa_em_vez_de_procurar(self) -> None:
        self.panel.model = GalleryModel()
        with mock.patch("chess_diagram_ocr.ui.gallery_panel.messagebox.showinfo") as aviso:
            self.panel.search_database()
        aviso.assert_called_once()

    def test_casamento_preenche_e_conta_na_barra_de_status(self) -> None:
        casamento = DiagramMatch(
            page_index=0,
            diagram_index=0,
            move_number=39,
            side_to_move="b",
            headers={"White": "Ljubojevic, Ljubomir", "Event": "IBM"},
            game_label="Ljubojevic x Browne, IBM 1972",
        )
        self.panel._search_done([casamento], pares_achados=1)
        self.assertEqual(self.panel.move_var.get(), "39")
        self.assertEqual(self.panel.side_var.get(), "b")
        self.assertEqual(self.panel.header_vars["White"].get(), "Ljubojevic, Ljubomir")
        self.assertIn("IBM 1972", self.panel.origin_var.get())
        self.assertTrue(any("Nada foi sobrescrito" in m for m in self.status))

    def test_a_procedencia_some_ao_ir_para_um_diagrama_que_a_base_nao_tocou(self) -> None:
        casamento = DiagramMatch(0, 0, 39, "b", {"Event": "IBM"}, game_label="Ljubojevic x Browne")
        self.panel._search_done([casamento], pares_achados=1)
        self.panel._go(1)
        self.assertEqual(self.panel.origin_var.get(), "")

    # ------------------------------------------------------------------ a legenda copiável

    def test_legenda_aparece_inteira(self) -> None:
        """Ela era cortada em 220 caracteres, e o que sobrava do corte era o fim do texto --
        onde costumam estar o segundo jogador e o ano."""
        longa = "Coull - Stanciu\n" + ("comentário do exercício. " * 40)
        self.panel.model.index.entries[0] = GalleryEntry(0, 0, PLACEMENT, caption=longa)
        self.panel.refresh(request_page=False)
        self.assertEqual(self.panel.caption(), longa.strip())
        self.assertGreater(len(self.panel.caption()), 220)

    def test_copiar_legenda_poe_o_texto_na_area_de_transferencia(self) -> None:
        self.panel.model.index.entries[0] = GalleryEntry(0, 0, PLACEMENT, caption="Coull - Stanciu")
        self.panel.refresh(request_page=False)
        self.panel.copy_caption()
        self.assertEqual(self.panel.clipboard_get(), "Coull - Stanciu")

    def test_copiar_legenda_vazia_avisa_em_vez_de_copiar_nada(self) -> None:
        self.panel.copy_caption()
        self.assertTrue(any("não tem legenda" in mensagem for mensagem in self.status))

    def test_a_legenda_nao_aceita_edicao_mas_aceita_copia(self) -> None:
        """Ela é texto de leitura. `state=DISABLED` custaria a seleção; o crivo é por tecla."""
        self.assertEqual(self.panel._reject_caption_edit(_Tecla(keysym="a")), "break")
        self.assertIsNone(self.panel._reject_caption_edit(_Tecla(keysym="c", state=0x0004)))
        self.assertIsNone(self.panel._reject_caption_edit(_Tecla(keysym="Down")))

    def test_trocar_de_diagrama_troca_a_legenda(self) -> None:
        self.panel.model.index.entries[0] = GalleryEntry(0, 0, PLACEMENT, caption="primeira")
        self.panel.model.index.entries[1] = GalleryEntry(4, 0, PLACEMENT, caption="segunda")
        self.panel.refresh(request_page=False)
        self.assertEqual(self.panel.caption(), "primeira")
        self.panel._go(1)
        self.assertEqual(self.panel.caption(), "segunda")


    # ------------------------------------ o botão e a janela de candidatas (S-86)
    # A regra está no `gallery_model`; o que sobra aqui é o que só quebra com widget.

    def _com_cache(self, *, count: int = 3) -> PositionHit:
        partida = PositionHit(
            move_number=24,
            side_to_move="b",
            headers={"White": "Karpov, Anatoly", "Black": "Korchnoi, Viktor", "Date": "1974.09.12"},
        )
        cache = PositionCache()
        cache.positions[PLACEMENT] = CachedPosition(count=count, games=(partida,))
        self.panel.model.position_cache = cache
        self.panel.refresh(request_page=False)
        return partida

    def test_sem_cache_o_botao_fica_desligado(self) -> None:
        """A lista é um caminho a mais, não uma pré-condição para anotar um livro."""
        self.assertEqual(str(self.panel.btn_candidates["state"]), "disabled")

    def test_o_botao_traz_a_contagem_verdadeira(self) -> None:
        """Saber que há 47 candidatas **antes** de clicar muda o gesto de quem está anotando."""
        self._com_cache(count=47)
        self.assertEqual(str(self.panel.btn_candidates["state"]), "normal")
        self.assertIn("(47)", self.panel.btn_candidates["text"])

    def test_a_janela_lista_as_candidatas_e_diz_quantas_ficaram_de_fora(self) -> None:
        self._com_cache(count=147)
        dialogo = GamesDialog(self.host, model=self.panel.model, on_applied=self.status.append)
        try:
            self.assertEqual(len(dialogo.tree.get_children()), 1)
            self.assertIn("1 de 147", dialogo.count_var.get())
        finally:
            dialogo.destroy()

    def test_o_filtro_reduz_a_lista_sem_apagar_as_candidatas(self) -> None:
        self._com_cache()
        dialogo = GamesDialog(self.host, model=self.panel.model, on_applied=self.status.append)
        try:
            dialogo.filter_var.set("korchnoi")
            self.assertEqual(len(dialogo.tree.get_children()), 1)
            dialogo.filter_var.set("tartakower")
            self.assertEqual(len(dialogo.tree.get_children()), 0)
            dialogo.filter_var.set("")
            self.assertEqual(len(dialogo.tree.get_children()), 1, "limpar o filtro traz tudo de volta")
        finally:
            dialogo.destroy()

    def test_aplicar_grava_a_escolha_e_avisa(self) -> None:
        partida = self._com_cache()
        dialogo = GamesDialog(self.host, model=self.panel.model, on_applied=self.status.append)
        try:
            dialogo.apply_selected()
        finally:
            dialogo.destroy()
        anotacao = self.panel.model.current_annotation
        self.assertEqual(anotacao.move_number, 24)
        self.assertEqual(anotacao.chosen_game, partida.key)
        self.assertTrue(any("Karpov" in mensagem for mensagem in self.status))

    def test_a_janela_avisa_quando_nao_ha_candidata(self) -> None:
        with mock.patch.object(gallery_panel.messagebox, "showinfo") as aviso:
            self.panel.open_games_dialog()
        self.assertTrue(aviso.called, "silêncio faria o botão parecer quebrado")

    # ------------------------------------------------ a busca pela posição (S-92)
    # A varredura é do `games_db` e o preenchimento é do `gallery_model`. O que só quebra com
    # widget é o que está aqui: não abrir 10,3 GB à toa, dizer o preço antes, e não gravar
    # meia passada no cache.

    def _base_no_disco(self) -> mock._patch:
        return mock.patch.object(gallery_panel, "database_paths", return_value=[Path("base.pgn")])

    def test_sem_base_no_disco_a_busca_por_posicao_diz_onde_poe_la(self) -> None:
        with (
            mock.patch.object(gallery_panel, "database_paths", return_value=[]),
            mock.patch.object(gallery_panel.messagebox, "showinfo") as aviso,
        ):
            self.panel.search_by_position()
        aviso.assert_called_once()
        self.assertIn("pgn_database", str(aviso.call_args))
        self.assertIn("mais de um", str(aviso.call_args), "a pasta aceita várias bases (S-93)")

    def test_as_duas_bases_da_pasta_vao_para_a_varredura(self) -> None:
        """O que a S-93 destrava na tela: a segunda gigabase deixa de ser invisível."""
        bases = [Path("a.pgn"), Path("b.pgn")]
        with (
            mock.patch.object(gallery_panel, "database_paths", return_value=bases),
            mock.patch.object(gallery_panel, "load_cache", return_value=PositionCache()),
            mock.patch.object(gallery_panel, "scan_by_positions", return_value=PositionIndex()) as varredura,
            mock.patch.object(gallery_panel, "save_cache"),
            mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=True) as pergunta,
            # A thread de verdade **não** pode subir aqui: fora do laço do Tk -- e num teste ele
            # não roda -- o `after` da volta levanta, e a exceção de uma thread é relatada em
            # qualquer teste que estiver correndo na hora. Foi assim que a suíte oscilou.
            mock.patch.object(gallery_panel.threading, "Thread") as thread,
        ):
            self.panel.search_by_position()
            # O mesmo trabalho, na thread do teste: os argumentos que iriam para a thread.
            self.panel._positions_worker(*thread.call_args.kwargs["args"])
        self.assertIn("2 arquivo(s)", str(pergunta.call_args))
        self.assertEqual(varredura.call_args[0][0], bases, "as duas, e não a maior")

    def test_livro_nao_varrido_nao_abre_a_base(self) -> None:
        """Sem diagrama varrido não há posição para procurar, e a base tem 10,3 GB."""
        self.panel.model = GalleryModel()
        with (
            self._base_no_disco(),
            mock.patch.object(gallery_panel, "scan_by_positions") as varredura,
            mock.patch.object(gallery_panel.messagebox, "showinfo") as aviso,
        ):
            self.panel.search_by_position()
        varredura.assert_not_called()
        aviso.assert_called_once()

    def test_posicao_ja_perguntada_responde_do_cache_sem_abrir_a_base(self) -> None:
        """O caso de todo livro que o `cvoff-games` já varreu: nada a perguntar, resposta na hora.

        É o que impede a meia hora de ser paga duas vezes -- e o cache é por **posição**, então
        um segundo livro que mostre os mesmos clássicos também não paga.
        """
        cache = PositionCache()
        cache.positions[PLACEMENT] = CachedPosition(
            count=1, games=(PositionHit(move_number=24, side_to_move="b", headers={"Event": "Linares"}),)
        )
        with (
            self._base_no_disco(),
            mock.patch.object(gallery_panel, "load_cache", return_value=cache),
            mock.patch.object(gallery_panel, "scan_by_positions") as varredura,
            mock.patch.object(gallery_panel.messagebox, "askokcancel") as pergunta,
        ):
            self.panel.search_by_position()
        varredura.assert_not_called()
        pergunta.assert_not_called()
        self.assertEqual(self.panel.move_var.get(), "24")
        self.assertIn("(1)", self.panel.btn_candidates["text"], "a lista de candidatas acende no mesmo gesto")

    def test_a_caixa_diz_o_preco_e_recusar_nao_varre(self) -> None:
        """Meia hora atrás de um botão que não avisa é uma janela travada."""
        with (
            self._base_no_disco(),
            mock.patch.object(gallery_panel, "load_cache", return_value=PositionCache()),
            mock.patch.object(gallery_panel, "scan_by_positions") as varredura,
            mock.patch.object(gallery_panel.messagebox, "askokcancel", return_value=False) as pergunta,
        ):
            self.panel.search_by_position()
        varredura.assert_not_called()
        self.assertIn("meia hora", str(pergunta.call_args))

    def test_a_resposta_da_base_vira_cache_gravado(self) -> None:
        cache = PositionCache()
        indice = PositionIndex(
            hits={PLACEMENT: [PositionHit(move_number=24, side_to_move="b")]}, counts={PLACEMENT: 1}
        )
        with (
            mock.patch.object(gallery_panel, "scan_by_positions", return_value=indice),
            mock.patch.object(gallery_panel, "save_cache") as gravar,
        ):
            self.panel._positions_worker(Path("base.pgn"), cache, {PLACEMENT}, {PLACEMENT})
        gravar.assert_called_once()
        self.assertEqual(cache.positions[PLACEMENT].count, 1)

    def test_a_posicao_sem_resposta_fica_registrada_como_perguntada(self) -> None:
        """Senão ela volta ao alvo de toda varredura futura -- e são a maioria (S-84)."""
        cache = PositionCache()
        with (
            mock.patch.object(gallery_panel, "scan_by_positions", return_value=PositionIndex()),
            mock.patch.object(gallery_panel, "save_cache"),
        ):
            self.panel._positions_worker(Path("base.pgn"), cache, {PLACEMENT}, {PLACEMENT})
        self.assertEqual(cache.positions[PLACEMENT].count, 0, "perguntada, e a base não conhece")

    def test_cancelar_no_meio_nao_grava_nada(self) -> None:
        """Meia base lida dá contagens que não valem -- ver `scan_by_positions`."""
        cache = PositionCache()

        def varrer(*_args: object, **kwargs: object) -> PositionIndex:
            kwargs["cancel"].set()  # type: ignore[union-attr]
            return PositionIndex()

        with (
            mock.patch.object(gallery_panel, "scan_by_positions", side_effect=varrer),
            mock.patch.object(gallery_panel, "save_cache") as gravar,
        ):
            self.panel._positions_worker(Path("base.pgn"), cache, {PLACEMENT}, {PLACEMENT})
        gravar.assert_not_called()
        self.assertEqual(cache.positions, {}, "nem como perguntada: a pergunta não chegou a ser feita")

    def test_cancelar_devolve_os_botoes_e_diz_que_nada_foi_gravado(self) -> None:
        self.panel._busy(True)
        self.assertEqual(str(self.panel.btn_positions["state"]), "disabled")
        self.panel._positions_cancelled()
        self.assertEqual(str(self.panel.btn_positions["state"]), "normal")
        self.assertEqual(str(self.panel.btn_games["state"]), "normal")
        self.assertTrue(any("nada foi gravado" in mensagem for mensagem in self.status))

    def test_o_que_a_base_leu_aparece_na_barra_de_status(self) -> None:
        cache = PositionCache()
        cache.positions[PLACEMENT] = CachedPosition(
            count=1, games=(PositionHit(move_number=24, side_to_move="b", headers={"Event": "Linares"}),)
        )
        self.panel._positions_done(cache, {PLACEMENT}, games_read=10_547_416)
        self.assertEqual(self.panel.header_vars["Event"].get(), "Linares")
        self.assertTrue(any("10.5 M partidas lidas" in mensagem for mensagem in self.status))
        self.assertTrue(any("Nada foi sobrescrito" in mensagem for mensagem in self.status))


@dataclass
class _Tecla:
    """O bastante de um `<Key>` para o crivo. O Tk não deixa construir um `tk.Event` útil."""

    keysym: str
    state: int = 0


if __name__ == "__main__":
    unittest.main()
