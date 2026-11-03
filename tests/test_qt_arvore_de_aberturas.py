"""A janela da árvore de aberturas montada: a thread, o clique que anda e a barra (S-535).

**O que só existe deste lado.** Que a consulta sai da linha de eventos; que o clique simples vira
`lance_escolhido` -- e o certo, mesmo depois de a tabela ser reordenada pelo cabeçalho --; que a
barra de três segmentos é desenhada onde há amostra e não é onde não há; que a falta de árvore vira
uma frase com saída em vez de tabela vazia; e que "Ver as partidas" abre a busca da S-533 já
preenchida.

O que a árvore responde está em `tests/test_arvore_de_aberturas.py`; o que a tabela mostra, em
`tests/test_ui_arvore_de_aberturas.py`. Aqui só a fiação.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import chess
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar, pixels_diferentes, renderizar

from chess_diagram_ocr import arvore_de_aberturas as arv

if TEM_PYQT:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import arvore_de_aberturas as qt_arvore
    from chess_diagram_ocr.qt import painel_de_estudo as qt_estudo
    from chess_diagram_ocr.ui import arvore_de_aberturas as arvore_ui

CABECALHO = (
    '[Event "Teste"]\n[Date "{data}"]\n[White "A, A"]\n[Black "B, B"]\n'
    '[Result "{resultado}"]\n[WhiteElo "2600"]\n[BlackElo "2500"]\n\n'
)


def _partida(lances: str, *, data: str = "2020.01.01", resultado: str = "1-0") -> str:
    return CABECALHO.format(data=data, resultado=resultado) + lances + "\n\n"


def _base() -> str:
    """Uma base pequena com três primeiros lances de frequências bem separadas.

    `1.c4` com dez partidas e resultados variados (a barra aparece), `1.d4` com seis, e `1.e4` com
    duas -- abaixo de `MINIMO_PARA_PERCENTUAL`, que é o caso em que a barra **não** pode aparecer.

    **O mais jogado é o primeiro do alfabeto de propósito.** Com `1.e4` no topo das duas contagens,
    uma tabela que reordenasse por SAN passaria pelo teste de ordem sem que ninguém notasse -- foi
    o que aconteceu até a foto de 1400×950 mostrar a Najdorf saindo `Rg1, Rb1, Qf3, … a3`.
    """
    partidas = [
        _partida("1. c4 c5 2. Nf3", resultado="1-0" if i % 3 else "0-1", data=f"20{10 + i:02d}.01.01")
        for i in range(10)
    ]
    partidas += [_partida("1. d4 d5 2. c4", resultado="1/2-1/2") for _ in range(6)]
    partidas += [_partida("1. e4 e5") for _ in range(2)]
    return "".join(partidas)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DialogoDaArvoreTests(unittest.TestCase):
    """O diálogo sobre uma árvore de verdade -- pequena, com a mesma maquinaria."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(_base(), encoding="utf-8")
        self.arvore = self.raiz / "arvore.sqlite"
        arv.construir(self.base, self.arvore, workers=1)
        # Sem pai: o dialogo e descartado no fim do teste, e pendura-lo na janela do processo o
        # faria sobreviver ao modulo com a thread dentro (a regra de `qt_app.descartar`).
        self.dialogo = qt_arvore.DialogoDaArvore(None, bases=[self.base], arvore=self.arvore)
        self.addCleanup(self._fechar)

    def _fechar(self) -> None:
        self.dialogo.esperar(20_000)
        self.app.processEvents()
        descartar(self.dialogo)

    def _perguntar(self, *lances: str) -> None:
        tabuleiro = chess.Board()
        for san in lances:
            tabuleiro.push_san(san)
        self.dialogo.definir_posicao(tabuleiro)
        self._esperar()

    def _esperar(self) -> None:
        self.assertTrue(self.dialogo.esperar(20_000), "a consulta não terminou")
        for _ in range(20):
            self.app.processEvents()

    def _celulas(self, altura: int) -> list[str]:
        item = self.dialogo.tabela.topLevelItem(altura)
        assert item is not None
        return [item.text(coluna) for coluna in range(len(arvore_ui.COLUNAS))]

    # ------------------------------------------------------------------------- a consulta

    def test_a_consulta_sai_da_linha_de_eventos(self) -> None:
        """Uma sonda num SQLite frio de mais de um gigabyte é disco, e a janela não pode esperar."""
        self.assertTrue(self.dialogo.definir_posicao(chess.Board()))
        self.assertEqual(arvore_ui.EM_BUSCA, self.dialogo.lbl_resumo.text())
        self._esperar()
        self.assertNotEqual(arvore_ui.EM_BUSCA, self.dialogo.lbl_resumo.text())

    def test_a_tabela_traz_um_lance_por_linha_na_ordem_da_frequencia(self) -> None:
        """E **na tela**, e não só na lista que `ui/` devolveu: com a ordenação pelo cabeçalho
        ligada, o Qt reordena pelo indicador corrente a cada preenchimento, e o de fábrica é a
        primeira coluna. Ver `COLUNA_DA_ORDEM`."""
        self._perguntar()
        self.assertEqual(3, self.dialogo.tabela.topLevelItemCount())
        self.assertEqual(["c4", "d4", "e4"], [self._celulas(i)[0] for i in range(3)])
        self.assertIn("18 partida(s)", self.dialogo.lbl_resumo.text())

    def test_a_tabela_nasce_com_o_indicador_na_coluna_das_partidas(self) -> None:
        """Ordenada e **dizendo por onde**: uma seta no cabeçalho errado ensina a ler a tabela
        errado, e é a mesma seta que a pessoa clica para trocar a ordem."""
        self._perguntar()
        cabecalho = self.dialogo.tabela.header()
        self.assertEqual(qt_arvore.COLUNA_DA_ORDEM, cabecalho.sortIndicatorSection())
        self.assertEqual(Qt.SortOrder.DescendingOrder, cabecalho.sortIndicatorOrder())
        self.assertEqual("partidas", arvore_ui.COLUNAS[qt_arvore.COLUNA_DA_ORDEM].chave)

    def test_a_posicao_perguntada_fica_escrita(self) -> None:
        """Sem esta linha, a tabela de dez lances de uma Najdorf é indistinguível da de outra."""
        self._perguntar("e4", "e5")
        self.assertIn("Lance 2", self.dialogo.lbl_posicao.text())
        self.assertIn("brancas", self.dialogo.lbl_posicao.text())

    def test_a_posicao_que_chega_durante_a_consulta_nao_se_perde(self) -> None:
        """Navegar com a seta dispara um pedido por lance: sem o pendente, a tabela ficaria na
        posição do primeiro."""
        self.dialogo.definir_posicao(chess.Board())
        depois = chess.Board()
        depois.push_san("e4")
        self.assertFalse(self.dialogo.definir_posicao(depois), "a segunda consulta não esperou a primeira")
        self._esperar()
        self._esperar()
        self.assertEqual(["e5"], [self._celulas(i)[0] for i in range(self.dialogo.tabela.topLevelItemCount())])

    # -------------------------------------------------------------------------- a escolha

    def test_o_clique_simples_joga_o_lance(self) -> None:
        """O clique **é** a navegação, como no explorador do Lichess: a árvore é uma pilha de
        posições e clicar num lance é descer um degrau."""
        self._perguntar()
        escolhidos: list[str] = []
        self.dialogo.lance_escolhido.connect(escolhidos.append)
        item = self.dialogo.tabela.topLevelItem(1)
        assert item is not None
        self.dialogo.tabela.itemClicked.emit(item, 0)
        self.assertEqual(["d4"], escolhidos)

    def test_o_Enter_joga_a_linha_marcada(self) -> None:
        self._perguntar()
        escolhidos: list[str] = []
        self.dialogo.lance_escolhido.connect(escolhidos.append)
        self.dialogo.tabela.setCurrentItem(self.dialogo.tabela.topLevelItem(2))
        self.dialogo.jogar_selecionado()
        self.assertEqual(["e4"], escolhidos)

    def test_reordenada_pelo_cabecalho_a_escolha_continua_certa(self) -> None:
        """Com a ordenação ligada, a altura na tela deixa de ser a posição na lista -- e sem
        `posicao_de` o clique jogaria o lance da linha que calhou de estar ali."""
        self._perguntar()
        self.dialogo.tabela.sortItems(1, Qt.SortOrder.AscendingOrder)
        escolhidos: list[str] = []
        self.dialogo.lance_escolhido.connect(escolhidos.append)
        primeiro = self.dialogo.tabela.topLevelItem(0)
        assert primeiro is not None
        self.assertEqual("e4", primeiro.text(0), "a ordenação crescente por partidas não pôs e4 no topo")
        self.dialogo.tabela.itemClicked.emit(primeiro, 0)
        self.assertEqual(["e4"], escolhidos)

    def test_clicar_numa_tabela_vazia_nao_emite_nada(self) -> None:
        escolhidos: list[str] = []
        self.dialogo.lance_escolhido.connect(escolhidos.append)
        self.dialogo.jogar_selecionado()
        self.assertEqual([], escolhidos)

    # ----------------------------------------------------------------------------- a barra

    def test_as_fracoes_acompanham_a_linha_e_nao_a_altura(self) -> None:
        """Reordenada a tabela, a barra tem de ir junto com o lance dela."""
        self._perguntar()
        self.dialogo.tabela.sortItems(1, Qt.SortOrder.AscendingOrder)
        for altura in range(self.dialogo.tabela.topLevelItemCount()):
            item = self.dialogo.tabela.topLevelItem(altura)
            assert item is not None
            with self.subTest(lance=item.text(0)):
                guardadas = item.data(qt_arvore.COLUNA_DA_BARRA, qt_arvore.PAPEL_DAS_FRACOES)
                esperadas = next(linha.fracoes for linha in self.dialogo._linhas if linha.lance == item.text(0))
                self.assertEqual(tuple(esperadas), tuple(guardadas))

    def test_a_barra_e_desenhada_onde_ha_amostra_e_nao_onde_nao_ha(self) -> None:
        """Duas partidas não sustentam uma percentagem (S-135), e a barra é a afirmação. O
        desenho da célula com barra tem de diferir do da célula sem -- é isso que se mede aqui,
        e não a cor de um pixel: sob `offscreen` não há fonte."""
        self._perguntar()
        self.dialogo.resize(880, 460)
        self.dialogo.show()
        self.app.processEvents()
        desenho = renderizar(self.dialogo.tabela)
        alturas = {self._celulas(i)[0]: i for i in range(self.dialogo.tabela.topLevelItemCount())}
        com_barra = self.dialogo.tabela.visualItemRect(self.dialogo.tabela.topLevelItem(alturas["c4"]))
        sem_barra = self.dialogo.tabela.visualItemRect(self.dialogo.tabela.topLevelItem(alturas["e4"]))
        coluna = self.dialogo.tabela.header().sectionPosition(qt_arvore.COLUNA_DA_BARRA)
        largura = self.dialogo.tabela.header().sectionSize(qt_arvore.COLUNA_DA_BARRA)
        recorte_com = desenho.copy(coluna, com_barra.top(), largura, com_barra.height())
        recorte_sem = desenho.copy(coluna, sem_barra.top(), largura, sem_barra.height())
        self.assertGreater(
            pixels_diferentes(recorte_com, recorte_sem),
            largura,
            "a célula com barra desenha o mesmo que a sem barra",
        )

    def test_a_coluna_da_barra_e_a_do_resultado(self) -> None:
        """O delegado é posto por índice, e uma coluna a mais em `COLUNAS` moveria a barra."""
        self.assertEqual("resultado", arvore_ui.COLUNAS[qt_arvore.COLUNA_DA_BARRA].chave)

    # ---------------------------------------------------------------------------- estados

    def test_sem_arvore_a_frase_traz_o_comando_e_e_pintada_de_aviso(self) -> None:
        outro = qt_arvore.DialogoDaArvore(None, bases=[self.base], arvore=self.raiz / "nao_existe.sqlite")
        self.addCleanup(descartar, outro)
        outro.definir_posicao(chess.Board())
        self.assertTrue(outro.esperar(20_000))
        for _ in range(20):
            self.app.processEvents()
        self.assertIn("cvoff-games --build-tree", outro.lbl_resumo.text())
        self.assertEqual(0, outro.tabela.topLevelItemCount())

    def test_fundo_demais_nao_diz_nenhuma_partida(self) -> None:
        """A distinção da S-135: a posição além da profundidade não foi perguntada a ninguém."""
        fundo = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 30")
        self.dialogo.definir_posicao(fundo)
        self._esperar()
        self.assertIn("árvore vai até o lance", self.dialogo.lbl_resumo.text())
        self.assertNotIn("Nenhuma partida", self.dialogo.lbl_resumo.text())

    # --------------------------------------------------------------------------- partidas

    def test_ver_as_partidas_emite_o_filtro_com_o_ECO_da_posicao(self) -> None:
        """A posição sozinha não estreita a busca (S-533); o ECO dela sim."""
        self._perguntar("e4", "c5", "Nf3", "d6", "d4")
        pedidos: list[object] = []
        self.dialogo.partidas_pedidas.connect(pedidos.append)
        self.dialogo.pedir_partidas()
        (filtro,) = pedidos
        self.assertTrue(filtro.eco_de.startswith("B"), f"o ECO da Siciliana saiu {filtro.eco_de!r}")
        self.assertEqual(filtro.eco_de, filtro.eco_ate)
        self.assertTrue(filtro.posicao)

    def test_o_botao_de_construir_pede_a_construcao_a_quem_tem_as_bases(self) -> None:
        pedidos: list[int] = []
        self.dialogo.construcao_pedida.connect(lambda: pedidos.append(1))
        QTest.mouseClick(self.dialogo.btn_construir, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        self.assertEqual([1], pedidos)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SalaTests(unittest.TestCase):
    """A fiação da sala: o comando abre, o lance escolhido anda, e a árvore acompanha o tabuleiro.

    **Afirma o efeito e não a chamada.** Trocar o método depois do `connect` não troca quem o
    sinal chama -- é a lição que este projeto pagou --, então o que se mede aqui é o tabuleiro da
    sala tendo andado, e não um `mock` que registrou uma visita.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(_base(), encoding="utf-8")
        self.arvore = self.raiz / "arvore.sqlite"
        arv.construir(self.base, self.arvore, workers=1)
        self.sala = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.raiz,
            pasta_de_estudos=self.raiz,
            pasta_de_treino=self.raiz,
            bases_de_partidas=lambda: [self.base],
        )
        self.addCleanup(self._fechar)

    def _fechar(self) -> None:
        arvore = self.sala._arvore
        if arvore is not None:
            arvore.esperar(20_000)
            self.app.processEvents()
            descartar(arvore)
        descartar(self.sala)

    def _quieto(self, dialogo: object) -> None:
        """Espera a árvore ficar sem consulta em curso -- **e não só a primeira delas**.

        `definir_posicao` guarda o pedido que chega durante uma consulta e o refaz no fim, então
        um `esperar` só devolve com a segunda ainda por começar. É o preço de a árvore acompanhar
        o tabuleiro, e o teste tem de esperar o mesmo que a pessoa vê.
        """
        for _ in range(40):
            dialogo.esperar(20_000)
            for _ in range(10):
                self.app.processEvents()
            if dialogo._tarefa is None:
                return

    def _abrir(self) -> object:
        # A arvore do teste mora ao lado da base, e nao no `data/` do repositorio: o dialogo a
        # recebe por argumento, e a sala usa o padrao -- por isso ele e trocado aqui.
        dialogo = self.sala.arvore_de_aberturas()
        assert dialogo is not None
        self._quieto(dialogo)
        dialogo._arquivo = self.arvore
        dialogo.definir_posicao(self.sala.estudo.tabuleiro)
        self._quieto(dialogo)
        return dialogo

    def test_o_lance_escolhido_na_arvore_anda_no_tabuleiro_da_sala(self) -> None:
        dialogo = self._abrir()
        self.assertGreater(dialogo.tabela.topLevelItemCount(), 0, "a árvore não respondeu")
        dialogo.lance_escolhido.emit("c4")
        self._quieto(dialogo)
        self.assertEqual("c4", self.sala.estudo.no.san())

    def test_um_lance_que_a_posicao_nao_sustenta_vira_frase_e_nao_lance(self) -> None:
        """A posição pode ter andado entre a consulta e o clique -- e aí o SAN é de outra."""
        self._abrir()
        self.assertFalse(self.sala.jogar_da_arvore("Qxh7"))
        self.assertIsNone(self.sala.estudo.no.move, "a sala jogou um lance ilegal")

    def test_a_arvore_aberta_acompanha_a_posicao_da_sala(self) -> None:
        """O `refresh` é o único ponto por onde toda mudança de nó passa, e é dele que a árvore
        recebe a posição nova -- inclusive quando o lance veio da seta do teclado."""
        dialogo = self._abrir()
        self.sala.push_move(self.sala.estudo.tabuleiro.parse_san("d4"))
        self._quieto(dialogo)
        self.assertIn("Lance 1", dialogo.lbl_posicao.text())
        self.assertIn("pretas", dialogo.lbl_posicao.text())
        self.assertEqual(["d5"], [dialogo.tabela.topLevelItem(i).text(0) for i in range(dialogo.tabela.topLevelItemCount())])

    def test_ver_as_partidas_abre_a_busca_ja_preenchida(self) -> None:
        dialogo = self._abrir()
        busca = self.sala.partidas_da_arvore(
            arvore_ui.busca_da_posicao(self.sala.estudo.tabuleiro.board_fen(), "B90")
        )
        self.assertIsNotNone(busca)
        self.addCleanup(descartar, busca)
        busca.esperar(20_000)
        for _ in range(20):
            self.app.processEvents()
        self.assertEqual("B90", busca.campo_eco_de.text())
        self.assertTrue(busca.caixa_posicao.isChecked())
        del dialogo


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class ConstrutorTests(unittest.TestCase):
    """A passada com barra e Cancelar, sem sair da janela (a forma da S-532)."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(_base(), encoding="utf-8")

    def test_a_passada_termina_e_a_frase_diz_o_que_ela_custou(self) -> None:
        alvo = self.raiz / "arvore.sqlite"
        construtor = qt_arvore.construir_com_dialogo(None, [self.base], alvo, mostrar=False)
        # O `QProgressDialog` se destrói sozinho no fim (`_fechar`); quem sobra é o construtor.
        self.addCleanup(descartar, construtor)
        feitos: list[object] = []
        construtor.terminou.connect(feitos.append)
        self.assertTrue(construtor.esperar(60_000), "a construção não terminou")
        for _ in range(30):
            self.app.processEvents()
        self.assertTrue(alvo.exists(), "a árvore não foi gravada")
        self.assertEqual(1, len(feitos))
        self.assertIn("Árvore de aberturas pronta", qt_arvore.frase_final(feitos[0]))

    def test_uma_segunda_rodada_e_recusada_enquanto_a_primeira_roda(self) -> None:
        """Duas escreveriam no mesmo arquivo -- a guarda de `IndexadorDaBase.iniciar`."""
        construtor = qt_arvore.ConstrutorDaArvore()
        self.addCleanup(descartar, construtor)
        self.assertTrue(construtor.iniciar([self.base], self.raiz / "a.sqlite"))
        self.assertFalse(construtor.iniciar([self.base], self.raiz / "b.sqlite"))
        self.assertTrue(construtor.esperar(60_000))
        for _ in range(30):
            self.app.processEvents()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
