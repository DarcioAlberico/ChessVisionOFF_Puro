"""O diálogo de busca montado: os campos, a thread, os três estados e a escolha (S-533).

**O que só existe deste lado.** Que a busca sai da linha de eventos (a janela não pode parar com
dez milhões de partidas), que o formulário malfeito não vira consulta, que a linha escolhida vira
`partida_escolhida(caminho, offset)` -- pelo duplo clique **e** pelo Enter --, e que o índice
ausente vira uma frase com saída em vez de uma tabela vazia.

O que a busca responde está em `tests/test_games_index.py`; o que a frase diz, em
`tests/test_ui_busca_de_partidas.py`. Aqui só a fiação.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.games_index import IndiceIndisponivel, build_index
from chess_diagram_ocr.ui.busca_de_partidas import Filtro

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import busca_de_partidas as qt_busca

CABECALHO = (
    '[Event "Tata Steel Masters"]\n[Date "{data}"]\n[White "{branco}"]\n[Black "{preto}"]\n'
    '[Result "1-0"]\n[WhiteElo "2835"]\n[BlackElo "2773"]\n[ECO "{eco}"]\n\n'
)
LANCES = "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 1-0\n\n"


def _base(quantas: int) -> str:
    """`quantas` partidas de Carlsen, com datas decrescentes -- para a paginação ter o que paginar."""
    return "".join(
        CABECALHO.format(data=f"2019.01.{dia + 1:02d}", branco="Carlsen, Magnus", preto=f"Rival{dia}, A", eco="B90")
        + LANCES
        for dia in range(quantas)
    )


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class DialogoDeBuscaTests(unittest.TestCase):
    """O diálogo sobre um índice de verdade -- pequeno, mas com a mesma maquinaria."""

    PARTIDAS = 7

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.base = self.raiz / "base.pgn"
        self.base.write_text(_base(self.PARTIDAS), encoding="utf-8")
        self.indice = self.raiz / "indice.sqlite"
        build_index(self.base, self.indice)
        # Sem pai: o diálogo é descartado no fim do teste, e pendurá-lo na janela do processo o
        # faria sobreviver ao módulo com a thread dentro (a regra de `qt_app.descartar`).
        self.dialogo = qt_busca.DialogoDeBusca(None, bases=[self.base], indice=self.indice)
        self.addCleanup(self._fechar)

    def _fechar(self) -> None:
        self.dialogo.esperar(20_000)
        self.app.processEvents()
        descartar(self.dialogo)

    def _buscar(self, **campos: str) -> None:
        """Preenche os campos, clica em Buscar e espera a thread. Deixa a tabela pronta."""
        campos_do_formulario = {
            "brancas": self.dialogo.campo_brancas,
            "pretas": self.dialogo.campo_pretas,
            "evento": self.dialogo.campo_evento,
            "ano_de": self.dialogo.campo_ano_de,
            "ano_ate": self.dialogo.campo_ano_ate,
            "elo_minimo": self.dialogo.campo_elo,
            "eco_de": self.dialogo.campo_eco_de,
            "eco_ate": self.dialogo.campo_eco_ate,
        }
        for nome, valor in campos.items():
            campos_do_formulario[nome].setText(valor)
        self.dialogo.buscar()
        self._esperar()

    def _esperar(self) -> None:
        self.assertTrue(self.dialogo.esperar(20_000), "a busca não terminou")
        for _ in range(20):
            self.app.processEvents()

    def test_o_filtro_de_fora_e_escrito_nos_campos_antes_de_buscar(self) -> None:
        """A árvore de aberturas (S-535) manda para cá a posição e o ECO dela.

        **Escrito nos campos, e não buscado por baixo deles**: o formulário é o que diz o que foi
        perguntado, e alargar o filtro é o gesto seguinte -- a posição sozinha não estreita nada.
        """
        self.assertTrue(self.dialogo.aplicar_filtro(Filtro(eco_de="B90", eco_ate="B90", posicao="colocacao")))
        self._esperar()
        self.assertEqual("B90", self.dialogo.campo_eco_de.text())
        self.assertEqual("B90", self.dialogo.campo_eco_ate.text())
        self.assertTrue(self.dialogo.caixa_posicao.isChecked())
        self.assertEqual("", self.dialogo.campo_ano_de.text(), "zero virou 0 no campo do ano")
        self.assertEqual("colocacao", self.dialogo.filtro_dos_campos().posicao)

    # ------------------------------------------------------------------------- montagem

    def test_a_tabela_tem_as_oito_colunas_declaradas(self) -> None:
        cabecalho = self.dialogo.tabela.headerItem()
        assert cabecalho is not None
        titulos = [cabecalho.text(coluna) for coluna in range(self.dialogo.tabela.columnCount())]
        self.assertEqual(["Brancas", "Elo", "Pretas", "Elo", "Resultado", "Evento", "Data", "ECO"], titulos)

    # ------------------------------------------------ ordenação pelo cabeçalho (S-533, r2)
    #
    # Clicar em "Elo" para achar a partida mais forte da página é o gesto de toda sessão de
    # quem usa uma base, e a tabela não o tinha. Ligá-lo abriu um defeito de um tipo pior que
    # a ausência: a escolha era `indexOfTopLevelItem`, que é a altura na tela, e com a lista
    # ordenada isso deixa de ser a posição em `_achados` -- o duplo clique abriria **outra
    # partida**, plausível e sem erro nenhum.

    def test_a_tabela_da_busca_ordena_e_a_da_fila_nao(self) -> None:
        self.assertTrue(self.dialogo.tabela.isSortingEnabled())

    def test_a_partida_escolhida_e_a_da_linha_marcada_depois_de_ordenar(self) -> None:
        self._buscar(brancas="Carlsen")
        tabela = self.dialogo.tabela
        tabela.sortItems(2, Qt.SortOrder.AscendingOrder)
        primeiro = tabela.topLevelItem(0)
        assert primeiro is not None
        tabela.setCurrentItem(primeiro)

        escolhidas: list[tuple[object, int]] = []
        self.dialogo.partida_escolhida.connect(lambda caminho, offset: escolhidas.append((caminho, offset)))
        self.dialogo.escolher_selecionada()

        (_caminho, offset) = escolhidas[0]
        achado = self.dialogo.selecionada()
        self.assertEqual(primeiro.text(2), achado.pretas, "a linha marcada não é a que foi emitida")
        self.assertEqual(achado.offset, offset)

    def test_ordenar_nao_muda_o_que_a_busca_achou(self) -> None:
        self._buscar(brancas="Carlsen")
        antes = {self.dialogo.tabela.topLevelItem(n).text(0) for n in range(self.dialogo.tabela.topLevelItemCount())}
        self.dialogo.tabela.sortItems(6, Qt.SortOrder.AscendingOrder)
        depois = {self.dialogo.tabela.topLevelItem(n).text(0) for n in range(self.dialogo.tabela.topLevelItemCount())}
        self.assertEqual(antes, depois)
        self.assertEqual(self.PARTIDAS, len(depois | antes) and self.dialogo.tabela.topLevelItemCount())

    def test_a_lista_de_resultado_oferece_os_quatro_valores_do_pgn(self) -> None:
        """O valor gravado, e não o rótulo: é ele que a coluna `result` do índice guarda."""
        valores = [self.dialogo.lista_resultado.itemData(i) for i in range(self.dialogo.lista_resultado.count())]
        self.assertEqual(["", "1-0", "0-1", "1/2-1/2", "*"], valores)

    def test_a_caixa_da_posicao_so_aparece_quando_ha_posicao(self) -> None:
        """Uma opção que não pode ser usada é pior que uma opção ausente (S-32). O diálogo é
        reusado entre aberturas, e a posição é a única coisa dele que envelhece."""
        self.dialogo.show()
        self.app.processEvents()
        self.assertFalse(self.dialogo.caixa_posicao.isVisible())
        self.dialogo.definir_posicao("8/8/8/8/8/8/4K3/4k3")
        self.assertTrue(self.dialogo.caixa_posicao.isVisible())
        self.dialogo.caixa_posicao.setChecked(True)
        self.dialogo.definir_posicao("")
        self.assertFalse(self.dialogo.caixa_posicao.isVisible())
        self.assertFalse(self.dialogo.caixa_posicao.isChecked(), "filtro marcado e invisível é filtro invisível")

    # ---------------------------------------------------------------------------- busca

    def test_a_busca_preenche_a_tabela_e_o_resumo(self) -> None:
        self._buscar(brancas="Carlsen")
        self.assertEqual(self.PARTIDAS, self.dialogo.tabela.topLevelItemCount())
        primeira = self.dialogo.tabela.topLevelItem(0)
        assert primeira is not None
        self.assertEqual("Carlsen, Magnus", primeira.text(0))
        self.assertEqual("B90", primeira.text(7))
        self.assertIn(f"{self.PARTIDAS} partidas", self.dialogo.lbl_resumo.text())
        self.assertIn("Carlsen", self.dialogo.lbl_resumo.text())

    def test_a_busca_nao_roda_na_linha_de_eventos(self) -> None:
        """**O critério de aceite da janela**: com dez milhões de partidas a consulta custa
        centenas de milissegundos, e na linha de eventos isso é a janela branca do Windows. Aqui
        se afirma que ela **começou** sem ter terminado -- que é o que uma thread faz e uma
        chamada direta não."""
        self.dialogo.campo_brancas.setText("Carlsen")
        with mock.patch.object(qt_busca, "buscar", wraps=qt_busca.buscar) as chamada:
            self.assertTrue(self.dialogo.buscar())
            self.assertEqual(qt_busca.EM_BUSCA, self.dialogo.lbl_resumo.text())
            self.assertFalse(self.dialogo.btn_buscar.isEnabled(), "duas buscas ao mesmo tempo")
            self._esperar()
        chamada.assert_called_once()
        self.assertTrue(self.dialogo.btn_buscar.isEnabled())

    def test_o_clique_no_botao_e_o_enter_no_campo_buscam(self) -> None:
        """O `clicked` do Qt carrega um `checked: bool` e o `returnPressed` não carrega nada: os
        dois caminhos chegam a `buscar`, e um posicional a mais seria `TypeError` no clique -- num
        caminho que nenhum teste de unidade percorre."""
        self.dialogo.campo_brancas.setText("Carlsen")
        self.dialogo.btn_buscar.click()
        self._esperar()
        self.assertEqual(self.PARTIDAS, self.dialogo.tabela.topLevelItemCount())
        self.dialogo.tabela.clear()
        self.dialogo.campo_brancas.returnPressed.emit()
        self._esperar()
        self.assertEqual(self.PARTIDAS, self.dialogo.tabela.topLevelItemCount())

    def test_uma_busca_de_cada_vez(self) -> None:
        """A segunda a chegar sobrescreveria a tabela da primeira, e qual delas está na tela
        passaria a depender do disco."""
        self.dialogo.campo_brancas.setText("Carlsen")
        self.assertTrue(self.dialogo.buscar())
        self.assertFalse(self.dialogo.buscar(), "a segunda busca não pode começar")
        self._esperar()

    def test_o_formulario_malfeito_nao_vira_consulta(self) -> None:
        """A frase diz **quais** campos, e a tabela fica vazia -- não é uma busca que achou nada."""
        self.dialogo.campo_ano_de.setText("dois mil")
        with mock.patch.object(qt_busca, "buscar") as chamada:
            self.assertFalse(self.dialogo.buscar())
        chamada.assert_not_called()
        self.assertIn("quatro dígitos", self.dialogo.lbl_resumo.text())
        self.assertEqual(0, self.dialogo.tabela.topLevelItemCount())

    def test_a_busca_sem_filtro_que_estreite_e_recusada(self) -> None:
        with mock.patch.object(qt_busca, "buscar") as chamada:
            self.assertFalse(self.dialogo.buscar())
        chamada.assert_not_called()
        self.assertIn("estreite", self.dialogo.lbl_resumo.text())

    def test_o_filtro_sem_achado_diz_de_que_pergunta_ele_esta_vazio(self) -> None:
        """Uma tabela vazia não diz **de que pergunta** ela está vazia, e quase sempre é um ano
        digitado errado -- não a base."""
        self._buscar(brancas="Kasparov")
        self.assertEqual(0, self.dialogo.tabela.topLevelItemCount())
        self.assertIn("Nenhuma partida", self.dialogo.lbl_resumo.text())
        self.assertIn("Kasparov", self.dialogo.lbl_resumo.text())

    def test_o_indice_indisponivel_vira_frase_com_instrucao_e_nao_tabela_vazia(self) -> None:
        outro = qt_busca.DialogoDeBusca(None, bases=[self.base], indice=self.raiz / "nao_existe.sqlite")
        self.addCleanup(descartar, outro)
        outro.campo_brancas.setText("Carlsen")
        outro.buscar()
        self.assertTrue(outro.esperar(20_000))
        for _ in range(20):
            self.app.processEvents()
        self.assertIn("ainda não foi construído", outro.lbl_resumo.text())
        self.assertIn("--build-index", outro.lbl_resumo.text())

    def test_o_botao_de_indexar_pede_o_indice_a_quem_sabe_construi_lo(self) -> None:
        """O diálogo não constrói o índice: quem tem a barra de progresso e o registro de ocupação
        da janela é a sala (S-532)."""
        pedidos: list[int] = []
        self.dialogo.indice_pedido.connect(lambda: pedidos.append(1))
        self.dialogo.btn_indexar.click()
        self.assertEqual([1], pedidos)

    # --------------------------------------------------------------------------- páginas

    def test_a_pagina_seguinte_e_a_anterior_andam_e_param(self) -> None:
        with mock.patch("chess_diagram_ocr.qt.busca_de_partidas.PAGINA", 3):
            self.dialogo.campo_brancas.setText("Carlsen")
            self.dialogo.buscar()
            self._esperar()
            self.assertEqual(3, self.dialogo.tabela.topLevelItemCount())
            self.assertFalse(self.dialogo.btn_anterior.isEnabled(), "não há página antes da primeira")
            self.assertTrue(self.dialogo.btn_proxima.isEnabled())
            # O texto e lido AGORA: `preencher` troca o conteudo inteiro, e o `QTreeWidgetItem`
            # da pagina anterior deixa de existir no instante em que a seguinte chega.
            primeira = self._pretas_da_primeira_linha()
            self.dialogo.proxima_pagina()
            self._esperar()
            self.assertNotEqual(primeira, self._pretas_da_primeira_linha(), "a segunda página repetiu a primeira")
            self.assertTrue(self.dialogo.btn_anterior.isEnabled())
            self.dialogo.pagina_anterior()
            self._esperar()
            self.assertEqual(primeira, self._pretas_da_primeira_linha())

    def _pretas_da_primeira_linha(self) -> str:
        item = self.dialogo.tabela.topLevelItem(0)
        assert item is not None
        return item.text(2)

    # --------------------------------------------------------------------------- escolha

    def test_o_duplo_clique_emite_onde_a_partida_mora(self) -> None:
        """`(caminho, offset)` e não a partida lida: ler o arquivo aqui dentro poria leitura de
        disco num widget, e a leitura é de quem vai usá-la."""
        self._buscar(brancas="Carlsen")
        escolhidas: list[tuple[object, int]] = []
        self.dialogo.partida_escolhida.connect(lambda caminho, offset: escolhidas.append((caminho, offset)))
        self.dialogo.tabela.setCurrentItem(self.dialogo.tabela.topLevelItem(1))
        item = self.dialogo.tabela.topLevelItem(1)
        assert item is not None
        self.dialogo.tabela.itemDoubleClicked.emit(item, 0)
        self.assertEqual(1, len(escolhidas))
        caminho, offset = escolhidas[0]
        self.assertEqual(self.base, caminho)
        self.assertGreater(offset, 0, "a segunda partida não começa no byte zero")

    def test_o_enter_na_tabela_abre_a_linha_marcada(self) -> None:
        """Quem acabou de rolar a lista com as setas espera que o Enter abra a linha marcada -- e
        não que ele refaça a busca, que é o que o botão padrão de um `QDialog` faria."""
        self._buscar(brancas="Carlsen")
        escolhidas: list[int] = []
        self.dialogo.partida_escolhida.connect(lambda _caminho, offset: escolhidas.append(offset))
        self.dialogo.show()
        self.dialogo.activateWindow()
        self.dialogo.tabela.setFocus()
        self.app.processEvents()
        self.dialogo.tabela.setCurrentItem(self.dialogo.tabela.topLevelItem(0))
        esperado = self.dialogo.selecionada().offset
        QTest.keyClick(self.dialogo.tabela, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual([esperado], escolhidas, "o Enter não chegou à tabela")

    def test_sem_linha_marcada_nada_e_emitido(self) -> None:
        self._buscar(brancas="Carlsen")
        escolhidas: list[int] = []
        self.dialogo.partida_escolhida.connect(lambda _caminho, offset: escolhidas.append(offset))
        self.dialogo.tabela.setCurrentItem(None)
        self.dialogo.escolher_selecionada()
        self.assertEqual([], escolhidas)

    def test_a_escolha_nao_fecha_o_dialogo(self) -> None:
        """Quem procura uma partida quer a lista ainda ali para a próxima."""
        self._buscar(brancas="Carlsen")
        self.dialogo.show()
        self.dialogo.tabela.setCurrentItem(self.dialogo.tabela.topLevelItem(0))
        self.dialogo.escolher_selecionada()
        self.app.processEvents()
        self.assertTrue(self.dialogo.isVisible())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FalhaInesperadaTests(unittest.TestCase):
    """Uma falha que não é `IndiceIndisponivel` vira log **e** frase: uma tabela que não muda não
    diz que houve erro."""

    def test_a_falha_inesperada_vai_para_o_log_e_para_a_frase(self) -> None:
        aplicacao()
        dialogo = qt_busca.DialogoDeBusca(None)
        self.addCleanup(descartar, dialogo)
        with self.assertLogs("chess_diagram_ocr.qt.busca_de_partidas", level="WARNING"):
            dialogo._falhou("o disco sumiu", OSError("o disco sumiu"))
        self.assertIn("o disco sumiu", dialogo.lbl_resumo.text())

    def test_o_indice_indisponivel_nao_polui_o_log(self) -> None:
        """Não é defeito: é um estado com saída, e o botão ao lado é a saída."""
        aplicacao()
        dialogo = qt_busca.DialogoDeBusca(None)
        self.addCleanup(descartar, dialogo)
        with mock.patch.object(qt_busca.logger, "warning") as aviso:
            dialogo._falhou("faça o índice", IndiceIndisponivel("faça o índice"))
        aviso.assert_not_called()
        self.assertIn("faça o índice", dialogo.lbl_resumo.text())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
