"""A fila da pele "Foco" no segundo frontend: pílulas por ação e o separador entre grupos (S-522).

**O que só existe deste lado.** Quem está na fila e como ela se agrupa é `comandos.fila_de_destaque`,
já afirmado em `tests/test_ui_comandos.py`; o que se afirma aqui é a tradução -- cada registro
virando pílula, cada fronteira de grupo virando um traço -- e a **cor** do traço, que é onde o
retrato desmentiu a forma óbvia: o `QFrame.VLine` desenha com a cor de texto da paleta, e não com a
da folha. O separador é pintado pela folha, e por isso o `grab()` sob `offscreen` mede o que o
produto desenha -- ao contrário da moldura dos controles, que é do estilo da plataforma.
"""

from __future__ import annotations

import unittest

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import comandos, tokens

if TEM_PYQT:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QWidget

    from chess_diagram_ocr.qt import fila, tema


def _hexa(imagem: object, x: int, y: int) -> str:
    return QColor(imagem.pixel(x, y)).name()  # type: ignore[attr-defined]


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FilaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = aplicacao()
        # A folha é da aplicação inteira: o que este teste aplica, ele devolve à clássica.
        self.addCleanup(tema.aplicar_tema, self.app)

    def _fila(self, *, cromo_escuro: bool = False) -> fila.Fila:
        tema.aplicar_tema(self.app, cromo_escuro=cromo_escuro)
        montada = fila.montar(None, {acao: (lambda: None) for acao in fila.acoes_da_fila()})
        self.addCleanup(descartar, montada)
        return montada

    def test_toda_acao_em_destaque_vira_pilula(self) -> None:
        self.assertEqual(set(fila.acoes_da_fila()), set(self._fila().botoes))

    def test_comando_sem_funcao_levanta_nomeando_o_que_falta(self) -> None:
        """Uma pílula com ícone que não faz nada é pior que a ausência dela (S-223)."""
        acoes = fila.acoes_da_fila()
        amarrados = {acao: (lambda: None) for acao in acoes[1:]}
        with self.assertRaises(KeyError) as erro:
            fila.montar(None, amarrados)
        self.assertIn(acoes[0], str(erro.exception))

    def test_ha_um_separador_entre_grupos_e_nenhum_na_ponta(self) -> None:
        montada = self._fila()
        separadores = montada.findChildren(QWidget, tema.ID_DO_SEPARADOR)
        self.assertEqual(len(comandos.fila_de_destaque()) - 1, len(separadores))

    def test_o_separador_e_um_pixel_da_moldura_do_cromo_nas_duas_peles(self) -> None:
        """Medido no `windows11` antes: 2 px em `#848688`, a cor de texto da paleta, mais claro que
        a borda das pílulas. Agora é 1 px da moldura derivada da superfície, e a mesma nas duas
        peles porque o valor sai de `tokens.moldura_sobre` e não de um número escrito."""
        for cromo_escuro in (False, True):
            with self.subTest(cromo_escuro=cromo_escuro):
                montada = self._fila(cromo_escuro=cromo_escuro)
                montada.resize(1600, 48)
                montada.show()
                self.app.processEvents()
                imagem = montada.grab().toImage()
                separador = montada.findChildren(QWidget, tema.ID_DO_SEPARADOR)[0]
                origem = separador.mapTo(montada, QPoint(0, 0))
                y = origem.y() + separador.height() // 2
                superficie = tema.cor_atual(tokens.SUPERFICIE_PADRAO)
                esperada = tokens.moldura_sobre(superficie)

                self.assertEqual(1, separador.width())
                self.assertGreater(separador.height(), 8, "o traço não ocupa a altura da fila")
                self.assertEqual(esperada, _hexa(imagem, origem.x(), y))
                self.assertEqual(superficie, _hexa(imagem, origem.x() - 3, y), "o vizinho não é a superfície")
                self.assertEqual(superficie, _hexa(imagem, origem.x() + 3, y))
                self.assertGreaterEqual(tokens.razao_de_contraste(esperada, superficie), tokens.AA_GRAFICO)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
