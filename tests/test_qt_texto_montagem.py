"""A montagem do `PainelDeTexto` não deixa exceção sair do filtro de eventos.

O filtro entra no editor antes de o rodapé existir, e o editor recebe eventos no meio da montagem:
`eventFilter` perguntava `a0 is self.status` e levantava `AttributeError`. O PyQt entrega a exceção
ao `sys.excepthook`; com o gancho padrão, no 3.13 ela vira `qFatal` e o processo morre sem uma linha
(a CI do PR #46 morria assim em `test_app_pyqt`). Aqui o gancho é trocado por um que anota.
"""

from __future__ import annotations

import sys
import unittest
from types import TracebackType

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

if TEM_PYQT:
    from chess_diagram_ocr.qt import tema
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MontagemTests(unittest.TestCase):
    def test_montar_e_mostrar_nao_levanta_dentro_do_filtro(self) -> None:
        anotadas: list[BaseException] = []

        def anotar(_tipo: type[BaseException], valor: BaseException, _tb: TracebackType | None) -> None:
            anotadas.append(valor)

        app = aplicacao()
        tema.aplicar_tema(app)
        antes = sys.excepthook
        sys.excepthook = anotar
        try:
            painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=pasta_temporaria(self) / "rascunhos")
            self.addCleanup(descartar, painel)
            painel.resize(640, 480)
            painel.show()
            app.processEvents()
        finally:
            sys.excepthook = antes
        self.assertEqual([repr(e) for e in anotadas], [])


if __name__ == "__main__":
    unittest.main()
