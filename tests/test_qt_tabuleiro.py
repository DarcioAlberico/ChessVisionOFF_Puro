"""O tabuleiro do Qt **chamando** as decisões do produto, e não repetindo-as (S-155/S-501).

**O que estes testes cobrem, e o que não.** Que a FEN vira pixel, que virar troca os cantos e que
sem PNG a peça ainda aparece já é afirmado em `tests/test_app_pyqt.py::TabuleiroTests`. A rampa de
calor e `BoardGeometry.fit` são afirmadas em `tests/test_board_palette.py` e
`tests/test_ui_geometria.py`. Repetir qualquer um dos dois aqui mediria o mesmo código duas vezes.

O que só existe deste lado é o **vínculo**: que a geometria, a rampa e a tabela de glifos usadas
pelo tabuleiro do Qt são as mesmas de `ui/desenho_do_tabuleiro.py`, e não cópias que combinam hoje
e divergem no primeiro ajuste. Era exatamente esse o achado que o cabeçalho deste tabuleiro
registrava por escrito antes da S-501 -- *"o único ponto do fluxo em que o segundo frontend teve
de repetir uma decisão em vez de chamá-la"*.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import chess
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.config import UNCERTAIN_SQUARE_THRESHOLD
from chess_diagram_ocr.fen_utils import reading_index_from_square
from chess_diagram_ocr.ui import conjuntos, tokens
from chess_diagram_ocr.ui import desenho_do_tabuleiro as desenho

if TEM_PYQT:
    from PyQt6.QtGui import QColor, QImage

    from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro
    from chess_diagram_ocr.qt import tabuleiro_de_jogo as qt_jogo
    from chess_diagram_ocr.qt import tema

VAZIO = "8/8/8/8/8/8/8/8"


def renderizar(widget: object) -> QImage:
    """O widget desenhado num `QImage`, para amostrar a cor de um pixel."""
    return widget.grab().toImage()  # type: ignore[attr-defined]


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DecisaoCompartilhadaTests(unittest.TestCase):
    """Nenhuma das três é uma cópia: são o mesmo objeto do módulo puro."""

    def test_a_tabela_de_glifos_e_a_do_produto(self) -> None:
        """**Era uma cópia byte a byte**, doze pares mantidos em dois lugares (S-501)."""
        self.assertIs(qt_tabuleiro.GLIFOS, desenho.UNICODE_PIECES)

    def test_a_rampa_de_calor_e_a_do_produto(self) -> None:
        self.assertIs(qt_tabuleiro.heatmap_color, desenho.heatmap_color)

    def test_a_geometria_e_a_do_produto(self) -> None:
        self.assertIs(qt_tabuleiro.BoardGeometry, desenho.BoardGeometry)

@unittest.skipUnless(TEM_PYQT, MOTIVO)
class GeometriaTests(unittest.TestCase):
    """O enquadramento sai de `BoardGeometry.fit`, e não de uma conta local."""

    def setUp(self) -> None:
        aplicacao()
        self.tabuleiro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(self.tabuleiro.deleteLater)
        self.tabuleiro.resize(400, 320)

    def test_a_geometria_e_a_que_fit_devolve(self) -> None:
        esperada = desenho.BoardGeometry.fit(
            400,
            320,
            min_size=qt_tabuleiro.LADO_MINIMO,
            max_size=qt_tabuleiro.MAX_DO_TABULEIRO,
            margin=qt_tabuleiro.MARGEM,
        )
        self.assertEqual(self.tabuleiro.geometria(), esperada)

    def test_o_tabuleiro_e_quadrado_e_centrado(self) -> None:
        geo = self.tabuleiro.geometria()
        self.assertAlmostEqual(geo.origin_x, (400 - geo.size) / 2)
        self.assertAlmostEqual(geo.origin_y, (320 - geo.size) / 2)
        self.assertAlmostEqual(geo.cell * 8, geo.size)

    def test_ele_nunca_passa_da_area_do_widget(self) -> None:
        """`fit` já documenta isto: abaixo do mínimo, o limite passa a ser a área.

        Sem essa regra o tabuleiro vazava para fora em vez de encolher -- e num painel estreito o
        que se via era meia posição.

        **O tamanho pedido é medido, e não suposto.** A primeira versão deste teste pedia 120x120
        e afirmava `size <= 120`; o widget declara `setMinimumSize(LADO_MINIMO)`, então o Qt lhe
        deu 240 e a afirmação media uma janela que não existe. O invariante que vale é contra a
        área que o widget de fato tem.
        """
        for pedido in (120, 300, 800):
            with self.subTest(pedido=pedido):
                self.tabuleiro.resize(pedido, pedido)
                lado = min(self.tabuleiro.width(), self.tabuleiro.height())
                geo = self.tabuleiro.geometria()
                self.assertLessEqual(geo.size, lado)
                self.assertGreaterEqual(geo.origin_x, 0)
                self.assertGreaterEqual(geo.origin_y, 0)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class CalorTests(unittest.TestCase):
    """A incerteza pintada com a rampa, e não com um contorno próprio."""

    def setUp(self) -> None:
        aplicacao()
        self.tabuleiro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(self.tabuleiro.deleteLater)
        self.tabuleiro.resize(400, 400)

    def cor_da_casa(self, linha: int, coluna: int) -> QColor:
        geo = self.tabuleiro.geometria()
        x0, y0, x1, y1 = geo.rect(linha, coluna)
        imagem = renderizar(self.tabuleiro)
        return QColor(imagem.pixel(int((x0 + x1) / 2), int((y0 + y1) / 2)))

    def test_a_casa_marcada_muda_de_cor(self) -> None:
        self.tabuleiro.mostrar(VAZIO)
        limpa = self.cor_da_casa(0, 0)
        self.tabuleiro.mostrar(VAZIO, incertas=[0])
        self.assertNotEqual(limpa.rgb(), self.cor_da_casa(0, 0).rgb())

    def test_menos_confianca_pinta_mais_vermelho(self) -> None:
        """**É a rampa do produto que decide isto**, e é o que se afirma aqui.

        `heatmap_color` vai do amarelo no limiar ao vermelho no chão, e a razão está lá: casa
        certa fica em ~0,999 e casa errada em ~0,75, então a faixa que interessa é estreita.
        """
        confiancas = [1.0] * 64
        confiancas[0] = self._limiar_menos(0.01)
        self.tabuleiro.mostrar(VAZIO, incertas=[0], confiancas=confiancas)
        morna = self.cor_da_casa(0, 0)

        confiancas[0] = 0.0
        self.tabuleiro.mostrar(VAZIO, incertas=[0], confiancas=confiancas)
        quente = self.cor_da_casa(0, 0)

        self.assertLess(quente.green(), morna.green(), "a casa mais duvidosa não ficou mais vermelha")

    @staticmethod
    def _limiar_menos(delta: float) -> float:
        return max(0.0, UNCERTAIN_SQUARE_THRESHOLD - delta)

    def test_sem_confianca_a_casa_sai_na_cor_do_limiar(self) -> None:
        """Dizer "esta casa é duvidosa" sem inventar o quanto."""
        self.tabuleiro.mostrar(VAZIO, incertas=[0])
        sem_medida = self.cor_da_casa(0, 0)

        confiancas = [1.0] * 64
        confiancas[0] = UNCERTAIN_SQUARE_THRESHOLD
        self.tabuleiro.mostrar(VAZIO, incertas=[0], confiancas=confiancas)
        self.assertEqual(sem_medida.rgb(), self.cor_da_casa(0, 0).rgb())

    def test_a_tinta_nao_esconde_a_peca(self) -> None:
        """A decisão do `BoardRenderer`, cumprida com alfa em vez de `stipple`.

        Lá o comentário diz que a trama é *"o único jeito de tingir sem apagar a casa no canvas do
        Tk, que não tem canal alfa"*. O Qt tem, e o que não pode mudar é o resultado: a peça por
        baixo continua legível.
        """
        self.assertLess(qt_tabuleiro.TINTA_DA_INCERTEZA, 255, "tinta opaca apagaria a peça")

        self.tabuleiro.mostrar("R7/8/8/8/8/8/8/8", incertas=[0])
        com_peca = self.cor_da_casa(0, 0)
        self.tabuleiro.mostrar(VAZIO, incertas=[0])
        sem_peca = self.cor_da_casa(0, 0)
        self.assertNotEqual(com_peca.rgb(), sem_peca.rgb(), "a torre sumiu sob a tinta")

    def test_a_confianca_de_casa_nao_marcada_e_ignorada(self) -> None:
        """`incertas` diz quais casas; `confiancas` diz quão quentes. Uma casa certa não acende."""
        self.tabuleiro.mostrar(VAZIO)
        limpa = self.cor_da_casa(1, 1)
        self.tabuleiro.mostrar(VAZIO, incertas=[0], confiancas=[0.0] * 64)
        self.assertEqual(limpa.rgb(), self.cor_da_casa(1, 1).rgb())

    def test_limpar_apaga_o_calor(self) -> None:
        self.tabuleiro.mostrar(VAZIO, incertas=[0], confiancas=[0.0] * 64)
        quente = self.cor_da_casa(0, 0)
        self.tabuleiro.limpar()
        self.assertNotEqual(quente.rgb(), self.cor_da_casa(0, 0).rgb())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ConjuntoDePecasTests(unittest.TestCase):
    """Os tres conjuntos da S-230, que o corte do Tk deixou sem quem os desenhasse (S-506).

    `ui/conjuntos.py` sobreviveu ao corte declarando tres conjuntos; `ui/board_render.py`, que era
    quem sabia o que `traco` significa, nao. O registro ficou descrevendo uma aparencia que nada
    alcancava -- um nivel abaixo do menu, que e onde a trava de `montar` nao chega.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        # Estado de modulo: um teste que deixa o traco ligado contamina o vizinho.
        self.addCleanup(qt_tabuleiro.definir_conjunto, conjuntos.PADRAO)

    def test_a_pasta_e_a_mesma_para_o_padrao_e_para_o_traco(self) -> None:
        """A diferenca entre os dois nao esta nos arquivos: esta no que se faz com eles."""
        self.assertEqual(
            qt_tabuleiro.pasta_do_conjunto(conjuntos.PADRAO),
            qt_tabuleiro.pasta_do_conjunto(conjuntos.TRACO),
        )

    def test_a_pasta_do_usuario_so_vale_para_o_conjunto_que_a_declara(self) -> None:
        minha = Path(tempfile.gettempdir()) / "pecas-de-mentira"
        self.assertEqual(minha, qt_tabuleiro.pasta_do_conjunto(conjuntos.PASTA, str(minha)))
        self.assertEqual(
            qt_tabuleiro.PASTA_DE_PECAS, qt_tabuleiro.pasta_do_conjunto(conjuntos.PADRAO, str(minha))
        )

    def test_um_nome_escrito_errado_cai_no_padrao_e_nao_derruba(self) -> None:
        """O contrato de degradacao: o que vem do disco ou do ambiente nao impede a janela de abrir."""
        self.assertEqual(conjuntos.PADRAO, qt_tabuleiro.definir_conjunto("roxo"))

    def test_o_traco_grosso_muda_o_desenho_da_peca(self) -> None:
        """**E o teste que faltava**: `engrossar_traco` existia e nada a chamava."""
        tabuleiro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(descartar, tabuleiro)
        original = tabuleiro._pecas.get("P")
        if original is None:
            self.skipTest("checkout sem assets/piece_images/")
        grossa = qt_tabuleiro.engrossada(original, 24)
        self.assertEqual((24, 24), (grossa.width(), grossa.height()))
        self.assertNotEqual(
            original.scaled(24, 24).toImage().constBits().asstring(24 * 24 * 4),
            grossa.toImage().convertToFormat(QImage.Format.Format_ARGB32).constBits().asstring(24 * 24 * 4),
        )

    def test_o_conjunto_padrao_nao_passa_pelo_caminho_do_traco(self) -> None:
        """A S-230 promete nao mudar um pixel de quem nunca escolheu conjunto nenhum."""
        tabuleiro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(descartar, tabuleiro)
        mapa = tabuleiro._pecas.get("P")
        if mapa is None:
            self.skipTest("checkout sem assets/piece_images/")
        self.assertIs(mapa, tabuleiro._preparada("P", mapa, 24))
        qt_tabuleiro.definir_conjunto(conjuntos.TRACO)
        self.assertIsNot(mapa, tabuleiro._preparada("P", mapa, 24))

    def test_a_troca_alcanca_os_tabuleiros_ja_montados(self) -> None:
        """Dois tabuleiros na tela, e trocar de conjunto e **uma** chamada e nao uma por widget."""
        tabuleiro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(descartar, tabuleiro)
        qt_tabuleiro.definir_conjunto(conjuntos.PASTA, str(Path(tempfile.gettempdir()) / "vazia"))
        self.assertEqual({}, tabuleiro._pecas, "o tabuleiro montado nao recarregou")
        qt_tabuleiro.definir_conjunto(conjuntos.PADRAO)
        self.assertTrue(tabuleiro._pecas, "o tabuleiro nao voltou ao conjunto padrao")

    def test_uma_pasta_cravada_ignora_o_conjunto_em_vigor(self) -> None:
        """E o que permite ao teste montar um tabuleiro sobre uma pasta que ele controla."""
        tabuleiro = qt_tabuleiro.TabuleiroQt(pasta_de_pecas=Path("pasta/que/nao/existe"))
        self.addCleanup(descartar, tabuleiro)
        qt_tabuleiro.definir_conjunto(conjuntos.PADRAO)
        self.assertEqual({}, tabuleiro._pecas)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class EsteiraTests(unittest.TestCase):
    """A esteira tem tamanho, e o que sobra é o vazio (S-507).

    **A regressão do item.** A S-449 mediu, na janela do Tk, uma esteira que era o fundo do canvas:
    o canvas enche o painel, e tudo o que não era tabuleiro virava quase-preto -- 62% da largura
    numa linha, contra um painel claro. Ela foi consertada em 2026-08-30 tocando `ui/board_render`
    e `ui/board_widget`; `qt/tabuleiro.py` entrou na árvore no dia seguinte, no commit do corte,
    com `fillRect(self.rect(), SUPERFICIE_TABULEIRO)`. **O defeito voltou inteiro, e nada acusou**
    -- a guarda que a S-449 reforçou saiu com os 46 arquivos de teste do Tk.
    """

    def setUp(self) -> None:
        aplicacao()
        self.tabuleiro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(descartar, self.tabuleiro)
        self.tabuleiro.resize(900, 700)
        self.tabuleiro.mostrar(VAZIO)

    def test_a_esteira_e_o_tabuleiro_mais_a_margem(self) -> None:
        geo = self.tabuleiro.geometria()
        esteira = self.tabuleiro.esteira()
        self.assertAlmostEqual(esteira.width(), geo.size + qt_tabuleiro.MARGEM, places=3)
        self.assertAlmostEqual(esteira.height(), geo.size + qt_tabuleiro.MARGEM, places=3)
        self.assertAlmostEqual(esteira.left(), geo.origin_x - qt_tabuleiro.MARGEM / 2, places=3)

    def test_a_margem_sai_da_funcao_do_produto(self) -> None:
        """**O número não é escolhido aqui.** Era `8`; sai de `margem_de_coordenada()` (S-508)."""
        self.assertEqual(qt_tabuleiro.MARGEM, desenho.margem_de_coordenada())

    def test_fora_da_esteira_o_canvas_e_o_vazio_e_nao_a_esteira(self) -> None:
        """O pixel do canto do widget, que é onde o slab morava."""
        imagem = renderizar(self.tabuleiro)
        canto = QColor(imagem.pixel(2, 2))
        self.assertEqual(
            canto.name(), tema.cor_atual(tokens.VAZIO_DE_CANVAS), "o canto do widget não é o vazio"
        )
        self.assertNotEqual(canto.name(), tema.cor_atual(tokens.SUPERFICIE_TABULEIRO))

    def test_a_esteira_encolhe_em_vez_de_crescer_com_o_widget(self) -> None:
        """**É o que separa este item do defeito de origem.** Lá a esteira era o fundo, então ela
        crescia com a janela; medido na sala, 41,5% da área num painel de 685x782. Aqui ela é o
        tabuleiro mais a margem, e alargar o widget só aumenta o vazio.
        """
        def fracao() -> float:
            imagem = renderizar(self.tabuleiro)
            esteira = tema.cor_atual(tokens.SUPERFICIE_TABULEIRO)
            escuros = sum(
                1
                for x in range(0, imagem.width(), 3)
                for y in range(0, imagem.height(), 3)
                if QColor(imagem.pixel(x, y)).name() == esteira
            )
            return escuros / ((imagem.width() // 3 + 1) * (imagem.height() // 3 + 1))

        self.tabuleiro.resize(700, 640)
        apertado = fracao()
        self.tabuleiro.resize(1100, 900)
        folgado = fracao()
        self.assertLess(folgado, apertado, "a esteira cresceu com o widget -- ela voltou a ser o fundo")
        self.assertLess(folgado, 0.10, "a esteira ainda ocupa mais de 10% do widget largo")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class CoordenadaTests(unittest.TestCase):
    """As letras a–h e os números 8–1, que este tabuleiro não desenhava (S-508)."""

    def setUp(self) -> None:
        aplicacao()
        self.tabuleiro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(descartar, self.tabuleiro)
        self.tabuleiro.resize(500, 500)
        self.tabuleiro.mostrar(VAZIO)

    def _tinta_na_faixa(self, *, abaixo: bool) -> int:
        """Quantos pixels da faixa de coordenada não são a esteira -- isto é, são letra."""
        geo = self.tabuleiro.geometria()
        imagem = renderizar(self.tabuleiro)
        esteira = tema.cor_atual(tokens.SUPERFICIE_TABULEIRO)
        if abaixo:
            faixa_x = range(int(geo.origin_x), int(geo.origin_x + geo.size))
            faixa_y = range(int(geo.origin_y + geo.size) + 1, int(self.tabuleiro.esteira().bottom()))
        else:
            faixa_x = range(int(self.tabuleiro.esteira().left()) + 1, int(geo.origin_x))
            faixa_y = range(int(geo.origin_y), int(geo.origin_y + geo.size))
        return sum(
            1
            for x in faixa_x
            for y in faixa_y
            if QColor(imagem.pixel(x, y)).name() != esteira
        )

    def test_ha_letra_abaixo_e_numero_a_esquerda(self) -> None:
        self.assertGreater(self._tinta_na_faixa(abaixo=True), 0, "nenhuma letra abaixo do tabuleiro")
        self.assertGreater(self._tinta_na_faixa(abaixo=False), 0, "nenhum número à esquerda")

    def test_a_letra_cabe_dentro_da_esteira(self) -> None:
        """**O defeito que `margem_de_coordenada` conserta**: a base de "a b c d e f g h" cortada.

        Se a letra vazasse, haveria tinta fora da esteira -- e ali o fundo é o vazio, não a
        esteira, então a comparação abaixo a acusaria.
        """
        esteira = self.tabuleiro.esteira()
        imagem = renderizar(self.tabuleiro)
        vazio = tema.cor_atual(tokens.VAZIO_DE_CANVAS)
        abaixo = int(esteira.bottom()) + 1
        fora = [
            x
            for x in range(int(esteira.left()), int(esteira.right()))
            for y in (abaixo, abaixo + 1)
            if y < imagem.height() and QColor(imagem.pixel(x, y)).name() != vazio
        ]
        self.assertEqual([], fora, "há tinta logo abaixo da esteira: a coordenada não coube")

    def test_a_ordem_das_reguas_e_a_decisao_pura(self) -> None:
        """Com as pretas embaixo, `a` fica à direita e `1` no topo.

        **Afirmado na função e não no pixel, e a razão é de bancada.** A plataforma `offscreen`
        da suíte não tem fonte nenhuma -- `QFontDatabase.families()` devolve vazio --, então `a` e
        `h` desenham o mesmo retângulo. Um teste que comparasse as duas fotografias passaria em
        verde com a ordem invertida, que é guarda vácua com outro nome. Quem amarra o widget à
        decisão é o `assertIs` abaixo.
        """
        self.assertEqual(("abcdefgh", "87654321"), desenho.reguas(False))
        self.assertEqual(("hgfedcba", "12345678"), desenho.reguas(True))
        self.assertIs(qt_tabuleiro.reguas, desenho.reguas)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class UltimoLanceTests(unittest.TestCase):
    """As duas casas do lance que chegou à posição (S-509).

    `BoardModel.last_move` e `last_move_squares()` existiam, eram puros, eram testados -- e
    **nunca recebiam valor**. O papel `CASA_ULTIMO_LANCE` existia e não tinha quem o pintasse.
    """

    def setUp(self) -> None:
        aplicacao()
        self.tabuleiro = qt_tabuleiro.TabuleiroQt()
        self.addCleanup(descartar, self.tabuleiro)
        self.tabuleiro.resize(400, 400)
        self.tabuleiro.mostrar(VAZIO)

    def cor_da_casa(self, indice: int) -> QColor:
        linha, coluna = divmod(indice, 8)
        geo = self.tabuleiro.geometria()
        x0, y0, x1, y1 = geo.rect(linha, coluna)
        imagem = renderizar(self.tabuleiro)
        return QColor(imagem.pixel(int((x0 + x1) / 2), int((y0 + y1) / 2)))

    def test_as_casas_marcadas_saem_no_papel_do_ultimo_lance(self) -> None:
        self.tabuleiro.definir_ultimo_lance([0, 63])
        esperada = tema.cor_atual(tokens.CASA_ULTIMO_LANCE)
        self.assertEqual(esperada, self.cor_da_casa(0).name())
        self.assertEqual(esperada, self.cor_da_casa(63).name())

    def test_sem_lance_nenhuma_casa_e_marcada(self) -> None:
        """A raiz do estudo é a posição do diagrama: ela não veio de lance nenhum."""
        limpa = self.cor_da_casa(0)
        self.tabuleiro.definir_ultimo_lance([0])
        self.tabuleiro.definir_ultimo_lance()
        self.assertEqual(limpa.rgb(), self.cor_da_casa(0).rgb())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DesenhoDoJogoTests(unittest.TestCase):
    """As medidas do tabuleiro de jogo saem do módulo puro, e não de literais (S-510)."""

    def setUp(self) -> None:
        aplicacao()
        self.tabuleiro = qt_jogo.TabuleiroDeJogo()
        self.addCleanup(descartar, self.tabuleiro)
        self.tabuleiro.resize(400, 400)

    def test_a_tabela_de_cor_de_seta_e_a_do_produto(self) -> None:
        """**Era uma cópia byte a byte** de `PAPEL_DE_SETA` -- quatro pares em dois lugares.

        É o mesmo achado que a S-501 fechou neste pacote para a tabela de glifos, com outro nome.
        """
        self.assertIs(qt_jogo.COR_DA_SETA, desenho.PAPEL_DE_SETA)

    def test_nenhuma_medida_da_casa_e_literal(self) -> None:
        """`geo.cell * 0.34` e `geo.cell * 0.14` viviam ao lado de `LARGURA_DA_SETA` não chamada."""
        fonte = Path(qt_jogo.__file__).read_text(encoding="utf-8")
        soltos = re.findall(r"geo\.cell\s*\*\s*([0-9]+\.[0-9]+)", fonte)
        self.assertEqual([], soltos, f"medida da casa cravada no widget: {soltos}")

    def test_o_alvo_nao_e_pintado_com_a_cor_da_selecao(self) -> None:
        """Duas coisas diferentes com a mesma cor é a família de defeito da S-145.

        A casa escolhida e as casas para onde ela pode ir dizem coisas diferentes, e o papel
        `ALVO` existe desde sempre para a segunda.
        """
        tabuleiro = chess.Board()
        self.tabuleiro.mostrar_tabuleiro(tabuleiro)
        # e2: o peão que tem dois alvos legais, e2-e3 e e2-e4.
        self.tabuleiro.modelo.press(reading_index_from_square(chess.E2))
        alvo = self.tabuleiro.modelo.legal_targets()
        self.assertTrue(alvo, "o peão de e2 não ofereceu alvo nenhum")

        geo = self.tabuleiro.geometria()
        linha, coluna = self.tabuleiro.modelo.display_from_index(sorted(alvo)[0])
        x0, y0, x1, y1 = geo.rect(linha, coluna)
        imagem = renderizar(self.tabuleiro)
        centro = QColor(imagem.pixel(int((x0 + x1) / 2), int((y0 + y1) / 2)))
        self.assertEqual(tema.cor_atual(tokens.ALVO), centro.name())
        self.assertNotEqual(tema.cor_atual(tokens.CONTORNO_DE_SELECAO), centro.name())

    def test_o_ultimo_lance_chega_do_modelo_puro(self) -> None:
        """`BoardModel.last_move_squares` estava sem chamador; agora é quem responde (S-509)."""
        tabuleiro = chess.Board()
        lance = tabuleiro.parse_san("e4")
        tabuleiro.push(lance)
        self.tabuleiro.mostrar_tabuleiro(tabuleiro, ultimo_lance=lance)
        self.assertEqual(
            self.tabuleiro.modelo.last_move_squares(),
            frozenset({reading_index_from_square(chess.E2), reading_index_from_square(chess.E4)}),
        )

    def test_sem_lance_a_marca_e_apagada(self) -> None:
        tabuleiro = chess.Board()
        lance = tabuleiro.parse_san("e4")
        tabuleiro.push(lance)
        self.tabuleiro.mostrar_tabuleiro(tabuleiro, ultimo_lance=lance)
        self.tabuleiro.mostrar_tabuleiro(chess.Board())
        self.assertEqual(frozenset(), self.tabuleiro.modelo.last_move_squares())
