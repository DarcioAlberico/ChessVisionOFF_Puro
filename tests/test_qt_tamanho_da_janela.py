"""O piso da janela, medido painel a painel, e o que ainda o segura (S-552).

**O defeito, medido em 2026-09-04.** Pedida a `1000x800`, a janela abria em **1245x902** -- e, uma
vez lida uma página, o piso subia para **1245x1218**, mais alto que a tela de um notebook de
1366x768 e sem volta na sessão. O ChessBase e o Lichess funcionam a 1024 px.

**A cadeia inteira, e quem é dono de cada elo:**

| elo | pedia | passou a pedir | quem declara |
| --- | ----- | -------------- | ------------ |
| `LARGURA_MINIMA_DAS_ABAS` | 720 px | **500 px** | `qt/janela.py` |
| `LARGURA_MINIMA_DO_VISOR` | 520 px | **440 px** | `qt/janela.py` |
| a aba mais exigente (Galeria) | 711 x 800 | 54 x 54 (rola) | `qt/painel_da_galeria.py` |
| o painel de Resultado depois de ler | 301 x 1095 | 54 x 54 (rola) | `qt/painel_de_resultado.py` |

**A primeira rodada fechou a altura e deixou a largura escrita como dívida**, porque os dois
literais eram de um arquivo que outro executor estava reescrevendo na mesma sessão: `720 + 520 + 5`
de alça = **1245**, e a janela pedida a 1024x768 abria em 1245x768. A segunda rodada baixou os dois
para o que os painéis de fato pedem -- medido, `522` (a aba do Dataset) `+ 198` (o painel do PDF).

Estes testes cobram as duas metades: **nenhuma aba exige da janela mais do que uma tela de 1024x768
tem**, e **a janela pedida a 1024x768 abre a 1024x768**. O que resta acima disso é `PISO_MEDIDO`, e
ele só vale num caminho -- ver `test_o_piso_declarado_ainda_e_o_da_S_150`.
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

    def test_os_dois_literais_da_janela_cabem_na_tela_minima(self) -> None:
        """**É o caso que estava quebrado.** O piso de largura é `LARGURA_MINIMA_DAS_ABAS +
        LARGURA_MINIMA_DO_VISOR + alça`, e enquanto ele valia `720 + 520 + 5` a janela não tinha
        como caber numa tela de 1024 -- por mais que nenhum painel exigisse aquilo.

        A régua é a soma declarada e não um número cravado: no dia em que alguém subir um dos dois
        de volta, é aqui que se vê.
        """
        alca = self.janela.divisor.handleWidth()
        declarado = qt_janela.LARGURA_MINIMA_DAS_ABAS + qt_janela.LARGURA_MINIMA_DO_VISOR + alca
        self.assertLessEqual(declarado, TELA_MINIMA[0], "os dois literais voltaram a estourar 1024")
        self.assertGreaterEqual(self.janela.minimumSizeHint().width(), declarado)

    def test_a_largura_preferida_nao_e_o_piso(self) -> None:
        """**O piso diz onde a janela para, e não como ela abre.**

        Até esta rodada os dois números coincidiam nos dois lados, e o piso fazia dois trabalhos.
        Baixá-lo sem separar o preferido levava junto o arranjo de fábrica: medido a 1400x950, a
        aba de trabalho ia de 720 para 585 px e o tabuleiro da sala de 488 para 392.
        """
        self.assertGreater(qt_janela.LARGURA_PREFERIDA_DAS_ABAS, qt_janela.LARGURA_MINIMA_DAS_ABAS)
        self.assertGreater(qt_janela.LARGURA_PREFERIDA_DO_VISOR, qt_janela.LARGURA_MINIMA_DO_VISOR)

    def test_a_janela_larga_abre_na_largura_preferida_das_abas(self) -> None:
        """A 1400x950 a aba de trabalho recebe os 720 que pede, e não os 586 que 42% dariam --
        que é o arranjo que o piso de 720 dava de graça enquanto ele existia."""
        largura = sum(self.janela.divisor.sizes())
        self.assertEqual(
            qt_janela.LARGURA_PREFERIDA_DAS_ABAS,
            geometria.divisor_da_primeira_abertura(
                largura,
                preferida_esquerda=qt_janela.LARGURA_PREFERIDA_DAS_ABAS,
                preferida_direita=qt_janela.LARGURA_PREFERIDA_DO_VISOR,
            ),
        )
        # **O efeito, medido contra o que o outro lado exige** -- e não contra 720 cravado. Sob
        # `offscreen` não há a fonte da interface e a fileira de campo mede 810 px, então ali o
        # esquerdo recebe os 586 que sobram; na janela de verdade o mesmo código dá os 720
        # (medido a 1400x950: divisor [720, 675], tabuleiro da sala 488 px).
        sobra = largura - self.janela.lado_do_livro.minimumSizeHint().width()
        self.assertGreaterEqual(
            self.janela.divisor.sizes()[0],
            min(qt_janela.LARGURA_PREFERIDA_DAS_ABAS, sobra),
            "a aba de trabalho não recebeu a largura que pede",
        )

    def test_na_tela_minima_quem_cede_e_a_aba_e_nao_a_pagina(self) -> None:
        """Os dois preferidos somam 1240 e não cabem em 1024. **O empate se desfaz a favor do
        livro**: é a página que não se lê espremida, e a aba já rola desde a S-552."""
        esquerda = geometria.divisor_da_primeira_abertura(
            TELA_MINIMA[0],
            preferida_esquerda=qt_janela.LARGURA_PREFERIDA_DAS_ABAS,
            preferida_direita=qt_janela.LARGURA_PREFERIDA_DO_VISOR,
        )
        self.assertEqual(qt_janela.LARGURA_PREFERIDA_DO_VISOR, TELA_MINIMA[0] - esquerda)
        self.assertGreaterEqual(esquerda, qt_janela.LARGURA_MINIMA_DAS_ABAS)

    def test_o_piso_declarado_ainda_e_o_da_S_150(self) -> None:
        """**O que sobrou acima de 1024, e ele vale num caminho só.**

        `geometria.piso_da_janela` devolve o **maior** entre a soma das partes e `PISO_MEDIDO`
        (1180x800), que é o piso que a avaliação da S-150 obteve dirigindo a janela do Tk. Somadas,
        as partes hoje dão 1000 px -- abaixo da tela mínima --, e é `PISO_MEDIDO` que mantém a
        resposta em 1180.

        Isso **não** entra na janela: quem a segura é o `minimumSizeHint` do layout, e o teste
        acima o mede. O piso declarado só é usado por `geometria.geometria_a_aplicar`, e só quando
        a geometria guardada **não cabe mais nos monitores de hoje** -- o caso de perder um
        monitor. Fica registrado aqui com o número, porque nessa recuperação a janela ainda nasce
        maior que uma tela de 1024.
        """
        soma = qt_janela.LARGURA_MINIMA_DAS_ABAS + qt_janela.LARGURA_MINIMA_DO_VISOR
        self.assertLess(soma + geometria.CHROME_HORIZONTAL, TELA_MINIMA[0])
        piso = geometria.piso_da_janela(
            qt_janela.LARGURA_MINIMA_DAS_ABAS, qt_janela.LARGURA_MINIMA_DO_VISOR
        )
        self.assertEqual(geometria.PISO_MEDIDO, piso, "a soma das partes passou o piso da S-150")

    def test_pedida_a_tela_minima_a_janela_encolhe_ate_o_que_o_layout_pede(self) -> None:
        """**O critério do item, e é o que o crítico mediu**: pedida a 1024x768 ela ficava em
        1245x768 -- e 1245 era exatamente a soma dos dois literais, ou seja, o piso **não** vinha
        do conteúdo.

        **O número de tela não pode ser afirmado aqui**, e é a mesma ressalva do resto do arquivo:
        sob `offscreen` não há a fonte da interface e todo widget de texto mede mais -- a janela
        responde 1314 px de mínimo neste teste e **955** na janela de verdade, que é onde a
        medição do item foi feita (`probe_1024.py`, com o `windows11` e as fontes do sistema:
        pedida 1024x768 -> **1024x768**, piso 955x553, divisor [500, 519], as seis abas
        desenhando). O que se afirma aqui é que **nada além do que o layout pede** segura a
        janela, e que os dois pisos que chegam aos widgets são os declarados -- o teste acima é o
        que cobra que eles caibam em 1024.
        """
        self.janela.resize(*TELA_MINIMA)
        self.app.processEvents()
        self.assertEqual(TELA_MINIMA[1], self.janela.height(), "a altura pedida foi recusada")
        self.assertEqual(self.janela.minimumSizeHint().width(), self.janela.width())
        self.assertEqual(qt_janela.LARGURA_MINIMA_DAS_ABAS, self.janela.abas.minimumWidth())
        self.assertEqual(qt_janela.LARGURA_MINIMA_DO_VISOR, self.janela.pdf.minimumWidth())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
