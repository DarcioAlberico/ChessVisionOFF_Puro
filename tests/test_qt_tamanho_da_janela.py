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
from chess_diagram_ocr.ui import (
    estado_do_rodape,
    galeria_declarada,
    geometria,
    pele,
    sala_declarada,
    state,
)

if TEM_PYQT:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtGui import QFont
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
        responde **955** na de verdade, que é onde a medição do item foi feita (`probe_1024.py`,
        com o `windows11` e as fontes do sistema: pedida 1024x768 -> **1024x768**, piso 955x553,
        divisor [500, 519], as seis abas desenhando). O que se afirma aqui é que **nada além do
        que o layout pede** segura a janela, e que os dois pisos que chegam aos widgets são os
        declarados -- o teste acima é o que cobra que eles caibam em 1024.

        **A resposta é `max(pedida, piso)` e não o piso cravado, e a mudança é da quinta rodada.**
        Este teste afirmava `piso == largura`, o que só é verdade quando o piso passa de 1024 --
        e sob `offscreen` ele passa **ou não**, conforme a fila de botões do painel de PDF já ter
        refluído: o `minimumSizeHint` dela responde 810 px antes do primeiro refluxo e 172 depois,
        e isso muda com o que rodou antes neste processo. Rodando o arquivo sozinho o piso dava
        1314; na suíte inteira, 1000.

        **E ele passava, na suíte inteira, por causa do defeito que a quinta rodada tirou.** Com a
        frase do rodapé exigindo a largura do texto, o piso da janela naquele instante era 1057 --
        acima de 1024 --, a janela era grampeada nele, e a igualdade fechava. Removida a exigência,
        o piso caiu para os 1000 do divisor, a janela passou a **receber os 1024 que pediu**, e a
        igualdade quebrou com `1000 != 1024`: era uma guarda verde porque a mensagem estava
        segurando a janela. A afirmação de agora vale nos dois regimes e continua dizendo o mesmo:
        nada além do layout a segura.
        """
        self.janela.resize(*TELA_MINIMA)
        self.app.processEvents()
        self.assertEqual(TELA_MINIMA[1], self.janela.height(), "a altura pedida foi recusada")
        piso = self.janela.minimumSizeHint().width()
        self.assertEqual(
            max(TELA_MINIMA[0], piso),
            self.janela.width(),
            f"a janela ficou em {self.janela.width()} px com o layout pedindo {piso} e a tela mínima "
            f"{TELA_MINIMA[0]} -- alguma coisa fora do layout a está segurando "
            f"(rodapé {self.janela.rodape.minimumSizeHint().width()}, "
            f"divisor {self.janela.divisor.minimumSizeHint().width()}, "
            f"cromo {self.janela.cromo.minimumSizeHint().width()})",
        )
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


class RodapeNaoEPisoDeJanelaTests(unittest.TestCase):
    """A frase do rodapé deixou de segurar a janela (S-552, quinta rodada).

    **O bloqueio, medido na janela de verdade a 1024x768.** `RodapeDaJanela._lbl_mensagem` era um
    `QLabel` sem quebra de linha, e o mínimo de um rótulo assim é a largura do texto inteiro. Ele
    subia pelo leiaute do rodapé e virava piso da janela: com frases de 120, 200, 300, 600 e 2000
    caracteres o piso ia a **1057, 1457, 1957, 3457 e 10457 px**, e `resize(1024, 768)` era recusado
    até chegar uma frase menor.

    E o caminho é o do produto: o erro de modelo ausente tem cerca de 600 caracteres e é escrito
    por `_falhou` -> `_dizer`. No percurso de ponta a ponta do crítico ele pôs a janela em **2906
    px** -- a mensagem que ensina a consertar o modelo tornava a janela maior que a tela e a si
    mesma ilegível.

    **Nas três peles**, porque o que muda entre elas é a fonte, e era a fonte que multiplicava.
    """

    FRASES = (120, 600, 2000)
    """Os três tamanhos do critério. 120 é a menor frase que já estourava 1024; 2000 é absurda de
    propósito -- se o piso não se mexer com ela, ele não depende mais do texto."""

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
        janela.resize(*TELA_MINIMA)
        janela.show()
        self.app.processEvents()
        return janela

    @staticmethod
    def frase_de(tamanho: int) -> str:
        """Uma frase de erro do tamanho pedido, com o começo que o produto de fato escreve."""
        comeco = "Não foi possível carregar o modelo de peças: "
        return (comeco + "detalhe " * tamanho)[:tamanho]

    def test_o_piso_da_janela_nao_muda_com_o_tamanho_da_frase(self) -> None:
        """**O bloqueio.** O piso é lido antes e depois de cada frase, e tem de ser o mesmo número.

        Comparado consigo mesmo e não com um valor cravado: sob `offscreen` não há a fonte da
        interface e o piso é outro -- 1314 px, contra 955 na janela de verdade. O que o defeito
        fazia era **variar**, e é a variação que se afirma aqui.
        """
        for uma in pele.PELES:
            with self.subTest(pele=uma.nome):
                janela = self.janela_na(uma)
                piso = janela.minimumSizeHint().width()  # type: ignore[attr-defined]
                for tamanho in self.FRASES:
                    janela._dizer(self.frase_de(tamanho))  # type: ignore[attr-defined]
                    self.app.processEvents()
                    self.assertEqual(
                        piso,
                        janela.minimumSizeHint().width(),  # type: ignore[attr-defined]
                        f"uma frase de {tamanho} caracteres mexeu no piso da janela",
                    )

    def test_a_janela_com_a_frase_de_erro_aceita_o_tamanho_pedido(self) -> None:
        """O outro lado do mesmo defeito: o piso subia, e com ele a janela **crescia sozinha**.

        A régua é a largura que a janela aceita sem a frase, e não 1024: offscreen o piso do layout
        é maior que a tela mínima (ver o teste acima). O que se afirma é que a frase não acrescenta
        um pixel a ele.
        """
        janela = self.janela_na(pele.PELES[0])
        janela.resize(*TELA_MINIMA)  # type: ignore[attr-defined]
        self.app.processEvents()
        sem_frase = janela.width()  # type: ignore[attr-defined]
        janela._dizer(self.frase_de(2000))  # type: ignore[attr-defined]
        self.app.processEvents()
        janela.resize(*TELA_MINIMA)  # type: ignore[attr-defined]
        self.app.processEvents()
        self.assertEqual(sem_frase, janela.width(), "a frase longa recusou o tamanho pedido")  # type: ignore[attr-defined]

    def test_a_zona_declarada_cabe_na_folga_do_rodape_nas_tres_peles(self) -> None:
        """**A invariante que a S-552 nomeia, e que ninguém afirmava** (sexta rodada).

        *"Ele não sobe o piso da janela"* é o que faz de `LARGURA_MINIMA_DA_MENSAGEM` um teto e não
        uma exigência nova, e era uma frase de spec sem guarda: a constante podia ir a 900 e só um
        teste de elisão caía. Medido na janela de verdade a 1024x768, o resto do rodapé pede **443
        px** (clássica e "Foco") e **431** ("Fita"); o piso do divisor é **955** e **945**. A zona
        pode pedir até **512** px (514 na "Fita") antes de o piso subir, e ela pede 100.

        **Os dois lados são medidos e não cravados**, e é o que faz a guarda valer nas duas ordens
        de execução. O resto do rodapé sai de encolher a zona a 1 px e descontar esse pixel -- quem
        o compõe, as três outras zonas mais a barra e o botão, muda de largura com a fonte e com a
        densidade --, e o piso do divisor é o do arquivo rodando sozinho (1314 px) ou o da suíte
        inteira (1000), conforme o refluxo da fila de botões do PDF já tenha acontecido. Sob
        `offscreen` o resto é 693 px, e um literal de qualquer um dos dois lados seria uma guarda
        que acusa em metade das corridas.
        """
        for uma in pele.PELES:
            with self.subTest(pele=uma.nome):
                janela = self.janela_na(uma)
                zona = janela.rodape._lbl_mensagem  # type: ignore[attr-defined]
                declarado = zona.minimumWidth()
                self.assertEqual(estado_do_rodape.LARGURA_MINIMA_DA_MENSAGEM, declarado)
                piso_com_a_zona = janela.minimumSizeHint().width()  # type: ignore[attr-defined]
                zona.setMinimumWidth(1)
                self.app.processEvents()
                resto = janela.rodape.minimumSizeHint().width() - 1  # type: ignore[attr-defined]
                self.assertEqual(
                    piso_com_a_zona,
                    janela.minimumSizeHint().width(),  # type: ignore[attr-defined]
                    "a zona declarada já está segurando o piso da janela",
                )
                zona.setMinimumWidth(declarado)
                self.app.processEvents()
                self.assertLess(
                    resto + estado_do_rodape.LARGURA_MINIMA_DA_MENSAGEM,
                    janela.divisor.minimumSizeHint().width(),  # type: ignore[attr-defined]
                    "o rodapé com a zona declarada passou a pedir mais que o divisor",
                )

    def test_a_troca_de_pele_refaz_a_elisao(self) -> None:
        """A pele nova traz outra fonte, e o que cabia na anterior pode não caber mais (S-393).

        **A cor era resolvida na hora de escrever e nunca mais, e o recorte também.** A elisão é
        refeita em `_repintar_mensagem` pela mesma razão que a cor: as duas foram resolvidas na
        hora de escrever, e a hora de escrever passou. Sem ela a frase fica recortada na fonte da
        pele anterior -- sobrando tarja vazia, ou estourando a zona -- e a suíte fica verde.

        **O regime é reproduzido, e não afirmado por número.** Sob `offscreen` não há as fontes das
        peles: as três respondem a mesma métrica, e o que muda entre elas é só a densidade -- que
        mexe na *largura* da zona e, por aí, dispara o `resizeEvent`, que reelidiria sozinho. O
        teste trava a largura e troca a fonte à mão, que é o que a pele de verdade faz: assim a
        única coisa que pode refazer o recorte é a repintura.
        """
        janela = self.janela_na(pele.PELES[0])
        frase = self.frase_de(600)
        janela._dizer(frase)  # type: ignore[attr-defined]
        self.app.processEvents()
        zona = janela.rodape._lbl_mensagem  # type: ignore[attr-defined]
        # **Travar a largura não basta, e foi assim que esta guarda nasceu vácua** (S-552,
        # sétima rodada). Aplicar a pele muda a altura do rótulo de 22 para 24 px, o
        # `resizeEvent` dispara por causa disso, e `_reescrever` refaz o recorte sozinha --
        # de modo que o teste passava com e sem `_repintar_mensagem`. Travar os dois lados é
        # o que deixa a repintura ser a única coisa que pode refazer o recorte.
        zona.setFixedSize(zona.width(), zona.height())
        self.app.processEvents()
        antes = zona.text()
        maior = QFont(zona.font())
        maior.setPointSize(max(2, zona.font().pointSize()) * 2)
        zona.setFont(maior)
        self.app.processEvents()
        self.assertEqual(antes, zona.text(), "a fonte sozinha já refez o recorte: o regime é outro")
        outra = pele.PELES[-1]
        tema.aplicar_tema(self.app, cromo_escuro=outra.cromo_escuro, densidade=outra.densidade)
        self.app.processEvents()
        self.assertLess(
            len(zona.text()),
            len(antes),
            "a troca de pele não refez a elisão: a frase ficou recortada na fonte da pele anterior",
        )
        self.assertTrue(
            frase.startswith(zona.text().rstrip("…")),
            f"a elisão comeu o começo da frase: {zona.text()!r}",
        )

    def test_a_frase_elidida_guarda_o_comeco_e_a_dica_traz_o_texto_inteiro(self) -> None:
        """**O começo é o que importa numa frase de erro**: é dele que sai a severidade, e é ele
        que diz o que falhou. O resto não some -- vai para a dica."""
        janela = self.janela_na(pele.PELES[0])
        frase = self.frase_de(600)
        janela._dizer(frase)  # type: ignore[attr-defined]
        self.app.processEvents()
        zona = janela.rodape._lbl_mensagem  # type: ignore[attr-defined]
        self.assertEqual(frase, janela.rodape.mensagem(), "o rodapé esqueceu a frase inteira")  # type: ignore[attr-defined]
        self.assertEqual(frase, zona.toolTip(), "a dica não traz o texto inteiro")
        self.assertNotEqual(frase, zona.text(), "a frase de 600 caracteres coube sem elidir?")
        self.assertTrue(
            frase.startswith(zona.text().rstrip("\u2026")),
            f"a elisão comeu o começo da frase: {zona.text()!r}",
        )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ColunaQueEncolheNaJanelaTests(unittest.TestCase):
    """O ciclo de crescer e encolher devolve o piso à coluna de leitura (S-551, sexta rodada).

    **A guarda que faltava, e é o defeito mais perigoso da base.** `ColunaQueEncolheTests`, em
    `tests/test_ui_sala_declarada.py`, prova que a régua pura sabe o que fazer com
    `largura_anterior`; nada provava que o painel **lhe passa** esse argumento. Tirada a linha
    `self._largura_acomodada = largura` de `qt/painel_de_estudo.py`, o degrau da quinta rodada
    volta -- a coluna de leitura cai de 203 para 183 px depois de 1400 -> 1600 -> 1400 -- e a suíte
    inteira fica verde.

    **Contra a janela montada, e não contra um painel solto.** É a armadilha que a S-551 já
    registra duas vezes: fora da janela o painel não recebe a largura que a aba lhe daria, o
    divisor sobra, e a mesma medição passa em verde com o defeito de pé.

    **O regime é reproduzido, e não afirmado por número** -- é a mesma disciplina de
    `SalaA1024SemMotorTests`. Sob `offscreen` não há a fonte da interface e a coluna de leitura pede
    262 px, acima do teto de `LARGURA_MINIMA_DA_LEITURA`: com esse pedido o `setMinimumWidth` do
    painel sozinho já impede o `QSplitter` de encolhê-la, e o degrau não aparece. O que a fonte de
    verdade faz é a coluna pedir **menos** que o teto (136 px medidos na janela de verdade sem
    motor), e é ali que o `QSplitter` tem para onde tomar. O teste encolhe o pedido e então cobra o
    piso.

    **E o piso cobrado é o que a régua declara para aquela largura**, lido na hora e não cravado:
    numa coluna apertada `piso_da_leitura` cede abaixo dos 210 declarados, como ela sempre cedeu, e
    um 210 literal mediria o aperto em vez do degrau.
    """

    CICLOS = ((1400, 1600), (1920, 2120))
    """As duas idas e voltas que o crítico mediu na janela de verdade: a leitura ficava em 183 px
    depois da primeira e em 190 depois da segunda, e estacionava ali."""

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
        self.janela.resize(self.CICLOS[0][0], 950)
        self.janela.show()
        self.app.processEvents()
        self.sala = self.janela.estudo
        for indice in range(self.janela.abas.count()):
            if self.janela.abas.tabText(indice).replace("&", "").startswith("Estudo"):
                self.janela.abas.setCurrentIndex(indice)
                break
        self.app.processEvents()
        self.encolher_o_pedido_da_coluna()

    def encolher_o_pedido_da_coluna(self) -> None:
        """Põe a coluna a pedir menos que o teto -- que é o que a fonte de verdade faz.

        **E solta o mínimo da coluna do tabuleiro, pela mesma razão.** Sob `offscreen` o mínimo
        que ela própria declara *sobe* depois de a janela ter sido larga -- medido, de 343 para
        369 px, e ele não desce mais --, e o `QSplitter` não pode dar à leitura mais do que a
        outra coluna larga: de volta a 1400 sobram 197 px numa sala de 566, abaixo dos 210 que a
        régua declara. Na janela de verdade a coluna do tabuleiro pede ~280 px numa sala de ~700 e
        essa folga nunca é quem manda. Sem soltá-lo, o que este teste mediria é o mínimo do
        vizinho, e não o degrau.
        """
        coluna = self.sala.divisor_vertical
        for grupo in coluna.findChildren(QGroupBox):
            if grupo.parentWidget() is coluna:
                grupo.setTitle("")
        self.sala.lista.setMinimumWidth(1)
        self.sala.comentario.setMinimumWidth(1)
        do_tabuleiro = self.sala.divisor.widget(0)
        if do_tabuleiro is not None:
            do_tabuleiro.setMinimumWidth(1)
        self.app.processEvents()
        self.sala._acomodar_o_tabuleiro()
        self.app.processEvents()

    def piso_de_agora(self) -> int:
        """O piso que a régua declara para a coluna que a sala tem **neste** instante."""
        return sala_declarada.piso_da_leitura(
            sum(self.sala.divisor.sizes()),
            minimo=self.sala._caixa_minima_do_tabuleiro(),
            esteira=self.sala._esteira_da_coluna(),
            alca=max(1, self.sala.divisor.handleWidth()),
        )

    def em(self, largura: int) -> int:
        self.janela.resize(largura, 950)
        self.app.processEvents()
        return self.sala.divisor_vertical.width()

    def test_a_coluna_pede_menos_que_o_teto_como_na_janela_de_verdade(self) -> None:
        """O controle do arquivo: sem este regime o teste seguinte passa em verde com o defeito.

        Com a coluna pedindo mais que o teto, o próprio `setMinimumWidth` do painel a segura e o
        `QSplitter` não tem de onde tomar -- e o degrau, que é do lado que **cede**, não acontece.
        """
        pedido = self.sala.divisor_vertical.minimumSizeHint().width()
        self.assertLess(pedido, self.piso_de_agora(), "o regime da janela de verdade não foi reproduzido")

    def test_o_ciclo_de_crescer_e_encolher_devolve_o_piso_a_leitura(self) -> None:
        """**A promessa é sobre pixel de tabuleiro, e ela estava guardada em fração.**

        Encolhida a janela, o `QSplitter` reparte em proporção *antes* de a régua rodar: a fração de
        uma coluna larga chega intacta a uma estreita e compra ali mais tabuleiro do que a estreita
        tem para vender. Quem paga é a coluna de leitura, e ela não volta -- é um degrau, e não um
        acúmulo.
        """
        for ida, volta in self.CICLOS:
            with self.subTest(ciclo=f"{ida}->{volta}->{ida}"):
                self.em(ida)
                self.em(volta)
                de_volta = self.em(ida)
                self.assertGreaterEqual(
                    de_volta,
                    self.piso_de_agora(),
                    "a coluna de leitura voltou abaixo do piso depois de a janela crescer e encolher",
                )


class ReparticaoAoRedimensionarTests(unittest.TestCase):
    """A repartição preferida vale ao redimensionar, e não só ao abrir (S-552, quinta rodada).

    **O achado.** O `QSplitter` reparte o crescimento em proporção. Uma janela levada de 1024 a
    1366 saía de `[526, 493]` para `[702, 659]` -- a aba com 696 px, o viewport da Galeria com 684,
    abaixo dos 702 de `LARGURA_MINIMA_DA_GALERIA` --, e a aba empilhava em toda tela de notebook.
    Aberta direto em 1366 a mesma janela dá 720 à aba e 702 ao viewport. Subindo pela faixa, a
    virada das duas colunas caía em **1504** em vez dos 1245 que a spec declara.

    **A régua é a função pura**, e não um número de tela: `divisor_da_primeira_abertura` responde o
    que os dois lados preferem naquela largura, e é exatamente o que a janela teria feito se
    tivesse nascido ali. Offscreen as duas contas batem porque é a mesma função dos dois lados.
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
        self.janela.resize(1400, 950)
        self.janela.show()
        self.app.processEvents()

    def montar(self, largura: int) -> object:
        """Uma janela **nascida** naquela largura -- a referência de que arranjo é o certo."""
        raiz = pasta_temporaria(self)
        outra = qt_janela.JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=raiz / "rotulos.csv",
            pasta_de_estudos=raiz / "estudos",
            pasta_da_galeria=raiz / "galeria",
            caminho_do_estado=raiz / "estado.json",
            motor=None,
        )
        outra.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.addCleanup(descartar, outra)
        outra.resize(largura, 950)
        outra.show()
        self.app.processEvents()
        return outra

    def preferida(self) -> int:
        return geometria.divisor_da_primeira_abertura(
            sum(self.janela.divisor.sizes()),
            preferida_esquerda=qt_janela.LARGURA_PREFERIDA_DAS_ABAS,
            preferida_direita=qt_janela.LARGURA_PREFERIDA_DO_VISOR,
        )

    def test_a_janela_redimensionada_reparte_como_a_recem_aberta(self) -> None:
        """**A afirmação é a igualdade entre as duas janelas**, e não um número.

        A régua é uma segunda janela **nascida** naquela largura: era exatamente essa a diferença
        que o crítico mediu, e é o que um número cravado não pega. Sob `offscreen` o lado do livro
        pede 810 px de mínimo e o `QSplitter` grampeia o preferido em quase toda largura -- afirmar
        `divisor_da_primeira_abertura` diretamente mediria a função pura, que já tem teste próprio,
        em vez do arranjo que chega à tela.
        """
        for largura in (1024, 1366, 1280, 1920, 1400, 1024, 1366):
            with self.subTest(largura=largura):
                self.janela.resize(largura, 950)
                self.app.processEvents()
                self.assertEqual(
                    self.montar(largura).divisor.sizes(),  # type: ignore[attr-defined]
                    self.janela.divisor.sizes(),
                    "o divisor manteve a proporção em vez de reaplicar o preferido",
                )

    def test_a_alca_arrastada_desliga_a_reaplicacao(self) -> None:
        """**Reaplicar não pode sobrescrever escolha**, e é o que separa esta correção de um defeito.

        `splitterMoved` só sai do gesto do mouse -- `setSizes` não o emite --, e é por ele que a
        janela sabe que a repartição passou a ser de alguém.
        """
        largura = sum(self.janela.divisor.sizes())
        escolhida = int(largura * 0.30)
        self.janela.divisor.setSizes([escolhida, largura - escolhida])
        self.janela.divisor.splitterMoved.emit(escolhida, 1)
        self.app.processEvents()
        antes = self.janela.divisor.sizes()[0]
        self.janela.resize(1800, 950)
        self.app.processEvents()
        self.assertNotEqual(
            self.preferida(), self.janela.divisor.sizes()[0], "a janela desfez o arrasto de alguém"
        )
        proporcao = self.janela.divisor.sizes()[0] / sum(self.janela.divisor.sizes())
        self.assertAlmostEqual(antes / largura, proporcao, places=1)

    def janela_com_a_fracao_no_disco(self, fracao: float, largura: int) -> object:
        """Uma janela que **lê do disco** aquela fração, e não uma com o atributo posto à mão.

        **É a diferença entre esta versão e a que o crítico recusou** (S-552, sexta rodada). A
        anterior cravava `_estado.sash_fraction` *e* `_divisor_de_fabrica` nos dois lados, que é
        exatamente a fiação sob teste: trocada por `True` a linha
        `_divisor_de_fabrica = not self._estado.sash_fraction` de `qt/janela.py`, a escolha da
        sessão anterior morria no primeiro redimensionamento e a suíte inteira ficava verde.

        **E a janela nasce larga.** A 1400 sob `offscreen` os dois lados estão no piso -- o do
        livro pede 810 px -- e o `QSplitter` grampeia qualquer fração pedida: os dois regimes
        respondem o mesmo número, e o que se mediria é o grampo.
        """
        raiz = pasta_temporaria(self)
        caminho = raiz / "estado.json"
        state.save_state(caminho, state.AppState(sash_fraction=fracao))
        outra = qt_janela.JanelaPrincipal(
            servico=_ServicoFalso(),  # type: ignore[arg-type]
            csv_de_rotulos=raiz / "rotulos.csv",
            pasta_de_estudos=raiz / "estudos",
            pasta_da_galeria=raiz / "galeria",
            caminho_do_estado=caminho,
            motor=None,
        )
        outra.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.addCleanup(descartar, outra)
        outra.resize(largura, 950)
        outra.show()
        self.app.processEvents()
        return outra

    def test_a_fracao_guardada_no_disco_tambem_desliga(self) -> None:
        """Uma fração que a sessão anterior gravou é escolha, e passa como veio (S-156).

        **A afirmação é depois do redimensionamento**, e é o que faltava: sem a fiação a fração
        guardada sobrevive ao `show()` -- o `showEvent` a aplica de qualquer jeito -- e só morre no
        primeiro `resize`, trocada pelos 720 px preferidos.
        """
        outra = self.janela_com_a_fracao_no_disco(0.60, 2200)
        tamanhos = outra.divisor.sizes()  # type: ignore[attr-defined]
        self.assertAlmostEqual(
            0.60, tamanhos[0] / sum(tamanhos), places=2, msg="o `show()` não aplicou a fração do disco"
        )
        outra.resize(2600, 950)  # type: ignore[attr-defined]
        self.app.processEvents()
        tamanhos = outra.divisor.sizes()  # type: ignore[attr-defined]
        self.assertAlmostEqual(
            0.60,
            tamanhos[0] / sum(tamanhos),
            places=2,
            msg="a escolha da sessão anterior morreu no primeiro redimensionamento",
        )
        preferida = geometria.divisor_da_primeira_abertura(
            sum(tamanhos),
            preferida_esquerda=qt_janela.LARGURA_PREFERIDA_DAS_ABAS,
            preferida_direita=qt_janela.LARGURA_PREFERIDA_DO_VISOR,
        )
        self.assertNotEqual(preferida, tamanhos[0], "a repartição de fábrica sobrescreveu a escolha")

    def test_a_fracao_de_fabrica_nao_e_gravada(self) -> None:
        """**Gravá-la transformava a repartição de fábrica na decisão de alguém.**

        Fechada a 1400 e reaberta a 1366, a sessão seguinte aplicava 0,516 -- a fração da largura
        em que a anterior por acaso fechou -- e a aba ficava com 702 px em vez dos 720 preferidos.
        É a mesma família do defeito da S-322: escrever por cima do disco o que ninguém escolheu.
        """
        self.janela._anotar_arranjo()
        self.assertEqual(0.0, self.janela._estado.sash_fraction)
        largura = sum(self.janela.divisor.sizes())
        self.janela.divisor.setSizes([int(largura * 0.3), largura - int(largura * 0.3)])
        self.janela.divisor.splitterMoved.emit(int(largura * 0.3), 1)
        self.app.processEvents()
        # Lida da tela e não cravada: os dois lados têm piso e o `QSplitter` grampeia o que se pede
        # a eles -- cravar 0,3 mediria o grampo. Ver `test_o_divisor_arrastado_volta_no_lugar`.
        arrastada = geometria.fracao_de_divisor(self.janela.divisor.sizes()[0], largura)
        self.janela._anotar_arranjo()
        self.assertAlmostEqual(arrastada, self.janela._estado.sash_fraction, places=2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
