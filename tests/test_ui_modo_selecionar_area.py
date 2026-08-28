"""O modo que ninguém via ligado: "Selecionar área" fora da pele clássica (S-396).

`selecionar_area` é um **modo**: o primeiro clique liga o arrasto sobre a folha, o segundo desliga.
A pele clássica dizia isso desde a S-222 -- o botão da barra do painel troca para "Cancelar
seleção". As outras duas peles desenham o mesmo comando noutro lugar (a fita, na aba Início) e
**criam os botões da barra sem empacotá-los**, então o texto trocado ficava numa barra que a pele
não mostra: ligar e desligar tinham exatamente o mesmo aspecto, e o único jeito de saber em que
estado se estava era arrastar o mouse e ver o que acontecia.

O que estes testes cobram é o canal que fecha isso, e não um widget: quem vira o modo **avisa**
(`comandos.alternou`), quem o desenha **segue** (`comandos.ao_alternar`).
"""

from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path

import numpy as np
from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.ui import comandos, fila, fita
from chess_diagram_ocr.ui.pdf_panel import PdfPanel

LIGADO = comandos.rotulo_alternado("selecionar_area")
DESLIGADO = comandos.rotulo_de_botao("selecionar_area")


class _SemSeguidoresDeAntes(unittest.TestCase):
    """Base que devolve o catálogo como o encontrou.

    `_SEGUIDORES` é estado de módulo, e um teste que registra um espião nele o deixaria vivo para
    o vizinho. Mexer no privado aqui é de propósito: a alternativa seria uma função pública que só
    os testes chamam, e o catálogo não ganha API para isso.
    """

    def setUp(self) -> None:
        guardado = {acao: list(quem) for acao, quem in comandos._SEGUIDORES.items()}
        self.addCleanup(self._repor, guardado)

    @staticmethod
    def _repor(guardado: dict[str, list[object]]) -> None:
        comandos._SEGUIDORES.clear()
        comandos._SEGUIDORES.update(guardado)  # type: ignore[arg-type]


class CanalDeAlternanciaTests(_SemSeguidoresDeAntes):
    """O canal em si, sem janela: é o catálogo que o guarda, e ele não importa `tkinter`."""

    def test_o_seguidor_recebe_os_dois_textos(self) -> None:
        vistos: list[str] = []
        comandos.ao_alternar("selecionar_area", vistos.append)

        comandos.alternou("selecionar_area", ligado=True)
        comandos.alternou("selecionar_area", ligado=False)

        self.assertEqual([LIGADO, DESLIGADO], vistos)
        self.assertNotEqual(LIGADO, DESLIGADO)

    def test_recebe_texto_e_nao_widget(self) -> None:
        """A assinatura é `Callable[[str], object]` porque `comandos` é o catálogo.

        Se ela recebesse o botão, este módulo importaria `tkinter` -- e é justamente por não
        importar que ele pode ser lido pela varredura de rótulos da S-324 e pelo menu, que roda
        antes de qualquer janela existir.
        """
        recebido: list[object] = []
        comandos.ao_alternar("selecionar_area", recebido.append)
        comandos.alternou("selecionar_area", ligado=True)
        self.assertEqual([LIGADO], recebido)

    def test_quem_morreu_sai_da_lista_sem_derrubar_os_outros(self) -> None:
        """Um botão destruído entre o registro e a troca é a janela de antes -- e a pele é
        remontada a cada troca de aparência, então isso acontece **sempre**, não por acidente."""
        vivo: list[str] = []

        def morto(_texto: str) -> None:
            raise tk.TclError('invalid command name ".!button"')

        comandos.ao_alternar("selecionar_area", morto)
        comandos.ao_alternar("selecionar_area", vivo.append)

        comandos.alternou("selecionar_area", ligado=True)
        comandos.alternou("selecionar_area", ligado=False)

        self.assertEqual([LIGADO, DESLIGADO], vivo)
        self.assertEqual([vivo.append], comandos._SEGUIDORES["selecionar_area"])

    def test_avisar_sem_ninguem_ouvindo_nao_levanta(self) -> None:
        """`disable_area_selection` roda na montagem da janela, antes de qualquer pele existir."""
        comandos.alternou("mostrar_diagrama", ligado=True)


class AFitaMostraOModoTests(_SemSeguidoresDeAntes):
    """A fita é o lugar apontado pelo relatório, e o único que desenha um comando que alterna."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        super().setUp()
        self.janela = tk.Frame(self.root)
        self.addCleanup(self.janela.destroy)
        amarrados = {acao: (lambda: None) for acao in fita.acoes_da_fita()}
        self.fita = fita.montar(self.janela, amarrados, modo=fita.PLENO)

    def test_a_fita_desenha_selecionar_area(self) -> None:
        """Se um dia ela deixar de desenhá-lo, o teste seguinte vira vácuo e este acusa."""
        self.assertIn("selecionar_area", fita.acoes_da_fita())

    def test_o_botao_da_fita_troca_de_texto(self) -> None:
        botao = self.fita.botao("selecionar_area")
        self.assertEqual(DESLIGADO, str(botao.cget("text")).replace("\n", " "))

        comandos.alternou("selecionar_area", ligado=True)
        self.assertEqual(LIGADO, str(botao.cget("text")).replace("\n", " "))

        comandos.alternou("selecionar_area", ligado=False)
        self.assertEqual(DESLIGADO, str(botao.cget("text")).replace("\n", " "))

    def test_a_fita_remontada_nao_carrega_a_de_antes(self) -> None:
        """Trocar de densidade destrói a fita e monta outra. Sem a limpeza do `alternou`, cada
        troca somaria um seguidor morto -- e o primeiro clique depois de N trocas percorreria N."""
        velha = self.fita.botao("selecionar_area")
        self.fita.destroy()
        self.fita = fita.montar(self.janela, {acao: (lambda: None) for acao in fita.acoes_da_fita()}, modo=fita.PLENO)

        comandos.alternou("selecionar_area", ligado=True)

        self.assertEqual(LIGADO, str(self.fita.botao("selecionar_area").cget("text")).replace("\n", " "))
        self.assertEqual(1, len(comandos._SEGUIDORES["selecionar_area"]))
        self.assertFalse(velha.winfo_exists())


class APilulaDaFilaTests(_SemSeguidoresDeAntes):
    """A pele "Foco" não desenha nenhum comando que alterne **hoje**.

    A pílula se registra assim mesmo porque a regra é da pele e não do comando: no dia em que
    `destaque=True` e `rotulo_alternado` se cruzarem numa linha do catálogo, a Foco mostra o modo
    sem que ninguém precise lembrar-se disto aqui. É por isso que o teste chama `_pilula` direto,
    em vez de montar a fila: montar a fila hoje não desenharia nada que alternasse.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def test_nenhum_comando_da_fila_alterna_hoje(self) -> None:
        alternam = {registro.acao for registro in comandos.CATALOGO if registro.rotulo_alternado}
        self.assertFalse(alternam & set(fila.acoes_da_fila()))

    def test_a_pilula_de_um_comando_que_alterna_segue(self) -> None:
        janela = tk.Frame(self.root)
        self.addCleanup(janela.destroy)
        pilula = fila._pilula(janela, comandos.comando("selecionar_area"), lambda: None, 16)

        comandos.alternou("selecionar_area", ligado=True)
        self.assertEqual(LIGADO, str(pilula.cget("text")))

    def test_a_pilula_de_quem_nao_alterna_nao_se_registra(self) -> None:
        janela = tk.Frame(self.root)
        self.addCleanup(janela.destroy)
        fila._pilula(janela, comandos.comando("salvar"), lambda: None, 16)
        self.assertEqual([], comandos._SEGUIDORES.get("salvar", []))


class OPainelAvisaTests(_SemSeguidoresDeAntes):
    """A ponta de cá: quem liga o modo é o painel, e é ele que precisa dizer.

    O botão da própria barra continua sendo repintado no lugar de sempre -- ele existe em todas as
    peles, empacotado ou não, e `_resincronizar_barras` o repõe depois de uma troca de aparência.
    O aviso é o que faltava para quem desenha o mesmo comando noutro canto da janela.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        super().setUp()
        self.host = tk.Frame(self.root)
        self.addCleanup(self.host.destroy)
        self.painel = PdfPanel(
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
        # Uma página na tela sem abrir arquivo nenhum: sem PDF, `toggle_area_selection` recusa
        # ligar e escreve a pré-condição da S-164 no rodapé, e não haveria modo nenhum para ver.
        self.painel.source = Path("livro.pdf")
        self.painel.page_rgb = np.zeros((400, 300, 3), dtype=np.uint8)
        self.painel.page_loaded_for_index = 0
        self.painel.zoom_var.set(1.0)
        self.painel.refresh_view()
        self.vistos: list[str] = []
        comandos.ao_alternar("selecionar_area", self.vistos.append)

    def test_ligar_e_desligar_avisam(self) -> None:
        self.painel.toggle_area_selection()
        self.assertEqual([LIGADO], self.vistos)
        self.assertTrue(self.painel._select_mode)

        self.painel.toggle_area_selection()
        self.assertEqual([LIGADO, DESLIGADO], self.vistos)
        self.assertFalse(self.painel._select_mode)

    def test_o_botao_da_barra_continua_trocando(self) -> None:
        """A pele clássica não regride: era o único feedback que existia, e continua existindo."""
        self.painel.toggle_area_selection()
        self.assertEqual(LIGADO, str(self.painel.btn_select.cget("text")))
        self.painel.disable_area_selection("cancelada")
        self.assertEqual(DESLIGADO, str(self.painel.btn_select.cget("text")))

    def test_a_recusa_por_falta_de_pdf_nao_avisa(self) -> None:
        """Sem livro aberto o modo não liga, e anunciar "ligado" faria a fita mentir."""
        self.painel.source = None
        self.painel.page_rgb = None
        self.painel.toggle_area_selection()
        self.assertEqual([], self.vistos)
