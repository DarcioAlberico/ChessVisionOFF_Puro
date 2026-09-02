"""A versão de teste em PyQt6, exercitada sem tela (S-500).

**O que estes testes cobrem, e o que não.** As decisões que a versão de teste **reusa** já são
afirmadas onde moram: `tests/test_page_overlay.py` responde por onde estão as caixas e por qual
delas um clique acerta, `tests/test_viewport.py` pela roda e pelo zoom. Repetir aquilo aqui
mediria o mesmo código duas vezes. O que só existe aqui é a **ponte** -- fração do `yview` do
Tk a partir de um `QScrollBar`, campo de peças virando pixel, e a janela ligando um painel ao
outro -- e é isso que está abaixo.

A janela recebe o serviço pronto (`servico=`), e é o que permite exercitar o caminho de leitura
inteiro sem o `models/piece_classifier.pt`, que não é versionado: um teste que dependesse dele
pularia em toda corrida de CI, que é o defeito que a S-417 nomeia.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import cv2
import fitz
import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, esperar

from chess_diagram_ocr.detection import DiagramCandidate
from chess_diagram_ocr.fen_utils import check_position
from chess_diagram_ocr.labels import DatasetEntry, LabelStore
from chess_diagram_ocr.semantics import compose_fen
from chess_diagram_ocr.service import RecognizedDiagram

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
LADO_DO_TABULEIRO = 320
CAIXA_NO_PDF = (60.0, 60.0, 260.0, 260.0)
"""Onde o diagrama sintético fica na página, em pontos do PDF."""


def tabuleiro_sintetico(lado: int = LADO_DO_TABULEIRO) -> np.ndarray:
    """Um xadrez de 8x8 com moldura. Basta para o detector de imagem embutida achá-lo."""
    imagem = np.full((lado, lado, 3), 255, np.uint8)
    casa = lado // 8
    for linha in range(8):
        for coluna in range(8):
            if (linha + coluna) % 2:
                imagem[linha * casa : (linha + 1) * casa, coluna * casa : (coluna + 1) * casa] = 150
    cv2.rectangle(imagem, (0, 0), (lado - 1, lado - 1), (0, 0, 0), 3)
    return imagem


def pdf_de_teste(destino: Path, *, paginas: int = 1) -> Path:
    """Um PDF com um diagrama embutido por página.

    Gerado em memória e não versionado, pelo mesmo motivo de `tests/test_detection.py`: o
    repositório não versiona PDF, e um tabuleiro sintético exercita o mesmo caminho.
    """
    ok, buffer = cv2.imencode(".png", cv2.cvtColor(tabuleiro_sintetico(), cv2.COLOR_RGB2BGR))
    if not ok:  # pragma: no cover - o OpenCV não falha ao codificar PNG de um array válido
        raise RuntimeError("Falha ao codificar o PNG do fixture.")
    documento = fitz.open()
    for numero in range(paginas):
        pagina = documento.new_page(width=400, height=500)
        pagina.insert_image(fitz.Rect(*CAIXA_NO_PDF), stream=buffer.tobytes())
        pagina.insert_text((60, 300), f"Diagrama {numero + 1}")
    documento.save(str(destino))
    documento.close()
    return destino


def _candidato_qualquer() -> DiagramCandidate:
    """Um candidato do detector, montado à mão. Serve para o teste da conferência de página."""
    return DiagramCandidate(
        board_rgb=tabuleiro_sintetico(64),
        bbox_pdf=CAIXA_NO_PDF,
        source="embedded",
        detector_score=1.0,
        native_size=(LADO_DO_TABULEIRO, LADO_DO_TABULEIRO),
    )


def diagrama_lido(indice: int, placement: str = INICIAL) -> RecognizedDiagram:
    """Um `RecognizedDiagram` como o serviço o devolveria, sem rodar o modelo."""
    return RecognizedDiagram(
        index=indice,
        board_rgb=tabuleiro_sintetico(64),
        placement=placement,
        min_confidence=0.97,
        mean_confidence=0.99,
        uncertain_squares=[12],
        legality=check_position(compose_fen(placement, True)),
        bbox_pdf=CAIXA_NO_PDF,
        detection_source="embedded",
    )


class ServicoComLeituraFixa:
    """O serviço com a leitura combinada, e o resto delegado ao de verdade.

    Herdar seria mais curto e seria pior: `OcrService.__init__` guarda um caminho de modelo, e
    um teste que herda passa a depender de o construtor continuar não tocando no disco. Aqui a
    superfície usada pela janela está escrita -- as quatro coisas que ela chama, e nada mais.
    """

    def __init__(self, itens: list[RecognizedDiagram]) -> None:
        from chess_diagram_ocr.service import OcrService

        self._real = OcrService()
        self.itens = itens
        self.paginas_lidas: list[int] = []
        self.candidatos_recebidos: list[object] = []
        """O que chegou em `candidates=` a cada leitura. `None` é o caminho de sempre, em que
        o serviço detecta por conta própria."""

    def page_count(self, pdf_source: object) -> int:
        return self._real.page_count(pdf_source)

    def render_page(self, pdf_source: object, page_index: int, *, dpi: int) -> np.ndarray:
        return self._real.render_page(pdf_source, page_index, dpi=dpi)

    def recognize_page(
        self,
        pdf_source: object,
        page_index: int,
        page_rgb: object = None,
        *,
        options: object,
        candidates: object = None,
    ) -> list[RecognizedDiagram]:
        self.paginas_lidas.append(page_index)
        self.candidatos_recebidos.append(candidates)
        return list(self.itens)

    @property
    def device(self) -> str | None:
        return None

    @property
    def device_label(self) -> str:
        return "nenhum modelo carregado"


def _renderizar(widget: object, lado: int = 320):
    """O widget desenhado num `QImage`, para o teste poder afirmar o que apareceu na tela."""
    from PyQt6.QtGui import QImage, QPainter

    imagem = QImage(lado, lado, QImage.Format.Format_RGB888)
    imagem.fill(0)
    pintor = QPainter(imagem)
    widget.render(pintor)  # type: ignore[attr-defined]
    pintor.end()
    return imagem


def _centro_da_casa(tabuleiro: object, linha: int, coluna: int) -> tuple[int, int]:
    """O centro de uma casa em pixels do widget, para amostrar a cor ali.

    Calculado e não cravado: o canto de uma casa cai fora do desenho da peça -- a primeira
    versão deste teste amostrava (40, 40) e comparava dois pixels de fundo, passando a afirmar
    que virar o tabuleiro não muda nada.

    **E perguntado ao widget, e não refeito aqui** (S-501). A segunda versão recalculava a partir
    de `MARGEM`, e isso deixou de bater quando o tabuleiro passou a enquadrar com
    `BoardGeometry.fit` -- a mesma conta do produto. Um teste que refaz a geometria do widget
    afirma a conta dele contra uma cópia da conta dele.
    """
    geo = tabuleiro.geometria()  # type: ignore[attr-defined]
    x0, y0, x1, y1 = geo.rect(linha, coluna)
    return (int((x0 + x1) / 2), int((y0 + y1) / 2))


class FracoesDaVistaTests(unittest.TestCase):
    """A tradução `QScrollBar` -> `yview`, que é o que decide a virada de página.

    Não precisa de Qt: são três inteiros entrando e dois floats saindo, e é justamente por isso
    que a regra continua afirmável sem abrir janela.
    """

    def setUp(self) -> None:
        if not TEM_PYQT:
            self.skipTest(MOTIVO)

    def test_conteudo_que_cabe_inteiro_esta_no_comeco_e_no_fim(self) -> None:
        from chess_diagram_ocr.qt.visor import fracoes_da_vista

        self.assertEqual((0.0, 1.0), fracoes_da_vista(0, 500, 0))

    def test_no_topo_o_primeiro_e_zero(self) -> None:
        from chess_diagram_ocr.qt.visor import fracoes_da_vista

        primeiro, ultimo = fracoes_da_vista(0, 100, 300)
        self.assertEqual(0.0, primeiro)
        self.assertLess(ultimo, 1.0)

    def test_no_fim_o_ultimo_e_um(self) -> None:
        """O `maximum` do Qt é o topo da última vista, e não o fim do conteúdo.

        Sem o `+ passo`, a última página pareceria ter chegado ao fim uma tela antes -- e a
        roda viraria a página no meio do último diagrama.
        """
        from chess_diagram_ocr.qt.visor import fracoes_da_vista

        self.assertEqual(1.0, fracoes_da_vista(300, 100, 300)[1])

    def test_barra_sem_passo_nao_divide_por_zero(self) -> None:
        from chess_diagram_ocr.qt.visor import fracoes_da_vista

        self.assertEqual((0.0, 1.0), fracoes_da_vista(0, 0, 0))


class TabuleiroTests(unittest.TestCase):
    """O campo de peças da FEN virando pixel."""

    def setUp(self) -> None:
        aplicacao()
        from chess_diagram_ocr.qt.tabuleiro import TabuleiroQt

        self.tabuleiro = TabuleiroQt()
        self.addCleanup(self.tabuleiro.deleteLater)
        self.tabuleiro.resize(320, 320)

    def test_fen_invalida_levanta_em_vez_de_virar_tabuleiro_vazio(self) -> None:
        """Mesma decisão da S-361: 64 casas vazias é indistinguível de uma posição sem peças,
        e quem olha a tela concluiria que o modelo não achou nada."""
        with self.assertRaises(ValueError):
            self.tabuleiro.mostrar("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNX")

    def test_as_casas_incertas_ficam_e_as_de_fora_da_faixa_caem(self) -> None:
        self.tabuleiro.mostrar(INICIAL, incertas=[0, 63, 64, -1])
        self.assertEqual((0, 63), self.tabuleiro.casas_incertas())

    def test_a_posicao_inicial_pinta_alguma_coisa_a_mais_que_o_tabuleiro_vazio(self) -> None:
        self.tabuleiro.mostrar("8/8/8/8/8/8/8/8")
        vazio = _renderizar(self.tabuleiro)
        self.tabuleiro.mostrar(INICIAL)
        self.assertNotEqual(vazio, _renderizar(self.tabuleiro))

    def test_virar_leva_a_peca_do_canto_de_cima_para_o_canto_de_baixo(self) -> None:
        """Uma torre em a8, sozinha: em pé ela aparece em cima à esquerda, virada em baixo à
        direita. É a inversão do índice de leitura, medida onde ela importa -- na tela."""
        canto_de_cima = _centro_da_casa(self.tabuleiro, 0, 0)
        canto_de_baixo = _centro_da_casa(self.tabuleiro, 7, 7)
        self.tabuleiro.mostrar("8/8/8/8/8/8/8/8")
        vazio = _renderizar(self.tabuleiro)

        self.tabuleiro.mostrar("R7/8/8/8/8/8/8/8")
        em_pe = _renderizar(self.tabuleiro)
        self.assertNotEqual(vazio.pixel(*canto_de_cima), em_pe.pixel(*canto_de_cima))
        self.assertEqual(vazio.pixel(*canto_de_baixo), em_pe.pixel(*canto_de_baixo))

        self.tabuleiro.mostrar("R7/8/8/8/8/8/8/8", virado=True)
        virado = _renderizar(self.tabuleiro)
        self.assertEqual(vazio.pixel(*canto_de_cima), virado.pixel(*canto_de_cima))
        self.assertNotEqual(vazio.pixel(*canto_de_baixo), virado.pixel(*canto_de_baixo))

    def test_sem_os_png_das_pecas_o_tabuleiro_ainda_desenha_a_peca(self) -> None:
        """`assets/piece_images/` não é obrigatório, e um tabuleiro em branco não diria se o
        que faltou foi a leitura ou a imagem."""
        from chess_diagram_ocr.qt.tabuleiro import TabuleiroQt

        sem_pecas = TabuleiroQt(pasta_de_pecas=Path("pasta/que/nao/existe"))
        self.addCleanup(sem_pecas.deleteLater)
        sem_pecas.resize(320, 320)
        sem_pecas.mostrar("8/8/8/8/8/8/8/8")
        vazio = _renderizar(sem_pecas)
        sem_pecas.mostrar(INICIAL)
        self.assertNotEqual(vazio, _renderizar(sem_pecas))


class VisorTests(unittest.TestCase):
    """A folha, o zoom e o clique que vira índice de diagrama."""

    def setUp(self) -> None:
        aplicacao()
        from chess_diagram_ocr.qt.visor import VisorDePagina

        self.visor = VisorDePagina()
        self.addCleanup(self.visor.deleteLater)
        self.visor.resize(400, 500)
        # **`show()` não é enfeite aqui**: o `QScrollArea` só recalcula a faixa das barras
        # quando é exibido, e sem isso `maximum()` fica em 0 -- o teste de zoom ancorado
        # mediria uma página que não rola, que é justamente o caso em que o defeito não
        # aparece. Com a plataforma `offscreen` do `tests/qt_app.py`, nada vai para a tela.
        self.visor.show()
        self.pagina = np.full((1000, 800, 3), 240, np.uint8)

    def _caixas(self):
        from chess_diagram_ocr.ui.page_overlay import DiagramBox, OverlayParams, PageBoxes

        return PageBoxes(
            0,
            OverlayParams(dpi=220, max_boards=12),
            (DiagramBox(index=0, bbox_pdf=CAIXA_NO_PDF, source="embedded"),),
        )

    def test_a_folha_fica_do_tamanho_da_pagina_vezes_o_zoom(self) -> None:
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.visor.definir_zoom(0.5)
        folha = self.visor.widget()
        self.assertEqual((400, 500), (folha.width(), folha.height()))

    def test_ajustar_a_pagina_cabe_nos_dois_eixos(self) -> None:
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.visor.ajustar_a_pagina()
        folha = self.visor.widget()
        self.assertLessEqual(folha.width(), self.visor.viewport().width())
        self.assertLessEqual(folha.height(), self.visor.viewport().height())

    def test_o_clique_dentro_da_caixa_diz_qual_diagrama_e(self) -> None:
        recebidos: list[int] = []
        self.visor.caixa_clicada.connect(recebidos.append)
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.visor.definir_caixas(self._caixas())

        # O centro da caixa em pixels de tela: ponto do PDF x dpi/72 x zoom.
        centro = 160.0 * (220.0 / 72.0) * self.visor.zoom
        self.visor.clicar_em(centro, centro)
        self.assertEqual([0], recebidos)

    def test_o_clique_fora_das_caixas_nao_diz_nada(self) -> None:
        recebidos: list[int] = []
        self.visor.caixa_clicada.connect(recebidos.append)
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.visor.definir_caixas(self._caixas())

        self.visor.clicar_em(5.0, 5.0)
        self.assertEqual([], recebidos)

    def test_com_as_caixas_escondidas_o_clique_nao_abre_diagrama(self) -> None:
        """Esconder as caixas esconde também o que elas fazem: um clique que abre um diagrama
        invisível é um clique que a pessoa não tem como ter pedido."""
        recebidos: list[int] = []
        self.visor.caixa_clicada.connect(recebidos.append)
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.visor.definir_caixas(self._caixas())
        self.visor.alternar_caixas(False)

        self.visor.clicar_em(160.0 * (220.0 / 72.0), 160.0 * (220.0 / 72.0))
        self.assertEqual([], recebidos)

    def _girar(self, ponto_na_folha: tuple[int, int], *, com_ctrl: bool, para_baixo: bool = True):
        """Um giro de roda sobre um ponto da folha -- que é o widget que o recebe de verdade."""
        from PyQt6.QtCore import QPoint, QPointF, Qt
        from PyQt6.QtGui import QWheelEvent

        posicao = QPointF(*ponto_na_folha)
        return QWheelEvent(
            posicao,
            posicao,
            QPoint(0, 0),
            QPoint(0, -120 if para_baixo else 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier if com_ctrl else Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    def test_o_zoom_com_ctrl_deixa_parado_o_ponto_sob_o_ponteiro(self) -> None:
        """**O defeito que isto pega**: a primeira versão somava o valor da barra ao ponteiro,
        que já vinha em coordenadas da folha -- a rolagem entrava duas vezes, e o zoom pulava
        para longe do ponto justamente quando a página estava rolada, que é sempre.

        A régua é o ponto da **página** (em pixels de render, independentes do zoom) que fica
        sob o ponteiro: ele tem de ser o mesmo antes e depois.
        """
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.visor.definir_zoom(1.0)
        barra = self.visor.verticalScrollBar()
        barra.setValue(300)
        folha = self.visor.widget()

        na_janela = 120
        antes = (barra.value() + na_janela) / self.visor.zoom
        self.visor.girar_roda(self._girar((60, na_janela - folha.pos().y()), com_ctrl=True, para_baixo=False))
        depois = (self.visor.verticalScrollBar().value() + na_janela) / self.visor.zoom

        self.assertGreater(self.visor.zoom, 1.0)
        self.assertAlmostEqual(antes, depois, delta=2.0)

    def test_a_roda_sem_ctrl_no_meio_da_pagina_rola_em_vez_de_virar(self) -> None:
        pedidos: list[int] = []
        self.visor.pagina_pedida.connect(pedidos.append)
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.visor.definir_zoom(2.0)
        barra = self.visor.verticalScrollBar()
        barra.setValue(barra.maximum() // 2)

        self.visor.girar_roda(self._girar((10, 10), com_ctrl=False))
        self.assertEqual([], pedidos)
        self.assertGreater(barra.value(), barra.maximum() // 2)

    def test_trocar_de_pagina_derruba_as_caixas_da_anterior(self) -> None:
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.visor.definir_caixas(self._caixas())
        self.visor.mostrar_pagina(self.pagina, dpi=220)
        self.assertIsNone(self.visor.caixas)


class JanelaTests(unittest.TestCase):
    """A janela inteira: abrir, navegar, marcar, ler e selecionar."""

    def setUp(self) -> None:
        aplicacao()
        self.pasta = pasta_temporaria(self)
        self.pdf = pdf_de_teste(self.pasta / "livro.pdf")
        self.csv = self.pasta / "labels.csv"

    def _janela(self, servico: object = None):
        from chess_diagram_ocr.qt.janela import JanelaPrincipal

        janela = JanelaPrincipal(
            motor=None,  # a suíte não procura binário na máquina de quem a roda (S-523)
            servico=servico,  # type: ignore[arg-type]
            csv_de_rotulos=self.csv,
            # **Sem isto o teste grava o estado da máquina de quem roda a suíte**: o
            # `addCleanup(janela.close)` abaixo dispara o `closeEvent`, que grava.
            caminho_do_estado=self.pasta / "janela.json",
        )
        self.addCleanup(janela.deleteLater)
        self.addCleanup(janela.close)
        janela.resize(1000, 700)
        return janela

    def test_o_titulo_diz_qual_das_duas_janelas_e_esta(self) -> None:
        """Duas janelas do mesmo produto abertas lado a lado é a situação em que se corrige
        vinte diagramas na janela errada.

        **A marca ficou mais necessária quando esta janela passou a gravar** (S-502): enquanto
        ela era somente-leitura, errar de janela custava um gesto perdido; agora as duas
        escrevem no mesmo `labels.csv`. O que o título dizia -- "versão de teste" -- passou a
        ser falso, e o que ele precisa dizer é qual janela é esta.
        """
        from chess_diagram_ocr.qt.janela import TITULO_DE_TESTE

        janela = self._janela()
        self.assertIn(TITULO_DE_TESTE, janela.windowTitle())
        self.assertNotIn("versão de teste", janela.windowTitle(), "o título ficou desatualizado")

    def test_abrir_o_livro_diz_o_nome_a_pagina_e_o_total(self) -> None:
        janela = self._janela()
        janela.abrir_pdf(self.pdf)

        self.assertIn("livro.pdf", janela.windowTitle())
        self.assertIn("p. 1 de 1", janela.rodape.documento())
        self.assertEqual(1, janela.pdf.campo_pagina.maximum())

    def test_pagina_fora_da_faixa_nao_mexe_na_tela(self) -> None:
        janela = self._janela()
        janela.abrir_pdf(self.pdf)
        janela.pdf.ir_para_pagina(7)
        self.assertEqual(1, janela.pdf.campo_pagina.value())

    def test_um_pdf_que_nao_abre_nao_deixa_a_janela_apontando_para_ele(self) -> None:
        from unittest import mock

        janela = self._janela()
        quebrado = self.pasta / "quebrado.pdf"
        quebrado.write_bytes(b"isto nao e um PDF")
        # A caixa modal é trocada aqui pelo mesmo motivo do `conftest`: uma caixa de verdade
        # deixa a suíte parada esperando um clique que ninguém vai dar.
        with mock.patch("chess_diagram_ocr.qt.janela.QMessageBox.critical") as caixa:
            janela.abrir_pdf(quebrado)

        self.assertTrue(caixa.called)
        self.assertIsNone(janela.pdf.visor.pagina_rgb())

    def test_marcar_diagramas_desenha_a_caixa_que_o_detector_achou(self) -> None:
        """O caminho de detecção de verdade -- render, detector híbrido, caixas -- sem modelo."""
        janela = self._janela()
        janela.abrir_pdf(self.pdf)
        janela.marcar_diagramas()
        esperar(janela)

        caixas = janela.pdf.visor.caixas
        self.assertIsNotNone(caixas)
        assert caixas is not None
        self.assertEqual(1, len(caixas))
        self.assertEqual("embedded", caixas.boxes[0].source)
        self.assertIn("1 diagrama(s)", janela.rodape.documento())

    def test_o_diagrama_ja_salvo_no_csv_aparece_marcado_antes_de_qualquer_ocr(self) -> None:
        """É a pergunta "onde eu parei neste livro?" (S-71), e ela se responde sem ler nada.

        O CSV conta em base 1 e a tela em base 0; a conversão é de `saved_diagrams_by_page`, e
        este teste é quem afirma que a versão de teste passa pela porta certa.
        """
        LabelStore(self.csv).append(
            DatasetEntry(
                filename="amostra.png",
                fen=INICIAL,
                source_pdf="livro.pdf",
                source_page="1",
                source_diagram="1",
            )
        )
        janela = self._janela()
        janela.abrir_pdf(self.pdf)
        janela.marcar_diagramas()
        esperar(janela)

        caixas = janela.pdf.visor.caixas
        assert caixas is not None
        self.assertTrue(caixas.boxes[0].saved)
        self.assertIn("página concluída", janela.rodape.documento())

    def test_ler_a_pagina_enche_a_lista_o_tabuleiro_e_a_fen(self) -> None:
        servico = ServicoComLeituraFixa([diagrama_lido(0), diagrama_lido(1, "8/8/4k3/8/8/4K3/8/8")])
        janela = self._janela(servico)
        janela.abrir_pdf(self.pdf)
        janela.ler_pagina()
        esperar(janela)

        self.assertEqual(2, janela.painel.lista.count())
        self.assertIn("legal", janela.painel.lista.item(0).text())
        self.assertEqual(compose_fen(INICIAL, True), janela.painel.campo_fen.text())
        self.assertEqual((12,), janela.painel.tabuleiro.casas_incertas())
        self.assertIn("assumido", janela.painel.detalhes.text())

    def test_o_clique_num_diagrama_ja_lido_so_seleciona(self) -> None:
        """`decide_box_click` manda `SELECT`, e selecionar não pode custar uma segunda leitura."""
        servico = ServicoComLeituraFixa([diagrama_lido(0), diagrama_lido(1, "8/8/4k3/8/8/4K3/8/8")])
        janela = self._janela(servico)
        janela.abrir_pdf(self.pdf)
        janela.ler_pagina()
        esperar(janela)

        janela._clicou_na_caixa(1)
        esperar(janela)
        self.assertEqual(1, janela.painel.lista.currentRow())
        self.assertEqual(1, janela.pdf.visor.selecionada)
        self.assertEqual([0], servico.paginas_lidas)

    def test_o_clique_num_diagrama_ainda_nao_lido_le_a_pagina_e_abre_aquele(self) -> None:
        servico = ServicoComLeituraFixa([diagrama_lido(0), diagrama_lido(1, "8/8/4k3/8/8/4K3/8/8")])
        janela = self._janela(servico)
        janela.abrir_pdf(self.pdf)

        janela._clicou_na_caixa(1)
        esperar(janela)
        self.assertEqual([0], servico.paginas_lidas)
        self.assertEqual(1, janela.painel.lista.currentRow())

    def test_a_leitura_que_termina_depois_da_virada_nao_escreve_na_pagina_errada(self) -> None:
        """A página virou enquanto a thread corria: o resultado é de lá, e não pode aparecer
        aqui. É o mesmo desencontro que a S-14 corrigiu entre a tela e o PGN."""
        servico = ServicoComLeituraFixa([diagrama_lido(0)])
        janela = self._janela(servico)
        janela.abrir_pdf(self.pdf)

        janela._chegaram_itens(3, [diagrama_lido(0)], None)
        self.assertEqual(0, janela.painel.lista.count())
        self.assertIn("já está em outra", janela.rodape.mensagem())

    def test_marcar_primeiro_faz_a_leitura_aproveitar_a_deteccao(self) -> None:
        """F4 e depois F5 não pode detectar duas vezes (S-501).

        O log de uma sessão de verdade mostrava as mesmas linhas do detector repetidas por
        página -- uma por marcar, outra por ler. Aqui a régua é o que chega ao serviço: a lista
        que o "Marcar diagramas" achou, e não `None`.
        """
        servico = ServicoComLeituraFixa([diagrama_lido(0)])
        janela = self._janela(servico)
        janela.abrir_pdf(self.pdf)

        janela.marcar_diagramas()
        esperar(janela)
        janela.ler_pagina()
        esperar(janela)

        recebido = servico.candidatos_recebidos[0]
        self.assertIsNotNone(recebido)
        assert recebido is not None
        self.assertEqual(1, len(recebido))  # type: ignore[arg-type]

    def test_marcar_duas_vezes_nao_varre_a_pagina_duas_vezes(self) -> None:
        """O detector é determinístico e receberia a mesma entrada: a segunda varredura
        devolveria caixa por caixa o que já está na tela, por ~1 s de espera."""
        from unittest import mock

        import chess_diagram_ocr.qt.janela as modulo

        janela = self._janela()
        janela.abrir_pdf(self.pdf)
        varreduras: list[int] = []
        real = modulo.detect_diagrams_in_pdf_page

        def _contando(*args: object, **kwargs: object) -> object:
            varreduras.append(1)
            return real(*args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(modulo, "detect_diagrams_in_pdf_page", _contando):
            janela.marcar_diagramas()
            esperar(janela)
            janela.marcar_diagramas()
            esperar(janela)

        self.assertEqual(1, len(varreduras))
        caixas = janela.pdf.visor.caixas
        assert caixas is not None
        self.assertEqual(1, len(caixas))

    def test_marcar_depois_de_ler_nao_rebaixa_os_retangulos(self) -> None:
        """**O defeito**: marcar depois de ler devolvia as caixas ao estado "a fazer".

        A lista ao lado continuava mostrando o diagrama com FEN e confiança, e a página passava
        a dizer que não havia leitura nenhuma -- a tela desaprendendo o que ela mesma mostrava.
        """
        servico = ServicoComLeituraFixa([diagrama_lido(0)])
        janela = self._janela(servico)
        janela.abrir_pdf(self.pdf)

        janela.ler_pagina()
        esperar(janela)
        janela.marcar_diagramas()
        esperar(janela)

        caixas = janela.pdf.visor.caixas
        assert caixas is not None
        self.assertTrue(caixas.recognized, "as caixas voltaram a ser só do detector")
        self.assertEqual(1, len(janela._itens))

    def test_ler_sem_marcar_antes_deixa_a_deteccao_com_o_servico(self) -> None:
        """`None` é o caminho de sempre, e ele continua sendo o padrão."""
        servico = ServicoComLeituraFixa([diagrama_lido(0)])
        janela = self._janela(servico)
        janela.abrir_pdf(self.pdf)

        janela.ler_pagina()
        esperar(janela)

        self.assertEqual([None], servico.candidatos_recebidos)

    def test_a_deteccao_de_outra_pagina_nao_e_aproveitada_aqui(self) -> None:
        """A detecção que terminou depois da virada é da página de lá.

        Sem a conferência de página, ela seria entregue à leitura desta -- e os diagramas da
        página anterior sairiam lidos, numerados e mostrados como se fossem daqui.
        """
        servico = ServicoComLeituraFixa([diagrama_lido(0)])
        janela = self._janela(servico)
        janela.abrir_pdf(pdf_de_teste(self.pasta / "duas.pdf", paginas=2))
        janela.pdf.ir_para_pagina(1)

        janela._chegaram_candidatos(0, [_candidato_qualquer()])
        janela.ler_pagina()
        esperar(janela)

        self.assertEqual([None], servico.candidatos_recebidos)

    def test_as_setinhas_do_campo_de_pagina_viram_a_pagina(self) -> None:
        """Com `editingFinished` no lugar de `valueChanged`, as setinhas mudavam o número e
        não viravam a página -- o clique mais óbvio da barra era o único sem efeito."""
        janela = self._janela()
        janela.abrir_pdf(pdf_de_teste(self.pasta / "duas.pdf", paginas=2))

        janela.pdf.campo_pagina.setValue(2)
        self.assertIn("p. 2 de 2", janela.rodape.documento())

    def test_esconder_as_caixas_apaga_os_retangulos_da_folha(self) -> None:
        janela = self._janela()
        janela.abrir_pdf(self.pdf)
        janela.marcar_diagramas()
        esperar(janela)

        com_caixas = _renderizar(janela.pdf.visor.widget(), 300)
        janela.pdf.marcar_diagramas.setChecked(False)
        self.assertFalse(janela.pdf.visor.mostrar_caixas)
        self.assertNotEqual(com_caixas, _renderizar(janela.pdf.visor.widget(), 300))

    def test_a_roda_no_fim_da_pagina_pede_a_proxima(self) -> None:
        """A ponte inteira num gesto só: barra do Qt -> fração do `yview` -> `decide_wheel`.

        A folha aqui cabe na vista, e é o caso que `fracoes_da_vista` responde `(0.0, 1.0)` --
        está no começo e no fim ao mesmo tempo, que é o que o Tk também devolve.
        """
        from PyQt6.QtCore import QPoint, QPointF, Qt
        from PyQt6.QtGui import QWheelEvent

        janela = self._janela()
        janela.abrir_pdf(pdf_de_teste(self.pasta / "duas.pdf", paginas=2))
        janela.pdf.visor.ajustar_a_pagina()

        giro = QWheelEvent(
            QPointF(10.0, 10.0),
            QPointF(10.0, 10.0),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        janela.pdf.visor.girar_roda(giro)
        self.assertIn("p. 2 de 2", janela.rodape.documento())

    def test_pagina_sem_diagrama_nao_e_erro(self) -> None:
        """Há muitas páginas de prosa, e tratá-las como falha ensina a ignorar a caixa de erro."""
        from chess_diagram_ocr.board_detection import NoBoardDetectedError

        janela = self._janela()
        janela._falhou("nenhum tabuleiro", NoBoardDetectedError("nada aqui"))
        self.assertIn("Nenhum diagrama", janela.rodape.mensagem())


class SelftestTests(unittest.TestCase):
    """O `--selftest`: responde, numa máquina limpa, se esta metade sobe ali."""

    @staticmethod
    def _app_pyqt():
        """`app_pyqt.py` mora na raiz e não é pacote; o pytest só põe `src/` no path."""
        import sys

        raiz = str(Path(__file__).resolve().parents[1])
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        import app_pyqt

        return app_pyqt

    def setUp(self) -> None:
        aplicacao()
        self.pasta = pasta_temporaria(self)

    def test_com_um_pdf_de_verdade_o_auto_teste_passa(self) -> None:
        """O caminho inteiro: checkpoint, PDF, janela, render, reconhecimento, treino e as peles.

        **Pula sem o checkpoint, e o pulo e a resposta honesta** (S-417). O `.pt` nao e
        versionado -- ele nasce do treino de quem usa o programa --, e numa maquina sem ele a
        pergunta que este auto-teste faz ("esta instalacao le um diagrama?") nao tem resposta.

        **Era isto que fazia o teste passar aqui e reprovar na CI**, e o defeito e meu: ate a
        S-506 o auto-teste nao abria o checkpoint, porque delegava o pipeline ao `--selftest` do
        arquivo de entrada que o corte apagou. Quando ele voltou a medir o caminho inteiro, o
        codigo 3 passou a ser a resposta certa numa maquina sem `.pt` -- e a maquina de quem
        desenvolve tem um.
        """
        app_pyqt = self._app_pyqt()
        if not Path(app_pyqt.DEFAULT_MODEL_PATH).exists():
            self.skipTest(f"sem checkpoint em {app_pyqt.DEFAULT_MODEL_PATH}: o pipeline nao roda")
        self.assertEqual(0, app_pyqt.selftest(pdf_de_teste(self.pasta / "livro.pdf")))

    def test_sem_checkpoint_o_codigo_de_saida_e_o_do_arquivo_que_falta(self) -> None:
        """O outro lado, e **este roda em toda maquina**: sem o `.pt` o programa abre e nao le.

        Codigo proprio e nao o 1 generico: quem chega aqui conserta com um arquivo, e a
        diferenca entre "o programa falhou" e "falta o modelo" e a diferenca entre abrir uma
        issue e copiar um `.pt` para `models/`.
        """
        from unittest import mock

        app_pyqt = self._app_pyqt()
        ausente = self.pasta / "modelos" / "nao_existe.pt"
        with mock.patch.object(app_pyqt, "DEFAULT_MODEL_PATH", ausente):
            self.assertEqual(3, app_pyqt.selftest(pdf_de_teste(self.pasta / "livro.pdf")))

    def test_sem_pdf_o_codigo_de_saida_diz_o_que_falta(self) -> None:
        from unittest import mock

        app_pyqt = self._app_pyqt()
        with mock.patch.object(app_pyqt, "find_default_pdf_path", lambda: None):
            self.assertEqual(2, app_pyqt.selftest())

    def test_sem_o_pyqt_instalado_o_codigo_e_outro_e_a_mensagem_diz_o_comando(self) -> None:
        """Códigos distintos porque as duas faltas pedem ações distintas -- e a que se conserta
        com um comando tem de trazer o comando escrito."""
        from unittest import mock

        app_pyqt = self._app_pyqt()
        with mock.patch.object(app_pyqt, "tem_pyqt", lambda: False):
            self.assertEqual(app_pyqt.CODIGO_SEM_QT, app_pyqt.selftest())
        # `uv sync` e nao `uv sync --extra qt`: o extra saiu no corte do Tk, quando o PyQt6
        # virou dependencia de base -- e este assert fixava a instrucao quebrada (S-506).
        self.assertIn("uv sync", app_pyqt.FALTA_O_PYQT)
        self.assertNotIn("--extra qt", app_pyqt.FALTA_O_PYQT)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class JanelaDoAutoTesteTests(unittest.TestCase):
    """O auto-teste monta a janela sem tocar na sessão de quem o roda (S-524).

    A segunda revisão externa viu o `--selftest` apagar o livro e a página da pessoa numa árvore
    em que a janela gravava a cada gesto. Aqui ela grava no `closeEvent`, que o auto-teste não
    dispara -- e a afirmação abaixo é o que faz isso deixar de depender de quando ela grava.
    """

    def setUp(self) -> None:
        aplicacao()
        self.pasta = pasta_temporaria(self)

    def test_o_estado_e_descartavel_e_nao_ha_motor(self) -> None:
        from chess_diagram_ocr.qt.janela import CAMINHO_DO_ESTADO

        app_pyqt = SelftestTests._app_pyqt()
        janela = app_pyqt._janela_do_auto_teste(ServicoComLeituraFixa([]), self.pasta)
        self.addCleanup(janela.deleteLater)
        self.addCleanup(janela.close)
        self.assertNotEqual(CAMINHO_DO_ESTADO, janela._caminho_do_estado)
        self.assertEqual(self.pasta, janela._caminho_do_estado.parent)
        self.assertFalse(janela.estudo.has_engine)


if __name__ == "__main__":  # pragma: no cover - conveniência de quem roda o arquivo direto
    unittest.main()
