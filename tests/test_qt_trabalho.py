"""A detecção de fundo: um pedido de cada vez, só o último espera, e a falha não é caixa (S-68)."""

from __future__ import annotations

import time
import unittest
from unittest import mock

from qt_app import MOTIVO, TEM_PYQT, TarefaAdiada, aplicacao, descartar, esperar_ate

if TEM_PYQT:
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt.trabalho import DeteccaoDeFundo

from chess_diagram_ocr.ui.ancora_da_tela import AncoraDaTela


def _na(pagina: int) -> AncoraDaTela:
    return AncoraDaTela.de("livro.pdf", pagina)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DeteccaoDeFundoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.detector = DeteccaoDeFundo()
        self.addCleanup(descartar, self.detector)
        self.addCleanup(self.detector.parar, 5000)
        self.chegou: list[tuple[AncoraDaTela, object]] = []
        self.detector.achou.connect(lambda a, c: self.chegou.append((a, c)))

    def _esperar(self, quantos: int, ate_ms: int = 5000) -> None:
        esperar_ate(
            lambda: len(self.chegou) >= quantos and not self.detector.ocupado,
            limite_s=ate_ms / 1000,
            o_que=f"{quantos} resultados com o detector parado",
        )

    def test_so_o_ultimo_pedido_espera_enquanto_um_roda(self) -> None:
        """Virar dez páginas com a roda não enfileira dez detecções: as do meio são puladas, e
        voltam a ser pedidas quando a página for exibida de novo."""

        def lenta() -> list[int]:
            time.sleep(0.15)
            return [1]

        self.detector.pedir(_na(0), lenta)
        self.detector.pedir(_na(1), lenta)
        self.detector.pedir(_na(2), lenta)
        self._esperar(2)
        self.assertEqual([a for a, _ in self.chegou], [_na(0), _na(2)])

    def test_a_falha_vai_para_o_log_e_o_proximo_pedido_ainda_roda(self) -> None:
        """Ninguém pediu esta detecção: uma caixa de erro por ela ensinaria a ignorar caixas."""

        def quebra() -> None:
            raise RuntimeError("sem contorno")

        with self.assertLogs("chess_diagram_ocr.qt.trabalho", level="WARNING") as registro:
            self.detector.pedir(_na(0), quebra)
            self.detector.pedir(_na(1), lambda: [1, 2])
            self._esperar(1)
        self.assertEqual([a for a, _ in self.chegou], [_na(1)])
        self.assertIn("página 1", registro.output[0])

    def test_parar_esquece_o_pedido_guardado_e_espera_o_que_corre(self) -> None:
        def lenta() -> list[int]:
            time.sleep(0.1)
            return []

        self.detector.pedir(_na(0), lenta)
        self.detector.pedir(_na(1), lenta)
        self.assertTrue(self.detector.parar(5000))
        self.assertFalse(self.detector.ocupado)
        QTest.qWait(50)
        self.assertEqual([a.pagina for a, _ in self.chegou], [0], "o pedido guardado não roda depois de parar")


class _TarefaQueJaAcabou(TarefaAdiada):
    """A thread terminou e os sinais dela ainda estão na fila: `wait` diz que acabou (S-829)."""

    def wait(self, _ms: int = 0) -> bool:
        return True


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SinalLevaAAncoraTests(unittest.TestCase):
    """`parar` e um `pedir` novo antes de a fila entregar o `pronto` velho (S-829)."""

    def setUp(self) -> None:
        aplicacao()
        TarefaAdiada.pendentes.clear()
        self.addCleanup(TarefaAdiada.pendentes.clear)
        self.detector = DeteccaoDeFundo()
        self.addCleanup(descartar, self.detector)
        self.chegou: list[tuple[AncoraDaTela, object]] = []
        self.detector.achou.connect(lambda a, c: self.chegou.append((a, c)))

    def test_o_resultado_velho_sai_com_a_ancora_do_pedido_dele(self) -> None:
        from chess_diagram_ocr.qt import trabalho

        with mock.patch.object(trabalho, "Tarefa", _TarefaQueJaAcabou):
            self.detector.pedir(_na(0), lambda: ["da 0"])
            self.assertTrue(self.detector.parar(0))
            self.detector.pedir(_na(1), lambda: ["da 1"])
        da_0, da_1 = TarefaAdiada.pendentes

        da_0.entregar()
        self.assertEqual([(_na(0), ["da 0"])], self.chegou, "o resultado da página 1 saiu rotulado com a 2")
        self.assertTrue(self.detector.ocupado, "o `finished` velho zerou a detecção que ainda corre")
        da_1.entregar()
        self.assertEqual([(_na(0), ["da 0"]), (_na(1), ["da 1"])], self.chegou)
        self.assertFalse(self.detector.ocupado)

    def test_o_resultado_que_chega_depois_do_detector_morrer_nao_o_toca(self) -> None:
        """O PyQt não desfaz a ligação a um `partial`: sem a guarda, `achou.emit` num objeto apagado
        levantaria dentro do slot, que no PyQt6 é `qFatal`."""
        from chess_diagram_ocr.qt import trabalho

        detector = DeteccaoDeFundo()
        detector.achou.connect(lambda a, c: self.chegou.append((a, c)))
        with mock.patch.object(trabalho, "Tarefa", TarefaAdiada):
            detector.pedir(_na(0), lambda: ["da 0"])
        descartar(detector)
        TarefaAdiada.entregar_todas()  # não levanta
        self.assertEqual([], self.chegou)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class CederAInterfaceTests(unittest.TestCase):
    """O intervalo de troca do interpretador encurta com a primeira `Tarefa` (OCR_UI passo 15)."""

    def test_a_primeira_tarefa_encurta_o_intervalo_e_nunca_o_alonga(self) -> None:
        import sys

        from chess_diagram_ocr.qt import trabalho

        aplicacao()
        anterior = sys.getswitchinterval()
        try:
            sys.setswitchinterval(0.005)
            trabalho._cedeu = False
            trabalho.Tarefa(lambda: None)
            self.assertLessEqual(sys.getswitchinterval(), trabalho.INTERVALO_DE_TROCA_S)

            sys.setswitchinterval(trabalho.INTERVALO_DE_TROCA_S / 2)
            trabalho._cedeu = False
            trabalho.ceder_a_interface()
            self.assertAlmostEqual(trabalho.INTERVALO_DE_TROCA_S / 2, sys.getswitchinterval(), msg="não alonga")
        finally:
            sys.setswitchinterval(anterior)

