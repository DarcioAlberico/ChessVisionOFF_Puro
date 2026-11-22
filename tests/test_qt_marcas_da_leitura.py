"""As marcas dos diagramas lidos (`qt/marcas_da_leitura.py`) e o caminho delas até a folha da aba Texto.

O detector e o modelo são respostas fixas aqui: o que eles acham é de `tests/test_detector_de_marcas.py` e
`tests/test_modelo_de_marcas.py`. O que se afirma é a regra da concordância no caminho, a thread, e que a
marca chega à folha como leitura -- sem virar alteração por gravar -- e de lá à folha da suíte.
"""

from __future__ import annotations

import threading
import unittest
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr import marcas_de_casa as mc
from chess_diagram_ocr.text import caderno_na_suite
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, Coluna, PaginaLida

if TEM_PYQT:
    from chess_diagram_ocr.qt import marcas_da_leitura as ml
    from chess_diagram_ocr.qt.painel_de_texto import PainelDeTexto

RECORTE = np.full((80, 80, 3), 230, np.uint8)
DETECTOR = {"c5": mc.X, "d3": mc.ESTRELA_PRETA}
MODELO = {"c5": mc.X, "f6": mc.BOLINHA_BRANCA}


def _detector(_recorte: np.ndarray) -> mc.MarcasDoDiagrama:
    return mc.MarcasDoDiagrama(casas=dict(DETECTOR))


def _modelo(_recorte: np.ndarray) -> dict[str, str]:
    return dict(MODELO)


@dataclass
class _Lido:
    placement: str
    board_rgb: np.ndarray


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class LeitorDeMarcasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        remendo = mock.patch.object(ml.detector_de_marcas, "sugerir_marcas", _detector)
        remendo.start()
        self.addCleanup(remendo.stop)

    def test_so_a_concordancia_e_o_recorte_vazio_e_nao_lido(self) -> None:
        self.assertEqual(ml.marcas_dos_recortes([RECORTE, np.zeros((0, 0, 3), np.uint8)], _modelo), [{"c5": mc.X}, None])

    def test_o_modelo_que_falha_deixa_o_diagrama_sem_leitura(self) -> None:
        def quebrado(_recorte: np.ndarray) -> dict[str, str]:
            raise RuntimeError("pesos estragados")

        self.assertEqual(ml.marcas_dos_recortes([RECORTE], quebrado), [None])

    def test_a_thread_entrega_pelo_sinal_com_o_livro_que_pediu(self) -> None:
        leitor = ml.LeitorDeMarcas(modelo=lambda: Path("nao-existe.pt"), leitor=_modelo)
        self.addCleanup(descartar, leitor)
        chegou: list[tuple[object, int, object]] = []
        leitor.prontas.connect(lambda livro, pagina, marcas: chegou.append((livro, pagina, marcas)))
        trabalho = leitor.ler("livro", 4, [RECORTE])
        assert trabalho is not None
        trabalho.join(10)
        self.app.processEvents()
        self.assertEqual(chegou, [("livro", 4, [{"c5": mc.X}])])

    def test_sem_o_arquivo_do_modelo_nada_chega(self) -> None:
        leitor = ml.LeitorDeMarcas(modelo=lambda: pasta_temporaria(self) / "nao-existe.pt")
        self.addCleanup(descartar, leitor)
        chegou: list[object] = []
        leitor.prontas.connect(lambda *args: chegou.append(args))
        trabalho = leitor.ler("livro", 0, [RECORTE])
        assert trabalho is not None
        trabalho.join(10)
        self.app.processEvents()
        self.assertEqual(chegou, [], "sem a segunda opinião, o detector sozinho não marca a folha")

    def test_pagina_sem_diagrama_nao_abre_thread(self) -> None:
        leitor = ml.LeitorDeMarcas(modelo=lambda: Path("nao-existe.pt"), leitor=_modelo)
        self.addCleanup(descartar, leitor)
        self.assertIsNone(leitor.ler("livro", 0, []))


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class MarcasNaFolhaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        remendo = mock.patch.object(ml.detector_de_marcas, "sugerir_marcas", _detector)
        remendo.start()
        self.addCleanup(remendo.stop)
        self.pasta = pasta_temporaria(self)
        self.painel = PainelDeTexto(dpi=72, pasta_de_rascunhos=self.pasta / "rascunhos")
        self.addCleanup(descartar, self.painel)
        self.painel.definir_livro(Path("livro.pdf"), pagina=0)
        # O modelo de verdade não entra no teste: o leitor recebe a resposta fixa.
        self.painel.leitor_de_marcas._leitor = _modelo
        self.painel.leitor_de_marcas._tentado = True

    def pagina(self) -> PaginaLida:
        return PaginaLida(
            documento="livro.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=(BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 60.0, 60.0)),)),)
        )

    def ler(self, pagina: int = 0) -> None:
        leitor = self.painel.leitor_de_marcas
        original = leitor.ler
        trabalhos: list[threading.Thread] = []

        def ler_e_guardar(livro: object, folha: int, recortes: Sequence[np.ndarray]) -> threading.Thread | None:
            trabalho = original(livro, folha, recortes)
            if trabalho is not None:
                trabalhos.append(trabalho)
            return trabalho

        with mock.patch.object(leitor, "ler", ler_e_guardar):
            self.painel.definir_leitura_dos_diagramas(pagina, [_Lido("8/8/8/8/8/8/8/K6k", RECORTE)])
        for trabalho in trabalhos:
            trabalho.join(10)
        self.app.processEvents()

    def test_a_marca_chega_a_folha_sem_virar_alteracao_e_vai_a_suite(self) -> None:
        self.painel.mostrar_pagina(self.pagina())
        self.ler()
        assert self.painel._pagina is not None
        self.assertEqual(self.painel._pagina.diagramas[0].placement, "8/8/8/8/8/8/8/K6k")
        self.assertEqual(self.painel._pagina.diagramas[0].marcas, (("c5", mc.X),))
        self.assertFalse(self.painel.tem_alteracoes, "a marca é leitura, não edição")
        (diagrama,) = [p for p in caderno_na_suite.paragrafos_da_folha(self.painel.documento) if p["kind"] == "diagram"]
        self.assertEqual(diagrama["marks"], {"c5": mc.X})

    def test_a_marca_que_chega_antes_espera_a_folha(self) -> None:
        self.ler()
        self.painel.mostrar_pagina(self.pagina())
        assert self.painel._pagina is not None
        self.assertEqual(self.painel._pagina.diagramas[0].marcas, (("c5", mc.X),))

    def test_resposta_de_outro_livro_e_ignorada(self) -> None:
        self.painel.mostrar_pagina(self.pagina())
        self.painel._chegaram_marcas("outro-livro", 0, [{"a1": mc.X}])
        assert self.painel._pagina is not None
        self.assertEqual(self.painel._pagina.diagramas[0].marcas, ())


if __name__ == "__main__":
    unittest.main()
