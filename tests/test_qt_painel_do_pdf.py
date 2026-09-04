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
6. **A folha fica no meio da área visível** (S-157): no Tk era uma conta de `ui/viewport.py`,
   aqui é uma propriedade do `QScrollArea` -- e a conta saiu na triagem da S-511.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import leitura_do_pdf
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
        self.assertEqual(painel.lbl_pdf.text(), "nenhum PDF aberto")
        self.assertFalse(painel.btn_leitor.isEnabled())
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

    def test_o_modo_de_selecao_troca_o_rotulo_do_botao(self) -> None:
        """"Selecionar área" é um modo, e ligar e desligar não podem ter a mesma aparência (S-396)."""
        from chess_diagram_ocr.ui import comandos

        painel = self.com_pagina()
        self.assertEqual(painel.btn_selecionar.text(), comandos.rotulo_de_botao("selecionar_area"))
        painel.alternar_selecao()
        self.assertEqual(painel.btn_selecionar.text(), comandos.rotulo_alternado("selecionar_area"))
        painel.alternar_selecao()
        self.assertEqual(painel.btn_selecionar.text(), comandos.rotulo_de_botao("selecionar_area"))

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

    def test_a_pagina_fica_no_meio_da_area_visivel(self) -> None:
        """A decisão da S-157, que no Tk era uma conta e aqui é uma propriedade do `QScrollArea`.

        `desvio_de_centralizacao` e `regiao_de_rolagem` saíram de `ui/viewport.py` na triagem da
        S-511 porque o Qt centraliza sozinho -- e esta é a guarda que ficou no lugar delas: sem o
        `setAlignment`, a folha volta ao canto superior esquerdo e, a 40% de zoom numa janela de
        1700, ~45% da vista vira vazio.
        """
        from PyQt6.QtCore import Qt

        painel = self.com_pagina()
        self.assertEqual(painel.visor.alignment(), Qt.AlignmentFlag.AlignCenter)


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
            "exportar_pgn": painel.btn_exportar,
            "cancelar_exportacao": painel.btn_cancelar_exportacao,
        }

    def test_os_cinco_tiram_o_rotulo_do_catalogo(self) -> None:
        """Nenhum texto escrito aqui: é a regra da S-324, e `test_ui_comandos` a varre por `ast`."""
        from chess_diagram_ocr.ui import comandos

        painel = self.painel()
        for acao, botao in self.os_cinco(painel).items():
            with self.subTest(acao=acao):
                self.assertEqual(comandos.rotulo_de_botao(acao), botao.text())  # type: ignore[attr-defined]

    def test_sem_livro_os_cinco_ficam_cinza(self) -> None:
        """A pré-condição é a mesma do "Abrir no leitor": não há página sobre a qual agir."""
        painel = self.painel()
        for acao, botao in self.os_cinco(painel).items():
            with self.subTest(acao=acao):
                self.assertFalse(botao.isEnabled())  # type: ignore[attr-defined]

    def test_com_livro_acendem_quatro_e_o_cancelar_continua_cinza(self) -> None:
        """O cancelar não depende de haver livro, e sim de haver exportação."""
        painel = self.painel(com_livro=True)
        for acao in ("ler_melhor", "ler_pagina", "tirar_caixa", "exportar_pgn"):
            with self.subTest(acao=acao):
                self.assertTrue(self.os_cinco(painel)[acao].isEnabled())  # type: ignore[attr-defined]
        self.assertFalse(painel.btn_cancelar_exportacao.isEnabled())

    def test_a_exportacao_troca_o_par_exportar_cancelar(self) -> None:
        """Uma por vez: enquanto uma roda, começar outra não é oferta."""
        painel = self.painel(com_livro=True)
        painel.exportacao_em_curso(True)
        self.assertFalse(painel.btn_exportar.isEnabled())
        self.assertTrue(painel.btn_cancelar_exportacao.isEnabled())

        painel.exportacao_em_curso(False)
        self.assertTrue(painel.btn_exportar.isEnabled())
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
        for acao in ("ler_melhor", "ler_pagina", "tirar_caixa", "exportar_pgn"):
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
        painel.btn_exportar.click()

        self.assertEqual(["cancelar", "comecar"], pedidos)

    def test_tirar_caixa_e_do_proprio_painel(self) -> None:
        """Ao contrário dos outros quatro, este não precisa da janela: a caixa é do visor."""
        painel = self.painel(com_livro=True)
        avisos: list[str] = []
        painel.estado.connect(avisos.append)

        painel.btn_tirar_caixa.click()

        self.assertTrue(avisos, "o botão não chegou a `dispensar_a_selecionada`")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
