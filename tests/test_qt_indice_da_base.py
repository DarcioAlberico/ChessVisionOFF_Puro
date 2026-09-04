"""O índice da base construído de dentro da janela (S-532): thread, sinais, cancelamento e diálogo.

A decisão -- a frase, a régua por mil, "perde trabalho?" -- é de `ui/indice_da_base.py` e já é
afirmada em `tests/test_ui_indice_da_base.py`; o incremento em si, em `tests/test_games_index.py`.
O que só existe aqui é o que atravessa a fronteira de thread e o que o diálogo liga.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui.busy import BusyRegistry

if TEM_PYQT:
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QPushButton

    from chess_diagram_ocr.qt.indice_da_base import IndexadorDaBase, frase_final, indexar_com_dialogo

PGN = (
    '[Event "London"]\n[White "Anderssen, Adolf"]\n[Black "Kieseritzky, Lionel"]\n[Result "1-0"]\n\n'
    "1. e4 e5 2. f4 exf4 1-0\n\n"
    '[Event "Havana"]\n[White "Capablanca, Jose Raul"]\n[Black "Lasker, Emanuel"]\n[Result "1-0"]\n\n'
    "1. d4 d5 1-0\n"
)


def _pgn_grande(partidas: int) -> str:
    bloco = '[Event "S {n}"]\n[White "Branco{n}, A"]\n[Black "Preto{n}, B"]\n\n1. e4 e5 2. Nf3 Nc6 *\n\n'
    return "".join(bloco.replace("{n}", str(n)) for n in range(partidas))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class IndexadorDaBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(PGN, encoding="utf-8")
        self.indice = self.raiz / "indice.sqlite"
        self.indexador = IndexadorDaBase()
        # LIFO: primeiro espera a thread, depois destroi o objeto -- um QThread destruido rodando
        # derruba o processo.
        self.addCleanup(descartar, self.indexador)
        self.addCleanup(self.indexador.esperar, 10_000)

    def _esperar(self, indexador: IndexadorDaBase | None = None, ate_ms: int = 10_000) -> None:
        alvo = indexador or self.indexador
        for _ in range(ate_ms // 20):
            QTest.qWait(20)
            if not alvo.ocupado:
                return

    def test_o_fim_chega_por_sinal_com_o_resultado(self) -> None:
        chegou: list[object] = []
        self.indexador.terminou.connect(chegou.append)
        self.assertTrue(self.indexador.iniciar([self.base], self.indice))
        self._esperar()
        self.assertEqual(len(chegou), 1)
        self.assertEqual(self.indexador.resultado.partidas, 2)  # type: ignore[union-attr]
        self.assertTrue(self.indice.exists())

    def test_o_progresso_chega_por_sinal_e_somado_por_mil(self) -> None:
        """O `progress` do índice roda na thread de trabalho; o que a barra recebe já veio pela
        fila de eventos, e o último valor do conjunto é mil."""
        avancos: list[int] = []
        avisos: list[tuple[str, int, int, int]] = []
        self.indexador.avancou.connect(avancos.append)
        self.indexador.progresso.connect(
            lambda nome, lidos, total, partidas: avisos.append((nome, lidos, total, partidas))
        )
        self.indexador.iniciar([self.base], self.indice)
        self._esperar()
        self.assertEqual(avancos[-1], 1000)
        self.assertEqual({nome for nome, *_ in avisos}, {"base.pgn"})

    def test_nao_comeca_duas_rodadas_ao_mesmo_tempo(self) -> None:
        """Duas escreveriam no mesmo arquivo."""
        self.assertTrue(self.indexador.iniciar([self.base], self.indice))
        self.assertFalse(self.indexador.iniciar([self.base], self.indice))
        self._esperar()

    def test_cancelar_para_e_o_resultado_diz(self) -> None:
        grande = self.raiz / "grande.pgn"
        grande.write_text(_pgn_grande(300_000), encoding="utf-8")
        self.indexador.iniciar([grande], self.indice)
        QTest.qWait(100)
        inicio = time.perf_counter()
        self.indexador.cancelar()
        self._esperar()
        self.assertLess(time.perf_counter() - inicio, 1.5)
        self.assertTrue(self.indexador.resultado.cancelado)  # type: ignore[union-attr]

    def test_a_falha_vira_sinal_e_nao_excecao(self) -> None:
        falhas: list[str] = []
        self.indexador.falhou.connect(lambda mensagem, _exc: falhas.append(mensagem))
        # O "diretorio" do indice e um arquivo: o SQLite nao tem onde nascer.
        impossivel = self.base / "indice.sqlite"
        with self.assertLogs("chess_diagram_ocr.qt", level="WARNING"):
            self.indexador.iniciar([self.base], impossivel)
            self._esperar()
        self.assertEqual(len(falhas), 1)
        self.assertIsNone(self.indexador.resultado)

    def test_registra_no_busy_enquanto_roda_e_solta_no_fim(self) -> None:
        """Fechar a janela no meio pergunta; e a operação não diz que perde trabalho, porque não perde."""
        registro = BusyRegistry()
        indexador = IndexadorDaBase(busy=registro)
        self.addCleanup(descartar, indexador)
        self.addCleanup(indexador.esperar, 10_000)
        indexador.iniciar([self.base], self.indice)
        self.assertTrue(registro.is_busy)
        (operacao,) = registro.running()
        self.assertFalse(operacao.loses_work)
        self.assertTrue(operacao.cancellable)
        self._esperar(indexador)
        self.assertFalse(registro.is_busy)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DialogoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.indice = self.raiz / "indice.sqlite"

    def _esperar(self, indexador: IndexadorDaBase, ate_ms: int = 10_000) -> None:
        for _ in range(ate_ms // 20):
            QTest.qWait(20)
            if not indexador.ocupado:
                return

    def test_o_dialogo_anda_com_o_indice_e_fecha_no_fim(self) -> None:
        """O valor da barra é lido a cada avanço, e não no fim: no fim o diálogo já foi
        destruído -- é o que "fecha sozinho" quer dizer, e um diálogo que sobrevivesse à rodada
        seria um por rodada pendurado na janela."""
        base = self.raiz / "base.pgn"
        base.write_text(PGN, encoding="utf-8")
        indexador = indexar_com_dialogo(None, [base], self.indice, mostrar=False)
        self.addCleanup(descartar, indexador)
        self.addCleanup(indexador.esperar, 10_000)
        dialogo = indexador.dialogo
        assert dialogo is not None
        self.assertEqual(dialogo.windowTitle(), "Índice da base de partidas")
        valores: list[int] = []
        rotulos: list[str] = []
        # Ligado DEPOIS do dialogo: o Qt chama os slots na ordem em que foram ligados, entao
        # aqui o `setValue` do dialogo ja aconteceu.
        indexador.avancou.connect(lambda _por_mil: valores.append(dialogo.value()))
        indexador.progresso.connect(lambda *_aviso: rotulos.append(dialogo.labelText()))
        self._esperar(indexador)
        self.assertEqual(valores[-1], 1000)
        self.assertIn("base.pgn", rotulos[-1])
        self.assertIsNone(indexador.dialogo, "fechou e foi marcado para destruição")
        self.assertIn("2 partidas no índice", frase_final(indexador.resultado))  # type: ignore[arg-type]

    def test_o_botao_cancelar_do_dialogo_para_o_indice(self) -> None:
        """O clique no botão, e não `cancel()`: o método só esconde e reinicia o diálogo, sem
        emitir `canceled` -- é o botão que está ligado ao indexador."""
        grande = self.raiz / "grande.pgn"
        grande.write_text(_pgn_grande(300_000), encoding="utf-8")
        indexador = indexar_com_dialogo(None, [grande], self.indice, mostrar=False)
        self.addCleanup(descartar, indexador)
        self.addCleanup(indexador.esperar, 10_000)
        QTest.qWait(100)
        assert indexador.dialogo is not None
        botao = indexador.dialogo.findChild(QPushButton)
        self.assertIsNotNone(botao)
        botao.click()
        self._esperar(indexador)
        self.assertTrue(indexador.resultado.cancelado)  # type: ignore[union-attr]
        self.assertIn("interrompido", frase_final(indexador.resultado))  # type: ignore[arg-type]
