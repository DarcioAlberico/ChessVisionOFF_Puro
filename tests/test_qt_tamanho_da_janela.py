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

import time
import unittest
from collections.abc import Callable

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, cor_em, descartar, renderizar
from test_engine import _launcher

from chess_diagram_ocr.engine import EngineAnalyzer
from chess_diagram_ocr.ui import galeria_declarada, geometria, pele, sala_declarada

if TEM_PYQT:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QGroupBox, QPushButton

    from chess_diagram_ocr.qt import janela as qt_janela
    from chess_diagram_ocr.qt import painel_da_galeria as qt_galeria
    from chess_diagram_ocr.qt import painel_de_resultado as qt_resultado
    from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
    from chess_diagram_ocr.qt import tema


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


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class GaleriaNaLarguraPreferidaTests(unittest.TestCase):
    """A Galeria em duas colunas na faixa em que cai toda tela de notebook (S-552, 4ª rodada).

    **A regressão, medida na janela de verdade em 2026-09-05.** De 1280 a 1700 px de janela o
    divisor dá ao lado das abas exatamente `LARGURA_PREFERIDA_DAS_ABAS`, e a aba fica com 714 px --
    o mesmo número em toda a faixa, porque a preferida é um teto. A barra de rolagem vertical come
    12, sobram **702** de viewport, e o limiar de 720 herdado do Tk disparava o empilhamento:
    conteúdo de 702x1358 com 692 px de rolagem vertical onde antes havia 714x848 sem rolagem
    nenhuma. E era uma trava -- empilhar dobra a altura, a barra que isso cria segura o viewport
    abaixo do limiar --, com as duas colunas só voltando em 1800 px de janela.

    **A faixa de janela não se reproduz sob `offscreen`, e o que importa dela se reproduz.** Sem as
    fontes do sistema o lado do livro pede 810 px de mínimo, e a 1400 o divisor dá 586 à aba em vez
    de 720; o que decide o arranjo, porém, não é a largura da janela e sim **a largura que a janela
    dá à aba**. Numa janela de 1700x700 o divisor entrega os mesmos `LARGURA_PREFERIDA_DAS_ABAS`
    que a janela de verdade entrega a 1280, e a altura de 700 põe a barra vertical na tela -- que é
    a metade do defeito que o número sozinho não mostra. Com os 720 antigos, esta classe empilha
    nas três peles.
    """

    JANELA = (1700, 700)
    """Offscreen, é a janela em que o divisor entrega à aba a largura preferida **e** a barra
    vertical aparece. A largura de janela é diferente da do notebook; a da aba é a mesma."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.raiz = pasta_temporaria(self)
        padrao = pele.PELES[0]
        self.addCleanup(
            lambda: tema.aplicar_tema(
                self.app, cromo_escuro=padrao.cromo_escuro, densidade=padrao.densidade
            )
        )

    def janela_na(self, uma: object) -> object:
        """A janela montada naquela pele, com a Galeria à frente."""
        tema.aplicar_tema(
            self.app,
            cromo_escuro=uma.cromo_escuro,  # type: ignore[attr-defined]
            densidade=uma.densidade,  # type: ignore[attr-defined]
        )
        self.app.processEvents()
        casa = self.raiz / str(uma.nome)  # type: ignore[attr-defined]
        janela = qt_janela.JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=casa / "rotulos.csv",
            pasta_de_estudos=casa / "estudos",
            pasta_da_galeria=casa / "galeria",
            caminho_do_estado=casa / "estado.json",
            motor=None,
        )
        janela.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.addCleanup(descartar, janela)
        janela.resize(*self.JANELA)
        janela.show()
        self.app.processEvents()
        for indice in range(janela.abas.count()):
            if janela.abas.tabText(indice).replace("&", "").startswith("Galeria"):
                janela.abas.setCurrentIndex(indice)
                break
        self.app.processEvents()
        self.app.processEvents()
        return janela

    def test_na_largura_preferida_a_galeria_fica_em_duas_colunas_nas_tres_peles(self) -> None:
        """**É a faixa de 1280 a 1700 px de janela**, reproduzida pela largura que ela dá à aba."""
        for uma in pele.PELES:
            with self.subTest(pele=uma.nome):
                janela = self.janela_na(uma)
                galeria = janela.galeria  # type: ignore[attr-defined]
                self.assertEqual(
                    qt_janela.LARGURA_PREFERIDA_DAS_ABAS,
                    janela.divisor.sizes()[0],  # type: ignore[attr-defined]
                    "a janela deixou de entregar a largura preferida à aba",
                )
                self.assertTrue(
                    galeria.rolagem.verticalScrollBar().isVisible(),
                    "sem a barra vertical na tela este teste não mede a trava",
                )
                lateral = galeria.lateral.mapTo(galeria, galeria.lateral.rect().topLeft())
                recorte = galeria.recorte.mapTo(galeria, galeria.recorte.rect().topLeft())
                self.assertEqual(lateral.y(), recorte.y(), "a Galeria empilhou numa aba que comporta duas colunas")
                self.assertEqual(
                    0, galeria.rolagem.horizontalScrollBar().maximum(), "as duas colunas não couberam"
                )

    def test_a_largura_preferida_das_abas_cobre_o_que_a_galeria_ocupa(self) -> None:
        """**A invariante que faltava, e ela liga os dois números que se desencontraram.**

        A aba não recebe `LARGURA_PREFERIDA_DAS_ABAS`: recebe isso menos a moldura do `QTabWidget`,
        e o corpo da Galeria recebe menos ainda -- a moldura da área de rolagem e a barra vertical.
        Enquanto a preferida (720) e o limiar (720) fossem o mesmo número, a conta **nunca** fechava,
        e nada no projeto dizia isso. Os dois lados são medidos aqui: quem subir o limiar ou baixar
        a preferida vê a diferença nesta linha, e não numa foto seis rodadas depois.
        """
        janela = self.janela_na(pele.PELES[0])
        galeria = janela.galeria  # type: ignore[attr-defined]
        cromo_da_aba = janela.divisor.sizes()[0] - galeria.width()  # type: ignore[attr-defined]
        rolagem = galeria.rolagem
        cromo_da_rolagem = 2 * rolagem.frameWidth() + rolagem.verticalScrollBar().sizeHint().width()
        self.assertGreaterEqual(
            qt_janela.LARGURA_PREFERIDA_DAS_ABAS - cromo_da_aba - cromo_da_rolagem,
            galeria_declarada.LARGURA_MINIMA_DA_GALERIA,
            "a largura preferida das abas deixou de caber as duas colunas da Galeria",
        )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SalaA1024SemMotorTests(unittest.TestCase):
    """A régua da leitura só **desce** exigência, e nunca sobe a de quem pede pouco (S-552, 4ª).

    **A regressão da terceira rodada, e ela custou 53 px de tabuleiro.** `piso_da_leitura` foi
    escrita para baixar os 386 px que o `QGroupBox` da seção do motor exige; aplicada em
    `setMinimumWidth`, ela é piso nos dois sentidos, e onde a coluna pedia **menos** ela subia a
    exigência. Medido na janela de verdade sem motor: a coluna pede 136 px, a régua os punha em
    192, e o tabuleiro caía de 298 para **245** px a 1024x768 -- de 301 para 245 na pele fita,
    menos 18% -- e de 454 para 447 a 1400x950. Nenhuma dessas trocas estava declarada.

    **A sala sem motor é o caso do achado**, e é por isso que ela ganhou classe própria: é ali que
    a coluna pede pouco. Com o motor a seção dele empurra o pedido para cima, e a régua volta a
    ser o que baixa -- que é o caso da classe seguinte.
    """

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
        self.janela.resize(*TELA_MINIMA)
        self.janela.show()
        self.app.processEvents()
        # Os mesmos 500 px de `SalaA1024ComMotorTests`, e pela mesma razão: é o que a janela de
        # verdade dá ao lado das abas a 1024, e o que a fonte de queda faria variar entre rodar o
        # arquivo sozinho e rodar a suíte.
        largura = sum(self.janela.divisor.sizes())
        self.janela.divisor.setSizes(
            [qt_janela.LARGURA_MINIMA_DAS_ABAS, max(1, largura - qt_janela.LARGURA_MINIMA_DAS_ABAS)]
        )
        self.app.processEvents()
        self.sala = self.janela.estudo
        for indice in range(self.janela.abas.count()):
            if self.janela.abas.tabText(indice).replace("&", "").startswith("Estudo"):
                self.janela.abas.setCurrentIndex(indice)
                break
        self.app.processEvents()

    def test_a_regua_da_leitura_nao_sobe_o_minimo_de_quem_pede_pouco(self) -> None:
        """**O regime é reproduzido, e não afirmado por número.** Sob `offscreen` não há a fonte da
        interface e a coluna pede 262 px -- acima do teto --, então ali o defeito não aparece
        sozinho: o que a fonte de verdade faz é a coluna pedir menos. O teste encolhe o pedido
        (títulos e caixas de texto) e cobra que o mínimo aplicado seja **o pedido**, e não o teto.
        """
        coluna = self.sala.divisor_vertical
        teto = sala_declarada.piso_da_leitura(
            sum(self.sala.divisor.sizes()),
            minimo=self.sala._caixa_minima_do_tabuleiro(),
            esteira=self.sala._esteira_da_coluna(),
            alca=max(1, self.sala.divisor.handleWidth()),
        )
        self.assertEqual(
            min(teto, coluna.minimumSizeHint().width()),
            coluna.minimumWidth(),
            "o mínimo da coluna deixou de ser o menor entre o teto da régua e o que ela pede",
        )
        for grupo in coluna.findChildren(QGroupBox):
            if grupo.parentWidget() is coluna:
                grupo.setTitle("")
        self.sala.lista.setMinimumWidth(1)
        self.sala.comentario.setMinimumWidth(1)
        self.app.processEvents()
        self.sala._acomodar_o_tabuleiro()
        self.app.processEvents()
        pedido = coluna.minimumSizeHint().width()
        self.assertLess(pedido, teto, "o regime da janela de verdade não foi reproduzido")
        self.assertEqual(pedido, coluna.minimumWidth(), "a régua subiu o mínimo de quem pedia pouco")

    def test_o_tabuleiro_sem_motor_nao_encolhe_e_nao_sai_cortado(self) -> None:
        """A outra ponta do mesmo achado: o que a régua tomava da coluna saía do tabuleiro.

        O número de tela não se afirma sob `offscreen` -- a fonte é outra e o tabuleiro mede 244 px
        aqui contra 298 na janela de verdade. O que se afirma é a **relação**: o tabuleiro fica com
        o que `lado_do_tabuleiro` prevê para a coluna que ele recebeu, e nada além do pedido da
        leitura sai dele.
        """
        tabuleiro = self.sala.tabuleiro
        self.assertEqual(
            tabuleiro.width(),
            tabuleiro.visibleRegion().boundingRect().width(),
            "o tabuleiro saiu cortado sem motor nenhum ligado",
        )
        self.assertGreaterEqual(tabuleiro.geometria().size, qt_tabuleiro.LADO_MINIMO)
        coluna = self.sala.divisor_vertical
        self.assertLessEqual(
            coluna.minimumWidth(),
            coluna.minimumSizeHint().width(),
            "a coluna de leitura exige mais do que ela própria pede",
        )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SalaA1024ComMotorTests(unittest.TestCase):
    """A 1024 o tabuleiro da sala não é cortado pela barra de avaliação (S-551, terceira rodada).

    **O que o crítico mediu na janela de verdade a 1024x768, com o motor ligado**: o widget do
    tabuleiro pedia 240 px e **203** apareciam -- 36 px cortados pela borda da coluna. Sumia a
    coluna `h`, sumiam as duas réguas de coordenadas, e os quatro botões de navegação quebravam em
    duas fileiras. E não voltava: nem redimensionando a janela, nem desligando o motor.

    **O teste mora aqui, e não em `test_qt_motor.py`, porque o aperto é da janela.** A aba Estudo
    fica com **496 px** numa janela de 1024 -- `LARGURA_MINIMA_DAS_ABAS` é 500 e é o que o divisor
    dá ao lado das abas nessa largura --, e um `PainelDeEstudo` solto não chega lá: o mínimo dele
    recusa o `resize`, o divisor sobra, e a mesma medição passa em verde com o defeito de pé.
    Medido: painel solto a 496 px responde `[338, 210]` de divisor; dentro da janela, `[320, 160]`.

    **Por que a prova é de pixel e não de `width()`.** Um widget cortado continua respondendo a
    largura que ele pediu, e `grab()` **nele** desenha os 240 inteiros. Quem sabe o que apareceu é
    o desenho do painel: as casas da coluna `h` ou estão pintadas nele, ou ficaram do lado de fora.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        raiz = pasta_temporaria(self)
        self.motor = EngineAnalyzer(_launcher(type(self)), movetime_ms=100)
        self.addCleanup(self.motor.close)
        self.janela = qt_janela.JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=raiz / "rotulos.csv",
            pasta_de_estudos=raiz / "estudos",
            pasta_da_galeria=raiz / "galeria",
            caminho_do_estado=raiz / "estado.json",
            motor=self.motor,
        )
        self.janela.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.addCleanup(descartar, self.janela)
        self.janela.resize(*TELA_MINIMA)
        self.janela.show()
        self.app.processEvents()
        # **O divisor da janela é posto à mão no piso do lado das abas**, e não deixado por conta
        # do `showEvent`. Sob `offscreen` a largura mínima da janela depende da fonte de queda e do
        # que os testes vizinhos deixaram na densidade: rodando sozinho este arquivo mede a aba em
        # 496 px, e na suíte inteira ela mediu 529 -- perto demais do limite para uma medição de
        # aperto. Os 500 px são `LARGURA_MINIMA_DAS_ABAS`, que é o que a janela de verdade dá ao
        # lado das abas a 1024 (S-552); pô-los aqui é reproduzir a janela do crítico, não simulá-la.
        largura = sum(self.janela.divisor.sizes())
        self.janela.divisor.setSizes(
            [qt_janela.LARGURA_MINIMA_DAS_ABAS, max(1, largura - qt_janela.LARGURA_MINIMA_DAS_ABAS)]
        )
        self.app.processEvents()
        self.sala = self.janela.estudo
        self.janela.abas.setCurrentIndex(self._aba("Estudo"))
        self.app.processEvents()

    def _aba(self, nome: str) -> int:
        for indice in range(self.janela.abas.count()):
            if self.janela.abas.tabText(indice).replace("&", "").startswith(nome):
                return indice
        raise AssertionError(f"a aba {nome!r} não existe")

    def _girar(self, condicao: Callable[[], bool], limite_s: float = 5.0) -> bool:
        fim = time.monotonic() + limite_s
        while time.monotonic() < fim:
            self.app.processEvents()
            if condicao():
                return True
            time.sleep(0.005)
        return False

    def ligar_a_analise(self) -> None:
        """Liga a análise contínua e **garante que ela pare** antes de a janela ser destruída.

        Um `QThread` destruído rodando derruba o processo inteiro e leva os testes seguintes junto
        (ver o cabeçalho de `tests/qt_app.py`). A limpeza entra depois da da janela, e por isso
        roda antes dela.
        """
        self.sala.alternar_analise_continua()
        self.addCleanup(self.parar_a_analise)
        self.assertTrue(self._girar(lambda: bool(self.sala._candidatos)))

    def parar_a_analise(self) -> None:
        if self.sala.btn_continua is not None and self.sala.btn_continua.isChecked():
            self.sala.alternar_analise_continua()
        self._girar(lambda: not self.sala._analysing)

    def _no_painel(self, x: float, y: float) -> QPoint:
        return self.sala.tabuleiro.mapTo(self.sala, QPoint(int(x), int(y)))

    def _tinta_na_faixa(self, imagem: object, x0: int, y0: int, x1: int, y1: int) -> int:
        """Quantos pixels da faixa diferem do canto dela. A régua desenha texto; sob `offscreen`
        ele sai como retângulo, e é tinta do mesmo jeito -- o que **não** se pode é comparar glifo
        com glifo (ver `ui/desenho_do_tabuleiro.reguas`)."""
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(imagem.width(), x1), min(imagem.height(), y1)  # type: ignore[attr-defined]
        if x1 <= x0 or y1 <= y0:
            return 0
        fundo = cor_em(imagem, x0, y0)
        return sum(1 for x in range(x0, x1) for y in range(y0, y1) if cor_em(imagem, x, y) != fundo)

    def test_a_aba_de_estudo_e_o_caso_apertado(self) -> None:
        """O controle do arquivo: se a aba deixar de ser estreita, os testes abaixo param de medir
        o que dizem medir.

        **Apertado tem definição**, e não é uma largura em pixel: é a aba em que o piso do
        tabuleiro (a caixa dele mais a esteira da coluna) e o piso da leitura **não cabem juntos**.
        É o regime em que o `QSplitter` não consegue atender nenhum dos dois lados e reparte meio a
        meio -- que é onde o tabuleiro saía cortado.
        """
        self.assertEqual(qt_janela.LARGURA_MINIMA_DAS_ABAS, self.janela.divisor.sizes()[0])
        precisam = (
            self.sala._caixa_minima_do_tabuleiro()
            + self.sala._esteira_da_coluna()
            + sala_declarada.LARGURA_MINIMA_DA_LEITURA
            + self.sala.divisor.handleWidth()
        )
        self.assertLess(
            sum(self.sala.divisor.sizes()),
            precisam,
            "a aba Estudo deixou de ser o caso apertado: os dois pisos passaram a caber",
        )

    def test_a_coluna_h_aparece_com_o_motor_ligado(self) -> None:
        """h1 e h8 pintadas dentro do desenho do painel, e em cores diferentes uma da outra --
        casas da mesma coluna alternam."""
        self.ligar_a_analise()
        desenho = renderizar(self.sala)
        geo = self.sala.tabuleiro.geometria()
        cantos = []
        for linha in (0, 7):
            x0, y0, x1, y1 = geo.rect(linha, 7)
            cantos.append(self._no_painel((x0 + x1) / 2, (y0 + y1) / 2))
        for ponto, nome in zip(cantos, ("h8", "h1"), strict=True):
            with self.subTest(casa=nome):
                self.assertLess(ponto.x(), self.sala.width(), f"{nome} caiu fora do painel")
                self.assertLess(ponto.y(), self.sala.height(), f"{nome} caiu fora do painel")
        self.assertNotEqual(
            cor_em(desenho, cantos[0].x(), cantos[0].y()),
            cor_em(desenho, cantos[1].x(), cantos[1].y()),
            "h1 e h8 saíram da mesma cor: a coluna h não foi desenhada",
        )

    def test_as_duas_reguas_aparecem_com_o_motor_ligado(self) -> None:
        """**As faixas são medidas em coordenadas do próprio tabuleiro**, e é o que separa esta
        guarda de uma vácua: tomá-las a partir de `origin_x - MARGEM` faz a da esquerda cair fora
        do widget, em cima da barra de avaliação, e contar a tinta **dela**.

        A régua de linhas é escrita em `origin_x - 11`: sem `MARGEM/2` de folga à esquerda do
        quadriculado, ela não tem onde ser desenhada. Era o que acontecia com o piso cru de 240 px
        -- as letras `a`..`h` apareciam e os números `1`..`8` não.
        """
        self.ligar_a_analise()
        desenho = renderizar(self.sala)
        tabuleiro = self.sala.tabuleiro
        geo = tabuleiro.geometria()
        folga = qt_tabuleiro.MARGEM / 2
        self.assertGreaterEqual(geo.origin_x, folga, "não sobrou margem para a régua de linhas")
        self.assertLessEqual(
            geo.origin_y + geo.size + folga, tabuleiro.height(), "não sobrou margem para as colunas"
        )
        faixas = {
            "linhas": (0.0, geo.origin_y, geo.origin_x, geo.origin_y + geo.size),
            "colunas": (
                geo.origin_x,
                geo.origin_y + geo.size,
                geo.origin_x + geo.size,
                geo.origin_y + geo.size + folga,
            ),
        }
        for nome, (x0, y0, x1, y1) in faixas.items():
            alto, baixo = self._no_painel(x0, y0), self._no_painel(x1, y1)
            with self.subTest(regua=nome):
                self.assertLessEqual(baixo.x(), self.sala.width(), "a régua passou da borda")
                self.assertLessEqual(baixo.y(), self.sala.height())
                self.assertGreater(
                    self._tinta_na_faixa(desenho, alto.x(), alto.y(), baixo.x(), baixo.y()),
                    0,
                    f"a régua de {nome} não pintou nada",
                )

    def test_o_tabuleiro_nao_e_cortado_e_religar_o_motor_nao_deixa_residuo(self) -> None:
        """**"E não volta" era metade do achado.** O mínimo do `QGroupBox` da seção do motor cresce
        quando ela ganha texto -- 266 px para **386** -- e não volta a encolher quando o motor é
        desligado. O piso da leitura passa a ser declarado por `sala_declarada.piso_da_leitura`,
        que não depende do que o `QGroupBox` responde.
        """
        momentos = ("antes", "com o motor", "sem o motor", "com o motor de novo")
        for volta, rotulo in enumerate(momentos):
            if volta == 1:
                self.ligar_a_analise()
            elif volta:
                self.sala.alternar_analise_continua()
                self._girar(lambda: False, 0.3)
            with self.subTest(momento=rotulo):
                tabuleiro = self.sala.tabuleiro
                visivel = tabuleiro.visibleRegion().boundingRect().width()
                self.assertEqual(tabuleiro.width(), visivel, f"o tabuleiro saiu cortado {rotulo}")
                self.assertGreaterEqual(tabuleiro.geometria().size, qt_tabuleiro.LADO_MINIMO)

    def test_os_quatro_botoes_de_navegacao_ficam_na_mesma_fileira(self) -> None:
        """Eles quebravam em duas porque o que sobrava da coluna eram 203 px."""
        faixa = self.sala.lbl_lance.parentWidget()
        assert faixa is not None
        botoes = list(faixa.findChildren(QPushButton))[:4]
        self.assertEqual(4, len(botoes), "a faixa de navegação não tem os quatro botões")
        alturas = {b.mapTo(self.sala, b.rect().topLeft()).y() for b in botoes}
        self.assertEqual(1, len(alturas), f"os quatro botões saíram em {len(alturas)} fileiras")

    def test_a_esteira_da_coluna_conta_a_barra_de_avaliacao(self) -> None:
        """Ela é medida e não cravada: são as margens da coluna mais a barra e o vão até ela."""
        coluna = self.sala.divisor.widget(0)
        assert coluna is not None and coluna.layout() is not None
        margens = coluna.layout().contentsMargins()
        faixa = self.sala._faixa_do_tabuleiro
        assert faixa is not None and self.sala.vantagem is not None
        self.assertEqual(
            self.sala._esteira_da_coluna(),
            margens.left()
            + margens.right()
            + self.sala.vantagem.sizeHint().width()
            + faixa.spacing(),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
