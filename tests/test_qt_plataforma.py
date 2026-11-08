"""DPI, ícone e identidade do processo, no segundo frontend (S-148/S-501).

**O que estes testes cobrem, e o que não.** O gerador do `.ico` continua sendo o de
`ui/plataforma.py` e é afirmado em `tests/test_ui_plataforma.py` -- inclusive que o arquivo em
disco e o gerador não divergiram. Repetir aquilo aqui mediria o mesmo código duas vezes.

O que só existe deste lado é o que o Qt faz diferente: a política de escala (que substitui o
`SetProcessDpiAwareness` do Tk), o ícone posto na **aplicação** e não na janela, e a identidade
na barra de tarefas -- que o Tk resolvia por dentro do `iconbitmap` e aqui é uma chamada
explícita.

E, acima de tudo, a **ausência de propagação**: este é o primeiro código a rodar na abertura da
janela, e uma exceção aqui é uma janela que não abre em vez de uma janela sem ícone.
"""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao

from chess_diagram_ocr.ui import plataforma as plataforma_tk

if TEM_PYQT:
    from chess_diagram_ocr.qt import plataforma


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EscalaTests(unittest.TestCase):
    """A fração de 125% e 150%, que é o que substitui o item de DPI da S-148."""

    def test_a_politica_preserva_a_fracao(self) -> None:
        """O padrão do Qt arredonda 125% para 100%, e o resultado é o borrão da S-148.

        A janela é desenhada para uma densidade e esticada para outra -- num programa cujo
        trabalho é conferir glifo impresso, isso é dano funcional e não estético.
        """
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("QT_SCALE_FACTOR_ROUNDING_POLICY", None)
            plataforma.politica_de_escala()
            self.assertEqual(os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"], "PassThrough")

    def test_quem_ja_escolheu_a_politica_manda(self) -> None:
        """`setdefault` e não `=`: dá para diagnosticar escala sem editar código."""
        with mock.patch.dict("os.environ", {"QT_SCALE_FACTOR_ROUNDING_POLICY": "Round"}):
            import os

            plataforma.politica_de_escala()
            self.assertEqual(os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"], "Round")

    def test_o_dpi_de_referencia_e_o_mesmo_dos_dois_lados(self) -> None:
        """As duas janelas do mesmo produto não podem discordar sobre o que é 100%."""
        self.assertEqual(plataforma.DPI_DE_REFERENCIA, plataforma_tk.DPI_DE_REFERENCIA)

    def test_o_percentual_e_dito_como_o_windows_o_mostra(self) -> None:
        for dpi, esperado in ((96.0, 100), (120.0, 125), (144.0, 150)):
            with self.subTest(dpi=dpi):
                preparo = plataforma.Preparo(dpi=dpi, escala=dpi / 96, icone=None, identificado=False)
                self.assertEqual(preparo.percentual, esperado)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class IconeTests(unittest.TestCase):
    """O ícone é do produto, e vale para toda janela do processo."""

    def setUp(self) -> None:
        self.app = aplicacao()

    def test_o_icone_vai_para_a_aplicacao_e_nao_para_uma_janela(self) -> None:
        """Pô-lo em cada janela deixaria o primeiro diálogo esquecido com o ícone genérico."""
        if not plataforma.CAMINHO_DO_ICONE.is_file():
            self.skipTest("assets/cvoff.ico não está no disco")
        self.assertEqual(plataforma.aplicar_icone(self.app), plataforma.CAMINHO_DO_ICONE)
        self.assertFalse(self.app.windowIcon().isNull())

    def test_sem_arquivo_a_janela_abre_com_o_padrao(self) -> None:
        ausente = Path("assets") / "nao-existe.ico"
        with mock.patch.object(plataforma, "CAMINHO_DO_ICONE", ausente):
            self.assertIsNone(plataforma.aplicar_icone(self.app))

    def test_arquivo_ilegivel_nao_vira_icone_vazio_em_silencio(self) -> None:
        """`QIcon` de um arquivo ruim **não levanta**: devolve um ícone vazio.

        A janela abriria com o padrão sem uma linha a que se agarrar, e é por isso que
        `aplicar_icone` pergunta `isNull()` em vez de confiar na ausência de exceção.
        """
        from ambiente_de_teste import pasta_temporaria

        ruim = pasta_temporaria(self) / "quebrado.ico"
        ruim.write_bytes(b"isto nao e um icone")
        with mock.patch.object(plataforma, "CAMINHO_DO_ICONE", ruim):
            self.assertIsNone(plataforma.aplicar_icone(self.app))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class IdentidadeTests(unittest.TestCase):
    """O `AppUserModelID`, que é o que separa o ícone da janela do ícone da barra de tarefas."""

    def test_o_identificador_tem_o_formato_que_a_microsoft_pede(self) -> None:
        partes = plataforma.ID_NA_BARRA_DE_TAREFAS.split(".")
        self.assertGreaterEqual(len(partes), 3, "o formato é Empresa.Produto.SubProduto")
        self.assertTrue(all(partes), "nenhuma parte pode ser vazia")

    @unittest.skipUnless(sys.platform == "win32", "o AppUserModelID é do Windows")
    def test_no_windows_ele_e_aceito(self) -> None:
        self.assertTrue(plataforma.identificar_na_barra_de_tarefas())

    def test_fora_do_windows_devolve_falso_sem_levantar(self) -> None:
        with mock.patch.object(sys, "platform", "linux"):
            self.assertFalse(plataforma.identificar_na_barra_de_tarefas())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PrepararTests(unittest.TestCase):
    """A garantia que importa: nada aqui derruba a janela."""

    def setUp(self) -> None:
        aplicacao()

    def test_prepara_e_devolve_o_que_deu_certo(self) -> None:
        preparo = plataforma.preparar_janela()
        self.assertGreater(preparo.dpi, 0)
        self.assertGreater(preparo.escala, 0)

    def test_uma_janela_que_levanta_em_toda_chamada_nao_impede_a_abertura(self) -> None:
        """O teste é sobre a **ausência de propagação**, e não sobre o efeito.

        Este é o primeiro código a rodar na abertura, e uma exceção aqui é uma janela que não
        abre em vez de uma janela sem ícone. É o mesmo teste que a S-148 fez do outro lado.
        """

        class JanelaHostil:
            def __getattr__(self, nome: str) -> object:
                raise RuntimeError(f"esta janela recusa {nome}")

        preparo = plataforma.preparar_janela(JanelaHostil())  # type: ignore[arg-type]
        self.assertEqual(preparo.dpi, plataforma.DPI_DE_REFERENCIA)

    def test_nao_declara_consciencia_de_dpi_e_a_ausencia_e_o_item(self) -> None:
        """O Qt 6 já é *per-monitor DPI aware* ao construir a `QApplication`.

        Reimplementar o `SetProcessDpiAwareness` aqui seria pior que inútil: a chamada precisa
        vir antes da primeira janela, e depois dela o Windows devolve `E_ACCESSDENIED`. A
        ausência da função é decisão, e este teste é onde ela está escrita para quem for
        procurá-la por analogia com `ui/plataforma.py`.
        """
        self.assertFalse(hasattr(plataforma, "consciencia_de_dpi"))
        self.assertFalse(hasattr(plataforma.Preparo, "consciencia_de_dpi"))


LEVANTA_NUM_SLOT = """
import os, sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from chess_diagram_ocr.logging_setup import configure_logging
configure_logging(log_file=Path(sys.argv[1]))
from chess_diagram_ocr.qt.plataforma import instalar_borda
instalar_borda()
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
aplicacao = QApplication([])
def levanta():
    raise RuntimeError("estourou dentro do slot")
QTimer.singleShot(0, levanta)
QTimer.singleShot(50, aplicacao.quit)
sys.exit(aplicacao.exec())
"""
"""Um slot que levanta, e o laço que termina logo depois. Sem borda, o PyQt6 chama `qFatal`."""


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class BordaTests(unittest.TestCase):
    """A exceção que escapa de tudo vira linha de log, e não processo morto (S-800)."""

    def test_excecao_num_slot_vai_ao_log_e_o_processo_segue(self) -> None:
        """O critério de aceite da S-800: código 0 e a linha `CRITICAL` com o traceback.

        Num subprocesso porque o que se mede é o processo: sem a borda o PyQt6 chama `qFatal`
        e ele sai com 0xC0000409 (ou 127 sob `offscreen`) sem escrever uma linha.
        """
        from subprocesso import rodar_python

        log = pasta_temporaria(self) / "borda.log"
        feito = rodar_python(LEVANTA_NUM_SLOT.replace("sys.argv[1]", repr(str(log))), check=False, timeout=120)
        texto = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertEqual(0, feito.returncode, f"o processo caiu:\n{feito.stderr[-2000:]}")
        self.assertIn("CRITICAL", texto)
        self.assertIn("Traceback (most recent call last)", texto)
        self.assertIn("RuntimeError: estourou dentro do slot", texto)

    def _borda(self) -> plataforma.Borda:
        """A borda instalada só durante o teste: os dois ganchos voltam ao que eram."""
        for alvo in (sys, threading):
            remendo = mock.patch.object(alvo, "excepthook")
            remendo.start()
            self.addCleanup(remendo.stop)
        return plataforma.instalar_borda()

    def test_com_janela_a_frase_vai_ao_rodape(self) -> None:
        app = aplicacao()
        frases: list[str] = []
        self._borda().frase.connect(frases.append)
        with self.assertLogs(plataforma.logger, "CRITICAL") as registro:
            try:
                raise ValueError("o slot quebrou")
            except ValueError:
                sys.excepthook(*sys.exc_info())
            app.processEvents()
        self.assertIsInstance((registro.records[0].exc_info or (None, None))[1], ValueError)
        self.assertEqual([plataforma.FRASE_DA_BORDA], frases)

    def test_excecao_de_thread_chega_ao_log_e_ao_rodape_pela_linha_de_eventos(self) -> None:
        """A frase sai da thread por sinal: widget tocado fora da linha de eventos derruba o Qt."""
        app = aplicacao()
        frases: list[str] = []
        self._borda().frase.connect(frases.append)

        def quebra() -> None:
            raise KeyError("da thread")

        with self.assertLogs(plataforma.logger, "CRITICAL") as registro:
            fio = threading.Thread(target=quebra, name="fio-que-quebra")
            fio.start()
            fio.join(5)
            app.processEvents()
        self.assertIn("fio-que-quebra", registro.output[0])
        self.assertIsInstance((registro.records[0].exc_info or (None, None))[1], KeyError)
        self.assertEqual([plataforma.FRASE_DA_BORDA], frases)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
