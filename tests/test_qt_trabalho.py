"""A detecção de fundo: um pedido de cada vez, só o último espera, e a falha não é caixa (S-68)."""

from __future__ import annotations

import time
import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

if TEM_PYQT:
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt.trabalho import DeteccaoDeFundo


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DeteccaoDeFundoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.detector = DeteccaoDeFundo()
        self.addCleanup(descartar, self.detector)
        self.addCleanup(self.detector.parar, 5000)
        self.chegou: list[tuple[str, int, object]] = []
        self.detector.achou.connect(lambda d, p, c: self.chegou.append((d, p, c)))

    def _esperar(self, quantos: int, ate_ms: int = 5000) -> None:
        passos = ate_ms // 20
        for _ in range(passos):
            QTest.qWait(20)
            if len(self.chegou) >= quantos and not self.detector.ocupado:
                return

    def test_so_o_ultimo_pedido_espera_enquanto_um_roda(self) -> None:
        """Virar dez páginas com a roda não enfileira dez detecções: as do meio são puladas, e
        voltam a ser pedidas quando a página for exibida de novo."""

        def lenta() -> list[int]:
            time.sleep(0.15)
            return [1]

        self.detector.pedir("livro.pdf", 0, lenta)
        self.detector.pedir("livro.pdf", 1, lenta)
        self.detector.pedir("livro.pdf", 2, lenta)
        self._esperar(2)
        self.assertEqual([(d, p) for d, p, _ in self.chegou], [("livro.pdf", 0), ("livro.pdf", 2)])

    def test_a_falha_vai_para_o_log_e_o_proximo_pedido_ainda_roda(self) -> None:
        """Ninguém pediu esta detecção: uma caixa de erro por ela ensinaria a ignorar caixas."""

        def quebra() -> None:
            raise RuntimeError("sem contorno")

        with self.assertLogs("chess_diagram_ocr.qt.trabalho", level="WARNING") as registro:
            self.detector.pedir("livro.pdf", 0, quebra)
            self.detector.pedir("livro.pdf", 1, lambda: [1, 2])
            self._esperar(1)
        self.assertEqual([(d, p) for d, p, _ in self.chegou], [("livro.pdf", 1)])
        self.assertIn("página 1", registro.output[0])

    def test_parar_esquece_o_pedido_guardado_e_espera_o_que_corre(self) -> None:
        def lenta() -> list[int]:
            time.sleep(0.1)
            return []

        self.detector.pedir("livro.pdf", 0, lenta)
        self.detector.pedir("livro.pdf", 1, lenta)
        self.assertTrue(self.detector.parar(5000))
        self.assertFalse(self.detector.ocupado)
        QTest.qWait(50)
        self.assertEqual([p for _, p, _ in self.chegou], [0], "o pedido guardado não roda depois de parar")
