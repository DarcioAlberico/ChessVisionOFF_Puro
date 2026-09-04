"""A barra da sala montada: uma fila, `QAction` por ação, e o slot certo em cada disparo (S-527).

**O que só existe deste lado.** Que a fila é uma em qualquer largura e o que não cabe está no
"Mais"; que cada ação virou `QAction` com ícone e dica; que disparar a ação chama o método do
painel -- afirmado pelo **efeito**, e não por `patch` depois do `connect`, que não intercepta
(o sinal guarda a referência antiga); e que o interruptor do catálogo alterna **uma** vez no
clique de mouse, que é o defeito que a medição de 2026-09-04 achou no `QPushButton` de "Treinar".
"""

from __future__ import annotations

import unittest
from unittest import mock

import chess
from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao, descartar, pixels_diferentes, renderizar, tinta

from chess_diagram_ocr.games_index import Indexacao
from chess_diagram_ocr.ui import atalhos, barra_da_sala, comandos, estilos, pele, tokens
from chess_diagram_ocr.ui.busy import BusyRegistry

if TEM_PYQT:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QAction
    from PyQt6.QtTest import QTest

    from chess_diagram_ocr.qt import barra_da_sala as qt_barra
    from chess_diagram_ocr.qt import busca_de_partidas as qt_busca
    from chess_diagram_ocr.qt import icones as qt_icones
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
                    primeira = acao.toolTip().split(chr(10))[0]
                    self.assertTrue(primeira.endswith(barra_da_sala.SEPARADOR_DA_TECLA + atalhos.acelerador(registro.acao)))

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

    def test_o_texto_ao_lado_do_icone_so_em_quem_a_tabela_manda(self) -> None:
        """Dois níveis (`Acao.com_texto`): três com texto, o resto só ícone. O "Mais" tem texto: é o
        único botão cujo rótulo é a própria função."""
        for botao, registro in self.barra._botoes:
            with self.subTest(acao=registro.acao):
                esperado = (
                    Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                    if registro.com_texto
                    else Qt.ToolButtonStyle.ToolButtonIconOnly
                )
                self.assertEqual(esperado, botao.toolButtonStyle())
                self.assertEqual(qt_barra.LADO_DO_ICONE, botao.iconSize().width())
                nivel = tema.NIVEL_TEXTO if registro.com_texto else tema.NIVEL_ICONE
                self.assertEqual(nivel, botao.property(tema.PROPRIEDADE_DE_NIVEL))
                # O texto do item de menu: curto só em quem o escreve no botão; o resto por extenso.
                acao = self.barra.acoes[registro.acao]
                self.assertEqual(registro.rotulo_curto if registro.com_texto else registro.rotulo_longo, acao.text())
        self.assertEqual(Qt.ToolButtonStyle.ToolButtonTextBesideIcon, self.barra.btn_mais.toolButtonStyle())
        # O nível de ícone tem recheio próprio na folha: é o que faz dez caberem em 702 px.
        self.assertIn(f"{tema.SELETOR_DO_NIVEL_ICONE} {{ padding:", tema.folha_de_estilo())

    def test_o_marcado_desenha_diferente_do_desmarcado(self) -> None:
        """**O achado 1 do crítico**: "Seguir OCR" marcado e desmarcado saíam pixel a pixel iguais --
        só havia `:checked` para `QPushButton`. Sob `offscreen` não há fonte, mas há cor de fundo e
        moldura: a face e a borda de ênfase de `QToolButton:checked` têm de mudar pixels."""
        tema.aplicar_tema(self.app)
        self.addCleanup(tema.aplicar_tema, self.app)
        for nome in (barra_da_sala.SEGUIR_OCR, "modo_treino"):
            with self.subTest(acao=nome):
                botao = self.barra.botao_de(nome)
                assert botao is not None
                acao = self.barra.acoes[nome]
                acao.setChecked(False)
                self.app.processEvents()
                antes = botao.grab().toImage()
                acao.setChecked(True)
                self.app.processEvents()
                depois = botao.grab().toImage()
                self.assertEqual(antes.size(), depois.size())
                diferentes = sum(
                    1
                    for x in range(antes.width())
                    for y in range(antes.height())
                    if antes.pixel(x, y) != depois.pixel(x, y)
                )
                self.assertGreater(diferentes, 0, "marcado e desmarcado desenham igual")
                acao.setChecked(False)

    def test_o_mais_tem_cabecalho_de_grupo_visivel(self) -> None:
        """**O achado 2**: `addSection` desenha só a linha no `windows11`. O título é um item
        desabilitado em negrito, um por grupo com item, na ordem da barra."""
        esperados = [
            barra_da_sala.rotulo_do_grupo(g)
            for g in barra_da_sala.GRUPOS
            if any(r.grupo == g for r in barra_da_sala.secundarias(com_motor=True))
        ]
        self.assertEqual(tuple(esperados), self.barra.cabecalhos_do_mais())
        self.assertIn("Posição", esperados)
        for acao in self.barra.menu_mais.actions():
            if acao.property(qt_barra.PROPRIEDADE_DE_CABECALHO) is None:
                continue
            with self.subTest(cabecalho=acao.text()):
                self.assertFalse(acao.isEnabled())
                self.assertTrue(acao.font().bold())
        self.assertNotIn("", self.barra.no_mais())
        # Estreitando, o grupo que transbordou ganha cabeçalho também.
        self.barra.resize(self.barra.btn_mais.sizeHint().width() + 10, 40)
        self.app.processEvents()
        self.assertEqual(
            tuple(barra_da_sala.rotulo_do_grupo(g) for g in barra_da_sala.GRUPOS), self.barra.cabecalhos_do_mais()
        )

    def test_o_mais_fica_logo_depois_do_ultimo_botao(self) -> None:
        """**O achado 3, o espaço morto**: a 1920 px havia ~110 px vazios entre "Símbolo" e "Mais".
        O transbordo mora onde a fila acaba; o vão vai para a direita dele."""
        self.barra.resize(self.larga + 600, 40)
        self.app.processEvents()
        ultimo = max(botao.geometry().right() for botao, _r in self.barra._botoes if not botao.isHidden())
        self.assertLessEqual(self.barra.btn_mais.geometry().left() - ultimo, 40)

    def test_o_texto_que_cresce_repergunta_a_cabem_sem_resize(self) -> None:
        """"Treinar" vira "Parar o treino" sem `resizeEvent`; sem reperguntar, o layout espremia o
        primário -- fotografado elidido ("Carregar…CR atual") a 1400 px. O rearranjo é agendado
        pelo `changed` da ação e roda no giro seguinte do laço."""
        acao = self.barra.acoes["modo_treino"]
        antes = len(self.barra.na_fila())
        acao.setText(comandos.rotulo_alternado("modo_treino"))
        self.app.processEvents()
        self.app.processEvents()
        self.assertLess(len(self.barra.na_fila()), antes, "ninguém saiu para o texto maior caber")
        for botao, _registro in self.barra._botoes:
            if not botao.isHidden():
                self.assertLessEqual(botao.geometry().right(), self.barra.width())
        self.assertLessEqual(self.barra.btn_mais.geometry().right(), self.barra.width())
        acao.setText(comandos.rotulo_de_botao("modo_treino"))
        self.app.processEvents()
        self.app.processEvents()
        self.assertEqual(antes, len(self.barra.na_fila()), "o texto curto devolve quem saiu")

    def test_o_par_promover_rebaixar_entra_e_sai_junto(self) -> None:
        for largura in range(self.barra.btn_mais.sizeHint().width(), self.larga, 7):
            self.barra.resize(largura, 40)
            self.app.processEvents()
            na_fila = set(self.barra.na_fila())
            with self.subTest(largura=largura):
                self.assertEqual("promover_variante" in na_fila, "rebaixar_variante" in na_fila)

    def test_a_tecla_da_sala_esta_na_qaction_com_alcance_de_widget(self) -> None:
        """A tecla é da `QAction` (dispara pelo mesmo caminho do clique, e não dispara desabilitada),
        com alcance no painel e nos filhos -- nunca na janela, que é da guarda de `qt/atalhos.py`."""
        for atalho in atalhos.TECLAS_DA_SALA:
            with self.subTest(acao=atalho.acao):
                acao = self.barra.acoes[atalho.acao]
                self.assertFalse(acao.shortcut().isEmpty())
                self.assertEqual(Qt.ShortcutContext.WidgetWithChildrenShortcut, acao.shortcutContext())
        for registro in barra_da_sala.acoes_para(com_motor=True):
            if registro.acao not in {a.acao for a in atalhos.TECLAS_DA_SALA}:
                self.assertTrue(self.barra.acoes[registro.acao].shortcut().isEmpty(), registro.acao)

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

    def test_treinar_fica_na_fila_e_marcado_enquanto_treina(self) -> None:
        """**O achado 3, o modo**: treinando, o botão da fila é o que sinaliza o modo -- marcado e
        com o texto alternado. Na rodada 1 ele estava no "Mais" e o marcado não se desenhava."""
        self.painel.push_move(chess.Move.from_uci("e2e4"))
        self.painel.alternar_treino()
        botao = self.painel.barra.botao_de("modo_treino")
        assert botao is not None
        self.assertFalse(botao.isHidden())
        self.assertTrue(botao.isChecked())
        self.assertEqual(comandos.rotulo_alternado("modo_treino"), botao.text())
        self.painel.alternar_treino()

    def test_a_tecla_da_sala_chega_ao_metodo_e_respeita_o_modo(self) -> None:
        """`Ctrl+↑` com o foco na sala chama `promover_variante`; sem estudo o grupo Variante está
        cinza e a mesma tecla não faz nada -- a regra do modo vale para o teclado (achado 6)."""
        vistos: list[str] = []
        self.painel.barra._executar = vistos.append
        self.painel.activateWindow()
        self.painel.tabuleiro.setFocus()
        self.app.processEvents()
        self.painel.barra.aplicar_modo(barra_da_sala.SEM_ESTUDO)
        QTest.keyClick(self.painel.tabuleiro, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertEqual([], vistos, "a tecla passou por cima do modo")
        self.painel.barra.aplicar_modo(barra_da_sala.COM_ESTUDO)
        QTest.keyClick(self.painel.tabuleiro, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(self.painel.tabuleiro, Qt.Key.Key_Delete, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertEqual(["promover_variante", "apagar_variante"], vistos)

    def test_indexar_base_chama_o_indexador_com_a_janela_e_o_busy(self) -> None:
        """**O achado 7**: a fiação pendente da S-532. A ação da barra chega ao indexador com a
        janela como pai, as bases da sala e o registro de ocupação; a frase final vai ao status."""
        base = self.pasta / "base.pgn"
        base.write_text('[White "A"]\n[Black "B"]\n\n1. e4 *\n', encoding="utf-8")
        registro = BusyRegistry()
        painel = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.pasta, pasta_de_estudos=self.pasta, bases_de_partidas=lambda: (base,), busy=registro
        )
        self.addCleanup(descartar, painel)
        self.assertIn("indexar_base", painel.barra.no_mais())
        indexador = mock.MagicMock()
        with mock.patch("chess_diagram_ocr.qt.indice_da_base.indexar_com_dialogo", return_value=indexador) as chamado:
            painel.barra.acoes["indexar_base"].trigger()
        chamado.assert_called_once_with(painel.window(), (base,), busy=registro)
        indexador.terminou.connect.assert_called_once()
        frase = indexador.terminou.connect.call_args[0][0]
        frase(Indexacao(partidas=2, relidas=2, arquivos_relidos=1, arquivos_pulados=0, arquivos_removidos=0, cancelado=False))
        self.assertIn("2 partidas no índice", painel.lbl_status.text())

    def test_buscar_partidas_abre_o_dialogo_com_a_janela_e_a_posicao_do_tabuleiro(self) -> None:
        """**A fiação da S-533**, no molde da do índice (S-532): a ação da barra chega ao diálogo
        com a janela como pai e as bases da sala, o filtro por posição já apontando para o
        tabuleiro que está na tela, e a partida escolhida chegando ao método que a abre."""
        base = self.pasta / "base.pgn"
        base.write_text(
            '[Event "Tata Steel"]\n[Date "2019.01.26"]\n[White "Carlsen, Magnus"]\n'
            '[Black "Anand, Viswanathan"]\n[Result "1-0"]\n[ECO "B90"]\n\n'
            "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 1-0\n",
            encoding="utf-8",
        )
        painel = qt_estudo.PainelDeEstudo(
            pasta_inicial=self.pasta, pasta_de_estudos=self.pasta, bases_de_partidas=lambda: (base,)
        )
        self.addCleanup(descartar, painel)
        self.assertIn("buscar_partidas", painel.barra.no_mais())
        dialogo = qt_busca.DialogoDeBusca(None, bases=[base], indice=self.pasta / "indice.sqlite")
        self.addCleanup(descartar, dialogo)
        with mock.patch(
            "chess_diagram_ocr.qt.busca_de_partidas.DialogoDeBusca", return_value=dialogo
        ) as construtor:
            painel.barra.acoes["buscar_partidas"].trigger()
        construtor.assert_called_once_with(painel.window(), bases=(base,))
        self.assertEqual(painel.estudo.tabuleiro.board_fen(), dialogo._posicao, "a posição da sala não chegou")
        self.assertTrue(dialogo.isVisible())
        # E o sinal está ligado ao método que abre a partida -- afirmado pelo **efeito**, porque um
        # `patch` depois do `connect` não intercepta (o sinal guarda a referência antiga).
        dialogo.partida_escolhida.emit(base, 0)
        self.app.processEvents()
        self.assertIn("Carlsen", painel.lbl_origem.text())
        self.assertEqual("ECO B90 · Sicilian, Najdorf", painel.lbl_eco.text(), "o ECO da partida aberta")

    def test_o_dialogo_de_busca_e_reusado_e_a_posicao_e_atualizada(self) -> None:
        """Um `QThread` destruído enquanto roda derruba o processo: abrir a busca duas vezes não
        pode construir dois diálogos. O que envelhece é a posição, e ela é atualizada."""
        painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, painel)
        base = self.pasta / "base.pgn"
        base.write_text('[White "A"]\n[Black "B"]\n\n1. e4 *\n', encoding="utf-8")
        with mock.patch("chess_diagram_ocr.games_db.database_paths", return_value=[base]):
            primeiro = painel.buscar_partidas()
            assert primeiro is not None
            self.addCleanup(descartar, primeiro)
            antes = primeiro._posicao
            painel.push_move(chess.Move.from_uci("e2e4"))
            segundo = painel.buscar_partidas()
        self.assertIs(primeiro, segundo)
        self.assertNotEqual(antes, segundo._posicao, "a segunda abertura filtraria pela posição da primeira")

    def test_sem_base_a_busca_diz_isso_em_vez_de_abrir_janela_vazia(self) -> None:
        painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, painel)
        with mock.patch("chess_diagram_ocr.games_db.database_paths", return_value=[]):
            self.assertIsNone(painel.buscar_partidas())
        self.assertIn("base de partidas", painel.lbl_status.text())

    def test_a_partida_que_o_indice_nao_acha_mais_nao_vira_meia_partida(self) -> None:
        """O índice adiantado em relação ao arquivo: alguém reescreveu o `.pgn`. A frase diz isso,
        e o estudo que estava na mesa fica."""
        painel = qt_estudo.PainelDeEstudo(pasta_inicial=self.pasta, pasta_de_estudos=self.pasta)
        self.addCleanup(descartar, painel)
        base = self.pasta / "vazia.pgn"
        base.write_text("nada aqui\n", encoding="utf-8")
        self.assertFalse(painel.abrir_partida_da_base(base, 0))
        self.assertIn("Refaça o índice", painel.lbl_status.text())

@unittest.skipUnless(TEM_PYQT, MOTIVO)
class BarraQueSeLeTests(unittest.TestCase):
    """Os dois bloqueios da segunda rodada do crítico, medidos **nesta** fila (S-553, S-554).

    Eles têm guarda de folha e de ícone em `tests/test_qt_tema.py` e `tests/test_qt_icones.py`; o
    que só existe aqui é o botão de verdade, com o papel de verdade, nas três peles -- que é onde
    o crítico fotografou. Onze dos catorze botões desta fila são só-ícone, e é isso que fazia o
    critério da S-527 ("Variante e Exportar ficam cinza sem estudo") ser vácuo na pele escura.
    """

    def setUp(self) -> None:
        self.app = aplicacao()
        anterior = self.app.styleSheet()
        self.addCleanup(self.app.setStyleSheet, anterior)
        self.addCleanup(qt_icones.limpar_cache)
        # A pele fica no módulo (`tema._cromo_escuro`): sem devolvê-la, o próximo teste da
        # suíte desenha na pele em que este parou. A limpeza roda ao contrário da ordem de
        # registro, então `aplicar_tema` vem antes de a folha de antes voltar.
        self.addCleanup(tema.aplicar_tema, self.app)
        self.barra = qt_barra.BarraDaSala(None, com_motor=True, executar=lambda _nome: None)
        self.addCleanup(descartar, self.barra)
        self.barra.resize(self.barra.largura_para_todas(), 40)
        self.barra.show()
        self.barra.activateWindow()
        self.app.processEvents()

    def _so_icone(self) -> str:
        """Uma ação principal sem texto, com ícone e sem papel de ênfase -- a maioria da fila.

        Escolhida da tabela e não escrita à mão: um nome literal aqui viraria um teste que passa a
        medir outra coisa no dia em que aquela ação ganhar rótulo.
        """
        for registro in barra_da_sala.principais(com_motor=True):
            if not registro.com_texto and registro.icone and registro.papel == estilos.NEUTRO:
                return registro.acao
        raise AssertionError("a fila não tem botão só-ícone: o item mediria outra coisa")

    def _sem_foco(self, botao: object) -> object:
        """Mostrar a fila dá o foco ao primeiro filho focável -- ver `Foco do Qt vaza entre
        testes`. Sem este `clearFocus` a fotografia de repouso já vem focada."""
        botao.clearFocus()  # type: ignore[attr-defined]
        self.app.processEvents()
        return renderizar(botao)

    def _com_foco(self, botao: object) -> object:
        botao.setFocus(Qt.FocusReason.TabFocusReason)  # type: ignore[attr-defined]
        self.app.processEvents()
        self.assertTrue(botao.hasFocus(), "o botão da fila não recebeu o foco")  # type: ignore[attr-defined]
        desenho = renderizar(botao)
        botao.clearFocus()  # type: ignore[attr-defined]
        self.app.processEvents()
        return desenho

    def test_o_foco_se_ve_no_primario_e_no_so_icone_nas_tres_peles(self) -> None:
        """**O bloqueio 1 do crítico**: `hasFocus()` verdadeiro e **0 px** diferentes, no primário
        e no só-ícone, nas duas peles que ele fotografou. São doze paradas de `Tab` nesta fila."""
        so_icone = self._so_icone()
        for uma in pele.PELES:
            tema.aplicar_tema(self.app, cromo_escuro=uma.cromo_escuro, densidade=uma.densidade)
            self.app.processEvents()
            for nome in ("estudo_do_diagrama", so_icone):
                botao = self.barra.botao_de(nome)
                assert botao is not None
                with self.subTest(pele=uma.nome, acao=nome):
                    self.assertGreater(
                        pixels_diferentes(self._sem_foco(botao), self._com_foco(botao)),
                        0,
                        "focado e não focado desenham igual",
                    )

    def test_o_botao_desabilitado_apaga_o_icone_nas_tres_peles(self) -> None:
        """**O bloqueio 2 do crítico**: na pele "Foco" o só-ícone desabilitado saía idêntico ao
        habilitado -- 9,47:1 dos dois lados --, porque o `QIcon` gerado pelo Qt **clareia**, e numa
        paleta escura clarear é destacar.

        **Os três papéis apagam para a mesma tinta**, e essa é a afirmação que vale para os catorze
        botões: ligado o ícone carrega o papel (letra da ênfase no primário, vermelho no
        destrutivo), desligado não há papel a carregar.

        **A queda de contraste é cobrada no neutro, e é decisão registrada.** No destrutivo a
        tinta ligada é `BOTAO_DESTRUTIVO`, que na pele "Foco" já vale 4,89:1 -- menos que os 7,14
        do cinza --, e ali o que apaga não é o **valor**, é a **matiz**: o vermelho de "isto apaga
        trabalho" some, e o botão vira um cinza igual aos vizinhos, exatamente como o rótulo dele.
        Cobrar queda de razão no destrutivo obrigaria a inventar um cinza mais fraco só para ele --
        uma segunda tinta de desabilitado, que é a divergência que o item veio fechar.
        """
        papeis = {}
        for registro in barra_da_sala.principais(com_motor=True):
            if registro.icone and registro.papel not in papeis:
                papeis[registro.papel] = registro.acao
        self.assertEqual({estilos.PRIMARIO, estilos.NEUTRO, estilos.DESTRUTIVO}, set(papeis))
        for uma in pele.PELES:
            tema.aplicar_tema(self.app, cromo_escuro=uma.cromo_escuro, densidade=uma.densidade)
            qt_icones.limpar_cache()
            self.barra._pintar_icones()
            self.app.processEvents()
            face = tema.cor_atual(tokens.SUPERFICIE_PADRAO)
            for papel, nome in papeis.items():
                acao = self.barra.acoes[nome]
                botao = self.barra.botao_de(nome)
                assert botao is not None
                acao.setEnabled(True)
                self.app.processEvents()
                ligado = renderizar(botao)
                acao.setEnabled(False)
                self.app.processEvents()
                desligado = renderizar(botao)
                traco_ligado, quantos = tinta(ligado, face)
                traco_desligado, _quantos = tinta(desligado, face)
                com_tinta = tokens.razao_de_contraste(traco_ligado, face)
                sem_tinta = tokens.razao_de_contraste(traco_desligado, face)
                with self.subTest(pele=uma.nome, papel=papel, acao=nome):
                    self.assertGreater(quantos, 0, "o botão saiu sem traço nenhum: nada foi medido")
                    self.assertGreater(
                        pixels_diferentes(ligado, desligado), 0, "ligado e desligado desenham igual"
                    )
                    self.assertEqual(qt_icones.tinta_apagada(), traco_desligado)
                    if papel == estilos.NEUTRO:
                        self.assertLess(
                            sem_tinta,
                            com_tinta,
                            f"a tinta não apagou: {com_tinta:.2f}:1 -> {sem_tinta:.2f}:1",
                        )
                acao.setEnabled(True)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
