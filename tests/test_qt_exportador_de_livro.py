"""As duas exportações do livro diante de duas suítes: a que recebe o caderno (R7) e a de antes.

A janela tem duas: *Exportar o livro para EPUB/DOCX…* (`qt/exportador_de_livro.montar`) e a da aba
Rotulagem (`qt/painel_de_rotulagem.montar`), que exporta o livro do projeto dela.

O `.venv` do tronco não tem a suíte, e por isso ela entra aqui como um módulo de mentira em
`sys.modules`: o que se afirma é a costura do tronco -- as folhas chegam a quem as aceita, e uma
suíte que não conhece `folhas_para` continua exportando em vez de falhar no argumento.
"""

from __future__ import annotations

import types
import unittest
from typing import Any
from unittest import mock

from qt_app import MOTIVO, TEM_PYQT, aplicacao

if TEM_PYQT:
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QWidget

    from chess_diagram_ocr.qt import exportador_de_livro, painel_de_rotulagem

    class _Antiga(QObject):
        """A face de `caissa.ui.views.exportacao.ExportadorDeLivro` antes do R7."""

        estado = pyqtSignal(str)
        controles = pyqtSignal(bool)

        def __init__(self, pai: Any) -> None:
            super().__init__(pai)
            self.chamadas: list[dict[str, Any]] = []

        def comecar(self, pdf_path: Any, page_count: int, *, formato: str = "epub", pagina_atual: int = 0, documento_para: Any = None) -> bool:
            self.chamadas.append({"pdf": pdf_path, "formato": formato, "documento_para": documento_para})
            return True

    class _Nova(_Antiga):
        def comecar(  # type: ignore[override]
            self, pdf_path: Any, page_count: int, *, formato: str = "epub", pagina_atual: int = 0,
            documento_para: Any = None, folhas_para: Any = None,
        ) -> bool:
            self.chamadas.append({"pdf": pdf_path, "formato": formato, "folhas_para": folhas_para})
            return True

    class _RotulagemAntiga(QWidget):
        def __init__(self, parent: Any = None, *, revisor: str = "") -> None:
            super().__init__(parent)

    class _RotulagemNova(_RotulagemAntiga):
        folhas_para: Any = None


def _suite(classe: type) -> dict[str, types.ModuleType]:
    modulo = types.ModuleType("caissa.ui.views.exportacao")
    modulo.ExportadorDeLivro = classe  # type: ignore[attr-defined]
    return {"caissa.ui.views.exportacao": modulo}


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MontarTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()
        self.frases: list[str] = []

    def montar(self, classe: type) -> Any:
        with mock.patch.dict("sys.modules", _suite(classe)):
            return exportador_de_livro.montar(None, dizer=self.frases.append, trancar=lambda _: None)  # type: ignore[arg-type]

    def test_a_suite_do_r7_recebe_as_folhas(self) -> None:
        exportador = self.montar(_Nova)
        folhas = lambda _paginas: []  # noqa: E731
        self.assertTrue(exportador.comecar("livro.pdf", 5, formato="epub", pagina_atual=0, folhas_para=folhas))
        self.assertIs(exportador.chamadas[-1]["folhas_para"], folhas)

    def test_a_suite_de_antes_exporta_sem_as_folhas(self) -> None:
        exportador = self.montar(_Antiga)
        documento = lambda _paginas: None  # noqa: E731
        self.assertTrue(
            exportador.comecar("livro.pdf", 5, formato="docx", pagina_atual=1, documento_para=documento, folhas_para=lambda _p: [])
        )
        self.assertEqual(exportador.chamadas, [{"pdf": "livro.pdf", "formato": "docx", "documento_para": documento}])

    def test_o_rodape_continua_ligado(self) -> None:
        exportador = self.montar(_Antiga)
        exportador.estado.emit("Exportando…")
        self.assertEqual(self.frases, ["Exportando…"])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class RotulagemTests(unittest.TestCase):
    def setUp(self) -> None:
        aplicacao()

    def montar(self, classe: type, folhas: Any) -> Any:
        modulo = types.ModuleType("caissa.ui.views.rotulagem")
        modulo.PainelDeRotulagem = classe  # type: ignore[attr-defined]
        with mock.patch.dict("sys.modules", {"caissa.ui.views.rotulagem": modulo}):
            painel = painel_de_rotulagem.montar(None, folhas_para=folhas)  # type: ignore[arg-type]
        self.addCleanup(painel.deleteLater)
        return painel

    def test_a_aba_do_r7_recebe_quem_da_as_folhas(self) -> None:
        folhas = lambda _pdf, _paginas: []  # noqa: E731
        self.assertIs(self.montar(_RotulagemNova, folhas).folhas_para, folhas)

    def test_a_aba_de_antes_monta_igual(self) -> None:
        painel = self.montar(_RotulagemAntiga, lambda _pdf, _paginas: [])
        self.assertIsInstance(painel, _RotulagemAntiga)
        self.assertFalse(hasattr(painel, "folhas_para"), "a aba de antes ganhou um atributo que não lê")


if __name__ == "__main__":
    unittest.main()
