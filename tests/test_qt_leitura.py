"""OCR_UI ciclo 2, passo C2: ler a página com progresso, cancelamento e o gravar trancado.

Antes, `_rodar` estava em `FORA_DO_REGISTRO`: rodapé sem barra nem «Cancelar», o painel
Resultado inteiro cinza durante a leitura, e o primeiro «Ler» da sessão pagando a carga do
modelo às cegas. Estes testes montam a janela com um serviço ditado cujo `recognize_page`
obedece aos ganchos, e afirmam o que a pessoa passa a ver.
"""

from __future__ import annotations

import threading
import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.service import RecognitionCanceled
from chess_diagram_ocr.ui.busy import BusyRegistry

if TEM_PYQT:
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt.janela import JanelaPrincipal
    from chess_diagram_ocr.qt.leitura import (
        ESPERA_PARA_AQUECER_MS,
        Aquecimento,
        Ocupacao,
        frase_de_cancelamento,
        sem_modelo,
    )
    from chess_diagram_ocr.qt.trabalho import Tarefa
    from test_qt_janela import _livro


def _diagrama(indice: int = 0):
    import numpy as np

    from chess_diagram_ocr.service import RecognizedDiagram

    return RecognizedDiagram(
        index=indice,
        board_rgb=np.full((64, 64, 3), 200, np.uint8),
        placement="8/8/8/8/8/8/8/K6k",
        min_confidence=0.93,
        square_confidences=[0.99] * 64,
        side_to_move="w",
    )


class _ServicoDitado:
    """Um `OcrService` cujo `recognize_page` lê `n` diagramas, avisa o progresso e obedece ao
    cancelamento; `segurar` prende a leitura até o teste soltar."""

    device = None
    device_label = ""
    caption_reader = None
    model_path = Path("inexistente.pt")

    def __init__(self, n: int = 3) -> None:
        self.n = n
        self.segurar = threading.Semaphore(0)   # um `release` por diagrama que pode ser lido
        self.carregado = 0
        self.progresso: list[tuple[int, int]] = []

    def invalidate_model(self, caminho: object = None) -> None:
        pass

    def model_session(self, caminho: object) -> None:  # pragma: no cover
        return None

    def load(self, caminho: object = None) -> tuple[object, str]:
        self.carregado += 1
        return object(), "cpu"

    def recognize_page(self, pdf, pagina, page_rgb=None, *, options, candidates=None,
                       progress=None, should_cancel=None):
        lidos = []
        if progress is not None:
            progress(0, self.n)
        for i in range(self.n):
            self.segurar.acquire(timeout=2.0)
            if should_cancel is not None and should_cancel():
                raise RecognitionCanceled(lidos)
            lidos.append(_diagrama(i))
            if progress is not None:
                self.progresso.append((i + 1, self.n))
                progress(i + 1, self.n)
        return lidos


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PecasTests(unittest.TestCase):
    """As peças de `qt/leitura.py`, sem janela."""

    def setUp(self) -> None:
        self.app = aplicacao()

    def test_a_ocupacao_registra_com_total_e_cancelar_e_solta(self) -> None:
        busy = BusyRegistry()
        tarefa = Tarefa(lambda: None, nome="leitura")
        ocupacao = Ocupacao(busy)
        ocupacao.registrar(tarefa, nome="leitura", aviso="Lendo…", total=4, cancelavel=True)
        operacao = busy.running()[0]
        self.assertEqual((operacao.name, operacao.total, operacao.cancellable), ("leitura", 4, True))
        ocupacao.progresso("página 3")(2, 4)
        operacao = busy.running()[0]
        self.assertEqual((operacao.feito, operacao.total), (2, 4))
        self.assertIn("2 de 4", operacao.detail)
        busy.request_cancel()
        self.assertTrue(tarefa.should_cancel())
        ocupacao.soltar()
        self.assertEqual(busy.running(), [])

    def test_o_aquecimento_carrega_uma_vez_e_diz_quando_o_modelo_falta(self) -> None:
        busy = BusyRegistry()
        servico = _ServicoDitado()
        ditos: list[tuple[str, str]] = []
        aquecimento = Aquecimento(servico, busy, dizer=lambda frase, nivel: ditos.append((frase, nivel)))
        tarefa = aquecimento.iniciar()
        assert tarefa is not None
        self.assertTrue(aquecimento.em_curso)
        # Sem pai (`manter_viva`): fechar a janela numa carga longa não pode abortar o processo.
        self.assertIsNone(tarefa.parent())
        for _ in range(200):
            QTest.qWait(10)
            if not aquecimento.em_curso:
                break
        self.assertEqual(servico.carregado, 1)
        self.assertEqual(busy.running(), [])
        self.assertIsNone(aquecimento.iniciar(), "uma vez por processo")

        class _SemPt(_ServicoDitado):
            def load(self, caminho: object = None):
                raise FileNotFoundError("piece_classifier.pt não encontrado")

        falho = Aquecimento(_SemPt(), busy, dizer=lambda frase, nivel: ditos.append((frase, nivel)))
        tarefa = falho.iniciar()
        for _ in range(200):
            QTest.qWait(10)
            if not falho.em_curso:
                break
        self.assertTrue(ditos and "Configurações" in ditos[-1][0], ditos)

    def test_as_frases(self) -> None:
        self.assertIn("antes do primeiro", frase_de_cancelamento(0))
        self.assertIn("2 diagrama(s)", frase_de_cancelamento(2))
        self.assertTrue(sem_modelo(FileNotFoundError("models/piece_classifier.pt")))
        self.assertFalse(sem_modelo(FileNotFoundError("outro.txt")))
        self.assertFalse(sem_modelo(RuntimeError("piece_classifier")))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LeituraNaJanelaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.livro = _livro(self.pasta)
        self.detector = mock.patch(
            "chess_diagram_ocr.qt.janela.detect_diagrams_in_pdf_page", return_value=[]).start()
        self.addCleanup(mock.patch.stopall)
        self.servico = _ServicoDitado()

    def janela(self) -> JanelaPrincipal:
        montada = JanelaPrincipal(
            servico=self.servico,  # type: ignore[arg-type]
            csv_de_rotulos=self.pasta / "labels.csv",
            pasta_de_estudos=self.pasta,
            pasta_da_galeria=self.pasta,
            caminho_do_estado=self.pasta / "janela.json",
        )
        self.addCleanup(descartar, montada)
        montada.resize(1400, 900)
        montada.abrir_pdf(self.livro)
        for _ in range(300):
            QTest.qWait(10)
            if not montada._detector.ocupado and montada.pdf.page_rgb is not None:
                break
        return montada

    def _esperar(self, condicao, ate_ms: int = 4000) -> None:
        for _ in range(ate_ms // 10):
            QTest.qWait(10)
            if condicao():
                return

    def test_abrir_o_livro_aquece_o_modelo_quando_a_janela_ocia(self) -> None:
        """O aquecimento é agendado (`ESPERA_PARA_AQUECER_MS`), não disparado: o portão
        `bloqueio` mediu 30–80 ms de GIL sobre «abrir PDF» com a carga no instante da abertura."""
        janela = self.janela()
        self.assertEqual(self.servico.carregado, 0, "ainda não: a janela acabou de abrir")
        self._esperar(lambda: self.servico.carregado >= 1, ate_ms=6000)
        self.assertEqual(self.servico.carregado, 1)

    def test_fechar_a_janela_cancela_o_aquecimento_agendado(self) -> None:
        """Fechada mas ainda não destruída, a janela guardava o relógio armado e o aquecimento
        disparava depois do fecho, numa janela morta (o portão de execução do tronco acusou
        duas threads sem dono). Fechar cancela o que estava agendado."""
        janela = self.janela()
        self.assertEqual(self.servico.carregado, 0)
        janela.close()
        self._esperar(lambda: False, ate_ms=ESPERA_PARA_AQUECER_MS + 1500)
        self.assertEqual(self.servico.carregado, 0, "o relógio de uma janela fechada disparou")
        self.assertFalse(janela._aquecimento.em_curso)

    def test_ler_a_pagina_registra_no_rodape_com_cancelar_e_tranca_so_o_gravar(self) -> None:
        janela = self.janela()
        self._esperar(lambda: self.servico.carregado >= 1, ate_ms=6000)
        janela.ler_pagina()
        self._esperar(lambda: any(o.name == "leitura" for o in janela.busy.running()))
        operacao = next(o for o in janela.busy.running() if o.name == "leitura")
        self.assertTrue(operacao.cancellable)
        # A leitura corre: o painel continua ligado, só o gravar está trancado.
        self.assertTrue(janela.painel.isEnabled())
        self.assertFalse(janela.painel.btn_salvar.isEnabled())
        for _ in range(3):
            self.servico.segurar.release()
        self._esperar(lambda: janela._tarefa is None)
        self.assertEqual(len(janela.painel.modelo.items), 3)
        self.assertEqual(self.servico.progresso, [(1, 3), (2, 3), (3, 3)])
        self.assertEqual([o.name for o in janela.busy.running()], [])
        self.assertTrue(janela.painel.btn_salvar.isEnabled(), "gravar volta quando a leitura acaba")

    def test_cancelar_pelo_rodape_para_entre_diagramas_e_o_lido_fica(self) -> None:
        janela = self.janela()
        self._esperar(lambda: self.servico.carregado >= 1, ate_ms=6000)
        self.servico.n = 3
        janela.ler_pagina()
        self._esperar(lambda: any(o.name == "leitura" for o in janela.busy.running()))
        # Solta um diagrama, pede para parar, solta o resto: o serviço olha o gancho antes do 2.º.
        self.servico.segurar.release()
        self._esperar(lambda: len(self.servico.progresso) >= 1)
        janela.busy.request_cancel()
        self.servico.segurar.release()
        self.servico.segurar.release()
        self._esperar(lambda: janela._tarefa is None)
        self.assertEqual(len(janela.painel.modelo.items), 1)
        self.assertIn("cancelada", janela.rodape.mensagem().lower())

    def test_sabotagem_um_servico_que_ignora_o_gancho_le_ate_o_fim(self) -> None:
        """O que o gancho compra: sem consultá-lo, o «Cancelar» não para nada."""

        class _Surdo(_ServicoDitado):
            def recognize_page(self, *args, should_cancel=None, **kwargs):
                return super().recognize_page(*args, should_cancel=None, **kwargs)

        self.servico = _Surdo()
        janela = self.janela()
        janela.ler_pagina()
        self._esperar(lambda: any(o.name == "leitura" for o in janela.busy.running()))
        janela.busy.request_cancel()
        for _ in range(3):
            self.servico.segurar.release()
        self._esperar(lambda: janela._tarefa is None)
        self.assertEqual(len(janela.painel.modelo.items), 3)
        self.assertNotIn("cancelada", janela.rodape.mensagem().lower())
