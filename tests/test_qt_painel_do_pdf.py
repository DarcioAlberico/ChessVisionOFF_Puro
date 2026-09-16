"""O visualizador de PDF do segundo frontend (S-31/S-68/S-304/S-305/S-328/S-330/S-503).

**O que estes testes cobrem, e o que não.** O zoom, a roda, o "caber na página", onde estão as
caixas e o que um clique nelas acerta são de `ui/viewport.py` e `ui/page_overlay.py`, e já são
afirmados sem janela. Os três números medidos são de `ui/leitura_do_pdf.py`, e são puros.

O que só existe deste lado são as coisas em que o Qt difere do Tk e que quebram calado:

1. **O campo de página é um `QSpinBox`**, e a comparação continua sendo contra a folha **que está
   na tela** -- não contra o índice que já mudou. É o defeito da S-305, que só aparece quando os
   dois divergem.
2. **A última página não re-rasteriza** (S-304): sem a guarda, cada giro da roda ali gasta uma
   rasterização inteira e joga a vista de volta ao topo.
3. **O piso da seleção é medido na folha, e não na tela** (S-330): a 25% ele valeria 48 px de
   página, e a 200%, 6 px.
4. **Clique e arrasto usam o mesmo botão**, e a folga é o que os separa (S-68).
5. **O deslizador de zoom não pode se realimentar** (S-225).
"""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import comandos, leitura_do_pdf
from chess_diagram_ocr.ui.page_overlay import DiagramBox, OverlayParams, PageBoxes

if TEM_PYQT:
    from chess_diagram_ocr.qt import painel_do_pdf as qt_pdf


def _pagina(largura: int = 300, altura: int = 400) -> np.ndarray:
    return np.zeros((altura, largura, 3), dtype=np.uint8)


def _caixas(pagina: int = 0, quantas: int = 2) -> PageBoxes:
    """Caixas cujo retângulo na tela é o próprio `bbox_pdf`, a zoom 1.

    `dpi=72` é o truque, e ele é honesto: `canvas_rect` escala por `dpi / 72 * zoom`, então a 72
    DPI a escala é o zoom. Com o 220 do produto o mesmo teste teria de dividir cada coordenada por
    3,0555 para dizer onde clicar -- e o número que ele afirma deixaria de ser o que se lê.
    """
    return PageBoxes(
        page_index=pagina,
        params=OverlayParams(dpi=72, max_boards=8),
        boxes=tuple(
            DiagramBox(index=i, bbox_pdf=(10.0 + 60 * i, 10.0, 60.0 + 60 * i, 60.0))
            for i in range(quantas)
        ),
    )


class DeclaracaoTests(unittest.TestCase):
    """A decisão é a mesma dos dois lados, e nenhum dos dois a reescreve."""

    def test_o_modulo_puro_nao_carrega_tkinter_nem_imagetk(self) -> None:
        import ast

        arvore = ast.parse(Path(leitura_do_pdf.__file__).read_text(encoding="utf-8"))
        nomes = {no.names[0].name.split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.Import)}
        nomes |= {(no.module or "").split(".")[0] for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
        self.assertNotIn("tkinter", nomes)
        self.assertNotIn("PIL", nomes)

@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelTests(unittest.TestCase):
    """O painel montado, com uma folha de mentira posta à mão no visor."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.dpi = 220
        self.addCleanup(self.app.processEvents)

    def painel(self, **kwargs: object) -> qt_pdf.PainelDoPdf:
        montado = qt_pdf.PainelDoPdf(dpi=lambda: self.dpi, **kwargs)  # type: ignore[arg-type]
        self.addCleanup(descartar, montado)
        montado.resize(900, 700)
        montado.show()
        self.app.processEvents()
        return montado

    def com_pagina(self, paginas: int = 3) -> qt_pdf.PainelDoPdf:
        """Um painel que **acredita** ter um livro aberto, com a rasterização anotada em vez de
        feita. O que ela desenhou fica em `painel.renderizadas`.

        **A rasterização é trocada, e não deixada rodar.** Os testes desta classe medem a
        navegação e os gestos, e nenhum depende de `render_pdf_page` -- mas `livro.pdf` não
        existe, e a de verdade abriria uma `QMessageBox.critical` que, sob `offscreen`, espera
        para sempre por um clique que ninguém vai dar. Um teste que trava não falha: ele fica
        parado, e a suíte inteira com ele.
        """
        painel = self.painel()
        painel.source = Path("livro.pdf")
        painel.name = "livro.pdf"
        painel.page_count = paginas
        painel.page_rgb = _pagina()
        painel.page_loaded_for_index = 0
        painel._faixa_do_campo_de_pagina()
        painel.visor.mostrar_pagina(painel.page_rgb, dpi=self.dpi)

        painel.renderizadas: list[int] = []  # type: ignore[attr-defined]

        def _anotar() -> bool:
            painel.renderizadas.append(painel.page_index)  # type: ignore[attr-defined]
            painel.page_loaded_for_index = painel.page_index
            return painel.page_rgb is not None

        painel.desenhar_pagina = _anotar  # type: ignore[method-assign]
        return painel

    def test_o_estado_vazio_nao_promete_o_que_nao_tem(self) -> None:
        painel = self.painel()
        from chess_diagram_ocr.ui import strings

        # **O rótulo do livro é elidido desde o F9-C2**: `text()` devolve o que está
        # desenhado, que depende da largura que o leiaute deu; o que a frase promete é
        # `texto_inteiro`. E `Abrir no leitor do sistema` saiu da barra para o menu `Arquivo`
        # (§7 item 11), onde ele já estava declarado em `ui/menu.MENUS`.
        self.assertEqual(painel.lbl_pdf.texto_inteiro, strings.NENHUM_PDF_ABERTO)
        self.assertIsNone(painel.source, "sem livro não há o que abrir no leitor")
        self.assertFalse(painel.desenhar_pagina(), "sem livro não há o que rasterizar")

    def test_selecionar_area_sem_livro_avisa_no_rodape(self) -> None:
        painel = self.painel()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.alternar_selecao()
        self.assertEqual(vistos, ["Abra um PDF antes de selecionar uma área."])
        self.assertFalse(painel.visor.selecionando)

    def test_o_campo_de_pagina_e_base_1_e_nunca_zero_a_zero(self) -> None:
        """"Página 0" não existe na contagem que o campo usa (S-328)."""
        vazio = self.painel()
        self.assertEqual((vazio.campo_pagina.minimum(), vazio.campo_pagina.maximum()), (1, 1))
        cheio = self.com_pagina(paginas=20)
        self.assertEqual((cheio.campo_pagina.minimum(), cheio.campo_pagina.maximum()), (1, 20))
        self.assertEqual(cheio.campo_pagina.value(), 1)

    def test_digitar_a_pagina_navega_de_verdade(self) -> None:
        """O `command` de um `ttk.Spinbox` só disparava nas setas: digitar `15` e teclar Enter
        mudava o índice e não mudava a imagem (S-305)."""
        painel = self.com_pagina(paginas=20)
        painel.campo_pagina.setValue(16)
        self.assertEqual(painel.page_index, 15)
        self.assertEqual(painel.renderizadas, [15])

    def test_a_ultima_pagina_nao_re_rasteriza(self) -> None:
        """Cinco giros da roda na última folha eram cinco rasterizações jogadas fora, e a vista
        voltava ao topo a cada uma (S-304)."""
        painel = self.com_pagina(paginas=3)
        painel._ir_para(2)
        painel.renderizadas.clear()
        for _ in range(5):
            painel.proxima_pagina()
        self.assertEqual(painel.renderizadas, [])

    def test_sem_imagem_a_ultima_pagina_ainda_tenta_de_novo(self) -> None:
        """Só o índice na guarda tiraria o único jeito de tentar depois de um render que falhou."""
        painel = self.com_pagina(paginas=3)
        painel._ir_para(2)
        painel.page_rgb = None
        painel.renderizadas.clear()
        painel.proxima_pagina()
        self.assertEqual(painel.renderizadas, [2])

    def test_ir_para_pagina_devolve_se_mudou(self) -> None:
        """A galeria só reage quando algo de fato se moveu -- é o que impede o vaivém (S-67)."""
        painel = self.com_pagina(paginas=5)
        self.assertTrue(painel.ir_para_pagina(3))
        self.assertFalse(painel.ir_para_pagina(3))
        self.assertFalse(painel.ir_para_pagina(99) and painel.page_index != 4)

    def test_a_pagina_e_grampeada_na_faixa_do_livro(self) -> None:
        painel = self.com_pagina(paginas=3)
        painel._ir_para(-5)
        self.assertEqual(painel.page_index, 0)
        painel._ir_para(99)
        self.assertEqual(painel.page_index, 2)

    def test_o_deslizador_e_o_zoom_andam_juntos_sem_se_realimentar(self) -> None:
        """Mover o deslizador aplica o zoom, e aplicar o zoom repõe o deslizador -- que
        dispararia de novo (S-225)."""
        from chess_diagram_ocr.ui.viewport import MAX_ZOOM, posicao_do_zoom

        painel = self.painel()
        painel.deslizador.setValue(int(posicao_do_zoom(MAX_ZOOM)))
        self.assertAlmostEqual(painel.zoom, MAX_ZOOM, places=3)
        self.assertEqual(painel.lbl_zoom.text(), "200%")
        painel.aplicar_zoom(0.5)
        self.assertEqual(painel.deslizador.value(), int(round(posicao_do_zoom(0.5))))
        self.assertAlmostEqual(painel.zoom, 0.5, places=3)

    def test_o_zoom_e_aditivo_e_grampeado(self) -> None:
        """Um clique, um passo previsível -- e nunca além da faixa."""
        from chess_diagram_ocr.ui.viewport import MAX_ZOOM, MIN_ZOOM

        painel = self.painel()
        painel.aplicar_zoom(1.0)
        painel.aumentar_zoom()
        self.assertAlmostEqual(painel.zoom, 1.0 + leitura_do_pdf.PASSO_DE_ZOOM, places=3)
        for _ in range(40):
            painel.aumentar_zoom()
        self.assertAlmostEqual(painel.zoom, MAX_ZOOM, places=3)
        for _ in range(60):
            painel.diminuir_zoom()
        self.assertAlmostEqual(painel.zoom, MIN_ZOOM, places=3)

    def test_o_texto_do_zoom_vem_de_formato(self) -> None:
        """Duas formatações do mesmo número é como elas divergem, e ele aparece em dois rótulos."""
        from chess_diagram_ocr.ui import formato

        painel = self.painel()
        painel.aplicar_zoom(0.7)
        self.assertEqual(painel.lbl_zoom.text(), formato.porcentagem(painel.zoom, casas=0))

    def test_as_caixas_de_outra_pagina_sao_recusadas(self) -> None:
        """A detecção roda em thread, e quem a pediu para a página 16 pode já estar na 17."""
        painel = self.com_pagina(paginas=5)
        self.assertTrue(painel.definir_caixas(_caixas(pagina=0)))
        self.assertIsNotNone(painel.boxes)
        self.assertFalse(painel.definir_caixas(_caixas(pagina=3)))
        assert painel.boxes is not None
        self.assertEqual(painel.boxes.page_index, 0)

    def test_dispensar_sem_selecao_diz_o_caminho(self) -> None:
        """Até a página ser lida, seleção nenhuma existe -- e é aí que o botão direito é o
        caminho (S-177)."""
        painel = self.com_pagina()
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        painel.dispensar_a_selecionada()
        painel.definir_caixas(_caixas())
        painel.dispensar_a_selecionada()
        self.assertEqual(len(vistos), 2)
        self.assertIn("Nenhuma caixa nesta página", vistos[0])
        self.assertIn("botão direito", vistos[1])

    def test_o_botao_direito_dispensa_a_caixa_de_baixo(self) -> None:
        painel = self.com_pagina()
        painel.definir_caixas(_caixas())
        dispensadas: list[int] = []
        painel.caixa_dispensada.connect(dispensadas.append)
        painel.visor.dispensar_em(35, 35)
        self.assertEqual(dispensadas, [0])

    def test_o_clique_abre_e_o_arrasto_nao(self) -> None:
        """A folga é o que deixa a rolagem pela mão conviver com os diagramas marcados (S-68)."""
        painel = self.com_pagina()
        painel.definir_caixas(_caixas())
        clicadas: list[int] = []
        painel.caixa_clicada.connect(clicadas.append)

        painel.visor.apertou_em(35, 35)
        painel.visor.soltou_em(35 + leitura_do_pdf.CLICK_SLOP_PX, 35)
        self.assertEqual(clicadas, [0], "andar menos que a folga continua sendo clique")

        painel.visor.apertou_em(35, 35)
        painel.visor.arrastou_para(200, 200)
        painel.visor.soltou_em(200, 200)
        self.assertEqual(clicadas, [0], "arrastar a página não abre diagrama nenhum")

    def test_o_duplo_clique_manda_o_diagrama_para_a_sala_de_estudo(self) -> None:
        """O segundo aperto do par chega como duplo clique, e não como clique: o primeiro já
        selecionou o diagrama (ou mandou ler a página), e o que este acrescenta é o destino."""
        painel = self.com_pagina()
        painel.definir_caixas(_caixas())
        para_estudo: list[int] = []
        painel.caixa_para_estudo.connect(para_estudo.append)

        painel.visor.estudar_em(35 + 60, 35)
        self.assertEqual(para_estudo, [1])
        painel.visor.estudar_em(200, 300)
        self.assertEqual(para_estudo, [1], "fora de qualquer caixa não há o que estudar")
        painel.marcar_diagramas.setChecked(False)
        painel.visor.estudar_em(35, 35)
        self.assertEqual(para_estudo, [1], "caixa escondida não é alvo, como no clique simples")

    def test_o_duplo_clique_do_qt_chega_ao_visor_sem_contar_um_terceiro_clique(self) -> None:
        """O Qt entrega o segundo aperto como `MouseButtonDblClick`, e a soltura que o segue não
        acha ponto marcado -- então o duplo clique não sai também como um clique a mais."""
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest

        painel = self.com_pagina()
        painel.definir_caixas(_caixas())
        clicadas: list[int] = []
        para_estudo: list[int] = []
        painel.caixa_clicada.connect(clicadas.append)
        painel.caixa_para_estudo.connect(para_estudo.append)

        QTest.mouseDClick(painel.visor._folha, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(35, 35))
        self.assertEqual(para_estudo, [0])
        self.assertEqual(clicadas, [], "a soltura depois do duplo clique não é um clique")

    def test_a_selecao_devolve_pixel_de_pagina_e_nao_de_tela(self) -> None:
        """A conversão é a única parte que depende do zoom; recortar é do serviço (S-31)."""
        painel = self.com_pagina()
        painel.aplicar_zoom(2.0)
        painel.alternar_selecao()
        regioes: list[tuple[int, int, int, int]] = []
        painel.regiao_pedida.connect(lambda _pagina, regiao: regioes.append(regiao))
        painel.visor.apertou_em(40, 60)
        painel.visor.arrastou_para(140, 200)
        painel.visor.soltou_em(140, 200)
        self.assertEqual(regioes, [(20, 30, 70, 100)])

    def test_o_piso_da_selecao_e_medido_na_folha(self) -> None:
        """A 200% o mesmo arrasto de tela vale metade na página: medi-lo antes da conversão fazia
        o mínimo variar oito vezes entre 25% e 200% (S-330)."""
        painel = self.com_pagina()
        painel.aplicar_zoom(2.0)
        vistos: list[str] = []
        painel.estado.connect(vistos.append)
        regioes: list[object] = []
        painel.regiao_pedida.connect(lambda _p, regiao: regioes.append(regiao))
        painel.alternar_selecao()
        # 20 px de tela a 200% são 10 px de folha -- abaixo dos 12 do piso.
        painel.visor.apertou_em(0, 0)
        painel.visor.arrastou_para(20, 20)
        painel.visor.soltou_em(20, 20)
        self.assertEqual(regioes, [])
        self.assertIn("Seleção muito pequena. Tente novamente.", vistos)

    def test_o_modo_de_selecao_se_ve_marcado_e_se_ouve_alternado(self) -> None:
        """"Selecionar área" é um modo, e ligar e desligar não podem ter a mesma aparência (S-396)."""
        from chess_diagram_ocr.ui import comandos

        # **O canal mudou no F9-C2, e a regra não.** O rótulo trocava entre dois textos de
        # larguras diferentes, e largura de botão da barra é largura da **barra**: ligar a
        # seleção reflowava a fila inteira, que é o defeito que o item 11 do §7 veio fechar.
        # Um botão marcável diz o mesmo estado sem mexer em pixel de leiaute, e o nome por
        # extenso continua alternando -- que é o que um leitor de tela anuncia.
        painel = self.com_pagina()
        self.assertFalse(painel.btn_selecionar.isChecked())
        self.assertEqual(
            painel.btn_selecionar.accessibleName(), comandos.nome_acessivel("selecionar_area")
        )
        painel.alternar_selecao()
        self.assertTrue(painel.btn_selecionar.isChecked())
        self.assertEqual(
            painel.btn_selecionar.accessibleName(), comandos.rotulo_alternado("selecionar_area")
        )
        painel.alternar_selecao()
        self.assertFalse(painel.btn_selecionar.isChecked())
        self.assertEqual(
            painel.btn_selecionar.accessibleName(), comandos.nome_acessivel("selecionar_area")
        )

    def test_os_dois_interruptores_saem_pelo_nome_do_comando(self) -> None:
        """Quem acrescentar uma terceira preferência a declara ao lado das outras duas (S-161)."""
        painel = self.painel()
        self.assertEqual(
            sorted(painel.interruptores_de_vista), ["marcar_diagramas", "roda_vira_pagina"]
        )
        mudou: list[int] = []
        painel.preferencias_mudaram.connect(lambda: mudou.append(1))
        painel.marcar_diagramas.setChecked(False)
        self.assertFalse(painel.visor.mostrar_caixas)
        painel.roda_vira_pagina.setChecked(False)
        self.assertFalse(painel.visor.virar_paginas)
        self.assertEqual(mudou, [1, 1])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ControlesDoLivroTests(unittest.TestCase):
    """Os cinco botões que agem sobre a página exibida, e quem fica cinza (S-77/S-506).

    **Eles tinham sumido no porte para o Qt** e ficado só no menu. A ausência não quebrou guarda
    nenhuma: os cinco continuavam com item de menu, entrada na paleta e tecla, e a conta do
    catálogo pergunta se a ação tem dono -- não se alguma tela a mostra.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.addCleanup(self.app.processEvents)

    def painel(self, *, com_livro: bool = False) -> qt_pdf.PainelDoPdf:
        montado = qt_pdf.PainelDoPdf(dpi=lambda: 220)
        self.addCleanup(descartar, montado)
        if com_livro:
            montado.source = Path("livro.pdf")
            montado._reavaliar_controles()
        return montado

    def os_cinco(self, painel: qt_pdf.PainelDoPdf) -> dict[str, object]:
        return {
            "ler_melhor": painel.btn_ler_melhor,
            "ler_pagina": painel.btn_ler_pagina,
            "tirar_caixa": painel.btn_tirar_caixa,
            # **`exportar_pgn` saiu da barra** (F9-C2, §7 item 11): começar a exportação é do
            # menu `Arquivo`, onde ela já estava declarada. `selecionar_area` entrou no lugar --
            # mesmo bloco, mesma pré-condição.
            "selecionar_area": painel.btn_selecionar,
            "cancelar_exportacao": painel.btn_cancelar_exportacao,
        }

    def test_os_cinco_tiram_o_nome_do_catalogo(self) -> None:
        """Nenhum texto escrito aqui: é a regra da S-324, e `test_ui_comandos` a varre por `ast`."""
        from chess_diagram_ocr.ui import comandos

        painel = self.painel()
        for acao, botao in self.os_cinco(painel).items():
            with self.subTest(acao=acao):
                # **A afirmação passou do rótulo para o nome** (F9-C2): três dos cinco desenham
                # só o ícone, e o rótulo por extenso vive no `accessibleName` -- que é o que um
                # leitor de tela anuncia e o que o portão `caissa.ui.audit.teclado` cobra.
                # Perguntar `text()` a um botão de ícone aprovaria a string vazia.
                self.assertEqual(comandos.nome_acessivel(acao), botao.accessibleName())  # type: ignore[attr-defined]

    def test_sem_livro_os_cinco_ficam_cinza(self) -> None:
        """A pré-condição é a mesma do "Abrir no leitor": não há página sobre a qual agir."""
        painel = self.painel()
        for acao, botao in self.os_cinco(painel).items():
            with self.subTest(acao=acao):
                self.assertFalse(botao.isEnabled())  # type: ignore[attr-defined]

    def test_com_livro_acendem_quatro_e_o_cancelar_continua_cinza(self) -> None:
        """O cancelar não depende de haver livro, e sim de haver exportação."""
        painel = self.painel(com_livro=True)
        for acao in ("ler_melhor", "ler_pagina", "tirar_caixa", "selecionar_area"):
            with self.subTest(acao=acao):
                self.assertTrue(self.os_cinco(painel)[acao].isEnabled())  # type: ignore[attr-defined]
        self.assertFalse(painel.btn_cancelar_exportacao.isEnabled())

    def test_a_exportacao_traz_o_bloco_do_cancelar_e_o_leva_embora(self) -> None:
        """Uma por vez: enquanto uma roda, começar outra não é oferta."""
        # **O bloco só existe enquanto existe o que cancelar** (F9-C2, §7 itens 7 e 11). Era um
        # par permanente na barra com um dos dois sempre cinza; começar a exportação é do menu
        # agora, e o que a barra ganha -- só durante a exportação -- é o botão que para.
        painel = self.painel(com_livro=True)
        self.assertFalse(painel._bloco_exportacao.isVisibleTo(painel))
        painel.exportacao_em_curso(True)
        self.assertTrue(painel._bloco_exportacao.isVisibleTo(painel))
        self.assertTrue(painel.btn_cancelar_exportacao.isEnabled())

        painel.exportacao_em_curso(False)
        self.assertFalse(painel._bloco_exportacao.isVisibleTo(painel))
        self.assertFalse(painel.btn_cancelar_exportacao.isEnabled())

    def test_o_cancelar_sobrevive_ao_trancamento(self) -> None:
        """**É o caso que faz o botão valer alguma coisa.**

        A exportação tranca o resto da janela enquanto roda, e é exatamente nesse intervalo que o
        cancelar precisa estar vivo. Obedecer ao trancamento o apagaria na única situação em que
        ele serve -- e um `setEnabled(False)` no painel inteiro faria isso sem apelação, porque no
        Qt filho de widget desabilitado não reabilita.
        """
        painel = self.painel(com_livro=True)
        painel.exportacao_em_curso(True)
        painel.trancar(False)

        self.assertTrue(painel.btn_cancelar_exportacao.isEnabled(), "o cancelar morreu no trancamento")
        self.assertTrue(painel.isEnabled(), "o painel foi desabilitado em bloco")
        for acao in ("ler_melhor", "ler_pagina", "tirar_caixa", "selecionar_area"):
            with self.subTest(acao=acao):
                self.assertFalse(self.os_cinco(painel)[acao].isEnabled())  # type: ignore[attr-defined]

    def test_o_trancamento_apaga_a_navegacao_e_o_visor(self) -> None:
        """O que o `setEnabled` em bloco fazia antes, agora nomeado item a item."""
        painel = self.painel(com_livro=True)
        painel.trancar(False)
        self.assertFalse(painel._barra_de_navegacao.isEnabled())
        self.assertFalse(painel.visor.isEnabled())
        self.assertFalse(painel.deslizador.isEnabled())

        painel.trancar(True)
        self.assertTrue(painel._barra_de_navegacao.isEnabled())
        self.assertTrue(painel.visor.isEnabled())

    def test_os_dois_botoes_de_ocr_pedem_tetos_diferentes(self) -> None:
        """**A diferença que o porte tinha perdido.** "OCR melhor diagrama" e "OCR todos" eram o
        mesmo método, e dois botões vizinhos com rótulos diferentes fariam a mesma coisa."""
        painel = self.painel(com_livro=True)
        pedidos: list[bool] = []
        painel.leitura_pedida.connect(pedidos.append)

        painel.btn_ler_melhor.click()
        painel.btn_ler_pagina.click()

        self.assertEqual([True, False], pedidos)

    def test_exportar_e_cancelar_avisam_a_janela(self) -> None:
        """Quem exporta é o controlador da janela: este painel não conhece o serviço."""
        painel = self.painel(com_livro=True)
        painel.exportacao_em_curso(True)
        pedidos: list[str] = []
        painel.exportacao_pedida.connect(lambda: pedidos.append("comecar"))
        painel.exportacao_cancelada.connect(lambda: pedidos.append("cancelar"))

        painel.btn_cancelar_exportacao.click()
        painel.exportacao_em_curso(False)
        # **Começar a exportação é do menu `Arquivo` desde o F9-C2** (§7 item 11), e a janela a
        # liga pelo mesmo sinal: o que este teste afirma é que o painel avisa em vez de
        # exportar sozinho, e isso não depende de qual controle emite.
        painel.exportacao_pedida.emit()

        self.assertEqual(["cancelar", "comecar"], pedidos)

    def test_tirar_caixa_e_do_proprio_painel(self) -> None:
        """Ao contrário dos outros quatro, este não precisa da janela: a caixa é do visor."""
        painel = self.painel(com_livro=True)
        avisos: list[str] = []
        painel.estado.connect(avisos.append)

        painel.btn_tirar_caixa.click()

        self.assertTrue(avisos, "o botão não chegou a `dispensar_a_selecionada`")



@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DicaDoBotaoSoDeIconeTests(unittest.TestCase):
    """A dica do botão só-de-ícone diz o nome do **botão** quando ele é outro nome (F9-C6, item 2).

    O estado vazio da aba Resultado manda usar "OCR todos diagramas", que é como o comando
    `ler_pagina` se chama no botão. Na pele Foco isso está escrito na pílula; na clássica o botão
    é só-de-ícone, e **a dica é o único canal visual que sobra**. Sem o nome do botão nela, a frase
    manda procurar um texto que a tela não tem -- que é o defeito do §7.1 do ciclo 5 com o literal
    trocado.

    O oposto também é defeito: prefixar toda dica com o `rotulo_curto` põe `"- — Diminuir o zoom
    da página"` nos botões de zoom e repete `"Tirar a caixa"` antes de "Tirar a caixa do diagrama
    selecionado". Só um comando da barra tem dois nomes sem uma palavra em comum, e só ele precisa
    dos dois.
    """

    def test_o_comando_de_dois_nomes_traz_os_dois(self) -> None:
        dica = qt_pdf.PainelDoPdf._dica_do_comando("ler_pagina", so_icone=True)
        self.assertEqual("OCR todos diagramas — Ler esta página", dica)

    def test_um_glifo_nao_vira_nome(self) -> None:
        """`zoom_mais` mostra `+`: `"+ — Aumentar o zoom da página"` seria ruído."""
        for acao in ("zoom_mais", "zoom_menos"):
            with self.subTest(acao=acao):
                self.assertEqual(
                    comandos.rotulo(acao), qt_pdf.PainelDoPdf._dica_do_comando(acao, so_icone=True)
                )

    def test_um_encurtamento_nao_se_repete(self) -> None:
        """"Tirar a caixa" é o começo de "Tirar a caixa do diagrama selecionado"."""
        self.assertEqual(
            comandos.rotulo("tirar_caixa"),
            qt_pdf.PainelDoPdf._dica_do_comando("tirar_caixa", so_icone=True),
        )

    def test_o_botao_com_rotulo_visivel_nao_ganha_prefixo(self) -> None:
        """Quem mostra o nome não precisa repeti-lo na dica."""
        self.assertEqual(
            comandos.rotulo("ler_pagina"),
            qt_pdf.PainelDoPdf._dica_do_comando("ler_pagina", so_icone=False),
        )

    def test_a_regra_separa_nome_de_encurtamento(self) -> None:
        """O **controle** da regra, contra exemplos literais e não contra o catálogo de hoje."""
        self.assertTrue(qt_pdf._e_outro_nome("OCR todos diagramas", "Ler esta página"))
        self.assertFalse(qt_pdf._e_outro_nome("+", "Aumentar o zoom da página"))
        self.assertFalse(qt_pdf._e_outro_nome("Tirar a caixa", "Tirar a caixa do diagrama"))
        self.assertFalse(qt_pdf._e_outro_nome("Selecionar área (OCR)", "Selecionar área para ler"))


class NomeDoBotaoQuandoOCromoNaoODesenhaTests(unittest.TestCase):
    """A barra do visor escreve o nome que a pele corrente **não** escreve (F9-C7, §3).

    O ciclo 6 tentou fechar isto pela dica, e a dica não é a tela: na pele clássica -- a padrão --
    "OCR todos diagramas" era desenhado por **zero** controles visíveis, enquanto `MENSAGEM_VAZIA`
    mandava apertá-lo e `OCR melhor diagrama`, outro comando, estava em azul ao lado.

    Aqui se cobram os dois lados da regra: o nome aparece quando o cromo não o traz, e **não**
    aparece quando ele traz -- dois controles visíveis com o mesmo rótulo é o outro defeito.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not TEM_PYQT:  # pragma: no cover - venv sem binding
            raise unittest.SkipTest(MOTIVO)

    def setUp(self) -> None:
        self.app = aplicacao()
        self.painel = qt_pdf.PainelDoPdf(dpi=lambda: 200)
        self.addCleanup(descartar, self.painel)

    def _cromo(self, *rotulos: str):
        """Um contêiner com botões escritos, como a fila ou a fita entregam.

        **O método recebe o widget e não uma lista de nomes**, e é o item: uma lista seria uma
        segunda declaração de quem cada pele desenha, e ela divergiria do cromo no dia em que
        alguém tirasse um comando do destaque. O teste monta o widget pela mesma razão.
        """
        from PyQt6.QtWidgets import QPushButton, QWidget

        caixa = QWidget()
        self.addCleanup(descartar, caixa)
        for rotulo in rotulos:
            QPushButton(rotulo, caixa)
        return caixa

    def test_sem_o_nome_no_cromo_o_botao_o_desenha(self) -> None:
        nomeados = self.painel.nomear_o_que_o_cromo_nao_desenha(self._cromo())
        self.assertEqual(["ler_pagina"], nomeados)
        self.assertEqual("OCR todos diagramas", self.painel.btn_ler_pagina.text())

    def test_sem_cromo_nenhum_o_botao_o_desenha(self) -> None:
        """`None` é a pele clássica: ela não tem cromo acima do divisor, por decisão da S-221."""
        self.assertEqual(["ler_pagina"], self.painel.nomear_o_que_o_cromo_nao_desenha(None))
        self.assertEqual("OCR todos diagramas", self.painel.btn_ler_pagina.text())

    def test_com_o_nome_no_cromo_o_botao_fica_so_com_o_icone(self) -> None:
        """A pílula da Foco já o escreve: escrevê-lo de novo é duplicar um rótulo."""
        self.painel.nomear_o_que_o_cromo_nao_desenha(self._cromo("Abrir PDF", "OCR todos diagramas"))
        self.assertEqual("", self.painel.btn_ler_pagina.text())
        self.assertIn("OCR todos diagramas", self.painel.btn_ler_pagina.toolTip())

    def test_a_quebra_de_linha_da_fita_conta_como_o_mesmo_nome(self) -> None:
        """`quebrar_rotulo` desenha "OCR todos" + quebra + "diagramas" -- as mesmas palavras.

        Comparar o literal fazia a barra escrever o nome uma segunda vez na pele fita, que é a
        duplicação que esta regra existe para não criar. Medido: `text()` da fita a 1920.
        """
        self.painel.nomear_o_que_o_cromo_nao_desenha(self._cromo("OCR todos" + chr(10) + "diagramas"))
        self.assertEqual("", self.painel.btn_ler_pagina.text())

    def test_um_encurtamento_e_um_glifo_nao_ganham_texto(self) -> None:
        """Só o comando de **dois nomes** entra. Os outros já dizem o que são pelo ícone."""
        self.painel.nomear_o_que_o_cromo_nao_desenha(self._cromo())
        self.assertEqual("", self.painel.btn_tirar_caixa.text())
        self.assertEqual("", self.painel.btn_selecionar.text())

    def test_a_dica_deixa_de_repetir_o_nome_que_o_botao_mostra(self) -> None:
        """Quem mostra o nome não precisa dizê-lo duas vezes; quem não mostra, precisa."""
        self.painel.nomear_o_que_o_cromo_nao_desenha(self._cromo())
        self.assertNotIn("—", self.painel.btn_ler_pagina.toolTip())
        self.painel.nomear_o_que_o_cromo_nao_desenha(self._cromo("OCR todos diagramas"))
        self.assertIn("OCR todos diagramas — Ler esta página", self.painel.btn_ler_pagina.toolTip())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
