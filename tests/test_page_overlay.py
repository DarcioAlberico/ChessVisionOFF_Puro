"""Os diagramas marcados na página: geometria, alvo do clique e escolha da fonte (S-68).

Nenhum destes precisa de janela, e é esse o ponto: converter ponto de PDF em pixel de tela,
decidir qual retângulo o dedo acertou e decidir de onde vêm as caixas são as três coisas que
erram em silêncio -- o retângulo desenhado ao lado do diagrama parece certo até alguém
conferir, e o clique que abre o vizinho parece um erro de leitura do modelo.
"""

from __future__ import annotations

import unittest

import numpy as np

from chess_diagram_ocr.detection import DiagramCandidate
from chess_diagram_ocr.service import RecognizedDiagram
from chess_diagram_ocr.ui import page_overlay
from chess_diagram_ocr.ui.page_overlay import (
    BoxClick,
    DiagramBox,
    OverlayParams,
    PageBoxes,
    PageBoxesCache,
    boxes_from_candidates,
    boxes_from_diagrams,
    canvas_rect,
    choose_boxes,
    decide_box_click,
    hit_test,
    mark_confirmed,
    mark_saved,
    saved_on_page,
)

PARAMS = OverlayParams(dpi=144, max_boards=12)
"""144 DPI é o dobro de 72: escala 2 px por ponto, e as contas dos testes ficam exatas."""


def caixa(index: int, x0: float, y0: float, x1: float, y1: float, **campos: object) -> DiagramBox:
    return DiagramBox(index=index, bbox_pdf=(x0, y0, x1, y1), **campos)  # type: ignore[arg-type]


class GeometryTests(unittest.TestCase):
    def test_ponto_do_pdf_vira_pixel_de_tela_pelo_dpi_e_pelo_zoom(self) -> None:
        retangulo = canvas_rect(caixa(0, 10, 20, 110, 120), dpi=144, zoom=0.5)
        self.assertEqual(retangulo, (10.0, 20.0, 110.0, 120.0))

    def test_o_zoom_multiplica_e_o_dpi_tambem(self) -> None:
        """São dois fatores independentes: um é do render, o outro é da exibição."""
        self.assertEqual(canvas_rect(caixa(0, 0, 0, 72, 72), dpi=72, zoom=1.0), (0.0, 0.0, 72.0, 72.0))
        self.assertEqual(canvas_rect(caixa(0, 0, 0, 72, 72), dpi=220, zoom=1.0)[2], 220.0)
        self.assertEqual(canvas_rect(caixa(0, 0, 0, 72, 72), dpi=220, zoom=0.5)[2], 110.0)

    def test_o_dpi_vem_dos_parametros_da_caixa_e_nao_de_fora(self) -> None:
        """A caixa achada a 144 DPI se desenha a 144, mesmo que o campo da tela já diga 300."""
        pagina = PageBoxes(3, PARAMS, (caixa(0, 0, 0, 100, 100),))
        self.assertEqual(pagina.rect_of(pagina.boxes[0], 1.0), (0.0, 0.0, 200.0, 200.0))


class HitTestTests(unittest.TestCase):
    def setUp(self) -> None:
        # A moldura do exercício e o tabuleiro dentro dela -- o caso real do caminho por
        # contorno, em que as duas caixas contêm o mesmo clique.
        self.boxes = (caixa(0, 0, 0, 200, 200), caixa(1, 20, 20, 120, 120))

    def test_clique_fora_de_tudo_nao_acerta_ninguem(self) -> None:
        self.assertIsNone(hit_test(self.boxes, 900.0, 900.0, dpi=72, zoom=1.0))

    def test_a_menor_caixa_vence_o_empate(self) -> None:
        self.assertEqual(hit_test(self.boxes, 50.0, 50.0, dpi=72, zoom=1.0), 1)

    def test_fora_da_menor_ainda_acerta_a_maior(self) -> None:
        self.assertEqual(hit_test(self.boxes, 150.0, 150.0, dpi=72, zoom=1.0), 0)

    def test_o_alvo_acompanha_o_zoom(self) -> None:
        """Com metade do zoom, o mesmo diagrama está na metade das coordenadas."""
        self.assertIsNone(hit_test(self.boxes, 150.0, 150.0, dpi=72, zoom=0.5))
        self.assertEqual(hit_test(self.boxes, 75.0, 75.0, dpi=72, zoom=0.5), 0)

    def test_a_borda_conta_como_acerto(self) -> None:
        self.assertEqual(hit_test(self.boxes, 200.0, 200.0, dpi=72, zoom=1.0), 0)

    def test_lista_vazia_devolve_nada_em_vez_de_levantar(self) -> None:
        self.assertIsNone(hit_test((), 10.0, 10.0, dpi=72, zoom=1.0))


class BoxSourceTests(unittest.TestCase):
    def _candidato(self, bbox: tuple[float, float, float, float], source: str = "embedded") -> DiagramCandidate:
        return DiagramCandidate(
            board_rgb=np.zeros((8, 8, 3), dtype=np.uint8),
            bbox_pdf=bbox,
            source=source,  # type: ignore[arg-type]
            detector_score=0.9,
            native_size=(8, 8),
        )

    def _lido(self, bbox: tuple[float, float, float, float] | None) -> RecognizedDiagram:
        return RecognizedDiagram.from_label(
            np.zeros((8, 8, 3), dtype=np.uint8),
            "8/8/8/8/8/8/8/8",
            detection_source="contour",
            bbox_pdf=bbox,
        )

    def test_o_indice_da_caixa_e_a_ordem_do_detector(self) -> None:
        """Renumerar aqui faria o "3" do retângulo abrir outro diagrama no editor."""
        caixas = boxes_from_candidates(
            [self._candidato((0, 0, 10, 10)), self._candidato((0, 20, 10, 30))]
        )
        self.assertEqual([box.index for box in caixas], [0, 1])
        self.assertEqual(caixas[1].bbox_pdf, (0, 20, 10, 30))

    def test_caixa_do_detector_nao_se_diz_lida(self) -> None:
        caixas = boxes_from_candidates([self._candidato((0, 0, 10, 10))])
        self.assertFalse(caixas[0].recognized)
        self.assertEqual(caixas[0].source, "embedded")

    def test_diagrama_lido_vira_caixa_marcada_como_lida(self) -> None:
        caixas = boxes_from_diagrams([self._lido((1, 2, 3, 4))])
        self.assertTrue(caixas[0].recognized)
        self.assertEqual(caixas[0].bbox_pdf, (1, 2, 3, 4))

    def test_diagrama_sem_bbox_nao_vira_caixa(self) -> None:
        """Recorte de área e item da fila não sabem de que ponto da página vieram."""
        self.assertEqual(boxes_from_diagrams([self._lido(None)]), ())

    def test_o_indice_e_a_posicao_na_lista_do_editor(self) -> None:
        """`item.index` é 0 em tudo que veio de `from_label`; o seletor conta a posição."""
        caixas = boxes_from_diagrams([self._lido((0, 0, 1, 1)), self._lido((2, 2, 3, 3))])
        self.assertEqual([box.index for box in caixas], [0, 1])

    def test_o_rotulo_e_base_1_como_o_seletor(self) -> None:
        self.assertEqual(caixa(0, 0, 0, 1, 1).label, "1")


class MarkSavedTests(unittest.TestCase):
    """O carimbo do que já tem amostra gravada (S-71)."""

    def setUp(self) -> None:
        self.boxes = (caixa(0, 0, 0, 10, 10), caixa(1, 20, 0, 30, 10), caixa(2, 40, 0, 50, 10))

    def test_carimba_pelo_indice_do_diagrama(self) -> None:
        marcadas = mark_saved(self.boxes, {0, 2})
        self.assertEqual([box.saved for box in marcadas], [True, False, True])

    def test_nada_salvo_devolve_as_mesmas_caixas(self) -> None:
        self.assertEqual(mark_saved(self.boxes, set()), self.boxes)

    def test_salvo_e_independente_de_lido(self) -> None:
        """É a procedência do CSV que responde, não o que está em memória: o verde vale
        antes de qualquer OCR nesta sessão."""
        marcadas = mark_saved(self.boxes, {1})
        self.assertTrue(marcadas[1].saved)
        self.assertFalse(marcadas[1].recognized)

    def test_indice_salvo_que_nao_existe_mais_na_pagina_nao_atrapalha(self) -> None:
        """Trocar `Max diagramas` muda quantas caixas a página tem."""
        marcadas = mark_saved(self.boxes, {7})
        self.assertEqual([box.saved for box in marcadas], [False, False, False])


class SavedOnPageTests(unittest.TestCase):
    """A mesma pergunta do `mark_saved`, para a página inteira (S-451).

    Quem usa a resposta é o "Salvar todos", para perguntar antes de gravar a segunda cópia de uma
    página que já foi salva. O índice é o mesmo que pinta o verde, e é o ponto: a pergunta tem de
    concordar com a cor que o usuário está vendo.
    """

    INDICE = {16: {0, 2}}

    def test_responde_o_que_o_indice_tem_daquela_pagina(self) -> None:
        self.assertEqual(saved_on_page(self.INDICE, "livro.pdf", 16, source_pdf="livro.pdf"), {0, 2})

    def test_pagina_sem_nada_salvo_responde_vazio_e_nao_erro(self) -> None:
        self.assertEqual(saved_on_page(self.INDICE, "livro.pdf", 17, source_pdf="livro.pdf"), set())

    def test_perguntar_por_outro_livro_nao_responde_pelo_que_esta_aberto(self) -> None:
        """O editor pode estar mostrando o resultado de um PDF que a janela já fechou, e
        responder por ele faria a pergunta citar diagramas de outro livro."""
        self.assertEqual(saved_on_page(self.INDICE, "outro.pdf", 16, source_pdf="livro.pdf"), set())
        self.assertEqual(saved_on_page(self.INDICE, "", 16, source_pdf=""), set())

    def test_a_resposta_e_copia_e_nao_o_conjunto_do_indice(self) -> None:
        """Quem pergunta filtra a resposta; mexer nela não pode apagar o verde da página."""
        indice = {16: {0, 2}}
        saved_on_page(indice, "livro.pdf", 16, source_pdf="livro.pdf").clear()
        self.assertEqual(indice, {16: {0, 2}})

    def test_o_indice_concorda_com_o_que_o_mark_saved_pinta(self) -> None:
        """As duas leem o mesmo dicionário, e é isso que impede a pergunta e a cor divergirem."""
        boxes = (caixa(0, 0, 0, 10, 10), caixa(1, 20, 0, 30, 10), caixa(2, 40, 0, 50, 10))
        salvos = saved_on_page(self.INDICE, "livro.pdf", 16, source_pdf="livro.pdf")
        self.assertEqual([box.saved for box in mark_saved(boxes, salvos)], [True, False, True])


class PageDoneTests(unittest.TestCase):
    """"Esta página está terminada?" (S-142) -- a conta que o usuário fazia de cabeça sobre o
    verde que a S-71 pinta caixa a caixa."""

    def setUp(self) -> None:
        self.boxes = (caixa(0, 0, 0, 10, 10), caixa(1, 20, 0, 30, 10), caixa(2, 40, 0, 50, 10))

    def _pagina(self, salvos: set[int]) -> PageBoxes:
        return PageBoxes(7, PARAMS, mark_saved(self.boxes, salvos))

    def test_a_pagina_so_se_diz_concluida_quando_todo_diagrama_tem_amostra(self) -> None:
        self.assertTrue(self._pagina({0, 1, 2}).all_saved)
        self.assertFalse(self._pagina({0, 1}).all_saved, "faltando um, não está terminada")
        self.assertFalse(self._pagina(set()).all_saved)

    def test_pagina_vazia_nao_e_concluida_e_sim_vazia(self) -> None:
        """Mesma regra do `recognized`: "não há trabalho aqui" não é "o trabalho está feito"."""
        self.assertFalse(PageBoxes(7, PARAMS, ()).all_saved)

    def test_confirmado_pela_base_nao_conclui_a_pagina(self) -> None:
        """Violeta é "não precisa" (S-75), e uma página de confirmados não rendeu amostra."""
        pagina = PageBoxes(7, PARAMS, mark_confirmed(self.boxes, {0, 1, 2}))
        self.assertFalse(pagina.all_saved)

    def test_a_conclusao_nao_depende_de_a_pagina_ter_sido_lida(self) -> None:
        """Quem responde é o CSV: um livro trabalhado semanas atrás abre já concluído."""
        pagina = self._pagina({0, 1, 2})
        self.assertTrue(pagina.all_saved)
        self.assertFalse(pagina.recognized, "nenhuma destas caixas passou pelo OCR nesta sessão")


class ChooseBoxesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detectadas = tuple(caixa(i, i * 10, 0, i * 10 + 9, 9) for i in range(6))
        self.lidas = tuple(
            caixa(i, i * 10, 0, i * 10 + 9, 9, recognized=True) for i in range(6)
        )

    def test_o_reconhecimento_ganha_quando_cobre_o_que_o_detector_achou(self) -> None:
        escolhidas = choose_boxes(recognized=self.lidas, detected=self.detectadas)
        self.assertTrue(all(box.recognized for box in escolhidas))

    def test_uma_leitura_so_nao_apaga_as_seis_caixas_do_detector(self) -> None:
        """O caso do "OCR melhor diagrama": ele lê um, e o detector tinha achado seis."""
        escolhidas = choose_boxes(recognized=self.lidas[:1], detected=self.detectadas)
        self.assertEqual(len(escolhidas), 6)
        self.assertFalse(any(box.recognized for box in escolhidas))

    def test_sem_deteccao_guardada_o_reconhecimento_serve_sozinho(self) -> None:
        escolhidas = choose_boxes(recognized=self.lidas[:2], detected=())
        self.assertEqual(len(escolhidas), 2)

    def test_pagina_sem_nada_devolve_nada(self) -> None:
        self.assertEqual(choose_boxes(recognized=(), detected=()), ())

    def test_a_pagina_so_se_diz_reconhecida_quando_todas_as_caixas_sao(self) -> None:
        self.assertTrue(PageBoxes(0, PARAMS, self.lidas).recognized)
        self.assertFalse(PageBoxes(0, PARAMS, self.detectadas).recognized)
        self.assertFalse(PageBoxes(0, PARAMS, ()).recognized, "vazio não é reconhecido")


class ClickDecisionTests(unittest.TestCase):
    def test_diagrama_ja_lido_so_muda_a_selecao(self) -> None:
        self.assertIs(decide_box_click(recognized_count=6, index=2), BoxClick.SELECT)

    def test_pagina_nao_lida_manda_reconhecer(self) -> None:
        self.assertIs(decide_box_click(recognized_count=0, index=0), BoxClick.RECOGNIZE)

    def test_indice_alem_do_que_foi_lido_manda_reconhecer(self) -> None:
        """Selecionar o índice 4 de uma lista de 1 abriria um diagrama que não é o clicado."""
        self.assertIs(decide_box_click(recognized_count=1, index=4), BoxClick.RECOGNIZE)

    def test_indice_negativo_e_erro_de_programa_e_nao_um_terceiro_caso(self) -> None:
        with self.assertRaises(ValueError):
            decide_box_click(recognized_count=3, index=-1)


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache = PageBoxesCache(max_pages=3)
        self.caixas = (caixa(0, 0, 0, 10, 10),)

    def test_guarda_e_devolve_pela_chave_de_documento_e_pagina(self) -> None:
        self.cache.put("livro.pdf", PageBoxes(7, PARAMS, self.caixas))
        self.assertIsNotNone(self.cache.get("livro.pdf", 7, PARAMS))
        self.assertIsNone(self.cache.get("outro.pdf", 7, PARAMS))
        self.assertIsNone(self.cache.get("livro.pdf", 8, PARAMS))

    def test_parametro_diferente_e_descartado_e_nao_adaptado(self) -> None:
        """Caixa achada a 144 DPI redesenhada como se fosse de 300 aponta para o lugar errado."""
        self.cache.put("livro.pdf", PageBoxes(7, PARAMS, self.caixas))
        outros = OverlayParams(dpi=300, max_boards=PARAMS.max_boards)
        self.assertIsNone(self.cache.get("livro.pdf", 7, outros))
        self.assertNotIn(("livro.pdf", 7), self.cache)

    def test_max_boards_tambem_invalida(self) -> None:
        self.cache.put("livro.pdf", PageBoxes(7, PARAMS, self.caixas))
        self.assertIsNone(self.cache.get("livro.pdf", 7, OverlayParams(dpi=PARAMS.dpi, max_boards=1)))

    def test_pagina_sem_diagrama_e_uma_resposta_e_fica_guardada(self) -> None:
        """Senão o detector percorreria toda página de prosa de novo a cada volta."""
        self.cache.put("livro.pdf", PageBoxes(2, PARAMS, ()))
        guardado = self.cache.get("livro.pdf", 2, PARAMS)
        self.assertIsNotNone(guardado)
        self.assertEqual(len(guardado), 0)  # type: ignore[arg-type]

    def test_a_pagina_menos_visitada_sai_primeiro(self) -> None:
        for pagina in range(3):
            self.cache.put("livro.pdf", PageBoxes(pagina, PARAMS, self.caixas))
        self.cache.get("livro.pdf", 0, PARAMS)  # 0 volta a ser a mais recente
        self.cache.put("livro.pdf", PageBoxes(3, PARAMS, self.caixas))

        self.assertEqual(len(self.cache), 3)
        self.assertIn(("livro.pdf", 0), self.cache)
        self.assertNotIn(("livro.pdf", 1), self.cache)

    def test_limpar_esvazia(self) -> None:
        self.cache.put("livro.pdf", PageBoxes(1, PARAMS, self.caixas))
        self.cache.clear()
        self.assertEqual(len(self.cache), 0)


class NoTkinterTests(unittest.TestCase):
    def test_o_modulo_nao_importa_tkinter(self) -> None:
        """A mesma varredura do `editor_model` e do `board_model`, pelo mesmo motivo.

        É sobre a árvore de importação e não sobre o texto: o docstring do módulo fala do
        canvas, e um `assertNotIn` sobre o texto reprovaria a própria explicação.
        """
        import ast
        from pathlib import Path

        from chess_diagram_ocr.ui import page_overlay

        arvore = ast.parse(Path(page_overlay.__file__).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for node in ast.walk(arvore):
            if isinstance(node, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                importados.add(node.module.split(".")[0])

        self.assertNotIn("tkinter", importados)


class ConfirmadoPelaBaseTests(unittest.TestCase):
    """A quarta marca da caixa (S-75): "não precisa", que a tela não sabia dizer."""

    def _caixas(self) -> tuple[DiagramBox, ...]:
        return (
            DiagramBox(index=0, bbox_pdf=(0, 0, 10, 10)),
            DiagramBox(index=1, bbox_pdf=(20, 0, 30, 10)),
        )

    def test_carimba_so_o_indice_confirmado(self) -> None:
        caixas = mark_confirmed(self._caixas(), {1})
        self.assertFalse(caixas[0].confirmed)
        self.assertTrue(caixas[1].confirmed)

    def test_sem_confirmacao_devolve_as_mesmas_caixas(self) -> None:
        self.assertEqual(mark_confirmed(self._caixas(), set()), self._caixas())

    def test_confirmado_e_salvo_convivem(self) -> None:
        """Um diagrama pode ter as duas marcas: são perguntas independentes."""
        caixas = mark_confirmed(mark_saved(self._caixas(), {0}), {0})
        self.assertTrue(caixas[0].saved)
        self.assertTrue(caixas[0].confirmed)


class CanalRedundanteTests(unittest.TestCase):
    """A cor não é o único portador do estado (S-159).

    **O achado, com número.** Quatro estados, quatro matizes e mais nada -- nem forma, nem
    traço, nem letra. E o par mais crítico era o menos distinguível: azul `#4da3ff` contra
    violeta `#9b7bff` dá **1,20:1** de contraste entre si, separados essencialmente por matiz,
    numa linha de 2 px sobre página impressa hachurada.

    Para quem tem protanopia ou deuteranopia — **~8% dos homens** — "ainda a fazer" e "não
    precisa" eram o mesmo retângulo. E são justamente os dois cuja confusão custa trabalho:
    refazer o que já estava pronto, ou pular o que faltava.

    O critério de aceite da spec é objetivo: *os quatro estados são distinguíveis numa impressão
    em tons de cinza da captura de tela*. Em teste, isso é a **injetividade** do par (traço,
    glifo) — dois estados que compartilhassem os dois seriam indistinguíveis sem cor.
    """

    def _caixa(self, **estado: bool) -> page_overlay.DiagramBox:
        return page_overlay.DiagramBox(index=0, bbox_pdf=(0.0, 0.0, 10.0, 10.0), **estado)

    def test_a_tabela_e_total(self) -> None:
        """Um estado sem traço declarado cairia em `KeyError` no meio do desenho da página."""
        self.assertEqual(set(page_overlay.ESTADOS), set(page_overlay.TRACO_POR_ESTADO))

    def test_o_par_traco_glifo_e_injetivo(self) -> None:
        """A propriedade que faz o segundo canal ser um canal, e não enfeite."""
        assinaturas = [page_overlay.TRACO_POR_ESTADO[estado].assinatura for estado in page_overlay.ESTADOS]
        self.assertEqual(len(assinaturas), len(set(assinaturas)), "dois estados desenham igual sem a cor")

    def test_o_estado_sai_da_mesma_precedencia_da_cor(self) -> None:
        """Se as duas decisões divergissem, apareceria um retângulo verde tracejado de "dispensado"."""
        casos = {
            "a_fazer": self._caixa(),
            "lido": self._caixa(recognized=True),
            "dispensado": self._caixa(confirmed=True),
            "pronto": self._caixa(saved=True),
        }
        for esperado, caixa in casos.items():
            with self.subTest(estado=esperado):
                self.assertEqual(page_overlay.estado_da_caixa(caixa), esperado)

    def test_salvo_vence_confirmado_como_na_cor(self) -> None:
        """Salvo é trabalho **seu** já feito, e é o que interessa ver ao olhar a página."""
        caixa = self._caixa(saved=True, confirmed=True, recognized=True)
        self.assertEqual(page_overlay.estado_da_caixa(caixa), "pronto")

    def test_o_par_critico_se_distingue_sem_cor(self) -> None:
        """"A fazer" contra "não precisa": o par de 1,20:1, e o que custa confundir."""
        a_fazer = page_overlay.traco_da_caixa(self._caixa())
        dispensado = page_overlay.traco_da_caixa(self._caixa(confirmed=True))
        self.assertNotEqual(a_fazer.assinatura, dispensado.assinatura)
        self.assertNotEqual(a_fazer.tracejado, dispensado.tracejado, "os dois dependeriam do glifo sozinho")

    def test_so_o_estado_inicial_dispensa_glifo(self) -> None:
        """"Ainda não mexi nisto" é a ausência de marca, e marcar o nada é ruído em toda página."""
        sem_glifo = [estado for estado in page_overlay.ESTADOS if not page_overlay.TRACO_POR_ESTADO[estado].glifo]
        self.assertEqual(sem_glifo, ["a_fazer"])

    def test_toda_espessura_e_visivel(self) -> None:
        """Espessura zero seria um estado invisível -- o defeito, com outro nome."""
        for estado, traco in page_overlay.TRACO_POR_ESTADO.items():
            with self.subTest(estado=estado):
                self.assertGreaterEqual(traco.espessura, 1)

    def test_pronto_e_o_traco_mais_forte(self) -> None:
        """O estado que encerra o trabalho é o que se lê de longe, ao varrer a página."""
        espessuras = {estado: traco.espessura for estado, traco in page_overlay.TRACO_POR_ESTADO.items()}
        self.assertEqual(max(espessuras, key=lambda estado: espessuras[estado]), "pronto")


class DroppedBoxesTests(unittest.TestCase):
    """As caixas que o usuário tirou da página (S-177).

    O detector erra, e a caixa errada não é inerte: ela ocupa vaga do `max_boards`, entra na
    numeração que o `[Diagram "N"]` do PGN usa e, se for grande, esconde os diagramas de
    verdade debaixo dela. A única resposta antes disto era desligar a marcação da página
    inteira, que apaga junto o que estava certo.
    """

    def setUp(self) -> None:
        self.tiradas = page_overlay.DroppedBoxes()
        self.caixas = (
            caixa(0, 10, 10, 110, 110),
            caixa(1, 200, 10, 300, 110),
            caixa(2, 10, 200, 110, 300),
        )

    def test_a_caixa_tirada_some_e_as_outras_ficam(self) -> None:
        self.tiradas.drop("livro.pdf", 7, self.caixas[1].bbox_pdf)
        restantes = self.tiradas.apply("livro.pdf", 7, self.caixas)
        self.assertEqual([box.index for box in restantes], [0, 2])

    def test_o_que_sobra_nao_e_renumerado(self) -> None:
        """O índice liga o retângulo ao seletor "Selecionado" e ao `[Diagram "N"]` do PGN.

        Renumerar faria o clique no retângulo "2" abrir o diagrama 3 do editor -- o mesmo
        desencontro que a S-14 corrigiu entre a tela e o PGN, recriado entre a tela e ela mesma.
        """
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        restantes = self.tiradas.apply("livro.pdf", 7, self.caixas)
        self.assertEqual([box.index for box in restantes], [1, 2])
        self.assertEqual([box.label for box in restantes], ["2", "3"])

    def test_a_remocao_e_por_geometria_e_nao_por_indice(self) -> None:
        """É o que faz a remoção sobreviver ao OCR da página.

        As caixas do detector viram as do reconhecimento quando o OCR roda (`choose_boxes`), e
        as duas listas podem ter tamanhos diferentes -- é o caso do "OCR melhor diagrama". Uma
        remoção gravada por índice passaria a apagar outro diagrama.
        """
        self.tiradas.drop("livro.pdf", 7, self.caixas[2].bbox_pdf)
        # A mesma região, vinda da outra fonte e com outro índice: continua tirada.
        depois_do_ocr = (caixa(0, 12, 202, 108, 298, recognized=True),)
        self.assertEqual(self.tiradas.apply("livro.pdf", 7, depois_do_ocr), ())

    def test_uma_caixa_vizinha_nao_e_a_mesma_caixa(self) -> None:
        """Casar por geometria não pode virar casar por proximidade."""
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        self.assertEqual(
            [box.index for box in self.tiradas.apply("livro.pdf", 7, self.caixas)], [1, 2]
        )

    def test_cada_pagina_tem_as_suas(self) -> None:
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        self.assertEqual(len(self.tiradas.apply("livro.pdf", 8, self.caixas)), 3)

    def test_cada_livro_tem_as_suas(self) -> None:
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        self.assertEqual(len(self.tiradas.apply("outro.pdf", 7, self.caixas)), 3)

    def test_tirar_a_mesma_caixa_duas_vezes_nao_a_duplica(self) -> None:
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        self.assertEqual(self.tiradas.count("livro.pdf", 7), 1)

    def test_devolver_traz_de_volta_a_pagina_inteira(self) -> None:
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        self.tiradas.drop("livro.pdf", 7, self.caixas[1].bbox_pdf)
        self.assertEqual(self.tiradas.restore("livro.pdf", 7), 2)
        self.assertEqual(len(self.tiradas.apply("livro.pdf", 7, self.caixas)), 3)

    def test_devolver_nao_alcanca_outra_pagina(self) -> None:
        """Desfazer noutra página mudaria o que o usuário não está vendo."""
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        self.tiradas.drop("livro.pdf", 8, self.caixas[0].bbox_pdf)
        self.tiradas.restore("livro.pdf", 7)
        self.assertEqual(self.tiradas.count("livro.pdf", 8), 1)

    def test_devolver_pagina_sem_remocao_devolve_zero(self) -> None:
        self.assertEqual(self.tiradas.restore("livro.pdf", 7), 0)

    def test_uma_pagina_sem_remocao_devolve_a_mesma_tupla(self) -> None:
        """O caminho comum é não haver remoção nenhuma, e ele não pode custar nada."""
        self.assertEqual(self.tiradas.apply("livro.pdf", 7, self.caixas), self.caixas)

    def test_o_limiar_e_o_mesmo_do_field_eval(self) -> None:
        """Um número só decide "a mesma caixa" na tela e na avaliação (S-77).

        Usar outro aqui faria o visualizador chamar de "a mesma caixa" o que a avaliação conta
        como duas -- e a remoção passaria a apagar um diagrama que a métrica ainda cobra.
        """
        from chess_diagram_ocr.field_eval import MATCH_IOU

        self.assertEqual(page_overlay.DroppedBoxes().same_box_iou, MATCH_IOU)

    def test_esquecer_tudo_ao_trocar_de_livro(self) -> None:
        self.tiradas.drop("livro.pdf", 7, self.caixas[0].bbox_pdf)
        self.tiradas.clear()
        self.assertEqual(len(self.tiradas), 0)


class FrasesDaRemocaoTests(unittest.TestCase):
    """O que a barra de status diz ao tirar e ao devolver uma caixa (S-177).

    Aqui pelo mesmo motivo que as três descrições do `rodape`: é decisão de texto e é pura, e
    afirmar "a frase nomeia o caminho de volta" não deveria exigir uma janela aberta.
    """

    def test_a_frase_nomeia_a_caixa_que_saiu(self) -> None:
        frase = page_overlay.frase_de_caixa_tirada(caixa(0, 0, 0, 10, 10), 1)
        self.assertIn("Caixa 1", frase, "a frase precisa dizer qual retângulo saiu")

    def test_a_frase_diz_quantas_ja_sairam_desta_pagina(self) -> None:
        """Sem o total, tirar cinco caixas por engano é invisível até virar a página."""
        self.assertIn("1 caixa tirada", page_overlay.frase_de_caixa_tirada(caixa(0, 0, 0, 1, 1), 1))
        self.assertIn("3 caixas tiradas", page_overlay.frase_de_caixa_tirada(caixa(2, 0, 0, 1, 1), 3))

    def test_a_frase_nomeia_os_dois_caminhos_a_partir_dali(self) -> None:
        """Ação destrutiva que não nomeia a volta obriga a procurá-la depois de já ter perdido."""
        frase = page_overlay.frase_de_caixa_tirada(caixa(0, 0, 0, 1, 1), 1)
        self.assertIn("Selecionar área (OCR)", frase)
        self.assertIn("Devolver as caixas tiradas", frase)

    def test_caixa_que_ja_nao_esta_na_pagina_tem_frase_propria(self) -> None:
        self.assertEqual(
            page_overlay.frase_de_caixa_tirada(None, 0), "Essa caixa não está mais na página."
        )

    def test_devolver_concorda_em_numero(self) -> None:
        self.assertIn("1 caixa devolvida", page_overlay.frase_de_caixas_devolvidas(1, 14))
        self.assertIn("2 caixas devolvidas", page_overlay.frase_de_caixas_devolvidas(2, 14))

    def test_devolver_zero_nao_afirma_que_houve_devolucao(self) -> None:
        """"0 caixas devolvidas" afirma um evento que não aconteceu."""
        self.assertEqual(
            page_overlay.frase_de_caixas_devolvidas(0, 14), "Nenhuma caixa foi tirada desta página."
        )


if __name__ == "__main__":
    unittest.main()
