"""A barra da sala montada: uma fila, `QAction` por ação, e o slot certo em cada disparo (S-527).

**O que só existe deste lado.** Que a fila é uma em qualquer largura e o que não cabe está no
"Mais"; que cada ação virou `QAction` com ícone e dica; que disparar a ação chama o método do
painel -- afirmado pelo **efeito**, e não por `patch` depois do `connect`, que não intercepta
(o sinal guarda a referência antiga); e que o interruptor do catálogo alterna **uma** vez no
clique de mouse, que é o defeito que a medição de 2026-09-04 achou no `QPushButton` de "Treinar".
"""

from __future__ import annotations

import unittest

import chess
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar

from chess_diagram_ocr.ui import atalhos, barra_da_sala, comandos

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QAction
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QToolButton

    from chess_diagram_ocr.qt import barra_da_sala as qt_barra
    from chess_diagram_ocr.qt import painel_de_estudo as qt_estudo
    from chess_diagram_ocr.qt import tema


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class BarraSoltaTests(unittest.TestCase):
    """A barra montada sozinha, com um `executar` que só anota."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.chamadas: list[str] = []
        self.barra = qt_barra.BarraDaSala(None, com_motor=True, executar=self.chamadas.append)
        self.addCleanup(descartar, self.barra)
        # Sob `offscreen` a fonte é outra e cada botão mede mais: "larga" é a largura que a própria
        # barra diz bastar para todas, e não um número de tela.
        self.larga = self.barra.largura_para_todas()
        self.barra.resize(self.larga, 40)
        self.barra.show()
        self.app.processEvents()

    def test_toda_acao_da_tabela_virou_qaction_com_icone_e_dica(self) -> None:
        """Ícone nulo seria um botão de texto no meio de botões com desenho; dica sem a tecla é a
        S-161 de novo -- o atalho existe e não está escrito em lugar nenhum."""
        for registro in barra_da_sala.acoes_para(com_motor=True):
            with self.subTest(acao=registro.acao):
                acao = self.barra.acoes[registro.acao]
                self.assertIsInstance(acao, QAction)
                self.assertEqual(barra_da_sala.dica_de(registro), acao.toolTip())
                if not registro.dentro_de:
                    self.assertFalse(acao.icon().isNull(), "ação sem ícone")
                if registro.no_catalogo and atalhos.acelerador(registro.acao):
                    self.assertIn(f"Tecla: {atalhos.acelerador(registro.acao)}", acao.toolTip())

    def test_a_fila_e_uma_e_larga_mostra_todas_as_principais(self) -> None:
        self.assertEqual(1, self.barra.linhas)
        self.assertEqual(
            tuple(r.acao for r in barra_da_sala.principais(com_motor=True)), self.barra.na_fila()
        )
        self.assertEqual(tuple(r.acao for r in barra_da_sala.secundarias(com_motor=True)), self.barra.no_mais())

    def test_estreita_o_que_nao_cabe_vai_para_o_mais_e_volta(self) -> None:
        """É a S-151 sem quebrar: nenhum botão some sem ter para onde ir, e nada vira segunda fila."""
        todas = set(self.barra.na_fila())
        self.barra.resize(500, 40)
        self.app.processEvents()
        na_fila = set(self.barra.na_fila())
        self.assertLess(len(na_fila), len(todas))
        self.assertEqual(1, self.barra.linhas)
        self.assertEqual(todas - na_fila, set(self.barra.no_mais()) - {r.acao for r in barra_da_sala.secundarias()})
        self.assertIn("estudo_do_diagrama", na_fila, "a de maior prioridade é a última a sair")
        # O botão do "Mais" está sempre na fila e nunca está escondido.
        self.assertFalse(self.barra.btn_mais.isHidden())

        self.barra.resize(self.larga, 40)
        self.app.processEvents()
        self.assertEqual(todas, set(self.barra.na_fila()), "alargar devolve o que saiu")

    def test_o_botao_e_texto_ao_lado_do_icone(self) -> None:
        for botao in self.barra.findChildren(QToolButton):
            with self.subTest(acao=botao.property("acao")):
                self.assertEqual(Qt.ToolButtonStyle.ToolButtonTextBesideIcon, botao.toolButtonStyle())

    def test_o_exportar_abre_os_tres_formatos_e_nao_esta_no_mais(self) -> None:
        agrupador = self.barra.acoes[barra_da_sala.EXPORTAR_ESTUDO]
        menu = agrupador.menu()
        assert menu is not None
        self.assertEqual(
            ["exportar_estudo_md", "exportar_estudo_html", "exportar_estudo_rtf"],
            [str(a.property("acao")) for a in menu.actions()],
        )
        for nome in ("exportar_estudo_md", "exportar_estudo_html", "exportar_estudo_rtf"):
            self.assertNotIn(nome, self.barra.no_mais())
        self.barra.acoes["exportar_estudo_rtf"].trigger()
        self.assertEqual(["exportar_estudo_rtf"], self.chamadas)

    def test_disparar_a_acao_chama_o_executar_com_o_nome(self) -> None:
        for registro in barra_da_sala.acoes_para(com_motor=True):
            if registro.agrupador or registro.marcavel:
                continue
            with self.subTest(acao=registro.acao):
                self.chamadas.clear()
                self.barra.acoes[registro.acao].trigger()
                self.assertEqual([registro.acao], self.chamadas)

    def test_o_interruptor_do_catalogo_devolve_o_estado_antes_de_chamar(self) -> None:
        """O método do painel inverte `isChecked()`; se o botão também invertesse, o clique ligaria
        e desligaria no mesmo gesto. Aqui o `executar` anota e não inverte, então o estado tem de
        voltar ao que era."""
        for nome in ("dobrar_variantes", "mostrar_diagrama", "analise_continua", "modo_treino"):
            with self.subTest(acao=nome):
                self.chamadas.clear()
                acao = self.barra.acoes[nome]
                self.assertFalse(acao.isChecked())
                acao.trigger()
                self.assertEqual([nome], self.chamadas)
                self.assertFalse(acao.isChecked(), "o botão alternou por conta própria")

    def test_o_seguir_ocr_alterna_no_botao_e_avisa(self) -> None:
        acao = self.barra.acoes[barra_da_sala.SEGUIR_OCR]
        acao.trigger()
        self.assertTrue(acao.isChecked())
        self.assertEqual([barra_da_sala.SEGUIR_OCR], self.chamadas)

    def test_o_papel_chega_ao_botao_e_a_folha_o_pinta(self) -> None:
        """O primário ganha face; o destrutivo ganha cor; e a folha tem regra para os dois."""
        primario = self.barra.botao_de("estudo_do_diagrama")
        destrutivo = self.barra.botao_de("apagar_variante")
        assert primario is not None and destrutivo is not None
        self.assertEqual("PRIMARIO", primario.property(tema.PROPRIEDADE_DE_PAPEL))
        self.assertEqual("DESTRUTIVO", destrutivo.property(tema.PROPRIEDADE_DE_PAPEL))
        qss = tema.folha_de_estilo()
        self.assertIn('QToolButton[papel="PRIMARIO"]', qss)
        self.assertIn('QToolButton[papel="DESTRUTIVO"]', qss)
        self.assertIn("QToolButton:disabled", qss)

    def test_aplicar_modo_desliga_o_grupo_e_soma_a_condicao(self) -> None:
        self.barra.aplicar_modo(barra_da_sala.SEM_ESTUDO, {"mostrar_diagrama": False})
        self.assertFalse(self.barra.acoes["promover_variante"].isEnabled())
        self.assertFalse(self.barra.acoes["salvar_estudo"].isEnabled())
        self.assertFalse(self.barra.acoes["exportar_estudo_md"].isEnabled(), "o item do submenu segue o grupo")
        self.assertFalse(self.barra.acoes["mostrar_diagrama"].isEnabled(), "a condição própria desliga")
        self.assertTrue(self.barra.acoes["estudo_do_diagrama"].isEnabled())
        self.barra.aplicar_modo(barra_da_sala.COM_ESTUDO, {"mostrar_diagrama": True})
        self.assertTrue(self.barra.acoes["promover_variante"].isEnabled())
        self.assertTrue(self.barra.acoes["mostrar_diagrama"].isEnabled())

    def test_sem_motor_o_grupo_nao_existe(self) -> None:
        sem = qt_barra.BarraDaSala(None, com_motor=False, executar=self.chamadas.append)
        self.addCleanup(descartar, sem)
        self.assertNotIn("analise_continua", sem.acoes)
        self.assertNotIn("analisar_posicao", sem.no_mais())


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class NoPainelTests(unittest.TestCase):
    """A barra dentro da sala: o disparo chega ao método, e o efeito aparece."""

    def setUp(self) -> None:
        self.app = aplicacao()
        self.pasta = pasta_temporaria(self)
        self.painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, self.painel)
        # Largo o bastante para toda principal ter botão: o clique de mouse de baixo precisa dele.
        self.painel.resize(self.painel.barra.largura_para_todas() + 400, 800)
        self.painel.show()
        self.app.processEvents()

    def test_o_clique_em_treinar_liga_o_treino_uma_vez(self) -> None:
        """**O defeito que o `QPushButton` tinha**: o clique alternava o botão e o método alternava
        de volta, e só o menu treinava. Com a `QAction`, o clique liga."""
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        botao = self.painel.barra.botao_de("modo_treino")
        assert botao is not None and not botao.isHidden()
        QTest.mouseClick(botao, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertTrue(self.painel.btn_treino.isChecked())
        self.assertEqual(comandos.rotulo_alternado("modo_treino"), self.painel.btn_treino.text())
        QTest.mouseClick(botao, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(self.painel.btn_treino.isChecked())

    def test_disparar_cada_acao_do_catalogo_chega_ao_metodo(self) -> None:
        """Afirmado pelo efeito, e não por `patch` depois do `connect`. O efeito comum a todo
        método da sala é a frase no rodapé ou a mudança de estado; aqui se afirma o mais barato
        de cada um: `executar` é chamado com o nome, via a própria tabela.

        Uma `QAction` desabilitada não dispara: sem estudo, Variante e Exportar estão cinza, então
        o modo é posto em "com estudo" antes -- e nenhum método roda de verdade, porque o `refresh`
        de qualquer um deles reaplicaria o modo e apagaria metade da lista."""
        vistos: list[str] = []

        # O `connect` guarda `self._executar` da barra, que é o método **ligado**; trocar o atributo
        # do painel não o intercepta -- por isso a troca é no atributo da barra.
        self.painel.barra._executar = vistos.append
        self.painel.barra.aplicar_modo(barra_da_sala.COM_ESTUDO)
        for registro in barra_da_sala.acoes_para(com_motor=False):
            if registro.agrupador:
                continue
            self.painel.barra.acoes[registro.acao].trigger()
        esperados = [r.acao for r in barra_da_sala.acoes_para(com_motor=False) if not r.agrupador]
        self.assertEqual(sorted(esperados), sorted(vistos))

    def test_sem_estudo_variante_e_exportar_ficam_cinza_e_com_lance_voltam(self) -> None:
        self.assertFalse(self.painel.barra.acoes["promover_variante"].isEnabled())
        self.assertFalse(self.painel.barra.acoes["salvar_estudo"].isEnabled())
        self.assertTrue(self.painel.barra.acoes["estudo_do_diagrama"].isEnabled())
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        self.assertTrue(self.painel.barra.acoes["promover_variante"].isEnabled())
        self.assertTrue(self.painel.barra.acoes["salvar_estudo"].isEnabled())
        self.assertFalse(self.painel.btn_dobra.isEnabled(), "sem variante a dobra continua cinza (S-516)")

    def test_treinando_a_arvore_fica_cinza(self) -> None:
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        self.painel.alternar_treino()
        self.assertFalse(self.painel.barra.acoes["apagar_variante"].isEnabled())
        self.assertTrue(self.painel.btn_treino.isEnabled(), "parar o treino é a saída")
        self.painel.alternar_treino()
        self.assertTrue(self.painel.barra.acoes["apagar_variante"].isEnabled())

    def test_os_nomes_antigos_apontam_para_as_acoes_da_barra(self) -> None:
        """`btn_dobra`, `btn_recorte`, `btn_treino` e `seguir_ocr` são o que o resto do painel chama;
        se deixarem de ser as ações da barra, o botão da fila e o estado do painel divergem."""
        barra = self.painel.barra
        self.assertIs(barra.acoes["dobrar_variantes"], self.painel.btn_dobra)
        self.assertIs(barra.acoes["mostrar_diagrama"], self.painel.btn_recorte)
        self.assertIs(barra.acoes["modo_treino"], self.painel.btn_treino)
        self.assertIs(barra.acoes[barra_da_sala.SEGUIR_OCR], self.painel.seguir_ocr)
        self.assertTrue(self.painel.seguir_ocr.isChecked(), "nasce marcado, como o QCheckBox nascia")
        self.assertIsNone(self.painel.btn_continua, "sem motor não há interruptor de análise")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
