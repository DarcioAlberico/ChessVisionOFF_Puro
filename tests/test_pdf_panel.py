"""O visualizador com os diagramas marcados, montado de verdade e sem PDF nenhum (S-68).

O `page_overlay` cobre a regra -- geometria, alvo do clique, escolha da fonte. O que sobra
para cá é o que só quebra com widget: o retângulo aparecer sobre a página e sumir com ela, o
clique virar aviso e o arrasto **não** virar, e a caixa que chegou atrasada não se desenhar
sobre a página seguinte.

O DPI da montagem é 72 de propósito: um ponto do PDF vira um pixel, e as coordenadas do teste
são as mesmas da tela. Com 220 as contas teriam de ser refeitas a cada leitura.
"""

from __future__ import annotations

import shutil
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

import fitz
import numpy as np

from chess_diagram_ocr.ui import pdf_panel
from chess_diagram_ocr.ui.page_overlay import DiagramBox, OverlayParams, PageBoxes
from chess_diagram_ocr.ui.pdf_panel import (
    BOX_OUTLINE,
    BOX_OUTLINE_RECOGNIZED,
    BOX_OUTLINE_SAVED,
    PdfPanel,
)

PARAMS = OverlayParams(dpi=72, max_boards=12)
CAIXAS = (
    DiagramBox(index=0, bbox_pdf=(10.0, 10.0, 110.0, 110.0), source="embedded"),
    DiagramBox(index=1, bbox_pdf=(10.0, 150.0, 110.0, 250.0), source="contour"),
)


def _evento(x: float, y: float) -> tk.Event:
    """Um evento de mouse cru. `tk.Event` é uma classe comum: dá para montá-la à mão."""
    evento = tk.Event()
    evento.x, evento.y = int(x), int(y)
    return evento


def _roda(delta: int) -> tk.Event:
    """Um giro da roda. `x_root`/`y_root` existem porque a roda é ligada na janela inteira."""
    evento = _evento(50, 50)
    evento.delta = delta
    evento.x_root, evento.y_root = 50, 50
    evento.state = 0
    return evento


_RAIZ: tk.Tk | None = None


def _raiz() -> tk.Tk:
    """Uma raiz Tk para o módulo inteiro, criada uma vez e nunca destruída.

    Cópia deliberada do `test_result_panel`, e pelo mesmo motivo: enquanto houve uma classe
    só, criar e destruir a raiz da classe funcionou; a segunda classe do módulo (a da S-123)
    caiu em `tk wasn't installed properly` -- reinicializar o Tcl depois de destruir a última
    raiz não é confiável no Windows. E o sintoma é pior que a causa: a classe não falha, é
    **pulada**, e uma suíte verde esconde os testes que não rodaram.
    """
    global _RAIZ
    if _RAIZ is None:
        try:
            _RAIZ = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - maquina sem display
            raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
        _RAIZ.withdraw()
    return _RAIZ


class PdfPanelBoxesTests(unittest.TestCase):
    """Uma raiz Tk para o módulo, pelo mesmo motivo do `test_gallery_panel` -- ver `_raiz`."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = _raiz()

    def setUp(self) -> None:
        self.cliques: list[int] = []
        self.marcacao: list[bool] = []
        self.status: list[str] = []
        self.host = tk.Frame(self.root)
        self.panel = PdfPanel(
            self.host,
            dpi=lambda: 72,
            initial_page_for=lambda _caminho: 0,
            on_status=self.status.append,
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
            on_box_click=self.cliques.append,
            on_prefs_changed=lambda: self.marcacao.append(bool(self.panel.show_boxes_var.get())),
        )
        # Uma página na tela sem abrir arquivo nenhum: o painel só precisa dos pixels e de
        # saber para qual página eles são.
        self.panel.source = Path("livro.pdf")
        self.panel.page_rgb = np.zeros((400, 300, 3), dtype=np.uint8)
        self.panel.page_loaded_for_index = 0
        self.panel.zoom_var.set(1.0)
        self.panel.refresh_view()

    def tearDown(self) -> None:
        self.host.destroy()

    # ------------------------------------------------------------------------- desenho

    def _retangulos(self) -> list[int]:
        return [
            item
            for item in self.panel.canvas.find_withtag("diagram-box")
            if self.panel.canvas.type(item) == "rectangle"
        ]

    def test_as_caixas_da_pagina_exibida_sao_aceitas_e_desenhadas(self) -> None:
        self.assertTrue(self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS)))
        # Dois retângulos por diagrama: o contorno e o fundo do número.
        self.assertEqual(len(self._retangulos()), 4)
        self.assertIn("2 diagrama(s)", self.panel.lbl_boxes.cget("text"))

    def test_a_caixa_atrasada_de_outra_pagina_e_recusada(self) -> None:
        """A detecção roda em thread: quem a pediu para a 16 pode já estar na 17."""
        self.assertFalse(self.panel.set_diagram_boxes(PageBoxes(9, PARAMS, CAIXAS)))
        self.assertEqual(self._retangulos(), [])
        self.assertIsNone(self.panel.boxes)

    def test_o_retangulo_fica_onde_o_diagrama_esta(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS[:1]))
        self.assertEqual(self.panel.canvas.coords(self._retangulos()[0]), [10.0, 10.0, 110.0, 110.0])

    def test_o_zoom_move_o_retangulo_junto_com_a_pagina(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS[:1]))
        self.panel.zoom_var.set(0.5)
        self.panel.refresh_view()
        self.assertEqual(self.panel.canvas.coords(self._retangulos()[0]), [5.0, 5.0, 55.0, 55.0])

    def test_a_selecao_nao_gasta_uma_cor(self) -> None:
        """A cor diz em que ponto do trabalho o diagrama está; a borda diz qual está aberto.

        Enquanto a seleção era uma quarta cor, ela apagava o estado do diagrama selecionado --
        justamente o que se quer ver ao chegar nele (S-71).
        """
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self.panel.select_box(1)
        cores = [self.panel.canvas.itemcget(item, "outline") for item in self._retangulos()]
        self.assertEqual(set(cores), {BOX_OUTLINE}, "a seleção não muda a cor de ninguém")

        larguras = [float(self.panel.canvas.itemcget(item, "width")) for item in self._retangulos()]
        self.assertEqual(larguras.count(4.0), 1, "só o selecionado tem a borda grossa")

    def test_a_selecao_nao_pinta_nada_sobre_o_tabuleiro(self) -> None:
        """A hachura punha pontinhos sobre as casas que se está tentando conferir (S-71).

        Virou uma segunda borda, **por fora** da caixa: marca a seleção sem gastar um pixel do
        diagrama.
        """
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self.panel.select_box(0)

        for item in self._retangulos():
            with self.subTest(item=item):
                self.assertEqual(self.panel.canvas.itemcget(item, "stipple"), "")

        caixa = CAIXAS[0].bbox_pdf
        halo = [
            item
            for item in self._retangulos()
            if self.panel.canvas.coords(item)[0] < caixa[0]
            and self.panel.canvas.coords(item)[2] > caixa[2]
        ]
        self.assertEqual(len(halo), 1, "a segunda borda fica para fora da caixa")

    def test_as_tres_cores_dizem_o_ponto_do_trabalho(self) -> None:
        caixas = (
            DiagramBox(index=0, bbox_pdf=(10.0, 10.0, 110.0, 110.0)),
            DiagramBox(index=1, bbox_pdf=(10.0, 150.0, 110.0, 250.0), recognized=True),
            DiagramBox(index=2, bbox_pdf=(150.0, 10.0, 250.0, 110.0), recognized=True, saved=True),
            DiagramBox(index=3, bbox_pdf=(150.0, 150.0, 250.0, 250.0), saved=True),
        )
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, caixas))
        cores = [self.panel.canvas.itemcget(item, "outline") for item in self._retangulos()]
        # Dois retângulos por caixa (contorno e fundo do número), na ordem em que foram criados.
        self.assertEqual(
            cores[::2],
            [BOX_OUTLINE, BOX_OUTLINE_RECOGNIZED, BOX_OUTLINE_SAVED, BOX_OUTLINE_SAVED],
            "salvo ganha de lido mesmo sem OCR nesta sessão",
        )

    def test_o_rotulo_conta_lidos_e_salvos_separadamente(self) -> None:
        caixas = (
            DiagramBox(index=0, bbox_pdf=(10.0, 10.0, 110.0, 110.0), recognized=True),
            DiagramBox(index=1, bbox_pdf=(10.0, 150.0, 110.0, 250.0), recognized=True, saved=True),
        )
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, caixas))
        texto = self.panel.lbl_boxes.cget("text")
        self.assertIn("2 diagrama(s)", texto)
        self.assertIn("1 lido(s)", texto)
        self.assertIn("1 de 2 salvo(s)", texto, "a fração diz quanto falta; o número solto, não")

    def test_a_pagina_com_tudo_salvo_diz_que_acabou_em_vez_de_somar(self) -> None:
        """A pergunta é "posso virar?", e contar retângulo verde é a resposta pela metade."""
        caixas = tuple(
            DiagramBox(index=i, bbox_pdf=(10.0, 10.0 + i * 140, 110.0, 110.0 + i * 140), saved=True)
            for i in range(2)
        )
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, caixas))
        self.assertIn("página concluída", self.panel.lbl_boxes.cget("text"))
        self.assertEqual(
            # `str`: o Tk devolve um objeto Tcl aqui, e ele não é igual à string do Python.
            str(self.panel.lbl_boxes.cget("foreground")),
            BOX_OUTLINE_SAVED,
            "o rótulo diz da página o que os retângulos dizem de cada diagrama",
        )

    def test_falta_um_diagrama_e_a_pagina_nao_se_diz_concluida(self) -> None:
        caixas = (
            DiagramBox(index=0, bbox_pdf=(10.0, 10.0, 110.0, 110.0), saved=True),
            DiagramBox(index=1, bbox_pdf=(10.0, 150.0, 110.0, 250.0)),
        )
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, caixas))
        texto = self.panel.lbl_boxes.cget("text")
        self.assertNotIn("concluída", texto)
        self.assertIn("1 de 2 salvo(s)", texto)

    def test_a_pagina_seguinte_apaga_o_verde_do_rotulo(self) -> None:
        """A cor é do estado, não do widget: deixá-la acesa afirmaria da 1 o que era da 0."""
        salva = DiagramBox(index=0, bbox_pdf=(10.0, 10.0, 110.0, 110.0), saved=True)
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, (salva,)))
        self.panel.clear_diagram_boxes()
        self.assertEqual(str(self.panel.lbl_boxes.cget("foreground")), "")

    def test_desligar_a_marcacao_apaga_os_retangulos_e_avisa(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self.panel.show_boxes_var.set(False)
        self.panel.on_boxes_toggle()
        self.assertEqual(self._retangulos(), [])
        self.assertEqual(self.marcacao, [False])

    def test_a_pagina_permanece_quando_os_retangulos_somem(self) -> None:
        """`delete("diagram-box")`, e não `delete("all")`: a imagem não é redesenhada aqui."""
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self.panel.clear_diagram_boxes()
        self.assertTrue(self.panel.canvas.find_withtag("all"), "a página sumiu junto")
        self.assertEqual(self._retangulos(), [])

    def test_pagina_sem_diagrama_diz_isso_em_vez_de_ficar_muda(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, ()))
        self.assertIn("nenhum diagrama", self.panel.lbl_boxes.cget("text"))

    def test_sem_resposta_ainda_o_rotulo_fica_vazio(self) -> None:
        """"Não se sabe" e "não há" são estados diferentes, e só o segundo se anuncia."""
        self.assertIsNone(self.panel.boxes)
        self.assertEqual(self.panel.lbl_boxes.cget("text"), "")

    # -------------------------------------------------------------------------- clique

    def _clicar(self, x: float, y: float, *, solta_em: tuple[float, float] | None = None) -> None:
        self.panel._on_press(_evento(x, y))
        alvo = solta_em or (x, y)
        self.panel._on_release(_evento(*alvo))

    def test_clicar_num_diagrama_avisa_a_janela_com_o_indice(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self._clicar(60, 200)
        self.assertEqual(self.cliques, [1])

    def test_clicar_fora_de_qualquer_diagrama_nao_avisa_nada(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self._clicar(250, 380)
        self.assertEqual(self.cliques, [])

    def test_arrastar_a_pagina_nao_abre_o_diagrama_de_baixo(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self._clicar(60, 60, solta_em=(60, 200))
        self.assertEqual(self.cliques, [])

    def test_a_folga_do_clique_tolera_a_mao_tremida(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self._clicar(60, 60, solta_em=(62, 61))
        self.assertEqual(self.cliques, [0])

    def test_com_a_marcacao_desligada_o_clique_nao_abre_nada(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self.panel.show_boxes_var.set(False)
        self._clicar(60, 60)
        self.assertEqual(self.cliques, [])

    def test_no_modo_de_selecao_de_area_o_clique_pertence_a_selecao(self) -> None:
        """Senão o arrasto que desenha o retângulo verde abriria um diagrama ao terminar."""
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self.panel.toggle_area_selection()
        self._clicar(20, 20, solta_em=(100, 100))
        self.assertEqual(self.cliques, [])

    def test_sem_caixas_o_clique_nao_levanta(self) -> None:
        self._clicar(60, 60)
        self.assertEqual(self.cliques, [])

    # ------------------------------------------------------------- roda e arrasto (S-70)

    def _finge_vista(self, primeiro: float, ultimo: float) -> list[tuple[int, str]]:
        """Fixa onde a vista está e devolve a lista onde as rolagens vão sendo anotadas.

        O canvas do teste não está mapeado, entao `yview()` de verdade diria sempre "a pagina
        inteira cabe" -- que é justamente uma das bordas. Fixar a vista é o que permite testar
        o meio da página."""
        rolagens: list[tuple[int, str]] = []
        self.panel.canvas.yview = lambda: (primeiro, ultimo)  # type: ignore[method-assign]
        self.panel.canvas.yview_scroll = lambda n, what: rolagens.append((n, what))  # type: ignore[method-assign]
        self.panel._pointer_over_canvas = lambda _evento: True  # type: ignore[method-assign]
        return rolagens

    def test_a_roda_no_meio_da_pagina_rola(self) -> None:
        rolagens = self._finge_vista(0.3, 0.7)
        self.panel._on_wheel(_roda(-120))
        self.assertEqual(rolagens, [(3, "units")])
        self.panel._on_wheel(_roda(120))
        self.assertEqual(rolagens[-1], (-3, "units"))

    def test_a_roda_no_rodape_vira_a_pagina_e_entra_pelo_topo(self) -> None:
        self._finge_vista(0.6, 1.0)
        self.panel.page_count = 5
        self.panel.render_current_page = lambda: True  # type: ignore[method-assign]
        posicoes: list[float] = []
        self.panel.canvas.yview_moveto = posicoes.append  # type: ignore[method-assign]

        self.panel._on_wheel(_roda(-120))
        self.assertEqual(self.panel.page_index, 1)
        self.assertEqual(posicoes[-1], 0.0, "a página seguinte começa no topo")

    def test_com_a_virada_desligada_a_borda_so_rola(self) -> None:
        rolagens = self._finge_vista(0.6, 1.0)
        self.panel.page_count = 5
        self.panel.flip_pages_var.set(False)
        self.panel._on_wheel(_roda(-120))
        self.assertEqual(self.panel.page_index, 0)
        self.assertEqual(rolagens, [(3, "units")])

    def test_o_ponteiro_fora_da_pagina_deixa_a_roda_passar(self) -> None:
        """A roda é ligada na janela inteira; quem não é o canvas nao pode engoli-la."""
        self.assertIsNone(self.panel._on_wheel(_roda(-120)))

    def test_o_ponteiro_e_decidido_pelo_retangulo_do_canvas(self) -> None:
        """Regressão medida: `winfo_containing` resolve pelo `WindowFromPoint` do Windows.

        Com a janela do app atrás do terminal, ele devolvia `None` para um ponto que estava
        dentro do canvas -- e a roda parava de funcionar sem nada na tela dizendo por quê. A
        conta com as coordenadas do próprio widget não depende de empilhamento.
        """
        canvas = self.panel.canvas
        canvas.winfo_ismapped = lambda: True  # type: ignore[method-assign]
        canvas.winfo_rootx = lambda: 100  # type: ignore[method-assign]
        canvas.winfo_rooty = lambda: 200  # type: ignore[method-assign]
        canvas.winfo_width = lambda: 400  # type: ignore[method-assign]
        canvas.winfo_height = lambda: 300  # type: ignore[method-assign]

        dentro, fora, abaixo = _roda(-120), _roda(-120), _roda(-120)
        dentro.x_root, dentro.y_root = 150, 250
        fora.x_root, fora.y_root = 90, 250
        abaixo.x_root, abaixo.y_root = 150, 600

        self.assertTrue(self.panel._pointer_over_canvas(dentro))
        self.assertFalse(self.panel._pointer_over_canvas(fora))
        self.assertFalse(self.panel._pointer_over_canvas(abaixo))

    def test_ctrl_roda_amplia_ancorado_no_ponteiro(self) -> None:
        self._finge_vista(0.3, 0.7)
        antes = float(self.panel.zoom_var.get())
        self.panel._on_wheel_zoom(_roda(120))
        self.assertGreater(float(self.panel.zoom_var.get()), antes)
        self.panel._on_wheel_zoom(_roda(-120))
        self.assertAlmostEqual(float(self.panel.zoom_var.get()), antes, places=6)

    def test_arrastar_desloca_a_pagina_em_vez_de_abrir_diagrama(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        arrastos: list[tuple[int, int]] = []
        self.panel.canvas.scan_dragto = lambda x, y, gain=1: arrastos.append((x, y))  # type: ignore[method-assign]

        self.panel._on_press(_evento(60, 60))
        self.panel._on_drag(_evento(60, 140))
        self.panel._on_release(_evento(60, 140))

        self.assertEqual(arrastos, [(60, 140)])
        self.assertEqual(self.cliques, [], "arrasto não é clique")
        self.assertFalse(self.panel._panning, "o cursor de mão tem de voltar ao normal")

    def test_o_tremor_dentro_da_folga_nao_vira_arrasto(self) -> None:
        arrastos: list[tuple[int, int]] = []
        self.panel.canvas.scan_dragto = lambda x, y, gain=1: arrastos.append((x, y))  # type: ignore[method-assign]
        self.panel._on_press(_evento(60, 60))
        self.panel._on_drag(_evento(62, 61))
        self.assertEqual(arrastos, [])

    def test_ajustar_a_largura_sem_pdf_avisa_em_vez_de_calcular(self) -> None:
        self.panel.page_rgb = None
        self.panel.fit_width()
        self.assertTrue(any("Abra um PDF" in mensagem for mensagem in self.status))

    def test_a_preferencia_da_virada_avisa_a_janela_para_ser_lembrada(self) -> None:
        antes = len(self.marcacao)
        self.panel.chk_flip.invoke()
        self.assertEqual(len(self.marcacao), antes + 1)

    # ------------------------------------------------------- leitor do sistema (S-69)

    def test_o_botao_do_leitor_nasce_desligado(self) -> None:
        """Sem PDF aberto não há o que mandar para o leitor."""
        self.assertEqual(str(self.panel.btn_system_reader.cget("state")), "disabled")

    def test_sem_pdf_o_botao_nao_faz_nada_em_vez_de_levantar(self) -> None:
        self.panel.source = None
        self.panel.open_in_system_reader()
        self.assertEqual(self.status, [])

    def test_com_pdf_manda_o_arquivo_para_o_leitor_do_sistema(self) -> None:
        enviados: list[Path] = []
        original = pdf_panel.open_in_system_reader
        pdf_panel.open_in_system_reader = enviados.append  # type: ignore[assignment]
        try:
            self.panel.name = "livro.pdf"
            self.panel.open_in_system_reader()
        finally:
            pdf_panel.open_in_system_reader = original  # type: ignore[assignment]

        self.assertEqual(enviados, [Path("livro.pdf")])
        self.assertTrue(any("leitor do sistema" in mensagem for mensagem in self.status))

    def test_falha_do_leitor_e_aviso_e_nao_derruba_o_painel(self) -> None:
        """O PDF continua na tela; o que falhou foi o programa de fora."""
        def _explode(_caminho: Path) -> None:
            raise OSError("nenhum aplicativo associado")

        avisos: list[tuple[str, str]] = []
        original = pdf_panel.open_in_system_reader
        original_box = pdf_panel.messagebox.showwarning
        pdf_panel.open_in_system_reader = _explode  # type: ignore[assignment]
        pdf_panel.messagebox.showwarning = lambda titulo, texto: avisos.append((titulo, texto))  # type: ignore[assignment]
        try:
            self.panel.open_in_system_reader()
        finally:
            pdf_panel.open_in_system_reader = original  # type: ignore[assignment]
            pdf_panel.messagebox.showwarning = original_box  # type: ignore[assignment]

        self.assertEqual(len(avisos), 1)
        self.assertIn("nenhum aplicativo associado", avisos[0][1])

    def test_nao_sobrou_aba_nenhuma_no_visualizador(self) -> None:
        """A "Leitura" saiu na S-69; um `Notebook` aqui seria ela voltando."""
        self.assertFalse(hasattr(self.panel, "view_tabs"))
        self.assertFalse(hasattr(self.panel, "reader_tab"))

    def test_o_ponteiro_vira_mao_sobre_o_diagrama(self) -> None:
        self.panel.set_diagram_boxes(PageBoxes(0, PARAMS, CAIXAS))
        self.panel._on_hover(_evento(60, 60))
        self.assertEqual(str(self.panel.canvas.cget("cursor")), "hand2")
        self.panel._on_hover(_evento(280, 380))
        self.assertEqual(str(self.panel.canvas.cget("cursor")), "")


class LoadPdfEstadoTests(unittest.TestCase):
    """O PDF que não abre não troca o livro por dentro (S-123).

    Aqui há arquivo de verdade -- em `tmp_path` e nunca versionado, como os fixtures da
    detecção -- porque o que se testa é exatamente a fronteira entre "abriu" e "não abriu", e
    um `get_pdf_page_count` fingido testaria o fingimento.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = _raiz()

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cvoff-s123-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

        self.bom = self.tmp / "bom.pdf"
        doc = fitz.open()
        doc.new_page(width=200, height=300)
        doc.new_page(width=200, height=300)
        doc.save(str(self.bom))
        doc.close()

        self.quebrado = self.tmp / "quebrado.pdf"
        self.quebrado.write_bytes(b"%PDF-1.4 isto nao e um PDF\n")

        self.abertos: list[Path] = []
        self.erros: list[tuple[str, str]] = []
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
            on_pdf_opened=self.abertos.append,
            on_before_page_change=lambda: None,
            on_page_rendered=lambda _indice: None,
            on_zoom_changed=lambda _zoom: None,
            initial_dir=self.tmp,
        )
        original = pdf_panel.messagebox.showerror
        pdf_panel.messagebox.showerror = (  # type: ignore[assignment]
            lambda titulo, texto: self.erros.append((titulo, texto))
        )
        self.addCleanup(setattr, pdf_panel.messagebox, "showerror", original)
        self.addCleanup(self.host.destroy)

    def test_o_pdf_valido_abre_e_o_estado_e_dele(self) -> None:
        self.panel.load_pdf(self.bom)
        self.assertEqual(self.erros, [])
        self.assertEqual(self.panel.source, self.bom)
        self.assertEqual(self.panel.name, "bom.pdf")
        self.assertEqual(self.panel.page_count, 2)
        self.assertEqual(self.abertos, [self.bom])

    def test_o_pdf_corrompido_nao_troca_o_estado_do_valido(self) -> None:
        """O defeito da S-123: a tela mostrava o livro anterior e o estado era o do quebrado."""
        self.panel.load_pdf(self.bom)
        self.abertos.clear()

        self.panel.load_pdf(self.quebrado)

        self.assertEqual(self.panel.source, self.bom)
        self.assertEqual(self.panel.name, "bom.pdf")
        self.assertEqual(self.panel.page_count, 2)

    def test_o_callback_nao_dispara_para_o_pdf_que_nao_abriu(self) -> None:
        """É `_on_pdf_opened` quem limpa as caixas e reaponta a Galeria. Ele não pode rodar."""
        self.panel.load_pdf(self.bom)
        self.abertos.clear()

        self.panel.load_pdf(self.quebrado)

        self.assertEqual(self.abertos, [])

    def test_a_mensagem_nomeia_o_arquivo_que_falhou_e_o_que_ficou(self) -> None:
        self.panel.load_pdf(self.bom)
        self.panel.load_pdf(self.quebrado)

        self.assertEqual(len(self.erros), 1)
        _titulo, texto = self.erros[0]
        self.assertIn("quebrado.pdf", texto)
        self.assertIn("bom.pdf continua aberto", texto)

    def test_sem_livro_anterior_a_mensagem_nao_promete_nenhum(self) -> None:
        """Dizer "continua aberto" sobre nada seria pior que não dizer."""
        self.panel.load_pdf(self.quebrado)

        self.assertIsNone(self.panel.source)
        self.assertEqual(len(self.erros), 1)
        self.assertIn("quebrado.pdf", self.erros[0][1])
        self.assertNotIn("continua aberto", self.erros[0][1])

    def test_a_falha_vai_para_o_log_com_rastro(self) -> None:
        """No bundle da S-55 não há console: sem isto, a falha não existe em lugar nenhum."""
        with self.assertLogs(pdf_panel.logger, level="ERROR") as registro:
            self.panel.load_pdf(self.quebrado)

        self.assertIn("quebrado.pdf", registro.output[0])
        self.assertIn("Traceback", registro.output[0])


if __name__ == "__main__":
    unittest.main()
