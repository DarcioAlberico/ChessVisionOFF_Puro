"""O processo de trabalho do passo 15 da OCR_UI: o filho existe, responde e morre limpo.

Os três testes que abrem um filho de verdade custam o `spawn` (um a dois segundos cada, na
primeira vez); estão aqui porque a promessa do módulo -- *"o pai só espera"* -- só se prova com
um processo de verdade. O resto da suíte roda em linha (`conftest.trabalho_em_linha`).
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

import numpy as np

from chess_diagram_ocr.pdf_io import render_pdf_page
from chess_diagram_ocr.processo_de_trabalho import PaginaQueDerruba, ProcessoDeTrabalho, processo_de_trabalho


def _soma(a: int, b: int) -> int:
    return a + b


def _pid() -> int:
    import os

    return os.getpid()


def _segura_o_gil(ms: int) -> int:
    """Python puro por `ms` milissegundos: numa thread, isto trava a janela; num filho, não."""
    fim = time.perf_counter() + ms / 1000.0
    contador = 0
    while time.perf_counter() < fim:
        contador += 1
    return contador


class EmLinhaTests(unittest.TestCase):
    def test_em_linha_roda_a_funcao_aqui_mesmo(self) -> None:
        trabalho = ProcessoDeTrabalho(em_processo=False)
        self.assertEqual(5, trabalho.executar(_soma, 2, 3))
        self.assertEqual(_pid(), trabalho.executar(_pid))
        trabalho.encerrar()

    def test_o_partilhado_e_um_so(self) -> None:
        self.assertIs(processo_de_trabalho(), processo_de_trabalho())


class NoFilhoTests(unittest.TestCase):
    """Um filho de verdade. `encerrar(esperar=True)` no fim, senão as threads de serviço vazam."""

    def setUp(self) -> None:
        self.trabalho = ProcessoDeTrabalho(em_processo=True)
        self.addCleanup(self.trabalho.encerrar, True)

    def test_a_funcao_roda_noutro_processo_e_o_resultado_volta(self) -> None:
        self.assertEqual(5, self.trabalho.executar(_soma, 2, 3))
        self.assertNotEqual(_pid(), self.trabalho.executar(_pid), "rodou aqui, e não no filho")

    def test_a_pagina_rasterizada_no_filho_e_a_mesma_de_render_pdf_page(self) -> None:
        import tempfile

        from test_app_pyqt import pdf_de_teste

        with tempfile.TemporaryDirectory() as pasta:
            pdf = pdf_de_teste(Path(pasta) / "livro.pdf")
            do_filho = self.trabalho.rasterizar(pdf, 0, dpi=72)
            daqui = render_pdf_page(pdf, 0, dpi=72)
        self.assertEqual(daqui.shape, do_filho.shape)
        self.assertTrue(np.array_equal(daqui, do_filho))

    def test_python_no_filho_nao_segura_o_interpretador_daqui(self) -> None:
        """A razão de o módulo existir, medida: 150 ms de Python no filho, e esta thread anda.

        O mesmo `_segura_o_gil` numa `threading.Thread` deixaria o laço abaixo parado por quase
        os 150 ms inteiros -- é o que o `bloqueio` mediu com o PyMuPDF e com o `labels.csv`.
        """
        self.trabalho.executar(_soma, 1, 1)  # o filho já nasceu e importou

        pior = 0.0

        def pedir() -> None:
            self.trabalho.executar(_segura_o_gil, 150)

        fio = threading.Thread(target=pedir)
        fio.start()
        ultimo = time.perf_counter()
        while fio.is_alive():
            time.sleep(0.001)
            agora = time.perf_counter()
            pior = max(pior, agora - ultimo)
            ultimo = agora
        fio.join()
        self.assertLess(pior * 1000, 40.0, f"a thread principal ficou {pior * 1000:.0f} ms sem andar")


def _derruba_no_filho(pid_da_janela: int, marca: str) -> int:
    """Mata o processo em que roda, se não for o da janela; no da janela, deixa `marca` escrita.

    É a página que derruba o MuPDF, sem o MuPDF: o `os._exit` é a queda que nenhum `except` pega.
    """
    import os

    if os.getpid() != pid_da_janela:
        os._exit(3)
    Path(marca).write_bytes(b"rodou no processo da janela")
    return os.getpid()


def _derruba_a_primeira_vez(marca: str) -> int:
    """Derruba o filho na primeira chamada (sem `marca`) e responde o pid nas seguintes."""
    import os

    if not Path(marca).exists():
        Path(marca).write_bytes(b"caiu uma vez")
        os._exit(3)
    return os.getpid()


class QuedaDoFilhoTests(unittest.TestCase):
    """S-874: a função que derruba o filho nunca roda no processo da janela."""

    def setUp(self) -> None:
        import tempfile

        self.trabalho = ProcessoDeTrabalho(em_processo=True)
        self.addCleanup(self.trabalho.encerrar, True)
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def test_funcao_que_derruba_o_filho_nunca_roda_no_pai(self) -> None:
        marca = self.pasta / "rodou_no_pai"
        erro: BaseException | None = None
        try:
            self.trabalho.executar(_derruba_no_filho, _pid(), str(marca), pagina=11)
        except Exception as exc:  # noqa: BLE001 - o tipo é conferido abaixo, depois da marca
            erro = exc
        self.assertFalse(marca.exists(), "a função que derruba o filho rodou no processo da janela")
        self.assertIsInstance(erro, PaginaQueDerruba)
        assert isinstance(erro, PaginaQueDerruba)
        self.assertEqual(11, erro.pagina)
        self.assertIn("página 12", str(erro), "a frase diz a página como a pessoa a conta")

    def test_uma_queda_por_chamada_nao_acumula_entre_chamadas(self) -> None:
        """Duas quedas em chamadas diferentes, com sucesso no meio, não mandam ninguém para a linha."""
        for nome in ("primeira", "segunda"):
            pid = self.trabalho.executar(_derruba_a_primeira_vez, str(self.pasta / nome))
            self.assertNotEqual(_pid(), pid, f"a {nome} chamada rodou no processo da janela")


class QuandoNaoHaFilhoTests(unittest.TestCase):
    def test_sem_filho_possivel_cai_para_a_linha_com_aviso(self) -> None:
        trabalho = ProcessoDeTrabalho(em_processo=True)
        self.addCleanup(trabalho.encerrar, True)
        original = sys.modules["chess_diagram_ocr.processo_de_trabalho"].ProcessPoolExecutor

        def quebrado(*_args: object, **_kwargs: object) -> object:
            raise OSError("sem spawn aqui")

        sys.modules["chess_diagram_ocr.processo_de_trabalho"].ProcessPoolExecutor = quebrado  # type: ignore[assignment]
        try:
            self.assertEqual(5, trabalho.executar(_soma, 2, 3))
        finally:
            sys.modules["chess_diagram_ocr.processo_de_trabalho"].ProcessPoolExecutor = original  # type: ignore[assignment]
        self.assertFalse(trabalho.em_processo, "depois da falha o módulo lembra que não há filho")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
