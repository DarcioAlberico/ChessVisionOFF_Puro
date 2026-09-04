"""O piso da janela, medido painel a painel, e o que ainda o segura (S-552).

**O defeito, medido em 2026-09-04.** Pedida a `1000x800`, a janela abria em **1245x902** -- e, uma
vez lida uma página, o piso subia para **1245x1218**, mais alto que a tela de um notebook de
1366x768 e sem volta na sessão. O ChessBase e o Lichess funcionam a 1024 px.

**A cadeia inteira, e quem é dono de cada elo:**

| elo | pedia | quem declara |
| --- | ----- | ------------ |
| `LARGURA_MINIMA_DAS_ABAS` | 720 px | `qt/janela.py` |
| `LARGURA_MINIMA_DO_VISOR` | 520 px | `qt/janela.py` |
| a aba mais exigente (Galeria) | 711 x 800 | `qt/painel_da_galeria.py` |
| o painel de Resultado depois de ler | 301 x 1095 | `qt/painel_de_resultado.py` |

Os dois primeiros somam `720 + 520 + 5` de alça = **1245**, e são literais de um arquivo que este
item não toca. Os dois últimos são o que a S-552 corrigiu, e é o que estes testes cobram: **nenhuma
aba pode exigir da janela mais do que uma tela de 1024x768 tem**. Com isso, o que sobra do piso é
exatamente a soma dos dois literais -- e o teste abaixo mede essa distância em vez de escondê-la,
para que ela não passe despercebida quando alguém baixá-los.
"""

from __future__ import annotations

import unittest

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import galeria_declarada, geometria

if TEM_PYQT:
    from PyQt6.QtCore import Qt

    from chess_diagram_ocr.qt import janela as qt_janela
    from chess_diagram_ocr.qt import painel_da_galeria as qt_galeria
    from chess_diagram_ocr.qt import painel_de_resultado as qt_resultado


class _ServicoFalso:
    """O `OcrService` visto de fora, com o que os painéis lhe pedem na montagem.

    A mesma forma de `tests/test_qt_janela.py`: um objeto de cinco atributos e não um `MagicMock`,
    porque o que se afirma aqui é geometria e um mock responderia a tudo -- inclusive a `width()`.
    """

    device = None
    device_label = ""
    caption_reader = None

    def invalidate_model(self, caminho: object = None) -> None:
        pass

    def model_session(self, caminho: object) -> None:  # pragma: no cover - nada é reconhecido aqui
        return None


TELA_MINIMA = (1024, 768)
"""A tela que o item pediu, e é a de um notebook de 1366x768 com a janela numa metade -- ou a de
um projetor. `ui/geometria.PISO_MEDIDO` já registrava que 800 px de altura não cabem em 768."""

CROMO = (0, 200)
"""O que a janela gasta fora das abas, com folga: barra de menu (32), de status (21), a fileira de
abas (~34) e as margens. Medido em 2026-09-04 e arredondado para cima -- o teste é sobre a **aba**,
e um número apertado o faria falhar por um pixel de tema."""


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PainelSemExigenciaTests(unittest.TestCase):
    """Cada painel sozinho: nenhum pede da janela mais do que a tela mínima tem."""

    def setUp(self) -> None:
        self.app = aplicacao()

    def test_a_galeria_rola_em_vez_de_exigir_800_px_de_altura(self) -> None:
        """Os 420 px do recorte e os 260 da lateral são medidos (S-154) e continuam inteiros: o que
        muda é que a soma deles deixa de ser o piso da janela."""
        pasta = pasta_temporaria(self)
        painel = qt_galeria.PainelDaGaleria(
            service=_ServicoFalso(),
            pdf_path=lambda: None,
            model_path=lambda: pasta / "modelo.pt",
            max_boards=lambda: 4,
            pasta_da_galeria=pasta / "galeria",
        )
        self.addCleanup(descartar, painel)
        pedido = painel.minimumSizeHint()
        self.assertLess(pedido.height(), TELA_MINIMA[1] - CROMO[1])
        self.assertLess(pedido.width(), TELA_MINIMA[0])
        # O conteúdo não encolheu: ele está dentro da área rolável.
        self.assertEqual(
            qt_galeria.BOARD_VIEW_SIZE, painel.recorte.width(), "o recorte medido da S-154 mudou"
        )
        self.assertIsNotNone(painel.rolagem.widget())

    def test_o_resultado_nao_cresce_de_piso_quando_o_texto_cresce(self) -> None:
        """`detalhes` quebra linha, e um `QLabel` com `wordWrap` responde a altura mínima calculada
        para a largura mais estreita possível: ler uma página levava o mínimo desta aba de 551 para
        **1095 px**. Dentro da área rolável, o piso não se mexe."""
        pasta = pasta_temporaria(self)
        painel = qt_resultado.PainelDeResultado(
            _ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=pasta / "rotulos.csv",
        )
        self.addCleanup(descartar, painel)
        antes = painel.minimumSizeHint().height()
        painel.detalhes.setText("uma frase bem comprida sobre a leitura. " * 60)
        self.app.processEvents()
        self.assertEqual(antes, painel.minimumSizeHint().height(), "o texto virou piso de janela")
        self.assertLess(antes, TELA_MINIMA[1] - CROMO[1])


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PisoDaJanelaTests(unittest.TestCase):
    """A janela montada: o que ela ainda exige, e de onde vem cada pixel."""

    def setUp(self) -> None:
        self.app = aplicacao()
        raiz = pasta_temporaria(self)
        self.janela = qt_janela.JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=raiz / "rotulos.csv",
            pasta_de_estudos=raiz / "estudos",
            pasta_da_galeria=raiz / "galeria",
            caminho_do_estado=raiz / "estado.json",
            motor=None,
        )
        self.janela.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.addCleanup(descartar, self.janela)
        self.janela.resize(1400, 950)
        self.janela.show()
        self.app.processEvents()

    def test_a_altura_minima_cabe_numa_tela_de_768(self) -> None:
        """Era 902 px com a janela recém-aberta e 1218 depois de ler uma página."""
        self.assertLessEqual(self.janela.minimumSizeHint().height(), TELA_MINIMA[1])

    def test_nenhuma_aba_exige_mais_altura_do_que_a_tela_tem(self) -> None:
        for indice in range(self.janela.abas.count()):
            nome = self.janela.abas.tabText(indice).replace("&", "")
            with self.subTest(aba=nome):
                pedido = self.janela.abas.widget(indice).minimumSizeHint()
                self.assertLessEqual(pedido.height(), TELA_MINIMA[1] - CROMO[1])

    def test_as_duas_abas_que_seguravam_o_piso_nao_o_seguram_mais(self) -> None:
        """A Galeria pedia `711 x 800` e o Resultado chegava a `301 x 1095` depois de ler.

        **A largura não é medida em número absoluto**, e é por isso que a régua é a constante
        declarada: sob `offscreen` não há a fonte da interface, e todo widget de texto mede mais --
        a aba Dataset responde 842 px aqui e 516 na janela de verdade. O que se afirma é que a
        Galeria deixou de pedir a soma das partes dela (S-154), e não um número de tela.
        """
        indices = {self.janela.abas.tabText(i).replace("&", ""): i for i in range(self.janela.abas.count())}
        galeria = self.janela.abas.widget(indices["Galeria"]).minimumSizeHint()
        self.assertLess(galeria.width(), galeria_declarada.LARGURA_MINIMA_DA_GALERIA)
        self.assertLess(galeria.height(), TELA_MINIMA[1] - CROMO[1])
        resultado = self.janela.abas.widget(indices["Resultado"]).minimumSizeHint()
        self.assertLess(resultado.height(), TELA_MINIMA[1] - CROMO[1])

    def test_o_piso_de_largura_e_o_dos_dois_literais_da_janela(self) -> None:
        """**A distância medida, e não escondida.** O piso de largura é `720 + 520 + alça`, e os
        dois números são literais de `qt/janela.py` -- que este item não toca. Quando alguém os
        baixar, este teste é o que diz se sobrou mais alguma coisa segurando a janela.
        """
        alca = self.janela.divisor.handleWidth()
        declarado = qt_janela.LARGURA_MINIMA_DAS_ABAS + qt_janela.LARGURA_MINIMA_DO_VISOR + alca
        self.assertGreaterEqual(self.janela.minimumSizeHint().width(), declarado)
        self.assertGreater(
            declarado, TELA_MINIMA[0], "os dois literais couberam em 1024: atualize a spec da S-552"
        )

    def test_o_piso_declarado_continua_sendo_a_soma_das_partes(self) -> None:
        """`geometria.piso_da_janela` acompanha um painel que cresça, e é o que um número cravado
        não faz. Ele continua acima da tela mínima **por causa dos dois literais**, e é a linha que
        fecha a conta deste item."""
        piso = geometria.piso_da_janela(
            qt_janela.LARGURA_MINIMA_DAS_ABAS, qt_janela.LARGURA_MINIMA_DO_VISOR
        )
        self.assertGreater(piso[0], TELA_MINIMA[0], "o piso declarado passou a caber: atualize a spec")

    def test_pedida_pequena_a_janela_encolhe_ate_o_piso_e_nao_mais(self) -> None:
        self.janela.resize(*TELA_MINIMA)
        self.app.processEvents()
        self.assertEqual(TELA_MINIMA[1], self.janela.height(), "a altura pedida foi recusada")
        self.assertEqual(self.janela.minimumSizeHint().width(), self.janela.width())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
