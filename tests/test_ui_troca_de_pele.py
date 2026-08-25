"""Trocar de pele sem fechar a janela, e sem perder o lugar (S-222).

Escolher aparência reiniciando o programa é escolher no escuro: quem compara três peles reabre
três vezes e compara de memória. E o custo maior é o outro -- reabrir perde o **contexto de
trabalho**, e quem está no meio de uma correção não troca de pele para ver.

**A troca remonta o cromo e não toca o conteúdo**, e a maior parte destes testes afirma a segunda
metade dessa frase. O que se destrói e refaz são as barras, a linha de conjunto de campo e a barra
de menus; o `PanedWindow`, os painéis, a página renderizada e o `DiagramEditorModel` continuam de
pé -- e é por isso que nada precisa ser salvo e restaurado.

**Hoje só existe a pele clássica**, então a troca que o programa faz é nenhuma. A máquina é
exercida aqui, e quem a liga de verdade é a S-223, quando registrar a segunda.
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

import numpy as np
from tk_root import raiz

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app_tkinter  # noqa: E402 - depende do `sys.path` ajustado acima
from chess_diagram_ocr.ui import abas, comandos, fila, fita, pele, theme  # noqa: E402
from chess_diagram_ocr.ui.pdf_panel import PdfPanel  # noqa: E402
from chess_diagram_ocr.ui.state import AppState  # noqa: E402


class RemontagemDoPainelTests(unittest.TestCase):
    """As barras destruídas e refeitas, com um PDF na tela e o trabalho em curso."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.host = tk.Frame(self.root)
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
        self.addCleanup(self.host.destroy)
        # Um livro na tela sem abrir arquivo nenhum, como faz o `test_pdf_panel`.
        self.panel.source = Path("livro.pdf")
        self.panel.name = "livro.pdf"
        self.panel.page_count = 12
        self.panel.page_rgb = np.zeros((400, 300, 3), dtype=np.uint8)
        self.panel.page_loaded_for_index = 3
        self.panel.page_index_var.set(3)
        self.panel.zoom_var.set(1.25)
        self.panel.refresh_view()

    def test_a_troca_preserva_a_pagina_e_o_zoom(self) -> None:
        pixels = self.panel.page_rgb
        self.panel.remontar_cromo()

        self.assertEqual(3, self.panel.page_index)
        self.assertEqual(1.25, self.panel.zoom_var.get())
        self.assertEqual("125%", str(self.panel.lbl_zoom.cget("text")))
        self.assertIn("livro.pdf", str(self.panel.lbl_pdf.cget("text")))
        self.assertEqual(11, int(self.panel.spin_page.cget("to")), "o teto do Spinbox voltou zerado")
        self.assertIs(pixels, self.panel.page_rgb, "a página foi re-renderizada")

    def test_a_troca_nao_re_renderiza_a_pagina(self) -> None:
        """O critério fala do `PhotoImage`, e é ele que se olha: reaproveitado, não refeito."""
        renderizadas: list[int] = []
        self.panel.render_current_page = lambda *a, **k: renderizadas.append(1)  # type: ignore[method-assign]
        foto = self.panel._page_photo

        self.panel.remontar_cromo()

        self.assertEqual([], renderizadas, "a remontagem mandou renderizar de novo")
        self.assertIs(foto, self.panel._page_photo, "o PhotoImage da página foi refeito")

    def test_a_troca_nao_duplica_ligacao_de_tecla(self) -> None:
        """**Depois de N trocas, uma ligação por sequência -- não N.**

        `_bind_wheel` usa `bind_all` com `add="+"`, que acumula. A resposta certa não é religar
        com cuidado: é **não religar**, porque a roda é do painel e o painel sobrevive à troca.
        """
        antes = str(self.root.bind_all("<MouseWheel>"))
        for _ in range(3):
            self.panel.remontar_cromo()
        self.assertEqual(antes, str(self.root.bind_all("<MouseWheel>")))

    def test_a_troca_preserva_o_estado_dos_botoes(self) -> None:
        """Uma troca no meio de uma exportação devolveria os seis ao estado de janela nova."""
        self.panel.set_ocr_controls_enabled(False)
        self.panel.set_export_controls_enabled(False)

        self.panel.remontar_cromo()

        self.assertEqual("disabled", str(self.panel.btn_ocr_all.cget("state")))
        self.assertEqual("disabled", str(self.panel.btn_export.cget("state")))
        self.assertEqual("normal", str(self.panel.btn_cancel_export.cget("state")))

    def test_a_troca_preserva_o_rotulo_de_quem_estava_ligado(self) -> None:
        """O `selecionar_area` troca o próprio texto quando liga, e o texto é estado."""
        self.panel.toggle_area_selection()
        self.assertTrue(self.panel._select_mode, "a seleção não ligou; o teste não mede nada")

        self.panel.remontar_cromo()

        self.assertEqual(
            comandos.rotulo_alternado("selecionar_area"),
            str(self.panel.btn_select.cget("text")),
        )

    def test_as_barras_voltam_acima_da_pagina(self) -> None:
        """Sem o `before=`, as barras refeitas nasceriam **abaixo** do canvas: o `pack` empilha
        quem chega por último."""
        self.panel.remontar_cromo()
        # `pack_slaves` e não `winfo_children`: o primeiro é a ordem de empilhamento,
        # o segundo é a de criação -- e a remontagem muda justamente a segunda.
        irmaos = [str(filho) for filho in self.panel._box.pack_slaves()]
        self.assertLess(irmaos.index(str(self.panel.barra_livro)), irmaos.index(str(self.panel.field_row)))
        self.assertLess(irmaos.index(str(self.panel.barra_vista)), irmaos.index(str(self.panel.field_row)))

    def test_na_pele_foco_as_barras_saem_da_tela_e_os_controles_continuam(self) -> None:
        """**Criados e não empacotados** (S-223), e a diferença é o contrato do painel.

        `set_ocr_controls_enabled`, `_open_pdf` e `update_zoom_label` escrevem nesses widgets o
        tempo todo. Fazê-los existir mantém o painel com um caminho só; o que a pele decide é o
        que aparece na tela. Os 21 controles continuam alcançáveis pelo menu, que é a regra 2.
        """
        self.panel.remontar_cromo(pele.CROMO_FOCO)

        empilhados = [str(filho) for filho in self.panel._box.pack_slaves()]
        self.assertNotIn(str(self.panel.barra_livro), empilhados)
        self.assertNotIn(str(self.panel.barra_vista), empilhados)

        # E o painel continua sabendo fazer tudo o que sabia.
        self.panel.set_ocr_controls_enabled(False)
        self.assertEqual("disabled", str(self.panel.btn_ocr_all.cget("state")))
        self.panel.update_zoom_label()
        self.assertEqual("125%", str(self.panel.lbl_zoom.cget("text")))

    def test_voltar_para_a_classica_devolve_as_barras(self) -> None:
        self.panel.remontar_cromo(pele.CROMO_FOCO)
        self.panel.remontar_cromo(pele.CROMO_CLASSICO)
        empilhados = [str(filho) for filho in self.panel._box.pack_slaves()]
        self.assertIn(str(self.panel.barra_livro), empilhados)
        self.assertLess(empilhados.index(str(self.panel.barra_livro)), empilhados.index(str(self.panel.field_row)))

    def test_a_linha_de_campo_e_refeita_e_nao_duplicada(self) -> None:
        montagens: list[int] = []

        def refazer(pai: tk.Widget) -> None:
            montagens.append(1)
            tk.Label(pai, text="conjunto de campo").pack()

        self.panel.remontar_cromo(refazer_linha_de_campo=refazer)
        self.panel.remontar_cromo(refazer_linha_de_campo=refazer)

        self.assertEqual([1, 1], montagens)
        self.assertEqual(1, len(self.panel.field_row.winfo_children()), "a linha de campo acumulou")


class _PainelDeCromoFalso:
    """Só o que `remontar_cromo` da janela pede do painel de PDF."""

    def __init__(self) -> None:
        self.remontagens: list[object] = []
        self.field_row = object()

    def remontar_cromo(self, montagem: str = "", *, refazer_linha_de_campo: object = None) -> None:
        self.remontagens.append((montagem, refazer_linha_de_campo))


class _PainelDeConteudoFalso:
    """O painel de resultado. Qualquer método chamado nele é a troca passando do cromo."""

    def __init__(self) -> None:
        self.fen = "8/8/8/8/8/8/8/K6k w - - 0 1"
        self.diagrama = 4

    def __getattr__(self, nome: str) -> object:  # pragma: no cover - só dispara se falhar
        raise AssertionError(f"a troca de pele tocou o conteúdo: result_panel.{nome}")


def _janela():  # noqa: ANN202
    """A janela reduzida aos métodos da troca, com os métodos **reais**.

    Mesmo recurso do `test_box_drop._janela`: montar o `ChessOcrTkApp` inteiro exigiria
    checkpoint e PDF, e o que se testa aqui é a costura entre escolher e remontar.
    """
    tipo = type(
        "JanelaMinima",
        (),
        {
            "_escolher_pele": app_tkinter.ChessOcrTkApp._escolher_pele,
            "_escolher_densidade": app_tkinter.ChessOcrTkApp._escolher_densidade,
            "_densidade": app_tkinter.ChessOcrTkApp._densidade,
            "remontar_cromo": app_tkinter.ChessOcrTkApp.remontar_cromo,
            "_build_menu": lambda self: self.menus.append(1),
            "_build_field_row": lambda self, _pai: None,
            "_save_app_state": lambda self: self.gravacoes.append(self.state.skin),
            "_comandos": lambda self: {
                acao: (lambda: None) for acao in (*fila.acoes_da_fila(), *fita.acoes_da_fita())
            },
        },
    )
    janela = tipo()
    janela.state = AppState()
    janela.skin_var = tk.StringVar(value=pele.CLASSICA)
    janela.densidade_var = tk.StringVar(value=pele.CONFORTAVEL)
    janela.pdf_panel = _PainelDeCromoFalso()
    janela.result_panel = _PainelDeConteudoFalso()
    janela.root = raiz()
    janela.fila_de_acoes = tk.Frame(janela.root)
    # Uma barra de abas de verdade, com as sete declaradas: a S-226 cobra que nenhuma pele as
    # esconda, e um dublê que não as tivesse não mediria isso.
    janela.left_tabs = ttk.Notebook(janela.root)
    for nome in abas.ABAS:
        janela.left_tabs.add(ttk.Frame(janela.left_tabs), text=nome)
    janela.menus = []
    janela.gravacoes = []
    return janela


class TrocaNaJanelaTests(unittest.TestCase):
    """A orquestração: o que a escolha dispara, e o que ela não alcança."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = _janela()

    def test_sem_escolha_cada_pele_traz_a_densidade_que_ela_sugere(self) -> None:
        """A sugestão é da pele (S-232), e ela vale enquanto ninguém decidiu nada."""
        for registro in pele.PELES:
            self.janela.state.skin = registro.nome
            self.janela.remontar_cromo()
            with self.subTest(pele=registro.nome):
                self.assertEqual(registro.densidade, self.janela.densidade_var.get())

    def test_a_escolha_de_densidade_sobrevive_a_troca_de_pele(self) -> None:
        """**É o critério de aceite que uma implementação apressada troca por "a fita é compacta".**

        Quem escolheu confortável continua confortável na fita, que sugere o contrário -- porque o
        que está guardado é a decisão da pessoa, e não o efeito dela.
        """
        self.janela.densidade_var.set(pele.CONFORTAVEL)
        self.janela._escolher_densidade()
        self.assertEqual(pele.CONFORTAVEL, self.janela.state.densidade)

        self.janela.state.skin = pele.FITA
        self.janela.remontar_cromo()
        self.assertEqual(pele.CONFORTAVEL, self.janela._densidade())
        self.assertEqual(pele.CONFORTAVEL, self.janela.densidade_var.get())

    def test_escolher_a_densidade_que_a_pele_sugeria_ainda_a_torna_explicita(self) -> None:
        """Escolher "compacta" na fita parece um clique sem efeito, e não é: a partir dele a
        densidade é decisão da pessoa, e deixa de mudar quando a pele muda."""
        self.janela.state.skin = pele.FITA
        self.janela.remontar_cromo()
        self.assertEqual("", self.janela.state.densidade, "a remontagem não pode gravar escolha")

        self.janela.densidade_var.set(pele.COMPACTA)
        self.janela._escolher_densidade()
        self.assertEqual(pele.COMPACTA, self.janela.state.densidade)

        self.janela.state.skin = pele.CLASSICA
        self.janela.remontar_cromo()
        self.assertEqual(pele.COMPACTA, self.janela._densidade())

    def test_a_troca_grava_a_escolha_na_hora(self) -> None:
        """E não só no fechamento: quem experimenta três peles e desliga na energia teria
        experimentado nada."""
        self.janela._escolher_pele()
        self.assertEqual([pele.CLASSICA], self.janela.gravacoes)
        self.assertEqual(pele.CLASSICA, self.janela.state.skin)

    def test_escolher_a_pele_que_ja_esta_valendo_nao_remonta(self) -> None:
        """A primeira escolha da vida do programa é a clássica sobre a clássica -- `skin` nasce
        vazio e resolve para ela. Remontar aí seria um piscar sem motivo."""
        self.janela._escolher_pele()
        self.assertEqual([], self.janela.pdf_panel.remontagens)
        self.assertEqual([], self.janela.menus)

    def test_pele_invalida_no_menu_cai_na_classica_e_a_variavel_acompanha(self) -> None:
        """A variável é corrigida, e não só o estado: um `radiobutton` marcado em algo que não
        existe é a interface dizendo que a escolha pegou."""
        self.janela.skin_var.set("mosaico")
        with self.assertLogs(pele.logger, level="WARNING"):
            self.janela._escolher_pele()
        self.assertEqual(pele.CLASSICA, self.janela.skin_var.get())
        self.assertEqual(pele.CLASSICA, self.janela.state.skin)

    def test_a_troca_refaz_o_menu_e_a_linha_de_campo(self) -> None:
        self.janela.remontar_cromo()
        self.assertEqual([1], self.janela.menus)
        self.assertEqual(1, len(self.janela.pdf_panel.remontagens))
        montagem, refazer = self.janela.pdf_panel.remontagens[0]
        self.assertEqual(pele.CROMO_CLASSICO, montagem)
        self.assertIsNotNone(refazer, "a linha de campo ficaria vazia")

    def test_a_troca_esvazia_o_cache_de_icones(self) -> None:
        """O cache é por `(nome, tamanho, cor)`, e a cor do cromo é o que a pele muda."""
        from chess_diagram_ocr.ui import icones

        icones.icone("salvar", 24, "#101010")
        self.assertEqual(1, icones.cache_de_icones())

        self.janela.remontar_cromo()

        self.assertEqual(0, icones.cache_de_icones())

    def test_a_troca_reaplica_o_tema_com_o_cromo_da_pele(self) -> None:
        """`theme.registrar_estilos` previu isto por escrito: estilo declarado antes do tema é
        sobrescrito por ele, e trocar em execução precisa reaplicá-lo. Desde a S-224 quem faz
        isso é `apply_theme`, porque a pele também escolhe o tema e manda repintar."""
        from unittest.mock import patch

        with patch.object(app_tkinter.theme, "apply_theme") as reaplicou:
            self.janela.remontar_cromo()
        reaplicou.assert_called_once_with(
            self.janela.root, cromo_escuro=False, densidade=pele.CONFORTAVEL
        )

    def test_as_sete_abas_existem_em_toda_pele(self) -> None:
        """A regra 2 no lugar em que a tentação de seguir a imagem é maior: a Imagem 1 não tem
        faixa de abas, e adotá-la ao pé da letra apagaria sete painéis."""
        for registro in pele.PELES:
            self.janela.state.skin = registro.nome
            self.janela.remontar_cromo()
            with self.subTest(pele=registro.nome):
                rotulos = [
                    abas.nome_base(str(self.janela.left_tabs.tab(i, "text")))
                    for i in range(int(self.janela.left_tabs.index("end")))
                ]
                self.assertEqual(list(abas.ABAS), rotulos)

    def test_a_faixa_de_abas_muda_de_peso_e_nao_de_conteudo(self) -> None:
        """O que a pele "Foco" muda na barra é o estilo; as abas são as mesmas sete."""
        self.janela.state.skin = pele.FOCO
        self.janela.remontar_cromo()
        self.assertEqual(theme.ESTILO_DE_ABAS_DISCRETO, str(self.janela.left_tabs.cget("style")))

        self.janela.state.skin = pele.CLASSICA
        self.janela.remontar_cromo()
        self.assertEqual("", str(self.janela.left_tabs.cget("style")), "a clássica ficou com o estilo da Foco")

    def test_a_troca_preserva_o_diagrama_e_a_fen(self) -> None:
        """O painel de resultado não é alcançado pela remontagem -- é o item inteiro em uma
        frase. O falso levanta em qualquer atributo que não seja o que ele guarda."""
        conteudo = self.janela.result_panel
        fen = conteudo.fen

        self.janela.remontar_cromo()

        self.assertIs(conteudo, self.janela.result_panel)
        self.assertEqual(fen, self.janela.result_panel.fen)
        self.assertEqual(4, self.janela.result_panel.diagrama)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
